"""
MQAR Capacity Probe — Layer 2 of Route-2 Budget (PREREG 2026-06-21)
====================================================================
Synthetic associative-recall experiment: GDN-2 (delta-rule, stateful)
vs LinearAttn (ELU+1, stateless) on Multi-Query Associative Recall.
Cross-validation arm: FLA canonical GatedDeltaNet (gdn2_fla) — requires HPC.

Judgement: PREREG thresholds in reference/ROUTE2_BUDGET_PREREG.md
  - LIVE: exists n in {16,32,64} s.t. acc_gdn2 - acc_la > 0.15
           AND acc_gdn2 > 0.5 AND acc_la < 0.5 AND seed std < 0.05
  - DEAD: gap < 0.15 everywhere or GDN-2 never beats acc_la + 0.15 at n<=64
  - SANITY gate: n=4 both arms must reach acc > 0.90

Architecture (2026-06-21 fix — single-layer→2-layer VLA original):
  Ref: VLA arXiv 2605.11196 §5.1/§6.4; Based 2402.18668; Zoology 2312.04927.
  Single-layer backbone cannot solve interleaved MQAR (key and value are
  adjacent tokens; at the value position the model has not yet seen the query,
  so a single-layer stateless head cannot bind k→v across the gap).
  Fix: 2-layer backbone.  Each layer = [mixer + shared FFN], pre-norm residual:
    x = x + mixer(LN(x))
    x = x + FFN(LN(x))
  FFN = Linear(d_model→4*d_model) + GELU + Linear(4*d_model→d_model).
  No short conv for gdn2/linear_attn arms (VLA intentionally omits it).
  gdn2_fla arm uses FLA GatedDeltaNet with use_short_conv=True (canonical config).
  Both arms use identical embedding/LN/FFN/head; only the mixer differs.

Arms:
  gdn2          — our GDN2MemoryModule (delta-rule, FLA-backed on HPC, stub on CPU)
  linear_attn   — LinearAttnModule (ELU+1, stateless baseline)
  gdn2_fla      — FLA canonical GatedDeltaNet (use_short_conv=True, conv_size=4,
                  num_heads=2). REQUIRES fla on HPC. Cross-validation reference arm.
                  This tests the canonical delta-rule with short conv (Zoology MQAR
                  standard) as a robust convergence reference — NOT our decoupled gate.

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
# FLA fallback: when fla is not installed (local CPU env), inject a pure-
# PyTorch gated-delta-rule stub so GDN2MemoryModule can be constructed and
# used for smoke tests.  On HPC (fla installed) this block is never entered.
# ---------------------------------------------------------------------------
def _pytorch_gated_delta_rule_stub(
    q: torch.Tensor,    # (B, T, nh, dh)
    k: torch.Tensor,
    v: torch.Tensor,
    beta: torch.Tensor, # (B, T, nh)
    g: torch.Tensor,    # (B, T, nh) log-decay
    output_final_state: bool = False,
):
    """
    Pure-PyTorch causal gated delta-rule, sequential scan.
    Matches FLA naive_chunk_gated_delta_rule output signature.
    Used when fla is unavailable (CPU smoke / pytest env).
    """
    B, T, nh, dh = q.shape
    device, dtype = q.device, q.dtype
    S = torch.zeros(B, nh, dh, dh, device=device, dtype=dtype)
    o_list = []
    for t in range(T):
        gt = torch.exp(g[:, t, :])                         # (B, nh)
        bt = beta[:, t, :]                                  # (B, nh)
        qt = q[:, t, :, :]                                  # (B, nh, dh)
        kt = k[:, t, :, :]                                  # (B, nh, dh)
        vt = v[:, t, :, :]                                  # (B, nh, dh)
        S = S * gt.unsqueeze(-1).unsqueeze(-1)
        e = torch.einsum('bnde,bne->bnd', S, kt)
        S = S + bt.unsqueeze(-1).unsqueeze(-1) * torch.einsum(
            'bnd,bne->bnde', vt - e, kt)
        ot = torch.einsum('bnde,bne->bnd', S, qt)
        o_list.append(ot)
    o = torch.stack(o_list, dim=1)                         # (B, T, nh, dh)
    return (o, S) if output_final_state else (o, None)


try:
    import fla  # noqa: F401 — trigger ImportError early if absent
    _FLA_AVAILABLE = True
except ImportError:
    _FLA_AVAILABLE = False
    # Patch _get_gdn2_fn in unet_gdn2 before importing GDN2MemoryModule
    import importlib
    _unet_mod = importlib.import_module('models.unet_gdn2')
    _unet_mod._get_gdn2_fn = lambda backend: _pytorch_gated_delta_rule_stub
    print("[mqar_probe] fla not found — using pure-PyTorch GDN-2 stub (CPU smoke only). "
          "Full sweep must run on HPC with fla installed.", file=sys.stderr)

from models.unet_gdn2 import GDN2MemoryModule, LinearAttnModule  # noqa: E402

# ---------------------------------------------------------------------------
# FLA GatedDeltaNet cross-validation arm (gdn2_fla)
# ---------------------------------------------------------------------------
# GatedDeltaNet.forward(hidden_states: (B, T, hidden_size), attention_mask=None,
#                       past_key_values=None, use_cache=False, ...)
#   → (o: (B, T, hidden_size), None, past_key_values)
# Source: fla/layers/gated_deltanet.py (fla-org/flash-linear-attention)
#
# Adapter wraps the layer to expose a clean (B, T, d_model) → (B, T, d_model)
# interface compatible with MQARBackbone.
#
# Config (official Zoology/FLA MQAR standard):
#   use_short_conv=True, conv_size=4 — "crucial, do not turn off" (FLA warning)
#   num_heads=2                       — Zoology MQAR baseline
#   head_dim=32                       — chosen so key_dim=num_heads*head_dim=64
#                                       and value_dim=key_dim*expand_v=128=d_model
#                                       with expand_v=2 (FLA default)
#   # TODO: head_dim not found in official Zoology+FLA MQAR source for d_model=128;
#   #       head_dim=32 is the smallest power-of-2 that satisfies the integer
#   #       constraint (key_dim=64 ≤ hidden_size=128). Researcher should confirm.
#
# NOTE: This arm requires `fla` (flash-linear-attention) installed with CUDA.
#       On local Windows (no fla) this class is defined but imports are guarded.
#       Always skip / mock in pytest when fla is absent.

_FLAGatedDeltaNet = None  # populated below when fla is available
if _FLA_AVAILABLE:
    from fla.layers import GatedDeltaNet as _FLAGatedDeltaNet  # noqa: E402


class FLAGatedDeltaNetAdapter(nn.Module):
    """
    Thin adapter around FLA's GatedDeltaNet layer for MQAR probe.

    Interface: (B, T, d_model) → (B, T, d_model) — same as GDN2Adapter /
    LinearAttnAdapter so it drops directly into MQARBackbone.mixers.

    FLA's GatedDeltaNet.forward returns a 3-tuple (o, None, past_key_values);
    we unpack only `o` and discard the rest.

    Args:
        d_model (int):   Token embedding dimension = hidden_size for FLA layer.
        num_heads (int): Number of attention heads. Default 2 (Zoology MQAR).
        head_dim (int):  Per-head key dimension. Default 32 → key_dim=64,
                         value_dim=128 (= d_model) for expand_v=2.
                         # TODO: confirm against official Zoology/FLA MQAR source
                         #       for the exact d_model=128 setting.
        conv_size (int): Short conv kernel size. Default 4 (FLA/Zoology standard).

    Raises:
        ImportError: if fla is not installed (guarded at construction time).
    """

    def __init__(
        self,
        d_model: int,
        num_heads: int = 2,
        head_dim: int = 32,       # TODO: verify against official Zoology MQAR d_model=128 config
        conv_size: int = 4,
    ):
        super().__init__()
        if not _FLA_AVAILABLE:
            raise ImportError(
                "FLAGatedDeltaNetAdapter requires the `fla` (flash-linear-attention) "
                "package, which is only available on HPC (CUDA env). "
                "Install via: pip install flash-linear-attention"
            )
        # expand_v=2 is FLA default: value_dim = num_heads * head_dim * expand_v
        # With num_heads=2, head_dim=32, expand_v=2: value_dim=128=d_model ✓
        self.layer = _FLAGatedDeltaNet(
            hidden_size=d_model,
            num_heads=num_heads,
            head_dim=head_dim,
            expand_v=2.0,            # FLA default; value_dim = key_dim * 2 = d_model
            use_short_conv=True,     # crucial: "do not turn off" (FLA warning)
            conv_size=conv_size,
            use_gate=True,           # FLA default; output gate
            mode='chunk',            # chunk mode for training (FLA requirement)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: (B, T, d_model) — token hidden states
        Returns: (B, T, d_model)
        FLA GatedDeltaNet.forward returns (o, None, past_key_values); we take o.
        """
        o, _, _ = self.layer(x)   # o: (B, T, d_model)
        return o


