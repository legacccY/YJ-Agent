# ImmugenX — 部署说明（QuantImmuBench §工具部署，免疫原侧 I20）

> 建档：2026-06-29。服务 quantimmu-bench 工具部署，免疫原侧 lever=补满到 20（I20 = ImmugenX）。
> 论文：ImmugenX, *PLOS Computational Biology* 2024（DOI 10.1371/journal.pcbi.1012511）。
> 官方 repo：immugenx_runner_pub（Zenodo 发布的自包含 runner + 编译模型）。
> 许可：**Academic Software License v1.0**（GPL 式；详见 §许可）。
> 权重：Zenodo `immugenx_runner_pub.zip`（~22 MB，含 runner 代码 + 两个 TorchScript JIT 权重），
>       已亲手解包在 `zenodo/immugenx_runner_pub/`。

---

## 工具简介

ImmugenX 用**自包含 TorchScript JIT 模型**（编译权重 `models/<run_id>_jit.pt`）预测肽-HLA-I
免疫原性，**纯 CPU 可跑、无外部 binary 依赖（不调 netMHCpan）**。token 编码 peptide + HLA 伪序列
（mhcnames 解析 + class1_pseudosequences 查表），sigmoid 输出连续分。

官方 config `genesis_pub_config.json` 含两个模型：
- **ImmugenX** — 免疫原性主分（`single_tcrs=false`，TCR 输入当前不需要）。
- **Stability** — pMHC 稳定性副产分（`pmhc_module=true`）。

- 输入：肽 **8–15mer**（模型 `peptide_length=15`）+ **HLA-I**（人类 HLA-A/B/C；
  class1_pseudosequences 另含 BoLA 等非人类，本部署只用 A/B/C）。
- 输出本质：**immunogenicity / stability 连续分 ∈ [0,1]**，**越高越强**（直接横评，归免疫原性侧）。

---

## 4 类信息（工具横评标准格式）

| 项 | 值 |
|----|----|
| 工具版本 | ImmugenX（Zenodo immugenx_runner_pub；PLOS Comput Biol 2024 发布模型） |
| 许可 | **Academic Software License v1.0**（学术非商用；benchmark 数字可发，见 §许可） |
| 输入格式 | CSV 至少 `Antigen, HLA`；肽 8–15mer；**HLA 带星号 `HLA-A*02:01` 直喂（mhcnames 解析）** |
| 输出分数 | `ImmugenX` ∈ [0,1]（sigmoid 免疫原性，**越高越强**，不翻转）；`Stability` ∈ [0,1]（副产同向） |
| 运行平台 | **纯 CPU 可跑**；python=3.9 + pytorch=1.12.0 + pandas=1.3.4 + numpy==1.23.3 + mhcnames==0.4.8 + biopython==1.78 |
| 分类 | 免疫原性侧（immunogenicity 直接预测，非纯 BA 代理） |

---

## 🔑 HLA 编码格式（带星号直喂 mhcnames）

**结论：universe 的 `HLA-A*02:01` 带星号格式直接喂官方 `HLA` 列即可，无需手工转换。**

来源（2026-06-29 核自亲手解包 immugenx_runner_pub）：
- README §Inputs 明示 HLA 格式由 OpenVax `mhcnames` 包解析，**容错**（带/不带 "HLA" 都能 parse）。
- `encoders.py HLAEncoder._fetch_hla`：`mhcnames.normalize_allele_name(hla)` 归一 →
  `.replace("CW","C")` → 4 处 02 变体订正（B*07:01→07:02 / A*24:01→24:02 / B*44:01→44:02 /
  C*06:01→06:02）→ 库查表；<8 不完整 HLA 自动补 ':01'。
- pseudosequence 库 `libraries/HLA/class1_pseudosequences.csv`（列 `allele,pseudosequence`，
  allele 原始写法如 `HLA-A0101`，库构建时同样经 `mhcnames.normalize_allele_name` 归一）。

⇒ 本部署 `prep_input.py` 把 universe 的 `HLA-A*02:01` 原样写进 `HLA` 列（官方自行 normalize），
  并写一份同值 `HLA_Allele` 穿透列供 parse 回贴 universe（与 base 表 HLA_Allele 同款带星号）。

> ⚠️ allele 不在 class1_pseudosequences 库内的行会让 `_fetch_hla` 抛
> `ValueError(hla + " invalid HLA lookup attempted")` **崩整批** → `run_immugenx.py` 在调官方前
> 镜像 `_populate_pseudoseq_library` + `_fetch_hla` 的解析逻辑二次过滤，
> 剔到 `immugenx_unsupported_allele.csv`（parse 阶段 NaN）。

