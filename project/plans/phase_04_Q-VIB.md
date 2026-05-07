# 阶段四：质量感知诊断模块（QAD）—— 基于 Q-VIB

## 目标

基于 Q-VIB（Quality-Conditioned Variational Information Bottleneck）框架，实现从图像到诊断的完整概率推理链路。核心创新有三层：

1. **质量自适应先验**：编码器的 KL 约束强度由 VisiScore-Net 输出的质量向量 $\mathbf{q} \in [0,1]^5$ 动态调控——低质量图的先验方差大，强制潜在编码趋向无信息先验，自然产生高熵（低置信度）预测
2. **质量分词器（Quality Tokenizer）**：将 $\mathbf{q}$ 通过可学习嵌入 $u(\mathbf{q}), v(\mathbf{q})$ 注入 Transformer 自注意力层，理论保证注意力漂移有界（Theorem 1）
3. **软校准**：预测置信度随质量连续变化，替代硬门控截断，全程可微

整体架构：**分割 → ABCD 特征 → Q-VIB 编码器（接收 $\mathbf{q}$）→ 分类器 → 诊断 + 校准置信度**

---

## 前置条件

- 阶段三完成：`best_visiscore.pth` 已就绪，VisiScore-Net 可输出 $\mathbf{q} \in [0,1]^5$
- 阶段二的数据集可用（含配对的原始/退化图像和 `quality_labels.csv`）

---

## 本阶段工具

| 工具 | 用途 |
|------|------|
| mobile-sam / sam2 | 分割模型预训练权重，仅推理 |
| opencv-python | ABCD 特征几何计算（对称性、轮廓、颜色分布） |
| PyTorch | Q-VIB 编码器 / 质量分词器 / 质量自适应先验 / 分类器全部用 torch 实现 |
| wandb | 记录 ELBO 曲线、KL 项随 $\bar{q}$ 变化、分类指标、对比实验 |

> 注：Q-VIB 不需要额外概率编程库——编码器（对角高斯）、先验（等方高斯）、KL 散度均有解析闭式，纯 PyTorch 即可。

---

## 关键技术决策点

1. **分割模型选择**（同原计划）：
   - MobileSAM（最快，~10ms/图，精度稍低）
   - EfficientSAM（精度更高，速度适中）
   - SAM2-tiny（最新，精度最好，速度最慢）
   - 决策标准：端到端推理 <500ms

2. **是否启用质量分词器（Attention Modulation）**：
   - **是（推荐）**：将 $\mathbf{q}$ 通过 $u, v$ 嵌入注入自注意力，提供更强的质量-特征交互。实现成本低（两层 MLP），推理开销极小
   - 否：仅通过先验方差调控，实现更简单但丢失了注意力层的质量感知能力
   - 论文中可对比两者（Ablation Study 的一环）

3. **$\beta$ 超参选择策略**：
   - $\beta \in [10^{-4}, 10^{-1}]$，控制信息瓶颈的总体强度
   - 策略：在验证集上扫描，选取使低质量段 ECE 最低的 $\beta$
   - 注意 $\beta$ 过大会导致高质量图也被过度压缩，$\beta$ 过小则质量调节失效

4. **先验参数 $\sigma_0^2, \tau, \alpha$ 调优方案**：
   - $\sigma_0^2$：完美质量图的先验方差。初值 0.1，范围 $(0.01, 0.5]$
   - $\tau$：质量阈值，$\bar{q} < \tau$ 时瓶颈开始显著收紧。初值 0.5
   - $\alpha$：过渡锐度。初值 5.0，范围 $[1, 20]$
   - 可学习（通过重参数化梯度回传）或固定（减少调参负担，推荐固定）

5. **是否集成 ABCD 规则特征**（同原计划）：
   - **是（推荐）**：分割掩码 → 对称性 / 边缘不规则度 / 颜色多样性 / 相对尺寸，作为 Q-VIB 编码器的结构化输入，可解释性强
   - 否：直接用 CNN 端到端，实现简单但可解释性弱

---

## 交付物清单

