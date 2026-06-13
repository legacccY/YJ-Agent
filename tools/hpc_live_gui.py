"""HPC 训练实时监控窗口 — 独立运行，不占 Claude token
前 2 epoch: 每 60 秒刷新
之后: 每 15 分钟刷新
"""
import tkinter as tk
from tkinter import scrolledtext
import threading, time, paramiko, warnings, sys
warnings.filterwarnings('ignore')

HOST    = 'dtn.hpc.xjtlu.edu.cn'
USER    = 'jiayu2403'
PASSWD  = 'pxXd3VGhbB'
JOB_ID   = sys.argv[1] if len(sys.argv) > 1 else '1433529'  # VisiEnhance Stage 2, 4xGPU DDP
HPC_BASE = '/gpfs/work/bio/jiayu2403/visienhance'
LOG_DIR  = f'{HPC_BASE}/logs'
STATE_FILE = f'{LOG_DIR}/experiment_state.json'

INTERVAL_FAST = 60    # epoch < 2 时
INTERVAL_SLOW = 300   # epoch >= 2 时（5 分钟）

# 错误关键词（用 \b 词边界防止 [INFO]/visienhance 等假阳性）
ERROR_PATTERNS = [r'\bnan\b', r'\binf\b', 'cuda out of memory', r'\boom\b', 'runtimeerror',
                  'killed', 'error:', 'traceback', 'exception']


def ssh_run(c, cmd, timeout=15):
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

    # 读 state.json（训练脚本写入）
    state_raw = ssh_run(c, f"cat {STATE_FILE} 2>/dev/null || echo '{{}}'")
    try:
        import json as _json
        state = _json.loads(state_raw)
    except:
        state = {}

    job_id = state.get('job_id') or JOB_ID
    if not job_id:
        # 从 squeue 找最新 job
        sq_all = ssh_run(c, f"squeue -u {USER} --format='%.10i %.8T' --noheader")
        for line in sq_all.strip().split('\n'):
            parts = line.split()
            if parts:
                job_id = parts[0].strip()
                break

    log_err = f"{LOG_DIR}/{job_id}.err" if job_id else None
    log_out = f"{LOG_DIR}/{job_id}.out" if job_id else None
    gpu_log = f"{LOG_DIR}/{job_id}_gpu.log" if job_id else None

    status   = ssh_run(c, f"squeue -u {USER} --format='%.10i %.12j %.8T %.10M %R'")
    resource = ssh_run(c, f"scontrol show job {job_id} 2>/dev/null | grep -E 'RunTime|TresPerNode|NodeList'") if job_id else ""

    # GPU 利用率
    gpu_raw = ""
    if job_id:
        gpu_raw = ssh_run(c,
            f"srun --overlap --jobid={job_id} nvidia-smi dmon -s um -c 10 2>&1",
            timeout=25)
        # fallback: 读 GPU log 文件
        if not gpu_raw or 'error' in gpu_raw.lower():
            gpu_raw = ssh_run(c, f"tail -5 {gpu_log} 2>/dev/null") or "无数据"

    # 训练日志（进度行在 .out，不在 .err）
    log_tail = ""
    if log_out:
        log_tail = ssh_run(c, f"grep -E 'Epoch|val_PSNR|PSNR|Train:|Test:' {log_out} 2>/dev/null | tail -12")

    # 错误检测
    errors = []
    if log_err:
        err_check = ssh_run(c, f"grep -iE '{'|'.join(ERROR_PATTERNS)}' {log_err} 2>/dev/null | tail -5")
        if err_check:
            errors.append(err_check)
    if log_out:
        out_check = ssh_run(c, f"grep -iE '{'|'.join(ERROR_PATTERNS)}' {log_out} 2>/dev/null | tail -3")
        if out_check:
            errors.append(out_check)

    # job 状态检查（FAILED/CANCELLED/TIMEOUT）
    job_state = ssh_run(c, f"scontrol show job {job_id} 2>/dev/null | grep 'JobState=' | awk -F= '{{print $2}}' | awk '{{print $1}}'") if job_id else ""

    c.close()

    # 解析 epoch
    current_epoch = state.get('epoch', 0)
    if not current_epoch:
        for line in reversed(log_tail.split('\n')):
            if 'Train:' in line:
                try:
                    current_epoch = int(line.split('Train:')[1].strip().split()[0])
                except:
                    pass
                break

    return status, resource, gpu_raw, log_tail, current_epoch, state, errors, job_state, job_id


