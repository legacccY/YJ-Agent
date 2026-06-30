# -*- coding: utf-8 -*-
"""只读核查 predig.sif 入口（runscript / labels）。不改 HPC,不提交,只 inspect+ls。"""
import re, sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
import paramiko

WF = Path(r"D:/YJ-Agent/project/HPC_WORKFLOW.md").read_text(encoding="utf-8", errors="ignore")
HOST = "dtn.hpc.xjtlu.edu.cn"
USER = re.search(r"用户名 \| `(.+?)`", WF).group(1)
PW   = re.search(r"密码 \| `(.+?)`", WF).group(1)
BASE = "/gpfs/work/bio/jiayu2403/quantimmu"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PW, timeout=20)
print(f"[OK] {USER}@{HOST}")

def run(cmd):
    _, o, e = c.exec_command(cmd, timeout=60)
    return o.read().decode("utf-8","ignore").strip(), e.read().decode("utf-8","ignore").strip()

for k, cmd in {
  "sif ls": f"ls -lh {BASE}/sif/predig.sif",
  "runscript": f"singularity inspect --runscript {BASE}/sif/predig.sif 2>&1 | head -40",
  "labels": f"singularity inspect {BASE}/sif/predig.sif 2>&1 | head -40",
  "official_inputs predig": f"ls -la {BASE}/official_inputs/out_official/predig_input*.csv 2>/dev/null; ls -la {BASE}/official_inputs/predig_input*.csv 2>/dev/null",
}.items():
    out, err = run(cmd)
    print(f"\n## {k}\n{out or '(empty)'}" + (f"\n[err]{err[:300]}" if err else ""))
c.close()
