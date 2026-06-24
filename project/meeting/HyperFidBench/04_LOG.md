# HyperFidBench — LOG（时间倒序，单一日志真源）

## Entry 1 — 2026-06-24 立项决策（用户拍板）

**来源**：选题流水线 `/ideate` 2026-06-24 轮（charter: `project/ideation/runs/2026-06-24_charter.md`；报告: `2026-06-24_选题报告.md`）。从 112 候选 → G2 16 → G3 评分 → G2′撞车核 + G4 红队 → 双 headline 幸存。本项目 = headline 1（B5-10）。

**立项要素**：
- **方向**：超图 GNN 脑病(ASD/AD)分类的解释忠实度 benchmark。对齐导师王水花超图 GCN 独门方向。
- **会议**：ACCV 2026（Biomedical track；截稿 2026-07-05）；退路 MICCAI workshop / BSPC。
- **核心 RQ**：同一忠实度公理下，超图 XAI(超边/GNNExplainer/Grad-CAM-graph)哪种最忠实+对齐 DMN；修复现有超图 fidelity 指标缺陷(2410.07764)。
- **边界**：与姊妹篇 [[WaveFidBench]] 同"XAI 忠实度"母题但模态/方法不重叠（本篇超图脑连接组 vs 姊妹 wavelet 脑结构 MRI）。

**G5 地基核查（researcher 联网，全绿）**：
- 数据 ABIDE I/II 免登录 S3 直下🟢；baseline BrainGB(217⭐)/BrainGNN(211⭐)/HyperGALE(超图16⭐)🟢；指标 PyG fidelity 内置+GraphFramEx+nilearn Schaefer(DMN)🟢。
- 最大坎=超图 fidelity 语义适配(删超边≠删边，~3-5天，是贡献点)。

**红队结论（skeptic G4）**：0 无出路致命。残差3条已入 02_ACCEPTANCE（引言讲透超图解释难评 / 可比协议先设计 / SHypX 无代码只引数字）。

**撞车（researcher G2′）**：🟡 有角度。最近邻 SHypX(2410.07764, 通用超图非脑病)、Explainable GNN Dementia(2509.18568, 普通图非超图无忠实度 benchmark)、HyperGALE(2403.14484, 分类无忠实度评测)。差异=脑病应用+跨解释类型可比协议+DMN 对齐。

**下一步**：认领 claim → `/design-experiment hyperfid` 出 Gate1 矩阵（先下 ABIDE + 跑通 BrainGB/HyperGALE + 验 PyG fidelity 出非 nan 数）。数据下载若走 HPC = 拍板点先报。
