"""
Re-ID loss functions for gdn2vessel Claim 2 (spatial same-vessel re-identification).

Loss design (planner+skeptic 2026-06-20):
  L_match      — BCE on K×K pairwise logits against synthetic same-root labels.
                 Labels come from apply_breaks (synth_breaks.py): the two endpoints
                 of the same synthetic cut are positive pairs; cross-cut pairs are
                 negative.  Because ReIDReadoutHead applies three detach barriers,
                 this loss ONLY updates the head's projection layers (mem_proj /
                 loc_proj / fuse / log_temp) — it mathematically cannot flow into
                 the GDN-2 memory, encoder, or Frangi gate.

  L_contrastive — InfoNCE-style contrastive loss on same-segment sampling.
                 Positive pairs = two points sampled from the same vessel segment.
                 Negative pairs = points from different segments (in-batch).
                 # TODO (P4): implement proper segment-aware positive mining;
                 #   current implementation is a simplified placeholder using
                 #   the same same_root_labels matrix as L_match.

  Combined loss:
    L_total = L_seg + lambda_reid * L_match + lambda_c * L_contrastive
    Default: lambda_reid=0.1, lambda_c=0.05
    # NOTE: these lambda values are self-designed (novel mechanism, NOT reproduced
    #   from any prior work).  They are NOT official hyperparameters.
    #   Pilot will grid-search lambda_reid in {0.05, 0.1, 0.3} and
    #   lambda_c in {0.0, 0.05, 0.1} — see PLAN/MASTER_PLAN.md block D.

Implementation notes:
  - No scipy (avoids OMP Error #15 on Windows with PyTorch).
  - No fork-based multiprocessing context here (loss is pure tensor ops).
  - Paths: no backslash literals.
"""

from __future__ import annotations

from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F


# --------------------------------------------------------------------------- #
#  L_match: synthetic breakpoint BCE matching loss
# --------------------------------------------------------------------------- #

def compute_match_loss(
    logits: torch.Tensor,
    same_root_labels: torch.Tensor,
    reduction: str = 'mean',
) -> torch.Tensor:
    """
    BCE loss between pairwise match logits and same-root binary labels.

    Because ReIDReadoutHead applies three stop-gradient detach barriers
    (detach1/2/3), backpropagating this loss ONLY updates the head's
    projection parameters (mem_proj / loc_proj / fuse / log_temp).
    It cannot flow into the GDN-2 memory, encoder, or Frangi gate,
    preserving Claim 1 (GT-topology-free associative memory).

    Args:
        logits:           (B, K, K) — pairwise logits from ReIDReadoutHead.forward.
                          Diagonal is -inf (self-matches excluded).
        same_root_labels: (B, K, K) — float {0.0, 1.0}.
                          same_root_labels[b, i, j] = 1 if breakpoints i and j
                          belong to the same vessel segment (from apply_breaks),
                          0 otherwise.  Diagonal is typically 0 (ignored anyway
                          because corresponding logit is -inf).
        reduction:        'mean' | 'sum' | 'none'

    Returns:
        loss: scalar (reduction='mean'/'sum') or (B, K, K) tensor ('none')
    """
    B, K, _ = logits.shape
    # Exclude diagonal entries (logit=-inf → gradient is 0, but -inf*label
    # can produce NaN).  Build a valid mask: True where both finite logit and
    # label should contribute.
    diag_mask = torch.eye(K, dtype=torch.bool, device=logits.device)   # (K, K)
    valid_mask = ~diag_mask.unsqueeze(0).expand(B, K, K)               # (B, K, K)

    # Clamp logits to prevent NaN from -inf positions (they're excluded anyway)
    logits_safe = logits.clone()
    logits_safe[~valid_mask] = 0.0   # will be masked out in loss

    loss_raw = F.binary_cross_entropy_with_logits(
        logits_safe,
        same_root_labels,
        reduction='none',
    )   # (B, K, K)

    # Zero out diagonal (excluded from training signal)
    loss_raw = loss_raw * valid_mask.float()

    if reduction == 'none':
        return loss_raw
    elif reduction == 'sum':
        return loss_raw.sum()
    else:  # 'mean' — average over valid (non-diagonal) entries
        n_valid = valid_mask.float().sum().clamp(min=1.0)
        return loss_raw.sum() / n_valid


# --------------------------------------------------------------------------- #
#  L_contrastive: simplified contrastive loss (P4 full mining is TODO)
# --------------------------------------------------------------------------- #

