"""
G5 Kill-shot: S5-07 — AD 大病灶失效边界外推（GPU 步）
服务: run-007 ACCV 选题流水线 G5 杀手锏（lever = S5-07 AD 失效相图 MAIN 保底）

预计单卡耗时: ~15-30 min (3-5 epoch AE on 6705 HAM-NV 64x64)
数据前置: data/external/ham10000/ (HAM10000 图 + metadata + GT lesion mask)
          project/meeting/MedAD-FailMap/ (failure_boundary.py + train_recon_ae.py)

目标（GPU 步）：
  1. 训 AE on HAM-NV 正常子集（3-5 epoch 证伪用，非全量复现）
  2. 推理全量 HAM-NV 图，产出 anomaly_score
  3. 用官方 GT lesion mask（非 proxy）算每张图 lesion_area_px 和 relative_size
  4. 按 lesion relative_size 分层（small/large，中位数切分），测大/小方向化 AUROC
  5. bootstrap 95% CI；判读 R9 三分流

R9 判读约定（_G5_DESIGN.md §S5-07）：
  PASS/signal : large 方向 AUROC CI 下界 > 0.5 且 large-small 差 CI 不含 0
                且差 >= 0.05 → 相图有跨域结构 → 维持 MAIN
  KILL        : large 方向 CI 整体含/低于 0.5 且 CI 窄（large-small 差 CI 含 0）
                → 无跨域结构 → 降 FINDINGS
  GRAY        : CI 宽（功效不足）→ 标需扩规模，MAIN 进 G6

数据路径（.portfolio/datasets.json 真源）：
  HAM10000 图: data/external/ham10000/HAM10000_images_part_1/ + part_2/
  HAM10000 metadata: data/external/ham10000/HAM10000_metadata.csv
  HAM10000 GT mask: data/external/ham10000/HAM10000_segmentations_lesion_tschandl/
                    ISIC_<id>_segmentation.png (binary PNG, 0=bg, 255=fg)

超参（researcher 已确认 / 官方 MedIAnomaly 来源）：
  G5 证伪模式: epochs=5, bs=64, lr=1e-3, AE 结构同官方 MedIAnomaly
  完整复现: 250 epochs（主线 /loop /run-experiment 起）
  注意: G5 只验 delta 方向，5 epoch 不是复现，anomaly_score 仅用于相对排序

输出: killshots/run-007/results/S5A07_anomaly_scores.csv
      killshots/run-007/results/S5A07_lesion_features.csv
      killshots/run-007/results/S5A07_failure_boundary.csv
      killshots/run-007/results/S5A07_state.json (进度记录)
"""

import argparse
import csv
import json
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
from torchvision import transforms

# ── 路径 ────────────────────────────────────────────────────────────────────
REPO_ROOT   = Path(__file__).resolve().parent.parent.parent
HAM_ROOT    = REPO_ROOT / "data" / "external" / "ham10000"
HAM_META    = HAM_ROOT / "HAM10000_metadata.csv"
HAM_MASK_DIR = HAM_ROOT / "HAM10000_segmentations_lesion_tschandl"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

# MedAD-FailMap 代码目录（借用 failure_boundary.py 函数）
MEDAD_CODE  = REPO_ROOT / "project" / "meeting" / "MedAD-FailMap" / "code"

# ── G5 证伪超参（5 epoch 只验方向，非全量复现）───────────────────────────────
G5_EPOCHS   = 5   # 证伪用；完整复现 250 epochs 交主线
OFFICIAL_BS = 64
OFFICIAL_LR = 1e-3  # 来源: MedIAnomaly base_worker.py Adam lr=1e-3 wd=0
OFFICIAL_LATENT = 16
INPUT_SIZE  = 64
MDE_DIRECTION_DIFF = 0.05   # R9 预声明 MDE: large-small AUROC 差 >= 0.05
N_BOOTSTRAP = 1000
RANDOM_STATE = 42

# ── 官方 AE 结构（复用自 MedAD-FailMap/code/train_recon_ae.py）──────────────


class ConvBlock(nn.Module):
    def __init__(self, in_c, out_c, stride=2):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_c, out_c, kernel_size=4, stride=stride, padding=1, bias=False),
            nn.BatchNorm2d(out_c),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.block(x)


