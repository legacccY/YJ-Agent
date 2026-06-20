# PHASE 1 — 数据 & 断点续连 benchmark（杀手锏，矩阵第一优先）

## ① 目标（锁定）
建成自造的「人工断点/遮挡 benchmark + 续连率/re-ID 率指标」，把「记忆能续连同根血管」从 overclaim 变成可量化的 headline 铁证。这是核心 1+核心 2 立得住的充要条件。

## ② 入口依赖
P0 PASS（方向成立）。5 主集已上 HPC（DRIVE/CHASE/FIVES/HRF/STARE）。

## ③ 任务清单
1. **数据补齐**：冠脉(XCAD/DCA1/CHUAC)、OCTA(OCTA-500/ROSE)、跨域(Crack500/Roads) 下载 + 许可证逐个确认 + 登记 `.portfolio/datasets.json`。
2. **断点合成协议**：对齐 creatis plug-and-play（arXiv 2404.10506）——半径分布 P(i)=2^(p-i)/(2^p-1) 抽样 + gap 参数 s∈{6,8,10,12}/σ；先 DRIVE/STARE，再推广。脚本放 `benchmark/`。
3. **续连指标实现**：ε_β0（连通分量误差比，直接用）+ SR（gap 闭合率，直接用）+ **re-ID 率**（同根血管匹配，自定义，借 MOT IDF1：正确同根 / 全部 gap）。
4. **工具库接入**：clDice / Betti-Matching-3D / Skeleton-Recall 三库（开源，见 DATA_INVENTORY）。

## ④ ACCEPTANCE 硬阈值（不妥协）
- [ ] 断点合成协议参数固定、可一键复现（同 seed 同断点）
- [ ] ε_β0 / SR / re-ID 率三指标实现 + 单测（合成 case 上数值正确）
- [ ] **防泄漏**：benchmark 测试集 held-out，零拼训练样本（grep/脚本断言）
- [ ] **记忆 key / re-ID 监督不碰 GT 拓扑**（self-supervised by reconstruction）
- [ ] 数据集 ≥10 集登记 datasets.json，许可证确认能学术发表

## ⑤ 自由发挥区
断点形态（随机 mask / 管腔遮挡 / 低对比衰减）、severity 分级粒度、re-ID 匹配公式细节、是否加真实病理断点子集。

## ⑥ 跑偏定义 / 红线
- ❌ 测试集拼训练样本 = in-sample 伪迹（红线1，参记忆 visiscore 喂错教训）
- ❌ re-ID / 记忆用 GT 监督（红线2，鸡生蛋+泄漏）
- ❌ 许可证未确认就纳入发表数据
- ❌ 重造 benchmark 轮子（合成算法对齐 creatis，别从零发明）

## ⑦ 退路 + 派谁 + 出口 gate
- 退路：边缘集（OCTA/冠脉/跨域）下载失败允许 1-2 集放弃（kill 放宽）；DCA1 CIMAT 曾 ECONNREFUSED → 换源或标 TODO 报用户。
- 派谁：数据下载/benchmark 脚本派 `coder`；HPC 上传新数据是拍板点（主线串行先报）。
- **出口 gate**：协议可复现 + 零泄漏 + 三指标实现 PASS → 进 P3（需 P2 模型就位）。
