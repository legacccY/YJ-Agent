# -*- coding: utf-8 -*-
"""Phase B HPC 连通 + 部署核查。凭证从 HPC_WORKFLOW.md 正则读，绝不硬编/打印。"""
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
print(f"[连通] {USER}@{HOST} OK")

def run(cmd):
    _, o, e = c.exec_command(cmd, timeout=30)
    return o.read().decode("utf-8", "ignore").strip(), e.read().decode("utf-8", "ignore").strip()

checks = {
    "项目根": f"ls -d {BASE} 2>/dev/null && du -sh {BASE} 2>/dev/null | cut -f1",
    "tools_repos": f"ls {BASE}/tools_repos 2>/dev/null",
    "conda envs": f"ls {BASE}/envs 2>/dev/null",
    "sif 镜像": f"ls -la {BASE}/sif/*.sif 2>/dev/null",
    "ImmuneApp": f"ls -d {BASE}/tools_repos/ImmuneApp {BASE}/envs/immuneapp 2>/dev/null",
    "pTuneos blastdb": f"find {BASE} -path '*blastdb*peptide*' 2>/dev/null | head -3",
    "PRIME+MixMHCpred": f"ls {BASE}/tools_repos/PRIME/PRIME {BASE}/tools_repos/MixMHCpred/MixMHCpred 2>/dev/null",
    "netMHCpan-4.1": f"find {BASE} -iname netMHCpan -type f 2>/dev/null | head -2",
}
for k, cmd in checks.items():
    out, err = run(cmd)
    print(f"\n## {k}\n{out or '(空)'}" + (f"\n[err] {err[:200]}" if err else ""))
c.close()
