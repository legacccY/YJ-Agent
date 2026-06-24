# WaveFidBench — LOG（时间倒序，单一日志真源）

## Entry 1 — 2026-06-24 立项决策（用户拍板）

**来源**：选题流水线 `/ideate` 2026-06-24 轮（charter: `project/ideation/runs/2026-06-24_charter.md`；报告: `2026-06-24_选题报告.md`）。从 112 候选漏斗收敛，本项目 = headline 2（B5-13），与 [[HyperFidBench]] 双 headline 并行。

**立项要素**：
- **方向**：Wavelet 频域子带视角的 XAI 忠实度 benchmark（AD 分类）。对齐导师王水花 wavelet×Transformer + 可解释双招牌。
- **会议**：ACCV 2026（Biomedical track；截稿 2026-07-05）；退路 CBM / BSPC。
- **核心 RQ**：AD 判别信息在 wavelet 频带的分布 + XAI 解释是否对齐承载信息的频带 + 哪类 XAI 在哪频带最忠实。
- **边界**：与姊妹篇 [[HyperFidBench]] 同"XAI 忠实度"母题但模态/方法不重叠（本篇 wavelet 脑结构 MRI vs 姊妹超图脑连接组）；共享 Quantus 工程框架。

**G5 地基核查（researcher 联网，全绿）**：
- 数据 Kaggle AD 4-class 当天可下🟢/OASIS 签 DUA🟢；baseline pytorch_wavelets(1.2k⭐)子带置零3行🟢；指标 Quantus(666⭐ ROAD/IROF)+captum🟢；<5 GPU·h。
- 撞车二次确认🟢干净：最近邻 WaveletFusion(2026-05 Haar+CNN AD,无忠实度维度)、2601.12826(肺CT无wavelet)、2407.08546(AD显著图无wavelet子带)。频带×忠实度交叉空白确认。

**红队结论（skeptic G4）**：0 无出路致命。残差4条已入 02_ACCEPTANCE（严守 benchmark 定位 / novelty 锚频带轴 / Quantus insertion-deletion 待核 / 2601.19017 思路借鉴诚实标）。

**最大风险**：WaveletFusion(2026-05)结构最近邻 → 必须定位 evaluation benchmark(多 XAI×多子带×多指标)拉开距离，不写成又一个 wavelet 分类器。

**下一步**：认领 claim → `/design-experiment wavefid` 出 Gate1 矩阵（下 Kaggle AD 4-class + 跑通 ResNet/ViT + pytorch_wavelets 子带置零 + Quantus 出非 nan faithfulness）。先核 Kaggle 数据溯源(防 AI 合成伪造集)。
