# /gh-flow — GitHub 发布/拉取/维护一键编排

一条命令调起 GitHub 全流程标准化作业：把本地子项目规范化推上 GitHub、从 GitHub 拉优质代码进来、维护已发布 repo（按 issue/PR review 意见定位修 bug）。隐私门=软提醒（列风险后主线拍板），对外推送=主线串行拍板。

用法：
- `/gh-flow publish <路径>` — 发本地子项目成新公开 repo（如 `/gh-flow publish apps/hpc-companion`）
- `/gh-flow pull <repo-url> [目标位置]` — 从 GitHub 拉代码进来 + 许可证合规
- `/gh-flow maintain <owner/repo>` — 拉 issue/PR review 意见 + 分诊修 bug
- 无参 → 问用户要做哪种 + 目标

## 我当 lead 执行

### publish 流程
1. **派 gh-publisher(sonnet) 模式 A**：给目标路径 + 「软提醒隐私门」+ drift 契约（独立工具，与 private YJ-Agent 隔离）。它跑隐私扫描 + 比对顶级开源骨架 + 生成 README/LICENSE/CI/.gitignore/CONTRIBUTING/.github 模板，回报告。
2. **收报告 → 隐私拍板**：
   - 有 🔴 阻断级（密钥/凭证）→ **停下**，AskUserQuestion 让用户确认怎么处理（删/占位/env 化），处理完才继续。
   - 🟠🟡🔵 风险 → 一句话列给用户，软提醒，用户拍板放不放行。
3. **LICENSE / 可见性拍板**：repo public/private？LICENSE 选型（默认建议 MIT）？AskUserQuestion 或用户已指定则用。
4. **🛑 对外发布拍板点**（CLAUDE.md 拍板点 #3）：放行后**主线串行**执行——`gh repo create` → `git init`/独立仓初始化（**不与主仓 YJ-Agent 历史纠缠**，子项目单独成仓或 subtree split）→ `git add`/`commit`/`push`。一步步来，每步回报。
5. 落档：在 `apps/<tool>/README` 或对应索引登 repo 地址；必要时记 memory。

### pull 流程
1. **派 gh-publisher(sonnet) 模式 B**：给 repo-url + 目标位置。它查 LICENSE 兼容性 + `clone --depth 1` + 扫可疑代码 + 给集成建议。
2. **许可证拍板**：GPL 传染/不兼容 → 报告 + 等用户拍是否仍并入。
3. 集成落地：小的主线接；大的派 coder 适配依赖/路径/命名。

### maintain 流程
1. **派 gh-publisher(sonnet) 模式 C**：给 `owner/repo`。它 `gh issue list`/`gh pr list` 拉意见 + 三类分诊 + bug 定位到 file:line + 小修直接改自测。
2. **修复落地**：<30 行明确 bug gh-publisher 直接改；大改派 coder。
3. **🛑 对外动作拍板**：回复 issue / push 修复 / 合 PR → 主线拍板后串行做，gh-publisher 不碰。

## 红线
- **对外推送全是主线串行拍板**（gh repo create / push / pr create / 回 issue）——agent 只准备不推。
- **隐私**：publish 必先扫；🔴 密钥级阻断等用户处理；其余软提醒列清单。
- **隔离**：公开的独立工具 repo 不夹带 YJ-Agent 科研内容（双盲护栏 + private 组合台隔离）。
- **不污染主仓 git 历史**：子项目成独立仓（单独 init 或 `git subtree split`），不把整个 YJ-Agent 推公开。
- 删/改名走 Filesystem MCP，不 `rm` / 不 PowerShell-via-Bash。

## 节流
gh-publisher 是 sonnet，读重活（扫文件/查骨架/拉 issue）在它侧，省主线 context。报告 caveman 压缩回汇，生成的文档正文 caveman OFF。
