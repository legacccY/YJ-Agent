"""
run_deepnetbim.py — QuantImmuBench §工具部署 第20槽  DeepNetBim 免疫原性预测
服务项目：quantimmu-bench §工具部署 lever=补免疫原性组第 20 槽（DeepNetBim）

功能（仿 mhcseqnet/run_mhcseqnet.py，subprocess 调官方 predict）：
  1. 读 deepnetbim_input.csv（prep_input.py 输出：peptide, HLA_Allele, mhc, sequence）
  2. 写 DeepNetBim 官方预测输入 CSV（两列 mhc, sequence）
  3. 在 repo 目录下 subprocess 调官方 predict 入口（cwd=repo 保证相对路径
     data/model_immuno.h5 自带权重可加载）—— **用 immuno 模型，非 binding 模型**
  4. 读回官方输出 → 含 immuno_probability 列
  5. 写 deepnetbim_raw.csv（mhc, sequence, immuno_probability）
  6. --smoke N: 用 N 个已知 9mer 肽 × HLA-A*02:01 跑快速验证（默认 N=5），不写全量 raw

==================== ⚠️ TODO（主线 clone repo 后必核，方可全量跑）====================
  DeepNetBim 的「官方预测入口 + 输入文件格式 + 输出列名 + immuno 模型选择参数」当前
  **未经 repo 二次核实**（coder 无网络/repo 未 clone）。以下用最合理默认 + 配置参数占位，
  主线 clone github.com/Li-Lab-SJTU/DeepNetBim 后按 README/示例核实并改：
    (A) PREDICT_SCRIPT_REL：官方 predict 脚本相对 repo 的路径（默认 'predict.py'）
        + PREDICT_ARGV 调用形式。❗DeepNetBim 有 immuno + bind 两个模型
        （data/model_immuno.h5 + data/model_bind.h5），**本工具用 immuno**
        → TODO 核官方如何选模型（默认 --model immuno 或 --weights data/model_immuno.h5，
        见 IMMUNO_MODEL_REL + PREDICT_ARGV，主线核 README 后改）。
    (B) write_predict_input()：输入文件格式（默认 CSV 两列表头 'mhc,sequence'）。
        TODO 核 README 示例：列名/列序/分隔符是否一致？
    (C) read_predict_output()：官方输出列（默认含 mhc, sequence, immuno_probability）。
        TODO 核实际输出表头 + 概率列名（immuno_probability vs probability vs score）。
  ❗ 必须 chdir 到 repo 目录跑（否则相对路径 data/model_immuno.h5 加载不到权重）—— 已 cwd=repo。
========================================================================================

输入：
  HPC/deploy/deepnetbim/deepnetbim_input.csv  （prep_input.py 生成）

输出：
  HPC/deploy/deepnetbim/deepnetbim_raw.csv     （mhc, sequence, immuno_probability）

部署环境（见 NOTES.md）：
  TF1 老栈（keras 2.2.4），需独立 conda env（参考 ImmuneApp py3.7+TF1.15.0 先例，TODO 核 pin）。
  纯 CPU 可跑（秒级/肽），无需 GPU。
"""

import argparse
import os
import pathlib
import subprocess
import sys
import tempfile

import pandas as pd

# ---------------------------------------------------------------------------
# 路径默认值
# ---------------------------------------------------------------------------
SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_INPUT = SCRIPT_DIR / "deepnetbim_input.csv"
DEFAULT_RAW = SCRIPT_DIR / "deepnetbim_raw.csv"
# repo clone 默认位置（主线 clone 后填实际路径，或用 --repo-dir 覆盖）
DEFAULT_REPO_DIR = SCRIPT_DIR / "repo"

# ⚠️ TODO(A)：官方 predict 脚本相对 repo 的路径 + 调用形式
PREDICT_SCRIPT_REL = "predict.py"   # TODO 核 repo（可能别名/子目录）
# ⚠️ TODO(A)：immuno 模型权重相对 repo 的路径（本工具用免疫原模型，非 binding）
IMMUNO_MODEL_REL = "data/model_immuno.h5"   # repo 自带，36.4MB

# 烟测用 5 个标准 **9mer** 肽（HLA-A*02:01，pMHC-I 经典验证集；DeepNetBim 仅 9mer）
SMOKE_PEPTIDES = ["NLVPMVATV", "GILGFVFTL", "KLGGALQAK", "YVLDHLIVV", "SLYNTVATL"]
SMOKE_HLA = "HLA-A*02:01"          # 原始带星号格式（universe 风格）


def _to_deepnetbim_allele(hla: str) -> str:
    """与 prep_input.to_deepnetbim_allele 一致：去星保冒号（HLA-A*02:01 → HLA-A02:01）。"""
    return hla.replace("*", "")


