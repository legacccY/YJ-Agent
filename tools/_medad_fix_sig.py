# -*- coding: utf-8 -*-
# Install missing statsmodels into HPC env + re-run stratify_significance (CPU).
# Password from env HPCPASS (never hardcoded).
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import paramiko, warnings
warnings.filterwarnings('ignore')
PW = os.environ.get('HPCPASS')
if not PW:
    sys.exit("HPCPASS env var not set")
ROOT = "/gpfs/work/bio/jiayu2403/medad-failmap"
PY = "/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password=PW, timeout=20)
def run(cmd, t=600):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode('utf-8', 'replace') + e.read().decode('utf-8', 'replace')

print("=== pip install statsmodels ===")
print(run(f"{PY} -m pip install statsmodels --quiet 2>&1 | tail -8"))
print("=== verify import ===")
print(run(f"{PY} -c 'import statsmodels; print(statsmodels.__version__)' 2>&1"))
print("=== re-run stratify_significance ===")
print(run(
    f"cd {ROOT} && {PY} code/stratify_significance.py "
    f"--score-csv {ROOT}/results/anomaly_scores_brats_ae.csv "
    f"--strat-per-image-csv {ROOT}/results/stratify_per_image_ae.csv "
    f"--out-csv {ROOT}/results/stratify_significance_FA.csv 2>&1 | tail -30"
))
print("=== FA output ===")
print(run(f"ls -la {ROOT}/results/stratify_significance_FA.csv 2>/dev/null; echo '---'; cat {ROOT}/results/stratify_significance_FA.csv 2>/dev/null"))
c.close()
