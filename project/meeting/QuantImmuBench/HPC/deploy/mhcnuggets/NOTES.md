# MHCnuggets — 部署说明（QuantImmuBench §工具部署 P10）

> 建档：2026-06-29。服务 quantimmu-bench 工具部署，补满 30 工具呈递槽 P10。
> 官方 repo：github.com/KarchinLab/mhcnuggets （JHU / Karchin Lab）
> 许可：BSD-like（Apache-2.0 风格，JHU 学术许可）—— **数字可自由发布**。

---

## 工具简介

MHCnuggets 是 Johns Hopkins Karchin Lab 出的 pMHC 结合预测工具，**LSTM** 架构，
单一网络 + 迁移学习覆盖大量 allele（罕见 allele 借「最近 allele」迁移）。
本部署用 **MHC-I 模式**（class I），预测肽-HLA 的 **binding affinity IC50（nM）**。

- 论文：Shao et al., *Cancer Immunol Res* 2020（"High-Throughput Prediction of MHC Class I
  and II Neoantigens with MHCnuggets"）。
- 输出本质：BA（binding affinity）代理，**非 T 细胞免疫原性直接预测** → 横评里归类
  `proxy baseline`（与 MHCflurry / NetMHCpan 同类）。

---

## 安装（权重内置，无需额外下载）

```bash
pip install mhcnuggets
```

依赖：numpy / scipy / scikit-learn / pandas / keras / tensorflow / varcode（pip 自动拉）。
**模型权重打包在 pip 包内**（`mhcnuggets/saves/production/<allele>_BA_to_HLAp.h5` 或 `_BA.h5`），
无需 `fetch`/下载，离线可跑。

### 部署环境（重要）

- **建议 Linux / WSL2 + conda 隔离环境跑**。MHCnuggets 依赖 TensorFlow/Keras，
  老版本对 Windows 原生不友好（TF 2.10 是最后一个原生 Windows 版）。
- CPU 即可，**无需 GPU**（LSTM 小模型）。
- 不调 scipy.stats 做相关系数，本部署脚本无 OMP 冲突；但 mhcnuggets 自身 import scipy，
  若在 Windows 本地与 torch 混用注意 OMP（HPC/WSL2 Linux 无此问题）。

```bash
conda create -n mhcnuggets_env python=3.9 -y
conda activate mhcnuggets_env
pip install mhcnuggets pandas
```

> TF/keras 版本：mhcnuggets 兼容 TF 2.x。若 import 报 keras/tf API 不兼容，
> 优先固定 `tensorflow==2.12` 一档（见「已知坑」3）。

---

## 运行流水线（供主线跑，本地/HPC 均可）

```bash
# Step 0: clone 官方 repo（仅供参考/对照，pip 包已含运行所需；主线按需）
git clone https://github.com/KarchinLab/mhcnuggets.git HPC/deploy/mhcnuggets/repo

# Step 1: 准备输入（肽长 + MHC-I 过滤 + HLA 去星号）
python HPC/deploy/mhcnuggets/prep_input.py
#   先用 --smoke 50 验格式：
#   python HPC/deploy/mhcnuggets/prep_input.py --smoke 50

# Step 2: 烟测（5 肽 × HLA-A*02:01 验算子/列结构）
python HPC/deploy/mhcnuggets/run_mhcnuggets.py --smoke 5

# Step 3: 全量预测（~53K 对，按 allele 分组逐组跑，CPU LSTM）
python HPC/deploy/mhcnuggets/run_mhcnuggets.py

# Step 4: 回贴 universe（34247 行输出）
python HPC/deploy/mhcnuggets/parse_output.py
```

最终输出：`scripts/out/newtools/MHCnuggets_DS1DS2_scores.csv`

---

## 4 类信息（工具横评标准格式）

| 项 | 值 |
|----|----|
| 工具版本 | MHCnuggets（pip 最新稳定版，repo master） |
| 许可 | BSD-like（JHU/Karchin Lab），数字可自由发布 |
| 输入格式 | 换行分隔肽文件 + 单 allele；allele 格式 **`HLA-A02:01`（无星号）**；MHC-I 8–15mer |
| 输出分数 | `ic50`（nM，binding affinity，**越低越强**） |
| 运行平台 | CPU（LSTM），TensorFlow/Keras；建议 Linux/WSL2 |
| 分类 | proxy baseline（BA 代理），非 T 细胞免疫原性直接预测 |

---

## 官方 API 出处（2026-06-29 核自 GitHub master）

**来源**：`github.com/KarchinLab/mhcnuggets/blob/master/mhcnuggets/src/predict.py`

```python
from mhcnuggets.src.predict import predict

predict(
    class_="I",                 # MHC-I（'II' = MHC-II）
    peptides_path="peps.txt",   # 换行分隔肽文件（源码 peptides=[p.strip() for p in open(path)]）
    mhc="HLA-A02:01",           # 单 allele，无星号格式；一次一个 allele
    output="out.csv",           # 输出 CSV，表头 'peptide,ic50'；None→stdout
)
# 输出文件内容：
#   peptide,ic50
#   SIINFEKL,123.45
#   ...
# ic50 单位 nM，越低越强。
```

