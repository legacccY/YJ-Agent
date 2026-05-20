# 工作日志（快速指针）

**最后更新**：2026-05-20 | **完整进度**：见 `D:/YJ-Agent/project/PROJECT_OVERVIEW.md`

---

## 🎯 当前焦点

- **BMVC 投稿** | Deadline 假设 2026-06-18（**60 天**）| 状态：**60 天稳中路线启动** — 期望命中率 65-72%（合规版 + 网上获取约束）
- **大项目** | VisiEnhance Stage 1 容量问题待决策（选 A 重训 vs 选 B 接受小 PSNR）

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
