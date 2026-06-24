# MHLAPre 部署备忘 / 阻塞报告

> 服务：QuantImmuBench（袁老师免疫原性 benchmark）
> 工具：MHLAPre — MAML + Transformer Encoder + TextCNN 预测 HLA-I 突变表位免疫原性
> repo：https://github.com/ChanganMakeYi/MHLAPre
> 论文：*Meta learning for mutant HLA class I epitope immunogenicity prediction*, Briefings in Bioinformatics 2024, Vol 26(1), DOI 10.1093/bib/bbae625
> 更新：2026-06-24

---

## !! 三大阻塞（部署前必解决，缺一不可）

### 阻塞 1：预训练权重缺失（最高优先）

README 明确说明权重文件「太大未上传」，repo 内无任何 `.pt` / `.pkl` / `model/` 目录。
**没有权重 = 无法推理，脚本可部署但无法运行。**

- 联系邮箱：23B903048@stu.hit.edu.cn（通讯作者，Briefings in Bioinformatics 2024）
- 邮件模板（建议包含）：机构身份 + benchmark 用途 + 请求 IM 模型权重文件 + 承诺学术用途
- 若作者长时间不回复（>2 周）→ 见下方 fallback 分析

**Fallback 分析：能否自己重训？**

训练数据来源：IEDB 实验验证 HLA-I 呈递+免疫原性肽，原始 156,244 样本，清洗后 47,810。
问题：IEDB 同样也是大多数 ELISpot benchmark 测试集的来源（见阻塞 3）。
结论：**大概率卡死——权重拿不到、训练数据也是 IEDB、还有 overlap 风险，自训没有意义。**
建议：直接标为「依赖作者响应」，主线先联系作者再决定投入部署。

### 阻塞 2：CUDA 版本不兼容（高风险）

- repo 指定：`torch==1.12.1+cu102`（CUDA 10.2）
- HPC GPU 节点：一般 CUDA 11.x / 12.x（RTX 系列驱动）
- 问题：CUDA 10.2 的 torch wheel 在 CUDA 11/12 驱动上可能无法加载 GPU（版本向下兼容有限制）

备选方案（需实测确认，见 `deploy_mhlapre.sh` 中备注的两条 pip 命令）：
1. CPU 版 torch：`pip install torch==1.12.1 --extra-index-url https://download.pytorch.org/whl/cpu`
   — 可运行但显著慢，benchmark 量小（几百条 ELISpot 样本）可接受
2. 对齐 HPC 驱动的 CUDA 版本：先 `nvidia-smi` 看驱动版本 → 改装对应 torch（如 1.12.1+cu116）
   — 需要 HPC 上确认 driver 版本后再定

TODO（上机后第一步）：`nvidia-smi` 确认 GPU 节点 CUDA 版本，再回来选 pip 命令。

### 阻塞 3：无 LICENSE + IEDB overlap 风险

**无 LICENSE**：GitHub 默认版权保留，严格来说不能用于任何目的（含学术）。
处理方式：邮件联系作者时一并确认学术 benchmark 用途许可。

**IEDB overlap**：MHLAPre 训练数据来自 IEDB；QuantImmuBench 的 ELISpot benchmark 测试集
也来自 IEDB（Guo et al. 2018, Capiod et al. 2022 等）。
风险：测试数据极可能出现在 MHLAPre 训练集中 → AUROC 虚高 → benchmark 结论不可信。

处理方式（二选一）：
1. 取 IEDB 训练集（作者邮件索取）→ 与 ELISpot 测试集做肽段去重（`Mut_peptide` 精确匹配）
2. 在报告/PPT 中加脚注：「MHLAPre 训练数据来自 IEDB，与本 benchmark 测试集存在 overlap
   风险，性能数字仅供参考，不做排名对比」

TODO（数据拿到后）：用 `scripts/mhlapre/check_overlap.py`（待写）做去重核查。

---

## 部署前置条件清单

```
[ ] 收到作者回复，获得权重文件（阻塞 1）
[ ] 权重文件上传至 HPC: /gpfs/work/bio/jiayu2403/quantimmu/tools_repos/MHLAPre/
[ ] HPC 节点 nvidia-smi 确认 CUDA 驱动版本 → 选定 torch pip 命令（阻塞 2）
[ ] 作者确认学术用途许可（阻塞 3-A）
[ ] ELISpot 测试集与 IEDB 训练集 overlap 核查完成（阻塞 3-B）
[ ] run inspect_mhlapre.sh 确认输入列名 + 脚本内路径硬编码（见下）
[ ] 准备输入 TSV（Mut_peptide + HLA_allele，精确列名待 inspect 确认）
```

---

## 已知输入/输出格式（部分）

| 项 | 状态 | 备注 |
|---|---|---|
| 输入列名 | TODO | repo 无 example，需 `inspect_mhlapre.sh` 读 `Pretreatment.py` 源码 |
| 肽段长度 | 8-15 AA（9-mer 主）| 论文明确 |
| HLA 格式 | `HLA-A*02:01` | 标准 HLA 命名，34 位伪序列内部编码 |
| 输出列名 | TODO | 需实跑或读 `TextCNN.py` 源码 |
| 输出分数类型 | 连续 0-1（softmax 概率）| 论文明确 |
| CLI 参数 | TODO | 无文档，需读源码或实跑 |

---

## 运行顺序（权重到位后）

```bash
# Step 1: 数据预处理（路径/列名适配）
python Pretreatment.py      # 输入格式 TODO，见 inspect 结果

# Step 2: Transformer Encoder 推理
python TransfomerEncoder.py  # 注：官方拼写如此（Transfomer，非笔误）

# Step 3: TextCNN 输出免疫原性分数
python TextCNN.py
```

注意：三个脚本无 CLI 参数文档，路径/文件名可能硬编码在脚本内。
`inspect_mhlapre.sh` 会扫描头部，上机前必跑。

---

## 决策建议：MHLAPre 排 Wave 3 末位

推荐优先级排序（由易到难）：
1. DeepImmuno / NetMHCpan（有 CLI，依赖清晰）
2. pTuneos（已测通）
3. IMPROVE（已测通，降级版）
4. NeoTImmuML（有 example data）
5. **MHLAPre（本工具）** ← 权重 + CUDA + license 三重阻塞，末位

行动建议：
- 立即发邮件给 23B903048@stu.hit.edu.cn（联系作者是零成本，不等回复可先推进其他工具）
- 2 周内无回复 → 在 PPT 中标注「权重未公开，无法测试，联系作者中」，不强求跑通
- 权重到位后执行 `deploy_mhlapre.sh` + `inspect_mhlapre.sh` → 再写 benchmark run 脚本

---

## 参考：其他已部署工具对比

| 工具 | 状态 | 备注 |
|---|---|---|
| pTuneos | 已测通 | ELISpot 全跑通 |
| IMPROVE | 已测通（降级）| Stability=NaN，imputed |
| MHLAPre | **阻塞** | 权重缺 + CUDA + license |
