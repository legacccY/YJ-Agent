"""Qwen3-4B ReAct 端到端冒烟测试。

运行前确认 Qwen/Qwen3-4B 已下载到 HuggingFace 缓存。

Usage:
  cd D:/YJ-Agent/project && python test_llm_react.py
"""

import sys, time, cv2, numpy as np, pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from agent.orchestrator import ReActAgent

# ── 取一张真实皮肤图用于测试 ──────────────────────────────────────────────────
df = pd.read_csv("D:/YJ-Agent/data/quality_labels_all.csv")
orig_path = df[df["source"] == "isic2020"].iloc[0]["original_path"]
heavy_path = df[(df["source"] == "isic2020") & (df["level"] == "heavy")].iloc[0]["degraded_path"]

good_img = cv2.cvtColor(cv2.imread(str(orig_path)), cv2.COLOR_BGR2RGB)
bad_img  = cv2.cvtColor(cv2.imread(str(heavy_path)), cv2.COLOR_BGR2RGB)


def run_test(name: str, img: np.ndarray, agent: ReActAgent):
    print(f"\n{'='*50}")
    print(f"Test: {name}")
    t0 = time.perf_counter()
    state = agent.start(img)
    elapsed = time.perf_counter() - t0

    print(f"  retake_count   : {state.retake_count}")
    print(f"  waiting_for_user: {state.waiting_for_user}")
    print(f"  done           : {state.done}")
    print(f"  elapsed        : {elapsed*1000:.0f} ms")

    if state.waiting_for_user:
        print(f"  pending_question: {state.pending_question}")

    if state.triage_result:
        r = state.triage_result
        print(f"  malignancy_prob: {r.malignancy_prob:.3f}")
        print(f"  urgency        : {r.urgency}")
        print(f"  recommendation : {r.recommendation[:60]}...")

    # Show last LLM message if available
    if state.messages and len(state.messages) > 2:
        last = state.messages[-1]
        content = last.get("content", "")[:200]
        print(f"  last_message [{last.get('role')}]: {content}")

    return state, elapsed


if __name__ == "__main__":
    print("Loading ReActAgent (Qwen3-4B 4-bit)...")
    agent = ReActAgent()

    # Trigger model loading explicitly
    ok = agent._load_model()
    if not ok:
        print("\n[ERROR] Qwen3-4B not available. Please run the download first.")
        sys.exit(1)

    print("\nModel loaded. Running tests...\n")

    # Test 1: good image → should complete without asking
    s1, t1 = run_test("Good image (原图)", good_img, agent)

    # Test 2: heavy degraded → should ask user to retake
    s2, t2 = run_test("Bad image (重度降质)", bad_img, agent)

    # Summary
    print(f"\n{'='*50}")
    print("Summary:")
    print(f"  Good image: done={s1.done}, retakes={s1.retake_count}, {t1*1000:.0f}ms")
    print(f"  Bad image:  waiting={s2.waiting_for_user}, retakes={s2.retake_count}, {t2*1000:.0f}ms")

    passed = s1.done and not s1.waiting_for_user and s2.retake_count > 0
    print(f"\nLLM ReAct test: {'PASS' if passed else 'FAIL (check above)'}")
