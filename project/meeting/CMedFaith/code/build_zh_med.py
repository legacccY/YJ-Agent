#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_zh_med.py — CMedFaith 中文医学 faithfulness 数据构造（MedHallu 四阶段中文复刻）
================================================================================
服务：CMedFaith / PLAN §A.2 R-P1.1（+ R-P1.2 质检投票/双向蕴含）。
lever：L1（中文医学 evidence-conditioned faithfulness 资源）。

这个脚本干什么
--------------------------------------------------
把 MedHallu（EMNLP 2025）的英文医学幻觉半自动构造四阶段管线**中文复刻**，从中文医学
（证据段, 忠实答案）对，构造"语义相似但不忠实于给定证据"的幻觉答案，产 pilot ~100-200 条
`CMedFaith-zh-med`。四阶段照 brief §7 / DATA_INVENTORY B2 逐字配方：

  证据源 = CMExam（`fzkuji/CMExam`，HF，Apache-2.0，见 [CMEXAM]）。researcher 实测 Huatuo-26M
  encyclopedia_qa/KG_qa 都只有 Q/A、无独立证据段，做不了 evidence-conditioned；CMExam 是唯一
  有独立证据段（Explanation 临床推理解析）的源。字段派生（承重）：
    · Explanation（临床推理解析，几十~3k 字符）           → context 给定证据段 C
    · Question + 正确选项文本（Options 按 Answer 字母取）  → 忠实答案 GT（合成为陈述句）
  这样"忠实答案 GT"由证据段 Explanation 支持，构造出的幻觉答案在 Explanation 语境下偏离证据，
  才是真正的 evidence-conditioned faithfulness 样本（对照 Huatuo answer≈evidence 的退化困境）。

  Phase1 候选生成   ：LLM（默认 Qwen2.5-14B-Instruct）按 9 类内容型幻觉定义 + in-context
                      示例，在 Explanation 语境下改写忠实答案使其偏离证据。超参逐字：temperature
                      0.3-0.7 变动 / top-p 0.95 固定 / max 512 tokens / 幻觉答案长度 = 真值 ±10%（中文按字数）。
  Phase2 质检投票   ：3-LLM 投票器（Qwen2.5-7B + Gemma2-9B + Yi-1.5-9B-Chat，[V3] 已定案）。
                      保留规则 = 骗过 ≥1 个投票模型即留；难度 = hard(全骗)/medium(部分)/easy(仅1)。
                      --use-openai：把投票器一票换成 GPT-4o-mini（对齐 MedHallu 原配方，默认关）。
  Phase3 两道 NLI   ：中文 NLI = mDeBERTa（与检测器 D1 复现锚一致），两道都过才算合格幻觉，复用同一实例：
                      (a) 幻觉vsGT：ℰ=min(NLI(H→GT),NLI(GT→H))，τ=0.75，保留 ℰ<τ（滤"其实是同义正确
                          答案"的伪幻觉，防造出同义正确答案——是一层，非 faithfulness 核心判据）。
                      (b) 🆕 幻觉vs证据（faithfulness 核心判据，守 R3）：nli_evi2hallu=NLI(证据→幻觉答案)，
                          τ_evi=0.5（--tau-evidence 可调），保留 nli_evi2hallu<τ_evi。faithfulness 定义=答案
                          是否被给定证据支持；真幻觉必须"不被证据蕴含"。若幻觉答案其实被证据支持（高 entailment）
                          =忠实于证据=滤掉（mini-pilot 样本3「酸溶血试验阳性…确诊特异性」其实忠实于证据却混进来，
                          根因就是原管线漏了这道——只查了 幻觉vsGT，没查 幻觉vs给定证据）。
  Phase4 兜底       ：选与 GT 余弦相似度最大的候选（中文句向量 BAAI/bge-base-zh-v1.5，[EMB] 已定案）。
                      TextGrad 精修 = --textgrad 可选开关，默认只兜底（先跳过精修）。

  输出：code/data/zh_med_pilot.csv（每条含 证据段/忠实答案/幻觉答案/幻觉类型/难度层/是否骗过
        各投票器/双向蕴含分 ℰ）+ code/data/zh_med_pilot_state.json（难度分布/类型分布/成功率等）。

================================================================================
⚠️⚠️ 主线跑前必须确认/解决的 TODO（coder 不臆想、不代跑）
================================================================================
[HPC-ENV]  vLLM 或 transformers 环境：默认 --backend vllm（HPC 4090 linux 装 vllm 后
           一条命令批量生成，吞吐高）。若环境无 vllm → --backend hf（transformers，慢但通用，
           Windows 也能跑烟测）。两条路都走 HF cache（HF_HOME / TRANSFORMERS_CACHE 环境变量），
           **不硬编码任何模型本地路径**。首次跑需联网拉模型权重（14B/9B/7B ×3 + mDeBERTa + embedding）。

[CMEXAM]   证据源 = CMExam（`fzkuji/CMExam`，HF，Apache-2.0 代码许可，68119 行）。researcher 定案：
           Huatuo-26M 各 config 都无独立证据段，CMExam 是唯一有独立证据段（Explanation）的中文源。
           默认走 HF datasets 自动下：repo=`fzkuji/CMExam`（--cmexam-repo / --cmexam-config 覆盖）。
           **字段映射（承重，已定案）**：
             · Explanation（可空，nullable）  → context 给定证据段；空解析行**跳过**（无证据段不能做
               evidence-conditioned），计入 skipped_no_explanation。
             · Question + 正确选项文本         → 忠实答案 GT。正确选项 = Options 按 Answer 字母取对应项，
               合成为陈述句（"针对问题「Q」，正确答案是：<选项文本>。"）。多选题多个正确选项以「；」连接。
           **⚠️ 字段名未在本地核过（coder 不臆想）**：默认字段名 Question/Options/Answer/Explanation
           按官方 CMExam CSV 列名（williamliujl/CMExam），大小写敏感。主线跑前：
             ① 确认 `fzkuji/CMExam` 的实际列名（HF 镜像可能改名）→ 用 --question-field/--options-field/
                --answer-field/--explanation-field 覆盖；若列名/格式与预期不符，先核 datasets 的 features
                再跑，别硬跑。
             ② Options 分隔格式多样（A．/A. /A、/A: /全角字母，可能换行/空格）→ 已做健壮解析
                （_parse_options）；取不到正确选项文本时**标记跳过并计数**（skipped_no_option），不硬崩。
             ③ 建议把 CMExam 补进 datasets.json（本地/HPC 路径 + Apache-2.0）后指向，别每次联网拉。
           **🔒 许可合规（守 L1-b，务必读）**：CMExam 是国家医师资格考试题库，题目/解析**许可受限、
           不可重分发**。本脚本输出的 `zh_med_pilot.csv` 是**内部构造文件**（含 Explanation/Question 原文，
           仅供本地构造/质检，不对外发布）。**正式发布集只发生成的幻觉答案 + CMExam 指针（题目 ID / 行号，
           见 cmexam_id 列），绝不重分发 Explanation 原文或题干原文**。发布打包脚本须据 cmexam_id 剔除
           evidence/gt_answer/question 原文列，只留 hid/cmexam_id/hallu_answer/type/difficulty 等派生列。

[V3]       第三投票器 = `01-ai/Yi-1.5-9B-Chat`（Apache-2.0，中文强，researcher 定案）。已替换原占位。
           🔴 红线：Yi 不在 K1 承重 judge 臂（D11 GLM-4 / D12 InternLM2.5），`_assert_no_k1_judge()`
           放行 Yi、仍硬拦 GLM-4/InternLM2.5——见 [DECOUPLE]。--voter3-model 仍可覆盖（覆盖成 D11/D12 会 raise）。

[EMB]      Phase4 兜底的中文句向量 = `BAAI/bge-base-zh-v1.5`（MIT，researcher 定案）。已替换原占位
           text2vec。--embed-model 仍可覆盖。

[TAU-EVI]  🆕 evidence-grounded 过滤阈值 τ_evi（Phase3 第二道，守 R3，本次修 mini-pilot 质量问题新增）：
           默认 0.5（--tau-evidence 可调）。判据 = 真幻觉必须 NOT entailed by 给定证据
           （nli_evi2hallu < τ_evi）；nli_evi2hallu ≥ τ_evi 说明幻觉答案其实被证据支持=忠实于证据=滤掉，
           这才是 faithfulness 的正确判据（答案 vs 给定证据），与原「幻觉vsGT 双向蕴含」（防同义正确、是
           另一层）**两道都过才是合格幻觉**。**⚠️ 非 brief §7 冻结超参**（brief 只定 τ=0.75 的 幻觉vsGT），
           不动已冻结超参。TODO: 0.5 为合理初值，主线 pilot 抽检后按「被误滤的真幻觉 vs 漏进的忠实答案」
           权衡校准（mDeBERTa entailment 概率分布经验值，证据段较长可能压低 entailment，需看实际分布微调）。
           新增列/字段：CSV 加 `nli_evi2hallu`（证据→幻觉 entailment 分）；state.json 加
           `skipped_faithful_to_evidence`（被这道滤掉=其实忠实于证据的计数）+ `n_after_phase3_gt_filter`
           （幻觉vsGT 过后数）+ `nli_tau_evidence_used`（本轮 τ_evi 取值）。

[PROMPT]   9 类幻觉的**中文定义**我按 DATA_INVENTORY B3 正交双轴类型学写全（我们自有 taxonomy，
           非从外库照搬）；**in-context 示例是我构造的中文占位示例**，结构对齐 MedHallu
           `Dataset Generation/Prompts/system_prompt_medical.txt`（行 24-62）。主线 clone
           `github.com/MedHallu/MedHallu`（MIT）后，建议用其 Appendix K 示例的**结构/风格**
           核对并中文化替换（不改我们 9 类定义，只校示例质量）。见 SYSTEM_PROMPT_ZH / HALLU_TYPES。

[JUDGE-P]  投票器 judge prompt 用 MedHallu 二分类式（question + 给定证据 + 答案 → 0 忠实 / 1 幻觉 /
           2 不确定）中文化，逐字结构对齐 `Detection/detection_vllm_notsurecase.py:30-70`。
           主线可 clone 核对后微调（VOTER_JUDGE_PROMPT_ZH）。

