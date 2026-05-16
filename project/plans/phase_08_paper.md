# 阶段八：论文写作（ICLR 2027，CCF-A 标准）

## 目标

基于前七个阶段的全部实验结果，撰写符合 ICLR 2027 标准的 9 页论文初稿，临床叙事为主线、ML 理论贡献为核心卖点。五大创新点（VisiScore-Net / Q-VIB / VisiEnhance-Net / 双通道 Agent / ITB Benchmark）在正文中均有充分展开，理论部分（4 个命题 + 1 个定理）有完整陈述，附录放完整证明和辅助实验。

---

## 前置条件

- 阶段七完成：VisiEnhance-Net 训练完毕，E3（诊断保持）和 E5（双通道效率）验收通过
- 所有论文图表就绪（预计 16 张，见下方图表规划）
- 所有数字已锁定，不在写作阶段再跑新实验
- ICLR 2027 LaTeX 模板已下载（`iclr2027_conference.sty`）

---

## 论文定位

### 与 MICCAI 的关键差异

| 维度 | MICCAI（原计划）| ICLR（当前目标）|
|------|----------------|----------------|
| 格式 | 8 页正文，无附录页数限制 | 9 页正文 + 无限附录 + 参考文献不计页数 |
| 评审焦点 | 临床价值 + 工程实现 | ML 方法论创新 + 理论严谨性 |
| 审稿人背景 | 医学图像分析专家 | 深度学习 / 信息论 / 概率 ML 研究者 |
| 匿名方式 | 双盲 | 双盲 |
| 主要定语 | "clinical AI system for triage" | "quality-conditioned uncertainty framework for medical AI" |

### 叙事主线（保持临床叙事，强化 ML 框架）

> "低质量输入下的 AI 可靠性"是一个普遍的 ML 问题。我们以皮肤镜分诊为动机场景，提出 **Q-VIB** 作为质量感知不确定度的通用框架，并进一步提出 **VisiEnhance-Net** 在理论保证下闭合"增强—诊断"回路，构成完整的质量—增强—诊断三模块统一理论。

**不改变**：临床背景（Introduction）、皮肤镜数据集、ITB 评测体系、Agent 追问叙事。
**加强**：用更多篇幅在 Introduction 中说清楚"这是一个一般性 ML 问题"，Related Work 加 Uncertainty Estimation 和 Image Restoration 两个方向的文献综述。

---

## 五大贡献陈述（论文 Introduction 贡献列表）

1. **VisiScore-Net**：首个面向皮肤镜的 5 维细粒度质量评估网络，为下游 Q-VIB 提供可微的质量信号（PLCC=0.924）

2. **Q-VIB（Quality-Conditioned VIB）**：将 VIB 框架推广到质量条件化先验，三个定理严格证明低质量图→高熵预测的单调性（Lemma 1 + Proposition 2 + Theorem 1）

3. **VisiEnhance-Net**：诊断保持型质量增强，在 Q-VIB 隐空间中用 DP-Loss 约束增强—诊断一致性，两个新定理建立增强与不确定度的桥梁（Proposition 3 + Lemma 3）

4. **双通道 Agent**：可修复退化走增强路径、不可修复退化走追问路径，退化可修复性判据有理论依据（$q_3$ 信息不可逆性）

5. **ITB Benchmark**：4 质量子集 × 9 条 baseline 的系统评测，开源可复现，填补领域空白

---

## 论文结构规划

