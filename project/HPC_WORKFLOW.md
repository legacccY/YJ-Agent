# XJTLU HPC 工作流（VisiEnhance 训练）

## 连接信息

| 字段 | 值 |
|------|-----|
| 主机 | `dtn.hpc.xjtlu.edu.cn` |
| 用户名 | `jiayu2403` |
| 密码 | `pxXd3VGhbB` |
| 账户（SLURM） | `shuihuawang` |
| 分区 | `gpu4090` |
| QOS | `4gpus` |
| VPN | 校外必须开 XJTLU VPN 才能连 |

---

## HPC 目录结构

```
/gpfs/work/bio/jiayu2403/visienhance/
├── code/                        # Python 训练代码
│   ├── train_visienhance.py     # 主训练脚本（STATE_PATH 已 patch）
│   ├── models/                  # 模型定义
│   ├── data/                    # 数据加载模块
│   └── configs/                 # （未用，config 在上一级）
├── configs/
│   └── visienhance_s2_planA_hpc.yaml  # Stage 2 HPC 专用 config
├── data/
│   ├── paired_dataset_nocrop/   # 149100 张降质图（medium/light/heavy）
│   ├── isic2020/                # 33126 张原图
│   ├── quality_labels_nocrop.csv        # 原始 Windows 路径版（不要用）
│   └── quality_labels_nocrop_hpc.csv   # HPC 路径版（训练用这个）
├── checkpoints/
│   ├── visienhance/stage1_planA_nocrop/best_visienhance.pth  # Stage 1 起点
│   ├── visienhance/stage2_planA/                             # Stage 2 输出
│   ├── best_visiscore.pth
│   └── efnet/best_qad.pth
├── logs/
│   ├── {job_id}.out             # SLURM stdout
│   ├── {job_id}.err             # 训练进度（Train:/Test: 行在这里）
│   ├── {job_id}_gpu.log         # GPU 利用率（每 30s 一条）
│   └── experiment_state.json   # 训练脚本写入的实时状态
├── results/
├── submit.sh                    # SLURM 提交脚本
└── hpc_setup_paths.py           # 路径修复工具（一次性运行）
```

---

## 本地工具文件

> ⚠️ HPC 脚本已统一移到 `D:\YJ-Agent\tools\`（2026-06-10 仓库整理）。

| 文件 | 用途 |
|------|------|
| `D:\YJ-Agent\tools\hpc_monitor.py` | 单次快照查询（job 状态 + 日志） |
| `D:\YJ-Agent\tools\hpc_watch.py` | 终端 watch 模式（轮询，Ctrl+C 退出） |
| `D:\YJ-Agent\tools\hpc_live_gui.py` | tkinter GUI 实时监控（自动刷新 + 错误检测） |
| `D:\YJ-Agent\tools\hpc_mednca_check.py` | Med-NCA job 状态/日志检查（弃 GUI 用这个） |

---

## 一次性 Setup 流程（已完成，记录备查）

```python
# 本地打包
zipfile paired_dataset_nocrop → D:\YJ-Agent\paired_dataset_nocrop.zip  (1.54 GB)
zipfile isic2020 orig          → D:\YJ-Agent\isic2020_orig.zip          (598 MB)

# SFTP 传输（paramiko）
sftp.put(zip, HPC) → unzip on HPC
sftp.put(checkpoints)
sftp.put(CSVs)
sftp.put(code/)

# HPC 端初始化
python hpc_setup_paths.py   # 生成 quality_labels_nocrop_hpc.csv（路径 Windows→GPFS）
```

---

## ⚠️ 首次提交前必做：预下载模型权重

**GPU 节点计费从 job 启动计算，不能在 GPU 上下权重。** 在登录节点（DTN）预下：

```python
import paramiko, warnings
warnings.filterwarnings('ignore')
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=15)

CACHE = '/gpfs/work/bio/jiayu2403/.cache/torch/hub/checkpoints'
PIP   = '/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/pip'

def run(cmd, timeout=300):
    _, o, e = c.exec_command(cmd, timeout=timeout)
    return o.read().decode() + e.read().decode()

# 按需安装缺包（只需一次）
print(run(f'{PIP} install lpips --quiet'))

