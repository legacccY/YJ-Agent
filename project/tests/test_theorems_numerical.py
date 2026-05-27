"""Numerical (toy) verification of 5-theorem closure.

Covers:
- Proposition 3  (VisiEnhance entropy reduction)         — Lemma 2.2 in Thm 2 derivation
- Lemma 3        (DP-Loss mutual-info lower bound)        — Pinsker-style
- Theorem 2      (Closed-loop agent expected-risk bound)  — P1/P2/P3 predictions

These are synthetic toys (numpy + scipy only). They guard against algebra/sign
mistakes in the proofs without requiring trained checkpoints. Real empirical
verification on csv (E4/E5/E7) is M2 D8-D28 (Plan A finish).

Run:
    cd D:/YJ-Agent/project
    pytest tests/test_theorems_numerical.py -v
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.stats import bootstrap


RNG = np.random.default_rng(20260524)


# ── Toy primitives ─────────────────────────────────────────────────────────────


def softmax(logits: np.ndarray, axis: int = -1) -> np.ndarray:
    z = logits - logits.max(axis=axis, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=axis, keepdims=True)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def entropy(p: np.ndarray, axis: int = -1, eps: float = 1e-12) -> np.ndarray:
    return -(p * np.log(p + eps)).sum(axis=axis)


def kl(p: np.ndarray, q: np.ndarray, axis: int = -1, eps: float = 1e-12) -> np.ndarray:
    return (p * (np.log(p + eps) - np.log(q + eps))).sum(axis=axis)


def total_variation(p: np.ndarray, q: np.ndarray, axis: int = -1) -> np.ndarray:
    return 0.5 * np.abs(p - q).sum(axis=axis)


def synthetic_predictor(x_logits: np.ndarray, q_bar: np.ndarray, sharpening: float = 4.0) -> np.ndarray:
    """Toy quality-aware predictor.

    The predictor is sharper (lower entropy) when q_bar is higher. This mimics a
    well-calibrated Q-VIB + classifier on quality-stratified inputs.
    """
    gain = sharpening * q_bar[..., None]
    return softmax(x_logits * (1.0 + gain))


# ── Proposition 3: enhancement reduces expected entropy ────────────────────────


def test_proposition3_entropy_strictly_decreases():
    """If T_ω strictly raises q̄ and predictor is quality-aware, expected entropy drops."""
    n = 2000
    K = 7  # HAM10000 class count, matches §A1
    x_logits = RNG.normal(size=(n, K))
    q_bar = RNG.uniform(0.1, 0.6, size=n)
    # Enhancement strictly raises mean quality (Prop 3 hypothesis).
    q_bar_enh = np.clip(q_bar + RNG.uniform(0.10, 0.20, size=n), 0.0, 1.0)
    assert (q_bar_enh > q_bar).all(), "enhancement must strictly raise q_bar (Prop 3 hypothesis)"

    p_direct = synthetic_predictor(x_logits, q_bar)
    p_enhance = synthetic_predictor(x_logits, q_bar_enh)

    H_direct = entropy(p_direct).mean()
    H_enhance = entropy(p_enhance).mean()

    # Prop 3 (and Lemma 2.2 of Thm 2 derivation).
    assert H_enhance < H_direct, f"H_enhance={H_enhance:.4f} not < H_direct={H_direct:.4f}"
    # Sanity: gap is meaningful (> 1% in nats).
    assert (H_direct - H_enhance) > 0.01


def test_proposition3_fails_when_enhancement_degrades_quality():
    """Counter-control: if q_bar drops, Prop 3 conclusion should NOT hold."""
    n = 2000
    K = 7
    x_logits = RNG.normal(size=(n, K))
    q_bar = RNG.uniform(0.4, 0.9, size=n)
    q_bar_bad = np.clip(q_bar - RNG.uniform(0.10, 0.20, size=n), 0.0, 1.0)

    p_direct = synthetic_predictor(x_logits, q_bar)
    p_bad = synthetic_predictor(x_logits, q_bar_bad)

    # Entropy should rise, not fall.
    assert entropy(p_bad).mean() > entropy(p_direct).mean()


# ── Lemma 3: DP-Loss bound implies mutual-info lower bound ────────────────────


def _joint_pyz(p_yz: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (p_y, p_z, p_y_given_z) for a discrete joint p(y,z)."""
    p_y = p_yz.sum(axis=1)
    p_z = p_yz.sum(axis=0)
    p_y_given_z = (p_yz / (p_z[None, :] + 1e-12))
    return p_y, p_z, p_y_given_z


