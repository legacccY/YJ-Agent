# HPC Companion

给学生用的 SLURM 集群图形客户端 —— 把繁琐的 SSH + sbatch + 监控 + 传文件，收进一个双击即用的桌面程序。

通用任意 SLURM 集群，内置 XJTLU HPC（gpu4090）一键预设。

## 功能

| 标签页 | 能做什么 |
|---|---|
| **连接** | 多集群 profile 管理；密码经系统凭据库加密存储（绝不明文）；XJTLU 一键预设 + VPN 提醒 |
| **任务监控** | `squeue` 表格自动刷新（状态着色）、一键取消、scontrol 详情、日志 tail、GPU 利用率曲线、读 `experiment_state.json` 画训练心跳曲线 |
| **文件传输** | 本地 ↔ 远端双栏 SFTP，多选上传/下载带进度条，远端新建目录/删除 |
| **提交任务** | 填表实时预览 `submit.sh`，一键写入远端并 `sbatch`，account/分区/QOS/工作目录自动从 profile 预填 |

## 安全设计

- 密码存系统凭据库（Windows 凭据管理器 / macOS Keychain），`profiles.json` 只存非敏感字段。
- 凭据库不可用时退化为「本会话内存保存」，重启需重填——不会落盘明文。

## 开发运行

```bash
pip install -r requirements.txt
python main.py
```

> **PyQt6 版本注意**：锁定 `6.6.1`。`6.7+` 在部分 anaconda / 旧 MSVC 运行库环境会
> `DLL load failed while importing QtCore`。换环境前先确认。

## 打包成 exe

```bash
pip install pyinstaller
pyinstaller build.spec --noconfirm
# 产物：dist/HPC-Companion.exe（单文件，可直接发给学生）
```

`build.spec` 已处理 paramiko / keyring 的隐式导入。首次打包后建议在干净机器上验证 keyring 后端能加载。

## 测试

```bash
python -m pytest tests/ -q     # SLURM 解析/生成纯函数单测
```

## 架构

```
main.py                 入口
core/
  config.py             路径常量 + 集群预设
  profiles.py           profile CRUD + keyring 密码读写
  ssh_client.py         paramiko SSH/SFTP 唯一出口（线程安全）
  slurm.py              squeue/scontrol/sinfo 解析 + sbatch 生成（纯函数，可测）
  worker.py             QThreadPool 异步执行器（含进度回调），SSH 调用不卡 UI
ui/
  theme.py              专业深色 QSS
  app_context.py        共享 SSH 连接 + 连接状态信号
  main_window.py        标签壳 + 顶部连接状态条
  connection_panel.py   连接/profile 管理
  jobs_panel.py         任务监控（表格/日志/GPU/心跳）
  transfer_panel.py     SFTP 双栏传输
  submit_panel.py       提交向导
```

所有阻塞的 SSH/SFTP 调用都走 `core.worker` 丢到线程池，结果用 Qt 信号回主线程，界面不冻结。
