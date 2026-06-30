"""
run_mhcseqnet.py — QuantImmuBench §工具部署 P10槽  MHCSeqNet MHC-I 预测
服务项目：quantimmu-bench §工具部署 lever=补呈递组第 10 槽（替 MAAP）

功能（仿 mhcnuggets/run_mhcnuggets.py，但 MHCSeqNet = pan-allele 官方脚本/subprocess 调用）：
  1. 读 mhcseqnet_input.csv（prep_input.py 输出：peptide, HLA_Allele, mhcseqnet_allele）
  2. 写 MHCSeqNet 官方预测输入文件（pairs：allele + peptide）
  3. 在 repo 目录下 subprocess 调官方 predict 入口（加载 PretrainedModels/ 自带权重）
  4. 读回官方输出 → 按 (peptide, mhcseqnet_allele) join 回原始带星号 HLA_Allele
  5. 合并 → 写 mhcseqnet_raw.csv（peptide, HLA_Allele, prob）
  6. --smoke N: 用 N 个已知肽 × HLA-A*02:01 跑快速验证（默认 N=5），不写全量 raw CSV

==================== ⚠️ TODO（主线 clone repo 后必核，方可全量跑）====================
  MHCSeqNet 的「官方预测入口 + 输入文件格式 + 输出列名」当前**未经 repo 二次核实**
  （coder 无网络/repo 未 clone）。以下三处用最合理默认 + 配置参数占位，主线 clone
  github.com/cmb-chula/MHCSeqNet 后按 README/Script 核实并改：
    (A) PREDICT_SCRIPT_REL：官方 predict 脚本相对 repo 的路径（默认 'predict.py'）
        + PREDICT_ARGV 调用形式（默认 [script, IN, OUT]，TODO 核实是否需 --flag）
    (B) write_predict_input()：pairs 文件格式（默认每行 "<allele> <peptide>" 空格分隔、
        无表头）。TODO 核 README 的 PredictionInput 示例：是 CSV? TSV? 有表头? 列序?
    (C) read_predict_output()：官方输出列（默认 allele, peptide, prediction/prob）。
        TODO 核实际输出表头 + prob 列名。
  ❗ 必须 chdir 到 repo 目录跑（否则相对路径 PretrainedModels/ 加载不到权重）—— 已用 cwd=repo。
========================================================================================

输入：
  HPC/deploy/mhcseqnet/mhcseqnet_input.csv  （prep_input.py 生成）

输出：
  HPC/deploy/mhcseqnet/mhcseqnet_raw.csv     （peptide, HLA_Allele, prob）

部署环境（见 NOTES.md）：
  TF1 老栈（TF>=1.6 / Keras>=2.2），需独立 conda env（参考 ImmuneApp py3.7+TF1.15.0 先例）。
  纯 CPU 可跑，无需 GPU。
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

DEFAULT_INPUT = SCRIPT_DIR / "mhcseqnet_input.csv"
DEFAULT_RAW = SCRIPT_DIR / "mhcseqnet_raw.csv"
# repo clone 默认位置（主线 clone 后填实际路径，或用 --repo-dir 覆盖）
DEFAULT_REPO_DIR = SCRIPT_DIR / "repo"

# ✅ 主线核实（clone 后）：官方入口 = MHCSeqNet.py（repo 根）
#   CLI: python MHCSeqNet.py -p <PretrainedModels/sequence_model> -m sequence -i paired \
#        <peptide_file> <allele_file> <output_file>
#   peptide_file / allele_file 各单列无表头；output = TSV 'peptide\tallele\tprob' 无表头。
#   HLA 写法 = 'HLA-A*XX:YY'（带星号，= universe 原样，无需转）。肽 8-15mer。
PREDICT_SCRIPT_REL = "MHCSeqNet.py"
MODEL_SUBDIR = "PretrainedModels/sequence_model"

# 烟测用 5 个标准肽（HLA-A*02:01，pMHC-I 经典验证集；与 mhcnuggets 一致）
SMOKE_PEPTIDES = ["SIINFEKL", "NLVPMVATV", "GILGFVFTL", "KLGGALQAK", "YVLDHLIVV"]
SMOKE_HLA = "HLA-A*02:01"          # 原始带星号格式（universe 风格）


# ---------------------------------------------------------------------------
# 官方 predict 调用封装（subprocess；所有 repo-specific 细节集中此处，便于核实后改）
# ---------------------------------------------------------------------------

def read_predict_output(out_path: pathlib.Path) -> pd.DataFrame:
    """
    读官方 MHCSeqNet.py 输出（TSV 无表头，3 列 peptide\tallele\tprob），
    返回含 [mhcseqnet_allele, peptide, prob] 列的 DataFrame。
    """
    df = pd.read_csv(out_path, sep="\t", header=None,
                     names=["peptide", "mhcseqnet_allele", "prob"])
    out = pd.DataFrame({
        "mhcseqnet_allele": df["mhcseqnet_allele"].astype(str).str.strip(),
        "peptide": df["peptide"].astype(str).str.strip(),
        "prob": pd.to_numeric(df["prob"], errors="coerce"),
    })
    return out


def call_mhcseqnet_predict(pairs: list, repo_dir: pathlib.Path) -> pd.DataFrame:
    """
    subprocess 调官方 MHCSeqNet.py（sequence pan 模型，paired 模式），
    返回 [mhcseqnet_allele, peptide, prob]。

    官方 CLI（核实）:
      python MHCSeqNet.py -p <repo>/PretrainedModels/sequence_model -m sequence \
             -i paired <peptide_file> <allele_file> <output_file>
      peptide_file / allele_file 各单列无表头、行对齐（paired）。
    必须 cwd=repo（加载 PretrainedModels/ 相对路径 + 安装的 MHCSeqNet 包）。
    """
    predict_script = repo_dir / PREDICT_SCRIPT_REL
    if not predict_script.exists():
        print(f"[run_mhcseqnet] ERROR: 官方入口不存在: {predict_script}\n"
              f"  请先 clone: git clone https://github.com/cmb-chula/MHCSeqNet.git {repo_dir}",
              file=sys.stderr)
        sys.exit(1)

    tmp_dir = tempfile.mkdtemp(prefix="mhcseqnet_")
    pep_path = pathlib.Path(tmp_dir) / "peptides.txt"
    allele_path = pathlib.Path(tmp_dir) / "alleles.txt"
    out_path = pathlib.Path(tmp_dir) / "pred_output.tsv"
    # 2 单列文件，行对齐（paired）
    with open(pep_path, "w", encoding="utf-8") as fp, \
         open(allele_path, "w", encoding="utf-8") as fa:
        for allele, pep in pairs:
            fp.write(f"{pep}\n")
            fa.write(f"{allele}\n")

    model_path = repo_dir / MODEL_SUBDIR
    # ⚠️ 尾斜杠必加：官方 BindingPredictor 用 model_path + "model_N.h5" 字符串拼接
    argv = [sys.executable, str(predict_script),
            "-p", str(model_path) + "/", "-m", "sequence", "-i", "paired",
            str(pep_path), str(allele_path), str(out_path)]
    print(f"[run_mhcseqnet] 调官方: {' '.join(argv)}  (cwd={repo_dir})")
    proc = subprocess.run(argv, cwd=str(repo_dir), capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[run_mhcseqnet] ERROR: MHCSeqNet.py 退出码 {proc.returncode}\n"
              f"  stdout:\n{proc.stdout}\n  stderr:\n{proc.stderr}", file=sys.stderr)
        sys.exit(1)

    if not out_path.exists():
        print(f"[run_mhcseqnet] ERROR: 官方未产出 {out_path}\n"
              f"  stdout:\n{proc.stdout}", file=sys.stderr)
        sys.exit(1)

    return read_predict_output(out_path)


# ---------------------------------------------------------------------------
# 全量预测
# ---------------------------------------------------------------------------

def run_predictions(df_input: pd.DataFrame, repo_dir: pathlib.Path) -> pd.DataFrame:
    """
    df_input 列: peptide, HLA_Allele, mhcseqnet_allele。
    一次性把所有 (mhcseqnet_allele, peptide) pairs 交官方 predict（pan-allele），
    输出按 (peptide, mhcseqnet_allele) join 回原始带星号 HLA_Allele。
    """
    pairs = list(zip(df_input["mhcseqnet_allele"].tolist(),
                     df_input["peptide"].tolist()))
    print(f"[run_mhcseqnet] 共 {len(pairs)} 个 (allele,peptide) pairs，交官方 predict...")
    pred = call_mhcseqnet_predict(pairs, repo_dir)

    # join 回原始带星号 HLA_Allele（按 peptide + mhcseqnet_allele）
    merged = pred.merge(
        df_input[["peptide", "HLA_Allele", "mhcseqnet_allele"]].drop_duplicates(),
        on=["peptide", "mhcseqnet_allele"], how="left",
    )
    out = merged[["peptide", "HLA_Allele", "prob"]].copy()
    n_nan_hla = int(out["HLA_Allele"].isna().sum())
    if n_nan_hla:
        print(f"[run_mhcseqnet] WARNING: {n_nan_hla} 行 join 不回原始 HLA（核 allele 写法一致性）",
              file=sys.stderr)
    return out


# ---------------------------------------------------------------------------
# 烟测
# ---------------------------------------------------------------------------

def run_smoke(n: int, repo_dir: pathlib.Path) -> None:
    """快速 smoke test：n 个已知肽 × HLA-A*02:01 验证官方调用链 + 输出列结构。"""
    smoke_peps = SMOKE_PEPTIDES[:n]
    seqnet_allele = SMOKE_HLA   # to_mhcseqnet_allele 当前 identity（见 prep_input.py TODO）
    print(f"\n[smoke] 烟测 {len(smoke_peps)} 肽 × allele={SMOKE_HLA}")
    pairs = [(seqnet_allele, p) for p in smoke_peps]
    pred = call_mhcseqnet_predict(pairs, repo_dir)
    print("[smoke] 输出 DataFrame:")
    print(pred.to_string(index=False))
    print(f"\n[smoke] 列名: {list(pred.columns)}")
    print("[smoke] 烟测通过。prob∈[0,1]（越高越强结合）有值即 OK。")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="MHCSeqNet MHC-I 批量预测（pan-allele，subprocess 调官方 predict）"
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="mhcseqnet_input.csv 路径（prep_input.py 生成）",
    )
    parser.add_argument(
        "--raw-out",
        default=str(DEFAULT_RAW),
        help="原始预测结果输出路径（默认 mhcseqnet_raw.csv）",
    )
    parser.add_argument(
        "--repo-dir",
        default=str(DEFAULT_REPO_DIR),
        help="MHCSeqNet repo clone 目录（含 predict 脚本 + PretrainedModels/）",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        metavar="N",
        default=0,
        help="烟测模式：只跑 N 个已知肽验证官方调用，不写全量 raw CSV（N=0=关闭）",
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
        print(f"[run_mhcseqnet] ERROR: 输入文件不存在: {input_path}", file=sys.stderr)
        print("  请先运行: python prep_input.py", file=sys.stderr)
        sys.exit(1)

    df_input = pd.read_csv(input_path, dtype=str, encoding="utf-8")
    print(f"[run_mhcseqnet] 读入 {len(df_input)} 行 from {input_path}")

    for col in ["peptide", "HLA_Allele", "mhcseqnet_allele"]:
        if col not in df_input.columns:
            print(f"[run_mhcseqnet] ERROR: 输入缺列 '{col}'，实际: {list(df_input.columns)}", file=sys.stderr)
            sys.exit(1)

    combined = run_predictions(df_input, repo_dir)
    combined = combined[["peptide", "HLA_Allele", "prob"]]

    raw_out = pathlib.Path(args.raw_out)
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(raw_out, index=False, encoding="utf-8", line_terminator="\n")

    print(f"\n[run_mhcseqnet] 完成。写入 {len(combined)} 行 → {raw_out}")
    print(f"[run_mhcseqnet] 列: {list(combined.columns)}")
    valid = combined["prob"].dropna()
    if len(valid):
        print(f"[run_mhcseqnet] prob 统计: min={valid.min():.4f}  max={valid.max():.4f}  median={valid.median():.4f}")
    print("[run_mhcseqnet] 注意：prob 越高越强结合；parse_output.py 不翻转方向。")


if __name__ == "__main__":
    main()
