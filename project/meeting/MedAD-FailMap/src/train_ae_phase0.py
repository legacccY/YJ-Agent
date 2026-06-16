"""
AE 重建异常检测训练脚本 — MedAD-FailMap Phase 0 / run A0-train-AE
服务: MedAD-FailMap Pillar① Phase0 (PC-A 地基)

复现来源: github.com/caiyu6666/MedIAnomaly
  reconstruction/networks/ae.py         — AE 结构
  reconstruction/utils/ae_worker.py     — 训练/推理逻辑
  reconstruction/utils/base_worker.py   — Adam/无scheduler
  reconstruction/dataload.py            — BraTSAD

超参锁定（官方明确，复现零偏离，禁私改）:
  - AE 4-block encoder/decoder, channels 16->32->64->64, latent=16
  - 输入 64x64, in_c=1(灰度), 无数据增强
  - Adam lr=1e-3, wd=0, 无 scheduler
  - bs=64, epochs=250 (BraTS)
  - AE loss: L2 mean
  - Normalize((0.5,),(0.5,)) -> [-1,1]
  - Anomaly score: torch.mean(per-pixel L2, dim=[1,2,3])

接 run-experiment 流水线:
  - 启动时写 pid 到 D:/YJ-Agent/log/experiment_state.json
  - 每 epoch 末更新 progress 字段

Windows 规范:
  - DataLoader: num_workers>=1 时 multiprocessing_context='spawn', pin_memory=False
  - 路径用 pathlib.Path
  - 无 scipy (避 OMP Error #15)
"""

import argparse
import csv
import json
import os
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import yaml
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms


