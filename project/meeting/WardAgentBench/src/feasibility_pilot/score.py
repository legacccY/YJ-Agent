# -*- coding: utf-8 -*-
"""
score.py — 精确匹配 agent 决策 vs 指南 D*，出命门判据
=====================================================
服务哪个 Q（可行性命门）：
  B（四角色分布）是否暴露 A（医生中心单流）没有的、且**公开指南可打分**的失败类？
  是 → 差异化承重可立项；否 → 退 workshop。本脚本**精确匹配**（非 LLM 判自由文本）。

打分口径（护栏：结构化精确匹配）：
  对每条 scenario 的每条件，逐字段（escalate/route_to_role/timing_bin）与 D* 精确相等 → 对。
  parse_ok=False（agent 没吐合法结构化输出）一律记**错**（该字段不匹配）。

B 特有失败类（命门核心）：按 scenario 配对 A/B 同一 D*，分类：
  A_correct_B_wrong : escalate A 对 B 错 —— **分布导致的整合失败**（命门正信号）
  both_correct      : A/B 都对
  both_wrong        : A/B 都错（非分布特异，可能任务本身难/模型弱）
  A_wrong_B_correct : A 错 B 对（分布**帮忙**，反向，需警惕小样本噪声）
  并对 A_correct_B_wrong 子集给失败**子类型**诊断：
    misroute        : escalate 对但 route_to_role 错（错路由——单流无「谁响应」概念，B 独有）
    dropped_concern : concern_injected 的窗、B 错且 A 对（家属/护士早期信号被分布丢弃）
    integration     : 其余（跨角色数值整合失败）

输入（CLI）：
  --scenarios  scenarios.jsonl（含真值 D*，防泄漏地只在打分侧 join）
  --decisions  agent_decisions.csv（run_agent 产出）
  --out        feasibility_result.csv（默认 ./feasibility_result.csv）

输出：feasibility_result.csv，两段：
  段1 per_scenario 明细行，列：
    scenario_id, record, window_idx, true_level, true_route, true_timing,
    concern_injected, red_flag,
    A_escalate, A_route, A_timing, A_parse_ok,
    B_escalate, B_route, B_timing, B_parse_ok,
    A_escalate_correct, B_escalate_correct, A_route_correct, B_route_correct,
    A_timing_correct, B_timing_correct,
    pair_class(both_correct/A_correct_B_wrong/A_wrong_B_correct/both_wrong),
    b_failure_subtype(misroute/dropped_concern/integration/'')
  段2 (同 csv 追加 summary_ 前缀行或另出) → 另出 feasibility_summary.csv：
    metric, condition, value（escalate/route/timing 正确率 by 条件 + 各 pair_class 计数 + 判据）

Windows 规范：pathlib/utf-8。纯 csv/collections，无 pandas 依赖（verifier 可直接 Bash 核）。**主线跑，我不跑。**
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import guideline as G

THIS = Path(__file__).resolve()
PILOT_DIR = THIS.parent


def load_scenarios(path):
    scen = {}
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        s = json.loads(ln)
        scen[s["scenario_id"]] = s
    return scen


def load_decisions(path):
    """agent_decisions.csv -> {scenario_id: {'A': row, 'B': row}}。"""
    dec = defaultdict(dict)
    with Path(path).open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            dec[row["scenario_id"]][row["condition"]] = row
    return dec


def _correct(agent_val, true_val):
    """精确匹配；agent_val 空串（parse 失败/非法）一律错。"""
    return bool(agent_val) and (agent_val == true_val)


def classify_pair(a_esc_ok, b_esc_ok):
    if a_esc_ok and b_esc_ok:
        return "both_correct"
    if a_esc_ok and not b_esc_ok:
        return "A_correct_B_wrong"
    if not a_esc_ok and b_esc_ok:
        return "A_wrong_B_correct"
    return "both_wrong"


def b_failure_subtype(sc, a_row, b_row, b_route_ok):
    """仅对 A_correct_B_wrong 判子类型。"""
    # escalate 对但 route 错 → 错路由（B 独有「谁响应」维度）
    if _correct(b_row.get("escalate", ""), sc["true_level"]) and not b_route_ok:
        return "misroute"
    # 有家属/护士早期信号的窗，B 错 → 早期信号被分布丢弃
    if sc.get("concern_injected"):
        return "dropped_concern"
    return "integration"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=str, default=str(PILOT_DIR / "scenarios.jsonl"))
    ap.add_argument("--decisions", type=str, default=str(PILOT_DIR / "agent_decisions.csv"))
    ap.add_argument("--out", type=str, default=str(PILOT_DIR / "feasibility_result.csv"))
    args = ap.parse_args()

    scen = load_scenarios(args.scenarios)
    dec = load_decisions(args.decisions)
    if not scen or not dec:
        print("[ERR] scenarios 或 decisions 为空。")
        return 2

    detail_fields = [
        "scenario_id", "record", "window_idx", "true_level", "true_route", "true_timing",
        "concern_injected", "red_flag",
        "A_escalate", "A_route", "A_timing", "A_parse_ok",
        "B_escalate", "B_route", "B_timing", "B_parse_ok",
        "A_escalate_correct", "B_escalate_correct",
        "A_route_correct", "B_route_correct",
        "A_timing_correct", "B_timing_correct",
        "pair_class", "b_failure_subtype",
    ]
    detail_rows = []
    # 计数器
    field_correct = {c: Counter() for c in ("A", "B")}  # field -> #correct
    n_eval = 0
    pair_counter = Counter()
    subtype_counter = Counter()

    for sid, sc in scen.items():
        if sid not in dec or "A" not in dec[sid] or "B" not in dec[sid]:
            continue
        a, b = dec[sid]["A"], dec[sid]["B"]
        n_eval += 1

        a_esc_ok = _correct(a.get("escalate", ""), sc["true_level"])
        b_esc_ok = _correct(b.get("escalate", ""), sc["true_level"])
        a_route_ok = _correct(a.get("route_to_role", ""), sc["true_route"])
        b_route_ok = _correct(b.get("route_to_role", ""), sc["true_route"])
        a_time_ok = _correct(a.get("timing_bin", ""), sc["true_timing"])
        b_time_ok = _correct(b.get("timing_bin", ""), sc["true_timing"])

        field_correct["A"]["escalate"] += a_esc_ok
        field_correct["A"]["route"] += a_route_ok
        field_correct["A"]["timing"] += a_time_ok
        field_correct["B"]["escalate"] += b_esc_ok
        field_correct["B"]["route"] += b_route_ok
        field_correct["B"]["timing"] += b_time_ok

        pair_class = classify_pair(a_esc_ok, b_esc_ok)
        pair_counter[pair_class] += 1
        subtype = ""
        if pair_class == "A_correct_B_wrong":
            subtype = b_failure_subtype(sc, a, b, b_route_ok)
            subtype_counter[subtype] += 1

        detail_rows.append({
            "scenario_id": sid, "record": sc["record"], "window_idx": sc["window_idx"],
            "true_level": sc["true_level"], "true_route": sc["true_route"],
            "true_timing": sc["true_timing"],
            "concern_injected": sc["concern_injected"], "red_flag": sc["red_flag"],
            "A_escalate": a.get("escalate", ""), "A_route": a.get("route_to_role", ""),
            "A_timing": a.get("timing_bin", ""), "A_parse_ok": a.get("parse_ok", ""),
            "B_escalate": b.get("escalate", ""), "B_route": b.get("route_to_role", ""),
            "B_timing": b.get("timing_bin", ""), "B_parse_ok": b.get("parse_ok", ""),
            "A_escalate_correct": a_esc_ok, "B_escalate_correct": b_esc_ok,
            "A_route_correct": a_route_ok, "B_route_correct": b_route_ok,
            "A_timing_correct": a_time_ok, "B_timing_correct": b_time_ok,
            "pair_class": pair_class, "b_failure_subtype": subtype,
        })

    if n_eval == 0:
        print("[ERR] 无可配对 scenario（decisions 缺 A 或 B）。")
        return 2

    # 写明细
    out_path = Path(args.out)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=detail_fields)
        w.writeheader()
        w.writerows(detail_rows)
    print(f"[written] {out_path}  ({len(detail_rows)} scenarios)")

    # 写 summary
    def rate(cnt):
        return cnt / n_eval if n_eval else float("nan")

    summary_rows = []
    for cond in ("A", "B"):
        for field in ("escalate", "route", "timing"):
            summary_rows.append({
                "metric": f"{field}_accuracy", "condition": cond,
                "value": round(rate(field_correct[cond][field]), 4),
                "n": n_eval,
            })
    for pc in ("both_correct", "A_correct_B_wrong", "A_wrong_B_correct", "both_wrong"):
        summary_rows.append({"metric": "pair_class_count", "condition": pc,
                             "value": pair_counter.get(pc, 0), "n": n_eval})
    for st in ("misroute", "dropped_concern", "integration"):
        summary_rows.append({"metric": "b_failure_subtype_count", "condition": st,
                             "value": subtype_counter.get(st, 0),
                             "n": pair_counter.get("A_correct_B_wrong", 0)})

    sum_path = out_path.with_name("feasibility_summary.csv")
    with sum_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["metric", "condition", "value", "n"])
        w.writeheader()
        w.writerows(summary_rows)
    print(f"[written] {sum_path}  ({len(summary_rows)} rows)")

    # ---- 命门判据打印 ----
    a_acc = rate(field_correct["A"]["escalate"])
    b_acc = rate(field_correct["B"]["escalate"])
    n_ACBW = pair_counter.get("A_correct_B_wrong", 0)
    n_AWBC = pair_counter.get("A_wrong_B_correct", 0)
    print("\n" + "=" * 62)
    print("命门判据（B 是否暴露 A 无的、指南可打分的失败）")
    print("=" * 62)
    print(f"  n_scenario(配对)         : {n_eval}")
    print(f"  escalate 正确率 A / B    : {a_acc:.3f} / {b_acc:.3f}")
    print(f"  route 正确率    A / B    : {rate(field_correct['A']['route']):.3f} / "
          f"{rate(field_correct['B']['route']):.3f}")
    print(f"  A对B错 (分布致败)        : {n_ACBW}")
    print(f"  A错B对 (分布帮忙,反向)   : {n_AWBC}")
    print(f"  A对B错 失败子类型        : {dict(subtype_counter)}")
    print("-" * 62)
    # 定性判据（阈值待 planner/主线按 STORY 判据表定，这里给方向性读数）
    go = (n_ACBW > n_AWBC) and (n_ACBW >= 1) and (b_acc < a_acc)
    verdict = "GO(方向性): B 存在 A 无的、指南可打分失败" if go else \
              "NO-GO(方向性): 未见 B 特异失败（分布不承重）→ 退 workshop"
    print(f"  方向性判据: {verdict}")
    print("  ⚠️ 这是**方向性**读数（含 mock 会假 NO-GO）；正式判据须 medgemma 后端 + 足量 n +")
    print("     rank_flip_guard 锚不变性通过后，由主线/planner 对 STORY 判据表定 GO/NO-GO。")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
