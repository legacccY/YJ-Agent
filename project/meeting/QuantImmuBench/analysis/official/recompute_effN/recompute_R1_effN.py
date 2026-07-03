#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recompute_R1_effN.py
====================
服务: QuantImmuBench §3.1 图1 (30 工具 max-pool per-patient Spearman 基线) 的 **修正重算**。
lever = 单工具 <tool>_max per-patient Spearman (零选择 headline)。

━━━ 修的是什么 (bug 已由 verifier+analyst+主线三方坐实) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
canonical R1_single_maxpool_official.csv 的 fisherz_rho_raw 用 _official_common.per_patient_spearman:
  · 逐患者 spearman_np(<tool>_max, Elispot); spearman_np 内部 ~(isnan|isnan) 去 NaN, rho 只在
    有效非 NaN 点上算 —— 这一步没错。
  · 【bug】门槛 (MIN_PEP=3) 与聚合剔除 (fisherz_weighted_agg 的 keep = ns > FISHER_MIN_N=3)
    用的 n = len(g) = 患者总行数 (8-19), 不是有效非 NaN 点数 effN。
  · 后果: 某工具在某患者只覆盖 2-3 条肽 (effN=2-3), rho 极易撞 ±1, 但 len(g)>3 让它逃过门槛,
    clip 0.9999 → arctanh≈4.95 强力拉高等权 Fisher-z 均值。榜首 HLAthena/andy90/Seq2Neo 皆此撑起。

━━━ 本脚本的修正 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  · effN = 该患者 <tool>_max 与 Elispot **同时非 NaN 的点数** (不是 len(g))。
  · 门槛改用 effN: 只有 effN >= EFFN_MIN 的患者 rho 进聚合 (EFFN_MIN 参数化, 主版 10, 敏感性 8/5, 对照 3)。
    ★ 2026-07-03 用户拍板: 主门槛 5→10 (更干净, 剔更多低覆盖患者); 聚合仍 Fisher-z 等权不变。
  · 聚合口径与原**逐位一致**: 等权 Fisher-z (clip ±0.9999 → arctanh → 均值 → tanh)。唯一变的是
    「哪些患者进聚合由 effN 门槛决定」。rho 本身仍复用 canonical spearman_np, 保证与原 bit 可比。
  · CI: cluster-bootstrap over patients (重采样通过门槛的患者, n_boot=2000, seed=42, 2.5/97.5 分位)。
  · coverage_fail = (n_full < 3): 9 患者里通过门槛不足 3 个 → 不该进主排序 (如 Seq2Neo/netMHCstabpan)。

输出 (analysis/official/recompute_effN/, 脚本自建目录, 绝不碰 canonical R1_* / data/):
  · R1_recomputed_effN10.csv  —— 主版 (EFFN_MIN=10)
  · R1_recomputed_effN8.csv   —— 敏感性中档 (EFFN_MIN=8)
  · R1_recomputed_effN5.csv   —— 敏感性低档 (EFFN_MIN=5, 原主版)
  · R1_recomputed_effN3.csv   —— 对照版 (EFFN_MIN=3)
  · R1_effN_sensitivity_5_8_10.csv —— 5/8/10 三档 rho/rank/n_full 并排 (看排名随门槛翻转否)
  · R1_compare_orig_vs_effN.csv —— 原 (canonical fisherz_rho_raw) vs 新 (effN10) 谁掉/谁升

