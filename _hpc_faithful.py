import paramiko, warnings, re, time
warnings.filterwarnings('ignore')
M = '/gpfs/work/bio/jiayu2403/mednca'
LOCAL = r'D:\YJ-Agent\project\meeting\Med-NCA\code'

FAITHFUL = """#!/bin/bash
#SBATCH --job-name=r2faith
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --cpus-per-task=8
#SBATCH --time=02:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/mednca/logs/faith_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/mednca/logs/faith_%j.err

export MEDNCA_ROOT=/gpfs/work/bio/jiayu2403/mednca
export R2_EPOCHS=20
export R2_LR=16e-4
export R2_GRAD_CLIP=0
export R2_STEPS=64
export R2_MODEL_IMPL=official
export R2_MODEL_TAG=r2_prostate_faithful
PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
echo "[faith] host=$(hostname) start=$(date) | 官方BackboneNCA+无裁剪+lr16e-4+64步"
$PY $MEDNCA_ROOT/code/run_r2_prostate.py
echo "[faith] done=$(date)"
"""

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=15)
def run(cmd, t=180):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read().decode('utf-8','replace') + e.read().decode('utf-8','replace')).strip()

# 串行红线：先确认无运行中 job
q = run('squeue -u jiayu2403 -h')
if q.strip():
    print("!!! 仍有运行中 job，不提交（守单卡串行红线）："); print(q)
    c.close(); raise SystemExit(0)
print("squeue 空闲，可提交")

sftp = c.open_sftp()
sftp.put(LOCAL + r'\run_r2_prostate.py', f'{M}/code/run_r2_prostate.py')
print("uploaded run_r2_prostate.py")
with sftp.file(f'{M}/submit_r2_faith.sh', 'w') as f:
    f.write(FAITHFUL.replace('\r\n', '\n'))

# import 自检（官方 backbone + 官方 agent）
PY = '/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python'
imp = (f'cd {M} && MEDNCA_ROOT={M} {PY} -c '
       f'"import sys; sys.path.insert(0,\'{M}/M3D-NCA-official\'); sys.path.insert(0,\'{M}/code\'); '
       f'from src.models.Model_BackboneNCA import BackboneNCA; '
       f'from src.agents.Agent_Med_NCA import Agent_Med_NCA; print(\'IMPORT OK\')"')
imp_out = run(imp, t=180); print("import:", imp_out)
if 'IMPORT OK' not in imp_out:
    print("import FAIL，不提交"); sftp.close(); c.close(); raise SystemExit(1)

print("clean faithful ckpt:", run(f'rm -rf {M}/checkpoints/r2_prostate_faithful && echo cleaned'))
out = run(f'cd {M} && sbatch submit_r2_faith.sh'); print("sbatch:", out)
m = re.search(r'(\d+)', out)
if m:
    jid = m.group(1)
    open(r'D:\YJ-Agent\_r2faith_jobid.txt','w').write(jid)
    print("JOBID:", jid)
    time.sleep(5); print(run(f'squeue -j {jid}'))
sftp.close(); c.close()
