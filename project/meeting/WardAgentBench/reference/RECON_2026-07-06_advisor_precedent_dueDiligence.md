# WardAgentBench 尽调报告 · 导师画像 × 本科先例 × 资源链

> **日期**：2026-07-06
> **目的**：为「明天与王水花面谈慧脉守护科研转化」做资源尽调 —— 王水花有没有类似方向的文章、XJTLU 有没有本科一作先例、AI4Health/孟佳/Moraros/苏大附二院这条链的真实成色。
> **方法**：3 个 researcher 编队并行联网核实（王水花发表画像 / 本科一作先例 / 资源链），全部结论带 URL，查不到标 TODO 不臆想。
> **一句话**：**平台层是真的（实验室真、王水花 Theme Leader 真、附二院三甲真），但对口层几乎全是空的** —— 王水花不做这个方向、本科先例走的是别的路且跟你的人无关、附二院公开需求不含病房监测。这不否定 pivot，但**改变了你明天该问什么、该期待什么**。

---

## 〇、执行摘要（一页看懂）

| 尽调问题 | 结论 | 成色 |
|---|---|---|
| 王水花有没有类似（LLM-agent/告警/部署/benchmark）的文章？ | **几乎没有**。她是静态医学影像 CNN 分类/分割 + 信息融合的连续高被引学者，与慧脉四大支柱（LLM-agent / 生理波形告警 / 真实部署 usability / benchmark 构建）**基本零交集** | 🔴 跨域挂名背书，非对口内行 |
| XJTLU 有本科一作医疗 AI 先例吗？ | **有且仅有 1 例**（Liu Yiheng, 2025, CSBJ, Q2）。但它是**方法+应用**型、通讯是黄夏、**跟王水花/孟佳/Moraros 都不是合著** | 🟡 证明「本科一作医疗 AI 可行」但不背书你这条路 |
| 有走 benchmark/deployment 路的本科先例吗？ | **没找到**（两轮零命中） | 🔴 你这条路在校内无先例可援引 |
| AI4Health 实验室能挂靠吗？ | **能**。实验室真实（2024 成立、Moraros 主任），**王水花在 Theme Leaders 名单** = 最强正面支点 | 🟢 平台硬证据成立 |
| Moraros / 孟佳能给方法支撑吗？ | **不能**。二人做公共卫生/城市交通AI/生信 m6A，非病房 AI，只提供平台+背书+行政力 | 🟡 背书可用，方法 cover 不了 |
| 苏大附二院对口吗？ | 三甲真、伦理委真、2024 办过 AI+医疗对接会；**但公开 AI 需求清单不含病房/ICU 监测**；XJTLU×附二院既有合作**查无实据** | 🟡 场景在但对口性和通道待你线下核 |

**对明天的一句话结论**：这场会不是「让内行导师审我的方向」（她审不了核心），而是「**用她的实验室席位 + 通讯声望 + 医院人情，把我一个人做得出来的 benchmark 升级成有真实落地背书的东西**」。你要主导技术、她提供平台与信誉——把预期摆正，问题就清楚了。

---

## 一、王水花发表画像：跨域背书，非对口内行

### 1.1 她是谁
- 西交利物浦生物科学系副教授，**连续多年 Clarivate 全球高被引**（2019、2022–2025），Stanford Top 2%，《Information Fusion》副主编。
- 引用量级：Google Scholar h-index ≈ **85–96**、引用 **2.4万–3万**（两处口径不同取范围）。量级很高，声望是真的。
- 来源：https://scholar.xjtlu.edu.cn/en/persons/ShuihuaWang ｜ https://research.com/u/shuihua-wang ｜ https://www.xjtlu.edu.cn/en/news/2025/11/dr-shuihua-wang-selected-once-again-for-the-global-2025-highly-cited-researchers-list

### 1.2 她做什么（代表作）
主场 = **静态医学影像的 CNN 分类/分割 + 信息融合 + 优化算法**，疾病域覆盖阿尔茨海默（脑 MRI）、COVID（胸片/CT）、脑肿瘤、胎儿脑超声、乳腺。

| 代表作 | 年 | venue | 位次 |
|---|---|---|---|
| 8-layer CNN 分类阿尔茨海默 | 2018 | J. Medical Systems | **一作** |
| A review of deep learning on medical image analysis | 2021 | Mobile Networks & Appl. | 第3 |
| Advances in multimodal data fusion in neuroimaging | 2020 | Information Fusion | 合著 |
| CMIS: 胎儿脑超声实例分割 | 2026 | IEEE JBHI | 资深/通讯（推定） |
| Semi-CLMT: 半监督医学影像分割 | 近期 | — | 资深（推定） |

