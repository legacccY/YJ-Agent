# 代码归属与出处（PROVENANCE）

明确区分**本项目自有代码**与**外部工具代码**，避免把别人的代码当成我们的，并标注许可与再分发限制。

## 我们自己写的代码（本项目原创）

| 路径 | 说明 |
|---|---|
| `scripts/prepare_inputs.py` | ELISpot 数据 → 各工具输入格式转换 |
| `scripts/merge_results.py` | 各工具输出汇总成统一 benchmark 表 |
| `scripts/improve/feature_calc_local.py`、`run_feature_calc.sh` | IMPROVE 特征计算的本地编排封装 |
| `scripts/neotimmuml/*.py`、`calc_78_features.R` | NeoTImmuML 训练集构建 + 78 特征计算 + 训练/预测 + 特征核对（**复刻官方 notebook 逻辑**，非官方 repo 原码） |
| `scripts/ptuneos/ptuneos_pre_recneo.py` | 抠出 pTuneos Pre&RecNeo 子模型批处理 wrapper（**复刻官方 `VCFprocessor.py::InVivoModelAndScore()` 的 5 特征 RF**，对账官方 example r=1.0） |
| `scripts/ptuneos/prep_input.py`、`merge_5tools.py` | pTuneos 输入准备 + 5 工具汇总 |
| `analysis/*.py`、`plot_benchmark_v3.R`、`build_report_docx.py`、`export_plot_data.py` | benchmark 指标计算、出图、报告生成 |
| `HPC/deploy/*.sh`、`HPC/elispot_run/*.sh` | HPC 部署 / SLURM 提交脚本 |
| `HPC/deploy/neoapred/` | NeoaPred prep / merge / runner 脚本（我方写，调官方 Docker `panda1103/neoapred:1.0.0`；Apache-2.0 可发数字）|
| `TOOLS/*.md`、`*.md` 文档 | 部署测试记录与报告 |

> `scripts/neotimmuml/models/*.joblib` 是我们**自训**的模型（NeoTImmuML 官方不发权重，按官方 notebook 用 TumorAgDB2.0 重训），不对标原论文精度。

## 外部工具代码（不是我们写的，标明出处）

下列代码/模型来自第三方官方 repo，**版权归原作者**。本项目仅部署调用，不主张著作权。
完整论文/DOI 见 `REFERENCES.md`。各 repo 体积大，留在 HPC `tools_repos/`，**未拉回本地、未进 git**——需要时从官方 repo 重新 clone。

| 外部代码 | 来源 | 许可 |
|---|---|---|
| DeepImmuno（`deepimmuno-cnn.py` 等） | github.com/frankligy/DeepImmuno | 见上游 repo |
| PredIG（R 脚本 + 模型 + `bsceapm/predig` 镜像内 predictors） | github.com/BSC-CNS-EAPM/PredIG | 见上游 repo |
| NeoTImmuML（`NeoTImmuML.ipynb`、`demo.csv`） | github.com/01SYan19/NeoTImmuML | 见上游 repo |
| IMPROVE（`Predict_immunogenicity*.py`、`feature_calculations.py`、models.zip） | github.com/SRHgroup/IMPROVE_tool | 见上游 repo |
| pTuneos（`VCFprocessor.py` 等，`bm2lab/ptuneos:v2.1` 镜像） | github.com/bm2-lab/pTuneos | 见上游 repo |
| PRIME / MixMHCpred | github.com/GfellerLab | 学术免费（商用需 Ludwig Institute 许可）|
| self_similarity | github.com/SRHgroup/self_similarity | 随 IMPROVE |
| NetCleave / NetCTLpan / MHCflurry / NOAH | PredIG 官方 Docker 镜像内打包 | 各自上游 |
| Ensembl VEP + cache | ensembl.org/vep | Apache-2.0 |

### 第二批 5 工具（原李紫晨负责，现并入；2026-06-24 调研建档，未部署）

