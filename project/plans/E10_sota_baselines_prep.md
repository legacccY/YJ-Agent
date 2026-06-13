# E10 — 6 个 SOTA 增强/复原基线对比 准备

**状态：仅调研规划，未下载权重，未跑任何 inference。**
**红线：禁止扩散模型（临床伪影红线）—— 以下 6 个均为非扩散方法。**

---

## 1. 选定的 6 个基线

| # | 方法 | 类型 | venue | 非扩散依据 | 官方 repo |
|---|------|------|-------|-----------|-----------|
| 1 | **Restormer** | Transformer (MDTA+GDFN) 复原 | CVPR 2022 Oral | 纯 transformer encoder-decoder, 单次前向回归, 无迭代去噪 | https://github.com/swz30/Restormer |
| 2 | **NAFNet** | CNN (NAFBlock, 无非线性激活) | ECCV 2022 | 纯卷积 U-Net, 单次前向, 我们自己 backbone 同源(可控变量) | https://github.com/megvii-research/NAFNet |
| 3 | **MIRNet (-v2)** | CNN 多尺度并行分支 | ECCV 2020 / TPAMI 2022 | 多分辨率并行 CNN, 单次前向回归 | https://github.com/swz30/MIRNet (v2: swz30/MIRNetv2) |
| 4 | **SwinIR** | Swin Transformer 复原 | ICCVW 2021 | 窗口注意力 transformer, 单次前向 | https://github.com/JingyunLiang/SwinIR |
| 5 | **Uformer** | U-shaped Transformer (LeWin block) | CVPR 2022 | 局部窗口注意力 U-Net, 单次前向 | https://github.com/ZhendongWang6/Uformer |
| 6 | **Real-ESRGAN** | GAN (ESRGAN+, RRDB + U-Net判别器) | ICCVW 2021 | GAN 范式(对抗训练但推理时单次前向生成器), 非扩散 | https://github.com/xinntao/Real-ESRGAN |

### 为什么是这 6 个（覆盖面考量）
- **架构多样性**：CNN (NAFNet, MIRNet) / Transformer (Restormer, SwinIR, Uformer) / GAN (Real-ESRGAN) 三大范式各有代表，论文里能写"我们在三类 SOTA 范式上都对比过"。
- **任务相关性**：均有 denoising/deblur/低光增强/超分辨率 的预训练权重，皮肤镜低质量图像（模糊/噪声/低对比）落在这些方法的训练分布内，可直接 inference 或少量 fine-tune。
- **NAFNet 特别说明**：和我们的 backbone 同源（VisiEnhanceNet 用 NAFBlock），作为基线对比"NAFNet 原版（无 quality-conditioning, 无 DP-loss）vs VisiEnhance（FiLM + DP-loss）"，能直接说明我们的 conditioning + diagnosis-preserving loss 的增量价值——这是消融叙事里最干净的一条线。
- **Real-ESRGAN 是唯一非 transformer/CNN-regression 的代表**（GAN），覆盖"对抗训练范式"，且明确非扩散，规避红线同时保证基线谱系完整。

### 备选（未选，记录原因）
- **HINet** (CVPR21 Workshop)：架构上与 MIRNet 重叠度高，优先级低于 Uformer。
- **MAXIM** (CVPR22)：MLP-based, JAX 官方实现迁移成本高，PyTorch 第三方权重质量不稳定。
- **DRBN / KinD (低光增强专用)**：任务针对性强但泛化到皮肤镜的证据少，且代码维护状态较差。
- 扩散类 (Diff-IR, Refusion, WeatherDiffusion 等)：**红线排除**。

---

## 2. 各方法跑法（在我们的 paired_dataset 上）

统一流程：**优先用官方预训练权重直接 inference（zero-shot baseline）**；
若 zero-shot 在我们的低质量分布上效果差（PSNR 远低于预期），
**再考虑用我们的 paired_dataset (low-quality / high-quality pairs)
做轻量 fine-tune**（冻结大部分层，只 fine-tune 输出头 + 少量 epoch，
避免和我们自己模型的训练算力差距过大导致不公平对比）。

| 方法 | 预训练权重来源 | 输入分辨率适配 | inference / fine-tune 策略 |
|------|---------------|---------------|---------------------------|
| Restormer | 官方 `Denoising`/`Deblurring` 任务权重 (Google Drive, repo README 链接) | 任意 (全卷积+transformer, patch-based 可变尺寸), 我们用 256×256 | zero-shot inference 优先; 若差则 fine-tune 最后 1-2 个 decoder block, ~10 epoch |
| NAFNet | 官方 `NAFNet-SIDD-width64`(去噪) 或 `NAFNet-GoPro-width64`(去模糊) ckpt | 256×256 直接支持 | zero-shot + fine-tune 全网络(与我们 VisiEnhance 同 epoch 数做严格公平对比的话) |
| MIRNet(v2) | 官方 enhancement (LOL/FiveK 低光增强) 权重 | 需 resize 到 256 或用其 multi-scale 自适应 | zero-shot inference 优先(低光增强权重和"去模糊/去噪伪影"的皮肤镜场景有 domain gap, 预期需 fine-tune) |
| SwinIR | 官方 `real_sr`/`color_dn` 任务权重 | window_size=8 倍数, 256 整除 OK | zero-shot inference; SR 模型需先 downsample 再 SR 回 256 或直接用 denoising 权重 |
| Uformer | 官方 SIDD 去噪 / GoPro 去模糊权重 | 256×256(其 patch size 可调) | zero-shot inference 优先 |
| Real-ESRGAN | 官方 `RealESRGAN_x2plus` 或 `x4plus` (取 x1 等价配置或 SR 后 downsample 回 256) | SR 模型需配合 resize pipeline | zero-shot inference (SR→downsample 回原尺寸做"增强") |

