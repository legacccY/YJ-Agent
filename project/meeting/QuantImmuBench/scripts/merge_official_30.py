#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_official_30.py
服务: quantimmu-bench / Phase 0 收口 (主窗 W0 orchestrator 备料)

合并 30 工具的 official 补跑分 + 87 复用肽旧分 -> 子肽×HLA 长表
  scripts/out/merged_all_tools_30_official.csv  (p0e 的输入)

================== 输入 ==================
  scripts/out_official/master_backbone_official.csv   (43 补跑肽 backbone, 1761 行, 含 mut_key)
  scripts/out_official/<Tool>_official.csv             (各工具补跑: bb_idx, MT_<Tool>[, WT_<Tool>])
  scripts/out/merged_all_tools_29tools.xlsx            (旧分: 183 mut_key × 30 工具列, 子肽×HLA)
  data/frozen/REUSE_DECISION.csv                       (reuse=87 / rerun_full=29 / rerun_partial=14)
  data/frozen/patient_hla.csv                          (新 HLA 集真源, 用于 partial 等位过滤)

================== 合并语义 (run-once, 零造数) ==================
  reuse (87 肽)        : 全取旧 merged 行 (所有工具旧分)。
  rerun_full (29 肽)   : 全取新 backbone+official 行 (旧无此肽或全变)。
  rerun_partial (14 肽, P104): backbone 只含新等位 A*30:01 行。
     -> 旧 5 个不变等位行 (HLA ∈ 新 patient_hla 集) 复用旧分;
        旧已换掉的 A*03:01 行丢弃 (等位不再属该患者);
        + 新 A*30:01 行取 official。
     用 patient_hla.csv 新 HLA 集做过滤 = 不变等位真源。

================== 工具名 canonical 化 (防 p0e 拆成重复工具) ==================
  旧列名与新 official 命名漂移 (netmhcpan_ba vs netMHCpan_BA / IMPROVE_mean_prediction_rf
  vs IMPROVE / Andy90 vs andy90 / BigMHC 双头 ...) -> 统一映射到 30-roster canonical 名。
  未识别的旧列 (MixMHCpred=PRIME 依赖 / *_aux) 标 __AUX_ 前缀保留但不计入 roster, 报告里列出。

================== 校验门 (fail-loud, 不 silent) ==================
  [M1] 最终 distinct mut_key == 130 (87+29+14)
  [M2] 每肽 (mut_key) 至少 1 工具有 MT 分 -> 否则报错停 (防整肽行空)
  [M3] partial 肽不含旧换出等位 (A*03:01); 含新 A*30:01
  [M4] 无重复 canonical 工具列 (映射后唯一)
  [M5] 覆盖报告: 每 canonical 工具 在 130 肽 / 43 补跑肽 的覆盖数 + distinct 等位
        (整列空=PENDING 待该窗补跑, 不报错; 但打印醒目)

================== 跑法 ==================
  python scripts/merge_official_30.py
  python scripts/merge_official_30.py --strict-roster   # 缺任一 roster 工具即报错 (收口终检用)
