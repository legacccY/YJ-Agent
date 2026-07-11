#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
k3_probe.py — CMedFaith P1 阶段 K3 初验（现成检测器中文医学 faithfulness 是否失效）
================================================================================
服务：CMedFaith / lever L2（发现+基线：现成检测器医学域失效）+ kill criteria K3
（中文迁移初验）。这是 **P1 粗信号 gate**，不是 P3 正式评测。

━━ 这个脚本在问什么（背景 → 逻辑 → rationale）━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 背景：CMedFaith 的核心 claim 之一是「现成 faithfulness 检测器在**中文医学**上识别不出
  幻觉」。前面的 pilot（killshot_med_vs_general / eval_harness）在**英文**上量到医学域
  比通用域弱（G_domain≈+0.29）。K3 要看这个"失效"能不能**迁移到中文**——用一个
  **原生支持中文**的现成检测器，直接测我们造的中文医学幻觉，看它抓不抓得住。
- 逻辑：取 R-P1.1 产出的 14 条中文医学数据（code/data/zh_med_pilot.csv），每条派生
  两条测试样本——一条 faithful（答案=gt_answer）、一条 unfaithful（答案=hallu_answer），
  共 **28 条平衡测试集**（14 正 14 负）。让检测器逐条判「有无幻觉」，与真值比对。
- rationale（怎么读结果）：
    * BA（Balanced Accuracy）接近 0.5 或偏低  → 检测器在中文医学上**基本抓瞎**，
      支持"现成检测器中文医学弱"（核心 claim 初步成立，值得上 P3 全套横评）。
    * BA 偏高（例 >0.8）→ 两种可能都要**警惕**：① 我们造的对抗幻觉**太明显**
      （检测器轻松识别 = 数据构造强度不够，需回看 Phase2 筛子）；② 该检测器其实
      对中文医学不弱（削弱 claim）。两者都得停下人工看逐条，别急着下结论。

━━ 两个检测后端（--detector）━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
本脚本支持两个独立检测后端，逐条对 28 条测试样本判「忠实 / 不忠实」：
  · --detector judge  （🆕 **当前默认**）= LLM-judge 后端，走 GLM-4-9B（硅基流动 API），
       evidence-conditioned 中文 faithfulness 判定（MedHallu 二分类式）。
  · --detector lettuce= LettuceDetect 多语版（transformer span 检测器），当前**跑不了**
       （版本地狱，见下），版本修好后可用。

  ⚠️ 为什么默认改成了 judge（LettuceDetect 版本地狱备注）：
    LettuceDetect 多语版 KRLabsOrg/lettucedect-v2-mmbert-base 的 mmBERT 底座要求较新的
    transformers，而本仓已跑通验证的 eval_harness / build_zh_med 依赖当前 transformers
    版本——升级会触发 `TokenizersBackend` 不存在等破坏性改动，**破坏已验证的下游管线**。
    为不动稳定环境、先拿到 K3 粗信号，改用 API judge 做初验。lettuce 后端代码保留，环境
    版本修好后 `--detector lettuce` 即可用。

━━ 🔴 独立性红线（避循环，🔴-2 精神）━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
我们的**构造管线**用了：DeepSeek-V3.2（Phase1 生成）+ DeepSeek/Qwen 投票（Phase2 "骗过
检测器"筛子）+ mDeBERTa NLI（Phase3 过滤）。K3 检测器**绝不能**用这几个，否则就是
"用造数据的模型测造的数据"= 循环自证。
  · judge 后端用 **GLM-4-9B**（硅基流动 model id `THUDM/GLM-4-9B-0414`）——它**没参与
    构造管线的任一阶段**（生成/投票/NLI 都不是它），对 K3 而言独立成立。注意 GLM-4 在
    STORY 里是 K1 承重 judge 臂（D11），但 K3 的"独立"是相对**构造管线**而言（不是相对
    K1 judge 名册）——GLM-4 没造过数据，用它当 K3 独立检测器不构成循环。
    （build_zh_med 的 `_assert_no_k1_judge` 黑名单是拦**构造用的**投票器/生成器别碰
    D11/D12，与此处 K3 判定后端用 GLM-4 是两回事，不冲突、不对本脚本生效。）
  · lettuce 后端用 **LettuceDetect 多语版**（KRLabsOrg/lettucedect-v2-mmbert-base），
    训练监督来自 PsiloQA，与 CMedFaith 构造管线完全独立；**不是**英文版
    `lettucedect-base-modernbert-en-v1`（英文检测器测中文无意义）。