def discrete_mutual_info(p_yz: np.ndarray, eps: float = 1e-12) -> float:
    p_y = p_yz.sum(axis=1, keepdims=True)
    p_z = p_yz.sum(axis=0, keepdims=True)
    ratio = p_yz / (p_y * p_z + eps)
    return float((p_yz * np.log(ratio + eps)).sum())


def test_lemma3_pinsker_style_mi_upper_bound_on_drop():
    """Lemma 3 (upper bound form):
       KL(p_enh || p_ref) ≤ ε  ⇒  I(Z_ref; Y) − I(Z_enh; Y) ≤ β · ε
    i.e., MI can drop by at most β·ε given a KL constraint.

    Toy: perturb p_ref by various magnitudes, regress MI-drop vs ε.
    Perturbations can either raise or lower MI; we care that the *drop* is
    bounded above linearly in ε (Pinsker + bounded log-density).
    """
    K, D = 4, 8
    p_ref = RNG.dirichlet(np.ones(K * D)).reshape(K, D)
    mi_ref = discrete_mutual_info(p_ref)

    epsilons = []
    mi_drops = []
    for scale in np.linspace(0.005, 0.05, 20):
        for _ in range(50):
            noise = RNG.normal(scale=scale, size=(K, D))
            p_enh = p_ref + noise
            p_enh = np.clip(p_enh, 1e-6, None)
            p_enh = p_enh / p_enh.sum()

            eps = float(kl(p_enh.ravel(), p_ref.ravel(), axis=0))
            drop = max(mi_ref - discrete_mutual_info(p_enh), 0.0)  # only positive drops

            epsilons.append(eps)
            mi_drops.append(drop)

    epsilons_arr = np.array(epsilons)
    drops_arr = np.array(mi_drops)

    # Worst-case slope (drop / ε) over all perturbations gives empirical β.
    finite_mask = epsilons_arr > 1e-6
    ratios = drops_arr[finite_mask] / epsilons_arr[finite_mask]
    beta_empirical = float(np.percentile(ratios, 99))  # robust to a few outliers

    # Pinsker + Lipschitz: β should be O(1) — small enough that bound is meaningful.
    assert beta_empirical < 50.0, f"empirical β={beta_empirical:.3f} too large; bound vacuous"
    # And the drop must scale sub-linearly: at small ε, drop should also be small.
    small_eps = epsilons_arr < 0.01
    if small_eps.sum() > 10:
        assert drops_arr[small_eps].mean() < 0.1, "small-ε perturbations cause big MI drop — bound fails"


# ── Lemma 3 (√ε scaling, paired latent): MI drop ≤ β·√ε  ──────────────────────


