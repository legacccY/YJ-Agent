"""
extract_frozen_feats.py
服务: ArtiOODBench Gate1 R3（OOD 方法特征输入）
lever: L3 重排命门

【做什么】
用 TorchXRayVision DenseNet121-res224 frozen encoder 提取倒数第二层特征（N=1024），
存 .npy + manifest CSV。供 l3_ood_rerank.py 直接读取。

【模型】
  import torchxrayvision as xrv
  model = xrv.models.DenseNet(weights="densenet121-res224-all")
  倒二层 = features before final classifier（global average pool 后 1024 维）

【数据集】
  - NIH ChestX-ray14 (CXR, ID=local機構)
  - VinDr-CXR (CXR, OOD=跨機構)
  - BraTS2021 normal / tumor (Brain MRI)
  - HAM10000 NV / non-NV (Dermoscopy)
  - Fitzpatrick17k NV (Dermoscopy, P4b OOD, nevus* label, ~485 张)
  - PAD-UFES NEV (Dermoscopy smartphone, P4c OOD, diagnostic=NEV, 244 张)

【输出】
  results/feats/<dataset_name>.npy   (N, 1024)
  results/feats/manifest.csv  (path, dataset, split, label, modality)

【运行】
  # smoke (每集 8 张, CPU)
  python extract_frozen_feats.py --smoke 8 --device cpu

  # 全量 (GPU)
  python extract_frozen_feats.py
"""

import argparse
import csv
import io
import os
import random
import sys
from pathlib import Path

import numpy as np

# Windows GBK 终端安全
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ============================================================
# 路径常量（来自 datasets.json）
# ============================================================
NIH_DIR = Path(
    "D:/YJ-Agent/project/meeting/Med-NCA/NCA-JEPA/data/nih_cxr14/images-224/images-224"
)
VINDR_DIR = Path("D:/YJ-Agent/data/external/vindr_cxr")
BRATS_DIR = Path("D:/YJ-Agent/project/meeting/MedAD-FailMap/data/BraTS2021")
HAM_DIR = Path("D:/YJ-Agent/data/external/ham10000")
# 新增 cross-source 数据集
RSNA_DIR = Path("D:/YJ-Agent/data/external/medianomaly/RSNA")
BRAINTUMOR_DIR = Path("D:/YJ-Agent/data/external/medianomaly/BrainTumor")
ISIC2020_DIR = Path("D:/YJ-Agent/data/raw/isic2020")
ISIC2020_GT_CSV = ISIC2020_DIR / "ISIC_2020_Training_GroundTruth_v2.csv"
ISIC2020_IMG_DIR = ISIC2020_DIR / "train-image" / "image"
# P4b: fitzpatrick17k NV（cross-source，与 HAM_NV 配对）
FITZPATRICK_DIR = Path("D:/YJ-Agent/data/raw/fitzpatrick17k")
FITZPATRICK_IMG_DIR = FITZPATRICK_DIR / "images"
FITZPATRICK_CSV = FITZPATRICK_DIR / "fitzpatrick17k.csv"
# P4c: PAD-UFES（cross-source，smartphone derm，与 ISIC2020_benign 配对）
PAD_UFES_DIR = Path("D:/YJ-Agent/data/external/pad_ufes")
PAD_UFES_IMG_DIR = PAD_UFES_DIR / "PAD-UFES-20" / "Dataset"
PAD_UFES_META_CSV = PAD_UFES_DIR / "metadata.csv"

OUT_DIR = Path(__file__).resolve().parent.parent / "results"
FEATS_DIR = OUT_DIR / "feats"
MANIFEST_CSV = FEATS_DIR / "manifest.csv"

TARGET_SIZE = 224
BATCH_SIZE = 32
SEED = 42


# ============================================================
# TorchXRayVision import（带清晰错误提示）
# ============================================================
def load_xrv_model(device: str):
    """
    加载 TorchXRayVision DenseNet121-res224 frozen encoder。
    返回 (model, preprocess_fn) 或抛 ImportError。
    """
    try:
        import torchxrayvision as xrv
    except ImportError:
        print(
            "[ERROR] torchxrayvision 未安装。请运行:\n"
            "  pip install torchxrayvision\n"
            "# TODO: 安装后重跑 extract_frozen_feats.py",
            file=sys.stderr,
        )
        raise

    try:
        import torch
    except ImportError:
        print("[ERROR] torch 未安装。", file=sys.stderr)
        raise

    print(f"[XRV] loading DenseNet121-res224-all on {device}...")
    model = xrv.models.DenseNet(weights="densenet121-res224-all")
    model.eval()
    model.to(device)
    # 冻结参数
    for p in model.parameters():
        p.requires_grad = False

    return model


