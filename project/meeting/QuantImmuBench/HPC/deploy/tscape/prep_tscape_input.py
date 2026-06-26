"""
prep_tscape_input.py  —  QuantImmuBench §Tier-3  T-SCAPE 输入准备
服务项目：quantimmu-bench §工具扩张v2 lever=部署T-SCAPE apples-to-apples

功能：
  1. 读 master_backbone.csv
  2. 取 unique (MT_Subpeptide, HLA_Allele) 对（≤20mer 过滤，超长跳过并计数）
  3. HLA 格式保持标准格式 HLA-A*02:01（T-SCAPE 直接接受，无需转换）
  4. 输出 tscape_input.csv（列：Allele,Peptide）—— T-SCAPE 所需表头
  5. 输出 tscape_input_map.csv（列：Peptide,Allele,bb_idx_list）—— 回贴用

T-SCAPE 范围说明（MT-only）：
  - 只喂 MT_Subpeptide + HLA_Allele，不需要 WT（T-SCAPE 是 MT-only 工具）
  - 对所有长度 ≤20mer 全覆盖（T-SCAPE MHC-I 推理，最优 9mer，最大 20mer）
  - 去重 unique (MT, HLA) 对喂工具，merge 时通过 map 回贴所有 bb_idx 行

用法：
  python prep_tscape_input.py [--backbone <csv>] [--out-dir <dir>] [--smoke N]
  默认 backbone: scripts/out/master_backbone.csv（相对脚本向上 3 级）
  默认 out-dir:  scripts/out/newtools/
  --smoke N：取前 N 个 unique (MT, HLA) 对（烟测用，建议 N=5）

输出文件：
  <out_dir>/tscape_input.csv      — 喂 T-SCAPE 的输入（列：Allele,Peptide）
  <out_dir>/tscape_input_map.csv  — (Peptide,Allele) → bb_idx 列表（逗号分隔）
"""

import argparse
import csv
import pathlib
import sys
from collections import defaultdict


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

MAX_PEPTIDE_LEN = 20   # T-SCAPE 支持 ≤20mer（超长跳过）
MIN_PEPTIDE_LEN = 1    # 防御性下界（理论上 master_backbone 不会有 0mer）


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def prep(backbone_path: str, out_dir: str, smoke: int = 0) -> None:
    backbone_path = pathlib.Path(backbone_path)
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tscape_input_path = out_dir / "tscape_input.csv"
    tscape_map_path   = out_dir / "tscape_input_map.csv"

    # (Peptide, Allele) → [bb_idx, ...] — 去重同时保留全部 bb_idx
    pair_to_bbidx: dict[tuple[str, str], list[str]] = defaultdict(list)

    skipped_long  = 0   # 超过 20mer 跳过
    skipped_empty = 0   # MT_Subpeptide 为空跳过
    total_rows    = 0

    with open(backbone_path, newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        for row in reader:
            total_rows += 1
            mt_pep  = row["MT_Subpeptide"].strip()
            hla_raw = row["HLA_Allele"].strip()
            bb_idx  = row["bb_idx"].strip()

            # MT 为空：跳过
            if not mt_pep:
                skipped_empty += 1
                print(
                    f"[prep_tscape] SKIP bb_idx={bb_idx}: MT_Subpeptide 为空",
                    file=sys.stderr,
                )
                continue

            # 肽长过滤
            pep_len = len(mt_pep)
            if pep_len > MAX_PEPTIDE_LEN:
                skipped_long += 1
                print(
                    f"[prep_tscape] SKIP bb_idx={bb_idx}: MT_Subpeptide={mt_pep!r} "
                    f"长度={pep_len} > {MAX_PEPTIDE_LEN}mer",
                    file=sys.stderr,
                )
                continue

            # HLA 格式：标准 HLA-A*02:01 直接用（T-SCAPE 原生支持 WHO 格式）
            pair = (mt_pep, hla_raw)
            pair_to_bbidx[pair].append(bb_idx)

    # unique 对列表，按首次出现顺序（保持确定性）
    unique_pairs = list(pair_to_bbidx.keys())

    # --smoke：截取前 N 对
    if smoke > 0:
        print(f"[prep_tscape] --smoke {smoke}：截取前 {smoke} 个 unique (MT, HLA) 对", file=sys.stderr)
        unique_pairs = unique_pairs[:smoke]

    # 写 T-SCAPE 输入（列：Allele,Peptide）
    with open(tscape_input_path, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(["Allele", "peptide"])   # T-SCAPE 官方 pmhc_im 输入列名（peptide 小写，核 example/inputs/pmhc_im.csv）
        for (pep, allele) in unique_pairs:
            writer.writerow([allele, pep])

    # 写 map CSV（(Peptide,Allele) → bb_idx 列表，逗号分隔）
    with open(tscape_map_path, "w", newline="", encoding="utf-8") as f_map:
        writer_map = csv.writer(f_map)
        writer_map.writerow(["Peptide", "Allele", "bb_idx_list"])
        for (pep, allele) in unique_pairs:
            bb_idx_list = ",".join(pair_to_bbidx[(pep, allele)])
            writer_map.writerow([pep, allele, bb_idx_list])

    n_unique = len(unique_pairs)
    n_total_bb = sum(len(v) for v in pair_to_bbidx.values())

    print(f"[prep_tscape] backbone 总行数       : {total_rows}")
    print(f"[prep_tscape] 跳过（MT_Subpeptide 空）: {skipped_empty}")
    print(f"[prep_tscape] 跳过（>{MAX_PEPTIDE_LEN}mer）   : {skipped_long}")
    print(f"[prep_tscape] unique (MT, HLA) 对    : {n_unique}")
    print(f"[prep_tscape] 覆盖 bb_idx 数          : {n_total_bb}")
    if smoke > 0:
        print(f"[prep_tscape] [SMOKE] 仅写前 {n_unique} 对，全量需去掉 --smoke")
    print(f"[prep_tscape] 输出 tscape_input.csv  : {tscape_input_path}")
    print(f"[prep_tscape] 输出 tscape_input_map  : {tscape_map_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    # 默认路径：本脚本在 HPC/deploy/tscape/，master_backbone 在 scripts/out/
    script_dir   = pathlib.Path(__file__).parent
    repo_root    = script_dir.parents[3]   # YJ-Agent/project/meeting/QuantImmuBench/
    default_bb   = repo_root / "scripts" / "out" / "master_backbone.csv"
    default_out  = repo_root / "scripts" / "out" / "newtools"

    parser = argparse.ArgumentParser(
        description="Prepare T-SCAPE input CSV from master_backbone.csv (MT-only, ≤20mer)"
    )
    parser.add_argument(
        "--backbone",
        default=str(default_bb),
        help="master_backbone.csv 路径（默认 scripts/out/master_backbone.csv）",
    )
    parser.add_argument(
        "--out-dir",
        default=str(default_out),
        help="输出目录（默认 scripts/out/newtools/）",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        default=0,
        metavar="N",
        help="烟测模式：只写前 N 个 unique (MT, HLA) 对（建议 N=5，0=关闭）",
    )
    args = parser.parse_args()

    bb_path = pathlib.Path(args.backbone)
    if not bb_path.exists():
        print(f"[prep_tscape] ERROR: backbone 不存在: {bb_path}", file=sys.stderr)
        sys.exit(1)

    prep(args.backbone, args.out_dir, smoke=args.smoke)


if __name__ == "__main__":
    main()
