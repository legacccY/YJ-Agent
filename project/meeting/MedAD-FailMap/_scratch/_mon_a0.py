#!/usr/bin/env python
# Monitor poll: HPC job 1451047 (MedAD A0 AE). 每 120s 查 squeue + log，emit 进度/终态。stdout 每行=事件。
import paramiko, warnings, time, sys, re
warnings.filterwarnings('ignore')
HOST, USER, PW = 'dtn.hpc.xjtlu.edu.cn', 'jiayu2403', 'pxXd3VGhbB'
JOB = '1451047'
R = '/gpfs/work/bio/jiayu2403/medad-failmap'
LOG = f'{R}/logs/a0_ae_{JOB}.out'
ERR = f'{R}/logs/a0_ae_{JOB}.err'

def emit(s):
    print(s, flush=True)

def conn():
    c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PW, timeout=30)
    return c

def sh(c, cmd, t=40):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode('utf-8', 'replace').strip()

last = ''
for _ in range(60):  # 60 * 120s = 2h 上限（job time=2h）
    try:
        c = conn()
        st = sh(c, f'squeue -j {JOB} -h -o "%t %M %R" 2>/dev/null')
        if not st:  # job 离队 = 结束
            tail = sh(c, f'tail -8 {LOG} 2>/dev/null')
            errtail = sh(c, f'tail -15 {ERR} 2>/dev/null')
            bad = re.search(r'Traceback|Error|FAILED|assert|Killed|OOM|CUDA', tail + errtail)
            emit(f'[A0 1451047 ENDED] {"⚠️异常" if bad else "✅正常退出"}')
            emit(f'[.out tail]\n{tail}')
            if bad:
                emit(f'[.err tail]\n{errtail}')
            # 看 anomaly score csv 出没出
            csv = sh(c, f'ls -la {R}/results/anomaly_scores_brats_ae.csv 2>/dev/null')
            emit(f'[results] {csv or "anomaly_scores csv 未生成"}')
            gate = sh(c, f'ls {R}/results/*.csv 2>/dev/null | wc -l')
            emit(f'[Gate0 csv 数] {gate}')
            c.close(); break
        # 还在跑：抓 epoch/loss + 崩溃签名
        prog = sh(c, f'grep -oE "Epoch [0-9]+|epoch [0-9]+|loss[:=] *[0-9.]+" {LOG} 2>/dev/null | tail -3')
        crash = sh(c, f'grep -E "Traceback|Error|FAILED|assert|Killed|OOM" {LOG} {ERR} 2>/dev/null | tail -2')
        cur = f'{st} | {prog}'
        if crash:
            emit(f'[A0 ⚠️ 日志现错误] {crash}')
        if cur != last:
            emit(f'[A0 R] {st} || {prog or "(尚无 epoch 输出)"}')
            last = cur
        c.close()
    except Exception as ex:
        emit(f'[mon 异常(忽略继续)] {type(ex).__name__}: {str(ex)[:80]}')
    time.sleep(120)
emit('[mon 退出]')
