#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
eval_harness.py — CMedFaith 统一评测 harness（R-P1.0 英文对照复现 + 评测骨架）
================================================================================
服务：CMedFaith / PLAN §A.2 R-P1.0（英文对照 pipeline，无依赖最先跑）。
lever：L2-a 基线管线 + L2-b 三级评测口径（response 主，claim/span 独立不混）。

这个脚本干两件事
--------------------------------------------------
1) **复现 pilot 冻结值**（KILLSHOT_LEDGER #2，Bash 已核）：
     - MedHallu pqa_labeled（医学）  macro-F1 ≈ 0.4277   (n_faith=1000, n_unfaith=1000)
     - PsiloQA-en（通用，平衡下采样） macro-F1 ≈ 0.7204   (n_faith=39,  n_unfaith=39)
     - G_domain = F1(gen) − F1(med) ≈ +0.2927，非配对 bootstrap 95%CI ≈ [0.1844, 0.3912]
   为保证**零偏离**，数据加载 + NLI 标签逻辑**直接复用** _scratch 里冻结的 pilot 脚本
   （killshot_psiloqa.py / killshot_med_vs_general.py），不重造。跑 `--selfcheck` 会额外
   调用 pilot 的 run_mdeberta 断言本 harness 的硬标签与之逐条相等（证明零偏离，可核）。

2) **搭三级评测骨架**（PLAN §E 精密规范）：
     - response 级：已实现（本轮唯一能跑通复现的级别）。
     - claim / span 级：留接口 stub + TODO（各自独立 csv，绝不与 response 混报，L2-b 铁律）。
   指标：主 = Balanced Accuracy + Macro-F1；辅 = MCC + AUPRC/AUROC。
     - 点估计 CI = **bootstrap 95%CI，默认 10000 resamples**（对 test cases 有放回重采，
       每 replicate 重算指标）。
     - 配对检验 = **paired bootstrap（差值 CI，用于 BA/F1）** + **McNemar（仅 accuracy）**。
       （§E 🔴 铁律：F1/BA 禁用 McNemar，必须 paired bootstrap。）
     - 多检测器校正 = **Holm-Bonferroni（FWER）**，自实现（不引 scipy/statsmodels，避 OMP 冲突）。
   输出统一 csv 到 code/results/。

检测器接口
--------------------------------------------------
抽象成 Detector.detect(evidence, answer) -> (label, score) / .run_batch(df) -> (labels, scores)。
本轮只接 **D1 = mDeBERTa-v3-XNLI**（复用 pilot 冻结 NLI 设置）。D2–D15 留注册表 stub + TODO
（见 STUB_DETECTORS / PLAN §A.0），本轮不实现，跑不到它们。

================================================================================
⚠️ 主线跑前必须确认的事项（TODO / 盲区，coder 不臆想不代跑）
================================================================================
[T1] 依赖包：datasets, transformers, torch, pandas, pyarrow, numpy, scikit-learn, huggingface_hub。
     （bootstrap/Holm/McNemar 全 numpy 自实现，不需 scipy/statsmodels——避与 torch 抢 OpenMP。）
[T2] PsiloQA parquet 路径：.portfolio/datasets.json 的 datasets.psiloqa.local 只写了
     "session scratchpad psiloqa_all.parquet（临时）"，**没有稳定磁盘路径**。本脚本会：
       (a) 读 datasets.json 确认数据集登记存在；
       (b) 在常见 temp/claude scratchpad 下 glob 找 psiloqa_all.parquet；
       (c) 找不到 → 报错并要求主线传 `--psiloqa-data <path>`（或从 HF s-nlp/PsiloQA 重下，
           重下代码见 killshot_psiloqa.load_psiloqa 的报错提示）。
     → **主线跑前请确认 psiloqa_all.parquet 的真实路径**，必要时用 --psiloqa-data 指定。
[T3] MedHallu：走 HF datasets 自动下（repo UTAustin-AIHealth/MedHallu, config pqa_labeled, MIT）。
     首次跑需联网 + HF 缓存；离线机需先 `datasets` 缓存好。
[T4] 模型 id 不一致（**需 researcher/主线拍板**）：PLAN §A.0 表里 D1 写的是
     `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`，但 pilot 冻结值 0.43/0.72
     是用 `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` 跑出来的。**要复现冻结值必须用后者**
     （本脚本默认 = 后者 = pilot 模型）。若正式横评要换成 2mil7 版，冻结值会变，需重新冻结，
     这是判据变动=拍板点，coder 不擅改。用 --model-id 可覆盖（覆盖后不再保证复现 0.43/0.72）。
[T5] _scratch 依赖：本脚本 import 了 _scratch/killshot_psiloqa.py + killshot_med_vs_general.py
     （pilot 冻结脚本）。_scratch 是 gitignored 临时区；若被清扫/归档，import 会失败并给清晰报错。
     R-P1.0 的定位就是复现这两个脚本，故 import 它们=最强零偏离保证。若 _scratch 缺，
     把这两个 .py 拷进 code/ 或恢复即可（报错里也写了）。
[T6] 预期复现值（跑完对照，verifier 核 code/results/results_response.csv 与 state.json）：
       medhallu_medical  macro_f1 ≈ 0.4277
       psiloqa_en_general macro_f1 ≈ 0.7204
       G_domain (gen−med) ≈ 0.2927, CI ≈ [0.1844, 0.3912]
     其余指标（BA/MCC/AUPRC/AUROC）是本 harness 新增，pilot 没冻结值，不作复现对照。

主线跑法（coder 不跑，只交付）
--------------------------------------------------
  # 冒烟（小样本 + 少量 bootstrap，先验管线通，占 0 卡登记或 local 短跑）
  python eval_harness.py --smoke
  # 正式复现（默认 10000 bootstrap；PsiloQA 路径按 T2 确认）
  python eval_harness.py --psiloqa-data <路径/psiloqa_all.parquet>
  # 证明与 pilot 零偏离（额外跑 pilot run_mdeberta 断言硬标签逐条相等）
  python eval_harness.py --psiloqa-data <...> --selfcheck
  # 起 GPU 走卡槽：python tools/gpu_slot.py request cmedfaith local 1（或 hpc 1）后再跑

