# 工作日志（快速指针）

**最后更新**：2026-05-21（第四次会话）| **完整进度**：见 `D:/YJ-Agent/project/PROJECT_OVERVIEW.md`

---

## 🎯 当前焦点

- **BMVC 投稿** | Deadline 假设 2026-07-15（**55 天**）| 状态：**主文 14 页正中 / W6 Round 2-5 写作打磨已合并完成 / 表格 caption 干涉修复** — 剩 Anonymous GitHub push + Zenodo DOI
- **大项目** | VisiEnhance Stage 1 容量问题待决策（选 A 重训 vs 选 B 接受小 PSNR）

## ✅ 今日完成（2026-05-21 第四次会话）

### 论文文字全面打磨 + 排版修复

| 完成项 | 内容 |
|--------|------|
| 主文压页 16→14 页 | Abstract 70→30 词首句 / §1 删 Fig 1 caption 重复 / 全篇压字 |
| Limitations bug 修 | 原来"First/Second/Third/Fifth/Finally"缺 Fourth，改为 5 条完整 |
| ρ Unicode 编译错修 | line 75 `ρ(H,\qbar)` 文本模式 → `$\rho(H,\qbar)$` math mode |
| Round 2 senior reviewer | Abstract hook 利落 / Discussion 结构性原因强化 |
| Round 3 non-domain reviewer | jargon 首次定义齐 / 句法平滑 / UK 拼写统一（colour/recognise） |
| Round 4 calibration expert | PAC-Bayes "motivating sketch" caveat / IB "not a theorem" / TS reversal "weakly quality-aware" 限定 |
| Round 5 copy-edit | "notoriously" → "well known" / "for practitioners" → "recommended default" / tense fix |
| Table 1/2/3 caption 干涉 toprule 修 | caption 紧凑 + 加 `\vspace{4pt}`，Table 1 caption 9→3 行 |
| Figure 浮动留白修 | `[t]` → `[!tbp]`（全 figure*/figure） |
| 长公式 overfull 修 | line 174 NLL 公式 / line 353 `$\tau\in\{...\}$` 集合，最大 50pt → 5.5pt |
| Platt orphan cite 加回 | `\cite{platt1999probabilistic}` |

### 最终验证

- 18 页（主 14 + ref 4）✅ BMVC 正中
- 0 error / 0 undefined ref/cite ✅
- 17/17 数字一致性 PASS ✅
- R1-R7 防御 grep 全 0 ✅
- Overfull 15 → 4（最大 5.5pt 可忽略）

### 待续（下次会话）

- [ ] Anonymous GitHub 实际创建 + push（跑 `release/git_init_with_history.sh`，用户亲自避免账号关联）
- [ ] Zenodo DOI 申请（接受后激活，placeholder 占位中）
- [ ] L10 Supplementary 25→30+ 页扩展（可选，~2% 命中率）

## ✅ 今日完成（2026-05-21 第三次会话）

### 非写作任务全部完成 + Supplementary 扩展

| 完成项 | 内容 |
|--------|------|
| 数字一致性 17/17 PASS | rho/ECE/QCDI/T0/alpha/Cohen's d/power 全对 csv 核算 |
| release/ 骨架完整 | generate_tables.py + .gitignore + GITHUB_SETUP.md + git_init_with_history.sh |
| Supplementary A11-A14 | 6-form 消融/跨模态完整/Pre-emptive rebuttal/NLL landscape 各一节 |
| ACCEPTANCE_CRITERIA 更新 | L1-L8 全 ✅，当前预测 ≈75% |
| fig_method.svg 验证 | 0 VisiScore 命中，干净 |

### 待续（下次会话）
- [ ] **W6 Round 2-5 写作打磨**（最后 ~2% 命中率）
- [ ] Anonymous GitHub 实际创建（用 GITHUB_SETUP.md + git_init_with_history.sh）
- [ ] 编译最终确认（pdflatex × 3，页数 ≤14）

## ✅ 今日完成（2026-05-21 第二次会话）

### Adversarial Defense 全部 5 个 Attack 完成 + 关键数据

