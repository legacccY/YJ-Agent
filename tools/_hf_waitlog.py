"""本地短轮询等 HPC 日志出现 pattern。用法: python tools/_hf_waitlog.py <logpath> <pattern> [max_min]"""
import sys, time
sys.path.insert(0, "tools")
from _hf_hpc import conn, run
logpath, pat = sys.argv[1], sys.argv[2]
max_min = int(sys.argv[3]) if len(sys.argv) > 3 else 30
deadline = time.time() + max_min * 60
while time.time() < deadline:
    try:
        c = conn()
        hit = run(c, f"grep -cE '{pat}|FETCH WHEELS DONE|Error|Traceback|No matching|FAILED' {logpath} 2>/dev/null", timeout=30).strip()
        c.close()
    except Exception as ex:
        print("poll err", type(ex).__name__); time.sleep(20); continue
    if hit not in ("0", ""):
        print("LOGHIT"); break
    time.sleep(25)
try:
    c = conn(); print(run(c, f"tail -20 {logpath} 2>/dev/null", timeout=30)); c.close()
except Exception as ex:
    print("tail err", ex)
print("WAITLOG_DONE")
