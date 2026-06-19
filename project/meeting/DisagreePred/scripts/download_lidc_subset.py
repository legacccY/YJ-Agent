"""
download_lidc_subset.py — DisagreePred A1 子集下载脚本

服务项目：DisagreePred，lever = A1 扩样坐实（LIDC 子集 50→150 patient）
禁止：不在此脚本内执行 parse_lidc / 训练；不碰其他项目文件

目标：
  从 lidc_disagreement_dist.csv 按平衡策略选 patient，
  调用 NBIA REST API（免 auth 公开）下载 DICOM zip，解压到 LIDC_subset/，
  并配置 ~/.pylidcrc 供 pylidc 使用。

运行模式（--mode）：
  fresh   : 首次下载 ~50 patient（原始行为，--n_scans 50）
  extend  : 扩样模式（默认）—— 检测 dest_root 已有 patient → 跳过已下的
            → 从剩余候选按平衡策略再选 ~n_new 个新 patient
            → --dry_run 时只打印新 UID 列表 + 预计大小，不下载
            → 去掉 --dry_run 后执行真实下载

选 patient 策略：
  优先：同时含 k=4（全一致）和 k<4（分歧）cluster 的 scan → 保证正负样本
  不足时：按 disagree 比例补充 only-disagree / only-agree scan

NBIA 下载 API（免 auth，公开 collection LIDC-IDRI）：
  getImage: https://services.cancerimagingarchive.net/nbia-api/services/v1/getImage
            ?SeriesInstanceUID=<uid>  → 返回该 series DICOM zip

pylidc 期望目录结构：
  LIDC_subset/
    LIDC-IDRI-0001/     # patient_id
      <StudyInstanceUID>/
        <SeriesInstanceUID>/
          *.dcm

主线执行命令（扩样预览，不下载）：
  python project/meeting/DisagreePred/scripts/download_lidc_subset.py --mode extend --n_new 100 --dry_run

主线执行命令（确认后真实下载）：
  python project/meeting/DisagreePred/scripts/download_lidc_subset.py --mode extend --n_new 100

注意：脚本主逻辑 gate 在 __main__。写完只 py_compile，不在此自动下载。
"""

from __future__ import annotations

# ─── numpy monkey-patch（pylidc 0.2.3 用 np.int/float/bool/object）─────────
# numpy >= 1.24 移除这些别名，必须在 import pylidc 前打补丁
import numpy as np
np.int = int
np.float = float
np.bool = bool
np.object = object
# ─────────────────────────────────────────────────────────────────────────────

import argparse
import csv
import io
import os
import re
import shutil
import sys
import time
import zipfile
from collections import defaultdict
from pathlib import Path

import requests

# ─── 路径配置（真源：.portfolio/datasets.json lidc_idri）─────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DIST_CSV = PROJECT_DIR / "results" / "lidc_disagreement_dist.csv"

# 下载目标目录（pylidc 配置的 DICOM 根）
# parse_lidc.py 会读此目录；也与 .portfolio/datasets.json lidc_idri.local 对齐
LIDC_SUBSET_DIR = Path("D:/YJ-Agent/project/meeting/DisagreePred/data/LIDC_subset")

# pylidcrc 路径
PYLIDCRC_PATH = Path.home() / ".pylidcrc"

# NBIA REST API
NBIA_BASE_URL = "https://services.cancerimagingarchive.net/nbia-api/services/v1"
NBIA_GET_IMAGE_URL = f"{NBIA_BASE_URL}/getImage"

# 下载参数
DOWNLOAD_TIMEOUT = 300      # 秒，单个 series zip，CT 可达 100MB+
RETRY_ATTEMPTS = 3
RETRY_DELAY = 5             # 秒
CHUNK_SIZE = 1024 * 1024    # 1MB 流式 chunk


# ─────────────────────────────────────────────────────────────────────────────
# 1. 平衡采样：从 dist.csv 选 ~n_scans 个 patient
# ─────────────────────────────────────────────────────────────────────────────

