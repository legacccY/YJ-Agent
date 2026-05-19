# BMVC P2 工作日志

---

## 2026-05-19 ⚠️ 重大策略调整：剥离 Q-VIB / VisiScore-Net

### 触发原因

复盘发现 BMVC 论文里**自引了 2 条未发表工作**（`anonymous2025qvib` + `anonymous2025visiscore`），且把 Q-VIB 的方法骨架（adaptive prior + quality tokeniser）+ 3 个变体性能数字 + 跨数据集 ρ 都公开了。这相当于把**大论文（MICCAI 2027 目标）的核心 novelty 提前发表在 BMVC 里**。三重风险：
1. 学术不合规（camera-ready 必须有真实 cite）
2. MICCAI novelty 提前曝光，未来投稿时 Q-VIB 不再 novel
3. "Anonymous, Under review" 占位被审稿人怀疑

### 核心决策

**BMVC 论文创新点严格限定为 ITB + QCTS**。Q-VIB / VisiScore-Net 完整保留给 MICCAI 大论文。

为弥补删除 Q-VIB 后失去的"quality-aware 上限对比"，并应对评审"taxonomy self-serving"攻击，论文创新性升级路线：
- **杠杆 1**：把"**TS 反转现象**"（Std VIB ρ=−0.024 → +TS ρ=+0.241，符号翻转）从 Table 1 默默的数字提升为**一级发现**
- **杠杆 2**：从 inductive biases 推导 QCTS 的 softplus 形式（半页 derivation，含候选 form 显式排除）
- **杠杆 3**：Per-bin optimal T 散点验证（新实验，证明 QCTS 接近 optimal calibration map）
- **杠杆 4**：QCTS 通用性 — 4 backbones（EfficientNet-B3 / Std VIB / ResNet-50 / ViT-Tiny）横跨 CNN/Transformer 三家族
- **补强**：EDL baseline（Sensoy 2018，已发表）作为 Taxonomy 第三类备选 + 训练时 baseline

### 改后的论文故事弧

> ITB 揭示主流 calibration 方法在质量分层下系统性失败 → **standard TS 反转 quality-aware 计算** → QCTS 用 2 参数后处理把任何 backbone 拉到 Quality-Aware 区域 → 比 30× 成本的 MC Dropout 还便宜还好。

### 今日完成 ✅

#### 1. 全面排查越界点（15 处 tex + 3 行 Table 1 + 4 张图 F/G 标注 + bib 2 条）

| 文件 | 范围 |
|------|------|
| `itb_paper.tex` | 11 处 Q-VIB + 4 处 VisiScore — 已全部处理 |
| `egbib.bib` | anonymous2025qvib + anonymous2025visiscore — 已删除 |
| `table1_main.tex` | 3 行 Q-VIB 系列（E/F/G）— **待删除（下次）** |
| `fig{2,3,4}_*.svg/pdf/png` | F/G 标注 — **待重做（下次）** |
| `gen_bmvc_figures.py` METHOD_META | F/G 条目 — **待修改（下次）** |

#### 2. 论文文本脱敏 + 重写（15 处全部完成）

- **Related Work Calibration 段**：删 Q-VIB 句，加 EDL 句
- **Related Work IQA 段**：VisiScore-Net 改为"5-head IQA module trained on synthetic degradations; details in Appendix A"
- **§3.2 Definition**：VisiScore-Net 改为"5-head IQA module"
- **§3.3 Taxonomy 第三类**：去掉 Q-VIB 代表，改为"Representative: our QCTS. To our knowledge no prior published method enters this regime on ITB-LQ"
- **§4.1 Baselines**：9 → 7（删 E/F/G）+ EDL + 预告 §5.4 ResNet/ViT 通用性
- **§4.2 "Unlike Q-VIB..."**：改为"Unlike training-time approaches (e.g., EDL [Sensoy 2018]), QCTS is post-hoc..."
- **§5.2 Main Results 文字**：删 Q-VIB Full ρ=-0.192 数字，**新增 TS 反转一段**（Std VIB ρ=-0.024 → +TS ρ=+0.241）
- **§5.3 QCTS Analysis**：删 "Q-VIB Full stay close..." 句
- **§5.5 Generalization**：用 QCTS 真实数字替代 Q-VIB（HAM ρ=-0.108 p<10⁻²⁶ / PAD ρ=-0.150 p<10⁻¹² — **已核算确认非编造**）
- **fig_method caption**：VisiScore-Net → 5-head IQA module
- **fig4 caption**：Q-VIB Full 阶梯改为 Std VIB → +QCTS 阶梯；V--VI gap 改回原表述"0.01--0.02 range"
- **Discussion 第一段**：完整改写，去掉 Q-VIB Full 对比，强调 post-hoc 极限 + training-time future work
- **Abstract**："nine representative methods" → 中性表述"a panel of representative discriminative, Bayesian, ensemble and post-hoc methods"

