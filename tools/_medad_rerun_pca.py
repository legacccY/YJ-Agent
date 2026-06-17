# -*- coding: utf-8 -*-
# Re-upload fixed stratify_eval.py + re-run PC-A (CPU only) on HPC.
# Password from env HPCPASS (never hardcoded).
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import paramiko, warnings
warnings.filterwarnings('ignore')
PW = os.environ.get('HPCPASS')
if not PW:
    sys.exit("HPCPASS env var not set")
LOCAL = r"D:\YJ-Agent\project\meeting\MedAD-FailMap\code\stratify_eval.py"
ROOT = "/gpfs/work/bio/jiayu2403/medad-failmap"
REMOTE = f"{ROOT}/code/stratify_eval.py"
PY = "/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password=PW, timeout=20)

# 1) upload fixed file
sftp = c.open_sftp()
sftp.put(LOCAL, REMOTE)
print(f"[upload] stratify_eval.py -> {REMOTE}")
print("[verify] remote load_mask has _seg_ mapping:",
      "_seg_" in sftp.open(REMOTE).read().decode('utf-8', 'replace'))
sftp.close()

def run(cmd, t=300):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode('utf-8', 'replace') + e.read().decode('utf-8', 'replace')

# 2) re-run stratify_eval (PC-A size/contrast + per-image export)
print("=== re-run stratify_eval ===")
print(run(
    f"cd {ROOT} && {PY} code/stratify_eval.py "
    f"--score-csv {ROOT}/results/anomaly_scores_brats_ae.csv "
    f"--mask-dir {ROOT}/data/BraTS2021/test/annotation "
    f"--tumor-img-dir {ROOT}/data/BraTS2021/test/tumor "
    f"--out-dir {ROOT}/results --model-tag ae 2>&1"
))

# 3) re-run stratify_significance (F-A T1/T2/T3)
print("=== re-run stratify_significance ===")
print(run(
    f"cd {ROOT} && {PY} code/stratify_significance.py "
    f"--score-csv {ROOT}/results/anomaly_scores_brats_ae.csv "
    f"--strat-per-image-csv {ROOT}/results/stratify_per_image_ae.csv "
    f"--out-csv {ROOT}/results/stratify_significance_FA.csv 2>&1 | tail -30"
))

# 4) list new PC-A outputs
print("=== PC-A outputs now ===")
print(run(f"ls -la {ROOT}/results/stratify_* {ROOT}/results/*FA* 2>/dev/null"))
c.close()
