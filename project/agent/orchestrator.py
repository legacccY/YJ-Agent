"""ReAct Agent 编排逻辑：Qwen3-4B 4-bit 量化驱动工具调用循环。

4 通道决策路由（per-input quality scalar q̄，基于 agent_vs_direct_risk.csv band 边界）：
  q̄ ≥ 0.50  → direct_diagnosis    （直接诊断）
  0.35 ≤ q̄ < 0.50 → cautioned_diagnosis（谨慎诊断，附不确定性标注）
  0.25 ≤ q̄ < 0.35 → enhance_then_diagnose（过 VisiEnhance Stage2 增强后诊断）
  q̄ < 0.25  → query_for_retake    （转介重拍，不诊断）

阈值真源：project/results/agent_vs_direct_risk.csv
  severe band  tau_lo=0.25（severe 上界）
  moderate band tau_lo=0.35, tau_hi=0.50
LLM 不可用时自动回退到规则引擎（_RuleBasedFallback），行为与 LLM 路由一致。
"""

from __future__ import annotations

import enum
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import torch

PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from agent.tools import (
    QualityResult, FeaturesResult, TriageResult,
    quality_assess, extract_features, triage,
)
from agent.question_bank import get_retake_question

MAX_RETAKE_ROUNDS = 3

# ── 4-Channel routing thresholds ─────────────────────────────────────────────
# Source: project/results/agent_vs_direct_risk.csv band boundaries
# severe band: q̄ < TAU_SEVERE  → query_for_retake
# moderate band: TAU_SEVERE ≤ q̄ < TAU_HIGH → enhance_then_diagnose (lower half)
#                TAU_MODERATE ≤ q̄ < TAU_HIGH → cautioned_diagnosis (upper half)
# high band:  q̄ ≥ TAU_HIGH   → direct_diagnosis
TAU_SEVERE   = 0.25   # severe band upper boundary  (csv: tau_lo=0.25 for severe)
TAU_MODERATE = 0.35   # moderate band lower boundary (csv: tau_lo=0.35 for moderate)
TAU_HIGH     = 0.50   # high band lower boundary     (csv: tau_hi=0.50 for moderate)

# VisiEnhance Stage 2 checkpoint (enhance_then_diagnose channel)
# Source: project/DATA_INVENTORY.md — stage2 ckpt path
# TODO: 未找到已训练的 Stage2 ckpt（DATA_INVENTORY 标注 "待训"）；
#       researcher 确认实际 ckpt 路径后替换此占位符。
VISIENHANCE_S2_CKPT = Path("D:/YJ-Agent/checkpoints/visienhance/stage2/best_visienhance.pth")


class ChannelDecision(enum.Enum):
    """4 通道决策标签（对应 C2.1 验收判据）。"""
    DIRECT_DIAGNOSIS      = "direct_diagnosis"        # q̄ ≥ TAU_HIGH
    CAUTIONED_DIAGNOSIS   = "cautioned_diagnosis"     # TAU_MODERATE ≤ q̄ < TAU_HIGH
    ENHANCE_THEN_DIAGNOSE = "enhance_then_diagnose"   # TAU_SEVERE ≤ q̄ < TAU_MODERATE
    QUERY_FOR_RETAKE      = "query_for_retake"        # q̄ < TAU_SEVERE


def route_by_quality(q_bar: float) -> ChannelDecision:
    """根据 per-input quality scalar q̄ 路由到 4 通道之一。

    Args:
        q_bar: overall quality score in [0, 1] (均值，来自 VisiScore-Net 5 维输出均值).
    Returns:
        ChannelDecision 枚举值。
    阈值来源：agent_vs_direct_risk.csv band 边界，不臆想，不另拍。
    """
    if q_bar >= TAU_HIGH:
        return ChannelDecision.DIRECT_DIAGNOSIS
    elif q_bar >= TAU_MODERATE:
        return ChannelDecision.CAUTIONED_DIAGNOSIS
    elif q_bar >= TAU_SEVERE:
        return ChannelDecision.ENHANCE_THEN_DIAGNOSE
    else:
        return ChannelDecision.QUERY_FOR_RETAKE

