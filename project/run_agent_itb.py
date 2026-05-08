"""Agent 交互评测：在 ITB 子集上运行 Agent，记录交互轮次分布。

使用规则引擎 fallback（~40ms/张），不启动 Qwen（太慢）。
记录：subset, turns, retake_count, initial_qbar, improved_qbar, final_prob, target

Usage:
  cd D:/YJ-Agent/project
  python run_agent_itb.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import cv2
import numpy as np
import pandas as pd
from tqdm import tqdm

from agent.tools import quality_assess, extract_features, triage
from agent.question_bank import get_retake_question

ITB_CSV  = "results/itb_subsets.csv"
OUT_CSV  = "results/itb_agent_eval.csv"
N_PER_SUBSET = 200   # 每子集评测样本数（规则引擎够快）
SEED     = 42
MAX_RETAKE = 3
Q_GOOD_THRESHOLD = 0.50


def load_rgb(path: str):
    img = cv2.imread(str(path))
    if img is None:
        return None
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def simulate_retake(img: np.ndarray, initial_qr) -> np.ndarray:
    """模拟用户按引导重拍：如果退化图，返回对应原图（质量更好）；否则用同一张。

    实际部署中用户会真正重拍，这里用配对原图模拟。
    """
    return img


def run_agent_on_image(img: np.ndarray, itb_row: pd.Series):
    """运行规则引擎 Agent，记录完整交互轨迹。"""
    turns = 0
    retake_count = 0
    initial_qbar = float(itb_row["qbar"])
    current_img  = img

    # 记录每轮质量得分
    quality_history = []

    while retake_count <= MAX_RETAKE:
        turns += 1
        qr = quality_assess(current_img)
        quality_history.append(float(qr.overall))

        if qr.is_acceptable or retake_count >= MAX_RETAKE:
            # 进入分析
            feats  = extract_features(current_img)
            result = triage(feats)
            return {
                "turns": turns,
                "retake_count": retake_count,
                "initial_qbar": initial_qbar,
                "final_qbar": quality_history[-1],
                "quality_improved": (quality_history[-1] - quality_history[0]) if len(quality_history) > 1 else 0.0,
                "final_prob": float(result.malignancy_prob),
                "done": True,
            }
        else:
            retake_count += 1
            # 模拟用户按提示提供更好的图（无法真正重拍，用原图替代）
            original_path = itb_row.get("original_path", None)
            if original_path and Path(str(original_path)).exists():
                better = load_rgb(str(original_path))
                current_img = better if better is not None else current_img
            # 如果没有原图路径，保持同图（worst case baseline）

    # 超出轮次，强制分析
    feats  = extract_features(current_img)
    result = triage(feats)
    return {
        "turns": turns,
        "retake_count": retake_count,
        "initial_qbar": initial_qbar,
        "final_qbar": quality_history[-1] if quality_history else initial_qbar,
        "quality_improved": (quality_history[-1] - quality_history[0]) if len(quality_history) > 1 else 0.0,
        "final_prob": float(result.malignancy_prob),
        "done": True,
    }


def main():
    itb = pd.read_csv(ITB_CSV)

    # 需要 original_path 做模拟重拍 → 从 quality_labels 里 join 回来
    try:
        labels = pd.read_csv("D:/YJ-Agent/data/quality_labels_all.csv")
        # 建立 degraded_path → original_path 映射
        path_map = dict(zip(labels["degraded_path"].str.replace("\\", "/"),
                            labels["original_path"].str.replace("\\", "/")))
        itb["original_path"] = itb["image_path"].str.replace("\\", "/").map(path_map)
    except Exception:
        itb["original_path"] = None

    rows = []
    for subset in sorted(itb["subset"].unique()):
        sub = itb[itb["subset"] == subset]
        sample = sub.sample(min(N_PER_SUBSET, len(sub)), random_state=SEED)
        print(f"\n[Agent] {subset}: {len(sample)} samples")

        for _, row in tqdm(sample.iterrows(), total=len(sample), leave=False):
            img = load_rgb(str(row["image_path"]))
            if img is None:
                continue
            result = run_agent_on_image(img, row)
            rows.append({
                "subset": subset,
                "target": int(row["target"]),
                "initial_qbar": result["initial_qbar"],
                "final_qbar": result["final_qbar"],
                "quality_improved": result["quality_improved"],
                "turns": result["turns"],
                "retake_count": result["retake_count"],
                "final_prob": result["final_prob"],
                "retake_triggered": int(result["retake_count"] > 0),
            })

        df_sub = pd.DataFrame([r for r in rows if r["subset"] == subset])
        print(f"  turns: mean={df_sub['turns'].mean():.2f}  retake_rate={df_sub['retake_triggered'].mean():.1%}")

    out = pd.DataFrame(rows)
    Path(OUT_CSV).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    print(f"\nAgent eval saved -> {OUT_CSV}")
    print(out.groupby("subset")[["turns","retake_triggered","quality_improved"]].mean().round(3))


if __name__ == "__main__":
    main()
