# -*- coding: utf-8 -*-
# Reads HPC password from env var HPCPASS (never hardcoded / committed).
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import paramiko, warnings
warnings.filterwarnings('ignore')
PW = os.environ.get('HPCPASS')
if not PW:
    sys.exit("HPCPASS env var not set")
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password=PW, timeout=20)
def run(cmd, t=40):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode('utf-8', 'replace') + e.read().decode('utf-8', 'replace')
WD = "/gpfs/work/bio/jiayu2403/medad-failmap"
print("=== sacct 1451047 ===")
print(run("sacct -j 1451047 --format=JobID,JobName,State,Elapsed,ExitCode -P 2>/dev/null"))
print("=== squeue active ===")
print(run("squeue -u jiayu2403 2>/dev/null"))
print("=== results/ ===")
print(run(f"ls -la {WD}/results/ 2>/dev/null"))
print("=== all csv in WD ===")
print(run(f"find {WD} -name '*.csv' 2>/dev/null"))
print("=== .out files ===")
print(run(f"find {WD} -maxdepth 2 -name '*.out' 2>/dev/null"))
print("=== slurm out tail ===")
print(run(f"cat {WD}/slurm-1451047.out 2>/dev/null | tail -40"))
c.close()
