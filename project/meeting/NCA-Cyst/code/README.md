# NCA-Cyst · code/ — M3D-NCA × KiTS23 baseline 管线

服务 NCA-Cyst § Phase 1a/1b baseline，lever = 打通官方 M3D-NCA 在 KiTS23 囊肿分割的数据/训练管线。

官方代码零改复用：`../../Med-NCA/M3D-NCA-official/`（模型/agent/loss/Experiment 全用其原类）。
所有 KiTS23 适配都在本目录新文件里，官方 repo 一个文件都没动。

## 文件

| 文件 | 作用 |
|---|---|
| `kits23_dataset.py` | `Dataset_KiTS23_3D`：官方 `Dataset_NiiGz_3D` 子类，直接读 `case_XXXXX/` 原生嵌套结构（**不扁平化复制 34GB**）。支持 `label_mode`（binary_all/cyst）与 `cases_subset`（烟测子集）。 |
| `config_kits23.py` | `CONFIG_SMOKE`（本地8GB烟测）+ `CONFIG_FULL`（HPC 24GB 正式）。每个超参标注来源（官方固定 / 官方分歧 / KiTS23适配TODO）。 |
| `train_kits23.py` | 训练入口。仿官方 `train_M3D_NCA.py`，加 state.json 实时监控 + 发散检测。 |
| `cyst_cases.json` | （主线已产）248 含囊肿 case 按体素降序 + `smoke_top5`。烟测子集取自此。 |
| `kits23_cyst_dist.py` | （主线已产）扫全库统计各 label 体素分布的脚本。 |
| `config_unet_kits23.py` | **（Phase 1c）** UNet3D 两套 config（smoke/full）。`import` config_kits23 的 `DATASET_ROOT`/`SMOKE_CASES`（同 case），超参取官方 `train_Unet3D.py`。 |
| `train_unet_kits23.py` | **（Phase 1c）** UNet3D 训练入口。仿 `train_kits23.py`（同 state.json 监控 + env 路径），模型换官方 `UNet3D` + `Agent_UNet` + `DiceBCELoss`，评估用同一 `agent.test(DiceLoss)`。 |
| `submit_unet_hpc.sh` | **（Phase 1c）** UNet3D full HPC SLURM 提交（job=ncacystU1c，落 `runs/unet_full_binaryall_seed0`）。 |

## 怎么跑（由主线跑；coder 不自跑）

本地烟测（conda env `mednca`，RTX4070 8GB，几分钟）：
```
python train_kits23.py --config smoke --label_mode binary_all --seed 0
```
- 只加载 5 个含囊肿 case（`config_kits23.SMOKE_CASES`），小体积 `[(32,32,16),(64,64,32)]`，30 epoch。
- 验通判据：不报错 + train loss 下降 + state.json 正常刷新。想更快加 `--n_epoch 5`。
- Phase 1b 囊肿模式：`--label_mode cyst`（用含囊肿 case 才有非零前景）。

HPC gpu4090 24GB 正式 baseline：
```
python train_kits23.py --config full --label_mode binary_all --seed 0   # Phase 1a 肾区
python train_kits23.py --config full --label_mode cyst        --seed 0   # Phase 1b 囊肿
```
> HPC 上须先把 `config_kits23.DATASET_ROOT` / 或 `--` 不支持路径覆盖，改 config 里 img_path/label_path
> 为 HPC 端 KiTS23 路径（数据上传是拍板点，主线串行做）。

## Phase 1c — UNet3D 同口径对照（证「主流模型囊肿近随机 vs NCA 能跑」）

三个新文件（`config_unet_kits23.py` / `train_unet_kits23.py` / `submit_unet_hpc.sh`）跑官方 UNet3D
作对照，**和 M3D-NCA 完全同口径**，同表对比。

⚠️ **依赖 `unet` pip 包**：`train_unet_kits23.py` 用 `from unet import UNet3D`（官方 `train_Unet3D.py`
的依赖），**不在官方已验证依赖里，HPC 可能没装**。主线部署时**先在 HPC DTN 上装**：
```
pip install unet
```
装好再提交 `submit_unet_hpc.sh`。本地烟测同理需先装。

**同口径对齐点**（命门——任何不一致对比即无效，逐条确认）：
- **同 Dataset**：复用 `Dataset_KiTS23_3D`（同 `__getitem__` 预处理 / torchio 归一化 / label 处理）。
- **同 case 集**：`config_unet_kits23` 直接 `import` config_kits23 的 `DATASET_ROOT` + `SMOKE_CASES`，
  不重定义 → smoke 用同一 5 个囊肿 case，full 同为全 489 例（`cases_subset=None`）。
- **同 split**：`data_split=[0.7,0,0.3]` 与 M3D-NCA 完全一致（官方 DataSplit 按 case 序 index 切）。
- **同 label**：`label_mode`（binary_all/cyst）走 Dataset 同一逻辑，`--label_mode` 切换。
- **同评估**：训练/收尾用官方 `agent.test(DiceLoss)` / `getAverageDiceScore()`，与 NCA 同一 Dice 口径。
- **唯一变量 = 模型**：NCA → 官方 `UNet3D(in_channels=1, padding=1, out_classes=1)` + `Agent_UNet`
  + `DiceBCELoss`（UNet 官方三件套，零改）。

