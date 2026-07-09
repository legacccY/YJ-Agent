# 改动②③ · 8-11mer 可变窗口全量重跑 · 多窗编队作战令

> 建 2026-07-08。服务 QuantImmuBench 改动②③「原始蛋白定点切含突变窗」新切口径，从**只 9mer** 扩到 **8/9/10/11 四种窗长**。
> 主窗（收口/协调）已把**地基全部打完**：切肽 + 输入 + 备份 + 增量机器就绪。各干活窗只需**按 slice 打分**。
> 用户授权：**HPC 或本地灵活选择跑，可并行**（HPC sbatch 非阻塞 + 本地 WSL/docker/R 同时跑）。
> 铁律（用户命门）：**不能漏跑，多跑没关系，事后必核有没有漏。** 复现零偏离（工具/权重/超参不改）。数字 Bash 核 csv 不信 Read。

---

## 0. 地基状态（主窗已完成，别重做）

| 产物 | 路径 | 说明 |
|---|---|---|
| **全 8-11 输入**（本地打分主喂料） | `scripts/out_rerun/` | backbone 17088 行（bb_idx 0-17087，含 Window_Size 列 8/9/10/11）；各工具输入已导出 |
| only-new 输入（HPC 省时可选） | `scripts/out_rerun_8to11/` | backbone 13035 行（只 window∈{8,10,11}）；HPC 若想省 9mer 重跑用它，收口装配复用 9mer |
| **打分输出目录**（各窗落这） | `scripts/out_rerun_official_8to11/` | 各窗 parse 落 `<Tool>_official.csv` |
| 9mer 分数备份（复用/交叉核） | `scripts/out_rerun_official_9mer_2026-07-08/` | Entry 57 的 29 工具 9mer 分 + backbone，**只读别动** |
| 9mer frozen 表备份 | `data/frozen/_9mer_newcut_backup_2026-07-08/` | 只读别动 |

切肽计数（Bash 核）：表A 3876 窗 = 102 肽 ×(8+9+10+11)；成窗 3855（SLP 3035 + MANE 820）；dropped 21（END_TRUNCATED 18 + ISOFORM_CONFLICT 3，显式记 `data/frozen/newcut_dropped_windows.NEW.csv`）。表B 34176 行（MT/WT 各 17088）。**8-11 里的 9mer 子集与独立 9mer 逐 key 完全一致**（已证），故 9mer 可直接复用/交叉核。

---

## 1. 打分策略（统一，所有窗照做）

**默认 = 全 8-11 重打分**（最稳、防漏、merge 统一）：
1. 各工具读**默认 backbone** `scripts/out_rerun/master_backbone_official.csv`（17088 行，工具脚本原本就指这里，路径不用改）。
2. 跑工具（复用其 9mer 已部署环境，见 §2 表右列，复现零偏离）。
3. parse 落 **`scripts/out_rerun_official_8to11/<Tool>_official.csv`**，列 `bb_idx, MT_<Tool>[, WT_<Tool>]`，**17088 行对齐 backbone bb_idx**。
   - 工具脚本默认写 `scripts/out_rerun_official/<Tool>_official.csv`（9mer 已备份到 `_9mer_2026-07-08/`，覆盖它安全）→ 跑完 **move/cp 到 `out_rerun_official_8to11/`**。或直接改脚本 OUT 常量指向 `_8to11`（二选一，别忘搬）。
4. **MT + WT 双侧都跑**（用户 2026-07-08 拍板 WT 也跑，8-11 也算 DAI）。

**HPC 省时可选**：想省 9mer 重跑 → 喂 `out_rerun_8to11/`（13035 行只新窗）→ 产 13035 行 official 落 `out_rerun_official_8to11new/<Tool>_official.csv`，**通知主窗**，收口用装配脚本拼 9mer 复用分成 17088。（不想省就跑全 8-11，最简单。）

**长度受限工具**（脚本会自动跳/或喂前滤，不能漏但也别硬喂它不支持的长度）：
- **DeepNetBim = 只 9mer** → 8/10/11 全 NaN，只需产 9mer 那 4053 行有值、其余 NaN（或直接复用 9mer 分）。
- **DeepImmuno = 只 9/10mer** → 8/11 NaN，只跑 10mer 新窗 + 复用 9mer。
- HLAthena = 支持 8-11 全长（但 B*27:06 无 ecdf → 诚实 NaN）。
- 其余 ~26 工具全长支持。
- 覆盖脚本 `build_coverage_matrix.py` 已内置 LEN_SUPPORT，会把长度不支持标 `len_filter`（正常，非真漏）。

---

## 2. Slice 分工（4 干活窗 + 主窗收口）

> 每工具在**其已部署环境**跑（见右列，真源 `TOOL_RERUN_STATUS.md` §30 工具状态）。**灵活**：一窗内 HPC 工具走 sbatch 非阻塞、本地工具同时跑，能并行就并行。跑前先 `python tools/gpu_slot.py request quantimmu-rerun8to11 <host> <gpus>`（GPU 工具 gpus=1，纯 CPU/推理填 0），绝不挤正在跑的。

