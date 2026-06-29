r"""
run_seq2neo.py  --  QuantImmuBench Seq2Neo immuno 推理启动器
服务项目：quantimmu-bench G1 工具补齐 lever=部署 Seq2Neo immunogenicity

================================================================
⚠️ LINUX-ONLY + 阻塞依赖（本地 Windows 跑不了，主线在 WSL/HPC 跑）
================================================================
  - Seq2Neo conda 包 `liuxslab::seq2neo` v2.1 仅 linux-64（2023-02-16），
    无 win-64 / osx build。本机 Windows 直跑必失败。
  - 硬依赖（需手动装、在 PATH 中可见）：
      * netMHCpan == 4.1.b  （已有 WSL: ~/quantimmu/ext_tools/netMHCpan-4.1）
      * netCTLpan == 1.1.b  （⚠️ 未独立部署，DTU 许可待申请——真阻塞）
  - netCTLpan 不到位前，本脚本会被 Seq2Neo 内部调用链卡住。
  ==> 主线在 WSL/HPC（已装 seq2neo + 两个 DTU 工具）下跑此脚本。

功能：
  subprocess 调 `seq2neo immuno --mode multiple --inputfile <X.csv> --outdir <Y>`。
  先用 prep_input.py 生成 seq2neo_inputs/seq2neo_input[_smoke].csv，再运行此脚本。

Seq2Neo immuno CLI（researcher 核实，带源见 NOTES.md §3）：
  seq2neo immuno \
    --mode multiple \                 # 批量模式（多条肽）
    --inputfile <input.csv> \         # 两列 Pep,HLA（P 大写，HLA 无星号格式）
    --outdir <out_dir>                # 输出目录

输出（researcher 核实 §6）：
  <out_dir>/cnn_results.csv        # 免疫原性分（越大越免疫原，阈值 >0.5）
                                   # # TODO: 确切分数列名待装后实跑确认
  <out_dir>/immuno_input_file.csv  # 中间特征文件

用法：
  python run_seq2neo.py [--in-dir <dir>] [--smoke] [--seq2neo-bin seq2neo] [--extra ...]

  --smoke: 使用 seq2neo_input_smoke.csv，输出到 seq2neo_out_smoke/
  --seq2neo-bin: seq2neo 可执行名/路径（默认 `seq2neo`，假定在 conda env PATH 中）

红线：本脚本由 coder 写好备用，**不在本地运行**（linux-only + netCTLpan 阻塞）。
"""

import argparse
import pathlib
import shutil
import subprocess
import sys


# ---------------------------------------------------------------------------
# 运行 seq2neo immuno
# ---------------------------------------------------------------------------

def run(
    seq2neo_bin: str,
    in_csv: pathlib.Path,
    out_dir: pathlib.Path,
    extra_args: list,
) -> None:
    if not in_csv.exists():
        raise FileNotFoundError(
            f"输入 CSV 不存在: {in_csv}\n"
            "请先运行 python prep_input.py [--smoke N]"
        )

    # 预检：seq2neo 可执行是否在 PATH（linux-only，本地 Windows 必无）
    resolved = shutil.which(seq2neo_bin)
    if resolved is None:
        print(
            f"[run_seq2neo] WARNING: 找不到可执行 '{seq2neo_bin}'（不在 PATH）。\n"
            "  Seq2Neo 仅 linux-64，需在已装 conda env（liuxslab::seq2neo）的 WSL/HPC 运行。\n"
            "  且硬依赖 netMHCpan-4.1.b + netCTLpan-1.1.b（后者 DTU 许可待申请，真阻塞）。",
            file=sys.stderr,
        )
        # 不在此处硬退出——交主线在正确环境跑；若确为缺环境会由 subprocess 报错。

    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        seq2neo_bin,
        "immuno",
        "--mode", "multiple",
        "--inputfile", str(in_csv),
        "--outdir", str(out_dir),
    ] + list(extra_args)

    print("[run_seq2neo] 命令:")
    print("  " + " ".join(cmd))
    print(f"[run_seq2neo] 输入: {in_csv}")
    print(f"[run_seq2neo] 输出目录: {out_dir}")
    print(f"[run_seq2neo] 预期产物: {out_dir / 'cnn_results.csv'}（+ immuno_input_file.csv）")
    print("[run_seq2neo] 注意: linux-only；依赖 netMHCpan-4.1.b + netCTLpan-1.1.b 在 PATH。")
    print("[run_seq2neo] 启动 seq2neo immuno ...")

    result = subprocess.run(cmd, check=False)

    if result.returncode != 0:
        print(
            f"[run_seq2neo] seq2neo 退出码: {result.returncode}\n"
            "  常见原因：netCTLpan/netMHCpan 不在 PATH、非 linux 平台、HLA/肽长不支持。",
            file=sys.stderr,
        )
        sys.exit(result.returncode)

    print(f"[run_seq2neo] 完成，输出目录: {out_dir}")
    print(f"[run_seq2neo] 下一步：python parse_output.py "
          f"--results {out_dir / 'cnn_results.csv'} [--score-col <列名>]")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    script_dir = pathlib.Path(__file__).parent
    default_in_dir = script_dir / "seq2neo_inputs"

    parser = argparse.ArgumentParser(
        description="调用 seq2neo immuno --mode multiple（linux-only，需 netMHCpan+netCTLpan）"
    )
    parser.add_argument(
        "--in-dir",
        default=str(default_in_dir),
        help="输入目录（默认 seq2neo_inputs/）",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="烟测：使用 seq2neo_input_smoke.csv，输出 seq2neo_out_smoke/",
    )
    parser.add_argument(
        "--seq2neo-bin",
        default="seq2neo",
        help="seq2neo 可执行名/路径（默认 `seq2neo`，假定在 conda env PATH 中）",
    )
    parser.add_argument(
        "--extra",
        nargs=argparse.REMAINDER,
        default=[],
        help="透传给 seq2neo 的额外参数（如 --threads N；置于命令末尾）",
    )
    args = parser.parse_args()

    suffix = "_smoke" if args.smoke else ""
    in_csv = pathlib.Path(args.in_dir) / f"seq2neo_input{suffix}.csv"
    out_dir = pathlib.Path(args.in_dir) / f"seq2neo_out{suffix}"

    run(
        seq2neo_bin=args.seq2neo_bin,
        in_csv=in_csv,
        out_dir=out_dir,
        extra_args=args.extra,
    )


if __name__ == "__main__":
    main()
