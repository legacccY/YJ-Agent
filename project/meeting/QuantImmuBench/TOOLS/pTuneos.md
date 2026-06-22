# pTuneos — 信息收集卡（PPT 素材）

> Wave 2（最难，依赖学术许可 + 老环境 + 全基因组数据）。事实来自官方 repo + 论文。

## 0. 定位 / 一句话
个性化新抗原**全流程优先级排序 pipeline**——从原始 WES/RNA-seq 出发，5 个免疫原性特征构 ML 分类器（Pre&RecNeo）+ 综合打分（RefinedNeo）输出排名。**非单一免疫原性评分工具，是端到端 pipeline。**

## 1. 输入数据模板 / 格式
- **WES 模式**：原始 WES（FASTQ）+ RNA-seq + `config_WES.yaml`
- **VCF 模式**：突变 VCF + 表达谱 + 拷贝数 + 肿瘤细胞含量 + `config_VCF.yaml`
- **不接受单纯肽段 CSV**，需配套患者基因组数据
- 是否需基因组数据：✅ 必需（WES/RNA-seq）
- **实测输入样例**：TODO

## 2. 运行参数设置
- 通过 YAML 配置文件（config_WES.yaml / config_VCF.yaml）调各模块参数
- **实测命令行**：TODO

## 3. 输出数据格式 + 含义
- **Pre&RecNeo**：T 细胞识别概率（0-1 连续）
- **RefinedNeo**：综合评分（整合表达量/等位基因比例/加工效率/自身抗原差异性/T 细胞识别概率，0-1 连续排名分）
- 患者水平：所有表位 RefinedNeo 分之和 = 总体免疫原性指标
- 分数类型：连续排名分
- **能否定量免疫强弱**：✅ 是（RefinedNeo 连续），但需完整基因组链，非「喂肽段出分」轻工具
- **实测输出样例**：TODO

## 4. 简介（特点 / 优势）
- 方法：ML 分类器 + 综合打分函数，端到端 pipeline
- 特点：从原始测序数据一站式到排名；患者级聚合指标
- 优势：定量 + 整合多组学特征（表达/加工/自身相似性）
- 局限：**部署难度最高**——Python 2.7（EOL）+ Ubuntu 16.04 老链 + netMHCpan 许可 + 多工具协调 + 需全基因组数据（不能只给肽段）

## 部署记录
- repo：https://github.com/bm2-lab/pTuneos
- 论文：*pTuneos: prioritizing tumor neoantigens from next-generation sequencing data*, Genome Medicine 2019, DOI 10.1186/s13073-019-0679-x
- 语言 / 框架：**Python 2.7（EOL）** + R 3.2.3 + sequenza 2.1.2
- 外部工具（需单独装/许可）：**NetMHCpan 4.0（DTU 学术许可）** + VEP + GATK 3.8 + Picard + BWA + samtools + kallisto + OptiType
- GPU 需求：不需要（但测试环境 88 核 256GB RAM）
- 部署策略：官方 Docker 镜像隔离 Py2.7/Ubuntu16.04 老环境。**镜像 = `bm2lab/ptuneos:v2.1`**（5.03GB；`:latest` 不存在，tag 仅 v2.1，Docker Hub API 查得）已拉到本地
- **🎯 镜像自带全套（实测，2026-06-22）**：
  - **netMHCpan-4.0 打包在 `/root/software/netMHCpan-4.0`** → **不用单独申请 netMHCpan-4.0 许可**（镜像内含）
  - netchop / netctlpan_1.1 / netMHCpan-2.3 也自带
  - **VCF_example_data + WES_example_data 都在** `/root/pTuneos/`，config_VCF.yaml / config_WES.yaml 现成
  - pTuneos 主程序 `/root/pTuneos/pTuneos.py`
- VCF 模式输入（config_VCF.yaml）：vcf_file(mutect2) + expression(Kallisto tsv) + copynumber(sequenza) + tumor_cellularity + hla_str + peptide_length=9 —— example 全有，跳过比对，**轻**
- **部署状态：🟡 部署验证通过，end-to-end 卡 VEP cache**（2026-06-22）。Py2.7 容器跑通、读 config、校验 VCF 输入 OK；停在 "Please check your vep path!"
- **镜像内真实工具路径**（config 占位符 `your/path/to/...` 须改成这些）：
  - vep_path = `/root/software/ensembl-vep/vep`
  - netMHCpan_path = `/root/software/netMHCpan-4.0/netMHCpan`
  - pyclone_path = `/usr/local/bin/PyClone`
  - 自带：GATK/BWA/samtools/kallisto/picard/vcftools/trimmomatic（/root/software/）
- **唯一缺口 = VEP cache**（真实人类基因组注释库 GRCh37/38，~15-25GB，**镜像只带 dummy 测试 cache**，需 `vep_install` 或官方下载到 `vep_cache_path`）。这是 end-to-end 跑通的最后一块。
- 内核修复：WSL `vsyscall=emulate` 已开 → 容器内老 netMHCpan 二进制不再 segfault
- example 烟测：`docker run -w /root/pTuneos bm2lab/ptuneos:v2.1 python pTuneos.py VCF -i config_VCF.yaml`（改好路径 + 备 VEP cache 后）
