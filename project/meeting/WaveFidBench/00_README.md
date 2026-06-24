# WaveFidBench — Wavelet 频域子带视角的 XAI 忠实度 benchmark（AD 分类）

> 组合台子项目入口。源自选题流水线 `project/ideation/runs/2026-06-24` G6 立项（headline 2，双 headline 并行之一；姊妹篇 [[HyperFidBench]]）。立项日 2026-06-24（用户拍板双 headline 并行）。
> 对齐导师王水花(Shuihua Wang)**wavelet×Transformer + 可解释双招牌**。

## 一句话

把 wavelet 分解的 **LL/LH/HL/HH 子带作为可控分解轴**，评测不同频带承载的 Alzheimer 判别信息 vs Grad-CAM/SHAP 解释热图覆盖的忠实度——**首次从频域视角拆解解释忠实度**。

## 核心 RQ

AD 脑 MRI 分类中：①不同 wavelet 频带(低频结构 / 高频纹理)各承载多少判别信息(子带置零的精度损失)？②Grad-CAM/SHAP 等解释热图是否对齐真正承载判别信息的频带，还是被高频噪声带偏？③哪类 XAI 在哪个频带最忠实(ROAD/IROF/insertion-deletion)？

## 立项证据（G5 地基核查全绿）

- **数据** 🟢：Kaggle Alzheimer 4-class(6400 张 JPG, NonDemented/VeryMild/Mild/Moderate)**当天免申请可下**；OASIS-1/2 签 DUA 数小时可得。
- **baseline** 🟢：pytorch_wavelets(1.2k⭐, 2D DWT, 返回 Yl/Yh, 子带置零 3 行 tensor 操作)；ResNet/ViT 分类器现成。
- **指标** 🟢：Quantus(666⭐, ROAD/IROF/PixelFlipping/RegionPerturbation faithfulness)+captum(Grad-CAM/IG/SHAP)。
- **撞车** 🟢 干净：最近邻 WaveletFusion(2026-05 Haar+CNN AD 分类，**无 XAI 忠实度维度**)、2601.12826(Grad-CAM 忠实度但肺 CT 无 wavelet)、2407.08546(AD 显著图但无 wavelet 子带)。两维交叉空白确认。

## 命门 / 最大风险（动手前必解）

WaveletFusion(2026-05)是结构最近邻 → 本文**必须定位成 evaluation benchmark 而非新分类模型**，novelty 锚定「**频带分解作忠实度的可控轴**」(多 XAI × 多子带 × 多 faithfulness 指标系统对比)，绝不停在"wavelet+GradCAM 试一下"。

## venue

- top：**ACCV 2026**（Biomedical Image Analysis track；截稿 2026-07-05 大阪）
- fallback：CBM / BSPC / Computerized Medical Imaging

## 数据

| 数据集 | 角色 | 状态 |
|---|---|---|
| Kaggle Alzheimer 4-class | AD 分类主战场(最快可跑) | 免申请当天可下 |
| OASIS-1/2 | 第二验证集(增信) | 签 DUA, 数小时-1天 |
| MIRIAD | 备选(46 AD+23 对照) | NITRC 可申请 |

## compute

<5 GPU·h（XJTLU HPC 或本机；2D MRI 分类轻量 + Quantus 评测多为推理）。

## 读档顺序

`00_README.md`（本文）→ `01_STORY.md` → `02_ACCEPTANCE.md`（含书面 kill criteria）→ `DATA_INVENTORY.md` → `04_LOG.md` 最新 entry。

## 文件导航

| 路径 | 内容 |
|---|---|
| `01_STORY.md` | 核心 Claim + 章节弧 + 与组合台边界 + 防御写法 R-rules |
| `02_ACCEPTANCE.md` | 二元 PASS/FAIL 验收 + kill criteria |
| `04_LOG.md` | 进度留痕（首条=立项决策）|
| `DATA_INVENTORY.md` | 数据细目（真源 .portfolio/datasets.json）|
| `src/` `tests/` | 实验代码 + pytest（待建）|
| `figures/` | 独立图表目录（待建）|
