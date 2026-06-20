---
name: conductor
description: 通用阶段编排器——Claude 自己当指挥，按依赖 DAG 自动推进单项目的多阶段工作：读当前 phase 建任务图→查就绪棒→派对应 agent 编队（独立棒并行扇出）→跑完自动解锁下一棒→到拍板点停下报。状态写 .portfolio/pipelines/<project>.json 抗 context 压缩，任何窗口 /conductor <project> 续跑。用于「自动把这篇推下去」「按阶段自动协调」「接着干」「continue」泛指令。比 /experiment-cycle 更通用（任意 DAG，可恢复，多波次并行）。
---

# /conductor — 通用阶段编排器（持久 DAG + 自动派编队 + 拍板点停）

把「单项目多阶段、有先后依赖、要 Claude 自己协调、同文件夹原地推进」固化成可恢复的引擎。
是 `/experiment-cycle`（固定 6 棒线性）的超集：任意 DAG、可并行扇出、跨窗恢复、到任意 gate 停。

**真源 = `.portfolio/pipelines/<project>.json`**（仿 gpu_slot/state.json，状态写文件不靠 context）。
引擎 = `python tools/pipeline.py`（头注有全命令）。**不手改 JSON，全走 CLI。**

用法：`/conductor <project> [paper|experiment|scout|writing]`。无 project → 用本窗认领项目。

## ⚖️ 先判值不值（别过度编排，否则纯亏效率）
建 DAG/拆窗本身有开销。**只有大活才上全套**：
- **上 conductor**：工作量 ≥ 半天 **且** 有 ≥2 个**真正独立可并行的块**（不同文件/不同 run）。
- **别上、直接内联干**：小活（<半天）、一条线顺序活、就改几个文件、急 bug。这种建图认领比干活还久。
- **集成烟测闸是例外，永远值**：哪怕单线，只要这轮有「多块拼起来跑」的集成动作，就保留 `integrate` 真烟测（几分钟本地，挡 HPC 半天崩）。
判据：拿不准 = 活够大够并行才编排，否则老实串着干。

## 主线驱动循环（你=lead，照此跑）

### 0. 认窗 + 读真源
- 认 `.portfolio/locks/<project>.claim`（没有则写）。
- **读 `.portfolio/registry.json` 取该项目 `home/story/acceptance/log/phase/status`**（各项目命名不同，以 registry 为准不硬猜）。
- 读项目 LOG 最新 entry，判当前卡在哪一棒。

### 1. 建图 / 续图（可恢复关键）
```
python tools/pipeline.py next <project>
```
- 报 `ERR 无 pipeline` → 按当前阶段选模板建：
  - 立项后要跑实验 → `init <project> -t experiment`
  - 整篇从调研到审稿 → `-t paper`；纯探路 → `-t scout`；纯写作冲刺 → `-t writing`
  - 阶段特殊 → `-t experiment` 后用 `add` 增删节点定制（依赖用 `--deps`，拍板棒加 `--gate`）。
- 已有图 → 直接续（这就是抗 context 压缩 / 跨窗恢复：新窗 `/conductor` 读图接着跑）。
- 建图后**镜像进原生任务表**（`TaskCreate` 每棒一条，标依赖），让用户 Ctrl+T 看进度。

### 2. 派单循环（核心，自动推进）
反复执行直到 gate 或全完成：
```
python tools/pipeline.py ready <project>
```
按输出分派：
- **`READY <id> agent=X`** → `start <project> <id>` 标记，派对应 agent（`.claude/agents/`），给紧凑冷启动上下文（**服务哪项目§/lever + 读 STORY/ACCEPTANCE + drift 契约 + 不得碰 X**）。agent 回来 → `done <project> <id> --out "结论/csv路径/指针"`（自动解锁下游，打印下一波）。
- **`PARALLEL[g] ...` 多条** → **一批多 agent 并行扇出**（同 group 无文件冲突）。全部回来再各自 `done`。同文件夹原地跑；万一某棒会改同一文件 → 派该 agent 时加 `isolation: worktree`（干完自动 merge，仍同 repo）。
- **`GATE <id>` (rc=10)** → 见下「拍板点」。
- **`WAIT 在跑`** → 别空等，推其他就绪棒 / 干主线关键路径。
- **`BLOCKED`** → 那棒 `block` 了（如 skeptic 抓致命伤/训练发散），读 `--out` 原因，回上游修（重置该棒 → `add` 修正棒或重派）或停报拍板。
- **`DONE` (rc=20)** → 全完成，写 LOG（`/checkpoint`），报总结 + 建议下一阶段。

### 3. 🛑 拍板点（gate 棒，停！）
`ready` 报 `GATE`（训练/HPC 上传/投稿/立项/改判据…）→ **停下一行报**：
```
[conductor] 到拍板点：<id> [<stage>] <desc>。<就绪要素>。说『放行/跑』即推进。
```
**训练那棒**（template 里 `train`，agent=主线）：放行后主线**亲自串行**——先 `gpu_slot.py request <project> <host> <gpus>`（GO 起 / QUEUED 排队），再 `/loop /run-experiment`，state.json 监控；跑完 `gpu_slot.py release` + `pipeline.py done <project> train --out "job/结果"` 解锁分析棒。
其余 gate 同理：放行 → 做 → `done` 推进。**绝不自行越过 gate。**

