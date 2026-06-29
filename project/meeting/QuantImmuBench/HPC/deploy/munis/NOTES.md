# MUNIS — 部署说明（QuantImmuBench §工具部署，免疫原侧强补位）

> 建档：2026-06-29。服务 quantimmu-bench 工具部署，免疫原侧 lever=补满到 20（强补位 MUNIS）。
> 官方 repo：github.com/jwohlwend/munis （Wohlwend et al.）
> 论文：MUNIS, *Nature Machine Intelligence* 2025（ESM-2 + 抗原加工 LSTM，肽-HLA-I 呈递/免疫显性）。
> 许可：**CC-BY-4.0**（Zenodo 记录 license 字段已核实）—— **数字可自由发布**。
> 权重：Zenodo `10.5281/zenodo.14219509`，文件 `jwohlwend/munis-v1.0.0.zip`（840 MB，含 models/ 权重）。

---

## 工具简介

MUNIS 用 **ESM-2 蛋白语言模型（esm2_t6_8M_UR50D，8M）** 编码 `[cls] HLA-pseudo [mask] peptide [eos]`，
外接 **抗原加工分支（flanking 的 BiLSTM，仅 use_flanks 模式）** + 线性分类头，
输出单一连续 **EL（eluted-ligand / 呈递）概率 score ∈ [0,1]**。5 模型 ensemble。

- 输入：肽 **8–15mer** + **HLA-I**（人类 HLA-A/B/C；SEQUENCES 另含鼠/牛等非人类，本部署只用 A/B/C）。
- 输出本质：**presentation / immunogenicity 连续分**，**越高越强**（直接横评，归类免疫原性侧工具）。

---

## 4 类信息（工具横评标准格式）

| 项 | 值 |
|----|----|
| 工具版本 | MUNIS v1.0.0（Zenodo munis-v1.0.0，GitHub main 同源） |
| 许可 | **CC-BY-4.0**（数字可自由发布） |
| 输入格式 | CSV 列 `pep, mhc, left, right`；肽 8–15mer；**HLA 编码 `HLA-A02:01`（无星号 2 字段，= SEQUENCES 键）** |
| 输出分数 | `score` ∈ [0,1]（EL 呈递概率，**越高越强**，无需翻转） |
| 运行平台 | Linux/WSL2 + GPU 优先（CPU 兜底）；torch 2.3.1 + fair-esm 2.0.0 + pytorch-lightning 2.0.2 |
| 分类 | 免疫原性侧（presentation/immunogenicity 直接预测，非纯 BA 代理） |

---

## 🔑 HLA 编码格式（曾标 TODO，**已查官方源核实**）

**结论：MUNIS 内部 allele 键 = `HLA-A02:01`（去星号 + 截到前 2 字段）。**

来源（2026-06-29 核自 GitHub main）：
- `munis/seqs.py` 的 `SEQUENCES` 字典键即 `HLA-A02:01` / `HLA-A02:02` / `HLA-B07:02` …（无星号 2 字段），
  值是 MHC 全长伪序列（process 时取前 `MIN_LEN=180` 残基）。
- `predict.py::clean_mhc_name(mhc)`：`mhc.replace("*","")` + `":".join(split(":")[:2])`
  —— 去星号、截 2 字段。
- `predict.py::PredictionDataset.process()`：`self.sequences[sample["mhc"].replace("*","")][:MIN_LEN]`
  —— **CSV 输入路径只做 `.replace("*","")`，不再截字段**。

⇒ 本部署 `prep_input.py` 把 universe 的 `HLA-A*02:01` 归一为 `HLA-A02:01`（照抄 `clean_mhc_name`）
写进 `mhc` 列，**恰为 SEQUENCES 键，process 的 `.replace("*","")` 对它是 no-op，保证命中**。
原始带星号 `HLA_Allele` 列穿透保留，供 parse 回贴 universe。

> ⚠️ allele 不在 SEQUENCES 字典内的行会让 process() KeyError 崩整批 → `run_munis.py`
> 在调官方前 `import munis.seqs.SEQUENCES` 二次过滤，剔到 `munis_unsupported_allele.csv`（parse 阶段 NaN）。

