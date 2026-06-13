import paramiko, warnings, re, time
warnings.filterwarnings('ignore')
M = '/gpfs/work/bio/jiayu2403/mednca'
old = open(r'D:\YJ-Agent\_r2faith_jobid.txt').read().strip()

FAITH_U = """#!/bin/bash
#SBATCH --job-name=r2faithU
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --cpus-per-task=8
#SBATCH --time=02:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/mednca/logs/faithU_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/mednca/logs/faithU_%j.err

export MEDNCA_ROOT=/gpfs/work/bio/jiayu2403/mednca
export R2_EPOCHS=5
export R2_LR=16e-4
export R2_GRAD_CLIP=0
export R2_STEPS=64
export R2_MODEL_IMPL=official
export R2_MODEL_TAG=r2_prostate_faithU
export PYTHONUNBUFFERED=1
PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
echo "[faithU] host=$(hostname) start=$(date) | 官方原版+无裁剪+lr16e-4+64步+unbuffered+5ep"
$PY -u $MEDNCA_ROOT/code/run_r2_prostate.py
echo "[faithU] done=$(date)"
"""

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=15)
def run(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read().decode('utf-8','replace') + e.read().decode('utf-8','replace')).strip()

# 1) kill 旧忠实 job（慢+缓冲，无信号）
print("scancel old:", run(f'scancel {old} && echo done'))
time.sleep(8)
print("squeue after cancel:", run('squeue -u jiayu2403 -h') or "[空]")

sftp = c.open_sftp()
with sftp.file(f'{M}/submit_r2_faithU.sh', 'w') as f:
    f.write(FAITH_U.replace('\r\n', '\n'))
print("clean ckpt:", run(f'rm -rf {M}/checkpoints/r2_prostate_faithU && echo cleaned'))

out = run(f'cd {M} && sbatch submit_r2_faithU.sh'); print("sbatch:", out)
m = re.search(r'(\d+)', out)
if m:
    jid = m.group(1)
    open(r'D:\YJ-Agent\_r2faithU_jobid.txt','w').write(jid)
    print("JOBID:", jid)
sftp.close(); c.close()
