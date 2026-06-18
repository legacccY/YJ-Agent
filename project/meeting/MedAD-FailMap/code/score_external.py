"""
score_external.py — 外部数据集推理入口（AE/VAE/MemAE）
服务: MedAD-FailMap § M-3 (LGG held-out C4 复现)
lever: 给外部图像目录用已训练 ckpt 打 anomaly_score，输出与 anomaly_scores_brats_ae.csv 同 schema

用法:
    python code/score_external.py \
        --ckpt results/phase2/ae_s42/checkpoints/brats_ae_ep250.pt \
        --model ae \
        --img-dir data/lgg_heldout/tumor \
        --out-csv results/phase1/anomaly_scores_lgg_heldout_ae.csv

    # 可选: --device cpu（228 切片 CPU 分钟级，无须等 GPU）
    # 可选: --img-dir 传 tumor/ 或 normal/ 均可；也可传混合目录，--split 指定 split 列值
    # 可选: --split normal|tumor|lgg_heldout（默认 lgg_heldout）

输出 csv schema（与 anomaly_scores_brats_ae.csv 完全相同）:
    filename, split, anomaly_score, label

label 规则（按 --label-mode 控制）:
    --label-mode by-subdir: 子目录名 tumor→1, normal→0, 其余→-1（img-dir 含 tumor/ 或 normal/）
    --label-mode auto:      传入 img-dir 若名含 tumor→1, normal→0, 其余→-1
    --label-mode csv:       从 --label-csv 读（filename 列 + label 列）；找不到则 -1

约束:
  - 只 load+forward，绝不重训，不改任何 model 结构/权重
  - 复用 train_recon_ae.py 的 model 定义（import，不复制）
  - 预处理口径同 BraTS: resize 64x64, Grayscale, Normalize(0.5, 0.5)
  - Windows spawn 规范: num_workers>0 时 multiprocessing_context='spawn', pin_memory=False
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

# 复用 train_recon_ae.py 的 model 定义（import，不复制结构）
_CODE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_CODE_DIR))
from train_recon_ae import (
    AENet,
    VAENet,
    MemAENet,
    MemAELoss,
    OFFICIAL_HPARAMS,
)


# ============================================================
# Dataset
# ============================================================

class ExternalSliceDataset(Dataset):
    """
    读取 img-dir（扁平目录）里所有图像。
    支持 tumor/ normal/ 子目录（按 --label-mode 打 label）。
    不递归子目录；若需子目录分类见 label-mode 说明。
    """
    EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

    def __init__(self, img_paths, transform, label_map=None):
        """
        img_paths: list of Path
        label_map: dict {filename_stem_or_name -> int} or None
        """
        self.files = img_paths
        self.transform = transform
        self.label_map = label_map or {}

    def __len__(self):
        return len(self.files)

    def __getitem__(self, idx):
        p = self.files[idx]
        img = Image.open(p).convert("L")
        if self.transform:
            img = self.transform(img)
        label = self.label_map.get(p.name, self.label_map.get(p.stem, -1))
        return img, p.name, int(label)


def collect_img_paths(img_dir: Path):
    """收集 img-dir 下（含一层子目录）所有图像路径，返回 list of Path"""
    exts = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
    paths = []
    for p in sorted(img_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in exts:
            paths.append(p)
        elif p.is_dir():
            # 一层子目录（tumor/ normal/ 等）
            for q in sorted(p.iterdir()):
                if q.is_file() and q.suffix.lower() in exts:
                    paths.append(q)
    return paths


def build_label_map(img_paths, label_mode: str, label_csv: str = None):
    """
    label_mode:
        by-subdir  -- 父目录名 tumor->1, normal->0, 其余->-1
        auto       -- img 所在目录名含 tumor->1, normal->0, 其余->-1
        csv        -- 从 label_csv 读
    返回 dict {filename (str) -> int}
    """
    label_map = {}
    if label_mode == "csv" and label_csv:
        lp = Path(label_csv)
        if lp.exists():
            with open(lp, newline="") as f:
                for row in csv.DictReader(f):
                    label_map[row["filename"]] = int(row["label"])
        else:
            print(f"[score_external] warn: label-csv not found: {lp}, using label=-1")
        return label_map

    for p in img_paths:
        # by-subdir / auto: 看直接父目录名
        pdir = p.parent.name.lower()
        if "tumor" in pdir:
            lbl = 1
        elif "normal" in pdir or "healthy" in pdir or "negative" in pdir:
            lbl = 0
        else:
            lbl = -1
        label_map[p.name] = lbl
    return label_map


# ============================================================
# 推理
# ============================================================

@torch.no_grad()
def score_batch(model, imgs, model_type, memae_loss_fn):
    """返回 (B,) tensor anomaly scores"""
    if model_type == "vae":
        recon, _, _ = model(imgs)
        score_maps = (imgs - recon) ** 2
        return torch.mean(score_maps, dim=[1, 2, 3])
    elif model_type == "memae":
        net_out = model(imgs)
        return memae_loss_fn(imgs, net_out, anomaly_score=True)
    else:  # ae
        recon = model(imgs)
        score_maps = (imgs - recon) ** 2
        return torch.mean(score_maps, dim=[1, 2, 3])


def run_inference(args):
    device = torch.device(args.device)

    # ---- 加载 ckpt ----
    ckpt_path = Path(args.ckpt)
    if not ckpt_path.exists():
        raise FileNotFoundError(f"ckpt not found: {ckpt_path}")
    ckpt = torch.load(ckpt_path, map_location=device)
    # ckpt 格式: {'epoch':..., 'model_state':..., 'config':...}
    state_dict = ckpt.get("model_state", ckpt)  # 兼容裸 state_dict

    # ---- 构建模型（与 train_recon_ae.py 同口径超参）----
    model_type = args.model
    hp = OFFICIAL_HPARAMS.get("brats")  # 固定用 brats 超参（64², in_c=1, latent=16）
    in_c   = hp["in_c"]
    latent = hp["latent"]

    if model_type == "ae":
        model = AENet(in_c=in_c, base_c=16, latent=latent)
    elif model_type == "vae":
        model = VAENet(in_c=in_c, base_c=16, latent=latent)
    elif model_type == "memae":
        model = MemAENet(in_c=in_c, base_c=16, latent=latent,
                         mem_size=MemAENet.MEM_SIZE,
                         shrink_thres=MemAENet.SHRINK_THRES)
    else:
        raise ValueError(f"Unknown model: {model_type}")

    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    print(f"[score_external] ckpt loaded: {ckpt_path}")
    print(f"[score_external] model={model_type}, device={device}")

    memae_loss_fn = MemAELoss() if model_type == "memae" else None

    # ---- 预处理（与 BraTS 同口径）----
    transform = transforms.Compose([
        transforms.Resize((hp["input_size"], hp["input_size"])),
        transforms.Grayscale(num_output_channels=1),
        transforms.ToTensor(),
        transforms.Normalize(mean=hp["normalize_mean"], std=hp["normalize_std"]),
    ])

    # ---- 收集图像 ----
    img_dir = Path(args.img_dir)
    if not img_dir.exists():
        raise FileNotFoundError(f"img-dir not found: {img_dir}")

    img_paths = collect_img_paths(img_dir)
    if not img_paths:
        raise RuntimeError(f"No images found under {img_dir}")
    print(f"[score_external] found {len(img_paths)} images in {img_dir}")

    # ---- label map ----
    label_map = build_label_map(img_paths, args.label_mode,
                                 getattr(args, "label_csv", None))

    # ---- Dataset / DataLoader ----
    ds = ExternalSliceDataset(img_paths, transform, label_map)
    nw = args.num_workers
    loader = DataLoader(
        ds,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=nw,
        multiprocessing_context="spawn" if nw > 0 else None,
        pin_memory=False,
    )

    # ---- 推理 ----
    split_val = args.split
    rows = []
    n_done = 0
    for imgs, fnames, labels in loader:
        imgs = imgs.to(device)
        scores = score_batch(model, imgs, model_type, memae_loss_fn)
        for fname, sc, lbl in zip(fnames, scores.cpu().tolist(), labels.tolist()):
            rows.append({
                "filename":     fname,
                "split":        split_val,
                "anomaly_score": sc,
                "label":        lbl,
            })
        n_done += len(fnames)
        if n_done % 100 == 0 or n_done == len(ds):
            print(f"  scored {n_done}/{len(ds)}")

    # ---- 输出 csv（与 anomaly_scores_brats_ae.csv 同 schema）----
    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["filename", "split", "anomaly_score", "label"]
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    n_tumor  = sum(1 for r in rows if r["label"] == 1)
    n_normal = sum(1 for r in rows if r["label"] == 0)
    n_unk    = sum(1 for r in rows if r["label"] == -1)
    print(f"[score_external] done. {len(rows)} rows -> {out_csv}")
    print(f"  label=1 (tumor): {n_tumor}, label=0 (normal): {n_normal}, label=-1 (unk): {n_unk}")


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    _repo_root = Path(__file__).resolve().parent.parent
    _res = _repo_root / "results"

    parser = argparse.ArgumentParser(
        description="score_external.py — 外部数据集推理 (load ckpt -> anomaly_score csv)"
    )
    parser.add_argument("--ckpt", required=True,
                        help="训练好的 ckpt 路径（train_recon_ae.py 产出的 .pt 文件）")
    parser.add_argument("--model", choices=["ae", "vae", "memae"], required=True,
                        help="模型类型，须与 ckpt 匹配")
    parser.add_argument("--img-dir", required=True,
                        help="图像目录（扁平或含一层子目录 tumor/normal/）")
    parser.add_argument("--out-csv", required=True,
                        help="输出 csv 路径（schema: filename,split,anomaly_score,label）")
    parser.add_argument("--split", default="lgg_heldout",
                        help="输出 csv split 列的值（默认 lgg_heldout；可传 normal/tumor）")
    parser.add_argument("--label-mode", choices=["by-subdir", "auto", "csv"],
                        default="by-subdir",
                        help="label 打分模式：by-subdir=按父目录名（tumor->1,normal->0）；"
                             "auto=同 by-subdir；csv=从 --label-csv 读")
    parser.add_argument("--label-csv", default=None,
                        help="label-mode=csv 时的 label 映射 csv（含 filename,label 列）")
    parser.add_argument("--device", default="cpu",
                        help="推理设备，默认 cpu（228 切片分钟级，无须等 GPU）；"
                             "有 GPU 可传 cuda:0")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--num-workers", type=int, default=0,
                        help="DataLoader workers（CPU 推理建议 0，避免 spawn 开销）")
    args = parser.parse_args()
    run_inference(args)
