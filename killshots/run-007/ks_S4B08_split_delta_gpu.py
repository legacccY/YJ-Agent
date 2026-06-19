"""
G5 Kill-shot: S4B-08 — ISIC2020 患者级 leakage GPU 定量
服务: run-007 ACCV 选题流水线 G5 杀手锏（lever = S4B-08 split delta 量化）

预计单卡耗时: ~20-40 min (EfficientNet-B0 fine-tune 3-5 epochs x 2 splits，子集)
数据前置:
  data/raw/isic2020/train-metadata.csv (isic_id, patient_id, target)
  data/raw/isic2020/train-image/image/ (ISIC2020 原图 jpg)

超参（researcher 已确认来源）：
  backbone: EfficientNet-B0 ImageNet 预训练
  输入: 224×224
  lr: 1e-4 Adam
  batch: 32
  loss: BCE
  epochs: 3-5 (G5 证伪用，非刷 SOTA)
  来源: researcher 已查 ISIC2020 常用 baseline 设置（EfficientNet-B0 竞赛 baseline）

目标：
  对比 image-level random split vs patient-level split 两套训练的 test AUC delta
  patient-level split 保证 train/test 患者不重叠

R9 判读约定（_G5_DESIGN.md §S4B-08）：
  PASS    : delta >= 0.02 且 CI > 0 → 泄漏实质 → 维持 FINDINGS
  KILL    : delta CI 含 0 且窄 → 泄漏不实质 → 弱化
  GRAY    : 子集/低 epoch 致 CI 宽 → 需全量复测

实现策略（G5 证伪用，<1 GPU·h）：
  - 取子集 N=8000 图（正负平衡），非全量 33126（全量训到收敛超时）
  - image-level split: sklearn random StratifiedShuffleSplit，不管 patient_id
  - patient-level split: 按 patient_id 分患者，在患者级 stratify 后切 train/val/test
    保证 test 患者与 train 患者无重叠
  - 两套 split 用相同 test 尽量不可行时（patient split test 患者必须独立），
    分别评估各自 test AUC，报 delta + bootstrap CI

输出: killshots/run-007/results/S4B08_split_delta_gpu.csv
      killshots/run-007/results/S4B08_state.json
"""

import argparse
import csv
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms, models

# ── 路径 ────────────────────────────────────────────────────────────────────
REPO_ROOT   = Path(__file__).resolve().parent.parent.parent
ISIC_META   = REPO_ROOT / "data" / "raw" / "isic2020" / "train-metadata.csv"
ISIC_IMG    = REPO_ROOT / "data" / "raw" / "isic2020" / "train-image" / "image"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

# ── 超参（researcher 已确认）────────────────────────────────────────────────
BACKBONE    = "efficientnet_b0"  # ImageNet 预训练
IMG_SIZE    = 224
LR          = 1e-4   # Adam lr
BATCH_SIZE  = 32
G5_EPOCHS   = 3      # G5 证伪用；刷 SOTA 需更多 epoch
SUBSET_N    = 8000   # G5 子集，正负平衡（非全量 33126）
TEST_RATIO  = 0.2
VAL_RATIO   = 0.1
N_BOOTSTRAP = 1000
RANDOM_STATE = 42
MDE_DELTA   = 0.02   # AUC delta 门槛 (_G5_DESIGN §S4B-08 §2)


# ── Dataset ─────────────────────────────────────────────────────────────────


class ISICDataset(Dataset):
    def __init__(self, records, img_dir, transform=None):
        """records: list of (isic_id, label) tuples"""
        self.records = records
        self.img_dir = Path(img_dir)
        self.transform = transform

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        isic_id, label = self.records[idx]
        img_path = self.img_dir / f"{isic_id}.jpg"
        if not img_path.exists():
            # 部分图可能无扩展，尝试 .jpeg
            img_path = self.img_dir / f"{isic_id}.jpeg"
        img = Image.open(img_path).convert("RGB")
        if self.transform:
            img = self.transform(img)
        return img, torch.tensor(float(label), dtype=torch.float32)


# ── Split 构造 ───────────────────────────────────────────────────────────────


