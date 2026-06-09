# ICLR 2027 数据全景表

**最后更新**：2026-06-09（会话 21 登记 E1-E12 评测产物）
**适用范围**：任何会话动数据/权重/脚本前必读

> ⚠️ **路径生效规则**：`checkpoints/` 在 `D:/YJ-Agent/`（项目根级），不在 `project/`。所有数据 `data/` 在 `project/data/`。

---

## 📦 Checkpoint 清单

### 主模型权重（D:/YJ-Agent/checkpoints/）

| 模型 | 类别 | 路径 | 参数量 | 用途 | 状态 |
|---|---|---|---|---|---|
| VisiScore-Net | 5维质量评估 | `checkpoints/best_visiscore.pth` | ~5M | M1 一切实验的质量打分 | ✅ |
| Q-VIB Full (F) | 主诊断模型 | `checkpoints/efnet/best_qad.pth` | 1.3M | ICLR 主结果 | ✅ |
| Q-VIB Full seed 42/123/2024 | 鲁棒性 | `checkpoints/efnet_s{42,123,2024}/` | 1.3M ×3 | CV<2% 验证 | ✅ |
| Std VIB (D) | baseline | `checkpoints/stdvib/best_qad.pth` | 1.3M | Table 1 baseline | ✅ |
| Std VIB 5-seed | 鲁棒性 | `checkpoints/stdvib_s{42,123,2024,456,789}/` | 1.3M ×5 | Deep Ensemble baseline | ✅ |
| Adaptive Prior (E) | 消融 | `checkpoints/adaptive/best_qad.pth` | 1.3M | Q-VIB ablation | ✅ |
| MC Dropout (I) | baseline | `checkpoints/mcdropout/best_qad.pth` | 1.3M | Bayesian baseline | ✅ |
| Focal+LS | baseline | `checkpoints/focal/` | 1.3M | Calibration baseline | ✅ |
| EfficientNet-B3 (A) | 诊断基线 | `checkpoints/efficientnet_b3_isic.pth` | 4M | Direct classification baseline | ✅ |
| EDL | baseline | `project/checkpoints/edl/best_edl.pth` | 4M | Evidential learning baseline (AUC 0.8622) | ✅ |
| ResNet-50 | universality | `project/checkpoints/resnet50/best_resnet50.pth` | 23.5M | §7.5 backbone (AUC 0.884) | ✅ |
| ViT-Tiny | universality | `project/checkpoints/vit_tiny/best_vit_tiny.pth` | 5.5M | §7.5 backbone (AUC 0.903) | ✅ |
| ConvNeXt-Tiny | universality | `project/checkpoints/convnext_tiny/best_vit_tiny.pth` | 28M | §7.5 backbone | ✅ |
| Swin-Tiny | universality | `project/checkpoints/swin_tiny/best_vit_tiny.pth` | 28M | §7.5 backbone | ✅ |
| **VisiEnhance Stage 1 v0** | **增强（待重训）** | `checkpoints/visienhance/stage1/best_visienhance.pth` | 1.7M | ❌ 容量不足，M1 启动 Plan A 重训（→ ~15M）|
| **VisiEnhance Stage 1 Plan A** | M1 目标 | `checkpoints/visienhance/stage1_planA/` | ~15M | M1 D8-D21 训练 | 🆕 待训 |
| **VisiEnhance Stage 2** | M1 目标 | `checkpoints/visienhance/stage2/` | ~15M | M1 D22-D28 DP-Loss 微调 | 🆕 待训 |
| **VisiEnhance Stage 3** | M2 目标 | `checkpoints/visienhance/stage3/` | ~15M | M2 D1-D7 质量 hinge | 🆕 待训 |
| **VisiEnhance S1 Plan A 256 noFiLM** | E8 消融 | `checkpoints/visienhance/stage1_planA_256_noFiLM/best_visienhance.pth` | ~15M | E8 Q-Cond 消融（film_scale=0，best_val_psnr 30.434）| ✅（会话 21，job 1441338 TIMEOUT@ep99/200）|

### Mobile SAM 分割权重
- `checkpoints/mobile_sam.pt` — Mobile SAM 分割（Agent 工具用，已 done）

---

## 🎓 数据集清单

### 原始数据集（项目核心 4 + 跨域 4）

