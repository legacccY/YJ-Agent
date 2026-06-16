"""提交一个持续打印 ~90s 的任务，供 GUI 实时观看。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.profiles import ProfileStore
from core.ssh_client import SSHClient
from core import slurm

s = ProfileStore(); p = s.get("XJTLU HPC (gpu4090)")
ssh = SSHClient(); ssh.connect(p, password=s.get_password(p), timeout=15)
WD = "/gpfs/work/bio/jiayu2403/test"
spec = slurm.SbatchSpec(
    job_name="live_watch", account="shuihuawang", partition="cpudebug",
    qos="cpudebug", nodes=1, ntasks=1, cpus_per_task=2, gpus=0,
    time_limit="00:10:00", workdir=WD,
    command='for i in $(seq 1 30); do echo "[$(date +%T)] step $i/30 ..."; sleep 3; done; echo "ALL DONE"')
r = slurm.submit_script(ssh, f"{WD}/submit_live.sh", slurm.build_sbatch(spec))
print("submit:", r.out.strip(), "| jobid:", slurm.parse_submitted_job_id(r.out))
ssh.close()
