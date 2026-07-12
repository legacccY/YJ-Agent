# CMedFaith — P3 全谱检测器横评 + 规模依赖曲线 实验矩阵

> Planner 交付，2026-07-11 19:17（主线落盘）。**服务 CMedFaith § / lever L2（发现+基线：现成检测器医学域失效边界）**。
> 只设计不写码不跑；实现交 coder，跑交主线（`/loop /run-experiment` + `gpu_slot.py`），分析交 analyst，核数交 verifier。
> **本文定位 = 细化并更新 `EXPERIMENT_MATRIX_P1-P3.md` 的 P3 段 + 新增「规模依赖曲线」核心 run（R-P3.13）**，对齐 ACCEPTANCE 2026-07-11 新增的「P3 验收口径」（K3 规模依赖）+「K1 第二承重臂」+ L2-a/b/c。
> **不推翻 `EXPERIMENT_MATRIX_P1-P3.md` §0.6 方案 A 冻结设计**（对称锚 zh-gen-adv / 🔴-2 解耦 / K2 重述 / MedFact 三角）——本文与之互补，凡与 §0.6 冲突处显式 flag，交 skeptic/主线裁。
> 判据不自创，用 ACCEPTANCE 既定值；数据集引用查 `.portfolio/datasets.json`；超参查官方源查不到标 TODO（红线6）。

---

## 0. drift 声明 + 本文与现有 PLAN 的边界

- **服务判据**：ACCEPTANCE 之 **L2-a（三族基线全面）+ L2-b（口径固定 + 统计规范）+ L2-c/K1（第二承重臂）+ K3「P3 验收口径」（规模依赖曲线）**。
- **本文新增的唯一核心 run = R-P3.13「能力→检测可靠性」规模依赖曲线**，是 ACCEPTANCE「P3 验收口径」的落地。其余 R-P3.1~3.12 沿用 `EXPERIMENT_MATRIX_P1-P3.md`，本文只补规模分档信息与承重 judge 分配修正。
- **不碰**：STORY headline 措辞（主线已落档，含「工作假设更新」谨慎版 b）、P1 数据构造管线（build_zh_med.py 已建）、K0/K2 判据设计（已冻结）。
- **轴红线**：只评 faithfulness（答案 vs 给定证据）；response/claim/span 三级独立报绝不混（R1/L2-b）；程度词按 P3 数据分档（STORY「#1 内部失效程度轴」），P3 前一律谨慎版 b。

### ⚠️ flag-A（本文发现的与现有档冲突点，交主线/skeptic 裁，非擅改判据方向）
`EXPERIMENT_MATRIX_P1-P3.md` A.0 把 **D13 = Qwen2.5-72B 当「强 judge 上界臂」**，但 **04_LOG entry（2026-07-11 里程碑）实测构造投票器 = {DeepSeek-V3.2（生成器+投票器）, Qwen2.5-7B, Qwen2.5-72B}**。→ Qwen2.5-72B **已是构造 ensemble 成员**，若当 K1/规模曲线的强档承重 judge = 重犯 🔴-2 循环（专挑投票器答错的考同一投票器）。
**修正（落实 §0.6 🔴-2 解耦原则到规模曲线，非改判据方向）**：K1/R-P3.13 承重 judge **排除清单 = {DeepSeek-V3.2, Qwen2.5-7B, Qwen2.5-72B}**（实际构造集）。强档上界 judge 改用**非构造模型**：GLM-4.5-Air / MiniMax-M2.5 / GPT-4o / DeepSeek-R1（reasoner，未当投票器）。**TODO（拍板前置）**：全量 P2 构造用的投票器集须冻结写进 KILLSHOT（若全量改用 Yi-1.5-9B 等，则排除清单随之更新，承重 judge 从补集重选）。

---

## 1. 检测器全谱 D1–D15（规模分档 + 族 + 许可 + 本地/API + 超参来源）

