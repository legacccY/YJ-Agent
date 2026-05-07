"""q 向量区分度分析：验证 VisiScore-Net 输出符合阶段四 Q-VIB 接口要求。

检查项：
  1. 值域 [0,1]
  2. 5 个维度之间无高度共线（相关矩阵对角外 |r| < 0.9）
  3. q̄ 在 light vs heavy 退化样本间有显著分离（t-test p < 0.05）

Usage:
    python check_q_vector.py --config configs/visiscore.yaml \
        --ckpt D:/YJ-Agent/checkpoints/best_visiscore.pth \
        --n_per_level 500
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from omegaconf import OmegaConf
from scipy import stats
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from PIL import Image
from tqdm import tqdm

from models.visiscore import VisiScoreNet

STATE_PATH = Path("state.json")
DIM_NAMES = ["sharpness", "brightness", "completeness", "color_temp", "contrast"]


def write_state(phase: str, status: str, **kwargs):
    STATE_PATH.write_text(
        json.dumps({"phase": phase, "status": status, "ts": time.time(), **kwargs}),
        encoding="utf-8",
    )


class LevelSubset(Dataset):
    def __init__(self, csv_path: str, level: str, n: int, img_size: int = 224):
        df = pd.read_csv(csv_path)
        df = df[df["level"] == level].sample(n=min(n, len(df)), random_state=42)
        self.paths = df["degraded_path"].tolist()
        self.tfm = transforms.Compose([
            transforms.Resize((img_size, img_size)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, idx):
        img = Image.open(self.paths[idx]).convert("RGB")
        return self.tfm(img)


def infer(model, dataset, device, batch_size=64) -> np.ndarray:
    loader = DataLoader(
        dataset, batch_size=batch_size, shuffle=False,
        num_workers=2, multiprocessing_context="spawn",
    )
    preds = []
    model.eval()
    with torch.no_grad():
        for batch in tqdm(loader, desc=f"  infer({len(dataset)} imgs)", leave=False):
            with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
                q = model(batch.to(device))
            preds.append(q.cpu().float().numpy())
    return np.concatenate(preds, axis=0)


def check_value_range(q: np.ndarray) -> dict:
    return {
        "min": float(q.min()),
        "max": float(q.max()),
        "pass": bool(q.min() >= 0.0 and q.max() <= 1.0),
    }


def check_collinearity(q: np.ndarray) -> dict:
    corr = np.corrcoef(q.T)
    off_diag = corr[np.triu_indices(5, k=1)]
    max_r = float(np.abs(off_diag).max())
    return {
        "corr_matrix": corr.tolist(),
        "max_off_diag_abs_r": max_r,
        "pass": bool(max_r < 0.9),
    }


def check_separation(q_light: np.ndarray, q_heavy: np.ndarray) -> dict:
    qbar_light = q_light.mean(axis=1)
    qbar_heavy = q_heavy.mean(axis=1)
    t_stat, p_val = stats.ttest_ind(qbar_light, qbar_heavy, alternative="greater")
    return {
        "qbar_light_mean": float(qbar_light.mean()),
        "qbar_light_std": float(qbar_light.std()),
        "qbar_heavy_mean": float(qbar_heavy.mean()),
        "qbar_heavy_std": float(qbar_heavy.std()),
        "t_stat": float(t_stat),
        "p_value": float(p_val),
        "pass": bool(p_val < 0.05 and qbar_light.mean() > qbar_heavy.mean()),
    }


def write_report(out_path: Path, vr: dict, col: dict, sep: dict):
    corr = np.array(col["corr_matrix"])
    header = " | ".join([""] + DIM_NAMES)
    sep_line = "|" + "------|" * (len(DIM_NAMES) + 1)
    rows = []
    for i, name in enumerate(DIM_NAMES):
        row = f"| {name} | " + " | ".join(f"{corr[i, j]:.3f}" for j in range(5)) + " |"
        rows.append(row)

    lines = [
        "",
        "## q 向量区分度分析",
        "",
        "### 1. 值域检查",
        "",
        f"- min: {vr['min']:.4f}  max: {vr['max']:.4f}  {'✅ 在 [0,1] 内' if vr['pass'] else '❌ 超出值域'}",
        "",
        "### 2. 维度共线性（Pearson r 矩阵）",
        "",
        f"| {header} |",
        sep_line,
    ] + rows + [
        "",
        f"- 非对角最大 |r|：{col['max_off_diag_abs_r']:.3f}  {'✅ < 0.9，区分度合格' if col['pass'] else '❌ ≥ 0.9，存在高度共线'}",
        "",
        "### 3. q̄ 退化分离度",
        "",
        "| 组别 | q̄ 均值 | q̄ 标准差 |",
        "|------|--------|---------|",
        f"| light 退化 | {sep['qbar_light_mean']:.3f} | {sep['qbar_light_std']:.3f} |",
        f"| heavy 退化 | {sep['qbar_heavy_mean']:.3f} | {sep['qbar_heavy_std']:.3f} |",
        "",
        f"- t = {sep['t_stat']:.2f}, p = {sep['p_value']:.2e}  {'✅ light 显著高于 heavy' if sep['pass'] else '❌ 未通过显著性检验'}",
        "",
        "### 总结",
        "",
    ]
    all_pass = vr["pass"] and col["pass"] and sep["pass"]
    lines.append("**三项全部通过 ✅ — q 向量满足阶段四 Q-VIB 接口要求**" if all_pass
                 else "⚠️ 部分检查未通过，见上方详情")

    report_path = Path("results/eval_report_visiscore.md")
    existing = report_path.read_text(encoding="utf-8")
    # 若已有该节则替换，否则追加
    marker = "\n## q 向量区分度分析"
    if marker in existing:
        existing = existing[:existing.index(marker)]
    report_path.write_text(existing + "\n".join(lines), encoding="utf-8")
    print(f"报告已更新：{report_path}")

    # 同时输出独立分析文件
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"分析文件：{out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/visiscore.yaml")
    parser.add_argument("--ckpt", default="D:/YJ-Agent/checkpoints/best_visiscore.pth")
    parser.add_argument("--n_per_level", type=int, default=500)
    args = parser.parse_args()

    write_state("init", "running")
    cfg = OmegaConf.load(args.config)
    device = torch.device("cuda" if cfg.device.cuda and torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    model = VisiScoreNet(
        backbone=cfg.model.backbone, pretrained=False,
        num_dims=cfg.model.num_quality_dims,
    ).to(device)
    ckpt = torch.load(args.ckpt, map_location=device)
    model.load_state_dict(ckpt["model"])
    print(f"Loaded: {args.ckpt} (epoch {ckpt['epoch']+1})")

    write_state("infer", "running", level="light")
    print(f"\n[1/2] 推理 light 退化样本（n={args.n_per_level}）")
    ds_light = LevelSubset(cfg.data.labels_csv, "light", args.n_per_level)
    q_light = infer(model, ds_light, device)

    write_state("infer", "running", level="heavy")
    print(f"[2/2] 推理 heavy 退化样本（n={args.n_per_level}）")
    ds_heavy = LevelSubset(cfg.data.labels_csv, "heavy", args.n_per_level)
    q_heavy = infer(model, ds_heavy, device)

    q_all = np.concatenate([q_light, q_heavy], axis=0)

    print("\n=== Check 1: value range ===")
    vr = check_value_range(q_all)
    print(f"  min={vr['min']:.4f}  max={vr['max']:.4f}  {'PASS' if vr['pass'] else 'FAIL'}")

    print("\n=== Check 2: collinearity ===")
    col = check_collinearity(q_all)
    print(f"  max off-diag |r| = {col['max_off_diag_abs_r']:.3f}  {'PASS' if col['pass'] else 'FAIL'}")

    print("\n=== Check 3: q_bar separation ===")
    sep = check_separation(q_light, q_heavy)
    print(f"  light q_bar={sep['qbar_light_mean']:.3f}  heavy q_bar={sep['qbar_heavy_mean']:.3f}")
    print(f"  t={sep['t_stat']:.2f}  p={sep['p_value']:.2e}  {'PASS' if sep['pass'] else 'FAIL'}")

    out_path = Path("results/q_vector_analysis.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_report(out_path, vr, col, sep)

    all_pass = vr["pass"] and col["pass"] and sep["pass"]
    write_state("done", "success" if all_pass else "failed",
                value_range=vr["pass"], collinearity=col["pass"], separation=sep["pass"])
    if not all_pass:
        sys.exit(1)
    print("\n[DONE] All checks passed.")


if __name__ == "__main__":
    main()
