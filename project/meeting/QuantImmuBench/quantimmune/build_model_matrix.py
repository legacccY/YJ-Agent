#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_model_matrix.py
======================
服务: quantimmu-bench F-pilot (QuantImmune 定量原型)
约束对齐: LEDGER §5 约束①②③④⑤⑥⑦⑧⑨ (主要: 防泄漏折内填补 + 预登记死工具剪枝)

输入
----
  scripts/out/merged_all_tools_9tools.xlsx  (9 工具 × 183 肽 × 全 HLA/window 子肽)
  ※ 注意: analysis/plotdata_perpep.csv 仅含 5 工具 + DS2 101 肽, 不满足 9 工具需求,
     本脚本使用 merged_all_tools_9tools.xlsx 作真源。

处理
----
  1. max-agg: 每 Peptide_ID × 工具, 取全部子肽行的最大分数 (Aggregation='max' 口径)
  2. 从 master_backbone join: Patient_ID / Dataset / Peptide_Length /
     MT_FullPeptide / WT_FullPeptide / HLA_Allele / Elispot (first non-null per pep)
  3. 缺失标记: missing_<tool> 布尔列 (折内填补在 lopo_eval.py LOPO 循环内完成)
  4. Tier-1 序列特征 (本地即算, 无需外部服务):
       seq_length         — 全肽长度 (Peptide_Length)
       seq_n_mutations    — MT vs WT Hamming 距离 (错配位点数)
       seq_blosum62_mut_score — BLOSUM62[WT_aa][MT_aa] sum over mismatch positions
                              (agretopicity 代理: 越负 = 越不保守 = 可能更外来)
       seq_mutation_rel_pos   — mean(mutation_positions) / length (相对位置)
       seq_kd_hydro_mt    — MT_FullPeptide Kyte-Doolittle 平均疏水性
       seq_kd_hydro_diff  — KD(MT) - KD(WT) 突变疏水性变化量
       seq_aromatic_mt    — MT_FullPeptide 芳香族残基(F/W/Y)比例
  5. Tier-2 外来度 (foreignness, Łuksza 2017):
       # TODO: Tier-2 需官方实现 (Łuksza 2017 Nat Methods doi:10.1038/nmeth.4279)
       # 本 pilot 只用 Tier-1; 预留接口 seq_foreignness 列(全 NaN 占位)

输出
----
  quantimmune/model_matrix.csv  (183 行 × 特征列)
  列: Peptide_ID, Patient_ID, Dataset, Elispot, HLA_Allele_first,
      Peptide_Length, MT_FullPeptide, WT_FullPeptide,
      [9 工具 max-agg score 列], [missing_<tool> 列], [seq_* 列]

跑法
----
  python quantimmune/build_model_matrix.py
  python quantimmune/build_model_matrix.py --input scripts/out/merged_all_tools_9tools.xlsx

来源引用
--------
  BLOSUM62: Henikoff & Henikoff (1992) PNAS 89:10915-10919
  Kyte-Doolittle: Kyte & Doolittle (1982) J Mol Biol 157:105-132
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_MERGED = ROOT / "scripts" / "out" / "merged_all_tools_9tools.xlsx"
OUT_MATRIX = HERE / "model_matrix.csv"

# ── 9 工具列名映射 (匹配 merged_all_tools_9tools.xlsx) ─────────────────────────
# 死工具 (fisherz ≤ 0.03 @ LEDGER §5 约束⑨): DeepImmuno / NeoTImmuML / HLAthena
TOOL_COLS = {
    "DeepImmuno":  "MT_DeepImmuno",          # dead: signal <= 0.03
    "PredIG":      "MT_PredIG",              # alive
    "IMPROVE":     "MT_IMPROVE_mean_prediction_rf",  # alive (冗余: r=0.69 with PRIME)
    "NeoTImmuML":  "MT_NeoTImmuML",          # dead: signal <= 0.03
    "pTuneos":     "MT_pTuneos",             # alive
    "PRIME":       "MT_PRIME",              # alive
    "ImmuneApp":   "MT_ImmuneApp",           # alive
    "deepHLApan":  "MT_deepHLApan",          # alive
    "HLAthena":    "MT_HLAthena",            # dead: signal <= 0.03
}
DEAD_TOOLS = {"DeepImmuno", "NeoTImmuML", "HLAthena"}
SURV6_TOOLS = [t for t in TOOL_COLS if t not in DEAD_TOOLS]

