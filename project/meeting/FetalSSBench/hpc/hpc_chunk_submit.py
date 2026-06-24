#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""取消 monolith 1491207，重传 patched harness + chunk sbatch，提 10 个 chunk(method x dataset)。"""
import paramiko, os
SC=r"C:\Users\yj200\AppData\Local\Temp\claude\D--YJ-Agent\f4261f6b-bb70-4a57-bee4-68009ddb5d3f\scratchpad"
SRC=r"D:\YJ-Agent\project\meeting\FetalSSBench\src"
R="/gpfs/work/bio/jiayu2403/fetalss"
METHODS=["supervised","mean_teacher","cps","uamt","fixmatch"]
DATASETS=["psfhs","hc18"]
c=paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("dtn.hpc.xjtlu.edu.cn",username="jiayu2403",password="pxXd3VGhbB",timeout=30)
def run(cmd):
    i,o,e=c.exec_command(cmd); return o.read().decode(errors="replace"), e.read().decode(errors="replace")
# 1) 取消 monolith
o,_=run("scancel 1491207"); print("[scancel 1491207]", o.strip() or "ok")
# 2) 重传 patched harness.py + chunk sbatch (去CRLF)
sftp=c.open_sftp()
d=open(os.path.join(SRC,"harness.py"),"rb").read().replace(b"\r\n",b"\n")
with sftp.open(f"{R}/code/harness.py","wb") as f: f.write(d)
print("[reup] harness.py", len(d))
sb=open(os.path.join(SC,"sbatch_chunk.sh"),"rb").read().replace(b"\r\n",b"\n")
with sftp.open(f"{R}/sbatch_chunk.sh","wb") as f: f.write(sb)
sftp.close()
# 3) 提 10 chunk
jids=[]
for M in METHODS:
    for DS in DATASETS:
        o,e=run(f"cd {R} && sbatch --job-name=fss_{M}_{DS} --export=ALL,M={M},DS={DS} sbatch_chunk.sh")
        jid=o.strip().split()[-1] if "Submitted" in o else f"ERR({e.strip()[:40]})"
        jids.append((f"{M}_{DS}", jid)); print(f"[chunk {M}_{DS}]", o.strip())
c.close()
print("CHUNKS_SUBMITTED", len(jids))
print("JIDS", jids)
