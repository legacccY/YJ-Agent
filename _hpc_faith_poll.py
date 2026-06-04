import paramiko, warnings, time
warnings.filterwarnings('ignore')
time.sleep(380)
jid = open(r'D:\YJ-Agent\_r2faith_jobid.txt').read().strip()
M = '/gpfs/work/bio/jiayu2403/mednca'
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=15)
def run(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read().decode('utf-8','replace') + e.read().decode('utf-8','replace')).strip()
print("=== squeue ==="); print(run(f'squeue -j {jid} 2>/dev/null'))
print("=== config echo ==="); print(run(f'grep -i "\[R2\] impl\|\[faith\]" {M}/logs/faith_{jid}.out 2>/dev/null'))
print("=== loss trajectory ==="); print(run(f'grep -E "^[0-9]+ loss =" {M}/logs/faith_{jid}.out 2>/dev/null'))
print("=== verdict ==="); print(run(f'grep -i "R2-single\|done=" {M}/logs/faith_{jid}.out 2>/dev/null | tail -3'))
c.close()
