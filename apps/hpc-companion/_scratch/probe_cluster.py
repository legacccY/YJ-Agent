"""探集群：分区列表 + 建 test 目录。为实跑测试任务做准备。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.profiles import ProfileStore
from core.ssh_client import SSHClient

s = ProfileStore()
p = s.get("XJTLU HPC (gpu4090)")
ssh = SSHClient()
ssh.connect(p, password=s.get_password(p), timeout=15)

print("=== sinfo 分区 ===")
print(ssh.exec("sinfo --format='%P|%a|%l|%D|%T' 2>&1").out)
print("\n=== 可用 account/qos ===")
print(ssh.exec("sacctmgr -n show assoc user=jiayu2403 format=account,qos%40 2>&1").out)
print("\n=== mkdir test ===")
r = ssh.exec("mkdir -p /gpfs/work/bio/jiayu2403/test/logs && echo OK && ls -la /gpfs/work/bio/jiayu2403/test")
print(r.out or r.err)
ssh.close()
