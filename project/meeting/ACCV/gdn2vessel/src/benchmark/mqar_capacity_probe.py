"""
MQAR Capacity Probe — Layer 2 of Route-2 Budget (PREREG 2026-06-21)
====================================================================
Synthetic associative-recall experiment: GDN-2 (A2, delta+gate+stateful)
vs GLA (gate+stateful, NO delta) vs LinearAttn (A1', stateless, no gate, no delta).
Full 2×2 factorial: stateful × delta.

Judgement: PREREG thresholds in reference/ROUTE2_BUDGET_PREREG.md
  - LIVE: exists n in {16,32,64} s.t. acc_gdn2 - acc_la > 0.15
           AND acc_gdn2 - acc_gla > 0.15
           AND acc_gdn2 > 0.5 AND acc_la < 0.5 AND seed std < 0.05
  - DEAD: gap < 0.15 everywhere or conditions fail for all n in {16,32,64}
  - SANITY gate: n=4 all three arms must reach acc > 0.90

Architecture (VLA arXiv 2605.11196 §5.1/§6.4; 2-layer backbone):
  Each layer = [mixer + FFN], pre-norm residual:
    x = x + mixer(LN(x))    [FLA layers have NO internal residual]
    x = x + FFN(LN(x))
  FFN = Linear(d→4d) + GELU + Linear(4d→d).

Three arms (all use FLA official CUDA layers):
  gdn2        — FLA GatedDeltaNet2  (A2: delta+gate+stateful)  [fla/layers/gdn2.py]
  gla         — FLA GatedLinearAttention (gate+stateful, no delta)  [fla/layers/gla.py]
  linear_attn — FLA LinearAttention (A1': stateless, no gate, no delta) [fla/layers/linear_attn.py]

Capacity parity (proven equal, hidden=128, num_heads=2, head_dim=64, expand_v=1.0, expand_k=1.0):
  GDN2:     head_k_dim=64,  head_v_dim=64*1.0=64  → state = 2×64×64 = 8192
  GLA:      key_dim=128*1.0=128, head_k_dim=128//2=64, head_v_dim=128//2=64 → state = 2×64×64 = 8192
  LinAttn:  key_dim=128*1.0=128, head_k_dim=128//2=64, head_v_dim=128//2=64 → state = 2×64×64 = 8192
  All equal → judgment clean. ✓

GLA params: expand_k=1.0 (NOT default 0.5), use_short_conv=False, use_output_gate=False.
  expand_k default is 0.5 → head_k_dim=32 (NOT 64) → capacity halved → WRONG.
  use_output_gate=False → remove sigmoid output gate → isolates stateful accumulation only.

LinearAttention params: expand_k=1.0, expand_v=1.0, feature_map='elu'.
  Default feature_map='elementwise_product' uses Hadamard/productmap; ELU+1 is
  standard stateless baseline in VLA/Zoology for capacity comparison.

GDN2 params: use_short_conv=False (VLA omits conv for clean comparison), expand_v=1.0.

FLA forward returns (o, None, past_key_values); adapters unpack o only.
FLA layers have internal o_norm + o_proj; NO residual inside → backbone uses standard
pre-norm residual (has_internal_residual=False).

Training config (VLA Table 3 / Zoology 2312.04927):
  steps=8000, lr=3e-4, cosine decay + 10% warmup, AdamW wd=1e-2, β=(0.9,0.999),
  grad_clip=1.0, batch=64, V=8192.

n_kv sweep: {4,8,16,32,64}, T=256 (n_kv=64 needs T>=193, 256 covers all).
  n_kv=96 removed: T=256 needs T>=289 (3*96+1) → assertion fails.

NO scipy.stats (OMP red-line). All stats in numpy.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# ---------------------------------------------------------------------------
# Project path resolution
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_SRC  = _HERE.parent.parent       # project/src/
_ROOT = _SRC.parent               # project root
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ---------------------------------------------------------------------------
# FLA availability check
# ---------------------------------------------------------------------------
try:
    import fla  # noqa: F401
    _FLA_AVAILABLE = True
except ImportError:
    _FLA_AVAILABLE = False
    print("[mqar_probe] fla not found — FLA adapters will raise ImportError at construction. "
          "Full sweep must run on HPC with fla installed.", file=sys.stderr)

# ---------------------------------------------------------------------------
# FLA layer imports (guarded — only populated when fla is available)
# ---------------------------------------------------------------------------
_FLAGatedDeltaNet2        = None
_FLAGatedLinearAttention  = None
_FLALinearAttention       = None

if _FLA_AVAILABLE:
    from fla.layers import GatedDeltaNet2       as _FLAGatedDeltaNet2       # noqa: E402
    from fla.layers import GatedLinearAttention  as _FLAGatedLinearAttention  # noqa: E402
    from fla.layers import LinearAttention       as _FLALinearAttention       # noqa: E402


# ---------------------------------------------------------------------------
# Adapter base class
# ---------------------------------------------------------------------------

class _FLAAdapterBase(nn.Module):
    """
    Base for FLA layer adapters.

    FLA layers:
      - forward(hidden_states: (B,T,H), ...) → (o: (B,T,H), None, past_kv)
      - contain internal o_norm + o_proj; NO residual/LN inside
    MQARBackbone uses standard pre-norm+residual (has_internal_residual=False).
    """

    # MQARBackbone reads this: False → backbone does x = x + mixer(LN(x))
    has_internal_residual: bool = False

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B, T, hidden_size) → (B, T, hidden_size). Unpacks tuple from FLA."""
        o, _, _ = self.layer(x)
        return o


