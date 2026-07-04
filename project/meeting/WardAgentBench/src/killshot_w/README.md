# killshot_w — 路 W' $5 kill-shot harness

**服务**：WardAgentBench 路 W' 的 $5 kill-shot。
**§/lever**：验证「前沿 MLLM 读**原始生理波形**能否判 ICU 警报真假」是否失败 →
建立「前沿 MLLM 在安全攸关警报判真假上**失败**」的初步证据。

**数据**：PhysioNet/CinC Challenge 2015（Reducing False Arrhythmia Alarms in the ICU）。
每条记录 = ICU 生理波形（ECG II/V、ABP、PLETH、RESP，250Hz，报警发生在段内第 300s），
`.hea` 注释含**报警类型**（Asystole / Bradycardia / Tachycardia / Ventricular_Tachycardia /
Ventricular_Flutter_Fib）+ **专家判定 True/False**（客观金标）。**开放获取，免 CITI**
（真源 `.portfolio/datasets.json` → `wardagent_alarm`）。

## 管道（配置驱动，单一真源 `config.py`）

| 脚本 | 干什么 | 联网 | 花 API |
|---|---|---|---|
| `download_data.py` | 拉跨 5 类均衡、真假都有的 ~N=30 条 + 写金标 `manifest.csv` | 是(PhysioNet) | 否 |
| `build_inputs.py` | 每条取报警前 16s：文本表征 A（数字序列化）+ 图像表征 B（PNG） | 否 | 否 |
| `run_models.py` | 对每 (记录×表征×模型) 发 rubric prompt，判 TRUE/FALSE | 是 | **是** |
| `score.py` | join 金标 → 总/逐类/逐表征/逐模型准确率 + naive 基线 + 对照图 | 否 | 否 |

## 主线运行顺序（我不跑，交主线）

```
# 1) 先看均衡不下载（快、免流量）
python download_data.py --no-download     # 检查每类 true/false 分布是否合理
python download_data.py                    # 满意后真下 .mat 到 data/challenge2015_killshot/

# 2) 构建输入（离线）；先烟测 2 条看文本/图对不对
python build_inputs.py --limit 2
python build_inputs.py

# 3) 预演（不花 API，校验输入齐 + 预估调用数），再真发
python run_models.py --dry-run
python run_models.py                        # 缺 key 的 provider 自动跳过并打印

# 4) 打分出图
python score.py
```

## 环境变量（provider key，缺的自动跳过）
- `OPENAI_API_KEY`（GPT-4o / GPT-5）
- `GEMINI_API_KEY`（Gemini）
- `ANTHROPIC_API_KEY`（Claude）

## 预估 API 调用数（对 cost 硬顶）
N(30) × 表征(2: text+image) × 可用模型数 M。
- M=4（4 个 key 全有）→ 240 次；`config.MAX_API_CALLS=300` 覆盖 + buffer。
- M=2 → 120 次（下调 `MAX_API_CALLS` 到 ~150 更省心）。
达 `MAX_API_CALLS` 即停；断点续跑（`raw_calls.jsonl` 已完成的三元组跳过），不重复花钱。

## 首跑必核（TODO，写码时无法运行核实，标此待主线）
1. `wfdb.rdheader(rec).comments` 的**确切内容**（告警类型 + True/False 的拼写/是否合并行）
   → `download_data.parse_comments` 的匹配是否命中（打印一条真实 comments 核对）。
2. `wfdb.dl_database(PN_DIR, ...)` 的 db_dir 路径是否吃 `challenge-2015/1.0.0/training`
   （不行退逐条 `rdrecord+wrsamp`，见 `config.py` PN_DIR TODO）。
3. `header.sig_name` 的确切导联拼写 → 补全 `config.ECG_LEAD_PRIORITY` /
   `PULSATILE_LEAD_PRIORITY`（若 II 常缺，调主导联）。
4. 各 `config.MODELS.model_id` 快照名 + 推理模型（GPT-5）参数名，官方文档核对。

## 输出
- `data/challenge2015_killshot/manifest.csv` — 金标（record_id, alarm_type, expert_label…）
- `inputs/<record>_text.txt`、`inputs/<record>.png`、`inputs/inputs_manifest.csv`
- `results/raw_calls.jsonl` — 每次调用原始返回全文
- `results/killshot_results.csv` — 长表（逐调用 correct + 返回摘录）
- `results/summary.csv` — 总/逐类/逐表征/逐模型 + naive + 引用参照线
- `results/killshot_accuracy.png` — 对照条形图（naive / 0.8139 / 0.96 三参照线）

## 红线遵守
- 金标 = 官方 True/False（非派生），可 Bash 核（R1）；数字入稿前过 verifier。
- **绝不把专家 True/False 金标写进 prompt / 图**（只给报警类型）——评估集不可泄漏。
- 参照线 0.8139（Challenge 冠军，加权评分口径）/ 0.96（VTaC CNN）= **引用值非自测**，
  图注 + summary 已标口径不同（R2）。
- 固定 seed 采样可复现（R3）。复现零偏离、超参查不到标 TODO（R4）。
