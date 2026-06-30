# CXR-SSLBench — 胸片自监督范式横评 + 轻量方法

> status: **Phase 0 验证 pilot**（未正式立项 registry，Gate1 PASS 后才跑 `/spin-off-paper` 全 schema）
> venue: 待定（PR/TMI 顶刊 vs benchmark 友好场，pilot 出信号后拍）
> 立项提案全文：`C:\Users\yj200\.claude\plans\ccf-c-vivid-yeti.md`

## 一句话
胸片上系统横评 5 种自监督范式（world-model SSL=CheXWorld/JEPA、MAE、DINO、MoCo-v3、监督），证「范式选择非单调最优、而是 regime 依赖（标注量×域×病理×probe/finetune）」，把横评定位的系统失败 regime 操作化成轻量 fix（CPF-Gate/ReStat）。

## 读档顺序
00_README（本文）→ `01_STORY.md` → `02_ACCEPTANCE.md` → `DATA_INVENTORY.md` → 立项提案 plan 文件 → `04_LOG.md` 最新 entry。
Phase1 动手档：`PLAN/PHASE1_A_PRIME_MATRIX.md`（A′ 实验矩阵）+ `reference/SSL_RECIPES.md`（官方配方真源）+ `INTERFACE.md`（implement 多块接口契约）。

## 核心 claim（零承重命门，BMVC 形状）
- **承重**（结果朝哪落都成立）：C1 无单一最优(Friedman/CD) / C2 数据效率 gap 1% 最大 / C3 probe-finetune 解离(世界模型 linear 弱) / C4 跨域退化因范式而异。
- **stretch**（挂掉不动主贡献）：C5 方法 fix 回收增益 / C6 腐蚀+罕见病理+校准 finding。

## 红队三发致命（已修订进 plan）
1. 「首次纳入 world model 横评」已被 **X-WIN(arXiv 2511.14918)** 抢做 → 删「首次」，打 X-WIN 没做的轴(MAE/MoCo+数据效率曲线+failure taxonomy+受控重训)。
2. 纯 benchmark+软贡献进不了顶刊(arXiv 2412.19124 抢做决策指南) → 必须加真方法+反直觉经验定律。
3. 「复用 CheXWorld 省力」证伪：受控横评须 5 范式同数据/backbone/预算重训 = 真算力 ~1000 GPU·h。

## Phase 0 pilot 目标（~1-2 周，纯推理+linear-probe，不抢卡）
验核心苗头：C1(范式排名随标注量/域洗牌?)、C3(世界模型 linear 弱、finetune 追回?)、重训可行性预判。
**Gate1**：苗头可见且方向一致 + 无泄漏 + 重训路径清 → PASS 进全盘；苗头不出 → 停下报，诚实止损。

## 数据（真源 .portfolio/datasets.json）
- NIH ChestX-ray14 224²：local `project/meeting/Med-NCA/NCA-JEPA/data/nih_cxr14/images-224/images-224/`；HPC `/gpfs/work/bio/jiayu2403/nca-jepa/data/nih_cxr14/`；splits HPC `/gpfs/.../nca-jepa/splits/`(probe 1/10/100% + test=25596，患者0重叠)。
- VinDr-CXR：local `D:/YJ-Agent/data/external/vindr_cxr`（512² PNG；⚠️ 分类标签可用性待 researcher 核，NCA-JEPA 用它是 label-free）。
- CheXpert：local `project/data/external/chexpert/`（partial 762MB/11.5GB，待续下）。

## 可复用资产
- CheXWorld repo+权重：`project/meeting/复现/CheXWorld/repo/`、`assets/chexworld_pretrained.tar`、`FINETUNE.md`(官方 recipe)。
- NCA-JEPA：已有 CheXWorld JEPA 框架 + NIH 管道 + build_splits.py（`project/meeting/Med-NCA/NCA-JEPA/`）。
