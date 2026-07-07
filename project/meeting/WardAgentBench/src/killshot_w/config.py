# -*- coding: utf-8 -*-
"""
config.py — 路 W' $5 kill-shot 单一配置真源
==========================================
服务哪个 §/lever（drift 契约）：
  WardAgentBench 路 W' 的 $5 kill-shot —— 验证「前沿 MLLM 读原始生理波形
  能否判 ICU 警报真假」是否失败。lever = 建立「前沿 MLLM 在安全攸关警报判
  真假上失败」的初步证据。数据 = PhysioNet/CinC Challenge 2015（五类心律
  报警 + 专家 True/False 金标，客观、开放、免 CITI）。

本文件是整条 harness 的**唯一配置源**：N、模型列表、window、下采样、cost 上限、
输出目录都在这里改，别散落到各脚本。所有下游脚本 `import config as C`。

Windows 规范：pathlib、utf-8、路径正斜杠、无硬编码盘符。
⚠️ 我不跑任何代码，写完交主线跑（见文件尾运行顺序）。
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径（真源同 .portfolio/datasets.json 的 wardagent_alarm.PhysioNet2015）
# ---------------------------------------------------------------------------
THIS = Path(__file__).resolve()
PKG_DIR = THIS.parent                      # .../src/killshot_w/
# killshot_w -> src -> WardAgentBench -> meeting -> project -> <repo root>
REPO_ROOT = THIS.parents[5]

# 原始波形下到共享 data/ 下（与 ks3_pilot 的 data/external/challenge-2015 区分开，
# 本 kill-shot 只取均衡子集，独立目录避免污染）。
DATA_DIR = REPO_ROOT / "data" / "challenge2015_killshot"
# 生成的模型输入（文本 + 图像）与结果留在包内，便于人工检视 + verifier Bash 核。
INPUTS_DIR = PKG_DIR / "inputs"
RESULTS_DIR = PKG_DIR / "results"

# 下载/在线只读用的 PhysioNet 目录（同 ks3_pilot 00_check_access 已验通的 pn_dir）。
# wfdb.rdheader(rec, pn_dir=PN_DIR) / wfdb.dl_database(PN_DIR, ...) 都用它。
PN_DIR = "challenge-2015/1.0.0/training"
# TODO(主线首跑确认): dl_database 的 db_dir 是否吃 "challenge-2015/1.0.0/training"。
#   若 dl_database 报路径错，退回逐条 wfdb.rdrecord(pn_dir=PN_DIR)+wfdb.wrsamp 落盘。

# ---------------------------------------------------------------------------
# 采样规模（跨 5 类均衡、真假都要有）
# ---------------------------------------------------------------------------
N_TOTAL = 30                # 目标总条数
N_PER_CLASS = 6             # 每类目标条数（5 类 × 6 = 30）
# 每类内尽量真假各半（best-effort，实际受该类真/假可得量限制，见 download_data 注释）。
N_TRUE_PER_CLASS_TARGET = 3
N_FALSE_PER_CLASS_TARGET = 3
# 探测 header 上限（防对 750 条全在线读头，超支时间）；按类优先探。
MAX_HEADER_PROBES = 400

# PhysioNet 2015 官方五类告警名（.hea 注释/comments 里的规范写法，同 ks3_pilot）。
# canonical -> 人类可读（喂 prompt / 图标题用可读，CSV 存 canonical）。
ALARM_TYPES = {
    "Asystole": "Asystole",
    "Bradycardia": "Extreme Bradycardia",
    "Tachycardia": "Extreme Tachycardia",
    "Ventricular_Tachycardia": "Ventricular Tachycardia",
    "Ventricular_Flutter_Fib": "Ventricular Flutter/Fibrillation",
}
# 记录名首字母 -> 告警类型（challenge-2015 命名惯例，仅用于**优先探测顺序**，
# 权威类型仍以 header comments 解析为准，不靠前缀定论）。
# TODO(主线首跑确认): 核 header 解析出的类型与前缀是否一致（打印不一致条数）。
RECORD_PREFIX_TYPE = {
    "a": "Asystole",
    "b": "Bradycardia",
    "t": "Tachycardia",
    "v": "Ventricular_Tachycardia",
    "f": "Ventricular_Flutter_Fib",
}

# ---------------------------------------------------------------------------
# 窗口 + 导联 + 下采样
# ---------------------------------------------------------------------------
# 报警发生在段内第 300s（官方固定 5min 处，同 ks3_pilot）。取报警点前 window。
ALARM_ONSET_S = 300.0
WINDOW_SECONDS = 16          # 取 [300-16, 300] s
NATIVE_HZ = 250.0            # challenge-2015 采样率（首跑以 header.fs 为准，此为默认）

# 文本表征下采样（控 token 量）。16s × 50Hz = 800 点/导联。
DOWNSAMPLE_HZ_TEXT = 50.0
MAX_TEXT_SAMPLES_PER_LEAD = 800   # 硬顶：超了再等间隔抽稀（防 token 爆）
TEXT_DECIMALS = 3                 # 数值保留小数位（控字符数）

# 图像表征渲染下采样（保形态，不追求极致 token）。16s × 125Hz = 2000 点/导联。
DOWNSAMPLE_HZ_IMAGE = 125.0
IMAGE_DPI = 120

# 导联选择：主 = ECG II，备用 1 条脉动波（ABP/PLETH），凑不满退备用 ECG 导联。
N_LEADS = 2
ECG_LEAD_PRIORITY = ["II", "V", "I", "III", "aVR", "aVL", "aVF", "MCL", "MCL1"]
PULSATILE_LEAD_PRIORITY = ["ABP", "PLETH", "RESP"]
# TODO(主线首跑确认): 核 header.sig_name 的确切拼写（大小写/别名），补全上面优先表。

# ---------------------------------------------------------------------------
# 模型列表（多 provider）。key 缺的 provider 由 run_models 自动跳过并打印。
# supports_image=能读图（表征 B）；文本表征 A 所有模型都跑。
#   supports_image=False 的纯文本模型：run_models 自动**跳过图像表征那一路**，
#   只跑文本（避免给纯文本模型发 PNG 报错）——逻辑已在 run_models.main 循环内。
# provider="openrouter"：走 OpenAI 兼容接口（openai SDK + OPENROUTER_BASE_URL），
#   一批 `:free` 免费模型共用 env_key=OPENROUTER_API_KEY；缺 key 则整批跳过。
# ⚠️ model_id 的确切快照名可能随 provider 更新，首跑前主线核对官方最新可用名。
#    别臆想不存在的快照；查不到就用 provider 文档给的 latest alias。
# ---------------------------------------------------------------------------
MODELS = [
    {
        "name": "gpt-4o",
        "provider": "openai",
        "model_id": "gpt-4o",              # alias 指向最新 4o 快照
        "env_key": "OPENAI_API_KEY",
        "supports_image": True,
        "is_reasoning": False,
    },
    {
        "name": "gpt-5",
        "provider": "openai",
        "model_id": "gpt-5",               # TODO(主线): 核实账号可用的 GPT-5 快照名
        "env_key": "OPENAI_API_KEY",
        "supports_image": True,
        "is_reasoning": True,              # 推理模型：用 max_completion_tokens、禁 temperature
    },
    {
        "name": "gemini-2.5-pro",
        "provider": "google",
        "model_id": "gemini-2.5-pro",      # TODO(主线): 核实可用快照（或 gemini-1.5-pro）
        "env_key": "GEMINI_API_KEY",
        "supports_image": True,
        "is_reasoning": False,
    },
    {
        "name": "claude-opus-4",
        "provider": "anthropic",
        "model_id": "claude-opus-4-20250514",  # TODO(主线): 核实可用快照名
        "env_key": "ANTHROPIC_API_KEY",
        "supports_image": True,
        "is_reasoning": False,
    },
    # --- OpenRouter 免费模型（OpenAI 兼容接口）。model_id 已含 `:free` 后缀 --------
    # 全部共用 env_key=OPENROUTER_API_KEY + base_url=OPENROUTER_BASE_URL（.env）。
    # ⚠️ model_id 由派单方核实（OpenRouter 上存在、`:free`）；首跑前主线在
    #    https://openrouter.ai/models?max_price=0 核对仍可用（免费模型下架/改名较频）。
    # ⚠️ OpenRouter free tier 有严格速率/日额限制（常见 20 req/min、每日上限），
    #    首跑关注 429/额度报错；必要时主线调大 config.REQUEST_SLEEP_S。
    # 纯文本强模型（supports_image=False -> 只跑文本表征 A）：
    {
        "name": "or-gpt-oss-120b",
        "provider": "openrouter",
        "model_id": "openai/gpt-oss-120b:free",
        "env_key": "OPENROUTER_API_KEY",
        "supports_image": False,
        # gpt-oss 系为推理模型：MAX_OUTPUT_TOKENS(400) 可能被 reasoning 吃掉致 content 空。
        # TODO(主线首跑): 看 raw_response 是否为空/被截，必要时上调 MAX_OUTPUT_TOKENS。
        "is_reasoning": False,     # OpenRouter 分支统一走标准 chat 参数（不区分此字段）
    },
    {
        "name": "or-qwen3-next-80b",
        "provider": "openrouter",
        "model_id": "qwen/qwen3-next-80b-a3b-instruct:free",
        "env_key": "OPENROUTER_API_KEY",
        "supports_image": False,
        "is_reasoning": False,
    },
    {
        "name": "or-llama-3.3-70b",
        "provider": "openrouter",
        "model_id": "meta-llama/llama-3.3-70b-instruct:free",
        "env_key": "OPENROUTER_API_KEY",
        "supports_image": False,
        "is_reasoning": False,
    },
    {
        "name": "or-nemotron-3-super-120b",
        "provider": "openrouter",
        "model_id": "nvidia/nemotron-3-super-120b-a12b:free",
        "env_key": "OPENROUTER_API_KEY",
        "supports_image": False,
        "is_reasoning": False,
    },
    # 多模态（supports_image=True -> 文本 A + 图像 B 都跑，能读波形 PNG）：
    {
        "name": "or-gemma-4-31b",
        "provider": "openrouter",
        "model_id": "google/gemma-4-31b-it:free",
        "env_key": "OPENROUTER_API_KEY",
        "supports_image": True,
        "is_reasoning": False,
    },
    {
        "name": "or-nemotron-nano-12b-vl",
        "provider": "openrouter",
        "model_id": "nvidia/nemotron-nano-12b-v2-vl:free",
        "env_key": "OPENROUTER_API_KEY",
        "supports_image": True,
        "is_reasoning": False,
    },
]

# 表征集合。text=数字序列化；image=波形 PNG。
REPRESENTATIONS = ["text", "image"]

# ---------------------------------------------------------------------------
# 调用/成本控制（防超支硬顶）
# ---------------------------------------------------------------------------
# 总 API 调用**硬上限**：达到即停，不再发新调用（含重试计入）。
# 预估：N(30) × 表征(2) × 可用模型(≤4) = ≤240 次；留 buffer → 300。
# 主线按实际可用 key 的 provider 数下调（例如只 2 个 key → 30×2×2=120，设 150 即可）。
MAX_API_CALLS = 300
MAX_RETRIES = 3              # 单次调用失败重试次数（指数退避）
RETRY_BASE_SLEEP_S = 4.0    # 退避基数秒
REQUEST_SLEEP_S = 1.0       # 每次调用后固定间隔（限速，防触发 provider RPM 限）
MAX_OUTPUT_TOKENS = 400     # 只要 TRUE/FALSE + 一句理由，短即可（省钱）；推理模型会另加思考预算

# ---------------------------------------------------------------------------
# rubric prompt（单一真源）。{alarm_type_readable} 注入人类可读告警类型。
# 严格首行输出格式，便于 score 端确定性解析 TRUE/FALSE。
# ⚠️ 只告知告警类型（任务设定的一部分），**绝不把专家 True/False 金标写进 prompt/图**
#    —— 否则泄漏答案（评估集不可泄漏红线）。
# ---------------------------------------------------------------------------
PROMPT_TEMPLATE = (
    "You are assisting with ICU physiological monitor review.\n"
    "A bedside monitor has just triggered a '{alarm_type_readable}' alarm.\n"
    "Below is the physiological waveform recorded in the {window_seconds} seconds "
    "immediately BEFORE the alarm was triggered.\n\n"
    "{payload}\n\n"
    "Question: Is this a TRUE alarm (a genuine {alarm_type_readable} event actually "
    "present in the waveform) or a FALSE alarm (caused by artifact / noise / lead "
    "movement rather than a real {alarm_type_readable} event)?\n\n"
    "Answer format (strict):\n"
    "- First line: exactly one word, either TRUE or FALSE.\n"
    "- Second line: one short sentence explaining your reasoning.\n"
)
# 图像表征时 payload 处放一句占位（真图作为独立 image part 附上）。
IMAGE_PAYLOAD_PLACEHOLDER = (
    "[The waveform is provided as an attached image. Leads and time axis are labeled "
    "on the figure.]"
)

# ---------------------------------------------------------------------------
# 文献参照线（score 画图用）—— 均为**文献值/引用**，非本 harness 自测（R2）。
#   naive       : 全判多数类基线（由本样本金标现算，不是常数）
#   0.8139      : PhysioNet/CinC 2015 Challenge 冠军参照（引用值）
#   VTaC CNN    : 官方 split AUC **0.949**（VTaC, NeurIPS 2023 D&B）。
#                 0.96 是**松 split**（arXiv 2503.14621）报的值，非官方 split —— 口径更宽松。
# ⚠️ 冠军 0.8139 是 Challenge 官方**加权评分**口径（惩罚漏真>误留假），与本 harness
#    的朴素准确率口径不同尺；画线仅作量级参照，图注须显式标「引用值·口径不同」。
# ⚠️ 下方 REF_LINES 当前画的仍是 0.96（松 split 值）。是否改用官方 split 0.949 涉及
#    图/summary 输出（属逻辑），留主线/planner 拍板；此处仅订正注释、不擅改字典值。
# ---------------------------------------------------------------------------
REF_LINES = {
    "PhysioNet2015 champion (0.8139, weighted score, cited)": 0.8139,
    "VTaC CNN (0.96, cited)": 0.96,   # 0.96=松 split；官方 split AUC=0.949（见上注）
}

# 中间/输出文件名（单一常量，防各脚本拼错）
MANIFEST_CSV = "manifest.csv"               # download_data -> DATA_DIR/manifest.csv
INPUTS_MANIFEST_CSV = "inputs_manifest.csv"  # build_inputs -> INPUTS_DIR/inputs_manifest.csv
RAW_CALLS_JSONL = "raw_calls.jsonl"          # run_models -> RESULTS_DIR/raw_calls.jsonl
RESULTS_CSV = "killshot_results.csv"         # score -> RESULTS_DIR/killshot_results.csv
SUMMARY_CSV = "summary.csv"                  # score -> RESULTS_DIR/summary.csv
PLOT_PNG = "killshot_accuracy.png"           # score -> RESULTS_DIR/killshot_accuracy.png

RANDOM_SEED = 20260704       # 采样可复现（R3 固定 seed）


def ensure_dirs():
    """建输出目录（下游脚本开头调）。"""
    for d in (DATA_DIR, INPUTS_DIR, RESULTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 运行顺序（主线按此跑，我不跑）：
#   1. python download_data.py            # 拉均衡子集 + manifest.csv（联网 PhysioNet，免 CITI）
#   2. python build_inputs.py             # 出文本 + 图像输入 + inputs_manifest.csv（离线）
#   3. python run_models.py               # 发 API（读 *_API_KEY 环境变量，缺的自动跳过）
#   4. python score.py                    # 出 killshot_results.csv + summary.csv + 图
# 烟测（不花 API）：python build_inputs.py --limit 2 ；python run_models.py --dry-run
# ---------------------------------------------------------------------------
