# T-SCAPE — 信息收集卡（PPT 素材）

> ⚠️ **许可证警示（醒目）**：T-SCAPE 采用 **CC BY-NC-ND 4.0**（署名—非商业性使用—禁止演绎）。其中 **ND 条款禁止任何衍生**，**NC 条款禁止商业用途**——本工具的全部产物**仅限学术非商业研究使用**，不得用于商业场景，不得分发修改后的代码/权重。
>
> 本卡事实来自官方 repo + 论文 + 本项目本地实测，实测项以「实测」标注。

## 0. 定位 / 一句话
T 细胞免疫原性预测（跨域辅助多任务深度学习，ByteNet 骨架）。全称 **T-cell Immunogenicity Scoring via Cross-domain Aided Predictive Engine**，2025 年发布；通过多任务跨域学习联合 HLA 结合、TCR 结合与免疫原性等任务。**输出 0-1 连续 score → 可定量免疫强弱并排名**，>0.5 判为免疫原。**MT-only**（仅需突变肽 + HLA，无需野生型对照）。

## 1. 输入数据模板 / 格式
- 文件格式：**CSV**
- 必填列 / 字段：`Allele,peptide`（**peptide 列为小写**——实测核对 `example/inputs/pmhc_im.csv`）
- 肽段长度：**≤20mer**，最优 **9mer**
- HLA 格式：标准型 **`HLA-A*02:01`**
- 是否需基因组数据（RNA-seq/VCF/表达量）：**否**
- 是否需野生型（WT）肽：**否（MT-only，仅需突变肽 + HLA）**
- 预处理依赖：推理前须先经 `mhc_pseudo_matching.py I` 给每行贴 pseudo 序列，并**过滤掉不支持的 allele**（不在 `MHC_classI_pseudo.csv` 内的 allele 会被滤除）
- **实测输入样例**：CSV 两列 `Allele,peptide`，如 `HLA-A*02:01,sllmwitqv`（peptide 小写）

## 2. 运行参数设置
- 两步流程：
  1. **贴 pseudo + 过滤**：`python mhc_pseudo_matching.py I input.csv input_mod.csv`
     （`I` = MHC class I；对每行匹配 pseudo 序列，过滤不支持 allele）
  2. **推理**：`python inference_csv.py --csv_path input_mod.csv --inf_type pmhc_im_neo --output out.csv`
- `--inf_type` 任务选择（关键）：
  - `pmhc_im_neo` = **癌症新抗原免疫原性**（本项目癌症用例所用）
  - `pmhc_im_inf` = 感染病免疫原性
  - `p_im` = 纯肽免疫原性（不含 HLA）
  - `pmhc_ba_I` / `pmhc_ba_II` = MHC class I / II 结合亲和力
  - `ptcr_ba` = TCR 结合亲和力
- 推理设备：**CPU**（`inference_csv.py` 内 `device=cpu`，不使用 GPU），`batch_size=32`
- 环境：conda env，Python 3.10+ + PyTorch
- 平台限制：**Linux-only**
- **实测命令行**（本项目两步实跑）：
  ```bash
  python mhc_pseudo_matching.py I input.csv input_mod.csv
  python inference_csv.py --csv_path input_mod.csv --inf_type pmhc_im_neo --output tscape_scores.csv
  ```

## 3. 输出数据格式 + 含义
- 输出文件格式：**CSV**
- 关键列 + 含义：`Allele,peptide,score`
  - `score` = 免疫原性分，**0-1 连续，越高越强免疫原**，**>0.5 = 免疫原**
- 分数类型：**连续 0-1**
- **能否定量免疫强弱**：✅ 是（0-1 连续，可排名）← 项目核心目标
- **实测输出样例**：列 `Allele,peptide,score`；本项目实测 score 范围 **0.0057-0.7716**

## 4. 简介（特点 / 优势）
- 方法：跨域辅助多任务深度学习，**ByteNet** 骨架；联合多个免疫学任务（HLA 结合 / TCR 结合 / 免疫原性）跨域共享表示
- 训练数据：多任务多域免疫学数据集（pMHC 结合、免疫原性、TCR 等，详见论文）
- 特点 / 优势：
  - **MT-only** —— 只需突变肽 + HLA，无需野生型对照，输入门槛低
  - 一套权重多任务复用（同模型切 `--inf_type` 即得结合 / 免疫原性 / TCR 多种预测）
  - 连续 0-1 分，可定量排名
  - CPU 即可推理，无 GPU 硬约束
- 局限：
  - **Linux-only**，且**官方发布代码有 bug，需修复才能跑通**（见「部署修复」节）
  - **许可 CC BY-NC-ND 4.0**，仅限学术非商用，禁止衍生与分发修改版
  - 肽段 ≤20mer（最优 9mer），长肽受限
  - 前身为 **TITANiAN**（bioRxiv 2025.05.11.653308）

## 部署修复（关键 caveat — 用官方权重 + 修复官方 bug，非原版代码）
> 官方发布代码存在 **2 个致命 bug + 1 个推理确定性 bug**，本项目修复后才跑通。**修法均有据，非臆想**。

1. **输入列名 bug**：官方 `pmhc_im` 输入列名文档写大写，实际代码读 `peptide` 小写；列名不符直接读不到肽段。修：输入 CSV 用小写 `peptide` 列。
2. **`pmhc_im_neo` 任务键缺失 → KeyError 崩溃**（最致命）：README 文档化的癌症命令 `--inf_type pmhc_im_neo` 在**所有官方版本 + 全部 fork** 都直接 `KeyError` 崩溃——`load_state_dict` 块和 `task_dict` 都漏了 `pmhc_im_neo` 键，**权重根本没被载入**。
   - 证据（非臆想）：`torch.load` 实测 ckpt 含 `model_state_dict`；该权重载入官方 `Finaltask1_perf` 架构为 **0-key 失配**（结构对得上）；`task_dict` 中免疫原性头输出维恒为 `[3]`。据此补回 `pmhc_im_neo` 的 state_dict 载入与 task_dict 条目即修复。
3. **dropout 推理确定性 bug**：`model_fused.py:326` 需加 `training=self.training`，否则推理期 dropout 仍激活 → 结果非确定性（每次跑分数不同）。该修复对应官方 **PR#3（未合并）**。

## 部署记录
- repo：https://github.com/seoklab/T-SCAPE
- 权重：HuggingFace `seoklab/T-SCAPE`（**全量 54.7GB**；癌症用例**仅需** `best_param/pmhc_im_neo` = **0.53GB**）
- 论文：*T-SCAPE*（Science Advances 2025，DOI **10.1126/sciadv.adz8759**）；前身 TITANiAN（bioRxiv **2025.05.11.653308**）
- 语言 / 框架：Python 3.10+ / PyTorch；**Linux-only**
- 外部许可证工具：无（自带 pseudo 序列 / 权重）
- 许可证：**CC BY-NC-ND 4.0（学术非商用，禁衍生）**
- GPU 需求：**不需要**（CPU 推理，batch_size=32）
- **部署状态：✅ 实测全量完成**（本地 WSL2 CPU）
  - 输入：32178 个 unique (MT, HLA) 对
  - Step A（`mhc_pseudo_matching.py I` 过滤）：滤除 **308 个不支持 allele** → 剩 **31871 行**进入推理
  - merge 后产物 `tscape_scores.csv`：**34247 行，其中 33939 行有分**（308 行因 allele 被滤为 NaN）
  - **score 范围 0.0057-0.7716**