def format_gpu(gpu_raw):
    """解析 nvidia-smi dmon -s um 输出
    列: Idx  sm%  mem_bw%  enc%  dec%  jpg%  ofa%  fb_MB  bar1_MB  ccpm_MB
    """
    sm_vals, membw_vals, fb_mb = [], [], None
    for ln in gpu_raw.split('\n'):
        ln = ln.strip()
        if ln.startswith('#') or not ln:
            continue
        parts = ln.split()
        if len(parts) >= 8:
            try:
                sm_vals.append(int(parts[1]))
                membw_vals.append(int(parts[2]))
                fb_mb = int(parts[7])   # fb_MB 很稳定，不波动
            except ValueError:
                pass
    if sm_vals:
        peak_sm  = max(sm_vals)
        avg_sm   = sum(sm_vals) // len(sm_vals)
        peak_bw  = max(membw_vals)
        mem_note = f"  显存已用: {fb_mb} MB / 24564 MB ({fb_mb*100//24564}%)" if fb_mb else ""
        busy_note = "  ⚠ 本次采样均为0%，可能在数据加载/验证阶段" if peak_sm == 0 else ""
        return (
            f"  SM 利用率: 峰值 {peak_sm}%  均值 {avg_sm}%  ({len(sm_vals)} 次采样)\n"
            f"  显存带宽: 峰值 {peak_bw}%\n"
            f"{mem_note}{busy_note}"
        )
    return f"  {gpu_raw[:300]}"


class MonitorApp:
    def __init__(self, root):
        self.root = root
        root.title(f"HPC 训练监控 — Job {JOB_ID}")
        root.geometry("820x560")
        root.configure(bg='#1e1e1e')

        self.status_var = tk.StringVar(value="连接中...")
        tk.Label(root, textvariable=self.status_var,
                 bg='#1e1e1e', fg='#00ff88', font=('Consolas', 10)).pack(pady=4)

        self.text = scrolledtext.ScrolledText(
            root, bg='#1e1e1e', fg='#d4d4d4',
            font=('Consolas', 10), wrap=tk.WORD,
            insertbackground='white'
        )
        self.text.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self.next_var = tk.StringVar(value="")
        tk.Label(root, textvariable=self.next_var,
                 bg='#1e1e1e', fg='#888888', font=('Consolas', 9)).pack(pady=2)

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

        root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self._running = False
        self.root.destroy()

    def _write(self, content):
        self.text.configure(state='normal')
        self.text.delete('1.0', tk.END)
        self.text.insert(tk.END, content)
        self.text.configure(state='disabled')
        self.text.see(tk.END)

    def _loop(self):
        while self._running:
            try:
                self.status_var.set("⟳ 拉取中...")
                status, resource, gpu_raw, log_tail, epoch, state, errors, job_state, job_id = fetch_status()

                interval = INTERVAL_FAST if epoch < 2 else INTERVAL_SLOW
                now = time.strftime('%H:%M:%S')

                # 错误/异常状态着色
                is_error = bool(errors) or job_state in ('FAILED', 'CANCELLED', 'TIMEOUT')

                # state.json 信息
                state_info = ""
                if state:
                    state_info = (
                        f"  status={state.get('status','?')}  "
                        f"epoch={state.get('epoch','?')}  "
                        f"val_psnr={state.get('val_psnr','?')}  "
                        f"train_loss={state.get('train_loss','?')}"
                    )

                warn = ""
                if is_error:
                    warn = f"\n⚠️  异常检测:\n" + "\n".join(errors) + f"\n  Job State: {job_state}\n"

                out = (
                    f"══ {now}  Job:{job_id}  Epoch:{epoch}  ══\n"
                    f"{state_info}\n"
                    f"{warn}\n"
                    f"【任务状态】\n{status}\n\n"
                    f"【资源分配】\n{resource}\n\n"
                    f"【GPU 利用率】\n{format_gpu(gpu_raw)}\n\n"
                    f"【训练进度（最近12条）】\n{log_tail}\n"
                )
                self._write(out)

                # 标题栏变红提示错误
                if is_error:
                    self.root.configure(bg='#3a0000')
                    self.status_var.set(f"⚠ 异常! {now} | Epoch {epoch} | Job:{job_state}")
                else:
                    self.root.configure(bg='#1e1e1e')
                    mode = "快速(60s)" if epoch < 2 else "慢速(5min)"
                    self.status_var.set(f"✓ {now}  |  Epoch {epoch}  |  {mode}  |  Job:{job_id}")

                for remaining in range(interval, 0, -1):
                    if not self._running:
                        break
                    self.next_var.set(f"下次刷新: {remaining}s 后")
                    time.sleep(1)

            except Exception as e:
                self.status_var.set(f"连接失败: {e}，5s 后重试")
                time.sleep(5)

        self.next_var.set("已停止")


if __name__ == '__main__':
    root = tk.Tk()
    app = MonitorApp(root)
    root.mainloop()
