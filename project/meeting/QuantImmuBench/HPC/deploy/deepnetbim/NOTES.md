# DeepNetBim — 部署说明（QuantImmuBench §工具部署 第20槽，免疫原性组）

> 建档：2026-06-30。服务 quantimmu-bench 工具部署，补免疫原性组第 20 槽。
> 官方 repo：github.com/Li-Lab-SJTU/DeepNetBim （上海交大 Li Lab）
> 许可：**license=null（repo 无 LICENSE 文件）** —— ⚠️ 见下「许可 caveat」。

---

## 工具简介

DeepNetBim 是 pMHC-I **结合 + 免疫原性**双任务深度学习预测器（attention + CNN）。
repo 自带两套权重：
- `data/model_immuno.h5`（**免疫原模型，36.4MB，本工具用这个**）
- `data/model_bind.h5`（结合模型，本工具**不用**）

clone 即得权重，**无需额外下载/重训**。

- 输入：peptide **仅 9-mer**（模型架构固定 9 位输入，非 9mer 不支持）+ HLA
  （写法 `HLA-A01:01`，**无星号、保留冒号** —— 区别 universe 的带星 `HLA-A*01:01`）。
  **HLA-aware**（同肽不同 HLA 给不同分）。无 MT/WT 概念、无 NetMHCpan 上游特征。
- 输出：`immuno_probability` ∈ [0,1]，**越高越免疫原** → 横评 **不翻转**。
  （另有 `pred_immuno` 二值列，本工具不用。）
- 横评归类：**免疫原性**预测（immunogenicity，用 immuno 模型）。

---

## ⚠️ 许可 caveat（重要，发表前必处理）

repo **无 LICENSE 文件（license=null）**。用户已拍板可用于本 benchmark，但：
- **发表前须邮件 Li-Lab-SJTU 索明确授权**；
- **只发聚合指标（Spearman 等横评数字），不二次分发权重 / 不重新托管 model_immuno.h5**。

→ 非标准 OSI 许可，不写 PENDING_DTU sidecar，但 NOTES + PROVENANCE 须标此 caveat。

---

## ⚠️ TODO（主线 clone repo 后必核，方可全量跑）

coder 建 kit 时**无网络访问、repo 未 clone**，以下 repo-specific 事实**未二次核实**，
按纪律标 TODO，主线 `git clone https://github.com/Li-Lab-SJTU/DeepNetBim.git` 后按
README/示例逐条核实并改：

| # | 待核点 | 当前默认（占位）| 改哪里 |
|---|--------|----------------|--------|
| T1 | **HLA allele 写法** | `HLA-A01:01`（去星保冒号，researcher 已核）| `prep_input.py::to_deepnetbim_allele`（当前 `.replace('*','')`）；`parse_output.py::to_universe_allele`（去星↔带星互逆，须同步改）|
| T2 | **官方 predict 入口脚本** | `<repo>/predict.py` | `run_deepnetbim.py::PREDICT_SCRIPT_REL` |
| T3 | **选 immuno 模型方式** | argv `--model data/model_immuno.h5` | `run_deepnetbim.py::IMMUNO_MODEL_REL` + `call_deepnetbim_predict` argv（核官方如何指定 immuno vs bind）|
| T4 | **predict 调用 argv** | `python predict.py --model data/model_immuno.h5 <IN> <OUT>`（cwd=repo）| `run_deepnetbim.py::call_deepnetbim_predict` |
| T5 | **预测输入文件格式** | CSV 两列表头 `mhc,sequence` | `run_deepnetbim.py::write_predict_input` |
| T6 | **预测输出列名** | 自动识别 mhc/sequence/immuno_probability 列 | `run_deepnetbim.py::read_predict_output` |
| T7 | **Python/keras/TF 精确版本 pin** | keras 2.2.4（TF1 老栈，纯 CPU）| 见下「环境」，建 env 时核 repo README/requirements |
| T8 | **patch BASE 最高 NN** | 假设 27 → 出 28 | `scripts/patch_add_deepnetbim.py::BASE_NN` |