| 章节 | 篇幅 | 核心内容 |
|------|------|---------|
| Abstract | ~250 词 | 问题 / 五大创新（各一句）/ 主要数字（E3 ΔAUC < 1.5%，Prop.2 ρ=−0.192，E5 SalvageRate > 55%）|
| **Introduction** | **~1.2 页** | 1) 低质量图像 = AI 可靠性问题（一般性 ML 动机）；2) 皮肤镜场景的临床紧迫性；3) 现有方法的两个割裂缺陷；4) 我们的方案概述；5) 贡献列表（5 条）|
| **Related Work** | **~1 页** | 6 个方向，每方向 2-3 句：① IQA（BRISQUE/NIMA/CLIP-IQA）② Uncertainty Estimation（MC Dropout/Ensemble/VIB）③ Image Restoration（NAFNet/Restormer）④ Calibration（TS/Focal Loss）⑤ Medical AI Agent ⑥ Information Bottleneck（Tishby/Alemi）|
| **Method** | **~3.5 页** | 3.1 VisiScore-Net（~0.3 页）→ 3.2 Q-VIB 理论框架（~1.2 页：Prop.1 ELBO + Lemma 1 + Theorem 1 + Prop.2）→ 3.3 VisiEnhance-Net（~1.2 页：NAFNet+FiLM + DP-Loss + Prop.3 + Lemma 3）→ 3.4 双通道 Agent（~0.8 页：决策逻辑 + 退化可修复性分析）|
| **Experiments** | **~2.5 页** | 4.1 数据集 + ITB 基准设置；4.2 主结果表（9 baseline × 4 子集）；4.3 Q-VIB 消融（Tab.2）；4.4 VisiEnhance-Net 核心实验（E3/E5）；4.5 Proposition 3 验证（E4）；4.6 对比 SOTA 增强方法（E10）；4.7 3-seed 鲁棒性 + 跨数据集 |
| Conclusion | ~0.3 页 | 总结 + 三大局限性（坦诚说明）+ 未来工作（Proposition 3 推广到其他任务域）|
| References | 不计页数 | 35-45 篇 |

### 篇幅控制策略

- Method 3.5 页 > 原 MICCAI 版本 2.5 页：ICLR 审稿人期望看到更充分的理论处理
- VisiEnhance-Net 架构细节（NAFBlock 内部 + 伪代码）移附录
- Proposition 3 + Lemma 3 完整证明放附录，正文给陈述 + 直觉解释（2-3 行）
- 如超过 9 页，先压 Related Work（每个方向只留 2 句）

---

## 关键图表规划

正文最多 8 张图（ICLR 惯例），附录不限。

### 正文图（建议 8 张）

| 编号 | 图名 | 信息 |
|------|------|------|
| Fig.1 | 系统总览（双通道架构图）| 输入 → VisiScore → 双通道决策 → 增强/追问/诊断，含理论定理标注位置 |
| Fig.2 | Q-VIB 概率图模型 + σ²(q̄) 曲线 | 展示 $X \to Z \leftarrow Q, Z \to Y$ + Lemma 1 曲线 |
| Fig.3 | Entropy vs q̄（Proposition 2）| F 单调下降 vs Std VIB 平坦，三数据集均显著 |
| Fig.4 | 主结果对比图（9 baseline × ITB 子集）| 折叠柱状图，F 在 ECE-LQ 上优势一目了然 |
| Fig.5 | VisiEnhance-Net 诊断保持图（E3）| A/B/C 三组 AUC 对比 + ΔAUC 置信区间 |
| Fig.6 | 双通道效率图（E5）| 按降质等级分层的挽救率 + Proposition 3 熵变化 |
| Fig.7 | 对比 SOTA 增强方法（E10）| 视觉质量（PSNR/SSIM）vs 诊断保持（ΔAUC）二维散点图，突出我们在诊断保持维度的优势 |
| Fig.8 | 端到端 Case Study | 2-3 个真实皮损的完整双通道流程（含增强前后对比）|

### 附录图（建议 6-8 张）

| 编号 | 内容 |
|------|------|
| Fig.A1 | AUC-ECE Pareto 图（原 Fig.8）|
| Fig.A2 | 失败案例 F vs B3 非对称错误分析（原 Fig.11）|
| Fig.A3 | 跨数据集 zero-shot 验证（原 Fig.9，HAM + PAD-UFES）|
| Fig.A4 | KL 崩塌曲线（原 Fig.10）|
| Fig.A5 | VisiEnhance 按退化类型 PSNR 分解（E2）|
| Fig.A6 | Proposition 3 完整验证（E4，三数据集）|
| Fig.A7 | Reader Study（S3.1，若完成）|

