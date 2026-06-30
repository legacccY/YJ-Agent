# W0 主窗验收账本（检测验收真源，不信自报）

> 建 2026-06-30 W0 orchestrator。各窗回报工具 DoD → W0 Bash 抽核（结构+反造数+诚实NaN核）→ 此账本记裁决。
> 验收法：merge 后 `scripts/out_official/<Tool>_official.csv` join backbone：① 1761 行对齐 bb_idx ② MT 非空数/distinct值/等位数/43补跑肽覆盖 ③ 反造数（跨工具列不雷同 + 非常量 + 范围合理）④ 诚实 NaN 与状态表说明吻合。

## 裁决（2026-06-30 首轮扫描，18 工具落 csv）

| 工具 | 行 | MT非空 | distinct | 等位 | 补跑肽 | 范围 | 裁决 |
|---|---|---|---|---|---|---|---|
| BigMHC_IM | 1761 | 1761 | 1418 | 26 | 43/43 | [6e-6,0.97] | ✅ PASS |
| CNNeo | 1761 | 1761 | 666 | 26 | 43/43 | [0.14,0.96] | ✅ PASS |
| DeepImmuno | 1761 | 1761 | 1424 | 26 | 43/43 | [0.12,0.999] | ✅ PASS |
| DeepNetBim | 1761 | 1761 | 1021 | 26 | 43/43 | [0,1] | ✅ PASS |
| ICERFIRE | 1761 | 244 | 225 | 7 | 14/43 | [0.077,0.33] | ✅ PASS（需WT→仅14SNV肽，诚实NaN吻合） |
| IEDB_Calis | 1761 | 1761 | 734 | 26 | 43/43 | [-0.79,0.49] | ✅ PASS |
| ImmuGenX | 1761 | 1761 | 1460 | 26 | 43/43 | [0.08,0.84] | ✅ PASS |
| ImmuneApp | 1761 | 1761 | 837 | 26 | 43/43 | [0,1] | ✅ PASS |
| MHCseqNet | 1761 | 1761 | 1354 | 26 | 43/43 | [0,1] | ✅ PASS |
| MUNIS | 1761 | 1761 | 1419 | 26 | 43/43 | [2e-4,0.997] | ✅ PASS |
| NetTepi | 1761 | 470 | 156 | 6 | 29/43 | [-0.04,0.73] | ✅ PASS（13等位模型+P104全NaN，吻合） |
| PRIME | 1761 | 1761 | 1321 | 26 | 43/43 | [3e-4,0.24] | ✅ PASS（26/26等位补齐，抽核B*27:06/C*05:01溯源一致） |
| deepHLApan | 1761 | 1761 | 949 | 26 | 43/43 | [0,0.9999] | ✅ PASS |
| netMHCpan_BA | 1761 | 1761 | 925 | 26 | 43/43 | [2e-3,0.83] | ✅ PASS |
| netMHCpan_EL | 1761 | 1761 | 319 | 26 | 43/43 | [0,0.97] | ✅ PASS |
| netMHCstabpan | 1761 | 1761 | 416 | 26 | 43/43 | [0,0.98] | ✅ PASS |
| pTuneos | 1761 | 244 | 5 | 7 | 14/43 | [0,0.6] | 🟡 PASS-注（232/244=0零膨胀；pTuneos严过滤旧亦稀疏，溯源一致；可用但记录） |
| Neoag | 1761 | 134 | 13 | 7 | 14/43 | [1.9,201] | 🔴 待W3核（13.17×70/1.9339×28 值聚集疑默认填充；状态表仍todo未定稿） |

**反造数全局检测**：18 工具两两 MT 列无一雷同（`np.allclose` n>50）→ 无 copy 造数。M3 partial 等位完整性 PASS（无换出 A*03:01，含新 A*30:01）。

## 🔴 阻塞 / 需攻坚（W0 代查根因 2026-06-30 定论）

**MHCflurry + TransHLA：从未在官方 43 补跑肽上真跑（raw 是旧 DS1DS2 残留冒充）。**
- 现场：out_official 只有空的 `mhcflurry_unsupported_official.csv` / `transhla_skipped_official.csv`（0 数据行）+ input，无真 official csv。
- W0 本地深挖（不连 HPC）：
  - `HPC/deploy/mhcflurry/mhcflurry_raw.csv`(53583 行) / `transhla_raw.csv`(11904 行) 看似有分，**但**：
  - 两 raw 对 backbone 9mer 覆盖 = **partial(P104,14 肽)168/168 全中 + full(29 新肽)0/294 全缺**。
  - 即 raw 只含 14 partial 肽的 MT 子肽（这些 9mer 旧数据本就有，因 MT 子肽未变只换 HLA），**29 个 full-rerun 新肽一个没跑** → raw = 旧 run 残留，非官方新跑。
