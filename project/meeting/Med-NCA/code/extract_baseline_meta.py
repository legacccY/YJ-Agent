"""
extract_baseline_meta.py
任务1 (S0): 固化 R1 test 样本清单 -> results/test_ids_r1.txt
任务2 (C1): R1 训练收敛曲线  -> results/r1_convergence.csv
"""

import sys
import os
import pickle
import csv
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFFICIAL_REPO = os.path.join(ROOT, "M3D-NCA-official")
SPLIT_PATH    = os.path.join(ROOT, "checkpoints", "r1_hippocampus", "data_split.dt")
TB_DIR        = os.path.join(ROOT, "checkpoints", "r1_hippocampus", "tensorboard")
OUT_IDS       = os.path.join(ROOT, "results", "test_ids_r1.txt")
OUT_CONV      = os.path.join(ROOT, "results", "r1_convergence.csv")

os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)

# ─────────────────────────────────────────────────────────────
# 任务1: 加载 data_split.dt，提取 test IDs
# ─────────────────────────────────────────────────────────────
print("=== 任务1: 加载 data_split.dt ===")

def try_load_split(path, add_repo_path=False):
    if add_repo_path and OFFICIAL_REPO not in sys.path:
        sys.path.insert(0, OFFICIAL_REPO)
    with open(path, "rb") as f:
        return pickle.load(f)

split = None
try:
    split = try_load_split(SPLIT_PATH, add_repo_path=False)
    print("  直接 load 成功（无需 sys.path）")
except Exception as e1:
    print(f"  直接 load 失败: {e1}")
    try:
        split = try_load_split(SPLIT_PATH, add_repo_path=True)
        print(f"  加 sys.path({OFFICIAL_REPO}) 后 load 成功")
    except Exception as e2:
        print(f"  加 sys.path 后仍失败: {e2}")
        split = None

if split is not None:
    print(f"  split 类型: {type(split)}")
    # 探明结构 —— DataSplit 对象，有 .images / .labels 属性
    # 结构: {'train': {id: path}, 'val': {id: path}, 'test': {id: path}}
    if hasattr(split, 'images'):
        img_struct = split.images
        print(f"  split.images keys: {list(img_struct.keys())}")
        for k, v in img_struct.items():
            print(f"    [{k}] {len(v)} 个样本")
    else:
        print(f"  split 内容概览: {repr(split)[:300]}")

    # 提取 test IDs —— DataSplit 对象用 .images['test']
    test_ids = None
    if hasattr(split, 'images') and isinstance(split.images, dict):
        if 'test' in split.images:
            test_ids = list(split.images['test'].keys())
            print(f"  找到 test split，样本数={len(test_ids)}")
        else:
            print(f"  未找到 test key，所有 keys: {list(split.images.keys())}")
    elif isinstance(split, dict):
        for k in split.keys():
            if "test" in str(k).lower():
                test_ids = split[k]
                print(f"  找到 test key='{k}'，样本数={len(test_ids)}")
                break
        if test_ids is None:
            print(f"  未找到 test key，所有 keys: {list(split.keys())}")

    if test_ids is not None:
        # 统一转字符串，排序
        test_ids_str = sorted([str(x) for x in test_ids])
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(OUT_IDS, "w", encoding="utf-8") as f:
            f.write(f"# 来源: {SPLIT_PATH}\n")
            f.write(f"# test 数量: {len(test_ids_str)}\n")
            f.write(f"# 生成时间: {now_str}\n")
            f.write(f"# seed: 见 config.dt（data_split.dt 本身不含 seed 字段）\n")
            for sid in test_ids_str:
                f.write(sid + "\n")
        print(f"  -> 写入 {OUT_IDS}，共 {len(test_ids_str)} 个 test 样本")
    else:
        print("  警告: 未能提取 test_ids，请检查 split 结构")
else:
    print("  错误: data_split.dt 无法加载，任务1 失败")

# ─────────────────────────────────────────────────────────────
# 任务2: 解析 tensorboard 事件，提取收敛曲线
# ─────────────────────────────────────────────────────────────
print("\n=== 任务2: 解析 tensorboard 收敛曲线 ===")

# 收集所有 tfevents 文件
tb_files = []
for dirpath, dirnames, filenames in os.walk(TB_DIR):
    for fn in filenames:
        if fn.startswith("events.out.tfevents"):
            tb_files.append(os.path.join(dirpath, fn))

print(f"  找到 {len(tb_files)} 个 tfevents 文件:")
for f in tb_files:
    print(f"    {f}")

rows = []  # (step, tag, value)

if tb_files:
    try:
        from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
        print("  tensorboard EventAccumulator 可用")

        for tb_file in tb_files:
            ea = EventAccumulator(tb_file)
            ea.Reload()
            tags = ea.Tags()
            scalar_tags = tags.get("scalars", [])
            print(f"  文件 {os.path.basename(tb_file)} scalar tags: {scalar_tags}")

            for tag in scalar_tags:
                events = ea.Scalars(tag)
                for e in events:
                    rows.append((e.step, tag, e.value))

        print(f"  共提取 {len(rows)} 个数据点")

    except ImportError as e:
        print(f"  tensorboard 不可用: {e}，尝试 tbparse...")
        try:
            from tbparse import SummaryReader
            reader = SummaryReader(TB_DIR, pivot=False)
            df = reader.scalars
            print(f"  tbparse 成功，共 {len(df)} 行")
            for _, row in df.iterrows():
                rows.append((int(row["step"]), str(row["tag"]), float(row["value"])))
        except Exception as e2:
            print(f"  tbparse 也失败: {e2}")
            rows = None

    except Exception as e:
        print(f"  EventAccumulator 解析失败: {e}")
        rows = None
else:
    print("  未找到 tfevents 文件")
    rows = None

# 写 CSV
if rows and len(rows) > 0:
    rows_sorted = sorted(rows, key=lambda x: (x[1], x[0]))
    with open(OUT_CONV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["step", "tag", "value"])
        writer.writerows(rows_sorted)
    print(f"  -> 写入 {OUT_CONV}，共 {len(rows_sorted)} 个数据点")
else:
    with open(OUT_CONV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["step", "tag", "value"])
        writer.writerow(["N/A", "无 tensorboard 数据", "R1 收敛曲线需重训时启用 logging 才有"])
    print(f"  -> 写入占位说明到 {OUT_CONV}")

print("\n=== 完成 ===")
