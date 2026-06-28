# -*- coding: utf-8 -*-
"""
prep_hlathena_hpc.py — Phase B：把 HPC 上的 backbone_101102.csv 拆成 HLAthena 的
per-allele 输入肽文件 + bb_idx 回填映射（供 run_hlathena_hpc.sh 逐 allele 调 sif）。

⚠️⚠️ HLAthena 预测 MHC-I **提呈（presentation）不是免疫原性**（Sarkizova 2020
Nat Biotech）。进 benchmark 只作 presentation baseline proxy，**单列 presentation 分**，
绝不与免疫原性工具 apples-to-apples 并列。方向照原：MSi 越高越可能被 HLA-I 提呈。

只读传入的 backbone csv（HPC 唯一订正源 $ROOT/phaseB/backbone_101102.csv）。产出：
  <work>/peps/<tag>.txt        —— 每个 covered allele 的去重肽列表（LF，无表头，同 SMOKE 格式）
  <work>/alleles_manifest.csv  —— tag,original_hla,covered,n_pep,pep_file（sh 据此只跑 covered）
  <work>/bb_map.csv            —— bb_idx,mt_pep,wt_pep,tag（parse 据此把 MSi 分回贴每行 MT/WT）

口径（与 scripts/phaseB/run_hlathena_101102.py 本地 docker 版严格一致）：
  - tag = HLA_Allele 去 HLA- 去 * 去 :（HLA-A*66:01 -> A6601，与原部署 --alleles A0101 同格）
  - HLAthena 仅支持 **8/9/10/11-mer**；12-14mer（本子集占比不小）→ 该肽留空（parse 出 NaN）
  - 仅标准 20 氨基酸；含非标准残基的肽 → 留空（NaN）
  - allele 覆盖：按 --models-dir 下该 allele 的 specific 模型目录/文件是否存在判定。
    有 specific 模型 → 进 manifest 跑；无 → covered=0，整组 NaN（不静默回退 pan-allele，
    避免改变原部署 allele-specific 方法学）。⚠️ 官方权威 65/95-allele 清单未在
    repo/web 确认（researcher TODO），故以本地模型文件实际存在为唯一覆盖真源。

服务: quantimmu-bench Phase B HLAthena 101/102 重推理（lever=HLAthena presentation proxy）。
⚠️ 本脚本只写不跑（coder 红线）；sif/解析由主线在 HPC 执行。py_compile 已过。
"""
import argparse
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

STD_AA = set("ACDEFGHIKLMNPQRSTVWY")          # HLAthena 仅接受标准 20 种氨基酸
HLATHENA_LENGTHS = frozenset({8, 9, 10, 11})  # 官方支持长度；其余 → NaN

# Phase B 7 个订正 allele（仅记录用，实际覆盖由 --models-dir 运行时判定）。
CORRECTED_ALLELES = (
    "HLA-A*02:01", "HLA-A*66:01", "HLA-B*35:03", "HLA-B*38:01",
    "HLA-B*40:01", "HLA-B*57:01", "HLA-C*06:02",
)


def hla_to_tag(h):
    """HLA-A*66:01 → A6601（去 HLA- 去 * 去 :），与原部署 --alleles A0101 同格。"""
    return h.replace("HLA-", "").replace("*", "").replace(":", "").strip()


def is_clean_pep(p):
    return bool(p) and all(c in STD_AA for c in p)


def has_specific_model(models_dir, tag):
    """该 allele 是否有 specific 模型（目录或文件含 tag）。覆盖判定唯一真源——
    不臆造 65-allele 清单，按本地模型文件实际存在判定，无 specific → NaN。"""
    md = Path(models_dir)
    if not md.exists():
        return False
    if (md / tag).exists():
        return True
    try:
        return any(tag in p.name for p in md.iterdir())
    except OSError:
        return False


