"""
run_mhcflurry_101102.py — QuantImmuBench §Phase B  MHCflurry 2.0 患者 101/102 重推理
服务项目：quantimmu-bench §Phase B lever=订正 HLA 等位重推理 MHCflurry 填合表缺口

背景：
  患者 101/102 旧推理用了错误的 HLA 等位。Phase B 用订正后的真值等位重推理：
    P101 = {A*66:01, B*40:01, B*57:01, C*06:02}
    P102 = {A*02:01, B*35:03, B*38:01}
  唯一订正输入源 = scripts/out/phaseB/backbone_101102.csv（4018 行，HLA_Allele 列已订正）。
  本脚本 prep+predict+parse 一体，只从 backbone 派生，不读旧 mhcflurry_input.csv。

流程：
  1. 读 backbone_101102.csv（列含 bb_idx, MT_Subpeptide, WT_Subpeptide, HLA_Allele, Window_Size）
  2. 收集每个 allele 下需打分的肽（MT ∪ WT 去重）→ 按 allele 分组调 predict
  3. 建 (peptide, HLA_Allele) → {presentation_score, affinity} 查找表
  4. 对 backbone 每行回贴 MT/WT 分数，按 bb_idx 输出
  5. 方向归一（与 parse_output.py 完全一致）：
       presentation_score: 越高越强 → 直接用
       affinity(nM):       越低越强 → 取负 → affinity_neg = -affinity（越高越强）

输入：
  scripts/out/phaseB/backbone_101102.csv

输出：
  scripts/out/phaseB/MHCflurry_101102.csv
  列: bb_idx, MT_MHCflurry_presentation, WT_MHCflurry_presentation,
      MT_MHCflurry_affinity_neg, WT_MHCflurry_affinity_neg

官方 API（沿用 run_mhcflurry.py 已核实，2026-06-26 自 github.com/openvax/mhcflurry master）：
  Class1PresentationPredictor.predict(peptides, alleles=[allele], verbose=0)
    返回 DataFrame: peptide, peptide_num, sample_name, affinity, best_allele,
                    processing_score, presentation_score, presentation_percentile
  allele 格式: 接受 HLA-A*02:01（标准格式，无需转换）

用法：
  python run_mhcflurry_101102.py                  # 全量重推理
  python run_mhcflurry_101102.py --smoke 2        # 烟测：2 肽 × HLA-A*02:01 验 API（主线跑）
"""

import argparse
import math
import pathlib
import sys

import pandas as pd

# ---------------------------------------------------------------------------
# 路径默认值
# ---------------------------------------------------------------------------
SCRIPT_DIR  = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_BACKBONE = PROJECT_DIR / "scripts" / "out" / "phaseB" / "backbone_101102.csv"
DEFAULT_OUT      = PROJECT_DIR / "scripts" / "out" / "phaseB" / "MHCflurry_101102.csv"

# 肽长范围（8–15mer；backbone 实际 8–14，全部通过）
MIN_PEP_LEN = 8
MAX_PEP_LEN = 15

# 烟测用已知肽（HLA-A*02:01，MHCflurry 经典验证集）
SMOKE_PEPTIDES = ["NLVPMVATV", "GILGFVFTL"]
SMOKE_ALLELE   = "HLA-A*02:01"

OUTPUT_COLS = [
    "bb_idx",
    "MT_MHCflurry_presentation", "WT_MHCflurry_presentation",
    "MT_MHCflurry_affinity_neg", "WT_MHCflurry_affinity_neg",
]


# ---------------------------------------------------------------------------
# 预测器
# ---------------------------------------------------------------------------

def load_predictor():
    try:
        from mhcflurry import Class1PresentationPredictor
    except ImportError:
        print("[mhcflurry_101102] ERROR: mhcflurry 未安装。请先 pip install mhcflurry", file=sys.stderr)
        sys.exit(1)
    print("[mhcflurry_101102] 加载 Class1PresentationPredictor...")
    predictor = Class1PresentationPredictor.load()
    print("[mhcflurry_101102] 预测器加载完成。")
    return predictor


