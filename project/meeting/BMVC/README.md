# BMVC P2 投稿目录

**Deadline**: 2026-05-29 | **进度**: 12 页论文 + 4 张图完成，待 QCTS 实验和英文润色

---

## 📖 快速开始

1. **读计划**：`BMVC_PLAN.md`（5 分钟了解全局）
2. **看进度**：`BMVC_LOG.md`（最新日志）
3. **开始工作**：根据下面的文件导航找你需要的资源

---

## 📂 文件结构导航

### 顶层（投稿相关）

| 文件 | 用途 |
|------|------|
| **BMVC_PLAN.md** ⭐ | 投稿总计划（论文大纲 + 13 天日程 + 实验待办 + 终检清单） |
| **BMVC_LOG.md** | 工作日志（更新最新进展） |
| **README.md** | 本文件（目录导航） |

### 📝 `paper/` - 论文文件

论文编写和编译相关。

| 文件 | 说明 |
|------|------|
| **itb_paper.tex** | 主论文（12 页） |
| **itb_paper.pdf** | 编译产物（最新版） |
| **egbib.bib** | 参考文献数据库 |
| `itb_paper.aux / .bbl / .blg / .log` | LaTeX 编译产物（可忽略） |

**编译命令**：
```bash
cd paper/
pdflatex itb_paper
bibtex itb_paper
pdflatex itb_paper
pdflatex itb_paper
```

### 🎨 `figures/` - 论文图表

所有论文图表（PDF + PNG）。

**当前图表**（已完成）：
- `fig0_teaser.pdf / .png` — 3×3 皮肤镜图像矩阵 + 置信度对比
- `fig1_taxonomy.pdf / .png` — 校准分类法散点图（双面板）
- `fig2_reliability.pdf / .png` — 可靠性曲线（LQ/HQ 分层）
- `fig3_degradation.pdf / .png` — 逐退化 ECE 柱状图

**待生成图表**（QCTS 实验后）：
- `fig4_entropy_qbar.pdf / .png` — Entropy–q̄ Hexbin（HAM10000）
- `fig5_qcts_curve.pdf / .png` — 学到的温度函数 T(q̄)
- （可选）`fig6_pareto.pdf / .png` — AUC–ECE Pareto 前沿
- （可选）`fig7_crossdataset.pdf / .png` — 跨数据集 ρ

**生成方法**：
```bash
cd ../../
python gen_bmvc_figures.py  # 一键生成所有图
```

生成脚本已在 `project/gen_bmvc_figures.py`，输出到 `meeting/BMVC/figures/`。

**图表设计指南**：见 `plan/02_figures_guide.md`

### 📚 `reference/` - 模板和参考资料

BMVC 模板、示例论文、参考文献。

| 文件 | 说明 |
|------|------|
| **bmvc2k.cls** | BMVC LaTeX 文档类（必需） |
| **bmvc2k_natbib.sty** | natbib 支持包 |
| **bmvc2k.bst** | BibTeX 样式 |
| `bmvc_final.pdf / .tex` | BMVC 最终版示例（学习排版） |
| `bmvc_review.pdf / .tex` | BMVC 匿名版示例（学习匿名化） |
| `Author_Guidelines_for_the_British_Machine_Vision_Conference.zip` | 官方指南 |
| `pastpapers/` | 历年接受的 BMVC 论文（参考写作风格） |
| `images/` | 截图或参考图片 |

**何时用**：
- 修改论文格式 → 参考 `bmvc_final.pdf`
- 检查匿名化 → 参考 `bmvc_review.pdf`
- 学习文献格式 → 参考 `egbib.bib` + BMVC 示例

### 📋 `plan/` - 执行计划和实验指南

### 文件说明

**`plan/` 内容**（从根目录的计划文件汇总）：

| 文件 | 来源 | 用途 |
|------|------|------|
| **PLAN_OVERVIEW.md** | 新建综合 | 计划总览 + 日程 |
| **01_solution.md** | 原 `BMVC计划.md` | 核心策略、方案、论文大纲 |
| **02_figures_guide.md** | 原 `plan2.md` | 7 张图的详细设计指南（含代码） |
| **03_experiments_todo.md** | 原 `图表和实验计划.md` | 实验清单和代码框架 |

