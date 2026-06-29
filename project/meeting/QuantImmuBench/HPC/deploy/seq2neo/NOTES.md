# Seq2Neo immuno 部署笔记

> 服务：quantimmu-bench G1 工具补齐 — apples-to-apples 免疫原性扩充
> Seq2Neo 规格由 researcher 联网核实（带源）。本 kit 由 coder 写好备用，**未运行**
> （Seq2Neo linux-only + netCTLpan 1.1.b 未部署，本地 Windows 跑不了）。

---

## 0. 当前阻塞清单（kit 就绪，跑不了的原因）

| 阻塞 | 状态 | 解法 |
|---|---|---|
| **netCTLpan == 1.1.b** | ⚠️ **未独立部署，DTU 学术许可待申请（真阻塞）** | 走 DTU Health Tech 申请页拿 netCTLpan-1.1，装到 PATH |
| netMHCpan == 4.1.b | ✅ 已有（WSL `~/quantimmu/ext_tools/netMHCpan-4.1`） | 确保在 PATH |
| linux-only | ⚠️ conda 包仅 linux-64，无 win/osx build | 在 WSL / HPC 跑，不在本机 Windows |
| 12mer 行为 | ⚠️ TODO 未实跑确认 | prep_input.py 已保守跳过 12mer（只留 8-11mer） |
| cnn_results 分数列名 | ⚠️ TODO 未实跑确认 | parse_output.py 自动猜测 + `--score-col` 可锁定 |

**结论：netCTLpan 到位 + 在 linux 环境，即可按 §10 命令链跑。**

---

## 1. 许可证（License）

- **Seq2Neo 本体**：AFL-3.0（Academic Free License）。学术非商用自由使用。
- **依赖 netMHCpan-4.1 / netCTLpan-1.1**：DTU Health Tech 学术许可
  （academic free，需到 DTU 申请页同意条款后下载；**不可随包分发**）。
  - netMHCpan-4.1：已申请并装好（WSL）。
  - **netCTLpan-1.1：尚未申请/部署 → pending_consent 阻断本工具。**

# TODO: 跑出结果发表前，确认 Seq2Neo + netCTLpan 的引用 + 许可合规（DTU 条款）。

---

## 2. 安装（linux，HPC / WSL）

**conda（推荐，v2.1，linux-64 only，2023-02-16）：**

```bash
conda create -n seq2neo python=3.8 -y
conda activate seq2neo
conda install -c liuxslab seq2neo
# 验证
seq2neo --help
seq2neo immuno --help
```

**docker（备选，镜像 ~7.46GB）：**

```bash
docker pull liuxslab/seq2neo:latest
docker run --rm -v $PWD:/data liuxslab/seq2neo:latest \
  seq2neo immuno --mode multiple --inputfile /data/seq2neo_input.csv --outdir /data/out
```

**硬依赖（手动装、在 PATH 中可见）：**
- `netMHCpan` == 4.1.b
- `netCTLpan` == 1.1.b  ⚠️ 待申请部署（见 §0）

装好后 `which netMHCpan netCTLpan` 应都能找到。

---

## 3. CLI（researcher 核实）

```bash
seq2neo immuno \
  --mode multiple \
  --inputfile /path/to/seq2neo_inputs/seq2neo_input.csv \
  --outdir   /path/to/seq2neo_inputs/seq2neo_out
```

| 参数 | 说明 | 值 |
|---|---|---|
| `immuno` | 子命令：免疫原性预测 | 固定 |
| `--mode multiple` | 批量模式（多条肽） | **固定 multiple** |
| `--inputfile` | 输入 CSV（两列 `Pep,HLA`） | seq2neo_input.csv |
| `--outdir` | 输出目录 | seq2neo_out/ |

`run_seq2neo.py` 已封装此调用（`--extra` 可透传额外参数，如线程数）。

---

## 4. 输入 CSV 格式（researcher 核实，确切列名）

**文件**：`seq2neo_inputs/seq2neo_input.csv`（由 `prep_input.py` 生成）

```
Pep,HLA
ADTSEARPFW,HLA-B44:02
RLETIRNPK,HLA-A24:02
RLETIRNPK,HLA-A03:01
...
```

- 列 0：**`Pep`**（P 大写！peptide 序列）
- 列 1：**`HLA`**（HLA allele，**`HLA-B44:02` 格式——无星号、无空格**）
- 含 1 行表头

**只含 8-11mer**（12mer / 越界肽长在 prep 阶段被跳过，见 §7）。

---

## 5. HLA allele 格式转换（关键，researcher 核实）

| 来源（benchmark universe） | 转换后（Seq2Neo） |
|---|---|
| `HLA-A*02:01` | `HLA-A02:01` |
| `HLA-B*44:02` | `HLA-B44:02` |

**规则：去掉星号 `*`（同时 strip 空格）。** 实现见 `prep_input.py::to_seq2neo_hla()`：
```python
hla.strip().replace("*", "").replace(" ", "")
```
parse_output.py 回贴时把 universe 的 `HLA_Allele` 用**同一函数**转换再做 join，保证 key 对齐。

