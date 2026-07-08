#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_coverage_matrix.py
服务: quantimmu-bench / 切肽口径大改 §改动②/③ S6 收口 (输出侧完整性命门)

用户命门「不能漏」的输出侧检查: 改动② 完整窗集灌全 30 工具后, 对**每个应打分的格子**
(窗 subpep_seq × HLA × side{MT,WT} × 30 工具 roster) 判有没有分。任何真漏 (unknown) 红标。

================== 输入 (只读) ==================
  data/frozen/newcut_subpep_hla.NEW.csv        完整窗集 (每行=一个 窗×HLA×side 格子)
      列 mut_key,Patient_ID,Peptide_ID,Vaccine_Peptide,subpep_seq,subpep_pos,
         window_size,hla_allele_std,side{MT,WT},source{SLP,MANE},consistency_flag
  scripts/out_rerun_official/<Tool>_official.csv  各切片窗跑完落这 (bb_idx, MT_<Tool>[, WT_<Tool>])
  scripts/out_rerun/master_backbone_official.csv  bb_idx -> (MT_Subpeptide,WT_Subpeptide,HLA_Allele)
      (build_rerun_inputs 产; 用来把 bb_idx-keyed 分数映回 (subpep_seq,HLA))

  roster 30 工具从 merge_official_30.ROSTER 取 (不硬编码)。

================== missing 原因分类 (优先级) ==================
  tool_not_run     : 整个工具文件缺 (切片没跑完/漏) 或该 side 零分 (空输出)
  mt_only_tool     : WT side 但工具无 WT_<Tool> 列 (如 pTuneos/NeoaPred/NeoaG 仅 MT, 结构性)
  END_TRUNCATED    : 该格子 consistency_flag != OK (窗本身<Lmer; newcut 一般无此行, 保留)
  len_filter       : 子肽长度不在该工具已打分的长度集 (DeepImmuno 9/10, DeepNetBim/NeoaPred 9,
                     HLAthena 8-11; 文档已载=documented, 否则从工具自身产出经验推=empirical)
  hla_unsupported  : 该 HLA 不在该工具已打分的等位集 (NetTepi 仅 6/26, HLAthena 无 B*27:06;
                     documented / empirical 同上)
  unknown          : 工具在别处打过【同长度+同HLA】的分, 却漏了这个格子 -> **真漏**, 红标 (命门)

  reason_source: structural(文件缺/无WT列) / documented(TOOL_RERUN_STATUS.md 明载) /
                 empirical(工具自身产出经验推) / REAL_GAP(unknown)

================== 输出 ==================
  data/frozen/coverage_matrix.NEW.csv   逐 (mut_key,subpep_seq,HLA,side,tool) -> scored/missing
  data/frozen/coverage_gaps.NEW.csv     所有 missing 格子 + reason + reason_source
  + print: 每工具覆盖率% + 每类 missing 计数; 红标任何 unknown

================== 跑法 (不在本脚本内跑; 交主线) ==================
  python scripts/build_coverage_matrix.py
  (切片没跑完 -> 大量 tool_not_run; 跑完 -> 只剩 hla_unsupported/len_filter/END_TRUNCATED, unknown=0)
