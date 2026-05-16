"""QCTS 实验脚本 — 供 BMVC P2 使用。

Pipeline:
  1. 从预计算特征加载 val split（不需要重新过图片）
  2. 用 Std VIB (D) 在 val 集跑确定性前向，得到 binary logit + q̄
  3. L-BFGS 拟合 QCTS 参数 (T0, α)，最小化 val NLL
  4. 用 itb_predictions.csv 里的 D 预测概率重建 logit，施加 QCTS
  5. 计算 ITB 各子集的 AUC/ECE/QCDI/ρ，写入 results/
  6. 逐退化维度 ECE 分析（ITB-LQ 按主降质维度分组）

Usage:
  cd D:/YJ-Agent/project
  python run_qcts.py
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from scipy.optimize import minimize
from scipy.stats import spearmanr
from torch.utils.data import DataLoader, TensorDataset
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from benchmark.metrics import compute_binary_ece, summary_metrics
from models.q_vib_encoder import QVIBEncoder
from models.qad_classifier import QADClassifier

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
ROOT = Path("D:/YJ-Agent")
PROJ = Path(__file__).parent
METADATA_CSV = ROOT / "data/raw/isic2020/train-metadata.csv"


# ── 1. 加载预计算数据 ──────────────────────────────────────────────────────────

def load_assets():
    q_labels = pd.read_csv(ROOT / "data/quality_labels_all.csv")
    abcd_cache = pd.read_csv(ROOT / "data/abcd_cache.csv")
    ef_index = pd.read_csv(ROOT / "data/efficientnet_index.csv")
    ef_all = np.load(ROOT / "data/efficientnet_features.npy", mmap_mode="r")
    isic_split = pd.read_csv(ROOT / "data/isic_split.csv")
    metadata = pd.read_csv(METADATA_CSV)[["isic_id", "target"]]
    return q_labels, abcd_cache, ef_index, ef_all, isic_split, metadata


def _extract_isic_id(path_str: str) -> str | None:
    m = re.search(r"(ISIC_\d+)", str(path_str))
    return m.group(1) if m else None


SCORE_COLS = ["sharpness", "brightness", "completeness", "color_temp", "contrast"]


# ── 2. 构建 val 集特征矩阵 ────────────────────────────────────────────────────

def build_val_tensors(q_labels, abcd_cache, ef_index, ef_all, isic_split, metadata):
    val_ids = set(isic_split[isic_split["split"] == "val"]["isic_id"])

    q_labels = q_labels.copy()
    q_labels["isic_id"] = q_labels["original_path"].apply(_extract_isic_id)

    # 只保留 val 集 + ISIC 来源（和训练时一致）
    q_val = q_labels[(q_labels["isic_id"].isin(val_ids)) & (q_labels["source"] == "isic2020")].copy()
    q_val = q_val.merge(metadata, on="isic_id", how="inner")
    q_val = q_val.merge(abcd_cache, on="degraded_path", how="inner")
    q_val = q_val.merge(ef_index, on="degraded_path", how="inner")

    print(f"[val] {len(q_val)} samples (3 levels × {len(val_ids)} ISIC val images)")

    abcd_arr = q_val[["A", "B", "C", "D"]].values.astype(np.float32)
    q_arr = q_val[SCORE_COLS].values.astype(np.float32)
    qbar_arr = q_arr.mean(axis=1)
    targets = q_val["target"].values.astype(np.int64)

    # EfficientNet features（从大矩阵按行索引取，mmap 不会全读进内存）
    row_idxs = q_val["efnet_row_idx"].values
    ef_arr = ef_all[row_idxs].astype(np.float32)

    return (
        torch.tensor(abcd_arr),
        torch.tensor(q_arr),
        torch.tensor(qbar_arr),
        torch.tensor(ef_arr),
        torch.tensor(targets),
    )


# ── 3. 加载 Std VIB 模型 ─────────────────────────────────────────────────────

def load_stdvib():
    ckpt = torch.load(ROOT / "checkpoints/stdvib/best_qad.pth", map_location=DEVICE)
    encoder = QVIBEncoder(
        abcd_dim=4, q_dim=5, d_model=128, n_heads=4, latent_dim=64, efnet_dim=1280
    ).to(DEVICE).eval()
    classifier = QADClassifier(
        latent_dim=64, hidden_dim=128, num_classes=2, dropout=0.2
    ).to(DEVICE).eval()
    encoder.load_state_dict(ckpt["encoder"])
    classifier.load_state_dict(ckpt["classifier"])
    # 关闭 tokenizer（Std VIB 不使用）
    encoder.tokenizer.forward = lambda q: torch.zeros(q.shape[0], device=q.device)
    return encoder, classifier


# ── 4. Val 集前向推理 → binary logit ─────────────────────────────────────────

def get_val_logits(encoder, classifier, abcd_t, q_t, qbar_t, ef_t, targets_t,
                   batch_size=512):
    """确定性前向（用 mu，不采样），返回 binary logit = l1 − l0。"""
    dataset = TensorDataset(abcd_t, q_t, qbar_t, ef_t, targets_t)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0)

    all_logits, all_qbar, all_targets = [], [], []
    with torch.no_grad():
        for abcd_b, q_b, qbar_b, ef_b, tgt_b in tqdm(loader, desc="[val inference]"):
            abcd_b = abcd_b.to(DEVICE)
            q_b = q_b.to(DEVICE)
            ef_b = ef_b.to(DEVICE)
            mu, _ = encoder(abcd_b, q_b, efnet_feat=ef_b)
            logits_2 = classifier(mu)           # (B, 2)
            binary_logit = logits_2[:, 1] - logits_2[:, 0]   # (B,)
            all_logits.append(binary_logit.cpu())
            all_qbar.append(qbar_b)
            all_targets.append(tgt_b)

    return (
        torch.cat(all_logits).numpy(),
        torch.cat(all_qbar).numpy(),
        torch.cat(all_targets).numpy(),
    )


# ── 5. QCTS 参数拟合 ──────────────────────────────────────────────────────────

def softplus(x):
    return np.log1p(np.exp(x))


def qcts_temperature(params, qbar):
    """T(q̄) = softplus(T0 + α·(1 − q̄))."""
    T0, alpha = params
    return softplus(T0 + alpha * (1.0 - qbar))


def qcts_nll(params, logits, qbar, targets):
    T = qcts_temperature(params, qbar)
    T = np.maximum(T, 1e-3)
    scaled = logits / T
    # log-sigmoid loss
    log_prob_pos = -np.log1p(np.exp(-scaled))
    log_prob_neg = -np.log1p(np.exp(scaled))
    nll = -(targets * log_prob_pos + (1 - targets) * log_prob_neg)
    return float(nll.mean())


def fit_qcts(val_logits, val_qbar, val_targets, seeds=3):
    """Multi-start L-BFGS。返回最优 (T0, α)。"""
    best_nll = np.inf
    best_params = None
    for seed in range(seeds):
        rng = np.random.default_rng(seed)
        x0 = rng.uniform(0.0, 1.0, size=2)
        res = minimize(
            qcts_nll, x0,
            args=(val_logits, val_qbar, val_targets),
            method="L-BFGS-B",
            bounds=[(-5, 5), (0, 10)],   # α ≥ 0 保证低质量 T 更大
            options={"maxiter": 500},
        )
        if res.fun < best_nll:
            best_nll = res.fun
            best_params = res.x

    T0, alpha = best_params
    T_base = softplus(T0)
    T_lq = softplus(T0 + alpha * 1.0)    # q̄ = 0
    T_hq = softplus(T0 + alpha * 0.0)    # q̄ = 1
    print(f"\n[QCTS] T0={T0:.4f}  α={alpha:.4f}  NLL={best_nll:.4f}")
    print(f"  T(q̄=0)={T_lq:.3f}   T(q̄=1)={T_hq:.3f}   T_base={T_base:.3f}")
    return float(T0), float(alpha)


# ── 6. ITB 推理（重建 logit 施加 QCTS）────────────────────────────────────────

def apply_qcts_to_itb(itb_preds, T0, alpha):
    """从 itb_predictions.csv 里的 D (Std VIB) 概率重建 logit，再施加 QCTS。"""
    d_preds = itb_preds[itb_preds["baseline"] == "D"].copy()

    # prob_pos → binary logit
    p = d_preds["prob_pos"].clip(1e-7, 1 - 1e-7).values
    logits = np.log(p / (1 - p))
    qbar = d_preds["qbar"].values

    T = qcts_temperature([T0, alpha], qbar)
    prob_qcts = 1.0 / (1.0 + np.exp(-logits / T))
    entropy = -(prob_qcts * np.log(prob_qcts + 1e-9) +
                (1 - prob_qcts) * np.log(1 - prob_qcts + 1e-9))

    d_preds = d_preds.copy()
    d_preds["prob_pos_qcts"] = prob_qcts
    d_preds["entropy_qcts"] = entropy
    return d_preds


def compute_itb_metrics(d_preds_qcts):
    rows = []
    for subset in sorted(d_preds_qcts["subset"].unique()):
        sub = d_preds_qcts[d_preds_qcts["subset"] == subset]
        prob = sub["prob_pos_qcts"].values
        targets = sub["target"].values
        qbar = sub["qbar"].values
        m = summary_metrics(prob, targets, qbar)
        rows.append({
            "baseline": "QCTS",
            "baseline_name": "Std VIB + QCTS (ours)",
            "subset": subset,
            "n": len(sub),
            **{k: v for k, v in m.items() if k != "qbar_ece_segments"},
        })
        print(f"  [QCTS] {subset}: AUC={m['auc']:.3f}  ECE={m['ece']:.3f}  "
              f"H̄={m['mean_entropy']:.3f}")

    # QCDI
    ece_lq = next(r["ece"] for r in rows if r["subset"] == "ITB-LQ")
    ece_hq = next(r["ece"] for r in rows if r["subset"] == "ITB-HQ")
    for r in rows:
        r["qcdi"] = ece_lq - ece_hq

    # Spearman ρ (entropy ~ q̄) on full ITB
    all_ent = d_preds_qcts["entropy_qcts"].values
    all_qbar = d_preds_qcts["qbar"].values
    rho, pval = spearmanr(all_ent, all_qbar)
    print(f"\n[QCTS] ρ(entropy, q̄) = {rho:.4f}  p = {pval:.2e}")
    print(f"[QCTS] QCDI = {ece_lq - ece_hq:.4f}")

    return rows, rho, ece_lq - ece_hq


# ── 7. 逐退化维度分析（ITB-LQ）────────────────────────────────────────────────

def per_degradation_analysis(itb_preds, q_labels, abcd_cache, ef_index):
    """按主降质维度分组 ITB-LQ，计算各 baseline 的 ECE。"""
    # ITB-LQ 的图片路径从 itb_subsets.csv 获取
    itb_sub = pd.read_csv(PROJ / "results/itb_subsets.csv")
    lq = itb_sub[itb_sub["subset"] == "ITB-LQ"].copy()

    # 取 image_path（即 degraded_path）
    lq["degraded_path"] = lq["image_path"].apply(str)

    # 合并质量维度
    q_sub = q_labels[SCORE_COLS + ["degraded_path"]].copy()
    lq = lq.merge(q_sub, on="degraded_path", how="left")

    # 主降质维度 = 最低分数的维度（排除 completeness）
    CHECK_DIMS = ["sharpness", "brightness", "color_temp", "contrast"]
    lq["dominant_degradation"] = lq[CHECK_DIMS].idxmin(axis=1)

    DIM_LABEL = {
        "sharpness": r"Blur ($q_1\downarrow$)",
        "brightness": r"Low brightness ($q_2\downarrow$)",
        "color_temp": r"Color temp ($q_4\downarrow$)",
        "contrast": r"Low contrast ($q_5\downarrow$)",
    }

    deg_rows = []
    for baseline in ["I", "J", "D", "QCTS"]:
        if baseline == "QCTS":
            sub_preds = itb_preds[itb_preds["baseline"] == "D"].copy()
            # 重建 QCTS prob（T0 和 alpha 存到文件后再读，这里占位）
            qcts_path = PROJ / "results/qcts_params.json"
            if qcts_path.exists():
                params = json.load(open(qcts_path))
                T0, alpha = params["T0"], params["alpha"]
                p = sub_preds["prob_pos"].clip(1e-7, 1 - 1e-7).values
                logits = np.log(p / (1 - p))
                T = qcts_temperature([T0, alpha], sub_preds["qbar"].values)
                sub_preds = sub_preds.copy()
                sub_preds["prob_pos"] = 1.0 / (1.0 + np.exp(-logits / T))
            bl_name = "D + QCTS"
        else:
            sub_preds = itb_preds[itb_preds["baseline"] == baseline].copy()
            bl_name = {"I": "MC Dropout", "J": "Deep Ensemble", "D": "Std VIB"}[baseline]

        lq_preds = sub_preds[sub_preds["subset"] == "ITB-LQ"].copy()

        # 合并主降质维度
        lq_merge = lq[["degraded_path", "dominant_degradation", "isic_id"]].copy()
        lq_merge["image_path"] = lq_merge["degraded_path"]
        # itb_preds 没有 image_path，要靠 isic_id 对上
        lq_with_target = lq[["isic_id", "dominant_degradation", "target"]].copy()

        # 用 target + qbar 的顺序对齐（两者都按 ITB-LQ 原顺序输出）
        # 简化：按 dominant_degradation 分组，找到 lq_preds 对应行
        # 由于 lq_preds 行数 == lq 行数，顺序一致（run_experiments.py 按 itb_subsets 行序输出）
        lq_preds = lq_preds.reset_index(drop=True)
        lq_dom = lq["dominant_degradation"].reset_index(drop=True)
        lq_targets = lq["target"].reset_index(drop=True)

        for dim in CHECK_DIMS:
            mask = (lq_dom == dim).values
            if mask.sum() < 10:
                continue
            prob = lq_preds.loc[mask, "prob_pos"].values
            tgt = lq_targets[mask].values
            ece = compute_binary_ece(prob, tgt)
            deg_rows.append({
                "baseline": baseline,
                "baseline_name": bl_name,
                "dominant_degradation": dim,
                "dim_label": DIM_LABEL[dim],
                "n": int(mask.sum()),
                "ece": round(ece, 4),
            })
            print(f"  [{bl_name}] {DIM_LABEL[dim]}: ECE={ece:.4f}  n={mask.sum()}")

    return pd.DataFrame(deg_rows)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("QCTS Experiment for BMVC P2")
    print("=" * 60)

    # 1. 加载资产
    q_labels, abcd_cache, ef_index, ef_all, isic_split, metadata = load_assets()

    # 2. 构建 val 特征
    abcd_t, q_t, qbar_t, ef_t, targets_t = build_val_tensors(
        q_labels, abcd_cache, ef_index, ef_all, isic_split, metadata
    )

    # 3. 加载 Std VIB
    print("\n[Loading Std VIB checkpoint...]")
    encoder, classifier = load_stdvib()

    # 4. Val 集推理
    val_logits, val_qbar, val_targets = get_val_logits(
        encoder, classifier, abcd_t, q_t, qbar_t, ef_t, targets_t
    )

    # 报告 val 集 TS 参照（和已有 T=2.324 对比）
    with open(ROOT / "checkpoints/stdvib/temperature.json") as f:
        T_ts = json.load(f)["T"]
    prob_ts = 1.0 / (1.0 + np.exp(-val_logits / T_ts))
    ece_ts_val = compute_binary_ece(prob_ts, val_targets)
    print(f"\n[val baseline] TS (T={T_ts:.3f}): val ECE = {ece_ts_val:.4f}")

    # 5. 拟合 QCTS
    print("\n[Fitting QCTS parameters...]")
    T0, alpha = fit_qcts(val_logits, val_qbar, val_targets)

    # 保存参数
    params_path = PROJ / "results/qcts_params.json"
    params_path.parent.mkdir(exist_ok=True)
    with open(params_path, "w") as f:
        json.dump({"T0": T0, "alpha": alpha}, f, indent=2)
    print(f"[Saved] {params_path}")

    # 6. 在 ITB 上评测 QCTS
    print("\n[Evaluating QCTS on ITB subsets...]")
    itb_preds = pd.read_csv(PROJ / "results/itb_predictions.csv")
    d_preds_qcts = apply_qcts_to_itb(itb_preds, T0, alpha)
    qcts_rows, rho, qcdi = compute_itb_metrics(d_preds_qcts)

    # 7. 和现有 D + TS 对比汇总
    itb_results = pd.read_csv(PROJ / "results/itb_results.csv")
    d_ts = itb_results[itb_results["baseline"].isin(["D", "TS"])][
        ["baseline", "baseline_name", "subset", "auc", "ece"]
    ].copy()
    print("\n── 对比汇总（ITB-LQ 和 ITB-HQ）──")
    for bl in ["D", "TS", "QCTS"]:
        if bl == "QCTS":
            lq_row = next(r for r in qcts_rows if r["subset"] == "ITB-LQ")
            hq_row = next(r for r in qcts_rows if r["subset"] == "ITB-HQ")
            print(f"  QCTS:  LQ AUC={lq_row['auc']:.3f} ECE={lq_row['ece']:.3f}  "
                  f"HQ ECE={hq_row['ece']:.3f}  QCDI={qcdi:.3f}  ρ={rho:.3f}")
        else:
            for sub in ["ITB-LQ", "ITB-HQ"]:
                r = d_ts[(d_ts["baseline"] == bl) & (d_ts["subset"] == sub)]
                if len(r):
                    print(f"  {bl} ({sub}): AUC={r['auc'].values[0]:.3f}  "
                          f"ECE={r['ece'].values[0]:.3f}")

    # 8. 保存 QCTS 结果
    qcts_df = pd.DataFrame(qcts_rows)
    qcts_df["rho"] = rho
    out_path = PROJ / "results/qcts_itb_results.csv"
    qcts_df.to_csv(out_path, index=False)
    print(f"\n[Saved] {out_path}")

    # 9. 逐退化维度分析
    print("\n[Per-degradation ECE analysis...]")
    deg_df = per_degradation_analysis(itb_preds, q_labels, abcd_cache, ef_index)
    deg_path = PROJ / "results/per_degradation_ece.csv"
    deg_df.to_csv(deg_path, index=False)
    print(f"[Saved] {deg_path}")

    print("\n✓ All done.")
    print("  → results/qcts_params.json")
    print("  → results/qcts_itb_results.csv")
    print("  → results/per_degradation_ece.csv")
    print("  Next: run gen_bmvc_figures.py to regenerate paper figures.")


if __name__ == "__main__":
    main()
