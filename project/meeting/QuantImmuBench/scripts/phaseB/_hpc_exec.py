# -*- coding: utf-8 -*-
"""Phase B HPC 执行 helper：上传 scripts/phaseB/hpc/ 下指定文件 → dos2unix → 跑命令 → 流式输出。
凭证从 HPC_WORKFLOW.md 正则读，绝不硬编。
用法: python _hpc_exec.py <remote_cmd> <file1> [file2 ...]
  remote_cmd 在 $BASE/phaseB 下执行。文件从 scripts/phaseB/hpc/ 上传到 $BASE/phaseB/。
下载: python _hpc_exec.py --pull <remote_relpath> <local_path>
"""
import re, sys, warnings, os
from pathlib import Path
warnings.filterwarnings("ignore")
import paramiko

WF = Path(r"D:/YJ-Agent/project/HPC_WORKFLOW.md").read_text(encoding="utf-8", errors="ignore")
HOST = "dtn.hpc.xjtlu.edu.cn"
USER = re.search(r"用户名 \| `(.+?)`", WF).group(1)
PW   = re.search(r"密码 \| `(.+?)`", WF).group(1)
BASE = "/gpfs/work/bio/jiayu2403/quantimmu"
RDIR = f"{BASE}/phaseB"
HPCD = Path(r"D:/YJ-Agent/project/meeting/QuantImmuBench/scripts/phaseB/hpc")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PW, timeout=20)
sf = c.open_sftp()

if sys.argv[1] == "--pull":
    remote_rel, local = sys.argv[2], sys.argv[3]
    sf.get(f"{RDIR}/{remote_rel}", local)
    print(f"[下载] {RDIR}/{remote_rel} → {local}  ({os.path.getsize(local)} bytes)")
    sf.close(); c.close(); sys.exit(0)

remote_cmd = sys.argv[1]
files = sys.argv[2:]
for f in files:
    lp = HPCD / f
    rp = f"{RDIR}/{f}"
    sf.put(str(lp), rp)
    # dos2unix on .sh/.py
    if f.endswith((".sh", ".py")):
        _, o, _ = c.exec_command(f"sed -i 's/\\r$//' {rp}")
        o.read()
    print(f"[上传] {f} → {rp}")

print(f"\n[执行] cd {RDIR} && {remote_cmd}\n" + "="*60)
chan = c.get_transport().open_session()
chan.exec_command(f"cd {RDIR} && {remote_cmd}")
while True:
    if chan.recv_ready():
        sys.stdout.write(chan.recv(4096).decode("utf-8", "ignore")); sys.stdout.flush()
    if chan.recv_stderr_ready():
        sys.stdout.write(chan.recv_stderr(4096).decode("utf-8", "ignore")); sys.stdout.flush()
    if chan.exit_status_ready() and not chan.recv_ready() and not chan.recv_stderr_ready():
        break
print(f"\n{'='*60}\n[exit {chan.recv_exit_status()}]")
sf.close(); c.close()
