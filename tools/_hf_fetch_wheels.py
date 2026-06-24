import sys; sys.path.insert(0, "tools")
from _hf_hpc import conn, run, put
c = conn()
ROOT = "/gpfs/work/bio/jiayu2403/hyperfid"
put(c, "project/meeting/HyperFidBench/hpc_fetch_wheels.sh", f"{ROOT}/hpc_fetch_wheels.sh")
print(run(c, f"cd {ROOT} && sed -i 's/\\r$//' hpc_fetch_wheels.sh && chmod +x hpc_fetch_wheels.sh && echo ok"))
try:
    run(c, f"cd {ROOT} && nohup bash hpc_fetch_wheels.sh > logs/fetch_wheels.log 2>&1 & echo STARTED", timeout=8)
except Exception:
    pass
print("DISPATCHED fetch_wheels")
c.close()
