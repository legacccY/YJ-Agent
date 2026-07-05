#!/usr/bin/env python3
"""
MHLAPre GroupKFold Cross-Validation
- Leave-One-Patient-Out (9 folds) to get honest performance estimate
- Replaces the inflated AUC=0.997 from data leakage
- Also computes per-patient Fisher-Z Spearman for comparison with main eval
"""
import os, sys, argparse
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from sklearn.metrics import roc_auc_score, average_precision_score
from scipy.stats import spearmanr
import json

# ============================================================
# BLOSUM50 encoding (same as train_predict.py)
# ============================================================
AA_ORDER = list("ACDEFGHIKLMNPQRSTVWY")
AA2IDX = {aa: i for i, aa in enumerate(AA_ORDER)}

BLOSUM50 = np.array([
    [ 5,-2,-1,-2,-1,-1,-1, 0,-2,-1,-2,-1,-1,-3,-1, 1, 0,-3,-2, 0,-1],
    [-2,13,-4,-3,-2,-3,-3,-3,-3,-2,-2,-3,-2,-2,-4,-1,-1,-5,-3,-1,-1],
    [-1,-4, 7, 2,-2, 0, 0, 0, 1,-3,-4, 0,-2,-4,-2, 1, 0,-4,-2,-3,-1],
    [-2,-3, 2, 8,-4, 0, 2,-1,-1,-4,-4,-1,-4,-5,-1, 0,-1,-5,-3,-4,-1],
    [-1,-2,-2,-4,13,-3,-3,-3,-3,-2,-2,-3,-2,-2,-4,-1,-1,-5,-3,-1,-1],
    [-1,-3, 0, 0,-3, 7, 2,-2, 1,-3,-2, 2, 0,-4,-1, 0,-1,-1,-1,-3,-1],
    [-1,-3, 0, 2,-3, 2, 6,-3, 0,-4,-3, 1,-2,-3,-1,-1,-1,-3,-2,-3,-1],
    [ 0,-3, 0,-1,-3,-2,-3, 8,-2,-4,-4,-2,-3,-4,-2, 0,-2,-3,-3,-4,-1],
    [-2,-3, 1,-1,-3, 1, 0,-2,10,-4,-3, 0,-1,-1,-2,-1,-2,-3, 2,-4,-1],
    [-1,-2,-3,-4,-2,-3,-4,-4,-4, 5, 2,-3, 2, 0,-3,-3,-1,-3,-1, 4,-1],
    [-2,-3,-4,-4,-2,-2,-3,-4,-3, 2, 5,-3, 3, 1,-4,-3,-1,-2,-1, 1,-1],
    [-1,-3, 0,-1,-3, 2, 1,-2, 0,-3,-3, 6,-2,-4,-1, 0,-1,-3,-2,-3,-1],
    [-1,-2,-2,-4,-2, 0,-2,-3,-1, 2, 3,-2, 7, 0,-3,-2,-1,-1, 0, 1,-1],
    [-3,-2,-4,-5,-2,-4,-3,-4,-1, 0, 1,-4, 0, 8,-4,-3,-2, 1, 4,-1,-1],
    [-1,-4,-2,-1,-4,-1,-1,-2,-2,-3,-4,-1,-3,-4,10,-1,-1,-4,-3,-3,-1],
    [ 1,-1, 1, 0,-1, 0,-1, 0,-1,-3,-3, 0,-2,-3,-1, 5, 2,-4,-2,-2,-1],
    [ 0,-1, 0,-1,-1,-1,-1,-2,-2,-1,-1,-1,-1,-2,-1, 2, 5,-3,-2, 0,-1],
    [-3,-5,-4,-5,-5,-1,-3,-3,-3,-3,-2,-3,-1, 1,-4,-4,-3,15, 2,-3,-1],
    [-2,-3,-2,-3,-3,-1,-2,-3, 2,-1,-1,-2, 0, 4,-3,-2,-2, 2, 8,-1,-1],
    [ 0,-1,-3,-4,-1,-3,-3,-4,-4, 4, 1,-3, 1,-1,-3,-2, 0,-3,-1, 5,-1],
    [-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1]
], dtype=np.float32)

