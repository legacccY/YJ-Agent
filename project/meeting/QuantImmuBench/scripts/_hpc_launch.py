# -*- coding: utf-8 -*-
"""通用 HPC 上传+后台启动器(主线串行用)。
用法: python _hpc_launch.py upload <localfile> <remote_relpath_under_BASE>   # 上传单文件
      python _hpc_launch.py bg <remote_cmd> <logname>                       # setsid 后台跑,日志 BASE/logs/<logname>
      python _hpc_launch.py tail <logname> [n]                              # 看日志尾
      python _hpc_launch.py exec <remote_cmd>                               # 前台跑(短命令),流式
"""
import re,sys,warnings,os
from pathlib import Path
warnings.filterwarnings("ignore")
import paramiko
WF=Path(r"D:/YJ-Agent/project/HPC_WORKFLOW.md").read_text(encoding="utf-8",errors="ignore")
HOST="dtn.hpc.xjtlu.edu.cn";USER=re.search(r"用户名 \| `(.+?)`",WF).group(1);PW=re.search(r"密码 \| `(.+?)`",WF).group(1)
BASE="/gpfs/work/bio/jiayu2403/quantimmu"
c=paramiko.SSHClient();c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST,username=USER,password=PW,timeout=20)
def run(cmd,t=120):
    _,o,e=c.exec_command(cmd,timeout=t);return o.read().decode("utf-8","ignore"),e.read().decode("utf-8","ignore")
mode=sys.argv[1]
if mode=="upload":
    lp,rrel=sys.argv[2],sys.argv[3];rp=f"{BASE}/{rrel}"
    sf=c.open_sftp()
    run(f"mkdir -p {os.path.dirname(rp)}")
    sf.put(lp,rp)
    if rp.endswith((".sh",".py")): run(f"sed -i 's/\r$//' {rp}")
    print(f"[上传] {lp} -> {rp} ({os.path.getsize(lp)}B)")
    sf.close()
elif mode=="bg":
    cmd,log=sys.argv[2],sys.argv[3]
    run(f"mkdir -p {BASE}/logs")
    full=f"cd {BASE} && setsid bash -c '{cmd}' </dev/null > {BASE}/logs/{log} 2>&1 & echo STARTED pid=$!"
    o,e=run(full)
    print(o.strip() or e.strip())
elif mode=="tail":
    log=sys.argv[2];n=sys.argv[3] if len(sys.argv)>3 else "40"
    o,e=run(f"tail -{n} {BASE}/logs/{log} 2>&1; echo '---'; ls -la {BASE}/logs/{log} 2>&1")
    print(o or e)
elif mode=="pull":
    rrel,local=sys.argv[2],sys.argv[3]
    sf=c.open_sftp(); sf.get(f"{BASE}/{rrel}",local); sf.close()
    print(f"[拉回] {BASE}/{rrel} -> {local} ({os.path.getsize(local)}B)")
elif mode=="exec":
    o,e=run(sys.argv[2],t=300);print(o);print("[err]",e[:500] if e else "")
c.close()
