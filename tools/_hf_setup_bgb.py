import sys; sys.path.insert(0, "tools")
from _hf_hpc import conn, run, put
c = conn()
ROOT = "/gpfs/work/bio/jiayu2403/hyperfid"
print(run(c, f"mkdir -p {ROOT}/logs && echo mkdir_ok"))
local = "project/meeting/HyperFidBench/hpc_setup_braingb.sh"
print(put(c, local, f"{ROOT}/hpc_setup_braingb.sh"))
# dos2unix (去 CRLF) + 后台跑
print(run(c, f"cd {ROOT} && sed -i 's/\\r$//' hpc_setup_braingb.sh && chmod +x hpc_setup_braingb.sh && echo dos2unix_ok"))
print(run(c, f"cd {ROOT} && nohup bash hpc_setup_braingb.sh > logs/setup_braingb.log 2>&1 & echo STARTED pid=$!"))
c.close()
print("DISPATCHED")
