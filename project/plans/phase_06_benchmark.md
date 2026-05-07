# 阶段六：评测基准 ITB（Iterative Triage Benchmark）

## 目标

构建包含 4 个子集的标准化评测基准，对整个系统（含 Q-VIB 各组件）进行系统性评估。输出可直接用于论文的实验对比数据、Q-VIB 消融实验表格、校准曲线和可视化图表。

---

## 前置条件

- 阶段五完成：完整 Agent 系统可运行
- 阶段四完成：Q-VIB 各组件（编码器/先验/质量分词器）已训练并可独立推理
- `agent/eval_agent.py` 已实现基础评测逻辑

---

## 本阶段工具

| 工具 | 用途 |
|------|------|
| scipy | t-test 显著性检验、置信区间计算 |
| scikit-learn | AUC、F1、混淆矩阵、校准曲线（`calibration_curve`） |
| matplotlib + seaborn | 论文用图：对比柱状图、分布图、**校准曲线（reliability diagram）**、**$\sigma^2(\bar{q})$ 曲线 + KL 项双轴图** |
| pandas | 汇总 itb_results.csv，方便筛选和统计 |
| wandb | 多 run 对比 dashboard，实验结果一目了然 |

> 注：Expected Calibration Error (ECE) 可用 scikit-learn 的 `calibration_curve` 输出按 bin 计算，或手写（~10 行代码），无需额外依赖。

---

## 关键技术决策点

1. **每个子集样本数**：100 / 500 / 1000。推荐 500（统计显著性 vs 运行时间的折中）

2. **对比 baseline 选择**（选 4-5 个）：
   - **Baseline A**：直接诊断（无质量过滤，端到端分类器）
   - **Baseline B**：BRISQUE 质量过滤 + 传统分类器（硬门控）
   - **Baseline C**：无 Agent 交互的端到端模型（VisiScore + QAD，不追问用户）
   - **Baseline D**：标准 VIB（固定先验 $\mathcal{N}(0, I_d)$，无质量条件化）—— **Q-VIB 的关键对照**
   - **Baseline E（消融）**：Q-VIB 仅先验自适应（无质量分词器）
   - **Ours（完整版）**：Q-VIB 完整版（先验自适应 + 质量分词器）

   其中 A/B/C 是外部 baseline，D/E 是内部消融。如果运行时间紧张，A 和 B 可只选其一。

3. **人工评估是否参与**：全自动 / 加入小规模人工评估（5-10 人）用于验证 Agent 交互质量

---

## 交付物清单

| 文件 | 用途 |
|------|------|
| `benchmark/build_itb.py` | 构建 4 个子集，从数据集中采样并标注 |
| `benchmark/metrics.py` | 评估指标计算：分诊准确率/交互轮次/遵从率/质量改善率/**ECE（按 $\bar{q}$ 分段）**/**预测熵分布** |
| `run_experiments.py` | 批量实验脚本：对所有 baseline（含 Q-VIB 消融）跑完整评测 |
| `analyze_results.py` | 结果统计分析 + matplotlib/seaborn 可视化（含校准曲线、消融对比） |
| `results/itb_results.csv` | 所有实验的原始数字 |
| `results/itb_ablation.csv` | Q-VIB 消融实验单独表格（固定先验 vs 自适应先验 vs + 质量分词器） |
| `results/figures/` | 论文用图：对比柱状图、交互轮次分布图、质量改善示例图、**校准曲线（reliability diagram）**、**KL 项随 $\bar{q}$ 变化图** |

---

## ITB 4 个子集定义

| 子集 | 内容 | 评测目的 |
|------|------|---------|
| **ITB-LQ**（低质量） | 人工退化的低质量皮肤图 | 测试系统识别低质量并引导追问的能力；**Q-VIB 的核心优势场景**（Proposition 2 验证） |
| **ITB-HQ**（高质量） | 原始高质量皮肤图 | 测试系统在好图上的诊断准确率；验证 Q-VIB 在高质量段不损害性能 |
| **ITB-Edge**（边界案例） | 质量评分在阈值附近的模糊案例 | 测试系统在不确定情况下的鲁棒性；验证 sigmoid 过渡区的行为 |
| **ITB-Diverse**（多样性） | 多肤色（FitzPatrick I-VI）多病灶类型 | 测试系统的公平性和泛化性 |

---

## 工作步骤

