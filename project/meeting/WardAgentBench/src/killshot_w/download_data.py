# -*- coding: utf-8 -*-
"""
download_data.py — 拉 PhysioNet 2015 均衡子集 + 写金标 manifest
==============================================================
服务哪个 §/lever：路 W' $5 kill-shot 的数据准备。取跨 5 类均衡、真假都有的
  ~N 条 challenge-2015 记录（专家 True/False 金标写在 .hea 注释 / rdheader.comments）。

流程：
  1. 取 training 集 RECORDS 索引（wfdb.get_record_list，失败退回抓 RECORDS 文本）。
  2. 按记录名首字母（a/b/t/v/f）分桶（仅定探测优先序，类型权威仍靠解析 comments）。
  3. 在线只读各条 header（wfdb.rdheader(rec, pn_dir=PN_DIR)）→ 解析告警类型 + True/False。
  4. 每类 best-effort 选 ~N_PER_CLASS 条、真假尽量各半；凑成 ~N_TOTAL。
  5. wfdb.dl_database 下选中记录（.hea + .mat）到 DATA_DIR。
  6. 写 DATA_DIR/manifest.csv：record_id, alarm_type, expert_label(TRUE/FALSE), fs,
     n_sig, sig_names, seg_len_s, name_prefix, prefix_type_match。

⚠️ 金标 = 官方 True/False（非派生），可 Bash 核（R1）。R3 固定 seed 采样可复现。
⚠️ 注释格式假设见 parse_comments 的 TODO —— **主线首跑必核实一条 rdheader().comments
   的确切内容**，不符再调解析。我不跑代码。
Windows 规范：pathlib、utf-8、纯 numpy。
"""
import argparse
import csv
import random
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402


# ---------------------------------------------------------------------------
# header 注释解析（复用 ks3_pilot/01_physionet2015_baseline.py 的经验证约定）
# ---------------------------------------------------------------------------
def parse_comments(comments):
    """
    从 wfdb rdheader().comments（list[str]，每项是一行注释、已剥前导 '#'）
    解析 (alarm_type_canonical, is_true_alarm)。

    官方约定（ks3_pilot 已验的经验）：注释里含
      - 告警类型词：Asystole / Bradycardia / Tachycardia /
        Ventricular Tachycardia / Ventricular Flutter/Fib（可能下划线或空格）
      - True alarm / False alarm 之一
    TODO(主线首跑): 打印一条真实 comments 核对确切拼写/大小写/是否合并同一行，
      不符则按实际微调下面匹配。
    """
    alarm_type = None
    is_true = None
    blob = " ".join(comments).lower()

    for canon in C.ALARM_TYPES:
        probe_underscore = canon.lower()               # ventricular_tachycardia
        probe_space = canon.lower().replace("_", " ")  # ventricular tachycardia
        if probe_underscore in blob or probe_space in blob:
            alarm_type = canon
    # Ventricular_Flutter_Fib 常写 'ventricular flutter' / 'flutter/fib'，兜底一层
    if alarm_type is None:
        if "flutter" in blob or "fib" in blob:
            alarm_type = "Ventricular_Flutter_Fib"

    if "true alarm" in blob:
        is_true = 1
    elif "false alarm" in blob:
        is_true = 0
    return alarm_type, is_true


def get_record_list():
    """取 challenge-2015 training RECORDS。优先 wfdb，失败退 HTTP 抓 RECORDS 文本。"""
    try:
        import wfdb  # noqa: WPS433
        recs = wfdb.get_record_list(C.PN_DIR)
        if recs:
            return [r.strip().strip("/").split("/")[-1] for r in recs if r.strip()]
    except Exception as e:  # noqa: BLE001
        print(f"[warn] wfdb.get_record_list 失败({type(e).__name__}: {e})，退回 HTTP RECORDS")
    # 退回：直接抓 RECORDS 文本
    url = f"https://physionet.org/files/{C.PN_DIR}/RECORDS"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (ks-w)"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
        return [ln.strip().split("/")[-1] for ln in text.splitlines() if ln.strip()]
    except Exception as e:  # noqa: BLE001
        print(f"[ERR] 取 RECORDS 失败：{type(e).__name__}: {e}")
        return []


