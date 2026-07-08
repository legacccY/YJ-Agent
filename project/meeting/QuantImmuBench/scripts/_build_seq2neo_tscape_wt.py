#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_build_seq2neo_tscape_wt.py — 给 Seq2Neo + T-SCAPE 补跑 WT 侧打分（§3.1 DAI 补全）。
服务：quantimmu-bench §3.1 DAI(MT−WT)；给昨天只跑了 MT 的 Seq2Neo/TSCAPE 补 WT 侧，
      纳入 DAI 排名。复现零偏离（工具/权重/方向定向一律不改，抄 MT parse 方向）。

★ coder 不跑任何代码 —— 本脚本由主线跑。两个子命令：

  # 子命令 prep：从 merged 权威源生成 WT 工具输入（与昨天 MT 输入逐字段一致，只把肽源 MT→WT）
  python scripts/_build_seq2neo_tscape_wt.py prep

  # 子命令 merge：解析两工具 WT 输出 → 广播回 merged 每 bb_idx → 加 WT_Seq2Neo/WT_TSCAPE 两列
  python scripts/_build_seq2neo_tscape_wt.py merge

================================================================================
为何以 merged 为权威源（不用 newcut_subpep_hla_WT.for_tools.csv）：
  已 Bash 核对——两者 (WT肽×HLA) 唯一对完全一致（各 3684 对，零差集），
  但 merged 是最终广播目标（4053 bb_idx）。以 merged 取输入源 → 保证 100% 覆盖、零 join 丢失
  （coordinator 铁律「不能漏数据，以 merged 为准」）。