# ---------------------------------------------------------------------------
# Module adapters: (B, T, d_model) → (B, d_model, 1, T) → module → back
# ---------------------------------------------------------------------------
# Design note (VLA §5.1): no short conv is added here.  VLA deliberately omits
# short conv to keep the stateless-arm comparison clean: conv gives stateless
# arms local context that lets them exploit k-v proximity and masks the
# capacity gap at small n.  We follow the same choice.

class GDN2Adapter(nn.Module):
    """
    Wraps GDN2MemoryModule so it takes (B, T, C) token sequences.

    Both modules expect (B, C, H, W) feature maps.  We reshape the token
    sequence to (B, C, 1, T) — a 1×T "image" — which satisfies:
      - H*W = T  ≤ MAX_SEQ_LEN=1024
      - C = d_model matches the module's assertion
    After the module forward, we reshape (B, C, 1, T) → (B, T, C).

    use_frangi=False: disables Frangi gate (vessel-specific), isolates pure
    delta-rule vs stateless comparison (required for MQAR mechanism isolation).

    has_internal_residual = True:
        GDN2MemoryModule.forward already applies residual+LayerNorm internally
        (see unet_gdn2.py L875-876: out_tokens = self.norm(tokens + out_tokens)).
        MQARBackbone uses this flag to skip its own pre-norm+residual wrapper
        and instead call:  x = mixer(x)   (module is the full sublayer)
        rather than:       x = x + mixer(LN(x))   (would cause double residual)
    """

    # MQARBackbone reads this flag to decide whether to wrap with pre-norm+residual
    has_internal_residual: bool = True

    def __init__(self, d_model: int, d_head: int, n_heads: int = 1,
                 max_seq_len: int = 1024):
        super().__init__()
        self.module = GDN2MemoryModule(
            d_model=d_model,
            d_head=d_head,
            n_heads=n_heads,
            max_seq_len=max_seq_len,
            directions=1,
            use_frangi=False,   # MQAR: no vessel gate — isolate pure mechanism
        )
        self.d_model = d_model

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: (B, T, C) → out: (B, T, C)

        NOTE: when called from MQARBackbone and has_internal_residual=True,
        the backbone passes x (pre-normed copy not applied) directly here,
        and this module returns the complete post-residual output.
        The backbone should NOT add x again.
        """
        B, T, C = x.shape
        # reshape to (B, C, 1, T) — "1×T feature map"
        feat = x.permute(0, 2, 1).unsqueeze(2)   # (B, C, 1, T)
        out_feat = self.module(feat)              # (B, C, 1, T)  — already has residual+LN
        out = out_feat.squeeze(2).permute(0, 2, 1)  # (B, T, C)
        return out


class LinearAttnAdapter(nn.Module):
    """
    Wraps LinearAttnModule so it takes (B, T, C) token sequences.
    Same reshape trick as GDN2Adapter.

    has_internal_residual = True:
        LinearAttnModule.forward also applies residual+LayerNorm internally
        (see unet_gdn2.py L1191-1193: out_tokens = self.norm(tokens + out_tokens)).
        Symmetric with GDN2Adapter — MQARBackbone skips the outer pre-norm+residual.
    """

    # MQARBackbone reads this flag (symmetric with GDN2Adapter)
    has_internal_residual: bool = True

    def __init__(self, d_model: int, d_head: int, n_heads: int = 1,
                 max_seq_len: int = 1024):
        super().__init__()
        self.module = LinearAttnModule(
            d_model=d_model,
            d_head=d_head,
            n_heads=n_heads,
            max_seq_len=max_seq_len,
            directions=1,
            use_frangi=False,   # MQAR: no vessel gate
        )
        self.d_model = d_model

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: (B, T, C) → out: (B, T, C)

        NOTE: module already has internal residual+LN (same as GDN2Adapter).
        MQARBackbone passes x directly and does NOT add a further residual.
        """
        B, T, C = x.shape
        feat = x.permute(0, 2, 1).unsqueeze(2)   # (B, C, 1, T)
        out_feat = self.module(feat)              # (B, C, 1, T)  — already has residual+LN
        out = out_feat.squeeze(2).permute(0, 2, 1)  # (B, T, C)
        return out


