"""
run_mhcnuggets.py — QuantImmuBench §工具部署 P10  MHCnuggets MHC-I 预测
服务项目：quantimmu-bench §工具部署 lever=补满30工具呈递槽 P10

功能：
  1. 读 mhcnuggets_input.csv（prep_input.py 的输出，列：peptide, HLA_Allele, mhcnuggets_allele）
  2. 按 mhcnuggets_allele 分组，对每组：
       a. 把该组肽写成临时换行分隔文本文件（MHCnuggets 要求 peptides_path 为换行文件）
       b. 调官方 predict(class_='I', peptides_path=<tmp>, mhc=<allele 无星号>, output=<tmp_out>)
       c. 读回 output（CSV：peptide,ic50），附上 HLA_Allele（原始带星号格式，便于回贴 universe）
  3. 合并所有组 → 写 mhcnuggets_raw.csv（peptide, HLA_Allele, ic50）
  4. --smoke N: 用 N 个已知肽 × HLA-A*02:01 跑快速验证（默认 N=5），不写 raw CSV

输入：
  HPC/deploy/mhcnuggets/mhcnuggets_input.csv  （prep_input.py 生成）

输出：
  HPC/deploy/mhcnuggets/mhcnuggets_raw.csv

官方 API（2026-06-29 核自 github.com/KarchinLab/mhcnuggets master mhcnuggets/src/predict.py）：
  from mhcnuggets.src.predict import predict
  predict(class_, peptides_path, mhc, output=None, ...)
    - class_: 'I' (MHC-I) 或 'II'
    - peptides_path: 换行分隔的肽文件路径（不是 list！源码 peptides=[p.strip() for p in open(path)]）
    - mhc: 单个 allele 字符串，格式 HLA-A02:01（无星号）；一次只跑一个 allele
    - output: 输出文件路径（None→stdout）；输出 CSV 表头 'peptide,ic50'
    - ic50 单位 nM，越低越强（binding affinity）
  MHCnuggets 用 closest_allele() 做模糊匹配——allele 不在训练集时自动选最近/默认 pan model，
  不会硬报错（默认 pan: HLA-A02:01 / HLA-B07:02 / HLA-C04:01）。
  权重内置 pip 包（saves/production/<allele>_BA_to_HLAp.h5 或 _BA.h5），无需额外下载。

部署环境：MHCnuggets 依赖 tensorflow/keras。建议 Linux/WSL2 + conda 跑（见 NOTES.md）。
  CPU 即可，无需 GPU。
"""

import argparse
import os
import pathlib
import sys
import tempfile

import pandas as pd

# ---------------------------------------------------------------------------
# 路径默认值
# ---------------------------------------------------------------------------
SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_INPUT = SCRIPT_DIR / "mhcnuggets_input.csv"
DEFAULT_RAW = SCRIPT_DIR / "mhcnuggets_raw.csv"

# 烟测用 5 个标准肽（HLA-A*02:01，长度 8-9mer，pMHC-I 经典验证集）
SMOKE_PEPTIDES = ["SIINFEKL", "NLVPMVATV", "GILGFVFTL", "KLGGALQAK", "YVLDHLIVV"]
SMOKE_HLA = "HLA-A*02:01"          # 原始带星号格式（universe 风格）


# ---------------------------------------------------------------------------
# 官方 predict 封装
# ---------------------------------------------------------------------------

def load_predict_fn():
    try:
        from mhcnuggets.src.predict import predict
    except ImportError:
        print("[run_mhcnuggets] ERROR: mhcnuggets 未安装。请先 pip install mhcnuggets", file=sys.stderr)
        sys.exit(1)
    return predict


def to_mhcnuggets_allele(hla: str) -> str:
    """HLA-A*02:01 → HLA-A02:01（去星号），与 prep_input.py 保持一致。"""
    return hla.replace("*", "")


def predict_for_allele(predict_fn, peptides: list, mhcn_allele: str) -> pd.DataFrame:
    """
    对一个 allele 的所有 peptide 调官方 predict。
    mhcn_allele 必须是无星号格式（HLA-A02:01）。
    官方 predict 把肽写到 peptides_path 文件、结果写到 output 文件（CSV: peptide,ic50）。
    返回含 peptide / ic50 列的 DataFrame（不含 HLA，由调用方补）。
    """
    tmp_dir = tempfile.mkdtemp(prefix="mhcn_")
    pep_file = os.path.join(tmp_dir, "peptides.txt")
    out_file = os.path.join(tmp_dir, "out.csv")

    # 写换行分隔肽文件（官方 peptides=[p.strip() for p in open(path)]）
    with open(pep_file, "w", encoding="utf-8") as fh:
        for p in peptides:
            fh.write(p + "\n")

    # 调官方 predict（MHC-I）
    predict_fn(
        class_="I",
        peptides_path=pep_file,
        mhc=mhcn_allele,
        output=out_file,
    )

    # 读回结果（CSV 表头 peptide,ic50）
    out_df = pd.read_csv(out_file, dtype={"peptide": str})
    out_df["peptide"] = out_df["peptide"].str.strip()
    return out_df[["peptide", "ic50"]].copy()


