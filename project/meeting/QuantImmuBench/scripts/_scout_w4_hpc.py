# -*- coding: utf-8 -*-
import re, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
import paramiko
WF = Path(r"D:/YJ-Agent/project/HPC_WORKFLOW.md").read_text(encoding="utf-8", errors="ignore")
HOST="dtn.hpc.xjtlu.edu.cn"
USER=re.search(r"用户名 \| `(.+?)`", WF).group(1)
PW=re.search(r"密码 \| `(.+?)`", WF).group(1)
BASE="/gpfs/work/bio/jiayu2403/quantimmu"
c=paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST,username=USER,password=PW,timeout=20)
print(f"[连通] {USER}@{HOST} OK")
def run(cmd):
    _,o,e=c.exec_command(cmd,timeout=40)
    return o.read().decode("utf-8","ignore").strip(), e.read().decode("utf-8","ignore").strip()
checks={
"sif镜像": f"ls -la {BASE}/sif/*.sif 2>/dev/null",
"envs": f"ls {BASE}/envs 2>/dev/null",
"tools_repos": f"ls {BASE}/tools_repos 2>/dev/null",
"PredIG": f"ls -d {BASE}/sif/predig.sif {BASE}/tools_repos/PredIG {BASE}/tools_repos/predig* 2>/dev/null",
"pTuneos": f"ls -d {BASE}/sif/ptuneos.sif {BASE}/tools_repos/pTuneos* 2>/dev/null",
"IMPROVE": f"ls -d {BASE}/envs/improve {BASE}/tools_repos/IMPROVE* {BASE}/*improve* 2>/dev/null",
"NeoTImmuML": f"ls -d {BASE}/envs/neotimmuml {BASE}/tools_repos/NeoTImmuML* 2>/dev/null",
"deepHLApan": f"ls -d {BASE}/sif/deephlapan* {BASE}/tools_repos/deephlapan* {BASE}/envs/deephlapan 2>/dev/null",
"Repitope": f"ls -d {BASE}/tools_repos/Repitope* {BASE}/envs/repitope* {BASE}/envs/*R* 2>/dev/null",
"official_inputs": f"ls {BASE}/official_inputs/out_official/ 2>/dev/null | head -40",
"scripts_hpc": f"ls {BASE}/scripts_official 2>/dev/null; ls {BASE}/hpc_official 2>/dev/null",
}
for k,cmd in checks.items():
    out,err=run(cmd)
    print(f"\n## {k}\n{out or '(空)'}"+(f"\n[err] {err[:150]}" if err else ""))
c.close()
