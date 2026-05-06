"""Multi-task losses for VisiScore-Net training."""
import torch
import torch.nn as nn
import torch.nn.functional as F


class RankingLoss(nn.Module):
    """Enforce that clean images score higher than degraded ones by a margin."""

    def __init__(self, margin: float = 0.1):
        super().__init__()
        self.margin = margin

    def forward(self, scores_deg: torch.Tensor, scores_clean: torch.Tensor) -> torch.Tensor:
        loss = F.relu(self.margin + scores_deg.mean(dim=1) - scores_clean.mean(dim=1))
        return loss.mean()


class VisiScoreLoss(nn.Module):
    def __init__(self, ranking_weight: float = 0.3):
        super().__init__()
        self.ranking = RankingLoss()
        self.ranking_weight = ranking_weight

    def forward(
        self,
        pred_deg: torch.Tensor,
        pred_clean: torch.Tensor,
        target_deg: torch.Tensor,
    ) -> torch.Tensor:
        mse = F.mse_loss(pred_deg, target_deg)
        rank = self.ranking(pred_deg, pred_clean)
        return mse + self.ranking_weight * rank