# ── Tool schema (Qwen3 function-calling format) ───────────────────────────────
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "quality_assess",
            "description": "评估当前上传皮肤图片的拍摄质量（清晰度/亮度/完整性等），返回各维度得分和 overall_score",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "enhance_image",
            "description": (
                "对图片进行诊断保持增强（VisiEnhance Stage2 DP-Loss 微调），"
                "仅在 overall_score ∈ [0.25, 0.35) 时调用（enhance_then_diagnose 通道）。"
                "增强后自动触发 analyze_lesion。"
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_lesion",
            "description": (
                "分析皮损 ABCD 临床特征并评估恶性风险，"
                "仅在 quality_assess 或 enhance_image 完成后调用。"
                "overall_score 0.35-0.50 时须设 cautioned=true（谨慎诊断通道）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cautioned": {
                        "type": "boolean",
                        "description": "true = 谨慎诊断通道（附不确定性标注），false = 直接诊断",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": (
                "向用户提问，引导其重新拍摄图片（query_for_retake 通道）或提供临床背景。"
                "仅在 overall_score < 0.25 时触发重拍请求。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "要向用户提问的具体问题（中文，口语化，100 字以内）",
                    }
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "final_answer",
            "description": "给出最终分诊建议并结束对话",
            "parameters": {
                "type": "object",
                "properties": {
                    "recommendation": {
                        "type": "string",
                        "description": "给用户的分诊建议（中文，包含就医紧迫度和注意事项）",
                    },
                    "urgency": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "就医紧迫程度",
                    },
                },
                "required": ["recommendation", "urgency"],
            },
        },
    },
]

SYSTEM_PROMPT = """你是 VisiSkin Agent，专门分析皮肤病变图片的 AI 助手。

【核心规则】每次回复必须且只能是一个工具调用，禁止输出任何纯文本解释。

4 通道决策路由（按 quality_assess 返回的 overall_score q̄ 严格路由）：
步骤1：收到图片 → 调用 quality_assess()
步骤2（按 q̄ 值路由，4 选 1）：
  q̄ ≥ 0.50  → 调用 analyze_lesion()              【direct_diagnosis 通道】
  0.35 ≤ q̄ < 0.50 → 调用 analyze_lesion()（设 cautioned=true）【cautioned_diagnosis 通道】
  0.25 ≤ q̄ < 0.35 → 调用 enhance_image()          【enhance_then_diagnose 通道】
  q̄ < 0.25  → 调用 ask_user()（重拍请求）          【query_for_retake 通道】
步骤3：analyze_lesion() / enhance_image() 完成后 → 调用 final_answer()

禁止跳过步骤，禁止输出纯文字，禁止用「确诊」「诊断为」等词。
Agent 决定何时诊断/增强/追问，自身不出具诊断。"""


# ── Agent state ───────────────────────────────────────────────────────────────
@dataclass
class AgentState:
    image: Optional[np.ndarray] = None
    retake_count: int = 0
    quality_result: Optional[QualityResult] = None
    features_result: Optional[FeaturesResult] = None
    triage_result: Optional[TriageResult] = None
    channel_decision: Optional[ChannelDecision] = None   # 4 通道路由结果
    enhanced_image: Optional[np.ndarray] = None          # enhance_then_diagnose 通道产物
    clinical_answers: list[str] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    done: bool = False
    waiting_for_user: bool = False
    pending_question: str = ""


