# MHCSeqNet — 部署说明（QuantImmuBench §工具部署 P10槽，替 MAAP）

> 建档：2026-06-30。服务 quantimmu-bench 工具部署，补呈递组第 10 槽（替 MAAP）。
> 官方 repo：github.com/cmb-chula/MHCSeqNet （Chulalongkorn CMB Lab）
> 许可：**Apache-2.0** —— **数字可自由发布**，非 DTU pending。

---

## 工具简介

MHCSeqNet 是 pMHC-I 结合/呈递似然预测器，深度神经网络（RNN/embedding），**pan-allele**
（单网络覆盖大量 allele，无需逐 allele 重训）。权重 repo 内自带 `PretrainedModels/`
（`one_hot_model` + `sequence_model` 两套），**无需重训/额外下载**。

- 输入：peptide 8–15mer + HLA（写法 `HLA-A*02:01`），**HLA-aware**（不同于 HLA-agnostic
  的 TransHLA —— 同肽不同 HLA 给不同分）。只需 peptide + HLA，**无 MT/WT 概念、无
  NetMHCpan 上游特征**。
- 输出：**binding probability ∈ [0,1]，越高越强**（呈递/配体似然）→ 横评 **不翻转**。
- 论文：Phloyphisut et al., *BMC Bioinformatics* 2019（"MHCSeqNet: a deep neural network
  model for universal MHC binding prediction"）。
- 横评归类：呈递/binding 代理（presentation/binding likelihood）。

---

## ⚠️ TODO（主线 clone repo 后必核，方可全量跑）

coder 建 kit 时**无网络访问、repo 未 clone**，以下 repo-specific 事实**未二次核实**，
按纪律标 TODO，主线 `git clone https://github.com/cmb-chula/MHCSeqNet.git` 后按
README/Script/示例输入逐条核实并改：

| # | 待核点 | 当前默认（占位）| 改哪里 |
|---|--------|----------------|--------|
| T1 | **HLA allele 写法** | 保留 `HLA-A*02:01`（带星号，researcher 已核）| `prep_input.py::to_mhcseqnet_allele`（当前 identity）|
| T2 | **官方 predict 入口脚本** | `<repo>/predict.py` | `run_mhcseqnet.py::PREDICT_SCRIPT_REL` |
| T3 | **predict 调用 argv** | `python predict.py <IN> <OUT>`（cwd=repo）| `run_mhcseqnet.py::call_mhcseqnet_predict`（是否需 --flag）|
| T4 | **预测输入文件格式** | 每行 `<allele> <peptide>` 空格分隔、无表头 | `run_mhcseqnet.py::write_predict_input` |
| T5 | **预测输出列名** | 自动识别 allele/peptide/prob 列 | `run_mhcseqnet.py::read_predict_output` |
| T6 | **Python/TF/Keras 精确版本 pin** | TF>=1.6 / Keras>=2.2（TF1 老栈）| 见下「环境」，建 env 时核 setup.py/requirements |
| T7 | **patch BASE 最高 NN** | 假设 26 → 出 27 | `scripts/patch_add_mhcseqnet.py::BASE_NN` |

❗ run 脚本**必须 chdir 到 repo 目录跑**（已用 `cwd=repo`），否则相对路径
`PretrainedModels/` 加载不到自带权重。

---

## 安装 / 环境（TF1 老栈，需独立 env）

repo 依赖 Python3 + Keras>=2.2 + TensorFlow>=1.6 + numpy/scipy/scikit-learn。**纯 CPU 可跑**。

> ⚠️ TF1.x 老栈与项目其它工具的 TF2/torch 环境**不兼容**，必须独立 conda env。
> 参考本项目 ImmuneApp 先例（py3.7 + TF1.15.0）：

```bash
git clone https://github.com/cmb-chula/MHCSeqNet.git HPC/deploy/mhcseqnet/repo
conda create -n mhcseqnet_env python=3.7 -y
conda activate mhcseqnet_env
# TODO(T6) 精确版本核 repo setup.py/requirements.txt；先按 ImmuneApp 先例：
pip install "tensorflow==1.15.0" "keras==2.2.4" numpy scipy scikit-learn pandas
```

---

## 运行流水线（供主线跑，本地 WSL2 / HPC 均可）

```bash
# Step 0: clone 官方 repo（权重自带 PretrainedModels/，无需额外下载）
git clone https://github.com/cmb-chula/MHCSeqNet.git HPC/deploy/mhcseqnet/repo

# Step 1: 准备输入（肽长 + MHC-I 过滤 + HLA 格式）
python HPC/deploy/mhcseqnet/prep_input.py
#   先用 --smoke 50 验格式：
#   python HPC/deploy/mhcseqnet/prep_input.py --smoke 50

# Step 2: 烟测（5 肽 × HLA-A*02:01 验官方调用链/列结构）—— 主线跑，coder 不跑
python HPC/deploy/mhcseqnet/run_mhcseqnet.py --smoke 5 --repo-dir HPC/deploy/mhcseqnet/repo
#   ⚠️ 烟测先核 TODO T2-T5（入口/argv/输入格式/输出列），跑通再全量

# Step 3: 全量预测（~53K pairs，pan-allele 一次跑，CPU）
python HPC/deploy/mhcseqnet/run_mhcseqnet.py --repo-dir HPC/deploy/mhcseqnet/repo

# Step 4: 回贴 universe（34247 行输出，方向不翻转）
python HPC/deploy/mhcseqnet/parse_output.py

# Step 5: 合并进大表（先核最高 NN 改 BASE_NN）
python scripts/patch_add_mhcseqnet.py
python analysis/merge_metrics_NNtools.py
```

