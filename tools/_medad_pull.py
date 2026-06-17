# -*- coding: utf-8 -*-
# Pull all Gate0 result csv from HPC -> local results/. Password from env HPCPASS.
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import paramiko, warnings
warnings.filterwarnings('ignore')
PW = os.environ.get('HPCPASS')
if not PW:
    sys.exit("HPCPASS env var not set")
RROOT = "/gpfs/work/bio/jiayu2403/medad-failmap/results"
LDIR = r"D:\YJ-Agent\project\meeting\MedAD-FailMap\results"
os.makedirs(LDIR, exist_ok=True)
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password=PW, timeout=20)
sftp = c.open_sftp()
files = [f for f in sftp.listdir(RROOT) if f.endswith('.csv') or f.endswith('.json')]
for f in sorted(files):
    sftp.get(f"{RROOT}/{f}", os.path.join(LDIR, f))
    print(f"pulled {f}")
sftp.close(); c.close()
print(f"\n[done] {len(files)} files -> {LDIR}")
