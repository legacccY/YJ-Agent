# -*- coding: utf-8 -*-
"""
run_models.py — 对每 (record × 表征 × 模型) 发 rubric prompt，判 TRUE/FALSE
==========================================================================
服务哪个 §/lever：路 W' $5 kill-shot 推理。多 provider 适配（OpenAI / Google /
  Anthropic）；读环境变量 *_API_KEY，**缺 key 的 provider 自动跳过并打印跳过了谁**。
  固定 rubric prompt（config.PROMPT_TEMPLATE），要求首行 TRUE/FALSE。

护栏：
  - cost 硬顶 MAX_API_CALLS（含重试计数），达到即停，不再发新调用（防超支）。
  - 重试 + 指数退避 + 每调用固定间隔限速。
  - 断点续跑：已在 raw_calls.jsonl 里的 (record, representation, model) 三元组跳过，
    不重复花钱。
  - 记录**原始返回全文**（raw_response），parse 只取 TRUE/FALSE，UNPARSED 也留证。

输入：INPUTS_DIR/inputs_manifest.csv + 各 _text.txt / .png。
输出：RESULTS_DIR/raw_calls.jsonl（每行一条调用记录）。

⚠️ 我不跑代码（含烟测/真调用），写完交主线跑。
   预演（不花 API）：python run_models.py --dry-run
Windows 规范：pathlib、utf-8。
"""
import argparse
import base64
import csv
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402


# ---------------------------------------------------------------------------
# 输入装载
# ---------------------------------------------------------------------------
def load_inputs_manifest(path):
    rows = []
    with Path(path).open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def read_text_payload(text_path):
    p = Path(text_path)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def b64_image(image_path):
    p = Path(image_path)
    if not p.exists():
        return None
    return base64.b64encode(p.read_bytes()).decode("ascii")


def build_prompt(alarm_type, representation, text_payload):
    """按表征拼 prompt 文本；image 表征 payload 用占位（真图作独立 part 附上）。"""
    readable = C.ALARM_TYPES.get(alarm_type, alarm_type)
    payload = text_payload if representation == "text" else C.IMAGE_PAYLOAD_PLACEHOLDER
    return C.PROMPT_TEMPLATE.format(
        alarm_type_readable=readable,
        window_seconds=C.WINDOW_SECONDS,
        payload=payload,
    )


def parse_verdict(text):
    """从返回全文取 TRUE/FALSE（取首个出现）。找不到/两者都无 -> UNPARSED。"""
    if not text:
        return "UNPARSED"
    up = text.upper()
    i_t = up.find("TRUE")
    i_f = up.find("FALSE")
    # FALSE 内含 'ALSE'，TRUE 不与 FALSE 子串冲突；取更靠前者
    if i_t == -1 and i_f == -1:
        return "UNPARSED"
    if i_t == -1:
        return "FALSE"
    if i_f == -1:
        return "TRUE"
    return "TRUE" if i_t < i_f else "FALSE"


# ---------------------------------------------------------------------------
# provider 适配（每个返回 raw_text；抛异常交上层重试）
# ⚠️ 各 SDK 的 import 放函数内，缺装不影响其它 provider。
#    model_id/参数名的确切性见 config MODELS 的 TODO，首跑前主线核对。
# ---------------------------------------------------------------------------
def call_openai(model_cfg, prompt, image_b64):
    from openai import OpenAI  # noqa: WPS433
    client = OpenAI(api_key=os.environ[model_cfg["env_key"]])
    content = [{"type": "text", "text": prompt}]
    if image_b64 is not None:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
        })
    kwargs = {
        "model": model_cfg["model_id"],
        "messages": [{"role": "user", "content": content}],
    }
    # 推理模型（GPT-5/o 系）：用 max_completion_tokens、禁 temperature
    if model_cfg.get("is_reasoning"):
        kwargs["max_completion_tokens"] = C.MAX_OUTPUT_TOKENS
    else:
        kwargs["max_tokens"] = C.MAX_OUTPUT_TOKENS
        kwargs["temperature"] = 0
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def call_openrouter(model_cfg, prompt, image_b64):
    """OpenRouter（OpenAI 兼容接口，复用 openai SDK）。
    - 文本表征：普通 user message。
    - 图像表征：OpenAI 兼容 vision 格式（image_url = data:image/png;base64,<b64>）。
      ⚠️ image_b64 仅当模型 supports_image=True 时由 main 传入（纯文本模型的图像
         表征已在 main 循环跳过），故这里不会给纯文本模型发图。
    - 走 chat.completions.create，标准 max_tokens/temperature（不区分 is_reasoning）。
    缺 openai SDK -> 抛带清晰提示的异常，交上层重试/记录。"""
    try:
        from openai import OpenAI  # noqa: WPS433
    except ImportError as e:
        raise RuntimeError(
            "缺 openai Python SDK：请先 `pip install openai`"
            "（OpenRouter 走 OpenAI 兼容接口，复用同一 SDK）"
        ) from e
    api_key = os.getenv("OPENROUTER_API_KEY")
    # base_url 优先取 .env 的 OPENROUTER_BASE_URL，缺省兜底官方地址（防漏设 base_url
    # 时 SDK 误连 openai.com）。
    base_url = os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"
    client = OpenAI(api_key=api_key, base_url=base_url)
    content = [{"type": "text", "text": prompt}]
    if image_b64 is not None:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
        })
    resp = client.chat.completions.create(
        model=model_cfg["model_id"],
        messages=[{"role": "user", "content": content}],
        max_tokens=C.MAX_OUTPUT_TOKENS,
        temperature=0,
    )
    return resp.choices[0].message.content or ""