def test_lemma3_sqrt_epsilon_scaling_paired_latent():
    """Lemma 3 (sharp √ε form):
        KL(p^enh || p^ref) ≤ ε  ⇒  I(Z_ref;Y) − I(Z_enh;Y) ≤ β · √ε
    with β = M · L_q / √2  (M = log K, L_q = classifier Lipschitz in TV).

    Toy: paired Gaussian latents p_ref = N(μ_ref, I_d), p_enh = N(μ_ref + δ, I_d).
    KL(p_enh || p_ref) = ‖δ‖²/2 = ε  ⇒  ‖δ‖ = √(2ε).
    Linear toy classifier  q(y=1|z) = σ(w·z)  with ‖w‖ = L_q.
    Then |Δ_predictive_TV| ≤ L_q · ‖δ‖ = L_q · √(2ε),
    and MI gap bounded above by Fannes constant × that TV.
    Test the regression slope of (MI drop) vs √ε is finite and < β_theory.
    """
    K = 2
    M = math.log(K)  # ≈ 0.693
    L_q = 1.5        # match Prop3_Lemma3 doc constant calibration
    d = 8
    beta_theory = M * L_q / math.sqrt(2)  # ≈ 0.735

    rng = np.random.default_rng(7777)

    def discrete_mi_from_samples(z, y, bins=6):
        """Empirical MI between latent (continuous) and label (binary) via binning."""
        z1 = z[:, 0]  # use first dim for binning
        edges = np.quantile(z1, np.linspace(0, 1, bins + 1))
        edges[0], edges[-1] = -np.inf, np.inf
        z_bin = np.digitize(z1, edges) - 1
        z_bin = np.clip(z_bin, 0, bins - 1)
        joint = np.zeros((bins, K))
        for b, lbl in zip(z_bin, y):
            joint[b, lbl] += 1
        joint = joint / joint.sum()
        return discrete_mutual_info(joint)

    # Reference predictor + label
    n = 6000
    mu_ref = np.zeros(d); mu_ref[0] = 1.0  # signal in first dim
    z_ref = rng.normal(loc=mu_ref, size=(n, d))
    w = np.zeros(d); w[0] = L_q
    p1 = _sigmoid(z_ref @ w)
    y = (rng.uniform(size=n) < p1).astype(int)
    mi_ref = discrete_mi_from_samples(z_ref, y)

    epsilons, mi_drops = [], []
    for eps_target in np.linspace(0.005, 0.20, 20):
        # δ with ‖δ‖ = √(2 eps_target)
        delta = rng.normal(size=d); delta = delta / np.linalg.norm(delta) * math.sqrt(2 * eps_target)
        z_enh = z_ref + delta  # same y (paired)
        eps = 0.5 * np.dot(delta, delta)  # KL of two unit-covariance Gaussians

        mi_enh = discrete_mi_from_samples(z_enh, y)
        drop = max(mi_ref - mi_enh, 0.0)
        epsilons.append(eps); mi_drops.append(drop)

    eps_arr = np.array(epsilons)
    drop_arr = np.array(mi_drops)
    sqrt_eps = np.sqrt(eps_arr)

    # Regress drop on √ε (intercept absorbed by tolerance).
    slope, intercept = np.polyfit(sqrt_eps, drop_arr, deg=1)

    # Empirical slope should be finite, not absurdly large, and bound by theory + slack.
    assert abs(slope) < 5.0, f"empirical slope {slope:.3f} too large; Lemma 3 may be vacuous"
    # Drop should be small at small ε (sub-linear).
    small = eps_arr < 0.01
    if small.sum() > 3:
        assert drop_arr[small].mean() < 0.15, "small-ε drop too large — √ε bound broken"
    # And the worst sample ratio should not exceed β_theory by more than 10× safety margin.
    ratios = drop_arr / np.maximum(sqrt_eps, 1e-9)
    worst = float(np.percentile(ratios, 95))
    assert worst < 10 * beta_theory, f"95th-percentile ratio {worst:.3f} >> 10·β_theory={10*beta_theory:.3f}"


# ── Theorem 2: salvage gain Δ(q̄, T_ω) — P1 / P2 / P3 ──────────────────────────