def predict_for_allele(predictor, peptides: list, allele: str) -> pd.DataFrame:
    """对一个 allele 的所有 peptide 做预测，返回 peptide/affinity/presentation_score。"""
    result = predictor.predict(
        peptides=peptides,
        alleles=[allele],
        verbose=0,
    )
    keep_cols = [c for c in ["peptide", "affinity", "presentation_score"]
                 if c in result.columns]
    return result[keep_cols].copy()


# ---------------------------------------------------------------------------
# 烟测
# ---------------------------------------------------------------------------

def run_smoke(predictor, n: int) -> None:
    smoke_peps = SMOKE_PEPTIDES[:n] if n <= len(SMOKE_PEPTIDES) else SMOKE_PEPTIDES
    print(f"\n[smoke] 烟测 {len(smoke_peps)} 肽 × allele={SMOKE_ALLELE}")
    df = predict_for_allele(predictor, smoke_peps, SMOKE_ALLELE)
    print(df.to_string(index=False))
    print(f"\n[smoke] 列名: {list(df.columns)}")
    print("[smoke] 烟测通过：affinity(nM) + presentation_score(0-1) 均有值。")


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def build_lookup(predictor, bb: pd.DataFrame) -> dict:
    """
    按 HLA_Allele 分组，收集该组下 MT_Subpeptide ∪ WT_Subpeptide 去重肽，调 predict。
    返回 (peptide, allele) → {presentation_score, affinity}。
    肽长越界 / allele 不支持 → 该肽不打分，回贴阶段填 NaN。
    """
    try:
        supported = set(predictor.supported_alleles)
    except Exception:
        supported = None  # 取不到则不做支持性过滤，交 predict 自身报错跳过

    lookup = {}
    alleles = sorted(bb["HLA_Allele"].dropna().unique())
    n_alleles = len(alleles)

    for i, allele in enumerate(alleles, 1):
        if supported is not None and allele not in supported:
            print(f"[mhcflurry_101102] WARNING: ({i}/{n_alleles}) {allele} 不在 supported_alleles，跳过 → NaN",
                  file=sys.stderr)
            continue

        sub = bb[bb["HLA_Allele"] == allele]
        # MT ∪ WT 去重肽，过滤长度
        peps = set()
        for col in ("MT_Subpeptide", "WT_Subpeptide"):
            for p in sub[col].dropna():
                p = str(p).strip()
                if MIN_PEP_LEN <= len(p) <= MAX_PEP_LEN:
                    peps.add(p)
        peps = sorted(peps)
        if not peps:
            print(f"[mhcflurry_101102] ({i}/{n_alleles}) {allele}: 无合法肽，跳过")
            continue

        print(f"[mhcflurry_101102] ({i}/{n_alleles}) {allele}: {len(peps)} 去重肽...")
        try:
            df_pred = predict_for_allele(predictor, peps, allele)
        except Exception as exc:
            print(f"[mhcflurry_101102] WARNING: {allele} 预测失败，跳过: {exc}", file=sys.stderr)
            continue

        for _, row in df_pred.iterrows():
            key = (row["peptide"], allele)
            if key not in lookup:
                lookup[key] = {
                    "presentation_score": row.get("presentation_score", float("nan")),
                    "affinity":           row.get("affinity",           float("nan")),
                }
    return lookup


def get_score(lookup: dict, peptide: str, allele: str) -> tuple:
    """查表返回 (presentation_score, affinity_neg)。未找到 → (NaN, NaN)。"""
    NAN = float("nan")
    entry = lookup.get((peptide, allele))
    if entry is None:
        return NAN, NAN
    ps = entry["presentation_score"]
    af = entry["affinity"]
    af_neg = -af if (af is not None and not math.isnan(af)) else NAN
    return ps, af_neg


