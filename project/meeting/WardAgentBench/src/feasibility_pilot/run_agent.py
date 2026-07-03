# -*- coding: utf-8 -*-
"""
run_agent.py — 对每条 scenario × {A,B} 取 agent 的结构化决策
============================================================
服务哪个 Q（可行性命门）：
  跑 agent（LLM 或 mock）在 A/B 两条件下的**结构化离散决策**，供 score.py 对指南 D*
  精确匹配。护栏：agent 只输出离散标签（escalate/route_to_role/timing_bin），
  **不用 LLM 判自由文本、不看真值**。

后端（--backend，可配置）：
  medgemma  默认。google/medgemma-4b-it，HF transformers，4-bit 量化(bitsandbytes)省显存，
            本机 8GB 或 CPU-fallback。**主线跑真模型，我只写不跑。**
  mock      规则/随机（seeded），不下模型、不看真值，供主线先跑通管道 + 建 chance baseline。
            ⚠️ mock A/B 期望相同 → 测不出命门，只验管道；命门信号来自 medgemma。

输入（CLI）：
  --scenarios  scenarios.jsonl（build_scenarios 产出，默认 ./scenarios.jsonl）
  --backend    medgemma | mock（默认 medgemma）
  --model-id   HF 模型 id（默认 google/medgemma-4b-it）
  --load-4bit  1=4bit 量化（默认 1；显存足可 0）
  --device     auto | cpu | cuda（默认 auto）
  --seed       mock 随机种子（默认 0）
  --max-new    生成最大 token（默认 128）
  --out        输出 csv（默认 ./agent_decisions.csv）

输出：agent_decisions.csv，列：
  scenario_id, record, window_idx, condition(A/B),
  backend, raw_output(截断转义), parse_ok(bool),
  escalate, route_to_role, timing_bin          # agent 结构化决策（解析失败填空串）
  （真值不在本表，score.py 从 scenarios.jsonl join，防泄漏）

Windows 规范：pathlib/utf-8/无硬编码盘符；不涉 DataLoader/spawn。**主线跑，我不跑。**
GPU 算子提示：加载 4bit HF 模型走 CUDA kernel/bitsandbytes → 主线跑
  `python run_agent.py --backend mock --smoke 1` 先验管道，再 `--backend medgemma` 跑真模型。
含 --smoke：只跑前 4 条 scenario（主线跑，我不跑）。
"""
import argparse
import csv
import json
import random
import re
import sys
from pathlib import Path

import guideline as G

THIS = Path(__file__).resolve()
PILOT_DIR = THIS.parent

VALID = {
    "escalate": set(G.ESCALATE_LEVELS),
    "route_to_role": set(G.ROLES),
    "timing_bin": set(G.TIMING_BINS),
}


# ---------------------------------------------------------------------------
# 结构化输出解析：从模型自由文本里抠 JSON，校验落在合法标签集
# ---------------------------------------------------------------------------
def parse_decision(text: str):
    """从模型输出抠出 {escalate, route_to_role, timing_bin}。返回 (decision_dict, ok)。
    ok=False 时 decision 各键为空串（score.py 记为 miss，防 LLM 判自由文本）。"""
    empty = {"escalate": "", "route_to_role": "", "timing_bin": ""}
    if not text:
        return empty, False
    # 抓第一个 {...} JSON 块
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not m:
        return empty, False
    try:
        obj = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return empty, False
    dec = {}
    ok = True
    for key in ("escalate", "route_to_role", "timing_bin"):
        val = str(obj.get(key, "")).strip().lower()
        if val in VALID[key]:
            dec[key] = val
        else:
            dec[key] = ""
            ok = False
    return dec, ok


# ---------------------------------------------------------------------------
# 后端 1：mock（seeded 随机，不看真值，建 chance baseline + 验管道）
# ---------------------------------------------------------------------------
class MockBackend:
    def __init__(self, seed=0):
        self.rng = random.Random(seed)

    def generate(self, prompt: str) -> str:
        dec = {
            "escalate": self.rng.choice(G.ESCALATE_LEVELS),
            "route_to_role": self.rng.choice(G.ROLES),
            "timing_bin": self.rng.choice(G.TIMING_BINS),
        }
        return json.dumps(dec)


