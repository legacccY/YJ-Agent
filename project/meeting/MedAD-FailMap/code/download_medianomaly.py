"""
download_medianomaly.py — MedIAnomaly Zenodo 数据下载 + 目录校验
服务: MedAD-FailMap Phase 0 数据前置

Zenodo 记录: https://zenodo.org/records/12677223
⚠️ 是【分集 tar.gz】不是单个 zip（核 Zenodo API 确认）：
  BraTS2021.tar.gz 70MB / BrainTumor 42MB / LAG 202MB / RSNA 568MB / VinCXR 620MB / Camelyon16 891MB
  (ISIC2018 不在此 Zenodo → 本地 HAM10000 NV 替代)

下载目标: project/meeting/MedAD-FailMap/data/
BraTS2021 解压后结构 (已验通)：
  data/BraTS2021/train/             <- 4211 正常切片
  data/BraTS2021/test/normal/       <- 828
  data/BraTS2021/test/tumor/        <- 1948
  data/BraTS2021/test/annotation/   <- 1948 像素 mask (pixel>0=肿瘤)

用法:
  python download_medianomaly.py --subset BraTS2021     # Phase 0 最小需求
  python download_medianomaly.py --subset all           # 全 6 集
  python download_medianomaly.py --verify-only --subset BraTS2021

依赖: requests, tarfile(标准库)
"""

import argparse
import sys
import tarfile
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ============================================================
# 常量（核 Zenodo API records/12677223 实测文件名）
# ============================================================
ZENODO_RECORD = "12677223"
_BASE = f"https://zenodo.org/api/records/{ZENODO_RECORD}/files"

DATASET_FILES = {
    "BraTS2021":  "BraTS2021.tar.gz",
    "BrainTumor": "BrainTumor.tar.gz",
    "LAG":        "LAG.tar.gz",
    "RSNA":       "RSNA.tar.gz",
    "VinCXR":     "VinCXR.tar.gz",
    "Camelyon16": "Camelyon16.tar.gz",
}

# 期望目录结构 + 最少图片数（sanity，仅 BraTS2021 有像素 mask）
EXPECTED_DIRS = {
    "BraTS2021": {
        "BraTS2021/train":           4000,
        "BraTS2021/test/normal":     800,
        "BraTS2021/test/tumor":      1800,
        "BraTS2021/test/annotation": 1800,
    },
}


def download_file(url, dest_path, chunk_size=1024 * 1024):
    if not HAS_REQUESTS:
        print("[error] requests 未安装: pip install requests")
        sys.exit(1)
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[download] {url}\n[download] -> {dest_path}")
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    done = 0
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done/1e6:.1f}/{total/1e6:.1f} MB ({done/total*100:.1f}%)", end="", flush=True)
    print(f"\n[download] complete ({done/1e6:.1f} MB)")
    return dest_path


def extract_tar(tar_path, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[extract] {tar_path} -> {out_dir}")
    with tarfile.open(tar_path, "r:gz") as tf:
        tf.extractall(out_dir)
    print("[extract] done")


def verify_structure(data_root, subset):
    data_root = Path(data_root)
    report, all_ok = [], True
    dirs = EXPECTED_DIRS.get(subset, {})
    if not dirs:
        report.append(f"[skip] {subset} 无预设校验项（仅 BraTS2021 有像素 mask 校验）")
        return True, report
    exts = {".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"}
    for rel_dir, min_c in dirs.items():
        abs_dir = data_root / rel_dir
        if not abs_dir.exists():
            report.append(f"[MISSING] {abs_dir}")
            all_ok = False
            continue
        count = sum(1 for p in abs_dir.iterdir() if p.suffix in exts)
        status = "OK" if count >= min_c else "WARN"
        if count < min_c:
            all_ok = False
        report.append(f"[{status}] {rel_dir}: {count} (min={min_c})")
    return all_ok, report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MedIAnomaly Zenodo 分集 tar.gz 下载 + 校验")
    _data = Path(__file__).resolve().parent.parent / "data"
    parser.add_argument("--subset", default="BraTS2021",
                        choices=list(DATASET_FILES) + ["all"])
    parser.add_argument("--data-dir", default=str(_data))
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--keep-tar", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    if args.verify_only:
        ok, report = verify_structure(data_dir, args.subset)
        for line in report:
            print(" ", line)
        print("[verify]", "PASS" if ok else "FAIL")
        sys.exit(0 if ok else 1)

    subsets = list(DATASET_FILES) if args.subset == "all" else [args.subset]
    for sub in subsets:
        fname = DATASET_FILES[sub]
        url = f"{_BASE}/{fname}/content"
        tar_path = data_dir / fname
        if not tar_path.exists():
            download_file(url, tar_path)
        else:
            print(f"[download] {tar_path} 已存在, 跳过")
        extract_tar(tar_path, data_dir)
        ok, report = verify_structure(data_dir, sub)
        for line in report:
            print(" ", line)
        if not args.keep_tar and tar_path.exists():
            tar_path.unlink()
            print(f"[clean] 删除 {tar_path}")
