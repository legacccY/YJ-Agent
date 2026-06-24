# HyperFidBench — 超图 GNN 脑病分类的解释忠实度 benchmark

> 组合台子项目入口。源自选题流水线 `project/ideation/runs/2026-06-24` G6 立项（headline 1，双 headline 并行之一；姊妹篇 [[WaveFidBench]]）。立项日 2026-06-24（用户拍板双 headline 并行）。
> 对齐导师王水花(Shuihua Wang)**超图 GCN 独门方向**（RHOAGCN / TGPO-WRHNN 系）。

## 一句话

给**超图(Hypergraph)GNN 脑病分类(ASD/AD)**建一套靠谱的**解释忠实度评测协议 + leaderboard**：系统比较超边权重 / GNNExplainer / Grad-CAM-for-graph 三类解释的忠实度(deletion/insertion fidelity)与已知脑网络(DMN)对齐，并修复现有超图 explainer 的 fidelity 指标缺陷。

## 核心 RQ

超图 GNN 因高阶连接被用于脑连接组分类，但它的「解释」(超边权重 / 后验 explainer / 梯度热图)**哪种最忠实、是否对齐神经科学先验**，无人系统评测——且 arXiv 2410.07764 已指出现有 hypergraph explainer 的 **fidelity 指标本身有缺陷**。本文：在同一忠实度公理(扰动后预测变化)下，给超图 XAI 建可比评测协议 + 脑病 leaderboard。

## 立项证据（G5 地基核查全绿）

- **数据** 🟢：ABIDE I/II 预处理版**免登录 S3 直下**（preprocessed-connectomes-project.org），含 cc200/aal/schaefer 连接矩阵，n≈1100。
- **baseline** 🟢：BrainGB(217⭐, ABIDE 内置多 GNN baseline)/BrainGNN(211⭐)/HyperGALE(超图, 16⭐, ABIDE-II+Schaefer400)。
- **指标** 🟢：PyG `torch_geometric.explain.metric.fidelity`(内置 fid+/fid-) + GraphFramEx(ICLR24) + nilearn Schaefer(自带 DMN 网络标签)。
- **撞车** 🟡 有角度：SHypX(2410.07764)是通用超图 explainer 非脑病应用、无 DMN 对齐；贡献点须落在「脑病应用层 + 超图 fidelity 修复」非「超图解释方法本身」。

## 命门 / 最大风险（动手前必解）

**超边(结构化解释)与 Grad-CAM(像素/节点热图)不在同一空间**——直接比忠实度=「苹果比橙子」。本文核心贡献 = 设计「同一忠实度公理(扰动后预测变化)下两种解释各自得分」的**可比协议**。引言须讲透「为什么超图解释比普通 GNN 更难评」。
- 工程坎：PyG 不原生支持超图，超图 fidelity 需把超图展平成二部图或桥接 HGNN 库（~3-5 天，正是贡献点不是阻碍）。

## venue

- top：**ACCV 2026**（Biomedical Image Analysis track；截稿 2026-07-05 大阪；CCF-C/CORE-B，录取~32%）
- fallback：MICCAI 2026 workshop (Brain Connectivity) / BSPC / Computerized Medical Imaging

## 数据

| 数据集 | 角色 | 状态 |
|---|---|---|
| ABIDE I/II (preprocessed) | ASD 功能连接组主战场 | 免登录 S3 直下（见 DATA_INVENTORY）|
| ADNI | AD 第二验证集(可选) | 需申请(2-4周)，非首选 |

## compute

~8 GPU·h（XJTLU HPC gpu4090 单卡；超图 GNN 训练轻量 + fidelity 多为推理/扰动）。

## 读档顺序

`00_README.md`（本文）→ `01_STORY.md` → `02_ACCEPTANCE.md`（含书面 kill criteria）→ `DATA_INVENTORY.md` → `04_LOG.md` 最新 entry。

## 文件导航

| 路径 | 内容 |
|---|---|
| `01_STORY.md` | 核心 Claim + 章节弧 + 与组合台边界 + 防御写法 R-rules |
| `02_ACCEPTANCE.md` | 二元 PASS/FAIL 验收 + kill criteria |
| `04_LOG.md` | 进度留痕（首条=立项决策）|
| `DATA_INVENTORY.md` | 数据细目（真源 .portfolio/datasets.json）|
| `src/` `tests/` | 实验代码 + pytest（待建）|
| `figures/` | 独立图表目录（待建）|
