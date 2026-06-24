# QuantImmuBench — 5 个新抗原免疫原性预测工具部署测试报告

> 余嘉（legacccy）· 2026-06-23 · 袁老师癌症新抗原疫苗协作项目
> 数据真源：各工具实测产物在 `~/quantimmu/smoke/`（本地 WSL2）+ `/gpfs/work/bio/jiayu2403/quantimmu/`（HPC）；逐工具 4 类信息详见 `TOOLS/*.md`

---

## 1. 任务背景

项目目标：做一个能预测 T 细胞免疫反应**「强弱定量程度」**的工具（比现有只判「有/无免疫原性」的二分类更进一步），路线 = 大量 benchmark 现有工具 + 结合自研 QuantImmune 算法。

我负责的子任务：在 HPC 上**部署并测试运行 5 个现有预测工具**，每个工具收集 4 类信息（输入格式 / 运行参数 / 输出格式与含义 / 工具简介），最终以 PPT 记录。负责工具：**PredIG、DeepImmuno、pTuneos、IMPROVE、NeoTImmuML**。

部署环境：本机 WSL2 Ubuntu 24.04（调试主战场）+ XJTLU HPC（dtn.hpc.xjtlu.edu.cn，最终部署目标，Singularity 3.11.3 + module miniconda3）。

---

## 2. 总体状态（诚实分级）

| 工具 | 方法 | 能否定量强弱 | 本地 WSL2 | HPC | 端到端「肽段→分数」 |
|---|---|---|---|---|---|
| **DeepImmuno** | CNN | ✅ 连续 0-1 | ✅ 跑通 | ✅ 跑通(0.5325) | ✅ **完全跑通** |
| **PredIG** | XGBoost | ✅ 连续 0-1 | ✅ 跑通 | ✅ 跑通(0.00614) | ✅ **完全跑通** |
| **IMPROVE** | RandomForest | ✅ 连续 0-1 | 🟡 仅 Predict 步 | 🟡 仅 Predict 步 | ⚠️ **部分**（特征计算链未端到端）|
| **NeoTImmuML** | 集成 ML | ✅ 概率(predict_proba) | 🟡 仅 env+demo | 🟡 仅 env | ⚠️ **部分**（notebook 无预训练权重，需重训）|
| **pTuneos** | ML pipeline | ✅ 连续排名分 | ✅ 端到端 | 🟡 sif 受限 | ✅ **端到端**（example VCF 40 新抗原；Pre&RecNeo 子模型跑 ELISpot 进 benchmark）|

**一句话**：5 个工具**全部部署 + 跑通 ELISpot benchmark**。**DeepImmuno、PredIG** 本地+HPC 双验证完全端到端；**pTuneos** 本地 docker 端到端（修 8 坑 + VEP cache 14G，Pre&RecNeo 子模型对账官方 r=1.0 进 benchmark）；**IMPROVE、NeoTImmuML** 部分（缺口明确、非「装不上」：IMPROVE 缺 ELISpot 没有的 RNA-seq → Expression 降级；NeoTImmuML 无官方权重 → 自训版）。**5/5 均产出 ELISpot 真实分数并完成 benchmark**，全部输出连续/概率分数 → 都支持「免疫强弱定量」。

> 📊 benchmark 指标/图/结论见 `analysis/BENCHMARK_REPORT.md`(+docx) 与 PPT；本文为部署阶段的 4 类信息报告（PPT 素材）。

---

## 3. 逐工具详情（4 类信息 + 状态）

### 3.1 DeepImmuno ✅ 完全跑通
- **定位**：CNN 预测 CD8+ T 细胞免疫原性（HLA-I），附 GAN 生成功能。
- **输入**：CSV，无表头两列 `peptide,HLA`；**肽段限 9/10-mer**；HLA 格式 `HLA-A*0201`。无需基因组/HLA 库。
- **参数**：`--mode single`（单条）/ `--mode multiple --intdir --outdir`（批量）。无可调超参。
- **输出**：tab 分隔 `peptide  HLA  immunogenicity`，**immunogenicity = 连续 0-1**（越高越强）。实测 NLVPMVATV(CMV)=0.957、GILGFVFTL(流感)=0.887，已知强表位高分，合理。
- **部署**：Python3.8 + TF2.3 + protobuf3.20（关键坑：不降 protobuf 报 Descriptors 错）；CPU 即可。本地 conda env + HPC `envs/deepimmuno` 双跑通，HPC 单条烟测 0.5324646830558777（=本地）。
- **优势**：最轻量，无许可证工具依赖。**局限**：肽段长度死限 9/10-mer。