| Attack | 写入位置 | 关键数字 |
|--------|---------|---------|
| A1 Platt/isotonic baseline | §5.3 后 | Platt ρ=+0.195 (quality-confused)；Isotonic ρ=+0.629；QCTS 唯一 ρ<0 |
| A2 τ 阈值敏感性 | §6 Discussion | LQ sub-pool 里 TS 改善 ρ；reversal 在 HQ tier；Laplacian 独立验证 |
| A3 Power analysis | §5.3 替换 | Prospective MCED=0.03，n=117 @ 80% power，非循环 |
| A4 QCDI sign-flip 歧义 | §3.3 新增段 | Genuine (ρ<-0.15 + QCDI≤0) vs quality-confused |
| A5 α NLL landscape | §5.3 新增 | Flat region [0.20, 1.35]，3 seeds 内 delta<0.0012 |

### 其他完成
- §6 failure mode 数字 v2 更新：(41%→49%, 33%→32%, 26%→19%)
- Fairness full breakdown 脚本跑通（lesion type 九分类 + 三分类）
- `itb_supp.tex` A5 新增 lesion-type 子表
- 新脚本：`scripts/threshold_sensitivity.py`、`attack1_platt_isotonic.py`、`attack5_nll_landscape.py`
- 新结果：`threshold_sensitivity.{csv,json}`、`attack1_baseline_comparison.{csv,json}`、`attack5_nll_landscape.{csv,json}`、`fairness_full_breakdown.{csv,json}`

### 待续（下次会话）
- [ ] pdflatex 编译确认页数未超 14（攻防段加了约 1 页）
- [ ] Tax sensitivity + Platt/isotonic 数字加入 Supplementary 表格
- [ ] Attack 2 数字加入 Supplementary threshold sensitivity 表
- [ ] W6 写作打磨 Round 1（自己重写一遍）
- [ ] Code/Docker 骨架（W7）

## ✅ 今日完成（2026-05-21 第一次会话）

### 论文关键 lever 补全 + Supplementary 骨架

| 任务 | 状态 | 关键数字 |
|------|------|---------|
| L7 统计写入论文（§5.3） | ✅ | Bonferroni p=0.0015, Power=0.929, Cohen's d=0.45 |
| MC/DE ρ LQ-stratum + Simpson 现象（§5.2） | ✅ | MC ρ=+0.350, DE ρ=+0.133 on ITB-LQ |
| L3 quality scalar 段落写入论文（§5.3） | ✅ | 移至 Supplementary Table S1 |
| Fundus 跨域 negative result（§5.6） | ✅ | QCTS 无效（IQA not domain-specific），诚实 negative result |
| §5.6 Fairness 数字修复 | ✅ | MC Dropout 0.157/0.182 → 0.124/0.103；QCTS V-VI ρ -0.134→-0.306 |
| §6 Limitations in-the-wild partial result | ✅ | 174 张 real LQ，ECE=0.073，benign-class well-calibrated |
| itb_supp.tex 创建（8 appendix sections） | ✅ | A1 IQA, A2 Table S1, A3 DCA, A4 MC/DE scatter, A5 Fairness I-VI, A6 ImageNet-C full, A7 real LQ, A8 failure mode |
| ImageNet-C 全表（18 corruption）写入 supplementary | ✅ | TS=Raw 全程，QCTS 全 18 改善 |
| Fitzpatrick I-VI 全表写入 supplementary | ✅ | 从 csv 计算实际数字 |
| L4 real LQ inference 脚本 | ✅ | `scripts/infer_real_lq_dermoscopy.py` |
| Failure mode clustering 脚本 | ✅ | `scripts/failure_mode_clustering.py`，KMeans k=3 |
| BRISQUE + CLIP-IQA + APTOS 引用加入 bib | ✅ | egbib.bib 更新 |

### 新增脚本
- `scripts/infer_real_lq_dermoscopy.py` → `results/real_lq_inference.json`
- `scripts/failure_mode_clustering.py` → `results/failure_mode_clusters.json`
- `scripts/fairness_fitzpatrick_breakdown.py` → `results/fairness_fitzpatrick_breakdown.{json,csv}`
- `meeting/BMVC/itb_supp.tex` → supplementary 骨架（8 sections）

### Lever 状态更新
- L3 quality scalar: ✅ 结果在 Supplementary Table S1 + 段落写入论文
- L4 real LQ: ✅ 174 张图、inference 完成、supplementary 记录
- L7 statistics: ✅ Bonferroni + Power + Cohen's d 写入 §5.3
- §5.6 fairness: ✅ 数字从 old estimate 修正为 csv 实测值

