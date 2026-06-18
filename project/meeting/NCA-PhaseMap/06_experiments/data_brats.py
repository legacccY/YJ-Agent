"""P0 BraTS2021 数据适配器 — NCA-PhaseMap Gate1

接口与 HipSliceDataset 完全相同：__getitem__ 返回 (img[1,64,64], lbl[1,64,64])，float32。

数据源：
    test/tumor/  BraTS2021_XXXXX_flair_NN.png   (FLAIR 脑切片)
    test/annotation/ BraTS2021_XXXXX_seg_NN.png (肿瘤分割 mask)
配对规则：从 flair 文件名提取 (case_id, slice_idx)，匹配 annotation/<id>_seg_<idx>.png。

预处理：
    - img: PNG uint16/uint8 → float32 min-max 归一 [0,1]（原始 PNG readme 标 No MinMax=未归一）
    - lbl: mask > 0 → 二值化 float32
    - resize 到 64×64（同 Hippocampus 默认大小）
    - 前景占比 < FG_THRESH=0.02 的切片排除（约 12%，低前景防假性 collapse）

使用：
    ds = BraTSSliceDataset(data_root="...", split='all', fg_thresh=0.02)
    img, lbl = ds[0]   # img: [1,64,64], lbl: [1,64,64]
    print(ds.report())

环境变量：
    BRATS_ROOT   覆盖 --data_root 默认值

入口（独立运行报告切片统计）：
    python data_brats.py [--data_root PATH] [--fg_thresh 0.02] [--show 5]
"""

import os
import re
import sys
import argparse
import numpy as np
import torch
from torch.utils.data import Dataset
from pathlib import Path

# ─── 默认数据根（env 可覆盖） ───────────────────────────────────────
_DEFAULT_BRATS_ROOT = os.environ.get(
    'BRATS_ROOT',
    os.path.join("D:", os.sep, "YJ-Agent", "project", "meeting",
                 "MedAD-FailMap", "data", "BraTS2021", "test")
)

IMG_SIZE = (64, 64)       # 对齐 Hippocampus
FG_THRESH_DEFAULT = 0.02  # 排除前景占比 < 2%

# flair 文件名模式：BraTS2021_XXXXX_flair_NN.png
_FLAIR_RE = re.compile(r'^(BraTS2021_\d+)_flair_(\d+)\.png$')


def _load_png_float(path: str) -> np.ndarray:
    """读 PNG → float32 [H, W]，支持 uint8 / uint16 / L / RGB。"""
    # PIL 对 uint16 用 I 模式，对 uint8 用 L/RGB
    from PIL import Image
    img = Image.open(path)
    # 统一转 numpy
    arr = np.array(img, dtype=np.float32)
    # 若 RGB，取均值灰度（BraTS flair 理论是灰度，以防万一）
    if arr.ndim == 3:
        arr = arr.mean(axis=2)
    return arr  # [H, W]


def _minmax(arr: np.ndarray) -> np.ndarray:
    """min-max 归一到 [0, 1]，全零图返回全零。"""
    mn, mx = arr.min(), arr.max()
    if mx - mn < 1e-9:
        return np.zeros_like(arr)
    return (arr - mn) / (mx - mn)