| 文件 | 用途 |
|------|------|
| `models/segmenter.py` | 选定分割模型的推理封装，统一接口 |
| `models/feature_extractor.py` | ABCD 特征提取（对称性/边缘/颜色/直径） |
| `models/q_vib_encoder.py` | **Q-VIB 编码器** $p_\phi(z\|x, \mathbf{q})$：接收 CNN 特征（或 ABCD 特征）+ 质量向量，输出对角高斯参数 $(\mu, \log\sigma^2)$ |
| `models/quality_tokenizer.py` | **质量分词器**：$u, v: [0,1]^5 \to \mathbb{R}^m$，两层 MLP + LayerNorm，满足边界条件 $u(\mathbf{1}) = v(\mathbf{1}) = 0$ |
| `models/quality_adaptive_prior.py` | **质量自适应先验** $r_\psi(z\|\mathbf{q}) = \mathcal{N}(0, \sigma^2(\bar{q}) I_d)$，sigmoid 调度（Eq. 8），含 KL 解析计算（Eq. 9） |
| `models/q_vib_loss.py` | **Q-VIB ELBO 损失**：交叉熵项（单样本 MC）+ $\beta \cdot D_{\text{KL}}(p_\phi \| r_\psi)$，含重参数化采样 |
| `models/qad_classifier.py` | 分类器 $q_\theta(y\|z)$：潜在编码 → $K$ 类 logits |
| `train_qad.py` | Q-VIB 训练脚本，支持 `--resume`、FP16、wandb |
| `eval_qad.py` | 评估脚本：含 Q-VIB 组件消融实验（固定先验 vs 自适应先验、无/有质量分词器） |

---

## 工作步骤

### Step 1：集成分割模型（同原计划）
封装选定模型，统一输入输出接口，测试推理速度。输出为二值掩码 $\mathbf{M} \in \{0,1\}^{H \times W}$。

### Step 2：ABCD 特征提取（同原计划）
基于分割掩码计算 4 个可解释特征，验证特征计算正确性。输出特征向量 $\mathbf{f}_{\text{ABCD}} \in \mathbb{R}^4$（或更多）。

### Step 3：实现质量自适应先验 `quality_adaptive_prior.py`
- 实现 Eq. (7–8)：$\sigma^2(\bar{q}) = \sigma_0^2 + (1-\sigma_0^2) \cdot \operatorname{sigmoid}(-\alpha(\bar{q} - \tau))$
- 实现 KL 解析式 Eq. (9)：$D_{\text{KL}} = \frac{1}{2}\sum_{j=1}^d \left[\frac{\mu_j^2 + \sigma_j^2}{\sigma^2(\bar{q})} - 1 - \log\frac{\sigma_j^2}{\sigma^2(\bar{q})}\right]$
- 单元测试：验证 $\sigma^2(\bar{q})$ 单调递减（Lemma 1），边界值 $\sigma^2(0) \approx 1$, $\sigma^2(1) \approx \sigma_0^2$

### Step 4：实现质量分词器 `quality_tokenizer.py`
- $u(\mathbf{q}) = \tilde{u}(\mathbf{1} - \mathbf{q})$, $v(\mathbf{q}) = \tilde{v}(\mathbf{1} - \mathbf{q})$，其中 $\tilde{u}, \tilde{v}$ 为两层 MLP（含 LayerNorm）
- 确保 $\tilde{u}(0) = \tilde{v}(0) = 0$（可将最后一层 bias 初始化为 0，或显式减均值）
- 注意力偏置计算：$\delta_{ij} = u(\mathbf{q})^\top v(\mathbf{q})$，注入 self-attention logits（Eq. 10）
- 单元测试：验证 $\mathbf{q} = \mathbf{1}$ 时 $\delta = 0$；验证 Lipschitz 常数有界（可选：spectral norm）

