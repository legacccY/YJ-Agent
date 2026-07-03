# WardAgentBench — STORY（反跑偏主文，探路阶段）

## 现状（诚实起点）
慧脉守护 = 一套**基于开源医疗大模型拼装的病房多角色 LLM-agent 系统设计 + 可跑 demo**，技术栈清晰（脉枢 HuimaiMed：MedSigLIP + MedGemma-4B/27B + Qwen3-ASR/MedASR + Qwen3；ReAct 6 工具；向量/BM25 混合检索；生命体征轻量 ML 三模块 + 双轨告警），但**零真实临床数据、零 IRB、零自建/微调模型、零自证实验**。团队真实 IP 在海洋/港口 CV 域，医疗为新 pivot。

## 核心 claim（候选 B，2026-07-02 大编队 5 researcher + skeptic 定，冲 SCI 一区）

**卖点 = 开源 benchmark + 经验刻画 + 依赖稳健校准配方，不 claim 方法 novelty。**（B 族，组合台铁律「benchmark/empirical 全活」）

> **最小可辩护 headline（承重，一句话）**：一个开源可复现 benchmark + 参考实现，在公开波形数据上**经验刻画**多个共触发 ICU 阈值告警的复合误报行为，并给一个**对告警间依赖稳健的联合校准配方（e-value 聚合）**。

- **novelty 承重点**：数据/benchmark（首个系统刻画多告警共触发复合误报）+ 一个验证过的依赖稳健校准配方（因病房告警高度相关 → e-value 任意依赖仍 valid，比 Bonferroni/BH 正当）。**方法明标「已知机器换场景」不 claim novelty**（e-value 聚合=Vovk-Wang、Learn-then-Test=Angelopoulos、Pareto Testing 均已知）。
- **诚实 venue 天花板**：SCI 一区 = **IEEE JBHI（现实）/ npj Digital Medicine（冲刺）**；NeurIPS E&D 主 track = 低概率不押；保底 D&B-workshop / JMIR。
- **卖点为何冲得动一区**：真空成立（医疗侧复合误报联合校准只工业做过 + conformal 临床告警唯一没死白点）+ 纯公开波形数据 + 后验校准不训大模型（不塌，算力极小）。

### 三腿骨架
- **腿 B 承重**（候选 B benchmark）：公开波形数据上多共触发阈值告警的复合误报 benchmark + e-value 依赖稳健联合校准。**全押数据命门（见下）。**
- **腿 A 开源贡献**（原路线①降级）：WardLung Compass 规范成可复现开源多角色 ward-agent 参考实现。**不带失败分类学实证 claim。** 也是 KS-3 NO-GO 时的诚实退路。
- **腿 C feasibility 框架**：TRIPOD-LLM + DECIDE-AI 报告规范化。

### KS-1 致命伤记录（为什么不走路线①作实证）
路线①「病房四角色交接失败探针」作**承重实证 claim = 死**（skeptic 致命判定，高置信）：可用公开数据**结构性不支撑** —— MedDG = 17,864 例春雨消化科**医患**对话（无护士/无家属/无跨角色升级/无 SBAR 交接），CBLUE-CHIP/Huatuo 同为单轮 QA。四角色场景只能自构造 → 观察到的失败 = 作者 prompt 设计的产物非真实浮现，审稿人一句毙（同 memory [[mechanism_probe_methodology]] / [[delta_statetrack]] 型「结构性不存在」坑）。且底层是单一 MedGemma 被 prompt 扮 4 角，「角色特有失败」与 prompt engineering 完全混杂。→ 降腿 A（开源实现仍有价值，无实证 claim）。**复活条件**：找到真含护士/交班/多方会诊的公开语料（真实 nursing handoff / SBAR）——当前 landscape 无。