最终单工具输出：`scripts/out/newtools/MHCSeqNet_DS1DS2_scores.csv`

---

## 4 类信息（工具横评标准格式）

| 项 | 值 |
|----|----|
| 工具版本 | MHCSeqNet（repo master，cmb-chula）|
| 许可 | Apache-2.0，数字可自由发布 |
| 输入格式 | peptide 8–15mer + HLA `HLA-A*02:01`（HLA-aware）；TODO T1/T4 核精确格式 |
| 输出分数 | `prob`（binding probability ∈[0,1]，**越高越强**）|
| 运行平台 | CPU，TF1 老栈（TF>=1.6/Keras>=2.2），独立 conda env |
| 分类 | 呈递/binding 似然代理 |

---

## HLA 格式

| 来源 | 格式 | 例 |
|------|------|----|
| universe / uniq_pep_hla.csv | 带星号（标准）| `HLA-A*02:01` |
| MHCSeqNet 输入 | TODO T1（researcher 核为带星号，当前保留原样）| `HLA-A*02:01` |

`prep_input.py::to_mhcseqnet_allele` 当前为 **identity**（保留带星号）。
`mhcseqnet_input.csv` 同时保留两列：
- `HLA_Allele`（带星号原始格式，供 `parse_output.py` 回贴 universe，行序 join key）
- `mhcseqnet_allele`（喂 MHCSeqNet 的格式）

`run_mhcseqnet.py` 输出的 `mhcseqnet_raw.csv` 里 `HLA_Allele` 回写**带星号**格式，
parse 阶段与 universe 直接匹配，无需再转。

---

## 分数方向（越高越免疫原，不翻转）

| 原始列 | 原始方向 | 输出列 | 变换 |
|--------|----------|--------|------|
| `prob` ∈[0,1] | **越高越强**（呈递/配体似然）| `MT/WT_MHCSeqNet` | **不变**（直接用）|

> ✅ researcher 已核：MHCSeqNet 输出 binding probability，越高越强 → 与 presentation 分数
> 同向。对照 MHCnuggets（IC50 越低越强需取负），本工具 **不取负**。
> `parse_output.py` / `patch_add_mhcseqnet.py` 均不翻转。

---

## HLA-aware（区别 TransHLA）

MHCSeqNet 是 **HLA-aware**（同 MHCnuggets / BigMHC_EL）：同肽不同 HLA 给不同分 →
score_map 键 = **(peptide, HLA)** 对，parse / patch 均按 (subpeptide, HLA) 对级查表。
**不是** TransHLA 那种 HLA-agnostic 肽-only 广播。
→ 无 HLA-agnostic caveat；P101/P102 HLA-FIX 走自然键，天然命中（同 MHCnuggets 套路）。

---

## 已知坑

1. **TF1 老栈隔离**：必须独立 conda env，别与项目 TF2/torch 工具混（OMP/版本冲突）。
2. **必须 cwd=repo 跑**：`PretrainedModels/` 是相对路径，run 脚本已 `cwd=repo`。
3. **TODO T2-T5 未核**：官方入口/argv/输入格式/输出列名为占位默认，主线 clone 后**先烟测
   核实**再全量，别盲跑 53K（见上 TODO 表）。
4. **HLA-aware**：按 (pep,HLA) 对查表，不是肽-only 广播（区别 TransHLA）。
5. **patch BASE NN**：跑前核 `scripts/out/merged_all_tools_*tools.xlsx` 最高 NN，
   改 `patch_add_mhcseqnet.py::BASE_NN`（默认 26）。

---

## 本部署四件套 + patch

| 文件 | 作用 |
|------|------|
| `prep_input.py` | uniq_pep_hla.csv → 肽长+MHC-I 过滤 + HLA 格式 → `mhcseqnet_input.csv`（含 map 列）+ `mhcseqnet_unsupported.csv`；`--smoke N` |
| `run_mhcseqnet.py` | subprocess 调官方 predict（pan-allele，cwd=repo）→ `mhcseqnet_raw.csv`（peptide, HLA_Allele, prob）；`--smoke N` |
| `parse_output.py` | raw join universe（MT/WT 双打分，HLA-aware）方向不翻转 → `MHCSeqNet_DS1DS2_scores.csv` |
| `NOTES.md` | 本文件 |
| `scripts/patch_add_mhcseqnet.py` | 合 MT/WT_MHCSeqNet 两列进 merged_all_tools_<NN>tools.xlsx → +1 |