[API-KEY]  --use-openai 时需环境变量 OPENAI_API_KEY（GPT-4o-mini）。默认关（零 API 成本，全开源）。
           大量 API 调用属拍板点（真金花费），主线先估预算。

[API-FULL] 🆕 全 API 模式 `--backend api`（本次新增，为让中文 pilot 完全绕开 GPU 排队/8GB 显存）：
           **Phase1 生成器 + Phase2 三投票器全走 OpenAI 兼容 API（不加载任何本地大 LLM、不占 GPU）**，
           只有 Phase3 NLI(mDeBERTa 0.3B) + Phase4 embedding(bge 0.1B) 留本地（CPU 也能跑，--device cpu）。
           用 openai SDK 的 base_url 机制「一套代码指向多家 provider」：
             --api-base-url    provider 端点。留空=OpenAI 官方；DeepSeek=https://api.deepseek.com；
                               Qwen dashscope 兼容模式=https://dashscope.aliyuncs.com/compatible-mode/v1；
                               OpenRouter（聚合多家，可一套 base_url 跑三家不同 model）=https://openrouter.ai/api/v1
             --api-key-env     读哪个环境变量取 key（默认 OPENAI_API_KEY；DeepSeek 用 DEEPSEEK_API_KEY；
                               dashscope 用 DASHSCOPE_API_KEY；OpenRouter 用 OPENROUTER_API_KEY 等）。
                               🔒 key 只从环境变量读，脚本内绝不硬编码。
             --gen-model       Phase1 生成器 model 名（如 gpt-4o-mini / deepseek-chat / qwen-plus）
             --voter-models    3 个投票器 model（nargs=3，保多样性）
           **⚠️ TODO（provider/model 可用性未核，主线/用户跑前确认，coder 不臆想）**：
             ① DEFAULT_API_GEN / DEFAULT_API_VOTERS 只是占位默认（都填 gpt-4o-mini，OpenAI 默认端点保底可用）。
                **默认三投票器同一 model = 同质，会削弱 hard/medium/easy 难度分层（骗过≥1 信号退化）**，
                正式 pilot 务必给 3 个「不同」model 拉开多样性（对齐 MedHallu 三异构投票器精神）：
                  · 走单一聚合器（推荐 OpenRouter）：--api-base-url https://openrouter.ai/api/v1
                    --voter-models deepseek/deepseek-chat openai/gpt-4o-mini qwen/qwen-plus  （一套 key 跑三家）
                  · 走各家直连端点：用 --voter-base-urls / --voter-key-envs（nargs=3）分别指向不同 provider
                    （高级选项，各家 key 需分别设环境变量）。
             ② 具体 model 名（qwen-plus/deepseek-chat 是否现行可用、聚合器上的完整命名如 qwen/qwen-plus）
                与参数支持（DeepSeek/dashscope 是否都吃 temperature+top_p+max_tokens 同时传）**由用户核**，
                本脚本按 OpenAI chat.completions 标准字段传（temp/top_p/max_tokens，照 brief §7）。
             ③ 成本：全 pilot API 调用数 ≈ limit × 9 类 × 4（1 生成 + 3 投票）。limit=150 → ~5400 次调用。
                --api-max-calls 设上限保护防意外刷爆（默认 20000，够 ~200 条 pilot；达上限硬停，见 §成本保护）。
           🔴-2 解耦（见 [DECOUPLE]）：全 API 下投票器用的是 API model 名（如 deepseek-chat），不是本地
           D11(THUDM/glm-4-9b-chat)/D12(internlm/internlm2_5-7b-chat)，_assert_no_k1_judge 照跑硬校验放行。

[DECOUPLE] 🔴-2 循环解耦（skeptic 致命，PLAN §0.6）：**投票器/生成器绝不用 K1 承重 judge
           D11(GLM-4-9B)/D12(InternLM2.5)**。投票器可含 Qwen2.5-7B（=D10 构造臂，据 PLAN §0.6
           单列"构造参与不进 K1 承重"）。脚本内 `_assert_no_k1_judge()` 硬校验：任一投票器/生成器
           命中 D11/D12 型号即 raise，防手滑违约。

预期产出
--------------------------------------------------
  code/data/zh_med_pilot.csv         : ~100-200 行（--limit 控 CMExam 抽样数，每条一个兜底幻觉答案；
                                         **内部文件**，含 CMExam 原文列，不对外发布，见 [CMEXAM] 许可合规）
  code/data/zh_med_pilot_state.json  : {难度分布 hard/med/easy、9 类内容型分布、构造成功率、
                                         各投票器被骗率、Phase3 两道过滤率（幻觉vsGT + 🆕 evidence-grounded
                                         skipped_faithful_to_evidence）、跳过计数、超参快照（含 τ_evi）}

主线跑法（coder 不跑，只交付）
--------------------------------------------------
  # 冒烟（mock backend，不下模型不占卡，验四阶段管线逻辑通）
  python build_zh_med.py --smoke 1
  # 正式 pilot（HPC 4090，vLLM，抽 150 条 CMExam）
  python tools/gpu_slot.py request cmedfaith hpc 1 "R-P1.1 zh-med 构造"   # 主线先申请卡
  python build_zh_med.py --backend vllm --limit 150
  # 无 vllm 环境退 transformers
  python build_zh_med.py --backend hf --limit 150
  # 对齐 MedHallu 原配方（一票换 GPT-4o-mini，需 OPENAI_API_KEY，属 API 花费拍板点）
  python build_zh_med.py --backend vllm --limit 150 --use-openai

  # 🆕 全 API 模式（生成器+3投票器全走 API，不占 GPU，绕开 8GB/4090 排队；见 [API-FULL]）
  #   步骤：① 先 mock 验管线不破  → ② 设 key 环境变量 → ③ 小 limit 试 → ④ 放量
  python build_zh_med.py --smoke 1                                     # ① mock 验管线（不占卡/不联网/零 API）
  # ② 设 key（PowerShell）：  $env:OPENAI_API_KEY = "sk-..."           （或对应 provider 的 key env）
  #    ② 设 key（bash）    ：  export OPENAI_API_KEY=sk-...
  python build_zh_med.py --backend api --limit 3 --gen-model gpt-4o-mini \
      --voter-models gpt-4o-mini gpt-4o gpt-3.5-turbo --device cpu     # ③ 小 limit 试（几十次调用，验通）
  # ④ 放量 · 单聚合器跑三家不同 model（推荐 OpenRouter，一套 key 多样性最强）：
  python build_zh_med.py --backend api --limit 150 --device cpu \
      --api-base-url https://openrouter.ai/api/v1 --api-key-env OPENROUTER_API_KEY \
      --gen-model openai/gpt-4o-mini \
      --voter-models deepseek/deepseek-chat openai/gpt-4o-mini qwen/qwen-plus
  # ④ 放量 · 或各家直连（DeepSeek 生成 + 三家直连投票，各 key 分别设环境变量）：
  python build_zh_med.py --backend api --limit 150 --device cpu \
      --api-base-url https://api.deepseek.com --api-key-env DEEPSEEK_API_KEY --gen-model deepseek-chat \
      --voter-models deepseek-chat gpt-4o-mini qwen-plus \
      --voter-base-urls https://api.deepseek.com https://api.openai.com/v1 https://dashscope.aliyuncs.com/compatible-mode/v1 \
      --voter-key-envs  DEEPSEEK_API_KEY OPENAI_API_KEY DASHSCOPE_API_KEY

红线遵守
--------------------------------------------------
- 超参逐字（brief §7）：temp 0.3-0.7 / top-p 0.95 / max 512 / 幻觉长=真值±10% / τ=0.75（幻觉vsGT），未私改。
  新增 τ_evi=0.5（Phase3 evidence-grounded 过滤，守 R3，--tau-evidence 可调）——**非 brief 冻结超参**，
  是修 mini-pilot「其实忠实于证据的样本混进来」问题新加的独立一道，pilot 抽检后校准（见 [TAU-EVI]）。
- 选型定案：第三投票器[V3]=Yi-1.5-9B-Chat、中文句向量[EMB]=bge-base-zh-v1.5；证据源[CMEXAM]=CMExam
  （Explanation→证据 / Question+正确选项→GT）。剩 TODO：CMExam 实际列名待主线核[CMEXAM]、in-context 示例[PROMPT]。
- 🔴-2 解耦：`_assert_no_k1_judge()` 硬校验，投票器/生成器不碰 D11/D12（Yi 放行）。
- L1-b 许可：CMExam 不可重分发，zh_med_pilot.csv 内部文件，正式发布只发幻觉答案 + cmexam_id 指针（见 [CMEXAM]）。
- Windows/HPC 兼容：路径全 pathlib；DataLoader 若用则 spawn（本脚本不用多进程 loader，纯批推理）；
  模型走 HF cache 环境变量，不硬编码路径。
- 复现零偏离锚：Phase3 中文 NLI 用与 pilot/D1 一致的 `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli`。
================================================================================
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

import numpy as np

# ----------------------------------------------------------------------------
# 路径锚（与 eval_harness.py 同约定：code/ 在 CMedFaith/ 下）
# ----------------------------------------------------------------------------
CODE_DIR = Path(__file__).resolve().parent          # .../CMedFaith/code
PROJECT_DIR = CODE_DIR.parent                        # .../CMedFaith
DATA_OUT_DIR = CODE_DIR / "data"                     # .../CMedFaith/code/data
REPO_ROOT = PROJECT_DIR.parents[2]                   # .../YJ-Agent
DATASETS_JSON = REPO_ROOT / ".portfolio" / "datasets.json"

OUT_CSV = DATA_OUT_DIR / "zh_med_pilot.csv"
OUT_STATE = DATA_OUT_DIR / "zh_med_pilot_state.json"

