"""
fetch_repo2.py — 无 API 版逐文件拉取（避 GitHub API 限流）
.lyr 文件名+大小跨所有 bat 目录相同（同架构，仅权重值不同）→ 从已完整的 bat512
取 manifest（EL 36 文件 + im 4 文件），所有 7 batch 复用，纯 raw URL 下载，零 API。
幂等：已存在且大小对的跳过。

用法: python fetch_repo2.py
"""
import os, sys, time, urllib.request, ssl

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(ROOT, "repo")
RAW = "https://raw.githubusercontent.com/KarchinLab/bigmhc/master/{}"
CTX = ssl.create_default_context()
HDR = {"User-Agent": "qib-fetch"}
BATCHES = [512, 1024, 2048, 4096, 8192, 16384, 32768]


def manifest_from(batdir):
    """从已完整目录取 {filename: size}"""
    return {f: os.path.getsize(os.path.join(batdir, f))
            for f in os.listdir(batdir) if f.endswith(".lyr")}


def fetch_file(relpath, expect_size, dest):
    if os.path.exists(dest) and os.path.getsize(dest) == expect_size:
        return True
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    url = RAW.format(relpath)
    for attempt in range(8):
        try:
            req = urllib.request.Request(url, headers=HDR)
            with urllib.request.urlopen(req, context=CTX, timeout=300) as r:
                data = r.read()
            if len(data) != expect_size:
                print(f"  [size {attempt}] {relpath}: {len(data)}!={expect_size}", file=sys.stderr)
                time.sleep(2); continue
            with open(dest, "wb") as f:
                f.write(data)
            return True
        except Exception as e:
            print(f"  [retry {attempt}] {relpath}: {e}", file=sys.stderr)
            time.sleep(3)
    print(f"  FAIL {relpath}", file=sys.stderr)
    return False


def main():
    el_manifest = manifest_from(os.path.join(REPO, "models", "bat512"))
    im_manifest = manifest_from(os.path.join(REPO, "models", "bat512", "im"))
    print(f"[manifest] EL {len(el_manifest)} files, im {len(im_manifest)} files")

    for b in BATCHES:
        # EL base
        ok = 0
        for fn, sz in el_manifest.items():
            rel = f"models/bat{b}/{fn}"
            if fetch_file(rel, sz, os.path.join(REPO, "models", f"bat{b}", fn)):
                ok += 1
        # im subdir
        iok = 0
        for fn, sz in im_manifest.items():
            rel = f"models/bat{b}/im/{fn}"
            if fetch_file(rel, sz, os.path.join(REPO, "models", f"bat{b}", "im", fn)):
                iok += 1
        print(f"[bat{b}] EL {ok}/{len(el_manifest)}  im {iok}/{len(im_manifest)}")

    # 完整性总检
    print("=== 完整性 ===")
    allok = True
    for b in BATCHES:
        for fn, sz in el_manifest.items():
            p = os.path.join(REPO, "models", f"bat{b}", fn)
            if not (os.path.exists(p) and os.path.getsize(p) == sz):
                print(f"MISSING bat{b}/{fn}"); allok = False
        for fn, sz in im_manifest.items():
            p = os.path.join(REPO, "models", f"bat{b}", "im", fn)
            if not (os.path.exists(p) and os.path.getsize(p) == sz):
                print(f"MISSING bat{b}/im/{fn}"); allok = False
    print("ALL COMPLETE" if allok else "INCOMPLETE")


if __name__ == "__main__":
    main()
