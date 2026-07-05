#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fusion_nested_cv.py
===================
服务: QuantImmuBench WS1 —— 给 fusion 补交叉验证 (量化「融合成员选择」使表观优势虚高多少)。
对应 lever: WS1「给 fusion 补交叉验证」。

做什么 (skeptic 红队已定的设计, 逐条落实):
  geomean 钉死为融合算子, 内层只做「前向贪心选成员」(不选 method、不选 pooling)。外层 9 折
  留一 DS2 患者 (nested-LOPO): 每折在其余 8 患者上前向贪心挑融合成员 (candidate=每工具
  <tool>_max, 零 pooling 选择), 在留出患者上诚实评估 = CV-honest 估计。对照臂 = oracle
  (全 9 患者选成员/单工具, in-sample 作弊上界) + fixed_surv6 (固定 SURV6 geomean)。

  ★ 首要交付量 = 选择膨胀 Δ (headline):
      inflation_integration = oracle_integration − cv_integration
      inflation_single      = oracle_single      − cv_single
    量化「成员选择使表观优势虚高多少」。整合-vs-单的配对检验降为佐证 (输出 Δ 和 p, 但结果
    解读预登记: null 写「无可检测的整合净优势」, 不写「证伪整合优势」)。

  候选池两版 (限每患者≥COVER_MIN 肽的全覆盖工具, 剔 NeoaPred/HLAthena/NetTepi/ICERFIRE 等稀疏
  工具防小 n 虚高): pool=fullcov 与 pool=fullcov_no_dtu (再剔 DTU 工具) 各跑全部臂;
  裸 + 控长两口径: 裸版 per-patient Spearman = 主指标, 控长版 partial(ctrl=peplen) = sensitivity;
  shuffle null: --shuffle 患者内打乱 Elispot 重跑, 所有臂应塌到 ≈0 (证信号非选择泄漏)。

无泄漏论证:
  · geomean 无监督 (病人内 rank 融合, 不碰标签), 且 within-patient 独立 → 留出患者融合分与
    内层 8 患者无关, 算全行 OK, 零泄漏 (成员『选择』被限在内层 8 患者是唯一防泄漏点)。
  · 内层贪心的每步 ρ̄ 只在内层 8 患者上评, 从不碰外层留出患者。

复用 (照抄, 只把「选 θ」改成「选融合成员」):
  · 外层留一 + shuffle null 结构 ← analysis/official/R5_official.py (compute_lopo_rho / --shuffle)
  · apply_fusion / spearman_np / _partial_spearman_one / fisherz_weighted_agg /
    present_patients / TOOLS_30 / DTU_TOOLS / DS2_PATIENTS / pool_col / r6
    ← analysis/official/_official_common.py
  ★ per-patient ρ̄ 不直接用 C.per_patient_spearman/partial (它们无退化守卫), 改用本文件
    guarded_perpat_metric (加 n_eff<4 剔患者 + |ρ_p|>0.999 丢退化); bootstrap/paired 同理
    用守卫后 per-patient ρ 向量的本地版 (guarded_bootstrap_ci / guarded_paired_test)。

输入 (只读干净表, 绝不改):
  data/frozen/pooled_clean_9mer.csv
输出 (analysis/fusion_cv/):
  fusion_nested_cv.csv          —— 每行 = (pool版本 × 口径裸/控长)
  fusion_nested_cv_members.csv  —— 每折 × pool × caliber 选中成员
  fusion_nested_cv_shuffle.csv  —— shuffle null 对照 (--shuffle 时写)

跑法 (主线跑, 我不跑):
  python analysis/fusion_cv/fusion_nested_cv.py
  python analysis/fusion_cv/fusion_nested_cv.py --shuffle --seed 42   # null 对照

★ scope (🟡⑨): 候选池限固定 pooling=max, 故本脚本只量化「固定 pooling=max 下的成员选择偏差」,
  不含 pooling 选择偏差 (那由 R2/R3 的 in-sample best_pooling 上界另行讨论)。
★ SURV6 也是 selection-informed 非中性 baseline (🟡⑦): 其成员由既往分析挑定, fixed_surv6 只作
  「若固定用大纲既有 6 维」参照, 不是无先验的中性对照。
