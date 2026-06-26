"""
launch_p3_baseline_sweep.py — P3 基线 ×4 severity 批量评测 driver。

任务：给定 (baseline, dataset, seed, ckpt) 矩阵，对 Easy/Medium/Hard/Extreme
      4 severity 做纯推理评测（不重训），每 severity 出一个 CSV。

----------------------------------------------------------------------
CSV 输出命名规范（对齐 LEADERBOARD_MATRIX 和 verdict 脚本）:
  outputs/p3/<DS>_<baseline>_seed<s>/p3_<ds>_<baseline>_s<s>_<Sev>.csv
  示例:
    outputs/p3/DRIVE_fr_unet_seed42/p3_drive_fr_unet_s42_Easy.csv
    outputs/p3/DRIVE_fr_unet_seed42/p3_drive_fr_unet_s42_Medium.csv
    outputs/p3/DRIVE_fr_unet_seed42/p3_drive_fr_unet_s42_Hard.csv
    outputs/p3/DRIVE_fr_unet_seed42/p3_drive_fr_unet_s42_Extreme.csv

CSV schema（27 列，对齐 _BENCHMARK_FIELDNAMES）:
  dataset, baseline, kind, seed, split, severity, img_id,
  dice, iou, auc, se, sp,
  cldice, betti_b0_err, betti_b1_err, skeleton_recall, topo_source,
  epsilon_beta0, success_rate, reid_rate, n_gaps,
  reid_rate_head, reid_idf1,
  ckpt_path, eval_input_mode, threshold, git_commit

正确性保证:
  - 续连指标 ε_β0 / success_rate / reid_rate 从 pred_mask + GT + BreakResult 算
    → 不需要 re-ID head，12 baseline 公平同台。
  - reid_rate_head / reid_idf1 仅当 model 有 model.reid_head 时才非 NaN（ours 专属）。
  - 每组 (baseline, dataset, seed) 加载模型 1 次，4 severity 共享推理缓存
    → 节省 ~4× forward 开销（benchmark 设计：severity 只改 gap，不改图像输入）。
  - 验证集不与训练集重叠（evaluate_benchmark 走 benchmark NPZ held-out test set）。

使用（dry-run 打印，不真提交）:
  python scripts/launch_p3_baseline_sweep.py --dry-run
  python scripts/launch_p3_baseline_sweep.py --dry-run --dataset drive --seed 42
  python scripts/launch_p3_baseline_sweep.py --dry-run --baseline fr_unet

真提交由主线串行（经 gpu_slot.py 卡槽调度 + 拍板点后才启）：
  python tools/gpu_slot.py request gdn2vessel hpc 1 "p3_baseline_sweep"
  # GO <id> → 逐 run 实例化 eval_benchmark_all_sev.sbatch.template → dos2unix → sbatch
  # 完成后 python tools/gpu_slot.py release <id>

DEP 清单:
  [DEP-P1] benchmark_cache 需先 precompute_benchmark.py 生成
           每个 dataset ×4 severity 的 NPZ + manifest.json 必须到位
  [DEP-P2] 每 (baseline, dataset, seed) 需有训练好的 best.pth
           从 outputs/ 目录按命名规范找（见 CKPT_ROOT）
  [DEP-P3] creatis_postproc 额外需要 stage1_ckpt（backbone_unet best.pth）
           须在 CREATIS_STAGE1_CKPTS 字典里配置
  [DEP-P4] 评测完全部 run → 跑 verdict 脚本聚合 leaderboard

红线:
  - 真提交 _submit_single_run_DISABLED 函数抛 NotImplementedError
  - 不重训（--severity all 纯推理，不跑 train_harness）
  - 12 baseline 超参零偏离（evaluate.py 接口已保证，此处不改任何超参）
  - 续连指标从 pred_mask+GT+BreakResult 算，不泄露 eval set
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

# ──────────────────────────────────────────────────────────────────────────────
#  集中配置区（HPC 路径 + 评测矩阵）
#  修改此处，全脚本生效。
# ──────────────────────────────────────────────────────────────────────────────

HPC_PROJECT_ROOT = "/gpfs/work/bio/jiayu2403/gdn2vessel"
EVAL_SCRIPT      = f"{HPC_PROJECT_ROOT}/src/evaluate.py"

# benchmark_cache 扁平目录（含 manifest.json + NPZ，precompute_benchmark.py 产出）
BENCH_CACHE_DIR = f"{HPC_PROJECT_ROOT}/data/benchmark_cache"

# 数据根（per-dataset）
DATA_ROOT_BASE = f"{HPC_PROJECT_ROOT}/data/vessel"
DATASET_CONFIG: Dict[str, Dict] = {
    "drive": {
        "data_root":     f"{DATA_ROOT_BASE}/DRIVE",
        "dataset_upper": "DRIVE",
    },
    "chase": {
        "data_root":     f"{DATA_ROOT_BASE}/CHASE",
        "dataset_upper": "CHASE",
    },
    "stare": {
        "data_root":     f"{DATA_ROOT_BASE}/STARE",
        "dataset_upper": "STARE",
    },
    "fives": {
        "data_root":     f"{DATA_ROOT_BASE}/FIVES",
        "dataset_upper": "FIVES",
    },
}

# 训练好的 ckpt 根目录（各 run 按 outputs/<baseline>_<dataset>_s<seed>/best.pth 存储）
CKPT_ROOT = f"{HPC_PROJECT_ROOT}/outputs"

# P3 评测矩阵（LEADERBOARD_MATRIX — 主线确认后改此处）
# architecture 类 baseline（全套自带 loss + backbone）
ARCH_BASELINES: List[str] = [
    "fr_unet",
    "ours_gdn2",
    "backbone_unet",
    "vmunet",
    "umamba",
    "mambavesselnet",
    "nnunet",
    "pascnet",
    "cs_net",
    "dscnet",
    "mm_unet",
    "creatis_postproc",
]

# loss 类 baseline（统一 backbone + 特定 loss）
LOSS_BASELINES: List[str] = [
    "cldice",
    "cbdice",
    "skeleton_recall",
]

# 评测用的所有 baseline（architecture + loss）
ALL_BASELINES: List[str] = ARCH_BASELINES + LOSS_BASELINES

# 数据集（主线评测集）
DATASETS: List[str] = ["drive", "chase"]

# 种子（主线 3-seed 均值消除随机性）
SEEDS: List[int] = [42, 1, 2]

# 4 severity（benchmark 固定，不可更改）
SEVERITIES: List[str] = ["Easy", "Medium", "Hard", "Extreme"]

# 输出根（HPC 端，p3/ 子目录）
OUTPUT_ROOT = f"{HPC_PROJECT_ROOT}/outputs/p3"

# creatis Stage-1 ckpt 路径（两段式专用）
# 用户拍板（2026-06-25）：creatis Stage-1 复用批1 FR-UNet ckpt，
#   架构 = FR_UNet(feature_scale=2, out_ave=True)，不是 backbone_unet。
# 调用侧须同时传 --creatis_stage1_adapter fr_unet（见 make_eval_command）。
#
# seed42（已实测，HPC 路径已核）：
CREATIS_STAGE1_CKPTS: Dict[tuple, str] = {
    ("drive", 42): f"{HPC_PROJECT_ROOT}/outputs/p3/DRIVE_fr_unet_seed42/best.pth",
    ("chase", 42): f"{HPC_PROJECT_ROOT}/outputs/p3/CHASE_fr_unet_seed42/best.pth",
    # seed 1 / seed 2: TODO — 需 researcher/主线确认 HPC 上 fr_unet seed1/seed2 ckpt 路径
    # ("drive", 1): f"{CKPT_ROOT}/fr_unet_drive_s1/best.pth",
    # ("drive", 2): f"{CKPT_ROOT}/fr_unet_drive_s2/best.pth",
    # ("chase", 1): f"{CKPT_ROOT}/fr_unet_chase_s1/best.pth",
    # ("chase", 2): f"{CKPT_ROOT}/fr_unet_chase_s2/best.pth",
}

# ──────────────────────────────────────────────────────────────────────────────
#  ckpt 路径推断（命名约定：<baseline>_<dataset>_s<seed>/best.pth）
# ──────────────────────────────────────────────────────────────────────────────

def _ckpt_path(baseline: str, dataset: str, seed: int) -> str:
    """
    推断 HPC 上训练好的 best.pth 路径。
    命名约定 = _output_dir()/best.pth（与训练产出一致，批1 FR-UNet 实测路径）：
      outputs/p3/<DATASET>_<baseline>_seed<seed>/best.pth
    """
    return f"{_output_dir(baseline, dataset, seed)}/best.pth"


def _output_dir(baseline: str, dataset: str, seed: int) -> str:
    """
    P3 CSV 输出目录。
    命名约定：outputs/p3/<DATASET>_<baseline>_seed<seed>/
    (大写 DATASET 便于按 dataset 归档)
    """
    ds_up = dataset.upper()
    return f"{OUTPUT_ROOT}/{ds_up}_{baseline}_seed{seed}"


def _csv_stem(baseline: str, dataset: str, seed: int) -> str:
    """
    CSV 文件名 stem（不含 severity 后缀和扩展名）。
    命名约定：p3_<ds>_<baseline>_s<seed>
    evaluate.py --severity all 会自动派生 _Easy.csv / _Medium.csv 等。
    """
    return f"p3_{dataset}_{baseline}_s{seed}"


# ──────────────────────────────────────────────────────────────────────────────
#  单 run 命令生成
# ──────────────────────────────────────────────────────────────────────────────

def make_eval_command(baseline: str, dataset: str, seed: int) -> str:
    """
    生成单次 evaluate.py 命令（--severity all → 4 severity，模型加载 1 次）。

    evaluate_benchmark 接口 (evaluate.py):
      --adapter  baseline 名
      --ckpt     best.pth 路径
      --data_root  原始数据集根（FR-UNet adapter 需要重新预处理，其余忽略）
      --dataset  DRIVE/CHASE/...（大写）
      --benchmark_dir  benchmark_cache 目录
      --severity all   → Easy + Medium + Hard + Extreme（4 CSV）
      --seed     随机种子（记录用，不影响评估逻辑）
      --device   cuda
      --output_csv <stem>.csv  → evaluate.py 自动派生 <stem>_Easy.csv 等

    creatis_postproc 额外参数:
      --creatis_stage1_ckpt  Stage-1 backbone_unet ckpt 路径
      (由 evaluate.py CLI 读取后写入 cfg['stage1_ckpt']，
       trigger: adapter.build_model(cfg) 中加载 _stage1_model)

    正确性保证:
      - --severity all 让 evaluate.py 在单次 python 进程内加载模型 1 次，
        跑 4 severity，每次用相同 pred_bin（推理缓存），只换 BreakResult。
      - 续连指标 epsilon_beta0 / success_rate / reid_rate 由 compute_all_metrics
        从 pred_mask + GT + BreakResult 计算，不需要 re-ID head。
      - reid_rate_head / reid_idf1 仅在 model.use_reid_head=True 时非 NaN（ours）。
      - threshold=0.5 严守 BASELINE_SPEC §2.5 量尺，不可改。
    """
    out_dir = _output_dir(baseline, dataset, seed)
    csv_stem = _csv_stem(baseline, dataset, seed)
    ds_cfg = DATASET_CONFIG[dataset]
    ckpt = _ckpt_path(baseline, dataset, seed)

    cmd_parts = [
        f"python {EVAL_SCRIPT}",
        f"--adapter   {baseline}",
        f"--ckpt      {ckpt}",
        f"--data_root {ds_cfg['data_root']}",
        f"--dataset   {ds_cfg['dataset_upper']}",
        f"--benchmark_dir {BENCH_CACHE_DIR}",
        f"--severity  all",
        f"--seed      {seed}",
        f"--device    cuda",
        f"--output_csv {out_dir}/{csv_stem}.csv",
    ]

    # creatis_postproc 需要额外传 stage1_ckpt + stage1_adapter
    if baseline == "creatis_postproc":
        s1_ckpt = CREATIS_STAGE1_CKPTS.get((dataset, seed), None)
        if s1_ckpt is not None:
            # 用户拍板：Stage-1 = FR-UNet ckpt（feature_scale=2 官方默认）
            cmd_parts.append(f"--creatis_stage1_ckpt {s1_ckpt}")
            cmd_parts.append("--creatis_stage1_adapter fr_unet")
        else:
            # TODO: CREATIS_STAGE1_CKPTS 未配置此 (dataset, seed) 组合
            # seed1/seed2: 确认 fr_unet ckpt HPC 路径后回填 CREATIS_STAGE1_CKPTS
            cmd_parts.append(
                f"# TODO: stage1_ckpt 未配置 (dataset={dataset}, seed={seed})\n"
                f"#       确认 fr_unet best.pth HPC 路径后填入 CREATIS_STAGE1_CKPTS"
            )

    return " \\\n    ".join(cmd_parts)


def _expected_csvs(baseline: str, dataset: str, seed: int) -> List[str]:
    """返回预期产出的 4 个 severity CSV 路径列表。"""
    out_dir = _output_dir(baseline, dataset, seed)
    stem = _csv_stem(baseline, dataset, seed)
    return [f"{out_dir}/{stem}_{sev}.csv" for sev in SEVERITIES]


def _sbatch_placeholders(baseline: str, dataset: str, seed: int) -> Dict[str, str]:
    """
    返回 eval_benchmark_all_sev.sbatch.template 的占位符替换字典。
    主线用此字典做 str.replace('{KEY}', val) 实例化 sbatch 文件。
    """
    ds_cfg = DATASET_CONFIG[dataset]
    return {
        "ADAPTER":    baseline,
        "DATASET":    dataset,
        "DATASET_UP": ds_cfg["dataset_upper"],
        "SEED":       str(seed),
        "DATA_ROOT":  ds_cfg["data_root"],
        "BENCH_DIR":  BENCH_CACHE_DIR,
        "CKPT_PATH":  _ckpt_path(baseline, dataset, seed),
        "OUT_DIR":    _output_dir(baseline, dataset, seed),
    }


# ──────────────────────────────────────────────────────────────────────────────
#  训练模板配置
# ──────────────────────────────────────────────────────────────────────────────

# FR-UNet pickle cache 路径（train_p3_baseline.sbatch.template 用）
FRUNET_CACHE_PATH = f"{HPC_PROJECT_ROOT}/data/frunet_cache"

# baseline → config yaml 相对路径（相对 GDN2_ROOT）
# 注意：umamba 和 nnunet 走 nnUNetv2 命令行，train_harness 不适用，标注跳过
_BASELINE_CONFIG_MAP: Dict[str, str] = {
    "fr_unet":          "src/configs/baselines/frunet.yaml",
    "backbone_unet":    "src/configs/baselines/backbone_unet.yaml",
    "vmunet":           "src/configs/baselines/vmunet.yaml",
    "umamba":           "src/configs/baselines/umamba.yaml",      # mamba 系，nnUNetv2 另出
    "mambavesselnet":   "src/configs/baselines/mambavesselnet.yaml",
    "nnunet":           "src/configs/baselines/nnunet.yaml",       # nnUNetv2 另出
    "pascnet":          "src/configs/baselines/pascnet.yaml",
    "cs_net":           "src/configs/baselines/csnet.yaml",  # registry名cs_net,config文件名csnet
    "dscnet":           "src/configs/baselines/dscnet.yaml",
    "mm_unet":          "src/configs/baselines/mm_unet.yaml",
    "creatis_postproc": "src/configs/baselines/creatis.yaml",
    "cldice":           "src/configs/baselines/cldice.yaml",
    "cbdice":           "src/configs/baselines/cbdice.yaml",
    "skeleton_recall":  "src/configs/baselines/skeleton_recall.yaml",
    "ours_gdn2":        "src/configs/baselines/ours_gdn2.yaml",
}

# baseline → env_tag（从 yaml baseline.env_tag 字段核定；mamba 系须激活 mamba_venv）
_BASELINE_ENV_TAG: Dict[str, str] = {
    "fr_unet":          "main",
    "backbone_unet":    "main",
    "vmunet":           "mamba",
    "umamba":           "mamba",
    "mambavesselnet":   "mamba",
    "nnunet":           "main",
    "pascnet":          "main",
    "cs_net":           "main",
    "dscnet":           "main",
    "mm_unet":          "mamba",
    "creatis_postproc": "main",
    "cldice":           "main",
    "cbdice":           "main",
    "skeleton_recall":  "main",
    "ours_gdn2":        "main",
}

# baseline → epochs（从 config train.epochs 字段读取；nnUNetv2 系不走此模板标 None）
_BASELINE_EPOCHS: Dict[str, Optional[int]] = {
    "fr_unet":          40,
    "backbone_unet":    100,
    "vmunet":           None,   # TODO: 未找到官方源，需 researcher 确认
    "umamba":           1000,   # nnUNetv2 默认（不走此模板）
    "mambavesselnet":   None,   # TODO: 未找到官方源，需 researcher 确认
    "nnunet":           1000,   # nnUNetv2 默认（不走此模板）
    "pascnet":          None,   # TODO: 未找到官方源，需 researcher 确认
    "cs_net":           1000,   # CS-Net 官方 train.py（researcher 核源 iMED-Lab/CS-Net）
    "dscnet":           400,    # DSCNet 官方 S0_Main.py ep400（researcher 核源 YaoleiQi/DSCNet）
    "mm_unet":          None,   # TODO: 未找到官方源，需 researcher 确认（mamba_venv 批4）
    "creatis_postproc": None,   # 两段式，不直接走此模板
    "cldice":           100,    # 与 backbone_unet 对齐（BASELINE_SPEC §2.4）
    "cbdice":           100,    # 与 backbone_unet 对齐
    "skeleton_recall":  100,    # 与 backbone_unet 对齐
    "ours_gdn2":        100,    # 同台不开后门 = 与 backbone_unet 统一协议（BASELINE_SPEC §2.4）
}

# 不走 train_p3_baseline.sbatch.template 的 baseline（单独路径）
_TRAIN_SKIP_BASELINES = {
    "umamba",      # nnUNetv2_train 命令行
    "nnunet",      # nnUNetv2_train 命令行
    "creatis_postproc",  # 两段式，Stage-1 = backbone_unet 独立跑，Stage-2 TODO
}


def make_train_sbatch_placeholders(
    baseline: str,
    dataset: str,
    seed: int,
) -> Optional[Dict[str, str]]:
    """
    返回 train_p3_baseline.sbatch.template 的占位符替换字典。

    Args:
        baseline: registry 注册名（如 'backbone_unet'）
        dataset:  数据集小写（如 'drive'）
        seed:     种子整数

    Returns:
        占位符字典，供 instantiate_sbatch(run, train_template_path) 使用；
        若 baseline 不走此训练模板（nnUNetv2/creatis），返回 None（调用方跳过）。

    Placeholders（对应 train_p3_baseline.sbatch.template {KEY} 格式）：
        BASELINE        — registry 注册名
        DATASET         — 数据集大写（DRIVE/CHASE/STARE/FIVES）
        SEED            — 种子整数
        CONFIG          — config 相对路径
        DATA_ROOT       — 该集 data_root 完整路径
        OUT_DIR         — 输出目录完整路径（与 _output_dir 一致）
        ENV_TAG         — main | mamba
        EPOCHS          — 训练 epoch 数（或 TODO 占位）
        FRUNET_CACHE    — fr_unet cache 路径；其他 baseline 填 'NONE'

    使用示例（backbone_unet × DRIVE × seed42）：
        ph = make_train_sbatch_placeholders('backbone_unet', 'drive', 42)
        content = instantiate_sbatch({'sbatch_placeholders': ph}, 'scripts/train_p3_baseline.sbatch.template')
        # content 即可直接写文件 + dos2unix + sbatch
    """
    if baseline in _TRAIN_SKIP_BASELINES:
        return None

    ds_cfg = DATASET_CONFIG[dataset]
    config_rel = _BASELINE_CONFIG_MAP.get(baseline)
    if config_rel is None:
        return None

    env_tag = _BASELINE_ENV_TAG.get(baseline, "main")
    epochs_val = _BASELINE_EPOCHS.get(baseline)
    epochs_str = str(epochs_val) if epochs_val is not None else "TODO_researcher_confirm"

    frunet_cache = FRUNET_CACHE_PATH if baseline == "fr_unet" else "NONE"

    return {
        "BASELINE":      baseline,
        "DATASET":       ds_cfg["dataset_upper"],   # 大写（train_harness --dataset 用大写）
        "SEED":          str(seed),
        "CONFIG":        config_rel,
        "DATA_ROOT":     ds_cfg["data_root"],
        "OUT_DIR":       _output_dir(baseline, dataset, seed),
        "ENV_TAG":       env_tag,
        "EPOCHS":        epochs_str,
        "FRUNET_CACHE":  frunet_cache,
    }


def build_train_run_matrix(
    filter_baseline: Optional[str] = None,
    filter_dataset: Optional[str] = None,
    filter_seed: Optional[int] = None,
) -> List[Dict]:
    """
    构建 P3 训练 run 列表（对应 train_p3_baseline.sbatch.template）。

    跳过不走此模板的 baseline（nnunet/umamba = nnUNetv2 另出；creatis_postproc = 两段式）。
    每 run = 一个 train_harness.py 调用（1 GPU job）。

    Returns:
        run dict 列表，每 run 含：
            baseline / dataset / seed /
            train_sbatch_placeholders / skip_reason
    """
    baselines_to_run = [filter_baseline] if filter_baseline else ALL_BASELINES
    datasets_to_run  = [filter_dataset]  if filter_dataset  else DATASETS
    seeds_to_run     = [filter_seed]     if filter_seed      else SEEDS

    valid_datasets = set(DATASET_CONFIG.keys())
    runs: List[Dict] = []
    run_idx = 1

    for baseline in baselines_to_run:
        for dataset in datasets_to_run:
            if dataset not in valid_datasets:
                continue
            for seed in seeds_to_run:
                # 不走此模板的 baseline
                if baseline in _TRAIN_SKIP_BASELINES:
                    runs.append({
                        "run_id":                  run_idx,
                        "baseline":                baseline,
                        "dataset":                 dataset,
                        "seed":                    seed,
                        "train_sbatch_placeholders": None,
                        "skip_reason": (
                            "nnUNetv2_train 命令行（另出）"
                            if baseline in ("umamba", "nnunet")
                            else "creatis_postproc 两段式（Stage-1 用 backbone_unet 模板）"
                        ),
                        "output_dir": _output_dir(baseline, dataset, seed),
                    })
                else:
                    ph = make_train_sbatch_placeholders(baseline, dataset, seed)
                    runs.append({
                        "run_id":                  run_idx,
                        "baseline":                baseline,
                        "dataset":                 dataset,
                        "seed":                    seed,
                        "train_sbatch_placeholders": ph,
                        "skip_reason":             None,
                        "output_dir":              _output_dir(baseline, dataset, seed),
                    })
                run_idx += 1

    return runs


# ──────────────────────────────────────────────────────────────────────────────
#  评测矩阵构建
# ──────────────────────────────────────────────────────────────────────────────

def build_run_matrix(
    filter_baseline: Optional[str] = None,
    filter_dataset: Optional[str] = None,
    filter_seed: Optional[int] = None,
) -> List[Dict]:
    """
    构建 P3 评测 run 列表。

    矩阵：baseline × dataset × seed = N × 2 × 3（默认全集）
    每 run = 1 次 evaluate.py --severity all → 4 CSV

    Args:
        filter_baseline: 若非 None，只保留此 baseline 的 run。
        filter_dataset:  若非 None，只保留此 dataset 的 run。
        filter_seed:     若非 None，只保留此 seed 的 run。

    Returns:
        run dict 列表（含 run_id / baseline / dataset / seed / command /
        expected_csvs / sbatch_placeholders / dep_flags）。
    """
    baselines_to_run = (
        [filter_baseline] if filter_baseline is not None else ALL_BASELINES
    )
    datasets_to_run = (
        [filter_dataset] if filter_dataset is not None else DATASETS
    )
    seeds_to_run = (
        [filter_seed] if filter_seed is not None else SEEDS
    )

    # 过滤掉不支持的 dataset
    valid_datasets = set(DATASET_CONFIG.keys())

    runs: List[Dict] = []
    run_idx = 1

    for baseline in baselines_to_run:
        for dataset in datasets_to_run:
            if dataset not in valid_datasets:
                print(
                    f"[launch_p3] WARNING: unknown dataset {dataset!r}, skip.",
                    file=sys.stderr,
                )
                continue
            for seed in seeds_to_run:
                dep_flags: List[str] = []

                # DEP-P2: ckpt 存在性标注（HPC 端，本地无法验证，仅标注）
                ckpt = _ckpt_path(baseline, dataset, seed)
                dep_flags.append(f"[DEP-P2] ckpt: {ckpt}")

                # DEP-P3: creatis 需要 stage1_ckpt
                if baseline == "creatis_postproc":
                    s1 = CREATIS_STAGE1_CKPTS.get((dataset, seed), None)
                    if s1 is None:
                        dep_flags.append(
                            f"[DEP-P3-MISSING] creatis stage1_ckpt 未配置 "
                            f"(dataset={dataset}, seed={seed}) — 填 CREATIS_STAGE1_CKPTS 后重试"
                        )
                    else:
                        dep_flags.append(f"[DEP-P3] creatis stage1_ckpt: {s1}")

                runs.append({
                    "run_id":             run_idx,
                    "baseline":           baseline,
                    "dataset":            dataset,
                    "seed":               seed,
                    "command":            make_eval_command(baseline, dataset, seed),
                    "output_dir":         _output_dir(baseline, dataset, seed),
                    "expected_csvs":      _expected_csvs(baseline, dataset, seed),
                    "sbatch_placeholders": _sbatch_placeholders(baseline, dataset, seed),
                    "dep_flags":          dep_flags,
                })
                run_idx += 1

    return runs


# ──────────────────────────────────────────────────────────────────────────────
#  Sbatch 实例化工具
# ──────────────────────────────────────────────────────────────────────────────

def instantiate_sbatch(
    run: Dict,
    template_path: str,
) -> str:
    """
    将 eval_benchmark_all_sev.sbatch.template 中的占位符替换为 run 的实际值。

    Args:
        run:           build_run_matrix 产出的单 run dict。
        template_path: sbatch template 文件路径（本地，用于 dry-run 打印）。

    Returns:
        实例化后的 sbatch 文件内容字符串（带 LF 换行，可直接上传 HPC）。
    """
    tpl_path = Path(template_path)
    if not tpl_path.exists():
        return f"# [WARNING] template not found: {template_path}"

    with open(tpl_path, "r", encoding="utf-8") as f:
        content = f.read()

    for key, val in run["sbatch_placeholders"].items():
        content = content.replace(f"{{{key}}}", val)

    # 统一 LF（HPC 上 dos2unix 防 CRLF，本地 Windows 转换）
    content = content.replace("\r\n", "\n")
    return content


# ──────────────────────────────────────────────────────────────────────────────
#  真提交存根（禁用）
# ──────────────────────────────────────────────────────────────────────────────

def _submit_single_run_DISABLED(run: Dict) -> None:
    """
    真提交存根。禁用，主线经 gpu_slot.py 卡槽调度 + 拍板点后才启。

    主线流程（单 run 提交）:
      1. python tools/gpu_slot.py request gdn2vessel hpc 1 "p3_baseline_sweep"
      2. GO <id> → 实例化 eval_benchmark_all_sev.sbatch.template（替换占位符）
      3. dos2unix 去 CRLF（防 HPC CRLF 报错）
      4. sbatch <实例化文件>.sbatch（单独提交，不并发）
      5. 看 logs/%x_%j.out 确认 4 个 CSV 产出（不信 jobid，见 feedback_hpc_submit_checklist）
      6. 全 done 后 python tools/gpu_slot.py release <id>
      7. 全部 run 完成后跑 verdict 脚本聚合 leaderboard

    sbatch 文件命名建议:
      p3_eval_{baseline}_{dataset}_s{seed}.sbatch
    """
    raise NotImplementedError(
        "真提交已禁用。\n"
        "主线流程: gpu_slot.py request → GO → 实例化 eval_benchmark_all_sev.sbatch.template "
        "→ dos2unix → 单独 sbatch → 看 logs 确认 4 CSV → release。\n"
        "见 scripts/launch_p3_baseline_sweep.py 头注。"
    )


# ──────────────────────────────────────────────────────────────────────────────
#  Dry-run 打印
# ──────────────────────────────────────────────────────────────────────────────

def dry_run(runs: List[Dict], show_sbatch: bool = False) -> None:
    """
    打印评测矩阵 + 每 run 的命令 + 预期 CSV + DEP 清单。
    不执行任何提交。

    Args:
        runs:        build_run_matrix 的输出。
        show_sbatch: 若 True，额外打印每 run 的 sbatch 实例化内容。
    """
    n_runs = len(runs)
    n_csvs = n_runs * len(SEVERITIES)

    print(f"\n{'='*72}")
    print(f"[DRY-RUN] gdn2vessel P3 baseline 批量评测 — {n_runs} run × 4 severity = {n_csvs} CSV")
    print(f"  baselines  = {sorted(set(r['baseline'] for r in runs))}")
    print(f"  datasets   = {sorted(set(r['dataset'] for r in runs))}")
    print(f"  seeds      = {sorted(set(r['seed'] for r in runs))}")
    print(f"  severities = {SEVERITIES}")
    print(f"  OUTPUT_ROOT = {OUTPUT_ROOT}")
    print(f"{'='*72}\n")

    # DEP 清单汇总
    missing_dep3 = [
        r for r in runs
        if any("DEP-P3-MISSING" in d for d in r.get("dep_flags", []))
    ]

    for run in runs:
        print(
            f"── Run {run['run_id']:03d}/{n_runs} ─────────────────────────────────────────"
        )
        print(f"   baseline={run['baseline']}  dataset={run['dataset']}  seed={run['seed']}")
        print(f"   output_dir: {run['output_dir']}")
        print(f"   expected CSV ({len(SEVERITIES)}个):")
        for csv in run["expected_csvs"]:
            print(f"     {csv}")

        # DEP 标注
        for dep in run.get("dep_flags", []):
            flag = "WARNING" if "MISSING" in dep else "INFO"
            print(f"   [{flag}] {dep}")

        print(f"   CMD:")
        print(f"     {run['command']}")
        print()

        if show_sbatch:
            tpl = str(
                Path(__file__).parent / "eval_benchmark_all_sev.sbatch.template"
            )
            sbatch_content = instantiate_sbatch(run, tpl)
            print(f"   SBATCH CONTENT (p3_eval_{run['baseline']}_{run['dataset']}_s{run['seed']}.sbatch):")
            for line in sbatch_content.splitlines():
                print(f"     {line}")
            print()

    # DEP 清单汇总
    print(f"{'='*72}")
    print(f"[汇总] {n_runs} run  |  4 severity × 每 run → {n_csvs} CSV")
    print(f"  CSV 命名: p3_<ds>_<baseline>_s<seed>_{{Easy,Medium,Hard,Extreme}}.csv")
    print(f"  每 run 产出 27 列 (含 epsilon_beta0/success_rate/reid_rate/reid_rate_head)")
    print()
    print("DEPENDENCY 清单（提交前必过）:")
    print(
        "  [DEP-P1] benchmark_cache: 各 dataset ×4 severity NPZ + manifest.json 到位\n"
        f"           目录: {BENCH_CACHE_DIR}"
    )
    print(
        "  [DEP-P2] 训练 ckpt: 各 (baseline, dataset, seed) 已有 best.pth\n"
        f"           根目录: {CKPT_ROOT}/<baseline>_<dataset>_s<seed>/best.pth"
    )
    if missing_dep3:
        print(
            "  [DEP-P3-MISSING] creatis_postproc stage1_ckpt 未配置 "
            f"({len(missing_dep3)} run 受影响):"
        )
        for r in missing_dep3:
            print(f"    (dataset={r['dataset']}, seed={r['seed']})")
        print(
            "    → 确认 backbone_unet best.pth HPC 路径后填入 CREATIS_STAGE1_CKPTS 字典"
        )
    else:
        print("  [DEP-P3] creatis stage1_ckpt: 已配置（或本次 run 无 creatis）")

    print()
    print("── 卡槽调度（提交前必做）─────────────────────────────────────────────")
    print('  python tools/gpu_slot.py request gdn2vessel hpc 1 "p3_baseline_sweep"')
    print("  GO <id> → 逐 run 实例化 eval_benchmark_all_sev.sbatch.template")
    print("            dos2unix 去 CRLF → sbatch 单独提交 → 看 logs 确认 4 CSV")
    print("  完成后 python tools/gpu_slot.py release <id>")
    print()
    print("── sbatch 实例化命令示例（主线用，替换 {占位符}）─────────────────────")
    if runs:
        ex = runs[0]
        ph = ex["sbatch_placeholders"]
        print(f"  # 示例：Run 1 ({ex['baseline']}, {ex['dataset']}, seed={ex['seed']})")
        for k, v in ph.items():
            print(f"    {{{k}}} → {v}")
    print()
    print(f"{'='*72}")
    print(f"[DRY-RUN 完成] {n_runs} run，未执行任何真实提交。")
    print(f"{'='*72}\n")


# ──────────────────────────────────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────────────────────────────────

def _parse_args():
    p = argparse.ArgumentParser(
        description=(
            "gdn2vessel P3 baseline ×4 severity 批量评测 driver。\n"
            "默认 --dry-run：只打印，不真提交。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--dry-run", "--dry_run",
        action="store_true",
        default=True,
        help="只打印命令，不真提交（默认 ON）",
    )
    p.add_argument(
        "--no-dry-run", "--no_dry_run",
        dest="dry_run",
        action="store_false",
        help="关闭 dry-run → 触发 NotImplementedError（真提交由主线串行）",
    )
    p.add_argument(
        "--baseline", default=None,
        help="过滤：只生成此 baseline 的 run（例如 fr_unet）",
    )
    p.add_argument(
        "--dataset", default=None,
        choices=list(DATASET_CONFIG.keys()),
        help="过滤：只生成此 dataset 的 run（例如 drive）",
    )
    p.add_argument(
        "--seed", type=int, default=None,
        help="过滤：只生成此 seed 的 run（例如 42）",
    )
    p.add_argument(
        "--show-sbatch", "--show_sbatch",
        action="store_true",
        default=False,
        help="dry-run 时额外打印每 run 的 sbatch 实例化内容",
    )
    return p.parse_args()


def main():
    args = _parse_args()
    runs = build_run_matrix(
        filter_baseline=args.baseline,
        filter_dataset=args.dataset,
        filter_seed=args.seed,
    )

    if not runs:
        print("[launch_p3] 过滤后无 run，检查 --baseline/--dataset/--seed 参数。",
              file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        dry_run(runs, show_sbatch=args.show_sbatch)
    else:
        raise NotImplementedError(
            "真提交已禁用。\n"
            "主线流程: gpu_slot.py request → GO → 逐 run 实例化 sbatch → dos2unix "
            "→ 单独提交 → 看 logs 确认 4 CSV → release。\n"
            "见 scripts/launch_p3_baseline_sweep.py 头注。"
        )


if __name__ == "__main__":
    main()
