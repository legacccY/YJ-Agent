# deepHLApan HPC 部署 NOTES

> 服务: quantimmu-bench / deepHLApan  
> 写于 2026-06-24，由主线实测后回填 TODO 项

---

## 1. 版本地狱（最高风险，必读）

### 官方 requirements 的冲突

| 包 | requirements.txt pin | 发布年 | 问题 |
|---|---|---|---|
| `keras` | `==2.0.8` | 2017 | Standalone Keras 2.x，已停更 |
| `tensorflow` | `==2.7.2` | 2021 | TF2.7 内置 `tf.keras`，与 standalone keras 2.0.8 ABI 不兼容 |
| Python | 未指定 | — | keras 2.0.8 最后支持 Python 3.6；TF2.7.2 需 Python 3.7+ |

**已知报错**：[Issue #9](https://github.com/jiujiezz/deephlapan/issues/9) 「Error in loading the saved optimizer state」——TF2.7 存的 optimizer 格式与 keras2.0.8 加载器不兼容。

### 备选 pin 方案（路 A 失败时试）

| 方案 | pip 命令 | 风险 |
|---|---|---|
| A-1（官方原文） | `tensorflow==2.7.2` + `keras==2.0.8` | 已知 optimizer 报错，大概率不通 |
| A-2（TF1 兼容栈） | `tensorflow-gpu==1.14.0` + `keras==2.2.4` | TF1.14 需 CUDA 9+cuDNN 7（HPC GPU 实际 CUDA 版本 TODO） |
| A-3（tf.keras 替换） | `tensorflow==2.7.2`，源码改 `import keras` → `from tensorflow import keras` | 需改 deepHLApan 所有 py 文件 import（侵入性高） |
| **B（推荐 fallback）** | 路 B singularity sif | 最稳，Docker 内版本已固化 |

**TODO（主线实测后回填）**：
- [ ] HPC GPU 驱动版本 + CUDA 版本（`nvidia-smi` 看）
- [ ] 路 A conda 探针是否通过
- [ ] 官方 Docker `biopharm/deephlapan:v1.1` 内真实 TF/Keras/Python 版本（进容器 `python -c "import tensorflow as tf; print(tf.__version__)"` 看）

---

## 2. 路 A vs 路 B 对比

| 项 | 路 A（conda） | 路 B（singularity sif） |
|---|---|---|
| 部署复杂度 | 低（纯 HPC，无跨机操作） | 中（需 WSL2→scp→HPC 三段） |
| 版本可控性 | 低（conda 解依赖可能冲突） | 高（Docker 镜像内版本已固化） |
| 版本地狱风险 | 高（keras2.0.8+TF2.7 已知冲突） | 低（官方镜像跳过此坑） |
| 镜像体积 | ~几百 MB env | ~3-5 GB sif（TODO：主线确认真实体积） |
| HPC 网络要求 | 只需 GitHub+PyPI（HPC 直通） | 需 WSL2 有 docker+代理拉 Docker Hub |
| 推荐度 | **先试**（省事，失败即换 B） | **推荐 fallback**（最稳） |

**推荐流程**：先跑路 A 探针 → 若探针 FAIL → 直接走路 B，不浪费时间调版本。

---

## 3. 输入格式（已知事实）

- CSV，header：`Annotation,HLA,peptide`
- HLA 格式：`HLA-A02:01`（无星号、连字符直连，**不是** `HLA-A*02:01`）
- 肽长：8–15 AA
- 转换规则：`master_backbone.HLA_Allele`（`HLA-A*02:01`）→ `str.replace('*', '')` → `HLA-A02:01`

---

## 4. 输出格式（✅ 已核：prior 本地 WSL2 docker 跑出样例 + 官方 README）

输出文件 `<input_basename>_predicted_result.csv`（另有 `_predicted_result_rank.csv` 多一列 rank）。
确切列名（核 `scripts/out/deephlapan_out_MT/deephlapan_input_MT_predicted_result.csv`）：

```
Annotation,HLA,Peptide,binding score,immunogenic score
0,HLA-A24:02,RLETIRNPK,0.0519,0.0315
```

| 列名 | 含义 | 数值范围 |
|---|---|---|
| `binding score` | HLA 结合预测分 | 0–1 |
| `immunogenic score` | 免疫原性预测分 | 0–1 |

HLA 列输出为**无星号**格式（`HLA-A24:02`），与输入/map key 同格式，回贴时直接 (peptide,HLA) 精确匹配。
高置信新抗原定义（文档声称）：immunogenicity > 0.5 AND binding 排名 top 20。

---

## 5. 主入口（✅ 已核：官方 README + setup.py console_scripts）

安装后是命令 `deephlapan`（非裸 .py），两种用法：
- 单条：`deephlapan -P LNIMNKLNI -H HLA-A02:01`
- 批量：`deephlapan -F <input.csv> -O <output_dir>` ← 官方数据补跑用此

输入 CSV header 必须 `Annotation,HLA,peptide`（HLA 无星号 `HLA-A02:01`，肽 8–15AA）。
⚠️ 坑：`-O` 输出目录须**先 mkdir**，否则报错（DEPLOY_TRACKER L296）。

---

## 6. 实测后需回填 TOOLS/deepHLApan.md 的项

跑通 smoke 后，把以下 TODO 填进 `TOOLS/deepHLApan.md`：

```
§1 实测输入样例 → 贴 demo/1.csv 头3行
§2 实测命令行   → 贴完整 -F <csv> 命令
§3 实测输出样例 → 贴 smoke_demo.csv 头3行 + 精确列名
部署记录        → 路 A/B 哪条通 + example job_id + 输出路径
```

---

## 7. ELISpot overlap 风险（benchmark 评估注意）

deepHLApan 训练数据含 IEDB（32,785 条，含 ELISpot 阳性）→ 与 benchmark ELISpot 测试集**可能有 overlap**。
使用 deepHLApan 分数做 benchmark 时需排重（去 IEDB 训练集中已出现的 peptide+HLA 对），
否则分数虚高、无意义。
**TODO（benchmark 评估阶段）**：拉 deepHLApan 训练集 peptide list，与 ELISpot dataset 做集合差。

---

## 8. 快速参考命令

```bash
# 路 A：建 env
bash /gpfs/work/bio/jiayu2403/quantimmu/scripts/deephlapan/deploy_deephlapan_condaA.sh

# 路 B：WSL2 段 1（拉镜像）
#   在 WSL2 手动跑 build_deephlapan_sifB.sh 段 1
# 路 B：段 3（HPC singularity build）
bash /gpfs/work/bio/jiayu2403/quantimmu/scripts/deephlapan/build_deephlapan_sifB.sh  # 段 3

# 烟测（路 A）
bash /gpfs/work/bio/jiayu2403/quantimmu/scripts/deephlapan/smoke_deephlapan.sh --mode conda

# 烟测（路 B）
bash /gpfs/work/bio/jiayu2403/quantimmu/scripts/deephlapan/smoke_deephlapan.sh --mode sif
```
