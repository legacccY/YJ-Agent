# DEPLOY_TRACKER — 5 工具部署状态总表

> 真源：每工具状态 + job_id + 阻塞写这里。详细 4 类信息写 `TOOLS/<tool>.md`。

## 本地部署环境（重要）
- **本机 WSL2 Ubuntu 24.04**（GPU 直通 RTX 4070 可见）= 本地部署/烟测主战场。这些工具多为 Linux-only 老链（TF2.3 / Py2.7 / netMHCpan Linux 二进制），**Windows 跑不动**（且 DeepImmuno repo 含 `HLA-A*0101.json` 非法 `*` 文件名，NTFS 无法 checkout）→ 一律在 WSL2 ext4 原生部署。
- WSL 部署根目录：`~/quantimmu/`（`tools_repos/` 各工具 repo + `smoke/` 烟测产物）；conda 在 `~/miniconda3`。
- HPC（dtn.hpc.xjtlu.edu.cn / jiayu2403）= 正式跑大数据时用；本地 WSL2 先把每个工具跑通 + 摸清 4 类信息。

## 状态总表

| 工具 | Wave | clone | 环境 | 权重下载 | example 烟测 | 4类信息收齐 | 状态 | 阻塞 |
|---|---|---|---|---|---|---|---|---|
| DeepImmuno | 1 | ✅ | ✅ | ✅ | ✅ | ✅ | **SMOKE_PASS** | 无（WSL2 全跑通，单条+批量）|
| PredIG | 1 | ✅ | ✅镜像 | ✅ | ✅ | ✅ | **SMOKE_PASS** | 无（docker 镜像跑通 recombinant，输出 PredIG 分）|
| NeoTImmuML | 1 | ✅ | ☐ | — | ☐ | ✅ | **PARTIAL** | notebook 无预训练权重+须R算78特征；信息齐，跑通需重训 |
| IMPROVE | 2 | ✅ | ✅ | ✅(LFS) | 🟡 步骤2 | ✅ | **PARTIAL** | Predict步✅；DTU工具(netMHCpan-4.1/stabpan/2.8)全✅通；feature_calc 还差 self_similarity/antigen.garnish |
| pTuneos | 2 | ✅ | ✅镜像 | ✅自带 | ✅端到端 | ✅ | **DONE(本地)** | example VCF 端到端跑通(VEP cache+修8坑→40新抗原)；Pre&RecNeo 子模型跑 ELISpot 32178 肽对进 benchmark(对账官方 r=1.0)。HPC sif 受限(非root/fakeroot)未真跑 |

状态枚举：TODO / IN_PROGRESS / SMOKE_PASS / DONE / BLOCKED（标原因，不假装跑通）

### HPC 部署状态（dtn.hpc.xjtlu.edu.cn / `/gpfs/work/bio/jiayu2403/quantimmu/`）
> 上表是本地 WSL2 验证；团队要求最终在 HPC。HPC 环境：Singularity 3.11.3 + module miniconda3/22.11.1；出网 github/pypi/DTU 通、Docker Hub 不通。

| 工具 | HPC 状态 | 说明 |
|---|---|---|
| DeepImmuno | ✅ **SMOKE_PASS** | env `envs/deepimmuno`，单条烟测 0.5324646830558777（=本地）|
| IMPROVE | ✅ **Predict SMOKE_PASS** | env `envs/improve`(py3.11+np2.4+sk1.9)；Predict Simple 出 mean_prediction_rf 100 行(=本地)。feature_calc 待 DTU 工具传 HPC |
| NeoTImmuML | ✅ env ready | env `envs/neotimmuml`(py3.10+lgbm4.6+xgb3.2)，demo 加载 OK。notebook 性质需重训才预测(同本地) |
| PredIG | ✅ **SMOKE_PASS** | predig.sif(4.6G) `singularity run --writable-tmpfs -B ...` recombinant 烟测 PredIG=0.0061380286(=本地) |
| pTuneos | 🟡 sif built / ✅本地端到端 | ptuneos.sif(1.7G)build✅。HPC run 受限：镜像程序在 /root，singularity 非root访问拒+无fakeroot(无subuid映射)。**本地 WSL2 docker 已端到端跑通**(example VCF 40 新抗原 + Pre&RecNeo 跑 ELISpot 进 benchmark)。HPC 真跑需 fakeroot 或重打包到非/root + VEP cache |
| netMHCstabpan | ⚠️ 容器待配 | 二进制需 glibc≥2.29(predig.sif有2.35) **且** tcsh(predig.sif没装) → wrapper跑不了。仅 IMPROVE feature_calc Stability 特征需(Predict 已✅不受影响)。彻底解=建 ubuntu+tcsh sif 或直调 binary 绕 wrapper |
| netMHCpan-4.1 | ✅ HPC 跑通 | 传配好的(53M含三件) + 重配 NMHOME → test.pep 11 行（HPC el8 原生跑，不用 vsyscall）|
| netMHCpan-2.8 | ✅ HPC 跑通 | test.pep 11 行 |
| netMHCstabpan-1.0 | ⚠️ glibc 挡 | 二进制需 **GLIBC_2.29**，HPC el8 仅 **glibc 2.28** → 原生跑不了（与本地 vsyscall 相反的兼容问题）。仅 IMPROVE feature_calc 的 Stability 特征需它（Predict 步不需，HPC 已✅）→ 需 singularity 容器(新 glibc)包它，随 PredIG/pTuneos 镜像批一起 |
| NeoTImmuML env | 🔄 | conda py3.10 装中 |

