"""
SPR Probe — Surgical Phase Recognition, Delta Crux 2 (PREREG 2026-06-22)
=========================================================================
Independent direction: delta-statetrack-probe / delta-statetrack-spr
Does negative-eigenvalue GDN-1 reduce temporal ordering violations
(PTVR) on real surgical video features, beyond what diagonal TC0 models
can achieve?

Dataset: Cholec80 (80 laparoscopic cholecystectomy videos)
  Features: LoViT frozen ViT-B/16 features, pkl per video
    path: <data_root>/features/video{NN:02d}.pkl
    shape: [768, T, 1, 1] (768=ViT-B/16 dim, T=1fps frames)
    load: feat.squeeze(-1).squeeze(-1).permute(1,0)  -> [T, 768]
  Labels: 25fps phase annotations, tab-separated
    path: <data_root>/phase_annotations/video{NN:02d}-phase.txt
    format: Frame<TAB>Phase (Phase = string, 7 classes)
    downsampled to 1fps: every 25th frame
  Split: video01-40 train, video41-80 test (social-standard, hard-coded)
  Phase map (7 classes):
    Preparation:0, CalotTriangleDissection:1, ClippingCutting:2,
    GallbladderDissection:3, GallbladderPackaging:4,
    CleaningCoagulation:5, GallbladderRetraction:6

5 arms (iso-param, d=256, 2 layers, causal / online):
  gdn1_neg      = GatedDeltaNet(allow_neg_eigval=True)   -- PRIMARY
  deltaproduct  = GatedDeltaProduct(num_householder=2, allow_neg_eigval=True)
  gla           = GatedLinearAttention                    -- TC0 control
  sliding_window= causal sliding-window attention W=--window (pure PyTorch)
  gdn1          = GatedDeltaNet(allow_neg_eigval=False)   -- ablation

All arms: use_short_conv=False, causal / online mode only.

Metrics:
  Global: Acc, Jaccard (macro), Precision (macro), Recall (macro)
  Strict + Relaxed (+-10 frames window, aligns LoViT eval protocol)
  PTVR: phase transition violation rate (vs. GT transition graph from TRAIN set only)
  Residual-PTVR: PTVR residual after regressing on Jaccard
  Long-range-violation (gap >= --lr_gap frames, default 30)
  Boundary-acc@10
  Segmental F1 @ {10, 25, 50} overlap thresholds

Verdict (skeptic-corrected, p+CI dual gate):
  P1: gdn1_neg PTVR significantly lower than BOTH {gla, sliding_window, gdn1}
      Wilcoxon p<0.05 (per-video, pure numpy) AND relative drop >= calibration margin
      AND bootstrap 95% CI lower bound > margin
  P2: gdn1_neg Jaccard (relaxed) >= max(TC arms) - 1pp
  P3: gdn1_neg PTVR significantly lower than gdn1 (neg-eigval ablation)
  P4: deltaproduct PTVR <= gdn1_neg (sanity: not underfitting)
  FAIL = P1 OR P2 OR P3 fails -> direction dead, negative result archived
  FAIL on P4 alone = result uninterpretable, investigate underfitting

Calibration modes:
  --calibrate: TC0 (gla + sw) sweep x multi-seed x capacity; produces
    (1) PTVR-vs-Jaccard scatter + R^2 (R^2>0.5 -> PTVR polluted, alert)
    (2) TC0-vs-TC0 bootstrap null distribution of PTVR delta -> 95th pct = margin
    (3) noise floor (absolute drop lower bound)
  --w_scan W1 W2 ...: sweep sliding-window widths to find Markov saturation point

NO scipy.stats (OMP red-line Windows). All statistics pure numpy.
NO pin_memory=True (Windows spawn worker restriction).
DataLoader multiprocessing_context='spawn' (Windows requirement).
bf16 autocast enabled on CUDA for FLA kernels (chunk_delta_rule forbids fp32).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import pickle
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

# ---------------------------------------------------------------------------
# Directory setup
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_PROBE_DIR = _HERE.parent  # project/meeting/delta-statetrack-probe/

# ---------------------------------------------------------------------------
# Phase map (7 classes, Cholec80 standard)
# ---------------------------------------------------------------------------
PHASE_MAP: Dict[str, int] = {
    'Preparation':              0,
    'CalotTriangleDissection':  1,
    'ClippingCutting':          2,
    'GallbladderDissection':    3,
    'GallbladderPackaging':     4,
    'CleaningCoagulation':      5,
    'GallbladderRetraction':    6,
}
NUM_PHASES = 7
PHASE_NAMES = [k for k, _ in sorted(PHASE_MAP.items(), key=lambda x: x[1])]

# ---------------------------------------------------------------------------
# Train / test split (Cholec80 social standard, hard-coded)
# ---------------------------------------------------------------------------
TRAIN_IDS = list(range(1, 41))   # video01 .. video40
TEST_IDS  = list(range(41, 81))  # video41 .. video80

# ---------------------------------------------------------------------------
# FLA availability guard
# ---------------------------------------------------------------------------
try:
    import fla  # noqa: F401
    _FLA_AVAILABLE = True
except ImportError:
    _FLA_AVAILABLE = False
    print(
        "[spr_probe] fla not found — FLA adapters will raise ImportError at construction. "
        "Full sweep runs on HPC (fla + CUDA).",
        file=sys.stderr,
    )

# ---------------------------------------------------------------------------
# FLA layer imports (guarded)
# ---------------------------------------------------------------------------
_FLAGatedLinearAttention = None
_FLAGatedDeltaNet        = None
_FLAGatedDeltaProduct    = None

if _FLA_AVAILABLE:
    from fla.layers import GatedLinearAttention as _FLAGatedLinearAttention   # noqa: E402
    from fla.layers import GatedDeltaNet        as _FLAGatedDeltaNet           # noqa: E402
    from fla.layers import GatedDeltaProduct    as _FLAGatedDeltaProduct       # noqa: E402


# ===========================================================================
# FLA adapter base
# ===========================================================================

class _FLAAdapterBase(nn.Module):
    """
    Thin wrapper for FLA layers.
    FLA forward: (B,T,H) -> (o: (B,T,H), None, past_kv) -- no internal residual.
    Backbone applies: x = x + LN(mixer(x)) -- handled in SPRBackbone.
    """
    has_internal_residual: bool = False

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        o, _, _ = self.layer(x)
        return o


# ===========================================================================
# Arm: GLA (TC0 diagonal control)
# ===========================================================================

class GLAAdapter(_FLAAdapterBase):
    """
    GatedLinearAttention: diagonal SSM, no delta.
    Capacity: expand_k=1.0, expand_v=1.0, num_heads=num_heads
    use_short_conv=False.
    """

    def __init__(self, hidden_size: int, num_heads: int):
        super().__init__()
        if not _FLA_AVAILABLE:
            raise ImportError("GLAAdapter requires fla with CUDA.")
        # NOTE: expand_k default=0.5 in FLA halves capacity -- must set 1.0
        self.layer = _FLAGatedLinearAttention(
            mode='chunk',
            hidden_size=hidden_size,
            expand_k=1.0,
            expand_v=1.0,
            num_heads=num_heads,
            use_short_conv=False,
            use_output_gate=True,
        )


# ===========================================================================
# Arm: GDN-1 neg eigval (primary)
# ===========================================================================

class GDN1NegAdapter(_FLAAdapterBase):
    """
    GatedDeltaNet(allow_neg_eigval=True) -- primary experimental arm.
    Hypothesis: neg eigenvalues enable state-tracking -> lower PTVR.
    use_short_conv=False to isolate recurrence mechanism.
    """

    def __init__(self, hidden_size: int, num_heads: int, head_dim: int):
        super().__init__()
        if not _FLA_AVAILABLE:
            raise ImportError("GDN1NegAdapter requires fla with CUDA.")
        self.layer = _FLAGatedDeltaNet(
            hidden_size=hidden_size,
            num_heads=num_heads,
            head_dim=head_dim,
            expand_v=1.0,
            use_short_conv=False,
            use_gate=True,
            allow_neg_eigval=True,
            mode='chunk',
        )


# ===========================================================================
# Arm: GDN-1 default (ablation: neg eigval off)
# ===========================================================================

class GDN1Adapter(_FLAAdapterBase):
    """
    GatedDeltaNet(allow_neg_eigval=False) -- ablation control.
    If gdn1_neg beats gdn1 on PTVR, neg eigenvalues are responsible.
    """

    def __init__(self, hidden_size: int, num_heads: int, head_dim: int):
        super().__init__()
        if not _FLA_AVAILABLE:
            raise ImportError("GDN1Adapter requires fla with CUDA.")
        self.layer = _FLAGatedDeltaNet(
            hidden_size=hidden_size,
            num_heads=num_heads,
            head_dim=head_dim,
            expand_v=1.0,
            use_short_conv=False,
            use_gate=True,
            allow_neg_eigval=False,
            mode='chunk',
        )


# ===========================================================================
# Arm: GatedDeltaProduct (sanity check: should be >= gdn1_neg)
# ===========================================================================

class DeltaProductAdapter(_FLAAdapterBase):
    """
    GatedDeltaProduct(num_householder=2, allow_neg_eigval=True).
    P4 sanity: deltaproduct PTVR <= gdn1_neg (more expressive update -> >= capability).
    """

    def __init__(self, hidden_size: int, num_heads: int, head_dim: int):
        super().__init__()
        if not _FLA_AVAILABLE:
            raise ImportError("DeltaProductAdapter requires fla with CUDA.")
        self.layer = _FLAGatedDeltaProduct(
            hidden_size=hidden_size,
            num_heads=num_heads,
            head_dim=head_dim,
            expand_v=1.0,
            use_short_conv=False,
            use_output_gate=True,
            allow_neg_eigval=True,
            num_householder=2,
            mode='chunk',
        )


# ===========================================================================
# Arm: Causal Sliding-Window Attention (pure PyTorch, TC0 upper-bound control)
# ===========================================================================

class SlidingWindowAttention(nn.Module):
    """
    Causal sliding-window attention with window W.
    Each position attends only to the W most recent positions (including itself).
    Pure PyTorch -- no FLA dependency.
    capacity = num_heads * head_dim^2 (same as GDN arms via parameter count parity).

    iso-param strategy: same Q/K/V projection dim as GDN arms, so numel is equal.
    """
    has_internal_residual: bool = False

    def __init__(self, hidden_size: int, num_heads: int, head_dim: int, window: int):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_heads   = num_heads
        self.head_dim    = head_dim
        self.window      = window
        inner_dim = num_heads * head_dim

        self.q_proj = nn.Linear(hidden_size, inner_dim, bias=False)
        self.k_proj = nn.Linear(hidden_size, inner_dim, bias=False)
        self.v_proj = nn.Linear(hidden_size, inner_dim, bias=False)
        self.o_proj = nn.Linear(inner_dim, hidden_size, bias=False)
        self.norm   = nn.LayerNorm(hidden_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B, T, H) -> (B, T, H). Causal sliding window, width W."""
        B, T, H = x.shape
        nh, hd  = self.num_heads, self.head_dim
        W = self.window

        q = self.q_proj(x).view(B, T, nh, hd).transpose(1, 2)  # (B,nh,T,hd)
        k = self.k_proj(x).view(B, T, nh, hd).transpose(1, 2)
        v = self.v_proj(x).view(B, T, nh, hd).transpose(1, 2)

        # Build (T,T) causal sliding-window mask: position i attends to [i-W+1, i]
        # 1 = attend, 0 = mask
        idx = torch.arange(T, device=x.device)
        # dist[i,j] = i - j (>= 0 means causal)
        dist = idx.unsqueeze(1) - idx.unsqueeze(0)  # (T,T)
        # causal AND within window: 0 <= dist <= W-1
        attend = (dist >= 0) & (dist < W)           # (T,T) bool
        mask_val = torch.zeros(T, T, device=x.device, dtype=q.dtype)
        mask_val = mask_val.masked_fill(~attend, float('-inf'))  # (T,T)

        scale = 1.0 / math.sqrt(hd)
        attn_logits = torch.matmul(q, k.transpose(-2, -1)) * scale  # (B,nh,T,T)
        attn_logits = attn_logits + mask_val.unsqueeze(0).unsqueeze(0)
        attn_weights = torch.softmax(attn_logits, dim=-1)  # (B,nh,T,T)
        # NaN guard: rows with all -inf (impossible here since diagonal always attended)
        # but keep for safety
        attn_weights = torch.nan_to_num(attn_weights, nan=0.0)

        out = torch.matmul(attn_weights, v)                     # (B,nh,T,hd)
        out = out.transpose(1, 2).contiguous().view(B, T, nh * hd)  # (B,T,inner)
        return self.o_proj(self.norm(out))


