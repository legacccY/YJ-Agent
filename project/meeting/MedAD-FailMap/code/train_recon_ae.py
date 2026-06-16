"""
AE / VAE 重建异常检测训练脚本 — MedAD-FailMap Phase 0
服务: MedAD-FailMap Phase 0, PC-A (A0-train-AE) + PC-B (B0-train-HAM)

复现来源: github.com/caiyu6666/MedIAnomaly
  reconstruction/networks/ae.py         — AE/VAE 结构
  reconstruction/utils/ae_worker.py     — 训练/推理逻辑
  reconstruction/utils/vae_worker.py    — VAE 专用
  reconstruction/utils/base_worker.py   — Adam/无scheduler
  reconstruction/dataload.py            — BraTSAD / ISIC2018

超参锁定（官方明确，复现零偏离，禁私改）:
  - AE 4-block encoder/decoder, channels 16->32->64->64, latent=16
  - 输入 64x64, in_c=1(灰度), 无数据增强
  - Adam lr=1e-3, wd=0, 无 scheduler
  - bs=64, epochs=250 (BraTS) / 250 (ISIC)
  - AE loss: L2 mean; VAE loss: L2 + 0.005*KL
  - Normalize((0.5,),(0.5,)) -> [-1,1]
  - Anomaly score: torch.mean(per-pixel L2, dim=[1,2,3])

Windows 规范:
  - DataLoader: num_workers=4, multiprocessing_context='spawn', pin_memory=False
  - 路径用 pathlib.Path
  - seed + cudnn flags 记录

不启训练: 脚本写好交主线 /loop /run-experiment 跑
"""

import argparse
import os
import random
import csv
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from PIL import Image


# ============================================================
# 官方超参常量（照 MedIAnomaly options.py，禁改）
# ============================================================
OFFICIAL_HPARAMS = {
    "brats": {"epochs": 250, "bs": 64, "lr": 1e-3, "wd": 0, "input_size": 64,
               "in_c": 1, "latent": 16, "normalize_mean": (0.5,), "normalize_std": (0.5,)},
    "isic":  {"epochs": 250, "bs": 64, "lr": 1e-3, "wd": 0, "input_size": 64,
               "in_c": 1, "latent": 16, "normalize_mean": (0.5,), "normalize_std": (0.5,)},
}
VAE_BETA = 0.005  # 官方 losses.py KL weight


# ============================================================
# 网络结构 — 复现自 MedIAnomaly reconstruction/networks/ae.py
# 4-block encoder/decoder, channels 16->32->64->64, latent=16
# ============================================================
class ConvBlock(nn.Module):
    """Conv2d -> BN -> ReLU (depth=1 per block, 官方结构)"""
    def __init__(self, in_c, out_c, stride=2):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_c, out_c, kernel_size=4, stride=stride, padding=1, bias=False),
            nn.BatchNorm2d(out_c),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.block(x)


class DeconvBlock(nn.Module):
    """ConvTranspose2d -> BN -> ReLU; last block: 仅 ConvTranspose2d(bias=False), 无 BN/ReLU/Tanh.
    官方 BasicBlock last_layer=True: layers = layers[:-2] 去掉 BN+ReLU, 线性输出.
    官方 up_conv 统一 bias=False.
    [偏离2 已对齐] 原: bias=True + Tanh; 现: bias=False, 无任何激活.
    """
    def __init__(self, in_c, out_c, last=False):
        super().__init__()
        if last:
            # 官方: 仅 ConvTranspose2d(bias=False), 无后接层 (线性输出)
            self.block = nn.Sequential(
                nn.ConvTranspose2d(in_c, out_c, kernel_size=4, stride=2, padding=1, bias=False),
            )
        else:
            self.block = nn.Sequential(
                nn.ConvTranspose2d(in_c, out_c, kernel_size=4, stride=2, padding=1, bias=False),
                nn.BatchNorm2d(out_c),
                nn.ReLU(inplace=True),
            )

    def forward(self, x):
        return self.block(x)


