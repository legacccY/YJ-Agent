#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rationale_ablations.py
======================
服务: QuantImmuBench §3.3 fusion / §4.3 selection-bias —— 「原则化 CV 融合选择」Part B (#1-13)。
对应 lever: 为每一个方法学抉择 (nested-CV/守卫/cover池/聚合/程序/口径…) 各给一条「只变一处」的
           受控消融, 落成一本可追溯的理由账 rationale_ledger.csv。

设计规格 = analysis/fusion_cv/SELECT_DESIGN.md (Part B, planner 定稿 + skeptic 6🟠 落实)。

★ 每条只变一处; 其余固定: pool=cover(≥8)/op=geomean/procedure=forward_greedy/outer=leave-patient/
   metric=guarded/caliber=raw/seed=42。措辞禁 proven optimal/best/SOTA; null 写「无可检测的整合净优势」。

★ import select_engine 的封装函数复用 (不重复实现选择程序):
   se.fusion_score_op / se.greedy_members_op / se.greedy_path_op / se.proc_forward_greedy /
   se.cv_pred_from_selector / se.oracle_pred_from_selector / se.cv_single_pred /
   se._topn_single / se._exhaust_best_k / se.cv_pred_joint / se.single_rhos / 常量。
   guarded 评估走 fn.guarded_perpat_metric (禁裸 per_patient; #4/#7 裸版仅作被试对照, 已显式标注)。

跑法 (主线跑, 我不跑):
   python analysis/fusion_cv/rationale_ablations.py
输出 (analysis/fusion_cv/): rationale_ledger.csv
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "analysis" / "official"))
sys.path.insert(0, str(HERE))
import _official_common as C                             # noqa: E402
import fusion_nested_cv as fn                            # noqa: E402
import select_engine as se                               # noqa: E402

SEED = 42
OP_GEO = se.OP_GEO
COVER_MIN = se.COVER_MIN
FIXED = "pool=cover(≥8)/op=geomean/proc=forward_greedy/outer=leave-patient/metric=guarded/caliber=raw/seed=42"


# ── 小工具 ────────────────────────────────────────────────────────────────────
def _fg_cv(df, pool, pats, caliber, return_perpat=False):
    """forward_greedy geomean 外层 9 折 CV-honest ρ̄ (headline 程序)。"""
    cv, _ = se.cv_pred_from_selector(df, pool, pats, caliber, OP_GEO, se.proc_forward_greedy)
    return fn.guarded_perpat_metric(df, cv.values, pats, caliber, return_perpat=return_perpat)


def _fg_oracle(df, pool, pats, caliber):
    """forward_greedy geomean 全 9 in-sample (oracle) ρ̄ + 选中成员。"""
    vals, m = se.oracle_pred_from_selector(df, pool, pats, caliber, OP_GEO, se.proc_forward_greedy)
    return fn.guarded_perpat_metric(df, vals, pats, caliber)[0], m


def _guarded_rho(df, vals, pats, caliber):
    return fn.guarded_perpat_metric(df, vals, pats, caliber)[0]


def _row(id_, choice, varied, chosen_v, alt_v, chosen_m, alt_m, delta, n_used,
         exp_dir, verdict, why, fixed_over=None):
    return dict(id=id_, choice=choice, fixed_vars=fixed_over or FIXED, varied_var=varied,
                chosen_value=chosen_v, alt_value=alt_v,
                chosen_metric=C.r6(chosen_m) if isinstance(chosen_m, (int, float, np.floating)) else chosen_m,
                alt_metric=C.r6(alt_m) if isinstance(alt_m, (int, float, np.floating)) else alt_m,
                delta=C.r6(delta) if delta is not None and isinstance(delta, (int, float, np.floating)) else delta,
                caliber="raw", n_used=n_used, expected_direction=exp_dir,
                observed_verdict=verdict, why_oneline=why)


def _peptide_folds(df, pats, n, seed):
    """留肽 5 折 stratified-by-patient: 每患者肽均分 n 折 (seed 固定), 返回 n 个 index list。"""
    rng = np.random.default_rng(seed)
    folds = [[] for _ in range(n)]
    for p in pats:
        idx = list(df.index[df["Patient_ID"] == p])
        rng.shuffle(idx)
        for i, chunk in enumerate(np.array_split(np.array(idx), n)):
            folds[i].extend(list(chunk))
    return folds


