# -*- coding: utf-8 -*-
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import paramiko
HOST="10.7.16.49"; USER="jiayu2403"
creds={}
with open(os.path.expanduser("~/.ssh/xjtlu_hpc_pass.txt")) as f:
    for line in f:
        if "=" in line:
            k,v=line.strip().split("=",1); creds[k]=v
cli=paramiko.SSHClient(); cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
cli.connect(HOST, username=USER, password=creds["PASS"], timeout=30)
def run(c):
    _,o,e=cli.exec_command(c); return o.read().decode()+e.read().decode()
WD="/gpfs/work/bio/jiayu2403/medad-failmap"
print("=== find .out files ===")
print(run(f"find {WD} -name '*.out' -o -name '*.log' 2>/dev/null"))
print("=== full WD tree ===")
print(run(f"ls -la {WD}/ 2>/dev/null"))
print("=== any csv anywhere in WD ===")
print(run(f"find {WD} -name '*.csv' 2>/dev/null"))
print("=== slurm out full (last 60) ===")
print(run(f"cat {WD}/slurm-1451047.out 2>/dev/null | tail -60"))
cli.close()