class DeconvBlock(nn.Module):
    def __init__(self, in_c, out_c, last=False):
        super().__init__()
        if last:
            self.block = nn.Sequential(
                nn.ConvTranspose2d(in_c, out_c, kernel_size=4, stride=2, padding=1, bias=False),
            )
        else:
            self.block = nn.Sequential(
                nn.ConvTranspose2d(in_c, out_c, kernel_size=4, stride=2, padding=1, bias=False),
                nn.BatchNorm2d(out_c),
                nn.ReLU(inplace=True),
            )

    def forward(self, x):
        return self.block(x)


class AEEncoder(nn.Module):
    _MID_NUM = 2048

    def __init__(self, in_c=1, base_c=16, latent=16):
        super().__init__()
        self.enc = nn.Sequential(
            ConvBlock(in_c,     base_c),
            ConvBlock(base_c,   base_c * 2),
            ConvBlock(base_c*2, base_c * 4),
            ConvBlock(base_c*4, base_c * 4),
        )
        feat_dim = base_c * 4 * 4 * 4
        self.fc = nn.Sequential(
            nn.Linear(feat_dim, self._MID_NUM),
            nn.BatchNorm1d(self._MID_NUM),
            nn.ReLU(inplace=True),
            nn.Linear(self._MID_NUM, latent),
        )

    def forward(self, x):
        h = self.enc(x)
        h = h.view(h.size(0), -1)
        return self.fc(h)


class AEDecoder(nn.Module):
    _MID_NUM = 2048

    def __init__(self, in_c=1, base_c=16, latent=16):
        super().__init__()
        feat_dim = base_c * 4 * 4 * 4
        self.fc = nn.Sequential(
            nn.Linear(latent, self._MID_NUM),
            nn.BatchNorm1d(self._MID_NUM),
            nn.ReLU(inplace=True),
            nn.Linear(self._MID_NUM, feat_dim),
        )
        self.dec = nn.Sequential(
            DeconvBlock(base_c*4, base_c*4),
            DeconvBlock(base_c*4, base_c*2),
            DeconvBlock(base_c*2, base_c),
            DeconvBlock(base_c,   in_c, last=True),
        )

    def forward(self, z):
        h = self.fc(z)
        h = h.view(h.size(0), 64, 4, 4)
        return self.dec(h)


class AENet(nn.Module):
    def __init__(self, in_c=1, base_c=16, latent=16):
        super().__init__()
        self.encoder = AEEncoder(in_c, base_c, latent)
        self.decoder = AEDecoder(in_c, base_c, latent)

    def forward(self, x):
        return self.decoder(self.encoder(x))


# ── Dataset ─────────────────────────────────────────────────────────────────


class HAMNVDataset(Dataset):
    """HAM10000 NV 子集，用于训练（dx==nv）和全量推理"""

    def __init__(self, image_ids, ham_root, transform=None):
        self.ham_root = Path(ham_root)
        self.transform = transform
        self.image_ids = image_ids
        self.part_dirs = [
            self.ham_root / "HAM10000_images_part_1",
            self.ham_root / "HAM10000_images_part_2",
        ]
        # 构建 id -> 路径映射
        self.id2path = {}
        for d in self.part_dirs:
            if d.exists():
                for p in d.iterdir():
                    stem = p.stem  # e.g. ISIC_0024306
                    self.id2path[stem] = p
        # 过滤有图文件的 id
        self.valid_ids = [iid for iid in image_ids if iid in self.id2path]
        if len(self.valid_ids) < len(image_ids):
            missing = len(image_ids) - len(self.valid_ids)
            print(f"[HAMNVDataset] WARNING: {missing} image_ids 无对应文件，已跳过")

    def __len__(self):
        return len(self.valid_ids)

    def __getitem__(self, idx):
        iid = self.valid_ids[idx]
        path = self.id2path[iid]
        img = Image.open(path).convert("L")
        if self.transform:
            img = self.transform(img)
        return img, iid


# ── GT mask 特征计算 ─────────────────────────────────────────────────────────


