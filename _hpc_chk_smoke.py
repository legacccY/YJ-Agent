import paramiko, warnings
warnings.filterwarnings('ignore')
jid = open(r'D:\YJ-Agent\_r2faithU_jobid.txt').read().strip()
M = '/gpfs/work/bio/jiayu2403/mednca'
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=15)
def run(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read().decode('utf-8','replace') + e.read().decode('utf-8','replace')).strip()
print("=== 全部我的 job ==="); print(run('squeue -u jiayu2403') or "[空闲]")
print("=== faithU loss + verdict ==="); print(run(f'grep -E "^[0-9]+ loss =|R2-single|R2-pseudo10|done=" {M}/logs/faithU_{jid}.out 2>/dev/null'))
c.close()
