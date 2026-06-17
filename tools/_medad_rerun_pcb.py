# -*- coding: utf-8 -*-
# Re-upload fixed failure_boundary.py + re-run PC-B (CPU only). Password from env HPCPASS.
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import paramiko, warnings
warnings.filterwarnings('ignore')
PW = os.environ.get('HPCPASS')
if not PW:
    sys.exit("HPCPASS env var not set")
LOCAL = r"D:\YJ-Agent\project\meeting\MedAD-FailMap\code\failure_boundary.py"
ROOT = "/gpfs/work/bio/jiayu2403/medad-failmap"
REMOTE = f"{ROOT}/code/failure_boundary.py"
PY = "/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password=PW, timeout=20)
sftp = c.open_sftp()
sftp.put(LOCAL, REMOTE)
remote_txt = sftp.open(REMOTE).read().decode('utf-8', 'replace')
print(f"[upload] failure_boundary.py -> {REMOTE}")
print("[verify] default brats-strat-csv = per_image:",
      "stratify_per_image_ae.csv" in remote_txt and "stratify_interact_ae.csv" not in remote_txt.split("brats-strat-csv")[1].split("help")[0])
sftp.close()

def run(cmd, t=300):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode('utf-8', 'replace') + e.read().decode('utf-8', 'replace')

print("=== re-run failure_boundary ===")
print(run(f"cd {ROOT} && {PY} code/failure_boundary.py 2>&1 | tail -30"))
print("=== B1 coefs ===")
print(run(f"cat {ROOT}/results/boundary_B1_coefs.csv"))
print("=== B3 baseline ===")
print(run(f"cat {ROOT}/results/boundary_B3_baseline.csv"))
print("=== B4 extrapolation ===")
print(run(f"cat {ROOT}/results/boundary_B4_extrapolation.csv"))
c.close()