---

## 肽长 caveat（重要）

- 模型 `peptide_length=15`：`immugenx_jit_runner.load_and_process_data` 对 `len(epitope) > 15`
  的肽**静默跳过**（不进输出 → 该 (pep,HLA) 在 raw 缺失 → parse NaN）。
- prep 过滤保留 **8–15mer**。universe 实际肽长 8–14，全部 ≤15 通过。
- ⚠️ **验证范围 caveat**：ImmugenX 论文验证集为 **8–11mer**；12–14mer 在论文验证范围外但模型
  仍会打分。报告须标：**score 对 8–15mer model-accepted，但仅 8–11mer 经论文验证**。

---

## 分数方向（越高越免疫原，无需翻转）

| 原始列 | 原始方向 | 输出列 | 变换 |
|--------|----------|--------|------|
| `ImmugenX`  | sigmoid 免疫原性分 [0,1]，**越高越强** | `MT/WT_ImmugenX`           | **直接用（不翻转）** |
| `Stability` | sigmoid pMHC 稳定性分 [0,1]，**越高越强** | `MT/WT_ImmugenX_Stability` | **直接用（不翻转）** |

来源：`immugenx_jit_runner.run_model` —— `prediction_dict[key] = {"score": torch.sigmoid(pred)...}`。
sigmoid 概率，越高越免疫原。与 MHCnuggets 的 ic50（越低越强，需取负）相反 —— ImmugenX 无需任何方向归一。

> **主指标 = ImmugenX 免疫原性分**；**Stability 为副产**（pMHC 稳定性模块同时跑出，零额外成本），
> parse 一并落库供横评对照，不作主排名指标。

---

## 许可（Academic Software License v1.0，数字可发，非 DTU pending）

- License.md = Academic Software License v1.0（GPL 式，约束**衍生软件作品**的再分发）。
- **Section 0 明示**：运行不受限，输出仅当构成**衍生软件作品**时才受约束。
  ⇒ benchmark 的**数字/分数可发表**（学术非商用，我方符合）；**非 DTU pending**，
    不写 `PENDING_DTU` sidecar，patch_add_immugenx 直接合表。
- ✅ 唯一红线：**别把 RUNNER_REPO 代码 / JIT 权重塞进公开 repo**（保持本地 `zenodo/`，
  与 private 组合台一致；公开发布只发 benchmark 派生数字）。

---

## 安装 + 权重（供主线跑，本地/HPC 均可；我不下不跑）

```bash
# 权重已解包在 HPC/deploy/immugenx/zenodo/immugenx_runner_pub/
#   含 immugenx_runner/cli.py + configs/genesis_pub_config.json + models/<id>_jit.pt
#   （若需重新拿：Zenodo immugenx_runner_pub.zip）

# 建隔离环境装依赖（官方 environment.yml：python 3.9 + pytorch 1.12.0 + mhcnames 等）
cd HPC/deploy/immugenx/zenodo/immugenx_runner_pub
conda env create --file environment.yml      # name: immugenx
conda activate immugenx
pip install -e .                              # 装 immugenx_runner 包
cd -
```

> JIT 权重已含在解包目录的 `models/`，无须额外下载（与 munis 不同，ImmugenX 权重小）。

---

## 运行流水线（供主线跑）

```bash
# Step 1: 准备输入（肽长 8-15 + MHC-I 过滤；HLA 带星号直喂）
python HPC/deploy/immugenx/prep_input.py
#   先 --smoke 50 验格式：
#   python HPC/deploy/immugenx/prep_input.py --smoke 50

# Step 2: 烟测（5 肽 × HLA-A*02:01 验官方算子/列结构；需先装 immugenx env）
python HPC/deploy/immugenx/run_immugenx.py --smoke 5

# Step 3: 全量预测（~53K 对，subprocess 调官方 cli.py，CPU 强制）
python HPC/deploy/immugenx/run_immugenx.py

# Step 4: 回贴 universe（34247 行输出）
python HPC/deploy/immugenx/parse_output.py
```

最终输出：`scripts/out/newtools/ImmugenX_DS1DS2_scores.csv`
（列：Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide, MT_ImmugenX, WT_ImmugenX,
  MT_ImmugenX_Stability, WT_ImmugenX_Stability）

---

## 显存 / 算力

- **纯 CPU**（`run_immugenx.py` 设 `CUDA_VISIBLE_DEVICES=""` 强制 CPU，不抢主窗 GPU）。
- TorchScript JIT 模型极小（~22MB zip 含两模型），论文实测 **50k 对 M1 笔记本 ~52s**。
  全量 ~53K 对预计分钟级（CPU）。

