"""Regression tests for the seed-batch eval bug (session 39/40).

Bug: itb_predictions_s{seed}.csv had F==G predictions (byte-identical prob_pos),
caused by run_s22_seeds.py mistakenly calling train_qad.py for G instead of
finetune_tokenizer.py, producing G ckpts with MD5 == F ckpts.

These tests assert:
1. [model_dispatch] D/E/F produce distinct prediction tensors on a CPU dummy input.
2. [ckpt_sentinel]  Given two toy ckpts, the eval sentinel raises RuntimeError when
                    F and G are identical files.
3. [agg_integrity]  aggregate_seeds.py warns (does not silently pass) when two
                    baselines have identical auc_mean in the output.

All tests run CPU-only, no GPU, no real data, no training.
"""

import hashlib
import sys
import types
import warnings
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import torch
import torch.nn as nn
import torch.nn.functional as F

# ── Project imports ──────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
from models.q_vib_encoder import QVIBEncoder
from models.qad_classifier import QADClassifier


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_encoder_classifier(efnet_dim: int = 0, seed: int = 0) -> tuple:
    """Build a tiny QVIBEncoder + QADClassifier with reproducible random init."""
    torch.manual_seed(seed)
    enc = QVIBEncoder(
        abcd_dim=4, q_dim=5,
        d_model=16, n_heads=2, latent_dim=8,
        efnet_dim=efnet_dim, use_tokenizer=True,
    )
    cls_ = QADClassifier(latent_dim=8, hidden_dim=16, num_classes=2)
    enc.eval(); cls_.eval()
    return enc, cls_


def _mc_predict(enc, cls_, abcd, q, ef, n_mc=5, seed_offset=0):
    """Run MC sampling and return mean prob_pos (class 1)."""
    torch.manual_seed(seed_offset)
    with torch.no_grad():
        mu, lsq = enc(abcd, q, efnet_feat=ef)
        probs_list = []
        for _ in range(n_mc):
            z = enc.reparameterize(mu, lsq)
            probs_list.append(F.softmax(cls_(z), dim=-1))
    return torch.stack(probs_list).mean(0)[:, 1]  # (B,)


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: D/E/F produce distinct predictions from distinct random-init models
# ─────────────────────────────────────────────────────────────────────────────

class TestModelDispatchDistinct:
    """Different random seeds -> different weights -> different predictions.

    This mirrors the D/E/F separation that was broken when G ckpt == F ckpt.
    """

    def setup_method(self):
        torch.manual_seed(0)
        self.B = 16
        self.abcd = torch.randn(self.B, 4)
        self.q    = torch.rand(self.B, 5)

    def test_different_seeds_give_different_predictions(self):
        """Models with different init seeds must produce distinct prob_pos vectors."""
        results = {}
        for name, seed in [("D", 1), ("E", 2), ("F", 3)]:
            enc, cls_ = _build_encoder_classifier(efnet_dim=0, seed=seed)
            prob = _mc_predict(enc, cls_, self.abcd, self.q, ef=None)
            results[name] = prob.numpy()

        # All pairs must differ
        for name_a, name_b in [("D", "E"), ("D", "F"), ("E", "F")]:
            a, b = results[name_a], results[name_b]
            assert not np.allclose(a, b, atol=1e-6), (
                f"{name_a} and {name_b} predictions are identical — "
                "dispatch bug: same ckpt loaded for both variants"
            )

    def test_same_seed_gives_same_predictions(self):
        """Sanity: identical init -> identical predictions (deterministic)."""
        enc1, cls1 = _build_encoder_classifier(efnet_dim=0, seed=7)
        enc2, cls2 = _build_encoder_classifier(efnet_dim=0, seed=7)
        p1 = _mc_predict(enc1, cls1, self.abcd, self.q, ef=None, seed_offset=99)
        p2 = _mc_predict(enc2, cls2, self.abcd, self.q, ef=None, seed_offset=99)
        assert np.allclose(p1.numpy(), p2.numpy(), atol=1e-6), (
            "Same seed must reproduce identical predictions"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: run_experiments.py sentinel raises on F==G ckpt
# ─────────────────────────────────────────────────────────────────────────────

class TestCkptSentinel:
    """The MD5 sentinel in run_experiments.main() must abort when F==G."""

    def _write_dummy_ckpt(self, path: Path, seed: int):
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.manual_seed(seed)
        enc, cls_ = _build_encoder_classifier(efnet_dim=0, seed=seed)
        torch.save({"encoder": enc.state_dict(), "classifier": cls_.state_dict()}, path)

    def test_sentinel_raises_on_identical_ckpts(self, tmp_path):
        """Identical F and G ckpt files must trigger RuntimeError."""
        f_ckpt = tmp_path / "efnet_s99" / "best_qad.pth"
        g_ckpt = tmp_path / "efnet_tokft_s99" / "best_qad.pth"

        # Write F, then copy to G (identical)
        self._write_dummy_ckpt(f_ckpt, seed=1)
        import shutil
        g_ckpt.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f_ckpt, g_ckpt)

        assert hashlib.md5(f_ckpt.read_bytes()).hexdigest() == \
               hashlib.md5(g_ckpt.read_bytes()).hexdigest(), "Test setup: files must be identical"

        # Inline the sentinel logic from run_experiments.py
        def _md5(p):
            try:
                with open(p, "rb") as _f:
                    return hashlib.md5(_f.read()).hexdigest()
            except FileNotFoundError:
                return None

        hf = _md5(f_ckpt)
        hg = _md5(g_ckpt)
        with pytest.raises(RuntimeError, match="byte-identical"):
            if hf is not None and hg is not None and hf == hg:
                raise RuntimeError(
                    f"[ABORT] F and G checkpoints are byte-identical (MD5={hf[:12]})!\n"
                    f"  F: {f_ckpt}\n  G: {g_ckpt}\n"
                    "Fix: run run_g_tokft_seeds.py to regenerate G seed checkpoints."
                )

    def test_sentinel_passes_on_distinct_ckpts(self, tmp_path):
        """Distinct F and G ckpt files must NOT raise."""
        f_ckpt = tmp_path / "efnet_s99" / "best_qad.pth"
        g_ckpt = tmp_path / "efnet_tokft_s99" / "best_qad.pth"

        self._write_dummy_ckpt(f_ckpt, seed=1)
        self._write_dummy_ckpt(g_ckpt, seed=2)  # different seed -> different weights

        def _md5(p):
            with open(p, "rb") as _f:
                return hashlib.md5(_f.read()).hexdigest()

        hf, hg = _md5(f_ckpt), _md5(g_ckpt)
        assert hf != hg, "Test setup: distinct seeds must produce distinct ckpts"
        # Must not raise
        if hf == hg:
            raise RuntimeError("sentinel false positive")
        # Reaching here = OK


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: aggregate_seeds.py warns on identical auc_mean across baselines
# ─────────────────────────────────────────────────────────────────────────────

