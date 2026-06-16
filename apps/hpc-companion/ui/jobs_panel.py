"""任务监控面板。

上：squeue 任务表（自动刷新、状态着色、取消）。
下：选中 job 的详情 / 日志 tail / GPU 利用率曲线 / 训练心跳曲线。
日志路径自动从 scontrol 的 StdOut/StdErr 取，无需手填。
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)  # noqa

import pyqtgraph as pg

from core import slurm
from core.worker import run_async
from .app_context import AppContext
from . import theme

pg.setConfigOption("background", theme.palette()["BG_ALT"])
pg.setConfigOption("foreground", theme.palette()["TEXT"])

FAIL_STATES = {"FAILED", "TIMEOUT", "OUT_OF_MEMORY", "CANCELLED", "NODE_FAIL", "BOOT_FAIL"}


class JobsPanel(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._jobs: list[slurm.Job] = []
        self._n_active: int = 0
        self._sel_job: str | None = None
        # 心跳曲线缓存：epoch -> metric
        self._hb_x: list[float] = []
        self._hb_y: list[float] = []
        self._gpu_t: list[float] = []
        self._gpu_sm: list[float] = []
        self._logpath_cache: dict = {}   # (jid,ext) -> 已定位日志路径，find 只跑一次
        self._tick = 0

        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.addLayout(self._build_controls())

        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self._build_table())
        split.addWidget(self._build_detail())
        split.setSizes([260, 420])
        root.addWidget(split, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)

        self.ctx.connected.connect(self._on_connected)
        self.ctx.disconnected.connect(self._on_disconnected)
        self._set_enabled(False)
        self.apply_theme()

    # ---- 顶部控制 ----
    def _build_controls(self) -> QHBoxLayout:
        lay = QHBoxLayout()
        self.btn_refresh = QPushButton("立即刷新")
        self.btn_refresh.clicked.connect(self.refresh)
        self.chk_auto = QCheckBox("自动刷新")
        self.chk_auto.setChecked(True)
        self.chk_auto.toggled.connect(self._toggle_auto)
        self.cmb_interval = QComboBox()
        for s in ("5 秒", "10 秒", "15 秒", "30 秒", "60 秒", "5 分钟"):
            self.cmb_interval.addItem(s)
        self.cmb_interval.setCurrentText("10 秒")
        self.cmb_interval.currentTextChanged.connect(self._toggle_auto)
        self.chk_history = QCheckBox("显示已结束")
        self.chk_history.setChecked(True)
        self.chk_history.toggled.connect(self.refresh)
        self.cmb_range = QComboBox()
        for s in ("今日", "近 3 天", "近 7 天", "近 30 天"):
            self.cmb_range.addItem(s)
        self.cmb_range.currentTextChanged.connect(self.refresh)
        self.lbl_tick = QLabel("")
        self.lbl_tick.setObjectName("hint")
        lay.addWidget(self.btn_refresh)
        lay.addWidget(self.chk_auto)
        lay.addWidget(QLabel("间隔"))
        lay.addWidget(self.cmb_interval)
        lay.addWidget(self.chk_history)
        lay.addWidget(self.cmb_range)
        lay.addWidget(self.lbl_tick)
        lay.addStretch(1)
        self.btn_cancel = QPushButton("取消选中任务")
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.clicked.connect(self._cancel_job)
        lay.addWidget(self.btn_cancel)
        return lay

    def _build_table(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Job ID", "名称", "状态", "运行时长", "节点", "原因/节点列表"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        v.addWidget(self.table)
        return w

    def _build_detail(self) -> QWidget:
        self.tabs = QTabWidget()

        # 日志
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        log_w = QWidget()
        lv = QVBoxLayout(log_w)
        bar = QHBoxLayout()
        self.cmb_logsrc = QComboBox()
        self.cmb_logsrc.addItems(["标准输出 (.out)", "错误输出 (.err)"])
        self.cmb_logsrc.currentTextChanged.connect(self._refresh_detail)
        bar.addWidget(QLabel("日志源"))
        bar.addWidget(self.cmb_logsrc)
        bar.addStretch(1)
        self.lbl_logpath = QLabel("")
        self.lbl_logpath.setObjectName("hint")
        bar.addWidget(self.lbl_logpath)
        lv.addLayout(bar)
        lv.addWidget(self.log_view)
        self.tabs.addTab(log_w, "日志")

        # GPU 曲线
        gpu_w = QWidget()
        gv = QVBoxLayout(gpu_w)
        self.lbl_gpu = QLabel("GPU：选中运行中的任务后显示")
        self.lbl_gpu.setObjectName("hint")
        gv.addWidget(self.lbl_gpu)
        self.gpu_plot = pg.PlotWidget()
        self.gpu_plot.setLabel("left", "SM 利用率 %")
        self.gpu_plot.setLabel("bottom", "采样次")
        self.gpu_plot.setYRange(0, 100)
        self.gpu_plot.showGrid(x=True, y=True, alpha=0.2)
        # Y 锁死 0-100，禁缩放/拖动，X 自动跟随
        vb = self.gpu_plot.getViewBox()
        vb.setMouseEnabled(x=False, y=False)
        vb.setYRange(0, 100, padding=0)
        vb.setLimits(yMin=0, yMax=100)
        self.gpu_plot.setMenuEnabled(False)
        self.gpu_curve = self.gpu_plot.plot(pen=pg.mkPen(theme.palette()["ACCENT"], width=2))
        gv.addWidget(self.gpu_plot)
        self.tabs.addTab(gpu_w, "GPU 利用率")

        # 心跳曲线
        hb_w = QWidget()
        hv = QVBoxLayout(hb_w)
        cfg = QHBoxLayout()
        cfg.addWidget(QLabel("心跳文件"))
        self.in_state = QLineEdit()
        self.in_state.setPlaceholderText(
            "experiment_state.json 远端路径（空=从 WorkDir/logs 自动找）")
        cfg.addWidget(self.in_state, 1)
        cfg.addWidget(QLabel("指标键"))
        self.in_metric = QLineEdit("val_psnr")
        self.in_metric.setFixedWidth(120)
        cfg.addWidget(self.in_metric)
        hv.addLayout(cfg)
        self.lbl_hb = QLabel("训练脚本写入的实时状态（status/epoch/loss…）")
        self.lbl_hb.setObjectName("hint")
        hv.addWidget(self.lbl_hb)
        self.hb_plot = pg.PlotWidget()
        self.hb_plot.setLabel("bottom", "epoch")
        self.hb_plot.showGrid(x=True, y=True, alpha=0.2)
        _w = theme.palette()["WARN"]
        self.hb_curve = self.hb_plot.plot(
            pen=pg.mkPen(_w, width=2), symbol="o", symbolSize=5, symbolBrush=_w)
        hv.addWidget(self.hb_plot)
        hrow = QHBoxLayout()
        btn_hb_reset = QPushButton("复位视图")
        btn_hb_reset.clicked.connect(lambda: self.hb_plot.getPlotItem().enableAutoRange())
        btn_hb_clear = QPushButton("清空曲线")
        btn_hb_clear.clicked.connect(self._clear_hb)
        hrow.addStretch(1); hrow.addWidget(btn_hb_clear); hrow.addWidget(btn_hb_reset)
        hv.addLayout(hrow)
        self.tabs.addTab(hb_w, "训练心跳")

        # 详情
        self.detail_view = QPlainTextEdit()
        self.detail_view.setReadOnly(True)
        self.tabs.addTab(self.detail_view, "scontrol 详情")

        # 容器：顶部错误横幅（失败任务变红显错）+ 标签页
        cont = QWidget()
        cl = QVBoxLayout(cont)
        cl.setContentsMargins(0, 0, 0, 0)
        self.err_banner = QLabel("")
        self.err_banner.setWordWrap(True)
        self.err_banner.setVisible(False)
        self.err_banner.setStyleSheet(
            f"background:{theme.palette()['DANGER']}; color:#fff; "
            f"padding:8px 12px; border-radius:6px; font-weight:600;")
        cl.addWidget(self.err_banner)
        cl.addWidget(self.tabs, 1)
        return cont

    # ---- 连接状态 ----
    def _set_enabled(self, on: bool) -> None:
        for w in (self.btn_refresh, self.chk_auto, self.cmb_interval,
                  self.btn_cancel, self.table):
            w.setEnabled(on)

    def _on_connected(self, _profile) -> None:
        self._set_enabled(True)
        self.refresh()
        if self.chk_auto.isChecked():
            self._toggle_auto()

    def _on_disconnected(self) -> None:
        self.timer.stop()
        self._set_enabled(False)
        self.table.setRowCount(0)

    def _interval_ms(self) -> int:
        return {"5 秒": 5000, "10 秒": 10000, "15 秒": 15000, "30 秒": 30000,
                "60 秒": 60000, "5 分钟": 300000}[self.cmb_interval.currentText()]

    def _toggle_auto(self, *_) -> None:
        if self.chk_auto.isChecked() and self.ctx.is_connected:
            self.timer.start(self._interval_ms())
        else:
            self.timer.stop()

    # ---- 刷新 squeue ----
    def refresh(self) -> None:
        if not self.ctx.is_connected or self.ctx.profile is None:
            return
        self._tick += 1
        user = self.ctx.profile.username
        want_hist = self.chk_history.isChecked()
        days = {"今日": 0, "近 3 天": 3, "近 7 天": 7, "近 30 天": 30}[self.cmb_range.currentText()]

        def do():
            sq = slurm.parse_squeue(self.ctx.ssh.exec(slurm.queue_cmd(user), timeout=20).out)
            hist = []
            if want_hist:
                hist = slurm.parse_sacct(
                    self.ctx.ssh.exec(slurm.sacct_cmd(user, days), timeout=30).out)
            return sq, hist

        run_async(self, do, on_ok=self._fill_table, on_err=self._err)
        # 选中的任务，刷新表的同时刷它的日志/GPU/心跳，实现"实时看"
        if self._sel_job:
            self._refresh_detail()

    def _fill_table(self, data) -> None:
        sq, hist = data
        # 融合：sacct 历史打底，squeue 活跃任务覆盖（活跃状态更准）
        active_ids = {j.job_id for j in sq}
        ended = [j for j in hist if j.job_id not in active_ids]
        ended.sort(key=lambda j: j.job_id, reverse=True)
        self._jobs = sq + ended
        self._n_active = len(sq)
        prev = self._sel_job
        sc = theme.state_colors()
        self.table.setRowCount(len(self._jobs))
        for r, j in enumerate(self._jobs):
            vals = [j.job_id, j.name, j.state, j.time, j.nodes, j.reason]
            for c, val in enumerate(vals):
                item = QTableWidgetItem(val)
                if c == 2:
                    color = sc.get(j.state)
                    if color:
                        item.setForeground(QColor(color))
                self.table.setItem(r, c, item)
        n_ended = len(self._jobs) - self._n_active
        self.lbl_tick.setText(
            f"刷新#{self._tick} · 活跃 {self._n_active} · 已结束 {n_ended}"
            + ("（无任务）" if not self._jobs else ""))
        # 维持选中
        if prev:
            for r, j in enumerate(self._jobs):
                if j.job_id == prev:
                    self.table.selectRow(r)
                    break

    # ---- 选中行 ----
    def _on_row_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        r = rows[0].row()
        if 0 <= r < len(self._jobs):
            new = self._jobs[r].job_id
            if new != self._sel_job:
                self._sel_job = new
                self._hb_x.clear(); self._hb_y.clear()
                self._gpu_t.clear(); self._gpu_sm.clear()
            self._refresh_detail()

    def _cur_state(self) -> str:
        for j in self._jobs:
            if j.job_id == self._sel_job:
                return j.state
        return ""

    def _refresh_detail(self, *_) -> None:
        if not self._sel_job or not self.ctx.is_connected:
            return
        jid = self._sel_job
        metric = self.in_metric.text().strip() or "val_psnr"
        state_override = self.in_state.text().strip()
        cur_state = self._cur_state()
        want_gpu = cur_state == "RUNNING"
        want_err = self.cmb_logsrc.currentIndex() == 1
        ext = "err" if want_err else "out"

        def do():
            ssh = self.ctx.ssh
            d = slurm.parse_scontrol(ssh.exec(slurm.detail_cmd(jid)).out)
            workdir = d.get("WorkDir", "")
            if workdir in ("(null)", ""):
                workdir = ""
            if not workdir:
                wd = ssh.exec(f"sacct -j {jid} -X -n --format=WorkDir%500 2>/dev/null").out.strip()
                workdir = wd.splitlines()[0].strip() if wd else ""

            def locate(want_ext: str) -> str:
                """先用 scontrol 的 StdOut/StdErr；清理后用 find 按 job id 搜（结果缓存）。"""
                lp = d.get("StdErr" if want_ext == "err" else "StdOut", "")
                if lp in ("(null)", ""):
                    lp = ""
                if lp:
                    return lp
                ck = (jid, want_ext)
                if ck in self._logpath_cache:      # find 每个 job 只跑一次
                    return self._logpath_cache[ck]
                roots = []
                if workdir:
                    roots.append(workdir.rstrip("/"))
                prof = self.ctx.profile
                if prof and prof.default_remote_dir:
                    roots.append(prof.default_remote_dir.rstrip("/"))
                result = ""
                seen = set()
                for root in roots:
                    if not root or root in seen:
                        continue
                    seen.add(root)
                    found = ssh.exec(
                        f"find '{root}' -maxdepth 4 -name '*{jid}*' -type f "
                        f"2>/dev/null | head -20").out.strip().splitlines()
                    if found:
                        pref = [f for f in found if f.endswith(f".{want_ext}")]
                        result = (pref or found)[0].strip()
                        break
                self._logpath_cache[ck] = result
                return result

            log_path = locate(ext)
            log_tail = ssh.exec(f"tail -n 300 '{log_path}' 2>/dev/null").out if log_path else ""

            # 失败任务 → 抓 .err 末尾 + 退出码，做红色错误摘要
            err_summary = ""
            if cur_state in FAIL_STATES:
                err_path = log_path if ext == "err" else locate("err")
                err_tail = ssh.exec(f"tail -n 15 '{err_path}' 2>/dev/null").out if err_path else ""
                exitcode = d.get("ExitCode", "")
                if not exitcode:
                    ec = ssh.exec(f"sacct -j {jid} -X -n --format=ExitCode 2>/dev/null").out.strip().splitlines()
                    exitcode = ec[0].strip() if ec else ""
                err_summary = self._build_err_summary(
                    cur_state, exitcode, d.get("Reason", ""), err_tail)

            # 心跳（快，文件读取）
            state_path = state_override
            if not state_path and workdir:
                state_path = workdir.rstrip("/") + "/logs/experiment_state.json"
            hb = slurm.read_experiment_state(ssh, state_path) if state_path else None
            detail_txt = self._fmt_detail(d) if d else ""
            return dict(detail=detail_txt, log=log_tail, log_path=log_path,
                        hb=hb, metric=metric, state=cur_state, err=err_summary)

        run_async(self, do, on_ok=self._apply_detail, on_err=self._err)
        # GPU 采样慢（srun dmon ~数秒），单独异步，不拖累日志/详情秒出
        if want_gpu:
            self._refresh_gpu(jid)

    def _refresh_gpu(self, jid: str) -> None:
        def do():
            graw = self.ctx.ssh.exec(slurm.gpu_dmon_cmd(jid, 3), timeout=20).out
            return slurm.parse_gpu_dmon(graw)
        run_async(self, do, on_ok=lambda g: self._apply_gpu(g, jid),
                  on_err=lambda _m: None)

    def _apply_gpu(self, gpu, jid: str) -> None:
        if jid != self._sel_job:   # 已切走，丢弃过期结果
            return
        if gpu and gpu.samples:
            self._gpu_t.append(len(self._gpu_t) + 1)
            self._gpu_sm.append(gpu.sm_peak)
            self.gpu_curve.setData(self._gpu_t, self._gpu_sm)
            self.lbl_gpu.setText(
                f"SM 峰值 {gpu.sm_peak}% · 均值 {gpu.sm_avg}% · "
                f"显存带宽峰值 {gpu.mem_bw_peak}% · 显存 {gpu.fb_used_mb} MB")

    @staticmethod
    def _build_err_summary(state: str, exitcode: str, reason: str, err_tail: str) -> str:
        bits = [f"✗ {state}"]
        if exitcode and exitcode not in ("0:0",):
            code = exitcode.split(":")[0]
            hint = " (命令未找到)" if code == "127" else (
                " (OOM/被杀)" if code in ("137", "139") else "")
            bits.append(f"退出码 {exitcode}{hint}")
        if reason and reason not in ("None", ""):
            bits.append(f"原因 {reason}")
        head = " · ".join(bits)
        last = ""
        if err_tail.strip():
            lines = [l for l in err_tail.strip().splitlines() if l.strip()]
            last = "\n最后错误输出：\n" + "\n".join(lines[-4:])
        return head + last

    @staticmethod
    def _fmt_detail(d: dict) -> str:
        keys = ["JobId", "JobName", "JobState", "Reason", "RunTime", "TimeLimit",
                "Partition", "QOS", "NodeList", "NumNodes", "NumCPUs",
                "TresPerNode", "StartTime", "WorkDir", "StdOut", "StdErr"]
        lines = [f"{k:14}= {d[k]}" for k in keys if k in d]
        return "\n".join(lines) if lines else "（无详情，任务可能已结束）"

    def _clear_gpu(self) -> None:
        self._gpu_t.clear(); self._gpu_sm.clear()
        self.gpu_curve.setData([], [])

    def _clear_hb(self) -> None:
        self._hb_x.clear(); self._hb_y.clear()
        self.hb_curve.setData([], [])

    def _apply_detail(self, data: dict) -> None:
        # 错误横幅
        err = data.get("err", "")
        if err:
            self.err_banner.setText(err)
            self.err_banner.setVisible(True)
        else:
            self.err_banner.setVisible(False)
        self.detail_view.setPlainText(data["detail"] or "（任务已结束，调度器不再保留详情；状态见任务表）")
        if data["log"]:
            self.log_view.setPlainText(data["log"])
        else:
            st = data.get("state", "")
            if st in ("PENDING",):
                msg = "（任务排队中，日志尚未生成）"
            elif st in ("COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY"):
                msg = ("（任务已结束，未定位到日志文件——可能日志写在非标准路径，"
                       "或已被清理。可在「文件传输」页到工作目录手动查看）")
            else:
                msg = "（暂无日志）"
            self.log_view.setPlainText(msg)
        self.lbl_logpath.setText(data["log_path"] or "")
        if data.get("state") != "RUNNING":
            self.lbl_gpu.setText("GPU：仅运行中的 GPU 任务有利用率数据")
        # 心跳
        hb = data["hb"]
        if hb:
            ep = hb.get("epoch")
            mval = hb.get(data["metric"])
            status = hb.get("status", "?")
            txt = f"status={status} · epoch={ep}"
            for k in ("train_loss", "val_loss", data["metric"]):
                if k in hb:
                    txt += f" · {k}={hb[k]}"
            self.lbl_hb.setText(txt)
            if isinstance(ep, (int, float)) and isinstance(mval, (int, float)):
                if not self._hb_x or ep != self._hb_x[-1]:
                    self._hb_x.append(ep)
                    self._hb_y.append(mval)
                    self.hb_plot.setLabel("left", data["metric"])
                    self.hb_curve.setData(self._hb_x, self._hb_y)
        else:
            self.lbl_hb.setText("未读到 experiment_state.json（路径不对或训练脚本未写）")

    # ---- 取消 ----
    def _cancel_job(self) -> None:
        if not self._sel_job:
            return
        if QMessageBox.question(self, "取消任务", f"scancel {self._sel_job}？")\
                != QMessageBox.StandardButton.Yes:
            return
        jid = self._sel_job
        run_async(self, lambda: self.ctx.ssh.exec(slurm.cancel_cmd(jid)),
                  on_ok=lambda _: (self.ctx.status_message.emit(f"已取消 {jid}"),
                                   self.refresh()),
                  on_err=self._err)

    def _err(self, msg: str) -> None:
        self.ctx.status_message.emit(f"错误：{msg}")

    # ---- 主题 ----
    def apply_theme(self) -> None:
        p = theme.palette()
        for plot in (self.gpu_plot, self.hb_plot):
            plot.setBackground(p["BG_ALT"])
            for axn in ("left", "bottom"):
                ax = plot.getAxis(axn)
                ax.setTextPen(p["TEXT"])
                ax.setPen(p["TEXT_DIM"])
        self.gpu_curve.setPen(pg.mkPen(p["ACCENT"], width=2))
        self.hb_curve.setPen(pg.mkPen(p["WARN"], width=2))
        self.hb_curve.setSymbolBrush(p["WARN"])
        # 表格状态列重新着色
        sc = theme.state_colors()
        for r, j in enumerate(self._jobs):
            it = self.table.item(r, 2)
            if it:
                color = sc.get(j.state, p["TEXT"])
                it.setForeground(QColor(color))
