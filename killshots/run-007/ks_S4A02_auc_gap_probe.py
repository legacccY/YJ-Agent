"""
G5 Kill-shot: S4A-02 — Fitzpatrick17k FST 标签版本 AUC gap 探针（GPU 步 / 复验）
服务: run-007 ACCV 选题流水线 G5 杀手锏（lever = S4A-02 标签噪声传播 FINDINGS→MAIN）

预计单卡耗时: ~0 GPU·h（本地已有 efnet.npy 特征缓存，直接用，零 GPU 提取）
             若缓存不可用：ImageNet ResNet50 提特征 < 30min
数据前置:
  data/raw/fitzpatrick17k/fitzpatrick17k.csv
  data/raw/fitzpatrick17k/efnet.npy    (16574, 1280) EfficientNet-B0 特征缓存
  data/raw/fitzpatrick17k/index.csv    (image_id 对应 efnet.npy 行)
  data/raw/fitzpatrick17k/images/      (若无缓存则用 ResNet50 提特征)

三版 FST 标签（_G5_DESIGN §S4A-02）：
  v1: fitzpatrick_scale  (原版，官方标注)
  v2: fitzpatrick_centaur (独立第二版标注)
  v3: ITA-relabeled       (从图像 Lab 空间算 ITA 映射至 FST I-VI)
      ITA = atan2(L* - 50, b*) * 180/pi
      ITA > 55 → I; 41-55 → II; 28-41 → III; 19-28 → IV; 10-19 → V; <=10 → VI
      参考: Kinyanjui 2019, Groh 2021

目标：
  各版本下 logistic linear probe 二分类（malignant vs rest）
  按 FST I-VI 分组算 AUC，取 max-min 组间 gap
  三版 gap 的版本间标准差（ddof=1）对照 MDE

R9 判读约定（_G5_DESIGN.md §S4A-02）：
  PASS/MAIN : gap std >= 0.03 且方向有结构 → 噪声传播实证 → 升 MAIN
  KILL      : std < 0.03 且 CI 窄 → 结论稳健 → 降平淡 audit
  GRAY      : FST 组样本少致 CI 宽 → FINDINGS 进 G6

注意（verifier 提醒）：
  - v3 ITA medium 组可能 NaN（无 malignant 样本）→ 跳过 NaN 组，仅用有效组算 gap
  - gap std 用 ddof=1 (sample std)
  - 三版 gap 取 max(per-group AUC) - min(per-group AUC) for each version

输出: killshots/run-007/results/S4A02_auc_gap_probe.csv
      killshots/run-007/results/S4A02_state.json
"""

import argparse
import csv
import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np

# ── 路径 ────────────────────────────────────────────────────────────────────
REPO_ROOT    = Path(__file__).resolve().parent.parent.parent
FITZ_CSV     = REPO_ROOT / "data" / "raw" / "fitzpatrick17k" / "fitzpatrick17k.csv"
FITZ_INDEX   = REPO_ROOT / "data" / "raw" / "fitzpatrick17k" / "index.csv"
FITZ_EFNET   = REPO_ROOT / "data" / "raw" / "fitzpatrick17k" / "efnet.npy"
FITZ_IMG_DIR = REPO_ROOT / "data" / "raw" / "fitzpatrick17k" / "images"
RESULTS_DIR  = Path(__file__).resolve().parent / "results"

# ── 超参 ─────────────────────────────────────────────────────────────────────
MDE_STD      = 0.03   # gap std >= 0.03 视为噪声传播 (_G5_DESIGN §S4A-02 §2)
N_BOOTSTRAP  = 1000
RANDOM_STATE = 42

# ITA 到 FST 阈值映射 (Kinyanjui 2019 / Groh 2021)
ITA_THRESHOLDS = [55, 41, 28, 19, 10]  # > 55 → I, 41-55 → II, ..., <=10 → VI

# ── ITA 计算 ─────────────────────────────────────────────────────────────────