def build_image_level_split(records, test_ratio=TEST_RATIO, val_ratio=VAL_RATIO, seed=RANDOM_STATE):
    """image-level random split，不考虑 patient_id。"""
    rng = np.random.default_rng(seed)
    indices = np.arange(len(records))
    labels = np.array([r[2] for r in records])  # records: (isic_id, patient_id, label)

    # 先切 test
    from sklearn.model_selection import StratifiedShuffleSplit
    sss_test = StratifiedShuffleSplit(n_splits=1, test_size=test_ratio, random_state=seed)
    train_val_idx, test_idx = next(sss_test.split(indices, labels))

    # 再从 train_val 切 val
    tv_labels = labels[train_val_idx]
    val_ratio_adjusted = val_ratio / (1 - test_ratio)
    sss_val = StratifiedShuffleSplit(n_splits=1, test_size=val_ratio_adjusted, random_state=seed)
    train_idx_local, val_idx_local = next(sss_val.split(np.arange(len(train_val_idx)), tv_labels))

    train_idx = train_val_idx[train_idx_local]
    val_idx = train_val_idx[val_idx_local]

    train = [records[i][:3:2] for i in train_idx]    # (isic_id, label)
    val   = [records[i][:3:2] for i in val_idx]
    test  = [records[i][:3:2] for i in test_idx]
    return train, val, test


def build_patient_level_split(records, test_ratio=TEST_RATIO, val_ratio=VAL_RATIO, seed=RANDOM_STATE):
    """
    patient-level split: 按 patient_id 分患者，保证 train/test 患者不重叠。
    records: list of (isic_id, patient_id, label)
    """
    rng = np.random.default_rng(seed)
    # 收集患者级信息
    patient2records = {}
    for isic_id, patient_id, label in records:
        if patient_id not in patient2records:
            patient2records[patient_id] = []
        patient2records[patient_id].append((isic_id, label))

    patient_ids = list(patient2records.keys())
    # 每个患者的最常见标签（患者级 label 用于 stratify）
    patient_labels = []
    for pid in patient_ids:
        labels = [r[1] for r in patient2records[pid]]
        # 若患者有正例则为 positive patient
        patient_labels.append(1 if 1 in labels else 0)
    patient_labels = np.array(patient_labels)
    patient_ids = np.array(patient_ids)

    from sklearn.model_selection import StratifiedShuffleSplit
    # 先切 test patients
    sss_test = StratifiedShuffleSplit(n_splits=1, test_size=test_ratio, random_state=seed)
    train_val_pidx, test_pidx = next(sss_test.split(patient_ids, patient_labels))

    # 再切 val patients
    tv_plabels = patient_labels[train_val_pidx]
    val_ratio_adj = val_ratio / (1 - test_ratio)
    sss_val = StratifiedShuffleSplit(n_splits=1, test_size=val_ratio_adj, random_state=seed)
    train_pidx_local, val_pidx_local = next(
        sss_val.split(np.arange(len(train_val_pidx)), tv_plabels)
    )
    train_pidx = train_val_pidx[train_pidx_local]
    val_pidx   = train_val_pidx[val_pidx_local]

    def pid_to_records(pidx):
        out = []
        for i in pidx:
            pid = patient_ids[i]
            out.extend(patient2records[pid])
        return out

    train = pid_to_records(train_pidx)
    val   = pid_to_records(val_pidx)
    test  = pid_to_records(test_pidx)
    return train, val, test


# ── 模型 ─────────────────────────────────────────────────────────────────────


def build_model(device):
    """EfficientNet-B0 ImageNet 预训练，替换最后 fc 为二分类。"""
    model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.IMAGENET1K_V1)
    # 替换分类头
    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(in_features, 1)
    model = model.to(device)
    return model


# ── 训练一个 epoch ────────────────────────────────────────────────────────────


def train_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss = 0.0
    n_batches = 0
    for imgs, labels in loader:
        imgs, labels = imgs.to(device), labels.to(device).unsqueeze(1)
        optimizer.zero_grad()
        logits = model(imgs)
        loss = criterion(logits, labels)
        if torch.isnan(loss) or torch.isinf(loss):
            continue
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        n_batches += 1
    return total_loss / max(n_batches, 1)


# ── 推理（出 probabilities）──────────────────────────────────────────────────


def infer_probs(model, loader, device):
    model.eval()
    all_probs = []
    all_labels = []
    with torch.no_grad():
        for imgs, labels in loader:
            imgs = imgs.to(device)
            logits = model(imgs)
            probs = torch.sigmoid(logits).squeeze(1).cpu().numpy()
            all_probs.extend(probs.tolist())
            all_labels.extend(labels.numpy().tolist())
    return np.array(all_probs), np.array(all_labels)


# ── Bootstrap AUC CI（纯 numpy）────────────────────────────────────────────


