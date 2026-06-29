# TransHLA — 部署说明（QuantImmuBench §工具部署 P9）

> 建档：2026-06-29。服务 quantimmu-bench §工具部署 P9 lever=补满 30 工具呈递槽。
> 许可：MIT，数字可自由发布。
> 来源：github.com/SkywalkerLuke/TransHLA（HuggingFace 权重 SkywalkerLu/TransHLA_I）

---

## 工具简介

TransHLA 是一个混合 Transformer 模型（transformer encoder + deep CNN），用 ESM2 预训练序列
嵌入 + contact map 结构特征做输入，预测一个肽是否会被 HLA 呈递为表位（epitope）。

**首个无需输入 HLA allele 的 epitope detector**——只吃肽序列，不吃 HLA。
分两个子模型：
- **TransHLA_I**（本部署用）：HLA-I 表位检测，肽长 **8-14mer**。
- TransHLA_II：HLA-II 表位检测，肽长 13-21mer（本 benchmark 不使用）。

输出三列（官方）：peptide / 是表位的概率 prob[0-1] / 预测标签 label（1=表位，0=非表位）。
可作为现有 HLA-表位结合亲和力工具的前置初筛。

---

## ⚠️ HLA-agnostic — 核心 caveat（与 Repitope 同）

**TransHLA 不使用 HLA 信息，只依赖肽序列本身。**

- 预测输入：仅肽序列（8-14mer），不输入 allele
- 映射方式：同一肽对所有 HLA_Allele 行填相同 MT_TransHLA / WT_TransHLA 值
- prep_input.py 阶段去重 HLA 维（取 unique peptide），parse_output.py 阶段广播回各 allele 行
  —— 与 HPC/deploy/repitope/ 处理一致
- benchmark 报告须标注：
  > "TransHLA is HLA-agnostic (the first HLA-allele-free epitope detector);
  >  the same epitope probability is assigned to all HLA alleles sharing the same peptide."

---

## 4 类信息（工具横评标准格式）

| 项 | 值 |
|----|----|
| 工具版本 | TransHLA（GitHub SkywalkerLuke/TransHLA；HF 权重 SkywalkerLu/TransHLA_I） |
| 许可 | MIT |
| 输入格式 | 肽序列（8-14mer，TransHLA_I）；**不使用 HLA 信息** |
| 输出分数 | prob（是表位概率，0-1，越高越强）+ label（0/1） |
| 运行平台 | CPU 可跑（CUDA >= 11.8 则 GPU 加速；ESM2 650M backbone，CPU 较慢，HPC GPU 更快） |
| 分类 | Transformer + CNN 表位检测，HLA-agnostic，肽-内在表位概率 |

---

## 模型 / 权重（官方核实，2026-06-29 核自 GitHub README + TransHLA_I.py）

| 项 | 值 | 出处 |
|---|---|---|
| HF model id | `SkywalkerLu/TransHLA_I` | README §How to use in transformers + TransHLA_I.py |
| 加载方式 | `AutoModel.from_pretrained("SkywalkerLu/TransHLA_I", trust_remote_code=True)` | 同上 |
| tokenizer | `facebook/esm2_t33_650M_UR50D`（ESM2 650M） | 同上 |
| pad 长度 | TransHLA_I 固定 pad 到 **16**（8-14mer + ESM2 CLS/EOS） | `pad_inner_lists_to_length(.., target_length=16)` |
| 前向返回 | `Result, _ = model(input_ids)`；Result 为 [N, 2] 概率 | TransHLA_I.py test_loader |
| 取概率 | `prob = Result[:, 1]`（第 2 列 = class 1「是表位」概率） | TransHLA_I.py main |
| 取标签 | `_, label = torch.max(Result, 1)`（argmax → 0/1） | TransHLA_I.py test_loader |
| batch | 官方 test_loader batchsize=128 | TransHLA_I.py |

> 推理逻辑严格镜像官方 TransHLA_I.py，零 API 臆造。

---

## 安装（主线跑，coder 不 clone 不 pip）

```bash
# 1. clone repo（仅取 example/参考；transformers 路径无需 repo 本体）
git clone https://github.com/SkywalkerLuke/TransHLA.git
# clone 目标建议：HPC/deploy/transhla/repo/

# 2. Python 依赖（官方 README §How to use in transformers）
#    CUDA >= 11.8 用 cu118 wheel，否则 CPU
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
pip install transformers
pip install fair-esm     # ESM2 后端，官方要求

# 首次运行会自动从 HuggingFace 下载：
#   - SkywalkerLu/TransHLA_I（自定义 modeling，trust_remote_code=True）
#   - facebook/esm2_t33_650M_UR50D（650M backbone + tokenizer，约 2.5GB）
```