| 数据集 | 规模 | 路径 | 用途 | 状态 |
|---|---|---|---|---|
| ISIC 2020 | 33,126 | `data/raw/isic2020/train-image/image/` | 主训练集 | ✅ |
| FitzPatrick17k | 16,577 | `data/raw/fitzpatrick17k/images/` | 公平性 + 训练补充 | ✅ |
| HAM10000 | 10,015 | `data/external/ham10000/` | zero-shot 跨数据集 | ✅ |
| PAD-UFES | 2,298 | `data/external/pad_ufes/` | zero-shot 跨数据集（smartphone）| ✅ |
| CheXpert | TBD | `data/external/chexpert/` | cross-modality 跨域（chest X-ray）| 🚧 数据需下载 |
| APTOS-fundus | TBD | `data/external/aptos2019/` | cross-modality 跨域（diabetic retinopathy）| 🚧 数据需下载 |
| Kvasir-endoscopy | TBD | `data/external/kvasir/` | cross-modality 跨域 | ❌ M2 下载 |
| ISIC 2024 SLICE-3D | 400K | `data/external/isic2024/` | L24 real LQ smartphone-style 子集 | ❌ M2 下载 |
| DermNet | ~23K | `data/external/dermnet/` | 训练补充 / 跨域 | ✅（已爬）|

### 配对训练数据（149K）

| 产物 | 大小 | 路径 | 作用 |
|---|---|---|---|
| 配对降质数据 | 149,012 对 | `project/data/paired_dataset/{light,medium,heavy}/` | VisiEnhance Stage 1 训练 |
| EfficientNet-B0 特征 | 728 MB | `project/data/efficientnet_features.npy` (149K×1280) | 快速 Q-VIB 训练 |
| ABCD 缓存 | - | `project/data/abcd_cache.csv` (149K 行) | ABCD 规则特征 |
| 质量标签 | - | `project/data/quality_labels_all.csv` | VisiScore 训练 GT |
| ISIC 70/10/20 分割 | - | `project/data/isic_split.csv` | train/val/test 划分 |
| 专家 QC 标注 | 487 | `project/data/expert_qc_labels.csv` | 质量标注的人工校验 |

### ITB 评测基准（4 子集）

| 子集 | 规模 | 定义 | 路径 |
|---|---|---|---|
| ITB-LQ | 300 | $\bar{q} \in [0.05, 0.45]$（ISIC2020 heavy 降质）| `results/itb_subsets.csv` |
| ITB-HQ | 360 | $\bar{q} \in [0.50, 0.81]$（ISIC2020 original）| 同上 |
| ITB-Edge | 660 | 边界质量 q̄∈[0.40,0.55]（ISIC2020 light+medium 降质）| 同上 |
| ITB-Diverse | 1500 | Fitzpatrick I-VI 各皮肤色（Fitz17k original）| 同上 |
| ITB Full Pool | 2820 | 全集 | `results/itb_predictions.csv` |

### 真实低质数据（L24，M2 目标）

- `project/data/real_lq_dermoscopy/` — 21 张 (ISIC API 下载)
- `project/data/real_lq_dermoscopy_isic/` — 200 张 (ISIC 2020 + visiscore 筛选)
- ⚠️ M2 D22-D28 任务：从 ISIC 2024 SLICE-3D 挖更大规模 LQ 子集（验证可行性）

---

## 📊 关键结果 csv（主要 30+ 个）

### 主诊断结果
- `project/results/eval_report_qad.md` — Q-VIB Full 完整评估
- `project/results/itb_predictions.csv` — Std VIB ITB full pool 预测
- `project/results/itb_predictions_s123.csv` — seed 123 复现
- `project/results/itb_ablation.csv` — D/E/F + I/J ablation
- `project/results/all_qcdi_summary.csv` — QCDI 跨 method 汇总

### Universality (5 backbone)
- `project/results/backbones/section54_summary.csv` — 5 backbone × 3 method
- `project/results/backbones/{resnet50,vit_tiny,convnext_tiny,swin_tiny}/predictions.csv` — 各 backbone 推理
- `project/results/backbones/{resnet50,vit_tiny}/corruption_robustness_itb-lq.csv` — ImageNet-C × 14 corruption

### 跨域
- `project/results/external_ham10000_predictions.csv` — HAM10000 zero-shot
- `project/results/external_pad_ufes_predictions.csv` — PAD-UFES zero-shot
- `project/results/external_ablation.csv` — 跨域消融
- `project/results/crossdomain/chexray_crossdomain.{json,csv}` — CheXpert （脚本就位，待跑）
- `project/results/cross_dataset_qcdi.csv` — 跨数据集 QCDI

