# -*- coding: utf-8 -*-
"""
patch_101102_scores.py — Phase B B3：把各工具重推理的 101/102 分数填回 canonical 合表。

逆 patch_merge_fixed.py：那一步把 101/102 的 HLA-dep 格置 NaN；这一步用重推理分数填回。
- 只填 scripts/out/phaseB/<Tool>_101102.csv 提供的列，且只填合表里**当前为 NaN 的 101/102 行**。
- 闸门 3：填后断言「除 101/102 的被填格外，其余所有格逐格不变」（对 backup diff）。
- 非破坏：先备份现合表到 _phaseB_backup/，写新表 merged_all_tools_16tools.xlsx。

用法:
  python scripts/phaseB/patch_101102_scores.py            # 正式填 + 闸门3
  python scripts/phaseB/patch_101102_scores.py --dry      # 只报每工具能填多少，不写
"""
import os
import sys
import glob
import argparse
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MERGED = os.path.join(ROOT, "scripts", "out", "merged_all_tools_16tools.xlsx")
PHASEB = os.path.join(ROOT, "scripts", "out", "phaseB")
BACKUP_DIR = os.path.join(ROOT, "scripts", "out", "_phaseB_backup")

# 工具分数 csv（排除中间/输入文件）
EXCLUDE = {"backbone_101102.csv", "deephlapan_input_101102.csv", "deepimmuno_input_101102.csv"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    m = pd.read_excel(MERGED)
    orig = m.copy(deep=True)
    pid = m["Patient_ID"].astype(str).str.extract(r"(10[12])")[0]
    is_pp = pid.notna()
    print(f"合表 {m.shape} | 101/102 行={int(is_pp.sum())}")

    csvs = sorted(f for f in glob.glob(os.path.join(PHASEB, "*_101102.csv"))
                  if os.path.basename(f) not in EXCLUDE)
    filled_cols = []
    for f in csvs:
        name = os.path.basename(f)
        t = pd.read_csv(f).set_index("bb_idx")
        for col in t.columns:
            if col not in m.columns:
                continue
            # 只填 101/102 且当前 NaN 的格
            target = is_pp & m[col].isna()
            idx = m.index[target]
            bbs = m.loc[idx, "bb_idx"].values
            vals = t[col].reindex(bbs).values
            n_fill = int(pd.notna(vals).sum())
            if n_fill:
                m.loc[idx, col] = vals
                filled_cols.append(col)
            print(f"  [{name:28}] {col:32} 填 {n_fill}/{len(idx)}")

    # ── 闸门 3：除被填格外，其余逐格不变 ────────────────────────────────────
    print("\n[闸门3] 校验非填充格不变...")
    changed_outside = 0
    for col in orig.columns:
        a, b = orig[col], m[col]
        # 两边都 NaN 视为相等
        both_nan = a.isna() & b.isna()
        eq = (a.astype(str) == b.astype(str)) | both_nan
        diff_rows = m.index[~eq]
        for ri in diff_rows:
            # 允许：101/102 行 + 本次填的列
            if is_pp.iloc[ri] and col in filled_cols:
                continue
            changed_outside += 1
            if changed_outside <= 5:
                print(f"  [FAIL] row{ri} col{col}: {orig.at[ri,col]!r} -> {m.at[ri,col]!r}")
    if changed_outside:
        raise SystemExit(f"[闸门3 FAIL] {changed_outside} 个非法变动格 → 不写，停。")
    print(f"[闸门3 PASS] 只有 101/102 的被填列变动，其余字节不变。")

    # 剩余 NaN 报告
    print("\n[剩余 101/102 NaN]（未跑/不适用的工具列）:")
    for col in sorted(set(c for c in m.columns if c.startswith(("MT_", "WT_")))):
        rem = int((is_pp & m[col].isna()).sum())
        if rem:
            print(f"  {col:34} 仍 NaN {rem}")

    if args.dry:
        print("\n[--dry] 不写盘。")
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bak = os.path.join(BACKUP_DIR, "merged_all_tools_16tools_preB3.xlsx")
    orig.to_excel(bak, index=False)
    m.to_excel(MERGED, index=False)
    print(f"\n[DONE] 备份 {bak}\n       写回 {MERGED}  shape={m.shape}")


if __name__ == "__main__":
    main()
