#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rebuild_canonical.py — QuantImmuBench 单一真源管道驱动 (编排, 非重构)
服务: quantimmu-bench「管道收敛成单一可复现真源」
lever: 把散落 3 处的 4 个 Tier2 补丁编排成一条确定性驱动脚本, 证明「编排=现状、零偏离」。

============================================================================
Tier1 (冻结输入, 本脚本【不重跑】30 工具)
============================================================================
  30 工具 raw --build_official_from_raw--> out_official/<Tool>_official.csv (39 个)
             --merge_official_30--> scripts/out/merged_all_tools_30_official.csv
                                    (base 长表, 34703 行, 2026-07-01)  ← Tier1 边界
  本脚本以此 base 长表为**只读起点**, 绝不重跑工具/重 merge。

============================================================================
Tier2 (本地可复现, 本脚本编排的部分; 每步 read -> write 全显式传路径)
============================================================================
9mer 主分析链 (canonical = data/frozen/pooled_clean_9mer.csv):
  S1 patch_covfix_8tools.py   base            -> rebuild/…_covfix.csv         (8 工具, 只填 NaN)
  S2 patch_deephlapan_indel.py …_covfix.csv   -> rebuild/…_covfix_di.csv      (deepHLApan INDEL raw)
  S3 patch_deephlapan_indel.py …_covfix_di.csv-> rebuild/…_covfix_final.csv   (deepHLApan SNV110 raw)★
  S4 p0e2_pool_clean.py --ninemer …_final.csv -> rebuild/pooled_clean_9mer.NEW.csv

8-11mer 补充链 (canonical = data/frozen/pooled_clean_8to11mer.csv):
  S5 patch_covfix_8to11.py    base            -> rebuild/…_covfix_8to11.csv        (9 工具+阶段2 8-11)
  S6 patch_deephlapan_indel.py …_8to11.csv    -> rebuild/…_8to11_di.csv            (INDEL raw)
  S7 patch_deephlapan_indel.py …_8to11_di.csv -> rebuild/…_8to11_final.csv         (SNV110 raw)★
  S8 p0e2_pool_clean.py --w811 …_8to11_final  -> rebuild/pooled_clean_8to11mer.NEW.csv

  ★ deepHLApan 需 **两次** patch (INDEL + SNV110): 当前 canonical 覆盖 101->130 里
    +29 = 28 indel + 1 长 SNV 肽 (16097-110-18, 90 子肽在 SNV110 raw)。现 patch 脚本
    单次只读 INDEL raw (→129), 故驱动对每个 covfix 副本连调两次补满到 130。见回执风险 §。

冻结: analysis/phase0/p0f_freeze_provenance.py -> data/frozen/PROVENANCE.json (仅 --promote 时重冻)

============================================================================
模式
============================================================================
  --verify (默认): 跑 S1..S8 到 staging (scripts/out/rebuild/), 产 *.NEW.csv,
                   然后逐列逐行 diff vs 现有 canonical, 打印「0 差异 PASS」或列出 diff。
                   **绝不动现有 canonical / 中间物** (所有产物落独立 staging 目录)。
  --promote      : 必须 verify 0-diff 才允许; 备份现 canonical -> *.pre_rebuild_REBUILD.bak,
                   staging *.NEW.csv -> 正式 canonical, 再跑 p0f 重冻 PROVENANCE.json。
  --dry-run      : 只打印将执行的步骤链 (每步 read -> write), 不跑任何东西。

============================================================================
跑法 (本脚本我不跑; 主线串行跑)
============================================================================
  python scripts/rebuild_canonical.py --dry-run     # 先看步骤链
  python scripts/rebuild_canonical.py --verify       # 证 0-diff (默认, 不加参数亦可)
  python scripts/rebuild_canonical.py --promote      # verify 0-diff 后才 promote
