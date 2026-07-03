# -*- coding: utf-8 -*-
"""
alarm_derive.py — 从 MIMIC-III 波形/numerics 派生阈值告警事件（02/03 共用）
==========================================================================
服务 KS-3 命门 Q1（共触发）/ Q2（复合 FAR 稳健）。
按 Chromik et al. 思路：读 numerics（1 Hz 体征），对每个体征按阈值族的上下限 + 最短持续
时间派生"告警活跃"时间线（去瞬时 artifact）。02 数共触发 + 相关，03 加弱代理算复合 FAR。

⚠️ 阈值/持续时间/窗宽全来自 alarm_thresholds.py，其中体征阈值为占位 TODO（见该文件红线）。
纯 numpy，无 scipy.stats（相关系数手写，避 OMP 冲突 & 保持规范）。
Windows 规范：pathlib、utf-8、无硬编码盘符。**本模块不执行，只被 import。**
"""
import numpy as np

from alarm_thresholds import (
    VITAL_THRESHOLD_FAMILIES,
    canonicalize_signal,
    COTRIGGER_WINDOW_S,
)


def load_numerics(record, pn_dir=None, local_dir=None):
    """
    读一条 MIMIC-III numerics record，返回 dict: 规范信号名 -> (values 1D float array, fs)。
    优先本地（local_dir/record），否则在线（wfdb pn_dir）。缺 wfdb 抛 ImportError。
    numerics record 通常 1 Hz，含 HR/SpO2/ABP/RESP 等派生体征。
    """
    try:
        import wfdb
    except ImportError as e:
        raise ImportError("需要 wfdb 读波形/numerics：pip install wfdb") from e

    if local_dir is not None:
        rec = wfdb.rdrecord(str(local_dir).rstrip("/") + "/" + record)
    else:
        # wfdb 在线读：record 含子目录(如 p00/p000020/xxxn)时须把目录并进 pn_dir，
        # record 只留 basename，否则 URL 会丢子目录前缀报 404。
        if "/" in record and pn_dir:
            subdir, base = record.rsplit("/", 1)
            eff_pn_dir = pn_dir.rstrip("/") + "/" + subdir
            rec = wfdb.rdrecord(base, pn_dir=eff_pn_dir)
        else:
            rec = wfdb.rdrecord(record, pn_dir=pn_dir)

    fs = float(rec.fs) if rec.fs else 1.0
    out = {}
    sig = np.asarray(rec.p_signal, dtype=float)  # shape (n_samp, n_sig)
    for i, name in enumerate(rec.sig_name):
        canon = canonicalize_signal(name)
        if canon is None:
            continue
        col = sig[:, i]
        # 同一规范体征可能多列（如 ABP 多导），保留第一条非全 NaN 的
        if canon in out:
            continue
        if np.all(np.isnan(col)):
            continue
        out[canon] = (col, fs)
    return out


def _sustained_mask(violation, fs, sustain_s):
    """
    输入逐样本布尔越界 violation，返回"持续 >= sustain_s 才算告警活跃"的布尔 mask。
    做法：找连续 True 段，段时长 >= sustain_s 的整段保留，否则清零（去瞬时 artifact）。
    """
    v = np.asarray(violation, dtype=bool)
    if v.size == 0:
        return v
    min_len = max(1, int(round(sustain_s * fs)))
    out = np.zeros_like(v)
    # 找连续 True 段
    idx = np.flatnonzero(np.diff(np.r_[0, v.view(np.int8), 0]))
    starts, ends = idx[0::2], idx[1::2]
    for s, e in zip(starts, ends):
        if (e - s) >= min_len:
            out[s:e] = True
    return out


def derive_alarm_timelines(signals, family_name):
    """
    对一条 record 的各体征，用指定阈值族派生"告警活跃"时间线。
    返回 dict: 规范体征名 -> (active_mask bool array, fs)。
    active_mask=True 表示该样本处该体征告警活跃（越界且持续够久）。
    """
    fam = VITAL_THRESHOLD_FAMILIES[family_name]
    timelines = {}
    for canon, (values, fs) in signals.items():
        if canon not in fam:
            continue
        cfg = fam[canon]
        low, high, sustain_s = cfg["low"], cfg["high"], cfg["sustain_s"]
        v = np.asarray(values, dtype=float)
        viol = np.zeros(v.shape, dtype=bool)
        finite = np.isfinite(v)
        if low is not None:
            viol |= finite & (v < low)
        if high is not None:
            viol |= finite & (v > high)
        active = _sustained_mask(viol, fs, sustain_s)
        timelines[canon] = (active, fs)
    return timelines