# ----------------------------------------------------------------------------
# 冻结超参（brief §7 逐字，别私改；改任一个 = 判据变动拍板点）
# ----------------------------------------------------------------------------
TEMP_MIN = 0.3                 # temperature 在 [0.3, 0.7] 变动
TEMP_MAX = 0.7
TOP_P = 0.95                   # 固定
MAX_NEW_TOKENS = 512           # 生成上限
LEN_TOL = 0.10                 # 幻觉答案长度 = 真值 ±10%（中文按字数）
NLI_TAU = 0.75                 # Phase3 双向蕴含阈值（幻觉vsGT），保留 ℰ < τ
NLI_TAU_EVIDENCE = 0.5         # 🆕 Phase3 第二道 evidence-grounded 过滤默认阈值 τ_evi（守 R3）：
                               #    nli_evi2hallu(证据→幻觉答案 蕴含分) ≥ τ_evi = 幻觉其实被证据支持=忠实=滤掉。
                               #    非 brief §7 冻结超参，是本次修 mini-pilot 质量问题新增；--tau-evidence 可调，
                               #    TODO: 0.5 为合理初值，主线 pilot 抽检后校准（见头注 [TAU-EVI]）。
NLI_MODEL_ID = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"   # 与 pilot/D1 复现锚一致（零偏离）

# 每条证据尝试生成的候选数（覆盖不同幻觉类型；Phase2/3/4 逐层筛，Phase4 兜底选 1）
N_CANDIDATES_PER_ITEM = 9      # = 9 类内容型各生成 1 个候选（brief §3「每条证据生成多个候选覆盖不同幻觉类型」）

# 默认模型（全开源，走 HF cache）
DEFAULT_GENERATOR = "Qwen/Qwen2.5-14B-Instruct"        # brief §7 默认生成器
DEFAULT_VOTER1 = "Qwen/Qwen2.5-7B-Instruct"            # = D10 构造臂（PLAN §0.6：不进 K1 承重）
DEFAULT_VOTER2 = "google/gemma-2-9b-it"                # brief §7 原配方成员
DEFAULT_VOTER3 = "01-ai/Yi-1.5-9B-Chat"               # [V3] 定案（Apache-2.0，中文强；不在 K1 judge 臂，放行）
DEFAULT_EMBED = "BAAI/bge-base-zh-v1.5"                # [EMB] 定案（MIT，中文句向量）

# 全 API 模式（--backend api）默认 model 名 —— ⚠️ 仅占位保底，provider/model 可用性未核（见 TODO[API-FULL]）。
# 默认走 OpenAI 官方端点（--api-base-url 留空）、都填 gpt-4o-mini（保底可用）。默认三投票器同质会削弱难度分层，
# 正式 pilot 务必 --voter-models 给 3 个不同 model（推荐 OpenRouter 一套 key 跑三家，见头注 [API-FULL] 示例）。
DEFAULT_API_GEN = "gpt-4o-mini"                         # TODO: provider/model 由用户核（brief 未定 API 生成器名）
DEFAULT_API_VOTERS = ["gpt-4o-mini", "gpt-4o-mini", "gpt-4o-mini"]  # TODO: 换 3 个不同 model 保多样性
DEFAULT_API_KEY_ENV = "OPENAI_API_KEY"                 # 默认读的 key 环境变量（provider 换则改 --api-key-env）
API_TIMEOUT_S = 60.0                                    # 单次 API 调用超时（秒）
API_MAX_RETRIES = 5                                     # 失败重试次数（指数退避）
API_MAX_CALLS_DEFAULT = 20000                          # --api-max-calls 默认上限（够 ~200 条 pilot；达上限硬停防刷爆）

# 🔴-2 解耦：K1 承重 judge 型号黑名单（投票器/生成器绝不能命中）
K1_JUDGE_FORBIDDEN = {
    "THUDM/glm-4-9b-chat",             # D11
    "internlm/internlm2_5-7b-chat",    # D12
}

DOWNSAMPLE_SEED = 42           # 与 pilot 抽样一致（可复现）


# ============================================================================
# 9 类内容型幻觉 taxonomy（DATA_INVENTORY B3 正交双轴 · 内容型轴，我们自有 taxonomy）
#   定义 = 我们的 taxonomy（非外库照搬）；示例 = 中文占位示例（结构对齐 MedHallu Appendix K，
#   主线 clone 后可校示例质量，见 TODO[PROMPT]）。剔 temporal/causal/memory/multimodal（属
#   factuality/推理，纳入会 confound faithfulness，呼应 R3）。
# ============================================================================
HALLU_TYPES = [
    {
        "id": "evidence_tamper",
        "name": "证据篡改/捏造",
        "definition": "改动或凭空捏造证据段中的关键事实（把证据说的 A 改成非 A），使答案与给定证据直接冲突。",
        "example_gt": "证据指出阿司匹林通过抑制环氧合酶（COX）减少血栓素生成。",
        "example_hallu": "阿司匹林通过激活环氧合酶（COX）促进血栓素生成来发挥抗血小板作用。",
    },
    {
        "id": "baseless",
        "name": "证据无关/无依据",
        "definition": "答案陈述在给定证据段中完全找不到依据（既未被证据支持也未被反驳），凭空引入证据外内容。",
        "example_gt": "证据描述二甲双胍降低肝糖输出以控制血糖。",
        "example_hallu": "二甲双胍还能显著改善患者的睡眠质量和记忆力。",
    },
    {
        "id": "dosage_numeric",
        "name": "剂量/数值错",
        "definition": "药物剂量、频次、疗程、指标阈值等数值与证据不符（本工作细化派生类，非直接引自 MedHallu/RAGTruth）。",
        "example_gt": "证据建议成人每次 500mg、每日 3 次口服。",
        "example_hallu": "证据建议成人每次 500mg、每日 30 次口服。",
    },
    {
        "id": "overclaim",
        "name": "过度断言",
        "definition": "把证据中的可能性/相关性/部分有效夸大为确定性/因果性/普遍有效（overclaim）。",
        "example_gt": "证据显示该疗法在部分患者中可能缓解症状。",
        "example_hallu": "该疗法对所有患者都能彻底治愈该疾病。",
    },
    {
        "id": "incomplete",
        "name": "信息不全",
        "definition": "遗漏证据中影响结论的关键限定/禁忌/前提，使答案在缺省条件下产生误导（最难检测）。",
        "example_gt": "证据指出该药有效，但孕妇及肝功能不全者禁用。",
        "example_hallu": "该药安全有效，适用于所有人群。",
    },
    {
        "id": "mechanism",
        "name": "机制/通路误归因",
        "definition": "把疗效/病理归因到证据未支持的错误生物学机制或通路（mechanism misattribution）。",
        "example_gt": "证据指出他汀通过抑制 HMG-CoA 还原酶降低胆固醇。",
        "example_hallu": "他汀通过直接溶解血管壁上的胆固醇斑块来降低胆固醇。",
    },
    {
        "id": "fabricated_guideline",
        "name": "捏造指南/引用",
        "definition": "虚构一条证据中不存在的指南、共识或文献引用来支撑答案（fabricated sources）。",
        "example_gt": "证据未提及任何具体指南编号。",
        "example_hallu": "根据《2023 中华医学会 XX 指南第 4.7 条》，本药为一线首选。",
    },
    {
        "id": "outdated_guideline",
        "name": "过时/被推翻的指南",
        "definition": "引用真实但已过时或已被推翻的旧指南/旧共识作为当前依据（真实但过时，≠捏造）。",
        "example_gt": "证据采用现行指南推荐的治疗方案。",
        "example_hallu": "按传统做法应常规使用该已被现行指南淘汰的旧疗法。",
    },
    {
        "id": "decision_misguide",
        "name": "诊断/治疗决策误导",
        "definition": "在诊断分诊或治疗决策上给出与证据不符的高危误导（如该转诊却建议观察），医学高危。",
        "example_gt": "证据提示出现该症状需立即就医评估。",
        "example_hallu": "出现该症状通常无需就医，居家观察数周即可自愈。",
    },
]
HALLU_TYPE_IDS = [t["id"] for t in HALLU_TYPES]


# ============================================================================
# Phase1 生成 system prompt（中文化，结构对齐 MedHallu system_prompt_medical.txt）
# ============================================================================
def build_type_catalog_zh() -> str:
    """把 9 类幻觉定义 + in-context 示例拼成 prompt 里的类型目录。"""
    lines = []
    for i, t in enumerate(HALLU_TYPES, 1):
        lines.append(
            f"{i}. 【{t['name']}】{t['definition']}\n"
            f"   示例 · 忠实答案：{t['example_gt']}\n"
            f"   示例 · 该类幻觉答案：{t['example_hallu']}"
        )
    return "\n".join(lines)


SYSTEM_PROMPT_ZH = """你是一个医学数据构造助手。给定一道中文医学问题、一段"给定证据"和一个忠实于该证据的"忠实答案"，你要生成一个"看似合理但不忠实于给定证据"的幻觉答案，用于训练和评测幻觉检测器。

严格要求：
1. 幻觉答案必须**只根据"给定证据"来判断忠实与否**（faithfulness = 答案 vs 给定证据），不是判断它在真实世界是否正确（不评 factuality）。
2. 幻觉答案要与忠实答案**语义相似、语气自然、专业可信**，但在指定的"幻觉类型"上不忠实于给定证据。
3. 幻觉答案的**长度 ≈ 忠实答案的字数 ±10%**（中文按汉字/字符计），不要明显更长或更短。
4. 只输出幻觉答案本身，不要输出解释、标注、类型名或任何额外前后缀。
5. 不要在幻觉答案里暴露"这是幻觉/这是错误示范"之类的元信息。
6. 幻觉答案必须包含在"给定证据"中**找不到依据**、或与"给定证据"**直接冲突**的具体内容（如错误的机制/数值/因果关系/结论），而不能只做同义改写或信息省略——被给定证据支持的答案是忠实答案、不是幻觉，会被质检剔除。

下面是 9 类内容型幻觉的定义与示例，你会被要求按其中**指定的某一类**生成：
{type_catalog}
"""

USER_PROMPT_ZH = """请按【{type_name}】这一类幻觉，为下面的样本生成一个幻觉答案。

问题：{question}
给定证据：{evidence}
忠实答案：{gt_answer}

要求：幻觉答案属于【{type_name}】类（{type_def}），长度约 {target_len} 字（忠实答案 ±10%），只输出幻觉答案本身。
特别注意：幻觉答案必须包含在"给定证据"中找不到依据、或与"给定证据"直接冲突的具体内容（如错误的机制/数值/因果/结论），不要只做同义改写或信息省略——否则它其实仍忠实于证据，不能作为幻觉样本。"""


