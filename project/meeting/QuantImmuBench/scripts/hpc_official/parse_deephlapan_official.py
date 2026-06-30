"""
parse_deephlapan_official.py — deepHLApan 官方数据结果回贴
=========================================================
本地跑（deepHLApan 输出拿到后）。解析 deephlapan_out_MT/ + deephlapan_out_WT/
的 *_predicted_result.csv（官方 batch 输出），经 deephlapan_input_map_MT/WT.csv
回贴 bb_idx，产出一张 CSV：

    scripts/out_official/deepHLApan_official.csv
      列：bb_idx, MT_deepHLApan_bind, MT_deepHLApan_immuno,
              WT_deepHLApan_bind, WT_deepHLApan_immuno

★ 数据完整性纪律（与 parse_prime_immuneapp_official.py 同源）★
deepHLApan 是 context-free：每行输出自带 HLA 列，分数只取决于 (peptide, HLA) 对。
故严格以 (peptide, HLA_no_star) 复合 key 建 score_map，回贴时只做精确匹配：
  - 缺该 (pep, HLA) 实际分 → 该 bb_idx 保持 NaN（诚实部分覆盖），
    **绝不肽级兜底回填别等位的分**；
  - bind 与 immuno 两列分别回贴，缺一即该列 NaN。

格式事实（已核 scripts/out_official/）：
  - 输入/map/输出 HLA 全为无星号格式：HLA-A66:01（map key `pep|HLA-A66:01`、
    输出 HLA 列 `HLA-A66:01` 直接同格式匹配，无需转换）；
  - 官方输出列名（已核 prior 本地 WSL2 docker 跑出样例）：
        Annotation,HLA,Peptide,binding score,immunogenic score
    （另有 *_predicted_result_rank.csv，多一列 rank，本脚本只读 *_predicted_result.csv）；
  - master_backbone_official.csv 的 HLA_Allele 为星号格式 HLA-A*66:01，
    但回贴走 map（map key 已是无星号），不直接碰 backbone 的 HLA 列。

输出目录结构（run 脚本产出，拉回本地）：
  deephlapan_out_MT/deephlapan_input_MT_predicted_result.csv
  deephlapan_out_WT/deephlapan_input_WT_predicted_result.csv

运行示例：
    python scripts/hpc_official/parse_deephlapan_official.py \
        --out-root  scripts/out_official \
        --map-dir   scripts/out_official \
        --backbone  scripts/out_official/master_backbone_official.csv \
        --out-dir   scripts/out_official
"""

import argparse
import ast
import csv
import sys
from pathlib import Path

import pandas as pd

# 官方输出列名变体（容错；已核标准为 "binding score" / "immunogenic score"）
BIND_CANDIDATES = ("binding score", "binding_score", "binding")
IMMUNO_CANDIDATES = ("immunogenic score", "immunogenic_score", "immunogenicity")


# ---------------------------------------------------------------------------
# HLA 归一：去星号、保 HLA- 前缀（deepHLApan 输入/输出/ map key 同格式）
# ---------------------------------------------------------------------------

def hla_no_star(hla: str) -> str:
    """HLA-A*66:01 → HLA-A66:01；已是无星号则原样。"""
    return str(hla).replace("*", "").strip()


# ---------------------------------------------------------------------------
# 解析单侧 *_predicted_result.csv → {(peptide, hla_no_star): (bind, immuno)}
# ---------------------------------------------------------------------------

def load_side_scores(side_dir: Path):
    """读 side_dir 下所有 *_predicted_result.csv（排除 *_rank.csv），
    返回 {(peptide, hla_no_star): (bind_float|None, immuno_float|None)}。无文件返回 {}。"""
    if not side_dir.exists():
        print(f"[WARN] 输出目录不存在：{side_dir}（该侧全 NaN）", file=sys.stderr)
        return {}
    files = sorted(
        f for f in side_dir.glob("*_predicted_result.csv")
        if "_rank" not in f.name
    )
    if not files:
        print(f"[WARN] {side_dir} 下无 *_predicted_result.csv 产出", file=sys.stderr)
        return {}

    lut = {}
    n_rows = 0
    for f in files:
        with f.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            cols = {c.lower().strip(): c for c in (reader.fieldnames or [])}
            pep_col = cols.get("peptide")
            hla_col = cols.get("hla")
            bind_col = next((cols[c] for c in BIND_CANDIDATES if c in cols), None)
            imm_col = next((cols[c] for c in IMMUNO_CANDIDATES if c in cols), None)
            if not (pep_col and hla_col and (bind_col or imm_col)):
                print(f"[WARN] {f.name} 缺必需列(peptide/HLA/bind/immuno)，跳过；"
                      f"实际列={reader.fieldnames}", file=sys.stderr)
                continue
            for row in reader:
                pep = str(row[pep_col]).strip()
                hla_ns = hla_no_star(row[hla_col])

                def _num(col):
                    if not col:
                        return None
                    v = str(row[col]).strip()
                    if v == "" or v.lower() == "nan":
                        return None
                    try:
                        return float(v)
                    except ValueError:
                        return None

                bind = _num(bind_col)
                imm = _num(imm_col)
                # 同键重复（context-free 应同分）保留首个
                lut.setdefault((pep, hla_ns), (bind, imm))
                n_rows += 1
    print(f"[parse] {side_dir.name}: 读 {len(files)} 文件 {n_rows} 行 → "
          f"{len(lut)} 个 distinct (pep,HLA)", file=sys.stderr)
    return lut


