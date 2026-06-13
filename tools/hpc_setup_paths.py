"""HPC 上运行：修复 CSV 路径（Windows → GPFS）+ 验证数据完整性
在 HPC 上执行: python hpc_setup_paths.py
"""
import pandas as pd
from pathlib import Path
import sys

HPC_BASE   = "/gpfs/work/bio/jiayu2403/visienhance"
DATA_DIR   = f"{HPC_BASE}/data"
CSV_IN     = f"{DATA_DIR}/quality_labels_nocrop.csv"
CSV_OUT    = f"{DATA_DIR}/quality_labels_nocrop_hpc.csv"

WIN_DEGRADED = "D:\\YJ-Agent\\data\\paired_dataset_nocrop\\"
WIN_ORIG_1   = "D:\\YJ-Agent\\data\\raw\\isic2020\\train-image\\image\\"
WIN_ORIG_2   = "D:/YJ-Agent/data/raw/isic2020/train-image/image/"
WIN_DEG_2    = "D:/YJ-Agent/data/paired_dataset_nocrop/"

HPC_DEGRADED = f"{DATA_DIR}/paired_dataset_nocrop/"
HPC_ORIG     = f"{DATA_DIR}/isic2020/"

def fix_path(p):
    p = str(p).replace("\\", "/")
    if "paired_dataset_nocrop" in p:
        fname = Path(p).name
        subdir = Path(p).parent.name  # light/medium/heavy
        return f"{HPC_DEGRADED}{subdir}/{fname}"
    elif "isic2020" in p or "raw" in p:
        fname = Path(p).name
        return f"{HPC_ORIG}{fname}"
    return p

print("读取 CSV...")
df = pd.read_csv(CSV_IN)
print(f"  共 {len(df)} 行")

print("修复路径...")
df["degraded_path"] = df["degraded_path"].apply(fix_path)
df["original_path"] = df["original_path"].apply(fix_path)

print("样本路径检查:")
print(f"  degraded: {df['degraded_path'].iloc[0]}")
print(f"  original: {df['original_path'].iloc[0]}")

print("\n验证文件存在性（抽样前 100 行）...")
dcount, ocount = 0, 0
for _, row in df.head(100).iterrows():
    if Path(row["degraded_path"]).exists(): dcount += 1
    if Path(row["original_path"]).exists(): ocount += 1
print(f"  degraded 存在: {dcount}/100")
print(f"  original 存在: {ocount}/100")

if dcount < 90 or ocount < 90:
    print("ERROR: 文件存在率过低，检查解压路径！")
    sys.exit(1)

df.to_csv(CSV_OUT, index=False)
print(f"\n✓ 已写出: {CSV_OUT}")

# 全量验证
print("\n全量验证（可能需要 1-2 分钟）...")
valid = df[
    df["degraded_path"].apply(lambda p: Path(p).exists()) &
    df["original_path"].apply(lambda p: Path(p).exists())
]
print(f"✓ 有效样本: {len(valid)} / {len(df)}")
print("完成！")