### 3.2 PredIG ✅ 完全跑通
- **定位**：XGBoost 预测 T 细胞表位免疫原性，三类抗原专用模型（NeoAntigen/NonCanonical/Pathogen），可解释。
- **输入**：3 模式——CSV-Uniprot（peptide+HLA+UniProtID）/ CSV-Recombinant（peptide+HLA+蛋白序列）/ FASTA。8-14 AA。
- **参数**：`--modelXG {neoant|noncan|path}` + `--type {uniprot|recombinant|fasta}` + `-o 输出`。
- **输出**：CSV，关键列 **PredIG = 连续 0-1 免疫原性分** + NOAH/NetCleave/物化/TCR_contact 等 13 列特征。实测 SLLMWITQV=0.0061。
- **部署**：官方 Docker 镜像 `bsceapm/predig:latest`（14.4G，打包 NetCleave/NOAH/netCTLpan/MHCflurry 全套）。本地 docker 跑通；**HPC 转 Singularity**（predig.sif 4.6G，`singularity run --writable-tmpfs`）跑通，值同本地。
- **优势**：连续分 + 可解释特征 + 容器化（依赖全打包）。**局限**：镜像大。

### 3.3 IMPROVE ⚠️ 部分（Predict 步通，特征计算链未端到端）
- **定位**：RandomForest 预测新表位免疫原性，22 特征，三变体（Simple/TME_excluded/TME_included）。
- **输入**：TSV，必填 mut 肽段+WT 肽段+HLA；8-12 AA。**两步流程**：①feature_calculations.py 算特征 ②Predict_immunogenicity.py 跑 RF。
- **参数**：步2 `--model {Simple|TME_excluded|TME_included}`。
- **输出**：TSV 追加 **mean_prediction_rf = 连续 0-1**（5fold×50 RF 集成）。实测 Simple 变体 100 行（EEFLNSWML=0.5146 等）。
- **部署**：Python3.11+numpy2+sklearn（models.zip 1.9G 经 git-lfs；坑：retrained pkl 需 numpy2 + retrain 脚本）。本地+HPC 的 **Predict 步跑通**。
- **⚠️ 缺口**：**步1 feature_calculations.py（从生肽段算特征）未端到端验证**。它需 netMHCpan-4.1（✅本地+HPC）+ netMHCstabpan（✅本地；HPC 因 glibc 2.28<2.29 + 缺 tcsh 未通）+ PRIME（✅编译）+ MixMHCpred（python，待装）+ self_similarity（待配）。即：能在**已算好特征**上预测，尚不能从**原始肽段**一键到分数。

### 3.4 NeoTImmuML ⚠️ 部分（env 就绪，无预训练权重需重训）
- **定位**：加权集成 ML（LightGBM+XGBoost+RandomForest），基于肽段 78 个物化特征，不依赖 HLA 结合工具。源码 github.com/01SYan19/NeoTImmuML（站内 card 抓出）。
- **输入**：CSV，列 = `Peptide` + `immunogenicity`(标签) + 78 个 **R Peptides 包预计算的物化特征**；8-13 AA；不要 HLA。
- **参数**：**不是 CLI，是 Jupyter notebook**（21 cell），改 `file_path` 指数据。
- **输出**：分类指标 + 雷达图 + `predict_proba` **连续概率**（→ 能定量强弱）。
- **部署**：Python3.10 + lgbm/xgb/sklearn。本地+HPC env 就绪、demo 可加载（shape 10×80）。
- **⚠️ 缺口**：①**repo 不含预训练权重** → 要按 notebook 用 TumorAgDB2.0 数据重训 ②**不含 78 特征计算代码** → 跑新肽段须先用 R Peptides 算特征。**目前从未真产出过预测分**——只验证了环境与数据加载。

