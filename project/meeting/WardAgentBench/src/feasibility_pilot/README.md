# feasibility_pilot — WardAgentBench reframe 可行性命门 kill-shot

**服务对象**：慧脉守护 reframe「多角色病房 agent 模拟 benchmark」立项前的**可行性命门**。
**要证的命门（skeptic + theorist 定）**：四角色信号**分布**是否制造一类
「医生中心单流 agent **结构上表达不出**、且能用**公开指南**打分」的失败？
- **是** → 差异化承重成立，可立项。
- **否** → 分布不承重，退 workshop。

> 这是 kill-shot 可行性验证，**不是完整 benchmark**：小样本、partial-NEWS2 子集、单模型，
> 只为回答「值不值得立项」。绝不当完整实验结果汇报。

---

## 严格护栏（theorist 定，防循环 / 防 artifact）
1. **D\* 只能是公开指南 NEWS2 的确定函数**（`guideline.py`），**绝不用 LLM 生成 D\***。
2. **病人状态 seed 自真实 mimic3wdb numerics**（HR/SpO2/ABPsys/RESP），复用 `ks3_pilot` 加载器。
3. 缺的 NEWS2 参数（体温/意识/吸氧）**标 TODO 缺失**，只算**可算子集** = partial-NEWS2，
   诚实声明是子集（系统性低估 full NEWS2，但 A/B 同 D\* 对比有效）。
4. **家属/护士早期担忧信号非循环**：锚**真实未来窗**的指南态（下一窗将升级才注入），非作者拍脑袋。
5. agent 决策**结构化离散输出**（escalate/route_to_role/timing_bin），**精确匹配** D\* 打分，
   **不用 LLM 判自由文本**。

---

## 跑法顺序（主线跑；coder 只写不跑）

```bash
cd project/meeting/WardAgentBench/src/feasibility_pilot
pip install -r requirements.txt          # torch/bitsandbytes 按本机 CUDA 装

# 1) 造场景（真实 numerics 切窗 + D* 真值 + A/B 两条件 prompt）
#    在线读（wfdb 只读 mimic3wdb-matched）或 --local-dir 指本地已下目录
python build_scenarios.py --records ../ks3_pilot/records.txt --limit 25 --window-min 30 --agg median
#    先烟测管道：
python build_scenarios.py --smoke 1

# 2) 先用 mock 后端跑通管道（不下模型，验 end-to-end）
python run_agent.py --backend mock --smoke 1
python run_agent.py --backend mock        # 全量 mock（chance baseline）

# 3) 真模型（命门信号来源）—— 主线在有 GPU 时跑
python run_agent.py --backend medgemma --load-4bit 1     # 本机 8GB / CPU-fallback
#    显存不够 → --device cpu（慢）或 HPC 单卡

# 4) 打分 + 命门判据
python score.py

# 5) 锚不变性检验（防作者 artifact）
python rank_flip_guard.py generate --n-variants 5
python run_agent.py --scenarios scenarios_variants.jsonl --backend medgemma --out agent_decisions_variants.csv
python rank_flip_guard.py compare
```

---

## 每脚本作用 + 产物

| 脚本 | 回答 | 输入 | 输出 |
|---|---|---|---|
| `guideline.py` | D\* 生成器（NEWS2 确定函数，非 LLM） | 窗聚合体征 dict | 无 CSV，被 import；`ground_truth()` 返 escalate/route/timing |
| `build_scenarios.py` | 造 A/B 两条件场景 + 真值标签 | `records.txt` 真实 numerics | `scenarios.jsonl` |
| `run_agent.py` | agent A/B 结构化决策 | `scenarios.jsonl` | `agent_decisions.csv` |
| `score.py` | 精确匹配 vs D\*，B 特有失败类 | scenarios + decisions | `feasibility_result.csv` + `feasibility_summary.csv` |
| `rank_flip_guard.py` | 锚不变性（换措辞是否翻） | scenarios / 变体 decisions | `scenarios_variants.jsonl` + `flip_guard_result.csv` |

**命门读数**：`score.py` 打印 `A对B错(分布致败)` 计数 + 失败子类型（misroute / dropped_concern /
integration）。B 存在 A 无的、指南可打分失败 + 锚不变性 PASS → 方向性 GO。

---

## 数据 / 模型下载指引
- **数据**：mimic3wdb-matched numerics，`records.txt`（ks3_pilot 已备清单）。在线 `wfdb` 只读
  `mimic3wdb-matched/1.0`（需 PhysioNet CITI 认证访问 matched 子集；`ks3_pilot/00_check_access.py`
  判开放性）。或 `--local-dir` 指本地已 `wget` 目录。
- **模型**：`google/medgemma-4b-it`（HF Hub，需同意 Google Health AI 许可 + `huggingface-cli login`）。
  4-bit 量化 ≈ 3-4GB 显存，本机 RTX4070 8GB 可跑；CPU-fallback 慢但可通。

## 阈值来源（红线：查官方源标出处）
NEWS2 评分表 + 升级协议 = **RCP, "National Early Warning Score (NEWS) 2", 2017**
（`guideline.py` 每函数标 Chart 1 / Chart 3 出处）。
⚠️ TODO(researcher): 复核官方 chart 边界行（SpO2 Scale1/2、单参=3 触发口径）与最新 RCP 版一致后
去除 `guideline.py` 中 TODO 标记。
