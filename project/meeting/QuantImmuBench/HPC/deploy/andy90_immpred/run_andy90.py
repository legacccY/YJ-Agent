"""
run_andy90.py — QuantImmuBench §工具部署  andy90 逐 HLA 跑预测 + 汇总 raw
服务项目：quantimmu-bench §工具部署 lever=免疫原补位（补到 20）

功能：
  1. 读 andy90_inputs/andy90_manifest.csv（prep_input.py 产生）
  2. 对每个 HLA：调 Rscript run_andy90.R（忠实包装官方 main.R），传该 HLA 的 fasta
     run_andy90.R 内部 source 官方 src/binding_prediction.R + get_similarity.R + predict_amp.R
  3. 收集每个 HLA 的 predicted_immunogenicity.csv（列 HLA,peptide,amplitude,immunogenic）
  4. 合并 → andy90_raw.csv（HLA,peptide,amplitude,immunogenic）

依赖（必须先就绪，见 NOTES.md）：
  A. git clone github.com/andy90/immunogenicity_predictor → --repo
  B. netMHCpan 二进制（andy90 原版 = 4.0；项目 HPC 有 4.1，列解析风险见 NOTES §netMHCpan 版本）→ --netmhcpan
  C. R 依赖：tidyverse, seqinr, here, Biostrings, doParallel（见 NOTES §安装）
  D. python prep_input.py 已产生 andy90_inputs/

⚠️ netMHCpan 是 Linux/Darwin 二进制 → 全量预测实际在 HPC(Linux) 跑（Rscript on HPC）。
   本机 Windows 仅能做无 netMHCpan 的静态检查。

用法（主线跑，本脚本不自跑）：
  python run_andy90.py \
    --repo      /path/to/immunogenicity_predictor \
    --netmhcpan /gpfs/.../netMHCpan-4.0/netMHCpan \
    --rscript   Rscript \
    [--inputs-dir andy90_inputs] [--out andy90_raw.csv] [--smoke N]
"""

import argparse
import csv
import pathlib
import subprocess
import sys

SCRIPT_DIR  = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_INPUTS_DIR = SCRIPT_DIR / "andy90_inputs"
DEFAULT_OUT        = SCRIPT_DIR / "andy90_raw.csv"
DEFAULT_RUNNER_R   = SCRIPT_DIR / "run_andy90.R"

# raw 输出列（对齐官方 predicted_immunogenicity.csv 表头）
RAW_COLS = ["HLA", "peptide", "amplitude", "immunogenic"]


