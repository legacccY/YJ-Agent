# FMReg — Flow-Matching 可变形医学图像配准

> 组合台子项目入口。源自选题流水线 `project/ideation/runs/2026-06-17_run-002_medimg-method` G6 立项卡（唯一存活候选 S2-03）。立项日 2026-06-17（用户拍板）。

## 一句话

用 flow-matching（OT-Flow）的**直线流形变场**做跨模态/单模态可变形医学图像配准，少步（≤4）逼近 diffusion 配准（DiffuseMorph 类）的精度，同时保证拓扑合法（雅可比正）。

## 核心 RQ

FM 已在图像**合成**上证明「直线传输 = 少步高质量」。把它迁到「形变场 = flow target」的**配准**范畴，能否在保持 diffeomorphism（无折叠）的前提下，用远少于 diffusion 的步数达到/超过 VoxelMorph/TransMorph 与 DiffuseMorph？

## 立项证据（G5 雅可比闸 GREEN）

`ideation/runs/2026-06-17_run-002_medimg-method/06_experiments/results/killshot_s2_03_jacobian.csv`：
- `neg_jac_pct = 0.0000`（OASIS 20 对 2D 单步 Euler 积分，零拓扑折叠）
- `dice_fm = 0.9279 > dice_affine = 0.8384`（胜仿射基线）

> ⚠️ caveat：killshot 用**简化 FM target 代理**。几何雅可比属性（关键）已干净验证，但完整 velocity→diffeomorphism 理论保证待中训证（立项后第一件事补几何配准理论复核，见 LOG）。

## venue（立项日已纠偏）

- top：**MICCAI 2027**（~2027-03 截）/ **CVPR 2027**（~2026-11 截）。注：MICCAI 2026/CVPR 2026 截稿已过（今 2026-06）。
- fallback：MedIA / TMLR（rolling）

## 数据

| 数据集 | 角色 | 状态 |
|---|---|---|
| BraTS2021 | 同模态/多序列形变配准主战场 | 本机 ready（见 datasets.json）|
| OASIS | 脑 MRI 配准标准 benchmark（killshot 已用 2D 切片）| 需下 |
| Learn2Reg | 多任务配准公开 benchmark（含跨模态 CT-MRI）| 需下 |

## compute

~80 GPU·h（XJTLU HPC gpu4090，可承）。

## 读档顺序

`00_README.md`（本文）→ `01_STORY.md` → `02_ACCEPTANCE.md`（含 3 条书面 kill criteria）→ `04_LOG.md` 最新 entry。

## 文件导航

| 路径 | 内容 |
|---|---|
| `01_STORY.md` | 故事框架 + 与组合台其他项目边界 |
| `02_ACCEPTANCE.md` | 验收判据 + kill criteria K1/K2/K3 |
| `04_LOG.md` | 进度留痕（首条 = 立项决策）|
| `06_experiments/` | 实验计划 + 结果（待建）|
