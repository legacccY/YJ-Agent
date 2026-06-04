"""HPC Med-NCA 训练实时监控窗口 — R2 prostate 专版
独立运行，不占 Claude token。
与 visienhance 版区别：
  - HPC_BASE 指向 mednca
  - NCA 不打 per-epoch stdout（只写 tensorboard）→ 进度从 ckpt epoch_N 文件推
  - 关键存活信号 = squeue 状态 + GPU 利用率 + 最新 ckpt epoch
用法: python hpc_mednca_gui.py <JOB_ID>
"""
import tkinter as tk
from tkinter import scrolledtext
import threading, time, paramiko, warnings, sys, re
warnings.filterwarnings('ignore')

HOST    = 'dtn.hpc.xjtlu.edu.cn'
USER    = 'jiayu2403'
PASSWD  = 'pxXd3VGhbB'
JOB_ID   = sys.argv[1] if len(sys.argv) > 1 else '1435267'
HPC_BASE = '/gpfs/work/bio/jiayu2403/mednca'
LOG_DIR  = f'{HPC_BASE}/logs'
CKPT_DIR = f'{HPC_BASE}/checkpoints/r2_prostate/models'
TOTAL_EPOCHS = 1000

INTERVAL_FAST = 60     # 启动初期
INTERVAL_SLOW = 300    # 稳定后 5 分钟

ERROR_PATTERNS = [r'\bnan\b', 'cuda out of memory', r'\boom\b', 'outofmemory',
                  'runtimeerror', 'killed', 'error:', 'traceback', 'exception']


def ssh_run(c, cmd, timeout=20):
    try:
        _, o, _ = c.exec_command(cmd, timeout=timeout)
        return o.read().decode('utf-8', errors='replace').strip()
    except Exception as e:
        return f"[ERR: {e}]"


def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWD, timeout=15)
    return c


def fetch_status():
    c = connect()
    job_id = JOB_ID
    log_out = f"{LOG_DIR}/r2full_{job_id}.out"
    log_err = f"{LOG_DIR}/r2full_{job_id}.err"

    status   = ssh_run(c, f"squeue -u {USER} --format='%.10i %.12j %.8T %.10M %R'")
    job_state = ssh_run(c, f"scontrol show job {job_id} 2>/dev/null | grep 'JobState=' | awk -F= '{{print $2}}' | awk '{{print $1}}'")

    # GPU 利用率（基于 jobid，与路径无关）
    gpu_raw = ssh_run(c, f"srun --overlap --jobid={job_id} nvidia-smi dmon -s um -c 6 2>&1", timeout=30)

    # 进度：ckpt epoch_N 文件（每 50 ep 存一次）
    ckpts = ssh_run(c, f"ls {CKPT_DIR} 2>/dev/null")
    epochs_saved = sorted(int(m) for m in re.findall(r'epoch_(\d+)', ckpts)) if ckpts else []
    latest_ckpt = epochs_saved[-1] if epochs_saved else 0

    # .out 关键行（[R2]/[R3]/Dice/train done）
    log_tail = ssh_run(c, f"grep -aE 'R2|R3|Dice|train done|verdict' {log_out} 2>/dev/null | tail -12")

    # 错误检测
    errors = []
    for lg in (log_err, log_out):
        chk = ssh_run(c, f"grep -aiE '{'|'.join(ERROR_PATTERNS)}' {lg} 2>/dev/null | tail -4")
        if chk:
            errors.append(chk)

    c.close()
    return status, gpu_raw, log_tail, latest_ckpt, epochs_saved, errors, job_state, job_id


def format_gpu(gpu_raw):
    sm_vals, membw_vals, fb_mb = [], [], None
    for ln in gpu_raw.split('\n'):
        ln = ln.strip()
        if ln.startswith('#') or not ln:
            continue
        parts = ln.split()
        if len(parts) >= 8:
            try:
                sm_vals.append(int(parts[1])); membw_vals.append(int(parts[2])); fb_mb = int(parts[7])
            except ValueError:
                pass
    if sm_vals:
        peak_sm, avg_sm = max(sm_vals), sum(sm_vals)//len(sm_vals)
        mem_note = f"  显存: {fb_mb} MB / 24564 MB ({fb_mb*100//24564}%)" if fb_mb else ""
        busy = "  ⚠ 采样均 0%（可能在数据加载/eval 间隙）" if peak_sm == 0 else ""
        return (f"  SM 利用率: 峰值 {peak_sm}%  均值 {avg_sm}%  ({len(sm_vals)} 采样)\n"
                f"  显存带宽峰值: {max(membw_vals)}%\n{mem_note}{busy}")
    return f"  {gpu_raw[:300]}"