#### 3. QCTS Derivation 段落（杠杆 2，新增半页）

插入 §4.2 "Formulation" 之后，作为独立"\textbf{Derivation from inductive biases.}"段：
- 三个 inductive biases（B1 monotonicity / B2 positivity / B3 smoothness & TS reduction）
- 显式排除候选 form：linear 违反 B2 / ReLU 违反 B3 / piecewise 违反 B3（Table 2 实证支撑）/ exp 经验上 overshoot
- 措辞 "derived from inductive biases" 而非 "theoretically proven"（按防御性写作要求）
- 引出 §5.4 per-bin optimal T 实证

#### 4. §5.4 占位节 `sec:universality`

新增 placeholder 节，明确标 "[Section under preparation]"，保证所有 `\ref{sec:universality}` 解析。等 ResNet-50 / ViT-Tiny 实验完成后填充。

#### 5. 真实数字核算（避免捏造）

跑了短脚本核算 QCTS 在 HAM10000 / PAD-UFES 上的真实 ρ：
```
QCTS params: T0=1.1700, alpha=0.9554
HAM10000 (n=10015): Std VIB ρ=−0.0329 → +QCTS ρ=−0.1078 (p=2.89e-27)
PAD-UFES (n=2298) : Std VIB ρ=−0.0748 → +QCTS ρ=−0.1498 (p=5.24e-13)
```
论文写的 -0.108 / -0.150 与真实值一致 ✅。

#### 6. 编译干净

- **14 页 PDF**（之前 12，加了 derivation + §5.4 占位）
- **0 编译 error**
- **0 undefined warning**
- 新增引用：Sensoy 2018 evidential / Platt 1999

---

### ⚠️ 下次会话启动指南（按此 checklist 执行）

#### 进入 BMVC 工作的快速回顾（30 秒）

1. Read `D:\YJ-Agent\project\meeting\BMVC\itb_paper.tex` — 看当前论文状态
2. Read 本文件 2026-05-19 entry — 了解策略和已完成项
3. 当前 PDF：`itb_paper.pdf` 14 页编译干净，但 Table 1 + 4 张图还含 E/F/G（Q-VIB 系列），§5.4 是占位

#### 优先级执行顺序（按 deadline 倒推，2026-05-29 投稿，剩 10 天）

**🔴 P0 — 4 天内必完成**

1. **写 ResNet-50 训练脚本 + config**（不需 GPU）
   - 入口：`project/train_resnet50.py` + `project/configs/resnet50.yaml`
   - 复用 `train_qad.py` 框架但换 backbone
   - ImageNet 预训练 finetune ISIC 2020 70/10/20

2. **启动 ResNet-50 训练**（GPU 6-8h）
   - 用户操作：`/loop /run-experiment project/train_resnet50.py project/configs/resnet50.yaml`
   - 不要直接 python 启动（CLAUDE.md 强制 /loop 流程）

3. **写 ViT-Tiny 训练脚本**（脚本类似 ResNet）+ 启动（GPU 6-8h）
   - `project/train_vit_tiny.py` + `project/configs/vit_tiny.yaml`
   - 用 DeiT-Tiny ImageNet 预训练（timm.create_model('deit_tiny_patch16_224', pretrained=True)）

4. **改造 `run_qcts.py` 支持任意 backbone**
   - 抽象 `load_backbone(name)` 接口
   - 输入 val logits → 拟合 (T0, α) → ITB 评测
   - 4 backbone × {TS, QCTS} × 3 seeds + bootstrap 1000 iter CI + permutation test

5. **跑 4 backbone × {TS, QCTS} 实验**
   - 重点：在每个 backbone 上看 TS 反转是否出现（核心 P0 claim）
   - 期望：至少 3/4 backbone 上 TS 反转 ρ，QCTS 改善 QCDI

