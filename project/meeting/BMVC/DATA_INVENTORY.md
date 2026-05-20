# BMVC 数据全景表（实验资产清单）

**用途**：所有写作 / 表格 / 图表前先来这里查数据是否已就位
**最后更新**：2026-05-20

---

## 📊 训练好的 backbone（5 个）

| Backbone | Best AUC (val) | Checkpoint | 状态 |
|---|---|---|---|
| EfficientNet-B3 (deterministic) | 0.938 (HQ) | `project/checkpoints/efficientnet_b3/best.pth` | ✅ 在 Table 1 |
| Std VIB (EfficientNet-B0 + VIB) | 0.587 (HQ) | `project/checkpoints/std_vib/best.pth` | ✅ 在 Table 1 + Table 3 |
| MC Dropout (Std VIB + dropout 0.2) | 0.808 (HQ) | 共享 Std VIB | ✅ 在 Table 1 |
| Deep Ensemble (5× Std VIB) | 0.868 (HQ) | `project/checkpoints/std_vib_seed{1..5}/` | ✅ 在 Table 1 |
| Focal+LS | 0.884 (HQ) | `project/checkpoints/focal_ls/best.pth` | ✅ 在 Table 1 |
| **ResNet-50** | 0.9035 (HQ) | `project/checkpoints/resnet50/best.pth` | ✅ 在 Table 3 |
| **ViT-Tiny (DeiT)** | 0.9261 (HQ) | `project/checkpoints/vit_tiny/best.pth` | ✅ 在 Table 3 |
| **EDL (EfficientNet-B3 + Dirichlet)** | 0.8622 | `project/checkpoints/edl/best_edl.pth` | 🚧 ITB infer 未跑 |

---

## 📁 已生成结果 csv（10 个核心数据源）

| 文件 | 内容 | 用于 |
|---|---|---|
| `results/itb_predictions.csv` | 全 baseline ITB 预测 | Table 1 |
| `results/qcts_params.json` | QCTS (T₀, α) 拟合参数 | §5.3 / §5.4 |
| `results/qcts_itb_results.csv` | QCTS 在 ITB 各分层的 ECE/QCDI | Table 1 / Table 3 |
| `results/per_degradation_ece.csv` | 5 quality dim 维度 ECE breakdown | fig3 / §5.3 |
| `results/backbones/section54_summary.csv` | 3 backbone × {raw/TS/QCTS} × {ECE/QCDI/ρ/AUC} | **Table 3** |
| `results/backbones/resnet50/itb_predictions.csv` | ResNet-50 ITB logits | Table 3 |
| `results/backbones/vit_tiny/itb_predictions.csv` | ViT-Tiny ITB logits | Table 3 |
| `results/backbones/resnet50/corruption_robustness_itb-lq.csv` | ResNet-50 × 14 corruption × 5 severity | **§5.5 ImageNet-C** |
| `results/backbones/vit_tiny/corruption_robustness_itb-lq.csv` | ViT-Tiny × 14 corruption × 5 severity | **§5.5 ImageNet-C** |
| `results/hamzero_predictions.csv` | HAM10000 zero-shot 预测 | §5.6 / fig4 |
| `results/padzero_predictions.csv` | PAD-UFES zero-shot 预测 | §5.6 / fig4 |

---

## 🖼️ 已生成图（论文使用 + 备份）

| 图 | 文件（pdf/svg/png） | 论文位置 | 状态 |
|---|---|---|---|
| fig1_teaser | `figures/fig1_teaser.*` | Intro | ✅ |
| fig2_problem | `figures/fig2_problem.*` | §5.2 | ⚠️ METHOD_META 含 F/G，待重跑 |
| fig3_qcts | `figures/fig3_qcts.*` | §5.3 | ✅ |
| fig4_generalization | `figures/fig4_generalization.*` | §5.6 | ⚠️ METHOD_META 含 F/G，待重跑 |
| fig5_perbin_optimal_T | `figures/fig5_perbin_optimal_T.*` | §5.4 (a) | ✅ |
| fig6_ts_reversal | `figures/fig6_ts_reversal.*` | §5.4 (b) | ✅ |
| fig7_imagenetc_reversal | 待生成 | §5.5 | ❌ 待 D2-D4 |
| fig_method | `figures/fig_method.{pdf,svg}` | §4 method overview | ⚠️ 含 VisiScore-Net，svg 待重跑 |

历史图（保留作备份，论文不引用）：
- fig0_teaser / fig1_taxonomy / fig2_reliability / fig3_degradation / fig4_entropy_qbar / fig5_T_curve / fig6_qcdi_barchart / fig7_threshold_sensitivity

---

## 📐 已完成实验 vs 待跑（与 ACCEPTANCE_CRITERIA 对应）

### W1 (D1-D7)
- ✅ §5.4 backbone universality（5 backbone × {raw/TS/QCTS}）
- ✅ ImageNet-C 18 corruption × 5 severity 推理 + §5.5 章节写完
- ✅ fig5 / fig6 / fig7 生成
- ✅ EDL ITB 推理（AUC-LQ=0.586, ECE-LQ=0.316, QCDI=+0.046）
- ✅ 4 主图 METHOD_META 清理（生成 SVG 无 Q-VIB/VisiScore 残留）
- ✅ fig_method.svg VisiScore-Net 注释替换

