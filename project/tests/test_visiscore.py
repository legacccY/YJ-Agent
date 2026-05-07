"""Phase 3 unit tests: VisiScoreNet model + losses."""
import torch

from models.losses import RankingLoss, VisiScoreLoss
from models.visiscore import VisiScoreNet

_SMALL_BACKBONE = "mobilenetv3_small_100"


def test_visiscore_forward_shape():
    model = VisiScoreNet(backbone=_SMALL_BACKBONE, pretrained=False, num_dims=5)
    x = torch.randn(2, 3, 224, 224)
    out = model(x)
    assert out.shape == (2, 5), f"expected (2,5), got {out.shape}"


def test_visiscore_output_range():
    model = VisiScoreNet(backbone=_SMALL_BACKBONE, pretrained=False, num_dims=5)
    model.eval()
    with torch.no_grad():
        out = model(torch.randn(4, 3, 224, 224))
    assert out.min() >= 0.0 and out.max() <= 1.0, f"scores out of [0,1]: {out.min():.3f}~{out.max():.3f}"


def test_ranking_loss_zero_when_clean_better():
    ranking = RankingLoss(margin=0.1)
    scores_clean = torch.full((2, 5), 0.9)
    scores_deg = torch.full((2, 5), 0.3)
    loss = ranking(scores_deg, scores_clean)
    assert loss.item() == 0.0, f"expected 0, got {loss.item()}"


def test_ranking_loss_positive_when_inverted():
    ranking = RankingLoss(margin=0.1)
    scores_clean = torch.full((2, 5), 0.3)
    scores_deg = torch.full((2, 5), 0.9)
    loss = ranking(scores_deg, scores_clean)
    assert loss.item() > 0.0


def test_visiscore_forward_features_shape():
    model = VisiScoreNet(backbone=_SMALL_BACKBONE, pretrained=False, num_dims=5)
    model.eval()
    with torch.no_grad():
        feats, q = model.forward_features(torch.randn(2, 3, 224, 224))
    assert q.shape == (2, 5), f"q shape wrong: {q.shape}"
    assert feats.ndim == 2 and feats.shape[0] == 2, f"features shape wrong: {feats.shape}"
    assert q.min() >= 0.0 and q.max() <= 1.0


def test_visiscore_loss_no_nan():
    loss_fn = VisiScoreLoss()
    pred_deg = torch.rand(4, 5)
    pred_clean = torch.rand(4, 5)
    target_deg = torch.rand(4, 5)
    target_clean = torch.ones(4, 5)
    loss = loss_fn(pred_deg, pred_clean, target_deg)
    assert loss.item() >= 0.0
    assert not torch.isnan(loss)
