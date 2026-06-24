# Wave-3 ELISpot Benchmark — 执行手册

工具：PRIME / ImmuneApp / deepHLApan  
主线：只需按顺序执行下面的命令；**脚本本身已内嵌过滤/格式转换/map 逻辑，不需要手工改文件**。

---

## 0. 先决条件

| 工具 | 运行位置 | Conda 环境 | 路径 |
|---|---|---|---|
| PRIME | HPC | `envs/prime` | `tools_repos/PRIME/` |
| ImmuneApp | HPC | `envs/immuneapp` | `tools_repos/ImmuneApp/` |
| deepHLApan | 本机 WSL2 | docker `biopharm/deephlapan:v1.1` | — |

---

## 1. 生成输入文件（本机，Windows）

```bash
python scripts/wave3_bench/prep_inputs_wave3.py \
    --backbone scripts/out/master_backbone.csv \
    --out-dir  scripts/out
```

产出（均在 `scripts/out/`）：

| 文件/目录 | 用途 |
|---|---|
| `prime_input_<allele>/peps_MT.txt` | PRIME MT 肽段（每 allele 一目录） |
| `prime_input_<allele>/peps_WT.txt` | PRIME WT 肽段 |
| `prime_input_map_MT.csv` | unique(peptide, allele) → bb_idx（MT） |
| `prime_input_map_WT.csv` | 同（WT） |
| `immuneapp_input_<allele>/peps_MT.txt` | ImmuneApp 按 allele 目录（allele 目录名中 `*:` 替换为 `_`） |
| `immuneapp_input_<allele>/peps_WT.txt` | |
| `immuneapp_input_map_MT.csv` | |
| `immuneapp_input_map_WT.csv` | |
| `deephlapan_input_MT.csv` | deepHLApan MT 整张 CSV（Annotation,HLA,peptide） |
| `deephlapan_input_WT.csv` | deepHLApan WT 整张 CSV |
| `deephlapan_input_map_MT.csv` | |
| `deephlapan_input_map_WT.csv` | |

---

## 2. 上传输入文件到 HPC

上传整个 `scripts/out/prime_input_*/` + `scripts/out/immuneapp_input_*/` 目录到 HPC 工作目录（如 `~/quantimmu/inputs/`）。deepHLApan 输入留本机 WSL2 用。

---

## 3. 在 HPC 跑 PRIME

### 3a. HLA 格式说明
- master_backbone 原格式：`HLA-A*24:02`
- PRIME 需要：`A2402`（去 `HLA-` 前缀 + 去星号 + 去冒号）
- prep_inputs_wave3.py 已自动转换，目录名即为 PRIME allele 格式

### 3b. 肽长过滤
- PRIME 支持 8–14 mer；超界行已跳过（map 中以 `SKIPPED_LEN:` 前缀标注，不会进输入 txt）

### 3c. 按 allele 循环跑（HPC）

```bash
conda activate envs/prime
PRIME_DIR=tools_repos/PRIME
MIX_DIR=<MixMHCpred路径>   # PRIME 依赖 MixMHCpred，需提前确认路径

INPUT_BASE=~/quantimmu/inputs
OUTPUT_BASE=~/quantimmu/prime_out

for allele_dir in ${INPUT_BASE}/prime_input_*/; do
    allele=$(basename "$allele_dir")                     # e.g. prime_input_A2402
    allele_code=${allele#prime_input_}                   # e.g. A2402

    # MT 侧
    out_mt="${OUTPUT_BASE}/${allele_code}/out_MT.txt"
    mkdir -p "$(dirname $out_mt)"
    ${PRIME_DIR}/PRIME \
        -i "${allele_dir}/peps_MT.txt" \
        -o "${out_mt}" \
        -a "${allele_code}" \
        -mix "${MIX_DIR}"

    # WT 侧
    out_wt="${OUTPUT_BASE}/${allele_code}/out_WT.txt"
    ${PRIME_DIR}/PRIME \
        -i "${allele_dir}/peps_WT.txt" \
        -o "${out_wt}" \
        -a "${allele_code}" \
        -mix "${MIX_DIR}"
done
```

