# WaveFidBench — DATA_INVENTORY

> 真源 = `.portfolio/datasets.json`。本文件只列本项目数据细目，路径/状态以真源为准，脚本不硬编码。

| 数据集 | 任务 | 来源 | 获取方式 | 状态 |
|---|---|---|---|---|
| Kaggle Alzheimer 4-class | AD 分类(最快可跑) | kaggle.com/datasets/sachinkumar413/alzheimer-mri-dataset | 免申请, Kaggle 免费账户 | todo（⚠️ 先核溯源:确认 OASIS 衍生非 AI 合成）|
| OASIS-1/2 | 第二验证集(增信) | sites.wustl.edu/oasisbrains | 签 Data Use Agreement, 数小时-1天 | todo |
| MIRIAD | 备选(46 AD+23 对照, 708 扫描) | nitrc.org/projects/miriad | 需 acknowledgment 不需 IRB | optional |

## baseline / 工具 repo（立项核查已验）

| 工具 | 用途 | repo | star |
|---|---|---|---|
| pytorch_wavelets | 2D DWT, 子带置零(Yl=LL, Yh=LH/HL/HH) | github.com/fbcotter/pytorch_wavelets | 1.2k |
| PyTorch-Wavelet-Toolbox | 可微小波(备选) | github.com/v0lta/PyTorch-Wavelet-Toolbox | — |
| Quantus | XAI faithfulness (ROAD/IROF/PixelFlipping) | github.com/understandable-machine-intelligence-lab/Quantus | 666 |
| captum | Grad-CAM/IG/SHAP | pytorch captum | — |
| WaveFormer | 频域 attention 设计借鉴(3D 分割非分类,不当 baseline) | github.com/mahfuzalhasan/WaveFormer | — |

## 待办（2026-06-24 researcher 清点 + 拍板更新）

- [x] 核 Kaggle 4-class 溯源：原 `sachinkumar413` slug 已 403/下架；溯源结论=OASIS-1 切片重分发**非合成**但**无 patient ID**→拍板降为**烟测替身**，正式主集改 **OASIS**（自带 subject ID）。烟测实下载 `lukechugh/best-alzheimer-mri-dataset-99-accuracy`(MIT, 4 类 Combined Dataset, 已平衡增强集) 到 `data/alzheimer_kaggle/`，仅验工程管道。
- [x] Quantus 无独立 insertion/deletion（`PixelFlipping`=deletion）→ insertion 已自实现 <50 行（LeRF 反转顺序，烟测 AUC 非 nan 验通）。
- [ ] OASIS-1/2 access 用户申请中（正式主集，对外，sites.wustl.edu/oasisbrains）→ 到位后填 `configs/gate1_oasis.yaml` data_root + 登记 `.portfolio/datasets.json`。
- [ ] 2601.19017 频带摄动忠实度方法（音频域无代码）思路自实现，引用诚实标（Gate2 才用）。

## Gate1 烟测状态（2026-06-24）

CPU tiny 烟测（87 图子集，1 epoch，`configs/gate1_smoke.yaml`）e2e 跑通验工程地基：
- `data_split.py` ✅（slice + patient 双模式，patient subject ID 提取 bug 已修）
- `train_classifier.py` ✅（ResNet50 CPU，--smoke flag 强制 CPU 不占卡槽）
- `subband_zero.py` ✅（**W-base 重建 acc=直通 acc，DWT→IDWT 往返无损**；4 子带置零各出 acc_drop）
- `faithfulness.py` insertion 自实现 ✅ 非 nan；Quantus 3 指标修 model 传参中
- pytest 23/23 PASS。烟测暴露并修 6 个真 bug（详见 04_LOG Entry2）。
正式数字待 GPU（local 被 ideation-run011 占 / HPC 2 卡空待上传拍板）+ OASIS 到位。
