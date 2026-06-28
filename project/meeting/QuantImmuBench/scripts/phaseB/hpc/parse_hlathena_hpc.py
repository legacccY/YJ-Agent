# -*- coding: utf-8 -*-
"""
parse_hlathena_hpc.py — Phase B：把 HLAthena per-allele 的 <tag>-predictions.txt
解析回 bb_idx 对齐的合表列（MT_HLAthena + WT_HLAthena）。

⚠️⚠️ HLAthena = MHC-I **提呈（presentation）proxy，不是免疫原性**。下游单列呈现，
不与免疫原性工具并列。方向照原：MSi 越高越提呈，**无翻转**。

在 HPC 上跑（run_hlathena_hpc.sh 调用）。读 <work> 下所有 <tag>-predictions.txt
（17 列含 MSi_<tag> 提呈分），按 (pep_upper, tag) 建 score_dict；再读 bb_map.csv，
对每行 bb_idx 的 mt_pep/wt_pep 各查 (pep, tag) → MSi，写入 MT_HLAthena / WT_HLAthena。
查不到（无 specific 模型 / 12-14mer / 非标准 AA）→ 留空（pandas 读为 NaN），如实不假填。

产出: $BASE/phaseB/HLAthena_101102.csv  列 = bb_idx, MT_HLAthena, WT_HLAthena

服务: quantimmu-bench Phase B HLAthena 101/102 重推理（lever=HLAthena presentation proxy）。
⚠️ 本脚本只写不跑（coder 红线）；sif/解析由主线在 HPC 执行。py_compile 已过。
"""
import argparse
import csv
import math
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def find_col(header, cands):
    """在表头里找首个命中列名（先精确，后大小写不敏感），返回索引或 None。"""
    for c in cands:
        if c in header:
            return header.index(c)
    low = [h.lower() for h in header]
    for c in cands:
        if c.lower() in low:
            return low.index(c.lower())
    return None


def parse_predictions(pred_txt, tag):
    """读 <tag>-predictions.txt（tab 或逗号，17 列），取 MSi 提呈分 → {pep_upper: score}。
    优先列 MSi_<tag>（如 MSi_A0101）；缺则 fallback best.MSi / MSi。peptide 列名常为
    'pep' 或 'peptide'。方向：越高越提呈，无翻转。"""
    text = pred_txt.read_text(encoding="utf-8", errors="replace")
    lines = [ln.rstrip("\r\n") for ln in text.splitlines() if ln.strip()]
    if not lines:
        return {}
    header_line = lines[0]
    sep = "\t" if "\t" in header_line else ","
    header = [h.strip() for h in header_line.split(sep)]

    pep_idx = find_col(header, ["pep", "peptide", "Peptide"])
    msi_idx = find_col(header, [f"MSi_{tag}", "best.MSi", "MSi", "MSi_pan"])
    if pep_idx is None or msi_idx is None:
        raise RuntimeError(
            f"{tag} predictions 缺列 pep/MSi（pep_idx={pep_idx}, msi_idx={msi_idx}），"
            f"实际表头={header}")

    scores = {}
    for ln in lines[1:]:
        parts = ln.split(sep)
        if len(parts) <= max(pep_idx, msi_idx):
            continue
        pep = parts[pep_idx].strip().upper()
        try:
            v = float(parts[msi_idx].strip())
        except ValueError:
            continue
        if not math.isnan(v):
            scores[pep] = v
    return scores


def main():
    ap = argparse.ArgumentParser(description="Phase B HLAthena parse（predictions -> bb_idx 合表列）")
    ap.add_argument("--work", required=True, help="工作目录（含 <tag>-predictions.txt + bb_map.csv）")
    ap.add_argument("--out", required=True, help="输出 HLAthena_101102.csv")
    args = ap.parse_args()

    work = Path(args.work)
    bb_map_csv = work / "bb_map.csv"
    if not bb_map_csv.exists():
        raise SystemExit(f"[FAIL] bb_map 不存在（prep 未跑？）: {bb_map_csv}")

    # ── 读所有 <tag>-predictions.txt，建 (pep, tag) -> MSi ────────────────────────
    score_dict = {}                  # (pep_upper, tag) -> MSi
    pred_files = sorted(work.glob("*-predictions.txt"))
    print(f"[parse] 发现 {len(pred_files)} 个 predictions 文件")
    for pf in pred_files:
        tag = pf.name[:-len("-predictions.txt")]  # <tag>-predictions.txt
        sc = parse_predictions(pf, tag)
        for pep, v in sc.items():
            score_dict[(pep, tag)] = v
        if sc:
            smin, smax = min(sc.values()), max(sc.values())
            print(f"[parse]   {tag:<8} {len(sc):>4} MSi 分 | range [{smin:.4f}, {smax:.4f}]")
        else:
            print(f"[parse]   {tag:<8} 0 MSi 分（空输出）")

    # ── 读 bb_map，回贴 MT/WT，写合表 ────────────────────────────────────────────
    def lookup(pep, tag):
        """pep 为 '' 或无分 → ''（NaN）；否则 round 6 位字符串。无翻转。"""
        if not pep:
            return ""
        v = score_dict.get((pep, tag))
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""
        return str(round(v, 6))

    n_mt = n_wt = n_mt_nan = n_wt_nan = 0
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(bb_map_csv, newline="", encoding="utf-8") as fin, \
            open(out, "w", newline="", encoding="utf-8") as fout:
        w = csv.DictWriter(fout, fieldnames=["bb_idx", "MT_HLAthena", "WT_HLAthena"])
        w.writeheader()
        for r in csv.DictReader(fin):
            tag = r["tag"]
            mt_s = lookup(r["mt_pep"], tag)
            wt_s = lookup(r["wt_pep"], tag)
            n_mt += mt_s != ""
            n_wt += wt_s != ""
            n_mt_nan += mt_s == ""
            n_wt_nan += wt_s == ""
            w.writerow({"bb_idx": r["bb_idx"], "MT_HLAthena": mt_s, "WT_HLAthena": wt_s})

    print(f"\n[parse] 写 {out}")
    print(f"[parse]   MT_HLAthena: {n_mt} found / {n_mt_nan} NaN")
    print(f"[parse]   WT_HLAthena: {n_wt} found / {n_wt_nan} NaN")
    print(f"[parse]   方向：MSi presentation 分越高越提呈（无翻转）")
    print(f"[parse]   ⚠️ presentation proxy，非免疫原性——下游单列，不与免疫原性工具并列。")


if __name__ == "__main__":
    main()
