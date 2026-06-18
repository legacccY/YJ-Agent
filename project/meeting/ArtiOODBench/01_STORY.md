# ArtiOODBench — STORY

## Headline

**医学影像 OOD 检测基准在测量采集 artifact，而非病理异常。** 不看任何病理内容的 artifact-only 手工特征即可高 AUROC 区分 ID/OOD（NIH vs VinDr，resize 控分辨率后 AUROC=0.92），说明现有 benchmark 的「OOD 信号」大半是 scanner/采集指纹。当 ID 与 OOD 来自不同机构/设备时（绝大多数医学 OOD benchmark 如此），方法排名被 artifact 混淆——「更强的 OOD 检测器」可能只是「更会读 scanner 指纹的检测器」。

## 为什么是 CV 社区在意的通用失效（非纯医学 niche）

这是 **spurious correlation / shortcut learning 在 OOD detection 评测层的实例**：评测协议本身被一个与任务无关但与域标签强相关的混杂变量（采集 artifact）污染。CV 社区对「benchmark 在测捷径不测能力」高度敏感（ImageNet-C、backgrounds challenge、shortcut learning 系列）。医学影像是这个失效的**最佳放大镜**——不同机构的 scanner/采集协议差异巨大且系统化，artifact 信号比自然图像强得多。

## Lever（承重链）

1. **L1 现象量化**（G5 已确证）：artifact-only 特征在 ≥3 个医学 OOD benchmark 对上的 AUROC 系统量化（不止 NIH/VinDr，扩到 MedIAnomaly 7 集 + dermoscopy 跨集）。证明污染普遍非个例。
2. **L2 去污染协议**：提出去除 artifact 信号的方法（如 artifact 特征 regress-out / 分层评测 / artifact-matched ID-OOD 配对），得到「干净」OOD 评测。
3. **L3 重排闭环**（命门 = actionable so-what）：在去污染评测下重跑主流 OOD 方法，证明**排名真的变了**（≥2 个方法排名翻转 / top 掉出 top3）。这是与「benchmark 有 artifact」（已知）的关键区别——污染有 actionable 后果。

## 与先驱的差异化（红队残差，Related Work 硬对齐）

- **OpenMIBOOD**（arXiv:2503.16247, CVPR25）：已区分 covariate-shift vs semantic-shift 概念，但**未做 artifact-only 量化 + 去污染重排**。
- **PMC10532230**（3D MRI）：已报 IHF AUROC=0.97 + 「benchmark 可能含 trivial feature」，但**限 3D 分割、无去污染重排、无方法重排闭环**。
- 差异化 = **2D 多模态系统化（L1）+ 去污染协议（L2）+ 方法重排闭环（L3）**。L3 是任何先驱都没做的承重点。

## 诚实边界（防跑偏）

- 现象 0.92 < 0.95 没顶满，且 NIH/VinDr 本就不同机构——headline 写「artifact-only 达 0.92」不夸大成「完全是 artifact」。
- 不 claim「所有 OOD benchmark 都废」；claim「当 ID/OOD 跨机构时排名被混淆，需去污染评测」。
- 若 L3 重排后排名不变（污染无 actionable 后果）→ 诚实降 ICBINB 短文，不硬撑。