def preprocess_xrv(arr: np.ndarray) -> "torch.Tensor":
    """
    TorchXRayVision 官方预处理：uint8 [0,255] -> float32 [-1024,1024]，单通道。
    返回 shape (1, H, W) float32 tensor。
    """
    import torch
    img = arr.astype(np.float32)
    # xrv normalize: (img / 255 * 2048) - 1024
    img = (img / 255.0) * 2048.0 - 1024.0
    return torch.tensor(img, dtype=torch.float32).unsqueeze(0)  # (1, H, W)


def extract_feats_and_logits(model, img_arrays: list, device: str):
    """
    img_arrays: list of HxW uint8 numpy arrays（已 resize 到 224²）
    返回 (feats_np, logits_np)：
      feats_np:  (N, 1024) float32 -- 倒数第二层 GAP 特征
      logits_np: (N, 18)   float32 -- DenseNet 分类头 raw pre-sigmoid logits
                 (TorchXRayVision densenet121-res224-all 有 18 个病理标签)

    取法：model.features2(x) -> (1, 1024) GAP 特征
          model.classifier(feat) -> (1, 18) raw logits（pre-sigmoid）
    注意：model.forward() 可能对某些权重文件额外做 sigmoid/op_norm；
          这里直接用 features2 + classifier 拿到 raw logits，与 Energy/MSP 计算一致。

    跨域限制（诚实注释）：
      DenseNet 是 CXR-only 模型，对 MRI/dermoscopy 输入只有 features2 有意义
      (迁移特征)，classifier logits 对非 CXR 图像无病理语义。
      logit-based 方法 (MSP/ODIN/Energy/GradNorm) 在非 CXR 模态预期过不了
      PR-F3 准入门 (全<0.6)，属设计预期，不是 bug。
      feature-based 方法 (MDS/KNN/ViM) 跨域尚可能有效。
    """
    import torch

    feats_list = []
    logits_list = []
    for arr in img_arrays:
        t = preprocess_xrv(arr).unsqueeze(0).to(device)  # (1,1,H,W)
        with torch.no_grad():
            feat = model.features2(t)          # (1, 1024) - GAP 后特征
            logit = model.classifier(feat)     # (1, 18)  - raw pre-sigmoid logits
        feats_list.append(feat.cpu().numpy()[0])    # (1024,)
        logits_list.append(logit.cpu().numpy()[0])  # (18,)

    feats_np = np.array(feats_list, dtype=np.float32)   # (N, 1024)
    logits_np = np.array(logits_list, dtype=np.float32) # (N, 18)
    return feats_np, logits_np


# ============================================================
# 图像加载（224² 灰度）
# ============================================================
def load_image_gray224(path: Path, size: int = TARGET_SIZE) -> np.ndarray:
    from PIL import Image
    img = Image.open(path).convert("L")
    if img.size != (size, size):
        img = img.resize((size, size), Image.BILINEAR)
    return np.array(img, dtype=np.uint8)


def _glob_images(d: Path, exts=(".png", ".jpg", ".jpeg")):
    if not d.exists():
        return []
    return sorted([p for p in d.iterdir() if p.suffix.lower() in exts])


