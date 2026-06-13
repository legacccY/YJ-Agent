import paramiko, warnings
warnings.filterwarnings('ignore')
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=20)
def run(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read().decode('utf-8','replace') + e.read().decode('utf-8','replace')).strip()
M = '/gpfs/work/bio/jiayu2403/mednca'
print("=== logs dir r2full ==="); print(run(f'ls -la {M}/logs/ 2>/dev/null | grep -iE "r2full|1435378"'))
for ext in ['out','err']:
    print(f"\n===== r2full_1435378.{ext} : loss/epoch lines =====")
    print(run(f'grep -niE "loss|epoch|dice" {M}/logs/r2full_1435378.{ext} 2>/dev/null'))
c.close()
