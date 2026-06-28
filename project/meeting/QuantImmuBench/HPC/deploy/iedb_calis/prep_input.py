"""
prep_input.py  --  QuantImmuBench §Tier-0 first wave  IEDB Calis 2013 输入准备
服务项目：quantimmu-bench benchmark 扩张 v2 第一波  lever=部署IEDB_Calis

工具：IEDB Class I Immunogenicity Predictor v3.0
      Calis et al. 2013 PLoS Comput Biol 9(10):e1003253
许可：NPOSL-3.0（纯统计模型，数字可自由发布，不触发 DTU 限制）
官方下载：https://downloads.iedb.org/tools/immunogenicity/LATEST/IEDB_Immunogenicity-3.0.tar.gz
CLI：python predict_immunogenicity.py [--allele=<IEDB_tag>] input.txt

功能：
  1. 读 uniq_pep_hla.csv（peptide, HLA_Allele, source）
  2. 将 HLA_Allele 转为 IEDB Calis 格式（去 * 去 :，如 HLA-A*02:01 → HLA-A0201）
  3. 检查是否在工具支持的 42 个 allele 中（从 predict_immunogenicity.py 源码提取）
  4. 按 allele 分组写肽序列文本文件（每行一肽），供 predict_immunogenicity.py 输入
  5. 写 allele_manifest.csv：allele_tag / original_hla / is_supported / pep_count /
     pep_filename / scores_filename

HLA 处理策略：
  - 在支持列表中的 allele：run_iedb_calis.sh 传 --allele=<allele_tag>（allele-specific mask）
  - 不在列表的 allele（HLA-C 全部 + 部分 HLA-A/B）：不传 --allele（默认 mask P1,P2,C-term）
  - 同一肽与不同 allele 配对时，如 allele 支持情况不同，得分可能有细微差异（mask 位置不同）
  - 详见 NOTES.md

用法：
    python prep_input.py [--uniq-pep-hla PATH] [--out-dir DIR]
    默认 --uniq-pep-hla：scripts/out/newtools/uniq_pep_hla.csv（相对 QuantImmuBench root）
    默认 --out-dir    ：scripts/out/newtools/iedb_calis_inputs/
"""

import argparse
import csv
import pathlib
from collections import defaultdict


# ---------------------------------------------------------------------------
# IEDB Calis 2013 支持的 allele
# 来源：IEDB_Immunogenicity-3.0/immunogenicity/predict_immunogenicity.py
#       allele_dict.keys()（42 个，含 6 个小鼠 H-2 allele + 36 个 HLA）
# 格式：无星号无冒号（如 HLA-A0201），与 hla_to_iedb() 转换后格式一致
# 注：我们 universe.csv 的 65 个 HLA allele 中约 17 个在此列表内
#     HLA-C allele 全部不在列表，均使用默认 mask（P1, P2, C-term）
# ---------------------------------------------------------------------------
SUPPORTED_ALLELES: frozenset[str] = frozenset({
    # Mouse H-2 alleles（来源：predict_immunogenicity.py allele_dict）
    "H-2-Db", "H-2-Dd", "H-2-Kb", "H-2-Kd", "H-2-Kk", "H-2-Ld",
    # HLA class I alleles
    "HLA-A0101", "HLA-A0201", "HLA-A0202", "HLA-A0203", "HLA-A0206", "HLA-A0211",
    "HLA-A0301", "HLA-A1101", "HLA-A2301", "HLA-A2402", "HLA-A2601", "HLA-A2902",
    "HLA-A3001", "HLA-A3002", "HLA-A3101", "HLA-A3201", "HLA-A3301", "HLA-A6801",
    "HLA-A6802", "HLA-A6901",
    "HLA-B0702", "HLA-B0801", "HLA-B1501", "HLA-B1502", "HLA-B1801", "HLA-B2705",
    "HLA-B3501", "HLA-B3901", "HLA-B4001", "HLA-B4002", "HLA-B4402", "HLA-B4403",
    "HLA-B4501", "HLA-B4601", "HLA-B5101", "HLA-B5301", "HLA-B5401", "HLA-B5701",
    "HLA-B5801",
})


def hla_to_iedb(h: str) -> str:
    """
    HLA_Allele 转 IEDB Calis 格式：去 * 去 :
    例：HLA-A*02:01 → HLA-A0201  /  HLA-C*07:02 → HLA-C0702
    """
    return h.replace("*", "").replace(":", "")


def allele_tag_to_file_tag(allele_tag: str) -> str:
    """
    allele_tag → 文件名 tag（去 HLA- 前缀，替换连字符为下划线）
    例：HLA-A0201 → A0201  /  H-2-Db → H_2_Db
    """
    return allele_tag.replace("HLA-", "").replace("-", "_")