### BMVC QCTS
- `project/results/qcts_itb_results.csv` — QCTS 主结果
- `project/results/qcts_form_ablation.csv` — softplus / linear / piecewise / MLP form
- `project/results/qcts_quality_scalar_ablation.csv` — 5 quality scalar source
- `project/results/threshold_sensitivity.{csv,json}` — τ 阈值敏感性

### 临床
- `project/results/dca/` — DCA + Net Benefit + Triage simulation
- `project/results/forward_ablation_stdvib.{csv,json}` — A1 3-way ablation

### 公平性
- `project/results/fairness_fitzpatrick_breakdown.{csv,json}` — Fitz I-VI
- `project/results/fairness_full_breakdown.{csv,json}` — 全维度

### Failure mode
- `project/results/failure_cases.csv` — 失败案例
- `project/results/failure_mode_clusters.json` + `_v2.json` — KMeans cluster
- `project/results/failure_mode_samples.csv` — 代表性样本

### EDL baseline
- `project/results/edl/itb_metrics.json` — AUC-LQ=0.586 ECE-LQ=0.316

### VisiEnhance E1-E12 评测（会话 21，2026-06-09）
- `project/results/e1_film_ablation.json` — E1 FiLM 同口径（job 1442290）：with-FiLM per-img PSNR 32.74 / no-FiLM 33.06
- `project/results/filmabl_diag.json` — FiLM 诊断消融（job 1442337）：with-FiLM dAUC−.033 / 一致率 .90 / KL .24 vs no-FiLM −.042 / .87 / .35
- `project/results/e2_perdim.csv` — E2 分退化（job 1441320）：brightness 37.68 / blur 35.82 PASS，color_shift 33.77 / contrast 29.11 FAIL
- `project/results/e6_severe.csv` — E6 severe 安全边界（job 1441321）：dAUC−0.056 CI 排零 FAIL = triage 弹药
- `project/results/e12_speed.csv` — E12 速度（job 1441322）：16.08 ms/img
- `project/results/stage2_diag_paired_v5.csv` — E3/E7（job 1441301）：dAUC−0.012 / 一致率 0.9575 / E7 ΔAUC+0.021
- `project/results/e5_salvage.csv`（+ `e5_salvage_persample.csv`）— E5 norm-q 路由（job 1442385）：moderate SalvageRate 0.737
- `project/results/qnorm_compare.csv` — visiscore 喂法对照（job 1442379）：raw-q vs NORM-q，证现有结果有效
- `project/results/dflip_persample.csv` + `project/results/dflip_panels/*.npz` — fig_dflip v5（job 1442284）：flip 10/74

---

## 🛠️ 关键脚本（按类别）

### 训练脚本（顶层 train_*.py）
- `train_visiscore.py` — VisiScore-Net 训练
- `train_qad.py` — Q-VIB / Std VIB / Adaptive Prior 训练（config 切换）
- `train_visienhance.py` — VisiEnhance 三阶段训练（M1-M2 重点）
- `train_qvib_clean.py` — Q-VIB cleanup variant
- `train_resnet50.py` / `train_vit_tiny.py` / `train_backbone_timm.py` — Universality 训练
- `train_edl.py` — EDL baseline

### 推理/评估
- `eval_qad.py` — Q-VIB 评估
- `eval_visiscore.py` — VisiScore 评估
- `eval_visienhance.py` — VisiEnhance 评估（含 E1-E12）
- `eval_ablation.py` / `eval_ablation_ft.py` — 消融评估
- `run_experiments.py` — ITB 全部 baseline 推理
- `run_external.py` — HAM/PAD zero-shot
- `run_agent_itb.py` — Agent end-to-end 评测
- `infer_backbone.py` — 通用 backbone 推理（支持 timm 任意模型）

### VisiEnhance E1-E12 评测脚本（会话 21）
- `eval_e2_perdim.py` — E2 分退化评测
- `eval_e6_severe.py` — E6 severe 安全边界评测
- `eval_e12_speed.py` — E12 速度评测
- `eval_e5_salvage.py` — E5 norm-q 路由 SalvageRate
- `eval_qnorm_compare.py` — visiscore raw-q vs NORM-q 喂法对照
- `run_e1_ablation_hpc.py` — E1 FiLM 同口径 HPC 提交
- `run_eval_filmabl_hpc.py` — FiLM 诊断消融 HPC 提交
- `run_{e2,e6,e12,e5,qnorm}_hpc.py` — 各 E 实验 HPC 提交脚本
- `plot_e5_salvage.py` — E5 SalvageRate 图
- `render_dflip_figure.py` + `dump_dflip_figure_data.py` — fig_dflip 渲染 + 数据导出

