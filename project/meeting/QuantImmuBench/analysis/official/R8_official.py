#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R8_official.py
==============
服务: QuantImmuBench 大纲 §3.4 (图4 / 表10) —— 全方法统一排名 + 部署建议。
对应大纲: paper/QuanImmu-Paper-Outline.md §3.4。

★ 2026-07-01 Part D Phase 3b 干净口径 (见 04_LOG):
  · 输入 = 干净表 pooled_clean_9mer.csv (含 peplen)。
  · [B5 零选择] 单工具/维度一律 <tool>_max (去 in-sample pooling selection); 旧 best_pooling_for_tool 已弃。
  · [B2 控肽长] 排名表新增 rho_bar_lenctrl 列 (per_patient_partial_spearman ctrl='peplen')。
  · [稀疏 + 肽长伪迹双 flag] 不入部署候选:
      - coverage_flag=sparse: per-patient 仅 2-3 肽算 Spearman → 虚高 (Seq2Neo/netMHCstabpan/NeoaPred)。
      - length_artifact_flag: 控肽长后掉幅 >0.15 → 排名含肽长效应 (预期 HLAthena/andy90), 全覆盖也不入部署。
  · 方案A netAffneg = 表内列 netMHCpan_BA_topk_k20_a0 (干净表已含 51 变体, 不再读外部派生 CSV)。
  · 方案B = dim7 geomean (max 维, 无监督 leak-free)。
  · 部署实例 T01/T04 仍 TODO 无数据 (冻结表纯 DS2 9 患者, 不造假数据)。

做什么 (因 §3.3.5 统计持平 → 把「持平」转成可操作部署结论):
  · 统一排名表 (表10): 所有候选方法放一张表按 per-patient Fisher-z ρ̄ 排名:
      - 30 单工具 (零选择 <tool>_max; 全覆盖=full / 稀疏=sparse; 控肽长掉幅>0.15 标 length_artifact)。
      - 8 无监督 fusion × 2 维度集 (SURV6 / dim7, max 维), method 列标 dim_set。
      每行: method, family, dim_set, pooling, rho_bar, rho_bar_lenctrl, ci_lo, ci_hi, n_used,
            coverage_flag, length_artifact_flag, overfit_flag, pending_DTU, deploy_candidate。
  · 部署建议 (写进 summary.json + csv 注释, 数字全部引用本脚本算出的 ρ̄, 不自创):
      - 方案A 务实默认 = netAffneg = netMHCpan_BA 9mer topk(k=20,α=0) 表内列 (零学习/单工具/依赖最少/DTU 需同意)。
      - 方案B 按需备选 = dim7 geomean fusion (多维、无监督 leak-free)。
      报告两方案 ρ̄ + 依赖工具数 + overfit 状态对比。
  · 部署实例 rank_T01_deploy: outline 要对无标签病人 T01/T04 排序 → 查冻结表有无该数据,
    没有则 summary 标 TODO, 不造假数据。

输入 (只读干净表):
  data/frozen/pooled_clean_9mer.csv   (主分析冻结表, 9mer, 含 51 pooling 变体, 经 FROZEN_POOLED)
输出 (analysis/official/):
  R8_unified_ranking_official.csv       —— 表10 全方法统一排名 (单工具 + netAffneg 方案A + fusion, 按 ρ̄ 排序)
  R8_deployment_official.summary.json   —— 两方案对比 + length_artifact 清单 + 部署实例状态

复用旧骨架:
  · 8 无监督 fusion / per-patient Fisher-z → _official_common (apply_fusion / per_patient_spearman)
  · 控肽长偏相关 (B2) → per_patient_partial_spearman
  · 学习型 (ridge/gbdt/stacking/constrained) 因 overfit_risk 不入部署候选, 本表只列无监督 fusion。

★ selection 已裁决 (2026-07-01, 用户拍板对齐 outline §2.2 9mer 主分析):
  · DS2 口径 = 130 肽 / 9 患者 (官方数据红线, Entry31 已拍)。
  · 维度集 SURV6 / dim7 成员 = 保持现状 (outline 抽象「6/7维」既有具体化, 朱同学传承)。
  · 方案A netAffneg = netMHCpan_BA_topk_k20_a0 (outline §3.2/§3.4 硬指定, 干净表内列)。
  · 全覆盖池门槛 = 保持 (outline §3.1 领先单工具皆全覆盖)。
  · 仅 DTU consent 保留为外部 pending (法律授权, 非写作阻塞)。