# ── ReAct Agent (Qwen3-8B) ────────────────────────────────────────────────────
class ReActAgent:
    """Qwen3-4B 4-bit 量化驱动的 ReAct Agent。LLM 不可用时回退到规则引擎。"""

    def __init__(self, model_name: str = "Qwen/Qwen3-4B", use_llm: bool = True):
        self.model_name = model_name
        self.use_llm = use_llm
        self._model = None
        self._tokenizer = None
        self._fallback = _RuleBasedFallback()
        self._llm_checked = False   # 只尝试一次加载，避免每次 start() 都打印警告

    # ── LLM loading ───────────────────────────────────────────────────────────
    def _load_model(self) -> bool:
        """尝试加载 Qwen3-8B 4-bit，失败则返回 False（只尝试一次）。"""
        if not self.use_llm:
            return False
        if self._llm_checked:
            return self._model is not None
        self._llm_checked = True
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
            import bitsandbytes  # noqa: F401

            print(f"Loading {self.model_name} (4-bit, nf4)…")
            bnb_cfg = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
            )
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_name, trust_remote_code=True
            )
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                quantization_config=bnb_cfg,
                device_map="auto",
                trust_remote_code=True,
            )
            self._model.eval()
            print("LLM ready.")
            return True
        except Exception as e:
            print(f"[INFO] LLM unavailable ({e}), using rule-based fallback.")
            return False

    # ── LLM inference ─────────────────────────────────────────────────────────
    def _generate(self, messages: list[dict]) -> str:
        # enable_thinking=True 让模型先推理再调工具，4B 小模型更可靠
        try:
            text = self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                tools=TOOLS_SCHEMA,
                enable_thinking=True,
            )
        except TypeError:
            text = self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                tools=TOOLS_SCHEMA,
            )

        inputs = self._tokenizer(text, return_tensors="pt").to(self._model.device)
        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=False,
                temperature=None,
                top_p=None,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        return self._tokenizer.decode(
            outputs[0][inputs.input_ids.shape[-1]:],
            skip_special_tokens=False,
        )

    @staticmethod
    def _parse_tool_call(response: str) -> tuple[str, dict] | None:
        """解析 Qwen3 格式的工具调用：<tool_call>{...}</tool_call>

        Qwen3 有时会先输出 </think> 结束 thinking block，再给出 tool call。
        """
        # Strip thinking block if present
        clean = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)

        match = re.search(r"<tool_call>\s*(\{.*\})\s*</tool_call>", clean, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                name = data.get("name", "")
                args = data.get("arguments", {})
                # arguments 有时是 JSON 字符串而非 dict
                if isinstance(args, str):
                    args = json.loads(args)
                return name, args
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    # ── Tool execution ────────────────────────────────────────────────────────
    def _execute_tool(self, name: str, args: dict, state: AgentState) -> tuple[str, bool]:
        """执行工具，返回 (observation, is_waiting_for_user)。"""
        if name == "quality_assess":
            if state.image is None:
                return "错误：尚未上传图片", False
            result = quality_assess(state.image)
            state.quality_result = result
            # 确定 4 通道路由决策并写入 state
            state.channel_decision = route_by_quality(result.overall)
            obs = {
                "overall_score": round(result.overall, 3),
                "scores": {k: round(v, 3) for k, v in result.scores.items()},
                "issues": result.issues,
                "is_acceptable": result.is_acceptable,
                "channel": state.channel_decision.value,   # 让 LLM 明确知道路由结果
            }
            return json.dumps(obs, ensure_ascii=False), False

        elif name == "enhance_image":
            # enhance_then_diagnose 通道：q̄ ∈ [TAU_SEVERE, TAU_MODERATE)
            if state.image is None:
                return "错误：尚未上传图片", False
            enhanced = _enhance_with_stage2(state.image)
            state.enhanced_image = enhanced
            # 增强后立即做特征提取 + triage（pipeline 内嵌）
            target_img = enhanced if enhanced is not None else state.image
            feats = extract_features(target_img)
            state.features_result = feats
            result = triage(feats)
            state.triage_result = result
            obs = {
                "enhanced": enhanced is not None,
                "malignancy_prob": round(result.malignancy_prob, 3),
                "uncertainty": round(result.uncertainty, 4),
                "abcd": {k: round(v, 3) for k, v in result.abcd_values.items()},
                "recommendation": result.recommendation,
                "urgency": result.urgency,
                "channel": ChannelDecision.ENHANCE_THEN_DIAGNOSE.value,
            }
            return json.dumps(obs, ensure_ascii=False), False

        elif name == "analyze_lesion":
            if state.image is None:
                return "错误：尚未上传图片", False
            cautioned = args.get("cautioned", False)
            feats = extract_features(state.image)
            state.features_result = feats
            result = triage(feats)
            state.triage_result = result
            # cautioned_diagnosis 通道：在推荐意见里附加不确定性标注
            if cautioned or (
                state.channel_decision == ChannelDecision.CAUTIONED_DIAGNOSIS
            ):
                result.recommendation = (
                    "【图像质量中等，结果存在不确定性】" + result.recommendation
                )
                state.channel_decision = ChannelDecision.CAUTIONED_DIAGNOSIS
            else:
                state.channel_decision = ChannelDecision.DIRECT_DIAGNOSIS
            obs = {
                "malignancy_prob": round(result.malignancy_prob, 3),
                "uncertainty": round(result.uncertainty, 4),
                "abcd": {k: round(v, 3) for k, v in result.abcd_values.items()},
                "recommendation": result.recommendation,
                "urgency": result.urgency,
                "channel": state.channel_decision.value,
            }
            return json.dumps(obs, ensure_ascii=False), False

        elif name == "ask_user":
            question = args.get("question", "能提供更多信息吗？")
            state.retake_count += 1
            state.waiting_for_user = True
            state.pending_question = question
            # query_for_retake 通道：保证 channel_decision 已设置
            if state.channel_decision is None or (
                state.quality_result is not None
                and state.quality_result.overall < TAU_SEVERE
            ):
                state.channel_decision = ChannelDecision.QUERY_FOR_RETAKE
            return f"已向用户提问：{question}", True

        elif name == "final_answer":
            recommendation = args.get(
                "recommendation",
                state.triage_result.recommendation if state.triage_result else "建议就医"
            )
            urgency = args.get("urgency", "medium")
            if state.triage_result:
                state.triage_result.recommendation = recommendation
                state.triage_result.urgency = urgency
            state.done = True
            return json.dumps({"recommendation": recommendation, "urgency": urgency}, ensure_ascii=False), False

        return f"未知工具：{name}", False

    # ── Public API ────────────────────────────────────────────────────────────
    def start(self, image: np.ndarray) -> AgentState:
        state = AgentState(image=image)
        state.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "我上传了一张皮肤图片，请帮我分析。"},
        ]
        if not self._load_model():
            return self._fallback.start(state)
        return self._llm_step(state)

    def continue_with_new_image(self, state: AgentState, new_image: np.ndarray) -> AgentState:
        state.image = new_image
        state.waiting_for_user = False
        state.pending_question = ""
        # Reset quality result so agent re-evaluates the new image
        state.quality_result = None
        state.messages.append({"role": "user", "content": "我重新拍了一张图片，请继续分析。"})
        if self._model is None:
            return self._fallback.start(state)
        return self._llm_step(state)

    def continue_with_text(self, state: AgentState, user_text: str) -> AgentState:
        state.clinical_answers.append(user_text)
        state.waiting_for_user = False
        state.pending_question = ""
        state.messages.append({"role": "user", "content": user_text})
        if self._model is None:
            return self._fallback.continue_after_text(state)
        return self._llm_step(state)

    # ── LLM loop ──────────────────────────────────────────────────────────────
    def _llm_step(self, state: AgentState, max_steps: int = 10) -> AgentState:
        for _ in range(max_steps):
            if state.done or state.waiting_for_user:
                break

            response = self._generate(state.messages)
            state.messages.append({"role": "assistant", "content": response})

            tool_call = self._parse_tool_call(response)
            if tool_call is None:
                break

            name, args = tool_call

            # 强制结束：超过追问上限后直接分析
            if name == "ask_user" and state.retake_count >= MAX_RETAKE_ROUNDS:
                state = self._fallback._analyze(state)
                break

            observation, is_waiting = self._execute_tool(name, args, state)
            state.messages.append({"role": "tool", "content": observation, "name": name})

            if is_waiting:
                break

        return state


