#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_dai_pool.py
服务: quantimmu-bench / §3.1 DAI 版单工具排名

从改动②/③ 重跑宽表 (merged_all_tools_30_rerun.csv, MT+WT 双分) 算 DAI 并
按 mut_key max-pool 成突变级表, schema 完全对齐现有 MT 版 pooled, 直接喂
recompute_R1_effN.py (它读 <tool>_max 列)。**不产分数以外的口径改动, 不跑代码。**

================== DAI 定义 (袁老师权威 outline §2.3 Step 1, 相减型 floored) ==================
  行级:  DAI_<tool> = max(MT_<tool> - WT_<tool>, 0)      # 负差归 0 (floored 净增强)
  MT 或 WT 任一 NaN -> 该行 DAI = NaN (不填补, 不参与后续 max-pool)
  两分均已定向「越大越免疫原」, 直接相减。

================== 工具集 (从 merged 自动派生, 零硬编码工具名, 数量随输入伸缩) ==================
  取 TOOLS_30 中在 merged 里 **MT_<tool> 与 WT_<tool> 两列都在** 的工具。
    · 原 merged_all_tools_30_rerun.csv          -> 24 (排除无 WT_ 的 ICERFIRE/IMPROVE/
                                                    Seq2Neo/TSCAPE/pTuneos 与无列的 NeoaPred)
    · WITH_WT2 副本 (补 WT_Seq2Neo/WT_TSCAPE)    -> 26 (侦测层; NeoaG DAI 全 NaN 时 25 能算)
  仅 MT / 缺 WT 的工具自动不产 DAI 列。

================== 池化 ==================
  按 mut_key 分组, 每工具 DAI 列取 max (skipna, 组内全 NaN -> NaN)。
  等价现有 MT 版 max-pooling 算子, 池化对象换成 floored-DAI。
  元数据 (Patient_ID, Peptide_ID, Elispot) 取组内第一个 (组内恒定)。

================== 输入 (只读; --merged 可切换) ==================
  --merged (默认 scripts/out/merged_all_tools_30_rerun.csv)   宽表 (含 MT_<tool>/WT_<tool>
      + mut_key/Patient_ID/Peptide_ID/Elispot 元数据; 全 mutation-spanning 窗)
  data/frozen/pooled_clean_rerun_9mer.csv      仅取其 mut_key 出现顺序 (行序对齐, 不改它)

================== 输出 (--out; 默认拦覆盖, 传 --force 才覆盖) ==================
  --out (默认 data/frozen/pooled_dai_rerun_9mer.csv)          102 行 (102 SNV 肽)
      列: mut_key, Patient_ID, Peptide_ID, Elispot, 然后 N 个 <tool>_max (N=侦测到的工具数)
      (值 = floored-DAI 的 max-pool; 列名沿用 <tool>_max 以直接喂 recompute)
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Windows 必要: UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent                  # analysis/official/recompute_effN/
OFFICIAL = HERE.parent                                  # analysis/official/
ROOT = OFFICIAL.parent.parent                           # QuantImmuBench/
sys.path.insert(0, str(OFFICIAL))

from _official_common import TOOLS_30                    # noqa: E402  (唯一工具真源)

DEFAULT_MERGED = ROOT / "scripts" / "out" / "merged_all_tools_30_rerun.csv"
POOLED_CLEAN = ROOT / "data" / "frozen" / "pooled_clean_rerun_9mer.csv"
DEFAULT_OUT = ROOT / "data" / "frozen" / "pooled_dai_rerun_9mer.csv"

META_COLS = ["mut_key", "Patient_ID", "Peptide_ID", "Elispot"]


def parse_args():
    p = argparse.ArgumentParser(description="floored-DAI 突变级 max-pool (schema 对齐 MT 版 pooled)")
    p.add_argument("--merged", type=Path, default=DEFAULT_MERGED,
                   help="MT+WT 宽表 (默认原 merged_all_tools_30_rerun.csv; 可指向 WITH_WT2 副本)")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT,
                   help="输出突变级 DAI-pool CSV (默认 pooled_dai_rerun_9mer.csv)")
    p.add_argument("--force", action="store_true",
                   help="允许覆盖已存在的 --out (默认拦; 传则覆盖并打印 warning)")
    return p.parse_args()


