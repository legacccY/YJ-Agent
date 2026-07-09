"""
run_neoag.py — QuantImmuBench §工具部署  neoag 启动器（调 Rscript run_neoag.R 出 raw）
服务项目：quantimmu-bench §工具部署 lever=补满 30 工具最后 1 个免疫原槽（neoag）

功能（对齐 run_andy90.py，但 neoag 不吃 HLA → 无逐 HLA 分组，单次跑全 input）：
  1. 读 neoag_input.csv（prep_input.py 产生：pair_id, mt_peptide, wt_peptide, mut_pos_1based, pep_len）
  2. 调 Rscript run_neoag.R（官方算法忠实包装：load Final_gbm_model.rds + 官方特征 + predict）
  3. 产出 neoag_raw.csv（列 mt_peptide, wt_peptide, score）
  4. --smoke N：只跑 input 前 N 行（先复制成临时小 CSV 喂 R）

依赖（必须先就绪，见 NOTES.md）：
  A. git clone github.com/vincentlaboratories/neoag → --repo（含 Final_gbm_model.rds）
  B. R 依赖：caret, gbm, Peptides, data.table, doParallel（R3.5.2 原版，见 NOTES §依赖）
  C. python prep_input.py 已产生 neoag_input.csv
  D. ⚠️ run_neoag.R 的 OFFICIAL API ADAPTER 块已由主窗按官方 repo 填妥（否则 R 会硬停）

CPU 秒~分钟级（GBM predict 轻量）。本机 Windows Rscript=E:/R-4.3.3/bin/Rscript.exe；HPC 用集群 R module。

用法（主窗跑，本脚本不自跑）：
  python run_neoag.py \
    --repo    /path/to/neoag \
    --rscript Rscript \
    [--model /path/to/Final_gbm_model.rds] [--input neoag_input.csv] [--out neoag_raw.csv] [--smoke N]
"""

import argparse
import csv
import pathlib
import subprocess
import sys

SCRIPT_DIR  = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_INPUT    = SCRIPT_DIR / "neoag_input.csv"
DEFAULT_OUT      = SCRIPT_DIR / "neoag_raw.csv"
DEFAULT_RUNNER_R = SCRIPT_DIR / "run_neoag.R"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="调 Rscript run_neoag.R（官方 GBM 忠实包装）出 neoag_raw.csv"
    )
    parser.add_argument("--repo", required=True,
                        help="neoag clone 根目录（git clone 见 NOTES.md，含 Final_gbm_model.rds）")
    parser.add_argument("--rscript", default="Rscript",
                        help="Rscript 路径（默认 PATH；本机 Windows=E:/R-4.3.3/bin/Rscript.exe）")
    parser.add_argument("--model", default="",
                        help="Final_gbm_model.rds 路径（默认 <repo>/Final_gbm_model.rds，⚠️TODO 核位置）")
    parser.add_argument("--input", default=str(DEFAULT_INPUT),
                        help="prep_input.py 产生的 neoag_input.csv")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help="raw 输出（默认 neoag_raw.csv）")
    parser.add_argument("--runner-r", default=str(DEFAULT_RUNNER_R),
                        help="run_neoag.R 路径")
    parser.add_argument("--smoke", type=int, default=0, metavar="N",
                        help="烟测：只跑 input 前 N 行（0=全量）")
    args = parser.parse_args()

    repo     = pathlib.Path(args.repo)
    input_p  = pathlib.Path(args.input)
    out_p    = pathlib.Path(args.out)
    runner_r = pathlib.Path(args.runner_r)

    if not input_p.exists():
        print(f"[run_neoag] ERROR: input 不存在: {input_p}\n  先跑 prep_input.py", file=sys.stderr)
        sys.exit(1)
    if not repo.exists():
        print(f"[run_neoag] ERROR: repo 不存在: {repo}\n"
              "  git clone https://github.com/vincentlaboratories/neoag", file=sys.stderr)
        sys.exit(1)
    if not runner_r.exists():
        print(f"[run_neoag] ERROR: run_neoag.R 不存在: {runner_r}", file=sys.stderr)
        sys.exit(1)

    # smoke：截前 N 行成临时 CSV
    run_input = input_p
    if args.smoke > 0:
        smoke_p = input_p.parent / "neoag_input_smoke.csv"
        with open(input_p, newline="", encoding="utf-8") as f_in:
            reader = csv.reader(f_in)
            rows = list(reader)
        header, body = rows[0], rows[1:1 + args.smoke]
        with open(smoke_p, "w", newline="", encoding="utf-8") as f_out:
            w = csv.writer(f_out)
            w.writerow(header)
            w.writerows(body)
        run_input = smoke_p
        print(f"[run_neoag] [SMOKE] 仅跑前 {len(body)} 对 → {smoke_p}")

    cmd = [
        args.rscript, str(runner_r),
        "--input", str(run_input),
        "--repo", str(repo),
        "--out", str(out_p),
    ]
    if args.model:
        cmd += ["--model", args.model]

    print(f"[run_neoag] >>> {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")  # Win: 防 R 输出非 gbk 字符崩溃
    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        print(f"[run_neoag] ⚠️ Rscript 退出码 {proc.returncode}（看上方 stderr；"
              "若提示 OFFICIAL API ADAPTER 未填 → 先按 NOTES §官方API 填 run_neoag.R）",
              file=sys.stderr)
        sys.exit(proc.returncode)
    if not out_p.exists():
        print(f"[run_neoag] ⚠️ 无输出文件 {out_p}", file=sys.stderr)
        sys.exit(1)

    print(f"\n[run_neoag] == 完成 ==")
    print(f"  raw: {out_p}（列 mt_peptide, wt_peptide, score）")
    print("[run_neoag] 下一步: python parse_output.py")


if __name__ == "__main__":
    main()
