# /ideate — 选题工业流水线编排（立项前置）

一条命令把「拍脑袋定大胆方向」改成「批量产 100 候选 → 漏斗逐级筛杀 → 立项前廉价证伪 → 才立项」。主线当 lead 按 G0→G6 跑。

用法：`/ideate "<方向种子 / 宪章要点>"`（种子可空=全开放挖）。

体系全档：`project/ideation/00_README.md`（病因+总图+三支柱）。量规 `02_RUBRICS.md`，逐闸 `03_GATES.md`，池 schema `04_POOL.schema.md`。

## 流程（我当 lead 执行）

**G0 宪章**（人主导）：据种子草拟 `project/ideation/runs/<date>_charter.md`（复制 `01_CHARTER.template.md`）→ AskUserQuestion 让用户过目/改硬排除/算力预算/双venue/风险配比 → 锁定。

**G1 批量产出**（自主）：起 **ideator(sonnet)×8**，按 **B 族倾斜配额**（S3×2 + S4×2 + S1/S2/S5/S6 各×1；B 族实证命中率高，A 族须填 mechanism_anchor），每个产 15-20 条 → 合并 → SPECTER2 余弦 0.8 去重 + 多样性聚类 → 落 `runs/<date>_pool.jsonl`（~50 唯一）。工具未实现前去重可降级人工判。

**G2 机器硬筛**（自主）：撞车检测（`tools/ideation_collision.py`，未实现则 researcher 网页版逐条查 top 候选）+ R1 二元 kill checklist → ~20 存活，砍的记 reason + 最近邻论文。

**G3 评分排序**（自主）：researcher 补情报 → R2 InnoEval 加权（硬阈 Feas<4/Q-Nov<4 砍）→ R3 Swiss pairwise → **R8 顶会天花板打分定 `ceiling_tier`（MAIN/FINDINGS/WORKSHOP，低 tier 不砍只标档）+ 保底 ≥1-2 个 MAIN-tier 苗子晋级（标 high_variance，防被 benchmark 题埋）** → top10 跑 R4 → 8-10 排名。**主线/用户 final rerank 否决权**。

**G4 红队预演**（自主）：skeptic(opus) 对 top 8-10 → R5 Heilmeier + 攻三死法 + R6 pre-mortem + **上风险红队（「全成了天花板到哪」，校准 R8 信号有无注水，低 tier 降级非砍）** → 提炼最大风险假设 + G5 草案 → ~5 存活（保 ≥1 MAIN-tier 进 G5；无出路🔴致命即砍/回G1）。

**G5 杀手锏预实验** 🛑（拍板点）：planner 落 <1 GPU·h run（**预声明功效 MDE + continuous metric**）→ 主线 `gpu_slot.py request` 申卡槽跑 → verifier 核 csv + **R9 三分流**：KILL（CI窄+continuous→砍）/ GRAY（CI宽/binary→欠功效不砍带债）/ KILL-proxy → 2-3 存活。

**G6 立项拍板** 🛑（拍板点）：幸存出完整立项卡（**双venue 顶档由 ceiling_tier 钉死不虚标** + 全分数轨迹含 Ceiling + kill-shot verdict + 红队残差 + R7 书面 kill criteria）→ **有 MAIN-tier 苗子显式点「这是顶会赌注」与稳票分开呈** → AskUserQuestion → 拍板走 `/spin-off-paper`。

## 落档
一轮结束写 `runs/<date>_选题报告.md`：漏斗各级数字 + 幸存立项卡 + 被砍 top 原因聚类。pool.jsonl 砍掉的不删（negative pool 复盘资产）。

## 红线
- 全程纯软活到 G5 前；**G5 跑训练是拍板点**（经 gpu_slot.py，绝不挤正在跑的）。**G6 立项是用户决策**，不替用户拍。
- 杀哪个历史死法每闸都标了（见 03_GATES）：①立项乐观无对手→G4前移 ②理论先行→G5强制证伪 ③蓝海塌→G2工具撞车+可行硬闸 ④顶会执念→双venue强制 ⑤只量下风险塌成benchmark厂→R8天花板维度+MAIN保底+G4上风险红队；R9 kill-shot三分流防误杀顶会苗子。
- **双向平衡（别矫枉过正）**：天花板信号必须举证（R8 举不出=0，防 LLM novelty 自评虚高泡沫 [Si et al.]）；GRAY 欠功效不砍但干净 KILL 照杀——既不退回大胆全死，也不塌成安全题。
- ideator 喂 no-hallucinate（why_new 写差异化角度不写"没人做"）；可行性诚实标，别自我审查到只剩 1 个安全选题。
- 数字/撞车阈一律工具/Bash 核，不信自报。

## 节流
G1 的 ideator 并行扇出（6 策略可同发）+ 紧凑冷启 + caveman 压缩回汇；读重活在 sonnet 侧。G3-G4 单棒串行（依赖前棒输出）。