# ---------------------------------------------------------------------------
# A2 adapter: FLA GatedDeltaNet2 (delta+gate+stateful)
# ---------------------------------------------------------------------------

class GDN2FLAAdapter(_FLAAdapterBase):
    """
    A2 arm: FLA GatedDeltaNet2.

    Source: fla/layers/gdn2.py — GatedDeltaNet2.__init__
    Params (capacity proof in module docstring):
        hidden_size=128, num_heads=2, head_dim=64, expand_v=1.0
        use_short_conv=False  (VLA omits conv for clean mechanism isolation)
        mode='chunk'          (required for training per FLA source assertion)

    State capacity: num_heads × head_k_dim × head_v_dim = 2 × 64 × 64 = 8192
    """

    def __init__(self, hidden_size: int = 128, num_heads: int = 2, head_dim: int = 64):
        super().__init__()
        if not _FLA_AVAILABLE:
            raise ImportError(
                "GDN2FLAAdapter requires `fla` (flash-linear-attention) with CUDA. "
                "Run on HPC: pip install flash-linear-attention"
            )
        # GatedDeltaNet2 signature (fla/layers/gdn2.py):
        #   hidden_size, expand_v=1.0, head_dim=128, num_heads=16,
        #   mode='chunk', use_short_conv=True, ...
        self.layer = _FLAGatedDeltaNet2(
            hidden_size=hidden_size,
            num_heads=num_heads,
            head_dim=head_dim,
            expand_v=1.0,           # head_v_dim = head_dim * expand_v = 64
            use_short_conv=False,   # VLA: omit conv for clean comparison
            mode='chunk',           # training mode (FLA asserts chunk-only in train)
        )


# ---------------------------------------------------------------------------
# GLA adapter: FLA GatedLinearAttention (gate+stateful, NO delta)
# ---------------------------------------------------------------------------

class GLAFLAAdapter(_FLAAdapterBase):
    """
    GLA arm: FLA GatedLinearAttention.

    Source: fla/layers/gla.py — GatedLinearAttention.__init__
    Key params for capacity parity:
        hidden_size=128, num_heads=2
        expand_k=1.0   ← CRITICAL: default is 0.5 → key_dim=64 → head_k_dim=32 (WRONG)
                          expand_k=1.0 → key_dim=128 → head_k_dim=128//2=64 ✓
        expand_v=1.0   → value_dim=128 → head_v_dim=128//2=64 ✓
        use_short_conv=False  (VLA: no conv)
        use_output_gate=False (isolate stateful accumulation, remove sigmoid gate)
        mode='chunk'

    State capacity: num_heads × head_k_dim × head_v_dim = 2 × 64 × 64 = 8192 ✓
    """

    def __init__(self, hidden_size: int = 128, num_heads: int = 2):
        super().__init__()
        if not _FLA_AVAILABLE:
            raise ImportError(
                "GLAFLAAdapter requires `fla` (flash-linear-attention) with CUDA. "
                "Run on HPC: pip install flash-linear-attention"
            )
        # GatedLinearAttention signature (fla/layers/gla.py):
        #   mode='chunk', hidden_size=1024, expand_k=0.5, expand_v=1.0,
        #   num_heads=4, use_short_conv=False, use_output_gate=True, ...
        self.layer = _FLAGatedLinearAttention(
            hidden_size=hidden_size,
            num_heads=num_heads,
            expand_k=1.0,           # CRITICAL: NOT default 0.5 (would give head_k_dim=32)
            expand_v=1.0,           # head_v_dim = value_dim // num_heads = 128//2 = 64
            use_short_conv=False,
            use_output_gate=False,  # remove output gate → isolate pure stateful accumulation
            mode='chunk',
        )


# ---------------------------------------------------------------------------
# A1' adapter: FLA LinearAttention (stateless, no gate, no delta)
# ---------------------------------------------------------------------------

