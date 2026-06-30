#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_trap_official.py
===============================================================================
服务：quantimmu-bench / 工具补跑舰队 / lever=工具补跑（TRAP 替代失效的 T-SCAPE）。

TRAP 官方批量推理（repo 无 CLI，仅 dash_app.py 网页版 + model.py 训练脚本）。
本脚本 **忠实复制** dash_app.py 的推理四函数（add_space_to_pep / preprocess_test_peptides
/ embed_test_peptides / predict_trap），算法零改，把网页交互剥成命令行批处理。
来源 commit 已 curl 实拉核对（2026-06-30）：
  https://raw.githubusercontent.com/ChloeHJ/TRAP/main/dash_app.py
  https://raw.githubusercontent.com/ChloeHJ/TRAP/main/model.py

★★★ 主线执行命令序列（我不跑，全部交主线串行）★★★
  # 1. clone 官方 repo 到 tools_local/TRAP（与 T-SCAPE 并列）
  cd D:/YJ-Agent/project/meeting/QuantImmuBench/tools_local
  git clone https://github.com/ChloeHJ/TRAP.git TRAP

  # 2. 建 conda env（官方 requirements，python>=3.9）
  cd TRAP
  conda create -n trap python=3.9 -y
  conda activate trap
  pip install -r requirements.txt
  # requirements pin：torch==1.12.1 tensorflow==2.9.1 transformers==4.24.0
  #                   keras==2.9.0 scikit-learn==1.0.2 numpy==1.21.6 pandas==1.3.5
  # 无 CUDA 强制，CPU 可跑（ProtT5 嵌入 + keras CNN）。

  # 3. ⚠️ TODO-WEIGHTS：训练好的模型权重 model/ 不在 repo，在 Google Drive
  #    https://drive.google.com/drive/folders/15A2P5xP2c-q48vVGPRB7h7uHEMycPYoX
  #    需下载并放到 tools_local/TRAP/ 下，得到目录：
  #      model/self_antigen_trap_model/            (SavedModel, --model self 必需)
  #      model/self_antigen_trap_softmax_model/    (Confidence 可选)
  #      model/self_antigen_trap_softmaxbucket_model* x10  (Confidence 可选)
  #      model/pathogenic_trap_model/              (--model pathogenic)
  #      data/cal_ood_data_selfantigen.csv         (Confidence 可选；repo data/ 无此文件)
  #      data/cal_ood_data_pathogenic.csv          (同上)
  #    本脚本只产 TRAP value（=我们要的 MT_TRAP），Confidence/OOD 为可选；
  #    若 softmax/bucket/cal_ood 缺，仍能出 TRAP value，Confidence 留空。

  # 4. ⚠️ ProtT5-XL-UniRef50 嵌入模型首次跑会从 HuggingFace 拉 Rostlab/prot_t5_xl_uniref50
  #    ≈2.8GB（非 R3 note 的"百MB"），需联网 + 磁盘空间。

  # 5. 烟测（最小 1-2 样本验算子，主线跑）：
  python scripts/hpc_official/run_trap_official.py \
      --trap-repo tools_local/TRAP \
      --input scripts/out_official/trap_inputs/trap_input.csv \
      --model self --smoke 2 \
      --out scripts/out_official/trap_inputs/trap_output_smoke.csv

  # 6. 全量推理：
  python scripts/hpc_official/run_trap_official.py \
      --trap-repo tools_local/TRAP \
      --input scripts/out_official/trap_inputs/trap_input.csv \
      --model self \
      --out scripts/out_official/trap_inputs/trap_output.csv

★ 模型选择（--model）★
  pathogenic = 病原体表位模型；self = 自身抗原模型（癌症 / 自身抗原）。
  README 明示「cancer, autoantigens 选 self-antigen 模型」→ 新抗原 benchmark 默认 --model self。
  ⚠️ TODO-MODEL：若 researcher 判定该用 pathogenic（如把新抗原视作"非己"），改 --model pathogenic 重跑。

