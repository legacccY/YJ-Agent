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
| 3 | PRIME | 免疫原 | HPC envs/prime | ✅ done 26/26 | 全等位补齐：MT 1761非空/26等位、WT 244/7等位。KeyError:0 根因=并发撞共享 temp(12等位顺序重跑即通) + B2706 非 alleles_list 走 pan 路径触 pandas3.0.3 索引 bug(`PWM[i+1][j]` 字母索引 Series int 当标签查)→ `.iloc` 忠实 compat 修(只影响 pan,patch 后还原 repo)。抽核 B*27:06/C*05:01 分溯源 raw 精确一致 |
| 4 | DeepImmuno | 免疫原 | **WSL deepimmuno(TF2.3)** | ✅ done | DeepImmuno_official.csv 1761MT/26HLA;repo /root/quantimmu/tools_repos/DeepImmuno;9/10mer;higher=强no flip;抽核2值PASS |
| 5 | PredIG | 免疫原 | HPC sif/predig.sif | ✅ done | W4: `singularity run`(OCI entrypoint=micromamba run -n predig_env python /Immuno/run_predig/run.py,非exec);--modelXG neoant --type recombinant;PredIG列(越高越免疫原)。MT 1761/0NaN+WT 244;位置join+3断言;2值对账容器一致。PredIG_official.csv |
| 6 | IMPROVE | 免疫原 | HPC envs/imp_feat+improve | ✅ done(档III) | W4: Simple模型(唯一可行,TME需组学)。官方feature_calculations.py全1761肽跑通(netMHCpan4.1+PRIME+MixMHCpred+**STAB=1真算netMHCstabpan**)。3缺特征(Expression/NetMHCExp/Foreigness纯肽结构性不可得)走**官方predict自带mean-impute**(论文明示=合法非降级)。MT_IMPROVE(mean_prediction_rf)越高越强;MT 1761全;3值溯源tsv MATCH。**档II(antigen.garnish真算foreignness)HPC受阻**:garnish装通+1.3GB数据下全+blastp 2.17,但Biostrings≥2.77.1 pairwiseAlignment defunct(antigen.garnish 2.3.1调它挂),降级Biostrings又撞conda solver墙→II待本地antigen.garnish(R4.3.3/Bioc3.18原生pairwiseAlignment)可补。IMPROVE_official.csv |
| 7 | pTuneos | 免疫原 | 本机 WSL docker bm2lab/ptuneos:v2.1 | ✅ done | W4: HPC sif 死路(/root perm700+无fakeroot+无blastdb)→本地docker(blastdb在/root,root daemon可读,无需sudo)。1462跑→244 found/1517 NaN(1517无WT配对=工具边界)。仅 MT_pTuneos 列。2值溯源容器一致。pTuneos_official.csv |
| 8 | NeoTImmuML | 免疫原 | 本机 R4.3.3(Peptides 2.4.6) | ✅ done | W4: HLA-agnostic纯肽78特征;无官方权重/训练CSV→**忠实复现**:TumorAgDB2.0真实带标重建平衡集5147:5147(≈论文5156:5156),论文超参重训RF/LGBM/XGB+4:8:9阈值0.5。held-out Ensemble AUC=0.867(≈论文0.86)正预测829/2059非全判负=模型有效。demo aaComp_1/cruciani_1损坏→论文语义口径(NonPolar/PP1)。MT 1757/WT 244;广播;2值溯源一致。非bit-exact(原权重需作者13401930670@163.com)。NeoTImmuML_official.csv |
| 9 | deepHLApan | 呈递/免疫原 | 本机 WSL2 docker biopharm/deephlapan:v1.1 | ✅ done | W4: 本地 docker 跑通(无需HPC),MT 1761全覆盖+WT 244;bind+immuno 双列;3值抽核对原始输出一致。deepHLApan_official.csv |
| 10 | BigMHC_IM | 免疫原 | **本地 CPU torch** | ✅ done | BigMHC_IM_official.csv 1761MT/26HLA;用 repo/src(完整clone非bigmhc-master);IM prob越高越强no flip;抽核2值PASS |
| 11 | CNNeo | 免疫原 | **本地 CPU torch(fcnn_tf)** | ✅ done | CNNeo_official.csv 1761MT/26HLA;repo+权重在HPC/deploy/cnneo;越高越强no flip;抽核2值PASS |
| 12 | Repitope | 免疫原 | **本机 R4.3.3(proven 2026-06-26)** | ✅ done | W4: HPC conda 5次堵死(无libmamba啃不动caret+mlr+msa)→改本机。**复用2026-06-26已部署proven pipeline**(HPC/deploy/repitope/,Repitope v3.1.7+rJava+extratrees+mendeley数据全在,跑过7437肽)——前面HPC死磕白费(工具早建好)。补跑551肽:Features 551×33特征(270s)+ERT训练(5seed×5fold)+Immunogenicity_Predict外推(551肽部分在训练集,用Predict非Score做apples-to-apples,NOTES记caveat不静默丢)。ImmunogenicityScore越高越强。MT 1761/0NaN+WT 244;HLA-agnostic广播;3不同肽溯源raw MATCH。Repitope_official.csv |
| 13 | TSCAPE | 免疫原 | HPC GPU(t_scape未装) | 🟡 defer | repo+54.7GB权重未装+需GPU;W1判defer,5工具先交,过夜拉权重增量补 |
| 14 | NetTepi | 免疫原 | HPC DTU ext_tools | ✅ done | netTepi.py+qib_py27(py2.7)+qib_perl(Env.pm)修通;Comb列;仅6/26等位(13等位模型,P104全NaN)→29/43肽;MT470;pending consent |
| 15 | ICERFIRE | 免疫原 | HPC envs/qib_icerfire | ✅ done | ICERFIRE.sh -a false -u false(ExprFalse);prediction列(越高越强);需WT→仅14SNV肽;MT244;pending consent |
| 16 | MUNIS | 免疫原 | **WSL munis_env(ESM-2 CPU)** | ✅ done | MUNIS_official.csv 1761MT/26HLA;EL presentation越高越强no flip;CPU 9:46min;抽核2值PASS |
| 17 | andy90 | 免疫原 | HPC envs/andy90_r+netMHCpan | ✅ done | andy90_official.csv 1761MT/26HLA/P104全;用户授权后HPC登录节点xargs-P4跑26HLA(~4.5min)+merge(envs/improve python,andy90_r无python=旧merge失败根因);amplitude越高越强no flip;抽核2值PASS;netMHCpan=DTU pending consent |
| 18 | ImmuGenX | 免疫原 | **WSL immugenx(CPU JIT)** | ✅ done | ImmugenX_official.csv 1761MT/26HLA;sigmoid越高越强no flip;抽核2值PASS |
| 19 | Seq2Neo | 免疫原 | HPC | ⬜ bonus | 阻塞 netCTLpan |
| 20 | DeepNetBim | 免疫原 | **WSL qib_tf1(TF1.15/keras2.2.4)** | ✅ done | DeepNetBim_official.csv 1761MT/26HLA;9mer ONLY;immuno_probability越高越强no flip;license=null发表前邮件Li-Lab-SJTU;抽核2值PASS |
| 21 | NeoaPred | 呈递结构 | HPC GPU | ✅ done | job1502935 跑完(gpu4090n9,1h35m,8块并行,244严格9mer)。NeoaPred_official.csv:1761行,**MT_NeoaPred 244非空**(非9mer NaN=工具9mer口径边界),仅MT列(foreignness无WT列)。分0–0.9796/mean0.244/62候选>0.5。抽核 ID_0=0.00200(bb226)/ID_233=0.32858(bb1660) 溯源 foreignness raw 精确一致。slot8e419949已release |
| 22 | netMHCpan_BA | 呈递 | HPC DTU ext_tools | ✅ done | netMHCpan-4.1 `-BA -xls`(一次出BA+EL列);BA-score列;MT 1761/100%/26等位/43肽全;WT244;pending consent;headline主角 |
| 23 | netMHCpan_EL | 呈递 | HPC DTU | ✅ done | 同-BA批xls的EL-score列;MT 1761/100%/26等位/43肽;WT244;pending consent |
| 24 | netMHCstabpan | 呈递 | HPC DTU | ✅ done | 登录节点直跑(glibc2.28无需net.sif,W1实证);Pred列(越高越稳);MT 1761/100%/26等位;WT244;pending consent |
| 25 | MHCflurry | 呈递 | HPC envs/mhcflurry(py3.10+tf-cpu2.12,新建) | ✅ done | MHCflurry_official.csv 1761 MT全/WT244/26等位;MT_MHCflurry_presentation(取presentation头,merge别名mhcflurry_presentation)+affinity_neg(=-aff,AUX);models走ghfast.top镜像(github直连20kB/s太慢);14883等位全SUP含B2706;抽核3值PASS |
| 26 | MHCnuggets | 呈递 | HPC envs/mhcnuggets(py3.9+tf2.12,新建) | ✅ done | MHCnuggets_official.csv 1761 MT全/WT244/26等位;-ic50越低越强取负;抽核3值PASS;镜像tsinghua装(pin tensorflow全量非cpu避回溯) |
| 27 | MHCseqNet | 呈递 | HPC envs/immuneapp(复用+sklearn) | ✅ done | MHCSeqNet_official.csv 1761 MT全/WT244/26等位;prob越高越强不翻;`-p sequence_model/`尾斜杠+cwd=repo;sequence模型5集成;抽核3值PASS |
| 28 | TransHLA | 呈递 | HPC envs/yjcu124py310(复用+fair-esm) | ✅ done | TransHLA_official.csv 1761 MT全/WT244/26等位;**HLA-agnostic肽广播**(同肽1值);prob↑不翻;抽核3值PASS+广播核(同肽4行1值)。**坑=ESM2-650M backbone权重(2.6GB)走fair-esm从fbaipublicfiles下,国内685KB/s且kill不续传→cpudebug 1h wall内永下不完**;修=8线程curl range下到torch hub cache(`~/.cache/torch/hub/checkpoints/esm2_t33_650M_UR50D.pt`)一次性,后job秒加载;cpudebug qos(cpu4/wall1h),PYTHONUNBUFFERED+直接activate非conda run(否则吞输出) |
| 29 | HLAthena | 呈递 | HPC sif/hlathena.sif+hla_arr ecdf | ✅ done | HLAthena_official.csv 1761 MT1708/WT244/**25等位**;B*27:06无ecdf仅B2705→诚实NaN(53行);MSi presentation proxy↑;复用老chunk管道(star→PRIME,单长度8-11mer);抽核2值PASS |
| 30 | NeoaG | 免疫原 | **本地 R4.3.3(GBM)** | ✅ done | Neoag_official.csv 134MT(89对广播/HLA-agnostic);WT结构NaN;用run_neoag_main.R(非死壳run_neoag.R);type=raw回归分higher=强no flip;researcher核实官方API清全TODO;抽核2值PASS |

排除：MHLAPre(权重永久缺)、ImmunoStruct(NO-GO)、DeepNeo(作者无回信)、Inference8-class(源码未确认)。

> **W0 验收账本** = `W0_VERIFY_LEDGER.md`（各工具检测验收裁决真源，含反造数/诚实NaN核 + 阻塞项）。

## 🔗 W0 命名契约（各窗强制对齐，否则 merge 捡不到你的补跑分）

W0 收口脚本 `scripts/merge_official_30.py` 按 **canonical 工具名 + 别名表** 自动并入。各窗产物只要满足：
1. **文件名** `scripts/out_official/<Tool>_official.csv`，`<Tool>` ∈ 下表 canonical 名或其别名（大小写不敏感）。
2. **列**：`bb_idx, MT_<Tool>[, WT_<Tool>]`，1761 行对齐 `master_backbone_official.csv`（bb_idx join）。
3. 不在表里的工具名 → 写完**通知 W0 加别名**，别自创让 merge 漏掉（标 __AUX_ 不计 roster）。

| canonical（W0 用） | 接受的别名 | 窗 |
|---|---|---|
| netMHCpan_BA / netMHCpan_EL / netMHCstabpan | netmhcpan_ba / netmhcpan_el / netmhcstabpan,stabpan | W1 |
| NetTepi / TSCAPE / ICERFIRE | nettepi / tscape / icerfire | W1 |
| MHCflurry | mhcflurry,mhcflurry_presentation（取 presentation 头） | W2 |
| MHCnuggets / MHCseqNet / TransHLA / HLAthena | mhcnuggets / mhcseqnet / transhla / hlathena | W2 |
| BigMHC_IM | bigmhc,bigmhc_im（取 IM 免疫原头） | W3 |
| CNNeo / MUNIS / DeepNetBim / DeepImmuno / andy90 / ImmuGenX / NeoaG | cnneo / munis / deepnetbim / deepimmuno / andy90 / immugenx / neoag | W3 |
| PredIG / pTuneos / IMPROVE / NeoTImmuML / deepHLApan / Repitope | predig / ptuneos / improve,improve_mean_prediction_rf / neotimmuml / deephlapan / repitope | W4 |
| PRIME / NeoaPred | prime / neoapred | W5 |

**W0 锁定 roster 默认（用户 2026-06-30 拍板「按默认先跑」，收口前与袁/朱终对齐）**：BigMHC 取 **IM 头**（EL→AUX）；MHCflurry 取 **presentation 头**（affinity_neg→AUX）；MixMHCpred=PRIME 依赖**不算独立工具**（→AUX）；Seq2Neo 进 roster 但多半 **PENDING**（阻塞 netCTLpan）。

## 合并终点
全 official csv 齐 → `scripts/merge_official_30.py`（合 87 复用旧分 + 43 补跑新分，5 校验门 + canonical 化 + 覆盖报告）→ `scripts/out/merged_all_tools_30_official.csv` → `p0e_pool_to_peptide.py` → `analysis/phase0/smoke_integration.py`（集成烟测闸，9 患者非 NaN）→ `p0f_freeze_provenance.py`（sha256 冻结）→ 解锁 R1-R9 分析。
**备料状态（2026-06-30 W0）**：merge+smoke 端到端验通（当前 3 工具齐，GATE PASS）；每补 1 工具重跑这条链自动并入放行，零返工。

## 进度
2/30 done(IEDB_Calis, ImmuneApp) + PRIME 13/26 等位 + 87 肽旧分可复用。
**2026-06-30 W1 收 DTU slice**：+5 DTU 工具 done(netMHCpan_BA/EL/netMHCstabpan/NetTepi/ICERFIRE),TSCAPE defer。→ **7/30 done**。5 csv 全 1761 行对齐+Bash 抽核≥2(肽,等位)真值 MATCH,待 W0 验收。剩 ~22 工具(W2-W5)。
