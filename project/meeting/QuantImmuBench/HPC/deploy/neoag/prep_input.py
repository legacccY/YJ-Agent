"""
prep_input.py — QuantImmuBench §工具部署  neoag 输入准备（第 30 工具，替搁置 NeoaPred）
服务项目：quantimmu-bench §工具部署 lever=补满 30 工具最后 1 个免疫原槽（neoag）

功能：
  1. 读 universe.csv（34247 行；列 Dataset/Peptide_ID/HLA_Allele/MT_Subpeptide/WT_Subpeptide/...）
  2. 取 unique (MT_Subpeptide, WT_Subpeptide) 对（neoag = 肽-对级打分，不吃 HLA → 同对各 HLA 行广播同值）
  3. 过滤 8-11mer（neoag Class-I 范围；MT/WT 同长才能算单残基替换）
  4. 算突变位号：MT vs WT 逐位比对取差异残基 index
     —— **只取恰好 1 个残基差异的对**；0 差异(同肽)/>1 差异/MT≠WT 长度 → 记入 skipped（parse 填 NaN）
  5. 写 neoag 输入 CSV（本部署 canonical 格式，run_neoag.R 消费）+ pair_map + skipped
  6. --smoke N：只保留前 N 个有效对（烟测）

⚠️⚠️ TODO（官方未核，本机无外网 curl HTTP 000，需主窗 clone github.com/vincentlaboratories/neoag 核实）：
  - neoag **官方 input CSV 确切列名**未核 → 本脚本输出本部署 canonical 列名
    (pair_id, mt_peptide, wt_peptide, mut_pos_1based, pep_len)；
    由 run_neoag.R 内部适配映射到官方 feature 函数所需列名（适配点见 run_neoag.R 的
    OFFICIAL API ADAPTER 块）。主窗 clone 后若官方直接吃某 CSV，把列名/格式在此对齐。
  - **突变位号 base 未核**：本脚本默认输出 **1-based 肽内位置**（差异残基在肽中第几位，从 1 数）。
    官方若要 0-based 肽内位 → 改 POS_BASE=0；若要蛋白位置 → 本数据无蛋白坐标，无法提供（标 TODO）。
    POS_BASE 是本文件顶部单一常量，主窗核实后改一处即可。

输入：
  scripts/out/newtools/universe.csv  (含 MT_Subpeptide, WT_Subpeptide 列)

输出（均在本脚本目录 neoag/ 下）：
  neoag_input.csv        ← run_neoag.R 输入（pair_id, mt_peptide, wt_peptide, mut_pos_1based, pep_len）
  neoag_pair_map.csv     ← 同上（含 skip 与否标记，溯源用）
  neoag_skipped.csv      ← 被跳过的对 + 原因（parse 阶段对应行填 NaN）

用法（主窗跑，本脚本不自跑）：
  python prep_input.py [--universe PATH] [--out-dir DIR] [--smoke N]
"""

import argparse
import csv
import pathlib
import sys

# ---------------------------------------------------------------------------
# 路径默认值（相对脚本位置，适配 HPC/deploy/neoag/ 位置）
# ---------------------------------------------------------------------------
SCRIPT_DIR  = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_UNIVERSE = PROJECT_DIR / "scripts" / "out" / "newtools" / "universe.csv"
DEFAULT_OUT_DIR  = SCRIPT_DIR

# neoag / Class-I 肽长（8-11mer）
MIN_PEP_LEN = 8
MAX_PEP_LEN = 11

# ⚠️ TODO 突变位号 base（官方未核）：1 = 肽内 1-based（默认）；0 = 肽内 0-based。
#    主窗 clone neoag 后核实官方 mut_position 约定，改这一处常量即可。
POS_BASE = 1

# 本部署 canonical 输入列（run_neoag.R 消费；与官方列名的映射在 run_neoag.R 适配）
INPUT_COLS = ["pair_id", "mt_peptide", "wt_peptide", "mut_pos_1based", "pep_len"]


def single_diff_position(mt: str, wt: str):
    """
    MT vs WT 逐位比对。返回 (status, pos)：
      status='ok'        → pos = 差异残基位置（按 POS_BASE）；恰好 1 个残基差异
      status='identical' → MT==WT（0 差异）
      status='multi_diff'→ >1 个残基差异
      status='len_mismatch' → MT/WT 长度不同（无法定义单残基替换）
    """
    if len(mt) != len(wt):
        return ("len_mismatch", None)
    diff_idx = [i for i in range(len(mt)) if mt[i] != wt[i]]
    if len(diff_idx) == 0:
        return ("identical", None)
    if len(diff_idx) > 1:
        return ("multi_diff", None)
    # 恰好 1 个差异：index 0-based → 按 POS_BASE 输出
    return ("ok", diff_idx[0] + POS_BASE)


