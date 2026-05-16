# 阶段七：VisiEnhance-Net（诊断保持型质量增强）

## 目标

在现有五阶段系统（VisiScore → Q-VIB → Agent）之上，新增**诊断保持型质量增强模块**，将系统从"低质量只能追问重拍"升级为**双通道决策**：

- **可修复退化**（光照/色温/对比度/轻度模糊）→ VisiEnhance-Net 自动增强 → Q-VIB 诊断
- **不可修复退化**（病灶裁切/极重度模糊）→ Agent 追问重拍

本阶段新增两个定理（Proposition 3 + Lemma 3），与前四个定理共同构成完整的理论闭环，支撑 ICLR 投稿。

**详细技术设计参见**：`V2.0plan.md`（含架构图、伪代码、参考文献 17 篇）

---

## 前置条件

| 依赖项 | 路径 | 验证方式 |
|--------|------|---------|
| VisiScore-Net 权重 | `checkpoints/best_visiscore.pth` | `python eval_visiscore.py` 输出 PLCC > 0.92 |
| Q-VIB Full 权重 | `checkpoints/efnet/best_qad.pth` | `python eval_ablation.py` 输出 F AUC > 0.70 |
| 149K 配对训练数据 | `data/paired_dataset/{light,medium,heavy}/` | 目录存在，文件数 > 99000 |
| ISIC 分割文件 | `data/isic_split.csv` | 含 train/val/test 三列 |
| ITB 结果基线 | `results/itb_results.csv` | 确认 9 条 baseline 全部已跑 |

---

## 核心理论新增

### Proposition 3：增强降低诊断不确定度

若增强满足质量改善条件 $\bar{q}(T_\omega(x, q)) > \bar{q}(x)$，则 Q-VIB 的预测熵不增：

$$\mathbb{E}\big[H(\hat{p}_{T_\omega(x, q)})\big] \leq \mathbb{E}\big[H(\hat{p}_x)\big]$$

**证明路径**：由 Lemma 1（$\sigma^2(\bar{q})$ 单调递减）→ KL 约束增强 → 隐变量 $\mu$ 偏离零向量 → 后验预测熵下降。完整证明放入论文附录。

### Lemma 3：DP-Loss 保持诊断互信息

最小化 $\mathcal{L}_{\text{DP}} = D_{\mathrm{KL}}(p_\phi^{\text{enh}} \| p_\phi^{\text{ref}})$ 蕴含：

$$\mathcal{L}_{\text{DP}} \leq \epsilon \implies I(Z_{\text{enh}}; Y) \geq I(Z_{\text{ref}}; Y) - \beta\epsilon$$

**意义**：DP-Loss 不是工程技巧，而是信息论意义上"增强不损害诊断"的充分条件。

---

## 架构设计

### 主架构：NAFNet + FiLM 质量条件调制

```
x_low [B,3,H,W] ────────────────────────────────┐
                                                  │
q [B,5] ──► Q-MLP (5→128→C) ──► γ, β           │
                                    │              │
                          ┌─────────▼──────────────▼──────┐
                          │  U-Net (NAFBlock × 12)         │
                          │  每个 NAFBlock 后 apply FiLM   │
                          │  Encoder→Bottleneck→Decoder    │
                          └──────────────┬─────────────────┘
                                         │
                                    x_enh [B,3,H,W]
```

**FiLM 调制**：$F' = (1 + \gamma_{\text{scale}} \cdot \gamma) \odot F + \gamma_{\text{scale}} \cdot \beta$，初始 scale=0.1，保证训练初期近似恒等映射。

**质量缺陷向量**：传入 MLP 前先做 $\tilde{q} = 1 - q$，使完美质量图（q→1）时 FiLM 调制趋近于零。

### 参数规模

| 组件 | 参数量 | 显存（FP16）|
|------|--------|-----------|
| NAFNet-64 骨干 | ~67 M | ~1.0 GB |
| FiLM MLP（每层独立） | ~0.5 M | 忽略 |
| 训练时总显存（batch=16） | — | ~6.7 GB（4070 8GB 可行）|
| 推理显存（连同 VisiScore + Q-VIB）| — | ~2.8 GB |

---

## 训练策略

### Stage 1：基础复原预训练

| 项目 | 配置 |
|------|------|
| 目标 | 学会从降质图恢复高质量参考图 |
| 数据 | 现有 149K 配对数据（light/medium/heavy 三级降质）|
| 损失 | $\mathcal{L} = \mathcal{L}_1 + 0.1 \cdot \mathcal{L}_{\text{LPIPS}}$ |
| 优化器 | AdamW, lr=1e-4, cosine annealing |
| Batch | 16, 384×384, FP16 AMP |
| Epochs | 200，早停（val PSNR 5 epoch 不升） |
| 预期结果 | PSNR > 32 dB，SSIM > 0.92，LPIPS < 0.08 |
| 时间估算 | ~72 h（RTX 4070）|

