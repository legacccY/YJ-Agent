# QuantImmuBench 工具补跑 · 大编队多窗协作计划（统一作战令）

> 建 2026-06-30 主窗。**所有窗口开工先读本文 + `TOOL_RERUN_STATUS.md`（工具状态真源）+ `03_EXPERIMENT_PLAN.md`（Phase 0 协议）。**
> 目标：30 工具在新官方 RCC 数据 43 补跑肽（29 缺失 + 14 P104）上重跑出分 → 合并 `merged_30_official` → 解锁 R1-R9 分析。
> 这是**大编队作战**：5 个干活窗 + 1 主窗，每窗内还可再派 3-5 个 agent 扇出（coder/researcher）。

---

## 0. 统一铁律（每窗每步强制，违反即停）

1. **不堵塞**：任何步「要么 HPC 要么本机」立即跑，绝不空等。HPC 排队就本机能跑的先跑，本机环境缺就 HPC。主线不 sleep 守长任务（甩后台/非阻塞瞥）。
2. **不许降级**：遇缺口/阻塞先攻坚补满（上网查、换实现、修 env），**不预设退守话术**。诚实降级只在路全堵死 + 主窗拍板时。某工具某等位工具真不支持 → 诚实 NaN（不是降级，是工具边界，写明）。
3. **上网查资料**：遇坑第一动作上网查——GitHub/Kaggle 高星实现 + 官方源码 + issue + Stack Overflow，对照再动手，绝不臆造。查到的记 LOG，查不到标 TODO。
4. **不许改原数据**：`data/OFFICIAL_DO_NOT_TOUCH/` + 任何原始数据**只读**，禁改禁覆盖。所有派生写 `scripts/out_official/` 或 `data/frozen/`。
5. **复现零偏离**：完全按工具官方跑，禁私改超参/裁剪/换实现凑结果。
6. **数字必核**：覆盖率/分数一律 Bash 核 csv，不信 parse 自报（已抓肽级兜底造数 bug，见下）。
7. **认领隔离**：开工先 `echo "<window> claim <slice> $(date)" > .portfolio/locks/quantimmu-tools-<slice>.claim`，避免两窗撞同工具。

---

## 1. 已固化通用 pattern（照搬，省每窗重踩）

- **输入就位**：HPC `/gpfs/work/bio/jiayu2403/quantimmu/official_inputs/out_official/`（已上传 MT+WT）。通用喂料 `newtools/uniq_pep_hla.csv`(1462) / `universe.csv`(1761) / `uniq_pep.csv`(462,HLA-agnostic)；各工具专用输入见 `out_official/`。
- **HPC 连接**：`dtn.hpc.xjtlu.edu.cn` / `jiayu2403`（校内直连无需 VPN）。root=`/gpfs/work/bio/jiayu2403/quantimmu`。工具 repo 多在 `tools_repos/`，DTU 二进制 `ext_tools/`，sif `sif/`，conda envs `envs/`。
- **conda 激活**（paramiko 非交互 shell 必须）：`module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta && source $(conda info --base)/etc/profile.d/conda.sh && conda activate envs/<tool>`。
- **相对路径工具要 `cd` 进 repo**（ImmuneApp 的 supporting_file 踩坑）。
- **paramiko 后台启**：`setsid bash X </dev/null >log 2>&1 &`（防 channel fd 阻塞卡死）。
- **MixMHCpred** 在 `tools_repos/MixMHCpred/MixMHCpred`。
- **🔴 parse 必精确 (肽, 输出目录等位) 匹配，缺→NaN，禁肽级兜底**（merge_prime 兜底误填别等位分=造数，已修，见 `parse_prime_immuneapp_official.py` strict 版为范本）。
- HPC 提交/上传新数据/代码、危险删除、训练启停 = **各窗主线串行**，agent 不碰；GPU 走 `tools/gpu_slot.py` 申卡绝不挤正在跑的。

---

## 2. 窗口编制（大编队，按工具族切，各窗认领一 slice）

