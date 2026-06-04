import paramiko, warnings, os
warnings.filterwarnings('ignore')
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=20)
def run(cmd, t=90):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read().decode('utf-8','replace') + e.read().decode('utf-8','replace')).strip()
M = '/gpfs/work/bio/jiayu2403/mednca'
JID = '1435378'
print("=== squeue (running?) ==="); print(run('squeue -u jiayu2403 -h') or '(empty = no running job)')
print("\n=== sacct 1435378 ==="); print(run(f'sacct -j {JID} --format=JobID,JobName,State,Elapsed,Start,End,MaxRSS 2>/dev/null'))
print(f"\n=== {JID}.err tail (train progress) ==="); print(run(f'tail -40 {M}/logs/{JID}.err 2>/dev/null'))
print(f"\n=== {JID}.out tail ==="); print(run(f'tail -25 {M}/logs/{JID}.out 2>/dev/null'))
print("\n=== r2_prostate ckpt models ==="); print(run(f'ls -la {M}/checkpoints/r2_prostate/models/ 2>/dev/null'))
print("\n=== all r2 result files on HPC ==="); print(run(f'ls -la {M}/results/ 2>/dev/null | grep -i -E "r2|prost"'))
print("\n=== r2 summary json contents ==="); print(run(f'for f in {M}/results/r2_prostate*summary*.json; do echo "### $f"; cat "$f" 2>/dev/null; echo; done'))
# download any r2 summary + csv
sftp = c.open_sftp()
LOCAL = r'D:\YJ-Agent\project\meeting\Med-NCA\results'
try:
    files = run(f'ls {M}/results/ 2>/dev/null').split()
    for fn in files:
        if 'r2_prostate' in fn and (fn.endswith('.json') or fn.endswith('.csv')):
            try:
                sftp.get(f'{M}/results/{fn}', os.path.join(LOCAL, fn))
                print(f"downloaded: {fn}")
            except Exception as ex:
                print(f"dl fail {fn}: {ex}")
except Exception as ex:
    print("dl err:", ex)
c.close()
