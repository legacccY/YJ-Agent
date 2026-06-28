# -*- coding: utf-8 -*-
"""
run_cnneo_101102.py — Phase B：用订正 HLA 等位重推理 CNNeo（FCNN_TF）P101/P102。

唯一订正输入源 = scripts/out/phaseB/backbone_101102.csv（prep_101102_subset.py 产，
已过闸门1：HLA_Allele == 订正真值 P101={A66:01,B40:01,B57:01,C06:02}/
P102={A02:01,B35:03,B38:01}）。本脚本只从这份派生，绝不读旧 cnneo 输入文件。

自包含三步（prep+run+parse 一体），与 HPC/deploy/cnneo 三件套调用逻辑一致：
  1. prep：从 backbone 取 MT_Subpeptide + WT_Subpeptide（连同各自行的 HLA_Allele），
     去重成 unique (peptide, hla) 对。肽长过滤 8-14（镜像 prep_input.py 默认）；
     非标准氨基酸肽防护 → 不送模型、回贴 NaN（本子集实测 0 个，防护用）。
  2. run：复用 run_cnneo.run_inference_fcnn_tf（编码/推理逻辑零改动），
     **加载已训练好的 weights/（fcnn_tf_model.pth + fcnn_tf_vectorizer.pkl），不重训**——
     复用产出原始全量分数的同一模型，保证与基准一致。
  3. parse：复用 parse_output.py 的 (peptide, hla) → score 映射，按每行 bb_idx 的
     MT/WT 肽分别回贴。

CNNeo 输入格式（见 TOOLS/CNNeo.md）：
  - 列 peptide + hla，HLA 用标准 HLA-A*02:01（run_cnneo 内部自动去 *）。
  - backbone 的 HLA_Allele 即标准格式，原样传入。

产出: scripts/out/phaseB/CNNeo_101102.csv
      列: bb_idx, MT_CNNeo, WT_CNNeo
方向: score ∈ [0,1]，softmax class=1 概率，越高越免疫原（官方原始方向，无翻转）。

用法:
    python run_cnneo_101102.py [--smoke N]
    --smoke N: 只对前 N 个 unique (peptide, hla) 对推理（验模型能跑、分数在 [0,1]），不产 CSV。
"""
import argparse
import csv
import importlib.util
import math
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # QuantImmuBench/
BACKBONE = ROOT / "scripts" / "out" / "phaseB" / "backbone_101102.csv"
CNNEO_DIR = ROOT / "HPC" / "deploy" / "cnneo"
WEIGHTS_DIR = CNNEO_DIR / "weights"
MODEL_PTH = WEIGHTS_DIR / "fcnn_tf_model.pth"
VECTORIZER_PKL = WEIGHTS_DIR / "fcnn_tf_vectorizer.pkl"
WORKDIR = ROOT / "scripts" / "out" / "phaseB" / "cnneo_work"  # 临时 input/raw_output
OUT = ROOT / "scripts" / "out" / "phaseB" / "CNNeo_101102.csv"

# 肽长过滤范围（镜像 HPC/deploy/cnneo/prep_input.py 默认 8-14）
MIN_LEN = 8
MAX_LEN = 14
STD_AA = set("ACDEFGHIKLMNPQRSTVWY")  # 非标准氨基酸肽防护（本子集实测 0 个）