# pTuneos 子特征列 (非独立工具, 排除)
EXCLUDE_MT_COLS = {
    "MT_FullPeptide", "MT_Subpeptide",
    "MT_NOAH", "MT_NetCleave", "MT_Stab_peptide", "MT_TCR_contact",
}

# ── BLOSUM62 (Henikoff & Henikoff 1992 PNAS 89:10915) ────────────────────────
# 标准 20×20 矩阵, 来源: NCBI BLAST ftp://ftp.ncbi.nih.gov/blast/matrices/BLOSUM62
# 对称矩阵, 此处显式列出全 20×20
BLOSUM62 = {
    "A": {"A": 4,"R":-1,"N":-2,"D":-2,"C": 0,"Q":-1,"E":-1,"G": 0,"H":-2,"I":-1,"L":-1,"K":-1,"M":-1,"F":-2,"P":-1,"S": 1,"T": 0,"W":-3,"Y":-2,"V": 0},
    "R": {"A":-1,"R": 5,"N": 0,"D":-2,"C":-3,"Q": 1,"E": 0,"G":-2,"H": 0,"I":-3,"L":-2,"K": 2,"M":-1,"F":-3,"P":-2,"S":-1,"T":-1,"W":-3,"Y":-2,"V":-3},
    "N": {"A":-2,"R": 0,"N": 6,"D": 1,"C":-3,"Q": 0,"E": 0,"G": 0,"H": 1,"I":-3,"L":-3,"K": 0,"M":-2,"F":-3,"P":-2,"S": 1,"T": 0,"W":-4,"Y":-2,"V":-3},
    "D": {"A":-2,"R":-2,"N": 1,"D": 6,"C":-3,"Q": 0,"E": 2,"G":-1,"H":-1,"I":-3,"L":-4,"K":-1,"M":-3,"F":-3,"P":-1,"S": 0,"T":-1,"W":-4,"Y":-3,"V":-3},
    "C": {"A": 0,"R":-3,"N":-3,"D":-3,"C": 9,"Q":-3,"E":-4,"G":-3,"H":-3,"I":-1,"L":-1,"K":-3,"M":-1,"F":-2,"P":-3,"S":-1,"T":-1,"W":-2,"Y":-2,"V":-1},
    "Q": {"A":-1,"R": 1,"N": 0,"D": 0,"C":-3,"Q": 5,"E": 2,"G":-2,"H": 0,"I":-3,"L":-2,"K": 1,"M": 0,"F":-3,"P":-1,"S": 0,"T":-1,"W":-2,"Y":-1,"V":-2},
    "E": {"A":-1,"R": 0,"N": 0,"D": 2,"C":-4,"Q": 2,"E": 5,"G":-2,"H": 0,"I":-3,"L":-3,"K": 1,"M":-2,"F":-3,"P":-1,"S": 0,"T":-1,"W":-3,"Y":-2,"V":-2},
    "G": {"A": 0,"R":-2,"N": 0,"D":-1,"C":-3,"Q":-2,"E":-2,"G": 6,"H":-2,"I":-4,"L":-4,"K":-2,"M":-3,"F":-3,"P":-2,"S": 0,"T":-2,"W":-2,"Y":-3,"V":-3},
    "H": {"A":-2,"R": 0,"N": 1,"D":-1,"C":-3,"Q": 0,"E": 0,"G":-2,"H": 8,"I":-3,"L":-3,"K":-1,"M":-2,"F":-1,"P":-2,"S":-1,"T":-2,"W":-2,"Y": 2,"V":-3},
    "I": {"A":-1,"R":-3,"N":-3,"D":-3,"C":-1,"Q":-3,"E":-3,"G":-4,"H":-3,"I": 4,"L": 2,"K":-3,"M": 1,"F": 0,"P":-3,"S":-2,"T":-1,"W":-3,"Y":-1,"V": 3},
    "L": {"A":-1,"R":-2,"N":-3,"D":-4,"C":-1,"Q":-2,"E":-3,"G":-4,"H":-3,"I": 2,"L": 4,"K":-2,"M": 2,"F": 0,"P":-3,"S":-2,"T":-1,"W":-2,"Y":-1,"V": 1},
    "K": {"A":-1,"R": 2,"N": 0,"D":-1,"C":-3,"Q": 1,"E": 1,"G":-2,"H":-1,"I":-3,"L":-2,"K": 5,"M":-1,"F":-3,"P":-1,"S": 0,"T":-1,"W":-3,"Y":-2,"V":-2},
    "M": {"A":-1,"R":-1,"N":-2,"D":-3,"C":-1,"Q": 0,"E":-2,"G":-3,"H":-2,"I": 1,"L": 2,"K":-1,"M": 5,"F": 0,"P":-2,"S":-1,"T":-1,"W":-1,"Y":-1,"V": 1},
    "F": {"A":-2,"R":-3,"N":-3,"D":-3,"C":-2,"Q":-3,"E":-3,"G":-3,"H":-1,"I": 0,"L": 0,"K":-3,"M": 0,"F": 6,"P":-4,"S":-2,"T":-2,"W": 1,"Y": 3,"V":-1},
    "P": {"A":-1,"R":-2,"N":-2,"D":-1,"C":-3,"Q":-1,"E":-1,"G":-2,"H":-2,"I":-3,"L":-3,"K":-1,"M":-2,"F":-4,"P": 7,"S":-1,"T":-1,"W":-4,"Y":-3,"V":-2},
    "S": {"A": 1,"R":-1,"N": 1,"D": 0,"C":-1,"Q": 0,"E": 0,"G": 0,"H":-1,"I":-2,"L":-2,"K": 0,"M":-1,"F":-2,"P":-1,"S": 4,"T": 1,"W":-3,"Y":-2,"V":-2},
    "T": {"A": 0,"R":-1,"N": 0,"D":-1,"C":-1,"Q":-1,"E":-1,"G":-2,"H":-2,"I":-1,"L":-1,"K":-1,"M":-1,"F":-2,"P":-1,"S": 1,"T": 5,"W":-2,"Y":-2,"V": 0},
    "W": {"A":-3,"R":-3,"N":-4,"D":-4,"C":-2,"Q":-2,"E":-3,"G":-2,"H":-2,"I":-3,"L":-2,"K":-3,"M":-1,"F": 1,"P":-4,"S":-3,"T":-2,"W":11,"Y": 2,"V":-3},
    "Y": {"A":-2,"R":-2,"N":-2,"D":-3,"C":-2,"Q":-1,"E":-2,"G":-3,"H": 2,"I":-1,"L":-1,"K":-2,"M":-1,"F": 3,"P":-3,"S":-2,"T":-2,"W": 2,"Y": 7,"V":-1},
    "V": {"A": 0,"R":-3,"N":-3,"D":-3,"C":-1,"Q":-2,"E":-2,"G":-3,"H":-3,"I": 3,"L": 1,"K":-2,"M": 1,"F":-1,"P":-2,"S":-2,"T": 0,"W":-3,"Y":-1,"V": 4},
}

