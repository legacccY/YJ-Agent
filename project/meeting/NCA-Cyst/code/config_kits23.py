"""M3D-NCA × KiTS23 两套训练 config（smoke 本地 / full HPC）。

服务 NCA-Cyst 项目 § Phase 1a/1b baseline。

=====================================================================================
⚠️ 官方无 KiTS23 配置——超参来源标注（复现零偏离纪律）
-------------------------------------------------------------------------------------
官方 M3D-NCA 有两套**互相不一致**的示例配置，本文件逐项标注每个值取自哪套 / 是否 KiTS23 适配：

  来源 A = src/examples/train_M3D_NCA.py（.py 脚本版）
     betas(0.5,0.5) · n_epoch=1000 · inference_steps=[10,10]
     input_size=[(32,32,26),(64,64,52)] · scale_factor=2 · keep_original_scale=True
  来源 B = train_M3D_NCA.ipynb（notebook 版，官方称"真实数据集"配置）
     betas(0.9,0.99) · n_epoch=3000 · inference_steps=[20,40]
     input_size=[(80,80,6),(320,320,24)] · scale_factor=4 · keep_original_scale=False

标注约定：
  # [官方固定]        —— A 与 B 一致，照搬不动（复现零偏离）。
  # [官方分歧->选X]   —— A/B 不一致，注明选了哪套 + 理由。
  # [KiTS23适配TODO]  —— 官方无对应值，给合理默认，须 researcher/用户确认。

⚠️ scale_factor 与 input_size 耦合（非自由超参）：agent 在两级间按 scale_factor 下采样，
   必须 == input_size 各维比值。本文件两套 input_size 层间比值均=2，故 scale_factor 都取 2。
   改 input_size 时务必同步改 scale_factor。
=====================================================================================
"""
import os
from pathlib import Path

# KiTS23 原始数据根（只读，别动）。case_XXXXX/{imaging,segmentation}.nii.gz
# 环境变量 KITS23_ROOT 可覆盖（HPC 用 /gpfs/work/bio/jiayu2403/kits23/dataset）；缺省=本地。
DATASET_ROOT = os.environ.get("KITS23_ROOT", r"D:/YJ-Agent/data/kits23_repo/dataset")

# 实验产物默认落 NCA-Cyst/06_experiments/ 下（绝对路径，避免污染 cwd）。
_EXP_ROOT = (Path(__file__).resolve().parents[1] / "06_experiments")

# 本地烟测用的 5 个"大囊肿"case（源自 code/cyst_cases.json 的 smoke_top5，按囊肿体素降序）。
# 主线可改；用含囊肿的 case 才能让 cyst 模式 loss 非零、验通管线。
SMOKE_CASES = [
    "case_00465",
    "case_00543",
    "case_00068",
    "case_00586",
    "case_00519",
]


# ------------------------------------------------------------------------------------
# CONFIG_SMOKE —— 本地 RTX4070 8GB 烟测：几分钟内验管线不报错、loss 下降。
# ------------------------------------------------------------------------------------
CONFIG_SMOKE = {
    'img_path': DATASET_ROOT,          # 见 kits23_dataset：img/label 同根，__getitem__ 内拼子目录
    'label_path': DATASET_ROOT,
    'model_path': str(_EXP_ROOT / "M3D_NCA_KiTS23_smoke"),
    'device': "cuda:0",
    'unlock_CPU': True,                # [官方固定] A=B
    # --- 数据子集 & 目标类（本子类构造参数，train 脚本读这两个键传给 Dataset_KiTS23_3D） ---
    'cases_subset': SMOKE_CASES,       # 只 5 个含囊肿 case
    'label_mode': 'binary_all',        # train 脚本可用 --label_mode 覆盖
    # Optimizer
    'lr': 16e-4,                       # [官方固定] A=B
    'lr_gamma': 0.9999,                # [官方固定] A=B
    'betas': (0.9, 0.99),              # [官方分歧->选B] 与 full 一致
    # Training（烟测缩到最小）
    'save_interval': 10,               # [KiTS23适配TODO] 烟测值
    'evaluate_interval': 10,           # [KiTS23适配TODO] 烟测值；每次评估写一次 state.json
    'n_epoch': 30,                     # [KiTS23适配TODO] 烟测值，几分钟即可
    'batch_duplication': 1,            # [官方固定] A=B
    # Model
    'channel_n': 16,                   # [官方固定] A=B
    'inference_steps': [10, 10],       # [KiTS23适配TODO] 烟测取轻量（A 值）；官方 B=[20,40]
    'cell_fire_rate': 0.5,             # [官方固定] A=B
    'batch_size': 2,                   # [KiTS23适配TODO] 8GB 烟测取 2
    'input_channels': 1,               # [官方固定] A=B
    'output_channels': 1,              # [官方固定] A=B
    'hidden_size': 64,                 # [官方固定] A=B
    'train_model': 1,                  # [官方固定] A=B（=2 级 NCA）
    # Data
    'input_size': [(32, 32, 16), (64, 64, 32)],  # [KiTS23适配TODO] 烟测小体积；层间比值=2
    'scale_factor': 2,                 # 耦合 input_size 比值(=2)，非自由超参
    'data_split': [0.7, 0, 0.3],       # [官方固定] A=B → 5 例按 index<0.7 切=4 train/0 val/1 test
    'keep_original_scale': False,      # [官方分歧->选B]
    'rescale': True,                   # [官方固定] A=B
}