❗ run 脚本**必须 chdir 到 repo 目录跑**（已用 `cwd=repo`），否则相对路径
`data/model_immuno.h5` 加载不到自带权重。

---

## 安装 / 环境（TF1 老栈，需独立 env）

repo 依赖 keras 2.2.4 + numpy/pandas/scipy/scikit-learn。**纯 CPU 可跑**（秒级/肽）。

> ⚠️ TF1.x 老栈与项目其它工具的 TF2/torch 环境**不兼容**，必须独立 conda env。
> 参考本项目 ImmuneApp 先例（py3.7 + TF1.15.0 + keras2.2.4）：

```bash
git clone https://github.com/Li-Lab-SJTU/DeepNetBim.git HPC/deploy/deepnetbim/repo
conda create -n deepnetbim_env python=3.7 -y
conda activate deepnetbim_env
# TODO(T7) 精确版本核 repo README/requirements；先按 ImmuneApp 先例：
pip install "tensorflow==1.15.0" "keras==2.2.4" numpy scipy scikit-learn pandas
```

---

## 运行流水线（供主线跑，本地 WSL2 / HPC 均可。coder 不跑，主线串行）

```bash
# Step 0: clone 官方 repo（权重自带 data/model_immuno.h5，无需额外下载）
git clone https://github.com/Li-Lab-SJTU/DeepNetBim.git HPC/deploy/deepnetbim/repo

# Step 1: 准备输入（仅 9mer 过滤 + MHC-I 过滤 + HLA 去星格式）
python HPC/deploy/deepnetbim/prep_input.py
#   先用 --smoke 50 验格式：
#   python HPC/deploy/deepnetbim/prep_input.py --smoke 50

# Step 2: 烟测（5 个 9mer 肽 × HLA-A*02:01 验官方调用链/列结构）—— 主线跑，coder 不跑
python HPC/deploy/deepnetbim/run_deepnetbim.py --smoke 5 --repo-dir HPC/deploy/deepnetbim/repo
#   ⚠️ 烟测先核 TODO T2-T6（入口/选immuno模型/argv/输入格式/输出列），跑通再全量

# Step 3: 全量预测（~9011 个 9mer pairs，immuno 模型，CPU）
python HPC/deploy/deepnetbim/run_deepnetbim.py --repo-dir HPC/deploy/deepnetbim/repo

# Step 4: 回贴 universe（34247 行输出，方向不翻转，仅 9mer 命中 ~17%）
python HPC/deploy/deepnetbim/parse_output.py

# Step 5: 合并进大表（先核最高 NN 改 BASE_NN）
python scripts/patch_add_deepnetbim.py
python analysis/merge_metrics_NNtools.py
```

最终单工具输出：`scripts/out/newtools/DeepNetBim_DS1DS2_scores.csv`

---

## 4 类信息（工具横评标准格式）

| 项 | 值 |
|----|----|
| 工具版本 | DeepNetBim（repo master，Li-Lab-SJTU），immuno 模型 model_immuno.h5 |
| 许可 | **license=null** —— 发表前须邮件索授权，只发聚合指标不分发权重 |
| 输入格式 | peptide **仅 9-mer** + HLA `HLA-A01:01`（去星保冒号，HLA-aware）；TODO T1/T5 核精确格式 |
| 输出分数 | `immuno_probability` ∈[0,1]，**越高越免疫原**（不翻转）|
| 运行平台 | CPU，TF1 老栈（keras 2.2.4），独立 conda env，秒级/肽 |
| 分类 | **免疫原性**预测（immunogenicity）|

---

## HLA 格式（去星 ↔ 带星 round-trip）

| 来源 | 格式 | 例 |
|------|------|----|
| universe / uniq_pep_hla.csv | 带星（标准）| `HLA-A*02:01` |
| DeepNetBim 输入（mhc 列）| **去星保冒号** | `HLA-A02:01` |

- `prep_input.py::to_deepnetbim_allele`：带星 → 去星（`.replace('*','')`）。
- `deepnetbim_input.csv` 同时保留：`HLA_Allele`（带星原始，join key）+ `mhc`（去星，喂模型）。
- `run_deepnetbim.py` 输出的 `deepnetbim_raw.csv` 列 = `mhc, sequence, immuno_probability`
  （mhc 仍去星）。