### QCTS 相关（BMVC 复用）
- `run_qcts.py` — QCTS 主实验
- `run_qcts_ablation.py` — form ablation
- `run_qcts_backbone.py` — 跨 backbone QCTS
- `run_quality_scalar_ablation.py` — 5 quality scalar source

### Cross-domain (scripts/)
- `scripts/eval_chexray_crossdomain.py` — CheXpert
- `scripts/eval_fundus_crossdomain.py` — Fundus APTOS
- `scripts/infer_real_lq_dermoscopy.py` — 真实 LQ inference
- `scripts/test_corruption_robustness.py` — ImageNet-C

### 统计/验证 (scripts/)
- `scripts/compute_statistics_l7.py` — Cohen's d / Bonferroni / Power
- `scripts/check_numbers_consistency.py` — 论文数字一致性检查
- `scripts/run_dca_triage.py` — DCA + Triage
- `scripts/attack6_forward_ablation.py` — A1 3-way ablation
- `scripts/fairness_fitzpatrick_breakdown.py` — Fitz I-VI fairness
- `scripts/threshold_sensitivity.py` — τ 阈值
- `scripts/failure_mode_clustering.py` — KMeans k=3

### 图表生成 (scripts/)
- `scripts/gen_fig5_perbin_T.py` — fig5 per-bin T*
- `scripts/gen_fig6_ts_reversal.py` — fig6 TS reversal bar
- `scripts/gen_fig7_imagenetc.py` — fig7 ImageNet-C scatter
- `scripts/gen_method_figure.py` — 方法架构图
- `scripts/gen_reliability_diagrams.py` — reliability diagrams
- `scripts/gen_table1.py` — Table 1 LaTeX with bootstrap CI + heatmap
- `scripts/gen_uncertainty_qbar_scatter.py` — uncertainty scatter

---

## 🖼️ 论文图（report/figures/）

### VisiEnhance E1-E12 图（会话 21，2026-06-09）
- `report/figures/fig_dflip.{pdf,png}` — d-flip headline 图（v5，300 dpi，job 1442284：flip 10/74）
- `report/figures/fig_e5_salvage.{pdf,png}` — E5 SalvageRate 图（job 1442385）

---

## 📋 W1-W16 完成 vs 待跑清单

### ✅ 已完成（BMVC 复用 + 大项目前期）
- W1-W6 全部 BMVC 已完成实验（详见 `meeting/BMVC/SUBMITTED.md`）
- 5 backbone universality
- ImageNet-C 14 corruption × 5 severity
- HAM10000 / PAD-UFES zero-shot
- BMVC QCTS 完整 ablation

### 🚧 M1 (W1-W4, 2026-05-24 ~ 06-22)
- [ ] **W1**: VisiEnhance Plan A Stage 1 config（base_channels=64, mid_blocks=8）+ 启动训练（~30-40h）
- [ ] **W1**: Theorem 2 (agent risk bound) 数学推导
- [ ] **W2**: Corollary 1 (Q-VIB + QCTS ECE bound) 推导
- [ ] **W2**: CheXpert + Fundus APTOS cross-domain inference 跑完
- [ ] **W3**: VisiEnhance Stage 2 DP-Loss 微调
- [ ] **W3**: Kvasir endoscopy 数据下载 + inference
- [ ] **W4**: VisiEnhance Stage 3 quality hinge
- [ ] **W4**: Q-VIB + VisiEnhance 联合推理 → Table 1 加 row

