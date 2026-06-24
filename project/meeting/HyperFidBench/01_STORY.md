# HyperFidBench — STORY（反跑偏主文）

## 核心 Claim（一句话钉死）

现有超图 GNN 脑病分类的「解释」无法横向比较、且 fidelity 指标本身有缺陷；本文给出**同一忠实度公理下的可比评测协议**，得到第一张超图 XAI 脑病忠实度 leaderboard，并发现哪类解释既忠实又对齐 DMN。

> 这是 **benchmark/empirical** 论文，不是新方法论文。卖点 = 评测协议 + 系统发现，不是更高分类精度。

## 为什么是真 gap（非"没人做"）

1. 超图 explainer 的 fidelity 指标有缺陷已被 arXiv 2410.07764 点名——洞是真的。
2. 超边(结构化)/GNNExplainer(子图)/Grad-CAM-graph(梯度热图)三类解释**在不同空间**，社区各报各的，无统一协议 → 不可比是真问题。
3. 脑病(ASD/AD)有神经科学先验(DMN 等网络)可作对齐金标准，但超图 XAI 从未对齐过。

## 章节弧

1. **Intro**：超图 GNN 在脑连接组崛起 → 但解释不可比 + fidelity 指标缺陷 → 临床/科学都需要可信解释 → 本文建协议+leaderboard。
2. **Related**：超图 GNN 脑病分类(HyperGALE 等)/图 XAI(GNNExplainer/GraphFramEx)/超图 explainer(SHypX 及其 fidelity 缺陷)/脑网络先验(DMN)。明确切开 SHypX(通用非脑病)。
3. **Method = 评测协议**：①同一忠实度公理(扰动后预测变化)定义跨解释类型可比的 fidelity ②超图 fidelity 的正确实现(删超边 vs 删边语义)③DMN 对齐度量(解释落在已知网络的比例)。
4. **Experiments**：ABIDE(+ADNI)上 ≥3 类解释 × ≥3 GNN/超图 baseline × {fidelity+, fidelity-, DMN 对齐}，出 leaderboard + 发现。
5. **Conclusion**：哪类解释最忠实/最对齐；超图解释的可信度边界;实践建议。

## 防御写法 R-rules

- **R1 不卖方法新**：全文定位 evaluation benchmark；不声称提出更好的分类器或 explainer。
- **R2 数字只用核实值**：所有 fidelity/AUC/对齐率经 verifier Bash 核 csv 才入文；禁 Read 看数据编造。
- **R3 撞车诚实**：Related 明写 SHypX(2410.07764)、GraphFramEx，本文差异=脑病应用+跨解释类型可比协议+DMN 对齐。
- **R4 可比协议先讲透**：超边 vs 热图不同空间，必须先论证为什么本文的公理化 fidelity 让它们可比，否则审稿人攻"苹果比橙子"。
- **R5 结论非平凡**：不能停在"大家都差不多"；必须有可操作发现(哪类解释在何条件最忠实/对齐 DMN)或意外结论。
- **R6 辖域限定**：claim 限超图 GNN × 脑连接组分类 × 这几个数据集，不外推所有图 XAI。

## 与组合台边界（防自撞）

- 姊妹篇 [[WaveFidBench]]：同是"XAI 忠实度评测"母题，但**模态/方法完全不同**(本篇=超图脑连接组；姊妹=wavelet 频域脑结构 MRI)。两篇共享忠实度评测**工程框架**(Quantus/扰动公理)可复用，但 claim/数据/方法不重叠。
- 与 ArtiOODBench(伪迹 OOD 检测)、MedAD-FailMap(失败外推)、selinf(报告值高估)：均不同母题，无重叠。
- 与 gdn2vessel(血管续连)、NCA 家族：完全无关。
