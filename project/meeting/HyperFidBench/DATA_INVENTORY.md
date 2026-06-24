# HyperFidBench — DATA_INVENTORY

> 真源 = `.portfolio/datasets.json`。本文件只列本项目用到的数据细目，路径/状态以真源为准，脚本不硬编码。

| 数据集 | 任务 | 来源 | 获取方式 | 状态 |
|---|---|---|---|---|
| ABIDE I/II (preprocessed, CPAC) | ASD 功能连接组分类 | preprocessed-connectomes-project.org | 免登录 S3 HTTP 直下（`s3.amazonaws.com/fcp-indi/data/Projects/ABIDE_Initiative/Outputs/cpac/...`），含 rois_cc200/aal/schaefer 连接矩阵 | todo（下载脚本: github.com/ShawonBarman/How-to-download-ABIDE-Preprocessed-dataset） |
| ADNI | AD 第二验证(可选) | adni.loni.usc.edu | 需机构申请(2-4周)，非首选 | optional |
| Schaefer 2018 atlas (含 Yeo DMN 标签) | 解释对齐金标准 | nilearn `datasets.fetch_atlas_schaefer_2018` | 一行代码自动下 | ready |

## baseline / 工具 repo（立项核查已验）

| 工具 | 用途 | repo | star |
|---|---|---|---|
| BrainGB | 多 GNN baseline (ABIDE 内置) | github.com/HennyJie/BrainGB | 217 |
| BrainGNN_Pytorch | 图 GNN baseline | github.com/xxlya/BrainGNN_Pytorch | 211 |
| HyperGALE | 超图 GNN (ABIDE-II+Schaefer400) | github.com/mehular0ra/HyperGALE | 16 |
| PyG explain.metric.fidelity | fidelity+/- 指标 | pytorch-geometric (内置) | — |
| GraphFramEx | 图 XAI 评测框架 (ICLR24) | github.com/GraphFramEx/graphframex | — |
| SHypX (超图 explainer) | 对比项(无代码,引数字) | arXiv 2410.07764 | 无 repo |

## 待办

- [ ] 下载 ABIDE preprocessed（HPC 上传新数据=拍板点先报）→ 登记进 `.portfolio/datasets.json`
- [ ] 确认 HyperGALE 2 个 open issue 是否影响接 XAI 管道
- [ ] 确认 SHypX 论文是否有可复用 fidelity 数字表（无则该格 TODO 不编造）
