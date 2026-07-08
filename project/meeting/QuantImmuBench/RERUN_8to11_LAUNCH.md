# 新窗口启动：QuantImmuBench 改动②③ 8-11mer 可变窗口径全量重跑

> 建 2026-07-08。给新窗口直接读的自包含启动指南。9mer 新切已完成（04_LOG Entry 57），本轮把新切口径从 9mer 扩到 8/9/10/11 四窗。

## 0. 先读档（强制，别跳）
本窗做 quantimmu-bench。开工先认领锁 `.portfolio/locks/quantimmu-bench-8to11.claim`，再按链读档：
- `project/meeting/QuantImmuBench/00_README.md`
- `04_LOG.md` 最新 **Entry 57**（含 9mer 新切全过程 + 8-11mer 工作量评估结论，重点读）
- `RERUN_LAUNCH_GUIDE.md`（工具→本地/HPC→env 映射表 §1/§2 + 收口流程 §3 + 不漏铁律 §4）
- `会前提纲_2026-07-07_新切肽口径.md`（改动②③口径定义）

数字一律 Bash/Grep 核 csv，不信 md/Read。复现零偏离（工具/权重/超参不改）。

## 1. 目标（一句话）
9mer 新切「原始蛋白定点切含突变窗」已完成（backbone 4053 行、102 SNV 肽、全 Window_Size=9）。本窗扩到 **8/9/10/11 四窗**，重跑受影响工具，出 8-11mer 单工具排名 + 与 9mer 对比。服务 §3.1 / §2.2（多长度敏感性）。

## 2. 三大堵点（前置化，防中途卡死）
1. **`cut_from_protein.py` 写固定路径** `data/frozen/newcut_{mt_wt_pairs,subpep_hla,conflicts}.NEW.csv`，跑 8-11 会**覆盖 9mer 版** → **第0步先备份**这 3 个 + `rerun_input_manifest.NEW.csv` + `scripts/out_rerun_official/master_backbone_official.csv` 到 `_archive/9mer_newcut_2026-07-08/`。8-11 所有产物走**独立命名**（`out_rerun_official_8to11/` 等），绝不覆盖 9mer。
2. **`scripts/diff_scored_universe.py` SCORED 路径硬编码**指向旧 SLP merged、无参数 → 增量复用 9mer 分需派 coder 加 `--scored` 指向 `scripts/out/merged_all_tools_30_rerun.csv`。
3. **对比出图脚本输入硬编码** → 派 coder 新写「新切9mer vs 新切8-11mer」对比图。

## 3. 执行步骤（单窗线性）
**第0步 备份**（主线，Filesystem MCP/cp）：见堵点①。

**第1步 切 8-11 肽**（🟢本地零改代码，秒级，主线）：
```
python scripts/cut_from_protein.py --window 8-11    # parse_window("8-11")→[8,9,10,11]，一次产四长
python scripts/build_rerun_inputs.py                 # 零改，读全量 newcut
```
核 manifest：8-11 窗数 ≈ 3860（102肽×8/9/10/11 减端截断），MT for_tools ≈ 17K 行。

**第2步 增量 diff**（派 coder 改 diff_scored_universe 加 `--scored` → 主线跑）：算出「只需新打分的 8/10/11 窗」（9mer 窗复用现有 `out_rerun_official` 分）。增量 ≈ 9mer 负载 3.2×。

**第3步 打分**（增量，MT 侧；WT 见 §6 决策）：
- 🟢**本地 15 工具**（slice_local_a/b，RERUN_LAUNCH_GUIDE §1 现成 env）：激活各 env 跑 8/10/11 窗 → parse 落 `scripts/out_rerun_official_8to11/<Tool>_official.csv`。
  - ⚠️ **wsl bash 命令必须前缀 `MSYS_NO_PATHCONV=1`**（否则 `/mnt/d/...` 被 Git Bash 转成 `D:/Git/mnt/...` 报 No such file — 9mer WT 补跑踩过）。
  - GPU 工具(TransHLA/TSCAPE)串行占本机 RTX4070，避开训练。
- 🛑🖥️**HPC 14 工具**（slice_hpc_dtu 6 + slice_hpc_env 8）：上传 8-11 输入到 `/gpfs/.../quantimmu/rerun8to11/` = **对外传输拍板点，停下报用户放行**后 sbatch，QOS 限用 `/loop` 轮询拉回 parse。
- **工具窗长支持**：**DeepNetBim 只 9mer**（8/10/11 标 NaN，对比图剔）；**DeepImmuno 只 9-10mer**（8/11 标 NaN）；其余 ~27 工具全支持。NeoaPred 已剔不跑。

**第4步 收口**（全参数化零改，主线）：
```
python scripts/merge_official_30.py --in-dir scripts/out_rerun_official_8to11 --out scripts/out/merged_all_tools_30_rerun_8to11.csv --pure-new --strict-roster
python analysis/phase0/p0e2_pool_clean.py --input scripts/out/merged_all_tools_30_rerun_8to11.csv --w811 --expect-peptides 102 --output data/frozen/pooled_clean_rerun_8to11mer.csv
python analysis/official/recompute_effN/recompute_R1_effN.py --input data/frozen/pooled_clean_rerun_8to11mer.csv --tag rerun_8to11mer
```
→ 产 `R1_recomputed_rerun_8to11mer_effN8.csv`（口径同 9mer：per-patient Spearman→effN≥8→clip±0.99→Fisher-Z 病人等权→tanh）。

**第5步 出图**（派 coder，主线跑+verifier 核）：新写 `plot_newcut_9mer_vs_8to11mer.py`：新切 9mer(`R1_recomputed_rerun_9mer_effN8.csv`) vs 新切 8-11mer(`R1_recomputed_rerun_8to11mer_effN8.csv`) 哑铃/条形对比。存 `figures/` + `paper/figures/`。

**第6步 核数+落档**：verifier 三方对账（csv↔图↔表）；写 04_LOG 新 entry。

## 4. 完整性铁律（不能漏数据，命门）
三重保险：① `merge --strict-roster` 硬闸（缺任一 roster 工具报错）② `python scripts/build_coverage_matrix.py` 逐(窗×HLA×side×工具)覆盖矩阵，每空缺格显式记原因（工具不支持长度/HLA=正常 vs 真漏=补）③ 每工具跑完自查无 unknown 再收。被排除的格子必显式记原因，**绝不静默丢**。多跑没关系，漏跑不行。

## 5. 拍板点（停下报用户）
- HPC 上传 8-11 新输入（对外传输）。
- 真实歧义无合理默认。
其余（本地跑、切肽、下游收口）自主推进。

## 6. 🔴 待用户确认的决策（开工前问一句）
**WT 侧跑不跑**：本 8-11 轮**默认只跑 MT**（够出单工具排名 + 与 9mer 对比，省一半算力/HPC）；若要 8-11 也算 DAI 需加跑 WT 侧（算力翻倍）。开工前跟用户确认 MT-only 还是 MT+WT。

## 7. 关键真源文件
- 9mer 已完成（复用其 9mer 分）：`R1_recomputed_rerun_9mer_effN8.csv`、`pooled_clean_rerun_9mer.csv`、`scripts/out_rerun_official/*.csv`
- 工具部署真源：`TOOL_RERUN_STATUS.md`（各工具 env/本地HPC/踩坑）
- 切肽/输入脚本：`scripts/{cut_from_protein.py, build_rerun_inputs.py, prepare_inputs_official.py}`
- 铁律：数字 Bash 核 csv、复现零偏离、不漏数据、`MSYS_NO_PATHCONV=1` 跑 wsl。