# ---------------------------------------------------------------------------
# 严格回贴：map key `pep|HLA-no-star` → backbone_indices；只精确匹配，缺即 NaN
# ---------------------------------------------------------------------------

def merge_side(result: pd.DataFrame, lut: dict, map_path: Path,
               bind_col: str, immuno_col: str):
    """把 lut 的 (bind, immuno) 按 map 回贴到 result 的 bind_col/immuno_col 两列。
    返回该侧实际命中的 distinct (pep,HLA) 数。"""
    if not map_path.exists():
        print(f"[WARN] map 不存在：{map_path}（{bind_col}/{immuno_col} 全 NaN）",
              file=sys.stderr)
        return 0
    if not lut:
        return 0
    map_df = pd.read_csv(map_path, encoding="utf-8")
    hit_keys = set()
    for _, map_row in map_df.iterrows():
        raw_key = str(map_row["key"])
        if raw_key.startswith("SKIPPED_LEN:"):
            continue
        parts = raw_key.split("|", 1)
        if len(parts) < 2:
            continue
        pep, hla_ns = parts[0].strip(), hla_no_star(parts[1])
        if (pep, hla_ns) not in lut:
            continue  # 缺该实际分 → 保持 NaN，不肽级兜底
        bind, imm = lut[(pep, hla_ns)]
        try:
            bb_indices = ast.literal_eval(str(map_row["backbone_indices"]))
        except (ValueError, SyntaxError):
            continue
        hit_keys.add((pep, hla_ns))
        for idx in bb_indices:
            if idx in result.index:
                if bind is not None:
                    result.at[idx, bind_col] = bind
                if imm is not None:
                    result.at[idx, immuno_col] = imm
    return len(hit_keys)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def parse_args():
    here = Path(__file__).resolve().parent
    default_official = here.parent / "out_official"
    p = argparse.ArgumentParser(
        description="deepHLApan 官方结果回贴 → deepHLApan_official.csv")
    p.add_argument("--out-root", default=str(default_official),
                   help="含 deephlapan_out_MT/ 与 deephlapan_out_WT/ 的根目录")
    p.add_argument("--mt-dir", default=None,
                   help="MT 输出目录（默认 <out-root>/deephlapan_out_MT）")
    p.add_argument("--wt-dir", default=None,
                   help="WT 输出目录（默认 <out-root>/deephlapan_out_WT）")
    p.add_argument("--map-dir", default=str(default_official),
                   help="存放 deephlapan_input_map_MT/WT.csv 的目录")
    p.add_argument("--backbone", default=str(default_official / "master_backbone_official.csv"),
                   help="master_backbone_official.csv（index_col=bb_idx）")
    p.add_argument("--out-dir", default=str(default_official), help="输出目录")
    return p.parse_args()


def main():
    args = parse_args()
    out_root = Path(args.out_root).resolve()
    mt_dir = Path(args.mt_dir).resolve() if args.mt_dir else out_root / "deephlapan_out_MT"
    wt_dir = Path(args.wt_dir).resolve() if args.wt_dir else out_root / "deephlapan_out_WT"
    map_dir = Path(args.map_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    backbone = pd.read_csv(Path(args.backbone).resolve(),
                           index_col="bb_idx", encoding="utf-8")
    print(f"[backbone] 读入 {len(backbone)} 行 ← {args.backbone}", file=sys.stderr)

    result = backbone.copy()
    for col in ("MT_deepHLApan_bind", "MT_deepHLApan_immuno",
                "WT_deepHLApan_bind", "WT_deepHLApan_immuno"):
        result[col] = float("nan")

    mt_lut = load_side_scores(mt_dir)
    wt_lut = load_side_scores(wt_dir)

    n_mt = merge_side(result, mt_lut, map_dir / "deephlapan_input_map_MT.csv",
                      "MT_deepHLApan_bind", "MT_deepHLApan_immuno")
    n_wt = merge_side(result, wt_lut, map_dir / "deephlapan_input_map_WT.csv",
                      "WT_deepHLApan_bind", "WT_deepHLApan_immuno")

    out_cols = ["MT_deepHLApan_bind", "MT_deepHLApan_immuno",
                "WT_deepHLApan_bind", "WT_deepHLApan_immuno"]
    out_df = (result[out_cols].reset_index().rename(columns={"index": "bb_idx"}))
    if "bb_idx" not in out_df.columns:
        out_df = out_df.rename(columns={out_df.columns[0]: "bb_idx"})
    out_path = out_dir / "deepHLApan_official.csv"
    out_df.to_csv(out_path, index=False, encoding="utf-8")

    print(f"[OUT] {out_path}（{len(out_df)} 行，列 {list(out_df.columns)}）", file=sys.stderr)
    print(f"[COVER] MT: 命中 {n_mt} 个 (pep,HLA)；"
          f"MT_bind 非空={result['MT_deepHLApan_bind'].notna().sum()} "
          f"MT_immuno 非空={result['MT_deepHLApan_immuno'].notna().sum()}", file=sys.stderr)
    print(f"[COVER] WT: 命中 {n_wt} 个 (pep,HLA)；"
          f"WT_bind 非空={result['WT_deepHLApan_bind'].notna().sum()} "
          f"WT_immuno 非空={result['WT_deepHLApan_immuno'].notna().sum()}", file=sys.stderr)
    print("[DONE] parse_deephlapan_official.py 完成", file=sys.stderr)


if __name__ == "__main__":
    main()