def main() -> None:
    # 默认路径：本脚本在 HPC/deploy/iedb_calis/，repo root 在上 4 级
    script_dir = pathlib.Path(__file__).parent
    repo_root = script_dir.parents[3]  # QuantImmuBench/
    default_src = repo_root / "scripts" / "out" / "newtools" / "uniq_pep_hla.csv"
    default_out = repo_root / "scripts" / "out" / "newtools" / "iedb_calis_inputs"

    parser = argparse.ArgumentParser(
        description="Prepare IEDB Calis 2013 immunogenicity predictor input files"
    )
    parser.add_argument(
        "--uniq-pep-hla",
        default=str(default_src),
        help="uniq_pep_hla.csv 路径（含 peptide,HLA_Allele,source 列）",
    )
    parser.add_argument(
        "--out-dir",
        default=str(default_out),
        help="输出目录（默认 scripts/out/newtools/iedb_calis_inputs/）",
    )
    args = parser.parse_args()

    src_path = pathlib.Path(args.uniq_pep_hla)
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not src_path.exists():
        raise FileNotFoundError(f"uniq_pep_hla.csv 不存在: {src_path}")

    # allele_tag → set of unique peptides（小写标准化后的去重集合）
    allele_peps: dict[str, set[str]] = defaultdict(set)
    # allele_tag → 第一次遇到的 original HLA string（供 manifest 记录）
    allele_original: dict[str, str] = {}

    total_input_rows = 0
    skipped_empty = 0

    with open(src_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pep = row["peptide"].strip()
            hla_raw = row["HLA_Allele"].strip()
            total_input_rows += 1
            if not pep or not hla_raw:
                skipped_empty += 1
                continue
            allele_tag = hla_to_iedb(hla_raw)
            allele_peps[allele_tag].add(pep.upper())  # 统一大写
            if allele_tag not in allele_original:
                allele_original[allele_tag] = hla_raw

    print(f"[prep] 读取 {total_input_rows} 行，跳过空行 {skipped_empty}")
    print(f"[prep] 唯一 allele 数：{len(allele_peps)}")

    # ---- 写 per-allele 肽序列文件 + 收集 manifest 数据 ----
    manifest_rows: list[dict] = []
    supported_count = 0

    for allele_tag in sorted(allele_peps.keys()):
        pep_set = allele_peps[allele_tag]
        pep_list = sorted(pep_set)  # 排序确保可复现
        is_supported = allele_tag in SUPPORTED_ALLELES
        file_tag = allele_tag_to_file_tag(allele_tag)

        pep_filename = f"{file_tag}.txt"
        scores_filename = f"{file_tag}_scores.txt"
        pep_file = out_dir / pep_filename

        with open(pep_file, "w", encoding="utf-8") as fout:
            for pep in pep_list:
                fout.write(pep + "\n")

        if is_supported:
            supported_count += 1

        manifest_rows.append({
            "allele_tag": allele_tag,
            "original_hla": allele_original.get(allele_tag, allele_tag),
            "is_supported": is_supported,
            "pep_count": len(pep_list),
            "pep_filename": pep_filename,
            "scores_filename": scores_filename,
        })

        status = "allele-specific mask" if is_supported else "default mask"
        print(f"[prep]   {allele_tag:<18} ({status:<22}) → {pep_filename}  ({len(pep_list)} peps)")

    # ---- 写 allele_manifest.csv ----
    manifest_path = out_dir / "allele_manifest.csv"
    fieldnames = ["allele_tag", "original_hla", "is_supported", "pep_count", "pep_filename", "scores_filename"]
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(manifest_rows)

    total_alleles = len(manifest_rows)
    unsupported_count = total_alleles - supported_count
    total_pep_allele = sum(r["pep_count"] for r in manifest_rows)

    print(f"\n[prep] ✓ allele_manifest.csv → {manifest_path}")
    print(f"[prep]   allele 总数：{total_alleles}  "
          f"（{supported_count} 支持 allele-specific mask + {unsupported_count} 使用 default mask）")
    print(f"[prep]   pep×allele 总对数：{total_pep_allele}")
    print(f"\n[prep] 下一步：")
    print(f"  1. 将 {out_dir}/ 上传至 HPC")
    print(f"  2. HPC 上运行 run_iedb_calis.sh（下载 IEDB 工具 + 批量打分）")
    print(f"  3. 将 HPC 的 scores/ 目录取回")
    print(f"  4. 运行 parse_output.py 回贴 universe.csv → IEDB_Calis_DS1DS2_scores.csv")


if __name__ == "__main__":
    main()
