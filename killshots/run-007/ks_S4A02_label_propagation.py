"""
G5 Kill-shot: S4A-02 — Fitzpatrick17k 标签版本传播
服务: run-007 ACCV 选题流水线 G5 杀手锏（lever = G5 立项前证伪）

目标（纯 CPU 初筛阶段）：
  1. 读 Fitzpatrick17k CSV，获得两版 FST 标签：
       fitzpatrick_scale  (原版，-1=未标)
       fitzpatrick_centaur (独立第二版，-1=未标)
  2. 第三版 = ITA-relabeled：从图算 ITA 值映射到 FST I-VI，无图文件则跳过并标 TODO。
  3. CPU 初筛：各版本下 FST 组间 AUC gap（malignant vs rest，I-VI 按 3类：light/medium/dark）
     用 group 平均真实正例率（即 label-mean per group）作 zero-shot gap 代理。
     NOTE: 最终 AUC gap 需 GPU linear probe 特征（backbone TODO）；本脚本做 label-distribution gap
           即不同肤色组的 malignant 标签率差异（版本间对比），量化传播效应的上界和方向。
  4. 算三版间 group-rate gap 的版本间标准差（continuous），对照 MDE。

R9 判读约定（_G5_DESIGN.md §S4A-02）：
  PASS/MAIN : gap 版本间标准差 >= 0.03 且方向有结构 → 噪声传播实证 → 升 MAIN
  KILL      : 版本间标准差 < 0.03 且 CI 窄 → 结论稳健（不传播）→ 降平淡 audit
  GRAY      : FST 组样本少致 CI 宽 → FINDINGS 进 G6

  CPU 初筛：label-distribution gap 是 AUC gap 的必要条件（分布无差异 → AUC gap 必小）。
  若 label-distribution gap 版本间标准差 >= 0.03 → 传播效应天花板非零 → 进 GPU 验 AUC gap。
  若约 0 → 传播效应天然弱，可提前降权。

ITA 计算（CPU，需图文件）：
  ITA = atan2(L* - 50, b*) * 180 / pi  （Lab 色彩空间；Fitzpatrick 6类阈值见代码）
  若图目录不可达，第三版 ITA 步跳过，脚本输出两版对比 + 标 TODO。

数据: D:/YJ-Agent/data/raw/fitzpatrick17k/fitzpatrick17k.csv
      列: md5hash, fitzpatrick_scale, fitzpatrick_centaur, label,
          nine_partition_label, three_partition_label, qc, url, url_alphanum
      图: D:/YJ-Agent/data/raw/fitzpatrick17k/images/  (用于 ITA 计算)
      -1 = 未标注（过滤掉）

TODO: backbone 选择（linear probe 用）待 researcher 确认是否有本地 Fitzpatrick 特征缓存。
      若有缓存则零 GPU 即可得 AUC gap；若无则 GPU 特征提取 <1h。
TODO: 第三方清洗标签（Fitzpatrick17k-C）可得性待 researcher 确认；降级路径=ITA 当第三版。

输出: killshots/run-007/results/S4A02_label_propagation.csv
      + stdout 判读摘要
"""
import argparse
import sys
import os
import math
import numpy as np
import pandas as pd
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FITZ_CSV = REPO_ROOT / "data" / "raw" / "fitzpatrick17k" / "fitzpatrick17k.csv"
FITZ_IMG_DIR = REPO_ROOT / "data" / "raw" / "fitzpatrick17k" / "images"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

# ── 超参（来自 _G5_DESIGN.md §S4A-02 §2）────────────────────────────────────
N_BOOTSTRAP = 1000
RANDOM_STATE = 42
MDE_STD = 0.03    # gap 版本间标准差门槛
ITA_THRESHOLDS = {
    # ITA → FST 映射（Chardon 1991 convention，常用公式）
    # ITA > 55  → FST I (very light)
    # 41-55     → FST II
    # 28-41     → FST III
    # 10-28     → FST IV
    # -30-10    → FST V
    # < -30     → FST VI (very dark)
    # 来源：del Bino & Bernerd 2012 / Chardon 1991；TODO researcher 确认口径
    55: 1, 41: 2, 28: 3, 10: 4, -30: 5,
}

