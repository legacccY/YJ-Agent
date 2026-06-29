"""
run_munis.py — QuantImmuBench §工具部署  MUNIS MHC-I 免疫原性预测
服务项目：quantimmu-bench §工具部署 免疫原侧 lever=补满到 20（强补位 MUNIS）

功能：
  1. 读 munis_input.csv（prep_input.py 输出，列：pep, mhc, left, right, HLA_Allele, source）
  2. 二次过滤：剔除 mhc 不在 MUNIS SEQUENCES 字典内的行（避免官方 predict.py KeyError 崩整批），
     写 munis_unsupported_allele.csv（peptide, HLA_Allele, reason=allele_not_in_SEQUENCES）
  3. 把支持行写成临时 CSV（pep, mhc, left, right, HLA_Allele），
     调官方 predict.py（subprocess，零改动官方推理逻辑）：
        python predict.py --peptides <tmp_in> --outdir <tmp_out> --cache <cache> --device <dev>
     —— 不传 --use_flanks ⇒ 用 models/no-flanks/model{1-5}.ckpt ensemble，
        官方把 left/right 覆盖为 "GGGGG"（本部署无 flanking，详见 NOTES.md §flanking）。
  4. 读回官方输出 <tmp_in_stem>_munis_predictions.csv（列含 pep, mhc, left, right, score,
     HLA_Allele 穿透），抽 pep / HLA_Allele(原始带星号) / score → 写 munis_raw.csv。
  5. --smoke N: 用 N 个已知肽 × HLA-A*02:01 跑官方 predict.py 快速验证 API/列结构（需权重）。

为何 subprocess 调官方 predict.py（而非重写推理）：
  MUNIS 推理含 5 模型 ensemble + ESM-2(esm2_t6_8M_UR50D) hub 下载 + 自定义 PredictionDataset
  编码（[cls] mhc_pseudo [mask] pep [eos] + flank LSTM 分支）。直接调官方入口 = 零 API 臆造、
  零复现偏离（复现红线）。官方 predict.py 保留输入 CSV 所有列到输出，故 HLA_Allele 穿透回贴。

输入：
  HPC/deploy/munis/munis_input.csv  （prep_input.py 生成）
  --munis-repo: 解压后的 Zenodo munis-v1.0.0 目录（含 predict.py + models/；见 NOTES.md）

输出：
  HPC/deploy/munis/munis_raw.csv               （peptide, HLA_Allele, score）
  HPC/deploy/munis/munis_unsupported_allele.csv（allele 不在 SEQUENCES 的行）

官方源（2026-06-29 核自 github.com/jwohlwend/munis main predict.py + munis/model.py + seqs.py）：
  - score = sigmoid(ensemble logits).mean(over 5 models) ∈ [0,1]（predict.py::predict）。
    EL（eluted-ligand presentation）概率，越高越可能呈递/免疫原 → 越高越强，parse 不翻转。
  - 输出 CSV 列：mhc, pep, left, right, score（+ 穿透的输入额外列）。
  - 权重：models/no-flanks/model{1..5}.ckpt（默认 ensemble，no-flanks 模式）。
  - ESM-2 backbone：esm2_t6_8M_UR50D（8M，torch.hub 下载到 --cache）。

部署环境：torch==2.3.1 / fair-esm==2.0.0 / pytorch-lightning==2.0.2（见 munis requirements.txt）。
  建议 Linux/WSL2 + GPU（CPU 兜底，8M ESM 小，example <5min CPU）。
  本脚本自动 device=cuda（可用）否则 cpu。

用法：
  # 烟测（需先解压 Zenodo 权重到 --munis-repo）
  python run_munis.py --munis-repo /path/to/munis-v1.0.0 --smoke 5
  # 全量
  python prep_input.py
  python run_munis.py --munis-repo /path/to/munis-v1.0.0
"""

import argparse
import os
import pathlib
import subprocess
import sys
import tempfile

import pandas as pd

# ---------------------------------------------------------------------------
# 路径默认值
# ---------------------------------------------------------------------------
SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_INPUT = SCRIPT_DIR / "munis_input.csv"
DEFAULT_RAW = SCRIPT_DIR / "munis_raw.csv"
DEFAULT_UNSUP_ALLELE = SCRIPT_DIR / "munis_unsupported_allele.csv"
DEFAULT_CACHE = SCRIPT_DIR / "esm_cache"

# 烟测用 5 个标准肽（HLA-A*02:01，pMHC-I 经典验证集）
SMOKE_PEPTIDES = ["SIINFEKL", "NLVPMVATV", "GILGFVFTL", "KLGGALQAK", "YVLDHLIVV"]
SMOKE_HLA = "HLA-A*02:01"          # 原始带星号格式（universe 风格）


# ---------------------------------------------------------------------------
# HLA 归一（镜像官方 predict.py::clean_mhc_name，与 prep_input.py 一致）
# ---------------------------------------------------------------------------

