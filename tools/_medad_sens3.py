# -*- coding: utf-8 -*-
# 三档阈值敏感性扫描 {P95/P90/P85} for PC-A + PC-C. Re-upload changed scripts + run.
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
CODE = r"D:\YJ-Agent\project\meeting\MedAD-FailMap\code"
RES = f"{ROOT}/results"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password=PW, timeout=20)
sftp = c.open_sftp()
for fn in ("incremental_stats.py", "failure_boundary.py"):
    sftp.put(os.path.join(CODE, fn), f"{ROOT}/code/{fn}")
    print(f"[upload] {fn}")
sftp.close()

def run(cmd, t=400):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode('utf-8', 'replace') + e.read().decode('utf-8', 'replace')

for pct in (95, 90, 85):
    od = f"{RES}/sens_p{pct}"
    print(f"\n########## threshold P{pct} ##########")
    print(run(f"mkdir -p {od}"))
    # PC-A: stratify_significance (T1/T2/T3 F-A)
    print(f"--- PC-A stratify_significance P{pct} ---")
    print(run(
        f"cd {ROOT} && {PY} code/stratify_significance.py "
        f"--score-csv {RES}/anomaly_scores_brats_ae.csv "
        f"--strat-per-image-csv {RES}/stratify_per_image_ae.csv "
        f"--out-csv {od}/stratify_significance_FA.csv "
        f"--threshold-pct {pct} 2>&1 | tail -8"
    ))
    # PC-C: incremental_stats (C2/C3 + FC family)
    print(f"--- PC-C incremental_stats P{pct} ---")
    print(run(
        f"cd {ROOT} && {PY} code/incremental_stats.py "
        f"--conspicuity-csv {RES}/conspicuity_features_tumor.csv "
        f"--normal-conspicuity-csv {RES}/conspicuity_features_normal.csv "
        f"--score-csv {RES}/anomaly_scores_brats_ae.csv "
        f"--stratify-csv {RES}/stratify_interact_ae.csv "
        f"--out-dir {od} --threshold-pct {pct} 2>&1 | tail -12"
    ))

print("\n\n========== SUMMARY: FA + FC_family across 三档 ==========")
for pct in (95, 90, 85):
    od = f"{RES}/sens_p{pct}"
    print(f"\n===== P{pct} stratify_significance_FA.csv =====")
    print(run(f"cat {od}/stratify_significance_FA.csv"))
    print(f"===== P{pct} incremental_FC_family_holm.csv =====")
    print(run(f"cat {od}/incremental_FC_family_holm.csv"))
c.close()