**使用场景**：
- 理解投稿策略 → 读 `01_solution.md`
- 画图时遇到问题 → 查 `02_figures_guide.md`（有代码框架）
- 跑实验卡住 → 参考 `03_experiments_todo.md`

### 📊 数据文件（project/results 里）

BMVC 相关的实验结果数据：

| 文件 | 内容 |
|------|------|
| `qcts_itb_results.csv` | QCTS 在 ITB 4 子集的评测结果 |
| `qcts_params.json` | 学到的 T₀ 和 α 参数 |
| `qcts_T_curve.npy` | 温度函数曲线（用于 Fig 5） |
| `per_degradation_ece.csv` | 逐退化拆解结果（用于 Fig 3） |
| `itb_subsets.csv` | ITB 子集定义 |

这些文件由 `project/run_qcts.py` 和 `gen_bmvc_figures.py` 生成。

---

## 🔄 工作流程

### 场景 1：修改论文内容

1. 编辑 `paper/itb_paper.tex`
2. 运行编译命令（上文）
3. 检查 `paper/itb_paper.pdf`

### 场景 2：更新或生成图表

1. 更新数据（确保 `project/results/` 里有最新的 CSV）
2. 运行 `python project/gen_bmvc_figures.py`
3. 检查 `figures/*.pdf` 和 `figures/*.png`
4. 如不满意，编辑 `project/gen_bmvc_figures.py`，重跑

### 场景 3：跑 QCTS 实验

1. 参考 `plan/03_experiments_todo.md` 的代码框架
2. 在 `project/` 下执行实验脚本（如 `python run_qcts.py`）
3. 确认产出：`results/qcts_itb_results.csv` 等
4. 重新生成图表（场景 2）

### 场景 4：投稿前最终检查

参考 `BMVC_PLAN.md` 的"投稿前终检清单"，逐项确认。

---

## ⏱️ 当前进度（2026-05-17）

| 任务 | 状态 | 预计完成 |
|------|:---:|---------|
| 论文大纲 | ✅ 完成 | - |
| 4 张初始图 | ✅ 完成 | - |
| QCTS 实验 | ⏳ 进行中 | 2026-05-18 |
| 剩余图表 | 🔴 待做 | 2026-05-19 |
| Introduction | ⏳ 骨架完成 | 2026-05-21 |
| Method + Experiments | 🔴 待写 | 2026-05-23 |
| Discussion + 英文润色 | 🔴 待做 | 2026-05-26 |
| 排版 + 匿名化 | 🔴 待做 | 2026-05-28 |
| **投稿** | 🔴 | **2026-05-29** |

---

## 💡 常见问题

**Q: 我想修改论文的某个数字，怎么办？**

A: 
1. 编辑 `paper/itb_paper.tex`
2. 重新编译：进入 `paper/` 目录，运行 `pdflatex × 2 + bibtex + pdflatex`
3. 新 PDF 会自动生成

**Q: 图表颜色不对，怎么改？**

A:
1. 编辑 `project/gen_bmvc_figures.py` 顶部的 `COLOR` 字典
2. 重新运行：`python project/gen_bmvc_figures.py`
3. 图表会更新

**Q: 我跑了新实验，怎么更新论文里的结果？**

A:
1. 确保新数据存在于 `project/results/` 
2. 更新 `paper/itb_paper.tex` 里的数字
3. 如有新图表，重新运行 `gen_bmvc_figures.py`
4. 重新编译论文

**Q: 需要投稿前检查什么？**

A: 见 `BMVC_PLAN.md` 的"投稿前终检清单"，包括：
- LaTeX 编译检查
- 图表质量（矢量化、颜色、字体）
- 匿名化（无作者名、无自引暴露）
- 页数控制（≤8 页）

---

## 🔗 相关链接

- **BMVC 官网**：https://bmvc2026.bmva.org/
- **OpenReview 投稿**：https://openreview.net/group?id=bmva.org/BMVC/2026/Conference
- **大项目总览**：`D:\YJ-Agent\project\PROJECT_OVERVIEW.md`
- **工作日志**：`D:\YJ-Agent\WORKLOG.md`

---

最后更新：2026-05-17 | 维护者：Claude
