# BigMHC -m=im 部署笔记

> 服务：quantimmu-bench 扩张 v2 — apples-to-apples 免疫原性扩充
> 所有信息均联网查自 github.com/KarchinLab/bigmhc（master 分支，2026-06-26 核实）

---

## 1. 许可证（License）

**BigMHC Academic License**（Johns Hopkins University Karchin Lab）

- **非商用学术研究/教学/非营利机构：自由使用，无需申请**
- 发表数字/结果：✅ 允许
- 商用（咨询/商业产品/商业研究）：需联系 Karchin Lab 另签商业协议
- 衍生作品分发：需保留版权声明 + 本许可证副本
- **本 benchmark 属学术非商用：✅ 合规，无 pending_consent 阻断**

来源：`LICENSE` 文件第 1 条（已核实）。

---

## 2. repo 结构与克隆

```
repo/
├── src/
│   ├── predict.py      # 推理入口（已核实 CLI）
│   ├── train.py        # 训练入口（本任务不用）
│   ├── cli.py          # CLI 解析 + 数据加载
│   ├── bigmhc.py       # 模型定义
│   ├── dataset.py      # Dataset / DataLoader 封装
│   └── mhcenc.py       # MHC 编码器
├── models/
│   ├── bat512/im/      # BigMHC_IM 模型（7个 checkpoint ensemble）
│   ├── bat1024/im/
│   ├── ...（bat512 ~ bat32768，7个 batch-size checkpoint）
│   └── ...
├── data/
│   ├── pseudoseqs.csv  # MHC → 伪序列 one-hot 映射（cli.py 默认 -s 参数）
│   ├── example1.csv    # 测试输入样例（EL 模式）
│   └── example1.csv.cmp  # 期望输出样例
└── README.md
```

**clone 命令（需 git-lfs，~5GB 含权重）：**

```bash
# 确保 git-lfs 已安装
git lfs install
git clone https://github.com/KarchinLab/bigmhc.git repo/
```

克隆后目录应为 `HPC/deploy/bigmhc_im/repo/`，即 `repo/src/predict.py` 可达。

**LFS 说明**：模型权重（`models/` 下 `*.pt` 文件）通过 Git LFS 存储，clone 时自动拉取。若 LFS 未装或网速慢，可先 `git clone --no-local` 再 `git lfs pull`。

---

## 3. predict.py CLI（已核实）

```bash
# 从 repo/src/ 目录运行（predict.py 有相对路径依赖 models/ 和 data/pseudoseqs.csv）
cd repo/src

python predict.py \
  -i=/path/to/bigmhc_inputs/bigmhc_input.csv \
  -m=im \
  -a=0 \
  -p=1 \
  -c=1 \
  -d=cpu \
  -o=/path/to/bigmhc_inputs/bigmhc_output.prd \
  -j=4 \
  -v=1
```

| 参数 | 说明 | 值 |
|---|---|---|
| `-i` | 输入 CSV 路径 | bigmhc_inputs/bigmhc_input.csv |
| `-m=im` | 模型：immunogenicity 模式 | **固定 im** |
| `-a=0` | allele 在第 0 列（默认值，显式写出） | 列索引 0 |
| `-p=1` | peptide 在第 1 列（默认值，显式写出） | 列索引 1 |
| `-c=1` | 跳过 1 行表头（默认值，显式写出） | 1 |
| `-d=cpu` | CPU 推理（HPC 有 GPU 改 `-d=0` 或 `-d=all`） | cpu |
| `-o` | 输出路径（不指定时默认 `<input>.prd`） | 显式指定 |
| `-j` | DataLoader workers（HPC 建议 4-8） | 4 |
| `-v=1` | 打印进度 | 1 |

来源：`src/predict.py` + `src/cli.py` `parseArgs()` 函数，逐参数核实。

---

## 4. 输入 CSV 格式

**文件**：`bigmhc_inputs/bigmhc_input.csv`（由 `prep_input.py` 生成）

```
mhc,pep
HLA-A*24:02,RLETIRNPK
HLA-A*03:01,RLETIRNPK
HLA-B*40:01,AAAMRILHN
...
```

- 第 0 列：`mhc`（HLA allele，HLA-A*02:01 格式）
- 第 1 列：`pep`（peptide 序列）
- 含 1 行表头（`-c=1` 跳过）
- 无 tgt 列（推理时不需要 label）
- 总行数：53582 + 1（表头）= 53583 行

---

## 5. HLA allele 格式（已核实）

BigMHC 使用**模糊字符串匹配**（fuzzy string matching）定位最近 MHC。以下格式均等价：

| 格式 | 示例 |
|---|---|
| HLA-A*02:01（本 benchmark 格式）| `HLA-A*02:01` ✅ |
| A*02:01 | `A*02:01` ✅ |
| HLAA0201 | `HLAA0201` ✅ |
| A0201 | `A0201` ✅ |
| HLA-A*02:01:01（同义替换/非编码字段）| `HLA-A*02:01:01` ✅ |