def resample_to_common_grid(timelines, grid_dt_s=1.0):
    """
    把各体征的 active_mask 对齐到统一时间栅格（默认 1 s），返回：
      types: list[str]（体征名）
      grid:  2D bool array，shape (n_types, n_bins)，grid[k, t]=该体征在第 t 个 bin 是否告警活跃。
    不同信号长度取最短公共时长；一个 bin 内任一样本活跃即该 bin 活跃。
    """
    if not timelines:
        return [], np.zeros((0, 0), dtype=bool)
    # 各体征总时长（秒）
    durs = []
    for canon, (active, fs) in timelines.items():
        durs.append(active.size / fs if fs else active.size)
    total_s = min(durs) if durs else 0.0
    n_bins = int(np.floor(total_s / grid_dt_s))
    types = sorted(timelines.keys())
    grid = np.zeros((len(types), n_bins), dtype=bool)
    for k, canon in enumerate(types):
        active, fs = timelines[canon]
        for t in range(n_bins):
            s = int(round(t * grid_dt_s * fs))
            e = int(round((t + 1) * grid_dt_s * fs))
            e = min(e, active.size)
            if e > s and active[s:e].any():
                grid[k, t] = True
    return types, grid


def count_cotrigger_windows(grid, window_s=COTRIGGER_WINDOW_S, grid_dt_s=1.0):
    """
    Q1 核心量：滑窗数"≥2 个不同体征告警在同一窗内活跃"的窗数。
    grid: (n_types, n_bins) bool。窗宽 window_s。步长 = 1 bin（非重叠可改）。
    返回 dict: n_bins, n_windows_total, n_cotrigger_windows, cotrigger_rate,
              n_bins_ge1_alarm, n_bins_ge2_alarm。
    """
    n_types, n_bins = grid.shape
    win = max(1, int(round(window_s / grid_dt_s)))
    n_windows = max(0, n_bins - win + 1)
    n_cotrig = 0
    for start in range(n_windows):
        block = grid[:, start:start + win]           # (n_types, win)
        types_active = (block.any(axis=1)).sum()      # 该窗内有几类体征曾活跃
        if types_active >= 2:
            n_cotrig += 1
    # 逐 bin 口径（另一角度）
    per_bin_active_types = grid.sum(axis=0)  # (n_bins,)
    return {
        "n_bins": int(n_bins),
        "n_windows_total": int(n_windows),
        "n_cotrigger_windows": int(n_cotrig),
        "cotrigger_rate": (n_cotrig / n_windows) if n_windows else float("nan"),
        "n_bins_ge1_alarm": int((per_bin_active_types >= 1).sum()),
        "n_bins_ge2_alarm": int((per_bin_active_types >= 2).sum()),
    }


def extract_events(active_mask, fs, grid_dt_s=1.0):
    """
    从逐样本 active_mask 提取告警事件段（连续 True）。
    返回 list[dict(start_bin, end_bin, dur_s)]，bin 以 grid_dt_s 为单位（供 03 弱代理定真假）。
    """
    v = np.asarray(active_mask, dtype=bool)
    if v.size == 0:
        return []
    idx = np.flatnonzero(np.diff(np.r_[0, v.view(np.int8), 0]))
    starts, ends = idx[0::2], idx[1::2]
    events = []
    for s, e in zip(starts, ends):
        dur_s = (e - s) / fs if fs else (e - s)
        sb = int(round((s / fs) / grid_dt_s)) if fs else int(s)
        eb = int(round((e / fs) / grid_dt_s)) if fs else int(e)
        events.append({"start_bin": sb, "end_bin": max(eb, sb + 1), "dur_s": dur_s})
    return events


def label_event_bins(n_bins, events, persist_s, grid_dt_s=1.0):
    """
    弱结局代理：按事件时长把每个告警 bin 标 true(1)/false(0)/inactive(-1)。
    dur_s >= persist_s -> 该事件所有 bin 记 true（持续生理紊乱=真）；否则 false（瞬时/artifact）。
    ⚠️ R8：这是**派生弱代理**（波形自定义），非专家/结局金标；完整结局代理需 CITI matched 临床结局。
    返回 int8 array，长度 n_bins：-1 inactive / 0 false / 1 true。
    """
    lab = np.full(n_bins, -1, dtype=np.int8)
    persist_bins = max(1, int(round(persist_s / grid_dt_s)))
    for ev in events:
        s = max(0, ev["start_bin"])
        e = min(n_bins, ev["end_bin"])
        if e <= s:
            continue
        dur_bins = ev["end_bin"] - ev["start_bin"]
        lab[s:e] = 1 if dur_bins >= persist_bins else 0
    return lab


def pairwise_phi(grid):
    """
    各体征告警活跃 bin 序列的两两相关（phi 系数 = 二值 Pearson），纯 numpy。
    返回 dict: 'A|B' -> phi（-1..1；活跃 bin 太少则 NaN）。
    phi 高 = 该对告警倾向同 bin 一起活跃（Q1 的"相关性共触发"证据）。
    """
    n_types, n_bins = grid.shape
    out = {}
    if n_bins < 2:
        return out
    # 需要体征名，调用方传 types 更好；这里用索引，调用处映射
    for a in range(n_types):
        for b in range(a + 1, n_types):
            x = grid[a].astype(float)
            y = grid[b].astype(float)
            sx, sy = x.std(), y.std()
            if sx == 0 or sy == 0:
                out[(a, b)] = float("nan")  # 一方恒定，phi 无定义
                continue
            phi = float(np.mean((x - x.mean()) * (y - y.mean())) / (sx * sy))
            out[(a, b)] = phi
    return out
