# -*- coding: utf-8 -*-
"""
prep_predig_hpc.py — Phase B：在 HPC 上为 PredIG singularity 重推理准备 recombinant 输入。

本脚本 = scripts/phaseB/run_predig_101102.py 的 prep 段拆分（HPC 路径变体），逻辑零改动：
只读订正源 backbone，构建 PredIG recombinant 输入 input.csv（保序），并写并行的
meta.csv 记录每个输入行的 (bb_idx, side)，供 parse 段位置 join 用。

口径与原 86 肽严格一致（源 = run_predig_101102.build_input）：
  - epitope     = MT_Subpeptide / WT_Subpeptide（仅长度 8-14 且标准 20 氨基酸的肽送工具）
  - protein_seq = MT_FullPeptide / WT_FullPeptide（全长肽缺失时退化为子肽）
  - HLA_allele  = backbone HLA_Allele 原样（标准格式 HLA-A*66:01，带星带冒号）
  - protein_name= {Peptide_ID}|{MT|WT}|win{Window_Size}|pos{Position}|{HLA} 唯一标识
不合格肽（长度∉[8,14] 或非标准氨基酸）不进 input.csv → parse 时该 bb_idx 该 side = NaN。

唯一订正输入源 = $QIB_BASE/phaseB/backbone_101102.csv（已过闸门1：HLA_Allele == 订正真值
P101={A*66:01,B*40:01,B*57:01,C*06:02}/P102={A*02:01,B*35:03,B*38:01}）。

容器 run.py 限制单次 input CSV < 5000 行 → 本脚本把 input.csv 同时切成
input_chunk{K}.csv（每块 ≤ --chunk-size 行，默认 4000），bash 逐块跑 singularity，
跑完按 K 序把各块 out 拼回 out.csv 再 parse。meta.csv 保持全量（parse 对拼接后的
完整 out.csv 位置 join，无需切 meta；各块按 K 序拼接后总行序 == 完整 input.csv 行序）。

用法:
    python prep_predig_hpc.py [--smoke N] [--chunk-size N] [--backbone ...] [--workdir ...]
    --smoke N:      只取前 N 个输入行（验镜像能跑）。
    --chunk-size N: 每块最大行数（默认 4000，须 < 容器上限 5000）。
环境变量覆盖: QIB_BASE / PREDIG_BACKBONE / PREDIG_WORKDIR
"""
import argparse
import csv
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── HPC 路径默认（实证本项目部署）─────────────────────────────────────────────
HPC_BASE = os.environ.get("QIB_BASE", "/gpfs/work/bio/jiayu2403/quantimmu")
DEFAULT_BACKBONE = os.environ.get("PREDIG_BACKBONE", f"{HPC_BASE}/phaseB/backbone_101102.csv")
DEFAULT_WORKDIR = os.environ.get("PREDIG_WORKDIR", f"{HPC_BASE}/phaseB/predig_work")

VALID_LEN = range(8, 15)               # PredIG recombinant 接受 8..14 mer（原 export_predig 同）
STD_AA = set("ACDEFGHIKLMNPQRSTVWY")   # MHCflurry/NOAH 仅接受标准 20 氨基酸


def is_clean_pep(p: str) -> bool:
    return bool(p) and len(p) in VALID_LEN and all(c in STD_AA for c in p)


def build_input(rows):
    """
    从 backbone 行构建 PredIG recombinant 输入（保序）。
    返回 (records, meta)：
      records = [{epitope,HLA_allele,protein_seq,protein_name}, ...]
      meta    = [(bb_idx, side), ...]  与 records 一一对应、同序（位置 join 用）
    长度/氨基酸不合格的肽不进 records（回贴时该 bb_idx 该 side = NaN）。
    """
    records, meta = [], []
    for r in rows:
        bb_idx = r["bb_idx"]
        hla = r["HLA_Allele"].strip()                 # 保标准 HLA-A*66:01
        pid = str(r.get("Peptide_ID", "")).strip()
        win = str(r.get("Window_Size", "")).strip()
        pos = str(r.get("Position", "")).strip()
        for side, sub_col, full_col in (
            ("MT", "MT_Subpeptide", "MT_FullPeptide"),
            ("WT", "WT_Subpeptide", "WT_FullPeptide"),
        ):
            sub = (r.get(sub_col) or "").strip().upper()
            full = (r.get(full_col) or "").strip().upper()
            if not is_clean_pep(sub):
                continue  # 不送工具 → NaN
            pname = f"{pid}|{side}|win{win}|pos{pos}|{hla}"
            records.append({
                "epitope": sub,
                "HLA_allele": hla,
                "protein_seq": full if full else sub,  # 全长肽缺失时退化为子肽
                "protein_name": pname,
            })
            meta.append((bb_idx, side))
    return records, meta