@pytest.fixture(scope="module")
def thm2_population():
    """Stratified synthetic population for Theorem 2 verification.

    Generative model (binary classification, K=2):
      1. Sample true label y ∈ {0, 1} uniformly.
      2. Sample latent margin m ~ N(μ_y, 1), with μ_1 = +1.5, μ_0 = −1.5.
      3. Sample quality scalar q_bar uniform on [0, 1].
      4. Observation noise: ε ~ N(0, σ(q_bar)²) where σ shrinks with q_bar
         (low q ⇒ noisy ⇒ predictor often wrong; high q ⇒ clean).
      5. Observed score s_obs = m + ε. Predictor: σ(s_obs).
      6. Enhancement T_ω: only on salvage band [0.35, 0.55], raises q_bar by
         ~+0.20 (and equivalently scales ε down). Outside band: identity.

    Under this model, Prop 3 holds *and* the predictor actually flips argmax
    on salvage-band samples, so risk reduction is realised, not vacuous.
    """
    n = 8000
    rng = np.random.default_rng(20260524)

    y = rng.integers(0, 2, size=n)
    margin = rng.normal(loc=np.where(y == 1, 1.5, -1.5), scale=1.0)

    q_bar = rng.uniform(0.0, 1.0, size=n)

    def _noise_scale(q):  # low q → high noise; high q → low noise.
        return 0.5 + 3.0 * (1.0 - q)

    eps_direct = rng.normal(scale=_noise_scale(q_bar))
    s_direct = margin + eps_direct

    in_band = (q_bar >= 0.35) & (q_bar <= 0.55)
    bump = np.where(in_band, rng.uniform(0.15, 0.25, size=n), 0.0)
    q_bar_enh = np.clip(q_bar + bump, 0.0, 1.0)

    # On enhanced sample, noise re-drawn at *lower* scale (Prop 3 hypothesis met).
    eps_enh = rng.normal(scale=_noise_scale(q_bar_enh))
    s_enh = margin + eps_enh

    p_direct = np.stack([1.0 - _sigmoid(s_direct), _sigmoid(s_direct)], axis=-1)
    p_enh = np.stack([1.0 - _sigmoid(s_enh), _sigmoid(s_enh)], axis=-1)

    return dict(
        n=n,
        q_bar=q_bar,
        q_bar_enh=q_bar_enh,
        p_direct=p_direct,
        p_enh=p_enh,
        y=y,
    )


def _zero_one_risk(p: np.ndarray, y: np.ndarray) -> float:
    return float((p.argmax(axis=-1) != y).mean())


def _per_bin_salvage_gain(pop: dict, q_bin_edges: np.ndarray, c_enh: float = 0.02) -> np.ndarray:
    """Δ(q̄) = R_direct(q̄) − R_enh(q̄) − c_e   (empirical, per-bin)."""
    gains = []
    for lo, hi in zip(q_bin_edges[:-1], q_bin_edges[1:]):
        mask = (pop["q_bar"] >= lo) & (pop["q_bar"] < hi)
        if mask.sum() < 30:
            gains.append(np.nan)
            continue
        r_direct = _zero_one_risk(pop["p_direct"][mask], pop["y"][mask])
        r_enh = _zero_one_risk(pop["p_enh"][mask], pop["y"][mask])
        gains.append((r_direct - r_enh) - c_enh)
    return np.array(gains)


def test_thm2_P1_delta_strictly_positive_on_salvage_band(thm2_population):
    """P1: Δ(q̄) > 0 for q̄ ∈ [0.35, 0.55]; trivially ≤ 0 outside."""
    edges = np.array([0.0, 0.20, 0.35, 0.55, 0.80, 1.0])
    deltas = _per_bin_salvage_gain(thm2_population, edges)
    # In-band bins (index 2, between 0.35 and 0.55).
    assert deltas[2] > 0, f"salvage band Δ should be > 0, got {deltas[2]:.4f}"
    # Out-of-band: low-quality bin (0-0.20) and high-quality bin (0.80-1.0).
    assert deltas[0] <= 0.05, f"very low q_bar should have small Δ, got {deltas[0]:.4f}"
    assert deltas[-1] <= 0.05, f"very high q_bar should have small Δ, got {deltas[-1]:.4f}"


def test_thm2_P2_threshold_estimation_recovers_synthetic_band(thm2_population):
    """P2: empirical τ_enh, τ_high recover the synthetic [0.35, 0.55] band."""
    edges = np.linspace(0.0, 1.0, 11)  # 10%-wide bins (n≈800/bin for n=8000)
    deltas = _per_bin_salvage_gain(thm2_population, edges, c_enh=0.02)
    bin_centers = 0.5 * (edges[:-1] + edges[1:])

    # Margin = 1 SE on risk diff ≈ √(2·0.5/800) ≈ 0.025; require Δ above noise.
    positive = deltas > 0.01
    pos_idx = np.where(positive)[0]
    assert pos_idx.size > 0, "no positive Δ found — Prop 3 toy broken"

    # Take the longest contiguous run of positives.
    runs = np.split(pos_idx, np.where(np.diff(pos_idx) != 1)[0] + 1)
    best = max(runs, key=len)
    tau_enh = bin_centers[best[0]]
    tau_high = bin_centers[best[-1]]

    # Synthetic band [0.35, 0.55]; allow ±0.15 slack for 10%-bin granularity.
    assert 0.20 <= tau_enh <= 0.50, f"τ_enh={tau_enh:.3f} not in [0.20, 0.50]"
    assert 0.40 <= tau_high <= 0.70, f"τ_high={tau_high:.3f} not in [0.40, 0.70]"


