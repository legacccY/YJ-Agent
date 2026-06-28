# 工具扩张 v2 —— 第二批纳入清单 + 部署 recipe + 许可

> 服务 quantimmu-bench。建档 2026-06-26。来源:researcher×3 联网普查(官方 repo/README/DTU 许可原文 + 2025-26 新文献)。
> 目标:在现有 9 工具基础上扩张 ~10 个高质量工具,数据集不变(DS1+DS2),跑通优先。
> 上游普查见 [[LANDSCAPE_tools.md]];许可红线见 PROVENANCE.md。

---

## 一句话:撞车判断(STORY 守护)

2025-2026 新出工具逐一核验,**无一个做连续 T 细胞反应强度(ELISpot SFC)回归**。最接近的 CNNeo(2026)/T-SCAPE(2025)输出连续概率分但仍是分类置信度,非 magnitude 回归。→ **QuantImmune 定量蓝海完好,不撞车**。

---

## 二、第二批纳入清单(按部署难度/优先级排序)

数据集不变,所有工具喂 DS1+DS2 的肽(8-15mer,MT 有,WT 多数有)+ HLA-I allele(标准 `HLA-A*02:01`)。子肽×allele 级 34247 行。

### Tier-0 易部署 + 许可自由(先跑,本地 CPU 即可烟测)

| # | 工具 | 类别 | 许可 | 可发数字? | 输入要点 | 输出分数 | 难度 |
|---|---|---|---|---|---|---|---|
| 1 | **MHCflurry 2.0** | proxy baseline(BA+presentation) | Apache-2.0 | ✅ 自由 | `pip install mhcflurry` + `mhcflurry-downloads fetch`;HLA `HLA-A*02:01`/`HLA-A0201`;8-15mer | `mhcflurry_affinity`(nM,越低越强)/`_presentation_score`(越高越强) | 低(CPU/GPU) |
| 2 | **IEDB Immunogenicity (Calis 2013)** | baseline(propensity) | NPOSL-3.0 | ✅ 自由(纯 immuno predictor 不触发 DTU) | Next-Gen `tcell_mhci.py -j input.json`;HLA `HLA-A*02:01`;8-15mer | `immunogenicity score`(越高越强) | 低(CPU,纯统计) |
| 3 | **CNNeo (CNNeoPP)** | apples-to-apples(免疫原性) | **MIT** ✅ | ✅ 自由 | github.com/AaronChen007/neoantigen;standalone notebook,CSV `peptide,hla`;无需测序/结构 | 连续 score(0-1)+二分 | 低-中(notebook) |

### Tier-1 中等部署 + 学术许可(本地或 HPC)

| # | 工具 | 类别 | 许可 | 可发数字? | 输入要点 | 输出分数 | 难度 |
|---|---|---|---|---|---|---|---|
| 4 | **BigMHC (IM)** | apples-to-apples | 学术非商用(TODO核LICENSE) | ✅ 学术 | clone(~5GB含权重);HLA 灵活模糊;MT-only;`predict.py -m=im` | `.prd` 追加列(IM分,列名 TODO 跑后看) | 中(PyTorch,CPU可推理) |
| 5 | **ImmugenX** | apples-to-apples | Academic Software License v1.0 | ✅ 学术 | Zenodo zip runner(13850954);肽+HLA(可选TCR);无结构 | 连续(AUROC 0.619) | 中(zip 解包配环境) |
| 6 | **Repitope** | apples/proxy ⚠️HLA-agnostic | **MIT** ✅ | ✅ 自由 | `devtools::install_github`;Mendeley fragment lib;**只吃肽不吃HLA**;8-11mer | 免疫原性概率(连续) | 中(R+rJava+JDK) |
| 7 | **RPEMHC**(备选) | proxy baseline(BA) | TODO核 | TODO | github.com/lennylv/RPEMHC;肽+MHC | 结合亲和力 | 中 |

### Tier-2 DTU pending(跑但标「pending DTU 同意」,数字暂不外发)