# FST → 3 大类分组（用于统计组间 gap，组内样本更多 CI 更窄）
FST_GROUP = {1: "light", 2: "light", 3: "medium", 4: "medium", 5: "dark", 6: "dark"}


def ita_to_fst(ita: float) -> int:
    """ITA 值映射到 FST I-VI（整数）。"""
    if ita > 55:
        return 1
    elif ita > 41:
        return 2
    elif ita > 28:
        return 3
    elif ita > 10:
        return 4
    elif ita > -30:
        return 5
    else:
        return 6


def compute_ita_from_image(img_path: Path) -> float:
    """
    从 RGB 图像算 ITA（Individual Typology Angle）。
    ITA = atan2(L* - 50, b*) * 180 / pi  （Lab 色彩空间，取图像中心 patch 均值）
    依赖：Pillow（纯 CPU），不依赖 cv2/scipy。
    返回 float 或 nan 若文件不存在/读取失败。
    """
    try:
        from PIL import Image
        img = Image.open(img_path).convert("RGB")
        # 取中心 64x64 patch 减少边缘/背景影响
        w, h = img.size
        cx, cy = w // 2, h // 2
        half = 32
        patch = img.crop((max(0, cx-half), max(0, cy-half),
                          min(w, cx+half), min(h, cy+half)))
        patch_lab = patch.convert("LAB")
        arr = np.array(patch_lab, dtype=np.float32)
        # PIL LAB: L in [0,255], a in [0,255], b in [0,255]，需标准化
        L = arr[:, :, 0] / 255.0 * 100.0       # [0, 100]
        b = (arr[:, :, 2] - 128.0) / 127.0 * 127.0  # approx [-127, 127]
        L_mean = float(np.mean(L))
        b_mean = float(np.mean(b))
        ita = math.degrees(math.atan2(L_mean - 50.0, b_mean))
        return ita
    except Exception:
        return float("nan")


def compute_group_malignant_rate(df_sub: pd.DataFrame,
                                 fst_col: str,
                                 target_col: str = "malignant") -> dict:
    """
    按 FST 3分组（light/medium/dark）计算 malignant 比率。
    返回 {group: rate} dict。
    """
    df_sub = df_sub.copy()
    df_sub["fst_group"] = df_sub[fst_col].map(FST_GROUP)
    rates = {}
    for grp in ["light", "medium", "dark"]:
        sub = df_sub[df_sub["fst_group"] == grp]
        if len(sub) == 0:
            rates[grp] = float("nan")
        else:
            rates[grp] = float(sub[target_col].mean())
    return rates


def group_gap(rates: dict) -> float:
    """max - min 的 malignant rate gap across groups（忽略 nan）。"""
    vals = [v for v in rates.values() if not math.isnan(v)]
    if len(vals) < 2:
        return float("nan")
    return float(max(vals) - min(vals))


def bootstrap_gap_ci(df_sub: pd.DataFrame, fst_col: str, target_col: str,
                     n_boot: int = N_BOOTSTRAP, alpha: float = 0.05,
                     rng: np.random.Generator = None) -> tuple:
    """
    Bootstrap CI for group gap（max-min malignant rate across light/medium/dark）。
    返回 (gap_point, ci_lo, ci_hi)。纯 numpy，不依赖 scipy。
    """
    if rng is None:
        rng = np.random.default_rng(RANDOM_STATE)
    n = len(df_sub)
    df_arr = df_sub[[fst_col, target_col]].values
    boot_gaps = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        sample = pd.DataFrame(df_arr[idx], columns=[fst_col, target_col])
        rates = compute_group_malignant_rate(sample, fst_col, target_col)
        g = group_gap(rates)
        if not math.isnan(g):
            boot_gaps.append(g)
    boot_gaps = np.array(boot_gaps)
    if len(boot_gaps) == 0:
        return float("nan"), float("nan"), float("nan")
    rates_pt = compute_group_malignant_rate(df_sub, fst_col, target_col)
    gap_pt = group_gap(rates_pt)
    ci_lo = float(np.percentile(boot_gaps, 100 * alpha / 2))
    ci_hi = float(np.percentile(boot_gaps, 100 * (1 - alpha / 2)))
    return gap_pt, ci_lo, ci_hi


