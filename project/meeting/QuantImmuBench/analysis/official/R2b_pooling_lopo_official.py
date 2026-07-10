#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R2b_pooling_lopo_official.py
============================
服务: QuantImmuBench 大纲 §3.2 (pooling) + §2.6 (无泄漏评估协议) —— 给「每工具最优 pooling」
补一套**嵌套留一患者交叉验证 (nested-LOPO)**, 把 R2 的样本内乐观上界换成**留出验证的增益**。

背景 (为何需要):
  R2_best_per_tool.csv 的 best_lenctrl 是**在同一批患者上遍历全 51 变体挑 ρ̄ 最高** = 样本内
  上界 (over-fit pooling, 见 _official_common.best_pooling_for_tool docstring 与 R2 §3.2 B5 注)。
  「换 pooling 涨多少」若报这个数会偏乐观。本脚本做无泄漏版:
    · 外层: 留一位患者当测试;
    · 内层: 只用其余患者选最优 pooling 变体 θ*;
    · 应用 θ* 到留出患者 → 得该患者的 held-out ρ;
    · 跨留出患者等权 Fisher-z 聚合 = 留出验证的 pooling 表现。
  与 R5 对 fusion 整合做的 nested-LOPO 同构, 这里下沉到**单工具 pooling 选择**层。

判据 (每工具, 裸 raw + 控肽长 lenctrl 两口径):
  max_rho          零选择基线 (= R2 的 max, headline)
  oracle_rho       样本内上界 (= R2 的 best, 遍历全变体挑最高)
  lopo_rho         留出验证 (内层选 θ*, 外层测)
  gain_lopo_max    lopo − max   ← ★ 能写进论文的「留出增益」(正=换 pooling 真涨)
  inflation        oracle − lopo ← 样本内挑最优造成的虚高
  paired_p         lopo vs max 病人配对符号置换 p (纯 numpy, 复用口径)
  modal_variant    各折被选最多的变体; member_stability 选它的折比例

口径 (与 R2 逐位对齐, 全部复用 _official_common):
  per-patient Spearman (裸) = per_patient_spearman; 控肽长偏相关 = per_patient_partial_spearman
  (ctrl='peplen'); 跨病人等权 Fisher-z 聚合 = fisherz_weighted_agg(weight='equal')。
  选择的度量与评估的度量一致 (裸口径用裸选裸测, 控长口径用控长选控长测)。
  §3.2 规律以**控肽长口径**为准 (裸口径大 k topk≈mean 会捡回肽长搭便车, R2 §3.2 已注)。

输出 (analysis/official/, 或 QIB_OUTDIR 重定向到 newcut9mer):
  R2b_pooling_lopo_official.csv          每工具一行 (raw+lenctrl 两口径全字段)
  R2b_pooling_lopo_official.summary.json 聚合: 多少工具留出增益>0 / 显著 / 分家族

跑法 (主线跑, 我不跑; 新切口径):
  set QIB_OUTDIR=project/meeting/QuantImmuBench/analysis/official/newcut9mer
  python analysis/official/R2b_pooling_lopo_official.py \
      --input data/frozen/pooled_clean_rerun_9mer.csv --min_pep 8
