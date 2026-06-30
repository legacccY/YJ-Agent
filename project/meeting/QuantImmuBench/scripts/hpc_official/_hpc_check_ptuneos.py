# -*- coding: utf-8 -*-
"""只读 HPC 核查 pTuneos 官方数据补跑前置（绝不上传/sbatch/rm/改）。
凭证从 HPC_WORKFLOW.md 正则读，绝不硬编/打印。"""
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
c.connect(HOST, username=USER, password=PW, timeout=25)
print(f"[连通] {USER}@{HOST} OK")

def run(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8", "ignore").strip(), e.read().decode("utf-8", "ignore").strip()

checks = {
    "sif 镜像": f"ls -la {BASE}/sif/*.sif 2>/dev/null",
    "singularity 可用": "command -v singularity apptainer 2>/dev/null; module avail singularity 2>&1 | head -5",
    "sif inspect runscript": f"singularity inspect --runscript {BASE}/sif/ptuneos.sif 2>&1 | head -20 || apptainer inspect --runscript {BASE}/sif/ptuneos.sif 2>&1 | head -20",
    "sif 内 pTuneos 目录": f"singularity exec {BASE}/sif/ptuneos.sif ls -d /root/pTuneos /root/pTuneos/train_model 2>&1 | head -10",
    "sif 内 train_model 文件": f"singularity exec {BASE}/sif/ptuneos.sif ls -la /root/pTuneos/train_model 2>&1 | head -20",
    "sif 内 netMHCpan": f"singularity exec {BASE}/sif/ptuneos.sif bash -c 'ls -d /root/software/netMHCpan-4.0 /root/software/netMHCpan-4.1 2>/dev/null; which netMHCpan 2>/dev/null' 2>&1 | head -10",
    "sif 内 blastp + python": f"singularity exec {BASE}/sif/ptuneos.sif bash -c 'which blastp python python2 python2.7 2>/dev/null; python --version 2>&1; python2 --version 2>&1' 2>&1 | head -10",
    "blastdb on HPC": f"find {BASE} -path '*peptide_database*' -name 'peptide.p*' 2>/dev/null | head -5; find {BASE} -name 'peptide.pin' 2>/dev/null | head -5",
    "official_inputs 目录": f"ls -la {BASE}/official_inputs 2>/dev/null | head -20",
    "ptuneos 既有输入痕迹": f"find {BASE} -iname 'ptuneos*input*' -o -iname '*pre_recneo*' 2>/dev/null | head -10",
}
for k, cmd in checks.items():
    out, err = run(cmd)
    print(f"\n## {k}\n{out or '(空)'}" + (f"\n[err] {err[:300]}" if err else ""))
c.close()
print("\n[完成] 只读核查结束")