- 判定：**不是工具不支持/降级，是 W2 根本没在官方输入上跑这两个工具**（旧 merged 34247/34247 + raw 9mer 打分都证明工具能跑）。空 unsupported/skipped 标记 = 误导性占位。
- 处置：**绝不拿 stale raw 产 official csv**（= 用旧分填 partial、full 留 NaN，把 168/462 冒充 done = 造数，正是 run-once 红线）。**W2 须在 HPC 对官方 input 真跑**：MHCflurry(CPU pip env)、TransHLA(GPU torch)，产 1761 行对齐 official csv。
- merge 已自动跳过空文件，当前靠旧复用分覆盖 87 肽；43 补跑肽缺口待 W2 真跑填。

## 🟡 已解释（降级关注）
- **Neoag**：值聚集(13.17×70/1.9339×28) = **HLA-agnostic 同肽分跨等位广播**（非默认填充），状态表 W3 标 done + 抽核 2 值 PASS。低关注，收口前抽核广播一致性即可。

---

## 全量验收第二轮（2026-06-30「开足马力」，24 工具，跳过 IMPROVE pending）

**全 PASS**：结构（1761 行 / bb_idx 集 ⊆ backbone / 无重复 / 无越界）+ 覆盖 + **反造数**（跨工具 24 列两两无雷同 `allclose` → 无 copy；本地 raw 可溯源者逐值核）。

**MHCflurry / TransHLA 重点复核（W2 中途快照曾疑，现真补完）**：
- MHCflurry：official ↔ 新 raw(1596 行) **maxdiff=0**，1761 全重叠，full 肽 29/29。✅ 真（presentation 头）。
- TransHLA：official ↔ 新 raw(551 行,scripts/out_official/) **maxdiff=0**，1761 全重叠，full 29/29。✅ 真（prob，HLA-agnostic 广播）。
- 教训：旧 stale raw(HPC/deploy 下 11903/53583 行)仅覆盖 168 partial-9mer，与 official 比有 0.0012 噪声差 → 溯源必须对**官方新 raw**，否则误判。W2 应删空 marker `mhcflurry_unsupported/transhla_skipped_official.csv`。

**诚实边界 NaN（查证非降级）**：
- HLAthena：53 NaN 全 B*27:06（模型无 ecdf）。
- ICERFIRE / Neoag / NeoaPred / pTuneos：full **1/29**（需 WT 或 9mer 结构 → 仅 SNV 肽；29 full 含 indel 无 WT）= 工具边界。
- NetTepi：partial **0/14**（P104 仅新等位 A*30:01，NetTepi 13-等位模型不含）+ full 29/29。

**朝向/尺度 note（rank-based Spearman 不受影响，记录）**：
- andy90：MT = **amplitude**（DAI 比值，范围 0.5~2.4e5），非 raw 的 `immunogenic` YES/NO 二值。连续 rank 有意义，选 amplitude 合理。
- MHCnuggets：MT = **−ic50**（范围 −4.3e4~−5.7），higher=强结合。
- pTuneos：232/244=0 零膨胀（填充检测报 43% 实为真零，非兜底）。

**待清理（不阻塞）**：`neotimmuml_features_official.csv` / `neotimmuml_scores_official.csv` = W4 中间文件误带 _official 后缀（无 bb_idx，merge 自动忽略），真产物 = `NeoTImmuML_official.csv`(1757/1 NaN)。建议 W4 改名/移走。

## 🔴 T-SCAPE 上游代码 blocker（W0 2026-06-30 实证，不 patch）
clone seoklab/T-SCAPE（HEAD 637cb5b，**无 tag/release**）读 `inference_csv.py` 实证：`--inf_type pmhc_im_neo`（README 指定用法）公开代码**跑不了**：
1. **权重未加载**：line 45 无条件建 `Finaltask1_perf`，但 `load_state_dict` 只在 `if (pmhc_im)|(p_im)` 分支（line 59-69）；pmhc_im_neo 走不进 → 随机初始化权重 = 垃圾输出（silent，比崩危险）。
2. **task_dict KeyError**：neo 权重名含 `el-mlm`→取 mlm 版 task_dict，无 `pmhc_im_neo` 键 → line 363 `task_dict[inf_type]` 崩。
- README + example/outputs/pmhc_im_output.csv 引用 pmhc_im_neo，但公开 release 代码不一致（作者内部版本有，公开版漏实现）。
- 复现零偏离：不私自加载载分支+猜 task index（=臆测+造数风险）。coder RISK note 也警告勿 patch。
- 工具概念有效（example 输出 0.13/0.87/4.2e-9 = 真免疫原分）；坏的是公开代码路径。
- **出路**：A=Galaxy web server（官方正确实现，手动传 CSV，galaxy.seoklab.org/design/t-scape）保 T-SCAPE；B=改用 **TRAP**（R3 vetted：Genome Medicine 2023，CPU，复用我们 netMHCpan rank，代码干净）；C=邮件 seoklab 要正确代码（慢）。本地代码 clone 留 `tools_local/T-SCAPE`。

