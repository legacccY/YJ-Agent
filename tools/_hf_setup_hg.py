import sys; sys.path.insert(0, "tools")
from _hf_hpc import conn, run, put
c = conn()
ROOT = "/gpfs/work/bio/jiayu2403/hyperfid"
local = "project/meeting/HyperFidBench/hpc_setup_hypergale.sh"
print(put(c, local, f"{ROOT}/hpc_setup_hypergale.sh"))
print(run(c, f"cd {ROOT} && sed -i 's/\\r$//' hpc_setup_hypergale.sh && chmod +x hpc_setup_hypergale.sh && echo dos2unix_ok"))
try:
    run(c, f"cd {ROOT} && nohup bash hpc_setup_hypergale.sh > logs/setup_hypergale.log 2>&1 & echo STARTED", timeout=8)
except Exception:
    pass  # nohup detach 后 channel read 超时正常
print("DISPATCHED hypergale")
c.close()
