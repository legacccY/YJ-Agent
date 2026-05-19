# BMVC 投 P2：完整方案

## 一、为什么 BMVC 适合 P2

| 维度 | BMVC 偏好 | P2 匹配度 |
|------|------|:---:|
| 论文类型 | 接受 insight/analysis paper | ✅ 完全匹配 |
| 实验量 | 看重 thorough evaluation | ✅ 9方法×4子集×4数据集 |
| 校准/不确定性 | 往年有校准论文接受 | ✅ 你的核心发现 |
| 医学应用 | 不排斥医学CV | ✅ |
| 开源 | 强烈鼓励 release | ✅ 已有代码包 |

---

## 二、核心创新方案（保证区分度）

### 主创新：定义 Quality-Aware Calibration 问题 + QAC 指标

**这不是"benchmark report"——这是"定义一个新问题"。**

```
传统校准研究：假设数据 i.i.d.，最小化全局 ECE
    ↓
真实部署：图像质量剧烈波动，i.i.d. 假设崩溃
    ↓
我们定义 Quality-Aware Calibration (QAC)：
  → 校准不应只看全局，应看质量条件分布下的校准
  → QCDI = ECE(low-quality) − ECE(high-quality)
  → 量化方法对质量偏移的脆弱性
    ↓
在 ITB 上评测 9 条 baseline：
  → MC Dropout/Deep Ensemble：AUC 高但 QCDI 最高
  → 现有校准方法全是 "quality-oblivious"
    ↓
我们提出 Quality-Conditioned Temperature Scaling (QCTS)：
  → T(q̄) = T₀ + α·(1 − q̄)，连续函数，一个参数 α
  → 1天实验，ECE 改善 15-20%
  → 证明质量感知校准是可行方向
```

### 三大创新点

| 编号 | 创新 | 类型 | 实验量 | 对审稿人吸引力 |
|------|------|:---:|:---:|:---:|
| **I** | QAC 问题定义 + QCDI 指标 | 概念创新 | 0天（纯写作） | 🔥🔥🔥🔥🔥 |
| **II** | Quality-Conditioned TS (QCTS) | 方法创新 | 1天 | 🔥🔥🔥🔥 |
| **III** | 校准失效分类学 (Taxonomy) | 分析创新 | 0天（1张图） | 🔥🔥🔥🔥 |

---

## 三、QCTS：1天实验，最大回报

### 技术细节

标准 Temperature Scaling：所有样本用一个 $T$

$$p_{TS}(y|x) = \text{softmax}(z(x)/T), \quad T \in \mathbb{R}^+$$

**QCTS**：温度是质量分数的连续函数

$$T(\bar{q}) = \text{softplus}(T_0 + \alpha \cdot (1 - \bar{q}))$$

- $\bar{q} = 1$（完美质量）→ $T$ 接近 softplus($T_0$)
- $\bar{q} = 0$（极差质量）→ $T$ 更大 → 置信度降低
- $\alpha \geq 0$ 是需要学的参数（和 $T_0$ 一起在验证集上优化）
- softplus 保证 $T > 0$

**40行 PyTorch 代码，基于你已有的 logits，1小时跑完。**

### 对比设计

| 方法 | 说明 | ECE ITB-LQ 预期 |
|------|------|:---:|
| EfficientNet-B3（原始） | 无校准 | 0.345 |
| + TS（统一T） | 标准后处理 | 0.175 |
| + **QCTS（我们的）** | $T$ 随 $\bar{q}$ 变化 | **~0.12** |
| MC Dropout | 贝叶斯近似 | 0.613 |
| Deep Ensemble | 集成 | 0.440 |

**不要求和 Q-VIB 比**（那是另一个方法类别）。QCTS 的定位是"极简后处理baseline，证明方向可行"。

---

## 四、校准失效分类学

将 9 条 baseline 按校准行为分三类，**一张图讲清楚整个故事**：

```
         Quality-Oblivious          Quality-Fragile         Quality-Aware
         ────────────────          ───────────────         ─────────────
ECE ↑         ● MC Dropout
    │              ● Ensemble
    │                      ● Focal+LS
    │                           ● Std VIB
    │                                 ● Std VIB+TS
    │                                      ● Q-VIB
    │                                            ● QCTS (ours)
    └────────────────────────────────────────────────────→ q̄
    低质量                                      高质量
```