def run(backbone_path: pathlib.Path, out_path: pathlib.Path) -> None:
    print(f"[mhcflurry_101102] 读 backbone: {backbone_path}")
    bb = pd.read_csv(backbone_path, encoding="utf-8")
    print(f"[mhcflurry_101102]   shape: {bb.shape}")

    for col in ("bb_idx", "MT_Subpeptide", "WT_Subpeptide", "HLA_Allele"):
        if col not in bb.columns:
            print(f"[mhcflurry_101102] ERROR: backbone 缺列 '{col}'，实际: {list(bb.columns)}", file=sys.stderr)
            sys.exit(1)

    # HLA 订正核对（仅打印，便于自校验）
    print("[mhcflurry_101102] HLA_Allele 分布（订正核对）:")
    for (pid, hla), cnt in bb.groupby(["Patient_ID", "HLA_Allele"]).size().items():
        print(f"    P{pid}  {hla}: {cnt}")

    predictor = load_predictor()
    lookup = build_lookup(predictor, bb)
    print(f"[mhcflurry_101102] 查找表条目数: {len(lookup)}")

    mt_pres, wt_pres, mt_afneg, wt_afneg = [], [], [], []
    for _, row in bb.iterrows():
        hla = row["HLA_Allele"]
        mt_pep = str(row["MT_Subpeptide"]).strip() if pd.notna(row["MT_Subpeptide"]) else ""
        wt_pep = str(row["WT_Subpeptide"]).strip() if pd.notna(row["WT_Subpeptide"]) else ""

        m_ps, m_af = get_score(lookup, mt_pep, hla) if mt_pep else (float("nan"), float("nan"))
        w_ps, w_af = get_score(lookup, wt_pep, hla) if wt_pep else (float("nan"), float("nan"))

        mt_pres.append(m_ps)
        wt_pres.append(w_ps)
        mt_afneg.append(m_af)
        wt_afneg.append(w_af)

    out_df = pd.DataFrame({
        "bb_idx": bb["bb_idx"],
        "MT_MHCflurry_presentation": mt_pres,
        "WT_MHCflurry_presentation": wt_pres,
        "MT_MHCflurry_affinity_neg": mt_afneg,
        "WT_MHCflurry_affinity_neg": wt_afneg,
    })

    # 覆盖统计
    n_total = len(out_df)
    n_mt = out_df["MT_MHCflurry_presentation"].notna().sum()
    n_wt = out_df["WT_MHCflurry_presentation"].notna().sum()
    print(f"\n[mhcflurry_101102] == 覆盖统计 ==")
    print(f"  总行数:                          {n_total}")
    print(f"  MT_MHCflurry_presentation 非NaN: {n_mt} ({100*n_mt/n_total:.1f}%)")
    print(f"  WT_MHCflurry_presentation 非NaN: {n_wt} ({100*n_wt/n_total:.1f}%)")
    if n_mt == 0:
        print("[mhcflurry_101102] WARNING: MT 分数全为 NaN，请检查肽/allele 对应关系。", file=sys.stderr)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df[OUTPUT_COLS].to_csv(out_path, index=False, encoding="utf-8", lineterminator="\n")
    print(f"\n[mhcflurry_101102] 写出 {len(out_df)} 行 → {out_path}")
    print("\n[mhcflurry_101102] 方向归一（与 parse_output.py 一致）：")
    print("  *_presentation: 原始 presentation_score(0-1)，越高越强，直接用。")
    print("  *_affinity_neg: = -affinity(nM)，原始越低越强，取负后越高越强。")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="MHCflurry 2.0 患者 101/102 订正 HLA 重推理（prep+predict+parse 一体，按 bb_idx 输出）"
    )
    parser.add_argument("--backbone", default=str(DEFAULT_BACKBONE),
                        help="backbone_101102.csv 路径")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help="输出 MHCflurry_101102.csv 路径")
    parser.add_argument("--smoke", type=int, metavar="N", default=0,
                        help="烟测模式：只跑 N 个已知肽验证 API，不写 CSV（N=0=关闭）")
    args = parser.parse_args()

    if args.smoke > 0:
        predictor = load_predictor()
        run_smoke(predictor, args.smoke)
        return

    backbone_path = pathlib.Path(args.backbone)
    out_path      = pathlib.Path(args.out)
    if not backbone_path.exists():
        print(f"[mhcflurry_101102] ERROR: backbone 不存在: {backbone_path}", file=sys.stderr)
        sys.exit(1)

    run(backbone_path, out_path)


if __name__ == "__main__":
    main()
