"""
parse_nettepi.py — NetTepi 1.0 输出解析 & 回贴 bb_idx
服务：quantimmu-bench §Tier-2, lever=NetTepi baseline

读 NetTepi 原始输出（每个 allele 一个 txt）+ pep_index.csv
→ 取 Comb / %Rank 列 → 回贴 bb_idx
→ 13 HLA 外的 bb_idx（unsupported_bbidx.csv）填 NaN
→ 输出 scripts/out/newtools/nettepi_DS1DS2_scores.csv

输出 schema（严格）：
    bb_idx, nettepi_Comb, nettepi_Rank, nettepi_score, pending_DTU_consent

nettepi_score 方向说明：
    nettepi_score = nettepi_Comb（Comb 分越高 = 免疫原性越强，方向已正）。
    直接赋值，无需取反。

pending_DTU_consent 说明：
    整列 True。NetTepi binary 需 DTU 学术授权；授权取得前分数不可对外发布。

TODO（跑通后核实）：
    - NetTepi 输出文件实际列名（Comb / %Rank 的精确列头，含空格/大小写）
    - 输出文件分隔符（空白 / tab / 固定宽度）
    - 是否有 header 行及行数偏移
    - 肽列名（Peptide / peptide / #Peptide 等）

用法：
    python parse_nettepi.py [--raw-dir DIR] [--pep-index PATH]
                            [--unsupported PATH] [--out PATH]
"""

import argparse
import csv
import os
import re

# ================================================================
# TODO: 跑通后将下方列名替换为 NetTepi 实际输出列头
# 当前为占位，基于 NetTepi 1.0 论文描述（Metje-Sprink 2020 / DTU README）
# ================================================================
COL_PEPTIDE = "Peptide"       # TODO 核实：肽序列列名
COL_COMB    = "Comb"          # TODO 核实：组合分列名（越高越强）
COL_RANK    = "%Rank"         # TODO 核实：百分位 rank 列名（越低越强，原样存储）

PENDING_DTU_CONSENT = True


def parse_raw_file(filepath: str) -> dict[str, dict]:
    """
    解析单个 NetTepi 原始输出文件。
    返回 {subpeptide: {"Comb": float, "Rank": float}}。

    容错逻辑（TODO 跑通后收紧）：
    - 跳过以 '#' 开头的注释行
    - 自动探测分隔符（tab / 多空格）
    - 若列名不匹配 COL_COMB / COL_RANK → 警告 + 返回空字典
    """
    results: dict[str, dict] = {}

    if not os.path.isfile(filepath):
        print(f"[parse] WARNING: 文件不存在: {filepath}，跳过")
        return results

    with open(filepath, encoding="utf-8", errors="replace") as f:
        lines = [l.rstrip("\n") for l in f.readlines()]

    # 找 header 行（含 Peptide 或 peptide 关键词的行）
    header_idx = None
    for i, line in enumerate(lines):
        if re.search(r"\bpeptide\b", line, re.IGNORECASE):
            header_idx = i
            break

    if header_idx is None:
        print(f"[parse] WARNING: 找不到 header 行（含 'Peptide'）in {filepath}")
        print(f"[parse] TODO: 确认 NetTepi 输出格式后修正列名探测逻辑")
        return results

    # 探测分隔符
    header_line = lines[header_idx]
    sep = "\t" if "\t" in header_line else None  # None → re.split 多空格

    def split_line(line: str) -> list[str]:
        if sep:
            return line.split(sep)
        return re.split(r"\s+", line.strip())

    headers = [h.strip() for h in split_line(header_line)]

    # 定位列索引
    try:
        idx_pep  = headers.index(COL_PEPTIDE)
    except ValueError:
        # 容错：大小写不敏感查找
        lower_headers = [h.lower() for h in headers]
        try:
            idx_pep = lower_headers.index("peptide")
        except ValueError:
            print(f"[parse] WARNING: 找不到 '{COL_PEPTIDE}' 列。header={headers}")
            print(f"[parse] TODO: 确认 NetTepi 输出肽列名")
            return results

    def find_col(name: str, headers: list[str]) -> int | None:
        try:
            return headers.index(name)
        except ValueError:
            lower = [h.lower() for h in headers]
            try:
                return lower.index(name.lower())
            except ValueError:
                return None

    idx_comb = find_col(COL_COMB, headers)
    idx_rank = find_col(COL_RANK, headers)

    if idx_comb is None:
        print(f"[parse] WARNING: 找不到 '{COL_COMB}' 列（Comb 分）。header={headers}")
        print(f"[parse] TODO: 确认 NetTepi Comb 列名")

    if idx_rank is None:
        print(f"[parse] WARNING: 找不到 '{COL_RANK}' 列（%Rank）。header={headers}")
        print(f"[parse] TODO: 确认 NetTepi %Rank 列名")

    # 解析数据行
    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = split_line(line)
        if len(parts) <= idx_pep:
            continue
        pep = parts[idx_pep].strip()
        if not pep:
            continue

        comb_val = None
        rank_val = None

        if idx_comb is not None and idx_comb < len(parts):
            try:
                comb_val = float(parts[idx_comb])
            except ValueError:
                comb_val = None

        if idx_rank is not None and idx_rank < len(parts):
            try:
                rank_val = float(parts[idx_rank])
            except ValueError:
                rank_val = None

        results[pep] = {"Comb": comb_val, "Rank": rank_val}

    return results