### Stage 2：DP-Loss 诊断保持微调

| 项目 | 配置 |
|------|------|
| 目标 | 增强后隐变量分布贴近参考图，确保诊断不变 |
| 冻结模块 | VisiScore-Net + Q-VIB encoder（只提供梯度，不更新权重）|
| 损失 | Stage 1 损失 + $0.05 \cdot D_{\mathrm{KL}}(p_\phi^{\text{enh}} \| p_\phi^{\text{ref}})$ |
| 优化器 | AdamW, lr=1e-5，batch=8 |
| Epochs | 80 |
| 监控 | DP-Loss 下降趋势；Q-VIB 对增强图 vs 参考图预测一致性 > 95% |
| 时间估算 | ~36 h |

### Stage 3：质量达标约束

| 项目 | 配置 |
|------|------|
| 目标 | 确保增强后 $\bar{q}$ 确实超过阈值 0.55 |
| 数据筛选 | 仅 $\bar{q} < 0.55$ 的样本（真正低质量输入）|
| 新增损失 | $+ 0.1 \cdot \max(0,\ 0.55 - \bar{q}_{\text{enh}})$（hinge loss，VisiScore-Net 冻结）|
| 优化器 | AdamW, lr=5e-6 |
| Epochs | 40 |
| 时间估算 | ~24 h |

---

## 实验矩阵

优先级：E3（诊断保持）和 E5（双通道效率）是论文核心实验；其余为支撑实验。

| 编号 | 实验名称 | 核心指标 | 通过标准 | 优先级 |
|------|---------|---------|---------|-------|
| **E3** | **诊断保持** | $\|\Delta\text{AUC}\|$（增强图 vs 参考图） | **< 1.5%**（核心指标） | 🔴 必须 |
| **E5** | **双通道效率** | 中等降质图增强挽救率 | **> 55%** | 🔴 必须 |
| E1 | 增强质量评估 | PSNR↑ / SSIM↑ / LPIPS↓ | PSNR ≥ 30 dB | 🟠 重要 |
| E2 | 分退化类型分析 | 按退化类型分解 PSNR | 光照/色温/对比 > 35 dB；模糊 > 28 dB | 🟠 重要 |
| E4 | Proposition 3 验证 | 增强前后 entropy–q̄ Spearman ρ 变化 | 增强后 \|ρ\| 增大（单调性增强）| 🟠 重要 |
| E6 | 增强安全边界 | 极低质量段（q̄<0.25）挽救率 | < 25%（验证拒绝决策正确性）| 🟡 支撑 |
| E7 | 消融：DP-Loss | 有/无 DP-Loss 的 E1+E3 对比 | DP-Loss 组 ΔAUC 更小 | 🟡 支撑 |
| E8 | 消融：Q 条件 | 有/无 FiLM 的 E1+E2 对比 | FiLM 组 PSNR 更高 | 🟡 支撑 |
| E9 | 消融：FiLM vs Cross-Attn | 速度 + PSNR 对比 | FiLM 速度 3-5× 快，性能持平 | 🟡 支撑 |
| E10 | 对比 SOTA | vs Real-ESRGAN / DiffBIR / Restormer / NAFNet-base | 诊断保持指标（ΔAUC, ΔECE）我们最优 | 🟠 重要 |
| E11 | 跨数据集泛化 | HAM10000 + PAD-UFES 上 AUC 保持率 | > 95% | 🟡 支撑 |
| E12 | 推理速度 | 单张端到端延迟 | < 50 ms | 🟡 支撑 |

### E3 详细设计（诊断保持 —— 最关键实验）

1. 从 ISIC 2020 测试集取 2000 张高质量图（$\bar{q} > 0.7$）
2. 对每张图生成 moderate 级别降质版本
3. 用 VisiEnhance-Net 增强降质图，得到 Group A（参考）/ B（降质）/ C（增强）
4. 用 Q-VIB 分别推理三组，计算：

| 对比 | 指标 | 通过标准 |
|------|------|---------|
| C vs A | 分类一致率 | > 95% |
| C vs A | \|ΔAUC\| | < 1.5% |
| C vs A | \|ΔECE\| | < 2% |
| C vs B | 不确定度 H(p) | C < B（增强降低不确定度）|

5. McNemar 检验：C vs A 的诊断一致性是否显著优于 B vs A

---

## 系统集成：双通道决策逻辑

```
输入图像
    │
    ▼ VisiScore-Net
    q = (q₁,...,q₅),  q̄ = mean(q)
    │
    ├─ q̄ ≥ 0.60 ──► 通道 A1：高质量直接诊断
    │
    ├─ 0.50 ≤ q̄ < 0.60 ──► 通道 A2：直接诊断 + 轻度警示
    │
    ├─ 0.35 ≤ q̄ < 0.50 ──► 通道 B：VisiEnhance-Net 增强
    │                           │
    │                           ├─ 增强后 q̄_enh ≥ 0.50 ──► Q-VIB 诊断
    │                           └─ 增强后 q̄_enh < 0.50 ──► Agent 追问
    │
    └─ q̄ < 0.35 ──► 通道 C：直接 Agent 追问（增强无意义）
```

