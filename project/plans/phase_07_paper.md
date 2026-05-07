# 阶段七：论文写作

## 目标

基于前六个阶段的实验结果，撰写 MICCAI 2027 格式的 8 页论文初稿，确保 LaTeX 可编译，图表完整，内容覆盖四大创新点（VisiScore-Net、Q-VIB 理论框架、QAD 工程集成、ITB 评测基准），且理论部分（Q-VIB 的 Proposition 1 / Theorem 1 / Proposition 2）有充分空间展开。

---

## 前置条件

- 阶段六完成：ITB 实验数据、对比表格、可视化图表全部就绪
- 所有模型性能指标已确认（含 Q-VIB 消融实验结果）
- MICCAI 2027 的 LaTeX 模板（.cls 文件）已下载

---

## 本阶段工具

| 工具 | 用途 |
|------|------|
| LaTeX + MiKTeX / TeX Live | 本地编译 MICCAI 格式论文 |
| MICCAI .cls 模板 | 官方格式模板，投稿必须使用 |
| Zotero | 文献管理，一键导出 BibTeX |
| draw.io | 绘制系统架构图（免费，导出 PDF 矢量图） |
| matplotlib | 结果对比图（由 analyze_results.py 直接生成，保持与数据一致） |
| Overleaf（可选） | 在线 LaTeX 编辑，适合多人协作修改 |

---

## 关键技术决策点

1. **论文标题**（选一个）：
   - *VisiSkin-Agent: Quality-Guided Visual Triage for Skin Lesion Analysis*
   - *Iterative Quality-Aware Triage: An Agent Framework for Dermatology Screening*
   - *Ask Before Diagnose: A Quality-Gated Agent for Skin Lesion Triage*
   - ***Q-VIB: Quality-Conditioned Variational Information Bottleneck for Skin Lesion Triage***（新增，强调理论贡献）
   
   选择建议：如果 Q-VIB 消融实验效果显著（低质量段 ECE 大幅优于固定先验），优先选第 4 个——以方法论创新作为标题锚点，在 MICCAI 审稿中更容易建立理论深度印象。

2. **作者顺序**：一作 / 通讯作者 / 合作者姓名和单位需要提前确认

3. **MICCAI .cls 模板**：需要提前下载官方模板，确认投稿系统接受的格式版本

---

## 交付物清单

| 文件 | 用途 |
|------|------|
| `paper/main.tex` | 完整论文正文（8 页 MICCAI 格式） |
| `paper/figures/arch.pdf` | 系统架构图（矢量图），需展示 Q-VIB 概率图模型 |
| `paper/figures/q_vib_prior.pdf` | Q-VIB 质量自适应先验示意图：$\sigma^2(\bar{q})$ 曲线 + KL 项随 $\bar{q}$ 变化 |
| `paper/figures/examples.pdf` | 质量引导交互示例图 |
| `paper/figures/results.pdf` | 主要实验对比图（含 Q-VIB 消融） |
| `paper/references.bib` | 参考文献（BibTeX 格式，~25-30 篇） |

---

## 论文结构规划

| 章节 | 篇幅 | 核心内容 |
|------|------|---------|
| Abstract | ~250 词 | 问题/方法/四大创新（VisiScore-Net → Q-VIB → QAD → ITB）/主要结果 |
| Introduction | ~1 页 | 动机：自拍皮肤照片的质量异质性 → 现有 IQA 不提供可操作反馈 → 现有分类器无质量校准 → 我们提出质量条件化 VIB + Agent 交互式分诊 |
| Related Work | ~0.5 页 | IQA（BRISQUE/NIMA）、皮肤病分析（ISIC 分类/SAM 分割）、Medical Agent（ReAct/视觉问答）、Information Bottleneck（Tishby 2000 / VIB Alemi 2017） |
| **Method** | **~2.5 页**（扩展） | **3.1** VisiScore-Net（5 维质量评估）→ **3.2 Q-VIB 理论框架**（核心，~0.8 页：Proposition 1 ELBO 推导、质量自适应先验 Eq.7-9、质量分词器 + Theorem 1 注意力漂移界、Proposition 2 校准保证）→ **3.3** QAD 工程集成（分割 + ABCD + 分类器）→ **3.4** Agent 系统（ReAct + 追问策略） |
| Experiments | ~2 页 | ITB 4 子集基准 + 对比实验 + **Q-VIB 消融实验**（固定先验 vs 自适应先验、无/有质量分词器）+ 校准曲线（ECE vs $\bar{q}$ 分段）+ 显著性检验 |
| Conclusion | ~0.3 页 | 总结 + 局限性 + 未来工作 |
| References | ~0.5 页 | 25-30 篇参考文献 |