def select_balanced_patients(dist_csv: Path, n_scans: int = 50,
                             exclude: set[str] | None = None) -> list[str]:
    """
    从 lidc_disagreement_dist.csv 按平衡策略选 patient list。

    策略：
      优先选同时含 k=4（agree=0）和 k<4（disagree=1）cluster 的 scan。
      优先组不足 n_scans 时，按 disagree 比例补充 only-disagree / only-agree。

    参数：
      exclude: 已下载 patient_id 集合，这些 patient 不再被选中（扩样用）

    返回排好序的 patient_id list（LIDC-IDRI-XXXX 格式）。
    """
    if not dist_csv.exists():
        raise FileNotFoundError(
            f"[select] dist.csv 不存在：{dist_csv}\n"
            "请先运行 lidc_disagreement_stats.py 生成分布统计。"
        )

    rows: list[dict] = []
    with open(str(dist_csv), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)

    if not rows:
        raise RuntimeError(f"[select] dist.csv 为空：{dist_csv}")

    exclude_set: set[str] = exclude if exclude is not None else set()

    # 统计每个 scan 的 cluster 情况（排除已下载）
    scan_has_agree: dict[str, bool] = defaultdict(bool)
    scan_has_disagree: dict[str, bool] = defaultdict(bool)
    scan_pids: set[str] = set()

    for r in rows:
        pid = r["scan_pid"]
        if pid in exclude_set:
            continue   # 跳过已下载
        scan_pids.add(pid)
        if r["disagree_binary"] == "0":
            scan_has_agree[pid] = True
        else:
            scan_has_disagree[pid] = True

    print(f"[select] dist.csv 候选（排除已下载 {len(exclude_set)} 个后）共 {len(scan_pids)} 个 scan")
    both = sorted([p for p in scan_pids
                   if scan_has_agree[p] and scan_has_disagree[p]])
    only_disagree = sorted([p for p in scan_pids
                            if not scan_has_agree[p] and scan_has_disagree[p]])
    only_agree = sorted([p for p in scan_pids
                         if scan_has_agree[p] and not scan_has_disagree[p]])

    print(f"  同时含 agree+disagree clusters：{len(both)}")
    print(f"  仅含 disagree（k<4）clusters ：{len(only_disagree)}")
    print(f"  仅含 agree（k=4）clusters   ：{len(only_agree)}")

    # 平衡采样：优先 both，不足时补 only-disagree，再补 only-agree
    selected: list[str] = []
    selected.extend(both[:n_scans])

    if len(selected) < n_scans:
        remaining = n_scans - len(selected)
        # 补 only_disagree（保证有正样本）
        n_od = min(remaining // 2, len(only_disagree))
        selected.extend(only_disagree[:n_od])

    if len(selected) < n_scans:
        remaining = n_scans - len(selected)
        selected.extend(only_agree[:remaining])

    selected = sorted(set(selected))[:n_scans]

    # 打印选中 patient 列表 + 预估正负 cluster 数
    selected_set = set(selected)
    n_pos = sum(1 for r in rows
                if r["scan_pid"] in selected_set and r["disagree_binary"] == "1")
    n_neg = sum(1 for r in rows
                if r["scan_pid"] in selected_set and r["disagree_binary"] == "0")

    print(f"\n[select] 选中 {len(selected)} 个 patient（目标 {n_scans}）：")
    for pid in selected:
        print(f"  {pid}")
    print(f"\n[select] 预估 cluster 数：disagree=1（k<4）= {n_pos}，"
          f"disagree=0（k=4）= {n_neg}，合计 {n_pos + n_neg}")

    return selected


# ─────────────────────────────────────────────────────────────────────────────
# 2. 从 pylidc DB 查 series_instance_uid
# ─────────────────────────────────────────────────────────────────────────────

def get_series_uid_map(patient_ids: list[str]) -> dict[str, str]:
    """
    通过 pylidc 查询每个 patient_id 对应的 series_instance_uid。
    返回 {patient_id: series_instance_uid}。

    注意：pylidc 自带 SQLite DB（含所有 1018 scan 元数据），
    无需 DICOM 就位即可查 UID，零 API 调用。
    """
    import pylidc as pl  # noqa: E402（monkey-patch 已在顶层做）

    print("\n[uid] 查询 pylidc DB 中各 patient 的 SeriesInstanceUID ...")
    uid_map: dict[str, str] = {}
    not_found: list[str] = []

    for pid in patient_ids:
        scans = pl.query(pl.Scan).filter(pl.Scan.patient_id == pid).all()
        if not scans:
            print(f"  [WARN] {pid}: pylidc DB 中未找到，跳过", file=sys.stderr)
            not_found.append(pid)
            continue
        # 每个 patient 通常只有 1 个 scan；若多个取第一个
        scan = scans[0]
        uid = scan.series_instance_uid
        uid_map[pid] = uid
        if len(scans) > 1:
            print(f"  [INFO] {pid}: 有 {len(scans)} 个 scan，取第一个 UID={uid}")

    print(f"[uid] 查到 {len(uid_map)} 个 UID，未找到 {len(not_found)} 个")
    return uid_map


# ─────────────────────────────────────────────────────────────────────────────
# 3. 下载单个 series（带重试 + 流式进度 + 失败跳过）
# ─────────────────────────────────────────────────────────────────────────────

def download_series(series_uid: str, patient_id: str, dest_root: Path) -> bool:
    """
    从 NBIA getImage 下载单个 series zip，解压到：
      dest_root/<patient_id>/<StudyInstanceUID>/<SeriesInstanceUID>/*.dcm
    （pylidc 期望的 patient/study/series 三级目录结构）

    流式下载 + 进度打印 + 失败重试 RETRY_ATTEMPTS 次。
    返回 True=成功，False=跳过（记录失败）。
    """
    url = f"{NBIA_GET_IMAGE_URL}?SeriesInstanceUID={series_uid}"
    patient_dir = dest_root / patient_id
    patient_dir.mkdir(parents=True, exist_ok=True)

    zip_path = patient_dir / f"{series_uid}.zip"

    # ── 下载（带重试）────────────────────────────────────────────────────
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            print(f"  [{patient_id}] 下载 attempt {attempt}/{RETRY_ATTEMPTS} "
                  f"SeriesUID={series_uid[:40]}...")
            resp = requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT)
            resp.raise_for_status()

            total_bytes = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(str(zip_path), "wb") as fout:
                for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        fout.write(chunk)
                        downloaded += len(chunk)
                        if total_bytes > 0:
                            pct = 100.0 * downloaded / total_bytes
                            mb = downloaded / 1024 / 1024
                            print(f"\r    {pct:.1f}%  {mb:.1f}MB", end="", flush=True)
            if total_bytes > 0:
                print()   # 换行
            print(f"  [{patient_id}] 下载完成  {downloaded / 1024 / 1024:.1f} MB")
            break   # 成功，跳出重试

        except requests.exceptions.RequestException as exc:
            print(f"  [{patient_id}] attempt {attempt} 失败: {exc}", file=sys.stderr)
            if zip_path.exists():
                zip_path.unlink()
            if attempt < RETRY_ATTEMPTS:
                print(f"  [{patient_id}] {RETRY_DELAY}s 后重试 ...", file=sys.stderr)
                time.sleep(RETRY_DELAY)
            else:
                print(f"  [{patient_id}] 重试耗尽，跳过此 patient", file=sys.stderr)
                return False

    # ── 解压（解压后删 zip 省空间）────────────────────────────────────────
    try:
        with zipfile.ZipFile(str(zip_path), "r") as zf:
            namelist = zf.namelist()
            # NBIA zip 结构示例：
            #   1.3.6.../1.3.6.../IM-0001-0001.dcm
            # 第一级目录通常是 StudyInstanceUID；解压到 patient_dir 下
            zf.extractall(str(patient_dir))
        dcm_count = sum(1 for n in namelist if n.lower().endswith(".dcm"))
        print(f"  [{patient_id}] 解压完成  {len(namelist)} 文件（{dcm_count} .dcm）")
    except zipfile.BadZipFile as exc:
        print(f"  [{patient_id}] zip 损坏，跳过: {exc}", file=sys.stderr)
        if zip_path.exists():
            zip_path.unlink()
        return False

    # 删 zip 省空间
    if zip_path.exists():
        zip_path.unlink()

    return True