输出结构：`~/quantimmu/prime_out/<allele>/out_MT.txt` + `out_WT.txt`

merge 时 `--prime-result-MT ~/quantimmu/prime_out/`（传目录，merge_wave3.py 自动扫所有 .txt）。  
注意：若某 allele 的 peps_MT.txt 为空（该 allele 下无有效肽），PRIME 可能报错，跳过即可。

---

## 4. 在 HPC 跑 ImmuneApp

### 4a. HLA 格式说明
- ImmuneApp 接受标准格式 `HLA-A*24:02`，无需转换
- 目录名中 `*` → `_`、`:` → `_`（如 `immuneapp_input_HLA-A_24_02`）

### 4b. 肽长过滤
- ImmuneApp 支持 8–15 mer；超界行已跳过

### 4c. 按 allele 循环跑（HPC）

```bash
conda activate envs/immuneapp
IMMUNEAPP_DIR=tools_repos/ImmuneApp

INPUT_BASE=~/quantimmu/inputs
OUTPUT_BASE=~/quantimmu/immuneapp_out

for allele_dir in ${INPUT_BASE}/immuneapp_input_*/; do
    dirname=$(basename "$allele_dir")                     # e.g. immuneapp_input_HLA-A_24_02
    allele_safe=${dirname#immuneapp_input_}               # e.g. HLA-A_24_02
    # 还原标准 HLA 格式（_ 还原为 * 和 :）
    # HLA-A_24_02 → HLA-A*24:02  （第一个 _ 是 *，第二个是 :）
    allele_std=$(echo "$allele_safe" | sed 's/_\([0-9]\)/*\1/' | sed 's/_\([0-9]\)/:\1/')
    # 上面 sed 仅处理 _DD 形式；对于格式不标准的 allele 需人工确认

    out_dir_mt="${OUTPUT_BASE}/${allele_safe}/MT"
    out_dir_wt="${OUTPUT_BASE}/${allele_safe}/WT"
    mkdir -p "${out_dir_mt}" "${out_dir_wt}"

    # MT 侧
    python ${IMMUNEAPP_DIR}/ImmuneApp_immunogenicity_prediction.py \
        -f "${allele_dir}/peps_MT.txt" \
        -a "${allele_std}" \
        -o "${out_dir_mt}"

    # WT 侧
    python ${IMMUNEAPP_DIR}/ImmuneApp_immunogenicity_prediction.py \
        -f "${allele_dir}/peps_WT.txt" \
        -a "${allele_std}" \
        -o "${out_dir_wt}"
done
```

输出：每个 `out_dir_mt/` 下含 `ImmuneApp_Immunogenicity_predictions.tsv`。

merge 时 `--immuneapp-result-MT ~/quantimmu/immuneapp_out/`（传顶层目录，脚本递归扫所有 .tsv）。  
注意：`-a` 参数恢复标准格式的 sed 命令对少数 allele（如 B7 超类群）可能有偏差，建议验证 1-2 条。

---

## 5. 在本机 WSL2 跑 deepHLApan

### 5a. HLA 格式说明
- 原格式：`HLA-A*24:02`
- deepHLApan 需要：`HLA-A24:02`（去星号，保留 HLA- 和冒号）
- prep_inputs_wave3.py 已自动转换，已写入 CSV 的 HLA 列

### 5b. 肽长过滤
- deepHLApan 支持 8–15 mer；超界行已跳过

### 5c. 运行（WSL2）

