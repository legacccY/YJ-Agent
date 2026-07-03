# KS-3 命门 kill-shot Pilot（WardAgentBench 候选 B）

**目的**：立项前证「多告警共触发 + 复合误报」在公开 ICU 波形数据**真实存在**（非自造 artifact）。
三问全过 → GO 冲一区（JBHI/npj DM）；任一翻 → 退腿 A 开源 + SOP。判据见 `../../02_ACCEPTANCE.md` § KS-3。

> ⚠️ **coder 只交代码，不跑任何代码**。以下命令**主线串行跑**（CPU 即可，<1 GPU·h）。
> 所有产出 csv 让 verifier / Bash 可核（R1）。告警 + 真/假为**派生非专家标注**（R8），稿中必声明。

## 依赖
```
pip install -r requirements.txt   # wfdb + numpy + pandas，CPU
```

## 数据下载指引
- **PhysioNet 2015 Challenge（Q3，开放）**：
  `wget -r -N -c -np https://physionet.org/files/challenge-2015/1.0.0/training/`
  或 `wfdb` 在线只读。落到 `<repo>/data/external/challenge-2015/training/`。
- **MIMIC-III Waveform Matched（Q1/Q2）**：`https://physionet.org/content/mimic3wdb-matched/1.0/`
  先跑 `00_check_access.py` 确认访问状态（coder 静态探针初判 **Open Access 无需 CITI**，主线复核）。
  开放 → `wfdb` 在线只读（`pn_dir='mimic3wdb-matched/1.0'`）或 `wget` 下子集；
  gated → 走 CITI（`../../reference/CITI_PHYSIONET_CHECKLIST.md`），本轮降级只跑 Q3。

## 跑法（主线，按顺序）
```bash
# STEP 0 数据可达性（先跑，决定 Q1 能否现在验）
python 00_check_access.py                      # -> access_report.json

# Q3 反证 + 单告警 FAR baseline（P2015，开放数据）
python 01_physionet2015_baseline.py --data-dir <repo>/data/external/challenge-2015/training
#   -> p2015_baseline.csv, p2015_far_summary.csv

# Q1 核心命门：共触发频率 + 相关（matched 开放才能跑）
python 02_mimic3wdb_cotrigger_probe.py --limit 20          # 在线只读，前 20 条
#   或 --records recs.txt / --local-dir <本地matched目录>
#   -> cotrigger_stats.csv

# Q2 复合 FAR 跨阈值族稳健性 + C2 独立可加基线（弱代理定真假）
python 03_compound_far_robustness.py --limit 20
#   -> compound_far.csv（含 expected_compound_far_indep / observed_over_expected_ratio）

# C3 依赖是否让 naive 独立合并检验失效（半合成 pilot demo）
python 04_dependence_demo.py --records records.txt --limit 20   # 从真实告警标定 ρ/K
#   或 python 04_dependence_demo.py --rho 0.4 --k 3             # 直接用 report phi 缺省
#   -> dependence_demo.csv

# 烟测（最小验证）：
python 02_mimic3wdb_cotrigger_probe.py --smoke 1
python 03_compound_far_robustness.py --smoke 1
python 04_dependence_demo.py --smoke 1                          # 纯数值 MC，无需数据
```
跑完把数字填进 `KS3_PILOT_REPORT.md` 骨架的判据表。

## 每个脚本作用
| 脚本 | 回答 | 输入 | 输出 |
|---|---|---|---|
| `00_check_access.py` | 前置门 | PhysioNet HTTP + wfdb 探针 | `access_report.json` |
| `01_physionet2015_baseline.py` | **Q3** + 单告警 FAR baseline | P2015 training `.hea` | `p2015_baseline.csv`, `p2015_far_summary.csv` |
| `02_mimic3wdb_cotrigger_probe.py` | **Q1**（共触发频率+相关） | MIMIC-III matched numerics | `cotrigger_stats.csv` |
| `03_compound_far_robustness.py` | **Q2**（复合 FAR 稳健）+ **命门 C2**（依赖是否致超额复合误报：观测 vs 独立可加基线，ratio>1=GO） | 同上 | `compound_far.csv` |
| `04_dependence_demo.py` | **命门 C3**（依赖是否让 naive 独立合并检验失效：Fisher vs e-value vs Bonferroni 经验 Type-I；半合成 MC，ρ/K 取自真实告警） | 真实告警标定 ρ/K（可选）或缺省 | `dependence_demo.csv` |
| `alarm_thresholds.py` | 阈值/告警定义配置（⚠️占位 TODO） | — | 被 import |
| `alarm_derive.py` | 波形→告警事件派生（共用） | — | 被 import |

## ⚠️ 红线 / 待办 TODO
- **阈值禁臆想**：`alarm_thresholds.py` 的体征阈值（HR/SpO2/ABP/RESP 上下限 + 持续秒数 +
  共触发窗宽 + 弱代理 persist）**全是占位 TODO**，需核 **Chromik et al. "Extracting Alarm
  Events from the MIMIC-III Clinical Database"** / 官方监护默认限后替换。锁定前绝对 FAR 只作方向参考。
- **PhysioNet 2015 五类告警定义**已用官方 ANSI/AAMI EC13（权威，非 TODO）。
- **真/假为弱代理派生**（持续紊乱 vs 短暂 artifact），非专家/结局金标 → R8 必声明；
  完整结局代理需 matched 临床结局（若仍 gated 则标需 CITI）。
- **不泄漏**：本 pilot 为描述性统计，无 train/test 划分；正式 benchmark 需切窗同病人不跨（R3）。
