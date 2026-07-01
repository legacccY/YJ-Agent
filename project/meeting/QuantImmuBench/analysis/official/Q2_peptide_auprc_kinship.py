#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Q2_peptide_auprc_kinship.py
===========================
服务: QuantImmuBench §3.3.4 (geomean fusion 措辞) + 回答袁老师问题二 ——
  geomean / mean_rank / median 三近亲融合法在 *肽级 AUPRC* 上的配对显著性 (副主指标, B3 口径)。
对应大纲: paper/QuanImmu-Paper-Outline.md §3.3.4 + §2.6 (肽级 AUPRC 为并列副指标, 非 headline)。

━━━ 定位 (与 Q2_fusion_kinship_paired 互补) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  · Q2_fusion_kinship_paired = patient-level Spearman 主指标口径的三近亲配对。
  · 本脚本 = 肽级 AUPRC 口径 (130 肽当一个池子, TESLA/IMPROVE 惯用), 复用 S1 机制。
    estimand 换了 (混病人内/间信号, 忽略病人结构), 二者并列不替换; headline 仍是 per-patient
    Spearman。这条 caveat 写进 CSV 头, 防 reviewer 误当 headline。

做什么 (照抄 S1 的标签构建 + bootstrap + 配对机制, fusion 换成三近亲):
  · fusion 输入 = S1 的 4 工具零选择 max 维 (FUSION_TOOLS_MAX, 不用 SURV6 —— 与 S1 同维便于对齐)。
  · 三近亲融合分: fusion_geomean / fusion_mean_rank / fusion_median (apply_fusion 病人内 rank 融合)。
  · 两套二分标签 (照抄 S1 load_binary_labels): 平衡标签 pval<0.05 (primary/headline) +
    Elispot>0 (sensitivity, 12 阴不可靠仅旁证)。
  · 三对配对 ΔAUPRC (1000× bootstrap, seed=42, 同 130 肽重采样, 共同非缺子集):
    (geomean,mean_rank)、(geomean,median)、(mean_rank,median)。

输入 (只读):
  · 分数 = data/frozen/pooled_clean_9mer.csv。
  · 标签 = data/OFFICIAL_DO_NOT_TOUCH/ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx (只读)。
输出 (analysis/official/):
  Q2_peptide_auprc_kinship.csv — 每对×每标签一行 (S1 paired 列):
    method_a,method_b,label_kind,AUPRC_a,AUPRC_b,delta,ci_lo,ci_hi,p_cross0,n_used。

跑法 (主线跑, 本脚本绝不自跑):
  cd D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/official
  python Q2_peptide_auprc_kinship.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _official_common import (                              # noqa: E402
    FROZEN_POOLED, apply_fusion, ensure_out_dir, load_frozen, r6,
)
# 复用 S1 的标签构建与配对 ΔAUPRC 机制 (不重造, 保口径逐位一致)。
from S1_peptide_level_auprc import (                        # noqa: E402
    attach_labels, paired_delta_auprc, FUSION_TOOLS_MAX, N_BOOT, SEED, LABEL_ROLE,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 三近亲融合法 (apply_fusion 方法名 -> 展示名)。fusion 输入 = S1 的 4 工具 max 维。
KIN_FUSIONS = {
    "geomean": "fusion_geomean",
    "mean_rank": "fusion_mean_rank",
    "median": "fusion_median",
}
# 三对近亲配对 (展示名)。
KIN_PAIRS = [
    ("fusion_geomean", "fusion_mean_rank"),
    ("fusion_geomean", "fusion_median"),
    ("fusion_mean_rank", "fusion_median"),
]


def build_kin_scores(df):
    """返回 {展示名: np.array(融合分, 对齐 df 行)}。fusion 输入 = S1 的 4 工具 max 维。"""
    scores = {}
    for meth, name in KIN_FUSIONS.items():
        fused = apply_fusion(df, FUSION_TOOLS_MAX, meth)
        scores[name] = np.asarray(fused.values, dtype=float)
    return scores


def main():
    out_dir = ensure_out_dir()
    print(f"[info] 读 pooled 干净表 (只读): {FROZEN_POOLED}")
    df = load_frozen(FROZEN_POOLED)
    print(f"[info] pooled shape={df.shape}; fusion 4 工具 max 维={FUSION_TOOLS_MAX}")

    df = attach_labels(df)                 # 挂 label_pval (主) + label_sfc (敏感性), 照抄 S1
    scores = build_kin_scores(df)

    all_paired = []
    for label_col, kind in [("label_pval", "pval<0.05"), ("label_sfc", "Elispot>0")]:
        role = LABEL_ROLE.get(kind, kind)
        y_all = df[label_col].values.astype(float)
        for a, b in KIN_PAIRS:
            rng_p = np.random.default_rng(SEED)     # 每对独立固定 seed, 复现 (同 S1)
            d = paired_delta_auprc(y_all, scores[a], scores[b], rng_p)
            d.update(method_a=a, method_b=b, label_kind=kind, role=role)
            all_paired.append(d)

    pdf = pd.DataFrame(all_paired)
    pcols = ["method_a", "method_b", "label_kind", "role", "AUPRC_a", "AUPRC_b",
             "delta", "ci_lo", "ci_hi", "p_cross0", "n_used"]
    pdf = pdf[pcols].copy()
    for c in ("AUPRC_a", "AUPRC_b", "delta", "ci_lo", "ci_hi", "p_cross0"):
        pdf[c] = pdf[c].map(lambda v: r6(v, 4))

    out_csv = out_dir / "Q2_peptide_auprc_kinship.csv"
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        f.write("# Q2_peptide_auprc_kinship.csv — §3.3.4 三近亲融合法肽级配对 ΔAUPRC (复用 S1 机制)\n")
        f.write("# 口径: 官方 130 肽; fusion 输入 = S1 的 4 工具零选择 max 维; bootstrap 1000× seed=42。\n")
        f.write("# delta = AUPRC(method_a) - AUPRC(method_b); p_cross0 = 双侧近似 (Δ* 跨 0 比例×2)。\n")
        f.write("# estimand caveat: 肽级 AUPRC 混病人内/间信号, 忽略病人结构, 与 per-patient Spearman【并列不替换】。\n")
        f.write("# role=primary(headline) 引平衡标签 pval<0.05; role=sensitivity(Elispot>0, 12阴不可靠) 仅旁证。\n")
        pdf.to_csv(f, index=False)
    print(f"\n[saved] {out_csv}")

    print("\n" + "=" * 78)
    print("三近亲融合法 肽级配对 ΔAUPRC (副主指标, 与 per-patient Spearman 并列不替换)")
    print("=" * 78)
    with pd.option_context("display.width", 160, "display.max_columns", 20):
        print(pdf.to_string(index=False))
    print("\n[caveat] AUPRC 混病人内/间信号; headline 仍是 per-patient Spearman (见 Q2_fusion_kinship_paired)。")
    print("[DONE] Q2_peptide_auprc_kinship 完成")


if __name__ == "__main__":
    main()