# ---------------------------------------------------------------------------
# 后端 2：medgemma（HF transformers，4bit 量化，主线跑真模型）
# ---------------------------------------------------------------------------
class MedGemmaBackend:
    def __init__(self, model_id="google/medgemma-4b-it", load_4bit=True,
                 device="auto", max_new=128):
        # 延迟 import：mock 路径无需装 transformers/bitsandbytes
        import torch  # noqa: F401
        from transformers import AutoTokenizer, AutoModelForCausalLM
        self.max_new = max_new
        quant_kwargs = {}
        if load_4bit:
            from transformers import BitsAndBytesConfig
            import torch as _t
            quant_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=_t.float16,
                bnb_4bit_quant_type="nf4",
            )
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id,
            device_map=device if device != "cpu" else None,
            **quant_kwargs,
        )
        if device == "cpu":
            self.model = self.model.to("cpu")
        self.device = device

    def generate(self, prompt: str) -> str:
        import torch
        msgs = [{"role": "user", "content": prompt}]
        # 优先 chat template；无则退回纯文本
        try:
            inputs = self.tok.apply_chat_template(
                msgs, add_generation_prompt=True, return_tensors="pt")
        except Exception:  # noqa: BLE001
            inputs = self.tok(prompt, return_tensors="pt").input_ids
        if self.device != "cpu":
            inputs = inputs.to(self.model.device)
        with torch.no_grad():
            out = self.model.generate(
                inputs, max_new_tokens=self.max_new, do_sample=False,
                temperature=None, top_p=None,
                pad_token_id=self.tok.eos_token_id,
            )
        gen = out[0][inputs.shape[-1]:]
        return self.tok.decode(gen, skip_special_tokens=True)


def make_backend(args):
    if args.backend == "mock":
        return MockBackend(seed=args.seed)
    if args.backend == "medgemma":
        return MedGemmaBackend(
            model_id=args.model_id, load_4bit=bool(args.load_4bit),
            device=args.device, max_new=args.max_new)
    raise ValueError(f"未知 backend: {args.backend}")


def _trunc(s, n=300):
    s = s.replace("\n", "\\n").replace("\r", "")
    return s[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=str, default=str(PILOT_DIR / "scenarios.jsonl"))
    ap.add_argument("--backend", type=str, default="medgemma",
                    choices=["medgemma", "mock"])
    ap.add_argument("--model-id", type=str, default="google/medgemma-4b-it")
    ap.add_argument("--load-4bit", type=int, default=1)
    ap.add_argument("--device", type=str, default="auto")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-new", type=int, default=128)
    ap.add_argument("--out", type=str, default=str(PILOT_DIR / "agent_decisions.csv"))
    ap.add_argument("--smoke", type=int, default=0, help="烟测：>0 只跑前 4 条 scenario")
    args = ap.parse_args()

    sc_path = Path(args.scenarios)
    if not sc_path.exists():
        print(f"[ERR] 找不到 scenarios：{sc_path}（先跑 build_scenarios.py）")
        return 2
    scenarios = [json.loads(ln) for ln in sc_path.read_text(encoding="utf-8").splitlines()
                 if ln.strip()]
    if args.smoke:
        scenarios = scenarios[:4]
    if not scenarios:
        print("[ERR] scenarios 为空。")
        return 2

    print(f"[info] backend={args.backend} 处理 {len(scenarios)} scenario × 2 条件")
    backend = make_backend(args)

    fieldnames = ["scenario_id", "record", "window_idx", "condition", "backend",
                  "raw_output", "parse_ok", "escalate", "route_to_role", "timing_bin"]
    rows = []
    for i, sc in enumerate(scenarios):
        for cond, pkey in (("A", "prompt_A"), ("B", "prompt_B")):
            raw = backend.generate(sc[pkey])
            dec, ok = parse_decision(raw)
            rows.append({
                "scenario_id": sc["scenario_id"],
                "record": sc["record"],
                "window_idx": sc["window_idx"],
                "condition": cond,
                "backend": args.backend,
                "raw_output": _trunc(raw),
                "parse_ok": ok,
                "escalate": dec["escalate"],
                "route_to_role": dec["route_to_role"],
                "timing_bin": dec["timing_bin"],
            })
        if (i + 1) % 10 == 0:
            print(f"  [{i+1}/{len(scenarios)}]")

    out_path = Path(args.out)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    n_ok = sum(1 for r in rows if r["parse_ok"])
    print(f"[written] {out_path}  ({len(rows)} rows, parse_ok {n_ok}/{len(rows)})")
    print("[next] 跑 score.py 对指南 D* 精确匹配 + 出命门判据。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