**本 benchmark 输入为 HLA-A*02:01 格式，无需任何转换，直接透传。**

注意：BigMHC 不验证 allele 名，会对任何输入做 fuzzy match 到最近 MHC。
支持的 allele 列表见 `data/pseudoseqs.csv`（HPC clone 后检查）。

---

## 6. 输出文件格式（已核实）

**文件**：`bigmhc_inputs/bigmhc_output.prd`（实为标准 CSV）

```csv
mhc,pep,tgt,len,BigMHC_IM
HLA-A*24:02,RLETIRNPK,,9,0.823456
HLA-A*03:01,RLETIRNPK,,9,0.012345
...
```

| 列 | 说明 |
|---|---|
| `mhc` | 原始输入 HLA_Allele 字符串（未规范化） |
| `pep` | peptide 序列 |
| `tgt` | label（推理时为空，NaN） |
| `len` | 肽长（int8，由 dataset.py 计算） |
| `BigMHC_IM` | **免疫原性预测分数，值域 [0,1]，越高越免疫原** |

列名来源：`src/cli.py` `_parseModel()` 中 `args.modelname = "BigMHC_IM"`（`-m=im` 时）。
输出由 `src/predict.py` `preds.to_csv(args.out, index=False)` 写出。

**行序**：内部按肽长分 batch 推理，最终 `pd.concat(preds).sort_index()` 复原行序，与输入一一对应。

---

## 7. CPU 强制法

`-d=cpu` 即强制 CPU，无需额外环境变量。

来源：`src/cli.py` `_parseDevices()`：
```python
if args.devices == "cpu":
    args.devices = []  # 空列表 = CPU 模式
```

HPC 有 GPU 时可改 `-d=0`（第一块 GPU）或 `-d=all`（全部 GPU），速度显著提升。
53582 行 × CPU 推理，预计时间较长（BigMHC 为 ensemble 7 个 checkpoint，CPU 下每条约 0.1-0.5s）。

**建议**：HPC 若可用 GPU，改 `run_bigmhc_im.py --device 0`。

---

## 8. Windows 本地调试注意

BigMHC 测试平台为 Linux（Debian 11），但 README 说明"Execution is OS agnostic"。

Windows 本地（非 HPC）调试时：
- `DataLoader` 使用 `persistent_workers=True` + `num_workers > 0`，Windows 下需 `if __name__ == '__main__':` 守卫（BigMHC repo 原生没有）
- **临时解法**：Windows 本地加 `--jobs 1`（单 worker，无 spawn 问题）：
  ```
  python run_bigmhc_im.py --jobs 1 --smoke
  ```
- **正式跑在 HPC（Linux），不受此限制影响**

---

## 9. 环境安装（HPC）

```bash
# conda 环境（HPC Python 3.9+ 均可）
conda create -n bigmhc python=3.9 -y
conda activate bigmhc

# 必须依赖
pip install numpy==1.21.5 torch==1.13.0 pandas==1.4.4 psutil==5.9.4

# CPU-only torch（无 CUDA 节点）：
pip install torch==1.13.0+cpu -f https://download.pytorch.org/whl/torch_stable.html

# 验证
python -c "import torch, pandas, numpy, psutil; print('OK')"
```

---

## 10. 烟测命令（主线跑）

```bash
# 步骤 1：生成烟测输入（10 行）
python HPC/deploy/bigmhc_im/prep_input.py --smoke 10

# 步骤 2：运行 BigMHC（需 repo/ 已 clone）
python HPC/deploy/bigmhc_im/run_bigmhc_im.py --smoke --jobs 1

# 步骤 3：解析输出
python HPC/deploy/bigmhc_im/parse_output.py --smoke

# 核查输出
head scripts/out/newtools/BigMHC_DS1DS2_scores_smoke.csv
```

全量跑（53582 行）去掉 `--smoke` 和 `--jobs 1` 即可。

---

## 11. 已知坑

1. **运行目录**：predict.py 内部用相对路径找 `../../models/` 和 `../data/pseudoseqs.csv`。必须从 `repo/src/` 目录运行（`run_bigmhc_im.py` 已通过 `cwd=repo/src/` 处理）。

2. **git clone ~5GB**：网速慢时拆两步（`--no-local` 先 clone metadata，再 `git lfs pull`）。

3. **ensemble 7 checkpoint**：BigMHC_IM 实际加载 7 个模型取平均（`bat512/im` ~ `bat32768/im`），CPU 下推理较慢，建议 GPU 节点跑。

4. **行序**：输出经 `sort_index()` 复原输入行序，但 DataLoader shuffle 会重排。`parse_output.py` 使用 (pep, mhc) 键 join，不依赖行序，安全。

5. **tgt 列**：输出中 `tgt` 列值为 NaN（推理时无 label），`parse_output.py` 已处理。

6. **肽长分组 batch**：BigMHC 按肽长 groupby 分批，不同长度分别推理，同长度内行序不保证与输入一致（由 sort_index 复原）。