def run_one_hla(
    rscript: str,
    runner_r: pathlib.Path,
    fasta: pathlib.Path,
    hla_netmhcpan: str,
    netmhcpan: str,
    repo: pathlib.Path,
    out_csv: pathlib.Path,
) -> bool:
    """调 Rscript run_andy90.R 跑单个 HLA；成功返回 True。"""
    cmd = [
        rscript, str(runner_r),
        "--fasta", str(fasta),
        "--hlas", hla_netmhcpan,
        "--netmhcpan", netmhcpan,
        "--repo", str(repo),
        "--out", str(out_csv),
    ]
    print(f"[run_andy90] >>> {hla_netmhcpan}  ({fasta.name})")
    print("             " + " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        print(f"[run_andy90] ⚠️ HLA={hla_netmhcpan} 退出码 {proc.returncode}，跳过（该 HLA 在 parse 阶段填 NaN）",
              file=sys.stderr)
        return False
    if not out_csv.exists():
        print(f"[run_andy90] ⚠️ HLA={hla_netmhcpan} 无输出文件 {out_csv}，跳过", file=sys.stderr)
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="逐 HLA 调 andy90 main.R（忠实包装），汇总 andy90_raw.csv"
    )
    parser.add_argument("--repo", required=True,
                        help="immunogenicity_predictor clone 根目录（git clone 见 NOTES.md）")
    parser.add_argument("--netmhcpan", required=True,
                        help="netMHCpan 二进制路径（andy90 原版=4.0；项目 HPC 4.1 见 NOTES §版本风险）")
    parser.add_argument("--rscript", default="Rscript",
                        help="Rscript 路径（默认 PATH 中 Rscript；本机 Windows=E:/R-4.3.3/bin/Rscript.exe）")
    parser.add_argument("--inputs-dir", default=str(DEFAULT_INPUTS_DIR),
                        help="prep_input.py 产生的 andy90_inputs/ 目录")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help="汇总 raw 输出（默认 andy90_raw.csv）")
    parser.add_argument("--runner-r", default=str(DEFAULT_RUNNER_R),
                        help="run_andy90.R 路径")
    parser.add_argument("--smoke", type=int, default=0, metavar="N",
                        help="烟测：只跑 manifest 前 N 个 HLA（0=全量）")
    args = parser.parse_args()

    inputs_dir = pathlib.Path(args.inputs_dir)
    manifest   = inputs_dir / "andy90_manifest.csv"
    repo       = pathlib.Path(args.repo)
    out_csv    = pathlib.Path(args.out)
    runner_r   = pathlib.Path(args.runner_r)
    tmp_dir    = inputs_dir / "andy90_per_hla_out"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    if not manifest.exists():
        print(f"[run_andy90] ERROR: manifest 不存在: {manifest}\n  先跑 prep_input.py", file=sys.stderr)
        sys.exit(1)
    if not repo.exists():
        print(f"[run_andy90] ERROR: repo 不存在: {repo}\n"
              "  git clone https://github.com/andy90/immunogenicity_predictor", file=sys.stderr)
        sys.exit(1)
    if not runner_r.exists():
        print(f"[run_andy90] ERROR: run_andy90.R 不存在: {runner_r}", file=sys.stderr)
        sys.exit(1)

    # 读 manifest
    rows = []
    with open(manifest, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.smoke > 0:
        rows = rows[: args.smoke]
        print(f"[run_andy90] [SMOKE] 仅跑前 {len(rows)} 个 HLA")

    # 逐 HLA 跑
    n_ok = 0
    n_fail = 0
    per_hla_outputs: list[pathlib.Path] = []
    for r in rows:
        hla_nostar = r["hla_netmhcpan"].strip()
        fasta = inputs_dir / r["fasta_file"].strip()
        safe = r["fasta_file"].strip().rsplit(".", 1)[0]
        per_out = tmp_dir / f"andy90_out_{safe}.csv"
        if not fasta.exists():
            print(f"[run_andy90] ⚠️ fasta 缺失 {fasta}，跳过 {hla_nostar}", file=sys.stderr)
            n_fail += 1
            continue
        ok = run_one_hla(args.rscript, runner_r, fasta, hla_nostar,
                         args.netmhcpan, repo, per_out)
        if ok:
            per_hla_outputs.append(per_out)
            n_ok += 1
        else:
            n_fail += 1

    # 合并所有 per-HLA 输出
    n_rows = 0
    with open(out_csv, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(RAW_COLS)
        for p in per_hla_outputs:
            with open(p, newline="", encoding="utf-8") as f_in:
                reader = csv.DictReader(f_in)
                # 官方列名 HLA,peptide,amplitude,immunogenic
                for row in reader:
                    writer.writerow([
                        row.get("HLA", "").strip(),
                        row.get("peptide", "").strip(),
                        row.get("amplitude", "").strip(),
                        row.get("immunogenic", "").strip(),
                    ])
                    n_rows += 1

    print(f"\n[run_andy90] == 汇总 ==")
    print(f"  HLA 成功: {n_ok}   失败/跳过: {n_fail}")
    print(f"  raw 行数: {n_rows}")
    print(f"  输出:     {out_csv}")
    print("[run_andy90] amplitude 越高越免疫原（直接用，无需翻转）；下一步 python parse_output.py")


if __name__ == "__main__":
    main()
