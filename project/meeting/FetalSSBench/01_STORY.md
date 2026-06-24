# FetalSSBench — STORY（反跑偏主文）

## 核心 Claim（一句话，承重）
**胎儿/产科超声半监督分割缺统一跨任务评测；本文建首个跨 3 数据集 × 5 标注比例 × 5 方法的统一 benchmark，揭示标注效率曲线、排名稳定性与结构难度不对称三个可报告规律，并给一个自适应置信阈值小增量稳定提升低标注区。**

不靠 radical novelty 取胜——靠**统一评测协议 + 实证规律 + 实用小增量**（benchmark+小增量形，对齐 ACCV CORE-B）。

## 命门假设（最先证伪，已部分验）
- H1（已 G5 验 GRAY-PASS）：不同半监督方法在不同标注比例下有**可报告的曲线结构**（效率曲线/收益递减/排名变化）——PSFHS 上已见单调曲线+MT 收益递减+PS/FH 不对称。
- H2（待正式验）：低标注比例(1/2%)区间 SSL headroom 大，方法 spread 更显著（pilot 显示 5% 才 1%，更低比例该更大）。
- H3（待验）：自适应阈值在低标注/难结构稳定提升，不只单数据集偶然。

> 命门软（即便排名不洗牌，"哪方法低标注最稳"本身有用）——这是 B 族优点，不押未验大胆前提。

## 章节弧
1. **Intro**：胎儿超声标注昂贵→半监督关键；但现有评测碎片化（各选各数据/比例/seed，ProPL 不含 PSFHS/FUGC，FUGC 单任务）→ 缺统一 benchmark。
2. **Related**：半监督医学分割(MT/CPS/UAMT/FixMatch)、胎儿超声分割(CMIS/PSFHS/HC18/FUGC)、标注效率研究。
3. **Benchmark 设计**：3 数据集 × 5 比例 × 5 方法 × 多 seed，统一 split/协议/评估，held-out 不泄漏。
4. **小增量**：自适应置信阈值，机理 + 实现。
5. **实验/发现**：效率曲线、排名稳定性(Kendall-τ)、PS/FH 难度不对称、自适应阈值增益、统计检验(95%CI/Wilcoxon)。
6. **Conclusion**：实用指南(临床标注决策) + 局限。

## 防御写法 R-rules
- R1：所有数字 Bash/Grep 核 csv，入 tex 前过 verifier；禁 Read 看数据编造。
- R2：held-out test 固定 seed，绝不混训练/无标注池；汇报前确认是 held-out。
- R3：半监督方法用 SSL4MIS 官方实现，超参标来源；查不到标 TODO。
- R4：spread 薄是诚实写"方法间差异小、SSL 增益集中低标注/难结构"，不夸大；负/弱结果照报。
- R5：不声称 SOTA/方法 novelty——定位 benchmark+实用小增量。
- R6：FUGC 需申请，拿不到则诚实写"双数据集"，不假装有。