红线遵守
--------------------------------------------------
- 复现零偏离：NLI 标签逻辑/阈值/映射全用 pilot 冻结实现，未私改凑数（--selfcheck 可证）。
- 评估集不泄漏：MedHallu 医学 vs PsiloQA 通用**两独立 slice，绝不 concat**，各自独立评测。
- 超参查不到标 TODO：见 [T4] 模型 id、STUB_DETECTORS 里 D2–D15 的 license/model TODO。
- 三级不混报：response/claim/span 各写独立 csv（results_response/claim/span.csv），列不混。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# 复用 _scratch 的 pilot 冻结实现（零偏离的最强保证）。code/ 与 _scratch/ 同在
# CMedFaith/ 下：code/eval_harness.py -> parent.parent = CMedFaith/，再进 _scratch/。
# ----------------------------------------------------------------------------
HARNESS_DIR = Path(__file__).resolve().parent          # .../CMedFaith/code
PROJECT_DIR = HARNESS_DIR.parent                        # .../CMedFaith
SCRATCH_DIR = PROJECT_DIR / "_scratch"                  # .../CMedFaith/_scratch
REPO_ROOT = PROJECT_DIR.parents[2]                      # .../YJ-Agent（meeting/CMedFaith 上三层）
DATASETS_JSON = REPO_ROOT / ".portfolio" / "datasets.json"

sys.path.insert(0, str(SCRATCH_DIR))
try:
    # 从 pilot 直接借：数据加载 + NLI 标签 + 指标 + 非配对 bootstrap（全冻结口径）
    from killshot_psiloqa import (  # noqa: E402
        macro_f1,                    # 两类 macro-F1（zero_division=0）
        run_mdeberta,                # 冻结 NLI 承重臂（仅 --selfcheck 用它做零偏离断言）
        bootstrap_g_ci,              # 非配对 bootstrap（复现 G_domain 冻结 CI 用，5000/seed42）
        FAITHFUL, UNFAITHFUL,        # 0 / 1
        BOOTSTRAP_N as PILOT_BOOTSTRAP_N,   # 5000（复现 G_domain CI 用这个 n 才对得上冻结值）
    )
    from killshot_med_vs_general import (  # noqa: E402
        load_medhallu,               # MedHallu -> 平衡二分类样本（wiki_passage/llm_answer/y_true）
        load_psiloqa_en_balanced,    # PsiloQA-en test -> 平衡下采样（seed 42）
        DOWNSAMPLE_SEED,             # 42
    )
except ImportError as e:  # noqa: BLE001
    raise ImportError(
        f"[eval_harness] 无法从 _scratch import pilot 冻结脚本：{e}\n"
        f"  期望位置：{SCRATCH_DIR}/killshot_psiloqa.py + killshot_med_vs_general.py\n"
        "  R-P1.0 复现依赖这两个 pilot 脚本（零偏离）。若 _scratch 被清扫/归档，请把这两个 .py\n"
        "  拷回 code/（或恢复 _scratch），再跑。[T5]"
    ) from e

# 复现锚点（KILLSHOT_LEDGER #2，Bash 已核；仅用于跑完打印对照，不参与计算，不许为凑数改）
FROZEN_MED_MACRO_F1 = 0.4277
FROZEN_GEN_MACRO_F1 = 0.7204
FROZEN_G_DOMAIN = 0.2927
FROZEN_G_DOMAIN_CI = (0.1844, 0.3912)

# 模型 id：默认 = pilot 冻结模型（复现 0.43/0.72 必须用它）。见 [T4]。
MDEBERTA_MODEL_ID = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"

# 冻结 NLI 阈值（pilot run_mdeberta 默认）：entail prob >= 阈值 -> faithful(0)。不许为凑数改。
NLI_THRESHOLD = 0.5

# 评测协议默认（PLAN §E）
DEFAULT_N_BOOTSTRAP = 10000
CI_LOW_Q, CI_HIGH_Q = 2.5, 97.5

# response 级指标集（主 + 辅，§E）。macro_f1 复用 pilot 实现，其余 sklearn。
# 标签类指标（从硬标签算）与分数类指标（从连续 unfaithfulness score 算）分开。
LABEL_METRICS = ["balanced_accuracy", "macro_f1", "mcc", "accuracy"]
SCORE_METRICS = ["auroc", "auprc"]
RESPONSE_METRICS = LABEL_METRICS + SCORE_METRICS

# 数据切片（**两独立集，绝不 concat**）：medical=MedHallu / general=PsiloQA-en
SLICE_MEDICAL = "medhallu_medical"
SLICE_GENERAL = "psiloqa_en_general"


# ============================================================================
# 数据路径解析（读 .portfolio/datasets.json，取不到给 TODO，不硬编码，[T2]）
# ============================================================================
def read_datasets_registry() -> dict:
    """读 datasets.json（跨论文数据集真源）。读不到给清晰提示，不 crash 主流程。"""
    if not DATASETS_JSON.exists():
        print(f"[data] 警告：找不到 {DATASETS_JSON}，跳过登记核对（用 --psiloqa-data 指定路径）。",
              flush=True)
        return {}
    with open(DATASETS_JSON, "r", encoding="utf-8") as f:
        reg = json.load(f)
    ds = reg.get("datasets", {})
    for key in ("psiloqa", "medhallu"):
        if key in ds:
            print(f"[data] datasets.json 登记 {key}: status={ds[key].get('status')} "
                  f"license={ds[key].get('license')}", flush=True)
        else:
            print(f"[data] 警告：datasets.json 无 {key} 登记项。", flush=True)
    return reg


