#!/usr/bin/env python3
"""HPC 数据恢复排查 — ICLR P-2/P-3 缺失数据全面搜索（只读，不删不改不拉）。
凭证运行时从 project/HPC_WORKFLOW.md 解析，本脚本不硬编码任何密钥（防 commit 泄露）。
搜：ITB 图像 / quality_labels_all / abcd_cache / efficientnet_index / per-sample eval 输出。
用法：python tools/hpc_p2_recover.py
"""
import paramiko, sys, re, pathlib

ROOTS = "/gpfs/work/bio/jiayu2403 /gpfs/home/bio/jiayu2403"


def load_creds():
    """从 HPC_WORKFLOW.md 的连接信息表解析 host/user/pw（已在 repo，不新增泄露面）。"""
    md = pathlib.Path(__file__).resolve().parents[1] / "project" / "HPC_WORKFLOW.md"
    txt = md.read_text(encoding="utf-8", errors="replace")

    def cell(label):
        m = re.search(r"\|\s*" + label + r"\s*\|\s*`?([^`|]+?)`?\s*\|", txt)
        return m.group(1).strip() if m else None
    host = cell("主机") or cell("host")
    user = cell("用户名") or cell("username")
    pw = cell("密码") or cell("password")
    if not (host and user and pw):
        print("CRED-PARSE-FAIL: 在 HPC_WORKFLOW.md 未解析到 host/user/pw")
        sys.exit(2)
    return host, user, pw


def main():
    host, user, pw = load_creds()
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        c.connect(host, username=user, password=pw, timeout=20,
                  banner_timeout=20, auth_timeout=20)
    except Exception as e:
        print("CONNECT-FAIL:", type(e).__name__, str(e)[:160])
        sys.exit(1)
    print("CONNECT-OK\n")

    def run(cmd, t=120):
        _, o, e = c.exec_command(cmd, timeout=t)
        return o.read().decode(errors="replace"), e.read().decode(errors="replace")

    print("=" * 60)
    print("[1] P-2 中间产物（名+大小）")
    for pat in ["quality_labels_all.csv", "quality_labels*.csv", "abcd_cache.csv",
                "abcd*.csv", "efficientnet_index.csv", "efnet_index.csv",
                "*efficientnet*index*", "efnet*.csv", "efnet*.npy"]:
        out, _ = run(f"find {ROOTS} -iname '{pat}' -printf '%10s  %p\\n' 2>/dev/null | head -20")
        print(f"--- {pat} ---")
        print(out.strip() or "(none)")

    print("=" * 60)
    print("[2] per-sample / held-out / ablation / qvib eval 输出")
    out, _ = run(
        f"find {ROOTS} \\( -iname '*ablation*' -o -iname '*per_sample*' "
        f"-o -iname '*persample*' -o -iname '*held*out*' -o -iname '*heldout*' "
        f"-o -iname '*qvib*' -o -iname '*eval_report*' \\) -printf '%10s  %p\\n' "
        f"2>/dev/null | head -40")
    print(out.strip() or "(none)")

    print("=" * 60)
    print("[3] 全树 csv（大小，>1KB）top50")
    out, _ = run(
        f"find {ROOTS} -name '*.csv' -size +1k -printf '%10s  %p\\n' "
        f"2>/dev/null | sort -rn | head -50")
    print(out.strip() or "(none)")

    print("=" * 60)
    print("[4] ITB / 图像目录 + 计数")
    out, _ = run(f"find {ROOTS} -type d -iname '*itb*' 2>/dev/null | head -20")
    print("--- itb dirs ---")
    print(out.strip() or "(none)")

    c.close()
    print("\nDONE.")


if __name__ == "__main__":
    main()