# ---------------------------------------------------------------------------
# 官方 predict 调用封装（subprocess；所有 repo-specific 细节集中此处，便于核实后改）
# ---------------------------------------------------------------------------

def write_predict_input(pairs: list, in_path: pathlib.Path) -> None:
    """
    写 DeepNetBim 官方预测输入 CSV。pairs = [(mhc, sequence), ...]，mhc 为去星格式。

    ⚠️ TODO(B)：默认 CSV 两列表头 'mhc,sequence'。
       主线核 README 示例后改为真实格式（列名/列序/分隔符）。
    """
    df = pd.DataFrame(pairs, columns=["mhc", "sequence"])
    df.to_csv(in_path, index=False, encoding="utf-8", line_terminator="\n")


def read_predict_output(out_path: pathlib.Path) -> pd.DataFrame:
    """
    读官方预测输出，返回含 [mhc, sequence, immuno_probability] 列的 DataFrame。

    ⚠️ TODO(C)：默认假设输出可被 pandas 读、含 mhc/sequence/immuno_probability 列。
       主线核实际输出表头后改列名映射。当前做容错：自动找概率列。
    """
    df = pd.read_csv(out_path)
    df.columns = [c.strip() for c in df.columns]
    cols_lower = {c.lower(): c for c in df.columns}

    # 自动识别列（TODO 核实后可硬编码真实列名）
    mhc_col = next((cols_lower[k] for k in cols_lower
                    if k in ("mhc", "allele", "hla")), df.columns[0])
    seq_col = next((cols_lower[k] for k in cols_lower
                    if k in ("sequence", "peptide", "pep")), df.columns[1])
    prob_col = next((cols_lower[k] for k in cols_lower
                     if k in ("immuno_probability", "immuno_prob", "probability",
                              "prob", "score", "immunogenicity")),
                    df.columns[-1])

    out = pd.DataFrame({
        "mhc": df[mhc_col].astype(str).str.strip(),
        "sequence": df[seq_col].astype(str).str.strip(),
        "immuno_probability": pd.to_numeric(df[prob_col], errors="coerce"),
    })
    return out


def call_deepnetbim_predict(pairs: list, repo_dir: pathlib.Path) -> pd.DataFrame:
    """
    subprocess 调官方 predict 脚本（immuno 模型），返回 [mhc, sequence, immuno_probability]。

    ⚠️ TODO(A)：默认命令
       `python <repo>/predict.py --model data/model_immuno.h5 <IN> <OUT>`（cwd=repo，
       确保相对路径 data/model_immuno.h5 可加载）。主线核 README 后改 argv
       （脚本名/选 immuno 模型的 flag/参数序）。
    """
    predict_script = repo_dir / PREDICT_SCRIPT_REL
    if not predict_script.exists():
        print(f"[run_deepnetbim] ERROR: 官方 predict 脚本不存在: {predict_script}\n"
              f"  请先 clone: git clone https://github.com/Li-Lab-SJTU/DeepNetBim.git {repo_dir}\n"
              f"  并核实 PREDICT_SCRIPT_REL（当前='{PREDICT_SCRIPT_REL}'，见脚本 TODO(A)）",
              file=sys.stderr)
        sys.exit(1)

    model_path = repo_dir / IMMUNO_MODEL_REL
    if not model_path.exists():
        print(f"[run_deepnetbim] WARNING: immuno 模型权重未找到: {model_path}\n"
              f"  DeepNetBim 应 repo 内自带 {IMMUNO_MODEL_REL}（36.4MB），"
              f"核 clone 是否完整 / 路径是否 TODO(A)。", file=sys.stderr)

    tmp_dir = tempfile.mkdtemp(prefix="deepnetbim_")
    in_path = pathlib.Path(tmp_dir) / "pred_input.csv"
    out_path = pathlib.Path(tmp_dir) / "pred_output.csv"
    write_predict_input(pairs, in_path)

    # ⚠️ TODO(A)：核实 argv 形式（选 immuno 模型的 flag / 输入输出参数序）
    argv = [sys.executable, str(predict_script),
            "--model", IMMUNO_MODEL_REL,
            str(in_path), str(out_path)]
    print(f"[run_deepnetbim] 调官方 predict(immuno): {' '.join(argv)}  (cwd={repo_dir})")
    proc = subprocess.run(argv, cwd=str(repo_dir), capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[run_deepnetbim] ERROR: predict 退出码 {proc.returncode}\n"
              f"  stdout:\n{proc.stdout}\n  stderr:\n{proc.stderr}", file=sys.stderr)
        sys.exit(1)

    if not out_path.exists():
        print(f"[run_deepnetbim] ERROR: 官方未产出 {out_path}（核 TODO(A) 输出参数）\n"
              f"  stdout:\n{proc.stdout}", file=sys.stderr)
        sys.exit(1)

    return read_predict_output(out_path)