━━ ⚠️ 这是粗信号，不是正式评测（别 overclaim）━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 样本量只有 28 条（14 pilot × 2），**统计上极弱**，只能给方向性信号，不能下定论。
- 只用了 **1 个检测器**（默认 GLM-4 judge / 或 LettuceDetect）。P3 正式评测要跑**全套 ~15 检测器**
  （族A NLI / 族B 专用 / 族C LLM-judge / 族D 自训，见 02_ACCEPTANCE L2-a）+ 大样本
  + bootstrap CI + 多检测器校正（Holm）。本脚本**不做** CI/校正（样本太小无意义）。
- 结论口径：BA/Macro-F1 只报点估计；混淆矩阵 + 逐类 recall 给人工看逐条对错。
  任何"现成检测器中文医学失效"的正式 claim 必须等 P3，不许拿这 28 条撑。

━━ 依赖 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  judge 后端（默认）：pandas, numpy, openai（openai SDK，走硅基流动 OpenAI 兼容端点）。
       复用 build_zh_med.OpenAICompatBackend（不重写 API 逻辑）；key 只从环境变量
       SILICONFLOW_API_KEY 读，不硬编码。judge 是纯 API 推理，**不占 GPU、不下模型**。
  lettuce 后端：额外需 lettucedetect（会拉 transformers + torch），当前版本地狱跑不了（见上）。
  指标（BA / Macro-F1 / 混淆矩阵 / 逐类 recall）全 **numpy 自算**，不引 sklearn/scipy
  （避与 torch 抢 OpenMP，见 CLAUDE.md Windows 规范；口径与 eval_harness 一致）。

━━ 主线跑法（coder 不跑，只交付）━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # ① 冒烟（mock judge，不调 API、不联网、零花费；验管线不破）
  python code/k3_probe.py --smoke 1
  # ② 设 key（PowerShell）： $env:SILICONFLOW_API_KEY = "sk-..."
  #    设 key（bash）    ： export SILICONFLOW_API_KEY=sk-...
  # ③ 全量 28 条（judge 默认，纯 API 推理不占 GPU；起卡槽填 0 卡登记）
  python tools/gpu_slot.py request cmedfaith local 0 "K3 judge API 推理"
  python code/k3_probe.py                 # ≈28 次 API 调用，约 ¥0.x（GLM-4-9B 便宜）
  # ④ 换 judge model（如别的独立模型）
  python code/k3_probe.py --judge-model <其它独立 model id>
  # ⑤ lettuce 后端（transformers 版本修好后才可用）
  python code/k3_probe.py --detector lettuce
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# 路径 & 常量（不硬编码绝对路径；以本脚本位置为锚，Windows/Path 兼容）
# ----------------------------------------------------------------------------
CODE_DIR = Path(__file__).resolve().parent              # .../CMedFaith/code
DEFAULT_DATA = CODE_DIR / "data" / "zh_med_pilot.csv"   # R-P1.1 产出的 14 条中文医学
DEFAULT_OUTDIR = CODE_DIR / "results"                   # 与 eval_harness 输出同目录

# 标签编码：faithful=0 / unfaithful=1（正类=幻觉/unfaithful，与 pilot/eval_harness 一致）
FAITHFUL, UNFAITHFUL = 0, 1

# 检测器 = LettuceDetect **多语/中文版**（独立于构造管线）。
# 确认来源：RESEARCH_BRIEF_2026-07-11 §2 检测器清单 + eval_harness.py STUB_DETECTORS D5，
# 两处一致给出此 HF id（MIT，mmBERT 底座，原生 7-14 语含中文，唯一原生中文专用）。
# 🔴 绝不用英文版 KRLabsOrg/lettucedect-base-modernbert-en-v1（英文检测器测中文无意义）。
# 备选多语底座：KRLabsOrg/lettucedect-210m-eurobert-*（EuroBERT，7 语），brief 里 id 带
# 通配未给全，故默认用完整给定的 mmBERT 版；主线可 --model-path 覆盖。
DEFAULT_MODEL_PATH = "KRLabsOrg/lettucedect-v2-mmbert-base"

