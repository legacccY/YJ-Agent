# PHASE 1 — Benchmark 主干（回填存档，✅ PASS）

> **状态**：✅ PASS（2026-06-25，`04_LOG.md` Entry 10）。本文件为**回填存档**，价值 = camera-ready 复现追溯 + 数据潜在问题清单留痕（防一审追问/防自己忘坑）。

---

## ① 阶段目标 & 服务哪条 Claim/lever

**目标**：跑通统一 benchmark 主干——5 方法 × 2 数据集 × 5 标注比例 × 3 seed，结果落 csv，构成论文 lever ① 的地基。
**服务**：核心 Claim 的「**统一评测协议**」支柱（引自 `01_STORY.md`）；对齐 `02_ACCEPTANCE.md` 的 **lever ①（统一 benchmark 真跑通）+ lever ④（数字可复现）**。

---

## ② 输入 / 前置依赖

- **数据**：PSFHS（✅ Zenodo 10969427，2716 .mha）+ HC18（✅ Zenodo 1322001，779 主视角 `_HC.png`）。详见 `DATA_INVENTORY.md`。
- **方法实现**：SSL4MIS 官方超参（`reference/SSL4MIS_hparams.md`，researcher 复现零偏离核过）。
- **harness**：`src/datasets.py` + `harness.py` + `run_matrix.py` + `unet.py`（results.csv + state.json 续跑）。
- **算力**：XJTLU HPC `gpu4090`，env `yjcu124py310`（torch2.6+cu124），绝对 python 路径。

---

## ③ 任务分解（run 矩阵）

**矩阵 = 5 方法 × 2 集 × 5 比例 × 3 seed = 150 run**（~12-18 GPU·h）。

| 维度 | 取值 |
|---|---|
| 方法（5） | `supervised` / `mean_teacher` / `cps` / `uamt` / `fixmatch` |
| 数据集（2） | `psfhs`（PS 耻骨联合 + FH 胎头，双结构）/ `hc18`（head 胎头围，单结构） |
| 标注比例（5） | 1% / 2% / 5% / 10% / 20% |
| seed（3） | 0 / 1 / 2 |

**HPC 执行策略**：切 **10 chunk（method × dataset，各 15 run ~2.5h，`--time=4h`）**——4h chunk 比 24h monolith 易 backfill 插队。各 chunk 经 `RESULTS_TAG` 写自己 `results_<m>_<ds>.csv` + `state_<m>_<ds>.json` 防并发写竞争，跑满后 `hpc/merge_results.py` 合并。脚本固化在 `hpc/`（poll_chunks.py / sbatch_chunk.sh / merge_results.py）。

---

## ④ DoD 验收阈值（已达）

> 阈值真源 = `02_ACCEPTANCE.md` § Phase 1。本节只记**实测自检命令 + 结果**，不复制阈值定义。

```bash
# 1. master_wide 满 150 数据行（含 header 151）
tail -n +2 results/master_wide.csv | wc -l        # 期望 150 ✅
# 2. master_long 满 225 数据行（PSFHS 双结构展开 + HC18 单结构）
tail -n +2 results/master_long.csv | wc -l        # 期望 225 ✅
# 3. 无 NaN / 空 dice
grep -i "nan" results/master_wide.csv | wc -l     # 期望 0 ✅
# 4. 每 combo(method×dataset×ratio) 满 3 seed
cut -d, -f1-3 results/master_wide.csv | tail -n +2 | sort | uniq -c | awk '$1!=3'  # 期望空 ✅
# 5. held-out split 无交集（代码核 train/test 文件名无重叠）
#    → datasets.py split 固定 seed，HC18 去多视角防泄漏（见 ⑤ 坑3）
```

- ✅ master_wide 150 行 / master_long 225 行（Grep 核实 2026-06-25：wide 151 含 header / long 226 含 header）。
- ✅ 无 NaN、无崩，10 chunk 全 done。
- ✅ held-out test 固定 seed，不泄漏。
- ✅ 标注效率曲线画出（`figures/fig_efficiency_curves.pdf`）。
- **判定**：`02_ACCEPTANCE.md` § Phase 1 PASS 条件全满足 → **PASS**。

---

