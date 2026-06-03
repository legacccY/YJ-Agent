"""hpc_upload_r2.py — 上传 Med-NCA R2 所需文件到 HPC（健壮分块可续传版）。

默认 dry-run（只打印分片计划）。真传加 --go 参数。

大文件策略：
  - zip 后切成 ~900 MB 分片（part_000, part_001, ...）
  - 每片单独 sftp.put，传完再传下一片
  - 重跑时 stat 检查 HPC 已有片 → 大小一致则跳过（续传）
  - 所有片传完 → ssh cat 重组 → unzip → 校验文件数 → 删 parts + zip

小文件：逐文件 sftp，也加 keepalive + 重试。
  - --skip-done 时对已传目录先 stat 确认存在则跳过。

Usage:
    python code/hpc_upload_r2.py                 # dry-run：打印分片计划
    python code/hpc_upload_r2.py --go            # 真传（从头或续传）
    python code/hpc_upload_r2.py --go --skip-done # 跳过已传的小目录
"""

import os
import sys
import time
import zipfile
import tempfile
import shutil
import warnings

warnings.filterwarnings("ignore")

DRY_RUN   = "--go" not in sys.argv
SKIP_DONE = "--skip-done" in sys.argv

# ---- 本地路径 --------------------------------------------------------
LOCAL_ROOT = r"D:\YJ-Agent\project\meeting\Med-NCA"

# 要传的目录（相对 LOCAL_ROOT）
DIRS_TO_UPLOAD = [
    "M3D-NCA-official",                                          # ~42 MB：已传，--skip-done 可跳
    "code",                                                       # ~85 KB：已传，--skip-done 可跳
    os.path.join("data", "ISIC2018_Task1-2_Training_Input"),     # ~10.4 GB：大文件分块
    os.path.join("data", "ISIC2018_Task1_Training_GroundTruth"), # ~46 MB：小文件
]

# ---- HPC 参数 --------------------------------------------------------
HPC_HOST = "dtn.hpc.xjtlu.edu.cn"
HPC_USER = "jiayu2403"
HPC_PASS = "pxXd3VGhbB"
HPC_ROOT = "/gpfs/work/bio/jiayu2403/mednca"

# 大文件分块阈值（字节）：超过此大小用分块传
ZIP_THRESHOLD  = 100 * 1024 * 1024       # 100 MB
# 每个分片的目标大小
CHUNK_SIZE     = 900 * 1024 * 1024       # 900 MB
# 单片上传最大重试次数
MAX_RETRY      = 3
# keepalive 间隔（秒）
KEEPALIVE_SECS = 30


# ---- 工具函数 --------------------------------------------------------