---

## 已知坑

1. **cwd 必须 = RUNNER_REPO**：cli 内部按 `models/<run_id>_jit.pt` **相对路径**加载 JIT 权重；
   cwd 不在 RUNNER_REPO 会找不到 models/。`run_immugenx.py` 用 `subprocess.run(cwd=runner_repo)` 保证。
2. **强制 CPU**：`run_immugenx.py` subprocess env 设 `CUDA_VISIBLE_DEVICES=""` →
   官方 `torch.cuda.is_available()` 回 False → CPU。本机 GPU 被主窗占，节点铁律不抢。
3. **config 实际文件名 = `genesis_pub_config.json`**（**非** README 写的 `immugenx_pub_config.json`，
   后者不存在）。`run_immugenx.py` 默认指向实际名。
4. **allele 不在 class1_pseudosequences 库 → `_fetch_hla` ValueError 崩整批** →
   `run_immugenx.py` 调官方前镜像官方解析逻辑二次过滤，剔到 `immugenx_unsupported_allele.csv`。
5. **肽 >15 官方静默跳过**（不报错、不进输出 → parse NaN）。prep 已过滤 8–15。
6. **非标准氨基酸**：peptide token 编码对 ONE_HOT_DICT 外字符（B/J/O/U/Z）抛 KeyError 崩批
   （X 在表内合法）。universe 肽应为标准 20AA；若全量跑遇崩，先排查含非标 AA 的肽。
7. **官方 cli 输出带索引列**：`runner.py` 用 `dataframe.to_csv(save_path)`（默认 `index=True`）→
   首列是无名索引。`run_immugenx.py` 读回时已 `drop(filter(regex="Unnamed:"))`。
8. **mhcnames 依赖**：allele 精过滤的精确归一靠 `mhcnames`（在 immugenx env 内）。
   `run_immugenx.py` 无 mhcnames 时降级字符串归一（仅近似，已标 TODO）→ **正式运行务必在 immugenx env**。

---

## 本部署四件套

| 文件 | 作用 |
|------|------|
| `prep_input.py` | uniq_pep_hla.csv → 肽长 8-15 + MHC-I 过滤 → `immugenx_input.csv`（Antigen,HLA,HLA_Allele,source）+ `immugenx_unsupported.csv` |
| `run_immugenx.py` | 精过滤未知 allele → subprocess 调官方 `cli.py`（cwd=RUNNER_REPO + CUDA_VISIBLE_DEVICES="" 强制 CPU）→ `immugenx_raw.csv`（peptide, HLA_Allele, ImmugenX, Stability）；`--smoke N` |
| `parse_output.py` | raw join universe（(peptide,HLA) MT/WT 双 key 双打分，方向不翻转）→ `ImmugenX_DS1DS2_scores.csv`（含 Stability 副产列） |
| `NOTES.md` | 本文件 |

---

## 官方源出处（2026-06-29 核自亲手解包 immugenx_runner_pub）

- `immugenx_runner/cli.py` —— CLI（`-c <config> -i <input.csv> -o <output.csv> [-v]`）。
- `configs/genesis_pub_config.json` —— ImmugenX + Stability 两模型（均 `single_tcrs=false`，
  `peptide_length=15`，Stability 带 `pmhc_module=true`）；run_id → `models/<id>_jit.pt`。
- `immugenx_runner/runner.py` —— `Runner._run_and_save`：读 Antigen/HLA，保留输入全部列到输出，
  加 ImmugenX/Stability 列，`to_csv`（默认带索引）。
- `immugenx_runner/immugenx_jit_runner.py` —— `load_and_process_data`（肽>15 跳过）、
  `run_model`（`torch.sigmoid(pred)` → score）、`mlflow_data_key`（key=epitope_hla_None_None）。
- `immugenx_runner/encoders.py` —— `HLAEncoder._populate_pseudoseq_library`（过滤 'HLA' in allele
  且末位非字母 + `mhcnames.normalize_allele_name`）、`_fetch_hla`（CW→C + 4 订正 + <8 自动补 + 不命中 ValueError）。
- `environment.yml` —— python=3.9 / pytorch=1.12.0 / pandas=1.3.4 / numpy==1.23.3 /
  mhcnames==0.4.8 / biopython==1.78 / torchtext。
- `License.md` —— Academic Software License v1.0（Section 0：运行不受限，仅衍生软件作品受约束）。