def main():
    ap = argparse.ArgumentParser(description="Phase B HLAthena prep（per-allele 肽文件 + bb 映射）")
    ap.add_argument("--backbone", required=True, help="HPC backbone_101102.csv 绝对路径（只读）")
    ap.add_argument("--work", required=True, help="工作目录（写 peps/ + manifest + bb_map）")
    ap.add_argument("--models-dir", required=True,
                    help="HLAthena specific 模型目录（覆盖判定真源，host 侧，sif 内挂 /models）")
    args = ap.parse_args()

    backbone = Path(args.backbone)
    work = Path(args.work)
    peps_dir = work / "peps"
    if not backbone.exists():
        raise SystemExit(f"[FAIL] 订正源不存在: {backbone}")
    peps_dir.mkdir(parents=True, exist_ok=True)

    # ── 读 backbone，按 tag 聚合需打分的肽（MT ∪ WT，去重）+ 逐行 bb 映射 ───────────
    rows = []
    allele_peps = defaultdict(set)   # tag → {pep_upper}（仅 8-11mer 标准 AA）
    allele_original = {}             # tag → 原始 HLA 串
    bb_map = []                      # (bb_idx, mt_pep_or_blank, wt_pep_or_blank, tag)
    n_len_drop = 0
    n_aa_drop = 0

    def clean_for_score(pep):
        """返回可送 HLAthena 的大写肽，或 ''（长度/AA 不合 → NaN）。计数副作用经 nonlocal。"""
        nonlocal n_len_drop, n_aa_drop
        p = (pep or "").strip().upper()
        if not p:
            return ""
        if len(p) not in HLATHENA_LENGTHS:
            n_len_drop += 1
            return ""
        if not is_clean_pep(p):
            n_aa_drop += 1
            return ""
        return p

    with open(backbone, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
            tag = hla_to_tag(r["HLA_Allele"])
            allele_original.setdefault(tag, r["HLA_Allele"].strip())
            mt = clean_for_score(r.get("MT_Subpeptide"))
            wt = clean_for_score(r.get("WT_Subpeptide"))
            if mt:
                allele_peps[tag].add(mt)
            if wt:
                allele_peps[tag].add(wt)
            bb_map.append((str(r["bb_idx"]).strip(), mt, wt, tag))

    alleles = sorted(allele_peps.keys())
    print(f"[prep] backbone={len(rows)} 行 | 唯一 allele={len(alleles)} <- {backbone}")
    print(f"[prep] 丢弃(置NaN)：长度∉8-11mer={n_len_drop} | 非标准氨基酸={n_aa_drop}")

    # ── allele 覆盖：按 specific 模型是否存在判定（不臆造 65 列表）────────────────────
    covered = {}
    print(f"[prep] HLAthena allele-specific 模型覆盖（--models-dir={args.models_dir}）：")
    for tag in alleles:
        ok = has_specific_model(args.models_dir, tag)
        covered[tag] = ok
        print(f"[prep]   {tag:<8} ({allele_original.get(tag, '?'):<12}) "
              f"specific模型={'OK在' if ok else 'X缺->NaN'}  "
              f"{len(allele_peps[tag])} uniq pep（8-11mer）")
    n_missing = sum(1 for v in covered.values() if not v)
    if n_missing:
        print(f"[prep] ⚠️ {n_missing} 个 allele 无 specific 模型 → 整组 NaN（不静默回退 pan）。")
        print(f"[prep]    ⚠️ 官方权威 allele 清单未在 repo/web 确认（researcher TODO）；"
              f"覆盖以 --models-dir 实际模型文件为准。")

    # ── 写 per-allele 肽文件（仅 covered）+ manifest ───────────────────────────────
    with open(work / "alleles_manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tag", "original_hla", "covered", "n_pep", "pep_file"])
        for tag in alleles:
            pep_file = peps_dir / f"{tag}.txt"
            if covered[tag]:
                pep_list = sorted(allele_peps[tag])
                pep_file.write_text("\n".join(pep_list) + "\n", encoding="utf-8")  # LF，无表头
            w.writerow([tag, allele_original.get(tag, ""), int(covered[tag]),
                        len(allele_peps[tag]), str(pep_file)])

    # ── 写 bb_map（parse 据此回贴）────────────────────────────────────────────────
    with open(work / "bb_map.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["bb_idx", "mt_pep", "wt_pep", "tag"])
        for bb, mt, wt, tag in bb_map:
            w.writerow([bb, mt, wt, tag])

    n_run = sum(1 for v in covered.values() if v)
    print(f"[prep] 写 {work / 'alleles_manifest.csv'}（{n_run} covered / {len(alleles)} 总 allele）")
    print(f"[prep] 写 {work / 'bb_map.csv'}（{len(bb_map)} 行）")
    print(f"[prep] per-allele 肽文件 -> {peps_dir}/<tag>.txt（仅 covered）")
    # 自校验：前 3 个 covered allele
    shown = 0
    for tag in alleles:
        if covered[tag] and shown < 3:
            print(f"        {tag}: {len(allele_peps[tag])} pep, e.g. {sorted(allele_peps[tag])[:2]}")
            shown += 1


if __name__ == "__main__":
    main()
