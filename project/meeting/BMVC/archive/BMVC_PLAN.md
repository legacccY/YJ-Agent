# BMVC P2 投稿总计划

**Deadline**: 2026-05-29（12 天）| **Status**: 论文框架 12 页 + 4 张图完成，待 QCTS 实验确数

---

## 🎯 核心策略

### 投稿亮点：定义 Quality-Aware Calibration 问题
- **传统校准**：假设数据 i.i.d.，最小化全局 ECE
- **现实问题**：医学图像质量波动剧烈，i.i.d. 假设崩溃
- **我们的贡献**：
  1. **QAC 问题定义** + QCDI 指标（ECE_LQ - ECE_HQ）
  2. **QCTS 方法**：Temperature Scaling + quality function T(q̄)
  3. **分类学分析**：9 方法分三类（Quality-Oblivious / Fragile / Aware）

### 为什么选 BMVC
| 维度 | BMVC 偏好 | 我们的匹配 |
|------|---------|----------|
| 论文类型 | 接受 insight/analysis paper | ✅ 首次形式化 QAC |
| 实验量 | thorough evaluation | ✅ 9 方法×4 子集×4 数据集 |
| 不确定性/校准 | 往年常见 | ✅ 医学 AI 校准核心 |
| 开源鼓励 | 强烈鼓励 | ✅ ITB + QCTS 代码包 |

---

## 📋 论文框架（BMVC 8 页）

```
1. Introduction (1 p)
   ├─ Hook: 皮肤镜诊断中的质量危机
   ├─ 现有校准方法全是 quality-oblivious
   └─ 贡献：QAC 定义 + QCTS + ITB benchmark

2. Related Work (0.5 p)
   ├─ ECE 和校准方法回顾
   ├─ 医学 AI benchmarks
   └─ Distribution shift under quality

3. Quality-Aware Calibration (1.5 p)      ← 概念创新
   ├─ 问题定义：质量条件下的校准
   ├─ QCDI 指标
   ├─ 分类学：三类校准失效模式
   └─ 图：分类学散点图 (Fig 1)

4. Quality-Conditioned Temperature Scaling (0.5 p)  ← 方法创新
   ├─ 方法描述：T(q̄) = softplus(T₀ + α·(1-q̄))
   └─ 优化方式：L-BFGS on val set

5. ITB Benchmark (0.5 p)
   ├─ 4 子集构造（LQ/HQ/Edge/Diverse）
   └─ 9 个 baseline 选择和对比

6. Experiments (2.5 p)
   ├─ 6.1 主结果：表 1（9 方法 × 5 指标）
   ├─ 6.2 分类学可视化：可靠性曲线 (Fig 2)
   ├─ 6.3 逐退化拆解：柱状图 (Fig 3)
   ├─ 6.4 Entropy-q̄ 单调性：Hexbin (Fig 4)
   ├─ 6.5 QCTS vs TS：T(q̄) 曲线 (Fig 5)
   └─ 6.6 跨数据集：HAM10000 / PAD-UFES (Fig 6)

7. Discussion (0.5 p)
   ├─ 为什么现有方法失败
   ├─ QCTS 的局限性
   └─ ITB 作为医学 AI 社区标准

8. Conclusion (0.5 p)
```

---

## 📊 图表清单（8 张 PDF）

### 必做图（核心论证）

| # | 标题 | 内容 | 数据来源 | 状态 |
|:-:|------|------|---------|:---:|
| **Fig 1** | Calibration Taxonomy Map | 散点图 + 三区域背景色：Quality-Oblivious/Fragile/Aware | 主结果表 | ✅ 数据齐 |
| **Fig 2** | Reliability Diagrams | 双面板（LQ/HQ），4 个代表方法的校准曲线 | 现有校准图 | ✅ 数据齐 |
| **Fig 3** | Per-Degradation ECE | 分面柱状图：4 退化类型 × 5 方法 | QCTS 实验产出 | ⏳ 待跑 |
| **Fig 4** | Entropy vs q̄ Hexbin | 6 条方法的熵-质量相关，双面板对比 | HAM10000 zero-shot | ✅ 数据齐 |
| **Fig 5** | QCTS Learned T(q̄) | 3 个 seed 的温度函数曲线 | QCTS 参数 | ⏳ 待跑 |

### 可选图（丰富论证）

