# -*- coding: utf-8 -*-
"""
多标签 AUC —— 纯 numpy 实现（Windows 规范：不用 scipy/sklearn，避免与 torch 抢 OpenMP -> OMP Error #15）

AUC 用 Mann-Whitney / rank 公式：AUC = (R_pos - n_pos*(n_pos+1)/2) / (n_pos * n_neg)，
其中 R_pos = 正样本秩之和（平均秩处理并列）。与 sklearn.metrics.roc_auc_score 数值等价（含 tie 处理）。

退化类（某类在该 split 上全 0 或全 1，n_pos==0 或 n_neg==0）→ AUC=nan，mean 时跳过 nan。
"""
import numpy as np


def _rankdata_average(x):
    """对一维数组返回平均秩（ties 取平均），等价 scipy.stats.rankdata(method='average')。"""
    x = np.asarray(x, dtype=np.float64)
    n = x.shape[0]
    order = np.argsort(x, kind='mergesort')          # 稳定排序
    ranks = np.empty(n, dtype=np.float64)
    sorted_x = x[order]
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sorted_x[j + 1] == sorted_x[i]:
            j += 1
        # [i, j] 为一组并列，秩为 1-based 平均
        avg_rank = (i + j) / 2.0 + 1.0
        ranks[order[i:j + 1]] = avg_rank
        i = j + 1
    return ranks


def binary_auc(scores, labels):
    """单类 AUC。labels∈{0,1}。退化（全 0 / 全 1）返回 nan。"""
    scores = np.asarray(scores, dtype=np.float64).ravel()
    labels = np.asarray(labels).ravel()
    pos = labels == 1
    neg = labels == 0
    n_pos = int(pos.sum())
    n_neg = int(neg.sum())
    if n_pos == 0 or n_neg == 0:
        return float('nan')
    ranks = _rankdata_average(scores)
    r_pos = ranks[pos].sum()
    auc = (r_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    return float(auc)


def multilabel_auc(scores, labels):
    """
    scores: [N, C] 预测 logit/概率（单调即可，AUC 不受单调变换影响）
    labels: [N, C] 0/1
    返回 (mauc, per_class_auc_list)。per_class 含 nan 的退化类；mauc 为非 nan 类均值 *100。
    与 repo util/metrics.compute_auc 同口径（*100），但纯 numpy。
    """
    scores = np.asarray(scores, dtype=np.float64)
    labels = np.asarray(labels)
    assert scores.shape == labels.shape, f'shape mismatch {scores.shape} vs {labels.shape}'
    C = scores.shape[1]
    per_class = []
    for c in range(C):
        a = binary_auc(scores[:, c], labels[:, c])
        per_class.append(a * 100.0 if a == a else float('nan'))  # a==a 过滤 nan
    valid = [a for a in per_class if a == a]
    mauc = float(np.mean(valid)) if valid else float('nan')
    return mauc, per_class


if __name__ == '__main__':
    # 静态自检（小数组 sanity，不依赖项目数据）—— 仍交主线跑，此处只是可独立 py_compile
    rng = np.random.RandomState(0)
    y = rng.randint(0, 2, size=(200, 3))
    s = rng.randn(200, 3) + y * 0.8
    m, pc = multilabel_auc(s, y)
    print('demo mauc=%.4f per_class=%s' % (m, pc))