### 竞品事实（KS-1 核实，STORY 措辞据此）
- **MedAgentAudit**（arXiv 2510.10185）实为 **~6 类**协同失败（key info loss / minority suppression / bypass evidence / loss of diversity / fail to prioritize high-risk / self-contradiction），agent = **同质医生咨询 agent 在 6 仿真集辩论**，**非四角色**（先前「10 类」写法不准，已更正）。
- **AI-TEW**（npj Digital Medicine 2026, s41746-026-02522-8）= 两阶段 tiered 早预警减 false alarm，174K ED visits 三院验证 + LLM/SHAP。⚠️ 占「分层减误报」轴，但它按**风险**分层提 PPV，慧脉按**延迟**分轨（<5ms 绕 LLM vs 异步 LLM）——**轴不同**，腿 B 押延迟轴 + 复合误报避开它。
- **PSEBench**（2606.05463）= 文本患者安全事件分流，与腿 B 生理体征系统实证**不撞**。

## 🔴 命门（数据存在性，skeptic 高置信坐实，动笔前必证 <1 GPU·h）
候选 B 中心对象「N 个不同告警器同一时间窗共触发 + 逐告警真/假 + 复合 FAR」在公开数据**不带标注地存在**：PhysioNet 2015=单告警/段（五类跨段分布不共触发）；VTaC=全 VT 单类；MIMIC-III Waveform=告警稀疏、多告警共触发须自按阈值合成、**无专家真/假标签**（真/假只能靠结局代理定义）。→ 硬做 = 自造现象（撞 [[delta_statetrack]]/[[nca-phasemap]]「结构性不存在」坑，本项目已用同逻辑砍路线①）。

**KS-3 命门实验三问（全过才 GO）**：按 Chromik et al. 法在 MIMIC-III/IV Waveform 派生多阈值告警共触发 + 书面登记结局代理定真/假 →
1. 多告警是否**真以有意义频率+相关性共触发**（非罕见事件）？
2. 复合 FAR 效应在 **≥2-3 组合理阈值族**下是否稳健（换阈值不翻）？
3. 确认 PhysioNet 2015 五类标签无法供共触发标注（锁死单告警结论）。
- ✅ 三问全过 → GO 冲一区；❌ 任一翻（随阈值翻转 / 共触发罕见）→ 退腿 A 开源 + SOP，不硬撑。

## 防御写法 R-rules
- R1：所有数字 Bash/Grep 核 csv，入稿前过 verifier；禁 Read 看数据编造。
- R2：**开源模型文献值（MedQA/EHRQA/AUC/WER）明标「引用非自测」**，绝不当自证结果。
- R3：held-out 固定 seed 不混训练/无标注池；汇报前确认是 held-out。
- R4：公开数据方法用官方实现，超参标来源查不到标 TODO；复现零偏离。
- R5：不声称真实临床部署 / 不夸大两院背书；负/弱结果照报。
- R6：不与 MedAgentAudit/PSEBench 硬拼通用坑 —— 只押竞品没覆盖的窄接地贡献；拼不出就诚实退。
- R7：转公开物前隐私清洗（学生证/证件照）。
- R8（候选 B 专属）：**多告警共触发标签为派生（阈值规则+结局代理），非专家标注 —— 稿中必显式声明**，防审稿人逮 overclaim。
- R9（候选 B 专属，venue 定 2026-07-02，HYPSM 直博一作视角）：**主力双投 CHIL 2027 + MLHC 2027**（PMLR 归档、Research Track 明收无新方法公开数据 benchmark、本科一作无障碍、临床门槛隔离在别 track）；冲刺 npj DM（需临床通讯）/ NeurIPS E&D（stretch）；保底 ML4H Findings。**别用中科院分区衡量**（HYPSM 不看）。
- R10（候选 B 专属）：方法明标「已知机器（e-value/LTT/Pareto Testing）换场景」，novelty 押数据 benchmark + 经验刻画 + 依赖稳健配方，不 claim 方法 novelty。
- R11（候选 B related-work 必切 3 处邻接，步骤 2 撞车复查定，真空成立中高置信但要主动切割）：① 工业 FDR-cry-wolf（Reliab Eng 2026 S0951832025010907）→ 切「单检测器时序 vs 多告警器联合覆盖」；② Veritas-RPM（arXiv 2604.16081，临床多 agent 融合但**零统计保证**）→ 切「启发式 vs 有限样本联合保证」；③ 通用 e-value conformal selection（arXiv 2604.11305）→ 切「告警依赖/在线到达使通用方法不直接可用」。承重点 = 「多生成器 joint 有限样本保证 + 临床 benchmark」双要素同具，暂无人做。
