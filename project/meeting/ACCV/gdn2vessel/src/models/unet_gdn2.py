"""
U-Net + GDN-2 Associative Memory Module for retinal vessel segmentation.

Architecture:
  - Same CNN U-Net backbone as unet.py
  - After the bottleneck (deepest encoder feature), insert a GDN-2 memory module:
      1. Flatten spatial dims → sequence (length = H/16 * W/16, asserted ≤ 1024)
      2. Multi-direction scan (default=1 for single-dir; 2/4 configurable for ablation)
      3. Run naive_chunk_gated_delta_rule (pure PyTorch, zero Triton by default)
      4. Merge outputs across directions (average of o; states NOT merged)
      5. Reshape back to 2D feature map
  - All q/k/v/beta/g projections come from input features (never from GT)
  - Can degrade to pure CNN by setting use_memory=False

Mechanism B — Decoupled erase/write gates modulated by differentiable Frangi:
  - A differentiable Frangi vesselness layer (DifferentiableFrangi) computes
    input-derived vesselness v ∈ [0,1] from the feature map (NEVER from GT).
  - Two separate gate projections are learned:
      proj_write  → write_gate (β in FLA convention): controls write strength
      proj_erase  → erase_gate: controls how much the memory forgets
  - Frangi modulation (blood-vessel evidence):
      write_gate  = sigmoid(proj_write(x)) * (1 + alpha_w * v)  # high v → write more
      erase_gate  = sigmoid(proj_erase(x)) * (1 - alpha_e * v)  # high v → erase less
  - The combined gate passed to FLA kernel is write_gate (β),
    and the decay gate g absorbs erase_gate as an additive correction.

Engineering A — Multi-direction scan (not a core claim, standard 2D reorder):
  STORY_FRAMEWORK § R4: "we adopt a standard reorder; the contribution is the
  associative memory, not the scan".
  Supported directions:
    1 → raster (H-major, single pass, default)
    2 → raster + transpose (W-major)
    4 → raster + transpose + horizontal-flip + vertical-flip

Backend switch:
  - BACKEND = 'naive'  →  fla.ops.gated_delta_rule.naive (HPC-tested)
  - BACKEND = 'chunk'  →  fla.ops.gated_delta_rule.chunk (needs TRITON_CACHE_DIR=/tmp)
  Set via env var GDN2_BACKEND or pass backend= arg to GDN2MemoryModule.

Memory key origin:
  - Keys derived from input features via learned linear projection.
  - NEVER reads GT segmentation masks.  Enforced by signature (no gt param).

Re-ID head (Claim 2 interface stub):
  - ReIDReadoutHead: accepts memory state + breakpoint positions → same-vessel
    matching logits.  Implementation is intentionally left as stub / TODO.
  - See ReIDReadoutHead docstring for the planned interface.
"""

from __future__ import annotations

import math
import os
from typing import Dict, List, Optional, Tuple, Union

import torch
import torch.nn as nn
import torch.nn.functional as F

from .unet import DoubleConv, Down, Up


# --------------------------------------------------------------------------- #
#  Backend switch (naive = HPC-tested; chunk = pending Triton env setup)
# --------------------------------------------------------------------------- #

BACKEND = os.environ.get('GDN2_BACKEND', 'naive').lower()


def _get_gdn2_fn(backend: str):
    """Return the appropriate GDN-2 kernel function."""
    if backend == 'naive':
        from fla.ops.gated_delta_rule.naive import naive_chunk_gated_delta_rule
        return naive_chunk_gated_delta_rule
    elif backend == 'chunk':
        # Use only after setting TRITON_CACHE_DIR=/tmp in sbatch env
        from fla.ops.gated_delta_rule import chunk_gated_delta_rule
        return chunk_gated_delta_rule
    else:
        raise ValueError(f"Unknown GDN2_BACKEND: {backend!r}. Use 'naive' or 'chunk'.")


# --------------------------------------------------------------------------- #
#  Mechanism B — Differentiable Frangi vesselness layer (input-derived, no GT)
# --------------------------------------------------------------------------- #

