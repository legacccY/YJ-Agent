#!/usr/bin/env python3
"""
feature_calc_local.py  (降级版 v2)
==============================
IMPROVE feature_calculations.py 的本地修复+降级版。

修改点（相对原版 feature_calculations.py）：
  1. sys.path 从硬编码 SRHgroup 路径改为动态推断
  2. [降级] 跳过 netMHCstabpan 调用（本地 WSL netMHCpan-2.8 后端乱码，
     输出垃圾肽+恒定分，inner-merge 会丢掉所有行）
     → 代替：在 merge 后注入 Stability=NaN 列，Predict 脚本会 fillna(col.mean()) impute
  3. 用本地实现的 runFeatureGeneration_no_stab() 替代原 runFeatureGeneration_NetMHCpan_stab_prime_molecular()
     —— 直接调 multimerPatientTools 的子函数，完全不改 multimerPatientTools.py
  4. 其余逻辑（netMHCpan-4.1 binding mut/wt、PRIME、SelfSim、理化特征）100% 保留

保留的特征（HLA 特异）：
  RankEL(mut), RankBA(mut), RankEL_wt, DAI, Prime, SelfSim, mw, Aro, Inst,
  PropHydroAro, CysRed, pI, HydroAll, HydroCore, PropSmall, PropAro, PropBasic,
  PropAcidic, Core, CoreNonAnchor, Loci

缺失的特征（→ NaN，Predict 会 impute）：
  Stability, Foreigness, NetMHCExp, Expression

服务: quantimmu-bench IMPROVE feature_calc 解锁
"""

# ---------- Load global modules ----------
import random
import os
import sys
import importlib
import seaborn as sns
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# FIX 1: 动态 sys.path
_SRC_PATH = os.path.join(
    os.path.expanduser("~"),
    "quantimmu/tools_repos/IMPROVE_tool/bin/src"
)
if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)

import multimerPatientTools
import procTools
import physiochemical_properties
import kernelSim

# ---------- arg parse ----------
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--file", "-i", type=str, required=True)
parser.add_argument("--outfile", "-o", type=str, required=True)
parser.add_argument("--dataset", "-d", type=str, required=True)
parser.add_argument("--PredDir", "-r", type=str, required=True)
parser.add_argument("--ProgramDir", "-p", type=str, required=True)
parser.add_argument("--TmpDir", "-t", type=str, required=True)
args = parser.parse_args()

infile = args.file
dataset_name = args.dataset
output_file = args.outfile
PredictionDirectory = args.PredDir
ProgramDirectory = args.ProgramDir
TemptDirectory = args.TmpDir

# cwd 需在 IMPROVE_tool/（run_feature_calc.sh 已 cd）以便 kernelSim 找 data/matrices/blosum62.qij
homeDir = '.'
print(homeDir)

pd.set_option("display.max_columns", 999)
pd.set_option("display.max_rows", None)
sns.set_context(context='talk', rc={"lines.linewidth": 2})

# ---------- 读输入 ----------
df = pd.read_csv(os.path.join(homeDir, infile), sep='\t')

# 兼容 WT_peptide 列名（防御性二次 rename，run_feature_calc.sh Step1 已做一次）
if 'WT_peptide' in df.columns and 'Norm_peptide' not in df.columns:
    df = df.rename(columns={'WT_peptide': 'Norm_peptide'})

# correct if Norm peptide is NA
df['PeptNorm'] = df.apply(
    lambda row: row['Mut_peptide'] if pd.isna(row['Norm_peptide']) else row['Norm_peptide'],
    axis=1
)

df = df.rename(columns={'HLA_allele': 'MHC', 'Mut_peptide': 'PeptMut'})
cols = ['MHC', 'PeptMut', 'PeptNorm']
dfdup = df[cols]
dfdup = dfdup[dfdup.duplicated(keep=False)]
dfSel = df[cols].drop_duplicates()
dfSel['PeptLen'] = dfSel['PeptMut'].apply(len)
dfSel['HLA'] = dfSel['MHC']
dfSel['Patient'] = 1

importlib.reload(multimerPatientTools)


