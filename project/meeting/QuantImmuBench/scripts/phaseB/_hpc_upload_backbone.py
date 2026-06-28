# -*- coding: utf-8 -*-
"""Phase B：上传唯一订正源 backbone_101102.csv 到 HPC（所有 HPC 工具从此派生）。
凭证从 HPC_WORKFLOW.md 正则读，绝不硬编。"""
import re, sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
import paramiko

WF = Path(r"D:/YJ-Agent/project/HPC_WORKFLOW.md").read_text(encoding="utf-8", errors="ignore")
HOST = "dtn.hpc.xjtlu.edu.cn"
USER = re.search(r"用户名 \| `(.+?)`", WF).group(1)
PW   = re.search(r"密码 \| `(.+?)`", WF).group(1)
BASE = "/gpfs/work/bio/jiayu2403/quantimmu"
REMOTE_DIR = f"{BASE}/phaseB"
LOCAL = r"D:/YJ-Agent/project/meeting/QuantImmuBench/scripts/out/phaseB/backbone_101102.csv"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PW, timeout=20)
c.exec_command(f"mkdir -p {REMOTE_DIR}")[1].read()
sf = c.open_sftp()
sf.put(LOCAL, f"{REMOTE_DIR}/backbone_101102.csv")
# 核验远端 md5 == 本地
import hashlib
lmd5 = hashlib.md5(Path(LOCAL).read_bytes()).hexdigest()
_, o, _ = c.exec_command(f"md5sum {REMOTE_DIR}/backbone_101102.csv")
rmd5 = o.read().decode().split()[0]
print(f"[上传] backbone_101102.csv → {REMOTE_DIR}/")
print(f"  本地 md5={lmd5}\n  远端 md5={rmd5}\n  {'✅ 一致' if lmd5==rmd5 else '❌ 不一致！'}")
# 远端核 101/102 HLA 订正值
_, o, _ = c.exec_command(
    f"cd {REMOTE_DIR} && python3 -c \""
    f"import csv;rows=list(csv.DictReader(open('backbone_101102.csv')));"
    f"import collections;d=collections.defaultdict(set);"
    f"[d[r['Patient_ID'].split('.')[0]].add(r['HLA_Allele']) for r in rows];"
    f"print('P101',sorted(d['101']));print('P102',sorted(d['102']))\" 2>&1")
print("[远端 HLA 核验]\n" + o.read().decode("utf-8", "ignore").strip())
sf.close(); c.close()