### 统一 inference 脚本设计（规划，未写代码）
- 新建 `project/baselines/` 目录（未建），每个方法一个 wrapper
  `run_<method>_inference.py`，输入 = `paired_dataset` 的 low-quality
  256×256 图像，输出 = enhanced 256×256 图像，存到
  `outputs/baselines/<method>/`。
- 复用我们现有的 `eval_diag_paired.py` 协议：把每个方法的输出图像
  当作"enhanced image"喂给 VisiScore/B3，跑同一套 PSNR/SSIM/dAUC 流程。

---

## 3. 评估指标（对齐 E1/E3）

与现有 v5/v6 评估表同口径，对每个基线方法跑：

1. **图像质量**：PSNR, SSIM (vs paired ground-truth high-quality 图)
   —— 对齐 E1 (`run_e1_hpc_v6.py` / `run_e1_ablation_hpc.py` 的指标定义)
2. **诊断保持 (dAUC)**：用冻结 B3 分类器算 enhanced 图像的诊断 AUC
   变化 (`Δ AUC` vs 原图 vs 我们 VisiEnhance) —— 对齐 E3/E5 的
   `eval_diag_paired.py` 协议(dAUC, 一致率, dangerous_flip, KL)
3. **Quality score 提升**：VisiScore q̄ 提升幅度 —— 对齐 Q-VIB 主线指标
4. **统计检验**：paired t-test (PSNR/dAUC), 同我们现有 E1 红线
   (PSNR>=30) 的判定方式

**核心叙事**：6 个 SOTA 基线大概率能在 PSNR/SSIM 上有竞争力（甚至更高，
因为它们是纯图像质量优化），但**不具备 diagnosis-preserving 约束**，
预期在 dAUC/dangerous_flip 上明显劣于 VisiEnhance —— 这正是我们
quality-conditioning + DP-loss 的核心卖点（"通用增强会破坏诊断语义，
我们的方法不会"）。

---

## 4. 预估算力

| 阶段 | 每方法预估 | 6 方法合计 |
|------|-----------|-----------|
| 权重下载 | ~0.5-2 GB/方法, 共 ~10GB | 一次性 |
| Zero-shot inference (val/test set, ~数百张 256×256) | 单 GPU 4090, <30 min/方法 | ~3 小时 |
| (可选) Fine-tune (若 zero-shot domain gap 大, ~10-20 epoch) | 单 GPU 4090, 2-4 小时/方法 | 最多 ~24 小时(若全部都需要) |
| 评估 (eval_diag_paired 协议) | ~15 min/方法(含 B3+VisiScore 推理) | ~1.5 小时 |

**总预估**：zero-shot only 路线 ≈ 半天算力；若多数方法需要 fine-tune
则 ≈ 1-2 天算力（4090 单卡）。建议先全部 zero-shot 跑一遍出表，
再针对"明显 domain gap 大"的方法（预期 MIRNet/Real-ESRGAN 的低光/SR
权重最可能需要）决定是否 fine-tune。

---

## 5. TODO 清单

1. [ ] 下载 6 个方法的官方预训练权重（repo README 链接见 §1 表格）
2. [ ] 建 `project/baselines/run_<method>_inference.py`（6 个 wrapper）
3. [ ] 在 paired_dataset val/test 上跑 zero-shot inference，存 enhanced 图
4. [ ] 跑 `eval_diag_paired.py` 协议算 PSNR/SSIM/dAUC/一致率/dangerous_flip/KL
5. [ ] 出对比表：VisiEnhance(v5/v6) vs 6 baselines，按 §3 指标
6. [ ] 若 zero-shot domain gap 明显，对该方法做 fine-tune 后重新评估
7. [ ] 写入 paper §7（消融/对比实验）

**当前完成度：2/7 代码侧铺完（会话 28，2026-06-14）**：
- [x] TODO2 6 wrapper 落地 — `baselines/run_<m>_inference.py` + `baselines/archs/<m>_arch.py` 官方 arch 逐字 vendor（6 sonnet agent 并行），本地 import+构造+forward 256→256 全过，param 量对齐官方。
- [x] eval entrypoint `run_e10_baseline_hpc.py` — VisiEnhance v5 vs baseline 严格 paired，per-image PSNR/SSIM（会话 27 口径锁）+ dAUC/dflip/KL + paired bootstrap（baseline−VE）。
- [x] 下载清单 `baselines/WEIGHTS.md`（URL + 构造参数 + ckpt key）。
- 余 TODO1/3/4/5 = HPC 侧（权重下载 + 上传 + GPU job），主线串行 + 待用户拍 GPU。zero-shot 路线（无 fine-tune）。

**原始完成度：0/7（仅调研选型，未下载未跑）。**
