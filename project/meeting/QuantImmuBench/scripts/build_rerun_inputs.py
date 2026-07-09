#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_rerun_inputs.py
服务: quantimmu-bench / 切肽口径大改 §改动②/③ S5

用户授权整一组重跑: 改动② 完整窗集 (MT+WT) 灌全 30 工具。铁律「不能漏, 多跑没关系」。
本脚本从改动② 的 newcut 表 B 产出**两张 frozen 风格 for_tools 表** + 调 prepare_inputs_official
的导出逻辑产全 30 工具输入到 scripts/out_rerun/ + 完整性 manifest。不产分数, 只备输入。不跑代码。

================== 输入 (只读) ==================
  data/frozen/newcut_subpep_hla.NEW.csv   表 B (cut_from_protein WITH mane 产, 8056 行)
      列 mut_key,Patient_ID,Peptide_ID,Vaccine_Peptide,subpep_seq,subpep_pos,
         window_size,hla_allele_std,side{MT,WT},source{SLP,MANE,dropped},consistency_flag
      注: 表 B 只含成窗(SLP/MANE)行, dropped 窗不在此(见表 A)。
  data/frozen/newcut_mt_wt_pairs.NEW.csv  表 A (每窗一行, 有 window_idx/source; 取 dropped)
  data/frozen/wt_fullpeptide_official.csv canonical WT 全长 (回填 WT_FullPeptide)

================== 关键: MT/WT 配对键防坐标撞车 ==================
  表 B 的 subpep_pos = abs_start+1: SLP 窗用 SLP 坐标, MANE 窗用蛋白坐标。同一肽内若二者
  数值撞车 (突变近蛋白 N 端, 本数据有 4 肽位置≤25) -> prepare_inputs 的
  (mut_key, subpep_pos, HLA) 逐格配对会错配。故本脚本**合成唯一配对键** pair_pos:
    对每个 (mut_key), 按 (window_size, source, 原 subpep_pos) 唯一化编号 -> pair_pos。
    MT 与 WT 同窗共享 pair_pos (它们除 side/subpep_seq 外全同), 且肽内跨窗不撞。
  写进 for_tools 表的 subpep_pos = pair_pos; 原坐标留 abs_subpep_pos 列 (追溯, prepare 忽略额外列)。

================== 输出 ==================
  data/frozen/newcut_subpep_hla_MT.for_tools.csv   side==MT (source∈SLP/MANE), frozen MT schema
      列 mut_key,Patient_ID,Peptide_ID,Vaccine_Peptide,subpep_seq,subpep_pos,window_size,
         hla_allele_std [+ abs_subpep_pos,source,consistency_flag 追溯]
  data/frozen/newcut_subpep_hla_WT.for_tools.csv   side==WT, frozen WT schema
      列 …,WT_FullPeptide,…,side='WT' [+ 追溯列]; subpep_pos=pair_pos 与 MT 同窗对齐
  data/frozen/newcut_dropped_windows.NEW.csv       表 A 里 source=dropped 的窗 (显式记, 不静默丢)
  data/frozen/rerun_input_manifest.NEW.csv         逐 side×source 窗/行数 + 逐工具输入文件行数
  scripts/out_rerun/                                全 30 工具输入 (prepare_inputs_official 导出)

================== 跑法 (不在本脚本内跑; 交主线) ==================
  python scripts/build_rerun_inputs.py
  (前置: 已跑 build_mane_map.py + cut_from_protein.py WITH mane 产 newcut 表)
