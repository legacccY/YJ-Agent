# ICLR 2027 投稿目录（M3 启动）

**Deadline**：2026-09-22（abstract）/ 2026-09-29（full paper）
**当前状态**：⏳ M3 (W9, 2026-07-23) 启动，目前空骨架
**主指导**：`../../README.md` + `../../STORY_FRAMEWORK.md`

---

## 计划文件结构（M3 启动时填）

```
meeting/ICLR2027/
├── README.md              ← 本文件
├── iclr2027.tex           ← 主文 9 页（M3 D1 起草）
├── iclr2027_supp.tex      ← Supp 50-80 页（M3 D8 起草）
├── iclr2027.cls           ← ICLR 模板（M3 W9 D1 下载）
├── egbib.bib              ← 文献（M3 W9 D2 整理）
├── figures/               ← 图表（M3 W10 起）
│   ├── fig1_teaser.{pdf,svg}
│   ├── fig2_method.{pdf,svg}
│   ├── fig3_results.{pdf,svg}
│   └── fig4_ablation.{pdf,svg}
├── tables/                ← Table tex
│   ├── table1_main.tex
│   ├── table2_universality.tex
│   ├── table3_crossdomain.tex
│   └── table4_ablation.tex
└── reviews/               ← 10 轮 LLM adversarial review（M4 W13 起）
    ├── round01_iclr_senior_ac.md
    ├── round02_calibration_expert.md
    ├── ...
    └── round10_copy_editor.md
```

---

## 附录指针

- `appendix/A27_generalization_fairness.tex` — 补充 analysis 附录（§\label{app:gen-fair}）：cross-source 泛化（fig:crossdomain，源 external_*_predictions.csv，Jun14-15 ICLR 重跑）+ skin-tone fairness（fig:fairness-fitz，源 fairness_fitzpatrick_iclr_full.csv，ICLR 专属）。R10 口径，只用 ICLR 重跑数；fairness 仅报 AUC 差异（不碰 ECE）。诚实边界 framing，不改 C1/C2 headline。待主线 \input 进 main.tex + 加正文指针。

---

## ⚠️ 严禁

- ❌ 从 BMVC 直接搬 fig / tex / 数字（必须重跑，cite-as-paper 引用方式）
- ❌ M1-M2 期间动手写 tex（数据/实验未就位，写 = 跑偏）
- ❌ 改 §1-§7 章节顺序（已锁定，详见 ../../STORY_FRAMEWORK.md）

---

## M3 W9 D1 启动 checklist

1. 下载 ICLR 2027 官方模板（`iclr2027.cls` + style 文件）
2. cd 到本目录，跑 `pdflatex iclr2027.tex` 验证模板可编译
3. Read `../../STORY_FRAMEWORK.md` §1-§9 章节顺序，起 tex 骨架
4. Read `../../ACCEPTANCE_CRITERIA.md` 25 lever 表，确认每条 lever 写哪个 section
5. 写 §1.1 + §1.2 + §1.3 hook（不要超 1 页）
