"""
launch_reid_sweep.py — 命门批量启动器（正式命门扫矩阵，ACCV2026 gdn2vessel L1 lever）

功能：
  • 生成 36 组合（全量）或 12 组合（--batch1）的训练命令
  • 默认 --dry-run：只打印命令 + 目标 output_dir + 预期产出，不真提交
  • 真提交路径留函数存根，默认禁用 + 注释（主线串行+卡槽调度+拍板点才启）
  • 末尾聚合 verdict 命令模板也一并打印

矩阵（ACCEPTANCE P4 预登记，禁改）：
  4 集 × 3 臂 × 3 seed = 36 组合
  batch-1 模式：4 集 × 3 臂 × 1 seed = 12 组合（先验通再全量）
  单 severity = Medium（防伪重复，设计预登记）
  epochs = 300（Entry14 命门设计：100→300 治欠训）

使用：
  python scripts/launch_reid_sweep.py --dry-run           # 全量 36 run（默认 dry-run）
  python scripts/launch_reid_sweep.py --dry-run --batch1  # batch-1 12 run

DEPENDENCY 汇总（见各处注释，主线需确认）：
  [DEP-1] A1' 臂（linear_attn）的 UNetGDN2 linear_attn 模块实现状态未确认
  [DEP-2] STARE/HRF/FIVES benchmark_cache 需先 precompute_benchmark.py 生成
  [DEP-3] 多 seed 聚合行粒度——已解决：concat 时给每 seed 的 image_id 加 seed 前缀，
          使 image_id_global = dataset__seed{seed}__image_id，每 seed 每图成独立配对单元，
          select_last_epoch 不再吞 seed，配对数 = seed × 图（每集）。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List

# ─────────────────────────────────────────────────────────────────────────────
# 集中配置区（只改此处，全脚本生效）
# ─────────────────────────────────────────────────────────────────────────────

# HPC 数据根（集级根目录，每集一个子目录）
DATA_ROOT_BASE = "/gpfs/work/bio/jiayu2403/gdn2vessel/data/vessel"

# 数据集名（小写，与 train_reid_pilot.py 的 --dataset 参数对齐）
DATASETS: List[str] = ["chase", "stare", "hrf", "fives"]

# 各集的 data_root 和 benchmark_cache 路径
# NOTE: benchmark_cache 按集分目录，路径为 <data_root_for_ds>/benchmark_cache
# DEPENDENCY [DEP-2]: 已知 CHASE benchmark_cache 8 NPZ 冻结好（Entry14）；
#   STARE/HRF/FIVES benchmark cache **可能尚未 precompute** → 跑前需先执行
#   precompute_benchmark.py 生成各集 benchmark_cache。路径如下参数化，
#   确认 precompute 完成后再真提交对应集的 run。
DATASET_CONFIG = {
    "chase": {
        "data_root":      f"{DATA_ROOT_BASE}/CHASE",
        "benchmark_dir":  f"{DATA_ROOT_BASE}/CHASE/benchmark_cache",
        # CHASE benchmark_cache 已冻结（Entry14），可直接跑 ✓
    },
    "stare": {
        "data_root":      f"{DATA_ROOT_BASE}/STARE",
        "benchmark_dir":  f"{DATA_ROOT_BASE}/STARE/benchmark_cache",
        # DEPENDENCY [DEP-2]: STARE benchmark_cache 需先 precompute_benchmark.py 生成
    },
    "hrf": {
        "data_root":      f"{DATA_ROOT_BASE}/HRF",
        "benchmark_dir":  f"{DATA_ROOT_BASE}/HRF/benchmark_cache",
        # DEPENDENCY [DEP-2]: HRF benchmark_cache 需先 precompute_benchmark.py 生成
    },
    "fives": {
        "data_root":      f"{DATA_ROOT_BASE}/FIVES",
        "benchmark_dir":  f"{DATA_ROOT_BASE}/FIVES/benchmark_cache",
        # DEPENDENCY [DEP-2]: FIVES benchmark_cache 需先 precompute_benchmark.py 生成
        # 注：FIVES 子采样 seed42 固定（Entry14），train_reid_pilot 内部处理
    },
}

# 三臂（ACCEPTANCE P4 预登记名称）
# DEPENDENCY [DEP-1]: A1' 臂（linear_attn）在 train_reid_pilot.py 的 argparse choices
#   中已列（'memory', 'linear_attn', 'cnn'），_source_to_mode 也已映射到 'linear_attn'。
#   但 UNetGDN2.linear_attn 模块的完整前向实现状态未在此确认。
#   本 launcher 只负责矩阵，不负责臂实现。
#   若 UNetGDN2 linear_attn 尚未实现，linear_attn 臂 run 会在模型构建阶段报错。
#   届时需在 unet_gdn2.py + 相关模块补实现后再提交对应 run。
ARMS: List[str] = ["memory", "linear_attn", "cnn"]
# ARM 到 ACCEPTANCE 标签映射（仅用于打印可读性）
ARM_LABEL = {
    "memory":       "A2(memory)",
    "linear_attn":  "A1'(linear_attn)",
    "cnn":          "A0'(cnn)",
}

# 三 seed（ACCEPTANCE 未预登记具体值，此为默认可配）
# NOTE: FIVES 子采样 seed42 固定（Entry14），此 seed 指训练随机性 seed，
#   与子采样 seed 独立。
SEEDS: List[int] = [42, 1337, 2024]

# batch-1 模式使用的单一 seed（3臂×4集×1seed=12 run）
BATCH1_SEED: int = 42

# 固定参数（ACCEPTANCE P4 预登记，禁改）
SEVERITY = "Medium"       # 防伪重复，单 severity
EPOCHS   = 300            # Entry14 命门设计：100→300 治欠训（--epochs 默认100，显式覆盖）

# HPC 训练脚本路径（相对于 gdn2vessel 项目根，HPC 端绝对路径由 launcher 拼）
HPC_PROJECT_ROOT = "/gpfs/work/bio/jiayu2403/gdn2vessel"
TRAIN_SCRIPT = f"{HPC_PROJECT_ROOT}/src/train_reid_pilot.py"

# 输出根目录（HPC 端）
OUTPUT_ROOT = f"{HPC_PROJECT_ROOT}/outputs/reid_sweep"

# ─────────────────────────────────────────────────────────────────────────────
# 命令生成
# ─────────────────────────────────────────────────────────────────────────────

def make_output_dir(dataset: str, arm: str, seed: int) -> str:
    """生成独立 output_dir，命名：outputs/reid_sweep/{dataset}_{arm}_seed{seed}/"""
    return f"{OUTPUT_ROOT}/{dataset}_{arm}_seed{seed}"


def make_run_command(dataset: str, arm: str, seed: int) -> str:
    """拼单条 train_reid_pilot 命令。严格按 CLI 参数表，不造参数。"""
    cfg = DATASET_CONFIG[dataset]
    out_dir = make_output_dir(dataset, arm, seed)
    cmd = (
        f"python {TRAIN_SCRIPT}"
        f" --reid_feat_source {arm}"
        f" --data_root {cfg['data_root']}"
        f" --benchmark_dir {cfg['benchmark_dir']}"
        f" --dataset {dataset}"
        f" --severity {SEVERITY}"
        f" --epochs {EPOCHS}"
        f" --seed {seed}"
        f" --output_dir {out_dir}"
    )
    return cmd


def build_run_matrix(batch1: bool = False) -> List[dict]:
    """
    返回 run 字典列表，每项含 dataset/arm/seed/command/output_dir/expected_outputs。
    batch1=True → 只用 BATCH1_SEED，生成 12 条；False → 36 条。
    """
    seeds = [BATCH1_SEED] if batch1 else SEEDS
    runs = []
    for dataset in DATASETS:
        for arm in ARMS:
            for seed in seeds:
                out_dir = make_output_dir(dataset, arm, seed)
                runs.append({
                    "dataset":    dataset,
                    "arm":        arm,
                    "arm_label":  ARM_LABEL[arm],
                    "seed":       seed,
                    "command":    make_run_command(dataset, arm, seed),
                    "output_dir": out_dir,
                    "expected_outputs": [
                        f"{out_dir}/reid_results.csv",
                        f"{out_dir}/state.json",
                    ],
                })
    return runs


# ─────────────────────────────────────────────────────────────────────────────
# Verdict 聚合命令生成
# ─────────────────────────────────────────────────────────────────────────────

def make_verdict_commands(batch1: bool = False) -> str:
    """
    生成末尾 verdict 聚合步骤的命令模板。

    聚合逻辑：
      每臂把该臂所有集+所有seed的 reid_results.csv 纵向 concat 成一个该臂总 CSV，
      再喂 reid_verdict_v2.py --csv_a2/a1p/a0p。

    DEP-3 已解决：concat 时给每个 seed 的 CSV 行加 seed 前缀。
      具体：读每个 (dataset, arm, seed) 的 reid_results.csv 时，把该行的 image_id
      改写为 "seed{seed}__{原image_id}"（例 seed42__img01）。
      load_arm_csv 再拼成 image_id_global = "dataset__seed{seed}__image_id"
      （如 chase__seed42__img01），每 seed 每图唯一，select_last_epoch 不再吞 seed，
      配对数 = seed × 图（每集），与 per_dataset 分组（按 dataset 列）完全兼容。

    此处模板使用 HPC 端路径；inline python -c 完成带 seed 前缀的 concat，无额外依赖。
    """
    verdict_root = f"{HPC_PROJECT_ROOT}/outputs/reid_verdict"
    seeds = [BATCH1_SEED] if batch1 else SEEDS

    # Step 1: concat 各臂 CSV（按臂收集所有 dataset × seed 的 reid_results.csv）
    # DEP-3 已修：每个 seed 的行在读取时给 image_id 加 seed 前缀（seed{seed}__image_id），
    # 使 image_id_global = dataset__seed{seed}__image_id，每 seed 每图独立配对单元。
    step1_lines = ["# ── Step 1: 各臂 concat CSV（纵向合并所有集+seed，带 seed 前缀）──"]
    for arm in ARMS:
        # 构造 (path, seed) 对列表，供 inline python 逐文件读取时注入 seed 前缀
        src_seed_pairs = []
        for dataset in DATASETS:
            for seed in seeds:
                out_dir = make_output_dir(dataset, arm, seed)
                src_seed_pairs.append((f"{out_dir}/reid_results.csv", seed))
        arm_out_csv = f"{verdict_root}/arm_{arm}_all.csv"
        # concat 用 Python 一行（无额外依赖）：
        # 读每个 (csv_path, seed) 时把 image_id 改写为 seed{seed}__{image_id}
        pairs_repr = repr(src_seed_pairs)
        concat_cmd = (
            f"python -c \""
            f"import csv, pathlib; "
            f"pairs={pairs_repr}; "
            f"rows=[]; "
            f"[([(r.__setitem__('image_id', 'seed'+str(s)+'__'+r['image_id']), rows.append(dict(r)))"
            f" for r in csv.DictReader(open(p))])"
            f" for p,s in pairs if pathlib.Path(p).exists()]; "
            f"pathlib.Path('{verdict_root}').mkdir(parents=True, exist_ok=True); "
            f"w=csv.DictWriter(open('{arm_out_csv}','w',newline=''), fieldnames=rows[0].keys()) if rows else None; "
            f"w and (w.writeheader(), [w.writerow(r) for r in rows])"
            f"\""
        )
        step1_lines.append(f"# arm={ARM_LABEL[arm]}")
        step1_lines.append(concat_cmd)

    # Step 2: reid_verdict_v2
    step2_lines = [
        "",
        "# ── Step 2: reid_verdict_v2 三臂对比 ──",
        "# 已修：seed 前缀使每 seed 每图独立配对，配对数 = seed × 图（每集），select_last_epoch 不吞 seed",
        f"python {HPC_PROJECT_ROOT}/src/reid_verdict_v2.py \\",
        f"  --csv_a2  {verdict_root}/arm_memory_all.csv \\",
        f"  --csv_a1p {verdict_root}/arm_linear_attn_all.csv \\",
        f"  --csv_a0p {verdict_root}/arm_cnn_all.csv \\",
        f"  --datasets chase stare hrf fives \\",
        f"  --out_json {verdict_root}/verdict.json",
    ]

    return "\n".join(step1_lines + step2_lines)


# ─────────────────────────────────────────────────────────────────────────────
# 真提交存根（默认禁用）
# ─────────────────────────────────────────────────────────────────────────────

def _submit_single_run_DISABLED(run: dict, sbatch_template_path: str) -> None:
    """
    真提交单 run 到 HPC 的存根函数。

    默认禁用 + 不调用。
    主线串行 + 卡槽调度（gpu_slot.py request）+ 拍板点确认后才启。
    Launcher 本身绝不自动提交。

    启用步骤（主线执行）：
      1. python tools/gpu_slot.py request gdn2vessel hpc 1 "reid_sweep batch1"
      2. GO <id> 才启；QUEUED 则排队等
      3. 对每条命令生成 sbatch job（从 reid_job.sbatch.template 实例化）
      4. 传文件到 HPC（dos2unix 去 CRLF）
      5. sbatch <job.sbatch>（单独跑，不并发批量）
      6. 看 logs/ 产出确认真跑，别信 jobid（会串别人 job）
      7. 完成后 python tools/gpu_slot.py release <id>
    """
    raise NotImplementedError(
        "真提交已禁用。主线经 gpu_slot.py 卡槽调度 + 拍板点后才启。"
        "见 scripts/launch_reid_sweep.py 头注 + CLAUDE.md 训练全自主规范。"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Dry-run 打印
# ─────────────────────────────────────────────────────────────────────────────

def dry_run(runs: List[dict], batch1: bool) -> None:
    """打印所有命令 + output_dir + 预期产出。不执行任何真实提交。"""
    mode_tag = "batch-1（12 run，3臂×4集×1seed）" if batch1 else f"全量（{len(runs)} run，3臂×4集×3seed）"
    print(f"\n{'='*70}")
    print(f"[DRY-RUN] gdn2vessel 命门扫矩阵 — {mode_tag}")
    print(f"  severity={SEVERITY}  epochs={EPOCHS}  seeds={[BATCH1_SEED] if batch1 else SEEDS}")
    print(f"{'='*70}\n")

    for i, run in enumerate(runs, 1):
        print(f"── Run {i:02d}/{len(runs)} ─────────────────────────────────────────────")
        print(f"   dataset={run['dataset']}  arm={run['arm_label']}  seed={run['seed']}")
        print(f"   output_dir: {run['output_dir']}")
        print(f"   expected:   {run['expected_outputs'][0]}")
        print(f"              {run['expected_outputs'][1]}")
        print(f"   CMD: {run['command']}")
        print()

    # 末尾汇总
    print(f"\n{'='*70}")
    print(f"[汇总] 共 {len(runs)} run  |  severity={SEVERITY}  |  epochs={EPOCHS}")
    print(f"  每 run 独立 output_dir: {OUTPUT_ROOT}/{{dataset}}_{{arm}}_seed{{seed}}/")
    print(f"  预计每 run 产出: reid_results.csv + state.json")
    print()
    print("DEPENDENCY 清单（跑前必确认）:")
    print("  [DEP-1] A1'(linear_attn) 臂: UNetGDN2.linear_attn 模块实现状态需确认")
    print("          train_reid_pilot.py 参数已支持，但模型实现须验完整前向不报错")
    print("  [DEP-2] STARE/HRF/FIVES benchmark_cache 需先 precompute_benchmark.py 生成")
    print("          CHASE 已冻结(Entry14)可直接跑；其余三集先跑 precompute 再提交")
    print("  [DEP-3] 已解决：concat 时给 image_id 加 seed 前缀（seed{seed}__image_id），")
    print("          image_id_global = dataset__seed{seed}__image_id，每 seed 每图独立配对，")
    print("          配对数 = seed × 图（每集），select_last_epoch 不再吞 seed")
    print()
    print("── Verdict 聚合命令（所有 run done 后执行）──────────────────────────")
    print(make_verdict_commands(batch1=batch1))
    print(f"\n{'='*70}")
    print("[DRY-RUN 完成] 未执行任何真实提交。主线经 gpu_slot.py + 拍板点后才启。")
    print(f"{'='*70}\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description=(
            "gdn2vessel 命门批量启动器 — 生成 36/12 条 train_reid_pilot 命令矩阵。\n"
            "默认 --dry-run：只打印，不真提交。"
        )
    )
    p.add_argument(
        "--dry-run", "--dry_run",
        action="store_true",
        default=True,
        help="只打印命令，不真提交（默认 ON；显式 --no-dry-run 会触发 NotImplementedError）",
    )
    p.add_argument(
        "--no-dry-run", "--no_dry_run",
        dest="dry_run",
        action="store_false",
        help="关闭 dry-run → 触发 NotImplementedError（真提交由主线串行）",
    )
    p.add_argument(
        "--batch1",
        action="store_true",
        default=False,
        help="batch-1 模式：只用 seed=42，生成 3臂×4集×1seed=12 run（先验通再全量）",
    )
    return p.parse_args()


def main():
    args = parse_args()
    runs = build_run_matrix(batch1=args.batch1)

    if args.dry_run:
        dry_run(runs, batch1=args.batch1)
    else:
        # 真提交路径：禁用，主线串行+卡槽调度+拍板点才启
        raise NotImplementedError(
            "真提交已禁用。\n"
            "主线流程: gpu_slot.py request → GO → 逐 run 生成 sbatch → 单独提交 → release。\n"
            "见 scripts/launch_reid_sweep.py 头注 + scripts/reid_job.sbatch.template。"
        )


if __name__ == "__main__":
    main()
