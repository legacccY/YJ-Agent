---
name: run-experiment
description: 多 agent 实验运行流水线：pytest 测试 → GPU 验证 → 启动训练 → 每 270 秒自动检查（读 state.json） → 小问题自动修复，大问题上报
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
- `$1` = 训练脚本路径（必填），如 `project/train_visiscore.py`
- `$2`（可选）= 配置文件路径，如 `project/configs/visiscore.yaml`

**断点续训检测**：读取 state.json 后，额外检查 `checkpoint.last_path` 字段：
- 字段存在且对应文件实际存在（用 Bash `ls <path>` 验证）→ 标记为续训模式，STEP 2 启动时自动带 `--resume <last_path>`
- 字段为 null 或文件不存在 → 全新训练，不加 `--resume`

---

## STEP 1：启动前检查（主会话 Bash 执行）

### 1a. GPU 验证
```
cd D:/YJ-Agent/project && python -c "
import torch
if torch.cuda.is_available():
    props = torch.cuda.get_device_properties(0)
    print(f'[GPU] {props.name} | 显存 {props.total_memory // 1024**2} MB | 设备数 {torch.cuda.device_count()}')
else:
    print('[GPU] 无 CUDA 设备，将用 CPU 训练')
"
```
打印 GPU 信息后继续；如果 CUDA 不可用，询问用户是否继续。

### 1b. pytest 测试
```
cd D:/YJ-Agent/project && python -m pytest tests/ -v -x --timeout=60 2>&1
```
- 全部通过 → 继续 STEP 2
- 有失败 → 展示失败测试名 + 错误摘要，询问用户「pytest 有 N 个失败，是否继续？(y/n)」
  - n → 停止
  - y → 继续 STEP 2
- `tests/` 不存在 → 跳过，打印「未找到 tests/，跳过」

---

## STEP 2：启动训练（主会话执行，不用 Haiku）

**说明**：训练脚本启动后会自己把 PID 写入 state.json，无需外部捕获 PID。

1. 获取当前时间戳（格式 YYYYMMDD_HHMMSS），构造：
   ```
   run_name = <script_basename_without_ext>_<timestamp>
   log_file = D:/YJ-Agent/log/train_<run_name>.log
   ```

2. 用 `Start-Process` 在独立 PowerShell 窗口启动（Windows 后台进程必须用此方式，bash 后台会随 shell 退出被杀）：
   ```powershell
   Start-Process powershell -ArgumentList (
     '-NoExit', '-Command',
     'cd D:/YJ-Agent/project; python <script_path> [--config <config_path>] [--resume <last_path>] 2>&1 | Tee-Object <log_file>'
   ) -WindowStyle Normal
   ```
   打印：`[全新] 从第 1 epoch 开始` 或 `[续训] 从 checkpoint <last_path> 继续`

3. 将以下内容写入 `D:/YJ-Agent/log/experiment_state.json`（训练脚本启动后会自动补全 pid 和 progress 字段）：
   ```json
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
       "pid": null,
       "log_file": "<log_file>",
       "is_alive": true,
       "last_checked_at": "<当前时间>"
     },
     "progress": {
       "current_epoch": null,
       "total_epochs": null,
       "last_loss": null,
       "last_val_metric": null,
       "val_metric_history": [],
       "last_update_at": null
     },
     "checkpoint": {
       "save_dir": "D:/YJ-Agent/checkpoints",
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
   ```
   续训时保留原有 checkpoint 字段，不清空。

4. 等待 15 秒，然后读取 state.json 确认 pid 字段已被训练脚本写入（非 null 即为成功）。

5. 打印：`[run-experiment] 训练已启动 PID=<pid> | 日志：<log_file> | 每 270 秒自动检查`
6. 调用 `ScheduleWakeup(delaySeconds=270, prompt="/loop /run-experiment $ARGUMENTS", reason="monitoring training progress via state.json")`

---

## STEP 3：检查循环（主会话执行）

**进度来源**：直接读 state.json 的 progress 字段（训练脚本每 epoch 末写入），不解析日志。

### 3a. 读取状态
读取 `D:/YJ-Agent/log/experiment_state.json`，获取：
- `process.pid`、`process.log_file`
- `progress.current_epoch`、`progress.last_loss`、`progress.last_val_metric`、`progress.val_metric_history`
- `checkpoint.last_path`、`checkpoint.best_path`

### 3b. 进程存活检测（优先用 log mtime，不依赖 PID）
```bash
python -c "
import os, time, json
log = json.load(open('D:/YJ-Agent/log/experiment_state.json'))['process']['log_file']
mtime = os.path.getmtime(log)
age_min = (time.time() - mtime) / 60
print(f'log_age={age_min:.1f}min')
"
```
- `log_age < 10 min` → 进程活跃（is_alive = true）
- `log_age >= 10 min` → 进程可能已停止，进入 3c 进一步判断
- 如果 pid 非 null，补充用 `tasklist /FI "PID eq <pid>" /FO CSV` 确认

