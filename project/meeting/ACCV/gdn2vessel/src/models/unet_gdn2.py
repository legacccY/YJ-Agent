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
from typing import List, Optional, Tuple

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
#  Re-ID Readout Head (Claim 2 interface stub — NOT YET IMPLEMENTED)
# --------------------------------------------------------------------------- #

class ReIDReadoutHead(nn.Module):
    """
    Spatial re-identification readout head (Claim 2 — stub / TODO).

    INTERFACE CONTRACT (finalise after planner+skeptic design session):

    Input:
      memory_state: (B, nh, d_head, d_head)  — final GDN-2 memory matrix S
                    (the associative memory that has "seen" the whole sequence)
      breakpoint_positions: (B, K, 2)  — spatial coordinates (h, w) of K
                            candidate breakpoint locations (derived from
                            input features, NOT GT topology)

    Output:
      match_logits: (B, K, K)  — pairwise same-vessel matching logits.
                   match_logits[b, i, j] > 0 means position i and j belong
                   to the same vessel branch according to the memory.

    Planned mechanism (TODO — needs planner+skeptic sign-off):
      1. Read memory at breakpoint positions: project spatial coords to query q_i,
         retrieve from S the associated value v_i = S^T q_i.
      2. Compute pairwise similarity logits: v_i · v_j / sqrt(d_head).
      3. Symmetric — logits[i,j] == logits[j,i].
      4. Supervised by same-vessel labels from synthetic breakpoint benchmark
         (breakpoint benchmark in STORY §4; GT used ONLY as supervision signal,
         NOT as input to the head at inference — the head reads memory+positions only).

    Why stub:
      This is the headline mechanism (Claim 2).  Implementing it incorrectly
      could create GT leakage or invalidate the novelty argument.
      Design must pass planner+skeptic before code is written.

    Args:
        d_head: head dimension of GDN-2 memory (must match GDN2MemoryModule.d_head)
        n_heads: number of attention heads
    """

    def __init__(self, d_head: int, n_heads: int):
        super().__init__()
        self.d_head = d_head
        self.n_heads = n_heads
        # TODO: implement after planner+skeptic design — see docstring above.
        # Placeholder parameter to keep the module non-empty (avoids PyTorch warnings).
        self._placeholder = nn.Linear(d_head * n_heads, d_head * n_heads, bias=False)

    def forward(
        self,
        memory_state: torch.Tensor,
        breakpoint_positions: torch.Tensor,
    ) -> torch.Tensor:
        """
        Stub — raises NotImplementedError until design is finalised.

        Args:
            memory_state:         (B, nh, d_head, d_head)
            breakpoint_positions: (B, K, 2)  integer (h, w) coords

        Returns:
            match_logits: (B, K, K)

        Raises:
            NotImplementedError: always, until implementation is complete.
        """
        # TODO: implement same-vessel pairwise matching via memory retrieval.
        #   See class docstring for planned mechanism.
        #   Implementation blocked on planner+skeptic design session.
        raise NotImplementedError(
            "ReIDReadoutHead is a stub.  Implementation pending planner+skeptic "
            "design sign-off (see class docstring)."
        )


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
        tokens: torch.Tensor,       # (B, T, C)
        perm: torch.Tensor,         # (T,) index permutation
        inv_perm: torch.Tensor,     # (T,) inverse permutation
        write_gate: torch.Tensor,   # (B, T, nh) — already Frangi-modulated
        erase_gate: torch.Tensor,   # (B, T, nh) — already Frangi-modulated
        g: torch.Tensor,            # (B, T, nh) log-space decay
    ) -> torch.Tensor:
        """
        Run one GDN-2 pass on reordered tokens, un-reorder output.

        Args:
            tokens:      (B, T, C) — full-sequence tokens (un-permuted)
            perm:        index permutation (T,)
            inv_perm:    inverse permutation (T,)
            write_gate:  (B, T, nh) — write β (already modulated)
            erase_gate:  (B, T, nh) — erase modifier (already modulated)
            g:           (B, T, nh) — baseline log-decay

        Returns:
            o_orig: (B, T, nh, dh) — output in original (un-permuted) order
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
        res = self._gdn2_fn(q, k, v, beta=wg, g=g_combined)
        o_perm = res[0] if isinstance(res, tuple) else res   # (B, T, nh, dh)

        # Un-reorder output to original spatial order
        o_orig = o_perm[:, inv_perm, :, :]             # (B, T, nh, dh)
        return o_orig

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, C, H, W)  input feature map — must have C == d_model
               NOTE: this is a feature map derived from input images, NEVER GT.
        Returns:
            out: (B, C, H, W)  same shape, memory-enhanced features
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

        o_list = []
        for perm, inv_perm in zip(perms, inv_perms):
            o_dir = self._run_one_direction(tokens, perm, inv_perm,
                                            write_gate, erase_gate, g)
            o_list.append(o_dir)                       # each (B, T, nh, dh)

        # Merge: average outputs across directions (states are NOT merged)
        o = torch.stack(o_list, dim=0).mean(dim=0)     # (B, T, nh, dh)

        # Merge heads → (B, T, nh*dh)
        o = o.reshape(B, T, nh * self.d_head)

        # Output projection + residual + norm
        out_tokens = self.proj_out(o)                  # (B, T, C)
        out_tokens = self.norm(tokens + out_tokens)    # residual connection

        # Reshape back: (B, T, C) → (B, C, H, W)
        out = out_tokens.reshape(B, H, W, C).permute(0, 3, 1, 2)
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

    Args:
        in_ch:          input channels (1 for green-channel DRIVE)
        out_ch:         output channels (1 for binary seg)
        base_ch:        base channel width (same as UNet)
        d_head:         GDN-2 head dim
        n_heads:        GDN-2 number of heads
        use_memory:     True = GDN-2 active; False = degrade to pure CNN (= UNet)
        backend:        'naive' | 'chunk' (see GDN2MemoryModule)
        directions:     1, 2, or 4 scan directions for ablation (default=1)
        use_frangi:     True = Frangi gate modulation (Mechanism B); False = off
        frangi_scales:  σ values for DifferentiableFrangi
    """

    def __init__(
        self,
        in_ch: int = 1,
        out_ch: int = 1,
        base_ch: int = 32,
        d_head: int = 64,
        n_heads: int = 1,
        use_memory: bool = True,
        backend: str = BACKEND,
        directions: int = 1,
        use_frangi: bool = True,
        frangi_scales: Tuple[float, ...] = (0.5, 1.0, 1.5),
    ):
        super().__init__()
        b = base_ch
        self.use_memory = use_memory

        # ---------- Encoder (identical to UNet) ----------
        self.enc1 = DoubleConv(in_ch, b)
        self.enc2 = Down(b, b * 2)
        self.enc3 = Down(b * 2, b * 4)
        self.enc4 = Down(b * 4, b * 8)
        # Bottleneck
        self.bottleneck = Down(b * 8, b * 16)

        # ---------- GDN-2 Memory (at bottleneck features: b*16 channels) ----------
        if use_memory:
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
        else:
            self.memory = None  # pure CNN path (degrade flag)

        # ---------- Decoder (identical to UNet) ----------
        self.dec4 = Up(b * 16, b * 8, b * 8)
        self.dec3 = Up(b * 8, b * 4, b * 4)
        self.dec2 = Up(b * 4, b * 2, b * 2)
        self.dec1 = Up(b * 2, b, b)
        # Head
        self.head = nn.Conv2d(b, out_ch, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, in_ch, H, W)  — input image (normalised green channel)
               NOTE: GT is NOT passed to this module or any submodule.
        Returns:
            logits: (B, out_ch, H, W)
        """
        # Encoder
        e1 = self.enc1(x)
        e2 = self.enc2(e1)
        e3 = self.enc3(e2)
        e4 = self.enc4(e3)
        bot = self.bottleneck(e4)

        # GDN-2 Memory (optional)
        if self.memory is not None:
            bot = self.memory(bot)

        # Decoder
        d4 = self.dec4(bot, e4)
        d3 = self.dec3(d4, e3)
        d2 = self.dec2(d3, e2)
        d1 = self.dec1(d2, e1)
        return self.head(d1)
