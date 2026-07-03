# WardAgentBench — 慧脉守护病房多角色 LLM-agent 科研转化（候选 B 立项，冲 SCI 一区）

> **一句话**：把创业项目「慧脉守护」（病房四端 LLM-agent + 服务机器人，脉枢 HuimaiMed）转化为可发表科研成果。**当前 = demo 原型零真实临床数据** → 纯公开数据路。2026-07-02 大编队（5 researcher + skeptic）侦察定方向 = **候选 B：医疗「多告警器复合误报」联合校准 benchmark + 依赖稳健校准配方**，冲 **SCI 一区（IEEE JBHI 现实 / npj DM 冲刺）**。
>
> **诚实定性**：产品侧成熟但科研从零起步（无数据/IRB/自证实验）。候选 B 卖点 = 开源 benchmark + 经验刻画 + e-value 依赖稳健校准（**不 claim 方法 novelty**，B 族）。顶会 NeurIPS E&D 主 track = 低概率不押，天花板诚实定一区期刊。
>
> **🔴 全押数据命门**：候选 B 中心对象「多告警共触发 + 逐告警真/假」在公开数据不带标注存在 → 动笔前必跑 KS-3 数据命门实验（<1GPU·h）证「共触发真频繁 + 复合 FAR 换阈值族稳健」，翻则退腿 A 开源 + SOP。详见 `01_STORY.md`。
>
> **定位**：低优先，当 SOP 临床合作叙事资产 + 冲一区双目标，**不挤 ArtiOOD/FetalSS/SelInf/QuantImmu 收尾**。导师 = 王水花（同 FetalSSBench）。
>
> **venue（2026-07-02 定，HYPSM 直博一作扛旗视角，非中科院分区）**：**主力双投 CHIL 2027（约 2 月）+ MLHC 2027（约 4 月）**——均 PMLR 归档、HYPSM 认、Research Track 明收无新方法公开数据 benchmark、本科一作无结构障碍、竞争池小（~25-36%）；CHIL 先投未中转 MLHC 错开。**冲刺** npj Digital Medicine（需拉临床 MD 挂通讯）/ NeurIPS E&D（stretch）。**保底** ML4H Findings（非归档练手）。IEEE JBHI 兜底。国内中科院分区不适用（HYPSM 不看，会低估 CHIL/MLHC）。
>
> **status**：`planning`（2026-07-02 候选 B 立项，承接决策档 + 大编队侦察 `reference/RECON_2026-07-02_venue_niche.md`）

## 铁律（本项目专属红线）
- **禁用 MedQA 69% / EHRQA 90% / AUC 0.881 等数当自己结果** —— 这些是底层开源模型（HAI-DEF/MedGemma/MedSigLIP/Whisper）的**已发表文献值**，引用须明标「引用值非自测」，当自证 = 学术不端。
- **诚实标 demo/设想**：慧脉当前无真实临床数据，任何叙事不得声称「已在两院跑真实病例」；两院是「成果应用证明」背书函，非数据交付。
- **隐私清洗**：源目录 `D:\商业计划书\` 含 `学生证.jpg` + 团队证件照/生活照，转任何公开物前必清（gh-publisher 隐私扫描，memory [[public_release_privacy_scrub]]）。
- 纯公开数据 + 复现零偏离；数字一律 Bash/Grep 核 csv 不信 Read；超参查官方源查不到标 TODO。
- 评估集不可泄漏；held-out 绝不混训练/无标注池。

## 读档顺序（新窗口一跳读全）
00_README（本文）→ `01_STORY.md`（候选 claim 三腿 + 命门假设 + R-rules）→ `02_ACCEPTANCE.md`（探路 GO/NO-GO 判据）→ `DATA_INVENTORY.md`（公开数据细目）→ `04_LOG.md` 最新 entry →（动手）`reference/LANDSCAPE_2026-07-02.md`（竞品清单 + 全 URL）+ `reference/SOURCE_MATERIALS.md`（商业计划书/PPT/repo 核实结论）

## 下一步（候选 B，见 02_ACCEPTANCE）
- ✅ **KS-1** 路线选择红队（done 2026-07-02）→ 候选 B。
- ✅ **venue/niche 大编队侦察**（done）→ 双靶 JBHI/npj + 候选 B 主攻，落 `reference/RECON_2026-07-02_venue_niche.md`。
- 🔄 **步骤 2 撞车复查**（researcher 在跑）：锁死「clinical alarm fusion + FWER/FDR」真空。
- ⏳ **KS-2 数据**：用户线下办 PhysioNet CITI（2 周提前量，`reference/CITI_PHYSIONET_CHECKLIST.md`）→ 拿 MIMIC Waveform。
- 🔴 **KS-3 数据命门**（<1GPU·h，动笔前必跑）：多告警共触发是否真存在 + 复合 FAR 阈值族稳健性。GO→冲一区；翻→退腿 A。
- 全过 → planner 出 benchmark 矩阵 + coder 建 harness。

## 源材料位置
- 商业计划书（采信版）：`D:\商业计划书\慧脉守护商业计划书.pdf`（106 页；`商业计划书1.txt` 是旧换皮稿弃用）
- 系统 PPT：`D:\商业计划书\慧脉守护——病房智能体平台与服务机器人系统.pptx`（+ EN 版）
- 硬件 BOM + 技术路线：`D:\商业计划书\硬件.docx`
- 代码：`github.com/ZXZ12310304/wardlung-composs-v2`（WardLung Compass v2 demo，在线 `wardlungcompass.top`）