# ============================================================================
# Phase2 投票器 judge prompt（MedHallu 二分类式中文化，见 TODO[JUDGE-P]）
# ============================================================================
VOTER_JUDGE_PROMPT_ZH = """你是一个医学幻觉检测器。判断"待判答案"是否忠实于"给定证据"。

问题：{question}
给定证据：{evidence}
待判答案：{answer}

只输出一个数字：
0 = 忠实（答案完全被给定证据支持，无幻觉）
1 = 幻觉（答案与给定证据冲突或含证据不支持的内容）
2 = 不确定（无法判断时选 2，不要瞎猜）

你的判断（只输出 0 / 1 / 2）："""


# ============================================================================
# 数据加载：CMExam（HF `fzkuji/CMExam`，Apache-2.0，见 [CMEXAM]）
#   Explanation → 证据段 C；Question + 正确选项文本 → 忠实答案 GT（合成陈述句）
# ============================================================================
def _first_str(x) -> str:
    """字段可能是 list[str] 或标量，取首个非空并转 str。"""
    if isinstance(x, (list, tuple)):
        for item in x:
            if item is not None and str(item).strip():
                return str(item).strip()
        return ""
    return "" if x is None else str(x).strip()


def _to_halfwidth(s: str) -> str:
    """全角字符转半角（全角字母 Ａ→A、全角标点等），便于统一解析选项字母/答案。"""
    out = []
    for ch in s:
        code = ord(ch)
        if code == 0x3000:          # 全角空格
            code = 0x20
        elif 0xFF01 <= code <= 0xFF5E:  # 全角 ！-～ → 半角
            code -= 0xFEE0
        out.append(chr(code))
    return "".join(out)


# 选项标记：半角/全角字母 + 分隔符（． . 。 、 : ： ) ）空格）。用 finditer 定位每个选项起点。
_OPT_MARKER = re.compile(r"([A-Za-zＡ-Ｚａ-ｚ])\s*[．\.。、::\)）]")


def _parse_options(options_raw) -> dict:
    """
    把 CMExam Options 字段解析成 {大写字母: 选项文本}。
    Options 格式多样（'A．xxx B．yyy' / 'A. xxx\\nB. yyy' / 'A、xxx' 等），做健壮解析。
    解析不出任何选项时返回空 dict，调用方计数跳过（不硬崩）。
    ⚠️ 若 CMExam 实际 Options 结构与此不符（见 [CMEXAM]），主线核 features 后调整此解析。
    """
    if options_raw is None:
        return {}
    # HF fzkuji/CMExam 版 Options 是 [{'key':'A','value':'...'}] dict-list（2026-07-11 主线核 features 实测），
    # 非字符串——优先按结构化取，取不到再退字符串正则解析。
    if isinstance(options_raw, (list, tuple)) and options_raw and isinstance(options_raw[0], dict):
        out = {}
        for d in options_raw:
            k = d.get("key") or d.get("Key") or d.get("label")
            v = d.get("value") if d.get("value") is not None else d.get("Value")
            if k and v is not None:
                out[_to_halfwidth(str(k)).upper()] = str(v).strip()
        if out:
            return out
    s = _first_str(options_raw)
    if not s:
        return {}
    matches = list(_OPT_MARKER.finditer(s))
    if not matches:
        return {}
    opts = {}
    for i, m in enumerate(matches):
        letter = _to_halfwidth(m.group(1)).upper()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(s)
        text = s[start:end].strip().strip("，,；;。 \t\r\n").strip()
        if letter and text:
            opts[letter] = text
    return opts


def _parse_answer_letters(answer_raw) -> list:
    """从 CMExam Answer 字段抠出选项字母（可能多选 'AB' / 'A、B' / 'A B'），去重保序、大写。"""
    if answer_raw is None:
        return []
    s = _to_halfwidth(_first_str(answer_raw)).upper()
    seen, out = set(), []
    for ch in re.findall(r"[A-Z]", s):
        if ch not in seen:
            seen.add(ch)
            out.append(ch)
    return out


def _compose_faithful_answer(question: str, opts: dict, letters: list):
    """Question + 正确选项文本 → 忠实答案陈述句。取不到任一正确选项文本返回 None（调用方跳过计数）。"""
    texts = [opts[l] for l in letters if l in opts]
    if not texts:
        return None
    joined = "；".join(texts)
    q = question.strip().rstrip("？?。.").strip()
    return f"针对问题「{q}」，正确答案是：{joined}。"


def load_cmexam(repo: str, config: str | None, question_field: str, options_field: str,
                answer_field: str, explanation_field: str, id_field: str | None,
                limit: int, cache_dir, seed: int):
    """
    从 HF 拉 CMExam，返回 list[dict(hid, cmexam_id, question, evidence, gt_answer, correct_letters)]。
    Explanation → evidence（证据段）；Question + 正确选项文本 → gt_answer（忠实答案）。
    空 Explanation 跳过（无独立证据段不能做 evidence-conditioned）；取不到正确选项跳过并计数。
    """
    from datasets import load_dataset  # 延迟导入，--smoke 不需要

    print(f"[cmexam] load_dataset({repo}, config={config}) ...", flush=True)
    if config:
        ds = load_dataset(repo, config, split="train", cache_dir=cache_dir)
    else:
        ds = load_dataset(repo, split="train", cache_dir=cache_dir)

    n = len(ds)
    rng = random.Random(seed)
    idxs = list(range(n))
    rng.shuffle(idxs)

    items = []
    skipped_no_expl = skipped_no_option = skipped_len = 0
    for i in idxs:
        if len(items) >= limit:
            break
        row = ds[i]
        q = _first_str(row.get(question_field))
        expl = _first_str(row.get(explanation_field))
        if not q:
            continue
        if not expl:                    # 无解析段 = 无独立证据段，不能做 evidence-conditioned
            skipped_no_expl += 1
            continue
        opts = _parse_options(row.get(options_field))
        letters = _parse_answer_letters(row.get(answer_field))
        gt = _compose_faithful_answer(q, opts, letters)
        if gt is None:                  # Options/Answer 取不到正确选项文本
            skipped_no_option += 1
            continue
        # 证据（Explanation）长度过滤：过短无信息量 / 过长超 NLI/生成截断风险（Explanation 上界约 3k）
        if len(expl) < 10 or len(expl) > 3000:
            skipped_len += 1
            continue
        # cmexam_id：优先官方 ID 字段（若存在），否则用行号作指针（供发布集指针化）
        cmexam_id = _first_str(row.get(id_field)) if id_field else ""
        if not cmexam_id:
            cmexam_id = f"cmexam_row_{i}"
        items.append({
            "hid": f"cmexam_{i}",
            "cmexam_id": cmexam_id,
            "question": q,
            "evidence": expl,               # Explanation 临床推理解析 = 给定证据段
            "gt_answer": gt,                # Question+正确选项合成陈述句 = 忠实答案
            "correct_letters": "".join(letters),
        })
    print(f"[cmexam] 抽得 {len(items)} 条 / limit={limit}；"
          f"跳过：无解析段 {skipped_no_expl}、无正确选项 {skipped_no_option}、长度不合 {skipped_len}", flush=True)
    return items, {"skipped_no_explanation": skipped_no_expl,
                   "skipped_no_option": skipped_no_option,
                   "skipped_len": skipped_len}


# ============================================================================
# LLM 后端抽象：vLLM（HPC 批推理，快）/ transformers（通用兜底）/ mock（--smoke）
#   统一接口 generate_batch(prompts, temperature) -> list[str]（system 固定）
# ============================================================================
class LLMBackend:
    def generate_batch(self, prompts, temperature, system=None):
        raise NotImplementedError


class VLLMBackend(LLMBackend):
    """
    HPC 4090 首选：vLLM 批推理。装：pip install vllm。走 HF cache（HF_HOME 环境变量）。
    单卡放不下 14B 时可 --tensor-parallel-size 或换 AWQ 量化（主线按显存定）。
    """
    def __init__(self, model_id: str, max_tokens: int = MAX_NEW_TOKENS,
                 tensor_parallel_size: int = 1, dtype: str = "auto"):
        from vllm import LLM
        self.model_id = model_id
        self.max_tokens = max_tokens
        print(f"[vllm] loading {model_id} (tp={tensor_parallel_size}) ...", flush=True)
        self.llm = LLM(model=model_id, tensor_parallel_size=tensor_parallel_size,
                       dtype=dtype, trust_remote_code=True)
        from transformers import AutoTokenizer
        self.tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)

    def _apply_chat(self, prompt: str, system: str | None) -> str:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        return self.tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)

    def generate_batch(self, prompts, temperature, system=None):
        from vllm import SamplingParams
        sp = SamplingParams(temperature=temperature, top_p=TOP_P, max_tokens=self.max_tokens)
        texts = [self._apply_chat(p, system) for p in prompts]
        outs = self.llm.generate(texts, sp)
        return [o.outputs[0].text.strip() for o in outs]


class HFBackend(LLMBackend):
    """
    通用兜底：transformers 逐条/小批生成（慢，Windows 也能跑）。走 HF cache。
    """
    def __init__(self, model_id: str, device: str = None, max_tokens: int = MAX_NEW_TOKENS):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.model_id = model_id
        self.max_tokens = max_tokens
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        print(f"[hf] loading {model_id} on {device} ...", flush=True)
        self.tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype=(torch.float16 if device == "cuda" else torch.float32),
            trust_remote_code=True).to(device).eval()

    def generate_batch(self, prompts, temperature, system=None):
        import torch
        outs = []
        for p in prompts:
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            msgs.append({"role": "user", "content": p})
            text = self.tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
            enc = self.tok(text, return_tensors="pt").to(self.device)
            with torch.no_grad():
                gen = self.model.generate(
                    **enc, do_sample=(temperature > 0), temperature=max(temperature, 1e-4),
                    top_p=TOP_P, max_new_tokens=self.max_tokens,
                    pad_token_id=(self.tok.pad_token_id or self.tok.eos_token_id))
            new = gen[0][enc["input_ids"].shape[1]:]
            outs.append(self.tok.decode(new, skip_special_tokens=True).strip())
        return outs


