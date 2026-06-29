"""
run_transhla.py — QuantImmuBench §工具部署  TransHLA_I 推理脚本
服务项目：quantimmu-bench §工具部署 P9 lever=补满 30 工具 apples-to-apples

功能：
  对 transhla_input.csv 的每个唯一肽（8-14mer）跑 TransHLA_I，输出表位概率 + 二分类标签。
  推理逻辑严格镜像官方 TransHLA_I.py（github.com/SkywalkerLuke/TransHLA，2026-06-29 核），
  零 API 臆造。

官方推理逻辑（照抄，见 README §How to use in transformers + TransHLA_I.py）：
  tokenizer = AutoTokenizer.from_pretrained("facebook/esm2_t33_650M_UR50D")
  model     = AutoModel.from_pretrained("SkywalkerLu/TransHLA_I", trust_remote_code=True)
  peptide_encoding = tokenizer(peptides)['input_ids']        # ESM2 加 CLS/EOS
  peptide_encoding = pad_inner_lists_to_length(.., 16)       # TransHLA_I 固定 pad 到 16
  peptide_encoding = torch.tensor(peptide_encoding)
  Result, _ = model(peptide_encoding.to(device))            # Result: [N, 2] 概率
  prob  = Result[:, 1]                                       # 第 2 列 = 表位概率（class 1）
  _, label = torch.max(Result, 1)                           # argmax → 0/1 标签

  注：官方 model 前向返回 (outputs, representations)；outputs 为 [N, 2] 概率分布
      （softmax 后），第二列为「是表位」的概率，越高越可能是表位。
      TransHLA_I 的 pad target_length=16（8-14mer + ESM2 CLS/EOS → 最长 16 token）。

输入：
  HPC/deploy/transhla/transhla_input.csv   ← prep_input.py 产生（单列 peptide）

输出：
  HPC/deploy/transhla/transhla_raw.csv     ← 列: peptide, prob, label

模型/权重：
  - HuggingFace：SkywalkerLu/TransHLA_I（trust_remote_code=True，自定义 modeling）
  - ESM2 嵌入：facebook/esm2_t33_650M_UR50D（tokenizer + 650M backbone，首次自动下载）
  - 许可：MIT（数字可自由发布）

平台：
  - CPU 可跑（无 CUDA 时自动 device=cpu；ESM2 650M 在 CPU 上较慢，HPC GPU 更快）。
  - 官方说明：CUDA >= 11.8 否则跑 CPU。

Windows 规范：
  - 路径用 pathlib.Path，不用反斜杠
  - 无 DataLoader 多进程（本脚本批量循环内推理，不起 worker）
  - 全程 UTF-8

用法：
  # 全量
  python run_transhla.py
  # 烟测（先跑 prep_input.py --smoke 5 生成小输入，再）
  python run_transhla.py --smoke 1
  # 指定路径 / batch
  python run_transhla.py --input-csv ... --output-csv ... --batch-size 128
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
import pandas as pd
import torch
from transformers import AutoModel, AutoTokenizer

# ---------------------------------------------------------------------------
# 路径默认值（相对脚本位置）
# ---------------------------------------------------------------------------
SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()

DEFAULT_INPUT_CSV  = SCRIPT_DIR / "transhla_input.csv"
DEFAULT_OUTPUT_CSV = SCRIPT_DIR / "transhla_raw.csv"

# 官方常量（照抄 TransHLA_I.py，零改动）
ESM2_TOKENIZER  = "facebook/esm2_t33_650M_UR50D"
TRANSHLA_MODEL  = "SkywalkerLu/TransHLA_I"
PAD_TARGET_LEN  = 16        # TransHLA_I 固定 pad 到 16（pad_inner_lists_to_length 默认）
DEFAULT_BATCH   = 128       # 官方 test_loader 用 batchsize=128


# ---------------------------------------------------------------------------
# 官方工具函数（照抄 TransHLA_I.py，零改动）
# ---------------------------------------------------------------------------

def pad_inner_lists_to_length(outer_list, target_length: int = PAD_TARGET_LEN):
    """ESM2 token id 列表统一 pad 到 target_length（pad id=1）。镜像官方实现。"""
    for inner_list in outer_list:
        padding_length = target_length - len(inner_list)
        if padding_length > 0:
            inner_list.extend([1] * padding_length)
    return outer_list


# ---------------------------------------------------------------------------
# 推理
# ---------------------------------------------------------------------------

def run(input_csv: pathlib.Path, output_csv: pathlib.Path, batch_size: int, smoke: int) -> None:
    # --- 读输入 ---
    df = pd.read_csv(input_csv, header=0, encoding="utf-8")
    peptides = df.iloc[:, 0].astype(str).str.strip().tolist()   # 官方亦取第一列
    if smoke > 0:
        peptides = peptides[:smoke]
        print(f"[run] [SMOKE] 仅推理前 {len(peptides)} 个肽")
    print(f"[run] 输入肽数: {len(peptides)}")

    # --- 加载模型（照抄官方）---
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[run] Using {device} device")
    print(f"[run] 加载 tokenizer: {ESM2_TOKENIZER}")
    tokenizer = AutoTokenizer.from_pretrained(ESM2_TOKENIZER)
    print(f"[run] 加载 model: {TRANSHLA_MODEL}（trust_remote_code=True）")
    model = AutoModel.from_pretrained(TRANSHLA_MODEL, trust_remote_code=True)
    model.to(device)
    model.eval()

    # --- 分批推理 ---
    probs: list[float] = []
    labels: list[int] = []
    n = len(peptides)
    with torch.no_grad():
        for start in range(0, n, batch_size):
            batch = peptides[start:start + batch_size]
            # 编码 + pad 到 16（照抄官方）
            enc = tokenizer(batch)["input_ids"]
            enc = pad_inner_lists_to_length(enc, PAD_TARGET_LEN)
            enc = torch.tensor(enc)
            Result, _ = model(enc.to(device))           # Result: [B, 2] 概率
            Result = Result.detach().cpu()
            prob = Result[:, 1]                          # 第 2 列 = 表位概率（class 1）
            _, predicted = torch.max(Result, 1)          # argmax → 0/1 标签
            probs.extend(np.asarray(prob).tolist())
            labels.extend(np.asarray(predicted).tolist())
            print(f"[run] 已处理 {min(start + batch_size, n)}/{n}")

    # --- 写出 ---
    out_df = pd.DataFrame({
        "peptide": peptides,
        "prob": probs,
        "label": labels,
    })
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(output_csv, index=False, encoding="utf-8", lineterminator="\n")
    print(f"[run] 写出 {len(out_df)} 行 → {output_csv}")
    print("[run] 方向：prob 为「是表位」概率 [0-1]，越高越强（免疫原方向正确，无需翻转）。")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="TransHLA_I 推理（HLA-agnostic，输出表位概率 + 0/1 标签）"
    )
    parser.add_argument(
        "--input-csv",
        default=str(DEFAULT_INPUT_CSV),
        help="transhla_input.csv 路径（prep_input.py 生成；单列 peptide）",
    )
    parser.add_argument(
        "--output-csv",
        default=str(DEFAULT_OUTPUT_CSV),
        help="transhla_raw.csv 输出路径（peptide, prob, label）",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH,
        help=f"推理 batch 大小（默认 {DEFAULT_BATCH}，官方值）",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        default=0,
        metavar="N",
        help="烟测模式：只推理前 N 个肽（建议 N=1~5，0=关闭）",
    )
    args = parser.parse_args()

    input_csv  = pathlib.Path(args.input_csv)
    output_csv = pathlib.Path(args.output_csv)

    if not input_csv.exists():
        print(f"[run] ERROR: 输入文件不存在: {input_csv}", file=sys.stderr)
        print("  请先运行: python prep_input.py", file=sys.stderr)
        sys.exit(1)

    run(input_csv, output_csv, batch_size=args.batch_size, smoke=args.smoke)


if __name__ == "__main__":
    main()