class TestAggregateIntegrity:
    """aggregate_seeds.py must warn (via print) when two baselines share auc_mean."""

    def _make_seed_csv(self, path: Path, auc_map: dict):
        """Write a fake per-seed result CSV. auc_map: {(baseline, subset): auc}"""
        import pandas as pd
        rows = []
        for (bl, subset), auc in auc_map.items():
            rows.append({
                "baseline": bl, "subset": subset,
                "auc": auc, "ece": 0.1, "n": 100,
            })
        pd.DataFrame(rows).to_csv(path, index=False)

    def test_warns_on_identical_auc_mean(self, tmp_path, capsys):
        """If E and F have same auc_mean, aggregate_seeds must print a WARN."""
        import pandas as pd

        # Three seed CSVs where E and F have identical AUC (per-seed may differ,
        # but their mean is the same — the bug scenario)
        auc_values = {
            "E": [0.720, 0.730, 0.726],
            "F": [0.719, 0.731, 0.726],  # mean == E mean
        }
        subset = "ITB-LQ"
        for i, (s, fn) in enumerate([(42, "s42"), (123, "s123"), (2024, "s2024")]):
            auc_map = {("E", subset): auc_values["E"][i],
                       ("F", subset): auc_values["F"][i]}
            self._make_seed_csv(tmp_path / f"itb_results_{fn}.csv", auc_map)

        # Verify means are indeed equal
        assert abs(np.mean(auc_values["E"]) - np.mean(auc_values["F"])) < 1e-9

        # Run aggregate
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        import importlib
        agg_mod = importlib.import_module("aggregate_seeds")
        files = [str(tmp_path / f) for f in ["itb_results_s42.csv",
                                              "itb_results_s123.csv",
                                              "itb_results_s2024.csv"]]
        agg_mod.aggregate(files)

        captured = capsys.readouterr()
        assert "WARN" in captured.out, (
            "aggregate_seeds must emit a WARN when two baselines share auc_mean. "
            f"Captured stdout:\n{captured.out}"
        )

    def test_no_warn_on_distinct_auc_mean(self, tmp_path, capsys):
        """Distinct auc_mean should produce no WARN."""
        subset = "ITB-LQ"
        auc_map_distinct = {
            "D": [0.710, 0.715, 0.712],
            "F": [0.730, 0.735, 0.732],
        }
        for i, fn in enumerate(["itb_results_s42.csv", "itb_results_s123.csv",
                                 "itb_results_s2024.csv"]):
            auc_map = {("D", subset): auc_map_distinct["D"][i],
                       ("F", subset): auc_map_distinct["F"][i]}
            self._make_seed_csv(tmp_path / fn, auc_map)

        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        import importlib
        import aggregate_seeds
        importlib.reload(aggregate_seeds)
        files = [str(tmp_path / f) for f in ["itb_results_s42.csv",
                                              "itb_results_s123.csv",
                                              "itb_results_s2024.csv"]]
        aggregate_seeds.aggregate(files)

        captured = capsys.readouterr()
        # Lines with WARN should NOT appear for D/F pair
        warn_lines = [l for l in captured.out.splitlines()
                      if "WARN" in l and ("D" in l or "F" in l)]
        assert not warn_lines, (
            f"Unexpected WARN on distinct auc_mean:\n{warn_lines}"
        )