"""

import sys
import argparse
import glob
import re
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
OUT_OFFICIAL = ROOT / "scripts" / "out_official"
BACKBONE = OUT_OFFICIAL / "master_backbone_official.csv"
OLD_MERGED = ROOT / "scripts" / "out" / "merged_all_tools_29tools.xlsx"
REUSE_DEC = ROOT / "data" / "frozen" / "REUSE_DECISION.csv"
PATIENT_HLA = ROOT / "data" / "frozen" / "patient_hla.csv"
OUT_CSV = ROOT / "scripts" / "out" / "merged_all_tools_30_official.csv"

# ── 30-roster canonical 名 (真源 = TOOL_RERUN_STATUS.md) ──────────────────
# canonical -> 别名集 (全小写匹配, 含旧列与新 official 可能命名)
ROSTER = {
    "IEDB_Calis":     {"iedb_calis"},
    "ImmuneApp":      {"immuneapp"},
    "PRIME":          {"prime"},
    "DeepImmuno":     {"deepimmuno"},
    "PredIG":         {"predig"},
    "IMPROVE":        {"improve", "improve_mean_prediction_rf"},
    "pTuneos":        {"ptuneos"},
    "NeoTImmuML":     {"neotimmuml"},
    "deepHLApan":     {"deephlapan"},
    "BigMHC_IM":      {"bigmhc_im", "bigmhc"},       # 旧 MT_BigMHC = IM 头
    "CNNeo":          {"cnneo"},
    "Repitope":       {"repitope"},
    "TSCAPE":         {"tscape"},
    "NetTepi":        {"nettepi"},
    "ICERFIRE":       {"icerfire"},
    "MUNIS":          {"munis"},
    "andy90":         {"andy90"},
    "ImmuGenX":       {"immugenx"},
    "DeepNetBim":     {"deepnetbim"},
    "NeoaPred":       {"neoapred"},
    "netMHCpan_BA":   {"netmhcpan_ba"},
    "netMHCpan_EL":   {"netmhcpan_el"},
    "netMHCstabpan":  {"netmhcstabpan", "stabpan"},
    "MHCflurry":      {"mhcflurry", "mhcflurry_presentation"},  # presentation 头为主
    "MHCnuggets":     {"mhcnuggets"},
    "MHCseqNet":      {"mhcseqnet"},
    "TransHLA":       {"transhla"},
    "HLAthena":       {"hlathena"},
    "NeoaG":          {"neoag"},
    "Seq2Neo":        {"seq2neo"},   # bonus, 阻塞 netCTLpan, 多半 PENDING
}
# 别名 -> canonical (反查)
ALIAS2CANON = {}
for canon, aliases in ROSTER.items():
    ALIAS2CANON[canon.lower()] = canon
    for a in aliases:
        ALIAS2CANON[a] = canon

# 元数据/非工具 MT_* 列 (不当工具分)
META_MT = {"MT_FullPeptide", "MT_Subpeptide", "MT_NOAH", "MT_NetCleave",
           "MT_Stab_peptide", "MT_TCR_contact"}
# 长表对齐的元数据列 (尽量保留)
META_KEEP = ["bb_idx", "Dataset", "Patient_ID", "Peptide_ID", "Gene_Name",
             "Mutation", "MT_FullPeptide", "WT_FullPeptide", "Peptide_Length",
             "Elispot", "Window_Size", "Position", "MT_Subpeptide",
             "WT_Subpeptide", "HLA_Allele", "Ref_UniProt_ID",
             "Peptide_Position", "mut_key"]

P104_DROPPED_ALLELE = "HLA-A*03:01"   # partial 换出等位 (核校用)
P104_NEW_ALLELE = "HLA-A*30:01"


def canon_of(raw_col):
    """MT_xxx / WT_xxx 原始列名 -> (prefix, canonical工具名 或 None)。"""
    m = re.match(r"^(MT|WT)_(.+)$", raw_col)
    if not m:
        return None, None
    prefix, body = m.group(1), m.group(2)
    key = body.lower()
    if key in ALIAS2CANON:
        return prefix, ALIAS2CANON[key]
    # 子串兜底 (如 improve_mean_prediction_rf 已在别名; 其余尝试前缀匹配)
    for alias, canon in ALIAS2CANON.items():
        if key == alias:
            return prefix, canon
    return prefix, None   # 未识别工具列


def build_new_long():
    """43 补跑肽: backbone + 各 <Tool>_official.csv join bb_idx -> 长表 (canonical 列)。"""
    if not BACKBONE.exists():
        raise SystemExit(f"[ERR] backbone 不存在: {BACKBONE}")
    bb = pd.read_csv(BACKBONE)
    assert "bb_idx" in bb.columns and "mut_key" in bb.columns
    print(f"[new] backbone {bb.shape}, distinct mut_key={bb['mut_key'].nunique()}")

    found, pending_files = [], []
    for f in sorted(glob.glob(str(OUT_OFFICIAL / "*_official.csv"))):
        name = Path(f).name
        if name == "master_backbone_official.csv" or name.endswith("_input.csv") \
           or "_input_" in name or name.endswith("_map.csv"):
            continue
        tool_raw = name[:-len("_official.csv")]
        key = tool_raw.lower()
        canon = ALIAS2CANON.get(key)
        if canon is None:
            print(f"[new][WARN] official 文件工具名未识别, 跳过: {name} (key={key})")
            continue
        t = pd.read_csv(f)
        if "bb_idx" not in t.columns:
            print(f"[new][WARN] {name} 无 bb_idx, 跳过")
            continue
        ren = {}
        for c in t.columns:
            if c == "bb_idx":
                continue
            pfx, cc = canon_of(c)
            if pfx and cc == canon:
                ren[c] = f"{pfx}_{canon}"
        t = t[["bb_idx"] + list(ren.keys())].rename(columns=ren)
        bb = bb.merge(t, on="bb_idx", how="left")
        found.append(canon)
        print(f"[new] +{canon:16s} from {name}  cols={list(ren.values())}")
    print(f"[new] 已并入补跑工具 {len(found)}: {sorted(found)}")
    return bb, found


def canonicalize_old(old):
    """旧 merged 列 -> canonical; 重复 canonical 合并 (优先非空), 未识别标 __AUX_。"""
    old = old.copy()
    if "mut_key" not in old.columns:
        old["mut_key"] = (old["Patient_ID"].astype(str) + "|"
                          + old["Peptide_ID"].astype(str))
    # 收集每 (prefix,canon) 的源列
    groups = {}   # (prefix,canon) -> [cols]
    aux_cols = []
    for c in old.columns:
        if not (c.startswith("MT_") or c.startswith("WT_")):
            continue
        if c in META_MT or c in META_KEEP:   # 元数据 (含 WT_FullPeptide/Subpeptide) 不当工具/AUX
            continue
        pfx, canon = canon_of(c)
        if canon is None:
            aux_cols.append(c)
            continue
        groups.setdefault((pfx, canon), []).append(c)

    out_cols = {}
    for (pfx, canon), cols in groups.items():
        tgt = f"{pfx}_{canon}"
        if len(cols) == 1:
            out_cols[tgt] = pd.to_numeric(old[cols[0]], errors="coerce")
        else:
            # 多列映同 canonical (如 BigMHC + BigMHC_EL 都映 BigMHC_IM? 不会;
            # 但 mhcflurry_presentation 唯一别名). 优先第一非空, 其余 coalesce。
            s = pd.to_numeric(old[cols[0]], errors="coerce")
            for extra in cols[1:]:
                s = s.fillna(pd.to_numeric(old[extra], errors="coerce"))
            out_cols[tgt] = s
            print(f"[old][coalesce] {cols} -> {tgt}")
    # aux 保留
    for c in aux_cols:
        out_cols[f"__AUX_{c}"] = old[c]
    if aux_cols:
        print(f"[old][AUX] 未计入 roster 的旧列 ({len(aux_cols)}): {aux_cols}")

    meta = [c for c in META_KEEP if c in old.columns]
    res = old[meta].copy()
    for k, v in out_cols.items():
        res[k] = v.values
    return res, aux_cols


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict-roster", action="store_true",
                    help="缺任一 roster 工具 (整列空) 即报错 (收口终检)")
    args = ap.parse_args()

    for p in (OLD_MERGED, REUSE_DEC, PATIENT_HLA):
        if not p.exists():
            raise SystemExit(f"[ERR] 依赖缺失: {p}")

    dec = pd.read_csv(REUSE_DEC)
    reuse_keys = set(dec[dec.status == "reuse"]["mut_key"])
    full_keys = set(dec[dec.status == "rerun_full"]["mut_key"])
    partial_keys = set(dec[dec.status == "rerun_partial"]["mut_key"])
    print(f"[dec] reuse={len(reuse_keys)} full={len(full_keys)} partial={len(partial_keys)}")
    assert len(reuse_keys) + len(full_keys) + len(partial_keys) == 130

    # 新 HLA 集 (per patient) 真源
    ph = pd.read_csv(PATIENT_HLA)
    valid_hla = {pid: set(g["hla_allele_std"])
                 for pid, g in ph.groupby("Patient_ID")}

    # ── 新长表 (43 补跑肽) ─────────────────────────────────────────────
    new_long, found_new = build_new_long()
    new_long["Patient_ID"] = new_long["Patient_ID"].astype(int)

    # ── 旧长表 canonical ───────────────────────────────────────────────
    print(f"[old] 读 {OLD_MERGED.name} ...")
    old = pd.read_excel(OLD_MERGED)
    old_c, aux_cols = canonicalize_old(old)
    old_c["Patient_ID"] = old_c["Patient_ID"].astype(int)
    print(f"[old] canonical 后 {old_c.shape}")

    # ── 三段切分 ───────────────────────────────────────────────────────
    # reuse: 全取旧
    seg_reuse = old_c[old_c["mut_key"].isin(reuse_keys)].copy()
    # full: 全取新
    seg_full = new_long[new_long["mut_key"].isin(full_keys)].copy()
    # partial: 旧不变等位 (HLA ∈ 新集) + 新等位行
    old_partial = old_c[old_c["mut_key"].isin(partial_keys)].copy()
    keep_mask = old_partial.apply(
        lambda r: r["HLA_Allele"] in valid_hla.get(int(r["Patient_ID"]), set()),
        axis=1)
    seg_partial_old = old_partial[keep_mask].copy()
    seg_partial_new = new_long[new_long["mut_key"].isin(partial_keys)].copy()

    print(f"[seg] reuse 行={len(seg_reuse)} | full 行={len(seg_full)} | "
          f"partial 旧保留={len(seg_partial_old)} (丢弃 {len(old_partial)-len(seg_partial_old)}) "
          f"| partial 新={len(seg_partial_new)}")

    merged = pd.concat([seg_reuse, seg_full, seg_partial_old, seg_partial_new],
                       ignore_index=True, sort=False)

    # canonical 工具列排序 (MT_ 在前 WT_ 紧随)
    tool_cols = [c for c in merged.columns
                 if (c.startswith("MT_") or c.startswith("WT_"))
                 and not c.startswith("__AUX_") and c not in META_MT]
    meta_cols = [c for c in META_KEEP if c in merged.columns]
    aux_out = [c for c in merged.columns if c.startswith("__AUX_")]
    merged = merged[meta_cols + sorted(tool_cols) + aux_out]

    # ── 校验门 ─────────────────────────────────────────────────────────
    nk = merged["mut_key"].nunique()
    assert nk == 130, f"[M1] FAIL: distinct mut_key={nk} != 130"
    print(f"[M1] PASS: distinct mut_key == 130")

    mt_cols = [c for c in tool_cols if c.startswith("MT_")]
    per_pep_any = merged.groupby("mut_key")[mt_cols].apply(
        lambda g: g.notna().any().any())
    empty_peps = per_pep_any[~per_pep_any].index.tolist()
    if empty_peps:
        raise SystemExit(f"[M2] FAIL: {len(empty_peps)} 肽全工具 MT 皆空: {empty_peps}")
    print(f"[M2] PASS: 每肽至少 1 工具有 MT 分")

    # M3 partial 等位
    pm = merged[merged["mut_key"].isin(partial_keys)]
    if P104_DROPPED_ALLELE in set(pm["HLA_Allele"]):
        raise SystemExit(f"[M3] FAIL: partial 肽仍含换出等位 {P104_DROPPED_ALLELE}")
    if P104_NEW_ALLELE not in set(pm["HLA_Allele"]):
        raise SystemExit(f"[M3] FAIL: partial 肽缺新等位 {P104_NEW_ALLELE}")
    print(f"[M3] PASS: partial 肽无 {P104_DROPPED_ALLELE}, 含 {P104_NEW_ALLELE}")

    # M4 无重复 canonical
    dup = [c for c in tool_cols if tool_cols.count(c) > 1]
    assert not dup, f"[M4] FAIL: 重复 canonical 列 {set(dup)}"
    print(f"[M4] PASS: 无重复 canonical 工具列")

    # ── M5 覆盖报告 ────────────────────────────────────────────────────
    rerun_keys = full_keys | partial_keys   # 43
    print(f"\n[M5] === canonical 工具覆盖报告 (130 肽 / {len(rerun_keys)} 补跑肽) ===")
    pending, partial_cov, full_cov = [], [], []
    for canon in ROSTER:
        mc = f"MT_{canon}"
        if mc not in merged.columns:
            pending.append(canon)
            print(f"   {canon:16s} : ⬜ 缺列 (无旧分无新分, PENDING)")
            continue
        s = merged[[mc, "mut_key", "HLA_Allele"]].copy()
        s[mc] = pd.to_numeric(s[mc], errors="coerce")
        peps_cov = s[s[mc].notna()]["mut_key"].nunique()
        rerun_cov = s[s[mc].notna() & s["mut_key"].isin(rerun_keys)]["mut_key"].nunique()
        n_allele = s[s[mc].notna()]["HLA_Allele"].nunique()
        tag = "✅" if peps_cov == 130 else ("🟡" if peps_cov > 0 else "⬜")
        if peps_cov == 0:
            pending.append(canon)
        elif peps_cov < 130 or rerun_cov < len(rerun_keys):
            partial_cov.append(canon)
        else:
            full_cov.append(canon)
        print(f"   {canon:16s} : {tag} {peps_cov:3d}/130 肽 | {rerun_cov:2d}/{len(rerun_keys)} 补跑 | {n_allele} 等位")
    print(f"\n[M5] 全覆盖(130) {len(full_cov)} | 部分 {len(partial_cov)} | PENDING {len(pending)}")
    if partial_cov:
        print(f"     🟡 部分覆盖 (补跑未齐): {partial_cov}")
    if pending:
        print(f"     ⬜ PENDING (待补跑): {pending}")
    if aux_cols:
        print(f"\n[M5] __AUX_ 旧列 (不计 roster, 留档): {aux_cols}")

    if args.strict_roster:
        miss = pending + partial_cov
        if miss:
            raise SystemExit(f"[strict] FAIL: roster 工具未达 130 全覆盖: {miss}")
        print(f"[strict] PASS: 30-roster 工具全 130 覆盖")

    # ── 写出 ───────────────────────────────────────────────────────────
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUT_CSV, index=False, encoding="utf-8")
    print(f"\n[saved] {OUT_CSV}  shape={merged.shape}")
    print(f"[info] 工具列 {len(tool_cols)} (canonical) + AUX {len(aux_out)}")
    print("[DONE] merge_official_30 完成")


if __name__ == "__main__":
    main()
