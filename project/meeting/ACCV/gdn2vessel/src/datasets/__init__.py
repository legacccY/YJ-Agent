"""
datasets — vessel segmentation dataset registry for gdn2vessel.

All datasets share the BaseVesselDataset interface:
  __getitem__ → {'image': (1,H,W), 'gt': (1,H,W), 'fov': (1,H,W), 'id': ...}
  get_tiles(sid, tile_size=512) → list of tile dicts (for high-res inference)
  get_train_ids() / get_val_ids() / get_test_ids() → deterministic split IDs

Anti-leakage (RED LINE 1): all datasets assert TRAIN/VAL/TEST disjoint at init.
Run verify_no_leakage.py before training as P1 gate.

FR-UNet official pipeline (P1 主实验官方化迁移):
  FRUNetDRIVE / FRUNetCHASE / FRUNetSTARE / FRUNetHRF / FRUNetFIVES
  → frunet_pipeline.py (FR-UNet 官方 normalize + augment + patch 48x48)
  FRUNetPreprocessor → 离线 global mean/std + pickle 缓存 (data_process.py 风格)
  make_frunet_dataset(name, data_root, ...) → 工厂函数
"""

from datasets.drive  import DRIVEDataset
from datasets.base_vessel import BaseVesselDataset, apply_clahe, pad_to_multiple
from datasets.chase  import CHASEDataset
from datasets.stare  import STAREDataset
from datasets.hrf    import HRFDataset
from datasets.fives  import FIVESDataset

# FR-UNet 官方 pipeline (P1 主实验官方化迁移)
from datasets.frunet_pipeline import (
    FRUNetDataset,
    FRUNetDRIVE,
    FRUNetCHASE,
    FRUNetSTARE,
    FRUNetHRF,
    FRUNetFIVES,
    FRUNetPreprocessor,
    make_frunet_dataset,
    frunet_augment,
    frunet_per_image_minmax,
)

__all__ = [
    # Base / classic pipeline
    'BaseVesselDataset',
    'DRIVEDataset',
    'CHASEDataset',
    'STAREDataset',
    'HRFDataset',
    'FIVESDataset',
    'apply_clahe',
    'pad_to_multiple',
    # FR-UNet official pipeline
    'FRUNetDataset',
    'FRUNetDRIVE',
    'FRUNetCHASE',
    'FRUNetSTARE',
    'FRUNetHRF',
    'FRUNetFIVES',
    'FRUNetPreprocessor',
    'make_frunet_dataset',
    'frunet_augment',
    'frunet_per_image_minmax',
]