class DifferentiableFrangi(nn.Module):
    """
    Differentiable 2D Frangi vesselness filter over a feature map.

    Computes multi-scale Hessian-based vesselness using analytical Gaussian
    derivative convolution kernels — fully differentiable w.r.t. input (no GT).

    This is NOT Frangi-Net (arXiv 1711.03345): Frangi-Net learns Frangi weights
    for segmentation.  Here we use Frangi output as an external gate signal that
    modulates the GDN-2 write/erase gates (Claim 3 / Mechanism B).

    Algorithm (Frangi 1998, doi:10.1007/BFb0056195):
      For each scale σ:
        1. Smooth input with Gaussian kernel G(σ)
        2. Compute 2nd-order Gaussian derivatives → Hessian H = [[Lxx, Lxy],[Lxy, Lyy]]
        3. Eigenvalues λ₁, λ₂ (|λ₁| ≤ |λ₂|)
        4. Rb  = λ₁ / λ₂          (blob-vs-line ratio)
        5. S²  = λ₁² + λ₂²        (Frobenius norm of H)
        6. V(σ) = exp(-Rb²/(2β₁²)) * (1 - exp(-S²/(2β₂²)))
                  when λ₂ < 0 (bright vessel on dark bg), else 0
      Final vesselness = max over σ.

    Hyperparameters:
      scales:  list of σ values (Gaussian std in pixels of the feature map).
               # TODO: researcher to confirm optimal scales for bottleneck feature
               #   (current feature spatial res = H/16; typical retinal vessel width
               #    at this resolution is ~0.5–2 px → default [0.5, 1.0, 1.5]).
               #   Official Frangi 1998 uses σ ∈ [1, …, sqrt(2)^k] up to vessel size.
      beta1:   anisotropy threshold Rb (Frangi 1998 default = 0.5).
               # SOURCE: Frangi 1998, eq. (13), β₁ = 0.5.
      beta2:   second-structure threshold (Frangi 1998 uses c = half max S; here
               beta2 is an approximation).
               # TODO: Frangi 1998 sets c to half the max Hessian norm in the image
               #   (adaptive); we use a fixed β₂ = 15 as a typical heuristic value
               #   (used widely in ITK/scikit-image Frangi; needs researcher confirmation
               #   for the feature-map domain vs raw-image domain).
      in_channels: number of feature channels to average before Frangi.

    Output:
      vesselness: (B, 1, H, W), values in [0, 1]  — input-derived, differentiable.
    """

    def __init__(
        self,
        scales: List[float] = (0.5, 1.0, 1.5),
        beta1: float = 0.5,    # SOURCE: Frangi 1998 eq.(13)
        beta2: float = 15.0,   # TODO: researcher confirm for feature-map domain
        in_channels: int = 1,  # channels to reduce before Hessian
    ):
        super().__init__()
        self.scales = list(scales)
        self.beta1 = beta1
        self.beta2 = beta2
        # Learnable 1×1 conv to collapse in_channels → 1 before Hessian.
        # This lets the network learn which channel mixture is most vessel-like.
        self.channel_reduce = nn.Conv2d(in_channels, 1, 1, bias=False)

    @staticmethod
    def _gaussian_kernel_1d(sigma: float, size: int, device, dtype) -> torch.Tensor:
        """1D Gaussian kernel of given size, centered."""
        x = torch.arange(size, device=device, dtype=dtype) - size // 2
        g = torch.exp(-x ** 2 / (2 * sigma ** 2))
        return g / g.sum()

    @staticmethod
    def _gaussian_deriv2_1d(sigma: float, size: int, device, dtype) -> torch.Tensor:
        """1D second derivative of Gaussian (d²G/dx²)."""
        x = torch.arange(size, device=device, dtype=dtype) - size // 2
        g = torch.exp(-x ** 2 / (2 * sigma ** 2))
        d2 = g * (x ** 2 / sigma ** 4 - 1.0 / sigma ** 2)
        return d2

    def _compute_hessian(
        self, img: torch.Tensor, sigma: float
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Compute Hessian components Lxx, Lxy, Lyy of img at scale sigma.

        Args:
            img: (B, 1, H, W)
        Returns:
            Lxx, Lxy, Lyy — each (B, 1, H, W)
        """
        device, dtype = img.device, img.dtype
        # Kernel size: 6*sigma rounded up to next odd integer (captures 3σ on each side)
        ksize = max(3, 2 * int(math.ceil(3 * sigma)) + 1)

        g = self._gaussian_kernel_1d(sigma, ksize, device, dtype)      # (ksize,)
        d2 = self._gaussian_deriv2_1d(sigma, ksize, device, dtype)     # (ksize,)

        # Separable convolution using F.conv2d with 1D kernels in H and W
        # Lxx = D2x(Gy)  — convolve with d2 in x, G in y
        # Lyy = Gx(D2y)  — convolve with G in x, d2 in y
        # Lxy = Dx(Dy)   — approximate as cross-derivative using first-order deriv
        #   first-order 1D: dG/dx = -x/σ² * G(x)
        d1 = self._gaussian_kernel_1d(sigma, ksize, device, dtype)
        x_ax = torch.arange(ksize, device=device, dtype=dtype) - ksize // 2
        d1 = d1 * (-x_ax / (sigma ** 2))   # first-order Gaussian deriv

        def sep_conv(inp, kx, ky):
            """Separable 2D conv: kx along W-axis, ky along H-axis."""
            pad = ksize // 2
            # apply kx along W  (kernel shape: (1,1,1,ksize))
            tmp = F.conv2d(inp, kx.view(1, 1, 1, ksize), padding=(0, pad))
            # apply ky along H  (kernel shape: (1,1,ksize,1))
            return F.conv2d(tmp, ky.view(1, 1, ksize, 1), padding=(pad, 0))

        # Scale-normalise: σ² factor (Frangi 1998 eq. 4 — prevents scale bias)
        scale_factor = sigma ** 2

        Lxx = scale_factor * sep_conv(img, d2, g)
        Lyy = scale_factor * sep_conv(img, g, d2)
        Lxy = scale_factor * sep_conv(img, d1, d1)

        return Lxx, Lxy, Lyy

    @staticmethod
    def _eigenvalues_2x2_sym(
        Lxx: torch.Tensor, Lxy: torch.Tensor, Lyy: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Closed-form eigenvalues of 2×2 symmetric matrix [[Lxx,Lxy],[Lxy,Lyy]].
        Returns (lambda1, lambda2) with |lambda1| ≤ |lambda2|.
        """
        trace = Lxx + Lyy
        diff = Lxx - Lyy
        disc = torch.sqrt(torch.clamp(diff ** 2 + 4 * Lxy ** 2, min=1e-12))
        e1 = (trace - disc) / 2.0
        e2 = (trace + disc) / 2.0
        # Sort so |λ1| ≤ |λ2|
        swap = torch.abs(e1) > torch.abs(e2)
        lam1 = torch.where(swap, e2, e1)
        lam2 = torch.where(swap, e1, e2)
        return lam1, lam2

    def _frangi_at_scale(self, img: torch.Tensor, sigma: float) -> torch.Tensor:
        """
        Frangi vesselness at one scale.

        Returns:
            v: (B, 1, H, W) in [0, 1]
        """
        Lxx, Lxy, Lyy = self._compute_hessian(img, sigma)
        lam1, lam2 = self._eigenvalues_2x2_sym(Lxx, Lxy, Lyy)

        # Vessel condition: λ₂ < 0 (bright-on-dark); zero otherwise
        vessel_mask = (lam2 < 0).float()

        # Safe division: add tiny eps to |λ₂|
        Rb = lam1 / (lam2.abs() + 1e-8)         # (B,1,H,W)
        S2 = lam1 ** 2 + lam2 ** 2               # (B,1,H,W)

        # Frangi 1998 eq. (13)
        beta1_sq2 = 2.0 * self.beta1 ** 2
        beta2_sq2 = 2.0 * self.beta2 ** 2

        v = torch.exp(-Rb ** 2 / beta1_sq2) * (1.0 - torch.exp(-S2 / beta2_sq2))
        v = v * vessel_mask
        return v  # (B, 1, H, W)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, C, H, W)  feature map — NOT GT, NOT segmentation result.
        Returns:
            vesselness: (B, 1, H, W)  in [0, 1], differentiable w.r.t. x.
        """
        # Reduce channels to 1 (learnable mixture) so Hessian is well-defined
        img = self.channel_reduce(x)  # (B, 1, H, W)

        responses = []
        for sigma in self.scales:
            responses.append(self._frangi_at_scale(img, sigma))

        # Max over scales (Frangi 1998: take max across scales)
        vesselness = torch.stack(responses, dim=0).max(dim=0).values  # (B, 1, H, W)
        # Normalise to [0, 1] per sample (divide by max; avoid div-by-zero)
        vmax = vesselness.flatten(1).max(dim=1).values.view(-1, 1, 1, 1).clamp(min=1e-8)
        vesselness = vesselness / vmax
        return vesselness  # (B, 1, H, W), input-derived, differentiable


# --------------------------------------------------------------------------- #
#  Re-ID Readout Head (Claim 2 — planner+skeptic design, 2026-06-20)
# --------------------------------------------------------------------------- #

def _gather_tokens_at(
    o_seq: torch.Tensor,
    positions: torch.Tensor,
    H: int,
    W: int,
) -> torch.Tensor:
    """
    Gather memory-output tokens at breakpoint positions via raster-order index lookup.

    Args:
        o_seq:     (B, T, D)  — flat token sequence (raster order H-major)
        positions: (B, K, 2)  — (h, w) coordinates in [0, H) x [0, W)
                               float or long; fractional coords are floored.
        H, W:      spatial dimensions matching raster order
    Returns:
        gathered:  (B, K, D)
    """
    B, K, _ = positions.shape
    # Convert (h, w) → flat token index in raster order
    h_idx = positions[..., 0].long().clamp(0, H - 1)   # (B, K)
    w_idx = positions[..., 1].long().clamp(0, W - 1)   # (B, K)
    flat_idx = h_idx * W + w_idx                        # (B, K)

    # Expand index for gather: (B, K, D)
    D = o_seq.shape[-1]
    idx_exp = flat_idx.unsqueeze(-1).expand(B, K, D)   # (B, K, D)
    gathered = o_seq.gather(1, idx_exp)                 # (B, K, D)
    return gathered


def _grid_sample_at(
    feat: torch.Tensor,
    positions: torch.Tensor,
) -> torch.Tensor:
    """
    Bilinear-sample decoder feature map at (h, w) breakpoint positions.

    Args:
        feat:      (B, C, H, W)  — decoder feature map
        positions: (B, K, 2)     — (h, w) in pixel coords [0, H) x [0, W)
    Returns:
        sampled:   (B, K, C)
    """
    B, C, H, W = feat.shape
    K = positions.shape[1]

    # Normalise to [-1, 1] for grid_sample (x=W-axis, y=H-axis)
    h_norm = (positions[..., 0] / (H - 1)) * 2.0 - 1.0   # (B, K)
    w_norm = (positions[..., 1] / (W - 1)) * 2.0 - 1.0   # (B, K)
    # grid_sample expects grid shape (B, Hout, Wout, 2) with (x, y) = (w, h)
    grid = torch.stack([w_norm, h_norm], dim=-1)           # (B, K, 2)
    grid = grid.unsqueeze(2)                               # (B, K, 1, 2)

    # Sample: (B, C, K, 1)
    sampled = F.grid_sample(feat, grid, mode='bilinear',
                            align_corners=True, padding_mode='border')
    sampled = sampled.squeeze(-1).permute(0, 2, 1)        # (B, K, C)
    return sampled


class ReIDReadoutHead(nn.Module):
    """
    Spatial re-identification readout head (Claim 2).

    Headline mechanism: GDN-2 associative memory encodes vessel identity.
    Given K breakpoint candidate positions, this head reads out per-position
    identity embeddings from memory + local decoder features, then computes
    pairwise same-vessel matching logits.

    Supervision: synthetic-break weak supervision (apply_breaks knows two sides
    of the same cut → same-root label).  Supervised signal stays OUTSIDE the
    main model via three stop-gradient barriers — the weak supervision ONLY
    updates this head's projection layers, never the memory / encoder / Frangi.
    This preserves Claim 1 (GT-topology-free associative memory).

    THREE detach barriers (致命-1 红线, planner+skeptic 2026-06-20):
      ★detach1: o_seq.detach()         — memory output side
      ★detach2: memory_state.detach()  — explicit memory state (if provided)
      ★detach3: dec_feat.detach()      — decoder feature side

    Ablation flags (Block D):
      feat_source   : 'memory' (A2, default) | 'cnn' (A0' — CNN-only baseline;
                      same head, but id_vec comes from a parallel CNN bottleneck
                      feature NOT flowing through GDN-2, i.e. skip memory path).
                      NOTE: A0' wiring lives in UNetGDN2 which passes appropriate
                      o_seq; this flag just labels the arm.
      detach_memory_train : bool (A3 — ablate gradient isolation: if False, no
                      detach → gradients can flow into memory; use ONLY for ablation
                      to show the detach is load-bearing).  Default=True (MUST be
                      True in all non-ablation runs — red line).
      breakpoint_source : 'gt_skeleton' (A2) | 'pred_skeleton' (A4 — removes
                      GT-topology dependency on breakpoint detection side).
                      This flag is informational here; actual source is determined
                      upstream in the training loop.

    Args:
        d_head:     GDN-2 head dimension (must match GDN2MemoryModule.d_head)
        n_heads:    number of GDN-2 attention heads
        dec_ch:     decoder feature channels (must match selected decoder layer)
        d_id:       identity embedding dimension (default 64)
        feat_source: ablation arm label (see above)
        detach_memory_train: True = enforce gradient isolation (default, red line)
        breakpoint_source:   ablation arm label (informational)
    """

    def __init__(
        self,
        d_head: int,
        n_heads: int,
        dec_ch: int,
        d_id: int = 64,
        feat_source: str = 'memory',            # ablation A2/A0'
        detach_memory_train: bool = True,        # ablation A3 — MUST be True in non-ablation
        breakpoint_source: str = 'gt_skeleton',  # ablation A2/A4 (informational)
        use_loc_feat: bool = True,               # A-v2 M-A: False = memory-only head
    ):
        super().__init__()
        assert feat_source in ('memory', 'cnn', 'linear_attn'), (
            f"feat_source must be 'memory', 'cnn', or 'linear_attn'; got {feat_source!r}"
        )
        assert breakpoint_source in ('gt_skeleton', 'pred_skeleton'), (
            f"breakpoint_source must be 'gt_skeleton' or 'pred_skeleton'; "
            f"got {breakpoint_source!r}"
        )
        self.d_head = d_head
        self.n_heads = n_heads
        self.dec_ch = dec_ch
        self.d_id = d_id
        self.feat_source = feat_source
        self.detach_memory_train = detach_memory_train
        self.breakpoint_source = breakpoint_source
        self.use_loc_feat = use_loc_feat         # A-v2 M-A flag

        # Memory-side projection: (nh * d_head) → d_id
        self.mem_proj = nn.Linear(d_head * n_heads, d_id, bias=False)

        if use_loc_feat:
            # Local decoder projection: dec_ch → d_id
            self.loc_proj = nn.Linear(dec_ch, d_id, bias=False)
            # Fusion: concat(mem, loc) → d_id
            self.fuse = nn.Linear(2 * d_id, d_id, bias=False)
        else:
            # M-A memory-only path: no loc_proj / fuse needed.
            # Register None to keep state_dict structure distinguishable.
            self.loc_proj = None  # type: ignore[assignment]
            self.fuse     = None  # type: ignore[assignment]

        # Learnable log-temperature (initialised at 0 → temp=1.0)
        self.log_temp = nn.Parameter(torch.zeros(1))

    def forward(
        self,
        o_seq: torch.Tensor,
        dec_feat: torch.Tensor,
        breakpoint_positions: torch.Tensor,
        memory_state: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Compute pairwise same-vessel matching logits for K breakpoint positions.

        The three detach barriers below are the critical gradient isolation
        (planner+skeptic 2026-06-20 致命-1 red line).  Do NOT remove them.
        Ablation A3 (detach_memory_train=False) is the only allowed exception.

        Args:
            o_seq:                (B, T, nh*d_head)  — memory output sequence
                                  (raster order, T = H_bot * W_bot at bottleneck)
            dec_feat:             (B, dec_ch, H_dec, W_dec)  — decoder feature map
                                  (spatial resolution of selected decoder layer)
            breakpoint_positions: (B, K, 2)  — (h, w) in dec_feat pixel coords
                                  Float or long; h in [0, H_dec), w in [0, W_dec).
            memory_state:         Optional (B, nh, d_head, d_head) or
                                  list of such tensors (per-direction final states).
                                  Not used in current forward (reserved for future
                                  explicit key-value retrieval variant).

        Returns:
            logits: (B, K, K)  — pairwise matching logits, symmetric, diagonal=-inf.
                    logits[b,i,j] > 0 → positions i and j likely same vessel.
        """
        # ------------------------------------------------------------------- #
        # ★ detach1 — memory output: weak supervision must NOT flow into memory
        # ------------------------------------------------------------------- #
        if self.detach_memory_train:
            mem_ctx = o_seq.detach()          # ★detach1
        else:
            # A3 ablation only — gradient allowed (demonstrates detach is load-bearing)
            mem_ctx = o_seq

        # ------------------------------------------------------------------- #
        # ★ detach2 — explicit memory state (future key-value retrieval path)
        # ------------------------------------------------------------------- #
        if memory_state is not None:
            if isinstance(memory_state, (list, tuple)):
                # Per-direction states: detach each individually.
                # A1'(linear_attn 无状态) 给的是含 None 元素的 list（无递推 state S_t）→
                # 必须 guard None（HPC 真跑 2026-06-20 逮：A1' s=None 撞 .detach，unit 测试没覆盖此路径）。
                memory_state = [
                    (s.detach() if self.detach_memory_train else s) if s is not None else None
                    for s in memory_state   # ★detach2
                ]
            else:
                if self.detach_memory_train:
                    memory_state = memory_state.detach()             # ★detach2

        # ------------------------------------------------------------------- #
        # ★ detach3 — decoder features: weak supervision must NOT flow into encoder
        # ------------------------------------------------------------------- #
        if self.detach_memory_train:
            loc = dec_feat.detach()           # ★detach3
        else:
            loc = dec_feat

        # ------------------------------------------------------------------- #
        # Gather identity embeddings at breakpoint positions
        # ------------------------------------------------------------------- #
        B, K, _ = breakpoint_positions.shape
        H_dec, W_dec = loc.shape[-2], loc.shape[-1]

        # Memory side: gather raster-order tokens from o_seq
        # o_seq has bottleneck spatial resolution (H_bot, W_bot);
        # breakpoint_positions are in dec_feat resolution → need to scale down.
        # NOTE: we scale positions to bottleneck token space for token gather.
        # Bottleneck spatial dims inferred from o_seq length T = H_bot * W_bot.
        T = mem_ctx.shape[1]
        # Heuristic: assume square bottleneck (valid for square patches).
        H_bot = W_bot = int(T ** 0.5)
        if H_bot * W_bot != T:
            # Non-square bottleneck fallback: gather by nearest flat index
            # (use bilinear-equivalent scaling along T-dim)
            # This case is unlikely given 512×512 → 32×32 bottleneck.
            H_bot = T
            W_bot = 1

        # Scale positions from dec_feat res → bottleneck res
        scale_h = H_bot / H_dec
        scale_w = W_bot / W_dec
        pos_bot = breakpoint_positions.float().clone()
        pos_bot[..., 0] = pos_bot[..., 0] * scale_h
        pos_bot[..., 1] = pos_bot[..., 1] * scale_w

        id_vec = _gather_tokens_at(mem_ctx, pos_bot, H_bot, W_bot)  # (B, K, nh*d_head)

        # ------------------------------------------------------------------- #
        # Project + fuse → normalised identity embedding e ∈ R^{d_id}
        # M-A (A-v2): use_loc_feat=False → memory-only path, skip dec_feat route
        # ------------------------------------------------------------------- #
        e_mem = self.mem_proj(id_vec)    # (B, K, d_id)

        if not self.use_loc_feat:
            # Memory-only: head only eats memory o_seq.
            # dec_feat (loc) is NOT accessed here — the shortcut that let
            # dec_feat overpower memory in A-I is eliminated.
            # ★ detach1/2/3 barriers are preserved (mem_ctx already detached above).
            e = F.normalize(e_mem, dim=-1)   # (B, K, d_id), L2-normalised
        else:
            # Local decoder side: bilinear-sample dec_feat at breakpoint positions
            loc_vec = _grid_sample_at(loc, breakpoint_positions.float())  # (B, K, dec_ch)
            e_loc = self.loc_proj(loc_vec)   # (B, K, d_id)
            e = F.normalize(
                self.fuse(torch.cat([e_mem, e_loc], dim=-1)),   # (B, K, d_id)
                dim=-1,
            )   # L2-normalised embedding

        # ------------------------------------------------------------------- #
        # Pairwise cosine logits scaled by learnable temperature
        # ------------------------------------------------------------------- #
        # (B, K, K): e[b,i] · e[b,j] (cosine since e is normalised)
        logits = torch.bmm(e, e.transpose(1, 2)) * self.log_temp.exp()

        # Mask diagonal (self-matching is trivially "same vessel" → exclude)
        diag_mask = torch.eye(K, dtype=torch.bool, device=logits.device)
        logits = logits.masked_fill(diag_mask.unsqueeze(0), float('-inf'))

        return logits   # (B, K, K), symmetric, diagonal=-inf


# --------------------------------------------------------------------------- #
#  Multi-direction reorder helpers (Engineering A — standard, not a core claim)
# --------------------------------------------------------------------------- #

def _get_scan_permutations(H: int, W: int, n_dirs: int, device) -> List[torch.Tensor]:
    """
    Return a list of index permutations (each of length H*W) for multi-direction scans.

    STORY_FRAMEWORK § R4: this is standard 2D reorder engineering; the contribution
    is the associative memory, not the scan direction design.

    Supported:
      n_dirs=1 → [raster (H-major)]
      n_dirs=2 → [raster, transpose (W-major)]
      n_dirs=4 → [raster, transpose, H-flip raster, V-flip raster]

    Args:
        H, W:   spatial dimensions (at bottleneck)
        n_dirs: 1, 2, or 4
        device: torch device

    Returns:
        list of n_dirs tensors, each shape (H*W,), dtype=torch.long
    """
    idx = torch.arange(H * W, device=device).view(H, W)  # (H, W) raster indices

    raster    = idx.reshape(-1)                           # H-major raster
    transpose = idx.t().reshape(-1)                       # W-major (transpose)
    hflip     = idx.flip(1).reshape(-1)                   # left-right flip then raster
    vflip     = idx.flip(0).reshape(-1)                   # top-bottom flip then raster

    all_perms = [raster, transpose, hflip, vflip]
    if n_dirs not in (1, 2, 4):
        raise ValueError(f"n_dirs must be 1, 2 or 4; got {n_dirs}")
    return all_perms[:n_dirs]


def _invert_permutation(perm: torch.Tensor) -> torch.Tensor:
    """Return the inverse permutation of perm (so x[perm][inv] == x)."""
    inv = torch.empty_like(perm)
    inv[perm] = torch.arange(len(perm), device=perm.device, dtype=perm.dtype)
    return inv


# --------------------------------------------------------------------------- #
#  GDN-2 Memory Module (Mechanism B + Engineering A)
# --------------------------------------------------------------------------- #

class GDN2MemoryModule(nn.Module):
    """
    GDN-2 Gated Delta Rule associative memory applied to 2D feature maps.

    Implements:
      * Claim 1 (C): vessel identity memory via delta-rule KV writes/retrievals.
      * Mechanism B: decoupled erase/write gates modulated by differentiable Frangi.
      * Engineering A: optional multi-direction scan with output merging.

    Mechanism B detail (Frangi modulation):
      - `proj_write`  → raw_write ∈ (0,1), passed as β (write gate) to FLA.
        Frangi-high regions: write_gate amplified (+alpha_w * vesselness).
      - `proj_erase`  → raw_erase ∈ (0,1), blended into g (decay) gate.
        Frangi-high regions: erase suppressed ((1 - alpha_e * vesselness) factor).
      Both alpha_w and alpha_e are learnable scalars (bounded [0,1] by sigmoid).

    Engineering A detail:
      - For each direction, tokens are reordered before the GDN-2 call and
        un-reordered after.  The output `o` tensors from all directions are
        averaged.  Memory states S are NOT merged (each direction processes
        independently; merging states is theoretically unsound).

    IMPORTANT: all projections (q, k, v, write, erase, g) come from `x` (input
    features).  This module has NO parameter that receives GT annotations.

    Args:
        d_model:       channel dimension of input feature map (must match in_ch)
        d_head:        head dimension for key/query/value
        n_heads:       number of attention heads
        max_seq_len:   maximum sequence length (spatial H*W).  Assertion enforced.
        backend:       'naive' | 'chunk'
        directions:    1, 2, or 4 scan directions (default=1; use 2 or 4 for ablation)
        use_frangi:    True = Frangi gate modulation active (Mechanism B)
                       False = skip Frangi (degrade to original single-gate design)
        frangi_scales: Gaussian σ values for DifferentiableFrangi (in feature pixels)
                       # TODO: researcher confirm scales for H/16 bottleneck resolution
        frangi_beta1:  anisotropy param (Frangi 1998 default=0.5)
        frangi_beta2:  structure param (heuristic default=15.0; TODO researcher confirm)
    """

    MAX_SEQ_LEN = 1024  # Hard upper bound — GDN-2 memory capacity constraint

    def __init__(
        self,
        d_model: int,
        d_head: int = 64,
        n_heads: int = 1,
        max_seq_len: int = MAX_SEQ_LEN,
        backend: str = BACKEND,
        directions: int = 1,
        use_frangi: bool = True,
        frangi_scales: Tuple[float, ...] = (0.5, 1.0, 1.5),
        frangi_beta1: float = 0.5,    # SOURCE: Frangi 1998 eq.(13)
        frangi_beta2: float = 15.0,   # TODO: researcher confirm for feature-map domain
    ):
        super().__init__()
        assert d_head % n_heads == 0, "d_head must be divisible by n_heads"
        assert directions in (1, 2, 4), f"directions must be 1, 2 or 4; got {directions}"
        dh = d_head
        nh = n_heads

        self.d_model = d_model
        self.d_head = d_head
        self.n_heads = n_heads
        self.max_seq_len = max_seq_len
        self.backend = backend
        self.directions = directions
        self.use_frangi = use_frangi

        # -- Q/K/V projections from input features (no GT) --
        self.proj_q = nn.Linear(d_model, dh * nh, bias=False)
        self.proj_k = nn.Linear(d_model, dh * nh, bias=False)
        self.proj_v = nn.Linear(d_model, dh * nh, bias=False)

        # -- Mechanism B: decoupled write / erase gate projections --
        # write gate (β in FLA): high → write new info to memory
        self.proj_write = nn.Linear(d_model, nh, bias=False)
        # erase gate: high → forget old memory (blended into g decay)
        self.proj_erase = nn.Linear(d_model, nh, bias=False)
        # decay gate (g in FLA, log-space): baseline decay independent of Frangi
        self.proj_g = nn.Linear(d_model, nh, bias=False)

        # Frangi modulation strengths: learnable scalars in (0,1)
        # alpha_w: how much Frangi boosts write gate
        # alpha_e: how much Frangi suppresses erase gate
        if use_frangi:
            self.alpha_w = nn.Parameter(torch.tensor(0.5))  # init mid-range
            self.alpha_e = nn.Parameter(torch.tensor(0.5))
            self.frangi = DifferentiableFrangi(
                scales=list(frangi_scales),
                beta1=frangi_beta1,
                beta2=frangi_beta2,
                in_channels=d_model,
            )
        else:
            self.alpha_w = None
            self.alpha_e = None
            self.frangi = None

        # -- Output projection --
        self.proj_out = nn.Linear(dh * nh, d_model, bias=False)
        self.norm = nn.LayerNorm(d_model)

        self._gdn2_fn = _get_gdn2_fn(backend)

    def _run_one_direction(
        self,
        tokens: torch.Tensor,           # (B, T, C)
        perm: torch.Tensor,             # (T,) index permutation
        inv_perm: torch.Tensor,         # (T,) inverse permutation
        write_gate: torch.Tensor,       # (B, T, nh) — already Frangi-modulated
        erase_gate: torch.Tensor,       # (B, T, nh) — already Frangi-modulated
        g: torch.Tensor,                # (B, T, nh) log-space decay
        output_final_state: bool = False,
    ) -> Union[torch.Tensor, Tuple[torch.Tensor, Optional[torch.Tensor]]]:
        """
        Run one GDN-2 pass on reordered tokens, un-reorder output.

        Args:
            tokens:             (B, T, C) — full-sequence tokens (un-permuted)
            perm:               index permutation (T,)
            inv_perm:           inverse permutation (T,)
            write_gate:         (B, T, nh) — write β (already modulated)
            erase_gate:         (B, T, nh) — erase modifier (already modulated)
            g:                  (B, T, nh) — baseline log-decay
            output_final_state: if True, also return the final memory state S
                                (B, nh, d_head, d_head).  The FLA naive kernel
                                supports this via output_final_state=True kwarg.
                                Falls back to None if the kernel does not support it.

        Returns:
            output_final_state=False → o_orig: (B, T, nh, dh)
            output_final_state=True  → (o_orig, final_state)
                where final_state is (B, nh, d_head, d_head) or None if kernel
                does not expose it.
        """
        B, T, C = tokens.shape
        nh = self.n_heads
        dh = self.d_head

        # Reorder tokens for this scan direction
        t_perm = tokens[:, perm, :]                    # (B, T, C)

        # Q, K, V from reordered tokens
        q = self.proj_q(t_perm).view(B, T, nh, dh)    # (B, T, nh, dh)
        k = self.proj_k(t_perm).view(B, T, nh, dh)
        v = self.proj_v(t_perm).view(B, T, nh, dh)
        q = F.normalize(q, dim=-1)
        k = F.normalize(k, dim=-1)

        # Reorder gate signals to match this direction
        wg = write_gate[:, perm, :]                    # (B, T, nh)
        eg = erase_gate[:, perm, :]                    # (B, T, nh)
        gd = g[:, perm, :]                             # (B, T, nh)

        # Combine erase into g: higher erase → stronger decay (more forgetting)
        # g is already in log-space (<0); subtract erase term to amplify decay
        # (i.e., erase_gate high → more negative g → faster decay = erasure)
        g_combined = gd - eg.abs()                     # (B, T, nh), log-space

        # GDN-2 kernel call (FLA convention: β=write gate, g=log-decay)
        # Try to request final_state from the kernel when needed.
        final_state = None
        if output_final_state:
            try:
                res = self._gdn2_fn(q, k, v, beta=wg, g=g_combined,
                                    output_final_state=True)
                # naive_chunk_gated_delta_rule returns (o, final_state)
                o_perm = res[0]
                final_state = res[1]   # (B, nh, d_head, d_head) or None
            except TypeError:
                # Kernel does not support output_final_state kwarg — fallback
                res = self._gdn2_fn(q, k, v, beta=wg, g=g_combined)
                o_perm = res[0] if isinstance(res, tuple) else res
                final_state = None
        else:
            res = self._gdn2_fn(q, k, v, beta=wg, g=g_combined)
            o_perm = res[0] if isinstance(res, tuple) else res   # (B, T, nh, dh)

        # Un-reorder output to original spatial order
        o_orig = o_perm[:, inv_perm, :, :]             # (B, T, nh, dh)

        if output_final_state:
            return o_orig, final_state
        return o_orig

    def forward(
        self,
        x: torch.Tensor,
        return_memory: bool = False,
    ) -> Union[torch.Tensor, Tuple[torch.Tensor, List[Optional[torch.Tensor]]]]:
        """
        Args:
            x: (B, C, H, W)  input feature map — must have C == d_model
               NOTE: this is a feature map derived from input images, NEVER GT.
            return_memory: if True, also return per-direction final memory states
               as a list of length n_dirs.  Each element is either
               (B, nh, d_head, d_head) if the FLA kernel exposes final_state,
               or None if the kernel does not support it.
               States are NOT merged across directions (merging states is
               theoretically unsound — L413 red line preserved).

        Returns:
            return_memory=False → out: (B, C, H, W)
            return_memory=True  → (out, states_list)
                out:         (B, C, H, W)
                states_list: List[Optional[Tensor]] length=n_dirs,
                             each (B, nh, d_head, d_head) or None
                Also exposes: self._last_o_seq (B, T, nh*d_head) — memory
                output sequence in raster order, used by ReIDReadoutHead.
        """
        B, C, H, W = x.shape
        assert C == self.d_model, f"Expected C={self.d_model}, got {C}"
        T = H * W
        assert T <= self.max_seq_len, (
            f"Sequence length {T} (H={H}, W={W}) exceeds GDN-2 limit "
            f"{self.max_seq_len}.  Use a smaller spatial resolution."
        )

        # Flatten: (B, C, H, W) → (B, T, C)
        tokens = x.permute(0, 2, 3, 1).reshape(B, T, C)
        nh = self.n_heads

        # ---- Mechanism B: compute Frangi vesselness (input-derived, no GT) ----
        if self.use_frangi:
            vesselness = self.frangi(x)                # (B, 1, H, W) in [0,1]
            # Flatten vesselness to match token order: (B, T, 1)
            v_flat = vesselness.permute(0, 2, 3, 1).reshape(B, T, 1)

            # Write gate: amplified at vessel-evidence locations
            alpha_w = torch.sigmoid(self.alpha_w)      # scalar in (0,1)
            raw_write = torch.sigmoid(self.proj_write(tokens))  # (B, T, nh)
            write_gate = raw_write * (1.0 + alpha_w * v_flat)   # (B, T, nh)
            write_gate = write_gate.clamp(0.0, 1.0)    # keep in valid range

            # Erase gate: suppressed at vessel-evidence locations
            alpha_e = torch.sigmoid(self.alpha_e)      # scalar in (0,1)
            raw_erase = torch.sigmoid(self.proj_erase(tokens))  # (B, T, nh)
            erase_gate = raw_erase * (1.0 - alpha_e * v_flat)   # (B, T, nh)
            erase_gate = erase_gate.clamp(min=0.0)     # non-negative erase strength
        else:
            # Without Frangi: single gate (original design, no modulation)
            write_gate = torch.sigmoid(self.proj_write(tokens))  # (B, T, nh)
            erase_gate = torch.zeros_like(write_gate)   # no separate erase signal

        # Baseline log-decay gate (always active)
        g = F.logsigmoid(self.proj_g(tokens))          # (B, T, nh), values < 0

        # ---- Engineering A: multi-direction scan (standard reorder, not a claim) ----
        perms = _get_scan_permutations(H, W, self.directions, device=x.device)
        inv_perms = [_invert_permutation(p) for p in perms]

        o_list: List[torch.Tensor] = []
        states_list: List[Optional[torch.Tensor]] = []
        for perm, inv_perm in zip(perms, inv_perms):
            if return_memory:
                o_dir, s_dir = self._run_one_direction(
                    tokens, perm, inv_perm, write_gate, erase_gate, g,
                    output_final_state=True,
                )
                states_list.append(s_dir)
            else:
                o_dir = self._run_one_direction(
                    tokens, perm, inv_perm, write_gate, erase_gate, g,
                    output_final_state=False,
                )
            o_list.append(o_dir)                       # each (B, T, nh, dh)

        # Merge: average outputs across directions (states are NOT merged)
        o = torch.stack(o_list, dim=0).mean(dim=0)     # (B, T, nh, dh)

        # Merge heads → (B, T, nh*dh)
        o_seq = o.reshape(B, T, nh * self.d_head)      # (B, T, nh*d_head)
        # Store for external access (ReIDReadoutHead may read this)
        self._last_o_seq = o_seq

        # Output projection + residual + norm
        out_tokens = self.proj_out(o_seq)              # (B, T, C)
        out_tokens = self.norm(tokens + out_tokens)    # residual connection

        # Reshape back: (B, T, C) → (B, C, H, W)
        out = out_tokens.reshape(B, H, W, C).permute(0, 3, 1, 2)

        if return_memory:
            return out, states_list
        return out


# --------------------------------------------------------------------------- #
#  A1' — Stateless Linear Attention Module (iso-parametric ablation arm)
# --------------------------------------------------------------------------- #

class LinearAttnModule(nn.Module):
    """
    A1' iso-parametric stateless linear attention module (ablation arm).

    **Purpose (ACCEPTANCE_CRITERIA P4, pre-registered 2026-06-20)**:
    Isolates the contribution of the *stateful delta-rule associative memory*
    in GDN2MemoryModule (A2) from the contribution of merely adding an
    attention-like module with the same parameter budget.

    **Structural invariant**:
    This module is a strict mirror of GDN2MemoryModule w.r.t. all learnable
    parameters:
      - q/k/v/out projections (identical shapes)
      - write / erase / g gate projections (identical shapes)
      - LayerNorm (identical d_model)
      - DifferentiableFrangi (identical config, identical channel_reduce)
      - alpha_w / alpha_e learnable scalars
    Thus full-model trainable numel(A1') == numel(A2) (difference = 0, well
    within the ≤±5% ACCEPTANCE threshold).

    **The only difference vs GDN2MemoryModule**:
    The GDN-2 kernel (naive_chunk_gated_delta_rule) performs a *stateful*
    recurrent delta-rule update:
        S_t = diag(g_t) * S_{t-1} + beta_t * (v_t - S_{t-1} k_t) outer k_t
        o_t = S_t @ q_t
    This maintains and evolves an explicit associative memory state S across
    the sequence — the defining mechanism of Claim 2 (vessel identity memory).

    A1' replaces this with *stateless* cumulative linear attention:
        A_t = sum_{s<=t} phi(k_s)^T v_s          (prefix sum of outer products)
        b_t = sum_{s<=t} phi(k_s)                 (prefix sum of keys)
        o_t = phi(q_t) @ A_t / (phi(q_t) . b_t + eps)

    where phi(x) = elu(x) + 1 (standard ELU feature map from
    Katharopoulos et al. 2020, "Transformers are RNNs", ICML 2020).
    This is the stateless degenerate case of the delta-rule:
    - No recursive state S_t carried across tokens.
    - No delta (error-correction) update term.
    - Each token's output is a normalised weighted sum of all prior tokens'
      v vectors, weighted by key-query similarity — no vessel identity is
      'stored' across disconnected vessel segments.

    **Choice justification**: ELU+1 linear attention is the most widely used
    stateless linear attention variant (Katharopoulos 2020), making A1'
    a canonical "attention capacity without memory" baseline.  The kernel is
    implemented in pure PyTorch (no FLA dependency), which also avoids any
    hardware-side confound.  As the delta-rule kernel degenerates to standard
    linear attention when the delta-update term is zeroed, A1' is the
    mathematically minimal change from A2.

    **Insert depth**: identical to GDN2MemoryModule — applied at the bottleneck
    (after DoubleConv, spatial resolution H/16 × W/16 ≤ 1024 tokens).

    **Scan / multi-direction**: same _get_scan_permutations / _invert_permutation
    helpers as GDN2MemoryModule; output is averaged across directions.

    Args:
        d_model:       channel dimension of input feature map (must match in_ch)
        d_head:        head dimension for key/query/value
        n_heads:       number of attention heads
        max_seq_len:   maximum sequence length (spatial H*W).  Assert enforced.
        directions:    1, 2, or 4 scan directions (default=1)
        use_frangi:    True = Frangi gate modulation active (same as A2)
        frangi_scales: Gaussian σ values for DifferentiableFrangi
        frangi_beta1:  anisotropy param (Frangi 1998 default=0.5)
        frangi_beta2:  structure param (heuristic default=15.0)
    """

    MAX_SEQ_LEN = 1024

    def __init__(
        self,
        d_model: int,
        d_head: int = 64,
        n_heads: int = 1,
        max_seq_len: int = MAX_SEQ_LEN,
        directions: int = 1,
        use_frangi: bool = True,
        frangi_scales: Tuple[float, ...] = (0.5, 1.0, 1.5),
        frangi_beta1: float = 0.5,    # SOURCE: Frangi 1998 eq.(13)
        frangi_beta2: float = 15.0,   # TODO: researcher confirm for feature-map domain
    ):
        super().__init__()
        assert d_head % n_heads == 0, "d_head must be divisible by n_heads"
        assert directions in (1, 2, 4), f"directions must be 1, 2 or 4; got {directions}"
        dh = d_head
        nh = n_heads

        self.d_model = d_model
        self.d_head = d_head
        self.n_heads = n_heads
        self.max_seq_len = max_seq_len
        self.directions = directions
        self.use_frangi = use_frangi

        # -- Q/K/V projections: identical to GDN2MemoryModule --
        self.proj_q = nn.Linear(d_model, dh * nh, bias=False)
        self.proj_k = nn.Linear(d_model, dh * nh, bias=False)
        self.proj_v = nn.Linear(d_model, dh * nh, bias=False)

        # -- Gate projections: identical to GDN2MemoryModule (same param count) --
        # write gate kept for Frangi modulation parity (not fed to stateful kernel)
        self.proj_write = nn.Linear(d_model, nh, bias=False)
        # erase gate kept for parity (not used in stateless attn; iso-param req)
        self.proj_erase = nn.Linear(d_model, nh, bias=False)
        # g (decay) gate kept for parity (not used in stateless attn; iso-param req)
        self.proj_g = nn.Linear(d_model, nh, bias=False)

        # -- Frangi modulation: identical to GDN2MemoryModule --
        if use_frangi:
            self.alpha_w = nn.Parameter(torch.tensor(0.5))
            self.alpha_e = nn.Parameter(torch.tensor(0.5))
            self.frangi = DifferentiableFrangi(
                scales=list(frangi_scales),
                beta1=frangi_beta1,
                beta2=frangi_beta2,
                in_channels=d_model,
            )
        else:
            self.alpha_w = None
            self.alpha_e = None
            self.frangi = None

        # -- Output projection + norm: identical to GDN2MemoryModule --
        self.proj_out = nn.Linear(dh * nh, d_model, bias=False)
        self.norm = nn.LayerNorm(d_model)

    @staticmethod
    def _elu_feature_map(x: torch.Tensor) -> torch.Tensor:
        """ELU+1 feature map φ(x) = elu(x) + 1 ≥ 0 (Katharopoulos 2020)."""
        return F.elu(x) + 1.0

    def _run_linear_attn_one_dir(
        self,
        tokens: torch.Tensor,          # (B, T, C)
        perm: torch.Tensor,            # (T,)
        inv_perm: torch.Tensor,        # (T,)
    ) -> torch.Tensor:
        """
        Run stateless causal linear attention on reordered tokens, un-reorder output.

        Formula (causal / prefix-sum form, Katharopoulos 2020 §3.1):
            phi_k_t = phi(k_t),  phi_q_t = phi(q_t)
            A_t = sum_{s=1..t} phi_k_s^T v_s    (B, nh, dh, dh) outer product sum
            b_t = sum_{s=1..t} phi_k_s            (B, nh, dh) key normaliser
            o_t = phi_q_t @ A_t / (phi_q_t . b_t + eps)   (B, nh, dh)

        No memory state S_t, no delta-correction, no recurrent update.
        Implemented as sequential scan for numerical correctness (no Triton).

        Returns:
            o_orig: (B, T, nh, dh)  — output in original (un-permuted) token order
        """
        B, T, C = tokens.shape
        nh = self.n_heads
        dh = self.d_head

        # Reorder
        t_perm = tokens[:, perm, :]                     # (B, T, C)

        # Q, K, V
        q = self.proj_q(t_perm).view(B, T, nh, dh)     # (B, T, nh, dh)
        k = self.proj_k(t_perm).view(B, T, nh, dh)
        v = self.proj_v(t_perm).view(B, T, nh, dh)

        # ELU+1 feature maps (Katharopoulos 2020)
        phi_q = self._elu_feature_map(q)                 # (B, T, nh, dh)
        phi_k = self._elu_feature_map(k)                 # (B, T, nh, dh)

        # Causal linear attention via sequential prefix-sum scan.
        # A = cumulative outer product sum (B, nh, dh, dh)
        # b = cumulative key sum            (B, nh, dh)
        # Both are updated token-by-token (causal = each position uses 1..t).
        A = torch.zeros(B, nh, dh, dh, device=tokens.device, dtype=tokens.dtype)
        b = torch.zeros(B, nh, dh,    device=tokens.device, dtype=tokens.dtype)
        o_list: List[torch.Tensor] = []

        for t in range(T):
            k_t = phi_k[:, t, :, :]    # (B, nh, dh)
            v_t = v[:, t, :, :]        # (B, nh, dh)
            q_t = phi_q[:, t, :, :]    # (B, nh, dh)

            # Update cumulative stats: A += k_t^T outer v_t
            # A shape: (B, nh, dh, dh); einsum b h d, b h e -> b h d e
            A = A + torch.einsum('bhd,bhe->bhde', k_t, v_t)  # (B, nh, dh, dh)
            b = b + k_t                                        # (B, nh, dh)

            # Output: normalised retrieval
            # numerator:   (B, nh, dh) = einsum('bhd, bhde->bhe', q_t, A)
            numer = torch.einsum('bhd,bhde->bhe', q_t, A)    # (B, nh, dh)
            # denominator: (B, nh) = (q_t * b).sum(d)
            denom = (q_t * b).sum(dim=-1, keepdim=True)      # (B, nh, 1)
            o_t = numer / (denom + 1e-6)                      # (B, nh, dh)

            o_list.append(o_t)

        # Stack: (B, T, nh, dh)
        o_perm = torch.stack(o_list, dim=1)                   # (B, T, nh, dh)

        # Un-reorder
        o_orig = o_perm[:, inv_perm, :, :]                   # (B, T, nh, dh)
        return o_orig

    def forward(
        self,
        x: torch.Tensor,
        return_memory: bool = False,
    ) -> Union[torch.Tensor, Tuple[torch.Tensor, List[Optional[torch.Tensor]]]]:
        """
        Args:
            x: (B, C, H, W)  input feature map — must have C == d_model
               NOTE: same signature as GDN2MemoryModule.forward (drop-in).
            return_memory: included for API parity with GDN2MemoryModule.
               Always returns states_list = [None, ...] (no stateful memory).

        Returns:
            return_memory=False → out: (B, C, H, W)
            return_memory=True  → (out, states_list)
                states_list: List[None] length=directions (no state in A1')
                self._last_o_seq: (B, T, nh*d_head) in raster order (for ReIDReadoutHead)
        """
        B, C, H, W = x.shape
        assert C == self.d_model, f"Expected C={self.d_model}, got {C}"
        T = H * W
        assert T <= self.max_seq_len, (
            f"Sequence length {T} (H={H}, W={W}) exceeds LinearAttnModule limit "
            f"{self.max_seq_len}.  Use a smaller spatial resolution."
        )

        # Flatten: (B, C, H, W) → (B, T, C)
        tokens = x.permute(0, 2, 3, 1).reshape(B, T, C)

        # Frangi vesselness + gate computation (M4: proj_erase/proj_g/alpha_e now
        # truly enter the compute graph — no ×0.0 dummies, stateless design preserved).
        #
        # Gate roles in A1' stateless linear attn (mirroring A2 semantics):
        #   write_gate  — amplified at vessel pixels (Frangi, alpha_w)
        #   erase_gate  — suppresses write_gate at vessel pixels (alpha_e),
        #                 reducing write strength where erase signal is strong.
        #                 Combined: actual_gate = write_gate * (1 - erase_gate)
        #   g_out       — per-token output gate (logsigmoid → sigmoid applied below),
        #                 scales the linear-attn output o_seq before projection.
        #
        # This gives proj_erase/proj_g/alpha_e real gradient paths while remaining
        # strictly stateless (no S_t recurrence introduced — A1' identity preserved).
        if self.use_frangi:
            vesselness = self.frangi(x)                              # (B, 1, H, W)
            v_flat = vesselness.permute(0, 2, 3, 1).reshape(B, T, 1)   # (B, T, 1)
            alpha_w = torch.sigmoid(self.alpha_w)
            alpha_e = torch.sigmoid(self.alpha_e)

            # Write gate (same Frangi-boost as A2)
            raw_write = torch.sigmoid(self.proj_write(tokens))      # (B, T, nh)
            write_gate = raw_write * (1.0 + alpha_w * v_flat)       # (B, T, nh)
            write_gate = write_gate.clamp(0.0, 1.0)

            # Erase gate (Frangi-suppressed, mirrors A2's suppression semantics)
            # M4: proj_erase truly enters graph — no ×0.0
            raw_erase = torch.sigmoid(self.proj_erase(tokens))      # (B, T, nh)
            erase_gate = raw_erase * (1.0 - alpha_e * v_flat)       # (B, T, nh)
            erase_gate = erase_gate.clamp(min=0.0)

            # Combined write: suppress write where erase is strong (stateless logic)
            actual_gate = write_gate * (1.0 - erase_gate)           # (B, T, nh)
            actual_gate = actual_gate.clamp(0.0, 1.0)

            # Output gate: M4: proj_g truly enters graph — no ×0.0
            # logsigmoid(.) < 0; exp(.) → (0,1) — acts as per-position output weight
            g_out = F.logsigmoid(self.proj_g(tokens))               # (B, T, nh)
        else:
            actual_gate  = torch.ones(B, T, self.n_heads, device=x.device, dtype=x.dtype)
            erase_gate   = torch.zeros(B, T, self.n_heads, device=x.device, dtype=x.dtype)
            g_out        = torch.zeros(B, T, self.n_heads, device=x.device, dtype=x.dtype)
            write_gate   = actual_gate  # kept for gate_map below

        # Multi-direction scan (same Engineering A as GDN2MemoryModule)
        perms     = _get_scan_permutations(H, W, self.directions, device=x.device)
        inv_perms = [_invert_permutation(p) for p in perms]

        o_list: List[torch.Tensor] = []
        for perm, inv_perm in zip(perms, inv_perms):
            # Run stateless linear attn on this direction's token ordering
            o_dir = self._run_linear_attn_one_dir(tokens, perm, inv_perm)
            o_list.append(o_dir)                                    # (B, T, nh, dh)

        # Average across directions (same merge as GDN2MemoryModule)
        o = torch.stack(o_list, dim=0).mean(dim=0)                 # (B, T, nh, dh)

        # Merge heads → (B, T, nh*dh)
        nh, dh = self.n_heads, self.d_head
        o_seq_raw = o.reshape(B, T, nh * dh)                       # (B, T, nh*dh)

        # M4: output gate g_out truly enters graph (no ×0.0).
        # g_out: (B, T, nh); take mean across heads → (B, T, 1) → broadcast to (B, T, nh*dh)
        # sigmoid(g_out) ∈ (0,1) — scales each token's output (stateless, no S_t recurrence).
        g_gate = torch.sigmoid(g_out).mean(dim=-1, keepdim=True)   # (B, T, 1)
        o_seq = o_seq_raw * g_gate                                  # (B, T, nh*dh)

        # Expose for ReIDReadoutHead (same API as GDN2MemoryModule)
        self._last_o_seq = o_seq

        # Output projection + residual + norm (identical to GDN2MemoryModule)
        out_tokens = self.proj_out(o_seq)                           # (B, T, C)
        out_tokens = self.norm(tokens + out_tokens)                 # residual

        # Reshape back
        out = out_tokens.reshape(B, H, W, C).permute(0, 3, 1, 2)  # (B, C, H, W)

        # M4: actual_gate (write suppressed by erase) applied as channel-wise scaling.
        # This keeps both write_gate and erase_gate in the forward path.
        # actual_gate: (B, T, nh) → mean → (B,1,H,W)
        gate_map = actual_gate.mean(dim=-1).reshape(B, H, W).unsqueeze(1)  # (B,1,H,W)
        out = out * gate_map

        if return_memory:
            states_list = [None] * self.directions
            return out, states_list
        return out


# --------------------------------------------------------------------------- #
#  UNet + GDN-2
# --------------------------------------------------------------------------- #

class UNetGDN2(nn.Module):
    """
    U-Net with GDN-2 Associative Memory inserted at the bottleneck.

    The memory module is inserted after the bottleneck double-conv, at
    spatial resolution H/16 × W/16 (deepest encoder).  For patch_size=512
    this gives 32×32 = 1024 tokens — exactly at the ≤1K limit.

    Re-ID head (Claim 2) is optionally attached via use_reid_head=True.
    The head reads memory output (o_seq) + a selected decoder feature map,
    computes pairwise matching logits for K breakpoint positions.
    Three detach barriers isolate weak supervision — see ReIDReadoutHead.

    Args:
        in_ch:           input channels (1 for green-channel DRIVE)
        out_ch:          output channels (1 for binary seg)
        base_ch:         base channel width (same as UNet)
        d_head:          GDN-2 head dim
        n_heads:         GDN-2 number of heads
        use_memory:      True = GDN-2 active; False = degrade to pure CNN (= UNet).
                         Deprecated in favour of memory_mode; kept for backward compat.
        memory_mode:     'delta_rule'   → A2: GDN2MemoryModule (stateful, default)
                         'linear_attn'  → A1': LinearAttnModule (stateless iso-param)
                         'cnn'          → A0': no attention module (pure CNN)
                         Overrides use_memory when set (use_memory is ignored if
                         memory_mode is explicitly passed).
        backend:         'naive' | 'chunk' (see GDN2MemoryModule)
        directions:      1, 2, or 4 scan directions for ablation (default=1)
        use_frangi:      True = Frangi gate modulation (Mechanism B); False = off
        frangi_scales:   σ values for DifferentiableFrangi
        use_reid_head:   True = attach ReIDReadoutHead; False = skip (pilot default)
        dec_feat_layer:  which decoder layer to sample for re-ID local features.
                         'dec3' (default, H/4 res, 4b channels) or 'dec2' (H/2).
                         Ablation superparameter — dec3 balances context+resolution.
        reid_d_id:       identity embedding dimension in ReIDReadoutHead
        reid_feat_source: 'memory' | 'linear_attn' | 'cnn' (ablation A2/A1'/A0')
        reid_detach_memory_train: bool (ablation A3; MUST be True in non-ablation)
        reid_breakpoint_source:   'gt_skeleton' | 'pred_skeleton' (ablation A2/A4)
        reid_use_loc_feat:        A-v2 M-A: True=fuse(mem,loc), False=memory-only head
                                  (命门 A-v2: False 砍 dec_feat 近路，头只吃 o_seq)
    """

    def __init__(
        self,
        in_ch: int = 1,
        out_ch: int = 1,
        base_ch: int = 32,
        d_head: int = 64,
        n_heads: int = 1,
        use_memory: bool = True,
        memory_mode: Optional[str] = None,  # A1': 'delta_rule'|'linear_attn'|'cnn'
        backend: str = BACKEND,
        directions: int = 1,
        use_frangi: bool = True,
        frangi_scales: Tuple[float, ...] = (0.5, 1.0, 1.5),
        # Re-ID head configuration
        use_reid_head: bool = False,
        dec_feat_layer: str = 'dec3',        # 'dec3' (H/4, 4b ch) or 'dec2' (H/2, 2b ch)
        reid_d_id: int = 64,
        reid_feat_source: str = 'memory',    # ablation A2/A1'/A0'
        reid_detach_memory_train: bool = True,  # ablation A3 — MUST be True normally
        reid_breakpoint_source: str = 'gt_skeleton',  # ablation A2/A4
        reid_use_loc_feat: bool = True,       # A-v2 M-A: False=memory-only head
    ):
        super().__init__()
        b = base_ch
        self.use_reid_head = use_reid_head
        self.d_head = d_head
        self.n_heads = n_heads

        # -- Resolve memory_mode (A1' / A2 / A0' ablation arm selector) --
        # memory_mode overrides use_memory when provided.
        if memory_mode is not None:
            assert memory_mode in ('delta_rule', 'linear_attn', 'cnn'), (
                f"memory_mode must be 'delta_rule', 'linear_attn', or 'cnn'; "
                f"got {memory_mode!r}"
            )
            self.memory_mode = memory_mode
        else:
            # Backward-compat: derive memory_mode from use_memory
            self.memory_mode = 'delta_rule' if use_memory else 'cnn'
        # For backward compat, expose use_memory as property of delta_rule arm
        self.use_memory = (self.memory_mode == 'delta_rule')

        assert dec_feat_layer in ('dec3', 'dec2'), (
            f"dec_feat_layer must be 'dec3' or 'dec2'; got {dec_feat_layer!r}"
        )
        self.dec_feat_layer = dec_feat_layer
        # Channel count for selected decoder layer
        _dec_ch_map = {'dec3': b * 4, 'dec2': b * 2}
        self._dec_ch = _dec_ch_map[dec_feat_layer]

        # ---------- Encoder (identical to UNet) ----------
        self.enc1 = DoubleConv(in_ch, b)
        self.enc2 = Down(b, b * 2)
        self.enc3 = Down(b * 2, b * 4)
        self.enc4 = Down(b * 4, b * 8)
        # Bottleneck
        self.bottleneck = Down(b * 8, b * 16)

        # ---------- Bottleneck attention module (ablation arm selector) ----------
        # A2  (delta_rule):   GDN2MemoryModule  — stateful delta-rule associative memory
        # A1' (linear_attn):  LinearAttnModule   — stateless linear attention, iso-param
        # A0' (cnn):          None               — pure CNN, no attention module
        if self.memory_mode == 'delta_rule':
            self.memory = GDN2MemoryModule(
                d_model=b * 16,
                d_head=d_head,
                n_heads=n_heads,
                max_seq_len=GDN2MemoryModule.MAX_SEQ_LEN,
                backend=backend,
                directions=directions,
                use_frangi=use_frangi,
                frangi_scales=frangi_scales,
            )
            self.linear_attn = None
        elif self.memory_mode == 'linear_attn':
            self.memory = None               # A2 path disabled
            self.linear_attn = LinearAttnModule(
                d_model=b * 16,
                d_head=d_head,
                n_heads=n_heads,
                max_seq_len=LinearAttnModule.MAX_SEQ_LEN,
                directions=directions,
                use_frangi=use_frangi,
                frangi_scales=frangi_scales,
            )
        else:
            # A0' — pure CNN, no attention module
            self.memory = None
            self.linear_attn = None

        # ---------- Decoder (identical to UNet) ----------
        self.dec4 = Up(b * 16, b * 8, b * 8)
        self.dec3 = Up(b * 8, b * 4, b * 4)
        self.dec2 = Up(b * 4, b * 2, b * 2)
        self.dec1 = Up(b * 2, b, b)
        # Head
        self.head = nn.Conv2d(b, out_ch, 1)

        # ---------- Re-ID Readout Head (Claim 2) ----------
        if use_reid_head:
            self.reid_head = ReIDReadoutHead(
                d_head=d_head,
                n_heads=n_heads,
                dec_ch=self._dec_ch,
                d_id=reid_d_id,
                feat_source=reid_feat_source,
                detach_memory_train=reid_detach_memory_train,
                breakpoint_source=reid_breakpoint_source,
                use_loc_feat=reid_use_loc_feat,   # A-v2 M-A: False=memory-only
            )
        else:
            self.reid_head = None

    def forward(
        self,
        x: torch.Tensor,
        return_reid_ctx: bool = False,
    ) -> Union[torch.Tensor, Tuple[torch.Tensor, Dict]]:
        """
        Args:
            x: (B, in_ch, H, W)  — input image (normalised green channel)
               NOTE: GT is NOT passed to this module or any submodule.
            return_reid_ctx: if True, additionally return a dict with context
               tensors for the re-ID head.  Default False (backward-compatible).

        Returns:
            return_reid_ctx=False → logits: (B, out_ch, H, W)
            return_reid_ctx=True  → (logits, reid_ctx)
                reid_ctx is a dict:
                  'o_seq':       (B, T, nh*d_head) — memory output sequence
                                 (raster order, T = H_bot * W_bot)
                  'memory_state': List[Optional[Tensor]] — per-direction final
                                  memory states (each (B,nh,d_head,d_head) or None)
                  'dec_feat':    (B, dec_ch, H_dec, W_dec) — selected decoder feature
                  'H_bot':       int — bottleneck H spatial dim
                  'W_bot':       int — bottleneck W spatial dim
        """
        # Encoder
        e1 = self.enc1(x)
        e2 = self.enc2(e1)
        e3 = self.enc3(e2)
        e4 = self.enc4(e3)
        bot = self.bottleneck(e4)

        # GDN-2 Memory (optional)
        o_seq = None
        memory_states = None
        if self.memory_mode == 'delta_rule' and self.memory is not None:
            # A2: GDN-2 stateful delta-rule associative memory
            if return_reid_ctx:
                bot, memory_states = self.memory(bot, return_memory=True)
                o_seq = self.memory._last_o_seq   # (B, T, nh*d_head)
            else:
                bot = self.memory(bot)
        elif self.memory_mode == 'linear_attn' and self.linear_attn is not None:
            # A1': stateless linear attention (iso-parametric ablation arm)
            if return_reid_ctx:
                bot, memory_states = self.linear_attn(bot, return_memory=True)
                o_seq = self.linear_attn._last_o_seq  # (B, T, nh*d_head)
            else:
                bot = self.linear_attn(bot)
        # A0' (memory_mode == 'cnn'): no attention module — bot unchanged

        # Decoder
        d4 = self.dec4(bot, e4)
        d3 = self.dec3(d4, e3)
        d2 = self.dec2(d3, e2)
        d1 = self.dec1(d2, e1)
        logits = self.head(d1)

        if return_reid_ctx:
            # Select decoder feature according to dec_feat_layer config
            dec_feat = d3 if self.dec_feat_layer == 'dec3' else d2
            H_bot = bot.shape[-2]
            W_bot = bot.shape[-1]
            reid_ctx: Dict = {
                'o_seq': o_seq,               # (B, T, nh*d_head) or None if no memory
                'memory_state': memory_states, # List or None
                'dec_feat': dec_feat,          # (B, dec_ch, H_dec, W_dec)
                'H_bot': H_bot,
                'W_bot': W_bot,
            }
            return logits, reid_ctx

        return logits
