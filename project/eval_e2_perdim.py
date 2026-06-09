"""E2 单维度降质 PSNR/SSIM 评估.

对 test split 原图, 逐维度隔离施加降质(brightness/color_shift/contrast/blur),
VisiEnhance v5 增强后在 256×256 全图计算 per-image PSNR/SSIM(skimage),
同时记录降质图 vs ref 的 PSNR 作 baseline.

验收阈值: brightness/color_shift/contrast PSNR_enh > 35 dB, blur > 28 dB.

cwd 必须是 project/.
"""

import random
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from torchvision import transforms
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_stage2_compare import load_visienhance, load_visiscore, CFG

# ---------------------------------------------------------------------------
# 路径常量 (本地默认; run_e2_hpc.py 覆盖为 GPFS 路径)
# ---------------------------------------------------------------------------
ROOT      = "D:/YJ-Agent"
LABELS    = f"{ROOT}/data/quality_labels_nocrop.csv"
SPLIT     = f"{ROOT}/data/isic_split.csv"
META      = f"{ROOT}/data/raw/isic2020/train-metadata.csv"
VISISCORE = f"{ROOT}/checkpoints/best_visiscore.pth"
B3        = f"{ROOT}/checkpoints/efficientnet_b3_isic.pth"
CKPT_V5   = f"{ROOT}/project/checkpoints/visienhance/stage2_planA_256_v5/best_visienhance.pth"

IMG    = 256
N_MAX  = 2000
_TT    = transforms.ToTensor()

# ---------------------------------------------------------------------------
# 验收阈值
# ---------------------------------------------------------------------------
THRESHOLDS = {
    "brightness":   35.0,
    "color_shift":  35.0,
    "contrast":     35.0,
    "blur":         28.0,
}

# ---------------------------------------------------------------------------
# moderate 降质参数 (直接抄自 enhance_dataset._DEG_CFG)
# ---------------------------------------------------------------------------
_MOD = {
    "blur_sigma":   (1.2, 2.5),
    "brightness":   (0.55, 0.84),
    "contrast":     (0.55, 0.84),
    "color_shift":  0.10,          # 乘以 255 得最大偏移量
}


def _degrade_single_axis(img: np.ndarray, axis: str, rng: random.Random) -> np.ndarray:
    """对 img(BGR uint8, HWC) 只施加 axis 指定的那一种 moderate 降质.

    概率强制 1.0 (必施加). 绝不触碰 enhance_dataset._DEG_PROBS.
    参数区间取 _DEG_CFG["moderate"].
    """
    out = img.astype(np.float32)

    if axis == "blur":
        sigma = rng.uniform(*_MOD["blur_sigma"])
        ksize = int(2 * np.ceil(3 * sigma) + 1)
        out = cv2.GaussianBlur(out, (ksize, ksize), sigma)

    elif axis == "brightness":
        out = np.clip(out * rng.uniform(*_MOD["brightness"]), 0, 255)

    elif axis == "contrast":
        alpha = rng.uniform(*_MOD["contrast"])
        mean  = out.mean(axis=(0, 1), keepdims=True)
        out   = np.clip(alpha * (out - mean) + mean, 0, 255)

    elif axis == "color_shift":
        shift = _MOD["color_shift"] * 255
        for c in range(3):
            out[:, :, c] = np.clip(out[:, :, c] + rng.uniform(-shift, shift), 0, 255)

    else:
        raise ValueError(f"未知 axis: {axis!r}. 合法值: blur/brightness/contrast/color_shift")

    return out.astype(np.uint8)


def build_df() -> pd.DataFrame:
    """返回 test split 去重原图 DataFrame, 只保留文件存在的行."""
    lbl = pd.read_csv(LABELS)
    sp  = pd.read_csv(SPLIT)
    test_ids = set(sp.loc[sp["split"] == "test", "isic_id"].astype(str))

    # isic_id 列: 从 original_path stem 提取 (与 eval_stage2_compare 一致)
    lbl["isic_id"] = lbl["original_path"].apply(lambda p: Path(p).stem)
    df = lbl[lbl["isic_id"].isin(test_ids)].drop_duplicates("original_path")
    df = df[df["original_path"].apply(lambda p: Path(p).exists())]
    df = df.reset_index(drop=True)

    if N_MAX and len(df) > N_MAX:
        df = df.sample(N_MAX, random_state=7).reset_index(drop=True)

    return df


