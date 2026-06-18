"""upload_phasemap.py — 上传 NCA-PhaseMap Gate1 脚本 + BraTS test 到 HPC。

默认 dry-run（只打印计划）。真传加 --go。

布局（Med-NCA 框架/Hippo 已在 run003/mednca/，复用不重传）：
  1. 8 个 Gate1 脚本 → /gpfs/work/bio/jiayu2403/run003/phasemap/
  2. BraTS test/tumor + test/annotation → run003/phasemap/data/brats_test/{tumor,annotation}/
  3. results/ 占位

sbatch 用 env：
  MEDNCA_ROOT=/gpfs/work/bio/jiayu2403/run003/mednca
  BRATS_ROOT =/gpfs/work/bio/jiayu2403/run003/phasemap/data/brats_test
  PHASEMAP_OUT=/gpfs/work/bio/jiayu2403/run003/phasemap

Usage:
    python _hpc/upload_phasemap.py        # dry-run
    python _hpc/upload_phasemap.py --go   # 真传（续传支持）
"""
import os, sys, time, pathlib, warnings
warnings.filterwarnings("ignore")

DRY_RUN = "--go" not in sys.argv

_THIS   = pathlib.Path(__file__).resolve()
EXP_DIR = _THIS.parent.parent                          # 06_experiments/
BRATS_LOCAL = pathlib.Path(
    os.environ.get('BRATS_TEST_LOCAL',
                   r"D:\YJ-Agent\project\meeting\MedAD-FailMap\data\BraTS2021\test")
)

HPC_HOST = "dtn.hpc.xjtlu.edu.cn"
HPC_USER = "jiayu2403"
HPC_PASS = "pxXd3VGhbB"
HPC_PHASEMAP = "/gpfs/work/bio/jiayu2403/run003/phasemap"
HPC_BRATS    = f"{HPC_PHASEMAP}/data/brats_test"

SCRIPTS = ["data_brats.py", "B0_baseline.py", "B1_B2_B3_sweep.py",
           "nca_impl2.py", "B4_impl2.py", "G_gradient_traj.py",
           "G_sensitivity.py", "M1_probe.py"]
MAX_RETRY = 3


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def dir_size(p):
    return sum(f.stat().st_size for f in pathlib.Path(p).rglob("*") if f.is_file())


def hpc_stat_size(sftp, rp):
    try:
        return sftp.stat(rp).st_size
    except IOError:
        return -1


def put_retry(sftp, lp, rp, max_retry=MAX_RETRY):
    last = None
    for a in range(max_retry):
        try:
            sftp.put(str(lp), rp)
            return
        except Exception as e:
            last = e
            w = 2 ** a
            print(f"    [retry {a+1}/{max_retry}] {e}  wait {w}s", flush=True)
            time.sleep(w)
    raise RuntimeError(f"上传失败（重试 {max_retry}）：{last}")


def upload_dir(sftp, ssh_run, local_dir, remote_dir, label=""):
    local_dir = pathlib.Path(local_dir)
    ssh_run(f"mkdir -p {remote_dir}")
    files = [f for f in sorted(local_dir.rglob("*")) if f.is_file()]
    made = {remote_dir.rstrip("/")}          # mkdir 缓存，避免平目录重复 ssh 往返
    done = 0
    for lf in files:
        rel = lf.relative_to(local_dir)
        rf = remote_dir.rstrip("/") + "/" + str(rel).replace("\\", "/")
        rparent = rf.rsplit("/", 1)[0]
        if rparent not in made:
            ssh_run(f"mkdir -p {rparent}")
            made.add(rparent)
        lsz = lf.stat().st_size
        if hpc_stat_size(sftp, rf) == lsz:
            done += 1
            continue
        put_retry(sftp, lf, rf)
        done += 1
        if done % 200 == 0:
            print(f"    [{done}/{len(files)}] {label}", flush=True)
    print(f"  [done] {label or remote_dir}  {len(files)} 文件", flush=True)


def main():
    print("=" * 60)
    print("DRY-RUN 计划" if DRY_RUN else "真传 --go 模式")
    print(f"  脚本 EXP_DIR : {EXP_DIR}  -> {HPC_PHASEMAP}")
    print(f"  BraTS local  : {BRATS_LOCAL}  -> {HPC_BRATS}")
    print("=" * 60)

    scr_sz = sum((EXP_DIR / s).stat().st_size for s in SCRIPTS if (EXP_DIR / s).exists())
    print(f"  脚本 {len(SCRIPTS)} 个: {human(scr_sz)}")
    for sub in ("tumor", "annotation"):
        d = BRATS_LOCAL / sub
        if d.exists():
            n = sum(1 for _ in d.iterdir())
            print(f"  BraTS test/{sub}: {n} 文件  {human(dir_size(d))}")
        else:
            print(f"  [WARN] 缺 {d}")

    if DRY_RUN:
        print("\nDry-run 完成。加 --go 真传：python _hpc/upload_phasemap.py --go")
        return

    import paramiko
    print("\n连接 HPC ...")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HPC_HOST, username=HPC_USER, password=HPC_PASS, timeout=20)
    c.get_transport().set_keepalive(30)

    def run(cmd, timeout=120):
        _, o, e = c.exec_command(cmd, timeout=timeout)
        return o.read().decode("utf-8", "replace").strip() + \
               (("\n" + e.read().decode("utf-8", "replace").strip()) if e else "")

    run(f"mkdir -p {HPC_PHASEMAP}/results {HPC_BRATS}/tumor {HPC_BRATS}/annotation")
    sftp = c.open_sftp()
    try:
        print("\n[1/3] Gate1 脚本 ...", flush=True)
        for s in SCRIPTS:
            lf = EXP_DIR / s
            if not lf.exists():
                print(f"  [SKIP] {s} 不存在")
                continue
            rf = f"{HPC_PHASEMAP}/{s}"
            if hpc_stat_size(sftp, rf) == lf.stat().st_size:
                print(f"  [skip] {s} 已传")
                continue
            put_retry(sftp, lf, rf)
            print(f"  [put] {s}  OK", flush=True)

        print("\n[2/3] BraTS test/tumor ...", flush=True)
        upload_dir(sftp, run, BRATS_LOCAL / "tumor", f"{HPC_BRATS}/tumor", "tumor")
        print("\n[3/3] BraTS test/annotation ...", flush=True)
        upload_dir(sftp, run, BRATS_LOCAL / "annotation", f"{HPC_BRATS}/annotation", "annotation")
    finally:
        sftp.close()

    print("\n" + "=" * 60)
    print("全部上传完成。")
    print("phasemap/:", run(f"ls {HPC_PHASEMAP}"))
    print("brats tumor 计数:", run(f"ls {HPC_BRATS}/tumor | wc -l"))
    print("brats annotation 计数:", run(f"ls {HPC_BRATS}/annotation | wc -l"))
    c.close()


if __name__ == "__main__":
    main()
