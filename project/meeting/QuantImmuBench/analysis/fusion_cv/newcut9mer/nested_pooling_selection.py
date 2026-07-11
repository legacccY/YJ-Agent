# -*- coding: utf-8 -*-
"""
nested_pooling_selection.py — 新切 9mer 融合层「nested pooling selection」正式分析脚本
================================================================================
服务: QuantImmuBench §3.3 融合层报告 (paper/QuanImmu-Paper-Outline.md §3.3)。
lever: nested pooling selection 作为可写进方法的诚实融合流程 —— 面板预先固定, 只在每一折
       内给每个工具选它的合成方式 (pooling), 报无泄漏交叉验证 ρ。

数据源 (只读, 新切 canonical 重跑冻结表):
  data/frozen/pooled_clean_rerun_9mer.csv  —— 固定窗口 9AA-only, DS2 人源。
  实测 9 位患者 (101,102,104,105,106,107,108,109,110); min_pep=8 下 P102 (仅 6 肽) 不足
  以算患者内 ρ → 从聚合掉出, 有效患者 = 8; 但 LOPO 外层仍留出全部 9 位 → 9 折。

方法 (nested pooling selection, self 准则):
  · 外层 LOPO (留一患者); 内层其余患者上, 对面板里每个工具, 从它的 51 个 <tool>_* 合成方式
    变体里选「该工具自己患者内 Spearman 最高」的一个 (self 准则, 与融合无关, DOF 最小);
  · 用这些逐工具逐折选出的 pooling 列, 在留出患者上算分, 病人内名次 geomean 融合 → 填 CV 预测;
  · 装满全部留出患者 → per_patient_spearman(CV 预测) = 诚实交叉验证 ρ。
  · oracle = 在全部患者上一次性选 pooling + 融合的样本内上界 (乐观, 非留出); inflation = oracle − CV。

复用引擎 (analysis/official/_official_common.py, 口径逐位一致, 不改算法):
  load_frozen / present_patients / per_patient_spearman / apply_fusion / pool_col /
  paired_patient_test / spearman_np / UNSUPERVISED_FUSIONS。

本脚本整合以下一次性 _scratch (逻辑照抄, 见 analysis/official/newcut9mer/):
  _scratch_nested_pooling_only.py     (固定面板 + 只选 pooling 的 CV)
  _scratch_nested_pool_paired.py      (配对 p + cluster-bootstrap CI + 逐病人)
  _scratch_defensible_panels.py       (面板敏感性)
  _scratch_operator_headroom.py       (8 算子 CV + 算子嵌套选)
  _scratch_nested_pooling_cv.py       (A/B/C/D 四臂选择梯队)
  _scratch_panel_ceiling_geomean.py   (面板 CV-argmax 天花板)
  _scratch_show_fold_pooling.py       (逐折 pooling 选择表)

输出 (写脚本所在目录 analysis/fusion_cv/newcut9mer/):
  stdout                              —— 全部关键数字 (主线核对)。
  nested_pooling_selection.csv        —— 主结果表, 每行一个配置。
  nested_pooling_selection_folds.csv  —— 本面板逐折 pooling 选择 (9 折)。

Windows 规范: UTF-8 stdout, pathlib 路径, 纯 numpy/pandas, 禁 scipy.stats (纯 numpy Spearman), 零 GPU。
跑法 (主线跑, 我不跑): python analysis/fusion_cv/newcut9mer/nested_pooling_selection.py
"""
import sys
import csv
import itertools
from collections import Counter
from pathlib import Path

import numpy as np

# ── 定位 ROOT 并挂 _official_common (与 _scratch 一致的向上找 QuantImmuBench) ────────
ROOT = Path(__file__).resolve()
while ROOT.name != "QuantImmuBench":
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "analysis" / "official"))

