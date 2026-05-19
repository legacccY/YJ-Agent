# BMVC P2 投稿目录

**Deadline**: 2026-05-29 | **当前状态**: ⚠️ 创新性升级中（剥离 Q-VIB / VisiScore-Net + 杠杆 1/2/3）

---

## ⚡ 下次启动 Claude Code 的第一步

**只读这一个文件即可了解全貌**：

👉 [`BMVC_LOG.md`](BMVC_LOG.md) — **单一日志真源**，看 `2026-05-19` entry：
- 当前策略调整背景（为什么剥离 Q-VIB / VisiScore-Net）
- 已完成项清单
- ⚠️ **下次执行 checklist**（P0 → P1 → P2 顺序 + 具体命令）
- 待决策项

**所有其他 plan / 旧计划文件都在 `archive/` 子目录，不要读，避免走弯路。**

---

## 📂 当前活跃文件

```
project/meeting/BMVC/
├── BMVC_LOG.md            ← 单一日志，从这里开始
├── README.md              ← 本文件（精简入口）
├── itb_paper.tex          ← 论文主文件（14 页，零 error）
├── itb_paper.pdf          ← 当前编译输出
├── table1_main.tex        ← 主表（待删 E/F/G 三行，见 LOG checklist）
├── table2_ablation.tex    ← QCTS form ablation 表
├── egbib.bib              ← 文献（已删 anonymous 自引）
├── bmvc2k.cls/.bst        ← BMVC 模板
└── figures/               ← 4 张主图 + fig_method.svg（待重做，删 F/G 标注）

archive/                   ← 历史 plan，不再使用
├── BMVC_PLAN.md           ← 旧总计划（已被 BMVC_LOG 替代）
├── BMVC计划.md            ← 旧中文计划（重复）
├── 图表和实验计划.md       ← 旧图表清单
└── plan_old/              ← 旧 plan 子目录
```

---

## 🔬 BMVC 创新点（精简版）

1. **TS 反转发现**（Std VIB ρ=-0.024 → +TS ρ=+0.241，符号翻转）— BMVC 一级 finding
2. **QCTS 方法 + derivation**（从 inductive biases 推导 softplus 形式）
3. **ITB Benchmark**（4 数据集 × 4 quality 分层子集）
4. **QCTS 通用性**（4 backbones 横跨 EfficientNet/ResNet/ViT，待训练）
5. **QAC/QCDI/Taxonomy 评测框架**

---

## ⚠️ 严禁事项

- ❌ 不要在 BMVC 论文里出现 `Q-VIB` / `VisiScore-Net` / `anonymous2025*` 字样
- ❌ 不要在 fig_method 灰框里写 "VisiScore-Net"，必须是 "5-head IQA"
- ❌ 不要 cite 未发表工作（Sensoy 2018 EDL 是已发表，可 cite）
- ❌ 不要凭印象写数字，所有 ρ/CI/p-value 必须从代码核算