★ 上游 bug 修正（已标注，非算法改动）★
  dash_app.embed_test_peptides 内 `embedding = model(input_ids=...)` 引用了未定义的全局
  `model`（应是传入的 ProtT5 encoder；model.py main() 中 model=encoder，dash 复制时漏改名）。
  本脚本把该参数命名为 encoder 并改 `encoder(input_ids=...)`，**仅修复 NameError 还原作者意图**，
  不动嵌入算法/超参。其余逻辑（ContactPosition=pep[2:-1]、hydrophobicity 算法、padding="pre"、
  T5 空格分词、TRAP 模型 forward）逐行照搬官方。

依赖：torch / tensorflow / keras / transformers / sklearn / numpy / pandas（在 trap env 内）。
Windows：utf-8 + pathlib。
"""

import argparse
import os
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

import numpy as np
import pandas as pd


# ===========================================================================
# 以下四函数逐行复制 dash_app.py（仅 embed 修 NameError，已注明）
# ===========================================================================

def add_space_to_pep(peptides):
    """[官方 dash_app.add_space_to_pep 逐行复制] ProtT5 需空格分隔 AA。"""
    peptide_space = []
    for ele in peptides:
        temp = [[]]
        for char in ele:
            temp.append([])
            temp[-1].append(char)
        peptide_space.append(' '.join(''.join(ele) for ele in temp))
    peptide_space = [re.sub(r"[UZOB]", "X", sequence.lstrip()) for sequence in peptide_space]
    return peptide_space


def preprocess_test_peptides(test_data):
    """[官方 dash_app.preprocess_test_peptides 逐行复制]
    ContactPosition = pep[2:-1]；Hydrophobicity = count(A,V,L,M,W)/len。"""
    cont_peptides = []
    hydrophobicity = []
    for pep in test_data.Peptide:
        cont_pep = pep[2:-1]
        cont_peptides.append(cont_pep)
        hyd_counts = pep.count('A') + pep.count('V') + pep.count('L') + pep.count('M') + pep.count('W')
        length = len(pep)
        hydrophobicity.append(hyd_counts / length)

    cont_peptides = pd.DataFrame(cont_peptides)
    cont_peptides.columns = ['ContactPosition']
    hydrophobicity = pd.DataFrame(hydrophobicity)
    hydrophobicity.columns = ['Hydrophobicity']
    test_data = pd.concat([test_data, cont_peptides, hydrophobicity], axis=1)
    return test_data


def embed_test_peptides(test_data, tokenizer, encoder):
    """[官方 dash_app.embed_test_peptides 复制 + 修 NameError]
    原文 `embedding = model(input_ids=...)` 中 model 未定义（作者从 model.py main() 复制时
    漏把 model 改成传入的 encoder）→ 这里用 encoder 参数还原意图，嵌入算法不变。"""
    from keras_preprocessing.sequence import pad_sequences

    test_peptides = test_data.ContactPosition.values
    input_peptides = add_space_to_pep(test_peptides)

    tokenized_texts = [tokenizer.tokenize(sent) for sent in input_peptides]
    input_ids = pad_sequences([tokenizer.convert_tokens_to_ids(txt) for txt in tokenized_texts],
                              padding="pre")

    # 官方此处构建 attention_masks 但未实际传入 encoder（且 append 在循环外），保持原样不传。
    embedding = encoder(input_ids=input_ids)[0]   # FIX: 原文为 model(...)，NameError
    embedding = np.asarray(embedding)
    return embedding


def predict_trap(embedding, test_data, trap, trap_softmax, trap_softmaxbucket, trap_ood):
    """[官方 dash_app.predict_trap 逐行复制] 返回含 TRAP / Confidence 的 df。
    Confidence 链（softmax / bucket / ood）为可选：缺则只出 TRAP（见 run()）。"""
    from keras.models import Model

    X_test = embedding
    X_test_mlp = test_data[['Hydrophobicity', 'nlog2Rank']]

    # trap（必需）
    y_pred = trap.predict([X_test, X_test_mlp])

    # on softmax
    y_pred_softmax = trap_softmax.predict([X_test, X_test_mlp])
    softmax = np.max(y_pred_softmax, axis=1)

    # ensemble on softmax
    bucket_softmax = []
    for i in range(10):
        random_model = trap_softmaxbucket[i]
        random_model_score = Model(random_model.input, random_model.get_layer('logits').output)
        X_random_test_logits = random_model_score.predict(x=[X_test, X_test_mlp])
        smax = np.max(X_random_test_logits, axis=1)
        bucket_softmax.append(smax)

    c_softmax = np.vstack((bucket_softmax)).T
    ensemble = np.mean(c_softmax, axis=1)

    # process ood output
    softmax_dt = pd.DataFrame(softmax)
    softmax_dt.columns = ['max']
    ensemble_dt = pd.DataFrame(ensemble)
    ensemble_dt.columns = ['ensemble_mean_maxprob']
    ood_test_data = pd.concat([softmax_dt, ensemble_dt], axis=1)

    # ood classifier
    X_test = ood_test_data
    y_pred_ood = trap_ood.predict(X_test)

    # process outputs
    trap_pred = pd.DataFrame(y_pred)
    trap_pred.columns = ['TRAP']
    ood_test_data.columns = ['MaxProb', 'Ensemble']

    ood_dt = pd.DataFrame(y_pred_ood)
    ood_dt.columns = ['Confidence']
    ood_dt['Confidence'] = np.where(ood_dt['Confidence'] == 1, 'High', 'Low')
    prediction_dt = pd.concat(
        [test_data[['Peptide', 'ContactPosition', 'nlog2Rank']], trap_pred, ood_test_data, ood_dt],
        axis=1)
    return prediction_dt


def predict_trap_value_only(embedding, test_data, trap):
    """仅算 TRAP value（=我们要的 MT_TRAP），不依赖 softmax/bucket/ood。
    TRAP value 部分逐行同官方 predict_trap 的 `trap.predict([X_test, X_test_mlp])`。"""
    X_test = embedding
    X_test_mlp = test_data[['Hydrophobicity', 'nlog2Rank']]
    y_pred = trap.predict([X_test, X_test_mlp])
    trap_pred = pd.DataFrame(np.asarray(y_pred).reshape(-1))
    trap_pred.columns = ['TRAP']
    out = pd.concat(
        [test_data[['Peptide', 'ContactPosition', 'nlog2Rank']].reset_index(drop=True),
         trap_pred.reset_index(drop=True)],
        axis=1)
    out['MaxProb'] = ''
    out['Ensemble'] = ''
    out['Confidence'] = ''
    return out


# ===========================================================================
# 模型加载 + 主流程
# ===========================================================================

MODEL_PREFIX = {
    'pathogenic': ('pathogenic_trap_model', 'pathogenic_trap_softmax_model',
                   'pathogenic_trap_softmaxbucket_model', 'cal_ood_data_pathogenic.csv'),
    'self':       ('self_antigen_trap_model', 'self_antigen_trap_softmax_model',
                   'self_antigen_trap_softmaxbucket_model', 'cal_ood_data_selfantigen.csv'),
}


def load_models(trap_repo: Path, which: str):
    """[逐行同官方 dash_app 顶层模型加载逻辑]
    返回 (trap, trap_softmax, trap_softmaxbucket(list), trap_ood)；缺的 Confidence 件 → None。"""
    import tensorflow as tf
    from sklearn.tree import DecisionTreeClassifier

    base, softmax_name, bucket_prefix, ood_csv = MODEL_PREFIX[which]
    model_dir = trap_repo / 'model'
    data_dir = trap_repo / 'data'

    trap_path = model_dir / base
    if not trap_path.exists():
        print(f'[run_trap][FATAL] TRAP 主模型缺: {trap_path}\n'
              f'  → 见 TODO-WEIGHTS，从 Google Drive 下载 model/ 放到 {trap_repo}', file=sys.stderr)
        sys.exit(1)
    print(f'[run_trap] load TRAP 主模型: {trap_path}', file=sys.stderr)
    trap = tf.keras.models.load_model(str(trap_path))

    # Confidence 链（可选）
    trap_softmax = None
    trap_softmaxbucket = None
    trap_ood = None
    softmax_path = model_dir / softmax_name
    bucket_files = sorted(model_dir.glob(bucket_prefix + '*')) if model_dir.exists() else []
    ood_path = data_dir / ood_csv
    if softmax_path.exists() and len(bucket_files) >= 10 and ood_path.exists():
        print(f'[run_trap] load Confidence 链（softmax + {len(bucket_files)} bucket + ood）',
              file=sys.stderr)
        trap_softmax = tf.keras.models.load_model(str(softmax_path))
        trap_softmaxbucket = [tf.keras.models.load_model(str(f)) for f in bucket_files]
        ood_data = pd.read_csv(ood_path)
        X_tr = ood_data[['max', 'ensemble_mean_maxprob']]
        y_tr = ood_data.iloc[:, -1]
        trap_ood = DecisionTreeClassifier().fit(X_tr, y_tr)
    else:
        print('[run_trap] Confidence 链缺件（softmax/bucket>=10/cal_ood），仅出 TRAP value，'
              'Confidence 留空。', file=sys.stderr)
    return trap, trap_softmax, trap_softmaxbucket, trap_ood


def run(args):
    trap_repo = Path(args.trap_repo).resolve()
    if not trap_repo.exists():
        print(f'[run_trap][FATAL] TRAP repo 不存在: {trap_repo}（先 git clone，见脚本头注）',
              file=sys.stderr)
        sys.exit(1)

    # 读输入（Peptide,nlog2Rank）
    df = pd.read_csv(args.input)
    need = {'Peptide', 'nlog2Rank'}
    if not need.issubset(df.columns):
        print(f'[run_trap][FATAL] 输入缺列 {need - set(df.columns)}。实际列={list(df.columns)}',
              file=sys.stderr)
        sys.exit(1)
    if args.smoke and args.smoke > 0:
        df = df.head(args.smoke).copy()
        print(f'[run_trap] SMOKE 模式：仅前 {len(df)} 行', file=sys.stderr)

    # 只保留官方需要的两列（与 dash callback 一致：df[['Peptide','nlog2Rank']]）
    test_data = df[['Peptide', 'nlog2Rank']].copy()
    test_data_p = preprocess_test_peptides(test_data)

    # tokenizer + ProtT5 encoder（官方 Rostlab/prot_t5_xl_uniref50, from_pt=True）
    print('[run_trap] 载入 ProtT5-XL-UniRef50（首次 ≈2.8GB 自 HF 下载）...', file=sys.stderr)
    from transformers import T5Tokenizer, TFT5EncoderModel
    os.environ.setdefault('CURL_CA_BUNDLE', '')   # 官方 dash 同设
    tokenizer = T5Tokenizer.from_pretrained('Rostlab/prot_t5_xl_uniref50', do_lower_case=False)
    encoder = TFT5EncoderModel.from_pretrained('Rostlab/prot_t5_xl_uniref50', from_pt=True)

    embedding = embed_test_peptides(test_data_p, tokenizer, encoder)
    print(f'[run_trap] 嵌入 shape={embedding.shape}', file=sys.stderr)

    trap, trap_softmax, trap_softmaxbucket, trap_ood = load_models(trap_repo, args.model)

    if trap_softmax is not None and trap_softmaxbucket is not None and trap_ood is not None:
        out_df = predict_trap(embedding, test_data_p, trap, trap_softmax,
                              trap_softmaxbucket, trap_ood)
    else:
        out_df = predict_trap_value_only(embedding, test_data_p, trap)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False, encoding='utf-8')
    print(f'[run_trap] 写 {out_path}  ({len(out_df)} 行, 列={list(out_df.columns)})', file=sys.stderr)
    print('[run_trap] 方向：TRAP value 越高越免疫原（>0.5 阳性），parse 不翻向。', file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description='TRAP 官方批量推理（复制 dash_app 推理逻辑）')
    ap.add_argument('--trap-repo', required=True, help='cloned TRAP repo 路径（含 model/ data/）')
    ap.add_argument('--input', required=True, help='trap_input.csv（列 Peptide,nlog2Rank）')
    ap.add_argument('--model', choices=['pathogenic', 'self'], default='self',
                    help='TRAP 模型变体（新抗原/癌症默认 self；见 TODO-MODEL）')
    ap.add_argument('--out', required=True, help='输出 trap_output.csv')
    ap.add_argument('--smoke', type=int, default=0, help='>0 则只跑前 N 行（烟测）')
    args = ap.parse_args()
    run(args)


if __name__ == '__main__':
    main()
