"""Agent 工具链 + 编排逻辑单元测试。"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.tools import quality_assess, extract_features, triage, QUALITY_DIMS
from agent.question_bank import get_retake_question, get_clinical_question, RETAKE_QUESTIONS
from agent.orchestrator import ReActAgent, AgentState

# 测试一律用规则引擎（跳过 LLM 加载，避免 Qwen3 未下载完时挂起）
def make_agent() -> ReActAgent:
    return ReActAgent(use_llm=False)


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def rand_img():
    rng = np.random.default_rng(42)
    return rng.integers(0, 255, (224, 224, 3), dtype=np.uint8)


@pytest.fixture(scope="module")
def dark_img():
    return np.zeros((224, 224, 3), dtype=np.uint8)


# ── quality_assess ────────────────────────────────────────────────────────────
class TestQualityAssess:
    def test_returns_five_dims(self, rand_img):
        result = quality_assess(rand_img)
        assert set(result.scores.keys()) == set(QUALITY_DIMS)

    def test_scores_in_unit_interval(self, rand_img):
        result = quality_assess(rand_img)
        for v in result.scores.values():
            assert 0.0 <= v <= 1.0

    def test_dark_image_has_issues(self, dark_img):
        result = quality_assess(dark_img)
        assert len(result.issues) > 0
        assert not result.is_acceptable

    def test_overall_is_mean(self, rand_img):
        result = quality_assess(rand_img)
        expected = np.mean(list(result.scores.values()))
        assert abs(result.overall - expected) < 1e-4


# ── extract_features ──────────────────────────────────────────────────────────
class TestExtractFeatures:
    def test_shapes(self, rand_img):
        feats = extract_features(rand_img)
        assert feats.abcd.shape == (4,)
        assert feats.q_vector.shape == (5,)
        assert feats.efnet_feat.shape == (1280,)

    def test_abcd_in_unit_interval(self, rand_img):
        feats = extract_features(rand_img)
        assert np.all(feats.abcd >= 0.0) and np.all(feats.abcd <= 1.0)

    def test_q_vector_in_unit_interval(self, rand_img):
        feats = extract_features(rand_img)
        assert np.all(feats.q_vector >= 0.0) and np.all(feats.q_vector <= 1.0)

    def test_mask_is_bool(self, rand_img):
        feats = extract_features(rand_img)
        assert feats.mask.dtype == bool


# ── triage ────────────────────────────────────────────────────────────────────
class TestTriage:
    def test_prob_in_unit_interval(self, rand_img):
        feats = extract_features(rand_img)
        result = triage(feats, n_mc=5)
        assert 0.0 <= result.malignancy_prob <= 1.0

    def test_urgency_valid(self, rand_img):
        feats = extract_features(rand_img)
        result = triage(feats, n_mc=5)
        assert result.urgency in ("low", "medium", "high")

    def test_uncertainty_non_negative(self, rand_img):
        feats = extract_features(rand_img)
        result = triage(feats, n_mc=5)
        assert result.uncertainty >= 0.0

    def test_disclaimer_present(self, rand_img):
        feats = extract_features(rand_img)
        result = triage(feats, n_mc=5)
        assert len(result.disclaimer) > 0


# ── question_bank ─────────────────────────────────────────────────────────────
class TestQuestionBank:
    def test_all_issues_have_questions(self):
        for issue in QUALITY_DIMS:
            q = get_retake_question(issue)
            assert isinstance(q, str) and len(q) > 0

    def test_unknown_issue_has_fallback(self):
        q = get_retake_question("unknown_issue_xyz")
        assert "unknown_issue_xyz" in q

    def test_clinical_questions_rotate(self):
        asked: list[str] = []
        seen = set()
        for _ in range(10):
            q = get_clinical_question(asked)
            if q is None:
                break
            asked.append(q)
            seen.add(q)
        assert len(seen) > 0

    def test_clinical_returns_none_when_exhausted(self):
        from agent.question_bank import CLINICAL_QUESTIONS
        q = get_clinical_question(list(CLINICAL_QUESTIONS))
        assert q is None


# ── orchestrator ──────────────────────────────────────────────────────────────
class TestOrchestrator:
    def test_high_quality_completes_without_asking(self, rand_img):
        agent = make_agent()
        state = agent.start(rand_img)
        # rand_img has good quality → should complete directly
        assert state.done
        assert not state.waiting_for_user
        assert state.triage_result is not None

    def test_dark_image_triggers_guidance(self, dark_img):
        agent = make_agent()
        state = agent.start(dark_img)
        assert state.waiting_for_user
        assert state.retake_count == 1
        assert len(state.pending_question) > 0

    def test_max_retake_rounds_enforced(self, dark_img):
        agent = make_agent()
        state = agent.start(dark_img)
        # Keep feeding the same dark image
        for _ in range(5):
            if state.done:
                break
            if state.waiting_for_user:
                state = agent.continue_with_new_image(state, dark_img)
        assert state.done
        assert state.retake_count <= 3

    def test_continue_with_text(self, rand_img):
        agent = make_agent()
        state = agent.start(rand_img)
        if state.waiting_for_user:
            state = agent.continue_with_text(state, "没有什么变化")
        assert state.done or state.waiting_for_user
