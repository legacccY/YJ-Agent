import paramiko, warnings
warnings.filterwarnings('ignore')
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=15)
def run(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read().decode('utf-8','replace') + e.read().decode('utf-8','replace')).strip()
M = '/gpfs/work/bio/jiayu2403/mednca'
print("=== logs dir (recent) ==="); print(run(f'ls -lat {M}/logs/ 2>/dev/null | head -20'))
print("=== r2 prostate summary single ==="); print(run(f'cat {M}/results/r2_prostate_single_summary.json'))
c.close()