class AEEncoder(nn.Module):
    """
    64x64 -> 4x4 (16x downsampling)
    channels: in_c(1) -> 16 -> 32 -> 64 -> 64
    官方 MedIAnomaly ae.py Encoder + BottleNeck encoder 侧.

    [偏离1+3 已对齐] 原: 单层 Linear(1024->16).
    现: Linear(1024->2048) -> BN1d(2048) -> ReLU -> Linear(2048->16).
    官方 blocks.py BottleNeck: mid_num=2048, latent_size=16, fm=4, 64 channel.
    """
    _MID_NUM = 2048  # 官方 BottleNeck mid_num 常量

    def __init__(self, in_c=1, base_c=16, latent=16):
        super().__init__()
        self.enc = nn.Sequential(
            ConvBlock(in_c,    base_c),      # 64->32
            ConvBlock(base_c,  base_c*2),    # 32->16
            ConvBlock(base_c*2, base_c*4),   # 16->8
            ConvBlock(base_c*4, base_c*4),   # 8->4
        )
        feat_dim = base_c * 4 * 4 * 4  # 64*4*4 = 1024
        # 官方 encoder 侧两层 MLP
        self.fc = nn.Sequential(
            nn.Linear(feat_dim, self._MID_NUM),
            nn.BatchNorm1d(self._MID_NUM),
            nn.ReLU(inplace=True),
            nn.Linear(self._MID_NUM, latent),
        )

    def forward(self, x):
        h = self.enc(x)
        h = h.view(h.size(0), -1)
        return self.fc(h)


class AEDecoder(nn.Module):
    """latent -> 64x64.

    [偏离4+5 已对齐] 原: 单层 Linear(16->1024).
    现: Linear(16->2048) -> BN1d(2048) -> ReLU -> Linear(2048->1024).
    官方 BottleNeck decoder 侧: 对称两层 MLP.
    输出层 last=True: 无激活/BN (偏离2 连同 DeconvBlock 一起对齐).
    """
    _MID_NUM = 2048  # 官方 BottleNeck mid_num 常量

    def __init__(self, in_c=1, base_c=16, latent=16):
        super().__init__()
        feat_dim = base_c * 4 * 4 * 4  # 64*4*4 = 1024
        # 官方 decoder 侧两层 MLP
        self.fc = nn.Sequential(
            nn.Linear(latent, self._MID_NUM),
            nn.BatchNorm1d(self._MID_NUM),
            nn.ReLU(inplace=True),
            nn.Linear(self._MID_NUM, feat_dim),
        )
        self.dec = nn.Sequential(
            DeconvBlock(base_c*4, base_c*4),         # 4->8
            DeconvBlock(base_c*4, base_c*2),         # 8->16
            DeconvBlock(base_c*2, base_c),           # 16->32
            DeconvBlock(base_c,  in_c, last=True),   # 32->64, 线性输出无激活
        )

    def forward(self, z):
        h = self.fc(z)
        h = h.view(h.size(0), 64, 4, 4)
        return self.dec(h)


class AENet(nn.Module):
    def __init__(self, in_c=1, base_c=16, latent=16):
        super().__init__()
        self.encoder = AEEncoder(in_c, base_c, latent)
        self.decoder = AEDecoder(in_c, base_c, latent)

    def forward(self, x):
        z = self.encoder(x)
        return self.decoder(z)


