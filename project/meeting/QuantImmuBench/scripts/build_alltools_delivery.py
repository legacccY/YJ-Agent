#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_alltools_delivery.py — QuantImmuBench 全 16 工具交付包
=================================================================
服务: quantimmu-bench / lever = 数据表更新（IMPROVE 跑通后全量重算）

给袁老师交付：16 个免疫原性预测工具，每个一张 xlsx，放
  5tools_delivery/data_tables/<Tool>.xlsx
每张 xlsx：
  Sheet1 = backbone（17 列）+ 该工具原生输出列（行对行）
  Sheet2 = 「列说明」工具主输出列含义 + 方向（统一越高越免疫原）+ 覆盖率 + caveat

数据源（关键）：分数列全部取自 IMPROVE 跑通后重算的
  scripts/out/merged_all_tools_16tools.xlsx
该表为子肽级（34247 行，bb_idx 主键），含 P101/P102 修正后的全量结果。

────────────────────────────────────────────────────────────────
backbone 选型 = Plan A（直接切 merged_16tools 的 17 列 backbone 区，行对行）
为什么不用 Plan B（join 对齐袁老师样例 Sample_merged_prime_results.xlsx 前 15 列）：
  1. merged_16tools 本身就是权威源——backbone 与工具列已行对行对齐（同一行同一 bb_idx），
     直接切片零 join、零 NaN 传播、零行扩张风险，最稳可靠。
  2. 样例的 15 列含 Treatment / Vaccine_Peptide / WT_Peptide_Seq / TPM_PurifiedTumorRNA
     等辅助字段，这些**不是工具输出**、也**不在 merged_16tools 里**；强行 join 回去要再
     按自然键拼一次，反而引入 NaN/重复，得不偿失。
  3. merged_16tools 的 17 列 backbone 信息更全（多 bb_idx 主键可溯源、Dataset 标 DS1/DS2、
     MT/WT_FullPeptide、Ref_UniProt_ID、Peptide_Position），交付价值更高。
旧脚本 build_5tools_delivery.py 用的是 Plan B（从已归档 merged_<tool>.xlsx 按
(Subpeptide,HLA) join 到样例 15 列 backbone）——那批源已归档，本脚本不再依赖。

跑法（主线跑，本脚本不自跑）：
  python scripts/build_alltools_delivery.py