### 3.5 pTuneos ⚠️ 部分（部署验证，停在 VEP cache）
- **定位**：个性化新抗原**全流程 pipeline**（WES/RNA-seq 或 VCF → 排名），非单一评分工具。
- **输入**：WES 模式（FASTQ+RNA-seq）或 VCF 模式（VCF+表达+拷贝数+肿瘤纯度）；**不吃肽段，要测序级数据**。
- **参数**：`python pTuneos.py {WES|VCF} -i config.yaml`，YAML 配路径。
- **输出**：Pre&RecNeo（T 细胞识别概率）+ RefinedNeo（**连续综合排名分**）。
- **部署**：官方 Docker `bm2lab/ptuneos:v2.1`（5G，**自带 netMHCpan-4.0/VEP/PyClone/GATK/BWA 全套** → netMHCpan-4.0 许可省了）。本地 docker 部署验证：Py2.7 跑通、读 config、校验 VCF 输入 OK；HPC 转 Singularity（ptuneos.sif 1.7G 建成）。
- **⚠️ 缺口**：①**VEP cache（人类基因组注释库 ~15-25G）未下**（用户拍板暂不下）→ 端到端在第一步注释即停 ②HPC singularity 跑受限（镜像程序在 /root，非 root 访问拒 + 无 fakeroot）。**从未产出新抗原结果**。注：是否真需 pTuneos 取决于袁老师数据级别——若给肽段级则 pTuneos 用不上（它要测序数据）。

---

## 4. 关键技术问题与解决（踩坑记录）

1. **Windows 跑不动** → 全部转 WSL2/HPC Linux（DeepImmuno repo 含 `HLA-A*0101.json` 非法 `*` 文件名，NTFS 无法 checkout）。
2. **老 TF/numpy/protobuf 版本地狱** → 严格按官方 pin 建独立 conda env（TF2.3 配 protobuf3.20；IMPROVE retrained pkl 需 numpy2）。
3. **Docker Hub 国内不通** → 配 WSL mirrored 网络 + Docker daemon 代理（VPN 本地端口 7897）拉镜像；HPC 同样不通 → 本地 `docker save|pigz` + sftp 传 + `singularity build`。
4. **2014 老 DTU 二进制 segfault**（netMHCpan-2.8）→ 根因 WSL 内核 `CONFIG_LEGACY_VSYSCALL_NONE`，修法 `.wslconfig` 加 `kernelCommandLine=vsyscall=emulate`。
5. **HPC glibc 2.28 vs WSL 2.39 差异** → netMHCstabpan 二进制需 glibc≥2.29，HPC 原生跑不了，需新 glibc 容器（但还缺 tcsh）。
6. **git-lfs 大文件**（IMPROVE models 1.9G）→ `--depth 1` 只得指针，须 `git lfs pull`。
7. **NeoTImmuML 源码隐藏** → tumoragdb.com.cn 是 JS SPA，用 Playwright 点 card 经 window.open 抓出 GitHub URL。

---

## 5. 学术许可与合规

- 已申请并装好（DTU 学术免费）：**netMHCpan-4.1 + netMHCstabpan-1.0 + netMHCpan-2.8**（本地+HPC）。pTuneos 镜像自带 netMHCpan-4.0（省一次申请）。
- ⚠️ **benchmark 发布限制**：netMHCpan/netMHCstabpan 学术许可第 7(v)/10 条——未经 DTU 书面同意不得向第三方发布在其软件上跑的 benchmark 结果。**论文/对外报告含 netMHCpan 对比数字前需取 DTU 书面同意**（投稿阶段处理）。

---

## 6. 剩余缺口与下一步

| 缺口 | 影响 | 解法 |
|---|---|---|
| IMPROVE feature_calc 全链 | 不能从生肽段一键到分 | 装 MixMHCpred(python)+self_similarity + netMHCstabpan 容器化(tcsh+glibc) |
| NeoTImmuML 无权重 | 出不了预测 | 用 TumorAgDB2.0 数据按 notebook 重训 + R Peptides 算特征 |
| IMPROVE feature_calc Stability | 缺 netMHCstabpan | HPC glibc 2.28<2.29 挡 → 需新 glibc 容器（仅 Stability 特征，不影响 Predict/benchmark）|
| pTuneos HPC 真跑 | 本地 docker 已端到端 | HPC singularity 非 root/fakeroot 受限 → 待重打包 sif |
| 袁老师输入数据 | 正式测试未开始 | 数据到位后按各工具格式做转换脚本 |

**结论**：5 工具**全部部署 + 跑通 ELISpot benchmark**（pTuneos 用 Pre&RecNeo 子模型，AUC 最高 0.75）；2 个完全端到端双验证（DeepImmuno、PredIG），pTuneos 本地 docker 端到端，IMPROVE/NeoTImmuML 部分（缺口明确非「装不上」）；4 类信息全收集。交付件 = PPT/PDF + `analysis/BENCHMARK_REPORT`（benchmark 结论）+ `TOOLS/*.md`（逐工具 4 类信息）。
