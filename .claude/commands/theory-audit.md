---
name: theory-audit
description: 一键起理论支撑推理器——三层防线推导/验证项目背后的理论与数据支撑。Layer1 theorist 半形式化推导(逐步假设+置信+来源)→ Layer2 skeptic 独立证伪(CoVe 式生成验证问题逐条反驳，命门可多路投票)→ Layer3 verifier 核 csv 数字。三 mode：kickoff(立项证可行性+预测回报)/diagnose(失败从理论侧三分流归因)/selfcheck(推导自检反幻觉)。用于「理论推导/理论支撑/证明这个/为什么该 work/可行性论证/这个推导对不对/失败了从理论上推错因」。
---

# /theory-audit — 理论支撑推理器（三层防线）

调起 `theorist`(opus) 做半形式化理论推导，再用 `skeptic`(opus)+`verifier`(opus) 三层防线防幻觉推导。可在项目**任何阶段**调用。

用法：`/theory-audit <project> [kickoff|diagnose|selfcheck] [claim/现象]`。
- 无 project → 用本窗口认领项目（`.portfolio/locks/*.claim`）。
- 无 mode → 按当前阶段自动选：planning/立项前 → `kickoff`；实验没达预期/失败 → `diagnose`；已有推导要复查 → `selfcheck`。

## 流程（主线当 lead，三层防线 = 核心命门）

1. **认窗 + 读档**：确认本窗项目；**读 `.portfolio/registry.json` 取该项目 `home/story/acceptance/log`**（各项目入口命名不同，以 registry 为真源不硬猜）；存在 `<home>/reference/THEORY_LEDGER.md` 或 `THEORY_FOUNDATION.md` 则一并给下游。

2. **Layer 1 — 推导**：派 `theorist`（`subagent_type: theorist`）。冷启动给：项目 home + mode + 要推的 claim/现象 + registry 取的 story/acceptance 路径 + 已有 ledger/理论文档 + drift 契约。收：逐步推导链（每步 `[假设]→[步骤]→[结论][置信][来源]`）+ 对应 mode 产物（四栏 chain / 三分流归因 / 修改单）+ 结论分档 + 命门定理。

3. **Layer 2 — 独立证伪**：派 `skeptic`（`subagent_type: skeptic`，**全新 context，不喂 theorist 的自评置信**，只给推导结论让它攻），任务 = 对 theorist 每步**生成验证问题、逐条试反驳**（CoVe 式）：哪步跳步？哪个假设其实不成立？哪条「定理」其实是 `待跑`？severity 分级（🔴致命/🟠值得改/🟢残差）。
   - **命门 claim（kickoff 的承重 claim / diagnose 的主归因）→ 多路投票**：再派 1-2 个 `theorist` 独立重推同一 claim（不看前一个结果，self-consistency），多数路径结论不一致 → 标红，该 claim 降级为「未坐实，需更强推导或实证」。

4. **Layer 3 — 核数**：theorist/推导引用了任何 csv 实测数字 → 派 `verifier`（`subagent_type: verifier`）Bash/Grep 核源（**禁 Read 看数据**），三方对账 registry↔ledger↔推导。无引用数字则跳过。

5. **落盘 + 拍板**：结果写进 `<home>/reference/THEORY_LEDGER.md`——
   - `kickoff`：建/更新 §2 假设链冻结表 + §3 命门定理 + §4 回报预测。**假设链出实证前写死，禁跑完调**（防 HARKing）。
   - `diagnose`：§5 诊断归因日志追加一条 entry（三分流结论 + 判别实验）。
   - `selfcheck`：§6 自检修改单追加（哪步病、已修）。
   无 ledger → 用 `project/templates/THEORY_LEDGER.md` 起一份。
   **命门塌缩**（承重 claim 被证伪 / 回报预测说不该 work / 主归因=假设错）→ **停下报拍板**（偏离 STORY、改 ACCEPTANCE 阈值、命门回退方向都是拍板点），写诚实结论，**不自行改判据 / 不粉饰 / 不 HARKing**。

## 红线
- `theorist` 只推导不写码不跑实验；推导引的数必过 `verifier`；文献/事实空白标 TODO 绝不臆想（[[feedback_no_hallucinate_settings]] [[feedback_research_before_design]]）。
- 三层独立：skeptic 拿全新 context 攻，不被 theorist 自评带偏。
- 结论分档诚实：`待跑` 不许卖成 `定理`（NCA-JEPA 100× 栽点）。
- 与 STORY/ACCEPTANCE 冲突、命门塌缩 → 停报拍板，不照描述硬干，写诚实回退（[[feedback_ask_on_unplanned]]）。
