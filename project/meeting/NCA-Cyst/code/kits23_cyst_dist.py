"""扫 KiTS23 所有 case 的 segmentation，统计各 label 体素数 + 囊肿(label==3)分布。
只读原始数据，不改。输出 CSV 到 scratchpad。"""
import os, csv, sys
import numpy as np
import nibabel as nib

ROOT = r"D:\YJ-Agent\data\kits23_repo\dataset"
OUT = r"C:\Users\yj200\AppData\Local\Temp\claude\D--YJ-Agent\3c590116-b5d6-480c-a364-ffbb3784f16b\scratchpad\kits23_cyst_dist.csv"

cases = sorted([d for d in os.listdir(ROOT) if d.startswith("case_")])
rows = []
n_with_cyst = 0
for i, c in enumerate(cases):
    seg_path = os.path.join(ROOT, c, "segmentation.nii.gz")
    if not os.path.exists(seg_path):
        rows.append([c, "MISSING", 0, 0, 0, 0, 0, 0.0])
        continue
    seg = nib.load(seg_path).get_fdata()
    total = seg.size
    n_bg = int((seg == 0).sum())
    n_kidney = int((seg == 1).sum())
    n_tumor = int((seg == 2).sum())
    n_cyst = int((seg == 3).sum())
    other = total - n_bg - n_kidney - n_tumor - n_cyst
    cyst_frac = n_cyst / total
    has_cyst = n_cyst > 0
    if has_cyst:
        n_with_cyst += 1
    rows.append([c, "OK", n_kidney, n_tumor, n_cyst, other, int(has_cyst), cyst_frac])
    if (i + 1) % 50 == 0:
        print(f"[{i+1}/{len(cases)}] scanned, cyst-cases so far={n_with_cyst}", flush=True)

with open(OUT, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["case", "status", "n_kidney", "n_tumor", "n_cyst", "n_other", "has_cyst", "cyst_frac"])
    w.writerows(rows)

# 汇总
cyst_fracs = [r[7] for r in rows if r[6] == 1 and r[1] == "OK"]
print("=" * 50)
print(f"total cases scanned: {len(cases)}")
print(f"cases WITH cyst (label==3): {n_with_cyst}")
print(f"cases WITHOUT cyst: {len(cases) - n_with_cyst}")
if cyst_fracs:
    arr = np.array(cyst_fracs)
    print(f"cyst voxel fraction among cyst-cases: min={arr.min():.2e} median={np.median(arr):.2e} max={arr.max():.2e} mean={arr.mean():.2e}")
print(f"CSV -> {OUT}")
