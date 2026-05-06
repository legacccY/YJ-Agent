---
name: run-experiment
description: 多 agent 实验运行流水线：pytest 测试 → Haiku 启动训练 → Monitor 实时可视化 → 每 270 秒自动检查 → 小问题自动修复，大问题上报
---

# 用法：/loop /run-experiment <script_path> [config_path]
# 重要：必须用 /loop 前缀触发，否则 ScheduleWakeup 无法工作

你是 VisiSkin-Agent 实验运行流水线的编排者。按以下 STEP 顺序执行。

---

## STEP 0：读状态，判断当前处于哪个阶段

首先，执行 `date` 获取当前北京时间。

读取 `D:/YJ-Agent/log/experiment_state.json`：
- 文件不存在 或 `status == "idle"` → 执行 STEP 1（首次启动）
- `status == "running"` → 执行 STEP 3（检查循环，跳过测试）
- `status == "done"` → 打印完成摘要，**不调用 ScheduleWakeup**，loop 自然结束
- `status == "error_major"` → 打印错误详情和修复建议，**不调用 ScheduleWakeup**，等待用户

解析 $ARGUMENTS：
- `$1` = 训练脚本路径（必填），如 `src/train_visiscore.py`
- `$2`（可选）= 配置文件路径，如 `configs/visiscore.yaml`；不填则脚本自行使用默认配置

**断点续训检测**：读取 state.json 后，额外检查 `checkpoint.last_path` 字段：
- 字段存在且对应文件实际存在（用 Bash `ls <path>` 验证）→ 标记为续训模式，STEP 2 启动时自动带 `--resume <last_path>`
- 字段为 null 或文件不存在 → 全新训练，不加 `--resume`

---

## STEP 1：测试阶段（主会话 Bash 执行）

在项目目录下执行：
```
python -m pytest tests/ -v -x --timeout=60 2>&1
```
- `-x`：遇到第一个失败立即停止
- `--timeout=60`：单测最长 60 秒，防止卡死

判断：
- 全部通过 → 打印「测试通过（N/N），准备启动训练」→ 继续 STEP 2
- 有失败 → 展示失败的测试名 + 错误摘要，询问用户「pytest 有 N 个测试失败，是否继续跑实验？(y/n)」
  - 用户选 n → 停止，不调 ScheduleWakeup
  - 用户选 y → 继续 STEP 2

如果 `tests/` 目录不存在，跳过测试直接进入 STEP 2，打印「未找到 tests/ 目录，跳过测试」。

---

## STEP 2：启动训练（Haiku agent 执行）

将以下任务完整交给 `Agent(model="haiku")`：

```
任务：启动训练进程并写入状态文件

1. 获取当前时间戳（格式 YYYYMMDD_HHMMSS），构造 run_name：
   run_name = <script_basename_without_ext>_<timestamp>
   例：train_visiscore_20260506_143000

2. 构造启动命令：
   - 全新训练：python <script_path> [--config <config_path>] 2>&1 | tee D:/YJ-Agent/log/train_<run_name>.log
   - 续训模式：python <script_path> [--config <config_path>] --resume <checkpoint.last_path> 2>&1 | tee D:/YJ-Agent/log/train_<run_name>.log
   log_file = D:/YJ-Agent/log/train_<run_name>.log
   打印：「[续训] 从 checkpoint <last_path> 继续」或「[全新] 从第 1 epoch 开始」

3. 用 Bash(run_in_background=true) 启动该命令，记录 PID

4. 将以下内容写入 D:/YJ-Agent/log/experiment_state.json：
{
  "status": "running",
  "experiment": {
    "script": "<script_path>",
    "config": "<config_path 或 null>",
    "run_name": "<run_name>",
    "started_at": "<当前 ISO 8601 时间>",
    "retry_count": 0
  },
  "process": {
    "pid": <PID>,
    "log_file": "D:/YJ-Agent/log/train_<run_name>.log",
    "is_alive": true,
    "last_checked_at": "<当前时间>"
  },
  "progress": {
    "current_epoch": null,
    "total_epochs": null,
    "last_loss": null,
    "last_val_metric": null,
    "last_update_at": null
  },
  "checkpoint": {
    "save_dir": null,
    "last_path": null,
    "best_path": null,
    "last_epoch_saved": null
  },
  "error": {
    "type": null,
    "message": null,
    "fix_applied": null,
    "occurred_at": null
  }
}
注意：续训时保留原有 checkpoint 字段值，不要清空；全新训练时全部置 null。

# TODO [阶段三完善]：确认训练脚本 --resume 参数名称和 checkpoint 保存路径格式后，更新此处。

5. 返回：PID 和 log_file 路径
```

主会话接收 Haiku 返回后：
- 调用 Monitor 订阅 log_file（让用户实时看到训练输出）
- 打印：「[run-experiment] 训练已启动 PID=<pid> | 日志：<log_file> | 每 270 秒自动检查」
- 调用 `ScheduleWakeup(delaySeconds=270, prompt="/loop /run-experiment $ARGUMENTS", reason="monitoring experiment epoch/loss progress")`

---

## STEP 3：5 分钟检查循环（Haiku agent 执行）

将以下任务完整交给 `Agent(model="haiku")`：