> 规模轴用**双代理**：①**参数量**（开源已知，MoE 标 total/active）②**能力代理**（通用/中文医学 benchmark 分，如 C-Eval / CMB / MedQA-zh；MoE 的 active≠dense 参数，纯参数量不可比 → 能力分更能排序 judge 强弱）。能力分查不到标 TODO 派 researcher，绝不臆想。
> ★ = K3 已在 28 条 pilot 实测的点（`code/results/k3_*`），P3 放量后重测。

### 族 A — NLI/蕴含 encoder（本地 8GB 全可跑，零 API 成本）
| ID | 检测器 / 版本 | 规模档 | 参数量 | 能力代理 | 中文 | 许可 | 跑法 | 超参来源 |
|---|---|---|---|---|---|---|---|---|
| D1 | mDeBERTa-v3-base-mnli-xnli（`MoritzLaurer/...-mnli-xnli`）| XS | ~86M backbone | XNLI-zh acc TODO核 | ✅真多语 | MIT | 本地 | pilot 冻结锚，零偏离必用此 ckpt（G_domain 0.2927 复现用它）|
| D2 | AlignScore-large（`yzha/AlignScore`）| XS | 355M(RoBERTa-L) | 英文 SummaC bench | ❌英 | 许可 TODO核 | 本地 | 官方 chunk-NLI 默认，TODO clone 核 |
| D3 | SummaC(ZS+Conv)（`tingofurro/summac`）| XS | 底层 NLI(~400M) | — | 底层定 | Apache TODO核 | 本地 | 官方 zs/conv 默认阈 TODO核 |
| D4 | HHEM-2.1-Open（`vectara/...`）| XS-S | ~600M TODO核 | Vectara LB | ❌英 | Apache-2.0 | 本地 | 官方 0-1 阈默认 |

### 族 B — 专用幻觉/事实核查检测器
| ID | 检测器 / 版本 | 规模档 | 参数量 | 能力代理 | 中文 | 许可 | 跑法 | 超参来源 |
|---|---|---|---|---|---|---|---|---|
| D5 | LettuceDetect-mmBERT-base（`KRLabsOrg/lettucedect-v2-mmbert-base`）| XS | ~150M TODO核 | 多语 span F1 | ✅7-14语含中文 | MIT | 本地(⚠️环境隔离,见风险) | 官方 token-span 默认 |
| D6 | LettuceDetect-EN-ModernBERT（`...modernbert-en-v1`）| XS | ~150M | 英文 | ❌英 | MIT | 本地 | 官方默认（英→中迁移对照）|
| D7 | MiniCheck-Flan-T5-Large（`lytang/MiniCheck-Flan-T5-Large`）| S | 0.77B | LLM-AggreFact | ❌英 | MIT | 本地/4090 | 官方 (doc,claim)→0/1 |
| D8 | Patronus Lynx-8B（`PatronusAI/Llama-3-Patronus-Lynx-8B-Instruct`）| M | 8B | 含 PubMedQA 训练 | ❌英 | **CC-BY-NC 禁商用** | HPC4090 | 官方 judge prompt |
| D9 | RefChecker（`amazon-science/RefChecker`）| — | extractor 定 | — | extractor 定 | Apache-2.0 | HPC4090 | **消融臂不进主结论**，pipeline 重 |