---

## 关键技术决策点

### 论文标题（待最终确认）

1. *VisiSkin-Agent: Quality-Conditioned Uncertainty and Diagnosis-Preserving Enhancement for Smartphone Dermoscopy Triage*（直白，完整覆盖两个核心贡献）
2. *Closing the Loop: A Unified Quality–Enhancement–Diagnosis Framework with Calibrated Uncertainty*（强调理论闭环，ICLR 审稿人更易共鸣，但需要在正文中讲清通用性）
3. *Q-VIB: Quality-Adaptive Variational Information Bottleneck with Diagnosis-Preserving Enhancement*（以 Q-VIB 为锚点，最直接）

**建议**：优先选选项 1 或 3——ICLR 审稿人看标题时会快速定位"这是 VIB 的改进"或"这是一个系统论文"，两者都合适。与导师讨论后最终确认。

### 作者顺序

需要提前与导师确认：一作 / 通讯作者 / 合作者名单和单位。

### 开源策略

ICLR 强烈鼓励开源，已有 reproduce.sh + README.md + requirements.txt，还需：
- 上传 HuggingFace 或 GitHub releases（VisiScore + Q-VIB + VisiEnhance 三套权重）
- Zenodo 存档数据集分割文件（`data/isic_split.csv`）
- 代码中移除任何硬编码路径

---

## CCF-A 质量自检清单

提交前逐条核对：

### 理论部分
- [ ] Lemma 1 / Proposition 2 / Theorem 1 / Proposition 3 / Lemma 3 在正文中全部有陈述（不只在附录）
- [ ] 每个命题有 1-2 行直觉解释，不只是公式堆砌
- [ ] 附录中所有证明步骤可独立验证，引用的不等式（Pinsker / Jensen 等）有出处
- [ ] 符号定义在一个统一的表格中，全文符号一致

### 实验部分
- [ ] 主结果表中所有数字与 `results/itb_results.csv` 完全一致
- [ ] 误差棒来源已在 caption 说明（bootstrap CI / ±std / ±SEM）
- [ ] 显著性检验结果（p 值或置信区间）已报告，不只是点估计
- [ ] 消融实验覆盖所有关键设计选择（DP-Loss / FiLM / Q 条件 / 双通道决策）
- [ ] Baseline 实现细节（超参、随机种子）在附录中说明，确保可复现
- [ ] 3-seed 鲁棒性验证结果已报告

### 写作部分
- [ ] Related Work 中每条引用都说清楚"和我们的区别"，不只是"A 做了 B"
- [ ] Limitation 章节坦诚列出至少 3 条局限性（如：依赖 ISIC 质量分布；Reader Study 人数有限；增强仅覆盖 4 类退化）
- [ ] 诊断术语使用符合规范（"assistance tool"，不写"diagnosis system"）
- [ ] 所有缩写在首次出现时展开（Q-VIB、VIB、IQA、ECE、AUC 等）

### 格式部分
- [ ] `pdflatex main.tex` 无 Warning 编译通过，PDF 恰好 9 页
- [ ] 所有图表为矢量图（PDF/EPS），DPI ≥ 300（位图）
- [ ] 参考文献格式统一（ICLR 要求用 iclr2027.bst 格式）
- [ ] 匿名版本中无自我引用可追溯信息（GitHub 链接 / 数据集 URL 替换为 "anonymous"）

---

## 工作步骤

1. **锁定所有数字**：确认 E3/E5/E10 实验完成，数字不再变动