class OpenAIBackend(LLMBackend):
    """--use-openai：GPT-4o-mini（投票器一票替换，对齐 MedHallu 原配方）。需 OPENAI_API_KEY。"""
    def __init__(self, model_id: str = "gpt-4o-mini", max_tokens: int = MAX_NEW_TOKENS):
        import os
        from openai import OpenAI
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("--use-openai 需环境变量 OPENAI_API_KEY（见 TODO[API-KEY]）")
        self.client = OpenAI()
        self.model_id = model_id
        self.max_tokens = max_tokens

    def generate_batch(self, prompts, temperature, system=None):
        outs = []
        for p in prompts:
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            msgs.append({"role": "user", "content": p})
            resp = self.client.chat.completions.create(
                model=self.model_id, messages=msgs, temperature=temperature,
                top_p=TOP_P, max_tokens=self.max_tokens)
            outs.append(resp.choices[0].message.content.strip())
        return outs


def _san(name: str) -> str:
    """把 model 名清成 CSV 列名安全 token（fooled_<voter_name> 列用；去 / : 空格等）。"""
    return re.sub(r"[^0-9A-Za-z]+", "-", str(name)).strip("-").lower() or "model"


class OpenAICompatBackend(LLMBackend):
    """
    🆕 全 API 模式后端（--backend api，见头注 [API-FULL]）：OpenAI 兼容 chat.completions API，不占 GPU。
    用 openai SDK 的 base_url 机制「一套代码指向多家 provider」（OpenAI / DeepSeek / Qwen dashscope /
    OpenRouter 聚合器…）。生成器 + 3 投票器都可用此后端，把大 LLM 全推到 API 侧，本地只留 NLI/embedding。

    健壮性：每次调用 retry（指数退避 min(2^attempt,30)s）+ 超时 + 失败计数；重试耗尽**不硬崩**，返回空串
    （Phase1 空生成后续会被长度/NLI 过滤；Phase2 judge 空串 _parse_judge→1=识破，保守不留伪幻觉）。
    成本保护：所有 API 后端共享一个 counter（dict），累计调用/失败/放弃数写进 state.json；达 --api-max-calls
    上限即 raise 硬停（防意外刷爆真金）。key 只从环境变量读，绝不硬编码。
    """
    def __init__(self, model_id: str, base_url: str | None = None,
                 api_key_env: str = DEFAULT_API_KEY_ENV, max_tokens: int = MAX_NEW_TOKENS,
                 timeout: float = API_TIMEOUT_S, max_retries: int = API_MAX_RETRIES,
                 counter: dict | None = None):
        import os
        from openai import OpenAI
        key = os.environ.get(api_key_env)
        if not key:
            raise RuntimeError(
                f"--backend api 需环境变量 {api_key_env} 提供 key（见 TODO[API-KEY]/[API-FULL]）。"
                f"key 只从环境变量读，脚本内绝不硬编码。设法：PowerShell $env:{api_key_env}='...'；"
                f"bash export {api_key_env}=...")
        client_kwargs = {"api_key": key, "timeout": timeout}
        if base_url:                       # 留空=OpenAI 官方端点；给了则指向该 provider
            client_kwargs["base_url"] = base_url
        self.client = OpenAI(**client_kwargs)
        self.model_id = model_id
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.counter = counter
        print(f"[api] backend ready: model={model_id} base_url={base_url or 'OpenAI默认'} "
              f"key_env={api_key_env}", flush=True)

    def _one_call(self, msgs, temperature) -> str:
        import time
        # 成本上限保护：达 --api-max-calls 即硬停（raise 传到 main）。计数在真正发起调用前 +1。
        if self.counter is not None:
            cap = self.counter.get("api_max_calls")
            if cap is not None and self.counter.get("api_calls", 0) >= cap:
                raise RuntimeError(
                    f"[api] 已达 --api-max-calls 上限 {cap} 次调用，硬停（成本保护，防意外刷爆）。"
                    f"已完成的阶段产出会随异常终止——如需更多调用，调大 --api-max-calls 后重跑。")
        last_err = None
        for attempt in range(self.max_retries):
            if self.counter is not None:
                self.counter["api_calls"] = self.counter.get("api_calls", 0) + 1
            try:
                resp = self.client.chat.completions.create(
                    model=self.model_id, messages=msgs, temperature=temperature,
                    top_p=TOP_P, max_tokens=self.max_tokens)   # 超参照 brief §7：top_p 0.95 / max 512
                return (resp.choices[0].message.content or "").strip()
            except Exception as e:                              # 网络/限流/超时等，退避重试
                last_err = e
                if self.counter is not None:
                    self.counter["api_failures"] = self.counter.get("api_failures", 0) + 1
                wait = min(2 ** attempt, 30)
                print(f"[api][retry {attempt + 1}/{self.max_retries}] {self.model_id} 调用失败: {e}；"
                      f"{wait}s 后重试", flush=True)
                time.sleep(wait)
        # 重试耗尽：不硬崩，返回空串并计数放弃（保管线不中断）
        if self.counter is not None:
            self.counter["api_giveup"] = self.counter.get("api_giveup", 0) + 1
        print(f"[api][FAIL] {self.model_id} 重试 {self.max_retries} 次仍失败，返回空串: {last_err}", flush=True)
        return ""

    def generate_batch(self, prompts, temperature, system=None):
        outs = []
        for p in prompts:
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            msgs.append({"role": "user", "content": p})
            outs.append(self._one_call(msgs, temperature))
        return outs


class MockBackend(LLMBackend):
    """--smoke：不下模型，返回可预测的假输出，验四阶段管线逻辑通（不占卡不联网）。"""
    def __init__(self, role: str = "gen"):
        self.role = role  # gen=生成幻觉答案 / judge=返回 0/1/2

    def generate_batch(self, prompts, temperature, system=None):
        if self.role == "judge":
            # 假投票：交替给 0（被骗）/1（识破），让 hard/med/easy 都出现
            return [str(i % 2) for i in range(len(prompts))]
        # 假生成：回一句带轻微改动的中文，长度可控
        return [f"（模拟幻觉答案 t={temperature:.2f}）此处为占位构造答案，仅供烟测管线。"
                for _ in prompts]


def make_backend(kind: str, model_id: str, role: str = "gen",
                 tensor_parallel_size: int = 1, base_url: str | None = None,
                 api_key_env: str = DEFAULT_API_KEY_ENV, timeout: float = API_TIMEOUT_S,
                 max_retries: int = API_MAX_RETRIES, counter: dict | None = None):
    if kind == "mock":
        return MockBackend(role=role)
    if kind == "vllm":
        return VLLMBackend(model_id, tensor_parallel_size=tensor_parallel_size)
    if kind == "hf":
        return HFBackend(model_id)
    if kind == "openai":
        return OpenAIBackend(model_id)
    if kind == "api":                      # 🆕 全 API 模式（OpenAI 兼容，可配 provider，不占 GPU）
        return OpenAICompatBackend(model_id, base_url=base_url, api_key_env=api_key_env,
                                   timeout=timeout, max_retries=max_retries, counter=counter)
    raise ValueError(f"未知 backend: {kind}")


# ============================================================================
# 🔴-2 解耦硬校验（PLAN §0.6）：投票器/生成器绝不用 K1 承重 judge D11/D12
# ============================================================================
def _assert_no_k1_judge(model_ids, where: str):
    for mid in model_ids:
        if mid in K1_JUDGE_FORBIDDEN:
            raise RuntimeError(
                f"[🔴-2 解耦] {where} 命中 K1 承重 judge 黑名单 '{mid}'（D11 GLM-4 / D12 InternLM2.5）。"
                f"投票器/生成器与最终评测 judge 必须解耦，否则构造循环使 K1 judge 臂失效。"
                f"换非黑名单型号（见 PLAN §0.6 / TODO[DECOUPLE]）。")


# ============================================================================
# Phase1：候选生成
# ============================================================================
def phase1_generate(items, gen_backend: LLMBackend):
    """
    每条证据对 9 类内容型各生成 1 个幻觉候选。返回候选 list（含 type / 长度比）。
    """
    type_catalog = build_type_catalog_zh()
    system = SYSTEM_PROMPT_ZH.format(type_catalog=type_catalog)

    prompts, meta = [], []
    for it in items:
        gt_len = len(it["gt_answer"])
        target_len = max(1, int(round(gt_len)))
        for t in HALLU_TYPES:
            prompts.append(USER_PROMPT_ZH.format(
                type_name=t["name"], type_def=t["definition"],
                question=it["question"], evidence=it["evidence"],
                gt_answer=it["gt_answer"], target_len=target_len))
            meta.append({"hid": it["hid"], "type": t["id"], "type_name": t["name"]})

    # 每个候选一个在 [0.3,0.7] 变动的 temperature（brief §7）
    rng = random.Random(DOWNSAMPLE_SEED)
    candidates = []
    # 逐 temperature 分桶批量（同 temp 一批，vLLM 高效）——这里简单起见逐条给随机 temp，
    # 对 vLLM 用同一 SamplingParams 批；为保留"每候选独立 temp"，按 temp 分组。
    temp_of = [round(rng.uniform(TEMP_MIN, TEMP_MAX), 3) for _ in prompts]
    order = sorted(range(len(prompts)), key=lambda k: temp_of[k])
    grouped = {}
    for k in order:
        grouped.setdefault(temp_of[k], []).append(k)

    id2text = {}
    for temp, ks in grouped.items():
        batch_prompts = [prompts[k] for k in ks]
        outs = gen_backend.generate_batch(batch_prompts, temperature=temp, system=system)
        for k, txt in zip(ks, outs):
            id2text[k] = txt

    it_by_hid = {it["hid"]: it for it in items}
    for k in range(len(prompts)):
        m = meta[k]
        it = it_by_hid[m["hid"]]
        hallu = _clean_gen(id2text.get(k, ""))
        gt_len = len(it["gt_answer"])
        h_len = len(hallu)
        len_ratio = (h_len / gt_len) if gt_len else 0.0
        candidates.append({
            "hid": m["hid"], "cmexam_id": it.get("cmexam_id", ""),
            "correct_letters": it.get("correct_letters", ""),
            "question": it["question"], "evidence": it["evidence"],
            "gt_answer": it["gt_answer"], "hallu_answer": hallu,
            "type": m["type"], "type_name": m["type_name"],
            "gen_temperature": temp_of[k], "len_ratio": round(len_ratio, 3),
            "len_ok": abs(len_ratio - 1.0) <= LEN_TOL,
        })
    print(f"[phase1] 生成候选 {len(candidates)} 个（{len(items)} 证据 × {len(HALLU_TYPES)} 类）", flush=True)
    return candidates


