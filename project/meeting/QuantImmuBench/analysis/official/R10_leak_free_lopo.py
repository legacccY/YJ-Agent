#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R10_leak_free_lopo.py
=====================
服务: QuantImmuBench §3.3 集成框架 / C2 融合负检验 (预期 NULL)。
对应冻结判据: PREREG_R10_featfusion.md §7 (leak-free LOPO 协议) + §5 (二元标签)。

做什么:
  读 R10_feature_builder.py 产的分层特征 + manifest, 对每层 (L0..L4, covariate_only) × 每模型
  (M1 logistic 主 / M2 浅 RF 副) × 每标签口径 (pval<0.05 主 / Elispot>0 敏感性), 跑手写 9-fold
  LOPO (留一患者), 拼出 leak-free 的 130 维 OOF 分。输出长表供 R10_eval_dual.py 双指标评测。

━━━ 🔒 leak-free 命门 (PREREG §7, 逐 fold) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  留一患者 p 为 test, 其余 8 患者为 train:
  ① 患者内无标签归一化 (min-shift+RMS): 每特征在每患者内独立归一 (x-min)/RMS, **只用该患者
     自身特征、无标签** → 对 test 患者也 leak-free。RMS=0(常量列) → 该患者该列置 0。
     ★ 这一步对全部患者独立做, 是「去患者基线」的两套变换之一 (与②不同套)。
  ② 训练折标准化器: mean/std **只在 8 训练患者** fit, transform 测试患者 (与①两套)。
  ③ 缺失填充: 用**训练折均值** (test 亦用训练折均值填, 不看 test 分布)。
  ④ 模型只在 8 患者 fit, 预测留出患者。9 折拼 OOF (index 对齐 mut_key)。
  ⑤ nested inner-LOPO 选 C: 在 8 训练患者内部再 LOPO 网格选超参 → 完全不碰外层 test 患者。
  → 任何跨折统计都只来自 train 患者, test 患者标签/分布从不进入任何拟合, 严格无泄漏。

━━━ 模型 (PREREG §7) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  M1 logistic (主, confirmatory 用): LogisticRegression(penalty='l2', solver='liblinear'),
     C 由 nested inner-LOPO 网格 [0.01,0.03,0.1,0.3,1] 选 (内层 per-patient ρ̄ 最高的 C),
     确定性无 seed。
  M2 浅 RF (副, exploratory): RandomForestClassifier(max_depth=3, n_estimators=100,
     min_samples_leaf=5), seed{1,2,3,4,5} 各跑一遍 (eval 端报均值±std)。参数 a-priori 固定。
  禁 deep gbdt / MLP。

━━━ 标签 (PREREG §5; 复用 S1 口径) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  主 = Ttest_pvalue_InVitroStim < 0.05 (xlsx 'In Vitro' sheet, ≈76阳/54阴)。
  敏感性 = Elispot SFC > 0 (≈118阳/12阴, 仅旁证)。训练用二元标签; 主指标评测另用 Elispot 连续值。
  --shuffle: 患者内打乱二元训练标签 (防泄漏对照, 期望 OOF per-patient ρ̄≈0 / AUPRC 塌 prevalence)。

━━━ 输入 (只读) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  R10_featfusion_features.csv + R10_featfusion_manifest.json (先跑 R10_feature_builder.py)
  data/OFFICIAL_DO_NOT_TOUCH/ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx ('In Vitro' sheet)
  data/frozen/pooled_clean_9mer.csv (取 peplen 供 eval; 此处只透传 Patient_ID/Elispot 已在特征表)

━━━ 输出 (analysis/official/) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  R10_featfusion_oof.csv          (正常标签; 长表 mut_key,Patient_ID,layer,model,label_kind,seed,oof)
  R10_featfusion_oof_shuffle.csv  (--shuffle 时; 同结构)

━━━ 跑法 (主线跑, 我不跑) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  python analysis/official/R10_leak_free_lopo.py
  python analysis/official/R10_leak_free_lopo.py --shuffle

