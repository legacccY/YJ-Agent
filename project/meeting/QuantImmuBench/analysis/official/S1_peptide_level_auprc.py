#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
S1_peptide_level_auprc.py
=========================
服务: QuantImmuBench Part D Phase 4 —— 肽级 AUPRC 副主指标 (B3, TESLA/IMPROVE 口径)。
对应大纲: paper/QuanImmu-Paper-Outline.md §2.6 评判标准 (per-patient Spearman 为主指标,
本脚本产「肽级 AUPRC/AUROC」作并列副指标, 不替换主指标)。

━━━ 为何要这个副指标 (诚实 caveat, 写进 CSV/print) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  主指标 = per-patient Spearman(工具分, ELISpot SFC), 病人内 rank, 跨病人 Fisher-z 等权聚合
    —— estimand = 「病人内把肽按免疫原性排序」的能力 (临床选肽的真实用法)。
  本脚本 = 把 130 肽当**一个池子**算二分类 AUPRC/AUROC (TESLA/IMPROVE benchmark 惯用口径),
    estimand 换了: 混了病人内 + 病人间信号, 忽略病人结构 (不同病人 SFC 基线不可比)。
  → 二者**并列不替换**: AUPRC 便于与 TESLA/IMPROVE 文献横比, Spearman 才是本文 headline。
    (这条 caveat 写进 CSV 头 + 打印, 防 reviewer 以为 AUPRC 是主结果。)

━━━ 二分免疫原标签 (label 是 choice, 注明来源) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  · 【主标签】官方 xlsx 'In Vitro' sheet 的 `Ttest_pvalue_InVitroStim` < 0.05 = 阳性 (免疫原)。
      来源 = data/OFFICIAL_DO_NOT_TOUCH/ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx (只读)。
      按 mut_key = "<Patient_ID>|<Peptide_ID>" join 到 pooled 干净表。类别平衡 (≈76 阳/54 阴)。
  · 【敏感性标签】Elispot SFC > 0 = 阳性 (退化到 118 阳/12 阴, 极不平衡, 仅作稳健性旁证)。
  两套标签都跑, 主表用 pvalue<0.05, 敏感性版并排打印。

━━━ 输入 (只读) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  · 分数 = data/frozen/pooled_clean_9mer.csv (130 肽 × 30 工具×51 pooling)。零选择 max 维。
      ★ pooled 列已按 higher = 更免疫原 定向 (与 R1-R9 Spearman 同源, 正 rho 期望);
        本脚本**不做 in-sample 翻转** (翻转 = 用标签挑方向 = 乐观偏), 分数原样喂 AUPRC/AUROC。
  · 标签 = ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx 'In Vitro' sheet 的 Ttest_pvalue_InVitroStim。

