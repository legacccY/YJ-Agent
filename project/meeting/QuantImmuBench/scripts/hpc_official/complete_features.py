# -*- coding: utf-8 -*-
"""
complete_features.py — IMPROVE feature_calc 输出 -> predict 可吃的完整特征表 (档II)
服务: quantimmu-bench Phase0 IMPROVE 档II (lever=IMPROVE)

档II 处理 (用户拍板):
  - Foreigness  → **真算** (run_foreignness.R 的 antigen.garnish 输出, 按 Mut_peptide merge 进来)
  - NetMHCExp / Expression → 官方 predict 自带 mean-impute 的合法处理。
      但这两列对纯肽输入 100% 缺失 → predict 的 batch col.mean()=NaN 会崩,
      故按论文明示的官方 fallback: 用官方参考文件 calculated_features_test.tsv 的列均值预填。
      (论文: "we impute the missing values using the mean ... except expression ... NetMHCpanExp/HPA")
  - Stability → STAB=1 时 feature_calc 已真算 (netMHCstabpan); STAB=0 时全NaN → 同上参考均值 fallback
  - Patient → 补常量 ID (仅分组标识, 非特征)

为什么需要这步: 官方 feature_calc 不产 NetMHCExp/Expression/Foreigness, 也无 Patient 列;
predict 的 Simple 列选择硬要这些, 缺列 KeyError / 全NaN 时 RF.predict_proba 崩。

红线: Foreigness 是真算 (非造); NetMHCExp/Expression 的参考均值 = 论文认可的官方缺失处理 (全程横幅披露), 非逐肽兜底造数。
"""
import sys
import argparse
import warnings
import pandas as pd
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 真算特征 (档II 经 run_foreignness.R 得到, 按肽 merge)
REAL_FEATS = ["Foreigness"]
# 官方 mean-impute 处理的特征 (纯肽 100% 缺 → 参考均值 fallback)
IMPUTE_FEATS = ["NetMHCExp", "Expression"]
# STAB=0 时也全NaN → 参考均值 fallback
MAYBE_ALLNAN = ["Stability"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", required=True, help="feature_calc 输出 tsv")
    ap.add_argument("--ref", required=True, help="官方参考特征 calculated_features_test.tsv (取列均值)")
    ap.add_argument("--out", required=True, help="补全输出 tsv")
    ap.add_argument("--foreignness", default="", help="run_foreignness.R 输出 csv (Mut_peptide,Foreigness); 空=Foreigness 也走参考均值")
    ap.add_argument("--patient", default="elispot", help="Patient 常量 ID")
    args = ap.parse_args()

    df = pd.read_csv(args.infile, sep="\t")
    n = len(df)
    print(f"[complete] 读入 {n} 行, cols={list(df.columns)}")

    # 1. 补 Patient
    if "Patient" not in df.columns:
        df["Patient"] = args.patient
        print(f"[complete] 补 Patient='{args.patient}'")

    # 2. Foreigness: 真算 merge
    foreign_real = False
    if args.foreignness:
        try:
            fdf = pd.read_csv(args.foreignness)
            fdf = fdf.rename(columns={c: "Foreigness" for c in fdf.columns
                                      if c.lower() in ("foreignness", "foreignness_score", "foreigness")})
            fdf = fdf[["Mut_peptide", "Foreigness"]].drop_duplicates("Mut_peptide")
            df = df.merge(fdf, on="Mut_peptide", how="left")
            cov = df["Foreigness"].notna().sum()
            print(f"[complete] Foreigness 真算 merge: {cov}/{len(df)} ({cov/max(len(df),1)*100:.1f}%) 命中 <- {args.foreignness}")
            foreign_real = True
        except Exception as e:
            warnings.warn(f"读 foreignness 失败, 回退参考均值: {e}")

    # 3. 参考均值 (NetMHCExp/Expression + Stability fallback + Foreigness 兜底)
    ref_means = {}
    try:
        ref = pd.read_csv(args.ref, sep="\t")
        for c in IMPUTE_FEATS + MAYBE_ALLNAN + REAL_FEATS:
            if c in ref.columns:
                v = pd.to_numeric(ref[c], errors="coerce").mean()
                if pd.notna(v):
                    ref_means[c] = float(v)
        print(f"[complete] 参考均值 <- {args.ref}: {ref_means}")
    except Exception as e:
        warnings.warn(f"读参考文件失败: {e}")

    banner = []
    # NetMHCExp/Expression: 官方 mean-impute (100% 缺 → 参考均值 fallback)
    for c in IMPUTE_FEATS:
        if c not in df.columns or df[c].isna().all():
            fill = ref_means.get(c, 0.0)
            df[c] = fill
            banner.append(f"  {c:<11} = {fill:.4g}  (官方 mean-impute / 参考均值 fallback; 纯肽不可测)")
    # Stability: STAB=1 真算则跳; 全NaN(STAB=0) → 参考均值
    for c in MAYBE_ALLNAN:
        if c not in df.columns or df[c].isna().all():
            fill = ref_means.get(c, 0.0)
            df[c] = fill
            banner.append(f"  {c:<11} = {fill:.4g}  (STAB=0 跳netMHCstabpan, 参考均值 fallback)")
        else:
            print(f"[complete] Stability 真算保留 (非NaN={df[c].notna().sum()}/{len(df)})")
    # Foreigness 兜底 (真算缺失 / 未提供)
    if "Foreigness" not in df.columns or df["Foreigness"].isna().all():
        fill = ref_means.get("Foreigness", 0.0)
        df["Foreigness"] = fill
        banner.append(f"  Foreigness  = {fill:.4g}  ([!] 真算未提供, 参考均值 fallback — 应跑 run_foreignness.R)")
    elif foreign_real:
        # 真算后零星缺的肽 → 官方 mean-impute (用真算列均值, 不是参考)
        miss = int(df["Foreigness"].isna().sum())
        if miss:
            df["Foreigness"] = df["Foreigness"].fillna(df["Foreigness"].mean())
            print(f"[complete] Foreigness 零星缺 {miss} -> 真算列均值 impute (官方)")

    if banner:
        print("=" * 70)
        print("[!] 以下特征对纯肽输入不可测, 按官方 mean-impute / 参考均值 fallback 处理:")
        print("\n".join(banner))
        print("Foreigness: " + ("[OK] antigen.garnish 真算" if foreign_real else "[!] 参考均值(未真算)"))
        print("=" * 70)

    df.to_csv(args.out, sep="\t", index=False)
    print(f"[complete] 写 {len(df)} 行 -> {args.out}")


if __name__ == "__main__":
    main()
