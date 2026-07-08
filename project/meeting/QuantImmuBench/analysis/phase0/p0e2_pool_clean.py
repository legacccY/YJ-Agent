#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
p0e2_pool_clean.py
服务: QuantImmuBench 论文 / Part A 数据处理重建 (计划 quirky-stirring-parrot.md)
lever: 产一张「干净的肽级 pooling 冻结表」, 堵住 3 个污染源 ==
  (1) WT 污染  -> A1 含突变窗过滤 (pVACseq 标准: 只留 MT_Subpeptide != WT_Subpeptide)
  (2) sum count 混杂 -> 弃 sum/mean/geomean/top3mean, 只保 outline §2.4 表3 的 4 算子
  (3) pooling 偏离 outline -> 公式 + 超参网格严格按 outline §2.4 (别照抄旧 p0e 固定值)

与旧 analysis/phase0/p0e_pool_to_peptide.py 的关系:
  骨架沿用 (读长表 / 锚定 130 肽 / 校验门 / UTF-8+pathlib+纯 numpy),
  但 pooling 算子族、超参、过滤口径全部按 outline 重写, 产【新表作对照】, 旧脚本不动。

================== 输入 (只读) ==================
  scripts/out/merged_all_tools_30_official.csv   子肽×HLA 长表
    列: MT_Subpeptide / WT_Subpeptide / MT_FullPeptide / HLA_Allele /
        Patient_ID / Peptide_ID / mut_key + 30 个 MT_<Tool> 分数列
        (另有 __AUX_* 辅助列, 前缀非 'MT_' -> 天然不入工具列)
  data/frozen/ds2_official_groundtruth.csv        130 肽锚定 + Elispot (p0a 产)

================== 处理 (每步注释标 outline §) ==================
  A1 含突变窗过滤: 只留 MT_Subpeptide != WT_Subpeptide 的行 (剔纯 WT 窗)
  A2 9mer 过滤   : 默认 9mer (outline §2.2 主分析口径); --allwindow -> 8-14mer 全窗补充
  B2 肽长列 peplen = len(MT_FullPeptide) (每 mut_key 恒定)
  §2.4 pooling  : max / topk_w(k,α) / softmax(T) / rankdecay(γ), 公式+网格严格按表3