@torch.no_grad()
def eval_axis(axis: str, model, visiscore, df: pd.DataFrame, device) -> dict:
    """单维度评估, 返回 {psnr_deg, psnr_enh, ssim_enh, n}."""
    from skimage.metrics import peak_signal_noise_ratio, structural_similarity

    psnr_deg_list, psnr_enh_list, ssim_enh_list = [], [], []
    BATCH = 8

    for s in tqdm(range(0, len(df), BATCH), desc=axis, ncols=72):
        rows = df.iloc[s : s + BATCH]
        lows, refs = [], []

        for j, row in rows.iterrows():
            img = cv2.imread(str(row["original_path"]))
            if img is None:
                continue
            img = cv2.resize(img, (IMG, IMG), interpolation=cv2.INTER_AREA)
            deg = _degrade_single_axis(img, axis, random.Random(42 + j))

            # BGR -> RGB, ToTensor -> [0,1]
            refs.append(_TT(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
            lows.append(_TT(cv2.cvtColor(deg, cv2.COLOR_BGR2RGB)))

        if not lows:
            continue

        x_ref = torch.stack(refs)           # CPU, for metric
        x_low = torch.stack(lows).to(device)

        q     = visiscore(x_low)
        x_enh = model(x_low, q).cpu()

        for i in range(x_enh.shape[0]):
            ref_u8 = (x_ref[i].permute(1, 2, 0).numpy() * 255).astype(np.uint8)
            deg_u8 = (x_low[i].cpu().permute(1, 2, 0).numpy() * 255).astype(np.uint8)
            enh_u8 = (x_enh[i].permute(1, 2, 0).numpy() * 255).clip(0, 255).astype(np.uint8)

            psnr_deg_list.append(peak_signal_noise_ratio(ref_u8, deg_u8, data_range=255))
            psnr_enh_list.append(peak_signal_noise_ratio(ref_u8, enh_u8, data_range=255))
            ssim_enh_list.append(
                structural_similarity(ref_u8, enh_u8, channel_axis=2, data_range=255)
            )

    return {
        "psnr_deg": float(np.mean(psnr_deg_list)),
        "psnr_enh": float(np.mean(psnr_enh_list)),
        "ssim_enh": float(np.mean(ssim_enh_list)),
        "n":        len(psnr_enh_list),
    }


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device={device}")

    visiscore = load_visiscore(VISISCORE, device)
    model     = load_visienhance(CFG, CKPT_V5, device)

    df = build_df()
    print(f"test 原图数: {len(df)}")

    axes = ["brightness", "color_shift", "contrast", "blur"]
    rows = []
    for axis in axes:
        res = eval_axis(axis, model, visiscore, df, device)
        thresh = THRESHOLDS[axis]
        verdict = "PASS" if res["psnr_enh"] >= thresh else "FAIL"
        res["axis"]    = axis
        res["thresh"]  = thresh
        res["verdict"] = verdict
        rows.append(res)
        print(
            f"  [{verdict}] {axis:14s}  PSNR_deg={res['psnr_deg']:.2f}  "
            f"PSNR_enh={res['psnr_enh']:.2f} (≥{thresh})  "
            f"SSIM_enh={res['ssim_enh']:.4f}  n={res['n']}"
        )

    # ---- 汇总表 ----
    print("\n===== E2 Per-Dimension Summary =====")
    header = f"{'axis':<14} {'psnr_deg':>9} {'psnr_enh':>9} {'thresh':>7} {'ssim_enh':>9} {'n':>5}  verdict"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['axis']:<14} {r['psnr_deg']:>9.2f} {r['psnr_enh']:>9.2f} "
            f"{r['thresh']:>7.1f} {r['ssim_enh']:>9.4f} {r['n']:>5}  {r['verdict']}"
        )

    # ---- 保存 ----
    out_cols = ["axis", "psnr_deg", "psnr_enh", "ssim_enh", "n"]
    Path("results").mkdir(exist_ok=True)
    csv_path = "results/e2_perdim.csv"
    pd.DataFrame(rows)[out_cols].to_csv(csv_path, index=False)
    print(f"\nsaved -> {csv_path}")


if __name__ == "__main__":
    main()
