# .portfolio/ — 跨窗口协调状态（单一真源）

多终端窗口同时跑不同论文时，靠此目录协调，避免撞车。**仿 run-experiment 的 state.json 模式**：状态写文件不靠 context（context 压缩会断链）。

## 文件

- `registry.json` — 全局项目登记表（venue / deadline / status / priority / home / log）。新论文经 `/spin-off-paper` 登记于此。
- `datasets.json` — **跨论文共享数据集地址单一真源**。本地 + HPC 路径、下载源、用途、状态。任何脚本/config 引用数据集前先查此表；换路径/新增只改这里。防止重复硬编码 + 臆想路径。
- `locks/training.lock` — **按卡训练调度（schema v2，取代旧全局单锁）**。容量 `local=1`（RTX4070 8GB）/ `hpc=4`（gpu4090 qos 4gpus）。多任务可共存只要空闲卡够，**绝不挤正在跑的**；卡满排队，有卡 release 后 FIFO 自动取出。
  - 不手改 JSON，全走 `python tools/gpu_slot.py {request|release|status|list|reap}`（头注有用法）。
  - 协议：启训前 `request <project> <host> <gpus>` → `GO`=有卡写 active starting 条目可启（`training_lock.js` hook 翻 running 放行）；`QUEUED`=卡满入队别裸启。完成 `release <id>` 清账 + 吐 `NEXT` 取出排队任务。
  - schema：`{"schema_version":2,"capacity":{"local":1,"hpc":4},"active":[{"id","project","host","gpus","status":"starting|running","start_ts","note"}],"queue":[{"id","project","host","gpus","enqueued_ts","note"}]}`
- `locks/<project>.claim` — 窗口认领。哪个终端在写哪篇，防两窗并写同项目 / 并写 PORTFOLIO.md。
  - 格式：`{"window_id","project","ts","heartbeat"}`

## 规则

1. 开窗 → session_start hook 报当前锁状态 + 建议认领。
2. 写某项目前先认领（写 `<project>.claim`）；他窗已认领则提示，避免并写。
3. 训练前 `gpu_slot.py request` 申请卡槽，`training_lock.js` hook 按卡放行/拦；完成 `gpu_slot.py release` 清账（自动取出排队任务）。
4. 锁是协作约定不是强制文件锁；hook 提示 + 主线纪律保证。陈旧锁（heartbeat 超时）可人工清。