class VAEBottleNeck(nn.Module):
    """官方 MedIAnomaly blocks.py VaeBottleNeck (继承 BottleNeck):

    enc 侧: Linear(1024->2048) -> BN1d(2048) -> ReLU -> Linear(2048->2*latent_size)
            然后 chunk(2, dim=1) 分出 mu / log_var。
    dec 侧: Linear(latent_size->2048) -> BN1d(2048) -> ReLU -> Linear(2048->1024)。
    与 AE BottleNeck 同款两层 MLP，mid_num=2048。
    """
    _MID_NUM = 2048  # 官方 BottleNeck mid_num 常量

    def __init__(self, feat_dim, latent=16):
        super().__init__()
        # enc 侧: 两层 MLP 出 2*latent，chunk 分 mu/log_var
        self.fc_enc = nn.Sequential(
            nn.Linear(feat_dim, self._MID_NUM),
            nn.BatchNorm1d(self._MID_NUM),
            nn.ReLU(inplace=True),
            nn.Linear(self._MID_NUM, 2 * latent),
        )
        # dec 侧: 两层 MLP，latent -> feat_dim
        self.fc_dec = nn.Sequential(
            nn.Linear(latent, self._MID_NUM),
            nn.BatchNorm1d(self._MID_NUM),
            nn.ReLU(inplace=True),
            nn.Linear(self._MID_NUM, feat_dim),
        )

    def reparameterize(self, mu, log_var):
        std = torch.exp(0.5 * log_var)
        eps = torch.randn_like(std)
        return mu + eps * std

    def forward(self, h):
        z_params = self.fc_enc(h)                    # (B, 2*latent)
        mu, lv = z_params.chunk(2, dim=1)            # 各 (B, latent)
        z = self.reparameterize(mu, lv)              # (B, latent)
        return self.fc_dec(z), mu, lv


class VAENet(nn.Module):
    """
    VAE 结构: 同 AE encoder/decoder + VaeBottleNeck
    官方 vae.py
    """
    def __init__(self, in_c=1, base_c=16, latent=16):
        super().__init__()
        feat_dim = base_c*4 * 4 * 4
        self.enc_conv = nn.Sequential(
            ConvBlock(in_c,    base_c),
            ConvBlock(base_c,  base_c*2),
            ConvBlock(base_c*2, base_c*4),
            ConvBlock(base_c*4, base_c*4),
        )
        self.bottleneck = VAEBottleNeck(feat_dim, latent)
        self.dec = nn.Sequential(
            DeconvBlock(base_c*4, base_c*4),
            DeconvBlock(base_c*4, base_c*2),
            DeconvBlock(base_c*2, base_c),
            DeconvBlock(base_c,  in_c, last=True),
        )

    def forward(self, x):
        h = self.enc_conv(x).view(x.size(0), -1)
        h_dec, mu, lv = self.bottleneck(h)
        h_dec = h_dec.view(x.size(0), 64, 4, 4)
        recon = self.dec(h_dec)
        return recon, mu, lv


def vae_loss(x, recon, mu, lv, beta=VAE_BETA):
    """官方 losses.py: L2 mean + beta*KL (mean over batch)"""
    recon_loss = torch.mean((x - recon) ** 2)
    kl = -0.5 * torch.mean(1 + lv - mu.pow(2) - lv.exp())
    return recon_loss + beta * kl, recon_loss, kl


# ============================================================
# Dataset
# ============================================================
def get_transform(input_size=64, mean=(0.5,), std=(0.5,)):
    """官方 dataload.py: resize->64x64, ToTensor, Normalize(0.5,0.5)。无数据增强。"""
    return transforms.Compose([
        transforms.Resize((input_size, input_size)),
        transforms.Grayscale(num_output_channels=1),  # 灰度, 官方 in_c=1
        transforms.ToTensor(),
        transforms.Normalize(mean=mean, std=std),
    ])


class BraTSTrainDataset(Dataset):
    """
    BraTS2021 训练集: train/ 目录下正常切片 (4211 张)
    官方 dataload.py BraTSAD: 只用 train/ (all normal)
    目录期望结构 (Zenodo MedIAnomaly-Data):
      <root>/brats/train/         <- 正常切片 png
      <root>/brats/test/normal/   <- 测试正常
      <root>/brats/test/tumor/    <- 测试异常
      <root>/brats/test/annotation/ <- 像素 mask
    """
    def __init__(self, root, transform=None):
        self.root = Path(root)
        train_dir = self.root / "BraTS2021" / "train"  # 官方 Zenodo 目录名
        if not train_dir.exists():
            raise FileNotFoundError(f"BraTS train dir not found: {train_dir}")
        self.files = sorted([
            p for p in train_dir.iterdir()
            if p.suffix.lower() in (".png", ".jpg", ".jpeg")
        ])
        if len(self.files) == 0:
            raise RuntimeError(f"No images in {train_dir}")
        self.transform = transform

    def __len__(self):
        return len(self.files)

    def __getitem__(self, idx):
        img = Image.open(self.files[idx]).convert("L")
        if self.transform:
            img = self.transform(img)
        return img, self.files[idx].name


