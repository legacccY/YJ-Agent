#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_downstream.py — QuantImmuBench 下游分析重跑驱动 (编排, 非重构)
服务: QuantImmuBench §3.2-§3.4「在干净 canonical 上重跑」
lever: 把散落的 R/S/Q 分析脚本编排成一条确定性驱动, 先备份旧输出(stale, 07-01/07-03
       pre-covfix)再重跑, 让下游结果表更新到 Phase A 干净 canonical。
复现零偏离: 只编排 subprocess + 备份, 绝不改任何 R/S/Q 脚本的计算逻辑。

============================================================================
Phase A canonical (只读输入, 本脚本【不重建】; 由 scripts/rebuild_canonical.py 产)
============================================================================
  9mer 主分析: data/frozen/pooled_clean_9mer.csv    (130×1536, covfix + deephlapan-indel + SNV110)
  8-11mer 补充: data/frozen/pooled_clean_8to11mer.csv (仅 --with-fig1 的 8to11mer 支路用)
  各 R/S/Q 脚本经 _official_common.FROZEN_POOLED 默认指向 9mer canonical; 有 --input 的
  脚本本驱动【显式】传 canonical 路径 (自文档 + 防 default 漂移)。

============================================================================
完整依赖序 + 每步产物 (写回 analysis/official/, 即各脚本 OUT_DIR)
============================================================================
【CORE】 R1-R9 + S1/S2 + Q2 —— 彼此独立, 各自读 canonical, 无 R↔R 依赖 (顺序仅为可读):
  R1_official.py                 canonical -> R1_single_maxpool_official.csv                     (§3.1 表5 max-pool 单工具)
  R2_official.py                 canonical -> R2_pooling_sweep_official.csv, R2_best_per_tool.csv (§3.2 pooling sweep)
  R3_official.py                 canonical -> R3_fusion_12methods_official.csv                    (§3.3 12 融合法)
  R4_official.py                 canonical -> R4_ablation_official.csv                            (§3.3.2 表7 消融)
  R5_official.py                 canonical -> R5_nested_lopo_official.csv + .summary.json         (§3.3.3 表8 nested-LOPO)
  R5_official.py --shuffle       canonical -> R5_nested_lopo_official_shuffle.csv + .summary.json (§3.3.3 shuffle null 对照)
  R6_official.py                 canonical -> R6_robustness_official_results.csv, ..._summary.csv (§3.3 鲁棒性 30 seed×drop)
  R7_official.py                 canonical -> R7_paired_significance_official.csv + .summary.json  (§3.3.5 配对显著性)
  R8_official.py                 canonical -> R8_unified_ranking_official.csv + R8_deployment_official.summary.json (§3.4 统一排名)
  R9_official.py                 canonical -> R9_single_maxpool_pearson_official.csv, R9_perpatient_distribution_official.csv + R9_supplementary_official.summary.json (补充)
  S1_peptide_level_auprc.py      canonical -> S1_peptide_auprc.csv, S1_peptide_auprc_paired.csv   (补充 肽级 AUPRC; 无 argparse, 硬读 canonical)
  S2_regime_compare.py           canonical(+legacy frozen) -> S2_regime_compare.csv               (regime 对照; legacy=frozen 输入非 stale 输出, 见风险§)
  Q2_rank_corr_matrix.py         canonical -> Q2_rank_corr_matrix.csv, ..._pooled.csv, Q2_rank_corr_perpatient.json (方法间 rank 相关)
  Q2_fusion_kinship_paired.py    canonical -> Q2_fusion_kinship_paired.csv                        (融合亲缘配对)
  Q2_peptide_auprc_kinship.py    canonical -> Q2_peptide_auprc_kinship.csv                        (肽级 AUPRC 亲缘; 无 argparse, 硬读 canonical)

【R10】 --with-r10 (opt-in): 预注册特征融合子链 (PREREG_R10_featfusion.md); 输出**从未生成过**,
        此组是 GENERATE-NEW 非 refresh-stale。内部有严格依赖链 (feature -> lopo -> eval):
  R10_feature_builder.py         canonical(+GT) -> R10_featfusion_features.csv, R10_featfusion_manifest.json
  R10_leak_free_lopo.py          features+manifest -> R10_featfusion_oof.csv
  R10_leak_free_lopo.py --shuffle features+manifest -> R10_featfusion_oof_shuffle.csv (shuffle null)
  R10_eval_dual.py               oof(+oof_shuffle)+canonical -> R10_featfusion_eval_main.csv, ..._eval_auprc.csv, ..._eval_summary.json