### 待续（下次会话）
- [ ] itb_paper.tex 编译验证（用户在 LaTeX 环境里跑 pdflatex）
- [ ] W5 Failure mode clustering §6 upgrade（更详细 analysis）
- [ ] Supplementary 扩展到 20-30 页（W7 前）
- [ ] LLM adversarial review 启动（W6）
- [ ] Code/Docker release 骨架（W7）

## ✅ 今日完成（2026-05-20 第三次会话）

### 跨域实验 + W2/W3/W4 批量完成

| 任务 | 状态 | 核心数字 |
|------|------|---------|
| CheXpert 跨域推理（DenseNet-121） | ✅ | ρ=-0.971，无 TS 反转，QCTS=TS |
| Fundus 跨域推理（APTOS 2019, ViT-DR） | ✅ | ρ=+0.259，弱 QA，QCTS=TS |
| L7 Cohen's d + Bonferroni + Power | ✅ | d(QCTS)=+0.452, power=0.929 |
| L5 DCA + Triage simulation | ✅ | QCTS max NB=0.192 vs VIB 0.186 |
| L6 Theory（IB connection + PAC-Bayes） | ✅ | 加入 §4 新 subsection，~0.5 页 |
| L4 真实 LQ dermoscopy（ISIC 2020） | ✅ | 200 张收集完毕（data/real_lq_dermoscopy_isic/） |
| MC Dropout/Deep Ensemble ρ scatter | ✅ | MC ρ=+0.350, DE ρ=+0.133（Quality-Oblivious） |
| §5.6 cross-modality 段落 | ✅ | CheXpert 结果写入论文，DCA 数字更新 |
| fig_method.svg VisiScore 清除 | ✅ | grep 0 命中 |
| itb_paper.tex 编译 | ✅ | 18 页，0 error |

### 新增脚本
- `scripts/eval_chexray_crossdomain.py` — CheXpert 跨域评估
- `scripts/eval_fundus_crossdomain.py` — Fundus 跨域评估
- `scripts/compute_statistics_l7.py` — Cohen's d / Bonferroni / Power
- `scripts/run_dca_triage.py` — DCA + Triage + 皮肤科 baseline
- `scripts/gen_uncertainty_qbar_scatter.py` — MC Dropout/DE ρ scatter
- `scripts/collect_real_lq_from_isic2020.py` — L4 本地 LQ 采集
- `scripts/download_real_lq_dermoscopy.py` — L4 ISIC API 下载（备用，进行中）

### 待续（下次会话）
- [ ] L4 real LQ inference：对 200 张真实 LQ 图跑 Std VIB 推理，与 ITB-LQ 对比校准行为
- [ ] Sub-population fairness 全维度（Fitzpatrick 1-6 breakdown，需 image-to-metadata 映射）
- [ ] ISIC API 下载进一步积累（当前 ~21 张，备用）
- [ ] 下一步论文写作：§5.6 MC Dropout 结果描述 + uncertainty scatter 图引用

## ✅ 今日完成（2026-05-20 第二次会话）

### D10 + EDL + §5.5 + 5-backbone 全部完成

| 任务 | 状态 | 核心数字 |
|------|------|---------|
| D10 质量标量消融 bug 修复 | ✅ | 5-head IQA α=0.95 best，BRISQUE α=0（collapse） |
| EDL ITB inference | ✅ | AUC-LQ=0.586 ECE-LQ=0.316 QCDI=+0.046 ρ=+0.039 |
| §5.5 ImageNet-C 章节 + fig7 | ✅ | TS neutral，QCTS 18/18 改善 |
| Table 3 扩展 5 backbone | ✅ | ConvNeXt + Swin（Swin QCDI flip +0.020→-0.021） |
| §5.2 EDL 行为描述 | ✅ | "Quality-Fragile"定性 |
| gen_bmvc_figures.py METHOD_META 清理 | 🟡 | F/G 部分清理（还剩1340+行未清） |
| CheXpert 跨域脚本 | ✅ 写完 | 等 kaggle 数据下载完 |

### CheXpert 跨域结果（D13-D14 ✅）

| 方法 | QCDI | ρ(H,q̄) |
|------|------|--------|
| DenseNet raw | −0.026 | −0.971 |
| +TS | −0.021 | −0.971 |
| +QCTS | −0.021 | −0.971 |

Raw model 已 quality-aware（QCDI < 0），QCTS 小改善。ρ 极高因 qbar=corruption_severity 只有 5 个离散值（非自然质量分布）。Paper 用 "cross-modality applicability" 而非 "reversal" framing。