def main():
    ap = argparse.ArgumentParser(description="Phase B PredIG prep（HPC recombinant 输入）")
    ap.add_argument("--smoke", type=int, default=0, help="只取前 N 个输入行（验镜像能跑）")
    ap.add_argument("--chunk-size", type=int, default=4000,
                    help="每块最大行数（默认 4000，须 < 容器上限 5000）")
    ap.add_argument("--backbone", default=DEFAULT_BACKBONE, help="订正源 backbone_101102.csv（只读）")
    ap.add_argument("--workdir", default=DEFAULT_WORKDIR, help="singularity 挂载工作目录（写 input.csv/meta.csv）")
    args = ap.parse_args()
    if args.chunk_size < 1 or args.chunk_size >= 5000:
        raise SystemExit(f"[FAIL] --chunk-size 须 1..4999（容器限 <5000），实得 {args.chunk_size}")

    backbone = Path(args.backbone)
    workdir = Path(args.workdir)
    if not backbone.exists():
        raise SystemExit(f"[FAIL] 订正源不存在: {backbone}")
    workdir.mkdir(parents=True, exist_ok=True)

    with open(backbone, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    records, meta = build_input(rows)
    n_mt = sum(1 for _, s in meta if s == "MT")
    n_wt = sum(1 for _, s in meta if s == "WT")

    # ── 自校验：打印 backbone 唯一 HLA（订正核对）─────────────────────────────
    uniq_hla = sorted({r["HLA_Allele"].strip() for r in rows})
    print(f"[prep] backbone = {backbone}")
    print(f"[prep] backbone={len(rows)} 行 → PredIG 输入 {len(records)} 行"
          f"（MT={n_mt} / WT={n_wt}；长度∉[8,14]或非标准氨基酸已剔置NaN）")
    print(f"[prep] backbone 唯一 HLA（订正核对）: {uniq_hla}")

    if args.smoke:
        records = records[:args.smoke]
        meta = meta[:args.smoke]
        print(f"[smoke] 截前 {len(records)} 行送 singularity")

    # 写 input.csv（保序，列序与原 predig_input.csv 一致）
    in_fields = ["epitope", "HLA_allele", "protein_seq", "protein_name"]
    input_csv = workdir / "input.csv"
    with open(input_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=in_fields)
        w.writeheader()
        w.writerows(records)

    # 写并行 meta.csv（每行 = input.csv 同序的 bb_idx,side，parse 位置 join 用）
    meta_csv = workdir / "meta.csv"
    with open(meta_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bb_idx", "side"])
        w.writeheader()
        for bb_idx, side in meta:
            w.writerow({"bb_idx": bb_idx, "side": side})

    print(f"[prep] 写 {input_csv}（{len(records)} 行）")
    print(f"[prep] 写 {meta_csv}（{len(meta)} 行，与 input.csv 同序）")

    # ── 切分块：input_chunk{K}.csv（每块 ≤ chunk_size，绕容器 <5000 行限制）─────────
    # 先清理上轮残留分块（防 bash 拼接时混入旧 out_chunk 对应的过期 input）。
    for old in sorted(workdir.glob("input_chunk*.csv")):
        old.unlink()
    cs = args.chunk_size
    nchunks = 0
    for k in range(0, len(records), cs):
        chunk = records[k:k + cs]
        cf = workdir / f"input_chunk{nchunks}.csv"
        with open(cf, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=in_fields)
            w.writeheader()
            w.writerows(chunk)
        nchunks += 1
    if nchunks == 0:  # records 为空（理论不至于）：仍写一个空块保 bash 循环不空跑
        cf = workdir / "input_chunk0.csv"
        with open(cf, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=in_fields).writeheader()
        nchunks = 1
    print(f"[prep] 切 {nchunks} 块 input_chunk0..{nchunks - 1}.csv（每块 ≤{cs} 行，容器限 <5000）")


if __name__ == "__main__":
    main()
