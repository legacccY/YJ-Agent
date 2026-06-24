"""
一次性修复脚本：把 results/sanity_samesource_vim.csv 里 note 列含逗号的值
用 csv.writer 的自动引号重写，让下游 parser 能正确识别 resid_auroc 列。

使用方法（主线执行）：
    python scripts/_fix_sanity_csv_quote.py

不修改数据值，仅给含逗号字段加 RFC 4180 引号。
"""

import csv
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parent.parent / "results" / "sanity_samesource_vim.csv"
TMP_PATH = CSV_PATH.with_suffix(".tmp")


def main():
    # 读：用 csv.reader 容错（即使原来已有奇怪的分列也能捞到原始行）
    rows = []
    with open(CSV_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        print("[ERR] CSV 为空，退出。")
        return

    header = rows[0]
    n_cols = len(header)
    print(f"[INFO] 列数={n_cols}，标题={header}")

    # 检查每行列数，note 是最后一列（index n_cols-1）
    # 若行列数 > n_cols，说明 note 列含逗号被多切了——合并多余字段回最后一列
    fixed_rows = [header]
    for i, row in enumerate(rows[1:], start=2):
        if len(row) == n_cols:
            fixed_rows.append(row)
        elif len(row) > n_cols:
            # 合并第 n_cols 及以后的字段为 note
            merged_note = ",".join(row[n_cols - 1:])
            fixed = row[: n_cols - 1] + [merged_note]
            fixed_rows.append(fixed)
            print(f"  [行{i}] 合并 {len(row)-n_cols+1} 个多余字段 → note={merged_note!r}")
        else:
            # 列数不足，原样保留（不应出现）
            print(f"  [行{i}] 警告：列数不足 ({len(row)})，原样保留")
            fixed_rows.append(row)

    # 写：csv.writer 自动给含逗号字段加引号（QUOTE_MINIMAL）
    with open(TMP_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerows(fixed_rows)

    # 原子替换
    import shutil
    shutil.move(str(TMP_PATH), str(CSV_PATH))
    print(f"[OK] 已重写 {CSV_PATH}（{len(fixed_rows)-1} 数据行）")


if __name__ == "__main__":
    main()
