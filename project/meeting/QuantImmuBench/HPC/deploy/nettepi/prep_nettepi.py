"""
prep_nettepi.py — NetTepi 1.0 输入准备
服务：quantimmu-bench §Tier-2, lever=NetTepi baseline

读 master_backbone.csv → 筛 HLA ∈ SUPPORTED_HLA → 按 allele 分组写
  - <out_dir>/<allele>.pep      每行一条去重 MT_Subpeptide
  - <out_dir>/pep_index.csv     (allele, subpeptide, bb_idx) 一行一条（不去重，保全 bb_idx）
  - <out_dir>/../unsupported_bbidx.csv  不在 13 个 HLA 内的 bb_idx（score 后填 NaN）

HLA 格式转换：master 列 HLA-A*24:02 → NetTepi 格式 HLA-A24:02（去星保冒号）
pending_DTU_consent=True：NetTepi binary 需学术授权，运行前须获得 DTU 同意

用法：
    python prep_nettepi.py [--backbone PATH] [--out-dir DIR]
"""

import argparse
import csv
import os
from collections import defaultdict

# ===========================================================
# NetTepi 1.0 支持的 13 个 HLA allele（NetTepi 格式，去星）
# 来源：researcher 核 DTU 官方服务页 https://services.healthtech.dtu.dk/services/NetTepi-1.0/
#       (2026-06-26 核实，"represent 11 of the 12 common HLA-A and B Supertypes")
# ===========================================================
SUPPORTED_HLA = [
    "HLA-A01:01",
    "HLA-A02:01",
    "HLA-A03:01",
    "HLA-A11:01",
    "HLA-A24:02",
    "HLA-A26:01",
    "HLA-B07:02",
    "HLA-B15:01",
    "HLA-B27:05",
    "HLA-B35:01",
    "HLA-B39:01",
    "HLA-B40:01",
    "HLA-B58:01",
]  # 13 个，DTU 官方核实

SUPPORTED_HLA_SET = set(SUPPORTED_HLA)

# pending 红线：NetTepi binary 需 DTU 学术授权
PENDING_DTU_CONSENT = True


def convert_hla(raw: str) -> str:
    """
    master HLA_Allele 格式 'HLA-A*24:02' → NetTepi 格式 'HLA-A24:02'
    去掉星号，保留冒号。
    TODO: 跑通后核实 NetTepi CLI 实际接受的 allele 格式。
    """
    return raw.replace("*", "")


def main():
    parser = argparse.ArgumentParser(description="Prepare NetTepi 1.0 input files")
    parser.add_argument(
        "--backbone",
        default="D:/YJ-Agent/project/meeting/QuantImmuBench/scripts/out/master_backbone.csv",
        help="Path to master_backbone.csv",
    )
    parser.add_argument(
        "--out-dir",
        default="D:/YJ-Agent/project/meeting/QuantImmuBench/scripts/out/newtools/nettepi_inputs",
        help="Output directory for .pep files and pep_index.csv",
    )
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    # allele → list of (bb_idx, subpeptide)
    supported: dict[str, list[tuple[int, str]]] = defaultdict(list)
    unsupported_rows: list[dict] = []

    with open(args.backbone, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bb_idx = int(row["bb_idx"])
            raw_hla = row["HLA_Allele"].strip()
            nettepi_hla = convert_hla(raw_hla)
            subpep = row["MT_Subpeptide"].strip()

            if nettepi_hla in SUPPORTED_HLA_SET:
                supported[nettepi_hla].append((bb_idx, subpep))
            else:
                unsupported_rows.append({"bb_idx": bb_idx, "HLA_Allele": raw_hla, "MT_Subpeptide": subpep})

    # ---- 写 .pep 文件（去重，只含子肽序列）----
    for allele, entries in supported.items():
        unique_peps = sorted(set(pep for _, pep in entries))
        # allele tag 用于文件名：去掉 'HLA-' 前缀、替换 ':' 为 ''
        allele_tag = allele.replace("HLA-", "").replace(":", "")
        pep_path = os.path.join(args.out_dir, f"{allele_tag}.pep")
        with open(pep_path, "w", encoding="utf-8") as f:
            for pep in unique_peps:
                f.write(pep + "\n")
        print(f"[prep] wrote {len(unique_peps)} unique peptides → {pep_path}")

    # ---- 写 pep_index.csv（不去重，保全 bb_idx 对照）----
    pep_index_path = os.path.join(args.out_dir, "pep_index.csv")
    with open(pep_index_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["allele", "subpeptide", "bb_idx"])
        writer.writeheader()
        for allele, entries in supported.items():
            for bb_idx, subpep in entries:
                writer.writerow({"allele": allele, "subpeptide": subpep, "bb_idx": bb_idx})
    print(f"[prep] pep_index → {pep_index_path}  ({sum(len(v) for v in supported.values())} rows)")

    # ---- 写 unsupported_bbidx.csv（parse 时填 NaN）----
    unsupported_path = os.path.join(args.out_dir, "..", "unsupported_bbidx.csv")
    unsupported_path = os.path.normpath(unsupported_path)
    with open(unsupported_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["bb_idx", "HLA_Allele", "MT_Subpeptide"])
        writer.writeheader()
        writer.writerows(unsupported_rows)
    print(f"[prep] unsupported → {unsupported_path}  ({len(unsupported_rows)} rows → score=NaN)")

    print("[prep] done. pending_DTU_consent =", PENDING_DTU_CONSENT)


if __name__ == "__main__":
    main()