1. **构建 4 子集**：从现有数据集中按子集标准采样，确保各子集互不重叠。特别关注 ITB-LQ 的退化参数分布（需覆盖不同 $\bar{q}$ 值）
2. **定义评估指标**：
   - 分类指标：准确率、F1、AUC（全局 + 按 $\bar{q}$ 分段）
   - **校准指标（Q-VIB 核心）**：ECE（Expected Calibration Error）、预测熵均值、KL 项均值——均按 $\bar{q}$ 分 5 段统计
   - 交互指标：平均交互轮次、引导成功率、遵从率
   - 写 `metrics.py` 并单元测试
3. **运行全量实验**：
   - 先跑 Baseline D（标准 VIB）和 Baseline E（消融版），确认 Q-VIB 组件的增量收益存在
   - 再跑完整 Ours 和外部 baseline A/B/C
   - 使用 `run_experiments.py --baseline <name>` 逐个运行，方便断点恢复
4. **Q-VIB 消融专项分析**（新增）：
   - 固定先验 vs 自适应先验：对比各质量分段的 ECE 和准确率
   - 无质量分词器 vs 有质量分词器：对比注意力漂移的实证效果
   - 可视化：校准曲线（reliability diagram）叠加对比、KL 项随 $\bar{q}$ 变化曲线
5. **统计分析**：置信区间、显著性检验（paired t-test between Ours and each baseline），确保结论统计可靠
6. **可视化出图**：生成论文质量的图表（字体/颜色/尺寸符合 MICCAI 要求），重点图：
   - 各 baseline 在 4 子集上的对比柱状图
   - Q-VIB 消融实验表 + 校准曲线
   - $\sigma^2(\bar{q})$ 曲线 + KL 项随 $\bar{q}$ 变化的双轴图（验证 Lemma 1 和 Proposition 2 的实证表现）

---

## 验收标准

- 4 个子集全部构建完成，总样本量达到设计规模
- 本系统在 ITB-LQ 子集上显著优于所有 baseline（这是论文核心实验）
- **Q-VIB 消融实验核心指标**：
  - 自适应先验版本在低质量段（$\bar{q} < 0.4$）ECE 显著低于固定先验版本（p < 0.05）
  - KL 项均值随 $\bar{q}$ 单调递减，与 Lemma 1 一致
  - 预测熵随 $\bar{q}$ 单调非增，与 Proposition 2 一致
- `analyze_results.py` 输出的图表可直接放入论文（无需额外美化）

---

## 硬件/资源约束

- 批量实验可能需要几小时 GPU 时间（每个 baseline × 4 子集 × 样本数）
- **Q-VIB 消融实验额外开销**：Baseline D（标准 VIB）和 Baseline E（消融版）各需独立推理，但模型结构相同仅权重不同，可复用推理管线
- 建议使用 `run_experiments.py` 的 `--baseline` 参数逐个运行，方便断点恢复
- 统计分析（CPU only）无显存压力

---

## 注意事项

- ITB-Diverse 子集需要覆盖 Fitzpatrick I-VI 各肤色，注意采样均衡
- 人工遵从率（用户按照 Agent 建议重拍的比率）如果没有真实用户，可用模拟：Agent 追问后自动提供"改善版"图片代替用户重拍
- 所有随机采样固定 seed，保证实验可复现
- 图表要提前确认 MICCAI 2027 的页面宽度和 DPI 要求，避免论文写作阶段返工
- **Q-VIB 消融实验设计细节**：
  - Baseline D（标准 VIB）与 Baseline E（Q-VIB 仅先验自适应）的唯一区别是 $\sigma^2(\bar{q})$ 调度——如果 E 在低质量段显著优于 D，则质量自适应先验的有效性得证
  - Baseline E 与 Ours 完整版的唯一区别是质量分词器——如果 Ours 优于 E，则注意力调制带来额外增益
  - 这两组对比是论文中最有力的消融证据，确保每组在 4 个子集上都有完整数据
- **ECE 计算**：按 $\bar{q}$ 等距分 5 个 bin，每个 bin 内计算 $\mathbb{E}[|\text{acc} - \text{conf}|]$，再取加权平均。确认 `benchmark/metrics.py` 中 ECE 实现与 scikit-learn 的 `calibration_curve` + 手写 binning 对齐
- **校准曲线图**：x 轴为置信度（等距 10 bin），y 轴为准确率，对角线为完美校准。叠加 Ours / Baseline D / Baseline E 三条曲线
