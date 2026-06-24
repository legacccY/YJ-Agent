"""
download_psfhs.py
=================
用途：从 Zenodo 10969427 下载 PSFHS 数据集（耻骨联合+胎头超声分割）并解压到
      D:/YJ-Agent/project/meeting/_run011_pilot/data/PSFHS/

怎么跑（主线先跑这个）：
    python download_psfhs.py
    python download_psfhs.py --dest D:/YJ-Agent/project/meeting/_run011_pilot/data/PSFHS

Zenodo 记录：https://zenodo.org/records/10969427
预期内容：image_mha/ + label_mha/（共 1358 例 .mha 文件）
"""

import argparse
import os
import sys
import zipfile
import urllib.request
from pathlib import Path

# ---------- Zenodo 文件清单（手动列出，避免 API 依赖）---------
# 如果 Zenodo 下载链接变了，去 https://zenodo.org/records/10969427 看 Files 列表
ZENODO_FILES = [
    {
        "url": "https://zenodo.org/records/10969427/files/PSFHS.zip?download=1",
        "filename": "PSFHS.zip",
    }
]

# 备用：如果单 zip 不存在，可能分成 image/label 分开
ZENODO_FILES_ALT = [
    {
        "url": "https://zenodo.org/records/10969427/files/image_mha.zip?download=1",
        "filename": "image_mha.zip",
    },
    {
        "url": "https://zenodo.org/records/10969427/files/label_mha.zip?download=1",
        "filename": "label_mha.zip",
    },
]


def download_file(url: str, dest_path: Path) -> bool:
    """下载单个文件，返回是否成功。显示进度。"""
    if dest_path.exists():
        print(f"  [skip] {dest_path.name} 已存在，跳过下载")
        return True

    print(f"  [download] {url}")
    print(f"  -> {dest_path}")

    try:
        def _progress(block_num, block_size, total_size):
            if total_size > 0:
                pct = min(100, block_num * block_size * 100 // total_size)
                mb_done = block_num * block_size / 1024 / 1024
                mb_total = total_size / 1024 / 1024
                print(f"\r    {pct}%  {mb_done:.1f}/{mb_total:.1f} MB", end="", flush=True)

        urllib.request.urlretrieve(url, dest_path, reporthook=_progress)
        print()  # newline after progress
        return True
    except Exception as e:
        print(f"\n  [ERROR] 下载失败: {e}")
        if dest_path.exists():
            dest_path.unlink()
        return False


def extract_zip(zip_path: Path, dest_dir: Path) -> bool:
    """解压 zip 到 dest_dir。"""
    print(f"  [extract] {zip_path.name} -> {dest_dir}")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            print(f"    文件数: {len(names)}")
            zf.extractall(dest_dir)
        print(f"  [ok] 解压完成")
        return True
    except zipfile.BadZipFile as e:
        print(f"  [ERROR] zip 损坏: {e}")
        return False


def verify_structure(data_dir: Path) -> bool:
    """检查解压后目录结构是否符合预期。"""
    print("\n[verify] 检查目录结构...")

    # 可能的子目录名变体
    possible_image_dirs = ["image_mha", "images", "img"]
    possible_label_dirs = ["label_mha", "labels", "mask", "seg"]

    found_image = None
    found_label = None

    # 递归查找（Zenodo zip 有时带顶层目录）
    for p in data_dir.rglob("*"):
        if p.is_dir() and p.name in possible_image_dirs:
            found_image = p
        if p.is_dir() and p.name in possible_label_dirs:
            found_label = p

    if found_image is None or found_label is None:
        # 直接列出现有内容帮助诊断
        print("  [WARN] 未找到预期的 image_mha/ 或 label_mha/ 目录")
        print("  当前内容：")
        for p in data_dir.iterdir():
            print(f"    {p.relative_to(data_dir)}  ({'dir' if p.is_dir() else 'file'})")
        print("  -> 请手动确认目录结构，并在 dataset.py 中更新 IMAGE_DIR / LABEL_DIR 常量")
        return False

    # 数 .mha 文件
    img_count = len(list(found_image.glob("*.mha")))
    lbl_count = len(list(found_label.glob("*.mha")))
    print(f"  image_mha: {found_image}  ({img_count} 个 .mha)")
    print(f"  label_mha: {found_label}  ({lbl_count} 个 .mha)")

    if img_count == 0 or lbl_count == 0:
        print("  [ERROR] .mha 文件为 0，解压可能失败或格式不同")
        return False

    if img_count != lbl_count:
        print(f"  [WARN] image ({img_count}) != label ({lbl_count})，检查配对")

    print(f"  [ok] 结构验证通过，共 {img_count} 例")
    return True


def main():
    parser = argparse.ArgumentParser(description="下载 PSFHS Zenodo 数据集")
    parser.add_argument(
        "--dest",
        type=str,
        default=r"D:/YJ-Agent/project/meeting/_run011_pilot/data/PSFHS",
        help="下载解压目标目录",
    )
    parser.add_argument(
        "--keep_zip",
        action="store_true",
        default=False,
        help="保留下载的 zip 文件（默认解压后删除）",
    )
    args = parser.parse_args()

    data_dir = Path(args.dest)
    data_dir.mkdir(parents=True, exist_ok=True)
    print(f"[PSFHS downloader]")
    print(f"  目标目录: {data_dir}")

    # --- 尝试主要下载方案 ---
    success = False
    for finfo in ZENODO_FILES:
        zip_path = data_dir / finfo["filename"]
        ok = download_file(finfo["url"], zip_path)
        if ok:
            ok2 = extract_zip(zip_path, data_dir)
            if ok2:
                if not args.keep_zip:
                    zip_path.unlink()
                    print(f"  [rm] {zip_path.name} 已删除")
                success = True
                break
            else:
                # zip 损坏，删掉重试备用
                zip_path.unlink()

    # --- 备用：分两个 zip ---
    if not success:
        print("\n[fallback] 尝试分开下载 image_mha.zip + label_mha.zip ...")
        for finfo in ZENODO_FILES_ALT:
            zip_path = data_dir / finfo["filename"]
            ok = download_file(finfo["url"], zip_path)
            if ok:
                ok2 = extract_zip(zip_path, data_dir)
                if ok2:
                    if not args.keep_zip:
                        zip_path.unlink()
                else:
                    print(f"  [ERROR] 解压 {finfo['filename']} 失败")
            else:
                print(f"  [ERROR] 下载 {finfo['filename']} 失败")
                print("  -> 请手动从 https://zenodo.org/records/10969427 下载并解压到：")
                print(f"     {data_dir}")
                sys.exit(1)
        success = True

    # --- 验证 ---
    ok_struct = verify_structure(data_dir)
    if not ok_struct:
        print("\n[NOTE] 目录结构与预期不符。请检查后手动更新 dataset.py 中路径常量。")
        sys.exit(1)

    print("\n[done] PSFHS 数据准备完成")


if __name__ == "__main__":
    main()