class MonitorApp:
    def __init__(self, root):
        self.root = root
        root.title(f"Med-NCA R2 监控 — Job {JOB_ID}")
        root.geometry("820x560"); root.configure(bg='#1e1e1e')
        self.status_var = tk.StringVar(value="连接中...")
        tk.Label(root, textvariable=self.status_var, bg='#1e1e1e', fg='#00ff88',
                 font=('Consolas', 10)).pack(pady=4)
        self.text = scrolledtext.ScrolledText(root, bg='#1e1e1e', fg='#d4d4d4',
                 font=('Consolas', 10), wrap=tk.WORD, insertbackground='white')
        self.text.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self.next_var = tk.StringVar(value="")
        tk.Label(root, textvariable=self.next_var, bg='#1e1e1e', fg='#888888',
                 font=('Consolas', 9)).pack(pady=2)
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self._running = False; self.root.destroy()

    def _write(self, content):
        self.text.configure(state='normal'); self.text.delete('1.0', tk.END)
        self.text.insert(tk.END, content); self.text.configure(state='disabled'); self.text.see(tk.END)

    def _loop(self):
        while self._running:
            try:
                self.status_var.set("⟳ 拉取中...")
                status, gpu_raw, log_tail, latest_ckpt, epochs_saved, errors, job_state, job_id = fetch_status()
                now = time.strftime('%H:%M:%S')
                done = job_state in ('COMPLETED',) or 'train done' in log_tail
                is_error = bool(errors) or job_state in ('FAILED', 'CANCELLED', 'TIMEOUT')
                interval = INTERVAL_FAST if latest_ckpt < 50 else INTERVAL_SLOW

                warn = ""
                if is_error:
                    warn = "\n⚠️  异常检测:\n" + "\n".join(errors) + f"\n  JobState: {job_state}\n"

                prog = f"已存 ckpt: {epochs_saved}  最新 epoch_{latest_ckpt}/{TOTAL_EPOCHS}" if epochs_saved else "尚无 ckpt（首 50 ep 内或刚启动）"
                out = (
                    f"══ {now}  Job:{job_id}  最新ckpt:epoch_{latest_ckpt}  ══\n"
                    f"  注: NCA 无 per-epoch stdout，进度看 ckpt(每50ep) + GPU\n"
                    f"{warn}\n"
                    f"【进度】\n  {prog}\n\n"
                    f"【任务状态】\n{status}\n\n"
                    f"【GPU 利用率】\n{format_gpu(gpu_raw)}\n\n"
                    f"【.out 关键行】\n{log_tail or '  (训练中，无输出；结束时打印 Dice/verdict)'}\n"
                )
                self._write(out)

                if done:
                    self.root.configure(bg='#003a1e')
                    self.status_var.set(f"✅ 完成 {now} | Job:{job_state} | 看 .out 的 Dice/verdict")
                elif is_error:
                    self.root.configure(bg='#3a0000')
                    self.status_var.set(f"⚠ 异常! {now} | Job:{job_state}")
                else:
                    self.root.configure(bg='#1e1e1e')
                    self.status_var.set(f"✓ {now} | epoch_{latest_ckpt}/{TOTAL_EPOCHS} | Job:{job_id}")

                for r in range(interval, 0, -1):
                    if not self._running:
                        break
                    self.next_var.set(f"下次刷新: {r}s 后")
                    time.sleep(1)
            except Exception as e:
                self.status_var.set(f"连接失败: {e}，5s 后重试")
                time.sleep(5)
        self.next_var.set("已停止")


if __name__ == '__main__':
    root = tk.Tk()
    app = MonitorApp(root)
    root.mainloop()
