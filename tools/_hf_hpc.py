"""HyperFidBench HPC 连接 helper。凭据从 HPC_WORKFLOW.md 读，不进命令行（防泄露）。
用法：from _hf_hpc import conn, run, put  ；或直接 python tools/_hf_hpc.py "<remote cmd>"
"""
import paramiko, warnings, re, pathlib, sys, os
warnings.filterwarnings('ignore')

_wf = pathlib.Path("project/HPC_WORKFLOW.md").read_text(encoding="utf-8")
HOST = re.search(r'`(dtn\.hpc\.xjtlu\.edu\.cn)`', _wf).group(1)
USER = re.search(r'用户名 \| `([^`]+)`', _wf).group(1)
_PW  = re.search(r'密码 \| `([^`]+)`', _wf).group(1)

def conn():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=_PW, timeout=25)
    return c

def run(c, cmd, timeout=120):
    i, o, e = c.exec_command(cmd, timeout=timeout)
    return o.read().decode(errors='replace') + e.read().decode(errors='replace')

def put(c, local, remote):
    sf = c.open_sftp()
    sf.put(local, remote)
    sf.close()
    return f"PUT {local} -> {remote}"

if __name__ == "__main__":
    c = conn()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "whoami; hostname"
    print(run(c, cmd, timeout=int(os.environ.get("HF_TO", "120"))))
    c.close()
