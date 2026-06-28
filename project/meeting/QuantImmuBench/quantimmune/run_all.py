#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_all.py
==========
服务: quantimmu-bench F-pilot — R0→R11 实验矩阵编排脚本
约束对齐: LEDGER §5 九约束执行顺序 (R0 打乱最先, R1 IEDB 次之, R2 去偏地板, ...)

说明
----
  本脚本不自动执行任何命令 (--dry-run 默认开启).
  运行后打印 R0-R11 全部命令及说明, 主线手动逐步跑.
  --run R0  可单步执行某个 run (通过 subprocess).
  ⚠️  建议主线逐条运行, 确认每步结果后再推进.

前置条件
--------
  1. build_model_matrix.py 已跑完 → quantimmune/model_matrix.csv 存在
  2. analysis/iedb_overlap_whitelist.csv 已生成 (R11 需要; R1 生成)
  3. data/iedb_tcell_full.csv 存在 (R1 需要; 如无则 R1 报告指引下载)

执行顺序 (LEDGER §5 验证优先级)
---------------------------------
  R0  标签打乱 3 种子 (防泄漏对照, **必须归零才算管道干净**, LEDGER 约束⑤)
  R1  IEDB overlap check (量化泄漏肽比例, LEDGER 约束⑥)
  R2  去偏地板复算 FixAvg (同 LOPO 重算地板, LEDGER 约束③)
  R3  Ridge-HR surv6 主模型 (LEDGER §3 命门: eff_DOF≈2-3)
  R4  Ridge-HR surv6+seq (H3 序列特征增量, LEDGER §2 H3 假设)
  R5  配对 bootstrap R3 vs R2 (主模型 vs 去偏地板, LEDGER 约束①②)
  R6  All9 特征集 Ridge (死工具包含, 敏感性, LEDGER 约束⑨)
  R7  Patient-centered 目标 (防患者均值代理, LEDGER 约束⑦)
  R8  GBDT 敏感性对照 (仅参考, LEDGER 约束⑨)
  R9  redundant-pruned 特征集 (IMPROVE-PRIME 冗余剪枝敏感性)
  R10 配对 bootstrap R4 vs R2 (seq+surv6 vs 地板, H3 增量估计)
  R11 IEDB 白名单过滤敏感性 (依赖 R1 产出 whitelist)

跑法
----
  python quantimmune/run_all.py            # 打印全部命令 (dry-run)
  python quantimmune/run_all.py --run R0   # 执行 R0 所有命令
  python quantimmune/run_all.py --run R3   # 执行 R3
  python quantimmune/run_all.py --list     # 仅列标题不展开命令