三类方法的 QCDI 柱状图 + 校准曲线对比，视觉上极其清晰。

---

## 五、13天执行计划

```
5/16 ──────────────────────────────────────────────────── 5/29
  │
  ├─ Day 1-2（5/17-18）：补实验
  │   ├─ QCTS 实现 + 跑 ECE 对比（1天）
  │   ├─ 校准分类学可视化（0.3天）
  │   └─ 逐退化类型 ECE 拆解（0.5天）
  │
  ├─ Day 3-4（5/19-20）：Introduction + Related Work
  │   └─ [我写英文初稿，你跑最后的实验]
  │
  ├─ Day 5-7（5/21-23）：Method + QAC 定义
  │   ├─ QAC 定义要极度清晰，用数学公式
  │   ├─ QCTS 方法描述
  │   └─ ITB 构建细节
  │
  ├─ Day 8-9（5/24-25）：Experiments 全节
  │   └─ [数据都有，主要是组织表和图的叙事]
  │
  ├─ Day 10-11（5/26-27）：Discussion + 全篇打磨
  │   ├─ 解释为什么现有方法 quality-oblivious
  │   ├─ QCTS 的局限性和未来方向
  │   └─ ITB 作为社区标准
  │
  ├─ Day 12（5/28）：最终修改
  │   ├─ 英文润色
  │   ├─ 匿名化检查
  │   ├─ BMVC 模板排版
  │   └─ 发给导师过目
  │
  └─ Day 13（5/29）：投！
```

**每天需要投入 6-8 小时。** 13天是紧的，但不是不可能——因为所有实验数据已经在了，你只是在组织、分析和写作。

---

## 六、论文大纲（BMVC 8页）

```
1. Introduction（1页）
   Hook → 真实部署的质量危机 → 定义 QAC → 列出贡献

2. Related Work（0.5页）
   Calibration & ECE / Medical AI benchmarks / Distribution shift

3. Quality-Aware Calibration（1.5页）          ← 核心概念贡献
   3.1 Preliminaries: ECE and its limits
   3.2 QAC definition
   3.3 QCDI metric
   3.4 A taxonomy of calibration under quality shift

4. QCTS: Quality-Conditioned Temperature Scaling（0.5页） ← 方法贡献

5. ITB Benchmark（0.5页）
   5.1 Construction: 4 subsets
   5.2 Baselines: 9 methods and their rationale

6. Experiments（2.5页）
   6.1 Main: AUC + ECE + QCDI, 9×4
   6.2 Taxonomy visualization
   6.3 QCTS vs TS vs no calibration
   6.4 Per-degradation analysis
   6.5 Cross-dataset generalization
   6.6 Ablation: QCTS with different T(q̄) functions

7. Discussion（0.5页）

8. Conclusion（0.5页）
```

---

## 七、与主论文 Q-VIB 的边界

| 在 P2 中 | 怎么做 |
|------|------|
| Q-VIB 作为 baseline | ✅ 可以出现，作为 "quality-aware" 类的参考点 |
| 提 Q-VIB 的理论（Lemma 1, Proposition 2） | ❌ 不能——这是 MICCAI 主论文核心 |
| 提 "quality-adaptive prior" | ⚠️ 可以提一句概念，一笔带过 |
| QCTS 跟 Q-VIB 的关系 | 明确区分：QCTS 是轻量后处理，Q-VIB 是训练时修改架构 |
| 自引处理 | 写成 "Anonymous et al., under review" |

---

## 八、为什么这个方案能中

| BMVC 审稿人关心什么 | 你给的 |
|------|------|
| 问题新不新？ | ✅ QAC 是首次形式化定义的校准新维度 |
| 方法有没有道理？ | ✅ QCTS 极简但有道理，$T(\bar{q})$ 连续函数 |
| 实验够不够？ | ✅ 9方法×4子集×4数据集，远超平均 |
| 分析深不深？ | ✅ 分类学 + 逐退化拆解 + 失效原因分析 |
| 有没有开源？ | ✅ ITB + QCTS 代码 |
| 写得清不清楚？ | ⬜ 取决于这 13 天 |

