"""本地短轮询等 HPC job 完成（每次重连，避开单 channel 长超时）。
用法: python tools/_hf_waitjob.py <jobid> <logpath> <done_pattern> [max_min]
"""
import sys, time
sys.path.insert(0, "tools")
from _hf_hpc import conn, run

jobid = sys.argv[1]
logpath = sys.argv[2]
done_pat = sys.argv[3]
max_min = int(sys.argv[4]) if len(sys.argv) > 4 else 90

deadline = time.time() + max_min * 60
last = ""
while time.time() < deadline:
    try:
        c = conn()
        st = run(c, f"squeue -j {jobid} -h -o '%T %M' 2>/dev/null", timeout=30).strip()
        hit = run(c, f"grep -cE '{done_pat}|Error|Traceback|No matching distribution' {logpath} 2>/dev/null", timeout=30).strip()
        c.close()
    except Exception as ex:
        print("poll err:", type(ex).__name__); time.sleep(20); continue
    last = st
    if not st or st.startswith("CG") or hit not in ("0", ""):
        print(f"STOP: job_state='{st}' loghit={hit}")
        break
    time.sleep(25)
# 最终 tail
try:
    c = conn()
    print("=== LOG TAIL ===")
    print(run(c, f"tail -18 {logpath} 2>/dev/null", timeout=30))
    c.close()
except Exception as ex:
    print("tail err:", ex)
print("WAITJOB_DONE")
