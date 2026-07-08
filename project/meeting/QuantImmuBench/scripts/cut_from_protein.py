#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cut_from_protein.py
服务: quantimmu-bench / 切肽口径大改 §改动②/③

把「切 ELISpot 长肽 SLP 喂工具」改成「从原始蛋白定点切 *只跨突变 AA* 的 L-mer 窗」。
点突变 + 固定窗长 L -> 跨突变窗口数恒定 = L -> 袋子大小常数 -> 从源头掐死肽长混杂。
同时对每个 MT 窗产同坐标 WT 窗 (SNV 只差 1 残基) 供配对算 DAI。仅 SNV (102 条)。

================== 算法 (逐 SNV 肽, 每个固定窗长 L 独立) ==================
  Step0 只留 SNV: is_snv = Variant_Type=="SNV" or parse_protein_change(...) is not None
  Step1 SLP 内定位: q(0-based) = 突变位; WT_SLP = MT SLP 把 q 处 mt_aa 换回 wt_aa
        (prot_pos 仅 QC 交叉核, 绝不拿来跨参考索引)
  Step2 核区+判溢出: L 个 mut-spanning 窗起点 = q-L+1 … q; 核区 = [q-(L-1), q+(L-1)]
        核区 ⊆ [0, len(SLP)-1] -> 全 SLP-only; 任一端越界 -> 需 MANE
  Step3 SLP-only 切: 落在 SLP 内的窗 MT_win=SLP[s:s+L], WT_win=WT_SLP[s:s+L] (source=SLP)
  Step4 溢出 MANE 补 (锚定+双闸门): 锚核区(≤2L-1)到 MANE 蛋白 P
        双闸: 唯一命中 且 P[abs_mut_pos]==wt_aa -> 构 MT_context, 溢出窗按绝对坐标切
        0/多命中 或残基不符 -> 真 isoform 冲突 -> dropped + 记 TODO, 绝不静默拼接
  Step5 端部截断: MANE 锚成但突变距 P 端 <L-1 -> 真实窗 <L -> END_TRUNCATED
  Step6 ×HLA 展开: 表 A 每行按患者 HLA 分裂, MT/WT 各出 side 行 -> 表 B

================== 输入 (只读 frozen + MANE) ==================
  data/frozen/ds2_official_groundtruth.csv    (MT 全长 SLP + p.XnY + Short_Epitope + ...)
  data/frozen/wt_fullpeptide_official.csv      (canonical WT 全长; 交叉核 + locate 歧义兜底)
  data/frozen/patient_hla.csv                  (Patient_ID -> hla_allele_std, ×HLA 展开用)
  scripts/build_mane_map.build_mane_map()      (溢出锚定原始蛋白; 仅溢出时用)

================== 输出 (先写 .NEW.csv 别覆盖旧 canonical) ==================
  data/frozen/newcut_mt_wt_pairs.NEW.csv   (表 A: 每窗一行)
  data/frozen/newcut_subpep_hla.NEW.csv    (表 B: 窗 × HLA × {MT,WT} side)
  data/frozen/newcut_conflicts.NEW.csv     (TODO 清单: locate 失败 / isoform 冲突 / 端截断)

================== 跑法 (不在本脚本内跑; 交主线) ==================
  python scripts/cut_from_protein.py               # 9mer 默认
  python scripts/cut_from_protein.py --window 8-11
  python scripts/cut_from_protein.py --no-mane     # 纯 SLP 烟测(溢出窗记 MANE_UNAVAILABLE)
