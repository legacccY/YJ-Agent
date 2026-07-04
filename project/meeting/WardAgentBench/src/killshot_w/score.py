# -*- coding: utf-8 -*-
"""
score.py — join 模型判定 ↔ 专家金标，出准确率 + naive 基线 + 对照图
================================================================
服务哪个 §/lever：路 W' $5 kill-shot 判据。把 raw_calls.jsonl 的模型 TRUE/FALSE 与
  专家金标 join，算：总准确率 + 逐类 + 逐表征 + 逐模型 + 逐(模型×表征)，并算
  **naive 基线（全判多数类）**准确率。产长表 CSV + 汇总 CSV + 三参照线对照图。

判据方向（lever）：若前沿 MLLM 准确率 ≈ naive / chance（且远低于文献参照线），
  即「MLLM 读原始波形判警报真假**失败**」的初步证据。**GO/NO-GO 阈值由 planner/主线
  按 ACCEPTANCE 定，本脚本只出客观读数，不擅自下裁决。**

护栏（R1）：所有数字直接由 raw_calls.jsonl 算，CSV 可 Bash 核。ERROR/UNPARSED 计错
  （保守）并单列 parse_rate。参照线 0.8139/0.96 = **引用值**（图注标口径不同，R2）。

输入：RESULTS_DIR/raw_calls.jsonl。
输出：RESULTS_DIR/killshot_results.csv（长表）、summary.csv、killshot_accuracy.png。

Windows 规范：pathlib、utf-8、matplotlib Agg、英文图标签。我不跑代码，交主线跑。
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def load_calls(jsonl_path):
    rows = []
    p = Path(jsonl_path)
    if not p.exists():
        return rows
    for ln in p.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return rows


def excerpt(text, n=200):
    """单行化 + 截断，供长表存证（不破 CSV）。"""
    if not text:
        return ""
    s = " ".join(str(text).split())
    return s[:n]


def is_correct(verdict, gold):
    return int(verdict in ("TRUE", "FALSE") and verdict == gold)


def acc(rows):
    """准确率（ERROR/UNPARSED 计错，分母=全部）。返回 (accuracy, n, parse_rate)。"""
    if not rows:
        return float("nan"), 0, float("nan")
    n = len(rows)
    n_correct = sum(is_correct(r["verdict"], r["expert_label"]) for r in rows)
    n_parsed = sum(1 for r in rows if r["verdict"] in ("TRUE", "FALSE"))
    return n_correct / n, n, n_parsed / n


def naive_majority_accuracy(calls):
    """
    naive 基线：全判多数类。多数类由**被评记录的金标**定（每条记录一份金标）。
    accuracy = max(n_true, n_false) / n_records。
    """
    gold_by_rec = {}
    for r in calls:
        gold_by_rec[r["record_id"]] = r["expert_label"]
    labels = list(gold_by_rec.values())
    if not labels:
        return float("nan"), "", 0
    n_true = labels.count("TRUE")
    n_false = labels.count("FALSE")
    n = len(labels)
    maj = "TRUE" if n_true >= n_false else "FALSE"
    return max(n_true, n_false) / n, maj, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", type=str, default=str(C.RESULTS_DIR / C.RAW_CALLS_JSONL))
    args = ap.parse_args()

    C.ensure_dirs()
    calls = load_calls(args.jsonl)
    if not calls:
        print(f"[ERR] {args.jsonl} 空或不存在，先跑 run_models.py。")
        return 2

    # ---- 长表 killshot_results.csv ----
    long_fields = ["record_id", "alarm_type", "expert_label", "representation",
                   "model", "model_verdict", "correct", "raw_response_excerpt"]
    long_rows = []
    for r in calls:
        long_rows.append({
            "record_id": r["record_id"],
            "alarm_type": r["alarm_type"],
            "expert_label": r["expert_label"],
            "representation": r["representation"],
            "model": r["model"],
            "model_verdict": r["verdict"],
            "correct": is_correct(r["verdict"], r["expert_label"]),
            "raw_response_excerpt": excerpt(r.get("raw_response", "")),
        })
    long_csv = C.RESULTS_DIR / C.RESULTS_CSV
    with long_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=long_fields)
        w.writeheader()
        w.writerows(long_rows)
    print(f"[written] {long_csv}  ({len(long_rows)} rows)")

    # ---- 汇总 summary.csv ----
    summary_fields = ["scope_type", "scope", "n", "accuracy", "parse_rate"]
    summary = []

    def add(scope_type, scope, rows):
        a, n, pr = acc(rows)
        summary.append({"scope_type": scope_type, "scope": scope, "n": n,
                        "accuracy": round(a, 4) if n else "",
                        "parse_rate": round(pr, 4) if n else ""})

    add("overall", "ALL", calls)
    # 逐类
    by_type = defaultdict(list)
    for r in calls:
        by_type[r["alarm_type"]].append(r)
    for t in C.ALARM_TYPES:
        if by_type.get(t):
            add("alarm_type", t, by_type[t])
    # 逐表征
    by_rep = defaultdict(list)
    for r in calls:
        by_rep[r["representation"]].append(r)
    for rep in C.REPRESENTATIONS:
        if by_rep.get(rep):
            add("representation", rep, by_rep[rep])
    # 逐模型
    by_model = defaultdict(list)
    for r in calls:
        by_model[r["model"]].append(r)
    for mname in sorted(by_model):
        add("model", mname, by_model[mname])
    # 逐 (模型×表征)
    by_mr = defaultdict(list)
    for r in calls:
        by_mr[(r["model"], r["representation"])].append(r)
    for (mname, rep) in sorted(by_mr):
        add("model_x_representation", f"{mname}|{rep}", by_mr[(mname, rep)])

    # naive 基线
    naive_acc, maj, n_rec = naive_majority_accuracy(calls)
    summary.append({"scope_type": "baseline", "scope": f"naive_majority({maj})",
                    "n": n_rec, "accuracy": round(naive_acc, 4), "parse_rate": ""})
    # 引用参照线（非自测，标注）
    for lbl, val in C.REF_LINES.items():
        summary.append({"scope_type": "reference_cited", "scope": lbl,
                        "n": "", "accuracy": val, "parse_rate": ""})

    sum_csv = C.RESULTS_DIR / C.SUMMARY_CSV
    with sum_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=summary_fields)
        w.writeheader()
        w.writerows(summary)
    print(f"[written] {sum_csv}  ({len(summary)} rows)")

    # 控制台打印关键读数
    print("\n" + "=" * 64)
    print("路 W' $5 kill-shot 读数（客观，不含裁决）")
    print("=" * 64)
    oa, on, opr = acc(calls)
    print(f"  总准确率        : {oa:.3f}  (n={on}, parse_rate={opr:.3f})")
    print(f"  naive 基线(多数类={maj}) : {naive_acc:.3f}  (n_records={n_rec})")
    print(f"  引用参照线      : " + ", ".join(f"{k}={v}" for k, v in C.REF_LINES.items()))
    print("  逐模型×表征准确率:")
    for (mname, rep) in sorted(by_mr):
        a, n, pr = acc(by_mr[(mname, rep)])
        print(f"    {mname:16s} | {rep:5s} : {a:.3f} (n={n}, parse={pr:.2f})")
    print("=" * 64)

    # ---- 对照条形图 ----
    plot_accuracy(by_mr, naive_acc, maj)
    return 0


def plot_accuracy(by_mr, naive_acc, maj):
    """模型×表征分组条形图 + naive / 0.8139 / 0.96 三参照线。"""
    models = sorted({m for (m, _rep) in by_mr})
    reps = C.REPRESENTATIONS
    x = np.arange(len(models))
    width = 0.8 / max(1, len(reps))
    colors = {"text": "#4C72B0", "image": "#DD8452"}

    fig, ax = plt.subplots(figsize=(max(7, 1.6 * len(models) + 3), 5))
    for j, rep in enumerate(reps):
        vals = []
        for m in models:
            a, _n, _pr = acc(by_mr.get((m, rep), []))
            vals.append(a if a == a else 0.0)  # NaN->0 画图
        ax.bar(x + j * width - (len(reps) - 1) * width / 2, vals, width,
               label=f"representation: {rep}",
               color=colors.get(rep, None), edgecolor="black", linewidth=0.5)

    # 参照线：naive（现算）+ 引用值
    ax.axhline(naive_acc, color="grey", linestyle="--", linewidth=1.3,
               label=f"naive majority ({maj}) = {naive_acc:.3f}")
    ax.axhline(0.5, color="lightgrey", linestyle=":", linewidth=1.0,
               label="chance = 0.50")
    ref_styles = [("--", "#2CA02C"), ("--", "#9467BD")]
    for (lbl, val), (ls, col) in zip(C.REF_LINES.items(), ref_styles):
        ax.axhline(val, color=col, linestyle=ls, linewidth=1.3, label=lbl)

    ax.set_xticks(x)
    ax.set_xticklabels(models, rotation=15, ha="right")
    ax.set_ylabel("Accuracy (true/false vs expert gold)")
    ax.set_ylim(0, 1.0)
    ax.set_title("Frontier MLLM: ICU alarm true/false from raw waveform\n"
                 "(PhysioNet/CinC 2015, N kill-shot subset)")
    ax.legend(loc="lower right", fontsize=8, framealpha=0.9)
    # 图注：参照线口径提醒（R2）
    fig.text(0.01, 0.005,
             "Ref lines 0.8139 (PhysioNet2015 champion, weighted score) & 0.96 (VTaC CNN) "
             "are CITED literature values on full sets; different scoring/scope than this "
             "subset accuracy. Shown for magnitude reference only.",
             fontsize=6, color="dimgray")
    fig.tight_layout(rect=[0, 0.03, 1, 1])
    out_png = C.RESULTS_DIR / C.PLOT_PNG
    fig.savefig(str(out_png), dpi=150)
    plt.close(fig)
    print(f"[written] {out_png}")


if __name__ == "__main__":
    sys.exit(main())
