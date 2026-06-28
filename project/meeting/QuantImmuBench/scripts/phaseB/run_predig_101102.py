# -*- coding: utf-8 -*-
"""
run_predig_101102.py — Phase B：用订正 HLA 等位重推理 PredIG（P101/P102）。

唯一订正输入源 = scripts/out/phaseB/backbone_101102.csv（prep_101102_subset.py 产，
已过闸门1：HLA_Allele == 订正真值 P101={A66:01,B40:01,B57:01,C06:02}/
P102={A02:01,B35:03,B38:01}）。本脚本只从这份派生，绝不读旧 predig_input.csv。

PredIG 走官方 Docker 镜像 bsceapm/predig:latest（14.4GB，recombinant 模式，避开 UniProt 库）。
自包含三步（prep+run+parse 一体），与原 prepare_inputs.export_predig + merge_results
位置 join 逻辑完全一致：
  1. prep：从 backbone 取每行的 MT 行（epitope=MT_Subpeptide, protein_seq=MT_FullPeptide）
     + WT 行（epitope=WT_Subpeptide, protein_seq=WT_FullPeptide），仅长度 8-14 且
     标准 20 氨基酸的肽送工具，其余置 NaN。HLA_allele 保标准格式 HLA-A*66:01（带星带冒号）。
     protein_name = {Peptide_ID}|{MT|WT}|win{Window_Size}|pos{Position}|{HLA} 唯一标识。
     写 predig_work/input.csv，同时记录每个输入行的 (bb_idx, side) 元数据（保序）。
  2. run：docker run 挂载 predig_work→/work，跑
       <input.csv> -o out.csv --modelXG neoant --type recombinant
  3. parse：PredIG 输出无 protein_name 但**严格保输入行序**（output[i] ↔ input[i]），
     位置 join 恢复 (bb_idx, side)，并断言 output[i].epitope/HLA == input[i] 防错序。
     PredIG 列（0-1，1=最高免疫原）回贴每行 bb_idx 的 MT/WT 分数。

产出: scripts/out/phaseB/PredIG_101102.csv
      列: bb_idx, MT_PredIG, WT_PredIG
方向: PredIG 分越高越免疫原（官方原始方向，无翻转）。

用法:
    python run_predig_101102.py [--smoke N]
    --smoke N: 只送前 N 个输入行给 docker（验镜像能跑、分数 ∈[0,1]），不产正式 CSV。
"""
import argparse
import csv
import math
import os
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # QuantImmuBench/
BACKBONE = ROOT / "scripts" / "out" / "phaseB" / "backbone_101102.csv"
WORKDIR = ROOT / "scripts" / "out" / "phaseB" / "predig_work"  # docker 挂载 /work
INPUT_CSV = WORKDIR / "input.csv"
OUT_CSV = WORKDIR / "out.csv"
OUT = ROOT / "scripts" / "out" / "phaseB" / "PredIG_101102.csv"

DOCKER_IMAGE = "bsceapm/predig:latest"
MODEL_XG = "neoant"   # 三类抗原模型：neoant=新抗原（本部署固定，与原 5tools 部署一致）

VALID_LEN = range(8, 15)            # PredIG recombinant 接受 8..14 mer（原 export_predig 同）
STD_AA = set("ACDEFGHIKLMNPQRSTVWY")  # MHCflurry/NOAH 仅接受标准 20 氨基酸


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


