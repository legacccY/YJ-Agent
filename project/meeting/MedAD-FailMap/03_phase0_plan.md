# MedAD-FailMap — Phase 0 可行性预检设计

> planner 产出（2026-06-16）。对齐收紧后 `02_ACCEPTANCE.md`。Phase 0 = 三道证伪闸，最小代价验最危险前提，任一红灯先修/转退路，不硬推 Phase 1。

## 定位：三道证伪闸（非缩小版全量）

| 闸 | 验的前提 | 塌了后果 | Pillar |
|---|---|---|---|
| **PC-A**（地基） | 协变量能受控操纵出**系统**失败变化（且见非单调/交互苗头） | ① 无地基 | ① |
| **PC-C**（防循环论证） | conspicuity 无 mask 代理 given anomaly score 后有**增量信息** | ③ 平凡（重命名「大病灶好检」） | ③ |
| **PC-B**（可外推） | 失败边界**跨集外推**雏形 + **赢 size 单变量 strong baseline** | ② 沦为装饰 | ② |

顺序：PC-A 先（地基）→ PC-C 并行（纯 CPU 软活，只需 A0 的 anomaly score）→ PC-B 后（最贵，依赖 PC-A 确认有信号）。

## 最小数据 + 方法

- **主分层集 = BraTS2021**（脑 MRI FLAIR，**有像素 mask**——切 size/contrast 协变量的刚需；MedIAnomaly 7 集只有它和 Camelyon16 有 mask）。todo 待下 Zenodo。
- **跨模态外推对照 = 本地 HAM10000 NV 子集**（6705 图，nevus=正常，**零下载 ready**）。
- **方法 = AE + VAE**（重建 AD 原型 + ④ 最便宜第二方法）。**超参一律照 MedIAnomaly 官方 repo，复现零偏离**。
- Phase 0 **不下全 7 集**；RSNA/VinDr（无 mask 不能切 size）、Camelyon16（大、patch 繁）不碰。

## 实验矩阵（关键 run）

**PC-A（Pillar ①）**：A0-train-AE（BraTS 正常切片训 AE）→ A1-strat-size（按 mask 面积分桶，检出率随 size 单调↑）/ A2-strat-contrast（病灶 vs 环带强度差分桶）/ **A3-interact-2D（size×contrast 3×3 网格，看交互苗头——收紧判据命门）**。

**PC-C（Pillar ③，纯 CPU 软活）**：C1 提无 mask 代理（σ/GLCM Cluster Prominence·Contrast/FFT 频谱熵/Otsu CNR_proxy）→ **C2 增量信息**（嵌套逻辑回归 LR 检验：base=anomaly score，full=+conspicuity）→ **C3 残差预测**（回归掉 size+contrast 后 conspicuity 仍有预测力）→ **C4 selective AUROC**（risk-coverage 曲线）。三件套任一不过 → ③ 诚实退守，不落「桥成立」。

**PC-B（Pillar ②）**：B0-train-HAM（HAM-NV 训第二 AE）→ B1 在 BraTS 拟合失败=f(size,contrast)边界 → **B2 跨集零调参外推**（BraTS→HAM-NV，AUROC≥集内 80% 且≥0.70，雏形未达标黄）→ **B3 vs strong baseline**（多维边界须显著超 size / size+contrast 回归）→ B4 extrapolation（训中等 size→测未见极小 size，非 i.i.d.）。

## 算力 + 依赖

- **GPU 仅两次训练**：A0-train-AE + B0-train-HAM，各 ~2-4 GPU·h，**合计 6-9 GPU·h**，单卡 4090 足，**绝不同时启**（主线串行各持训练锁）。
- **其余纯 CPU 软活**：C1-C4、B1-B4（scikit-image + sklearn，分钟级），coder 实现即可跑不抢 GPU。
- 数据下载是前置非训练，可先做。

## Gate 0 决策表

| 结果 | 决策 |
|---|---|
| PC-A 绿（≥2 轴系统+A3 交互苗头）+ PC-C 绿（增量信息非零）+ PC-B 雏形不塌 | **全绿→Phase 1**（扩 ≥3 集严判 Gate 1） |
| PC-A 红（协变量无系统变化） | 停，重审协变量/数据（换合成可控异常或换 size 口径）；仍红→方向不成立报拍板 |
| PC-A 绿但 A3 无交互（纯单变量） | 黄→报拍板：补 texture/位置轴找交互，找不到→② 降级走 MICCAI 退路 |
| PC-C 红（增量信息=0/残差塌） | ③ 诚实退守，砍 per-image 判据，①② 仍成立项目继续 |
| PC-B 红（跨集塌随机/输给 size baseline） | 报拍板：退守「受控失败现象学」MICCAI 档，产物不白做 |