依赖: pandas, openpyxl
Windows 规范: 纯 pandas/openpyxl，无多进程，pathlib 路径。
"""

import sys
from pathlib import Path

import pandas as pd

# UTF-8 stdout（Windows 必要）
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HERE = Path(__file__).resolve().parent          # scripts/
ROOT = HERE.parent                               # project/meeting/QuantImmuBench/

SRC      = HERE / 'out' / 'merged_all_tools_16tools.xlsx'
OUT_DIR  = ROOT / '5tools_delivery' / 'data_tables'

# ── backbone 17 列（与 merged_16tools / remerge_fixed.py BACKBONE_COLS 完全一致）──
BACKBONE_COLS = [
    'bb_idx', 'Dataset', 'Patient_ID', 'Peptide_ID', 'Gene_Name', 'Mutation',
    'MT_FullPeptide', 'WT_FullPeptide', 'Peptide_Length', 'Elispot',
    'Window_Size', 'Position', 'MT_Subpeptide', 'WT_Subpeptide', 'HLA_Allele',
    'Ref_UniProt_ID', 'Peptide_Position',
]

# backbone 列说明（每张表 Sheet2 都附，便于老师独立看懂）
BACKBONE_DESC = {
    'bb_idx': '子肽级唯一主键（行号，溯源用，跨工具表可对齐同一肽×HLA 记录）',
    'Dataset': '来源数据集（DS1 / DS2）',
    'Patient_ID': '病人编号（含修正后的 P101/P102）',
    'Peptide_ID': '肽编号',
    'Gene_Name': '突变所在基因',
    'Mutation': '氨基酸突变（如 V600E）',
    'MT_FullPeptide': '突变全长肽（vaccine peptide）',
    'WT_FullPeptide': '对应野生全长肽',
    'Peptide_Length': '滑窗子肽长度（mer）',
    'Elispot': 'ELISpot 实验标签（免疫原性金标准，正=有反应）',
    'Window_Size': '滑窗窗口大小',
    'Position': '子肽在全长肽内的起始位置',
    'MT_Subpeptide': '突变子肽序列（绝大多数工具的实际打分单位）',
    'WT_Subpeptide': '对应野生子肽序列',
    'HLA_Allele': 'HLA 等位基因（标准格式 HLA-A*24:02；P101/P102 已修正）',
    'Ref_UniProt_ID': '参考蛋白 UniProt ID',
    'Peptide_Position': '肽在参考蛋白内的位置',
}

# ── 16 工具定义 ───────────────────────────────────────────────────────────────
# 每项: 显示名 -> dict(file, cols, primary, desc, caveat)
#   cols   = 该工具在 merged_16tools 内的原生输出列（顺序即交付表内顺序）
#   primary= 主输出列（算覆盖率用，统一"越高越免疫原"方向的总分）
#   desc   = {列名(或合并键如 'MT_NOAH/WT_NOAH'): 含义+方向}
#   caveat = 该工具的限制/注意（覆盖率、肽长/HLA 限制、proxy、许可等）
TOOLS = {
    'DeepImmuno': dict(
        file='DeepImmuno',
        cols=['MT_DeepImmuno', 'WT_DeepImmuno'],
        primary='MT_DeepImmuno',
        desc={
            'MT_DeepImmuno': '突变肽免疫原性概率 0-1（CNN，主输出，越高越免疫原）',
            'WT_DeepImmuno': '对应野生肽免疫原性概率 0-1',
        },
        caveat='仅支持 9-10mer；其它肽长无分（空白）。方向：越高越免疫原。',
    ),
    'PredIG': dict(
        file='PredIG',
        cols=['MT_PredIG', 'WT_PredIG',
              'MT_NOAH', 'WT_NOAH', 'MT_NetCleave', 'WT_NetCleave',
              'MT_Stab_peptide', 'WT_Stab_peptide', 'MT_TCR_contact', 'WT_TCR_contact'],
        primary='MT_PredIG',
        desc={
            'MT_PredIG': 'PredIG-Neo 突变肽免疫原性总分（主输出，越高越免疫原）',
            'WT_PredIG': '对应野生肽免疫原性总分',
            'MT_NOAH/WT_NOAH': 'NOAH pMHC 结合预测分量（子特征）',
            'MT_NetCleave/WT_NetCleave': 'NetCleave 蛋白酶切割位点分量（子特征）',
            'MT_Stab_peptide/WT_Stab_peptide': 'pMHC 稳定性分量（子特征）',
            'MT_TCR_contact/WT_TCR_contact': 'TCR 接触面特征分量（子特征）',
        },
        caveat='PredIG 是集成模型，主分用 MT_PredIG；NOAH/NetCleave/Stab/TCR 为构成总分的'
               '子特征列。方向：MT_PredIG 越高越免疫原；子特征为内部分量，不单独定方向。'
               '不在 PredIG 支持肽长/HLA 范围的肽无分（空白）。',
    ),
    'pTuneos': dict(
        file='pTuneos',
        cols=['MT_pTuneos', 'pTuneos_hydro_defaulted'],
        primary='MT_pTuneos',
        desc={
            'MT_pTuneos': 'Pre&RecNeo 免疫原性总概率 model_pro 0-1（主输出，越高越免疫原）',
            'pTuneos_hydro_defaulted': '疏水分是否用了默认填补（True=该肽缺值兜底，仅元信息非分数）',
        },
        caveat='只对突变肽打分（MT-only）。pTuneos_hydro_defaulted 是质控标记不是分数。'
               '未跑出的肽×HLA（肽长/HLA 限制）空白。方向：越高越免疫原。',
    ),
    'IMPROVE': dict(
        file='IMPROVE',
        cols=['MT_IMPROVE_mean_prediction_rf'],
        primary='MT_IMPROVE_mean_prediction_rf',
        desc={
            'MT_IMPROVE_mean_prediction_rf': 'IMPROVE 随机森林集成最终免疫原性分（主输出，越高越免疫原）',
        },
        caveat='突变肽 RF 集成，只对 MT 打分（MT-only）。本部署中 Expression（表达量）特征为'
               '降级值（缺 RNA-seq TPM 真值），故 IMPROVE 分含此局限。同 (MT,WT,HLA) 多病人行'
               '已取均值。不在 netMHC 支持肽长/HLA 内的肽空白。方向：越高越免疫原。',
    ),
    'NeoTImmuML': dict(
        file='NeoTImmuML',
        cols=['MT_NeoTImmuML', 'WT_NeoTImmuML'],
        primary='MT_NeoTImmuML',
        desc={
            'MT_NeoTImmuML': '突变肽免疫原性总分（RF+LGB+XGB 集成，主输出，越高越免疫原）',
            'WT_NeoTImmuML': '对应野生肽免疫原性总分',
        },
        caveat='HLA-agnostic：仅用肽理化特征，不分等位基因（同肽在不同 HLA 下同分）。'
               '自训复刻版（官方权重不可得，PPT 标★）。该肽长不在支持范围则空白。'
               '方向：越高越免疫原。',
    ),
    'PRIME': dict(
        file='PRIME',
        cols=['MT_PRIME', 'WT_PRIME'],
        primary='MT_PRIME',
        desc={
            'MT_PRIME': 'PRIME 突变肽免疫原性分 Score_bestAllele（主输出，越高越免疫原）',
            'WT_PRIME': '对应野生肽免疫原性分',
        },
        caveat='per-allele 运行，按 (子肽, HLA) 回贴。不在 PRIME 支持肽长/HLA 范围的肽空白。'
               '方向：越高越免疫原。',
    ),
    'ImmuneApp': dict(
        file='ImmuneApp',
        cols=['MT_ImmuneApp', 'WT_ImmuneApp'],
        primary='MT_ImmuneApp',
        desc={
            'MT_ImmuneApp': '突变肽免疫原性分 Immunogenicity_score（主输出，越高越免疫原）',
            'WT_ImmuneApp': '对应野生肽免疫原性分',
        },
        caveat='per-HLA 运行，按 (子肽, HLA) 回贴。不支持的肽长/HLA 空白。方向：越高越免疫原。',
    ),
    'deepHLApan': dict(
        file='deepHLApan',
        cols=['MT_deepHLApan', 'WT_deepHLApan'],
        primary='MT_deepHLApan',
        desc={
            'MT_deepHLApan': '突变肽免疫原性分 immunogenic score 0-1（主输出，越高越免疫原）',
            'WT_deepHLApan': '对应野生肽免疫原性分',
        },
        caveat='本次已修复 merge NaN 传播 bug（同一 (子肽,HLA) 的多 bb_idx 现全部回贴）。'
               '不支持的肽长/HLA 空白。方向：越高越免疫原。',
    ),
    'HLAthena': dict(
        file='HLAthena',
        cols=['MT_HLAthena', 'WT_HLAthena'],
        primary='MT_HLAthena',
        desc={
            'MT_HLAthena': '突变肽 MSi presentation score（主输出，越高越可能被呈递/免疫原）',
            'WT_HLAthena': '对应野生肽 MSi presentation score',
        },
        caveat='HLAthena 原生预测的是 MHC-I 抗原呈递（MSi），此处作免疫原性 proxy 使用（非直接'
               '免疫原性模型）。不支持的肽长/HLA 空白。方向：越高越（呈递→）免疫原。',
    ),
    'BigMHC': dict(
        file='BigMHC',
        cols=['MT_BigMHC', 'WT_BigMHC'],
        primary='MT_BigMHC',
        desc={
            'MT_BigMHC': '突变肽免疫原性分 BigMHC_IM（主输出，越高越免疫原）',
            'WT_BigMHC': '对应野生肽免疫原性分',
        },
        caveat='不支持的肽长/HLA 空白。方向：越高越免疫原。',
    ),
    'CNNeo': dict(
        file='CNNeo',
        cols=['MT_CNNeo', 'WT_CNNeo'],
        primary='MT_CNNeo',
        desc={
            'MT_CNNeo': '突变肽免疫原性分（CNN，主输出，越高越免疫原）',
            'WT_CNNeo': '对应野生肽免疫原性分',
        },
        caveat='不支持的肽长/HLA 空白。方向：越高越免疫原。',
    ),
    'IEDB_Calis': dict(
        file='IEDB_Calis',
        cols=['MT_IEDB_Calis', 'WT_IEDB_Calis'],
        primary='MT_IEDB_Calis',
        desc={
            'MT_IEDB_Calis': '突变肽 IEDB Calis 免疫原性分（主输出，越高越免疫原）',
            'WT_IEDB_Calis': '对应野生肽免疫原性分',
        },
        caveat='Calis et al. 序列免疫原性模型（IEDB immunogenicity）。'
               '不支持的肽长/HLA 空白。方向：越高越免疫原。',
    ),
    'MHCflurry': dict(
        file='MHCflurry',
        cols=['MT_MHCflurry_presentation', 'WT_MHCflurry_presentation',
              'MT_MHCflurry_affinity_neg', 'WT_MHCflurry_affinity_neg'],
        primary='MT_MHCflurry_presentation',
        desc={
            'MT_MHCflurry_presentation': '突变肽呈递分 presentation score 0-1（主输出，越高越可能被呈递）',
            'WT_MHCflurry_presentation': '对应野生肽呈递分',
            'MT_MHCflurry_affinity_neg/WT_..._affinity_neg':
                '结合亲和力（已取负，统一为越高越强结合；原始 affinity 越小越强已翻转）',
        },
        caveat='MHCflurry 输出两组：presentation（呈递概率）+ affinity（结合亲和力，本表用 _neg '
               '即取负后越高越强结合）。两者均为呈递/结合 proxy，非直接免疫原性。'
               '不支持的肽长/HLA 空白。方向：两列均越高越（强结合/呈递→）免疫原。',
    ),
    'Repitope': dict(
        file='Repitope',
        cols=['MT_Repitope', 'WT_Repitope'],
        primary='MT_Repitope',
        desc={
            'MT_Repitope': '突变肽免疫原性分（Repitope，主输出，越高越免疫原）',
            'WT_Repitope': '对应野生肽免疫原性分',
        },
        caveat='不支持的肽长/HLA 空白。方向：越高越免疫原。',
    ),
    'TSCAPE': dict(
        file='TSCAPE',
        cols=['MT_TSCAPE'],
        primary='MT_TSCAPE',
        desc={
            'MT_TSCAPE': 'T-SCAPE 突变肽免疫原性分（主输出，越高越免疫原）',
        },
        caveat='仅对突变肽打分（MT-only，无 WT 列）。不支持的肽长/HLA 空白。方向：越高越免疫原。',
    ),
    'netMHCpan-BA': dict(
        file='netMHCpan-BA',
        cols=['MT_netmhcpan_ba', 'WT_netmhcpan_ba'],
        primary='MT_netmhcpan_ba',
        desc={
            'MT_netmhcpan_ba': '突变肽 netMHCpan 结合亲和力分（主输出，作免疫原性 proxy）',
            'WT_netmhcpan_ba': '对应野生肽结合亲和力分',
        },
        caveat='netMHCpan-BA 预测的是 pMHC 结合亲和力（presentation 上游 proxy，非直接免疫原性）。'
               'DTU 许可受限工具（部署/分发受官方许可约束）。不支持的肽长/HLA 空白。'
               '方向：按本表数值约定越高越强结合→越可能免疫原（若交付方需原始 IC50/%Rank 口径请确认）。',
    ),
}


def main():
    print(f'[INFO] 数据源: {SRC}')
    print(f'[INFO] 输出  : {OUT_DIR}')
    if not SRC.exists():
        print(f'[ERR] 数据源不存在: {SRC}', file=sys.stderr)
        sys.exit(1)

    df = pd.read_excel(SRC, engine='openpyxl')
    df.columns = [c.strip() for c in df.columns]
    n_rows = len(df)
    print(f'[源] 读入 {n_rows} 行 × {len(df.columns)} 列')

    # backbone 列完整性检查
    miss_bb = [c for c in BACKBONE_COLS if c not in df.columns]
    if miss_bb:
        print(f'[ERR] 源表缺 backbone 列: {miss_bb}', file=sys.stderr)
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    n_done = 0
    for name, spec in TOOLS.items():
        cols = spec['cols']
        # 工具列完整性检查（缺列只警告不中止，方便定位 schema 漂移）
        miss = [c for c in cols if c not in df.columns]
        if miss:
            print(f'[WARN] [{name}] 源表缺工具列 {miss}，跳过这些列', file=sys.stderr)
        use_cols = [c for c in cols if c in df.columns]
        if not use_cols:
            print(f'[ERR] [{name}] 无任何可用工具列，跳过该工具', file=sys.stderr)
            continue

        # Plan A：直接切 backbone 17 列 + 工具列（行对行）
        sub = df[BACKBONE_COLS + use_cols].copy()

        # 覆盖率（按主输出列非空 / 总行数）
        primary = spec['primary'] if spec['primary'] in sub.columns else use_cols[0]
        n_cover = int(sub[primary].notna().sum())
        cover_pct = n_cover / n_rows * 100 if n_rows else 0.0

        out_path = OUT_DIR / f'{spec["file"]}.xlsx'
        with pd.ExcelWriter(out_path, engine='openpyxl') as xw:
            sub.to_excel(xw, sheet_name=name[:31], index=False)

            # Sheet2「列说明」
            rows = []
            rows.append(['== backbone 列（17，所有工具表通用） ==', ''])
            for k, v in BACKBONE_DESC.items():
                rows.append([k, v])
            rows.append(['', ''])
            rows.append([f'== {name} 工具输出列 ==', ''])
            for k, v in spec['desc'].items():
                rows.append([k, v])
            rows.append(['', ''])
            rows.append(['方向约定', '本交付包统一：分数越高 = 越可能免疫原（结合/呈递类工具为 proxy，见 caveat）'])
            rows.append(['覆盖率', f'{primary} 非空 {n_cover}/{n_rows} 行 = {cover_pct:.1f}%'
                                   '（覆盖率 = 工具适用面，非"跑没跑完"；空白多因肽长/HLA 不支持）'])
            rows.append(['caveat', spec['caveat']])
            rows.append(['数据源', 'scripts/out/merged_all_tools_16tools.xlsx（IMPROVE 跑通后全量重算，含 P101/P102 修正）'])
            desc_df = pd.DataFrame(rows, columns=['列名 / 项', '说明'])
            desc_df.to_excel(xw, sheet_name='列说明', index=False)

        print(f'[{name}] {n_rows} 行，{len(use_cols)} 工具列，覆盖率 {cover_pct:.1f}% -> {out_path.name}')
        n_done += 1

    print(f'\n[DONE] 生成 {n_done}/{len(TOOLS)} 张工具交付表 -> {OUT_DIR}')


if __name__ == '__main__':
    main()