class LinearAttnFLAAdapter(_FLAAdapterBase):
    """
    A1' arm: FLA LinearAttention (stateless baseline).

    Source: fla/layers/linear_attn.py — LinearAttention.__init__
    Key params for capacity parity:
        hidden_size=128, num_heads=2
        expand_k=1.0 → key_dim=128 → head_k_dim=128//2=64 ✓
        expand_v=1.0 → value_dim=128 → head_v_dim=128//2=64 ✓
        feature_map='elu'  (ELU+1 kernel, standard stateless baseline in VLA/Zoology)
        mode='chunk'

    State capacity (if it were stateful — it's stateless but projection is equal):
        num_heads × head_k_dim × head_v_dim = 2 × 64 × 64 = 8192 ✓

    No short conv, no output gate (LinearAttention has neither by design).
    """

    def __init__(self, hidden_size: int = 128, num_heads: int = 2):
        super().__init__()
        if not _FLA_AVAILABLE:
            raise ImportError(
                "LinearAttnFLAAdapter requires `fla` (flash-linear-attention) with CUDA. "
                "Run on HPC: pip install flash-linear-attention"
            )
        # LinearAttention signature (fla/layers/linear_attn.py):
        #   mode='chunk', hidden_size=1024, expand_k=1.0, expand_v=1.0,
        #   num_heads=8, feature_map='elementwise_product', ...
        self.layer = _FLALinearAttention(
            hidden_size=hidden_size,
            num_heads=num_heads,
            expand_k=1.0,
            expand_v=1.0,
            feature_map='elu',      # ELU+1, standard stateless baseline (VLA/Zoology)
            mode='chunk',
        )


# ---------------------------------------------------------------------------
# FFN block (shared between layers, same for all arms)
# ---------------------------------------------------------------------------