def compute_contrastive_loss(
    logits: torch.Tensor,
    same_root_labels: torch.Tensor,
    temperature: float = 0.07,
) -> torch.Tensor:
    """
    Simplified InfoNCE-style contrastive loss over breakpoint embeddings.

    Current implementation uses the same same_root_labels matrix as positive
    indicator — for each anchor i, positives are j where same_root_labels[b,i,j]=1
    and negatives are j where same_root_labels[b,i,j]=0.

    # TODO (P4): replace with proper segment-aware positive mining:
    #   - Sample anchor + positive from same vessel segment (continuous stretch).
    #   - Sample negatives from different segments in the same image.
    #   - Use hard-negative mining (closest negative in embedding space).
    #   Reference: SimCLR (Chen et al. 2020) / SupCon (Khosla et al. 2020)
    #   for implementation pattern.
    #   # NOTE: lambda_c=0.05 is self-designed; not from any prior work.

    Args:
        logits:           (B, K, K) — pairwise logits (already temperature-scaled
                          inside ReIDReadoutHead via log_temp).  Here we apply
                          an additional fixed temperature for the contrastive
                          softmax normalisation (log_temp is learnable; this
                          temperature is fixed for contrastive formulation).
        same_root_labels: (B, K, K) — binary {0, 1} same-root indicator
        temperature:      softmax temperature for contrastive normalisation
                          # TODO: researcher to confirm value; 0.07 is standard
                          #   SimCLR default but has no official grounding here.

    Returns:
        loss: scalar
    """
    B, K, _ = logits.shape
    # Exclude diagonal from both positives and denominator
    diag_mask = torch.eye(K, dtype=torch.bool, device=logits.device)

    loss_total = torch.tensor(0.0, device=logits.device)
    n_valid_anchors = 0

    for b in range(B):
        logit_b = logits[b]               # (K, K)
        label_b = same_root_labels[b]     # (K, K)

        for i in range(K):
            pos_mask = (label_b[i] > 0.5) & ~diag_mask[i]   # positives for anchor i
            neg_mask = (label_b[i] < 0.5) & ~diag_mask[i]   # negatives

            if pos_mask.sum() == 0:
                # No positive pair for this anchor — skip
                continue

            # Contrastive: log( sum(exp(pos)) / sum(exp(all non-diag)) )
            # Numerically stable via logsumexp
            all_mask = pos_mask | neg_mask
            if all_mask.sum() < 2:
                continue

            all_logits = logit_b[i][all_mask] / temperature    # (n_all,)
            pos_logits = logit_b[i][pos_mask] / temperature    # (n_pos,)

            log_denom = torch.logsumexp(all_logits, dim=0)
            log_num   = torch.logsumexp(pos_logits, dim=0)
            loss_total = loss_total + (log_denom - log_num)
            n_valid_anchors += 1

    if n_valid_anchors == 0:
        return torch.tensor(0.0, device=logits.device, requires_grad=True)
    return loss_total / n_valid_anchors


# --------------------------------------------------------------------------- #
#  Combined loss (seg + reid)
# --------------------------------------------------------------------------- #

def compute_reid_combined_loss(
    seg_loss: torch.Tensor,
    reid_logits: Optional[torch.Tensor],
    same_root_labels: Optional[torch.Tensor],
    lambda_reid: float = 0.1,    # grid search {0.05, 0.1, 0.3} in pilot
    lambda_c: float = 0.05,      # grid search {0.0, 0.05, 0.1} in pilot
    # NOTE: these defaults are self-designed (novel mechanism), NOT from any paper.
) -> torch.Tensor:
    """
    Total training loss combining segmentation + re-ID matching losses.

    L_total = L_seg + lambda_reid * L_match + lambda_c * L_contrastive

    The re-ID terms are zero when reid_logits is None (e.g., when
    use_reid_head=False or breakpoints are not available).

    Args:
        seg_loss:          scalar — L_seg (Dice + BCE, from seg_loss.py / train loop)
        reid_logits:       (B, K, K) or None — from ReIDReadoutHead.forward
        same_root_labels:  (B, K, K) float {0,1} or None — synthetic break GT
        lambda_reid:       weight for L_match
                           # NOTE: self-designed; grid-search in pilot.
        lambda_c:          weight for L_contrastive
                           # NOTE: self-designed; grid-search in pilot.

    Returns:
        total_loss: scalar
    """
    total = seg_loss

    if reid_logits is not None and same_root_labels is not None:
        l_match = compute_match_loss(reid_logits, same_root_labels)
        l_cont  = compute_contrastive_loss(reid_logits, same_root_labels)
        total   = total + lambda_reid * l_match + lambda_c * l_cont

    return total


# --------------------------------------------------------------------------- #
#  Convenience class (wraps hyper-params for training config YAML)
# --------------------------------------------------------------------------- #

class ReIDLoss(nn.Module):
    """
    Stateless wrapper around compute_reid_combined_loss for use in training loops.

    Args:
        lambda_reid: float (default 0.1)
                     # NOTE: self-designed; grid {0.05, 0.1, 0.3} in pilot
        lambda_c:    float (default 0.05)
                     # NOTE: self-designed; grid {0.0, 0.05, 0.1} in pilot
    """

    def __init__(
        self,
        lambda_reid: float = 0.1,   # NOTE: self-designed, not from prior work
        lambda_c: float = 0.05,     # NOTE: self-designed, not from prior work
    ):
        super().__init__()
        self.lambda_reid = lambda_reid
        self.lambda_c = lambda_c

    def forward(
        self,
        seg_loss: torch.Tensor,
        reid_logits: Optional[torch.Tensor] = None,
        same_root_labels: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        return compute_reid_combined_loss(
            seg_loss=seg_loss,
            reid_logits=reid_logits,
            same_root_labels=same_root_labels,
            lambda_reid=self.lambda_reid,
            lambda_c=self.lambda_c,
        )