━━━ 方法 (纯 numpy/pandas + sklearn.metrics; 禁 scipy.stats 防 OMP #15) ━━━━━━━━━━━━━━━
  · 逐 method (netMHCpan_BA/PRIME/PredIG/IMPROVE 的 _max + fusion geomean/powmean/mean_rank/
    maxrank, fusion 用 4 工具零选择 max 维经 _official_common.apply_fusion 病人内 rank 融合)。
  · AUPRC = sklearn.metrics.average_precision_score; AUROC = roc_auc_score。130 肽为单位, 不分病人。
  · bootstrap-over-peptides 95%CI: 1000 次有放回重采样 130 肽, seed = np.random.default_rng(42)。
    单类别的重采样 (罕见, 平衡标签下几乎不发生) 剔出。
  · 配对 bootstrap ΔAUPRC (同 130 肽重采样, 共同非缺子集上配对): 三对——
      [关键对照 O4] fusion_geomean vs netMHCpan_BA (整合 vs 最强单; 持平=「整合≈最强单」自洽),
      netMHCpan_BA vs PredIG (单 vs 单), fusion_geomean vs fusion_maxrank (最强融合 vs 最弱融合)。
    headline p 引 primary(平衡标签 pval<0.05, ≈76/54); Elispot>0 版 role=sensitivity (12 阴不可靠)。

━━━ 输出 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  · S1_peptide_auprc.csv        —— method, label_kind, AUPRC, AUROC, CI_lo/hi (各指标), n_pos/n_neg。
  · S1_peptide_auprc_paired.csv —— 配对 ΔAUPRC 点估 + 95%CI + 跨 0 比例 (双侧近似 p)。
  · stdout 打印全表 + caveat。

━━━ 跑法 (主线跑, 本脚本不自跑) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  python analysis/official/S1_peptide_level_auprc.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# 复用官方引擎 (同目录): 冻结表路径 / 融合 / 圆整。
from _official_common import (
    FROZEN_POOLED, apply_fusion, ensure_out_dir, load_frozen, pool_col, r6,
)

# Windows 必要: UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent                  # analysis/official/
ROOT = HERE.parents[1]                                  # QuantImmuBench/ (official→analysis→QuantImmuBench)
OFFICIAL_XLSX = (ROOT / "data" / "OFFICIAL_DO_NOT_TOUCH"
                 / "ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx")
SHEET = "In Vitro"
PVALUE_COL = "Ttest_pvalue_InVitroStim"     # 官方列名 (静态核过 sharedStrings 确认存在)
PVAL_THRESH = 0.05                          # <0.05 = 免疫原阳性 (TESLA/IMPROVE 惯用门)

# 单工具副指标用零选择 max 维 (headline 口径, 不 in-sample 挑 pooling)。
SINGLE_TOOLS = ["netMHCpan_BA", "PRIME", "PredIG", "IMPROVE"]
# fusion 输入 = 上述 4 工具的 max 维 (零选择)。
FUSION_TOOLS_MAX = [f"{t}_max" for t in SINGLE_TOOLS]
# fusion 法: apply_fusion 的方法名 -> 展示名 ('max' 融合与 pooling 'max' 重名, 展示叫 maxrank)。
FUSION_METHODS = {
    "geomean": "fusion_geomean",
    "powmean": "fusion_powmean",
    "mean_rank": "fusion_mean_rank",
    "max": "fusion_maxrank",
}

# 配对 ΔAUPRC 对比 (展示名): 看肽级是否比 per-patient 更可分。
PAIRED_COMPARISONS = [
    # ★ 关键对照 (O4): 整合 (geomean 融合) vs 最强单工具 (netMHCpan_BA_max)。大概率持平/微差,
    #   与本文「整合 ≈ 最强单」claim 自洽 —— 若融合肽级也打不过最强单, 支撑「不做 fusion 收益」。
    ("fusion_geomean", "netMHCpan_BA"),
    ("netMHCpan_BA", "PredIG"),            # 单工具 vs 单工具 (SOTA 单 vs 代表性单)
    ("fusion_geomean", "fusion_maxrank"),  # 融合法 vs 融合法 (geomean 最强 vs maxrank 最弱)
]

N_BOOT = 1000
SEED = 42

# [O4] label 角色标注: 平衡标签 (pval<0.05, ≈76阳/54阴) = headline 主口径; SFC>0 (118阳/12阴,
#   12 阴近天花板、极不平衡不可靠) 降为敏感性旁证。headline p 一律引 primary 行, 别引 sensitivity。
LABEL_ROLE = {"pval<0.05": "primary(headline)", "Elispot>0": "sensitivity"}

# DTU 受限工具 (netMHCpan_BA 属之): 结果照常算, 标 pending_DTU_consent。
DTU_NOTE = "netMHCpan_BA 属 DTU 受限工具 (pending_DTU_consent), 结果照常算仅内部用。"


# ═══════════════════════════════════════════════════════════════════════════════
# 标签构建 (从官方 xlsx, 只读)
# ═══════════════════════════════════════════════════════════════════════════════

def load_binary_labels():
    """读官方 xlsx 'In Vitro' sheet, 构建二分免疫原标签, 按 mut_key 返回。
    label_pval = (Ttest_pvalue_InVitroStim < 0.05) 主标签; pval NaN -> label NaN (drop)。
    返回 DataFrame[mut_key, pval, label_pval]。fail-loud: 缺列/缺 sheet 直接停 (不臆造)。
    """
    if not OFFICIAL_XLSX.exists():
        sys.exit(f"[ERR] 官方 xlsx 不存在: {OFFICIAL_XLSX}")
    lab = pd.read_excel(OFFICIAL_XLSX, sheet_name=SHEET, engine="openpyxl")
    for c in ("Patient_ID", "Peptide_ID", PVALUE_COL):
        if c not in lab.columns:
            sys.exit(f"[ERR] xlsx 'In Vitro' sheet 缺列 {c}; 实际列: {list(lab.columns)}")
    lab["Patient_ID"] = lab["Patient_ID"].astype(int)
    lab["Peptide_ID"] = lab["Peptide_ID"].astype(str)
    lab["mut_key"] = lab["Patient_ID"].astype(str) + "|" + lab["Peptide_ID"]
    pval = pd.to_numeric(lab[PVALUE_COL], errors="coerce")
    label = pd.Series(np.where(pval.notna(), (pval < PVAL_THRESH).astype(float), np.nan),
                      index=lab.index)
    return pd.DataFrame({"mut_key": lab["mut_key"].values,
                         "pval": pval.values,
                         "label_pval": label.values})


def attach_labels(df):
    """把二分标签 (pval<0.05) 与敏感性标签 (Elispot>0) 挂到 pooled 表, 打印分布。"""
    labdf = load_binary_labels()
    merged = df.merge(labdf, on="mut_key", how="left")
    if len(merged) != len(df):
        sys.exit(f"[ERR] join 后行数变化 {len(df)}->{len(merged)} (mut_key 非一对一)")

    # 主标签分布
    lp = merged["label_pval"]
    n_pos = int((lp == 1).sum()); n_neg = int((lp == 0).sum()); n_nan = int(lp.isna().sum())
    print(f"[label:pval<0.05] 阳={n_pos} 阴={n_neg} 缺={n_nan} (来源 {PVALUE_COL}, 官方 xlsx In Vitro)")
    matched = int(merged["pval"].notna().sum())
    print(f"[label:join] pooled 130 肽中 {matched} 肽匹配到 pvalue (未匹配 {len(merged)-matched})")

    # 敏感性标签 = Elispot>0 (退化 118/12)
    sfc = pd.to_numeric(merged["Elispot"], errors="coerce")
    merged["label_sfc"] = np.where(sfc.notna(), (sfc > 0).astype(float), np.nan)
    s_pos = int((merged["label_sfc"] == 1).sum()); s_neg = int((merged["label_sfc"] == 0).sum())
    print(f"[label:Elispot>0] 阳={s_pos} 阴={s_neg} (敏感性版, 极不平衡, 仅旁证)")
    return merged


# ═══════════════════════════════════════════════════════════════════════════════
# method 分数向量 (单工具 max 维 / fusion 融合分)
# ═══════════════════════════════════════════════════════════════════════════════

def build_method_scores(df):
    """返回 {method_name: np.array(分数, 对齐 df 行)}。分数原样 (不翻转), higher=更免疫原。"""
    scores = {}
    for t in SINGLE_TOOLS:
        col = pool_col(t, "max")
        if col not in df.columns:
            sys.exit(f"[ERR] 缺工具 max 列: {col}")
        scores[t] = df[col].values.astype(float)
    # fusion: 4 工具 max 维经 apply_fusion 病人内 rank 融合 (leak-free)
    for meth, name in FUSION_METHODS.items():
        fused = apply_fusion(df, FUSION_TOOLS_MAX, meth)
        scores[name] = np.asarray(fused.values, dtype=float)
    return scores


# ═══════════════════════════════════════════════════════════════════════════════
# 指标 + bootstrap (sklearn.metrics; 禁 scipy.stats)
# ═══════════════════════════════════════════════════════════════════════════════

def _metrics(y, s):
    """(AUPRC, AUROC) on 已对齐非缺 y/s; 单类别 -> (nan, nan)。"""
    from sklearn.metrics import average_precision_score, roc_auc_score
    if len(np.unique(y)) < 2:
        return np.nan, np.nan
    return float(average_precision_score(y, s)), float(roc_auc_score(y, s))


def eval_method(y_all, s_all, rng):
    """单 method: 点估 AUPRC/AUROC + bootstrap-over-peptides 95%CI。
    y_all/s_all = 全 130 对齐向量 (含 NaN); 先取二者非缺子集, 再重采样该子集。
    返回 dict(AUPRC, AUROC, AUPRC_lo/hi, AUROC_lo/hi, n_pos, n_neg, n_used)。
    """
    m = ~(np.isnan(y_all) | np.isnan(s_all))
    y, s = y_all[m], s_all[m]
    n = len(y)
    n_pos = int((y == 1).sum()); n_neg = int((y == 0).sum())
    ap, au = _metrics(y, s)
    boot_ap = np.full(N_BOOT, np.nan); boot_au = np.full(N_BOOT, np.nan)
    if n > 0:
        for b in range(N_BOOT):
            idx = rng.integers(0, n, size=n)          # 有放回重采样肽
            a2, r2 = _metrics(y[idx], s[idx])
            boot_ap[b] = a2; boot_au[b] = r2
    def _ci(arr):
        v = arr[~np.isnan(arr)]
        if len(v) == 0:
            return np.nan, np.nan
        return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))
    ap_lo, ap_hi = _ci(boot_ap); au_lo, au_hi = _ci(boot_au)
    return dict(AUPRC=ap, AUROC=au, AUPRC_lo=ap_lo, AUPRC_hi=ap_hi,
                AUROC_lo=au_lo, AUROC_hi=au_hi, n_pos=n_pos, n_neg=n_neg, n_used=n)


