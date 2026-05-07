"""VisiSkin Agent — Gradio Demo

上传皮肤图片 → Agent 评估质量 → 必要时引导重拍（最多 3 轮）→ 输出分诊建议

启动：
  cd D:/YJ-Agent/project && python app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import gradio as gr
from gradio.components.chatbot import ChatMessage

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

import argparse

from agent.orchestrator import ReActAgent, AgentState
from agent.tools import QUALITY_DIMS

# ── CLI 参数 ──────────────────────────────────────────────────────────────────
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--no-llm", action="store_true", help="强制使用规则引擎（跳过 Qwen3 加载）")
_args, _ = _parser.parse_known_args()

# ── Global state ──────────────────────────────────────────────────────────────
_agent = ReActAgent(use_llm=not _args.no_llm)
_state: AgentState | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────
def _quality_bars(quality_result) -> dict | None:
    if quality_result is None:
        return None
    return {dim: round(quality_result.scores.get(dim, 0), 2) for dim in QUALITY_DIMS}


def _format_triage(result) -> str:
    if result is None:
        return ""
    urgency_label = {"low": "🟢 低风险", "medium": "🟡 中度风险", "high": "🔴 较高风险"}.get(
        result.urgency, "⚪ 未知"
    )
    abcd = result.abcd_values
    return (
        f"### {urgency_label}\n\n"
        f"**恶性概率**: {result.malignancy_prob:.1%} &nbsp;|&nbsp; "
        f"**不确定性**: {result.uncertainty:.3f}\n\n"
        f"**ABCD 特征** — "
        f"A（不对称）`{abcd['asymmetry']:.2f}` · "
        f"B（边界）`{abcd['border']:.2f}` · "
        f"C（色彩）`{abcd['color']:.2f}` · "
        f"D（大小）`{abcd['diameter']:.2f}`\n\n"
        f"**建议**: {result.recommendation}\n\n"
        f"*{result.disclaimer}*"
    )


# ── Event handlers ────────────────────────────────────────────────────────────
def _bot_msg(text: str) -> ChatMessage:
    return ChatMessage(role="assistant", content=text)


def _user_msg(text: str) -> ChatMessage:
    return ChatMessage(role="user", content=text)


def handle_upload(image, chat_history: list) -> tuple:
    global _state
    if image is None:
        return chat_history, None, ""

    _state = _agent.start(np.array(image) if not isinstance(image, np.ndarray) else image)

    if _state.waiting_for_user:
        chat_history = chat_history + [_bot_msg(_state.pending_question)]
        return chat_history, _quality_bars(_state.quality_result), ""

    if _state.done and _state.triage_result:
        triage_md = _format_triage(_state.triage_result)
        chat_history = chat_history + [_bot_msg(triage_md)]
        return chat_history, _quality_bars(_state.quality_result), triage_md

    return chat_history, None, ""


def handle_retake(new_image, chat_history: list) -> tuple:
    global _state
    if _state is None or new_image is None:
        return chat_history, None, ""

    img = np.array(new_image) if not isinstance(new_image, np.ndarray) else new_image
    _state = _agent.continue_with_new_image(_state, img)

    if _state.waiting_for_user:
        chat_history = chat_history + [_bot_msg(_state.pending_question)]
        return chat_history, _quality_bars(_state.quality_result), ""

    if _state.done and _state.triage_result:
        triage_md = _format_triage(_state.triage_result)
        chat_history = chat_history + [_bot_msg(triage_md)]
        return chat_history, _quality_bars(_state.quality_result), triage_md

    return chat_history, _quality_bars(_state.quality_result), ""


def handle_text(text: str, chat_history: list) -> tuple:
    global _state
    if _state is None or not text.strip():
        return chat_history, ""

    chat_history = chat_history + [_user_msg(text)]
    _state = _agent.continue_with_text(_state, text)

    if _state.waiting_for_user:
        chat_history = chat_history + [_bot_msg(_state.pending_question)]
    elif _state.done and _state.triage_result:
        chat_history = chat_history + [_bot_msg(_format_triage(_state.triage_result))]

    return chat_history, ""


def reset_session() -> tuple:
    global _state
    _state = None
    return [], None, ""


# ── UI ────────────────────────────────────────────────────────────────────────
with gr.Blocks(title="VisiSkin Agent") as demo:
    gr.Markdown("# 🔬 VisiSkin Agent\n皮肤病变智能分诊助手 — 上传图片开始分析")

    with gr.Row():
        # Left column: image inputs + quality
        with gr.Column(scale=1):
            gr.Markdown("### 图片上传")
            initial_img = gr.Image(label="上传皮肤图片", type="numpy", height=280)
            retake_img = gr.Image(label="重拍图片（Agent 引导后上传）", type="numpy", height=280)
            reset_btn = gr.Button("🔄 重新开始", variant="secondary")

            gr.Markdown("### 图片质量评分（0–1）")
            quality_json = gr.JSON(label="各维度质量")

        # Right column: chat + result
        with gr.Column(scale=2):
            gr.Markdown("### Agent 对话")
            chatbot = gr.Chatbot(height=380)

            with gr.Row():
                text_in = gr.Textbox(placeholder="回答 Agent 的追问…", show_label=False, scale=4)
                send_btn = gr.Button("发送", scale=1, variant="primary")

            gr.Markdown("### 分诊结果")
            result_md = gr.Markdown("")

    # ── Bindings ──────────────────────────────────────────────────────────────
    initial_img.upload(
        handle_upload,
        inputs=[initial_img, chatbot],
        outputs=[chatbot, quality_json, result_md],
    )
    retake_img.upload(
        handle_retake,
        inputs=[retake_img, chatbot],
        outputs=[chatbot, quality_json, result_md],
    )
    send_btn.click(handle_text, inputs=[text_in, chatbot], outputs=[chatbot, text_in])
    text_in.submit(handle_text, inputs=[text_in, chatbot], outputs=[chatbot, text_in])
    reset_btn.click(reset_session, outputs=[chatbot, quality_json, result_md])


if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7862, share=False, theme=gr.themes.Soft())