def compute_lesion_features(image_ids, mask_dir):
    """
    用官方 GT lesion mask 计算每张图 lesion_area_px 和 relative_size。
    mask_dir: HAM10000_segmentations_lesion_tschandl/
              命名: ISIC_<id>_segmentation.png (binary PNG 0=bg 255=fg)
    返回: dict {image_id: {lesion_area_px, total_area_px, relative_size}}
    """
    mask_dir = Path(mask_dir)
    features = {}
    missing_mask = 0
    for iid in image_ids:
        mask_path = mask_dir / f"{iid}_segmentation.png"
        if not mask_path.exists():
            missing_mask += 1
            features[iid] = {"lesion_area_px": float("nan"),
                             "total_area_px": float("nan"),
                             "relative_size": float("nan")}
            continue
        mask = np.array(Image.open(mask_path).convert("L"))
        total_area = float(mask.shape[0] * mask.shape[1])
        lesion_area = float(np.sum(mask > 127))  # 255 前景
        rel_size = lesion_area / total_area if total_area > 0 else float("nan")
        features[iid] = {
            "lesion_area_px": lesion_area,
            "total_area_px": total_area,
            "relative_size": rel_size,
        }
    if missing_mask > 0:
        print(f"[lesion_features] WARNING: {missing_mask} mask 文件缺失（relative_size=nan）")
    return features


# ── Bootstrap AUROC CI (纯 numpy + sklearn，无 scipy) ────────────────────────


def bootstrap_auroc_ci(y_true, scores, n_boot=1000, seed=42, alpha=0.05):
    """95% bootstrap CI, 纯 numpy。防 scipy OMP#15。"""
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


# ── 方向化 AUROC 计算 ────────────────────────────────────────────────────────


def directional_auroc(image_ids, scores_dict, features_dict, size_threshold=None):
    """
    按 relative_size 分 small/large（median 切分），计算各方向 AUROC。
    AD 失效方向: large 病灶 vs small 病灶，用 anomaly_score 作连续分预测。
    label: large=1(异常-高分期望), small=0（正常-低分期望）
    返回: dict with AUROC + CI 各方向
    """
    from sklearn.metrics import roc_auc_score
    # 收集有效样本
    valid_ids = []
    valid_scores = []
    valid_sizes = []
    for iid in image_ids:
        s = scores_dict.get(iid)
        f = features_dict.get(iid, {})
        rel_s = f.get("relative_size", float("nan"))
        if s is None or np.isnan(s) or np.isnan(rel_s):
            continue
        valid_ids.append(iid)
        valid_scores.append(s)
        valid_sizes.append(rel_s)

    valid_scores = np.array(valid_scores)
    valid_sizes = np.array(valid_sizes)
    n = len(valid_ids)
    print(f"[directional_auroc] valid samples: {n}")

    if size_threshold is None:
        size_threshold = float(np.median(valid_sizes))
    print(f"[directional_auroc] size_threshold (median): {size_threshold:.4f}")

    large_mask = valid_sizes >= size_threshold
    small_mask = valid_sizes < size_threshold
    n_large = int(large_mask.sum())
    n_small = int(small_mask.sum())
    print(f"[directional_auroc] large={n_large}, small={n_small}")

    results = {
        "n_valid": n,
        "n_large": n_large,
        "n_small": n_small,
        "size_threshold_median": round(float(size_threshold), 6),
    }

    # AUROC: 大病灶（label=1）vs 小病灶（label=0），score 预测能否区分
    y_direction = large_mask.astype(int)  # 1=large, 0=small
    if len(np.unique(y_direction)) < 2:
        print("[directional_auroc] WARNING: 只有一类大小，AUROC 无定义")
        results.update({
            "large_direction_auroc": float("nan"),
            "small_direction_auroc": float("nan"),
            "direction_diff": float("nan"),
            "large_ci_lo": float("nan"),
            "large_ci_hi": float("nan"),
            "diff_ci_lo": float("nan"),
            "diff_ci_hi": float("nan"),
        })
        return results

    # 大方向 AUROC: large 样本 anomaly_score 是否高于 small
    large_auroc = float(roc_auc_score(y_direction, valid_scores))

    # 小方向 AUROC: small 样本 anomaly_score 是否低于 large（对称）
    small_auroc = 1.0 - large_auroc

    # Bootstrap CI for large direction
    ci_lo_large, ci_hi_large = bootstrap_auroc_ci(
        y_direction, valid_scores, n_boot=N_BOOTSTRAP, seed=RANDOM_STATE
    )

    # 方向差 = large_auroc - small_auroc = 2*large_auroc - 1
    direction_diff = large_auroc - small_auroc

    # Bootstrap CI for direction diff
    rng = np.random.default_rng(RANDOM_STATE)
    boot_diffs = []
    for _ in range(N_BOOTSTRAP):
        idx = rng.integers(0, n, size=n)
        yt = y_direction[idx]
        ys = valid_scores[idx]
        if len(np.unique(yt)) < 2:
            continue
        a = float(roc_auc_score(yt, ys))
        boot_diffs.append(2 * a - 1)
    if len(boot_diffs) >= 10:
        diff_ci_lo = float(np.percentile(boot_diffs, 2.5))
        diff_ci_hi = float(np.percentile(boot_diffs, 97.5))
    else:
        diff_ci_lo = diff_ci_hi = float("nan")

    results.update({
        "large_direction_auroc": round(large_auroc, 4),
        "small_direction_auroc": round(small_auroc, 4),
        "direction_diff": round(direction_diff, 4),
        "large_ci_lo": round(ci_lo_large, 4) if not np.isnan(ci_lo_large) else "nan",
        "large_ci_hi": round(ci_hi_large, 4) if not np.isnan(ci_hi_large) else "nan",
        "diff_ci_lo": round(diff_ci_lo, 4) if not np.isnan(diff_ci_lo) else "nan",
        "diff_ci_hi": round(diff_ci_hi, 4) if not np.isnan(diff_ci_hi) else "nan",
    })
    return results