def resolve_psiloqa_parquet(cli_path: Path | None) -> Path:
    """
    解析 PsiloQA parquet 路径。优先级：
      1. --psiloqa-data 显式指定（推荐，[T2]）；
      2. datasets.json 无稳定磁盘路径 -> 在常见 temp/claude scratchpad 下 glob psiloqa_all.parquet；
      3. pilot killshot_psiloqa.DEFAULT_DATA（可能是过期 session 路径）；
      4. 全找不到 -> 抛错并要求主线 --psiloqa-data。
    """
    if cli_path is not None:
        p = Path(cli_path)
        if not p.exists():
            raise FileNotFoundError(f"[data] --psiloqa-data 指定的路径不存在：{p}")
        return p

    candidates: list[Path] = []
    # glob 常见 claude scratchpad（各 session 目录名是 uuid，故通配）
    temp_claude = Path.home() / "AppData" / "Local" / "Temp" / "claude"
    if temp_claude.exists():
        candidates += sorted(temp_claude.glob("**/psiloqa_all.parquet"))
    # pilot 默认路径兜底
    try:
        from killshot_psiloqa import DEFAULT_DATA as PILOT_PSILOQA
        candidates.append(Path(PILOT_PSILOQA))
    except Exception:  # noqa: BLE001
        pass

    for c in candidates:
        if c.exists():
            print(f"[data] 解析到 PsiloQA parquet: {c}", flush=True)
            return c

    raise FileNotFoundError(
        "[data] 找不到 psiloqa_all.parquet（datasets.json 只登记了 session scratchpad 临时路径，"
        "无稳定磁盘路径）。[T2]\n"
        "  → 主线请用 --psiloqa-data <路径> 指定，或从 HF s-nlp/PsiloQA 重下"
        "（重下代码见 _scratch/killshot_psiloqa.load_psiloqa 的报错提示）。\n"
        f"  已尝试的候选：{[str(c) for c in candidates] or '（无）'}"
    )


def load_slices(psiloqa_path: Path, include_artificial: bool, medhallu_cache: Path | None,
                limit: int | None) -> dict:
    """
    加载两独立切片（复用 pilot 冻结加载器，零偏离）：
      SLICE_MEDICAL  = MedHallu pqa_labeled 平衡二分类
      SLICE_GENERAL  = PsiloQA-en test 平衡下采样（seed 42）
    **两者各自独立 DataFrame，绝不 concat**（评估集不泄漏红线）。
    列统一 wiki_passage(证据) / llm_answer(答案) / y_true(0/1)。
    """
    df_med = load_medhallu(include_artificial, medhallu_cache, limit)
    df_gen = load_psiloqa_en_balanced(psiloqa_path, limit, seed=DOWNSAMPLE_SEED)
    slices = {SLICE_MEDICAL: df_med, SLICE_GENERAL: df_gen}
    for name, sub in slices.items():
        n = len(sub)
        nf = int((sub["y_true"] == FAITHFUL).sum())
        nu = int((sub["y_true"] == UNFAITHFUL).sum())
        print(f"[data] slice={name}: n={n} (faithful={nf}, unfaithful={nu})", flush=True)
    return slices


# ============================================================================
# 检测器接口（统一 detect(evidence, answer) -> (label, score)）
# ============================================================================
class Detector(ABC):
    """
    统一检测器接口。约定：
      - label: 0=faithful / 1=unfaithful（正类=unfaithful，与 pilot 一致）。
      - score: 连续 **unfaithfulness 分数**（越大越可能 unfaithful），供 AUROC/AUPRC；
               无分数的检测器返回 None，则该检测器 AUROC/AUPRC 记 NaN。
    """
    detector_id: str = "BASE"
    family: str = "?"

    @abstractmethod
    def run_batch(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray | None]:
        """批量：df 需含 wiki_passage/llm_answer 列 -> (labels[N], scores[N] 或 None)。"""
        raise NotImplementedError

    def detect(self, evidence: str, answer: str) -> tuple[int, float | None]:
        """单条：包一层 run_batch。"""
        one = pd.DataFrame([{"wiki_passage": evidence, "llm_answer": answer}])
        labels, scores = self.run_batch(one)
        return int(labels[0]), (None if scores is None else float(scores[0]))


class D1MDeBERTaXNLI(Detector):
    """
    D1 — mDeBERTa-v3-XNLI 承重 NLI 臂（复用 pilot 冻结设置，零偏离）。
      premise=wiki_passage(证据), hypothesis=llm_answer(答案)。
      entail 概率 >= NLI_THRESHOLD -> faithful(0)，否则 unfaithful(1)（= pilot run_mdeberta 逐字规则）。
      unfaithfulness score = 1 - entail_prob（仅供 AUROC/AUPRC，不影响硬标签/复现值）。
    单次前向同时产 probs 与 labels（避免二次加载）；--selfcheck 会额外调 pilot run_mdeberta
    断言 labels 逐条相等，证明零偏离。
    """
    detector_id = "D1_mDeBERTa_XNLI"
    family = "A_NLI"

    def __init__(self, model_id: str = MDEBERTA_MODEL_ID, threshold: float = NLI_THRESHOLD,
                 batch_size: int = 16, device: str | None = None):
        self.model_id = model_id
        self.threshold = threshold
        self.batch_size = batch_size
        self.device = device or _auto_device()
        self._tok = None
        self._model = None
        self._entail_idx = None

    def _lazy_load(self):
        if self._model is not None:
            return
        import torch  # noqa: F401
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        print(f"[D1] loading {self.model_id} on {self.device} ...", flush=True)
        self._tok = AutoTokenizer.from_pretrained(self.model_id)
        self._model = AutoModelForSequenceClassification.from_pretrained(self.model_id)
        self._model.to(self.device).eval()
        # 动态取 entailment 下标（不硬编码，防不同版本 id2label 顺序不一）——与 pilot 同逻辑
        label2id = {k.lower(): v for k, v in self._model.config.label2id.items()}
        if "entailment" not in label2id:
            raise RuntimeError(
                f"[D1] 模型 config.label2id 无 'entailment'：{self._model.config.label2id}")
        self._entail_idx = label2id["entailment"]

    def run_batch(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray | None]:
        import torch
        self._lazy_load()
        premises = df["wiki_passage"].fillna("").astype(str).tolist()
        hyps = df["llm_answer"].fillna("").astype(str).tolist()
        probs = np.empty(len(df), dtype=float)
        for start in range(0, len(df), self.batch_size):
            bp = premises[start:start + self.batch_size]
            bh = hyps[start:start + self.batch_size]
            # 与 pilot run_mdeberta 逐字相同的 tokenization（longest_first / max_length=512 / padding）
            enc = self._tok(bp, bh, truncation="longest_first", max_length=512,
                            padding=True, return_tensors="pt").to(self.device)
            with torch.no_grad():
                logits = self._model(**enc).logits
            p = torch.softmax(logits, dim=-1)[:, self._entail_idx].cpu().numpy()
            probs[start:start + len(p)] = p
        # 硬标签 = pilot 逐字规则；unfaithfulness score = 1 - entail_prob
        labels = np.where(probs >= self.threshold, FAITHFUL, UNFAITHFUL).astype(int)
        scores = 1.0 - probs
        return labels, scores