跑法 (主线跑, 我不跑):
  python analysis/official/R8_official.py
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
    per_patient_partial_spearman, apply_fusion, pool_col, DTU_TOOLS,
    TOOLS_30, MIN_PEP, FROZEN_POOLED, ensure_out_dir,
)

# ── 维度集 (已裁决: 保持现状=outline 抽象「6/7维」既有具体化, 朱同学传承) ──────────
SURV6 = ["PredIG", "IMPROVE", "pTuneos", "PRIME", "ImmuneApp", "deepHLApan"]
AFFINITY_PROXY = "netMHCpan_BA"          # dim7 第7维 (max 维)
DIM7_TOOLS = list(SURV6) + [AFFINITY_PROXY]

# ── 方案A netAffneg (outline §3.2/§3.4 = netMHCpan_BA 9mer topk k=20,α=0, 干净表内列) ──
NETAFF_COL = "netMHCpan_BA_topk_k20_a0"
NETAFF_METHOD = "netMHCpan_BA_topk_k20_a0"
UNSUP_8 = ["mean_rank", "geomean", "median", "powmean",
           "max", "min", "weighted_mean_rank", "softmax_rank"]

# 控肽长掉幅阈值: rho_bar_raw - rho_bar_lenctrl > 此值 → 排名含肽长效应, 不入部署候选
LEN_ARTIFACT_DROP = 0.15
# 部署实例目标 (outline 指定的无标签病人)
DEPLOY_TARGET_PATIENTS = ["T01", "T04"]


def _r(v, d=6):
    return round(float(v), d) if v is not None and not np.isnan(v) else np.nan


def build_dim_cols(df, tools):
    """[B5 零选择] 一组工具各取 <tool>_max 列; 返回 (cols, used_labels)。缺列剔除。"""
    cols, used = [], []
    for t in tools:
        col = pool_col(t, "max")
        if col not in df.columns or df[col].notna().sum() == 0:
            print(f"[warn] {t}: 列 {col} 缺失或全空, 剔除")
            continue
        cols.append(col)
        used.append(f"{t}_max")
    return cols, used


def _len_drop(rb, rb_len):
    """裸 - 控肽长 掉幅 (两者均有效才算, 否则 NaN)。"""
    if rb is None or rb_len is None or np.isnan(rb) or np.isnan(rb_len):
        return np.nan
    return float(rb - rb_len)