6. **写 §5.4 实际内容**（替换占位）
   - 表：4 backbones × {raw / +TS / +QCTS} × {QCDI, ρ, ECE-LQ, ECE-HQ} + bootstrap CI
   - 文字：报告 TS 反转的稳健性 + QCTS 通用性

**🟡 P1 — 5-7 天内**

7. **TS 反转 visualization 图**（task #15）
   - 配对样本 LQ vs HQ 在 TS 前后的 confidence flip 箭头图

8. **Per-bin optimal T 散点图**（task #16）
   - ITB 按 q̄ 分 20 bin，每个 bin 拟合 optimal T*
   - 叠加 QCTS 拟合曲线 — visual proof

9. **EDL baseline 训练**
   - `/loop /run-experiment project/train_edl.py project/configs/edl.yaml`
   - Sensoy 2018 Dirichlet outputs
   - GPU 4-6h

**🟢 P2 — 8 天内**

10. **重做 Table 1**：删 E/F/G 3 行；加 EDL 行；加 4 backbone × QCTS 行（或独立成 Table 3）
    - 编辑 `table1_main.tex`
    - 重算 heatmap 渐变范围

11. **重做 4 张图**：改 `gen_bmvc_figures.py` METHOD_META 删 F/G；`gen_method_figure.py` 改 VisiScore→5-head IQA
    - 重跑两个脚本生成新 SVG/PDF
    - `gen_method_figure.py` 已经手动改 VisiScore 为 5-head IQA，但 fig_method.svg 还是旧版，需要重跑

12. **Abstract hook 化**（task #17）
    - 第一句改 "We discover that standard temperature scaling can **reverse** quality-aware calibration..."

13. **每图 caption 加结论句 + Limitations 防御写作**（task #18）
    - 每张图末尾加 takeaway
    - Limitations：诚实声明 "TS reversal observed across {EfficientNet, ResNet, ViT}; broader cross-modality verification remains future work"

14. **Supplementary 补 grid search + 完整 4×3-seed 表**（task #19）

15. **最终重编译 + 数字一致性核查**（task #11）
    - pdflatex × 2 + bibtex + pdflatex
    - 核对每个数字与 Table 1 一致
    - 页数 ≤ 14（除参考文献）

#### 关键防御性写作 checklist（贯穿所有改动）

- ⚠️ 不 overclaim 为 theorem，用 "derived from inductive biases"
- ⚠️ 每个 claim 加 bootstrap CI 或 p-value
- ⚠️ Abstract 第一句必须是 TS 反转 hook
- ⚠️ Limitations 主动承认架构依赖性
- ⚠️ 任何新数字必须从代码核算，不能凭印象写

#### 待决策项（下次启动前确认）

- ResNet-50 / ViT-Tiny 的 input size：224×224（标准）还是 256×256（贴合 ISIC 原图）
- 训练 epochs：90（与 Std VIB 对齐）还是 50（更快）
- ViT-Tiny 是 DeiT-Tiny 还是 timm 的 vit_tiny_patch16_224

---

### 今日完成

#### 1. 解压模板 + 修复 LaTeX 编译环境
- 解压 `Author_Guidelines_for_the_British_Machine_Vision_Conference.zip`，获取 `bmvc2k.cls / .bst / egbib.bib`
- 修复三处编译错误：
  - 去掉 `\bibliographystyle{bmva}`（与 cls 自带的 `plainnat` 冲突）
  - 修正 `irvin2019chexpert`：`@article` → `@inproceedings`
  - 修正 `pacheco2020pad`：`@inproceedings` → `@article`
- 完整四步编译流程（pdflatex × 2 + bibtex + pdflatex）通过，零 error

#### 2. 写 Abstract 初稿
- 原 tex 里 Abstract 是 BMVC 模板占位文字，替换为论文真实摘要（约 150 词）
- 覆盖：问题定义（QAC / QCDI）、ITB benchmark、9 条 baseline 核心发现、QCTS 方法

#### 3. 实验代码编写（暂未跑）
- `project/run_qcts.py`：QCTS 完整实验流水线
  - 从预计算特征（efficientnet_features.npy + abcd_cache.csv）加载 val split，不重新过图片
  - Std VIB 确定性前向 → binary logit → scipy L-BFGS 拟合 (T₀, α)
  - 用 `itb_predictions.csv` 里 D 的概率重建 logit 后施加 QCTS
  - 输出 `qcts_params.json` + `qcts_itb_results.csv` + `per_degradation_ece.csv`