# ---- 已实现检测器注册表（本轮只有 D1） ----
IMPLEMENTED_DETECTORS = {
    "D1_mDeBERTa_XNLI": D1MDeBERTaXNLI,
}

# ---- D2–D15 stub 注册表（本轮不实现，留 TODO；模型/license 见 PLAN §A.0）----
# 每项：family / model / license / todo。coder 不臆想超参，接的时候由 researcher 核官方源。
STUB_DETECTORS = {
    "D2_AlignScore":        dict(family="A_NLI",  model="yzha/AlignScore",
                                 license="TODO核", todo="英文迁移对照臂；许可待核"),
    "D3_SummaC":            dict(family="A_NLI",  model="github tingofurro/summac",
                                 license="Apache TODO核", todo="句×句 NLI 矩阵臂"),
    "D4_HHEM_2.1":          dict(family="A_NLI",  model="vectara/hallucination_evaluation_model",
                                 license="Apache-2.0", todo="英文迁移对照臂"),
    "D5_LettuceDetect_mmBERT": dict(family="B_span", model="KRLabsOrg/lettucedect-v2-mmbert-base",
                                 license="MIT", todo="唯一原生中文专用 + span 主臂（R-P3.3）"),
    "D6_LettuceDetect_EN":  dict(family="B_span", model="KRLabsOrg/lettucedect-base-modernbert-en-v1",
                                 license="MIT", todo="英->中迁移对照臂"),
    "D7_MiniCheck":         dict(family="B_span", model="lytang/MiniCheck-Flan-T5-Large",
                                 license="MIT", todo="事实核查 SOTA<1B 对照"),
    "D8_Lynx_8B":           dict(family="B_span", model="PatronusAI/Llama-3-Patronus-Lynx-8B-Instruct",
                                 license="CC-BY-NC 非商用", todo="含 PubmedQA 医学素材；HPC4090"),
    "D9_RefChecker":        dict(family="B_span", model="github amazon-science/RefChecker",
                                 license="Apache TODO核", todo="消融臂（非主 baseline）"),
    "D10_Qwen2.5_7B":       dict(family="C_judge", model="Qwen/Qwen2.5-7B-Instruct",
                                 license="Apache-2.0", todo="中文 judge 主力（K1 承重）；判 prompt 待 researcher"),
    "D11_GLM4_9B":          dict(family="C_judge", model="THUDM/glm-4-9b-chat",
                                 license="TODO核", todo="中文 judge 对照臂（inter-judge κ）"),
    "D12_InternLM2.5_7B":   dict(family="C_judge", model="internlm/internlm2_5-7b-chat",
                                 license="Apache TODO核", todo="中文 judge 对照臂"),
    "D13_Qwen2.5_72B":      dict(family="C_judge", model="Qwen/Qwen2.5-72B-Instruct",
                                 license="Qwen License", todo="强 judge 上界；HPC 多卡/量化"),
    "D14_GPT4o_DeepSeek":   dict(family="C_judge", model="API",
                                 license="商用/MIT", todo="API 参考臂（不作主结论，不可复现）"),
    "D15_CMedFaith_ft":     dict(family="D_finetune", model="finetune mDeBERTa/中文BERT",
                                 license="—", todo="族D 自训；finetune 官方超参待 researcher（红线6，不臆想）"),
}


def build_detectors(detector_ids: list[str], batch_size: int, device: str | None,
                    model_id: str) -> list[Detector]:
    """按 id 建检测器。stub 的 id 给清晰提示并跳过（本轮不实现，不臆想）。"""
    built = []
    for did in detector_ids:
        if did in IMPLEMENTED_DETECTORS:
            cls = IMPLEMENTED_DETECTORS[did]
            if cls is D1MDeBERTaXNLI:
                built.append(cls(model_id=model_id, batch_size=batch_size, device=device))
            else:
                built.append(cls())
        elif did in STUB_DETECTORS:
            info = STUB_DETECTORS[did]
            print(f"[detector] {did} 是 stub（未实现）：{info['todo']}；本轮跳过。", flush=True)
        else:
            print(f"[detector] 未知检测器 id：{did}，跳过。", flush=True)
    return built


def _auto_device() -> str:
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


# ============================================================================
# 指标（response 级）
# ============================================================================
def _single_metric(name: str, yt: np.ndarray, yp: np.ndarray,
                   ys: np.ndarray | None) -> float:
    """
    单指标点估计。标签类从 (yt, yp)，分数类从 (yt, ys)。
    退化情形（单类等）返回 NaN，让 bootstrap 里丢弃该 replicate、CI 不被污染。
    """
    from sklearn.metrics import (average_precision_score, balanced_accuracy_score,
                                 matthews_corrcoef, roc_auc_score)
    yt = np.asarray(yt)
    yp = np.asarray(yp)
    if len(yt) == 0:
        return float("nan")
    if name == "balanced_accuracy":
        return float(balanced_accuracy_score(yt, yp))
    if name == "macro_f1":
        return float(macro_f1(yt, yp))               # 复用 pilot（zero_division=0）
    if name == "accuracy":
        return float((yt == yp).mean())
    if name == "mcc":
        # 单类（真值或预测）时 MCC 无定义 -> NaN，避免误导
        if len(np.unique(yt)) < 2 or len(np.unique(yp)) < 2:
            return float("nan")
        return float(matthews_corrcoef(yt, yp))
    if name in ("auroc", "auprc"):
        if ys is None or len(np.unique(yt)) < 2:
            return float("nan")
        ys = np.asarray(ys)
        if name == "auroc":
            return float(roc_auc_score(yt, ys))       # 正类=unfaithful(1)，ys 越大越 unfaithful
        return float(average_precision_score(yt, ys))
    raise ValueError(f"未知指标：{name}")