def _clean_gen(txt: str) -> str:
    """清掉模型可能带的前缀（"幻觉答案："）/ 引号 / 多余空白。"""
    if not txt:
        return ""
    txt = txt.strip()
    txt = re.sub(r"^(幻觉答案|答案|输出)[:：]\s*", "", txt)
    txt = txt.strip().strip('"“”\'').strip()
    # 只取第一段（模型偶尔附解释）
    return txt.split("\n\n")[0].strip()


# ============================================================================
# Phase2：3-LLM 投票 + 难度分层
#   投票器判"待判答案 = 幻觉答案"是否忠实。骗过 = 投票器判 0（忠实）→ 没识破幻觉。
#   保留规则 = 骗过 ≥1 个；难度 hard(全骗)/medium(部分)/easy(仅1)。
# ============================================================================
def _parse_judge(txt: str) -> int:
    """从投票器输出里抠 0/1/2，抠不到当 1（识破，保守不留伪幻觉）。"""
    m = re.search(r"[012]", txt or "")
    return int(m.group()) if m else 1


def phase2_vote(candidates, voter_backends, voter_names):
    """
    voter_backends: list[LLMBackend]（每个投票器一个后端）。
    给每个候选记：fooled_<voter> (bool) + n_fooled + difficulty。保留 n_fooled>=1。
    """
    n_voters = len(voter_backends)
    prompts = [VOTER_JUDGE_PROMPT_ZH.format(
        question=c["question"], evidence=c["evidence"], answer=c["hallu_answer"])
        for c in candidates]

    votes = []  # votes[v] = list[int] 每个候选的判决
    for v, be in enumerate(voter_backends):
        # 投票器判决温度用低值（判别任务求稳），非生成温度；这里固定 0.0
        outs = be.generate_batch(prompts, temperature=0.0, system=None)
        votes.append([_parse_judge(o) for o in outs])
        print(f"[phase2] 投票器 {voter_names[v]} 判决完成（{len(candidates)} 候选）", flush=True)

    kept = []
    for i, c in enumerate(candidates):
        fooled_flags = []
        for v in range(n_voters):
            # 判 0（忠实）= 被骗（没识破这个幻觉答案）
            fooled = (votes[v][i] == 0)
            fooled_flags.append(fooled)
            c[f"fooled_{voter_names[v]}"] = bool(fooled)
        n_fooled = sum(fooled_flags)
        c["n_fooled"] = int(n_fooled)
        c["n_voters"] = n_voters
        if n_fooled >= n_voters:
            c["difficulty"] = "hard"
        elif n_fooled >= 2:
            c["difficulty"] = "medium"
        elif n_fooled == 1:
            c["difficulty"] = "easy"
        else:
            c["difficulty"] = "rejected"   # 一个都没骗过 → 不留
        if n_fooled >= 1:
            kept.append(c)
    print(f"[phase2] 保留 {len(kept)}/{len(candidates)}（骗过≥1）", flush=True)
    return kept


# ============================================================================
# Phase3：两道 NLI 过滤（中文 NLI = mDeBERTa），两道都过才是合格幻觉：
#   (a) 幻觉vsGT：ℰ = min(NLI(H→GT), NLI(GT→H))；保留 ℰ < τ
#       → H 与 GT 非互相蕴含 = 真幻觉，滤掉"其实是同义正确答案"的伪幻觉（防造出同义正确答案，一层）。
#   (b) 🆕 幻觉vs证据（faithfulness 核心判据，守 R3）：nli_evi2hallu = NLI(证据 → 幻觉答案) 的 entailment 分。
#       faithfulness 定义 = 答案是否被给定证据支持；真幻觉必须 **NOT entailed by 证据**。
#       nli_evi2hallu ≥ τ_evi = 幻觉答案其实被证据支持 = 忠实于证据 = 滤掉；保留 < τ_evi（真不忠实）。
#       —— mini-pilot 样本3「酸溶血试验阳性…确诊特异性」其实忠实于证据却混进来，根因就是漏了这道。
#   两道复用同一 mDeBERTa 实例（不重复加载）。
# ============================================================================
def _load_nli(device):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    print(f"[phase3] loading NLI {NLI_MODEL_ID} on {device} ...", flush=True)
    tok = AutoTokenizer.from_pretrained(NLI_MODEL_ID)
    model = AutoModelForSequenceClassification.from_pretrained(NLI_MODEL_ID).to(device).eval()
    label2id = {k.lower(): v for k, v in model.config.label2id.items()}
    if "entailment" not in label2id:
        raise RuntimeError(f"[NLI] config.label2id 无 'entailment'：{model.config.label2id}")
    return tok, model, label2id["entailment"]


def _nli_entail_prob(tok, model, entail_idx, premises, hyps, device, batch_size=16):
    import torch
    probs = np.empty(len(premises), dtype=float)
    for s in range(0, len(premises), batch_size):
        bp = [str(x) for x in premises[s:s + batch_size]]
        bh = [str(x) for x in hyps[s:s + batch_size]]
        enc = tok(bp, bh, truncation="longest_first", max_length=512,
                  padding=True, return_tensors="pt").to(device)
        with torch.no_grad():
            logits = model(**enc).logits
        probs[s:s + len(bp)] = torch.softmax(logits, dim=-1)[:, entail_idx].cpu().numpy()
    return probs


def phase3_entailment_filter(candidates, device, tau=NLI_TAU, tau_evi=NLI_TAU_EVIDENCE, use_mock=False):
    """
    两道 NLI 过滤，复用同一 mDeBERTa 实例（不重复加载）。返回 (kept, phase3_meta)。
      (a) 幻觉vsGT：ℰ = min(NLI(H→GT), NLI(GT→H)) < τ（防同义正确答案，原有一层）。
      (b) 🆕 幻觉vs证据（守 R3，faithfulness 核心判据）：nli_evi2hallu = NLI(证据 → 幻觉答案) < τ_evi
          （幻觉必须 NOT entailed by 证据；≥τ_evi = 其实忠实于证据 = 滤掉）。
    phase3_meta 记 n_after_gt_filter / skipped_faithful_to_evidence（写进 state.json）。
    """
    if use_mock:
        # --smoke：假 NLI 分，(a)(b) 都设 < 阈值 → 全保留，验管线（含新过滤 mock 分支）
        for c in candidates:
            c["nli_h2gt"] = 0.1
            c["nli_gt2h"] = 0.1
            c["entail_E"] = 0.1
            c["nli_evi2hallu"] = 0.1      # 证据不蕴含幻觉 → 真幻觉，保留
        kept_gt = [c for c in candidates if c["entail_E"] < tau]
        kept = [c for c in kept_gt if c["nli_evi2hallu"] < tau_evi]
        skipped_evi = len(kept_gt) - len(kept)
        print(f"[phase3][mock] 幻觉vsGT 保留 {len(kept_gt)}/{len(candidates)} (ℰ<{tau})；"
              f"evidence-grounded 保留 {len(kept)}/{len(kept_gt)} (nli_evi2hallu<{tau_evi})", flush=True)
        return kept, {"n_after_gt_filter": len(kept_gt),
                      "skipped_faithful_to_evidence": skipped_evi}

    tok, model, entail_idx = _load_nli(device)
    H = [c["hallu_answer"] for c in candidates]
    GT = [c["gt_answer"] for c in candidates]
    EVI = [c["evidence"] for c in candidates]
    p_h2gt = _nli_entail_prob(tok, model, entail_idx, H, GT, device)     # premise=H,  hyp=GT
    p_gt2h = _nli_entail_prob(tok, model, entail_idx, GT, H, device)     # premise=GT, hyp=H
    p_evi2h = _nli_entail_prob(tok, model, entail_idx, EVI, H, device)   # 🆕 premise=证据, hyp=幻觉答案
    kept = []
    n_gt_kept = 0
    skipped_evi = 0
    for i, c in enumerate(candidates):
        E = float(min(p_h2gt[i], p_gt2h[i]))
        c["nli_h2gt"] = round(float(p_h2gt[i]), 4)
        c["nli_gt2h"] = round(float(p_gt2h[i]), 4)
        c["entail_E"] = round(E, 4)
        c["nli_evi2hallu"] = round(float(p_evi2h[i]), 4)
        # (a) 幻觉vsGT：ℰ≥τ = 同义正确答案，滤（原有一层）
        if E >= tau:
            continue
        n_gt_kept += 1
        # (b) 🆕 evidence-grounded（守 R3）：证据蕴含幻觉答案（高分）= 幻觉其实忠实于证据 = 滤掉
        if c["nli_evi2hallu"] >= tau_evi:
            skipped_evi += 1
            continue
        kept.append(c)
    print(f"[phase3] 幻觉vsGT 保留 {n_gt_kept}/{len(candidates)}（ℰ<{tau}，滤同义正确答案）；"
          f"evidence-grounded 保留 {len(kept)}/{n_gt_kept}（nli_evi2hallu<{tau_evi}，滤"
          f"「其实忠实于证据」{skipped_evi} 条，守 R3 faithfulness）", flush=True)
    return kept, {"n_after_gt_filter": n_gt_kept,
                  "skipped_faithful_to_evidence": skipped_evi}


# ============================================================================
# Phase4：兜底（每条证据选与 GT 余弦相似度最大的候选）+ 可选 TextGrad（默认跳过）
# ============================================================================
def _embed(texts, model_id, device, use_mock=False):
    if use_mock:
        # --smoke：假 embedding（长度归一的随机向量），只验选择逻辑
        rng = np.random.default_rng(0)
        return rng.random((len(texts), 8))
    from sentence_transformers import SentenceTransformer
    print(f"[phase4] loading embedding {model_id} on {device} ...", flush=True)
    st = SentenceTransformer(model_id, device=device)
    return np.asarray(st.encode(texts, normalize_embeddings=True, show_progress_bar=False))