# ----------------------------------------------------------------------------
# judge 后端（🆕 默认）：GLM-4-9B via 硅基流动（OpenAI 兼容端点），独立于构造管线。
#   独立性：GLM-4 未参与构造（构造用 DeepSeek 生成 + DeepSeek/Qwen 投票 + mDeBERTa NLI）→
#   用它做 K3 独立检测器不构成循环（见头注 🔴 独立性红线）。
#   key 只从环境变量 SILICONFLOW_API_KEY 读，绝不硬编码。
#   API 逻辑复用 build_zh_med.OpenAICompatBackend（不重写），此处只给默认端点/model/key-env。
# ----------------------------------------------------------------------------
DEFAULT_JUDGE_MODEL = "THUDM/GLM-4-9B-0414"                # 硅基流动 model id（独立 judge）
DEFAULT_JUDGE_BASE_URL = "https://api.siliconflow.cn/v1"  # 硅基流动 OpenAI 兼容端点
DEFAULT_JUDGE_KEY_ENV = "SILICONFLOW_API_KEY"             # key 环境变量名（只从环境读）
DEFAULT_JUDGE_TEMPERATURE = 0.0                           # 低温求判定稳定（0.0-0.2 区间；见红线）
JUDGE_API_MAX_CALLS = 500                                 # 成本保护上限（28 条约 28 次调用，留余量）

# judge 判定输出编码：不确定(2) 保守归 faithful(0)，同时单列 judge_raw + 计数（标注清楚，见红线）
UNCERTAIN_FALLBACK = FAITHFUL


# faithfulness judge prompt（MedHallu 式 evidence-conditioned，中文）：
#   只评 faithfulness（答案 vs 给定证据），不评世界知识对错（守 R3）。
#   0=忠实（答案每条陈述都被证据支持）/ 1=不忠实（含证据未支持或矛盾内容）/ 2=不确定。
JUDGE_PROMPT_ZH = """你是一个医学幻觉检测器。你的任务是判断"待判答案"是否**完全忠于给定证据**。

问题：{question}
给定证据：{evidence}
待判答案：{answer}

判断规则（**只看答案是否忠于给定证据，不看答案在现实中对不对**）：
- 只依据"给定证据"判断：答案里的每一条陈述都必须能被"给定证据"支持，才算忠实。
- **不要用你自己的医学知识判断答案在真实世界里是否正确**（不评 factuality，只评 faithfulness）。
- 若答案包含"给定证据"中找不到依据、或与"给定证据"直接冲突的内容，即为不忠实。

只输出一个数字：
0 = 忠实（答案的每一条陈述都被给定证据支持，无幻觉）
1 = 不忠实（答案含证据未支持或与证据矛盾的内容）
2 = 不确定（无法判断时选 2，不要瞎猜）

你的判断（只输出 0 / 1 / 2）："""


# ============================================================================
# 数据 → 平衡测试集（每条 pilot 派生 faithful + unfaithful 两条）
# ============================================================================
def load_pilot(data_path: Path) -> pd.DataFrame:
    """读 R-P1.1 的 14 条中文医学 pilot。缺列给清晰报错，不静默。"""
    data_path = Path(data_path)
    if not data_path.exists():
        raise FileNotFoundError(
            f"[k3] 找不到中文医学 pilot 数据：{data_path}\n"
            "  应为 R-P1.1 产出（build_zh_med.py）。用 --data 指定实际路径。"
        )
    df = pd.read_csv(data_path, encoding="utf-8")
    required = {"evidence", "question", "gt_answer", "hallu_answer"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"[k3] pilot 数据缺字段 {missing}；实际列={list(df.columns)}。"
        )
    return df


def build_balanced_testset(df: pd.DataFrame) -> pd.DataFrame:
    """
    每条 pilot 派生两条平衡测试样本（context 均为 evidence，question 均为 question）：
      - faithful  : answer=gt_answer,    y_true=0
      - unfaithful: answer=hallu_answer, y_true=1
    → N=2*len(df)（14 条 pilot -> 28 条测试；14 正 14 负，天然平衡）。
    保留 pilot 溯源列（hid/type_name）供逐条人工核。
    """
    rows = []
    for _, r in df.iterrows():
        base = dict(
            hid=r.get("hid"),
            type_name=r.get("type_name"),
            evidence=str(r["evidence"]),
            question=str(r["question"]),
        )
        rows.append({**base, "variant": "faithful",
                     "answer": str(r["gt_answer"]), "y_true": FAITHFUL})
        rows.append({**base, "variant": "unfaithful",
                     "answer": str(r["hallu_answer"]), "y_true": UNFAITHFUL})
    return pd.DataFrame(rows).reset_index(drop=True)