> env 依赖：`torch` + `transformers` + `fair-esm`。
> TODO：未实测确切 transformers/torch 版本下限；官方仅给 CUDA>=11.8 约束。
> 若 trust_remote_code 自定义 modeling 与本地 transformers 版本冲突，需对照
> HF SkywalkerLu/TransHLA_I 的 modeling 文件 requirements 调 transformers 版本。

---

## 运行流水线（主线串行跑，coder 不跑任何代码）

```bash
set REPO=D:\YJ-Agent\project\meeting\QuantImmuBench

# Step 1: 准备输入（去重 HLA 维取唯一肽 + 过滤 8-14mer，~数秒）
python %REPO%\HPC\deploy\transhla\prep_input.py

# Step 2: 烟测（先用 --smoke 5 生成小输入，再推理 1 个肽验算子/列结构）
python %REPO%\HPC\deploy\transhla\prep_input.py --smoke 5
python %REPO%\HPC\deploy\transhla\run_transhla.py --smoke 1

# Step 3: 全量准备 + 推理（去 --smoke；ESM2 650M，CPU 慢，GPU 快）
python %REPO%\HPC\deploy\transhla\prep_input.py
python %REPO%\HPC\deploy\transhla\run_transhla.py

# Step 4: 回贴 universe（~1 分钟）
python %REPO%\HPC\deploy\transhla\parse_output.py

# 最终输出：scripts/out/newtools/TransHLA_DS1DS2_scores.csv（34247 行）
```

---

## 分数方向归一说明（越高越强）

| 原始输出 | 方向 | 输出列 | 变换 |
|---|---|---|---|
| `prob`（是表位概率） | 越高越可能是表位（越强） | `MT_TransHLA` / `WT_TransHLA` | **直接用** |

Spearman(ρ, ELISpot) 时直接使用 MT_TransHLA（正相关方向正确，无需翻转）。

---

## HLA-agnostic 映射方案（parse_output.py 实现）

```
universe.csv (34247 行，4-key 唯一)
  ↓  MT_Subpeptide → peptide_lookup → MT_TransHLA
  ↓  WT_Subpeptide → peptide_lookup → WT_TransHLA
  HLA_Allele 字段：忽略（HLA-agnostic）
  同肽不同 allele 行：填相同值
  <8mer / >14mer / 未打分肽：填 NaN
```

---

## 肽长限制

- **TransHLA_I 仅 8-14mer**（官方 README §Intended uses）。
- benchmark 中 <8mer / >14mer 的肽 → prep 阶段进 transhla_skipped.csv，parse 阶段填 NaN。
- 来源：github.com/SkywalkerLuke/TransHLA README（2026-06-29 核）。

---

## 已知坑 / 风险

### 1. ESM2 650M 下载体积大
- `facebook/esm2_t33_650M_UR50D` 约 2.5GB，首次自动下载，需网络 + 磁盘。
- HPC 离线节点可能需先在登录节点缓存 HF cache（`HF_HOME`）。

### 2. CPU 推理慢
- ESM2 650M backbone 在 CPU 上前向较慢。本 benchmark 唯一唯一肽数量级（数万）下
  CPU 可跑完但耗时；HPC GPU（CUDA>=11.8）更快。
- 若全量太慢，可先 --smoke 验通，再上 HPC GPU 跑全量。

### 3. trust_remote_code 自定义 modeling
- TransHLA_I 用 `trust_remote_code=True` 加载 HF 上的自定义 modeling 文件。
- 不同 transformers 版本对自定义 modeling 的 API 兼容性可能不同。
- TODO：未实测；若报错，对照 HF SkywalkerLu/TransHLA_I 仓库 modeling 文件确认 transformers 版本要求。

### 4. 前向 batch 内肽长不一
- 同 batch 内肽长不同，token 列表长度不同，已用 pad_inner_lists_to_length 统一 pad 到 16
  （照抄官方），保证 torch.tensor 可堆叠。8-14mer 经 ESM2 加 CLS/EOS → 最长 16 token，恰好。

---

## 文件清单（本目录）

| 文件 | 作用 |
|---|---|
| prep_input.py | 读 uniq_pep_hla.csv → 去重 HLA 维取唯一肽 → 过滤 8-14mer → transhla_input.csv |
| run_transhla.py | TransHLA_I 推理（HF transformers，镜像官方）→ transhla_raw.csv（peptide,prob,label） |
| parse_output.py | HLA-agnostic 广播回贴 universe → TransHLA_DS1DS2_scores.csv |
| NOTES.md | 本文件 |
