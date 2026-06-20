"""
datasets — vessel segmentation dataset registry for gdn2vessel.

All datasets share the BaseVesselDataset interface:
  __getitem__ → {'image': (1,H,W), 'gt': (1,H,W), 'fov': (1,H,W), 'id': ...}
  get_tiles(sid, tile_size=512) → list of tile dicts (for high-res inference)
  get_train_ids() / get_val_ids() / get_test_ids() → deterministic split IDs

Anti-leakage (RED LINE 1): all datasets assert TRAIN/VAL/TEST disjoint at init.
Run verify_no_leakage.py before training as P1 gate.
"""

from datasets.drive  import DRIVEDataset
from datasets.base_vessel import BaseVesselDataset, apply_clahe, pad_to_multiple
from datasets.chase  import CHASEDataset
from datasets.stare  import STAREDataset
from datasets.hrf    import HRFDataset
from datasets.fives  import FIVESDataset

__all__ = [
    'BaseVesselDataset',
    'DRIVEDataset',
    'CHASEDataset',
    'STAREDataset',
    'HRFDataset',
    'FIVESDataset',
    'apply_clahe',
    'pad_to_multiple',
]
