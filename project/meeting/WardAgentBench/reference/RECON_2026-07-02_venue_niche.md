# 大编队侦察：冲 SCI 一区/顶会 venue + 低竞争 niche（2026-07-02）

> 5 opus researcher + skeptic 红队。用户要求上限 SCI 一区/顶会、低竞争、可行。全 URL 落此。

## 裁决（诚实档次）
- **SCI 一区 = 现实可达**：IEEE JBHI（JCR Q1 / 中科院小类医学信息 1 区 / APC $2345 / 审 2.5 月，性价比最稳）；npj Digital Medicine（中科院医学 1 区 Top，IF18，APC $4290，冲刺档，有 benchmark 先例）。
- **顶会主 track = 低概率不押**：NeurIPS 2026 Evaluations & Datasets track 官方不要求 novelty/SOTA，但 25% 接收率下「本科一作 + 无真实数据 + 已知方法 + 合成派生 benchmark」难中主 track。天花板据实定一区期刊 + D&B-workshop。
- **主攻方向 = 候选 B**（两个独立 researcher 汇聚 + skeptic 放行，命门先行）。

## venue landscape（R1 期刊 + R2 会议）
### 顶会/会议
- **NeurIPS 2026 Evaluations & Datasets track**（原 D&B 改名扩容）：「submissions need not introduce a new model or outperform prior work」，数据需公开托管 + Croissant metadata；abstract 2026-05-04 / full 2026-05-06 AoE；接收率 ~25%。https://neurips.cc/Conferences/2026/CallForEvaluationsDatasets
  - 先例：AgentClinic（demo-only 临床 agent benchmark 进 D&B）https://openreview.net/forum?id=ak7r4He1qH
- ML4H 2026：Proceedings（PMLR 归档 ≤8p）vs Findings（非归档 ≤4p），历年约 9 月截，CFP 未发布(TODO)。https://ahli.cc/ml4h/call-for-papers/
- CHIL 2027（AHLI，有 Proceedings，三轨含 Applications&Practice）：预计 2026-12 开投（2026 版 2/4 已过）。https://chil.ahli.cc/submit/call-for-papers/
- BioNLP@ACL2026 shared task（demo+公开数据友好，非正会）：paper 截 2026-04-17。https://www.aclweb.org/portal/content/shared-task-clinskill-qa-bionlp-acl-2026
- AAAI-27（full 2026-07-28，benchmark 占比低本科难）；GenAI4Health@NeurIPS（2025 版 8 月截，非归档）。

### SCI 一区期刊
| 期刊 | IF | 分区 | 收 benchmark? | APC | 备注 |
|---|---|---|---|---|---|
| **IEEE JBHI** | 7.7 | JCR Q1 / 中科院小类医学信息 1 区 | ✅ | $2345 | 审 2.5 月，性价比最稳 |
| npj Digital Medicine | 18.0 | 中科院医学 1 区 Top | ✅（AgentClinic/CSEDB 先例） | $4290 | 冲刺档，编辑筛狠 |
| PLOS Digital Health | 7.7 | JCR Q1，**中科院未收录** | ✅ 最不吃 novelty | ~$2575 | 认中科院一区则不行 |
| JMIR | 8.2 | JCR Q1 / 中科院医学 2 区 | ✅ 收稿广 | $2950 | evaluation 友好 |
| IJMI | 5.0 | JCR Q1 / 中科院医学 2 区 | ✅ 评测/部署主场 | $3160 | 审快 |
- ⚠️ CBM（IF6.3）快但有预警传闻，投前查名单；JBI 已掉 Q2 不推；Nature Machine Intelligence 太难。

## niche 白地（R3 白地 + R4 方法 + R5 中文）
### 🟢 候选 B（主攻）— 医疗多告警器复合误报联合校准 benchmark + 依赖稳健校准
- R3：医疗侧复合误报联合校准 = 最干净真空（只工业消防/安防做过）；医疗误报 ML 全单信号。
- R4：conformal 临床告警唯一没死白点 = 多相关告警器 OR 融合联合保证（e-value 聚合任意依赖 valid / Learn-then-Test / Pareto Testing）。「conformal+selective+cost-defer 单模型 triage」已被 Sci Rep 2026（s41598-026-40637-w）吃掉。
- 理论抓手顶会先例：Conformal Risk Control @ ICLR2024；Learn-then-Test（arXiv 2110.01052）；Pareto Testing（arXiv 2210.07913）；e-value FWER（arXiv 2501.09015）；e-value 聚合任意依赖（arXiv 2605.07963）。

### 🟢 候选 A（次选）— 边缘/资源受限医学 *agent* 延迟-显存-精度前沿 benchmark
- 半真空：占位者 arXiv 2601.03266「On-Device LLMs for Clinical Decision Support」是单轮 CDS 非 agent；医疗 agent × 边缘仍空。劣势：基建重（多模型 on-device profiling）+ agent 任务撞「真任务不存在」坑。KS-3 过则 B 风险 < A。

