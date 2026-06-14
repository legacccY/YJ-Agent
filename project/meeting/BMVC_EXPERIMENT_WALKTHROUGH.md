# BMVC 实验部分全流程走读

> 说明文档，不属于投稿物料，**不在 `meeting/BMVC/` 封印目录内**，仅做实验流程回溯 + 指针索引用。
> 对应论文：`meeting/BMVC/bmvc_final.tex`（Quality-Conditioned Temperature Scaling, QCTS）

---

## 0. 总览：实验在回答什么问题

论文核心问题（对应 `bmvc_final.tex:145` `\section{Quality-Aware Calibration}`）：

> AI 诊断模型给出的"自信度"（概率/熵），在图片质量变差时是否还可信？如果不可信，能不能用一个轻量、不重训的方法把它修回来？

实验部分要做 3 件事：
1. **造一个能测"质量-校准"关系的 benchmark**（ITB）
2. **把 10 个候选方法都跑一遍**，量出谁的校准会被图片质量带偏
3. **验证 QCTS（本文方法）是唯一修好这个关系的 post-hoc 方法**，并做跨数据集泛化 + 统计检验兜底

---

## 1. 全流程图（10 步）

```
原始数据 ISIC2020(33126) ──┬──> Step1 退化生成 (data/degrade.py)
                            │         │
                            │         v
                            │   149,100 张退化图 (light/medium/heavy)
                            │         │
                            │         v
                            └──> Step2 VisiScore-Net 打分 (train_visiscore.py)
                                      │
                                      v
                              quality_labels_all.csv (5维度 q̄)
                                      │
                                      v
                              Step3 构建 ITB (benchmark/build_itb.py)
                                      │
                                      v
                              results/itb_subsets.csv (LQ/Edge/HQ/Diverse)
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        v                              v                              v
Step4 训练 10 baseline          Step5 跑 ITB 评测              Step6 拟合 QCTS
(train_qad.py + configs)        (run_experiments.py)           (run_bmvc_experiments.py)
        │                              │                              │
        v                              v                              v
checkpoints/{stdvib,efnet,...}   results/itb_results.csv      results/qcts_itb_results.csv
                                  results/itb_predictions.csv  results/qcts_itb_predictions.csv
                                      │                              │
                                      └──────────────┬───────────────┘
                                                      v
                                      Step7 跨数据集泛化 (HAM10000/PAD-UFES zero-shot)
                                                      │
                                                      v
                                      Step8 统计检验 (bootstrap CI / McNemar / TS reversal ablation)
                                                      │
                                                      v
                                      Step9 出图 (gen_bmvc_figures.py + scripts/gen_fig*.py)
                                                      │
                                                      v
                                      Step10 出表 (scripts/gen_table1.py) → bmvc_final.tex
```

---

## Step 1：图像退化生成

**脚本**：`project/data/degrade.py`

模拟相机/拍摄条件差的皮肤镜图像，3 档强度：

| 档位 | 模糊 σ | 亮度范围 | JPEG 质量 | 裁剪比例 | 色偏强度 |
|---|---|---|---|---|---|
| light | 0.8 | 0.85-1.0 | 75-90 | 0.90-1.0 | 0.05 |
| medium | 1.5 | 0.65-0.85 | 50-74 | 0.75-0.89 | 0.12 |
| heavy | 2.5 | 0.40-0.64 | 20-49 | 0.55-0.74 | 0.22 |

定义见 `data/degrade.py:8-35`（`DEGRADATION_LEVELS`），5 种退化独立按概率叠加（`DEGRADATION_PROBS`，`data/degrade.py:38-43`）。

> ⚠️ 注：早期版本（v0）的随机裁剪曾因像素错位制造过 bug（详见 `WORKLOG.md` 会话 8），但那是 **VisiEnhance**（ICLR 项目）的坑，跟 BMVC 的退化标注流程是两条线，BMVC 这边不受影响。

无裁剪重生成版本：`project/scripts/regen_nocrop.py`（ICLR 用，BMVC 用的是原版 `degrade.py` 输出）。

---

## Step 2：质量打分网络 VisiScore-Net

**训练脚本**：`project/train_visiscore.py`
**模型定义**：`project/models/visiscore.py`
**评测脚本**：`project/eval_visiscore.py`

对 149,100 张图（原图 + light/medium/heavy 各档）打 5 维质量分：

```
SCORE_COLS = ["sharpness", "brightness", "completeness", "color_temp", "contrast"]
```
（定义见 `run_bmvc_experiments.py:48`）

