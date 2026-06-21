# 官方/高赞开源代码复用清单（反自搓踩坑）

**日期**：2026-06-21
**触发**：用户质疑「自搓外壳惯性」→ 盘查整个项目该用官方的东西（GitHub 高星 + Kaggle 高赞）。
**原则**：基础设施一律用官方/高赞验证过的，**自搓只留 4 个 novelty 件**（DifferentiableFrangi / ReIDReadoutHead / SR·re-ID 指标 / 断点标注扩展）。

---

## 已对接官方（保持）
| 组件 | 官方 | 状态 |
|---|---|---|
| 拓扑指标 clDice/Skeleton-Recall/Betti | [jocpae/clDice](https://github.com/jocpae/clDice)⭐285 / [MIC-DKFZ/Skeleton-Recall](https://github.com/MIC-DKFZ/Skeleton-Recall)(ECCV24) / [nstucki/Betti-Matching-3D](https://github.com/nstucki/Betti-Matching-3D) | wrapper 已调 ✓ |
| 断点合成 | [creatis-myriad/plug-and-play-reco-regularization](https://github.com/creatis-myriad/plug-and-play-reco-regularization)（`disconnect.py`） | 已对齐 ✓ |
| GDN-2 kernel | [fla-org/flash-linear-attention](https://github.com/fla-org/flash-linear-attention)（`GatedDeltaNet2`/`GatedLinearAttention`/`LinearAttention`） | 已用 ✓ |
| MQAR harness | [HazyResearch/zoology](https://github.com/HazyResearch/zoology) | 改用中（run_zoology_pure.py）✓ |
| baseline | FR-UNet 等各官方 repo | copy 入 third_party ✓ |

## 待换（血管主实验 P1，换掉自搓 dataloader/backbone）
| 我们自搓 | 该换官方（⭐star） | 借什么 |
|---|---|---|
| `models/unet.py`（vanilla CNN 无预训练，审稿第一枪） | `segmentation_models_pytorch`（500+ 预训练 encoder）/ 或 nnU-Net/MONAI 当地基 + GDN-2 插件 | 预训练 backbone baseline |
| `datasets/`（自搓 DRIVE/CHASE 加载预处理，踩 cv2/gif 坑） | ★ [lseventeen/FR-UNet](https://github.com/lseventeen/FR-UNet)（视网膜+冠脉 DRIVE/CHASE/STARE/DCA1/CHUAC 全覆盖，`data_process.py` patch48/stride6/二值化）+ [orobix/retina-unet](https://github.com/orobix/retina-unet)⭐1.4k（CLAHE clipLimit=2.0/tile8×8 + gamma1.2 + 48×48 patch，**Kaggle notebook 原型来源**） | **DRIVE/CHASE data load + 预处理直接抄** |
| `train_pilot.py`（lr=1e-3 vs FR-UNet 官方 1e-4、BCE+Dice vs 纯 BCE = 复现红线偏离） | FR-UNet `config.yaml` / MONAI Engine | 训练超参对齐 |
| 续连指标设计 | [tyb311/SkelCon](https://github.com/tyb311/SkelCon)（骨架先验+对比 loss，TMI22，跟 headline 最相关）/ [agaldran/lwnet](https://github.com/agaldran/lwnet)⭐94（W-Net 70k 参数 SOTA，自动下 7 数据集） | 连通性评估 + 轻量 baseline |

## Kaggle（数据处理参考，upvote 需人工登录确认）
- [orobix/retina-unet](https://github.com/orobix/retina-unet) 是 Kaggle 绝大多数 DRIVE notebook 的预处理原型（gray→std→CLAHE→gamma→/255，48×48 patch 190k，无增强靠 patch 抖动）。
- ipythonx Starter 系列（Starter→SegFormer→GradCAM 三连版，最活跃维护，建在 `nikitamanaenkov/fundus-image-dataset` 上）。
- ⚠️ **TODO**：精确 upvote 排名 Kaggle 登录墙挡，需人工登录 `kaggle.com/datasets/andrewmvd/drive...` → Code → Most Votes。

> 预处理共识（多 repo 交叉）：CLAHE(clipLimit=2.0,tile=8×8) + gamma≈1.2 + 标准化 + 48×48 patch；薄血管**对强增强脆弱**，只用翻转+旋转，别上 sunflare/弹性形变（debuggercafe 实证）。green channel：很多 repo 直接 rgb2gray（≈0.587G 加权），显式 G 通道用 `img[:,:,1]`。

> 用途：当前卡在 MQAR go/no-go（用 run_zoology_pure 纯 Zoology 验）；本清单主要服务 **headline 定了之后的 P1 血管主实验**——届时 backbone/dataloader/预处理全换官方，只留 4 个 novelty 件自搓。