# ===========================================================================
# FFN block
# ===========================================================================

class FFN(nn.Module):
    """Two-layer FFN: Linear(d->4d) + GELU + Linear(4d->d). No bias."""

    def __init__(self, d_model: int, expand: int = 4):
        super().__init__()
        self.fc1 = nn.Linear(d_model, d_model * expand, bias=False)
        self.fc2 = nn.Linear(d_model * expand, d_model, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.fc2(F.gelu(self.fc1(x)))


# ===========================================================================
# 2-layer temporal backbone (pre-norm residual, causal)
# ===========================================================================

class SPRBackbone(nn.Module):
    """
    N-layer backbone (default 2):
      each layer: x = x + mixer(LN(x))
                  x = x + FFN(LN(x))
    Causal by design: FLA layers use chunk mode (causal), SlidingWindow is causal.
    """

    def __init__(
        self,
        d_model: int,
        mixers: List[nn.Module],
        n_layers: int = 2,
        ffn_expand: int = 4,
    ):
        super().__init__()
        assert len(mixers) == n_layers
        self.n_layers     = n_layers
        self.mixer_norms  = nn.ModuleList([nn.LayerNorm(d_model) for _ in range(n_layers)])
        self.ffn_norms    = nn.ModuleList([nn.LayerNorm(d_model) for _ in range(n_layers)])
        self.mixers       = nn.ModuleList(mixers)
        self.ffns         = nn.ModuleList([FFN(d_model, expand=ffn_expand) for _ in range(n_layers)])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (1, T, d_model) -> (1, T, d_model). Single video, full-sequence causal."""
        for i in range(self.n_layers):
            x = x + self.mixers[i](self.mixer_norms[i](x))
            x = x + self.ffns[i](self.ffn_norms[i](x))
        return x


# ===========================================================================
# Full SPR model: proj -> backbone -> classifier head
# ===========================================================================

class SPRModel(nn.Module):
    """
    Linear input projection (768 -> d_model) -> SPRBackbone -> Linear(d_model -> 7).
    Input features are frozen LoViT ViT-B/16, 768-dim.
    No weight tying (regression head not embedding-tied).
    """
    FEAT_DIM: int = 768

    def __init__(self, d_model: int, backbone: SPRBackbone):
        super().__init__()
        self.input_proj = nn.Linear(self.FEAT_DIM, d_model, bias=True)
        self.backbone   = backbone
        self.head       = nn.Linear(d_model, NUM_PHASES, bias=True)

    def forward(self, feats: torch.Tensor) -> torch.Tensor:
        """feats: (1, T, 768) -> logits: (1, T, NUM_PHASES)"""
        x = self.input_proj(feats)   # (1, T, d_model)
        x = self.backbone(x)          # (1, T, d_model)
        return self.head(x)            # (1, T, NUM_PHASES)


# ===========================================================================
# Dataset: LoViT Cholec80 per-video
# ===========================================================================

class CholecVideoDataset(Dataset):
    """
    One video per item.
    Loads .pkl feature file + phase annotation txt.
    Returns: (feats [T, 768], labels [T]) where T = num 1fps frames.
    Robust label loader: auto-detects header + tab/space delimiter.
    """

    def __init__(self, data_root: Path, video_ids: List[int]):
        self.data_root = Path(data_root)
        self.video_ids = video_ids
        self._validate_root()

    def _validate_root(self) -> None:
        feat_dir  = self.data_root / 'features'
        label_dir = self.data_root / 'phase_annotations'
        if not feat_dir.exists():
            raise FileNotFoundError(
                f"[CholecVideoDataset] Feature dir not found: {feat_dir}\n"
                f"  Expected layout: <data_root>/features/video01.pkl ...\n"
                f"  Set --data_root to the correct root."
            )
        if not label_dir.exists():
            raise FileNotFoundError(
                f"[CholecVideoDataset] Label dir not found: {label_dir}\n"
                f"  Expected layout: <data_root>/phase_annotations/video01-phase.txt ..."
            )

    def __len__(self) -> int:
        return len(self.video_ids)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        vid = self.video_ids[idx]
        return self._load_video(vid)

    def _load_feat(self, vid: int) -> torch.Tensor:
        """Load pkl -> [T, 768] float32."""
        pkl_path = self.data_root / 'features' / f'video{vid:02d}.pkl'
        if not pkl_path.exists():
            raise FileNotFoundError(
                f"[CholecVideoDataset] Feature file not found: {pkl_path}\n"
                f"  Check --data_root and that features are downloaded."
            )
        with open(pkl_path, 'rb') as f:
            raw = pickle.load(f)
        # raw may be a tensor or ndarray; shape should be [768, T, 1, 1]
        if isinstance(raw, torch.Tensor):
            feat = raw.float()
        elif isinstance(raw, np.ndarray):
            feat = torch.from_numpy(raw).float()
        else:
            raise TypeError(
                f"[CholecVideoDataset] Unexpected type in {pkl_path}: {type(raw)}\n"
                f"  Expected torch.Tensor or np.ndarray."
            )
        # Shape: [768, T, 1, 1] -> [T, 768]
        if feat.ndim == 4:
            # [768, T, 1, 1]
            feat = feat.squeeze(-1).squeeze(-1).permute(1, 0)  # [T, 768]
        elif feat.ndim == 2:
            # [T, 768] already (some LoViT exports)
            if feat.shape[1] != 768:
                # might be [768, T]
                if feat.shape[0] == 768:
                    feat = feat.permute(1, 0)
                else:
                    raise ValueError(
                        f"[CholecVideoDataset] Unexpected 2D feature shape in {pkl_path}: {feat.shape}\n"
                        f"  Expected [768, T] or [T, 768]."
                    )
        else:
            raise ValueError(
                f"[CholecVideoDataset] Unexpected feature tensor ndim={feat.ndim} "
                f"shape={tuple(feat.shape)} in {pkl_path}.\n"
                f"  Expected [768, T, 1, 1] or [T, 768]."
            )
        if feat.shape[1] != 768:
            raise ValueError(
                f"[CholecVideoDataset] Feature dim mismatch: shape={tuple(feat.shape)}, expected dim=768."
            )
        return feat  # [T, 768]

    def _load_label(self, vid: int, n_frames: int) -> torch.Tensor:
        """
        Load phase annotation txt -> [T] int64 (1fps downsampled).
        Original 25fps: every 25th frame (0, 25, 50, ...) -> T frames.
        Robust: auto-detects header (Frame/Phase column names) + tab/space delimiter.
        Raises clear errors on format mismatch or unknown phase names.
        """
        txt_path = self.data_root / 'phase_annotations' / f'video{vid:02d}-phase.txt'
        if not txt_path.exists():
            raise FileNotFoundError(
                f"[CholecVideoDataset] Label file not found: {txt_path}\n"
                f"  Check --data_root and that phase_annotations are available."
            )

        raw_lines: List[str] = []
        with open(txt_path, 'r', encoding='utf-8', errors='replace') as f:
            raw_lines = [line.rstrip('\n\r') for line in f.readlines()]

        if not raw_lines:
            raise ValueError(
                f"[CholecVideoDataset] Label file is empty: {txt_path}"
            )

        # Auto-detect delimiter (tab preferred, fallback to whitespace)
        # and whether first line is a header
        def _split_line(line: str) -> List[str]:
            if '\t' in line:
                return line.split('\t')
            return line.split()

        # Peek at first line: if it contains non-numeric chars in col 0 it's a header
        first_parts = _split_line(raw_lines[0])
        has_header = False
        if len(first_parts) >= 2:
            try:
                int(first_parts[0])
            except ValueError:
                # First column is not an integer -> header row
                has_header = True

        start_idx = 1 if has_header else 0
        data_lines = raw_lines[start_idx:]

        if len(data_lines) == 0:
            raise ValueError(
                f"[CholecVideoDataset] Label file has no data rows after header: {txt_path}"
            )

        # Parse all rows: (frame_idx, phase_str)
        rows: List[Tuple[int, str]] = []
        unknown_phases: List[str] = []
        parse_errors: List[int] = []
        for lineno, line in enumerate(data_lines, start=start_idx + 1):
            if not line.strip():
                continue
            parts = _split_line(line)
            if len(parts) < 2:
                parse_errors.append(lineno)
                continue
            try:
                frame_idx = int(parts[0])
            except ValueError:
                parse_errors.append(lineno)
                continue
            phase_str = parts[1].strip()
            if phase_str not in PHASE_MAP:
                if phase_str not in unknown_phases:
                    unknown_phases.append(phase_str)
            rows.append((frame_idx, phase_str))

        if parse_errors:
            raise ValueError(
                f"[CholecVideoDataset] Parse errors on {len(parse_errors)} lines in {txt_path}.\n"
                f"  First bad line number(s): {parse_errors[:5]}\n"
                f"  Expected format: <frame_idx><TAB><PhaseName>"
            )
        if unknown_phases:
            raise ValueError(
                f"[CholecVideoDataset] Unknown phase names in {txt_path}: {unknown_phases}\n"
                f"  Valid phases: {list(PHASE_MAP.keys())}"
            )
        if len(rows) == 0:
            raise ValueError(
                f"[CholecVideoDataset] No valid rows parsed from {txt_path}"
            )

        # Build frame_idx -> phase_id dense array
        # Original 25fps frames. We downsample: take frames 0, 25, 50, ...
        # The txt typically has one row per 25fps frame (frame 0, 1, 2, ...).
        # We select every 25th row.
        frame_indices = np.array([r[0] for r in rows], dtype=np.int64)
        phase_strs    = [r[1] for r in rows]

        # Downsample: keep only rows where frame_idx % 25 == 0
        mask_25 = (frame_indices % 25 == 0)
        down_frames = frame_indices[mask_25]
        down_phases = np.array([phase_strs[i] for i in np.where(mask_25)[0]])

        if len(down_phases) == 0:
            # Fallback: maybe already 1fps (no multiples of 25 issue)
            # -> use all rows as-is
            down_phases = np.array(phase_strs)
            print(
                f"[CholecVideoDataset] WARNING: video{vid:02d} label file has no frames "
                f"divisible by 25. Treating as already 1fps.",
                file=sys.stderr,
            )

        # Convert to int labels
        label_seq = np.array([PHASE_MAP[p] for p in down_phases], dtype=np.int64)

        T_label = len(label_seq)
        T_feat  = n_frames

        if T_label != T_feat:
            # Allow small mismatch (off-by-one rounding): truncate/pad to T_feat
            diff = abs(T_label - T_feat)
            if diff > 5:
                print(
                    f"[CholecVideoDataset] WARNING: video{vid:02d} "
                    f"T_label={T_label} != T_feat={T_feat} (diff={diff}). "
                    f"Truncating/padding label to T_feat.",
                    file=sys.stderr,
                )
            if T_label > T_feat:
                label_seq = label_seq[:T_feat]
            else:
                # Pad with last label
                pad = np.full(T_feat - T_label, label_seq[-1], dtype=np.int64)
                label_seq = np.concatenate([label_seq, pad])

        return torch.from_numpy(label_seq)  # [T] int64

    def _load_video(self, vid: int) -> Tuple[torch.Tensor, torch.Tensor]:
        feat   = self._load_feat(vid)           # [T, 768]
        labels = self._load_label(vid, len(feat))  # [T]
        return feat, labels


# ===========================================================================
# Transition graph builder (from TRAIN set GT only — no test leak)
# ===========================================================================

def build_transition_graph(
    dataset: CholecVideoDataset,
    video_ids: List[int],
) -> np.ndarray:
    """
    Build allowed_transitions[i, j] = 1 if transition i->j (or stay i->i)
    observed in training set GT labels.
    Returns: (NUM_PHASES, NUM_PHASES) bool array.
    Only uses labels from video_ids (must be TRAIN_IDS, never TEST_IDS).
    """
    allowed = np.zeros((NUM_PHASES, NUM_PHASES), dtype=bool)
    for idx, vid in enumerate(video_ids):
        _, labels = dataset._load_video(vid)
        lab = labels.numpy()
        # Self-loops always allowed
        for ph in range(NUM_PHASES):
            allowed[ph, ph] = True
        for t in range(1, len(lab)):
            src = int(lab[t - 1])
            dst = int(lab[t])
            allowed[src, dst] = True
    return allowed


# ===========================================================================
# Metrics (all pure numpy, no scipy)
# ===========================================================================

def _confusion_matrix(pred: np.ndarray, gt: np.ndarray, n_classes: int) -> np.ndarray:
    """Compute (n_classes, n_classes) confusion matrix. C[i,j] = #(gt=i, pred=j)."""
    cm = np.zeros((n_classes, n_classes), dtype=np.int64)
    for i in range(n_classes):
        gt_i = gt == i
        for j in range(n_classes):
            cm[i, j] = int(np.sum(gt_i & (pred == j)))
    return cm


def compute_global_metrics(
    pred: np.ndarray,
    gt: np.ndarray,
    relaxed_window: int = 10,
) -> Dict:
    """
    Compute strict + relaxed global classification metrics.
    pred, gt: 1D int arrays of length T.
    relaxed_window: +-W frames around phase transitions; within window -> count as correct.

    Returns dict with keys:
      strict_{acc,jaccard,precision,recall}
      relaxed_{acc,jaccard,precision,recall}
    """
    T = len(gt)
    assert len(pred) == T

    # ---- Relaxed mask: find phase transition frames in GT, mark +-W window ----
    transition_mask = np.zeros(T, dtype=bool)
    for t in range(1, T):
        if gt[t] != gt[t - 1]:
            lo = max(0, t - relaxed_window)
            hi = min(T - 1, t + relaxed_window)
            transition_mask[lo:hi + 1] = True

    def _metrics(p: np.ndarray, g: np.ndarray) -> Dict:
        cm = _confusion_matrix(p, g, NUM_PHASES)
        # Per-class TP, FP, FN
        tp = np.diag(cm).astype(float)
        fp = cm.sum(axis=0) - tp
        fn = cm.sum(axis=1) - tp
        total = float(np.sum(cm))
        acc = float(np.sum(tp)) / max(total, 1.0)
        # Jaccard (IoU) per class: TP / (TP + FP + FN), macro average
        jacc_per = tp / np.maximum(tp + fp + fn, 1.0)
        jaccard  = float(np.mean(jacc_per))
        # Precision per class: TP / (TP + FP)
        prec_per = tp / np.maximum(tp + fp, 1.0)
        precision = float(np.mean(prec_per))
        # Recall per class: TP / (TP + FN)
        rec_per  = tp / np.maximum(tp + fn, 1.0)
        recall   = float(np.mean(rec_per))
        return {
            'acc': acc, 'jaccard': jaccard,
            'precision': precision, 'recall': recall,
        }

    strict_m = _metrics(pred, gt)

    # Relaxed: in transition window, if pred matches GT, count as correct;
    # otherwise use strict pred (this matches the "don't penalize boundary" protocol)
    # The standard relaxed eval: at positions within the window, assign the correct label
    # to whichever segment the model predicts -- i.e., exclude transition frames from penalty.
    # Implementation: create a relaxed_gt that equals pred within transition windows,
    # so those frames are never penalized regardless of what model predicts.
    relaxed_gt = gt.copy()
    relaxed_gt[transition_mask] = pred[transition_mask]
    relaxed_m = _metrics(pred, relaxed_gt)

    return {
        'strict_acc':       strict_m['acc'],
        'strict_jaccard':   strict_m['jaccard'],
        'strict_precision': strict_m['precision'],
        'strict_recall':    strict_m['recall'],
        'relaxed_acc':      relaxed_m['acc'],
        'relaxed_jaccard':  relaxed_m['jaccard'],
        'relaxed_precision':relaxed_m['precision'],
        'relaxed_recall':   relaxed_m['recall'],
    }


def compute_ptvr(
    pred: np.ndarray,
    allowed_transitions: np.ndarray,
) -> float:
    """
    Phase Transition Violation Rate.
    PTVR = # of consecutive prediction pairs (pred[t-1], pred[t]) that are NOT in
           allowed_transitions / (T - 1).
    allowed_transitions: (NUM_PHASES, NUM_PHASES) bool, built from TRAIN GT only.
    """
    T = len(pred)
    if T < 2:
        return 0.0
    violations = 0
    for t in range(1, T):
        src = int(pred[t - 1])
        dst = int(pred[t])
        if not allowed_transitions[src, dst]:
            violations += 1
    return violations / (T - 1)


def compute_long_range_violation(
    pred: np.ndarray,
    allowed_transitions: np.ndarray,
    gap: int = 30,
) -> float:
    """
    Long-range violation rate: same as PTVR but only counting pairs (t-1, t)
    where the transition involves a phase change AND the distance between the
    two segments involved is >= gap frames (measured as run-length gap).

    Implementation: for each predicted frame t where pred[t] != pred[t-1],
    check if the distance from the START of the new segment to the END of the
    previous segment satisfies gap condition.
    Simpler proxy: count (pred[t-1], pred[t]) transitions where pred[t] != pred[t-1],
    they are NOT in allowed_transitions, AND the model has been predicting pred[t-1]
    for at least `gap` consecutive frames (i.e., run length >= gap).
    """
    T = len(pred)
    if T < 2:
        return 0.0

    # Compute run-length encoding: at each position, how long has current phase been predicted
    run_len = np.ones(T, dtype=np.int64)
    for t in range(1, T):
        if pred[t] == pred[t - 1]:
            run_len[t] = run_len[t - 1] + 1
        else:
            run_len[t] = 1

    long_violations = 0
    long_total = 0
    for t in range(1, T):
        src = int(pred[t - 1])
        dst = int(pred[t])
        if src != dst:
            # This is a cross-phase jump; check if previous run was >= gap
            if run_len[t - 1] >= gap:
                long_total += 1
                if not allowed_transitions[src, dst]:
                    long_violations += 1

    if long_total == 0:
        return 0.0
    return long_violations / long_total


def compute_boundary_acc(
    pred: np.ndarray,
    gt: np.ndarray,
    window: int = 10,
) -> float:
    """
    Boundary accuracy at +-window frames.
    For each GT transition boundary, check if model prediction within +-window
    frames contains a matching transition (i.e., a frame-level change).
    Returns: fraction of GT boundaries detected.
    """
    T = len(gt)
    if T < 2:
        return 1.0

    gt_boundaries = [t for t in range(1, T) if gt[t] != gt[t - 1]]
    if not gt_boundaries:
        return 1.0

    detected = 0
    pred_transitions = set(t for t in range(1, T) if pred[t] != pred[t - 1])

    for b in gt_boundaries:
        lo = max(1, b - window)
        hi = min(T - 1, b + window)
        window_range = set(range(lo, hi + 1))
        if window_range & pred_transitions:
            detected += 1

    return detected / len(gt_boundaries)


def compute_segmental_f1(
    pred: np.ndarray,
    gt: np.ndarray,
    overlap_thresholds: Tuple[float, ...] = (0.10, 0.25, 0.50),
) -> Dict[str, float]:
    """
    Segmental F1 @ overlap thresholds {0.10, 0.25, 0.50} (MS-TCNN standard).
    A predicted segment is a TP if:
      1. It overlaps a GT segment of the same class.
      2. The intersection-over-union (IoU) of that pair exceeds the threshold.
    Each GT segment can be matched at most once (greedy, best overlap).
    F1 = 2*P*R / (P+R).
    """
    def _get_segments(arr: np.ndarray) -> List[Tuple[int, int, int]]:
        """Returns list of (class, start, end_exclusive)."""
        segs = []
        if len(arr) == 0:
            return segs
        start = 0
        cur   = arr[0]
        for t in range(1, len(arr)):
            if arr[t] != cur:
                segs.append((int(cur), start, t))
                start = t
                cur   = arr[t]
        segs.append((int(cur), start, len(arr)))
        return segs

    pred_segs = _get_segments(pred)
    gt_segs   = _get_segments(gt)

    results: Dict[str, float] = {}
    for thr in overlap_thresholds:
        tp = 0
        fp = 0
        fn = 0
        gt_matched = [False] * len(gt_segs)

        for (p_cls, p_s, p_e) in pred_segs:
            best_iou  = 0.0
            best_gt_i = -1
            for gi, (g_cls, g_s, g_e) in enumerate(gt_segs):
                if g_cls != p_cls:
                    continue
                inter = max(0, min(p_e, g_e) - max(p_s, g_s))
                union = (p_e - p_s) + (g_e - g_s) - inter
                iou   = inter / max(union, 1)
                if iou > best_iou:
                    best_iou  = iou
                    best_gt_i = gi
            if best_iou >= thr and best_gt_i >= 0 and not gt_matched[best_gt_i]:
                tp += 1
                gt_matched[best_gt_i] = True
            else:
                fp += 1

        fn = sum(1 for m in gt_matched if not m)
        prec  = tp / max(tp + fp, 1)
        rec   = tp / max(tp + fn, 1)
        f1    = 2.0 * prec * rec / max(prec + rec, 1e-9)
        key   = f'seg_f1_{int(thr * 100):02d}'
        results[key] = float(f1)

    return results


# ===========================================================================
# Wilcoxon signed-rank test (pure numpy, no scipy)
# Implementation: exact normal approximation (n>10), two-sided p-value
# ===========================================================================

def _wilcoxon_pvalue(x: np.ndarray, y: np.ndarray) -> float:
    """
    Two-sided Wilcoxon signed-rank test for paired samples H0: median(x-y)=0.
    Returns p-value. Pure numpy, no scipy.
    Uses normal approximation (valid for n >= 10; for n < 10 returns conservative p=1.0).
    """
    d = x - y
    d = d[d != 0.0]  # remove zeros
    n = len(d)
    if n < 10:
        return 1.0  # conservative: can't reject with too few pairs

    ranks_abs = np.argsort(np.argsort(np.abs(d))) + 1.0  # ranks of |d|, 1-indexed
    W_plus  = float(np.sum(ranks_abs[d > 0]))
    # Expected value and variance under H0
    E_W = n * (n + 1) / 4.0
    Var_W = n * (n + 1) * (2 * n + 1) / 24.0
    if Var_W <= 0:
        return 1.0
    z = (W_plus - E_W) / math.sqrt(Var_W)
    # Two-sided p-value from normal CDF (approximation)
    p = 2.0 * (1.0 - _normal_cdf(abs(z)))
    return float(p)


def _normal_cdf(z: float) -> float:
    """Standard normal CDF via math.erfc approximation."""
    return 0.5 * math.erfc(-z / math.sqrt(2))


# ===========================================================================
# Bootstrap confidence interval (pure numpy)
# ===========================================================================

def _bootstrap_ci(
    values: np.ndarray,
    n_bootstrap: int = 2000,
    alpha: float = 0.05,
    statistic=np.mean,
    rng_seed: int = 42,
) -> Tuple[float, float]:
    """
    Bootstrap (n_bootstrap) resamples of `values`, return (lower, upper) CI
    at confidence level 1-alpha (default 95% CI, alpha=0.05).
    """
    rng = np.random.default_rng(rng_seed)
    boot_stats = np.empty(n_bootstrap, dtype=float)
    n = len(values)
    for i in range(n_bootstrap):
        sample = rng.choice(values, size=n, replace=True)
        boot_stats[i] = statistic(sample)
    lo = float(np.percentile(boot_stats, 100 * alpha / 2))
    hi = float(np.percentile(boot_stats, 100 * (1 - alpha / 2)))
    return lo, hi


# ===========================================================================
# Residual-PTVR: regress PTVR on Jaccard, return residuals
# ===========================================================================

def _linear_residuals(x: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, float]:
    """
    Fit y = a*x + b (OLS), return (residuals, R^2).
    x, y: 1D arrays of same length.
    """
    n = len(x)
    if n < 3:
        return y - y.mean(), 0.0
    x_mean = x.mean()
    y_mean = y.mean()
    ss_xy = float(np.sum((x - x_mean) * (y - y_mean)))
    ss_xx = float(np.sum((x - x_mean) ** 2))
    if ss_xx < 1e-12:
        return y - y_mean, 0.0
    a = ss_xy / ss_xx
    b = y_mean - a * x_mean
    y_hat = a * x + b
    residuals = y - y_hat
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((y - y_mean) ** 2))
    r2 = 1.0 - ss_res / max(ss_tot, 1e-12)
    return residuals, float(r2)


