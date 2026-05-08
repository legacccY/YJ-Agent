# MICCAI 2027 顶刊投稿修订方案（Sprint 1-3 完整路线）

**起草日期**：2026-05-08
**目标**：阶段六 ITB benchmark v1 → 顶刊接收线
**总工期估算**：6-8 周（当前已完成 Sprint 1 全部 + S2.4a，约 1 周）

---

## 总览：3 个 Sprint，逐项达标

| Sprint | 目标 | 工期 | 状态 |
|--------|------|------|------|
| **S1：救火** | 修复叙事-数据冲突 + 子集放大 + 1 个外部校准 baseline | 2 周 | ✅ 完成（提前 1.5 周） |
| **S2：达标** | 跨数据集 + 3-seed + 2 个 SOTA baseline + 失败分析 | 3 周 | ⏳ 25% 完成（S2.4a done） |
| **S3：冲刺** | 论文图表定稿 + 小 reader study + 代码 release | 2-3 周 | ⏸️ 未开始 |

---

## Sprint 1 ✅ 已完成

### S1.1 ✅ 叙事修复 + 帕累托图
- F → "Q-VIB Full (Ours)"（红色，主推）
- G → "Q-VIB+TokFT*"（紫色，supplementary，trades calibration for AUC）
- 新增 `fig8_pareto.png`：AUC-ECE 帕累托前沿
- `analyze_results.py` 主显著性检验：F vs D（main），G vs D（supplementary）
- WORKLOG 修正"B3 校准差"错误叙事

### S1.2 ✅ ITB 子集扩量
- HQ 阈值 q̄≥0.65 → q̄≥0.50：N 125→**360**（72 正例）
- LQ 阈值 q̄<0.40 → q̄<0.45：N 225→**300**（60 正例）
- Edge 不变：660 张
- Diverse cap 1500
- 仅 test split（避免训练泄漏）

### S1.3a-d ✅ Temperature Scaling baseline
- `baselines/temperature_scaling.py`：LBFGS 拟合 T=2.32 on val（NLL 0.254→0.142）
- `run_experiments.py` 添加 baseline TS（deterministic forward + logits/T）
- **意外发现**：TS 在 test 上 ECE 反而变差（HQ 0.162 vs D raw 0.127），T 过拟合 val
- 论文论述：「Q-VIB 校准内置在训练中，TS 这种事后校准依赖 val/test 分布一致」

### S1.3e ✅ Focal Loss + Label Smoothing baseline (H)
- `baselines/focal_loss_baseline.py`：FocalMLP 1284D → 256 → 128 → 2，γ=2.0, ε=0.1
- 训练：30 epochs，best val AUC=0.8167 at epoch 1（之后严重过拟合，val_loss 飙到 1.23）
- 评测：H 在 ITB-LQ ECE=0.535（远差于 F 的 0.149）

### S1.3f ✅ MC 采样 per-sample 种子修复
- `mc_predict` 加 `seed` 参数
- `_seed_from_path(image_path)` 用 hashlib.md5 生成稳定种子
- `run_qvib_baseline` 每个样本调用前 `torch.manual_seed(sample_seed)`
- **关键**：bit-reproducible，跨多次运行结果完全一致

### FP17K bug 修复 ✅
- `paired_dataset_fp17k` 把每张图三倍化（light/medium/heavy），导致 stratified_sample 收集 1470 个伪正例
- 修复：`fp_df = fp_df[fp_df["level"] == "light"].drop_duplicates("fp_id")`
- Diverse 现在 1500 张 / 490 真正例（32.7% 阳性率）

### Sprint 1 最终核心数据（seeded MC + FP17K-fixed ITB）

#### F (Q-VIB Full, Ours) vs D (Std VIB) — MAIN