#### 4. 生成论文图表（gen_bmvc_figures.py）

生成 4 张图，均 300 DPI PDF + PNG，存于 `meeting/BMVC/figures/`：

| 图 | 文件 | 内容 | 关键设计决策 |
|----|------|------|------------|
| Fig 1 | `fig1_taxonomy` | 校准分类散点图（双面板） | 左：全局视图含背景色区域；右：Quality-Aware 区域放大，QCTS 星型点标注 |
| Fig 2 | `fig2_reliability` | 可靠性曲线（LQ/HQ 分层） | 全范围 [0,1]，底部密度条显示预测集中位置；早期版本裁到 [0,0.5] 隐藏了关键故事（已修复） |
| Fig 3 | `fig3_degradation` | 逐降质维度 ECE 柱状图 | 按各质量维度底 20th 百分位分组（非主降质），蓝色虚线为 Std VIB 基准 |
| Fig 4 | `fig4_entropy_qbar` | Entropy–q̄ hexbin 对比 | **使用 HAM10000**（自然质量分布，n=10,015），而非 ITB（人为分层产生 Simpson's Paradox） |

#### 5. 排查两个数据问题

**问题 A — Fig 2 裁轴错误**
- MC Dropout / Deep Ensemble 的预测集中在 prob ≈ 0.8+（LQ 上 84% 的预测 > 0.3）
- 早期将 x 轴裁到 [0, 0.5] 把它们的过度自信行为完全切掉了
- 修复：还原全范围 [0, 1]，底部密度条让读者看到每个方法的预测分布

**问题 B — Fig 4 方法论错误（Simpson's Paradox）**
- 用 ITB（人为按 LQ/HQ/Edge/Diverse 分层）合并计算 entropy–q̄ ρ
- Std VIB 显示 ρ = −0.153，但论文声称 ρ ≈ −0.024（近零）
- 根因：ITB 的组间差异（不同 source、不同质量档）产生虚假跨组相关
- 修复：改用 HAM10000 zero-shot 数据（n=10,015，质量自然分布）
  - D (Std VIB): ρ = −0.033 ✅（接近论文全测试集的 −0.024）
  - F (Q-VIB Full): ρ = −0.164 ✅（接近论文声称的 −0.165）

#### 6. 更新 itb_paper.tex
- Abstract：模板文字 → 真实摘要
- Section 5.2：灰框占位 → `fig1_taxonomy`（双面板）+ `fig2_reliability`
- Section 5.4（Per-Degradation）：表格 + 文字分析 → `fig3_degradation` + 文字
- Section 5.5（Entropy-Quality）：新增小节 + `fig4_entropy_qbar`
- 最终 PDF：12 页，483 KB，零编译 error

---

### 待完成

| 优先级 | 任务 | 说明 |
|--------|------|------|
| 🔴 高 | 跑 `run_qcts.py` | 拿到 QCTS 真实数值，替换 Table 1 里的 `†` 投影值 |
| 🔴 高 | 重跑 `gen_bmvc_figures.py` | QCTS 结果出来后更新 fig1 的 QCTS 星号位置 |
| 🟡 中 | 论文正文 Intro / Related Work 润色 | 内容已有骨架，需要英文打磨 |
| 🟡 中 | Fig 2 进一步优化 | 目前曲线在高置信度区间仍有些噪声（少样本导致），可考虑合并末尾稀疏 bin |
| 🟢 低 | Reader Study 图（Fig 12） | 等找到 reader 后生成 |
| 🟢 低 | Zenodo 上传 | 接受后再做 |

---

### 文件清单

```
project/meeting/BMVC/
├── itb_paper.tex          ← 论文主文件（已有 4 张真实图）
├── itb_paper.pdf          ← 已编译 PDF，12 页
├── egbib.bib              ← 文献库（已修正格式错误）
├── bmvc2k.cls / .bst      ← BMVC 模板
├── BMVC_LOG.md            ← 本日志
└── figures/
    ├── fig1_taxonomy.pdf/png
    ├── fig2_reliability.pdf/png
    ├── fig3_degradation.pdf/png
    └── fig4_entropy_qbar.pdf/png

project/
├── run_qcts.py            ← QCTS 实验脚本（待跑）
└── gen_bmvc_figures.py    ← 图表生成脚本（可重跑更新图）
```