# ===========================================================================
# Arm factory
# ===========================================================================

ARM_NAMES = ['gdn1_neg', 'deltaproduct', 'gla', 'sliding_window', 'gdn1']
TC0_ARMS  = ['gla', 'sliding_window']  # diagonal / local attention arms


def build_arm(
    arm_name: str,
    d_model: int,
    num_heads: int,
    head_dim: int,
    n_layers: int,
    window: int,
) -> SPRModel:
    """Build SPRModel for a given arm. Returns the full model (proj + backbone + head)."""

    def _make_mixer() -> nn.Module:
        if arm_name == 'gdn1_neg':
            return GDN1NegAdapter(hidden_size=d_model, num_heads=num_heads, head_dim=head_dim)
        elif arm_name == 'deltaproduct':
            return DeltaProductAdapter(hidden_size=d_model, num_heads=num_heads, head_dim=head_dim)
        elif arm_name == 'gla':
            return GLAAdapter(hidden_size=d_model, num_heads=num_heads)
        elif arm_name == 'sliding_window':
            return SlidingWindowAttention(
                hidden_size=d_model, num_heads=num_heads,
                head_dim=head_dim, window=window
            )
        elif arm_name == 'gdn1':
            return GDN1Adapter(hidden_size=d_model, num_heads=num_heads, head_dim=head_dim)
        else:
            raise ValueError(f"Unknown arm: {arm_name!r}. Valid: {ARM_NAMES}")

    mixers   = [_make_mixer() for _ in range(n_layers)]
    backbone = SPRBackbone(d_model=d_model, mixers=mixers, n_layers=n_layers)
    model    = SPRModel(d_model=d_model, backbone=backbone)
    return model