**退化可修复性判据**（写死为决策逻辑第一层）：若 $q_3$（完整度）< 0.4（病灶严重裁切），强制走 C 通道，不经过增强模块。

---

## 新增依赖

```
# requirements.txt 追加
lpips>=0.1.4       # DP-Loss LPIPS 感知损失
nafnet>=0.1.0      # NAFNet 骨干（或直接 vendor 进 project/models/）
```

---

## 交付物清单

| 文件 | 说明 |
|------|------|
| `project/models/visienhance.py` | NAFNet + FiLM 模型定义 |
| `project/train_visienhance.py` | 三阶段训练脚本，支持 `--stage 1/2/3`，支持 `--resume` |
| `project/configs/visienhance_s1.yaml` | Stage 1 超参配置 |
| `project/configs/visienhance_s2.yaml` | Stage 2 超参配置（含 λ_DP）|
| `project/configs/visienhance_s3.yaml` | Stage 3 超参配置（含 λ_quality）|
| `project/eval_visienhance.py` | E1-E12 全部实验脚本 |
| `project/models/dual_channel.py` | 双通道决策逻辑封装 |
| `checkpoints/best_visienhance.pth` | Stage 3 最佳权重 |
| `results/visienhance_e3.csv` | E3 诊断保持实验结果 |
| `results/figures/fig13_enhance_quality.png` | E1 PSNR/SSIM 对比图 |
| `results/figures/fig14_diag_preserve.png` | E3 诊断保持图（核心图）|
| `results/figures/fig15_dual_channel.png` | E5 双通道效率图 |
| `results/figures/fig16_prop3_verify.png` | E4 Proposition 3 验证图 |
| `tests/test_visienhance.py` | 单元测试 + 冒烟测试 |

---

## 验收标准

| 指标 | 标准 | 验证脚本 |
|------|------|---------|
| 基础复原（E1）| PSNR ≥ 30 dB（moderate 降质集）| `eval_visienhance.py --exp E1` |
| **诊断保持（E3）** | **\|ΔAUC\| < 1.5%（增强图 vs 参考图）** | `eval_visienhance.py --exp E3` |
| **双通道效率（E5）** | **SalvageRate ≥ 55%（moderate 降质段）** | `eval_visienhance.py --exp E5` |
| Proposition 3 验证（E4）| 增强后 entropy–q̄ \|ρ\| 显著大于增强前 | `eval_visienhance.py --exp E4` |
| 推理速度（E12）| < 50 ms / 张（含 VisiScore-Net + 增强）| `eval_visienhance.py --exp E12` |
| 测试套件 | `pytest tests/test_visienhance.py` 全绿 | — |
| 安全边界（E6）| 极低质量（q̄<0.25）挽救率 < 25% | `eval_visienhance.py --exp E6` |

---

## 风险分析

| 编号 | 风险 | 概率 | 影响 | 缓解措施 | 回退方案 |
|------|------|------|------|---------|---------|
| R1 | **诊断保持失败**（\|ΔAUC\| > 3%）| 中 | 致命 | 增大 λ_DP；限制增强范围到安全区间 | 降级为 QIFL（特征层对比学习，不改像素）|
| R2 | 多退化混合修复 PSNR 显著低于预期（< 28 dB）| 中 | 中等 | 缩小到 mild-moderate；分任务路由 | 按退化类型分别训练专家模型 |
| R3 | DP-Loss 训练不稳定 | 低 | 中等 | 降低 λ_DP；渐进式引入（Stage 2 初期 λ_DP=0.01，每 10 epoch 增加 0.01）| 用 L1 隐空间欧氏距离替代 KL 散度 |
| R4 | 显存超过 8 GB | 低 | 中等 | 降低 batch（16→8）或图像尺寸（384→256）| 梯度检查点（`torch.utils.checkpoint`）|
| R5 | ICLR 8 页放不下 5 个模块 | 高 | 中等 | 正文聚焦 Proposition 3 + E3/E5；VisiEnhance 细节移附录 | 见 phase_08_paper.md 篇幅策略 |

---

## 注意事项

- **绝不用扩散生成模型**（SD-Turbo / DiffBIR 等）做皮肤镜增强——生成式模型可能凭空"发明"色素网络或血管结构，在临床上是不可接受的伪影风险
- 增强后必须过一遍 VisiScore-Net 重新评估 q̄，不能直接用预期值
- E3 实验的 2000 张图必须来自 test split（`isic_split.csv` 的 `split == 'test'`），严禁用训练数据
- Stage 2/3 训练中 VisiScore-Net 和 Q-VIB encoder 权重必须完全冻结（`requires_grad_(False)`）
