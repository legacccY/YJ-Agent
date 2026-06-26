# NetTepi 1.0 部署说明

**服务**：quantimmu-bench §Tier-2，lever = NetTepi 1.0 作经典加权 baseline

---

## ⚠️ pending_DTU_consent = True（红线）

NetTepi 1.0 为 DTU 学术授权工具。**binary 需向 DTU 申请**（health-software@dtu.dk）。
在获得书面授权并取得 binary 前：
- 不得运行 `run_nettepi.sh`
- 不得对外发布 `nettepi_DS1DS2_scores.csv`
- 输出 CSV 中 `pending_DTU_consent` 整列 = `True`

---

## ⚠️ BLOCKED 风险：stabpan GLIBC 版本不足

NetTepi 1.0 内部调用 **netMHCstabpan**（稳定性预测子组件）。

| 组件 | 需要 | HPC el8 实际 | 状态 |
|------|------|--------------|------|
| netMHCstabpan | GLIBC_2.29 | GLIBC_2.28 | ⚠️ **可能 BLOCKED** |

**验证步骤**（获得 binary 后，运行前先测）：
```bash
ldd /path/to/netMHCstabpan 2>&1 | grep "GLIBC"
# 若报 "version `GLIBC_2.29' not found" → BLOCKED，需替代方案
```

若 BLOCKED，可选替代：
- 申请更新系统节点（需 HPC admin）
- 使用 Singularity/Apptainer 容器封装（携带 GLIBC）
- 降级为仅用 NetMHCpan（跳过稳定性分，结果不完整）

---

## 13 个支持 HLA Allele（TODO）

NetTepi 1.0 仅支持固定 13 个 HLA-I allele（官方 README 列出）。

```python
SUPPORTED_HLA = [
    # TODO: researcher 从官方 README 核实完整列表
    "HLA-A01:01", "HLA-A02:01", "HLA-A03:01", "HLA-A11:01", "HLA-A24:02",
    "HLA-B07:02", "HLA-B08:01", "HLA-B15:01", "HLA-B27:05", "HLA-B35:01",
    "HLA-B44:02", "HLA-B57:01", "HLA-C07:02",
]  # 占位，未经官方 README 核实
```

**master_backbone.csv 中超出这 13 个 allele 的行**：
- 不生成 `.pep` 输入
- 在 `unsupported_bbidx.csv` 记录
- 最终 scores CSV 中对应 `nettepi_score = NaN`（空字符串）

---

## 依赖链

```
NetTepi 1.0
├── NetMHCpan-4.x      （结合亲和力）
└── netMHCstabpan-1.0  （稳定性）← ⚠️ GLIBC_2.29 阻塞风险
```

下载顺序（获得 DTU 授权后）：
1. NetMHCpan: https://services.healthtech.dtu.dk/software.php
2. netMHCstabpan: https://services.healthtech.dtu.dk/software.php
3. NetTepi: https://services.healthtech.dtu.dk/software.php （同一邮件地址）

---

## HLA 格式

| 来源 | 格式 | 示例 |
|------|------|------|
| master_backbone.csv | `HLA-A*02:01` | 含星号 |
| NetTepi CLI 输入（TODO 核） | `HLA-A02:01` | 去星保冒号 |

`prep_nettepi.py` 中 `convert_hla()` 做此转换。跑通后核实实际格式。

---

## 输出分数方向

`nettepi_score = nettepi_Comb`

- **Comb 越高 = 免疫原性越强**（方向正，直接用，无需取反）
- `nettepi_Rank`（%Rank）越低越强，原样存储供参考，不作为主 score

---

## 文件说明

| 文件 | 说明 |
|------|------|
| `prep_nettepi.py` | 读 master_backbone → 筛 HLA → 写 `.pep` + `pep_index.csv` + `unsupported_bbidx.csv` |
| `run_nettepi.sh` | SLURM sbatch 脚本，含 BLOCKED 风险注释，CLI 待 binary 到位后填实 |
| `parse_nettepi.py` | 读 NetTepi 输出 + pep_index → 回贴 bb_idx → 输出 scores CSV |

输入/输出路径：
```
scripts/out/newtools/nettepi_inputs/
    ├── A0201.pep, A0301.pep, ...  （每 allele 一个）
    ├── pep_index.csv               （allele, subpeptide, bb_idx）
    └── ../unsupported_bbidx.csv   （超出 13 HLA 的 bb_idx）

scripts/out/newtools/nettepi_DS1DS2_scores.csv
    列: bb_idx, nettepi_Comb, nettepi_Rank, nettepi_score, pending_DTU_consent
```

---

## 运行顺序

```bash
# 1. 准备输入（本地/HPC 均可）
python prep_nettepi.py --backbone .../master_backbone.csv --out-dir .../nettepi_inputs

# 2. 提交 SLURM（获得 binary + 通过 BLOCKED 检查后）
for pep in nettepi_inputs/*.pep; do
    tag=$(basename $pep .pep)
    sbatch run_nettepi.sh $tag $pep
done

# 3. 解析输出（所有 allele job 完成后）
python parse_nettepi.py \
    --raw-dir /gpfs/.../nettepi_run/out \
    --pep-index .../nettepi_inputs/pep_index.csv \
    --unsupported .../nettepi_inputs/../unsupported_bbidx.csv \
    --out .../nettepi_DS1DS2_scores.csv
```

---

## TODO 清单（必须在运行前逐条核实）

- [ ] researcher 从官方 README 核实 13 个支持 HLA allele 完整清单 → 更新 `prep_nettepi.py:SUPPORTED_HLA`
- [ ] 获得 DTU 学术授权 binary（health-software@dtu.dk）
- [ ] 验证 netMHCstabpan GLIBC 兼容性（GLIBC_2.29 vs HPC el8 2.28）
- [ ] 确认 NetTepi CLI 参数：`-p`（肽文件）`-a`（allele）`-l`（长度）实际名称及格式
- [ ] 确认 HLA allele 格式（`HLA-A02:01` vs `HLA-A*02:01` vs `A0201`）
- [ ] 确认 NetTepi 输出文件：分隔符、header 行、Comb 列名、%Rank 列名、肽列名
- [ ] 跑通后收紧 `parse_nettepi.py` 的容错逻辑（当前宽松探测）
- [ ] 若 BLOCKED：评估 Singularity 容器方案或跳过稳定性分的替代
