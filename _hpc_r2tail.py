import paramiko, warnings
warnings.filterwarnings('ignore')
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=15)
def run(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read().decode('utf-8','replace') + e.read().decode('utf-8','replace')).strip()
M = '/gpfs/work/bio/jiayu2403/mednca'
print("=== 1435267.out tail ==="); print(run(f'tail -50 {M}/logs/1435267.out 2>/dev/null'))
print("=== ckpt epochs ==="); print(run(f'ls -la {M}/checkpoints/r2_prostate/models/ 2>/dev/null'))
print("=== prostate result csv on HPC ==="); print(run(f'ls -la {M}/results/ 2>/dev/null | grep -i prost'))
print("=== all recent jobs by me ==="); print(run('sacct -u jiayu2403 --starttime 2026-06-03 --format=JobID,JobName,State,Elapsed,End 2>/dev/null | tail -25'))
c.close()