| 窗 | slice | 工具（认领文件名）| 跑哪 | 备注 |
|---|---|---|---|---|
| **W0 主窗** | orchestrator | 不认领干活节点 | — | 见 §4 主窗职责 |
| **W1** | dtu | netMHCpan_BA★ / netMHCpan_EL / netMHCstabpan / NetTepi / TSCAPE / ICERFIRE | HPC | DTU 二进制(ext_tools)+qib envs；netMHCpan_BA=headline 主角优先；5 个 pending consent 照跑标注 |
| **W2** | presml | MHCflurry / MHCnuggets / MHCseqNet / TransHLA / HLAthena | HPC(+本机可跑的) | ML 呈递；MHCflurry pip 可本机试；TransHLA GPU；HLAthena sif |
| **W3** | immml | BigMHC_IM / CNNeo / MUNIS / DeepNetBim / DeepImmuno / andy90 / ImmuGenX / NeoaG | HPC(+本机) | torch/ML 免疫原 8 个；输入多用 universe/uniq_pep_hla |
| **W4** | immbox | PredIG / pTuneos / IMPROVE / NeoTImmuML / deepHLApan / Repitope | HPC(+本机WSL) | 容器/复杂：sif(predig/ptuneos) + R(NeoTImmuML 78特征/Repitope) + deepHLApan(WSL docker 或 HPC) |
| **W5** | finish | PRIME 补 12 等位 + NeoaPred | HPC | PRIME MixMHCpred 等位坑深挖(查官方/issue,不支持就诚实NaN)；NeoaPred GPU 走 gpu_slot 单卡 |

★ 已 done 不在表：IEDB_Calis(本地✅)、ImmuneApp(HPC✅)。PRIME 13/26 在 W5 收尾。

---

## 3. 每窗统一验收标准 + 严格完工界限（DoD）

**每个工具的 DoD（缺一不可）**：
1. 产出 `scripts/out_official/<Tool>_official.csv`（列 `bb_idx, MT_<Tool>[, WT_<Tool>]`），1761 行对齐 backbone。
2. **Bash 核覆盖**（不信脚本自报）：`43 补跑肽`各有 ≥1 等位的 MT 分；打印实际 distinct 等位覆盖数 + MT 非空行数。
3. **诚实 NaN**：工具真不支持的等位/肽长 → NaN 并在该工具 NOTES 写明原因（查官方确认，非偷懒）；**绝不**用别等位分回填（精确匹配）。
4. 跑法脚本入 `scripts/hpc_official/run_<tool>_official.*` + parse；HPC 输出拉回本地。
5. 该工具在 `TOOL_RERUN_STATUS.md` 行翻 ✅ + 一句话记 env/坑/覆盖数。

**窗口 DoD**：本窗 slice 全工具达上述 → 在 `.portfolio/locks/quantimmu-tools-<slice>.claim` 写 DONE + 通知主窗。**到此停，不冲下一棒、不碰别窗工具**。

**验收红线**：主窗合并前对每工具 Bash 抽核 ≥2 个 (肽,等位) 分数确属该工具该等位真输出（防再现造数）。

---

## 4. 主窗（W0 orchestrator）设计 —— 我现在这个窗

主窗**不认领具体工具**，只做编排/收口（每次开多窗都设一个）：
1. **派活**：把 §2 五个 slice 分发给 5 个干活窗（用户开终端，各窗读本文认领 slice）。
2. **维护真源**：`TOOL_RERUN_STATUS.md` 状态表 + 本计划，各窗回报即更新。
3. **不堵塞调度**：哪窗 HPC 排队→提醒先跑本机能跑的；GPU 冲突→`gpu_slot.py` 仲裁。
4. **收口合并**：各窗 DoD 后，主窗 Bash 抽核 → 合并所有 `<Tool>_official.csv` + 87 肽旧分 → `merged_all_tools_30_official.csv` → 跑 `p0e_pool_to_peptide.py`（pooling，round8+count混杂诊断）→ `p0f_freeze_provenance.py`（sha256 冻结）。
5. **集成烟测闸**：合并表跑 per-patient Spearman 试算，9 患者全非 NaN + 无 silent dropna → 放行。
6. **解锁分析**：地基冻结后开 R1-R9 + AB 消融（`03_EXPERIMENT_PLAN.md`）。
7. **拍板点**：DTU consent / 30 工具是否达标 / geomean headline / 偏离 STORY —— 停下报用户。

---

## 5. 自由发挥空间（明确授权）

各窗在统一铁律内**自由解决实现细节**：env 怎么修、哪个 GitHub 实现参考、本机还是 HPC、要不要再派 coder/researcher 扇出、parse 怎么写——窗口自决，不必逐步问主窗。只在「真拍板点 / 撞别窗 / 路全堵死要降级」时找主窗。鼓励每窗内大编队扇出（researcher 查工具坑 + coder 写 runner + verifier 核覆盖）。

---

## 6. 终点

30 工具 official csv 全齐（或诚实 N + 缺口写明）→ `merged_30_official` → p0e/p0f 冻结 → 集成烟测过 → 解锁 R1-R9 一次跑出 paper-ready 数据（run-once 零返工）。
