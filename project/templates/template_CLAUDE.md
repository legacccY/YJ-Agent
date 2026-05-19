# {PROJECT_NAME} — Claude 行为准则

## 项目标识
- Project: {PROJECT_NAME}
- Phase: {N}/{TOTAL} — {阶段名}
- Venue: {目标会议/期刊} | Deadline: {YYYY-MM-DD}

## 关键文件指针
- OVERVIEW:    ./OVERVIEW.md
- Active Plan: ./plans/phase_{N}_active.md
- State File:  ./experiments/state.json
- Registry:    ./experiments/registry.json
- Figures:     ./scripts/gen_figures.py
- Worklog:     ./WORKLOG.md

## Windows 训练规范（不可省略）
- DataLoader: multiprocessing_context='spawn'（不能用 fork）
- 路径: 用 Path() 或正斜杠 /，不用 \
- 后台启动: Start-Process powershell，不用 Bash run_in_background
- GPU 互斥: 启动前读 state.json，status=running 时拒绝启动
- 绝不同时运行两个训练任务

## Skills 触发规范
- 训练实验: `/loop /run-experiment <script> <config>`
- 图表验证: `/validate-figures` 生成图后运行
- 阶段切换: `/phase-transition` 完成当前阶段时运行
- 子论文剥离: `/spin-off-paper` 从主项目拆独立投稿时运行
- 投稿前检查: `/pre-submit-check` 提交前运行

## 对话规范
- 中文对话，中英混排加半形空格
- 启动时 read OVERVIEW.md，一句话说状态，问"今天做什么"
- 收工时更新 WORKLOG.md 并 git commit