# ============================================================
# 各数据集路径收集
# 涵盖 4 个 cross-source 对 + within-source 对照
# ============================================================
def collect_datasets(n_sample: int, seed: int = SEED):
    """
    返回 dict: dataset_name -> {paths, modality, split, label, pair_role}
    pair_role: 'cross_source_id' | 'cross_source_ood' | 'within_source_id' | 'within_source_ood'

    Cross-source 对（A-1/A-2/A-4 主战场，对齐 ACCEPTANCE v2）：
      P1 CXR:   NIH (ID)        vs VinDr (OOD)
      P2 CXR:   NIH (ID)        vs RSNA_normal (OOD)
      P3 MRI:   BraTS_normal (ID) vs BrainTumor_normal (OOD)
      P4 derm:  HAM_NV (ID)     vs ISIC2020_benign (OOD)
      P4b derm: HAM_NV (ID)     vs Fitzpatrick_NV (OOD, nevus* ~485 张)
      P4c derm: ISIC2020_benign (ID) vs PAD_UFES_NEV (OOD, smartphone, 244 张)

    Within-source 对照（附录 robustness，subset='within_source_control'）：
      BraTS normal vs tumor
      HAM NV vs nonNV
      RSNA normal vs pneumonia（test["1"]）
    """
    rng = random.Random(seed)

    def sample(paths, n):
        paths = list(paths)
        rng.shuffle(paths)
        return paths[:n] if n and n < len(paths) else paths

    def _add(name, paths, modality, label, pair_role, split="all"):
        if paths:
            datasets[name] = {
                "paths": sample(paths, n_sample),
                "modality": modality, "split": split,
                "label": label, "pair_role": pair_role,
            }
        else:
            print(f"[WARN] no images for {name}", file=sys.stderr)

    datasets = {}

    # ---- P1 / P2: NIH CXR (cross-source ID) ----
    nih_files = _glob_images(NIH_DIR)
    if nih_files:
        datasets["NIH_CXR14"] = {
            "paths": sample(nih_files, n_sample),
            "modality": "CXR", "split": "all",
            "label": "normal", "pair_role": "cross_source_id",
        }
    else:
        print(f"[WARN] NIH not found: {NIH_DIR}", file=sys.stderr)

    # ---- P1 OOD: VinDr CXR ----
    vindr_files = _glob_images(VINDR_DIR / "test") + _glob_images(VINDR_DIR / "train")
    _add("VinDr_CXR", vindr_files, "CXR", "ood", "cross_source_ood")

    # ---- P2 OOD: RSNA normal (class 0) ----
    rsna_json = RSNA_DIR / "data.json"
    if rsna_json.exists():
        import json as _json
        rsna_data = _json.loads(rsna_json.read_text(encoding="utf-8"))
        rsna_normal_names = (rsna_data.get("train", {}).get("0", []) +
                             rsna_data.get("test", {}).get("0", []))
        rsna_img_dir = RSNA_DIR / "images"
        rsna_normal_paths = [rsna_img_dir / n for n in rsna_normal_names
                             if (rsna_img_dir / n).exists()]
        _add("RSNA_normal", rsna_normal_paths, "CXR", "normal", "cross_source_ood")
        # within-source control: RSNA normal vs pneumonia (test["1"])
        rsna_pneumonia_names = rsna_data.get("test", {}).get("1", [])
        rsna_pneumonia_paths = [rsna_img_dir / n for n in rsna_pneumonia_names
                                if (rsna_img_dir / n).exists()]
        _add("RSNA_pneumonia", rsna_pneumonia_paths, "CXR", "anomaly", "within_source_ood")
    else:
        print(f"[WARN] RSNA data.json not found: {rsna_json}", file=sys.stderr)

    # ---- P3 ID: BraTS normal ----
    norm_dir = BRATS_DIR / "test" / "normal"
    if not norm_dir.exists():
        norm_dir = BRATS_DIR / "normal"
    bnorm = _glob_images(norm_dir)
    _add("BraTS_normal", bnorm, "BrainMRI", "normal", "cross_source_id", split="test")

    # ---- P3 OOD: BrainTumor normal (class 0, different scanner/source) ----
    bt_json = BRAINTUMOR_DIR / "data.json"
    if bt_json.exists():
        import json as _json
        bt_data = _json.loads(bt_json.read_text(encoding="utf-8"))
        bt_normal_names = (bt_data.get("train", {}).get("0", []) +
                           bt_data.get("test", {}).get("0", []))
        bt_img_dir = BRAINTUMOR_DIR / "images"
        bt_normal_paths = [bt_img_dir / n for n in bt_normal_names
                           if (bt_img_dir / n).exists()]
        _add("BrainTumor_normal", bt_normal_paths, "BrainMRI", "normal", "cross_source_ood")
        # within-source control: BrainTumor normal vs tumor (class 1)
        bt_tumor_names = bt_data.get("test", {}).get("1", [])
        bt_tumor_paths = [bt_img_dir / n for n in bt_tumor_names
                          if (bt_img_dir / n).exists()]
        _add("BrainTumor_tumor", bt_tumor_paths, "BrainMRI", "anomaly", "within_source_ood")
    else:
        print(f"[WARN] BrainTumor data.json not found: {bt_json}", file=sys.stderr)

    # within-source control: BraTS tumor
    tumor_dir = BRATS_DIR / "test" / "tumor"
    if not tumor_dir.exists():
        tumor_dir = BRATS_DIR / "tumor"
    btumor = _glob_images(tumor_dir)
    _add("BraTS_tumor", btumor, "BrainMRI", "anomaly", "within_source_ood", split="test")

    # ---- P4 ID: HAM10000 NV ----
    meta_path = HAM_DIR / "HAM10000_metadata.csv"
    if not meta_path.exists():
        meta_path = HAM_DIR / "metadata.csv"
    if meta_path.exists():
        nv_ids, nonnv_ids = [], []
        with open(meta_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                dx = row.get("dx", "").strip().lower()
                img_id = row.get("image_id", "").strip()
                (nv_ids if dx == "nv" else nonnv_ids).append(img_id)

        def ids_to_paths(ids):
            paths = []
            for img_id in ids:
                for part in ["HAM10000_images_part_1", "HAM10000_images_part_2"]:
                    p = HAM_DIR / part / f"{img_id}.jpg"
                    if p.exists():
                        paths.append(p)
                        break
            return paths

        nv_paths = ids_to_paths(nv_ids)
        nonnv_paths = ids_to_paths(nonnv_ids)
        _add("HAM_NV", nv_paths, "Dermoscopy", "normal", "cross_source_id")
        _add("HAM_nonNV", nonnv_paths, "Dermoscopy", "anomaly", "within_source_ood")
    else:
        print(f"[WARN] HAM metadata not found: {meta_path}", file=sys.stderr)

    # ---- P4 OOD: ISIC2020 benign（跨源 derm，not HAM）----
    if ISIC2020_GT_CSV.exists():
        benign_ids = []
        with open(ISIC2020_GT_CSV, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("benign_malignant", "") == "benign":
                    benign_ids.append(row["image_name"])
        isic_paths = [ISIC2020_IMG_DIR / (img_id + ".jpg") for img_id in benign_ids
                      if (ISIC2020_IMG_DIR / (img_id + ".jpg")).exists()]
        _add("ISIC2020_benign", isic_paths, "Dermoscopy", "normal", "cross_source_ood")
    else:
        print(f"[WARN] ISIC2020 GT CSV not found: {ISIC2020_GT_CSV}", file=sys.stderr)

    # ---- P4b OOD: fitzpatrick17k NV（cross-source，与 HAM_NV 配对）----
    # 筛 label 包含 'nevus'（nevocytic/halo/congenital/becker/sebaceous/epidermal nevus
    # 等，共 ~485 张）。不用 three_partition_label='benign' 避免混入非痣良性皮损。
    if FITZPATRICK_CSV.exists():
        fitz_nv_paths = []
        with open(FITZPATRICK_CSV, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                label_lower = row.get("label", "").lower()
                if "nevus" in label_lower:
                    md5 = row["md5hash"].strip()
                    p = FITZPATRICK_IMG_DIR / f"{md5}.jpg"
                    if p.exists():
                        fitz_nv_paths.append(p)
        _add("Fitzpatrick_NV", fitz_nv_paths, "Dermoscopy", "normal", "cross_source_ood")
    else:
        print(f"[WARN] fitzpatrick17k CSV not found: {FITZPATRICK_CSV}", file=sys.stderr)

    # ---- P4c OOD: PAD-UFES NEV（cross-source smartphone derm，与 ISIC2020_benign 配对）----
    # 只取 diagnostic=NEV（痣），共 244 张，全部使用（不足 500 不强制 500）。
    if PAD_UFES_META_CSV.exists():
        pad_nev_paths = []
        with open(PAD_UFES_META_CSV, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("diagnostic", "").strip() == "NEV":
                    p = PAD_UFES_IMG_DIR / row["img_id"].strip()
                    if p.exists():
                        pad_nev_paths.append(p)
        # PAD-UFES NEV n=244，全量提取（不足 500 不 pad）
        # n_sample 传 None 的 sample() 会原样返回全部；这里绕过 sample() 直接存
        if pad_nev_paths:
            datasets["PAD_UFES_NEV"] = {
                "paths": pad_nev_paths,  # 244 张，不再随机截断
                "modality": "Dermoscopy", "split": "all",
                "label": "normal", "pair_role": "cross_source_ood",
            }
        else:
            print(f"[WARN] no PAD-UFES NEV images found in {PAD_UFES_IMG_DIR}", file=sys.stderr)
    else:
        print(f"[WARN] PAD-UFES metadata CSV not found: {PAD_UFES_META_CSV}", file=sys.stderr)

    return datasets


# ============================================================
# 主逻辑
# ============================================================
def main(smoke_n: int = 0, device: str = "cuda"):
    import importlib.util
    n_sample = smoke_n if smoke_n > 0 else 500

    FEATS_DIR.mkdir(parents=True, exist_ok=True)

    # 检查 torchxrayvision
    if importlib.util.find_spec("torchxrayvision") is None:
        print(
            "[ERROR] torchxrayvision 未安装。请先运行:\n"
            "  pip install torchxrayvision\n"
            "# TODO: 安装后重跑 extract_frozen_feats.py",
            file=sys.stderr,
        )
        sys.exit(1)

    import torch
    if device == "cuda" and not torch.cuda.is_available():
        print("[WARN] CUDA 不可用，fallback 到 CPU")
        device = "cpu"

    model = load_xrv_model(device)

    datasets = collect_datasets(n_sample)
    if not datasets:
        print("[ERROR] 没有找到任何数据集，请检查路径。", file=sys.stderr)
        sys.exit(1)

    manifest_rows = []
    for name, info in datasets.items():
        paths = info["paths"]
        modality = info["modality"]
        split = info["split"]
        label = info["label"]
        pair_role = info.get("pair_role", "unknown")

        print(f"\n[{name}] n={len(paths)}, modality={modality}, label={label}, role={pair_role}")
        if not paths:
            print(f"  [SKIP] no images")
            continue

        all_feats = []
        all_logits = []
        for i in range(0, len(paths), BATCH_SIZE):
            batch_paths = paths[i: i + BATCH_SIZE]
            imgs = []
            valid_paths = []
            for p in batch_paths:
                try:
                    imgs.append(load_image_gray224(Path(p)))
                    valid_paths.append(str(p))
                except Exception as e:
                    print(f"  [WARN] skip {Path(p).name}: {e}", file=sys.stderr)

            if not imgs:
                continue

            # 同时提取 1024 维特征 + 18 维 raw logits
            batch_feats, batch_logits = extract_feats_and_logits(model, imgs, device)
            all_feats.append(batch_feats)
            all_logits.append(batch_logits)

            for path in valid_paths:
                manifest_rows.append({
                    "path": path,
                    "dataset": name,
                    "modality": modality,
                    "split": split,
                    "label": label,
                    "pair_role": pair_role,
                })

            if (i // BATCH_SIZE + 1) % 5 == 0 or i == 0:
                print(f"  processed {min(i + BATCH_SIZE, len(paths))}/{len(paths)}")

        if not all_feats:
            print(f"  [SKIP] {name}: no valid features extracted")
            continue

        feats_np = np.concatenate(all_feats, axis=0)    # (N, 1024)
        logits_np = np.concatenate(all_logits, axis=0)  # (N, 18)

        # 存特征 npy
        npy_feats = FEATS_DIR / f"{name}.npy"
        np.save(npy_feats, feats_np)
        # 存 logits npy（文件名加 _logits 后缀）
        npy_logits = FEATS_DIR / f"{name}_logits.npy"
        np.save(npy_logits, logits_np)
        print(f"  feats  {feats_np.shape} -> {npy_feats}")
        print(f"  logits {logits_np.shape} -> {npy_logits}")

    # manifest CSV
    fieldnames = ["path", "dataset", "modality", "split", "label", "pair_role"]
    with open(MANIFEST_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(manifest_rows)
    print(f"\n[manifest] -> {MANIFEST_CSV}  (n={len(manifest_rows)} rows)")
    print("[NOTE] feats: <dataset>.npy (N,1024), logits: <dataset>_logits.npy (N,18 pre-sigmoid)")

    if smoke_n > 0:
        print(f"\n[SMOKE] n={smoke_n}/dataset，验结构 OK。全量去掉 --smoke。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract TorchXRayVision frozen features")
    parser.add_argument("--smoke", type=int, default=0,
                        help="smoke: n per dataset (0=full)")
    parser.add_argument("--device", type=str, default="cuda",
                        help="cuda | cpu")
    args = parser.parse_args()
    main(smoke_n=args.smoke, device=args.device)