数据：`results/crossdomain/chexray_crossdomain.{json,csv}`

### 待续（下次会话）
- [ ] **gen_bmvc_figures.py** 剩余 F/G 清理（1340-1950 行）+ 重跑 fig{1,2,3,4}
- [ ] **fig_method.svg** 重跑（含 VisiScore-Net → 5-head IQA 替换）
- [ ] **CheXpert 结果写入 §5.6 或新 §5.7 段落**（cross-modality generalization）

---

## ✅ 今日完成（2026-05-20）

### W2 D8-D9：QCTS Form Ablation 扩展
- `run_qcts_ablation.py`：新增 bin10 / dimwise / MLP 三种 T(q̄) 形式
- 结果：softplus 在 4 指标全部最优（ECE-LQ 0.047 / ECE-HQ 0.062 / QCDI −0.015 / ρ −0.249）
- bin10 NLL 最低但 ρ=+0.009（不 quality-aware）；MLP QCDI=0（退化）
- `table2_ablation.tex` 扩展为 6 行，编译 0 error
- 结果：`results/qcts_form_ablation.csv`

### W2 D10：质量标量消融（进行中，有 bug 待修）
- `run_quality_scalar_ablation.py`：BRISQUE / CLIP-IQA / RF-Stat / LaplacianVar / 5-head IQA 骨架完成
- BRISQUE/CLIP-IQA/LaplacianVar/RF 质量分数已计算并缓存（`results/quality_scalar_cache.pkl`）
- **Bug**：`itb_sub["qbar"]` 与 `d_preds["qbar"]` 顺序不一致 → 质量分数错配 → ECE 结果错误
- **修复方向**：通过 (subset, target, qbar) join 对齐顺序，或直接用 `d_preds["qbar"]` 作 5-head IQA

### 命名红线修复
- 删除脚本中 "VisiScore-Net" 字样，改为 "5-head IQA (ours)"

---

## ✅ 今日完成（2026-05-21 自动跑完）

### 实验产出
- **ImageNet-C 腐蚀重跑**：18 corruption × 5 severity × Raw/TS/QCTS 三方法，新增 `raw_rho/ts_rho/qcts_rho` 列。TS 反转 16/18（ResNet-50）、14/18（ViT-Tiny），远超验收阈值 3/14。结果：`results/backbones/{resnet50,vit_tiny}/corruption_robustness_itb-lq.csv`
- **EDL ITB inference**：AUC-LQ=0.586, ECE-LQ=0.316 [0.273,0.361], AUC-HQ=0.895, ECE-HQ=0.270, QCDI=+0.046, ρ=+0.039。Table 1 EDL 行数字就位。结果：`results/edl/itb_metrics.json`
- **ConvNeXt-Tiny + Swin-Tiny 完整链路**：train(30ep) → infer_backbone → QCTS 拟合。section54_summary.csv 现有 5 backbone（Std VIB / ResNet-50 / ViT-Tiny / ConvNeXt-Tiny / Swin-Tiny）。

### Bug 修复
- `infer_backbone.py` + `test_corruption_robustness.py`：`build_backbone` 改用 `timm.is_model()` 通用路由，支持 convnext/swin 等任意 timm 模型

---

## 🚫 永久红线
1. Reader Study 不可伪造（详见 BMVC_LOG.md 顶部"永久红线" section）。临床相关性用 DCA + Triage simulation + Published dermatologist baseline 替代。
2. **所有材料只能从网上公开资源获取**（2026-05-20 用户确认）。不联系诊所、不采集线下样本、不依赖人际网络。Adversarial review 用 LLM 扮演不同 persona 替代真人。

## ✅ D6 + D7 部分（2026-05-20，提前 5 天）

### D6 §6 Discussion / Limitations 调整
- itb_paper.tex §6 加 "Structural reason TS reverses on weakly quality-aware backbones" 段（200 词）
- Limitations 改 4 条：(1) reversal backbone-dependent；(2) ITB synthetic degradation；(3) q̄ resolution + IQA cost；(4) clinical translation
- 6 张图 caption 全部加 `\emph{Takeaway:}` 句（teaser / method / problem / qcts / universality / generalization）
- 验收 ACCEPTANCE D6 全 PASS

