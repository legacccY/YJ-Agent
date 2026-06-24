# 参考文献 / 工具出处

本 benchmark 部署测试的 5 个免疫原性预测工具及其外部依赖工具的官方论文、代码仓库与许可。
逐工具的输入/参数/输出/特点详见 `TOOLS/<tool>.md`；代码归属（哪些是我们写的、哪些是外部的）详见 `PROVENANCE.md`。

## 我负责测试的 5 个工具

| 工具 | 论文 | DOI | 官方 repo |
|---|---|---|---|
| **DeepImmuno** | DeepImmuno: deep learning-empowered prediction and generation of immunogenic peptides for T-cell immunity. *Briefings in Bioinformatics*, 2021. | [10.1093/bib/bbab160](https://doi.org/10.1093/bib/bbab160) | https://github.com/frankligy/DeepImmuno |
| **PredIG** | PredIG: an interpretable predictor of T-cell epitope immunogenicity. *Genome Medicine*, 2025. | [10.1186/s13073-025-01569-8](https://doi.org/10.1186/s13073-025-01569-8) | https://github.com/BSC-CNS-EAPM/PredIG · 容器 https://github.com/BSC-CNS-EAPM/predig-containers |
| **NeoTImmuML** | NeoTImmuML: a machine learning-based prediction model for human tumor neoantigen immunogenicity. *Frontiers in Immunology*, 2025. | [10.3389/fimmu.2025.1681396](https://doi.org/10.3389/fimmu.2025.1681396) | https://github.com/01SYan19/NeoTImmuML |
| **IMPROVE** | IMPROVE: a feature model to predict neoepitope immunogenicity through broad-scale validation of T-cell recognition. *Frontiers in Immunology*, 2024. | [10.3389/fimmu.2024.1360281](https://doi.org/10.3389/fimmu.2024.1360281) | https://github.com/SRHgroup/IMPROVE_tool · 论文 repo https://github.com/SRHgroup/IMPROVE_paper |
| **pTuneos** | pTuneos: prioritizing tumor neoantigens from next-generation sequencing data. *Genome Medicine*, 2019. | [10.1186/s13073-019-0679-x](https://doi.org/10.1186/s13073-019-0679-x) | https://github.com/bm2-lab/pTuneos |

## 第二批 5 工具（原李紫晨负责，现并入；2026-06-24 调研建档）

| 工具 | 论文 | DOI | 官方 repo |
|---|---|---|---|
| **PRIME** v2.1 | PRIME 1.0: Prediction of neo-epitope immunogenicity reveals TCR recognition determinants. *Cell Reports Medicine*, 2021. / PRIME 2.0: Improved predictions of antigen presentation and TCR recognition with MixMHCpred2.2 and PRIME2.0. *Cell Systems*, 2023. | [10.1016/j.celrep.2021.100194](https://doi.org/10.1016/j.celrep.2021.100194) · [10.1016/j.cels.2022.12.002](https://doi.org/10.1016/j.cels.2022.12.002) | https://github.com/GfellerLab/PRIME |
| **deepHLApan** | DeepHLApan: A Deep Learning Approach for Neoantigen Prediction Considering Both HLA-Peptide Binding and Immunogenicity. *Frontiers in Immunology*, 2019. | [10.3389/fimmu.2019.02559](https://doi.org/10.3389/fimmu.2019.02559) | https://github.com/jiujiezz/deephlapan |
| **ImmuneApp** | ImmuneApp for HLA-I epitope prediction and immunopeptidome analysis. *Nature Communications*, 2024. | [10.1038/s41467-024-53296-0](https://doi.org/10.1038/s41467-024-53296-0) | https://github.com/bsml320/ImmuneApp |
| **MHLAPre** | Meta learning for mutant HLA class I epitope immunogenicity prediction to accelerate cancer clinical immunotherapy. *Briefings in Bioinformatics*, 2024. | [10.1093/bib/bbae625](https://doi.org/10.1093/bib/bbae625) | https://github.com/ChanganMakeYi/MHLAPre |
| **HLAthena** | A large peptidome dataset improves HLA class I epitope prediction across most of the human population. *Nature Biotechnology*, 2020. | [10.1038/s41587-019-0322-9](https://doi.org/10.1038/s41587-019-0322-9) | 无 GitHub；web hlathena.tools + Docker `ssarkizova/hlathena-external` |

> ⚠️ HLAthena 预测 MHC 提呈非免疫原性（benchmark 只能当 proxy）；MHLAPre 权重未发布需邮件作者。详见 `DEPLOY_TRACKER.md` §第二批 Wave 3。

## 外部依赖工具（被上述工具调用）

| 工具 | 用途 / 被谁依赖 | 出处 | 许可 |
|---|---|---|---|
| **netMHCpan-4.1 / 4.0 / 2.8** | HLA 结合预测；pTuneos、IMPROVE、PredIG(容器内) | DTU Health Tech, services.healthtech.dtu.dk | ⚠️ **学术许可，禁再分发**（含跑出的 benchmark 结果，见 PROVENANCE） |
| **netMHCstabpan-1.0** | HLA 稳定性；IMPROVE feature_calc | DTU Health Tech | ⚠️ 学术许可，禁再分发 |
| **PRIME** | TCR 识别分；IMPROVE | https://github.com/GfellerLab/PRIME | 学术免费 |
| **MixMHCpred** | PRIME / IMPROVE 依赖 | https://github.com/GfellerLab/MixMHCpred | 学术免费 |
| **self_similarity** | Self-similarity 特征；IMPROVE | https://github.com/SRHgroup/self_similarity | 随 IMPROVE |
| **NetCleave / NetCTLpan / MHCflurry / NOAH** | 蛋白酶切 / 提呈 / 亲和力；PredIG（打包在官方 Docker 镜像 `bsceapm/predig`） | PredIG 容器 | 各自上游许可 |
| **Ensembl VEP + cache (GRCh37/38)** | 变体注释；pTuneos 完整 pipeline | https://www.ensembl.org/vep | Apache-2.0 |
| **R `Peptides` 包** | NeoTImmuML 的 78 个肽段特征计算 | CRAN `Peptides` | 开源 |

## 数据集

| 数据集 | 用途 | 出处 |
|---|---|---|
| ELISpot Dataset1 / Dataset2 | benchmark 评测真值（T 细胞反应强弱） | 袁老师团队提供（`data/Elispot_Dataset*.xlsx`） |
| Sample_merged_prime_results | 输入样例 | 团队提供（`data/`） |
| TumorAgDB2.0 (2024–2025) | NeoTImmuML 训练数据 | https://tumoragdb.com.cn |

> ⚠️ 投稿/对外报告含 netMHCpan / netMHCstabpan 跑出的对比数字前，需先取 DTU 书面同意（许可第 7(v)/10 条，见 `DEPLOY_TRACKER.md` 与 `PROVENANCE.md`）。