# ============================================================================
# 检测器：LettuceDetect 多语版（独立臂）
# ============================================================================
def load_detector(model_path: str, device: str | None):
    """
    加载 LettuceDetect 多语版。import 用法逐字对齐 pilot killshot_psiloqa.run_lettucedetect：
      from lettucedetect.models.inference import HallucinationDetector
      HallucinationDetector(method="transformer", model_path=<多语版>)
    device：LettuceDetect 内部按 transformers 自动放置；此处仅打印提示（其构造函数不同版本
    是否接受 device 参数不一，不强传，避免版本报错）。
    """
    try:
        from lettucedetect.models.inference import HallucinationDetector
    except ImportError as e:
        raise ImportError(
            "[k3] 未安装 lettucedetect。装：pip install lettucedetect\n"
            f"  （首次跑会自动从 HF 下载 {model_path} 权重，约 0.5GB，需联网）"
        ) from e
    print(f"[k3] loading LettuceDetect(multilingual) model_path={model_path} "
          f"(device 由 transformers 自动放置; 提示 device={device})", flush=True)
    detector = HallucinationDetector(method="transformer", model_path=model_path)
    return detector


def predict_one(detector, context: str, question: str, answer: str) -> int:
    """
    对单条 (context, question, answer) 判有无 hallucinated span：
      有 span -> unfaithful(1)，无 span -> faithful(0)。
    LettuceDetect 是 context-question-answer 三段式（brief §2）；context 需传 list。
    出异常保守判 unfaithful(1)（与 pilot 一致），并向上抛出计数用的标记。
    """
    spans = detector.predict(
        context=[str(context)],
        question=str(question),
        answer=str(answer),
        output_format="spans",
    )
    return UNFAITHFUL if spans else FAITHFUL


def run_detector(detector, test_df: pd.DataFrame) -> tuple[np.ndarray, int]:
    """逐条推理，返回 (preds[N], n_errors)。异常条保守判 unfaithful 并计数。"""
    n = len(test_df)
    preds = np.empty(n, dtype=int)
    n_errors = 0
    for i, row in test_df.reset_index(drop=True).iterrows():
        try:
            preds[i] = predict_one(detector, row["evidence"], row["question"], row["answer"])
        except Exception as e:  # noqa: BLE001  单条容错，不拖垮整轮；记数供人工看
            n_errors += 1
            preds[i] = UNFAITHFUL  # 保守
            print(f"[k3][warn] 第 {i} 条推理异常({type(e).__name__}: {e})，保守判 unfaithful。",
                  flush=True)
        if (i + 1) % 10 == 0:
            print(f"[k3] {i + 1}/{n} 条完成", flush=True)
    print(f"[k3] 全部 {n} 条完成（异常 {n_errors} 条）", flush=True)
    return preds, n_errors


# ============================================================================
# 检测器：LLM-judge 后端（GLM-4-9B via 硅基流动，独立臂，🆕 默认）
#   复用 build_zh_med.OpenAICompatBackend（不重写 API 逻辑）；evidence-conditioned 判定。
# ============================================================================
def load_judge_backend(judge_model: str, base_url: str, key_env: str, counter: dict):
    """
    加载 judge 后端 = build_zh_med.OpenAICompatBackend（OpenAI 兼容，硅基流动端点）。
    key 从环境变量 key_env 读（OpenAICompatBackend 内部处理，缺 key 会给清晰报错）。
    counter：成本计数 dict（api_calls/api_failures/api_giveup/api_max_calls），达上限硬停。
    """
    try:
        from build_zh_med import OpenAICompatBackend  # 复用同目录构造脚本的 API 后端，不重写
    except ImportError as e:
        raise ImportError(
            "[k3] 无法从 build_zh_med 导入 OpenAICompatBackend（应与本脚本同在 code/ 下）。\n"
            f"  也需安装 openai SDK：pip install openai。原始错误：{e}"
        ) from e
    print(f"[k3] loading LLM-judge backend model={judge_model} base_url={base_url} "
          f"key_env={key_env}（独立于构造管线）", flush=True)
    return OpenAICompatBackend(judge_model, base_url=base_url, api_key_env=key_env,
                               counter=counter)


