# .portfolio/ — 跨窗口协调状态（单一真源）

多终端窗口同时跑不同论文时，靠此目录协调，避免撞车。**仿 run-experiment 的 state.json 模式**：状态写文件不靠 context（context 压缩会断链）。

## 文件

- `registry.json` — 全局项目登记表（venue / deadline / status / priority / home / log）。新论文经 `/spin-off-paper` 登记于此。
- `datasets.json` — **跨论文共享数据集地址单一真源**。本地 + HPC 路径、下载源、用途、状态。任何脚本/config 引用数据集前先查此表；换路径/新增只改这里。防止重复硬编码 + 臆想路径。
- `locks/training.lock` — **全局训练锁**。任何本地 `Start-Process` 训练 / HPC `sbatch` 前必须持锁；被占即阻断（串行红线，跨所有窗口 + 本地 GPU + HPC 配额）。完成清锁。
  - 格式（JSON 单行）：`{"window_id","project","host":"local|hpc","pid","start_ts"}`
- `locks/<project>.claim` — 窗口认领。哪个终端在写哪篇，防两窗并写同项目 / 并写 PORTFOLIO.md。
  - 格式：`{"window_id","project","ts","heartbeat"}`

## 规则

1. 开窗 → session_start hook 报当前锁状态 + 建议认领。
2. 写某项目前先认领（写 `<project>.claim`）；他窗已认领则提示，避免并写。
3. 训练前 `training_lock.js` 检查 `training.lock`；持锁训练，完成清锁。
4. 锁是协作约定不是强制文件锁；hook 提示 + 主线纪律保证。陈旧锁（heartbeat 超时）可人工清。
