"""
Parity / State-Tracking Probe — Delta Crux 1 (PREREG 2026-06-22)
=================================================================
Self-contained experiment: which delta variant truly supports state-tracking,
and does GDN-2 (as-shipped) fail parity due to "gate killing negative eigenvalues"?

Official reference config:
  Grazzi et al., "Unlocking State-Tracking in Linear RNNs Through Negative Eigenvalues"
  https://arxiv.org/abs/2411.12537
  GitHub: https://github.com/automl/unlocking_state_tracking  (parity task config)

Task — Parity (primary):
  Input: random 0/1 token stream.
  Label: per-token CUMULATIVE PARITY (XOR prefix) — token-level cross-entropy, vocab=2.
  Key judgment = OOD length generalisation:
    Train on sequence lengths [3, 40],
    Evaluate on longer lengths [40, 256] (bucketed).
  Diagonal SSM (GLA) theory predicts: OOD parity acc → 0.5 (chance).
  State-tracking arms should hold high acc across ALL length buckets.

Task — S3 (optional second task, --task s3):
  S3 group-word problem: 3 generators of permutation group S3 (|S3|=6),
  per-token label = current group element after composing generators.
  vocab=6. Validates DeltaProduct on non-parity state-tracking.
  # TODO: S3 generator implementation — left as placeholder, parity is primary.

Verdict thresholds (PREREG):
  STATE_TRACKING_LIVE ⟺  long-bucket (length ≥ 128) mean acc > 0.90
  DIAGONAL_FAIL expected: gla long-bucket acc ≈ 0.5  (±0.05)
  🔴-2 (GDN-2 gate kills neg eigval):
    gdn2(as-shipped) long-bucket acc ≈ 0.5  → CONFIRMED (gate kills parity)
    gdn2(as-shipped) long-bucket acc > 0.9  → UNEXPECTED (re-evaluate GDN-2 theory)
  Random baseline: parity=0.5, s3=1/6≈0.167

Training hyperparameters (Grazzi et al. Table 1 alignment):
  d_model=128, num_heads=4, head_dim=32, n_layers=2
  lr=1e-3, batch=256, steps=20000, warmup=2000
  Train lengths: U[3,40], Eval lengths: buckets [40-64, 64-128, 128-256]
  context_length=256 (maximum eval length)

Capacity proof (all arms equal):
  GLA:           expand_k=1.0, expand_v=1.0, num_heads=4
                 → key_dim=128, value_dim=128
                 → head_k_dim=32, head_v_dim=32
                 → state = 4×32×32 = 4096 ✓
  GDN2:          num_heads=4, head_dim=32, expand_v=1.0
                 → head_k_dim=32, head_v_dim=32
                 → state = 4×32×32 = 4096 ✓
  GatedDeltaNet: same as GDN2 (num_heads=4, head_dim=32)
                 → state = 4×32×32 = 4096 ✓
  DeltaNet:      expand_k=1.0, expand_v=1.0, num_heads=4
                 → key_dim=128, value_dim=128
                 → head_k_dim=32, head_v_dim=32
                 → state = 4×32×32 = 4096 ✓
  All arms: use_short_conv=False  (isolate pure mechanism, no short-conv contamination)

Arms (default --arms gla gdn2 gdn1 gdn1_neg deltanet_neg):
  gla           = GatedLinearAttention  (diagonal SSM, predict: OOD fails → 0.5)
  gdn2          = GatedDeltaNet2        (as-shipped, predict: fails — 🔴-2 test)
  gdn1          = GatedDeltaNet(allow_neg_eigval=False)  (baseline delta)
  gdn1_neg      = GatedDeltaNet(allow_neg_eigval=True)   (ablation: neg eigval rescues?)
  deltanet_neg  = DeltaNet(use_beta=True, allow_neg_eigval=True)  (predict: passes)
  deltaproduct  = GatedDeltaProduct(num_householder=2, allow_neg_eigval=True) [s3 arm]

--dummy mode (CPU-runnable, no FLA needed):
  Replaces ALL arms with a minimal PyTorch causal linear mixer (no CUDA).
  Validates task generator + backbone + training loop + verdict + CSV/JSON plumbing.
  Use this for local smoke testing without GPU/FLA.

NO scipy.stats (OMP red-line). All statistics in pure numpy.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# ---------------------------------------------------------------------------
# Directory setup
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_PROBE_DIR = _HERE.parent  # project/meeting/delta-statetrack-probe/

# ---------------------------------------------------------------------------
# FLA availability guard
# ---------------------------------------------------------------------------
try:
    import fla  # noqa: F401
    _FLA_AVAILABLE = True
except ImportError:
    _FLA_AVAILABLE = False
    print(
        "[parity_probe] fla not found — FLA adapters will raise ImportError at construction. "
        "Use --dummy for local plumbing test. Full sweep runs on HPC (fla + CUDA).",
        file=sys.stderr,
    )

# ---------------------------------------------------------------------------
# FLA layer imports (guarded)
# ---------------------------------------------------------------------------
_FLAGatedLinearAttention = None
_FLAGatedDeltaNet2       = None
_FLAGatedDeltaNet        = None
_FLADeltaNet             = None
_FLAGatedDeltaProduct    = None

if _FLA_AVAILABLE:
    from fla.layers import GatedLinearAttention  as _FLAGatedLinearAttention   # noqa: E402
    from fla.layers import GatedDeltaNet2        as _FLAGatedDeltaNet2          # noqa: E402
    from fla.layers import GatedDeltaNet         as _FLAGatedDeltaNet           # noqa: E402
    from fla.layers import DeltaNet              as _FLADeltaNet                # noqa: E402
    from fla.layers import GatedDeltaProduct     as _FLAGatedDeltaProduct       # noqa: E402


# ===========================================================================
# FLA adapter base
# ===========================================================================

class _FLAAdapterBase(nn.Module):
    """
    Base adapter for FLA layers.
    FLA forward: (B,T,H) -> (o: (B,T,H), None, past_kv) — no internal residual.
    Backbone applies pre-norm residual: x = x + mixer(LN(x)).
    """
    has_internal_residual: bool = False

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        o, _, _ = self.layer(x)
        return o


# ===========================================================================
# Arm 1: GLA — diagonal SSM, predict OOD parity → 0.5 (chance)
# ===========================================================================

class GLAAdapter(_FLAAdapterBase):
    """
    GLA arm: GatedLinearAttention (gate+stateful, NO delta).

    Capacity: expand_k=1.0, expand_v=1.0, num_heads=4
      key_dim=128, value_dim=128
      head_k_dim=128//4=32, head_v_dim=128//4=32
      state = 4×32×32 = 4096  ✓

    NOTE: expand_k default=0.5 in FLA → head_k_dim=16 (capacity halved, WRONG).
    Must set expand_k=1.0 for capacity parity.
    use_output_gate=True (keep GLA's own output gating as-shipped).
    use_short_conv=False (isolate pure mechanism).
    """

    def __init__(self, hidden_size: int = 128, num_heads: int = 4):
        super().__init__()
        if not _FLA_AVAILABLE:
            raise ImportError(
                "GLAAdapter requires fla (flash-linear-attention) with CUDA. "
                "Use --dummy for CPU plumbing test."
            )
        # GLA signature: mode, hidden_size, expand_k=0.5, expand_v=1.0,
        #                num_heads=4, use_short_conv=False, use_output_gate=True, ...
        self.layer = _FLAGatedLinearAttention(
            mode='chunk',
            hidden_size=hidden_size,
            expand_k=1.0,           # CRITICAL: default 0.5 halves capacity
            expand_v=1.0,
            num_heads=num_heads,
            use_short_conv=False,   # isolate mechanism
            use_output_gate=True,   # keep GLA as-shipped
        )


# ===========================================================================
# Arm 2: GDN-2 (as-shipped) — 🔴-2 test: predict fails due to gate
# ===========================================================================

class GDN2Adapter(_FLAAdapterBase):
    """
    GDN-2 arm: GatedDeltaNet2 as-shipped (allow_neg_eigval=False by default).

    Capacity: num_heads=4, head_dim=32, expand_v=1.0
      head_k_dim=32, head_v_dim=32
      state = 4×32×32 = 4096  ✓

    🔴-2 Crux: GDN-2 as-shipped has allow_neg_eigval=False.
    Theory predicts: erase-gate b ∈ (0,1) → beta effectively ∈ (0,1) →
    no negative eigenvalues → parity long-bucket acc → 0.5 (FAIL).
    If instead acc > 0.9: GDN-2 unexpectedly retains state-tracking, re-evaluate.
    """

    def __init__(self, hidden_size: int = 128, num_heads: int = 4, head_dim: int = 32):
        super().__init__()
        if not _FLA_AVAILABLE:
            raise ImportError("GDN2Adapter requires fla with CUDA.")
        # GDN2 signature: hidden_size, expand_v=1.0, head_dim=128,
        #                 num_heads=16, mode='chunk', use_short_conv=True, allow_neg_eigval=False
        self.layer = _FLAGatedDeltaNet2(
            hidden_size=hidden_size,
            num_heads=num_heads,
            head_dim=head_dim,
            expand_v=1.0,
            use_short_conv=False,   # isolate pure mechanism
            allow_neg_eigval=False, # as-shipped default
            mode='chunk',
        )


# ===========================================================================
# Arm 3: GDN-1 default (allow_neg_eigval=False) — delta baseline
# ===========================================================================

class GDN1Adapter(_FLAAdapterBase):
    """
    GDN-1 arm: GatedDeltaNet(allow_neg_eigval=False) — default GDN-1.

    Capacity: num_heads=4, head_dim=32, expand_v=1.0
      head_k_dim=32, head_v_dim=32
      state = 4×32×32 = 4096  ✓

    Predicts: without negative eigenvalues, parity long-bucket acc → 0.5 (FAIL).
    """

    def __init__(self, hidden_size: int = 128, num_heads: int = 4, head_dim: int = 32):
        super().__init__()
        if not _FLA_AVAILABLE:
            raise ImportError("GDN1Adapter requires fla with CUDA.")
        # GatedDeltaNet signature: hidden_size, expand_v=2.0, head_dim=256,
        #   num_heads=6, mode='chunk', use_gate=True, use_short_conv=True,
        #   allow_neg_eigval=False
        # NOTE: expand_v=1.0 (not default 2.0) for capacity parity.
        #       use_gate=True kept (as-shipped GDN-1 output gate).
        self.layer = _FLAGatedDeltaNet(
            hidden_size=hidden_size,
            num_heads=num_heads,
            head_dim=head_dim,
            expand_v=1.0,           # capacity parity
            use_short_conv=False,   # isolate mechanism
            use_gate=True,          # as-shipped GDN-1
            allow_neg_eigval=False, # default: no neg eigval
            mode='chunk',
        )


# ===========================================================================
# Arm 4: GDN-1 + neg eigval (ablation — does neg eigval rescue parity?)
# ===========================================================================

class GDN1NegAdapter(_FLAAdapterBase):
    """
    GDN-1 arm with allow_neg_eigval=True.

    Ablation: enabling neg eigenvalues on GDN-1 (via beta×2 trick per Grazzi).
    Predicts: parity long-bucket acc > 0.9 (PASS — neg eigval enables state-tracking).
    """

    def __init__(self, hidden_size: int = 128, num_heads: int = 4, head_dim: int = 32):
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
            allow_neg_eigval=True,  # ablation: enable neg eigval
            mode='chunk',
        )


# ===========================================================================
# Arm 5: DeltaNet + neg eigval — primary state-tracking positive control
# ===========================================================================

class DeltaNetNegAdapter(_FLAAdapterBase):
    """
    DeltaNet arm: DeltaNet(use_beta=True, allow_neg_eigval=True).

    Capacity: expand_k=1.0, expand_v=1.0, num_heads=4
      key_dim=128, value_dim=128
      head_k_dim=32, head_v_dim=32
      state = 4×32×32 = 4096  ✓

    Predicts: parity long-bucket acc > 0.9 (PASS).
    This is the Grazzi et al. positive control — DeltaNet with neg eigval SHOULD
    perform state-tracking per their theory and experiments.
    """

    def __init__(self, hidden_size: int = 128, num_heads: int = 4):
        super().__init__()
        if not _FLA_AVAILABLE:
            raise ImportError("DeltaNetNegAdapter requires fla with CUDA.")
        # DeltaNet signature: mode, hidden_size, expand_k=1.0, expand_v=1.0,
        #   num_heads=4, use_beta=True, use_gate=False, use_short_conv=True,
        #   allow_neg_eigval=False
        self.layer = _FLADeltaNet(
            mode='chunk',
            hidden_size=hidden_size,
            expand_k=1.0,
            expand_v=1.0,
            num_heads=num_heads,
            use_beta=True,          # required for delta rule update
            use_gate=False,         # no output gate (DeltaNet original)
            use_short_conv=False,   # isolate mechanism
            allow_neg_eigval=True,  # enables state-tracking per Grazzi
        )


# ===========================================================================
# Arm 6: GatedDeltaProduct — S3 arm (also tested on parity)
# ===========================================================================

class DeltaProductAdapter(_FLAAdapterBase):
    """
    GatedDeltaProduct arm: num_householder=2, allow_neg_eigval=True.

    Capacity: num_heads=4, head_dim=32, expand_v=1.0
      head_k_dim=32, head_v_dim=32
      state = 4×32×32 = 4096  ✓

    Predicts: parity PASS (positive control for S3 group-word problem).
    GatedDeltaProduct with 2 Householder reflections can represent more complex
    state transitions needed for S3 (|S3|=6 group elements).

    Note: GatedDeltaProduct has allow_neg_eigval=True as default already.
    """

    def __init__(self, hidden_size: int = 128, num_heads: int = 4, head_dim: int = 32):
        super().__init__()
        if not _FLA_AVAILABLE:
            raise ImportError("DeltaProductAdapter requires fla with CUDA.")
        # GatedDeltaProduct signature: hidden_size, expand_v=2, head_dim=256,
        #   num_heads=6, mode='chunk', use_output_gate=True, use_short_conv=True,
        #   allow_neg_eigval=True, num_householder=2
        self.layer = _FLAGatedDeltaProduct(
            hidden_size=hidden_size,
            num_heads=num_heads,
            head_dim=head_dim,
            expand_v=1.0,           # capacity parity
            use_short_conv=False,   # isolate mechanism
            use_output_gate=True,   # as-shipped
            allow_neg_eigval=True,
            num_householder=2,      # Householder product depth
            mode='chunk',
        )


# ===========================================================================
# Dummy mixer — CPU fallback for plumbing tests (no FLA/CUDA needed)
# ===========================================================================

class _DummyCausalMixer(nn.Module):
    """
    Minimal causal linear mixer for --dummy mode.
    No FLA dependency. Implements a simple causal cumsum-weighted value:
        s_t = decay * s_{t-1} + k_t^T v_t  (scalar decay, no matrix state)
    This is intentionally weak (won't solve parity at OOD lengths) — the point is
    to validate task generator + backbone plumbing + CSV/JSON output, not model correctness.
    """
    has_internal_residual: bool = False

    def __init__(self, hidden_size: int = 128):
        super().__init__()
        self.hidden_size = hidden_size
        self.q_proj = nn.Linear(hidden_size, hidden_size, bias=False)
        self.k_proj = nn.Linear(hidden_size, hidden_size, bias=False)
        self.v_proj = nn.Linear(hidden_size, hidden_size, bias=False)
        self.o_proj = nn.Linear(hidden_size, hidden_size, bias=False)
        self.norm   = nn.LayerNorm(hidden_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B,T,H) → (B,T,H). Causal cumsum attention (diagonal, no neg eigval)."""
        B, T, H = x.shape
        q = self.q_proj(x)  # (B,T,H)
        k = self.k_proj(x)  # (B,T,H)
        v = self.v_proj(x)  # (B,T,H)
        # Scalar softmax over causal positions (simple causal attention approx)
        # Purely for plumbing — not a real SSM
        attn_logits = torch.bmm(q, k.transpose(1, 2)) / math.sqrt(H)  # (B,T,T)
        causal_mask = torch.tril(torch.ones(T, T, device=x.device, dtype=torch.bool))
        attn_logits = attn_logits.masked_fill(~causal_mask, float('-inf'))
        attn_weights = torch.softmax(attn_logits, dim=-1)  # (B,T,T)
        out = torch.bmm(attn_weights, v)                   # (B,T,H)
        return self.o_proj(self.norm(out))


# ===========================================================================
# FFN block
# ===========================================================================

class FFN(nn.Module):
    """
    Two-layer FFN: Linear(d→4d) + GELU + Linear(4d→d). No bias.
    Standard expand=4 (VLA / Grazzi).
    """

    def __init__(self, d_model: int, expand: int = 4):
        super().__init__()
        self.fc1 = nn.Linear(d_model, d_model * expand, bias=False)
        self.fc2 = nn.Linear(d_model * expand, d_model, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.fc2(F.gelu(self.fc1(x)))


# ===========================================================================
# 2-layer backbone (pre-norm residual)
# ===========================================================================

class ParityBackbone(nn.Module):
    """
    2-layer backbone: each layer = pre-norm residual mixer + pre-norm residual FFN.
      x = x + mixer(LN(x))
      x = x + FFN(LN(x))
    FLA layers have no internal residual (has_internal_residual=False).
    """

    def __init__(
        self,
        d_model: int,
        mixers: List[nn.Module],
        n_layers: int = 2,
        ffn_expand: int = 4,
    ):
        super().__init__()
        assert len(mixers) == n_layers, (
            f"len(mixers)={len(mixers)} must equal n_layers={n_layers}"
        )
        self.n_layers = n_layers
        self.d_model  = d_model

        self.mixer_norms = nn.ModuleList([nn.LayerNorm(d_model) for _ in range(n_layers)])
        self.ffn_norms   = nn.ModuleList([nn.LayerNorm(d_model) for _ in range(n_layers)])
        self.mixers      = nn.ModuleList(mixers)
        self.ffns        = nn.ModuleList([FFN(d_model, expand=ffn_expand) for _ in range(n_layers)])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B,T,d_model) → (B,T,d_model)"""
        for i in range(self.n_layers):
            mixer = self.mixers[i]
            if getattr(mixer, 'has_internal_residual', False):
                x = mixer(x)
            else:
                x = x + mixer(self.mixer_norms[i](x))
            x = x + self.ffns[i](self.ffn_norms[i](x))
        return x


# ===========================================================================
# Full model (embed → backbone → head, weight-tied)
# ===========================================================================

class ParityModel(nn.Module):
    """
    Embedding(vocab_size, d_model) → ParityBackbone → Linear(d_model, vocab_size).
    Weight tying: head.weight = embed.weight.
    vocab_size = 2 for parity, 6 for s3.
    """

    def __init__(self, vocab_size: int, d_model: int, backbone: ParityBackbone):
        super().__init__()
        self.vocab_size = vocab_size
        self.d_model    = d_model
        self.embed      = nn.Embedding(vocab_size, d_model)
        self.backbone   = backbone
        self.head       = nn.Linear(d_model, vocab_size, bias=False)
        # Weight tying
        self.head.weight = self.embed.weight

    def forward(self, token_ids: torch.Tensor) -> torch.Tensor:
        """token_ids: (B,T) long → logits: (B,T,vocab_size)"""
        x = self.embed(token_ids)   # (B,T,d_model)
        x = self.backbone(x)        # (B,T,d_model)
        return self.head(x)          # (B,T,vocab_size)


# ===========================================================================
# Task generators
# ===========================================================================

def build_parity_batch(
    batch_size: int,
    seq_len: int,
    device: torch.device,
    rng: np.random.Generator,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    Parity task (Grazzi et al.).
    Input: random 0/1 token stream, shape (B,T), dtype long.
    Label: cumulative XOR prefix, shape (B,T), dtype long.
      label[t] = token[0] XOR token[1] XOR ... XOR token[t]
    Token 0 = bit-0, token 1 = bit-1.
    All positions have valid labels (no padding / ignore_index=-100 needed here).
    """
    # tokens: (B,T) ∈ {0,1}
    tokens = rng.integers(0, 2, size=(batch_size, seq_len), dtype=np.int64)
    # parity: cumulative XOR
    parity = np.cumsum(tokens, axis=1) % 2  # (B,T) ∈ {0,1}
    token_t  = torch.from_numpy(tokens).to(device)
    parity_t = torch.from_numpy(parity).to(device)
    return token_t, parity_t


def build_s3_batch(
    batch_size: int,
    seq_len: int,
    device: torch.device,
    rng: np.random.Generator,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    S3 group-word problem (Grazzi et al.).
    S3 = symmetric group on 3 elements, |S3|=6.
    3 generators: r (rotation by 120°), s (reflection), identity.
    We use the standard presentation:
      elements as permutations of (0,1,2):
        e=(0,1,2), r=(1,2,0), r2=(2,0,1), s=(0,2,1), sr=(2,1,0), sr2=(1,0,2)
      Tokens (generators + their inverses): we use 3 generators mapped to tokens 0..5:
        token 0 → r  (rotation), token 1 → r2=r^{-1}, token 2 → s,
        token 3 → sr, token 4 → sr2, token 5 → e (identity)
    Current state = index of current group element after composing all generators so far.
    Label[t] = index of current group element after applying generator[t].
    # TODO: full S3 generator composition table — implement when --task s3 is needed.
    """
    raise NotImplementedError(
        "S3 task not yet implemented. Use --task parity (default). "
        "# TODO: S3 generator composition table + state-tracking per Grazzi §4."
    )


# Composition table for S3 (element × generator → new element).
# S3 elements indexed 0..5: e, r, r2, s, sr, sr2
# Generators (token values): 0=r, 1=r^{-1}=r2, 2=s, 3=sr, 4=sr2, 5=e
# TODO: fill in when S3 task activated.
_S3_COMPOSE_TABLE: Optional[np.ndarray] = None  # shape (6, 6) when filled


# ===========================================================================
# Sampler: uniform random training length in [lo, hi]
# ===========================================================================

def sample_train_length(lo: int, hi: int, rng: np.random.Generator) -> int:
    """Sample a uniform random sequence length in [lo, hi]."""
    return int(rng.integers(lo, hi + 1))


# ===========================================================================
# Eval length buckets
# ===========================================================================

# OOD evaluation buckets: (name, lo_inclusive, hi_inclusive)
_EVAL_BUCKETS = [
    ('40-64',   40,  64),
    ('64-128',  64,  128),
    ('128-256', 128, 256),
]
_BUCKET_NAMES = [b[0] for b in _EVAL_BUCKETS]


def _bucket_for_length(length: int) -> Optional[str]:
    for name, lo, hi in _EVAL_BUCKETS:
        if lo <= length <= hi:
            return name
    return None


# ===========================================================================
# Cosine LR scheduler with linear warmup
# ===========================================================================

class CosineWarmupScheduler:
    """
    Linear warmup (0 → lr over warmup_steps) + cosine decay (lr → 0).
    Grazzi config: lr=1e-3, total_steps=20000, warmup=2000.
    """

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
# Training loop — one arm, one seed
# ===========================================================================

def train_one_arm(
    arm_name: str,
    task: str,
    seed: int,
    # Architecture
    d_model: int,
    num_heads: int,
    head_dim: int,
    n_layers: int,
    # Training
    steps: int,
    lr: float,
    warmup_steps: int,
    batch_size: int,
    train_len_lo: int,
    train_len_hi: int,
    # Eval
    n_eval_seqs_per_bucket: int,
    eval_lengths_per_bucket: int,
    context_length: int,
    # Hardware
    device: torch.device,
    dummy: bool,
    log_every: int,
) -> Dict:
    """
    Train one (arm, seed) config. Returns result dict with per-bucket eval acc.

    arm_name: 'gla' | 'gdn2' | 'gdn1' | 'gdn1_neg' | 'deltanet_neg' | 'deltaproduct'
    task:     'parity' | 's3'  (s3 raises NotImplementedError until implemented)
    """
    # Seeding
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    rng = np.random.default_rng(seed)

    # Vocab size
    if task == 'parity':
        vocab_size = 2
    elif task == 's3':
        vocab_size = 6
    else:
        raise ValueError(f"Unknown task: {task!r}. Valid: 'parity', 's3'")

    # ---- Build model ----
    def _make_mixer() -> nn.Module:
        if dummy:
            return _DummyCausalMixer(hidden_size=d_model)
        if arm_name == 'gla':
            return GLAAdapter(hidden_size=d_model, num_heads=num_heads)
        elif arm_name == 'gdn2':
            return GDN2Adapter(hidden_size=d_model, num_heads=num_heads, head_dim=head_dim)
        elif arm_name == 'gdn1':
            return GDN1Adapter(hidden_size=d_model, num_heads=num_heads, head_dim=head_dim)
        elif arm_name == 'gdn1_neg':
            return GDN1NegAdapter(hidden_size=d_model, num_heads=num_heads, head_dim=head_dim)
        elif arm_name == 'deltanet_neg':
            return DeltaNetNegAdapter(hidden_size=d_model, num_heads=num_heads)
        elif arm_name == 'deltaproduct':
            return DeltaProductAdapter(hidden_size=d_model, num_heads=num_heads, head_dim=head_dim)
        else:
            raise ValueError(f"Unknown arm: {arm_name!r}")

    mixers = [_make_mixer() for _ in range(n_layers)]
    backbone = ParityBackbone(d_model=d_model, mixers=mixers, n_layers=n_layers)
    model = ParityModel(vocab_size=vocab_size, d_model=d_model, backbone=backbone).to(device)

    # ---- Optimizer + Scheduler ----
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=lr,
        weight_decay=1e-2,
        betas=(0.9, 0.999),
    )
    scheduler = CosineWarmupScheduler(
        optimizer, total_steps=steps, warmup_steps=warmup_steps, lr=lr
    )

    # ---- AMP autocast flag ----
    # chunk_delta_rule (used by DeltaNet / GDN family) forbids fp32; requires bf16.
    # Use CUDA autocast to feed bf16 to FLA kernels without converting the whole model.
    # dummy mode runs on CPU and does not use FLA, so autocast is skipped there.
    _use_autocast = (device.type == 'cuda') and (not dummy)

    # ---- Training ----
    model.train()
    for step in range(1, steps + 1):
        scheduler.step(step)

        # Sample random training length uniformly in [train_len_lo, train_len_hi]
        seq_len = sample_train_length(train_len_lo, train_len_hi, rng)

        if task == 'parity':
            token_ids, labels = build_parity_batch(batch_size, seq_len, device, rng)
        else:
            token_ids, labels = build_s3_batch(batch_size, seq_len, device, rng)

        with torch.autocast(device_type='cuda', dtype=torch.bfloat16, enabled=_use_autocast):
            logits = model(token_ids)  # (B,T,vocab_size)
        # Cast logits to float32 before CE for numerical stability (AMP best practice).
        # labels stay int64, unaffected by autocast.
        B, T, V = logits.shape
        loss = F.cross_entropy(
            logits.float().reshape(B * T, V),
            labels.reshape(B * T),
            ignore_index=-100,
        )

        optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

        if step % log_every == 0 or step == steps:
            print(
                f"  [{arm_name}|{task}|seed={seed}] "
                f"step={step}/{steps} loss={loss.item():.4f} len={seq_len}"
            )

    # ---- OOD Evaluation ----
    model.eval()
    bucket_results: Dict[str, Dict] = {}

    with torch.no_grad():
        for bucket_name, bucket_lo, bucket_hi in _EVAL_BUCKETS:
            all_correct = 0
            all_total   = 0

            # Sample eval_lengths_per_bucket lengths uniformly in [bucket_lo, bucket_hi]
            eval_rng = np.random.default_rng(seed + 99999)  # fixed eval seed
            eval_lengths = eval_rng.integers(bucket_lo, bucket_hi + 1, size=eval_lengths_per_bucket)

            for eval_len in eval_lengths:
                # Guard: don't exceed context_length
                eval_len = min(int(eval_len), context_length)

                n_eval = max(16, n_eval_seqs_per_bucket // eval_lengths_per_bucket)
                eval_batch_rng = np.random.default_rng(seed + 88888 + int(eval_len))

                if task == 'parity':
                    tok_e, lab_e = build_parity_batch(n_eval, eval_len, device, eval_batch_rng)
                else:
                    tok_e, lab_e = build_s3_batch(n_eval, eval_len, device, eval_batch_rng)

                with torch.autocast(device_type='cuda', dtype=torch.bfloat16, enabled=_use_autocast):
                    logits_e = model(tok_e)  # (B,T,V)
                # argmax on fp32 for accuracy (float() is cheap; avoids bf16 tie-breaking oddities)
                preds    = logits_e.float().argmax(dim=-1)  # (B,T)
                # All positions have valid labels (no ignore_index in parity)
                mask = (lab_e != -100)
                all_correct += ((preds == lab_e) & mask).sum().item()
                all_total   += mask.sum().item()

            acc = all_correct / max(all_total, 1)
            random_baseline = 1.0 / vocab_size

            bucket_results[bucket_name] = {
                'acc':             float(acc),
                'n_correct':       int(all_correct),
                'n_total':         int(all_total),
                'random_baseline': float(random_baseline),
                'above_chance':    bool(acc > random_baseline + 0.05),
                'live_threshold':  0.90,
                'live':            bool(acc > 0.90),
            }
            print(
                f"  [{arm_name}|{task}|seed={seed}] "
                f"OOD bucket {bucket_name}: acc={acc:.4f} "
                f"({'LIVE' if acc > 0.90 else 'FAIL'})"
            )

    # Long-bucket acc (≥128) for 🔴-2 verdict
    long_bucket = bucket_results.get('128-256', {})
    long_acc = long_bucket.get('acc', float('nan'))

    return {
        'arm':        arm_name,
        'task':       task,
        'seed':       seed,
        'd_model':    d_model,
        'num_heads':  num_heads,
        'head_dim':   head_dim,
        'n_layers':   n_layers,
        'steps':      steps,
        'lr':         lr,
        'dummy':      int(dummy),
        'long_acc_128_256': float(long_acc),
        'bucket_40_64':     float(bucket_results.get('40-64',   {}).get('acc', float('nan'))),
        'bucket_64_128':    float(bucket_results.get('64-128',  {}).get('acc', float('nan'))),
        'bucket_128_256':   float(bucket_results.get('128-256', {}).get('acc', float('nan'))),
    }


# ===========================================================================
# Verdict computation (pure numpy, no scipy)
# ===========================================================================

def compute_verdict(csv_path: Path, task: str) -> Dict:
    """
    Read sweep CSV, compute per-arm mean±std across seeds for each length bucket.
    Judge STATE_TRACKING_LIVE / DIAGONAL_FAIL / 🔴-2.

    Thresholds (PREREG):
      STATE_TRACKING_LIVE ⟺ long-bucket (128-256) mean acc > 0.90
      DIAGONAL_FAIL       ⟺ gla long-bucket mean acc ≤ 0.55 (≈ 0.5 ± 0.05)
      🔴-2 CONFIRMED      ⟺ gdn2 long-bucket mean acc ≤ 0.55
      🔴-2 UNEXPECTED     ⟺ gdn2 long-bucket mean acc > 0.90

    Random baseline: parity=0.5, s3=1/6≈0.167
    """
    rows: List[Dict] = []
    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('task', task) != task:
                continue
            rows.append({
                'arm':              row['arm'],
                'seed':             int(row['seed']),
                'long_acc_128_256': float(row['long_acc_128_256']),
                'bucket_40_64':     float(row['bucket_40_64']),
                'bucket_64_128':    float(row['bucket_64_128']),
                'bucket_128_256':   float(row['bucket_128_256']),
                'dummy':            int(row.get('dummy', 0)),
            })

    if not rows:
        return {'verdict': 'NO_DATA', 'error': 'Empty or mismatched CSV for task=' + task}

    # Aggregate per arm
    from collections import defaultdict
    arm_buckets: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: {
        '40-64': [], '64-128': [], '128-256': []
    })
    for r in rows:
        arm_buckets[r['arm']]['40-64'].append(r['bucket_40_64'])
        arm_buckets[r['arm']]['64-128'].append(r['bucket_64_128'])
        arm_buckets[r['arm']]['128-256'].append(r['bucket_128_256'])

    # Stats (pure numpy)
    stats: Dict[str, Dict] = {}
    for arm, buckets in arm_buckets.items():
        stats[arm] = {}
        for bname, accs in buckets.items():
            arr = np.array(accs, dtype=float)
            n = len(arr)
            stats[arm][bname] = {
                'mean':    float(np.mean(arr)),
                'std':     float(np.std(arr, ddof=1) if n > 1 else 0.0),
                'n_seeds': n,
                'accs':    [float(a) for a in arr],
            }

    random_baseline = 0.5 if task == 'parity' else 1.0 / 6.0

    # Per-arm live/fail judgment
    arm_verdicts: Dict[str, Dict] = {}
    for arm, bstats in stats.items():
        long_mean = bstats.get('128-256', {}).get('mean', float('nan'))
        arm_verdicts[arm] = {
            'long_bucket_128_256_mean': long_mean,
            'STATE_TRACKING_LIVE':      bool(long_mean > 0.90),
            'AT_CHANCE':                bool(not math.isnan(long_mean) and long_mean <= 0.55),
        }

    # 🔴-2 GDN-2 verdict
    gdn2_long = arm_verdicts.get('gdn2', {}).get('long_bucket_128_256_mean', float('nan'))
    if math.isnan(gdn2_long):
        red2_verdict = 'NO_DATA'
    elif gdn2_long > 0.90:
        red2_verdict = 'UNEXPECTED_PASS (GDN-2 retains parity — re-evaluate gate-kills-neg-eigval theory)'
    elif gdn2_long <= 0.55:
        red2_verdict = 'CONFIRMED (gate kills neg eigval — GDN-2 cannot do parity OOD)'
    else:
        red2_verdict = f'AMBIGUOUS (long acc={gdn2_long:.3f}, between 0.55 and 0.90)'

    # DIAGONAL_FAIL check for GLA
    gla_long = arm_verdicts.get('gla', {}).get('long_bucket_128_256_mean', float('nan'))
    diagonal_fail = (not math.isnan(gla_long)) and (gla_long <= 0.55)

    # Overall state-tracking arms
    live_arms = [arm for arm, v in arm_verdicts.items() if v['STATE_TRACKING_LIVE']]
    dead_arms = [arm for arm, v in arm_verdicts.items() if not v['STATE_TRACKING_LIVE']]

    return {
        'task':             task,
        'random_baseline':  random_baseline,
        'prereg_thresholds': {
            'STATE_TRACKING_LIVE':  '>0.90 long-bucket (128-256) mean acc',
            'DIAGONAL_FAIL':        'gla long-bucket mean acc ≤ 0.55',
            'RED2_CONFIRMED':       'gdn2 long-bucket mean acc ≤ 0.55',
        },
        'stats':            stats,
        'arm_verdicts':     arm_verdicts,
        'live_arms':        live_arms,
        'dead_arms':        dead_arms,
        'gla_diagonal_fail': diagonal_fail,
        'red2_verdict':     red2_verdict,
        'gdn2_long_acc':    float(gdn2_long) if not math.isnan(gdn2_long) else None,
        'gla_long_acc':     float(gla_long)  if not math.isnan(gla_long)  else None,
        'n_rows_parsed':    len(rows),
    }


# ===========================================================================
# CLI
# ===========================================================================

def parse_args() -> argparse.Namespace:
    _epilog = (
        "Examples:\n"
        "  # CPU plumbing smoke test (no FLA/GPU needed):\n"
        "  python parity_probe.py --dummy --smoke\n"
        "\n"
        "  # FLA smoke test on GPU (minimal steps):\n"
        "  python parity_probe.py --smoke --arms gla gdn2\n"
        "\n"
        "  # Full sweep (HPC, all arms, 3 seeds):\n"
        "  python parity_probe.py --arms gla gdn2 gdn1 gdn1_neg deltanet_neg --seeds 0 1 2\n"
    )
    p = argparse.ArgumentParser(
        description='Parity / State-Tracking Probe - Delta Crux 1 (gdn2vessel Crux 1)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_epilog,
    )

    # Task
    p.add_argument('--task', type=str, default='parity', choices=['parity', 's3'],
                   help='Task: parity (default) or s3 (S3 group-word, TODO)')

    # Arms
    p.add_argument('--arms', type=str, nargs='+',
                   default=['gla', 'gdn2', 'gdn1', 'gdn1_neg', 'deltanet_neg'],
                   help=(
                       'Arms to run (space-separated). '
                       'gla=GatedLinearAttention, gdn2=GatedDeltaNet2(as-shipped), '
                       'gdn1=GatedDeltaNet(no neg eigval), gdn1_neg=GatedDeltaNet(neg eigval), '
                       'deltanet_neg=DeltaNet(neg eigval), deltaproduct=GatedDeltaProduct. '
                       'Default excludes deltaproduct (s3 arm).'
                   ))

    # Architecture
    p.add_argument('--d_model',   type=int, default=128, help='Model dim (default 128)')
    p.add_argument('--num_heads', type=int, default=4,   help='Num heads (default 4; head_dim=128/4=32)')
    p.add_argument('--head_dim',  type=int, default=32,  help='Head dim (default 32 = d_model/num_heads)')
    p.add_argument('--n_layers',  type=int, default=2,   help='Backbone layers (default 2)')

    # Training (Grazzi et al. Table 1)
    p.add_argument('--steps',       type=int,   default=20000, help='Training steps (default 20000)')
    p.add_argument('--lr',          type=float, default=1e-3,  help='Learning rate (default 1e-3)')
    p.add_argument('--warmup_steps',type=int,   default=2000,  help='LR warmup steps (default 2000)')
    p.add_argument('--batch_size',  type=int,   default=256,   help='Batch size (default 256)')

    # Train lengths
    p.add_argument('--train_len_lo', type=int, default=3,  help='Min train seq length (default 3)')
    p.add_argument('--train_len_hi', type=int, default=40, help='Max train seq length (default 40)')

    # Eval
    p.add_argument('--context_length',           type=int, default=256,
                   help='Max eval seq length (default 256)')
    p.add_argument('--n_eval_seqs_per_bucket',   type=int, default=256,
                   help='Total eval sequences per length bucket (default 256)')
    p.add_argument('--eval_lengths_per_bucket',  type=int, default=8,
                   help='Number of distinct eval lengths sampled per bucket (default 8)')

    # Seeds
    p.add_argument('--seeds', type=int, nargs='+', default=[0, 1, 2],
                   help='Seeds to sweep (default: 0 1 2)')

    # Output
    p.add_argument('--out_dir', type=str,
                   default=str(_PROBE_DIR / 'outputs'),
                   help='Output directory for CSV + verdict JSON')

    # Flags
    p.add_argument('--smoke', action='store_true',
                   help='Smoke mode: steps=200, batch=16, seeds=[0], train_len 3-20, eval short')
    p.add_argument('--dummy', action='store_true',
                   help=(
                       'Dummy mode: replace ALL arms with CPU-runnable PyTorch causal mixer. '
                       'No FLA/CUDA needed. Validates plumbing (task gen + training loop + CSV/JSON). '
                       'Model will NOT solve parity at OOD lengths — that is expected.'
                   ))
    p.add_argument('--cpu',   action='store_true', help='Force CPU (debug only)')
    p.add_argument('--log_every', type=int, default=500, help='Log every N steps (default 500)')

    return p.parse_args()


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    args = parse_args()

    # Validate arms
    valid_arms = {'gla', 'gdn2', 'gdn1', 'gdn1_neg', 'deltanet_neg', 'deltaproduct'}
    for arm in args.arms:
        if arm not in valid_arms:
            raise ValueError(f"Unknown arm: {arm!r}. Valid: {sorted(valid_arms)}")

    # S3 task guard
    if args.task == 's3':
        print("[parity_probe] WARNING: s3 task raises NotImplementedError — "
              "S3 generator table not yet implemented. Use --task parity.", file=sys.stderr)

    # Smoke mode override
    if args.smoke:
        args.steps               = 200
        args.batch_size          = 16
        args.seeds               = [0]
        args.log_every           = 50
        if args.dummy:
            # CPU smoke: even shorter
            args.train_len_lo            = 3
            args.train_len_hi            = 20
            args.context_length          = 64
            args.n_eval_seqs_per_bucket  = 32
            args.eval_lengths_per_bucket = 4
        else:
            # GPU FLA smoke
            args.train_len_lo            = 3
            args.train_len_hi            = 40
            args.context_length          = 256
            args.n_eval_seqs_per_bucket  = 64
            args.eval_lengths_per_bucket = 4
        print(
            f"[parity_probe] SMOKE MODE: steps={args.steps} batch={args.batch_size} "
            f"seeds={args.seeds} train_len=[{args.train_len_lo},{args.train_len_hi}] "
            f"dummy={args.dummy}"
        )

    # Device
    if args.cpu or (args.dummy and not torch.cuda.is_available()):
        device = torch.device('cpu')
    elif args.dummy:
        device = torch.device('cpu')  # dummy always CPU
    elif torch.cuda.is_available():
        device = torch.device('cuda')
    else:
        device = torch.device('cpu')
        if not args.dummy:
            print("[parity_probe] WARNING: No CUDA found. FLA arms require GPU. "
                  "Use --dummy for CPU plumbing test.", file=sys.stderr)
    print(f"[parity_probe] device={device} dummy={args.dummy} task={args.task}")

    # Capacity report
    head_dim = args.d_model // args.num_heads
    if args.head_dim != head_dim:
        print(
            f"[parity_probe] WARNING: --head_dim={args.head_dim} != "
            f"d_model/num_heads={head_dim}. "
            f"Using --head_dim={args.head_dim} as specified."
        )
    state_cap = args.num_heads * args.head_dim * args.head_dim
    print(
        f"[parity_probe] Capacity: num_heads={args.num_heads} × "
        f"head_dim={args.head_dim}² = {state_cap} (all arms equal)"
    )

    # Output setup
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix  = '_dummy' if args.dummy else ''
    csv_path     = out_dir / f'parity_{args.task}{suffix}_results.csv'
    verdict_path = out_dir / f'parity_{args.task}{suffix}_verdict.json'

    fieldnames = [
        'arm', 'task', 'seed', 'd_model', 'num_heads', 'head_dim', 'n_layers',
        'steps', 'lr', 'dummy',
        'long_acc_128_256', 'bucket_40_64', 'bucket_64_128', 'bucket_128_256',
    ]
    csv_exists = csv_path.exists()
    done_keys: set = set()
    if csv_exists:
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                done_keys.add((row['arm'], row['task'], int(row['seed'])))
        print(f"[parity_probe] Found {len(done_keys)} existing results, will skip.")

    fout        = open(csv_path, 'a', newline='', encoding='utf-8')
    writer_csv  = csv.DictWriter(fout, fieldnames=fieldnames)
    if not csv_exists:
        writer_csv.writeheader()
        fout.flush()

    total_configs = len(args.arms) * len(args.seeds)
    done_count = 0
    skipped    = 0

    for arm in args.arms:
        for seed in args.seeds:
            key = (arm, args.task, seed)
            if key in done_keys:
                skipped += 1
                continue

            done_count += 1
            print(
                f"\n[parity_probe] [{done_count}/{total_configs - skipped}] "
                f"arm={arm} task={args.task} seed={seed}"
            )

            result = train_one_arm(
                arm_name=arm,
                task=args.task,
                seed=seed,
                d_model=args.d_model,
                num_heads=args.num_heads,
                head_dim=args.head_dim,
                n_layers=args.n_layers,
                steps=args.steps,
                lr=args.lr,
                warmup_steps=args.warmup_steps,
                batch_size=args.batch_size,
                train_len_lo=args.train_len_lo,
                train_len_hi=args.train_len_hi,
                n_eval_seqs_per_bucket=args.n_eval_seqs_per_bucket,
                eval_lengths_per_bucket=args.eval_lengths_per_bucket,
                context_length=args.context_length,
                device=device,
                dummy=args.dummy,
                log_every=args.log_every,
            )

            writer_csv.writerow(result)
            fout.flush()
            print(
                f"  -> long_acc(128-256)={result['long_acc_128_256']:.4f} | "
                f"40-64={result['bucket_40_64']:.4f} | "
                f"64-128={result['bucket_64_128']:.4f}"
            )

    fout.close()
    print(f"\n[parity_probe] Sweep done. Results: {csv_path}")

    # Verdict
    verdict = compute_verdict(csv_path, task=args.task)
    with open(verdict_path, 'w', encoding='utf-8') as f:
        json.dump(verdict, f, indent=2)

    print(f"\n[parity_probe] === VERDICT ===")
    print(f"  Task:         {args.task}")
    print(f"  Live arms:    {verdict.get('live_arms', [])}")
    print(f"  Dead arms:    {verdict.get('dead_arms', [])}")
    print(f"  GLA diagonal fail (≈0.5): {verdict.get('gla_diagonal_fail')}")
    print(f"  🔴-2 GDN-2:   {verdict.get('red2_verdict')}")
    print(f"  Verdict JSON: {verdict_path}")


if __name__ == '__main__':
    main()
