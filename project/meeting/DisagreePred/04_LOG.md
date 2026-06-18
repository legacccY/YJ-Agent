# DisagreePred PROJECT LOG

> 进度留痕。倒序（最新在上）。

---

## Entry 3 — 分歧分布确认（2026-06-18，零下载，用户拍板「先 XML-only 算分布」）

用户拍板**不下载过大数据**（LIDC 全集 124GB 出局）。researcher 探精简路径 → 关键发现：**pylidc 自带 `pylidc.sqlite`（6859 标注/1018 scan 全在 DB），算分歧分布零下载**（比下 XML <200MB 还省）。coder 写 `scripts/lidc_disagreement_stats.py`（monkey-patch np.int 修 pylidc 0.2.3 compat + 顺修 parse_lidc.py 同 bug）跑通：

**分歧分布（2651 cluster，无异常 scan，`results/lidc_disagreement_dist.csv`）**：
- k=1:771(29.1%) / k=2:488(18.4%) / k=3:481(18.1%) / k=4:897(33.8%) / k>4:14(0.5%,pylidc 聚类未降到≤4 的边缘)。
- **k=4 全一致=897(33.8%) vs k<4 存在分歧=1754(66.2%)**。
- 对照 Armato2011 65.2%，偏差仅 1.0pp = 数量级完全吻合 → **分歧标签信号真实存在，统计先验过**。

⚠️ 注意：这只证**标签分布真实**，"分歧可从图像预测"（真 KILL-1）仍需 CT patch 跑 AUROC。

**精简数据路径（datasets.json lidc_idri 已登）**：①XML/DB 零下载算分布(已做✅) ②DICOM-LIDC-IDRI-Nodules 2.51GB=per-annotator SEG mask(非CT像素) ③真 KILL-1 需 CT 图像 patch→NBIA 子集 ~50 scan(~6GB,smoke)/~150 scan(~18-24GB,功效足)。LUNA16 衍生丢标注者身份不可用/QUBIQ 无肺结节排除。

**带债 / 下一步拍板点**：分布既已坐实，真 KILL-1（图像预测分歧 AUROC>0.60）需下小 CT 子集——等用户定 ~6GB(50scan smoke) 还是 ~18-24GB(150scan 一步到位)，或继续暂缓。k>4 的 14 cluster 处理（clamp 到 4 还是丢）留 parse_lidc 实现时定。

---

## Entry 2 — Gate1 设计 + skeptic 红队 + 数字订正（2026-06-18，用户拍板方案甲）

**planner 出 KILL-1 矩阵 → skeptic 红队 1🔴 + researcher 核源逮出 STORY 数字错 → 用户拍板补救。**

🔴 **致命（label leakage）**：负样本 k=0（无结节区）让「分歧 vs 不分歧」≈「有结节 vs 无结节」，模型学结节检测就能拿高 AUROC = KILL-1 假 PASS，根本没验「分歧可预测」。**用户拍板方案甲**：KILL-1 改为**只在 k≥1 区内**（至少 1 医师标注的位置）预测专家是否分歧（k∈{1,2,3} vs k=4 全体一致），彻底切检测捷径。社区 SSN（Monteiro+ NeurIPS2020）正是只处理被标过切片。已订正 01_STORY（加 KILL-1 设计红线）+ 02_ACCEPTANCE A1。

🔴 **数字错（researcher 核源）**：旧稿「margin 0.22」用错——0.22 来自 **Dong 2017 是结节边缘锐利度评分（1-5 量表）的分歧**，**不是 detection-level 存在性分歧**。存在性分歧正确口径 = **65.2%**（2669 被标结节仅 928=34.8% 获 4/4 一致，Armato et al. Medical Physics 2011, PMC3041807）。已订正全处（STORY/README/registry/datasets/本 LOG）。

**researcher 补齐官方口径（堵臆想）**：
- pylidc `cluster_annotations()` tol 默认=`slice_thickness`（⚠️ 文档写 pixel_spacing 是 bug，源码为准 Scan.py L419）；padding 在 `bbox/boolean_mask(pad=)`。
- 负样本社区惯例：用 annotation count 当 soft label（0/4~4/4）或只处理标过位置（方案甲对齐）。
- CT 超参：肺窗 clip[−1000,400] 归一化 `(x+1000)/1400`（LUNA16）；ImageNet ResNet-18 当 2D 探针合理（RadImageNet 无 R18 权重，3D 用 MedicalNet）；patient-level split；CT 禁垂直翻转，水平翻转+±10°旋转 OK；Adam lr=1e-4 wd=1e-4。
- 撞车信号：arXiv 2508.09381（skin lesion 从图像预测 IAA 一致性用 AUROC）但当**辅助任务**，落 K2 对手侧，差异化暂守得住——靠「分歧空间结构对齐」拉开（A1 后半句别省）。