聚合成单一标量 $\bar q \in [0,1]$（质量越高越接近 1）。输出：`data/quality_labels_all.csv`。
论文里报的指标：PLCC 0.924 / SRCC 0.895（见 `WORKLOG.md:122`）。

这一步是**全部下游实验的地基**——ITB 的分组、所有方法的 $\rho$(entropy, $\bar q$) 计算都依赖这个 $\bar q$。

---

## Step 3：构建 ITB（Image Triage Benchmark）

**脚本**：`project/benchmark/build_itb.py`
**输出**：`project/results/itb_subsets.csv`（columns: `subset, isic_id, image_path, target, level, source, qbar`）

4 个子集，按 $\bar q$ 严格分层 + 仅采 test split（避免训练泄漏）：

| 子集 | 条件 | n | 说明 |
|---|---|---|---|
| ITB-LQ | heavy 退化 且 $\bar q < 0.45$ | 300 | 临床关键的低质量图 |
| ITB-HQ | 原图 且 $\bar q > 0.50$ | 360 | 干净图 |
| ITB-Edge | light/medium 退化 且 $\bar q \in [0.40,0.55]$ | 660 | 边界质量 |
| ITB-Diverse | FitzPatrick17k，6 种肤色均衡采样 | ≤1500 | 跨肤色公平性 |

阈值定义见 `benchmark/build_itb.py:40-43`（`LQ_QBAR_MAX=0.45`, `HQ_QBAR_MIN=0.50`）。正例率统一调到 20%（`TARGET_POS_RATE`，`build_itb.py:38`）。

对应论文：`bmvc_final.tex:219-227`（`\subsection{Image Triage Benchmark}`）。

---

## Step 4：训练 10 个 baseline

对应论文 `bmvc_final.tex:229-235`，10 个方法（A/D/E/F/G/H/I/J/TS/QCTS）：

| 代号 | 方法 | 训练/实现入口 | checkpoint |
|---|---|---|---|
| A | EfficientNet-B3（判别式，无不确定性） | `finetune_efficientnet.py` | `checkpoints/efficientnet_b3_isic.pth` |
| D | Std VIB | `train_qad.py` + `configs/qad_*.yaml`（standard prior） | `checkpoints/stdvib/best_qad.pth` |
| E | Adaptive Prior VIB | `train_qad.py` + `models/quality_adaptive_prior.py` | `checkpoints/adaptive/best_qad.pth` |
| F | Q-VIB Full（本文/ICLR 共用底座） | `train_qvib_clean.py` → `train_qad.py`（`configs/qad_finetuned_clean.yaml`） | `checkpoints/efnet/best_qad.pth` / `checkpoints/qvib_ft_clean/` |
| G | Q-VIB + TokFT（判别变体，补充材料） | `finetune_tokenizer.py` | `checkpoints/efnet_tokft/best_qad.pth` |
| H | Focal Loss + Label Smoothing | `baselines/focal_loss_baseline.py`（MLP 1284D→256→128→2, γ=2.0, label smoothing ε=0.1） | `checkpoints/focal/best.pth` |
| I | MC Dropout（30 次前向, p=0.2） | `eval_ablation_ft.py:275 eval_mc_dropout()` | 复用 D 的 ckpt，推断时开 dropout |
| J | Deep Ensemble（5 个独立初始化的 Std VIB） | `eval_ablation_ft.py`（ensemble 评测段） | 5 套独立训练的 stdvib ckpt |
| TS | Std VIB + Temperature Scaling | `baselines/temperature_scaling.py`（单标量 T，L-BFGS 拟合 NLL） | `checkpoints/stdvib/temperature.json` |
| **QCTS（ours）** | D + QCTS | `run_bmvc_experiments.py`（见 Step 6） | 仅 2 个标量参数 $(T_0,\alpha)$，post-hoc |

核心模型代码：
- VIB encoder：`models/q_vib_encoder.py`
- 分类头：`models/qad_classifier.py`
- Adaptive Prior：`models/quality_adaptive_prior.py`

训练超参（论文 `bmvc_final.tex:281-288` `\textbf{Setup}`）：AdamW lr=1e-4, batch 128, 90 epoch, 单张 RTX 4070；EfficientNet-B3 同 schedule fine-tune。

---

## Step 5：跑全量 ITB 评测

**脚本**：`project/run_experiments.py`

```
python run_experiments.py               # 跑全部 baseline
python run_experiments.py --baseline D  # 只跑 Std VIB
python run_experiments.py --baseline TS # 只跑 Temperature Scaling
```