def paired_delta_auprc(y_all, s_a, s_b, rng):
    """配对 ΔAUPRC = AUPRC(A) - AUPRC(B), 同肽重采样 95%CI + 跨 0 比例 (双侧近似 p)。
    共同非缺子集 (A/B/label 三者非缺) 上配对重采样, 保证同一批肽比两法。
    返回 dict(delta, ci_lo, ci_hi, p_cross0, n_used, AUPRC_a, AUPRC_b)。
    """
    m = ~(np.isnan(y_all) | np.isnan(s_a) | np.isnan(s_b))
    y, a, b = y_all[m], s_a[m], s_b[m]
    n = len(y)
    ap_a, _ = _metrics(y, a); ap_b, _ = _metrics(y, b)
    delta = ap_a - ap_b if not (np.isnan(ap_a) or np.isnan(ap_b)) else np.nan
    boot = np.full(N_BOOT, np.nan)
    if n > 0:
        for i in range(N_BOOT):
            idx = rng.integers(0, n, size=n)
            aa, _ = _metrics(y[idx], a[idx]); bb, _ = _metrics(y[idx], b[idx])
            if not (np.isnan(aa) or np.isnan(bb)):
                boot[i] = aa - bb
    v = boot[~np.isnan(boot)]
    if len(v) == 0:
        return dict(delta=delta, ci_lo=np.nan, ci_hi=np.nan, p_cross0=np.nan,
                    n_used=n, AUPRC_a=ap_a, AUPRC_b=ap_b)
    ci_lo = float(np.percentile(v, 2.5)); ci_hi = float(np.percentile(v, 97.5))
    # 双侧近似 p = 2 * min(P(Δ*<=0), P(Δ*>=0)), 截到 [0,1]
    p = 2.0 * min(float(np.mean(v <= 0)), float(np.mean(v >= 0)))
    p = min(p, 1.0)
    return dict(delta=delta, ci_lo=ci_lo, ci_hi=ci_hi, p_cross0=p,
                n_used=n, AUPRC_a=ap_a, AUPRC_b=ap_b)


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════