def run_predictions(predict_fn, df_input: pd.DataFrame) -> pd.DataFrame:
    """
    按 (HLA_Allele, mhcnuggets_allele) 分组逐组预测，合并结果。
    df_input 列: peptide, HLA_Allele, mhcnuggets_allele
    raw 输出附原始带星号 HLA_Allele（便于回贴 universe）。
    """
    all_results = []
    groups = df_input.groupby(["HLA_Allele", "mhcnuggets_allele"])
    n_groups = len(groups)

    for i, ((hla, mhcn_allele), grp) in enumerate(groups, 1):
        peptides = grp["peptide"].tolist()
        print(f"[run_mhcnuggets] ({i}/{n_groups}) {hla} (→{mhcn_allele}): {len(peptides)} 肽...")
        try:
            df_pred = predict_for_allele(predict_fn, peptides, mhcn_allele)
            df_pred["HLA_Allele"] = hla   # 原始带星号格式
            all_results.append(df_pred)
        except Exception as exc:
            # 预测失败 → 跳过，parse 阶段填 NaN
            print(f"[run_mhcnuggets] WARNING: {hla} 预测失败，跳过: {exc}", file=sys.stderr)

    if not all_results:
        print("[run_mhcnuggets] ERROR: 没有任何预测成功。", file=sys.stderr)
        sys.exit(1)

    combined = pd.concat(all_results, ignore_index=True)
    return combined


# ---------------------------------------------------------------------------
# 烟测
# ---------------------------------------------------------------------------

def run_smoke(predict_fn, n: int) -> None:
    """快速 smoke test：用 n 个已知肽 × HLA-A*02:01 验证 API 和列结构。"""
    smoke_peps = SMOKE_PEPTIDES[:n]
    mhcn_allele = to_mhcnuggets_allele(SMOKE_HLA)
    print(f"\n[smoke] 烟测 {len(smoke_peps)} 肽 × allele={SMOKE_HLA} (→{mhcn_allele})")
    df = predict_for_allele(predict_fn, smoke_peps, mhcn_allele)
    df["HLA_Allele"] = SMOKE_HLA
    print("[smoke] 输出 DataFrame:")
    print(df.to_string(index=False))
    print(f"\n[smoke] 列名: {list(df.columns)}")
    print("[smoke] 烟测通过。ic50(nM, 越低越强) 有值即 OK。")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="MHCnuggets MHC-I 批量预测（按 HLA allele 分组调官方 predict）"
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="mhcnuggets_input.csv 路径（prep_input.py 生成）",
    )
    parser.add_argument(
        "--raw-out",
        default=str(DEFAULT_RAW),
        help="原始预测结果输出路径（默认 mhcnuggets_raw.csv）",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        metavar="N",
        default=0,
        help="烟测模式：只跑 N 个已知肽验证 API，不写 raw CSV（N=0=关闭）",
    )
    args = parser.parse_args()

    predict_fn = load_predict_fn()

    # --- 烟测分支 ---
    if args.smoke > 0:
        run_smoke(predict_fn, args.smoke)
        return

    # --- 全量预测 ---
    input_path = pathlib.Path(args.input)
    if not input_path.exists():
        print(f"[run_mhcnuggets] ERROR: 输入文件不存在: {input_path}", file=sys.stderr)
        print("  请先运行: python prep_input.py", file=sys.stderr)
        sys.exit(1)

    df_input = pd.read_csv(input_path, dtype=str, encoding="utf-8")
    print(f"[run_mhcnuggets] 读入 {len(df_input)} 行 from {input_path}")

    for col in ["peptide", "HLA_Allele", "mhcnuggets_allele"]:
        if col not in df_input.columns:
            print(f"[run_mhcnuggets] ERROR: 输入缺列 '{col}'，实际: {list(df_input.columns)}", file=sys.stderr)
            sys.exit(1)

    n_alleles = df_input["mhcnuggets_allele"].nunique()
    print(f"[run_mhcnuggets] 共 {n_alleles} 个 HLA allele，按组逐一预测...")

    combined = run_predictions(predict_fn, df_input)

    # 列顺序
    combined = combined[["peptide", "HLA_Allele", "ic50"]]

    raw_out = pathlib.Path(args.raw_out)
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(raw_out, index=False, encoding="utf-8", lineterminator="\n")

    print(f"\n[run_mhcnuggets] 完成。写入 {len(combined)} 行 → {raw_out}")
    print(f"[run_mhcnuggets] 列: {list(combined.columns)}")
    print(f"[run_mhcnuggets] ic50(nM) 统计: min={combined['ic50'].min():.1f}  max={combined['ic50'].max():.1f}  median={combined['ic50'].median():.1f}")
    print("[run_mhcnuggets] 注意：ic50 越低越强；parse_output.py 会取负做方向归一。")


if __name__ == "__main__":
    main()
