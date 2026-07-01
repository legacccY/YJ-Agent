#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compute_netAffneg_topk20eq.py
=============================
服务: QuantImmuBench 大纲 §3.2 / §3.4 方案A —— 按袁老师 outline 硬指定参数补算
      netAffneg = netMHCpan_BA 的 top-k 等权池 (k=20, α=0)。

对应 outline (paper/QuanImmu-Paper-Outline.md):
  §2.2「全文主分析用 9AA-only (9mer), 可变窗 8-14mer 入补充」。
  §3.2「netAffneg_9 经 top-20 等权平均 (k=20,α=0) 跃居单工具第一 +0.3946」。
  §3.4 方案A「务实默认: netAffneg_9 topk k=20,α=0」。
  注 outline 名 netAffneg_9 中的「_9」= 9mer 口径, 非全窗。

根因 (为何默认 9mer):
  netMHCpan_BA topk(k=20,α=0) 全窗 8-14mer 上 per-patient Fisher-z 只 ρ̄≈0.263,
  复现不了 outline「跃居单工具第一」的故事; 限 9mer (MT_Subpeptide 长度==9) 后 ρ̄≈0.519,
  才对齐 outline §3.2 netAffneg_9=9mer 的判据。故本脚本 9mer 过滤 **默认 ON**,
  --allwindow 可切回全窗做对照。