def count_numel(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())


# ===========================================================================
# Training loop — one arm, one seed
# ===========================================================================

def train_one_arm(
    arm_name: str,
    seed: int,
    data_root: Path,
    d_model: int,
    num_heads: int,
    head_dim: int,
    n_layers: int,
    window: int,
    steps: int,
    lr: float,
    warmup_steps: int,
    allowed_transitions: np.ndarray,
    device: torch.device,
    log_every: int,
    smoke: bool,
) -> Tuple[nn.Module, Dict]:
    """
    Train one (arm, seed) config on Cholec80 train split.
    Returns (trained_model, train_metrics_dict).
    Online (causal) evaluation: process each video as a full sequence.
    """
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)

    model = build_arm(
        arm_name=arm_name,
        d_model=d_model,
        num_heads=num_heads,
        head_dim=head_dim,
        n_layers=n_layers,
        window=window,
    ).to(device)

    n_params = count_numel(model)
    print(f"  [{arm_name}|seed={seed}] numel={n_params:,}")

    optimizer = torch.optim.AdamW(
        model.parameters(), lr=lr, weight_decay=1e-2, betas=(0.9, 0.999)
    )
    scheduler = CosineWarmupScheduler(
        optimizer, total_steps=steps, warmup_steps=warmup_steps, lr=lr
    )

    # bf16 autocast: FLA chunk_delta_rule requires bf16 on CUDA
    _use_autocast = (device.type == 'cuda')

    # DataLoader: spawn workers required on Windows
    # pin_memory=False (Windows spawn worker restriction)
    train_ids = TRAIN_IDS if not smoke else TRAIN_IDS[:4]
    train_ds  = CholecVideoDataset(data_root=data_root, video_ids=train_ids)
    # num_workers=0 avoids spawn overhead for per-video sequential loading
    train_loader = DataLoader(
        train_ds,
        batch_size=1,
        shuffle=True,
        num_workers=0,
        pin_memory=False,
        multiprocessing_context=None,  # num_workers=0: no multiprocessing
    )

    step = 0
    epoch = 0
    model.train()

    while step < steps:
        epoch += 1
        for feats, labels in train_loader:
            if step >= steps:
                break
            scheduler.step(step + 1)

            # feats: [1, T, 768], labels: [1, T]
            feats  = feats.to(device)    # [1, T, 768]
            labels = labels.to(device).squeeze(0)  # [T]

            with torch.autocast(
                device_type=device.type, dtype=torch.bfloat16, enabled=_use_autocast
            ):
                logits = model(feats)  # [1, T, NUM_PHASES]

            logits_2d = logits.float().squeeze(0)  # [T, NUM_PHASES]
            loss = F.cross_entropy(logits_2d, labels)

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            step += 1
            if step % log_every == 0 or step == steps:
                print(
                    f"  [{arm_name}|seed={seed}] "
                    f"step={step}/{steps} loss={loss.item():.4f} epoch={epoch}"
                )

    return model, {'steps': steps, 'epochs': epoch, 'n_params': n_params}