### D7 数字一致性 + R1-R7 防御扫描
- R1-R7 grep：itb_paper.tex 0 命中 Q-VIB / VisiScore / anonymous2025 / "TS always" / "universal reversal" / "we prove"
- **严重不一致修复**：Abstract / Intro / §5.2 中 Std VIB raw ρ 写的 −0.024 = ITB-LQ only (n=300, **p=0.62 非显著**)，但 +0.241 是 full ITB pool 才成立的数字。**两个数字混搭了不同 pool，reversal hook 在 ITB-LQ pool 上根本不存在**（实际 ρ=−0.029 → +TS ρ=−0.387，更负 = 更 quality-aware）
- 修复：3 处 −0.024 → −0.153 + 加 pool 限定 "across the full ITB pool, n=2820" + 加 p-value 标注（p<10⁻¹⁵ / p<10⁻³⁷）
- 重算源：`itb_predictions.csv` Spearman(entropy, q̄) on Std VIB / Std VIB+TS，full ITB pool n=2820
- 编译干净：16 页总（主文 1-14 + ref 14-16）、0 error、0 undefined
- **STORY_FRAMEWORK 锁定数字表与 csv 已对齐**

---

## ✅ D1 非写作任务完成（2026-05-20）

### fig5：Per-bin optimal T* vs QCTS curve
- 脚本：`project/scripts/gen_fig5_perbin_T.py`
- 输出：`figures/fig5_perbin_optimal_T.{pdf,svg,png}`
- 用 `degraded_val` 数据（9936 样本）按 q̄ 分 20 bin，拟合每 bin 最优 T*，叠加 QCTS softplus 曲线
- ViT-Tiny：散点清晰跟随下降曲线（alpha=1.40 → T 随 q̄ 升高而降低）
- ResNet-50：曲线接近平坦（alpha=0.24）

### fig6：TS reversal — ECE gap flip bar chart
- 脚本：`project/scripts/gen_fig6_ts_reversal.py`
- 输出：`figures/fig6_ts_reversal.{pdf,svg,png}`
- ViT-Tiny：Raw ΔECE=+0.023 → Std-TS ΔECE=**-0.029**（符号翻转 = reversal！）
- ResNet-50：Raw +0.014 → TS +0.004（始终为正 = neutral）
- 直接可视化 "TS reversal most pronounced on ViT-Tiny" 这一 §5.4 核心 claim

### ✅ ImageNet-C 风格腐蚀鲁棒性实验完成（2026-05-19）
- 方案：imagecorruptions 库（无需下载，实时生成）
- 脚本：`project/scripts/test_corruption_robustness.py`（14 腐蚀 × 5 级别 × ITB-LQ 300 张）
- 结果：`results/backbones/{resnet50,vit_tiny}/corruption_robustness_itb-lq.csv`

| 汇总 | ResNet-50 | ViT-Tiny |
|------|-----------|----------|
| Clean AUC | 0.691 | 0.718 |
| Mean Corruption AUC | 0.623 | 0.645 |
| AUC drop | 0.068 | 0.073 |

关键：ViT 绝对性能更高但稍脆弱；blur 类 AUC 反高于 clean（皮肤镜特有现象）

---

## ✅ EDL baseline 训练完成（2026-05-19 深夜）

- 脚本：`project/train_edl.py` + `configs/edl.yaml`（EfficientNet-B3 + Dirichlet loss）
- best AUC：**0.8622**（ep10，KL 退火完成后停止）
- checkpoint：`project/checkpoints/edl/best_edl.pth`
- 修复记录：OOM（batch 64→32）、Windows shared memory 崩溃（num_workers=0）

---

## ✅ §5.4 Backbone Universality 实验完成（2026-05-19）

| Backbone | best AUC | ρ(H,q̄) Raw | TS 反转 | QCTS ρ |
|----------|----------|------------|---------|--------|
| ResNet-50 | 0.884 | −0.368 ✅ | 无 | −0.380 |
| ViT-Tiny | 0.903 | −0.160 ✅ | **有** ✅ | −0.266 (p=9e-23) |

- logits 输出：`results/backbones/{resnet50,vit_tiny}/`
- QCTS 拟合结果：`results/backbones/section54_summary.csv`
- ITB-Diverse（Fitzpatrick17k）排除出 §5.4（跨域，放 Limitations）

**详见**：`project/meeting/BMVC/BMVC_LOG.md` 2026-05-19 entry

---

