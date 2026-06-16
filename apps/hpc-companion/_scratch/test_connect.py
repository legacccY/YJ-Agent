"""实测：用 store 里的 profile+密码连 HPC 跑 squeue。验证后端真能用。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.profiles import ProfileStore
from core.ssh_client import SSHClient
from core import slurm

s = ProfileStore()
p = s.get("XJTLU HPC (gpu4090)")
pw = s.get_password(p)
ssh = SSHClient()
try:
    ssh.connect(p, password=pw, timeout=15)
    print("CONNECTED ok:", ssh.is_alive())
    r = ssh.exec(slurm.queue_cmd(p.username), timeout=20)
    print("squeue rc=", r.rc)
    jobs = slurm.parse_squeue(r.out)
    print("jobs:", len(jobs))
    for j in jobs[:10]:
        print(f"  {j.job_id} {j.state:10} {j.name}")
    who = ssh.exec("whoami && hostname").out
    print("whoami/host:", who.replace(chr(10), " / "))
except Exception as e:
    print("CONNECT FAILED:", type(e).__name__, e)
finally:
    ssh.close()
