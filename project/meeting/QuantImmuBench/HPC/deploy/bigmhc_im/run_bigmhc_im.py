"""
run_bigmhc_im.py  --  QuantImmuBench BigMHC -m=im 推理启动器
服务项目：quantimmu-bench 扩张 v2 lever=部署BigMHC immunogenicity

功能：
  调用克隆在 repo/ 子目录下的 BigMHC predict.py，以 CPU 模式推理免疫原性。
  先用 prep_input.py 生成 bigmhc_inputs/bigmhc_input[_smoke].csv，再运行此脚本。

BigMHC CLI（已核实自 src/predict.py + src/cli.py）：
  python predict.py \
    -i=<input.csv>      # 输入 CSV（列 0=mhc, 列 1=pep，含1行表头）
    -m=im               # immunogenicity 模式 → 输出列名 BigMHC_IM
    -a=0                # allele 在第 0 列（默认值，显式写出）
    -p=1                # peptide 在第 1 列（默认值，显式写出）
    -c=1                # 跳过1行表头（默认值，显式写出）
    -d=cpu              # CPU 推理（HPC 若有 GPU 改为 -d=0 或 -d=all）
    -o=<output.prd>     # 输出路径（默认 <input>.prd）
    -j=<workers>        # DataLoader 并行 workers（HPC 建议 4-8）

输出文件格式（已核实自 src/predict.py 的 preds.to_csv）：
  CSV，列：mhc, pep, tgt, len, BigMHC_IM
  行序与输入一一对应（内部按肽长分 batch，最终 sort_index() 复原行序）
  BigMHC_IM 值域 [0,1]，越高越可能免疫原性

用法：
  python run_bigmhc_im.py [--repo-dir <dir>] [--in-dir <dir>] [--smoke] [--jobs N]

  --smoke: 使用 bigmhc_input_smoke.csv（先 prep_input.py --smoke N 生成）
           输出到 bigmhc_output_smoke.prd
  --jobs N: DataLoader workers（默认 4；Windows 本地调试用 --jobs 1）
  --device: 推理设备（默认 cpu；HPC 有 GPU 时改 0/all）
"""

import argparse
import pathlib
import subprocess
import sys


# ---------------------------------------------------------------------------
# 运行 BigMHC predict.py
# ---------------------------------------------------------------------------

def run(
    repo_dir: pathlib.Path,
    in_csv: pathlib.Path,
    out_prd: pathlib.Path,
    jobs: int,
    device: str,
) -> None:
    predict_py = repo_dir / "src" / "predict.py"
    if not predict_py.exists():
        raise FileNotFoundError(
            f"BigMHC predict.py 不存在: {predict_py}\n"
            "请先 git clone https://github.com/KarchinLab/bigmhc.git repo/\n"
            "（含 LFS 权重，约 5GB；需 git-lfs installed）"
        )

    if not in_csv.exists():
        raise FileNotFoundError(
            f"输入 CSV 不存在: {in_csv}\n"
            "请先运行 python prep_input.py [--smoke N]"
        )

    cmd = [
        sys.executable,
        str(predict_py),
        f"-i={in_csv}",
        "-m=im",       # immunogenicity 模式 → 输出列 BigMHC_IM
        "-a=0",        # col 0 = allele (HLA_Allele)
        "-p=1",        # col 1 = peptide
        "-c=1",        # skip 1 header row
        f"-d={device}",
        f"-o={out_prd}",
        f"-j={jobs}",
        "-v=1",        # verbose
    ]

    print("[run_bigmhc_im] 命令:")
    print("  " + " ".join(cmd))
    print(f"[run_bigmhc_im] 输入: {in_csv}")
    print(f"[run_bigmhc_im] 输出: {out_prd}")
    print(f"[run_bigmhc_im] 设备: {device}  workers: {jobs}")
    print(f"[run_bigmhc_im] 注意: BigMHC 按肽长分 batch 推理，CPU 大规模需较长时间")
    print("[run_bigmhc_im] 启动 predict.py ...")

    # 必须从 repo/src/ 切换工作目录，predict.py 有相对路径依赖（models/、data/pseudoseqs.csv）
    result = subprocess.run(
        cmd,
        cwd=str(repo_dir / "src"),
        check=False,
    )

    if result.returncode != 0:
        print(
            f"[run_bigmhc_im] predict.py 退出码: {result.returncode}",
            file=sys.stderr,
        )
        sys.exit(result.returncode)

    print(f"[run_bigmhc_im] 完成，输出: {out_prd}")
    print(f"[run_bigmhc_im] 输出列：mhc, pep, tgt, len, BigMHC_IM（已核实 cli.py modelname='BigMHC_IM'）")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    script_dir = pathlib.Path(__file__).parent
    default_repo = script_dir / "repo"
    default_in_dir = script_dir / "bigmhc_inputs"

    parser = argparse.ArgumentParser(
        description="调用 BigMHC predict.py -m=im，CPU 模式推理免疫原性"
    )
    parser.add_argument(
        "--repo-dir",
        default=str(default_repo),
        help="BigMHC git clone 路径（含 src/predict.py 和 models/；默认 bigmhc_im/repo/）",
    )
    parser.add_argument(
        "--in-dir",
        default=str(default_in_dir),
        help="输入/输出目录（默认 bigmhc_inputs/）",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="烟测：使用 bigmhc_input_smoke.csv，输出 bigmhc_output_smoke.prd",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=4,
        help="DataLoader workers（默认 4；Windows 本地调试用 1 避免 spawn 问题）",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        help="推理设备（默认 cpu；HPC 有 GPU 时用 0 或 all）",
    )
    args = parser.parse_args()

    suffix = "_smoke" if args.smoke else ""
    in_csv = pathlib.Path(args.in_dir) / f"bigmhc_input{suffix}.csv"
    out_prd = pathlib.Path(args.in_dir) / f"bigmhc_output{suffix}.prd"

    run(
        repo_dir=pathlib.Path(args.repo_dir),
        in_csv=in_csv,
        out_prd=out_prd,
        jobs=args.jobs,
        device=args.device,
    )


if __name__ == "__main__":
    main()