## 收尾手工 handoff（2026-06-30 收工，runner 全就绪，用户手工跑）

### TRAP（替 T-SCAPE，已选）— 本地 CPU
- runner 就绪：`scripts/hpc_official/{prep,run,parse}_trap_official.py`（prep 已跑✅ 1761 覆盖，产 `scripts/out_official/trap_inputs/trap_input.csv`）
- repo 已 clone `tools_local/TRAP`（openssl 后端绕 schannel SSL）
- **RANK=EL_Rank**（NetMHCpan-4.1 默认 %Rank=EL + TRAP "presented peptides" 语义；论文 Methods 三源全挡没核到，BA 为一参重跑备选）；**MODEL=self**（cancer/autoantigen）
- coder 修 1 处上游 NameError（`dash_app` 的 `model(...)`→`encoder(...)`，仅修 bug）
- 手工命令（前台跑，勿后台/会被 kill；建议 WSL/linux 跑 2022 老栈）：
  1. 下权重 ensemble：`cd tools_local/TRAP && python -m gdown --folder "https://drive.google.com/drive/folders/15A2P5xP2c-q48vVGPRB7h7uHEMycPYoX" -O drive_assets --remaining-ok`（多套 TF SavedModel，按 repo 归位 model/+data/）
  2. env：`conda create -n trap python=3.7 -y && pip install -r requirements.txt`（torch1.12.1/TF2.9.1/transformers4.24；首推理拉 ProtT5-XL ≈2.8GB）
  3. 跑：`run_trap_official.py --trap-repo tools_local/TRAP --input scripts/out_official/trap_inputs/trap_input.csv --model self [--smoke 2] --out .../trap_output.csv` → `parse_trap_official.py` → `TRAP_official.csv`
- 跑完重跑 `merge_official_30.py` 自动并入（别名 trap→TRAP 已配）= 29 工具。

### Seq2Neo（第 30）— HPC，卡 netCTLpan 许可
- runner 就绪：`scripts/hpc_official/{prep,run,parse}_seq2neo_official.*`
- 真阻塞：netCTLpan-1.1 需 DTU 学术许可申请（services.healthtech.dtu.dk/services/NetCTLpan-1.1/，CNN 硬依赖其 TAP 列）；W0 paramiko 被 auto 拦 → 用户 `!` 跑或 W1 接手
- 手工：装 netCTLpan-1.1 入 PATH → 填 run 脚本头变量 → 烟测→全量→parse → `Seq2Neo_official.csv`

## roster 收尾决策（用户 2026-06-30 拍板）
- **TSCAPE**：弃 54.7GB+GPU 重装路。用户追问「有没有别的方法」→ R1 researcher 查轻量跑法；并行 R3 查更有参考价值的免疫原性工具替代（保 10 呈递+20 免疫原 框架，袁老师定稿）。
- **Seq2Neo**：攻坚补上 → R2 researcher 查 netCTLpan 解阻塞/替代。
- 3 researcher 后台并行中（不堵塞），结果回 W0 综合再拍板落哪个工具（可能涉袁老师 roster 对齐）。

**节点验收裁决**：
- `tools_dtu`（W1）：5/6 PASS（netMHCpan_BA/EL/stabpan/NetTepi/ICERFIRE），TSCAPE defer 过夜拉权重（tracked 尾项）。
- `tools_immml`（W3）：8/8 PASS（ImmuGenX/MUNIS/CNNeo/DeepImmuno/BigMHC_IM/DeepNetBim/andy90/Neoag）。
- `tools_presml`（W2）：5/5 PASS（MHCflurry/MHCnuggets/MHCSeqNet/TransHLA/HLAthena，溯源精确）。
- 待：`tools_immbox`（W4：PredIG✅/deepHLApan✅/pTuneos✅ + IMPROVE pending/NeoTImmuML/Repitope）、`tools_finish`（W5：PRIME✅/NeoaPred✅ 收尾）。

## 状态（节点级 DoD，等窗回报 + 余项）
- **PENDING（旧新皆无）**：NeoaPred（job1502935 在跑，授权提交）、Seq2Neo（阻塞 netCTLpan，bonus）。
- **未落 csv（状态表 todo）**：PredIG、IMPROVE、NeoTImmuML、Repitope、andy90、TSCAPE(defer 54.7GB权重过夜拉)、MHCnuggets、HLAthena。
- **W1 DTU slice**：5 done（netMHCpan_BA/EL/stabpan/NetTepi/ICERFIRE）✅验收 PASS，TSCAPE defer → slice 未 100%。

## 收口闸（全绿才放行 R1-R9）
`merge_official_30.py --strict-roster` → `p0e` → `smoke_integration.py` GATE PASS → `p0f` 冻结。
当前 8/30 全覆盖(130)，20 partial，2 PENDING。
