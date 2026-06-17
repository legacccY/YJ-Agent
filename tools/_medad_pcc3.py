# -*- coding: utf-8 -*-
# PC-C 三档重跑，修正 --stratify-csv 接 per_image (有真 size_px/contrast). Pwd from env HPCPASS.
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import paramiko, warnings
warnings.filterwarnings('ignore')
PW = os.environ.get('HPCPASS')
if not PW:
    sys.exit("HPCPASS env var not set")
ROOT = "/gpfs/work/bio/jiayu2403/medad-failmap"
PY = "/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python"
RES = f"{ROOT}/results"
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password=PW, timeout=20)
def run(cmd, t=400):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode('utf-8', 'replace') + e.read().decode('utf-8', 'replace')
for pct in (95, 90, 85):
    od = f"{RES}/sens_p{pct}"
    print(f"\n########## PC-C P{pct} (stratify-csv = per_image) ##########")
    print(run(
        f"cd {ROOT} && {PY} code/incremental_stats.py "
        f"--conspicuity-csv {RES}/conspicuity_features_tumor.csv "
        f"--normal-conspicuity-csv {RES}/conspicuity_features_normal.csv "
        f"--score-csv {RES}/anomaly_scores_brats_ae.csv "
        f"--stratify-csv {RES}/stratify_per_image_ae.csv "
        f"--out-dir {od} --threshold-pct {pct} 2>&1 | tail -14"
    ))
print("\n\n========== SUMMARY: FC_family across 三档 ==========")
for pct in (95, 90, 85):
    od = f"{RES}/sens_p{pct}"
    print(f"\n===== P{pct} incremental_FC_family_holm.csv =====")
    print(run(f"cat {od}/incremental_FC_family_holm.csv"))
c.close()