class HAMNVTrainDataset(Dataset):
    """
    HAM10000 NV(nevus) 子集训练集 — 官方 ISIC2018 Task3 协议
    官方 dataload.py ISIC2018: NV = label 0 = 正常
    本地: project/data/external/ham10000/
    期望结构: <root>/images/*.jpg + <root>/HAM10000_metadata.csv (dx 列)
              或预分好的 <root>/train_nv/ 目录

    官方 6705 NV 训练图, 同 64x64 Normalize(0.5,0.5) 无增强
    """
    def __init__(self, root, transform=None):
        self.root = Path(root)
        # 优先读预分好的 train_nv 目录
        train_nv_dir = self.root / "train_nv"
        if train_nv_dir.exists():
            self.files = sorted([
                p for p in train_nv_dir.iterdir()
                if p.suffix.lower() in (".png", ".jpg", ".jpeg")
            ])
        else:
            # fallback: 从 metadata 过滤 NV
            meta_csv = self.root / "HAM10000_metadata.csv"
            img_dir  = self.root / "images"
            if not meta_csv.exists() or not img_dir.exists():
                raise FileNotFoundError(
                    f"HAM10000: need either {train_nv_dir} or "
                    f"{meta_csv} + {img_dir}"
                )
            import csv as _csv
            with open(meta_csv, newline="") as f:
                reader = _csv.DictReader(f)
                nv_ids = [row["image_id"] for row in reader if row["dx"].strip().lower() == "nv"]
            self.files = []
            for iid in nv_ids:
                for ext in (".jpg", ".png", ".jpeg"):
                    p = img_dir / (iid + ext)
                    if p.exists():
                        self.files.append(p)
                        break
        if len(self.files) == 0:
            raise RuntimeError(f"No HAM10000 NV images found under {self.root}")
        self.transform = transform

    def __len__(self):
        return len(self.files)

    def __getitem__(self, idx):
        img = Image.open(self.files[idx]).convert("L")
        if self.transform:
            img = self.transform(img)
        return img, self.files[idx].name


# ============================================================
# 推理: 计算 per-image anomaly score + 保存 csv
# ============================================================
@torch.no_grad()
def compute_anomaly_scores(model, dataloader, device, model_type="ae"):
    """
    官方 ae_worker.py: score = torch.mean(per-pixel L2 map, dim=[1,2,3])
    返回 list of (filename, score)
    """
    model.eval()
    results = []
    for batch in dataloader:
        imgs, fnames = batch
        imgs = imgs.to(device)
        if model_type == "vae":
            recon, _, _ = model(imgs)
        else:
            recon = model(imgs)
        score_maps = (imgs - recon) ** 2          # [B,1,H,W]
        scores = torch.mean(score_maps, dim=[1,2,3])  # [B]
        for fname, s in zip(fnames, scores.cpu().tolist()):
            results.append((fname, s))
    return results


