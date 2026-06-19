# gdn2vessel PROJECT_LOG

## Entry 1 — 2026-06-20 立项 + 环境就绪 + 数据集开下

### 立项决策（用户拍板链）
- 任务：ACCV 2026 拿最新模型做深度结构创新稳录。锚模型经多轮调研收敛 = **Gated DeltaNet-2**（arXiv 2605.22791，NVIDIA 2026-05，零视觉版）。
- 靶场：从皮肤镜（GDN-2 吃亏处）重定向到**血管/管状结构分割**（GDN-2 长程优势能兑现处；Serp-Mamba/HM-Mamba 已证 SSM>CNN）。
- headline 收敛（skeptic 两轮红队）：**delta-rule 关联记忆做血管断点续连**（C 独头承重；A 拓扑扫描撞 TopoMamba 降工程、B 解耦门作 C 机制）。
- 数据集：血管+跨域管状 9+ 集碾压（同类才 3-5 集）。kill 放宽（允许 1-2 边缘集失败）。HPC 4 卡动态并行。
- 批准 plan：`~/.claude/plans/d-yj-agent-project-meeting-accv-2024-acc-keen-pony.md`。

### 🆕 铁律（用户 2026-06-20）
**遇到计划外任何问题先问用户、绝不盲跑**。详见 00_README。

### kill-shot 进展（HPC 优先）
- **关 0 PASS**：driver=565.77。<570 → cu128 路线堵；**退路 cu126 确认可行**（driver 565 支持 CUDA≤12.7，torch wheel 自带 runtime）。系统 CUDA module 最高 12.6。
- **关 1 PASS**：HPC 建 venv `/gpfs/work/bio/jiayu2403/gdn2venv`（py3.10），装 **torch 2.9.0+cu126 + triton 3.5.0 + FLA(flash-linear-attention)**，跳过 flash-attn（烟测只需 FLA gated_delta_rule）。验证 `import torch,fla` OK。
  - 坑1（已修）：FLA `--no-build-isolation` 缺 `wheel` → `invalid command 'bdist_wheel'`。修法 A：装 wheel/setuptools 后重试，通。
  - 注：登录节点无 GPU，FLA import 报 "Triton roll back to CPU" 属正常；真 kernel 烟测须 srun 上 GPU 节点。
- **关 2（GPU kernel 烟测）= 待下次**：srun gpu4090 跑单层 GDN-2 fwd/bwd（退路 `naive_chunk_gated_delta_rule` 纯 PyTorch）。骨架见 plan。
- **关 3（pilot 不输 CNN）= 待**。

### 数据集
- 本地：kaggle 全家桶 `umairinayat/retinal-vessel-segmentation-datasets`（DRIVE+CHASE+FIVES，1.79GB）→ `data/vessel/`（下载中）。
- HPC：kaggle.json 传 HPC 被权限分类器拦（凭证越界）→ 用户拍板走 **A：本地下完 sftp 公开数据给 HPC**（不碰凭证）。
- 缺 STARE/HRF/冠脉(XCAD/DCA1/CHUAC)/OCTA → 下批另源（DCA1 CIMAT 服务器曾 ECONNREFUSED 待复查）。
- Kaggle slug 已核：DRIVE=`andrewmvd/drive-digital-retinal-images-for-vessel-extraction`、FIVES=`nikitamanaenkov/fundus-image-dataset-for-vessel-segmentation`。

### HPC 连接
dtn.hpc.xjtlu.edu.cn / jiayu2403 / account shuihuawang / gpu4090·4gpus / `/gpfs/work/bio/jiayu2403/`。venv=`gdn2venv`。

### 下一步（下窗）
1. 本地下载完 → sftp data/vessel 给 HPC。
2. 关 2 GPU kernel 烟测（srun，gpu_slot 申请）。
3. 关 3 pilot。两关 PASS → planner 出完整矩阵（断点续连 benchmark 第一优先）。
4. STORY+ACCEPTANCE 落档。补 STARE/HRF/冠脉/OCTA 数据集。