"""

import sys
import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "scripts"
FROZEN = ROOT / "data" / "frozen"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 复用 build_backbone + 全 export_*（格式契约 100% 沿用, 不重写）
sys.path.insert(0, str(HERE))
import prepare_inputs_official as pio  # noqa: E402

SUBPEP_B = FROZEN / "newcut_subpep_hla.NEW.csv"
TABLE_A = FROZEN / "newcut_mt_wt_pairs.NEW.csv"
WT_FULL = FROZEN / "wt_fullpeptide_official.csv"

OUT_MT_FT = FROZEN / "newcut_subpep_hla_MT.for_tools.csv"
OUT_WT_FT = FROZEN / "newcut_subpep_hla_WT.for_tools.csv"
OUT_DROPPED = FROZEN / "newcut_dropped_windows.NEW.csv"
OUT_MANIFEST = FROZEN / "rerun_input_manifest.NEW.csv"
OUT_DIR = HERE / "out_rerun"

MT_SCHEMA = ["mut_key", "Patient_ID", "Peptide_ID", "Vaccine_Peptide",
             "subpep_seq", "subpep_pos", "window_size", "hla_allele_std"]
WT_SCHEMA = ["mut_key", "Patient_ID", "Peptide_ID", "Vaccine_Peptide", "WT_FullPeptide",
             "subpep_seq", "subpep_pos", "window_size", "hla_allele_std", "side"]
TRACE_COLS = ["abs_subpep_pos", "source", "consistency_flag"]  # prepare 忽略, 供追溯


def build_for_tools_tables(subpep_b=SUBPEP_B, wt_full=WT_FULL,
                           out_mt_ft=OUT_MT_FT, out_wt_ft=OUT_WT_FT):
    """读表 B -> 合成 pair_pos -> 产 MT/WT for_tools 两表。返回 (mt_ft, wt_ft, b_kept)。"""
    b = pd.read_csv(subpep_b, dtype=str, encoding="utf-8")
    n_all = len(b)
    b = b[b["source"].isin(["SLP", "MANE"])].copy()  # 只留成窗(dropped 本就不在表 B)
    print(f"[info] 表 B 总行 {n_all} -> 成窗(SLP/MANE) {len(b)} "
          f"(side: {b['side'].value_counts().to_dict()})")

    # 合成唯一配对键 pair_pos: 每 (mut_key) 内按 (window_size, source, 原 subpep_pos) 唯一化。
    # MT/WT 同窗共享 (二者 _wkey 全同), 肽内跨窗不撞 (含 source, 隔开 SLP/MANE 坐标空间)。
    b["_wkey"] = (b["mut_key"] + "||" + b["window_size"] + "||" +
                  b["source"] + "||" + b["subpep_pos"])
    b["pair_pos"] = b.groupby("mut_key")["_wkey"].transform(
        lambda s: pd.factorize(s)[0] + 1)  # 1-based, 每肽独立编号

    # WT_FullPeptide 回填 (Peptide_ID -> canonical WT 全长)
    wt_full_df = pd.read_csv(wt_full, dtype=str, encoding="utf-8")
    wt_full_map = {}
    for r in wt_full_df.itertuples(index=False):
        v = "" if pd.isna(r.WT_FullPeptide) else str(r.WT_FullPeptide).strip()
        if v:
            wt_full_map[str(r.Peptide_ID)] = v

    # MT for_tools
    mt = b[b["side"] == "MT"].copy()
    mt_ft = pd.DataFrame({
        "mut_key": mt["mut_key"], "Patient_ID": mt["Patient_ID"],
        "Peptide_ID": mt["Peptide_ID"], "Vaccine_Peptide": mt["Vaccine_Peptide"],
        "subpep_seq": mt["subpep_seq"], "subpep_pos": mt["pair_pos"],
        "window_size": mt["window_size"], "hla_allele_std": mt["hla_allele_std"],
        "abs_subpep_pos": mt["subpep_pos"], "source": mt["source"],
        "consistency_flag": mt["consistency_flag"],
    })[MT_SCHEMA + TRACE_COLS]

    # WT for_tools (subpep_pos=pair_pos 与 MT 同窗对齐; WT_FullPeptide 回填)
    wt = b[b["side"] == "WT"].copy()
    wt_ft = pd.DataFrame({
        "mut_key": wt["mut_key"], "Patient_ID": wt["Patient_ID"],
        "Peptide_ID": wt["Peptide_ID"], "Vaccine_Peptide": wt["Vaccine_Peptide"],
        "WT_FullPeptide": wt["Peptide_ID"].map(wt_full_map).fillna(""),
        "subpep_seq": wt["subpep_seq"], "subpep_pos": wt["pair_pos"],
        "window_size": wt["window_size"], "hla_allele_std": wt["hla_allele_std"],
        "side": "WT",
        "abs_subpep_pos": wt["subpep_pos"], "source": wt["source"],
        "consistency_flag": wt["consistency_flag"],
    })[WT_SCHEMA + TRACE_COLS]

    n_wt_nofull = int((wt_ft["WT_FullPeptide"].astype(str).str.len() == 0).sum())
    if n_wt_nofull:
        print(f"[WARN] {n_wt_nofull} WT 行无 WT_FullPeptide 回填 (Peptide_ID 不在 wt_full); "
              f"WT_Subpeptide 仍在, 仅全长上下文空")

    mt_ft.to_csv(out_mt_ft, index=False, encoding="utf-8")
    wt_ft.to_csv(out_wt_ft, index=False, encoding="utf-8")
    print(f"[saved] {out_mt_ft}  shape={mt_ft.shape}")
    print(f"[saved] {out_wt_ft}  shape={wt_ft.shape}")
    return mt_ft, wt_ft, b


def record_dropped(table_a=TABLE_A, out_dropped=OUT_DROPPED):
    """从表 A 取 source=dropped 的窗, 显式落档 (不静默丢)。返回 dropped 行数。"""
    if not table_a.exists():
        print(f"[WARN] 表 A 缺失, 无法记 dropped: {table_a}")
        pd.DataFrame(columns=["mut_key", "Peptide_ID", "window_size", "window_idx",
                              "consistency_flag", "mane_prot_acc"]).to_csv(
            out_dropped, index=False, encoding="utf-8")
        return 0
    a = pd.read_csv(table_a, dtype=str, encoding="utf-8")
    dropped = a[a["source"] == "dropped"].copy()
    cols = [c for c in ["mut_key", "Peptide_ID", "window_size", "window_idx",
                        "consistency_flag", "mane_prot_acc"] if c in dropped.columns]
    dropped[cols].to_csv(out_dropped, index=False, encoding="utf-8")
    print(f"[saved] {out_dropped}  dropped 窗 {len(dropped)} 个 "
          f"(flag: {dropped['consistency_flag'].value_counts().to_dict() if len(dropped) else {}})")
    return len(dropped)


def _count_lines(p):
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return sum(1 for _ in fh)
    except Exception:
        return -1


def build_manifest(mt_ft, wt_ft, n_dropped, out_dir=OUT_DIR, out_manifest=OUT_MANIFEST):
    """完整性 manifest: 逐 side×source 窗/行数 + 逐工具输入文件行数 + 断言无空。"""
    rows = []

    # ── Part A: backbone 覆盖 (side×source 窗数/行数) ──────────────────────
    for label, ft in (("MT", mt_ft), ("WT", wt_ft)):
        for source, g in ft.groupby("source"):
            n_win = g[["mut_key", "subpep_pos"]].drop_duplicates().shape[0]
            rows.append({"category": "coverage", "name": f"{label}_{source}", "side": label,
                         "n_rows": len(g), "n_windows": n_win,
                         "note": f"source={source}"})
        # 汇总
        n_win_all = ft[["mut_key", "subpep_pos"]].drop_duplicates().shape[0]
        n_pep = ft["Peptide_ID"].nunique()
        n_pep_hla = ft[["subpep_seq", "hla_allele_std"]].drop_duplicates().shape[0]
        rows.append({"category": "coverage", "name": f"{label}_ALL", "side": label,
                     "n_rows": len(ft), "n_windows": n_win_all,
                     "note": f"{n_pep} 肽, {n_pep_hla} unique(subpep,HLA)"})
    rows.append({"category": "coverage", "name": "dropped_windows", "side": "-",
                 "n_rows": n_dropped, "n_windows": n_dropped, "note": "表 A source=dropped, 见 newcut_dropped_windows.NEW.csv"})

    # ── Part B: 逐工具输入文件行数 (glob out_rerun) ───────────────────────
    # 已知单文件 (name, side)
    single = [
        ("deepimmuno_input.csv", "MT", "DeepImmuno"),
        ("predig_input.csv", "BOTH", "PredIG(含|WT|行)"),
        ("improve_input.tsv", "BOTH", "IMPROVE(MT+WT_peptide)"),
        ("deephlapan_input_MT.csv", "MT", "deepHLApan-MT"),
        ("deephlapan_input_WT.csv", "WT", "deepHLApan-WT"),
        ("newtools/universe.csv", "BOTH", "newtools universe(回贴)"),
        ("newtools/uniq_pep_hla.csv", "BOTH", "newtools uniq_pep_hla(≈15工具主喂料)"),
        ("newtools/uniq_pep.csv", "BOTH", "newtools uniq_pep(HLA-agnostic如Repitope)"),
        ("ptuneos/ptuneos_input_all.tsv", "BOTH", "pTuneos all"),
        ("ptuneos/ptuneos_input_unique.tsv", "BOTH", "pTuneos unique"),
    ]
    empties = []
    for name, side, tool in single:
        p = out_dir / name
        n = _count_lines(p) if p.exists() else -1
        status = "OK" if n > 1 else ("EMPTY" if n in (0, 1) else "MISSING")
        if status != "OK":
            empties.append((name, status))
        rows.append({"category": "artifact", "name": name, "side": side,
                     "n_rows": n, "n_windows": "", "note": f"{tool} [{status}]"})

    # 按 allele 分目录: PRIME / ImmuneApp 的 peps_{MT,WT}.txt
    for prefix, tool in (("prime_input_*", "PRIME"), ("immuneapp_input_*", "ImmuneApp")):
        for side in ("MT", "WT"):
            n_files = 0
            n_lines = 0
            for d in sorted(out_dir.glob(prefix)):
                fp = d / f"peps_{side}.txt"
                if fp.exists():
                    n_files += 1
                    n_lines += max(_count_lines(fp), 0)
            status = "OK" if n_lines > 0 else "EMPTY/NONE"
            if n_lines == 0:
                empties.append((f"{prefix}/peps_{side}.txt", status))
            rows.append({"category": "artifact", "name": f"{prefix}/peps_{side}.txt",
                         "side": side, "n_rows": n_lines, "n_windows": n_files,
                         "note": f"{tool}-{side} 跨 {n_files} allele 目录 [{status}]"})

    # newtools uniq_pep_hla 的 source(MT/WT/BOTH) 分布 (side 覆盖核)
    uph = out_dir / "newtools" / "uniq_pep_hla.csv"
    if uph.exists():
        try:
            u = pd.read_csv(uph, encoding="utf-8")
            if "source" in u.columns:
                for src, cnt in u["source"].value_counts().items():
                    rows.append({"category": "artifact_detail",
                                 "name": "uniq_pep_hla.source", "side": src,
                                 "n_rows": int(cnt), "n_windows": "",
                                 "note": "uniq(pep,HLA) 按 MT/WT/BOTH 分布"})
        except Exception as e:
            print(f"[WARN] 读 uniq_pep_hla 分布失败: {e}")

    man = pd.DataFrame(rows, columns=["category", "name", "side", "n_rows", "n_windows", "note"])
    man.to_csv(out_manifest, index=False, encoding="utf-8")
    print(f"[saved] {out_manifest}  shape={man.shape}")
    return man, empties


def main():
    ap = argparse.ArgumentParser(description="改动② 完整窗集 -> for_tools 两表 + 全 30 工具输入 (不跑)")
    ap.add_argument("--out-dir", default=str(OUT_DIR), help="工具输入输出目录 (默认 scripts/out_rerun/)")
    ap.add_argument("--table-b", default=str(SUBPEP_B), help="输入表 B (默认 newcut_subpep_hla.NEW.csv)")
    ap.add_argument("--table-a", default=str(TABLE_A), help="输入表 A (取 dropped 窗)")
    ap.add_argument("--mt-ft", default=str(OUT_MT_FT), help="输出 MT for_tools 表路径")
    ap.add_argument("--wt-ft", default=str(OUT_WT_FT), help="输出 WT for_tools 表路径")
    ap.add_argument("--dropped", default=str(OUT_DROPPED), help="输出 dropped 窗清单路径")
    ap.add_argument("--manifest", default=str(OUT_MANIFEST), help="输出完整性 manifest 路径")
    args = ap.parse_args()
    out_dir = Path(args.out_dir).resolve()
    table_b = Path(args.table_b)
    table_a = Path(args.table_a)
    mt_ft_path = Path(args.mt_ft)
    wt_ft_path = Path(args.wt_ft)
    dropped_path = Path(args.dropped)
    manifest_path = Path(args.manifest)

    for p in (table_b, WT_FULL):
        if not p.exists():
            raise SystemExit(f"[ERR] 依赖缺失: {p}  (先跑 cut_from_protein.py + reconstruct_wt)")

    # 1. 产两张 for_tools 表 (合成 pair_pos 防坐标撞车)
    mt_ft, wt_ft, _ = build_for_tools_tables(
        subpep_b=table_b, out_mt_ft=mt_ft_path, out_wt_ft=wt_ft_path)

    # 2. 记 dropped 窗 (显式, 不静默丢)
    n_dropped = record_dropped(table_a=table_a, out_dropped=dropped_path)

    # 3. 调 prepare_inputs_official 导出全 30 工具输入到 out_rerun/
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n[info] === prepare_inputs_official 导出 -> {out_dir} ===")
    backbone = pio.build_backbone(out_dir, mt_csv=mt_ft_path, wt_csv=wt_ft_path)
    pio.assert_coverage(backbone, expected_peptides=None)  # 改动② 肽数动态, 软报
    pio.export_deepimmuno(backbone, out_dir)
    pio.export_predig(backbone, out_dir)
    pio.export_improve(backbone, out_dir)
    pio.wave3.export_prime(backbone, out_dir)
    pio.wave3.export_immuneapp(backbone, out_dir)
    pio.wave3.export_deephlapan(backbone, out_dir)
    pio.export_newtools_universe(backbone, out_dir)
    pio.export_ptuneos(backbone, out_dir)
    pio.report_hla_warnings()

    # 4. 完整性 manifest + 断言无空 (命门: 每工具都拿到全部窗, 宁多勿漏)
    man, empties = build_manifest(mt_ft, wt_ft, n_dropped,
                                  out_dir=out_dir, out_manifest=manifest_path)

    print("\n========== 完整性汇总 ==========")
    cov = man[man["category"] == "coverage"]
    print("[side×source 窗/行数]")
    print(cov[["name", "n_rows", "n_windows", "note"]].to_string(index=False))
    print(f"\n[backbone] {len(backbone)} 行; MT 窗={cov[cov['name']=='MT_ALL']['n_windows'].values}, "
          f"WT 窗={cov[cov['name']=='WT_ALL']['n_windows'].values}; dropped 窗={n_dropped}")

    if empties:
        print(f"\n[FLAG][EMPTY] {len(empties)} 个工具输入为空/缺失 (人工核, 别静默漏):")
        for name, st in empties:
            print(f"    {name}  [{st}]")
    else:
        print("\n[OK] 全部工具输入文件非空 (完整性通过)")

    # 命门文件: newtools uniq_pep_hla 是 ≈15 工具主喂料, 空则重跑必漏 -> 硬失败
    uph = out_dir / "newtools" / "uniq_pep_hla.csv"
    if _count_lines(uph) <= 1:
        raise SystemExit(f"[FAIL] 命门文件空/缺: {uph} (≈15 HPC 工具主喂料, 不可空)")

    print("[DONE] build_rerun_inputs 完成 (只写未跑; for_tools 两表 + out_rerun 全工具输入 + manifest)")


if __name__ == "__main__":
    main()
