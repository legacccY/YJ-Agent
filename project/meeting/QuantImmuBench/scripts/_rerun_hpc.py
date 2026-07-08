# -*- coding: utf-8 -*-
"""slice_immbox rerun HPC helper. 凭证从 HPC_WORKFLOW.md 读，绝不硬编。
用法:
  python _rerun_hpc.py run "<remote_cmd>"          # 在 BASE 下跑命令，流式输出
  python _rerun_hpc.py put <local> <remote_rel>     # 上传单文件 (相对 BASE)
  python _rerun_hpc.py putdir <local_dir> <remote_rel>  # 递归上传目录
  python _rerun_hpc.py pull <remote_rel> <local>    # 下载
"""
import re, sys, os, stat, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
import paramiko

WF = Path(r"D:/YJ-Agent/project/HPC_WORKFLOW.md").read_text(encoding="utf-8", errors="ignore")
HOST = "dtn.hpc.xjtlu.edu.cn"
USER = re.search(r"用户名 \| `(.+?)`", WF).group(1)
PW   = re.search(r"密码 \| `(.+?)`", WF).group(1)
BASE = "/gpfs/work/bio/jiayu2403/quantimmu"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PW, timeout=30)
sf = c.open_sftp()

def _mkdirs(remote):
    parts = remote.strip("/").split("/")
    cur = ""
    for p in parts:
        cur += "/" + p
        try: sf.stat(cur)
        except IOError:
            try: sf.mkdir(cur)
            except IOError: pass

def putdir(local_dir, remote_rel):
    local_dir = Path(local_dir)
    remote_root = f"{BASE}/{remote_rel}".rstrip("/")
    _mkdirs(remote_root)
    n = 0
    for root, dirs, filesx in os.walk(local_dir):
        rel = os.path.relpath(root, local_dir).replace("\\", "/")
        rroot = remote_root if rel == "." else f"{remote_root}/{rel}"
        _mkdirs(rroot)
        for fn in filesx:
            sf.put(os.path.join(root, fn), f"{rroot}/{fn}")
            n += 1
            if n % 20 == 0: print(f"  ...{n} files")
    print(f"[putdir] {local_dir} -> {remote_root}  ({n} files)")

cmd = sys.argv[1]
if cmd == "run":
    remote_cmd = sys.argv[2]
    chan = c.get_transport().open_session()
    chan.exec_command(f"cd {BASE} && {remote_cmd}")
    while True:
        if chan.recv_ready():
            sys.stdout.write(chan.recv(8192).decode("utf-8","ignore")); sys.stdout.flush()
        if chan.recv_stderr_ready():
            sys.stdout.write(chan.recv_stderr(8192).decode("utf-8","ignore")); sys.stdout.flush()
        if chan.exit_status_ready() and not chan.recv_ready() and not chan.recv_stderr_ready():
            break
    print(f"\n[exit {chan.recv_exit_status()}]")
elif cmd == "put":
    local, remote_rel = sys.argv[2], sys.argv[3]
    rp = f"{BASE}/{remote_rel}"
    _mkdirs(os.path.dirname(rp))
    sf.put(local, rp)
    if rp.endswith((".sh",".py",".R")):
        _,o,_ = c.exec_command(f"sed -i 's/\\r$//' {rp}"); o.read()
    print(f"[put] {local} -> {rp}")
elif cmd == "putdir":
    putdir(sys.argv[2], sys.argv[3])
elif cmd == "pull":
    remote_rel, local = sys.argv[2], sys.argv[3]
    Path(os.path.dirname(local)).mkdir(parents=True, exist_ok=True)
    sf.get(f"{BASE}/{remote_rel}", local)
    print(f"[pull] {BASE}/{remote_rel} -> {local} ({os.path.getsize(local)} bytes)")

sf.close(); c.close()