### 不推
- 候选 C 四角色 agent（模拟医院饱和 AI Hospital/MAP npj 2026/MedAgentBoard）；D 机器人 HRI（违纯公开数据）；E 中文 agent（MedBench v4 已含 agent track）。
- R5 中文病房/护理 + 方言医疗 = 蓝海但标注数据不存在须自建（撞 [[benchmark_stratify_gt_first]]）。中文医疗 benchmark 进顶会有先例（CMExam→NeurIPS2023 / CMB→EMNLP2023 / CliMedBench→EMNLP2024 / MedBench→AAAI2024）。

## skeptic 红队候选 B（致命=1，有出路）
- 🔴 **数据命门（生死点）**：PhysioNet 2015=单告警/段（五类跨段不共触发）；VTaC=全 VT 单类；MIMIC-III Waveform=告警稀疏、多告警共触发须自按阈值合成、无专家真/假标签。→ 硬做=自造现象。出路=KS-3 三问先证（见 02_ACCEPTANCE）。
- 🟠 novelty 双腿互掏：方法=已知机器换场景（薄）；数据=自造合成。→ 押数据 benchmark + 经验刻画 + 依赖稳健配方（E&D 式不 claim 方法 novelty）；「告警高相关→e-value 优于 Bonferroni/BH」是非任意正当动机。
- 🟠 撞车中置信：未见 clinical alarm fusion + FWER/FDR 直接撞车（conformal-e-value FDR 文献 arXiv 2604.11305/2302.07294 全通用未落地告警融合），但单告警 FAR 削减红海（PhysioNet2015 衍生几十篇 + VTaC + npj2019 + SigmaMedStat 2605.29236 + AI-TEW）。→ 步骤 2 再查一次锁死 + related work 明切「联合 FAR + 依赖稳健」非单告警削减。
- 🟢 venue 天花板：诚实 JBHI/npj DM/D&B-workshop，别写 NeurIPS 主 track。

## 关键 URL（竞品/方法/数据）
- Sci Rep 2026 conformal selective triage — https://www.nature.com/articles/s41598-026-40637-w
- Pareto Testing — https://arxiv.org/abs/2210.07913 ｜ Learn-then-Test — https://arxiv.org/abs/2110.01052
- e-value 聚合任意依赖 — https://arxiv.org/html/2605.07963v1 ｜ FWER with e-values — https://arxiv.org/pdf/2501.09015
- Conformal Risk Control ICLR2024 — https://proceedings.iclr.cc/paper_files/paper/2024/file/f3549ef9b5ff520a7e41ff3cc306ab2b-Paper-Conference.pdf
- VTaC NeurIPS D&B 2023 — https://proceedings.neurips.cc/paper_files/paper/2023/file/7a53bf4e02022aad32a4019d41b3b476-Paper-Datasets_and_Benchmarks.pdf
- PhysioNet 2015 Challenge — https://physionet.org/content/challenge-2015/1.0.0/
- MIMIC-III Waveform — https://physionet.org/content/mimic3wdb/1.0/ ｜ Chromik 告警派生 — https://pdfs.semanticscholar.org/885f/5bd815509c191d1d2dd72991a51d5742b4a3.pdf
- SigmaMedStat 2026 — https://arxiv.org/pdf/2605.29236 ｜ AI-TEW npj DM 2026 — https://www.nature.com/articles/s41746-026-02522-8
- 边缘 CDS 占位者 — https://arxiv.org/abs/2601.03266

## 步骤 2 撞车复查 ✅ 已过（2026-07-02，真空成立中高置信）
两轮穷尽未找到「临床多告警器**联合**误报有限样本保证 benchmark/方法」——**此格子确为空**。承重点 = 「多生成器 joint 有限样本保证 + 临床 benchmark」双要素同时具备暂无人做。但 STORY related-work **必须显式切割 3 处强邻接**（R11）：
1. **工业 FDR-cry-wolf**（Reliability Eng & System Safety v267 2026, S0951832025010907）：已用 FDR 量化 alarm fatigue + FDR-control，但**工业单检测器时序**（TEP+镀锌线）。→ 切「单检测器时序 FDR vs 多告警器**联合**覆盖」。https://www.sciencedirect.com/science/article/abs/pii/S0951832025010907
2. **Veritas-RPM**（arXiv 2604.16081 2026）：临床 RPM 多 agent 融合抑制假阳，但**纯启发式零统计保证**（TSR/FER/INDR）。→ 切「启发式融合 vs 有限样本联合保证」（正是本 claim 补的洞）。https://arxiv.org/abs/2604.16081
3. **通用 e-value conformal selection**（arXiv 2604.11305 2026）：reviewer 潜在「直接套」弹药。→ 切「告警依赖结构/在线到达/事件定义使通用方法不直接可用」。https://arxiv.org/pdf/2604.11305
- 旁证单检测器/启发式多参数降警全无联合保证：SigmaMedStat(2605.29236 单 vital)、sepsis conformal(medRxiv 2024 单检测器)、PhysioNet2015 多参数抑制(全启发式)、工业 ISA-18.2/EEMUA-191(无跨检测器 FWER/FDR)。

## TODO
- ML4H2026/CHIL2027 CFP 未发布定期查。MIMIC Waveform 多告警派生标注可行性 = KS-3 证。
