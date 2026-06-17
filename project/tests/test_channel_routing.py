"""4 通道路由单元测试 — C2.1 验收判据（ICLR 唯一论文）。

测试目标：
  mock per-input q̄（overall quality scalar）喂 4 个档位，
  断言 route_by_quality() 和 _RuleBasedFallback 路由到正确通道。

阈值真源：project/results/agent_vs_direct_risk.csv
  TAU_SEVERE   = 0.25  (severe band 上界)
  TAU_MODERATE = 0.35  (moderate band 下界)
  TAU_HIGH     = 0.50  (moderate band 上界 / high band 下界)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.orchestrator import (
    ChannelDecision,
    TAU_HIGH,
    TAU_MODERATE,
    TAU_SEVERE,
    _RuleBasedFallback,
    route_by_quality,
)


# ── 辅助：构造一个假的 QualityResult，overall=q_bar ─────────────────────────
def _make_quality_result(q_bar: float):
    """构造 mock QualityResult，overall=q_bar，不依赖真实模型。"""
    from agent.tools import QualityResult
    scores = {dim: q_bar for dim in ["sharpness", "brightness", "completeness", "color_temp", "contrast"]}
    issues = [] if q_bar >= 0.5 else ["sharpness"]
    return QualityResult(
        scores=scores,
        overall=q_bar,
        issues=issues,
        is_acceptable=(q_bar >= 0.5),
    )


def _make_triage_result():
    """构造 mock TriageResult，不依赖真实模型。"""
    from agent.tools import TriageResult
    return TriageResult(
        malignancy_prob=0.3,
        uncertainty=0.1,
        abcd_values={"asymmetry": 0.2, "border": 0.3, "color": 0.4, "diameter": 0.1},
        recommendation="建议定期观察",
        urgency="low",
        disclaimer="仅供参考",
    )


# ── 1. route_by_quality 纯函数 4 档位测试 ────────────────────────────────────
class TestRouteByQuality:
    """route_by_quality(q_bar) 边界值 + 典型值测试。"""

    # 1a. q̄ ≥ TAU_HIGH → direct_diagnosis
    @pytest.mark.parametrize("q_bar", [TAU_HIGH, TAU_HIGH + 0.01, 0.75, 1.0])
    def test_direct_diagnosis(self, q_bar):
        assert route_by_quality(q_bar) == ChannelDecision.DIRECT_DIAGNOSIS

    # 1b. TAU_MODERATE ≤ q̄ < TAU_HIGH → cautioned_diagnosis
    @pytest.mark.parametrize("q_bar", [TAU_MODERATE, 0.40, TAU_HIGH - 0.001])
    def test_cautioned_diagnosis(self, q_bar):
        assert route_by_quality(q_bar) == ChannelDecision.CAUTIONED_DIAGNOSIS

    # 1c. TAU_SEVERE ≤ q̄ < TAU_MODERATE → enhance_then_diagnose
    @pytest.mark.parametrize("q_bar", [TAU_SEVERE, 0.28, TAU_MODERATE - 0.001])
    def test_enhance_then_diagnose(self, q_bar):
        assert route_by_quality(q_bar) == ChannelDecision.ENHANCE_THEN_DIAGNOSE

    # 1d. q̄ < TAU_SEVERE → query_for_retake
    @pytest.mark.parametrize("q_bar", [0.0, 0.10, TAU_SEVERE - 0.001])
    def test_query_for_retake(self, q_bar):
        assert route_by_quality(q_bar) == ChannelDecision.QUERY_FOR_RETAKE

    # 1e. 确认阈值边界值精确吻合 csv band（关键回归）
    def test_boundary_values_match_csv(self):
        """阈值边界吻合 agent_vs_direct_risk.csv band 定义（非臆想）。"""
        assert TAU_SEVERE   == 0.25
        assert TAU_MODERATE == 0.35
        assert TAU_HIGH     == 0.50
        # 边界归属：TAU_SEVERE 属于 enhance_then_diagnose（≥ TAU_SEVERE）
        assert route_by_quality(0.25) == ChannelDecision.ENHANCE_THEN_DIAGNOSE
        # TAU_MODERATE 属于 cautioned_diagnosis（≥ TAU_MODERATE）
        assert route_by_quality(0.35) == ChannelDecision.CAUTIONED_DIAGNOSIS
        # TAU_HIGH 属于 direct_diagnosis（≥ TAU_HIGH）
        assert route_by_quality(0.50) == ChannelDecision.DIRECT_DIAGNOSIS


# ── 2. _RuleBasedFallback 4 通道路由集成测试（mock tools）─────────────────────
class TestRuleBasedFallbackRouting:
    """_RuleBasedFallback.start() 对 4 个 q̄ 档位路由到正确 ChannelDecision。

    Mock 掉 quality_assess / extract_features / triage，不依赖真实模型/ckpt。
    """

    def _run_fallback(self, q_bar: float) -> "AgentState":
        """Mock 整个工具链，喂指定 q_bar，返回最终 AgentState。"""
        from agent.orchestrator import AgentState

        fake_quality = _make_quality_result(q_bar)
        fake_triage = _make_triage_result()
        fake_feats = MagicMock()

        state = AgentState(image=np.zeros((224, 224, 3), dtype=np.uint8))

        with (
            patch("agent.orchestrator.quality_assess", return_value=fake_quality),
            patch("agent.orchestrator.extract_features", return_value=fake_feats),
            patch("agent.orchestrator.triage", return_value=fake_triage),
            patch("agent.orchestrator._enhance_with_stage2", return_value=None),
        ):
            fb = _RuleBasedFallback()
            return fb.start(state)

    # 2a. q̄ = 0.75 → direct_diagnosis，done=True，无追问
    def test_high_quality_direct(self):
        state = self._run_fallback(q_bar=0.75)
        assert state.channel_decision == ChannelDecision.DIRECT_DIAGNOSIS
        assert state.done is True
        assert state.waiting_for_user is False

    # 2b. q̄ = 0.42 → cautioned_diagnosis，done=True，recommendation 含不确定性标注
    def test_medium_quality_cautioned(self):
        state = self._run_fallback(q_bar=0.42)
        assert state.channel_decision == ChannelDecision.CAUTIONED_DIAGNOSIS
        assert state.done is True
        assert state.triage_result is not None
        assert "不确定性" in state.triage_result.recommendation

    # 2c. q̄ = 0.28 → enhance_then_diagnose，done=True（ckpt absent → fallback 到原图）
    def test_low_medium_enhance_then_diagnose(self):
        state = self._run_fallback(q_bar=0.28)
        assert state.channel_decision == ChannelDecision.ENHANCE_THEN_DIAGNOSE
        assert state.done is True
        # enhanced_image 为 None（mock ckpt 不存在），但 triage 仍运行
        assert state.triage_result is not None

    # 2d. q̄ = 0.10 → query_for_retake，waiting_for_user=True，不诊断
    def test_very_low_quality_retake(self):
        state = self._run_fallback(q_bar=0.10)
        assert state.channel_decision == ChannelDecision.QUERY_FOR_RETAKE
        assert state.waiting_for_user is True
        assert state.done is False
        assert len(state.pending_question) > 0
        # query_for_retake 通道：不应有诊断结果
        assert state.triage_result is None


# ── 3. query_for_retake 通道最大追问次数兜底测试 ──────────────────────────────
class TestRetakeFallbackAfterMaxRounds:
    """超过 MAX_RETAKE_ROUNDS 后 query_for_retake 通道降级为 cautioned_diagnosis。"""

    def test_max_retake_falls_back_to_cautioned(self):
        from agent.orchestrator import AgentState, MAX_RETAKE_ROUNDS

        fake_quality = _make_quality_result(0.10)  # severe → query_for_retake
        fake_triage = _make_triage_result()
        fake_feats = MagicMock()

        state = AgentState(
            image=np.zeros((224, 224, 3), dtype=np.uint8),
            retake_count=MAX_RETAKE_ROUNDS,   # 已达上限
        )

        with (
            patch("agent.orchestrator.quality_assess", return_value=fake_quality),
            patch("agent.orchestrator.extract_features", return_value=fake_feats),
            patch("agent.orchestrator.triage", return_value=fake_triage),
            patch("agent.orchestrator._enhance_with_stage2", return_value=None),
        ):
            fb = _RuleBasedFallback()
            result_state = fb.start(state)

        # 超限后应兜底 cautioned_diagnosis，done=True
        assert result_state.done is True
        assert result_state.channel_decision == ChannelDecision.CAUTIONED_DIAGNOSIS


# ── 4. ChannelDecision 枚举值字符串确认（STORY C2 措辞对齐）────────────────────
class TestChannelDecisionEnum:
    """确认枚举 value 字符串与 STORY/ACCEPTANCE 措辞一致（写 tex/报告用）。"""

    def test_enum_values(self):
        assert ChannelDecision.DIRECT_DIAGNOSIS.value      == "direct_diagnosis"
        assert ChannelDecision.CAUTIONED_DIAGNOSIS.value   == "cautioned_diagnosis"
        assert ChannelDecision.ENHANCE_THEN_DIAGNOSE.value == "enhance_then_diagnose"
        assert ChannelDecision.QUERY_FOR_RETAKE.value      == "query_for_retake"