def main():
    ap = argparse.ArgumentParser(
        description="R8 官方: 全方法统一 排名 + 部署建议 (§3.4 图4/表10)")
    ap.add_argument("--input", default=str(FROZEN_POOLED), help="干净肽级表路径")
    ap.add_argument("--min_pep", type=int, default=MIN_PEP)
    ap.add_argument("--ctrl", default="peplen", help="控制变量列 (B2 偏相关, 默认 peplen)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    df = load_frozen(args.input)
    pats = present_patients(df)
    n_rows = len(df)
    print(f"[info] 干净表 {df.shape}; DS2 患者({len(pats)})={pats}; min_pep={args.min_pep}; "
          f"ctrl={args.ctrl}")

    rows = []
    length_artifact_tools = []   # 收集被标肽长效应的工具, 写 summary

    # ── 30 单工具 (零选择 <tool>_max; full/sparse + length_artifact 双 flag) ─────────
    for t in TOOLS_30:
        col = pool_col(t, "max")
        if col not in df.columns or df[col].notna().sum() == 0:
            print(f"[warn] 单工具 {t}: 列 {col} 缺失或全空, 跳过")
            continue
        rb, lo, hi, nu, nd = per_patient_spearman(
            df, col, patients=pats, min_pep=args.min_pep)
        rb_len, _, _, _, _ = per_patient_partial_spearman(
            df, col, ctrl=args.ctrl, patients=pats, min_pep=args.min_pep)
        full_cov = int(df[col].notna().sum()) == n_rows
        cov_flag = "full" if full_cov else "sparse"
        drop = _len_drop(rb, rb_len)
        # 全覆盖但控肽长后掉幅>0.15 → 排名含肽长效应 (稀疏工具本就不入部署, 不重复标)
        length_artifact = bool(full_cov and not np.isnan(drop) and drop > LEN_ARTIFACT_DROP)
        len_flag = "length_artifact" if length_artifact else "none"
        if length_artifact:
            length_artifact_tools.append(dict(tool=f"{t}_max", rho_bar=_r(rb),
                                              rho_bar_lenctrl=_r(rb_len), drop=_r(drop, 4)))
        rows.append(dict(
            method=f"{t}_max", family="single_tool", dim_set="-", pooling="max",
            rho_bar=_r(rb), rho_bar_lenctrl=_r(rb_len), ci_lo=_r(lo), ci_hi=_r(hi),
            n_used=int(nu), coverage_flag=cov_flag, length_artifact_flag=len_flag,
            overfit_flag="none", pending_DTU=t in DTU_TOOLS,
            # 稀疏(per-patient 虚高) 或 含肽长效应 → 不入部署候选
            deploy_candidate=bool(full_cov and not length_artifact)))

    # ── 方案A: netAffneg = netMHCpan_BA_topk_k20_a0 (outline §3.2/§3.4, 表内列) ──────
    netaff_present = NETAFF_COL in df.columns and bool(df[NETAFF_COL].notna().any())
    if netaff_present:
        na_full = int(df[NETAFF_COL].notna().sum()) == n_rows
        na_rb, na_lo, na_hi, na_nu, _ = per_patient_spearman(
            df, NETAFF_COL, patients=pats, min_pep=args.min_pep)
        na_rb_len, _, _, _, _ = per_patient_partial_spearman(
            df, NETAFF_COL, ctrl=args.ctrl, patients=pats, min_pep=args.min_pep)
        na_drop = _len_drop(na_rb, na_rb_len)
        na_artifact = bool(na_full and not np.isnan(na_drop) and na_drop > LEN_ARTIFACT_DROP)
        rows.append(dict(
            method=NETAFF_METHOD, family="single_tool", dim_set="affinity_default",
            pooling="topk_k20_a0",
            rho_bar=_r(na_rb), rho_bar_lenctrl=_r(na_rb_len), ci_lo=_r(na_lo),
            ci_hi=_r(na_hi), n_used=int(na_nu),
            coverage_flag="full" if na_full else "sparse",
            length_artifact_flag="length_artifact" if na_artifact else "none",
            overfit_flag="none", pending_DTU=AFFINITY_PROXY in DTU_TOOLS,
            deploy_candidate=bool(na_full and not na_artifact)))     # outline 方案A 务实默认
        print(f"[info] 方案A netAffneg {NETAFF_METHOD} ρ̄={_r(na_rb)} "
              f"lenctrl={_r(na_rb_len)} CI=[{_r(na_lo)},{_r(na_hi)}] n_pat={na_nu}")
    else:
        na_rb = na_rb_len = na_lo = na_hi = np.nan
        na_nu = 0
        print(f"[warn] 方案A netAffneg 列 {NETAFF_COL} 缺失, 排名表不含该行, summary 标 pending")

    # ── 8 无监督 fusion × 2 维度集 (SURV6 / dim7, max 维) ────────────────────────
    fusion_rho = {}   # (dim_name, method) -> rho_bar, 供部署方案引用
    dim_used = {}
    for dim_name, tools in [("SURV6", SURV6), ("dim7", DIM7_TOOLS)]:
        dim_cols, used = build_dim_cols(df, tools)
        dim_used[dim_name] = used
        for method in UNSUP_8:
            s = apply_fusion(df, dim_cols, method, patients=pats, seed=args.seed)
            s_arr = np.asarray(s.values, dtype=float)
            rb, lo, hi, nu, nd = per_patient_spearman(
                df, s_arr, patients=pats, min_pep=args.min_pep)
            rb_len, _, _, _, _ = per_patient_partial_spearman(
                df, s_arr, ctrl=args.ctrl, patients=pats, min_pep=args.min_pep)
            fusion_rho[(dim_name, method)] = rb
            overfit = ("weighted_leak_free"
                       if method in {"weighted_mean_rank", "softmax_rank"}
                       else "leak_free")
            rows.append(dict(
                method=method, family="fusion", dim_set=dim_name, pooling="rankfuse",
                rho_bar=_r(rb), rho_bar_lenctrl=_r(rb_len), ci_lo=_r(lo), ci_hi=_r(hi),
                n_used=int(nu), coverage_flag="full", length_artifact_flag="none",
                overfit_flag=overfit, pending_DTU=any(t in DTU_TOOLS for t in tools),
                deploy_candidate=(method == "geomean")))

    # ── 排名 (按 rho_bar 降序) ──────────────────────────────────────────────────
    rank_df = pd.DataFrame(rows).sort_values(
        "rho_bar", ascending=False, na_position="last").reset_index(drop=True)
    rank_df.insert(0, "rank", np.arange(1, len(rank_df) + 1))

    out_dir = ensure_out_dir()
    out_csv = out_dir / "R8_unified_ranking_official.csv"
    with open(out_csv, "w", encoding="utf-8") as f:
        f.write("# R8_unified_ranking_official.csv\n")
        f.write("# QuantImmuBench §3.4 表10: 全方法统一 per-patient Fisher-z ρ̄ 排名 (干净口径, 零选择 max)\n")
        f.write(f"# 输入={Path(args.input).name} (9mer 主分析); DS2 患者={pats}\n")
        f.write(f"# SURV6={dim_used.get('SURV6')}; dim7={dim_used.get('dim7')} (已裁决: 保持现状具体化, max 维)\n")
        f.write(f"# 方案A(outline §3.2/§3.4)={NETAFF_METHOD} dim_set=affinity_default (表内列)\n")
        f.write("# rho_bar=裸 per-patient Fisher-z; rho_bar_lenctrl=控肽长偏相关(B2, ctrl=peplen)\n")
        f.write("# family=single_tool/fusion; coverage_flag=full/sparse(稀疏 per-patient 虚高,不入部署)\n")
        f.write(f"# length_artifact_flag=length_artifact 表示控肽长后掉幅>{LEN_ARTIFACT_DROP}(排名含肽长效应, 预期 HLAthena/andy90, 全覆盖也不入部署)\n")
        f.write("# overfit_flag=leak_free/none(本表只含无监督, 学习型因 overfit_risk 已排除部署候选)\n")
        f.write("# deploy_candidate=True 才进部署方案; pending_DTU=DTU 受限工具(部署需同意)\n")
        rank_df.to_csv(f, index=False)
    print(f"[saved] {out_csv}  ({len(rank_df)} 行)")

    # ── 部署方案 A: netAffneg = netMHCpan_BA_topk_k20_a0 (outline §3.2/§3.4) ─────────
    scheme_a = {
        "name": "务实默认 (outline 方案A: netAffneg = netMHCpan_BA 9mer topk k=20,α=0)",
        "method": NETAFF_METHOD,
        "n_tools": 1,
        "fisherz_rho": _r(na_rb), "fisherz_rho_lenctrl": _r(na_rb_len),
        "ci_lo": _r(na_lo), "ci_hi": _r(na_hi), "n_used": int(na_nu),
        "overfit": "none (零学习, 单工具, 依赖最少)",
        "pending_DTU": AFFINITY_PROXY in DTU_TOOLS,
        "decision": ("已按 outline §3.2/§3.4 裁决: netAffneg = 干净表内列 netMHCpan_BA_topk_k20_a0; "
                     "直接算 per-patient Fisher-z, 不再读外部派生 CSV"),
        "available": bool(netaff_present),
    }

    # ── 部署方案 B: dim7 geomean fusion (max 维; SURV6 一并报参考) ──────────────────
    scheme_b = {
        "name": "按需备选 (multi-dim max + geomean, 无监督 leak-free)",
        "dim7_geomean": {
            "n_tools": len(dim_used.get("dim7", [])),
            "dims": dim_used.get("dim7"),
            "fisherz_rho": _r(fusion_rho.get(("dim7", "geomean"))),
        },
        "SURV6_geomean_ref": {
            "n_tools": len(dim_used.get("SURV6", [])),
            "dims": dim_used.get("SURV6"),
            "fisherz_rho": _r(fusion_rho.get(("SURV6", "geomean"))),
        },
        "overfit": "none (无监督 rank fusion, leak-free)",
        "decision": "已裁决: 维度集成员 SURV6/dim7=保持现状 (outline 抽象「6/7维」既有具体化, max 维), 方案B 主推 dim7 geomean",
    }

    # ── 部署实例 rank_T01_deploy: 查冻结表有无 T01/T04 无标签病人数据 ─────────────
    present_ids = set(str(x) for x in df["Patient_ID"].astype(str).unique())
    target_found = [p for p in DEPLOY_TARGET_PATIENTS if p in present_ids]
    if target_found:
        deploy_status = f"AVAILABLE — 冻结表含 {target_found}, 可跑 rank_T01_deploy (需补实现打分导出)"
    else:
        deploy_status = ("TODO — T01/T04 无标签病人数据不在冻结表 (冻结表纯 DS2 9 患者), "
                         "需数据组提供后跑 rank_T01_deploy; 本脚本不造假数据")
    print(f"[deploy] 部署实例状态: {deploy_status}")

    print(f"\n[方案A] {scheme_a['method']} ρ̄={scheme_a['fisherz_rho']} (1 工具, 零学习)")
    print(f"[方案B] dim7 geomean ρ̄={scheme_b['dim7_geomean']['fisherz_rho']} "
          f"({scheme_b['dim7_geomean']['n_tools']} 工具) / "
          f"SURV6 geomean ρ̄={scheme_b['SURV6_geomean_ref']['fisherz_rho']} "
          f"({scheme_b['SURV6_geomean_ref']['n_tools']} 工具)")
    if length_artifact_tools:
        print(f"[length_artifact] 控肽长掉幅>{LEN_ARTIFACT_DROP} 的工具(排名含肽长效应, 不入部署): "
              f"{[x['tool'] for x in length_artifact_tools]}")

    summary = {
        "section": "§3.4 unified ranking + deployment recommendation (干净口径, 零选择 max)",
        "input": Path(args.input).name,
        "patients": pats,
        "dim_sets_decision": "已裁决: SURV6/dim7 成员=保持现状 (outline 抽象「6/7维」既有具体化, max 维)",
        "netAffneg_available": bool(netaff_present),
        "dim_used": dim_used,
        "n_methods_ranked": int(len(rank_df)),
        "length_artifact_threshold": LEN_ARTIFACT_DROP,
        "length_artifact_tools": length_artifact_tools,
        "top5_by_rho": rank_df.head(5)[
            ["rank", "method", "family", "dim_set", "rho_bar", "rho_bar_lenctrl",
             "coverage_flag", "length_artifact_flag", "deploy_candidate"]].to_dict(orient="records"),
        "deployment_scheme_A": scheme_a,
        "deployment_scheme_B": scheme_b,
        "deployment_note": ("因 §3.3.5 整合 vs 最强单工具统计持平, 部署按 "
                            "'零过拟合+依赖最少+鲁棒+可解释' 排序; 稀疏(虚高) 与 length_artifact(含肽长效应) "
                            "均不入部署候选; 两方案 ρ̄ 见上, 数字均为本脚本实测"),
        "deploy_instance_status": deploy_status,
        "deploy_target_patients": DEPLOY_TARGET_PATIENTS,
        "learning_fusion_excluded": ("ridge/gbdt/stacking/constrained 因 overfit_risk "
                                     "不入部署候选 (证据见 R5 nested-LOPO)"),
        "seed": args.seed,
    }
    out_json = out_dir / "R8_deployment_official.summary.json"

    def _jd(o):
        if isinstance(o, np.integer): return int(o)
        if isinstance(o, np.floating): return float(o)
        if isinstance(o, (np.bool_,)): return bool(o)
        return str(o)

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=_jd)
    print(f"[saved] {out_json}")
    print("[DONE] R8")


if __name__ == "__main__":
    main()
