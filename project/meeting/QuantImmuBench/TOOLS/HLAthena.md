# HLAthena — 信息收集卡（PPT 素材）

> 第二批 5 工具（Wave 3，原李紫晨负责，现并入余嘉测试）。事实来自官方论文 + web/Docker，实测项标 TODO。
> ⚠️⚠️ **可行性红旗**：HLAthena 预测 **MHC-I 提呈（presentation）不是免疫原性**。论文原文明确「不预测 HLA-presented peptides 能否与 TCR 互作，该问题 remains unsolved」。独立 benchmark 上 ELISpot AUC ~0.6、PPV 0.3063（近随机）。**进 benchmark 只能当 presentation baseline proxy，须标注层次不同，不与免疫原性工具 apples-to-apples 并列。**

## 0. 定位 / 一句话
全连接神经网络（MS 质谱训练）预测内源肽被 HLA-I **提呈的概率**——presentation，非免疫原性。Broad Institute / Keskin-Wu lab。

## 1. 输入数据模板 / 格式
- 文件格式：tab 分隔（带 header）或 FASTA
- 必填列：`peptide`（氨基酸序列）
- 肽段长度限制：8 / 9 / 10 / 11-mer
- HLA 格式：TODO（官方文档未在检索中明确字符串格式，需查 hlathena.tools "Predict→How to"）
- 可选列（决定跑哪个模型）：`exists_ctex=true`+`ctex_up`/`ctex_dn`（上下游 30aa）→ MSiC；`exists_expr=true`+表达量(TPM)→ MSiCE
- 是否需基因组数据：非必须（不给只跑 MSi；给 RNA 表达提精度）
- **实测输入样例**：TODO

## 2. 运行参数设置
- 主要参数：选模型 MSi / MSiC / MSiCE / MSiCEB（取决于提供的可选列）
- **实测命令行**：TODO（Docker `ssarkizova/hlathena-external` 参数同 web server）

## 3. 输出数据格式 + 含义
- 输出列：`MSi`（仅肽序列）/ `MSiC`（+剪切位点上下文）/ `MSiCE`（+表达量）/ `MSiCEB`（+基因提呈偏好）
- 关键列含义：连续 presentation score，越高越可能被 HLA-I 提呈
- 分数类型：连续提呈概率（阈值参考 MSiC ≥0.95 strong / ≥0.90 normal / ≥0.80 weak，TODO 官方核实）
- **能否定量免疫强弱**：❌ **否**——是提呈概率分，不是免疫强弱分
- **实测输出样例**：TODO

## 4. 简介（特点 / 优势）
- 方法：全连接神经网络（1 隐藏层；allele-specific tanh hidden50 / pan-allele ReLU hidden250），MS immunopeptidome 训练
- 训练数据：单等位基因细胞系 LC-MS/MS 鉴定肽段（95 HLA alleles）
- 特点 / 优势：大规模 MS peptidome 训练、提呈预测覆盖人群广、不依赖 netMHCpan
- 局限：**只预测提呈不预测免疫原性**（核心 caveat）；无公开 GitHub（仅论文 Supplementary Code + Docker）；Docker 6 年未更；research-only

## 部署记录
- repo / 部署：**无公开 GitHub**；web server http://hlathena.tools （限 10000 肽/批）；Docker `ssarkizova/hlathena-external:dev`（~909MB，可本地/HPC）；Terra/FireCloud（大批次）
- 论文：*A large peptidome dataset improves HLA class I epitope prediction across most of the human population*, Nature Biotechnology 2020 (38:199–209), DOI 10.1038/s41587-019-0322-9（Sarkizova et al.）
- 语言 / 框架 / 依赖：Python（推断，需核 Docker 内部）；不依赖 netMHCpan
- 外部许可证工具：无已知
- GPU 需求：CPU 可（小网络）
- 部署状态：✅ **SMOKE_PASS（2026-06-24 本机 WSL2 docker，GCS 死锁已绕过）**。
- **关键坑+解（实测）**：镜像 standalone 运行时**从作者 GCS bucket `gs://msmodels` 现拉模型**（镜像内 /models 空），bundled `gcloud_key.json`（project decent-oxygen-195020）**已死**（`storage.buckets.get` 401）→ 卡 `retry_util.py Retrying request`。**突破**：bucket **对象匿名可下**（list API + 直链 `https://storage.googleapis.com/msmodels/<obj>` 通，只是 buckets.get 要权限）。解 = ①匿名下需要的模型（A0101.tar.gz + models_pan_pan_CV 15 文件 + linear/ecdf RDS，共 **136M**；⚠️ 别下整 `models_panpan/` 前缀——含 `ecdf/OLD_nmhc_mhcflurry_mixmhcpred/` 全 allele 57MB 文件会膨胀几百 GB）②布置 /models（A0101 解压+linear+ecdf）+ /models_panpan（CV+linear_pan_pan+ecdf）③`sed 's/fetch_models="true"/fetch_models="false"/'` patch `predict_docker.bash`（chmod +x）④docker 挂载本地模型+patched 脚本跑。
- example 烟测：`predict --runID x --rundir /work --peptides /pred/test/peps.txt --alleles A0101` → 出 `<id>-predictions.txt`（17 列含 `MSi_A0101` 提呈分、`prank.MSi`、`best.MSi_allele`）。例 `IDLLKEIY MSi=0.844`。
- **全量 ELISpot benchmark 未跑**：需下全 65 allele 的 specific 模型（每个 ~100M，约 6.5G）+ R 慢；HLAthena 仅 presentation proxy（预期近随机），ROI 低 → 暂停在 smoke-deployed。
- 许可：research purposes only（商用联系 Broad）；无显式开源协议

### TODO（researcher 标）
- HLA 格式字符串（hlathena.tools 文档核）
- 官方是否提供 .sif（HPC Singularity）/ Docker→Singularity 转换可行性
- 输出阈值是否官方标注
- Docker 镜像再分发是否允许（联系作者）
