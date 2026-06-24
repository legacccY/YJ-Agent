"""Build FR-UNet 官方 global-stats minmax cache (pickle) for given datasets.

复现零偏离：FR-UNet 官方 data_process.py 用全训练集 global mean/std + per-image minmax，
离线 pickle 存盘。train_harness --frunet_cache_path 读它。不传则 fallback per-image minmax (偏离)。

Usage (HPC):
    python scripts/build_frunet_cache.py --data_root_base <.../data/vessel> \
        --datasets DRIVE CHASE --out_dir <.../data/frunet_cache>
"""
import argparse
import sys
from pathlib import Path

# src/ on path
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from datasets.frunet_pipeline import FRUNetPreprocessor  # noqa: E402
from datasets.drive import DRIVEDataset  # noqa: E402
from datasets.chase import CHASEDataset  # noqa: E402

try:
    from datasets.stare import STAREDataset
except Exception:
    STAREDataset = None
try:
    from datasets.fives import FIVESDataset
except Exception:
    FIVESDataset = None

_DS_MAP = {
    "DRIVE": DRIVEDataset,
    "CHASE": CHASEDataset,
    "STARE": STAREDataset,
    "FIVES": FIVESDataset,
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data_root_base", required=True,
                   help="父目录，下含 DRIVE/ CHASE/ ... 各集")
    p.add_argument("--datasets", nargs="+", default=["DRIVE", "CHASE"])
    p.add_argument("--out_dir", required=True, help="pickle 输出目录")
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for ds_name in args.datasets:
        cls = _DS_MAP.get(ds_name)
        if cls is None:
            print(f"[SKIP] {ds_name}: dataset class 不可用")
            continue
        data_root = Path(args.data_root_base) / ds_name
        if not data_root.exists():
            print(f"[SKIP] {ds_name}: data_root 不存在 {data_root}")
            continue
        print(f"[build] {ds_name} from {data_root}")
        src = cls(str(data_root), split="train", skip_missing=True)
        pre = FRUNetPreprocessor(src, dataset_name=ds_name.lower())
        cache_path = out_dir / f"{ds_name.lower()}.pkl"
        pre.run(cache_path=str(cache_path))
        sz = cache_path.stat().st_size if cache_path.exists() else 0
        print(f"[done] {ds_name} -> {cache_path}  ({sz/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