# ── Kyte-Doolittle 疏水性标度 (Kyte & Doolittle 1982 J Mol Biol 157:105-132) ──
KD_HYDROPHOBICITY = {
    "A": 1.8,  "R": -4.5, "N": -3.5, "D": -3.5, "C":  2.5,
    "Q": -3.5, "E": -3.5, "G": -0.4, "H": -3.2, "I":  4.5,
    "L":  3.8, "K": -3.9, "M":  1.9, "F":  2.8, "P": -1.6,
    "S": -0.8, "T": -0.7, "W": -0.9, "Y": -1.3, "V":  4.2,
}


# ── 序列特征计算函数 ──────────────────────────────────────────────────────────

def _find_mut_positions(mt_seq: str, wt_seq: str) -> list:
    """返回 MT vs WT 错配位点索引列表 (0-based)."""
    if not isinstance(mt_seq, str) or not isinstance(wt_seq, str):
        return []
    length = min(len(mt_seq), len(wt_seq))
    return [i for i in range(length) if mt_seq[i].upper() != wt_seq[i].upper()]


def compute_blosum62_mut_score(mt_seq, wt_seq) -> float:
    """BLOSUM62[WT_aa][MT_aa] sum over mismatch positions.
    越负 = 越不保守 = 可能更具外来度 (agretopicity proxy).
    返回 NaN if 任一序列无效。
    """
    if not isinstance(mt_seq, str) or not isinstance(wt_seq, str):
        return np.nan
    mt_seq = mt_seq.upper()
    wt_seq = wt_seq.upper()
    positions = _find_mut_positions(mt_seq, wt_seq)
    if not positions:
        return 0.0  # 完全相同序列
    total = 0
    for i in positions:
        wt_aa = wt_seq[i]
        mt_aa = mt_seq[i]
        row = BLOSUM62.get(wt_aa)
        if row is None:
            continue  # 非标准氨基酸, 跳过
        total += row.get(mt_aa, 0)
    return float(total)


