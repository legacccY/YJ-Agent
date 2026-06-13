import paramiko, warnings, re, time
warnings.filterwarnings('ignore')
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=15)
def run(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read().decode('utf-8','replace') + e.read().decode('utf-8','replace')).strip()
M = '/gpfs/work/bio/jiayu2403/mednca'
out = run(f'cd {M} && sbatch submit_r2.sh')
print("sbatch:", out)
m = re.search(r'(\d+)', out)
if m:
    jid = m.group(1)
    print("JOBID:", jid)
    with open(r'D:\YJ-Agent\_r2_jobid.txt', 'w') as f:
        f.write(jid)
    time.sleep(5)
    print("=== squeue ==="); print(run(f'squeue -u jiayu2403'))
c.close()
