# BMVC P2 工作日志

---

## 2026-05-16

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