def compute_ita_from_img(img_path):
    """
    从 RGB 图计算 ITA。
    ITA = atan2(L* - 50, b*) * 180/pi
    L*, b* 取图像中心 crop 均值（避免白边），Lab 色彩空间。
    返回 ITA float 或 nan（图不存在/读取失败）。
    """
    from PIL import Image
    try:
        img = Image.open(img_path).convert("RGB")
        # 中心 crop 50%
        w, h = img.size
        cx, cy = w // 2, h // 2
        cw, ch = max(w // 4, 1), max(h // 4, 1)
        img_crop = img.crop((cx - cw, cy - ch, cx + cw, cy + ch))
        arr = np.array(img_crop, dtype=np.float32) / 255.0
        # sRGB → linear RGB
        arr_lin = np.where(arr <= 0.04045, arr / 12.92, ((arr + 0.055) / 1.055) ** 2.4)
        # linear RGB → XYZ (D65 standard)
        M = np.array([[0.4124564, 0.3575761, 0.1804375],
                      [0.2126729, 0.7151522, 0.0721750],
                      [0.0193339, 0.1191920, 0.9503041]])
        xyz = arr_lin.reshape(-1, 3) @ M.T  # (N, 3)
        # XYZ → Lab (D65 ref)
        ref = np.array([0.95047, 1.00000, 1.08883])
        f = xyz / ref
        f = np.where(f > 0.008856, f ** (1/3), 7.787 * f + 16/116)
        L = 116 * f[:, 1] - 16
        b = 200 * (f[:, 1] - f[:, 2])
        L_mean = float(np.mean(L))
        b_mean = float(np.mean(b))
        ita = math.atan2(L_mean - 50, b_mean) * 180.0 / math.pi
        return ita
    except Exception:
        return float("nan")


def ita_to_fst(ita):
    """ITA 值 → FST I-VI (1-6 int)，nan → -1"""
    if math.isnan(ita):
        return -1
    if ita > ITA_THRESHOLDS[0]:   return 1
    elif ita > ITA_THRESHOLDS[1]: return 2
    elif ita > ITA_THRESHOLDS[2]: return 3
    elif ita > ITA_THRESHOLDS[3]: return 4
    elif ita > ITA_THRESHOLDS[4]: return 5
    else:                          return 6


# ── 特征加载 ─────────────────────────────────────────────────────────────────


def load_features(smoke=False):
    """
    加载 EfficientNet-B0 特征缓存（efnet.npy + index.csv）。
    返回 feats (N, 1280)，ids (list of image_id/md5hash)。
    若缓存不可用，退化到 ResNet50 GPU 提取（标 TODO）。
    """
    if FITZ_EFNET.exists() and FITZ_INDEX.exists():
        print(f"[features] 使用本地特征缓存: {FITZ_EFNET}")
        feats = np.load(str(FITZ_EFNET), allow_pickle=True).astype(np.float32)
        ids = []
        with open(FITZ_INDEX, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ids.append(row["image_id"])
        assert len(ids) == feats.shape[0], \
            f"index.csv 行数 {len(ids)} != efnet.npy 行数 {feats.shape[0]}"
        if smoke:
            feats = feats[:200]
            ids   = ids[:200]
        print(f"  feats shape: {feats.shape}")
        return feats, ids
    else:
        # TODO: 若无缓存，需 GPU 提取 ResNet50 特征
        # 本地已确认 efnet.npy 存在，此分支仅作 fallback 占位
        raise RuntimeError(
            "# TODO: 特征缓存不存在，需 GPU 提取 ResNet50/EfficientNet 特征。\n"
            f"  期望路径: {FITZ_EFNET}\n"
            "  请先运行 feature extraction 或确认路径正确。"
        )


# ── 对齐 CSV 标签与特征 ──────────────────────────────────────────────────────


def load_and_align(feats, feat_ids, smoke=False):
    """
    读 fitzpatrick17k.csv，按 md5hash 与 feat_ids 对齐，
    返回 aligned_feats, metadata_list。
    metadata: (idx_in_feats, fst_v1, fst_v2, is_malignant, url_alphanum)
    """
    import pandas as pd
    df = pd.read_csv(FITZ_CSV, encoding="utf-8")

    # 构建 md5hash → 行映射
    df_map = {row["md5hash"]: row for _, row in df.iterrows()}

    aligned_idxs = []
    fst_v1_list = []
    fst_v2_list = []
    malignant_list = []
    url_list = []

    feat_id2idx = {iid: i for i, iid in enumerate(feat_ids)}
    for md5 in feat_ids:
        row = df_map.get(md5)
        if row is None:
            continue
        # v1: fitzpatrick_scale，-1=未标，过滤
        v1 = int(row["fitzpatrick_scale"])
        v2 = int(row["fitzpatrick_centaur"])
        if v1 == -1 or v2 == -1:
            continue
        is_mal = int(row["three_partition_label"] == "malignant")
        aligned_idxs.append(feat_id2idx[md5])
        fst_v1_list.append(v1)
        fst_v2_list.append(v2)
        malignant_list.append(is_mal)
        url_list.append(md5)

    aligned_feats = feats[aligned_idxs]
    fst_v1  = np.array(fst_v1_list, dtype=np.int32)
    fst_v2  = np.array(fst_v2_list, dtype=np.int32)
    malignant = np.array(malignant_list, dtype=np.int32)

    print(f"[align] aligned samples: {len(malignant)}, malignant: {malignant.sum()}")
    return aligned_feats, fst_v1, fst_v2, malignant, url_list


# ── ITA 第三版标签计算 ────────────────────────────────────────────────────────


def compute_v3_ita_labels(url_list, img_dir, smoke=False):
    """
    对 aligned 样本计算 ITA，映射为 FST v3。
    url_list: md5hash 列表（与对齐后样本一一对应）。
    图文件名可能是 md5hash 或其他，需要查实际 images/ 目录结构。
    """
    img_dir = Path(img_dir)
    if not img_dir.exists():
        print(f"[v3 ITA] 图目录不存在: {img_dir}，跳过 v3，标 TODO")
        return None

    # 看看实际图文件命名格式
    sample_files = list(img_dir.iterdir())[:3]
    print(f"[v3 ITA] 图目录示例: {[f.name for f in sample_files]}")

    fst_v3 = []
    n_ok = 0
    n_missing = 0
    targets = url_list[:200] if smoke else url_list
    for md5 in targets:
        # 尝试多种命名
        found = False
        for suffix in [".jpg", ".jpeg", ".png"]:
            p = img_dir / f"{md5}{suffix}"
            if p.exists():
                ita = compute_ita_from_img(p)
                fst_v3.append(ita_to_fst(ita))
                n_ok += 1
                found = True
                break
        if not found:
            fst_v3.append(-1)
            n_missing += 1

    print(f"[v3 ITA] computed: {n_ok}/{len(targets)}, missing: {n_missing}")
    if n_ok < len(targets) * 0.5:
        print(f"[v3 ITA] WARNING: 超过 50% 图文件未找到，v3 可能不可靠")
    return np.array(fst_v3, dtype=np.int32)


# ── Logistic Probe + 分组 AUC ───────────────────────────────────────────────


def logistic_probe_group_aucs(feats, fst_labels, malignant, version_name):
    """
    训练 logistic probe（malignant vs rest），在每个 FST I-VI 组单独算 AUC。
    返回 dict: {fst_group: auc} （nan 若该组样本<5 或 AUC 无定义）
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score

    # 过滤 -1 (未标)
    valid_mask = fst_labels >= 1
    X = feats[valid_mask]
    y = malignant[valid_mask]
    groups = fst_labels[valid_mask]

    if len(np.unique(y)) < 2:
        print(f"[probe {version_name}] WARNING: 只有一类 malignant 标签，跳过")
        return {}

    # 标准化特征
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # 训 logistic probe（全量，对齐后数据）
    clf = LogisticRegression(C=1.0, max_iter=1000, solver="lbfgs",
                             random_state=RANDOM_STATE)
    clf.fit(X_scaled, y)
    probs = clf.predict_proba(X_scaled)[:, 1]

    # 按 FST 分组算 AUC
    group_aucs = {}
    for g in range(1, 7):  # FST I-VI
        mask = groups == g
        if mask.sum() < 5:
            group_aucs[f"FST_{g}"] = float("nan")
            continue
        yt = y[mask]
        ys = probs[mask]
        if len(np.unique(yt)) < 2:
            group_aucs[f"FST_{g}"] = float("nan")
            continue
        group_aucs[f"FST_{g}"] = float(roc_auc_score(yt, ys))

    n_valid = sum(1 for v in group_aucs.values() if not (isinstance(v, float) and math.isnan(v)))
    print(f"[probe {version_name}] valid groups: {n_valid}/6, "
          f"aucs: {[round(v,3) if not (isinstance(v,float) and math.isnan(v)) else 'nan' for v in group_aucs.values()]}")
    return group_aucs


def compute_gap(group_aucs):
    """
    gap = max(valid_aucs) - min(valid_aucs)（跳过 nan 组）
    若有效组 < 2，返回 nan。
    """
    valid = [v for v in group_aucs.values() if isinstance(v, float) and not math.isnan(v)]
    if len(valid) < 2:
        return float("nan")
    return max(valid) - min(valid)


# ── Bootstrap gap std CI ──────────────────────────────────────────────────────


def bootstrap_gap_std_ci(gap_list, n_boot=N_BOOTSTRAP, seed=RANDOM_STATE, alpha=0.05):
    """
    对三版 gap 值的 std（ddof=1）做 bootstrap CI。
    gap_list: list of 3 float（v1/v2/v3 各一个 gap）
    Bootstrap: 对三元组做 resample with replacement，每次算 std(ddof=1)。
    注意: n=3 太小，bootstrap 此处主要用于方向性，宽 CI 视为 GRAY。
    """
    rng = np.random.default_rng(seed)
    gaps = np.array([g for g in gap_list if not math.isnan(g)], dtype=np.float64)
    if len(gaps) < 2:
        return float("nan"), float("nan")
    boot_stds = []
    n = len(gaps)
    for _ in range(n_boot):
        samp = rng.choice(gaps, size=n, replace=True)
        std = float(np.std(samp, ddof=1)) if len(samp) >= 2 else float("nan")
        if not math.isnan(std):
            boot_stds.append(std)
    if len(boot_stds) < 10:
        return float("nan"), float("nan")
    boot_stds = np.array(boot_stds)
    lo = float(np.percentile(boot_stds, 100 * alpha / 2))
    hi = float(np.percentile(boot_stds, 100 * (1 - alpha / 2)))
    return lo, hi


# ── R9 判读 ──────────────────────────────────────────────────────────────────


def r9_verdict(gap_std, ci_lo, ci_hi, mde=MDE_STD):
    if any(isinstance(x, float) and math.isnan(x) for x in [gap_std, ci_lo, ci_hi]):
        return "GRAY", "gap std 或 CI 含 nan（v3 无效 / 样本不足）→ FINDINGS 进 G6"
    ci_width = ci_hi - ci_lo
    if ci_width > 0.10:
        return "GRAY", f"CI 宽={ci_width:.4f}>0.10（n=3 版本，功效不足）→ FINDINGS 进 G6"
    if gap_std >= mde and ci_lo > 0:
        return "PASS", (f"gap_std={gap_std:.4f}>={mde}, CI=[{ci_lo:.4f},{ci_hi:.4f}] 下界 > 0 "
                        f"→ 噪声传播实证 → 升 MAIN")
    if gap_std < mde and ci_hi < mde:
        return "KILL", (f"gap_std={gap_std:.4f}<{mde} 且 CI_hi={ci_hi:.4f}<{mde} "
                        f"→ 结论对标签版本稳健 → 降平淡 audit")
    return "GRAY", f"gap_std={gap_std:.4f}，方向信号但 CI 宽，待进 G6 扩规模"


# ── 写工具 ───────────────────────────────────────────────────────────────────


def _write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"  -> {path}")


def _update_state(state_path, **kwargs):
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {}
    if state_path.exists():
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
    state.update(kwargs)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ── 主流程 ───────────────────────────────────────────────────────────────────


def set_seed(seed=RANDOM_STATE):
    random.seed(seed)
    np.random.seed(seed)


def main(args):
    set_seed(RANDOM_STATE)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    state_path = RESULTS_DIR / "S4A02_state.json"

    # GPU 检查（本脚本以缓存特征为主，GPU 非必须，但检查后打印）
    try:
        import torch
        if torch.cuda.is_available() and not args.cpu:
            print(f"[S4A02] CUDA 可用: {torch.cuda.get_device_name(0)}")
            print(f"  注: 本脚本使用本地 efnet.npy 缓存，GPU 仅在需要重新提特征时使用")
        else:
            print("[S4A02] CPU 模式（efnet.npy 缓存已有，不需要 GPU 提特征）")
    except ImportError:
        print("[S4A02] torch 不可用，CPU 模式")

    _update_state(state_path, status="running", start_time=time.strftime("%Y-%m-%dT%H:%M:%S"),
                  smoke=args.smoke)

    # ── Step 1: 加载特征缓存 ─────────────────────────────────────────────────
    print("\n[Step 1] 加载 EfficientNet-B0 特征缓存")
    feats, feat_ids = load_features(smoke=args.smoke)

    # ── Step 2: 对齐 CSV 标签与特征 ────────────────────────────────────────
    print("\n[Step 2] 对齐 Fitzpatrick17k CSV 标签")
    aligned_feats, fst_v1, fst_v2, malignant, url_list = load_and_align(
        feats, feat_ids, smoke=args.smoke
    )
    if args.smoke:
        # smoke 只用前 500 行
        aligned_feats = aligned_feats[:500]
        fst_v1 = fst_v1[:500]
        fst_v2 = fst_v2[:500]
        malignant = malignant[:500]
        url_list = url_list[:500]

    _update_state(state_path, n_aligned=len(malignant), n_malignant=int(malignant.sum()))

    # ── Step 3: ITA 第三版标签 ──────────────────────────────────────────────
    print("\n[Step 3] 计算 ITA 第三版标签 (v3)")
    fst_v3 = compute_v3_ita_labels(url_list, FITZ_IMG_DIR, smoke=args.smoke)
    if fst_v3 is not None and len(fst_v3) == len(malignant):
        v3_valid = int(np.sum(fst_v3 >= 1))
        print(f"  v3 valid (FST 1-6): {v3_valid}/{len(fst_v3)}")
        _update_state(state_path, v3_valid=v3_valid)
    else:
        print("  v3 ITA 不可用或长度不匹配，仅用 v1/v2 计算 std")
        fst_v3 = None

    # ── Step 4: 三版 logistic probe + 分组 AUC gap ──────────────────────────
    print("\n[Step 4] logistic probe FST 分组 AUC gap")
    versions = {"v1": fst_v1, "v2": fst_v2}
    if fst_v3 is not None:
        versions["v3"] = fst_v3

    gap_per_version = {}
    group_auc_rows = []
    for vname, fst_labels in versions.items():
        group_aucs = logistic_probe_group_aucs(aligned_feats, fst_labels, malignant, vname)
        gap = compute_gap(group_aucs)
        gap_per_version[vname] = gap
        print(f"  [{vname}] gap={gap:.4f}" if not math.isnan(gap) else f"  [{vname}] gap=nan")
        for grp, auc in group_aucs.items():
            group_auc_rows.append({
                "version": vname,
                "fst_group": grp,
                "group_auc": round(auc, 4) if not math.isnan(auc) else "nan",
                "gap": round(gap, 4) if not math.isnan(gap) else "nan",
            })

    _write_csv(RESULTS_DIR / "S4A02_group_aucs.csv", group_auc_rows)

    # ── Step 5: 版本间 gap std + bootstrap CI ───────────────────────────────
    print("\n[Step 5] 版本间 gap std (ddof=1) + bootstrap CI")
    gap_list = list(gap_per_version.values())
    valid_gaps = [g for g in gap_list if not math.isnan(g)]

    if len(valid_gaps) >= 2:
        gap_std = float(np.std(valid_gaps, ddof=1))  # ddof=1 (verifier 要求)
        ci_lo, ci_hi = bootstrap_gap_std_ci(valid_gaps)
    else:
        gap_std = float("nan")
        ci_lo = ci_hi = float("nan")

    print(f"  gap per version: {gap_per_version}")
    print(f"  gap_std(ddof=1)={gap_std:.4f}" if not math.isnan(gap_std) else "  gap_std=nan")
    print(f"  CI=[{ci_lo:.4f},{ci_hi:.4f}]" if not (math.isnan(ci_lo) or math.isnan(ci_hi)) else "  CI=[nan,nan]")

    # R9 判读
    verdict, verdict_msg = r9_verdict(gap_std, ci_lo, ci_hi)

    # 组合输出行
    result_row = {
        "gap_v1": round(gap_per_version.get("v1", float("nan")), 4)
                  if not math.isnan(gap_per_version.get("v1", float("nan"))) else "nan",
        "gap_v2": round(gap_per_version.get("v2", float("nan")), 4)
                  if not math.isnan(gap_per_version.get("v2", float("nan"))) else "nan",
        "gap_v3": round(gap_per_version.get("v3", float("nan")), 4)
                  if "v3" in gap_per_version and not math.isnan(gap_per_version["v3"]) else "nan",
        "gap_std_ddof1": round(gap_std, 4) if not math.isnan(gap_std) else "nan",
        "gap_std_ci_lo": round(ci_lo, 4) if not math.isnan(ci_lo) else "nan",
        "gap_std_ci_hi": round(ci_hi, 4) if not math.isnan(ci_hi) else "nan",
        "n_versions_valid": len(valid_gaps),
        "n_aligned": len(malignant),
        "n_malignant": int(malignant.sum()),
        "mde_threshold": MDE_STD,
        "r9_verdict": verdict,
        "r9_msg": verdict_msg,
        "note": (
            "v1=fitzpatrick_scale(原版) v2=fitzpatrick_centaur(独立标注) "
            "v3=ITA-relabeled(Lab色彩空间 atan2(L*-50,b*)); "
            "probe=EfficientNet-B0 缓存特征(efnet.npy 16574x1280)+LogisticRegression C=1.0; "
            "gap=max_group_AUC-min_group_AUC per FST I-VI（跳 nan 组）; "
            "gap_std ddof=1(sample std); "
            "v3 ITA medium 组 nan 已处理（计算 gap 只用有效组）"
        ),
    }

    _write_csv(RESULTS_DIR / "S4A02_auc_gap_probe.csv", [result_row])

    print("\n" + "=" * 60)
    print(f"[S4A02] R9 判读: {verdict}")
    print(f"  {verdict_msg}")
    print(f"  gap v1={result_row['gap_v1']} v2={result_row['gap_v2']} v3={result_row['gap_v3']}")
    print(f"  gap_std(ddof=1)={result_row['gap_std_ddof1']} CI=[{result_row['gap_std_ci_lo']},{result_row['gap_std_ci_hi']}]")
    print(f"  MDE={MDE_STD}, n_aligned={len(malignant)}, n_malignant={malignant.sum()}")
    print("=" * 60)

    _update_state(state_path, status="done",
                  end_time=time.strftime("%Y-%m-%dT%H:%M:%S"),
                  r9_verdict=verdict,
                  gap_std=gap_std if not math.isnan(gap_std) else "nan")
    print("[S4A02] 完成。结果在 killshots/run-007/results/")


def parse_args():
    parser = argparse.ArgumentParser(
        description="S4A-02 G5 killshot: FST 标签版本 AUC gap 探针"
    )
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--cpu", action="store_true", help="强制 CPU 模式")
    parser.add_argument("--smoke", action="store_true",
                        help="烟测模式: 500 samples, 1 round")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(args)
