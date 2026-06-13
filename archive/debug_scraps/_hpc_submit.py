import paramiko, warnings
warnings.filterwarnings('ignore')

SUBMIT = """#!/bin/bash
#SBATCH --job-name=mednca_r2
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --cpus-per-task=8
#SBATCH --time=24:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/mednca/logs/%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/mednca/logs/%j.err

export MEDNCA_ROOT=/gpfs/work/bio/jiayu2403/mednca
export R2_EPOCHS=300
PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
echo "[submit] host=$(hostname) gpu=$CUDA_VISIBLE_DEVICES start=$(date)"
$PY $MEDNCA_ROOT/code/run_r2_prostate.py
echo "[submit] done=$(date)"
"""

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=15)
def run(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read().decode('utf-8','replace') + e.read().decode('utf-8','replace')).strip()

M = '/gpfs/work/bio/jiayu2403/mednca'
sftp = c.open_sftp()
with sftp.file(f'{M}/submit_r2.sh', 'w') as f:
    f.write(SUBMIT.replace('\r\n', '\n'))
print("submit_r2.sh written")

print("clean ckpt:", run(f'rm -rf {M}/checkpoints/r2_prostate && echo cleaned'))
print("mkdir logs:", run(f'mkdir -p {M}/logs && echo ok'))

PY = '/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python'
imp = (f'cd {M} && MEDNCA_ROOT={M} {PY} -c '
       f'"import sys; sys.path.insert(0,\'{M}/M3D-NCA-official\'); '
       f'sys.path.insert(0,\'{M}/code\'); '
       f'from src.datasets.Nii_Gz_Dataset_3D import Dataset_NiiGz_3D; '
       f'from fast_nca import FastBackboneNCA; '
       f'from src.agents.Agent_Med_NCA import Agent_Med_NCA; '
       f'from src.losses.LossFunctions import DiceBCELoss; '
       f'from src.utils.Experiment import Experiment; print(\'IMPORT OK\')"')
print("=== import smoke (login node) ===")
print(run(imp, t=180))
sftp.close(); c.close()