def main(smoke: bool = False, max_ita_images: int = 500):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── 读数据 ──────────────────────────────────────────────────────────────
    if not FITZ_CSV.exists():
        print(f"[MISSING DATA] Fitzpatrick17k CSV not found at {FITZ_CSV}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(FITZ_CSV, encoding="utf-8")
    print(f"Loaded Fitzpatrick17k: {len(df)} rows, cols={list(df.columns)}")

    # ── 构造 malignant 二分标签 ───────────────────────────────────────────
    df["malignant"] = (df["three_partition_label"] == "malignant").astype(int)
    print(f"  malignant={df['malignant'].sum()}, total={len(df)}")

    # ── 版本 1 & 2：过滤掉 -1（未标注）────────────────────────────────────
    v1_valid = df[df["fitzpatrick_scale"] != -1].copy()
    v2_valid = df[df["fitzpatrick_centaur"] != -1].copy()

    print(f"\n  Version 1 (fitzpatrick_scale)  : n={len(v1_valid)} valid")
    print(f"  Version 2 (fitzpatrick_centaur): n={len(v2_valid)} valid")

    if smoke:
        v1_valid = v1_valid.iloc[:300].copy()
        v2_valid = v2_valid.iloc[:300].copy()
        print("[SMOKE] truncated to 300 rows per version")

    # ── 版本 3：ITA-relabeled ─────────────────────────────────────────────
    has_images = FITZ_IMG_DIR.exists()
    ita_computed = False
    v3_valid = None

    if has_images:
        print(f"\n  Computing ITA for images in {FITZ_IMG_DIR} ...")
        # 采样限制：全量计算可能慢；smoke 或 max_ita_images 限制
        df_ita = df.copy()
        if smoke:
            df_ita = df_ita.iloc[:100].copy()
        elif max_ita_images > 0:
            df_ita = df_ita.sample(n=min(max_ita_images, len(df_ita)),
                                   random_state=RANDOM_STATE).copy()

        # 构造图像路径：Fitzpatrick17k 图像以 md5hash 命名
        def find_image(md5: str) -> Path:
            for ext in [".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"]:
                p = FITZ_IMG_DIR / f"{md5}{ext}"
                if p.exists():
                    return p
            return None

        ita_values = []
        found_count = 0
        for _, row in df_ita.iterrows():
            img_path = find_image(str(row["md5hash"]))
            if img_path is not None:
                ita = compute_ita_from_image(img_path)
                found_count += 1
            else:
                ita = float("nan")
            ita_values.append(ita)
        df_ita["ita"] = ita_values

        print(f"    Found {found_count}/{len(df_ita)} images; ITA computed for {(~pd.isna(df_ita['ita'])).sum()}")

        if found_count > 10:
            df_ita["fst_v3"] = df_ita["ita"].apply(
                lambda x: ita_to_fst(x) if not math.isnan(x) else -1)
            v3_valid = df_ita[df_ita["fst_v3"] != -1].copy()
            v3_valid = v3_valid.rename(columns={"fst_v3": "fitzpatrick_v3"})
            print(f"  Version 3 (ITA-relabeled): n={len(v3_valid)} valid")
            ita_computed = True
        else:
            print("  [TODO] 找到图像文件 <10 张，ITA 第三版跳过。"
                  "请确认图像目录结构（md5hash.jpg/png 命名）或 researcher 确认图像路径约定。")
    else:
        print(f"\n  [TODO] 图像目录不存在: {FITZ_IMG_DIR}")
        print("  第三版 ITA-relabeled 无法计算，跳过。")
        print("  仅输出版本 1 vs 版本 2 对比。若需三版对比，请确认图像路径。")

    # ── 各版本 FST 组间 gap ────────────────────────────────────────────────
    rng = np.random.default_rng(RANDOM_STATE)
    print("\n" + "=" * 60)
    print("S4A-02 RESULTS — Fitzpatrick17k Label Propagation")
    print("=" * 60)

    results = []

    # Version 1
    rates_v1 = compute_group_malignant_rate(v1_valid, "fitzpatrick_scale", "malignant")
    gap_v1, ci_lo_v1, ci_hi_v1 = bootstrap_gap_ci(
        v1_valid, "fitzpatrick_scale", "malignant", rng=np.random.default_rng(RANDOM_STATE))
    print(f"\n  Version 1 (fitzpatrick_scale):")
    print(f"    Group rates: {', '.join(f'{k}={v:.4f}' for k,v in rates_v1.items())}")
    print(f"    Gap (max-min) = {gap_v1:.4f}  95%CI=[{ci_lo_v1:.4f}, {ci_hi_v1:.4f}]")
    results.append({"version": "v1_scale", "n": len(v1_valid),
                    "gap": gap_v1, "ci_lo": ci_lo_v1, "ci_hi": ci_hi_v1,
                    **{f"rate_{k}": v for k, v in rates_v1.items()}})

    # Version 2
    rates_v2 = compute_group_malignant_rate(v2_valid, "fitzpatrick_centaur", "malignant")
    gap_v2, ci_lo_v2, ci_hi_v2 = bootstrap_gap_ci(
        v2_valid, "fitzpatrick_centaur", "malignant", rng=np.random.default_rng(RANDOM_STATE + 1))
    print(f"\n  Version 2 (fitzpatrick_centaur):")
    print(f"    Group rates: {', '.join(f'{k}={v:.4f}' for k,v in rates_v2.items())}")
    print(f"    Gap (max-min) = {gap_v2:.4f}  95%CI=[{ci_lo_v2:.4f}, {ci_hi_v2:.4f}]")
    results.append({"version": "v2_centaur", "n": len(v2_valid),
                    "gap": gap_v2, "ci_lo": ci_lo_v2, "ci_hi": ci_hi_v2,
                    **{f"rate_{k}": v for k, v in rates_v2.items()}})

    # Version 3（如果算出来了）
    if ita_computed and v3_valid is not None and len(v3_valid) > 50:
        rates_v3 = compute_group_malignant_rate(v3_valid, "fitzpatrick_v3", "malignant")
        gap_v3, ci_lo_v3, ci_hi_v3 = bootstrap_gap_ci(
            v3_valid, "fitzpatrick_v3", "malignant",
            rng=np.random.default_rng(RANDOM_STATE + 2))
        print(f"\n  Version 3 (ITA-relabeled):")
        print(f"    Group rates: {', '.join(f'{k}={v:.4f}' for k,v in rates_v3.items())}")
        print(f"    Gap (max-min) = {gap_v3:.4f}  95%CI=[{ci_lo_v3:.4f}, {ci_hi_v3:.4f}]")
        results.append({"version": "v3_ITA", "n": len(v3_valid),
                        "gap": gap_v3, "ci_lo": ci_lo_v3, "ci_hi": ci_hi_v3,
                        **{f"rate_{k}": v for k, v in rates_v3.items()}})
    else:
        print(f"\n  Version 3 (ITA-relabeled): [SKIPPED — 图像不可达或样本不足]")
        print(f"  TODO: 确认 {FITZ_IMG_DIR} 图像文件存在后重跑以得三版对比")

    # ── 版本间标准差 ──────────────────────────────────────────────────────
    gap_vals = [r["gap"] for r in results if not math.isnan(r["gap"])]
    if len(gap_vals) >= 2:
        version_gap_std = float(np.std(gap_vals, ddof=0))
    else:
        version_gap_std = float("nan")

    print(f"\n  Gaps per version: {[f'{v:.4f}' for v in gap_vals]}")
    print(f"  Version-level gap std = {version_gap_std:.4f}  (MDE = {MDE_STD})")

    # ── 不一致对分析（两版对比）────────────────────────────────────────
    # 有效行同时有两版标签的
    both_valid = df[(df["fitzpatrick_scale"] != -1) & (df["fitzpatrick_centaur"] != -1)].copy()
    disagree = both_valid[both_valid["fitzpatrick_scale"] != both_valid["fitzpatrick_centaur"]]
    agree_rate = 1.0 - len(disagree) / len(both_valid) if len(both_valid) > 0 else float("nan")
    print(f"\n  Version 1 vs 2 agreement: {100*agree_rate:.1f}%  "
          f"({len(disagree)} disagreements / {len(both_valid)} both-labeled)")

    # 不一致是否集中在深肤色（IV-VI）
    disagree = disagree.copy()
    disagree["is_dark"] = disagree["fitzpatrick_scale"].isin([4, 5, 6])
    dark_disagree_frac = float(disagree["is_dark"].mean()) if len(disagree) > 0 else float("nan")
    dark_in_all = float((both_valid["fitzpatrick_scale"].isin([4, 5, 6])).mean())
    print(f"  Disagreements in dark (IV-VI): {100*dark_disagree_frac:.1f}%  "
          f"(base rate in all: {100*dark_in_all:.1f}%)")
    if not math.isnan(dark_disagree_frac):
        if dark_disagree_frac > dark_in_all + 0.05:
            print("    -> 不一致集中在深肤色 (H3 支持：深肤色更难标注，噪声更大)")
        else:
            print("    -> 不一致未集中在深肤色")

    # ── R9 判读 ──────────────────────────────────────────────────────────
    print("\n--- R9 判读（CPU label-distribution gap）---")
    if math.isnan(version_gap_std):
        verdict = "GRAY — 仅有一版 gap 可用，无法算版本间标准差，标功效不足"
    elif version_gap_std >= MDE_STD:
        verdict = (
            f"PASS/MAIN — gap 版本间标准差={version_gap_std:.4f} >= MDE({MDE_STD}) → "
            "label distribution gap 在版本间有可测差异 → 传播效应天花板非零 → 进 GPU 验 AUC gap → 升 MAIN"
        )
    else:
        verdict = (
            f"KILL — gap 版本间标准差={version_gap_std:.4f} < MDE({MDE_STD}) → "
            "label 分布对版本稳健 → 传播效应天然弱 → 降平淡 audit"
        )

    print(f"  {verdict}")
    print(f"\n  NOTE: label-distribution gap 是 AUC gap 的必要条件；")
    print(f"  最终 AUC gap 需 GPU linear probe（backbone TODO：待 researcher 确认）")

    # ── 存 CSV ───────────────────────────────────────────────────────────
    out_df = pd.DataFrame(results)
    out_df["version_gap_std"] = version_gap_std
    out_df["mde_std"] = MDE_STD
    out_df["v1v2_agreement_pct"] = float(100 * agree_rate)
    out_df["dark_disagree_pct"] = float(100 * dark_disagree_frac)
    out_df["verdict"] = verdict
    out_path = RESULTS_DIR / "S4A02_label_propagation.csv"
    out_df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"\n  Saved -> {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="S4A-02 Fitzpatrick17k label propagation kill-shot")
    parser.add_argument("--smoke", type=int, default=0, help="smoke test (0=full)")
    parser.add_argument("--max_ita_images", type=int, default=500,
                        help="max images to compute ITA (0=all; full run slow on 16k images)")
    args = parser.parse_args()
    main(smoke=bool(args.smoke), max_ita_images=args.max_ita_images)
