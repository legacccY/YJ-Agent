"""Phase 4 unit tests: Q-VIB components."""

import numpy as np
import torch
import pytest

from models.quality_adaptive_prior import QualityAdaptivePrior
from models.quality_tokenizer import QualityTokenizer
from models.q_vib_encoder import QVIBEncoder
from models.q_vib_loss import QVIBLoss
from models.qad_classifier import QADClassifier
from models.feature_extractor import extract_abcd


# ── Prior ──────────────────────────────────────────────────────────────────

class TestQualityAdaptivePrior:
    def setup_method(self):
        self.prior = QualityAdaptivePrior(sigma0_sq=0.1, tau=0.5, alpha=5.0)

    def test_variance_range(self):
        q = torch.rand(8, 5)
        var = self.prior.prior_variance(q)
        assert var.shape == (8,)
        assert (var >= 0.1).all() and (var <= 1.0).all(), f"variance out of [0.1, 1.0]: {var}"

    def test_lemma1_monotone_decreasing(self):
        """Lemma 1: sigma^2(q_bar) is strictly decreasing in q_bar."""
        qbars = torch.linspace(0.0, 1.0, 20)
        q_batch = qbars.unsqueeze(1).expand(-1, 5)
        vars_ = self.prior.prior_variance(q_batch)
        diffs = vars_[1:] - vars_[:-1]
        assert (diffs <= 0).all(), f"Non-monotone at {diffs[diffs > 0]}"

    def test_boundary_low_quality(self):
        """Low quality (q_bar->0) => variance ~1 (max compression)."""
        q = torch.zeros(4, 5)
        var = self.prior.prior_variance(q)
        assert (var > 0.9).all(), f"Expected ~1 for q=0, got {var}"

    def test_boundary_high_quality(self):
        """High quality (q_bar->1) => variance close to sigma0^2 (min compression).

        With tau=0.5, alpha=5: sigma^2(1) = 0.1 + 0.9*sigmoid(-2.5) ~= 0.168.
        Must be < sigma^2(0) and significantly below 1.0.
        """
        q = torch.ones(4, 5)
        var = self.prior.prior_variance(q)
        assert (var < 0.25).all(), f"Expected < 0.25 for q=1, got {var}"
        q_low = torch.zeros(4, 5)
        var_low = self.prior.prior_variance(q_low)
        assert (var < var_low).all(), "High-quality variance must be less than low-quality"

    def test_kl_non_negative(self):
        mu = torch.randn(8, 32)
        log_sigma_sq = torch.zeros(8, 32)
        q = torch.rand(8, 5)
        kl = self.prior.kl_divergence(mu, log_sigma_sq, q)
        assert kl.shape == (8,)
        assert (kl >= 0).all(), f"Negative KL: {kl.min()}"

    def test_kl_zero_when_prior_matches(self):
        """KL = 0 when encoder matches prior: mu=0, sigma^2=prior_var."""
        prior = QualityAdaptivePrior(sigma0_sq=1.0, tau=0.5, alpha=5.0)
        q = torch.ones(4, 5)  # high quality -> prior_var ~ 1.0
        mu = torch.zeros(4, 16)
        log_sigma_sq = torch.zeros(4, 16)  # sigma^2 = 1.0
        kl = prior.kl_divergence(mu, log_sigma_sq, q)
        assert (kl.abs() < 1e-4).all(), f"Expected ~0 KL, got {kl}"


# ── Tokenizer ──────────────────────────────────────────────────────────────

class TestQualityTokenizer:
    def setup_method(self):
        self.tok = QualityTokenizer(q_dim=5, hidden_dim=32, out_dim=16, spectral=True)

    def test_output_shape(self):
        q = torch.rand(4, 5)
        delta = self.tok(q)
        assert delta.shape == (4,), f"Expected (4,), got {delta.shape}"

    def test_boundary_perfect_quality(self):
        """Theorem 1 prerequisite: delta=0 when q=1 (boundary condition)."""
        q = torch.ones(4, 5)
        delta = self.tok(q)
        assert delta.abs().max() < 1e-5, f"Expected delta=0 at q=1, got {delta}"

    def test_nonzero_for_degraded(self):
        """Tokenizer should produce nonzero bias for degraded images."""
        q = torch.zeros(4, 5)  # worst quality
        delta = self.tok(q)
        assert delta.abs().max() > 1e-6


# ── Encoder ────────────────────────────────────────────────────────────────