# ------------------------------------------------------------------------------------
# CONFIG_FULL —— HPC gpu4090 24GB 正式 baseline。
# ------------------------------------------------------------------------------------
CONFIG_FULL = {
    'img_path': DATASET_ROOT,          # 注：HPC 上须改为 HPC 端 KiTS23 路径（上传后由主线填）
    'label_path': DATASET_ROOT,
    'model_path': str(_EXP_ROOT / "M3D_NCA_KiTS23_full"),
    'device': "cuda:0",
    'unlock_CPU': True,                # [官方固定] A=B
    # --- 数据子集 & 目标类 ---
    'cases_subset': None,              # 全 489 例
    'label_mode': 'binary_all',        # Phase 1a；Phase 1b 用 --label_mode cyst
    # Optimizer
    'lr': 16e-4,                       # [官方固定] A=B
    'lr_gamma': 0.9999,                # [官方固定] A=B
    'betas': (0.9, 0.99),              # [官方分歧->选B] B 是官方"真实数据集"配置
    # Training
    'save_interval': 10,               # [KiTS23适配TODO]
    'evaluate_interval': 10,           # [KiTS23适配TODO]；每次评估写 state.json + 发散检测
    'n_epoch': 1000,                   # [KiTS23适配TODO] 默认 A 的 1000（B=3000 更久）；NCA 需大量 epoch
    'batch_duplication': 1,            # [官方固定] A=B
    # Model
    'channel_n': 16,                   # [官方固定] A=B
    'inference_steps': [10, 10],       # [KiTS23适配TODO] 默认 A=[10,10]（轻）；官方 B=[20,40]（更强更吃显存）
    'cell_fire_rate': 0.5,             # [官方固定] A=B
    'batch_size': 2,                   # [KiTS23适配TODO] 官方=4；KiTS23 体积大先取 2，按 24GB 实测调
    'input_channels': 1,               # [官方固定] A=B
    'output_channels': 1,              # [官方固定] A=B
    'hidden_size': 64,                 # [官方固定] A=B
    'train_model': 1,                  # [官方固定] A=B
    # Data
    'input_size': [(64, 64, 32), (128, 128, 64)],  # [KiTS23适配TODO] CT 体积大；层间比值=2
    'scale_factor': 2,                 # 耦合 input_size 比值(=2)，非自由超参
    'data_split': [0.7, 0, 0.3],       # [官方固定] A=B
    'keep_original_scale': False,      # [官方分歧->选B]
    'rescale': True,                   # [官方固定] A=B
}


def get_config(name):
    """按名字取 config 的**副本**（避免多次运行共享可变 dict）。"""
    if name == "smoke":
        return dict(CONFIG_SMOKE)
    if name == "full":
        return dict(CONFIG_FULL)
    raise ValueError(f"未知 config 名: {name!r}（只支持 'smoke' / 'full'）")