def _cos(a, b):
    na = np.linalg.norm(a) + 1e-12
    nb = np.linalg.norm(b) + 1e-12
    return float(np.dot(a, b) / (na * nb))


def phase4_fallback(candidates, embed_model, device, use_mock=False, textgrad=False):
    """
    每个 hid 选与 GT 余弦相似度最大的候选（MedHallu Phase4 兜底逻辑）。
    --textgrad：TextGrad 精修（TODO，默认跳过——见头注 Phase4 说明）。
    """
    if textgrad:
        # TODO[TEXTGRAD]：TextGrad 精修（backend GPT-4o-mini，最多 5 次；MedHallu generation.py）
        # 未实现，默认关。主线要开需 clone MedHallu 的 TextGrad 精修逻辑 + 定 backend。
        print("[phase4][WARN] --textgrad 尚未实现（见 TODO[TEXTGRAD]），本轮仍只走兜底选择。", flush=True)

    # 按 hid 分组
    by_hid = {}
    for c in candidates:
        by_hid.setdefault(c["hid"], []).append(c)

    # 一次性 encode 所有 hallu + 各 GT
    all_texts, idx = [], {}
    for c in candidates:
        idx[id(c)] = len(all_texts)
        all_texts.append(c["hallu_answer"])
    gt_texts, gt_idx = [], {}
    for hid, cs in by_hid.items():
        gt_idx[hid] = len(all_texts) + len(gt_texts)
        gt_texts.append(cs[0]["gt_answer"])
    embs = _embed(all_texts + gt_texts, embed_model, device, use_mock=use_mock)

    finals = []
    for hid, cs in by_hid.items():
        gt_vec = embs[gt_idx[hid]]
        best, best_sim = None, -1.0
        for c in cs:
            sim = _cos(embs[idx[id(c)]], gt_vec)
            c["cos_sim_gt"] = round(sim, 4)
            if sim > best_sim:
                best_sim, best = sim, c
        if best is not None:
            best["selected"] = True
            finals.append(best)
    print(f"[phase4] 兜底选出 {len(finals)} 条最终 zh-med 幻觉样本", flush=True)
    return finals


# ============================================================================
# 输出：csv + state.json
# ============================================================================
# 注：hid/cmexam_id = CMExam 指针；question/evidence/gt_answer = CMExam 原文派生列，仅内部文件保留，
#     正式发布集据 cmexam_id 剔除这三列，只发 hallu_answer + 派生标签（见 [CMEXAM] 许可合规）。
CSV_FIELDS = [
    "hid", "cmexam_id", "correct_letters", "question", "evidence", "gt_answer", "hallu_answer",
    "type", "type_name", "difficulty", "n_fooled", "n_voters",
    "entail_E", "nli_h2gt", "nli_gt2h", "nli_evi2hallu", "cos_sim_gt",
    "gen_temperature", "len_ratio", "len_ok",
]


def write_outputs(finals, voter_names, meta: dict):
    DATA_OUT_DIR.mkdir(parents=True, exist_ok=True)
    import csv

    # 动态补投票器被骗列（fooled_<name>）
    fooled_cols = [f"fooled_{n}" for n in voter_names]
    fields = CSV_FIELDS + fooled_cols

    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for c in finals:
            w.writerow(c)

    # state：难度分布 / 类型分布 / 成功率 / 各投票器被骗率 / 超参快照
    diff_dist, type_dist = {}, {}
    for c in finals:
        diff_dist[c["difficulty"]] = diff_dist.get(c["difficulty"], 0) + 1
        type_dist[c["type"]] = type_dist.get(c["type"], 0) + 1
    fool_rate = {}
    for n in voter_names:
        col = f"fooled_{n}"
        vals = [1 for c in finals if c.get(col)]
        fool_rate[n] = round(len(vals) / max(1, len(finals)), 4)

    state = {
        "run": "R-P1.1/R-P1.2 build_zh_med",
        "n_final": len(finals),
        "difficulty_dist": diff_dist,
        "type_dist": type_dist,
        "voter_fool_rate": fool_rate,
        "hyperparams": {
            "temperature_range": [TEMP_MIN, TEMP_MAX], "top_p": TOP_P,
            "max_new_tokens": MAX_NEW_TOKENS, "len_tol": LEN_TOL,
            "nli_tau": NLI_TAU, "nli_tau_evidence_default": NLI_TAU_EVIDENCE,
            "nli_model": NLI_MODEL_ID,
            "n_candidates_per_item": N_CANDIDATES_PER_ITEM,
        },
        **meta,
    }
    OUT_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[out] csv  -> {OUT_CSV}", flush=True)
    print(f"[out] state-> {OUT_STATE}", flush=True)
    print(f"[out] 难度分布 {diff_dist} ｜ 类型数 {len(type_dist)}", flush=True)


