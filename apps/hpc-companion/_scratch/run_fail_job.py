"""单独跑报错任务，观察真正的 FAILED 状态 + 错误日志（打印 stderr）。"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.profiles import ProfileStore
from core.ssh_client import SSHClient
from core import slurm

s = ProfileStore()
p = s.get("XJTLU HPC (gpu4090)")
ssh = SSHClient(); ssh.connect(p, password=s.get_password(p), timeout=15)
WD = "/gpfs/work/bio/jiayu2403/test"

spec = slurm.SbatchSpec(
    job_name="hpc_fail", account="shuihuawang", partition="cpudebug",
    qos="cpudebug", nodes=1, ntasks=1, cpus_per_task=2, gpus=0,
    time_limit="00:05:00", workdir=WD,
    command='echo "start"; set -e; this_cmd_does_not_exist_xyz; echo "unreachable"')

r = slurm.submit_script(ssh, f"{WD}/submit_fail.sh", slurm.build_sbatch(spec))
print(f"submit rc={r.rc} out={r.out!r} err={r.err!r}")
jid = slurm.parse_submitted_job_id(r.out)
print("jobid:", jid)
if not jid:
    print("提交失败，停止。"); ssh.close(); sys.exit()

for _ in range(40):
    st = slurm.parse_scontrol(ssh.exec(slurm.detail_cmd(jid)).out).get("JobState", "?")
    print(time.strftime("%H:%M:%S"), "state:", st)
    if st in ("COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"):
        break
    time.sleep(4)

print("\nsacct:", ssh.exec(f"sacct -j {jid} --format=JobID,State,ExitCode -n").out)
d = slurm.parse_scontrol(ssh.exec(slurm.detail_cmd(jid)).out)
print("StdOut path:", d.get("StdOut"))
print("--- .out ---\n", ssh.exec(f"tail -10 {d.get('StdOut','')} 2>&1").out)
print("--- .err ---\n", ssh.exec(f"tail -10 {d.get('StdErr','')} 2>&1").out)
ssh.close()