def probe_header(rec):
    """在线只读一条 header，返回 dict 或 None。不下 .mat（只 header，省流量）。"""
    try:
        import wfdb  # noqa: WPS433
        hdr = wfdb.rdheader(rec, pn_dir=C.PN_DIR)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] rdheader 失败 {rec}: {type(e).__name__}: {e}")
        return None
    atype, is_true = parse_comments(list(hdr.comments or []))
    fs = float(hdr.fs) if hdr.fs else None
    seg_len_s = (hdr.sig_len / fs) if (fs and hdr.sig_len) else None
    return {
        "record": rec,
        "alarm_type": atype,
        "is_true_alarm": is_true,
        "fs": fs,
        "n_sig": int(hdr.n_sig) if hdr.n_sig else None,
        "sig_names": list(hdr.sig_name or []),
        "seg_len_s": seg_len_s,
    }


def select_balanced(records, rng):
    """
    按类均衡采样。每类 best-effort 选 N_PER_CLASS 条、真假尽量各半。
    先按记录名首字母分桶定探测顺序（省 header 探测），权威类型仍以解析为准。
    返回 (selected_meta:list[dict], probe_count:int)。
    """
    # 按首字母分桶（仅定探测优先序）；桶内 shuffle 保随机 + 可复现（rng 固定 seed）。
    buckets = defaultdict(list)
    for r in records:
        buckets[r[:1].lower()].append(r)
    for k in buckets:
        rng.shuffle(buckets[k])

    # 每个 canonical 类型收集 true[] / false[]（按标签配额封顶，保证真假各半 best-effort）。
    collected = {t: {"true": [], "false": []} for t in C.ALARM_TYPES}
    target = {"true": C.N_TRUE_PER_CLASS_TARGET, "false": C.N_FALSE_PER_CLASS_TARGET}
    probe_count = 0
    probed = {}          # rec -> meta 缓存：leftover 记录跨多类队列不重复在线探测
    selected_ids = set()  # 全局去重，防同一记录被两个类都选中

    def class_full(t):
        c = collected[t]
        return (len(c["true"]) >= target["true"]
                and len(c["false"]) >= target["false"])

    # (type -> 候选记录队列)。前缀命中的入对应类；无前缀映射的 leftover 并入所有类兜底。
    type_queue = {t: list(buckets.get(pfx, []))
                  for pfx, t in C.RECORD_PREFIX_TYPE.items()}
    for t in C.ALARM_TYPES:
        type_queue.setdefault(t, [])
    leftover = [r for r in records
                if r[:1].lower() not in C.RECORD_PREFIX_TYPE]
    for t in type_queue:
        type_queue[t].extend(leftover)

    active = True
    while active and probe_count < C.MAX_HEADER_PROBES:
        active = False
        for t in C.ALARM_TYPES:
            if class_full(t):
                continue
            q = type_queue.get(t, [])
            if not q:
                continue
            active = True
            rec = q.pop(0)
            if rec in selected_ids:
                continue
            # 探测缓存：leftover 记录可能已在别类队列被探过，复用不重发请求
            if rec in probed:
                meta = probed[rec]
            else:
                probe_count += 1
                meta = probe_header(rec)
                probed[rec] = meta
            if meta is None or meta["alarm_type"] is None or meta["is_true_alarm"] is None:
                continue
            true_type = meta["alarm_type"]  # 权威类型（以解析为准，不靠前缀）
            if true_type not in collected:
                continue
            label = "true" if meta["is_true_alarm"] == 1 else "false"
            slot = collected[true_type][label]
            # 只在该标签配额未满时收 -> 真假各半 best-effort（某标签稀缺则该类偏斜但仍两者兼有）
            if len(slot) < target[label]:
                slot.append(meta)
                selected_ids.add(rec)
            if probe_count >= C.MAX_HEADER_PROBES:
                break

    # 扁平化 selected（每类 true 段 + false 段）
    selected = []
    for t in C.ALARM_TYPES:
        selected.extend(collected[t]["true"])
        selected.extend(collected[t]["false"])
    return selected, probe_count