def run_label(df, scores, label_col, label_kind):
    """对某套标签跑全 method + 配对。返回 (per_method_rows, paired_rows)。"""
    role = LABEL_ROLE.get(label_kind, label_kind)   # [O4] primary(headline) / sensitivity
    y_all = df[label_col].values.astype(float)
    rng = np.random.default_rng(SEED)
    rows = []
    for name, s in scores.items():
        r = eval_method(y_all, s, rng)
        r.update(method=name, label_kind=label_kind, role=role)
        rows.append(r)
    # 配对 (每对独立固定 seed, 复现)
    prows = []
    for a, b in PAIRED_COMPARISONS:
        if a not in scores or b not in scores:
            continue
        rng_p = np.random.default_rng(SEED)
        d = paired_delta_auprc(y_all, scores[a], scores[b], rng_p)
        d.update(method_a=a, method_b=b, label_kind=label_kind, role=role)
        prows.append(d)
    return rows, prows


def main():
    out_dir = ensure_out_dir()
    print(f"[info] 读 pooled 干净表 (只读): {FROZEN_POOLED}")
    df = load_frozen(FROZEN_POOLED)
    print(f"[info] pooled shape={df.shape}")
    print(f"[note] {DTU_NOTE}")

    df = attach_labels(df)
    scores = build_method_scores(df)

    all_rows, all_paired = [], []
    for label_col, kind in [("label_pval", "pval<0.05"), ("label_sfc", "Elispot>0")]:
        rows, prows = run_label(df, scores, label_col, kind)
        all_rows.extend(rows); all_paired.extend(prows)

    # ── 写主表 ────────────────────────────────────────────────────────────────
    cols = ["method", "label_kind", "role", "AUPRC", "AUPRC_lo", "AUPRC_hi",
            "AUROC", "AUROC_lo", "AUROC_hi", "n_pos", "n_neg", "n_used"]
    out = pd.DataFrame(all_rows)[cols].copy()
    for c in ("AUPRC", "AUPRC_lo", "AUPRC_hi", "AUROC", "AUROC_lo", "AUROC_hi"):
        out[c] = out[c].map(lambda v: r6(v, 4))
    out_csv = out_dir / "S1_peptide_auprc.csv"
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        f.write("# S1_peptide_auprc.csv — 肽级 AUPRC/AUROC 副主指标 (B3, TESLA/IMPROVE 口径)\n")
        f.write("# estimand caveat: 130 肽当一个池子, 混病人内/间信号, 忽略病人结构;\n")
        f.write("#   与 per-patient Spearman 主指标【并列不替换】(Spearman 才是 headline)。\n")
        f.write(f"# role: primary(headline) = 平衡标签 {PVALUE_COL}<{PVAL_THRESH} (≈76阳/54阴, headline 引这行);\n")
        f.write("#       sensitivity = Elispot>0 (118阳/12阴, 12 阴近天花板不可靠, 仅旁证, 别当 headline)。\n")
        f.write("# 分数原样 (higher=更免疫原, 同 R1-R9), 不 in-sample 翻转; bootstrap 1000× seed=42。\n")
        out.to_csv(f, index=False)
    print(f"\n[saved] {out_csv}")

    # ── 写配对表 ──────────────────────────────────────────────────────────────
    pdf = pd.DataFrame(all_paired)
    pcols = ["method_a", "method_b", "label_kind", "role", "AUPRC_a", "AUPRC_b",
             "delta", "ci_lo", "ci_hi", "p_cross0", "n_used"]
    pdf = pdf[pcols].copy()
    for c in ("AUPRC_a", "AUPRC_b", "delta", "ci_lo", "ci_hi", "p_cross0"):
        pdf[c] = pdf[c].map(lambda v: r6(v, 4))
    pout_csv = out_dir / "S1_peptide_auprc_paired.csv"
    with open(pout_csv, "w", encoding="utf-8", newline="") as f:
        f.write("# S1_peptide_auprc_paired.csv — 配对 ΔAUPRC (同 130 肽 bootstrap, seed=42)\n")
        f.write("# delta = AUPRC(method_a) - AUPRC(method_b); p_cross0 = 双侧近似 (Δ* 跨 0 比例×2)。\n")
        f.write("# role=primary(headline) 行引 headline p (平衡标签 pval<0.05); role=sensitivity (Elispot>0)\n")
        f.write("#   仅敏感性旁证 (12 阴近天花板不可靠), 别当 headline。关键对照 = fusion_geomean vs\n")
        f.write("#   netMHCpan_BA (整合 vs 最强单, 持平即支撑「整合≈最强单」)。\n")
        pdf.to_csv(f, index=False)
    print(f"[saved] {pout_csv}")

    # ── 打印 ──────────────────────────────────────────────────────────────────
    print("\n" + "=" * 78)
    print("肽级 AUPRC / AUROC (副主指标, 与 per-patient Spearman 并列不替换)")
    print("=" * 78)
    with pd.option_context("display.width", 160, "display.max_columns", 20):
        print(out.to_string(index=False))
    print("\n配对 ΔAUPRC:")
    with pd.option_context("display.width", 160, "display.max_columns", 20):
        print(pdf.to_string(index=False))
    print("\n[caveat] AUPRC 混病人内/间信号 (忽略病人结构), 便于与 TESLA/IMPROVE 文献横比;")
    print("         本文 headline 仍是 per-patient Spearman。二者并列呈现。")
    print("[O4] headline p 引 role=primary(平衡标签 pval<0.05); role=sensitivity(Elispot>0, 12阴")
    print("     近天花板不可靠) 仅旁证。关键配对 = fusion_geomean vs netMHCpan_BA (整合 vs 最强单)。")
    print("[DONE] S1_peptide_level_auprc 完成")


if __name__ == "__main__":
    main()