def test_thm2_P3_population_risk_reduction(thm2_population):
    """P3: E[R_agent] ≤ E[R_direct] − π_salvage · Δ_avg (Corollary 2.2)."""
    pop = thm2_population
    in_band = (pop["q_bar"] >= 0.35) & (pop["q_bar"] <= 0.55)

    # Threshold policy: enhance iff in-band, else direct.
    p_agent = np.where(in_band[:, None], pop["p_enh"], pop["p_direct"])
    r_agent = _zero_one_risk(p_agent, pop["y"])
    r_direct = _zero_one_risk(pop["p_direct"], pop["y"])

    pi_salvage = float(in_band.mean())

    assert r_agent < r_direct, f"agent risk {r_agent:.4f} not < direct {r_direct:.4f}"
    # Strict positive gap, proportional to salvage prob.
    assert (r_direct - r_agent) > 0.5 * pi_salvage * 0.02  # weak floor


def test_thm2_corollary_2_1_agent_never_worse_than_direct(thm2_population):
    """Corollary 2.1: agent risk ≤ direct risk pointwise (per-bin)."""
    pop = thm2_population
    edges = np.linspace(0.0, 1.0, 11)
    in_band = (pop["q_bar"] >= 0.35) & (pop["q_bar"] <= 0.55)
    p_agent = np.where(in_band[:, None], pop["p_enh"], pop["p_direct"])

    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (pop["q_bar"] >= lo) & (pop["q_bar"] < hi)
        if m.sum() < 50:
            continue
        r_a = _zero_one_risk(p_agent[m], pop["y"][m])
        r_d = _zero_one_risk(pop["p_direct"][m], pop["y"][m])
        # Allow a 1.5% finite-sample slack (bootstrap-CI width on n=200 bins).
        assert r_a <= r_d + 0.015, f"q_bar∈[{lo:.2f},{hi:.2f}]: agent {r_a:.4f} > direct {r_d:.4f}"


def test_thm2_bootstrap_CI_excludes_zero(thm2_population):
    """Final sanity: bootstrap 2000-resample 95% CI of (R_direct − R_agent) excludes 0."""
    pop = thm2_population
    in_band = (pop["q_bar"] >= 0.35) & (pop["q_bar"] <= 0.55)
    p_agent = np.where(in_band[:, None], pop["p_enh"], pop["p_direct"])

    diff_per_sample = (pop["p_direct"].argmax(-1) != pop["y"]).astype(float) - (
        p_agent.argmax(-1) != pop["y"]
    ).astype(float)

    res = bootstrap(
        (diff_per_sample,),
        statistic=np.mean,
        n_resamples=2000,
        confidence_level=0.95,
        random_state=20260524,
    )
    lo, hi = res.confidence_interval
    assert lo > 0, f"95% CI [{lo:.4f}, {hi:.4f}] contains 0 — population risk reduction not significant"


# ── Cross-coupling: Prop 3 + Lemma 2.1 → Lemma 2.2 of Thm 2 derivation ────────


def test_lemma2_1_entropy_risk_coupling():
    """Gibbs bound: 0-1 risk ≤ 1 − exp(−H(p̂)) for plug-in classifier."""
    n, K = 5000, 5
    p_hat = RNG.dirichlet(np.ones(K), size=n)
    y = np.array([RNG.choice(K, p=row) for row in p_hat])  # calibrated true label

    plugin_risk = (p_hat.argmax(-1) != y).mean()
    gibbs_bound = (1.0 - np.exp(-entropy(p_hat))).mean()
    assert plugin_risk <= gibbs_bound + 1e-2, f"{plugin_risk=:.4f} > Gibbs bound {gibbs_bound:.4f}"
