# -*- coding: utf-8 -*-
"""
三种 probe（冻结特征上的下游评测）：
  linear-probe   : 冻结 pooled 特征 [N,D] 上训 1-layer nn.Linear(D,14)，BCEWithLogitsLoss。
  attentive-probe: 冻结 token 特征 [N,T,D] 上训 repo 原版 AttentiveClassifier（注意力池化+linear），给 JEPA 公平。
  finetune       : 见 run_finetune.py —— 复现零偏离，照搬 FINETUNE.md 官方 recipe，不在此重写训练循环。

⚠️ 超参诚实声明（红线：超参禁臆想）：
  linear/attentive **probe-head 的超参（lr/epochs/wd/standardize）NOT 来自 CheXWorld 官方**——官方只给了
  full-finetune recipe（FINETUNE.md）。下方默认值是 SSL linear-probe 的通用工程惯例（AdamW + cosine，
  feature standardize），作 harness 默认；planner/researcher 应确认 probe sweep 协议。
  # TODO: 未找到 CheXWorld 官方 linear/attentive probe 超参，下方为 harness 惯例默认，需 researcher/planner 确认。

无泄漏断言：probe-train 与 test 的 patient_ids 交集必须为空（splits 已保证；此处显式 assert，红线）。
"""
import time
import numpy as np
import torch
import torch.nn as nn

import paths
import datasets as D

paths.ensure_repo_on_path()
from models.attentive_pooler import AttentiveClassifier  # noqa: E402

from metrics_auc import multilabel_auc


# ---------------------------------------------------------------------------
# 无泄漏断言
# ---------------------------------------------------------------------------
def assert_no_patient_leak(pids_train, pids_test):
    inter = set(np.asarray(pids_train).tolist()) & set(np.asarray(pids_test).tolist())
    assert len(inter) == 0, \
        f'!! 患者泄漏：probe-train 与 test 有 {len(inter)} 个重叠患者（示例 {list(inter)[:5]}）'


def _set_seed(seed):
    torch.manual_seed(seed)
    np.random.seed(seed)


# ---------------------------------------------------------------------------
# linear probe（pooled 特征）
# 默认超参 = harness 惯例（非官方），见文件头 TODO。
# ---------------------------------------------------------------------------
def run_linear_probe(train_cache, test_cache, seed=0, epochs=100, lr=1e-3, weight_decay=0.0,
                     batch_size=512, standardize=True, device='cuda'):
    _set_seed(seed)
    Xtr = np.asarray(train_cache['feats'], dtype=np.float32)
    ytr = np.asarray(train_cache['labels'], dtype=np.float32)
    Xte = np.asarray(test_cache['feats'], dtype=np.float32)
    yte = np.asarray(test_cache['labels'], dtype=np.float32)
    assert_no_patient_leak(train_cache['patient_ids'], test_cache['patient_ids'])

    if standardize:
        mu = Xtr.mean(0, keepdims=True)
        sd = Xtr.std(0, keepdims=True) + 1e-6
        Xtr = (Xtr - mu) / sd
        Xte = (Xte - mu) / sd

    Dn = Xtr.shape[1]
    C = ytr.shape[1]
    clf = nn.Linear(Dn, C).to(device)
    opt = torch.optim.AdamW(clf.parameters(), lr=lr, weight_decay=weight_decay)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    crit = nn.BCEWithLogitsLoss()

    Xtr_t = torch.from_numpy(Xtr).to(device)
    ytr_t = torch.from_numpy(ytr).to(device)
    n = Xtr_t.shape[0]
    t0 = time.time()
    for ep in range(epochs):
        clf.train()
        perm = torch.randperm(n, device=device)
        for i in range(0, n, batch_size):
            idx = perm[i:i + batch_size]
            opt.zero_grad()
            loss = crit(clf(Xtr_t[idx]), ytr_t[idx])
            loss.backward()
            opt.step()
        sched.step()
    clf.eval()
    with torch.no_grad():
        scores = clf(torch.from_numpy(Xte).to(device)).cpu().numpy()
    mauc, per_class = multilabel_auc(scores, yte)
    return dict(mAUC=mauc, per_class_auc=per_class, n_train=int(n), n_test=int(Xte.shape[0]),
                seconds=round(time.time() - t0, 1))


# ---------------------------------------------------------------------------
# attentive probe（token 特征；repo 原版 AttentiveClassifier）
# ---------------------------------------------------------------------------
def run_attentive_probe(train_cache, test_cache, feature_dim, num_heads=12, seed=0,
                        epochs=50, lr=1e-3, weight_decay=0.0, batch_size=256, device='cuda'):
    _set_seed(seed)
    Ttr = train_cache['tokens']      # memmap [N,T,D]
    ytr = np.asarray(train_cache['labels'], dtype=np.float32)
    Tte = test_cache['tokens']
    yte = np.asarray(test_cache['labels'], dtype=np.float32)
    assert_no_patient_leak(train_cache['patient_ids'], test_cache['patient_ids'])

    C = ytr.shape[1]
    clf = AttentiveClassifier(embed_dim=feature_dim, num_heads=num_heads, num_classes=C).to(device)
    opt = torch.optim.AdamW(clf.parameters(), lr=lr, weight_decay=weight_decay)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    crit = nn.BCEWithLogitsLoss()
    ytr_t = torch.from_numpy(ytr).to(device)

    n = Ttr.shape[0]
    t0 = time.time()
    for ep in range(epochs):
        clf.train()
        perm = np.random.permutation(n)
        for i in range(0, n, batch_size):
            idx = np.sort(perm[i:i + batch_size])           # memmap 需升序索引
            xb = torch.from_numpy(np.asarray(Ttr[idx])).to(device)
            yb = ytr_t[torch.from_numpy(idx).to(device)]
            opt.zero_grad()
            loss = crit(clf(xb), yb)
            loss.backward()
            opt.step()
        sched.step()
    clf.eval()
    scores = np.zeros((Tte.shape[0], C), dtype=np.float32)
    with torch.no_grad():
        for i in range(0, Tte.shape[0], batch_size):
            xb = torch.from_numpy(np.asarray(Tte[i:i + batch_size])).to(device)
            scores[i:i + batch_size] = clf(xb).cpu().numpy()
    mauc, per_class = multilabel_auc(scores, yte)
    return dict(mAUC=mauc, per_class_auc=per_class, n_train=int(n), n_test=int(Tte.shape[0]),
                seconds=round(time.time() - t0, 1))


if __name__ == '__main__':
    print('probes: run_linear_probe (pooled) / run_attentive_probe (tokens) / finetune->run_finetune.py')
    print('!! probe-head 超参为 harness 惯例默认，非 CheXWorld 官方，见文件头 TODO。')