### 篇幅控制说明

Method 从 ~2 页扩展到 ~2.5 页，需要从 Introduction 和 Related Work 各挤压 ~0.2 页。具体做法：
- Introduction 最后一段的贡献列表用紧凑 itemize（压缩 ~0.1 页）
- Related Work 中 IQA 和皮肤病分析各压缩 1-2 句（压缩 ~0.1 页）
- 如果仍超页，考虑将 Proposition 1 的详细推导放入 Supplementary Material，正文只保留陈述和直观解释

---

## 工作步骤

1. **确认论文标题和作者**：与合作者对齐，确认贡献点表述；Q-VIB 作为理论贡献在作者贡献声明中应单独列出
2. **撰写 Method 章节**：优先写 **Section 3.2 Q-VIB**（理论最密集、最需要打磨），再写 3.1/3.3/3.4
3. **撰写 Experiments 章节**：直接引用 ITB 结果，重点编排 Q-VIB 消融实验表格和校准曲线图
4. **撰写 Introduction 和 Related Work**：基于 Method 和 Experiments 反写动机；Related Work 必须包含 IB/VIB 文献脉络
5. **生成论文图表**：
   - 架构图（draw.io）：需展示 VisiScore-Net → Q-VIB 编码器（含质量自适应先验 + 质量分词器）→ 分类器 → Agent 的完整数据流
   - Q-VIB 先验示意图（matplotlib）：$\sigma^2(\bar{q})$ 曲线 + KL 项随 $\bar{q}$ 变化的双轴图
   - 结果图：由 `analyze_results.py` 直接生成 PDF
6. **整合 LaTeX + 编译验证**：确保无报错，页数符合要求，参考文献格式正确

---

## 验收标准

- `pdflatex main.tex` 编译无错误，生成 8 页 PDF
- Q-VIB 三个命题（Proposition 1 / Theorem 1 / Proposition 2）在 Method 中有完整陈述和简洁证明（或指向 Supplementary）
- 图表清晰，文字可读，无图文压缩失真
- 所有表格中的数字与 `itb_results.csv` 完全一致
- 参考文献格式符合 MICCAI 要求，**必须包含** Alemi et al. 2017 (VIB)、Tishby et al. 2000 (IB)、Kingma & Welling 2014 (VAE/reparameterization)、Gao & Pavel 2017 (softmax 扰动界)
- 消融实验表至少包含 4 行：① 标准 VIB（固定先验） ② Q-VIB 无质量分词器 ③ Q-VIB 完整版 ④ 硬门控 baseline

---

## 硬件/资源约束

- 此阶段为写作工作，无 GPU 需求
- LaTeX 编译在本机即可完成

---

## 注意事项

- MICCAI 2027 投稿截止日期需要提前确认，预留 2-4 周审稿前缓冲时间
- 论文中的诊断术语使用要谨慎，不能夸大临床价值，强调"辅助工具"而非"诊断系统"
- **Ablation Study 需扩展为至少 4 组对比**（含 Q-VIB 组件消融）：
  1. 标准 VIB（固定先验 $\mathcal{N}(0, I_d)$，无质量条件化）
  2. Q-VIB 仅先验自适应（无质量分词器）
  3. Q-VIB 完整版（先验自适应 + 质量分词器）
  4. 硬门控 baseline（$\bar{q} < \tau$ 拒绝诊断）
  5. （可选）无质量过滤的端到端分类器
- **Q-VIB 理论的呈现策略**：如果 8 页空间紧张，Proposition 1 的完整推导可以放入 Supplementary Material，正文只给陈述 + 一两行直觉解释；但 Theorem 1 和 Proposition 2 必须在正文中给出——它们是 Q-VIB 区别于普通"调一下先验方差"的关键
- **质量分词器**（Theorem 1 相关）的注意力漂移可视化可以作为一个有力的实验图：展示 $\mathbf{q}$ 从 $\mathbf{1}$ 到 $\mathbf{0}$ 时 attention map 的变化
- 架构图是 MICCAI 审稿人第一眼关注的地方，投入足够时间设计清晰的系统图，确保 Q-VIB 的概率图模型结构（$X \to Z \leftarrow Q$, $Z \to Y$）一目了然
- 如果某阶段实验结果不理想，在 Limitation 章节诚实说明，不要隐瞒
- **Related Work 新增条目提醒**：Information Bottleneck 和 VIB 是相对小众的方向，在医学图像分析领域很少出现——这正是我们的差异化优势。Related Work 中需要简要介绍 IB 原理，建立上下文
