"""
fetch_repo.py — 健壮逐文件拉取 BigMHC repo（绕大流截断）
组装可跑 repo:  repo/{src, data/pseudoseqs.csv+example, models/bat{X}/(+im/)}
每个 .lyr 经 GitHub raw URL 下载，校验大小（对 GitHub API 报的 size），不符重试。
官方 -m=im = 7 模型 ensemble：bat512..bat32768 各 EL 基 + im 子目录。

用法: python fetch_repo.py   (幂等，已完整文件跳过)
"""
import os, sys, json, time, urllib.request, ssl

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(ROOT, "repo")
API = "https://api.github.com/repos/KarchinLab/bigmhc/contents/{}"
RAW = "https://raw.githubusercontent.com/KarchinLab/bigmhc/master/{}"
CTX = ssl.create_default_context()
HDR = {"User-Agent": "qib-fetch"}

BATCHES = [512, 1024, 2048, 4096, 8192, 16384, 32768]


def api_list(path):
    """GitHub API 列目录 → [(name, size, type)]"""
    req = urllib.request.Request(API.format(path), headers=HDR)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, context=CTX, timeout=60) as r:
                data = json.load(r)
            return [(e["name"], e.get("size", 0), e["type"]) for e in data]
        except Exception as e:
            print(f"  [api retry {attempt}] {path}: {e}", file=sys.stderr)
            time.sleep(3)
    raise RuntimeError(f"api_list failed: {path}")


def fetch_file(relpath, expect_size, dest):
    """下载单文件到 dest，校验大小，不符重试。已存在且大小对则跳过。"""
    if os.path.exists(dest) and (expect_size == 0 or os.path.getsize(dest) == expect_size):
        return True
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    url = RAW.format(relpath)
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers=HDR)
            with urllib.request.urlopen(req, context=CTX, timeout=300) as r:
                data = r.read()
            if expect_size and len(data) != expect_size:
                print(f"  [size mismatch {attempt}] {relpath}: got {len(data)} != {expect_size}", file=sys.stderr)
                time.sleep(2)
                continue
            with open(dest, "wb") as f:
                f.write(data)
            return True
        except Exception as e:
            print(f"  [dl retry {attempt}] {relpath}: {e}", file=sys.stderr)
            time.sleep(3)
    print(f"  FAIL {relpath}", file=sys.stderr)
    return False


def fetch_dir(path):
    """下载一个目录下所有 file 类型（非递归）到 repo/<path>/"""
    entries = api_list(path)
    ok = 0
    for name, size, typ in entries:
        if typ != "file":
            continue
        rel = f"{path}/{name}"
        dest = os.path.join(REPO, path, name)
        if fetch_file(rel, size, dest):
            ok += 1
    print(f"[dir] {path}: {ok}/{sum(1 for _,_,t in entries if t=='file')} files ok")
    return ok


def main():
    # 1. src/（8 文件）
    print("=== src/ ===")
    fetch_dir("src")
    # 2. data/ pseudoseqs + example（小）
    print("=== data/ ===")
    for name, size, typ in api_list("data"):
        if typ == "file" and (name == "pseudoseqs.csv" or name.startswith("example")):
            fetch_file(f"data/{name}", size, os.path.join(REPO, "data", name))
    # 3. models: 7 batch × (EL 基 + im 子目录)
    for b in BATCHES:
        print(f"=== models/bat{b} (EL base) ===")
        fetch_dir(f"models/bat{b}")
        print(f"=== models/bat{b}/im ===")
        fetch_dir(f"models/bat{b}/im")
    print("=== DONE ===")


if __name__ == "__main__":
    main()