# ── 训练 + 推理 ──────────────────────────────────────────────────────────────


def set_seed(seed=42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def train_ae_on_ham_nv(nv_ids, ham_root, device, epochs, num_workers, smoke=False):
    """训 AE on HAM-NV (nv_ids 列表), 返回 model。"""
    transform = transforms.Compose([
        transforms.Resize((INPUT_SIZE, INPUT_SIZE)),
        transforms.Grayscale(num_output_channels=1),
        transforms.ToTensor(),
        transforms.Normalize(mean=(0.5,), std=(0.5,)),
    ])
    if smoke:
        # smoke 模式: 只取 64 张, 1 epoch
        nv_ids = nv_ids[:64]
        epochs = 1
        num_workers = 0

    ds = HAMNVDataset(nv_ids, ham_root, transform=transform)
    if len(ds) == 0:
        raise RuntimeError("[train_ae] HAMNVDataset is empty, check ham_root / image_ids")
    loader = DataLoader(
        ds,
        batch_size=OFFICIAL_BS,
        shuffle=True,
        num_workers=num_workers,
        multiprocessing_context="spawn" if num_workers > 0 else None,
        pin_memory=False,
        drop_last=True,
    )
    model = AENet(in_c=1, base_c=16, latent=OFFICIAL_LATENT).to(device)
    optimizer = optim.Adam(model.parameters(), lr=OFFICIAL_LR, weight_decay=0)

    t0 = time.time()
    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        n_batches = 0
        for imgs, _ in loader:
            imgs = imgs.to(device)
            optimizer.zero_grad()
            recon = model(imgs)
            loss = torch.mean((imgs - recon) ** 2)  # 官方 L2 mean
            if torch.isnan(loss) or torch.isinf(loss):
                continue
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            n_batches += 1
        avg = total_loss / max(n_batches, 1)
        elapsed = time.time() - t0
        print(f"  [train] epoch {epoch}/{epochs} | loss={avg:.5f} | {elapsed:.0f}s")

    print(f"[train_ae] done. total={time.time()-t0:.0f}s, n_train={len(ds)}")
    return model


def infer_anomaly_scores(model, all_ids, ham_root, device, num_workers, smoke=False):
    """对所有 NV 图推理 anomaly_score = mean pixel-level L2。"""
    transform = transforms.Compose([
        transforms.Resize((INPUT_SIZE, INPUT_SIZE)),
        transforms.Grayscale(num_output_channels=1),
        transforms.ToTensor(),
        transforms.Normalize(mean=(0.5,), std=(0.5,)),
    ])
    if smoke:
        all_ids = all_ids[:64]
        num_workers = 0

    ds = HAMNVDataset(all_ids, ham_root, transform=transform)
    loader = DataLoader(
        ds,
        batch_size=128,
        shuffle=False,
        num_workers=num_workers,
        multiprocessing_context="spawn" if num_workers > 0 else None,
        pin_memory=False,
    )
    model.eval()
    scores_dict = {}
    with torch.no_grad():
        for imgs, iids in loader:
            imgs = imgs.to(device)
            recon = model(imgs)
            scores = torch.mean((imgs - recon) ** 2, dim=[1, 2, 3])
            for iid, s in zip(iids, scores.cpu().tolist()):
                scores_dict[iid] = s
    print(f"[infer] computed anomaly_scores for {len(scores_dict)} images")
    return scores_dict


# ── R9 判读 ──────────────────────────────────────────────────────────────────


def r9_verdict(auroc_results, mde=MDE_DIRECTION_DIFF):
    """依 G5_DESIGN §S5-07 §5 三分流判读。"""
    large_auroc = auroc_results.get("large_direction_auroc", float("nan"))
    diff = auroc_results.get("direction_diff", float("nan"))
    large_ci_lo = auroc_results.get("large_ci_lo", float("nan"))
    diff_ci_lo = auroc_results.get("diff_ci_lo", float("nan"))
    diff_ci_hi = auroc_results.get("diff_ci_hi", float("nan"))

    if any(x == "nan" or (isinstance(x, float) and np.isnan(x))
           for x in [large_auroc, diff, large_ci_lo, diff_ci_lo, diff_ci_hi]):
        return "GRAY", "CI/AUROC 含 nan，功效不足，需扩规模"

    # CI 宽度判断: 差 CI 宽度 > 0.4 视为 GRAY（G5 小样本）
    diff_ci_width = float(diff_ci_hi) - float(diff_ci_lo)
    if diff_ci_width > 0.4:
        return "GRAY", f"diff CI 宽={diff_ci_width:.3f}>0.4，功效不足，需扩规模"

    large_ci_lo = float(large_ci_lo)
    diff = float(diff)
    diff_ci_lo = float(diff_ci_lo)
    diff_ci_hi = float(diff_ci_hi)

    # PASS: large CI 下界 > 0.5 且 diff >= MDE 且 diff CI 不含 0
    if large_ci_lo > 0.5 and diff >= mde and diff_ci_lo > 0:
        return "PASS", f"large CI_lo={large_ci_lo:.3f}>0.5, diff={diff:.3f}>={mde}, diff_CI=[{diff_ci_lo:.3f},{diff_ci_hi:.3f}] 不含 0 → 相图有跨域结构 → 维持 MAIN"

    # KILL: large CI 含/低于 0.5 且 diff CI 含 0
    if large_ci_lo <= 0.5 and diff_ci_lo <= 0:
        return "KILL", f"large CI_lo={large_ci_lo:.3f}<=0.5 且 diff CI 含 0 → 无跨域结构 → 降 FINDINGS"

    return "GRAY", f"大/小方向有分离但 diff={diff:.3f}<{mde} 或 CI 宽，R9 待扩规模"


# ── 写工具 ───────────────────────────────────────────────────────────────────


def _write_csv(path, rows, fieldnames=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
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


# ── 主流程 ───────────────────────────────────────────────────────────────────


def main(args):
    set_seed(RANDOM_STATE)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    state_path = RESULTS_DIR / "S5A07_state.json"

    # GPU 可用性检查
    if torch.cuda.is_available() and not args.cpu:
        device = torch.device(f"cuda:{args.gpu}")
        print(f"[S5A07] device: {device} ({torch.cuda.get_device_name(args.gpu)})")
    else:
        device = torch.device("cpu")
        print("[S5A07] WARNING: CUDA 不可用，退化到 CPU（训练会较慢）")

    _update_state(state_path, status="running", start_time=time.strftime("%Y-%m-%dT%H:%M:%S"),
                  device=str(device), smoke=args.smoke)

    # ── Step 1: 读 HAM10000 metadata，过滤 NV ─────────────────────────────
    print("\n[Step 1] 读 HAM10000 metadata，过滤 dx==nv")
    import csv as _csv
    nv_ids = []
    all_ids = []
    with open(HAM_META, newline="", encoding="utf-8") as f:
        for row in _csv.DictReader(f):
            all_ids.append(row["image_id"])
            if row["dx"].strip().lower() == "nv":
                nv_ids.append(row["image_id"])
    print(f"  HAM10000 total: {len(all_ids)}, NV: {len(nv_ids)}")
    _update_state(state_path, n_total=len(all_ids), n_nv=len(nv_ids))

    # ── Step 2: 计算 GT mask lesion 特征 ────────────────────────────────────
    print("\n[Step 2] 计算 GT lesion mask 特征 (lesion_area_px / relative_size)")
    if not HAM_MASK_DIR.exists():
        raise FileNotFoundError(
            f"GT mask 目录不存在: {HAM_MASK_DIR}\n"
            f"请确认 datasets.json 路径: data/external/ham10000/HAM10000_segmentations_lesion_tschandl/"
        )
    # G5 只用 NV 样本（正常子集训 AE + 全量 NV 推理）
    features_dict = compute_lesion_features(nv_ids, HAM_MASK_DIR)
    valid_feat = {k: v for k, v in features_dict.items()
                  if not np.isnan(v["relative_size"])}
    print(f"  NV 有效 mask: {len(valid_feat)}/{len(nv_ids)}")

    # 保存 lesion_features.csv
    feat_rows = [
        {"image_id": iid, **fv}
        for iid, fv in features_dict.items()
    ]
    _write_csv(RESULTS_DIR / "S5A07_lesion_features.csv", feat_rows)
    _update_state(state_path, n_nv_with_mask=len(valid_feat))

    # ── Step 3: 训 AE on HAM-NV ──────────────────────────────────────────────
    print(f"\n[Step 3] 训 AE on HAM-NV (epochs={1 if args.smoke else G5_EPOCHS})")
    model = train_ae_on_ham_nv(
        nv_ids, HAM_ROOT, device,
        epochs=G5_EPOCHS,
        num_workers=args.num_workers,
        smoke=args.smoke,
    )
    _update_state(state_path, ae_train_done=True, ae_epochs=G5_EPOCHS)

    # ── Step 4: 推理 anomaly_score ────────────────────────────────────────────
    print("\n[Step 4] 推理 anomaly_score (全量 NV)")
    scores_dict = infer_anomaly_scores(
        model, nv_ids, HAM_ROOT, device,
        num_workers=args.num_workers,
        smoke=args.smoke,
    )
    # 保存 anomaly_scores.csv
    score_rows = [{"image_id": iid, "anomaly_score": s}
                  for iid, s in scores_dict.items()]
    _write_csv(RESULTS_DIR / "S5A07_anomaly_scores.csv", score_rows)
    _update_state(state_path, n_scored=len(scores_dict))

    # ── Step 5: 方向化 AUROC ─────────────────────────────────────────────────
    print("\n[Step 5] 方向化 AUROC (large vs small relative_size)")
    auroc_results = directional_auroc(nv_ids, scores_dict, features_dict)

    # R9 判读
    verdict, verdict_msg = r9_verdict(auroc_results)
    auroc_results["r9_verdict"] = verdict
    auroc_results["r9_msg"] = verdict_msg
    auroc_results["mde_threshold"] = MDE_DIRECTION_DIFF
    auroc_results["g5_epochs"] = G5_EPOCHS
    auroc_results["note"] = (
        "G5 证伪 5-epoch AE，非全量复现；anomaly_score 仅用于相对排序；"
        "size 特征来自官方 GT lesion mask（非 proxy）"
    )

    # 保存 failure_boundary.csv
    _write_csv(RESULTS_DIR / "S5A07_failure_boundary.csv", [auroc_results])

    # ── 控制台判读 ────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"[S5A07] R9 判读: {verdict}")
    print(f"  {verdict_msg}")
    print(f"  large_auroc={auroc_results.get('large_direction_auroc')} "
          f"CI=[{auroc_results.get('large_ci_lo')},{auroc_results.get('large_ci_hi')}]")
    print(f"  direction_diff={auroc_results.get('direction_diff')} "
          f"CI=[{auroc_results.get('diff_ci_lo')},{auroc_results.get('diff_ci_hi')}]")
    print(f"  MDE={MDE_DIRECTION_DIFF}, n_valid={auroc_results.get('n_valid')}")
    print("=" * 60)

    _update_state(state_path, status="done",
                  end_time=time.strftime("%Y-%m-%dT%H:%M:%S"),
                  r9_verdict=verdict,
                  large_auroc=auroc_results.get("large_direction_auroc"),
                  direction_diff=auroc_results.get("direction_diff"))
    print("[S5A07] 完成。结果在 killshots/run-007/results/")


def parse_args():
    parser = argparse.ArgumentParser(
        description="S5-07 G5 killshot: AD 大病灶失效边界 GPU 步"
    )
    parser.add_argument("--gpu", type=int, default=0, help="CUDA device id")
    parser.add_argument("--cpu", action="store_true", help="强制 CPU 模式（调试用）")
    parser.add_argument("--smoke", action="store_true",
                        help="烟测模式: 64 samples, 1 epoch（<5min 验算子）")
    parser.add_argument("--num-workers", type=int, default=4,
                        help="DataLoader num_workers（Windows 建议 >=2，spawn）")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(args)
