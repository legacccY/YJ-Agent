# SSL4MIS 官方超参 + HC18 mask 口径（复现零偏离真源）

> researcher 2026-06-24 核 github.com/HiLab-git/SSL4MIS（带行号引用）。
> **对照协议**：方法特有超参取官方值；训练预算统一（100ep / Adam lr=1e-3 / UNet base32 / CosineAnneal，与 pilot 一致）做公平对照，**不照搬 SSL4MIS 的 SGD/iteration 数**。rampup 单位需从 iteration 换算到我们的 epoch 制。

## 方法特有超参（官方值，必须照用）

| 方法 | 关键超参 | 官方值 | 源 |
|---|---|---|---|
| **CPS** | cps/一致性损失权重 | `consistency=0.1` | train_cross_pseudo_supervision_2D.py |
| | rampup | sigmoid, `consistency_rampup=200`(epoch), `get_current_consistency_weight(iter//150)` | 同上 |
| | 双网络 | 同架构 create_model()×2，随机独立初始化(Kaiming/Xavier)，无显式差异化 | 同上 |
| **UAMT** | EMA decay | `ema_decay=0.99`(固定) | train_uncertainty_aware_mean_teacher_2D.py L~48 |
| | 一致性权重 | `consistency=0.1` + 同 CPS sigmoid rampup(200) | L~141,49 |
| | MC-dropout 次数 | `T=8`（`for i in range(T//2)` 生成8次） | L~131 |
| | 不确定性阈值 | `threshold=(0.75+0.25*sigmoid_rampup(iter,max_iter))*ln(2)`，0.520→0.693，`mask=(uncertainty<threshold)` | L~144-146 |
| **FixMatch-Seg** | 置信阈值 τ | `conf_thresh=0.8`（SSL4MIS，注意≠原FixMatch 0.95/UniMatch 0.95） | train_fixmatch_cta.py / train_fixmatch_standard_augs.py |
| | 增广 | CTAugment 版 or WeakStrongAugment 版（二选一） | 同上 |
| | 伪标签权重 | 并入 consistency=0.1 sigmoid rampup（cta版）/ entropy-adaptive as_weight（standard版） | 同上 |

**MeanTeacher**（pilot 已用，低风险）：EMA=0.99 / cons_w=0.1 / rampup=40ep，对齐 SSL4MIS。

## HC18 椭圆 GT → 分割 mask（社区惯例）

- GT 两形式：CSV(center_x_mm,center_y_mm,semi_a_mm,semi_b_mm,angle_rad) + `*_Annotation.png`(2px 椭圆**轮廓**非实心)
- **分割 mask = 填实心椭圆**（不是用 2px 轮廓训练）：
  ```python
  # mm→px: center_px = center_mm / pixel_size_mm（pixel_size 在 training_set_pixel_size_and_HC.csv）
  mask = np.zeros((H,W),np.uint8)
  cv2.ellipse(mask, center_px, axes_px, angle_deg, 0,360, 1, thickness=-1)  # -1=FILLED
  ```
- resize 到 256²：center/axes 各乘 scale_x/scale_y，**angle 不变**。优先从 CSV 算参数按目标分辨率直接 draw（别 resize 2px PNG 会断裂）。
- HC18 单前景类(head)，NUM_CLASSES=2，harness 需适配可变类数。
- 评测：官方是 HC mm 误差；我们做分割报 Dice+HD95（GT=filled mask）。
- 高星对照：pranjalrai-iitd/Fetal-head-segmentation、junqiangchen/HC18（提供 pre-built mask 下载）。

## TODO（人工 clone 后核）
- FixMatch WeakStrongAugment / CTAugment 具体增广操作列表（raw 未返回 augmentation 类实现）
- 建议 coder clone SSL4MIS 看 `dataloaders/` + `augmentations/ctaugment.py` 取增广细节

## 引用
- SSL4MIS: github.com/HiLab-git/SSL4MIS（CPS/UAMT/FixMatch 各 train_*.py）
- HC18: hc18.grand-challenge.org ; DatasetNinja 确认 filled mask