---

## flanking（left / right）说明

- 官方输入需 `left` / `right` 两列（N/C 端 flanking 序列，喂抗原加工 BiLSTM 分支）。
- **本部署无 flanking**（universe 只有 subpeptide，无上下文蛋白序列）→ **不传 `--use_flanks`**：
  - 官方 `predict.py` 在无 `--use_flanks` 时把 `left=right="GGGGG"` 并加载 **`models/no-flanks/` ensemble**
    （该套权重训练时就不依赖 flank）。这是无 flank 场景的官方正确用法，非私自改动。
  - `prep_input.py` 把 left/right 写空字符串，run 阶段交官方覆盖为 GGGGG。
- 若未来拿到 flanking，可给 `run_munis.py --use-flanks`（透传官方 `--use_flanks`，改用 `models/flanks/`）。

---

## 分数方向（越高越免疫原，无需翻转）

| 原始列 | 原始方向 | 输出列 | 变换 |
|--------|----------|--------|------|
| `score` | EL 呈递概率 [0,1]，**越高越强** | `MT/WT_MUNIS` | **直接用（不翻转）** |

来源：`predict.py::predict()` —— `logits = torch.sigmoid(model(...))`（ensemble [5,B] logits）
→ `.mean(dim=0)`（5 模型平均）→ `score`。sigmoid 概率，越高越可能呈递/免疫原。
与 MHCnuggets 的 ic50（越低越强，需取负）相反 —— **MUNIS 无需任何方向归一**。

---

## 安装 + 权重下载（供主线跑，本地/HPC 均可；我不下不跑）

```bash
# Step 0a: 下载 Zenodo 权重包（840MB，含 repo + models/ 权重）
mkdir -p HPC/deploy/munis/zenodo
wget -O HPC/deploy/munis/zenodo/munis-v1.0.0.zip \
  "https://zenodo.org/api/records/14219509/files/jwohlwend/munis-v1.0.0.zip/content"

# Step 0b: 解压（得到含 predict.py + munis/ + models/flanks + models/no-flanks 的目录）
cd HPC/deploy/munis/zenodo && unzip munis-v1.0.0.zip && cd -
#   解压目录名形如 jwohlwend-munis-xxxxxxx/ —— 记为 <MUNIS_REPO>
#   TODO（主线下载后核）：确认解压根目录确含 predict.py 与 models/no-flanks/model{1..5}.ckpt；
#                        若 zip 内层多一级目录，--munis-repo 指到含 predict.py 的那一层。

# Step 0c: 建隔离环境装依赖（官方在 python 3.10 + 下列 pin 测过）
conda create -n munis_env python=3.10 -y && conda activate munis_env
cd <MUNIS_REPO>
pip install -r requirements.txt   # torch==2.3.1 fair-esm==2.0.0 pytorch-lightning==2.0.2 ...
pip install .                     # 装 munis 包（run_munis.py import munis.seqs 需要）
cd -
```

