"""
parse_neotimmuml_official.py — NeoTImmuML 官方数据结果回贴（QuantImmuBench Phase0）
=================================================================================
本地跑。读 run_neotimmuml_official.sh 产出的肽级分数 neotimmuml_scores_official.csv
(列: Peptide, neotimmuml_score, ...)，按【精确肽段匹配】广播回 master_backbone_official.csv
的每一行，产出：

    scripts/out_official/NeoTImmuML_official.csv   列: bb_idx, MT_NeoTImmuML, WT_NeoTImmuML

★ NeoTImmuML 是 HLA-agnostic（模型输入=纯肽 78 物化特征，无 HLA 维度），所以回贴是
  纯「肽→分」映射，无等位维度 —— 比 PRIME/ImmuneApp 的 (肽,等位) 复合 key 简单：
    - MT_NeoTImmuML = score_map[MT_Subpeptide]
    - WT_NeoTImmuML = score_map[WT_Subpeptide]
  精确肽匹配缺失 → NaN（诚实部分覆盖，绝不肽级以外兜底造数）。

★ 数据保真红线：分数本身的可信度受「训练集类不平衡 1:364 / 无官方权重 / aaComp_1·
  cruciani_1 不可复刻 demo」三重限制，见 run_neotimmuml_official.sh 头注与 calc_78_features.R。
  本脚本只负责「把已算出的分诚实回贴」，不评判分数质量。

运行示例：
    python scripts/hpc_official/parse_neotimmuml_official.py \
        --scores   scripts/out_official/neotimmuml_scores_official.csv \
        --backbone scripts/out_official/master_backbone_official.csv \
        --out-dir  scripts/out_official
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

VALID_AAS = set("ACDEFGHIKLMNPQRSTVWY")


def _norm_pep(p):
    """与 extract_peptides.py / calc_78_features.R 一致的肽段规范化：strip + upper。
    非字符串 / 空 / 含非标准 AA / 长度越界 → None（这些肽不会有官方分）。"""
    if not isinstance(p, str):
        return None
    p = p.strip().upper()
    if not p:
        return None
    if not (8 <= len(p) <= 13):
        return None
    if not all(c in VALID_AAS for c in p):
        return None
    return p


def parse_args():
    here = Path(__file__).resolve().parent
    default_official = here.parent / "out_official"
    ap = argparse.ArgumentParser(
        description="NeoTImmuML 官方肽级分数回贴 → NeoTImmuML_official.csv")
    ap.add_argument("--scores",
                    default=str(default_official / "neotimmuml_scores_official.csv"),
                    help="肽级分数 csv（列 Peptide, neotimmuml_score）")
    ap.add_argument("--backbone",
                    default=str(default_official / "master_backbone_official.csv"),
                    help="master_backbone_official.csv（含 bb_idx, MT_Subpeptide, WT_Subpeptide）")
    ap.add_argument("--out-dir", default=str(default_official), help="输出目录")
    ap.add_argument("--score-col", default="neotimmuml_score",
                    help="分数列名（默认 neotimmuml_score）")
    return ap.parse_args()


def main():
    args = parse_args()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    backbone = pd.read_csv(Path(args.backbone).resolve(), encoding="utf-8")
    if "bb_idx" not in backbone.columns:
        sys.exit(f"[ERR] backbone 缺 bb_idx 列：{args.backbone}")
    n_bb = len(backbone)
    print(f"[backbone] 读入 {n_bb} 行 ← {args.backbone}", file=sys.stderr)

    # ---- 肽级分数 → 严格肽 key 映射 ----
    score_map = {}
    scores_path = Path(args.scores).resolve()
    if scores_path.exists():
        sdf = pd.read_csv(scores_path)
        if "Peptide" not in sdf.columns or args.score_col not in sdf.columns:
            sys.exit(f"[ERR] scores csv 需含 'Peptide' 和 '{args.score_col}' 列，"
                     f"实有 {list(sdf.columns)}")
        for _, r in sdf.iterrows():
            pep = _norm_pep(r["Peptide"])
            val = r[args.score_col]
            if pep is None or pd.isna(val):
                continue
            score_map[pep] = float(val)   # 同肽重复以最后一次为准（理应唯一）
        print(f"[scores] {len(score_map)} 个 distinct 肽有分 ← {scores_path}", file=sys.stderr)
    else:
        print(f"[WARN] scores 文件不存在：{scores_path} —— MT/WT_NeoTImmuML 全 NaN",
              file=sys.stderr)

    # ---- 精确肽匹配广播（缺 → NaN）----
    def map_col(src_col):
        if src_col not in backbone.columns:
            print(f"[WARN] backbone 无列 {src_col}，该列结果全 NaN", file=sys.stderr)
            return np.full(n_bb, np.nan)
        out = np.full(n_bb, np.nan)
        for i, raw in enumerate(backbone[src_col].values):
            pep = _norm_pep(raw)
            if pep is not None and pep in score_map:
                out[i] = score_map[pep]
        return out

    mt_vals = map_col("MT_Subpeptide")
    wt_vals = map_col("WT_Subpeptide")

    result = pd.DataFrame({
        "bb_idx": backbone["bb_idx"].values,
        "MT_NeoTImmuML": mt_vals,
        "WT_NeoTImmuML": wt_vals,
    })

    out_path = out_dir / "NeoTImmuML_official.csv"
    result.to_csv(out_path, index=False, encoding="utf-8")

    n_mt = int(np.sum(~np.isnan(mt_vals)))
    n_wt = int(np.sum(~np.isnan(wt_vals)))
    # 覆盖核对：MT_Subpeptide 中有效肽且其肽在 score_map 内的行 = 期望非空
    mt_expect = sum(
        1 for raw in backbone.get("MT_Subpeptide", pd.Series([], dtype=str)).values
        if (_norm_pep(raw) is not None and _norm_pep(raw) in score_map))
    print(f"[OUT] {out_path}（{len(result)} 行）"
          f" MT_NeoTImmuML 非空={n_mt} (期望={mt_expect})"
          f" WT_NeoTImmuML 非空={n_wt}", file=sys.stderr)
    if n_mt != mt_expect:
        print(f"[CHECK][WARN] MT 非空 {n_mt} ≠ 期望 {mt_expect}，回贴可能有缺", file=sys.stderr)
    else:
        print(f"[CHECK][OK] MT 精确肽匹配全覆盖 ✅", file=sys.stderr)
    print("[DONE] parse_neotimmuml_official.py 完成", file=sys.stderr)


if __name__ == "__main__":
    main()