def main():
    parser = argparse.ArgumentParser(description="Parse NetTepi output and merge with bb_idx")
    parser.add_argument(
        "--raw-dir",
        default="/gpfs/work/bio/jiayu2403/quantimmu/nettepi_run/out",
        help="Directory containing NetTepi raw output .txt files (one per allele)",
    )
    parser.add_argument(
        "--pep-index",
        default="D:/YJ-Agent/project/meeting/QuantImmuBench/scripts/out/newtools/nettepi_inputs/pep_index.csv",
        help="pep_index.csv from prep_nettepi.py (allele, subpeptide, bb_idx)",
    )
    parser.add_argument(
        "--unsupported",
        default="D:/YJ-Agent/project/meeting/QuantImmuBench/scripts/out/newtools/unsupported_bbidx.csv",
        help="unsupported_bbidx.csv from prep_nettepi.py (bb_idx with HLA outside 13)",
    )
    parser.add_argument(
        "--out",
        default="D:/YJ-Agent/project/meeting/QuantImmuBench/scripts/out/newtools/nettepi_DS1DS2_scores.csv",
        help="Output scores CSV path",
    )
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    # ---- 1. 载入 pep_index（支持 allele） ----
    # allele 格式：HLA-A02:01 → 文件名 tag A0201
    def allele_to_tag(allele: str) -> str:
        return allele.replace("HLA-", "").replace(":", "")

    supported_rows: list[dict] = []      # {bb_idx, allele, subpeptide}
    with open(args.pep_index, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            supported_rows.append({
                "bb_idx":     int(row["bb_idx"]),
                "allele":     row["allele"],
                "subpeptide": row["subpeptide"],
            })

    # ---- 2. 载入每个 allele 的 NetTepi 输出 ----
    # 按 allele tag 聚合，避免重复读同一文件
    allele_data: dict[str, dict[str, dict]] = {}  # tag → {subpep → {Comb, Rank}}
    for row in supported_rows:
        tag = allele_to_tag(row["allele"])
        if tag not in allele_data:
            raw_file = os.path.join(args.raw_dir, f"{tag}_nettepi_raw.txt")
            allele_data[tag] = parse_raw_file(raw_file)

    # ---- 3. 回贴 bb_idx ----
    out_rows: list[dict] = []

    for row in supported_rows:
        tag = allele_to_tag(row["allele"])
        pep_results = allele_data.get(tag, {})
        subpep = row["subpeptide"]
        hit = pep_results.get(subpep, {})

        comb = hit.get("Comb")   # None if missing
        rank = hit.get("Rank")   # None if missing

        # nettepi_score = Comb（越高越强，方向已正，直接赋值）
        nettepi_score = comb

        out_rows.append({
            "bb_idx":              row["bb_idx"],
            "nettepi_Comb":        "" if comb is None else comb,
            "nettepi_Rank":        "" if rank is None else rank,
            "nettepi_score":       "" if nettepi_score is None else nettepi_score,
            "pending_DTU_consent": PENDING_DTU_CONSENT,
        })

    # ---- 4. 载入 unsupported_bbidx → 填 NaN（空字符串） ----
    if os.path.isfile(args.unsupported):
        with open(args.unsupported, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                out_rows.append({
                    "bb_idx":              int(row["bb_idx"]),
                    "nettepi_Comb":        "",   # NaN: HLA not in 13 supported
                    "nettepi_Rank":        "",
                    "nettepi_score":       "",
                    "pending_DTU_consent": PENDING_DTU_CONSENT,
                })
    else:
        print(f"[parse] WARNING: unsupported_bbidx.csv 不存在: {args.unsupported}（先跑 prep_nettepi.py）")

    # ---- 5. 按 bb_idx 排序写出 ----
    out_rows.sort(key=lambda r: int(r["bb_idx"]))

    FIELDNAMES = ["bb_idx", "nettepi_Comb", "nettepi_Rank", "nettepi_score", "pending_DTU_consent"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"[parse] wrote {len(out_rows)} rows → {args.out}")
    supported_n  = sum(1 for r in out_rows if r["nettepi_score"] != "")
    nan_n        = sum(1 for r in out_rows if r["nettepi_score"] == "")
    print(f"[parse]   scored={supported_n}  NaN(unsupported HLA)={nan_n}")
    print(f"[parse]   pending_DTU_consent={PENDING_DTU_CONSENT}")


if __name__ == "__main__":
    main()
