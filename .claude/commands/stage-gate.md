# stage-gate

半天级大阶段工作收口时的**严格 opus 审核闸门**。对 ACCEPTANCE_CRITERIA 判 PASS/FAIL，不存在"基本完成"。不达标不放行。

## 触发场景

用户说"这阶段做完了"、"大阶段收官"、"过一下 gate"、"严审一下"、"stage-gate"，或 stage_progress / drift_guard hook 提示后。
用法：`/stage-gate <project>`（project ∈ registry.json 的 key：iclr / nca-jepa / …）。未给则用本窗 `.portfolio/locks/*.claim` 推断。

## 核心原则（强制，违反即本命令失败）

1. **二元判定**：每条验收阈值要么 PASS 要么 FAIL。禁"接近达标""大致 OK""基本完成"。
2. **opus 亲审**：reviewer agent 必须 opus（对抗审稿 + 反跑偏），不可降级 sonnet。
3. **数字先过 verifier**：任何被审的指标先 Bash/Grep 核 csv 原值，不信 Read、不信 LOG 转述。
4. **不护主**：发现没达标直接判 FAIL，写诚实回退，绝不为"让阶段过去"放水。

## 执行步骤

### Step 1：定位 + 读档（主线串行）

1. 读 `.portfolio/registry.json` 确认 project 的 `home` / `story` / `log`。
2. 读该项目 `ACCEPTANCE_CRITERIA.md`（ICLR）或对应 plan 的 Success Criteria（其他项目）。
3. 读该项目 LOG 最新若干 entry，列出"本阶段声称完成"的 lever / milestone / 实验清单。
4. 读 `.portfolio/datasets.json` 确认本阶段用到的数据集状态与声称一致（没拿 todo 数据集冒充 ready）。

### Step 2：派 verifier（sonnet）核数字 — 先于审

派 `verifier` agent，prompt 必带：
- 本阶段声称的每个关键数字 + 它在 LOG/tex 里的值 + 应在的 csv 路径。
- 要求：Bash/Grep 直核 csv 原值，三方对账（registry ↔ STORY/ACCEPTANCE ↔ tex/LOG），**禁 Read 看数据**。
- 返回逐条 `数字 | 声称值 | csv 实测 | 一致?`，任一 drift 标红。

verifier 报 drift → 本 gate 直接 FAIL，停，让主线先修数字。

### Step 3：派 reviewer（opus）严审 — 对抗 + 反跑偏

verifier 全绿后，派 `reviewer` agent（**opus，caveman OFF**），prompt 必带：
- 服务项目 § / 本阶段范围 / 不得碰的红线（BMVC 封印、复现零偏离、R1-R10 等）。
- 任务：对照 ACCEPTANCE 每条阈值，逐条判 **PASS / FAIL**，FAIL 给具体差距 + 命中率回退预估。
- 额外两轨：①对抗审稿（十角色找漏洞）②反跑偏审计（本阶段产出是否偏离项目 STORY）。
- 输出格式：
  ```
  ## Gate 判定：<project> 阶段 <名>
  | 验收条目 | 阈值 | 实测 | PASS/FAIL | 差距/回退 |
  总判：PASS（全条达标） / FAIL（列出阻断项）
  对抗审稿 top 漏洞：…
  跑偏审计：…
  ```

### Step 4：主线综合 + 落档

1. 汇总 verifier + reviewer 结论，给用户**一句话总判 + 阻断清单**。
2. **PASS**：在项目 LOG 写一条 gate-passed entry（日期、过的条目、reviewer top 意见留存）；如需进下一阶段提示 `/phase-transition`。
3. **FAIL**：在 LOG 写诚实回退（"命中率回退 N%" / 阻断项），**不放行**；列出修复 TODO。绝不粉饰。
4. 若产出新重要文件未登指针 / 数据集路径未入 datasets.json → 一并补。

## 注意事项

- 此 gate 是"严"的闸门，宁可判 FAIL 也不放水；用户可推翻判定但必须显式说。
- 主线只做编排 + 落档；核数字交 verifier、审交 reviewer（省主线 context）。
- 训练/HPC/危险删除不在本命令范围（主线另行串行）。