class FFN(nn.Module):
    """
    Two-layer feed-forward network with GELU activation.
    FFN(x) = Linear(GELU(Linear(x, 4*d)), d)
    Standard transformer FFN expansion ratio = 4 (VLA / Based / Zoology).
    No bias to match typical no-bias attention convention.
    """

    def __init__(self, d_model: int, expand: int = 4):
        super().__init__()
        self.fc1 = nn.Linear(d_model, d_model * expand, bias=False)
        self.fc2 = nn.Linear(d_model * expand, d_model, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B, T, d_model) → (B, T, d_model)"""
        return self.fc2(F.gelu(self.fc1(x)))


# ---------------------------------------------------------------------------
# 2-layer backbone (VLA §5.1 original setup)
# ---------------------------------------------------------------------------

class MQARBackbone(nn.Module):
    """
    2-layer backbone following VLA arXiv 2605.11196 §5.1/§6.4.

    Each layer applies standard pre-norm residual:
        x = x + mixer(LN(x))      # pre-norm residual for mixer
        x = x + FFN(LN(x))        # pre-norm residual for FFN

    FLA layers (GDN2FLAAdapter / GLAFLAAdapter / LinearAttnFLAAdapter) all have
    has_internal_residual=False — they output only the transformed value, NOT a
    residual result. The backbone applies the residual connection here.

    All arms use identical MQARBackbone; only the mixer modules differ.
    Embedding / LN / FFN / head are structurally identical across arms.
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
        self.d_model = d_model

        # Pre-norm LayerNorms: 2 per layer (one before mixer, one before FFN)
        self.mixer_norms = nn.ModuleList([nn.LayerNorm(d_model) for _ in range(n_layers)])
        self.ffn_norms   = nn.ModuleList([nn.LayerNorm(d_model) for _ in range(n_layers)])

        # Mixer modules (arm-specific)
        self.mixers = nn.ModuleList(mixers)

        # FFN modules (shared structure; weights per-instance)
        self.ffns = nn.ModuleList([FFN(d_model, expand=ffn_expand) for _ in range(n_layers)])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: (B, T, d_model) → (B, T, d_model)

        Standard pre-norm residual for both mixer and FFN.
        FLA layers do NOT have internal residual (has_internal_residual=False),
        so the backbone always applies x = x + mixer(LN(x)).
        """
        for i in range(self.n_layers):
            mixer = self.mixers[i]
            if getattr(mixer, 'has_internal_residual', False):
                # Legacy compat: old stub adapters had internal residual+LN.
                # Should not be hit with the new FLA adapters.
                x = mixer(x)
            else:
                # Standard pre-norm residual (FLA layers: output is delta only, no norm/residual)
                x = x + mixer(self.mixer_norms[i](x))
            x = x + self.ffns[i](self.ffn_norms[i](x))
        return x


# ---------------------------------------------------------------------------
# MQAR sequence generator
# ---------------------------------------------------------------------------

def build_mqar_batch(
    batch_size: int,
    T: int,
    n_kv: int,
    V: int,
    device: torch.device,
    seed: Optional[int] = None,
    d_head: int = 64,
    noise_sigma: float = 0.0,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """
    Build a batch of MQAR sequences (online, no stored dataset).

    Layout (Zoology arXiv 2312.04927 convention):
      - prefix: 2*n_kv tokens — n_kv (key, value) pairs interleaved
        [k0, v0, k1, v1, ..., k_{n_kv-1}, v_{n_kv-1}]
      - query zone: T - 2*n_kv tokens — contains n_kv query tokens
        placed at random positions among noise tokens.

    Token ranges:
      keys   ∈ [1, V//2)
      values ∈ [V//2, V)
      noise  ∈ {0}

    Returns:
      seq_ids:     (B, T)   long
      targets:     (B, T)   long — value id at query positions, -100 elsewhere
      query_mask:  (B, T)   bool — True at query positions
    """
    rng = np.random.default_rng(seed)
    B = batch_size

    key_pool   = np.arange(1, V // 2, dtype=np.int64)
    value_pool = np.arange(V // 2, V, dtype=np.int64)
    key_ids   = np.stack([rng.choice(key_pool,   size=n_kv, replace=False) for _ in range(B)])
    value_ids = np.stack([rng.choice(value_pool, size=n_kv, replace=False) for _ in range(B)])

    prefix_len = 2 * n_kv
    suffix_len = T - prefix_len
    assert suffix_len >= n_kv, (
        f"T={T} too short for n_kv={n_kv}: need at least {prefix_len + n_kv} tokens"
    )

    seq_ids    = np.zeros((B, T), dtype=np.int64)
    targets    = np.full((B, T), -100, dtype=np.int64)
    query_mask = np.zeros((B, T), dtype=bool)

    for b in range(B):
        for i in range(n_kv):
            seq_ids[b, 2 * i]     = key_ids[b, i]
            seq_ids[b, 2 * i + 1] = value_ids[b, i]

        q_positions = rng.choice(suffix_len, size=n_kv, replace=False)
        q_positions_sorted = np.sort(q_positions)
        query_perm = rng.permutation(n_kv)

        for idx, (qpos, kv_idx) in enumerate(
                zip(q_positions_sorted, query_perm)):
            abs_pos = prefix_len + int(qpos)
            seq_ids[b, abs_pos]    = key_ids[b, kv_idx]
            targets[b, abs_pos]    = value_ids[b, kv_idx]
            query_mask[b, abs_pos] = True

    seq_ids_t    = torch.from_numpy(seq_ids).to(device)
    targets_t    = torch.from_numpy(targets).to(device)
    query_mask_t = torch.from_numpy(query_mask).to(device)

    return seq_ids_t, targets_t, query_mask_t


# ---------------------------------------------------------------------------
# MQAR model
# ---------------------------------------------------------------------------

class MQARModel(nn.Module):
    """
    Embedding → 2-layer backbone → classifier head.

    Structure (VLA §5.1):
      - nn.Embedding(V, d_model)
      - MQARBackbone(2 layers of [mixer + FFN], pre-norm residual)
      - nn.Linear(d_model, V) with weight tying to embedding

    Weight tying (VLA 2605.11196 "weight tying ... shared identically"):
      head.weight = embed.weight
      Prevents copy-recall degeneration with large vocab V=8192.
    """

    def __init__(
        self,
        V: int,
        d_model: int,
        backbone: MQARBackbone,
    ):
        super().__init__()
        self.V       = V
        self.d_model = d_model

        self.embed = nn.Embedding(V, d_model)
        self.backbone = backbone
        self.head = nn.Linear(d_model, V)
        # Weight tying
        self.head.weight = self.embed.weight

    def forward(self, seq_ids: torch.Tensor) -> torch.Tensor:
        """seq_ids: (B, T) long → logits: (B, T, V)"""
        x = self.embed(seq_ids)   # (B, T, d_model)
        x = self.backbone(x)      # (B, T, d_model)
        return self.head(x)       # (B, T, V)


# ---------------------------------------------------------------------------
# Cosine LR scheduler with warmup (pure PyTorch, no external dep)
# ---------------------------------------------------------------------------

class CosineWarmupScheduler:
    """
    Linear warmup + cosine annealing.
    VLA Table 3: warmup = 10% of total steps, then cosine to lr_min=0.
    """

    def __init__(self, optimizer: torch.optim.Optimizer, total_steps: int,
                 warmup_frac: float = 0.1, lr: float = 3e-4):
        self.optimizer   = optimizer
        self.total_steps = total_steps
        self.warmup_steps = max(1, int(total_steps * warmup_frac))
        self.base_lr     = lr

    def step(self, step: int) -> None:
        if step < self.warmup_steps:
            lr = self.base_lr * step / self.warmup_steps
        else:
            progress = (step - self.warmup_steps) / max(1, self.total_steps - self.warmup_steps)
            lr = self.base_lr * 0.5 * (1.0 + math.cos(math.pi * progress))
        for pg in self.optimizer.param_groups:
            pg['lr'] = lr


# ---------------------------------------------------------------------------
# Training loop (single arm, single config)
# ---------------------------------------------------------------------------

def train_one_config(
    arm: str,
    n_kv: int,
    d_head: int,
    lr: float,
    seed: int,
    T: int,
    V: int,
    steps: int,
    device: torch.device,
    batch_size: int = 64,
    d_model: int = 128,
    num_heads: int = 2,
    log_every: int = 200,
    n_layers: int = 2,
) -> Dict:
    """
    Train one (arm, n_kv, lr, seed) config. Returns result dict.

    arm: 'gdn2' | 'gla' | 'linear_attn'

    Training config (VLA Table 3):
      AdamW lr=3e-4, wd=1e-2, β=(0.9,0.999), grad_clip=1.0, batch=64,
      cosine decay + 10% warmup, steps=8000.

    All three arms use FLA official CUDA layers. Requires fla installed (HPC).
    """
    torch.manual_seed(seed)
    np.random.seed(seed)

    # Build n_layers mixer instances for the backbone
    # hidden_size = d_model = 128, num_heads = 2, head_dim = 64
    # → capacity = 2 × 64 × 64 = 8192 for ALL three arms
    if arm == 'gdn2':
        # A2: GatedDeltaNet2, delta+gate+stateful
        # head_k_dim=64, head_v_dim=64*1.0=64 → state 8192
        mixers = [
            GDN2FLAAdapter(hidden_size=d_model, num_heads=num_heads, head_dim=d_head)
            for _ in range(n_layers)
        ]
    elif arm == 'gla':
        # GLA: GatedLinearAttention, gate+stateful, NO delta
        # expand_k=1.0 → key_dim=128 → head_k_dim=64; head_v_dim=64 → state 8192
        mixers = [
            GLAFLAAdapter(hidden_size=d_model, num_heads=num_heads)
            for _ in range(n_layers)
        ]
    elif arm == 'linear_attn':
        # A1': LinearAttention, stateless, ELU+1
        # expand_k=1.0 → key_dim=128 → head_k_dim=64; head_v_dim=64 → state 8192
        mixers = [
            LinearAttnFLAAdapter(hidden_size=d_model, num_heads=num_heads)
            for _ in range(n_layers)
        ]
    else:
        raise ValueError(
            f"Unknown arm: {arm!r}. Valid: 'gdn2', 'gla', 'linear_attn'"
        )

    backbone = MQARBackbone(d_model=d_model, mixers=mixers, n_layers=n_layers)
    model = MQARModel(V=V, d_model=d_model, backbone=backbone).to(device)

    # AdamW: VLA Table 3 — wd=1e-2, β=(0.9,0.999)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=lr,
        weight_decay=1e-2,
        betas=(0.9, 0.999),
    )
    scheduler = CosineWarmupScheduler(optimizer, total_steps=steps, warmup_frac=0.1, lr=lr)

    best_acc = 0.0

    for step in range(1, steps + 1):
        scheduler.step(step)
        model.train()
        seq_ids, targets, query_mask = build_mqar_batch(
            batch_size=batch_size, T=T, n_kv=n_kv, V=V,
            device=device, seed=None,
            d_head=d_head,
        )

        logits = model(seq_ids)   # (B, T, V)

        B, Tlen, Vsize = logits.shape
        loss = F.cross_entropy(
            logits.reshape(B * Tlen, Vsize),
            targets.reshape(B * Tlen),
            ignore_index=-100,
        )

        optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

        if step % log_every == 0 or step == steps:
            model.eval()
            with torch.no_grad():
                seq_ids_e, targets_e, query_mask_e = build_mqar_batch(
                    batch_size=batch_size * 2, T=T, n_kv=n_kv, V=V,
                    device=device, seed=step * 997 + seed,
                    d_head=d_head,
                )
                logits_e = model(seq_ids_e)
                pred_e = logits_e.argmax(dim=-1)
                correct = (pred_e == targets_e) & query_mask_e
                n_queries = query_mask_e.sum().item()
                acc = correct.sum().item() / max(n_queries, 1)

            if acc > best_acc:
                best_acc = acc

            if step % (log_every * 5) == 0 or step == steps:
                print(f"  [{arm}|n={n_kv}|lr={lr:.0e}|seed={seed}] "
                      f"step={step}/{steps} loss={loss.item():.4f} "
                      f"acc={acc:.4f} best={best_acc:.4f}")

    return {
        'arm': arm,
        'n_kv': n_kv,
        'd_head': d_head,
        'lr': lr,
        'seed': seed,
        'final_acc': float(best_acc),
        'steps': steps,
        'converged': int(best_acc > 0.9),
    }


# ---------------------------------------------------------------------------
# Verdict computation (pure numpy, no scipy)
# ---------------------------------------------------------------------------

def compute_verdict(csv_path: Path, prereg_delta: float = 0.15) -> Dict:
    """
    Read sweep CSV, compute per-n_kv mean±std across seeds, judge LIVE/DEAD.

    PREREG thresholds (ROUTE2_BUDGET_PREREG.md, 2026-06-21 dual-gap):
      LIVE: sanity_ok AND exists n in {16,32,64} where ALL hold:
        (a)  acc_gdn2 - acc_la  > 0.15
        (a') acc_gdn2 - acc_gla > 0.15  (mechanism specificity)
        (b)  acc_gdn2 > 0.5
        (c)  acc_la   < 0.5
        (d)  std < 0.05 for ALL THREE arms
      DEAD: otherwise
      SANITY (n=4): gdn2, gla, linear_attn ALL mean > 0.90
    """
    rows = []
    with open(csv_path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                'arm':       row['arm'],
                'n_kv':      int(row['n_kv']),
                'd_head':    int(row['d_head']),
                'lr':        float(row['lr']),
                'seed':      int(row['seed']),
                'final_acc': float(row['final_acc']),
                'steps':     int(row['steps']),
                'converged': int(row['converged']),
            })

    from collections import defaultdict
    best = defaultdict(lambda: -1.0)
    for r in rows:
        key = (r['arm'], r['n_kv'], r['seed'])
        if r['final_acc'] > best[key]:
            best[key] = r['final_acc']

    by_arm_n = defaultdict(lambda: defaultdict(list))
    for (arm, n_kv, seed), acc in best.items():
        by_arm_n[arm][n_kv].append(acc)

    stats = {}
    for arm, n_dict in by_arm_n.items():
        stats[arm] = {}
        for n, accs in n_dict.items():
            arr = np.array(accs, dtype=float)
            stats[arm][n] = {
                'mean':    float(np.mean(arr)),
                'std':     float(np.std(arr, ddof=1) if len(arr) > 1 else 0.0),
                'n_seeds': len(arr),
                'accs':    [float(a) for a in arr],
            }

    # Sanity gate: n=4, three arms all mean > 0.9
    sanity_ok = True
    sanity_detail = {}
    for arm in ('gdn2', 'gla', 'linear_attn'):
        if arm in stats and 4 in stats[arm]:
            s = stats[arm][4]
            sanity_detail[arm] = {'mean': s['mean'], 'pass': bool(s['mean'] > 0.9)}
            if s['mean'] <= 0.9:
                sanity_ok = False
        else:
            sanity_detail[arm] = {'mean': None, 'pass': False}
            sanity_ok = False

    all_n = sorted(set(
        list(stats.get('gdn2', {}).keys()) +
        list(stats.get('gla', {}).keys()) +
        list(stats.get('linear_attn', {}).keys())
    ))
    gap_table = {}
    live_windows = []
    delta_nonspecific_ns = []

    for n in all_n:
        g2  = stats.get('gdn2', {}).get(n, None)
        gla = stats.get('gla', {}).get(n, None)
        la  = stats.get('linear_attn', {}).get(n, None)

        entry = {
            'acc_gdn2': float(g2['mean'])  if g2  is not None else None,
            'std_gdn2': float(g2['std'])   if g2  is not None else None,
            'acc_gla':  float(gla['mean']) if gla is not None else None,
            'std_gla':  float(gla['std'])  if gla is not None else None,
            'acc_la':   float(la['mean'])  if la  is not None else None,
            'std_la':   float(la['std'])   if la  is not None else None,
            'gap_la':   None,
            'gap_gla':  None,
        }
        if g2 is not None and la is not None:
            entry['gap_la'] = float(g2['mean'] - la['mean'])
        if g2 is not None and gla is not None:
            entry['gap_gla'] = float(g2['mean'] - gla['mean'])
        gap_table[n] = entry

        if n in (16, 32, 64) and g2 is not None and gla is not None and la is not None:
            gap_la  = entry['gap_la']
            gap_gla = entry['gap_gla']

            cond_gap_la  = gap_la  > prereg_delta
            cond_gap_gla = gap_gla > prereg_delta
            cond_g2      = g2['mean']  > 0.5
            cond_la_lt   = la['mean']  < 0.5
            cond_std     = (g2['std'] < 0.05 and gla['std'] < 0.05 and la['std'] < 0.05)

            all_live = cond_gap_la and cond_gap_gla and cond_g2 and cond_la_lt and cond_std
            if all_live:
                live_windows.append({
                    'n_kv':                  n,
                    'gap_la':                float(gap_la),
                    'gap_gla':               float(gap_gla),
                    'acc_gdn2':              float(g2['mean']),
                    'acc_gla':               float(gla['mean']),
                    'acc_la':                float(la['mean']),
                    'std_gdn2':              float(g2['std']),
                    'std_gla':               float(gla['std']),
                    'std_la':                float(la['std']),
                    'cond_gap_la':           cond_gap_la,
                    'cond_gap_gla':          cond_gap_gla,
                    'cond_acc_gdn2_gt_05':   cond_g2,
                    'cond_acc_la_lt_05':     cond_la_lt,
                    'cond_std_lt_005':       cond_std,
                })

            if cond_gap_la and not cond_gap_gla:
                delta_nonspecific_ns.append(n)

    verdict = 'LIVE' if (sanity_ok and len(live_windows) > 0) else 'DEAD'
    if not sanity_ok:
        verdict = 'DEAD_SANITY_FAIL'

    delta_nonspecific = len(delta_nonspecific_ns) > 0 and verdict != 'LIVE'
    delta_nonspecific_msg = (
        'acc_gdn2 ≈ acc_gla at n={}: gap(gdn2-gla) ≤ {:.2f}; '
        'delta 非特异——仅有状态效应，headline「delta 关联记忆」塌，回退路1/benchmark-led'.format(
            delta_nonspecific_ns, prereg_delta
        ) if delta_nonspecific else None
    )

    return {
        'verdict':               verdict,
        'prereg_delta':          prereg_delta,
        'prereg_file':           'reference/ROUTE2_BUDGET_PREREG.md',
        'sanity_gate': {
            'pass':         sanity_ok,
            'detail':       sanity_detail,
            'threshold':    0.9,
            'arms_checked': ['gdn2', 'gla', 'linear_attn'],
        },
        'live_windows':          live_windows,
        'delta_nonspecific':     delta_nonspecific,
        'delta_nonspecific_ns':  delta_nonspecific_ns,
        'delta_nonspecific_msg': delta_nonspecific_msg,
        'gap_table':             {str(k): v for k, v in gap_table.items()},
        'stats': {
            arm: {str(n): s for n, s in nd.items()}
            for arm, nd in stats.items()
        },
        'random_baseline': None,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='MQAR Capacity Probe — Route 2 Layer 2')
    p.add_argument('--n_kv', type=int, nargs='+',
                   default=[4, 8, 16, 32, 64],
                   help='n_kv values to sweep (default: 4 8 16 32 64; T=256 covers all)')
    p.add_argument('--d_head', type=int, default=64,
                   help='Head dim = 64 (capacity anchor; all three arms use head_k_dim=64)')
    p.add_argument('--lr', type=float, nargs='+',
                   default=[3e-4],
                   help='Learning rate (VLA Table 3: single lr=3e-4)')
    p.add_argument('--seeds', type=int, nargs='+', default=[0, 1, 2])
    p.add_argument('--T', type=int, default=256,
                   help='Sequence length (T=256 covers n_kv<=64; Zoology upper bound)')
    p.add_argument('--vocab', type=int, default=8192,
                   help='Vocabulary size V (VLA §5.1: 8192)')
    p.add_argument('--steps', type=int, default=8000,
                   help='Training steps per config (VLA Table 3 alignment: 8000)')
    p.add_argument('--n_layers', type=int, default=2,
                   help='Backbone layers (VLA §5.1: 2)')
    p.add_argument('--batch_size', type=int, default=64,
                   help='Batch size (VLA Table 3: 64)')
    p.add_argument('--d_model', type=int, default=128,
                   help='Token embedding dimension (d_model=128, d_head=64, num_heads=2)')
    p.add_argument('--num_heads', type=int, default=2,
                   help='Number of heads (num_heads=2; head_k_dim=d_model//num_heads=64)')
    p.add_argument('--smoke', action='store_true',
                   help='Quick smoke test: n_kv=4, 1 seed, 200 steps, batch=8')
    p.add_argument('--out_dir', type=str,
                   default=str(_ROOT / 'outputs' / 'route2_budget'))
    p.add_argument('--cpu', action='store_true', help='Force CPU (smoke/debug only)')
    p.add_argument('--arms', type=str, nargs='+',
                   default=['gdn2', 'gla', 'linear_attn'],
                   help=(
                       'Arms to run. Options: gdn2, gla, linear_attn. '
                       'gdn2        = A2: FLA GatedDeltaNet2 (delta+gate+stateful). '
                       'gla         = FLA GatedLinearAttention (gate+stateful, no delta). '
                       'linear_attn = A1\': FLA LinearAttention (stateless, ELU+1). '
                       'All require fla (flash-linear-attention) on HPC with CUDA.'
                   ))
    p.add_argument('--log_every', type=int, default=200)
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.cpu or not torch.cuda.is_available():
        device = torch.device('cpu')
    else:
        device = torch.device('cuda')
    print(f"[mqar_probe] device={device}")

    if args.smoke:
        args.n_kv      = [4]
        args.lr        = [3e-4]
        args.seeds     = [0]
        args.steps     = 200
        args.batch_size = 8
        print("[mqar_probe] SMOKE MODE: n_kv=[4] lr=[3e-4] seeds=[0] steps=200 batch=8")

    assert args.d_model >= args.d_head, (
        f"d_model={args.d_model} must be >= d_head={args.d_head}"
    )

    # Validate T covers all n_kv (need T >= 3*n_kv+1 for query zone)
    for n in args.n_kv:
        min_T = 3 * n + 1
        assert args.T >= min_T, (
            f"T={args.T} too short for n_kv={n}: need T >= {min_T}"
        )

    # Validate arms
    valid_arms = {'gdn2', 'gla', 'linear_attn'}
    for arm in args.arms:
        if arm not in valid_arms:
            raise ValueError(f"Unknown arm: {arm!r}. Valid: {sorted(valid_arms)}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path     = out_dir / 'mqar_results.csv'
    verdict_path = out_dir / 'mqar_verdict.json'

    random_baseline = 1.0 / (args.vocab // 2)
    print(f"[mqar_probe] random_baseline = {random_baseline:.6f} (=1/(V/2)=1/{args.vocab//2})")
    print(f"[mqar_probe] Capacity proof: all arms state=num_heads({args.num_heads})"
          f"×head_k_dim(64)×head_v_dim(64)=8192 (expand_k=1.0, expand_v=1.0)")

    fieldnames = ['arm', 'n_kv', 'd_head', 'lr', 'seed', 'final_acc', 'steps', 'converged']
    csv_exists = csv_path.exists()
    done_keys = set()
    if csv_exists:
        with open(csv_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                done_keys.add((row['arm'], int(row['n_kv']),
                                float(row['lr']), int(row['seed'])))
        print(f"[mqar_probe] Found {len(done_keys)} existing results, will skip.")

    fout = open(csv_path, 'a', newline='')
    writer_csv = csv.DictWriter(fout, fieldnames=fieldnames)
    if not csv_exists:
        writer_csv.writeheader()
        fout.flush()

    total_configs = len(args.arms) * len(args.n_kv) * len(args.lr) * len(args.seeds)
    done_count = 0
    skipped = 0

    for arm in args.arms:
        for n_kv in args.n_kv:
            for lr in args.lr:
                for seed in args.seeds:
                    key = (arm, n_kv, lr, seed)
                    if key in done_keys:
                        skipped += 1
                        continue

                    done_count += 1
                    print(f"\n[mqar_probe] [{done_count}/{total_configs - skipped}] "
                          f"arm={arm} n_kv={n_kv} d_head={args.d_head} "
                          f"lr={lr:.0e} seed={seed}")

                    result = train_one_config(
                        arm=arm, n_kv=n_kv, d_head=args.d_head,
                        lr=lr, seed=seed, T=args.T, V=args.vocab,
                        steps=args.steps, device=device,
                        batch_size=args.batch_size,
                        d_model=args.d_model,
                        num_heads=args.num_heads,
                        log_every=args.log_every,
                        n_layers=args.n_layers,
                    )

                    writer_csv.writerow(result)
                    fout.flush()
                    print(f"  -> final_acc={result['final_acc']:.4f} "
                          f"converged={result['converged']}")

    fout.close()
    print(f"\n[mqar_probe] Sweep done. Results: {csv_path}")

    verdict = compute_verdict(csv_path, prereg_delta=0.15)
    verdict['random_baseline'] = random_baseline

    with open(verdict_path, 'w') as f:
        json.dump(verdict, f, indent=2)

    print(f"\n[mqar_probe] VERDICT: {verdict['verdict']}")
    print(f"[mqar_probe] Sanity gate (n=4 all arms >0.9): {verdict['sanity_gate']['pass']}")
    if verdict['live_windows']:
        print(f"[mqar_probe] Live windows at n_kv={[w['n_kv'] for w in verdict['live_windows']]}")
    print(f"[mqar_probe] Verdict JSON: {verdict_path}")


if __name__ == '__main__':
    main()