# ============================================================
# 主训练循环
# ============================================================
def set_seed(seed=42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def train(args):
    set_seed(args.seed)

    # 超参 (官方锁定)
    hp = OFFICIAL_HPARAMS[args.dataset]
    epochs     = hp["epochs"]
    bs         = hp["bs"]
    lr         = hp["lr"]
    wd         = hp["wd"]
    input_size = hp["input_size"]
    in_c       = hp["in_c"]
    latent     = hp["latent"]

    device = torch.device(f"cuda:{args.gpu}" if torch.cuda.is_available() else "cpu")
    print(f"[train] dataset={args.dataset} model={args.model} "
          f"epochs={epochs} bs={bs} lr={lr} latent={latent} device={device}")

    transform = get_transform(input_size,
                              mean=hp["normalize_mean"],
                              std=hp["normalize_std"])

    # Dataset
    if args.dataset == "brats":
        train_ds = BraTSTrainDataset(root=args.data_root, transform=transform)
    elif args.dataset == "isic":
        train_ds = HAMNVTrainDataset(root=args.data_root, transform=transform)
    else:
        raise ValueError(f"Unknown dataset: {args.dataset}")

    # DataLoader — Windows spawn 规范
    train_loader = DataLoader(
        train_ds,
        batch_size=bs,
        shuffle=True,
        num_workers=args.num_workers,
        multiprocessing_context="spawn" if args.num_workers > 0 else None,
        pin_memory=False,   # spawn worker 不支持 pin_memory
        drop_last=True,
    )

    # Model
    if args.model == "ae":
        model = AENet(in_c=in_c, base_c=16, latent=latent).to(device)
    elif args.model == "vae":
        model = VAENet(in_c=in_c, base_c=16, latent=latent).to(device)
    else:
        raise ValueError(f"Unknown model: {args.model}")

    # Optimizer — Adam lr=1e-3 wd=0 无 scheduler (官方 base_worker.py)
    optimizer = optim.Adam(model.parameters(), lr=lr, weight_decay=wd)

    # Output dirs
    out_dir = Path(args.out_dir)
    ckpt_dir = out_dir / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    # Training log
    log_path = out_dir / f"train_log_{args.dataset}_{args.model}.csv"
    with open(log_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["epoch", "loss", "elapsed_s"])

    # Save config
    cfg = {
        "dataset": args.dataset,
        "model": args.model,
        "epochs": epochs,
        "bs": bs,
        "lr": lr,
        "wd": wd,
        "latent": latent,
        "input_size": input_size,
        "vae_beta": VAE_BETA if args.model == "vae" else None,
        "seed": args.seed,
        "source": "MedIAnomaly github.com/caiyu6666/MedIAnomaly (复现零偏离)",
    }
    with open(out_dir / f"config_{args.dataset}_{args.model}.json", "w") as f:
        json.dump(cfg, f, indent=2)

    t0 = time.time()
    for epoch in range(1, epochs + 1):
        model.train()
        epoch_loss = 0.0
        n_batches  = 0
        for batch in train_loader:
            imgs, _ = batch
            imgs = imgs.to(device)
            optimizer.zero_grad()
            if args.model == "vae":
                recon, mu, lv = model(imgs)
                loss, _, _ = vae_loss(imgs, recon, mu, lv, beta=VAE_BETA)
            else:
                recon = model(imgs)
                loss = torch.mean((imgs - recon) ** 2)  # 官方 L2 mean
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
            n_batches  += 1

        avg_loss = epoch_loss / max(n_batches, 1)
        elapsed  = time.time() - t0

        if epoch % 10 == 0 or epoch == 1 or epoch == epochs:
            print(f"  epoch {epoch:3d}/{epochs} | loss={avg_loss:.5f} | {elapsed:.0f}s")

        with open(log_path, "a", newline="") as f:
            csv.writer(f).writerow([epoch, avg_loss, round(elapsed, 1)])

    # Save checkpoint
    ckpt_path = ckpt_dir / f"{args.dataset}_{args.model}_ep{epochs}.pt"
    torch.save({
        "epoch":       epochs,
        "model_state": model.state_dict(),
        "config":      cfg,
    }, ckpt_path)
    print(f"[train] checkpoint saved: {ckpt_path}")

    # ---- 推理: 生成 anomaly score csv ----
    # BraTS test set (normal + tumor)
    if args.dataset == "brats":
        _save_brats_scores(model, args, transform, device, out_dir)
    elif args.dataset == "isic":
        _save_isic_scores(model, args, transform, device, out_dir)

    print(f"[train] done. total={time.time()-t0:.0f}s")


def _save_brats_scores(model, args, transform, device, out_dir):
    """BraTS test normal + tumor anomaly scores"""
    data_root = Path(args.data_root) / "BraTS2021" / "test"  # 官方 Zenodo 目录名
    score_rows = []
    for split in ("normal", "tumor"):
        split_dir = data_root / split
        if not split_dir.exists():
            print(f"[score] skip {split_dir} (not found)")
            continue
        files = sorted([p for p in split_dir.iterdir()
                        if p.suffix.lower() in (".png", ".jpg", ".jpeg")])
        ds = _ListDataset(files, transform)
        loader = DataLoader(ds, batch_size=64, shuffle=False,
                            num_workers=args.num_workers,
                            multiprocessing_context="spawn" if args.num_workers > 0 else None,
                            pin_memory=False)
        results = compute_anomaly_scores(model, loader, device, args.model)
        for fname, s in results:
            score_rows.append({"filename": fname, "split": split,
                                "anomaly_score": s, "label": 1 if split == "tumor" else 0})
    csv_path = out_dir / f"anomaly_scores_brats_{args.model}.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["filename","split","anomaly_score","label"])
        writer.writeheader()
        writer.writerows(score_rows)
    print(f"[score] brats scores -> {csv_path} ({len(score_rows)} rows)")


def _save_isic_scores(model, args, transform, device, out_dir):
    """HAM10000 test anomaly scores"""
    data_root = Path(args.data_root)
    # 尝试 test_nv / test_abnormal 目录结构
    score_rows = []
    for split_name, label in [("test_nv", 0), ("test_abnormal", 1)]:
        split_dir = data_root / split_name
        if not split_dir.exists():
            print(f"[score] skip {split_dir} (not found)")
            continue
        files = sorted([p for p in split_dir.iterdir()
                        if p.suffix.lower() in (".png", ".jpg", ".jpeg")])
        ds = _ListDataset(files, transform)
        loader = DataLoader(ds, batch_size=64, shuffle=False,
                            num_workers=args.num_workers,
                            multiprocessing_context="spawn" if args.num_workers > 0 else None,
                            pin_memory=False)
        results = compute_anomaly_scores(model, loader, device, args.model)
        for fname, s in results:
            score_rows.append({"filename": fname, "split": split_name,
                                "anomaly_score": s, "label": label})
    if score_rows:
        csv_path = out_dir / f"anomaly_scores_isic_{args.model}.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["filename","split","anomaly_score","label"])
            writer.writeheader()
            writer.writerows(score_rows)
        print(f"[score] isic scores -> {csv_path} ({len(score_rows)} rows)")
    else:
        print("[score] no ISIC test splits found; skip score csv")


class _ListDataset(Dataset):
    def __init__(self, files, transform):
        self.files = files
        self.transform = transform

    def __len__(self):
        return len(self.files)

    def __getitem__(self, idx):
        img = Image.open(self.files[idx]).convert("L")
        if self.transform:
            img = self.transform(img)
        return img, self.files[idx].name


# ============================================================
# Entry point
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MedAD-FailMap AE/VAE 训练 (MedIAnomaly 官方超参复现)")
    parser.add_argument("-d", "--dataset", choices=["brats", "isic"], required=True,
                        help="brats=BraTS2021 (A0), isic=HAM10000-NV (B0)")
    parser.add_argument("-m", "--model",   choices=["ae", "vae"],     required=True,
                        help="ae=AE, vae=VAE")
    parser.add_argument("--data-root", default=None,
                        help="数据根目录。brats: 含 brats/train/ 的目录；"
                             "isic: project/data/external/ham10000/")
    parser.add_argument("--out-dir",   default=None,
                        help="输出目录 (ckpt + score csv)。默认 project/meeting/MedAD-FailMap/results/")
    parser.add_argument("-g", "--gpu",  type=int, default=0)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--seed",  type=int, default=42)
    args = parser.parse_args()

    # 默认路径
    _repo_root = Path(__file__).resolve().parent.parent  # project/meeting/MedAD-FailMap/
    if args.data_root is None:
        if args.dataset == "brats":
            args.data_root = str(_repo_root / "data")
        else:
            args.data_root = str(Path(__file__).resolve().parents[3] / "data" / "external" / "ham10000")
    if args.out_dir is None:
        args.out_dir = str(_repo_root / "results")

    train(args)
