"""ReAct Agent 编排逻辑：Qwen3-8B 4-bit 量化驱动工具调用循环。

状态机（最多追问 3 轮）：
  INIT → quality_assess → (质量差) → ask_user → 等待新图
                        → (质量好) → analyze_lesion → final_answer

LLM 不可用时自动回退到规则引擎（RuleBasedFallback）。
"""

from __future__ import annotations

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

# ── Tool schema (Qwen3 function-calling format) ───────────────────────────────
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "quality_assess",
            "description": "评估当前上传皮肤图片的拍摄质量（清晰度/亮度/完整性等），返回各维度得分",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_lesion",
            "description": "分析皮损 ABCD 临床特征并运行 Q-VIB 模型评估恶性风险，仅在质量达标后调用",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "向用户提问，引导其上传更好的图片或提供临床背景信息",
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

SYSTEM_PROMPT = """你是 VisiSkin Agent，一个专门分析皮肤病变图片的 AI 助手。

工作流程（必须严格遵守）：
1. 用户上传图片后，首先调用 quality_assess() 检查图片质量
2. 如果图片质量不达标（issues 不为空），用 ask_user() 引导用户重新拍摄，最多 3 次
3. 图片质量达标后，调用 analyze_lesion() 获取分析结果
4. 调用 final_answer() 给出分诊建议

重要原则：
- 必须先 quality_assess，再 analyze_lesion，最后 final_answer
- 给出的是「分诊建议」而非「确诊结论」，不可用「确诊」「诊断为」等词
- 中文回复，语气温和专业"""


# ── Agent state ───────────────────────────────────────────────────────────────
@dataclass
class AgentState:
    image: Optional[np.ndarray] = None
    retake_count: int = 0
    quality_result: Optional[QualityResult] = None
    features_result: Optional[FeaturesResult] = None
    triage_result: Optional[TriageResult] = None
    clinical_answers: list[str] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    done: bool = False
    waiting_for_user: bool = False
    pending_question: str = ""


# ── ReAct Agent (Qwen3-8B) ────────────────────────────────────────────────────
class ReActAgent:
    """Qwen3-8B 4-bit 量化驱动的 ReAct Agent。LLM 不可用时回退到规则引擎。"""

    def __init__(self, model_name: str = "Qwen/Qwen3-8B", use_llm: bool = True):
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

            print(f"Loading {self.model_name} (4-bit)…")
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
        # enable_thinking=False 关闭 Qwen3 的 CoT 思考链，减少推理时间
        try:
            text = self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                tools=TOOLS_SCHEMA,
                enable_thinking=False,
            )
        except TypeError:
            # 旧版 transformers 不支持 enable_thinking 参数
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
                max_new_tokens=256,
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

        match = re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", clean, re.DOTALL)
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
            obs = {
                "overall_score": round(result.overall, 3),
                "scores": {k: round(v, 3) for k, v in result.scores.items()},
                "issues": result.issues,
                "is_acceptable": result.is_acceptable,
            }
            return json.dumps(obs, ensure_ascii=False), False

        elif name == "analyze_lesion":
            if state.image is None:
                return "错误：尚未上传图片", False
            feats = extract_features(state.image)
            state.features_result = feats
            result = triage(feats)
            state.triage_result = result
            obs = {
                "malignancy_prob": round(result.malignancy_prob, 3),
                "uncertainty": round(result.uncertainty, 4),
                "abcd": {k: round(v, 3) for k, v in result.abcd_values.items()},
                "recommendation": result.recommendation,
                "urgency": result.urgency,
            }
            return json.dumps(obs, ensure_ascii=False), False

        elif name == "ask_user":
            question = args.get("question", "能提供更多信息吗？")
            state.retake_count += 1
            state.waiting_for_user = True
            state.pending_question = question
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
    """无 LLM 时的规则状态机，行为与 ReAct Agent 一致。"""

    def start(self, state: AgentState) -> AgentState:
        result = quality_assess(state.image)
        state.quality_result = result

        if result.is_acceptable or state.retake_count >= MAX_RETAKE_ROUNDS:
            return self._analyze(state)

        top_issue = result.issues[0] if result.issues else "sharpness"
        state.retake_count += 1
        state.waiting_for_user = True
        state.pending_question = get_retake_question(top_issue)
        return state

    def continue_after_text(self, state: AgentState) -> AgentState:
        # Text answer → proceed to analysis if quality was OK enough
        if state.quality_result and state.quality_result.is_acceptable:
            return self._analyze(state)
        return self.start(state)

    @staticmethod
    def _analyze(state: AgentState) -> AgentState:
        feats = extract_features(state.image)
        state.features_result = feats
        state.triage_result = triage(feats)
        state.done = True
        return state
