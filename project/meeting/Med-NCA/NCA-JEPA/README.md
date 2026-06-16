# NCA-JEPA — 项目入口

**一句话**：把医学影像世界模型（I-JEPA）里又重又黑盒的 ViT 预测器，换成会「自己生长出答案」的神经细胞自动机（NCA）预测器。不比谁分数高，证明这个细胞预测器能做三件 ViT 预测器**结构上做不到**的事——训练稳定性可分析可控、推理随时可停、生长过程可看。

> **命名规范（单一真源）**：
> - **NCA-JEPA** = 项目 / 架构家族名（本文件夹、arXiv 占坑名，2026-06 实测搜索未被占用）
> - **SCP-JEPA**（Stable Cellular Predictor JEPA）= 加了稳定化三件套（SN + EMA + Det）的具体方法 = 实验 A2 臂
> - 「我们的方法 / 主臂」一律指 SCP-JEPA；「这条研究线 / 框架」一律指 NCA-JEPA

## 与 Med-NCA 复现的关系

Med-NCA 复现（本文件夹的父目录，**已封印**）是地基：复现亲手撞到 NCA 在高分辨率像素空间训练**静默发散**（前列腺 0/11 训满轮数、同种子落不同盆地）。NCA-JEPA 把 NCA 挪到 **latent token 网格**当预测器——理论上是 NCA 的「安全区」（步数 S 从 128→16，指数敏感性大幅降低）。那批独家失败数据是退路 B 的核心资产。

## 读档顺序

| # | 文件 | 用途 |
|---|---|---|
| 0 | `README.md`（本文） | 入口 + 命名规范 + 状态 |
| 1 | `01_创新计划.md` | **why**：核心叙事 / 竞争版图 / 三张牌 / 退路 B/C/D / 审稿人对峙 |
| 2 | `02_理论框架.md` | **命题**：SCP-JEPA 动力系统分析（§0–§10，🟢严格/🟡近似/🔵假说分级）|
| 3 | `03_pilot_NIH_ChestXray14.md` | **怎么跑**：唯一权威 pilot 执行计划（数据/4 臂/8 哨兵/Gate0-3/HPC/交付物）|

`_archive/pilot实验设计_v1.md` = 旧 2 周 pilot 设计，已被 `03_` 取代，留档。

## 当前状态

**🟢 实验阶段已启（2026-06-16）**。地基搭建完 + HPC 部署验通 + 哨兵门 7/8 + **A0 baseline 训练健康跑通**（job 1450052，loss 0.476→0.056@ep10，50ep ~16min）+ 红线10 官方超参联网复核完成（见 `configs/PROVENANCE.md`）。
- 算力：XJTLU HPC `gpu4090`（account `shuihuawang`，qos `4gpus`），项目根 `/gpfs/work/bio/jiayu2403/nca-jepa/`
- 数据：NIH ChestX-ray14（112,120 图全解压 HPC，pilot 子集 `splits/pretrain_10k.txt` 10k/3257 患者，泄漏 0）✅
- 地基库：`facebookresearch/ijepa` clone+集成 ✅ + `LeapLabTHU/CheXWorld`（超参参考）
- 进度详见 `../PROJECT_LOG.md` 最新 entry（2026-06-16）

## HPC 部署（NCA-JEPA 专属，单一真源）

> 连接凭证/VPN 见 `D:/YJ-Agent/project/HPC_WORKFLOW.md`（与 VisiEnhance 共用 HPC 账号）。本节是 NCA-JEPA 专属路径。

| 项 | 值 |
|---|---|
| 项目根 | `/gpfs/work/bio/jiayu2403/nca-jepa/`（与 `mednca/`/`visienhance/` 平行）|
| Python env | `/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python`（torch2.6/cu124，einops/timm/pandas/cv2 全在，缺 submitit 但用 main.py 本地启动不需要）|
| 数据 | `data/nih_cxr14/images-224/images-224/`（112120 png）+ `splits/` |
| 哨兵门 | `sbatch hpc/run_sentinels.sh` → `logs/sentinel_<job>.out` |
| pilot 训练 | `sbatch --export=ALL,ARM={a0\|a1\|a2},SEED={42\|123\|2024} --job-name=ncaj_<arm>_s<seed> hpc/sbatch_pilot.sh` |
| sbatch 头 | account `shuihuawang` / partition `gpu4090` / qos `4gpus` / `gres=gpu:rtx4090:1` |
| 监控 | 本地 `_hpc_wait_*.py`（paramiko 轮询 `logs/`）；训练脚本日志在 `logs/<jobname>_<job>.err`（I-JEPA 进度在 stdout/.out）|
| 上传工具 | `_hpc_upload.py`（首传）/ `_hpc_resume.py`（断点续传，EOF 后用）/ `_hpc_post.py`（补推+build_splits+smoke）|

## 判向逻辑（一图）

```
PC-1/2 稳定？─ 否 → RED 路线 B（稳定性理论，NeurIPS/ICLR）
   │是
Gate2 非劣？─ 差>5 → 路线 C（诊断工具，CVPR/ECCV）
   │>−3
Gate3 能力 ≥2 项？─ 否 → AMBER 限时再赌 / 降级
   │是
  GREEN 主攻（4 周升 ViT-B/0.5M）
```
