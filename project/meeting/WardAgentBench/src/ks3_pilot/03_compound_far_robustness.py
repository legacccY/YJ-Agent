# -*- coding: utf-8 -*-
"""
03_compound_far_robustness.py — Q2：复合 FAR 跨阈值族稳健性
==========================================================
回答哪个 Q：
  - Q2（部分）：复合误报率在 **≥2-3 组合理阈值族**下是否稳健（换阈值不翻）？
    用**波形弱代理**（持续生理紊乱=真 vs 短暂 artifact=假，见 alarm_derive.label_event_bins）
    给每个派生告警定真/假，再算：
      * 单告警 FAR（假事件 / 全事件）
      * 复合 FAR（共触发窗中"全部构成告警皆为假"的窗 / 共触发窗）
    跨 default/conservative/liberal 三族比较，检验复合误报现象换阈值是否翻转。

前置：同 02（需 mimic3wdb-matched 可读；gated 则 Q2 需 CITI，见 report）。
输入：同 02（--records 清单 或 --local-dir 本地目录）。
输出：compound_far.csv，列：
      threshold_family, n_records, n_single_events, n_single_false, single_far,
      n_cotrigger_windows, n_compound_false_windows, compound_far,
      expected_compound_far_indep, observed_over_expected_ratio,
      weak_proxy_persist_s
      （每阈值族一行，跨族看 compound_far 是否同量级/不翻）

命门 C2（联合校准有没有价值 —— 依赖是否导致超额复合误报）：
  新增「独立可加基线」对照 `expected_compound_far_indep`。
  统计模型 + 假设（全部显式，供 verifier 核）：
    * 观测复合 FAR = P(共触发窗内全部构成告警皆假 | 该窗共触发)，实测联合量。
    * 独立基线：**假设各告警器在同一窗内的「真/假状态」跨告警器相互独立**，则
        P(全假) = ∏_{k∈S} p_k，  S = 该窗活跃告警集，p_k = 告警 k 的边际窗级假报率。
      p_k = (告警 k 活跃且窗内无 true bin 的窗数) / (告警 k 活跃的窗数)，
        跨全部 record 估计的边际率（窗级口径，与复合定义同一口径，避免事件级/窗级混用）。
      逐共触发窗按其真实活跃集 S 取积，再对全部共触发窗求均值 -> expected_compound_far_indep
        （**组成匹配**：不是简单全局 far^2，而是按每个窗真实活跃了哪几类算积，更贴实测）。
    * observed_over_expected_ratio = observed_compound_far / expected_compound_far_indep。
  判据（planner/主线定显著性阈）：
    - ratio 显著 >1（实测复合误报超独立预期）= 假报跨告警器同现/依赖导致超额 -> **C2 GO**
      （naive 独立 FDR/Bonferroni 会低估联合误报 -> 依赖稳健联合校准有正当动机）。
    - ratio ≈ 1 = 复合误报可加/独立近似成立 = 联合校准无增量价值 -> C2 塌。
  ⚠️ 独立基线是「零依赖对照」不是真值；边际率 p_k 本身受占位阈值影响 -> ratio 为方向性证据，
     阈值锁定后才定量。基线假设「窗级真/假状态跨告警器独立」= 待被数据证伪的 null。

⚠️ R8：真/假为**弱代理派生**非专家标注，稿中必声明；完整结局代理需 CITI matched 临床结局。
   阈值为占位 TODO（见 alarm_thresholds.py）→ 绝对 FAR 待阈值锁定；**稳健性方向**先看。
纯 numpy + wfdb + pandas。Windows 规范：pathlib/utf-8/无硬编码盘符。主线跑。含 --smoke。
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from alarm_thresholds import VITAL_THRESHOLD_FAMILIES, COTRIGGER_WINDOW_S, WEAK_PROXY_PERSIST_S
from alarm_derive import (
    load_numerics,
    derive_alarm_timelines,
    extract_events,
    label_event_bins,
)

THIS = Path(__file__).resolve()
OUT_DIR = THIS.parent
DEFAULT_PN_DIR = "mimic3wdb-matched/1.0"


def get_record_list(args):
    if args.records:
        recs = [ln.strip() for ln in Path(args.records).read_text(encoding="utf-8").splitlines() if ln.strip()]
        return recs[: args.limit] if args.limit > 0 else recs
    try:
        import wfdb
        recs = wfdb.get_record_list(DEFAULT_PN_DIR)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 在线取 RECORDS 失败({e})，用 --records 传清单。")
        return []
    return recs[: args.limit] if args.limit > 0 else recs


def analyze_record_family(signals, fam, persist_s, grid_dt_s=1.0):
    """
    对一条 record + 一个阈值族：派生告警 -> 弱代理定真假 -> 累计单/复合 FAR 计数。
    返回 dict 计数（供跨 record 累加）：
      n_single_events, n_single_false, n_cotrigger_windows, n_compound_false_windows
    C2 独立基线附加返回：
      per_type_active_win: dict 体征名 -> 该体征活跃的窗数（任一窗，含单活跃）
      per_type_false_win:  dict 体征名 -> 该体征活跃且窗内无 true bin 的窗数（边际窗级假报分子）
      cotrig_set_counts:   dict 活跃集(tuple, 排序) -> 该组成的共触发窗数（供组成匹配的独立积）
    """
    timelines = derive_alarm_timelines(signals, fam)
    if not timelines:
        return None

    # 统一到公共时长的 bin 栅格 + 逐体征真假标签
    durs = [active.size / fs if fs else active.size for (active, fs) in timelines.values()]
    total_s = min(durs) if durs else 0.0
    n_bins = int(np.floor(total_s / grid_dt_s))
    if n_bins <= 0:
        return None

    types = sorted(timelines.keys())
    lab_mat = np.full((len(types), n_bins), -1, dtype=np.int8)  # -1 inact / 0 false / 1 true
    n_single_events = 0
    n_single_false = 0
    for k, canon in enumerate(types):
        active, fs = timelines[canon]
        events = extract_events(active, fs, grid_dt_s=grid_dt_s)
        # 裁到公共时长
        events = [e for e in events if e["start_bin"] < n_bins]
        n_single_events += len(events)
        lab = label_event_bins(n_bins, events, persist_s, grid_dt_s=grid_dt_s)
        lab_mat[k, :] = lab
        # 单告警 FAR：事件级，dur < persist -> false
        persist_bins = max(1, int(round(persist_s / grid_dt_s)))
        for e in events:
            if (e["end_bin"] - e["start_bin"]) < persist_bins:
                n_single_false += 1

    # 复合：滑窗 >=2 类活跃；窗内"全部活跃类只含 false bin"记复合假
    win = max(1, int(round(COTRIGGER_WINDOW_S / grid_dt_s)))
    n_windows = max(0, n_bins - win + 1)
    n_cotrig = 0
    n_compound_false = 0
    # C2 独立基线：每类窗级边际假报率（分母=活跃窗、分子=活跃且窗内全假）+ 共触发窗组成计数
    per_type_active_win = {c: 0 for c in types}
    per_type_false_win = {c: 0 for c in types}
    cotrig_set_counts = {}
    for start in range(n_windows):
        block = lab_mat[:, start:start + win]        # (n_types, win)
        active_per_type = (block >= 0).any(axis=1)   # 该类窗内是否活跃
        n_active_types = int(active_per_type.sum())
        # 边际窗级假报：对**每个活跃类**（不论单/共触发）累计，得独立假设下的 p_k
        # per-type "窗内视为假" = 该类活跃但窗内无 true bin
        type_false_flag = {}
        for k in range(len(types)):
            if not active_per_type[k]:
                continue
            per_type_active_win[types[k]] += 1
            is_false = not bool((block[k] == 1).any())
            type_false_flag[k] = is_false
            if is_false:
                per_type_false_win[types[k]] += 1
        if n_active_types < 2:
            continue
        n_cotrig += 1
        active_set = tuple(types[k] for k in range(len(types)) if active_per_type[k])
        cotrig_set_counts[active_set] = cotrig_set_counts.get(active_set, 0) + 1
        # 观测复合假：全部活跃类窗内皆假（无任一 true）
        all_false = all(type_false_flag[k] for k in range(len(types)) if active_per_type[k])
        if all_false:
            n_compound_false += 1

    return {
        "n_single_events": n_single_events,
        "n_single_false": n_single_false,
        "n_cotrigger_windows": n_cotrig,
        "n_compound_false_windows": n_compound_false,
        "per_type_active_win": per_type_active_win,
        "per_type_false_win": per_type_false_win,
        "cotrig_set_counts": cotrig_set_counts,
    }


def expected_compound_far_independent(per_type_active_win, per_type_false_win, cotrig_set_counts):
    """
    C2 独立可加基线：在「各告警器窗级真/假状态相互独立」假设下，预期复合误报率。
      p_k = per_type_false_win[k] / per_type_active_win[k]  （边际窗级假报率，跨全部 record）
      逐共触发窗按其真实活跃集 S 取积 ∏_{k∈S} p_k，再按组成计数加权求均值。
    返回 (expected_compound_far_indep, total_cotrig, per_type_far dict)。
    无有效共触发窗 -> (nan, 0, {})。某类活跃窗数为 0 -> 其 p_k 不定，含它的窗积记 nan（跳过）。
    """
    per_type_far = {}
    for t, n_act in per_type_active_win.items():
        per_type_far[t] = (per_type_false_win.get(t, 0) / n_act) if n_act > 0 else float("nan")
    total = sum(cotrig_set_counts.values())
    if total <= 0:
        return float("nan"), 0, per_type_far
    exp_sum = 0.0
    used = 0
    for active_set, cnt in cotrig_set_counts.items():
        prod = 1.0
        ok = True
        for t in active_set:
            f = per_type_far.get(t, float("nan"))
            if f != f:  # NaN -> 该窗积不可算，跳过（不计入均值）
                ok = False
                break
            prod *= f
        if ok:
            exp_sum += cnt * prod
            used += cnt
    if used <= 0:
        return float("nan"), total, per_type_far
    # 用可算窗的加权均值（分母=可算窗数，与 observed 口径对齐时须一致，见下打印说明）
    return exp_sum / used, total, per_type_far


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", type=str, default="")
    ap.add_argument("--local-dir", type=str, default="")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--families", type=str, default="default,conservative,liberal")
    ap.add_argument("--persist-s", type=float, default=WEAK_PROXY_PERSIST_S,
                    help="弱代理：持续紊乱达此秒数判真（TODO 核合理值）")
    ap.add_argument("--smoke", type=int, default=0)
    args = ap.parse_args()
    args.local_dir = args.local_dir or None

    families = [f.strip() for f in args.families.split(",") if f.strip()]
    for f in families:
        if f not in VITAL_THRESHOLD_FAMILIES:
            print(f"[ERR] 未知阈值族: {f}")
            return 2
    if args.smoke:
        args.limit = 2

    records = get_record_list(args)
    if not records:
        print("[ERR] 无 record 可处理（同 02：需 matched 开放 + --records/--local-dir）。")
        return 2

    # 每族累加计数（+ C2 独立基线用的边际率分子分母 + 共触发窗组成计数）
    acc = {f: {"n_records": 0, "n_single_events": 0, "n_single_false": 0,
               "n_cotrigger_windows": 0, "n_compound_false_windows": 0,
               "per_type_active_win": {}, "per_type_false_win": {},
               "cotrig_set_counts": {}} for f in families}

    for i, rec in enumerate(records):
        print(f"  [{i+1}/{len(records)}] {rec}")
        try:
            signals = load_numerics(
                rec,
                pn_dir=None if args.local_dir else DEFAULT_PN_DIR,
                local_dir=args.local_dir,
            )
        except Exception as e:  # noqa: BLE001
            print(f"[warn] 读取失败 {rec}: {e}")
            continue
        if not signals:
            continue
        for fam in families:
            res = analyze_record_family(signals, fam, args.persist_s)
            if res is None:
                continue
            acc[fam]["n_records"] += 1
            for k in ("n_single_events", "n_single_false",
                      "n_cotrigger_windows", "n_compound_false_windows"):
                acc[fam][k] += res[k]
            # C2: 累加边际窗级假报分子/分母（按体征名）+ 共触发窗组成计数
            for t, v in res["per_type_active_win"].items():
                acc[fam]["per_type_active_win"][t] = acc[fam]["per_type_active_win"].get(t, 0) + v
            for t, v in res["per_type_false_win"].items():
                acc[fam]["per_type_false_win"][t] = acc[fam]["per_type_false_win"].get(t, 0) + v
            for s, v in res["cotrig_set_counts"].items():
                acc[fam]["cotrig_set_counts"][s] = acc[fam]["cotrig_set_counts"].get(s, 0) + v

    rows = []
    for fam in families:
        a = acc[fam]
        single_far = (a["n_single_false"] / a["n_single_events"]) if a["n_single_events"] else float("nan")
        compound_far = (a["n_compound_false_windows"] / a["n_cotrigger_windows"]) if a["n_cotrigger_windows"] else float("nan")
        # C2 独立基线 + 实测/预期比
        exp_far, _tot, _fars = expected_compound_far_independent(
            a["per_type_active_win"], a["per_type_false_win"], a["cotrig_set_counts"])
        if compound_far == compound_far and exp_far == exp_far and exp_far > 0:
            ratio = compound_far / exp_far
        else:
            ratio = float("nan")
        rows.append({
            "threshold_family": fam,
            "n_records": a["n_records"],
            "n_single_events": a["n_single_events"],
            "n_single_false": a["n_single_false"],
            "single_far": round(single_far, 6) if single_far == single_far else "",
            "n_cotrigger_windows": a["n_cotrigger_windows"],
            "n_compound_false_windows": a["n_compound_false_windows"],
            "compound_far": round(compound_far, 6) if compound_far == compound_far else "",
            "expected_compound_far_indep": round(exp_far, 6) if exp_far == exp_far else "",
            "observed_over_expected_ratio": round(ratio, 4) if ratio == ratio else "",
            "weak_proxy_persist_s": args.persist_s,
        })

    df = pd.DataFrame(rows)
    out_csv = OUT_DIR / "compound_far.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"[written] {out_csv}")
    print(df.to_string(index=False))

    # ---- Q2 稳健性判据 ----
    cf = [r["compound_far"] for r in rows if isinstance(r["compound_far"], float)]
    if len(cf) >= 2:
        spread = max(cf) - min(cf)
        print(f"\n[Q2] compound_far 跨族: min={min(cf):.4f} max={max(cf):.4f} spread={spread:.4f}")
        print("     判据（planner/主线定阈）：换族不翻（同量级、不从'显著>0'掉到'~0'）-> Q2 GO。")
        print("     ⚠️ 阈值为占位 TODO -> 绝对值待锁定；此处先看方向是否一致。")
    else:
        print("\n[Q2] 有效阈值族 <2，无法比较稳健性（检查数据/阈值族）。")

    # ---- C2 命门：依赖是否导致超额复合误报（observed vs independent-expected）----
    print("\n[C2] 复合误报：实测 vs 独立可加基线（依赖有没有让联合误报超额）")
    print("     独立基线假设：各告警器窗级真/假状态相互独立 -> P(全假)=∏ p_k（组成匹配加权均值）")
    any_ratio = False
    for r in rows:
        obs = r["compound_far"]
        exp = r["expected_compound_far_indep"]
        rat = r["observed_over_expected_ratio"]
        if isinstance(rat, float):
            any_ratio = True
            print(f"     {r['threshold_family']:<12} observed={obs}  expected_indep={exp}  "
                  f"ratio={rat}  (n_cotrig={r['n_cotrigger_windows']})")
        else:
            print(f"     {r['threshold_family']:<12} observed={obs}  expected_indep={exp}  ratio=NA")
    if any_ratio:
        print("     判据（planner/主线定显著性阈）：")
        print("       ratio 显著 >1 -> 实测复合误报超独立预期 = 依赖导致超额 -> C2 GO"
              "（naive 独立校准低估联合误报，依赖稳健联合校准有动机）。")
        print("       ratio ≈ 1     -> 复合误报可加/独立近似成立 = 联合校准无增量 -> C2 塌。")
        print("     ⚠️ 独立基线是零依赖对照非真值；p_k 受占位阈值影响 -> ratio 为方向性证据，"
              "阈值锁定后定量。")
    else:
        print("     无有效 ratio（共触发窗不足或边际率不可算）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
