# FEASIBILITY_REPORT — WardAgentBench reframe 可行性命门（2026-07-02 主线真跑）

> 数字真源 = `feasibility_result.csv`（274 行）/ `feasibility_summary.csv` / `agent_decisions.csv`（548 行）。可 Bash 核。

## 0. 管道可行性 ✅ 证通
真实 mimic3wdb-matched numerics（HR/SpO2/RR/ABP，开放**无需 CITI**）→ 切窗 30min → partial-NEWS2 指南 D*（`guideline.py`，RCP 2017 阈值，确定函数**非 LLM**）→ A/B 场景（`build_scenarios.py`，家属信号非循环锚下一窗真值升级态）→ Qwen2.5-3B-Instruct 4-bit 本机 8GB 推理（`run_agent.py`）→ 结构化精确匹配打分（`score.py`）。端到端跑通，548 决策 parse_ok 548/548。**管道是可复现硬资产。**

## 1. 命门结果（真 Qwen2.5-3B，274 场景）= 方向性 NO-GO
| 指标 | A 医生中心单流 | B 四角色分布 |
|---|---|---|
| escalate 正确率 | 0.507 | 0.507 |
| route 正确率 | 0.562 | 0.303 |
| A对B错（分布致败）| 40 | |
| A错B对（分布反帮）| 40 | |
| B 失败子类 | dropped_concern 8 / integration 32 | |

**判读**：
- escalate A=B → 分布不影响核心升级判断。
- **A对B错 40 = A错B对 40（对称）** → 分布=加噪声非承重信号；若四角色真揭示结构性失败类应**不对称**（B 系统性栽在 A 拿对的一类）。
- route B 更差纯「分布更难」，非新失败类（reviewer 会说 obvious）。
- dropped_concern 仅 8 → 家属/护士早期信号轴**被设计欠采样**（concern 注入率低），唯一未干净测的窄缝。

**裁决**：四角色协同作为**被打分的能力**不承重 → 实证坐实 theorist 预测（只剩多模态升级退化刻画）→ **天花板 workshop/D&B，多角色=背景板，够不到一作扛旗一区**。

## 2. 诚实边界 / 未死窄缝
- 单模型（Qwen-3B 弱模型）；换强模型/MedGemma 绝对精度会变，但 A/B **对称性**结论大概率稳（结构性非能力性）。
- 家属/护士「唯一早期信号」轴欠采样（8 例）——要救需**过采样**该场景专测；期望=窄 claim，大概率仍 workshop。
- rank_flip_guard 锚不变性检验（`rank_flip_guard.py`）**未跑**（命门已 NO-GO，无需）。
- partial-NEWS2 缺体温/意识/吸氧 3 参数，系统性低估 full NEWS2；A/B 同 D* 对比仍有效。

## 3. 复现
```
python build_scenarios.py --limit 8 --agg median
python run_agent.py --backend medgemma --model-id Qwen/Qwen2.5-3B-Instruct --load-4bit 1
python score.py
```
真源 `.portfolio/datasets.json` → `wardagent_alarm`（mimic3wdb 开放）。