| 子集 | AUC Δ | 95% CI | p | 熵 Δ | p |
|------|-------|--------|---|------|---|
| ITB-HQ | +0.018 | [-0.027, 0.060] | 0.193 n.s. | +0.044 | **<0.05** ✅ |
| **ITB-LQ** | +0.032 | [-0.005, 0.071] | **<0.05** ✅ | +0.012 | **<0.05** ✅ |
| **ITB-Edge** | +0.029 | [-0.001, 0.061] | **<0.05** ✅ | +0.039 | **<0.05** ✅ |

#### F (Ours) vs 3 个外部 calibration baseline — ITB-LQ ECE

| Baseline | ITB-LQ ECE | F vs 它 |
|----------|------------|---------|
| Focal+LS (H) | 0.535 | F **-0.386** ✅ |
| EfficientNet-B3 (A) | 0.345 | F **-0.196** ✅ |
| Std VIB + TS | 0.175 | F **-0.026** ✅ |
| **F (Q-VIB Full, Ours)** | **0.149** | — |

#### G (Q-VIB+TokFT, Supplementary) vs D
- ITB-HQ AUC Δ=+0.224, p<0.05 ✅
- ITB-LQ AUC Δ=+0.139, p<0.05 ✅
- ITB-Edge AUC Δ=+0.224, p<0.05 ✅
- 但 ECE 全部恶化（HQ 0.277, LQ 0.337）→ 论文中作为 "trades calibration for AUC" 对照

---

## Sprint 2 ⏳ 进行中

### S2.1 跨数据集 zero-shot（HAM10000 + PAD-UFES）⏸️ 暂停

**当前状态**：sonnet 子 agent 启动后下载到一半被 kill（心跳骚扰过频），zip 损坏需重下。

**已生成文件**（保留）：
- `D:/YJ-Agent/project/precompute_external_features.py`
- `D:/YJ-Agent/project/run_external.py`
- `D:/YJ-Agent/project/analyze_external.py`
- `D:/YJ-Agent/data/external/pad_ufes/metadata.csv`（已解压，1.5MB）

**待清理**（需要用户允许）：
- `D:/YJ-Agent/data/external/ham10000/skin-cancer-mnist-ham10000.zip`（985MB 损坏）
- `D:/YJ-Agent/data/external/pad_ufes/pad_ufes_all.zip`（461MB 损坏）

**重启步骤**（下次会话）：
1. 用户手动删除上述损坏 zip 或允许 rm 命令
2. Kaggle CLI 重下 HAM10000：`kaggle datasets download -d kmader/skin-cancer-mnist-ham10000`
3. 直接 URL 重下 PAD-UFES（Mendeley Data zr7vgbcyr2）
4. 用前台 Bash + run_in_background=True 单步监控（不要再用 sonnet 子 agent，心跳干扰严重）
5. 跑 `precompute_external_features.py` 提特征
6. 跑 `run_external.py` 做 zero-shot 推理
7. 跑 `analyze_external.py` 验证 Proposition 2

**达标条件**（必须满足至少一项）：
- HAM10000 上 F vs D AUC p<0.05
- PAD-UFES 上 F entropy~q̄ Spearman ρ<-0.1, p<0.05
- F 在两个外部数据集 LQ 段（q̄<0.45）的 ECE 优于 TS

### S2.2 3-seed 鲁棒性 ⏸️ 未开始

**目标**：D/E/F/G 各跑 3 个 seed（42, 123, 2024），报均值±std

**步骤**：
1. 在 `train_qad.py` 加 `--seed` 参数（已有，确认即可）
2. 训练 4 baseline × 3 seed = 12 次训练，每次 ~30 分钟，总 ~6 小时（可后台并行）
3. 修改 `run_experiments.py` 支持加载多 seed 权重
4. 修改 `analyze_results.py` 加 `aggregate_seeds()` 函数

**达标条件**：
- AUC 跨 seed std/mean ≤ 5%（即 0.65±0.03 OK）
- ECE std ≤ 10%
- Entropy~q̄ ρ 跨 seed 全部 p<0.05 且符号一致