def encode_peptide_blosum(peptide, max_len=15):
    peptide = str(peptide).strip().upper()
    if len(peptide) > max_len:
        peptide = peptide[:max_len]
    idxs = [AA2IDX.get(aa, 20) for aa in peptide]
    k = len(idxs)
    idxs = idxs[:k//2] + [20] * (max_len - k) + idxs[k//2:]
    return BLOSUM50[idxs]

# ============================================================
# MHLAPre TextCNN Model (same architecture)
# ============================================================
class MHLAPreModel(nn.Module):
    def __init__(self, max_len=15, embed_dim=21, num_filters=300, dropout=0.2):
        super().__init__()
        kernel_sizes = [1, 2, 3]
        self.attention = nn.MultiheadAttention(embed_dim, 3, dropout=dropout, batch_first=True)
        self.convs = nn.ModuleList([
            nn.Conv1d(max_len, num_filters, ks, padding=ks//2) for ks in kernel_sizes
        ])
        fc_in = len(kernel_sizes) * num_filters
        self.fc = nn.Sequential(
            nn.Linear(fc_in, 1024), nn.BatchNorm1d(1024), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(1024, 256), nn.BatchNorm1d(256), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(256, 1)
        )

    def forward(self, x):
        x_attn, _ = self.attention(x, x, x)
        x = x + x_attn
        pooled = []
        for conv in self.convs:
            c = F.relu(conv(x))
            c = F.max_pool1d(c, c.size(2)).squeeze(2)
            pooled.append(c)
        x = torch.cat(pooled, dim=1)
        x = self.fc(x)
        return torch.sigmoid(x).squeeze()

# ============================================================
# Dataset
# ============================================================
class PeptideDataset(Dataset):
    def __init__(self, peptides, labels=None, max_len=15):
        self.X = [torch.tensor(encode_peptide_blosum(p, max_len), dtype=torch.float32) for p in peptides]
        self.has_label = labels is not None
        if self.has_label:
            self.y = [float(l) for l in labels]

    def __len__(self): return len(self.X)
    def __getitem__(self, i):
        if self.has_label:
            return self.X[i], torch.tensor(self.y[i], dtype=torch.float32)
        return self.X[i],

# ============================================================
# Training for one fold
# ============================================================
def train_fold(train_df, device, epochs=30, batch_size=128, lr=1e-3):
    labeled = train_df[train_df['label'].notna()].copy()
    labeled['label'] = labeled['label'].astype(int)

    # Internal val split (20% of training patients)
    patients = sorted(labeled['patient'].unique())
    np.random.seed(42)
    val_patients = set(np.random.choice(patients, max(1, len(patients)//5), replace=False))
    train_split = labeled[~labeled['patient'].isin(val_patients)]
    val_split = labeled[labeled['patient'].isin(val_patients)]

    train_ds = PeptideDataset(train_split['peptide'].values, labels=train_split['label'].values)
    val_ds = PeptideDataset(val_split['peptide'].values, labels=val_split['label'].values)
    train_dl = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    model = MHLAPreModel().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    loss_fn = nn.BCELoss()
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5)

    best_auc, best_state = 0, None
    for epoch in range(epochs):
        model.train()
        train_loss = 0
        for x, y in train_dl:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            loss = loss_fn(model(x), y)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()

        model.eval()
        val_preds, val_labels = [], []
        with torch.no_grad():
            for x, y in val_dl:
                val_preds.extend(model(x.to(device)).cpu().tolist())
                val_labels.extend(y.tolist())

        val_auc = roc_auc_score(val_labels, val_preds)
        scheduler.step(-val_auc)
        if val_auc > best_auc:
            best_auc = val_auc
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)
    return model, best_auc

# ============================================================
# Predict
# ============================================================
def predict_fold(model, df, device, batch_size=256):
    ds = PeptideDataset(df['peptide'].values)
    dl = DataLoader(ds, batch_size=batch_size, shuffle=False)
    model.eval()
    scores = []
    with torch.no_grad():
        for (x,) in dl:
            scores.extend(model(x.to(device)).cpu().tolist())
    return scores

# ============================================================
# MAIN: GroupKFold by Patient
# ============================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_dir', default='/gpfs/work/bio/zichenli24/rerun_v2')
    parser.add_argument('--output_dir', default='/gpfs/work/bio/zichenli24/rerun_v2/05_MHLAPre/outputs')
    parser.add_argument('--epochs', type=int, default=30)
    parser.add_argument('--batch_size', type=int, default=128)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--n_folds', type=int, default=9)
    args = parser.parse_args()

    # Auto-detect paths
    input_dir = os.path.join(args.data_dir, '05_MHLAPre', 'inputs')
    os.makedirs(args.output_dir, exist_ok=True)

    device = torch.device(args.device)
    print(f"Device: {device}")
    print(f"Data dir: {args.data_dir}")
    print(f"Input dir: {input_dir}")

    # Load training data
    print("\nLoading training data...")
    tdf = pd.read_csv(os.path.join(input_dir, 'dataset2_MT.csv'))
    tdf.columns = ['peptide', 'HLA', 'label', 'patient']
    wdf = pd.read_csv(os.path.join(input_dir, 'dataset2_WT.csv'))
    wdf.columns = ['peptide', 'HLA', 'label', 'patient']

    train_df = pd.concat([tdf, wdf], ignore_index=True)
    patients = sorted(train_df['patient'].unique())
    print(f"Total: {len(train_df)} rows, {len(patients)} patients")
    print(f"  Pos: {(train_df['label']==1).sum()}, Neg: {(train_df['label']==0).sum()}")

    # Also load the prediction data to know which peptides to predict for
    pred_mt = pd.read_csv(os.path.join(input_dir, 'dataset2_MT_predict.csv'))
    pred_mt.columns = ['peptide', 'allele', 'patient'] if len(pred_mt.columns)==3 else ['peptide', 'allele']
    pred_wt = pd.read_csv(os.path.join(input_dir, 'dataset2_WT_predict.csv'))
    pred_wt.columns = ['peptide', 'allele', 'patient'] if len(pred_wt.columns)==3 else ['peptide', 'allele']

    # ============================================================
    # GroupKFold CV: Leave-One-Patient-Out
    # ============================================================
    print(f"\n{'='*60}")
    print(f"GroupKFold CV: {args.n_folds} folds (Leave-One-Patient-Out)")
    print(f"{'='*60}")

    all_results = []
    fold_metrics = []

    for fold, test_patient in enumerate(patients[:args.n_folds]):
        print(f"\n--- Fold {fold+1}/{args.n_folds}: Test Patient = P{test_patient} ---")

        # Train on all other patients
        fold_train = train_df[train_df['patient'] != test_patient]
        fold_test = train_df[train_df['patient'] == test_patient]

        # Need "prediction" format: peptide, allele, patient with ground-truth label
        # Filter prediction data to this patient
        fold_test_pred = fold_test[['peptide', 'HLA', 'patient', 'label']].copy()
        fold_test_pred.columns = ['peptide', 'allele', 'patient', 'label']

        print(f"  Train: {len(fold_train)} rows ({fold_train['patient'].nunique()} patients)")
        print(f"  Test:  {len(fold_test)} rows (patient P{test_patient})")
        print(f"    Pos={fold_test['label'].sum()}, Neg={len(fold_test) - fold_test['label'].sum()}")

        # Train
        model, val_auc = train_fold(fold_train, device, epochs=args.epochs,
                                     batch_size=args.batch_size)

        # Predict on held-out patient
        scores = predict_fold(model, fold_test_pred, device)
        fold_test_pred['MHLAPre_score'] = scores
        fold_test_pred['fold'] = fold + 1
        fold_test_pred['test_patient'] = test_patient
        all_results.append(fold_test_pred)

        # Fold-level metrics
        test_labels = fold_test_pred['label'].values.astype(int)
        test_scores = fold_test_pred['MHLAPre_score'].values

        if len(np.unique(test_labels)) >= 2:
            fold_auc = roc_auc_score(test_labels, test_scores)
            fold_ap = average_precision_score(test_labels, test_scores)
        else:
            fold_auc = np.nan
            fold_ap = np.nan

        fold_spearman, fold_spear_p = spearmanr(test_labels, test_scores)

        print(f"  Fold AUC: {fold_auc:.4f}, AP: {fold_ap:.4f}, Spearman: {fold_spearman:.4f} (p={fold_spear_p:.4f})")
        fold_metrics.append({
            'fold': fold + 1,
            'test_patient': test_patient,
            'n_test': len(fold_test),
            'n_pos': int(fold_test['label'].sum()),
            'n_neg': int(len(fold_test) - fold_test['label'].sum()),
            'auc': fold_auc,
            'average_precision': fold_ap,
            'spearman_r': fold_spearman,
            'spearman_p': fold_spear_p,
        })

    # ============================================================
    # Aggregate Results
    # ============================================================
    all_preds = pd.concat(all_results, ignore_index=True)
    all_labels = all_preds['label'].values.astype(int)
    all_scores = all_preds['MHLAPre_score'].values

    # Overall AUC
    overall_auc = roc_auc_score(all_labels, all_scores)
    overall_ap = average_precision_score(all_labels, all_scores)
    overall_spear, overall_spear_p = spearmanr(all_labels, all_scores)

    # Per-patient Fisher-Z Spearman (matches eval_v5_three_tier methodology)
    from scipy.stats import spearmanr as spr
    import math
    def fisher_z(r):
        return 0.5 * math.log((1 + r) / (1 - r)) if abs(r) < 1 else 0.0
    def inv_fisher_z(z):
        return (math.exp(2*z) - 1) / (math.exp(2*z) + 1)

    per_patient_rhos = []
    for pid in sorted(all_preds['test_patient'].unique()):
        sub = all_preds[all_preds['test_patient'] == pid]
        if len(sub) >= 3 and len(np.unique(sub['label'])) >= 2:
            r, _ = spr(sub['label'], sub['MHLAPre_score'])
            n = len(sub)
            z = fisher_z(r)
            w = n - 3
            per_patient_rhos.append({'patient': pid, 'n': n, 'rho': r, 'z': z, 'weight': w})

    pp_df = pd.DataFrame(per_patient_rhos)
    if len(pp_df) > 0:
        total_w = pp_df['weight'].sum()
        fisher_z_weighted = (pp_df['z'] * pp_df['weight']).sum() / total_w
        fisher_z_se = 1.0 / np.sqrt(total_w)
        fisher_z_lo = inv_fisher_z(fisher_z_weighted - 1.96 * fisher_z_se)
        fisher_z_hi = inv_fisher_z(fisher_z_weighted + 1.96 * fisher_z_se)
        fisher_z_rho = inv_fisher_z(fisher_z_weighted)
    else:
        fisher_z_rho = np.nan
        fisher_z_lo, fisher_z_hi = np.nan, np.nan

    # ============================================================
    # Report
    # ============================================================
    print(f"\n{'='*60}")
    print("GROUP K-FOLD CV RESULTS (Leave-One-Patient-Out)")
    print(f"{'='*60}")
    print(f"  Folds:              {len(fold_metrics)}")
    print(f"  Total predictions:  {len(all_preds)}")
    print(f"  Overall AUC:        {overall_auc:.4f}  ← HONEST (was 0.997, leaked!)")
    print(f"  Overall AP:         {overall_ap:.4f}")
    print(f"  Global Spearman ρ:  {overall_spear:.4f} (p={overall_spear_p:.4f})")
    print(f"  Fisher-Z weighted:  {fisher_z_rho:.4f} [{fisher_z_lo:.4f}, {fisher_z_hi:.4f}]")
    print(f"  Per-fold AUC mean:  {np.nanmean([m['auc'] for m in fold_metrics]):.4f} ± {np.nanstd([m['auc'] for m in fold_metrics]):.4f}")

    print(f"\n  Per-fold details:")
    for m in fold_metrics:
        print(f"    Fold {m['fold']} P{m['test_patient']}: n={m['n_test']} pos={m['n_pos']} neg={m['n_neg']} "
              f"AUC={m['auc']:.4f} Spearman={m['spearman_r']:.4f}")

    # Save
    all_preds_out = os.path.join(args.output_dir, 'MHLAPre_GroupKFold_predictions.csv')
    all_preds.to_csv(all_preds_out, index=False)
    print(f"\n  Saved predictions: {all_preds_out}")

    cv_metrics = {
        'tool': 'MHLAPre',
        'method': 'GroupKFold_LeaveOnePatientOut',
        'n_folds': len(fold_metrics),
        'n_total': len(all_preds),
        'overall_auc': overall_auc,
        'overall_ap': overall_ap,
        'global_spearman_r': overall_spear,
        'global_spearman_p': overall_spear_p,
        'fisher_z_rho': fisher_z_rho,
        'fisher_z_95CI_lo': fisher_z_lo,
        'fisher_z_95CI_hi': fisher_z_hi,
        'per_fold_auc_mean': np.nanmean([m['auc'] for m in fold_metrics]),
        'per_fold_auc_std': np.nanstd([m['auc'] for m in fold_metrics]),
        'fold_details': fold_metrics,
        'caveat': 'HONEST estimate via GroupKFold (by Patient). Replaces leaked AUC=0.997 from train-on-test.',
    }

    cv_json_out = os.path.join(args.output_dir, 'MHLAPre_GroupKFold_metrics.json')
    with open(cv_json_out, 'w') as f:
        json.dump(cv_metrics, f, indent=2)
    print(f"  Saved metrics: {cv_json_out}")

    print(f"\n{'='*60}")
    print("CV COMPLETE")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()
