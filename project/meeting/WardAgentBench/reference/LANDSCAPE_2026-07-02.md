# Landscape 调研（researcher，2026-07-02，全 URL）

> 承接决策档（2026-07-01）。决策档写时未捕捉 MedAgentAudit + PSEBench 两篇最新撞车工作，本文补齐。

## 竞品 / 撞车威胁（按承重排序）

| 工作 | 是什么 | 与慧脉关系 | URL |
|---|---|---|---|
| **MedAgentAudit** ⚠️最强撞车 | 医学多 agent 协同失败模式分类学，10 类（unsupported observations 16.63%/authority bias 28.76%/minority suppression 5.11% 等），6 仿真数据集/3600 logs/14400 cases | 纯做失败分类学=撞车。差异=它无真实部署/无四角色/无去标识分流 | https://arxiv.org/abs/2510.10185 |
| **PSEBench** ⚠️ | 患者安全事件分流 benchmark，评 15 LLM（含 GPT-5.5/Claude Opus） | 最接近病房事件识别+分流，纯做分流 bench=撞车 | https://arxiv.org/pdf/2606.05463 |
| **MedAgentBrief** | Stanford Sequoia Hospital 真实住院 10 周部署，11 医生收 AI 出院小结 | 「LLM-agent 真实住院部署」坑的占据者，但做出院小结非多角色分流 | https://www.medrxiv.org/content/10.64898/2026.02.05.26345607v2 |
| MedAgentBench | 300 医生撰写任务/去标识 STARR/含 triage，虚拟 EHR agent 基准 | 去标识分流坑已被占 | https://ai.nejm.org/doi/full/10.1056/AIdbp2500144 |
| Emergency Triage Benchmark | 去标识急诊分流+恶化预测 | 同上 | https://arxiv.org/html/2509.26351v1 |
| MedGemma Bonn pilot | 放射科文本支持 1 周 22 医生 on-premise，无自主决策 | MedGemma 唯一真实 pilot=imaging，非病房多角色 | https://arxiv.org/pdf/2604.22768 |
| MAST (Cemri) | 通用（非医学）multi-agent 失败分类 14 模式/MAST-Data 1600+ traces | 通用失败分类学已多 | https://arxiv.org/html/2604.22708v1 |
| **AI-TEW** ⚠️(KS-1 补) | 两阶段 tiered 早预警减 false alarm，174K ED visits 三院验证 + LLM/SHAP filtering | 占「分层减误报」轴，但按**风险**分层提 PPV；慧脉腿 B 按**延迟**分轨(<5ms 绕 LLM)+复合误报 = 轴不同，避开 | https://www.nature.com/articles/s41746-026-02522-8 |

> **KS-1 事实更正**：MedAgentAudit 实为 **~6 类**（key info loss/minority suppression/bypass evidence/loss of diversity/fail to prioritize high-risk/self-contradiction），agent=同质医生咨询 agent 6 仿真集辩论，**非四角色**（先前「10 类」不准）。

## 空位裁决
「MedGemma + 病房多角色（患/家/护/医）+ 事件识别/分流 + 真实部署」四条同满足 = **成立但窄**。救命三角 = **真实部署接地 + 病房多角色 + 中国医院数据**。⚠️ 慧脉 demo-only → 缺「真实部署+中国数据」两角 → 纯公开数据路无护城河。

## venue（多数 CFP 未发布，定期查）
- **JMIR Formative Research**：滚动无截止，随时投，本科友好，APC $2500。https://formative.jmir.org/
- **ML4H 2026**：TODO CFP 未公布，历年约 9 月，含非存档 Findings track。https://ahli.cc/ml4h/call-for-papers/
- **CHIL 2027**：TODO（参照 2026=2/4 投稿，推 2027 约 2 月）。https://chil.ahli.cc/submit/call-for-papers/
- **Clinical NLP**：LREC 2026 版=2026-02-16 已过，2027 TODO。https://clinical-nlp.github.io/
- **GenAI4Health@NeurIPS 2026**：TODO（2025 版 8/22 截）。https://genai4health.github.io/

## 评估规范（仍主流）
- TRIPOD-LLM（living，Nat Med 2024，交互站 tripod-llm.vercel.app）https://pmc.ncbi.nlm.nih.gov/articles/PMC12104976/
- DECIDE-AI（早期临床评估，Nat Med 2022）https://www.sciencedirect.com/science/article/pii/S0009926022007048
- HealthBench（OpenAI 2025-05，~5000 对话 262 医生 rubric；有「not yet clinically ready」批评）

## 公开数据（详见 DATA_INVENTORY）
- Huatuo-26M-Lite（Apache-2.0）/ MedSafetyBench（MIT）/ MIETIC（PhysioNet CITI+DUA 2 周）/ MedDG·CBLUE-CHIP（中文 license 待确认）/ 生理集 SLEEP-EDF·MIMIC·PTB-XL·MIT-BIH。

## TODO（定期复查）
CHIL2027/ML4H2026/ClinicalNLP2027/GenAI4Health2026 四 CFP 未发布；MIETIC 认证确切工作日；MedDG/CBLUE-CHIP 确切 license。