| # | 标题 | 内容 | 数据来源 | 优先级 |
|:-:|------|------|---------|:---:|
| **Fig 6** | AUC–ECE Pareto | ECE vs AUC 散点图，QCTS 突出 | 现有数据 | 中 |
| **Fig 7** | Cross-Dataset ρ | 3 数据集 × 5 方法的 Spearman ρ | 现有数据 | 低 |

### 表

| # | 标题 | 内容 | 状态 |
|:-:|------|------|:---:|
| **Table 1** | Main Results | 9 方法 × (ITB-LQ AUC / ECE / ITB-HQ ECE / QCDI / ρ) | ⏳ QCTS 待确数 |
| **Table 2** | Per-Degradation ECE | 4 退化类型 × 5 方法 | ⏳ 待跑 |
| **Table 3** | ITB Subset Statistics | n / q̄均值±std / 正例比 / 数据源 | ✅ 数据齐 |

---

## ⏳ 13 天执行计划（5/17~5/29）

### Week 1: 实验 + 数据 + 初稿（5/17-5/23）

**Day 1-2（5/17-18）：补实验**
- [ ] QCTS 优化：验证集上的 T₀ 和 α 参数
- [ ] 在 ITB 4 子集推理 → 得 ECE / AUC / QCDI / ρ
- [ ] 逐退化拆解：4 质量维度 × 5 方法
- [ ] 输出：Table 1 + Table 2 + Fig 3 + Fig 5 数据

**Day 3（5/19）：图表生成**
- [ ] 运行 `gen_bmvc_figures.py`（所有 8 张图）
- [ ] 检查配色一致、轴范围、标注清晰

**Day 4-5（5/20-21）：Introduction + Related Work + Method**
- [ ] Intro：问题定义 → 贡献列表
- [ ] Related Work：校准方法 + 医学 AI 文献
- [ ] QAC 定义：数学公式 + QCDI + 分类学

**Day 6-7（5/22-23）：Experiments 全节**
- [ ] 6.1-6.6 逐小节写
- [ ] 嵌入表 1-3 和图 1-8
- [ ] 组织叙事：从分类学 → QCTS 有效性 → 跨数据集泛化

### Week 2: 打磨 + 投稿（5/24-5/29）

**Day 8-9（5/24-25）：Discussion + 英文润色**
- [ ] Discussion：为什么现有方法失败 / QCTS 局限 / 未来方向
- [ ] Conclusion
- [ ] 全篇英文拼写 + 语法检查

**Day 10-11（5/26-27）：排版 + 匿名化**
- [ ] BMVC 模板排版（页数控制 ≤8 页）
- [ ] 匿名化检查：无作者名、无机构、无自引暴露
- [ ] 图表 PDF 矢量化 + 字体检查

**Day 12（5/28）：最终审阅**
- [ ] LaTeX 完整编译（pdflatex × 2 + bibtex + pdflatex）
- [ ] 发给导师过目 + 反馈汇总
- [ ] 终检清单（见下文）

**Day 13（5/29）：投稿**
- [ ] OpenReview 上传
- [ ] 确认收货

---

## 🔬 待跑实验清单（精确到代码）

### 实验 1：QCTS 优化 + 推理（1 天）

**步骤**：
```python
# 1. 加载 Std VIB 在验证集上的 logits 和 q_bar
logits_val, q_bar_val, labels_val = load_val_set()

# 2. 定义 QCTS
class QCTS(nn.Module):
    def forward(self, logits, q_bar):
        T = F.softplus(self.T0 + self.alpha * (1 - q_bar))
        return logits / T.unsqueeze(-1)

# 3. 用 L-BFGS 优化 T0 + alpha
model = QCTS()
optimizer = torch.optim.LBFGS([model.T0, model.alpha], max_iter=200)
for iteration in range(20):
    optimizer.step(closure)  # closure 计算 CrossEntropy loss

# 4. 在 ITB 4 子集推理，计算 ECE / AUC / QCDI / rho
# 输出：qcts_params.json, qcts_itb_results.csv
```

**输出**：
- `qcts_params.json`：T₀, α 值 × 3 seed
- `qcts_itb_results.csv`：9 方法 × 4 子集的评测结果
- `qcts_T_curve.npy`：Fig 5 绘图用

### 实验 2：逐退化拆解（0.5 天）

