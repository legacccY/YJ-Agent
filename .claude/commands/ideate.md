# /ideate — 选题工业流水线编排（立项前置）

一条命令把「拍脑袋定大胆方向」改成「批量产 100 候选 → 漏斗逐级筛杀 → 立项前廉价证伪 → 才立项」。主线当 lead 按 G0→G6 跑。

用法：`/ideate "<方向种子 / 宪章要点>"`（种子可空=全开放挖）。

体系全档：`project/ideation/00_README.md`（病因+总图+三支柱）。量规 `02_RUBRICS.md`，逐闸 `03_GATES.md`，池 schema `04_POOL.schema.md`。

## 流程（我当 lead 执行）

**G0 宪章**（人主导）：据种子草拟 `project/ideation/runs/<date>_charter.md`（复制 `01_CHARTER.template.md`）→ AskUserQuestion 让用户过目/改硬排除/算力预算/双venue/风险配比 → 锁定。

**G1 批量产出**（自主）：起 **ideator(sonnet)×N**（每个领一种正交策略 S1-S6），每个产 15-20 条 → 合并 → SPECTER2 余弦 0.8 去重 + 多样性聚类 → 落 `runs/<date>_pool.jsonl`（~50 唯一）。工具未实现前去重可降级人工判。

**G2 机器硬筛**（自主）：撞车检测（`tools/ideation_collision.py`，未实现则 researcher 网页版逐条查 top 候选）+ R1 二元 kill checklist → ~20 存活，砍的记 reason + 最近邻论文。

**G3 评分排序**（自主）：researcher 补情报 → R2 InnoEval 加权（硬阈 Feasibility<4/Novelty<5 砍）→ R3 Swiss pairwise → top10 跑 R4 12维taste → 8-10 排名。**主线/用户对 top 有 final rerank 否决权**（别全自动）。

**G4 红队预演**（自主）：skeptic(opus) 对 top 8-10 → R5 Heilmeier 8问 + 攻三死法 + R6 pre-mortem → 提炼最大风险假设 + G5 实验设计草案 → ~5 存活（无出路🔴致命即砍/回G1）。

**G5 杀手锏预实验** 🛑（拍板点）：planner 把证伪草案落成 <1 GPU·h run → 主线 `gpu_slot.py request` 申卡槽（有空卡即起，一行回报）跑 → verifier 核 csv → 核心 claim 没死的 2-3 个存活。

**G6 立项拍板** 🛑（拍板点）：幸存出完整立项卡（双venue + 全分数轨迹 + 红队残差 + 杀手锏读数 + R7 书面 kill criteria）→ 一句话推荐 + AskUserQuestion 呈用户 → 拍板的走 `/spin-off-paper`（建 schema + 登 registry + 关联 datasets + claim + 首条 LOG 含选题轨迹）。

## 落档
一轮结束写 `runs/<date>_选题报告.md`：漏斗各级数字 + 幸存立项卡 + 被砍 top 原因聚类。pool.jsonl 砍掉的不删（negative pool 复盘资产）。

## 红线
- 全程纯软活到 G5 前；**G5 跑训练是拍板点**（经 gpu_slot.py，绝不挤正在跑的）。**G6 立项是用户决策**，不替用户拍。
- 杀哪个历史死法每闸都标了（见 03_GATES）：①立项乐观无对手→G4前移 ②理论先行→G5强制证伪 ③蓝海塌→G2工具撞车+可行硬闸 ④顶会执念→双venue强制。
- ideator 喂 no-hallucinate（why_new 写差异化角度不写"没人做"）；可行性诚实标，别自我审查到只剩 1 个安全选题。
- 数字/撞车阈一律工具/Bash 核，不信自报。

## 节流
G1 的 ideator 并行扇出（6 策略可同发）+ 紧凑冷启 + caveman 压缩回汇；读重活在 sonnet 侧。G3-G4 单棒串行（依赖前棒输出）。
