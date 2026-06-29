# 给团队的索取清单 —— 解 30 工具的 2 个团队侧 blocker

> 服务 QuantImmuBench §工具部署补满 30，lever=解「需团队提供才能补的工具槽」。2026-06-29 攻坚清单的一部分（不降级，逐个解 blocker）。
> 用法：余嘉转给袁老师 / 徐伊琳组。两项拿到即各补 1 槽（呈递 P6 MAAP + 免疫原 I18 内部 Inference）。

---

## 1. MAAP 确切全称 + 官方源（→ 呈递槽 P6）

**现状**：袁老师大纲 §2.2 表 2 把 **MAAP** 列在呈递/binding 类（§3.2 与 netMHCpan Aff/BA/EL 并列「结合/亲和力类→要聚合」）。但 researcher 两轮多源全检（WebSearch + GitHub repo 搜索 + 学术库）**零命中**——"MAAP" 在生信领域所有命中都是无关工具（基因组指纹 MAAP / 微阵列 MAAPster / NASA 平台等），无任何叫 MAAP 的肽-HLA 提呈/binding 预测器。大纲只给缩写无引用，本地 LOG 已两次标记此 TODO。

**请提供**（任一即可定位）：
- MAAP 的**确切全称**（缩写展开）
- 原始**文献 DOI** 或 **官方 repo URL**

**消歧候选**（仅供确认指向，请勿默认）：是否实为 ① MHCflurry 的 presentation score (PS) 别名、② MARIA（MHC-II 提呈，Stanford）、③ 某 NetMHC 变体的笔误？

**拿到后**：余嘉按官方源部署，补呈递 P6。

---

## 2. 内部 Inference 8-class 源码 / 接口（→ 免疫原槽 I18）

**现状**：袁老师大纲 §3.1 直接引用其数（Inference class_2/3 突变级 Spearman +0.31），§3.2 归「概率类→取最强」。属团队**内部工具**，源码在徐伊琳 QuantImmu 框架组，本地未确认接口，无法自行接入。

**请提供**（徐伊琳组）：
- Inference 8-class 的**推理入口**（脚本/CLI/函数签名）
- **输入格式**（肽+HLA？还是已 build 好的特征矩阵？）
- **输出**（class_0..7 八列概率？分数列名 + 方向）
- 预训练**权重**位置（HPC 路径或文件）

**拿到后**：余嘉按接口喂 DS2 数据出 class_0..7 列，补免疫原 I18，对齐大纲 §3.1 表 5 引用。

---

## 3. DeepNeo v1 代码+权重 —— 发邮件给原作者（→ 免疫原槽 I17，余嘉自发）

**现状**：DeepNeo（NAR 2023，双输出 MHC binding + T cell reactivity）抢救路径全穷尽——原 repo 404、Wayback 唯一快照是代码提交前空壳、无 fork/无第三方 deposit、webserver 域名已出售。唯一兜底=向通讯作者索取。

**发邮件**：Jung Kyoon Choi（KAIST Bio and Brain Engineering）**jungkyoon@kaist.ac.kr**（发前用 PMC10320182 full text 再核拼写），索 **DeepNeo v1 源码 + 预训练权重**。回复不确定 → I17 标 BLOCKED-待作者回信，并行用替代工具补位不空等。

---

## 附：其余 blocker 余嘉本窗自攻（不需团队）
- netMHCpan Aff/EL 独立列（HPC re-run，本窗）· TransHLA/MHCnuggets/ImmugenX 部署（许可自由，本窗）· Seq2Neo 解 netCTLpan · NeoaPred 解 HPC job · NetMHCstabpan 解 glibc 容器 · DeepNeo 试 Wayback 抢救。
- DTU 系工具（netmhcpan_ba/Aff/EL、ICERFIRE、NetTepi、TSCAPE）发表数字前需 **DTU 书面同意** → 袁老师拍板（投稿阶段）。
