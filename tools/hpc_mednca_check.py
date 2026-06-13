"""HPC Med-NCA 训练终端快照监控 — R2 prostate（无 GUI 弹窗版）

替代 hpc_mednca_gui.py：纯终端单次打印，无 tkinter 窗口 → 零黑屏风险。
新增发散检测：loss 死平 + Dice 全 0（hpc_mednca_gui 只查 nan/oom，漏了这种静默发散，
会话 10 的 job 1436075 就是这样烧了 2.5h GPU 没报警）。

用法:
  python hpc_mednca_check.py [JOB_ID]        # 单次快照
  python hpc_mednca_check.py [JOB_ID] watch  # 每 120s 轮询（Ctrl+C 退出）
"""
import sys, re, time, warnings
import paramiko
warnings.filterwarnings('ignore')
try:
    sys.stdout.reconfigure(encoding='utf-8')  # Windows GBK 控制台 emoji 不崩
except Exception:
    pass

HOST, USER, PASSWD = 'dtn.hpc.xjtlu.edu.cn', 'jiayu2403', 'pxXd3VGhbB'
JOB_ID = sys.argv[1] if len(sys.argv) > 1 else open('_r2full_jobid.txt').read().strip()
WATCH  = len(sys.argv) > 2 and sys.argv[2] == 'watch'
B = '/gpfs/work/bio/jiayu2403/mednca'
TOTAL_EPOCHS = 1000


def run(c, cmd, t=40):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode('utf-8', 'replace') + e.read().decode('utf-8', 'replace')


def snapshot():
    c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWD, timeout=20)
    out = f"{B}/logs/r2full_{JOB_ID}.out"

    q = run(c, f"squeue -j {JOB_ID} -h -o '%T %M %R'").strip()
    ckpts = run(c, f"ls {B}/checkpoints/r2_prostate/models/ 2>/dev/null")
    eps = sorted(int(m) for m in re.findall(r'epoch_(\d+)', ckpts)) if ckpts else []
    losses = re.findall(r'(\d+) loss = ([\d.]+)', run(c, f"grep -aE 'loss = ' {out} 2>/dev/null | tail -8"))
    dices = re.findall(r'Average Dice Loss 3d: \d+, ([\d.]+)',
                       run(c, f"grep -a 'Average Dice Loss 3d' {out} 2>/dev/null | tail -6"))
    c.close()

    last_ep = int(losses[-1][0]) if losses else 0
    last_loss = float(losses[-1][1]) if losses else None
    last_dice = float(dices[-1]) if dices else None

    # 发散检测：已过 ep10 且 loss 仍 >3.0（健康起点 ~1.25）+ 最近验证 Dice==0
    diverged = (last_ep >= 10 and last_loss is not None and last_loss > 3.0
                and (last_dice is None or last_dice == 0.0))
    healthy = last_loss is not None and last_loss < 2.0

    now = time.strftime('%H:%M:%S')
    print(f"\n══ {now}  Job {JOB_ID}  ep{last_ep}/{TOTAL_EPOCHS}  ckpt{eps} ══")
    print(f"  队列: {q or '(不在队列 = 已结束/被杀)'}")
    print(f"  最近 loss: {[f'{e}:{v}' for e, v in losses[-5:]]}")
    print(f"  验证 Dice(第二数): {dices or '(暂无)'}")
    if diverged:
        print(f"  🔴 疑似发散! loss 死平 {last_loss:.2f}(健康<2.0) + Dice {last_dice} → 建议 scancel 重提")
    elif healthy:
        print(f"  ✅ 健康收敛中 (loss {last_loss:.2f} < 2.0)")
    else:
        print(f"  ⏳ 观察中 (loss {last_loss}, 需过 ep10 才判发散)")
    return diverged


if __name__ == '__main__':
    if WATCH:
        try:
            while True:
                snapshot(); print("  (下次 120s 后，Ctrl+C 退出)"); time.sleep(120)
        except KeyboardInterrupt:
            print("\n已停止")
    else:
        snapshot()
