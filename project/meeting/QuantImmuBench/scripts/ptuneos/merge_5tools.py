"""
merge_5tools.py
服务: quantimmu-bench
功能: 把 pTuneos unique 输出 (model_pro) 贴回 4-tools benchmark 表 → 生成 5-tools 表
      join 键: (MT_Subpeptide==MT_pep, WT_Subpeptide==WT_pep, HLA_Allele==HLA_type)
      unique 输出三键唯一 → 左连接不会炸开行数
输出: scripts/out/merged_all_tools_5tools.xlsx
运行: python scripts/ptuneos/merge_5tools.py
"""

import os
import sys
import pandas as pd
import pathlib

# ── 路径 ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parent.parent  # project/meeting/QuantImmuBench

UNIQUE_OUTPUT = SCRIPT_DIR / "ptuneos_unique_output.tsv"
FOUR_TOOLS    = PROJECT_DIR / "scripts" / "out" / "merged_all_tools_4tools.xlsx"
OUT_PATH      = PROJECT_DIR / "scripts" / "out" / "merged_all_tools_5tools.xlsx"


def main():
    # ── 1. 读文件 ──────────────────────────────────────────────────────────────
    print(f"Reading 4-tools table: {FOUR_TOOLS}")
    df4 = pd.read_excel(FOUR_TOOLS)
    print(f"  shape = {df4.shape}")
    print(f"  cols  = {list(df4.columns)}")

    print(f"\nReading pTuneos unique output: {UNIQUE_OUTPUT}")
    df_ptun = pd.read_csv(UNIQUE_OUTPUT, sep="\t")
    print(f"  shape = {df_ptun.shape}")
    print(f"  cols  = {list(df_ptun.columns)}")

    # ── 2. 验证 unique 三键确实唯一 ───────────────────────────────────────────
    dup_check = df_ptun.duplicated(subset=["MT_pep", "WT_pep", "HLA_type"]).sum()
    print(f"\n  pTuneos (MT_pep, WT_pep, HLA_type) 重复行数: {dup_check}")
    if dup_check > 0:
        print("  WARNING: unique 输出三键不唯一，merge 可能炸行数，请检查！")

    # ── 3. 从 unique 输出取所需列 ─────────────────────────────────────────────
    #    只保留 join 键 + 目标列，避免列名冲突
    df_ptun_slim = df_ptun[["MT_pep", "WT_pep", "HLA_type", "model_pro", "hydro_defaulted"]].copy()
    df_ptun_slim = df_ptun_slim.rename(columns={
        "model_pro":       "MT_pTuneos",
        "hydro_defaulted": "pTuneos_hydro_defaulted",
    })

    # ── 4. 左连接贴回 4-tools 表 ─────────────────────────────────────────────
    #    join 键: 4tools 的 MT_Subpeptide / WT_Subpeptide / HLA_Allele
    #             对应 unique 的 MT_pep / WT_pep / HLA_type
    n_before = len(df4)
    df5 = df4.merge(
        df_ptun_slim,
        left_on=["MT_Subpeptide", "WT_Subpeptide", "HLA_Allele"],
        right_on=["MT_pep",       "WT_pep",         "HLA_type"],
        how="left",
        validate="m:1",   # 4tools 多行 → unique 一行，m:1 保证不炸行数
    )
    # 删掉 unique 表带过来的重复键列
    df5 = df5.drop(columns=["MT_pep", "WT_pep", "HLA_type"])

    n_after = len(df5)
    assert n_before == n_after, \
        f"行数变化！before={n_before} after={n_after}，请检查 join 键"

    # ── 5. 统计覆盖情况 ───────────────────────────────────────────────────────
    n_filled = df5["MT_pTuneos"].notna().sum()
    n_nan    = df5["MT_pTuneos"].isna().sum()
    print(f"\n== 覆盖统计 ==")
    print(f"  总行数:          {len(df5)}")
    print(f"  贴上 MT_pTuneos: {n_filled}")
    print(f"  NaN 行数:        {n_nan}")

    # DS2 覆盖
    ds2 = df5[df5["Dataset"] == "DS2"]
    ds2_pep_total   = ds2["Peptide_ID"].nunique()
    ds2_pep_covered = ds2[ds2["MT_pTuneos"].notna()]["Peptide_ID"].nunique()
    print(f"\n  DS2 unique Peptide_ID 总数:       {ds2_pep_total}")
    print(f"  DS2 有 pTuneos 覆盖的 Peptide_ID: {ds2_pep_covered}")

    # 按长度统计覆盖
    df5["_pep_len"] = df5["MT_Subpeptide"].str.len()
    len_stats = (
        df5[df5["MT_pTuneos"].notna()]
        .groupby("_pep_len")
        .size()
        .rename("n_filled")
    )
    print(f"\n  各长度覆盖行数:\n{len_stats.to_string()}")
    df5 = df5.drop(columns=["_pep_len"])

    # hydro_defaulted 统计
    n_hydro_default = (df5["pTuneos_hydro_defaulted"] == True).sum()
    print(f"\n  pTuneos_hydro_defaulted=True 行数: {n_hydro_default}  (非9/10/11mer)")

    # ── 6. 保存 ───────────────────────────────────────────────────────────────
    print(f"\nSaving: {OUT_PATH}")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df5.to_excel(OUT_PATH, index=False)
    print(f"Done. shape = {df5.shape}")
    print(f"\n列顺序（末尾新增）:")
    print(f"  MT_pTuneos, pTuneos_hydro_defaulted")


if __name__ == "__main__":
    main()
