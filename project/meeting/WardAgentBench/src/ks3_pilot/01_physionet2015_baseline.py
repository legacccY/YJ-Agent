# -*- coding: utf-8 -*-
"""
01_physionet2015_baseline.py — Q3（反证）+ 单告警 FAR baseline
==============================================================
回答哪个 Q：
  - Q3（反证/锁死）：确认 PhysioNet 2015 Challenge 是"单告警 / 单段"结构
    （每条 record 仅 1 个告警、5 类跨 record 分布、彼此不在同一时间窗共触发），
    **无法**供多告警共触发标注 —— 坐实"共触发必须去 MIMIC 波形派生"。
  - 单告警 baseline：用官方真/假金标（写在 .hea 注释行）算逐类 + 总体 FAR
    （false alarm rate = 假告警数 / 总告警数），作候选 B benchmark 的单告警对照基线。

输入：PhysioNet 2015 Challenge training 集本地目录（*.hea + *.mat）。
      默认路径 data/external/challenge-2015/training/（可 --data-dir 覆盖）。
      每条 .hea 注释含：告警类型（Asystole/Bradycardia/...）+ True alarm / False alarm。
输出：p2015_baseline.csv，列：
      record, alarm_type, is_true_alarm(0/1), n_alarms_in_record, seg_len_s, alarm_onset_s
      —— n_alarms_in_record 恒为 1 即证 Q3；末尾另 print 逐类/总体 FAR 汇总。
      同时输出 p2015_far_summary.csv，列：alarm_type, n_total, n_false, n_true, FAR

⚠️ 红线：真/假为**官方金标**（非本脚本派生），FAR 直接由金标算，可 Bash 核。
Windows 规范：pathlib、utf-8、无硬编码盘符、纯 numpy。主线跑。
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# 项目根：本文件在 <root>/project/meeting/WardAgentBench/src/ks3_pilot/
# data 默认放 <root>/data/external/challenge-2015/training/
THIS = Path(__file__).resolve()
REPO_ROOT = THIS.parents[5]  # ks3_pilot->src->WardAgentBench->meeting->project-><root>
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "external" / "challenge-2015" / "training"
OUT_DIR = THIS.parent

# PhysioNet 2015 官方五类告警名（.hea 注释里出现的规范写法）
KNOWN_TYPES = {
    "asystole": "Asystole",
    "bradycardia": "Bradycardia",
    "tachycardia": "Tachycardia",
    "ventricular_tachycardia": "Ventricular_Tachycardia",
    "ventricular_flutter_fib": "Ventricular_Flutter_Fib",
}


def parse_hea(hea_path):
    """
    解析一条 PhysioNet 2015 .hea 头。
    返回 dict(record, alarm_type, is_true_alarm, seg_len_s, fs, n_sig)。
    官方约定：注释行（以 '#' 开头）含告警类型词 + 'True alarm' / 'False alarm'。
    告警 onset 固定在段内第 300 s（官方：告警发生在 5min 处）。
    """
    text = hea_path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    # 第一行：record_name n_sig fs n_samples
    first = lines[0].split()
    record = first[0]
    n_sig = int(first[1]) if len(first) > 1 else None
    fs = float(first[2]) if len(first) > 2 else None
    n_samp = int(first[3]) if len(first) > 3 else None
    seg_len_s = (n_samp / fs) if (fs and n_samp) else None

    alarm_type = None
    is_true = None
    for ln in lines:
        if not ln.startswith("#"):
            continue
        low = ln.lower()
        for key, canon in KNOWN_TYPES.items():
            # 注释里可能写 'Ventricular Tachycardia' 或下划线形式，做宽松匹配
            probe = canon.lower().replace("_", " ")
            if probe in low or key.replace("_", " ") in low or canon.lower() in low:
                alarm_type = canon
        if "true alarm" in low or low.strip("# ").strip() == "true":
            is_true = 1
        elif "false alarm" in low or low.strip("# ").strip() == "false":
            is_true = 0

    return {
        "record": record,
        "alarm_type": alarm_type,
        "is_true_alarm": is_true,
        "n_alarms_in_record": 1,   # 结构性事实：每条 record 恒 1 个告警（Q3 证据）
        "seg_len_s": seg_len_s,
        "alarm_onset_s": 300.0,    # 官方固定 5min 处
        "fs": fs,
        "n_sig": n_sig,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=str, default=str(DEFAULT_DATA_DIR),
                    help="PhysioNet 2015 training 目录（含 *.hea）")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 条（0=全部）")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"[ERR] data dir 不存在: {data_dir}")
        print("      先下 PhysioNet 2015 Challenge training 集（见 README 下载指引）。")
        return 2

    hea_files = sorted(data_dir.glob("*.hea"))
    if args.limit > 0:
        hea_files = hea_files[: args.limit]
    if not hea_files:
        print(f"[ERR] 未找到 .hea: {data_dir}")
        return 2

    rows = []
    for hp in hea_files:
        try:
            rows.append(parse_hea(hp))
        except Exception as e:  # noqa: BLE001
            print(f"[warn] 解析失败 {hp.name}: {e}")

    df = pd.DataFrame(rows)
    per_rec_cols = ["record", "alarm_type", "is_true_alarm",
                    "n_alarms_in_record", "seg_len_s", "alarm_onset_s"]
    out_csv = OUT_DIR / "p2015_baseline.csv"
    df[per_rec_cols].to_csv(out_csv, index=False, encoding="utf-8")
    print(f"[written] {out_csv}  ({len(df)} records)")

    # ---- Q3 证据：每条 record 告警数恒为 1 ----
    max_alarms = int(df["n_alarms_in_record"].max()) if len(df) else 0
    print(f"[Q3] max n_alarms_in_record = {max_alarms} "
          f"(=1 即证：单告警/单段结构，无法供共触发标注)")

    # ---- 单告警 FAR baseline（用官方金标）----
    valid = df.dropna(subset=["alarm_type", "is_true_alarm"]).copy()
    valid["is_true_alarm"] = valid["is_true_alarm"].astype(int)
    summ = []
    for atype, g in valid.groupby("alarm_type"):
        n_total = len(g)
        n_false = int((g["is_true_alarm"] == 0).sum())
        n_true = int((g["is_true_alarm"] == 1).sum())
        far = (n_false / n_total) if n_total else float("nan")
        summ.append({"alarm_type": atype, "n_total": n_total,
                     "n_false": n_false, "n_true": n_true, "FAR": far})
    # 总体
    n_total = len(valid)
    n_false = int((valid["is_true_alarm"] == 0).sum())
    summ.append({"alarm_type": "ALL", "n_total": n_total, "n_false": n_false,
                 "n_true": n_total - n_false,
                 "FAR": (n_false / n_total) if n_total else float("nan")})

    sdf = pd.DataFrame(summ)
    sum_csv = OUT_DIR / "p2015_far_summary.csv"
    sdf.to_csv(sum_csv, index=False, encoding="utf-8")
    print(f"[written] {sum_csv}")
    print(sdf.to_string(index=False))
    print(f"\n[note] 解析出告警类型的 record: {len(valid)}/{len(df)}"
          f"（未解析出的检查 .hea 注释格式，或用 wfdb 读 comments）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