**步骤**：
```python
# 按 q1/q2/q4/q5 的最小值分类 ITB-LQ 图像
# 对每类，计算 MC Dropout / Ensemble / Std VIB / Q-VIB / QCTS 的 ECE
# 输出：per_degradation_ece.csv

deg_types = ['blur', 'low_brightness', 'color_temp', 'low_contrast']
for deg_type in deg_types:
    for method in [MC_Dropout, DeepEns, StdVIB, QVIB, QCTS]:
        ece = compute_ece(predictions[mask], labels[mask])
        print(f"{deg_type} {method}: ECE={ece:.3f}")
```

**输出**：
- `per_degradation_ece.csv`：Table 2 数据
- Table 2 LaTeX 片段

### 实验 3：QCDI 汇总（0.2 天）

**步骤**：
```python
# QCDI = ECE(ITB-LQ) - ECE(ITB-HQ)
for method in all_methods:
    qcdi = ece_lq[method] - ece_hq[method]
    print(f"{method}: QCDI={qcdi:.3f}")
# 补 Table 1 的 QCDI 列
```

---

## ✅ 投稿前终检清单

### LaTeX 编译
- [ ] `pdflatex × 2 + bibtex + pdflatex` → 零 error
- [ ] 无 "??" 引用断裂
- [ ] 页数 ≤ 8 + ref

### 浮动体
- [ ] 每张图在首次 `\ref` 后同一页或下一页
- [ ] 每张表在首次引用后同一页
- [ ] 各节末尾有 `\FloatBarrier`

### 图表质量
- [ ] 所有图 PDF 矢量（非 PNG）
- [ ] 同一方法跨图颜色一致（COLOR 字典）
- [ ] **灰度打印测试**：所有颜色编码差异仍可辨识
- [ ] **色盲兼容**：红/绿对比不用于关键分组
- [ ] 字体与正文一致（text.usetex=True）

### 表格
- [ ] booktabs 三线表（\toprule / \midrule / \bottomrule）
- [ ] 无竖线
- [ ] 最优值 \textbf{}，次优 \underline{}
- [ ] 数字右对齐，小数点对齐

### 匿名化
- [ ] ❌ 无作者名、机构名、Acknowledgment
- [ ] ❌ 自引改为 "Anonymous et al., under review"
- [ ] ❌ 代码链接为匿名仓库（若有）
- [ ] ✅ PDF 元数据干净

### 内容
- [ ] 论文长度合理（8 页 + ref）
- [ ] 数字对应最新实验结果
- [ ] 图表标题和 caption 清晰完整

---

## 📂 文件结构（本文档生效后）

```
meeting/BMVC/
├── BMVC_PLAN.md ← 你在这里
├── README.md
│
├── paper/
│   ├── itb_paper.tex / .pdf         主论文
│   ├── egbib.bib                    参考文献
│   └── *.aux / *.log / *.bbl       编译产物
│
├── figures/
│   ├── fig1_taxonomy.pdf / .png
│   ├── fig2_reliability.pdf / .png
│   ├── fig3_degradation.pdf / .png
│   ├── fig4_entropy_qbar.pdf / .png
│   ├── fig5_qcts_curve.pdf / .png
│   ├── fig6_pareto.pdf / .png
│   ├── fig7_crossdataset.pdf / .png
│   └── archive/                    旧版本备份
│
├── reference/
│   ├── bmvc_final.pdf              模板示例
│   ├── bmvc_review.pdf             匿名版示例
│   ├── bmvc2k.cls / .sty / .bst    BMVC 模板
│   ├── Author_Guidelines.zip
│   ├── pastpapers/                 历年论文
│   └── images/                     截图
│
├── plan/
│   ├── 01_solution.md              完整方案
│   ├── 02_figures_guide.md         7 张图详细设计
│   └── 03_experiments_todo.md      实验代码框架
│
└── BMVC_LOG.md                     日志（更新中）
```

---

## 📞 关键联系信息

| 项 | 信息 |
|----|------|
| **Deadline** | 2026-05-29 23:59 UTC |
| **投稿平台** | OpenReview (openreview.net/group?id=bmva.org/BMVC/2026) |
| **论文格式** | BMVC 模板 (bmvc2k.cls)，≤8 页 |
| **图表格式** | PDF 矢量 + PNG 预览，DPI 300 |
| **匿名要求** | 双盲审，无自引暴露 |

---

最后更新：2026-05-17