================== 为何不做归一化 (数学证明, outline §2.3) ==================
  逐病人 min-shift + RMS (y=x-min, y/√mean(y²)) 是【病人内仿射变换】x' = a·x + b (a>0)。
  · per-patient Spearman(x', ELISpot) = Spearman(x, ELISpot): 秩相关对单调正仿射不变。
  · rank-fusion 先在病人内把各维转 rank, 仿射同样保 rank 不变。
  故归一化【不改】本表下游用到的 per-patient Spearman + rank-fusion 结论,
  仅影响 pooled-AUPRC (绝对阈值敏感), 那是 B3 另处理。=> 本表存【原始 pooled 分】。

================== 为何不做 count_conf (弃旧 per-tool 阈值门) ==================
  旧 p0e 的 count_conf_<tool>_<op> = |spearman(pooled, n_subpep_tool)|>0.5 的 per-tool 阈值门,
  其 denominator (逐工具有效计数) 与实际 pooling 用的子肽集不一致 -> 判定口径错, 废弃。
  count 混杂控制改由下游 B2「控肽长偏相关」统一做 (partial corr, 不在本表打 bool 门)。

================== 输出 (data/frozen/) ==================
  pooled_clean_9mer.csv        (默认, 9mer 主分析)
  pooled_clean_allwindow.csv   (--allwindow, 8-14mer 补充)
    均 130 行, 列:
      mut_key, Patient_ID, Peptide_ID, Elispot, peplen, n_subpep
      + <Tool>_max
      + <Tool>_topk_k{k}_a{α}     (k∈{1,2,3,5,8,10,20,50,100} × α∈{0,0.5,1,2})
      + <Tool>_softmax_T{T}       (T∈{0.03,0.05,0.1,0.2,0.5,1,2})
      + <Tool>_rankdecay_g{γ}     (γ∈{1,1.5,2,3,5,10,20})
    每工具 = 1 + 36 + 7 + 7 = 51 pooling 变体 × 30 工具 = 1530 pooled 列
    (α/T/γ 的小数点用 'p' 编码, 如 a0p5 / T0p03 / g1p5)
    n_subpep = 该肽【含突变、当前口径 (9mer 或全窗)】的子肽×HLA 行数
    注: topk k=20,α=0 即 outline 的 netAffneg 等权 top-20 口径。

================== 校验门 (fail-loud) ==================
  [G1] 行数 == --expect-peptides (默认 130; 锚定 = GT 顺序里长表实际有的肽; rerun 纯新窗传 102=仅 SNV)
  [G2] 每肽 ≥1 工具有值 (整肽行不能全 NaN)
  [G3] 含突变过滤后每肽仍 ≥1 含突变子肽 (9mer 口径下即 ≥1 含突变 9mer, 无空肽)

================== 跑法 (我不跑, 主线串行跑) ==================
  python analysis/phase0/p0e2_pool_clean.py              # 默认 9mer 主分析
  python analysis/phase0/p0e2_pool_clean.py --allwindow  # 8-14mer 全窗补充
  python analysis/phase0/p0e2_pool_clean.py --w811       # 8-11mer 多长度补充 (对齐 zichenli 窗)
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
FROZEN_DIR = ROOT / "data" / "frozen"
GT_CSV = FROZEN_DIR / "ds2_official_groundtruth.csv"
DEFAULT_INPUT = ROOT / "scripts" / "out" / "merged_all_tools_30_official.csv"
OUT_CSV_9MER = FROZEN_DIR / "pooled_clean_9mer.csv"
OUT_CSV_ALLWINDOW = FROZEN_DIR / "pooled_clean_allwindow.csv"
OUT_CSV_W811 = FROZEN_DIR / "pooled_clean_8to11mer.csv"

SUBPEP_MT = "MT_Subpeptide"   # 子肽序列 (MT); 9mer 过滤 = str 长度==9
SUBPEP_WT = "WT_Subpeptide"   # 对应 WT 子肽序列; 含突变窗判定 MT!=WT
FULLPEP_MT = "MT_FullPeptide"  # 全肽 (MT); peplen = 其字符串长度

# 工具列 = 前缀 'MT_' 且非以下两个序列列 (__AUX_* 前缀天然不入)
EXCLUDE = {"MT_FullPeptide", "MT_Subpeptide"}

# ── outline §2.4 表3 超参网格 (严格照大纲, 别用旧 p0e 固定值) ──────────────────
TOPK_K = [1, 2, 3, 5, 8, 10, 20, 50, 100]     # topk_w: 取前 k
TOPK_ALPHA = [0, 0.5, 1, 2]                     # topk_w: wᵣ = r^(-α)
SOFTMAX_T = [0.03, 0.05, 0.1, 0.2, 0.5, 1, 2]   # softmax: 温度 T
RANKDECAY_GAMMA = [1, 1.5, 2, 3, 5, 10, 20]     # rankdecay: wᵣ = 1/log(r+γ)


def _fmt_num(x):
    """超参 -> 列名片段: 整数去小数, 小数把 '.' 换 'p' (0.5->0p5, 0.03->0p03)。"""
    if float(x).is_integer():
        return str(int(x))
    return str(x).replace(".", "p")


# ── 纯 numpy Spearman (禁 scipy 防 OMP#15; 复用旧 p0e 实现) ────────────────────
def spearman_np(x, y):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    m = ~(np.isnan(x) | np.isnan(y))
    x, y = x[m], y[m]
    n = len(x)
    if n < 3 or len(np.unique(x)) < 2 or len(np.unique(y)) < 2:
        return np.nan
    rx = pd.Series(x).rank().values
    ry = pd.Series(y).rank().values
    rx -= rx.mean()
    ry -= ry.mean()
    denom = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
    if denom == 0:
        return np.nan
    return float((rx * ry).sum() / denom)


# ── 4 种 pooling 算子 (outline §2.4 表3; 输入 s = 已降序排序、去 NaN 的向量) ─────
# 约定: s 由 _sorted_desc 预排序 (v₁ ≥ v₂ ≥ ...), r=1..len(s) 为降序秩, None/空 -> NaN。
def _pool_max(s):
    """max: s = v₁ (排序降序取第一)。"""
    if s is None or len(s) == 0:
        return np.nan
    return float(s[0])


def _pool_topk_w(s, k, alpha):
    """topk_w: s = Σ(wᵣ·vᵣ)/Σwᵣ, wᵣ = r^(-α), 取前 k。α=0 即等权 (r^0=1)。"""
    if s is None or len(s) == 0:
        return np.nan
    top = s[:k]                                  # 前 k (不足则全取)
    r = np.arange(1, len(top) + 1, dtype=float)  # 降序秩 r=1..min(k,n)
    w = r ** (-float(alpha))
    ws = w.sum()
    return float((w * top).sum() / ws) if ws > 0 else np.nan


def _pool_softmax(s, T):
    """softmax: s = Σ(e^(vᵣ/T)·vᵣ)/Σe^(vᵣ/T), 数值稳定减 max。全部 n 个值参与。"""
    if s is None or len(s) == 0:
        return np.nan
    z = s / float(T)
    z = z - z.max()          # 数值稳定: 平移不改 softmax 权重
    e = np.exp(z)
    es = e.sum()
    return float((e * s).sum() / es) if es > 0 else np.nan


def _pool_rankdecay(s, gamma):
    """rankdecay: s = Σ(wᵣ·vᵣ)/Σwᵣ, wᵣ = 1/log(r+γ), r=1..n 降序秩 (全部值)。

    注: 用 outline 公式 wᵣ=1/log(r+γ), 【不是】旧 p0e 的 d^r 指数衰减。
    r+γ ≥ 1+1 = 2 > 1 -> log(r+γ) > 0, 无除零。
    """
    if s is None or len(s) == 0:
        return np.nan
    n = len(s)
    r = np.arange(1, n + 1, dtype=float)   # 降序秩 r=1..n
    w = 1.0 / np.log(r + float(gamma))
    ws = w.sum()
    return float((w * s).sum() / ws) if ws > 0 else np.nan


def _sorted_desc(arr):
    """去 NaN 并降序排序 -> v₁ ≥ v₂ ≥ ...; 空 -> 长度 0 数组。"""
    a = np.asarray(arr, dtype=float)
    a = a[~np.isnan(a)]
    if len(a) == 0:
        return a
    return np.sort(a)[::-1].copy()


def col_to_toolname(col):
    """MT_<Tool> -> 工具短名 (剥 'MT_' 前缀)。"""
    return col[3:]


def build_variant_specs():
    """返回 [(suffix, fn(s)->float), ...] 的有序列表, 定 pooling 列顺序。

    顺序: max -> topk(k外α内) -> softmax(T) -> rankdecay(γ), 共 51 个/工具。
    """
    specs = []
    # max (无超参)
    specs.append(("max", _pool_max))
    # topk_w: k∈{...} × α∈{...}  (9×4 = 36)
    for k in TOPK_K:
        for a in TOPK_ALPHA:
            suffix = f"topk_k{k}_a{_fmt_num(a)}"
            specs.append((suffix, (lambda s, k=k, a=a: _pool_topk_w(s, k, a))))
    # softmax: T∈{...}  (7)
    for T in SOFTMAX_T:
        suffix = f"softmax_T{_fmt_num(T)}"
        specs.append((suffix, (lambda s, T=T: _pool_softmax(s, T))))
    # rankdecay: γ∈{...}  (7)
    for g in RANKDECAY_GAMMA:
        suffix = f"rankdecay_g{_fmt_num(g)}"
        specs.append((suffix, (lambda s, g=g: _pool_rankdecay(s, g))))
    return specs


def main():
    ap = argparse.ArgumentParser(
        description="子肽×HLA 长表 -> 干净肽级 pooling 冻结表 (outline §2.4 四算子)")
    ap.add_argument("--input", default=None,
                    help="子肽×HLA 长表 (默认 scripts/out/merged_all_tools_30_official.csv)")
    ap.add_argument("--ninemer", action="store_true",
                    help="显式声明 9mer 主分析口径 (默认即 9mer, 无需置位; 与 --allwindow 互斥)")
    ap.add_argument("--allwindow", action="store_true",
                    help="8-14mer 全窗补充口径 (不置位=9mer 主分析, outline §2.2)")
    ap.add_argument("--w811", action="store_true",
                    help="8-11mer 多长度补充口径 (只留子肽长度∈{8,9,10,11}); 与 --allwindow/--ninemer 互斥")
    ap.add_argument("--output", default=None,
                    help="显式输出路径覆盖 (默认写 data/frozen/pooled_clean_<regime>.csv; "
                         "rebuild_canonical.py 用它把产物写进 staging 而不动 canonical)")
    ap.add_argument("--expect-peptides", type=int, default=130,
                    help="锚定期望肽数 (默认 130=官方全集, 零改动; 改动② 纯新窗重跑传 102=仅 SNV, "
                         "28 indel 无 mut-spanning 窗被排除, 不触发空肽 FAIL)")
    args = ap.parse_args()

    # ── 口径三分支 (互斥) ──────────────────────────────────────────────────
    if args.w811 and args.allwindow:
        raise SystemExit("[ERR] --w811 与 --allwindow 互斥, 只能择一 (口径不同)")
    if args.w811:
        ninemer, w811 = False, True
        regime = "8-11mer"
        out_csv = OUT_CSV_W811
    elif args.allwindow:
        ninemer, w811 = False, False
        regime = "全窗 8-14mer"
        out_csv = OUT_CSV_ALLWINDOW
    else:
        ninemer, w811 = True, False
        regime = "9mer"
        out_csv = OUT_CSV_9MER
    if args.output:                       # 显式覆盖 (rebuild 驱动写 staging, 不动 canonical)
        out_csv = Path(args.output)
    print(f"[info] 口径 = {regime} -> 输出 {out_csv.name}")

    in_path = Path(args.input) if args.input else DEFAULT_INPUT
    if not in_path.is_absolute():
        in_path = ROOT / in_path
    if not in_path.exists():
        raise SystemExit(f"[ERR] 长表不存在: {in_path}")
    if not GT_CSV.exists():
        raise SystemExit(f"[ERR] GT 缺失: {GT_CSV} (先跑 p0a_build_groundtruth.py)")

    # ── 读 GT 锚定 130 肽 ────────────────────────────────────────────────
    gt = pd.read_csv(GT_CSV)
    gt["Patient_ID"] = gt["Patient_ID"].astype(int)
    gt["Peptide_ID"] = gt["Peptide_ID"].astype(str)
    gt_keys = gt["mut_key"].tolist()
    assert len(gt_keys) == 130, f"[ERR] GT 锚定肽数={len(gt_keys)} != 130"
    # idx (锚定集) 在读长表后按【长表实际有的肽】定 (rerun 纯新窗只 102 SNV / official 130), 见下。

    # ── 读长表 ──────────────────────────────────────────────────────────
    print(f"[info] 读长表: {in_path}")
    df = pd.read_csv(in_path)
    print(f"[info] 长表 shape={df.shape}")

    for req in (SUBPEP_MT, SUBPEP_WT, FULLPEP_MT, "mut_key"):
        if req not in df.columns:
            raise SystemExit(f"[ERR] 长表缺列: {req}")

    # ── 锚定集 = GT 顺序里【长表实际有的肽】(rerun 只 102 SNV -> 锚 102; official 130 -> 锚 130) ──
    input_keys = set(df["mut_key"].astype(str))
    anchor_keys = [k for k in gt_keys if str(k) in input_keys]
    if not anchor_keys:                       # 与 GT 完全不交(格式漂移?) -> 退回全 GT (旧行为)
        print("[warn] 长表 mut_key 与 GT 无交集, 退回全 130 GT 锚定")
        anchor_keys = gt_keys
    idx = pd.Index(anchor_keys, name="mut_key")
    expect = args.expect_peptides
    print(f"[info] 锚定肽数={len(idx)} (长表实际有; --expect-peptides={expect}); "
          f"GT 全集 130, 缺席={130 - len(idx)} (改动② 纯新窗预期 28 indel 缺席)")

    # peplen 映射 (B2): 每 mut_key 的 MT_FullPeptide 长度, 从【过滤前】全表取, 保证覆盖。
    peplen_map = (df.groupby("mut_key")[FULLPEP_MT]
                    .first().astype(str).str.len())

    # ── A1 含突变窗过滤 (pVACseq 标准, outline §2.2) ──────────────────────
    # 只留 MT_Subpeptide != WT_Subpeptide 的行 (剔纯 WT 窗)。
    # NaN 的 WT (novel 窗) astype(str)='nan' 与 MT 序列不等 -> 保留 (确含突变)。
    before = len(df)
    mut_mask = df[SUBPEP_MT].astype(str) != df[SUBPEP_WT].astype(str)
    df = df[mut_mask].copy()
    print(f"[A1] 含突变窗过滤: {before} -> {len(df)} 行 "
          f"(剔纯 WT 窗 {before - len(df)} 行, {100.0*(before-len(df))/before:.1f}%)")
    if df.empty:
        raise SystemExit("[ERR] 含突变过滤后长表为空, 检查 MT/WT_Subpeptide 列")

    # ── A2 长度过滤 (outline §2.2 主分析口径 9mer; §2.2 补充口径 8-11mer) ─────
    if ninemer:
        before = len(df)
        sub_len = df[SUBPEP_MT].astype(str).str.len()
        df = df[sub_len == 9].copy()
        print(f"[A2] 9mer 过滤: {before} -> {len(df)} 行 (MT_Subpeptide 长度==9)")
        if df.empty:
            raise SystemExit("[ERR] 9mer 过滤后长表为空")
    elif w811:
        before = len(df)
        sub_len = df[SUBPEP_MT].astype(str).str.len()
        df = df[sub_len.isin([8, 9, 10, 11])].copy()
        print(f"[A2] 8-11mer 过滤: {before} -> {len(df)} 行 (MT_Subpeptide 长度∈8-11)")
        if df.empty:
            raise SystemExit("[ERR] 8-11mer 过滤后长表为空")
    else:
        print(f"[A2] 全窗口径: 保留 8-14mer 全部 {len(df)} 行 (不做长度过滤)")

    # ── 工具列检测 (前缀 'MT_' 且非序列列; __AUX_* 天然排除) ────────────────
    tool_cols = []
    for c in df.columns:
        if not c.startswith("MT_") or c in EXCLUDE:
            continue
        df[c] = pd.to_numeric(df[c], errors="coerce")
        tool_cols.append(c)
    if not tool_cols:
        raise SystemExit("[ERR] 未找到 MT_<Tool> 工具分数列")
    tools = {col_to_toolname(c): c for c in tool_cols}
    n_tools = len(tools)
    print(f"[info] 检测到 {n_tools} 个工具: {sorted(tools.keys())}")
    if n_tools != 30:
        print(f"[warn] 工具数={n_tools} != 30 (outline 声明 30); 以长表实际为准, 继续。")

    # ── 组装骨架 (锚定 130 肽) ────────────────────────────────────────────
    out = gt.set_index("mut_key")[["Patient_ID", "Peptide_ID", "Elispot"]].reindex(idx).copy()
    out["peplen"] = peplen_map.reindex(idx).astype("Int64")
    # n_subpep = 该肽【含突变、当前口径】子肽×HLA 行数
    n_subpep = df.groupby("mut_key").size().reindex(idx).fillna(0).astype(int)
    out["n_subpep"] = n_subpep.values

    # ── 逐工具 × 51 pooling 变体 ─────────────────────────────────────────
    specs = build_variant_specs()
    n_variants = len(specs)
    print(f"[info] pooling 变体/工具 = {n_variants} "
          f"(1 max + {len(TOPK_K)*len(TOPK_ALPHA)} topk + "
          f"{len(SOFTMAX_T)} softmax + {len(RANKDECAY_GAMMA)} rankdecay)")

    pooled_data = {}   # colname -> list(按 idx 顺序)
    pooled_cols = []
    for tool, col in sorted(tools.items()):
        # 每 mut_key 预排序一次 (降序去 NaN), 缓存供 51 变体复用
        cache = {}
        sub = df[["mut_key", col]].dropna(subset=[col])
        for mk, series in sub.groupby("mut_key")[col]:
            cache[mk] = _sorted_desc(series.values)
        # 逐变体铺列
        for suffix, fn in specs:
            pcol = f"{tool}_{suffix}"
            pooled_data[pcol] = [fn(cache.get(mk)) for mk in idx]
            pooled_cols.append(pcol)

    pooled_df = pd.DataFrame(pooled_data, index=idx).round(8)  # round8 防浮点 tie
    out = pd.concat([out, pooled_df], axis=1).reset_index()

    # ── 校验门 (fail-loud) ────────────────────────────────────────────────
    # [G1] 行数 == expect (默认 130; rerun 纯新窗传 102=仅 SNV)
    assert len(out) == expect, (
        f"[G1] FAIL: 行数={len(out)} != {expect} "
        f"(锚定={len(idx)}; rerun 纯新窗须 --expect-peptides 102)")
    print(f"[G1] PASS: 行数 == {expect}")

    # [G3] 含突变过滤后每肽仍 ≥1 含突变子肽 (无空肽)
    empty_pep = out.loc[out["n_subpep"] == 0, "mut_key"].tolist()
    if empty_pep:
        raise SystemExit(
            f"[G3] FAIL: {len(empty_pep)} 肽在 {regime} 含突变过滤后无任何子肽行 "
            f"(空肽): {empty_pep}\n        -- 该肽无含突变"
            f"{'9mer' if ninemer else '窗'}, 需回查长表覆盖")
    print(f"[G3] PASS: 每肽 ≥1 含突变{'9mer' if ninemer else '子肽'} (无空肽)")

    # [G2] 每肽 ≥1 工具有值 (整肽行不能全 NaN)
    pooled_mat = out[pooled_cols]
    all_empty = ~pooled_mat.notna().any(axis=1)
    n_all_empty = int(all_empty.sum())
    if n_all_empty > 0:
        bad = out.loc[all_empty, "mut_key"].tolist()
        raise SystemExit(f"[G2] FAIL: {n_all_empty} 肽全工具皆空: {bad}")
    print(f"[G2] PASS: 每肽 ≥1 工具有值")

    # 工具覆盖诊断 (非门, 提示整列空的 pending 工具)
    n_pending = 0
    for tool in sorted(tools):
        cols_t = [c for c in pooled_cols if c.startswith(f"{tool}_")]
        filled = int(out[cols_t].notna().any(axis=1).sum())
        if filled == 0:
            n_pending += 1
            print(f"       [pending] {tool}: 整列空 (0/130 肽有值)")
    if n_pending:
        print(f"[info] pending 工具数: {n_pending}/{n_tools} (整列空, 长表未覆盖)")

    # ── 写出 ─────────────────────────────────────────────────────────────
    FROZEN_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"\n[saved] {out_csv}  shape={out.shape}  (口径={regime})")
    print(f"[info] {n_tools} 工具 × {n_variants} pooling = {len(pooled_cols)} pooled 列 "
          f"(+ 6 元列 mut_key/Patient_ID/Peptide_ID/Elispot/peplen/n_subpep)")
    print("[DONE] p0e2_pool_clean 完成")


if __name__ == "__main__":
    main()