def prep(universe: pathlib.Path, out_dir: pathlib.Path, smoke: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    input_path   = out_dir / "neoag_input.csv"
    pairmap_path = out_dir / "neoag_pair_map.csv"
    skipped_path = out_dir / "neoag_skipped.csv"

    # 收集 unique (MT, WT) 对，保持插入序
    seen_pairs: set = set()
    valid_rows: list = []     # [pair_id, mt, wt, pos, plen]
    skipped_rows: list = []   # [mt, wt, reason]

    n_total_rows = 0
    n_uniq_pairs = 0
    n_ok = 0
    n_short = 0
    n_long = 0
    n_len_mismatch = 0
    n_identical = 0
    n_multi = 0

    with open(universe, newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        if "MT_Subpeptide" not in reader.fieldnames or "WT_Subpeptide" not in reader.fieldnames:
            print(f"[prep] ERROR: universe 缺 MT_Subpeptide/WT_Subpeptide 列，实有: {reader.fieldnames}",
                  file=sys.stderr)
            sys.exit(1)
        for row in reader:
            n_total_rows += 1
            mt = (row.get("MT_Subpeptide") or "").strip().upper()
            wt = (row.get("WT_Subpeptide") or "").strip().upper()
            if not mt or not wt:
                continue
            pair_key = (mt, wt)
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            n_uniq_pairs += 1

            plen = len(mt)
            # 肽长过滤（按 MT；len_mismatch 单独判）
            if plen < MIN_PEP_LEN:
                n_short += 1
                skipped_rows.append([mt, wt, f"len={plen}_lt_{MIN_PEP_LEN}"])
                continue
            if plen > MAX_PEP_LEN:
                n_long += 1
                skipped_rows.append([mt, wt, f"len={plen}_gt_{MAX_PEP_LEN}"])
                continue

            status, pos = single_diff_position(mt, wt)
            if status == "len_mismatch":
                n_len_mismatch += 1
                skipped_rows.append([mt, wt, f"len_mismatch_MT{len(mt)}_WT{len(wt)}"])
                continue
            if status == "identical":
                n_identical += 1
                skipped_rows.append([mt, wt, "identical_MT_eq_WT"])
                continue
            if status == "multi_diff":
                n_multi += 1
                skipped_rows.append([mt, wt, "multi_residue_diff"])
                continue

            # ok：恰好 1 残基差异
            if smoke > 0 and n_ok >= smoke:
                continue
            pair_id = f"pair_{n_ok}"
            valid_rows.append([pair_id, mt, wt, pos, plen])
            n_ok += 1

    # 写 neoag_input.csv（run_neoag.R 输入）
    with open(input_path, "w", newline="", encoding="utf-8") as f_inp:
        w = csv.writer(f_inp)
        w.writerow(INPUT_COLS)
        for r in valid_rows:
            w.writerow(r)

    # 写 pair_map.csv（溯源：含 valid，skip 信息在 skipped.csv）
    with open(pairmap_path, "w", newline="", encoding="utf-8") as f_map:
        w = csv.writer(f_map)
        w.writerow(["pair_id", "mt_peptide", "wt_peptide", "mut_pos_1based", "pep_len"])
        for r in valid_rows:
            w.writerow(r)

    # 写 skipped.csv
    with open(skipped_path, "w", newline="", encoding="utf-8") as f_skip:
        w = csv.writer(f_skip)
        w.writerow(["mt_peptide", "wt_peptide", "reason"])
        for r in skipped_rows:
            w.writerow(r)

    print(f"[prep] universe 总行数:                {n_total_rows}")
    print(f"[prep] unique (MT,WT) 对:              {n_uniq_pairs}")
    print(f"[prep] 有效对(8-11mer + 单残基差异):   {n_ok}")
    print(f"[prep]   skip <{MIN_PEP_LEN}mer:                 {n_short}")
    print(f"[prep]   skip >{MAX_PEP_LEN}mer:                 {n_long}")
    print(f"[prep]   skip MT/WT 长度不等:          {n_len_mismatch}")
    print(f"[prep]   skip MT==WT(无突变):          {n_identical}")
    print(f"[prep]   skip 多残基差异:              {n_multi}")
    print(f"[prep] POS_BASE = {POS_BASE}（mut_pos_1based 按此 base，⚠️TODO 官方未核）")
    if smoke > 0:
        print(f"[prep] [SMOKE] 仅前 {n_ok} 个有效对，全量去掉 --smoke")
    print(f"[prep] 输入 CSV: {input_path}")
    print(f"[prep] pair_map: {pairmap_path}")
    print(f"[prep] skipped:  {skipped_path}")
    print("[prep] 下一步（主窗）: python run_neoag.py --repo <clone> --rscript <Rscript>")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="准备 neoag 输入（unique MT/WT 对 + 8-11mer + 单残基突变位号）"
    )
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE),
                        help="universe.csv 路径（默认 scripts/out/newtools/universe.csv）")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR),
                        help="输出目录（默认本脚本目录 neoag/）")
    parser.add_argument("--smoke", type=int, default=0, metavar="N",
                        help="烟测：只保留前 N 个有效对（建议 N=5，0=关闭）")
    args = parser.parse_args()

    universe = pathlib.Path(args.universe)
    out_dir  = pathlib.Path(args.out_dir)

    if not universe.exists():
        print(f"[prep] ERROR: universe 不存在: {universe}", file=sys.stderr)
        sys.exit(1)

    prep(universe, out_dir, smoke=args.smoke)


if __name__ == "__main__":
    main()