def compute_metrics(yt: np.ndarray, yp: np.ndarray, ys: np.ndarray | None,
                    metric_names: list[str]) -> dict:
    return {m: _single_metric(m, yt, yp, ys) for m in metric_names}


def bootstrap_ci(yt: np.ndarray, yp: np.ndarray, ys: np.ndarray | None,
                 metric_names: list[str], n: int = DEFAULT_N_BOOTSTRAP,
                 seed: int = 42) -> dict:
    """
    对 test cases **有放回重采**（每 replicate 重算所有指标），percentile 95%CI。
    退化 replicate（某指标 NaN）在该指标上丢弃。返回 {metric: (ci_low, ci_high)}。
    §E：response 主口径的点估计 CI = bootstrap 95%CI，10000 resamples。
    """
    yt = np.asarray(yt); yp = np.asarray(yp)
    ys = None if ys is None else np.asarray(ys)
    N = len(yt)
    rng = np.random.default_rng(seed)
    buckets = {m: [] for m in metric_names}
    for _ in range(n):
        idx = rng.integers(0, N, N)
        yti, ypi = yt[idx], yp[idx]
        ysi = None if ys is None else ys[idx]
        for m in metric_names:
            v = _single_metric(m, yti, ypi, ysi)
            if not (v is None or (isinstance(v, float) and math.isnan(v))):
                buckets[m].append(v)
    out = {}
    for m in metric_names:
        arr = np.asarray(buckets[m], dtype=float)
        if arr.size == 0:
            out[m] = (float("nan"), float("nan"))
        else:
            lo, hi = np.percentile(arr, [CI_LOW_Q, CI_HIGH_Q])
            out[m] = (float(lo), float(hi))
    return out


# ============================================================================
# 配对检验（§E：BA/F1 用 paired bootstrap；仅 accuracy 用 McNemar）
# ============================================================================
def paired_bootstrap_diff(yt: np.ndarray, pred_a: np.ndarray, pred_b: np.ndarray,
                          metric_name: str, score_a: np.ndarray | None = None,
                          score_b: np.ndarray | None = None,
                          n: int = DEFAULT_N_BOOTSTRAP, seed: int = 42) -> dict:
    """
    配对 bootstrap 差值 CI（同一批 test cases，两检测器共用同一 resample 索引）。
    diff = metric(A) - metric(B) per replicate；返回点估计 + 95%CI + 双侧 p 值
    （p = 2*min(P(diff>0), P(diff<0))，clip 到 1）。用于 BA/Macro-F1（§E 铁律：不用 McNemar）。
    """
    yt = np.asarray(yt)
    pa, pb = np.asarray(pred_a), np.asarray(pred_b)
    sa = None if score_a is None else np.asarray(score_a)
    sb = None if score_b is None else np.asarray(score_b)
    N = len(yt)
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n):
        idx = rng.integers(0, N, N)
        yti = yt[idx]
        va = _single_metric(metric_name, yti, pa[idx], None if sa is None else sa[idx])
        vb = _single_metric(metric_name, yti, pb[idx], None if sb is None else sb[idx])
        if not (math.isnan(va) or math.isnan(vb)):
            diffs.append(va - vb)
    diffs = np.asarray(diffs, dtype=float)
    point = _single_metric(metric_name, yt, pa, sa) - _single_metric(metric_name, yt, pb, sb)
    if diffs.size == 0:
        return dict(diff=point, ci_low=float("nan"), ci_high=float("nan"), pval=float("nan"))
    lo, hi = np.percentile(diffs, [CI_LOW_Q, CI_HIGH_Q])
    frac_gt = float((diffs > 0).mean())
    frac_lt = float((diffs < 0).mean())
    pval = min(1.0, 2.0 * min(frac_gt, frac_lt))
    return dict(diff=float(point), ci_low=float(lo), ci_high=float(hi), pval=float(pval))


def mcnemar_test(yt: np.ndarray, pred_a: np.ndarray, pred_b: np.ndarray) -> dict:
    """
    McNemar 检验（**仅 accuracy** 口径，§E 铁律）。基于 discordant pairs：
      b = A 对 / B 错， c = A 错 / B 对。
    小样本（b+c<=25）用精确二项 p 值（math.comb 自实现）；否则连续性校正卡方，
    1 自由度卡方 sf 用 math.erfc（免 scipy，避 OMP 冲突）。
    """
    yt = np.asarray(yt); pa = np.asarray(pred_a); pb = np.asarray(pred_b)
    a_correct = (pa == yt)
    b_correct = (pb == yt)
    b = int(np.sum(a_correct & ~b_correct))   # A 对 B 错
    c = int(np.sum(~a_correct & b_correct))   # A 错 B 对
    nd = b + c
    if nd == 0:
        return dict(b=b, c=c, stat=0.0, pval=1.0, method="none(无 discordant)")
    if nd <= 25:
        # 精确二项：两侧 p = 2 * sum_{k<=min(b,c)} C(nd,k) 0.5^nd，clip 1
        k = min(b, c)
        tail = sum(math.comb(nd, i) for i in range(0, k + 1)) * (0.5 ** nd)
        pval = min(1.0, 2.0 * tail)
        return dict(b=b, c=c, stat=float(k), pval=float(pval), method="exact_binomial")
    # 连续性校正卡方（1 dof）
    chi2 = (abs(b - c) - 1.0) ** 2 / nd
    pval = math.erfc(math.sqrt(chi2 / 2.0))   # chi2 1-dof survival function
    return dict(b=b, c=c, stat=float(chi2), pval=float(pval), method="chi2_continuity")


def holm_bonferroni(pvals: list[float]) -> tuple[list[float], list[bool]]:
    """
    Holm-Bonferroni（FWER 校正，自实现，免 statsmodels）。
    输入原始 p 值列表 -> (校正后 p 值[对齐输入顺序], reject@0.05[对齐输入顺序])。
    NaN p 值原样透传（不参与排序秩），标 not reject。
    """
    idx_valid = [i for i, p in enumerate(pvals) if not (p is None or math.isnan(p))]
    m = len(idx_valid)
    adj = [float("nan")] * len(pvals)
    reject = [False] * len(pvals)
    if m == 0:
        return adj, reject
    order = sorted(idx_valid, key=lambda i: pvals[i])
    running = 0.0
    for rank, i in enumerate(order):
        a = min(1.0, (m - rank) * pvals[i])
        running = max(running, a)   # Holm 单调不减
        adj[i] = running
        reject[i] = running < 0.05
    return adj, reject


