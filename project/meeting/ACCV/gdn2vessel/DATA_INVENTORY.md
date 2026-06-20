# gdn2vessel 数据全景表

**真源**：跨论文共享数据集真源 = `.portfolio/datasets.json`（本地+HPC+source+状态）。本文件是 gdn2vessel 视角的导航 + 脚本/结果/baseline 索引，**数据集路径不重抄**，引 datasets.json 的 key。
**最后更新**：2026-06-20

---

## 📦 数据集（按用途分级；详细路径/许可见 datasets.json）

| 分级 | 数据集 | datasets.json key | 状态 |
|---|---|---|---|
| **核心主做（撑 headline + 断点 benchmark）** | DRIVE / CHASE_DB1 / FIVES / STARE | `vessel_collection_kaggle` | ✅ 5 集已部署 HPC 验通（含 HRF），`/gpfs/work/bio/jiayu2403/gdn2vessel/data/vessel/` |
| 高分辨率（长序列优势） | HRF / FIVES（2048²） | `vessel_collection_kaggle` | ✅ 同上 |
| 冠脉（跨器官管状） | XCAD / DCA1 / CHUAC | `vessel_pending` | ⬜ todo（XCAD=github Dropbox / DCA1=CIMAT 曾 ECONNREFUSED 待复查 / CHUAC=figshare） |
| OCTA 血管 | OCTA-500 / ROSE | `vessel_pending` | ⬜ todo（OCTA-500 需注册 / ROSE=zenodo） |
| 跨域（附录泛化） | Crack500 / Massachusetts Roads | TODO 待登记 | ⬜ todo |

> 许可证逐个确认能否学术发表后才纳入（红线）。边缘集（OCTA/冠脉/跨域）允许 1-2 失败（kill 放宽）。

---

## 🧪 断点续连 benchmark（自造，P1 产出）

- **合成协议**：对齐 creatis plug-and-play（arXiv 2404.10506），半径分布 P(i)=2^(p-i)/(2^p-1) 抽样 + gap 参数 s∈{6,8,10,12}/σ；DRIVE/STARE 先做，再推广。
- **指标**：
  - ε_β0（连通分量误差比）— 直接用，参 plug-and-play
  - SR（success rate，gap 闭合率）— 直接用
  - **re-ID 率**（同根血管匹配，自定义，借 MOT IDF1）— P1 设计
- **工具库**（开源可直接用）：
  - clDice → https://github.com/jocpae/clDice
  - Betti-Matching-3D → https://github.com/nstucki/Betti-Matching-3D
  - Skeleton Recall → https://github.com/MIC-DKFZ/Skeleton-Recall
  - 合成协议参考 → https://github.com/creatis-myriad/plug-and-play-reco-regularization

---

## 🤖 baseline 全谱（P3 同台，≥12；调研已核数字见 STORY 锁定表）

> **★ canonical 真源 = [`PLAN/BASELINE_SPEC.md`](PLAN/BASELINE_SPEC.md)**（2026-06-20 3 researcher+1 planner 综合）：roster 三档（A 同框架可跑 12+B 候选+C 仅引数字）+ 官方超参表（含 TODO 槽位）+ license 合规 + harness 设计（公平矩阵/反向公平点/mamba 隔离）+ 算力拍板。下表是速览，详情/超参/repo 一律以 BASELINE_SPEC 为准。

| 类 | 方法 | 开源 |
|---|---|---|
| 公平主干 | nnU-Net | 是 |
| SSM/Mamba | HM-Mamba / Serp-Mamba / VM-UNet / U-Mamba / OCTAMamba / TopoMamba / **VFGS-Net(2026.02)** / **MM-UNet(2025.11)** / **MambaVesselNet++** | 部分（MambaVesselNet++ 开源跨域） |
| 拓扑 | DSCNet / clDice / **cbDice(MICCAI24)** / **Skeleton Recall(ECCV24)** / **TFFM(WACV26)** / **PASC-Net(FIVES SOTA)** | 多数开源 |
| 血管经典 | FR-UNet / SA-UNet(v2) / SCS-Net / CS-Net | 部分 |

> TODO（调研标）：TA-Mamba/CS-Net 官方 Dice、Skeleton Recall 各集 Dice、XCAD SOTA、nnU-Net retinal 2D 数字——用前需核官方源。

---

## 📁 代码/结果/checkpoint 路径（待建占位）

| 类 | 路径 | 状态 |
|---|---|---|
| 训练脚本 | `project/meeting/ACCV/gdn2vessel/src/`（待建） | ⬜ P2 |
| benchmark 生成脚本 | `.../benchmark/`（待建） | ⬜ P1 |
| kill-shot 脚本 | `killshots/`（<50 行主线串行跑） | 🚧 关0/1 done |
| 结果 csv | `.../results/`（待建） | ⬜ P3 |
| baseline checkpoint | HPC `/gpfs/work/bio/jiayu2403/gdn2vessel/ckpt/`（待建） | ⬜ P3 |
| 图 | `.../figures/`（待建） | ⬜ P6 |

---

## 🖥️ HPC 连接

- 节点：dtn.hpc.xjtlu.edu.cn / 用户 jiayu2403 / account shuihuawang / 分区 gpu4090·4 卡 qos
- 工作目录：`/gpfs/work/bio/jiayu2403/gdn2vessel/`
- venv：`/gpfs/work/bio/jiayu2403/gdn2venv`（py3.10 + torch 2.9.0+cu126 + triton 3.5.0 + FLA）
- 卡调度：`python tools/gpu_slot.py request gdn2vessel hpc 1`，绝不挤正在跑的，完成 release
- 详细工作流：`project/HPC_WORKFLOW.md`
