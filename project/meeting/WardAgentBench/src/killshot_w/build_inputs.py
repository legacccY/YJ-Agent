# -*- coding: utf-8 -*-
"""
build_inputs.py — 每条记录 -> 文本表征 A + 图像表征 B
====================================================
服务哪个 §/lever：路 W' $5 kill-shot 输入构建。对每条 challenge-2015 记录取报警点
  （300s）前 window_seconds 的波形，产两种喂 MLLM 的表征：
    表征 A（数字/文本）：主 ECG II + 1 备用脉动波，下采样，序列化成带元数据的文本。
    表征 B（图像）：matplotlib(Agg) 渲染同样导联为 PNG（网格 + 时间轴 + 英文标签）。

⚠️ 只写告警类型进元数据；**绝不把专家 True/False 金标写进文本/图**（评估集不可泄漏）。
输入：DATA_DIR/manifest.csv（download_data 产）+ DATA_DIR 下 .hea/.mat。
输出：INPUTS_DIR/<record>_text.txt、INPUTS_DIR/<record>.png、INPUTS_DIR/inputs_manifest.csv。

Windows 规范：pathlib、utf-8、matplotlib Agg、纯 numpy 下采样（无 scipy，避 OMP）、英文标签。
我不跑代码，写完交主线跑。烟测：python build_inputs.py --limit 2。
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

import matplotlib
matplotlib.use("Agg")  # 无界面后端（Windows 规范）
import matplotlib.pyplot as plt  # noqa: E402


def load_manifest(path):
    rows = []
    with Path(path).open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def read_window(record_path, fs_hint):
    """
    读一条记录报警点前 window 的物理信号。
    返回 (sig[np.ndarray T×n], sig_name[list], units[list], fs[float]) 或 None。
    """
    import wfdb  # noqa: WPS433
    # 先读 header 拿真实 fs / sig_len（不臆想）
    hdr = wfdb.rdheader(str(record_path))
    fs = float(hdr.fs) if hdr.fs else float(fs_hint or C.NATIVE_HZ)
    sig_len = int(hdr.sig_len)

    onset = int(round(C.ALARM_ONSET_S * fs))
    win = int(round(C.WINDOW_SECONDS * fs))
    sampto = min(onset, sig_len)          # 报警点（或记录末尾）
    sampfrom = max(0, sampto - win)       # 前推 window
    if sampto - sampfrom < int(0.5 * win):
        print(f"[warn] {record_path.name} 可用窗过短 (from={sampfrom} to={sampto} "
              f"sig_len={sig_len})，仍取可得段。")

    rec = wfdb.rdrecord(str(record_path), sampfrom=sampfrom, sampto=sampto)
    sig = np.asarray(rec.p_signal, dtype=float)  # T × n_sig，物理单位
    units = list(rec.units or [""] * rec.n_sig)
    return sig, list(rec.sig_name), units, fs


def select_leads(sig_name):
    """选 ≤N_LEADS 导联：主 ECG（II 优先）+ 备用脉动波，凑不满退备用 ECG。返回索引 list。"""
    name_to_idx = {}
    for i, nm in enumerate(sig_name):
        name_to_idx.setdefault(nm, i)  # 同名取首个

    chosen = []

    def take(priority):
        for nm in priority:
            if nm in name_to_idx and name_to_idx[nm] not in chosen:
                chosen.append(name_to_idx[nm])
                return True
        return False

    take(C.ECG_LEAD_PRIORITY)               # 主 ECG
    if len(chosen) < C.N_LEADS:
        take(C.PULSATILE_LEAD_PRIORITY)     # 备用脉动波
    # 仍不满：拿剩余 ECG 优先表里其它导联
    idx_priority = 0
    while len(chosen) < C.N_LEADS and idx_priority < len(C.ECG_LEAD_PRIORITY):
        nm = C.ECG_LEAD_PRIORITY[idx_priority]
        if nm in name_to_idx and name_to_idx[nm] not in chosen:
            chosen.append(name_to_idx[nm])
        idx_priority += 1
    # 再不满：随便补通道，保证有输出
    for i in range(len(sig_name)):
        if len(chosen) >= C.N_LEADS:
            break
        if i not in chosen:
            chosen.append(i)
    return chosen[:C.N_LEADS]


def downsample(x, fs_in, fs_out):
    """
    纯 numpy 下采样：先 box-average 抗混叠再等间隔抽（无 scipy，避 OMP 冲突）。
    x: 1D。返回 (x_ds, fs_actual)。fs_out>=fs_in 时原样返回。
    """
    x = np.asarray(x, dtype=float)
    if fs_out >= fs_in or len(x) == 0:
        return x, fs_in
    factor = int(round(fs_in / fs_out))
    if factor <= 1:
        return x, fs_in
    n = (len(x) // factor) * factor
    if n == 0:
        return x, fs_in
    # box-average（简易抗混叠）后抽稀
    ds = x[:n].reshape(-1, factor).mean(axis=1)
    fs_actual = fs_in / factor
    return ds, fs_actual


def to_int_bool(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def serialize_text(record_id, alarm_type, leads):
    """
    leads: list of dict(name, units, fs, values(np.ndarray))。
    产带元数据的文本 payload（控 token：MAX_TEXT_SAMPLES_PER_LEAD + 定小数位）。
    """
    parts = [
        f"Record: {record_id}",
        f"Alarm type: {C.ALARM_TYPES.get(alarm_type, alarm_type)}",
        f"Window: {C.WINDOW_SECONDS} s immediately before the alarm.",
        f"Samples listed oldest->newest; the last value is at the alarm time.",
        "",
    ]
    for ld in leads:
        vals = ld["values"]
        # 再等间隔抽稀到硬顶（若还超）
        if len(vals) > C.MAX_TEXT_SAMPLES_PER_LEAD:
            step = int(np.ceil(len(vals) / C.MAX_TEXT_SAMPLES_PER_LEAD))
            vals = vals[::step]
        vals = np.round(np.nan_to_num(vals, nan=0.0), C.TEXT_DECIMALS)
        seq = ",".join(f"{v:g}" for v in vals)
        parts.append(
            f"Lead {ld['name']} (unit={ld['units'] or 'a.u.'}, "
            f"sample_rate={ld['fs']:.4g} Hz, n={len(vals)}):"
        )
        parts.append(seq)
        parts.append("")
    return "\n".join(parts)


def render_image(record_id, alarm_type, leads, out_png):
    """matplotlib(Agg) 堆叠子图渲染导联；英文标签、网格、时间轴（0=报警点）。不含金标。"""
    n = len(leads)
    fig, axes = plt.subplots(n, 1, figsize=(11, 2.4 * n + 0.6), sharex=True)
    if n == 1:
        axes = [axes]
    for ax, ld in zip(axes, leads):
        vals = np.nan_to_num(ld["values"], nan=np.nan)
        # 时间轴：window 秒内，0 = 报警时刻，最左 = -window
        t = np.linspace(-C.WINDOW_SECONDS, 0.0, num=len(vals), endpoint=True)
        ax.plot(t, vals, linewidth=0.7, color="#111111")
        ax.grid(True, which="major", linestyle="-", linewidth=0.4, alpha=0.35)
        ax.grid(True, which="minor", linestyle=":", linewidth=0.3, alpha=0.25)
        ax.minorticks_on()
        ax.set_ylabel(f"{ld['name']}\n({ld['units'] or 'a.u.'})")
        ax.margins(x=0)
    axes[-1].set_xlabel("Time relative to alarm (s)  [0 = alarm onset]")
    axes[0].set_title(
        f"ICU waveform before '{C.ALARM_TYPES.get(alarm_type, alarm_type)}' alarm "
        f"(record {record_id})"
    )
    fig.tight_layout()
    fig.savefig(str(out_png), dpi=C.IMAGE_DPI)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=str, default=str(C.DATA_DIR))
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 条（烟测用）")
    args = ap.parse_args()

    C.ensure_dirs()
    data_dir = Path(args.data_dir)
    manifest = data_dir / C.MANIFEST_CSV
    if not manifest.exists():
        print(f"[ERR] 找不到 {manifest}，先跑 download_data.py。")
        return 2

    rows = load_manifest(manifest)
    if args.limit > 0:
        rows = rows[: args.limit]

    out_fields = ["record_id", "alarm_type", "expert_label", "leads_used",
                  "text_path", "image_path", "fs_native", "hz_text", "hz_image",
                  "window_seconds"]
    out_rows = []
    n_ok = 0
    for r in rows:
        rid = r["record_id"]
        atype = r["alarm_type"]
        rec_path = data_dir / rid
        if not (rec_path.with_suffix(".hea")).exists():
            print(f"[warn] 缺 {rid}.hea，跳过（下载不全？）")
            continue
        try:
            sig, sig_name, units, fs = read_window(rec_path, r.get("fs"))
        except Exception as e:  # noqa: BLE001
            print(f"[warn] 读窗失败 {rid}: {type(e).__name__}: {e}")
            continue

        lead_idx = select_leads(sig_name)
        leads = []
        for i in lead_idx:
            vals_ds, fs_ds = downsample(sig[:, i], fs, C.DOWNSAMPLE_HZ_TEXT)
            leads.append({"name": sig_name[i], "units": units[i] if i < len(units) else "",
                          "fs": fs_ds, "values": vals_ds})
        # 图像用较高保真下采样，单独算一份
        leads_img = []
        for i in lead_idx:
            vals_img, fs_img = downsample(sig[:, i], fs, C.DOWNSAMPLE_HZ_IMAGE)
            leads_img.append({"name": sig_name[i], "units": units[i] if i < len(units) else "",
                              "fs": fs_img, "values": vals_img})

        text_payload = serialize_text(rid, atype, leads)
        text_path = C.INPUTS_DIR / f"{rid}_text.txt"
        text_path.write_text(text_payload, encoding="utf-8")

        image_path = C.INPUTS_DIR / f"{rid}.png"
        try:
            render_image(rid, atype, leads_img, image_path)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] 渲图失败 {rid}: {type(e).__name__}: {e}")
            image_path = Path("")

        leads_used = "|".join(sig_name[i] for i in lead_idx)
        out_rows.append({
            "record_id": rid, "alarm_type": atype, "expert_label": r["expert_label"],
            "leads_used": leads_used,
            "text_path": str(text_path), "image_path": str(image_path),
            "fs_native": f"{fs:g}", "hz_text": f"{C.DOWNSAMPLE_HZ_TEXT:g}",
            "hz_image": f"{C.DOWNSAMPLE_HZ_IMAGE:g}", "window_seconds": C.WINDOW_SECONDS,
        })
        n_ok += 1
        print(f"[ok] {rid}  leads={leads_used}  fs={fs:g}")

    if not out_rows:
        print("[ERR] 没产出任何输入（检查下载 / 导联名）。")
        return 2

    out_manifest = C.INPUTS_DIR / C.INPUTS_MANIFEST_CSV
    with out_manifest.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        w.writerows(out_rows)
    print(f"[written] {out_manifest}  ({n_ok} records)")
    print("[done] 下一步：python run_models.py（先 --dry-run 看不花 API 的预演）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