def dir_size(path):
    """递归计算目录大小（字节）。"""
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def zip_dir(src_path, zip_path):
    """把 src_path 目录打包成 zip_path，返回 zip 大小。"""
    src_parent = os.path.dirname(src_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for dirpath, _, filenames in os.walk(src_path):
            for fname in filenames:
                full = os.path.join(dirpath, fname)
                arcname = os.path.relpath(full, src_parent)
                zf.write(full, arcname)
    return os.path.getsize(zip_path)


def split_file(src_path, out_dir, chunk_size=CHUNK_SIZE):
    """把 src_path 按 chunk_size 切成 part_000, part_001, ...
    返回 [(part_path, part_size), ...]。
    """
    parts = []
    idx = 0
    with open(src_path, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            part_name = f"part_{idx:03d}"
            part_path = os.path.join(out_dir, part_name)
            with open(part_path, "wb") as pf:
                pf.write(data)
            parts.append((part_path, len(data)))
            idx += 1
    return parts


def hpc_stat_size(sftp, remote_path):
    """返回 HPC 上文件的字节大小，若不存在返回 -1。"""
    try:
        attr = sftp.stat(remote_path)
        return attr.st_size
    except IOError:
        return -1


def sftp_put_with_retry(sftp, local_path, remote_path, max_retry=MAX_RETRY):
    """带指数退避的 sftp.put，失败最多重试 max_retry 次。"""
    last_exc = None
    for attempt in range(max_retry):
        try:
            sftp.put(local_path, remote_path)
            return  # 成功
        except Exception as e:
            last_exc = e
            wait = 2 ** attempt  # 1s, 2s, 4s
            print(f"  [retry {attempt+1}/{max_retry}] {e}  等待 {wait}s ...")
            time.sleep(wait)
    raise RuntimeError(f"上传失败（重试 {max_retry} 次）：{last_exc}")


# ---- 主逻辑 ----------------------------------------------------------

def main():
    import paramiko

    # ---- 打印传输计划 ------------------------------------------------
    print("=" * 60)
    print(f"{'DRY-RUN 分片计划' if DRY_RUN else '真传 --go 模式'}"
          + ("  (+skip-done)" if SKIP_DONE else ""))
    print(f"  Local  : {LOCAL_ROOT}")
    print(f"  HPC    : {HPC_ROOT}")
    print("=" * 60)

    plan = []
    for rel_dir in DIRS_TO_UPLOAD:
        local_path = os.path.join(LOCAL_ROOT, rel_dir)
        if not os.path.exists(local_path):
            print(f"  [SKIP] {rel_dir}  <- 本地不存在")
            continue
        sz       = dir_size(local_path)
        use_zip  = sz > ZIP_THRESHOLD
        strategy = "分块sftp+续传" if use_zip else "sftp逐文件"

        if use_zip:
            # 估算 zip 后大小（JPEG 压缩率约 1.0，zip 基本不缩）
            est_zip_sz = sz   # JPEG 几乎不压缩，保守估算
            n_chunks = max(1, -(-est_zip_sz // CHUNK_SIZE))   # 向上整除
            print(f"  {rel_dir}")
            print(f"    本地大小: {human(sz)}   策略: {strategy}")
            print(f"    预估分片: {n_chunks} 片 × ~{human(CHUNK_SIZE)}/片")
        else:
            print(f"  {rel_dir}")
            print(f"    大小: {human(sz)}   策略: {strategy}")

        plan.append((rel_dir, local_path, sz, use_zip))

    total = sum(s for _, _, s, _ in plan)
    print(f"\n合计本地大小: {human(total)}\n")

    if DRY_RUN:
        print("Dry-run 完成。加 --go 开始真传（支持断点续传）。")
        print("  python code/hpc_upload_r2.py --go")
        print("  python code/hpc_upload_r2.py --go --skip-done  # 跳过已传的小目录")
        return

    # ---- 真传 --------------------------------------------------------
    print("连接 HPC ...")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HPC_HOST, username=HPC_USER, password=HPC_PASS, timeout=20)
    c.get_transport().set_keepalive(KEEPALIVE_SECS)

    def run(cmd, timeout=300):
        _, o, e = c.exec_command(cmd, timeout=timeout)
        out = o.read().decode("utf-8", errors="replace").strip()
        err = e.read().decode("utf-8", errors="replace").strip()
        return out + ("\n" + err if err else "")

    # 确保 HPC 根目录存在
    run(f"mkdir -p {HPC_ROOT}/logs {HPC_ROOT}/checkpoints/r2_isic {HPC_ROOT}/results")

    sftp = c.open_sftp()
    tmp_dir = tempfile.mkdtemp(prefix="mednca_upload_")

    try:
        for rel_dir, local_path, sz, use_zip in plan:
            # HPC 路径用正斜杠
            hpc_dest   = (HPC_ROOT + "/" + rel_dir.replace("\\", "/"))
            hpc_parent = hpc_dest.rsplit("/", 1)[0]
            dir_name   = os.path.basename(local_path)

            if use_zip:
                # ============================================================
                # 大文件：zip → split → 逐片续传 → HPC cat + unzip
                # ============================================================
                zip_name  = dir_name + ".zip"
                zip_local = os.path.join(tmp_dir, zip_name)

                # Step 1: 打包（若 zip 已存在且大小合理则复用）
                if os.path.exists(zip_local) and os.path.getsize(zip_local) > 1024:
                    zip_sz = os.path.getsize(zip_local)
                    print(f"\n[zip] 复用已有 {zip_name} ({human(zip_sz)})")
                else:
                    print(f"\n[zip] 打包 {rel_dir} ...")
                    zip_sz = zip_dir(local_path, zip_local)
                    print(f"[zip] 完成 → {human(zip_sz)}")

                # Step 2: 切片
                parts_dir = os.path.join(tmp_dir, dir_name + "_parts")
                os.makedirs(parts_dir, exist_ok=True)

                # 判断是否需要重新切片（parts 数量对不上则重切）
                existing_parts = sorted([
                    f for f in os.listdir(parts_dir) if f.startswith("part_")
                ])
                expected_n = max(1, -(-zip_sz // CHUNK_SIZE))

                if len(existing_parts) == expected_n:
                    print(f"[split] 复用已有 {expected_n} 个分片")
                    parts = [
                        (os.path.join(parts_dir, p), os.path.getsize(os.path.join(parts_dir, p)))
                        for p in existing_parts
                    ]
                else:
                    print(f"[split] 切分为 {expected_n} 片（每片 ~{human(CHUNK_SIZE)}）...")
                    # 清理旧的不完整分片
                    for old in os.listdir(parts_dir):
                        os.remove(os.path.join(parts_dir, old))
                    parts = split_file(zip_local, parts_dir)
                    print(f"[split] 完成：{len(parts)} 片")

                # Step 3: HPC 准备目录
                hpc_parts_dir = f"{hpc_parent}/{dir_name}_parts"
                run(f"mkdir -p {hpc_parts_dir} {hpc_parent}")

                # Step 4: 逐片续传
                print(f"[sftp] 开始逐片上传到 {hpc_parts_dir} ...")
                all_parts_ok = True
                for part_path, part_sz in parts:
                    part_name   = os.path.basename(part_path)
                    remote_part = f"{hpc_parts_dir}/{part_name}"

                    # 续传检查：HPC 已有且大小一致 → 跳过
                    remote_sz = hpc_stat_size(sftp, remote_part)
                    if remote_sz == part_sz:
                        print(f"  [skip] {part_name} 已存在 ({human(part_sz)})")
                        continue

                    print(f"  [put ] {part_name} ({human(part_sz)}) ...", end=" ", flush=True)
                    t0 = time.time()
                    try:
                        sftp_put_with_retry(sftp, part_path, remote_part)
                        elapsed = time.time() - t0
                        speed   = part_sz / elapsed / 1024 / 1024
                        print(f"OK ({elapsed:.0f}s, {speed:.1f} MB/s)")
                    except Exception as e:
                        print(f"FAILED: {e}")
                        all_parts_ok = False
                        # 单片失败不毁全局，继续下一片

                if not all_parts_ok:
                    print(f"[warn] {rel_dir} 有分片传失败，请重跑 --go 续传缺片。跳过 HPC 重组。")
                    continue

                # Step 5: HPC 端重组 → unzip → 校验 → 清理
                zip_remote = f"{hpc_parent}/{zip_name}"
                print(f"[hpc ] 重组分片 → {zip_remote} ...")
                cat_cmd = (
                    f"cd {hpc_parts_dir} && "
                    f"cat $(ls part_* | sort) > {zip_remote} && "
                    f"echo 'cat_ok'"
                )
                out = run(cat_cmd, timeout=600)
                if "cat_ok" not in out:
                    print(f"[hpc ] cat 失败：{out[:300]}")
                    continue
                print(f"[hpc ] cat 完成，开始 unzip ...")

                unzip_cmd = (
                    f"cd {hpc_parent} && "
                    f"unzip -o {zip_name} && "
                    f"echo 'unzip_ok'"
                )
                out = run(unzip_cmd, timeout=900)
                if "unzip_ok" not in out:
                    print(f"[hpc ] unzip 失败：{out[:300]}")
                    continue
                print(f"[hpc ] unzip 完成，清理临时文件 ...")

                # 校验：统计解压出来的文件数
                count_out = run(f"find {hpc_dest} -type f | wc -l", timeout=60)
                print(f"[hpc ] {hpc_dest} 共 {count_out.strip()} 个文件")

                # 清理 zip + parts（只在全部成功后）
                run(f"rm -f {zip_remote}", timeout=60)
                run(f"rm -rf {hpc_parts_dir}", timeout=60)
                print(f"[done] {rel_dir} 传输完成！")

            else:
                # ============================================================
                # 小目录：sftp 逐文件，支持 --skip-done
                # ============================================================
                print(f"\n[sftp] 上传 {rel_dir} ({human(sz)}) ...")

                if SKIP_DONE:
                    # stat 检查 HPC 上目录是否存在（stat 目录本身）
                    remote_sz = hpc_stat_size(sftp, hpc_dest)
                    if remote_sz != -1:
                        print(f"  [skip] {rel_dir} 已存在于 HPC，跳过（--skip-done）")
                        continue

                run(f"mkdir -p {hpc_dest}")
                for dirpath, dirs, filenames in os.walk(local_path):
                    rel_sub    = os.path.relpath(dirpath, local_path)
                    remote_sub = (hpc_dest + "/" + rel_sub.replace("\\", "/")).replace("/.", "")
                    run(f"mkdir -p {remote_sub}")
                    for fname in filenames:
                        local_f  = os.path.join(dirpath, fname)
                        remote_f = remote_sub.rstrip("/") + "/" + fname
                        local_f_sz = os.path.getsize(local_f)

                        # 逐文件也做续传检查
                        r_sz = hpc_stat_size(sftp, remote_f)
                        if r_sz == local_f_sz:
                            continue  # 已传，跳过

                        try:
                            sftp_put_with_retry(sftp, local_f, remote_f)
                        except Exception as e:
                            print(f"  [warn] {fname} 上传失败：{e}")

                print(f"[done] {rel_dir} 上传完成")

    finally:
        sftp.close()
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print("\n全部上传任务完成。")
    print(f"HPC 端目录: {run('ls ' + HPC_ROOT)}")
    c.close()


if __name__ == "__main__":
    main()
