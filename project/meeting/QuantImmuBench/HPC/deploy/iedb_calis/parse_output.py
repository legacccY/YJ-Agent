"""
parse_output.py  --  QuantImmuBench §Tier-0 first wave  IEDB Calis 2013 输出解析
服务项目：quantimmu-bench benchmark 扩张 v2 第一波  lever=部署IEDB_Calis

功能：
  1. 读 allele_manifest.csv（prep_input.py 生成）→ 所有 allele_tag 及对应 scores_filename
  2. 从 --scores-dir 读每个 <file_tag>_scores.txt（predict_immunogenicity.py stdout）
     - 跳过元数据行（allele: / masking: / masked variables:）
     - 找到 "peptide,length,score" 表头后开始读 CSV data
  3. 构建 score_dict：(peptide.upper(), allele_tag) → immunogenicity_score
  4. 读 universe.csv（34247 行，4-key + MT/WT/HLA/...）
  5. 对每行回贴 MT_IEDB_Calis 和 WT_IEDB_Calis
     - join key：(MT_Subpeptide.upper(), hla_to_iedb(HLA_Allele))
     - 无对应分数填 NaN（unsupported 肽长 / 工具失败的行）
  6. 输出 scripts/out/newtools/IEDB_Calis_DS1DS2_scores.csv
     列：Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide, MT_IEDB_Calis, WT_IEDB_Calis

输出方向：
  score 越高越免疫原（与 predict_immunogenicity.py 原始方向相同，无需翻转）

注意事项（详见 NOTES.md）：
  - 不支持的 HLA allele 使用默认 anchor mask（P1, P2, C-term），score 为肽序列本征值
  - 同一肽在支持/不支持 allele 下的 score 可能有细微差异（mask 位置不同）
  - 工具从 predict_immunogenicity.py 提取时验证过（不含 WT，纯肽打分）
  - 不支持肽长 < 2 的序列（实际 8-15mer 全部可跑）

用法：
    python parse_output.py [--manifest PATH] [--scores-dir DIR] [--universe PATH] [--out-csv PATH]
"""

import argparse
import csv
import math
import pathlib
import sys


# ---------------------------------------------------------------------------
# HLA 格式转换（与 prep_input.py 一致）
# ---------------------------------------------------------------------------

def hla_to_iedb(h: str) -> str:
    """HLA-A*02:01 → HLA-A0201（去 * 去 :）"""
    return h.replace("*", "").replace(":", "")


def allele_tag_to_file_tag(allele_tag: str) -> str:
    """HLA-A0201 → A0201  /  H-2-Db → H_2_Db（与 prep_input.py 一致）"""
    return allele_tag.replace("HLA-", "").replace("-", "_")


# ---------------------------------------------------------------------------
# 读 scores 文件（predict_immunogenicity.py 的 stdout 输出）
# ---------------------------------------------------------------------------