"""
import sys
import json
import argparse
import itertools
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _official_common import (                              # noqa: E402
    load_frozen, present_patients, per_patient_spearman,
    per_patient_partial_spearman, tool_pooling_cols,
    fisherz_weighted_agg, TOOLS_30, DTU_TOOLS, MIN_PEP,
    FISHER_MIN_N, FISHER_CLIP, FROZEN_POOLED, ensure_out_dir, r6,
)

# 家族归类 (与 R2 一致)
BINDING_TOOLS = {"netMHCpan_BA", "netMHCpan_EL", "netMHCstabpan", "MHCflurry",
                 "MHCnuggets", "MHCseqNet", "TransHLA", "HLAthena"}   # 结合/呈递类


def _family(variant):
    if variant == "max":
        return "max"
    for fam in ("topk", "softmax", "rankdecay"):
        if variant.startswith(fam + "_"):
            return fam
    return "other"


def _agg(rhos, ns):
    """等权 Fisher-z 聚合点估 (与 R2 一致)。"""
    return fisherz_weighted_agg(np.asarray(rhos, float), np.asarray(ns, float),
                                weight="equal")[0]


def variant_perpat(df, tool, cols, pats, min_pep, ctrl):
    """该工具每个 pooling 变体的 per-patient rho 与 n (dict: 变体后缀 -> {pat: rho}, {pat: n})。
    ctrl=None 走裸 Spearman; ctrl='peplen' 走控肽长偏相关。全部复用 _official_common, 口径一致。"""
    rho_by_var, n_by_var = {}, {}
    for col in cols:
        var = col[len(tool) + 1:]
        if df[col].notna().sum() == 0:
            rho_by_var[var] = {p: np.nan for p in pats}
            n_by_var[var] = {p: 0 for p in pats}
            continue
        if ctrl is None:
            *_, rbp, nbp = per_patient_spearman(
                df, col, patients=pats, min_pep=min_pep, return_perpat=True)
        else:
            *_, rbp, nbp = per_patient_partial_spearman(
                df, col, ctrl=ctrl, patients=pats, min_pep=min_pep, return_perpat=True)
        rho_by_var[var] = rbp
        n_by_var[var] = nbp
    return rho_by_var, n_by_var


def _valid(rho, n):
    return (rho is not None) and (not np.isnan(rho)) and (n > FISHER_MIN_N)


def nested_lopo(rho_by_var, n_by_var, eff_pats):
    """外层留一 eff_pats 中每位患者; 内层用其余患者 (仅 eff) 选样本内最优变体; 应用到留出患者。
    返回 (lopo_rho_by_pat, lopo_n_by_pat, selected_by_fold: dict pat->变体)。
    选择资格: 变体须在**全部训练患者**上都有有效 rho (n>FISHER_MIN_N), 保证选择公平、可迁移。"""
    variants = list(rho_by_var.keys())
    lopo_rho, lopo_n, selected = {}, {}, {}
    for p in eff_pats:
        train = [q for q in eff_pats if q != p]
        best_var, best_agg = None, -np.inf
        for v in variants:
            rbp, nbp = rho_by_var[v], n_by_var[v]
            if not all(_valid(rbp.get(q, np.nan), nbp.get(q, 0)) for q in train):
                continue                      # 训练折里有患者该变体无效 → 不参与选择
            a = _agg([rbp[q] for q in train], [nbp[q] for q in train])
            if a is not None and not np.isnan(a) and a > best_agg:
                best_agg, best_var = a, v
        if best_var is None:                  # 兜底: 无合格变体 → 退回 max
            best_var = "max" if "max" in rho_by_var else variants[0]
        selected[p] = best_var
        lopo_rho[p] = rho_by_var[best_var].get(p, np.nan)     # 留出患者用所选变体的 rho
        lopo_n[p] = n_by_var[best_var].get(p, 0)
    return lopo_rho, lopo_n, selected


def paired_from_rhos(rho_a, rho_b, n_a, n_b, pats):
    """两法 per-patient rho 的病人配对符号置换检验 (Fisher-z 差, 纯 numpy 双侧; K<=20 精确枚举)。
    复用 _official_common.paired_patient_test 的核心逻辑, 但直接吃 per-patient rho dict
    (LOPO 每折选不同变体, 无单一 score 列)。返回 (delta_zbar, p, K)。"""
    diffs = []
    for p in pats:
        va, vb = rho_a.get(p, np.nan), rho_b.get(p, np.nan)
        if np.isnan(va) or np.isnan(vb):
            continue
        if n_a.get(p, 0) <= FISHER_MIN_N or n_b.get(p, 0) <= FISHER_MIN_N:
            continue
        za = np.arctanh(np.clip(va, -FISHER_CLIP, FISHER_CLIP))
        zb = np.arctanh(np.clip(vb, -FISHER_CLIP, FISHER_CLIP))
        diffs.append(za - zb)
    diffs = np.asarray(diffs, float)
    K = len(diffs)
    if K == 0:
        return np.nan, np.nan, 0
    observed = float(diffs.mean())
    if K <= 20:
        signs = np.array(list(itertools.product([1.0, -1.0], repeat=K)))
        perm = (signs * diffs[np.newaxis, :]).mean(axis=1)
    else:
        rng = np.random.default_rng(42)
        signs = rng.choice(np.array([1.0, -1.0]), size=(10000, K))
        perm = (signs * diffs[np.newaxis, :]).mean(axis=1)
    p = float(np.mean(np.abs(perm) >= np.abs(observed) - 1e-12))
    return observed, p, K


def run_caliber(df, tool, cols, pats, min_pep, ctrl):
    """跑单个口径 (ctrl=None 裸 / 'peplen' 控长), 返回该工具该口径的全部判据 dict。"""
    rho_by_var, n_by_var = variant_perpat(df, tool, cols, pats, min_pep, ctrl)
    # 有效患者 = max 变体有有效 rho 的患者 (基线与比较的公共病人集)
    rho_max = rho_by_var.get("max", {})
    n_max = n_by_var.get("max", {})
    eff = [p for p in pats if _valid(rho_max.get(p, np.nan), n_max.get(p, 0))]
    if len(eff) < 3:
        return None
    # 零选择 max 基线
    max_rho = _agg([rho_max[p] for p in eff], [n_max[p] for p in eff])
    # 样本内上界 oracle (全 eff 上遍历全变体挑聚合最高)
    oracle_rho, oracle_var = -np.inf, None
    for v, rbp in rho_by_var.items():
        nbp = n_by_var[v]
        vals = [(rbp.get(p, np.nan), nbp.get(p, 0)) for p in eff]
        if not all(_valid(r, n) for r, n in vals):
            continue
        a = _agg([r for r, _ in vals], [n for _, n in vals])
        if a is not None and not np.isnan(a) and a > oracle_rho:
            oracle_rho, oracle_var = a, v
    if oracle_var is None:
        oracle_rho, oracle_var = max_rho, "max"
    # 留出验证 nested-LOPO
    lopo_rho_bp, lopo_n_bp, selected = nested_lopo(rho_by_var, n_by_var, eff)
    lopo_rho = _agg([lopo_rho_bp[p] for p in eff if not np.isnan(lopo_rho_bp[p])],
                    [lopo_n_bp[p] for p in eff if not np.isnan(lopo_rho_bp[p])])
    # 配对显著: lopo vs max
    delta, pval, K = paired_from_rhos(lopo_rho_bp, rho_max, lopo_n_bp, n_max, eff)
    # modal 变体 + 稳定度
    sel_vals = list(selected.values())
    modal = max(set(sel_vals), key=sel_vals.count) if sel_vals else "max"
    stability = sel_vals.count(modal) / len(sel_vals) if sel_vals else np.nan
    return dict(
        n_pat=len(eff),
        max_rho=max_rho, oracle_rho=oracle_rho, oracle_var=oracle_var,
        lopo_rho=lopo_rho, gain_lopo_max=(lopo_rho - max_rho),
        inflation=(oracle_rho - lopo_rho), paired_p=pval, paired_delta_z=delta,
        modal_variant=modal, modal_family=_family(modal), member_stability=stability,
    )


def main():
    ap = argparse.ArgumentParser(
        description="R2b: 每工具 pooling 选择的 nested-LOPO 留出验证 (§3.2 无泄漏版)")
    ap.add_argument("--input", default=str(FROZEN_POOLED))
    ap.add_argument("--min_pep", type=int, default=MIN_PEP)
    ap.add_argument("--ctrl", default="peplen")
    args = ap.parse_args()

    df = load_frozen(args.input)
    pats = present_patients(df)
    print(f"[info] 表={Path(args.input).name} shape={df.shape}; DS2 患者({len(pats)})={pats}; "
          f"min_pep={args.min_pep}; nested-LOPO pooling 留出验证")

    rows = []
    for tool in TOOLS_30:
        cols = tool_pooling_cols(df, tool)
        if not cols:
            continue                          # 该表无此工具 (如 NeoaPred 已剔) → 跳过
        is_dtu = tool in DTU_TOOLS
        raw = run_caliber(df, tool, cols, pats, args.min_pep, ctrl=None)
        lenc = run_caliber(df, tool, cols, pats, args.min_pep, ctrl=args.ctrl)
        if raw is None and lenc is None:
            continue
        row = dict(Tool=tool, pending_DTU=is_dtu,
                   binding_class=(tool in BINDING_TOOLS),
                   n_pat=(lenc or raw)["n_pat"])
        for tag, res in (("raw", raw), ("lenctrl", lenc)):
            if res is None:
                continue
            row.update({
                f"max_rho_{tag}": r6(res["max_rho"], 4),
                f"oracle_rho_{tag}": r6(res["oracle_rho"], 4),
                f"lopo_rho_{tag}": r6(res["lopo_rho"], 4),
                f"gain_lopo_max_{tag}": r6(res["gain_lopo_max"], 4),
                f"inflation_{tag}": r6(res["inflation"], 4),
                f"paired_p_{tag}": r6(res["paired_p"], 4),
                f"modal_variant_{tag}": res["modal_variant"],
                f"modal_family_{tag}": res["modal_family"],
                f"member_stability_{tag}": r6(res["member_stability"], 3),
            })
        rows.append(row)
        g = row.get("gain_lopo_max_lenctrl", np.nan)
        infl = row.get("inflation_lenctrl", np.nan)
        print(f"  {tool:15s} [控长] max={row.get('max_rho_lenctrl'):+.3f} "
              f"oracle={row.get('oracle_rho_lenctrl'):+.3f} lopo={row.get('lopo_rho_lenctrl'):+.3f} "
              f"→ 留出增益={g:+.3f} 虚高={infl:+.3f} p={row.get('paired_p_lenctrl')} "
              f"选[{row.get('modal_variant_lenctrl')}·{row.get('member_stability_lenctrl')}]")

    out_df = pd.DataFrame(rows).sort_values("gain_lopo_max_lenctrl",
                                            ascending=False, na_position="last")

    # ── 聚合统计 (控长口径为准) ──────────────────────────────────────────────────
    def _col(c):
        return pd.to_numeric(out_df[c], errors="coerce") if c in out_df else pd.Series(dtype=float)
    g_len = _col("gain_lopo_max_lenctrl")
    p_len = _col("paired_p_lenctrl")
    infl_len = _col("inflation_lenctrl")
    n_tools = len(out_df)
    n_gain_pos = int((g_len > 0).sum())
    n_gain_sig = int(((g_len > 0) & (p_len < 0.05)).sum())
    n_loss_sig = int(((g_len < 0) & (p_len < 0.05)).sum())
    bind = out_df[out_df["binding_class"] == True]  # noqa: E712
    bind_gain_pos = int((pd.to_numeric(bind.get("gain_lopo_max_lenctrl"), errors="coerce") > 0).sum()) if len(bind) else 0
    summary = dict(
        caliber_primary="lenctrl(控肽长)",
        n_tools=n_tools,
        n_tools_holdout_gain_positive=n_gain_pos,
        n_tools_holdout_gain_significant=n_gain_sig,
        n_tools_holdout_loss_significant=n_loss_sig,
        median_holdout_gain=r6(float(np.nanmedian(g_len)) if len(g_len) else np.nan, 4),
        median_inflation=r6(float(np.nanmedian(infl_len)) if len(infl_len) else np.nan, 4),
        binding_class_n=int(len(bind)),
        binding_class_holdout_gain_positive=bind_gain_pos,
        note=("留出增益=内层选最优 pooling 再外层测 − 零选择 max; >0 且 p<0.05 才是"
              "统计站得住的「换 pooling 真涨」。样本内 oracle 与 lopo 之差=选择虚高。"
              "n_pat 见各行, 8 病人下功效有限, 检不出≠证明无用。"),
    )

    out_dir = ensure_out_dir()
    csv_path = out_dir / "R2b_pooling_lopo_official.csv"
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("# R2b_pooling_lopo_official.csv\n")
        f.write("# QuantImmuBench §3.2+§2.6: 每工具 pooling 选择的 nested-LOPO 留出验证 (R2 的无泄漏版)\n")
        f.write("# 外层留一患者测, 内层用其余患者选样本内最优 pooling 变体, 应用到留出患者。裸(raw)+控肽长(lenctrl)两口径。\n")
        f.write("# max_rho=零选择基线(R2 headline); oracle_rho=样本内上界(R2 best, 遍历全变体挑最高); lopo_rho=留出验证\n")
        f.write("# gain_lopo_max=lopo-max(★留出增益, 正=换pooling真涨); inflation=oracle-lopo(样本内挑最优虚高); paired_p=lopo vs max 病人配对符号置换\n")
        f.write("# 规律以 lenctrl(控肽长)口径为准; 8 病人功效有限, 检不出≠证明无用。\n")
        out_df.to_csv(f, index=False)
    print(f"\n[saved] {csv_path}  shape={out_df.shape}")

    json_path = out_dir / "R2b_pooling_lopo_official.summary.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[saved] {json_path}")
    print(f"[聚合·控长] {n_tools} 工具中 留出增益>0 = {n_gain_pos}; 其中显著(p<0.05) = {n_gain_sig}; "
          f"显著变差 = {n_loss_sig}; 结合类 {len(bind)} 中留出增益>0 = {bind_gain_pos}")
    print("[DONE] R2b")


if __name__ == "__main__":
    main()
