# HPC 镜像 — XJTLU HPC 上 QuantImmuBench 的部署/运行产物

本目录是从 XJTLU HPC 拉回的**我们自己写的编排文件 + 小体积运行产物**，方便离线查阅与归档。
体积大的外部资产（容器镜像、外部工具 repo、conda 环境、许可二进制）**留在 HPC 不拉回**（见下「留在 HPC」一节）。

- HPC 主机：`dtn.hpc.xjtlu.edu.cn`，用户 `jiayu2403`，分区 `gpu4090`（连接细节见 `project/HPC_WORKFLOW.md` + memory `project_hpc_xjtlu`）。
- HPC 项目根：`/gpfs/work/bio/jiayu2403/quantimmu/`（拉回时间 2026-06-24，总占 47 GB）。

## 目录内容（全部为本项目自有文件）

```
HPC/
├── deploy/                     # 各工具的 HPC 部署 / 环境搭建脚本 + 日志（我们写的）
│   ├── hpc_clones.sh           # git clone 各工具 repo
│   ├── dep_deepimmuno.sh/.log  # DeepImmuno conda 环境
│   ├── build_predig.sh/.log    # PredIG singularity 镜像构建
│   ├── build_ptuneos.sh/.log   # pTuneos singularity 镜像构建
│   ├── hpc_improve.sh          # IMPROVE 环境 + Predict 步
│   ├── hpc_neotimmuml.sh       # NeoTImmuML 环境
│   ├── hpc_dtu_setup.sh        # DTU 工具（netMHCpan 等）配置
│   ├── improve.log / neotimmuml.log
├── elispot_run/                # ELISpot 数据集在 HPC 上的正式跑（sbatch + 输入 + 输出）
│   ├── di_elispot.sh           # DeepImmuno SLURM 脚本
│   ├── di_1485416.out/.err     # job 1485416 日志
│   ├── deepimmuno_input.csv    # DeepImmuno 输入
│   ├── di_out/deepimmuno-cnn-result.txt  # DeepImmuno 输出
│   ├── predig_elispot.sh       # PredIG SLURM 脚本
│   └── predig_input.csv / predig_run/input.csv  # PredIG 输入
└── smoke/                      # HPC 烟测产物
    ├── predig/                 # PredIG recombinant 烟测 in/out
    └── improve/out_simple.tsv  # IMPROVE Predict Simple 烟测输出
```

> 注：脚本里硬编码的路径是 HPC 路径（`/gpfs/work/bio/jiayu2403/quantimmu/...`），仅作归档/参考，本地不可直接跑。

## 留在 HPC（未拉，体积/许可原因）

| HPC 路径 | 体积 | 不拉原因 |
|---|---|---|
| `sif/` | 32 GB | Singularity 容器镜像（PredIG 4.6G / pTuneos 1.7G 等），可由 `deploy/build_*.sh` 重建 |
| `tools_repos/` | 11 GB | 外部工具源码 repo（见 `../PROVENANCE.md`），各有自家许可，从官方 repo 重新 clone 即可 |
| `envs/` | 4.2 GB | conda 环境，由 `deploy/*.sh` 重建 |
| `ext_tools/` | 217 MB | **DTU 许可二进制**（netMHCpan-4.1 / 2.8 / netMHCstabpan-1.0）——学术许可禁止再分发，**绝不进 git / 绝不拉回公开仓**（见 `../PROVENANCE.md` 许可一节） |

## 复现路线（在新 HPC 账户重建）

1. `deploy/hpc_clones.sh` 拉外部 repo。
2. 各 `deploy/*.sh` / `build_*.sh` 重建环境与容器。
3. DTU 许可工具需各自向 services.healthtech.dtu.dk 申请后放 `ext_tools/`。
4. `elispot_run/*.sh` 跑正式 ELISpot 评测。
