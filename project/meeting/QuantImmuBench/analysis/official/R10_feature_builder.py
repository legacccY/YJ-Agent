#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R10_feature_builder.py
======================
服务: QuantImmuBench §3.3 集成框架 / C2「有方法贡献的融合」判决性负检验 (预期 NULL)。
对应冻结判据: analysis/official/PREREG_R10_featfusion.md §1 (分层特征)。

做什么:
  按 mut_key 把 ds2_official_groundtruth.csv merge 到 pooled_clean_9mer.csv, 构建 L0→L4 逐层
  累积特征矩阵 + covariate-only (归因闸对照) 矩阵, 输出一份合并特征表 + 一份 manifest.json
  (记每列属哪层 / kind=tool|covariate|meta / 缺失率 / TODO)。下游 R10_leak_free_lopo.py 按
  manifest 取层选列跑 leak-free LOPO。

━━━ leak-free 保证 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  本脚本**只造特征, 不碰标签, 不做任何跨样本拟合/标准化/填充**。所有特征都是「每条肽自身
  可算」的函数 (工具分 / GT 元数据 / 序列理化), 无 label、无跨折统计 → 天然 leak-free。
  真正的防泄漏协议 (折内标准化/填充/患者内归一) 在 R10_leak_free_lopo.py 里做。

━━━ 层定义 (累积; PREREG §1) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  L0 = SURV6 六工具 _max (PredIG/IMPROVE/pTuneos/PRIME/ImmuneApp/deepHLApan)。   [kind=tool]
  L1 = L0 + log1p(TPM) + CCF + Clonal + is_indel + is_driver。                    [+covariate]
  L2 = L1 + DAI_improve(max(RankEL_WT-RankEL_MT,0)) + DAI_tesla(max(log2(Aff_WT/Aff_MT),0))
           + DAI_missing 指示列。
       ⚠️⚠️ 数据无 WT 序列/无 WT netMHCpan 分数 (Bash 核: 无 WT 列) → DAI 两形式无法算 →
       全 NaN, DAI_missing 常量=1, 本层对 L1 无真增量。留 --wt_scores 接口: 传入含 WT MT
       netMHCpan RankEL/Aff 的 csv (列 mut_key + wt_rankEL/mt_rankEL/wt_aff/mt_aff) 即自动算。
       TODO(需 researcher/数据组): 用 netMHCpan 对 WT_FullPeptide 重打分产 WT 分, 否则 L2≡L1。
  L3 = L2 + 理化(HydroCore/PropHydroAro/Aro/PropSmall/PropAcidic/PropBasic/Inst/pI/mw)
           + SelfSim(MT↔WT, BLOSUM62)。                                          [+covariate]
       理化在 Short_Epitope(MT 短表位) 上纯手写算 (氨基酸性质表见下), 减少外部库依赖。
       Inst(不稳定指数)需 Guruprasad DIWV 400 项二肽表, 风险高不手嵌 → 若 Biopython 可 import
       用其 ProtParam 算, 否则 NaN + TODO (声明可选依赖 Biopython)。
       SelfSim 需 WT epitope → 用 Gene_and_Protein_Change 的 p.XnnnY 注释 best-effort 重建
       SNV 的 WT 短表位 (indel/歧义 → NaN + SelfSim_missing=1)。BLOSUM62 均值相似。
  L4 = L3 + 工具分歧元特征(rank_var / rank_entropy / present_immuno_gap / tool_gap)。 [+meta]
       在全覆盖工具池 _max 上, 患者内百分位 rank → 逐肽算 (无 label, leak-free)。
  covariate-only = L1-L3 的**非工具**免疫学特征, drop 全部工具分(L0) + 工具派生(DAI/L4 meta)。
       用于 PREREG §3 归因闸: full 须 > max(单工具, covariate-only) 才算「整合工具」而非学粗规律。

