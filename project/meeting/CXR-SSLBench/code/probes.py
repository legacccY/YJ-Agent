# -*- coding: utf-8 -*-
"""
四种 probe（冻结特征上的下游评测）：
  linear-probe   : 冻结 pooled 特征 [N,D] 上训 1-layer nn.Linear(D,C)，BCEWithLogitsLoss。
  attentive-probe: 冻结 token 特征 [N,T,D] 上训 attentive pooling 头（默认 DINOv2/IJEPA-eval 标准 MHA
                   pooling，自含实现 AttentiveProbeHead；可选 head='repo' 用 CheXWorld repo AttentiveClassifier）。
  knn-probe      : 冻结 pooled 特征上做 DINO-eval 风格 kNN（k=20,T=0.07 DINO 默认，cosine），无参数训练。
  finetune       : 见 run_finetune.py —— 复现零偏离，照搬 FINETUNE.md 官方 recipe，不在此重写训练循环。

⚠️ 超参诚实声明（红线：超参禁臆想）：
  linear/attentive **probe-head 的训练超参（lr/epochs/wd/standardize）NOT 来自 CheXWorld 官方**——官方只给了
  full-finetune recipe（FINETUNE.md）。下方默认值是 SSL linear-probe 的通用工程惯例（AdamW + cosine，
  feature standardize），作 harness 默认；planner/researcher 应确认 probe sweep 协议。
  # TODO: 未找到 CheXWorld 官方 linear/attentive probe 训练超参，下方为 harness 惯例默认，需 researcher/planner 确认。
  attentive 头**结构**超参（num_queries=1 / num_heads=12(ViT-B 768/12=64 head_dim) / mlp_ratio=4.0 / depth=1）
  取 DINOv2/IJEPA/V-JEPA eval AttentivePooler 的标准默认，非臆想（同构于 repo AttentiveClassifier）。
  knn k=20 + temperature=0.07 = DINO/DINOv2 kNN-eval 官方默认；多标签为 DINO 单标签 kNN 的文档化适配（见 run_knn_probe）。

无泄漏断言：probe-train 与 test 的 patient_ids 交集必须为空（splits 已保证；此处显式 assert，红线）。
"""
import time
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from metrics_auc import multilabel_auc


# ---------------------------------------------------------------------------
# repo AttentiveClassifier 惰性加载（仅 head='repo' 时才需 CheXWorld repo 在 path 上；
# 默认 head='mha' 用自含 AttentiveProbeHead，使本模块无 repo 依赖即可 import（pytest 友好））。
# ---------------------------------------------------------------------------
def _load_repo_attentive_classifier():
    import paths
    paths.ensure_repo_on_path()
    from models.attentive_pooler import AttentiveClassifier
    return AttentiveClassifier


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
# attentive probe 头 —— DINOv2 / IJEPA / V-JEPA eval 标准 attentive pooling
# 自含实现（nn.MultiheadAttention），不依赖 CheXWorld repo，pytest 友好。
# 结构 = 1 个 learnable query token + 单层 cross-attention block（pre-norm MHA + 残差 + MLP）+ linear 分类头，
# 与 repo models/attentive_pooler.py::AttentiveClassifier（complete_block, num_queries=1, depth=1）同构。
# 结构超参取标准默认（num_heads=12 / mlp_ratio=4.0 / init_std=0.02），非臆想。
# ---------------------------------------------------------------------------
class AttentiveProbeHead(nn.Module):
    def __init__(self, embed_dim, num_classes, num_heads=12, mlp_ratio=4.0, init_std=0.02):
        super().__init__()
        self.query = nn.Parameter(torch.zeros(1, 1, embed_dim))
        self.norm_q = nn.LayerNorm(embed_dim)
        self.norm_kv = nn.LayerNorm(embed_dim)
        self.attn = nn.MultiheadAttention(embed_dim, num_heads, batch_first=True)
        self.norm_mlp = nn.LayerNorm(embed_dim)
        hidden = int(embed_dim * mlp_ratio)
        self.mlp = nn.Sequential(nn.Linear(embed_dim, hidden), nn.GELU(), nn.Linear(hidden, embed_dim))
        self.norm_out = nn.LayerNorm(embed_dim)
        self.linear = nn.Linear(embed_dim, num_classes)
        self._init_std = init_std
        nn.init.trunc_normal_(self.query, std=init_std)
        self.apply(self._init_weights)

    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            nn.init.trunc_normal_(m.weight, std=self._init_std)
            if m.bias is not None:
                nn.init.constant_(m.bias, 0.0)
        elif isinstance(m, nn.LayerNorm):
            nn.init.constant_(m.bias, 0.0)
            nn.init.constant_(m.weight, 1.0)

    def forward(self, x):
        # x: [B, T, D] frozen tokens（pooling-agnostic，对所有 backbone 统一，是公平主对照）
        B = x.shape[0]
        q = self.query.expand(B, -1, -1)                       # [B,1,D]
        kv = self.norm_kv(x)
        attn_out, _ = self.attn(self.norm_q(q), kv, kv)        # [B,1,D]
        q = q + attn_out
        q = q + self.mlp(self.norm_mlp(q))
        return self.linear(self.norm_out(q.squeeze(1)))         # [B,C]