2. **撰写 Method 章节**：
   - 优先写 3.2 Q-VIB（理论最密集）和 3.3 VisiEnhance-Net（新内容最多）
   - 确保 Proposition 3 + Lemma 3 的正文陈述和直觉解释清晰
   - 再写 3.1 VisiScore-Net / 3.4 双通道 Agent

3. **撰写 Experiments 章节**：
   - 先画出所有表格框架，填数字
   - 核心：E3 表格（三组对比）+ E5 分层挽救率 + 主结果表

4. **撰写 Introduction + Related Work**：
   - Introduction 前两段要从"一般性 ML 问题"切入，不能直接从皮肤科开场
   - Related Work 补充 Uncertainty Estimation 和 Image Restoration 两个方向

5. **生成/更新论文图表**：
   - Fig.1 系统总览（draw.io，需重新设计以包含 VisiEnhance-Net 双通道）
   - Fig.5/6/7 是新增图（VisiEnhance-Net 实验），需从 eval_visienhance.py 结果生成
   - 其余图更新为 ICLR 格式（字体大小、DPI 等）

6. **撰写附录**：完整证明 + 辅助实验 + Baseline 实现细节

7. **整合 LaTeX + 编译验证**：确认 9 页，无 Warning，所有交叉引用正确

8. **CCF-A 质量自检**：逐条过上方清单

---

## 图表工具

| 工具 | 用途 |
|------|------|
| LaTeX + ICLR 模板 | 论文正文编译 |
| draw.io | 系统架构图（Fig.1）+ Q-VIB 概率图（Fig.2）|
| matplotlib | 实验结果图（从现有 analyze_results.py + eval_visienhance.py 生成）|
| Zotero | 文献管理，导出 BibTeX |
| Overleaf（可选）| 在线协作 |

---

## 必须引用的关键文献

| 文献 | 原因 |
|------|------|
| Alemi et al., ICLR 2017 (VIB) | Q-VIB 的直接前驱 |
| Tishby et al., Allerton 1999 (IB) | Information Bottleneck 原理 |
| Kingma & Welling, ICLR 2014 (VAE) | 重参数化技巧 |
| Gao & Pavel, arXiv 2017 (Softmax 扰动) | Theorem 1 证明工具 |
| Chen et al., ECCV 2022 (NAFNet) | VisiEnhance-Net 骨干 |
| Perez et al., AAAI 2018 (FiLM) | 质量条件调制 |
| Zamir et al., CVPR 2022 (Restormer) | 对比基线 |
| Lin et al., ECCV 2024 (DiffBIR) | 对比基线 |
| Guo et al., ICML 2017 (Temperature Scaling) | 校准 baseline |
| Gal & Ghahramani, ICML 2016 (MC Dropout) | Baseline I |

---

## 验收标准

- `pdflatex main.tex` 无 Warning，PDF 精确 9 页（不含参考文献和附录）
- 五大贡献在正文中均有对应的实验验证（不只是 claim）
- 五个定理（Lemma 1 / Prop.1 / Theorem 1 / Prop.2 / Prop.3 / Lemma 3）在正文中全部有陈述
- Limitation 章节至少 3 条
- 所有表格数字与 CSV 文件一致（单人核查 + 脚本核查双重验证）
- CCF-A 质量自检清单全部打勾

---

## 注意事项

- ICLR 2027 投稿时间预计在 2026 年 9-10 月，提交前务必确认官方 deadline
- **ICLR 是双盲评审**：匿名版本中不得出现作者姓名、GitHub 账号、机构等可追溯信息；Zenodo / HuggingFace 链接替换为 "anonymous code available at [link]"
- Introduction 的"一般性 ML 问题"切入不能脱离临床背景：先说清低质量输入对 AI 的威胁是普遍问题（举 1-2 个非医疗例子），再快速收到皮肤镜场景，避免让 ICLR 审稿人误以为这只是一篇工程论文
- 若 Reader Study（S3.1）在写作阶段仍未完成，将其放入"Limitation + Future Work"，不要作为主结果呈现