━━━ 🔒 边核 TODO (不臆想; PREREG §0/§1) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  TODO#1 [已解, 无需改]: 二元标签 Ttest_pvalue_InVitroStim 在 xlsx 'In Vitro' sheet, 阈 0.05
    —— 标签构建不在本脚本 (在 lopo/eval), S1_peptide_level_auprc.py 已静态核过该列存在。
  TODO#2 [数据缺, 已按红线处理]: 无 WT netMHCpan 分数 → DAI 全 NaN + missing 指示 + 留接口,
    绝不硬造 (task 派单: 不够则该层标 TODO 待补 WT 打分, 别硬造)。
  TODO#3 [论文语义近似, 需实核]: 锚位定义(9mer=P2+PΩ)、SelfSim BLOSUM62 kernel、理化公式
    均为**论文语义近似**, 未逐行对齐官方 IMPROVE feature_calculations.py (researcher 报 GitHub
    404 未逐行核)。⚠️ 需 `gh clone SRHgroup/IMPROVE_tool` 逐行核锚位/kernel 再定稿。
  foreignness: 留 _foreignness() → NotImplementedError('需 antigen.garnish+IEDB, 暂缓')。

━━━ 输入 (只读) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  data/frozen/pooled_clean_9mer.csv       (130 肽 × 30 工具×51 pooling + peplen/n_subpep)
  data/frozen/ds2_official_groundtruth.csv (按 mut_key merge 的 GT 元数据)
  [可选] --wt_scores <csv>                 (含 WT/MT netMHCpan RankEL/Aff, 供 DAI; 缺则 DAI=NaN)

━━━ 输出 (analysis/official/) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  R10_featfusion_features.csv   —— mut_key + Patient_ID + Elispot + 全部特征列 (L4 全集)。
  R10_featfusion_manifest.json  —— {layers(累积), layer_added(增量), covariate_only,
                                    kind{col->tool|covariate|meta}, missing_rate, todo}。

━━━ 跑法 (主线跑, 我不跑) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  python analysis/official/R10_feature_builder.py
  python analysis/official/R10_feature_builder.py --wt_scores <path_to_wt_scores.csv>