class TestQVIBEncoder:
    def setup_method(self):
        self.enc = QVIBEncoder(abcd_dim=4, q_dim=5, d_model=32, n_heads=4, latent_dim=16)
        self.enc_efnet = QVIBEncoder(
            abcd_dim=4, q_dim=5, d_model=32, n_heads=4, latent_dim=16, efnet_dim=1280
        )

    def test_output_shapes(self):
        abcd = torch.rand(4, 4)
        q = torch.rand(4, 5)
        mu, log_sigma_sq = self.enc(abcd, q)
        assert mu.shape == (4, 16)
        assert log_sigma_sq.shape == (4, 16)

    def test_log_sigma_clamped(self):
        abcd = torch.rand(8, 4)
        q = torch.rand(8, 5)
        _, log_sigma_sq = self.enc(abcd, q)
        assert log_sigma_sq.min() >= -10.0 - 1e-5
        assert log_sigma_sq.max() <= 2.0 + 1e-5

    def test_reparameterize_shape(self):
        abcd = torch.rand(4, 4)
        q = torch.rand(4, 5)
        mu, log_sigma_sq = self.enc(abcd, q)
        z = self.enc.reparameterize(mu, log_sigma_sq)
        assert z.shape == (4, 16)

    def test_no_nan(self):
        abcd = torch.rand(4, 4)
        q = torch.rand(4, 5)
        mu, log_sigma_sq = self.enc(abcd, q)
        z = self.enc.reparameterize(mu, log_sigma_sq)
        assert not torch.isnan(mu).any()
        assert not torch.isnan(z).any()

    def test_efnet_token_output_shapes(self):
        """Encoder with EfficientNet 5th token produces same output shape."""
        abcd = torch.rand(4, 4)
        q = torch.rand(4, 5)
        efnet_feat = torch.rand(4, 1280)
        mu, log_sigma_sq = self.enc_efnet(abcd, q, efnet_feat=efnet_feat)
        assert mu.shape == (4, 16)
        assert log_sigma_sq.shape == (4, 16)

    def test_efnet_none_fallback(self):
        """efnet_dim encoder called without efnet_feat falls back to ABCD-only."""
        abcd = torch.rand(4, 4)
        q = torch.rand(4, 5)
        mu, _ = self.enc_efnet(abcd, q, efnet_feat=None)
        assert mu.shape == (4, 16)

    def test_efnet_changes_output(self):
        """EfficientNet token should change the encoder output vs ABCD-only."""
        abcd = torch.rand(4, 4)
        q = torch.rand(4, 5)
        efnet_feat = torch.rand(4, 1280)
        mu_with, _ = self.enc_efnet(abcd, q, efnet_feat=efnet_feat)
        mu_without, _ = self.enc_efnet(abcd, q, efnet_feat=None)
        assert not torch.allclose(mu_with, mu_without), "efnet_feat should change the output"


# ── Loss ───────────────────────────────────────────────────────────────────

class TestQVIBLoss:
    def setup_method(self):
        prior = QualityAdaptivePrior()
        self.loss_fn = QVIBLoss(prior=prior, beta_max=1e-3, warmup_steps=100)

    def test_loss_positive(self):
        logits = torch.randn(4, 2)
        targets = torch.randint(0, 2, (4,))
        mu = torch.randn(4, 16)
        log_sigma_sq = torch.zeros(4, 16)
        q = torch.rand(4, 5)
        loss, info = self.loss_fn(logits, targets, mu, log_sigma_sq, q)
        assert loss.item() > 0
        assert not torch.isnan(loss)

    def test_beta_annealing(self):
        prior = QualityAdaptivePrior()
        loss_fn = QVIBLoss(prior=prior, beta_max=1.0, warmup_steps=10)
        assert loss_fn.current_beta() == 0.0
        for _ in range(5):
            loss_fn.step()
        assert abs(loss_fn.current_beta() - 0.5) < 1e-6
        for _ in range(5):
            loss_fn.step()
        assert loss_fn.current_beta() == 1.0


# ── Classifier ─────────────────────────────────────────────────────────────

def test_qad_classifier_shape():
    clf = QADClassifier(latent_dim=16, hidden_dim=32, num_classes=2)
    z = torch.randn(4, 16)
    logits = clf(z)
    assert logits.shape == (4, 2)


# ── Feature Extractor ──────────────────────────────────────────────────────

def test_abcd_feature_range():
    img = (np.random.rand(224, 224, 3) * 255).astype(np.uint8)
    mask = np.zeros((224, 224), dtype=bool)
    mask[80:140, 80:140] = True
    feats = extract_abcd(img, mask)
    assert feats.shape == (4,), f"Expected (4,), got {feats.shape}"
    assert feats.min() >= 0.0 and feats.max() <= 1.0, f"Features out of [0,1]: {feats}"


def test_abcd_empty_mask():
    img = (np.random.rand(64, 64, 3) * 255).astype(np.uint8)
    mask = np.zeros((64, 64), dtype=bool)
    feats = extract_abcd(img, mask)
    assert not np.isnan(feats).any(), "NaN with empty mask"