---

## 部署排序逻辑（易→难，许可解耦）
- **Wave 1（无学术许可依赖，先上）**：DeepImmuno（最干净）→ PredIG（容器绕依赖）→ NeoTImmuML（先找源码 URL）。
- **Wave 2（依赖 netMHCpan 等学术许可，到位后上）**：IMPROVE（核心简单卡外部工具）→ pTuneos（最难，老环境+全基因组）。

---

## 每工具标准部署 6 步
按 `project/HPC_WORKFLOW.md` + paramiko 模板（HPC: dtn.hpc.xjtlu.edu.cn / jiayu2403 / gpu4090）：
1. **本地 clone repo + 读官方 README/example** → 把已知事实填 `TOOLS/<tool>.md`。
2. **建隔离环境**：conda env（DeepImmuno/IMPROVE/NeoTImmuML）或 Singularity/Docker（PredIG/pTuneos）。版本严格按官方 pin（红线：超参/版本禁臆想，查不到标 TODO）。
3. **DTN 预下权重/模型**（GPU 节点不能联网，登录节点 wget/git-lfs 到 cache）。
4. **bundled example 烟测**：用 repo 自带 example 跑通，存 stdout + 输出文件，确认产出分数。
5. **记录 4 类信息**进 `TOOLS/<tool>.md`（输入模板 / 参数 / 输出格式含义 / 简介特点）。
6. **更新本表 + 04_LOG**（状态 + job_id/路径）。

> 拍板点：HPC 上传新代码/数据/许可证 = 对外传输，每次上传前一行报。其余自主推进。

---

## 学术许可申请清单（许可均已解决，状态同步至 2026-06-24）

| 许可工具 | 用途 | 申请处 | 状态 |
|---|---|---|---|
| netMHCpan-4.1 | pTuneos + IMPROVE 的 HLA 结合预测 | DTU Health Tech | ✅ **HPC 装+跑通** `ext_tools/netMHCpan-4.1`（官方 test.pep PASS）|
| netMHCpan-4.0 | pTuneos scoring | （pTuneos 镜像内置）| ✅ **镜像自带** `bm2lab/ptuneos:v2.1` 内 `/root/software/netMHCpan-4.0`，免单独申请 |
| **netMHCpan-2.8** | netMHCstabpan 的后端（必需）| DTU services.healthtech.dtu.dk/services/NetMHCpan-2.8/ | ✅ **HPC 跑通** `ext_tools/netMHCpan-2.8`（el8 原生跑，test.pep 11 行；WSL2 曾 segfault → 已挪 HPC 解决）|
| netMHCstabpan-1.0 | IMPROVE 的 HLA 稳定性 | DTU Health Tech | ⚠️ **HPC glibc 挡**：二进制需 GLIBC_2.29，HPC el8 仅 2.28 → 需新 glibc 容器。**仅 IMPROVE feature_calc 的 Stability 特征用它，Predict 步与 benchmark 不受影响** |
| PRIME | IMPROVE 的 TCR 识别分 | Gfeller lab github.com/GfellerLab/PRIME（学术免费）| ✅ **已 clone** HPC `tools_repos/PRIME` |
| MixMHCpred | IMPROVE / PRIME 依赖 | Gfeller lab github.com/GfellerLab/MixMHCpred（学术免费）| ✅ **已 clone** HPC `tools_repos/MixMHCpred` |
| self_similarity | IMPROVE 的 Self-similarity 特征 | github.com/SRHgroup/self_similarity | ✅ **已 clone** HPC `tools_repos/self_similarity` |