## ⑤ 数据潜在问题清单（仿 BMVC 留痕，camera-ready 须如实写入 limitation/supplementary）

| # | 问题 | 根因 | 处置 | 影响评估 |
|---|---|---|---|---|
| **坑1** | HC18 mask 填充错（前景占比仅 5.9%，2px 椭圆轮廓被 findContours 碎段，fillPoly 只填环不填盘） | HC18 GT 是椭圆参数 CSV 不是实心 mask | **修：`cv2.fitEllipse` 拟合轮廓点 → 画实心椭圆（thickness=-1）**。修后前景占比中位 **18.6%**（合理胎头面积）；smoke 实证 supervised hc18 10% dice_head=**0.8895** 坐实修复正确 | 修复前所有 HC18 结果作废；修复后有效。**须在 supplementary 写明 HC18 mask 由椭圆参数重建** |
| **坑2** | HC18 配对 779 ≠ 999 | 220 个多视角 `_2HC.png` glob 未匹配 | **有意保留 779 主视角**——多视角 = 同患者另一切面，混 train/test 会泄漏（R2 红线） | 防泄漏正确处置，非 bug。须写明「单视角去重」 |
| **坑3** | PSFHS @1% UAMT 高方差（seed Dice 0.26/0.49/0.81） | 1% = 6 图训练，固有随机性 | **非 bug**，照实报；n=3 seed 部分格 CI 宽功效有限 | 须在 limitation 写「极低标注区方差大、功效有限」，不夸大 |
| **坑4** | sbatch `python: command not found` 全 5 方法崩 | 假设的 `conda.sh` 路径不存在，conda activate 没生效 | **修：用绝对 python 路径 `/gpfs/.../yjcu124py310/bin/python`，不靠 activate** | env 工程坑，已修，不影响结果有效性 |

---

## ⑥ 对齐哪条 ACCEPTANCE

`02_ACCEPTANCE.md` § **Phase 1 — benchmark 主干**（PSFHS+HC18，5 方法 5 比例 ≥3 seed，held-out 不泄漏，PASS = 完整矩阵无 NaN/崩 + 效率曲线画出）。**FAIL 条件**（某方法复现不出/崩 → 查官方实现不私改超参凑）未触发。

---

## ⑦ 佐证引用（带出处）

- **半监督方法超参**：SSL4MIS 官方实现（`reference/SSL4MIS_hparams.md`）——CPS consistency=0.1/rampup=200、UAMT ema=0.99/T=8、FixMatch conf_thresh=0.8。**复现零偏离**（`feedback_repro_zero_deviation`）。
- **PSFHS 数据集**：Zenodo 10969427（免申请，132MB，1358 图 + 像素 mask）。
- **HC18 数据集**：Zenodo 1322001（999 训 + 335 测，椭圆轮廓 GT）。
- **ACCV 2026 接受 benchmark 类**：官方 CFP 接受「Datasets and Performance Analysis」（accv2026.org），dataset 须 camera-ready（2026-10-04）前公开。

---

## ⑧ 预期产出物清单（已交付）

- `results/master_wide.csv`（150 run，每 run 一行：method/dataset/label_ratio/seed/dice_mean/hd95_mean/n_labeled/n_unlabeled/n_test/train_time_min）
- `results/master_long.csv`（225 行，per-structure 展开：+ structure/dice 列，供 PS/FH 不对称分析）
- `src/`：datasets.py / harness.py / run_matrix.py / unet.py
- `hpc/`：poll_chunks.py / sbatch_chunk.sh / sbatch_full.sh / hpc_chunk_submit.py / merge_results.py
- `reference/SSL4MIS_hparams.md`（超参来源留痕）

---

## ⑨ 完成判定（5 步流程）

1. 查 `02_ACCEPTANCE.md` § Phase 1 验收阈值。
2. 逐条跑 ④ 的自检命令对照实际产出。
3. 全条 PASS → 写 `04_LOG.md`（已记 Entry 10）+ 移 Phase 2。
4. 跑反跑偏检查：确认无泄漏（坑2/坑3 处置）、无 NaN、数字 Grep 核 csv 非 Read。
5. **不存在「基本完成」**——10 chunk 全 done 满 150 才判 PASS。已达 → **PASS 存档**。