来源：https://research.com/u/shuihua-wang ｜ https://scholar.xjtlu.edu.cn/en/publications/semi-clmt-a-semi-supervised-framework-for-medical-image-segmentat/

### 1.3 她离慧脉方向有多远（五问核验）
| 慧脉支柱 | 她做过吗 | 证据 |
|---|---|---|
| LLM / medical LLM / agent / 多智能体 | **NO**（XJTLU 页有"Generative AI"兴趣标签但无对应论文=意向非产出） | 定向检索零命中 |
| 临床部署 / usability / human factors / 医护访谈 | **NO** | 检索空手（TODO 人工复核） |
| benchmark / 数据集构建类论文 | **弱/NO**（在公开影像集上做方法，未见发布新数据集/benchmark） | 未找到发布类论文 |
| ICU / 生命体征 / 告警 / 波形 / 早预警 | **NO**（她的"sensor"=MRI/CT 影像非 ECG/PPG/ABP 波形） | 检索零命中 |
| 真实医院队列 + IRB | **NO 公开证据**（工作以公开影像数据集为主） | TODO 人工复核 |

补充：她曾在 Leicester **BHF 精准医学加速器**做研究员，语境沾"心血管"，但产出仍是影像 ML，非生命体征监测。来源：https://le.ac.uk/bhf-accelerator/people/previous-researchers/shuihua-wang

### 1.4 诚实定性
> **方向背书 = 跨域挂名（信誉/通讯可用）；方法背书 = 仅限通用 ML/DL 层；命门（告警融合 / LLM-agent / 部署人因）她 cover 不了。**

她能给你的**真实价值**：① 通用 ML 方法学把关 + 写作/投稿背书 ② 高被引通讯作者的声望与投稿信誉 ③ AI4Health 实验室席位 + 经费 + 医院人情通道。她**给不了**的：核心方法内审（agent/告警/部署这些她没做过）。→ 这些命门你得自己扛，或另找 ICU/临床信息学/LLM 领域的方法顾问补位。

---

## 二、XJTLU 本科一作先例：仅 1 例，且不背书你这条路

### 2.1 Liu Yiheng（唯一确证先例，精确信息）
| 项 | 内容 |
|---|---|
| 标题 | Random splicing assisted deep learning for breast cancer cell line classification via Raman spectroscopy |
| 期刊 / 年 | Computational and Structural Biotechnology Journal (CSBJ), 2025 |
| DOI | 10.1016/j.csbj.2025.05.051 |
| 作者 | **Yiheng Liu（本科一作）**, Junfeng Liu, Jiayi Wan, Hongke Hao, Guangxing Liu, **Xia Huang（黄夏，末位通讯）** |
| 学生身份 | 生物科学与生信系 **大四本科生** |
| 导师 | **黄夏（直接指导+通讯）**；John Moraros（院长）**仅背书露面、非作者** |
| 王水花/孟佳 | **均不在作者列表** |
| 孵化路径 | 2024 SURF 项目 → 2025 发表 |
| 贡献类型 | **方法改进（RS-CNN 数据增强）+ 应用**，非 benchmark、非 deployment |

来源：https://spj.science.org/doi/10.1016/j.csbj.2025.05.051 ｜ https://www.xjtlu.edu.cn/en/news/2025/06/xjtlu-undergraduate-developed-innovative-ai-diagnostic-tool

> ⚠️ **重要更正**：项目此前档案（pivot 报告）把这个先例记成「Moraros 背书的本科一作先例」暗示它能佐证你走 Moraros/王水花的路——**核实后不成立**。Moraros 不是作者，真正的通讯是黄夏；王水花、孟佳都没参与。这个先例只能证明「XJTLU 本科生发医疗 AI 一作**这件事本身**可行（有个例）」，**不能**证明「走王水花/Moraros 这条链能发」，也**不能**证明「benchmark/deployment 路本科能发」。

### 2.2 有没有第二例 / 更贴近你方向的先例
- **第二例本科一作医疗 AI 论文**：两轮检索**未找到确证**（搜到的 XJTLU AI/影像名字如 Gan Hong Seng、Jionglong Su 全是教职/研究员非本科生）。`TODO：需人工查 scholar.xjtlu.edu.cn 机构库 + 各系导师 Scholar 学生合著确认。`
- **走 LLM/agent/部署/benchmark 路的本科先例**：**零命中**。唯一先例是影像/光谱分类，与慧脉「多告警/多角色 benchmark」贡献形状不同类。

### 2.3 venue 档次含义
CSBJ = **JCR Q2（IF≈4.6）、中科院生物学 2 区、Gold OA（APC≈$2642）**，非顶会非一区。→ 校内唯一确证的本科一作先例走的是「**方法+应用 → 中档 Q2 OA 期刊**」路子。这跟你 pivot 后要投的 CHIL/JMIR HF/AMIA（健康 ML 专业 venue，HYPSM 认）**不是同一形状**——校内没有可直接援引的同路先例。