Windows 规范: UTF-8 stdout, pathlib, 纯 numpy/pandas + canonical 纯 numpy spearman_np (禁 scipy.stats,
  防 OMP #15), __main__ 守卫。★ 本脚本不自跑, 主线跑 (见文件尾 CLI 说明)。
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# Windows 必要: UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent                  # analysis/official/recompute_effN/
OFFICIAL = HERE.parent                                  # analysis/official/
ROOT = OFFICIAL.parent.parent                           # QuantImmuBench/ (项目根, 供 --input 相对路径解析)
sys.path.insert(0, str(OFFICIAL))

# 复用 canonical 口径常量 + 纯 numpy Spearman (rho 逐位可比, 只改门槛)。
from _official_common import (                          # noqa: E402
    TOOLS_30, DTU_TOOLS, DS2_PATIENTS, FROZEN_POOLED, FISHER_CLIP,
    spearman_np, load_frozen,
)

CANON_R1 = OFFICIAL / "R1_single_maxpool_official.csv"   # canonical (只读, 取 fisherz_rho_raw)
OUT_DIR = HERE

N_BOOT = 2000
BOOT_SEED = 42

# 输出文件名 tag: 空=9mer 主口径 (维持现有无前缀命名不变); 非空 (如 "8to11mer") 则插入所有产物名。
TAG = ""
INPUT_NAME = "pooled_clean_9mer.csv"                     # 输入表名 (main 里按 --input 覆写, 供 header 口径标注)


def _tag_seg():
    """TAG 非空 -> '_<TAG>' (供拼进文件名); 空 -> '' (原名完全不变)。"""
    return f"_{TAG}" if TAG else ""

# 本地 clip 常量: 防 Fisher-z 在 rho→±1 发散 (arctanh 爆). canonical FISHER_CLIP=0.9999 太贴边,
# effN>=10 主门槛下各患者 rho 温和 (不再是 2-3 点凑的 ±1 伪迹), 此收紧到 0.99 不影响主结果,
# 仅对残留极端 rho 加固数值稳定性。★ 聚合口径仍 Fisher-z 等权, 只改截断阈值不改算法。
LOCAL_CLIP = 0.99


# ═══════════════════════════════════════════════════════════════════════════════
# 等权 Fisher-z 聚合 (与 canonical fisherz_weighted_agg 的 equal 分支逐位一致, 但输入
# 已是「通过 effN 门槛」的 rho 数组 —— 门槛在调用方按 effN 施加, 不再用 len(g))
# ═══════════════════════════════════════════════════════════════════════════════
def fisherz_equal(rhos):
    """等权 Fisher-z 均值 → tanh 回。rhos 已是通过门槛且非 NaN 的患者 rho。空 → NaN。"""
    r = np.asarray(rhos, float)
    r = r[~np.isnan(r)]
    if len(r) == 0:
        return np.nan
    r = np.clip(r, -LOCAL_CLIP, LOCAL_CLIP)             # 本地加固 (0.99, 见顶部注释), 非 canonical 0.9999
    z = np.arctanh(r)
    return float(np.tanh(z.mean()))


def bootstrap_ci(passing_rhos, n_boot=N_BOOT, seed=BOOT_SEED):
    """cluster-bootstrap over patients: 有放回重采样「通过门槛的患者」, 每次等权 Fisher-z 聚合,
    2.5/97.5 分位。passing_rhos 已是通过 effN 门槛的患者 rho 数组。
    K<1 → (NaN,NaN); K==1 → 退化 (CI 收缩到点值)。
    """
    r = np.asarray(passing_rhos, float)
    r = r[~np.isnan(r)]
    K = len(r)
    if K == 0:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    boot = np.full(n_boot, np.nan)
    for b in range(n_boot):
        samp = rng.integers(0, K, size=K)               # 有放回重采样患者
        boot[b] = fisherz_equal(r[samp])
    bv = boot[~np.isnan(boot)]
    if len(bv) == 0:
        return np.nan, np.nan
    return float(np.percentile(bv, 2.5)), float(np.percentile(bv, 97.5))


# ═══════════════════════════════════════════════════════════════════════════════
# 单工具逐患者 effN + rho + effN 门槛聚合
# ═══════════════════════════════════════════════════════════════════════════════
def compute_tool(df, tool, effn_min):
    """对单工具算逐患者 (effN, rho) + effN 门槛下的等权 Fisher-z 聚合 + bootstrap CI。

    effN = 该患者 <tool>_max 与 Elispot 同时非 NaN 的点数 (★ 修 bug 的核心: 不是 len(g))。
      effN<2 或 x/y 无方差 → rho=NaN (spearman_np 内部判)。
    门槛: 只有 effN >= effn_min 的患者 rho (且非 NaN) 进聚合。
    返回 dict: fisherz_rho_effN, ci_lo, ci_hi, n_full, min_effN, max_effN, n_dropped_effN,
      coverage_fail, rho_p<id>, effN_p<id>, dropped_list(用于 stdout)。
    """
    col = f"{tool}_max"
    per_rho = {}                                        # pat -> rho (NaN 允许)
    per_effN = {}                                       # pat -> effN (int)
    if col not in df.columns:
        # 工具 max 列整个缺失: 全 NaN 占位 (coverage_fail)。
        for pat in DS2_PATIENTS:
            per_rho[pat] = np.nan
            per_effN[pat] = 0
        return _pack(tool, per_rho, per_effN, effn_min, dropped=[], col_missing=True)

    for pat in DS2_PATIENTS:
        g = df[df["Patient_ID"] == pat]
        x = g[col].values.astype(float)
        y = g["Elispot"].values.astype(float)
        m = ~(np.isnan(x) | np.isnan(y))                # 同时非 NaN 的子集
        effN = int(m.sum())
        rho = spearman_np(x[m], y[m]) if effN >= 2 else np.nan  # rho 复用 canonical, 与原可比
        per_rho[pat] = rho
        per_effN[pat] = effN

    return _pack(tool, per_rho, per_effN, effn_min, dropped=None, col_missing=False)


def _pack(tool, per_rho, per_effN, effn_min, dropped, col_missing):
    """按 effN 门槛聚合 + 组装输出行。"""
    passing_rhos, passing_effNs = [], []
    dropped_list = []                                   # (tool, pat, effN) 因 effN 不足被剔
    for pat in DS2_PATIENTS:
        effN = per_effN[pat]
        rho = per_rho[pat]
        if effN >= effn_min and not np.isnan(rho):
            passing_rhos.append(rho)
            passing_effNs.append(effN)
        elif 2 <= effN < effn_min:
            # 有可算 rho 但 effN 不足 (正是 bug 里 rho=±1 伪迹的来源, 现被剔)。
            dropped_list.append((tool, pat, effN))

    n_full = len(passing_rhos)
    rho_bar = fisherz_equal(passing_rhos) if n_full > 0 else np.nan
    ci_lo, ci_hi = bootstrap_ci(passing_rhos) if n_full > 0 else (np.nan, np.nan)
    min_effN = int(min(passing_effNs)) if passing_effNs else np.nan
    max_effN = int(max(passing_effNs)) if passing_effNs else np.nan
    coverage_fail = bool(n_full < 3)

    row = {
        "Tool": tool,
        "pending_DTU": tool in DTU_TOOLS,
        "fisherz_rho_effN": rho_bar,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "n_full": n_full,
        "min_effN": min_effN,
        "max_effN": max_effN,
        "n_dropped_effN": len(dropped_list),
        "coverage_fail": coverage_fail,
    }
    for pat in DS2_PATIENTS:
        row[f"rho_p{pat}"] = per_rho[pat]
    for pat in DS2_PATIENTS:
        row[f"effN_p{pat}"] = per_effN[pat]
    row["__dropped__"] = dropped_list                   # 私有, stdout 用, 写 csv 前删
    return row


# ═══════════════════════════════════════════════════════════════════════════════
# 单个 EFFN_MIN 版本的重算 → csv
# ═══════════════════════════════════════════════════════════════════════════════
def run_version(df, effn_min):
    """重算全 30 工具 @ 指定 EFFN_MIN, 写 R1_recomputed_effN{effn_min}.csv, 返回 rows(list dict)。"""
    print(f"\n{'='*78}\n[EFFN_MIN={effn_min}] 重算 30 工具 per-patient Spearman (effN 门槛)\n{'='*78}")
    rows = [compute_tool(df, t, effn_min) for t in TOOLS_30]

    # 排序: coverage_fail=False 优先, 组内按 fisherz_rho_effN 降序 (NaN 最后)。
    def _key(r):
        rho = r["fisherz_rho_effN"]
        rho_key = -np.inf if (rho is None or np.isnan(rho)) else rho
        return (r["coverage_fail"], -rho_key)           # False(0)<True(1); rho 大在前
    rows_sorted = sorted(rows, key=_key)

    # stdout: 每工具 n_full + 被剔明细
    print(f"\n[EFFN_MIN={effn_min}] 每工具 n_full (通过 effN>= {effn_min} 门槛的患者数):")
    for r in rows_sorted:
        flag = "  <coverage_fail>" if r["coverage_fail"] else ""
        rho = r["fisherz_rho_effN"]
        rho_s = "  nan" if (rho is None or np.isnan(rho)) else f"{rho:+.4f}"
        print(f"   {r['Tool']:<16} n_full={r['n_full']}/9  rho_effN={rho_s}"
              f"  n_dropped_effN={r['n_dropped_effN']}{flag}")

    print(f"\n[EFFN_MIN={effn_min}] 因 effN 不足被剔的 (工具, 患者, effN) —— 这些是 rho=±1 伪迹来源:")
    any_drop = False
    for r in rows_sorted:
        for (t, pat, effN) in r["__dropped__"]:
            print(f"   剔: {t:<16} patient={pat}  effN={effN}  (< {effn_min})")
            any_drop = True
    if not any_drop:
        print("   (无)")

    # 写 csv (删私有列)
    out_rows = []
    for r in rows_sorted:
        rr = {k: v for k, v in r.items() if k != "__dropped__"}
        out_rows.append(rr)
    out_df = pd.DataFrame(out_rows)
    out_path = OUT_DIR / f"R1_recomputed{_tag_seg()}_effN{effn_min}.csv"
    in_name = INPUT_NAME                                 # main 里设的输入表名 (口径标注)
    header = (
        f"# {out_path.name} —— §3.1 图1 修正重算 (effN 门槛)\n"
        f"# 输入={in_name}; DS2 9 患者; Elispot 连续 SFC; headline 零选择 <tool>_max\n"
        f"# fisherz_rho_effN=等权 Fisher-z (门槛改用有效覆盖 effN>={effn_min}, 非患者总行数 len(g))\n"
        f"# ci_*=cluster-bootstrap over 通过门槛患者 95%CI (n_boot={N_BOOT}, seed={BOOT_SEED}, 2.5/97.5)\n"
        f"# n_full=effN>={effn_min} 的患者数; n_dropped_effN=2<=effN<{effn_min} 被剔患者数 (原 bug 伪迹来源)\n"
        f"# coverage_fail=(n_full<3): 通过门槛患者不足 3 → 不入主排序; 排序: coverage_fail 后置 + rho 降序\n"
        f"# pending_DTU=True 为 DTU 受限工具 (结果照常算, 部署受 DTU 同意约束)\n"
        f"# rho_p<id>=各患者 per-patient rho (与 canonical spearman_np 可比); effN_p<id>=各患者有效覆盖点数\n"
    )
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write(header)
        out_df.to_csv(f, index=False)
    print(f"\n[saved] {out_path}  ({len(out_df)} 工具)")
    return rows_sorted


# ═══════════════════════════════════════════════════════════════════════════════
# 对照表: 原 (canonical fisherz_rho_raw) vs 新 (effN10)
# ═══════════════════════════════════════════════════════════════════════════════
def build_compare(rows_effN10):
    """读 canonical R1 的 fisherz_rho_raw, 与 effN10 新值对照 (谁掉下/谁升上)。"""
    if TAG:
        # canonical R1_single_maxpool_official.csv 是 9mer 口径; 非 9mer tag (如 8-11mer) 下
        # 口径不同, 对照意义弱且易误导 -> 跳过, 不产 compare 表。
        print(f"[skip] TAG='{TAG}' 非 9mer 口径, canonical(9mer) 对照意义弱 -> 跳过 build_compare")
        return
    if not CANON_R1.exists():
        print(f"[warn] canonical R1 不存在, 跳过对照表: {CANON_R1}")
        return
    canon = pd.read_csv(CANON_R1, comment="#", encoding="utf-8")
    if "Tool" not in canon.columns or "fisherz_rho_raw" not in canon.columns:
        print(f"[warn] canonical R1 缺 Tool/fisherz_rho_raw 列, 跳过对照表; 实际={list(canon.columns)}")
        return
    orig_map = dict(zip(canon["Tool"], pd.to_numeric(canon["fisherz_rho_raw"], errors="coerce")))
    # orig_rank: canonical 按 fisherz_rho_raw 降序 (NaN 最后)
    canon_sorted = sorted(orig_map.items(),
                          key=lambda kv: -np.inf if np.isnan(kv[1]) else kv[1], reverse=True)
    orig_rank = {t: i + 1 for i, (t, _) in enumerate(canon_sorted)}

    new_map = {r["Tool"]: r["fisherz_rho_effN"] for r in rows_effN10}
    fail_map = {r["Tool"]: r["coverage_fail"] for r in rows_effN10}
    # new_rank: 按 fisherz_rho_effN 降序 (NaN 最后)
    new_sorted = sorted(new_map.items(),
                        key=lambda kv: -np.inf if (kv[1] is None or np.isnan(kv[1])) else kv[1],
                        reverse=True)
    new_rank = {t: i + 1 for i, (t, _) in enumerate(new_sorted)}

    comp = []
    for t in TOOLS_30:
        o = orig_map.get(t, np.nan)
        n = new_map.get(t, np.nan)
        delta = (n - o) if (not np.isnan(o) and n is not None and not np.isnan(n)) else np.nan
        comp.append({
            "Tool": t,
            "orig_rho": o,
            "orig_rank": orig_rank.get(t, np.nan),
            "new_rho": n,
            "new_rank": new_rank.get(t, np.nan),
            "delta": delta,
            "coverage_fail": fail_map.get(t, ""),
        })
    comp_df = pd.DataFrame(comp).sort_values("orig_rank").reset_index(drop=True)
    out_path = OUT_DIR / "R1_compare_orig_vs_effN.csv"
    header = (
        "# R1_compare_orig_vs_effN.csv —— §3.1 图1 原(canonical) vs 新(effN>=10) 对照\n"
        "# orig_rho=canonical R1_single_maxpool_official.csv fisherz_rho_raw (含 len(g) 门槛 bug)\n"
        "# new_rho=R1_recomputed_effN10.csv fisherz_rho_effN (门槛改用有效覆盖 effN>=10)\n"
        "# delta=new_rho-orig_rho; *_rank 各自按 rho 降序; coverage_fail=True 者新排序应排最后\n"
        "# 按 orig_rank 升序排列 (原榜首在最上, 一眼看谁被 bug 撑起后掉下去)\n"
    )
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write(header)
        comp_df.to_csv(f, index=False)
    print(f"[saved] {out_path}")

    # stdout: 新旧 top10 对照
    print(f"\n{'='*78}\n新旧 top10 对照 (原 fisherz_rho_raw vs 新 fisherz_rho_effN)\n{'='*78}")
    print(f"{'rank':<5}{'原-工具':<18}{'原rho':>9}   | {'新-工具':<18}{'新rho':>9}{'  fail':>7}")
    for i in range(10):
        ot, orho = canon_sorted[i] if i < len(canon_sorted) else ("", np.nan)
        nt, nrho = new_sorted[i] if i < len(new_sorted) else ("", np.nan)
        orho_s = "nan" if np.isnan(orho) else f"{orho:+.4f}"
        nrho_s = "nan" if (nrho is None or np.isnan(nrho)) else f"{nrho:+.4f}"
        nfail = "  FAIL" if fail_map.get(nt, False) else ""
        print(f"{i+1:<5}{ot:<18}{orho_s:>9}   | {nt:<18}{nrho_s:>9}{nfail:>7}")


# ═══════════════════════════════════════════════════════════════════════════════
# 三档 effN 门槛 (5/8/10) 敏感性表
# ═══════════════════════════════════════════════════════════════════════════════
def _rank_sorted(rows):
    """按 fisherz_rho_effN 降序排 (coverage_fail=True 或 rho NaN 归最后), 返回排序后的 row list。
    与 run_version._key / build_compare 的降序逻辑一致 (好工具在前, 坏的后置)。"""
    def _key(r):
        rho = r["fisherz_rho_effN"]
        is_nan = (rho is None) or np.isnan(rho)
        bad = bool(r["coverage_fail"]) or is_nan       # 覆盖失败 或 无 rho → 排最后
        rho_key = -np.inf if is_nan else rho
        return (bad, -rho_key)                          # False(0)<True(1); 组内 rho 大在前
    return sorted(rows, key=_key)


def _rank_map(rows):
    """Tool -> rank(int, 1-based), 排名口径见 _rank_sorted。"""
    return {r["Tool"]: i + 1 for i, r in enumerate(_rank_sorted(rows))}


def build_sensitivity(rows5, rows8, rows10):
    """三档 effN 门槛 (5/8/10) 敏感性表: 每工具 rho/rank/n_full 三档并排, 看排名是否随门槛翻转。
    rows5/rows8/rows10 均为 run_version 返回的 list[dict], 用 Tool 做 key 对齐三档。
    产 R1_effN_sensitivity_5_8_10.csv, 按主档 rank_effN10 升序。"""
    m5 = {r["Tool"]: r for r in rows5}
    m8 = {r["Tool"]: r for r in rows8}
    m10 = {r["Tool"]: r for r in rows10}
    rank5, rank8, rank10 = _rank_map(rows5), _rank_map(rows8), _rank_map(rows10)

    def _rho(m, t):
        v = m.get(t, {}).get("fisherz_rho_effN", np.nan)
        return np.nan if v is None else v

    def _nfull(m, t):
        return m.get(t, {}).get("n_full", np.nan)

    rows_out = []
    for t in TOOLS_30:
        rows_out.append({
            "Tool": t,
            "rho_effN5": _rho(m5, t),
            "rho_effN8": _rho(m8, t),
            "rho_effN10": _rho(m10, t),
            "rank_effN5": rank5.get(t, np.nan),
            "rank_effN8": rank8.get(t, np.nan),
            "rank_effN10": rank10.get(t, np.nan),
            "n_full_effN5": _nfull(m5, t),
            "n_full_effN8": _nfull(m8, t),
            "n_full_effN10": _nfull(m10, t),
            "coverage_fail_effN10": bool(m10.get(t, {}).get("coverage_fail", True)),
        })
    sens_df = pd.DataFrame(rows_out).sort_values("rank_effN10").reset_index(drop=True)
    out_path = OUT_DIR / f"R1_effN_sensitivity{_tag_seg()}_5_8_10.csv"
    header = (
        f"# {out_path.name} —— §3.1 图1 effN 门槛 5/8/10 三档敏感性 (输入={INPUT_NAME})\n"
        "# 门槛越高越干净 (剔低覆盖患者的 rho=±1 伪迹) 但也剔掉更多患者 (n_full 降), 样本更少更抖。\n"
        "# 用途: 看稳定工具的排名 (rank_effN*) 是否随门槛翻转 —— 不翻=结论稳健, 翻=对门槛敏感需谨慎。\n"
        "# rho_effN*=各档 fisherz_rho_effN (Fisher-z 等权聚合); rank_effN*=各档按 rho 降序 (NaN/coverage_fail 最后)\n"
        "# n_full_effN*=各档通过门槛患者数; coverage_fail_effN10=主档(10)通过患者<3 (不入主排序)\n"
        "# 按 rank_effN10 (主档排名) 升序排列\n"
    )
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write(header)
        sens_df.to_csv(f, index=False)
    print(f"[saved] {out_path}")

    # stdout: 三档 top5 工具对比 (看榜首是否随门槛翻转)
    print(f"\n{'='*78}\n三档 effN 门槛 top5 工具对比 (rho 降序; 看排名是否随门槛翻转)\n{'='*78}")
    for label, rows in [("effN5 ", rows5), ("effN8 ", rows8), ("effN10", rows10)]:
        top = _rank_sorted(rows)[:5]
        parts = []
        for r in top:
            rho = r["fisherz_rho_effN"]
            rho_s = "nan" if (rho is None or np.isnan(rho)) else f"{rho:+.3f}"
            parts.append(f"{r['Tool']}({rho_s})")
        print(f"   [{label}] " + ", ".join(parts))


def main():
    global TAG, INPUT_NAME
    ap = argparse.ArgumentParser(
        description="§3.1 图1 per-patient Spearman effN 门槛修正重算 (支持多长度口径 --input/--tag)")
    ap.add_argument("--input", default=None,
                    help="pooling 冻结表 (默认 None=用 FROZEN_POOLED 9mer 主口径); "
                         "相对路径按项目根解析, 如 data/frozen/pooled_clean_8to11mer.csv")
    ap.add_argument("--tag", default="",
                    help="非空则加进所有输出文件名 (如 8to11mer -> R1_recomputed_8to11mer_effN10.csv); "
                         "空=维持现有 9mer 无前缀产物命名不变")
    args = ap.parse_args()
    TAG = args.tag.strip()

    if args.input:
        in_path = Path(args.input)
        if not in_path.is_absolute():
            in_path = ROOT / in_path                    # 相对路径按项目根解析 (同 p0e2 ROOT 处理)
        if not in_path.exists():
            raise SystemExit(f"[ERR] --input 冻结表不存在: {in_path}")
    else:
        in_path = FROZEN_POOLED                         # 默认 9mer 主口径
    INPUT_NAME = Path(in_path).name

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[info] 输入 (只读): {in_path}")
    print(f"[info] 输出目录: {OUT_DIR}  (tag='{TAG}')")
    df = load_frozen(in_path)                           # 强制 Patient_ID int, Elispot float
    print(f"[info] 冻结表 {df.shape[0]} 行; 患者={sorted(df['Patient_ID'].unique().tolist())}")

    rows10 = run_version(df, effn_min=10)               # 主版 (用户 2026-07-03 拍板: 门槛 5→10)
    rows8 = run_version(df, effn_min=8)                 # 敏感性中档
    rows5 = run_version(df, effn_min=5)                 # 敏感性低档 (原主版)
    _ = run_version(df, effn_min=3)                     # 对照版 (analyst 实测 effN=4 仍偶发 ±1)

    build_sensitivity(rows5, rows8, rows10)             # 5/8/10 三档敏感性表
    build_compare(rows10)                               # 原(canonical) vs 新(effN10) 对照
    print("\n[DONE] recompute_R1_effN 完成 (effN10 主 + effN8/5/3 + 敏感性表 + 对照表)")


if __name__ == "__main__":
    main()
