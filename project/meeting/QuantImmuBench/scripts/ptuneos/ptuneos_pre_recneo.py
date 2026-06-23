# -*- coding: utf-8 -*-
"""
ptuneos_pre_recneo.py  (Python 2.7, 容器内跑)
服务项目: quantimmu-bench  lever: pTuneos Pre&RecNeo benchmark

批处理版 InVivoModelAndScore，只算 model_pro，跳过 immuno_effect_score
（immuno_effect_score 块需 variant_allele_frequency/cellular_prevalence/tpm/
combined_prediction_score，纯 ELISpot 肽输入无此列，故截断于 model_pro）。

用法:
  python ptuneos_pre_recneo.py \
      --input  /work/ptuneos_input_unique.tsv \
      --output /work/ptuneos_output.tsv \
      --models /root/pTuneos/train_model \
      --blastdb /work/blastdb/peptide \
      --nproc  4

输入 TSV 必须含列: MT_pep, WT_pep, HLA_type
输出 TSV: 原列 + Hydrophobicity_score / Recognition_score /
          Self_sequence_similarity / MT_Binding_EL / WT_Binding_EL /
          model_pro / hydro_defaulted
"""

from __future__ import print_function
import os
import sys
import argparse
import subprocess
import tempfile
import multiprocessing
import math
from math import log, exp

import pandas as pd
import numpy as np
from Bio import pairwise2
from Bio.SubsMat import MatrixInfo as matlist
from sklearn.externals import joblib


# -------------------------------------------------------------------------
# constants (直接从 VCFprocessor_patched.py 抄，保持一致)
# -------------------------------------------------------------------------
a = 26
k = 4.86936

# -------------------------------------------------------------------------
# helpers (逐字复刻 VCFprocessor_patched.py L220-267)
# -------------------------------------------------------------------------

def hydro_vector(pep):
    hydro_score = {
        "A": 1.8, "C": 2.5, "D": -3.5, "E": -3.5, "F": 2.8,
        "G": -0.4, "H": -3.2, "I": 4.5, "K": -3.9, "L": 3.8,
        "M": 1.9, "N": -3.5, "P": -1.6, "Q": -3.5, "R": -4.5,
        "S": -0.8, "T": -0.7, "V": 4.2, "W": -0.9, "Y": -1.3
    }
    hydrophobicity_vector = []
    pep_list = list(pep)
    for aa in pep_list:
        hydrophobicity_vector.append(hydro_score[aa.upper()])
    return hydrophobicity_vector


_STD_AA = 'ACDEFGHIKLMNPQRSTVWY'

def aligner(seq1, seq2):
    matrix = matlist.blosum62
    gap_open = -11
    gap_extend = -1
    # 防御：BLOSUM62 只含 20 标准氨基酸；blastp 同源肽可能带 gap '-' 或非标准残基(X/B/Z/*)
    # → 剔除非标准字符避免 KeyError(('-','D'))。干净肽(MT/WT/iedb)不受影响，r=1.0 验证不破。
    s1 = ''.join(c for c in seq1.upper() if c in _STD_AA)
    s2 = ''.join(c for c in seq2.upper() if c in _STD_AA)
    if not s1 or not s2:
        return []
    aln = pairwise2.align.localds(s1, s2, matrix, gap_open, gap_extend)
    return aln


def calculate_R(neo_seq, iedb_seq):
    """严格复刻 VCFprocessor_patched.py L241-259"""
    align_score = []
    for seq in iedb_seq:
        aln_score = aligner(neo_seq, seq)
        if aln_score != []:
            localds_core = max([line[2] for line in aln_score])
            align_score.append(localds_core)
    bindingEnergies = map(lambda x: -k * (a - x), align_score)
    lZk = logSum(list(bindingEnergies) + [0])
    lGb = logSum(list(bindingEnergies))
    R = exp(lGb - lZk)
    return R


def logSum(v):
    ma = max(v)
    return log(sum(map(lambda x: exp(x - ma), v))) + ma


def cal_similarity_per(mut_seq, normal_seq):
    """严格复刻 VCFprocessor_patched.py L263-267"""
    aln = aligner(mut_seq, normal_seq)
    if not aln:
        return 0.0
    score_pair = aln[0][2]
    aln_self = aligner(mut_seq, mut_seq)
    if not aln_self:
        return 0.0
    score_self = aln_self[0][2]
    if score_self == 0:
        return 0.0
    return score_pair / score_self