## 前置 TODO + 风险

- **researcher 锁官方超参**（最高优先前置）：从 `github.com/caiyu6666/MedIAnomaly` 锁 AE/VAE 的 latent dim/输入尺寸/optimizer/lr/epochs/loss(L2 vs SSIM) + BraTS2021 预处理与切片划分协议。查不到标 TODO 不臆想。
- **协变量口径**：size 按连通域面积、contrast 用病灶 vs 3px 膨胀环带均值差（雏形，Gate 0 复裁）。
- **gCNR 不用于 per-image 判据**（需 mask）；仅 PC-A 分层时可选作 contrast 定义。
- **跨模态雏形偏弱**（仅 BraTS→HAM 一对）：B2 未达标只标黄不判死，Phase 1 扩 ≥3 集再严判。
- **多重比较**：A3/C2-C4/B3 预登记检验清单 + Holm/FDR 校正（ACCEPTANCE 硬要求）。
- ⚠️ 主线/Opus 复核点：PC-B 跨模态雏形仅 1 对统计力弱 + size/contrast 精确口径。

## 交接链
researcher（锁超参 ✅）→ coder（5 个脚本：AE/VAE 训练 / 分层评估器 / conspicuity 代理提取 / 增量统计含 FDR / 边界拟合+外推+baseline）→ 🛑主线跑两次 GPU 训练（拍板点+训练锁）→ analyst（Gate 0 收口）→ reviewer 复裁雏形阈值。

---

## 附：MedIAnomaly 官方超参锁定（researcher 核 repo `github.com/caiyu6666/MedIAnomaly`，复现零偏离照此，几乎全 🟢官方明确）

**AE**（`reconstruction/networks/ae.py` + `options.py`）：4 block encoder/decoder（16× 降采样），通道 16→32→64→64（base C=16，depth 各 1）；latent dim=16；输入 **64×64**；in_c=1（灰度）；**无数据增强**。
**VAE**（`networks/vae.py` + `losses.py`）：同 AE 结构 + VaeBottleNeck（mu/log_var/reparam）；latent=16；**KL β=0.005**；loss=L2 recon + 0.005·KL。
**训练**（`base_worker.py` + `options.py`）：Adam lr=**1e-3** wd=0，**无 scheduler**（cosine 被注释），bs=**64**，epochs BraTS=**250**（'brats' key）/ISIC=250。
**AE loss**：L2 = `(net_in - x_hat)²` 的 mean（变体 ae-l1/ae-ssim/ae-perceptual）。
**Anomaly score**（`ae_worker.py`）：per-pixel L2 map → 图像级 = `torch.mean(score_maps, dim=[1,2,3])`（spatial mean），**无后处理**。评估=AUROC + APpix + best Dice。
**BraTS2021**（`dataload.py BraTSAD` + arXiv v4）：FLAIR axial 2D 切片；train=**4211 normal**（1051 scans，相邻切片≥5 间隔）；test=**828 normal + 1948 tumor**（200 scans）；正常=无肿瘤，异常 mask 在 `test/annotation/`（pixel>0=肿瘤，**协变量分层就用这个 mask**）；central crop 70×208×208 → resize **64×64**；`Normalize((0.5,),(0.5,))`→[-1,1]。
**ISIC2018/HAM-NV**（`dataload.py ISIC2018`）：NV=1 正常（train **6705**），test 909 normal + 603 abnormal；64×64；同 Normalize；无增强；recon 方法转灰度。
**可复用脚本**：`reconstruction/{dataloaders/dataload.py, utils/losses.py, utils/ae_worker.py, utils/vae_worker.py, utils/base_worker.py, train.py, test.py}`，调用 `-d brats -m ae -g 0`。
**🔴 TODO**：BraTS NIfTI→2D 切片的预处理脚本 repo 未公开（论文给了 central crop 70×208×208 + axial 采样口径）——预处理好的切片应在 **Zenodo 打包（records/12677223）的 MedIAnomaly-Data** 里，下载后核对目录结构 `train/ test/normal/ test/tumor/ test/annotation/`；若缺则查 repo Issues 或联系作者。