# ── Rule-based fallback ───────────────────────────────────────────────────────
class _RuleBasedFallback:
    """无 LLM 时的规则状态机，按 4 通道阈值路由，行为与 ReAct Agent 一致。

    4 通道路由（复用 route_by_quality，阈值真源同 csv）：
      QUERY_FOR_RETAKE      → 触发重拍询问（最多 MAX_RETAKE_ROUNDS 次）
      ENHANCE_THEN_DIAGNOSE → 调用 VisiEnhance Stage2 增强后诊断
      CAUTIONED_DIAGNOSIS   → 直接诊断 + 附不确定性标注
      DIRECT_DIAGNOSIS      → 直接诊断
    """

    def start(self, state: AgentState) -> AgentState:
        result = quality_assess(state.image)
        state.quality_result = result
        channel = route_by_quality(result.overall)
        state.channel_decision = channel

        if channel == ChannelDecision.QUERY_FOR_RETAKE:
            if state.retake_count >= MAX_RETAKE_ROUNDS:
                # 超过最大追问次数 → 按 cautioned_diagnosis 兜底
                return self._analyze(state, cautioned=True)
            top_issue = result.issues[0] if result.issues else "sharpness"
            state.retake_count += 1
            state.waiting_for_user = True
            state.pending_question = get_retake_question(top_issue)
            return state

        elif channel == ChannelDecision.ENHANCE_THEN_DIAGNOSE:
            return self._enhance_and_analyze(state)

        elif channel == ChannelDecision.CAUTIONED_DIAGNOSIS:
            return self._analyze(state, cautioned=True)

        else:  # DIRECT_DIAGNOSIS
            return self._analyze(state, cautioned=False)

    def continue_after_text(self, state: AgentState) -> AgentState:
        # Text answer → re-route based on current quality result
        if state.quality_result is None:
            return self.start(state)
        channel = route_by_quality(state.quality_result.overall)
        if channel in (ChannelDecision.DIRECT_DIAGNOSIS, ChannelDecision.CAUTIONED_DIAGNOSIS):
            return self._analyze(state, cautioned=(channel == ChannelDecision.CAUTIONED_DIAGNOSIS))
        return self.start(state)

    @staticmethod
    def _enhance_and_analyze(state: AgentState) -> AgentState:
        """enhance_then_diagnose 通道：增强后再做 triage。"""
        enhanced = _enhance_with_stage2(state.image)
        state.enhanced_image = enhanced
        target = enhanced if enhanced is not None else state.image
        feats = extract_features(target)
        state.features_result = feats
        result = triage(feats)
        state.triage_result = result
        state.channel_decision = ChannelDecision.ENHANCE_THEN_DIAGNOSE
        state.done = True
        return state

    @staticmethod
    def _analyze(state: AgentState, *, cautioned: bool = False) -> AgentState:
        """直接诊断 / 谨慎诊断通道。"""
        feats = extract_features(state.image)
        state.features_result = feats
        result = triage(feats)
        if cautioned:
            result.recommendation = (
                "【图像质量中等，结果存在不确定性】" + result.recommendation
            )
            state.channel_decision = ChannelDecision.CAUTIONED_DIAGNOSIS
        else:
            state.channel_decision = ChannelDecision.DIRECT_DIAGNOSIS
        state.triage_result = result
        state.done = True
        return state


