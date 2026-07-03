# KS-3 数据命门 kill-shot — 预热报告（2026-07-02，主线真跑）

> 服务 WardAgentBench 候选 B 立项前数据命门验证。**结论：核心命门 Q1 初步 GO，立项-killing 的「结构性不存在」风险已退。** 数字全为主线真跑（15 条 mimic3wdb matched numerics record），可 Bash 核 `cotrigger_stats.csv`。判据见 `02_ACCEPTANCE.md` § KS-3。

## 0. 数据可达性（颠覆 KS-2 假设）
`00_check_access.py` 实跑确认三库**全 Open Access，不需 CITI**：
- `mimic3wdb/1.0` = ODbL ✅ | `mimic3wdb-matched/1.0` = ODbL ✅ | `challenge-2015/1.0.0` = ODC-BY ✅
- **→ 整个命门 + benchmark 主体现在就能跑，CITI 只在想要结构化 EHR 临床结局时才需**。原「MIMIC 需 CITI 2 周提前量」假设作废（已改 datasets.json）。

## 1. Q1 核心命门（多告警共触发是否真存在+相关）— ✅ 初步 GO
15 条 matched numerics record × 3 阈值族，共触发窗宽 30s。

| 阈值族 | 共触发窗占比 | 有共触发的 record | ge2-alarm bins |
|---|---|---|---|
| conservative | 2.76% | 6/15 | 1707 |
| **default** | **3.32%** | **11/15 (73%)** | 2102 |
| liberal | 4.65% | 13/15 (87%) | 3569 |

**告警对相关（default，phi 中位）**：HR\|RESP **0.41**(n=6) / ABPsys\|SpO2 **0.39**(n=3) / ABPsys\|RESP 0.11 / HR\|SpO2 0.12；17/33 对 phi>0.1，最高至 0.86-0.96。

**判读**：
- 共触发**常见非罕见**（多数病人出现，随阈值松紧单调 6→11→13/15，行为合理）。
- 告警**正相关/依赖**（多对中等相关）→ **正是承重前提**：alarms 依赖 → naive 独立 FDR/Bonferroni 失效 → e-value 依赖稳健联合校准有正当动机。
- **不是 [[delta_statetrack]]/[[nca-phasemap]]「结构性不存在」坑** —— 现象真实、可派生、可复现。

## 2. Q3 单告警反证 — ✅ by-design（不烧带宽）
PhysioNet 2015 Challenge 官方设计 = 每 record **单一**致命心律失常告警、onset 固定 300s、跨段分布不共触发（AAMI EC13，见 `alarm_thresholds.py` 引证）。→ 单告警数据**结构上无法**供共触发标注，锁死「共触发只能从多体征波形派生」结论。`00` 已实拉 challenge-2015 record a103l 证可读。

## 3. Q2 复合 FAR 稳健性 — ⏳ 待阈值锁定后跑
`03_compound_far_robustness.py` 就绪，但**阈值全占位 TODO**（未拿 Chromik et al. 确切阈值表）。复合 FAR 绝对值须待阈值锁定 + 弱结局代理定义后才定量。Q1「存在+相关」对阈值不敏感（3 族一致），不受影响。

## 4. 立项裁决
- **核心命门（方向能不能做）= 过**：共触发现象真实、常见、正相关，公开数据可派生复现，无需 CITI。**立项后做不出来的结构性风险已退。**
- **仍需补（非 blocker，执行细化）**：① researcher 查 Chromik/官方监护默认阈值替换占位 ② 扩 30-50 record 出稳定数 ③ 定弱结局代理跑 Q2 ④ e-value 联合校准方法实现。
- **诚实边界**：N=15 firm 但非终值；阈值占位；phi 为 within-record；弱结局代理非专家金标（R8 稿中声明）。

## 复现
```
python 00_check_access.py
python 02_mimic3wdb_cotrigger_probe.py --records records.txt --limit 15
# 数字核: cotrigger_stats.csv (45 行 = 15 rec × 3 族)
```
真源 `.portfolio/datasets.json` → `wardagent_alarm`。
