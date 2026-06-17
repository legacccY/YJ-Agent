"""C0 可靠性 × 可恢复性决策面评估脚本.

产出 results/c0_decision_surface.csv.

论文对应: §3.2 可靠性轴 (C0.1) + §3.3 可恢复性轴 (C0.2).

C0.1 可靠性轴:
  - 5 维单维隔离退化: blur / brightness / contrast / color_shift / completeness
  - 每维 5 档 severity (基于 data/degrade.py light/medium/heavy 三锚物理量纲等距插/外插)
  - 对 ITB-HQ 干净集 (results/itb_subsets.csv 中 subset==ITB-HQ 行) 施加单维退化
    → EfficientNet-B3 前向 → 诊断 AUC + ECE + bootstrap 2000 次 95% CI
  - 主指标: 诊断 AUC; ECE 仅作附指标 (避撞 BMVC ECE 主轴角度)

C0.2 可恢复性轴:
  - 对 C0.1 每个退化点, 再过 VisiEnhance Stage2 v5 增强 → 重算 AUC
  - 可恢复性 delta = AUC_enhanced - AUC_degraded (>0=救回, <0=帮倒忙)
  - bootstrap CI 以同一 bootstrap 样本计算 delta

CSV 列:
  axis, severity_level, severity_value, auc, auc_ci_lo, auc_ci_hi,
  ece, ece_ci_lo, ece_ci_hi, n,
  auc_enhanced, recoverability_delta, recoverability_ci_lo, recoverability_ci_hi

注意事项:
  - completeness 退化定义为视野截断 (crop_ratio), CenterCrop224 喂 B3.
    措辞: "partially recoverable", 非 "irreversible".
  - ECE 附而不主 (BMVC 已占逐维 ECE 视角, STORY 明文禁止 ECE 当主轴).
  - AUC 是主指标, 避撞 BMVC tab:perdeg.
  - 不运行训练, 只做退化 + 前向推理.
  - 不依赖 scipy.stats (Windows OMP 兼容), 全 numpy 实现 bootstrap.
  - CWD 必须是 project/ (D:/YJ-Agent/project/).

用法:
  python eval_c0_decision_surface.py [--n_max N] [--boot B] [--seed S]
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from omegaconf import OmegaConf
from torchvision import transforms
from tqdm import tqdm

# ---------------------------------------------------------------------------
# sys.path: 保证从 project/ 运行时能 import eval_stage2_compare 等
# ---------------------------------------------------------------------------
_PROJECT_DIR = Path(__file__).resolve().parent
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

from eval_stage2_compare import load_b3, load_visienhance, load_visiscore, CFG  # noqa

# ---------------------------------------------------------------------------
# 路径常量 (单一真源: DATA_INVENTORY.md + .portfolio/datasets.json)
# ---------------------------------------------------------------------------
ROOT = "D:/YJ-Agent"
LABELS    = f"{ROOT}/data/quality_labels_nocrop.csv"
SPLIT     = f"{ROOT}/data/isic_split.csv"
META      = f"{ROOT}/data/raw/isic2020/train-metadata.csv"
VISISCORE = f"{ROOT}/checkpoints/best_visiscore.pth"
B3_PATH   = f"{ROOT}/checkpoints/efficientnet_b3_isic.pth"
CKPT_V5   = f"{ROOT}/project/checkpoints/visienhance/stage2_planA_256_v5/best_visienhance.pth"
ITB_SUBSETS_CSV = f"{ROOT}/project/results/itb_subsets.csv"
OUT_CSV   = f"{ROOT}/project/results/c0_decision_surface.csv"

# 图像尺寸: degrade 在 256, B3 需 224 (CenterCrop)
IMG_SIZE = 256
CROP_SIZE = 224

_TT   = transforms.ToTensor()
_NORM = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])


# ---------------------------------------------------------------------------
# 5 档 severity 参数表
# 基于 data/degrade.py 三锚 (light/medium/heavy) 物理量纲等距插/外插:
#   S1 = 轻于 light (外插到 "很轻" 方向)
#   S2 = light 锚
#   S3 = medium 锚
#   S4 = heavy 锚
#   S5 = 重于 heavy (外插到 "极重" 方向)
#
# 插值步长 = (medium - light) / 1 取 S2-S3 间距, 再等距外插.
# 每维用代表性单值 (区间中点或确定值), 确保单调.
#
# blur:
#   light=0.8, medium=1.5, heavy=2.5
#   step_lo=(1.5-0.8)=0.7, step_hi=(2.5-1.5)=1.0, 用等距 [0.5,0.8,1.5,2.5,3.5]
#
# brightness (factor=区间中点):
#   light中点=(0.85+1.0)/2=0.925, medium=(0.65+0.85)/2=0.75, heavy=(0.40+0.64)/2=0.52
#   step=(0.925-0.75)=0.175  外插: S1=0.925+0.175=1.0(clip), S5=0.52-0.175=0.345
#   5档: [1.0, 0.925, 0.75, 0.52, 0.345]
#
# contrast (alpha, 来自 enhance_dataset._DEG_CFG 口径):
#   mild中点=(0.85+1.0)/2=0.925, moderate=(0.55+0.84)/2=0.695, severe=(0.30+0.54)/2=0.42
#   mild=S2, moderate=S3, severe=S4
#   step_lo=0.925-0.695=0.23  S1=0.925+0.23=1.0(clip不加), S5=0.42-0.23=0.19
#   5档: [1.0, 0.925, 0.695, 0.42, 0.19]
#   Note: contrast alpha<1 收缩对比度 (图偏灰), alpha>1 增强 (这里 <=1 单调减)
#
# color_shift (绝对偏移量对255的比例):
#   light=0.05, medium=0.12, heavy=0.22
#   step_lo=(0.12-0.05)=0.07, step_hi=(0.22-0.12)=0.10  使用等距 [0.02,0.05,0.12,0.22,0.34]
#
# completeness (crop_ratio 中点, 值越小截断越重):
#   light中点=(0.90+1.0)/2=0.95, medium=(0.75+0.89)/2=0.82, heavy=(0.55+0.74)/2=0.645
#   step_lo=0.95-0.82=0.13  S1=0.95+0.13=1.0(整图), S5=0.645-0.13=0.515
#   5档: [1.0, 0.95, 0.82, 0.645, 0.515]
# ---------------------------------------------------------------------------

# 每维5档显式常量 (不臆想, 严格从 degrade.py 三锚物理外插)
SEVERITY_GRID: dict[str, list[float]] = {
    # blur_sigma (越大越模糊)
    "blur":         [0.50, 0.80, 1.50, 2.50, 3.50],
    # brightness factor 乘子 (越小越暗)
    "brightness":   [1.00, 0.925, 0.75, 0.52, 0.345],
    # contrast alpha (越小对比度越低, 图越灰)
    "contrast":     [1.00, 0.925, 0.695, 0.42, 0.19],
    # color_shift 比例 (对255, 越大色温偏移越重)
    "color_shift":  [0.02, 0.05, 0.12, 0.22, 0.34],
    # completeness crop_ratio (越小视野截断越重, 1.0=无截断)
    "completeness": [1.00, 0.95, 0.82, 0.645, 0.515],
}

# 5档 label (对应 ImageNet-C severity 1-5 惯例)
SEVERITY_LABELS = [1, 2, 3, 4, 5]


# ---------------------------------------------------------------------------
# 单维退化函数 (确定性, seed 固定, 强制施加)
# ---------------------------------------------------------------------------

def degrade_single_axis(
    img: np.ndarray,
    axis: str,
    sev_val: float,
    rng: random.Random,
    target_size: int = IMG_SIZE,
) -> np.ndarray:
    """对 img (BGR uint8 HWC) 只施加 axis 指定的单维退化, 强制概率 1.0.

    completeness: 随机裁 crop_ratio 比例再 resize 回 target_size.
      - 当 sev_val == 1.0 时直接 resize 不裁 (S1 无截断基准).
    其余轴: 不改尺寸.
    """
    out = img.astype(np.float32)

    if axis == "blur":
        sigma = sev_val
        if sigma > 0:
            ksize = int(2 * np.ceil(3 * sigma) + 1)
            if ksize % 2 == 0:
                ksize += 1
            out = cv2.GaussianBlur(out, (ksize, ksize), sigma)

    elif axis == "brightness":
        factor = sev_val
        out = np.clip(out * factor, 0, 255)

    elif axis == "contrast":
        alpha = sev_val
        if alpha != 1.0:
            mean = out.mean(axis=(0, 1), keepdims=True)
            out = np.clip(alpha * (out - mean) + mean, 0, 255)

    elif axis == "color_shift":
        shift = sev_val * 255.0
        for c in range(3):
            delta = rng.uniform(-shift, shift)
            out[:, :, c] = np.clip(out[:, :, c] + delta, 0, 255)

    elif axis == "completeness":
        ratio = sev_val
        h, w = img.shape[:2]
        crop_h = int(h * ratio)
        crop_w = int(w * ratio)
        crop_h = max(crop_h, 1)
        crop_w = max(crop_w, 1)
        max_y = max(h - crop_h, 0)
        max_x = max(w - crop_w, 0)
        y = rng.randint(0, max_y) if max_y > 0 else 0
        x = rng.randint(0, max_x) if max_x > 0 else 0
        out = img[y: y + crop_h, x: x + crop_w].astype(np.float32)
        out = cv2.resize(out, (target_size, target_size), interpolation=cv2.INTER_LINEAR)
    else:
        raise ValueError(f"未知 axis: {axis!r}")

    return out.astype(np.uint8)


# ---------------------------------------------------------------------------
# 纯 numpy ECE (避免 scipy, Windows OMP 兼容)
# ---------------------------------------------------------------------------

def compute_ece(probs: np.ndarray, labels: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error, equal-width bins [0,1]."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(probs)
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (probs >= lo) & (probs < hi)
        if mask.sum() == 0:
            continue
        avg_conf = probs[mask].mean()
        avg_acc  = labels[mask].mean()
        ece += mask.sum() / n * abs(avg_conf - avg_acc)
    return float(ece)


# ---------------------------------------------------------------------------
# AUC (numpy, 无 sklearn 依赖也可跑; 若 sklearn 可用更快)
# ---------------------------------------------------------------------------

def compute_auc(labels: np.ndarray, scores: np.ndarray) -> float:
    try:
        from sklearn.metrics import roc_auc_score
        return float(roc_auc_score(labels, scores))
    except Exception:
        # 纯 numpy 梯形 AUC (fallback)
        order = np.argsort(-scores)
        labels_sorted = labels[order]
        tps = np.cumsum(labels_sorted)
        fps = np.cumsum(1 - labels_sorted)
        tp_rate = tps / max(tps[-1], 1e-9)
        fp_rate = fps / max(fps[-1], 1e-9)
        return float(np.trapz(tp_rate, fp_rate))


# ---------------------------------------------------------------------------
# Bootstrap CI (2000 次, 纯 numpy, Windows OMP 安全)
# ---------------------------------------------------------------------------

def bootstrap_auc_ece(
    labels: np.ndarray,
    scores_deg: np.ndarray,
    scores_enh: np.ndarray | None,
    n_boot: int = 2000,
    seed: int = 0,
) -> dict:
    """同一 bootstrap 样本同时算 degraded / enhanced AUC 和 ECE.

    返回字典含:
      auc, auc_ci_lo, auc_ci_hi,
      ece, ece_ci_lo, ece_ci_hi,
      auc_enhanced (若 scores_enh 非 None),
      recoverability_delta, recoverability_ci_lo, recoverability_ci_hi,
      n
    """
    rng_bs = np.random.default_rng(seed)
    n = len(labels)

    auc_boot, ece_boot = [], []
    auc_enh_boot, delta_boot = [], []

    for _ in range(n_boot):
        idx = rng_bs.integers(0, n, size=n)
        lb = labels[idx]
        sd = scores_deg[idx]
        if lb.sum() == 0 or lb.sum() == n:
            continue  # skip degenerate samples
        auc_boot.append(compute_auc(lb, sd))
        ece_boot.append(compute_ece(sd, lb))
        if scores_enh is not None:
            se = scores_enh[idx]
            a_e = compute_auc(lb, se)
            auc_enh_boot.append(a_e)
            delta_boot.append(a_e - auc_boot[-1])

    auc_arr  = np.array(auc_boot)
    ece_arr  = np.array(ece_boot)

    result = {
        "auc":        compute_auc(labels, scores_deg),
        "auc_ci_lo":  float(np.percentile(auc_arr, 2.5)),
        "auc_ci_hi":  float(np.percentile(auc_arr, 97.5)),
        "ece":        compute_ece(scores_deg, labels),
        "ece_ci_lo":  float(np.percentile(ece_arr, 2.5)),
        "ece_ci_hi":  float(np.percentile(ece_arr, 97.5)),
        "n":          n,
    }

    if scores_enh is not None and auc_enh_boot:
        enh_arr   = np.array(auc_enh_boot)
        delta_arr = np.array(delta_boot)
        result.update({
            "auc_enhanced":         compute_auc(labels, scores_enh),
            "recoverability_delta": float(np.mean(delta_arr)),
            "recoverability_ci_lo": float(np.percentile(delta_arr, 2.5)),
            "recoverability_ci_hi": float(np.percentile(delta_arr, 97.5)),
        })
    else:
        result.update({
            "auc_enhanced":         float("nan"),
            "recoverability_delta": float("nan"),
            "recoverability_ci_lo": float("nan"),
            "recoverability_ci_hi": float("nan"),
        })

    return result


# ---------------------------------------------------------------------------
# 数据加载: ITB-HQ 干净集
# ---------------------------------------------------------------------------

def load_itb_hq_df(n_max: int | None = None, seed: int = 42) -> pd.DataFrame:
    """从 itb_subsets.csv 取 ITB-HQ 行, 合并 meta target.

    ITB-HQ 定义: subset==ITB-HQ, 来源是 ISIC2020 原图 (高质).
    需要 target 列 (melanoma 0/1).
    """
    itb = pd.read_csv(ITB_SUBSETS_CSV)
    hq  = itb[itb["subset"] == "ITB-HQ"].copy()

    # 优先用 itb_subsets.csv 自带 target; 若缺则 merge meta
    if "target" not in hq.columns or hq["target"].isna().all():
        meta = pd.read_csv(META)[["isic_id", "target"]]
        meta["isic_id"] = meta["isic_id"].astype(str)
        hq["isic_id"]   = hq["isic_id"].astype(str)
        hq = hq.merge(meta, on="isic_id", how="left")
        hq["target"] = hq["target"].fillna(0).astype(int)

    # 用 image_path 列 (itb_subsets.csv 有此列, 路径指向 paired_dataset/heavy 目录)
    # ITB-HQ 应指向原图. 检查 image_path 是否存在; 若不存在尝试从 LABELS 补
    if "image_path" in hq.columns:
        hq = hq[hq["image_path"].apply(lambda p: Path(str(p)).exists())]
    else:
        # fallback: 从 quality_labels_nocrop.csv 匹配
        lbl = pd.read_csv(LABELS)
        lbl["isic_id"] = lbl["original_path"].apply(lambda p: Path(p).stem)
        hq = hq.merge(lbl[["isic_id", "original_path"]], on="isic_id", how="inner")
        hq["image_path"] = hq["original_path"]
        hq = hq[hq["image_path"].apply(lambda p: Path(str(p)).exists())]

    hq = hq.reset_index(drop=True)

    if n_max and len(hq) > n_max:
        hq = hq.sample(n_max, random_state=seed).reset_index(drop=True)

    return hq


# ---------------------------------------------------------------------------
# B3 推理: batch 输入 tensor (N,3,256,256), 返回 mel prob np array
# ---------------------------------------------------------------------------

@torch.no_grad()
def b3_forward(b3_model, imgs_tensor: torch.Tensor, device) -> np.ndarray:
    """imgs_tensor: (N,3,256,256) float [0,1], 输出 mel softmax prob (N,)."""
    x = imgs_tensor.to(device)
    x = F.interpolate(x, size=CROP_SIZE, mode="bilinear", align_corners=False)
    x = _NORM(x)
    logits = b3_model(x)
    return torch.softmax(logits, dim=-1)[:, 1].cpu().numpy()


@torch.no_grad()
def enhance_forward(enh_model, visiscore_model, imgs_tensor: torch.Tensor, device) -> torch.Tensor:
    """imgs_tensor: (N,3,256,256) float [0,1], 输出增强后 tensor (N,3,256,256).

    口径与 eval_e2_perdim.py / eval_e5_salvage.py 一致:
      x_low(256) -> visiscore(x_low) -> q[B,5] -> enh_model(x_low, q).

    cuDNN 兼容说明:
      ConvTranspose2d(kernel=2, stride=2) 在 Windows RTX4070 某些 cuDNN 版本
      (cuDNN 8.x IMPLICIT_GEMM) 触发 "GET was unable to find an engine" 报错.
      修法: 临时禁用 cuDNN (cudnn.enabled=False), 强制走 PyTorch ATen fallback
      实现 conv_transpose2d, 结果数值正确, 速度稍慢但 eval 可接受.
      visiscore / b3 的普通 Conv2d 不受影响 (单独调用时 cuDNN 正常).
    """
    x = imgs_tensor.to(device)
    # visiscore 接受 256x256 raw 输入 (训练口径, 参见 eval_e5_salvage.py L90 q_raw = vs(x_low))
    q = visiscore_model(x)
    # 临时关闭 cuDNN, 绕过 ConvTranspose2d engine 选择失败
    with torch.backends.cudnn.flags(enabled=False):
        out = enh_model(x, q)
    return out.cpu()


# ---------------------------------------------------------------------------
# 主评估循环: 单轴单档
# ---------------------------------------------------------------------------

@torch.no_grad()
def eval_axis_severity(
    axis: str,
    sev_val: float,
    df: pd.DataFrame,
    b3_model,
    enh_model,
    visiscore_model,
    device,
    batch_size: int = 16,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """返回 (labels, scores_ref, scores_deg, scores_enh).

    - labels: (N,) 0/1 melanoma
    - scores_ref: B3 在干净原图上的 mel prob
    - scores_deg: B3 在退化图上的 mel prob
    - scores_enh: B3 在增强后退化图上的 mel prob
    """
    labels_list, scores_ref_list, scores_deg_list, scores_enh_list = [], [], [], []

    for start in tqdm(
        range(0, len(df), batch_size),
        desc=f"{axis} S={sev_val:.3f}",
        ncols=80,
        leave=False,
    ):
        rows = df.iloc[start: start + batch_size]
        refs_tensor, degs_tensor = [], []
        valid_targets = []

        for _, row in rows.iterrows():
            img_path = str(row.get("image_path", row.get("original_path", "")))
            img = cv2.imread(img_path)
            if img is None:
                continue
            img = cv2.resize(img, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_AREA)

            # 单维退化 (seed = 固定值确保可复现)
            rng_local = random.Random(42 + int(row.name))
            deg = degrade_single_axis(img, axis, sev_val, rng_local, target_size=IMG_SIZE)

            refs_tensor.append(_TT(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
            degs_tensor.append(_TT(cv2.cvtColor(deg, cv2.COLOR_BGR2RGB)))
            valid_targets.append(int(row["target"]))

        if not refs_tensor:
            continue

        x_ref = torch.stack(refs_tensor)
        x_deg = torch.stack(degs_tensor)

        p_ref = b3_forward(b3_model, x_ref, device)
        p_deg = b3_forward(b3_model, x_deg, device)

        # 增强路径 (C0.2)
        x_enh = enhance_forward(enh_model, visiscore_model, x_deg, device)
        p_enh = b3_forward(b3_model, x_enh, device)

        labels_list.extend(valid_targets)
        scores_ref_list.extend(p_ref.tolist())
        scores_deg_list.extend(p_deg.tolist())
        scores_enh_list.extend(p_enh.tolist())

    return (
        np.array(labels_list),
        np.array(scores_ref_list),
        np.array(scores_deg_list),
        np.array(scores_enh_list),
    )


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

def main(n_max: int = 360, n_boot: int = 2000, seed: int = 42, batch_size: int = 16):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[C0] device={device}")
    # eval 阶段不需要 benchmark 加速; enhance_forward 内部对 ConvTranspose2d 临时
    # 禁用 cuDNN (见 enhance_forward 注释).
    torch.backends.cudnn.benchmark = False

    print("[C0] 加载模型...")
    visiscore_model = load_visiscore(VISISCORE, device)
    b3_model        = load_b3(B3_PATH, device)
    enh_model       = load_visienhance(CFG, CKPT_V5, device)

    print("[C0] 加载 ITB-HQ...")
    df = load_itb_hq_df(n_max=n_max, seed=seed)
    print(f"[C0] ITB-HQ n={len(df)}, pos(mel)={int(df['target'].sum())}")

    if len(df) == 0:
        raise RuntimeError("ITB-HQ 数据集为空, 检查 itb_subsets.csv 路径和 image_path 列.")

    records = []
    axes = list(SEVERITY_GRID.keys())

    for axis in axes:
        sev_values = SEVERITY_GRID[axis]
        for sev_idx, sev_val in enumerate(sev_values):
            sev_label = SEVERITY_LABELS[sev_idx]
            print(f"\n[C0] axis={axis}  S{sev_label}={sev_val:.3f}")

            labels, scores_ref, scores_deg, scores_enh = eval_axis_severity(
                axis, sev_val, df,
                b3_model, enh_model, visiscore_model,
                device, batch_size=batch_size,
            )

            if len(labels) < 10 or labels.sum() == 0:
                print(f"  [WARN] 跳过: n={len(labels)}, pos={int(labels.sum())}")
                continue

            stats = bootstrap_auc_ece(
                labels, scores_deg, scores_enh,
                n_boot=n_boot, seed=seed + sev_idx,
            )

            rec = {
                "axis":                   axis,
                "severity_level":         sev_label,
                "severity_value":         sev_val,
                **stats,
            }
            records.append(rec)

            print(
                f"  AUC_deg={stats['auc']:.4f} [{stats['auc_ci_lo']:.4f},{stats['auc_ci_hi']:.4f}]"
                f"  ECE={stats['ece']:.4f}"
                f"  AUC_enh={stats['auc_enhanced']:.4f}"
                f"  delta={stats['recoverability_delta']:.4f}"
                f"  n={stats['n']}"
            )

    # ---------- 保存 ----------
    out_cols = [
        "axis", "severity_level", "severity_value",
        "auc", "auc_ci_lo", "auc_ci_hi",
        "ece", "ece_ci_lo", "ece_ci_hi",
        "n",
        "auc_enhanced",
        "recoverability_delta", "recoverability_ci_lo", "recoverability_ci_hi",
    ]
    out_path = Path(OUT_CSV)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records)[out_cols].to_csv(out_path, index=False)
    print(f"\n[C0] saved -> {out_path}")
    print(pd.DataFrame(records)[["axis", "severity_level", "auc", "recoverability_delta"]].to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="C0 决策面评估")
    parser.add_argument("--n_max",      type=int, default=360,  help="最大评估样本数 (ITB-HQ=360)")
    parser.add_argument("--n_boot",     type=int, default=2000, help="Bootstrap 次数")
    parser.add_argument("--seed",       type=int, default=42,   help="随机种子")
    parser.add_argument("--batch_size", type=int, default=16,   help="每批处理图像数")
    args = parser.parse_args()

    main(n_max=args.n_max, n_boot=args.n_boot, seed=args.seed, batch_size=args.batch_size)
