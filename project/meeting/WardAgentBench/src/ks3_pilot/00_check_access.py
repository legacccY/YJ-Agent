# -*- coding: utf-8 -*-
"""
00_check_access.py — STEP 0 数据可达性核查（KS-3 命门前置）
============================================================
回答哪个 Q：无（是三问的**前置门**）——判定 mimic3wdb / mimic3wdb-matched / challenge-2015
           现在能不能不经 CITI credentialing 直接拉。决定核心命门 Q1 现在能否验。
输入：无（探 PhysioNet HTTP + 可选 wfdb 拉一条 record 头）。
输出：access_report.json，字段：
  dataset, url, http_status, access_policy(str), license(str),
  wfdb_probe(str: ok/err/skipped), note
判定：
  - matched 开放 -> Q1/Q2 现在就能在本地 CPU 跑（无需 CITI）。
  - matched gated -> 降级只跑 PhysioNet 2015（Q3 + 单告警 baseline），Q1 标"需 CITI matched"。

⚠️ 本脚本只做**只读 HTTP 探针 + 单 record 头拉取**，不下整库。主线跑。
Windows 规范：pathlib、utf-8、无硬编码盘符。
"""
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
OUT_JSON = OUT_DIR / "access_report.json"

# 三个候选数据集（真源同 .portfolio/datasets.json）
DATASETS = {
    "mimic3wdb":         "https://physionet.org/content/mimic3wdb/1.0/",
    "mimic3wdb-matched": "https://physionet.org/content/mimic3wdb-matched/1.0/",
    "challenge-2015":    "https://physionet.org/content/challenge-2015/1.0.0/",
}

# 用于 wfdb 探针的一条已知 record（不下整库，只拉头）。
# TODO(主线): 若下面 record 名失效，从各库 RECORDS 文件取任一条替换。
#   mimic3wdb-matched 的 record 形如 'p00/p000020/p000020-2183-04-28-17-47'（含病人子目录）。
WFDB_PROBE = {
    # pn_dir 传给 wfdb.rdheader(record_name, pn_dir=...) 做在线只读探针
    "challenge-2015":    {"pn_dir": "challenge-2015/1.0.0/training", "record": "a103l"},
    # matched 的探针 record 走 RECORDS 首条更稳，这里给占位；探针失败不致命（HTTP 已证开放）
    "mimic3wdb-matched": {"pn_dir": "mimic3wdb-matched/1.0", "record": None},
}


def probe_http(url):
    """只读 GET 页面，抓 Access Policy / License 文本。返回 (status, access_policy, license)。"""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (KS3-access-probe)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            html = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        return e.code, f"HTTPError {e.code}", ""
    except Exception as e:  # noqa: BLE001
        return -1, f"ERROR {type(e).__name__}: {e}", ""

    access = _extract_after(html, "Access Policy:")
    lic = _extract_after(html, "License (for files):")
    return status, access, lic


def _extract_after(html, label):
    """从 html 抓 label 之后、剥 tag 的一小段文本（粗解析，够核 open/credentialed）。"""
    idx = html.find(label)
    if idx < 0:
        return "(label not found)"
    chunk = html[idx + len(label): idx + len(label) + 400]
    # 剥 HTML tag
    out, in_tag = [], False
    for ch in chunk:
        if ch == "<":
            in_tag = True
        elif ch == ">":
            in_tag = False
        elif not in_tag:
            out.append(ch)
    text = " ".join("".join(out).split())
    return text[:160]


def probe_wfdb(name):
    """可选：用 wfdb 在线拉一条 record 头，证真能读。wfdb 缺失/失败不致命。"""
    cfg = WFDB_PROBE.get(name)
    if not cfg or not cfg.get("record"):
        return "skipped (no probe record configured)"
    try:
        import wfdb  # noqa: WPS433
    except ImportError:
        return "skipped (wfdb not installed)"
    try:
        hdr = wfdb.rdheader(cfg["record"], pn_dir=cfg["pn_dir"])
        return f"ok (record={cfg['record']}, n_sig={hdr.n_sig}, fs={hdr.fs}, sigs={hdr.sig_name})"
    except Exception as e:  # noqa: BLE001
        return f"err {type(e).__name__}: {e}"


def main():
    report = {}
    for name, url in DATASETS.items():
        status, access, lic = probe_http(url)
        wfdb_res = probe_wfdb(name)
        is_open = "anyone can access" in access.lower()
        report[name] = {
            "url": url,
            "http_status": status,
            "access_policy": access,
            "license": lic,
            "is_open_access": is_open,
            "wfdb_probe": wfdb_res,
        }
        print(f"[{name}] status={status} open={is_open}")
        print(f"    access_policy: {access}")
        print(f"    license      : {lic}")
        print(f"    wfdb_probe   : {wfdb_res}")

    # 命门前置判定
    matched_open = report.get("mimic3wdb-matched", {}).get("is_open_access", False)
    report["_verdict"] = {
        "mimic3wdb_matched_open": matched_open,
        "q1_feasible_now": matched_open,
        "note": (
            "matched 开放 -> Q1/Q2 现在即可在本地 CPU 跑，无需 CITI credentialing。"
            if matched_open else
            "matched 非开放 -> 降级只跑 PhysioNet 2015（Q3 + 单告警 baseline），"
            "Q1/Q2 标'需 CITI matched'。"
        ),
    }

    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[written] {OUT_JSON}")
    print(f"[VERDICT] q1_feasible_now = {matched_open}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
