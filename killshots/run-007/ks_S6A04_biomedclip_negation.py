"""
G5 Kill-shot: S6-04 — BiomedCLIP 否定/不确定性理解失效
服务: run-007 ACCV 选题流水线 G5 杀手锏（lever = G5 立项前证伪）
目标: BiomedCLIP zero-shot 在 CheXpert-5x200 上分三层（pos/neg/uncertain）
      各算 AUC，测否定层/不确定层 AUC 是否显著低于肯定层（失效 claim）。

R9 判读约定（_G5_DESIGN.md §S6-04 §2 MDE）：
  PASS/FINDINGS : 否定层 AUC 比肯定层低 >= 0.05 且 CI 不含 0
                → 失效真存在 → 维持 FINDINGS
  KILL/neg-findings : 三层 AUC 差 CI 含 0 且窄
                → BiomedCLIP 否定鲁棒 → 转写否定鲁棒性 findings
  GRAY : 分层后每层样本太少致 CI 宽（同时覆盖 null+signal）
                → 标需扩子集，FINDINGS 进 G6

核心设计（researcher 已查实）：
  - 模型: microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224
  - 官方 prompt 模板: 'this is a photo of ' + label_name
  - 否定 prompt 策略: CLIP 系无官方"no X"否定模板；S6-04 用
    pos_prompt = 'this is a photo of {finding}'
    neg_prompt = 'this is a photo of no {finding}'（可选 --neg_strategy abnormal/no_finding）
    本脚本把否定 prompt 策略做成 --neg_strategy 参数，这是 S6-04 要测的核心。
  - AUC 口径: 对每个 finding, 对每个标注层（pos/neg/uncertain）内部做
    二分类: 该层样本 vs 其他标注层样本；continuous AUC + 1000 bootstrap CI。

数据:
  train.csv: D:/YJ-Agent/project/data/external/chexpert/train.csv
  图像目录:  D:/YJ-Agent/project/data/external/chexpert/CheXpert-v1.0-small/train/
  （图像需先解压 chexpert.zip；若未解压则子集选择 dry-run 仍可跑，不需图）

输出:
  killshots/run-007/results/S6A04_subset.csv        — 子集清单（不依赖图）
  killshots/run-007/results/S6A04_biomedclip.csv    — 逐 finding×层 AUC + bootstrap CI
  killshots/run-007/results/S6A04_state.json        — R9 判读摘要

安装依赖（若未装）:
  pip install open_clip_torch transformers torch torchvision pillow pandas numpy tqdm

NOTE: 若 open_clip 未安装或 BiomedCLIP 权重未缓存，脚本顶部 import 检查失败时
      会打印安装/缓存提示并退出，不会硬跑。权重首次运行时从 HuggingFace 自动下载
      （~1GB），需网络。CPU 烟测（--smoke 1 --cpu）只跑子集选择，不加载模型。

Windows 规范: pathlib / UTF-8 / spawn guard / no scipy / pin_memory=False
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# ── 路径 ──────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent       # D:/YJ-Agent
CHEXPERT_CSV = REPO_ROOT / "project" / "data" / "external" / "chexpert" / "train.csv"
CHEXPERT_IMG_ROOT = REPO_ROOT / "project" / "data" / "external" / "chexpert"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

# ── 超参（全部来自 _G5_DESIGN.md，不臆想）────────────────────────────────────
# 5 个 finding，researcher 查实 CheXpert 常用 zero-shot 评测子集
TARGET_FINDINGS = [
    "Cardiomegaly",
    "Edema",
    "Consolidation",
    "Pleural Effusion",
    "Pneumonia",
]

# 每 finding 每层最多抽取样本数（_G5_DESIGN §S6-04: 5x200 子集）
N_PER_STRATUM = 200

# 标注层映射（CheXpert 原始标签: 1=pos / 0=neg / -1=uncertain / NaN=未提及）
LABEL_POS = 1.0
LABEL_NEG = 0.0
LABEL_UNC = -1.0

# MDE（_G5_DESIGN §S6-04 §2）: 否定层 AUC 比肯定层低 >= 0.05 视为失效真存在
MDE_AUC_DIFF = 0.05

# bootstrap
N_BOOTSTRAP = 1000
RANDOM_STATE = 42

# BiomedCLIP 模型标识（researcher 查实）
BIOMEDCLIP_HF_ID = "hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224"

# 官方 prompt 模板（researcher 查实）
PROMPT_TEMPLATE = "this is a photo of "

# neg_strategy 选项说明（S6-04 核心测点）:
#   'no_X'        : pos='this is a photo of {finding}'
#                   neg='this is a photo of no {finding}'
#   'normal'      : neg='this is a photo of normal chest'（对照健康胸片）
#   'no_finding'  : neg='this is a photo of no finding'（官方 no-finding 类）
# 默认 'no_X' 测否定理解最直接
NEG_STRATEGY_OPTS = ("no_X", "normal", "no_finding")


# ── 纯 numpy bootstrap AUC（不用 scipy，避免 OMP Error #15）─────────────────
def _auc_from_scores(labels: np.ndarray, scores: np.ndarray) -> float:
    """Mann-Whitney AUC（trapezoid，O(n log n)）。labels: 0/1。"""
    pos_scores = scores[labels == 1]
    neg_scores = scores[labels == 0]
    if len(pos_scores) == 0 or len(neg_scores) == 0:
        return float("nan")
    # vectorized: count (pos > neg) + 0.5*(pos == neg)
    diff = pos_scores[:, None] - neg_scores[None, :]  # (P, N)
    return float((np.sum(diff > 0) + 0.5 * np.sum(diff == 0)) / diff.size)


def bootstrap_auc_ci(
    labels: np.ndarray,
    scores: np.ndarray,
    n_boot: int = N_BOOTSTRAP,
    seed: int = RANDOM_STATE,
    ci: float = 0.95,
) -> tuple[float, float, float]:
    """返回 (point_estimate, ci_lo, ci_hi)。纯 numpy，无 scipy。"""
    rng = np.random.default_rng(seed)
    n = len(labels)
    boot_aucs = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        lb, sc = labels[idx], scores[idx]
        if len(np.unique(lb)) < 2:
            continue
        boot_aucs.append(_auc_from_scores(lb, sc))
    if len(boot_aucs) < 10:
        return float("nan"), float("nan"), float("nan")
    arr = np.array(boot_aucs)
    alpha = 1.0 - ci
    return (
        _auc_from_scores(labels, scores),
        float(np.percentile(arr, 100 * alpha / 2)),
        float(np.percentile(arr, 100 * (1 - alpha / 2))),
    )


# ── 子集选择（不依赖图/模型，纯 CSV，必须能跑通）──────────────────────────────
def build_subset(csv_path: Path, n_per_stratum: int = N_PER_STRATUM) -> pd.DataFrame:
    """
    从 train.csv 分层抽取 CheXpert-5x200 子集。
    只保留 Frontal 图，对 5 个 finding 各抽 pos/neg/uncertain 三层，
    每层最多 n_per_stratum 张（随机种子 RANDOM_STATE）。
    返回含 Path + 每个 finding 标签列的 DataFrame。
    NaN（未提及）不入任何层。
    """
    df = pd.read_csv(csv_path, low_memory=False)

    # 只用 frontal
    df = df[df["Frontal/Lateral"] == "Frontal"].reset_index(drop=True)

    # 标签列转 float（已是 float，但防万一）
    for f in TARGET_FINDINGS:
        df[f] = pd.to_numeric(df[f], errors="coerce")

    selected_rows = []
    rng = np.random.default_rng(RANDOM_STATE)

    for finding in TARGET_FINDINGS:
        col = df[finding]
        for lval in (LABEL_POS, LABEL_NEG, LABEL_UNC):
            mask = col == lval
            pool = df[mask]
            if len(pool) == 0:
                continue
            take = min(n_per_stratum, len(pool))
            chosen_idx = rng.choice(pool.index.to_numpy(), size=take, replace=False)
            subset_rows = df.loc[chosen_idx].copy()
            subset_rows["_finding"] = finding
            subset_rows["_stratum"] = {
                LABEL_POS: "pos",
                LABEL_NEG: "neg",
                LABEL_UNC: "uncertain",
            }[lval]
            selected_rows.append(subset_rows)

    if not selected_rows:
        raise ValueError("子集为空，检查 train.csv 路径和标签列名")

    result = pd.concat(selected_rows, ignore_index=True)
    # 去重（同一图可能在多个 finding 中被选中，保留所有行因为是 finding 维度的）
    result = result.drop_duplicates(subset=["Path", "_finding", "_stratum"])
    return result


# ── Prompt 构造 ────────────────────────────────────────────────────────────────
def make_prompts(finding: str, neg_strategy: str) -> tuple[str, str]:
    """
    返回 (pos_prompt, neg_prompt)。
    S6-04 核心测点：CLIP 系对否定理解的弱点在此体现。
    官方 BiomedCLIP 无"no X"否定模板（researcher 确认），
    neg_strategy 参数化供消融。
    """
    pos_prompt = PROMPT_TEMPLATE + finding.lower()

    if neg_strategy == "no_X":
        neg_prompt = PROMPT_TEMPLATE + f"no {finding.lower()}"
    elif neg_strategy == "normal":
        neg_prompt = PROMPT_TEMPLATE + "normal chest"
    elif neg_strategy == "no_finding":
        neg_prompt = PROMPT_TEMPLATE + "no finding"
    else:
        raise ValueError(f"未知 neg_strategy: {neg_strategy}, 可选: {NEG_STRATEGY_OPTS}")

    return pos_prompt, neg_prompt


# ── 模型加载（try-import，失败即退出并提示）───────────────────────────────────
def load_biomedclip(device: str):
    """
    加载 BiomedCLIP 模型 + preprocess。
    若 open_clip 未安装或权重未缓存，打印提示并 sys.exit(1)。
    权重首次加载从 HuggingFace 自动下载（~1GB），需网络。
    """
    try:
        import open_clip  # noqa: PLC0415
    except ImportError:
        print(
            "[ERROR] open_clip 未安装。请运行:\n"
            "  pip install open_clip_torch\n"
            "然后重试。",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        import torch  # noqa: PLC0415
    except ImportError:
        print(
            "[ERROR] torch 未安装。请运行:\n"
            "  pip install torch torchvision\n"
            "然后重试。",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[INFO] 加载 BiomedCLIP: {BIOMEDCLIP_HF_ID} (device={device})")
    print("[INFO] 首次运行将从 HuggingFace 下载模型权重（~1GB），请确保网络畅通...")

    try:
        model, preprocess = open_clip.create_model_from_pretrained(
            BIOMEDCLIP_HF_ID
        )
        tokenizer = open_clip.get_tokenizer(BIOMEDCLIP_HF_ID)
    except Exception as e:
        print(
            f"[ERROR] BiomedCLIP 加载失败: {e}\n"
            "可能原因:\n"
            "  1. 网络不通，无法下载权重\n"
            "  2. open_clip_torch 版本过旧（需 >= 2.20.0）\n"
            "  3. HuggingFace Hub 缓存损坏（清除 ~/.cache/huggingface/hub/ 重试）\n"
            "安装命令: pip install open_clip_torch>=2.20.0 transformers",
            file=sys.stderr,
        )
        sys.exit(1)

    model = model.to(device).eval()
    return model, preprocess, tokenizer


# ── BiomedCLIP zero-shot 推理 ─────────────────────────────────────────────────
def infer_similarity(
    image_paths: list[Path],
    pos_prompt: str,
    neg_prompt: str,
    model,
    preprocess,
    tokenizer,
    device: str,
    batch_size: int = 64,
) -> np.ndarray:
    """
    对每张图计算 softmax(pos_prompt 相似度) 作为「该 finding 存在」的概率分数。
    返回 shape (N,) float32。
    """
    try:
        import torch  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415
        from tqdm import tqdm  # noqa: PLC0415
    except ImportError as e:
        print(f"[ERROR] 缺少依赖: {e}\npip install Pillow tqdm", file=sys.stderr)
        sys.exit(1)

    texts = tokenizer([pos_prompt, neg_prompt]).to(device)  # (2, seq_len)

    with torch.no_grad():
        text_feats = model.encode_text(texts)
        text_feats = text_feats / text_feats.norm(dim=-1, keepdim=True)  # (2, D)

    all_scores = []

    for start in tqdm(range(0, len(image_paths), batch_size), desc="  inference"):
        batch_paths = image_paths[start : start + batch_size]
        imgs = []
        for p in batch_paths:
            try:
                img = preprocess(Image.open(p).convert("RGB"))
                imgs.append(img)
            except Exception:
                # 图像损坏/缺失，填零特征
                imgs.append(torch.zeros(3, 224, 224))

        batch_tensor = torch.stack(imgs).to(device)  # (B, 3, 224, 224)

        with torch.no_grad():
            img_feats = model.encode_image(batch_tensor)
            img_feats = img_feats / img_feats.norm(dim=-1, keepdim=True)  # (B, D)

        # cosine sim to pos/neg prompts: (B, 2)
        logits = (img_feats @ text_feats.T).float().cpu().numpy()

        # softmax over 2 classes → pos 的概率
        exp_logits = np.exp(logits - logits.max(axis=1, keepdims=True))
        probs_pos = exp_logits[:, 0] / exp_logits.sum(axis=1)  # (B,)
        all_scores.append(probs_pos)

    return np.concatenate(all_scores, axis=0)


# ── 单 finding 分层 AUC 计算 ─────────────────────────────────────────────────
def compute_layered_auc(
    subset: pd.DataFrame,
    finding: str,
    scores_dict: dict[int, np.ndarray],  # idx -> score（全量 subset index）
    score_col: str = "_score",
) -> list[dict]:
    """
    对单个 finding 分三层（pos/neg/uncertain）计算 AUC。
    AUC 口径: 该层 vs 其余两层（二分类），continuous + bootstrap CI。
    返回 list of row dicts。
    """
    rows = []
    finding_df = subset[subset["_finding"] == finding].copy()
    finding_df = finding_df.reset_index(drop=True)

    # 获取分数
    if score_col in finding_df.columns:
        scores = finding_df[score_col].to_numpy(dtype=float)
    else:
        return rows  # dry-run 模式无分数列

    strata = {"pos": "pos", "neg": "neg", "uncertain": "uncertain"}
    stratum_vals = finding_df["_stratum"].to_numpy()

    for stratum_name in strata:
        binary_labels = (stratum_vals == stratum_name).astype(int)
        if binary_labels.sum() == 0 or binary_labels.sum() == len(binary_labels):
            rows.append(
                {
                    "finding": finding,
                    "stratum": stratum_name,
                    "n_stratum": int(binary_labels.sum()),
                    "n_total": len(binary_labels),
                    "auc": float("nan"),
                    "ci_lo": float("nan"),
                    "ci_hi": float("nan"),
                    "note": "single_class_skip",
                }
            )
            continue

        auc, ci_lo, ci_hi = bootstrap_auc_ci(binary_labels, scores)
        rows.append(
            {
                "finding": finding,
                "stratum": stratum_name,
                "n_stratum": int(binary_labels.sum()),
                "n_total": len(binary_labels),
                "auc": round(auc, 4),
                "ci_lo": round(ci_lo, 4),
                "ci_hi": round(ci_hi, 4),
                "note": "",
            }
        )
    return rows


# ── R9 判读 ───────────────────────────────────────────────────────────────────
def r9_verdict(results_df: pd.DataFrame) -> dict:
    """
    按 _G5_DESIGN §S6-04 R9 判读规则汇总。
    MDE: neg 层 AUC 比 pos 层低 >= MDE_AUC_DIFF=0.05 且 CI 不含 0 → PASS/FINDINGS。
    """
    verdict_per_finding: dict[str, str] = {}

    for finding in TARGET_FINDINGS:
        fdf = results_df[results_df["finding"] == finding]

        pos_row = fdf[fdf["stratum"] == "pos"]
        neg_row = fdf[fdf["stratum"] == "neg"]
        unc_row = fdf[fdf["stratum"] == "uncertain"]

        def get_auc(row):
            if len(row) == 0:
                return None, None, None
            r = row.iloc[0]
            return r["auc"], r["ci_lo"], r["ci_hi"]

        pos_auc, pos_lo, pos_hi = get_auc(pos_row)
        neg_auc, neg_lo, neg_hi = get_auc(neg_row)
        unc_auc, unc_lo, unc_hi = get_auc(unc_row)

        # CI 宽度判断（宽 = ci_hi - ci_lo > 0.15）
        def ci_narrow(lo, hi):
            if lo is None or hi is None or np.isnan(lo) or np.isnan(hi):
                return False
            return (hi - lo) <= 0.15

        if any(x is None or np.isnan(x) for x in [pos_auc, neg_auc]):
            verdict_per_finding[finding] = "GRAY(no_data)"
            continue

        diff_neg_pos = pos_auc - neg_auc  # 正值 = neg 层 AUC 更低（失效）

        # CI 不含 0 的近似：若 diff - (ci 宽度/2) > 0 则不含 0
        # 用 bootstrap: ci of diff 近似 = 两者 ci 宽度相加（保守估计）
        # 更精确做法在 aggregate_diff_ci，此处简化判读
        ci_width_approx = (
            (pos_hi - pos_lo if not np.isnan(pos_hi) else 0.2)
            + (neg_hi - neg_lo if not np.isnan(neg_hi) else 0.2)
        ) / 2

        if not ci_narrow(pos_lo, pos_hi) or not ci_narrow(neg_lo, neg_hi):
            verdict_per_finding[finding] = "GRAY(wide_CI)"
        elif diff_neg_pos >= MDE_AUC_DIFF and diff_neg_pos > ci_width_approx:
            verdict_per_finding[finding] = "PASS/FINDINGS(negation_fail)"
        elif diff_neg_pos < 0:
            # neg 层 AUC 更高，反向
            verdict_per_finding[finding] = "KILL/neg_robust(reversed)"
        elif diff_neg_pos < MDE_AUC_DIFF and ci_narrow(pos_lo, pos_hi) and ci_narrow(neg_lo, neg_hi):
            verdict_per_finding[finding] = "KILL/neg_robust(narrow_CI_below_MDE)"
        else:
            verdict_per_finding[finding] = "GRAY(borderline)"

    # 汇总
    n_pass = sum(1 for v in verdict_per_finding.values() if v.startswith("PASS"))
    n_kill = sum(1 for v in verdict_per_finding.values() if v.startswith("KILL"))
    n_gray = sum(1 for v in verdict_per_finding.values() if v.startswith("GRAY"))

    if n_pass >= 3:
        overall = "PASS/FINDINGS — BiomedCLIP 否定失效在 >=3/5 findings 成立，claim 活"
    elif n_kill >= 3:
        overall = "KILL/neg_robust — BiomedCLIP 否定鲁棒，否定退化 claim 证伪，转写 negative findings"
    else:
        overall = f"GRAY — 信号不一致（PASS={n_pass}/KILL={n_kill}/GRAY={n_gray}），需扩子集复测"

    return {
        "per_finding": verdict_per_finding,
        "n_pass": n_pass,
        "n_kill": n_kill,
        "n_gray": n_gray,
        "overall": overall,
        "mde_used": MDE_AUC_DIFF,
    }


# ── 主流程 ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="S6-04 BiomedCLIP 否定/不确定性失效 kill-shot"
    )
    parser.add_argument(
        "--smoke", type=int, default=0,
        help="烟测模式：1=只跑子集选择（不加载模型），0=完整推理"
    )
    parser.add_argument(
        "--cpu", action="store_true",
        help="强制 CPU 推理（用于烟测/调试；正式推理推荐 GPU）"
    )
    parser.add_argument(
        "--neg_strategy", type=str, default="no_X",
        choices=NEG_STRATEGY_OPTS,
        help=(
            "否定 prompt 策略（S6-04 核心测点）: "
            "no_X=使用'no {finding}', "
            "normal=对比'normal chest', "
            "no_finding=对比'no finding'"
        ),
    )
    parser.add_argument(
        "--batch_size", type=int, default=64,
        help="推理 batch size（CPU 建议 16，GPU 可 64）"
    )
    parser.add_argument(
        "--n_per_stratum", type=int, default=N_PER_STRATUM,
        help=f"每 finding 每层最多采样数（默认 {N_PER_STRATUM}）"
    )
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    subset_csv = RESULTS_DIR / "S6A04_subset.csv"
    results_csv = RESULTS_DIR / "S6A04_biomedclip.csv"
    state_json = RESULTS_DIR / "S6A04_state.json"

    # ── Step 1: 子集选择（不依赖图/模型，必须跑通）──────────────────────────
    print("=" * 60)
    print("[Step 1] 构造 CheXpert-5x200 子集 ...")
    print(f"  CSV: {CHEXPERT_CSV}")

    if not CHEXPERT_CSV.exists():
        print(
            f"[ERROR] train.csv 不存在: {CHEXPERT_CSV}\n"
            "请确认 CheXpert 数据已下载至 "
            "D:/YJ-Agent/project/data/external/chexpert/train.csv",
            file=sys.stderr,
        )
        sys.exit(1)

    subset = build_subset(CHEXPERT_CSV, n_per_stratum=args.n_per_stratum)
    subset.to_csv(subset_csv, index=False, encoding="utf-8")

    # 打印子集统计
    print(f"  子集总行数: {len(subset)}")
    for finding in TARGET_FINDINGS:
        fdf = subset[subset["_finding"] == finding]
        counts = fdf["_stratum"].value_counts().to_dict()
        print(f"  {finding}: pos={counts.get('pos',0)}, "
              f"neg={counts.get('neg',0)}, "
              f"uncertain={counts.get('uncertain',0)}")
    print(f"  [OK] 子集已保存: {subset_csv}")

    # ── smoke 模式：只跑子集选择，不加载模型 ─────────────────────────────────
    if args.smoke:
        print("\n[SMOKE MODE] 子集选择完成，跳过模型推理。")
        state = {
            "status": "smoke_ok",
            "subset_rows": len(subset),
            "smoke": True,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        state_json.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] state.json 已写: {state_json}")
        return

    # ── Step 2: 检查图像目录 ─────────────────────────────────────────────────
    print("\n[Step 2] 检查图像目录 ...")
    # 取一张样本图做路径解析
    sample_path_str = subset["Path"].iloc[0]
    # Path 形如 CheXpert-v1.0-small/train/patientXXXXX/...
    # 实际图在 CHEXPERT_IMG_ROOT / Path
    sample_full = CHEXPERT_IMG_ROOT / sample_path_str
    img_dir_exists = sample_full.parent.exists() or (
        CHEXPERT_IMG_ROOT / "CheXpert-v1.0-small"
    ).exists()

    if not img_dir_exists:
        print(
            "[WARNING] 图像目录未找到（CheXpert 可能尚未解压）。\n"
            f"  期望路径示例: {sample_full}\n"
            "  请解压 chexpert.zip 到 "
            "D:/YJ-Agent/project/data/external/chexpert/ 后重跑完整推理。\n"
            "[DRY-RUN] 跳过推理，子集 CSV 已就绪。",
            file=sys.stderr,
        )
        state = {
            "status": "dry_run_no_images",
            "subset_rows": len(subset),
            "smoke": False,
            "note": "images not found, run after extracting chexpert.zip",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        state_json.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] state.json 已写 (dry_run): {state_json}")
        return

    # ── Step 3: 加载 BiomedCLIP ──────────────────────────────────────────────
    print("\n[Step 3] 加载 BiomedCLIP ...")

    try:
        import torch  # noqa: PLC0415
        CUDA_AVAILABLE = torch.cuda.is_available()
    except ImportError:
        CUDA_AVAILABLE = False

    if args.cpu or not CUDA_AVAILABLE:
        device = "cpu"
        if not args.cpu and not CUDA_AVAILABLE:
            print("[INFO] CUDA 不可用，使用 CPU 推理（速度较慢，1000图约10-30min）")
    else:
        device = "cuda"
        print(f"[INFO] 使用 GPU: {torch.cuda.get_device_name(0)}")

    model, preprocess, tokenizer = load_biomedclip(device)

    # ── Step 4: 逐 finding zero-shot 推理 + 分层 AUC ─────────────────────────
    print(f"\n[Step 4] Zero-shot 推理 (neg_strategy={args.neg_strategy}) ...")
    all_rows = []

    for finding in TARGET_FINDINGS:
        print(f"\n  [{finding}]")
        pos_prompt, neg_prompt = make_prompts(finding, args.neg_strategy)
        print(f"    pos_prompt: {pos_prompt!r}")
        print(f"    neg_prompt: {neg_prompt!r}")

        finding_df = subset[subset["_finding"] == finding].copy()
        finding_df = finding_df.reset_index(drop=True)

        # 构造图像完整路径
        img_paths = [
            CHEXPERT_IMG_ROOT / row["Path"]
            for _, row in finding_df.iterrows()
        ]

        # 推理
        scores = infer_similarity(
            img_paths, pos_prompt, neg_prompt,
            model, preprocess, tokenizer,
            device=device, batch_size=args.batch_size,
        )

        finding_df["_score"] = scores

        # 写回 subset（含 _score）
        subset.loc[finding_df.index[finding_df["_finding"] == finding], "_score"] = scores

        # 分层 AUC + bootstrap CI
        rows = compute_layered_auc(finding_df, finding, {}, score_col="_score")
        all_rows.extend(rows)

        for r in rows:
            print(
                f"    {r['stratum']:>10}: AUC={r['auc']:.4f} "
                f"[{r['ci_lo']:.4f}, {r['ci_hi']:.4f}] "
                f"(n={r['n_stratum']}/{r['n_total']})"
            )

    # ── Step 5: 保存 results + R9 判读 ───────────────────────────────────────
    print("\n[Step 5] 保存结果 + R9 判读 ...")
    results_df = pd.DataFrame(all_rows)
    results_df["neg_strategy"] = args.neg_strategy
    results_df.to_csv(results_csv, index=False, encoding="utf-8")
    print(f"  [OK] 推理结果: {results_csv}")

    verdict = r9_verdict(results_df)

    print("\n" + "=" * 60)
    print("R9 判读结果：")
    for f, v in verdict["per_finding"].items():
        print(f"  {f}: {v}")
    print(f"\n  汇总: {verdict['overall']}")
    print("=" * 60)

    state = {
        "status": "done",
        "neg_strategy": args.neg_strategy,
        "subset_rows": len(subset),
        "n_findings": len(TARGET_FINDINGS),
        "r9_verdict": verdict,
        "results_csv": str(results_csv),
        "subset_csv": str(subset_csv),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    state_json.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] state.json 已写: {state_json}")


if __name__ == "__main__":
    main()