def _build_attentive_head(head, feature_dim, num_classes, num_heads, device):
    if head == 'mha':
        return AttentiveProbeHead(embed_dim=feature_dim, num_classes=num_classes,
                                  num_heads=num_heads).to(device)
    elif head == 'repo':
        AttentiveClassifier = _load_repo_attentive_classifier()
        return AttentiveClassifier(embed_dim=feature_dim, num_heads=num_heads,
                                   num_classes=num_classes).to(device)
    else:
        raise ValueError(f"head 须为 'mha'(DINOv2-eval 自含) 或 'repo'(CheXWorld AttentiveClassifier)，得到 {head}")


# ---------------------------------------------------------------------------
# attentive probe（token 特征；默认 head='mha' = DINOv2-eval 标准 MHA pooling）
# ---------------------------------------------------------------------------
def run_attentive_probe(train_cache, test_cache, feature_dim, num_heads=12, seed=0,
                        epochs=50, lr=1e-3, weight_decay=0.0, batch_size=256, device='cuda',
                        head='mha'):
    _set_seed(seed)
    Ttr = train_cache['tokens']      # memmap [N,T,D]
    ytr = np.asarray(train_cache['labels'], dtype=np.float32)
    Tte = test_cache['tokens']
    yte = np.asarray(test_cache['labels'], dtype=np.float32)
    assert_no_patient_leak(train_cache['patient_ids'], test_cache['patient_ids'])

    C = ytr.shape[1]
    clf = _build_attentive_head(head, feature_dim, C, num_heads, device)
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


# ---------------------------------------------------------------------------
# knn probe（pooled 特征；DINO/DINOv2 eval 风格 kNN，无参数训练）
# k=20 + temperature=0.07 = DINO/DINOv2 kNN-eval 官方默认；cosine 相似度（特征 L2 归一化后内积）。
# 多标签适配（文档化，非官方）：DINO 官方 kNN 为单标签温度加权类投票（每个近邻投自己的类）；
#   多标签 NIH/VinDr 下改为「取 k 近邻、按 softmax(sim/T) 权重对近邻的多热标签向量加权平均」-> [C] 分数供 AUC。
#   单标签退化为标准 DINO 软投票，故是其自然推广。
# ---------------------------------------------------------------------------
def run_knn_probe(train_cache, test_cache, k=20, temperature=0.07, seed=0,
                  l2_normalize=True, device='cuda', chunk=1024):
    _set_seed(seed)
    Xtr = torch.from_numpy(np.asarray(train_cache['feats'], dtype=np.float32))
    ytr = torch.from_numpy(np.asarray(train_cache['labels'], dtype=np.float32))
    Xte = torch.from_numpy(np.asarray(test_cache['feats'], dtype=np.float32))
    yte = np.asarray(test_cache['labels'], dtype=np.float32)
    assert_no_patient_leak(train_cache['patient_ids'], test_cache['patient_ids'])

    t0 = time.time()
    Xtr = Xtr.to(device)
    ytr = ytr.to(device)
    Xte = Xte.to(device)
    if l2_normalize:
        Xtr = F.normalize(Xtr, dim=1)
        Xte = F.normalize(Xte, dim=1)

    Ntr = Xtr.shape[0]
    N = Xte.shape[0]
    C = ytr.shape[1]
    k_eff = int(min(k, Ntr))
    scores = torch.zeros((N, C), dtype=torch.float32, device=device)
    with torch.no_grad():
        for i in range(0, N, chunk):
            sims = Xte[i:i + chunk] @ Xtr.t()                  # [b, Ntr] cosine（已归一化）
            topv, topi = sims.topk(k_eff, dim=1)               # [b, k]
            w = torch.softmax(topv / temperature, dim=1)       # [b, k] 温度加权
            nbr_labels = ytr[topi]                             # [b, k, C]
            scores[i:i + chunk] = (w.unsqueeze(-1) * nbr_labels).sum(dim=1)  # [b, C]
    scores = scores.cpu().numpy()
    mauc, per_class = multilabel_auc(scores, yte)
    return dict(mAUC=mauc, per_class_auc=per_class, n_train=int(Ntr), n_test=int(N),
                seconds=round(time.time() - t0, 1))


if __name__ == '__main__':
    print('probes: run_linear_probe (pooled) / run_attentive_probe (tokens, head=mha|repo) / '
          'run_knn_probe (pooled, k=20) / finetune->run_finetune.py')
    print('!! probe-head 训练超参为 harness 惯例默认，非 CheXWorld 官方，见文件头 TODO。')
    print('!! attentive 结构超参 + knn k/T 取 DINOv2/IJEPA/DINO eval 标准默认（非臆想）。')