def main():
    args = parse_args()
    merged_path = args.merged if args.merged.is_absolute() else (ROOT / args.merged)
    out_path = args.out if args.out.is_absolute() else (DEFAULT_OUT.parent / args.out)

    df = pd.read_csv(merged_path, encoding="utf-8")

    # ---- 派生 DAI 工具: MT_ 与 WT_ 两列都在 (零硬编码工具名, 数量随 merged 自动伸缩) ----
    #   原 merged -> 24; WITH_WT2 (补 WT_Seq2Neo/WT_TSCAPE) -> 26 (NeoaG 全 NaN 时 25 能算)
    dai_tools = [t for t in TOOLS_30
                 if f"MT_{t}" in df.columns and f"WT_{t}" in df.columns]
    assert dai_tools, "未侦测到任何 MT+WT 双列工具"

    for c in META_COLS:
        assert c in df.columns, f"merged 缺元数据列 {c}"

    # ---- 行级 floored-DAI: max(MT-WT, 0), 任一 NaN -> NaN ----
    dai = pd.DataFrame({"mut_key": df["mut_key"]})
    for t in dai_tools:
        mt = df[f"MT_{t}"].astype(float)
        wt = df[f"WT_{t}"].astype(float)
        d = (mt - wt).clip(lower=0)                      # floor 负差到 0
        d = d.mask(mt.isna() | wt.isna())               # 任一 NaN -> NaN (clip 不还原 NaN 时兜底)
        dai[f"{t}_max"] = d

    # ---- 按 mut_key max-pool (skipna; 组内全 NaN -> NaN) ----
    tool_cols = [f"{t}_max" for t in dai_tools]
    pooled = dai.groupby("mut_key", sort=False)[tool_cols].max()  # pandas max 默认 skipna
    pooled = pooled.reset_index()

    # ---- 元数据: 组内第一个 ----
    meta = (df[META_COLS].drop_duplicates("mut_key", keep="first")
            .set_index("mut_key"))
    out = pooled.merge(meta, left_on="mut_key", right_index=True, how="left")

    # ---- 行序对齐现有 pooled_clean (只读取其 mut_key 顺序, 不改它) ----
    order = pd.read_csv(POOLED_CLEAN, usecols=["mut_key"], encoding="utf-8")["mut_key"].tolist()
    assert set(out["mut_key"]) == set(order), (
        "mut_key 集合与 pooled_clean 不一致: "
        f"仅DAI有={set(out['mut_key'])-set(order)}; 仅clean有={set(order)-set(out['mut_key'])}")
    out = out.set_index("mut_key").reindex(order).reset_index()

    # ---- schema: mut_key, Patient_ID, Peptide_ID, Elispot, 然后 24 个 <tool>_max ----
    out = out[META_COLS + tool_cols]

    assert len(out) == 102, f"期望 102 行, 实得 {len(out)}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        if not args.force:
            raise SystemExit(f"[拒绝] 输出已存在: {out_path} (传 --force 才覆盖)")
        print(f"[warning] --force: 覆盖已存在文件 {out_path}")
    out.to_csv(out_path, index=False, encoding="utf-8")

    # ---- stdout 诊断 ----
    print(f"[build_dai_pool] 输入 merged: {merged_path} ({len(df)} 行)")
    print(f"[build_dai_pool] DAI 工具 ({len(dai_tools)}): {dai_tools}")
    print(f"[build_dai_pool] 输出: {out_path} ({len(out)} 行)\n")
    print(f"{'tool':<16} {'n_nonNaN':>8} {'n_zero':>7} {'min':>10} {'max':>10}  const?")
    print("-" * 66)
    for t in dai_tools:
        col = out[f"{t}_max"]
        nn = col.notna().sum()
        vals = col.dropna()
        n_zero = int((vals == 0).sum())                 # floor 后归零的肽数 (判 0 平局主导风险)
        vmin = f"{vals.min():.4g}" if nn else "NA"
        vmax = f"{vals.max():.4g}" if nn else "NA"
        const = "YES" if nn and vals.nunique() == 1 else "-"
        print(f"{t:<16} {nn:>8} {n_zero:>7} {vmin:>10} {vmax:>10}  {const}")
    print("-" * 66)
    print(f"总行数 = {len(out)} (期望 102)")
    # DeepNetBim 退化专项提示
    dnb = out["DeepNetBim_max"].dropna()
    if dnb.nunique() <= 1:
        print(f"[!] DeepNetBim_max 退化: nunique={dnb.nunique()} (DAI 可能全常数, 谱不可排)")


if __name__ == "__main__":
    main()
