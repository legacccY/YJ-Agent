# 官方 SSL 预训练配方（ViT-B/16）— R4 合规真源

> 用途：CXR-SSLBench Phase1 受控重训 5 范式的官方超参冻结。所有值带官方出处；查不到的标 TODO，禁臆想（红线 R4）。
> 受控横评铁律：5 范式同 backbone(ViT-B/16) / 同语料 / 同预算重训。各范式官方 eff_batch/epoch 不同 → 强制同预算会偏离官方，属**设计选择非红线违规，但须在 LOG 显式标注**。

## 1. MAE（facebookresearch/mae）
- 官方 ImageNet ViT-B：`--model mae_vit_base_patch16`，`mask_ratio=0.75`，`epochs=800`，`warmup_epochs=40`，`blr=1.5e-4`（lr=blr×eff_bs/256，linear scaling），`weight_decay=0.05`，`--norm_pix_loss`，eff_bs=4096，AdamW(β1=0.9,β2=0.95)，cosine decay，增强=RandomResizedCrop scale[0.2,1.0]+flip（无 color jitter）。
  - 来源：https://github.com/facebookresearch/mae/blob/main/PRETRAIN.md ；β/optimizer 来自 MAE 论文 appendix A.1（arXiv 2111.06377）。
- **CXR 复现（medical_mae, CVPR'23）**：ViT-B `mask_ratio=0.90`（胸片信息密度低需更高遮挡）、`batch 256×8=2048`、`epochs=800`、`warmup 40`、`blr 1.5e-4`、`wd 0.05`、`input 224`、`random_resize_range 0.5 1.0` → NIH mAUC 83.0。**但用 CheXpert+NIH+MIMIC 合并 ~0.3–0.5M 图**。
  - 来源：https://raw.githubusercontent.com/lambert-x/medical_mae/main/PRETRAIN.md
- **112k 小语料风险：低-中**（三者最抗小数据，无对比/无 collapse）。建议 mask_ratio 用 **0.90** 而非 0.75。
- TODO：单用 NIH 112k（不合并）从头 ViT-B 的独立收敛先例未找到 → 本项目实测或人工确认。

## 2. DINO v1（facebookresearch/dino，**非 DINOv2**）
- 官方 ViT-B args.txt：`arch=vit_base`，`batch_size_per_gpu=32`(×16=512 eff)，`epochs=400`，`warmup_epochs=10`，`lr=0.00075`，`min_lr=2e-06`，`weight_decay=0.04`，`weight_decay_end=0.4`，AdamW，`out_dim=65536`。
- 防 collapse 必须项：`momentum_teacher=0.996`，`warmup_teacher_temp=0.04`，`teacher_temp=0.07`，`warmup_teacher_temp_epochs=50`（temp 缓升，升太快 collapse），`norm_last_layer=true`，`freeze_last_layer=3`，`use_fp16=false`（ViT-B 关 fp16，AMP 致 NaN/collapse）。
- crop：`global_crops_scale=[0.25,1.0]`，`local_crops_scale=[0.05,0.25]`，`local_crops_number=10`。
  - 来源：https://dl.fbaipublicfiles.com/dino/dino_vitbase16_pretrain/args.txt
- **112k 小语料风险：最高**。CXR 先例 DINO-CXR 仅 ~13k + 改 backbone（arXiv 2308.00475）。112k 单库标准 DINO ViT-B 无成功先例 → ⚠️ 必监 collapse（KL/teacher entropy），先小规模烟测。

## 3. MoCo-v3（facebookresearch/moco-v3）
- 官方 ViT-B 8-node：`arch=vit_base`，AdamW，`lr=1.5e-4`，`weight_decay=.1`，`epochs=300`，`warmup_epochs=40`，`batch_size=4096`，`--moco-t=.2`，`--stop-grad-conv1`，`--moco-m-cos`。
  - ⚠️ argparse 默认是 ResNet/LARS（`--lr 0.6 --optimizer lars --moco-t 1.0 --moco-m 0.99`，stop-grad-conv1/moco-m-cos 默认 False）→ **ViT 须显式覆盖全部**。
  - 来源：https://github.com/facebookresearch/moco-v3/blob/main/CONFIG.md ；https://raw.githubusercontent.com/facebookresearch/moco-v3/main/main_moco.py
- ViT 不稳定缓解 = **fixed random patch projection**：`stop_grad_conv1` 冻结 patch_embed.proj.weight/bias + fixed sin-cos pos_embed（vits.py）。论文：随机 patch proj 训练曲线更平滑。
- lr 敏感：论文 ViT-B/16 100ep bs4096 `lr=1.0e-4`→72.2%，`1.5e-4` 更不稳更低；大 batch(4k+) 有 "dips"，小 batch 更平滑（arXiv 2104.02057）。
- **112k 小语料风险：中-高**。MoCo-CXR 用 ResNet 非 ViT（arXiv 2010.05352）。建议必开 `--stop-grad-conv1`，lr 取 **1.0e-4** 而非 1.5e-4，batch 别盲目放大。
- TODO：112k 级 CXR ViT-B MoCo-v3 具体复现配方无官方/高星直接来源 → 标 TODO。

## 4. CheXWorld（world-model）
- 权重+repo+官方 recipe(FINETUNE.md) 已在 `project/meeting/复现/CheXWorld/repo/` + HPC `/gpfs/.../chexworld/`。Phase0 pilot 已用。

## 5. 监督参考 / scratch floor
- imagenet_sup ViT-B/16 timm（pilot 已用）；scratch floor = 随机初始化 finetune。

## ✅ 受控横评路线 = A′ 混合受控（2026-06-30 拍板，skeptic 强推）
官方 eff_batch（MAE/MoCo 4096 vs DINO 512）、epoch（MAE/DINO 400-800 vs MoCo 300）、语料（先例都 ImageNet 1.28M 或合并 0.3-0.5M，**非单 NIH 112k**）三者不一致。

**采纳 A′ 混合受控**（控 claim 相关轴、放开方法构成要素轴）：
- **同**：预训练数据 NIH 112k + backbone ViT-B/16 + 计算预算（按 **GPU·h 或 images-seen** 预登记对齐，**不按 epoch**——batch 差异会偷换 images-seen）。
- **各自官方冻结**：batch / lr / temp / mask_ratio / 稳定性开关（DINO temp warmup 0.04→0.07@50ep + fp16=off；MoCo stop-grad-conv1 + lr 1e-4；MAE mask 0.90）。
- 预登记「batch 因方法而异是构成要素非疏漏」+ 每范式 images-seen 表。这是 solo-learn/VISSL/「A Closer Look at SSL ViT」公认横评协议。

**否决**：
- ❌ **纯 A 强制同 batch/epoch**：对 DINO/MoCo batch 是方法构成要素（负样本数/对比信号），强行同 batch = 比「被调坏的 DINO vs 调坏的 MoCo」，C1 被审稿人判调参不公伪发现（skeptic 🔴 陷阱）。
- ❌ **B 作 headline**：非受控，「最受控」差异化反噬，C1 被「谁拿更多 epoch/更大 batch」污染。可附录补 B 式官方配方点做 robustness 对照。
- ⏸ **C 扩语料**：仅作 A′ 下 collapse 压不住时后备（HPC 传新数据=拍板点 + 稀释 C2 NIH 干净数据效率曲线卖点）。

**投全预算前必做**：DINO/MoCo 各 1 个小规模 collapse 烟测（监 KL/teacher entropy）确认能起。