# ── VisiEnhance Stage2 helper ─────────────────────────────────────────────────
def _enhance_with_stage2(image_rgb: np.ndarray) -> Optional[np.ndarray]:
    """使用 VisiEnhance Stage2（DP-Loss 微调）对图片进行诊断保持增强。

    enhance_then_diagnose 通道调用此函数。
    ckpt 未就绪时 graceful fallback：返回 None，由调用方使用原图。

    TODO: Stage2 ckpt（VISIENHANCE_S2_CKPT）尚未训练完成（DATA_INVENTORY 标注「待训」）；
          ckpt 就绪后取消 early return，确认 VisiEnhanceNet 参数与训练 config 一致。
          researcher 确认：base_channels=64, mid_blocks=8（Plan A config，需核 train_visienhance.py）。
    """
    if not VISIENHANCE_S2_CKPT.exists():
        # Graceful fallback：ckpt 不存在时返回 None（调用方使用原图继续推断）
        return None

    try:
        import cv2
        from torchvision import transforms
        from models.visienhance import VisiEnhanceNet

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # TODO: 确认 base_channels/mid_blocks 与 Stage2 训练 config 一致（查 train_visienhance.py）
        model = VisiEnhanceNet(
            base_channels=64,   # TODO: 未找到官方源中 Stage2 训练 config，需 researcher 确认
            mid_blocks=8,       # TODO: 同上
        ).to(device).eval()

        ckpt = torch.load(str(VISIENHANCE_S2_CKPT), map_location=device)
        state_dict = ckpt.get("model", ckpt)
        model.load_state_dict(state_dict)

        # Preprocess
        img = cv2.resize(image_rgb, (256, 256))
        _to_tensor = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        x = _to_tensor(img).unsqueeze(0).to(device)

        # VisiScore q vector（用于 FiLM conditioning）
        from agent.tools import ModelRegistry, _TRANSFORM
        reg = ModelRegistry.get()
        q_input = _TRANSFORM(cv2.resize(image_rgb, (224, 224))).unsqueeze(0).to(device)
        with torch.no_grad():
            _, q_vec = reg.visiscore.forward_features(q_input)
            x_enh = model(x, q_vec)   # VisiEnhanceNet.forward(x, q)

        # Postprocess → uint8 RGB
        x_enh = x_enh.squeeze(0).clamp(0, 1).cpu().numpy().transpose(1, 2, 0)
        # Denormalize from ImageNet normalization
        mean = np.array([0.485, 0.456, 0.406])
        std  = np.array([0.229, 0.224, 0.225])
        x_enh = (x_enh * std + mean).clip(0, 1)
        enhanced = (x_enh * 255).astype(np.uint8)
        return cv2.resize(enhanced, (image_rgb.shape[1], image_rgb.shape[0]))

    except Exception as e:
        # 任何加载/推理错误 → graceful fallback，不崩 agent
        print(f"[INFO] VisiEnhance Stage2 enhancement failed ({e}), using original image.")
        return None
