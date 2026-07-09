"""UNet3D × KiTS23 两套训练 config（smoke 本地 / full HPC）。

服务 NCA-Cyst 项目 § Phase 1c，lever = UNet3D 同口径对照（亲手复现「主流模型囊肿近随机」）。

=====================================================================================
同口径命门（与 M3D-NCA baseline 逐项对齐）
-------------------------------------------------------------------------------------
Phase 1c 的价值全在「和 M3D-NCA 完全同口径」——同 case 集 / 同 split / 同 label 处理 / 同
评估，只把模型从 NCA 换成官方 UNet3D。任何不一致对比即无效。对齐点：
  - DATASET_ROOT / SMOKE_CASES：**直接 import 自 config_kits23**（不重定义），保证同一批 case。
  - data_split=[0.7,0,0.3]：与 M3D-NCA 完全一致（官方 DataSplit 按 index 切，同 case 序 → 同 split）。
  - label_mode（binary_all / cyst）：复用 Dataset_KiTS23_3D 的同一 label 处理逻辑。
  - 评估：train 脚本用官方 agent.test(DiceLoss) / getAverageDiceScore，与 M3D-NCA 同一套 Dice 口径。

=====================================================================================
超参来源标注（复现零偏离纪律）
-------------------------------------------------------------------------------------
UNet3D **有官方示例** src/examples/train_Unet3D.py（同一 M3D-NCA repo 提供的对照 baseline），
故超参逐项取该官方脚本；官方未给 KiTS23 值（input_size 等）的标 KiTS23 适配 TODO。

标注约定：
  # [UNet官方]        —— 取自官方 src/examples/train_Unet3D.py，照搬不动（复现零偏离）。
  # [同M3D-NCA口径]   —— 为与 NCA baseline 可比而对齐 config_kits23 的值。
  # [KiTS23适配TODO]  —— 官方无对应值，给合理默认，须 researcher/用户确认。

⚠️ UNet3D 输入尺寸整除约束（非自由超参）：`unet` 包 UNet3D 在编码器每级做一次 2× 下采样池化，
   输入各维必须能被 2^(池化次数) 整除，否则解码器上采样后与编码器 skip 特征尺寸不匹配会报错。
   fepegar/unet 的 UNet3D 默认编码块数（num_encoding_blocks）随版本不同（常见 3~5 级，即需被
   4 / 8 / 16 整除）。为**保险覆盖到 5 级（需被 32 整除）**，本文件所选尺寸均取 32 的倍数：
     full  (128,128,64) → 128/32=4, 128/32=4, 64/32=2  ✓ 全整除，覆盖 depth ≤5
     smoke ( 64, 64,32) →  64/32=2,  64/32=2, 32/32=1  ✓ 全整除，覆盖 depth ≤5
   ⚠️ 待主线烟测确认：真实 num_encoding_blocks 以 `unet` 装的版本为准；上述尺寸对 4/8/16/32
      整除全满足，最保险，但仍须真跑 `--smoke` 看是否报形状错。标 [KiTS23适配TODO]。
   注：full 的 (128,128,64) 特意对齐 M3D-NCA 最细级 input_size[-1]=(128,128,64)，两模型见到
      的输入体积一致，可比。
=====================================================================================
"""
# 复用 M3D-NCA config 的数据根 / 烟测 case / 产物根，保证同一批 case（同口径命门）。
from config_kits23 import DATASET_ROOT, SMOKE_CASES, _EXP_ROOT


