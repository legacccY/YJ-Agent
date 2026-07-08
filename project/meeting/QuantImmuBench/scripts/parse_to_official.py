"""
parse_to_official.py — QuantImmuBench 改动②/③ 重跑：raw → bb_idx official 适配器
服务项目：quantimmu-bench §改动②/③ 全量重跑 lever=slice_presml 落 out_rerun_official/

功能：
  把某工具的 raw 打分（peptide[+HLA]→score）回贴到 master_backbone_official.csv 的
  逐 bb_idx 行，产出对齐旧 out_official schema 的 <Tool>_official.csv：
    bb_idx, MT_<col>[, WT_<col>]   （MHCflurry 有 presentation + affinity_neg 两列组）

  master_backbone_official.csv 每行 = 一个 (bb_idx) 打分格子，含 MT_Subpeptide /
  WT_Subpeptide / HLA_Allele。对每行：
    MT 分 = raw_lookup[(MT_Subpeptide, HLA)]（HLA-agnostic 工具忽略 HLA）
    WT 分 = raw_lookup[(WT_Subpeptide, HLA)]
  缺失 → 空（NaN），与旧 official 一致。

方向归一（见各工具 NOTES）：
  direct  = 原值直接用（越高越强）
  neg     = 取负（原值越低越强，如 affinity/ic50）

用法：
  python parse_to_official.py --tool TransHLA \
      --raw HPC/deploy/transhla/transhla_raw.csv \
      --backbone scripts/out_rerun/master_backbone_official.csv \
      --out scripts/out_rerun_official/TransHLA_official.csv
"""

import argparse
import pathlib
import sys

import pandas as pd


# ---------------------------------------------------------------------------
# 各工具规格：raw 列名 + 是否 HLA-aware + 输出列组（对齐旧 out_official）
#   value_specs: [(输出后缀, raw 列, 变换)]  变换 ∈ {direct, neg}
# ---------------------------------------------------------------------------
TOOL_SPECS = {
    "TransHLA": {
        "hla_aware": False,
        "pep_col": "peptide",
        "value_specs": [("MT_TransHLA", "WT_TransHLA", "prob", "direct")],
    },
    "MHCnuggets": {
        "hla_aware": True,
        "pep_col": "peptide",
        "hla_col": "HLA_Allele",
        "value_specs": [("MT_MHCnuggets", "WT_MHCnuggets", "ic50", "neg")],
    },
    "MHCSeqNet": {
        "hla_aware": True,
        "pep_col": "peptide",
        "hla_col": "HLA_Allele",
        "value_specs": [("MT_MHCSeqNet", "WT_MHCSeqNet", "prob", "direct")],
    },
    "HLAthena": {
        "hla_aware": True,
        "pep_col": "peptide",
        "hla_col": "HLA_Allele",
        # 旧 official 列名 = MT_HLAthena / WT_HLAthena；raw 列 = MSi（presentation）
        "value_specs": [("MT_HLAthena", "WT_HLAthena", "MSi", "direct")],
    },
    "MHCflurry": {
        "hla_aware": True,
        "pep_col": "peptide",
        "hla_col": "HLA_Allele",
        "value_specs": [
            ("MT_MHCflurry_presentation", "WT_MHCflurry_presentation", "presentation_score", "direct"),
            ("MT_MHCflurry_affinity_neg", "WT_MHCflurry_affinity_neg", "affinity", "neg"),
        ],
    },
}


def norm_hla(hla: str) -> str:
    """归一 HLA 键：去星号 + 去空白（兼容 raw 带/不带星号）。"""
    return str(hla).strip().replace("*", "")


def transform(val, kind):
    if pd.isna(val):
        return float("nan")
    return -float(val) if kind == "neg" else float(val)


def build_lookup(raw_df, spec):
    """建 raw 查找表：HLA-aware → (pep, hla_nostar)→row；agnostic → pep→row。"""
    pep_col = spec["pep_col"]
    aware = spec["hla_aware"]
    lookup = {}
    n_dup = 0
    for _, r in raw_df.iterrows():
        pep = str(r[pep_col]).strip()
        if aware:
            key = (pep, norm_hla(r[spec["hla_col"]]))
        else:
            key = pep
        if key in lookup:
            n_dup += 1
            continue
        lookup[key] = r
    return lookup, n_dup


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", required=True, choices=list(TOOL_SPECS))
    ap.add_argument("--raw", required=True)
    ap.add_argument("--backbone", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec = TOOL_SPECS[args.tool]
    raw_path = pathlib.Path(args.raw)
    bb_path = pathlib.Path(args.backbone)
    out_path = pathlib.Path(args.out)

    if not raw_path.exists():
        print(f"[official] ERROR: raw 不存在: {raw_path}", file=sys.stderr)
        sys.exit(1)
    if not bb_path.exists():
        print(f"[official] ERROR: backbone 不存在: {bb_path}", file=sys.stderr)
        sys.exit(1)

    raw_df = pd.read_csv(raw_path, encoding="utf-8")
    bb = pd.read_csv(bb_path, encoding="utf-8")
    print(f"[official] {args.tool}: raw {len(raw_df)} 行, backbone {len(bb)} 行")

    lookup, n_dup = build_lookup(raw_df, spec)
    if n_dup:
        print(f"[official] WARNING: raw 有 {n_dup} 个重复键（已取首条）", file=sys.stderr)
    print(f"[official] 查找表条目: {len(lookup)}")

    aware = spec["hla_aware"]
    out = pd.DataFrame({"bb_idx": bb["bb_idx"]})

    def lookup_row(pep, hla):
        pep = str(pep).strip() if pd.notna(pep) else ""
        if not pep or pep.lower() == "nan":
            return None
        key = (pep, norm_hla(hla)) if aware else pep
        return lookup.get(key)

    cov = {}
    for mt_col, wt_col, raw_col, kind in spec["value_specs"]:
        mt_vals, wt_vals = [], []
        for _, row in bb.iterrows():
            mr = lookup_row(row["MT_Subpeptide"], row.get("HLA_Allele"))
            wr = lookup_row(row["WT_Subpeptide"], row.get("HLA_Allele"))
            mt_vals.append(transform(mr[raw_col], kind) if mr is not None else float("nan"))
            wt_vals.append(transform(wr[raw_col], kind) if wr is not None else float("nan"))
        out[mt_col] = mt_vals
        out[wt_col] = wt_vals
        cov[mt_col] = pd.Series(mt_vals).notna().sum()
        cov[wt_col] = pd.Series(wt_vals).notna().sum()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False, encoding="utf-8", lineterminator="\n")

    n = len(out)
    print(f"\n[official] == 覆盖统计 (总 {n} 行) ==")
    for col, c in cov.items():
        print(f"  {col:34s} 非空 {c:5d} ({100*c/n:.1f}%)")
    print(f"\n[official] 写出 → {out_path}")
    if aware:
        print("[official] HLA-aware：按 (肽, HLA去星) 查表。")
    else:
        print("[official] HLA-agnostic：只按肽查表，同肽全 HLA 行同值。")


if __name__ == "__main__":
    main()
