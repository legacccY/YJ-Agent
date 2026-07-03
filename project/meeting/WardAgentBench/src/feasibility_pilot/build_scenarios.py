# -*- coding: utf-8 -*-
"""
build_scenarios.py — 从真实 mimic3wdb numerics 造 A/B 两条件 scenario
=====================================================================
服务哪个 Q（可行性命门）：
  给 agent **同一批信息**，分布方式不同（A 医生中心单流 vs B 四角色分散），
  是否制造差异化失败？本脚本造场景 + 用 guideline.py 的 D* 打真值标签（确定性，非 LLM）。

护栏（theorist 定，本脚本严格遵守）：
  - 病人状态 seed 自**真实 mimic3wdb numerics**（HR/SpO2/ABPsys/RESP），复用 ks3_pilot 加载器。
  - 真值 D* = guideline.ground_truth()（公开指南 NEWS2 确定函数），**绝不 LLM 生成**。
  - 家属/护士「早期担忧」信号**非循环**派生：锚在**真实未来窗**的指南态——
    仅当下一窗 NEWS2 级别将**升级**时注入 "nurse notes patient appears unwell"。
    这是真实未来指南态的确定函数，不是作者拍脑袋、也不是 LLM 生成。

输入（CLI）：
  --records     record 名清单（每行一条 numerics record；默认 ks3_pilot/records.txt）
  --local-dir   本地已下 MIMIC-III matched 目录（不给则在线 wfdb 只读，pn_dir=matched/1.0）
  --limit       最多取 N 条 record（默认 25）
  --window-min  窗口时长(分钟，默认 30；非重叠切窗)
  --agg         窗内体征聚合法：median(默认)/mean/worst（worst=最偏离正常，最触发）
  --out         输出 jsonl 路径（默认 ./scenarios.jsonl）

输出：scenarios.jsonl（每行一条 scenario，JSON 字段）：
  scenario_id     : str   record::win{k}
  record          : str
  window_idx      : int
  window_min      : int
  agg             : str
  vitals          : dict   窗聚合体征（喂 D* 与 prompt 的同一份）
  true_news2      : int    partial-NEWS2 聚合分
  true_level      : str    D* escalate ∈ {none,ward,urgent,immediate}
  true_route      : str    D* route_to_role ∈ {nurse,doctor,rapid_response}
  true_timing     : str    D* timing_bin
  red_flag        : bool
  missing_params  : list
  future_escalates: bool   下一窗级别是否 > 本窗（家属信号锚点，真实未来指南态）
  concern_injected: bool   是否注入护士/家属早期担忧（== future_escalates）
  prompt_A        : str    医生中心单流 prompt（全信息 + 担忧信号打包给单医生 agent）
  prompt_B        : str    四角色分散 prompt（同信息散给 nurse/family/monitor/doctor 角色）

⚠️ partial-NEWS2 是子集（缺体温/意识/吸氧，见 guideline.py），A/B 同 D* 对比有效。
纯 numpy + wfdb + pandas 无关(用 json)。Windows 规范：pathlib/utf-8/无硬编码盘符。**主线跑，我不跑。**
含 --smoke：只取前 2 条 record 造最小 scenario 集（主线跑，我不跑）。
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

THIS = Path(__file__).resolve()
PILOT_DIR = THIS.parent
KS3_DIR = PILOT_DIR.parent / "ks3_pilot"
# 复用 ks3_pilot 加载器（load_numerics）+ 别名规范化
if str(KS3_DIR) not in sys.path:
    sys.path.insert(0, str(KS3_DIR))

from alarm_derive import load_numerics  # noqa: E402  ks3_pilot 复用
import guideline as G  # noqa: E402

DEFAULT_PN_DIR = "mimic3wdb-matched/1.0"
DEFAULT_RECORDS = KS3_DIR / "records.txt"
VITAL_ORDER = ["HR", "SpO2", "ABPsys", "RESP"]
VITAL_UNITS = {"HR": "bpm", "SpO2": "%", "ABPsys": "mmHg (systolic)", "RESP": "/min"}


# ---------------------------------------------------------------------------
# 窗口聚合：把 1Hz 体征切成 window_min 分钟非重叠窗，每窗算代表体征值
# ---------------------------------------------------------------------------
def _agg_value(arr: np.ndarray, how: str, canon: str) -> float:
    """窗内一条体征的代表值。median 去 artifact；worst=向"更危险"方向取极值。"""
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return float("nan")
    if how == "median":
        return float(np.median(finite))
    if how == "mean":
        return float(np.mean(finite))
    if how == "worst":
        # worst = 最可能触发 NEWS2 的方向：HR/RESP 取偏离 [正常] 最远的极值，
        # SpO2 取最低，ABPsys 取最低（低血压更危险，NEWS2 低端权重高）。
        if canon == "SpO2":
            return float(np.min(finite))
        if canon == "ABPsys":
            return float(np.min(finite))
        # HR / RESP：双向危险，取使 NEWS2 得分最高的一端
        lo, hi = float(np.min(finite)), float(np.max(finite))
        scorer = G._SCORERS[canon]
        return lo if scorer(lo) >= scorer(hi) else hi
    raise ValueError(f"未知聚合法: {how}")


def window_vitals(signals: dict, window_min: int, how: str):
    """把一条 record 的各体征切窗聚合。signals: canon -> (values, fs)。
    返回 list[dict(canon->value)]，按窗顺序；不同体征取最短公共窗数对齐。"""
    win_s = window_min * 60
    per_sig_windows = {}
    n_windows_each = []
    for canon, (values, fs) in signals.items():
        fs = fs or 1.0
        step = max(1, int(round(win_s * fs)))
        v = np.asarray(values, dtype=float)
        n_win = v.size // step
        n_windows_each.append(n_win)
        per_sig_windows[canon] = (v, step, n_win)
    if not n_windows_each:
        return []
    n_common = min(n_windows_each)
    windows = []
    for k in range(n_common):
        wv = {}
        for canon, (v, step, _n) in per_sig_windows.items():
            seg = v[k * step:(k + 1) * step]
            wv[canon] = _agg_value(seg, how, canon)
        windows.append(wv)
    return windows


# ---------------------------------------------------------------------------
# Prompt 构造：A 单流 vs B 四角色分散（同信息，分布不同）
# ---------------------------------------------------------------------------
OUTPUT_SPEC = (
    "Respond with ONLY a JSON object, no other text, with exactly these keys:\n"
    '  "escalate": one of ["none","ward","urgent","immediate"],\n'
    '  "route_to_role": one of ["nurse","doctor","rapid_response"],\n'
    '  "timing_bin": one of ["routine_12h","ward_4to6h","hourly","continuous"].\n'
)

CONCERN_TEXT = "nurse notes patient appears unwell (looks worse than the numbers alone suggest)"


def _fmt_vital(canon, val):
    if val is None or (isinstance(val, float) and val != val):
        return f"{canon}: not available"
    return f"{canon}: {val:.0f} {VITAL_UNITS[canon]}"


def build_prompt_A(vitals: dict, concern: bool) -> str:
    """条件 A：医生中心单流。全部体征 + 担忧信号预整合成一个给单医生 agent 的 prompt。"""
    lines = [
        "You are the ward doctor. All available information about a patient is below.",
        "Decide the escalation using standard early-warning-score practice.",
        "",
        "Current vital signs (window aggregate):",
    ]
    for c in VITAL_ORDER:
        lines.append("  - " + _fmt_vital(c, vitals.get(c)))
    if concern:
        lines.append("")
        lines.append(f"Additional note: {CONCERN_TEXT}.")
    lines.append("")
    lines.append(OUTPUT_SPEC)
    return "\n".join(lines)


def build_prompt_B(vitals: dict, concern: bool) -> str:
    """条件 B：四角色分散。同信息散给 nurse/family/monitor/doctor——
    体征拆到不同角色端，家属报担忧，医生只见摘要；agent 须**跨角色整合 + 路由**才拿全。
    分布方案（固定，防作者调参 artifact）：
      - nurse 端：HR, RESP
      - monitor(仪器) 端：SpO2, ABPsys
      - family 端：早期担忧信号（若 concern）
      - doctor 端：只有一句「请你综合团队信息决策」的摘要，无原始数值。"""
    nurse_vitals = ["HR", "RESP"]
    monitor_vitals = ["SpO2", "ABPsys"]
    lines = [
        "You are coordinating a ward care team. Information is spread across team members.",
        "Integrate ALL of it before deciding; some numbers are only held by one member.",
        "",
        "[Nurse]: I have these readings — "
        + "; ".join(_fmt_vital(c, vitals.get(c)) for c in nurse_vitals) + ".",
        "[Monitor]: bedside monitor shows — "
        + "; ".join(_fmt_vital(c, vitals.get(c)) for c in monitor_vitals) + ".",
    ]
    if concern:
        lines.append(f"[Family]: we think {CONCERN_TEXT}.")
    else:
        lines.append("[Family]: (no additional concern reported).")
    lines.append("[Doctor]: I only have a brief handover summary and no raw numbers; "
                 "please integrate the team's information and decide.")
    lines.append("")
    lines.append("Decide the escalation using standard early-warning-score practice, "
                 "and route to whichever role should respond.")
    lines.append("")
    lines.append(OUTPUT_SPEC)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def process_record(record, args):
    """一条 record -> 若干 scenario dict（每窗一条；末窗无未来窗，future_escalates=False）。"""
    try:
        signals = load_numerics(
            record,
            pn_dir=None if args.local_dir else DEFAULT_PN_DIR,
            local_dir=args.local_dir,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 读取失败 {record}: {e}")
        return []
    if not signals:
        print(f"[warn] {record} 无可用体征信号，跳过")
        return []

    windows = window_vitals(signals, args.window_min, args.agg)
    if len(windows) < 1:
        print(f"[warn] {record} 时长不足一个 {args.window_min}min 窗，跳过")
        return []

    # 先算每窗 D*（真值）
    gts = [G.ground_truth(wv) for wv in windows]
    scenarios = []
    for k, (wv, gt) in enumerate(zip(windows, gts)):
        # 未来锚点：下一窗级别是否升级（非循环，锚真实未来指南态）
        if k + 1 < len(gts):
            future_escalates = (G.ESCALATE_ORDER[gts[k + 1]["escalate"]]
                                > G.ESCALATE_ORDER[gt["escalate"]])
        else:
            future_escalates = False
        concern = bool(future_escalates)
        # vitals 存成可 JSON 的（NaN -> None）
        vitals_json = {c: (None if (isinstance(wv.get(c), float) and wv[c] != wv[c])
                           else wv.get(c)) for c in VITAL_ORDER}
        scenarios.append({
            "scenario_id": f"{record}::win{k}",
            "record": record,
            "window_idx": k,
            "window_min": args.window_min,
            "agg": args.agg,
            "vitals": vitals_json,
            "true_news2": gt["news2_partial_total"],
            "true_level": gt["escalate"],
            "true_route": gt["route_to_role"],
            "true_timing": gt["timing_bin"],
            "red_flag": gt["red_flag"],
            "missing_params": gt["missing_params"],
            "future_escalates": bool(future_escalates),
            "concern_injected": concern,
            "prompt_A": build_prompt_A(wv, concern),
            "prompt_B": build_prompt_B(wv, concern),
        })
    return scenarios


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", type=str, default=str(DEFAULT_RECORDS),
                    help="record 名清单文件（默认 ks3_pilot/records.txt）")
    ap.add_argument("--local-dir", type=str, default="",
                    help="本地已下 MIMIC-III matched 目录（不给则在线 wfdb 只读）")
    ap.add_argument("--limit", type=int, default=25, help="最多取 N 条 record")
    ap.add_argument("--window-min", type=int, default=30, help="窗口时长(分钟)")
    ap.add_argument("--agg", type=str, default="median",
                    choices=["median", "mean", "worst"], help="窗内体征聚合法")
    ap.add_argument("--out", type=str, default=str(PILOT_DIR / "scenarios.jsonl"))
    ap.add_argument("--smoke", type=int, default=0, help="烟测：>0 只取前 2 条 record")
    args = ap.parse_args()
    args.local_dir = args.local_dir or None
    if args.smoke:
        args.limit = 2

    recs = [ln.strip() for ln in Path(args.records).read_text(encoding="utf-8").splitlines()
            if ln.strip()]
    recs = recs[: args.limit] if args.limit > 0 else recs
    if not recs:
        print("[ERR] records 清单为空。")
        return 2

    print(f"[info] 处理 {len(recs)} 条 record，窗 {args.window_min}min，聚合 {args.agg}")
    all_sc = []
    for i, rec in enumerate(recs):
        print(f"  [{i+1}/{len(recs)}] {rec}")
        all_sc.extend(process_record(rec, args))

    if not all_sc:
        print("[ERR] 无 scenario 产出（record 全读取失败或时长不足）。")
        return 2

    out_path = Path(args.out)
    with out_path.open("w", encoding="utf-8") as f:
        for sc in all_sc:
            f.write(json.dumps(sc, ensure_ascii=False) + "\n")
    print(f"[written] {out_path}  ({len(all_sc)} scenarios)")

    # 分布快照（供主线一眼看真值分布是否有梯度，非全 none 才有得测）
    from collections import Counter
    lvl = Counter(s["true_level"] for s in all_sc)
    n_concern = sum(1 for s in all_sc if s["concern_injected"])
    print(f"[dist] true_level: {dict(lvl)}")
    print(f"[dist] concern_injected(未来升级锚): {n_concern}/{len(all_sc)}")
    print("[note] 若 true_level 几乎全 'none' 或全同级 → 无梯度，命门测不出，"
          "需调 --agg worst / 换 window-min / 换 record 子集扩大分布。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