# ===========================================================================
# Evaluation loop — full test set, collect per-video metrics
# ===========================================================================

def evaluate_arm(
    model: nn.Module,
    data_root: Path,
    allowed_transitions: np.ndarray,
    device: torch.device,
    lr_gap: int,
    smoke: bool,
) -> Dict:
    """
    Evaluate trained model on test split (video41-80).
    Returns per-video metrics and aggregate stats.
    """
    test_ids = TEST_IDS if not smoke else TEST_IDS[:4]
    test_ds  = CholecVideoDataset(data_root=data_root, video_ids=test_ids)

    _use_autocast = (device.type == 'cuda')

    per_video: List[Dict] = []
    model.eval()

    with torch.no_grad():
        for idx in range(len(test_ds)):
            feats, labels = test_ds[idx]  # [T, 768], [T]
            vid = test_ids[idx]

            feats_in = feats.unsqueeze(0).to(device)   # [1, T, 768]
            with torch.autocast(
                device_type=device.type, dtype=torch.bfloat16, enabled=_use_autocast
            ):
                logits = model(feats_in)  # [1, T, NUM_PHASES]
            pred = logits.float().squeeze(0).argmax(dim=-1).cpu().numpy()  # [T]
            gt   = labels.numpy()  # [T]

            # --- Global metrics ---
            global_m = compute_global_metrics(pred, gt, relaxed_window=10)

            # --- PTVR ---
            ptvr_val = compute_ptvr(pred, allowed_transitions)

            # --- Long-range violation ---
            lrv_val = compute_long_range_violation(pred, allowed_transitions, gap=lr_gap)

            # --- Boundary acc ---
            boundary = compute_boundary_acc(pred, gt, window=10)

            # --- Segmental F1 ---
            seg_f1 = compute_segmental_f1(pred, gt, overlap_thresholds=(0.10, 0.25, 0.50))

            per_video.append({
                'video_id': vid,
                **global_m,
                'ptvr':          ptvr_val,
                'lr_violation':  lrv_val,
                'boundary_acc10': boundary,
                **seg_f1,
            })

    # Aggregate (mean across videos)
    agg: Dict[str, float] = {}
    keys_to_agg = [
        'strict_acc', 'strict_jaccard', 'strict_precision', 'strict_recall',
        'relaxed_acc', 'relaxed_jaccard', 'relaxed_precision', 'relaxed_recall',
        'ptvr', 'lr_violation', 'boundary_acc10',
        'seg_f1_10', 'seg_f1_25', 'seg_f1_50',
    ]
    for k in keys_to_agg:
        vals = np.array([v[k] for v in per_video if k in v], dtype=float)
        agg[f'mean_{k}']  = float(np.mean(vals)) if len(vals) > 0 else float('nan')
        agg[f'std_{k}']   = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0
        agg[f'vals_{k}']  = vals.tolist()

    return {'per_video': per_video, 'agg': agg, 'n_test': len(per_video)}


# ===========================================================================
# Cosine LR scheduler (same as parity_probe, reused)
# ===========================================================================

class CosineWarmupScheduler:
    """Linear warmup -> cosine decay."""

    def __init__(
        self,
        optimizer: torch.optim.Optimizer,
        total_steps: int,
        warmup_steps: int,
        lr: float,
    ):
        self.optimizer    = optimizer
        self.total_steps  = total_steps
        self.warmup_steps = max(1, warmup_steps)
        self.base_lr      = lr

    def step(self, step: int) -> None:
        if step < self.warmup_steps:
            lr = self.base_lr * step / self.warmup_steps
        else:
            progress = (step - self.warmup_steps) / max(1, self.total_steps - self.warmup_steps)
            lr = self.base_lr * 0.5 * (1.0 + math.cos(math.pi * progress))
        for pg in self.optimizer.param_groups:
            pg['lr'] = lr


# ===========================================================================
# Calibration mode
# ===========================================================================

