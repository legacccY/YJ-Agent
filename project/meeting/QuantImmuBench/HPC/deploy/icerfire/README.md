# ICERFIRE 1.0 — QuantImmuBench §Tier-2 部署说明

> 服务项目：quantimmu-bench §Tier-2 lever=部署 ICERFIRE apples-to-apples 免疫原性工具

---

## 工具简介

ICERFIRE 1.0（DTU Health Tech）= 新抗原免疫原性预测工具，需 MT+WT 配对肽段输入。
学术下载申请：health-software@dtu.dk

**pending_DTU_consent = True**：binary 尚未在 HPC，所有脚本和输出均标此字段，提示使用条款待 DTU 书面确认。获得书面确认后将 `pending_DTU_consent` 列改为 `False`。

---

## 入口脚本

```
bashscripts/ICERFIRE.sh
```

CLI 形式：

```bash
./ICERFIRE.sh -f <input_file> -a <add_expr true/false> -u <user_exp true/false>
```

| 参数 | 说明 |
|---|---|
| `-f <input_file>` | 无表头 CSV，列序 `mut,wt,HLA` |
| `-a false` | 无基因表达数据（DS1/DS2 均无 TPM → 固定用 false） |
| `-u false` | 不使用用户自定义表达（同上）|

无表达数据时 ICERFIRE 自动选用 `ICERFIRE_ExprFalse.pkl` 模型。

---

## 部署前必做：修改 ICERFIRE.sh 顶部 3 个 config 变量

`bashscripts/ICERFIRE.sh` 顶部有 3 个路径变量需替换为 HPC 实际路径：

```
USERDIR=/gpfs/work/bio/jiayu2403/quantimmu/ext_tools/ICERFIRE
PEPXDIR=${USERDIR}/pepx/
NETMHCPAN=/gpfs/work/bio/jiayu2403/quantimmu/ext_tools/netMHCpan-4.1/netMHCpan
```

一次性 sed 替换命令（在 HPC login 节点执行，仅需一次）：

```bash
ICERFIRE_SH=/gpfs/work/bio/jiayu2403/quantimmu/ext_tools/ICERFIRE/bashscripts/ICERFIRE.sh
sed -i "s|^USERDIR=.*|USERDIR=/gpfs/work/bio/jiayu2403/quantimmu/ext_tools/ICERFIRE|" "${ICERFIRE_SH}"
sed -i "s|^NETMHCPAN=.*|NETMHCPAN=/gpfs/work/bio/jiayu2403/quantimmu/ext_tools/netMHCpan-4.1/netMHCpan|" "${ICERFIRE_SH}"
sed -i 's|^PEPXDIR=.*|PEPXDIR="${USERDIR}/pepx/"|' "${ICERFIRE_SH}"
```

---

## 依赖安装

### pepx-export.db

ICERFIRE 内部 KernDist/PepX 查询依赖 SQLite 数据库，需单独下载：

```
https://services.healthtech.dtu.dk/services/ICERFIRE-1.0/pepx-export.db
```

下载后放到：`${USERDIR}/pepx/pepx-export.db`（对应 `PEPXDIR` 变量）。

### Python 环境（py3.9 + 指定依赖版本）

ICERFIRE requirements.txt 固定版本：

```
scikit-learn==1.0.2
numpy==1.21.5
pandas==1.4.2
```

建议建独立 conda 环境：

```bash
conda create -n icerfire_env python=3.9
conda activate icerfire_env
pip install scikit-learn==1.0.2 numpy==1.21.5 pandas==1.4.2
```

### 其他依赖

- `sqlite3`（系统工具，通常已有）
- `netMHCpan-4.1`（同批部署，路径见 `NETMHCPAN` 变量）

---

## 输入格式

- **无表头 CSV**，列顺序固定：`mut,wt,HLA`
  - `mut`：突变肽（MT_Subpeptide，8-14mer）
  - `wt`：野生肽（WT_Subpeptide，8-14mer）
  - `HLA`：HLA 等位基因（格式见下方 HLA 白名单节）
- 可选第 4 列 `TPM`（表达量，DS1/DS2 无此数据，直接省略）
- **必须 MT+WT 配对**：WT 为空的行跳过，不写入输入文件

### HLA 格式转换

master_backbone.csv 中 `HLA_Allele` 为标准格式（如 `HLA-A*02:01`），ICERFIRE 要求去掉星号和冒号：

```
HLA-A*02:01  →  HLA-A0201
HLA-B*40:01  →  HLA-B4001
HLA-C*07:02  →  HLA-C0702
```

转换函数（prep_icerfire.py）：

```python
def hla_to_icerfire(h):
    return h.replace("*", "").replace(":", "")
```

---

## HLA 白名单（ICERFIRE 1.0 支持的 65 个等位基因）

不在白名单的行不写入 `icerfire_input.csv`，改写入 `icerfire_unsupported_bbidx.csv`，parse 阶段填 NaN。