## 📊 一句话进度

| 部分 | 状态 | 核心数字 | 最后更新 |
|------|------|---------|---------|
| **BMVC** | ⚠️ 脱敏完成，待 ResNet/ViT 训练 + 重做 Table/图 | 14 页 / 0 error / Q-VIB+VisiScore 已剥离 | 2026-05-19 |
| **大项目 Q-VIB** | ✅ 完成 | F AUC 0.707 / ECE 0.098 / ρ=-0.165 | 2026-05-15 |
| **大项目 VisiScore** | ✅ 完成 | PLCC 0.924 / SRCC 0.895 | 2026-05-07 |
| **大项目 Agent** | ✅ 完成 | 低质追问 59% / 高质 15.5% | 2026-05-07 |
| **大项目 VisiEnhance** | ❌ 待决策 | PSNR 25.55 dB（目标 ≥30）| 2026-05-16 |

---

## 🚀 紧急待修（下次开始前）

1. **D10 bug**：`run_quality_scalar_ablation.py` 中 itb 质量分数与 logit 顺序错配
   - 修复：join d_preds + itb_sub on (subset, target, qbar) 获取 image_path，再查 cache
   - 或：删除 cache 并重构 `eval_on_itb`，用 d_preds 顺序重新映射质量分数

2. **table3_quality_scalar.tex** 数字全部无效，等 D10 修复后重新生成

---

## 🚀 下一步（60 天稳中路线，完整日程见 BMVC_LOG.md 2026-05-19 深夜）

### 8 周高层日程（D1=05-20，投稿日 07-15~18）

| Week | 日期 | 核心工作 |
|------|------|---------|
| **W1** | 05-20~26 | 叙事重构 + §5.4 正文 + ImageNet-C 全量 + ConvNeXt/Swin 训练 |
| **W2** | 05-27~06-02 | 过度参数化消融完整 + 5 quality scalar 对比 + EDL + CheXpert 跨域 |
| **W3** | 06-03~09 | Fundus 跨域 + 真实低质照片采集（实习生拍）+ Sub-population fairness |
| **W4** | 06-10~16 | DCA + Triage simulation + Theory section（1 页） |
| **W5** | 06-17~23 | Failure clustering + Table/Figure 全部重做（10-12 主图） |
| **W6** | 06-24~30 | 写作打磨 × 5 轮（含 4-6 人 adversarial review + copy-editing） |
| **W7** | 07-01~07 | 30-50 页 supplementary + Code/Docker/ITB v1.0 release 打包 |
| **W8** | 07-08~14 | 编译 × 3 + 数字核查 + buffer × 3 天 |
| **投稿** | 07-15~18 | OpenReview 上传 + ethics declaration 签署 |

### D1 必须启动的 3 件事（critical path）

1. 联系皮肤科诊所，安排实习生/护士采集 200 张真实低质照片（4 周窗口）
2. 起 ITB v1.0 数据集 license 草稿（CC-BY-NC-SA 或类似）
3. 写 anonymous GitHub repo skeleton（累积 8 周 commit history）

### 已完成（保留作为历史）
- [x] **P0**：ResNet-50 + ViT-Tiny 训练完成（best AUC 0.884 / 0.903）
- [x] **P0**：infer_backbone.py + run_qcts_backbone.py 跑完，section54_summary.csv 就位

### 7 月后
- [ ] MICCAI 版本 Abstract / Experiments / Conclusion / Appendix（含真 Reader Study + train-time EDL/DUE 对照）
- [ ] **VisiEnhance 决策**：选方案 A（重训 30-40h）或 B（接受 25-26 dB）

### 5 月底前（投稿前）
- [ ] **BMVC**：最终检查 + OpenReview 上传
- [ ] **大项目**：Method 3.3 数字对应 VisiEnhance 决策

### 6 月后
- [ ] MICCAI 版本 Abstract / Experiments / Conclusion / Appendix
- [ ] Release 准备（ITB Benchmark + QCTS code）
- [ ] Reader Study（推进 3 位医生）

---

## 📂 快速导航

| 需求 | 文件 |
|------|------|
| **项目全貌** | `project/PROJECT_OVERVIEW.md` ⭐ |
| **BMVC 日志** | `project/meeting/BMVC/BMVC_LOG.md` |
| **BMVC 论文** | `project/meeting/BMVC/itb_paper.tex` |
| **阶段计划** | `project/plans/00_overview.md` |
| **核心实验脚本** | `project/run_qcts.py` / `gen_bmvc_figures.py` |
| **权重位置** | `project/checkpoints/` |
| **数据资产** | `project/data/` |
| **结果数据** | `project/results/` |

