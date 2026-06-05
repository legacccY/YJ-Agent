"""R2 多 seed 扫描监控 — 一次快照 5 个 seed job，逐个发散检测。

读 _r2seed_jobids.txt（每行 "seed jid"）。发散 signature: 过 ep10 loss>3 + 验证 Dice==0。
用法: python hpc_r2seed_check.py
输出: 每 seed 一行 [seed jid 队列态 ep loss dice 判定]，发散的列出 scancel 建议。
"""
import re, sys, warnings
import paramiko
warnings.filterwarnings('ignore')
try:
    sys.stdout.reconfigure(encoding='utf-8')  # Windows GBK 控制台 emoji 不崩
except Exception:
    pass
HOST, USER, PASSWD = 'dtn.hpc.xjtlu.edu.cn', 'jiayu2403', 'pxXd3VGhbB'
B = '/gpfs/work/bio/jiayu2403/mednca'

pairs = []
for ln in open(r'D:\YJ-Agent\_r2seed_jobids.txt'):
    s, j = ln.split()
    pairs.append((int(s), j))

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWD, timeout=20)
def run(cmd, t=40):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode('utf-8', 'replace') + e.read().decode('utf-8', 'replace')

qall = run("squeue -u jiayu2403 -h -o '%i %T %M %R'")
qmap = {}
for ln in qall.strip().splitlines():
    p = ln.split(None, 3)
    if p: qmap[p[0]] = (p[1], p[2] if len(p) > 2 else '', p[3] if len(p) > 3 else '')

print(f"\n{'seed':<5}{'jobid':<10}{'state':<10}{'ep':<7}{'loss':<9}{'dice':<9}verdict")
diverged, done = [], []
for seed, jid in pairs:
    out = f"{B}/logs/r2seed_{seed}_{jid}.out"
    st = qmap.get(jid, ('GONE', '', ''))
    losses = re.findall(r'(\d+) loss = ([\d.]+)', run(f"grep -aE 'loss = ' {out} 2>/dev/null | tail -4"))
    dices = re.findall(r'Average Dice Loss 3d: \d+, ([\d.]+)',
                       run(f"grep -a 'Average Dice Loss 3d' {out} 2>/dev/null | tail -3"))
    ep = int(losses[-1][0]) if losses else 0
    loss = float(losses[-1][1]) if losses else None
    dice = float(dices[-1]) if dices else None
    verdict = '...'
    if st[0] == 'PENDING':
        verdict = 'PENDING'
    elif st[0] == 'GONE':
        verdict = 'FINISHED/eval?'
        done.append((seed, jid))
    elif ep >= 10 and loss is not None and loss > 3.0 and (dice is None or dice < 0.05):
        verdict = '🔴 DIVERGED'  # 含中途崩：loss>3 + Dice 塌(<0.05)，seed43 ep61 跳崖 0.004 验证
        diverged.append((seed, jid))
    elif loss is not None and loss < 2.0:
        verdict = '✅ healthy'
    elif ep < 10:
        verdict = 'warmup'
    print(f"{seed:<5}{jid:<10}{st[0]:<10}{ep:<7}{str(round(loss,3) if loss else '-'):<9}"
          f"{str(round(dice,3) if dice is not None else '-'):<9}{verdict}")

if diverged:
    ids = ' '.join(j for _, j in diverged)
    print(f"\n🔴 发散: {[(s,j) for s,j in diverged]}")
    print(f"   早杀省 GPU: scancel {ids}")
if done:
    print(f"\n🏁 已结束(查 eval 结果): {done}")
c.close()