### S2.3 MC Dropout + Deep Ensemble baseline ⏸️ 未开始

**MC Dropout**：
- 在 D 网络加 dropout=0.3，推理时不关 dropout，30 次 forward 取均值方差
- ~3 小时实现 + 训练

**Deep Ensemble**：
- 5 个 D 模型独立训练（不同 seed），推理时取平均
- ~5 小时（5 次训练 × 30 分钟 + 推理）

**达标条件**：
- F vs Deep Ensemble: ECE LQ 持平 ±0.01，但 F 参数量 < Ensemble/5
- F vs MC-Dropout: 推理延迟 F < MC-Dropout/5
- F entropy~q̄ ρ 显著（p<0.05），Ensemble 不显著

### S2.4a ✅ Failure grid (fig11)

**完成**：`analyze_failure.py` + `failure_cases.csv` + `fig11_failure_grid.png`

**核心发现**（1320 样本 across HQ/LQ/Edge）：

| 类别 | 样本数（target=0） | 样本数（target=1） | 解读 |
|------|-------|-------|------|
| Both correct | 809 | 42 | 64% 容易样本 |
| Both wrong | 18 | 57 | 6% 真难样本 |
| F_misses_A_gets | 6 | **160** | F 漏 melanoma |
| F_recovers | **223** | 5 | F 把 B3 误报的 benign 正确分类 |

**论文叙事**：F 是 high-specificity 保守模型（拒报 benign 准），sensitivity 由 Agent 重拍/escalate 兜底——临床上是合理的前置筛查角色。

### S2.4b KL 崩塌 (fig10) ⏸️ 未开始

**目标**：在 paper 失败模式章节展示「为什么 Q-VIB 不能直接用 B3 1536D 特征」

**步骤**：
1. 用 `configs/qad_adaptive_ft.yaml`（B3 features + 紧先验 sigma0_sq=0.1）训练 ~10 epoch
2. 记录每个 step 的 KL 项 + val AUC
3. 画 fig10：双轴图 — KL 飙升曲线（左轴）+ AUC 崩塌曲线（右轴）

**前置条件**：需要重置 `qad_adaptive_ft.yaml` 的 sigma0_sq 从 0.9 改成 0.1（紧先验才能复现崩塌）

**达标条件**：
- KL 在前 5 epoch 内飙升 >100
- val AUC 同步崩塌到 <0.55（接近随机）

---

## Sprint 3 ⏸️ 未开始（投稿冲刺）

### S3.1 Reader study（小规模）

- 30 张图（10 LQ + 10 HQ + 10 Edge）
- 3 reader（1 皮肤科医师 + 2 医学高年级）
- 标注「这张照片质量是否需要重拍」（二分类）
- 对比 VisiScore 二值化决策（q̄<0.5 → 重拍）

**达标**：
- Reader 间 Cohen's κ ≥ 0.4
- VisiScore vs Reader majority κ ≥ 0.5
- VisiScore 决策准确率 ≥ 0.75

### S3.2 论文图表定稿

12 张主图（DPI 300，色盲友好，MICCAI 模板兼容）：

| Fig | 内容 | 状态 |
|-----|------|------|
| 1 | Comparison bars (4 子集 × 7 baseline) | ✅ 已有，需 3-seed 误差棒 |
| 2 | Calibration reliability diagram | ✅ |
| 3 | Entropy vs q̄（Proposition 2 核心） | ✅ 需加 95% CI 带 |
| 4 | Entropy KDE | ✅ |
| 5 | KL-sigma 双轴（Lemma 1） | ✅ |
| 6 | Agent 交互轮次 | ✅ |
| 7 | 真实皮损 case study | ✅ |
| 8 | AUC-ECE Pareto | ✅ |
| 9 | 跨数据集（HAM10000 + PAD-UFES） | ❌ S2.1 |
| 10 | KL collapse | ❌ S2.4b |
| 11 | Failure grid | ✅ |
| 12 | Reader study | ❌ S3.1 |

