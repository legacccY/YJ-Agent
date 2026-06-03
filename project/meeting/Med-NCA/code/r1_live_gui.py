"""R1 本地训练实时监控弹窗 (tkinter).
读 results/r1_train.log (UTF-16/含 null), 解析最新 Epoch + loss, 估速率/ETA.

启动:
    python code\r1_live_gui.py
或后台弹窗:
    Start-Process python -ArgumentList '"D:\YJ-Agent\project\meeting\Med-NCA\code\r1_live_gui.py"'
"""
import os
import re
import time
import tkinter as tk

LOG = r"D:\YJ-Agent\project\meeting\Med-NCA\results\r1_train.log"
TARGET_EPOCH = 1000          # R1 论文目标轮数
REFRESH_MS = 5000            # 5s 刷新
STALE_SEC = 600              # log 超 10min 不更新 = 疑似卡死/结束

EPOCH_RE = re.compile(r"Epoch:\s*(\d+)")
LOSS_RE = re.compile(r"(\d+)\s+loss\s*=\s*([0-9.]+)")

# 记录 (epoch, wallclock) 用来估速率
_seen = {}   # epoch -> 首次观测到的时间戳


def read_log_tail(path, nbytes=20000):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - nbytes))
            raw = f.read()
        return raw.replace(b"\x00", b"").decode("utf-8", "replace")
    except FileNotFoundError:
        return ""


def parse(text):
    epochs = [int(m) for m in EPOCH_RE.findall(text)]
    cur_epoch = max(epochs) if epochs else None
    losses = LOSS_RE.findall(text)
    last_loss = float(losses[-1][1]) if losses else None
    return cur_epoch, last_loss


class App:
    def __init__(self, root):
        self.root = root
        root.title("R1 Hippocampus 监控")
        root.geometry("440x300")
        self.lbl = tk.Label(root, font=("Consolas", 12), justify="left",
                            anchor="nw", padx=14, pady=14)
        self.lbl.pack(fill="both", expand=True)
        self.tick()

    def tick(self):
        text = read_log_tail(LOG)
        epoch, loss = parse(text)
        now = time.time()
        try:
            mtime = os.path.getmtime(LOG)
            age = now - mtime
        except OSError:
            mtime, age = None, 1e9

        # 速率估计: 记录每个新 epoch 首见时间
        rate_str = "—"
        eta_str = "—"
        if epoch is not None:
            if epoch not in _seen:
                _seen[epoch] = now
            if len(_seen) >= 2:
                eps = sorted(_seen)
                span_e = eps[-1] - eps[0]
                span_t = _seen[eps[-1]] - _seen[eps[0]]
                if span_e > 0 and span_t > 0:
                    sec_per_ep = span_t / span_e
                    rate_str = f"{sec_per_ep/60:.1f} min/epoch"
                    remain = (TARGET_EPOCH - epoch) * sec_per_ep
                    eta_str = f"{remain/3600:.1f} h"

        # 状态判定
        if age > STALE_SEC:
            status, bg = f"⚠ log {int(age)}s 未更新 (卡死/已结束?)", "#fff2cc"
        else:
            status, bg = "● 训练中", "#e8f5e9"
        if "FAIL" in text or "PASS" in text or "train done" in text:
            status, bg = "✓ 训练完成 (见 results/*.json)", "#e3f2fd"

        ep_show = f"{epoch}/{TARGET_EPOCH}" if epoch is not None else "—"
        loss_show = f"{loss:.5f}" if loss is not None else "—"
        mt_show = time.strftime("%H:%M:%S", time.localtime(mtime)) if mtime else "—"

        self.lbl.config(bg=bg, text=(
            f"状态:  {status}\n\n"
            f"Epoch: {ep_show}\n"
            f"Loss:  {loss_show}\n"
            f"速率:  {rate_str}\n"
            f"ETA:   {eta_str}\n\n"
            f"log 最后更新: {mt_show}  ({int(age)}s 前)\n"
            f"刷新: {time.strftime('%H:%M:%S')}"
        ))
        self.root.configure(bg=bg)
        self.root.after(REFRESH_MS, self.tick)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