# ============================================================
# FIX 2: 降级版 feature generation——跳过 netMHCstabpan
# ============================================================
def mergeSourceDFwithNetMHCpan_no_stab(df, dfNet_mut, dfNet_wt):
    """
    原 mergeSourceDFwithNetMHCpan_stab() 去掉 stab merge。
    只合并 netMHCpan-4.1 mut + wt binding，保留所有 binding 列。
    不传 dfNet_stab，不调 netMHCstabpan。
    """
    colsMut = ['Allele', 'Peptide', 'Core', 'Of', 'Gp', 'Gl', 'Ip', 'Il',
               'Score_EL', '%Rank_EL', 'Score_BA', '%Rank_BA', 'Aff(nM)']
    colsWT  = ['Allele', 'Peptide', 'Score_EL', '%Rank_EL', 'Score_BA', '%Rank_BA', 'Aff(nM)']

    dfSel_mut_pred = df.merge(
        dfNet_mut[colsMut], left_on=['MHC', 'PeptMut'], right_on=['Allele', 'Peptide']
    )
    dfSel_mut_wt_pred = dfSel_mut_pred.merge(
        dfNet_wt[colsWT], left_on=['Allele', 'PeptNorm'], right_on=['Allele', 'Peptide'],
        suffixes=('_mut', '_wt')
    )
    try:
        dfSel_return = dfSel_mut_wt_pred.drop_duplicates(['PeptMut', 'HLA', 'Patient', 'Target'])
    except KeyError:
        dfSel_return = dfSel_mut_wt_pred.drop_duplicates(['PeptMut', 'HLA', 'Patient'])

    # 注入 Stability 列为 NaN（Predict 会 fillna(col.mean()) impute）
    dfSel_return = dfSel_return.copy()
    dfSel_return['%Rank_Stab'] = float('nan')
    print(f"[no_stab] mergeSourceDF done: {len(dfSel_return)} rows, Stability=NaN injected")
    return dfSel_return


def runFeatureGeneration_no_stab(df, predDir, dataSet="my_dat",
                                  utilsDir='ProgramDirectory',
                                  tmpDir='ProgramDirectory',
                                  plot=False, clean=False):
    """
    原 runFeatureGeneration_NetMHCpan_stab_prime_molecular() 降级版：
      - 跑 netMHCpan-4.1 (mut + wt)   ✅
      - 跳过 netMHCstabpan             ❌ → Stability=NaN
      - 跑 PRIME + MixMHCpred          ✅
      - 跑 kernelSim (SelfSim)          ✅
      - 跑理化特征                       ✅
    """
    predDir_net41   = os.path.join(predDir, 'netmhcpan41')
    predDir_prime   = os.path.join(predDir, 'PRIME')

    utilsDir_net41  = os.path.join(utilsDir, 'netMHCpan-4.1', 'netmhcpan')
    utilsDir_prime  = os.path.join(utilsDir, 'PRIME', 'PRIME')

    # 预建输出子目录
    for d in [os.path.join(predDir_net41, 'mut'),
              os.path.join(predDir_net41, 'wt'),
              predDir_prime]:
        os.makedirs(d, exist_ok=True)

    if clean:
        for d in [os.path.join(predDir_net41, 'mut'),
                  os.path.join(predDir_net41, 'wt'),
                  predDir_prime]:
            multimerPatientTools.clearDirectory(d)

    # --- netMHCpan-4.1 mut ---
    kwargs_net41 = {'p': True, 'BA': True}
    print("[no_stab] Running NetMHCpan-4.1 MUT...")
    evalDF_net41_mut = multimerPatientTools.predReadWriteNetMHCpan_41(
        df, predDir_net41, utilsDir_net41, dataSet=dataSet, WT=False, **kwargs_net41
    )

    # --- netMHCpan-4.1 wt ---
    print("[no_stab] Running NetMHCpan-4.1 WT...")
    evalDF_net41_wt = multimerPatientTools.predReadWriteNetMHCpan_41(
        df, predDir_net41, utilsDir_net41, dataSet=dataSet, WT=True, **kwargs_net41
    )

    # --- PRIME + MixMHCpred ---
    print("[no_stab] Running PRIME...")
    dfPrime = multimerPatientTools.predReadWritePRIME(
        df, predDir_prime, utilsDir_prime, dataSet=dataSet, tmpDir=False, utilsDir=utilsDir
    )

    # --- Merge binding (no stab) ---
    dfNet = mergeSourceDFwithNetMHCpan_no_stab(df, evalDF_net41_mut, evalDF_net41_wt)

    # --- Merge PRIME ---
    dfMerge = multimerPatientTools.mergePrepFeatures_noFlurry(
        dfNet, dfPrime, peptCol='PeptMut', plot=plot
    )

    # --- SelfSim (BLOSUM62 kernel) ---
    blosFile = "data/matrices/blosum62.qij"
    blosPath = os.path.join(homeDir, blosFile)
    dfMerge = kernelSim.kernelWrapper(blosPath, dfMerge)

    # --- 理化特征 ---
    physiochemical_properties.calculate_and_save_properties(
        dfMerge, 'PeptMut', 'mw', 'aro', 'inst', 'helix', 'cys_red', 'pI'
    )

    print(f"[no_stab] runFeatureGeneration_no_stab done: {len(dfMerge)} rows")
    return dfMerge