> GitHub clone 不含大权重文件（840MB 在 Zenodo），**务必用 Zenodo zip 拿 models/**。

---

## 运行流水线（供主线跑）

```bash
# Step 1: 准备输入（肽长 8-15 + MHC-I 过滤 + HLA 归一为 SEQUENCES 键）
python HPC/deploy/munis/prep_input.py
#   先 --smoke 50 验格式：
#   python HPC/deploy/munis/prep_input.py --smoke 50

# Step 2: 烟测（5 肽 × HLA-A*02:01 验官方算子/列结构；需先装好权重）
python HPC/deploy/munis/run_munis.py --munis-repo <MUNIS_REPO> --smoke 5

# Step 3: 全量预测（~53K 对，调官方 predict.py，no-flanks ensemble，GPU 优先）
python HPC/deploy/munis/run_munis.py --munis-repo <MUNIS_REPO>

# Step 4: 回贴 universe（34247 行输出）
python HPC/deploy/munis/parse_output.py
```

最终输出：`scripts/out/newtools/MUNIS_DS1DS2_scores.csv`
（列：Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide, MT_MUNIS, WT_MUNIS）

---

## 显存 / 算力

- backbone = ESM-2 **8M（esm2_t6_8M_UR50D）**，5 模型 ensemble，模型极小 → **8GB GPU 充裕**，CPU 也能跑。
- 官方 README：example 蛋白 GPU 几秒、CPU <5 min。全量 ~53K 对 GPU 预计分钟级。
- ESM-2 权重首次经 `torch.hub` 下载到 `--cache`（默认 `HPC/deploy/munis/esm_cache`）。

---

## 已知坑

1. **HLA 必须是 SEQUENCES 键格式**：3 字段或带星号会让 process() 的字典查找 miss/KeyError。
   prep 用 `clean_mhc_name` 归一为 `HLA-A02:01`；run 再用 SEQUENCES 集合二次过滤剔除未知 allele。
2. **必须用 Zenodo zip 拿权重**：GitHub repo 不含 840MB 的 `models/` ckpt。`--munis-repo` 指向解压目录。
3. **解压内层目录层级 TODO**：Zenodo zip 解压后可能多包一层（`jwohlwend-munis-<hash>/`）；
   `--munis-repo` 必须指到**直接含 `predict.py` 与 `models/`** 的那层（主线解压后 `ls` 核一眼）。
4. **predict.py 硬编码 `num_workers=4` + `pin_memory=True`**：官方原样，Linux/HPC 无碍；
   **勿在 Windows 原生跑**（fork/pin_memory 不友好）—— 本部署规定 Linux/WSL2/HPC 跑。我们不改官方脚本。
5. **flanking 缺省**：本部署 no-flanks（left/right=GGGGG + models/no-flanks）。报告须标此 caveat：
   分数不含真实 N/C 端加工上下文（与论文 flanks 模式略有差异，但 universe 无 flank 数据，这是唯一可行口径）。
6. **依赖 pin 较严**：torch==2.3.1 等。建议独立 conda env，别与项目其他 torch 版本混（OMP/版本冲突）。
7. **CC-BY-4.0**：可发数字，引用时标注 MUNIS 论文 + repo（CC-BY 要求署名）。

---

## 本部署四件套

| 文件 | 作用 |
|------|------|
| `prep_input.py` | uniq_pep_hla.csv → 肽长 8-15 + MHC-I 过滤 + HLA 归一为 `HLA-A02:01` → `munis_input.csv`（pep,mhc,left,right,HLA_Allele,source）+ `munis_unsupported.csv` |
| `run_munis.py` | 二次过滤未知 allele → subprocess 调官方 `predict.py`（no-flanks ensemble，GPU 优先 CPU 兜底）→ `munis_raw.csv`（peptide, HLA_Allele, score）；`--smoke N` |
| `parse_output.py` | raw join universe（(peptide,HLA) MT/WT 双 key 双打分，方向不翻转）→ `MUNIS_DS1DS2_scores.csv` |
| `NOTES.md` | 本文件 |

---

## 官方源出处（2026-06-29 核自 GitHub main）

- `predict.py` —— CLI（`--peptides`/`--fasta`/`--mhc`/`--output`/`--min_len 8`/`--max_len 15`/`--device`/
  `--use_flanks`/`--checkpoint`）；input CSV 列 `pep,mhc,left,right`；output 加 `score`；
  `clean_mhc_name`；默认 ensemble `models/{flanks,no-flanks}/model{1..5}.ckpt`；
  `predict()` 中 `sigmoid(logits).mean(dim=0)`。
- `munis/seqs.py` —— `SEQUENCES` 字典（键 `HLA-A02:01` 等）、`MIN_LEN=180`。
- `munis/model.py` —— `MunisModel`（ESM-2 + use_flanks 时 BiLSTM 加工分支 + `fc_el` 头）、
  `EnsembleMunisModel`（5 模型 stack）。
- `requirements.txt` —— torch==2.3.1 / pytorch-lightning==2.0.2 / fair-esm==2.0.0 / numpy==1.26.4 / pandas==2.2.2 …
- Zenodo `10.5281/zenodo.14219509` —— `jwohlwend/munis-v1.0.0.zip`（840 MB），license `cc-by-4.0`。