输入：`results/itb_subsets.csv`
输出：
- `results/itb_results.csv` —— 每个 baseline 一行汇总指标
- `results/itb_predictions.csv` —— 每个样本一行（含 `kl_term`, `prior_var`，供 Lemma 1 / Fig 5 用）

指标计算逻辑在 `benchmark/metrics.py`：
- `compute_binary_ece()`（`metrics.py:6`）—— classwise ECE，按 `prob_pos` 分桶（不是 max-confidence，因为正负样本不平衡）
- `summary_metrics()` —— 汇总 AUC / ECE / QCDI / $\rho$

**QCDI 定义**：QCDI = ECE_LQ − ECE_HQ（正值=质量越差校准越烂，负值=过修正）

---

## Step 6：拟合 QCTS（本文方法核心）

**脚本**：`project/run_bmvc_experiments.py`

3 种函数形式（对应论文 `bmvc_final.tex:420-427` functional form ablation）：

| 形式 | 代码 | 公式 |
|---|---|---|
| softplus（提案） | `qcts_softplus()` @ `run_bmvc_experiments.py:61` | $T(\bar q)=\text{softplus}(T_0+\alpha(1-\bar q))$ |
| linear | `qcts_linear()` @ `run_bmvc_experiments.py:66` | $T(\bar q)=\max(T_0+\alpha(1-\bar q),0.1)$ |
| piecewise（3 bins） | `qcts_piecewise()` @ `run_bmvc_experiments.py:71` | 按 $\bar q$<0.45 / 0.45-0.55 / >0.55 分段常数 |

拟合：`fit_qcts_multiseed()` @ `run_bmvc_experiments.py:189`，3 个随机种子独立跑 `scipy.optimize.minimize(method="L-BFGS-B", maxiter=500)`，目标是验证集 NLL（`run_bmvc_experiments.py:210-215`）。

输出：
- `results/qcts_itb_results.csv`
- `results/qcts_itb_predictions.csv`
- ICLR 重跑版本：`project/gen_qcts_iclr.py`（会话 28 新增，**不写回 BMVC 封印目录**）

5 个实验子任务（脚本头部 docstring `run_bmvc_experiments.py:3-8`）：
1. QCTS on Std VIB（D），3-seed 稳定性
2. QCTS on EfficientNet-B3（A），泛化性 demo（结果：$\alpha \approx 0$，退化成标准 TS——论文 `bmvc_final.tex:413-418` 的 boundary condition）
3. 函数形式 ablation（softplus vs linear vs piecewise）
4. 跨数据集 QCDI（HAM10000 + PAD-UFES，复用已有预测）
5. Per-degradation ECE（ITB-LQ 按退化维度拆分）

---

## Step 7：跨数据集泛化（zero-shot）

对应论文 `bmvc_final.tex:470-491` `\subsection{Cross-Dataset Generalization}`

| 数据集 | n | 输出 |
|---|---|---|
| HAM10000 | 10,015 | `results/external_ham10000_predictions.csv` |
| PAD-UFES | 2,298 | `results/external_pad_ufes_predictions.csv` |

关键数字：Q-VIB Full 的 $\rho$（entropy vs $\bar q$）在 HAM10000 = −0.164（p<10⁻⁶⁰），PAD-UFES = −0.236（p<10⁻²⁹）。
QCDI 排名一致性：ITB vs HAM10000 Kendall τ=0.71（p=0.03）；vs PAD-UFES τ=−0.43（p=0.24，因 PAD-UFES 质量分布太窄）。

分析脚本：`project/analyze_external.py`

---

## Step 8：统计检验 / 防御性 ablation

这部分是为了回应"这数字是不是凑出来的"质疑，全部脚本在 `project/scripts/`：

| 脚本 | 目的 |
|---|---|
| `scripts/attack6_forward_ablation.py` | **TS reversal 3-way forward ablation**——证明 MC vs deterministic-μ forward 是 Std VIB ρ 翻转（+0.324）的真正机制，不是 TS 本身的锅 |
| `scripts/verify_reversal_ci.py` | 给 TS reversal 结论配 bootstrap CI |
| `scripts/attack1_platt_isotonic.py` | Platt scaling / Isotonic regression 作为额外校准对照 |
| `scripts/attack5_nll_landscape.py` | NLL 优化landscape 检查（QCTS 两个 basin α≈0.35/0.96 的来源） |
| `scripts/threshold_sensitivity.py` | ITB-LQ 阈值敏感性（$\tau_{LQ}\in[0.38,0.46]$，Kendall τ≥0.78） |
| `scripts/compute_statistics_l7.py` | L7 lever 用的统计量汇总 |
| `scripts/fairness_fitzpatrick_breakdown.py` / `fairness_full_breakdown.py` | ITB-Diverse 公平性拆解（6 种肤色） |
| `scripts/run_dca_triage.py` | Decision Curve Analysis + Net Benefit（临床效用） |