### Step 5：实现 Q-VIB 编码器 + 损失 `q_vib_encoder.py` + `q_vib_loss.py`
- 编码器 $p_\phi(z|x, \mathbf{q})$：特征提取（CNN Backbone 或 MLP 接收 ABCD 特征）→ 与 $\mathbf{q}$ 拼接 → 输出 $(\mu, \log\sigma^2)$
- 如果启用质量分词器：将 $\delta$ 注入 Backbone 的 self-attention 层
- 损失函数 Eq. (6)：$\mathcal{L} = -\log q_\theta(y|z) + \beta \cdot D_{\text{KL}}(p_\phi \| r_\psi)$，$z$ 通过重参数化采样
- 单元测试：验证前向传播不报错，$z$ 形状正确，损失值为正有限标量

### Step 6：训练 Q-VIB
- FP16 混合精度，Batch 128，约 30 epoch
- wandb 记录：ELBO、交叉熵项、KL 项（按 $\bar{q}$ 分段统计）、分类准确率（按 $\bar{q}$ 分段）
- 全程支持 `--resume` 断点续训

### Step 7：对比实验 + 消融
在同一测试集上运行以下对比：
- **Baseline 1**：标准 VIB（固定先验 $\mathcal{N}(0, I_d)$，无质量条件化）
- **Baseline 2**：Q-VIB 无质量分词器（仅先验自适应）
- **Baseline 3**：Q-VIB 完整版（先验自适应 + 注意力调制）
- **Baseline 4（可选）**：硬门控（$\bar{q} < \tau$ 直接拒绝，不输出诊断）

评估指标：各质量分段的准确率、ECE（Expected Calibration Error）、预测熵分布。

---

## 验收标准

- 分割模型推理单张 <200ms（RTX 4070）
- ABCD 特征提取结果可视化符合人类直觉
- **Q-VIB 核心指标（论文关键数据）**：
  - KL 项随 $\bar{q}$ 单调递减（低质量图 KL 项大→编码被压缩，可视化验证）
  - 低质量段（$\bar{q} < 0.4$）预测熵显著高于高质量段（$\bar{q} > 0.8$），验证 Proposition 2
  - 质量自适应先验版本在低质量段 ECE 显著优于固定先验版本
- 端到端推理链路（VisiScore + 分割 + Q-VIB 编码 + 分类）<1s/张

---

## 硬件/资源约束

- 分割模型 + Q-VIB 编码器（轻量 Backbone）+ 分类器同时加载，总显存 ≤ 7GB
- 质量分词器 $u, v$ 为两层 MLP（$5 \to 128 \to 64$），参数量 <10k，显存/计算开销可忽略
- 注意力偏置 $\delta_{ij}$ 对所有 token pair 相同（标量），实际计算为 $u^\top v$ 然后在 logits 上加 broadcast，O(1) 额外开销

---

## 注意事项

- **重参数化采样的数值稳定性**：$\log\sigma^2$ 参数化避免 $\sigma$ 为负；采样时 $\sigma = \exp(0.5 \cdot \log\sigma^2)$
- **KL 项的 $\beta$ 调度**：训练初期 $\beta$ 不宜过大（避免 posterior collapse），可从 0 线性 warmup 到目标值（参考 KL annealing, Bowman et al. 2016）
- **质量分词器的 Lipschitz 约束**：Theorem 1 的 bound 依赖于 $\tilde{u}, \tilde{v}$ 的 Lipschitz 常数。实践中可通过 spectral normalization 约束，但不是必须（不约束也不会发散，只是 bound 更松）
- **ABCD 特征与 CNN 特征的融合方式**：可以（a）ABCD 特征作为编码器的唯一输入（纯可解释路径），或（b）CNN 提取视觉特征后与 ABCD 特征拼接。方案 (a) 更轻量且可解释性强，推荐先试
- **边界条件 $\tilde{u}(0) = \tilde{v}(0) = 0$**：如果最后一层有 bias 会导致 $\mathbf{q}=\mathbf{1}$ 时残差非零，两种修复方式：（1）最后一层不加 bias；（2）显式 $\tilde{u}(x) - \tilde{u}(0)$。推荐 (1)
- 确保 `eval_qad.py` 输出的表格直接对齐论文格式，含 ECE / 分段准确率 / 平均熵三组指标
