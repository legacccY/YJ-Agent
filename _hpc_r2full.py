import paramiko, warnings, re, time
warnings.filterwarnings('ignore')
M = '/gpfs/work/bio/jiayu2403/mednca'

FULL = """#!/bin/bash
#SBATCH --job-name=r2_1k
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --cpus-per-task=8
#SBATCH --time=48:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/mednca/logs/r2full_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/mednca/logs/r2full_%j.err

export MEDNCA_ROOT=/gpfs/work/bio/jiayu2403/mednca
export R2_EPOCHS=1000
export R2_LR=16e-4
export R2_GRAD_CLIP=0
export R2_STEPS=64
export R2_MODEL_IMPL=official
export R2_MODEL_TAG=r2_prostate
export PYTHONUNBUFFERED=1
PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
echo "[r2full] host=$(hostname) start=$(date) | 忠实官方: BackboneNCA+无裁剪+lr16e-4+64步+ch32+256+1000ep(论文轮数)"
$PY -u $MEDNCA_ROOT/code/run_r2_prostate.py
echo "[r2full] done=$(date)"
"""

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=15)
def run(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read().decode('utf-8','replace') + e.read().decode('utf-8','replace')).strip()

# 串行红线确认
q = run('squeue -u jiayu2403 -h')
if q.strip():
    print("!!! 仍有 job，不提交:"); print(q); c.close(); raise SystemExit(0)

sftp = c.open_sftp()
with sftp.file(f'{M}/submit_r2_full.sh', 'w') as f:
    f.write(FULL.replace('\r\n', '\n'))
# 清 canonical 目录防 config.dt 陷阱
print("clean r2_prostate:", run(f'rm -rf {M}/checkpoints/r2_prostate && echo cleaned'))
out = run(f'cd {M} && sbatch submit_r2_full.sh'); print("sbatch:", out)
m = re.search(r'(\d+)', out)
if m:
    jid = m.group(1)
    open(r'D:\YJ-Agent\_r2full_jobid.txt','w').write(jid)
    print("JOBID:", jid)
    time.sleep(5); print(run(f'squeue -j {jid}'))
sftp.close(); c.close()