**超参**（取自官方 `src/examples/train_Unet3D.py`，非硬套 NCA 的）：
lr=1e-4、betas(0.9,0.99)、lr_gamma=0.9999、DiceBCELoss、batch_size=2（full）、n_epoch=1000（full）、
evaluate_interval=10、save_interval=100。KiTS23 无官方值的（input_size、smoke 各值）标 `[KiTS23适配TODO]`。

⚠️ **UNet3D 输入尺寸整除约束**：`unet` 包 UNet3D 编码器每级 2× 下采样，输入各维须被 `2^池化次数` 整除。
默认编码块数随版本不同（常见 3~5 级 = 需被 4/8/16 整除）。本 config 所选尺寸取 **32 的倍数**保险覆盖到
5 级：full `(128,128,64)`（对齐 M3D-NCA 最细级以求可比）、smoke `(64,64,32)`，两者对 4/8/16/32 整除全满足。
**待主线烟测确认**真实 num_encoding_blocks（以装的 `unet` 版本为准，真跑 `--smoke` 看是否报形状错）。

跑法（由主线跑；coder 不自跑）：
```
# 本地烟测（先 pip install unet；8GB，几分钟，batch=1/尺寸(64,64,32)/30ep）
python train_unet_kits23.py --config smoke --label_mode binary_all --seed 0

# HPC full（先 pip install unet）
python train_unet_kits23.py --config full --label_mode binary_all --seed 0   # Phase 1a 肾区对照
python train_unet_kits23.py --config full --label_mode cyst        --seed 0   # Phase 1b 囊肿对照
# 或 sbatch submit_unet_hpc.sh（HPC）
```

## state.json 监控

训练每 epoch 写 `<model_path>/state.json`（原子写）：
```json
{"status": "running|starting|diverged|done|crashed",
 "epoch": N, "avg_loss": ..., "dice": ..., "max_steps": M, "config":..., "label_mode":..., "seed":...}
```
- `status='diverged'`：ep≥10 后 train loss>3 且 test Dice<0.05（NCA 发散 signature）→ 主线可 scancel。
- 主线 loop 监控读 state.json 判进度（比 stdout 解析可靠，context 压缩不断链）。

## 超参来源（复现零偏离）

官方**无 KiTS23 配置**，且官方两套示例互相不一致：
- **A** = `train_M3D_NCA.py`：betas(0.5,0.5)/1000ep/steps[10,10]/input[(32,32,26),(64,64,52)]/scale2/keep_scale True
- **B** = `train_M3D_NCA.ipynb`（官方"真实数据集"配置）：betas(0.9,0.99)/3000ep/steps[20,40]/input[(80,80,6),(320,320,24)]/scale4/keep_scale False

`config_kits23.py` 逐项标注取哪套。要点：
- **[官方固定]**（A=B，零偏离）：Adam、ExponentialLR、cell_fire_rate=0.5、channel_n=16、hidden_size=64、
  DiceFocalLoss、data_split=[0.7,0,0.3]、train_model=1、lr=16e-4、lr_gamma=0.9999、**无梯度裁剪**、模型架构。
- **[官方分歧->选B]**：betas(0.9,0.99)、keep_original_scale=False（跟"真实数据集"配置）。
- **[KiTS23适配TODO]**（官方无值，须 researcher/用户确认）：input_size、inference_steps、n_epoch、batch_size。
- ⚠️ `scale_factor` 非自由超参——必须 == input_size 层间比值（本文件两套都=2）。改 input_size 要同步改它。

## 关键设计决策 / 待主线验证的点

1. **路径 override（必须主线真跑烟测验证）**：官方 `__getitem__` 用同一 `img_name` 拼 image 和 label
   两个路径（假设两扁平目录同名）。KiTS23 是 `case_XXXXX/{imaging,segmentation}.nii.gz` 嵌套。
   处理方式：`img_path=label_path=dataset根`，`getFilesInPath` 返回 case 目录名当"文件名"，
   复制 `__getitem__` 仅改路径拼接为 `os.path.join(root, case_id, 'imaging.nii.gz'/'segmentation.nii.gz')`。
   **这条是最需要真跑验证的**——若父类还有别处写死扁平路径，烟测会暴露。
2. **label 缓存不被污染**：官方 `label[label>0]=1` 是**原地**改，会把缓存里的多类原始 label 破坏；
   `cyst` 模式第二 epoch 会对已二值化 label 取 `==3` 得全零。本子类改用**非原地**赋值
   （`(label>0)` / `(np.rint(label)==3)`），保住缓存多类原始值。二值化结果与官方等价。
3. **cases_subset 走构造参数不走 config**：官方 `Experiment()` 在 `set_experiment()` 之前就调
   `getFilesInPath`，那时 `self.exp` 没挂上，读不到 config。故子集只能构造时传。
4. **训练循环复制**：官方 `BaseAgent.train` 无监控钩子，`run_training` 逐行复制其循环体、仅插入
   state.json 写入与发散判定，训练步骤零改。
5. **极端类不平衡**（囊肿体素占比中位 6.5e-5）：Phase 1b cyst 模式大概率难收敛/Dice 低——这是
   **数据事实**不是 bug，属 baseline 预期结果，不许为凑收敛私改官方超参（复现零偏离红线）。
6. **NCA seed 锁不住命运**：同 seed 可能一次收敛一次发散，须跑多 seed 报收敛率（见发散 signature 记忆）。