# ------------------------------------------------------------------------------------
# CONFIG_UNET_SMOKE —— 本地 RTX4070 8GB 烟测：几分钟内验管线不报错、loss 下降。
# ------------------------------------------------------------------------------------
CONFIG_UNET_SMOKE = {
    'img_path': DATASET_ROOT,          # img/label 同根，Dataset_KiTS23_3D.__getitem__ 内拼子目录
    'label_path': DATASET_ROOT,
    'model_path': str(_EXP_ROOT / "UNet3D_KiTS23_smoke"),
    'device': "cuda:0",
    'unlock_CPU': True,                # [同M3D-NCA口径] 不限线程（config_kits23 也 True）
    # --- 数据子集 & 目标类（train 脚本读这两个键传给 Dataset_KiTS23_3D，与 NCA 完全同源） ---
    'cases_subset': SMOKE_CASES,       # [同M3D-NCA口径] 同一 5 个含囊肿 case
    'label_mode': 'binary_all',        # train 脚本可用 --label_mode 覆盖
    # Optimizer（全部取自官方 train_Unet3D.py）
    'lr': 1e-4,                        # [UNet官方] 注意：UNet 官方 lr=1e-4，NCA 是 16e-4，各用各的官方值
    'lr_gamma': 0.9999,                # [UNet官方]
    'betas': (0.9, 0.99),              # [UNet官方]
    # Training（烟测缩到最小）
    'save_interval': 10,               # [KiTS23适配TODO] 烟测值（官方 full=100）
    'evaluate_interval': 10,           # [KiTS23适配TODO] 烟测值（官方=10）；每次评估写 state.json
    'n_epoch': 30,                     # [KiTS23适配TODO] 烟测值，几分钟即可（官方 full=1000）
    # Model（UNet3D 用 out_classes=1；channel_n/cell_fire_rate 是 NCA 遗留键，UNet 不用，
    #        沿用官方 train_Unet3D.py 的 config 键位以求一致，Experiment 也会自动补默认值）
    'channel_n': 16,                   # [UNet官方] UNet 不用，官方 config 保留
    'cell_fire_rate': 0.5,             # [UNet官方] UNet 不用，官方 config 保留
    'input_channels': 1,              # [UNet官方] 配 UNet3D(in_channels=1)；Agent_UNet.initialize 读它
    'output_channels': 1,             # [KiTS23适配] 二分类，配 UNet3D(out_classes=1)；官方示例=3(其3类MRI)
    'batch_size': 1,                   # [KiTS23适配TODO] 8GB 烟测保守取 1（UNet 比 NCA 吃显存）；官方=2
    # Data
    'input_size': (64, 64, 32),        # [KiTS23适配TODO] 单一固定尺寸(UNet非两级)；32的倍数满足整除约束
    'data_split': [0.7, 0, 0.3],       # [同M3D-NCA口径] 与 config_kits23 完全一致 → 5 例=4 train/0 val/1 test
    'keep_original_scale': False,      # [同M3D-NCA口径] 与 config_kits23 一致（同预处理口径）
    'rescale': True,                   # [同M3D-NCA口径] 与 config_kits23 一致（rescale3d 到 input_size）
}


# ------------------------------------------------------------------------------------
# CONFIG_UNET_FULL —— HPC gpu4090 24GB 正式对照 baseline。
# ------------------------------------------------------------------------------------
CONFIG_UNET_FULL = {
    'img_path': DATASET_ROOT,          # HPC 上经 env KITS23_ROOT 覆盖（见 submit_unet_hpc.sh）
    'label_path': DATASET_ROOT,
    'model_path': str(_EXP_ROOT / "UNet3D_KiTS23_full"),
    'device': "cuda:0",
    'unlock_CPU': True,                # [同M3D-NCA口径]
    # --- 数据子集 & 目标类 ---
    'cases_subset': None,              # [同M3D-NCA口径] 全 489 例（与 CONFIG_FULL 一致）
    'label_mode': 'binary_all',        # Phase 1a 肾区；Phase 1b 囊肿用 --label_mode cyst
    # Optimizer（官方 train_Unet3D.py）
    'lr': 1e-4,                        # [UNet官方]
    'lr_gamma': 0.9999,                # [UNet官方]
    'betas': (0.9, 0.99),              # [UNet官方]
    # Training
    'save_interval': 100,              # [UNet官方] 官方 train_Unet3D.py=100
    'evaluate_interval': 10,           # [UNet官方] 官方=10；每次评估写 state.json + 发散检测
    'n_epoch': 1000,                   # [UNet官方] 官方 train_Unet3D.py=1000
    # Model
    'channel_n': 16,                   # [UNet官方] UNet 不用，官方 config 保留
    'cell_fire_rate': 0.5,             # [UNet官方] UNet 不用，官方 config 保留
    'input_channels': 1,              # [UNet官方] 配 UNet3D(in_channels=1)
    'output_channels': 1,             # [KiTS23适配] 二分类，配 UNet3D(out_classes=1)；官方示例=3(其3类MRI)
    'batch_size': 2,                   # [UNet官方] 官方=2；24GB 可承，按实测可调
    # Data
    'input_size': (128, 128, 64),      # [KiTS23适配TODO] 对齐 M3D-NCA 最细级(128,128,64)以求可比；32倍数满足整除
    'data_split': [0.7, 0, 0.3],       # [同M3D-NCA口径] 与 CONFIG_FULL 完全一致
    'keep_original_scale': False,      # [同M3D-NCA口径]
    'rescale': True,                   # [同M3D-NCA口径]
}


def get_unet_config(name):
    """按名字取 UNet config 的**副本**（避免多次运行共享可变 dict）。"""
    if name == "smoke":
        return dict(CONFIG_UNET_SMOKE)
    if name == "full":
        return dict(CONFIG_UNET_FULL)
    raise ValueError(f"未知 config 名: {name!r}（只支持 'smoke' / 'full'）")