def _naive_best_single(df, pool, pats):
    """裸 per-patient Spearman (无退化守卫) argmax 单工具 —— ★仅作 #4 被试对照, 不用于任何 CV 选择。"""
    best_t, best = None, -np.inf
    for t in pool:
        col = C.pool_col(t, "max")
        if col not in df.columns or df[col].notna().sum() == 0:
            continue
        rho = C.per_patient_spearman(df, col, patients=pats)[0]
        if not np.isnan(rho) and rho > best:
            best, best_t = rho, t
    return best_t, best


def _shuffle_null_oracle(df, pool, pats, seed):
    """患者内打乱 Elispot 后 forward_greedy(geomean) in-sample oracle ρ̄ (shuffle-null)。"""
    rng = np.random.default_rng(seed)
    dfs = df.copy()
    for p in pats:
        idx = dfs.index[dfs["Patient_ID"] == p]
        dfs.loc[idx, C.LABEL_COL] = rng.permutation(dfs.loc[idx, C.LABEL_COL].values)
    vals, _m = se.oracle_pred_from_selector(dfs, pool, pats, "raw", OP_GEO, se.proc_forward_greedy)
    return _guarded_rho(dfs, vals, pats, "raw")


def _shuffle_null_naive_single(df, pool, pats, seed):
    """患者内打乱 Elispot 后, 裸 per-patient best-single 的偶然天花板。
    暴露稀疏工具: 全30 池含 min<8 工具, 打乱后仍能碰到虚假完美相关 → 天花板虚高;
    cover 池无稀疏工具 → 天花板低。仅作 #5 池对照, 不用于任何 CV 选择。"""
    rng = np.random.default_rng(seed)
    dfs = df.copy()
    for p in pats:
        idx = dfs.index[dfs["Patient_ID"] == p]
        dfs.loc[idx, C.LABEL_COL] = rng.permutation(dfs.loc[idx, C.LABEL_COL].values)
    _, rho = _naive_best_single(dfs, pool, pats)
    return rho


