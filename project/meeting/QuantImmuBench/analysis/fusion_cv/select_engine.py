#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
select_engine.py
================
服务: QuantImmuBench §3.3 fusion / §4.3 selection-bias —— 「原则化 CV 融合选择」Part A (A1-A6)。
对应 lever: 把「融合成员/k/算子/程序」的选择做成无泄漏 nested-CV, 量化每一维选择的膨胀,
           给出统计不可分带, 而非宣称「唯一最优融合」。

设计规格 = analysis/fusion_cv/SELECT_DESIGN.md (planner 定稿 + skeptic 6🟠 落实), 逐条实现。

★ 诚实边界 (写进每个 CSV 顶部注释, 措辞禁 "proven optimal/the best/SOTA"):
   n=9 无「唯一最优」确定性证明; 交付 = 无泄漏 CV 程序 + 选出的(成员×k×算子) + 稳定性/不可分带
   + 每选择的受控证明。null 结果一律写「无可检测的整合净优势」, 绝不写「证伪整合优势」。

复用 (import, 不改):
   · fusion_nested_cv as fn : guarded_perpat_metric / cover_pool / guarded_bootstrap_ci /
        guarded_paired_test / best_single / _sub / 常量 EPS/MAXDIM/COVER_MIN/N_EFF_MIN/DEGEN_RHO。
        ★ 所有 CV 评估一律走 fn.guarded_perpat_metric, 禁裸 per_patient (裸版仅 rationale #4/#7 对照)。
   · _official_common as C : apply_fusion / UNSUPERVISED_FUSIONS(8) / pool_col / present_patients /
        TOOLS_30 / DTU_TOOLS / DS2_PATIENTS / fisherz_weighted_agg / spearman_np / LABEL_COL / r6。
   · _toolcorr_common as TC: load_max_scores / spearman_corr(→corr,dropped) / category / is_dtu。

★ 必新增 (本文件内, 不改 fusion_nested_cv.py): 算子参数化的 fusion_score_op / greedy_members_op +
   各选择程序 (forward/backward/exhaustive/topk/decorr) + 联合选(子集×算子)。这些写成模块级
   可 import 函数, 供 rationale_ablations.py 复用 (避免重复实现)。

统一口径 (Part A 全固定): 外层 LOPO 9 折; 内层其余 8 患者选; pooling=_max; 池=cover_pool(≥8)=24 工具;
   raw 主 / lenctrl 只做固定 geomean 敏感性 (不做联合选)。CV-honest 装配: 外层每折留出患者 p 填
   fusion_score_op(df, members_f, [p], op) (geomean within-patient 独立 → 零泄漏), 装满 130 行后
   fn.guarded_perpat_metric(cv_pred)。seed=42 全程; 纯 numpy/pandas 禁 scipy.stats。

跑法 (主线跑, 我不跑):
   python analysis/fusion_cv/select_engine.py            # A1-A6 全跑, 写 6 CSV
   python analysis/fusion_cv/select_engine.py --fast     # 降 B/S/R/n_boot 做快速冒烟
输出 (analysis/fusion_cv/):
   k_curve.csv / select_engine.csv / select_stability.csv / select_null.csv / tool_tool_corr.csv
   (rationale_ledger.csv 由 rationale_ablations.py 写)
"""

import sys
import argparse
import itertools
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent                  # analysis/fusion_cv/
ROOT = HERE.parent.parent                               # QuantImmuBench/
sys.path.insert(0, str(ROOT / "analysis" / "official"))
sys.path.insert(0, str(HERE))
import _official_common as C                             # noqa: E402
import _toolcorr_common as TC                            # noqa: E402
import fusion_nested_cv as fn                            # noqa: E402

# ── 可调常量 (顶部, 易改; --fast 会覆盖慢的几个) ─────────────────────────────────
SEED = 42
EPS = fn.EPS                    # 0.01 前向贪心接受阈
MAXDIM = fn.MAXDIM              # 6   融合成员封顶
COVER_MIN = fn.COVER_MIN        # 8   候选池全覆盖过滤 (每患者≥8肽)
N_BOOT = 2000                   # cluster bootstrap 次数 (A6/CI 便宜)
STAB_B = 200                    # A4 每折 cluster bootstrap 次数 (慢→降 100)
STAB_PI = [0.5, 0.6, 0.8]       # A4 共识阈 (主 0.6)
NULL_R = 1000                   # A5 随机 k-子集 null 每 k 抽样数 (in-sample 纯评估)
NULL_S = 200                    # A5 患者内置换 null 次数 (只对 CHOSEN 程序整条重跑选择)
NULL_KS = (1, 2, 3, 4, 5, 6)    # A5 随机 k-子集扫的 k
DECORR_LAMBDAS = [0.05, 0.10, 0.20]   # 去相关 λ 固定先验扫 (主报 0.10, 绝不用外层ρ̄挑λ)
DECORR_MAIN_LAMBDA = 0.10
KCURVE_KMAX = 8                 # A1 greedy_to_k 跑满 k=1..8
EXHAUST_KMAX = 3                # A1/A3 穷举 k≤3
TOPN_EXHAUST = 10               # 穷举前内层单工具 ρ̄ top-N 预筛
TOPN_BACKWARD = 12              # 后向消除起始 top-N
TOPK_SINGLE_KMAX = 6            # topk_single 扫 k=1..6

OP_GEO = "geomean"
OP_ALL8 = list(C.UNSUPERVISED_FUSIONS.keys())        # 8 无监督算子
OP_CONSENSUS3 = ["geomean", "mean_rank", "median"]   # 共识 3 算子 (skeptic🟠①)

CALIBERS = ("raw", "lenctrl")


# ═══════════════════════════════════════════════════════════════════════════════
# ★ 患者内 rank 缓存 (性能优化, 数学零偏离) —— 见 --selftest 逐元素 allclose 断言
# ═══════════════════════════════════════════════════════════════════════════════
# 根因: C.apply_fusion 每次调 ~27ms (pandas 每次对成员列做 groupby 病人内 rank), 选择搜索调它
#   几十万次 → A4/A5 数小时不可行。关键观察: apply_fusion 的病人内 rank 是【逐列】算的——
#   sub.fillna(sub.mean()) 按【列均值】填 NaN, 再逐列 .rank(method='average'), 故每个工具的
#   病人内 rank 【与选了哪些其它成员无关】。→ 可一次性预缓存 130×n_tool 的 rank 矩阵, 融合改成
#   缓存上的纯 numpy 逐行聚合 (行内不跨患者, rank 已是患者内的), 复用 C.UNSUPERVISED_FUSIONS 原
#   组合子 (op 语义逐位一致)。仅换【融合评估】底层, guarded metric / 分析逻辑 / 输出全不动。
#
# 缓存有效性 (安全键): 以 df.index.equals + 行数为键。全 df 与其 .copy() (A5 shuffle 只改 Elispot,
#   工具列不变) → 命中快路径; 行子集 df (rationale #3 留肽) index 不等 → 自动退回 apply_fusion 慢路径
#   (逐位复刻, 正确)。工具 _max 列全程只读不改, 故 index 相等即缓存 rank 有效。
_CACHE = {"index": None, "mat": None, "col": {}, "pid": None, "n": 0}


def build_rank_cache(df, tools):
    """一次性预计算患者内 rank 缓存, 逐位复刻 C.apply_fusion 的 per-column fill+rank 语义:
      每工具 <tool>_max 列, 病人内: NaN 用【该列该患者均值】填, 整列全 NaN 的患者 → 0, 再
      .rank(method='average') (升序, 平均并列)。存 mat[n×n_tool] + col{tool→列索引} + pid。"""
    n = len(df)
    pid = df["Patient_ID"].values
    mat = np.full((n, len(tools)), np.nan)
    col = {}
    for j, t in enumerate(tools):
        col[t] = j
        c = C.pool_col(t, "max")
        if c not in df.columns:
            continue
        vals = df[c].values.astype(float)
        for p in np.unique(pid):
            mask = pid == p
            sub = vals[mask]
            if np.all(np.isnan(sub)):
                filled = np.zeros(sub.shape, dtype=float)     # 整列全 NaN → 0 (同 fillna(0.0))
            else:
                m = np.nanmean(sub)
                filled = np.where(np.isnan(sub), m, sub)       # NaN 填该列该患者均值
                filled = np.where(np.isnan(filled), 0.0, filled)
            mat[mask, j] = pd.Series(filled).rank(method="average").values
    _CACHE.update(index=df.index, mat=mat, col=col, pid=pid, n=n)
    print(f"[rank_cache] 建成 {n}×{len(tools)} 患者内 rank 缓存 (工具={len(tools)})")


def _cache_valid(df):
    return (_CACHE["index"] is not None and len(df) == _CACHE["n"]
            and df.index.equals(_CACHE["index"]))


# ═══════════════════════════════════════════════════════════════════════════════
# 算子参数化融合 + 前向贪心 (必新增; op=geomean 时逐位等于 fn.fusion_score / fn.greedy_members)
# ═══════════════════════════════════════════════════════════════════════════════

def fusion_score_op(df, members, pats, op):
    """members (工具短名 list) → 算子 op 的病人内 rank 融合分 Series (只算 pats 组)。
    数学 = C.apply_fusion(df, [<t>_max for t in members], op, patients=pats), 但走 rank 缓存加速。
    ★ 无监督算子病人内独立 → 传 pats=[p] 与传全体, p 行值一致 → 用于留出评估零泄漏。
    快路径 (缓存命中 + members 全在缓存): 取缓存 rank 列, 复用 C.UNSUPERVISED_FUSIONS 原组合子逐行聚合;
    慢路径 (子集 df / 未建缓存 / 有缓存外工具): 退回 C.apply_fusion (逐位复刻)。"""
    if not members:
        return pd.Series(np.nan, index=df.index, dtype=float)
    if _cache_valid(df) and all(t in _CACHE["col"] for t in members):
        idxs = [_CACHE["col"][t] for t in members]
        R = _CACHE["mat"][:, idxs]                              # n×k, 已是患者内 rank, 无 NaN
        s = np.asarray(C.UNSUPERVISED_FUSIONS[op](R), dtype=float)   # 复用原组合子 → op 语义逐位一致
        mask = np.isin(_CACHE["pid"], np.asarray(list(pats)))
        out = np.full(_CACHE["n"], np.nan, dtype=float)
        out[mask] = s[mask]                                    # 非 pats 患者置 NaN (同 apply_fusion)
        return pd.Series(out, index=_CACHE["index"])
    cols = [C.pool_col(t, "max") for t in members]             # 慢路径 (子集 df 等)
    return C.apply_fusion(df, cols, op, patients=pats)


def _allclose_nan(a, b, tol=1e-9):
    """允许 NaN 的逐元素比对: NaN 位置须一致, 非 NaN 处 allclose(atol=tol)。"""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    na, nb = np.isnan(a), np.isnan(b)
    if not np.array_equal(na, nb):
        return False
    return bool(np.allclose(a[~na], b[~nb], atol=tol, rtol=0.0))


def selftest_cache(df, tools, pats, n_subset=5, seed=SEED):
    """★ 正确性自检: 对 n_subset 个随机 member 子集 × 8 个 op, 断言【缓存版 fusion_score】与
    【C.apply_fusion】逐元素 allclose(1e-9) (全患者 + 单患者两种 pats)。不过就 sys.exit 停。"""
    build_rank_cache(df, tools)
    rng = np.random.default_rng(seed)
    tools_present = [t for t in tools if C.pool_col(t, "max") in df.columns
                     and df[C.pool_col(t, "max")].notna().sum() > 0]
    ok = True
    for _ in range(n_subset):
        k = int(rng.integers(1, min(6, len(tools_present)) + 1))
        members = list(rng.choice(tools_present, size=k, replace=False))
        cols = [C.pool_col(t, "max") for t in members]
        for op in OP_ALL8:
            a = fusion_score_op(df, members, pats, op).values
            b = C.apply_fusion(df, cols, op, patients=pats).values
            if not _allclose_nan(a, b):
                print(f"[selftest FAIL] op={op} members={members} (全患者)")
                ok = False
            p = int(pats[int(rng.integers(0, len(pats)))])
            a2 = fusion_score_op(df, members, [p], op).values
            b2 = C.apply_fusion(df, cols, op, patients=[p]).values
            if not _allclose_nan(a2, b2):
                print(f"[selftest FAIL] op={op} members={members} (患者 {p})")
                ok = False
    if ok:
        print(f"[selftest PASS] 缓存 fusion ≡ apply_fusion (allclose 1e-9); "
              f"{n_subset} 子集 × {len(OP_ALL8)} op × 2 pats 全过 → 优化零偏离")
    else:
        sys.exit("[selftest] 缓存与 apply_fusion 不一致, 拒绝继续 (优化有偏离, 需修)")
    return ok


# ═══════════════════════════════════════════════════════════════════════════════
# ★ lean numpy-native 守卫评估 (性能优化2, 数学零偏离) —— 见 --selftest allclose 断言
# ═══════════════════════════════════════════════════════════════════════════════
# 根因2: fn.guarded_perpat_metric 传 numpy score 时内部 work=df.copy() (130×1536 大表) ≈15.9ms/次,
#   选择内循环调它几十万次 → A4≈69min/A5≈34min。杀手是 copy 1536 列, 而评估只需 3 列
#   (Elispot/peplen/Patient_ID)。→ lean 版纯 numpy 逐位复刻 guarded_perpat_metric, 零 pandas 零 copy。
# ★ y/z/pat 从【传入的 df】现取 (df[col].values 只 O(130) 单列, 微秒级): 天然正确处理
#   A5 shuffle (标签从 shuffled df 读) / #3 子集 (从 df_train 读) / 全 df —— 无需全局标签交换。


def lean_guarded_metric(score, y, z, pat, pats, caliber, *, return_perpat=False):
    """numpy-native 退化守卫 per-patient ρ̄ —— 逐位复刻 fn.guarded_perpat_metric (零 pandas/零 copy)。
    入参全 numpy 且与被评 df 同行序、等长: score(n,)/y=Elispot(n,)/z=peplen(n, raw 时 None)/pat=Patient_ID(n,);
    pats = 患者 id 列表 (可含重复, cluster bootstrap 加权用)。守卫: 患者内 score×Elispot(×peplen) 非空交集,
    n_eff<N_EFF_MIN 剔该患者 + |ρ_p|>DEGEN_RHO 退化剔; raw 走 C.spearman_np, lenctrl 走 C._partial_spearman_one;
    跨患者 C.fisherz_weighted_agg(equal)。返回签名对齐 guarded_perpat_metric (return_perpat=True 追加 rhos_by,ns_by)。"""
    score = np.asarray(score, float)
    y = np.asarray(y, float)
    pat = np.asarray(pat)
    if caliber != "raw":
        if z is None:
            sys.exit("[ERR] lean_guarded_metric: caliber=lenctrl 但缺 peplen (z=None)")
        z = np.asarray(z, float)
    rhos, ns = [], []
    rhos_by, ns_by = {}, {}
    for p in pats:
        mk = pat == p
        x = score[mk]
        yy = y[mk]
        if caliber == "raw":
            m = ~(np.isnan(x) | np.isnan(yy))
            n_eff = int(m.sum())
            rho = C.spearman_np(x[m], yy[m]) if n_eff >= fn.N_EFF_MIN else np.nan
        else:
            zz = z[mk]
            m = ~(np.isnan(x) | np.isnan(yy) | np.isnan(zz))
            n_eff = int(m.sum())
            rho = (C._partial_spearman_one(x[m], yy[m], zz[m])
                   if n_eff >= fn.N_EFF_MIN else np.nan)
        if not np.isnan(rho) and abs(rho) > fn.DEGEN_RHO:     # 退化患者 (虚假完美相关) 丢弃
            rho = np.nan
        rhos.append(rho)
        ns.append(float(n_eff))
        rhos_by[p] = rho
        ns_by[p] = n_eff
    rb, lo, hi, nu, nd = C.fisherz_weighted_agg(
        np.array(rhos, float), np.array(ns, float), weight="equal")
    if return_perpat:
        return rb, lo, hi, nu, nd, rhos_by, ns_by
    return rb, lo, hi, nu, nd


def _lean_from_df(df, score, pats, caliber, *, return_perpat=False):
    """从【传入的 df】现取 y/z/pat (单列 .values, 微秒级) 后走 lean_guarded_metric。
    score = 列名 str (从 df 取列) 或与 df 等长 array (缓存版 fusion 的 numpy 向量, 已同 df 行序)。"""
    if isinstance(score, str):
        s = df[score].values.astype(float)
    else:
        s = np.asarray(score, float)
    y = df[C.LABEL_COL].values.astype(float)
    pat = df["Patient_ID"].values
    z = df["peplen"].values.astype(float) if caliber != "raw" else None
    return lean_guarded_metric(s, y, z, pat, pats, caliber, return_perpat=return_perpat)


def selftest_lean(df, pats, n_vec=6, seed=SEED):
    """★ 正确性自检2: 随机 score 向量 (含 NaN + 一条近完美相关触发退化守卫) × raw/lenctrl 两口径,
    断言 lean_guarded_metric 与 fn.guarded_perpat_metric 的 (rho_bar + per-patient rhos + n_eff)
    全 allclose(1e-9)/相等 (NaN 位置一致)。不过就 sys.exit 停。"""
    rng = np.random.default_rng(seed + 7)
    y = df[C.LABEL_COL].values.astype(float)
    ok = True
    for it in range(n_vec):
        if it == 0:
            score = y.copy()                                  # 近完美相关 → 触发 |ρ|>0.999 退化守卫
        else:
            score = rng.standard_normal(len(df))
            score[rng.random(len(df)) < 0.12] = np.nan        # 注入 NaN 测 n_eff<4 守卫
        for caliber in ("raw", "lenctrl"):
            la = _lean_from_df(df, score, pats, caliber, return_perpat=True)
            fb = fn.guarded_perpat_metric(df, score, pats, caliber, return_perpat=True)
            if not _allclose_nan([la[0]], [fb[0]]):
                print(f"[selftest FAIL] lean rho_bar≠fn (it={it}, {caliber}): {la[0]} vs {fb[0]}")
                ok = False
            for p in pats:
                if not _allclose_nan([la[5][p]], [fb[5][p]]):
                    print(f"[selftest FAIL] lean per-patient ρ≠fn (it={it}, {caliber}, p={p})")
                    ok = False
                if int(la[6][p]) != int(fb[6][p]):
                    print(f"[selftest FAIL] lean n_eff≠fn (it={it}, {caliber}, p={p})")
                    ok = False
    if ok:
        print(f"[selftest PASS] lean_guarded_metric ≡ fn.guarded_perpat_metric (rho_bar+per-patient+n_eff "
              f"allclose 1e-9); {n_vec} 向量 × 2 口径全过 → 优化零偏离")
    else:
        sys.exit("[selftest] lean 与 fn.guarded_perpat_metric 不一致, 拒绝继续 (优化有偏离, 需修)")
    return ok


def _guard_rho(df, score, pats, caliber):
    """守卫版 per-patient ρ̄ 单值 (score = 列名 str 或与 df 等长 array)。所有 CV 评估唯一入口。
    ★ 走 lean (numpy-native, 零 df.copy); 数学 ≡ fn.guarded_perpat_metric (--selftest 断言)。"""
    return _lean_from_df(df, score, pats, caliber)[0]


def greedy_members_op(df, pool, pats, caliber, eps, maxdim, op):
    """算子参数化前向贪心 (逻辑同 fn.greedy_members, 只把融合走 op)。
    空集起, 每步在 pool 未选工具里试加, 选内层守卫 ρ̄ 最大者; 接受 = ρ̄ > 当前 + eps; 封顶 maxdim。
    baseline 当前 = 0.0 (null ρ̄=0 → 首成员须 ρ̄>eps)。返回 (members, cur_rho, trace)。"""
    members, remaining, cur, trace = [], list(pool), 0.0, []
    while len(members) < maxdim and remaining:
        best_t, best_rho = None, -np.inf
        for t in remaining:
            s = fusion_score_op(df, members + [t], pats, op)
            rho = _guard_rho(df, s.values, pats, caliber)
            if not np.isnan(rho) and rho > best_rho:
                best_rho, best_t = rho, t
        if best_t is None or not (best_rho > cur + eps):
            break
        members.append(best_t)
        remaining.remove(best_t)
        cur = best_rho
        trace.append((best_t, round(best_rho, 6)))
    return members, cur, trace


def greedy_path_op(df, pool, pats, caliber, op, maxk):
    """强制前向贪心 (关 eps): 每步纳入使内层守卫 ρ̄ 最大的工具, 直到 maxk 或候选耗尽。
    返回有序成员 list —— 前缀 [:k] 即各 k 的选集 (A1 一次算全 k, 省重复贪心)。"""
    members, remaining = [], list(pool)
    while len(members) < maxk and remaining:
        best_t, best_rho = None, -np.inf
        for t in remaining:
            s = fusion_score_op(df, members + [t], pats, op)
            rho = _guard_rho(df, s.values, pats, caliber)
            if not np.isnan(rho) and rho > best_rho:
                best_rho, best_t = rho, t
        if best_t is None:
            break
        members.append(best_t)
        remaining.remove(best_t)
    return members


# ── 单工具内层 ρ̄ 排序 (top-N 预筛 / topk_single 用) ────────────────────────────
def single_rhos(df, pool, pats, caliber):
    """pool 内每工具 <tool>_max 的内层守卫 per-patient ρ̄, 返回 {tool: rho} (剔 NaN/缺列)。"""
    out = {}
    for t in pool:
        col = C.pool_col(t, "max")
        if col not in df.columns or df[col].notna().sum() == 0:
            continue
        rho = _guard_rho(df, col, pats, caliber)
        if not np.isnan(rho):
            out[t] = rho
    return out


def _topn_single(df, pool, pats, caliber, n):
    r = single_rhos(df, pool, pats, caliber)
    return [t for t, _ in sorted(r.items(), key=lambda kv: -kv[1])[:n]]


# ═══════════════════════════════════════════════════════════════════════════════
# 选择程序 (A3, 算子固定 geomean 隔离「程序」变量) —— 统一签名 (df,pool,pats,caliber)->members
# ═══════════════════════════════════════════════════════════════════════════════

def proc_forward_greedy(df, pool, pats, caliber, op=OP_GEO, eps=EPS, maxdim=MAXDIM):
    """前向贪心 (headline 程序)。"""
    return greedy_members_op(df, pool, pats, caliber, eps, maxdim, op)[0]


def proc_backward_elim(df, pool, pats, caliber, op=OP_GEO, topn=TOPN_BACKWARD, kmin=1):
    """后向消除: 从内层单工具 ρ̄ top-N=12 起, 每步移除「移除后内层 ρ̄ 最大」者;
    停在「无任何移除能维持/提升 ρ̄」或降到 kmin。隔离『程序』变量 (算子仍 geomean)。"""
    members = _topn_single(df, pool, pats, caliber, topn)
    if not members:
        return []
    cur = _guard_rho(df, fusion_score_op(df, members, pats, op).values, pats, caliber)
    while len(members) > kmin:
        best_rm, best_rho = None, -np.inf
        for t in members:
            trial = [x for x in members if x != t]
            rho = _guard_rho(df, fusion_score_op(df, trial, pats, op).values, pats, caliber)
            if not np.isnan(rho) and rho > best_rho:
                best_rho, best_rm = rho, t
        if best_rm is None or best_rho < cur:   # 移除不再提升 → 停
            break
        members = [x for x in members if x != best_rm]
        cur = best_rho
    return members


def _exhaust_best_k(df, pool, pats, caliber, op, k, topn=TOPN_EXHAUST):
    """内层单工具 ρ̄ top-N 预筛后, 穷举 C(topn, k) 精确取内层 ρ̄ 最大的 size-k 子集。"""
    cand = _topn_single(df, pool, pats, caliber, topn)
    if k > len(cand):
        return []
    best, best_rho = [], -np.inf
    for combo in itertools.combinations(cand, k):
        rho = _guard_rho(df, fusion_score_op(df, list(combo), pats, op).values, pats, caliber)
        if not np.isnan(rho) and rho > best_rho:
            best_rho, best = rho, list(combo)
    return best


def proc_exhaustive_k(df, pool, pats, caliber, op=OP_GEO, kmax=EXHAUST_KMAX, topn=TOPN_EXHAUST):
    """穷举 k≤kmax: 内层 top-N 预筛, 穷举 C(topn,1..kmax) 取内层 ρ̄ 最大子集 (跨 k 也取最大)。"""
    best, best_rho = [], -np.inf
    for k in range(1, kmax + 1):
        m = _exhaust_best_k(df, pool, pats, caliber, op, k, topn)
        if not m:
            continue
        rho = _guard_rho(df, fusion_score_op(df, m, pats, op).values, pats, caliber)
        if not np.isnan(rho) and rho > best_rho:
            best_rho, best = rho, m
    return best


def proc_topk_single(df, pool, pats, caliber, op=OP_GEO, kmax=TOPK_SINGLE_KMAX):
    """内层单工具 ρ̄ top-k (k=1..kmax), 取内层融合 ρ̄ 最大的 k。"""
    ranked = _topn_single(df, pool, pats, caliber, kmax)
    best, best_rho = [], -np.inf
    for k in range(1, len(ranked) + 1):
        members = ranked[:k]
        rho = _guard_rho(df, fusion_score_op(df, members, pats, op).values, pats, caliber)
        if not np.isnan(rho) and rho > best_rho:
            best_rho, best = rho, list(members)
    return best


def _decorr_penalty(corr, t, members):
    """去相关惩罚 = max_{s∈members}|corr(t,s)|。首成员/不在阵内(DeepNetBim) 惩罚 0。"""
    if not members or t not in corr.columns:
        return 0.0
    vals = [abs(corr.loc[t, s]) for s in members if s in corr.columns and s in corr.index]
    return max(vals) if vals else 0.0


def proc_decorr_greedy(df, pool, pats, caliber, corr, lam, op=OP_GEO, eps=EPS, maxdim=MAXDIM):
    """去相关贪心 (skeptic🟠③堵两泄漏口): 选择 score(t)=ρ̄_inner(op(members+[t])) − λ·max|corr(t,s)|;
    corr 来自全 130 肽 spearman_corr (feature-feature, 非标签泄漏)。
    ★ 用 penalized score 挑候选, 但接受门仍卡原始 ρ̄ 提升 (>cur+eps) → 保持是合格停止的贪心。"""
    members, remaining, cur = [], list(pool), 0.0
    while len(members) < maxdim and remaining:
        best_t, best_score, best_rho = None, -np.inf, None
        for t in remaining:
            rho = _guard_rho(df, fusion_score_op(df, members + [t], pats, op).values, pats, caliber)
            if np.isnan(rho):
                continue
            score = rho - lam * _decorr_penalty(corr, t, members)
            if score > best_score:
                best_score, best_t, best_rho = score, t, rho
        if best_t is None or not (best_rho > cur + eps):
            break
        members.append(best_t)
        remaining.remove(best_t)
        cur = best_rho
    return members


# ═══════════════════════════════════════════════════════════════════════════════
# 联合选 (子集×算子) (A2, skeptic🟠①): 对 op_set 每算子跑贪心, 取内层 ρ̄ 最大 (算子, 成员)
# ═══════════════════════════════════════════════════════════════════════════════

def joint_select(df, pool, pats, caliber, op_set, eps=EPS, maxdim=MAXDIM):
    """联合选: 引入算子自由度 → 膨胀应 ≥ 固定算子。返回 (members, best_op, best_rho)。"""
    best_m, best_op, best_rho = [], op_set[0], -np.inf
    for op in op_set:
        m, rho, _ = greedy_members_op(df, pool, pats, caliber, eps, maxdim, op)
        if m and rho > best_rho:
            best_m, best_op, best_rho = m, op, rho
    return best_m, best_op, best_rho


# ═══════════════════════════════════════════════════════════════════════════════
# CV-honest 装配 (外层 9 折) + oracle (全 9 in-sample) + 最强单工具 CV 预测
# ═══════════════════════════════════════════════════════════════════════════════

def cv_pred_from_selector(df, pool, pats, caliber, op, select_members):
    """外层 9 折 CV-honest 融合预测向量: 每折内层 8 患者跑 select_members, 留出患者 p 填
    fusion_score_op(df, members_f, [p], op)。返回 (cv_pred Series, {p: members_f})。"""
    cv = pd.Series(np.nan, index=df.index, dtype=float)
    fold_members = {}
    for p in pats:
        inner = [q for q in pats if q != p]
        m = select_members(df, pool, inner, caliber)
        fold_members[p] = m
        idx = df.index[df["Patient_ID"] == p]
        if m:
            cv.loc[idx] = fusion_score_op(df, m, [p], op).loc[idx].values
    return cv, fold_members


def oracle_pred_from_selector(df, pool, pats, caliber, op, select_members):
    """oracle 对照: 全 9 患者 in-sample 选成员 + in-sample 评估 (作弊上界)。返回 (vals, members)。"""
    m = select_members(df, pool, pats, caliber)
    if m:
        return fusion_score_op(df, m, pats, op).values, m
    return np.full(len(df), np.nan), m


def cv_single_pred(df, pool, pats, caliber):
    """外层 9 折最强单工具 CV 预测 (每折内层选 best_single, 留出患者填该工具 <t>_max)。"""
    pred = pd.Series(np.nan, index=df.index, dtype=float)
    for p in pats:
        inner = [q for q in pats if q != p]
        t, _ = fn.best_single(df, pool, inner, caliber)
        idx = df.index[df["Patient_ID"] == p]
        if t:
            pred.loc[idx] = df.loc[idx, C.pool_col(t, "max")].values
    return pred


# ── 联合选的 CV / oracle 装配 (算子逐折变) ────────────────────────────────────
def cv_pred_joint(df, pool, pats, caliber, op_set, eps=EPS, maxdim=MAXDIM):
    cv = pd.Series(np.nan, index=df.index, dtype=float)
    fold_ops = {}
    for p in pats:
        inner = [q for q in pats if q != p]
        m, op, _ = joint_select(df, pool, inner, caliber, op_set, eps, maxdim)
        fold_ops[p] = op
        idx = df.index[df["Patient_ID"] == p]
        if m:
            cv.loc[idx] = fusion_score_op(df, m, [p], op).loc[idx].values
    return cv, fold_ops


def oracle_joint(df, pool, pats, caliber, op_set, eps=EPS, maxdim=MAXDIM):
    m, op, _ = joint_select(df, pool, pats, caliber, op_set, eps, maxdim)
    if m:
        return fusion_score_op(df, m, pats, op).values, m, op
    return np.full(len(df), np.nan), m, op


# ═══════════════════════════════════════════════════════════════════════════════
# 指标打包 (给一个 config 算 cv/oracle/inflation/paired/delta + 留下 CV per-patient ρ 向量)
# ═══════════════════════════════════════════════════════════════════════════════

def score_metrics(df, pats, caliber, cv_pred, oracle_vals, oracle_members, single_cv, meta,
                  n_boot=N_BOOT, seed=SEED):
    """给定已装配好的 cv_pred / oracle_vals / oracle_members / single_cv, 算所有 CV 指标。
    返回 (row_dict[不含 indistinguishable/interpretation], rhos_by, ns_by[CV per-patient ρ 向量])。
    meta = dict(procedure, arm, op_set, lambda, caliber)。"""
    r = _lean_from_df(df, np.asarray(cv_pred, float), pats, caliber, return_perpat=True)
    cv_rho, rhos_by, ns_by = r[0], r[5], r[6]
    _, ci_lo, ci_hi = fn.guarded_bootstrap_ci(rhos_by, ns_by, pats, n_boot, seed)
    oracle_rho = _lean_from_df(df, np.asarray(oracle_vals, float), pats, caliber)[0]
    rs = _lean_from_df(df, np.asarray(single_cv, float), pats, caliber, return_perpat=True)
    single_rho, rhos_s, ns_s = rs[0], rs[5], rs[6]
    _dz, paired_p, _K = fn.guarded_paired_test(rhos_by, ns_by, rhos_s, ns_s, pats, seed)
    row = {**meta,
           "k_selected": len(oracle_members),
           "members_selected": ";".join(oracle_members),
           "cv_rho": C.r6(cv_rho), "cv_ci_lo": C.r6(ci_lo), "cv_ci_hi": C.r6(ci_hi),
           "oracle_rho": C.r6(oracle_rho), "inflation": C.r6(fn._sub(oracle_rho, cv_rho)),
           "paired_p_vs_best_single": C.r6(paired_p),
           "delta_vs_best_single": C.r6(fn._sub(cv_rho, single_rho))}
    return row, rhos_by, ns_by


# ═══════════════════════════════════════════════════════════════════════════════
# A6 统计不可分带: 枚举所有候选 config 的 CV per-patient ρ 向量, 判与 CV 最优不可分
# ═══════════════════════════════════════════════════════════════════════════════

def indistinguishable_band(configs, pats, seed=SEED, n_boot=N_BOOT):
    """configs: list of dict(label, cv_rho, rhos_by, ns_by)。
    CV 最优 = cv_rho 最大者; 判「与 CV 最优不可分」= (a) guarded_paired_test p>0.05 或
    (b) bootstrap 95%CI 重叠。返回 (best_idx, band_idx_list, detail[label->(p, overlap)])。
    ★ 不宣称唯一最优; 报 band 大小 + 是否连最强单工具(MHCnuggets)都区分不了。"""
    valid = [i for i, c in enumerate(configs)
             if c["cv_rho"] is not None and not (isinstance(c["cv_rho"], float) and np.isnan(c["cv_rho"]))]
    if not valid:
        return None, [], {}
    best_idx = max(valid, key=lambda i: configs[i]["cv_rho"])
    best = configs[best_idx]
    _, blo, bhi = fn.guarded_bootstrap_ci(best["rhos_by"], best["ns_by"], pats, n_boot, seed)
    band, detail = [], {}
    for i in valid:
        c = configs[i]
        if i == best_idx:
            band.append(i)
            detail[c["label"]] = (1.0, True)
            continue
        _dz, p, _K = fn.guarded_paired_test(best["rhos_by"], best["ns_by"],
                                            c["rhos_by"], c["ns_by"], pats, seed)
        _, clo, chi = fn.guarded_bootstrap_ci(c["rhos_by"], c["ns_by"], pats, n_boot, seed)
        overlap = not (bhi < clo or chi < blo)
        in_band = (p is not None and not np.isnan(p) and p > 0.05) or overlap
        detail[c["label"]] = (p, overlap)
        if in_band:
            band.append(i)
    return best_idx, band, detail


def _interp(cv_rho, single_rho, paired_p, in_band, is_best):
    """预登记结果解读 (禁 proven optimal/best/SOTA; null 写「无可检测的整合净优势」)。"""
    delta = fn._sub(cv_rho, single_rho)
    ds = f"Δvs单={delta:+.4f}" if delta is not None and not np.isnan(delta) else "Δvs单=NaN"
    ps = f"p={paired_p:.4f}" if paired_p is not None and not np.isnan(paired_p) else "p=NaN"
    band_tag = "在CV最优不可分带内" if in_band else "带外(可区分较差)"
    if is_best:
        return f"CV-最优 config ({ds}, {ps}); 非唯一最优, 见 indistinguishable_set_size"
    if delta is None or np.isnan(delta) or paired_p is None or np.isnan(paired_p) or paired_p >= 0.05 or delta <= 0:
        return f"无可检测的整合净优势 ({ds}, {ps}); {band_tag}"
    return f"见净优势 ({ds}, {ps}), 佐证性; {band_tag}"


# ═══════════════════════════════════════════════════════════════════════════════
# A1 k 学习曲线
# ═══════════════════════════════════════════════════════════════════════════════

def _modal_members(fold_members):
    """跨折成员集众数 + 众数占比 (frac = 该集出现折数 / 有非空选集的折数)。"""
    keys = [";".join(sorted(m)) for m in fold_members.values() if m]
    if not keys:
        return "", 0.0
    cnt = Counter(keys)
    top, n = cnt.most_common(1)[0]
    return top, round(n / len(fold_members), 4)


def _a1_row(df, pats, caliber, mode, k, fold_members, oracle_members, op, single_cv, seed):
    """装配一个 A1 k-curve 行 + 供 band 用的 config。fold_members = {p: members_f (已截到 k)}。"""
    cv = pd.Series(np.nan, index=df.index, dtype=float)
    for p, m in fold_members.items():
        idx = df.index[df["Patient_ID"] == p]
        if m:
            cv.loc[idx] = fusion_score_op(df, m, [p], op).loc[idx].values
    r = _lean_from_df(df, cv.values, pats, caliber, return_perpat=True)
    cv_rho, n_used, rhos_by, ns_by = r[0], r[3], r[5], r[6]
    _, ci_lo, ci_hi = fn.guarded_bootstrap_ci(rhos_by, ns_by, pats, N_BOOT, seed)
    orc_vals = (fusion_score_op(df, oracle_members, pats, op).values
                if oracle_members else np.full(len(df), np.nan))
    oracle_rho = _lean_from_df(df, orc_vals, pats, caliber)[0]
    rs = _lean_from_df(df, single_cv.values, pats, caliber, return_perpat=True)
    rhos_s, ns_s = rs[5], rs[6]
    _dz, paired_p, _K = fn.guarded_paired_test(rhos_by, ns_by, rhos_s, ns_s, pats, seed)
    modal, frac = _modal_members(fold_members)
    note = "lenctrl敏感性(不联合选)" if caliber == "lenctrl" else ""
    row = dict(k=k, caliber=caliber, select_mode=mode,
               cv_rho=C.r6(cv_rho), cv_ci_lo=C.r6(ci_lo), cv_ci_hi=C.r6(ci_hi),
               oracle_rho=C.r6(oracle_rho), inflation=C.r6(fn._sub(oracle_rho, cv_rho)),
               n_folds_used=int(n_used) if n_used is not None else 0,
               paired_p_vs_best_single=C.r6(paired_p),
               modal_members=modal, member_stability_frac=frac, note=note)
    cfg = dict(label=f"A1:{mode}:k{k}:{caliber}", cv_rho=cv_rho, rhos_by=rhos_by, ns_by=ns_by)
    return row, cfg


def build_k_curve(df, pool, pats, single_by_caliber, seed=SEED):
    """A1: greedy_to_k (关eps跑满k=1..8, raw+lenctrl) + exhaustive_topk (k≤3, raw)。
    inflation(k)=oracle−cv。top-10 预筛在内层8患者做, oracle 臂在全9。返回 (rows, band_configs)。"""
    rows, configs = [], []
    # ── greedy_to_k: 一次算强制贪心路径, 前缀即各 k ──
    for caliber in CALIBERS:
        single_cv = single_by_caliber[caliber]
        oracle_path = greedy_path_op(df, pool, pats, caliber, OP_GEO, KCURVE_KMAX)
        fold_paths = {p: greedy_path_op(df, pool, [q for q in pats if q != p], caliber, OP_GEO, KCURVE_KMAX)
                      for p in pats}
        for k in range(1, KCURVE_KMAX + 1):
            fold_members = {p: fold_paths[p][:k] for p in pats}
            oracle_members = oracle_path[:k]
            row, cfg = _a1_row(df, pats, caliber, "greedy_to_k", k, fold_members,
                               oracle_members, OP_GEO, single_cv, seed)
            rows.append(row)
            configs.append(cfg)
    # ── exhaustive_topk (raw only, k≤3) ──
    caliber = "raw"
    single_cv = single_by_caliber[caliber]
    for k in range(1, EXHAUST_KMAX + 1):
        fold_members = {p: _exhaust_best_k(df, pool, [q for q in pats if q != p], caliber, OP_GEO, k, TOPN_EXHAUST)
                        for p in pats}
        oracle_members = _exhaust_best_k(df, pool, pats, caliber, OP_GEO, k, TOPN_EXHAUST)
        row, cfg = _a1_row(df, pats, caliber, "exhaustive_topk", k, fold_members,
                           oracle_members, OP_GEO, single_cv, seed)
        rows.append(row)
        configs.append(cfg)
    return rows, configs


# ═══════════════════════════════════════════════════════════════════════════════
# A2 联合选(子集×算子) + A3 选择程序横比 → select_engine.csv 行
# ═══════════════════════════════════════════════════════════════════════════════

def build_a2(df, pool, pats, single_cv, seed=SEED):
    """A2 (raw): joint_all8 / joint_consensus3 / fixed_geomean / op_<name>_subsetsel×8。
    三护栏: ①每算子分开 subset-sel 曲线; ②inflation_joint vs inflation_fixed_geomean; ③all8/consensus3。"""
    rows, configs = [], []
    caliber = "raw"

    # ③ 两版联合选 (all8 / consensus3)
    for arm, op_set, opset_name in [("joint_all8", OP_ALL8, "all8"),
                                    ("joint_consensus3", OP_CONSENSUS3, "consensus3")]:
        cv, _ops = cv_pred_joint(df, pool, pats, caliber, op_set)
        orc_vals, orc_members, _orc_op = oracle_joint(df, pool, pats, caliber, op_set)
        meta = dict(procedure="joint_select", arm=arm, op_set=opset_name,
                    **{"lambda": np.nan}, caliber=caliber)
        row, rby, nby = score_metrics(df, pats, caliber, cv, orc_vals, orc_members, single_cv, meta, seed=seed)
        rows.append(row)
        configs.append(dict(label=f"A2:{arm}", cv_rho=_rho_of(row), rhos_by=rby, ns_by=nby))

    # ② fixed_geomean 对照 (固定算子, 前向贪心)
    cv, _ = cv_pred_from_selector(df, pool, pats, caliber, OP_GEO, proc_forward_greedy)
    orc_vals, orc_members = oracle_pred_from_selector(df, pool, pats, caliber, OP_GEO, proc_forward_greedy)
    meta = dict(procedure="fixed_geomean", arm="fixed_geomean", op_set="geomean",
                **{"lambda": np.nan}, caliber=caliber)
    row, rby, nby = score_metrics(df, pats, caliber, cv, orc_vals, orc_members, single_cv, meta, seed=seed)
    rows.append(row)
    configs.append(dict(label="A2:fixed_geomean", cv_rho=_rho_of(row), rhos_by=rby, ns_by=nby))

    # ① 每算子分开的 subset-selected 曲线 (前向贪心, 该算子固定)
    for op in OP_ALL8:
        sel = lambda d, pl, pa, cal, _op=op: greedy_members_op(d, pl, pa, cal, EPS, MAXDIM, _op)[0]
        cv, _ = cv_pred_from_selector(df, pool, pats, caliber, op, sel)
        orc_vals, orc_members = oracle_pred_from_selector(df, pool, pats, caliber, op, sel)
        meta = dict(procedure="op_subsetsel", arm=f"op_{op}_subsetsel", op_set=op,
                    **{"lambda": np.nan}, caliber=caliber)
        row, rby, nby = score_metrics(df, pats, caliber, cv, orc_vals, orc_members, single_cv, meta, seed=seed)
        rows.append(row)
        configs.append(dict(label=f"A2:op_{op}_subsetsel", cv_rho=_rho_of(row), rhos_by=rby, ns_by=nby))
    return rows, configs


def build_a3(df, pool, pats, single_cv, corr, seed=SEED):
    """A3 (raw, op 固定 geomean): forward_greedy / backward_elim / exhaustive_k≤3 / topk_single /
    decorr_greedy×λ{0.05,0.10,0.20}。隔离『程序』变量。"""
    rows, configs = [], []
    caliber = "raw"
    procs = [
        ("forward_greedy", proc_forward_greedy, np.nan),
        ("backward_elim", proc_backward_elim, np.nan),
        ("exhaustive_k", proc_exhaustive_k, np.nan),
        ("topk_single", proc_topk_single, np.nan),
    ]
    for pname, sel, lam in procs:
        cv, _ = cv_pred_from_selector(df, pool, pats, caliber, OP_GEO, sel)
        orc_vals, orc_members = oracle_pred_from_selector(df, pool, pats, caliber, OP_GEO, sel)
        meta = dict(procedure=pname, arm=pname, op_set="geomean", **{"lambda": lam}, caliber=caliber)
        row, rby, nby = score_metrics(df, pats, caliber, cv, orc_vals, orc_members, single_cv, meta, seed=seed)
        rows.append(row)
        configs.append(dict(label=f"A3:{pname}", cv_rho=_rho_of(row), rhos_by=rby, ns_by=nby))

    # 去相关贪心: λ 固定先验扫, 每 λ 一行, 绝不用外层 ρ̄ 挑 λ
    for lam in DECORR_LAMBDAS:
        sel = lambda d, pl, pa, cal, _lam=lam: proc_decorr_greedy(d, pl, pa, cal, corr, _lam)
        cv, _ = cv_pred_from_selector(df, pool, pats, caliber, OP_GEO, sel)
        orc_vals, orc_members = oracle_pred_from_selector(df, pool, pats, caliber, OP_GEO, sel)
        arm = f"decorr_greedy_lam{lam:g}" + ("_main" if abs(lam - DECORR_MAIN_LAMBDA) < 1e-12 else "")
        meta = dict(procedure="decorr_greedy", arm=arm, op_set="geomean",
                    **{"lambda": lam}, caliber=caliber)
        row, rby, nby = score_metrics(df, pats, caliber, cv, orc_vals, orc_members, single_cv, meta, seed=seed)
        rows.append(row)
        configs.append(dict(label=f"A3:{arm}", cv_rho=_rho_of(row), rhos_by=rby, ns_by=nby))
    return rows, configs


def _rho_of(row):
    """从已 r6 的 row 取 cv_rho float (给 band 排序; NaN 保留)。"""
    v = row.get("cv_rho")
    return float(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else np.nan


# ═══════════════════════════════════════════════════════════════════════════════
# A4 稳定性选择 (cluster bootstrap 入选频率 + 算子 churn)
# ═══════════════════════════════════════════════════════════════════════════════

def build_stability(df, pool, pats, B=STAB_B, seed=SEED):
    """A4: 外层 9 折 × 每折内层 8 患者 cluster bootstrap B 跑 forward_greedy(geomean) 记成员 →
    入选频率 = 选中次数/(9×B)。共识阈 π∈{0.5,0.6(主),0.8}。加算子 churn (联合选每折选中算子)。"""
    rng = np.random.default_rng(seed)
    boot_counts = {t: 0 for t in pool}
    total = 0
    for p in pats:
        inner = [q for q in pats if q != p]
        for _ in range(B):
            samp = rng.integers(0, len(inner), size=len(inner))
            bpats = [inner[i] for i in samp]                   # 有放回重采样内层患者 (允许重复)
            m = greedy_members_op(df, pool, bpats, "raw", EPS, MAXDIM, OP_GEO)[0]
            for t in m:
                boot_counts[t] += 1
            total += 1

    # 9 折朴素入选频率 + 各工具跨折内层单工具 ρ̄ 均值
    fold_counts = {t: 0 for t in pool}
    single_by_fold = defaultdict(list)
    op_counts = Counter()
    for p in pats:
        inner = [q for q in pats if q != p]
        for t in proc_forward_greedy(df, pool, inner, "raw"):
            fold_counts[t] += 1
        for t, v in single_rhos(df, pool, inner, "raw").items():
            single_by_fold[t].append(v)
        _m, op, _ = joint_select(df, pool, inner, "raw", OP_ALL8)   # 算子 churn
        op_counts[op] += 1

    rows = []
    for t in pool:
        fb = boot_counts[t] / total if total else np.nan
        f9 = fold_counts[t] / len(pats)
        rows.append(dict(
            tool=t, category=TC.category(t), is_dtu=(t in C.DTU_TOOLS),
            select_freq_boot=C.r6(fb), select_freq_9fold=C.r6(f9),
            in_consensus_0p5=bool(fb >= 0.5), in_consensus_0p6=bool(fb >= 0.6),
            in_consensus_0p8=bool(fb >= 0.8),
            mean_single_rho_inner=C.r6(np.mean(single_by_fold[t]) if single_by_fold[t] else np.nan)))
    rows.sort(key=lambda r: -(r["select_freq_boot"] if r["select_freq_boot"] is not None
                              and not np.isnan(r["select_freq_boot"]) else -1))

    # 算子 churn 行块 (tool 列打 __op_churn__:<op>, select_freq_9fold=被选折数/9)
    churn_rows = []
    for op in OP_ALL8:
        churn_rows.append(dict(
            tool=f"__op_churn__:{op}", category="operator", is_dtu=False,
            select_freq_boot=np.nan, select_freq_9fold=C.r6(op_counts.get(op, 0) / len(pats)),
            in_consensus_0p5=np.nan, in_consensus_0p6=np.nan, in_consensus_0p8=np.nan,
            mean_single_rho_inner=np.nan))
    geo_frac = op_counts.get(OP_GEO, 0) / len(pats)
    print(f"[A4] 算子 churn: geomean 占 {geo_frac:.2%} 折; 各算子={dict(op_counts)}")
    return rows + churn_rows


# ═══════════════════════════════════════════════════════════════════════════════
# A5 两个正交 null (随机 k-子集 + 患者内置换, skeptic🟠④分列标死)
# ═══════════════════════════════════════════════════════════════════════════════

def build_null(df, pool, pats, seed=SEED, R=NULL_R, S=NULL_S, ks=NULL_KS):
    """A5: ①随机 k-子集 null (in-sample 纯评估, 控『从多子集挑』天花板);
           ②患者内置换 null (重跑 CHOSEN=forward_greedy geomean 整条选择, 控选择泄漏 vs 信号)。"""
    rows = []
    # ── ① 随机 k-子集 null (raw, in-sample geomean) ──
    rng = np.random.default_rng(seed)
    poolL = list(pool)
    oracle_path = greedy_path_op(df, poolL, pats, "raw", OP_GEO, max(ks))
    for k in ks:
        if k > len(poolL):
            continue
        vals = []
        for _ in range(R):
            idx = rng.choice(len(poolL), size=k, replace=False)
            members = [poolL[i] for i in idx]
            rho = _guard_rho(df, fusion_score_op(df, members, pats, OP_GEO).values, pats, "raw")
            if not np.isnan(rho):
                vals.append(rho)
        vals = np.array(vals, float)
        # observed = oracle 贪心在 k 的 in-sample geomean ρ̄ (与 null 同 in-sample 口径可比)
        orc_members = oracle_path[:k]
        obs = _guard_rho(df, fusion_score_op(df, orc_members, pats, OP_GEO).values, pats, "raw") if orc_members else np.nan
        perm_p = float(np.mean(vals >= obs)) if len(vals) and not np.isnan(obs) else np.nan
        rows.append(dict(null_type="random_ksubset", k=k, R_or_S=len(vals),
                         null_mean=C.r6(np.nanmean(vals)), null_p95=C.r6(np.nanpercentile(vals, 95)),
                         null_max=C.r6(np.nanmax(vals)), observed_cv_rho=C.r6(obs),
                         perm_p=C.r6(perm_p), caliber="raw"))

    # ── ② 患者内置换 null: 重跑 CHOSEN 程序整条选择 (只对 forward_greedy geomean) ──
    cv_obs, _ = cv_pred_from_selector(df, pool, pats, "raw", OP_GEO, proc_forward_greedy)
    observed_cv = _lean_from_df(df, cv_obs.values, pats, "raw")[0]
    rng2 = np.random.default_rng(seed + 1)
    null = []
    for _ in range(S):
        dfs = df.copy()
        for p in pats:
            idx = dfs.index[dfs["Patient_ID"] == p]
            dfs.loc[idx, C.LABEL_COL] = rng2.permutation(dfs.loc[idx, C.LABEL_COL].values)
        cvp, _ = cv_pred_from_selector(dfs, pool, pats, "raw", OP_GEO, proc_forward_greedy)
        rho = _lean_from_df(dfs, cvp.values, pats, "raw")[0]
        if not np.isnan(rho):
            null.append(rho)
    null = np.array(null, float)
    perm_p = float(np.mean(null >= observed_cv)) if len(null) and not np.isnan(observed_cv) else np.nan
    rows.append(dict(null_type="patient_perm", k=np.nan, R_or_S=len(null),
                     null_mean=C.r6(np.nanmean(null)) if len(null) else np.nan,
                     null_p95=C.r6(np.nanpercentile(null, 95)) if len(null) else np.nan,
                     null_max=C.r6(np.nanmax(null)) if len(null) else np.nan,
                     observed_cv_rho=C.r6(observed_cv), perm_p=C.r6(perm_p), caliber="raw"))
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# CSV 写出
# ═══════════════════════════════════════════════════════════════════════════════

_BOUND = ("# ★诚实边界: n=9 无「唯一最优」确定性证明; 交付=无泄漏 CV 程序 + 选出的(成员×k×算子) "
          "+ 稳定性/不可分带 + 每选择的受控证明。措辞禁 proven optimal/the best/SOTA; "
          "null 写「无可检测的整合净优势」不写「证伪整合优势」。\n")
_CFG = (f"# 口径: 外层 LOPO 9 折; 内层 8 患者选; pooling=_max; 池=cover_pool(≥{COVER_MIN})=24 工具; "
        f"CV 评估全走 guarded_perpat_metric (退化守卫); seed={SEED}; 纯 numpy 禁 scipy.stats。\n")


def _write(path, rows, cols, extra_comments):
    df_out = pd.DataFrame(rows)
    for c in cols:
        if c not in df_out.columns:
            df_out[c] = np.nan
    df_out = df_out[cols]
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(_BOUND)
        f.write(_CFG)
        for line in extra_comments:
            f.write(line)
        df_out.to_csv(f, index=False)
    print(f"[saved] {path} ({len(df_out)} 行)")


K_CURVE_COLS = ["k", "caliber", "select_mode", "cv_rho", "cv_ci_lo", "cv_ci_hi",
                "oracle_rho", "inflation", "n_folds_used", "paired_p_vs_best_single",
                "modal_members", "member_stability_frac", "note"]
ENGINE_COLS = ["procedure", "arm", "op_set", "lambda", "caliber", "k_selected",
               "members_selected", "cv_rho", "cv_ci_lo", "cv_ci_hi", "oracle_rho",
               "inflation", "paired_p_vs_best_single", "delta_vs_best_single",
               "indistinguishable_set_size", "interpretation"]
STAB_COLS = ["tool", "category", "is_dtu", "select_freq_boot", "select_freq_9fold",
             "in_consensus_0p5", "in_consensus_0p6", "in_consensus_0p8", "mean_single_rho_inner"]
NULL_COLS = ["null_type", "k", "R_or_S", "null_mean", "null_p95", "null_max",
             "observed_cv_rho", "perm_p", "caliber"]


def dump_tool_tool_corr(corr, path):
    """A3 去相关用的工具×工具 Spearman 阵 → 长表 tool_a,tool_b,spearman。
    ★ 全 130 肽算一次 (feature-feature, 非标签泄漏; label-free 预处理放松, 不 claim 零泄漏)。"""
    recs = []
    tools = list(corr.columns)
    for i, a in enumerate(tools):
        for b in tools[i + 1:]:
            recs.append(dict(tool_a=a, tool_b=b, spearman=C.r6(corr.loc[a, b])))
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("# tool_tool_corr.csv —— 30 工具 <tool>_max 打分的 per-peptide Spearman 相关 (全130肽)。\n")
        f.write("# ★ feature-feature 相关, 非标签泄漏; 供 A3 decorr_greedy 惩罚项。DeepNetBim 常数列已剔。\n")
        pd.DataFrame(recs)[["tool_a", "tool_b", "spearman"]].to_csv(f, index=False)
    print(f"[saved] {path} ({len(recs)} 对)")


# ═══════════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="QuantImmuBench 原则化 CV 融合选择 Part A (A1-A6)")
    ap.add_argument("--input", default=str(C.FROZEN_POOLED), help="冻结肽级表路径")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--fast", action="store_true", help="降 B/S/R/n_boot 快速冒烟 (非正式结果)")
    ap.add_argument("--selftest", action="store_true",
                    help="只跑 rank 缓存正确性自检 (缓存 fusion ≡ apply_fusion allclose 1e-9) 后退出")
    args = ap.parse_args()

    global STAB_B, NULL_R, NULL_S, N_BOOT
    if args.fast:
        STAB_B, NULL_R, NULL_S, N_BOOT = 20, 100, 20, 500
        print(f"[fast] STAB_B={STAB_B} NULL_R={NULL_R} NULL_S={NULL_S} N_BOOT={N_BOOT} (冒烟, 非正式)")

    df = C.load_frozen(args.input)
    pats = C.present_patients(df)
    all30_present = fn.filter_pool(df, C.TOOLS_30)     # 缓存建全 30 present (cover ⊂ 30, 供 rationale #5 all30)

    if args.selftest:
        selftest_cache(df, all30_present, pats, seed=args.seed)
        selftest_lean(df, pats, seed=args.seed)
        return

    pool, dropped = fn.cover_pool(df, C.TOOLS_30, pats, COVER_MIN)
    build_rank_cache(df, all30_present)                # ★ 一次性建缓存, 后续融合走快路径
    print(f"[info] DS2 患者({len(pats)})={pats}; cover_pool({len(pool)} 工具, 每患者≥{COVER_MIN}肽)")
    print(f"[info] 剔稀疏 ({len(dropped)}): " + ", ".join(f"{t}(min={mn})" for t, mn in sorted(dropped, key=lambda kv: kv[1])))

    # 工具×工具相关阵 (全 130 肽, feature-feature) —— A3 decorr 用 + dump
    scores = TC.load_max_scores(args.input)
    corr, corr_dropped = TC.spearman_corr(scores)
    print(f"[info] tool-tool corr: {corr.shape[0]} 工具入阵 (剔 {corr_dropped})")
    dump_tool_tool_corr(corr, HERE / "tool_tool_corr.csv")

    # 最强单工具 CV 预测 (两口径各一份, 复用给所有臂)
    single_by_caliber = {cal: cv_single_pred(df, pool, pats, cal) for cal in CALIBERS}

    # ── A1 k 学习曲线 ──
    print("\n[A1] k 学习曲线 (greedy_to_k raw+lenctrl + exhaustive_topk raw) ...")
    k_rows, a1_cfgs = build_k_curve(df, pool, pats, single_by_caliber, args.seed)
    _write(HERE / "k_curve.csv", k_rows, K_CURVE_COLS,
           ["# A1: greedy_to_k(关eps跑满k=1..8) + exhaustive_topk(k≤3,内层top-10穷举C(10,k)); "
            "inflation(k)=oracle−cv; oracle 臂全9 in-sample, top-10 预筛在内层8。\n"])

    # ── A2 联合选 + A3 程序横比 → select_engine.csv ──
    print("[A2] 联合选 (子集×算子) ...")
    a2_rows, a2_cfgs = build_a2(df, pool, pats, single_by_caliber["raw"], args.seed)
    print("[A3] 选择程序横比 (op 固定 geomean) ...")
    a3_rows, a3_cfgs = build_a3(df, pool, pats, single_by_caliber["raw"], corr, args.seed)

    engine_rows = a2_rows + a3_rows
    engine_cfgs = a2_cfgs + a3_cfgs             # 与 engine_rows 一一对齐 (A2 在前 A3 在后)
    band_cfgs = a1_cfgs + engine_cfgs           # band 候选 = A1∪A2∪A3

    # ── 最强单工具作为 band 候选 (必报「连 MHCnuggets 都区分不了否」) ──
    rs = _lean_from_df(df, single_by_caliber["raw"].values, pats, "raw", return_perpat=True)
    best_single_cfg = dict(label="best_single_cv", cv_rho=rs[0], rhos_by=rs[5], ns_by=rs[6])
    band_input = band_cfgs + [best_single_cfg]

    # ── A6 统计不可分带 ──
    print("[A6] 统计不可分带 ...")
    best_idx, band, detail = indistinguishable_band(band_input, pats, args.seed, N_BOOT)
    band_size = len(band)
    best_label = band_input[best_idx]["label"] if best_idx is not None else "NA"
    single_p, single_overlap = detail.get("best_single_cv", (np.nan, False))
    single_in_band = "best_single_cv" in [band_input[i]["label"] for i in band]
    print(f"[A6] CV-最优={best_label}; indistinguishable_set_size={band_size}; "
          f"连 best_single 都不可分? {single_in_band} (p={single_p}, CI重叠={single_overlap})")

    # 填 select_engine.csv 的 indistinguishable_set_size (全局带大小) + interpretation
    band_labels = set(band_input[i]["label"] for i in band)
    single_rho_raw = best_single_cfg["cv_rho"]
    for row, cfg in zip(engine_rows, engine_cfgs):
        in_band = cfg["label"] in band_labels
        is_best = cfg["label"] == best_label
        cv_rho = _rho_of(row)
        pp = row["paired_p_vs_best_single"]
        pp = float(pp) if pp is not None and not (isinstance(pp, float) and np.isnan(pp)) else np.nan
        row["indistinguishable_set_size"] = band_size
        row["interpretation"] = _interp(cv_rho, single_rho_raw, pp, in_band, is_best)
    _write(HERE / "select_engine.csv", engine_rows, ENGINE_COLS,
           [f"# A2(joint_all8/consensus3/fixed_geomean/op_*_subsetsel) + A3(forward/backward/exhaustive/"
            f"topk/decorr×λ{DECORR_LAMBDAS}主{DECORR_MAIN_LAMBDA}); op 固定 geomean(除A2)。\n",
            f"# indistinguishable_set_size={band_size} (全局: A1∪A2∪A3∪best_single 中与 CV-最优 "
            f"paired-p>0.05 或 bootstrap-CI 重叠者); CV-最优={best_label}; "
            f"连 best_single 都不可分={single_in_band}。\n",
            "# lambda 仅 decorr_greedy 有值 (固定先验扫, 绝不用外层ρ̄挑λ); 其余 NaN。\n"])

    # ── A4 稳定性 ──
    print(f"[A4] 稳定性选择 (cluster bootstrap B={STAB_B}) ...")
    stab_rows = build_stability(df, pool, pats, STAB_B, args.seed)
    _write(HERE / "select_stability.csv", stab_rows, STAB_COLS,
           [f"# A4: 外层9折×每折内层8患者 cluster bootstrap B={STAB_B} 跑 forward_greedy(geomean) 记成员; "
            f"select_freq_boot=选中/(9×B); 共识阈 π∈{{0.5,0.6主,0.8}}。\n",
            "# 末尾 __op_churn__:<op> 行块 = 联合选每折选中算子占比 (select_freq_9fold)。\n"])

    # ── A5 两 null ──
    print(f"[A5] 两个正交 null (随机k-子集 R={NULL_R} + 患者内置换 S={NULL_S}) ...")
    null_rows = build_null(df, pool, pats, args.seed, NULL_R, NULL_S)
    _write(HERE / "select_null.csv", null_rows, NULL_COLS,
           ["# A5①random_ksubset: 每k从cover池随机抽R子集 in-sample geomean ρ̄ null (控『从多子集挑』天花板); "
            "observed=oracle贪心k的in-sample ρ̄; perm_p=P(null≥observed)。\n",
            "# A5②patient_perm: 患者内打乱Elispot重跑CHOSEN=forward_greedy(geomean)整条选择, S次; "
            "observed_cv_rho=真CV; perm_p=P(null≥observed) (控选择泄漏vs信号)。\n"])

    print("\n[DONE] select_engine (A1-A6) —— 主线可跑; 结论冲突(CV说小k/单工具最优 vs SURV6)= 拍板点报袁+朱。")


if __name__ == "__main__":
    main()