裁决背景 (plan 裁决备忘 #3, 以老师计划为准):
  冻结表 `netMHCpan_BA_topk_w` = k=5 inv_rank (≠ outline 的 k=20,α=0)。R8 方案A 此前
  用 netMHCpan_BA_geomean(0.386) 近似。本脚本按 outline 硬指定补算 k=20,α=0 专列，
  不改 sha256 冻结表, 新增派生列文件供 R2/R8 join。

做什么:
  1. 读子肽×HLA 长表 merged_all_tools_30_official.csv (MT_netMHCpan_BA, 已 −Aff 定向)。
  2. 默认过滤 9mer 子肽 (MT_Subpeptide 长度==9; --allwindow 则跳过过滤走全窗对照)。
  3. 按 mut_key (Patient_ID|Peptide_ID) 分组, 对每肽的 netMHCpan_BA 子肽分应用
     pool_topk_w(k=20, weight_scheme="equal") = top-20 等权平均 (复用 p0e 现成算子, 零新造轮子)。
  4. 锚定官方 130 肽 (GT 顺序), 输出派生列文件 netAffneg_topk20eq_official.csv。
  5. 自评: per-patient Fisher-z Spearman (复用 _official_common), 9mer 下预期 ρ̄≈0.519,
     对标 outline +0.3946 (全窗仅 0.263 做对照)。

输入 (只读):
  scripts/out/merged_all_tools_30_official.csv   (子肽×HLA 长表)
  data/frozen/ds2_official_groundtruth.csv       (130 肽锚定 + Elispot 真值)
输出:
  data/frozen/netAffneg_topk20eq_official.csv    (mut_key,Patient_ID,Peptide_ID,Elispot,
                                                  n_subpep_BA, netMHCpan_BA_topk20eq)

朝向核对: MT_netMHCpan_BA 与既有 netMHCpan_BA_* pooled 列同源, 既有 geomean 列 per-patient
  Fisher-z=+0.386 为正 ⇒ 已 −Aff 定向 (越大越免疫原), 直接用不再翻转。

跑法 (主线跑):
  python analysis/official/compute_netAffneg_topk20eq.py               # 9mer 主分析 (默认, 预期 ρ̄≈0.519)
  python analysis/official/compute_netAffneg_topk20eq.py --allwindow   # 全窗 8-14mer 对照 (ρ̄≈0.263)
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent          # analysis/official/
ANALYSIS = HERE.parent                          # analysis/
ROOT = ANALYSIS.parent                          # QuantImmuBench/

# 复用 p0e 现成 pool_topk_w (k=20,α=0=equal) —— 零新造轮子, 与冻结表口径同源
sys.path.insert(0, str(ANALYSIS / "phase0"))
from p0e_pool_to_peptide import pool_topk_w      # noqa: E402
# 复用官方主指标 per-patient Fisher-z 自评
sys.path.insert(0, str(HERE))
from _official_common import per_patient_spearman, present_patients, MIN_PEP  # noqa: E402

LONG_TABLE = ROOT / "scripts" / "out" / "merged_all_tools_30_official.csv"
GT_CSV = ROOT / "data" / "frozen" / "ds2_official_groundtruth.csv"
OUT_CSV = ROOT / "data" / "frozen" / "netAffneg_topk20eq_official.csv"

BA_COL = "MT_netMHCpan_BA"
SUBPEP_COL = "MT_Subpeptide"  # 子肽序列列; 9mer 过滤 = str 长度==9
K, SCHEME = 20, "equal"       # outline 硬指定: k=20, α=0 (等权)
OUT_COL = "netMHCpan_BA_topk20eq"


def main():
    ap = argparse.ArgumentParser(
        description="netAffneg = netMHCpan_BA topk(k=20,α=0); 默认 9mer 主分析 (outline §3.2)")
    ap.add_argument("--allwindow", action="store_true",
                    help="不过滤 9mer, 用全窗 8-14mer 做对照 (ρ̄≈0.263); 默认=9mer 主分析 (ρ̄≈0.519)")
    args = ap.parse_args()
    regime = "全窗 8-14mer" if args.allwindow else "9mer"

    if not LONG_TABLE.exists():
        sys.exit(f"[ERR] 长表不存在: {LONG_TABLE}")
    if not GT_CSV.exists():
        sys.exit(f"[ERR] GT 不存在: {GT_CSV}")

    gt = pd.read_csv(GT_CSV)
    gt["Patient_ID"] = gt["Patient_ID"].astype(int)
    gt["Peptide_ID"] = gt["Peptide_ID"].astype(str)
    gt_keys = gt["mut_key"].tolist()
    assert len(gt_keys) == 130, f"[ERR] GT 锚定肽数={len(gt_keys)} != 130"

    print(f"[info] 读长表: {LONG_TABLE}")
    df = pd.read_csv(LONG_TABLE)
    print(f"[info] 长表 shape={df.shape}; 口径={regime}")
    if BA_COL not in df.columns:
        sys.exit(f"[ERR] 长表缺 {BA_COL} 列")

    # ── 9mer 过滤 (默认, 对齐 outline §3.2 netAffneg_9=9mer) ──────────────────
    if not args.allwindow:
        if SUBPEP_COL not in df.columns:
            sys.exit(f"[ERR] 9mer 主分析需列 {SUBPEP_COL} 判子肽长度, 长表缺该列 (或加 --allwindow)")
        before = len(df)
        df = df[df[SUBPEP_COL].astype(str).str.len() == 9].copy()
        print(f"[info] 9mer 过滤: {before} -> {len(df)} 子肽行 (MT_Subpeptide 长度==9)")
        if df.empty:
            sys.exit("[ERR] 9mer 过滤后长表为空, 检查 MT_Subpeptide 列内容")

    if "mut_key" not in df.columns:
        for req in ("Patient_ID", "Peptide_ID"):
            if req not in df.columns:
                sys.exit(f"[ERR] 长表缺 '{req}' 且无 mut_key")
        df["mut_key"] = (df["Patient_ID"].astype(int).astype(str)
                         + "|" + df["Peptide_ID"].astype(str))

    df[BA_COL] = pd.to_numeric(df[BA_COL], errors="coerce")
    valid = df[df[BA_COL].notna()]
    print(f"[info] netMHCpan_BA 非空子肽行={len(valid)} / 长表 {len(df)}")

    idx = pd.Index(gt_keys, name="mut_key")
    out = gt.set_index("mut_key")[["Patient_ID", "Peptide_ID", "Elispot"]].reindex(idx).copy()

    g = valid.groupby("mut_key")[BA_COL]
    out["n_subpep_BA"] = g.size().reindex(idx).fillna(0).astype(int).values
    pooled = g.agg(lambda a: pool_topk_w(a.values, k=K, weight_scheme=SCHEME))
    out[OUT_COL] = pooled.reindex(idx).round(8).values
    out = out.reset_index()

    assert len(out) == 130, f"[ERR] 行数={len(out)} != 130"
    n_nan = int(out[OUT_COL].isna().sum())
    print(f"[gate] 行数=130 PASS; {OUT_COL} NaN 肽数={n_nan} "
          f"(=netMHCpan_BA 未覆盖肽, 与工具边界一致)")
    print(f"[range] {OUT_COL}: min={out[OUT_COL].min():.4f} "
          f"max={out[OUT_COL].max():.4f} mean={out[OUT_COL].mean():.4f}")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", encoding="utf-8") as f:
        f.write("# netAffneg_topk20eq_official.csv\n")
        f.write("# QuantImmuBench §3.2/§3.4方案A: netMHCpan_BA top-k等权池 k=20,α=0 (outline硬指定)\n")
        f.write(f"# 口径={regime} (默认9mer=outline §3.2 netAffneg_9; --allwindow=全窗对照)\n")
        f.write("# 派生列, 不改sha256冻结表; 源=scripts/out/merged_all_tools_30_official.csv MT_netMHCpan_BA\n")
        f.write(f"# 算子=p0e_pool_to_peptide.pool_topk_w(k={K},weight_scheme='{SCHEME}'); 锚定官方130肽\n")
        out.to_csv(f, index=False)
    print(f"[saved] {OUT_CSV}  shape={out.shape}")

    # ── 自评: per-patient Fisher-z, 对标 outline +0.3946 ──────────────────
    pats = present_patients(out)
    rho_bar, lo, hi, n_used, n_drop = per_patient_spearman(
        out, OUT_COL, patients=pats, min_pep=MIN_PEP)
    print(f"\n[eval] netAffneg topk(k=20,α=0) per-patient Fisher-z ρ̄={rho_bar:+.4f} "
          f"CI=[{lo:+.4f},{hi:+.4f}] n_pat={n_used}(drop{n_drop})")
    print(f"[eval] outline §3.2 声称 +0.3946; 本地实测 {rho_bar:+.4f}; "
          f"Δ={rho_bar - 0.3946:+.4f}")
    print("[DONE] compute_netAffneg_topk20eq")


if __name__ == "__main__":
    main()