核实点：
- **predict 签名**：`predict(class_, peptides_path, mhc, ..., output=None, ...)`（predict.py L35）。
- **peptides_path 是文件不是 list**：`peptides = [p.strip() for p in open(peptides_path)]`（L51）。
- **输出列**：`peptide,ic50`（L140-142），ic50 = `map_proba_to_ic50` 反算的 nM 值。
- **一次一个 allele**：predict 内部对单个 `mhc` 加载对应权重。
- **HLA 格式无星号**：`find_closest_mhcI.py::closest_human_allele_name` 用
  `mhc[4]`（基因字母）、`int(mhc[5:7])`（超型）、`int(mhc[8:10])`（亚型）切片解析，
  星号会让 `int()` 崩 → 必须 `HLA-A02:01` 无星号格式。default pan model 常量也是
  `HLA-A02:01 / HLA-B07:02 / HLA-C04:01`（同文件 L23-25）。

---

## HLA 格式转换（关键）

| 来源 | 格式 | 例 |
|------|------|----|
| universe / uniq_pep_hla.csv | 带星号（标准） | `HLA-A*02:01` |
| MHCnuggets 输入 | **去星号** | `HLA-A02:01` |

`prep_input.py::to_mhcnuggets_allele` 做 `hla.replace("*", "")` 转换，
并在 `mhcnuggets_input.csv` 同时保留两列：
- `HLA_Allele`（带星号原始格式，供 `parse_output.py` 回贴 universe）
- `mhcnuggets_allele`（去星号，供 `run_mhcnuggets.py` 喂 MHCnuggets）

`run_mhcnuggets.py` 输出的 `mhcnuggets_raw.csv` 里 `HLA_Allele` 回写**带星号**格式，
所以 parse 阶段与 universe 直接匹配，无需再转。

---

## 分数方向归一说明（越高越免疫原）

| 原始列 | 原始方向 | 输出列 | 变换 |
|--------|----------|--------|------|
| `ic50` (nM) | **越低越强**（binding affinity） | `MT/WT_MHCnuggets` | **取负** (`-ic50`) |

> ✅ 已查官方源确认：MHCnuggets MHC-I 输出的是 **binding affinity IC50（nM），越低越强**
> （predict.py 注释 "Predict IC50s"，`map_proba_to_ic50`）。与 presentation 分数（越高越强）相反，
> 故本部署 `parse_output.py` **取负**，使 `MT/WT_MHCnuggets` 越高越免疫原，与其他工具列对齐。
> 计算 Spearman(ρ, ELISpot) 时直接用这两列（正相关越高越好）。

---

## 已知坑

1. **HLA 必须去星号**：`HLA-A*02:01` 直接传会让 closest_allele 的 `int()` 切片崩 →
   已在 prep 阶段统一转 `HLA-A02:01`。
2. **closest_allele 不硬报错**：allele 不在训练集时 MHCnuggets 自动选生物超型/名称最近 allele，
   兜底默认 pan model（A02:01 / B07:02 / C04:01）。**意味着所有 MHC-I allele 都会拿到分数**
   （可能来自 closest 迁移），不会出现「unsupported」NaN（除非肽长/非 Class I 被 prep 过滤）。
   横评时若要严格只看 exact-match allele，需另从 stdout 的 "Closest allele found" 日志核对。
3. **TF/Keras 版本**：mhcnuggets 老代码 `from keras.optimizers import Adam` 有 fallback 到
   `tensorflow.keras`，但极端版本组合可能 import 失败 → 固定 `tensorflow==2.12` + 对应 keras 较稳。
   建议新建 conda env 隔离，别与项目其他 TF 版本混。
4. **MHC-II 未部署**：本部署只跑 class I（`class_='I'`）。universe 若含 HLA-DRB/DQ/DP 行会被
   `prep_input.py` 过滤进 `mhcnuggets_unsupported.csv`（reason=not_mhc_class_I）。当前 uniq_pep_hla
   全为 HLA-A/B/C，预计无 Class II 行。
5. **逐 allele 重建模型**：官方 predict 每次调用重建 LSTM + load 权重，65 个 allele = 65 次加载，
   有固定开销但可接受；不要在循环里担心权重缓存，按 allele 分组跑即可。
6. **peptides_path 文件**：run 脚本用 `tempfile.mkdtemp` 为每组写临时换行肽文件 + 临时输出，
   读回后合并。临时目录未主动清理（系统 temp，量小可忽略）。

---

## repo 结构（参考，pip 包内同构）

```
mhcnuggets/
  src/
    predict.py            ← 核心 predict() 入口（本部署调用）
    find_closest_mhcI.py  ← closest_allele 模糊匹配（确定 HLA 无星号格式）
    models.py             ← mhcnuggets_lstm 架构 + get_predictions
    dataset.py            ← mask_peptides / tensorize / map_proba_to_ic50
  saves/production/        ← 内置权重 <allele>_BA_to_HLAp.h5 / _BA.h5
  data/production/         ← examples_per_allele.pkl 等
```

---

## 本部署四件套

| 文件 | 作用 |
|------|------|
| `prep_input.py` | uniq_pep_hla.csv → 肽长+MHC-I 过滤 + HLA 去星号 → `mhcnuggets_input.csv`（含 map 列）+ `mhcnuggets_unsupported.csv` |
| `run_mhcnuggets.py` | 按 allele 分组调官方 `predict(class_='I')` → `mhcnuggets_raw.csv`（peptide, HLA_Allele, ic50）；`--smoke N` |
| `parse_output.py` | raw join universe（MT/WT 双打分）+ 取负方向归一 → `MHCnuggets_DS1DS2_scores.csv` |
| `NOTES.md` | 本文件 |
