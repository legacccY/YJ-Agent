"""实时训练进度可视化窗口，读取日志文件每 3 秒刷新一次。"""
import re
import sys
import time
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.animation as animation

LOG_FILE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("D:/YJ-Agent/log/train_train_visiscore_20260506_160040.log")

train_losses, val_losses, epochs = [], [], []

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
fig.suptitle("VisiScore-Net 训练进度", fontsize=14)

def parse_log():
    if not LOG_FILE.exists():
        return
    text = LOG_FILE.read_text(encoding="utf-8", errors="ignore")
    train_losses.clear(); val_losses.clear(); epochs.clear()
    for m in re.finditer(r"Epoch \[(\d+)/\d+\] loss=([\d.]+)", text):
        epochs.append(int(m.group(1)))
        train_losses.append(float(m.group(2)))
    for m in re.finditer(r"Epoch \[\d+/\d+\] val_loss=([\d.]+)", text):
        val_losses.append(float(m.group(1)))

def update(_frame):
    parse_log()
    ax1.cla(); ax2.cla()

    # 进度条
    total_epochs = 20
    done = len(epochs)
    ax1.barh(["进度"], [done], color="#4CAF50", height=0.4)
    ax1.barh(["进度"], [total_epochs - done], left=[done], color="#e0e0e0", height=0.4)
    ax1.set_xlim(0, total_epochs)
    ax1.set_xlabel("Epoch")
    ax1.set_title(f"训练进度  {done}/{total_epochs} epochs")
    for i, (e, l) in enumerate(zip(epochs, train_losses)):
        if i == len(epochs) - 1:
            ax1.text(done - 0.1, 0, f" loss={l:.4f}", va="center", ha="right", fontsize=9, color="white")

    # loss 曲线
    if train_losses:
        ax2.plot(epochs, train_losses, "b-o", markersize=4, label="train loss")
    if val_losses:
        n = min(len(epochs), len(val_losses))
        ax2.plot(epochs[:n], val_losses[:n], "r-o", markersize=4, label="val loss")
    ax2.set_xlabel("Epoch"); ax2.set_ylabel("Loss")
    ax2.set_title("Loss 曲线")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    # 状态文字
    status = "训练中..." if not train_losses else f"最新 train_loss={train_losses[-1]:.4f}"
    if val_losses:
        status += f"  val_loss={val_losses[-1]:.4f}"
    fig.canvas.manager.set_window_title(f"VisiScore-Net — {status}")
    plt.tight_layout()

ani = animation.FuncAnimation(fig, update, interval=3000, cache_frame_data=False)
plt.tight_layout()
plt.show()
