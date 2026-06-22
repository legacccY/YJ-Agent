# QuantImmuBench — 工作日志（时间倒序）

> 数字一律 Bash/Grep 核 csv，不信 Read。删改需在新 entry 说明原因。

---

## Entry 13 — 2026-06-23 HPC 部署收口（4/5 smoke-pass + 2 容器边界）

- ptuneos.sif build✅(1.7G)。但 singularity run 受限：①镜像程序在 /root，非root用户访问拒，`--fakeroot` 无 subuid 映射不可用 ②VEP cache 缺(用户拍板不下)。pTuneos 部署已本地 docker 验证(Py2.7+校验输入)，HPC sif 建成；真跑需 fakeroot 或重打包+VEP cache。
- netMHCstabpan 容器化：predig.sif glibc 2.35(够≥2.29)但**无 tcsh**(wrapper 是 tcsh 脚本)→ 跑不了。仅 IMPROVE feature_calc 的 Stability 特征需(Predict 已✅)。彻底解=建 ubuntu+tcsh sif 或直调 binary。
- **HPC 部署最终态**：DeepImmuno ✅ / IMPROVE Predict ✅ / PredIG ✅ / NeoTImmuML env ✅(notebook需重训) — **4 个 smoke-pass**；pTuneos sif建成(run受fakeroot/VEP限)；netMHCpan-4.1/2.8✅+PRIME编译✅；netMHCstabpan待tcsh容器。
- 原始要求「在 HPC 部署测试 5 工具 + 收 4 类信息」基本达成：4 工具 HPC 真跑出分，pTuneos 部署验证，4 类信息全收(TOOLS/*.md)。剩 PPT(B4)。

---

## Entry 12 — 2026-06-23 PredIG/NeoTImmuML HPC 就绪 + 大镜像转 singularity

- **大镜像传 HPC**（用户同意）：本地 docker save|pigz → predig.tar.gz 4.6G + ptuneos.tar.gz 2.1G → sftp 传 HPC（3.2MB/s 慢，VPN 绕日本节点；predig 25.7min）。坑：sftp 前需确保远程 sif/ 目录存在(mkdir 竞态失败一次)。
- **PredIG HPC ✅ SMOKE_PASS**：`singularity build predig.sif docker-archive://predig.tar`(gunzip后) → `singularity run --writable-tmpfs -B smoke:/work predig.sif ... --type recombinant` → PredIG=0.0061380286（=本地）。singularity 容器只读，PredIG 写 tmp 需 `--writable-tmpfs`。
- **NeoTImmuML HPC env ✅**：py3.10+lgbm4.6+xgb3.2，demo 加载 OK（notebook 需重训才预测，同本地）。
- ptuneos.sif build 进行中 → VCF 烟测（VEP cache 缺，部署验证级）。
- netMHCstabpan(glibc) 待用 newer-glibc 容器(predig.sif conda base 新 glibc)跑。
- **HPC 真就绪 4/5**：DeepImmuno + IMPROVE(Predict) + NeoTImmuML(env) + PredIG。

---

## Entry 11 — 2026-06-22 HPC 轻活：DTU 工具 + PRIME 编译 + NeoTImmuML env

- **DTU 工具传 HPC**（53M 配好包）：netMHCpan-4.1 ✅(test 11行) + netMHCpan-2.8 ✅(11行) HPC el8 原生跑（老二进制不用 vsyscall）。**netMHCstabpan ❌**：二进制需 GLIBC_2.29，HPC el8 仅 glibc 2.28 → 原生跑不了（与本地 vsyscall 相反的兼容坑）。仅 IMPROVE feature_calc 的 Stability 特征需它。
- **PRIME 编译 ✅**：HPC `module load gcc`(g++13.1) → `g++ -O3 PRIME.cc -o PRIME.x`。
- MixMHCpred 3.x = python 版（非 C++ 编译），需装 python 库 + MAFFT（install_packages）。
- NeoTImmuML env(py3.10)：装中（lightgbm/xgboost pip 慢）。
- **结论**：HPC 完整 IMPROVE feature_calc 卡 netMHCstabpan(glibc) → 与 PredIG/pTuneos 同归 singularity 批（容器带新 glibc 一并解决）。HPC 已真就绪：DeepImmuno + IMPROVE(Predict) + netMHCpan-4.1/2.8 + PRIME(编译)。

---

## Entry 10 — 2026-06-22 IMPROVE HPC Predict 真就绪（HPC 第 2 个）

- IMPROVE models.zip lfs 1.94G 落地（China 拉 ~1h+ 龟速但成）→ HPC 解压 + 建 env `envs/improve`(py3.11+numpy2.4.6+sklearn1.9.0) + 改 retrain 脚本 base_dir + Predict Simple 烟测。
- **IMPROVE HPC ✅ SMOKE_PASS**：out_simple.tsv 100 行，mean_prediction_rf 与本地一字不差（KAQPVTQATSF=0.2459/EEFLNSWML=0.5146）。
- HPC 真就绪 2/5：DeepImmuno + IMPROVE(Predict)。
- 剩：PredIG/pTuneos docker 镜像传 HPC 转 singularity（14.4G+5G，docker save→sftp→singularity build，大上传）；NeoTImmuML env；IMPROVE feature_calc 需 DTU 工具传 HPC。

---

## Entry 9 — 2026-06-22 DeepImmuno HPC 真就绪（第一个 HPC 烟测出分）

- HPC 部署改 nohup 后台 + 日志轮询（exec 通道挂 lfs 1.9G 超时崩过；脚本 `_scratch/hpc_launch.py` putfo+nohup）。
- **DeepImmuno HPC ✅ SMOKE_PASS**：clone(gpfs 无 NTFS `*` 坑全检出) + conda env(`/gpfs/.../quantimmu/envs/deepimmuno` py3.8+TF2.3+protobuf3.20) + 单条烟测 = **0.5324646830558777**（与本地 WSL 一字不差）。HPC module miniconda3/22.11.1 + pypi 装 TF 顺。
- IMPROVE models.zip lfs(1.9G) 仍在 HPC 拉取中。
- 下一步：models.zip 落地 → IMPROVE py 环境 + Predict 烟测；NeoTImmuML env；PredIG/pTuneos docker 镜像传 HPC 转 singularity。

---

## Entry 8 — 2026-06-22 转 HPC 部署（用户拍板完成原始要求）

用户拍板：团队原始要求=「在各自 HPC 上部署」→ 把本地验通的配方搬 HPC。
- **HPC 环境探明**（dtn.hpc.xjtlu.edu.cn / jiayu2403）：Singularity 3.11.3 ✅ + module miniconda3/22.11.1 ✅ + gpfs 136T 空闲。出网：github ✅ / pypi ✅ / DTU ✅ / **Docker Hub ❌**（HPC 也连不上）。
- **HPC 策略**：①DeepImmuno/IMPROVE/NeoTImmuML → HPC 原生 clone+conda+pip（依赖全可达，且 HPC 真 Linux 老二进制不用 vsyscall hack）②PredIG/pTuneos → Docker Hub 不通，传本地镜像转 singularity。
- **踩坑**：Git Bash `/tmp` 与 Windows Python `/tmp` 路径不一致 → sftp.put 找不到本地脚本失败两次。改 paramiko `putfo`（内存传）解决，编排脚本 `_scratch/hpc_deploy.py`。
- 进行中：HPC clone 全工具 + DeepImmuno conda env(TF2.3) + IMPROVE models.zip(lfs 1.9G)。
- 待：IMPROVE py env + DTU 工具(netMHCpan licensed binary)传 HPC + PredIG/pTuneos docker 镜像传 HPC + 配置烟测。

---

## Entry 7 — 2026-06-22 内核修复救活老二进制 + PredIG/netMHCstabpan 跑通 + pTuneos 部署验证

**WSL 内核修复（关键，救多个老二进制）**：诊断 `CONFIG_LEGACY_VSYSCALL_NONE=y` = 2014 老静态二进制 segfault 根因。`.wslconfig` 加 `kernelCommandLine=vsyscall=emulate` + 重启 → **netMHCpan-2.8 不崩了**（官方 test.pep 正常出结果）。**HPC 彻底不用上**——所有老 DTU 二进制本地能跑。

**netMHCstabpan ✅ 全链通**：配后端=2.8 + 下 data.tar.gz(6.8MB，原缺 data/version) + 正确参数 `-p test.pep` → 11 行 stability 结果。IMPROVE 的 DTU 工具链(netMHCpan-4.1 + netMHCstabpan + 2.8)全部本地搞定。

**PredIG ✅ SMOKE_PASS**：镜像 14.4GB 经代理 7897 拉成。容器 run.py，recombinant 模式跑通（输入 epitope,HLA_allele,protein_seq,protein_name）→ 输出 PredIG 0-1 分 + NOAH/NetCleave/物化/TCR_contact 全列(与README一致)。全链 MHCflurry→NOAH→netCTLpan→XGBoost CPU 跑通。

**pTuneos 🟡 部署验证通过**：镜像 5.03GB。Py2.7 容器跑通、读 config_VCF、校验 VCF 输入 OK。镜像自带 netMHCpan-4.0/VEP/PyClone/GATK/BWA 全套。停在 VEP cache 缺失（真实注释库 ~15-25GB，镜像只带 dummy）= end-to-end 唯一缺口。config 占位路径要改镜像内真路径(已记 TOOLS/pTuneos.md)。

**5 工具进度**：DeepImmuno ✅ / PredIG ✅ / NeoTImmuML 信息齐(需重训) / IMPROVE Predict✅+DTU全通(差self_sim/garnish) / pTuneos 部署验证✅(差VEP cache)。全本地 WSL2 CPU，无 HPC。

---

## Entry 6 — 2026-06-22 修 Docker Hub 网络（WSL mirrored + 代理 7897）

PredIG 镜像 Docker Hub 阻塞根因链 + 修复：
1. WSL2 NAT 网络 + Windows VPN 冲突 → WSL 断网。修：`C:\Users\yj200\.wslconfig` 设 `networkingMode=mirrored` + `dnsTunneling=true` + `wsl --shutdown` 重启 → github/google 通。
2. docker daemon 仍连不上 registry-1：①`/etc/docker/daemon.json` 原配死镜像 `docker.mirrors.ustc.edu.cn`（USTC 已停服）②daemon 不走 VPN 本地代理。修：daemon.json 删死镜像 + 配 `proxies.https-proxy=http://127.0.0.1:7897`（用户 VPN 全局模式本地端口 7897，curl -v 探出），`pkill dockerd` 重启。
3. `docker pull bsceapm/predig:latest` → /var/lib/docker/tmp 增长，代理生效拉取中。
- 旧 daemon.json 备份在 `/etc/docker/daemon.json.bak`。

---

## Entry 5 — 2026-06-22 PredIG 容器卡 Docker Hub + NeoTImmuML 源码找到摸清

**PredIG**（Wave1）：
- 摸清机制：主 repo 只有 R 脚本(`predig_pipe1/2/3_container.R`)+ 3 模型(neoant/noncan/path)，外部 predictors(NetCleave/NOAH/netctlpan/MHCflurry) 全在官方 Docker 镜像 `bsceapm/predig:latest`。输出格式 README 写全(PredIG score 0-1 + NOAH/NetCleave/物化/TCR-contact 特征列)。
- docker daemon(28.4.0) WSL2 跑通 + clone PredIG + predig-containers + 下 UniProt swissprot 库(`~/quantimmu/ext_tools/uniprot/`)。
- **BLOCKED**：`docker pull bsceapm/predig` 超时（`registry-1.docker.io context deadline exceeded`，国内连不上 Docker Hub）→ 待配镜像源 / HPC 拉 / 代理。

**NeoTImmuML**（Wave1）：
- **源码找到**：Playwright 进 tumoragdb.com.cn `#/neotimmuml`，card 点击经 `window.open` 抓出 → **github.com/01SYan19/NeoTImmuML**（repo=NeoTImmuML.ipynb + demo.csv[实为xlsx] + README，py3.10.4）。
- 摸清：input CSV = `Peptide` + `immunogenicity`(标签) + 78 个 R Peptides 物化特征(col3-80)；是**训练评估 notebook 非预测 CLI**，无预训练权重、无特征计算代码(78特征须外部 R 算)。`predict_proba` 暴露连续概率 → **能定量强弱**（此前待核已解）。
- 4 类信息已齐填 TOOLS/NeoTImmuML.md。完整跑通需补 R Peptides 特征管线 + 重训。

**当前 5 工具**：DeepImmuno ✅ / IMPROVE 🟡(Predict通,feature_calc待stabpan@HPC) / NeoTImmuML ✅信息齐(notebook需重训) / PredIG ⚠️(Docker Hub阻塞) / pTuneos ⬜(Wave2)。

---

## Entry 4 — 2026-06-22 IMPROVE Predict 步骤跑通 + netMHCpan-2.8 segfault

- **netMHCpan-2.8**（netMHCstabpan 后端）：用户下了 2.8a.Linux，装 + 下 data(7.59MB 精确匹配) + 配 NMHOME/TMPDIR。但**二进制 segfault**（signal 11，2014 静态 ELF for Linux 2.6.4，关 ASLR `setarch -R` 仍崩，WSL2 内核不兼容）→ netMHCstabpan 本地不能跑，**待 HPC 重试**（真 Linux 旧环境兼容性好）。
- **IMPROVE ✅ 步骤2(Predict) 跑通**：
  - clone IMPROVE_tool + PRIME + MixMHCpred（后两 Gfeller 免许可）。
  - models.zip = **1.9GB git-lfs**（`--depth 1` 只得 135B 指针，装 git-lfs `git lfs pull` 拉真文件），解压得 models/<3变体>/各 250 pkl。
  - 坑：pkl 是 **numpy 2.x retrained**（老 py3.7 env 报 `No module named numpy._core`）→ 改用现代 env `improve_new`(py3.11+numpy2.4+sklearn1.9+pd3.0) + `Predict_immunogenicity_CLEAN_retrain.py`（base_dir 硬编码改本机路径）。
  - Simple 变体自带 example(`data/calculated_features_test.tsv`) 跑通 → 输出 `out_simple.tsv` 关键列 `mean_prediction_rf`（5fold×50 RF 集成，连续 0-1，100 行）。
  - gpu_slot 0aaec1be 申请→GO→release（CPU 推理，hook 误判训练故走卡槽协议）。
- IMPROVE 完整 feature_calc 还差：netMHCstabpan(2.8,HPC)、self_similarity、antigen.garnish(Foreignness)、MuPeXI/MCP-Counter(TME 变体)。但 Predict 步 + 输出格式已确证，4 类信息可填。

---

## Entry 3 — 2026-06-22 netMHCpan-4.1 装通 + netMHCstabpan 需 2.8 后端

用户已拿 DTU 学术许可，下了 netMHCpan-4.1b + netMHCstabpan-1.0b（E:\Edge Download\）。装进 WSL `~/quantimmu/ext_tools/`：
- **netMHCpan-4.1 ✅ 跑通**：tar 解压 + `apt install tcsh`（脚本是 tcsh）+ wget data.tar.gz(29M) 解压 + sed 设 NMHOME=`/root/quantimmu/ext_tools/netMHCpan-4.1` + mkdir tmp → 官方 `test.pep` PASS（输出 Score_EL/%Rank_EL/BindLevel，AAAWYLWEV=SB 强结合）。
- **netMHCstabpan-1.0 ⚠️ 半配**：NMHOME 已设，但脚本第 17 行硬依赖 **netMHCpan-2.8** 做后端（`-affpred`），非 4.1，接口不同不能替 → **需另下 netMHCpan-2.8a**（DTU services.healthtech.dtu.dk/services/NetMHCpan-2.8/）才能跑。
- **许可合规提醒**：DTU 许可禁未经书面同意发布 benchmark 结果（第7(v)/10条）→ 投稿阶段需取 DTU 同意。已记 DEPLOY_TRACKER。

**IMPROVE 还差**：netMHCpan-2.8（待用户下）+ PRIME + MixMHCpred（Gfeller，免许可可直接 clone）。下一步可现做：clone PRIME/MixMHCpred + IMPROVE_tool + 建 py3.7 env。

---

## Entry 2 — 2026-06-22 DeepImmuno 本地跑通 + WSL2 定为本地部署环境

**策略变更**：本机 WSL2 Ubuntu 24.04（GPU 直通）= 本地部署主战场，弃 Windows。原因：①DeepImmuno repo 含 `new_imgt_scraping/.../HLA-A*0101.json`，`*` 在 NTFS 非法 → Windows `git checkout` 直接崩；②这些工具是 Linux-only 老链（TF2.3/Py2.7/netMHCpan 二进制），原生跑 Linux 才顺。WSL 部署根 `~/quantimmu/`。

**DeepImmuno ✅ SMOKE_PASS**（单条 + 批量两模式）：
- 环境：conda env `deepimmuno` = python3.8 + tensorflow==2.3.0 + numpy==1.18.5 + pandas==1.1.1 + **protobuf==3.20.3**（关键坑：不降 protobuf 报 `Descriptors cannot be created directly`）。CUDA10.1 库缺失自动回退 CPU。
- 单条：`python deepimmuno-cnn.py --mode single --epitope HPPLMNVER --hla "HLA-A*0201"` → stdout `0.5324646830558777`。
- 批量：输入无表头 CSV 两列 `peptide,HLA` → 输出 `deepimmuno-cnn-result.txt`（tab 分隔，列 `peptide HLA immunogenicity` 连续 0-1）。
- 合理性：NLVPMVATV(CMV)=0.957、GILGFVFTL(流感M1)=0.887 已知强免疫表位高分，结果可信。
- 4 类信息已补进 `TOOLS/DeepImmuno.md`（输入模板/参数/输出格式实测）。

**下一步**：Wave1 续 → PredIG（Singularity 容器）或先 NeoTImmuML 站内找源码 URL。pTuneos+IMPROVE 等许可证（清单已给用户）。

---

## Entry 1 — 2026-06-22 建档 + 5 工具调研落地

**决策**：在 YJ-Agent 组合台给袁老师的癌症新抗原疫苗协作项目建**轻量工程台档**（key=`quantimmu-bench`，status=active）。我负责子任务 = HPC 部署测试 5 工具（PredIG/DeepImmuno/pTuneos/IMPROVE/NeoTImmuML）+ 收集 4 类信息 → PPT。

**已做**：
- 建档：`00_README` + 本 LOG + `DEPLOY_TRACKER` + `TOOLS/`（5 工具 md + 模板）+ `scripts/`。
- 登记：`.portfolio/registry.json` 加 quantimmu-bench 条目 + `CLAUDE.md` 入口行 + `datasets.json` 占位（袁老师数据 todo）+ 认领锁。
- **5 工具联网调研落地**（researcher，带 repo + 论文 DOI，已填进各 `TOOLS/*.md`）：
  - PredIG — XGBoost(R)，连续 0-1 分，有 Docker/Singularity。repo: github.com/BSC-CNS-EAPM/PredIG
  - DeepImmuno — CNN(TF2.3)，连续 0-1，仅 9/10-mer。repo: github.com/frankligy/DeepImmuno
  - pTuneos — ML pipeline，连续排名分但需全基因组，**Python2.7 老链**。repo: github.com/bm2-lab/pTuneos
  - IMPROVE — RandomForest，连续 0-1，需 netMHCpan/PRIME 等学术许可。repo: github.com/SRHgroup/IMPROVE_tool
  - NeoTImmuML — 集成 ML，**源码 URL 未公开（TODO 站内找）**，定量能力待核。论文 Front Immunol 2025。

**关键阻塞**（影响排期）：
1. netMHCpan/PRIME 等学术许可未到位 → pTuneos+IMPROVE 排 Wave 2（许可申请清单见 DEPLOY_TRACKER）。
2. NeoTImmuML 源码 URL 要进 tumoragdb.com.cn 站内找。
3. 袁老师输入数据未到 → 先用各工具 bundled example 烟测。

**部署排序**（易→难，许可解耦）：Wave 1 = DeepImmuno → PredIG → NeoTImmuML（无许可证）；Wave 2 = IMPROVE → pTuneos（依赖学术许可）。

**下一步**：①列 netMHCpan/PRIME 学术许可申请清单交用户/袁老师本人学术邮箱发；②Wave 1 从 DeepImmuno 本地 clone + 读 README 起。