from _official_common import (  # noqa: E402
    load_frozen, present_patients, per_patient_spearman,
    apply_fusion, pool_col, paired_patient_test, spearman_np,
    UNSUPERVISED_FUSIONS,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent                  # analysis/fusion_cv/newcut9mer/
FROZEN = ROOT / "data" / "frozen" / "pooled_clean_rerun_9mer.csv"
OUT_MAIN = HERE / "nested_pooling_selection.csv"
OUT_FOLDS = HERE / "nested_pooling_selection_folds.csv"

MP = 8                                                   # 患者内最少肽数 (task 派单)
LABEL = "Elispot"

df = load_frozen(FROZEN)
PATS = present_patients(df)                              # 实测 9 患者 (LOPO 折数 = 9)
PID = df["Patient_ID"].values

# 头衔面板 (预先固定, 呈递金标准 + 识别最强 PredIG + 原面板识别工具 deepHLApan)
MAIN_PANEL = ["netMHCpan_BA", "PredIG", "deepHLApan"]
SINGLE_COL = pool_col("netMHCpan_BA", "max")             # 零选择基线单工具

# 全 20 免疫原 (零成员挑选面板) 与 8 呈递工具 (梯队选择器候选池用)
IMMUNO = ["deepHLApan", "IEDB_Calis", "ImmuneApp", "PRIME", "DeepImmuno", "PredIG",
          "IMPROVE", "pTuneos", "NeoTImmuML", "BigMHC_IM", "CNNeo", "Repitope",
          "TSCAPE", "NetTepi", "ICERFIRE", "MUNIS", "andy90", "ImmuGenX", "Seq2Neo", "NeoaG"]
BINDING = ["netMHCpan_BA", "netMHCpan_EL", "netMHCstabpan", "MHCflurry",
           "MHCnuggets", "MHCseqNet", "TransHLA", "HLAthena"]
ALL_TOOLS = IMMUNO + BINDING                             # 28 工具 (梯队/天花板穷举池)

EPS = 0.01                                               # 前向贪心接受阈 (梯队选择器)
MAXDIM = 6                                               # 贪心最大成员数


# ═══════════════════════════════════════════════════════════════════════════════
# 基础工具 (照抄 _scratch: variants / rho / safe / fuse)
# ═══════════════════════════════════════════════════════════════════════════════

def variants(tool):
    """该工具全部可用 pooling 变体列 (非全 NaN 且非常量, 才进选择池)。"""
    pref = tool + "_"
    return [c for c in df.columns
            if c.startswith(pref) and df[c].notna().sum() > 0
            and df[c].nunique(dropna=True) >= 2]


# 预算各工具 variants (贯穿全脚本复用, 与逐处重算等价)
VARS = {t: variants(t) for t in set(ALL_TOOLS) | set(MAIN_PANEL)}


def rho(score, pats):
    """geomean/单列 score 在 pats 上的 per-patient 等权 Fisher-z ρ (raw 口径)。"""
    return per_patient_spearman(df, score, patients=pats, min_pep=MP)[0]


def safe(r):
    """NaN/None 折成 -9.0 (供 argmax 比较, 与 _scratch 一致)。"""
    return -9.0 if (r is None or np.isnan(r)) else r


def fuse(cols, pats):
    """cols 列 geomean 融合在 pats 上的 ρ; 单列直接算。"""
    if len(cols) == 1:
        return rho(cols[0], pats)
    return rho(apply_fusion(df, cols, method="geomean", patients=pats), pats)


# ═══════════════════════════════════════════════════════════════════════════════
# nested pooling selection 核心 (self 准则)
# ═══════════════════════════════════════════════════════════════════════════════

def select_pool_per_tool(tools, train):
    """在 train 患者上, 为每个工具选它自己内层 ρ 最高的 pooling 列 (self 准则)。
    返回 {tool: chosen_col}, 保持 tools 顺序。"""
    chosen = {}
    for t in tools:
        vs = VARS.get(t) or variants(t)
        if not vs:
            continue
        chosen[t] = max(vs, key=lambda c: safe(rho(c, train)))
    return chosen


def nested_pool_cv(tools, return_folds=False):
    """外层 LOPO nested pooling selection: 每折内层选 pooling, geomean 融合填留出患者。
    返回诚实 CV ρ; return_folds=True 追加 [{tool: chosen_col}, ...] (逐折)。"""
    pred = np.full(len(df), np.nan)
    fold_choices = []
    for p in PATS:
        train = [q for q in PATS if q != p]
        ch = select_pool_per_tool(tools, train)
        cols = list(ch.values())
        fold_choices.append(ch)
        mask = PID == p
        if len(cols) == 1:
            fill = df[cols[0]].values
        else:
            fill = apply_fusion(df, cols, method="geomean", patients=[p]).values
        pred[mask] = fill[mask]
    cv = rho(pred, PATS)
    if return_folds:
        return cv, pred, fold_choices
    return cv, pred, None


def oracle_pool(tools):
    """样本内上界: 在全部患者上一次选 pooling + 融合 (乐观, 非留出)。"""
    ch = select_pool_per_tool(tools, list(PATS))
    return fuse(list(ch.values()), PATS)


# ═══════════════════════════════════════════════════════════════════════════════
# 选择梯队三臂前向贪心选择器 (照抄 _scratch_nested_pooling_cv.py)
#   臂对照:  只选 pooling (面板固定) / 完全数据驱动 (成员+pooling) / 只选成员 (pooling=max)
# ═══════════════════════════════════════════════════════════════════════════════

TOOL_COLS = {t: v for t, v in ((t, variants(t)) for t in ALL_TOOLS) if v}
USABLE = [t for t in ALL_TOOLS if t in TOOL_COLS and pool_col(t, "max") in TOOL_COLS[t]]


def rho_on(cols, pats):
    """geomean 融合 cols 在 pats 上 ρ (梯队选择器内部用, 与 fuse 等价)。"""
    if len(cols) == 1:
        return per_patient_spearman(df, cols[0], patients=pats, min_pep=MP)[0]
    return per_patient_spearman(df, apply_fusion(df, cols, method="geomean", patients=pats),
                                patients=pats, min_pep=MP)[0]


def greedy_select(train_pats, pool_mode):
    """前向贪心选成员; pool_mode='max' 固定 max / 'best' 每工具试全部变体。返回 [(tool,col),...]。"""
    chosen = []
    cur = -9.0
    while len(chosen) < MAXDIM:
        best = None
        for t in USABLE:
            if any(t == ct for ct, _ in chosen):
                continue
            cand_cols = [pool_col(t, "max")] if pool_mode == "max" else TOOL_COLS[t]
            for col in cand_cols:
                trial = [c for _, c in chosen] + [col]
                r = safe(rho_on(trial, train_pats))
                if best is None or r > best[0]:
                    best = (r, t, col)
        if best is None or best[0] <= cur + EPS:
            break
        cur = best[0]
        chosen.append((best[1], best[2]))
    return chosen


def nested_cv_greedy(pool_mode):
    """外层 LOPO + 每折内层贪心选成员 (± pooling), 装 CV 预测。返回 (cv, [members_per_fold])。"""
    pred = np.full(len(df), np.nan)
    members_per_fold = []
    for p in PATS:
        train = [q for q in PATS if q != p]
        sel = greedy_select(train, pool_mode)
        cols = [c for _, c in sel]
        members_per_fold.append([t for t, _ in sel])
        mask = PID == p
        if len(cols) == 1:
            fill = df[cols[0]].values
        elif len(cols) == 0:
            fill = np.full(len(df), np.nan)
        else:
            fill = apply_fusion(df, cols, method="geomean", patients=[p]).values
        pred[mask] = fill[mask]
    return rho(pred, PATS), members_per_fold


def oracle_greedy(pool_mode):
    """样本内贪心选择上界。"""
    sel = greedy_select(list(PATS), pool_mode)
    return rho_on([c for _, c in sel], PATS)


# ═══════════════════════════════════════════════════════════════════════════════
# 面板 CV-argmax 天花板 (照抄 _scratch_panel_ceiling_geomean.py)
#   加速: self 准则下每工具逐折选的 pooling 与面板无关 → 预装每工具「nested-pooling CV 预测列」,
#         任意面板 = geomean 融合这些预装列; 穷举 C(28,k) 秒级。
#   ★ 直接取「CV 最高的面板」= 用 CV 当选择目标, 本身又是一层挑选 (乐观), 只报天花板景观。
# ═══════════════════════════════════════════════════════════════════════════════

def assemble_np_columns():
    """为每个 usable 工具预装其单工具 nested-pooling CV 预测列 (逐折 self 选 pooling 填留出患者)。"""
    assembled = {}
    for t in ALL_TOOLS:
        vs = VARS.get(t) or variants(t)
        if not vs:
            continue
        col = np.full(len(df), np.nan)
        for p in PATS:
            train = [q for q in PATS if q != p]
            best = max(vs, key=lambda c: safe(rho(c, train)))
            m = PID == p
            col[m] = df[best].values[m]
        assembled[t] = col
    return assembled


def panel_cv_from_assembled(work, tools):
    """预装列上 geomean 融合 tools → per-patient ρ (work = 只含 Patient_ID/Elispot + 预装列)。"""
    cols = [t + "__npcv" for t in tools]
    if len(cols) == 1:
        return per_patient_spearman(work, cols[0], patients=PATS, min_pep=MP)[0]
    return per_patient_spearman(work, apply_fusion(work, cols, method="geomean", patients=PATS),
                                patients=PATS, min_pep=MP)[0]


def panel_ceiling(assembled, ks=(3, 4)):
    """穷举各 k 的面板, 报 nested-pooling geomean 诚实 CV 最高的面板 (天花板景观)。"""
    import pandas as pd
    work = df[["Patient_ID", LABEL]].copy()
    for t, col in assembled.items():
        work[t + "__npcv"] = col
    usable = list(assembled.keys())
    out = {}
    for k in ks:
        best = None
        for combo in itertools.combinations(usable, k):
            r = safe(panel_cv_from_assembled(work, list(combo)))
            if r > -8 and (best is None or r > best[0]):
                best = (r, combo)
        out[k] = best
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# cluster-bootstrap CI (照抄 _scratch_nested_pool_paired.py: RandomState(42), 2000, 患者重采样)
# ═══════════════════════════════════════════════════════════════════════════════

def per_pat_rhos(score):
    """逐患者 Spearman(score, Elispot), n>=MP 才留; 返回 {patient: rho}。"""
    s = np.asarray(score, float) if not isinstance(score, str) else df[score].values.astype(float)
    y = df[LABEL].values.astype(float)
    out = {}
    for p in PATS:
        m = PID == p
        xx, yy = s[m], y[m]
        mm = ~(np.isnan(xx) | np.isnan(yy))
        if mm.sum() >= MP:
            r = spearman_np(xx[mm], yy[mm])
            if not np.isnan(r):
                out[p] = r
    return out


def cluster_bootstrap_ci(fus_score, single_score, n_boot=2000, seed=42):
    """融合 CV 预测的患者 cluster-bootstrap 95%CI (等权 Fisher-z 均值)。
    common = 融合与单工具都有有效 ρ 的患者。返回 (lo, hi, point, r_fus, r_sg, common)。"""
    r_fus = per_pat_rhos(fus_score)
    r_sg = per_pat_rhos(single_score)
    common = sorted(set(r_fus) & set(r_sg))
    arr = np.array([r_fus[p] for p in common], float)
    rng = np.random.RandomState(seed)
    boots = []
    for _ in range(n_boot):
        samp = rng.choice(arr, size=len(arr), replace=True)
        z = np.arctanh(np.clip(samp, -0.9999, 0.9999))
        boots.append(np.tanh(np.mean(z)))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    point = float(np.tanh(np.mean(np.arctanh(np.clip(arr, -0.9999, 0.9999)))))
    return float(lo), float(hi), point, r_fus, r_sg, common


# ═══════════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════════

def _f(v):
    if v is None or v == "" or (isinstance(v, float) and np.isnan(v)):
        return ""
    try:
        return round(float(v), 4)
    except (ValueError, TypeError):
        return v


def main():
    print(f"[nested_pooling_selection] 源 = {FROZEN.name}")
    print(f"  患者 (LOPO 折) = {PATS}  (共 {len(PATS)} 折; min_pep={MP})")
    print(f"  头衔面板 = {MAIN_PANEL}   单工具基线 = {SINGLE_COL}")

    rows = []   # 主结果表行 (dict)

    # ── (1) 头衔面板: nested-pooling CV / oracle / inflation / 配对 p / bootstrap CI ────────
    print("\n" + "=" * 72)
    print("(1) 头衔面板 nested pooling selection")
    cv_main, cv_pred, fold_choices = nested_pool_cv(MAIN_PANEL, return_folds=True)
    orc_main = oracle_pool(MAIN_PANEL)
    infl_main = safe(orc_main) - safe(cv_main)
    sg_rho = rho(SINGLE_COL, PATS)
    dz, pval, K = paired_patient_test(df, cv_pred, SINGLE_COL, patients=PATS, min_pep=MP)
    lo, hi, point, r_fus, r_sg, common = cluster_bootstrap_ci(cv_pred, SINGLE_COL)
    print(f"  nested-pooling CV ρ = {safe(cv_main):+.4f}")
    print(f"  oracle (样本内)  ρ = {safe(orc_main):+.4f}   inflation = {infl_main:+.4f}")
    print(f"  单工具 netMHCpan_BA_max ρ = {safe(sg_rho):+.4f}")
    print(f"  配对 (Fisher-z Δ, 病人配对置换): Δz={dz:+.4f}  p={pval:.4f}  K={K} 病人")
    print(f"  cluster-bootstrap(2000,seed42) 95%CI = [{lo:+.3f}, {hi:+.3f}]  (点估={point:+.3f})")
    rows.append(dict(config="headline_dualaxis3_PredIG",
                     panel="netMHCpan_BA+PredIG+deepHLApan",
                     cv_rho=cv_main, oracle_rho=orc_main, inflation=infl_main,
                     delta_vs_single=dz, paired_p=pval, ci_lo=lo, ci_hi=hi,
                     note="headline; Δz=Fisher-z配对差 vs netMHCpan_BA_max; CI=患者cluster-bootstrap"))

    # ── (2) 逐病人融合 ρ + 留一去患者 ────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("(2) 逐病人融合 ρ (共同患者)")
    print(f"  共同患者 {len(common)}: 融合均值={np.mean([r_fus[p] for p in common]):+.3f} | "
          f"单工具={np.mean([r_sg[p] for p in common]):+.3f}")
    for p in common:
        print(f"   P{p}: 融合={r_fus[p]:+.3f}  单工具={r_sg[p]:+.3f}  Δ={r_fus[p]-r_sg[p]:+.3f}")
    # 留一去患者对融合 CV ρ 的影响 (fisher-z 等权均值)
    print("  留一去患者 (融合 CV ρ 的患者 jackknife):")
    arr_common = {p: r_fus[p] for p in common}
    for p in common:
        rest = [arr_common[q] for q in common if q != p]
        z = np.arctanh(np.clip(np.array(rest, float), -0.9999, 0.9999))
        loo = float(np.tanh(np.mean(z)))
        print(f"   去 P{p} → {loo:+.4f}")

    # ── (3) 面板敏感性 (6 个先验面板 nested-pooling CV + 配对 p) ──────────────────────
    print("\n" + "=" * 72)
    print("(3) 面板敏感性 (nested-pooling CV / Δvs单工具 / 配对p)")
    SENS_PANELS = [
        ("single_netMHCpan_BA", ["netMHCpan_BA"]),
        ("dual2_BA_PredIG", ["netMHCpan_BA", "PredIG"]),
        ("dual3_BA_PredIG_deepHLApan", ["netMHCpan_BA", "PredIG", "deepHLApan"]),
        ("dual3_BA_PredIG_ICERFIRE", ["netMHCpan_BA", "PredIG", "ICERFIRE"]),
        ("old_BA_PRIME_deepHLApan", ["netMHCpan_BA", "PRIME", "deepHLApan"]),
        ("all_immuno20", IMMUNO),
    ]
    print(f"  {'面板':<32}{'CV ρ':>9}{'Δvs单工具':>11}{'配对p':>9}")
    for cfg, tools in SENS_PANELS:
        cv_s, pred_s, _ = nested_pool_cv(tools)
        dz_s, p_s, _ = paired_patient_test(df, pred_s, SINGLE_COL, patients=PATS, min_pep=MP)
        d_raw = safe(cv_s) - safe(sg_rho)
        print(f"  {cfg:<32}{safe(cv_s):>+9.4f}{d_raw:>+11.4f}{p_s:>9.3f}")
        if cfg != "dual3_BA_PredIG_deepHLApan":     # headline 已在 (1) 落表, 敏感性不重复该行
            rows.append(dict(config="sens_" + cfg, panel="+".join(tools) if len(tools) <= 4 else "all_immuno20",
                             cv_rho=cv_s, oracle_rho="", inflation="",
                             delta_vs_single=dz_s, paired_p=p_s, ci_lo="", ci_hi="",
                             note="面板敏感性; Δvs单工具(raw)=%.4f" % d_raw))

    # ── (4) 8 无监督算子 nested-pooling CV + 算子嵌套选 ──────────────────────────────
    print("\n" + "=" * 72)
    print("(4) 8 聚合算子 (固定面板, 逐工具 self 选 pooling)")
    OPS = list(UNSUPERVISED_FUSIONS)
    # self 准则每工具选 pooling 与算子无关 → 逐折先选好 pooling, 再套不同算子
    fold_pool_cols = []
    for p in PATS:
        train = [q for q in PATS if q != p]
        ch = select_pool_per_tool(MAIN_PANEL, train)
        fold_pool_cols.append((p, list(ch.values())))

    def cv_for_op(op):
        pred = np.full(len(df), np.nan)
        for p, cols in fold_pool_cols:
            m = PID == p
            pred[m] = apply_fusion(df, cols, method=op, patients=[p]).values[m]
        return rho(pred, PATS)

    op_rows = []
    for op in OPS:
        c = safe(cv_for_op(op))
        op_rows.append((op, c))
    op_rows.sort(key=lambda x: -x[1])
    for op, c in op_rows:
        print(f"   {op:20s}  nested-pooling CV = {c:+.4f}")
        rows.append(dict(config="operator_" + op, panel="+".join(MAIN_PANEL),
                         cv_rho=c, oracle_rho="", inflation="", delta_vs_single="",
                         paired_p="", ci_lo="", ci_hi="", note="固定面板8聚合算子对比(figE)"))
    # 算子也嵌套选 (内层挑内层 ρ 最高的算子)
    pred_opsel = np.full(len(df), np.nan)
    op_picks = []
    for p in PATS:
        train = [q for q in PATS if q != p]
        cols = dict(fold_pool_cols)[p]
        best_op = max(OPS, key=lambda op: safe(rho(
            apply_fusion(df, cols, method=op, patients=train), train)))
        op_picks.append(best_op)
        m = PID == p
        pred_opsel[m] = apply_fusion(df, cols, method=best_op, patients=[p]).values[m]
    cv_opsel = rho(pred_opsel, PATS)
    print(f"   {'每折选算子':20s}  nested-pooling CV = {safe(cv_opsel):+.4f}   "
          f"各折选中算子: {dict(Counter(op_picks))}")
    rows.append(dict(config="operator_per_fold_select", panel="+".join(MAIN_PANEL),
                     cv_rho=cv_opsel, oracle_rho="", inflation="", delta_vs_single="",
                     paired_p="", ci_lo="", ci_hi="", note="算子也嵌套选(多搜一维)"))

    # ── (5) 选择梯队三臂 ────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("(5) 选择梯队 (选择越多, 诚实 CV 越低)")
    # 臂 1: 只选 pooling (面板固定) = 头衔面板
    print(f"  只选pooling(面板固定)       oracle={safe(orc_main):+.4f}  CV={safe(cv_main):+.4f}")
    rows.append(dict(config="ladder_pooling_only", panel="+".join(MAIN_PANEL),
                     cv_rho=cv_main, oracle_rho=orc_main, inflation=infl_main,
                     delta_vs_single="", paired_p="", ci_lo="", ci_hi="",
                     note="梯队臂: 只选pooling(面板固定)"))
    # 臂 2: 完全数据驱动 (成员 + pooling)
    cv_b, _ = nested_cv_greedy("best")
    orc_b = oracle_greedy("best")
    print(f"  完全数据驱动(成员+pooling)  oracle={safe(orc_b):+.4f}  CV={safe(cv_b):+.4f}")
    rows.append(dict(config="ladder_fully_data_driven", panel="greedy(28工具池)",
                     cv_rho=cv_b, oracle_rho=orc_b, inflation=safe(orc_b) - safe(cv_b),
                     delta_vs_single="", paired_p="", ci_lo="", ci_hi="",
                     note="梯队臂: 完全数据驱动(成员+pooling), 前向贪心 EPS=0.01"))
    # 臂 3: 只选成员 (pooling=max)
    cv_a, _ = nested_cv_greedy("max")
    orc_a = oracle_greedy("max")
    print(f"  只选成员(pooling=max)       oracle={safe(orc_a):+.4f}  CV={safe(cv_a):+.4f}")
    rows.append(dict(config="ladder_member_only", panel="greedy(28工具池)",
                     cv_rho=cv_a, oracle_rho=orc_a, inflation=safe(orc_a) - safe(cv_a),
                     delta_vs_single="", paired_p="", ci_lo="", ci_hi="",
                     note="梯队臂: 只选成员(pooling=max)"))
    # 样本内挑的最大值 (不进 CV): 头衔面板 fixed max geomean
    fixed_max = fuse([pool_col(t, "max") for t in ["netMHCpan_BA", "PRIME", "deepHLApan"]], PATS)
    print(f"  [样本内] 固定面板 max geomean (netMHCpan_BA+PRIME+deepHLApan) = {safe(fixed_max):+.4f} "
          f"(不进CV, 不可复现)")

    # ── (6) 面板 CV-argmax 天花板 ───────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("(6) 面板 CV-argmax 天花板 (用 CV 当选择目标 = 一层挑选, 乐观)")
    assembled = assemble_np_columns()
    ceil = panel_ceiling(assembled, ks=(3, 4))
    for k, best in ceil.items():
        if best is None:
            continue
        r, combo = best
        print(f"  k={k} 最高 CV = {r:+.4f}   面板 = {'+'.join(combo)}")
        rows.append(dict(config=f"cv_argmax_k{k}", panel="+".join(combo),
                         cv_rho=r, oracle_rho="", inflation="", delta_vs_single="",
                         paired_p="", ci_lo="", ci_hi="",
                         note=f"面板CV-argmax天花板k={k}(不进CV,不可复现)"))

    # ── 写主结果表 ─────────────────────────────────────────────────────────────────
    cols = ["config", "panel", "cv_rho", "oracle_rho", "inflation",
            "delta_vs_single", "paired_p", "ci_lo", "ci_hi", "note"]
    with open(OUT_MAIN, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: (_f(r[k]) if k in ("cv_rho", "oracle_rho", "inflation",
                                              "delta_vs_single", "paired_p", "ci_lo", "ci_hi")
                            else r[k]) for k in cols})
    print(f"\n[saved] {OUT_MAIN}  ({len(rows)} 行)")

    # ── 写逐折 pooling 表 (头衔面板, 9 折) ───────────────────────────────────────────
    def _short(col, tool):
        return col.split(tool + "_", 1)[-1] if col else ""

    with open(OUT_FOLDS, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["held_out_patient", "netMHCpan_BA_pooling", "PredIG_pooling", "deepHLApan_pooling"])
        print("\n(逐折 pooling 选择, 头衔面板 9 折)")
        print(f"  {'留出病人':<8}{'netMHCpan_BA':<20}{'PredIG':<18}{'deepHLApan':<18}")
        picks_by_tool = {t: [] for t in MAIN_PANEL}
        for p, ch in zip(PATS, fold_choices):
            shorts = {t: _short(ch.get(t, ""), t) for t in MAIN_PANEL}
            for t in MAIN_PANEL:
                picks_by_tool[t].append(shorts[t])
            w.writerow([p, shorts["netMHCpan_BA"], shorts["PredIG"], shorts["deepHLApan"]])
            print(f"  {p:<8}{shorts['netMHCpan_BA']:<20}{shorts['PredIG']:<18}{shorts['deepHLApan']:<18}")
    print(f"[saved] {OUT_FOLDS}")
    for t in MAIN_PANEL:
        print(f"  {t:16s} 跨折 pooling 分布: {dict(Counter(picks_by_tool[t]))}")

    print("\n[DONE] nested_pooling_selection")


if __name__ == "__main__":
    main()