def load_run_cnneo():
    """从 HPC/deploy/cnneo/run_cnneo.py 动态导入推理逻辑（零改动复用编码/模型）。"""
    spec = importlib.util.spec_from_file_location("run_cnneo", CNNEO_DIR / "run_cnneo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def is_clean_pep(p: str) -> bool:
    return bool(p) and MIN_LEN <= len(p) <= MAX_LEN and all(c in STD_AA for c in p)


def main():
    ap = argparse.ArgumentParser(description="Phase B CNNeo(FCNN_TF) 重推理 P101/P102")
    ap.add_argument("--smoke", type=int, default=0,
                    help="只对前 N 个 unique (peptide,hla) 对推理验工具，不产 CSV")
    args = ap.parse_args()

    if not BACKBONE.exists():
        raise SystemExit(f"[FAIL] 订正源不存在: {BACKBONE}")
    if not (MODEL_PTH.exists() and VECTORIZER_PKL.exists()):
        raise SystemExit(
            f"[FAIL] 已训练权重缺失: {MODEL_PTH} / {VECTORIZER_PKL}\n"
            "  本脚本复用原全量训练好的权重做推理，不重训。请先跑 run_cnneo.py 训练或确认 weights/ 完整。"
        )
    WORKDIR.mkdir(parents=True, exist_ok=True)

    rc = load_run_cnneo()  # run_cnneo 模块（run_inference_fcnn_tf 等）

    # ── prep：读 backbone，收集 unique (peptide, hla) 对（MT ∪ WT，去重）──────────
    rows = []
    pair_set = set()                  # {(pep_upper, hla)}
    dropped = 0                       # 非标准/越界肽（去重计数）
    dropped_pairs = set()
    with open(BACKBONE, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
            hla = r["HLA_Allele"].strip()
            for col in ("MT_Subpeptide", "WT_Subpeptide"):
                pep = (r.get(col) or "").strip().upper()
                if not pep:
                    continue
                key = (pep, hla)
                if is_clean_pep(pep):
                    pair_set.add(key)
                else:
                    dropped_pairs.add(key)

    dropped = len(dropped_pairs)
    pairs = sorted(pair_set)
    print(f"[prep] backbone={len(rows)} 行 | unique (peptide,hla) 对={len(pairs)} "
          f"| 非标准/越界肽对(置NaN)={dropped}")

    run_pairs = pairs[:args.smoke] if args.smoke else pairs

    # 写 CNNeo 输入 CSV（列 peptide,hla；HLA 原样标准格式，run_cnneo 内部去 *）
    input_csv = WORKDIR / "cnneo_input_101102.csv"
    with open(input_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["peptide", "hla"])
        for pep, hla in run_pairs:
            w.writerow([pep, hla])

    # ── run：复用 run_cnneo.run_inference_fcnn_tf（加载已训练权重，不重训）──────────
    raw_out = WORKDIR / "cnneo_raw_output_101102.csv"
    rc.run_inference_fcnn_tf(
        input_csv=input_csv,
        output_csv=raw_out,
        model_path=MODEL_PTH,
        vectorizer_path=VECTORIZER_PKL,
        smoke=0,  # 已在 run_pairs 截断；此处对整 input_csv 推理
    )

    # ── 读回 raw_output，构 (pep_upper, hla) → score 映射（镜像 parse_output.py）──
    score_dict = {}
    with open(raw_out, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pep = (r.get("peptide") or "").strip().upper()
            hla = (r.get("hla") or "").strip()
            try:
                score_dict[(pep, hla)] = float(r["score"])
            except (KeyError, ValueError):
                continue

    if args.smoke:
        vals = list(score_dict.values())
        smin = min(vals) if vals else float("nan")
        smax = max(vals) if vals else float("nan")
        print(f"\n[smoke] 推理了 {len(run_pairs)} 对，得 {len(score_dict)} 个分数 | "
              f"range [{smin:.4f}, {smax:.4f}]（应在 [0,1]）。未产 CSV。")
        return

    # ── parse：回贴 bb_idx，写 CNNeo_101102.csv ──────────────────────────────────
    def fmt(pep, hla):
        v = score_dict.get((pep, hla))
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""  # NaN → 空（pandas 读为 NaN）
        return str(round(v, 6))

    n_mt = n_wt = n_mt_nan = n_wt_nan = 0
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bb_idx", "MT_CNNeo", "WT_CNNeo"])
        w.writeheader()
        for r in rows:
            hla = r["HLA_Allele"].strip()
            mt = (r.get("MT_Subpeptide") or "").strip().upper()
            wt = (r.get("WT_Subpeptide") or "").strip().upper()
            mt_s = fmt(mt, hla) if mt else ""
            wt_s = fmt(wt, hla) if wt else ""
            n_mt += mt_s != ""
            n_wt += wt_s != ""
            n_mt_nan += mt_s == ""
            n_wt_nan += wt_s == ""
            w.writerow({"bb_idx": r["bb_idx"], "MT_CNNeo": mt_s, "WT_CNNeo": wt_s})

    print(f"\n[parse] 写 {OUT}  ({len(rows)} 行)")
    print(f"[parse]   MT_CNNeo: {n_mt} found / {n_mt_nan} NaN")
    print(f"[parse]   WT_CNNeo: {n_wt} found / {n_wt_nan} NaN")
    print(f"[parse]   方向：score ∈ [0,1] 越高越免疫原（无翻转）")


if __name__ == "__main__":
    main()
