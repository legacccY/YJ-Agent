"""离屏跑真 GUI → 自动连接 → 选已结束任务 → 等日志 find 定位 → 截图。"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PyQt6.QtWidgets import QApplication
from ui import theme
from core import config
from ui.main_window import MainWindow

def pump(ms):
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)

app = QApplication([])
theme.CURRENT = config.load_settings().get("theme", "dark")
app.setStyleSheet(theme.stylesheet())
w = MainWindow(); w.resize(1180, 760); w.show()
pump(600)
for _ in range(80):
    pump(200)
    if w.ctx.is_connected:
        break
print("connected:", w.ctx.is_connected)

jp = w.jobs_panel
w.tabs.setCurrentWidget(jp)
jp.chk_history.setChecked(True)
jp.cmb_range.setCurrentText("近 7 天")
jp.refresh()
pump(5000)
print("rows:", jp.table.rowCount())

# 选一个已结束任务（优先 ncaj，否则最后一行）
sel = -1
for r, j in enumerate(jp._jobs):
    if j.job_id == "1450899":
        sel = r; break
if sel < 0 and jp._jobs:
    sel = len(jp._jobs) - 1
print("select row:", sel, "job:", jp._jobs[sel].job_id if sel >= 0 else None)
jp.table.selectRow(sel)
jp.tabs.setCurrentIndex(0)   # 日志子页
pump(6000)                   # 等远端 find 定位 + tail

print("log_path label:", jp.lbl_logpath.text())
print("log head:", jp.log_view.toPlainText()[:200].replace("\n", " | "))
out = Path(__file__).resolve().parent / "shot_jobs.png"
w.grab().save(str(out))
print("SAVED", out)
