# 工具补跑状态追踪（新官方数据 43 肽，run-once）

> 建 2026-06-30。新官方 RCC 数据换桩后，30 工具需在 43 补跑肽（29 缺失 + 14 P104）上重跑。
> 复用 87 肽旧分（已在 merged_29tools），补跑产 official csv → 合并 merged_30_official。
> **数字真源**：各 `scripts/out_official/<Tool>_official.csv`（bb_idx, MT_<Tool>, WT_<Tool>）。覆盖核：Bash 不信 parse 自报（曾抓肽级兜底造数）。

## 已固化的通用 pattern（续窗照搬）
- 输入：`HPC official_inputs/out_official/`（已上传，含 MT+WT）。通用喂料 `newtools/uniq_pep_hla.csv`(1462) / `universe.csv` / `uniq_pep.csv`(462)。
- 本地纯 python 工具 → 本地跑（如 IEDB_Calis）。其余在 HPC（conda env/sif/DTU 二进制/GPU）。
- HPC conda 激活：`module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta` + `source $(conda info --base)/etc/profile.d/conda.sh` + `conda activate envs/<tool>`。
- 相对路径工具要 `cd` 进 repo（ImmuneApp 的 supporting_file 踩坑）。
- paramiko 后台启用 `setsid bash X </dev/null >log 2>&1 &`（防 channel fd 阻塞）。
- 拉回 parse **必须精确 (肽,等位) 匹配，缺→NaN**，禁肽级兜底（merge_prime 造数 bug 教训）。
- HPC 路径：root=`/gpfs/work/bio/jiayu2403/quantimmu`，工具 repo 多在 `tools_repos/`，DTU 二进制 `ext_tools/`，sif `sif/`，envs `envs/`。MixMHCpred=`tools_repos/MixMHCpred/MixMHCpred`。

## 30 工具状态（17 免疫原 + 呈递；含已复用旧分的）

| # | 工具 | 类 | env/位置 | 状态 | 备注 |
|---|---|---|---|---|---|
| 1 | IEDB_Calis | 免疫原 | 本地 python | ✅ done | `run_iedb_calis_official.py`，1761 行，43 肽全覆盖，管道验通 |
| 2 | ImmuneApp | 免疫原 | HPC envs/immuneapp | ✅ done | 26 等位全，cd repo 修复后跑通；ImmuneApp_official.csv |
| 3 | PRIME | 免疫原 | HPC envs/prime | 🟡 13/26 等位 | MixMHCpred 第 15+ 等位(B40/B44/B55/B57/全C)报 pandas KeyError:0，待深挖等位PWM/env |
| 4 | DeepImmuno | 免疫原 | HPC envs/deepimmuno | ⬜ todo | 输入 deepimmuno_input.csv 已生成 |
| 5 | PredIG | 免疫原 | HPC sif/predig.sif | ⬜ todo | predig_input.csv(2005,含WT)已生成 |
| 6 | IMPROVE | 免疫原 | HPC envs/improve+imp_feat | ⬜ todo | improve_input.tsv 已生成；WT_peptide 空(已补全)|
| 7 | pTuneos | 免疫原 | HPC sif/ptuneos.sif | ⬜ todo | ptuneos_input_unique.tsv;依赖 netMHCpan |
| 8 | NeoTImmuML | 免疫原 | HPC envs/neotimmuml | ⬜ todo | 需先 calc_78_features.R(R+iFeature) |
| 9 | deepHLApan | 呈递/免疫原 | 本机 WSL2 docker / HPC | ⬜ todo | deephlapan_input_MT/WT.csv 已生成 |
| 10 | BigMHC_IM | 免疫原 | HPC torch | ⬜ todo | universe 喂料；run_bigmhc_im.py |
| 11 | CNNeo | 免疫原 | HPC | ⬜ todo | run_cnneo.py |
| 12 | Repitope | 免疫原 | HPC R | ⬜ todo | uniq_pep.csv(HLA-agnostic) |
| 13 | TSCAPE | 免疫原 | HPC DTU | ⬜ todo | pending DTU consent |
| 14 | NetTepi | 免疫原 | HPC DTU ext_tools | ⬜ todo | pending DTU consent;低覆盖 |
| 15 | ICERFIRE | 免疫原 | HPC envs/qib_icerfire | ⬜ todo | pending DTU consent |
| 16 | MUNIS | 免疫原 | HPC torch | ⬜ todo | run_munis.py |
| 17 | andy90 | 免疫原 | HPC envs/andy90_r | ⬜ todo | run_andy90.py;最近跑过(andy90b job) |
| 18 | ImmuGenX | 免疫原 | HPC | ⬜ todo | run_immugenx.py;100%覆盖 |
| 19 | Seq2Neo | 免疫原 | HPC | ⬜ bonus | 阻塞 netCTLpan |
| 20 | DeepNetBim | 免疫原 | HPC torch | ⬜ todo | run_deepnetbim.py |
| 21 | NeoaPred | 呈递结构 | HPC GPU | ⬜ todo | 唯一 GPU,走 gpu_slot;慢;Apache-2.0 |
| 22 | netMHCpan_BA | 呈递 | HPC DTU ext_tools | ⬜ todo | pending DTU consent;headline 主角 |
| 23 | netMHCpan_EL | 呈递 | HPC DTU | ⬜ todo | run via patch_add_netmhcpan_el |
| 24 | netMHCstabpan | 呈递 | HPC DTU | ⬜ todo | pending consent;依赖 netMHCpan-2.8 |
| 25 | MHCflurry | 呈递 | HPC pip(env) | ⬜ todo | run_mhcflurry.py;CPU |
| 26 | MHCnuggets | 呈递 | HPC TF | ⬜ todo | run_mhcnuggets.py |
| 27 | MHCseqNet | 呈递 | HPC torch | ⬜ todo | run_mhcseqnet.py(替MAAP) |
| 28 | TransHLA | 呈递 | HPC GPU torch | ⬜ todo | run_transhla.py |
| 29 | HLAthena | 呈递 | HPC sif/hlathena.sif | ⬜ todo | proxy 单列 |
| 30 | NeoaG | 免疫原 | HPC | ⬜ todo | run_neoag.py |

排除：MHLAPre(权重永久缺)、ImmunoStruct(NO-GO)、DeepNeo(作者无回信)、Inference8-class(源码未确认)。

## 合并终点
全 official csv 齐 → 合并入 `merged_all_tools_30_official.csv`（87 复用肽旧分 + 43 补跑肽新分）→ `p0e_pool_to_peptide.py` → `p0f_freeze_provenance.py` → 解锁 R1-R9 分析。

## 进度
2/30 done(IEDB_Calis, ImmuneApp) + PRIME 13/26 等位 + 87 肽旧分可复用。剩 ~27 工具按 pattern grind。