def download_records(rec_names, out_dir):
    """直连 physionet.org/files 下 .hea + .mat。
    （wfdb.dl_database(PN_DIR=...training) 会把版本号拼重成 .../1.0.0/1.0.0/training/ → 404，
     首跑实证；.hea 头引用 {rec}.mat，直下最稳，主线 2026-07-04 核实修。）"""
    import urllib.request  # noqa: WPS433
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"https://physionet.org/files/{C.PN_DIR}"
    for rec in rec_names:
        for ext in (".hea", ".mat"):
            dest = out_dir / f"{rec}{ext}"
            if dest.exists() and dest.stat().st_size > 0:
                continue
            url = f"{base}/{rec}{ext}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (ks-w)"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = resp.read()
            dest.write_bytes(data)


def write_manifest(selected, out_csv):
    fields = ["record_id", "alarm_type", "expert_label", "is_true_alarm",
              "fs", "n_sig", "sig_names", "seg_len_s",
              "name_prefix", "prefix_type_match"]
    with Path(out_csv).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in selected:
            pfx = m["record"][:1].lower()
            prefix_type = C.RECORD_PREFIX_TYPE.get(pfx)
            w.writerow({
                "record_id": m["record"],
                "alarm_type": m["alarm_type"],
                "expert_label": "TRUE" if m["is_true_alarm"] == 1 else "FALSE",
                "is_true_alarm": m["is_true_alarm"],
                "fs": m["fs"],
                "n_sig": m["n_sig"],
                "sig_names": "|".join(m["sig_names"]),
                "seg_len_s": m["seg_len_s"],
                "name_prefix": pfx,
                "prefix_type_match": int(prefix_type == m["alarm_type"]),
            })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-download", action="store_true",
                    help="只选样 + 写 manifest，不真下 .mat（先看均衡再决定下不下）")
    ap.add_argument("--data-dir", type=str, default=str(C.DATA_DIR))
    args = ap.parse_args()

    C.ensure_dirs()
    out_dir = Path(args.data_dir)
    rng = random.Random(C.RANDOM_SEED)

    records = get_record_list()
    if not records:
        print("[ERR] 取不到 RECORDS，检查网络 / PN_DIR。")
        return 2
    print(f"[info] training RECORDS 共 {len(records)} 条")

    selected, n_probe = select_balanced(records, rng)
    print(f"[info] 探测 header {n_probe} 次，选中 {len(selected)} 条")
    # 均衡打印
    per_class = defaultdict(lambda: [0, 0])  # type -> [n_true, n_false]
    for m in selected:
        idx = 0 if m["is_true_alarm"] == 1 else 1
        per_class[m["alarm_type"]][idx] += 1
    print("[info] 每类 (true/false):")
    for t in C.ALARM_TYPES:
        tt, ff = per_class[t]
        print(f"    {t:28s}  true={tt}  false={ff}")

    if not selected:
        print("[ERR] 未选到任何条（检查 header 解析 / 探测上限）。")
        return 2

    manifest = out_dir / C.MANIFEST_CSV
    out_dir.mkdir(parents=True, exist_ok=True)
    write_manifest(selected, manifest)
    print(f"[written] {manifest}  ({len(selected)} rows)")

    if args.no_download:
        print("[info] --no-download：跳过下载 .mat。确认均衡 OK 后去掉此旗重跑即下。")
        return 0

    print(f"[info] 下载 {len(selected)} 条记录到 {out_dir} ...")
    try:
        download_records([m["record"] for m in selected], out_dir)
    except Exception as e:  # noqa: BLE001
        print(f"[ERR] 下载失败：{type(e).__name__}: {e}")
        print("      先跑 --no-download 看均衡；下载路径问题见 config PN_DIR TODO。")
        return 3
    print("[done] 下载完成。下一步：python build_inputs.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
