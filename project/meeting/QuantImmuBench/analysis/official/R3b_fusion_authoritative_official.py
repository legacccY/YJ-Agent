#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R3b_fusion_authoritative_official.py
====================================
服务: QuantImmuBench §3.3（多工具融合）+ §2.6（无泄漏评估）。
按袁老师指示 + 文献权威做法重做融合层：**预先固定面板 + median 名次融合，零成员挑选**。

为什么这么做（研究结论，见 04_LOG / 报告 §2）：
  免疫信息学的权威组合范式（IEDB Consensus / pVACtools / NetMHCcons / TESLA）一致是——
  成员**先验固定**（按覆盖或生物学，不按在评估集上的表现挑）、聚合取**百分位名次的中位数**
  （median rank，parameter-free、不学权重）。在同一小样本上"又选又评"会引入选择偏倚/优胜者
  诅咒（Ambroise&McLachlan 2002 PNAS；Cawley&Talbot 2010 JMLR；Gelman&Loken 2014），
  正对应本项目实测的"选择虚高≈0.09 + 成员不稳"。故融合成员**不数据驱动挑**（弃旧 SURV6 存活式选择）。

关键简化：median / mean 名次融合是**无监督、无参数**的——固定面板下没有成员/超参可选，
  不存在选择虚高，per-patient Spearman 本身即无泄漏，**无需嵌套 CV**。真问题=一个预先固定
  的面板打不打得过最强单工具。

做什么:
  几组**预先固定**的面板（零挑选）× {median, mean_rank} 名次融合，各算 DS2 per-patient
  Spearman（裸 + 控肽长），与最强单工具 netMHCpan_BA_max 病人配对显著性比较。
  面板成员一律用零选择 <tool>_max（不做 pooling 挑选），保证全链零挑选。

面板（先验固定，看结果前定死）:
  · 全用-免疫原  : 全部免疫原性类工具（IEDB/pVACtools "use all applicable" 式）
  · 全用-全部    : 全部工具（呈递+免疫原）
  · 双轴小面板   : netMHCpan_BA(呈递) + PRIME + deepHLApan（识别）——TESLA 式呈递+识别轴
  · SURV6(旧对照): 旧数据驱动"存活"6 工具，仅作对照（показ其非权威）
  （DeepNetBim 取最高分后饱和成常数、无法排序 → 按"不适用"排除，同单工具榜。）

输出 (analysis/official/, 或 QIB_OUTDIR 重定向到 newcut9mer):
  R3b_fusion_authoritative_official.csv       每 (面板×聚合) 一行
  R3b_fusion_authoritative_official.summary.json

跑法 (主线跑; 新切口径):
  set QIB_OUTDIR=analysis/official/newcut9mer
  python analysis/official/R3b_fusion_authoritative_official.py \
      --input data/frozen/pooled_clean_rerun_9mer.csv --min_pep 8
