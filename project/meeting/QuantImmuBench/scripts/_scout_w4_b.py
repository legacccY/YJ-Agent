# -*- coding: utf-8 -*-
import re, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
import paramiko
WF=Path(r"D:/YJ-Agent/project/HPC_WORKFLOW.md").read_text(encoding="utf-8",errors="ignore")
HOST="dtn.hpc.xjtlu.edu.cn"; USER=re.search(r"用户名 \| `(.+?)`",WF).group(1); PW=re.search(r"密码 \| `(.+?)`",WF).group(1)
BASE="/gpfs/work/bio/jiayu2403/quantimmu"
c=paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST,username=USER,password=PW,timeout=20)
def run(cmd):
    _,o,e=c.exec_command(cmd,timeout=40); return o.read().decode("utf-8","ignore").strip(), e.read().decode("utf-8","ignore").strip()
checks={
"improve.log尾": f"tail -30 {BASE}/improve.log 2>/dev/null",
"hpc_improve.sh": f"cat {BASE}/hpc_improve.sh 2>/dev/null",
"已有official输出csv": f"find {BASE} -name '*_official.csv' 2>/dev/null | head; find {BASE} -name 'IMPROVE*.csv' -o -name 'predig*out*' -o -name 'PredIG*' 2>/dev/null | head",
"IMPROVE_tool结构": f"ls {BASE}/tools_repos/IMPROVE_tool 2>/dev/null; echo '---progs---'; ls {BASE}/improve_programs 2>/dev/null | head",
"NeoTImmuML结构": f"ls {BASE}/tools_repos/NeoTImmuML 2>/dev/null",
"predig.sif内help": f"cd {BASE} && timeout 60 singularity exec sif/predig.sif predig --help 2>&1 | head -20 || echo 'predig cmd fail'",
"newtools内容": f"ls {BASE}/official_inputs/out_official/newtools 2>/dev/null; wc -l {BASE}/official_inputs/out_official/newtools/* 2>/dev/null",
"job队列": f"squeue -u {USER} 2>/dev/null",
}
for k,cmd in checks.items():
    out,err=run(cmd); print(f"\n## {k}\n{out or '(空)'}"+(f"\n[err] {err[:200]}" if err else ""))
c.close()