```
任务：检查实验进度，更新状态文件

1. 读取 D:/YJ-Agent/log/experiment_state.json，获取 PID 和 log_file

2. 检查进程是否存活（Windows）：
   tasklist /FI "PID eq <pid>" /FO CSV
   如果输出包含该 PID → is_alive = true
   否则 → is_alive = false

3. 读取 log_file 最后 50 行：tail -n 50 <log_file>

4. 正则提取进度（按优先级尝试以下模式）：
   - epoch：匹配 "Epoch \[(\d+)/(\d+)\]" → current_epoch, total_epochs
   - loss：匹配 "loss[: =]([\d.]+)" → last_loss
   - val_metric：匹配 "val_plcc[: =]([\d.]+)" 或 "val_metric[: =]([\d.]+)" → last_val_metric

   检测 checkpoint 保存事件（更新 state.checkpoint 字段）：
   # TODO [阶段三完善]：训练脚本确定后，替换为实际的 checkpoint 保存日志格式
   - 匹配 "Saved checkpoint.*last\.pth" 或 "checkpoint saved.*last\.pth" → 提取路径更新 checkpoint.last_path
   - 匹配 "Saved checkpoint.*best\.pth" 或 "New best.*saved" → 提取路径更新 checkpoint.best_path
   - 同步更新 checkpoint.last_epoch_saved = current_epoch

5. 检查最后 50 行是否包含错误关键词：
   小问题关键词：
   - oom: "CUDA out of memory" / "OutOfMemoryError" / "torch.cuda.OutOfMemoryError"
   - path: "FileNotFoundError" / "No such file or directory"
   - param: "ConfigAttributeError" / "unexpected keyword argument" / "KeyError" (in config context)
   - connection: "wandb: ERROR" / "ConnectionError" / "requests.exceptions"

   大问题关键词：
   - arch: "mat1 and mat2 shapes" / "size mismatch" / "shape mismatch" / "Expected input batch_size"
   - data_format: "not enough values to unpack" / "IndexError" (in DataLoader context)
   - nan: "loss is nan" / "loss became nan" / "nan values"
   - import: "ModuleNotFoundError" / "ImportError"

6. 判断状态并更新 experiment_state.json：
   - is_alive=true + 无错误 → status 保持 "running"，更新 progress 字段
   - is_alive=false + 无错误关键词 → status = "done"
   - is_alive=false + 有错误关键词 → status = "error_minor" 或 "error_major"（按上方分类）
   - is_alive=true + 有错误关键词 → 同上分类
   同时更新 process.is_alive、process.last_checked_at、error.type、error.message（最后 30 行日志）

7. 返回摘要：{status, current_epoch, total_epochs, last_loss, last_val_metric, is_alive, error_type}
```

主会话根据返回决定下一步：

**status == "running"**：
- 打印进度：「[<时间>] 自动检查 | Epoch <N>/<M> | loss=<x> | PLCC=<x> | 进程 ✓」
- 重新调用 Monitor 订阅 log_file（防止 stream 断开后输出中断）
- 调用 `ScheduleWakeup(delaySeconds=270, ...)`

**status == "done"**：
- 打印：「实验完成！run_name=<name>，共 <N> epoch，最终 loss=<x>，PLCC=<x>」
- 不调 ScheduleWakeup，loop 结束

**status == "error_minor" 且 retry_count < 3**：
- 执行 STEP 4（自动修复）

**status == "error_minor" 且 retry_count >= 3**：
- 打印：「已自动修复 3 次，问题仍未解决，升级为人工处理」
- 执行 STEP 5

**status == "error_major"**：
- 执行 STEP 5

---

## STEP 4：自动修复（主会话 Sonnet 执行）

读取 experiment_state.json 中的 error.type，执行对应修复：

**oom（CUDA 内存不足）**：
1. 读取 config 文件，找 `batch_size` 字段，将其减半（如 128 → 64，最小值 8）
2. 写回 config 文件
3. 检查 state.checkpoint.last_path 是否存在：
   - 存在 → 打印「[自动修复] OOM：batch_size → <new_value>，从 Epoch <last_epoch_saved> 续训」
   - 不存在 → 打印「[自动修复] OOM：batch_size → <new_value>，无 checkpoint，从头重启」
4. 更新 state.json：retry_count++，status="idle"（保留 checkpoint 字段不清空）
5. 重新执行 STEP 2（有 checkpoint → 续训模式；无 checkpoint → 全新模式）

**path（路径不存在）**：
1. 从 error.message 中提取缺失路径
2. 用 Bash `mkdir -p <path>` 创建目录（如果是目录缺失）
3. 打印：「[自动修复] 创建缺失目录：<path>」
4. 更新 state.json：retry_count++，status="idle"
5. 重新执行 STEP 2

**param（配置参数非法）**：
1. 从 error.message 中定位非法字段名
2. 读取 config 文件，注释掉或删除该字段（保留一行注释说明原因）
3. 打印：「[自动修复] 移除非法 config 字段：<field_name>」
4. 更新 state.json：retry_count++，status="idle"
5. 重新执行 STEP 2

**connection（网络/wandb 连接失败）**：
1. 在启动命令前追加 `WANDB_MODE=disabled`
2. 打印：「[自动修复] wandb 连接失败，切换为离线模式重启」
3. 更新 state.json：retry_count++，status="idle"
4. 重新执行 STEP 2（带 WANDB_MODE=disabled）

---

## STEP 5：大问题上报（主会话 Sonnet 执行）

打印以下格式的错误报告：

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[ERROR] 实验 <run_name> 需要人工介入
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
错误类型：<type>
发生时间：<occurred_at>
当前进度：Epoch <N>/<M>，loss=<last_loss>

日志末尾（最后 30 行）：
<message>

建议排查方向：
• [arch]        检查模型输入输出维度与 config 中设置是否匹配
• [data_format] 检查 DataLoader 输出的 tensor shape 是否符合模型期望
• [nan]         尝试降低学习率（如 /10），检查数据是否有极端值（inf/nan）
• [import]      运行 pip install -r requirements.txt 确认依赖完整
• [unknown]     根据日志定位，可能是环境或配置问题

修复后重新运行：/loop /run-experiment <script> <config>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

更新 state.json：status = "error_major"
**不调用 ScheduleWakeup**，loop 结束，等待用户指令。
