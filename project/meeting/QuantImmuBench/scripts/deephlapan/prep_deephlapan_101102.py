#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ===========================================================================
# prep_deephlapan_101102.py — Phase B deepHLApan 输入构造（HLA 订正后重推理）
# 服务: QuantImmuBench / Phase B / lever=HLA-AUDIT 用订正 HLA 重推理填合表缺口
#
# 唯一输入源: scripts/out/phaseB/backbone_101102.csv（订正真值，4018 行）
#   只从这份派生，绝不读旧 deephlapan_input*.csv（防旧伪迹 HLA）。
#
# deepHLApan 是 context-free（同 (subpeptide, HLA) 同分），故对 MT_Subpeptide
# 与 WT_Subpeptide 取并集去重，构造单个最小输入 → 一次 docker 跑覆盖两侧。
#
# 输出格式（deepHLApan 要求，TOOLS/deepHLApan.md §1）:
#   CSV header: Annotation,HLA,peptide
#   HLA 无星号、保 HLA- 前缀: HLA-A*66:01 → HLA-A66:01
#   肽长 8–15 AA（本数据全为 8–14，全合规）
#
# 用法（主线跑）:
#   python scripts/deephlapan/prep_deephlapan_101102.py
# 产出:
#   scripts/out/phaseB/deephlapan_input_101102.csv
# ===========================================================================

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # QuantImmuBench/
BACKBONE = ROOT / "scripts" / "out" / "phaseB" / "backbone_101102.csv"
OUT_INPUT = ROOT / "scripts" / "out" / "phaseB" / "deephlapan_input_101102.csv"

MIN_LEN, MAX_LEN = 8, 15  # deepHLApan 接受 8–15 AA


def hla_no_star(hla_std: str) -> str:
    """HLA-A*66:01 → HLA-A66:01（去星号，保留 HLA- 前缀；deepHLApan 输入/输出格式）。"""
    return str(hla_std).replace("*", "").strip()


def main() -> None:
    if not BACKBONE.exists():
        raise SystemExit(f"[ERROR] 输入源不存在: {BACKBONE}")

    # 收集 MT/WT subpeptide 与订正 HLA 的去重 (peptide, HLA_no_star) 对
    pairs = {}  # (peptide, hla_ns) -> 保序
    skipped = 0
    with BACKBONE.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            hla_ns = hla_no_star(row["HLA_Allele"])
            for col in ("MT_Subpeptide", "WT_Subpeptide"):
                pep = str(row[col]).strip()
                if not (MIN_LEN <= len(pep) <= MAX_LEN):
                    skipped += 1
                    continue
                key = (pep, hla_ns)
                if key not in pairs:
                    pairs[key] = len(pairs)

    OUT_INPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT_INPUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Annotation", "HLA", "peptide"])
        for (pep, hla_ns), idx in pairs.items():
            w.writerow([f"dp_{idx}", hla_ns, pep])

    hlas = sorted({h for _, h in pairs})
    print(f"[prep] 唯一 (peptide, HLA) 对: {len(pairs)}")
    print(f"[prep] 跳过(肽长越界): {skipped}")
    print(f"[prep] HLA 集({len(hlas)}): {hlas}")
    print(f"[prep] 写出: {OUT_INPUT}")


if __name__ == "__main__":
    main()