### 族 C — LLM-judge（承重臂须避开构造投票器，见 flag-A）
| ID | judge / 版本 | 规模档 | 参数量 | 能力代理 | 构造成员? | 许可 | 跑法 | recall_unfaith★(28条) |
|---|---|---|---|---|---|---|---|---|
| D10 | Qwen2.5-7B-Instruct | M | 7B | C-Eval TODO核 | **是（投票器）→不进承重** | Apache-2.0 | HPC4090 | 构造臂，只作构造 |
| D11 | GLM-4-9B（`THUDM/GLM-4-9B-0414`）| M | 9B | C-Eval 87.2 | 否 | glm-4 学术免费 | HPC4090/API | **0.143 / BA 0.571**★ |
| D12 | InternLM2.5-7B-chat | M | 7B | C-Eval TODO核 | 否 | Apache 学术免费 | HPC4090 | 待测 |
| D13⚠️ | Qwen2.5-72B → **改 MiniMax-M2.5** | XL | 72B→MoE大 | — | **72B 是投票器→禁承重** | — | API | MiniMax **0.786 / BA 0.786**★ |
| — | Hunyuan-A13B-Instruct（`tencent/...`）| L | MoE 80B/13B活 | TODO核 | 否 | 许可 TODO核 | API | **0.286 / BA 0.607**★ |
| — | GLM-4.5-Air（`zai-org/GLM-4.5-Air`）| XL | MoE~106B/12B活 | TODO核 | 否 | 许可 TODO核 | API | **0.714 / BA 0.786**★ |
| D14 | GPT-4o / DeepSeek-R1(reasoner) | XL | 闭源/超大 | MedQA TODO核 | 否(R1≠投票器V3.2) | 商用/MIT | API | 参考臂，不作主复现结论 |

### 族 D — 自训中文小检测器
| ID | 模型 | 规模档 | 参数量 | 中文 | 许可 | 跑法 | 超参来源 |
|---|---|---|---|---|---|---|---|
| D15 | CMedFaith-finetune（在 CMedFaith-train 上 finetune mDeBERTa/中文BERT）| XS | ~86-300M | ✅ | 我们发布 | HPC4090训 | RAGTruth lr 2e-5/1ep（batch/warmup 未披露=**TODO 派 researcher，拍板对齐 full-ft vs LoRA 哪套**，红线6）|

**L2-a 满足性**：主横评核心 = 族A全 + D5/D6/D7/D8（族B）+ D11/D12/D14 + MiniMax/GLM-4.5-Air/Hunyuan（族C 承重）+ D15（族D）→ **4 族齐**，D9/D10 作消融/构造臂不进主结论表。

---

## 2. 规模依赖验证设计（本 P3 核心，对齐 ACCEPTANCE「P3 验收口径」）

### 2.1 分档（规模/能力）
按**能力代理**（首选）+ 参数量（辅）分 5 档，横轴排序用能力代理（MoE 用 active 参数不可比，故主锚能力分）：

| 档 | 参数量区间 | 检测器（承重，已排除构造投票器）| pilot 先验 recall_unfaith |
|---|---|---|---|
| **XS encoder** | <0.5B | D1 mDeBERTa / D2 AlignScore / D5 LettuceDetect-mmBERT / D15 自训 | NLI 族 pilot 医学 macro-F1 0.43<随机 |
| **S** | 0.5–2B | D7 MiniCheck-Flan-T5-L(0.77B) | 待测 |
| **M judge** | 7–9B | D11 GLM-4-9B / D12 InternLM2.5-7B / D8 Lynx-8B | GLM-4-9B **0.14≈随机**★ |
| **L judge** | 13B 级 | Hunyuan-A13B（MoE 13B活）| Hunyuan **0.29≈随机**★ |
| **XL judge** | 70B+/MoE大 | GLM-4.5-Air / MiniMax-M2.5 / GPT-4o / DeepSeek-R1 | 0.71–0.79（仍漏 20–30%）★ |

### 2.2 双面板曲线（防「encoder vs judge 机制不可比」被 skeptic 攻）
规模曲线**分两面板独立画 + 一张合成图**：
- **面板 (a) — generative LLM-judge 族内规模轴**（主结论锚）：只含 judge（M/L/XL 档），横轴=能力代理，纵轴=recall_unfaithful / BA，验能力单调性。机制同类可比。
- **面板 (b) — 专门训练 encoder/专用检测器带**（补充证据）：族A/B 小模型（含 D15 自训），验「即便针对性训练的小检测器也失效」，横轴标注机制不同、不与 judge 直接比参数量。
- **合成图 F-scale**：两面板叠加，主 claim 落在面板 (a) 的单调性 + XL 档仍显著漏检。