def get_iedb_seq(iedb_file):
    iedb_seq = []
    for line in open(iedb_file):
        if line.startswith(">"):
            continue
        iedb_seq.append(line.strip())
    return iedb_seq


# -------------------------------------------------------------------------
# batch netMHCpan EL
# 严格复刻 get_EL_info 的列解析：
#   行以 4 空格开头 → strip → split → filter '' → [12] = EL %Rank
# -------------------------------------------------------------------------

def parse_netmhcpan_output(out_file):
    """
    解析单个 netMHCpan -p 输出文件，返回 {peptide_str: EL_rank_str}。
    列解析严格复刻 get_EL_info/get_homolog_info：
      line.startswith('    ') → record.split(' ') → filter '' → [12]
    netMHCpan-4.0 列序: Pos[0] HLA[1] Peptide[2] Core[3] ... Score[11] %Rank[12] BindLevel[13]
    其中 ml_record[2] = Peptide 序列（第3列，index 2）
         ml_record[12] = EL %Rank（第13列，index 12）
    """
    result = {}
    for line in open(out_file):
        if not line.startswith('    '):
            continue
        record = line.strip().split(' ')
        ml_record = [i for i in record if i != '']
        if len(ml_record) <= 12:
            continue
        pep = ml_record[2]
        el_rank = ml_record[12]
        result[pep] = el_rank
    return result


def run_netmhcpan_batch(peptides_by_hla_len, tmp_dir, netmhcpan_bin):
    """
    peptides_by_hla_len: dict  {(hla_stripped, pep_len): [pep1, pep2, ...]}
    返回 dict {(pep, hla_stripped): EL_rank_str}
    """
    el_dict = {}
    groups = sorted(peptides_by_hla_len.keys())
    total = len(groups)
    for gi, (hla_stripped, pep_len) in enumerate(groups):
        peps = list(set(peptides_by_hla_len[(hla_stripped, pep_len)]))
        if not peps:
            continue
        pep_file = os.path.join(tmp_dir, 'mhc_{}_{}.pep'.format(
            hla_stripped.replace(':', '_'), pep_len))
        out_file = os.path.join(tmp_dir, 'mhc_{}_{}.out'.format(
            hla_stripped.replace(':', '_'), pep_len))
        with open(pep_file, 'w') as f:
            for p in peps:
                f.write(p + '\n')
        cmd = '{} -p {} -a {} > {}'.format(
            netmhcpan_bin, pep_file, hla_stripped, out_file)
        ret = subprocess.call(cmd, shell=True, executable='/bin/bash')
        if ret != 0:
            print("[WARNING] netMHCpan returned {} for hla={} len={}".format(
                ret, hla_stripped, pep_len), file=sys.stderr)
        if os.path.exists(out_file):
            parsed = parse_netmhcpan_output(out_file)
            for pep_str, el in parsed.items():
                el_dict[(pep_str, hla_stripped)] = el
        else:
            print("[WARNING] netMHCpan output missing: {}".format(out_file),
                  file=sys.stderr)
        if (gi + 1) % 10 == 0 or (gi + 1) == total:
            print("[netMHCpan] {}/{} groups done".format(gi + 1, total))
    return el_dict


# -------------------------------------------------------------------------
# batch blastp homolog
# 严格复刻 get_homolog_info L282-289：
#   Sbjct 行 → split → filter '' → [2] → len==pep_len → break; else 'AAAAAAAAA'
# -------------------------------------------------------------------------

