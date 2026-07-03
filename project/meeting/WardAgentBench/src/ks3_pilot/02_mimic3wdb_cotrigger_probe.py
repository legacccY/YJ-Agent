# -*- coding: utf-8 -*-
"""
02_mimic3wdb_cotrigger_probe.py — Q1 核心命门：多告警共触发频率 + 相关
=====================================================================
回答哪个 Q：
  - Q1（核心命门）：多告警是否**真以有意义频率 + 相关性共触发**？
    对一批 MIMIC-III Waveform (Matched) numerics record，按标准监护阈值派生
    HR/SpO2/ABP/RESP 阈值告警，统计"≥2 类告警在同一时间窗共活跃"的窗数/占比
    + 告警类型间两两 phi 相关。共触发频繁且相关明显 -> Q1 GO。

前置：00_check_access.py 判定 mimic3wdb-matched 是否开放。
      开放 -> 可直接在线/本地跑；gated -> 本脚本无数据可跑（Q1 需 CITI，见 report）。
输入：一批 record 名（--records 文件，每行一条）或默认在线取 RECORDS 前 N 条。
      pn_dir 默认 'mimic3wdb-matched/1.0'（在线只读）；或 --local-dir 指本地已下目录。
输出：cotrigger_stats.csv，列：
      record, family, duration_h, n_types_present,
      n_alarm_bins_HR, n_alarm_bins_SpO2, n_alarm_bins_ABPsys, n_alarm_bins_RESP,
      n_cotrigger_windows, n_windows_total, cotrigger_rate,
      n_bins_ge2_alarm, phi_pairs(json 串: "HR|SpO2":0.3,...)
      （每 record × 每阈值族一行；phi_pairs 空则该对活跃 bin 不足）

⚠️ 阈值为占位 TODO（见 alarm_thresholds.py）；共触发**存在性**结论对阈值不敏感，
   但绝对频率待阈值锁定后才作定量。R8：告警为派生非专家标注。
纯 numpy + wfdb + pandas。Windows 规范：pathlib/utf-8/无硬编码盘符/spawn 不涉及。主线跑。
含 --smoke：只跑前 2 条 record 做最小验证（主线跑，我不跑）。
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from alarm_thresholds import VITAL_THRESHOLD_FAMILIES, COTRIGGER_WINDOW_S
from alarm_derive import (
    load_numerics,
    derive_alarm_timelines,
    resample_to_common_grid,
    count_cotrigger_windows,
    pairwise_phi,
)

THIS = Path(__file__).resolve()
OUT_DIR = THIS.parent
DEFAULT_PN_DIR = "mimic3wdb-matched/1.0"
CANON_ORDER = ["HR", "SpO2", "ABPsys", "RESP"]


def get_record_list(args):
    """取要处理的 record 名列表：--records 文件优先；否则在线读 RECORDS 前 N 条。"""
    if args.records:
        p = Path(args.records)
        recs = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
        return recs[: args.limit] if args.limit > 0 else recs
    # 在线取 RECORDS（matched 的 RECORDS 列出 'pXX/pXXXXXX' 病人目录；numerics 需拼具体 record）
    # TODO(主线): matched 的 record 结构为 pNN/pNNNNNN/<record>；此处给占位取法，
    #   若在线枚举不便，改用 --records 传预先 wget 的 numerics record 名清单。
    try:
        import wfdb
        recs = wfdb.get_record_list(DEFAULT_PN_DIR)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 在线取 RECORDS 失败({e})，请用 --records 传清单。")
        return []
    return recs[: args.limit] if args.limit > 0 else recs


def process_record(record, families, args):
    """对一条 record，逐阈值族派生告警 -> 数共触发 + 相关。返回行 list。"""
    rows = []
    try:
        signals = load_numerics(
            record,
            pn_dir=None if args.local_dir else DEFAULT_PN_DIR,
            local_dir=args.local_dir,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 读取失败 {record}: {e}")
        return rows
    if not signals:
        print(f"[warn] {record} 无可用体征信号（HR/SpO2/ABP/RESP），跳过")
        return rows

    for fam in families:
        timelines = derive_alarm_timelines(signals, fam)
        types, grid = resample_to_common_grid(timelines, grid_dt_s=1.0)
        ct = count_cotrigger_windows(grid, window_s=COTRIGGER_WINDOW_S, grid_dt_s=1.0)

        # 逐体征活跃 bin 数
        per_type_bins = {t: int(grid[i].sum()) for i, t in enumerate(types)}
        # phi 两两相关，索引映射回体征名
        phi_idx = pairwise_phi(grid)
        phi_named = {}
        for (ai, bi), val in phi_idx.items():
            key = f"{types[ai]}|{types[bi]}"
            phi_named[key] = None if (val != val) else round(val, 4)  # NaN->None

        duration_h = (ct["n_bins"] / 3600.0)
        row = {
            "record": record,
            "family": fam,
            "duration_h": round(duration_h, 3),
            "n_types_present": len(types),
            "n_alarm_bins_HR": per_type_bins.get("HR", 0),
            "n_alarm_bins_SpO2": per_type_bins.get("SpO2", 0),
            "n_alarm_bins_ABPsys": per_type_bins.get("ABPsys", 0),
            "n_alarm_bins_RESP": per_type_bins.get("RESP", 0),
            "n_cotrigger_windows": ct["n_cotrigger_windows"],
            "n_windows_total": ct["n_windows_total"],
            "cotrigger_rate": round(ct["cotrigger_rate"], 6) if ct["cotrigger_rate"] == ct["cotrigger_rate"] else "",
            "n_bins_ge2_alarm": ct["n_bins_ge2_alarm"],
            "phi_pairs": json.dumps(phi_named, ensure_ascii=False),
        }
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", type=str, default="",
                    help="record 名清单文件（每行一条 numerics record）")
    ap.add_argument("--local-dir", type=str, default="",
                    help="本地已下 MIMIC-III matched 目录（不给则在线 wfdb 只读）")
    ap.add_argument("--limit", type=int, default=20, help="最多处理 N 条 record")
    ap.add_argument("--families", type=str, default="default,conservative,liberal",
                    help="逗号分隔阈值族名")
    ap.add_argument("--smoke", type=int, default=0,
                    help="烟测：>0 时只跑前 2 条 record 最小验证")
    args = ap.parse_args()
    args.local_dir = args.local_dir or None

    families = [f.strip() for f in args.families.split(",") if f.strip()]
    for f in families:
        if f not in VITAL_THRESHOLD_FAMILIES:
            print(f"[ERR] 未知阈值族: {f}（可选 {list(VITAL_THRESHOLD_FAMILIES)}）")
            return 2

    if args.smoke:
        args.limit = 2

    records = get_record_list(args)
    if not records:
        print("[ERR] 无 record 可处理。00_check_access 判定 matched 开放后，"
              "用 --records 传 numerics record 清单或 --local-dir 指本地目录。")
        return 2

    print(f"[info] 处理 {len(records)} 条 record × {len(families)} 阈值族")
    all_rows = []
    for i, rec in enumerate(records):
        print(f"  [{i+1}/{len(records)}] {rec}")
        all_rows.extend(process_record(rec, families, args))

    if not all_rows:
        print("[ERR] 无有效行产出（全部 record 读取失败或无体征）。")
        return 2

    df = pd.DataFrame(all_rows)
    out_csv = OUT_DIR / "cotrigger_stats.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"[written] {out_csv}  ({len(df)} rows)")

    # ---- Q1 汇总（逐阈值族）----
    print("\n[Q1 汇总] 每阈值族的共触发占比（record 加权）：")
    for fam, g in df.groupby("family"):
        tot_win = g["n_windows_total"].sum()
        tot_ct = g["n_cotrigger_windows"].sum()
        rate = (tot_ct / tot_win) if tot_win else float("nan")
        n_rec_with_ct = int((g["n_cotrigger_windows"] > 0).sum())
        print(f"  [{fam}] 共触发窗 {tot_ct}/{tot_win} = {rate:.4%}; "
              f"有共触发的 record {n_rec_with_ct}/{len(g)}")
    print("\n[判据] Q1 GO 需：共触发非罕见（有意义占比 + 多 record 出现）+ phi 相关明显。"
          "\n       具体阈值待 planner/主线按 report 判据表定；本脚本只出可核统计量。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