Windows 规范: UTF-8 stdout, pathlib 路径, 纯 numpy/pandas (Inst 用可选 Biopython), 零 GPU。
"""

import sys
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _official_common import (                              # noqa: E402
    load_frozen, FROZEN_POOLED, FROZEN_GT, ensure_out_dir,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent

# ── L0 SURV6 (同 R3/R5 口径, 零选择 _max) ────────────────────────────────────────
SURV6 = ["PredIG", "IMPROVE", "pTuneos", "PRIME", "ImmuneApp", "deepHLApan"]
L0_COLS = [f"{t}_max" for t in SURV6]

# ═══════════════════════════════════════════════════════════════════════════════
# 氨基酸性质表 (纯手写, TODO#3 论文语义近似, 未逐行对齐官方 IMPROVE)
# ═══════════════════════════════════════════════════════════════════════════════
AA20 = "ARNDCQEGHILKMFPSTWYV"

# Kyte-Doolittle 疏水指数 (1982 原表)
KD = {"A": 1.8, "R": -4.5, "N": -3.5, "D": -3.5, "C": 2.5, "Q": -3.5, "E": -3.5,
      "G": -0.4, "H": -3.2, "I": 4.5, "L": 3.8, "K": -3.9, "M": 1.9, "F": 2.8,
      "P": -1.6, "S": -0.8, "T": -0.7, "W": -0.9, "Y": -1.3, "V": 4.2}

# 平均残基质量 (Da, 已减水; MW = Σ残基 + 一个水 18.01524)
AA_MASS = {"A": 71.0788, "R": 156.1875, "N": 114.1038, "D": 115.0886, "C": 103.1388,
           "E": 129.1155, "Q": 128.1307, "G": 57.0519, "H": 137.1411, "I": 113.1594,
           "L": 113.1594, "K": 128.1741, "M": 131.1926, "F": 147.1766, "P": 97.1167,
           "S": 87.0782, "T": 101.1051, "W": 186.2132, "Y": 163.1760, "V": 99.1326}
WATER = 18.01524

# 残基性质集合 (论文语义近似, TODO#3 待官方核)
AROMATIC = set("FWY")
HYDROPHOBIC = set("AVLIPMFWC")                 # 疏水侧链 (含芳香族的 F/W)
PROPHYDROARO = HYDROPHOBIC | AROMATIC          # 疏水+芳香并集 (PropHydroAro, IMPROVE 头号信号族)
SMALL = set("AGSCTPDNV")                        # 小体积残基 (ProtScale 语义近似)
ACIDIC = set("DE")
BASIC = set("KRH")

# 侧链可解离基 pKa (ExPASy/EMBOSS 常用值, 论文语义近似); N/C 端亦计入
PKA_POS = {"K": 10.5, "R": 12.5, "H": 6.0}     # 质子化带正电
PKA_NEG = {"D": 3.9, "E": 4.1, "C": 8.5, "Y": 10.1}  # 去质子带负电
PKA_NTERM = 9.0
PKA_CTERM = 3.1


def _clean_seq(seq):
    """取序列大写, 仅保留 20 标准氨基酸字母 (剔 X/*/间隔)。空 -> ''。"""
    if not isinstance(seq, str):
        return ""
    return "".join(ch for ch in seq.upper() if ch in KD)


def _hydro_core(seq):
    """结合核区去锚位 Kyte-Doolittle 平均疏水 (HydroCore, IMPROVE 头号信号)。
    锚位 = 9mer 的 P2 + PΩ(末位) —— 论文语义近似 (TODO#3, 9mer 锚位 P2/P9)。核区 = 去掉
    P2 与末位后的中段残基。序列 <4 残基 → 无有效核区 → NaN。
    """
    s = _clean_seq(seq)
    L = len(s)
    if L < 4:
        return np.nan
    core = [s[i] for i in range(L) if i != 1 and i != (L - 1)]   # 去 P2(idx1) 与末位
    if not core:
        return np.nan
    return float(np.mean([KD[a] for a in core]))


def _frac(seq, aa_set):
    s = _clean_seq(seq)
    if not s:
        return np.nan
    return float(sum(1 for a in s if a in aa_set) / len(s))


def _mw(seq):
    s = _clean_seq(seq)
    if not s:
        return np.nan
    return float(sum(AA_MASS[a] for a in s) + WATER)


def _pi(seq):
    """等电点 pI: Henderson-Hasselbalch 二分求净电荷=0 的 pH (纯 numpy, 无 scipy)。
    净电荷(pH) = Σ_pos 1/(1+10^(pH-pKa)) - Σ_neg 1/(1+10^(pKa-pH)) + N/C 端。
    """
    s = _clean_seq(seq)
    if not s:
        return np.nan
    counts = {a: s.count(a) for a in set(s)}

    def net_charge(pH):
        pos = 1.0 / (1.0 + 10 ** (pH - PKA_NTERM))                       # N 端
        for a, pk in PKA_POS.items():
            pos += counts.get(a, 0) * (1.0 / (1.0 + 10 ** (pH - pk)))
        neg = 1.0 / (1.0 + 10 ** (PKA_CTERM - pH))                       # C 端
        for a, pk in PKA_NEG.items():
            neg += counts.get(a, 0) * (1.0 / (1.0 + 10 ** (pk - pH)))
        return pos - neg

    lo, hi = 0.0, 14.0
    for _ in range(100):                                                # 二分 100 次足够收敛
        mid = 0.5 * (lo + hi)
        if net_charge(mid) > 0:
            lo = mid
        else:
            hi = mid
    return float(0.5 * (lo + hi))


def _instability(seq):
    """不稳定指数 Inst (Guruprasad 1990 DIWV 二肽表)。DIWV 400 项手嵌风险高 → 用可选
    Biopython ProtParam 算 (声明可选依赖); 不可 import → NaN (TODO#3, 待补 DIWV 表或装 Biopython)。
    """
    s = _clean_seq(seq)
    if len(s) < 2:
        return np.nan
    try:
        from Bio.SeqUtils.ProtParam import ProteinAnalysis   # 可选依赖
    except Exception:
        return np.nan
    try:
        return float(ProteinAnalysis(s).instability_index())
    except Exception:
        return np.nan


# ═══════════════════════════════════════════════════════════════════════════════
# BLOSUM62 (标准表, 顺序 = AA20 = ARNDCQEGHILKMFPSTWYV) —— SelfSim 用
# ═══════════════════════════════════════════════════════════════════════════════
_BLOSUM62_ROWS = [
    [4, -1, -2, -2, 0, -1, -1, 0, -2, -1, -1, -1, -1, -2, -1, 1, 0, -3, -2, 0],   # A
    [-1, 5, 0, -2, -3, 1, 0, -2, 0, -3, -2, 2, -1, -3, -2, -1, -1, -3, -2, -3],   # R
    [-2, 0, 6, 1, -3, 0, 0, 0, 1, -3, -3, 0, -2, -3, -2, 1, 0, -4, -2, -3],       # N
    [-2, -2, 1, 6, -3, 0, 2, -1, -1, -3, -4, -1, -3, -3, -1, 0, -1, -4, -3, -3],  # D
    [0, -3, -3, -3, 9, -3, -4, -3, -3, -1, -1, -3, -1, -2, -3, -1, -1, -2, -2, -1],  # C
    [-1, 1, 0, 0, -3, 5, 2, -2, 0, -3, -2, 1, 0, -3, -1, 0, -1, -2, -1, -2],      # Q
    [-1, 0, 0, 2, -4, 2, 5, -2, 0, -3, -3, 1, -2, -3, -1, 0, -1, -3, -2, -2],     # E
    [0, -2, 0, -1, -3, -2, -2, 6, -2, -4, -4, -2, -3, -3, -2, 0, -2, -2, -3, -3], # G
    [-2, 0, 1, -1, -3, 0, 0, -2, 8, -3, -3, -1, -2, -1, -2, -1, -2, -2, 2, -3],   # H
    [-1, -3, -3, -3, -1, -3, -3, -4, -3, 4, 2, -3, 1, 0, -3, -2, -1, -3, -1, 3],  # I
    [-1, -2, -3, -4, -1, -2, -3, -4, -3, 2, 4, -2, 2, 0, -3, -2, -1, -2, -1, 1],  # L
    [-1, 2, 0, -1, -3, 1, 1, -2, -1, -3, -2, 5, -1, -3, -1, 0, -1, -3, -2, -2],   # K
    [-1, -1, -2, -3, -1, 0, -2, -3, -2, 1, 2, -1, 5, 0, -2, -1, -1, -1, -1, 1],   # M
    [-2, -3, -3, -3, -2, -3, -3, -3, -1, 0, 0, -3, 0, 6, -4, -2, -2, 1, 3, -1],   # F
    [-1, -2, -2, -1, -3, -1, -1, -2, -2, -3, -3, -1, -2, -4, 7, -1, -1, -4, -3, -2],  # P
    [1, -1, 1, 0, -1, 0, 0, 0, -1, -2, -2, 0, -1, -2, -1, 4, 1, -3, -2, -2],      # S
    [0, -1, 0, -1, -1, -1, -1, -2, -2, -1, -1, -1, -1, -2, -1, 1, 5, -2, -2, 0],  # T
    [-3, -3, -4, -4, -2, -2, -3, -2, -2, -3, -2, -3, -1, 1, -4, -3, -2, 11, 2, -3],  # W
    [-2, -2, -2, -3, -2, -1, -2, -3, 2, -1, -1, -2, -1, 3, -3, -2, -2, 2, 7, -1], # Y
    [0, -3, -3, -3, -1, -2, -2, -3, -3, 3, 1, -2, 1, -1, -2, -2, 0, -3, -1, 4],   # V
]
_AA_IDX = {a: i for i, a in enumerate(AA20)}
BLOSUM62 = {(a, b): _BLOSUM62_ROWS[_AA_IDX[a]][_AA_IDX[b]]
            for a in AA20 for b in AA20}


def _self_sim(mt_seq, wt_seq):
    """SelfSim(MT↔WT) = 逐位 BLOSUM62(mt_i, wt_i) 均值 (论文语义近似, TODO#3)。
    两序列须等长且非空; 不等长/含非标准残基剔位后为空 → NaN。
    """
    mt, wt = _clean_seq(mt_seq), _clean_seq(wt_seq)
    if not mt or not wt or len(mt) != len(wt):
        return np.nan
    scores = [BLOSUM62[(a, b)] for a, b in zip(mt, wt) if a in _AA_IDX and b in _AA_IDX]
    if not scores:
        return np.nan
    return float(np.mean(scores))


def _foreignness():
    raise NotImplementedError("需 antigen.garnish+IEDB, 暂缓")


# ═══════════════════════════════════════════════════════════════════════════════
# WT epitope best-effort 重建 (SNV only, 供 SelfSim; indel/歧义 → NaN)
# ═══════════════════════════════════════════════════════════════════════════════
import re

_PROT_CHANGE_RE = re.compile(r"p\.([A-Z])(\d+)([A-Z])$")   # p.E545K → (E, 545, K)


def reconstruct_wt_epitope(short_epitope, prot_change, variant_type):
    """从 Gene_and_Protein_Change 的 p.<WT><pos><MT> 注释, best-effort 重建 SNV 的 WT 短表位。
    仅 SNV: 在 MT 短表位中定位「等于 MT 残基」的位置, 唯一则替换回 WT 残基得 WT 表位; 位置数
    !=1 (0 个或多个, 歧义) → 无法重建 → None。indel / 注释不匹配 → None。
    ⚠️ TODO#3: 蛋白坐标(545)非表位坐标, 靠残基匹配定位是**近似**, 需官方 WT 序列实核。
    返回 (wt_epitope | None, recon_ok: 1.0/0.0)。
    """
    vt = str(variant_type).upper().strip()
    if vt not in ("SNV",):                           # 仅 SNV 可重建 (indel 无简单 WT)
        return None, 0.0
    if not isinstance(prot_change, str):
        return None, 0.0
    m = _PROT_CHANGE_RE.search(prot_change.strip())
    if not m:
        return None, 0.0
    wt_res, _pos, mt_res = m.group(1), m.group(2), m.group(3)
    s = _clean_seq(short_epitope)
    if not s:
        return None, 0.0
    hits = [i for i, ch in enumerate(s) if ch == mt_res]
    if len(hits) != 1:                               # 0 个或多个 → 歧义, 不硬造
        return None, 0.0
    idx = hits[0]
    wt = s[:idx] + wt_res + s[idx + 1:]
    return wt, 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# L4 工具分歧元特征 (患者内百分位 rank, 无 label, leak-free)
# ═══════════════════════════════════════════════════════════════════════════════
# 呈递类(结合亲和)vs 免疫原类工具分组 —— TODO#3 待袁/朱确认 outline 分类。
PRESENTATION_TOOLS = ["netMHCpan_BA", "netMHCpan_EL", "netMHCstabpan", "MHCflurry",
                      "MHCnuggets", "HLAthena", "deepHLApan", "TransHLA", "MHCseqNet"]
IMMUNO_TOOLS = ["PRIME", "DeepImmuno", "IEDB_Calis", "Repitope", "PredIG", "IMPROVE",
                "pTuneos", "ImmuneApp", "BigMHC_IM", "CNNeo", "ICERFIRE", "NeoTImmuML"]


def _pct_rank_within_patient(df, cols):
    """每列在每患者内做百分位 rank (0..1), 返回 dict col->ndarray(对齐 df 行)。
    患者内缺失填该患者该列均值再 rank; 全缺 → 0.5 (无信息中点)。leak-free (无 label)。
    """
    out = {c: np.full(len(df), np.nan) for c in cols}
    for _pat, g in df.groupby("Patient_ID"):
        idx = g.index
        for c in cols:
            v = g[c].astype(float)
            v = v.fillna(v.mean())
            if v.notna().sum() == 0:
                out[c][df.index.get_indexer(idx)] = 0.5
                continue
            r = v.rank(method="average", pct=True).values
            out[c][df.index.get_indexer(idx)] = r
    return out


def build_l4_meta(df):
    """L4 工具分歧元特征 (逐肽标量): rank_var / rank_entropy / present_immuno_gap / tool_gap。
    在全覆盖(notna 全 130)工具 _max 上做患者内百分位 rank, 再逐肽跨工具聚合。返回 DataFrame。
    """
    from _official_common import TOOLS_30
    full_cov = [f"{t}_max" for t in TOOLS_30
                if f"{t}_max" in df.columns and int(df[f"{t}_max"].notna().sum()) == len(df)]
    if len(full_cov) < 3:
        print(f"[warn] L4: 全覆盖工具 <3 ({len(full_cov)}), 元特征可能退化")
    pr = _pct_rank_within_patient(df, full_cov)
    M = np.column_stack([pr[c] for c in full_cov]) if full_cov else np.zeros((len(df), 1))

    rank_var = np.nanvar(M, axis=1)
    rank_gap = np.nanmax(M, axis=1) - np.nanmin(M, axis=1)
    # 熵: 把该肽跨工具的百分位 rank 归一成分布再算 (分歧越大熵越高), eps 防 log0
    P = M / np.clip(M.sum(axis=1, keepdims=True), 1e-12, None)
    rank_entropy = -np.nansum(P * np.log(np.clip(P, 1e-12, None)), axis=1)

    # 呈递类 vs 免疫原类 一致度 gap = |两组均值百分位之差|
    pres_cols = [f"{t}_max" for t in PRESENTATION_TOOLS if f"{t}_max" in full_cov]
    immu_cols = [f"{t}_max" for t in IMMUNO_TOOLS if f"{t}_max" in full_cov]
    if pres_cols and immu_cols:
        pres_mean = np.nanmean(np.column_stack([pr[c] for c in pres_cols]), axis=1)
        immu_mean = np.nanmean(np.column_stack([pr[c] for c in immu_cols]), axis=1)
        pres_immu_gap = np.abs(pres_mean - immu_mean)
    else:
        print("[warn] L4: 呈递/免疫原分组缺列, present_immuno_gap 置 NaN")
        pres_immu_gap = np.full(len(df), np.nan)

    return pd.DataFrame({
        "L4_rank_var": rank_var,
        "L4_rank_entropy": rank_entropy,
        "L4_present_immuno_gap": pres_immu_gap,
        "L4_tool_gap": rank_gap,
    }, index=df.index)


# ═══════════════════════════════════════════════════════════════════════════════
# DAI (需 WT 打分; 无 WT 分 → 全 NaN + missing 指示 + TODO)
# ═══════════════════════════════════════════════════════════════════════════════
def build_dai(df, wt_scores_path):
    """DAI 两形式 + DAI_missing。
      · DAI_improve = max(RankEL_WT - RankEL_MT, 0)   (IMPROVE 差值版)
      · DAI_tesla   = max(log2(Aff_WT / Aff_MT), 0)    (TESLA 比值版)
    需 --wt_scores csv (列 mut_key + wt_rankEL/mt_rankEL/wt_aff/mt_aff)。
    ⚠️ 数据现无 WT netMHCpan 分数 (TODO#2) → 不传该文件时 DAI 两列全 NaN, DAI_missing=1。
    """
    n = len(df)
    dai_imp = np.full(n, np.nan)
    dai_tes = np.full(n, np.nan)
    missing = np.ones(n)                              # 默认全缺 (无 WT 分)
    if wt_scores_path:
        p = Path(wt_scores_path)
        if not p.exists():
            print(f"[warn] --wt_scores 不存在: {p}; DAI 保持全 NaN")
        else:
            ws = pd.read_csv(p, encoding="utf-8")
            need = {"mut_key", "wt_rankEL", "mt_rankEL", "wt_aff", "mt_aff"}
            if not need.issubset(ws.columns):
                print(f"[warn] --wt_scores 缺列 {need - set(ws.columns)}; DAI 保持全 NaN")
            else:
                mp = ws.set_index("mut_key")
                for i, mk in enumerate(df["mut_key"].values):
                    if mk not in mp.index:
                        continue
                    row = mp.loc[mk]
                    wr, mr = row["wt_rankEL"], row["mt_rankEL"]
                    wa, ma = row["wt_aff"], row["mt_aff"]
                    ok = False
                    if pd.notna(wr) and pd.notna(mr):
                        dai_imp[i] = max(float(wr) - float(mr), 0.0); ok = True
                    if pd.notna(wa) and pd.notna(ma) and float(ma) > 0 and float(wa) > 0:
                        dai_tes[i] = max(np.log2(float(wa) / float(ma)), 0.0); ok = True
                    if ok:
                        missing[i] = 0.0
                print(f"[DAI] 从 {p.name} 算得 DAI (缺 WT 分的肽 missing=1)")
    if float(np.nanmin(missing)) == 1.0:
        print("[DAI] ⚠️ 全部肽 DAI_missing=1 (无 WT 打分) → L2 对 L1 无真增量 (TODO#2 待补 WT 分)")
    return pd.DataFrame({"L2_DAI_improve": dai_imp, "L2_DAI_tesla": dai_tes,
                         "L2_DAI_missing": missing}, index=df.index)


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(
        description="R10 特征构建: L0→L4 分层 + covariate-only (§3.3 融合负检验)")
    ap.add_argument("--input", default=str(FROZEN_POOLED), help="pooled 干净表路径")
    ap.add_argument("--gt", default=str(FROZEN_GT), help="GT 元数据表路径")
    ap.add_argument("--wt_scores", default=None,
                    help="[可选] WT/MT netMHCpan 分数 csv (供 DAI; 缺则 DAI 全 NaN)")
    args = ap.parse_args()

    df = load_frozen(args.input).reset_index(drop=True)
    gt = pd.read_csv(args.gt, encoding="utf-8")
    print(f"[info] pooled={df.shape}; GT={gt.shape}")

    # ── merge GT 元列 (按 mut_key) ────────────────────────────────────────────
    gt_cols = ["mut_key", "TPM_PurifiedTumorRNA", "CCF", "Clonal", "Variant_Type",
               "Mutation_type", "Short_Epitope", "Gene_and_Protein_Change"]
    gt_use = gt[[c for c in gt_cols if c in gt.columns]].copy()
    m = df.merge(gt_use, on="mut_key", how="left")
    if len(m) != len(df):
        sys.exit(f"[ERR] merge 后行数变化 {len(df)}->{len(m)} (mut_key 非一对一)")
    n_match = int(m["Short_Epitope"].notna().sum()) if "Short_Epitope" in m else 0
    print(f"[merge] GT 元列 merge 完成; Short_Epitope 匹配 {n_match}/{len(m)}")

    feats = {}                                        # 特征列 -> ndarray
    layer_added = {"L0": [], "L1": [], "L2": [], "L3": [], "L4": []}
    kind = {}                                         # col -> tool|covariate|meta

    # ── L0: SURV6 _max (工具) ──────────────────────────────────────────────────
    for c in L0_COLS:
        if c not in m.columns or m[c].notna().sum() == 0:
            print(f"[warn] L0 缺列 {c}")
            continue
        feats[c] = m[c].values.astype(float)
        layer_added["L0"].append(c); kind[c] = "tool"

    # ── L1: 免疫学 covariate ───────────────────────────────────────────────────
    tpm = pd.to_numeric(m.get("TPM_PurifiedTumorRNA"), errors="coerce")
    feats["L1_log1p_TPM"] = np.log1p(tpm.values.astype(float))
    feats["L1_CCF"] = pd.to_numeric(m.get("CCF"), errors="coerce").values.astype(float)
    feats["L1_Clonal"] = pd.to_numeric(m.get("Clonal"), errors="coerce").values.astype(float)
    vt = m.get("Variant_Type").astype(str).str.upper().str.strip()
    feats["L1_is_indel"] = vt.isin(["DEL", "INS"]).astype(float).values
    mut = m.get("Mutation_type").astype(str).str.strip().str.lower()
    feats["L1_is_driver"] = (mut == "driver").astype(float).values
    for c in ["L1_log1p_TPM", "L1_CCF", "L1_Clonal", "L1_is_indel", "L1_is_driver"]:
        layer_added["L1"].append(c); kind[c] = "covariate"

    # ── L2: DAI (工具派生; 无 WT 分 → 全 NaN + missing) ─────────────────────────
    dai = build_dai(m, args.wt_scores)
    for c in dai.columns:
        feats[c] = dai[c].values.astype(float)
        layer_added["L2"].append(c)
        kind[c] = "tool"          # DAI 依赖 netMHCpan 打分 → 归为 tool-derived (归因闸时 drop)

    # ── L3: 理化 (covariate, 序列派生) + SelfSim ───────────────────────────────
    short = m.get("Short_Epitope")
    pc = m.get("Gene_and_Protein_Change")
    hydro, pha, aro, small, acid, basic = ([] for _ in range(6))
    inst, pI, mw, selfsim, selfmiss = ([] for _ in range(5))
    for i in range(len(m)):
        s = short.iloc[i] if short is not None else None
        hydro.append(_hydro_core(s))
        pha.append(_frac(s, PROPHYDROARO))
        aro.append(_frac(s, AROMATIC))
        small.append(_frac(s, SMALL))
        acid.append(_frac(s, ACIDIC))
        basic.append(_frac(s, BASIC))
        inst.append(_instability(s))
        pI.append(_pi(s))
        mw.append(_mw(s))
        wt_ep, ok = reconstruct_wt_epitope(
            s, pc.iloc[i] if pc is not None else None,
            m["Variant_Type"].iloc[i] if "Variant_Type" in m else None)
        ss = _self_sim(s, wt_ep) if wt_ep is not None else np.nan
        selfsim.append(ss)
        selfmiss.append(0.0 if (wt_ep is not None and not np.isnan(ss)) else 1.0)
    l3 = {
        "L3_HydroCore": hydro, "L3_PropHydroAro": pha, "L3_Aro": aro,
        "L3_PropSmall": small, "L3_PropAcidic": acid, "L3_PropBasic": basic,
        "L3_Inst": inst, "L3_pI": pI, "L3_mw": mw,
        "L3_SelfSim": selfsim, "L3_SelfSim_missing": selfmiss,
    }
    for c, v in l3.items():
        feats[c] = np.asarray(v, float)
        layer_added["L3"].append(c); kind[c] = "covariate"   # 序列派生, 非工具
    n_ss = int(np.nansum([1.0 - x for x in selfmiss]))
    n_inst = int(np.sum(~np.isnan(np.asarray(inst, float))))
    print(f"[L3] SelfSim 可算(SNV WT 重建成功) {n_ss}/{len(m)}; Inst 可算(Biopython) {n_inst}/{len(m)}")
    if n_inst == 0:
        print("[L3] ⚠️ Inst 全 NaN (Biopython 未装) —— TODO#3: 装 Biopython 或手嵌 DIWV 表")

    # ── L4: 工具分歧元特征 (meta) ──────────────────────────────────────────────
    l4 = build_l4_meta(m)
    for c in l4.columns:
        feats[c] = l4[c].values.astype(float)
        layer_added["L4"].append(c); kind[c] = "meta"

    # ── 组装输出表 ─────────────────────────────────────────────────────────────
    feat_df = pd.DataFrame(feats, index=m.index)
    out = pd.concat([m[["mut_key", "Patient_ID", "Elispot"]].reset_index(drop=True),
                     feat_df.reset_index(drop=True)], axis=1)

    # 累积层 (L1=L0+L1_added, ...)
    layers, cum = {}, []
    for lname in ["L0", "L1", "L2", "L3", "L4"]:
        cum = cum + layer_added[lname]
        layers[lname] = list(cum)

    # covariate-only = L1-L3 里 kind=='covariate' 的列 (drop 工具 + tool-derived + meta)
    cov_only = [c for c in layers["L3"] if kind.get(c) == "covariate"]

    missing_rate = {c: float(np.mean(np.isnan(feat_df[c].values.astype(float))))
                    for c in feat_df.columns}

    todo = [
        "TODO#2: 无 WT netMHCpan 分数 → DAI 全 NaN(L2≡L1); 需数据组用 netMHCpan 对 WT 重打分, "
        "产 --wt_scores csv(mut_key+wt_rankEL/mt_rankEL/wt_aff/mt_aff)。",
        "TODO#3: 锚位(9mer P2/PΩ)/SelfSim BLOSUM62 kernel/理化公式为论文语义近似, 未逐行对齐官方 "
        "IMPROVE feature_calculations.py, 需 gh clone SRHgroup/IMPROVE_tool 实核。",
        "TODO#3: Inst 需 Biopython(可选依赖); 未装则全 NaN。L4 呈递/免疫原分组待袁/朱确认。",
        "foreignness 留 NotImplementedError(需 antigen.garnish+IEDB, 暂缓)。",
    ]
    manifest = {
        "service": "QuantImmuBench §3.3 集成框架 / C2 融合负检验 (预期 NULL)",
        "prereg": "PREREG_R10_featfusion.md",
        "input": Path(args.input).name, "gt": Path(args.gt).name,
        "wt_scores": (Path(args.wt_scores).name if args.wt_scores else None),
        "n_peptides": int(len(out)),
        "layers": layers, "layer_added": layer_added,
        "covariate_only": cov_only,
        "kind": kind, "missing_rate": missing_rate,
        "L0_surv6": SURV6, "strongest_single": "netMHCpan_BA_max",
        "todo": todo,
    }

    out_dir = ensure_out_dir()
    feat_path = out_dir / "R10_featfusion_features.csv"
    with open(feat_path, "w", encoding="utf-8", newline="") as f:
        f.write("# R10_featfusion_features.csv — L0→L4 分层特征 (§3.3 融合负检验, 预期 NULL)\n")
        f.write("# 只造特征不碰标签, 天然 leak-free; 防泄漏协议在 R10_leak_free_lopo.py 折内做。\n")
        f.write("# 列-层-kind 映射见 R10_featfusion_manifest.json; L2 DAI 全 NaN(无 WT 分, TODO#2)。\n")
        out.to_csv(f, index=False)
    print(f"[saved] {feat_path}  shape={out.shape}")

    man_path = out_dir / "R10_featfusion_manifest.json"
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"[saved] {man_path}")
    print("[manifest] 各层维数:",
          {k: len(v) for k, v in layers.items()}, "| covariate-only:", len(cov_only))
    print("[DONE] R10_feature_builder")


if __name__ == "__main__":
    main()
