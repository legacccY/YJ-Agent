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

## 待办

- [ ] 核 Kaggle 4-class 数据溯源（确认 OASIS 真实衍生而非 AI 合成伪造；存疑改用 OASIS 官方）→ 登记 `.portfolio/datasets.json`
- [ ] 确认 Quantus 是否含独立 insertion/deletion（否则 PixelFlipping 等价 + 自实现 <50 行标清楚）
- [ ] 2601.19017 频带摄动忠实度方法（音频域无代码）思路自实现，引用诚实标
