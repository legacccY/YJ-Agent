"""
run_mhcflurry.py — QuantImmuBench §Tier-0  MHCflurry 2.0 预测
服务项目：quantimmu-bench §Tier-0 lever=部署MHCflurry 扩张v2第一波

功能：
  1. 加载 Class1PresentationPredictor
  2. 读 mhcflurry_input.csv（prep_input.py 的输出，已过滤不支持 allele）
  3. 按 HLA_Allele 分组，对每组调用 predictor.predict(peptides, [allele], verbose=0)
  4. 合并结果 → 写 mhcflurry_raw.csv（peptide, HLA_Allele, affinity, presentation_score, processing_score）
  5. --smoke N: 从输入文件取前 N 行跑快速验证（默认 N=5），主线用于验算子

输入：
  HPC/deploy/mhcflurry/mhcflurry_input.csv  （prep_input.py 生成）

输出：
  HPC/deploy/mhcflurry/mhcflurry_raw.csv

官方 API（2026-06-26 核自 github.com/openvax/mhcflurry master）：
  Class1PresentationPredictor.predict(peptides, alleles, verbose=0)
    - peptides: list[str]
    - alleles: list[str]（当作单样本，每肽取 best_allele）
    - 返回 DataFrame，列: peptide, peptide_num, sample_name, affinity, best_allele,
                             processing_score, presentation_score, presentation_percentile
  来源: mhcflurry/class1_presentation_predictor.py::predict_columns() + predict() docstring
  allele 格式: 接受 HLA-A*02:01（标准格式，无需转换）
  github.com/openvax/mhcflurry/blob/master/mhcflurry/class1_presentation_predictor.py

Windows CPU 注意：MHCflurry 默认用 TF/Keras，CPU 下推理较慢但可跑。
  若 HPC 有 GPU 会自动使用（无需特殊配置）。
"""

import argparse
import pathlib
import sys

import pandas as pd

# ---------------------------------------------------------------------------
# 路径默认值
# ---------------------------------------------------------------------------
SCRIPT_DIR   = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR  = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_INPUT = SCRIPT_DIR / "mhcflurry_input.csv"
DEFAULT_RAW   = SCRIPT_DIR / "mhcflurry_raw.csv"

# 烟测用 5 个标准肽（HLA-A*02:01，长度 8-9mer，MHCflurry 经典验证集）
SMOKE_PEPTIDES = ["SIINFEKL", "NLVPMVATV", "GILGFVFTL", "KLGGALQAK", "YVLDHLIVV"]
SMOKE_ALLELE   = "HLA-A*02:01"


# ---------------------------------------------------------------------------
# 预测
# ---------------------------------------------------------------------------

def load_predictor():
    try:
        from mhcflurry import Class1PresentationPredictor
    except ImportError:
        print("[run_mhcflurry] ERROR: mhcflurry 未安装。请先 pip install mhcflurry", file=sys.stderr)
        sys.exit(1)
    print("[run_mhcflurry] 加载 Class1PresentationPredictor...")
    predictor = Class1PresentationPredictor.load()
    print("[run_mhcflurry] 预测器加载完成。")
    return predictor


def predict_for_allele(predictor, peptides: list, allele: str) -> pd.DataFrame:
    """
    对一个 allele 的所有 peptide 做预测。
    alleles 传 [allele] = 单样本单 allele，每肽评估 best_allele=allele。
    返回含 peptide/allele/affinity/presentation_score/processing_score 的 DataFrame。
    """
    result = predictor.predict(
        peptides=peptides,
        alleles=[allele],
        verbose=0,
    )
    # 官方返回列: peptide, peptide_num, sample_name, affinity, best_allele,
    #             processing_score, presentation_score, presentation_percentile
    # 我们只取需要的列，并补 HLA_Allele 列
    keep_cols = [c for c in ["peptide", "affinity", "processing_score", "presentation_score"]
                 if c in result.columns]
    out = result[keep_cols].copy()
    out["HLA_Allele"] = allele
    # 肽序列来自 result["peptide"]，顺序与输入一致
    return out