# ============================================================
# 官方超参常量（照 MedIAnomaly options.py，禁改）
# ============================================================
OFFICIAL_HPARAMS = {
    "brats": {
        "epochs": 250,
        "bs": 64,
        "lr": 1e-3,
        "wd": 0,
        "input_size": 64,
        "in_c": 1,
        "latent": 16,
        "normalize_mean": (0.5,),
        "normalize_std": (0.5,),
    },
    "isic": {
        "epochs": 250,
        "bs": 64,
        "lr": 1e-3,
        "wd": 0,
        "input_size": 64,
        "in_c": 1,
        "latent": 16,
        "normalize_mean": (0.5,),
        "normalize_std": (0.5,),
    },
}


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
    """ConvTranspose2d -> BN -> ReLU (last block uses Tanh, 无 BN)"""
    def __init__(self, in_c, out_c, last=False):
        super().__init__()
        if last:
            self.block = nn.Sequential(
                nn.ConvTranspose2d(in_c, out_c, kernel_size=4, stride=2, padding=1, bias=True),
                nn.Tanh(),
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
    官方 MedIAnomaly ae.py Encoder
    """
    def __init__(self, in_c=1, base_c=16, latent=16):
        super().__init__()
        self.enc = nn.Sequential(
            ConvBlock(in_c,      base_c),       # 64->32
            ConvBlock(base_c,    base_c * 2),   # 32->16
            ConvBlock(base_c*2,  base_c * 4),   # 16->8
            ConvBlock(base_c*4,  base_c * 4),   # 8->4
        )
        self.fc = nn.Linear(base_c * 4 * 4 * 4, latent)

    def forward(self, x):
        h = self.enc(x)
        h = h.view(h.size(0), -1)
        return self.fc(h)


class AEDecoder(nn.Module):
    """latent -> 64x64"""
    def __init__(self, in_c=1, base_c=16, latent=16):
        super().__init__()
        self.fc = nn.Linear(latent, base_c * 4 * 4 * 4)
        self.dec = nn.Sequential(
            DeconvBlock(base_c * 4, base_c * 4),          # 4->8
            DeconvBlock(base_c * 4, base_c * 2),          # 8->16
            DeconvBlock(base_c * 2, base_c),              # 16->32
            DeconvBlock(base_c,     in_c, last=True),     # 32->64, Tanh
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


# ============================================================
# Dataset — BraTS2021
# TODO: 数据未下载，见 datasets.json medianomaly_bench (status=todo)
#       Zenodo: https://zenodo.org/records/12677223
#       期望结构: <data_root>/brats/train/*.png
# ============================================================
def get_transform(input_size=64, mean=(0.5,), std=(0.5,)):
    """官方 dataload.py: resize->64x64, ToTensor, Normalize(0.5,0.5)。无数据增强。"""
    return transforms.Compose([
        transforms.Resize((input_size, input_size)),
        transforms.Grayscale(num_output_channels=1),
        transforms.ToTensor(),
        transforms.Normalize(mean=mean, std=std),
    ])


class BraTSTrainDataset(Dataset):
    """
    BraTS2021 训练集: brats/train/ 目录下正常切片 (4211 张)
    官方 dataload.py BraTSAD: 只用 train/ (all normal)
    目录期望结构 (Zenodo MedIAnomaly-Data):
      <data_root>/brats/train/          <- 正常切片 png
      <data_root>/brats/test/normal/    <- 测试正常
      <data_root>/brats/test/tumor/     <- 测试异常
      <data_root>/brats/test/annotation/ <- 像素 mask
    """
    def __init__(self, data_root: Path, transform=None):
        # TODO: 数据未下载，见 datasets.json medianomaly_bench (status=todo)
        train_dir = data_root / "brats" / "train"
        if not train_dir.exists():
            raise FileNotFoundError(
                f"BraTS2021 训练目录不存在: {train_dir}\n"
                f"请先从 Zenodo https://zenodo.org/records/12677223 下载数据，\n"
                f"解压至 {data_root}，确保 brats/train/ 存在。\n"
                f"详见 .portfolio/datasets.json 的 medianomaly_bench 条目。"
            )
        self.files = sorted([
            p for p in train_dir.iterdir()
            if p.suffix.lower() in (".png", ".jpg", ".jpeg")
        ])
        if len(self.files) == 0:
            raise RuntimeError(f"BraTS train_dir 中无图像文件: {train_dir}")
        self.transform = transform

    def __len__(self):
        return len(self.files)

    def __getitem__(self, idx):
        img = Image.open(self.files[idx]).convert("L")
        if self.transform:
            img = self.transform(img)
        return img, self.files[idx].name


# ============================================================
# state.json — run-experiment 流水线对接
# ============================================================
STATE_JSON = Path("D:/YJ-Agent/log/experiment_state.json")


def _write_state(patch: dict):
    """读取现有 state.json，合并 patch 后写回（不整体覆盖）。"""
    STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    state = {}
    if STATE_JSON.exists():
        try:
            with open(STATE_JSON, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {}
    # 深合并 patch（只改 patch 指定的 key，不清空其他字段）
    def _merge(base, delta):
        for k, v in delta.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                _merge(base[k], v)
            else:
                base[k] = v
    _merge(state, patch)
    with open(STATE_JSON, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ============================================================
# 工具
# ============================================================
def set_seed(seed: int = 42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def load_config(config_path: str) -> dict:
    """加载 yaml config，返回 dict。"""
    p = Path(config_path)
    if not p.exists():
        raise FileNotFoundError(f"Config 不存在: {p}")
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ============================================================
# 推理: per-image anomaly score
# ============================================================
@torch.no_grad()
def compute_anomaly_scores(model, dataloader, device):
    """
    官方 ae_worker.py: score = torch.mean(per-pixel L2 map, dim=[1,2,3])
    返回 list of (filename, score)
    """
    model.eval()
    results = []
    for imgs, fnames in dataloader:
        imgs = imgs.to(device)
        recon = model(imgs)
        scores = torch.mean((imgs - recon) ** 2, dim=[1, 2, 3])
        for fname, s in zip(fnames, scores.cpu().tolist()):
            results.append((fname, s))
    return results


# ============================================================
# 主训练函数
# ============================================================
def train(cfg: dict):
    seed       = cfg.get("seed", 42)
    dataset    = cfg["dataset"]           # "brats"
    gpu        = cfg.get("gpu", 0)
    num_workers = cfg.get("num_workers", 4)
    data_root  = Path(cfg["data_root"])
    out_dir    = Path(cfg["out_dir"])

    set_seed(seed)

    # 超参（官方锁定，从 OFFICIAL_HPARAMS 取，禁 config 覆盖核心超参）
    hp         = OFFICIAL_HPARAMS[dataset]
    epochs     = hp["epochs"]
    bs         = hp["bs"]
    lr         = hp["lr"]
    wd         = hp["wd"]
    input_size = hp["input_size"]
    in_c       = hp["in_c"]
    latent     = hp["latent"]

    device = torch.device(f"cuda:{gpu}" if torch.cuda.is_available() else "cpu")
    print(f"[train] dataset={dataset} model=ae epochs={epochs} bs={bs} "
          f"lr={lr} latent={latent} device={device}")

    # 写 pid 到 state.json（run-experiment 流水线依赖）
    _write_state({
        "process": {
            "pid": os.getpid(),
            "is_alive": True,
            "last_checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
        "progress": {
            "current_epoch": 0,
            "total_epochs": epochs,
            "last_loss": None,
            "last_val_metric": None,
            "val_metric_history": [],
            "last_update_at": None,
        },
        "checkpoint": {
            "save_dir": str(out_dir / "checkpoints"),
            "last_path": None,
            "best_path": None,
            "last_epoch_saved": None,
        },
    })
    print(f"[train] pid={os.getpid()} written to {STATE_JSON}")

    transform = get_transform(input_size,
                              mean=hp["normalize_mean"],
                              std=hp["normalize_std"])

    train_ds = BraTSTrainDataset(data_root=data_root, transform=transform)
    print(f"[train] dataset size: {len(train_ds)} images")

    # DataLoader — Windows spawn 规范
    train_loader = DataLoader(
        train_ds,
        batch_size=bs,
        shuffle=True,
        num_workers=num_workers,
        multiprocessing_context="spawn" if num_workers > 0 else None,
        pin_memory=False,   # Windows spawn worker 不支持 pin_memory=True
        drop_last=True,
    )

    # AE 模型（官方 4-block, base_c=16, latent=16）
    model = AENet(in_c=in_c, base_c=16, latent=latent).to(device)

    # Adam lr=1e-3 wd=0 无 scheduler（官方 base_worker.py）
    optimizer = optim.Adam(model.parameters(), lr=lr, weight_decay=wd)

    # 输出目录
    ckpt_dir = out_dir / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    log_path = out_dir / "train_log_brats_ae.csv"
    with open(log_path, "w", newline="") as f:
        csv.writer(f).writerow(["epoch", "loss", "elapsed_s"])

    # 保存 config 快照
    config_snapshot = {
        "dataset": dataset,
        "model": "ae",
        "epochs": epochs,
        "bs": bs,
        "lr": lr,
        "wd": wd,
        "latent": latent,
        "input_size": input_size,
        "seed": seed,
        "source": "MedIAnomaly github.com/caiyu6666/MedIAnomaly (复现零偏离)",
    }
    with open(out_dir / "config_brats_ae.json", "w") as f:
        json.dump(config_snapshot, f, indent=2)

    t0 = time.time()
    for epoch in range(1, epochs + 1):
        model.train()
        epoch_loss = 0.0
        n_batches  = 0

        for imgs, _ in train_loader:
            imgs = imgs.to(device)
            optimizer.zero_grad()
            recon = model(imgs)
            loss  = torch.mean((imgs - recon) ** 2)   # 官方 L2 mean
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

        # 每 epoch 末写 state.json progress（run-experiment 监控依赖）
        _write_state({
            "progress": {
                "current_epoch": epoch,
                "total_epochs": epochs,
                "last_loss": round(avg_loss, 6),
                "last_val_metric": None,   # AE 训练阶段无验证集 metric
                "last_update_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        })

        # Checkpoint — 每 50 epoch 保存一次 + 最终 epoch
        if epoch % 50 == 0 or epoch == epochs:
            ckpt_path = ckpt_dir / f"brats_ae_ep{epoch:03d}.pt"
            torch.save({
                "epoch":       epoch,
                "model_state": model.state_dict(),
                "config":      config_snapshot,
            }, ckpt_path)
            _write_state({
                "checkpoint": {
                    "last_path": str(ckpt_path),
                    "last_epoch_saved": epoch,
                }
            })
            print(f"  [ckpt] saved: {ckpt_path}")

    # 最终 checkpoint 标为 best（无验证集，直接用最终）
    final_ckpt = ckpt_dir / f"brats_ae_ep{epochs:03d}.pt"
    _write_state({
        "checkpoint": {
            "best_path": str(final_ckpt),
        }
    })

    # 推理: 生成 anomaly score csv（test normal + tumor）
    _save_brats_scores(model, data_root, num_workers, transform, device, out_dir)

    total_time = time.time() - t0
    print(f"[train] done. total={total_time:.0f}s")
    print("Training complete.")   # run-experiment 流水线检测关键字


def _save_brats_scores(model, data_root: Path, num_workers: int,
                       transform, device, out_dir: Path):
    """BraTS test normal + tumor anomaly scores -> csv"""
    test_dir = data_root / "brats" / "test"
    score_rows = []

    for split, label in [("normal", 0), ("tumor", 1)]:
        split_dir = test_dir / split
        if not split_dir.exists():
            print(f"[score] skip {split_dir} (not found)")
            continue
        files = sorted([
            p for p in split_dir.iterdir()
            if p.suffix.lower() in (".png", ".jpg", ".jpeg")
        ])
        ds = _ListDataset(files, transform)
        loader = DataLoader(
            ds, batch_size=64, shuffle=False,
            num_workers=num_workers,
            multiprocessing_context="spawn" if num_workers > 0 else None,
            pin_memory=False,
        )
        results = compute_anomaly_scores(model, loader, device)
        for fname, s in results:
            score_rows.append({
                "filename": fname,
                "split": split,
                "anomaly_score": s,
                "label": label,
            })

    if score_rows:
        csv_path = out_dir / "anomaly_scores_brats_ae.csv"
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["filename", "split", "anomaly_score", "label"])
            w.writeheader()
            w.writerows(score_rows)
        print(f"[score] brats scores -> {csv_path} ({len(score_rows)} rows)")
    else:
        print("[score] no brats test splits found; skip score csv")


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
def parse_args():
    parser = argparse.ArgumentParser(
        description="MedAD-FailMap A0-train-AE (MedIAnomaly 官方超参复现)"
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="YAML config 路径（可选）。若提供则从 config 读 data_root/out_dir/gpu 等字段。",
    )
    # 命令行参数可覆盖 config（run-experiment 传 --config 即可）
    parser.add_argument("--data-root", type=str, default=None,
                        help="数据根目录（含 brats/train/）")
    parser.add_argument("--out-dir",   type=str, default=None,
                        help="输出目录")
    parser.add_argument("--gpu",       type=int, default=None)
    parser.add_argument("--num-workers", type=int, default=None)
    parser.add_argument("--seed",      type=int, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # 基础 config（默认值）
    _script_dir  = Path(__file__).resolve().parent           # src/
    _project_dir = _script_dir.parent                        # MedAD-FailMap/

    cfg: dict = {
        "dataset":     "brats",
        "gpu":         0,
        "num_workers": 4,
        "seed":        42,
        # TODO: 数据未下载，见 datasets.json medianomaly_bench (status=todo)
        "data_root":   str(_project_dir / "data"),
        "out_dir":     str(_project_dir / "results"),
    }

    # 从 yaml config 覆盖
    if args.config:
        file_cfg = load_config(args.config)
        cfg.update({k: v for k, v in file_cfg.items() if v is not None})

    # 命令行再覆盖（优先级最高）
    if args.data_root   is not None: cfg["data_root"]    = args.data_root
    if args.out_dir     is not None: cfg["out_dir"]      = args.out_dir
    if args.gpu         is not None: cfg["gpu"]          = args.gpu
    if args.num_workers is not None: cfg["num_workers"]  = args.num_workers
    if args.seed        is not None: cfg["seed"]         = args.seed

    train(cfg)
