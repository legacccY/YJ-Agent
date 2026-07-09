"""量化「M3D-NCA 多尺度下采样抹掉散布小囊肿」机制。

对每个含囊肿 case，把 cyst mask(label==3) 按**官方 rescale3d 同法**(cv2 INTER_NEAREST 逐层，
xy 一遍 + xz 一遍)重采样到 M3D-NCA 两级输入尺寸，统计：
  - 下采样前后 cyst 体素数
  - 存活比例 = after/before
  - 是否完全抹没(after==0)
聚合：各分辨率下 cyst「幸存 case%」+ 存活比例中位。

服务 NCA-Cyst § 01_STORY 支柱3（M3D-NCA 全局视野只来自最低分辨率级，散布小囊肿在下采样级被抹掉）。
诚实：这是**几何重采样**证据(证小囊肿被下采样吞掉)，非训练结果；分割失败还有类不平衡等其他因。
"""
import os, csv
import numpy as np
import nibabel as nib
import cv2

ROOT = r"D:\YJ-Agent\data\kits23_repo\dataset"
DIST = r"D:\YJ-Agent\project\meeting\NCA-Cyst\06_experiments\kits23_cyst_dist.csv"
OUT = r"D:\YJ-Agent\project\meeting\NCA-Cyst\06_experiments\downsample_survival.csv"

# M3D-NCA full config 两级 input_size（见 config_kits23 CONFIG_FULL）
SIZES = {"L1_128x128x64": (128, 128, 64), "L0_64x64x32": (64, 64, 32)}


def rescale3d_nearest(vol, size):
    """复刻官方 Nii_Gz_Dataset_3D.rescale3d 的 label 分支(INTER_NEAREST 两遍)。
    vol: 3D numpy (H,W,D)。size: (H,W,D)。"""
    # 第一遍：逐 z 切片 resize (H,W)
    size_xy = (size[0], size[1])
    tmp = np.zeros((size[0], size[1], vol.shape[2]), dtype=vol.dtype)
    for z in range(vol.shape[2]):
        tmp[:, :, z] = cv2.resize(vol[:, :, z].astype(np.float32), dsize=size_xy,
                                  interpolation=cv2.INTER_NEAREST)
    # 第二遍：逐 y 切片 resize (D 维) —— 官方 size2=(size[2], size[0])
    size2 = (size[2], size[0])
    out = np.zeros((size[0], size[1], size[2]), dtype=vol.dtype)
    for y in range(tmp.shape[1]):
        out[:, y, :] = cv2.resize(tmp[:, y, :].astype(np.float32), dsize=size2,
                                  interpolation=cv2.INTER_NEAREST)
    return out


cyst_cases = [r["case"] for r in csv.DictReader(open(DIST)) if r["has_cyst"] == "1"]
print(f"含囊肿 case: {len(cyst_cases)}", flush=True)

rows = []
for i, case in enumerate(cyst_cases):
    seg = nib.load(os.path.join(ROOT, case, "segmentation.nii.gz")).get_fdata()
    cyst = (np.rint(seg) == 3).astype(np.float32)
    n_before = int(cyst.sum())
    rec = {"case": case, "n_cyst_orig": n_before}
    for name, size in SIZES.items():
        ds = rescale3d_nearest(cyst, size)
        n_after = int((ds >= 0.5).sum())
        rec[f"n_{name}"] = n_after
        rec[f"survive_{name}"] = n_after / n_before if n_before > 0 else 0.0
        rec[f"vanished_{name}"] = int(n_after == 0)
    rows.append(rec)
    if (i + 1) % 40 == 0:
        print(f"[{i+1}/{len(cyst_cases)}]", flush=True)

cols = ["case", "n_cyst_orig"] + [f"{p}_{n}" for n in SIZES for p in ("n", "survive", "vanished")]
with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)

print("=" * 60, flush=True)
print(f"总含囊肿 case: {len(rows)}", flush=True)
for name in SIZES:
    vanished = sum(r[f"vanished_{name}"] for r in rows)
    surv = np.array([r[f"survive_{name}"] for r in rows])
    print(f"[{name}] 囊肿完全抹没 case: {vanished}/{len(rows)} ({100*vanished/len(rows):.1f}%) | "
          f"存活比例 median={np.median(surv):.3f} mean={surv.mean():.3f}", flush=True)
print(f"CSV -> {OUT}", flush=True)
