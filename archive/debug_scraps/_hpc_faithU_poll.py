import paramiko, warnings, time
warnings.filterwarnings('ignore')
jid = open(r'D:\YJ-Agent\_r2faithU_jobid.txt').read().strip()
M = '/gpfs/work/bio/jiayu2403/mednca'
def connect():
    c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=15); return c
def run(c, cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read().decode('utf-8','replace') + e.read().decode('utf-8','replace')).strip()
for _ in range(12):
    time.sleep(75)
    c = connect()
    q = run(c, f'squeue -j {jid} -h 2>/dev/null')
    loss = run(c, f'grep -E "^[0-9]+ loss =" {M}/logs/faithU_{jid}.out 2>/dev/null')
    verdict = run(c, f'grep -i "R2-single\|done=" {M}/logs/faithU_{jid}.out 2>/dev/null | tail -2')
    c.close()
    nloss = len([l for l in loss.splitlines() if l.strip()])
    if not q.strip():
        print("=== JOB DONE ==="); print(loss); print("--- verdict ---"); print(verdict); break
    if nloss >= 3:  # 看到 >=3 epoch loss 够判趋势
        print(f"=== {nloss} epochs loss (still running) ==="); print(loss); break
else:
    print("=== timeout ==="); print("loss:", loss or "[空-仍缓冲/慢]")