def parse_score_file(score_path: pathlib.Path) -> dict[str, float]:
    """
    解析单个 allele 的 scores 文件。
    返回 {peptide_upper: score} dict。

    predict_immunogenicity.py 输出格式（stdout）：
      [可选] allele: HLA-A0201
      masking: custom
      masked variables: [1, 2, 9]
                                      ← 空行
      peptide,length,score            ← 表头（以此行为数据开始标记）
      FIAGLIAIV,9,0.45678
      LITGRLQSL,9,0.23456
      ...
    输出按 score 降序排列（join 时按 peptide 索引，不依赖行序）。
    """
    results: dict[str, float] = {}
    in_data = False

    with open(score_path, "r", encoding="utf-8") as f:
        for line in f:
            line_stripped = line.strip()

            if not in_data:
                # 等到表头行
                if line_stripped == "peptide,length,score":
                    in_data = True
                continue

            # data 区域
            if not line_stripped:
                continue

            parts = line_stripped.split(",")
            if len(parts) < 3:
                continue  # 格式异常行跳过

            pep = parts[0].strip().upper()
            try:
                score = float(parts[2].strip())
            except ValueError:
                continue  # score 列不可转 float，跳过

            results[pep] = score

    return results


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def run(
    manifest_path: pathlib.Path,
    scores_dir: pathlib.Path,
    universe_path: pathlib.Path,
    out_csv: pathlib.Path,
) -> None:

    # ---- Step 1: 读 allele_manifest.csv ----
    if not manifest_path.exists():
        print(f"ERROR: allele_manifest.csv not found: {manifest_path}", file=sys.stderr)
        sys.exit(1)

    manifest: list[dict] = []
    with open(manifest_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            manifest.append(row)
    print(f"[parse] manifest: {len(manifest)} alleles loaded from {manifest_path}")

    # ---- Step 2: 读每个 allele 的 scores 文件 ----
    # score_dict[(peptide_upper, allele_tag)] = immunogenicity_score
    score_dict: dict[tuple[str, str], float] = {}

    missing_scores = 0
    for row in manifest:
        allele_tag = row["allele_tag"]
        scores_filename = row["scores_filename"]
        scores_file = scores_dir / scores_filename

        if not scores_file.exists():
            print(f"[warn] scores file not found (skip): {scores_file}", file=sys.stderr)
            missing_scores += 1
            continue

        file_scores = parse_score_file(scores_file)
        if not file_scores:
            print(f"[warn] scores file is empty or unparseable: {scores_file}", file=sys.stderr)
            missing_scores += 1
            continue

        for pep, score in file_scores.items():
            score_dict[(pep, allele_tag)] = score

        print(f"[parse]   {allele_tag:<18} → {len(file_scores)} scores loaded")

    total_scores = len(score_dict)
    print(f"[parse] total (peptide, allele_tag) scores: {total_scores}")
    if missing_scores > 0:
        print(f"[parse] ⚠️  {missing_scores} allele(s) missing scores → those rows → NaN")

    # ---- Step 3: 读 universe.csv，回贴 scores ----
    if not universe_path.exists():
        print(f"ERROR: universe.csv not found: {universe_path}", file=sys.stderr)
        sys.exit(1)

    out_csv.parent.mkdir(parents=True, exist_ok=True)

    OUTFIELDS = [
        "Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide",
        "MT_IEDB_Calis", "WT_IEDB_Calis",
    ]

    n_total = 0
    n_mt_found = 0
    n_wt_found = 0
    n_mt_nan = 0
    n_wt_nan = 0

    with (
        open(universe_path, newline="", encoding="utf-8") as f_in,
        open(out_csv, "w", newline="", encoding="utf-8") as f_out,
    ):
        reader = csv.DictReader(f_in)
        writer = csv.DictWriter(f_out, fieldnames=OUTFIELDS)
        writer.writeheader()

        for row in reader:
            n_total += 1
            hla_raw = row["HLA_Allele"].strip()
            allele_tag = hla_to_iedb(hla_raw)

            mt_pep = row["MT_Subpeptide"].strip().upper()
            wt_pep = row.get("WT_Subpeptide", "").strip().upper()

            # MT score
            mt_key = (mt_pep, allele_tag)
            if mt_key in score_dict:
                mt_score: float | str = round(score_dict[mt_key], 6)
                n_mt_found += 1
            else:
                mt_score = float("nan")
                n_mt_nan += 1

            # WT score
            if wt_pep:
                wt_key = (wt_pep, allele_tag)
                if wt_key in score_dict:
                    wt_score: float | str = round(score_dict[wt_key], 6)
                    n_wt_found += 1
                else:
                    wt_score = float("nan")
                    n_wt_nan += 1
            else:
                wt_score = float("nan")
                n_wt_nan += 1

            # NaN → 空字符串写入 CSV（pandas 读取时识别为 NaN）
            def fmt(v: float | str) -> str:
                if isinstance(v, float) and math.isnan(v):
                    return ""
                return str(v)

            writer.writerow({
                "Dataset": row["Dataset"],
                "Peptide_ID": row["Peptide_ID"],
                "HLA_Allele": row["HLA_Allele"],
                "MT_Subpeptide": row["MT_Subpeptide"],
                "MT_IEDB_Calis": fmt(mt_score),
                "WT_IEDB_Calis": fmt(wt_score),
            })

    print(f"\n[parse] universe.csv: {n_total} rows processed")
    print(f"[parse]   MT_IEDB_Calis: {n_mt_found} found ({n_mt_nan} NaN)")
    print(f"[parse]   WT_IEDB_Calis: {n_wt_found} found ({n_wt_nan} NaN)")
    print(f"[parse] ✓ 输出: {out_csv}")
    print(f"[parse]   列：Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide, MT_IEDB_Calis, WT_IEDB_Calis")
    print(f"[parse]   方向：score 越高越免疫原（原始，无翻转）")

    if n_mt_nan > 0:
        nan_pct = 100 * n_mt_nan / n_total
        if nan_pct > 10:
            print(
                f"[parse] ⚠️  MT NaN 率 {nan_pct:.1f}% 较高，检查 run_iedb_calis.sh 是否有 allele 失败",
                file=sys.stderr,
            )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    script_dir = pathlib.Path(__file__).parent
    repo_root = script_dir.parents[3]  # QuantImmuBench/
    newtools_dir = repo_root / "scripts" / "out" / "newtools"

    default_manifest = newtools_dir / "iedb_calis_inputs" / "allele_manifest.csv"
    default_scores_dir = newtools_dir / "iedb_calis_scores"  # 从 HPC 取回后放这里
    default_universe = newtools_dir / "universe.csv"
    default_out_csv = newtools_dir / "IEDB_Calis_DS1DS2_scores.csv"

    parser = argparse.ArgumentParser(
        description="解析 IEDB Calis 2013 打分结果，回贴 universe.csv"
    )
    parser.add_argument(
        "--manifest",
        default=str(default_manifest),
        help="allele_manifest.csv 路径（prep_input.py 生成）",
    )
    parser.add_argument(
        "--scores-dir",
        default=str(default_scores_dir),
        help="HPC scores 目录（run_iedb_calis.sh 的 ${SCORES_DIR} 取回后的本地路径）",
    )
    parser.add_argument(
        "--universe",
        default=str(default_universe),
        help="universe.csv 路径（默认 scripts/out/newtools/universe.csv）",
    )
    parser.add_argument(
        "--out-csv",
        default=str(default_out_csv),
        help="输出 CSV 路径（默认 scripts/out/newtools/IEDB_Calis_DS1DS2_scores.csv）",
    )
    args = parser.parse_args()

    manifest_path = pathlib.Path(args.manifest)
    scores_dir = pathlib.Path(args.scores_dir)
    universe_path = pathlib.Path(args.universe)
    out_csv = pathlib.Path(args.out_csv)

    if not scores_dir.exists():
        print(
            f"ERROR: scores-dir 不存在: {scores_dir}\n"
            "  1. 先在 HPC 跑 run_iedb_calis.sh，取回 scores/ 目录\n"
            f"  2. 将取回的 scores/ 目录放在 {scores_dir}\n"
            "  3. 再跑 parse_output.py",
            file=sys.stderr,
        )
        sys.exit(1)

    run(
        manifest_path=manifest_path,
        scores_dir=scores_dir,
        universe_path=universe_path,
        out_csv=out_csv,
    )


if __name__ == "__main__":
    main()