Table 1 里所有 CI 由 `scripts/gen_table1.py` 统一算（1000-iter bootstrap，AUC 用 sklearn）。

---

## Step 9：出图

**主脚本**：`project/gen_bmvc_figures.py`（大文件，含全部 9 张图的绘图逻辑 + 10 个方法的配色/marker 映射表，`gen_bmvc_figures.py:50-60` 起）

补充脚本：
- `scripts/gen_fig5_perbin_T.py` → `fig5_perbin_optimal_T` / `fig5_T_curve`（QCTS 学到的 $T(\bar q)$ 曲线，3 seeds）
- `scripts/gen_reliability_diagrams.py` → `fig2_reliability`（分质量层的可靠性曲线）
- `scripts/gen_fig6_ts_reversal.py` → `fig6_qcdi_barchart`
- `scripts/gen_fig7_imagenetc.py` → ImageNet-C severity 上的泛化图
- `scripts/gen_method_figure.py` → `fig1_taxonomy`（方法分类示意图）

全部图源文件在 `project/meeting/BMVC/figures/`（pdf+png+svg 三件套）。

---

## Step 10：出表 + 整合进论文

**脚本**：`project/scripts/gen_table1.py`

读取：
- `results/itb_results.csv`（9 baseline 单 seed）
- `results/itb_predictions.csv`（per-sample，供 bootstrap）
- `results/qcts_itb_results.csv` / `qcts_itb_predictions.csv`（QCTS 行）

算出 Table 1 全部列（ITB-LQ/HQ AUC+ECE、QCDI、$\rho$，均带 95% CI），LaTeX 直接写入 `meeting/ICLR2027/table1_main.tex`（注意：会话 28 后输出已改道到 ICLR 目录，**BMVC 封印目录不再被此脚本写入**）。

论文正文表格位置：`bmvc_final.tex:324-359`（`\begin{table}...\label{tab:main}`），三条 Finding 写在 `bmvc_final.tex:295-322`。

---

## 关键产物 CSV 速查表

| 文件 | 内容 | 产生脚本 |
|---|---|---|
| `data/quality_labels_all.csv` | 全部图的 5 维质量分 + $\bar q$ | `train_visiscore.py` + `eval_visiscore.py` |
| `results/itb_subsets.csv` | ITB 4 子集成员名单 | `benchmark/build_itb.py` |
| `results/itb_results.csv` | 9 baseline 汇总指标 | `run_experiments.py` |
| `results/itb_predictions.csv` | 9 baseline per-sample 预测 | `run_experiments.py` |
| `results/qcts_itb_results.csv` | QCTS 汇总指标 | `run_bmvc_experiments.py` |
| `results/qcts_itb_predictions.csv` | QCTS per-sample 预测 | `run_bmvc_experiments.py` |
| `results/per_degradation_ece.csv` | 按退化类型拆分的 ECE（Table 2） | `run_bmvc_experiments.py` 任务 5 |
| `results/external_ham10000_predictions.csv` | HAM10000 zero-shot | `analyze_external.py` |
| `results/external_pad_ufes_predictions.csv` | PAD-UFES zero-shot | `analyze_external.py` |
| `results/itb_results_3seed_agg.csv` + `_s42/_s123/_s2024` | QCTS 3-seed 稳定性 | `run_bmvc_experiments.py` |

---

## 这部分实验对应的核心论文章节地图

```
bmvc_final.tex
├── §3 Quality-Aware Calibration (145-214)
│   ├── 3.1 Preliminaries (149)        ← VIB 公式
│   ├── 3.2 QAC and QCDI (165)         ← QCDI 指标定义
│   └── 3.3 Taxonomy (192)             ← Quality-Oblivious/Fragile/Aware 三分类
├── §4 Benchmark and Method (215-276)
│   ├── 4.1 ITB (219)                  ← Step 3
│   └── 4.2 QCTS (243)                 ← Step 6
└── §5 Experiments (277-493)
    ├── Setup (281)                     ← Step 4/5 超参
    ├── 5.1 Main Results (290)          ← Table 1, Step 5+10
    ├── 5.2 Calibration Taxonomy (361)  ← fig1/fig2
    ├── 5.3 QCTS Analysis (389)         ← Step 6 三个子分析
    ├── 5.4 Per-Degradation (429)       ← Table 2
    └── 5.5 Cross-Dataset (470)         ← Step 7
```