MT 输入格式（照抄，逐字段一致，见 scripts/out_rerun/{seq2neo,tscape}_inputs/*.csv）：
  - Seq2Neo：列 `Pep,HLA`，HLA 去星  → 例 `RDPLSEITE,HLA-A66:01`
  - T-SCAPE：列 `Allele,peptide`，HLA 带星 → 例 `HLA-A*66:01,RDPLSEITE`
  肽长过滤照抄 MT：Seq2Neo 8≤len≤11（_cnn.py encode maxlen=11）；T-SCAPE ≤20mer。
  WT 全 9mer，正常不触发过滤（触发即打印计数，诚实留 NaN，禁兜底）。

方向定向（抄 MT parse，不翻向）：
  - Seq2Neo：immunogenicity（sigmoid 0-1，越大越免疫原）→ WT_Seq2Neo = immunogenicity
  - T-SCAPE：score（0-1，越高越强）→ WT_TSCAPE = score

Windows/HPC：utf-8 显式、pathlib、纯标准库（csv），禁 scipy。零硬编码肽/HLA。
"""

import argparse
import csv
import sys
from pathlib import Path
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = Path(__file__).resolve().parent                       # scripts/
PROJ = SCRIPT_DIR.parent                                           # QuantImmuBench/
MERGED = SCRIPT_DIR / "out" / "merged_all_tools_30_rerun.csv"
S2N_DIR = SCRIPT_DIR / "out_rerun" / "seq2neo_inputs"
TSC_DIR = SCRIPT_DIR / "out_rerun" / "tscape_inputs"

# WT 工具输入（本脚本 prep 产）
S2N_IN_WT = S2N_DIR / "seq2neo_input_WT.csv"
TSC_IN_WT = TSC_DIR / "tscape_input_WT.csv"
TSC_MAP_WT = TSC_DIR / "tscape_input_map_WT.csv"

# WT 工具输出（主线跑工具后产；默认路径，可 --* 覆盖）
S2N_OUT_WT = S2N_DIR / "full_out_WT" / "cnn_results.csv"
TSC_OUT_WT = TSC_DIR / "tscape_output_WT.csv"

# merged 副本（merge 子命令写；不覆盖原 merged）
MERGED_WITH_WT2 = SCRIPT_DIR / "out" / "merged_all_tools_30_rerun.WITH_WT2.csv"

# 肽长过滤（照抄 MT prep）
S2N_MIN_LEN, S2N_MAX_LEN = 8, 11        # _cnn.py encode maxlen=11
TSC_MAX_LEN = 20                        # T-SCAPE ≤20mer

WT_PEP_COL = "WT_Subpeptide"
HLA_COL = "HLA_Allele"


# ---------- HLA 归一（与 MT prep/parse 逐字节一致）----------
def norm_hla_seq2neo(h: str) -> str:
    """benchmark HLA → Seq2Neo 格式：去星 + 去空格。HLA-A*66:01 → HLA-A66:01。
    与 prep_seq2neo_official.norm_hla_seq2neo / parse_seq2neo_official.norm_hla 一致。"""
    return str(h).strip().replace("*", "").replace(" ", "")


def norm_allele_tscape(a: str) -> str:
    """HLA-A*66:01 → A6601（去 HLA-、*、:）。与 parse_tscape_official._norm_allele 一致。"""
    a = str(a).strip()
    if a.upper().startswith("HLA-"):
        a = a[4:]
    elif a.upper().startswith("HLA"):
        a = a[3:]
    return a.replace("*", "").replace(":", "")


def clean_pep(s: str) -> str:
    s = str(s).strip()
    return "" if s.lower() in ("nan", "none", "<na>", "") else s


def is_nan(v: str) -> bool:
    return (v is None) or (str(v).strip().lower() in ("nan", "none", "<na>", ""))


# ---------- 读 merged → 唯一 (WT肽, HLA带星) 对 + bb_idx 列表 ----------
def load_merged_pairs():
    """→ (pair_to_bb, rows) : {(wt_pep, hla_star): [bb_idx,...]}, 总数据行数。"""
    pair_to_bb = defaultdict(list)
    rows = 0
    empty = 0
    with open(MERGED, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for r in rd:
            rows += 1
            pep = clean_pep(r.get(WT_PEP_COL, ""))
            hla = str(r.get(HLA_COL, "")).strip()
            bb = str(r.get("bb_idx", "")).strip()
            if not pep or not hla:
                empty += 1
                continue
            pair_to_bb[(pep, hla)].append(bb)
    return pair_to_bb, rows, empty


# ============================================================
# 子命令 prep：生成 WT 工具输入
# ============================================================
def cmd_prep(_args):
    if not MERGED.exists():
        raise FileNotFoundError(f"merged 不存在: {MERGED}")
    pair_to_bb, rows, empty = load_merged_pairs()
    pairs = list(pair_to_bb.keys())
    print(f"[prep] merged 数据行={rows}  空(WT/HLA)行={empty}  唯一(WT肽,HLA)对={len(pairs)}")

    # ---- Seq2Neo 输入（Pep,HLA；HLA 去星；肽长 8-11）----
    S2N_IN_WT.parent.mkdir(parents=True, exist_ok=True)
    s2n_skip_len = 0
    s2n_written = 0
    with open(S2N_IN_WT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Pep", "HLA"])
        for pep, hla in pairs:
            if not (S2N_MIN_LEN <= len(pep) <= S2N_MAX_LEN):
                s2n_skip_len += 1
                print(f"[prep_seq2neo] SKIP 肽长越界: {pep!r} len={len(pep)}", file=sys.stderr)
                continue
            w.writerow([pep, norm_hla_seq2neo(hla)])
            s2n_written += 1
    print(f"[prep_seq2neo] 写 {S2N_IN_WT}  唯一对={s2n_written}  肽长越界跳过={s2n_skip_len}")

    # ---- T-SCAPE 输入（Allele,peptide；HLA 带星；肽长 ≤20）----
    TSC_IN_WT.parent.mkdir(parents=True, exist_ok=True)
    tsc_skip_len = 0
    tsc_written = 0
    with open(TSC_IN_WT, "w", newline="", encoding="utf-8") as f, \
         open(TSC_MAP_WT, "w", newline="", encoding="utf-8") as fm:
        w = csv.writer(f)
        wm = csv.writer(fm)
        w.writerow(["Allele", "peptide"])
        wm.writerow(["Peptide", "Allele", "bb_idx_list"])
        for pep, hla in pairs:
            if len(pep) > TSC_MAX_LEN:
                tsc_skip_len += 1
                print(f"[prep_tscape] SKIP >{TSC_MAX_LEN}mer: {pep!r} len={len(pep)}", file=sys.stderr)
                continue
            w.writerow([hla, pep])                                  # 带星，peptide 小写列名
            wm.writerow([pep, hla, ",".join(pair_to_bb[(pep, hla)])])
            tsc_written += 1
    print(f"[prep_tscape] 写 {TSC_IN_WT}  唯一对={tsc_written}  >{TSC_MAX_LEN}mer跳过={tsc_skip_len}")
    print(f"[prep_tscape] 写 map {TSC_MAP_WT}")
    print("[prep] 完成。下一步主线跑两工具 WT（命令见脚本头/回执），再跑 merge 子命令。")


# ============================================================
# 子命令 merge：解析 WT 输出 → 广播回 merged → 加两列
# ============================================================
def load_seq2neo_wt(path: Path) -> dict:
    """cnn_results.csv → {(pep, hla去星归一): immunogenicity}。列同 MT parse。"""
    lookup = {}
    dups = 0
    n_nan = 0
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        fields = rd.fieldnames or []
        for col in ("Peptide", "HLA", "immunogenicity"):
            if col not in fields:
                raise KeyError(f"cnn_results.csv 缺列 '{col}'。实际: {fields}")
        for r in rd:
            pep = clean_pep(r.get("Peptide", ""))
            hla = norm_hla_seq2neo(r.get("HLA", ""))
            val = str(r.get("immunogenicity", "")).strip()
            if not pep or not hla:
                continue
            try:
                v = float(val)
            except (TypeError, ValueError):
                n_nan += 1
                continue
            if v != v:
                n_nan += 1
                continue
            if (pep, hla) in lookup:
                dups += 1
            lookup[(pep, hla)] = v
    if dups:
        print(f"[merge_seq2neo] ⚠️ {dups} 个重复 (Pep,HLA) key，取最后。", file=sys.stderr)
    print(f"[merge_seq2neo] cnn_results 读入 {len(lookup)} 唯一(Pep,HLA去星)分（NaN/空={n_nan}）")
    return lookup


def load_tscape_wt(path: Path) -> dict:
    """tscape_output.csv → {(peptide, allele归一): score}。列同 MT parse。"""
    lookup = {}
    n_bad = 0
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        fields = rd.fieldnames or []
        missing = {"Allele", "peptide", "score"} - set(fields)
        if missing:
            raise ValueError(f"tscape_output 缺列 {missing}。实际: {fields}")
        for r in rd:
            pep = str(r.get("peptide", "")).strip()
            allele = norm_allele_tscape(r.get("Allele", ""))
            try:
                sc = float(r.get("score", ""))
            except (TypeError, ValueError):
                n_bad += 1
                continue
            lookup[(pep, allele)] = sc
    print(f"[merge_tscape] tscape_output 读入 {len(lookup)} 唯一(pep,allele)分（bad={n_bad}）")
    return lookup


def cmd_merge(args):
    if not MERGED.exists():
        raise FileNotFoundError(f"merged 不存在: {MERGED}")

    s2n_path = Path(args.seq2neo_out)
    tsc_path = Path(args.tscape_out)
    if not s2n_path.exists():
        print(f"[merge] WARNING: Seq2Neo WT 输出不存在: {s2n_path} → WT_Seq2Neo 全 NaN。", file=sys.stderr)
        s2n_lookup = {}
    else:
        s2n_lookup = load_seq2neo_wt(s2n_path)
    if not tsc_path.exists():
        print(f"[merge] WARNING: T-SCAPE WT 输出不存在: {tsc_path} → WT_TSCAPE 全 NaN。", file=sys.stderr)
        tsc_lookup = {}
    else:
        tsc_lookup = load_tscape_wt(tsc_path)

    # 读 merged 全部行（保序、保全字段）
    with open(MERGED, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        fieldnames = list(rd.fieldnames)
        rows = list(rd)
    n_rows = len(rows)

    # 断言：不新写覆盖已存在同名列
    for newcol in ("WT_Seq2Neo", "WT_TSCAPE"):
        if newcol in fieldnames:
            raise RuntimeError(f"merged 已有列 {newcol}，拒绝覆盖（本任务应为新增）。")
    out_fields = fieldnames + ["WT_Seq2Neo", "WT_TSCAPE"]

    # 广播：每 bb_idx 行按 (WT_Subpeptide, HLA) 内容 join
    s2n_hit = 0
    tsc_hit = 0
    s2n_miss_pairs = set()
    tsc_miss_pairs = set()
    for r in rows:
        pep = clean_pep(r.get(WT_PEP_COL, ""))
        hla = str(r.get(HLA_COL, "")).strip()
        # Seq2Neo
        k_s = (pep, norm_hla_seq2neo(hla))
        if pep and k_s in s2n_lookup:
            r["WT_Seq2Neo"] = round(s2n_lookup[k_s], 6)
            s2n_hit += 1
        else:
            r["WT_Seq2Neo"] = ""
            if pep:
                s2n_miss_pairs.add((pep, hla))
        # T-SCAPE
        k_t = (pep, norm_allele_tscape(hla))
        if pep and k_t in tsc_lookup:
            r["WT_TSCAPE"] = round(tsc_lookup[k_t], 6)
            tsc_hit += 1
        else:
            r["WT_TSCAPE"] = ""
            if pep:
                tsc_miss_pairs.add((pep, hla))

    # ---- 断言 + 覆盖对比 ----
    assert n_rows == 4053, f"merged 数据行应 4053，实得 {n_rows}"

    def pct(x):
        return f"{x/n_rows*100:.1f}%"

    print("\n========== WT 补跑覆盖核查（coordinator 铁律：不能漏数据） ==========")
    print(f"广播前后行数：读入 {n_rows} → 写出 {n_rows}（无 join 丢失）")
    print(f"WT_Seq2Neo 非NaN行={s2n_hit} ({pct(s2n_hit)})   | 参照 MT_Seq2Neo=4053 (100.0%)")
    print(f"WT_TSCAPE   非NaN行={tsc_hit} ({pct(tsc_hit)})   | 参照 MT_TSCAPE  =4053 (100.0%)")

    if s2n_miss_pairs:
        print(f"\n[归因] WT_Seq2Neo 缺 {len(s2n_miss_pairs)} 个 (WT肽,HLA) 唯一对未命中：")
        for p in sorted(s2n_miss_pairs)[:30]:
            print(f"   MISS seq2neo: {p}")
    if tsc_miss_pairs:
        print(f"\n[归因] WT_TSCAPE 缺 {len(tsc_miss_pairs)} 个 (WT肽,HLA) 唯一对未命中：")
        for p in sorted(tsc_miss_pairs)[:30]:
            print(f"   MISS tscape: {p}")

    # 非全 NaN 断言（若两工具输出都存在则必须有命中）
    if s2n_lookup:
        assert s2n_hit > 0, "WT_Seq2Neo 全 NaN 但有输出 → join key 对不上，停下查！"
    if tsc_lookup:
        assert tsc_hit > 0, "WT_TSCAPE 全 NaN 但有输出 → join key 对不上，停下查！"

    # ---- 写 merged 副本（不覆盖原 merged）----
    MERGED_WITH_WT2.parent.mkdir(parents=True, exist_ok=True)
    with open(MERGED_WITH_WT2, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"\n[merge] 写副本 {MERGED_WITH_WT2}（原 merged 未动，可回滚）")
    print("[merge] 方向：WT_Seq2Neo=immunogenicity(0-1 越大越免疫原)；WT_TSCAPE=score(0-1 越高越强)，均不翻向。")


def main():
    ap = argparse.ArgumentParser(description="Seq2Neo/T-SCAPE WT 补跑 prep + merge（§3.1 DAI）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_prep = sub.add_parser("prep", help="从 merged 生成 WT 工具输入")
    ap_prep.set_defaults(func=cmd_prep)

    ap_merge = sub.add_parser("merge", help="解析 WT 输出 + 广播回 merged 副本")
    ap_merge.add_argument("--seq2neo-out", default=str(S2N_OUT_WT),
                          help="Seq2Neo WT cnn_results.csv（default: %(default)s）")
    ap_merge.add_argument("--tscape-out", default=str(TSC_OUT_WT),
                          help="T-SCAPE WT tscape_output.csv（default: %(default)s）")
    ap_merge.set_defaults(func=cmd_merge)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