def _parse_judge_output(raw: str):
    """
    解析 judge 原始输出 → (y_pred[0/1], is_uncertain[bool])。
      找输出里第一个 0/1/2 数字：
        0 → faithful(0)   1 → unfaithful(1)
        2 → 不确定：保守归 faithful(0)（UNCERTAIN_FALLBACK），is_uncertain=True，raw 单列记原文。
      空串 / 无法解析 → 也保守归 faithful(0) 并标 is_uncertain=True（judge 未给有效判定）。
    """
    m = re.search(r"[012]", str(raw))
    if m is None:
        return UNCERTAIN_FALLBACK, True          # judge 没给有效数字，保守 + 标注
    v = m.group(0)
    if v == "2":
        return UNCERTAIN_FALLBACK, True
    return (FAITHFUL if v == "0" else UNFAITHFUL), False


def run_judge(backend, test_df: pd.DataFrame, temperature: float, smoke: bool):
    """
    逐条 judge：构造 evidence-conditioned prompt → 判 0/1/2 → 解析成 pred。
    返回 (preds[N], judge_raws[N], n_uncertain, n_api_calls)。
    smoke=True：不调 API，按 variant 理想化 mock（faithful→"0" / unfaithful→"1"）验管线。
    异常（backend 已内部 retry+兜底返回空串）不额外崩；空串经 _parse_judge_output 保守归 faithful。
    """
    n = len(test_df)
    preds = np.empty(n, dtype=int)
    judge_raws = [""] * n
    n_uncertain = 0
    n_api_calls = 0
    for i, row in test_df.reset_index(drop=True).iterrows():
        prompt = JUDGE_PROMPT_ZH.format(
            question=str(row["question"]),
            evidence=str(row["evidence"]),
            answer=str(row["answer"]),
        )
        if smoke:
            # mock：不真调 API，理想化返回（验管线不破，非真实结果）
            raw = "0" if row["variant"] == "faithful" else "1"
        else:
            raw = backend.generate_batch([prompt], temperature=temperature)[0]
            n_api_calls += 1
        pred, is_unc = _parse_judge_output(raw)
        preds[i] = pred
        judge_raws[i] = raw
        if is_unc:
            n_uncertain += 1
        if (i + 1) % 10 == 0:
            print(f"[k3][judge] {i + 1}/{n} 条完成", flush=True)
    print(f"[k3][judge] 全部 {n} 条完成（不确定/无效判定 {n_uncertain} 条，"
          f"API 调用 {n_api_calls} 次）", flush=True)
    return preds, judge_raws, n_uncertain, n_api_calls