"""

import sys
import itertools
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent                  # analysis/fusion_cv/
ROOT = HERE.parent.parent                               # QuantImmuBench/
sys.path.insert(0, str(ROOT / "analysis" / "official"))
import _official_common as C                             # noqa: E402

# ── 可调常量 (脚本顶部, 易改) ────────────────────────────────────────────────
EPS = 0.01          # 前向贪心接受阈: 内层 ρ̄ 提升须 > EPS 才纳入新成员
MAXDIM = 6          # 融合成员数封顶
FUSION_OP = "geomean"   # ★ 钉死融合算子 (skeptic 定); 内层只选成员, 不选算子
SURV6 = ["PredIG", "IMPROVE", "pTuneos", "PRIME", "ImmuneApp", "deepHLApan"]  # 同 R3
LENCTRL_MIN_FOLDS = 6   # 控长版有效折 < 此 → 标 lenctrl_underpowered

# ── ★ 退化守卫 (修 HLAthena 小样本伪迹: P101 仅 3 非空 → 虚假 ρ=1.0 → 裸 ρ̄=0.627 假冠军) ──
# 逐患者取「工具/融合分 vs Elispot」非空交集后: 有效点数 n_eff<N_EFF_MIN 的患者不计入;
# 且丢弃 |ρ_p|>DEGEN_RHO 的退化患者 (小样本虚假完美相关)。选择/评估/bootstrap/paired 全走守卫。
N_EFF_MIN = 4        # 患者内有效点数硬底 (Spearman n<4 不稳; lenctrl 偏相关本就需≥4)
DEGEN_RHO = 0.999    # |ρ_p| 超此判退化 (小样本虚假完美相关), 丢弃该患者

# ── ★ 候选池全覆盖过滤 (对齐 R5 FULL_COV 思路; 修 shuffle null 不塌 0) ──
# 守卫挡「已退化 |ρ|>0.999」, 但挡不住「未退化但小 n 高方差」(NeoaPred 某患者 0 肽、
# HLAthena/NetTepi min 3、ICERFIRE min 4 → 打乱后 inner 上因点少 |ρ| 虚高被 argmax 选中)。
# 候选池只保留「每患者内 <tool>_max 与 Elispot 双非空点数 ≥ COVER_MIN」的工具 (24 个满足);
# 剔的正是 NeoaPred/HLAthena/NetTepi/ICERFIRE 及边界 pTuneos/NeoaG(min=6)。
# ★ 仅过滤『候选池』(贪心/单工具argmax/oracle); fixed_surv6 仍用原 SURV6 (非中性 baseline 不动)。
COVER_MIN = 8        # 每患者最少肽数 (min over patients of 双非空计数) 才入候选池


# ═══════════════════════════════════════════════════════════════════════════════
# 度量 / 融合 / 选择 helper
# ═══════════════════════════════════════════════════════════════════════════════

def guarded_perpat_metric(df, score, pats, caliber, *, return_perpat=False):
    """★ 退化守卫版 per-patient ρ̄ (取代 C.per_patient_spearman / per_patient_partial_spearman)。

    逐患者算 ρ_p (raw 走纯 numpy Spearman, lenctrl 走偏 Spearman(|peplen)), 但守卫:
      · 在该患者内对 score/Elispot(/peplen) 取非空交集, 有效点数 n_eff<N_EFF_MIN 的患者不计入;
      · 丢弃 |ρ_p|>DEGEN_RHO 的退化患者 (小样本虚假完美相关, 如 HLAthena P101 3 点 ρ=1.0)。
    保留患者的 (ρ_p, n_eff) 再 C.fisherz_weighted_agg 等权聚合。接口对齐旧 per_patient_*:
      return_perpat=False → (rho_bar, ci_lo, ci_hi, n_used, n_dropped);
      True → 追加 (rhos_by_pat, ns_by_pat)。ns_by_pat 存 n_eff (供 lenctrl n_used 报告)。

    score : df 列名 (str) 或与 df 等长 array (fusion / CV-honest 预测向量)。
    caliber: 'raw' | 'lenctrl'。
    """
    ctrl = None if caliber == "raw" else "peplen"
    if isinstance(score, str):
        work, col = df, score
    else:
        work = df.copy()
        col = "__score__"
        work[col] = np.asarray(score, dtype=float)
    if ctrl is not None and ctrl not in work.columns:
        sys.exit(f"[ERR] guarded_perpat_metric: 控制列缺失 ctrl={ctrl}")

    rhos, ns = [], []
    rhos_by, ns_by = {}, {}
    for pat in pats:
        g = work[work["Patient_ID"] == pat]
        x = g[col].values.astype(float)
        y = g[C.LABEL_COL].values.astype(float)
        if ctrl is None:
            m = ~(np.isnan(x) | np.isnan(y))
            n_eff = int(m.sum())
            rho = C.spearman_np(x[m], y[m]) if n_eff >= N_EFF_MIN else np.nan
        else:
            zc = g[ctrl].values.astype(float)
            m = ~(np.isnan(x) | np.isnan(y) | np.isnan(zc))
            n_eff = int(m.sum())
            rho = (C._partial_spearman_one(x[m], y[m], zc[m])
                   if n_eff >= N_EFF_MIN else np.nan)
        if not np.isnan(rho) and abs(rho) > DEGEN_RHO:   # 退化患者 (虚假完美相关) 丢弃
            rho = np.nan
        rhos.append(rho)
        ns.append(float(n_eff))
        rhos_by[pat] = rho
        ns_by[pat] = n_eff

    rb, lo, hi, nu, nd = C.fisherz_weighted_agg(
        np.array(rhos, float), np.array(ns, float), weight="equal")
    if return_perpat:
        return rb, lo, hi, nu, nd, rhos_by, ns_by
    return rb, lo, hi, nu, nd


def guarded_bootstrap_ci(rhos_by, ns_by, pats, n_boot, seed):
    """基于守卫后 per-patient ρ 向量做 cluster bootstrap over patients 的 95%CI。
    (不用 C.bootstrap_patient_ci, 因其内部重算无守卫的 per_patient_*。) 返回 (point, lo, hi)。
    """
    rho_arr = np.array([rhos_by[p] for p in pats], float)
    n_arr = np.array([float(ns_by[p]) for p in pats], float)
    point = C.fisherz_weighted_agg(rho_arr, n_arr, weight="equal")[0]
    rng = np.random.default_rng(seed)
    K = len(pats)
    boot = np.full(n_boot, np.nan)
    for b in range(n_boot):
        if K == 0:
            break
        samp = rng.integers(0, K, size=K)
        boot[b] = C.fisherz_weighted_agg(rho_arr[samp], n_arr[samp], weight="equal")[0]
    bv = boot[~np.isnan(boot)]
    if len(bv) == 0:
        return point, np.nan, np.nan
    return point, float(np.percentile(bv, 2.5)), float(np.percentile(bv, 97.5))


def guarded_paired_test(ra, na, rb, nb, pats, seed, n_perm=10000):
    """基于守卫后 per-patient ρ 向量的病人配对符号置换检验 (镜像 C.paired_patient_test 内核)。
    两法在该病人都需 n_eff>FISHER_MIN_N 且 ρ 非 NaN (与守卫聚合 keep 口径一致)。
    返回 (delta_zbar, p_permutation, K)。
    """
    diffs = []
    for p in pats:
        va, vb = ra.get(p, np.nan), rb.get(p, np.nan)
        if np.isnan(va) or np.isnan(vb):
            continue
        if na.get(p, 0) <= C.FISHER_MIN_N or nb.get(p, 0) <= C.FISHER_MIN_N:
            continue
        za = np.arctanh(np.clip(va, -C.FISHER_CLIP, C.FISHER_CLIP))
        zb = np.arctanh(np.clip(vb, -C.FISHER_CLIP, C.FISHER_CLIP))
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
        rng = np.random.default_rng(seed)
        signs = rng.choice(np.array([1.0, -1.0]), size=(n_perm, K))
        perm = (signs * diffs[np.newaxis, :]).mean(axis=1)
    p = float(np.mean(np.abs(perm) >= np.abs(observed) - 1e-12))
    return observed, p, K


def fusion_score(df, members, pats):
    """members (工具短名 list) → geomean 融合分 Series (病人内 rank 融合, 只算 pats 组)。
    ★ geomean within-patient 独立 → 传 pats=[p] 与传全体, p 行值一致 (无泄漏用于留出评估)。
    """
    cols = [C.pool_col(t, "max") for t in members]
    return C.apply_fusion(df, cols, FUSION_OP, patients=pats)


def greedy_members(df, pool, pats, caliber, eps, maxdim):
    """前向贪心选融合成员: 空集起, 每步在 pool 未选工具里试加, 选内层 (守卫) ρ̄ 最大者;
    接受条件 = ρ̄ > 当前 + eps; 封顶 maxdim; 无提升即停。打分走 guarded_perpat_metric。
    baseline 当前 = 0.0 (null 模型 ρ̄=0 → 首成员须 ρ̄>eps 才纳入, 使 shuffle 下多返空集)。
    返回 (members, cur_rho, trace[(tool, rho)])。
    """
    members, remaining, cur, trace = [], list(pool), 0.0, []
    while len(members) < maxdim and remaining:
        best_t, best_rho = None, -np.inf
        for t in remaining:
            s = fusion_score(df, members + [t], pats)
            rho = guarded_perpat_metric(df, s.values, pats, caliber)[0]
            if not np.isnan(rho) and rho > best_rho:
                best_rho, best_t = rho, t
        if best_t is None or not (best_rho > cur + eps):
            break
        members.append(best_t)
        remaining.remove(best_t)
        cur = best_rho
        trace.append((best_t, round(best_rho, 6)))
    return members, cur, trace


def best_single(df, pool, pats, caliber):
    """内层 (守卫) ρ̄ argmax 的单工具 (零 pooling 选择, 用 <tool>_max)。返回 (tool, rho)。
    守卫剔小样本虚假完美相关患者 → HLAthena 假冠军 (裸 ρ̄0.627) 被压回真值 (≈0.207)。
    """
    best_t, best_rho = None, -np.inf
    for t in pool:
        col = C.pool_col(t, "max")
        if col not in df.columns or df[col].notna().sum() == 0:
            continue
        rho = guarded_perpat_metric(df, col, pats, caliber)[0]
        if not np.isnan(rho) and rho > best_rho:
            best_rho, best_t = rho, t
    return best_t, best_rho


def filter_pool(df, tools):
    """剔除 <tool>_max 列缺失/全空的工具 (无法作候选)。仅供 fixed_surv6 (SURV6 原样)。"""
    return [t for t in tools
            if C.pool_col(t, "max") in df.columns
            and df[C.pool_col(t, "max")].notna().sum() > 0]


def _min_perpat_cover(df, tool, pats):
    """该工具 <tool>_max 与 Elispot 双非空计数在各患者上的最小值 (min over patients)。
    基于肽存在性 (与 Elispot 值无关), shuffle 打乱标签不改此计数, seed 无关。列缺失 → 0。
    """
    col = C.pool_col(tool, "max")
    if col not in df.columns:
        return 0
    min_n = np.inf
    for p in pats:
        g = df[df["Patient_ID"] == p]
        n = int((~(np.isnan(g[col].values.astype(float))
                   | np.isnan(g[C.LABEL_COL].values.astype(float)))).sum())
        min_n = min(min_n, n)
    return int(min_n) if np.isfinite(min_n) else 0


def cover_pool(df, tools, pats, cover_min=COVER_MIN):
    """★ 候选池全覆盖过滤: 只保留每患者双非空点数 min ≥ cover_min 的工具 (剔稀疏防小 n 虚高)。
    返回 (kept[list], dropped[list of (tool, min_n)]) 供打印。"""
    kept, dropped = [], []
    for t in tools:
        mn = _min_perpat_cover(df, t, pats)
        if mn >= cover_min:
            kept.append(t)
        else:
            dropped.append((t, mn))
    return kept, dropped


# ═══════════════════════════════════════════════════════════════════════════════
# 一个 (pool × caliber) 臂的完整计算
# ═══════════════════════════════════════════════════════════════════════════════

def run_arm(df, pool, pats, caliber, eps, maxdim, n_boot, seed):
    """跑一个 (pool × caliber) 臂: 9 折 CV-honest + oracle + fixed_surv6 + 膨胀 Δ + 佐证配对。
    所有选择/评估/bootstrap/paired 全走退化守卫版 (guarded_perpat_metric)。
    返回 (row_dict, fold_records[list])。
    """
    # ── 外层 9 折: 构建 CV-honest 预测向量 (每患者填其留出折下的融合/单工具分) ──
    cv_int_pred = pd.Series(np.nan, index=df.index, dtype=float)
    cv_single_pred = pd.Series(np.nan, index=df.index, dtype=float)
    fold_records = []
    for p in pats:
        inner = [q for q in pats if q != p]
        members_f, _cur, _tr = greedy_members(df, pool, inner, caliber, eps, maxdim)
        single_f, _sr = best_single(df, pool, inner, caliber)
        idx_p = df.index[df["Patient_ID"] == p]
        if members_f:
            s_int = fusion_score(df, members_f, [p])      # 只算留出患者 p (within-patient 独立)
            cv_int_pred.loc[idx_p] = s_int.loc[idx_p].values
        if single_f is not None:
            cv_single_pred.loc[idx_p] = df.loc[idx_p, C.pool_col(single_f, "max")].values
        fold_records.append(dict(pool=pool_name(pool), caliber=caliber,
                                 fold_left_out_patient=int(p),
                                 members_selected=";".join(members_f),
                                 n_members=len(members_f),
                                 single_selected=single_f if single_f else ""))

    # ── CV-honest 指标 (guarded_perpat_metric(cv_int_pred) 恰 = 9 折留出守卫 ρ 的 Fisher-z 聚合) ──
    r_int = guarded_perpat_metric(df, cv_int_pred.values, pats, caliber, return_perpat=True)
    cv_integration, n_folds_used = r_int[0], r_int[3]
    rhos_int_by, ns_int_by = r_int[5], r_int[6]
    r_sin = guarded_perpat_metric(df, cv_single_pred.values, pats, caliber, return_perpat=True)
    cv_single = r_sin[0]
    rhos_sin_by, ns_sin_by = r_sin[5], r_sin[6]

    # 控长版: 把每折留出患者的完整用例点数 (守卫后 n_eff) 写进 fold_records (供 n_used 报告)
    if caliber == "lenctrl":
        for fr in fold_records:
            fr["n_used_lenctrl"] = int(ns_int_by.get(fr["fold_left_out_patient"], 0))

    # ── oracle 对照 (全 9 患者, in-sample 作弊上界) ──
    members_or, _cur_or, _tr_or = greedy_members(df, pool, pats, caliber, eps, maxdim)
    oracle_int_score = (fusion_score(df, members_or, pats).values if members_or
                        else np.full(len(df), np.nan))
    oracle_integration = guarded_perpat_metric(df, oracle_int_score, pats, caliber)[0]
    _single_or, oracle_single = best_single(df, pool, pats, caliber)

    # ── fixed_surv6 (固定 SURV6 geomean; selection-informed 非中性 baseline) ──
    surv6_pool = filter_pool(df, SURV6)
    surv6_score = fusion_score(df, surv6_pool, pats).values
    fixed_surv6 = guarded_perpat_metric(df, surv6_score, pats, caliber)[0]

    # ── 首要交付量: 选择膨胀 Δ (oracle − cv; in-sample 上界减诚实估计) ──
    inflation_integration = _sub(oracle_integration, cv_integration)
    inflation_single = _sub(oracle_single, cv_single)

    # ── 佐证: 整合 vs 单工具 CV-honest 配对检验 (守卫后 per-patient ρ 向量, 病人配对符号置换) ──
    _dz, paired_p, _K = guarded_paired_test(
        rhos_int_by, ns_int_by, rhos_sin_by, ns_sin_by, pats, seed)
    integration_minus_single_cv = _sub(cv_integration, cv_single)

    # ── CV-honest 整合分的 cluster-bootstrap 95%CI (基于守卫后 per-patient ρ 向量) ──
    _rp, ci_lo, ci_hi = guarded_bootstrap_ci(rhos_int_by, ns_int_by, pats, n_boot, seed)

    lenctrl_underpowered = bool(caliber == "lenctrl" and (n_folds_used or 0) < LENCTRL_MIN_FOLDS)

    row = dict(
        pool=pool_name(pool), caliber=caliber,
        cv_integration=C.r6(cv_integration), cv_single=C.r6(cv_single),
        oracle_integration=C.r6(oracle_integration), oracle_single=C.r6(oracle_single),
        fixed_surv6=C.r6(fixed_surv6),
        inflation_integration=C.r6(inflation_integration),
        inflation_single=C.r6(inflation_single),
        integration_minus_single_cv=C.r6(integration_minus_single_cv),
        paired_p=C.r6(paired_p), ci_lo=C.r6(ci_lo), ci_hi=C.r6(ci_hi),
        n_folds_used=int(n_folds_used) if n_folds_used is not None else 0,
        lenctrl_underpowered=lenctrl_underpowered,
        consent_critical=False,             # 后处理 (fullcov_no_dtu vs fullcov 翻转) 时改
        interpretation=_interpretation(integration_minus_single_cv, paired_p, n_folds_used),
    )
    return row, fold_records


def _sub(a, b):
    if a is None or b is None or np.isnan(a) or np.isnan(b):
        return np.nan
    return a - b


def _interpretation(delta, p, n_used):
    """预登记结果解读: null 写「无可检测的整合净优势」, 绝不写「证伪整合优势」。"""
    nu = int(n_used) if n_used is not None else 0
    if delta is None or np.isnan(delta):
        return f"整合成员未选出(shuffle/无信号), 无整合分可评 (n={nu})"
    ds = f"Δ={delta:+.4f}"
    ps = f"p={p:.4f}" if (p is not None and not np.isnan(p)) else "p=NaN"
    if p is None or np.isnan(p) or p >= 0.05 or delta <= 0:
        return f"在{nu}有效患者下无可检测的整合净优势 ({ds}, {ps})"
    return f"整合较单工具见净优势 ({ds}, {ps}); 佐证性, 非主结论 (主结论=膨胀Δ)"


# pool → 名字标签 (对象是 list, 需按内容判)
_POOL_NAME_CACHE = {}


def pool_name(pool):
    """按 pool list 内容返回 'fullcov' / 'fullcov_no_dtu' 标签 (调用方注册后查)。"""
    key = tuple(pool)
    return _POOL_NAME_CACHE.get(key, "custom")


def register_pool(name, pool):
    _POOL_NAME_CACHE[tuple(pool)] = name
    return pool


# ═══════════════════════════════════════════════════════════════════════════════
# 成员稳定性 (🟠② 佐证 + 🟡⑧): 跨折成员数分布 + 各工具被选中折数
# ═══════════════════════════════════════════════════════════════════════════════

def print_stability(fold_records, pool_label, caliber):
    """打印 (pool×caliber) 主臂的成员稳定性: 成员数分布 + 各工具被选中折数频次表。
    类别级稳定性拿不到可靠亲和/免疫原分类 → 诚实退回单工具选中频次表 (task 允许)。
    """
    recs = [fr for fr in fold_records
            if fr["pool"] == pool_label and fr["caliber"] == caliber]
    if not recs:
        return
    sizes = [fr["n_members"] for fr in recs]
    print(f"\n[stability {pool_label}/{caliber}] 成员数/折: {sizes} "
          f"(均值{np.mean(sizes):.2f}, 范围{min(sizes)}-{max(sizes)})")
    freq = {}
    for fr in recs:
        for t in (fr["members_selected"].split(";") if fr["members_selected"] else []):
            freq[t] = freq.get(t, 0) + 1
    if freq:
        print(f"[stability {pool_label}/{caliber}] 工具被选中折数 (共{len(recs)}折):")
        for t, c in sorted(freq.items(), key=lambda kv: -kv[1]):
            print(f"    {t:<16s} {c}/{len(recs)}")
    # 单工具臂选中频次 (旁证)
    sfreq = {}
    for fr in recs:
        s = fr["single_selected"]
        if s:
            sfreq[s] = sfreq.get(s, 0) + 1
    if sfreq:
        print(f"[stability {pool_label}/{caliber}] 最强单工具被选折数: "
              + ", ".join(f"{t}:{c}" for t, c in sorted(sfreq.items(), key=lambda kv: -kv[1])))


# ═══════════════════════════════════════════════════════════════════════════════
# CSV 写出
# ═══════════════════════════════════════════════════════════════════════════════

def _hdr_comments(f, input_name):
    f.write("# fusion_nested_cv.csv  —— QuantImmuBench WS1: fusion 交叉验证 (成员选择膨胀 Δ)\n")
    f.write(f"# 数据源={input_name}; DS2 9 患者 (纯 DS2, 无 DS1 训练池)\n")
    f.write(f"# 融合算子钉死={FUSION_OP} (内层只前向贪心选成员, 不选算子/pooling); "
            f"候选=每工具 <tool>_max (零 pooling 选择)\n")
    f.write(f"# ★候选池限每患者≥{COVER_MIN}肽全覆盖工具 (剔 NeoaPred/HLAthena/NetTepi/ICERFIRE "
            f"等稀疏工具防小 n 虚高, 修 shuffle null 不塌 0); pool=fullcov/fullcov_no_dtu\n")
    f.write(f"# 前向贪心: 接受阈 EPS={EPS} (内层 ρ̄ 提升须 >EPS), 成员封顶 MAXDIM={MAXDIM}, "
            f"baseline=0.0 (null ρ̄=0)\n")
    f.write(f"# ★退化守卫 (选择/评估/bootstrap/paired 全走): 患者内 score×Elispot 非空交集 "
            f"n_eff<{N_EFF_MIN} 剔该患者 + 丢弃 |ρ_p|>{DEGEN_RHO} (修 HLAthena 小样本虚假完美相关)\n")
    f.write("# oracle_* = 全 9 患者 in-sample 选成员/单工具 = 作弊上界; cv_* = nested-LOPO 诚实估计\n")
    f.write("# ★首要交付量=膨胀 Δ: inflation_*=oracle_*-cv_* (量化成员选择使表观优势虚高多少)\n")
    f.write("# integration_minus_single_cv/paired_p = 佐证 (预登记: null 不写「证伪整合优势」)\n")
    f.write("# fixed_surv6 = 固定 SURV6 geomean, selection-informed 非中性 baseline (🟡⑦)\n")
    f.write("# scope (🟡⑨): 候选限 pooling=max, 只量化固定 pooling=max 下的成员选择偏差\n")
    f.write("# DTU 工具 (netMHCpan_BA/EL,netMHCstabpan,TSCAPE,ICERFIRE,NetTepi,Seq2Neo) "
            "结果照常算, pending_DTU_consent; fullcov_no_dtu 版剔之\n")


CSV_COLS = ["pool", "caliber", "cv_integration", "cv_single", "oracle_integration",
            "oracle_single", "fixed_surv6", "inflation_integration", "inflation_single",
            "integration_minus_single_cv", "paired_p", "ci_lo", "ci_hi",
            "n_folds_used", "lenctrl_underpowered", "consent_critical", "interpretation"]

MEMBER_COLS = ["pool", "caliber", "fold_left_out_patient", "members_selected",
               "n_members", "single_selected", "n_used_lenctrl"]


def write_main_csv(rows, out_csv, input_name):
    df_out = pd.DataFrame(rows)[CSV_COLS]
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        _hdr_comments(f, input_name)
        df_out.to_csv(f, index=False)
    print(f"[saved] {out_csv}")


def write_members_csv(fold_records, out_csv):
    for fr in fold_records:
        fr.setdefault("n_used_lenctrl", "")
    df_out = pd.DataFrame(fold_records)[MEMBER_COLS]
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        f.write("# fusion_nested_cv_members.csv —— 每折 × pool × caliber 选中融合成员\n")
        f.write("# n_used_lenctrl = 控长口径下该留出患者的完整用例点数 (裸口径列空)\n")
        df_out.to_csv(f, index=False)
    print(f"[saved] {out_csv}")


# ═══════════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="QuantImmuBench WS1: fusion nested-CV (成员选择膨胀 Δ + 佐证配对 + shuffle null)")
    ap.add_argument("--input", default=str(C.FROZEN_POOLED), help="冻结肽级表路径")
    ap.add_argument("--shuffle", action="store_true",
                    help="患者内打乱 Elispot (null 对照; 期望所有臂≈0), 写 _shuffle.csv")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--min_pep", type=int, default=C.MIN_PEP,
                    help="[已由退化守卫 N_EFF_MIN=4 取代, 保留兼容] per-patient 最少肽数")
    ap.add_argument("--eps", type=float, default=EPS, help="前向贪心接受阈 (默认 0.01)")
    ap.add_argument("--maxdim", type=int, default=MAXDIM, help="融合成员数封顶 (默认 6)")
    ap.add_argument("--n_boot", type=int, default=2000, help="cluster bootstrap 次数")
    args = ap.parse_args()

    df = C.load_frozen(args.input)
    pats = C.present_patients(df)
    rng = np.random.default_rng(args.seed)
    if args.shuffle:
        print(f"[shuffle] 患者内打乱 Elispot (seed={args.seed}); 期望所有臂≈0")
        df = df.copy()
        # 患者内打乱 (不跨患者), 保各患者肽数结构
        for p in pats:
            idx = df.index[df["Patient_ID"] == p]
            df.loc[idx, C.LABEL_COL] = rng.permutation(df.loc[idx, C.LABEL_COL].values)

    # ── 候选池全覆盖过滤 (剔稀疏工具防小 n 虚高); fullcov_no_dtu = fullcov 再剔 DTU ──
    fullcov_tools, dropped = cover_pool(df, C.TOOLS_30, pats, COVER_MIN)
    fullcov = register_pool("fullcov", fullcov_tools)
    fullcov_no_dtu = register_pool("fullcov_no_dtu",
                                   [t for t in fullcov_tools if t not in C.DTU_TOOLS])
    print(f"[info] DS2 患者({len(pats)})={pats}; eps={args.eps}; maxdim={args.maxdim}; "
          f"shuffle={args.shuffle}; COVER_MIN={COVER_MIN}")
    print(f"[info] pool fullcov ({len(fullcov)} 工具, 每患者≥{COVER_MIN}肽); "
          f"fullcov_no_dtu ({len(fullcov_no_dtu)} 工具, 再剔 "
          f"{sorted(C.DTU_TOOLS & set(fullcov))})")
    print(f"[info] 剔稀疏工具 ({len(dropped)}): "
          + ", ".join(f"{t}(min={mn})" for t, mn in sorted(dropped, key=lambda kv: kv[1])))

    rows, all_folds = [], []
    for pool, pname in [(fullcov, "fullcov"), (fullcov_no_dtu, "fullcov_no_dtu")]:
        for caliber in ("raw", "lenctrl"):
            print("\n" + "=" * 72)
            print(f"[arm] pool={pname} caliber={caliber}")
            print("=" * 72)
            row, fold_records = run_arm(df, pool, pats, caliber,
                                        args.eps, args.maxdim, args.n_boot, args.seed)
            rows.append(row)
            all_folds.extend(fold_records)
            print(f"  cv_integration={row['cv_integration']} cv_single={row['cv_single']} "
                  f"oracle_int={row['oracle_integration']} oracle_single={row['oracle_single']}")
            print(f"  膨胀Δ int={row['inflation_integration']} single={row['inflation_single']} "
                  f"| int-single_cv={row['integration_minus_single_cv']} p={row['paired_p']}")
            print(f"  {row['interpretation']}")

    # ── consent_critical: fullcov_no_dtu 结论 (integration_minus_single_cv 符号) 相对 fullcov 翻转 → 标 ──
    by_key = {(r["pool"], r["caliber"]): r for r in rows}
    for caliber in ("raw", "lenctrl"):
        a = by_key.get(("fullcov", caliber))
        b = by_key.get(("fullcov_no_dtu", caliber))
        if a is None or b is None:
            continue
        da, db = a["integration_minus_single_cv"], b["integration_minus_single_cv"]
        if da is None or db is None or np.isnan(da) or np.isnan(db):
            continue
        if np.sign(da) != np.sign(db):
            b["consent_critical"] = True
            print(f"[consent_critical] caliber={caliber}: fullcov_no_dtu 整合-单符号相对 fullcov "
                  f"翻转 (fullcov Δ={da:+.4f}, no_dtu Δ={db:+.4f}) → 标 consent_critical")

    # ── 成员稳定性 (🟠②): 主臂 fullcov/raw ──
    print_stability(all_folds, "fullcov", "raw")
    print_stability(all_folds, "fullcov_no_dtu", "raw")

    # ── 写出 ──
    HERE.mkdir(parents=True, exist_ok=True)
    input_name = Path(args.input).name
    if args.shuffle:
        write_main_csv(rows, HERE / "fusion_nested_cv_shuffle.csv", input_name)
        write_members_csv(all_folds, HERE / "fusion_nested_cv_members_shuffle.csv")
    else:
        write_main_csv(rows, HERE / "fusion_nested_cv.csv", input_name)
        write_members_csv(all_folds, HERE / "fusion_nested_cv_members.csv")

    print("\n[DONE] fusion_nested_cv")


if __name__ == "__main__":
    main()
