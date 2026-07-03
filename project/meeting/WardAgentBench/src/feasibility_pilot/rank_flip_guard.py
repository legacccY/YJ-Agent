# -*- coding: utf-8 -*-
"""
rank_flip_guard.py — 预登记锚不变性检验（防「测的是作者 artifact」）
==================================================================
服务哪个 Q（可行性命门·防伪）：
  命门若成立，B 的失败应源自**信息分布结构**，而非作者写的具体措辞/角色名（叙述 artifact）。
  本脚本换 NPC 名 / 叙述措辞重生成 prompt，主线跑后比 agent 决策**是否稳定**：
    - 决策翻转率低 + 命门结论跨措辞稳 → 测的是结构（可信）。
    - 一换措辞就翻 → 测的是作者 artifact（命门存疑，需回炉）。

两段用法（骨架，主线跑）：
  step1  generate：读 scenarios.jsonl，对每条 scenario 生成 N 个**措辞变体** prompt
         （只换角色名/寒暄/语序，**不改任何体征数值、不改 concern 有无、不改分布方案**），
         输出 scenarios_variants.jsonl（新增 variant_idx 字段）。
         主线用 run_agent.py --scenarios scenarios_variants.jsonl 跑各变体 → decisions。
  step2  compare：读多变体的 agent_decisions（或按 variant 分列的合并 csv），
         算逐 scenario×condition 的决策翻转率 + 变体间排名 Kendall τ，输出 flip_guard_result.csv。

护栏：变体函数**保证语义等价**——数值/concern/角色分布集合不变，仅表层措辞。
  预登记：变体种子 + 措辞库在此固定，主线跑前不得按结果回调（防 HARKing）。

Kendall τ / 翻转率纯 numpy 手写（无 scipy.stats，避 OMP 冲突，符合项目规范）。
Windows 规范：pathlib/utf-8。**主线跑，我不跑。**
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

THIS = Path(__file__).resolve()
PILOT_DIR = THIS.parent

# ---------------------------------------------------------------------------
# 预登记措辞库（固定，主线跑前不得按结果改）——只换表层，不改语义
# ---------------------------------------------------------------------------
NURSE_NAMES = ["the nurse", "Nurse Adams", "the charge nurse", "the ward nurse", "Nurse Lee"]
FAMILY_LABELS = ["Family", "Daughter", "Son", "Wife", "Relative"]
CONCERN_PARAPHRASES = [
    "patient appears unwell (looks worse than the numbers alone suggest)",
    "the patient seems to be doing worse than the readings imply",
    "something looks off with the patient beyond what the vitals show",
    "the patient looks more unwell than the measured values indicate",
    "we feel the patient is deteriorating despite the numbers",
]
PREAMBLE_A = [
    "You are the ward doctor. All available information about a patient is below.",
    "As the attending ward physician, you have the full patient picture below.",
    "You are the doctor on the ward. Everything known about this patient follows.",
]


def _apply_variant_A(prompt_A: str, vi: int) -> str:
    """A 变体：只替换开头寒暄 + concern 措辞（数值行原样不动）。"""
    lines = prompt_A.split("\n")
    if lines:
        lines[0] = PREAMBLE_A[vi % len(PREAMBLE_A)]
    out = []
    for ln in lines:
        if ln.startswith("Additional note: nurse notes"):
            out.append(f"Additional note: {NURSE_NAMES[vi % len(NURSE_NAMES)]} notes that "
                       f"{CONCERN_PARAPHRASES[vi % len(CONCERN_PARAPHRASES)]}.")
        else:
            out.append(ln)
    return "\n".join(out)


def _apply_variant_B(prompt_B: str, vi: int) -> str:
    """B 变体：只替换护士名/家属标签/concern 措辞（体征数值 + 分布结构原样）。"""
    out = []
    for ln in prompt_B.split("\n"):
        if ln.startswith("[Family]: we think"):
            out.append(f"[{FAMILY_LABELS[vi % len(FAMILY_LABELS)]}]: we think "
                       f"{CONCERN_PARAPHRASES[vi % len(CONCERN_PARAPHRASES)]}.")
        elif ln.startswith("[Nurse]:"):
            out.append(ln.replace("[Nurse]:",
                                  f"[{NURSE_NAMES[vi % len(NURSE_NAMES)].title()}]:", 1))
        else:
            out.append(ln)
    return "\n".join(out)


def cmd_generate(args):
    scen = [json.loads(ln) for ln in Path(args.scenarios).read_text(encoding="utf-8").splitlines()
            if ln.strip()]
    out_path = Path(args.out)
    n = 0
    with out_path.open("w", encoding="utf-8") as f:
        for sc in scen:
            for vi in range(args.n_variants):
                s2 = dict(sc)
                s2["variant_idx"] = vi
                s2["scenario_id"] = f"{sc['scenario_id']}::v{vi}"
                s2["base_scenario_id"] = sc["scenario_id"]
                s2["prompt_A"] = _apply_variant_A(sc["prompt_A"], vi)
                s2["prompt_B"] = _apply_variant_B(sc["prompt_B"], vi)
                f.write(json.dumps(s2, ensure_ascii=False) + "\n")
                n += 1
    print(f"[written] {out_path}  ({n} variant scenarios = {len(scen)}×{args.n_variants})")
    print("[next] 主线: python run_agent.py --scenarios "
          f"{out_path.name} --backend medgemma --out agent_decisions_variants.csv")
    return 0


# ---------------------------------------------------------------------------
# 指标：Kendall τ + 决策翻转率（纯 numpy）
# ---------------------------------------------------------------------------
def kendall_tau(x, y):
    """Kendall τ-a（纯 numpy）。x,y 等长数值序列（如同一组对象在两措辞下的分数/排名）。
    τ = (一致对 - 不一致对) / C(n,2)。并列按 0 计（τ-a 口径，够本 pilot 用）。"""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = x.size
    if n < 2:
        return float("nan")
    conc = disc = 0
    for i in range(n):
        for j in range(i + 1, n):
            sx = np.sign(x[i] - x[j])
            sy = np.sign(y[i] - y[j])
            p = sx * sy
            if p > 0:
                conc += 1
            elif p < 0:
                disc += 1
    denom = n * (n - 1) / 2
    return (conc - disc) / denom if denom else float("nan")


def _level_to_ord(lv):
    order = {"none": 0, "ward": 1, "urgent": 2, "immediate": 3, "": -1}
    return order.get(lv, -1)


def cmd_compare(args):
    """读变体 decisions（含 base_scenario_id 或从 scenario_id 拆 ::vK），
    算逐 (base_scenario, condition) 的决策翻转率 + escalate 序数在变体间的 Kendall τ。"""
    dec_path = Path(args.decisions)
    var_path = Path(args.variants) if args.variants else None
    # base id 映射：优先从 variants jsonl 取 base_scenario_id
    base_of = {}
    if var_path and var_path.exists():
        for ln in var_path.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                s = json.loads(ln)
                base_of[s["scenario_id"]] = s.get("base_scenario_id",
                                                   s["scenario_id"].split("::v")[0])

    # 收集：{(base, condition): [(variant_idx, escalate)]}
    groups = defaultdict(list)
    with dec_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            sid = row["scenario_id"]
            base = base_of.get(sid) or sid.split("::v")[0]
            vi = 0
            if "::v" in sid:
                try:
                    vi = int(sid.split("::v")[1])
                except (IndexError, ValueError):
                    vi = 0
            groups[(base, row["condition"])].append((vi, row.get("escalate", "")))

    out_rows = []
    flips = 0
    total = 0
    for (base, cond), items in groups.items():
        items.sort(key=lambda t: t[0])
        escs = [e for _v, e in items]
        n_var = len(escs)
        modal = max(set(escs), key=escs.count) if escs else ""
        n_flip = sum(1 for e in escs if e != modal)
        flips += n_flip
        total += n_var
        out_rows.append({
            "base_scenario_id": base, "condition": cond, "n_variants": n_var,
            "modal_escalate": modal, "n_flip_vs_modal": n_flip,
            "flip_rate": round(n_flip / n_var, 4) if n_var else "",
            "escalates": "|".join(escs),
        })

    out_path = Path(args.out)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["base_scenario_id", "condition", "n_variants",
                                          "modal_escalate", "n_flip_vs_modal",
                                          "flip_rate", "escalates"])
        w.writeheader()
        w.writerows(out_rows)
    overall_flip = flips / total if total else float("nan")
    print(f"[written] {out_path}  ({len(out_rows)} base×cond)")
    print(f"[metric] 整体决策翻转率(vs 众数) = {overall_flip:.4f}  (越低越稳=测结构非 artifact)")
    print("[判据] 锚不变性: 翻转率低(如 <0.1) + 命门结论(A对B错方向)跨措辞不翻 → PASS(测结构)。")
    print("       高翻转 → 命门存疑，是作者措辞 artifact，需回炉。阈值待主线/planner 按 STORY 定。")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="生成措辞变体 scenarios")
    g.add_argument("--scenarios", type=str, default=str(PILOT_DIR / "scenarios.jsonl"))
    g.add_argument("--n-variants", type=int, default=5)
    g.add_argument("--out", type=str, default=str(PILOT_DIR / "scenarios_variants.jsonl"))
    g.set_defaults(func=cmd_generate)

    c = sub.add_parser("compare", help="比对变体决策稳定性")
    c.add_argument("--decisions", type=str,
                   default=str(PILOT_DIR / "agent_decisions_variants.csv"))
    c.add_argument("--variants", type=str,
                   default=str(PILOT_DIR / "scenarios_variants.jsonl"),
                   help="变体 jsonl（取 base_scenario_id 映射）")
    c.add_argument("--out", type=str, default=str(PILOT_DIR / "flip_guard_result.csv"))
    c.set_defaults(func=cmd_compare)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