# ============================================================================
# response 级评测运行 + 输出
# ============================================================================
def evaluate_response_level(detectors: list[Detector], slices: dict,
                            n_bootstrap: int) -> dict:
    """
    response 级：每检测器 × 每 slice 算全指标 + bootstrap CI；
    每检测器算 G_domain（gen−macro_f1(med)）非配对 bootstrap CI（复现锚，用 pilot 5000/seed42）；
    若 ≥2 检测器：同 slice 两两 paired bootstrap（BA/F1）+ McNemar（accuracy）+ Holm 校正。
    返回结构化 dict（供写 csv/json）。**只 response 级，claim/span 见 stub。**
    """
    # 先把每检测器在每 slice 的预测缓存下来（供配对检验共用同索引）
    preds = {}   # (det_id, slice) -> dict(y_true, y_pred, y_score)
    for det in detectors:
        for sname, sub in slices.items():
            labels, scores = det.run_batch(sub)
            preds[(det.detector_id, sname)] = dict(
                y_true=sub["y_true"].to_numpy(), y_pred=labels, y_score=scores)
            print(f"[eval] {det.detector_id} @ {sname}: {len(sub)} 条推理完成", flush=True)

    # 1) 逐检测器 × 逐 slice 指标 + CI
    metric_rows = []
    for det in detectors:
        for sname, sub in slices.items():
            rec = preds[(det.detector_id, sname)]
            yt, yp, ys = rec["y_true"], rec["y_pred"], rec["y_score"]
            point = compute_metrics(yt, yp, ys, RESPONSE_METRICS)
            ci = bootstrap_ci(yt, yp, ys, RESPONSE_METRICS, n=n_bootstrap)
            for m in RESPONSE_METRICS:
                lo, hi = ci[m]
                metric_rows.append(dict(
                    level="response", detector=det.detector_id, slice=sname,
                    n=int(len(sub)),
                    n_faithful=int((yt == FAITHFUL).sum()),
                    n_unfaithful=int((yt == UNFAITHFUL).sum()),
                    metric=m, value=round(point[m], 4),
                    ci_low=round(lo, 4), ci_high=round(hi, 4),
                    ci_method=f"bootstrap_{n_bootstrap}"))

    # 2) 逐检测器 G_domain 契约（macro_f1(gen) − macro_f1(med)），非配对 bootstrap CI
    #    用 pilot bootstrap_g_ci（5000/seed42）才能对上冻结值 [0.1844,0.3912]；标注 n。
    contrast_rows = []
    for det in detectors:
        gen = preds[(det.detector_id, SLICE_GENERAL)]
        med = preds[(det.detector_id, SLICE_MEDICAL)]
        f1_gen = macro_f1(gen["y_true"], gen["y_pred"])
        f1_med = macro_f1(med["y_true"], med["y_pred"])
        g = f1_gen - f1_med
        ci_lo, ci_hi = bootstrap_g_ci(
            gen["y_true"], gen["y_pred"], med["y_true"], med["y_pred"])  # pilot 默认 5000/seed42
        contrast_rows.append(dict(
            level="response", detector=det.detector_id,
            contrast="G_domain=macroF1(general)-macroF1(medical)",
            macroF1_general=round(f1_gen, 4), macroF1_medical=round(f1_med, 4),
            G_domain=round(g, 4), ci_low=round(ci_lo, 4), ci_high=round(ci_hi, 4),
            ci_method=f"unpaired_bootstrap_{PILOT_BOOTSTRAP_N}"))

    # 3) 两两配对检验（同 slice；仅 ≥2 检测器才有）
    pairwise_rows = []
    det_ids = [d.detector_id for d in detectors]
    if len(det_ids) >= 2:
        for sname in slices:
            comparisons = []   # 暂存以便对 pval 做 Holm 校正
            for ia in range(len(det_ids)):
                for ib in range(ia + 1, len(det_ids)):
                    da, db = det_ids[ia], det_ids[ib]
                    ra = preds[(da, sname)]; rb = preds[(db, sname)]
                    yt = ra["y_true"]
                    # BA / Macro-F1：paired bootstrap
                    for m in ("balanced_accuracy", "macro_f1"):
                        res = paired_bootstrap_diff(yt, ra["y_pred"], rb["y_pred"], m,
                                                    n=n_bootstrap)
                        comparisons.append(dict(
                            level="response", slice=sname, detector_a=da, detector_b=db,
                            metric=m, test="paired_bootstrap",
                            diff=round(res["diff"], 4), ci_low=round(res["ci_low"], 4),
                            ci_high=round(res["ci_high"], 4), stat=float("nan"),
                            pval=res["pval"]))
                    # accuracy：McNemar
                    mc = mcnemar_test(yt, ra["y_pred"], rb["y_pred"])
                    comparisons.append(dict(
                        level="response", slice=sname, detector_a=da, detector_b=db,
                        metric="accuracy", test=f"mcnemar({mc['method']})",
                        diff=float("nan"), ci_low=float("nan"), ci_high=float("nan"),
                        stat=round(mc["stat"], 4), pval=mc["pval"]))
            # Holm-Bonferroni：对本 slice 的全部两两比较 p 值做 FWER 校正
            adj, rej = holm_bonferroni([c["pval"] for c in comparisons])
            for c, pa, rj in zip(comparisons, adj, rej):
                c["pval"] = round(c["pval"], 5) if not math.isnan(c["pval"]) else c["pval"]
                c["pval_holm"] = round(pa, 5) if not math.isnan(pa) else pa
                c["reject_holm_0.05"] = bool(rj)
                pairwise_rows.append(c)
    else:
        print("[eval] 只有 1 个检测器，跳过两两配对检验/Holm（本轮 R-P1.0 仅 D1）。"
              "接入 ≥2 检测器后自动启用。", flush=True)

    return dict(metric_rows=metric_rows, contrast_rows=contrast_rows,
                pairwise_rows=pairwise_rows)