# ---------------------------------------------------------------------------
# FFN block (shared between layers, same for both arms)
# ---------------------------------------------------------------------------

class FFN(nn.Module):
    """
    Two-layer feed-forward network with GELU activation.

    FFN(x) = Linear(GELU(Linear(x, 4*d)), d)

    Standard transformer FFN expansion ratio = 4 (VLA / Based / Zoology all
    use this default for the sequence-model capacity benchmark backbones).
    No bias to match the typical no-bias attention convention.
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

    Each layer applies pre-norm residual blocks:
        x = x + mixer(LN(x))      # token-mixer: GDN2Adapter or LinearAttnAdapter
        x = x + FFN(LN(x))        # feed-forward

    Both arms use the *same* MQARBackbone class; only the mixer list differs.
    Embedding / LN / FFN / head are structurally identical across arms (the
    test verifies parameter parity excluding mixer weights ±5%).

    No short conv: VLA intentionally excludes it so stateless arms cannot
    exploit k-v proximity to fake capacity (see adapter comment above).

    Args:
        d_model:    token embedding dimension
        mixers:     list of n_layers mixer modules (GDN2Adapter / LinearAttnAdapter)
                    already instantiated.  len(mixers) == n_layers.
        n_layers:   number of backbone layers (default 2, VLA §5.1)
        ffn_expand: FFN expansion ratio (default 4)
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

        # Mixer modules (arm-specific: GDN2Adapter or LinearAttnAdapter)
        self.mixers = nn.ModuleList(mixers)

        # FFN modules (shared structure; weights are arm-specific per-instance)
        self.ffns = nn.ModuleList([FFN(d_model, expand=ffn_expand) for _ in range(n_layers)])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: (B, T, d_model) → (B, T, d_model)

        Each layer:
            if mixer.has_internal_residual:
                x = mixer(x)           # module already owns residual+LN internally
            else:
                x = x + mixer(LN(x))  # standard pre-norm residual (mixer is delta-only)
            x = x + FFN(LN(x))        # FFN pre-norm residual (always standard)

        Background (2026-06-21 double-residual fix):
            GDN2MemoryModule and LinearAttnModule both perform:
                out_tokens = self.norm(tokens + proj_out(delta_rule_output))
            i.e., they are designed as *complete sublayers* (residual+norm included).
            The original code wrapped them in an additional pre-norm+residual:
                x = x + mixer(LN(x))
            which produced:
                x = x + LN(x_in + proj_out(delta_rule(LN(x_in))))
            — double residual + double LN.  This washes out recall signal and
            destroys gradient flow through the associative memory.
            Fix: when has_internal_residual=True, call x = mixer(x) instead.
        """
        for i in range(self.n_layers):
            mixer = self.mixers[i]
            if getattr(mixer, 'has_internal_residual', False):
                # Mixer already applies its own pre-norm + residual + LayerNorm.
                # Pass x directly; do NOT apply mixer_norm or add residual here.
                x = mixer(x)
            else:
                # Standard pre-norm residual (mixer outputs only delta, no internal norm).
                x = x + mixer(self.mixer_norms[i](x))
            x = x + self.ffns[i](self.ffn_norms[i](x))       # FFN pre-norm residual
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
    continuous_key: bool = False,
    d_head: int = 64,
    noise_sigma: float = 0.0,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """
    Build a batch of MQAR sequences (online, no stored dataset).

    Layout (Zoology arXiv 2312.04927 convention):
      - prefix: 2*n_kv tokens — n_kv (key, value) pairs interleaved
        [k0, v0, k1, v1, ..., k_{n_kv-1}, v_{n_kv-1}]
      - query zone: T - 2*n_kv tokens — contains n_kv query tokens
        placed at random positions among noise tokens; each query token
        equals one of the prefix keys; the model must recall the paired value.

    Token ranges (discrete mode):
      keys   ∈ [1, V//2)
      values ∈ [V//2, V)
      noise  ∈ {0}  (zero token = noise / padding)

    Continuous key mode:
      key tokens are replaced with d_head-dim unit-sphere samples + Gaussian
      noise (sigma=noise_sigma). Value targets remain discrete (classification).

    Returns:
      seq_ids:     (B, T)       long — token ids (noise=0 for query-zone nones;
                                continuous key positions carry real ids for embed
                                lookup? No: in continuous mode we skip embed for keys)
      targets:     (B, T)       long — value id at query positions, -100 elsewhere
      query_mask:  (B, T)       bool — True at query positions

    For continuous_key=True, we also return continuous key vectors via a
    separate buffer stored on the returned tensors:
      seq_ids[..., prefix positions] still valid (value tokens embedded normally)
      But the caller must handle key injection — see MQARModel.forward() logic.

    Implementation note:
      We store continuous key embeddings as an extra attribute on returned
      seq_ids tensor: seq_ids._cont_keys = (B, n_kv, d_head) when continuous_key=True.
      This avoids changing the return signature visible to tests.
    """
    rng = np.random.default_rng(seed)

    B = batch_size

    # --- Sample keys and values (unique per batch item) ---
    # keys: [1, V//2) — must be distinct per sequence (MQAR spec: each key queried once)
    # values: [V//2, V) — must be distinct per sequence
    key_pool   = np.arange(1, V // 2, dtype=np.int64)
    value_pool = np.arange(V // 2, V, dtype=np.int64)
    key_ids   = np.stack([rng.choice(key_pool,   size=n_kv, replace=False) for _ in range(B)])
    value_ids = np.stack([rng.choice(value_pool, size=n_kv, replace=False) for _ in range(B)])

    # --- Build sequences ---
    prefix_len = 2 * n_kv
    suffix_len = T - prefix_len
    assert suffix_len >= n_kv, (
        f"T={T} too short for n_kv={n_kv}: need at least {prefix_len + n_kv} tokens"
    )

    seq_ids    = np.zeros((B, T), dtype=np.int64)
    targets    = np.full((B, T), -100, dtype=np.int64)
    query_mask = np.zeros((B, T), dtype=bool)

    # --- Continuous key vectors (if needed) ---
    cont_keys_np = None
    if continuous_key:
        # Sample unit-sphere vectors for each key in each batch
        raw = rng.standard_normal((B, n_kv, d_head)).astype(np.float32)
        norms = np.linalg.norm(raw, axis=-1, keepdims=True)
        cont_keys_np = raw / (norms + 1e-8)
        if noise_sigma > 0.0:
            cont_keys_np = cont_keys_np + rng.standard_normal(
                cont_keys_np.shape).astype(np.float32) * noise_sigma

    for b in range(B):
        # prefix: [k0, v0, k1, v1, ...]
        for i in range(n_kv):
            seq_ids[b, 2 * i]     = key_ids[b, i]
            seq_ids[b, 2 * i + 1] = value_ids[b, i]

        # query zone: n_kv query positions chosen randomly in suffix
        q_positions = rng.choice(suffix_len, size=n_kv, replace=False)
        q_positions_sorted = np.sort(q_positions)

        # which key each query asks about (each key queried exactly once)
        query_perm = rng.permutation(n_kv)

        for idx, (qpos, kv_idx) in enumerate(
                zip(q_positions_sorted, query_perm)):
            abs_pos = prefix_len + int(qpos)
            seq_ids[b, abs_pos]    = key_ids[b, kv_idx]   # query = key
            targets[b, abs_pos]    = value_ids[b, kv_idx]  # target = value
            query_mask[b, abs_pos] = True

    seq_ids_t    = torch.from_numpy(seq_ids).to(device)
    targets_t    = torch.from_numpy(targets).to(device)
    query_mask_t = torch.from_numpy(query_mask).to(device)

    # Attach continuous keys as an attribute so MQARModel can use them
    if cont_keys_np is not None:
        seq_ids_t._cont_keys = torch.from_numpy(cont_keys_np).to(device)  # (B, n_kv, d_head)
    else:
        seq_ids_t._cont_keys = None

    return seq_ids_t, targets_t, query_mask_t


# ---------------------------------------------------------------------------
# MQAR model
# ---------------------------------------------------------------------------

class MQARModel(nn.Module):
    """
    Embedding → 2-layer backbone → classifier head.

    Structure (VLA §5.1 original 2-layer setup):
      - nn.Embedding(V, d_model)
      - MQARBackbone(2 layers of [mixer + FFN], pre-norm residual)
      - nn.Linear(d_model, V)

    Both arms use the same MQARBackbone structure; only the mixer modules
    inside the backbone differ (GDN2Adapter vs LinearAttnAdapter).
    Embedding / LN / FFN / head are structurally identical.

    Continuous-key mode: key positions in the prefix use injected continuous
    vectors (bypassing embedding lookup) rather than discrete token ids.
    Value positions and query positions still use embedding lookup.
    """

    def __init__(
        self,
        V: int,
        d_model: int,
        d_head: int,
        backbone: Optional[MQARBackbone] = None,  # 2-layer backbone (arm-specific mixers inside)
        n_heads: int = 1,
        continuous_key: bool = False,
        n_kv: int = 0,              # needed to identify prefix key positions
        # Legacy compat: accept 'adapter' kwarg and wrap it in a 1-layer backbone.
        # Do not use in new code — always pass backbone= explicitly.
        adapter: Optional[nn.Module] = None,
    ):
        super().__init__()
        self.V          = V
        self.d_model    = d_model
        self.d_head     = d_head
        self.continuous_key = continuous_key
        self.n_kv       = n_kv

        self.embed = nn.Embedding(V, d_model)

        if backbone is not None:
            self.backbone = backbone
        elif adapter is not None:
            # Legacy 1-layer compat path (used in existing tests via adapter= kwarg)
            self.backbone = MQARBackbone(d_model=d_model, mixers=[adapter], n_layers=1)
        else:
            raise ValueError("Either backbone= or adapter= must be provided")

        self.head = nn.Linear(d_model, V)

    def forward(
        self,
        seq_ids: torch.Tensor,     # (B, T) long
        cont_keys: Optional[torch.Tensor] = None,  # (B, n_kv, d_head) if continuous
    ) -> torch.Tensor:
        """Returns logits (B, T, V)."""
        # Embedding lookup for all positions first
        x = self.embed(seq_ids)    # (B, T, d_model)

        # Continuous key injection: replace prefix key positions with cont vectors
        # Key positions in prefix: 0, 2, 4, ..., 2*(n_kv-1)
        if self.continuous_key and cont_keys is not None:
            # cont_keys: (B, n_kv, d_head); project to d_model
            # We use a simple expand if d_head == d_model, else zero-pad/truncate
            # Since d_model >= d_head always in our config (d_model=128, d_head=64),
            # we zero-pad the remainder so continuous vectors have same dim as embed
            B, n_kv, dh = cont_keys.shape
            if dh == self.d_model:
                cont_proj = cont_keys
            else:
                # zero-pad to d_model
                pad = torch.zeros(B, n_kv, self.d_model - dh,
                                  device=cont_keys.device, dtype=cont_keys.dtype)
                cont_proj = torch.cat([cont_keys, pad], dim=-1)  # (B, n_kv, d_model)

            # Insert into x at key positions (0, 2, ..., 2*(n_kv-1))
            key_positions = torch.arange(0, 2 * n_kv, 2, device=seq_ids.device)
            x[:, key_positions, :] = cont_proj

        x = self.backbone(x)       # (B, T, d_model)  — 2-layer backbone
        logits = self.head(x)      # (B, T, V)
        return logits


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
    batch_size: int = 32,
    d_model: int = 128,
    n_heads: int = 1,
    continuous_key: bool = False,
    noise_sigma: float = 0.0,
    log_every: int = 100,
    n_layers: int = 2,           # VLA §5.1: 2-layer backbone
    # gdn2_fla arm config (only used when arm='gdn2_fla')
    fla_num_heads: int = 2,      # Zoology/FLA MQAR standard
    fla_head_dim: int = 32,      # TODO: verify against official Zoology MQAR d_model=128 config
    fla_conv_size: int = 4,      # FLA/Zoology MQAR standard
) -> Dict:
    """
    Train one (arm, n_kv, lr, seed) config. Returns result dict.

    arm: 'gdn2' | 'linear_attn' | 'gdn2_fla'

    Backbone: 2-layer (n_layers=2), each layer = mixer + FFN, pre-norm residual.
    Both arms use MQARBackbone; only the mixer module differs.
    No short conv for gdn2/linear_attn (VLA original setup).
    gdn2_fla arm uses FLA canonical GatedDeltaNet with short conv (Zoology MQAR
    standard). Requires fla installed (HPC only). Will raise ImportError locally.
    """
    torch.manual_seed(seed)
    np.random.seed(seed)

    # Build n_layers mixer instances for the backbone
    if arm == 'gdn2':
        mixers = [
            GDN2Adapter(d_model=d_model, d_head=d_head, n_heads=n_heads, max_seq_len=T)
            for _ in range(n_layers)
        ]
    elif arm == 'linear_attn':
        mixers = [
            LinearAttnAdapter(d_model=d_model, d_head=d_head, n_heads=n_heads, max_seq_len=T)
            for _ in range(n_layers)
        ]
    elif arm == 'gdn2_fla':
        # FLA canonical GatedDeltaNet: cross-validation reference arm.
        # Tests delta-rule WITH official short conv (Zoology MQAR standard).
        # use_short_conv=True is "crucial" per FLA source warning.
        # NOTE: requires `fla` (flash-linear-attention) on HPC with CUDA.
        #       FLAGatedDeltaNetAdapter.__init__ raises ImportError if fla absent.
        if not _FLA_AVAILABLE:
            raise ImportError(
                "arm='gdn2_fla' requires the `fla` (flash-linear-attention) package "
                "with CUDA support. This arm must run on HPC. "
                "Install via: pip install flash-linear-attention"
            )
        mixers = [
            FLAGatedDeltaNetAdapter(
                d_model=d_model,
                num_heads=fla_num_heads,
                head_dim=fla_head_dim,
                conv_size=fla_conv_size,
            )
            for _ in range(n_layers)
        ]
    else:
        raise ValueError(f"Unknown arm: {arm!r}. Valid: 'gdn2', 'linear_attn', 'gdn2_fla'")

    backbone = MQARBackbone(d_model=d_model, mixers=mixers, n_layers=n_layers)

    model = MQARModel(
        V=V, d_model=d_model, d_head=d_head, backbone=backbone,
        n_heads=n_heads, continuous_key=continuous_key, n_kv=n_kv,
    ).to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)

    best_acc = 0.0
    converged = False

    for step in range(1, steps + 1):
        model.train()
        seq_ids, targets, query_mask = build_mqar_batch(
            batch_size=batch_size, T=T, n_kv=n_kv, V=V,
            device=device,
            seed=None,  # random each step
            continuous_key=continuous_key,
            d_head=d_head,
            noise_sigma=noise_sigma,
        )
        cont_keys = seq_ids._cont_keys  # None if not continuous

        logits = model(seq_ids, cont_keys=cont_keys)  # (B, T, V)

        # CE loss only at query positions
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

        # Eval every log_every steps (on a fresh batch)
        if step % log_every == 0 or step == steps:
            model.eval()
            with torch.no_grad():
                seq_ids_e, targets_e, query_mask_e = build_mqar_batch(
                    batch_size=batch_size * 2, T=T, n_kv=n_kv, V=V,
                    device=device, seed=step * 997 + seed,
                    continuous_key=continuous_key, d_head=d_head,
                    noise_sigma=noise_sigma,
                )
                cont_keys_e = seq_ids_e._cont_keys
                logits_e = model(seq_ids_e, cont_keys=cont_keys_e)
                pred_e = logits_e.argmax(dim=-1)  # (B, T)
                # accuracy only at query positions
                correct = (pred_e == targets_e) & query_mask_e
                n_queries = query_mask_e.sum().item()
                acc = correct.sum().item() / max(n_queries, 1)

            if acc > best_acc:
                best_acc = acc

            if step % (log_every * 5) == 0 or step == steps:
                print(f"  [{arm}|n={n_kv}|lr={lr:.0e}|seed={seed}] "
                      f"step={step}/{steps} loss={loss.item():.4f} acc={acc:.4f} best={best_acc:.4f}")

    # Final convergence check: n_kv=4 sanity gate handled by caller
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

    PREREG thresholds (from ROUTE2_BUDGET_PREREG.md):
      LIVE: exists n in {16,32,64}:
        acc_gdn2(n) - acc_la(n) > 0.15
        AND acc_gdn2(n) > 0.5
        AND acc_la(n) < 0.5
        AND seed std < 0.05
      DEAD: otherwise (gap < 0.15 everywhere or never beats la+delta at n<=64)
      SANITY: n=4 both arms acc > 0.90 (else training failure, not null)
    """
    rows = []
    with open(csv_path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                'arm': row['arm'],
                'n_kv': int(row['n_kv']),
                'd_head': int(row['d_head']),
                'lr': float(row['lr']),
                'seed': int(row['seed']),
                'final_acc': float(row['final_acc']),
                'steps': int(row['steps']),
                'converged': int(row['converged']),
            })

    # Group by (arm, n_kv): take best lr per seed, then average over seeds
    from collections import defaultdict
    by_arm_n = defaultdict(lambda: defaultdict(list))  # arm -> n_kv -> [acc]

    # For each (arm, n_kv, seed), take max acc across lrs
    best = defaultdict(dict)  # (arm, n_kv, seed) -> best_acc
    for r in rows:
        key = (r['arm'], r['n_kv'], r['seed'])
        cur = best.get(key, -1.0)
        if r['final_acc'] > cur:
            best[key] = r['final_acc']

    for (arm, n_kv, seed), acc in best.items():
        by_arm_n[arm][n_kv].append(acc)

    # Compute stats
    stats = {}  # arm -> n_kv -> {mean, std, n}
    for arm, n_dict in by_arm_n.items():
        stats[arm] = {}
        for n, accs in n_dict.items():
            arr = np.array(accs, dtype=float)
            stats[arm][n] = {
                'mean': float(np.mean(arr)),
                'std': float(np.std(arr, ddof=1) if len(arr) > 1 else 0.0),
                'n_seeds': len(arr),
                'accs': [float(a) for a in arr],
            }

    # Sanity gate: n=4, both arms > 0.9
    sanity_ok = True
    sanity_detail = {}
    for arm in ('gdn2', 'linear_attn'):
        if arm in stats and 4 in stats[arm]:
            s = stats[arm][4]
            sanity_detail[arm] = {'mean': s['mean'], 'pass': bool(s['mean'] > 0.9)}
            if s['mean'] <= 0.9:
                sanity_ok = False
        else:
            sanity_detail[arm] = {'mean': None, 'pass': False}
            sanity_ok = False

    # Gap per n_kv
    all_n = sorted(set(
        list(stats.get('gdn2', {}).keys()) +
        list(stats.get('linear_attn', {}).keys())
    ))
    gap_table = {}
    live_windows = []

    for n in all_n:
        g2 = stats.get('gdn2', {}).get(n, None)
        la = stats.get('linear_attn', {}).get(n, None)
        if g2 is None or la is None:
            gap_table[n] = {'gap': None, 'acc_gdn2': None, 'acc_la': None,
                            'std_gdn2': None, 'std_la': None}
            continue

        gap = g2['mean'] - la['mean']
        gap_table[n] = {
            'gap': float(gap),
            'acc_gdn2': float(g2['mean']),
            'acc_la': float(la['mean']),
            'std_gdn2': float(g2['std']),
            'std_la': float(la['std']),
        }

        # Check LIVE conditions for this n
        if n in (16, 32, 64):
            cond_gap  = gap > prereg_delta
            cond_g2   = g2['mean'] > 0.5
            cond_la   = la['mean'] < 0.5
            cond_std  = g2['std'] < 0.05
            if cond_gap and cond_g2 and cond_la and cond_std:
                live_windows.append({
                    'n_kv': n,
                    'gap': float(gap),
                    'acc_gdn2': float(g2['mean']),
                    'acc_la': float(la['mean']),
                    'std_gdn2': float(g2['std']),
                    'cond_gap': cond_gap,
                    'cond_acc_gdn2_gt_05': cond_g2,
                    'cond_acc_la_lt_05': cond_la,
                    'cond_std_lt_005': cond_std,
                })

    verdict = 'LIVE' if (sanity_ok and len(live_windows) > 0) else 'DEAD'
    if not sanity_ok:
        verdict = 'DEAD_SANITY_FAIL'

    return {
        'verdict': verdict,
        'prereg_delta': prereg_delta,
        'prereg_file': 'reference/ROUTE2_BUDGET_PREREG.md',
        'sanity_gate': {
            'pass': sanity_ok,
            'detail': sanity_detail,
            'threshold': 0.9,
        },
        'live_windows': live_windows,
        'gap_table': {str(k): v for k, v in gap_table.items()},
        'stats': {
            arm: {str(n): s for n, s in nd.items()}
            for arm, nd in stats.items()
        },
        'random_baseline': None,  # filled by caller
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='MQAR Capacity Probe — Layer 2')
    p.add_argument('--n_kv', type=int, nargs='+',
                   default=[4, 8, 16, 32, 64, 96],
                   help='List of n_kv values to sweep')
    p.add_argument('--d_head', type=int, default=64)
    p.add_argument('--lr', type=float, nargs='+',
                   default=[1e-3, 5e-4, 1e-4],
                   help='Learning rates to sweep')
    p.add_argument('--seeds', type=int, nargs='+', default=[0, 1])
    p.add_argument('--T', type=int, default=256)
    p.add_argument('--vocab', type=int, default=8192)
    p.add_argument('--steps', type=int, default=2000,
                   help='Training steps per config (VLA §5.1 alignment: 2000)')
    p.add_argument('--n_layers', type=int, default=2,
                   help='Number of backbone layers (VLA §5.1: 2)')
    p.add_argument('--batch_size', type=int, default=32)
    p.add_argument('--d_model', type=int, default=128,
                   help='Token embedding dimension (must be >= d_head; d_model=128, d_head=64 → n_heads=1)')
    p.add_argument('--continuous_key', action='store_true',
                   help='Use continuous sphere-sampled keys (R4 robustness variant)')
    p.add_argument('--noise_sigma', type=float, default=0.0,
                   help='Gaussian noise sigma for continuous key variant')
    p.add_argument('--smoke', action='store_true',
                   help='Quick smoke test: n_kv=4, 1 lr, 1 seed, 200 steps')
    p.add_argument('--out_dir', type=str,
                   default=str(_ROOT / 'outputs' / 'route2_budget'))
    p.add_argument('--cpu', action='store_true', help='Force CPU even if CUDA available')
    p.add_argument('--arms', type=str, nargs='+', default=['gdn2', 'linear_attn'],
                   help=(
                       'Which arms to run. Options: gdn2, linear_attn, gdn2_fla. '
                       'gdn2_fla = FLA canonical GatedDeltaNet (use_short_conv=True, '
                       'cross-validation reference). REQUIRES fla on HPC (CUDA). '
                       'Example: --arms gdn2 linear_attn gdn2_fla'
                   ))
    p.add_argument('--log_every', type=int, default=100)
    # --- gdn2_fla arm config (only used when gdn2_fla is in --arms) ---
    p.add_argument('--fla_num_heads', type=int, default=2,
                   help='GatedDeltaNet num_heads for gdn2_fla arm (Zoology MQAR: 2)')
    p.add_argument('--fla_head_dim', type=int, default=32,
                   help=(
                       'GatedDeltaNet head_dim for gdn2_fla arm. '
                       'key_dim = fla_num_heads * fla_head_dim must be <= d_model. '
                       'Default 32 → key_dim=64, value_dim=128=d_model for expand_v=2. '
                       '# TODO: verify against official Zoology MQAR d_model=128 config.'
                   ))
    p.add_argument('--fla_conv_size', type=int, default=4,
                   help='GatedDeltaNet short conv kernel size (FLA/Zoology standard: 4)')
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Device
    if args.cpu or not torch.cuda.is_available():
        device = torch.device('cpu')
    else:
        device = torch.device('cuda')
    print(f"[mqar_probe] device={device}")

    # Smoke mode: shrink sweep
    if args.smoke:
        args.n_kv   = [4]
        args.lr     = [1e-3]
        args.seeds  = [0]
        args.steps  = 200
        args.batch_size = 8
        print("[mqar_probe] SMOKE MODE: n_kv=[4] lr=[1e-3] seeds=[0] steps=200")

    # Validate d_model >= d_head
    assert args.d_model >= args.d_head, (
        f"d_model={args.d_model} must be >= d_head={args.d_head}"
    )

    # Output dir
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path     = out_dir / 'mqar_results.csv'
    verdict_path = out_dir / 'mqar_verdict.json'

    # Random baseline
    random_baseline = 1.0 / (args.vocab // 2)
    print(f"[mqar_probe] random_baseline = {random_baseline:.6f} "
          f"(= 1/(V/2) = 1/{args.vocab//2})")

    # Sweep
    fieldnames = ['arm', 'n_kv', 'd_head', 'lr', 'seed',
                  'final_acc', 'steps', 'converged']
    csv_exists = csv_path.exists()
    # Load already-done configs to skip
    done_keys = set()
    if csv_exists:
        with open(csv_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                done_keys.add((row['arm'], int(row['n_kv']),
                                float(row['lr']), int(row['seed'])))
        print(f"[mqar_probe] Found {len(done_keys)} existing results, will skip.")

    fout = open(csv_path, 'a', newline='')
    writer = csv.DictWriter(fout, fieldnames=fieldnames)
    if not csv_exists:
        writer.writeheader()
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
                        continuous_key=args.continuous_key,
                        noise_sigma=args.noise_sigma,
                        log_every=args.log_every,
                        n_layers=args.n_layers,
                        fla_num_heads=args.fla_num_heads,
                        fla_head_dim=args.fla_head_dim,
                        fla_conv_size=args.fla_conv_size,
                    )

                    writer.writerow(result)
                    fout.flush()

                    print(f"  -> final_acc={result['final_acc']:.4f} "
                          f"converged={result['converged']}")

    fout.close()
    print(f"\n[mqar_probe] Sweep done. Results: {csv_path}")

    # Compute verdict
    verdict = compute_verdict(csv_path, prereg_delta=0.15)
    verdict['random_baseline'] = random_baseline

    with open(verdict_path, 'w') as f:
        json.dump(verdict, f, indent=2)

    print(f"\n[mqar_probe] VERDICT: {verdict['verdict']}")
    print(f"[mqar_probe] Sanity gate (n=4 both arms >0.9): {verdict['sanity_gate']['pass']}")
    if verdict['live_windows']:
        print(f"[mqar_probe] Live windows found at n_kv={[w['n_kv'] for w in verdict['live_windows']]}")
    print(f"[mqar_probe] Verdict JSON: {verdict_path}")


if __name__ == '__main__':
    main()