| Slice | 工具（数）· 环境 |
|---|---|
| **W1 · slice_local_a**（8，纯 CPU/本地） | IEDB_Calis(本地 py `run_iedb_calis_rerun.py`) · DeepImmuno(WSL deepimmuno TF2.3, **9/10 only**) · BigMHC_IM(本地 CPU torch) · CNNeo(本地 CPU torch fcnn_tf) · MHCnuggets(WSL2 CPU TF2.10) · ImmuGenX(WSL2 immugenx torch1.12) · MUNIS(WSL munis_env ESM-2 CPU) · DeepNetBim(WSL qib_tf1 TF1.15, **9 only**) |
| **W2 · slice_local_b**（7，含 docker/R/GPU） | Seq2Neo(本地 pip+自带 netMHCpan-4.1/netCTLpan) · NeoaG(本地 R4.3.3 GBM, WT 结构 NaN) · Repitope(本机 R4.3.3 proven) · pTuneos(WSL docker bm2lab/ptuneos) · deepHLApan(WSL docker biopharm/deephlapan) · TransHLA(WSL2 RTX4070 GPU) · TSCAPE(WSL2 tscape env RTX4070) |
| **W3 · slice_hpc_dtu**（6，HPC DTU 二进制） | netMHCpan_BA · netMHCpan_EL · netMHCstabpan · andy90(需 netMHCpan) · NetTepi(仅 6/26 等位) · ICERFIRE(需 WT，14 SNV) — 全 `ext_tools/`，consent=发表闸非算力闸照跑；netMHCpan=DAI 硬输入 |
| **W4 · slice_hpc_env**（8，HPC conda/sif） | ImmuneApp(envs) · PRIME(envs) · PredIG(sif) · IMPROVE(envs imp_feat+improve) · MHCflurry(envs) · MHCseqNet(envs immuneapp 复用) · HLAthena(sif) · NeoTImmuML(**本机 R4.3.3** 或 envs，其 proven env 是本机 R) |
| **主窗** | 收口：merge→pool→recompute effN8（MT+DAI）+ 覆盖矩阵核漏 + 出图 + verifier 核数 + 落档 |

> NeoTImmuML 的 proven env 是**本机 R4.3.3**（TOOL_RERUN_STATUS §8），W4 窗可本地跑它。NeoaPred 已剔不跑。

---

## 3. 每窗 DoD（完成定义，跑完 done 前必做）

1. 自己 slice 每工具 MT+WT 都跑完，parse 落 `out_rerun_official_8to11/<Tool>_official.csv`（17088 行对齐 bb_idx；长度受限工具不支持的长度=NaN 正常）。
2. **抽核 ≥2 个 (肽,等位) 真值**溯源工具原始输出一致（Bash 核，禁 parse 自报）。
3. `python scripts/build_coverage_matrix.py --scored-dir scripts/out_rerun_official_8to11`（若脚本无该参数则先 `--in-dir`/看头注）→ 看**自己那几个工具**有没有 🔴unknown（真漏=工具在同长度+同HLA别处打过分却漏某格）。有就补跑再 done，别把漏留给收口。
4. 一行回报主窗：`<slice> done：N 工具×MT+WT 落 _8to11，抽核 PASS，覆盖无 unknown`。

---

## 4. 铁律（全窗通用）

- **不能漏**：merge `--strict-roster` 硬闸（缺任一 roster 工具报错）+ 覆盖矩阵 + 切片窗自查（§3.3）三重；被排除的格子必**显式记原因**（工具不支持长度/HLA=正常 vs 真漏=补），绝不静默丢。**多跑没关系，漏跑不行。**
- **复现零偏离**：工具/权重/超参/实现完全按 9mer 版，别改别裁剪。
- **别动**：`_9mer_2026-07-08/`、`_9mer_newcut_backup/`、别窗正跑的工具、9mer 已完成的 `out_rerun_official/`（那是 9mer 备份源）。
- **数字 Bash 核 csv 不信 Read**。GPU 工具（TransHLA/TSCAPE）串行占本机 RTX4070(8GB)，避开训练。
- **HPC**：上传输入=对外传输，用户已授权本轮 8-11 上传，但每次上传**一行报**；GPU 经 `gpu_slot.py` 不挤正在跑的；受 QOS 限用 `/loop` 轮询拉回 parse。wsl bash 命令必须前缀 `MSYS_NO_PATHCONV=1`（否则 `/mnt/d/...` 被 Git Bash 转成 `D:/Git/mnt/...` 报 No such file）。
- 状态：各窗写 `04_LOG` 自己那段；主窗收口写总 entry。别撞 PORTFOLIO 写锁。

---

## 5. 收口（主窗，4 slice 全 done 后）

```
# 1. merge（缺任一 roster 报错）
python scripts/merge_official_30.py --in-dir scripts/out_rerun_official_8to11 \
  --out scripts/out/merged_all_tools_30_rerun_8to11.csv --pure-new --strict-roster
# 2. 覆盖矩阵核漏（命门交付，逐格记原因）
python scripts/build_coverage_matrix.py --scored-dir scripts/out_rerun_official_8to11
# 3. pool → recompute effN8（MT）
python analysis/phase0/p0e2_pool_clean.py --input scripts/out/merged_all_tools_30_rerun_8to11.csv --w811 --expect-peptides 102 --output data/frozen/pooled_clean_rerun_8to11mer.csv
python analysis/official/recompute_effN/recompute_R1_effN.py --input data/frozen/pooled_clean_rerun_8to11mer.csv --tag rerun_8to11mer
# → R1_recomputed_rerun_8to11mer_effN8.csv（口径同 9mer：per-patient Spearman→effN≥8→clip±0.99→Fisher-Z 病人等权→tanh）
# 4. DAI（WT 已跑）：build_dai_pool + recompute --tag rerun_8to11mer_dai
# 5. 出图：新写 plot_newcut_9mer_vs_8to11mer.py（哑铃/条形对比）→ figures/ + paper/figures/
# 6. verifier 三方对账（csv↔图↔表）+ 写 04_LOG 新 entry
```

> ⚠️ 收口脚本的具体参数名（`--w811`/`--scored-dir` 等）以脚本头注/`--help` 为准，主窗跑前先核；缺参数派 coder 加（复现零偏离）。
