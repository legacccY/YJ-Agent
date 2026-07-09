#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prep_seq2neo_official.py — 从 master_backbone 生成 Seq2Neo immuno 输入 (HPC, 主线跑)
服务: quantimmu-bench Phase0 官方数据工具补跑舰队 (lever=Seq2Neo, bonus 升正式)

作用:
  读 master_backbone_official.csv (1761 行) → 取 MT_Subpeptide(9mer) + HLA_Allele
  → 生成 Seq2Neo `immuno --mode multiple` 的输入 CSV (列 `Pep,HLA`)。

Seq2Neo 输入格式 (官方源核实, 带源):
  - 列名 = `Pep,HLA` (P 大写)。见 repo seq2neo/function/immuno_Prediction/data/test_input.csv:
        Pep,HLA
        ADTSEARPFW,HLA-B44:02
  - HLA = **无星号** 格式 `HLA-B44:02` (benchmark 的 HLA-B*44:02 去掉 `*`)。
    依据: add_tap_ic50.py 注释「免疫原性模块的HLA的形式与netMHCpan和netCTLpan相同，直接用即可」,
    且 _cnn.py::hlatopseudoseq 内部 `a.replace("*","")` 去星后 merge class1_pseudosequences.csv。

肽长过滤 (官方源核实):
  - _cnn.py::encode(peptides, maxlen=11): len > 11 → 返回 ["NaN"] (编码失败)。
    故只写入 8 ≤ len ≤ 11 的肽; 越界肽长跳过 (打印跳过数)。
    backbone MT_Subpeptide 为 9mer, 正常应全部通过; 防御性过滤防异常行。
  - 被跳过的肽在 parse 阶段不在 score_map → 自然 NaN (诚实留空, 不兜底)。

去重: 同 (Pep, HLA) 对只跑一次 (省 netMHCpan/netCTLpan 调用); parse 按内容回贴, 去重无损。

输出:
  --out  seq2neo_input.csv  (列 Pep,HLA; 去重后的唯一对; 含表头)
  parse 阶段直接读 backbone 做 (Pep,HLA)→bb_idx 精确映射, 无须额外 index 文件。

Windows/HPC: utf-8 显式, pathlib, 纯标准库 (csv)。
红线: 仅准备输入, 不运行 Seq2Neo (主线在 HPC linux 跑)。复现零偏离。
"""

import argparse
import csv
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def norm_hla_seq2neo(h: str) -> str:
    """benchmark HLA → Seq2Neo 格式: 去星号 + 去空格。HLA-A*02:01 → HLA-A02:01。"""
    return h.strip().replace("*", "").replace(" ", "")


def clean_pep(s: str) -> str:
    s = str(s).strip()
    return "" if s.lower() in ("nan", "none", "<na>", "") else s


def main():
    script_dir = Path(__file__).resolve().parent
    default_backbone = script_dir.parent / "out_official" / "master_backbone_official.csv"
    default_out = script_dir.parent / "out_official" / "seq2neo_inputs" / "seq2neo_input.csv"

    ap = argparse.ArgumentParser(
        description="生成 Seq2Neo immuno 输入 CSV (Pep,HLA) <- master_backbone"
    )
    ap.add_argument("--backbone", default=str(default_backbone))
    ap.add_argument("--out", default=str(default_out))
    ap.add_argument("--min-len", type=int, default=8)
    ap.add_argument("--max-len", type=int, default=11)  # _cnn.py encode maxlen=11
    ap.add_argument("--side", choices=["MT", "WT"], default="MT",
                    help="打分侧：MT 读 MT_Subpeptide（默认，向后兼容 9mer）；"
                         "WT 读 WT_Subpeptide（8-11 DAI 补跑）。仅换肽源列，其余口径不变。")
    ap.add_argument("--smoke", type=int, default=0, help=">0 取前 N 个唯一对烟测")
    args = ap.parse_args()

    pep_col = "MT_Subpeptide" if args.side == "MT" else "WT_Subpeptide"

    backbone = Path(args.backbone)
    if not backbone.exists():
        raise FileNotFoundError(f"backbone 不存在: {backbone}")

    n_rows = 0
    n_skip_pep = 0          # 空肽
    n_skip_len = 0          # 肽长越界
    seen = {}               # (pep, hla_seq2neo) -> True, 保唯一对插入顺序
    alleles = set()
    with open(backbone, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for r in rd:
            n_rows += 1
            pep = clean_pep(r.get(pep_col, ""))
            hla_raw = r.get("HLA_Allele", "")
            if not pep:
                n_skip_pep += 1
                continue
            if not (args.min_len <= len(pep) <= args.max_len):
                n_skip_len += 1
                continue
            hla = norm_hla_seq2neo(hla_raw)
            if not hla:
                continue
            key = (pep, hla)
            if key not in seen:
                seen[key] = True
            alleles.add(hla)

    pairs = list(seen.keys())
    if args.smoke > 0:
        pairs = pairs[: args.smoke]
        print(f"[smoke] 取前 {args.smoke} 个唯一对 -> {len(pairs)}", file=sys.stderr)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Pep", "HLA"])
        for pep, hla in pairs:
            w.writerow([pep, hla])

    print(f"[prep_seq2neo] side={args.side}（肽源列={pep_col}）  backbone 行={n_rows}  "
          f"空肽跳过={n_skip_pep}  肽长越界({args.min_len}-{args.max_len})跳过={n_skip_len}", file=sys.stderr)
    print(f"[prep_seq2neo] 写 {out}  唯一(Pep,HLA)对={len(pairs)}  distinct等位={len(alleles)}",
          file=sys.stderr)
    print("[prep_seq2neo] 下一步(HPC): seq2neo immuno --mode multiple "
          f"--inputfile {out} --outdir <outdir>", file=sys.stderr)


if __name__ == "__main__":
    main()