def run_blastp_batch(unique_mt_peps, tmp_dir, blast_db):
    """
    unique_mt_peps: list of unique MT peptide strings
    返回 dict {MT_pep: homolog_pep_str}
    """
    query_file = os.path.join(tmp_dir, 'blast_query.fasta')
    out_file = os.path.join(tmp_dir, 'blast_out.txt')

    with open(query_file, 'w') as f:
        for idx, pep in enumerate(unique_mt_peps):
            f.write('>{}\n{}\n'.format(idx, pep))

    cmd = ('blastp -query {} -db {} -out {} '
           '-evalue 200000 -comp_based_stats 0').format(
        query_file, blast_db, out_file)
    print("[blastp] Running batch query ({} seqs)...".format(len(unique_mt_peps)))
    ret = subprocess.call(cmd, shell=True, executable='/bin/bash')
    if ret != 0:
        print("[WARNING] blastp returned {}".format(ret), file=sys.stderr)

    # 解析：按 Query 块分割，每块找第一个同长 Sbjct 肽
    # 复刻 get_homolog_info L282-289：
    #   human_pep_record=line.strip().split(' ')
    #   human_pep = [i for i in human_pep_record if i!=''][2]
    #   if len(human_pep)==pep_len: break; else continue
    homolog_dict = {}
    if not os.path.exists(out_file):
        print("[WARNING] blastp output missing, all homologs default to AAAAAAAAA",
              file=sys.stderr)
        for pep in unique_mt_peps:
            homolog_dict[pep] = 'AAAAAAAAA'
        return homolog_dict

    current_query_idx = None
    current_pep = None
    found = False

    for line in open(out_file):
        if line.startswith('Query='):
            # 上一个 query 收尾
            if current_pep is not None and current_pep not in homolog_dict:
                homolog_dict[current_pep] = 'AAAAAAAAA'
            # 解析新 query idx
            parts = line.strip().split()
            try:
                current_query_idx = int(parts[1])
                current_pep = unique_mt_peps[current_query_idx]
            except (IndexError, ValueError):
                current_pep = None
            found = False

        elif line.startswith('Sbjct') and current_pep is not None and not found:
            human_pep_record = line.strip().split(' ')
            human_pep = [i for i in human_pep_record if i != ''][2]
            pep_len = len(current_pep)
            # 要求同长 + 仅标准 20 氨基酸(拒 gapped/非标准 hit，否则下游 aligner KeyError)
            if len(human_pep) == pep_len and all(c in _STD_AA for c in human_pep.upper()):
                homolog_dict[current_pep] = human_pep
                found = True

    # 最后一个 query 收尾
    if current_pep is not None and current_pep not in homolog_dict:
        homolog_dict[current_pep] = 'AAAAAAAAA'

    # 兜底：未出现在 blast 输出的（e.g. no hits）
    for pep in unique_mt_peps:
        if pep not in homolog_dict:
            homolog_dict[pep] = 'AAAAAAAAA'

    print("[blastp] Batch done. {}/{} peps got non-default homolog".format(
        sum(1 for v in homolog_dict.values() if v != 'AAAAAAAAA'),
        len(unique_mt_peps)))
    return homolog_dict


# -------------------------------------------------------------------------
# multiprocessing worker for calculate_R
# -------------------------------------------------------------------------

def _calc_R_worker(args):
    mt_pep, iedb_seq = args
    try:
        R = calculate_R(mt_pep, iedb_seq)
        return mt_pep, R
    except Exception as e:
        print("[WARNING] calculate_R failed for {}: {}".format(mt_pep, e),
              file=sys.stderr)
        return mt_pep, float('nan')


def run_recognition_parallel(unique_mt_peps, iedb_seq, nproc):
    """
    Recognition score 是最重部分，并行跑。
    返回 dict {MT_pep: R_float}
    """
    print("[Recognition] Computing R for {} unique MT peps with {} procs...".format(
        len(unique_mt_peps), nproc))
    pool = multiprocessing.Pool(processes=nproc)
    args_list = [(pep, iedb_seq) for pep in unique_mt_peps]
    results = pool.map(_calc_R_worker, args_list)
    pool.close()
    pool.join()
    r_dict = {}
    for pep, R in results:
        r_dict[pep] = R
    nans = sum(1 for v in r_dict.values() if math.isnan(v))
    print("[Recognition] Done. {} NaN".format(nans))
    return r_dict