### 2.4 SURF 机制（可用的路径资产）
- SURF = 暑期本科生科研基金，学生在导师下做独立项目；2024 有 399 个项目。
- **它是 Liu Yiheng 论文的直接孵化通道**（SURF→发表官方叙事），但多数 SURF 止于海报，转一作论文是少数（仅 1 例确证）。
- `TODO：SURF 官方申请细则页 404，需人工找最新 URL 确认 eligibility/时长/资助额。`
- **给你的启发**：如果王水花愿带，走 SURF 立项是一条校内认可、有先例的正规孵化路径，可以在会上问她要不要走 SURF 挂这个项目。

---

## 三、资源链尽调：平台真、对口薄

### 3.1 AI4Health 苏州市重点实验室 —— 🟢 硬证据成立
- 官方名 **AI4Health Suzhou Key Laboratory**，理学院下，**2024 成立**，**主任确为 John Moraros**。
- Scope 原文含 *"personalized medicine, predictive analytics, healthcare delivery"* —— 与病房预测监测**沾边但未显式写 ICU/告警/生命体征**。
- **Theme Leaders 名单（逐字）**：Faez Khan、**Zhen Wei（魏振）**、Justin Fendos、**Shuihua Wang（王水花）**。
  - → **王水花在名单里 = 本项目最强正面支点**：你的导师本人就是这个校级 AI 医疗平台的 Theme Leader，论文挂靠该平台有合法身份。
  - **孟佳不在名单**（多次核实未出现）。
- 来源：https://www.xjtlu.edu.cn/en/study/departments/school-of-science/labs-and-spaces/suzhou-key-laboratory

### 3.2 John Moraros —— 🟡 平台/行政/背书，非 AI 实操
- MD/MPH/PhD，方向**公共卫生/流行病学/健康公平**。近作是城市交通 AI 决策支持 + m6A 生信 roadmap，**无医疗影像/临床监测/LLM/病房 AI 论文，无带学生发医疗 AI 一作记录**。
- → 他给的是**院长头衔 + 实验室平台 + 行政调动力 + 背书**，不是方法支撑。
- 来源：https://scholar.xjtlu.edu.cn/en/persons/JohnMoraros

### 3.3 孟佳 Jia Meng —— 🟡 生信系主任，非病房 AI
- 系主任、MIT/Broad 背景，方向 **RNA 表观转录组 m6A / 精准医疗 / 癌症疫苗 / 单细胞**，有"ML for biomedicine"子方向。H-index 35+、5440+ 引用、全球前 2%。
- 企业合作：2018 江苏"双创"×**苏州精准医疗**（证据存在但旧、且是测序方向非病房）。
- **不在 AI4Health Theme Leaders 名单**；本科生一作记录 = `TODO 未找到`；「川昕生物」= `TODO 无任何公开源，勿写入`。
- → 若拉他进来，价值是**统计/生信方法学 + 系主任调动力 + 通讯背书**，非病房监测方向对口。
- 来源：https://scholar.xjtlu.edu.cn/en/persons/JiaMeng ｜ https://www.xjtlu.edu.cn/en/departments/academic-departments/biological-sciences/staff/jia-meng

### 3.4 苏大附二院 —— 🟡 场景真、对口性与通道待核
- 苏州大学附属第二医院 = **三甲综合医院**（确认）。伦理委员会真实（2003 成立、第八届 15 委员，受理涉人生物医学研究；**AI 医疗是否受理页面未明说**）。
- **2024-05 确在该院办过「AI+医疗」应用场景对接会**，但公开的 AI 需求 = **智能导诊机器人 / 可穿戴 / 影像智能诊断 / 手术机器人 / 3D 建模** —— **不含「病房智能监护 / ICU 生命体征预警 / 多告警融合」**这类你正对口的方向（挂靠属间接推断非硬对口）。
- 苏州**市级** 2025 有「智能数字化重症监护系统」入选 AI 医疗器械揭榜，但**未指名附二院**。
- **XJTLU/王水花/理学院 × 苏大附二院既有合作**：`TODO 查无公开实据`。理学院有实体合作意向的是**十堰太和医院**（Moraros+孟佳 2025-01 访，谈联培/样本共享，**未涉医疗 AI/监测**）——太和≠附二院。
- 来源：https://www.sdfey.com/gfb/llwyh.html ｜ https://kxjst.jiangsu.gov.cn/art/2024/5/23/art_82538_11252026.html（现 404 待复验）｜ https://www.xjtlu.edu.cn/en/news/2025/01/xjtlu-school-of-science-visits-taihe-hospital