def bootstrap_auc_ci(y_true, scores, n_boot=N_BOOTSTRAP, seed=RANDOM_STATE, alpha=0.05):
    from sklearn.metrics import roc_auc_score
    rng = np.random.default_rng(seed)
    n = len(y_true)
    boot = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        yt = y_true[idx]
        ys = scores[idx]
        if len(np.unique(yt)) < 2:
            continue
        boot.append(roc_auc_score(yt, ys))
    if len(boot) < 10:
        return float("nan"), float("nan")
    boot = np.array(boot)
    lo = float(np.percentile(boot, 100 * alpha / 2))
    hi = float(np.percentile(boot, 100 * (1 - alpha / 2)))
    return lo, hi


def bootstrap_delta_ci(y1, s1, y2, s2, n_boot=N_BOOTSTRAP, seed=RANDOM_STATE, alpha=0.05):
    """
    bootstrap delta CI: delta = AUC(split1) - AUC(split2)
    这里 split1=image-level, split2=patient-level，期望 delta >= MDE
    注意: 两套 split 的 test 样本不同（patient split 保患者不重叠），
    delta 的 bootstrap 需分别对两套 test 各自 bootstrap。
    """
    from sklearn.metrics import roc_auc_score
    rng = np.random.default_rng(seed)
    boot_deltas = []
    n1, n2 = len(y1), len(y2)
    for _ in range(n_boot):
        idx1 = rng.integers(0, n1, size=n1)
        idx2 = rng.integers(0, n2, size=n2)
        yt1, ys1 = y1[idx1], s1[idx1]
        yt2, ys2 = y2[idx2], s2[idx2]
        if len(np.unique(yt1)) < 2 or len(np.unique(yt2)) < 2:
            continue
        a1 = roc_auc_score(yt1, ys1)
        a2 = roc_auc_score(yt2, ys2)
        boot_deltas.append(a1 - a2)
    if len(boot_deltas) < 10:
        return float("nan"), float("nan")
    boot_deltas = np.array(boot_deltas)
    lo = float(np.percentile(boot_deltas, 100 * alpha / 2))
    hi = float(np.percentile(boot_deltas, 100 * (1 - alpha / 2)))
    return lo, hi


# ── 写工具 ───────────────────────────────────────────────────────────────────


def _write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"  -> {path}")


def _update_state(state_path, **kwargs):
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {}
    if state_path.exists():
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
    state.update(kwargs)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ── R9 判读 ──────────────────────────────────────────────────────────────────


def r9_verdict(delta, delta_ci_lo, delta_ci_hi, mde=MDE_DELTA):
    if any(isinstance(x, float) and np.isnan(x)
           for x in [delta, delta_ci_lo, delta_ci_hi]):
        return "GRAY", "CI 含 nan，功效不足，需全量复测"
    ci_width = delta_ci_hi - delta_ci_lo
    if ci_width > 0.15:
        return "GRAY", f"delta CI 宽={ci_width:.3f}>0.15，需全量复测"
    if delta >= mde and delta_ci_lo > 0:
        return "PASS", (f"delta={delta:.4f}>={mde}, CI=[{delta_ci_lo:.4f},{delta_ci_hi:.4f}] 不含 0 "
                        f"→ 泄漏实质 → 维持 FINDINGS")
    if delta_ci_lo <= 0 and ci_width < 0.10:
        return "KILL", (f"delta CI 含 0 且窄 (width={ci_width:.3f}) "
                        f"→ 泄漏不实质 → 弱化 story")
    return "GRAY", f"delta={delta:.4f} 未达 MDE={mde} 或 CI 宽，R9 待全量复测"


# ── 主流程 ───────────────────────────────────────────────────────────────────


