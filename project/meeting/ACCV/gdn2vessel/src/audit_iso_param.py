"""
audit_iso_param.py — Iso-parameter audit script for A1'/A2 ablation arms (M5).

Verifies two things after one backward pass:
  1. A1' proj_erase.weight.grad / proj_g.weight.grad / alpha_e.grad norms > 0
     (confirms M4 fix: these are no longer dead parameters).
  2. Trainable parameter count of A1' vs A2 differs by ≤±5%
     (ACCEPTANCE_CRITERIA P4 pre-registered iso-parametric hard constraint).

Usage::

    python src/audit_iso_param.py
    python src/audit_iso_param.py --base_ch 32 --d_head 64 --n_heads 1

Prints a table suitable for paper appendix / audit trail.

Windows-safe: no scipy, no spawn issues (no DataLoader), pure CPU.
"""

from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path

import torch
import torch.nn.functional as F

# ---------------------------------------------------------------------------
#  Path setup
# ---------------------------------------------------------------------------

_src = Path(__file__).parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))


# ---------------------------------------------------------------------------
#  Mock FLA (only needed if fla not installed; auto-skipped if installed)
# ---------------------------------------------------------------------------

def _patch_fla_if_needed() -> None:
    """Mock FLA kernel for CPU-only audit (no GPU kernel needed)."""
    if 'fla' in sys.modules:
        return  # already loaded (real or previously mocked)

    def _fake_gdn2_fn(q, k, v, beta, g, output_final_state=False):
        B, T, nh, dh = v.shape
        state = torch.zeros(B, nh, dh, dh) if output_final_state else None
        return v.clone(), state

    fake_fla   = types.ModuleType('fla')
    fake_ops   = types.ModuleType('fla.ops')
    fake_gdr   = types.ModuleType('fla.ops.gated_delta_rule')
    fake_naive = types.ModuleType('fla.ops.gated_delta_rule.naive')
    fake_chunk = types.ModuleType('fla.ops.gated_delta_rule.chunk')
    fake_naive.naive_chunk_gated_delta_rule = _fake_gdn2_fn
    fake_chunk.chunk_gated_delta_rule       = _fake_gdn2_fn
    sys.modules.setdefault('fla',                              fake_fla)
    sys.modules.setdefault('fla.ops',                          fake_ops)
    sys.modules.setdefault('fla.ops.gated_delta_rule',         fake_gdr)
    sys.modules.setdefault('fla.ops.gated_delta_rule.naive',   fake_naive)
    sys.modules.setdefault('fla.ops.gated_delta_rule.chunk',   fake_chunk)


_patch_fla_if_needed()