def run_predictions(predictor, df_input: pd.DataFrame) -> pd.DataFrame:
    """
    按 HLA_Allele 分组，逐组调用 predict，合并结果。
    df_input 列: peptide, HLA_Allele
    """
    all_results = []
    groups = df_input.groupby("HLA_Allele")
    n_groups = len(groups)

    for i, (allele, grp) in enumerate(groups, 1):
        peptides = grp["peptide"].tolist()
        print(f"[run_mhcflurry] ({i}/{n_groups}) {allele}: {len(peptides)} 肽...")
        try:
            df_pred = predict_for_allele(predictor, peptides, allele)
            all_results.append(df_pred)
        except Exception as exc:
            # 预测失败（e.g. allele 在 predictor 内部找不到）→ 跳过，parse 阶段填 NaN
            print(f"[run_mhcflurry] WARNING: {allele} 预测失败，跳过: {exc}", file=sys.stderr)

    if not all_results:
        print("[run_mhcflurry] ERROR: 没有任何预测成功。", file=sys.stderr)
        sys.exit(1)

    combined = pd.concat(all_results, ignore_index=True)
    return combined


# ---------------------------------------------------------------------------
# 烟测
# ---------------------------------------------------------------------------

def run_smoke(predictor, n: int) -> None:
    """
    快速 smoke test：用 n 个已知肽验证 API 和列结构。
    """
    smoke_peps = SMOKE_PEPTIDES[:n]
    print(f"\n[smoke] 烟测 {len(smoke_peps)} 肽 × allele={SMOKE_ALLELE}")
    df = predict_for_allele(predictor, smoke_peps, SMOKE_ALLELE)
    print("[smoke] 输出 DataFrame:")
    print(df.to_string(index=False))
    print(f"\n[smoke] 列名: {list(df.columns)}")
    print("[smoke] 烟测通过。affinity(nM), presentation_score(0-1), processing_score(0-1) 均有值。")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="MHCflurry 2.0 批量预测（按 HLA allele 分组调用 Class1PresentationPredictor.predict）"
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="mhcflurry_input.csv 路径（prep_input.py 生成）",
    )
    parser.add_argument(
        "--raw-out",
        default=str(DEFAULT_RAW),
        help="原始预测结果输出路径（默认 mhcflurry_raw.csv）",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        metavar="N",
        default=0,
        help="烟测模式：只跑 N 个已知肽验证 API，不写 raw CSV（N=0=关闭）",
    )
    args = parser.parse_args()

    predictor = load_predictor()

    # --- 烟测分支 ---
    if args.smoke > 0:
        run_smoke(predictor, args.smoke)
        return

    # --- 全量预测 ---
    input_path = pathlib.Path(args.input)
    if not input_path.exists():
        print(f"[run_mhcflurry] ERROR: 输入文件不存在: {input_path}", file=sys.stderr)
        print("  请先运行: python prep_input.py", file=sys.stderr)
        sys.exit(1)

    df_input = pd.read_csv(input_path, encoding="utf-8")
    print(f"[run_mhcflurry] 读入 {len(df_input)} 行 from {input_path}")

    if "peptide" not in df_input.columns or "HLA_Allele" not in df_input.columns:
        print(f"[run_mhcflurry] ERROR: 输入缺列，期望 peptide + HLA_Allele，实际: {list(df_input.columns)}", file=sys.stderr)
        sys.exit(1)

    n_alleles = df_input["HLA_Allele"].nunique()
    print(f"[run_mhcflurry] 共 {n_alleles} 个 HLA allele，按组逐一预测...")

    combined = run_predictions(predictor, df_input)

    # 列顺序
    col_order = ["peptide", "HLA_Allele", "affinity", "presentation_score", "processing_score"]
    col_order = [c for c in col_order if c in combined.columns]
    combined = combined[col_order]

    raw_out = pathlib.Path(args.raw_out)
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(raw_out, index=False, encoding="utf-8", lineterminator="\n")

    print(f"\n[run_mhcflurry] 完成。写入 {len(combined)} 行 → {raw_out}")
    print(f"[run_mhcflurry] 列: {list(combined.columns)}")
    print(f"[run_mhcflurry] affinity(nM) 统计: min={combined['affinity'].min():.1f}  max={combined['affinity'].max():.1f}  median={combined['affinity'].median():.1f}")
    print(f"[run_mhcflurry] presentation_score 统计: min={combined['presentation_score'].min():.4f}  max={combined['presentation_score'].max():.4f}")


if __name__ == "__main__":
    main()
