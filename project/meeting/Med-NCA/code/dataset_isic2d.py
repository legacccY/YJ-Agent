"""ISIC 2018 Task1 2D RGB dataset adapter for the Med-NCA official framework.

Fits into the official Experiment / DataSplit pipeline by implementing the same
interface as Dataset_NiiGz_3D, but for flat jpg/png image pairs.

Key design decisions:
- self.slice = 0  → tells Agent.test() to use the 2D per-image accumulation path
  (the official code checks `if dataset.slice is not None` to pick 2D vs 3D mode;
   we set it to 0 as a sentinel — the value is never used for actual axis slicing)
- Each image is its own "patient" (id = image stem, single "slice" index 0)
  so per-image Dice = per-patient Dice in Agent.test()
- Images are resized to `self.size` (set by Experiment.set_size()).
  GT masks are resized with INTER_NEAREST to keep binary values.
- RGB input is returned as shape (H, W, 3) — float32, normalised [0, 1].
  GT mask  is returned as shape (H, W, 1) — binary {0, 1}.
- Pixel alignment guarantee: cv2.resize uses the same dsize tuple for both
  img and label; img uses INTER_CUBIC, label uses INTER_NEAREST (then threshold
  back to binary) — same spatial grid, no offset.
- Junk files (ATTRIBUTION.txt, macOS ._* files) are filtered at scan time.
"""

import os
import cv2
import numpy as np
from torch.utils.data import Dataset
from src.datasets.Data_Instance import Data_Container


class ISIC2D_RGB_Dataset(Dataset):
    """2D RGB dataset for ISIC 2018 Task1 skin lesion segmentation.

    Compatible with the official Experiment / DataSplit / Agent_Med_NCA pipeline.
    Works as a drop-in replacement for Dataset_NiiGz_3D(slice=2) in 2D mode.
    """

    # Sentinel value: tells Agent.test() to use the 2D per-image path.
    # The actual value (0) is never used for axis indexing in our code.
    slice = 0

    def __init__(self):
        self.size = (64, 64)          # overwritten by Experiment.set_size()
        self.data = Data_Container()  # in-memory cache (same as official datasets)
        self.images_list = []
        self.labels_list = []
        self.images_path = None
        self.labels_path = None
        self.length = 0
        self.state = "train"
        self.exp = None

    # ------------------------------------------------------------------
    # Interface required by DataSplit.getFilesInFolder()
    # ------------------------------------------------------------------

    def getFilesInPath(self, path):
        """Return {stem: {0: (filename, stem, 0)}} for every valid image in path.

        Filters out:
          - ATTRIBUTION.txt
          - macOS resource-fork files (._*)
          - Any file that is not .jpg / .png
        """
        valid_exts = {".jpg", ".jpeg", ".png"}
        try:
            entries = os.listdir(path)
        except FileNotFoundError:
            return {}

        dic = {}
        for fname in sorted(entries):
            # Skip junk
            if fname.startswith("._"):
                continue
            stem, ext = os.path.splitext(fname)
            if ext.lower() not in valid_exts:
                continue
            # Use stem as patient/image id; single "slice" at index 0
            dic[stem] = {0: (fname, stem, 0)}
        return dic

    # ------------------------------------------------------------------
    # Interface required by Experiment.set_size() and Dataset_Base
    # ------------------------------------------------------------------

    def set_size(self, size):
        self.size = tuple(size)

    def set_experiment(self, experiment):
        self.exp = experiment

    def setState(self, state):
        self.state = state

    def setPaths(self, images_path, images_list, labels_path, labels_list):
        self.images_path = images_path
        self.images_list = images_list
        self.labels_path = labels_path
        self.labels_list = labels_list
        self.length = len(self.images_list)
        # Clear cache when paths change (train → test switch)
        self.data = Data_Container()

    def getImagePaths(self):
        return self.images_list

    def __len__(self):
        return self.length

    # ------------------------------------------------------------------
    # Required by Agent.test() id-parsing logic
    # ------------------------------------------------------------------

    def __getname__(self, data_id):
        """Return a string that, when split on '_', gives (_, patient_id, slice).

        Agent.test() does:  _, id, slice = dataset.__getname__(data_id).split('_')
        Our image stems look like: ISIC_0000000
        Split on '_' → ['ISIC', '0000000']  — only 2 parts, not 3.

        Work-around: we encode the stem as  "_<stem>_0"  so the split yields
        ['', stem, '0'], which the agent code unpacks correctly as:
          _ = '',  id = stem,  slice = '0'
        """
        if isinstance(data_id, (list, tuple)):
            data_id = data_id[0]
        return "_" + str(data_id) + "_0"

    # ------------------------------------------------------------------
    # Core __getitem__
    # ------------------------------------------------------------------

    def __getitem__(self, idx):
        """Load, preprocess and return (id_str, img_HWC, label_HWC).

        id_str : "_ISIC_XXXXXXX_0"  (matches __getname__ output)
        img    : float32 (H, W, 3)  RGB normalised to [0, 1]
        label  : float32 (H, W, 1)  binary {0.0, 1.0}
        """
        cache_key = self.images_list[idx]
        cached = self.data.get_data(key=cache_key)
        if cached is not False:
            img_id, img, label = cached
            return (img_id, img, label)

        img_fname, stem, _ = self.images_list[idx]

        # --- Derive GT filename from image stem ---------------------
        # Input:  ISIC_0000000.jpg
        # GT:     ISIC_0000000_segmentation.png
        gt_fname = stem + "_segmentation.png"

        # --- Load image (BGR → RGB) ---------------------------------
        img_bgr = cv2.imread(os.path.join(self.images_path, img_fname))
        if img_bgr is None:
            raise FileNotFoundError(
                f"[ISIC2D] Cannot read image: {os.path.join(self.images_path, img_fname)}"
            )
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

        # --- Load GT mask -------------------------------------------
        gt_raw = cv2.imread(os.path.join(self.labels_path, gt_fname), cv2.IMREAD_GRAYSCALE)
        if gt_raw is None:
            raise FileNotFoundError(
                f"[ISIC2D] Cannot read GT mask: {os.path.join(self.labels_path, gt_fname)}"
            )

        # --- Pixel-aligned resize -----------------------------------
        # Both use the same dsize; img = bicubic, label = nearest-neighbour.
        dsize = (self.size[1], self.size[0])   # cv2 expects (width, height)
        img_resized = cv2.resize(img_rgb, dsize=dsize, interpolation=cv2.INTER_CUBIC)
        gt_resized  = cv2.resize(gt_raw,  dsize=dsize, interpolation=cv2.INTER_NEAREST)

        # --- Normalise image to [0, 1] ------------------------------
        img_f32 = img_resized.astype(np.float32) / 255.0   # shape (H, W, 3)

        # --- Binarise GT mask ---------------------------------------
        gt_bin = (gt_resized > 127).astype(np.float32)      # shape (H, W)
        gt_f32 = gt_bin[..., np.newaxis]                    # shape (H, W, 1)

        # --- Build id string ----------------------------------------
        img_id = "_" + stem + "_0"

        self.data.set_data(key=cache_key, data=(img_id, img_f32, gt_f32))
        return (img_id, img_f32, gt_f32)