| # | 工具 | 类别 | 许可 | 可发数字? | 输入要点 | 输出分数 | 难度 |
|---|---|---|---|---|---|---|---|
| 8 | **NetMHCpan 4.1 -BA** | proxy baseline(BA) | DTU Academic | ❌ pending DTU | 申请下载;`netMHCpan -p x.pep -BA -a HLA-A02:01`;任意HLA;8-14mer | `Aff(nM)`/`Rnk_BA` | 低(CPU,需申请) |
| 9 | **NetTepi 1.0** | baseline(经典加权) | DTU Academic | ❌ pending DTU | 申请下载;依赖 NetMHCpan+NetMHCstab;**仅13 HLA**;8-14mer | `Comb`/`%Rank` | 中(CPU,依赖链) |
| 10 | **ICERFIRE 1.0** | apples-to-apples | DTU(独立版TODO) | ❌ pending DTU | 独立版 v1.0a;CSV无表头 `mut,wt,HLA[,TPM]`;**HLA-A0201格式**;需MT+WT;8-14mer | percentile rank 0-100(**0=最强,方向反**) | 中(CPU,RF) |

### Tier-3 重型(GPU+结构,选做/视算力)

| # | 工具 | 类别 | 许可 | 可发? | 阻碍 | 难度 |
|---|---|---|---|---|---|---|
| 11 | **NeoaPred** | apples(结构 foreignness) | Apache-2.0 ✅ | ✅ | **严格9mer**(仅DS1+DS2的9mer子肽);需MSMS/APBS/PDB2PQR;Docker`panda1103/neoapred:1.0.0`;需MT+WT | 高(GPU+结构) |
| 12 | **T-SCAPE** | apples(2025 SOTA) | CC BY-NC-ND 4.0 ⚠️ | ⚠️ 学术非商用,ND禁衍生 | Linux-only;HuggingFace权重;HLA`HLA-A*02:01`;MT-only;≤20mer | 中-高(GPU) |
| 13 | **ImmunoStruct** | apples(多模态) | Yale非商用 | ⚠️ 学术 | **需AF2结构+无通用推理入口**(最重,可能放弃);限27 HLA存疑 | 极高(AF2+改码) |

**排除**(无可用 repo / 需 TCR / 需测序):neoIM(专利)、diffRBM/TLImm/TEIM/UniPMT(需TCR)、ImmunoNX/Seq2Neo全管线(需测序)、imNEO/Müller-ML/TEIP/PredImmuno(无公开 repo,TODO 标注)。

---

## 三、推荐执行批次(凑足 ~10 个有质量)

- **第一波(必跑,易+自由)**:MHCflurry · IEDB-Calis · CNNeo · BigMHC-IM · Repitope —— 5 个,本地/HPC CPU 即可,许可全自由(除 BigMHC 学术)。
- **第二波(DTU pending)**:NetMHCpan-BA · NetTepi · ICERFIRE —— 3 个,跑出数但标 pending,先申请 DTU 邮件 health-software@dtu.dk。
- **第三波(重型,视算力选 1-2)**:NeoaPred(9mer 子集)· T-SCAPE —— ImmunoStruct 列为 stretch(AF2 太重,优先级最低)。
- 备选补位:ImmugenX · RPEMHC。

→ 第一波 5 + 第二波 3 + 第三波 2 = **10 个**,达标。

---

## 四、关键部署坑(coder kit 必读)

1. **Repitope HLA-agnostic**:只按肽打分,无法区分同肽不同 HLA → 合并表里该工具对同一肽的所有 allele 行填同值;结论须标此 caveat。
2. **NeoaPred 严格 9mer**:只能跑 DS1(全9mer)+ DS2 的 9mer 子肽;非 9mer 填 NaN。需 MT+WT 配对。
3. **ICERFIRE HLA 格式特殊**:`HLA-A0201`(无星号无冒号),需转换;输出 **0=最强**(用前取负或 100-x 对齐方向)。
4. **DTU 三工具**:需学术注册邮件下载,CLI 在包内 README(下载后核);数字全程标 pending,csv/图/PPT/报告统一脚注。
5. **ImmunoStruct**:无通用自定义推理入口 + 需 ColabFold AF2(~50GB库)→ 端到端极重,coder 须自行适配,优先级最低,跑不通可诚实放弃。
6. **每工具输出方向不一**:BA/nM 越低越强、ICERFIRE 0 越强、其余越高越强 → 合并时统一成「越高越免疫原」方向再算 Spearman。

## 五、残留 TODO(不臆想)
BigMHC LICENSE+输出列名(跑后看)、ICERFIRE 独立版命令/依赖/许可、NeoaPred 推理是否强制GPU+8GB够否、T-SCAPE HPC安装+显存、ImmunoStruct HLA格式+Yale条款+推理VRAM、NetTepi CLI命令+依赖版本、RPEMHC许可、ImmugenX输入格式(zip内)。