# ---------- 主调用（降级版）----------
dfMerge = runFeatureGeneration_no_stab(
    dfSel,
    predDir=PredictionDirectory,
    dataSet=dataset_name,
    utilsDir=ProgramDirectory,
    tmpDir=TemptDirectory,
    plot=False,
    clean=False
)

# make nice names（与原版 rename 映射完全一致）
dfMerge = dfMerge.rename(columns={
    'MHC': 'HLA_allele', 'PeptMut': 'Mut_peptide',
    'aro': 'Aro', 'inst': 'Inst', 'cys_red': 'CysRed',
    '%Rank_EL_mut': 'RankEL', '%Rank_EL_wt': 'RankEL_wt', '%Rank_BA_mut': 'RankBA',
    'Expression_Level': 'Expression', 'Self_Similarity': 'SelfSim', 'Score_PRIME': 'Prime',
    'helix': 'PropHydroAro', 'MeanHydroph_coreNoAnc': 'HydroCore', 'MeanHydroph': 'HydroAll',
    'Prop_Small': 'PropSmall', 'Prop_Aromatic': 'PropAro', 'Prop_Basic': 'PropBasic',
    'Prop_Acidic': 'PropAcidic', 'Agrotopicity': 'DAI', '%Rank_Stab': 'Stability'
})

cols_to_include = [
    'HLA_allele', 'Mut_peptide', 'PeptNorm', 'PeptLen',
    'Core', 'Of', 'Gp', 'Gl', 'Ip',
    'Il', 'RankEL', 'RankBA', 'RankEL_wt', 'Stability',
    'Prime', 'DAI', 'CoreNonAnchor', 'Loci', 'HydroAll', 'HydroCore',
    'PropSmall', 'PropAro', 'PropBasic', 'PropAcidic', 'SelfSim', 'mw',
    'Aro', 'Inst', 'PropHydroAro', 'CysRed', 'pI'
]
# 确保 Stability 列存在（rename 已把 %Rank_Stab -> Stability）
if 'Stability' not in dfMerge.columns:
    dfMerge['Stability'] = float('nan')
dfMerge = dfMerge[cols_to_include]

df = df.rename(columns={'MHC': 'HLA_allele', 'PeptMut': 'Mut_peptide'})

dfMerge_with_input = df.merge(dfMerge, on=['HLA_allele', 'Mut_peptide', 'PeptNorm'], how='left')

# correct NA values when Norm peptide is NA
dfMerge_with_input['RankEL_wt'] = dfMerge_with_input.apply(
    lambda row: pd.NA if pd.isna(row['Norm_peptide']) else row['RankEL_wt'], axis=1
)
dfMerge_with_input['DAI'] = dfMerge_with_input.apply(
    lambda row: pd.NA if pd.isna(row['Norm_peptide']) else row['DAI'], axis=1
)

# 诊断输出：确认 RankEL 非 NaN 行数
rankEL_ok = dfMerge_with_input['RankEL'].notna().sum()
total_rows = len(dfMerge_with_input)
print(f"[QC] 总行数: {total_rows}, RankEL 非NaN: {rankEL_ok}, Stability列: NaN(预期)")

print(len(dfMerge_with_input))
print(dfMerge_with_input.columns)

dfMerge_with_input.to_csv(os.path.join('.', output_file), sep='\t', index=False)
print(f"[feature_calc_local v2] Done -> {output_file}")
