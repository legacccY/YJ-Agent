#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""拉回 HPC 10 chunk 的 results_<m>_<ds>.csv，合并成统一 master 表。
难点：PSFHS 15 列(dice_PS/dice_FH/dice_mean)，HC18 13 列(dice_head/dice_mean)——schema 不同。
统一到 long-format：公共列 + dice_mean(通比) + per-structure dice 长表(structure 维)。
输出本地 results/master_long.csv + results/master_wide.csv。完成 150/150 后跑。"""
import paramiko, io, csv, os
R = "/gpfs/work/bio/jiayu2403/fetalss"
OUT = os.path.join(os.path.dirname(__file__), "..", "results")
os.makedirs(OUT, exist_ok=True)
METHODS = ["supervised", "mean_teacher", "cps", "uamt", "fixmatch"]
DATASETS = ["psfhs", "hc18"]

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("dtn.hpc.xjtlu.edu.cn", username="jiayu2403", password="pxXd3VGhbB", timeout=30)
sftp = c.open_sftp()

wide_rows = []   # 每 run 一行：公共字段 + dice_mean + hd95_mean
long_rows = []   # 每 (run, structure) 一行：用于结构难度不对称分析
missing = []
for m in METHODS:
    for d in DATASETS:
        rp = f"{R}/code/results/results_{m}_{d}.csv"
        try:
            with sftp.open(rp, "r") as f:
                txt = f.read().decode(errors="replace")
        except IOError:
            missing.append(f"{m}_{d}"); continue
        rdr = list(csv.DictReader(io.StringIO(txt)))
        # 去重 (method,dataset,label_ratio,seed) 取最后一条(续跑覆盖)
        dedup = {}
        for r in rdr:
            if r.get("epochs") != "100":
                continue
            key = (r["method"], r["dataset"], r["label_ratio"], r["seed"])
            dedup[key] = r
        for r in dedup.values():
            common = {
                "method": r["method"], "dataset": r["dataset"],
                "label_ratio": float(r["label_ratio"]), "seed": int(r["seed"]),
                "dice_mean": float(r["dice_mean"]), "hd95_mean": float(r["hd95_mean"]),
                "n_labeled": int(r["n_labeled"]), "n_unlabeled": int(r["n_unlabeled"]),
                "n_test": int(r["n_test"]), "train_time_min": float(r["train_time_min"]),
            }
            wide_rows.append(common)
            # per-structure 长表
            if d == "psfhs":
                for st, key in [("PS", "dice_PS"), ("FH", "dice_FH")]:
                    long_rows.append({**common, "structure": st, "dice": float(r[key])})
            else:
                long_rows.append({**common, "structure": "head", "dice": float(r["dice_head"])})
sftp.close(); c.close()

wide_rows.sort(key=lambda x: (x["dataset"], x["method"], x["label_ratio"], x["seed"]))
long_rows.sort(key=lambda x: (x["dataset"], x["method"], x["label_ratio"], x["seed"], x["structure"]))

wp = os.path.join(OUT, "master_wide.csv")
with open(wp, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(wide_rows[0].keys())); w.writeheader(); w.writerows(wide_rows)
lp = os.path.join(OUT, "master_long.csv")
with open(lp, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(long_rows[0].keys())); w.writeheader(); w.writerows(long_rows)

print(f"[merge] wide rows={len(wide_rows)} (expect 150) -> {wp}")
print(f"[merge] long rows={len(long_rows)} -> {lp}")
if missing:
    print(f"[merge] MISSING combos: {missing}")
# 完整性核
from collections import Counter
cnt = Counter((r["method"], r["dataset"]) for r in wide_rows)
print("[merge] per-combo counts (expect 15 each):")
for m in METHODS:
    print("  " + " ".join(f"{m[:4]}_{d}={cnt.get((m,d),0)}" for d in DATASETS))
