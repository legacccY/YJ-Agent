# -*- coding: utf-8 -*-
"""轮询 HPC 日志直到出现完成/错误标记或超时。用法: python _hpc_wait.py <logname> <done_regex> <max_min>"""
import re,sys,time,warnings
from pathlib import Path
warnings.filterwarnings("ignore")
import paramiko
WF=Path(r"D:/YJ-Agent/project/HPC_WORKFLOW.md").read_text(encoding="utf-8",errors="ignore")
HOST="dtn.hpc.xjtlu.edu.cn";USER=re.search(r"用户名 \| `(.+?)`",WF).group(1);PW=re.search(r"密码 \| `(.+?)`",WF).group(1)
BASE="/gpfs/work/bio/jiayu2403/quantimmu"
log,pat,mx=sys.argv[1],sys.argv[2],float(sys.argv[3])
deadline=time.time()+mx*60
def once():
    c=paramiko.SSHClient();c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST,username=USER,password=PW,timeout=20)
    _,o,_=c.exec_command(f"tail -20 {BASE}/logs/{log} 2>/dev/null",timeout=30)
    t=o.read().decode("utf-8","ignore");c.close();return t
n=0
while time.time()<deadline:
    t=once();n+=1
    if re.search(pat,t):
        print(f"[done @poll{n}]\n{t[-1500:]}");sys.exit(0)
    time.sleep(45)
print(f"[TIMEOUT {mx}min]\n{once()[-1500:]}")