```
HLA-A0101  HLA-A0201  HLA-A0202  HLA-A0203  HLA-A0205
HLA-A0206  HLA-A0210  HLA-A0211  HLA-A0224  HLA-A0301
HLA-A0302  HLA-A1101  HLA-A1102  HLA-A2402  HLA-A2501
HLA-A2601  HLA-A2902  HLA-A3001  HLA-A3002  HLA-A3101
HLA-A3301  HLA-A6801  HLA-A6802  HLA-A6901  HLA-A8001

HLA-B0702  HLA-B0801  HLA-B1302  HLA-B1501  HLA-B1801
HLA-B2702  HLA-B2705  HLA-B3501  HLA-B3503  HLA-B3701
HLA-B3704  HLA-B3801  HLA-B3901  HLA-B3906  HLA-B4001
HLA-B4002  HLA-B4102  HLA-B4402  HLA-B4403  HLA-B4408
HLA-B4901  HLA-B5101  HLA-B5201  HLA-B5401  HLA-B5601
HLA-B5701

HLA-C0102  HLA-C0303  HLA-C0304  HLA-C0401  HLA-C0501
HLA-C0602  HLA-C0701  HLA-C0702  HLA-C0802  HLA-C1202
HLA-C1203  HLA-C1402  HLA-C1403  HLA-C1502
```

共 65 个（HLA-A 25 + HLA-B 26 + HLA-C 14）。

---

## 方向翻转（重要）

ICERFIRE 原始输出为 **percentile rank（0-100）**，方向与本 benchmark 其他工具**相反**：

| 值 | ICERFIRE 原始含义 | 翻转后 icerfire_score |
|---|---|---|
| 0 | 最强免疫原 | 100 |
| 100 | 最弱免疫原 | 0 |

翻转公式：`icerfire_score = 100 - icerfire_rank`

输出 schema（`scripts/out/newtools/icerfire_DS1DS2_scores.csv`）：

```
bb_idx, icerfire_rank, icerfire_score, pending_DTU_consent
```

- `icerfire_rank`：原始 ICERFIRE percentile rank（0=最强，保留供溯源）
- `icerfire_score`：翻转后方向（越高越强，与其他工具 apples-to-apples）
- `pending_DTU_consent`：整列 `True`（获书面确认后改 `False`）

---

## 文件说明

| 文件 | 作用 |
|---|---|
| `prep_icerfire.py` | master_backbone.csv → icerfire_input.csv（支持 HLA）+ icerfire_unsupported_bbidx.csv（不支持 HLA）+ icerfire_index.csv（行号→bb_idx） |
| `run_icerfire.sh` | SLURM sbatch 作业脚本（cpudebug，4cpu/16G/1h） |
| `parse_icerfire.py` | ICERFIRE 输出 + index + unsupported → 回贴 bb_idx → icerfire_DS1DS2_scores.csv（含翻转+NaN 合并） |
| `README.md` | 本文 |

---

## 行序 join 机制

ICERFIRE 输入无表头、输出也无行标识，靠**严格行序**回贴 bb_idx：

1. `prep_icerfire.py` 写 `icerfire_input.csv` 第 N 行 = `icerfire_index.csv` 第 N 行（output_row=N）
2. `parse_icerfire.py` 读 ICERFIRE 输出第 N 行 = 对应 index 第 N 行 → 查 bb_idx 回贴

跳过行（WT 为空）只记 index（output_row=SKIPPED），不写 icerfire_input.csv，不影响行序。
不支持 HLA 的行写 icerfire_unsupported_bbidx.csv，parse 阶段作为额外 NaN 行合并进输出。

---

## 运行顺序

```bash
# 1. 准备输入（本地或 HPC 登录节点）
python prep_icerfire.py \
    --backbone scripts/out/master_backbone.csv \
    --out-dir scripts/out/newtools/icerfire_inputs/
# 产出：icerfire_input.csv / icerfire_index.csv / icerfire_unsupported_bbidx.csv

# 2. 提交 HPC 作业（binary 到位 + ICERFIRE.sh config 变量已 sed 后）
sbatch run_icerfire.sh
# 产出：icerfire_input_scored_output（名称 TODO 核实）

# 3. 解析输出（作业完成后）
python parse_icerfire.py \
    --icerfire-out scripts/out/newtools/icerfire_inputs/icerfire_input_scored_output \
    --index scripts/out/newtools/icerfire_inputs/icerfire_index.csv \
    --unsupported-csv scripts/out/newtools/icerfire_inputs/icerfire_unsupported_bbidx.csv \
    --out-csv scripts/out/newtools/icerfire_DS1DS2_scores.csv
    # --rank-col <TODO: 跑后核实列名>
    # --delimiter <TODO: 核实分隔符，默认 TAB>
```

---

## TODO（binary 到位后核实）

- [ ] 输出文件确切名称：`icerfire_input_scored_output` 是否有扩展名？落在哪个目录？
- [ ] percentile rank 所在列名（`--rank-col` 参数，常见 `rank`/`percentile_rank`/`icerfire_rank`）
- [ ] 输出分隔符（CSV 还是 TSV？`--delimiter` 参数）
- [ ] HPC conda env 名称（run_icerfire.sh 中 `source activate <env_name>` 占位）
- [ ] WT 为空时 ICERFIRE 是否支持仅突变肽模式（当前策略：跳过）
- [ ] 获 DTU 书面许可后将 `pending_DTU_consent` 列改 `False`

---

## 许可红线

- **pending_DTU_consent = True**：binary 使用条款待 DTU 书面确认（health-software@dtu.dk）
- 投稿前需取 DTU 书面同意（与 netMHCpan 系列同批处理）
- 输出文件 `pending_DTU_consent=True` = 提示未获书面确认，不得直接引用进论文/对外报告
- ICERFIRE = 学术工具，禁止对第三方发布在其软件上跑的数字（参考 netMHCpan 使用条款）