def compute_kd_mean(seq) -> float:
    """Kyte-Doolittle 均值疏水性. 非标准氨基酸跳过."""
    if not isinstance(seq, str) or len(seq) == 0:
        return np.nan
    scores = [KD_HYDROPHOBICITY[aa.upper()]
              for aa in seq if aa.upper() in KD_HYDROPHOBICITY]
    return float(np.mean(scores)) if scores else np.nan


def compute_aromatic_fraction(seq) -> float:
    """芳香族残基 (F/W/Y) 占比."""
    if not isinstance(seq, str) or len(seq) == 0:
        return np.nan
    aromatics = sum(1 for aa in seq if aa.upper() in ("F", "W", "Y"))
    return float(aromatics / len(seq))


def compute_seq_features(row) -> dict:
    """计算一行 (Peptide_ID 级) 的所有 Tier-1 序列特征."""
    mt = row.get("MT_FullPeptide", None)
    wt = row.get("WT_FullPeptide", None)

    n_mut = np.nan
    blosum_score = np.nan
    mut_rel_pos = np.nan
    kd_mt = np.nan
    kd_wt = np.nan
    kd_diff = np.nan
    aromatic_mt = np.nan

    if isinstance(mt, str) and isinstance(wt, str):
        mt = mt.upper()
        wt = wt.upper()
        positions = _find_mut_positions(mt, wt)
        n_mut = float(len(positions))
        blosum_score = compute_blosum62_mut_score(mt, wt)
        if positions and len(mt) > 0:
            mut_rel_pos = float(np.mean(positions)) / len(mt)
        kd_mt = compute_kd_mean(mt)
        kd_wt = compute_kd_mean(wt)
        if not np.isnan(kd_mt) and not np.isnan(kd_wt):
            kd_diff = kd_mt - kd_wt
        aromatic_mt = compute_aromatic_fraction(mt)

    return {
        "seq_length":           float(row.get("Peptide_Length", np.nan))
                                if not np.isnan(float(row.get("Peptide_Length", np.nan) or np.nan))
                                else np.nan,
        "seq_n_mutations":      n_mut,
        "seq_blosum62_mut_score": blosum_score,
        "seq_mutation_rel_pos": mut_rel_pos,
        "seq_kd_hydro_mt":      kd_mt,
        "seq_kd_hydro_diff":    kd_diff,
        "seq_aromatic_mt":      aromatic_mt,
        # Tier-2 外来度占位 (TODO: Łuksza 2017 neoantigen fitness, 需官方实现)
        # TODO: seq_foreignness — Łuksza 2017 doi:10.1038/nmeth.4279 需官方实现
        "seq_foreignness":      np.nan,
    }