### 🚧 M2 (W5-W8, 2026-06-23 ~ 07-22)
- [x] **W5**: E1-E3 实验（PSNR / SSIM / LPIPS / 诊断保持）— ✅ 会话 21：E1 FiLM 同口径(job 1442290) + E2 分退化(job 1441320) + E3(job 1441301)
- [~] **W5**: E4 Prop 3 验证 + E7 DP-Loss ablation — E7 ✅(job 1441301 ΔAUC+0.021)；E4 ❌ 待跑（碰重训/新数据红线）
- [x] **W6**: E5 SalvageRate + E6 安全边界 — ✅ 会话 21：E5 norm-q 路由(job 1442385, SalvageRate 0.737) + E6 severe(job 1441321, dAUC−0.056 FAIL=triage 弹药)
- [~] **W6**: E8 Q-Cond + E9 FiLM vs Cross-Attn — E8 ✅(noFiLM ckpt job 1441338) + FiLM 诊断消融(job 1442337)；E9 ❌ 待跑
- [ ] **W7**: E10 vs 6 SOTA enhancement — ❌ 待跑（碰重训/新数据红线）
- [ ] **W7**: L9 per-mechanism ablation（λ_DP / KL schedule）
- [ ] **W8**: Fitz I-VI + sex + age fairness 完整
- [ ] **W8**: ISIC 2024 SLICE-3D LQ 子集（L24）

> **E1-E12 状态汇总（会话 21）**：✅ 有数据 E1/E2/E3/E5/E6/E7/E8/E12；❌ 待跑 E4/E9/E10/E11（均碰重训/新数据红线）。另：E12 速度 16.08 ms/img(job 1441322)；qnorm_compare 喂法对照(job 1442379)；fig_dflip v5(job 1442284, flip 10/74)。

### 🚧 M3 (W9-W12, 2026-07-23 ~ 08-22)
- [ ] **W9**: 主文 9 页 draft v1（§1-§4）
- [ ] **W9**: 5+ dermatologist baseline 文献整理（L12）
- [ ] **W10**: 主文 §5-§7 + Supp 骨架
- [ ] **W10**: Cost-benefit deployment analysis（L13）
- [ ] **W11**: LLM-as-clinical-judge 200 case study（L14）
- [ ] **W11**: Anonymous GitHub + 持续 commit（L15）
- [ ] **W12**: Failure mode taxonomy + mitigation（L21）
- [ ] **W12**: Docker + reproduce.sh（L16）

### 🚧 M4 (W13-W16, 2026-08-23 ~ 09-22)
- [ ] **W13**: 10 轮 LLM adversarial review 1-3（L19）
- [ ] **W13**: ITB v1.0 + Zenodo DOI（L17）+ HF mirror（L18）
- [ ] **W14**: LLM adversarial review 4-7
- [ ] **W14**: Pre-emptive rebuttal section（L20）
- [ ] **W15**: LLM adversarial review 8-10
- [ ] **W15**: 5 轮 polish
- [ ] **W16**: 数字一致性 30/30 检查 + R1-R10 grep 扫描
- [ ] **W16**: OpenReview 上传（D-Day 2026-09-22）

---

## 🔗 数据/权重/脚本 健康检查命令

```bash
# 1. 验证主权重存在
ls D:/YJ-Agent/checkpoints/{best_visiscore.pth,best_qad.pth} \
   D:/YJ-Agent/checkpoints/efnet/best_qad.pth \
   D:/YJ-Agent/project/checkpoints/{resnet50,vit_tiny,convnext_tiny,swin_tiny}/

# 2. 验证 ITB 数据
python -c "import pandas as pd; df = pd.read_csv('D:/YJ-Agent/project/results/itb_predictions.csv'); print(df.shape, df.columns.tolist()[:10])"

# 3. 健康检查所有 backbone
python project/scripts/_inspect_backbone.py

# 4. 数字一致性检查
python project/scripts/check_numbers_consistency.py
```

---

## ⚠️ 数据 / 路径 常见坑

1. **checkpoints/ 位置混淆**：主 checkpoint 在 `D:/YJ-Agent/checkpoints/`，backbone universality 的在 `D:/YJ-Agent/project/checkpoints/`，**不一致**。M2 前可能统一到 `project/checkpoints/`，但目前先不动。
2. **swin_tiny/convnext_tiny 文件名**：用了 `best_vit_tiny.pth` 当文件名（命名 bug，存的是 swin/convnext 权重），不要被骗。
3. **VisiEnhance Stage 1 现有权重不够用**：1.7M 参数容量不足，Plan A 必须重训 ~15M 版本，旧权重仅作起点参考（不可直接用于 E1 论文数字）。
4. **配对数据 paired_dataset/**：3 难度（light/medium/heavy）× 各 ~49K 对，total 149K，已就位。但 ISIC 2024 SLICE-3D 加入后要扩。
5. **ITB 4 子集定义**：在 `results/itb_subsets.csv`，不要直接看 itb_predictions.csv 当真值（后者是预测，前者是 subset 定义）。