# ─────────────────────────────────────────────────────────────────────────────
# 4. 配置 ~/.pylidcrc
# ─────────────────────────────────────────────────────────────────────────────

def configure_pylidcrc(lidc_root: Path) -> None:
    """
    写 / 更新 ~/.pylidcrc，将 [dicom] path 指向 lidc_root。
    若已存在配置文件，先备份为 ~/.pylidcrc.bak，再覆写 [dicom] path。

    pylidc 期望格式：
      [dicom]
      path = <DICOM 根目录>

    注意：pylidc 会在 path 下递归搜索 .dcm 文件并匹配 patient_id，
    目录层级（patient/study/series）应与 NBIA 解压结构一致。
    """
    rcpath = PYLIDCRC_PATH
    lidc_root_str = str(lidc_root).replace("\\", "/")

    if rcpath.exists():
        # 备份已有配置
        bak = rcpath.with_suffix(".bak")
        shutil.copy2(str(rcpath), str(bak))
        print(f"[pylidcrc] 已有配置备份至：{bak}")

        # 读取现有内容，替换或追加 [dicom] path
        content = rcpath.read_text(encoding="utf-8")
        if re.search(r"^\[dicom\]", content, re.MULTILINE):
            # 替换已有 path 行
            content = re.sub(
                r"(?m)^(path\s*=\s*).*$",
                f"path = {lidc_root_str}",
                content,
            )
            print(f"[pylidcrc] 已更新 [dicom] path → {lidc_root_str}")
        else:
            # 追加 [dicom] section
            content += f"\n[dicom]\npath = {lidc_root_str}\n"
            print(f"[pylidcrc] 已追加 [dicom] path → {lidc_root_str}")
        rcpath.write_text(content, encoding="utf-8")
    else:
        # 全新写入
        rcpath.write_text(
            f"[dicom]\npath = {lidc_root_str}\n",
            encoding="utf-8",
        )
        print(f"[pylidcrc] 新建 ~/.pylidcrc，path → {lidc_root_str}")

    print(f"[pylidcrc] 配置已就绪：{rcpath}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. 主流程
# ─────────────────────────────────────────────────────────────────────────────

def get_already_downloaded(dest_root: Path) -> set[str]:
    """
    从 dest_root 读取已下载的 patient 目录名（LIDC-IDRI-XXXX 格式）。
    只要目录存在即认为已下载（不验证内部 dcm 完整性，避免重下误删）。
    """
    if not dest_root.exists():
        return set()
    return {
        p.name for p in dest_root.iterdir()
        if p.is_dir() and p.name.startswith("LIDC-IDRI-")
    }


# ─── 每个 CT scan 平均大小估算（LIDC-IDRI 典型值约 120MB/scan）─────────────
APPROX_MB_PER_SCAN = 120


def download_subset(n_scans: int = 50, dest_root: Path = LIDC_SUBSET_DIR,
                    dry_run: bool = False) -> None:
    """
    主下载流程（fresh 模式）：
      1. 平衡采样选 n_scans 个 patient
      2. 查 pylidc DB 取 series_instance_uid
      3. 逐 patient 下载 DICOM zip → 解压
      4. 配置 ~/.pylidcrc
      5. 报告成功/失败计数 + 总大小
    """
    print("=" * 60)
    print("  download_lidc_subset — DisagreePred A1 (fresh)")
    print(f"  目标 patient 数：{n_scans}")
    print(f"  下载目标目录  ：{dest_root}")
    print("=" * 60)

    # Step 1：平衡采样（无 exclude）
    patient_ids = select_balanced_patients(DIST_CSV, n_scans, exclude=None)

    # Step 2：查 UID
    uid_map = get_series_uid_map(patient_ids)

    if not uid_map:
        print("[ERROR] 无有效 UID，检查 pylidc 安装和网络连通性。", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        print("\n[DRY RUN] 以下为将要下载的 patient 列表（未实际下载）：")
        for pid, uid in sorted(uid_map.items()):
            print(f"  {pid}  SeriesUID={uid}")
        approx_gb = len(uid_map) * APPROX_MB_PER_SCAN / 1024
        print(f"\n[DRY RUN] 预计下载量：~{approx_gb:.1f} GB（按 {APPROX_MB_PER_SCAN} MB/scan 估算）")
        print("[DRY RUN] 去掉 --dry_run 参数执行真实下载。")
        return

    # Step 3：逐 patient 下载
    dest_root.mkdir(parents=True, exist_ok=True)

    success_list: list[str] = []
    fail_list: list[str] = []

    total = len(uid_map)
    for i, (pid, uid) in enumerate(sorted(uid_map.items()), 1):
        print(f"\n[{i}/{total}] {pid}")
        ok = download_series(uid, pid, dest_root)
        if ok:
            success_list.append(pid)
        else:
            fail_list.append(pid)

    # Step 4：配置 pylidcrc
    print()
    configure_pylidcrc(dest_root)

    # Step 5：统计总大小
    total_bytes = sum(
        f.stat().st_size
        for f in dest_root.rglob("*")
        if f.is_file()
    )
    total_gb = total_bytes / 1024 ** 3

    print()
    print("=" * 60)
    print("  下载完成 — 摘要")
    print("=" * 60)
    print(f"  成功：{len(success_list)} 个 patient")
    print(f"  失败：{len(fail_list)} 个 patient")
    if fail_list:
        print(f"  失败列表：{fail_list}")
    print(f"  下载总大小：{total_gb:.2f} GB")
    print(f"  LIDC 子集目录：{dest_root}")
    print()
    print("  下一步：")
    print(f"    python {SCRIPT_DIR}/parse_lidc.py --data_root {dest_root}")
    print("=" * 60)


def extend_subset(n_new: int = 100, dest_root: Path = LIDC_SUBSET_DIR,
                  dry_run: bool = True) -> None:
    """
    扩样模式（extend）：
      1. 检测 dest_root 已下载 patient → 生成 exclude 集合
      2. 从剩余候选按平衡策略选 n_new 个**新** patient
      3. 查 pylidc DB 取 series_instance_uid
      4. dry_run=True（默认）：只打印新 UID 列表 + 预计大小，不下载
      5. dry_run=False：执行真实下载

    注意：已下载的 patient 绝不重下（通过 exclude 集合跳过）。
    """
    print("=" * 60)
    print("  download_lidc_subset — DisagreePred A1 (extend)")
    print(f"  新增目标 patient 数：{n_new}")
    print(f"  下载目标目录      ：{dest_root}")
    print(f"  dry_run            ：{dry_run}")
    print("=" * 60)

    # Step 1：检测已下载
    already = get_already_downloaded(dest_root)
    print(f"\n[extend] 已下载 {len(already)} 个 patient（将跳过）：")
    for pid in sorted(already):
        print(f"  {pid}")

    if not already:
        print("[WARN] dest_root 未发现已下载 patient，建议先跑 --mode fresh --n_scans 50",
              file=sys.stderr)

    # Step 2：平衡采样（exclude 已下载）
    new_patients = select_balanced_patients(DIST_CSV, n_new, exclude=already)

    if not new_patients:
        print("[ERROR] 无新候选 patient 可选，dist.csv 候选已耗尽？", file=sys.stderr)
        sys.exit(1)

    # Step 3：查 UID
    uid_map = get_series_uid_map(new_patients)

    if not uid_map:
        print("[ERROR] 无有效 UID，检查 pylidc 安装。", file=sys.stderr)
        sys.exit(1)

    # Step 4：预览 / 下载
    total_after = len(already) + len(uid_map)
    approx_gb = len(uid_map) * APPROX_MB_PER_SCAN / 1024

    print(f"\n[extend] 新增 {len(uid_map)} 个 patient（已有 {len(already)}，"
          f"完成后共 ~{total_after} 个）")
    print(f"[extend] 预计新增下载量：~{approx_gb:.1f} GB（{APPROX_MB_PER_SCAN} MB/scan 估算）")
    print()
    print("[extend] 将要下载的新 patient 列表：")
    for pid, uid in sorted(uid_map.items()):
        print(f"  {pid}  SeriesUID={uid}")

    if dry_run:
        print()
        print("=" * 60)
        print("  [DRY RUN] 预览完毕，未执行下载。")
        print("  确认无误后运行（去掉 --dry_run）：")
        print(f"    python {SCRIPT_DIR / 'download_lidc_subset.py'} "
              f"--mode extend --n_new {n_new}")
        print("=" * 60)
        return

    # 真实下载
    dest_root.mkdir(parents=True, exist_ok=True)
    success_list: list[str] = []
    fail_list: list[str] = []

    total = len(uid_map)
    for i, (pid, uid) in enumerate(sorted(uid_map.items()), 1):
        print(f"\n[{i}/{total}] {pid}")
        ok = download_series(uid, pid, dest_root)
        if ok:
            success_list.append(pid)
        else:
            fail_list.append(pid)

    configure_pylidcrc(dest_root)

    total_bytes = sum(
        f.stat().st_size
        for f in dest_root.rglob("*")
        if f.is_file()
    )
    total_gb_all = total_bytes / 1024 ** 3

    print()
    print("=" * 60)
    print("  扩样下载完成 — 摘要")
    print("=" * 60)
    print(f"  原有 patient ：{len(already)}")
    print(f"  新增成功     ：{len(success_list)}")
    print(f"  新增失败     ：{len(fail_list)}")
    if fail_list:
        print(f"  失败列表：{fail_list}")
    print(f"  dest_root 当前总大小：{total_gb_all:.2f} GB")
    print(f"  LIDC 子集目录：{dest_root}")
    print()
    print("  下一步：")
    print(f"    python {SCRIPT_DIR}/parse_lidc.py --data_root {dest_root}")
    print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# 入口（主线执行命令见此）
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "DisagreePred A1：下载 LIDC-IDRI 子集（平衡 agree/disagree）\n"
            "  fresh  模式：首次下载 --n_scans 个 patient\n"
            "  extend 模式：跳过已下，再下 --n_new 个新 patient（默认 dry_run 预览）"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode", type=str, default="extend", choices=["fresh", "extend"],
        help="运行模式：fresh=首次下载，extend=扩样（默认 extend）"
    )
    parser.add_argument(
        "--n_scans", type=int, default=50,
        help="[fresh 模式] 目标 patient 总数（默认 50）"
    )
    parser.add_argument(
        "--n_new", type=int, default=100,
        help="[extend 模式] 新增 patient 数（默认 100，凑 ~150 total）"
    )
    parser.add_argument(
        "--dest_root", type=str, default=str(LIDC_SUBSET_DIR),
        help=f"DICOM 下载目标目录（默认 {LIDC_SUBSET_DIR}）"
    )
    parser.add_argument(
        "--dry_run", action="store_true", default=False,
        help="[extend 模式] 只打印将下载的 UID 列表 + 预计大小，不执行下载"
    )
    args = parser.parse_args()

    dest = Path(args.dest_root)

    if args.mode == "fresh":
        download_subset(
            n_scans=args.n_scans,
            dest_root=dest,
            dry_run=args.dry_run,
        )
    else:  # extend
        extend_subset(
            n_new=args.n_new,
            dest_root=dest,
            dry_run=args.dry_run,
        )
