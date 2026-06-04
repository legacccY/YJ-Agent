import paramiko, warnings
warnings.filterwarnings('ignore')
jid = open(r'D:\YJ-Agent\_r2faith_jobid.txt').read().strip()
M = '/gpfs/work/bio/jiayu2403/mednca'
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=15)
def run(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read().decode('utf-8','replace') + e.read().decode('utf-8','replace')).strip()
print("=== squeue (elapsed) ==="); print(run(f'squeue -j {jid} -o "%.10i %.8T %.10M %.12L %R" 2>/dev/null'))
print("=== ckpt 进度（epoch_N 出现=训到该轮） ==="); print(run(f'ls {M}/checkpoints/r2_prostate_faithful/models/ 2>/dev/null'))
print("=== out 文件大小/尾 ==="); print(run(f'ls -la {M}/logs/faith_{jid}.out 2>/dev/null; tail -3 {M}/logs/faith_{jid}.out 2>/dev/null'))
print("=== 节点 GPU 占用 ==="); print(run(f'srun --jobid={jid} nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader 2>/dev/null', t=30))
c.close()
