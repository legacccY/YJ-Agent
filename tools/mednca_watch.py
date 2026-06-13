"""Med-NCA HPC job watcher (console popup).
用法: python mednca_watch.py <JOB_ID> [间隔秒=30]
轮询 HPC squeue 存活 + tail logs/r2_<jid>.out, 高亮 Dice/崩溃/完成.
"""
import sys
import time
import warnings

import paramiko

warnings.filterwarnings("ignore")

JID = sys.argv[1] if len(sys.argv) > 1 else "1434734"
INTERVAL = int(sys.argv[2]) if len(sys.argv) > 2 else 30
OUT = f"/gpfs/work/bio/jiayu2403/mednca/logs/r2_{JID}.out"
ERR = f"/gpfs/work/bio/jiayu2403/mednca/logs/r2_{JID}.err"

HOST, USER, PW = "dtn.hpc.xjtlu.edu.cn", "jiayu2403", "pxXd3VGhbB"


def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PW, timeout=15)
    return c


def run(c, cmd, t=30):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8", "replace") + e.read().decode("utf-8", "replace")


def main():
    print(f"=== Med-NCA watch  job={JID}  每 {INTERVAL}s 刷新 ===")
    print(f"out: {OUT}\nCtrl+C 退出\n")
    seen = 0
    while True:
        try:
            c = connect()
            sq = run(c, f"squeue -j {JID} -h -o '%T %M %N' 2>/dev/null").strip()
            gpu = ""
            if sq:
                gpu = run(c, f"srun --overlap --jobid={JID} nvidia-smi "
                             "--query-gpu=utilization.gpu,memory.used,memory.total,"
                             "temperature.gpu,power.draw --format=csv,noheader 2>/dev/null", t=50).strip()
            out = run(c, f"cat {OUT} 2>/dev/null")
            err = run(c, f"tail -n 20 {ERR} 2>/dev/null").strip()
            c.close()
        except Exception as ex:
            print(f"[{time.strftime('%H:%M:%S')}] 连接失败: {ex}")
            time.sleep(INTERVAL)
            continue

        lines = out.splitlines()
        new = lines[seen:]
        seen = len(lines)
        ts = time.strftime("%H:%M:%S")
        if sq:
            st = sq.split()
            state = st[0] if st else "?"
            el = st[1] if len(st) > 1 else "?"
            node = st[2] if len(st) > 2 else "?"
            g = gpu.splitlines()[0] if gpu else "GPU查询无回应"
            print(f"[{ts}] {state} | 已跑 {el} | {node}")
            print(f"         GPU: {g}")
        else:
            sac = ""
            try:
                c = connect()
                sac = run(c, f"sacct -j {JID} --format=State,ExitCode -P -n 2>/dev/null").splitlines()[:1]
                c.close()
            except Exception:
                pass
            print(f"[{ts}] 不在队列 (已结束?)  sacct={sac}")
        for ln in new:
            mark = ""
            low = ln.lower()
            if "dice" in low:
                mark = "  <<< DICE"
            if any(k in ln for k in ("Traceback", "Error", "FAILED", "Killed", "OOM", "assert")):
                mark = "  <<< !!! 崩溃信号"
            print("   " + ln + mark)
        if err and (not sq):
            print("   --- .err tail ---")
            for ln in err.splitlines()[-8:]:
                print("   " + ln)
            print(">>> job 已结束, 停止轮询")
            break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