# -------------------------------------------------------------------------
# main
# -------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='pTuneos Pre&RecNeo batch scorer (Python 2.7, container)')
    parser.add_argument('--input', required=True,
                        help='Input TSV (MT_pep, WT_pep, HLA_type)')
    parser.add_argument('--output', required=True,
                        help='Output TSV path')
    parser.add_argument('--models', default='/root/pTuneos/train_model',
                        help='Directory with RF_train_model.m and cf_hy_*.m')
    parser.add_argument('--blastdb', default='/work/blastdb/peptide',
                        help='Blast DB path (without .pin/.phr/.psq suffix)')
    parser.add_argument('--nproc', type=int, default=4,
                        help='Parallel processes for calculate_R')
    args = parser.parse_args()

    # ---- 0. netMHCpan PATH check ----
    netmhcpan_bin = 'netMHCpan'  # assumed in PATH via export PATH=...
    os.environ['PATH'] = '/root/software/netMHCpan-4.0:' + os.environ.get('PATH', '')

    # ---- 1. load input ----
    print("[main] Loading input: {}".format(args.input))
    df = pd.read_csv(args.input, sep='\t')
    print("[main] Input shape: {}".format(df.shape))
    for col in ['MT_pep', 'WT_pep', 'HLA_type']:
        if col not in df.columns:
            raise ValueError("Input TSV missing column: {}".format(col))

    df = df.reset_index(drop=True)
    n = len(df)

    # ---- 2. load models ----
    models_dir = args.models
    print("[main] Loading models from: {}".format(models_dir))
    cf_hy_9  = joblib.load(os.path.join(models_dir, 'cf_hy_9_model.m'))
    cf_hy_10 = joblib.load(os.path.join(models_dir, 'cf_hy_10_model.m'))
    cf_hy_11 = joblib.load(os.path.join(models_dir, 'cf_hy_11_model.m'))
    RF_model  = joblib.load(os.path.join(models_dir, 'RF_train_model.m'))
    iedb_file = os.path.join(models_dir, 'iedb.fasta')
    print("[main] Loading IEDB sequences: {}".format(iedb_file))
    iedb_seq = get_iedb_seq(iedb_file)
    print("[main] IEDB seqs loaded: {}".format(len(iedb_seq)))

    # ---- 3. tmp dir ----
    tmp_dir = tempfile.mkdtemp(prefix='ptuneos_run_')
    print("[main] Tmp dir: {}".format(tmp_dir))

    # ---- 4. batch netMHCpan EL ----
    # 收集唯一 (pep, hla_stripped) 对，按 (hla_stripped, pep_len) 分组
    print("[main] Building netMHCpan batch groups...")
    peptides_by_hla_len = {}
    for i in range(n):
        mt_pep = str(df.loc[i, 'MT_pep'])
        wt_pep = str(df.loc[i, 'WT_pep'])
        hla_stripped = str(df.loc[i, 'HLA_type']).replace('*', '')
        for pep in [mt_pep, wt_pep]:
            key = (hla_stripped, len(pep))
            if key not in peptides_by_hla_len:
                peptides_by_hla_len[key] = []
            peptides_by_hla_len[key].append(pep)

    print("[main] Running batch netMHCpan ({} hla/len groups)...".format(
        len(peptides_by_hla_len)))
    el_dict = run_netmhcpan_batch(peptides_by_hla_len, tmp_dir, netmhcpan_bin)
    print("[main] EL dict size: {}".format(len(el_dict)))

    # ---- 5. batch blastp homolog ----
    unique_mt_peps = list(set(str(p) for p in df['MT_pep']))
    print("[main] Running batch blastp ({} unique MT peps)...".format(len(unique_mt_peps)))
    homolog_dict = run_blastp_batch(unique_mt_peps, tmp_dir, args.blastdb)

    # ---- 6. Recognition score (parallel) ----
    r_dict = run_recognition_parallel(unique_mt_peps, iedb_seq, args.nproc)

    # ---- 7. per-row feature assembly ----
    print("[main] Assembling features per row...")
    hydro_scores  = []
    recog_scores  = []
    mt_el_list    = []
    wt_el_list    = []
    sss_list      = []
    hydro_def_list = []

    def safe_el(pep, hla_stripped):
        """查 el_dict，缺失返回 None 并 warn"""
        val = el_dict.get((pep, hla_stripped), None)
        if val is None:
            print("[WARNING] EL not found for pep={} hla={}".format(
                pep, hla_stripped), file=sys.stderr)
        return val

    n_failed = 0
    for i in range(n):
        mt_pep = str(df.loc[i, 'MT_pep'])
        wt_pep = str(df.loc[i, 'WT_pep'])
        hla_stripped = str(df.loc[i, 'HLA_type']).replace('*', '')
        pep_len = len(mt_pep)
        # 先算 locals，最后统一 append（保证 6 个 list 永远等长；单行异常→该行置默认不崩整跑）
        try:
            # Hydrophobicity (复刻 L352-373)
            hydro_def = False
            if pep_len == 9:
                h = cf_hy_9.predict_proba(
                    np.array(hydro_vector(mt_pep)).reshape((1, 9)))[:, 1][0]
            elif pep_len == 10:
                h = cf_hy_10.predict_proba(
                    np.array(hydro_vector(mt_pep)).reshape((1, 10)))[:, 1][0]
            elif pep_len == 11:
                h = cf_hy_11.predict_proba(
                    np.array(hydro_vector(mt_pep)).reshape((1, 11)))[:, 1][0]
            else:
                h = 0.5
                hydro_def = True
            # Recognition
            R = r_dict.get(mt_pep, float('nan'))
            # EL
            mt_el = safe_el(mt_pep, hla_stripped)
            wt_el = safe_el(wt_pep, hla_stripped)
            # Self_sequence_similarity (复刻 L377-389)
            homolog_pep = homolog_dict.get(mt_pep, 'AAAAAAAAA')
            paired_s   = cal_similarity_per(mt_pep, wt_pep)
            homolog_s  = cal_similarity_per(mt_pep, homolog_pep)
            sss = paired_s if paired_s >= homolog_s else homolog_s
        except Exception as e:
            n_failed += 1
            print("[feature] row {} ({}/{}/{}) FAILED: {} -> NaN".format(
                i, mt_pep, wt_pep, hla_stripped, repr(e)), file=sys.stderr)
            h = float('nan'); hydro_def = False; R = float('nan')
            mt_el = None; wt_el = None; sss = float('nan')

        hydro_scores.append(h)
        hydro_def_list.append(hydro_def)
        recog_scores.append(R)
        mt_el_list.append(mt_el)
        wt_el_list.append(wt_el)
        sss_list.append(sss)

        if (i + 1) % 50 == 0 or (i + 1) == n:
            print("[feature] {}/{} rows assembled".format(i + 1, n))

    # ---- 8. RF predict_proba = model_pro (复刻 L397-401) ----
    print("[main] Running RF model...")
    df['Hydrophobicity_score']    = hydro_scores
    df['Recognition_score']       = recog_scores
    df['Self_sequence_similarity'] = sss_list
    df['MT_Binding_EL']           = mt_el_list
    df['WT_Binding_EL']           = wt_el_list
    df['hydro_defaulted']         = hydro_def_list

    # 构造特征矩阵，按源码列顺序
    feat_cols = ['Hydrophobicity_score', 'Recognition_score',
                 'Self_sequence_similarity', 'MT_Binding_EL', 'WT_Binding_EL']

    # EL 可能是 None（缺失），转 float；整行若有 None 则 model_pro = NaN
    df_feat = df[feat_cols].copy()
    for c in ['MT_Binding_EL', 'WT_Binding_EL']:
        df_feat[c] = pd.to_numeric(df_feat[c], errors='coerce')

    valid_mask = df_feat.notnull().all(axis=1)
    model_pro = pd.Series([float('nan')] * n)
    if valid_mask.any():
        feat_vals = df_feat[valid_mask].values.astype(float)
        preds = RF_model.predict_proba(feat_vals)[:, 1]
        model_pro[valid_mask] = preds
    n_nan = (~valid_mask).sum()
    if n_nan > 0:
        print("[WARNING] {} rows have NaN features, model_pro set to NaN".format(
            n_nan), file=sys.stderr)

    df['model_pro'] = model_pro.values

    # ---- 9. output ----
    print("[main] Writing output: {}".format(args.output))
    out_dir = os.path.dirname(args.output)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)

    df.to_csv(args.output, sep='\t', index=False)
    print("[main] Done. {} rows written.".format(n))
    nan_rows = df['model_pro'].isnull().sum()
    if nan_rows:
        print("[main] WARNING: {} rows have NaN model_pro (see stderr for details)".format(
            nan_rows))
    else:
        print("[main] All rows have valid model_pro.")


if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