> ⚠️ **benchmark 发布限制**：netMHCpan/netMHCstabpan 学术许可第 7(v)/10 条 —— 未经 DTU 书面同意不得向第三方发布在其软件上跑的 benchmark 结果。本项目是 benchmark → 论文/对外报告含 netMHCpan 对比数字前需取 DTU 书面同意（投稿阶段处理）。
> DTU 工具 = Linux 二进制，装 WSL2 `~/quantimmu/ext_tools/`。net 工具脚本是 tcsh（已 `apt install tcsh`）。

---

## 袁老师输入数据（第二阶段）
- 状态：未到（datasets.json `yuan_input_data` status=todo）。
- 到位后：按各工具输入格式写格式转换脚本（`scripts/`）→ 正式跑 → 补真实输出到 TOOLS md。

---

## 第二批 5 工具（Wave 3，原李紫晨负责，现并入余嘉测试）

> 2026-06-24 调研建档完成（5 researcher 并行查官方 repo/paper/依赖/输入输出/许可）。本轮**只到第 1 步（建档）+ 可行性判定**，未部署。逐工具 4 类信息见 `TOOLS/<tool>.md`，论文/许可见 `REFERENCES.md`/`PROVENANCE.md`。

### 状态总表

| 工具 | clone | 环境 | 权重 | example 烟测 | 4类信息 | 状态 | 阻塞 |
|---|---|---|---|---|---|---|---|
| PRIME | ✅ | ✅ `envs/prime` | ✅(随repo) | ✅ **r=1.0** | ✅ | **SMOKE_PASS** | 无（PRIME2.1+MixMHCpred3.0 跑通，147 行对账官方 diff=0）|
| ImmuneApp | ✅(tarball) | ✅ `envs/immuneapp` | ✅随repo | ✅ | ✅ | **SMOKE_PASS** | 无（HPC py3.7+TF1.15.0 跑通，出 Immunogenicity_score；坑=staged 装 TF 防 pip 回溯）|
| deepHLApan | ✅(Docker镜像) | ✅(镜像内) | ✅ | ✅ | ✅ | **SMOKE_PASS** | 无（本机 WSL2 docker `biopharm/deephlapan:v1.1` 跑通 binding+immuno 双分；坑=outdir 须先建）|
| HLAthena | ✅(Docker镜像) | ✅(镜像内) | ✅(匿名下136M) | ✅ | ✅ | **SMOKE_PASS(proxy)** | GCS 死锁绕过(匿名下模型+patch fetch_models=false 挂载)。出 MSi 提呈分。⚠️ 仅 presentation proxy；全量 benchmark 需下全65allele模型~6.5G+R慢,未跑 |
| MHLAPre | ✅(15M) | ☐ | ❌缺 | ❌ | ✅ | **阻塞·不可复现** | 🔴 无权重 + ProcessData npy 缺 + **预处理管线代码也缺**（Pretreatment.py 无 main、生成 hla_epit_cdr3.npy 的拼装码被注释）→ 自训路也不通。全网(GitHub/Kaggle/Zenodo/HF)搜权重空。唯一路=邮件作者(23B903048@stu.hit.edu.cn)。已摸清列名 |

### 部署排序（易→难）
**PRIME（最易，已半 clone）→ ImmuneApp → deepHLApan → HLAthena(proxy) → MHLAPre（权重阻塞，末位）**

### ⚠️ 两个可行性红旗（部署前必读，防踩坑）
1. **HLAthena 不是免疫原性工具**：预测 MHC-I 提呈（presentation），论文明确不预测免疫原性；独立 benchmark ELISpot AUC~0.6、PPV 0.3063 近随机。→ 进 benchmark **只能当 presentation baseline proxy，须标注层次不同，不与 PRIME/deepHLApan/ImmuneApp/MHLAPre 等免疫原性工具 apples-to-apples 并列**。
2. **MHLAPre 权重缺**：README 称权重+训练数据太大未上传，需邮件作者（23B903048@stu.hit.edu.cn）；且 repo 无 LICENSE、CUDA10.2 旧、IEDB 训练数据与 ELISpot benchmark 可能 overlap（数据泄露）。→ 部署前置阻塞，可能要权重或重训。

### 共性观察
- 这 5 个里 4 个（PRIME/deepHLApan/ImmuneApp/MHLAPre）有免疫原性连续输出，**理论可进 ELISpot benchmark**（HLAthena 仅 proxy）。
- 4 个有 HLA 格式差异需预处理（deepHLApan 无星号 `HLA-A01:01`，others `HLA-A*01:01`），肽长限制各异（PRIME 8-14 / 其余多 8-15），benchmark 喂数据时按各自格式转换。
- **多数训练数据含 IEDB → 与 ELISpot benchmark 测试集 overlap 风险普遍**，正式 benchmark 前需统一排重（与第一批同此 caveat）。