def run_calibration(
    data_root: Path,
    d_model: int,
    num_heads: int,
    head_dim: int,
    n_layers: int,
    window: int,
    steps: int,
    lr: float,
    warmup_steps: int,
    allowed_transitions: np.ndarray,
    device: torch.device,
    log_every: int,
    out_dir: Path,
    calib_seeds: List[int],
    calib_capacity_mults: List[float],
    smoke: bool,
    lr_gap: int,
) -> Dict:
    """
    Calibration sweep: TC0 arms (gla + sliding_window) x seeds x capacity mults.
    Outputs:
      1. PTVR-vs-Jaccard scatter data + R^2 -> alerts if R^2 > 0.5
      2. TC0 bootstrap null distribution of PTVR delta -> 95th pct = margin
      3. noise floor (absolute drop lower bound)
    """
    print("[spr_probe] === CALIBRATION MODE ===")
    calib_arms = TC0_ARMS
    all_ptvr:    List[float] = []
    all_jaccard: List[float] = []
    # Collect per-arm per-seed per-video results
    tc0_results: Dict[str, List[Dict]] = defaultdict(list)

    for arm_name in calib_arms:
        for mult in calib_capacity_mults:
            # Adjust d_model by capacity multiplier
            d_m = max(64, int(d_model * mult))
            # Round to nearest multiple of num_heads
            d_m = (d_m // num_heads) * num_heads
            for seed in calib_seeds:
                print(f"\n[calibrate] arm={arm_name} cap_mult={mult:.1f} d={d_m} seed={seed}")
                model, _ = train_one_arm(
                    arm_name=arm_name, seed=seed,
                    data_root=data_root,
                    d_model=d_m, num_heads=num_heads,
                    head_dim=head_dim, n_layers=n_layers,
                    window=window, steps=steps, lr=lr,
                    warmup_steps=warmup_steps,
                    allowed_transitions=allowed_transitions,
                    device=device, log_every=log_every, smoke=smoke,
                )
                eval_r = evaluate_arm(
                    model, data_root, allowed_transitions,
                    device, lr_gap=lr_gap, smoke=smoke,
                )
                for vd in eval_r['per_video']:
                    tc0_results[arm_name].append({
                        'arm':     arm_name,
                        'seed':    seed,
                        'cap_mult': mult,
                        'd_model': d_m,
                        'ptvr':    vd['ptvr'],
                        'jaccard': vd['relaxed_jaccard'],
                    })
                    all_ptvr.append(vd['ptvr'])
                    all_jaccard.append(vd['relaxed_jaccard'])

    # 1. PTVR-vs-Jaccard R^2
    arr_j = np.array(all_jaccard, dtype=float)
    arr_p = np.array(all_ptvr,    dtype=float)
    _, r2  = _linear_residuals(arr_j, arr_p)
    polluted = r2 > 0.5
    print(
        f"[calibrate] PTVR-vs-Jaccard R^2={r2:.4f} "
        f"{'!!! WARNING: PTVR polluted by precision (R^2>0.5), primary verdict may be invalid' if polluted else '-> OK (R^2<=0.5)'}"
    )

    # 2. Bootstrap null distribution: TC0 vs TC0 PTVR delta
    # Use gla vs sliding_window per-video PTVR differences as null
    # (both are TC0: any difference is noise)
    ptvr_gla = np.array([r['ptvr'] for r in tc0_results.get('gla', [])], dtype=float)
    ptvr_sw  = np.array([r['ptvr'] for r in tc0_results.get('sliding_window', [])], dtype=float)
    # Match lengths (use minimum)
    min_len = min(len(ptvr_gla), len(ptvr_sw))
    null_deltas: np.ndarray
    if min_len >= 5:
        null_deltas = np.abs(ptvr_gla[:min_len] - ptvr_sw[:min_len])
    else:
        # Fallback: use all TC0 ptvr values to build null from variance
        null_deltas = np.abs(arr_p - arr_p.mean())

    # Bootstrap 95th percentile of null deltas -> margin
    n_boot = 2000
    rng_boot = np.random.default_rng(1234)
    boot_95 = np.empty(n_boot, dtype=float)
    n_null  = len(null_deltas)
    for i in range(n_boot):
        sample = rng_boot.choice(null_deltas, size=n_null, replace=True)
        boot_95[i] = np.percentile(sample, 95)
    margin = float(np.mean(boot_95))  # expected 95th pct of null
    print(f"[calibrate] Bootstrap null margin (95th pct of TC0 PTVR delta): {margin:.4f}")

    # 3. Noise floor: minimum ptvr observed across TC0
    noise_floor = float(np.min(arr_p)) if len(arr_p) > 0 else 0.0
    print(f"[calibrate] TC0 PTVR noise floor (min): {noise_floor:.4f}")

    # Save calibration results
    calib_out = {
        'ptvr_jaccard_r2':    float(r2),
        'ptvr_polluted_alert': bool(polluted),
        'null_margin':         margin,
        'noise_floor':         noise_floor,
        'n_tc0_points':        int(len(all_ptvr)),
        'raw_records':         {k: v for k, v in tc0_results.items()},
    }
    calib_path = out_dir / 'spr_calibration.json'
    with open(calib_path, 'w', encoding='utf-8') as f:
        json.dump(calib_out, f, indent=2)
    print(f"[calibrate] Saved: {calib_path}")

    return calib_out


# ===========================================================================
# W scan mode
# ===========================================================================

def run_w_scan(
    w_values: List[int],
    data_root: Path,
    d_model: int,
    num_heads: int,
    head_dim: int,
    n_layers: int,
    steps: int,
    lr: float,
    warmup_steps: int,
    allowed_transitions: np.ndarray,
    device: torch.device,
    log_every: int,
    out_dir: Path,
    seeds: List[int],
    smoke: bool,
    lr_gap: int,
) -> Dict:
    """
    Scan sliding_window arm across window sizes W to find Markov saturation.
    Reports PTVR vs W -> where PTVR stops improving = strong Markov upper bound.
    """
    print("[spr_probe] === W SCAN MODE ===")
    scan_results: List[Dict] = []

    for W in w_values:
        for seed in seeds:
            print(f"\n[w_scan] W={W} seed={seed}")
            model, _ = train_one_arm(
                arm_name='sliding_window', seed=seed,
                data_root=data_root,
                d_model=d_model, num_heads=num_heads,
                head_dim=head_dim, n_layers=n_layers,
                window=W, steps=steps, lr=lr,
                warmup_steps=warmup_steps,
                allowed_transitions=allowed_transitions,
                device=device, log_every=log_every, smoke=smoke,
            )
            eval_r = evaluate_arm(
                model, data_root, allowed_transitions,
                device, lr_gap=lr_gap, smoke=smoke,
            )
            scan_results.append({
                'W':               W,
                'seed':            seed,
                'mean_ptvr':       eval_r['agg']['mean_ptvr'],
                'mean_jaccard':    eval_r['agg']['mean_relaxed_jaccard'],
                'mean_lr_viol':    eval_r['agg']['mean_lr_violation'],
            })
            print(
                f"  W={W} seed={seed} ptvr={eval_r['agg']['mean_ptvr']:.4f} "
                f"jaccard={eval_r['agg']['mean_relaxed_jaccard']:.4f}"
            )

    scan_path = out_dir / 'spr_w_scan.json'
    out_data  = {'w_scan': scan_results}
    with open(scan_path, 'w', encoding='utf-8') as f:
        json.dump(out_data, f, indent=2)
    print(f"[w_scan] Saved: {scan_path}")
    return out_data


# ===========================================================================
# Verdict computation (skeptic-corrected, p+CI dual gate)
# ===========================================================================

def compute_verdict(
    all_results: Dict[str, List[Dict]],
    calib_margin: float,
    n_bootstrap: int = 2000,
) -> Dict:
    """
    Compute SPR probe verdict from per-arm per-seed per-video results.

    all_results: {arm_name: [{'seed':int, 'per_video':[{'ptvr':float,'relaxed_jaccard':float,...}], ...}]}
    calib_margin: bootstrap null distribution 95th pct margin from --calibrate.
                  If calibration not run, caller should pass a conservative default.

    Gates:
      P1: gdn1_neg PTVR sig lower than ALL {gla, sliding_window, gdn1}
          Wilcoxon p<0.05 AND relative_drop >= margin AND CI_lower > margin
      P2: gdn1_neg relaxed Jaccard >= max(TC_arms) - 0.01
      P3: gdn1_neg PTVR sig lower than gdn1 (neg-eigval ablation; Wilcoxon p<0.05)
      P4: deltaproduct PTVR <= gdn1_neg (sanity; not a gate, but flags underfitting)

    FAIL = P1 OR P2 OR P3 fails.
    P4 fail = uninterpretable (investigate underfitting).
    """
    # Collect per-video PTVR and jaccard for each arm (pool across seeds)
    arm_ptvr:    Dict[str, List[float]] = defaultdict(list)
    arm_jaccard: Dict[str, List[float]] = defaultdict(list)

    for arm_name, seed_results in all_results.items():
        for sr in seed_results:
            for vd in sr.get('per_video', []):
                arm_ptvr[arm_name].append(float(vd['ptvr']))
                arm_jaccard[arm_name].append(float(vd['relaxed_jaccard']))

    def _ptvr_arr(arm: str) -> np.ndarray:
        return np.array(arm_ptvr.get(arm, []), dtype=float)

    primary_arr = _ptvr_arr('gdn1_neg')

    if len(primary_arr) == 0:
        return {'verdict': 'NO_DATA_gdn1_neg', 'PASS': False}

    # ---- P1: gdn1_neg < {gla, sw, gdn1} ----
    p1_comparisons: Dict[str, Dict] = {}
    p1_all_pass = True
    tc0_jaccards = []
    for ctrl in ['gla', 'sliding_window', 'gdn1']:
        ctrl_arr = _ptvr_arr(ctrl)
        if len(ctrl_arr) == 0:
            p1_comparisons[ctrl] = {'error': f'No data for {ctrl}', 'p1_pass': False}
            p1_all_pass = False
            continue

        # Match lengths for paired test
        n_pairs = min(len(primary_arr), len(ctrl_arr))
        p_arr   = primary_arr[:n_pairs]
        c_arr   = ctrl_arr[:n_pairs]

        pval         = _wilcoxon_pvalue(c_arr, p_arr)  # H0: ctrl == gdn1_neg; want p_arr < c_arr
        mean_primary = float(np.mean(p_arr))
        mean_ctrl    = float(np.mean(c_arr))
        rel_drop     = (mean_ctrl - mean_primary) / max(mean_ctrl, 1e-9)

        # Bootstrap CI on the drop
        drops = c_arr - p_arr
        ci_lo, ci_hi = _bootstrap_ci(drops, n_bootstrap=n_bootstrap, alpha=0.05, statistic=np.mean)

        p1_pass = (
            pval < 0.05
            and rel_drop >= calib_margin
            and ci_lo > calib_margin
        )
        p1_all_pass = p1_all_pass and p1_pass

        p1_comparisons[ctrl] = {
            'wilcoxon_p':   float(pval),
            'mean_ptvr_gdn1_neg': mean_primary,
            'mean_ptvr_ctrl':     mean_ctrl,
            'rel_drop':     float(rel_drop),
            'ci_lower':     float(ci_lo),
            'ci_upper':     float(ci_hi),
            'calib_margin': float(calib_margin),
            'p1_pass':      bool(p1_pass),
        }
        if ctrl in TC0_ARMS:
            tc0_jaccards.extend(arm_jaccard.get(ctrl, []))

    # ---- P2: gdn1_neg relaxed Jaccard >= max(TC arms) - 1pp ----
    gdn1_neg_jacc = float(np.mean(arm_jaccard.get('gdn1_neg', [0.0])))
    max_tc0_jacc  = float(np.max([np.mean(arm_jaccard.get(a, [0.0])) for a in TC0_ARMS])) if TC0_ARMS else 0.0
    p2_pass       = gdn1_neg_jacc >= max_tc0_jacc - 0.01  # 1pp tolerance

    # ---- P3: gdn1_neg PTVR < gdn1 (neg-eigval ablation) ----
    gdn1_arr = _ptvr_arr('gdn1')
    if len(gdn1_arr) == 0:
        p3_pass = False
        p3_detail = {'error': 'No data for gdn1'}
    else:
        n3 = min(len(primary_arr), len(gdn1_arr))
        p3_p = _wilcoxon_pvalue(gdn1_arr[:n3], primary_arr[:n3])
        p3_pass = p3_p < 0.05
        p3_detail = {
            'wilcoxon_p': float(p3_p),
            'mean_ptvr_gdn1_neg': float(np.mean(primary_arr[:n3])),
            'mean_ptvr_gdn1':     float(np.mean(gdn1_arr[:n3])),
            'p3_pass': bool(p3_pass),
        }

    # ---- P4: deltaproduct PTVR <= gdn1_neg (sanity) ----
    dp_arr  = _ptvr_arr('deltaproduct')
    if len(dp_arr) > 0:
        n4 = min(len(primary_arr), len(dp_arr))
        p4_pass = float(np.mean(dp_arr[:n4])) <= float(np.mean(primary_arr[:n4]))
        p4_detail = {
            'mean_ptvr_deltaproduct': float(np.mean(dp_arr[:n4])),
            'mean_ptvr_gdn1_neg':     float(np.mean(primary_arr[:n4])),
            'p4_pass': bool(p4_pass),
        }
    else:
        p4_pass   = None
        p4_detail = {'error': 'No data for deltaproduct'}

    overall_pass = p1_all_pass and p2_pass and p3_pass

    # Residual-PTVR (diagnostic)
    all_ptvr_v   = np.array(arm_ptvr.get('gdn1_neg', []), dtype=float)
    all_jacc_v   = np.array(arm_jaccard.get('gdn1_neg', []), dtype=float)
    if len(all_ptvr_v) >= 3:
        _, r2_ptvr_jacc = _linear_residuals(all_jacc_v, all_ptvr_v)
    else:
        r2_ptvr_jacc = float('nan')

    verdict_str = 'PASS' if overall_pass else 'FAIL'
    if not overall_pass:
        fail_reasons = []
        if not p1_all_pass:
            fail_reasons.append('P1: gdn1_neg PTVR not significantly lower than all controls')
        if not p2_pass:
            fail_reasons.append('P2: gdn1_neg Jaccard below TC0 max - 1pp (precision penalty)')
        if not p3_pass:
            fail_reasons.append('P3: neg-eigval ablation not significant')
        verdict_str = 'FAIL: ' + '; '.join(fail_reasons)

    return {
        'verdict':            verdict_str,
        'PASS':               bool(overall_pass),
        'P1_all_pass':        bool(p1_all_pass),
        'P2_pass':            bool(p2_pass),
        'P3_pass':            bool(p3_pass),
        'P4_pass':            p4_pass,
        'P1_comparisons':     p1_comparisons,
        'P2_detail': {
            'gdn1_neg_jaccard':  gdn1_neg_jacc,
            'max_tc0_jaccard':   max_tc0_jacc,
            'threshold':         max_tc0_jacc - 0.01,
        },
        'P3_detail':          p3_detail,
        'P4_detail':          p4_detail,
        'calib_margin_used':  float(calib_margin),
        'residual_ptvr_r2':   float(r2_ptvr_jacc) if not math.isnan(r2_ptvr_jacc) else None,
        'fail_rule': (
            'FAIL = P1 OR P2 OR P3 fails. P4 fail = underfitting (investigate). '
            'FAIL on PTVR polluted (R^2>0.5 from calibration) = verdict invalid, rerun with R^2<=0.5.'
        ),
    }


# ===========================================================================
# CLI
# ===========================================================================

def parse_args() -> argparse.Namespace:
    _epilog = (
        "Examples:\n"
        "  # Calibration run (defines margin from TC0 null distribution):\n"
        "  python spr_probe.py --mode calibrate --data_root /path/to/cholec80 --seeds 0 1 2\n"
        "\n"
        "  # Window scan (find Markov saturation point for sliding_window):\n"
        "  python spr_probe.py --mode w_scan --w_scan 10 30 60 120 --data_root /path/to/cholec80 --seeds 0\n"
        "\n"
        "  # Full sweep (all 5 arms, 3 seeds, use margin from calibration):\n"
        "  python spr_probe.py --mode full --data_root /path/to/cholec80 --seeds 0 1 2\n"
        "\n"
        "  # Smoke test (HPC minimal forward check; --smoke reduces videos/steps):\n"
        "  python spr_probe.py --smoke --mode full --data_root /path/to/cholec80 --seeds 0\n"
    )
    p = argparse.ArgumentParser(
        description='SPR Probe - Surgical Phase Recognition, Delta Crux 2',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_epilog,
    )

    # Mode
    p.add_argument(
        '--mode', type=str, default='full',
        choices=['full', 'calibrate', 'w_scan'],
        help=(
            'Run mode: full = train+eval all 5 arms; '
            'calibrate = TC0 sweep for null margin; '
            'w_scan = sliding_window W sweep'
        ),
    )

    # Data
    p.add_argument(
        '--data_root', type=str, default='TODO_set_data_root',
        help=(
            'Root dir of Cholec80 data. Expected layout:\n'
            '  <data_root>/features/video01.pkl ...\n'
            '  <data_root>/phase_annotations/video01-phase.txt ...\n'
            '# TODO: data not yet downloaded; set this path once available.'
        ),
    )

    # Arms (full mode)
    p.add_argument(
        '--arms', type=str, nargs='+', default=ARM_NAMES,
        help=f'Arms to run in full mode (default: {ARM_NAMES})',
    )

    # Architecture
    p.add_argument('--d_model',   type=int, default=256,
                   help='Temporal head d_model (default 256)')
    p.add_argument('--num_heads', type=int, default=4,
                   help='Num heads (default 4; head_dim=256/4=64)')
    p.add_argument('--head_dim',  type=int, default=64,
                   help='Head dim (default 64 = d_model/num_heads)')
    p.add_argument('--n_layers',  type=int, default=2,
                   help='Backbone layers (default 2)')
    p.add_argument('--window',    type=int, default=60,
                   help='Sliding window size W (default 60; used in full mode)')

    # Training
    # TODO: lr, steps not confirmed from LoViT official source -- using parity_probe defaults
    # as starting point. Researcher to confirm optimal SPR training settings.
    p.add_argument('--steps',        type=int,   default=20000,
                   help='Training steps per arm per seed (default 20000)')
    p.add_argument('--lr',           type=float, default=1e-3,
                   help='Learning rate (default 1e-3; TODO: confirm from LoViT official)')
    p.add_argument('--warmup_steps', type=int,   default=2000,
                   help='LR warmup steps (default 2000)')

    # Seeds
    p.add_argument('--seeds', type=int, nargs='+', default=[0, 1, 2],
                   help='Seeds for full / calibrate sweep (default: 0 1 2)')

    # Metrics
    p.add_argument('--lr_gap', type=int, default=30,
                   help='Minimum run length (frames) for long-range violation (default 30)')

    # Calibration-specific
    p.add_argument('--calib_capacity_mults', type=float, nargs='+', default=[0.5, 1.0, 2.0],
                   help='Capacity multipliers for calibration sweep (default: 0.5 1.0 2.0)')

    # W scan specific
    p.add_argument('--w_scan', type=int, nargs='+', default=[10, 30, 60, 120],
                   help='Window values for w_scan mode (default: 10 30 60 120)')

    # Calibration margin override (used in full mode verdict)
    p.add_argument('--calib_margin', type=float, default=None,
                   help=(
                       'Override calibration margin (from --calibrate run). '
                       'If not set and calibration JSON exists, loaded automatically. '
                       'If neither, uses conservative default 0.05.'
                   ))

    # Output
    p.add_argument('--out_dir', type=str,
                   default=str(_PROBE_DIR / 'outputs'),
                   help='Output directory for CSV + verdict JSON')

    # Flags
    p.add_argument('--smoke', action='store_true',
                   help=(
                       'Smoke mode: 4 train videos, 4 test videos, 200 steps. '
                       'Validates data loading + forward pass + metric computation. '
                       'Does NOT validate convergence.'
                   ))
    p.add_argument('--log_every', type=int, default=500, help='Log every N steps (default 500)')
    p.add_argument('--n_bootstrap', type=int, default=2000,
                   help='Bootstrap resamples for CI (default 2000)')

    return p.parse_args()


# ===========================================================================
# numel parity check
# ===========================================================================

def check_numel_parity(
    d_model: int, num_heads: int, head_dim: int, n_layers: int, window: int
) -> None:
    """Print numel for all arms and warn if parity is violated (>5% spread)."""
    print("\n[spr_probe] === NUMEL PARITY CHECK ===")
    counts: Dict[str, int] = {}
    for arm in ARM_NAMES:
        if arm in ('gdn1_neg', 'deltaproduct', 'gla', 'gdn1') and not _FLA_AVAILABLE:
            print(f"  {arm}: FLA not available, skipping numel check")
            continue
        try:
            m = build_arm(arm, d_model, num_heads, head_dim, n_layers, window)
            n = count_numel(m)
            counts[arm] = n
            print(f"  {arm}: {n:,}")
        except Exception as e:
            print(f"  {arm}: ERROR ({e})")

    if len(counts) >= 2:
        vals = list(counts.values())
        mn, mx = min(vals), max(vals)
        spread = (mx - mn) / max(mn, 1)
        if spread > 0.05:
            print(
                f"  WARNING: numel spread={spread:.2%} > 5% tolerance. "
                f"Arms are NOT iso-param. Adjust d_model / head_dim."
            )
        else:
            print(f"  numel spread={spread:.2%} <= 5% -> iso-param OK")
    print()


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    args = parse_args()

    # Validate arms
    for arm in args.arms:
        if arm not in ARM_NAMES:
            raise ValueError(f"Unknown arm: {arm!r}. Valid: {ARM_NAMES}")

    # Smoke mode overrides
    if args.smoke:
        args.steps    = 200
        args.log_every = 50
        print(
            f"[spr_probe] SMOKE MODE: steps={args.steps} seeds={args.seeds} "
            f"videos=4train/4test"
        )

    # Device
    if torch.cuda.is_available():
        device = torch.device('cuda')
    else:
        device = torch.device('cpu')
        if any(arm != 'sliding_window' for arm in args.arms):
            print(
                "[spr_probe] WARNING: No CUDA found. FLA arms (gla/gdn1_neg/gdn1/deltaproduct) "
                "require GPU. sliding_window arm is CPU-runnable.",
                file=sys.stderr,
            )
    print(f"[spr_probe] device={device} mode={args.mode}")

    # data_root guard
    if args.data_root == 'TODO_set_data_root':
        print(
            "[spr_probe] WARNING: --data_root not set. "
            "Data not yet downloaded. Set --data_root when available.",
            file=sys.stderr,
        )
        if not args.smoke:
            # Still proceed -- DataLoader will raise FileNotFoundError with clear message
            pass

    data_root = Path(args.data_root)

    # Output directory
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # numel check (before training, purely informational)
    if _FLA_AVAILABLE:
        check_numel_parity(
            args.d_model, args.num_heads, args.head_dim, args.n_layers, args.window
        )

    # Build transition graph from train set (train split only -- no test leak)
    print("[spr_probe] Building transition graph from train split GT ...")
    try:
        train_ds_for_graph = CholecVideoDataset(
            data_root=data_root,
            video_ids=TRAIN_IDS if not args.smoke else TRAIN_IDS[:4],
        )
        allowed_transitions = build_transition_graph(
            train_ds_for_graph,
            train_ds_for_graph.video_ids,
        )
        print(
            f"[spr_probe] Transition graph built: "
            f"{int(allowed_transitions.sum())} allowed transitions (incl. self-loops)."
        )
    except FileNotFoundError as e:
        print(f"[spr_probe] Cannot build transition graph: {e}", file=sys.stderr)
        if not args.smoke:
            raise
        # Smoke with no data: allow all transitions as fallback
        print("[spr_probe] SMOKE fallback: allowing all transitions.", file=sys.stderr)
        allowed_transitions = np.ones((NUM_PHASES, NUM_PHASES), dtype=bool)

    # ---- Calibrate mode ----
    if args.mode == 'calibrate':
        run_calibration(
            data_root=data_root,
            d_model=args.d_model,
            num_heads=args.num_heads,
            head_dim=args.head_dim,
            n_layers=args.n_layers,
            window=args.window,
            steps=args.steps,
            lr=args.lr,
            warmup_steps=args.warmup_steps,
            allowed_transitions=allowed_transitions,
            device=device,
            log_every=args.log_every,
            out_dir=out_dir,
            calib_seeds=args.seeds,
            calib_capacity_mults=args.calib_capacity_mults,
            smoke=args.smoke,
            lr_gap=args.lr_gap,
        )
        return

    # ---- W scan mode ----
    if args.mode == 'w_scan':
        run_w_scan(
            w_values=args.w_scan,
            data_root=data_root,
            d_model=args.d_model,
            num_heads=args.num_heads,
            head_dim=args.head_dim,
            n_layers=args.n_layers,
            steps=args.steps,
            lr=args.lr,
            warmup_steps=args.warmup_steps,
            allowed_transitions=allowed_transitions,
            device=device,
            log_every=args.log_every,
            out_dir=out_dir,
            seeds=args.seeds,
            smoke=args.smoke,
            lr_gap=args.lr_gap,
        )
        return

    # ---- Full mode ----
    # Load calibration margin
    calib_margin = args.calib_margin
    calib_path   = out_dir / 'spr_calibration.json'
    if calib_margin is None:
        if calib_path.exists():
            with open(calib_path, 'r', encoding='utf-8') as cf:
                calib_data = json.load(cf)
            calib_margin = float(calib_data.get('null_margin', 0.05))
            print(f"[spr_probe] Loaded calib_margin={calib_margin:.4f} from {calib_path}")
        else:
            calib_margin = 0.05  # conservative default
            print(
                f"[spr_probe] WARNING: No calibration JSON found at {calib_path}. "
                f"Using conservative default margin={calib_margin}. "
                f"Run --mode calibrate first for data-driven margin.",
                file=sys.stderr,
            )

    # CSV output
    csv_path = out_dir / 'spr_full_results.csv'
    verdict_path = out_dir / 'spr_verdict.json'

    fieldnames = [
        'arm', 'seed', 'd_model', 'num_heads', 'head_dim', 'n_layers', 'window',
        'steps', 'lr',
        'mean_strict_acc', 'mean_strict_jaccard', 'mean_strict_precision', 'mean_strict_recall',
        'mean_relaxed_acc', 'mean_relaxed_jaccard', 'mean_relaxed_precision', 'mean_relaxed_recall',
        'mean_ptvr', 'std_ptvr',
        'mean_lr_violation',
        'mean_boundary_acc10',
        'mean_seg_f1_10', 'mean_seg_f1_25', 'mean_seg_f1_50',
        'n_test_videos',
    ]

    csv_exists = csv_path.exists()
    done_keys: set = set()
    if csv_exists:
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader_check = csv.DictReader(f)
            for row in reader_check:
                done_keys.add((row['arm'], int(row['seed'])))
        print(f"[spr_probe] Found {len(done_keys)} existing arm-seed results, will skip.")

    fout       = open(csv_path, 'a', newline='', encoding='utf-8')
    csv_writer = csv.DictWriter(fout, fieldnames=fieldnames, extrasaction='ignore')
    if not csv_exists:
        csv_writer.writeheader()
        fout.flush()

    # Collect all results for verdict
    all_results: Dict[str, List[Dict]] = defaultdict(list)

    for arm_name in args.arms:
        for seed in args.seeds:
            key = (arm_name, seed)
            if key in done_keys:
                print(f"[spr_probe] Skipping {arm_name} seed={seed} (already in CSV)")
                continue

            print(f"\n[spr_probe] arm={arm_name} seed={seed}")
            model, train_info = train_one_arm(
                arm_name=arm_name,
                seed=seed,
                data_root=data_root,
                d_model=args.d_model,
                num_heads=args.num_heads,
                head_dim=args.head_dim,
                n_layers=args.n_layers,
                window=args.window,
                steps=args.steps,
                lr=args.lr,
                warmup_steps=args.warmup_steps,
                allowed_transitions=allowed_transitions,
                device=device,
                log_every=args.log_every,
                smoke=args.smoke,
            )

            eval_r = evaluate_arm(
                model, data_root, allowed_transitions, device,
                lr_gap=args.lr_gap, smoke=args.smoke,
            )

            agg = eval_r['agg']
            row = {
                'arm': arm_name, 'seed': seed,
                'd_model': args.d_model, 'num_heads': args.num_heads,
                'head_dim': args.head_dim, 'n_layers': args.n_layers,
                'window': args.window, 'steps': args.steps, 'lr': args.lr,
                'mean_strict_acc':      agg['mean_strict_acc'],
                'mean_strict_jaccard':  agg['mean_strict_jaccard'],
                'mean_strict_precision':agg['mean_strict_precision'],
                'mean_strict_recall':   agg['mean_strict_recall'],
                'mean_relaxed_acc':     agg['mean_relaxed_acc'],
                'mean_relaxed_jaccard': agg['mean_relaxed_jaccard'],
                'mean_relaxed_precision': agg['mean_relaxed_precision'],
                'mean_relaxed_recall':  agg['mean_relaxed_recall'],
                'mean_ptvr':      agg['mean_ptvr'],
                'std_ptvr':       agg['std_ptvr'],
                'mean_lr_violation':    agg['mean_lr_violation'],
                'mean_boundary_acc10':  agg['mean_boundary_acc10'],
                'mean_seg_f1_10': agg['mean_seg_f1_10'],
                'mean_seg_f1_25': agg['mean_seg_f1_25'],
                'mean_seg_f1_50': agg['mean_seg_f1_50'],
                'n_test_videos':  eval_r['n_test'],
            }
            csv_writer.writerow(row)
            fout.flush()

            all_results[arm_name].append({
                'seed':      seed,
                'per_video': eval_r['per_video'],
                'agg':       agg,
            })

            print(
                f"  -> ptvr={agg['mean_ptvr']:.4f} jaccard(relaxed)={agg['mean_relaxed_jaccard']:.4f} "
                f"seg_f1_50={agg['mean_seg_f1_50']:.4f}"
            )

    fout.close()
    print(f"\n[spr_probe] Sweep done. Results: {csv_path}")

    # Verdict
    if all_results:
        verdict = compute_verdict(
            all_results, calib_margin=calib_margin, n_bootstrap=args.n_bootstrap
        )
    else:
        verdict = {'verdict': 'NO_NEW_RESULTS', 'PASS': False}

    with open(verdict_path, 'w', encoding='utf-8') as f:
        json.dump(verdict, f, indent=2)

    print(f"\n[spr_probe] === VERDICT ===")
    print(f"  Result: {verdict.get('verdict')}")
    print(f"  PASS:   {verdict.get('PASS')}")
    print(f"  P1 (gdn1_neg PTVR < all controls): {verdict.get('P1_all_pass')}")
    print(f"  P2 (Jaccard >= TC0 max - 1pp):     {verdict.get('P2_pass')}")
    print(f"  P3 (neg-eigval ablation sig):       {verdict.get('P3_pass')}")
    print(f"  P4 (deltaproduct sanity):           {verdict.get('P4_pass')}")
    print(f"  Verdict JSON: {verdict_path}")

    if not verdict.get('PASS'):
        print(
            "\n[spr_probe] FAIL -> direction dead. "
            "Per PREREG red line: no indicator swap / seed expansion / W tuning / "
            "threshold shift allowed. Archive as negative result."
        )


if __name__ == '__main__':
    main()