"""

import sys
import argparse
import shutil
import subprocess
from collections import namedtuple
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── 目录 ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]          # QuantImmuBench/
SCRIPTS = ROOT / "scripts"
PHASE0 = ROOT / "analysis" / "phase0"
OUTDIR = ROOT / "scripts" / "out"
STAGING = OUTDIR / "rebuild"                          # 独立 staging, verify 只写这里
FROZEN = ROOT / "data" / "frozen"

# ── Tier1 冻结输入 (只读起点, 不重跑) ────────────────────────────────────────
BASE_MERGED = OUTDIR / "merged_all_tools_30_official.csv"

# ── deepHLApan raw (Tier-frozen, 只读; 两个: INDEL + SNV110) ──────────────────
CF = SCRIPTS / "out_official" / "coverage_fix"
DEEPHLA_INDEL_RAW = CF / "deephlapan_out_INDEL" / "deephlapan_input_INDEL_predicted_result.csv"
DEEPHLA_SNV110_RAW = CF / "deephlapan_out_SNV110" / "deephlapan_input_SNV110_predicted_result.csv"

# ── 现有 canonical (verify 对照; 仅 promote 覆写) ─────────────────────────────
CANON_9MER = FROZEN / "pooled_clean_9mer.csv"
CANON_8TO11 = FROZEN / "pooled_clean_8to11mer.csv"

# ── staging 中间物 + 最终 pooled ─────────────────────────────────────────────
ST_COVFIX = STAGING / "merged_all_tools_30_official_covfix.csv"
ST_COVFIX_DI = STAGING / "merged_all_tools_30_official_covfix_di.csv"
ST_COVFIX_FINAL = STAGING / "merged_all_tools_30_official_covfix_final.csv"
ST_COVFIX_8TO11 = STAGING / "merged_all_tools_30_official_covfix_8to11.csv"
ST_COVFIX_8TO11_DI = STAGING / "merged_all_tools_30_official_covfix_8to11_di.csv"
ST_COVFIX_8TO11_FINAL = STAGING / "merged_all_tools_30_official_covfix_8to11_final.csv"
ST_POOLED_9MER = STAGING / "pooled_clean_9mer.NEW.csv"
ST_POOLED_8TO11 = STAGING / "pooled_clean_8to11mer.NEW.csv"

PROMOTE_STAMP = "REBUILD"   # 固定占位 (不用 Date.now); 主线 promote 后可自行改名归档
ATOL = 1e-9                 # 浮点格式噪声容忍 (round8 + to_csv 理论应精确一致)

# ── 步骤链 (每步显式 in/out, 无隐式全局状态) ─────────────────────────────────
Step = namedtuple("Step", ["name", "script", "args", "reads", "writes"])


def build_steps():
    """返回有序 Step 列表 (S1..S8)。args 里所有路径都是绝对路径。"""
    steps = [
        # ── 9mer 主分析链 ──
        Step("S1 covfix_8tools(9mer)",
             SCRIPTS / "patch_covfix_8tools.py",
             ["--in", str(BASE_MERGED), "--out", str(ST_COVFIX)],
             [BASE_MERGED], [ST_COVFIX]),
        Step("S2 deephlapan INDEL(9mer)",
             SCRIPTS / "patch_deephlapan_indel.py",
             ["--in", str(ST_COVFIX), "--out", str(ST_COVFIX_DI), "--raw", str(DEEPHLA_INDEL_RAW)],
             [ST_COVFIX, DEEPHLA_INDEL_RAW], [ST_COVFIX_DI]),
        Step("S3 deephlapan SNV110(9mer)",
             SCRIPTS / "patch_deephlapan_indel.py",
             ["--in", str(ST_COVFIX_DI), "--out", str(ST_COVFIX_FINAL), "--raw", str(DEEPHLA_SNV110_RAW)],
             [ST_COVFIX_DI, DEEPHLA_SNV110_RAW], [ST_COVFIX_FINAL]),
        Step("S4 pool --ninemer",
             PHASE0 / "p0e2_pool_clean.py",
             ["--ninemer", "--input", str(ST_COVFIX_FINAL), "--output", str(ST_POOLED_9MER)],
             [ST_COVFIX_FINAL], [ST_POOLED_9MER]),
        # ── 8-11mer 补充链 ──
        Step("S5 covfix_8to11",
             SCRIPTS / "patch_covfix_8to11.py",
             ["--in", str(BASE_MERGED), "--out", str(ST_COVFIX_8TO11)],
             [BASE_MERGED], [ST_COVFIX_8TO11]),
        Step("S6 deephlapan INDEL(8to11)",
             SCRIPTS / "patch_deephlapan_indel.py",
             ["--in", str(ST_COVFIX_8TO11), "--out", str(ST_COVFIX_8TO11_DI), "--raw", str(DEEPHLA_INDEL_RAW)],
             [ST_COVFIX_8TO11, DEEPHLA_INDEL_RAW], [ST_COVFIX_8TO11_DI]),
        Step("S7 deephlapan SNV110(8to11)",
             SCRIPTS / "patch_deephlapan_indel.py",
             ["--in", str(ST_COVFIX_8TO11_DI), "--out", str(ST_COVFIX_8TO11_FINAL), "--raw", str(DEEPHLA_SNV110_RAW)],
             [ST_COVFIX_8TO11_DI, DEEPHLA_SNV110_RAW], [ST_COVFIX_8TO11_FINAL]),
        Step("S8 pool --w811",
             PHASE0 / "p0e2_pool_clean.py",
             ["--w811", "--input", str(ST_COVFIX_8TO11_FINAL), "--output", str(ST_POOLED_8TO11)],
             [ST_COVFIX_8TO11_FINAL], [ST_POOLED_8TO11]),
    ]
    return steps


def _rel(p):
    """打印用: 尽量显示 ROOT 相对路径。"""
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def print_chain(steps):
    print("=" * 78)
    print("Tier1 (冻结, 不重跑): 30 工具 raw -> build_official -> merge_official_30")
    print(f"  base 长表 (只读起点): {_rel(BASE_MERGED)}")
    print("=" * 78)
    for s in steps:
        print(f"\n[{s.name}]  {_rel(s.script)}")
        for r in s.reads:
            print(f"    read  <- {_rel(r)}")
        for w in s.writes:
            print(f"    write -> {_rel(w)}")
        print(f"    cmd: python {_rel(s.script)} {' '.join(s.args)}")
    print("\n" + "=" * 78)
    print("verify diff:")
    print(f"  {_rel(ST_POOLED_9MER)}   vs  {_rel(CANON_9MER)}")
    print(f"  {_rel(ST_POOLED_8TO11)}  vs  {_rel(CANON_8TO11)}")
    print("=" * 78)


def preflight():
    """Tier1 输入 + raw 存在性检查 (fail-loud)。"""
    missing = [p for p in (BASE_MERGED, DEEPHLA_INDEL_RAW, DEEPHLA_SNV110_RAW) if not p.exists()]
    if missing:
        raise SystemExit("[ERR] Tier1/raw 输入缺失:\n  " + "\n  ".join(str(m) for m in missing))


def run_step(s):
    """subprocess 执行单步 (cwd=ROOT, 显式路径参数)。失败即抛。"""
    for r in s.reads:
        if not Path(r).exists():
            raise SystemExit(f"[ERR] {s.name} 输入不存在: {r}")
    cmd = [sys.executable, str(s.script), *s.args]
    print(f"\n{'-'*78}\n[RUN] {s.name}\n  {' '.join(cmd)}\n{'-'*78}")
    res = subprocess.run(cmd, cwd=str(ROOT))
    if res.returncode != 0:
        raise SystemExit(f"[ERR] {s.name} 退出码 {res.returncode} -> 中止")
    for w in s.writes:
        if not Path(w).exists():
            raise SystemExit(f"[ERR] {s.name} 声称写出但文件不存在: {w}")


def run_all_steps(steps):
    STAGING.mkdir(parents=True, exist_ok=True)
    for s in steps:
        run_step(s)


# ── 逐列逐行比对 (区分真差异 vs 浮点格式噪声) ────────────────────────────────
def compare_frames(new_path, canon_path):
    """返回 dict: status(PASS/FAIL) + 明细。数值列 atol=1e-9, 非数值列精确比。"""
    rep = {"new_path": str(new_path), "canon_path": str(canon_path)}
    if not Path(canon_path).exists():
        rep["status"] = "FAIL"
        rep["reason"] = f"canonical 不存在: {canon_path}"
        return rep
    new = pd.read_csv(new_path)
    canon = pd.read_csv(canon_path)
    rep["new_shape"] = tuple(new.shape)
    rep["canon_shape"] = tuple(canon.shape)

    if new.shape != canon.shape:
        rep["status"] = "FAIL"
        rep["reason"] = f"shape 不一致 new={new.shape} canon={canon.shape}"
        return rep
    if list(new.columns) != list(canon.columns):
        only_new = [c for c in new.columns if c not in canon.columns]
        only_canon = [c for c in canon.columns if c not in new.columns]
        order_diff = (set(new.columns) == set(canon.columns))
        rep["status"] = "FAIL"
        rep["reason"] = (f"列不一致 (仅顺序差={order_diff}) only_new={only_new[:8]} "
                         f"only_canon={only_canon[:8]}")
        return rep

    # 快路: 整表精确一致 (NaN==NaN 视相等)
    if new.equals(canon):
        rep["status"] = "PASS"
        rep["exact"] = True
        rep["beyond_atol"] = 0
        rep["float_noise"] = 0
        rep["nonnum_mismatch"] = 0
        return rep

    beyond_atol = 0      # 真数值差 (>atol)
    float_noise = 0      # 数值差但 <=atol (读写浮点格式噪声)
    nonnum_mismatch = 0  # 非数值列不一致
    diff_cols = []       # (col, beyond, noise/nonnum)

    for col in new.columns:
        a, b = new[col], canon[col]
        if a.equals(b):
            continue
        # 数值列路由: 两列都能无损转数值才走数值比对
        both_num = None
        try:
            an = pd.to_numeric(a, errors="raise").to_numpy(dtype=float)
            bn = pd.to_numeric(b, errors="raise").to_numpy(dtype=float)
            both_num = (an, bn)
        except (ValueError, TypeError):
            both_num = None

        if both_num is not None:
            an, bn = both_num
            close = np.isclose(an, bn, atol=ATOL, rtol=0.0, equal_nan=True)
            exact_cell = (an == bn) | (np.isnan(an) & np.isnan(bn))
            n_bad = int((~close).sum())
            n_noise = int((close & ~exact_cell).sum())
            beyond_atol += n_bad
            float_noise += n_noise
            if n_bad or n_noise:
                diff_cols.append((col, n_bad, n_noise))
        else:
            am = a.where(a.notna(), "\x00__NA__").astype(str)
            bm = b.where(b.notna(), "\x00__NA__").astype(str)
            n_bad = int((am.to_numpy() != bm.to_numpy()).sum())
            nonnum_mismatch += n_bad
            if n_bad:
                diff_cols.append((col, n_bad, 0))

    rep["exact"] = False
    rep["beyond_atol"] = beyond_atol
    rep["float_noise"] = float_noise
    rep["nonnum_mismatch"] = nonnum_mismatch
    rep["diff_cols"] = sorted(diff_cols, key=lambda x: -(x[1] + x[2]))[:20]
    # 判据: 真差异(>atol) + 非数值不一致 全为 0 -> PASS (float_noise 允许但显式打印)
    rep["status"] = "PASS" if (beyond_atol == 0 and nonnum_mismatch == 0) else "FAIL"
    return rep


def print_compare(label, rep):
    print(f"\n=== diff [{label}] ===")
    print(f"  new={rep.get('new_shape')}  canon={rep.get('canon_shape')}")
    if "reason" in rep:
        print(f"  [{rep['status']}] {rep['reason']}")
        return
    if rep.get("exact"):
        print(f"  [PASS] 0 差异 (整表精确一致, 逐列逐行 new.equals(canon)=True)")
        return
    print(f"  真数值差(>atol={ATOL}): {rep['beyond_atol']}  "
          f"非数值列不一致: {rep['nonnum_mismatch']}  "
          f"浮点格式噪声(<=atol): {rep['float_noise']}")
    if rep["diff_cols"]:
        print("  差异列 (col, beyond_atol/nonnum, float_noise) top:")
        for col, bad, noise in rep["diff_cols"]:
            print(f"    - {col}: {bad}, {noise}")
    if rep["status"] == "PASS":
        print(f"  [PASS] 0 真差异 (仅 {rep['float_noise']} 格浮点格式噪声 <= {ATOL}, 可容忍)")
    else:
        print(f"  [FAIL] 存在真差异 -> 编排链与现 canonical 不一致, 禁 promote, 查上表列")


def do_verify(run=True):
    """跑全链 (可选) + 比对。返回 True=两表皆 PASS。"""
    steps = build_steps()
    if run:
        preflight()
        run_all_steps(steps)
    rep9 = compare_frames(ST_POOLED_9MER, CANON_9MER)
    rep8 = compare_frames(ST_POOLED_8TO11, CANON_8TO11)
    print("\n" + "=" * 78 + "\nVERIFY 结果 (新链 vs 现 canonical)\n" + "=" * 78)
    print_compare("9mer", rep9)
    print_compare("8to11mer", rep8)
    ok = rep9["status"] == "PASS" and rep8["status"] == "PASS"
    print("\n" + "=" * 78)
    print(f"总判: {'PASS ✅ 编排=现状, 零偏离' if ok else 'FAIL ❌ 有真差异, 见上'}")
    print("=" * 78)
    return ok


def do_promote():
    """verify 0-diff 后: 备份 canonical -> staging 转正 -> 重冻 PROVENANCE。"""
    ok = do_verify(run=True)
    if not ok:
        raise SystemExit("[ABORT] promote 需 verify 0-diff, 当前 FAIL -> 不 promote (canonical 未动)")

    for new_path, canon in ((ST_POOLED_9MER, CANON_9MER), (ST_POOLED_8TO11, CANON_8TO11)):
        bak = canon.with_name(canon.name + f".pre_rebuild_{PROMOTE_STAMP}.bak")
        if canon.exists():
            if bak.exists():
                print(f"[promote] 备份已存在, 保留原 pre-rebuild 状态不覆写: {_rel(bak)}")
            else:
                shutil.copyfile(canon, bak)
                print(f"[promote] 备份 {_rel(canon)} -> {_rel(bak)}")
        shutil.copyfile(new_path, canon)
        print(f"[promote] 转正 {_rel(new_path)} -> {_rel(canon)}")

    # 重冻 PROVENANCE.json
    p0f = PHASE0 / "p0f_freeze_provenance.py"
    print(f"\n[promote] 重冻 PROVENANCE: python {_rel(p0f)}")
    res = subprocess.run([sys.executable, str(p0f)], cwd=str(ROOT))
    if res.returncode != 0:
        raise SystemExit(f"[ERR] p0f 冻结退出码 {res.returncode}")
    print("\n[promote] 完成: canonical 已更新 + PROVENANCE 重冻。旧 canonical 见 *.pre_rebuild_"
          f"{PROMOTE_STAMP}.bak")


def main():
    ap = argparse.ArgumentParser(
        description="QuantImmuBench Tier2 单一真源管道驱动 (编排现有脚本, 零偏离)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--verify", action="store_true", help="跑全链到 staging + diff vs canonical (默认)")
    g.add_argument("--promote", action="store_true", help="verify 0-diff 后转正 + 重冻 (改 canonical)")
    g.add_argument("--dry-run", action="store_true", help="只打印步骤链, 不执行")
    args = ap.parse_args()

    if args.dry_run:
        print_chain(build_steps())
        return

    if args.promote:
        do_promote()
        return

    # 默认 = verify
    ok = do_verify(run=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