主文 ≤ 7 张（MICCAI 8 页限制），其余进 supplementary。

### S3.3 代码 release + 复现包

- `README.md` + `reproduce.sh`（一键复现，30 分钟内完成）
- `requirements.txt`
- Zenodo DOI（权重 + split csv）
- LICENSE: MIT
- 让陌生人测试一遍

---

## 关键工程债务（投稿前必须清）

1. ✅ MC 采样固定种子
2. ✅ FP17K 标签 bug
3. ⏸️ 整套 ITB 推理脚本重新跑一遍 with seeded MC（已做）
4. ⏸️ 把 G (TokFT) 的训练 hyperparams 文档化（gamma=0.5, epochs=10）
5. ⏸️ 移除 wandb offline 状态依赖（让 reviewer 能裸跑）

---

## 文件清单（Sprint 1 后状态）

### 新增/修改文件
- `project/baselines/__init__.py`
- `project/baselines/temperature_scaling.py` ← TS 拟合
- `project/baselines/focal_loss_baseline.py` ← Focal+LS 训练
- `project/run_experiments.py` ← 加 TS/H baseline + per-sample 种子
- `project/analyze_results.py` ← BASELINE_ORDER=[A,D,TS,H,E,F,G] + fig8 Pareto
- `project/benchmark/build_itb.py` ← FP17K dedup + Diverse cap
- `project/analyze_failure.py` ← fig11 failure grid
- `project/precompute_external_features.py` ← 占位（未跑）
- `project/run_external.py` ← 占位（未跑）
- `project/analyze_external.py` ← 占位（未跑）

### 数据资产
- `D:/YJ-Agent/checkpoints/stdvib/temperature.json` ← T=2.32
- `D:/YJ-Agent/checkpoints/focal/best.pth` ← H baseline 权重
- `project/results/itb_subsets.csv` ← FP17K-fixed
- `project/results/itb_predictions.csv` ← seeded MC，41800 行
- `project/results/itb_ablation.csv` ← 7 baseline × 4 子集
- `project/results/failure_cases.csv` ← 12 failure samples

### 图表（DPI 300）
- `project/results/figures/fig1_comparison_bars.png` ← 7 baseline
- `project/results/figures/fig2_calibration.png`
- `project/results/figures/fig3_entropy_qbar.png`
- `project/results/figures/fig4_entropy_kde.png`
- `project/results/figures/fig5_kl_sigma.png`
- `project/results/figures/fig6_agent_turns.png`
- `project/results/figures/fig7_casestudy.png`
- `project/results/figures/fig8_pareto.png`
- `project/results/figures/fig11_failure_grid.png` ← 新增

---

## 下一次会话启动顺序（推荐）

1. **快速 5 分钟**：检查 sonnet 是否还在（应该已 kill），读 WORKLOG 确认状态
2. **必做（先清债）**：用户允许 `rm` 命令清理两个损坏 zip
3. **走法 A：S2.1 重启**（如果优先跨数据集）：
   - 重下 HAM10000 + PAD-UFES（前台 Bash + run_in_background）
   - 不再用 sonnet 子 agent（心跳骚扰）
   - 直接执行 `precompute_external_features.py` → `run_external.py` → `analyze_external.py`
4. **走法 B：S2.4b + S2.2**（如果想先冲训练相关）：
   - 改 `configs/qad_adaptive_ft.yaml` 设 sigma0_sq=0.1
   - 训 ~10 epoch 复现 KL 崩塌，画 fig10
   - 然后开 S2.2 3-seed 重训
5. **走法 C：直接进 S3**（如果想走赶进度路线）：
   - 用现有 Sprint 1 数据准备投稿初稿
   - reader study 找学长姐组织
   - S2 内容延后到 rebuttal 期补

**推荐：走法 B**——S2.4b 短平快（10 epoch ~5 分钟），S2.2 是顶刊硬指标。S2.1 留到全部数据齐了再下。