def call_google(model_cfg, prompt, image_b64):
    import google.generativeai as genai  # noqa: WPS433
    genai.configure(api_key=os.environ[model_cfg["env_key"]])
    model = genai.GenerativeModel(model_cfg["model_id"])
    parts = [prompt]
    if image_b64 is not None:
        parts.append({"mime_type": "image/png", "data": base64.b64decode(image_b64)})
    resp = model.generate_content(
        parts,
        generation_config={"temperature": 0, "max_output_tokens": C.MAX_OUTPUT_TOKENS},
    )
    return getattr(resp, "text", "") or ""


def call_anthropic(model_cfg, prompt, image_b64):
    import anthropic  # noqa: WPS433
    client = anthropic.Anthropic(api_key=os.environ[model_cfg["env_key"]])
    content = [{"type": "text", "text": prompt}]
    if image_b64 is not None:
        content.insert(0, {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
        })
    resp = client.messages.create(
        model=model_cfg["model_id"],
        max_tokens=C.MAX_OUTPUT_TOKENS,
        temperature=0,
        messages=[{"role": "user", "content": content}],
    )
    # 取第一段 text
    for blk in resp.content:
        if getattr(blk, "type", "") == "text":
            return blk.text or ""
    return ""


PROVIDER_DISPATCH = {
    "openai": call_openai,
    "openrouter": call_openrouter,
    "google": call_google,
    "anthropic": call_anthropic,
}


def call_with_retry(model_cfg, prompt, image_b64, counter):
    """带重试 + 退避 + cost 计数。返回 (raw_text, error_str)。counter=[已用调用数]。"""
    fn = PROVIDER_DISPATCH[model_cfg["provider"]]
    last_err = ""
    for attempt in range(C.MAX_RETRIES):
        if counter[0] >= C.MAX_API_CALLS:
            return "", "COST_CAP_REACHED"
        counter[0] += 1
        try:
            txt = fn(model_cfg, prompt, image_b64)
            time.sleep(C.REQUEST_SLEEP_S)
            return txt, ""
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
            sleep_s = C.RETRY_BASE_SLEEP_S * (2 ** attempt)
            print(f"    [retry {attempt+1}/{C.MAX_RETRIES}] {model_cfg['name']}: "
                  f"{last_err} -> sleep {sleep_s:.0f}s")
            time.sleep(sleep_s)
    return "", last_err


# ---------------------------------------------------------------------------
# 断点续跑 + provider 可用性
# ---------------------------------------------------------------------------
def load_done(jsonl_path):
    """已完成 (record, representation, model) 三元组集合（verdict 非 UNPARSED/ERROR 才算）。"""
    done = set()
    p = Path(jsonl_path)
    if not p.exists():
        return done
    for ln in p.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            o = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if o.get("verdict") not in (None, "UNPARSED", "ERROR"):
            done.add((o["record_id"], o["representation"], o["model"]))
    return done