"""

import sys
import re
import glob
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "scripts"
FROZEN = ROOT / "data" / "frozen"

sys.path.insert(0, str(HERE))
from merge_official_30 import ROSTER, ALIAS2CANON, canon_of  # noqa: E402  (roster 真源, 不硬编码)

NEWCUT = FROZEN / "newcut_subpep_hla.NEW.csv"
DEFAULT_SCORED = HERE / "out_rerun_official"
DEFAULT_BACKBONE = HERE / "out_rerun" / "master_backbone_official.csv"
OUT_MATRIX = FROZEN / "coverage_matrix.NEW.csv"
OUT_GAPS = FROZEN / "coverage_gaps.NEW.csv"

# ── 文档已载能力 (TOOL_RERUN_STATUS.md; 仅记明载的, 其余靠 empirical, 不臆造) ──────
DOC_LEN = {                        # 工具 -> 支持的子肽长度集
    "DeepImmuno": {9, 10},         # tool4: 9/10mer
    "DeepNetBim": {9},             # tool20: 9mer ONLY
    "NeoaPred": {9},               # tool21: 严格 9mer
    "HLAthena": {8, 9, 10, 11},    # tool29: 单长度 8-11mer
}
DOC_HLA_UNSUP = {                  # 工具 -> 已知不支持的具体等位
    "HLAthena": {"HLA-B*27:06"},   # tool29: B*27:06 无 ecdf -> 诚实 NaN
}
# NetTepi 仅 6/26 等位但文档未列具体值 -> 交给 empirical 推 (不硬编造具体等位)


def load_backbone(path):
    """bb_idx -> (MT_Subpeptide, WT_Subpeptide, HLA_Allele)。"""
    bb = pd.read_csv(path)
    need = ["bb_idx", "MT_Subpeptide", "WT_Subpeptide", "HLA_Allele"]
    for c in need:
        if c not in bb.columns:
            raise SystemExit(f"[ERR] backbone 缺列 {c}: {path}")
    return bb[need].copy()


_SIDE_RE = re.compile(r"^(MT|WT)_(.+)$")


def cols_for(all_cols, canon, prefix):
    """
    该 official 文件里属于 canon 的 prefix(MT/WT) 打分列。
    canon_of 精确别名 (MHCflurry_presentation) + body 以别名开头兜底
    (deepHLApan_bind/_immuno、MHCflurry_affinity_neg、ImmuGenX_Stability 等多列/带后缀头)。
    canon_of 单列硬匹配对这些多列工具返回 None -> 会误报 0 scored (命门 false-negative), 故加兜底。
    只对本文件已知 canon 匹配, 不跨工具 (文件即该工具产出), 无污染。
    """
    aliases = {canon.lower()} | {a.lower() for a in ROSTER.get(canon, set())}
    out = []
    for c in all_cols:
        mm = _SIDE_RE.match(c)
        if not mm or mm.group(1) != prefix:
            continue
        _, cc = canon_of(c)                 # 精确别名匹配 (如 mhcflurry_presentation)
        if cc == canon:
            out.append(c)
            continue
        body = mm.group(2).lower()          # 多头/后缀兜底 (body 以别名+"_" 开头)
        if any(body == a or body.startswith(a + "_") for a in aliases):
            out.append(c)
    return out


def index_scored(scored_dir, bb):
    """
    各 <Tool>_official.csv join backbone -> 每 canonical 工具的已打分能力:
      cells_mt/cells_wt = set('subpep||HLA') 已有非 NaN 分的格子
      hla_mt/hla_wt = 已打分等位集; len_mt/len_wt = 已打分子肽长度集
      has_wt = 有 WT_<Tool> 列
    返回 cap[canon] = {...}; 无文件的工具不在 cap (= tool_not_run)。
    """
    cap = {}
    for f in sorted(glob.glob(str(scored_dir / "*_official.csv"))):
        name = Path(f).name
        if name == "master_backbone_official.csv" or name.endswith("_input.csv") \
           or "_input_" in name or name.endswith("_map.csv"):
            continue
        tool_raw = name[:-len("_official.csv")]
        canon = ALIAS2CANON.get(tool_raw.lower())
        if canon is None:
            print(f"[WARN] official 文件工具名未识别, 跳过: {name}")
            continue
        t = pd.read_csv(f)
        if "bb_idx" not in t.columns:
            print(f"[WARN] {name} 无 bb_idx, 跳过")
            continue
        m = t.merge(bb, on="bb_idx", how="left")
        # 多列工具修: 找该文件里属于 canon 的所有 MT_*/WT_* 打分列 (canon_of 精确 + 别名前缀兜底)。
        # canon_of 单列对 deepHLApan_bind/_immuno 等返回 None -> 会误报 0 scored, cols_for 兜底修正。
        mt_cols = cols_for(t.columns, canon, "MT")
        wt_cols = cols_for(t.columns, canon, "WT")
        e = {"file": name, "has_mt": bool(mt_cols), "has_wt": bool(wt_cols)}
        for side, seqcol, tcols in (("mt", "MT_Subpeptide", mt_cols),
                                    ("wt", "WT_Subpeptide", wt_cols)):
            if tcols:
                # 任一匹配列非 NaN 即该窗该 side scored
                sc = m[m[tcols].notna().any(axis=1)]
                seq = sc[seqcol].astype(str)
                hla = sc["HLA_Allele"].astype(str)
                e[f"cells_{side}"] = set(seq + "||" + hla)
                e[f"hla_{side}"] = set(hla)
                e[f"len_{side}"] = set(seq.str.len())
            else:
                e[f"cells_{side}"], e[f"hla_{side}"], e[f"len_{side}"] = set(), set(), set()
        cap[canon] = e
    return cap


def classify_tool(nc, canon, e):
    """
    对单工具 canon 在整个 newcut(nc) 上判 scored/missing + reason。向量化。
    返回 (status: ndarray[str], reason: ndarray[str], rsrc: ndarray[str])。
    """
    n = len(nc)
    side = nc["side"].values
    key = nc["_key"].values
    hla = nc["hla_allele_std"].values
    slen = nc["_len"].values
    flag = nc["consistency_flag"].values
    is_mt = (side == "MT")
    is_wt = (side == "WT")

    status = np.full(n, "missing", dtype=object)
    reason = np.full(n, "", dtype=object)
    rsrc = np.full(n, "", dtype=object)

    if e is None:                      # 整个工具文件缺 -> 全 tool_not_run
        reason[:] = "tool_not_run"
        rsrc[:] = "structural"
        return status, reason, rsrc

    # scored 判定 (按 side 查各自 cells 集)
    scored = np.zeros(n, dtype=bool)
    if is_mt.any():
        scored[is_mt] = np.isin(key[is_mt], list(e["cells_mt"]))
    if is_wt.any():
        scored[is_wt] = np.isin(key[is_wt], list(e["cells_wt"]))
    status[scored] = "scored"

    miss = ~scored
    assigned = scored.copy()           # scored 行不用 reason

    def _assign(cond, r, s):
        nonlocal assigned
        c = miss & (~assigned) & cond
        reason[c] = r
        rsrc[c] = s
        assigned |= c

    # 1) WT side 但无 WT 列 -> mt_only_tool (结构性)
    if not e["has_wt"]:
        _assign(is_wt, "mt_only_tool", "structural")
    # 2) side 有列但该 side 零分 (空输出) -> tool_not_run
    if len(e["cells_mt"]) == 0:
        _assign(is_mt, "tool_not_run", "structural")
    if e["has_wt"] and len(e["cells_wt"]) == 0:
        _assign(is_wt, "tool_not_run", "structural")
    # 3) 窗本身截断 (consistency_flag != OK)
    _assign(flag != "OK", "END_TRUNCATED", "structural")
    # 4) 长度过滤: 长度不在工具已打分长度集 (按 side)
    len_ok = np.zeros(n, dtype=bool)
    if is_mt.any():
        len_ok[is_mt] = np.isin(slen[is_mt], list(e["len_mt"]))
    if is_wt.any():
        len_ok[is_wt] = np.isin(slen[is_wt], list(e["len_wt"]))
    len_src = "documented" if canon in DOC_LEN else "empirical"
    _assign(~len_ok, "len_filter", len_src)
    # 5) HLA 不支持: HLA 不在工具已打分等位集 (按 side)
    hla_ok = np.zeros(n, dtype=bool)
    if is_mt.any():
        hla_ok[is_mt] = np.isin(hla[is_mt], list(e["hla_mt"]))
    if is_wt.any():
        hla_ok[is_wt] = np.isin(hla[is_wt], list(e["hla_wt"]))
    # documented: 该 HLA 在文档明载不支持集
    doc_unsup = DOC_HLA_UNSUP.get(canon, set())
    hla_doc = np.isin(hla, list(doc_unsup)) if doc_unsup else np.zeros(n, dtype=bool)
    _assign(hla_doc, "hla_unsupported", "documented")
    _assign(~hla_ok, "hla_unsupported", "empirical")
    # 6) 剩余 missing -> unknown (工具打过同长度+同HLA却漏此格 = 真漏)
    _assign(np.ones(n, dtype=bool), "unknown", "REAL_GAP")

    return status, reason, rsrc


def main():
    ap = argparse.ArgumentParser(description="改动② 输出侧完整性覆盖矩阵 (窗×HLA×side×30工具; 不跑)")
    ap.add_argument("--scored-dir", default=str(DEFAULT_SCORED),
                    help="各工具 official csv 目录 (默认 scripts/out_rerun_official)")
    ap.add_argument("--backbone", default=str(DEFAULT_BACKBONE),
                    help="bb_idx 映射 backbone (默认 scripts/out_rerun/master_backbone_official.csv)")
    args = ap.parse_args()
    scored_dir = Path(args.scored_dir).resolve()
    backbone_path = Path(args.backbone).resolve()

    if not NEWCUT.exists():
        raise SystemExit(f"[ERR] 完整窗集缺失: {NEWCUT} (先跑 cut_from_protein.py)")

    nc = pd.read_csv(NEWCUT, dtype=str, encoding="utf-8")
    nc["subpep_seq"] = nc["subpep_seq"].astype(str)
    nc["hla_allele_std"] = nc["hla_allele_std"].astype(str)
    nc["_len"] = nc["subpep_seq"].str.len()
    nc["_key"] = nc["subpep_seq"] + "||" + nc["hla_allele_std"]
    if "consistency_flag" not in nc.columns:
        nc["consistency_flag"] = "OK"
    print(f"[info] 完整窗集: {len(nc)} 格子 (side: {nc['side'].value_counts().to_dict()})")

    roster = list(ROSTER)
    print(f"[info] roster: {len(roster)} 工具 (来自 merge_official_30.ROSTER)")

    # 载 backbone + scored (若无 backbone 但有 scored 文件 -> 无法映射, 报错)
    scored_files = [p for p in glob.glob(str(scored_dir / "*_official.csv"))
                    if Path(p).name != "master_backbone_official.csv"]
    if scored_files and not backbone_path.exists():
        raise SystemExit(f"[ERR] 有 scored 文件但缺 backbone (无法映射 bb_idx): {backbone_path}")
    if backbone_path.exists() and scored_files:
        bb = load_backbone(backbone_path)
        cap = index_scored(scored_dir, bb)
    else:
        cap = {}
        print(f"[info] scored 目录空/无 backbone -> 视全部工具未跑 (预期大量 tool_not_run): {scored_dir}")
    ran = sorted(cap.keys())
    not_run = [c for c in roster if c not in cap]
    print(f"[info] 已跑工具 {len(ran)}: {ran}")
    if not_run:
        print(f"[info] 未跑工具 {len(not_run)} (tool_not_run): {not_run}")

    # ── 逐工具分类, 拼长表 ────────────────────────────────────────────────
    base = nc[["mut_key", "subpep_seq", "hla_allele_std", "side", "source", "consistency_flag"]]
    mat_parts, gap_parts = [], []
    per_tool_summary = []
    for canon in roster:
        e = cap.get(canon)
        status, reason, rsrc = classify_tool(nc, canon, e)
        part = base.copy()
        part["tool"] = canon
        part["status"] = status
        mat_parts.append(part[["mut_key", "subpep_seq", "hla_allele_std", "side", "tool", "status"]])
        # gaps (missing 子集)
        miss = status == "missing"
        if miss.any():
            g = base[miss].copy()
            g["tool"] = canon
            g["reason"] = reason[miss]
            g["reason_source"] = rsrc[miss]
            gap_parts.append(g[["mut_key", "subpep_seq", "hla_allele_std", "side",
                                "source", "consistency_flag", "tool", "reason", "reason_source"]])
        # 汇总
        n_sc = int((status == "scored").sum())
        n_ms = int(miss.sum())
        per_tool_summary.append({
            "tool": canon, "ran": e is not None,
            "n_scored": n_sc, "n_missing": n_ms,
            "coverage_pct": round(100.0 * n_sc / len(nc), 2) if len(nc) else 0.0,
            "n_unknown": int((reason == "unknown").sum()),
        })

    matrix = pd.concat(mat_parts, ignore_index=True)
    gaps = (pd.concat(gap_parts, ignore_index=True) if gap_parts
            else pd.DataFrame(columns=["mut_key", "subpep_seq", "hla_allele_std", "side",
                                       "source", "consistency_flag", "tool", "reason", "reason_source"]))

    FROZEN.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(OUT_MATRIX, index=False, encoding="utf-8")
    gaps.to_csv(OUT_GAPS, index=False, encoding="utf-8")
    print(f"\n[saved] {OUT_MATRIX}  shape={matrix.shape} (格子×工具)")
    print(f"[saved] {OUT_GAPS}  shape={gaps.shape}")

    # ── 汇总 print ────────────────────────────────────────────────────────
    print("\n========== 每工具覆盖率 ==========")
    summ = pd.DataFrame(per_tool_summary).sort_values("coverage_pct")
    for r in summ.itertuples(index=False):
        tag = "" if r.ran else " [未跑]"
        red = f"  🔴unknown={r.n_unknown}" if r.n_unknown else ""
        print(f"   {r.tool:16s}{tag:7s} {r.coverage_pct:6.2f}%  scored={r.n_scored:6d} missing={r.n_missing:6d}{red}")

    print("\n========== missing 原因分类计数 ==========")
    if len(gaps):
        by_reason = gaps.groupby(["reason", "reason_source"]).size().reset_index(name="n")
        by_reason = by_reason.sort_values("n", ascending=False)
        for r in by_reason.itertuples(index=False):
            print(f"   {r.reason:16s} ({r.reason_source:10s}) : {r.n}")
    else:
        print("   (无 missing, 全覆盖)")

    n_unknown = int((gaps["reason"] == "unknown").sum()) if len(gaps) else 0
    print("\n========== 命门判定 ==========")
    if n_unknown == 0:
        print("[OK] unknown = 0 (无真漏; 所有 missing 均由 结构/文档/经验 边界解释)")
    else:
        print(f"[🔴 FAIL] unknown = {n_unknown} 个格子真漏 (工具打过同长度+同HLA却漏此格)! "
              f"命门, 见 coverage_gaps.NEW.csv reason==unknown, 人工核后重跑补")
        red = gaps[gaps["reason"] == "unknown"]
        print("   涉及工具:", red["tool"].value_counts().to_dict())
    print("[DONE] build_coverage_matrix 完成")


if __name__ == "__main__":
    main()