### 2.3 家族内对照（最干净的 within-family scaling 证据，控训练配方）
- **GLM 家族**：GLM-4-9B（0.14★）vs GLM-4.5-Air（0.71★）——**同源不同规模**，paired bootstrap 在同一 test 集比 recall，控家族训练差 → 「能力↑检测↑」的因果性最强单点。
- （若全量构造改用非 Qwen 投票器）可补 Qwen 家族 7B vs 14B/32B 作第二家族对照；当前 Qwen 全系被投票器占，暂不可用。

### 2.4 样本量：28 → 建议区间 + rationale
- **当前 28 条（14 faithful + 14 unfaithful）= pilot 粗信号**：recall_unfaithful 基于仅 14 条 unfaithful，Wilson 95%CI half-width ≈ **±0.20**（如 0.79 点估计 CI≈[0.52,0.92]）——**无法区分「随机档 0.5」与「强档 0.79」，更测不出「XL 档 CI 上界<0.90」**。K3 初验只够定性说「中小失效、强档抓大部分」，不够 P3 定量。
- **P3 规模曲线专用/主横评 test 集建议：类平衡 ≥400 条（200 faithful + 200 unfaithful），理想 600（300+300）**。
  - **rationale（recall CI 收敛）**：recall_unfaithful 基于 n_unfaithful 条。n=100→Wilson half-width≈±0.085；**n=200→≈±0.06**；n=300→≈±0.05。要预注册判据「XL 档 CI 上界<0.90」且「中小档 CI 含/低于 0.5」两条**不重叠**可判，需各档 half-width ≤0.08 → **n_unfaithful ≥ 100（取 200 留分层余量）**。
  - **分层余量**：按幻觉类型（7-9 类）或难度轴分层子分析后，每格仍需 ≥15-20 unfaithful → 全集 200 unfaithful 才够 hard 子集不塌。
- **平衡比例 faithful:unfaithful = 1:1**（对齐 L1-c 不搞 PsiloQA 式极不平衡；BA/recall 在平衡集上解释最干净；28 条 pilot 已是 14:14）。
- **放量路径**：14 条 pilot → P2 全量 ≥8-10k（R-P2.1）→ 从中划**类平衡 test split ≥400-600**（train/dev/test 患者/题源不重叠防泄漏）→ 规模曲线 R-P3.13 在此 test 上跑全档。

### 2.5 统计规范（对齐 L2-b + PLAN §E，落到规模曲线每个量）
| 量 | 方法 |
|---|---|
| 每检测器 recall_unfaithful / BA 点估计 | 平衡 test 集直接算 |
| 点估计 95%CI | **bootstrap 10000 resamples**（对 unfaithful 子集重采样算 recall；对全集重采样算 BA）|
| 能力→可靠性单调性 | **Spearman ρ(能力代理, recall_unfaithful)** + bootstrap CI；ρ>0 且 CI 下界>0 = 单调上升成立 |
| 档间差异（强 vs 弱） | **paired bootstrap**（同 test 集，配对重采样）Δrecall = XL − M，CI 排 0；**家族内 GLM-4-9B vs GLM-4.5-Air 同法** |
| 「每检测器 recall 是否>随机 0.5」多重检验 | **Holm-Bonferroni（FWER）** 校正全部检测器的 p 值（≥12 个 → Holm 优于 Bonferroni）|
| 配对检验禁忌 | recall/BA/F1 **禁 McNemar**（仅 accuracy 可），一律 paired bootstrap/permutation [arXiv:1609.09471] |
| effect size | Δrecall + bootstrap CI |

---

## 3. 对齐 ACCEPTANCE「P3 验收口径」的 PASS/FAIL run

