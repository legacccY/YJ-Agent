"""一次性：把 XJTLU profile + 密码写入应用 store/keyring。
密码不硬编码——从已有的 project/HPC_WORKFLOW.md 表格里读，避免泄漏到命令行/transcript。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.profiles import Profile, ProfileStore

DOC = Path("D:/YJ-Agent/project/HPC_WORKFLOW.md")
text = DOC.read_text(encoding="utf-8")

def cell(label):
    m = re.search(rf"\|\s*{label}\s*\|\s*`?([^`|]+?)`?\s*\|", text)
    return m.group(1).strip() if m else ""

host = cell("主机") or "dtn.hpc.xjtlu.edu.cn"
user = cell("用户名") or "jiayu2403"
pw = cell("密码")
account = cell("账户（SLURM）") or "shuihuawang"
part = cell("分区") or "gpu4090"
qos = cell("QOS") or "4gpus"

if not pw:
    print("ERROR: 没从 HPC_WORKFLOW.md 解析到密码"); sys.exit(1)

s = ProfileStore()
p = Profile(
    name="XJTLU HPC (gpu4090)", host=host, port=22, username=user,
    auth_method="password", slurm_account=account, partition=part, qos=qos,
    default_remote_dir=f"/gpfs/work/bio/{user}/",
    vpn_note="校外必须先连 XJTLU VPN 才能访问该主机。")
s.upsert(p, password=pw)
print("SEEDED:", p.name, "| user=", user, "| host=", host)
print("keyring_available=", s.keyring_available)
print("profiles:", [x.name for x in s.list()])