from models.unet_gdn2 import UNetGDN2  # noqa: E402


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _count_params(model: torch.nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def _run_backward(model: torch.nn.Module, H: int = 64, W: int = 64) -> None:
    """Run a dummy forward+backward to populate all .grad fields."""
    model.train()
    for p in model.parameters():
        p.grad = None
    x = torch.randn(1, 1, H, W)
    logits = model(x)
    loss = logits.sum()
    loss.backward()


def _grad_norm(param: torch.nn.Parameter) -> float:
    if param.grad is None:
        return 0.0
    return float(param.grad.norm().item())


# ---------------------------------------------------------------------------
#  Audit function
# ---------------------------------------------------------------------------

def audit_iso_param(
    base_ch: int = 32,
    d_head: int = 64,
    n_heads: int = 1,
    image_size: int = 64,
) -> dict:
    """
    Run iso-parameter audit for given model config.

    Returns dict with:
      'n_a2', 'n_a1p', 'n_a0p'      — trainable numel
      'diff_pct'                      — (n_a1p - n_a2) / n_a2 * 100
      'iso_pass'                      — bool: |diff_pct| ≤ 5%
      'proj_erase_grad_norm'          — A1' proj_erase.weight grad norm
      'proj_g_grad_norm'              — A1' proj_g.weight grad norm
      'alpha_e_grad_norm'             — A1' alpha_e grad norm
      'dead_param_pass'               — bool: all three > 0
    """
    # Build three arms
    m_a2 = UNetGDN2(
        in_ch=1, out_ch=1, base_ch=base_ch, d_head=d_head, n_heads=n_heads,
        memory_mode='delta_rule', use_frangi=True,
        use_reid_head=True, reid_d_id=d_head, reid_feat_source='memory',
    )
    m_a1p = UNetGDN2(
        in_ch=1, out_ch=1, base_ch=base_ch, d_head=d_head, n_heads=n_heads,
        memory_mode='linear_attn', use_frangi=True,
        use_reid_head=True, reid_d_id=d_head, reid_feat_source='linear_attn',
    )
    m_a0p = UNetGDN2(
        in_ch=1, out_ch=1, base_ch=base_ch, d_head=d_head, n_heads=n_heads,
        memory_mode='cnn', use_frangi=False,
        use_reid_head=True, reid_d_id=d_head, reid_feat_source='cnn',
    )

    # Numel
    n_a2  = _count_params(m_a2)
    n_a1p = _count_params(m_a1p)
    n_a0p = _count_params(m_a0p)
    diff_pct = (n_a1p - n_a2) / max(n_a2, 1) * 100.0
    iso_pass = abs(diff_pct) <= 5.0

    # Grad norms for A1' dead params (M4 verification)
    _run_backward(m_a1p, H=image_size, W=image_size)

    la = m_a1p.linear_attn
    proj_erase_gn = _grad_norm(la.proj_erase.weight) if la is not None else 0.0
    proj_g_gn     = _grad_norm(la.proj_g.weight)     if la is not None else 0.0
    alpha_e_gn    = _grad_norm(la.alpha_e)            if (la is not None and la.alpha_e is not None) else 0.0

    dead_pass = (proj_erase_gn > 0.0) and (proj_g_gn > 0.0) and (alpha_e_gn > 0.0)

    return {
        'base_ch': base_ch, 'd_head': d_head, 'n_heads': n_heads,
        'n_a2':  n_a2,
        'n_a1p': n_a1p,
        'n_a0p': n_a0p,
        'diff_pct': diff_pct,
        'iso_pass': iso_pass,
        'proj_erase_grad_norm': proj_erase_gn,
        'proj_g_grad_norm':     proj_g_gn,
        'alpha_e_grad_norm':    alpha_e_gn,
        'dead_param_pass': dead_pass,
    }


# ---------------------------------------------------------------------------
#  CLI entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Iso-parameter audit: A1'/A2 dead-param check")
    p.add_argument('--base_ch',    type=int, default=32)
    p.add_argument('--d_head',     type=int, default=64)
    p.add_argument('--n_heads',    type=int, default=1)
    p.add_argument('--image_size', type=int, default=64,
                   help='Spatial size for dummy backward (smaller = faster audit)')
    return p.parse_args()


def _main() -> None:
    args = _parse_args()
    r = audit_iso_param(
        base_ch    = args.base_ch,
        d_head     = args.d_head,
        n_heads    = args.n_heads,
        image_size = args.image_size,
    )

    print()
    print("=" * 70)
    print(f"[ISO-PARAM AUDIT]  base_ch={r['base_ch']}  d_head={r['d_head']}  n_heads={r['n_heads']}")
    print("=" * 70)
    print(f"  {'Arm':<20} {'Trainable params':>20}")
    print(f"  {'-'*20} {'-'*20}")
    print(f"  {'A2  (delta_rule)':<20} {r['n_a2']:>20,}")
    a1p_label = "A1' (linear_attn)"
    print(f"  {a1p_label:<20} {r['n_a1p']:>20,}  diff vs A2: {r['diff_pct']:+.3f}%")
    print(f"  {'A0  (cnn)':<20} {r['n_a0p']:>20,}")
    print()
    iso_label = "PASS" if r['iso_pass'] else "FAIL"
    print(f"  Iso-param check (|diff| ≤ 5%): {iso_label}")
    print()
    print("  A1' dead-param gradient norms (after one dummy backward):")
    print(f"    proj_erase.weight.grad.norm : {r['proj_erase_grad_norm']:.6e}")
    print(f"    proj_g.weight.grad.norm     : {r['proj_g_grad_norm']:.6e}")
    print(f"    alpha_e.grad.norm           : {r['alpha_e_grad_norm']:.6e}")
    dead_label = "PASS (all > 0)" if r['dead_param_pass'] else "FAIL (some == 0 — M4 not applied)"
    print(f"    Dead-param check            : {dead_label}")
    print("=" * 70)
    print()

    if not r['iso_pass']:
        print("ERROR: iso-param FAIL — numel diff exceeds 5%. "
              "Adjust LinearAttnModule projection dims to align.")
        sys.exit(1)
    if not r['dead_param_pass']:
        print("ERROR: dead-param FAIL — proj_erase/proj_g/alpha_e still have zero grad. "
              "M4 fix not applied correctly.")
        sys.exit(1)
    print("All checks passed.")


if __name__ == '__main__':
    _main()