- `parse_output.py::to_universe_allele`：去星 → 带星（在 HLA-A/B/C 后插 `*`），重建后
  与 universe 的 HLA_Allele 匹配回贴。**T1 改写法时这两个互逆函数须同步改。**

---

## 分数方向（越高越免疫原，不翻转）

| 原始列 | 原始方向 | 输出列 | 变换 |
|--------|----------|--------|------|
| `immuno_probability` ∈[0,1] | **越高越免疫原** | `MT/WT_DeepNetBim` | **不变**（直接用）|

> ✅ researcher 已核：DeepNetBim immuno 模型输出免疫原概率，越高越免疫原 → 与 benchmark
> 「越大越免疫原」约定同向。对照 MHCnuggets（IC50 越低越强需取负），本工具 **不取负**。
> `parse_output.py` / `patch_add_deepnetbim.py` 均不翻转。

---

## HLA-aware（区别 TransHLA）

DeepNetBim 是 **HLA-aware**（同 MHCnuggets / MHCSeqNet / BigMHC_EL）：同肽不同 HLA 给不同分
→ score_map 键 = **(peptide, HLA)** 对，parse / patch 均按 (subpeptide, HLA) 对级查表。
**不是** TransHLA 那种 HLA-agnostic 肽-only 广播。
→ 无 HLA-agnostic caveat；P101/P102 HLA-FIX 走自然键，天然命中（同 MHCnuggets 套路）。

---

## 已知坑 / caveat

1. **仅 9-mer，低覆盖 ~17%**：universe 53582 对里只 ~9011 个 9-mer → 非 9mer 子肽全填 NaN
   （同 NetTepi 的低覆盖处境）。这是工具本身限制，**不是 bug**，merge 时 NaN 属预期。
2. **IEDB 泄露风险**：训练数据 `immunogenic_train.csv` 在仓，**IEDB 来源高度可能**
   → 与本 benchmark 的 ELISpot 测试集可能存在**数据泄露**（训练肽与测试肽重叠）。
   横评/解读时须标此 caveat，DeepNetBim 偏高的分可能部分来自记忆而非泛化。
3. **license=null**：见上「许可 caveat」—— 发表前邮件索授权，只发聚合指标不分发权重。
4. **TF1 老栈隔离**：必须独立 conda env，别与项目 TF2/torch 工具混（OMP/版本冲突）。
5. **必须 cwd=repo 跑**：`data/model_immuno.h5` 是相对路径，run 脚本已 `cwd=repo`。
6. **TODO T1-T6 未核**：HLA 写法/官方入口/选 immuno 模型/argv/输入格式/输出列名为占位默认，
   主线 clone 后**先烟测核实**再全量，别盲跑（见上 TODO 表）。
7. **patch BASE NN**：跑前核 `scripts/out/merged_all_tools_*tools.xlsx` 最高 NN，
   改 `patch_add_deepnetbim.py::BASE_NN`（默认 27）。

---

## 本部署四件套 + patch

| 文件 | 作用 |
|------|------|
| `prep_input.py` | uniq_pep_hla.csv → **仅 9mer** + MHC-I 过滤 + HLA 去星 → `deepnetbim_input.csv`（peptide,HLA_Allele,mhc,sequence，含 map）+ `deepnetbim_unsupported.csv`；`--smoke N` |
| `run_deepnetbim.py` | subprocess 调官方 predict（**immuno 模型**，cwd=repo）→ `deepnetbim_raw.csv`（mhc,sequence,immuno_probability）；`--smoke N`+`--repo-dir` |
| `parse_output.py` | raw 去星重建带星 → join universe（MT/WT 双打分，HLA-aware）方向不翻转 → `DeepNetBim_DS1DS2_scores.csv`（4-key + MT/WT_DeepNetBim）|
| `NOTES.md` | 本文件 |
| `scripts/patch_add_deepnetbim.py` | 合 MT/WT_DeepNetBim 两列进 merged_all_tools_<NN>tools.xlsx → +1（BASE_NN TODO 核最高 NN）|
