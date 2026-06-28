# -*- coding: utf-8 -*-
"""
run_bigmhc_101102.py — Phase B：用订正 HLA 等位重推理 BigMHC -m=im（P101/P102）。

唯一订正输入源 = scripts/out/phaseB/backbone_101102.csv（prep_101102_subset.py 产，
已过闸门1：HLA_Allele == 订正真值 P101={A66:01,B40:01,B57:01,C06:02}/
P102={A02:01,B35:03,B38:01}）。本脚本只从这份派生，绝不读旧 bigmhc 输入文件。

自包含三步（prep+run+parse 一体），与 HPC/deploy/bigmhc_im 三件套调用逻辑一致：
  1. prep：从 backbone 取 MT_Subpeptide + WT_Subpeptide，与 HLA_Allele 配对，
     去重为 (mhc, pep) 双列 CSV（HLA-A*66:01 格式直接透传，BigMHC 模糊匹配原生接受）。
  2. run：调克隆在 repo/ 下的官方 predict.py，-m=im -d=cpu，
     **Windows 本地 -j=1（spawn worker pickle 易 OOM，单 worker 最稳）**。
     必须从 repo/src/ 目录运行（predict.py 相对路径依赖 ../../models/ 与 ../data/）。
  3. parse：读输出 .prd（列 mhc,pep,tgt,len,BigMHC_IM），按 (pep, mhc) 键建 score_map，
     回贴每行 bb_idx 的 MT/WT 分数。

产出: scripts/out/phaseB/BigMHC_101102.csv
      列: bb_idx, MT_BigMHC, WT_BigMHC
方向: BigMHC_IM ∈ [0,1] 越高越免疫原（官方 sigmoid 概率，无翻转）。

用法:
    python run_bigmhc_101102.py [--smoke N] [--jobs N] [--device cpu] [--repo-dir <dir>]
    --smoke N: 只取前 N 个唯一 (mhc,pep) 对跑（验工具能跑、分数合理），不产正式 CSV。
    --jobs N : DataLoader workers（默认 1；Windows 本地必 1 防 spawn OOM）。
    --device : 推理设备（默认 cpu；HPC 有 GPU 改 0/all）。
"""
import argparse
import csv
import math
import os
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # QuantImmuBench/
BACKBONE = ROOT / "scripts" / "out" / "phaseB" / "backbone_101102.csv"
REPO = ROOT / "HPC" / "deploy" / "bigmhc_im" / "repo"  # 官方 git clone（含 src/predict.py + models/）
WORKDIR = ROOT / "scripts" / "out" / "phaseB" / "bigmhc_work"  # in/out 临时
OUT = ROOT / "scripts" / "out" / "phaseB" / "BigMHC_101102.csv"