### 3.5 资源链诚实分档
| 节点 | 硬证据 | 薄弱/未证实 |
|---|---|---|
| AI4Health 实验室 | ✅ 真实、2024、Moraros 主任、王水花+魏振 Theme Leader | scope 未显式含病房/ICU |
| **王水花** | ✅ **Theme Leader + 高被引 + AI/ML 实操 = 本链最强支点** | 方向不对口（见 §1） |
| 魏振 Zhen Wei | ✅ Theme Leader | 是否参与本项目未核 |
| Moraros | ✅ 院长+主任头衔真 | ❌ 不做 AI/agent/监测 |
| 孟佳 | ✅ 系主任、生信、2018 企业合作 | ❌ 不在实验室名单；方向不对口；川昕/本科一作=TODO |
| 苏大附二院 | ✅ 三甲、伦理委真、办过 AI 对接会 | ⚠️ 公开需求不含病房监测；×XJTLU 合作=TODO |
| 医院通道 | ✅ 太和医院有实体基地意向 | ❌ 太和≠附二院，且未涉医疗 AI |

---

## 四、这对明天见面意味着什么（尽调 → 行动）

### 4.1 三个认知校正
1. **别指望王水花审你的核心方向**。她审不了 agent/告警/部署——这些是你的活。会上把她定位成「平台席位 + 通讯声望 + 医院人情 + 通用 ML 把关」，别浪费时间让她评判技术命门。
2. **本科先例只证明"可行"，不证明"你这条路可行"**。会上可以用 Liu Yiheng 佐证「XJTLU 本科一作医疗 AI 有先例」，但别夸张成「Moraros/王水花带出来的先例」（不实）。你走的是校内无先例的 benchmark/deployment 路——这既是风险也是**差异化卖点**（没人做过=空白）。
3. **附二院的"对口"是你要去落实的，不是现成的**。公开需求不含病房监测、既有合作查无实据——所以会上第一优先级就是问清「医院对接到底到哪一步、能不能落到具体科室的具体人」。

### 4.2 明天必问（按尽调结果重排优先级）
1. 🔴 **医院通道**：您对接苏大附二院到什么程度？能不能落到 ICU/心内/呼吸/神外某个**具体科室的某位医生**、帮我引荐？（尽调证实这是全链最空的一环，也是腿 2 生死点）
2. 🔴 **署名**：我想以**本科一作/主导**扛这篇（为直博）。您做通讯 + 通用 ML 把关，可行吗？要不要走 **SURF 立项**孵化（校内有先例路径）？
3. 🔴 **AI4Health 挂靠**：您是实验室 Theme Leader，这篇能不能挂靠 AI4Health？需不需要您跟 Moraros 那边提一句？
4. 🟠 **方法命门谁补**：核心的 agent/告警/部署方法学您这边不是主场，我们要不要拉一个懂 ICU/临床信息学或 LLM 的人补方法顾问？（诚实暴露,反而显专业）
5. 🟠 **孟佳**：要不要拉孟佳(系主任+统计/生信+调动力)？他方向不对口但背书和资源有用。
6. 🟢 **时间线/venue**：最小风险 IRB 在附二院大概多久？您对 CHIL/JMIR HF 这类健康 ML venue 熟不熟、觉得够不够撑直博？

### 4.3 措辞红线（别在会上说漏）
- 别说慧脉"已在医院真实部署/跑真实病例"——现在是 demo、零真实数据。
- 别把两院意向函说成"已获资源"；别说附二院"有病房监测需求"（公开清单没有）。
- 别把 Liu Yiheng 说成王水花/Moraros 的学生成果。
- MedQA69%/AUC 那些是底层开源模型文献值，不是你测的。

---

## 五、遗留 TODO（人工复核，别臆想）
1. 王水花是否真有部署/usability/真实医院队列论文（检索空手，中置信 NO，建议机构库人工复核）
2. XJTLU 第二个本科一作医疗 AI 先例（阴性结果非强证，建议 scholar.xjtlu.edu.cn 人工扫）
3. SURF 官方最新申请细则页（原页 404）
4. 孟佳带本科生一作记录 / 川昕生物合作（无公开源）
5. XJTLU/王水花 × 苏大附二院任何既有合作证据
6. 附二院是否公开征集过病房/ICU 监护需求（现有清单未含，江苏科技网原文页 404 待复验）
7. 附二院伦理委是否受理 AI 医疗研究

---

*本报告由 3 个 researcher 编队并行核实（2026-07-06），结论带 URL，数字/事实以官方源为准，标 TODO 处未一手确认勿越级引用。是明天面谈的尽调底稿，与 `REPORT_2026-07-04_pivot_strategy.md`（方向决策）互补——本报告负责"资源链到底几分真"，pivot 报告负责"方向往哪走"。*