### R-P3.13 — 规模依赖曲线判决（本文新增核心 run，验 K3 P3 验收口径）
| 项 | 内容 |
|---|---|
| **服务判据** | ACCEPTANCE K3「P3 验收口径」（规模依赖曲线稳健性）+ L2-a/b |
| **自变量** | 检测器规模档（XS/S/M/L/XL），能力代理连续轴 |
| **控制（固定）** | 同一 zh-med 类平衡 test 集（≥400-600）；judge prompt/温度/response 级口径跨检测器恒定；承重 judge 排除构造投票器（flag-A）|
| **检测器** | 面板(a) judge：D11/D12/D8 + Hunyuan/GLM-4.5-Air/MiniMax/D14；面板(b) encoder：D1/D2/D5/D7/D15 |
| **数据切片** | CMedFaith-zh-med test（类平衡，从 R-P2.1 全量划）|
| **主指标** | recall_unfaithful + BA + bootstrap 95%CI；Spearman ρ 单调性；GLM 家族内 paired bootstrap |
| **预注册判据（建议阈，⚠️阈属拍板点见 §6）** | **PASS** = ①面板(a) Spearman ρ(能力,recall)>0 且 CI 下界>0（单调上升）**且** ②**最强 XL 档 recall_unfaithful bootstrap 95%CI 上界 < 0.90**（最强 judge 仍显著漏≥10% 幻觉）**且** ③中小档（M/XS）recall_unfaithful 95%CI 含或低于 0.5（≈随机）。**FAIL** = 最强 XL 档 recall CI 下界 ≥ 0.90（最强档已可靠）→ 失效仅低端伪迹，headline 重心须再议（触 ACCEPTANCE「FAIL：最强档已可靠→再议」）|
| **预期** | pilot 先验：GLM-4-9B 0.14 / Hunyuan 0.29 / GLM-4.5-Air 0.71 / MiniMax 0.79 → 放量后单调上升 + XL 档 CI 上界<0.90 稳健成立（PASS，落 STORY 谨慎版 b「规模/能力依赖失效边界」）|
| **落表图** | **T-scale**（各档 recall/BA/CI）+ **F-scale**（双面板能力→可靠性曲线）|
| **依赖** | R-P2.1（全量 test 建好）+ R-P3.1（主横评 harness）|

### K1 承重臂（R-P3.4，沿用 §0.6，本文只补 judge 分配）
- 承重 judge **改用非构造模型**：NLI(D1) + 非投票 judge（GLM-4-9B/InternLM2.5/MiniMax/GLM-4.5-Air）+ 专用(D5)；**D10/D13(Qwen 系)不进承重**（flag-A + §0.6 🔴-2）。
- 判据不变（§0.6 K1）：`G_domain=MacroF1(zh-gen-adv)−MacroF1(zh-med-adv)≥0.05` 且 CI 下界>0，≥2 族（含≥1 非投票 judge）医学显著弱 → #1 保；FAIL → 收缩「NLI 族失效」。
- **与 R-P3.13 关系**：K1 判「域效应（医学 vs 通用对称锚）在多族是否成立」；R-P3.13 判「失效随规模如何变（能力单调 + 最强档仍漏）」。两者正交互补，非重复（K1 = 跨域对照，R-P3.13 = 跨规模剖面）。

### 其余 P3 run 沿用 EXPERIMENT_MATRIX §A.4（R-P3.1 主横评 / R-P3.2 claim / R-P3.3 span / R-P3.5 K2 / R-P3.6 K3全量 / R-P3.7 校准 / R-P3.8 judge稳定性 / R-P3.9 族D / R-P3.10 类型 / R-P3.11 分歧 / R-P3.12 MedFact三角），本文不重列。

---

## 4. 算力 / 成本估（分本地 vs API，供主线判拍板）

| 档 | 检测器 | 硬件 | 成本 |
|---|---|---|---|
| **本地 CPU/8GB（零 API ¥）** | D1-D4 NLI / D5-D7 专用 encoder / bge / bootstrap 10000 / ECE / 统计 | RTX4070 8GB + CPU | ~0.5-2 GPU·h/万条·model，无钱花 |
| **HPC 4090** | D8 Lynx / D11 GLM-4-9B / D12 InternLM / D15 finetune | gpu4090（`gpu_slot request cmedfaith hpc 1`）| judge 推理 ~2-4 GPU·h/万条；D15 训 ~3-6 GPU·h |
| **API（真金¥）** | MiniMax-M2.5 / GLM-4.5-Air / Hunyuan-A13B / GPT-4o / DeepSeek-R1 | 硅基流动/OpenRouter | 见下 |