【FIG1】 --with-fig1 (opt-in): §3.1 图1 effN 修正链。**07-04 已在 canonical 上重跑过(fresh)**,
        默认不再跑; 仅当 canonical 再次变动时才需。内部 recompute -> plot 依赖:
  recompute_effN/recompute_R1_effN.py                          9mer canonical    -> R1_recomputed_effN{3,5,8,10}.csv, R1_compare_orig_vs_effN.csv, R1_effN_sensitivity_5_8_10.csv
  recompute_effN/recompute_R1_effN.py --input 8to11 --tag 8to11mer  8to11 canonical -> R1_recomputed_8to11mer_effN{3,5,8,10}.csv, R1_effN_sensitivity_8to11mer_5_8_10.csv
  recompute_effN/plot_R1_effN.py                               R1_recomputed_effN8.csv -> fig1_spearman_30tools_9mer_effN8.png + paper/figures/*.pdf
  recompute_effN/plot_R1_effN.py --input ... --tag 8to11mer    R1_recomputed_8to11mer_effN8.csv -> fig1_spearman_30tools_8to11mer_effN8.png + paper/figures/*.pdf
  recompute_effN/plot_9mer_vs_8to11mer.py                      两个 effN8 csv + 8to11 canonical -> paper/figures/fig_9mer_vs_8to11mer_spearman.{png,pdf}, fig_8to11mer_coverage.{png,pdf}

============================================================================
【故意排除, 不编排 —— 见回执风险§, 由主线判】
============================================================================
  compute_netAffneg_topk20eq.py    —— 读 Tier1 base 长表 (scripts/out/merged_all_tools_30_official.csv,
      pre-covfix 冻结边界), 写 data/frozen/netAffneg_topk20eq_official.csv。**非 canonical 下游**,
      不属本驱动范畴; base 长表未变故无需刷新。
  compare_countclean_vs_dirty.py   —— DIAG, 依赖冻结表 count_conf_<tool>_<pooling> 布尔列, 但 B2 干净
      canonical 已【不再带 count_conf 列】(见 _official_common.py 注); 在 canonical 上跑会崩/退化。
      是已退役的 count-clean 旧范式诊断, 不刷新。
  孤儿 stale 输出 (无当前生产脚本, 仅 --backup 备份, 不重跑):
      DIAG_peptide_level_auprc.csv, DIAG_within_patient_consistency.csv, figures/DIAG_power_rescue.png

============================================================================
模式
============================================================================
  --backup   : 仅把当前 analysis/official/ 下 stale 结果 (*.csv/*.json + figures + recompute_effN
               产物) 复制到 analysis/official/_pre_covfix_backup_REBUILD/ (固定占位 REBUILD, 不用
               时间戳), 供 analyst diff 老 vs 新。不跑任何分析。
  --run (默认): 先 --backup, 再按依赖序 subprocess 跑 CORE (+ 可选 --with-r10 / --with-fig1)。
               每步打印 [RUN] <script> + 退出码; 任一步非零退出立即中止并打印失败脚本 (不静默续跑)。
  --dry-run  : 只打印将跑的脚本顺序 + 每步 read -> write, 不备份不执行。

============================================================================
跑法 (本脚本我不跑; 主线串行跑)
============================================================================
  python analysis/official/run_downstream.py --dry-run              # 先看步骤链
  python analysis/official/run_downstream.py --dry-run --with-r10 --with-fig1  # 看含 opt-in 的全链
  python analysis/official/run_downstream.py --backup               # 只备份 stale (可先单独跑一次)
  python analysis/official/run_downstream.py                        # = --run: 备份 + 重跑 CORE
  python analysis/official/run_downstream.py --with-r10             # CORE + 预注册 R10 子链

  # ── 新切「定点切窗」9mer canonical 上重跑 CORE (输出隔离到独立子目录, 不碰旧切) ──
  # --input-canonical 换主分析表, --outdir 把全体输出经 env QIB_OUTDIR 重定向; 二者须同时给。
  # 新切自动跳过无 argparse 的 S1/S2/Q2_peptide (硬读 FROZEN_POOLED 改不了输入); 禁 --with-r10/fig1。
  python analysis/official/run_downstream.py --dry-run \
      --input-canonical data/frozen/pooled_clean_rerun_9mer.csv --outdir newcut9mer   # 先看新切链
  python analysis/official/run_downstream.py \
      --input-canonical data/frozen/pooled_clean_rerun_9mer.csv --outdir newcut9mer   # 跑新切 CORE
"""

import os
import sys
import argparse
import shutil
import subprocess
from collections import namedtuple
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── 目录 ────────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent                  # analysis/official/
ANALYSIS = HERE.parent                                  # analysis/
ROOT = ANALYSIS.parent                                  # QuantImmuBench/
OFFICIAL = HERE
RECOMPUTE = HERE / "recompute_effN"
FIGURES = HERE / "figures"

# ── Phase A canonical (只读输入) ─────────────────────────────────────────────
FROZEN = ROOT / "data" / "frozen"
CANON_9MER = FROZEN / "pooled_clean_9mer.csv"
CANON_8TO11 = FROZEN / "pooled_clean_8to11mer.csv"

# ── 备份目标 (固定占位 REBUILD, 主线可自行改名归档) ──────────────────────────
BACKUP_STAMP = "REBUILD"
BACKUP_DIR = OFFICIAL / f"_pre_covfix_backup_{BACKUP_STAMP}"

# ── 步骤 (每步显式 in/out, 无隐式全局状态; group 供分组打印) ──────────────────
Step = namedtuple("Step", ["name", "script", "args", "reads", "writes", "group"])


def build_core_steps(canon=CANON_9MER, out=OFFICIAL, include_noarg=True):
    """CORE: R1-R9 + S1/S2 + Q2。彼此独立读 canonical, 顺序仅为可读性 (无 R↔R 依赖)。
    有 --input 的脚本显式传 canonical; 无 argparse 的 (S1/S2/Q2_peptide) 硬读 FROZEN_POOLED。

    canon : 主分析 canonical 路径 (默认旧切 9mer; 新切经 --input-canonical 覆盖)。
    out   : 输出目录 (默认 OFFICIAL=analysis/official/; 新切经 --outdir 重定向, 与子进程 env
            QIB_OUTDIR 同一目录, 保 writes 存在性校验对齐实际落盘)。
    include_noarg : False 时剔除无 --input、硬读 _official_common.FROZEN_POOLED 的补充步
            (S1/S2/Q2_peptide) —— 新切下这些脚本无法改输入源, 若跑会用错(旧)输入产出, 故新切
            一律跳过 (task 派单: 跳过无 argparse 硬读 FROZEN_POOLED 的补充脚本)。"""
    C = str(canon)
    inp = ["--input", C]
    steps = [
        Step("R1 max-pool 单工具(§3.1 表5)", OFFICIAL / "R1_official.py", inp,
             [canon], [out / "R1_single_maxpool_official.csv"], "CORE"),
        Step("R2 pooling sweep(§3.2)", OFFICIAL / "R2_official.py", inp,
             [canon], [out / "R2_pooling_sweep_official.csv",
                       out / "R2_best_per_tool.csv"], "CORE"),
        Step("R3 12 融合法(§3.3)", OFFICIAL / "R3_official.py", inp,
             [canon], [out / "R3_fusion_12methods_official.csv"], "CORE"),
        Step("R4 维度消融(§3.3.2 表7)", OFFICIAL / "R4_official.py", inp,
             [canon], [out / "R4_ablation_official.csv"], "CORE"),
        Step("R5 nested-LOPO(§3.3.3 表8)", OFFICIAL / "R5_official.py", inp,
             [canon], [out / "R5_nested_lopo_official.csv",
                       out / "R5_nested_lopo_official.summary.json"], "CORE"),
        Step("R5 shuffle null(§3.3.3)", OFFICIAL / "R5_official.py", inp + ["--shuffle"],
             [canon], [out / "R5_nested_lopo_official_shuffle.csv",
                       out / "R5_nested_lopo_official_shuffle.summary.json"], "CORE"),
        Step("R6 鲁棒性(§3.3)", OFFICIAL / "R6_official.py", inp,
             [canon], [out / "R6_robustness_official_results.csv",
                       out / "R6_robustness_official_summary.csv"], "CORE"),
        Step("R7 配对显著性(§3.3.5)", OFFICIAL / "R7_official.py", inp,
             [canon], [out / "R7_paired_significance_official.csv",
                       out / "R7_paired_significance_official.summary.json"], "CORE"),
        Step("R8 统一排名+部署(§3.4)", OFFICIAL / "R8_official.py", inp,
             [canon], [out / "R8_unified_ranking_official.csv",
                       out / "R8_deployment_official.summary.json"], "CORE"),
        Step("R9 Pearson+分布(补充)", OFFICIAL / "R9_official.py", inp,
             [canon], [out / "R9_single_maxpool_pearson_official.csv",
                       out / "R9_perpatient_distribution_official.csv",
                       out / "R9_supplementary_official.summary.json"], "CORE"),
        # 无 argparse 的三个: 硬读 _official_common.FROZEN_POOLED (=9mer canonical); 新切跳过 (见 docstring)
        Step("S1 肽级 AUPRC(补充)", OFFICIAL / "S1_peptide_level_auprc.py", [],
             [canon], [out / "S1_peptide_auprc.csv",
                       out / "S1_peptide_auprc_paired.csv"], "CORE"),
        Step("S2 regime 对照", OFFICIAL / "S2_regime_compare.py", [],
             [canon], [out / "S2_regime_compare.csv"], "CORE"),
        Step("Q2 rank 相关矩阵", OFFICIAL / "Q2_rank_corr_matrix.py", inp,
             [canon], [out / "Q2_rank_corr_matrix.csv",
                       out / "Q2_rank_corr_matrix_pooled.csv",
                       out / "Q2_rank_corr_perpatient.json"], "CORE"),
        Step("Q2 融合亲缘配对", OFFICIAL / "Q2_fusion_kinship_paired.py", inp,
             [canon], [out / "Q2_fusion_kinship_paired.csv"], "CORE"),
        Step("Q2 肽级 AUPRC 亲缘", OFFICIAL / "Q2_peptide_auprc_kinship.py", [],
             [canon], [out / "Q2_peptide_auprc_kinship.csv"], "CORE"),
    ]
    if not include_noarg:
        steps = [s for s in steps if "--input" in s.args]   # 剔 S1/S2/Q2_peptide (硬读 FROZEN_POOLED)
    return steps


def build_r10_steps():
    """R10 预注册特征融合子链 (opt-in)。内部严格依赖: feature -> lopo(+shuffle) -> eval。
    ⚠ 输出从未生成过 = GENERATE-NEW (非 refresh)。feature_builder 有 --input; lopo/eval 读
    上游产物 (--features/--manifest/--oof 默认已指向同目录产物, 不必传)。"""
    C = str(CANON_9MER)
    steps = [
        Step("R10 特征构建", OFFICIAL / "R10_feature_builder.py", ["--input", C],
             [CANON_9MER], [OFFICIAL / "R10_featfusion_features.csv",
                            OFFICIAL / "R10_featfusion_manifest.json"], "R10"),
        Step("R10 leak-free LOPO", OFFICIAL / "R10_leak_free_lopo.py", [],
             [OFFICIAL / "R10_featfusion_features.csv",
              OFFICIAL / "R10_featfusion_manifest.json"],
             [OFFICIAL / "R10_featfusion_oof.csv"], "R10"),
        Step("R10 leak-free LOPO shuffle", OFFICIAL / "R10_leak_free_lopo.py", ["--shuffle"],
             [OFFICIAL / "R10_featfusion_features.csv",
              OFFICIAL / "R10_featfusion_manifest.json"],
             [OFFICIAL / "R10_featfusion_oof_shuffle.csv"], "R10"),
        Step("R10 dual 评测", OFFICIAL / "R10_eval_dual.py", ["--input", C],
             [OFFICIAL / "R10_featfusion_oof.csv", CANON_9MER],
             [OFFICIAL / "R10_featfusion_eval_main.csv",
              OFFICIAL / "R10_featfusion_eval_auprc.csv",
              OFFICIAL / "R10_featfusion_eval_summary.json"], "R10"),
    ]
    return steps


def build_fig1_steps():
    """§3.1 图1 effN 修正链 (opt-in)。07-04 已 fresh; 仅 canonical 再变时才需。
    内部依赖: recompute(9mer/8to11) -> plot。recompute --input 相对路径按 ROOT 解析,
    plot --input 相对路径按 recompute_effN/ 目录解析 (故传纯文件名)。"""
    steps = [
        Step("fig1 recompute 9mer", RECOMPUTE / "recompute_R1_effN.py", [],
             [CANON_9MER], [RECOMPUTE / "R1_recomputed_effN8.csv",
                            RECOMPUTE / "R1_effN_sensitivity_5_8_10.csv"], "FIG1"),
        Step("fig1 recompute 8to11mer", RECOMPUTE / "recompute_R1_effN.py",
             ["--input", str(CANON_8TO11), "--tag", "8to11mer"],
             [CANON_8TO11], [RECOMPUTE / "R1_recomputed_8to11mer_effN8.csv",
                             RECOMPUTE / "R1_effN_sensitivity_8to11mer_5_8_10.csv"], "FIG1"),
        Step("fig1 plot 9mer", RECOMPUTE / "plot_R1_effN.py", [],
             [RECOMPUTE / "R1_recomputed_effN8.csv"],
             [RECOMPUTE / "fig1_spearman_30tools_9mer_effN8.png"], "FIG1"),
        Step("fig1 plot 8to11mer", RECOMPUTE / "plot_R1_effN.py",
             ["--input", "R1_recomputed_8to11mer_effN8.csv", "--tag", "8to11mer",
              "--lenlabel", "8-11mer"],
             [RECOMPUTE / "R1_recomputed_8to11mer_effN8.csv"],
             [RECOMPUTE / "fig1_spearman_30tools_8to11mer_effN8.png"], "FIG1"),
        Step("fig1 plot 9mer vs 8to11mer", RECOMPUTE / "plot_9mer_vs_8to11mer.py", [],
             [RECOMPUTE / "R1_recomputed_effN8.csv",
              RECOMPUTE / "R1_recomputed_8to11mer_effN8.csv", CANON_8TO11],
             [ROOT / "paper" / "figures" / "fig_9mer_vs_8to11mer_spearman.pdf",
              ROOT / "paper" / "figures" / "fig_8to11mer_coverage.pdf"], "FIG1"),
    ]
    return steps


def assemble_steps(canon=CANON_9MER, out=OFFICIAL, include_noarg=True,
                   with_r10=False, with_fig1=False):
    """组装步骤链。canon/out/include_noarg 仅作用于 CORE (R1-R9/S1/S2/Q2, 全经 --input 或
    ensure_out_dir 认 QIB_OUTDIR 隔离)。R10/FIG1 opt-in 子链内部有默认路径/自身 OUT_DIR 假设,
    不认输出隔离, 故只在默认切 (canon=CANON_9MER, out=OFFICIAL) 编排 —— main 已守新切禁混用。"""
    steps = build_core_steps(canon, out, include_noarg)
    if with_r10:
        steps += build_r10_steps()
    if with_fig1:
        steps += build_fig1_steps()
    return steps


def _rel(p):
    """打印用: 尽量显示 ROOT 相对路径。"""
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def print_chain(steps, canon=CANON_9MER, out=OFFICIAL):
    print("=" * 78)
    print("Phase A canonical (只读输入, 本脚本不重建):")
    print(f"  主分析 canonical: {_rel(canon)}"
          + ("" if canon == CANON_9MER else "  ★新切 (--input-canonical)"))
    print(f"  8-11mer 补充:     {_rel(CANON_8TO11)}  (仅 FIG1 8to11mer 支路)")
    print(f"  输出目录:         {_rel(out)}"
          + ("" if out == OFFICIAL else "  ★重定向 (--outdir / env QIB_OUTDIR)"))
    print("=" * 78)
    cur_group = None
    for i, s in enumerate(steps, 1):
        if s.group != cur_group:
            cur_group = s.group
            print(f"\n----- 组 [{cur_group}] -----")
        print(f"\n[{i:02d}] {s.name}  ({_rel(s.script)})")
        for r in s.reads:
            print(f"     read  <- {_rel(r)}")
        for w in s.writes:
            print(f"     write -> {_rel(w)}")
        cmd = f"python {_rel(s.script)}" + ("" if not s.args else " " + " ".join(s.args))
        print(f"     cmd: {cmd}")
    print("\n" + "=" * 78)
    print(f"共 {len(steps)} 步。故意排除 (不编排, 见 docstring 风险§): compute_netAffneg_topk20eq.py,"
          " compare_countclean_vs_dirty.py, 孤儿 DIAG_*。")
    print("=" * 78)


# ── 备份 (stale 结果 -> _pre_covfix_backup_REBUILD/, 保留相对结构) ────────────
# 只备份【结果产物】(*.csv/*.json + 图), 不备份 .py 脚本 / __pycache__ / 备份目录自身。
BACKUP_GLOBS = [
    "*.csv",
    "*.json",
    "figures/*.png",
    "recompute_effN/*.csv",
    "recompute_effN/*.png",
]


def backup():
    """把当前 stale 结果复制到 BACKUP_DIR, 保留相对 OFFICIAL 的子目录结构。幂等: 已存在则跳过。"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    skipped = 0
    for pat in BACKUP_GLOBS:
        for src in sorted(OFFICIAL.glob(pat)):
            # 排除备份目录自身内的文件 (防递归)
            if BACKUP_DIR in src.resolve().parents or src.resolve() == BACKUP_DIR:
                continue
            if not src.is_file():
                continue
            rel = src.relative_to(OFFICIAL)
            dst = BACKUP_DIR / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                skipped += 1
                continue
            shutil.copy2(src, dst)
            copied += 1
    print(f"[backup] stale 结果 -> {_rel(BACKUP_DIR)}  (新复制 {copied} 个, 已存在跳过 {skipped} 个)")
    print(f"[backup] 供 analyst diff: 老(备份) vs 新(重跑后 analysis/official/)。")


# ── 逐步执行 (subprocess, 失败即抛非零退出) ───────────────────────────────────
def run_step(s, idx, total, env=None):
    for r in s.reads:
        if not Path(r).exists():
            raise SystemExit(f"[ERR] [{idx}/{total}] {s.name} 输入不存在, 中止: {r}")
    cmd = [sys.executable, str(s.script), *s.args]
    print(f"\n{'-' * 78}")
    print(f"[RUN] [{idx}/{total}] {s.name}")
    print(f"  {' '.join(cmd)}")
    print(f"{'-' * 78}")
    res = subprocess.run(cmd, cwd=str(ROOT), env=env)
    print(f"[exit] [{idx}/{total}] {s.name} -> returncode={res.returncode}")
    if res.returncode != 0:
        # 立即停, 打印失败脚本, 非零退出 (绝不 [ERR] 后还 exit 0)
        raise SystemExit(f"[ABORT] 步骤失败: {s.name}  ({_rel(s.script)})  退出码={res.returncode}")
    # 写出存在性校验 (脚本声称写了却没写 = 视为失败)
    missing = [w for w in s.writes if not Path(w).exists()]
    if missing:
        raise SystemExit(f"[ABORT] {s.name} 退出 0 但声称的产物缺失: "
                         + ", ".join(_rel(m) for m in missing))


def run_all(steps, env=None):
    total = len(steps)
    for i, s in enumerate(steps, 1):
        run_step(s, i, total, env=env)
    print("\n" + "=" * 78)
    print(f"[DONE] 全部 {total} 步成功, 下游结果表已刷新到 Phase A canonical。")
    print("=" * 78)


def preflight(steps, canon=CANON_9MER):
    """canonical + 所有待跑脚本存在性检查 (fail-loud, 跑前一次性核清)。"""
    need_canon = {canon}
    if any(s.group == "FIG1" for s in steps):
        need_canon.add(CANON_8TO11)
    miss_canon = [c for c in need_canon if not c.exists()]
    if miss_canon:
        raise SystemExit("[ERR] canonical 缺失 (先跑 scripts/rebuild_canonical.py):\n  "
                         + "\n  ".join(str(m) for m in miss_canon))
    miss_scripts = sorted({str(s.script) for s in steps if not s.script.exists()})
    if miss_scripts:
        raise SystemExit("[ERR] 分析脚本缺失:\n  " + "\n  ".join(miss_scripts))


def main():
    ap = argparse.ArgumentParser(
        description="QuantImmuBench 下游分析重跑驱动 (编排 R/S/Q, 零偏离; 先备份再重跑)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--run", action="store_true", help="先备份再按依赖序重跑 (默认)")
    g.add_argument("--backup", action="store_true", help="仅备份当前 stale 结果, 不重跑")
    g.add_argument("--dry-run", action="store_true", help="只打印步骤链, 不备份不执行")
    ap.add_argument("--with-r10", action="store_true",
                    help="含 R10 预注册特征融合子链 (opt-in; 输出从未生成过=GENERATE-NEW)")
    ap.add_argument("--with-fig1", action="store_true",
                    help="含 §3.1 图1 effN 链 (opt-in; 07-04 已 fresh, 仅 canonical 再变时需)")
    # ── 新切「定点切窗」入口 (薄封装; 默认不传 → 行为逐字节等于旧切) ──
    ap.add_argument("--input-canonical", default=None,
                    help="新切 canonical 主分析表路径 (默认=旧切 pooled_clean_9mer.csv)。设了则所有有 "
                         "--input 的 CORE 子步骤读它; 必须配 --outdir 写独立目录 (防覆盖旧切结果)。")
    ap.add_argument("--outdir", default=None,
                    help="输出目录 (子目录名按 analysis/official/<名> 解析, 或绝对路径)。设了则经 env "
                         "QIB_OUTDIR 把全体 R/S/Q 输出重定向到此目录 (防覆盖旧切 + 并行踩踏)。")
    args = ap.parse_args()

    # ── 新切参数解析 ──
    new_cut = args.input_canonical is not None or args.outdir is not None

    if args.input_canonical is not None:
        canon = Path(args.input_canonical).resolve()
        if args.outdir is None:
            raise SystemExit("[ERR] --input-canonical 必须配 --outdir (否则新切结果会覆盖旧切默认目录)。")
    else:
        canon = CANON_9MER

    if args.outdir is not None:
        od = Path(args.outdir)
        if not od.is_absolute():
            od = OFFICIAL / od                      # 子目录名 -> analysis/official/<名>
        out_dir = od.resolve()
    else:
        out_dir = OFFICIAL

    # opt-in 子链 R10/FIG1 内部有默认路径 (R10 --features/--manifest 默认 HERE/) / 自身 OUT_DIR
    # (FIG1 recompute_effN 脚本), 均【不认】QIB_OUTDIR 输出隔离 → 禁与新切混用 (防串目录/覆盖)。
    if new_cut and (args.with_r10 or args.with_fig1):
        raise SystemExit(
            "[ERR] --with-r10 / --with-fig1 不支持与 --input-canonical / --outdir 混用 "
            "(R10 子链默认读同目录产物、FIG1 recompute 脚本用自身 OUT_DIR, 均不认 QIB_OUTDIR "
            "输出隔离)。新切请只跑 CORE; opt-in 子链在默认切单独跑。")

    include_noarg = not new_cut         # 新切跳过无 --input 硬读 FROZEN_POOLED 的 S1/S2/Q2_peptide
    steps = assemble_steps(canon=canon, out=out_dir, include_noarg=include_noarg,
                           with_r10=args.with_r10, with_fig1=args.with_fig1)

    # 子进程环境: 设了 --outdir 就注入 QIB_OUTDIR, 让各脚本 ensure_out_dir/resolve_out_dir 重定向输出。
    env = None
    if args.outdir is not None:
        env = dict(os.environ)
        env["QIB_OUTDIR"] = str(out_dir)

    if args.dry_run:
        print_chain(steps, canon, out_dir)
        return

    if args.backup:
        if new_cut:
            print("[backup] 新切写独立目录, 无 stale 可覆盖, 跳过 backup。")
        else:
            backup()
        return

    # 默认 = --run
    preflight(steps, canon)
    if new_cut:
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"[newcut] 输入 canonical = {canon}")
        print(f"[newcut] 输出重定向 -> {out_dir}  (env QIB_OUTDIR, 跳过 backup: 新目录无 stale)")
    else:
        backup()                        # 旧切原地刷新: 先备份 stale
    run_all(steps, env=env)


if __name__ == "__main__":
    main()