"""

import sys
import subprocess
import argparse
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# ── 实验矩阵定义 ──────────────────────────────────────────────────────────────
# 每条 run: (id, title, commands_list, notes)
# commands_list: 每项是 (描述, 命令字符串)
# 路径用相对于 ROOT 的形式 (方便主线在 ROOT 下执行)

RUNS = [
    # ─ R0 ─────────────────────────────────────────────────────────────────────
    {
        "id": "R0",
        "title": "标签打乱防泄漏对照 (LEDGER §5 约束⑤)",
        "notes": (
            "期望: 3 个种子下 DS2 Fisher-z ρ̄ ≈ 0 (|ρ̄| < 0.1).\n"
            "若 ρ̄ > 0.1 → 管道有泄漏, 停止后续运行先排查."
        ),
        "cmds": [
            ("Ridge surv6 shuffle seed=42",
             "python quantimmune/lopo_eval.py --model ridge --features surv6 --target raw_sfc --shuffle --seed 42"),
            ("Ridge surv6 shuffle seed=123",
             "python quantimmune/lopo_eval.py --model ridge --features surv6 --target raw_sfc --shuffle --seed 123"),
            ("Ridge surv6 shuffle seed=999",
             "python quantimmune/lopo_eval.py --model ridge --features surv6 --target raw_sfc --shuffle --seed 999"),
            ("FixAvg surv6 shuffle seed=42",
             "python quantimmune/lopo_eval.py --model fixavg --features surv6 --target raw_sfc --shuffle --seed 42"),
        ],
    },

    # ─ R1 ─────────────────────────────────────────────────────────────────────
    {
        "id": "R1",
        "title": "IEDB overlap 量化 (LEDGER §5 约束⑥)",
        "notes": (
            "需要 data/iedb_tcell_full.csv (IEDB 下载, 见脚本内指引).\n"
            "产出: analysis/iedb_overlap_whitelist.csv (R11 用).\n"
            "报告 overlap 比例 + 提示 AUC 乐观偏差."
        ),
        "cmds": [
            ("IEDB overlap check",
             "python analysis/iedb_overlap_check.py --iedb data/iedb_tcell_full.csv"),
        ],
    },

    # ─ R2 ─────────────────────────────────────────────────────────────────────
    {
        "id": "R2",
        "title": "去偏地板复算 FixAvg (LEDGER §5 约束③)",
        "notes": (
            "在**同 15 患者、同 LOPO 折**重算等权免疫原性集成地板.\n"
            "这是主结论对比 baseline (不是事后取最优单工具).\n"
            "输出 DS2 Fisher-z ρ̄ 即预登记地板."
        ),
        "cmds": [
            ("FixAvg surv6 raw_sfc (去偏地板)",
             "python quantimmune/lopo_eval.py --model fixavg --features surv6 --target raw_sfc"),
        ],
    },

    # ─ R3 ─────────────────────────────────────────────────────────────────────
    {
        "id": "R3",
        "title": "Ridge-HR surv6 主模型 (LEDGER §3 命门定理)",
        "notes": (
            "主力模型: surv6 特征 + 强正则 Ridge (eff_DOF≈2-3).\n"
            "检查: 1) eff_DOF 是否在 2-3 区间; 2) 权重是否塌单工具 (H2 验证).\n"
            "期望 LEDGER §4 中性档: DS2 Fisher-z ρ̄ ≈ 0.27-0.33."
        ),
        "cmds": [
            ("Ridge surv6 raw_sfc (主模型)",
             "python quantimmune/lopo_eval.py --model ridge --features surv6 --target raw_sfc"),
        ],
    },

    # ─ R4 ─────────────────────────────────────────────────────────────────────
    {
        "id": "R4",
        "title": "Ridge-HR surv6+seq 序列特征增量 (H3 假设, LEDGER §2)",
        "notes": (
            "加入 Tier-1 序列特征 (BLOSUM62 距离/KD 疏水/芳香比等).\n"
            "对比 R3: Δ(surv6+seq - surv6) 若 >0 → H3 部分兑现.\n"
            "若 Δ≈0 → 序列信号已被工具吸收, H3 否."
        ),
        "cmds": [
            ("Ridge surv6+seq raw_sfc (H3 验证)",
             "python quantimmune/lopo_eval.py --model ridge --features surv6+seq --target raw_sfc"),
        ],
    },

    # ─ R5 ─────────────────────────────────────────────────────────────────────
    {
        "id": "R5",
        "title": "配对 bootstrap: R3 (Ridge) vs R2 (FixAvg 地板)",
        "notes": (
            "主结论效应量估计: 元模型 vs 去偏地板.\n"
            "读数: Δz̄ 点估 + 95% CI + P(Δ>0).\n"
            "需要 R2 和 R3 已完成."
        ),
        "cmds": [
            ("配对 bootstrap Ridge vs FixAvg",
             "python quantimmune/paired_bootstrap.py "
             "--meta quantimmune/results/lopo_ridge_surv6_raw_sfc.per_patient.csv "
             "--baseline quantimmune/results/lopo_fixavg_surv6_raw_sfc.per_patient.csv"),
        ],
    },

    # ─ R6 ─────────────────────────────────────────────────────────────────────
    {
        "id": "R6",
        "title": "All9 特征集敏感性 (含死工具, LEDGER §5 约束⑨)",
        "notes": (
            "包含 DeepImmuno/NeoTImmuML/HLAthena 死工具.\n"
            "期望: 比 surv6 差 (死工具注入噪声, eff_DOF 更难控制)."
        ),
        "cmds": [
            ("Ridge all9 raw_sfc (含死工具)",
             "python quantimmune/lopo_eval.py --model ridge --features all9 --target raw_sfc"),
        ],
    },

    # ─ R7 ─────────────────────────────────────────────────────────────────────
    {
        "id": "R7",
        "title": "Patient-centered 目标 (LEDGER §5 约束⑦)",
        "notes": (
            "训练目标换成患者内中心化 SFC (防 ridge 用工具分当患者均值代理).\n"
            "对比 R3 看中心化是否改变 LOPO ρ."
        ),
        "cmds": [
            ("Ridge surv6 patient_centered",
             "python quantimmune/lopo_eval.py --model ridge --features surv6 --target patient_centered"),
        ],
    },

    # ─ R8 ─────────────────────────────────────────────────────────────────────
    {
        "id": "R8",
        "title": "GBDT 敏感性对照 (LEDGER §5 约束⑨)",
        "notes": (
            "GradientBoosting max_depth<=2, 仅敏感性.\n"
            "期望: 因 n=183 小, GBDT 泛化差于 Ridge."
        ),
        "cmds": [
            ("GBDT surv6 raw_sfc (敏感性)",
             "python quantimmune/lopo_eval.py --model gbdt --features surv6 --target raw_sfc"),
        ],
    },

    # ─ R9 ─────────────────────────────────────────────────────────────────────
    {
        "id": "R9",
        "title": "redundant-pruned 特征集 (IMPROVE-PRIME 冗余剪枝)",
        "notes": (
            "surv6 去掉 IMPROVE (r=0.69 with PRIME, 留 PRIME).\n"
            "验证冗余剪枝是否提升 LOPO ρ."
        ),
        "cmds": [
            ("Ridge redundant-pruned raw_sfc",
             "python quantimmune/lopo_eval.py --model ridge --features redundant-pruned --target raw_sfc"),
        ],
    },

    # ─ R10 ────────────────────────────────────────────────────────────────────
    {
        "id": "R10",
        "title": "配对 bootstrap: R4 (surv6+seq) vs R2 (FixAvg 地板)",
        "notes": (
            "序列特征增量 vs 地板: H3 假设增量有多大?\n"
            "需要 R2 和 R4 已完成."
        ),
        "cmds": [
            ("配对 bootstrap surv6+seq vs FixAvg",
             "python quantimmune/paired_bootstrap.py "
             "--meta quantimmune/results/lopo_ridge_surv6_seq_raw_sfc.per_patient.csv "
             "--baseline quantimmune/results/lopo_fixavg_surv6_raw_sfc.per_patient.csv"),
        ],
    },

    # ─ R11 ────────────────────────────────────────────────────────────────────
    {
        "id": "R11",
        "title": "IEDB 白名单过滤敏感性 (依赖 R1, LEDGER §5 约束⑥)",
        "notes": (
            "仅用 IEDB 非重叠肽 (iedb_overlap_whitelist.csv) 重跑 LOPO.\n"
            "量化 IEDB 训练集污染对 ρ 的影响.\n"
            "需要 R1 已完成 → analysis/iedb_overlap_whitelist.csv 存在."
        ),
        "cmds": [
            ("Ridge surv6 IEDB 白名单过滤",
             "python quantimmune/lopo_eval.py --model ridge --features surv6 --target raw_sfc "
             "--whitelist analysis/iedb_overlap_whitelist.csv"),
            ("配对 bootstrap R11 vs R2",
             "python quantimmune/paired_bootstrap.py "
             "--meta quantimmune/results/lopo_ridge_surv6_raw_sfc_whitelist.per_patient.csv "
             "--baseline quantimmune/results/lopo_fixavg_surv6_raw_sfc.per_patient.csv"),
        ],
    },
]

# 按 ID 索引
RUNS_BY_ID = {r["id"]: r for r in RUNS}


def print_run(run, verbose=True):
    """打印单个 run 的信息."""
    print(f"\n{'─'*70}")
    print(f"[{run['id']}] {run['title']}")
    if verbose:
        print(f"  注: {run['notes']}")
        print(f"  命令:")
        for desc, cmd in run["cmds"]:
            print(f"    # {desc}")
            print(f"    {cmd}")
    else:
        print(f"  ({len(run['cmds'])} 条命令)")


def execute_run(run):
    """执行单个 run 的所有命令."""
    print(f"\n[执行] {run['id']}: {run['title']}")
    for desc, cmd in run["cmds"]:
        print(f"\n  >> {desc}")
        print(f"  $ {cmd}")
        # 从 ROOT 目录执行
        result = subprocess.run(
            cmd, shell=True, cwd=str(ROOT),
            capture_output=False)
        if result.returncode != 0:
            print(f"  [ERROR] returncode={result.returncode}, 停止该 run")
            break
        print(f"  [OK]")


def main():
    ap = argparse.ArgumentParser(
        description="F-pilot R0-R11 实验矩阵编排 (quantimmu-bench)")
    ap.add_argument("--run", default=None,
                    help="执行指定 run (如 R0, R3); 不指定则 dry-run 打印全部")
    ap.add_argument("--list", action="store_true",
                    help="仅列标题不展开命令")
    ap.add_argument("--from_run", default=None,
                    help="从指定 run 开始 dry-run 打印 (如 --from_run R3)")
    args = ap.parse_args()

    print("=" * 70)
    print("QuantImmune F-pilot 实验矩阵 R0→R11")
    print(f"工作目录: {ROOT}")
    print("=" * 70)

    if args.run:
        run_id = args.run.upper()
        if run_id not in RUNS_BY_ID:
            sys.exit(f"[ERR] 未知 run ID: {run_id}. 可用: {list(RUNS_BY_ID.keys())}")
        execute_run(RUNS_BY_ID[run_id])
        return

    # Dry-run: 打印全部 (或从某个 run 开始)
    start_printing = (args.from_run is None)
    for run in RUNS:
        if args.from_run and run["id"] == args.from_run.upper():
            start_printing = True
        if not start_printing:
            continue
        print_run(run, verbose=not args.list)

    print(f"\n{'='*70}")
    print("执行建议 (LEDGER 验证优先级):")
    print("  1. 先跑 build_model_matrix.py 生成 model_matrix.csv")
    print("  2. python quantimmune/run_all.py --run R0  (打乱对照必先跑)")
    print("  3. python quantimmune/run_all.py --run R1  (IEDB 若有数据)")
    print("  4. python quantimmune/run_all.py --run R2  (去偏地板)")
    print("  5. python quantimmune/run_all.py --run R3  (主模型)")
    print("  6. python quantimmune/run_all.py --run R5  (配对 bootstrap)")
    print("  7. R4,R6-R11 按需跑消融/敏感性")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
