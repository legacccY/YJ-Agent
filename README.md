# YJ-Agent — 仓库总指针

legacccy（余嘉）的 LifeOS 工作仓库。本文件是**唯一总入口**，告诉你每样东西在哪。

> 找文件先看这里。各子项目有自己的日志/读档文件，别在 root 翻。

---

## 📁 目录地图

| 目录 | 是什么 | 入口文件 |
|---|---|---|
| **`project/`** | 🎯 ICLR 2027 主项目（VisiSkin-Agent）+ Med-NCA 子项目 | `project/README.md` |
| **`huimai/`** | 慧脉医疗 AI 平台（商业计划 + 技术调研，独立项目） | `huimai/产出/` |
| **`homework/`** | 西交利物浦课程作业（BIO113 / INT102 / PHY） | — |
| **`tools/`** | HPC 监控 / 提交 / 路径修复脚本 | `project/HPC_WORKFLOW.md` |
| **`archive/`** | 废弃残渣（旧稿 / 调试脚本 / 旧 demo），不再用 | — |
| `checkpoints/` `data/` `log/` `wandb/` `tests/` `_mednca_repo/` | 运行时产物 / 数据 / 参考 repo（多数 gitignore） | — |

## 📌 配置 / 指针文件（root 只留这些）

| 文件 | 用途 |
|---|---|
| `CLAUDE.md` | Claude 行为准则（身份 / 工具纪律 / 读档流程） |
| `WORKLOG.md` | ICLR 主项目快速状态指针（一句话进度 + 下一步） |
| `README.md` | 本文件（仓库总地图） |
| `skills-lock.json` | skills marketplace 锁文件 |

---

## 🚀 各项目从哪开始

- **ICLR 2027（主线）** → 读 `project/README.md`，再按它指的 4 文件顺序读档。当前状态看 `WORKLOG.md`。
- **Med-NCA（顶会复现子项目）** → `project/meeting/Med-NCA/REPRO_PLAN.md` + `PROJECT_LOG.md`。
- **慧脉医疗** → `huimai/产出/`（商业计划书 + 各技术调研报告）。
- **HPC 训练 / 查进度** → `project/HPC_WORKFLOW.md`（凭证 + 目录 + tools/ 脚本用法）。

## 🗂️ archive/ 里有什么（仅供翻历史，勿复用）

- `archive/old_paper/` — root 旧 `paper/`（BMVC 时代 Stage1 25.55 dB 裁剪 bug 废稿，真 ICLR 论文在 `project/meeting/ICLR2027/`）
- `archive/debug_scraps/` — Med-NCA 调试残渣（`_hpc_*.py` / `_r2*.txt` / `_debug_*.py` / jobid 临时文件）
- `archive/old_launchers_demos/` — 旧训练 launcher（`run_*.ps1`）/ demo 图 / `biwi_reid.py` / `train_log.txt`