| 外部代码 | 来源 | 许可 |
|---|---|---|
| PRIME | github.com/GfellerLab/PRIME | 学术非商用免费；商用需 Ludwig Institute (nbulgin@lcr.org) |
| deepHLApan | github.com/jiujiezz/deephlapan（或 Docker `biopharm/deephlapan:v1.1`）| **GPL-2.0**（衍生品须同 GPL 开源）|
| ImmuneApp | github.com/bsml320/ImmuneApp | **MIT**（自由使用/修改/分发）|
| MHLAPre | github.com/ChanganMakeYi/MHLAPre | **无 LICENSE**（GitHub 默认版权保留；学术使用需确认作者，权重未发布需邮件 23B903048@stu.hit.edu.cn）|
| HLAthena | 无 GitHub；Docker `ssarkizova/hlathena-external` + 论文 Supplementary Code | **research-only**（无显式开源协议，商用联系 Broad；Docker 再分发待作者确认）|

### Tier-3 工具（2026-06-26 建档）

| 外部代码 | 来源 | 许可 |
|---|---|---|
| NeoaPred（`neoapred` 镜像 + PepConf/PepFore 权重）| github.com/Dulab2020/NeoaPred；Docker `panda1103/neoapred:1.0.0` | **Apache-2.0**（可发数字/结果）|
| T-SCAPE（模型权重 + 推理脚本）| github.com/seoklab/T-SCAPE | **CC BY-NC-ND 4.0** ⚠️ 学术非商用，**ND 禁衍生**（见下⚠️条目）|
| ImmunoStruct（模型 + PyG 图推理脚本）| github.com/KrishnaswamyLab/ImmunoStruct；HF ChenLiu1996/ImmunoStruct | Yale 学术非商用（**未部署，NO-GO**）|

## ⚠️ 许可与再分发限制（重要）

- **DTU 工具（netMHCpan-4.1/4.0/2.8、netMHCstabpan-1.0）= 学术许可，禁止再分发**：
  - 二进制留在 HPC `ext_tools/`，**绝不进 git、绝不拉回本地公开仓、绝不上传 GitHub**。
  - 许可第 7(v)/10 条：未经 DTU 书面同意，**不得向第三方发布在其软件上跑出的 benchmark 结果**。
  - → 论文/对外报告若含 netMHCpan / netMHCstabpan 的对比数字，投稿阶段先取 DTU 书面同意。
- 其余外部 repo 各按其上游许可使用；开源/发布本项目时只发**我们自己写的代码 + 文档**，外部 repo 以「从官方 clone」方式引用，不打包别人源码。
- **T-SCAPE = CC BY-NC-ND 4.0，学术非商用，ND 禁衍生（重要）**：
  - 本项目修复官方发布代码 **2 个 bug** 才跑通：①输入列名须为 `peptide`（全小写，官方脚本大小写不一致导致 KeyError）；②`pmhc_im_neo` 加载分支 / `task_dict` 缺失致 KeyError（ckpt 结构 `torch.load` 实测 + 0-key 失配验证 + `task_dict` 一致性核实，详见 04_LOG Entry T3）。
  - 我方改动性质 = **使用官方权重 + 修复官方 bug**，非对原版代码做功能性衍生；但 ND 条款边界需注意。
  - → **投稿 / 对外报告含 T-SCAPE 数字时**：须标注（a）CC BY-NC-ND 4.0 学术非商用；（b）数字来自「官方权重 + 2-bug patch 版本」，非原始官方发布版，需加 caveat 说明差异。
- **ImmunoStruct = 未部署（NO-GO）**：Yale 学术非商用许可本身不挡；工程三重 blocker 封死（无裸肽+HLA 通用推理入口 / AF2 结构数百 GPU·h 不可承受 / HLA 仅覆盖 27 allele 而 DS1+DS2 共 65 allele）——不产 benchmark 数字，benchmark 报告**不引用 ImmunoStruct 分数**。
