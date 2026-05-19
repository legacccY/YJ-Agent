# 工作日志（快速指针）

**最后更新**：2026-05-19 晚 | **完整进度**：见 `D:/YJ-Agent/project/PROJECT_OVERVIEW.md`

---

## 🎯 当前焦点

- **BMVC 投稿** | Deadline 2026-05-29（**10 天**）| 状态：**重大策略调整中** — 剥离 Q-VIB / VisiScore-Net 保护 MICCAI novelty + 创新性 3 杠杆升级
- **大项目** | VisiEnhance Stage 1 容量问题待决策（选 A 重训 vs 选 B 接受小 PSNR）

## ⚠️ BMVC 紧急策略变更（2026-05-19）

**问题**：原 BMVC 论文自引 `anonymous2025qvib` + `anonymous2025visiscore` 2 条未发表工作 + 公开 Q-VIB 方法骨架 + 3 个变体性能 — 提前曝光大论文 novelty。

**对策**：
- ✅ 已完成：tex 15 处脱敏（Q-VIB 11 处 + VisiScore 4 处）+ 删 bib 自引 + 写 QCTS derivation 段 + §5.4 占位 + 编译干净 14 页
- ⏳ 下次首要任务：写 ResNet-50 + ViT-Tiny 训练脚本 → `/loop /run-experiment ...` 启动

**详见**：`project/meeting/BMVC/BMVC_LOG.md` 2026-05-19 entry（含完整下次执行 checklist）

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

## 🚀 下一步（清单）

### 本周（2026-05-19~05-26）BMVC 冲刺
- [ ] **P0**：写 ResNet-50 + ViT-Tiny 训练脚本（不需 GPU，可立即开始）
- [ ] **P0**：`/loop /run-experiment train_resnet50.py configs/resnet50.yaml`（GPU 6-8h）
- [ ] **P0**：`/loop /run-experiment train_vit_tiny.py configs/vit_tiny.yaml`（GPU 6-8h）
- [ ] **P0**：改造 run_qcts.py 支持任意 backbone + 跑 4 backbone × {TS, QCTS} + bootstrap CI
- [ ] **P0**：写 §5.4 universality 实际内容（替换占位）
- [ ] **P1**：TS 反转 visualization 图
- [ ] **P1**：Per-bin optimal T 散点图
- [ ] **P1**：EDL baseline 训练
- [ ] **P2**：重做 Table 1（删 E/F/G）+ 4 张图（gen_bmvc_figures METHOD_META 删 F/G）
- [ ] **P2**：Abstract hook 化 + 每图 caption 加结论句 + Limitations 防御写作
- [ ] **VisiEnhance 决策**：选方案 A（重训，30-40h）或 B（接受 25-26 dB）— **延后到 BMVC 投稿后**

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
