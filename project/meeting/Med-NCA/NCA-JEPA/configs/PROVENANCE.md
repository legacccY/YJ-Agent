# NCA-JEPA 超参来源审计（红线 10 单一真源）

> **目的**：分清哪些设置遵循官方、哪些是我们自定。每值标来源，可审计、可辩护。
> **核实日期**：2026-06-16（本会话联网核 CheXWorld `opts.py` + `PRETRAIN.md` + I-JEPA repo）。
> **来源**：
> - CheXWorld `opts.py`（argparse 默认）+ `PRETRAIN.md`（实际预训练命令，覆写部分默认）：https://github.com/LeapLabTHU/CheXWorld
> - I-JEPA `facebookresearch/ijepa`（我们的代码地基，train.py/transforms.py）

## 图例
- 🟢 **官方对标**：值 = CheXWorld 官方（opts.py 默认或 PRETRAIN.md 命令），已联网核实
- 🔵 **I-JEPA 默认**：用 I-JEPA 代码原值（未覆写）
- 🟡 **pilot 自定义**：我们为 pilot 主动改（加速/缩水/单卡），**非官方**，明确标注
- 🔴 **我们自创方法**：SCP-JEPA NCA 参数，本就无官方对标（A1/A2 用）
- ⚠️ **偏差/需注意**：与官方不符或注释曾误导，已澄清

## 数据 / 增强
| 字段 | 我们值 | 来源 | 核实 |
|---|---|---|---|
| color_jitter_strength | 0.2 | 🟢 CheXWorld opts.py `color_jitter=0.2` | ✅ 属实 |
| use_color_distortion | true | 🟢 CheXWorld aug_type=jit | ✅ |
| use_horizontal_flip | true (p=0.5) | 🟢 CheXWorld flip_prob=0.5 = I-JEPA RandomHorizontalFlip 默认 | ✅ |
| use_gaussian_blur | true | ⚠️ CheXWorld iwm_blur_prob=**0.2**，但 I-JEPA `transforms.py::GaussianBlur` 硬编码 **p=0.5**，我们 config 只能开关不能设 prob → **实跑 0.5 非 0.2**（旧注释「CheXWorld 0.2」误导，已更正） | ⚠️ 偏差 |
| crop_scale | [0.3,1.0] | 🟢 CheXWorld PRETRAIN `--scale_min 0.3`（opts.py 默认 0.08 被覆写） | ✅ |
| batch_size | 64 | 🟡 **我们单卡选择**；CheXWorld 是 128×accum2=**256 effective** | ⚠️ 我们 deviate |
| crop_size | 224 | 🟢 CheXWorld input_size 224 | ✅ |

## Mask
| 字段 | 我们值 | 来源 | 核实 |
|---|---|---|---|
| enc_mask_scale | [0.85,1.0] | 🟢 CheXWorld **opts.py 默认 (0.85,1.0)**；但 PRETRAIN.md 命令用 `0.75 1.0` → 两者并存，我们取 opts 默认，**可辩护非臆想** | ✅（注 recipe 用 0.75）|
| pred_mask_scale | [0.15,0.2] | 🟢 CheXWorld opts.py `(0.15,0.2)` | ✅ |
| min_keep | 10 | 🟢 CheXWorld opts.py `mask_min_keep=10` | ✅ |
| num_enc_masks | 1 | 🟢 CheXWorld opts.py `mask_nenc=1`（亦 = 我们 NCA predictor 当前限制，双重正当） | ✅ |
| num_pred_masks | 4 | 🟢 CheXWorld opts.py `mask_npred=4` | ✅ |
| aspect_ratio | [0.75,1.5] | 🔵 I-JEPA 默认 multiblock aspect ratio | I-JEPA |
| patch_size | 16 | 🟢 ViT-S/16 标准 | ✅ |

## Meta / 模型
| 字段 | 我们值 | 来源 | 核实 |
|---|---|---|---|
| model_name | vit_small | 🟡 **pilot 加速**；CheXWorld 用 vit_base（主攻再升） | ⚠️ 我们 deviate |
| pred_depth | 6 | 🟢 CheXWorld `pred_depth=6` | ✅ |
| pred_emb_dim | 384 | 🟢 CheXWorld `pred_emb_dim=384` | ✅ |
| use_bfloat16 | true | 🔵 I-JEPA 默认 | I-JEPA |

## 优化
| 字段 | 我们值 | 来源 | 核实 |
|---|---|---|---|
| lr | 2e-4 | 🟢 CheXWorld PRETRAIN `--lr 2e-4` | ✅ |
| weight_decay | 0.05 | 🟢 CheXWorld PRETRAIN `--weight_decay 0.05`（opts.py 默认 0.04 被覆写）| ✅ |
| final_weight_decay | 0.05 | 🟢 CheXWorld `--weight_decay_end 0.05`（恒定不 ramp）| ✅ |
| final_lr | 1e-6 | 🟢 CheXWorld `--min_lr 1e-6` | ✅ |
| ema | [0.996,1.0] | 🟢 CheXWorld `--ema 0.996`（start）+ end 1.0（I-JEPA 惯例）| ✅ |
| ipe_scale | 1.25 | 🟢 CheXWorld `--ipe_scale 1.25` | ✅ |
| epochs | 50 | 🟡 **pilot 缩水**；CheXWorld 300 | ⚠️ 我们 deviate |
| warmup | 5 | 🟡 **pilot 按比例缩**；CheXWorld warmup_epochs 40 | ⚠️ 我们 deviate |
| start_lr | 4e-5 | 🟡 **我们按 I-JEPA start/ref≈0.2 推算**，非 CheXWorld 明确值 | ⚠️ 我们推算 |
| (clip_grad) | **无** | 🟡⚠️ CheXWorld 用 `--clip_grad 1`，**我们故意不加**——三件套是 SN+EMA+Det（理论 §6），加 grad clip 会同时稳住 A1/A2 **掩盖 NCA 不稳定性**（PC-1 正要观察）。**这是 pilot 科学设计选择，非遗漏** | ⚠️ 我们故意 deviate |
| loss | smooth_l1 | 🔵 I-JEPA train.py 默认；CheXWorld 用 `--loss_type l2`（差异，未对齐）| ⚠️ I-JEPA 默认 |

## NCA 方法参数（🔴 我们自创 SCP-JEPA，A1/A2 用，无官方对标）
| 字段 | 值 | 依据 |
|---|---|---|
| nca_steps | 16 | 02_理论框架 §1.2（latent 网格步数，远小于像素 Med-NCA 128）|
| fire_rate | 0.5 | 官方 Med-NCA BackboneNCA cell_fire_rate=0.5（沿用复现的官方 NCA 语义）|
| nca_hidden | 128 | 我们设（per-cell MLP 隐藏维）|
| stabilize (SN) | A2=true | 三件套之 Spectral Norm（理论 §1.1）|
| deterministic | A2=true | 三件套之 Det fire-mask（理论 §3.2）|

## A1/A2 开跑前 TODO（红线 10）
- [x] CheXWorld 官方超参联网核实（本文件）
- [ ] 决定 blur prob：保持 I-JEPA 0.5 还是改 CheXWorld 0.2（需让 GaussianBlur 可配 prob）
- [ ] 决定 enc_mask_scale：0.85（opts 默认）vs 0.75（PRETRAIN recipe）——目前 0.85，可辩护
- [ ] clip_grad 故意不加已确认（科学设计），写入 pilot 结论免 reviewer 误读