def run_docker(workdir: Path):
    """
    docker run 调 PredIG 镜像（recombinant 模式，挂载 workdir→/work）。
    入参顺序与 TOOLS/PredIG.md 实测命令一致：
      <input.csv 位置参> -o <out.csv> --modelXG neoant --type recombinant
    NOTE: Windows Docker Desktop 的 -v 用 posix 风格绝对路径（D:/...），主线本地跑。
          HPC 上等价命令走 singularity（见 HPC/elispot_run/predig_elispot.sh）：
          singularity run --writable-tmpfs -B <workdir>:/work predig.sif \
            /work/input.csv -o /work/out.csv --modelXG neoant --type recombinant
    """
    mount = f"{workdir.resolve().as_posix()}:/work"
    cmd = [
        "docker", "run", "--rm",
        "-v", mount,
        DOCKER_IMAGE,
        "/work/input.csv",
        "-o", "/work/out.csv",
        "--modelXG", MODEL_XG,
        "--type", "recombinant",
    ]
    print(f"[run] {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    if res.returncode != 0:
        raise RuntimeError(
            f"docker PredIG 失败 rc={res.returncode}\n"
            f"STDERR: {res.stderr[-800:]}\nSTDOUT: {res.stdout[-400:]}"
        )
    return res


def read_predig_out(path: Path):
    """读 PredIG out.csv → list[dict]，校验含 epitope/HLA_allele/PredIG 列。"""
    with open(path, newline="", encoding="utf-8") as f:
        out_rows = list(csv.DictReader(f))
    if not out_rows:
        raise RuntimeError(f"PredIG 输出为空: {path}")
    need = {"epitope", "HLA_allele", "PredIG"}
    have = set(out_rows[0].keys())
    if not need.issubset(have):
        raise RuntimeError(f"PredIG 输出缺列 {need - have}，实际列: {sorted(have)}")
    return out_rows


def position_join(out_rows, records, meta):
    """
    位置 join：PredIG 严格保输入行序 → output[i] ↔ records[i] ↔ meta[i]。
    断言 epitope/HLA 一致防错序，返回 (bb_idx, side) → PredIG_score。
    """
    n_out, n_in = len(out_rows), len(records)
    if n_out != n_in:
        raise RuntimeError(
            f"PredIG 行数不符: output={n_out} != input={n_in}（位置 join 不可用，"
            "检查工具是否丢/并行重排了行）"
        )
    joined = {}
    for i, (orow, irec, (bb_idx, side)) in enumerate(zip(out_rows, records, meta)):
        oe = (orow.get("epitope") or "").strip().upper()
        oh = (orow.get("HLA_allele") or "").strip()
        if oe != irec["epitope"] or oh != irec["HLA_allele"]:
            raise RuntimeError(
                f"PredIG 位置 join 断言失败 @行{i}: "
                f"output=({oe},{oh}) != input=({irec['epitope']},{irec['HLA_allele']})。"
                "输出行序被打乱，不能位置 join。"
            )
        try:
            val = float((orow.get("PredIG") or "").strip())
        except ValueError:
            val = float("nan")
        joined[(bb_idx, side)] = val
    return joined


def main():
    ap = argparse.ArgumentParser(description="Phase B PredIG 重推理 P101/P102（docker recombinant）")
    ap.add_argument("--smoke", type=int, default=0,
                    help="只送前 N 个输入行给 docker 验镜像能跑、分数∈[0,1]，不产 CSV")
    args = ap.parse_args()

    if not BACKBONE.exists():
        raise SystemExit(f"[FAIL] 订正源不存在: {BACKBONE}")
    WORKDIR.mkdir(parents=True, exist_ok=True)

    # ── prep：读 backbone 构建 recombinant 输入（保序）─────────────────────────
    with open(BACKBONE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    records, meta = build_input(rows)
    n_mt = sum(1 for _, s in meta if s == "MT")
    n_wt = sum(1 for _, s in meta if s == "WT")
    print(f"[prep] backbone={len(rows)} 行 → PredIG 输入 {len(records)} 行"
          f"（MT={n_mt} / WT={n_wt}；长度∉[8,14]或非标准氨基酸已剔置NaN）")

    if args.smoke:
        records = records[:args.smoke]
        meta = meta[:args.smoke]
        print(f"[smoke] 截前 {len(records)} 行送 docker")

    # 写 input.csv（保序，列序与原 predig_input.csv 一致）
    with open(INPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["epitope", "HLA_allele", "protein_seq", "protein_name"])
        w.writeheader()
        w.writerows(records)
    print(f"[prep] 写 {INPUT_CSV}（{len(records)} 行）")

    # ── run：docker ─────────────────────────────────────────────────────────
    run_docker(WORKDIR)
    out_rows = read_predig_out(OUT_CSV)
    print(f"[run] PredIG 输出 {len(out_rows)} 行 → {OUT_CSV}")

    # ── parse：位置 join ─────────────────────────────────────────────────────
    joined = position_join(out_rows, records, meta)
    vals = [v for v in joined.values() if not math.isnan(v)]
    if vals:
        print(f"[parse] PredIG 分 range [{min(vals):.4f}, {max(vals):.4f}]"
              f"（应 ∈[0,1]，越高越免疫原）")
        oob = [v for v in vals if v < 0 or v > 1]
        if oob:
            print(f"[parse][WARN] {len(oob)} 个分数越界 [0,1]，首个={oob[0]}")

    if args.smoke:
        print(f"\n[smoke] 跑了 {len(records)} 行，镜像可跑、位置 join 通过、分数区间合理。未产 CSV。")
        return

    # ── 回贴 bb_idx，写 PredIG_101102.csv ───────────────────────────────────
    def fmt(bb_idx, side):
        v = joined.get((bb_idx, side))
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""  # NaN → 空（pandas 读为 NaN）
        return str(round(v, 6))

    c_mt = c_wt = c_mt_nan = c_wt_nan = 0
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bb_idx", "MT_PredIG", "WT_PredIG"])
        w.writeheader()
        for r in rows:
            bb_idx = r["bb_idx"]
            mt_s = fmt(bb_idx, "MT")
            wt_s = fmt(bb_idx, "WT")
            c_mt += mt_s != ""
            c_wt += wt_s != ""
            c_mt_nan += mt_s == ""
            c_wt_nan += wt_s == ""
            w.writerow({"bb_idx": bb_idx, "MT_PredIG": mt_s, "WT_PredIG": wt_s})

    print(f"\n[parse] 写 {OUT}  ({len(rows)} 行)")
    print(f"[parse]   MT_PredIG: {c_mt} found / {c_mt_nan} NaN")
    print(f"[parse]   WT_PredIG: {c_wt} found / {c_wt_nan} NaN")
    print(f"[parse]   方向：PredIG 分越高越免疫原（无翻转）")


if __name__ == "__main__":
    main()