Windows 规范: UTF-8 stdout, pathlib, 纯 numpy/pandas + sklearn; 纯 numpy Spearman(禁 scipy.stats)。
"""

import sys
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _official_common import (                              # noqa: E402
    spearman_np, fisherz_weighted_agg, present_patients, ensure_out_dir,
    FROZEN_POOLED, MIN_PEP,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OFFICIAL_XLSX = (ROOT / "data" / "OFFICIAL_DO_NOT_TOUCH"
                 / "ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx")
SHEET = "In Vitro"
PVALUE_COL = "Ttest_pvalue_InVitroStim"
PVAL_THRESH = 0.05

FEATURES_CSV = HERE / "R10_featfusion_features.csv"
MANIFEST_JSON = HERE / "R10_featfusion_manifest.json"

LAYERS = ["L0", "L1", "L2", "L3", "L4", "covariate_only"]
C_GRID = [0.01, 0.03, 0.1, 0.3, 1.0]        # nested inner-LOPO logistic C 网格 (PREREG §7)
RF_SEEDS = [1, 2, 3, 4, 5]
RF_PARAMS = dict(max_depth=3, n_estimators=100, min_samples_leaf=5)


# ═══════════════════════════════════════════════════════════════════════════════
# 标签 (复用 S1 口径; 从官方 xlsx 只读)
# ═══════════════════════════════════════════════════════════════════════════════
def load_binary_labels():
    """读官方 xlsx 'In Vitro' sheet → {mut_key: label_pval(0/1/NaN)}。fail-loud 缺列即停。"""
    if not OFFICIAL_XLSX.exists():
        sys.exit(f"[ERR] 官方 xlsx 不存在: {OFFICIAL_XLSX}")
    lab = pd.read_excel(OFFICIAL_XLSX, sheet_name=SHEET, engine="openpyxl")
    for c in ("Patient_ID", "Peptide_ID", PVALUE_COL):
        if c not in lab.columns:
            sys.exit(f"[ERR] xlsx 'In Vitro' 缺列 {c}; 实际: {list(lab.columns)}")
    lab["Patient_ID"] = lab["Patient_ID"].astype(int)
    lab["Peptide_ID"] = lab["Peptide_ID"].astype(str)
    lab["mut_key"] = lab["Patient_ID"].astype(str) + "|" + lab["Peptide_ID"]
    pval = pd.to_numeric(lab[PVALUE_COL], errors="coerce")
    label = np.where(pval.notna(), (pval < PVAL_THRESH).astype(float), np.nan)
    return dict(zip(lab["mut_key"].values, label))


# ═══════════════════════════════════════════════════════════════════════════════
# leak-free 变换 (PREREG §7 ①②③)
# ═══════════════════════════════════════════════════════════════════════════════
def within_patient_normalize(df, feat_cols):
    """① 患者内无标签归一化 (min-shift + RMS)。每特征在每患者内独立: (x-min)/RMS_of_(x-min)。
    只用该患者自身特征值, 无 label → 对 test 患者亦 leak-free。RMS=0(常量) → 置 0。
    返回归一后的新 DataFrame (副本), 不改原表。缺失保持 NaN (交给③训练折均值填)。
    """
    out = df.copy()
    for c in feat_cols:
        vals = out[c].values.astype(float)
        for pat, g in out.groupby("Patient_ID"):
            idx = g.index
            v = vals[out.index.get_indexer(idx)]
            mask = ~np.isnan(v)
            if mask.sum() == 0:
                continue
            shifted = v - np.nanmin(v[mask])            # min-shift → 该患者内 min=0
            rms = np.sqrt(np.nanmean(shifted[mask] ** 2))
            if rms < 1e-12:
                normed = np.where(mask, 0.0, np.nan)    # 常量列 → 0 (无患者内变异)
            else:
                normed = shifted / rms
            vals[out.index.get_indexer(idx)] = normed
        out[c] = vals
    return out


def _standardize_and_impute(Xtr, Xte):
    """②训练折标准化 + ③训练折均值填 (只用 train 统计)。返回 (Xtr_z, Xte_z)。
    先用训练折列均值填两折缺失 (nan→train mean; train 全缺→0), 再用训练折 mean/std 标准化。
    """
    col_mean = np.nanmean(Xtr, axis=0)
    col_mean = np.where(np.isnan(col_mean), 0.0, col_mean)
    Xtr_f = np.where(np.isnan(Xtr), col_mean[None, :], Xtr)
    Xte_f = np.where(np.isnan(Xte), col_mean[None, :], Xte)
    mu = Xtr_f.mean(axis=0)
    sd = Xtr_f.std(axis=0)
    sd[sd < 1e-10] = 1.0
    return (Xtr_f - mu) / sd, (Xte_f - mu) / sd


def _perpat_rho_agg(pred, y_cont, pat_ids, patients, min_pep):
    """逐患者 Spearman(pred, y_cont) → Fisher-z 等权聚合 ρ̄ (内层选 C 用连续 Elispot 评)。"""
    rhos, ns = [], []
    for p in patients:
        mk = pat_ids == p
        n = int(mk.sum())
        if n < min_pep:
            continue
        r = spearman_np(pred[mk], y_cont[mk])
        if not np.isnan(r):
            rhos.append(r); ns.append(n)
    if not rhos:
        return np.nan
    return fisherz_weighted_agg(rhos, ns)[0]


# ═══════════════════════════════════════════════════════════════════════════════
# 单模型 LOPO OOF
# ═══════════════════════════════════════════════════════════════════════════════
def logistic_lopo_oof(dfn, feat_cols, y_bin, y_cont, patients, min_pep):
    """M1 logistic: nested inner-LOPO 选 C 的 9-fold LOPO OOF (确定性无 seed)。
    dfn = 已患者内归一化后的表; y_bin 二元训练标签; y_cont 连续 Elispot (内层选 C 评指标)。
    返回 OOF ndarray (对齐 dfn 行, 未预测行=NaN)。
    """
    from sklearn.linear_model import LogisticRegression
    pat_ids = dfn["Patient_ID"].values.astype(int)
    X_all = dfn[feat_cols].values.astype(float)
    oof = np.full(len(dfn), np.nan)

    for p_out in patients:
        outer_test = pat_ids == p_out
        outer_train = ~outer_test & np.isin(pat_ids, patients)
        inner_pats = [q for q in patients if q != p_out]

        # ── 内层 nested-LOPO 选 C ──────────────────────────────────────────────
        best_C, best_score = C_GRID[0], -np.inf
        for C in C_GRID:
            inner_pred = np.full(len(dfn), np.nan)
            for q in inner_pats:
                inn_test = pat_ids == q
                inn_train = np.isin(pat_ids, [r for r in inner_pats if r != q])
                yb = y_bin[inn_train]
                if len(np.unique(yb[~np.isnan(yb)])) < 2:
                    continue                          # 训练折单类 → 跳过该内折
                Xtr_z, Xte_z = _standardize_and_impute(X_all[inn_train], X_all[inn_test])
                m2 = ~np.isnan(yb)
                if m2.sum() < 3 or len(np.unique(yb[m2])) < 2:
                    continue
                clf = LogisticRegression(penalty="l2", solver="liblinear", C=C, max_iter=1000)
                clf.fit(Xtr_z[m2], yb[m2].astype(int))
                inner_pred[inn_test] = clf.decision_function(Xte_z)
            # 内层 per-patient ρ̄ (vs 连续 Elispot) 评这个 C
            valid = ~np.isnan(inner_pred)
            if valid.sum() == 0:
                continue
            score = _perpat_rho_agg(inner_pred[valid], y_cont[valid],
                                    pat_ids[valid], inner_pats, min_pep)
            if not np.isnan(score) and score > best_score:
                best_score, best_C = score, C

        # ── 外层: 用 best_C 训 8 患者, 预测留出患者 ─────────────────────────────
        yb = y_bin[outer_train]
        m2 = ~np.isnan(yb)
        if m2.sum() < 3 or len(np.unique(yb[m2])) < 2:
            continue
        Xtr_z, Xte_z = _standardize_and_impute(X_all[outer_train], X_all[outer_test])
        clf = LogisticRegression(penalty="l2", solver="liblinear", C=best_C, max_iter=1000)
        clf.fit(Xtr_z[m2], yb[m2].astype(int))
        oof[outer_test] = clf.decision_function(Xte_z)
    return oof


def rf_lopo_oof(dfn, feat_cols, y_bin, patients, seed):
    """M2 浅 RF: 固定参数 9-fold LOPO OOF (给定 seed)。OOF = 阳性类概率 (predict_proba[:,1])。"""
    from sklearn.ensemble import RandomForestClassifier
    pat_ids = dfn["Patient_ID"].values.astype(int)
    X_all = dfn[feat_cols].values.astype(float)
    oof = np.full(len(dfn), np.nan)
    for p_out in patients:
        outer_test = pat_ids == p_out
        outer_train = (~outer_test) & np.isin(pat_ids, patients)
        yb = y_bin[outer_train]
        m2 = ~np.isnan(yb)
        if m2.sum() < 3 or len(np.unique(yb[m2])) < 2:
            continue
        Xtr_z, Xte_z = _standardize_and_impute(X_all[outer_train], X_all[outer_test])
        clf = RandomForestClassifier(random_state=seed, n_jobs=1, **RF_PARAMS)
        clf.fit(Xtr_z[m2], yb[m2].astype(int))
        proba = clf.predict_proba(Xte_z)
        # 取阳性类(标签 1)概率列
        pos_idx = list(clf.classes_).index(1) if 1 in clf.classes_ else -1
        oof[outer_test] = proba[:, pos_idx] if pos_idx >= 0 else np.nan
    return oof


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(
        description="R10 leak-free LOPO 学习融合 OOF (§3.3 融合负检验)")
    ap.add_argument("--features", default=str(FEATURES_CSV))
    ap.add_argument("--manifest", default=str(MANIFEST_JSON))
    ap.add_argument("--min_pep", type=int, default=MIN_PEP)
    ap.add_argument("--shuffle", action="store_true",
                    help="患者内打乱二元训练标签 (防泄漏对照; 期望 OOF ρ̄≈0)")
    ap.add_argument("--shuffle_seed", type=int, default=42)
    args = ap.parse_args()

    fp, mp = Path(args.features), Path(args.manifest)
    if not fp.exists() or not mp.exists():
        sys.exit(f"[ERR] 先跑 R10_feature_builder.py; 缺 {fp.name}/{mp.name}")
    df = pd.read_csv(fp, comment="#", encoding="utf-8").reset_index(drop=True)
    manifest = json.loads(mp.read_text(encoding="utf-8"))
    layers_map = dict(manifest["layers"])
    layers_map["covariate_only"] = manifest["covariate_only"]

    df["Patient_ID"] = df["Patient_ID"].astype(int)
    patients = present_patients(df)
    y_cont = pd.to_numeric(df["Elispot"], errors="coerce").values.astype(float)

    # ── 二元训练标签 ───────────────────────────────────────────────────────────
    lab_map = load_binary_labels()
    y_pval = np.array([lab_map.get(mk, np.nan) for mk in df["mut_key"].values], float)
    sfc = pd.to_numeric(df["Elispot"], errors="coerce").values.astype(float)
    y_sfc = np.where(~np.isnan(sfc), (sfc > 0).astype(float), np.nan)
    label_sets = {"pval<0.05": y_pval, "Elispot>0": y_sfc}
    for k, yy in label_sets.items():
        print(f"[label:{k}] 阳={int(np.nansum(yy==1))} 阴={int(np.nansum(yy==0))} "
              f"缺={int(np.isnan(yy).sum())}")

    rng = np.random.default_rng(args.shuffle_seed)
    if args.shuffle:
        print(f"[shuffle] 患者内打乱二元标签 (seed={args.shuffle_seed}); 期望 OOF ρ̄≈0")
        for k in label_sets:
            yy = label_sets[k].copy()
            for p in patients:
                mk = df["Patient_ID"].values == p
                idx = np.where(mk)[0]
                sub = yy[idx]
                valid = ~np.isnan(sub)
                perm = sub.copy()
                perm[valid] = rng.permutation(sub[valid])   # 只在非缺内打乱
                yy[idx] = perm
            label_sets[k] = yy

    # ── 逐层 × 模型 × 标签 跑 LOPO ─────────────────────────────────────────────
    rows = []
    for layer in LAYERS:
        feat_cols = [c for c in layers_map[layer] if c in df.columns]
        if not feat_cols:
            print(f"[warn] {layer} 无有效特征列, 跳过")
            continue
        dfn = within_patient_normalize(df, feat_cols)       # ① 患者内归一化 (全患者独立)
        print(f"\n[{layer}] {len(feat_cols)} 维: {feat_cols}")
        for label_kind, y_bin in label_sets.items():
            if len(np.unique(y_bin[~np.isnan(y_bin)])) < 2:
                print(f"  [warn] {label_kind} 单类, 跳过")
                continue
            # M1 logistic (确定性, seed=-1 占位)
            oof_lg = logistic_lopo_oof(dfn, feat_cols, y_bin, y_cont, patients, args.min_pep)
            for i, mk in enumerate(df["mut_key"].values):
                if not np.isnan(oof_lg[i]):
                    rows.append(dict(mut_key=mk, Patient_ID=int(df["Patient_ID"].iloc[i]),
                                     layer=layer, model="logistic", label_kind=label_kind,
                                     seed=-1, oof=float(oof_lg[i])))
            n_lg = int((~np.isnan(oof_lg)).sum())
            # M2 RF (5 seeds)
            n_rf = 0
            for s in RF_SEEDS:
                oof_rf = rf_lopo_oof(dfn, feat_cols, y_bin, patients, s)
                for i, mk in enumerate(df["mut_key"].values):
                    if not np.isnan(oof_rf[i]):
                        rows.append(dict(mut_key=mk, Patient_ID=int(df["Patient_ID"].iloc[i]),
                                         layer=layer, model="rf", label_kind=label_kind,
                                         seed=s, oof=float(oof_rf[i])))
                n_rf = int((~np.isnan(oof_rf)).sum())
            print(f"  [{label_kind}] logistic OOF={n_lg}/{len(df)}; rf OOF={n_rf}/{len(df)}×{len(RF_SEEDS)}seed")

    if not rows:
        sys.exit("[ERR] 无 OOF 产出")
    out_df = pd.DataFrame(rows)
    out_dir = ensure_out_dir()
    suffix = "_shuffle" if args.shuffle else ""
    out_csv = out_dir / f"R10_featfusion_oof{suffix}.csv"
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        f.write("# R10_featfusion_oof.csv — leak-free LOPO 学习融合 OOF (§3.3 融合负检验)\n")
        f.write("# 长表: mut_key,Patient_ID,layer,model,label_kind,seed,oof。model=logistic(seed=-1 确定性)|rf(seed 1-5)。\n")
        f.write("# leak-free: 患者内归一化(无标签)+训练折标准化/填充/选C 全不碰 test 患者(PREREG §7)。\n")
        if args.shuffle:
            f.write("# ★ SHUFFLE 版: 患者内打乱二元训练标签, 期望 per-patient ρ̄≈0 / AUPRC 塌 prevalence。\n")
        out_df.to_csv(f, index=False)
    print(f"\n[saved] {out_csv}  rows={len(out_df)}")
    print("[DONE] R10_leak_free_lopo" + (" (shuffle)" if args.shuffle else ""))


if __name__ == "__main__":
    main()