---

## 🔬 关键数据速查

### Q-VIB 主结果（test set, 19878 张）
```
F (Q-VIB Full):  AUC 0.707  ECE 0.098  Entropy~q̄ ρ = -0.165 ✅
D (Std VIB):     AUC 0.693  ECE 0.097  Entropy~q̄ ρ = -0.024
```

### BMVC QCTS 结果（ITB-LQ）
```
Std VIB:           ECE 0.146
Std VIB + QCTS:    ECE 0.047  (68% ↓) ✅
```

### VisiScore-Net
```
平均 PLCC 0.924 / SRCC 0.895 ✅
```

---

## ⚠️ 待决策

### VisiEnhance Stage 1
- **现状**：PSNR 25.55 dB（目标 ≥30），SSIM 0.9535（目标 >0.92 ✅）
- **原因**：模型仅 1.7M 参数，容量不足
- **选项 A**：换大 config（~15M），重跑 30-40h
- **选项 B**：接受 25-26 dB，核心靠代码发布 + E1 贡献

---

## 📅 今日完成（2026-05-17）

### ✅ 1. 项目文档重构（上午）
- 创建 `project/PROJECT_OVERVIEW.md`：495 行完整项目全景
- 简化 WORKLOG.md + BMVC 文件整理 + token 效率优化

### ✅ 2. BMVC 4 张图大重做（下午~晚）
- **Fig 1 Teaser**：真实皮肤镜 4×3 矩阵（HQ/Blur/Colour/Combined），选图脚本 + 手选样本（ISIC_8713598/8370773/9383110/9989680），顶部诊断条 + Std VIB vs QCTS 双条对比
- **Fig 2 Problem**：Taxonomy 散点（9 方法 + 三区域 + QCTS 星 + "Only post-hoc to Aware" callout）+ LQ/HQ Reliability 双图
- **Fig 3 QCTS Solution**：T(qbar) 三 seed + α inset / Per-deg 4 维度 × 3 方法 / qbar bin waterfall + "Avg 34% reduction" 大字
- **Fig 4 Generalization**：Entropy~qbar 三联 hexbin (ρ -0.033→-0.108→-0.164) / Cross-dataset QCDI 含 QCTS / Fitzpatrick V-VI fairness

### ✅ 3. Table 1 重做 + 视觉升级
- 11 行 × 4 分组（Discriminative / Bayes / VIB / Post-hoc），bootstrap 95% CI
- per-column heatmap 渐变（QCTS 在 ECE/QCDI 列 green shade）
- QCTS 拿 4 个 best：ECE-LQ / ECE-HQ / QCDI / ρ
- 生成器：`project/scripts/gen_table1.py`

### ✅ 4. 字号修复 + framing 加强
- 全 4 图 figsize 从 13-15 inch 缩到 7-8 inch → BMVC 印刷字号 4pt → 7-10pt
- Fig 2 加 callout "Only post-hoc to Aware"
- Fig 3 加 "Avg ECE reduction across 5 bins: 34%" 绿色 callout
- Fig 4(b) 补 QCTS cross-dataset 数据列
- Fig 4(c) 加 V-VI QCDI 具体数字标注

### 📁 新增文件
- `project/scripts/select_teaser_candidates.py` — fig1 候选池生成器
- `project/scripts/selected_teaser.json` — 4 张选定样本元数据
- `project/scripts/gen_table1.py` — Table 1 LaTeX 生成器（含 bootstrap CI + heatmap）
- `project/meeting/BMVC/figures/fig{1,2,3,4}_*.{pdf,svg,png}` — 4 张图（SVG 可后期 Illustrator）
- `project/meeting/BMVC/table1_main.tex` — Table 1 单独 .tex
- 计划文件：`C:/Users/yj200/.claude/plans/bmvc-py-r-matlab-deep-planet.md`

### 📄 论文状态
- `itb_paper.pdf`：12 页，零 error，4 张新组图 + 新 Table 1
- 大小：3.9MB → 2.1MB（缩 figsize 后）
- BMVC limit 14 页 ref 不含，还有 2 页余量

---

最后更新时间：2026-05-17 18:30（北京时间）