# ---------------------------------------------------------------------------
# 全量预测
# ---------------------------------------------------------------------------

def run_predictions(df_input: pd.DataFrame, repo_dir: pathlib.Path) -> pd.DataFrame:
    """
    df_input 列: peptide, HLA_Allele, mhc, sequence。
    把所有 (mhc, sequence) pairs 交官方 predict（immuno 模型），
    输出 deepnetbim_raw.csv schema = mhc, sequence, immuno_probability。
    （原始带星号 HLA_Allele 的回贴在 parse_output.py 做：mhc 去星 → 重建带星查 universe）
    """
    pairs = list(zip(df_input["mhc"].tolist(), df_input["sequence"].tolist()))
    print(f"[run_deepnetbim] 共 {len(pairs)} 个 (mhc,sequence) pairs，交官方 predict(immuno)...")
    pred = call_deepnetbim_predict(pairs, repo_dir)
    return pred[["mhc", "sequence", "immuno_probability"]]


# ---------------------------------------------------------------------------
# 烟测
# ---------------------------------------------------------------------------

def run_smoke(n: int, repo_dir: pathlib.Path) -> None:
    """快速 smoke test：n 个已知 9mer 肽 × HLA-A*02:01 验证官方调用链 + 输出列结构。"""
    smoke_peps = SMOKE_PEPTIDES[:n]
    db_allele = _to_deepnetbim_allele(SMOKE_HLA)   # HLA-A*02:01 → HLA-A02:01
    print(f"\n[smoke] 烟测 {len(smoke_peps)} 个 9mer 肽 × mhc={db_allele}（源 {SMOKE_HLA}）")
    pairs = [(db_allele, p) for p in smoke_peps]
    pred = call_deepnetbim_predict(pairs, repo_dir)
    print("[smoke] 输出 DataFrame:")
    print(pred.to_string(index=False))
    print(f"\n[smoke] 列名: {list(pred.columns)}")
    print("[smoke] 烟测通过：immuno_probability∈[0,1]（越高越免疫原）有值即 OK。")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="DeepNetBim 免疫原性批量预测（immuno 模型，subprocess 调官方 predict）"
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="deepnetbim_input.csv 路径（prep_input.py 生成）",
    )
    parser.add_argument(
        "--raw-out",
        default=str(DEFAULT_RAW),
        help="原始预测结果输出路径（默认 deepnetbim_raw.csv）",
    )
    parser.add_argument(
        "--repo-dir",
        default=str(DEFAULT_REPO_DIR),
        help="DeepNetBim repo clone 目录（含 predict 脚本 + data/model_immuno.h5）",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        metavar="N",
        default=0,
        help="烟测模式：只跑 N 个已知 9mer 肽验证官方调用，不写全量 raw CSV（N=0=关闭）",
    )
    args = parser.parse_args()

    repo_dir = pathlib.Path(args.repo_dir)

    # --- 烟测分支 ---
    if args.smoke > 0:
        run_smoke(args.smoke, repo_dir)
        return

    # --- 全量预测 ---
    input_path = pathlib.Path(args.input)
    if not input_path.exists():
        print(f"[run_deepnetbim] ERROR: 输入文件不存在: {input_path}", file=sys.stderr)
        print("  请先运行: python prep_input.py", file=sys.stderr)
        sys.exit(1)

    df_input = pd.read_csv(input_path, dtype=str, encoding="utf-8")
    print(f"[run_deepnetbim] 读入 {len(df_input)} 行 from {input_path}")

    for col in ["peptide", "HLA_Allele", "mhc", "sequence"]:
        if col not in df_input.columns:
            print(f"[run_deepnetbim] ERROR: 输入缺列 '{col}'，实际: {list(df_input.columns)}", file=sys.stderr)
            sys.exit(1)

    combined = run_predictions(df_input, repo_dir)
    combined = combined[["mhc", "sequence", "immuno_probability"]]

    raw_out = pathlib.Path(args.raw_out)
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(raw_out, index=False, encoding="utf-8", line_terminator="\n")

    print(f"\n[run_deepnetbim] 完成。写入 {len(combined)} 行 → {raw_out}")
    print(f"[run_deepnetbim] 列: {list(combined.columns)}")
    valid = combined["immuno_probability"].dropna()
    if len(valid):
        print(f"[run_deepnetbim] immuno_probability 统计: min={valid.min():.4f}  "
              f"max={valid.max():.4f}  median={valid.median():.4f}")
    print("[run_deepnetbim] 注意：immuno_probability 越高越免疫原；parse_output.py 不翻转方向。")


if __name__ == "__main__":
    main()