**下一步**：派 coder 实现 pylidc 解析（方案甲：k≥1 区分歧标签 + 投票熵）+ KILL-1 baseline（ResNet-18 5seed + 置换检验 + bootstrap AUROC CI）。数据先下 LIDC 到本地（~124GB，确认 D 盘）；🛑 上 HPC=拍板点。

---

## Entry 1 — 立项 spin-off（2026-06-18，用户已拍板）

**立项决策**：源 = ideation run-002（医学图像 × 不确定性）G6 立项 **C065**。用户 2026-06-17 AskUserQuestion 拍板「立项 C025 + C065」（G6_charter.md 签字）。本 entry 为拍板后 spin-off 执行（建标准 schema + 登 registry），非新决策。

**RQ / headline**：别再把标注者分歧当噪声消除——分歧本身可从图像预测。LIDC-IDRI 上把「预测 4-annotator 分歧」当建模目标（而非 majority-vote 取 GT），首次证明分歧是图像可预测的结构信号而非随机标注噪声；模型在专家也犹豫处主动犹豫 = 临床 deferral 信号。

**与边界**：纯新项目（非主论文拆分）。与 ICLR(VisiSkin) / MedAD-FailMap / FMReg / NCA-PhaseMap / SelInfBench 零重叠——多标注分歧预测，正交于校准 / 分割 / 配准 / meta-science。

**立项依据**：
- LIDC-IDRI 4-annotator 存在性分歧巨大（65.2% 被标结节非 4/4 一致，Armato 2011 PMC3041807）= 真实、可量化、临床有意义的分歧源。⚠️ 旧稿「margin 0.22」用错（0.22=Dong2017 边缘锐利度评分分歧≠存在性分歧），2026-06-18 researcher 核源订正。
- R4 taste 48 全 top，零直接竞品；framing 新（预测分歧 vs 消除分歧取 GT）。
- ⚠️ 须守差异化于 EDUE(2403.16594) / 2510.10462（难度估计 / disagreement-guided 训练）——它们用分歧辅助别的目标，本文把「预测分歧本身」当终极目标。
- 立项卡 `ideation/runs/2026-06-17_run-002_medimg-uncertainty/07_report/G6_charter.md` 立项 2。

**G5 killshot ⏳ 未跑（数据待下）**：列为 KILL-1 gating，立项后首要动作——区别于 C025（已 PASS），C065 的核心 claim 全押在下 LIDC 后的分歧可预测性 baseline。先验后大投入。

**诚实天花板**：framing 强 + taste 高，但核心 claim 全押 KILL-1（分歧可预测 AUROC > 0.60）。过不了即砍。退路档 MedIA/UNSURE/D&B（A1+A2+A3 单集）；顶会 MICCAI 需 A4（QUBIQ 第二集 + deferral 临床价值）。书面 kill criteria K1-K4 见 02_ACCEPTANCE。

**带债 / 立项后第一前置**：
- R1（gating，最优先）：下 LIDC-IDRI（TCIA 公开免费 1018 CT 4-annotator）→ 跑分歧可预测性 baseline（KILL-1，AUROC ≤ 0.60 即砍）。
- R2（差异化）：投稿前 researcher 复查 EDUE/2510.10462 系列是否先发占 disagreement-as-target（KILL-2）。
- R3（普适+临床）：QUBIQ 第二集复现 + deferral 实验（A4，standout 升级）。

**venue**：top MICCAI 2026｜fallback MedIA / UNSURE workshop / NeurIPS D&B。算力 ≤ 50 GPU·h。

**下一步 Gate1**：先下 LIDC-IDRI（**HPC 上传新数据 = 拍板点，先报用户**）→ `/design-experiment disagree` 出 KILL-1 baseline 矩阵。数据尚未在 `.portfolio/datasets.json`，已登 lidc 条目 status=todo。
