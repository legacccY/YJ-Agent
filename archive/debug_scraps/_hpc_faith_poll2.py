import paramiko, warnings, time
warnings.filterwarnings('ignore')
jid = open(r'D:\YJ-Agent\_r2faith_jobid.txt').read().strip()
M = '/gpfs/work/bio/jiayu2403/mednca'
def connect():
    c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=15)
    return c
def run(c, cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read().decode('utf-8','replace') + e.read().decode('utf-8','replace')).strip()
# 轮询到 job 结束或最多 ~14 分钟
for _ in range(14):
    time.sleep(60)
    c = connect()
    q = run(c, f'squeue -j {jid} -h 2>/dev/null')
    loss = run(c, f'grep -E "^[0-9]+ loss =" {M}/logs/faith_{jid}.out 2>/dev/null | tail -25')
    verdict = run(c, f'grep -i "R2-single\|R2-pseudo10\|done=" {M}/logs/faith_{jid}.out 2>/dev/null | tail -3')
    c.close()
    if not q.strip():  # job 结束
        print("=== JOB DONE ==="); print("--- loss ---"); print(loss); print("--- verdict ---"); print(verdict)
        break
    if loss.strip():   # buffer 刷出了 loss
        print("=== loss flushed (job still running) ==="); print(loss)
        if verdict.strip(): print("--- verdict ---"); print(verdict)
        break
else:
    print("=== timeout, last state ==="); print("loss:", loss); print("verdict:", verdict)
