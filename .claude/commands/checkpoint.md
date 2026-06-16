# checkpoint

阶段性进度落档（轻量，非收工、非 gate）。把本轮做的事写进项目 LOG，让文档进度跟上工作，防 context 压缩后断链。

## 触发场景

用户说"记一下进度"、"checkpoint"、"存个档"，或 stage_progress hook 提示"改了 N 个文件没写 LOG"后。
用法：`/checkpoint [project]`，未给则用本窗 `.portfolio/locks/*.claim` 推断。

## 执行步骤

1. 读 `.portfolio/registry.json` 拿该 project 的 `log` 路径。
2. 读 LOG 最新 entry，确认会话编号 + 上次"待续"。
3. `git -C <root> status --porcelain` + `git diff --stat` 看本轮实际改了什么（**以 git 为准，不靠记忆**）。
4. 在 LOG **顶部**（时间倒序）插一条 entry，沿用该项目既有格式：
   - 标题 `## YYYY-MM-DD（会话 N，<一句话摘要>）`（日期先 `date` 确认北京时间）。
   - 完成 / 关键产物（带路径）/ 待续。
   - 若本阶段有命中率相关变动 → 写诚实记录（PASS/FAIL/回退 N%），不粉饰。
5. 新产生的重要文件未登指针 → 顺手在 README / registry 补；用到的数据集路径未入 `.portfolio/datasets.json` → 补。
6. 一句话报：写了哪条 entry、补了哪些指针。

## 注意事项

- 只追加 LOG，不动代码、不跑实验、不 commit（commit 走收工流程）。
- 数字若要写进 entry 先 Bash/Grep 核 csv，不信 Read。
- 与 `/stage-gate` 区别：checkpoint 只记录不审；大阶段达标判定走 stage-gate。