def set_seed(seed=RANDOM_STATE):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def main(args):
    set_seed(RANDOM_STATE)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    state_path = RESULTS_DIR / "S4B08_state.json"

    # GPU 可用性
    if torch.cuda.is_available() and not args.cpu:
        device = torch.device(f"cuda:{args.gpu}")
        print(f"[S4B08] device: {device} ({torch.cuda.get_device_name(args.gpu)})")
    else:
        device = torch.device("cpu")
        print("[S4B08] WARNING: CUDA 不可用，退化到 CPU")

    _update_state(state_path, status="running", start_time=time.strftime("%Y-%m-%dT%H:%M:%S"),
                  device=str(device), smoke=args.smoke)

    # ── Step 1: 读 ISIC2020 metadata ─────────────────────────────────────────
    print("\n[Step 1] 读 ISIC2020 metadata")
    if not ISIC_META.exists():
        raise FileNotFoundError(f"ISIC2020 metadata 不存在: {ISIC_META}")

    records_all = []  # (isic_id, patient_id, label)
    with open(ISIC_META, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            records_all.append((row["isic_id"], row["patient_id"], int(row["target"])))
    print(f"  total records: {len(records_all)}")

    n_pos = sum(r[2] for r in records_all)
    n_neg = len(records_all) - n_pos
    print(f"  positive (malignant): {n_pos}, negative: {n_neg}")
    _update_state(state_path, n_total=len(records_all), n_pos=n_pos)

    # ── Step 2: 子集采样（G5 证伪，平衡正负，不超过 SUBSET_N）──────────────
    print(f"\n[Step 2] 子集采样 (target N={SUBSET_N}, 正负平衡)")
    pos_records = [r for r in records_all if r[2] == 1]
    neg_records = [r for r in records_all if r[2] == 0]

    n_each = min(SUBSET_N // 2, len(pos_records), len(neg_records))
    rng = np.random.default_rng(RANDOM_STATE)
    pos_idx = rng.choice(len(pos_records), size=n_each, replace=False)
    neg_idx = rng.choice(len(neg_records), size=n_each, replace=False)
    subset = [pos_records[i] for i in pos_idx] + [neg_records[i] for i in neg_idx]
    rng.shuffle(subset)
    if args.smoke:
        subset = subset[:200]
    print(f"  subset size: {len(subset)} (each class sampled: {min(n_each, len(subset) // 2)})")
    _update_state(state_path, subset_n=len(subset))

    # ── Step 3: 构造两套 split ───────────────────────────────────────────────
    print("\n[Step 3] 构造两套 split")
    img_train, img_val, img_test = build_image_level_split(subset)
    pat_train, pat_val, pat_test = build_patient_level_split(subset)

    print(f"  image-level  : train={len(img_train)}, val={len(img_val)}, test={len(img_test)}")
    print(f"  patient-level: train={len(pat_train)}, val={len(pat_val)}, test={len(pat_test)}")
    print(f"  patient-level test 正例: {sum(r[1] for r in pat_test)}")

    # ── Transforms ──────────────────────────────────────────────────────────
    train_tf = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225]),
    ])
    test_tf = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225]),
    ])

    num_workers = 0 if args.smoke else args.num_workers
    epochs = 1 if args.smoke else G5_EPOCHS

    from sklearn.metrics import roc_auc_score

    # ── Step 4: 训练两套分类器，计算 AUC ────────────────────────────────────
    aucs = {}
    probs_store = {}
    labels_store = {}

    for split_name, train_recs, val_recs, test_recs in [
        ("image_level", img_train, img_val, img_test),
        ("patient_level", pat_train, pat_val, pat_test),
    ]:
        print(f"\n[Step 4] 训练 {split_name} split (epochs={epochs})")

        train_ds = ISICDataset(train_recs, ISIC_IMG, transform=train_tf)
        val_ds   = ISICDataset(val_recs,   ISIC_IMG, transform=test_tf)
        test_ds  = ISICDataset(test_recs,  ISIC_IMG, transform=test_tf)

        train_loader = DataLoader(
            train_ds, batch_size=BATCH_SIZE, shuffle=True,
            num_workers=num_workers,
            multiprocessing_context="spawn" if num_workers > 0 else None,
            pin_memory=False, drop_last=True,
        )
        test_loader = DataLoader(
            test_ds, batch_size=64, shuffle=False,
            num_workers=num_workers,
            multiprocessing_context="spawn" if num_workers > 0 else None,
            pin_memory=False,
        )

        model = build_model(device)
        optimizer = optim.Adam(model.parameters(), lr=LR)
        criterion = nn.BCEWithLogitsLoss()

        t0 = time.time()
        for epoch in range(1, epochs + 1):
            avg_loss = train_epoch(model, train_loader, optimizer, criterion, device)
            elapsed = time.time() - t0
            print(f"  [{split_name}] epoch {epoch}/{epochs} | loss={avg_loss:.5f} | {elapsed:.0f}s")

        # 推理 test AUC
        probs, labels = infer_probs(model, test_loader, device)
        if len(np.unique(labels)) >= 2:
            auc = float(roc_auc_score(labels, probs))
        else:
            auc = float("nan")
            print(f"  [{split_name}] WARNING: test set 只有一类标签，AUC=nan")
        aucs[split_name] = auc
        probs_store[split_name] = probs
        labels_store[split_name] = labels
        print(f"  [{split_name}] test AUC: {auc:.4f}")
        _update_state(state_path, **{f"auc_{split_name}": auc})

        # 清理 model（释放显存）
        del model
        torch.cuda.empty_cache() if torch.cuda.is_available() else None

    # ── Step 5: 计算 delta + CI ──────────────────────────────────────────────
    print("\n[Step 5] 计算 AUC delta + bootstrap CI")
    auc_img = aucs.get("image_level", float("nan"))
    auc_pat = aucs.get("patient_level", float("nan"))
    delta = (auc_img - auc_pat) if not (np.isnan(auc_img) or np.isnan(auc_pat)) else float("nan")

    # bootstrap CI for delta
    y1 = labels_store["image_level"]
    s1 = probs_store["image_level"]
    y2 = labels_store["patient_level"]
    s2 = probs_store["patient_level"]

    if not np.isnan(delta):
        ci_lo, ci_hi = bootstrap_delta_ci(y1, s1, y2, s2)
        ci_lo_img, ci_hi_img = bootstrap_auc_ci(y1, s1)
        ci_lo_pat, ci_hi_pat = bootstrap_auc_ci(y2, s2)
    else:
        ci_lo = ci_hi = ci_lo_img = ci_hi_img = ci_lo_pat = ci_hi_pat = float("nan")

    verdict, verdict_msg = r9_verdict(
        delta if not np.isnan(delta) else float("nan"),
        ci_lo if not np.isnan(ci_lo) else float("nan"),
        ci_hi if not np.isnan(ci_hi) else float("nan"),
    )

    # ── 结果输出 ────────────────────────────────────────────────────────────
    row = {
        "auc_image_level":   round(auc_img, 4) if not np.isnan(auc_img) else "nan",
        "auc_image_ci_lo":   round(ci_lo_img, 4) if not np.isnan(ci_lo_img) else "nan",
        "auc_image_ci_hi":   round(ci_hi_img, 4) if not np.isnan(ci_hi_img) else "nan",
        "auc_patient_level": round(auc_pat, 4) if not np.isnan(auc_pat) else "nan",
        "auc_patient_ci_lo": round(ci_lo_pat, 4) if not np.isnan(ci_lo_pat) else "nan",
        "auc_patient_ci_hi": round(ci_hi_pat, 4) if not np.isnan(ci_hi_pat) else "nan",
        "delta_image_minus_patient": round(delta, 4) if not np.isnan(delta) else "nan",
        "delta_ci_lo": round(ci_lo, 4) if not np.isnan(ci_lo) else "nan",
        "delta_ci_hi": round(ci_hi, 4) if not np.isnan(ci_hi) else "nan",
        "n_test_image_level": len(img_test),
        "n_test_patient_level": len(pat_test),
        "subset_n": len(subset),
        "g5_epochs": epochs,
        "backbone": BACKBONE,
        "mde_threshold": MDE_DELTA,
        "r9_verdict": verdict,
        "r9_msg": verdict_msg,
        "note": (
            "G5 定量 3-epoch EfficientNet-B0 子集; image-level AUC 预期高于 patient-level "
            "（patient split 无跨患者泄漏）; delta=image_auc-patient_auc; "
            "bootstrap CI 独立对两套 test 各自采样再差分"
        ),
    }

    _write_csv(RESULTS_DIR / "S4B08_split_delta_gpu.csv", [row])

    print("\n" + "=" * 60)
    print(f"[S4B08] R9 判读: {verdict}")
    print(f"  {verdict_msg}")
    print(f"  image-level AUC={auc_img:.4f}  CI=[{ci_lo_img:.4f},{ci_hi_img:.4f}]")
    print(f"  patient-level AUC={auc_pat:.4f} CI=[{ci_lo_pat:.4f},{ci_hi_pat:.4f}]")
    print(f"  delta={delta:.4f}  CI=[{ci_lo:.4f},{ci_hi:.4f}]  MDE>={MDE_DELTA}")
    print("=" * 60)

    _update_state(state_path, status="done",
                  end_time=time.strftime("%Y-%m-%dT%H:%M:%S"),
                  r9_verdict=verdict, delta=delta)
    print("[S4B08] 完成。结果在 killshots/run-007/results/")


def parse_args():
    parser = argparse.ArgumentParser(
        description="S4B-08 G5 killshot: ISIC2020 split delta GPU 定量"
    )
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--cpu", action="store_true", help="强制 CPU 模式")
    parser.add_argument("--smoke", action="store_true",
                        help="烟测模式: 200 samples, 1 epoch")
    parser.add_argument("--num-workers", type=int, default=4)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(args)
