# optimize

协作系统自优化。派 `optimizer` agent 读摩擦信号 + git log，聚类反复出现的问题，小的安全修复直接改，大的报你拍板。优化的是"我们怎么协作"，不碰论文内容/数据/实验。

## 触发场景

用户说"优化一下流程"、"自检"、"最近老踩同一个坑"、"/optimize"；或收工流程自动跑（friction.jsonl 有新条目时）。

## 执行步骤

1. **先看值不值得跑**（省 token）：`wc -l .portfolio/friction.jsonl`（不存在/0 条且本会话无明显重复纠正 → 直接报"系统健康"，不派 agent）。
2. 派 `optimizer` agent（sonnet + caveman，冷启动给：本会话主线注意到的反复纠正/坑），让它：
   - 聚类 `.portfolio/friction.jsonl`（≥2 次的）+ `git log --oneline -20` + 上下文摩擦。
   - 小+安全+高信心 → 直接改 `.claude/` / `CLAUDE.md` / `PROJECT_LIFECYCLE.md` / `.portfolio/` 规范文件（改 hook 后自跑 `node -c` 验）。
   - 大 / 改行为契约 / 动拍板边界 → 写提案，不改。
   - 处理完的 friction 事件归档到 `.portfolio/friction.archive.jsonl`。
3. **主线收口**：转述 agent 的「已修 / 待拍板提案 / 健康」。提案里属拍板点的（删规则、改拍板边界、大改契约）→ 停下等用户拍。

## 注意事项

- optimizer **只动流程/规范文件**，绝不碰论文 tex/正文/数据/训练 config/封印 BMVC（碰到即停报主线）。
- 减法优先：能删冗余/合并重复解决的不新增文件；系统越小越好。
- 不为凑工作量造改动；无 ≥2 次摩擦也无大坑 → 报健康即可。
- friction.jsonl 由 block 类 hook（redline / no-pointer / training-lock-block）自动追加，零模型 token。