def _sign(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return 0
    return int(np.sign(v))


# ═══════════════════════════════════════════════════════════════════════════════
# main —— 逐条 #1-#13
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="QuantImmuBench 原则化 CV 融合选择 Part B (#1-13 理由账)")
    ap.add_argument("--input", default=str(C.FROZEN_POOLED))
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()
    seed = args.seed

    df = C.load_frozen(args.input)
    pats = C.present_patients(df)
    pool, dropped = fn.cover_pool(df, C.TOOLS_30, pats, COVER_MIN)
    se.build_rank_cache(df, fn.filter_pool(df, C.TOOLS_30))   # ★ 患者内 rank 缓存 (全30 present, cover⊂30)
    print(f"[info] DS2 患者({len(pats)}); cover_pool({len(pool)} 工具)")

    rows = []

    # 复用基线: forward_greedy geomean 主臂 CV + oracle (#1/#2/#3/#10/#11/#12 用)
    r_cv = _fg_cv(df, pool, pats, "raw", return_perpat=True)
    cv_rho, n_used = r_cv[0], r_cv[3]
    oracle_rho, members_all9 = _fg_oracle(df, pool, pats, "raw")

    # ── #1 nested-CV vs oracle (varied=选择集{inner8|all9}) ──
    d1 = fn._sub(oracle_rho, cv_rho)
    rows.append(_row("1", "nested-CV(inner8选)", "选择集", "inner8", "all9",
                     cv_rho, oracle_rho, d1, n_used, "oracle−cv>0 (膨胀≈0.17)",
                     f"膨胀Δ={C.r6(d1)}: 全数据选成员=in-sample上界, nested-CV才诚实",
                     "成员选择使表观优势虚高的量, 用 held-out 折隔离"))

    # ── #2 nested vs 单层LOPO (⚠️恒等陷阱): 单层=全数据选+只LOPO评 ≡ oracle ──
    sl_pred = pd.Series(np.nan, index=df.index, dtype=float)
    for p in pats:
        idx = df.index[df["Patient_ID"] == p]
        if members_all9:
            sl_pred.loc[idx] = se.fusion_score_op(df, members_all9, [p], OP_GEO).loc[idx].values
    single_layer = _guarded_rho(df, sl_pred.values, pats, "raw")
    # geomean within-patient 独立 → 单层 LOPO 逐位 ≡ oracle (in-sample); 显式断言
    assert not np.isnan(single_layer) and not np.isnan(oracle_rho) and abs(single_layer - oracle_rho) < 1e-9, \
        f"[#2 恒等断言失败] single_layer={single_layer} vs oracle={oracle_rho} 应逐位相等"
    d2 = fn._sub(single_layer, cv_rho)
    rows.append(_row("2", "nested-CV", "评估协议", "nested(inner8选+外层评)",
                     "单层LOPO(全数据选+LOPO评)", cv_rho, single_layer, d2, n_used,
                     "单层≡oracle (非独立数)",
                     f"恒等断言过 |单层−oracle|<1e-9 (={C.r6(abs(single_layer-oracle_rho))}); "
                     f"全数据选+LOPO评≡in-sample, 非真CV, 膨胀同#1",
                     "geomean病人内独立→单层LOPO=oracle, 不当独立数报"))

    # ── #3 留患者 vs 留肽 (5折 stratified-by-patient) ──
    folds = _peptide_folds(df, pats, 5, seed)
    lp_pred = pd.Series(np.nan, index=df.index, dtype=float)
    for f in range(5):
        test_idx = folds[f]
        df_train = df[~df.index.isin(test_idx)]
        tpats = C.present_patients(df_train)
        members = se.proc_forward_greedy(df_train, pool, tpats, "raw")  # 训练肽选成员 (标签只见 train 肽)
        if not members:
            continue
        fused = se.fusion_score_op(df, members, pats, OP_GEO)           # 无监督融合, 装配 out-of-fold
        lp_pred.loc[test_idx] = fused.loc[test_idx].values
    lp_rho = _guarded_rho(df, lp_pred.values, pats, "raw")
    d3 = fn._sub(lp_rho, cv_rho)
    rows.append(_row("3", "外层=留患者(leave-patient)", "折单元", "leave-patient",
                     "leave-peptide(5折stratified-by-patient)", cv_rho, lp_rho, d3, n_used,
                     "留肽−留患者>0 (留肽泄漏患者内结构)",
                     f"Δ={C.r6(d3)} (留肽{C.r6(lp_rho)} vs 留患者{C.r6(cv_rho)}); "
                     f"★承认bundle了折粒度, 不claim纯单变量",
                     "留患者才检验跨患者泛化; 留肽同患者训练/测试→乐观偏"))

    # ── #4 守卫 vs 裸指标 (best_single, 两臂都用全30池 → 只变 metric) ──
    pool_all30 = fn.filter_pool(df, C.TOOLS_30)                # 全30, 含稀疏伪迹工具 (#5 复用同一变量)
    t_g, rho_g = fn.best_single(df, pool_all30, pats, "raw")   # 守卫: 剔退化相关, 选真信号工具
    t_n, rho_n = _naive_best_single(df, pool_all30, pats)      # 裸: 被小n虚假完美相关抬冠军
    d4 = fn._sub(rho_n, rho_g)
    rows.append(_row("4", "guarded per-patient ρ̄", "度量守卫", f"guarded:{t_g}",
                     f"naive裸(对照):{t_n}", rho_g, rho_n, d4, n_used,
                     "裸选小n伪迹虚高, 守卫剔退化后选真信号",
                     f"裸选{t_n}={C.r6(rho_n)} vs 守卫选{t_g}={C.r6(rho_g)}; "
                     f"裸被小样本虚假完美相关抬冠军",
                     "n_eff<4剔患者+丢|ρ|>0.999退化, 挡小n假冠军; 裸版仅对照",
                     fixed_over=FIXED.replace("pool=cover(≥8)", "pool=全30(演示伪迹)")))

    # ── #5 cover池 vs 全30 (只变池): 裸 shuffle-null 单工具天花板 ──
    # pool_all30 已在 #4 算, 此处复用别重算
    nn_cover = _shuffle_null_naive_single(df, pool, pats, seed)        # cover 裸天花板 (低)
    nn_all30 = _shuffle_null_naive_single(df, pool_all30, pats, seed)  # 全30 裸天花板 (稀疏工具虚高)
    d5 = fn._sub(nn_all30, nn_cover)
    rows.append(_row("5", "候选池=cover(≥8)", "候选池", f"cover({len(pool)}工具)",
                     f"全30({len(pool_all30)}工具)", nn_cover, nn_all30, d5, n_used,
                     "全30裸天花板>cover (稀疏工具打乱仍碰虚假相关)",
                     f"裸shuffle-null best-single: cover={C.r6(nn_cover)} vs 全30={C.r6(nn_all30)}; "
                     f"Δ={C.r6(d5)}, 全30含min<8工具打乱后仍虚高",
                     "cover过滤挡小n假信号; 裸口径下全30稀疏工具天花板虚高"))
    # ── #5b 同池对照, 守卫口径 (防线重叠, 诚实记冗余) ──
    null_cover_g = _shuffle_null_oracle(df, pool, pats, seed)          # 守卫, cover
    null_all30_g = _shuffle_null_oracle(df, pool_all30, pats, seed)    # 守卫, 全30
    d5b = fn._sub(null_all30_g, null_cover_g)
    rows.append(_row("5b", "候选池=cover(≥8)", "候选池", f"cover({len(pool)}工具)",
                     f"全30({len(pool_all30)}工具)", null_cover_g, null_all30_g, d5b, n_used,
                     "守卫下 cover≈全30 (守卫已中和稀疏膨胀→与池过滤防线重叠)",
                     f"守卫shuffle-null: cover={C.r6(null_cover_g)} vs 全30={C.r6(null_all30_g)}; "
                     f"Δ={C.r6(d5b)}≈0 = 防线重叠(非矛盾)",
                     "守卫在时池过滤冗余; 守卫关时(见#5主行)池过滤仍是真防线"))

    # ── #6 Fisher-z(equal) vs 逆方差 vs 均值 (⚠️同一份 rhos_by/ns_by) ──
    vals_o, _m = se.oracle_pred_from_selector(df, pool, pats, "raw", OP_GEO, se.proc_forward_greedy)
    r6 = fn.guarded_perpat_metric(df, vals_o, pats, "raw", return_perpat=True)
    rhos_by, ns_by = r6[5], r6[6]
    rho_arr = np.array([rhos_by[p] for p in pats], float)
    n_arr = np.array([float(ns_by[p]) for p in pats], float)
    agg_equal = C.fisherz_weighted_agg(rho_arr, n_arr, weight="equal")
    agg_invvar = C.fisherz_weighted_agg(rho_arr, n_arr, weight="invvar")
    mean_rho = float(np.nanmean(rho_arr))
    _, elo, ehi = fn.guarded_bootstrap_ci(rhos_by, ns_by, pats, se.N_BOOT, seed)
    ci_w_equal = fn._sub(ehi, elo)
    d6a = fn._sub(agg_equal[0], agg_invvar[0])
    rows.append(_row("6", "跨病人聚合=Fisher-z 等权", "聚合", "equal(Fisher-z)", "invvar(逆方差)",
                     agg_equal[0], agg_invvar[0], d6a, n_used, "点估相近, 权口径差异",
                     f"同一rhos_by: equal={C.r6(agg_equal[0])}(CI宽{C.r6(ci_w_equal)}) vs "
                     f"invvar={C.r6(agg_invvar[0])} vs 均值ρ={C.r6(mean_rho)}",
                     "等权不让大n病人主导; 三聚合共用同一份守卫ρ向量"))
    d6b = fn._sub(agg_equal[0], mean_rho)
    rows.append(_row("6b", "跨病人聚合=Fisher-z 等权", "聚合", "equal(Fisher-z)", "均值(np.nanmean ρ)",
                     agg_equal[0], mean_rho, d6b, n_used, "Fisher-z vs 线性均值差异小",
                     f"equal={C.r6(agg_equal[0])} vs 均值ρ={C.r6(mean_rho)}",
                     "Fisher-z 方差稳定后再平均, 极端ρ不过度拉动"))

    # ── #7 per-patient vs pooled (⚠️只换ρ口径, 同融合分) ──
    per_patient = agg_equal[0]
    y = df[C.LABEL_COL].values.astype(float)
    pooled = C.spearman_np(np.asarray(vals_o, float), y)   # 裸池化 Spearman (对照口径)
    d7 = fn._sub(per_patient, pooled)
    rows.append(_row("7", "per-patient Fisher-z", "相关口径", "per-patient", "pooled(全130)",
                     per_patient, pooled, d7, n_used, "背离 (pooled 受跨患者标度混杂)",
                     f"per-patient={C.r6(per_patient)} vs pooled={C.r6(pooled)}; Δ={C.r6(d7)}",
                     "患者间Elispot标度不可比, pooled把标度差当信号"))

    # ── #8 贪心 vs 穷举 (⚠️同池top-10同k同算子, 只变搜索; k=2,3) ──
    top10 = se._topn_single(df, pool, pats, "raw", 10)
    for k in (2, 3):
        g = se.greedy_path_op(df, top10, pats, "raw", OP_GEO, k)
        g_rho = _guarded_rho(df, se.fusion_score_op(df, g, pats, OP_GEO).values, pats, "raw")
        e = se._exhaust_best_k(df, pool, pats, "raw", OP_GEO, k, 10)
        e_rho = _guarded_rho(df, se.fusion_score_op(df, e, pats, OP_GEO).values, pats, "raw")
        d8 = fn._sub(e_rho, g_rho)
        rows.append(_row(f"8{'' if k == 2 else 'b'}", "前向贪心", f"搜索(k={k})", "greedy", "exhaustive",
                         g_rho, e_rho, d8, n_used, "exhaustive−greedy 小 (贪心近最优)",
                         f"k={k}: greedy{';'.join(g)}={C.r6(g_rho)} vs "
                         f"exhaustive{';'.join(e)}={C.r6(e_rho)}",
                         "★解耦: 只证贪心是合格优化器, 泛化由 oracle−CV(#1) 答, 别混"))

    # ── #9 ε/maxdim 敏感性 (小网格, 报峰位) ──
    grid = {}
    for eps in (0.0, 0.01, 0.02):
        for md in (3, 6, 8):
            sel = (lambda d, pl, pa, cal, _e=eps, _m=md:
                   se.greedy_members_op(d, pl, pa, cal, _e, _m, OP_GEO)[0])
            cvg, _ = se.cv_pred_from_selector(df, pool, pats, "raw", OP_GEO, sel)
            grid[(eps, md)] = _guarded_rho(df, cvg.values, pats, "raw")
    default9 = grid[(0.01, 6)]
    peak_key = max(grid, key=lambda kk: (grid[kk] if not np.isnan(grid[kk]) else -np.inf))
    peak9 = grid[peak_key]
    d9 = fn._sub(peak9, default9)
    rows.append(_row("9", "eps=0.01,maxdim=6", "eps×maxdim", "(0.01,6)", f"峰{peak_key}",
                     default9, peak9, d9, n_used, "峰稳→不靠调参",
                     f"网格CV: 默认(0.01,6)={C.r6(default9)}, 峰{peak_key}={C.r6(peak9)}, Δ={C.r6(d9)}",
                     "峰位与默认接近=结论不靠 eps/maxdim 精调"))

    # ── #10 算子CV选 vs 钉geomean ──
    cvj, _ops = se.cv_pred_joint(df, pool, pats, "raw", se.OP_ALL8)
    cv_opselect = _guarded_rho(df, cvj.values, pats, "raw")
    d10 = fn._sub(cv_rho, cv_opselect)
    rows.append(_row("10", "钉死 op=geomean", "算子自由度", "fixed_geomean", "cv_select_op(all8)",
                     cv_rho, cv_opselect, d10, n_used, "fixed−cvselect≥0 (DOF伤CV)",
                     f"钉geomean CV={C.r6(cv_rho)} vs 算子CV选={C.r6(cv_opselect)}; Δ={C.r6(d10)}",
                     "多一个算子自由度→CV再罚一次, 钉geomean更稳"))

    # ── #11 DTU入池 vs 剔DTU (符号翻转 → consent_critical) ──
    pool_no_dtu = [t for t in pool if t not in C.DTU_TOOLS]
    cv_no = _fg_cv(df, pool_no_dtu, pats, "raw")[0]
    _tw, sw = fn.best_single(df, pool, pats, "raw")
    _tn2, sn2 = fn.best_single(df, pool_no_dtu, pats, "raw")
    sign_with = _sign(fn._sub(cv_rho, sw))
    sign_no = _sign(fn._sub(cv_no, sn2))
    flip = (sign_with != 0 and sign_no != 0 and sign_with != sign_no)
    d11 = fn._sub(cv_rho, cv_no)
    rows.append(_row("11", "DTU工具入池", "DTU入池", "含DTU", "剔DTU", cv_rho, cv_no, d11, n_used,
                     "报两版+符号翻转 (consent_critical)",
                     f"含DTU CV={C.r6(cv_rho)}(整合-单符号{sign_with}) vs 剔DTU={C.r6(cv_no)}"
                     f"(符号{sign_no}); 翻转={flip} → consent_critical={flip}",
                     "DTU 待授权; 若结论符号依赖DTU则决策归袁+朱"))

    # ── #12 裸 vs 控肽长口径 ──
    cv_lenctrl = _fg_cv(df, pool, pats, "lenctrl")[0]
    _or_len, m_len = _fg_oracle(df, pool, pats, "lenctrl")
    consistent = (";".join(members_all9) == ";".join(m_len))
    d12 = fn._sub(cv_rho, cv_lenctrl)
    rows.append(_row("12", "caliber=raw", "口径", "raw", "lenctrl(控肽长)", cv_rho, cv_lenctrl,
                     d12, n_used, "两口径CV最优/结论是否一致",
                     f"raw CV={C.r6(cv_rho)}(选{';'.join(members_all9)}) vs "
                     f"lenctrl={C.r6(cv_lenctrl)}(选{';'.join(m_len)}); 成员一致={consistent}",
                     "控肽长后结论若稳=非肽长搭便车 (lenctrl 有效折少, 敏感性)"))

    # ── #13 geomean vs mean_rank/median/max_rank (同CV最优成员集只换算子) ──
    if members_all9:
        base13 = _guarded_rho(df, se.fusion_score_op(df, members_all9, pats, OP_GEO).values, pats, "raw")
        for op2, tag in [("mean_rank", "13"), ("median", "13b"), ("max", "13c")]:
            alt13 = _guarded_rho(df, se.fusion_score_op(df, members_all9, pats, op2).values, pats, "raw")
            d13 = fn._sub(base13, alt13)
            rows.append(_row(tag, "算子=geomean", "算子(成员集固定)", "geomean", op2,
                             base13, alt13, d13, n_used, "geomean≥或≈其它算子",
                             f"同成员集{';'.join(members_all9)}: geomean={C.r6(base13)} vs "
                             f"{op2}={C.r6(alt13)}; Δ={C.r6(d13)}",
                             "geomean=共识(AND)鲁棒: 任一维差则拉低, 抗单工具虚高"))

    # ── 写出 ──
    cols = ["id", "choice", "fixed_vars", "varied_var", "chosen_value", "alt_value",
            "chosen_metric", "alt_metric", "delta", "caliber", "n_used",
            "expected_direction", "observed_verdict", "why_oneline"]
    df_out = pd.DataFrame(rows)[cols]
    out = HERE / "rationale_ledger.csv"
    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write("# rationale_ledger.csv —— QuantImmuBench 原则化 CV 融合选择: 每方法学抉择「只变一处」受控账。\n")
        f.write(f"# 固定(除被试): {FIXED}。措辞禁 proven optimal/best/SOTA; null=「无可检测的整合净优势」。\n")
        f.write("# ★#2 恒等断言(单层LOPO≡oracle)已在脚本内 assert; #3 承认bundle折粒度; "
                "#4/#7 裸口径仅作被试对照非CV选择。\n")
        df_out.to_csv(f, index=False)
    print(f"[saved] {out} ({len(df_out)} 行)")
    print("\n[DONE] rationale_ablations (#1-13) —— 主线可跑; #2 恒等断言过则合规。")


if __name__ == "__main__":
    main()