# ============================================================================
# main
# ============================================================================
def main():
    ap = argparse.ArgumentParser(
        description="CMedFaith 中文医学 faithfulness 数据构造（MedHallu 四阶段中文复刻，R-P1.1/1.2）")
    # 后端 / 模型
    ap.add_argument("--backend", choices=["vllm", "hf", "api", "mock"], default="vllm",
                    help="生成/投票后端：vllm(HPC首选)/hf(通用)/api(全API不占GPU,见[API-FULL])/mock(仅--smoke)")
    ap.add_argument("--generator", default=DEFAULT_GENERATOR, help="Phase1 生成器（默认 Qwen2.5-14B）")
    ap.add_argument("--voter1", default=DEFAULT_VOTER1, help="投票器1（默认 Qwen2.5-7B=D10 构造臂）")
    ap.add_argument("--voter2", default=DEFAULT_VOTER2, help="投票器2（默认 Gemma2-9B）")
    ap.add_argument("--voter3-model", default=DEFAULT_VOTER3,
                    help="投票器3（[V3] 定案 Yi-1.5-9B-Chat；覆盖成 D11/D12 会被 _assert_no_k1_judge raise）")
    ap.add_argument("--use-openai", action="store_true",
                    help="投票器3 换 GPT-4o-mini（对齐 MedHallu 原配方，需 OPENAI_API_KEY，API 花费拍板点）")
    # 全 API 模式（--backend api）：生成器+3投票器全走 OpenAI 兼容 API，不占 GPU（见头注 [API-FULL]）
    ap.add_argument("--api-base-url", default=None,
                    help="[api] provider 端点。留空=OpenAI 官方；DeepSeek=https://api.deepseek.com；"
                         "Qwen dashscope=https://dashscope.aliyuncs.com/compatible-mode/v1；"
                         "OpenRouter=https://openrouter.ai/api/v1（一套 base_url 跑三家不同 model）")
    ap.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV,
                    help="[api] 读哪个环境变量取 key（默认 OPENAI_API_KEY；DeepSeek 用 DEEPSEEK_API_KEY 等）。"
                         "key 只从环境变量读，绝不硬编码")
    ap.add_argument("--gen-model", default=None,
                    help="[api] Phase1 生成器 model 名（如 gpt-4o-mini/deepseek-chat/qwen-plus；"
                         f"留空用占位默认 {DEFAULT_API_GEN}，⚠️可用性待用户核 TODO[API-FULL]）")
    ap.add_argument("--voter-models", nargs=3, default=None, metavar=("V1", "V2", "V3"),
                    help="[api] 3 个投票器 model 名（保多样性，建议 3 个不同 model，如 "
                         "deepseek-chat gpt-4o-mini qwen-plus；留空用占位默认（同质，会削弱难度分层，"
                         "见 TODO[API-FULL]））")
    ap.add_argument("--voter-base-urls", nargs=3, default=None, metavar=("U1", "U2", "U3"),
                    help="[api] 高级：3 投票器各自 provider 端点（各家直连时用，跨 provider 多样性最强）。"
                         "留空则都用 --api-base-url")
    ap.add_argument("--voter-key-envs", nargs=3, default=None, metavar=("K1", "K2", "K3"),
                    help="[api] 高级：3 投票器各自 key 环境变量名（配 --voter-base-urls 用）。"
                         "留空则都用 --api-key-env")
    ap.add_argument("--api-max-calls", type=int, default=API_MAX_CALLS_DEFAULT,
                    help=f"[api] 全局 API 调用上限（防意外刷爆真金；默认 {API_MAX_CALLS_DEFAULT}，达上限硬停）。"
                         "全 pilot 调用数≈limit×9×4，limit=150→~5400")
    ap.add_argument("--api-timeout", type=float, default=API_TIMEOUT_S,
                    help=f"[api] 单次 API 调用超时秒数（默认 {API_TIMEOUT_S}）")
    ap.add_argument("--api-max-retries", type=int, default=API_MAX_RETRIES,
                    help=f"[api] 单次调用失败重试次数（指数退避，默认 {API_MAX_RETRIES}）")
    ap.add_argument("--tau-evidence", type=float, default=NLI_TAU_EVIDENCE,
                    help="[Phase3 第二道·守 R3] evidence-grounded 过滤阈值 τ_evi：nli_evi2hallu"
                         "(证据→幻觉答案 entailment 分) ≥ 此值 = 幻觉其实被证据支持=忠实=滤掉；"
                         f"保留 < 此值(真不忠实)。默认 {NLI_TAU_EVIDENCE}，TODO 主线 pilot 抽检后校准（见头注 [TAU-EVI]）")
    ap.add_argument("--embed-model", default=DEFAULT_EMBED,
                    help="Phase4 中文句向量（[EMB] 定案 BAAI/bge-base-zh-v1.5）")
    ap.add_argument("--textgrad", action="store_true", help="Phase4 TextGrad 精修（TODO，默认跳过）")
    ap.add_argument("--tensor-parallel-size", type=int, default=1,
                    help="vLLM 多卡张量并行（14B 单卡放不下时用；默认单卡）")
    # 数据（CMExam，见 [CMEXAM]；字段名大小写敏感，未在本地核过，主线跑前确认）
    ap.add_argument("--cmexam-repo", default="fzkuji/CMExam",
                    help="CMExam HF repo（[CMEXAM] 主线核实际列名/config）")
    ap.add_argument("--cmexam-config", default=None, help="CMExam config（如需）")
    ap.add_argument("--question-field", default="Question", help="题干字段（默认 CMExam 'Question'）")
    ap.add_argument("--options-field", default="Options", help="选项字段（默认 CMExam 'Options'）")
    ap.add_argument("--answer-field", default="Answer", help="正确答案字母字段（默认 CMExam 'Answer'）")
    ap.add_argument("--explanation-field", default="Explanation",
                    help="解析字段=证据段（默认 CMExam 'Explanation'，空则跳过该行）")
    ap.add_argument("--id-field", default=None,
                    help="CMExam 题目 ID 字段（供指针化；无则用行号 cmexam_row_<i>）")
    ap.add_argument("--cache-dir", default=None, help="HF datasets cache（默认 HF 环境变量）")
    ap.add_argument("--limit", type=int, default=150, help="抽 CMExam 证据条数（pilot 目标 100-200）")
    ap.add_argument("--seed", type=int, default=DOWNSAMPLE_SEED, help="抽样/温度种子")
    ap.add_argument("--device", default=None, help="cuda/cpu（NLI/embedding；默认自动）")
    ap.add_argument("--smoke", type=int, default=0, help=">0：mock 烟测（不下模型不占卡，验管线）")
    args = ap.parse_args()

    smoke = args.smoke > 0
    if smoke:
        args.backend = "mock"
        args.limit = min(args.limit, max(2, args.smoke))
        print(f"[smoke] mock 烟测，limit={args.limit}（不下模型/不联网/不占卡）", flush=True)

    # device 自动
    if args.device is None:
        try:
            import torch
            args.device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            args.device = "cpu"

    api_mode = (args.backend == "api")

    # 全 API 模式：解析生成器 + 3 投票器 model 名（占位默认可用性待用户核，见 TODO[API-FULL]）
    if api_mode:
        gen_model = args.gen_model or DEFAULT_API_GEN
        voter_models = list(args.voter_models) if args.voter_models else list(DEFAULT_API_VOTERS)
        api_counter = {"api_calls": 0, "api_failures": 0, "api_giveup": 0,
                       "api_max_calls": args.api_max_calls}
    else:
        gen_model, voter_models, api_counter = None, None, None

    # 🔴-2 解耦硬校验（生成器 + 3 投票器都不能是 D11/D12；Yi-1.5-9B-Chat 放行）
    # 全 API 下投票器/生成器用的是 API model 名（如 deepseek-chat），非本地 D11/D12 HF repo，照跑硬校验放行。
    if api_mode:
        voter3_id = voter_models[2]
        _assert_no_k1_judge([gen_model] + voter_models, where="生成器/投票器(API)")
    else:
        voter3_id = "gpt-4o-mini" if args.use_openai else args.voter3_model
        _assert_no_k1_judge([args.generator, args.voter1, args.voter2, voter3_id],
                            where="生成器/投票器")

    # ---- 数据（CMExam：Explanation→证据 / Question+正确选项→GT，见 [CMEXAM]）----
    load_meta = {}
    if smoke:
        # mock 烟测样本：模拟 CMExam 派生（evidence=Explanation 风格 / gt=Question+正确选项合成陈述句）
        items = [
            {"hid": "cmexam_smoke_0", "cmexam_id": "cmexam_row_smoke0", "correct_letters": "A",
             "question": "下列哪类药物属于一线降压药？",
             "evidence": "解析：一线降压药包括 ACEI、ARB、钙拮抗剂和利尿剂，临床需根据患者合并症"
                         "个体化选择，故 A（ACEI）符合一线降压药定义。",
             "gt_answer": "针对问题「下列哪类药物属于一线降压药」，正确答案是：ACEI 类药物。"},
            {"hid": "cmexam_smoke_1", "cmexam_id": "cmexam_row_smoke1", "correct_letters": "B",
             "question": "二甲双胍降糖的主要机制是什么？",
             "evidence": "解析：二甲双胍主要通过抑制肝糖异生、降低肝糖输出来控制血糖，"
                         "并非促进胰岛素分泌，故 B（抑制肝糖异生）为正确机制。",
             "gt_answer": "针对问题「二甲双胍降糖的主要机制是什么」，正确答案是：抑制肝糖异生、降低肝糖输出。"},
        ][:args.limit]
    else:
        items, load_meta = load_cmexam(
            args.cmexam_repo, args.cmexam_config, args.question_field, args.options_field,
            args.answer_field, args.explanation_field, args.id_field,
            args.limit, args.cache_dir, args.seed)
    if not items:
        print("[FATAL] 无可用证据条目，检查 CMExam repo/字段名（见 [CMEXAM]，先核 features 再跑）。", flush=True)
        sys.exit(2)

    # ---- Phase1 生成 ----
    if api_mode:
        gen_backend = make_backend("api", gen_model, role="gen", base_url=args.api_base_url,
                                   api_key_env=args.api_key_env, timeout=args.api_timeout,
                                   max_retries=args.api_max_retries, counter=api_counter)
    else:
        gen_backend = make_backend(args.backend, args.generator, role="gen",
                                   tensor_parallel_size=args.tensor_parallel_size)
    candidates = phase1_generate(items, gen_backend)

    # ---- Phase2 投票 ----
    if smoke:
        voter_names = ["qwen7b", "gemma9b", "voter3"]
        voter_backends = [MockBackend(role="judge") for _ in range(3)]
    elif api_mode:
        # 全 API：3 投票器各走 API model；列名带序号防同 model 时列冲突（fooled_v1_.../v2_.../v3_...）
        voter_names = [f"v{i + 1}_{_san(m)}" for i, m in enumerate(voter_models)]
        vbu = list(args.voter_base_urls) if args.voter_base_urls else [args.api_base_url] * 3
        vke = list(args.voter_key_envs) if args.voter_key_envs else [args.api_key_env] * 3
        voter_backends = [
            make_backend("api", voter_models[i], role="judge", base_url=vbu[i],
                         api_key_env=vke[i], timeout=args.api_timeout,
                         max_retries=args.api_max_retries, counter=api_counter)
            for i in range(3)
        ]
    else:
        voter_names = ["qwen7b", "gemma9b", ("gpt4omini" if args.use_openai else "voter3")]
        voter_backends = [
            make_backend(args.backend, args.voter1, role="judge",
                         tensor_parallel_size=args.tensor_parallel_size),
            make_backend(args.backend, args.voter2, role="judge",
                         tensor_parallel_size=args.tensor_parallel_size),
            (make_backend("openai", "gpt-4o-mini", role="judge") if args.use_openai
             else make_backend(args.backend, args.voter3_model, role="judge",
                               tensor_parallel_size=args.tensor_parallel_size)),
        ]
    kept2 = phase2_vote(candidates, voter_backends, voter_names)
    if not kept2:
        print("[WARN] Phase2 后无候选（无一骗过投票器）——投票器过强或生成质量低，检查后重跑。", flush=True)

    # ---- Phase3：两道 NLI 过滤（幻觉vsGT 防同义正确 + 🆕 幻觉vs证据 守 R3 faithfulness）----
    kept3, phase3_meta = phase3_entailment_filter(
        kept2, args.device, tau=NLI_TAU, tau_evi=args.tau_evidence, use_mock=smoke)

    # ---- Phase4 兜底 ----
    finals = phase4_fallback(kept3, args.embed_model, args.device,
                             use_mock=smoke, textgrad=args.textgrad)

    # ---- 输出 ----
    n_gen = len(candidates)
    meta = {
        "backend": args.backend,
        "generator": (gen_model if api_mode else args.generator),
        "voters": ({"voter_models": voter_models} if api_mode else
                   {"voter1": args.voter1, "voter2": args.voter2, "voter3": voter3_id}),
        "api": ({
            "base_url": args.api_base_url or "OpenAI默认",
            "key_env": args.api_key_env,
            "gen_model": gen_model, "voter_models": voter_models,
            "voter_base_urls": (list(args.voter_base_urls) if args.voter_base_urls
                                else [args.api_base_url or "OpenAI默认"] * 3),
            "api_calls": api_counter["api_calls"],
            "api_failures": api_counter["api_failures"],
            "api_giveup": api_counter["api_giveup"],
            "api_max_calls": args.api_max_calls,
            "note": "全 API 模式：生成器+3投票器走 API 不占 GPU；Phase3 NLI/Phase4 embedding 仍本地",
        } if api_mode else None),
        "use_openai": args.use_openai, "embed_model": args.embed_model,
        "evidence_source": "CMExam (fzkuji/CMExam, Apache-2.0)",
        "cmexam_repo": args.cmexam_repo, "cmexam_config": args.cmexam_config,
        "field_mapping": {"evidence": args.explanation_field,
                          "gt": f"{args.question_field}+正确选项文本(Options 按 Answer 取)"},
        "load_skip_counts": load_meta,
        "n_items": len(items), "n_candidates_generated": n_gen,
        "n_after_phase2": len(kept2), "n_after_phase3": len(kept3),
        "n_after_phase3_gt_filter": phase3_meta["n_after_gt_filter"],       # 幻觉vsGT 过后
        "skipped_faithful_to_evidence": phase3_meta["skipped_faithful_to_evidence"],  # 🆕 被 evidence-grounded 滤掉（其实忠实于证据）
        "nli_tau_evidence_used": args.tau_evidence,                          # 🆕 本轮 τ_evi 实际取值
        "n_final": len(finals),
        "construct_success_rate": round(len(finals) / max(1, n_gen), 4),
        "smoke": smoke,
        "license_note": "CMExam 不可重分发；zh_med_pilot.csv 为内部文件，正式发布只发 hallu_answer + cmexam_id 指针",
        "todo_open": ["HPC-ENV", "CMEXAM(列名待核)", "PROMPT", "JUDGE-P",
                      "V3(已定案 Yi-1.5-9B-Chat)", "EMB(已定案 bge-base-zh-v1.5)", "DECOUPLE(已硬校验)"]
                     + (["API-FULL(provider/model可用性待用户核)"] if api_mode else []),
    }
    write_outputs(finals, voter_names, meta)
    print("[done] R-P1.1/1.2 中文医学 faithfulness 构造完成（smoke）" if smoke
          else "[done] R-P1.1/1.2 中文医学 faithfulness 构造完成", flush=True)


if __name__ == "__main__":
    main()