**API 调用量 + ¥估（对标 pilot：20 条构造 720 调用≈¥1-2；K3 单 judge 28 条 28 调用≈¥0.x → 单价约 ¥0.002-0.003/调用）**：
- **R-P3.13 规模曲线（P3 增量）**：API judge 约 5-6 个 × test 400-600 条 × 1 次（response 级）= **~2400-3600 调用**；judge 自一致性（R-P3.8）只对 ~80 条子集 × 5 采样 × 5 judge = ~2000 调用。→ **规模曲线+稳定性 API ≈ ¥15-30**（test 600 + GPT-4o 单价偏高则 ¥30-50）。
- **P3 评测总 API（judge 臂全部）≈ ¥30-80**（小额，非拍板点）。
- **⚠️ P2 全量构造（前置，非 P3 但 P3 依赖，真金大头）**：pilot 产出 1 条≈36 调用（生成候选+3投票器）。全量 ≥8-10k 最终条 → ~8000×36 ≈ **~29 万调用 ≈ ¥300-900**（DeepSeek-V3.2 生成便宜档）。**属「大笔 API 花费」拍板点**（红线7），主线先估预算报用户。可分批（先 2k 验规模曲线信号，再放满）。

---

## 5. 依赖顺序（可并行 / 串行）

```
前置（P2 数据，串行，P3 全部前提）:
  R-P2.1 全量构造 ≥8-10k ─→ 划 train/dev/test（患者/题源不重叠防泄漏）
     └─ test 类平衡 ≥400-600 = R-P3.13 规模曲线的评测集

P3 内并行（test 建好后，各检测器无文件冲突，多 opus/多卡扇出）:
  ┌ 本地零成本先起（无 API 依赖）: D1-D7 encoder 全跑 → 填面板(b) + 主横评 encoder 行
  ├ HPC 4090: D8/D11/D12 judge + D15 训（gpu_slot 各占 1 卡）
  └ API: MiniMax/GLM-4.5-Air/Hunyuan/GPT-4o/R1（走 API，与 GPU 并行，先估预算）

  R-P3.13 规模曲线 = 汇齐上述全档 recall/BA 后出双面板曲线
  R-P3.4 K1 依赖对称锚 R-P2.7（§0.6）建好 + R-P3.1 主横评
  串行: R-P3.0(D15训) → R-P3.9(族D评); R-P3.3(span) → R-P3.5(K2)
```
- **R-P3.13 与 R-P3.1 主横评共用同一批检测器推理输出**（只是切 recall_unfaithful/分档视角）→ 不额外多跑，analyst 从主横评结果重切即可。
- **最先起（零成本、无依赖一旦 test ready）**：本地 D1-D7 encoder + 已测 4 judge 在放量 test 上重测。

---

## 6. 风险点 / 前置 TODO