### 3c. 判断完成 vs 错误
如果 is_alive = false：
- 读取 log 文件最后 30 行
- 包含 "Training complete." → status = "done"
- 包含以下关键词 → 对应错误类型：

  **小问题（error_minor）**：
  - `oom`: "CUDA out of memory" / "OutOfMemoryError"
  - `path`: "FileNotFoundError" / "No such file or directory"
  - `param`: "ConfigAttributeError" / "unexpected keyword argument" / "KeyError"
  - `connection`: "wandb: ERROR" / "ConnectionError"

  **大问题（error_major）**：
  - `arch`: "mat1 and mat2 shapes" / "size mismatch" / "shape mismatch"
  - `data_format`: "not enough values to unpack" / "IndexError"
  - `nan`: "loss is nan" / "loss became nan" / "nan values"
  - `import`: "ModuleNotFoundError" / "ImportError"

  - 无关键词 + 进程死了 → status = "done"（正常结束）

### 3d. 过拟合检测（is_alive = true 时持续监测）
读取 `progress.val_metric_history`（训练脚本每 epoch append 一个 PLCC 值）：
- 最近 3 个值连续下降 且 `last_loss` 仍在下降 → error.type = "overfitting"，status = "error_minor"
- 当前 val_metric 低于历史最高值 20% 以上 → 同上

### 3e. 更新 state.json 并决定下一步

**status == "running"（无异常）**：
- 打印：`[<北京时间>] 自动检查 | Epoch <N>/<M> | loss=<x> | PLCC=<x> | 进程 ✓`
- 调用 `ScheduleWakeup(delaySeconds=270, ...)`

**status == "done"**：
- 打印：`实验完成！run_name=<name>，共 <N> epoch，最佳 PLCC=<x>，checkpoint: <best_path>`
- 不调 ScheduleWakeup

**status == "error_minor" 且 retry_count < 3**：
- 执行 STEP 4

**status == "error_minor" 且 retry_count >= 3**：
- 打印「已自动修复 3 次，问题仍未解决」→ 执行 STEP 5

**status == "error_major"**：
- 执行 STEP 5

---

## STEP 4：自动修复（主会话执行）

**oom（显存不足）**：
1. 读 config，找 `batch_size`，减半（最小值 8），写回
2. 检查 checkpoint.last_path 是否存在 → 续训或重头
3. 打印：`[自动修复] OOM：batch_size → <new_value>`
4. state.json：retry_count++，status="idle"
5. 重新执行 STEP 2

**overfitting（过拟合）**：
1. 读 config，在 `train` 节下添加或更新 `lr_scheduler: cosine`
2. 有 checkpoint.last_path → 续训；否则重头
3. 打印：`[自动修复] 过拟合检测：启用 CosineAnnealingLR，从 Epoch <N> 续训`
4. state.json：retry_count++，status="idle"，清空 val_metric_history
5. 重新执行 STEP 2

**path（路径不存在）**：
1. 从 error.message 提取缺失路径，`mkdir -p <path>`
2. 打印：`[自动修复] 创建缺失目录：<path>`
3. state.json：retry_count++，status="idle"
4. 重新执行 STEP 2

**param（配置参数非法）**：
1. 定位非法字段，注释掉或删除
2. 打印：`[自动修复] 移除非法 config 字段：<field_name>`
3. state.json：retry_count++，status="idle"
4. 重新执行 STEP 2

**connection（wandb 连接失败）**：
1. 在启动命令前加 `WANDB_MODE=offline`
2. 打印：`[自动修复] wandb 切换为离线模式`
3. state.json：retry_count++，status="idle"
4. 重新执行 STEP 2（带 WANDB_MODE=offline）

---

## STEP 5：大问题上报（主会话执行）

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
• [arch]        检查模型输入输出维度与 config 设置是否匹配
• [data_format] 检查 DataLoader 输出 tensor shape 是否符合模型期望
• [nan]         降低学习率（如 /10），检查数据是否有 inf/nan
• [import]      运行 pip install -r requirements.txt 确认依赖完整

修复后重新运行：/loop /run-experiment <script> <config>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

state.json：status = "error_major"
**不调用 ScheduleWakeup**，等待用户指令。

---

## Windows 训练环境规范（每次启动前确认）

| 检查项 | 正确做法 | 错误做法 |
|--------|----------|----------|
| DataLoader 多进程 | `multiprocessing_context='spawn'` | 默认 fork（Linux 行为） |
| 路径分隔符 | 正斜杠 `/` 或 `Path()` 对象 | 反斜杠 `\v` `\t` 等会被解释为转义字符 |
| 相关系数计算 | 纯 numpy 实现 PLCC/SRCC | scipy.stats（与 PyTorch 共享 OpenMP，Windows 报 OMP Error #15） |
| 后台启动 | `Start-Process powershell` | `Bash(run_in_background=True)`（随 shell 退出被杀） |
| pin_memory | `false`（Windows spawn workers 不支持） | `true` |