# ============================================================================
# 指标（纯 numpy 自算，口径对齐 eval_harness：BA + Macro-F1 + 混淆矩阵 + 逐类 recall）
# ============================================================================
def confusion_2x2(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """
    2x2 混淆矩阵（正类=unfaithful=1）：
      tn=真faithful判faithful, fp=真faithful判unfaithful,
      fn=真unfaithful判faithful, tp=真unfaithful判unfaithful。
    """
    y_true = np.asarray(y_true); y_pred = np.asarray(y_pred)
    tn = int(np.sum((y_true == FAITHFUL) & (y_pred == FAITHFUL)))
    fp = int(np.sum((y_true == FAITHFUL) & (y_pred == UNFAITHFUL)))
    fn = int(np.sum((y_true == UNFAITHFUL) & (y_pred == FAITHFUL)))
    tp = int(np.sum((y_true == UNFAITHFUL) & (y_pred == UNFAITHFUL)))
    return dict(tn=tn, fp=fp, fn=fn, tp=tp)


def _safe_div(a: float, b: float) -> float:
    """零分母返回 nan（供 recall/precision 退化处理，与 sklearn zero_division 精神一致）。"""
    return float(a) / float(b) if b else float("nan")


def balanced_accuracy(cm: dict) -> tuple[float, float, float]:
    """
    Balanced Accuracy = (recall_faithful + recall_unfaithful) / 2。
    返回 (BA, recall_faithful, recall_unfaithful)。某类无样本时该 recall=nan，
    BA 用 nanmean（只对有样本的类平均），退化情形不污染。
    """
    recall_faithful = _safe_div(cm["tn"], cm["tn"] + cm["fp"])      # 真 faithful 中判对比例
    recall_unfaithful = _safe_div(cm["tp"], cm["tp"] + cm["fn"])    # 真 unfaithful 中判对比例
    ba = float(np.nanmean([recall_faithful, recall_unfaithful]))
    return ba, recall_faithful, recall_unfaithful


def macro_f1(cm: dict) -> tuple[float, float, float]:
    """
    两类 Macro-F1（zero_division=0 语义：分母为 0 时该项 F1 记 0）。
    class faithful(0)：precision=tn/(tn+fn), recall=tn/(tn+fp)
    class unfaithful(1)：precision=tp/(tp+fp), recall=tp/(tp+fn)
    返回 (macro_f1, f1_faithful, f1_unfaithful)。
    """
    def _f1(tp_, fp_, fn_):
        p = tp_ / (tp_ + fp_) if (tp_ + fp_) else 0.0
        r = tp_ / (tp_ + fn_) if (tp_ + fn_) else 0.0
        return (2 * p * r / (p + r)) if (p + r) else 0.0

    f1_faithful = _f1(cm["tn"], cm["fn"], cm["fp"])     # faithful 视作正类时的 tp/fp/fn
    f1_unfaithful = _f1(cm["tp"], cm["fp"], cm["fn"])   # unfaithful 为正类
    return float((f1_faithful + f1_unfaithful) / 2.0), float(f1_faithful), float(f1_unfaithful)


# ============================================================================
# 输出
# ============================================================================
def write_per_case_csv(test_df: pd.DataFrame, preds: np.ndarray, outdir: Path) -> Path:
    """逐条 label/pred/对错 + 溯源，写 code/results/k3_probe.csv。"""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    out = test_df.copy()
    out["y_pred"] = preds
    out["correct"] = (out["y_true"].to_numpy() == preds).astype(int)
    # 只留人工核需要的列（不写整段 evidence，避免 csv 过肥；answer 留短判据）
    cols = ["hid", "type_name", "variant", "question", "answer", "y_true", "y_pred", "correct"]
    cols = [c for c in cols if c in out.columns]
    path = outdir / "k3_probe.csv"
    out[cols].to_csv(path, index=False, encoding="utf-8")
    return path


def write_per_case_csv_judge(test_df: pd.DataFrame, preds: np.ndarray,
                             judge_raws, outdir: Path) -> Path:
    """
    judge 后端逐条：hid/type_name/variant/question/answer/y_true/y_pred/judge_raw/correct，
    写 code/results/k3_probe_judge.csv（judge_raw 留 GLM-4 原始输出供人工核判定）。
    """
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    out = test_df.copy()
    out["y_pred"] = preds
    out["judge_raw"] = [str(r).replace("\n", " ").strip() for r in judge_raws]
    out["correct"] = (out["y_true"].to_numpy() == preds).astype(int)
    cols = ["hid", "type_name", "variant", "question", "answer",
            "y_true", "y_pred", "judge_raw", "correct"]
    cols = [c for c in cols if c in out.columns]
    path = outdir / "k3_probe_judge.csv"
    out[cols].to_csv(path, index=False, encoding="utf-8")
    return path


def write_judge_state(outdir: Path, cm: dict, ba: float, rec_f: float, rec_u: float,
                      mf1: float, n: int, n_uncertain: int, counter: dict,
                      judge_model: str, base_url: str) -> Path:
    """
    judge 运行 state → code/results/k3_probe_judge_state.json：API 调用数 + 指标快照
    + 不确定条数 + 后端信息（供复盘/成本核对）。
    """
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    state = {
        "note": "CMedFaith K3 初验 P1 粗信号（28 条），非 P3 正式评测；judge=GLM-4 独立臂",
        "detector": "llm-judge",
        "judge_model": judge_model,
        "base_url": base_url,
        "n_samples": int(n),
        "api_calls": int(counter.get("api_calls", 0)),
        "api_failures": int(counter.get("api_failures", 0)),
        "api_giveup": int(counter.get("api_giveup", 0)),
        "n_uncertain_or_invalid": int(n_uncertain),
        "confusion_matrix": cm,
        "balanced_accuracy": None if np.isnan(ba) else float(ba),
        "recall_faithful": None if np.isnan(rec_f) else float(rec_f),
        "recall_unfaithful": None if np.isnan(rec_u) else float(rec_u),
        "macro_f1": float(mf1),
    }
    path = outdir / "k3_probe_judge_state.json"
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def print_summary(cm: dict, ba: float, rec_f: float, rec_u: float,
                  mf1: float, f1_f: float, f1_u: float, n: int, n_errors: int,
                  model_path: str, detector_label: str = "LettuceDetect 多语版"):
    print("\n" + "=" * 72)
    print(f"CMedFaith K3 初验（P1 粗信号，非 P3 正式评测）—— {detector_label}")
    print("-" * 72)
    print(f"检测器（独立于构造管线）: {model_path}")
    print(f"测试集: N={n}（14 pilot × 2 = faithful/unfaithful 平衡）；异常/不确定={n_errors} 条")
    print("-" * 72)
    print("混淆矩阵（正类=unfaithful=1）:")
    print(f"                    pred_faithful   pred_unfaithful")
    print(f"  true_faithful  :      {cm['tn']:>4}            {cm['fp']:>4}")
    print(f"  true_unfaithful:      {cm['fn']:>4}            {cm['tp']:>4}")
    print("-" * 72)
    print(f"  recall_faithful   (真faithful判对比例)  = {rec_f:.4f}")
    print(f"  recall_unfaithful (真unfaithful抓出比例)= {rec_u:.4f}")
    print(f"  Balanced Accuracy                       = {ba:.4f}")
    print(f"  Macro-F1                                = {mf1:.4f}  "
          f"(F1_faithful={f1_f:.4f}, F1_unfaithful={f1_u:.4f})")
    print("=" * 72)
    # 结论提示（不下定论，只给方向 + 警惕点）
    print("结论提示（⚠️ 28 条粗信号，方向性参考，正式结论等 P3）:")
    if not np.isnan(ba) and ba <= 0.6:
        print(f"  → BA 偏低(≤0.6)：{detector_label} 在中文医学上基本抓不住我们造的幻觉，")
        print("    初步支持核心 claim「现成检测器中文医学弱」→ 值得上 P3 全套横评。")
    elif not np.isnan(ba) and ba >= 0.8:
        print("  → BA 偏高(≥0.8)：⚠️ 警惕两种可能——① 我们造的对抗幻觉太明显(构造强度不够,")
        print("    回看 Phase2 筛子)；② 该检测器对中文医学不弱(削弱 claim)。停下人工看逐条。")
    else:
        print("  → BA 居中(0.6~0.8)：信号不明朗，样本太小；人工看逐条 + 扩样再判，别下结论。")
    print(f"  recall_unfaithful 尤其关键：它=检测器抓出幻觉的比例，越低越支持'失效'。")
    print("=" * 72)


# ============================================================================
# main
# ============================================================================
def main():
    ap = argparse.ArgumentParser(
        description="CMedFaith K3 初验：独立检测器测中文医学 faithfulness（P1 粗信号）")
    ap.add_argument("--detector", choices=["judge", "lettuce"], default="judge",
                    help="检测后端：judge=GLM-4 LLM-judge（默认，走 API 不占 GPU）；"
                         "lettuce=LettuceDetect 多语版（当前 transformers 版本地狱跑不了）")
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA,
                    help=f"中文医学 pilot csv（默认 {DEFAULT_DATA}）")
    ap.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR,
                    help=f"输出目录（默认 {DEFAULT_OUTDIR}）")
    # --- lettuce 后端参数 ---
    ap.add_argument("--model-path", default=DEFAULT_MODEL_PATH,
                    help=f"[lettuce] LettuceDetect 多语版 HF id（默认 {DEFAULT_MODEL_PATH}；"
                         "🔴 别填英文版 lettucedect-*-modernbert-en）")
    ap.add_argument("--device", default=None, help="[lettuce] cuda/cpu 提示（transformers 自动放置）")
    # --- judge 后端参数 ---
    ap.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL,
                    help=f"[judge] 独立 judge model id（默认 {DEFAULT_JUDGE_MODEL}，硅基流动 GLM-4-9B）。"
                         "🔴 独立性：勿填构造管线用过的模型（DeepSeek/Qwen/mDeBERTa）")
    ap.add_argument("--judge-base-url", default=DEFAULT_JUDGE_BASE_URL,
                    help=f"[judge] OpenAI 兼容端点（默认 {DEFAULT_JUDGE_BASE_URL}）")
    ap.add_argument("--judge-key-env", default=DEFAULT_JUDGE_KEY_ENV,
                    help=f"[judge] 读哪个环境变量取 key（默认 {DEFAULT_JUDGE_KEY_ENV}；key 不硬编码）")
    ap.add_argument("--judge-temperature", type=float, default=DEFAULT_JUDGE_TEMPERATURE,
                    help=f"[judge] 判定温度（默认 {DEFAULT_JUDGE_TEMPERATURE}，低温求稳定）")
    ap.add_argument("--api-max-calls", type=int, default=JUDGE_API_MAX_CALLS,
                    help=f"[judge] API 调用上限（成本保护，默认 {JUDGE_API_MAX_CALLS}；达上限硬停）")
    ap.add_argument("--smoke", type=int, default=0,
                    help="冒烟：只取前 N 条 pilot（每条派生 2 测试样本）验管线；judge 后端 smoke 不调 API（mock）")
    args = ap.parse_args()

    smoke = bool(args.smoke and args.smoke > 0)

    # 数据 → 平衡测试集
    df = load_pilot(args.data)
    if smoke:
        df = df.head(args.smoke).reset_index(drop=True)
        print(f"[smoke] 冒烟模式：只取前 {len(df)} 条 pilot（{2*len(df)} 测试样本），验管线非正式结果。",
              flush=True)
    test_df = build_balanced_testset(df)
    n = len(test_df)
    n_pos = int((test_df["y_true"] == UNFAITHFUL).sum())
    n_neg = int((test_df["y_true"] == FAITHFUL).sum())
    print(f"[k3] 检测后端={args.detector}；测试集: N={n}（faithful={n_neg}, unfaithful={n_pos}）"
          f"来自 {len(df)} 条 pilot", flush=True)

    y_true = test_df["y_true"].to_numpy()

    if args.detector == "judge":
        # LLM-judge 后端（GLM-4，独立于构造管线）
        detector_label = f"LLM-judge（{args.judge_model}）"
        counter = {"api_calls": 0, "api_failures": 0, "api_giveup": 0,
                   "api_max_calls": args.api_max_calls}
        backend = None
        if not smoke:
            backend = load_judge_backend(args.judge_model, args.judge_base_url,
                                         args.judge_key_env, counter)
        else:
            print("[smoke] judge 后端 mock：不调 API（faithful→0/unfaithful→1 理想化），验管线不破。",
                  flush=True)
        preds, judge_raws, n_uncertain, n_api_calls = run_judge(
            backend, test_df, args.judge_temperature, smoke)

        cm = confusion_2x2(y_true, preds)
        ba, rec_f, rec_u = balanced_accuracy(cm)
        mf1, f1_f, f1_u = macro_f1(cm)

        csv_path = write_per_case_csv_judge(test_df, preds, judge_raws, args.outdir)
        state_path = write_judge_state(args.outdir, cm, ba, rec_f, rec_u, mf1, n,
                                       n_uncertain, counter, args.judge_model,
                                       args.judge_base_url)
        print_summary(cm, ba, rec_f, rec_u, mf1, f1_f, f1_u, n, n_uncertain,
                      args.judge_model, detector_label=detector_label)
        print(f"\n[out] 逐条对错+judge原文: {csv_path}")
        print(f"[out] 运行 state（API 调用数等）: {state_path}")
        if not smoke:
            print(f"[cost] 本轮 API 调用 {counter.get('api_calls', 0)} 次"
                  f"（失败重试 {counter.get('api_failures', 0)}、放弃 {counter.get('api_giveup', 0)}）",
                  flush=True)
    else:
        # LettuceDetect 后端（当前版本地狱跑不了；环境修好后可用）
        detector = load_detector(args.model_path, args.device)
        preds, n_errors = run_detector(detector, test_df)

        cm = confusion_2x2(y_true, preds)
        ba, rec_f, rec_u = balanced_accuracy(cm)
        mf1, f1_f, f1_u = macro_f1(cm)

        csv_path = write_per_case_csv(test_df, preds, args.outdir)
        print_summary(cm, ba, rec_f, rec_u, mf1, f1_f, f1_u, n, n_errors, args.model_path)
        print(f"\n[out] 逐条对错: {csv_path}")


if __name__ == "__main__":
    main()
