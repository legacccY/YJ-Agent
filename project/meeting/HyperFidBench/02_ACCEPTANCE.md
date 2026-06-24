# HyperFidBench — ACCEPTANCE（二元 PASS/FAIL 验收）

## lever 分解（headline 承重链）

headline =「超图 XAI 脑病忠实度可比协议 + leaderboard + 非平凡发现」，承重三腿：
- **L1 协议可比性**：同一忠实度公理下，超边/GNNExplainer/Grad-CAM-graph 能被放进一张可比的 fidelity 表（不是各报各的）。
- **L2 leaderboard 真实**：≥3 解释 × ≥3 baseline × ≥2 数据集(ABIDE I/II 或 +ADNI)，fidelity 数字经 verifier 核 csv。
- **L3 非平凡发现**：得到可操作结论(哪类解释在何条件最忠实/最对齐 DMN)，非"大家都差不多"。

## 阶段硬阈值

| 阶段 | PASS 条件 | FAIL→动作 |
|---|---|---|
| Gate1 地基跑通 | ABIDE 下载+BrainGB/HyperGALE 训练出可用分类器(ASD acc 合理, 对齐文献~65-70%) + PyG fidelity 能算出非 nan 数 | 跑不通/数据拿不到 → 砍(见 K1) |
| Gate2 协议成立 | 超图 fidelity 正确实现(删超边语义)+ 三类解释进同一可比表 + DMN 对齐可计算 | 协议立不住(无法可比) → 退 workshop 或砍(K2) |
| Gate3 leaderboard+发现 | ≥3解释×≥3baseline×≥2集 全表 + ≥1 条非平凡可操作发现 | 只得"都差不多"无发现 → 退 BSPC/workshop(K3) |

## 红线（反跑偏，不可松动）

- **数字一律 Bash/Grep 核 csv**，不信 Read（[[feedback_verify_paper_numbers.md]]）。fidelity/AUC/对齐率入文前过 verifier。
- **评估不泄漏**：解释忠实度评测的扰动/held-out 不混入训练；分类器训练/测试 patient-level split 不交叉。
- **超参禁臆想**：BrainGB/HyperGALE/GNNExplainer 超参一律查官方源，查不到标 TODO（[[feedback_no_hallucinate_settings.md]]）。
- **复现零偏离**：baseline 按官方实现跑，不私改凑结果（[[feedback_repro_zero_deviation.md]]）。
- **不卖方法新**：定位 benchmark，不声称 SOTA 分类。

## 书面 kill criteria（事前冻结，防 HARKing）

- **K1 地基死**：ABIDE 拿不到 / 超图 baseline+fidelity 工程跑不通(>预算仍无 nan-free 结果) → 砍。
- **K2 协议塌**：无法构造让超边 vs 像素热图可比的公理化 fidelity（"苹果比橙子"攻不破）→ 退 workshop 或砍，不硬凑。
- **K3 发现空洞**：leaderboard 跑完只得"各解释忠实度无显著差异/都对齐差"且无任何可操作结论 → 退 BSPC/workshop，不当 ACCV main 卖。
- **K4 撞车**：投稿前复查，若 2026 出现做了同样"超图脑病 XAI 忠实度 benchmark"的论文 → 重定位差异或退路。
- **K5 算力超支**：>8 GPU·h（实际应远低）仍无可用结果 → 停下报。

## G4 红队残差（动手前置，已记 LOG）

1. 引言必须讲透"为什么超图解释比普通 GNN 更难评"，否则 reviewer 不买超图这个前提。
2. 超边 vs Grad-CAM 可比协议是 L1 命门——先设计协议再跑，不是先跑再补。
3. SHypX 无公开代码 → 若 benchmark 要对比超图专用 explainer，只能引论文数字，须确认其论文有可复用数字表（否则该格留 TODO 不编造）。