"""

import sys
import argparse
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
FROZEN_DIR = ROOT / "data" / "frozen"

# 复用现有纯函数 (照抄签名, 不自造)
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "analysis" / "phase0"))
from reconstruct_wt_official import parse_protein_change, locate_mut_pos, reconstruct_wt  # noqa: E402
from p0c_subpep_expansion import parse_window  # noqa: E402  (slide 不用: 本脚本自定 mut-spanning 窗)
from build_mane_map import build_mane_map  # noqa: E402

GT_CSV = FROZEN_DIR / "ds2_official_groundtruth.csv"
WT_CSV = FROZEN_DIR / "wt_fullpeptide_official.csv"
HLA_CSV = FROZEN_DIR / "patient_hla.csv"

OUT_PAIRS = FROZEN_DIR / "newcut_mt_wt_pairs.NEW.csv"
OUT_SUBPEP = FROZEN_DIR / "newcut_subpep_hla.NEW.csv"
OUT_CONFLICT = FROZEN_DIR / "newcut_conflicts.NEW.csv"


# ─────────────────────────────────────────────────────────────────────────
# MANE exact-find 锚定 (源: data/from_advisor_wt_2026-07/2_infer_wt.py L149,
# 逐字复制 -- 该模块名以数字开头无法 import, 且其 main 有 input()/FASTA 拼接 bug)
# ─────────────────────────────────────────────────────────────────────────
def find_peptide_in_sequence(peptide, full_sequence):
    """在全长蛋白里定位肽 (纯 str.find)。返回 (found, start_1based, msg)。"""
    pos = full_sequence.find(peptide)
    if pos != -1:
        return True, pos + 1, f"Found at position {pos+1}-{pos+len(peptide)}"
    else:
        return False, -1, "Not found in reference sequence"


def find_all_occurrences(sub, seq):
    """seq 中 sub 的全部 0-based 起点 (判唯一命中用; 双闸门①要求恰 1 命中)。"""
    idxs = []
    start = 0
    while True:
        i = seq.find(sub, start)
        if i == -1:
            break
        idxs.append(i)
        start = i + 1  # 允许重叠命中
    return idxs


def lookup_mane(gene, mane):
    """gene symbol -> MANE entry。官方 symbol 优先; 不命中走别名(alias/prev -> hgnc_id -> by_hgnc); 仍无 -> None。"""
    g = gene.strip().upper()
    e = mane["by_symbol"].get(g)
    if e is not None:
        return e
    hgnc = mane.get("by_alias", {}).get(g)   # 别名/旧名 -> hgnc_id (如 CCDC130 -> HGNC:28118)
    if hgnc:
        return mane["by_hgnc"].get(hgnc)
    return None


# ─────────────────────────────────────────────────────────────────────────
# Step1: SLP 内定位突变位 + 定 WT_SLP (canonical 交叉核 + locate 歧义兜底)
# ─────────────────────────────────────────────────────────────────────────
def locate_and_wt(slp, wt_aa, mt_aa, short_epi, canon_wt):
    """
    返回 (q_0based, wt_slp, flag, detail)。
    主法: locate_mut_pos 唯一定位 -> reconstruct_wt 回推 WT_SLP。
    canonical WT (wt_fullpeptide_official.csv) 若存在: 作交叉核, 不一致以 canonical 为准并 flag;
    locate 歧义时用 canonical 与 MT 的单残基差回推 q 兜底。
    flag: 'OK' / 'WT_RECON_MISMATCH' / 'LOCATE_FAIL'
    """
    q1, st = locate_mut_pos(slp, mt_aa, short_epi)
    q = q1 - 1 if (st == "ok" and q1 is not None) else None
    wt_recon = reconstruct_wt(slp, wt_aa, mt_aa, q1) if q is not None else None

    canon = canon_wt if (canon_wt and len(canon_wt) == len(slp)) else None

    # 主路径成功
    if wt_recon is not None:
        if canon is not None and wt_recon != canon:
            # 交叉核失败 -> 以 canonical 为准, 重定位单残基差
            diffs = [i for i in range(len(slp)) if slp[i] != canon[i]]
            if len(diffs) == 1 and slp[diffs[0]] == mt_aa and canon[diffs[0]] == wt_aa:
                return diffs[0], canon, "WT_RECON_MISMATCH", f"recon!=canon, 用canonical@{diffs[0]}"
            return q, wt_recon, "WT_RECON_MISMATCH", "recon!=canon 且canon非单残基差, 保留recon"
        return q, wt_recon, "OK", ""

    # locate 歧义 -> canonical 兜底 (SNV 只差 1 残基)
    if canon is not None:
        diffs = [i for i in range(len(slp)) if slp[i] != canon[i]]
        if len(diffs) == 1 and slp[diffs[0]] == mt_aa and canon[diffs[0]] == wt_aa:
            return diffs[0], canon, "OK", "locate歧义, canonical单残基差定位"

    return None, None, "LOCATE_FAIL", f"locate={st}, canon={'有' if canon else '无'}"


# ─────────────────────────────────────────────────────────────────────────
# 单肽单窗长 L 切窗 (Step2-5)
# ─────────────────────────────────────────────────────────────────────────
def cut_one(row, L, wt_map, mane, stats, conflicts):
    """
    对单条 SNV 肽在固定窗长 L 下切 L 个 mut-spanning 窗。返回表 A 行 list(dict)。
    每个窗要么 SLP-only, 要么 MANE 补, 要么 dropped。
    """
    mut_key = row.mut_key
    pep_id = str(row.Peptide_ID)
    patient = int(row.Patient_ID)
    slp = "" if pd.isna(row.Vaccine_Peptide) else str(row.Vaccine_Peptide).strip()
    short_epi = row.Short_Epitope
    gene_change = row.Gene_and_Protein_Change

    parsed = parse_protein_change(gene_change)
    if parsed is None:
        return []  # Step0 已滤; 双保险
    wt_aa, mt_aa, prot_pos = parsed
    gene = str(gene_change).split("|", 1)[0].strip()

    # Step1: 定位 + WT_SLP
    canon_wt = wt_map.get(pep_id, "")
    q, wt_slp, loc_flag, loc_detail = locate_and_wt(slp, wt_aa, mt_aa, short_epi, canon_wt)
    if q is None or wt_slp is None:
        stats["locate_fail"] += 1
        conflicts.append({
            "mut_key": mut_key, "Peptide_ID": pep_id, "gene": gene, "window_size": L,
            "flag": "LOCATE_FAIL", "detail": loc_detail,
        })
        return []
    if loc_flag == "WT_RECON_MISMATCH":
        stats["wt_mismatch"] += 1
        conflicts.append({
            "mut_key": mut_key, "Peptide_ID": pep_id, "gene": gene, "window_size": L,
            "flag": "WT_RECON_MISMATCH", "detail": loc_detail,
        })

    n = len(slp)

    # Step2: 核区 + 判溢出
    core_lo = q - (L - 1)
    core_hi = q + (L - 1)          # inclusive
    overflow = (core_lo < 0) or (core_hi > n - 1)

    # Step4 前置: 溢出则先锚定一次 MANE (核区 exact-find + 双闸门)
    mane_ok = False
    abs_mut_pos = None
    P = None
    mt_context = None
    mane_acc = ""
    anchor_flag = "OK"
    if overflow:
        stats["peptides_overflow"] += 1
        if mane is None:
            anchor_flag = "MANE_UNAVAILABLE"
        else:
            entry = lookup_mane(gene, mane)
            if entry is None:
                anchor_flag = "MANE_GENE_NOTFOUND"
                conflicts.append({
                    "mut_key": mut_key, "Peptide_ID": pep_id, "gene": gene, "window_size": L,
                    "flag": "MANE_GENE_NOTFOUND", "detail": f"gene '{gene}' 不在 MANE by_symbol/别名",
                })
            else:
                P = entry["protein_seq"]
                mane_acc = entry["refseq_prot_acc"]
                core_start = max(0, q - (L - 1))          # SLP 0-based 核区起点
                core_wt = wt_slp[core_start: q + (L - 1) + 1]   # 只锚核区(≤2L-1), 绕无关侧翼
                occ = find_all_occurrences(core_wt, P)
                if len(occ) == 1:
                    abs_mut_pos = occ[0] + (q - core_start)   # 突变在 P 的绝对 0-based 位
                    # 双闸门②: WT 蛋白该位须 == wt_aa
                    if 0 <= abs_mut_pos < len(P) and P[abs_mut_pos] == wt_aa:
                        mane_ok = True
                        mt_context = P[:abs_mut_pos] + mt_aa + P[abs_mut_pos + 1:]
                        stats["anchor_ok"] += 1
                    else:
                        anchor_flag = "ISOFORM_CONFLICT"
                        got = P[abs_mut_pos] if (0 <= abs_mut_pos < len(P)) else "?"
                        conflicts.append({
                            "mut_key": mut_key, "Peptide_ID": pep_id, "gene": gene, "window_size": L,
                            "flag": "ISOFORM_CONFLICT",
                            "detail": f"锚成但P[{abs_mut_pos}]={got}!=wt_aa {wt_aa} ({mane_acc})",
                        })
                        stats["anchor_conflict"] += 1
                else:
                    anchor_flag = "ISOFORM_CONFLICT"
                    conflicts.append({
                        "mut_key": mut_key, "Peptide_ID": pep_id, "gene": gene, "window_size": L,
                        "flag": "ISOFORM_CONFLICT",
                        "detail": f"核区在{mane_acc}命中{len(occ)}次(需恰1), core_wt={core_wt}",
                    })
                    stats["anchor_conflict"] += 1

    # Step3/4/5: 逐窗切
    rows = []
    for j in range(L):
        s = q - L + 1 + j          # SLP 0-based 起点 (可能 <0)
        mut_off = q - s            # 突变在窗内偏移 = L-1-j (恒 0..L-1, 每窗必跨突变)
        base = {
            "mut_key": mut_key, "Patient_ID": patient, "Peptide_ID": pep_id,
            "window_size": L, "window_idx": j, "mut_offset_in_window": mut_off,
        }
        if s >= 0 and s + L <= n:
            # Step3: SLP-only
            rows.append({**base,
                         "abs_start": s, "abs_mut_pos": q,
                         "MT_peptide": slp[s:s + L], "WT_peptide": wt_slp[s:s + L],
                         "source": "SLP", "consistency_flag": "OK", "mane_prot_acc": ""})
            stats["win_slp"] += 1
        elif mane_ok:
            # Step4: MANE 补; SLP->P 坐标映射 abs(x) = abs_mut_pos + (x - q)
            a_start = abs_mut_pos + (s - q)
            if a_start >= 0 and a_start + L <= len(P):
                rows.append({**base,
                             "abs_start": a_start, "abs_mut_pos": abs_mut_pos,
                             "MT_peptide": mt_context[a_start:a_start + L],
                             "WT_peptide": P[a_start:a_start + L],
                             "source": "MANE", "consistency_flag": "OK", "mane_prot_acc": mane_acc})
                stats["win_mane"] += 1
            else:
                # Step5: 端部截断 (突变距 P 端 <L-1, 该窗无法成完整 L-mer)
                rows.append({**base,
                             "abs_start": "", "abs_mut_pos": abs_mut_pos,
                             "MT_peptide": "", "WT_peptide": "",
                             "source": "dropped", "consistency_flag": "END_TRUNCATED",
                             "mane_prot_acc": mane_acc})
                stats["win_endtrunc"] += 1
        else:
            # 溢出但 MANE 未锚成 -> dropped (isoform 冲突 / MANE 缺 / gene 未找到)
            rows.append({**base,
                         "abs_start": "", "abs_mut_pos": "",
                         "MT_peptide": "", "WT_peptide": "",
                         "source": "dropped", "consistency_flag": anchor_flag,
                         "mane_prot_acc": mane_acc})
            stats["win_dropped"] += 1

    # n_windows_actual = 该肽实际成窗数 (有序列的 OK 窗)
    n_actual = sum(1 for r in rows if r["source"] in ("SLP", "MANE"))
    for r in rows:
        r["n_windows_actual"] = n_actual
    return rows


# ─────────────────────────────────────────────────────────────────────────
# Step6: ×HLA 展开 (表 A -> 表 B, MT/WT 各出 side 行)
# ─────────────────────────────────────────────────────────────────────────
def expand_hla(pairs_rows, slp_map, patient_hla):
    """
    对每个成窗行(source∈SLP/MANE), 按患者 HLA 等位分裂, MT/WT 各出一 side 行。
    """
    sub_rows = []
    for r in pairs_rows:
        if r["source"] not in ("SLP", "MANE"):
            continue  # dropped 无序列, 不展开
        patient = r["Patient_ID"]
        alleles = patient_hla.get(patient, [])
        if not alleles:
            continue
        vp = slp_map.get(r["Peptide_ID"], "")  # 溯源: 原始 MT 全长 SLP
        for side, seq in (("MT", r["MT_peptide"]), ("WT", r["WT_peptide"])):
            if not seq:
                continue
            for allele in alleles:
                sub_rows.append({
                    "mut_key": r["mut_key"],
                    "Patient_ID": patient,
                    "Peptide_ID": r["Peptide_ID"],
                    "Vaccine_Peptide": vp,
                    "subpep_seq": seq,
                    "subpep_pos": (r["abs_start"] + 1) if isinstance(r["abs_start"], int) else "",
                    "window_size": r["window_size"],
                    "hla_allele_std": allele,
                    "side": side,
                    "source": r["source"],
                    "consistency_flag": r["consistency_flag"],
                })
    return sub_rows


def main():
    ap = argparse.ArgumentParser(description="从原始蛋白定点切 mut-spanning L-mer 窗 + MT/WT 配对 (不跑工具)")
    ap.add_argument("--window", default="9", help="窗长: '9'(默认) 或 '8-11'")
    ap.add_argument("--no-mane", action="store_true", help="跳过 MANE(溢出窗记 MANE_UNAVAILABLE), 纯 SLP 烟测用")
    args = ap.parse_args()
    windows = parse_window(args.window)
    print(f"[info] 窗长: {windows}")

    for p in (GT_CSV, WT_CSV, HLA_CSV):
        if not p.exists():
            raise SystemExit(f"[ERR] 依赖缺失: {p}")

    gt = pd.read_csv(GT_CSV)
    print(f"[info] 官方肽数: {len(gt)}")

    # canonical WT 全长 map (Peptide_ID -> WT_FullPeptide; 仅有 WT 的行)
    wt_df = pd.read_csv(WT_CSV)
    wt_map = {}
    for r in wt_df.itertuples(index=False):
        wt = "" if pd.isna(r.WT_FullPeptide) else str(r.WT_FullPeptide).strip()
        if wt:
            wt_map[str(r.Peptide_ID)] = wt
    print(f"[info] canonical WT 肽数: {len(wt_map)}")

    # 患者 HLA map (Patient_ID -> [hla_allele_std])
    hla_df = pd.read_csv(HLA_CSV)
    patient_hla = {}
    for pid, grp in hla_df.groupby("Patient_ID"):
        patient_hla[int(pid)] = sorted(set(grp["hla_allele_std"].dropna().astype(str)))
    print(f"[info] 患者数(有 HLA): {len(patient_hla)}")

    # 原始 MT 全长 SLP map (溯源用)
    slp_map = {}

    # MANE map (溢出锚定; --no-mane 或加载失败 -> None)
    mane = None
    if not args.no_mane:
        try:
            mane = build_mane_map(use_cache=True)
        except SystemExit as e:
            print(f"[WARN] MANE 加载失败 ({e}); 溢出窗将记 MANE_UNAVAILABLE")
            mane = None

    # Step0: 只留 SNV (含 AMACR: Variant_Type 空但记法可解析)
    snv_rows = []
    for r in gt.itertuples(index=False):
        vtype = "" if pd.isna(r.Variant_Type) else str(r.Variant_Type).strip()
        parsed = parse_protein_change(r.Gene_and_Protein_Change)
        is_snv = (vtype == "SNV") or (parsed is not None)
        if is_snv and parsed is not None:
            snv_rows.append(r)
            slp_map[str(r.Peptide_ID)] = "" if pd.isna(r.Vaccine_Peptide) else str(r.Vaccine_Peptide).strip()
    print(f"[info] SNV 肽数(Step0, 期望 102): {len(snv_rows)}")

    # 逐窗长 × 逐肽切窗
    all_pairs = []
    conflicts = []
    stats = {k: 0 for k in ("locate_fail", "wt_mismatch", "peptides_overflow",
                            "anchor_ok", "anchor_conflict",
                            "win_slp", "win_mane", "win_dropped", "win_endtrunc")}
    for L in windows:
        for r in snv_rows:
            all_pairs.extend(cut_one(r, L, wt_map, mane, stats, conflicts))

    # Step6: ×HLA 展开
    sub_rows = expand_hla(all_pairs, slp_map, patient_hla)

    # ── 写出 (先 .NEW.csv 不覆盖旧 canonical) ──────────────────────────────
    FROZEN_DIR.mkdir(parents=True, exist_ok=True)
    col_A = ["mut_key", "Patient_ID", "Peptide_ID", "window_size", "window_idx",
             "mut_offset_in_window", "abs_start", "abs_mut_pos", "MT_peptide", "WT_peptide",
             "source", "consistency_flag", "n_windows_actual", "mane_prot_acc"]
    pairs_df = pd.DataFrame(all_pairs, columns=col_A)
    pairs_df.to_csv(OUT_PAIRS, index=False, encoding="utf-8")
    print(f"\n[saved] {OUT_PAIRS}  shape={pairs_df.shape}")

    col_B = ["mut_key", "Patient_ID", "Peptide_ID", "Vaccine_Peptide", "subpep_seq",
             "subpep_pos", "window_size", "hla_allele_std", "side", "source", "consistency_flag"]
    sub_df = pd.DataFrame(sub_rows, columns=col_B)
    sub_df.to_csv(OUT_SUBPEP, index=False, encoding="utf-8")
    print(f"[saved] {OUT_SUBPEP}  shape={sub_df.shape}")

    conf_df = pd.DataFrame(conflicts, columns=["mut_key", "Peptide_ID", "gene", "window_size", "flag", "detail"])
    conf_df.to_csv(OUT_CONFLICT, index=False, encoding="utf-8")
    print(f"[saved] {OUT_CONFLICT}  shape={conf_df.shape}")

    # ── 计数汇总 (供主线烟测核对; L=9 默认期望 ≈766 SLP / 152 MANE / 少量 dropped, 918 总窗) ──
    print("\n========== 计数汇总 ==========")
    print(f"SNV 肽数           = {len(snv_rows)}  (期望 102)")
    print(f"locate 失败肽      = {stats['locate_fail']}  (期望 0)")
    print(f"WT 交叉核失配      = {stats['wt_mismatch']}  (理想 0; >0 见 conflicts)")
    print(f"溢出肽(需 MANE)    = {stats['peptides_overflow']}  锚成={stats['anchor_ok']} isoform冲突={stats['anchor_conflict']}")
    print(f"窗: SLP={stats['win_slp']}  MANE={stats['win_mane']}  "
          f"dropped={stats['win_dropped']}  END_TRUNCATED={stats['win_endtrunc']}")
    total_win = len(pairs_df)
    ok_win = stats["win_slp"] + stats["win_mane"]
    print(f"总窗(表A 行)       = {total_win}  其中成窗(有序列)={ok_win}  "
          f"(单窗长 L 时期望总窗=102×L; L=9 -> 918)")
    print(f"表B 行(窗×HLA×side)= {len(sub_df)}")
    # 恒常数自检: 每肽每窗长应恰 L 行(含 dropped 占位), 破坏则报
    if len(windows) == 1:
        L = windows[0]
        per = pairs_df.groupby("Peptide_ID").size()
        bad = per[per != L]
        if bad.empty:
            print(f"[OK] 每肽窗数恒 = {L} (袋子大小常数, 肽长混杂从源头掐死)")
        else:
            print(f"[FLAG] {len(bad)} 肽窗数 != {L} (应恒常数, 人工核): {bad.to_dict()}")
    print("[DONE] cut_from_protein 完成")


if __name__ == "__main__":
    main()