def clean_mhc_name(mhc: str) -> str:
    mhc = mhc.replace("*", "")
    if len(mhc.split(":")) > 1:
        mhc = ":".join(mhc.split(":")[:2])
    return mhc


# ---------------------------------------------------------------------------
# 载入 MUNIS SEQUENCES 字典（用于 allele 二次过滤）
# ---------------------------------------------------------------------------

def load_sequences(munis_repo: pathlib.Path):
    """
    import munis.seqs.SEQUENCES。优先用已 pip install 的 munis；
    否则把 munis_repo 加进 sys.path 再 import（解压目录内含 munis/ 包）。
    """
    try:
        from munis.seqs import SEQUENCES  # noqa: E402
        return SEQUENCES
    except Exception:
        pass
    if munis_repo is not None and munis_repo.exists():
        sys.path.insert(0, str(munis_repo))
        try:
            from munis.seqs import SEQUENCES  # noqa: E402
            return SEQUENCES
        except Exception as exc:
            print(f"[run_munis] ERROR: 无法从 {munis_repo} import munis.seqs: {exc}", file=sys.stderr)
    print("[run_munis] ERROR: 找不到 munis 包。请先解压 Zenodo 权重并 `pip install .`，"
          "或用 --munis-repo 指向解压目录。", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# 调官方 predict.py（subprocess）
# ---------------------------------------------------------------------------

def call_official_predict(
    munis_repo: pathlib.Path,
    in_df: pd.DataFrame,
    cache_dir: pathlib.Path,
    device: str,
    batch_size: int,
    use_flanks: bool,
) -> pd.DataFrame:
    """
    把 in_df（含 pep, mhc, left, right, HLA_Allele）写临时 CSV，调官方 predict.py，
    读回 <stem>_munis_predictions.csv 返回带 score 的 DataFrame。
    """
    predict_py = munis_repo / "predict.py"
    if not predict_py.exists():
        print(f"[run_munis] ERROR: 找不到官方 predict.py: {predict_py}", file=sys.stderr)
        print("  请确认 --munis-repo 指向解压后的 Zenodo munis-v1.0.0 目录。", file=sys.stderr)
        sys.exit(1)

    tmp_dir = pathlib.Path(tempfile.mkdtemp(prefix="munis_"))
    tmp_in = tmp_dir / "munis_batch.csv"
    out_dir = tmp_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 官方要求 pep/mhc/left/right 列；额外列（HLA_Allele）会被原样保留到输出
    in_df.to_csv(tmp_in, index=False, encoding="utf-8")

    cmd = [
        sys.executable, "predict.py",
        "--peptides", str(tmp_in),
        "--outdir", str(out_dir),
        "--cache", str(cache_dir),
        "--device", device,
        "--batch_size", str(batch_size),
    ]
    if use_flanks:
        cmd.append("--use_flanks")

    print(f"[run_munis] 调官方 predict.py（cwd={munis_repo}）:")
    print("  " + " ".join(cmd))
    # cwd=munis_repo 使 models/no-flanks/*.ckpt 相对路径可解析
    subprocess.run(cmd, cwd=str(munis_repo), check=True)

    # 官方输出名：<input stem>_munis_predictions.csv
    out_csv = out_dir / (tmp_in.stem + "_munis_predictions.csv")
    if not out_csv.exists():
        print(f"[run_munis] ERROR: 官方输出未生成: {out_csv}", file=sys.stderr)
        sys.exit(1)

    pred = pd.read_csv(out_csv)
    if "score" not in pred.columns:
        print(f"[run_munis] ERROR: 官方输出缺 'score' 列，实际: {list(pred.columns)}", file=sys.stderr)
        sys.exit(1)
    return pred


# ---------------------------------------------------------------------------
# 烟测
# ---------------------------------------------------------------------------

def run_smoke(munis_repo, cache_dir, device, batch_size, use_flanks, n: int) -> None:
    smoke_peps = SMOKE_PEPTIDES[:n]
    mhc = clean_mhc_name(SMOKE_HLA)
    print(f"\n[smoke] 烟测 {len(smoke_peps)} 肽 × allele={SMOKE_HLA} (→{mhc})")
    df = pd.DataFrame({
        "pep": smoke_peps,
        "mhc": [mhc] * len(smoke_peps),
        "left": [""] * len(smoke_peps),
        "right": [""] * len(smoke_peps),
        "HLA_Allele": [SMOKE_HLA] * len(smoke_peps),
    })
    pred = call_official_predict(munis_repo, df, cache_dir, device, batch_size, use_flanks)
    print("[smoke] 官方输出 DataFrame:")
    print(pred.to_string(index=False))
    print(f"\n[smoke] 列名: {list(pred.columns)}")
    print("[smoke] 烟测通过：score ∈ [0,1]（越高越强）有值即 OK。")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="MUNIS MHC-I 免疫原性预测（subprocess 调官方 predict.py，no-flanks ensemble）"
    )
    parser.add_argument(
        "--munis-repo",
        required=True,
        help="解压后的 Zenodo munis-v1.0.0 目录（含 predict.py + models/no-flanks/*.ckpt）",
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="munis_input.csv 路径（prep_input.py 生成）",
    )
    parser.add_argument(
        "--raw-out",
        default=str(DEFAULT_RAW),
        help="原始预测结果输出路径（默认 munis_raw.csv）",
    )
    parser.add_argument(
        "--cache",
        default=str(DEFAULT_CACHE),
        help="ESM-2 权重 torch.hub 缓存目录（首次自动下载 esm2_t6_8M_UR50D）",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="推理设备（默认 cuda 可用则 cuda 否则 cpu）",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="推理 batch 大小（默认 32，官方默认值）",
    )
    parser.add_argument(
        "--use-flanks",
        action="store_true",
        help="传 --use_flanks 给官方（用 flanks ensemble）。本部署无 flanking，默认关闭。",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        metavar="N",
        default=0,
        help="烟测模式：N 个已知肽验证官方 API（N=0=关闭）",
    )
    args = parser.parse_args()

    munis_repo = pathlib.Path(args.munis_repo).resolve()
    cache_dir = pathlib.Path(args.cache).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)

    # 设备：GPU 优先 CPU 兜底
    device = args.device
    if device is None:
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            device = "cpu"
    print(f"[run_munis] device = {device}")

    # --- 烟测分支 ---
    if args.smoke > 0:
        run_smoke(munis_repo, cache_dir, device, args.batch_size, args.use_flanks, args.smoke)
        return

    # --- 全量预测 ---
    input_path = pathlib.Path(args.input)
    if not input_path.exists():
        print(f"[run_munis] ERROR: 输入文件不存在: {input_path}", file=sys.stderr)
        print("  请先运行: python prep_input.py", file=sys.stderr)
        sys.exit(1)

    df_input = pd.read_csv(input_path, dtype=str, encoding="utf-8").fillna("")
    print(f"[run_munis] 读入 {len(df_input)} 行 from {input_path}")
    for col in ["pep", "mhc", "left", "right", "HLA_Allele"]:
        if col not in df_input.columns:
            print(f"[run_munis] ERROR: 输入缺列 '{col}'，实际: {list(df_input.columns)}", file=sys.stderr)
            sys.exit(1)

    # --- allele 二次过滤（mhc 必须在 SEQUENCES 字典内）---
    SEQUENCES = load_sequences(munis_repo)
    supported_mask = df_input["mhc"].isin(set(SEQUENCES.keys()))
    df_sup = df_input[supported_mask].copy()
    df_unsup = df_input[~supported_mask].copy()

    if len(df_unsup) > 0:
        unsup_out = DEFAULT_UNSUP_ALLELE
        out = df_unsup[["pep", "HLA_Allele"]].rename(columns={"pep": "peptide"})
        out["reason"] = "allele_not_in_SEQUENCES"
        out.to_csv(unsup_out, index=False, encoding="utf-8", lineterminator="\n")
        print(f"[run_munis] {len(df_unsup)} 行 allele 不在 SEQUENCES → {unsup_out}（parse 阶段 NaN）")

    if len(df_sup) == 0:
        print("[run_munis] ERROR: 无任何受支持 allele 行可预测。", file=sys.stderr)
        sys.exit(1)
    print(f"[run_munis] 受支持行 {len(df_sup)}（{df_sup['mhc'].nunique()} 个 allele）→ 官方推理")

    # --- 调官方 predict.py ---
    feed = df_sup[["pep", "mhc", "left", "right", "HLA_Allele"]].copy()
    pred = call_official_predict(
        munis_repo, feed, cache_dir, device, args.batch_size, args.use_flanks
    )

    # --- 抽列写 raw（peptide=pep, HLA_Allele=原始带星号, score）---
    raw = pd.DataFrame({
        "peptide": pred["pep"].astype(str).str.strip(),
        "HLA_Allele": pred["HLA_Allele"].astype(str).str.strip(),
        "score": pred["score"],
    })

    raw_out = pathlib.Path(args.raw_out)
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    raw.to_csv(raw_out, index=False, encoding="utf-8", lineterminator="\n")

    print(f"\n[run_munis] 完成。写入 {len(raw)} 行 → {raw_out}")
    print(f"[run_munis] 列: {list(raw.columns)}")
    sc = pd.to_numeric(raw["score"], errors="coerce").dropna()
    if len(sc):
        print(f"[run_munis] score ∈[0,1] 统计: min={sc.min():.4f}  max={sc.max():.4f}  median={sc.median():.4f}")
    print("[run_munis] 方向：score 为 EL 呈递概率 [0-1]，越高越强；parse_output.py 直接用，无需翻转。")


if __name__ == "__main__":
    main()
