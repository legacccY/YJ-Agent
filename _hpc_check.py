import paramiko, warnings, sys
warnings.filterwarnings('ignore')
jid = open(r'D:\YJ-Agent\_r2_jobid.txt').read().strip()
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=15)
def run(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read().decode('utf-8','replace') + e.read().decode('utf-8','replace')).strip()
M = '/gpfs/work/bio/jiayu2403/mednca'
print("=== squeue ==="); print(run(f'squeue -j {jid}'))
print(f"=== {jid}.out ==="); print(run(f'cat {M}/logs/{jid}.out 2>/dev/null | head -40'))
print(f"=== {jid}.err (filtered) ==="); print(run(f'grep -av "oneDNN\\|tensorflow\\|float" {M}/logs/{jid}.err 2>/dev/null | tail -30'))
c.close()
