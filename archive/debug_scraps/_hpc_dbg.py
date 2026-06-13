import paramiko, warnings
warnings.filterwarnings('ignore')
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=15)
def run(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read().decode('utf-8','replace') + e.read().decode('utf-8','replace')).strip()
M = '/gpfs/work/bio/jiayu2403/mednca'
for j in ['1435324','1435325']:
    print(f"=== {j}.out ==="); print(run(f'cat {M}/logs/{j}.out 2>/dev/null'))
    print(f"=== {j}.err (filt) ==="); print(run(f'grep -av "oneDNN\|tensorflow\|RuntimeWarning\|np.sum" {M}/logs/{j}.err 2>/dev/null | tail -15'))
c.close()