### 4. 收尾 + 🧹 清扫（每轮做完必清中间遗留）
全 done → `pipeline.py status` 出总览 → 写项目 LOG → 报达没达本阶段 ACCEPTANCE 判据 + 建议（进写作 / 下一轮实验 / `/stage-gate`）。
**然后清中间物（只清已知一次性产物，绝不碰真结果/代码）**：
- `pipeline.py rm <project>` → DAG 图归档到 `.archive/`（保留可追溯，不留活图挡下轮）。
- **集成烟测临时产出**（小跑的 npz/png/log）→ 统一写在 `_scratch/conductor_<project>/`（已 gitignore）→ 用 **Filesystem MCP `move_file` 改名存档或删**（不用 rm、不经 Bash 调 PowerShell，见工具纪律）。
- **保留**：`INTERFACE.md`（接口契约，下轮还用）、真实结果 csv/ckpt、项目 LOG。
- **红线**：清扫只动 `_scratch/` + 归档图；删真产物/代码是危险删除拍板点，停下问。
> 烟测/小跑的输出从一开始就写进 `_scratch/conductor_<project>/`，别撒在项目目录，省得收尾难分哪个是垃圾。

## 🔬 集成烟测闸（治「pytest 全绿但真跑暴露集成缝」）
paper/experiment 模板在 `train` 棒**前**自带 `integrate` 节点（agent=主线，非拍板 gate 但硬卡）：
- 依赖**所有 implement 块**，主线跑一次**真·端到端最小跑**（1 图 1 step 本地 <5min），专踩缝：数据格式（NPZ key/结构）/ 依赖（scipy 等装没装）/ 路径（硬编码 split、datasets.json）/ eval I/O（train 输出 vs eval 输入对不对）。
- **不是 pytest**——单测每块自绿，缝在块之间照不到。集成烟测真跑全链，把「真跑才暴露」从 HPC 半天提前到本地几分钟。
- 缝暴露 → `block integrate --reason "..."` + 回对应 implement 块 `reset` 重修；过了 → `done integrate` 解锁 train 拍板点。
- **绝不跳过 integrate 直接上 HPC**（这是 5 处跨窗集成缝的根治闸）。

## 🪟 一篇多窗并行（节点级认领，不是整篇互斥）
同一篇多窗一起干 = **各窗认领 DAG 的不同节点**（改不同文件，天然不撞），最后全汇到 `integrate` 真烟测：
1. **拆活**：把单个 `implement` 拆成并行块——`skip implement --reason 拆块` → `add impl-X --agent coder --deps design`（每块一个）→ `dep integrate --rm implement --add impl-X,impl-Y`（让集成闸等齐所有块，**别漏**）。
2. **各窗领块**：A 窗 `claim <project> impl-reid winA`、B 窗 `claim <project> impl-eval winB`。`ready --free` 看还剩哪些没人领，`mine <project> <win>` 看本窗领了啥。**已 running 且他窗认领的块不重做**。
3. **接口契约先行**（防缝根因）：开多窗前先在 `<home>/INTERFACE.md` 钉死块间接口（NPZ key schema / 依赖清单 / 路径走 datasets.json 不硬编码 / eval 输入格式），各窗照契约造，不各编各的。
4. **汇流**：各块 `done` → 释放认领 → 全齐后 `integrate` 解锁 → 主线跑集成烟测踩缝 → 过了进 train 拍板点。
> 仍守：train/HPC/投稿是 gate，主线串行；GPU 抢卡走 gpu_slot.py（多窗各占 1 卡绝不挤）。

## 与现有体系的关系
- **gpu_slot.py 正交**：pipeline 管「干哪棒、谁先谁后」，gpu_slot 管「训练有没有空卡」。train 棒走 gpu_slot。
- **registry.json 是项目级真源**（phase/status/路径）；pipeline 是**本阶段工作图**（细到每棒）。两者互补：阶段做完，把结论写回 registry.phase + LOG，可 `pipeline.py rm` 归档本图，下阶段 `init` 新图。
- **/experiment-cycle 仍可用**（想要固定线性中段时）；conductor 用于要 DAG/并行/恢复/自定义阶段时。

## 红线（贯穿）
- 训练启停/HPC 上传/投稿/危险删除 = gate，主线串行，绝不自动越过。
- 派出的 agent 守四红线（数字核 csv/超参查官方/复现零偏离/BMVC 封印）+ drift 契约。
- 任一棒发现偏离 STORY / 改判据方向 → `block` + 停报拍板，不照描述硬干。
- 节流：每 agent 紧凑冷启 + caveman 压缩回汇（planner/writer/reviewer/skeptic OFF）+ 读重活交 sonnet 省主线 context。