# 预下 EfficientNet + AlexNet（LPIPS backbone）
print(run(f'wget -q -O {CACHE}/efficientnet_b0_rwightman-7f5810bc.pth '
          'https://download.pytorch.org/models/efficientnet_b0_rwightman-7f5810bc.pth'))
print(run(f'wget -q -O {CACHE}/alexnet-owt-7be5be79.pth '
          'https://download.pytorch.org/models/alexnet-owt-7be5be79.pth'))
c.close()
```

已缓存权重（2026-06-01）：EfficientNet-B0 (21MB) + AlexNet (234MB) + LPIPS v0.1/alex.pth（包内）

## 提交训练

```bash
# 在本地用 paramiko 执行，或 SSH 后手动：
sbatch /gpfs/work/bio/jiayu2403/visienhance/submit.sh

# 查看任务
squeue -u jiayu2403
```

Stage 切换：
- Stage 1: `configs/visienhance_s1_planA_hpc.yaml`（若需重跑 Stage 1）
- Stage 2: `configs/visienhance_s2_planA_hpc.yaml`（当前活跃）
- Stage 3: 待创建 `configs/visienhance_s3_planA_hpc.yaml`

---

## 日常监控

```bash
# 单次查询
python "D:\YJ-Agent\tools\hpc_monitor.py" [job_id]

# 实时 GUI（弹窗，自动刷新）—— 必须带 job_id 参数
python "D:\YJ-Agent\tools\hpc_live_gui.py" [job_id]

# 实时终端 watch
python "D:\YJ-Agent\tools\hpc_watch.py" [job_id] [间隔秒]
```

**弹窗快捷启动（PowerShell）：**
```powershell
Start-Process python -ArgumentList '"D:\YJ-Agent\tools\hpc_live_gui.py" <JOB_ID>'
```

GUI 特性：
- 前 2 epoch：60 秒刷新（快速跟进启动状态）
- Epoch ≥ 2：5 分钟刷新
- 读 `experiment_state.json`（训练脚本实时写入）
- 错误检测：NaN/OOM/RuntimeError/Killed → 背景变红 + 警告

---

## 快速 paramiko 连接模板

```python
import paramiko, warnings
warnings.filterwarnings('ignore')

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=15)

def run(cmd, timeout=30):
    _, o, e = c.exec_command(cmd, timeout=timeout)
    return o.read().decode('utf-8', errors='replace').strip()

# 用完后
c.close()
```

---

## 故障排查

| 症状 | 原因 | 处理 |
|------|------|------|
| Authentication failed | 校外未开 VPN | 开 XJTLU VPN 再连 |
| 数据集为空 0 样本 | CSV 用了 Windows 路径版 | 确认 config 指向 `*_hpc.csv` |
| GPU 利用率一直 0% | 数据加载瓶颈 / srun 采样在间隙 | 看 GPU log 文件峰值 |
| Job FAILED 立即退出（6s）| `module load / source activate` 在 SLURM 不生效 | submit.sh 用绝对路径 `/conda/envs/.../python3.10` |
| Job FAILED 立即退出（30s）| DDP resume 用 `model.load_state_dict` → key 有 `module.` 前缀不匹配 | 改为 `_raw_model.load_state_dict` |
| Job FAILED：ModuleNotFoundError | 新包未装 / 权重未预下 | DTN 上 pip install + wget 后再提交 |
| NaN loss | lr 过高 / DP-Loss 过强 | 降 lr 或 lambda_dp |
| PSNR 下滑 Stage 2 | val_severity 配置问题（已修复）| 确认 val_severity=mixed |
| GUI 显示异常但 job 在跑 | job_id 硬编码旧值 / `inf` 匹配 `[INFO]` | 带正确 job_id 参数重启 GUI |

---

## 环境说明

- conda 环境：`yjcu124py310`（路径 `/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310`）
- 所有必需包已验证：torch / torchvision / timm / lpips / wandb / pandas / PIL / yaml / tqdm
- GPU：RTX 4090 (24 GB VRAM)，节点 `gpu4090n[2-10]`
- SLURM account：`shuihuawang`（指导老师配额，最多 4 GPU）