```bash
# WSL2 内部，假设 scripts/out/ 挂载在 /mnt/d/YJ-Agent/.../scripts/out/
MT_INPUT=/mnt/d/YJ-Agent/project/meeting/QuantImmuBench/scripts/out/deephlapan_input_MT.csv
WT_INPUT=/mnt/d/YJ-Agent/project/meeting/QuantImmuBench/scripts/out/deephlapan_input_WT.csv
OUT_MT=/mnt/d/YJ-Agent/project/meeting/QuantImmuBench/scripts/out/deephlapan_out_MT
OUT_WT=/mnt/d/YJ-Agent/project/meeting/QuantImmuBench/scripts/out/deephlapan_out_WT

mkdir -p "${OUT_MT}" "${OUT_WT}"

docker run --rm \
    -v "$(dirname $MT_INPUT):/data" \
    biopharm/deephlapan:v1.1 \
    deephlapan -F /data/deephlapan_input_MT.csv -O /data/deephlapan_out_MT

docker run --rm \
    -v "$(dirname $WT_INPUT):/data" \
    biopharm/deephlapan:v1.1 \
    deephlapan -F /data/deephlapan_input_WT.csv -O /data/deephlapan_out_WT
```

输出：`deephlapan_out_MT/<name>_predicted_result.csv`（列 Annotation,HLA,Peptide,binding score,immunogenic score）。

merge 时传具体 CSV 路径：`--deephlapan-result-MT scripts/out/deephlapan_out_MT/deephlapan_input_MT_predicted_result.csv`（文件名由 deepHLApan 根据输入 CSV 名决定，请确认实际文件名）。

---

## 6. 下载 HPC 输出到本机

把 `~/quantimmu/prime_out/` 和 `~/quantimmu/immuneapp_out/` 下载到本机（如 `scripts/out/prime_out/` 和 `scripts/out/immuneapp_out/`）。

---

## 7. 合并结果（本机，Windows）

```bash
python scripts/wave3_bench/merge_wave3.py \
    --base                 scripts/out/merged_all_tools_5tools.xlsx \
    --backbone             scripts/out/master_backbone.csv \
    --map-dir              scripts/out \
    --prime-result-MT      scripts/out/prime_out \
    --prime-result-WT      scripts/out/prime_out \
    --immuneapp-result-MT  scripts/out/immuneapp_out \
    --immuneapp-result-WT  scripts/out/immuneapp_out \
    --deephlapan-result-MT scripts/out/deephlapan_out_MT/<name>_predicted_result.csv \
    --deephlapan-result-WT scripts/out/deephlapan_out_WT/<name>_predicted_result.csv \
    --out-dir              scripts/out
```

产出：`scripts/out/merged_all_tools_8tools.xlsx`（主干 + 5tools 原有列 + 新 6 列）。

---

## 8. 注意事项与常见坑

### 肽长超界处理
- map 中 `SKIPPED_LEN:` 前缀的 key 对应超界肽，不写进输入文件、不跑、不填分数（NaN）
- PRIME >14 mer、ImmuneApp/deepHLApan >15 mer 会被跳过

### PRIME 空 allele 目录
- 若某 allele 下所有肽均超界，`peps_MT.txt` 为空文件，直接跳过该 allele 的 PRIME 运行

### deepHLApan Annotation 是 bb_idx
- prep_inputs_wave3.py 写的 Annotation 字段 = bb_idx 整数字符串（如 `"12345"`）
- merge_wave3.py 直接用 Annotation 整数定位 backbone 行，**无需 map 文件**
- 若 deepHLApan 输出修改了 Annotation 列（如只输出部分行），merge 会正确处理（跳过缺失行）

### ImmuneApp -a allele 格式
- 命令行 `-a` 参数传标准格式（`HLA-A*24:02`），**不传 ImmuneApp 目录名的安全格式**
- 上面 bash 脚本用 sed 从目录名还原，建议在正式跑前抽查 3-5 个 allele 对照 master_backbone 确认

### PRIME -a 与 Score_bestAllele
- PRIME 一次可传多 allele，但建议按单一 allele 目录跑，Score_bestAllele 即为该 allele 分数
- 若多 allele 混跑，merge 时会从 Score_bestAllele 列取分（最高分 allele），而非目标 HLA 的分；单 allele 跑可避免此歧义

### 第一批结果不碰
- merge_wave3.py 以 merged_all_tools_5tools.xlsx 为底，**只追加 6 列**，不修改第一批已有列
- 若 --base 不存在则用 master_backbone（不含第一批分数，仍可跑，但需事后手工 join）