def main():
    ap = argparse.ArgumentParser(description="Phase B BigMHC -m=im 重推理 P101/P102")
    ap.add_argument("--smoke", type=int, default=0,
                    help="只取前 N 个唯一 (mhc,pep) 对验工具，不产 CSV")
    ap.add_argument("--jobs", type=int, default=1,
                    help="DataLoader workers（默认 1；Windows 本地必 1 防 spawn pickle OOM）")
    ap.add_argument("--device", default="cpu",
                    help="推理设备（默认 cpu；HPC 有 GPU 改 0/all）")
    ap.add_argument("--repo-dir", default=str(REPO),
                    help="BigMHC git clone 路径（含 src/predict.py 与 models/）")
    args = ap.parse_args()

    if not BACKBONE.exists():
        raise SystemExit(f"[FAIL] 订正源不存在: {BACKBONE}")
    repo_dir = Path(args.repo_dir)
    predict_py = repo_dir / "src" / "predict.py"
    if not predict_py.exists():
        raise SystemExit(
            f"[FAIL] 官方 predict.py 不存在: {predict_py}\n"
            "请先 git clone https://github.com/KarchinLab/bigmhc.git repo/（含 LFS 权重 ~5GB）")
    WORKDIR.mkdir(parents=True, exist_ok=True)

    # ── prep：读 backbone，聚合所有需打分的 (mhc, pep) 对（MT ∪ WT，去重）─────────
    rows = []
    pairs = {}  # (hla, pep) → None（有序去重）
    skipped_empty = 0
    with open(BACKBONE, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
            hla = (r.get("HLA_Allele") or "").strip()
            for col in ("MT_Subpeptide", "WT_Subpeptide"):
                pep = (r.get(col) or "").strip()
                if not pep or not hla:
                    skipped_empty += 1
                    continue
                # HLA-A*66:01 格式直接透传，BigMHC fuzzy match 原生接受（无需去 */:）
                pairs.setdefault((hla, pep), None)

    pair_list = list(pairs.keys())
    if args.smoke:
        pair_list = pair_list[:args.smoke]
    print(f"[prep] backbone={len(rows)} 行 | 唯一 (mhc,pep)={len(pairs)} | "
          f"空跳过={skipped_empty}" + (f" | smoke 取前 {len(pair_list)} 对" if args.smoke else ""))
    alleles = sorted({h for h, _ in pair_list})
    print(f"[prep]   涉及 allele({len(alleles)}): {', '.join(alleles)}")

    suffix = "_smoke" if args.smoke else ""
    in_csv = WORKDIR / f"bigmhc_input{suffix}.csv"
    out_prd = WORKDIR / f"bigmhc_output{suffix}.prd"
    with open(in_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["mhc", "pep"])  # BigMHC default: -a=0(mhc) -p=1(pep) -c=1(header)
        for hla, pep in pair_list:
            w.writerow([hla, pep])
    print(f"[prep] 写输入 {in_csv}（{len(pair_list)} 行 + 表头）")

    # ── run：从 repo/src/ 调官方 predict.py（相对路径依赖 ../../models/ 与 ../data/）──
    cmd = [
        sys.executable, str(predict_py),
        f"-i={in_csv}",
        "-m=im",          # immunogenicity 模式 → 输出列 BigMHC_IM
        "-a=0",           # col 0 = mhc
        "-p=1",           # col 1 = pep
        "-c=1",           # skip 1 header row
        f"-d={args.device}",
        f"-o={out_prd}",
        f"-j={args.jobs}",
        "-v=1",
    ]
    print(f"[run] cwd={repo_dir / 'src'}")
    print(f"[run] {' '.join(cmd)}")
    print(f"[run] device={args.device} jobs={args.jobs}（CPU ensemble 7 ckpt，规模大较慢）")
    res = subprocess.run(cmd, cwd=str(repo_dir / "src"), check=False)
    if res.returncode != 0:
        raise SystemExit(f"[FAIL] predict.py 退出码 {res.returncode}")
    if not out_prd.exists():
        raise SystemExit(f"[FAIL] 未生成输出 {out_prd}")
    print(f"[run] 完成，输出 {out_prd}")

    # ── parse：读 .prd → score_map{(pep,mhc):BigMHC_IM} ─────────────────────────
    score_map = {}
    n_nan = 0
    with open(out_prd, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        im_col = "BigMHC_IM"
        if im_col not in fieldnames:
            cand = [c for c in fieldnames if "im" in c.lower()]
            if cand:
                im_col = cand[0]
                print(f"[parse] WARNING: 无 BigMHC_IM 列，fallback '{im_col}'，实际列 {fieldnames}",
                      file=sys.stderr)
            else:
                raise SystemExit(f"[FAIL] 输出无 BigMHC_IM 列，实际列 {fieldnames}")
        for row in reader:
            pep = (row.get("pep") or "").strip()
            mhc = (row.get("mhc") or "").strip()
            vs = (row.get(im_col) or "").strip()
            if not pep or not mhc:
                continue
            try:
                v = float(vs)
            except (ValueError, TypeError):
                n_nan += 1
                continue
            if math.isnan(v):
                n_nan += 1
                continue
            score_map[(pep, mhc)] = v
    print(f"[parse] 读入 BigMHC_IM 分数 {len(score_map)} 条（NaN/空跳过 {n_nan}）")

    if args.smoke:
        vals = list(score_map.values())
        if vals:
            print(f"[smoke] {len(vals)} 分数 | range [{min(vals):.4f}, {max(vals):.4f}]（应 ∈ [0,1]）")
        print(f"[smoke] 跑了 {len(pair_list)} 对，工具可跑、分数合理。未产正式 CSV。")
        return

    # ── 回贴 bb_idx，写 BigMHC_101102.csv ──────────────────────────────────────
    def fmt(pep, hla):
        if not pep or not hla:
            return ""
        v = score_map.get((pep, hla))
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""  # NaN → 空（pandas 读为 NaN）
        return str(round(v, 6))

    n_mt = n_wt = n_mt_nan = n_wt_nan = 0
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bb_idx", "MT_BigMHC", "WT_BigMHC"])
        w.writeheader()
        for r in rows:
            hla = (r.get("HLA_Allele") or "").strip()
            mt = (r.get("MT_Subpeptide") or "").strip()
            wt = (r.get("WT_Subpeptide") or "").strip()
            mt_s = fmt(mt, hla)
            wt_s = fmt(wt, hla)
            n_mt += mt_s != ""
            n_wt += wt_s != ""
            n_mt_nan += mt_s == ""
            n_wt_nan += wt_s == ""
            w.writerow({"bb_idx": r["bb_idx"], "MT_BigMHC": mt_s, "WT_BigMHC": wt_s})

    print(f"\n[parse] 写 {OUT}  ({len(rows)} 行)")
    print(f"[parse]   MT_BigMHC: {n_mt} found / {n_mt_nan} NaN")
    print(f"[parse]   WT_BigMHC: {n_wt} found / {n_wt_nan} NaN")
    print(f"[parse]   方向：BigMHC_IM 越高越免疫原（无翻转）")


if __name__ == "__main__":
    main()