class BraTSSliceDataset(Dataset):
    """BraTS2021 test/tumor + test/annotation 配对 2D 切片数据集。

    接口与 HipSliceDataset 完全相同：
        __getitem__ → (img: Tensor[1,H,W], lbl: Tensor[1,H,W])

    参数
    ----
    data_root : str
        BraTS2021/test/ 目录路径（含 tumor/ 和 annotation/ 子目录）
    split : str
        'all'（Gate1 全量用于训练扫描）
    fg_thresh : float
        排除前景像素占比 < fg_thresh 的切片（默认 0.02=2%）
    img_size : tuple
        resize 目标 (H, W)，默认 (64, 64)
    """

    def __init__(self,
                 data_root: str = _DEFAULT_BRATS_ROOT,
                 split: str = 'all',
                 fg_thresh: float = FG_THRESH_DEFAULT,
                 img_size: tuple = IMG_SIZE):
        self.data_root  = Path(data_root)
        self.fg_thresh  = fg_thresh
        self.img_size   = img_size

        tumor_dir = self.data_root / "tumor"
        annot_dir = self.data_root / "annotation"

        if not tumor_dir.exists():
            raise FileNotFoundError(f"tumor 目录不存在: {tumor_dir}")
        if not annot_dir.exists():
            raise FileNotFoundError(f"annotation 目录不存在: {annot_dir}")

        # 构建 annotation 索引：(case_id, slice_idx) -> seg_path
        annot_index = {}
        for p in annot_dir.iterdir():
            # BraTS2021_XXXXX_seg_NN.png
            m = re.match(r'^(BraTS2021_\d+)_seg_(\d+)\.png$', p.name)
            if m:
                annot_index[(m.group(1), int(m.group(2)))] = p

        # 扫描 flair 文件，配对 annotation
        total_flair   = 0
        no_mask_count = 0
        low_fg_count  = 0
        self.samples  = []  # list of (flair_path, mask_path)

        for p in sorted(tumor_dir.iterdir()):
            m = _FLAIR_RE.match(p.name)
            if not m:
                continue
            total_flair += 1
            case_id   = m.group(1)
            slice_idx = int(m.group(2))

            key = (case_id, slice_idx)
            if key not in annot_index:
                no_mask_count += 1
                continue

            # 快速检查前景占比（读 mask）
            mask_arr = np.array(__import__('PIL').Image.open(str(annot_index[key])),
                                dtype=np.float32)
            if mask_arr.ndim == 3:
                mask_arr = mask_arr.mean(axis=2)
            fg_ratio = float((mask_arr > 0).mean())

            if fg_ratio < self.fg_thresh:
                low_fg_count += 1
                continue

            self.samples.append((str(p), str(annot_index[key]), fg_ratio))

        self._stats = {
            'total_flair':   total_flair,
            'no_mask':       no_mask_count,
            'low_fg_pruned': low_fg_count,
            'kept':          len(self.samples),
        }

        print(
            f"[BraTSSliceDataset] total_flair={total_flair}  "
            f"no_mask={no_mask_count}  low_fg(<{fg_thresh*100:.0f}%)={low_fg_count}  "
            f"kept={len(self.samples)}",
            flush=True
        )

    # ─── Dataset 接口 ────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        """返回 (img[1,H,W], lbl[1,H,W])，与 HipSliceDataset 完全相同接口。"""
        flair_path, mask_path, _fg = self.samples[idx]
        H, W = self.img_size

        # 读取 + 归一
        img_arr  = _minmax(_load_png_float(flair_path))   # [H0, W0] float32 [0,1]
        mask_arr = (_load_png_float(mask_path) > 0).astype(np.float32)  # binary

        # resize（双线性/最近邻）
        img_arr  = _resize_np(img_arr,  H, W, mode='bilinear')
        mask_arr = _resize_np(mask_arr, H, W, mode='nearest')

        # [1, H, W]
        img  = torch.from_numpy(img_arr[None]).float()
        lbl  = torch.from_numpy(mask_arr[None]).float()

        return img, lbl

    # ─── 报告工具 ────────────────────────────────────────────────────

    def report(self) -> str:
        s = self._stats
        fg_ratios = [r for _, _, r in self.samples]
        med = float(np.median(fg_ratios)) if fg_ratios else float('nan')
        mn  = float(np.min(fg_ratios))    if fg_ratios else float('nan')
        mx  = float(np.max(fg_ratios))    if fg_ratios else float('nan')
        return (
            f"BraTSSliceDataset  total_flair={s['total_flair']}  "
            f"no_mask={s['no_mask']}  "
            f"low_fg(<{self.fg_thresh*100:.0f}%)={s['low_fg_pruned']}  "
            f"kept={s['kept']}\n"
            f"  fg_ratio  median={med:.4f}  min={mn:.4f}  max={mx:.4f}"
        )

    def fg_ratios(self):
        """返回所有保留切片的前景占比列表（用于 B0 统计）。"""
        return [r for _, _, r in self.samples]


# ─── numpy resize（无 scipy） ───────────────────────────────────────

def _resize_np(arr: np.ndarray, H: int, W: int, mode: str = 'bilinear') -> np.ndarray:
    """用 torch interpolate 做 resize，绕过 PIL 对 float 的限制。"""
    t = torch.from_numpy(arr[None, None]).float()  # [1,1,h,w]
    align = (mode == 'bilinear')
    out = torch.nn.functional.interpolate(
        t, size=(H, W),
        mode=mode if mode != 'nearest' else 'nearest',
        align_corners=align if mode == 'bilinear' else None,
    )
    return out[0, 0].numpy()


# ─── CLI（独立运行输出统计） ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="BraTS P0 数据适配器统计报告")
    parser.add_argument('--data_root', default=_DEFAULT_BRATS_ROOT)
    parser.add_argument('--fg_thresh', type=float, default=FG_THRESH_DEFAULT)
    parser.add_argument('--show',      type=int,   default=5,
                        help='打印前 N 个样本形状验证接口')
    args = parser.parse_args()

    ds = BraTSSliceDataset(data_root=args.data_root, fg_thresh=args.fg_thresh)
    print(ds.report())

    if args.show > 0:
        print(f"\n[验证] 前 {min(args.show, len(ds))} 个样本：")
        for i in range(min(args.show, len(ds))):
            img, lbl = ds[i]
            fg = float(lbl.mean())
            print(f"  [{i}] img={tuple(img.shape)} dtype={img.dtype} "
                  f"range=[{img.min():.3f},{img.max():.3f}]  "
                  f"lbl={tuple(lbl.shape)} fg={fg:.4f}")


if __name__ == '__main__':
    main()