### W2 (D8-D14) — 全部完成
- ✅ 过度参数化消融（softplus/linear/piecewise/bin10/dimwise/MLP）→ table2_ablation.tex
- ✅ 5 种 quality scalar 对比（5-head IQA best, BRISQUE collapse α=0）→ table3_quality_scalar.tex
- ✅ CheXpert 跨域推理（DenseNet-121, ρ=-0.971, 无 TS 反转）→ chexray_crossdomain.json
- ✅ L7 Cohen's d + Bonferroni + Power（d=+0.452 QCTS, power=0.929）→ statistics_l7.json

### W3 (D15-D21) — 部分提前完成
- ✅ Fundus 跨域（APTOS 2019, ViT-DR, ρ=+0.259, 弱 QA）→ fundus_crossdomain.json
- 🟡 公开真实低质 dermoscopy 采集（21/200 张，下载进行中）→ data/real_lq_dermoscopy/
- ❌ MC Dropout + Deep Ensemble variance vs q̄ 散点 + bootstrap ρ
- ❌ Sub-population fairness 全维度

### W4 (D22-D28) — 部分提前完成
- ✅ DCA + Triage simulation + Published dermatologist baseline（Haenssle 2018）→ results/dca/
- ✅ §5.6 cross-modality 段落 + Limitations DCA 数字更新
- ❌ Theory section 1 页（softplus uniqueness + IB connection + PAC-Bayes）

### W5 (D29-D35)
- ❌ Failure mode auto-clustering（HDBSCAN on confidently-wrong embedding）
- ❌ 10-12 主图 + 20+ supplementary 图迭代

### W6-W8
- ❌ LLM adversarial review × 5 轮
- ❌ Supplementary 30-50 页
- ❌ Code/Docker release 工程化

---

## 🔧 关键脚本路径（任何重跑都用这些）

| 脚本 | 用途 |
|---|---|
| `project/run_qcts.py` | QCTS 拟合 + ITB 评测主流水 |
| `project/run_qcts_backbone.py` | 多 backbone QCTS（4 backbone 通用） |
| `project/infer_backbone.py` | 任意 backbone ITB 推理 |
| `project/train_resnet50.py` + `configs/resnet50.yaml` | ResNet-50 训练 |
| `project/train_vit_tiny.py` + `configs/vit_tiny.yaml` | ViT-Tiny 训练 |
| `project/train_edl.py` + `configs/edl.yaml` | EDL 训练 |
| `project/scripts/test_corruption_robustness.py` | ImageNet-C 14×5 corruption 推理 |
| `project/scripts/gen_fig5_perbin_T.py` | fig5 生成 |
| `project/scripts/gen_fig6_ts_reversal.py` | fig6 生成 |
| `project/gen_bmvc_figures.py` | fig{1,2,3,4} 生成（METHOD_META 待清理） |
| `project/scripts/gen_table1.py` | Table 1 LaTeX 生成器 |
| `project/scripts/infer_edl_itb.py` | EDL ITB 推理（待写，D2 任务） |

---

## 🔬 数据集元信息

| 数据集 | 大小 | 用途 | 路径 |
|---|---|---|---|
| ISIC 2020 | 33,126 | 主训练集（70/10/20） | `project/data/isic2020/` |
| HAM10000 | 10,015 | Zero-shot 评测 | `project/data/ham10000/` |
| PAD-UFES | 2,298 | Zero-shot 评测 | `project/data/pad_ufes/` |
| FitzPatrick17k | 16,577 | Fairness（ITB-Diverse） | `project/data/fitzpatrick17k/` |
| ITB-LQ | 300 | 低质子集（q̄ < 0.45） | `project/data/itb/lq/` |
| ITB-Edge | 660 | 边界子集（q̄ ∈ [0.40, 0.55]） | `project/data/itb/edge/` |
| ITB-HQ | 360 | 高质子集（q̄ > 0.50） | `project/data/itb/hq/` |
| ITB-Diverse | 1,500 | Fitzpatrick I-VI | `project/data/itb/diverse/` |
| 5-head IQA train pool | 149,100 | IQA module 训练 | `project/data/iqa_train/` |

---

## ⚠️ 数据潜在问题（写作时避免）

1. **`section54_summary.csv` 第一行 ViT-Tiny 字段错位**（raw_rho 解析为 0.0277 实为 -0.1596）
   - 修复方案：写作时只用第三行 `ViT-Tiny (DeiT)` 数据，或重跑 csv 生成脚本

2. **EDL 训练完但未推 ITB**（Table 1 EDL 行 TBD）
   - D2 任务

3. **fig_method.svg 含 "VisiScore-Net"** 但 .tex 已改 "5-head IQA"
   - D5 任务（重跑 fig_method 生成）

4. **fig{2,3,4} METHOD_META 含 F/G 条目**（Q-VIB 系列）
   - D5 任务（修 `gen_bmvc_figures.py` METHOD_META + 重跑）

5. **Table 3 Edge / Diverse 列 ResNet-50/ViT-Tiny 缺**（csv 字段空）
   - 不影响 Table 3，只用 LQ/HQ 列