# ---- claim / span 级：本轮 stub（PLAN §E，独立表不混报，L2-b 铁律）----
def evaluate_claim_level(*_args, **_kw) -> dict:
    """
    TODO(R-P3.2)：claim 级 = 原子陈述；主指标 BA+Macro-F1+MCC+CI；独立 results_claim.csv。
    本轮 R-P1.0 不实现（需先有原子级切分 + claim 标注）。接口占位，绝不与 response 混报。
    """
    return dict(metric_rows=[], note="TODO R-P3.2 claim 级未实现（原子陈述切分 + 标注待 P2）")


def evaluate_span_level(*_args, **_kw) -> dict:
    """
    TODO(R-P3.3)：span 级 = char-level P/R/F1 + soft(partial-overlap)-F1；独立 results_span.csv。
    本轮 R-P1.0 不实现（需 span 标注 + LettuceDetect D5/D6 token-span 输出）。接口占位，不混报。
    """
    return dict(metric_rows=[], note="TODO R-P3.3 span 级未实现（char-level span 标注 + D5/D6 待接）")


# ============================================================================
# 写出（三级各独立 csv，绝不混报）
# ============================================================================
def write_outputs(outdir: Path, resp: dict, claim: dict, span: dict, meta: dict,
                  frozen_check: dict):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # response 级：三张独立 csv（指标 / 契约 / 配对）
    pd.DataFrame(resp["metric_rows"], columns=[
        "level", "detector", "slice", "n", "n_faithful", "n_unfaithful",
        "metric", "value", "ci_low", "ci_high", "ci_method"]).to_csv(
        outdir / "results_response.csv", index=False, encoding="utf-8")

    pd.DataFrame(resp["contrast_rows"], columns=[
        "level", "detector", "contrast", "macroF1_general", "macroF1_medical",
        "G_domain", "ci_low", "ci_high", "ci_method"]).to_csv(
        outdir / "contrasts_response.csv", index=False, encoding="utf-8")

    pw_cols = ["level", "slice", "detector_a", "detector_b", "metric", "test",
               "diff", "ci_low", "ci_high", "stat", "pval", "pval_holm", "reject_holm_0.05"]
    pd.DataFrame(resp["pairwise_rows"], columns=pw_cols).to_csv(
        outdir / "pairwise_response.csv", index=False, encoding="utf-8")

    # claim / span：本轮 stub，写只有表头的独立 csv（占位，证明三级分开、不混）
    claim_path = outdir / "results_claim.csv"
    span_path = outdir / "results_span.csv"
    pd.DataFrame(claim["metric_rows"], columns=[
        "level", "detector", "slice", "n", "metric", "value", "ci_low", "ci_high"]).to_csv(
        claim_path, index=False, encoding="utf-8")
    pd.DataFrame(span["metric_rows"], columns=[
        "level", "detector", "slice", "n", "metric", "value", "ci_low", "ci_high"]).to_csv(
        span_path, index=False, encoding="utf-8")

    # state.json：汇总 + 复现对照 + stub 说明
    state = dict(
        meta=meta,
        frozen_reproduction_check=frozen_check,
        response=dict(
            n_metric_rows=len(resp["metric_rows"]),
            n_contrast_rows=len(resp["contrast_rows"]),
            n_pairwise_rows=len(resp["pairwise_rows"]),
            contrasts=resp["contrast_rows"],
        ),
        claim_level=claim.get("note"),
        span_level=span.get("note"),
        outputs=dict(
            results_response=str(outdir / "results_response.csv"),
            contrasts_response=str(outdir / "contrasts_response.csv"),
            pairwise_response=str(outdir / "pairwise_response.csv"),
            results_claim=str(claim_path), results_span=str(span_path)),
    )
    with open(outdir / "state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print(f"\n[out] {outdir/'results_response.csv'}")
    print(f"[out] {outdir/'contrasts_response.csv'}")
    print(f"[out] {outdir/'pairwise_response.csv'}")
    print(f"[out] {claim_path}  (stub)")
    print(f"[out] {span_path}  (stub)")
    print(f"[out] {outdir/'state.json'}")


def build_frozen_check(resp: dict) -> dict:
    """跑完把 D1 的关键值与 KILLSHOT_LEDGER 冻结值并排，供 verifier 核（不参与计算）。"""
    got = {}
    for row in resp["metric_rows"]:
        if row["detector"] == "D1_mDeBERTa_XNLI" and row["metric"] == "macro_f1":
            got[row["slice"]] = row["value"]
    g_row = next((c for c in resp["contrast_rows"]
                  if c["detector"] == "D1_mDeBERTa_XNLI"), None)
    return dict(
        note="与 KILLSHOT_LEDGER #2 冻结值对照；差异应在 bootstrap/取整噪声内。仅 macro_f1/G_domain 有冻结锚。",
        medhallu_medical=dict(got=got.get(SLICE_MEDICAL), frozen=FROZEN_MED_MACRO_F1),
        psiloqa_en_general=dict(got=got.get(SLICE_GENERAL), frozen=FROZEN_GEN_MACRO_F1),
        G_domain=dict(got=(g_row or {}).get("G_domain"), frozen=FROZEN_G_DOMAIN,
                      frozen_ci=list(FROZEN_G_DOMAIN_CI),
                      got_ci=[(g_row or {}).get("ci_low"), (g_row or {}).get("ci_high")]),
    )


# ============================================================================
# --selfcheck：断言 D1 硬标签与 pilot run_mdeberta 逐条相等（证明零偏离）
# ============================================================================
def run_selfcheck(slices: dict, model_id: str, batch_size: int, device: str):
    """
    额外调 pilot run_mdeberta（冻结 NLI 臂）在同样两 slice 上出硬标签，
    与本 harness D1 的硬标签逐条比对。全等 => 证明 harness 未偏离 pilot NLI 设置。
    注意：pilot run_mdeberta 内部写死用 mnli-xnli 模型；仅当 --model-id 也是它时可比。
    """
    if model_id != MDEBERTA_MODEL_ID:
        print(f"[selfcheck] 跳过：--model-id={model_id} 非 pilot 冻结模型 {MDEBERTA_MODEL_ID}，"
              "无法与 pilot run_mdeberta 逐条比对（pilot 内部写死后者）。", flush=True)
        return
    print("[selfcheck] 用 pilot run_mdeberta 复算硬标签做零偏离断言 ...", flush=True)
    det = D1MDeBERTaXNLI(model_id=model_id, batch_size=batch_size, device=device)
    pilot_preds = run_mdeberta(slices, NLI_THRESHOLD, batch_size, device)
    all_ok = True
    for sname, sub in slices.items():
        harness_labels, _ = det.run_batch(sub)
        ok = bool(np.array_equal(harness_labels, pilot_preds[sname]))
        all_ok = all_ok and ok
        print(f"[selfcheck] {sname}: harness==pilot 硬标签 -> {'PASS' if ok else 'FAIL'}"
              f" ({int((harness_labels==pilot_preds[sname]).sum())}/{len(sub)} 一致)", flush=True)
    print(f"[selfcheck] 总裁决：{'ZERO-DEVIATION PASS' if all_ok else 'DEVIATION DETECTED (排查!)'}",
          flush=True)


# ============================================================================
# main
# ============================================================================
def main():
    ap = argparse.ArgumentParser(
        description="CMedFaith 统一评测 harness（R-P1.0 英文对照复现 + 三级评测骨架）")
    ap.add_argument("--psiloqa-data", type=Path, default=None,
                    help="PsiloQA parquet 路径（通用 slice）；不给则读 datasets.json + glob 兜底，见 [T2]")
    ap.add_argument("--outdir", type=Path, default=HARNESS_DIR / "results",
                    help="输出目录（默认 code/results/）")
    ap.add_argument("--detectors", nargs="+", default=["D1_mDeBERTa_XNLI"],
                    help="要跑的检测器 id（本轮只有 D1 实现，D2-D15 是 stub）")
    ap.add_argument("--model-id", default=MDEBERTA_MODEL_ID,
                    help=f"mDeBERTa 模型 id（默认 pilot 冻结 {MDEBERTA_MODEL_ID}；换则不保证复现 0.43/0.72，见 [T4]）")
    ap.add_argument("--n-bootstrap", type=int, default=DEFAULT_N_BOOTSTRAP,
                    help="bootstrap resamples（§E 默认 10000）")
    ap.add_argument("--batch-size", type=int, default=16, help="mDeBERTa 推理 batch")
    ap.add_argument("--device", default=None, help="cuda/cpu；默认自动")
    ap.add_argument("--include-artificial", action="store_true",
                    help="MedHallu 加 pqa_artificial(9k 合成集)；复现冻结值不加（冻结用 pqa_labeled）")
    ap.add_argument("--medhallu-cache", type=Path, default=None, help="MedHallu HF 缓存目录")
    ap.add_argument("--limit", type=int, default=None,
                    help="调试：医学限前 N question、通用限前 N 条")
    ap.add_argument("--selfcheck", action="store_true",
                    help="额外用 pilot run_mdeberta 断言硬标签逐条相等（证明零偏离）")
    ap.add_argument("--smoke", action="store_true",
                    help="冒烟：等价 --limit 20 --n-bootstrap 200（先验管线通，非正式结果）")
    args = ap.parse_args()

    if args.smoke:
        args.limit = args.limit or 20
        args.n_bootstrap = min(args.n_bootstrap, 200)
        print(f"[smoke] 冒烟模式：limit={args.limit}, n_bootstrap={args.n_bootstrap}"
              "（结果仅验管线，不作复现对照）", flush=True)

    device = args.device or _auto_device()
    print(f"[cfg] device={device} model_id={args.model_id} n_bootstrap={args.n_bootstrap} "
          f"detectors={args.detectors}", flush=True)

    # 数据登记核对 + 路径解析（[T2]/[T3]）
    read_datasets_registry()
    psiloqa_path = resolve_psiloqa_parquet(args.psiloqa_data)

    # 加载两独立 slice（复用 pilot 冻结加载器；绝不 concat）
    slices = load_slices(psiloqa_path, args.include_artificial, args.medhallu_cache, args.limit)

    # 可选：零偏离断言
    if args.selfcheck:
        run_selfcheck(slices, args.model_id, args.batch_size, device)

    # 建检测器（stub 自动跳过）
    detectors = build_detectors(args.detectors, args.batch_size, device, args.model_id)
    if not detectors:
        print("[eval] 无可跑检测器（都是 stub 或未知），退出。", flush=True)
        sys.exit(2)

    # 三级评测：response 实现，claim/span stub（独立不混）
    resp = evaluate_response_level(detectors, slices, args.n_bootstrap)
    claim = evaluate_claim_level(detectors, slices)
    span = evaluate_span_level(detectors, slices)

    # 复现对照 + 写出
    frozen_check = build_frozen_check(resp)
    meta = dict(
        run="R-P1.0", psiloqa_data=str(psiloqa_path), model_id=args.model_id,
        nli_threshold=NLI_THRESHOLD, n_bootstrap=args.n_bootstrap,
        include_artificial=args.include_artificial, limit=args.limit,
        downsample_seed=DOWNSAMPLE_SEED, device=device, detectors=args.detectors)
    write_outputs(args.outdir, resp, claim, span, meta, frozen_check)

    # 控制台打印复现对照（供快速肉眼核，正式核走 verifier + Bash csv）
    print("\n" + "=" * 78)
    print("复现对照（KILLSHOT_LEDGER #2 冻结 vs 本次；差异应在 bootstrap/取整噪声内）")
    print("-" * 78)
    fc = frozen_check
    print(f"  MedHallu(medical)  macro_f1: got={fc['medhallu_medical']['got']}  "
          f"frozen={fc['medhallu_medical']['frozen']}")
    print(f"  PsiloQA-en(general) macro_f1: got={fc['psiloqa_en_general']['got']}  "
          f"frozen={fc['psiloqa_en_general']['frozen']}")
    print(f"  G_domain: got={fc['G_domain']['got']} CI={fc['G_domain']['got_ci']}  "
          f"frozen={fc['G_domain']['frozen']} CI={fc['G_domain']['frozen_ci']}")
    print("=" * 78)


if __name__ == "__main__":
    main()
