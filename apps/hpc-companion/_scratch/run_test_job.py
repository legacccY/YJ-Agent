"""实跑测试任务，验证 submit→monitor 整条链（用 GUI 同款后端 core.slurm）。
- 1 个成功任务（echo+sleep+写文件）
- 1 个报错任务（set -e + 不存在命令 → FAILED）
观察：排队→运行→结束/失败 的状态，以及日志/退出码怎么取。
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.profiles import ProfileStore
from core.ssh_client import SSHClient
from core import slurm

s = ProfileStore()
p = s.get("XJTLU HPC (gpu4090)")
ssh = SSHClient()
ssh.connect(p, password=s.get_password(p), timeout=15)
print("connected:", ssh.is_alive())

WD = "/gpfs/work/bio/jiayu2403/test"

# --- 先验证远端导航后端（转到/双击底层用的就是这俩）---
print("\n=== 远端导航后端测试 ===")
real = ssh.normalize(WD)
print("normalize:", real)
print("listdir:", [(e.name, e.is_dir) for e in ssh.listdir(real)])

# --- 成功任务 ---
ok_spec = slurm.SbatchSpec(
    job_name="hpc_ok", account="shuihuawang", partition="cpudebug",
    qos="cpudebug", nodes=1, ntasks=1, cpus_per_task=2, gpus=0,
    time_limit="00:05:00", workdir=WD,
    command='echo "hello from HPC"; hostname; date; sleep 15; echo DONE > result.txt; echo finished')
# --- 报错任务 ---
fail_spec = slurm.SbatchSpec(
    job_name="hpc_fail", account="shuihuawang", partition="cpudebug",
    qos="cpudebug", nodes=1, ntasks=1, cpus_per_task=2, gpus=0,
    time_limit="00:05:00", workdir=WD,
    command='set -e; echo "start"; this_cmd_does_not_exist_xyz; echo "unreachable"')

ids = {}
for tag, spec, path in [("OK", ok_spec, f"{WD}/submit_ok.sh"),
                        ("FAIL", fail_spec, f"{WD}/submit_fail.sh")]:
    r = slurm.submit_script(ssh, path, slurm.build_sbatch(spec))
    jid = slurm.parse_submitted_job_id(r.out)
    ids[tag] = jid
    print(f"\n[{tag}] submit rc={r.rc} -> {r.out.strip()}  jobid={jid}")

# --- 轮询直到都结束 ---
print("\n=== 轮询状态（每 5s）===")
pending = set(ids.values())
for _ in range(40):
    if not pending:
        break
    line = []
    for tag, jid in ids.items():
        st = slurm.parse_scontrol(ssh.exec(slurm.detail_cmd(jid)).out).get("JobState", "?")
        line.append(f"{tag}({jid})={st}")
        if st in ("COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "?"):
            pending.discard(jid)
    print(time.strftime("%H:%M:%S"), " | ".join(line))
    if pending:
        time.sleep(5)

# --- 最终：sacct 退出码 + 日志 ---
print("\n=== 最终状态 (sacct) ===")
for tag, jid in ids.items():
    sa = ssh.exec(f"sacct -j {jid} --format=JobID,JobName,State,ExitCode -n 2>&1").out
    print(f"[{tag}]\n{sa}")

print("\n=== 日志 (GUI 用 scontrol StdOut/StdErr 路径取) ===")
for tag, jid in ids.items():
    d = slurm.parse_scontrol(ssh.exec(slurm.detail_cmd(jid)).out)
    so, se = d.get("StdOut", ""), d.get("StdErr", "")
    print(f"\n--- [{tag}] StdOut={so}")
    print(ssh.exec(f"tail -8 {so} 2>&1").out)
    if se and se != so:
        print(f"--- [{tag}] StdErr={se}")
        print(ssh.exec(f"tail -8 {se} 2>&1").out)

print("\n=== test 目录最终内容 ===")
print(ssh.exec(f"ls -la {WD}").out)
ssh.close()
