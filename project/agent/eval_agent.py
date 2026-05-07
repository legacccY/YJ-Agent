"""Agent 端到端评测脚本。

评测指标：
  - 引导选择性：低质量图片触发追问率 vs 高质量图片触发追问率
  - 分类准确率：最终 triage 结果与 ISIC ground-truth 对比

用法：
  cd D:/YJ-Agent/project && python agent/eval_agent.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from tqdm import tqdm

PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from agent.orchestrator import ReActAgent

# ── Config ────────────────────────────────────────────────────────────────────
LABELS_CSV   = "D:/YJ-Agent/data/quality_labels_all.csv"
METADATA_CSV = "D:/YJ-Agent/data/raw/isic2020/train-metadata.csv"
SPLIT_CSV    = "D:/YJ-Agent/data/isic_split.csv"
N_EVAL       = 200   # 高质量 + 低质量各取 N_EVAL 张
QAD_THRESH   = 0.50  # 恶性概率判正阈值
SEED         = 42
OUT_FILE     = "D:/YJ-Agent/project/results/eval_agent_report.md"


def load_rgb(path: str) -> np.ndarray | None:
    img = cv2.imread(str(path))
    if img is None:
        return None
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return cv2.resize(img, (224, 224))


def evaluate():
    df = pd.read_csv(LABELS_CSV)
    meta = pd.read_csv(METADATA_CSV)[["isic_id", "target"]]
    split = pd.read_csv(SPLIT_CSV)

    # 只取 test split 中的 ISIC 样本
    test_ids = set(split[split["split"] == "test"]["isic_id"])
    df["isic_id"] = df["degraded_path"].apply(lambda p: Path(p).stem.split("_")[0] + "_" + Path(p).stem.split("_")[1]
                                               if len(Path(p).stem.split("_")) >= 2 else Path(p).stem)
    # ISIC id format: ISIC_XXXXXXX
    df["isic_id"] = df["degraded_path"].apply(
        lambda p: "_".join(Path(p).stem.replace("\\", "/").split("/")[-1].split("_")[:2])
    )
    df = df[df["isic_id"].isin(test_ids) & (df["source"] == "isic2020")]
    df = df.merge(meta, on="isic_id", how="left").dropna(subset=["target"])

    # 高质量 = 原始未降质图（original_path），低质量 = 重度降质图
    df_orig = df.drop_duplicates("isic_id").copy()
    df_orig["eval_path"] = df_orig["original_path"]
    df_heavy = df[df["level"] == "heavy"].copy()
    df_heavy["eval_path"] = df_heavy["degraded_path"]

    df_high = df_orig.sample(min(N_EVAL, len(df_orig)), random_state=SEED)
    df_low  = df_heavy.sample(min(N_EVAL, len(df_heavy)), random_state=SEED)

    agent = ReActAgent()

    stats: dict[str, dict] = {
        "high_quality": {"guided": 0, "total": 0, "probs": [], "targets": []},
        "low_quality":  {"guided": 0, "total": 0, "probs": [], "targets": []},
    }

    for label, df_split in [("high_quality", df_high), ("low_quality", df_low)]:
        for _, row in tqdm(df_split.iterrows(), total=len(df_split), desc=label):
            img = load_rgb(str(row["eval_path"]))
            if img is None:
                continue

            state = agent.start(img)

            # 如果 Agent 追问，用同一张图模拟用户重传（验证引导后能正常完成分析）
            for _ in range(3):
                if not state.waiting_for_user:
                    break
                state = agent.continue_with_new_image(state, img)

            stats[label]["total"] += 1
            if state.retake_count > 0:
                stats[label]["guided"] += 1

            if state.triage_result is not None:
                stats[label]["probs"].append(state.triage_result.malignancy_prob)
                stats[label]["targets"].append(int(row["target"]))

    # ── Report ────────────────────────────────────────────────────────────────
    lines = [
        "# VisiSkin Agent 端到端评测报告",
        "",
        "## 引导选择性",
        "",
        "| 数据集 | 样本数 | 触发追问数 | 追问率 |",
        "|--------|--------|------------|--------|",
    ]

    for label, s in stats.items():
        total = s["total"]
        rate = s["guided"] / total if total > 0 else 0
        lines.append(f"| {label} | {total} | {s['guided']} | {rate:.1%} |")

    lines += ["", "## 分类性能（最终 Triage）", ""]
    lines += ["| 数据集 | AUC-ROC | Accuracy | Sensitivity | Specificity |",
              "|--------|---------|----------|-------------|-------------|"]

    for label, s in stats.items():
        probs = np.array(s["probs"])
        targets = np.array(s["targets"])
        if len(probs) < 2 or targets.sum() == 0:
            lines.append(f"| {label} | N/A | N/A | N/A | N/A |")
            continue
        auc = float(roc_auc_score(targets, probs))
        preds = (probs >= QAD_THRESH).astype(int)
        tp = int(((preds == 1) & (targets == 1)).sum())
        tn = int(((preds == 0) & (targets == 0)).sum())
        fp = int(((preds == 1) & (targets == 0)).sum())
        fn = int(((preds == 0) & (targets == 1)).sum())
        acc = (tp + tn) / len(targets)
        sens = tp / (tp + fn) if (tp + fn) > 0 else float("nan")
        spec = tn / (tn + fp) if (tn + fp) > 0 else float("nan")
        lines.append(f"| {label} | {auc:.3f} | {acc:.3f} | {sens:.3f} | {spec:.3f} |")

    lines += ["", "## 验收判定", ""]
    hq_rate = stats["high_quality"]["guided"] / max(stats["high_quality"]["total"], 1)
    lq_rate = stats["low_quality"]["guided"] / max(stats["low_quality"]["total"], 1)
    passed = lq_rate >= 0.50 and hq_rate <= 0.30
    lines += [
        f"- 低质量图追问率：{lq_rate:.1%}（目标 ≥ 50%）",
        f"- 高质量图追问率：{hq_rate:.1%}（目标 ≤ 30%）",
        f"- 引导选择性测试：{'[PASS]' if passed else '[FAIL]'}",
    ]

    Path(OUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(OUT_FILE).write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n报告已写入 {OUT_FILE}")


if __name__ == "__main__":
    evaluate()