| 风险 / TODO | 影响 | 处置 |
|---|---|---|
| **R-P3.13 PASS 阈「XL 档 CI 上界<0.90」是新增判据阈** | 改/加验收阈=拍板点（红线4）| **⚠️ planner 不自定阈，建议 0.90（rationale：MedHallu not-sure 档 F1 仅~38%，pilot 强档 0.79；上界<0.90=仍漏≥10%=「未被可靠覆盖」的合理操作化）→ 交主线/用户预注册前拍板冻结**，冻结后写 KILLSHOT 防 HARKing |
| **全量构造投票器集须冻结**（当前 {DeepSeek-V3.2,Qwen2.5-7B,Qwen2.5-72B}）| 决定承重 judge 排除清单（flag-A/🔴-2）| **TODO**：主线冻结全量构造投票器写进 KILLSHOT+spec；承重 judge 从补集选，绝不重叠 |
| **能力代理分（C-Eval/CMB/MedQA-zh）多数未查** | 规模轴排序依据 | **TODO 派 researcher** 查各 judge 官方 benchmark 分；查不到标 TODO 用参数量降级排序（红线6）|
| **MoE active vs total 参数量不可比** | 纯参数量横轴误导 | 主锚能力代理轴，参数量标 total/active 双值，面板(a) 只比 judge 机制同类 |
| **LettuceDetect(D5) transformers 版本地狱**（04_LOG：mmBERT 顶 numpy2 撞 scipy，当前跑不了）| 唯一原生中文专用检测器缺位 | **TODO**：独立 venv 隔离跑 D5（不动已验证主环境），跑不通则诚实报「专用检测器族仅英文迁移臂 D6/D7，中文专用缺位」写 Limitations |
| **D15 finetune batch/warmup 官方未披露** | 族D 复现 | **TODO 派 researcher**，拍板对齐 RAGTruth full-ft(lr2e-5/1ep) vs repo LoRA(r8/α32) 哪套，查不到标 TODO 不臆想 |
| **judge 逐字 prompt**（MedHallu 0-1-2 式 / RAGTruth span-JSON 式）| judge 臂一致性 | brief §7 已抓到路径，coder 实现时逐字对齐；judge 二分类 prompt 统一（recall_unfaithful 口径要求二值输出）|
| **强档 judge 多走 API 不可复现** | 复现性（R7）| API judge 标「参考臂」，主复现结论锚可本地/HPC 复现的开源 judge（GLM-4-9B/InternLM/Lynx）+ 开源 encoder；API judge 报但注明不可复现 |
| **test split 泄漏**（同题源/患者进 train+test）| 规模曲线虚高 | 划分按 CMExam 题源/患者 group split，coder 实现时硬隔离（对齐 ArtiOOD 泄漏教训）|

---

## 7. 交接

- **→ researcher**（先派解 TODO）：各 judge 能力代理分（C-Eval/CMB/MedQA-zh）；D15 finetune batch/warmup 官方超参；D2/D3/D4/D5 参数量+许可核实；LettuceDetect 隔离环境可行性。
- **→ skeptic**（本设计动手前红队）：攻 ① R-P3.13 双面板是否真化解「encoder vs judge 不可比」；② PASS 阈 0.90 是否合理/是否 HARKing 风险；③ GLM 家族内对照是否足够控家族（GLM-4-9B 0414 vs GLM-4.5-Air 训练配方是否同源）；④ K1（跨域）与 R-P3.13（跨规模）判据是否真正交不重复。
- **→ coder**：规模曲线从主横评检测器输出重切 recall_unfaithful/BA + bootstrap CI + Spearman + paired bootstrap + Holm；test group-split 防泄漏；judge 二分类 prompt 统一；D5 独立 venv。**无文件冲突可多 opus 扇出。**
- **→ 主线**：①R-P3.13 PASS 阈拍板冻结（0.90）；②全量构造投票器集冻结；③P2 全量构造 API 预算（¥300-900）拍板；GPU run 经 `gpu_slot.py request cmedfaith hpc 1`，API 批跑 `hpc 0` 登记；上传 HPC 新代码/数据先报（对外传输）。
- **→ analyst**：R-P3.13 出各档 recall/CI 后判单调性 + XL 档上界 + 家族内对照 → 对齐 ACCEPTANCE「P3 验收口径」PASS/FAIL；出 T-scale/F-scale；反哺 STORY「#1 内部失效程度轴」定最终措辞（a 系统性 / b 规模依赖）。
- **→ verifier**：所有入表 recall/BA/CI Bash/Grep 核 csv（红线5）；response/claim/span 三级不混（L2-b）。

> **建议主线/Opus 复核（拍板前提示）**：① R-P3.13 PASS 阈 0.90（新增验收阈=拍板点，planner 未擅定仅建议）；② flag-A（D13=Qwen2.5-72B 强档 judge 与实际构造投票器冲突）的修正是否需同步改 EXPERIMENT_MATRIX A.0 表；③ P2 全量构造 API 预算属大笔花费拍板点。
