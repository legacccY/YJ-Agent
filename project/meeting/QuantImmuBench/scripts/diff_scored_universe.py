#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diff_scored_universe.py
服务: quantimmu-bench / 切肽口径大改 §改动②/③ S4

切肽(改动②原始蛋白版)产的窗里, 一部分工具已打过分(可复用), 一部分是新肽(要上 HPC
重跑)。本脚本精确量化「要重跑多少」, 喂会上分工谈判 + 备 HPC 上传包。不产分数, 只做差集。

================== 输入 (只读) ==================
  表 B = data/frozen/newcut_subpep_hla.NEW.csv   (cut_from_protein WITH mane 产物)
      列 mut_key,Patient_ID,Peptide_ID,Vaccine_Peptide,subpep_seq,subpep_pos,
         window_size,hla_allele_std,side{MT,WT},source{SLP,MANE,dropped},consistency_flag
  已打分 universe = scripts/out/merged_all_tools_30_official.csv  (per-subpep×HLA)
      join 键: Peptide_ID + (MT_Subpeptide|WT_Subpeptide) + HLA_Allele (HLA-A*01:01)
      分数列: MT_<tool> ×30 / WT_<tool> ×24 (排除 *_FullPeptide/*_Subpeptide/__AUX_*)

================== 逻辑 ==================
  表 B MT side: join 按 (Peptide_ID, subpep_seq==MT_Subpeptide, hla_allele_std==HLA_Allele)。
      未命中(新肽, 主要 source=MANE 溢出窗) -> 全部工具待重跑。
  表 B WT side: join 按 (Peptide_ID, subpep_seq==WT_Subpeptide, HLA_Allele), 且*逐工具*看
      WT_<tool> 是否非 NaN (各工具 WT 填充率不同; BigMHC/CNNeo 高, DeepImmuno 低)。
  某窗某工具: 命中行 且该工具值非 NaN = 可复用; 否则(未命中 或 NaN) = 待重跑。
  窗级: 全工具都可复用 = fully_reusable; 任一工具缺 = needs_rerun。

================== 输出 (先写 .NEW.csv 别覆盖) ==================
  data/frozen/rerun_needed.NEW.csv   待重跑窗清单 + 缺哪些工具(missing_tools)
  data/frozen/reuse_summary.NEW.csv  side×source 统计: 总窗/命中/可复用/待重跑
  data/frozen/tool_gap.NEW.csv       按 (side,工具) 的缺口计数 (WT 各工具缺口分布)
  + print 汇总

================== 跑法 (不在本脚本内跑; 交主线) ==================
  python scripts/diff_scored_universe.py
  (先跑 cut_from_protein.py 产 newcut_subpep_hla.NEW.csv)
"""

import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
FROZEN_DIR = ROOT / "data" / "frozen"

SUBPEP_B = FROZEN_DIR / "newcut_subpep_hla.NEW.csv"
SCORED = ROOT / "scripts" / "out" / "merged_all_tools_30_official.csv"

OUT_RERUN = FROZEN_DIR / "rerun_needed.NEW.csv"
OUT_SUMMARY = FROZEN_DIR / "reuse_summary.NEW.csv"
OUT_TOOLGAP = FROZEN_DIR / "tool_gap.NEW.csv"

# 分数列前缀下的非工具元数据列 (排除, 别当工具算缺口)
META_MT = {"MT_FullPeptide", "MT_Subpeptide"}
META_WT = {"WT_FullPeptide", "WT_Subpeptide"}


def tool_cols(cols, prefix, meta):
    """取 prefix(MT_/WT_) 下真工具列: 排除元数据 + __AUX_* 辅助列。"""
    return [c for c in cols
            if c.startswith(prefix) and c not in meta and not c.startswith("__AUX")]


def compute_missing(merged, tools):
    """
    对 merge 后的表, 逐窗逐工具判「待重跑」。
    待重跑 = 未命中(_merge!='both') 或 命中但该工具 NaN。
    返回 (matched: bool ndarray, n_missing: Series, missing_tools: list[str])。
    """
    matched = merged["_merge"].eq("both").to_numpy()
    miss = pd.DataFrame(index=merged.index)
    for t in tools:
        miss[t] = (~matched) | merged[t].isna().to_numpy()
    n_missing = miss.sum(axis=1)
    tool_names = [t[3:] for t in tools]  # 去 'MT_'/'WT_' 前缀
    miss_arr = miss.to_numpy()
    missing_tools = [";".join(n for n, m in zip(tool_names, row) if m) for row in miss_arr]
    return matched, n_missing, missing_tools, miss


def diff_side(b_side, scored, subpep_col, tools, side_name):
    """
    单 side(MT/WT) 差集: b_side join scored, 算每窗待重跑工具。
    返回 (b_side 加列后的 df, miss_df 逐工具 bool)。
    """
    slim = scored[["Peptide_ID", subpep_col, "HLA_Allele"] + tools].copy()
    n_dup = slim.duplicated(subset=["Peptide_ID", subpep_col, "HLA_Allele"]).sum()
    if n_dup:
        print(f"[WARN] scored 里 {side_name} join 键有 {n_dup} 重复行, 取首个 "
              f"(可能漏后行非 NaN 分, 人工核 scored 唯一性)")
        slim = slim.drop_duplicates(subset=["Peptide_ID", subpep_col, "HLA_Allele"], keep="first")

    merged = b_side.merge(
        slim, how="left",
        left_on=["Peptide_ID", "subpep_seq", "hla_allele_std"],
        right_on=["Peptide_ID", subpep_col, "HLA_Allele"],
        indicator=True,
    )
    matched, n_missing, missing_tools, miss = compute_missing(merged, tools)
    out = b_side.copy()
    out["matched"] = matched
    out["n_tools_total"] = len(tools)
    out["n_tools_missing"] = n_missing.to_numpy()
    out["missing_tools"] = missing_tools
    return out, miss


def main():
    for p in (SUBPEP_B, SCORED):
        if not p.exists():
            raise SystemExit(f"[ERR] 依赖缺失: {p}  (表 B 需先跑 cut_from_protein.py)")

    # 表 B: 只需键 + side/source; 全按 str 读保 join 键稳定
    b = pd.read_csv(SUBPEP_B, dtype=str)
    for c in ("Peptide_ID", "subpep_seq", "hla_allele_std"):
        b[c] = b[c].astype(str).str.strip()
    print(f"[info] 表 B 行数: {len(b)}  (side: {b['side'].value_counts().to_dict()})")

    scored = pd.read_csv(SCORED)
    for c in ("Peptide_ID", "MT_Subpeptide", "WT_Subpeptide", "HLA_Allele"):
        scored[c] = scored[c].astype(str).str.strip()
    mt_tools = tool_cols(scored.columns, "MT_", META_MT)
    wt_tools = tool_cols(scored.columns, "WT_", META_WT)
    print(f"[info] 已打分 universe 行数: {len(scored)}  "
          f"MT 工具={len(mt_tools)}  WT 工具={len(wt_tools)}")

    # ── 逐 side 差集 ──────────────────────────────────────────────────────
    b_mt = b[b["side"] == "MT"].copy()
    b_wt = b[b["side"] == "WT"].copy()
    mt_out, mt_miss = diff_side(b_mt, scored, "MT_Subpeptide", mt_tools, "MT")
    wt_out, wt_miss = diff_side(b_wt, scored, "WT_Subpeptide", wt_tools, "WT")

    all_out = pd.concat([mt_out, wt_out], ignore_index=True)

    # ── 输出 1: 待重跑窗清单 (任一工具缺) ─────────────────────────────────
    rerun = all_out[all_out["n_tools_missing"] > 0].copy()
    rerun_cols = ["mut_key", "Patient_ID", "Peptide_ID", "subpep_seq", "hla_allele_std",
                  "side", "source", "consistency_flag", "window_size",
                  "matched", "n_tools_total", "n_tools_missing", "missing_tools"]
    rerun_cols = [c for c in rerun_cols if c in rerun.columns]
    FROZEN_DIR.mkdir(parents=True, exist_ok=True)
    rerun[rerun_cols].to_csv(OUT_RERUN, index=False, encoding="utf-8")
    print(f"\n[saved] {OUT_RERUN}  shape={rerun[rerun_cols].shape}")

    # ── 输出 2: side×source 统计 ──────────────────────────────────────────
    summ_rows = []
    for (side, source), g in all_out.groupby(["side", "source"]):
        n = len(g)
        n_matched = int(g["matched"].sum())
        n_unmatched = n - n_matched
        n_full = int((g["n_tools_missing"] == 0).sum())
        n_rerun = int((g["n_tools_missing"] > 0).sum())
        n_partial = n_rerun - n_unmatched  # 命中但仍缺工具的窗
        summ_rows.append({
            "side": side, "source": source, "n_windows": n,
            "n_matched": n_matched, "n_unmatched": n_unmatched,
            "n_fully_reusable": n_full, "n_partial": n_partial, "n_needs_rerun": n_rerun,
        })
    summ = pd.DataFrame(summ_rows).sort_values(["side", "source"]).reset_index(drop=True)
    summ.to_csv(OUT_SUMMARY, index=False, encoding="utf-8")
    print(f"[saved] {OUT_SUMMARY}  shape={summ.shape}")

    # ── 输出 3: 按 (side,工具) 缺口计数 (WT 各工具填充率不同, 是 WT 重跑主缺口) ──
    gap_rows = []
    for side_name, miss_df, tools, b_side in (("MT", mt_miss, mt_tools, b_mt),
                                              ("WT", wt_miss, wt_tools, b_wt)):
        n_side = len(b_side)
        for t in tools:
            n_miss = int(miss_df[t].sum())
            gap_rows.append({
                "side": side_name, "tool": t[3:],
                "n_windows_side": n_side, "n_missing": n_miss,
                "frac_missing": round(n_miss / n_side, 4) if n_side else 0.0,
            })
    gap = pd.DataFrame(gap_rows).sort_values(["side", "n_missing"], ascending=[True, False]).reset_index(drop=True)
    gap.to_csv(OUT_TOOLGAP, index=False, encoding="utf-8")
    print(f"[saved] {OUT_TOOLGAP}  shape={gap.shape}")

    # ── print 汇总 ───────────────────────────────────────────────────────
    print("\n========== 汇总 ==========")
    print("[side×source 统计]")
    print(summ.to_string(index=False))

    mt_total = len(b_mt)
    mt_unmatched = int((~mt_out["matched"]).sum())
    mt_full = int((mt_out["n_tools_missing"] == 0).sum())
    print(f"\n[MT] 总窗={mt_total}  可复用(命中)={int(mt_out['matched'].sum())}  "
          f"待重跑(未命中新肽)={mt_unmatched}  (预期 ≈162 溢出窗)  "
          f"全工具就绪={mt_full}")

    print("\n[WT] 各工具待重跑窗数 (缺口从大到小; 各工具 WT 填充率不同):")
    wt_gap = gap[gap["side"] == "WT"]
    for r in wt_gap.itertuples(index=False):
        print(f"    {r.tool:16s} 缺 {r.n_missing:6d} / {r.n_windows_side}  ({r.frac_missing:.1%})")

    print(f"\n[总] 待重跑窗行(任一工具缺): {len(rerun)} / 表B总行 {len(all_out)}")
    print("[DONE] diff_scored_universe 完成")


if __name__ == "__main__":
    main()
