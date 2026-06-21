"""
pytest for MQAR capacity probe (Layer 2 of Route-2 Budget).

Tests:
  1. Sequence construction correctness
     - query target == paired value
     - prefix contains all n_kv key-value pairs
     - shapes correct
  2. Random baseline value
  3. Both arms forward pass on CPU (tiny config, no crash)
  4. Verdict function on synthetic CSVs
     - "has window" data  → verdict LIVE
     - "no window" data   → verdict DEAD

NOTE on FLA stub:
  `fla` (Flash-Linear-Attention) is only installed on HPC (CUDA env).
  For CPU pytest we monkeypatch `models.unet_gdn2._get_gdn2_fn` with a
  pure-PyTorch delta-rule stub that has the same signature/output shape.
  This stub is mathematically correct (stateful delta-rule, CPU-safe) and
  lets us verify the adapter wiring without the CUDA kernel.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import numpy as np
import pytest
import torch
import torch.nn as nn
import torch.nn.functional as F

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_HERE  = Path(__file__).resolve().parent
_ROOT  = _HERE.parent
_SRC   = _ROOT / 'src'
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ---------------------------------------------------------------------------
# FLA stub — pure PyTorch gated-delta-rule (CPU-safe, matches FLA signature)
# ---------------------------------------------------------------------------

def _pytorch_gated_delta_rule_stub(
    q: torch.Tensor,    # (B, T, nh, dh)
    k: torch.Tensor,
    v: torch.Tensor,
    beta: torch.Tensor, # (B, T, nh) write gate
    g: torch.Tensor,    # (B, T, nh) log-decay
    output_final_state: bool = False,
):
    """
    Pure-PyTorch causal gated delta-rule (sequential scan).
    Matches FLA naive_chunk_gated_delta_rule signature.

    S_t = diag(exp(g_t)) * S_{t-1} + beta_t * outer(v_t - S_{t-1}@k_t, k_t)
    o_t = S_t @ q_t
    """
    B, T, nh, dh = q.shape
    device, dtype = q.device, q.dtype

    o_list = []
    # S: (B, nh, dh, dh)
    S = torch.zeros(B, nh, dh, dh, device=device, dtype=dtype)

    for t in range(T):
        gt   = torch.exp(g[:, t, :])            # (B, nh), decay in [0,1]
        bt   = beta[:, t, :]                     # (B, nh), write gate
        qt   = q[:, t, :, :]                     # (B, nh, dh)
        kt   = k[:, t, :, :]                     # (B, nh, dh)
        vt   = v[:, t, :, :]                     # (B, nh, dh)

        # Decay: S = diag(g) * S  per head
        # gt: (B, nh) → (B, nh, 1, 1)
        S = S * gt.unsqueeze(-1).unsqueeze(-1)

        # Retrieve: e = S @ k_t  → (B, nh, dh)
        e = torch.einsum('bnde,bne->bnd', S, kt)

        # Delta: delta_v = v_t - e  → (B, nh, dh)
        delta_v = vt - e

        # Write: S += beta * outer(delta_v, k_t)
        # bt: (B, nh) → (B, nh, 1, 1)
        S = S + bt.unsqueeze(-1).unsqueeze(-1) * torch.einsum(
            'bnd,bne->bnde', delta_v, kt)

        # Output: o = S @ q_t
        ot = torch.einsum('bnde,bne->bnd', S, qt)  # (B, nh, dh)
        o_list.append(ot)

    o = torch.stack(o_list, dim=1)  # (B, T, nh, dh)

    if output_final_state:
        return o, S
    return o, None  # FLA naive returns tuple


def _stub_get_gdn2_fn(backend: str):
    """Replace _get_gdn2_fn so GDN2MemoryModule can init on CPU without FLA."""
    return _pytorch_gated_delta_rule_stub


# ---------------------------------------------------------------------------
# Autouse fixture: patch FLA import for all tests in this file
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_fla(monkeypatch):
    """Patch out FLA so GDN2MemoryModule initialises on CPU (pytest env)."""
    import models.unet_gdn2 as _unet_mod
    monkeypatch.setattr(_unet_mod, '_get_gdn2_fn', _stub_get_gdn2_fn)
    yield


# ---------------------------------------------------------------------------
# Import probe after patching (imports happen at module level; we need to
# re-trigger GDN2MemoryModule construction after the patch, so adapters are
# built inside test methods — that's already the case).
# ---------------------------------------------------------------------------

from benchmark.mqar_capacity_probe import (  # noqa: E402
    GDN2Adapter,
    LinearAttnAdapter,
    FLAGatedDeltaNetAdapter,
    FFN,
    MQARBackbone,
    MQARModel,
    build_mqar_batch,
    compute_verdict,
    _FLA_AVAILABLE,
)


# ---------------------------------------------------------------------------
# Test 1 — Sequence construction
# ---------------------------------------------------------------------------

class TestMQARSequenceConstruction:
    """Verify build_mqar_batch produces correct sequences."""

    @pytest.mark.parametrize("n_kv", [4, 8, 16])
    def test_prefix_contains_all_kv_pairs(self, n_kv: int):
        """Prefix (first 2*n_kv tokens) must contain all key-value pairs."""
        T = 256
        V = 8192
        device = torch.device('cpu')

        seq_ids, targets, query_mask = build_mqar_batch(
            batch_size=4, T=T, n_kv=n_kv, V=V, device=device, seed=42
        )
        seq_np = seq_ids.cpu().numpy()   # (B, T)

        prefix_len = 2 * n_kv
        for b in range(seq_np.shape[0]):
            prefix = seq_np[b, :prefix_len]
            # Key positions (0, 2, 4, ...) must be in [1, V//2)
            key_positions = np.arange(0, prefix_len, 2)
            val_positions = np.arange(1, prefix_len, 2)

            keys   = prefix[key_positions]
            values = prefix[val_positions]

            assert np.all(keys >= 1) and np.all(keys < V // 2), (
                f"Batch {b}: key ids out of range [1,{V//2}): {keys}"
            )
            assert np.all(values >= V // 2) and np.all(values < V), (
                f"Batch {b}: value ids out of range [{V//2},{V}): {values}"
            )
            # All keys are distinct
            assert len(np.unique(keys)) == n_kv, (
                f"Batch {b}: duplicate keys found"
            )

    @pytest.mark.parametrize("n_kv", [4, 8])
    def test_query_target_matches_paired_value(self, n_kv: int):
        """Each query token must point to the correct value in prefix."""
        T = 256
        V = 8192
        device = torch.device('cpu')

        seq_ids, targets, query_mask = build_mqar_batch(
            batch_size=4, T=T, n_kv=n_kv, V=V, device=device, seed=7
        )
        seq_np      = seq_ids.cpu().numpy()
        targets_np  = targets.cpu().numpy()
        qmask_np    = query_mask.cpu().numpy()

        prefix_len = 2 * n_kv

        for b in range(seq_np.shape[0]):
            # Build key→value map from prefix
            kv_map = {}
            for i in range(n_kv):
                k = seq_np[b, 2 * i]
                v = seq_np[b, 2 * i + 1]
                kv_map[int(k)] = int(v)

            # Check every query position
            query_positions = np.where(qmask_np[b])[0]
            assert len(query_positions) == n_kv, (
                f"Batch {b}: expected {n_kv} queries, got {len(query_positions)}"
            )
            for pos in query_positions:
                assert pos >= prefix_len, (
                    f"Batch {b}: query at pos={pos} is inside prefix (< {prefix_len})"
                )
                q_key = int(seq_np[b, pos])
                t_val = int(targets_np[b, pos])
                assert q_key in kv_map, (
                    f"Batch {b} pos {pos}: query key {q_key} not in prefix"
                )
                assert kv_map[q_key] == t_val, (
                    f"Batch {b} pos {pos}: expected target {kv_map[q_key]}, "
                    f"got {t_val}"
                )

    def test_shapes(self):
        """Check output tensor shapes."""
        T = 256
        V = 8192
        B = 8
        n_kv = 4
        device = torch.device('cpu')
        seq_ids, targets, query_mask = build_mqar_batch(
            batch_size=B, T=T, n_kv=n_kv, V=V, device=device, seed=0
        )
        assert seq_ids.shape   == (B, T), f"seq_ids shape: {seq_ids.shape}"
        assert targets.shape   == (B, T), f"targets shape: {targets.shape}"
        assert query_mask.shape == (B, T), f"query_mask shape: {query_mask.shape}"
        assert seq_ids.dtype   == torch.long
        assert targets.dtype   == torch.long
        assert query_mask.dtype == torch.bool

    def test_non_query_targets_are_minus100(self):
        """Targets at non-query positions must be -100 (ignore_index)."""
        seq_ids, targets, query_mask = build_mqar_batch(
            batch_size=4, T=256, n_kv=8, V=8192,
            device=torch.device('cpu'), seed=123
        )
        t = targets.cpu().numpy()
        m = query_mask.cpu().numpy()
        # Non-query positions must be -100
        assert np.all(t[~m] == -100), "Non-query positions should be -100"
        # Query positions must NOT be -100
        assert np.all(t[m] != -100), "Query positions should not be -100"


# ---------------------------------------------------------------------------
# Test 2 — Random baseline value
# ---------------------------------------------------------------------------

class TestRandomBaseline:
    def test_random_baseline(self):
        """random baseline = 1/(V/2)."""
        V = 8192
        expected = 1.0 / (V // 2)  # = 1/4096 ≈ 0.000244
        assert abs(expected - 1.0 / 4096) < 1e-9
        # Also verify the formula used in the probe matches
        assert abs(1.0 / (V // 2) - expected) < 1e-9

    def test_random_baseline_value_matches_prereg(self):
        """PREREG: V=8192, random_baseline = 1/4096."""
        V = 8192
        rb = 1.0 / (V // 2)
        assert rb == pytest.approx(1.0 / 4096, rel=1e-6)


# ---------------------------------------------------------------------------
# Test 3 — Both arms forward pass (CPU, tiny config)
# ---------------------------------------------------------------------------

class TestArmForwardPass:
    """Verify both arms can process sequences without errors (CPU only)."""

    # Tiny config: small model that runs quickly on CPU
    D_MODEL = 64
    D_HEAD  = 32    # must evenly divide D_MODEL; 64 % 32 == 0
    N_HEADS = 1
    T       = 32    # short sequence
    B       = 2
    V       = 64    # tiny vocab for speed
    N_KV    = 4

    def _make_model(self, arm: str) -> MQARModel:
        if arm == 'gdn2':
            adapter = GDN2Adapter(
                d_model=self.D_MODEL, d_head=self.D_HEAD,
                n_heads=self.N_HEADS, max_seq_len=self.T,
            )
        else:
            adapter = LinearAttnAdapter(
                d_model=self.D_MODEL, d_head=self.D_HEAD,
                n_heads=self.N_HEADS, max_seq_len=self.T,
            )
        return MQARModel(
            V=self.V, d_model=self.D_MODEL, d_head=self.D_HEAD,
            adapter=adapter, n_heads=self.N_HEADS,
            continuous_key=False, n_kv=self.N_KV,
        )

    @pytest.mark.parametrize("arm", ["gdn2", "linear_attn"])
    def test_forward_no_crash(self, arm: str):
        """Both arms must complete a forward pass without exception."""
        device = torch.device('cpu')
        model = self._make_model(arm).to(device)

        seq_ids, targets, query_mask = build_mqar_batch(
            batch_size=self.B, T=self.T, n_kv=self.N_KV,
            V=self.V, device=device, seed=0,
        )
        logits = model(seq_ids, cont_keys=None)
        assert logits.shape == (self.B, self.T, self.V), (
            f"{arm}: expected logits {(self.B, self.T, self.V)}, got {logits.shape}"
        )
        # Must be finite
        assert torch.isfinite(logits).all(), f"{arm}: logits contain NaN/Inf"

    @pytest.mark.parametrize("arm", ["gdn2", "linear_attn"])
    def test_loss_backward_no_crash(self, arm: str):
        """Backward pass must complete without error."""
        device = torch.device('cpu')
        model = self._make_model(arm).to(device)

        seq_ids, targets, query_mask = build_mqar_batch(
            batch_size=self.B, T=self.T, n_kv=self.N_KV,
            V=self.V, device=device, seed=1,
        )
        logits = model(seq_ids, cont_keys=None)
        B, Tlen, Vsize = logits.shape
        loss = torch.nn.functional.cross_entropy(
            logits.reshape(B * Tlen, Vsize),
            targets.reshape(B * Tlen),
            ignore_index=-100,
        )
        assert torch.isfinite(loss), f"{arm}: loss is {loss}"
        loss.backward()  # must not raise

    @pytest.mark.parametrize("arm", ["gdn2", "linear_attn"])
    def test_continuous_key_forward(self, arm: str):
        """Continuous key mode: forward pass must work."""
        device = torch.device('cpu')
        adapter_cls = GDN2Adapter if arm == 'gdn2' else LinearAttnAdapter
        adapter = adapter_cls(
            d_model=self.D_MODEL, d_head=self.D_HEAD,
            n_heads=self.N_HEADS, max_seq_len=self.T,
        )
        model = MQARModel(
            V=self.V, d_model=self.D_MODEL, d_head=self.D_HEAD,
            adapter=adapter, n_heads=self.N_HEADS,
            continuous_key=True, n_kv=self.N_KV,
        ).to(device)

        seq_ids, targets, query_mask = build_mqar_batch(
            batch_size=self.B, T=self.T, n_kv=self.N_KV,
            V=self.V, device=device, seed=2,
            continuous_key=True, d_head=self.D_HEAD, noise_sigma=0.1,
        )
        logits = model(seq_ids, cont_keys=seq_ids._cont_keys)
        assert logits.shape == (self.B, self.T, self.V)
        assert torch.isfinite(logits).all()


# ---------------------------------------------------------------------------
# Test 3b — 2-layer backbone structure (VLA §5.1 fix)
# ---------------------------------------------------------------------------

class TestTwoLayerBackbone:
    """
    Verify the 2-layer MQARBackbone:
      - correct output shape
      - contains FFN and LN per layer
      - both arms (gdn2, linear_attn) have matching non-mixer param counts ±5%
      - forward pass is differentiable
    """

    D_MODEL  = 64
    D_HEAD   = 32
    N_HEADS  = 1
    T        = 32
    B        = 2
    V        = 64
    N_KV     = 4
    N_LAYERS = 2

    def _make_backbone(self, arm: str) -> MQARBackbone:
        """Build a 2-layer backbone for the given arm."""
        if arm == 'gdn2':
            mixers = [
                GDN2Adapter(d_model=self.D_MODEL, d_head=self.D_HEAD,
                            n_heads=self.N_HEADS, max_seq_len=self.T)
                for _ in range(self.N_LAYERS)
            ]
        else:
            mixers = [
                LinearAttnAdapter(d_model=self.D_MODEL, d_head=self.D_HEAD,
                                  n_heads=self.N_HEADS, max_seq_len=self.T)
                for _ in range(self.N_LAYERS)
            ]
        return MQARBackbone(d_model=self.D_MODEL, mixers=mixers, n_layers=self.N_LAYERS)

    def test_backbone_output_shape(self):
        """Backbone must return (B, T, d_model) unchanged shape."""
        backbone = self._make_backbone('gdn2')
        x = torch.randn(self.B, self.T, self.D_MODEL)
        out = backbone(x)
        assert out.shape == (self.B, self.T, self.D_MODEL), (
            f"Expected shape {(self.B, self.T, self.D_MODEL)}, got {out.shape}"
        )

    def test_backbone_has_two_layers(self):
        """Backbone must contain exactly n_layers mixer/FFN/LN sets."""
        backbone = self._make_backbone('linear_attn')
        assert len(backbone.mixers)      == self.N_LAYERS, "Wrong number of mixer layers"
        assert len(backbone.ffns)        == self.N_LAYERS, "Wrong number of FFN layers"
        assert len(backbone.mixer_norms) == self.N_LAYERS, "Wrong number of mixer LN layers"
        assert len(backbone.ffn_norms)   == self.N_LAYERS, "Wrong number of FFN LN layers"

    def test_ffn_structure(self):
        """FFN must have fc1 (d→4d) and fc2 (4d→d)."""
        ffn = FFN(d_model=self.D_MODEL, expand=4)
        assert ffn.fc1.in_features  == self.D_MODEL
        assert ffn.fc1.out_features == self.D_MODEL * 4
        assert ffn.fc2.in_features  == self.D_MODEL * 4
        assert ffn.fc2.out_features == self.D_MODEL
        # Check forward shape
        x = torch.randn(self.B, self.T, self.D_MODEL)
        out = ffn(x)
        assert out.shape == x.shape

    @pytest.mark.parametrize("arm", ["gdn2", "linear_attn"])
    def test_two_layer_model_forward(self, arm: str):
        """2-layer MQARModel must produce correct logits shape."""
        backbone = self._make_backbone(arm)
        model = MQARModel(
            V=self.V, d_model=self.D_MODEL, d_head=self.D_HEAD,
            backbone=backbone, n_heads=self.N_HEADS,
            continuous_key=False, n_kv=self.N_KV,
        )
        seq_ids, targets, query_mask = build_mqar_batch(
            batch_size=self.B, T=self.T, n_kv=self.N_KV,
            V=self.V, device=torch.device('cpu'), seed=99,
        )
        logits = model(seq_ids, cont_keys=None)
        assert logits.shape == (self.B, self.T, self.V), (
            f"{arm}: expected {(self.B, self.T, self.V)}, got {logits.shape}"
        )
        assert torch.isfinite(logits).all(), f"{arm}: logits contain NaN/Inf"

    def test_non_mixer_param_parity(self):
        """
        Non-mixer parameters must be equal in count for both arms (±5% ACCEPTANCE).
        Mixer parameters are excluded from comparison.
        """
        gdn2_bb  = self._make_backbone('gdn2')
        la_bb    = self._make_backbone('linear_attn')

        def non_mixer_numel(bb: MQARBackbone) -> int:
            mixer_ids = {id(p) for m in bb.mixers for p in m.parameters()}
            return sum(
                p.numel() for p in bb.parameters() if id(p) not in mixer_ids
            )

        g2_count = non_mixer_numel(gdn2_bb)
        la_count = non_mixer_numel(la_bb)

        assert g2_count > 0, "gdn2 backbone has no non-mixer parameters?"
        assert la_count > 0, "linear_attn backbone has no non-mixer parameters?"

        # Must be identical (same FFN + LN structure)
        rel_diff = abs(g2_count - la_count) / max(g2_count, la_count)
        assert rel_diff <= 0.05, (
            f"Non-mixer param count mismatch: gdn2={g2_count}, la={la_count}, "
            f"rel_diff={rel_diff:.3f} > 0.05"
        )

    @pytest.mark.parametrize("arm", ["gdn2", "linear_attn"])
    def test_backward_through_two_layers(self, arm: str):
        """Gradients must flow through both layers."""
        backbone = self._make_backbone(arm)
        model = MQARModel(
            V=self.V, d_model=self.D_MODEL, d_head=self.D_HEAD,
            backbone=backbone, n_heads=self.N_HEADS,
            continuous_key=False, n_kv=self.N_KV,
        )
        seq_ids, targets, _ = build_mqar_batch(
            batch_size=self.B, T=self.T, n_kv=self.N_KV,
            V=self.V, device=torch.device('cpu'), seed=42,
        )
        logits = model(seq_ids)
        B, Tlen, Vs = logits.shape
        loss = torch.nn.functional.cross_entropy(
            logits.reshape(B * Tlen, Vs),
            targets.reshape(B * Tlen),
            ignore_index=-100,
        )
        loss.backward()
        # Check that FFN and LN layers received gradients (always in graph).
        # Mixer params: some may have None grad when use_frangi=False (proj_erase,
        # proj_g are zeroed in the stateless path and skipped in the gdn2 no-frangi
        # path) — this is expected; we only assert FFN/LN are grad-connected.
        for i, ffn in enumerate(backbone.ffns):
            for name, p in ffn.named_parameters():
                assert p.grad is not None, (
                    f"{arm} FFN layer {i} param '{name}' has no gradient after backward"
                )
        for i, (mn, fn) in enumerate(zip(backbone.mixer_norms, backbone.ffn_norms)):
            for norm, label in [(mn, 'mixer_norm'), (fn, 'ffn_norm')]:
                # When the mixer has has_internal_residual=True (GDN2Adapter /
                # LinearAttnAdapter), the backbone skips mixer_norms[i] entirely —
                # these LN params are unused in the forward path and have no gradient.
                # Only assert grad for mixer_norm when the mixer does NOT own its residual.
                mixer_has_internal_residual = getattr(backbone.mixers[i],
                                                      'has_internal_residual', False)
                if label == 'mixer_norm' and mixer_has_internal_residual:
                    # mixer_norm is bypassed (dead weight) — no gradient expected
                    continue
                for name, p in norm.named_parameters():
                    assert p.grad is not None, (
                        f"{arm} layer {i} {label} param '{name}' has no gradient"
                    )


# ---------------------------------------------------------------------------
# Test 4 — Verdict function on synthetic CSVs
# ---------------------------------------------------------------------------

def _make_csv(rows: list[dict]) -> Path:
    """Write synthetic CSV to a temp file, return path."""
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.csv', delete=False, newline=''
    )
    fieldnames = ['arm', 'n_kv', 'd_head', 'lr', 'seed',
                  'final_acc', 'steps', 'converged']
    writer = csv.DictWriter(tmp, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    tmp.close()
    return Path(tmp.name)


def _base_row(arm, n_kv, lr, seed, final_acc):
    return {
        'arm': arm, 'n_kv': n_kv, 'd_head': 64,
        'lr': lr, 'seed': seed, 'final_acc': final_acc,
        'steps': 1500, 'converged': int(final_acc > 0.9),
    }


class TestVerdictFunction:
    """Verdict on synthetic CSVs."""

    def test_verdict_live(self):
        """
        Scenario: GDN-2 clearly wins at n=32 (gap > 0.15, gdn2>0.5, la<0.5,
        std < 0.05), sanity n=4 both pass.
        """
        rows = []
        # Sanity: n=4 both arms converge
        for seed in (0, 1):
            rows.append(_base_row('gdn2',        4, 1e-3, seed, 0.95))
            rows.append(_base_row('linear_attn', 4, 1e-3, seed, 0.93))

        # n=16: both do ok, no clear winner
        for seed in (0, 1):
            rows.append(_base_row('gdn2',        16, 1e-3, seed, 0.48))
            rows.append(_base_row('linear_attn', 16, 1e-3, seed, 0.45))

        # n=32: GDN-2 wins clearly (gap=0.40 > 0.15, gdn2>0.5, la<0.5, std~0)
        for seed in (0, 1):
            rows.append(_base_row('gdn2',        32, 1e-3, seed, 0.72))
            rows.append(_base_row('linear_attn', 32, 1e-3, seed, 0.32))

        # n=64: both collapse
        for seed in (0, 1):
            rows.append(_base_row('gdn2',        64, 1e-3, seed, 0.25))
            rows.append(_base_row('linear_attn', 64, 1e-3, seed, 0.21))

        csv_path = _make_csv(rows)
        try:
            verdict = compute_verdict(csv_path, prereg_delta=0.15)
            assert verdict['verdict'] == 'LIVE', (
                f"Expected LIVE, got {verdict['verdict']}. "
                f"live_windows={verdict['live_windows']}"
            )
            live_ns = [w['n_kv'] for w in verdict['live_windows']]
            assert 32 in live_ns, f"Expected n=32 in live windows, got {live_ns}"
        finally:
            os.unlink(csv_path)

    def test_verdict_dead_no_gap(self):
        """
        Scenario: gap < 0.15 everywhere (both arms track each other).
        """
        rows = []
        # Sanity: n=4 both pass
        for seed in (0, 1):
            rows.append(_base_row('gdn2',        4, 1e-3, seed, 0.95))
            rows.append(_base_row('linear_attn', 4, 1e-3, seed, 0.92))

        # All n_kv: small gap < 0.15
        for n_kv in (8, 16, 32, 64, 96):
            for seed in (0, 1):
                # GDN-2 slightly ahead but never > 0.15 gap
                rows.append(_base_row('gdn2',        n_kv, 1e-3, seed, 0.40 + seed * 0.05))
                rows.append(_base_row('linear_attn', n_kv, 1e-3, seed, 0.38 + seed * 0.05))

        csv_path = _make_csv(rows)
        try:
            verdict = compute_verdict(csv_path, prereg_delta=0.15)
            assert verdict['verdict'] == 'DEAD', (
                f"Expected DEAD, got {verdict['verdict']}"
            )
            assert len(verdict['live_windows']) == 0
        finally:
            os.unlink(csv_path)

    def test_verdict_dead_sanity_fail(self):
        """
        Scenario: n=4 sanity gate fails (both arms never reach 0.9).
        Even if fake gap > 0.15 at n=32, verdict should be DEAD_SANITY_FAIL.
        """
        rows = []
        # n=4: failed convergence
        for seed in (0, 1):
            rows.append(_base_row('gdn2',        4, 1e-3, seed, 0.55))  # < 0.9
            rows.append(_base_row('linear_attn', 4, 1e-3, seed, 0.50))  # < 0.9

        # n=32: fake large gap (should be ignored due to sanity fail)
        for seed in (0, 1):
            rows.append(_base_row('gdn2',        32, 1e-3, seed, 0.80))
            rows.append(_base_row('linear_attn', 32, 1e-3, seed, 0.30))

        csv_path = _make_csv(rows)
        try:
            verdict = compute_verdict(csv_path, prereg_delta=0.15)
            assert verdict['verdict'] == 'DEAD_SANITY_FAIL', (
                f"Expected DEAD_SANITY_FAIL, got {verdict['verdict']}"
            )
            assert not verdict['sanity_gate']['pass']
        finally:
            os.unlink(csv_path)

    def test_verdict_dead_la_not_collapsed(self):
        """
        Scenario: gap > 0.15 at n=32 BUT la >= 0.5 (la hasn't collapsed).
        Should be DEAD (condition c fails: acc_la must be < 0.5).
        """
        rows = []
        # Sanity ok
        for seed in (0, 1):
            rows.append(_base_row('gdn2',        4, 1e-3, seed, 0.95))
            rows.append(_base_row('linear_attn', 4, 1e-3, seed, 0.93))

        # n=32: gap=0.21 > 0.15, gdn2=0.75>0.5, BUT la=0.54 >= 0.5 → DEAD
        for seed in (0, 1):
            rows.append(_base_row('gdn2',        32, 1e-3, seed, 0.75))
            rows.append(_base_row('linear_attn', 32, 1e-3, seed, 0.54))

        csv_path = _make_csv(rows)
        try:
            verdict = compute_verdict(csv_path, prereg_delta=0.15)
            # la >= 0.5 at n=32, so condition (c) fails → no live window at n=32
            n32_live = [w for w in verdict['live_windows'] if w['n_kv'] == 32]
            assert len(n32_live) == 0, (
                f"n=32 should NOT be live (la not collapsed), got {n32_live}"
            )
        finally:
            os.unlink(csv_path)

    def test_verdict_lr_best_selected(self):
        """
        Verdict must take best lr per (arm, n_kv, seed) — not average.
        If one lr gives acc=0.95 and another gives 0.2, result should be 0.95.
        """
        rows = []
        # n=4 sanity
        for seed in (0, 1):
            rows.append(_base_row('gdn2',        4, 1e-3, seed, 0.95))
            rows.append(_base_row('linear_attn', 4, 1e-3, seed, 0.93))

        # n=32: gdn2 only good at lr=1e-3, bad at lr=1e-4
        # linear_attn: bad at all lrs
        for seed in (0, 1):
            rows.append(_base_row('gdn2', 32, 1e-3, seed, 0.75))  # good lr
            rows.append(_base_row('gdn2', 32, 1e-4, seed, 0.20))  # bad lr
            rows.append(_base_row('linear_attn', 32, 1e-3, seed, 0.30))
            rows.append(_base_row('linear_attn', 32, 1e-4, seed, 0.28))

        csv_path = _make_csv(rows)
        try:
            verdict = compute_verdict(csv_path, prereg_delta=0.15)
            # Best lr should give gdn2@32 = 0.75, la@32 = 0.30 → gap=0.45 > 0.15
            live_ns = [w['n_kv'] for w in verdict['live_windows']]
            assert 32 in live_ns, (
                f"Expected n=32 live (best-lr logic), got live_ns={live_ns}, "
                f"verdict={verdict['verdict']}"
            )
        finally:
            os.unlink(csv_path)

    def test_gap_table_keys_are_strings(self):
        """gap_table keys must be strings (JSON-serialisable)."""
        rows = []
        for seed in (0, 1):
            rows.append(_base_row('gdn2',        4, 1e-3, seed, 0.95))
            rows.append(_base_row('linear_attn', 4, 1e-3, seed, 0.93))

        csv_path = _make_csv(rows)
        try:
            verdict = compute_verdict(csv_path, prereg_delta=0.15)
            for k in verdict['gap_table']:
                assert isinstance(k, str), f"gap_table key must be str, got {type(k)}"
            # Ensure it round-trips through JSON without error
            json_str = json.dumps(verdict)
            reloaded = json.loads(json_str)
            assert '4' in reloaded['gap_table']
        finally:
            os.unlink(csv_path)


# ---------------------------------------------------------------------------
# Test 5 — FLA GatedDeltaNet cross-validation arm (gdn2_fla)
# ---------------------------------------------------------------------------

class TestFLAGatedDeltaNetArm:
    """
    Tests for the gdn2_fla cross-validation arm (FLAGatedDeltaNetAdapter).

    Two test categories:
      A. No-fla path (always runs): verify ImportError is raised gracefully when
         fla is absent and that the adapter guard behaves correctly.
      B. With-fla path (skipped when fla absent): verify the adapter builds,
         forward pass shape/finiteness, and backward works.
         Uses pytest.importorskip("fla") to skip when fla not installed.

    NOTE: True convergence verification must run on HPC (fla + CUDA). These
    tests only verify adapter wiring and interface compatibility.
    """

    D_MODEL  = 64    # small for speed; must satisfy num_heads*head_dim*2 <= d_model
    T        = 32
    B        = 2
    V        = 64
    N_KV     = 4
    # fla params: num_heads=2, head_dim=16 → key_dim=32, value_dim=64=D_MODEL ✓
    # (Use head_dim=16 for D_MODEL=64 to satisfy integer constraint)
    FLA_NUM_HEADS = 2
    FLA_HEAD_DIM  = 16   # key_dim=32 ≤ 64=D_MODEL, value_dim=64=D_MODEL (expand_v=2)
    FLA_CONV_SIZE = 4

    # --- Path A: fla absent → ImportError raised, not silenced ---

    def test_import_error_when_fla_absent(self, monkeypatch):
        """
        When fla is not installed, constructing FLAGatedDeltaNetAdapter must
        raise ImportError with a helpful message (not silently fail/crash later).
        This test always runs regardless of fla availability.
        """
        import benchmark.mqar_capacity_probe as _probe_mod
        # Force _FLA_AVAILABLE=False for this test even if fla happens to be present
        monkeypatch.setattr(_probe_mod, '_FLA_AVAILABLE', False)

        with pytest.raises(ImportError, match="flash-linear-attention"):
            FLAGatedDeltaNetAdapter(d_model=self.D_MODEL)

    def test_train_one_config_raises_when_fla_absent(self, monkeypatch):
        """
        train_one_config(arm='gdn2_fla') must raise ImportError when fla absent.
        """
        import benchmark.mqar_capacity_probe as _probe_mod
        monkeypatch.setattr(_probe_mod, '_FLA_AVAILABLE', False)

        from benchmark.mqar_capacity_probe import train_one_config
        device = torch.device('cpu')
        with pytest.raises(ImportError, match="flash-linear-attention"):
            train_one_config(
                arm='gdn2_fla', n_kv=self.N_KV, d_head=16,
                lr=1e-3, seed=0, T=self.T, V=self.V,
                steps=1, device=device,
                d_model=self.D_MODEL,
            )

    # --- Path B: fla present (skip when absent) ---

    @pytest.mark.skipif(not _FLA_AVAILABLE, reason="fla not installed — HPC only")
    def test_adapter_builds_with_fla(self):
        """When fla is installed, FLAGatedDeltaNetAdapter must construct without error."""
        adapter = FLAGatedDeltaNetAdapter(
            d_model=self.D_MODEL,
            num_heads=self.FLA_NUM_HEADS,
            head_dim=self.FLA_HEAD_DIM,
            conv_size=self.FLA_CONV_SIZE,
        )
        assert adapter is not None
        assert hasattr(adapter, 'layer'), "Adapter must expose .layer (FLA GatedDeltaNet)"

    @pytest.mark.skipif(not _FLA_AVAILABLE, reason="fla not installed — HPC only")
    def test_adapter_forward_shape(self):
        """FLAGatedDeltaNetAdapter forward: (B, T, d_model) → (B, T, d_model)."""
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        adapter = FLAGatedDeltaNetAdapter(
            d_model=self.D_MODEL,
            num_heads=self.FLA_NUM_HEADS,
            head_dim=self.FLA_HEAD_DIM,
            conv_size=self.FLA_CONV_SIZE,
        ).to(device)
        x = torch.randn(self.B, self.T, self.D_MODEL, device=device)
        out = adapter(x)
        assert out.shape == (self.B, self.T, self.D_MODEL), (
            f"Expected ({self.B}, {self.T}, {self.D_MODEL}), got {out.shape}"
        )
        assert torch.isfinite(out).all(), "Output contains NaN/Inf"

    @pytest.mark.skipif(not _FLA_AVAILABLE, reason="fla not installed — HPC only")
    def test_backbone_with_fla_arm(self):
        """MQARBackbone with gdn2_fla mixers: correct output shape + backward."""
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        mixers = [
            FLAGatedDeltaNetAdapter(
                d_model=self.D_MODEL,
                num_heads=self.FLA_NUM_HEADS,
                head_dim=self.FLA_HEAD_DIM,
                conv_size=self.FLA_CONV_SIZE,
            )
            for _ in range(2)
        ]
        backbone = MQARBackbone(d_model=self.D_MODEL, mixers=mixers, n_layers=2).to(device)
        x = torch.randn(self.B, self.T, self.D_MODEL, device=device)
        out = backbone(x)
        assert out.shape == (self.B, self.T, self.D_MODEL)
        assert torch.isfinite(out).all()
        # Backward
        out.sum().backward()
        # FFN should have gradients
        for ffn in backbone.ffns:
            for name, p in ffn.named_parameters():
                assert p.grad is not None, f"FFN param '{name}' has no gradient"

    @pytest.mark.skipif(not _FLA_AVAILABLE, reason="fla not installed — HPC only")
    def test_model_forward_loss_backward_fla(self):
        """Full MQARModel with gdn2_fla arm: forward + loss + backward on tiny config."""
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        mixers = [
            FLAGatedDeltaNetAdapter(
                d_model=self.D_MODEL,
                num_heads=self.FLA_NUM_HEADS,
                head_dim=self.FLA_HEAD_DIM,
                conv_size=self.FLA_CONV_SIZE,
            )
            for _ in range(2)
        ]
        backbone = MQARBackbone(d_model=self.D_MODEL, mixers=mixers, n_layers=2)
        model = MQARModel(
            V=self.V, d_model=self.D_MODEL, d_head=self.FLA_HEAD_DIM,
            backbone=backbone, n_heads=self.FLA_NUM_HEADS,
            continuous_key=False, n_kv=self.N_KV,
        ).to(device)

        seq_ids, targets, query_mask = build_mqar_batch(
            batch_size=self.B, T=self.T, n_kv=self.N_KV,
            V=self.V, device=device, seed=0,
        )
        logits = model(seq_ids, cont_keys=None)
        assert logits.shape == (self.B, self.T, self.V)
        assert torch.isfinite(logits).all()

        B, Tlen, Vsize = logits.shape
        loss = torch.nn.functional.cross_entropy(
            logits.reshape(B * Tlen, Vsize),
            targets.reshape(B * Tlen),
            ignore_index=-100,
        )
        assert torch.isfinite(loss), f"Loss is {loss}"
        loss.backward()  # must not raise

    # --- Path C: mock-based construction test (always runs, validates wiring) ---

    def test_adapter_uses_correct_fla_params_via_mock(self, monkeypatch):
        """
        Verify FLAGatedDeltaNetAdapter passes the correct parameters to the
        FLA GatedDeltaNet constructor (use_short_conv=True, conv_size=4, etc.)
        using a mock — runs on CPU without fla installed.
        """
        import benchmark.mqar_capacity_probe as _probe_mod

        # Build a fake GatedDeltaNet that records constructor kwargs
        captured_kwargs = {}

        class FakeGatedDeltaNet(nn.Module):
            def __init__(self, **kwargs):
                super().__init__()
                captured_kwargs.update(kwargs)

            def forward(self, x):
                return x, None, None

        # Temporarily patch _FLA_AVAILABLE=True and inject FakeGatedDeltaNet
        monkeypatch.setattr(_probe_mod, '_FLA_AVAILABLE', True)
        monkeypatch.setattr(_probe_mod, '_FLAGatedDeltaNet', FakeGatedDeltaNet)

        adapter = FLAGatedDeltaNetAdapter(
            d_model=self.D_MODEL,
            num_heads=self.FLA_NUM_HEADS,
            head_dim=self.FLA_HEAD_DIM,
            conv_size=self.FLA_CONV_SIZE,
        )

        # Verify all official config params were passed correctly
        assert captured_kwargs.get('hidden_size') == self.D_MODEL, (
            f"hidden_size should be {self.D_MODEL}, got {captured_kwargs.get('hidden_size')}"
        )
        assert captured_kwargs.get('num_heads') == self.FLA_NUM_HEADS, (
            f"num_heads should be {self.FLA_NUM_HEADS}, got {captured_kwargs.get('num_heads')}"
        )
        assert captured_kwargs.get('head_dim') == self.FLA_HEAD_DIM, (
            f"head_dim should be {self.FLA_HEAD_DIM}, got {captured_kwargs.get('head_dim')}"
        )
        assert captured_kwargs.get('use_short_conv') is True, (
            "use_short_conv must be True (Zoology/FLA MQAR standard: 'crucial, do not turn off')"
        )
        assert captured_kwargs.get('conv_size') == self.FLA_CONV_SIZE, (
            f"conv_size should be {self.FLA_CONV_SIZE}, got {captured_kwargs.get('conv_size')}"
        )
        assert captured_kwargs.get('expand_v') == 2.0, (
            f"expand_v should be 2.0 (FLA default), got {captured_kwargs.get('expand_v')}"
        )
        assert captured_kwargs.get('mode') == 'chunk', (
            "mode must be 'chunk' (FLA training requirement)"
        )

    def test_adapter_forward_via_mock(self, monkeypatch):
        """
        Verify FLAGatedDeltaNetAdapter.forward correctly unpacks the FLA tuple
        (o, None, past_kv) and returns only o with the correct shape.
        Uses a mock — runs on CPU without fla installed.
        """
        import benchmark.mqar_capacity_probe as _probe_mod

        expected_out = torch.zeros(self.B, self.T, self.D_MODEL)

        class FakeGatedDeltaNet(nn.Module):
            def __init__(self, **kwargs):
                super().__init__()

            def forward(self, hidden_states, **kwargs):
                # FLA returns (o, None, past_key_values)
                return expected_out, None, None

        monkeypatch.setattr(_probe_mod, '_FLA_AVAILABLE', True)
        monkeypatch.setattr(_probe_mod, '_FLAGatedDeltaNet', FakeGatedDeltaNet)

        adapter = FLAGatedDeltaNetAdapter(d_model=self.D_MODEL)
        x = torch.randn(self.B, self.T, self.D_MODEL)
        out = adapter(x)

        assert out.shape == (self.B, self.T, self.D_MODEL), (
            f"Adapter forward must return (B, T, d_model), got {out.shape}"
        )
        # Must be the first element of the tuple (o), not the tuple itself
        assert isinstance(out, torch.Tensor), f"Return must be Tensor, got {type(out)}"