# TODO: 若实跑发现 cnn_results.csv 的 HLA 列保留了星号，需调整 join（见 parse_output.py 顶注）。

---

## 6. 输出文件格式（researcher 核实）

**目录**：`seq2neo_inputs/seq2neo_out/`

| 文件 | 说明 |
|---|---|
| `cnn_results.csv` | **免疫原性分（越大越免疫原，阈值 >0.5）** |
| `immuno_input_file.csv` | 中间特征文件（不直接用） |

**方向**：分数越大越免疫原 → 与 benchmark 其他工具一致，无需翻转。

# TODO（实跑后必须确认并回填）:
#   - cnn_results.csv 的**确切分数列名**（parse_output.py 默认猜 immunogenicity/score/...，
#     用 `--score-col <真名>` 锁定）。
#   - cnn_results.csv 的 peptide / HLA 列名（默认猜 Pep / HLA，用 --pep-col/--hla-col 覆盖）。

---

## 7. 肽长过滤（12mer 处理）

Seq2Neo netMHCpan/netCTLpan 链支持 **8-11mer**。

- prep_input.py 只写入 8 ≤ len ≤ 11 的肽；**12mer 及越界肽长被跳过**（打印跳过数）。
- 这些被跳过的肽在 parse_output.py 回贴时不在 score_map 中 → 自然得 **NaN**（空值）。

# TODO: 12mer 在 Seq2Neo 内部的确切行为（报错 / 静默丢弃）未实跑确认。
#       当前保守跳过以免整批崩。装后实跑可核实是否能放宽。

---

## 8. 输出回贴 → benchmark scores CSV

`parse_output.py` 读 cnn_results.csv → 按 `(peptide, HLA无星号)` join `universe.csv`
→ 写 `scripts/out/newtools/Seq2Neo_DS1DS2_scores.csv`：

- 列 = universe 全部列 + **`MT_Seq2Neo`** + **`WT_Seq2Neo`**
- 方向：值越大越免疫原（无翻转）
- 12mer / 不支持的行 → 空值（NaN）

（注：仿 bigmhc parse_output.py 同款 join 模式；任务单提到的 "bb_idx" 在本 universe schema
 中无对应列，故沿用 bigmhc 的「universe 全列 + MT/WT」输出格式，universe 自带 Peptide_ID 作行标识。）

---

## 9. Windows 本地说明

**Seq2Neo 不能在本机 Windows 跑**（conda 包仅 linux-64）。
- `prep_input.py` / `parse_output.py` 是纯 pandas/csv，本地 Windows 可跑（仅做输入准备 / 输出解析）。
- `run_seq2neo.py` 必须在 WSL / HPC（已装 seq2neo + netMHCpan + netCTLpan）跑。

---

## 10. netCTLpan 到位后的完整命令链（主线跑）

```bash
# === 在本机 Windows 或 linux 均可（纯 csv 处理）===
# 步骤 1：生成输入（全量；HLA 转无星号 + 过滤 12mer）
python HPC/deploy/seq2neo/prep_input.py
#   -> seq2neo_inputs/seq2neo_input.csv（列 Pep,HLA）

# === 以下必须在 linux/WSL/HPC（已装 seq2neo + netMHCpan-4.1 + netCTLpan-1.1）===
# 步骤 2：跑 Seq2Neo immuno
python HPC/deploy/seq2neo/run_seq2neo.py
#   -> seq2neo_inputs/seq2neo_out/cnn_results.csv

# 步骤 3：解析输出，回贴 universe（实跑后用真分数列名锁定 --score-col）
python HPC/deploy/seq2neo/parse_output.py --score-col <实跑确认的分数列名>
#   -> scripts/out/newtools/Seq2Neo_DS1DS2_scores.csv
```

**烟测（先验通管道，10 条）：**

```bash
python HPC/deploy/seq2neo/prep_input.py --smoke 10
python HPC/deploy/seq2neo/run_seq2neo.py --smoke
python HPC/deploy/seq2neo/parse_output.py --smoke --score-col <真列名>
head scripts/out/newtools/Seq2Neo_DS1DS2_scores_smoke.csv
```

---

## 11. 已知坑

1. **netCTLpan 阻塞**：未部署前 `run_seq2neo.py` 必卡/报错。先申请 DTU 许可装好。
2. **linux-only**：本机 Windows 直跑必失败；用 WSL/HPC。
3. **HLA 星号**：benchmark 是 `HLA-A*02:01`，Seq2Neo 要 `HLA-A02:01`。prep 已自动去星号。
4. **分数列名 TODO**：cnn_results.csv 列名未实跑确认，parse 自动猜 + `--score-col` 兜底。
5. **12mer**：被 prep 跳过（保守），覆盖率会因此 <100%（预期，非 bug）。
6. **PATH**：netMHCpan / netCTLpan 必须在 PATH（Seq2Neo 内部 subprocess 调它们；
   曾踩 MixMHCpred PATH 缺 numpy 的坑，注意 conda env 激活）。
