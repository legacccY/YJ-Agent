import paramiko, warnings
warnings.filterwarnings('ignore')
jid = open(r'D:\YJ-Agent\_r2smoke_jobid.txt').read().strip()
M = '/gpfs/work/bio/jiayu2403/mednca'
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=15)
def run(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read().decode('utf-8','replace') + e.read().decode('utf-8','replace')).strip()
print("=== squeue ==="); print(run(f'squeue -j {jid} 2>/dev/null'))
print("=== loss trajectory (per epoch) ==="); print(run(f'grep -E "^[0-9]+ loss =" {M}/logs/smoke_{jid}.out 2>/dev/null'))
print("=== R2 verdict lines ==="); print(run(f'grep -i "R2-\|verdict\|dice_mean\|done=" {M}/logs/smoke_{jid}.out 2>/dev/null | tail -10'))
c.close()