def load_env_file(path=None):
    """轻量加载 killshot_w/.env（不引入 python-dotenv 依赖）。
    - 只补**未设**的环境变量：shell 里已 export 的优先，.env 不覆盖它。
    - 行格式 KEY=VALUE，跳过空行与 # 注释；去掉值两侧引号。
    这样主线无需手动 export 即可让 OPENROUTER_API_KEY / *_API_KEY 生效。"""
    p = Path(path) if path else (C.PKG_DIR / ".env")
    if not p.exists():
        return
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        key, _, val = ln.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def available_models():
    """按环境变量 key 过滤可用 provider，打印跳过了谁。"""
    avail, skipped = [], []
    for m in C.MODELS:
        if os.environ.get(m["env_key"]):
            avail.append(m)
        else:
            skipped.append(m)
    if skipped:
        for m in skipped:
            print(f"[skip] {m['name']}（provider={m['provider']}）: 环境变量 "
                  f"{m['env_key']} 未设 -> 跳过")
    if not avail:
        print("[ERR] 没有任何 provider 的 API key，无可跑模型。设 OPENROUTER_API_KEY "
              "/ OPENAI_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY 之一再跑"
              "（OPENROUTER_API_KEY 走一批 :free 免费模型，见 config.MODELS）。")
    return avail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="不发 API，只打印将发多少调用 + 校验输入齐不齐")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条记录（调试）")
    args = ap.parse_args()

    C.ensure_dirs()
    load_env_file()  # 从 killshot_w/.env 补齐未 export 的 *_API_KEY / OPENROUTER_BASE_URL
    in_manifest = C.INPUTS_DIR / C.INPUTS_MANIFEST_CSV
    if not in_manifest.exists():
        print(f"[ERR] 找不到 {in_manifest}，先跑 build_inputs.py。")
        return 2
    rows = load_inputs_manifest(in_manifest)
    if args.limit > 0:
        rows = rows[: args.limit]

    models = C.MODELS if args.dry_run else available_models()
    if not models:
        return 2

    jsonl_path = C.RESULTS_DIR / C.RAW_CALLS_JSONL
    done = load_done(jsonl_path)

    # 预演/预估
    planned = 0
    for r in rows:
        for rep in C.REPRESENTATIONS:
            for m in models:
                if rep == "image" and not m.get("supports_image"):
                    continue
                if (r["record_id"], rep, m["name"]) in done:
                    continue
                planned += 1
    print(f"[plan] 记录 {len(rows)} × 表征 {len(C.REPRESENTATIONS)} × 模型 {len(models)} "
          f"-> 待发 {planned} 次调用（已完成跳过 {len(done)}）")
    print(f"[plan] cost 硬顶 MAX_API_CALLS={C.MAX_API_CALLS}")
    if args.dry_run:
        # 校验输入文件齐不齐
        miss = 0
        for r in rows:
            if not Path(r["text_path"]).exists():
                print(f"  [miss text] {r['record_id']}"); miss += 1
            if r["image_path"] and not Path(r["image_path"]).exists():
                print(f"  [miss image] {r['record_id']}"); miss += 1
        print(f"[dry-run] 输入缺失 {miss} 个。未发任何 API。")
        return 0

    counter = [0]  # 已用调用数（跨记录累计，含重试）
    n_written = 0
    with jsonl_path.open("a", encoding="utf-8") as fout:
        for r in rows:
            rid = r["record_id"]
            text_payload = read_text_payload(r["text_path"])
            img_b64 = b64_image(r["image_path"]) if r["image_path"] else None
            for rep in C.REPRESENTATIONS:
                for m in models:
                    if rep == "image" and not m.get("supports_image"):
                        continue
                    if (rid, rep, m["name"]) in done:
                        continue
                    if counter[0] >= C.MAX_API_CALLS:
                        print(f"[STOP] 达 cost 硬顶 {C.MAX_API_CALLS}，停止发新调用。")
                        print(f"[done] 本轮写 {n_written} 条。续跑再执行本脚本（会跳已完成）。")
                        return 0
                    prompt = build_prompt(r["alarm_type"], rep, text_payload)
                    image_arg = img_b64 if rep == "image" else None
                    raw, err = call_with_retry(m, prompt, image_arg, counter)
                    verdict = "ERROR" if err else parse_verdict(raw)
                    rec = {
                        "record_id": rid,
                        "alarm_type": r["alarm_type"],
                        "expert_label": r["expert_label"],
                        "representation": rep,
                        "model": m["name"],
                        "provider": m["provider"],
                        "model_id": m["model_id"],
                        "verdict": verdict,
                        "error": err,
                        "raw_response": raw,
                        "calls_used": counter[0],
                    }
                    fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fout.flush()
                    n_written += 1
                    print(f"[{counter[0]:>3}] {rid} | {rep:5s} | {m['name']:16s} "
                          f"-> {verdict}"
                          + (f"  ERR={err}" if err else ""))
    print(f"[done] 写 {n_written} 条 -> {jsonl_path}（cost 用 {counter[0]}/{C.MAX_API_CALLS}）")
    print("[done] 下一步：python score.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