# ── 主函数 ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Build F-pilot model matrix (9 tools + seq features)")
    ap.add_argument("--input", default=str(DEFAULT_MERGED),
                    help="merged_all_tools_9tools.xlsx 路径 (默认自动找)")
    ap.add_argument("--out", default=str(OUT_MATRIX),
                    help="输出 CSV 路径 (默认 quantimmune/model_matrix.csv)")
    args = ap.parse_args()

    merged_path = Path(args.input)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not merged_path.exists():
        sys.exit(f"[ERR] 输入文件不存在: {merged_path}")

    print(f"[info] 读取 {merged_path}")
    df = pd.read_excel(merged_path)
    print(f"[info] 原始行数: {len(df)}, 列数: {len(df.columns)}")

    # ── 验证必要列 ─────────────────────────────────────────────────────────────
    required = ["Peptide_ID", "Dataset", "Patient_ID", "Elispot",
                "MT_FullPeptide", "WT_FullPeptide", "Peptide_Length", "HLA_Allele"]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        sys.exit(f"[ERR] 缺少必要列: {missing_cols}")

    # ── Step 1: max-agg 工具分数 (子肽 → 肽级) ──────────────────────────────
    print("\n[step1] max-agg 工具分数 per Peptide_ID ...")
    agg_dict = {}
    present_tool_cols = {}
    for tool_name, col in TOOL_COLS.items():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            if df[col].notna().any():
                agg_dict[col] = "max"
                present_tool_cols[tool_name] = col
            else:
                print(f"  [warn] {tool_name} 列 {col} 全为 NaN, 跳过")
        else:
            print(f"  [warn] {tool_name} 列 {col} 不存在")

    # 聚合: per Peptide_ID max score
    pep_scores = df.groupby("Peptide_ID").agg(agg_dict).reset_index()
    print(f"  [info] max-agg 后: {len(pep_scores)} 行 × {len(agg_dict)+1} 列")

    # ── Step 2: per-peptide 元信息 (first non-null per Peptide_ID) ────────────
    print("\n[step2] 提取每肽元信息 (Dataset / Patient_ID / 序列 / Elispot) ...")
    meta_cols = ["Peptide_ID", "Dataset", "Patient_ID", "Peptide_Length",
                 "MT_FullPeptide", "WT_FullPeptide", "Elispot", "HLA_Allele"]
    pep_meta = (df[meta_cols]
                .drop_duplicates("Peptide_ID")
                .reset_index(drop=True))
    print(f"  [info] 唯一肽 meta: {len(pep_meta)} 行")

    # DS1/DS2 分布确认
    ds_counts = pep_meta["Dataset"].value_counts()
    print(f"  DS 分布: {dict(ds_counts)}")
    pat_counts = pep_meta["Patient_ID"].nunique()
    print(f"  患者数: {pat_counts}")

    # ── Step 3: join meta + scores ────────────────────────────────────────────
    matrix = pep_meta.merge(pep_scores, on="Peptide_ID", how="left")
    print(f"\n[step3] join 后 matrix shape: {matrix.shape}")

    # ── Step 4: 缺失标记列 (折内填补在 lopo_eval.py 里完成, 此处只标记) ────────
    # 策略: 折内训练集均值填补, 禁用含 held-out 患者的全局统计 (防泄漏)
    print("\n[step4] 生成 missing 标记列 ...")
    for tool_name, col in present_tool_cols.items():
        miss_col = f"missing_{tool_name}"
        matrix[miss_col] = matrix[col].isna().astype(int)
        n_miss = matrix[miss_col].sum()
        if n_miss > 0:
            print(f"  {tool_name}: {n_miss} 肽缺分数 → {miss_col}=1")

    # ── Step 5: Tier-1 序列特征 ───────────────────────────────────────────────
    print("\n[step5] 计算 Tier-1 序列特征 ...")
    seq_feats = matrix.apply(compute_seq_features, axis=1)
    seq_df = pd.DataFrame(list(seq_feats))
    matrix = pd.concat([matrix.reset_index(drop=True), seq_df], axis=1)

    seq_cols = list(seq_df.columns)
    for col in seq_cols:
        n_valid = matrix[col].notna().sum()
        print(f"  {col}: {n_valid}/{len(matrix)} 非 NaN")

    # ── Step 6: HLA_Allele 取第一个 (保留一行标签) ───────────────────────────
    matrix = matrix.rename(columns={"HLA_Allele": "HLA_Allele_first"})

    # ── 最终列顺序整理 ────────────────────────────────────────────────────────
    meta_out = ["Peptide_ID", "Patient_ID", "Dataset", "Elispot",
                "HLA_Allele_first", "Peptide_Length", "MT_FullPeptide", "WT_FullPeptide"]
    tool_out = list(agg_dict.keys())         # MT_<tool> 分数列
    missing_out = [f"missing_{t}" for t in present_tool_cols]
    seq_out = seq_cols

    final_cols = [c for c in meta_out + tool_out + missing_out + seq_out
                  if c in matrix.columns]
    matrix = matrix[final_cols]

    matrix.to_csv(out_path, index=False, encoding="utf-8")
    print(f"\n[saved] {out_path}  shape={matrix.shape}")
    print(f"  工具分数列 ({len(tool_out)}): {[c.replace('MT_','') for c in tool_out]}")
    print(f"  序列特征列 ({len(seq_out)}): {seq_out}")
    print(f"\n[DONE] model_matrix.csv 就绪, 下一步: python quantimmune/lopo_eval.py")


if __name__ == "__main__":
    main()