"""
import sys
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _official_common import (                              # noqa: E402
    load_frozen, present_patients, per_patient_spearman,
    per_patient_partial_spearman, apply_fusion, paired_patient_test,
    pool_col, METHOD_ORDER, UNSUPERVISED_FUSIONS, MIN_PEP, FROZEN_POOLED,
    ensure_out_dir, r6,
)

# 类别（与报告 29 工具表一致）
IMMUNO_TOOLS = [
    "deepHLApan", "IEDB_Calis", "ImmuneApp", "PRIME", "DeepImmuno", "PredIG",
    "IMPROVE", "pTuneos", "NeoTImmuML", "BigMHC_IM", "CNNeo", "Repitope",
    "TSCAPE", "NetTepi", "ICERFIRE", "MUNIS", "andy90", "ImmuGenX", "Seq2Neo", "NeoaG",
]  # DeepNetBim 排除（取最高分饱和无法排序）
BINDING_TOOLS = ["netMHCpan_BA", "netMHCpan_EL", "netMHCstabpan", "MHCflurry",
                 "MHCnuggets", "MHCseqNet", "TransHLA", "HLAthena"]
SURV6 = ["PredIG", "IMPROVE", "pTuneos", "PRIME", "ImmuneApp", "deepHLApan"]

BASELINE_TOOL = "netMHCpan_BA"          # 最强单工具（呈递金标准；本轮各口径均居首）

# 预先固定面板（看结果前定死；成员一律用 <tool>_max，零挑选）
PANELS = {
    "全用-免疫原": IMMUNO_TOOLS,
    "全用-全部": IMMUNO_TOOLS + BINDING_TOOLS,
    "双轴小面板": ["netMHCpan_BA", "PRIME", "deepHLApan"],
    "SURV6(旧对照)": SURV6,
}
# 全 12 融合法（大纲 §3.3.1）: 前 8 无监督无参数(零挑选) + 后 4 学习型(病人级LOPO学权重)。
# median=文献权威 headline; mean_rank=等权对照; 其余为完整性。
AGGREGATORS = list(METHOD_ORDER)


def member_cols(df, tools):
    """面板成员 -> <tool>_max 列（零选择 pooling）; 缺列/全空/常量剔除。"""
    cols, used = [], []
    for t in tools:
        c = pool_col(t, "max")
        if c not in df.columns:
            continue
        s = df[c]
        if s.notna().sum() == 0 or s.nunique(dropna=True) < 2:
            continue                     # 全空或常量（无法排序）→ 不适用，剔
        cols.append(c)
        used.append(t)
    return cols, used


def main():
    ap = argparse.ArgumentParser(
        description="R3b 权威融合: 固定面板 + median/mean 名次融合 vs 最强单工具 (§3.3)")
    ap.add_argument("--input", default=str(FROZEN_POOLED))
    ap.add_argument("--min_pep", type=int, default=MIN_PEP)
    ap.add_argument("--ctrl", default="peplen")
    ap.add_argument("--patients", default=None,
                    help="逗号分隔目标患者 ID (默认 None=DS2 官方 9 人 [101,102,104-110], 零改动; "
                         "DS1 跨队列复现传 1,2,3,4,5,6)")
    args = ap.parse_args()

    df = load_frozen(args.input)
    pat_list = [int(x) for x in args.patients.split(",")] if args.patients else None
    pats = present_patients(df, patients=pat_list)
    print(f"[info] 表={Path(args.input).name} shape={df.shape}; DS2 患者({len(pats)})={pats}; "
          f"min_pep={args.min_pep}; 权威融合=固定面板+median名次(零挑选)")

    base_col = pool_col(BASELINE_TOOL, "max")
    single_raw = per_patient_spearman(df, base_col, patients=pats, min_pep=args.min_pep)[0]
    single_len = per_patient_partial_spearman(df, base_col, ctrl=args.ctrl,
                                              patients=pats, min_pep=args.min_pep)[0]
    print(f"[基线] 最强单工具 {BASELINE_TOOL}_max: 裸={single_raw:+.4f} 控长={single_len:+.4f}")

    rows = []
    for pname, tools in PANELS.items():
        cols, used = member_cols(df, tools)
        if len(cols) < 2:
            print(f"[warn] 面板 {pname}: 有效成员<2, 跳过")
            continue
        for agg in AGGREGATORS:
            score = apply_fusion(df, cols, method=agg, patients=pats)   # 无监督, 病人内 rank
            f_raw = per_patient_spearman(df, score, patients=pats, min_pep=args.min_pep)[0]
            f_len = per_patient_partial_spearman(df, score, ctrl=args.ctrl,
                                                 patients=pats, min_pep=args.min_pep)[0]
            # 融合 vs 最强单工具 病人配对（裸 + 控长）
            d_raw, p_raw, K = paired_patient_test(df, score, base_col,
                                                  patients=pats, min_pep=args.min_pep)
            d_len, p_len, _ = paired_patient_test(df, score, base_col, ctrl=args.ctrl,
                                                  patients=pats, min_pep=args.min_pep)
            agg_type = "无监督零挑选" if agg in UNSUPERVISED_FUSIONS else "学习型学权重"
            rows.append(dict(
                panel=pname, aggregator=agg, agg_type=agg_type, n_members=len(cols),
                fusion_rho_raw=r6(f_raw, 4), fusion_rho_lenctrl=r6(f_len, 4),
                single_rho_raw=r6(single_raw, 4), single_rho_lenctrl=r6(single_len, 4),
                delta_raw=r6((f_raw - single_raw), 4),
                delta_lenctrl=r6((f_len - single_len), 4),
                paired_p_raw=r6(p_raw, 4), paired_p_lenctrl=r6(p_len, 4),
                n_pat=int(K), members=";".join(used),
            ))
            print(f"  [{pname:14s}·{agg:9s}] n={len(cols):2d} 融合裸={f_raw:+.4f}/控长={f_len:+.4f} "
                  f"| 融合−单工具 裸Δ={f_raw-single_raw:+.4f}(p={p_raw:.3f}) "
                  f"控长Δ={f_len-single_len:+.4f}(p={p_len:.3f})")

    out_df = pd.DataFrame(rows)

    # 聚合小结（median 聚合为权威口径）
    med = out_df[out_df["aggregator"] == "median"]
    def _num(c, frame):
        return pd.to_numeric(frame[c], errors="coerce")
    n_beat = int((_num("delta_lenctrl", med) > 0).sum())
    n_beat_sig = int(((_num("delta_lenctrl", med) > 0) & (_num("paired_p_lenctrl", med) < 0.05)).sum())
    best_med = med.iloc[_num("fusion_rho_lenctrl", med).values.argmax()] if len(med) else None
    summary = dict(
        method="固定面板 + median 名次融合（零成员挑选，无监督无参数，无需嵌套CV）",
        baseline_single=f"{BASELINE_TOOL}_max 裸{single_raw:.4f}/控长{single_len:.4f}",
        n_panels=len(PANELS), aggregators=AGGREGATORS,
        median_panels_beating_single_lenctrl=n_beat,
        median_panels_beating_single_significant=n_beat_sig,
        best_median_panel=(f"{best_med['panel']} 控长 {best_med['fusion_rho_lenctrl']} "
                           f"(Δ {best_med['delta_lenctrl']}, p {best_med['paired_p_lenctrl']})"
                           if best_med is not None else None),
        note=("median/mean 名次融合无监督无参数→固定面板下无选择虚高、无需CV；"
              "所有面板看结果前预先固定；对照 SURV6=旧数据驱动'存活'集，非权威。"
              "n=8 病人功效有限，检不出≠证明无用。"),
    )

    out_dir = ensure_out_dir()
    csv_path = out_dir / "R3b_fusion_authoritative_official.csv"
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("# R3b_fusion_authoritative_official.csv\n")
        f.write("# QuantImmuBench §3.3: 文献权威融合=预先固定面板 + median/mean 名次融合(零成员挑选) vs 最强单工具\n")
        f.write("# 面板看结果前定死; 成员用 <tool>_max(零pooling挑选); median/mean 无监督无参数→无选择虚高、无需嵌套CV\n")
        f.write("# fusion_rho_*=融合 per-patient Spearman(裸/控长); single_rho_*=netMHCpan_BA_max; delta=融合-单工具; paired_p=病人配对符号置换\n")
        f.write("# 规律以 lenctrl(控长)为准; SURV6=旧数据驱动对照(非权威); n=8 功效有限\n")
        out_df.to_csv(f, index=False)
    print(f"\n[saved] {csv_path}  shape={out_df.shape}")
    json_path = out_dir / "R3b_fusion_authoritative_official.summary.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[saved] {json_path}")
    print(f"[聚合·median·控长] {len(med)} 个面板中 打过最强单工具 = {n_beat}; 其中显著 = {n_beat_sig}")
    print("[DONE] R3b")


if __name__ == "__main__":
    main()
