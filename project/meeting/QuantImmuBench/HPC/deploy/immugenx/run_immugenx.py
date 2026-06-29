"""
run_immugenx.py — QuantImmuBench §工具部署  ImmugenX 免疫原性预测
服务项目：quantimmu-bench §工具部署 免疫原侧 lever=补满到 20（I20 = ImmugenX）

功能：
  1. 读 immugenx_input.csv（prep_input.py 输出，列：Antigen, HLA, HLA_Allele, source）
  2. 精过滤未知 allele：读 RUNNER_REPO 的 class1_pseudosequences.csv 建支持 allele 集合
     （镜像官方 HLAEncoder._populate_pseudoseq_library + _fetch_hla 的解析逻辑），
     剔除不可解析行到 immugenx_unsupported_allele.csv，避免官方 _fetch_hla 抛 ValueError 崩整批。
  3. 把支持行写成临时 CSV（Antigen, HLA, HLA_Allele, source），
     subprocess 调官方 cli（零改动官方推理逻辑）：
        python immugenx_runner/cli.py -c <config> -i <tmp_in> -o <tmp_out>
     —— cwd=RUNNER_REPO（关键：cli 内部按 models/<id>_jit.pt 相对路径加载，cwd 错则找不到）；
     —— env CUDA_VISIBLE_DEVICES=""（强制 CPU；本机 GPU 被主窗占，节点铁律不抢；
        官方 jit_runner `torch.cuda.is_available()` 据此回 False → CPU）。
  4. 读回官方输出 CSV（含 Antigen, HLA, HLA_Allele, source, ImmugenX, Stability 列）→
     抽 peptide=Antigen / HLA_Allele(原始带星号) / ImmugenX / Stability → 写 immugenx_raw.csv。
  5. --smoke N: 用 N 个已知肽 × HLA-A*02:01 跑官方 cli 快速验证 API/列结构（需 JIT 权重）。

为何 subprocess 调官方 cli（而非重写推理）：
  ImmugenX = 自包含 TorchScript JIT 模型 + 自定义 token 编码 + mhcnames HLA 伪序列查表。
  直接调官方入口 cli.py = 零 API 臆造、零复现偏离（复现红线）。
  runner.py _run_and_save 保留输入 CSV 所有列到输出，故 HLA_Allele/source 穿透回贴。

输入：
  HPC/deploy/immugenx/immugenx_input.csv  （prep_input.py 生成）
  --runner-repo: 解包后的 zenodo immugenx_runner_pub 目录（含 immugenx_runner/cli.py + models/）

输出：
  HPC/deploy/immugenx/immugenx_raw.csv               （peptide, HLA_Allele, ImmugenX, Stability）
  HPC/deploy/immugenx/immugenx_unsupported_allele.csv（allele 不在库的行）

官方源（2026-06-29 核自亲手解包 immugenx_runner_pub）：
  - cli.py：`-c <config> -i <input.csv> -o <output.csv> [-v]`。
  - configs/genesis_pub_config.json：ImmugenX + Stability 两模型（README 写的
    immugenx_pub_config.json 不存在，实际文件名是 genesis_pub_config.json）。
  - immugenx_jit_runner.run_model：`torch.sigmoid(pred)` → score ∈ [0,1]，越高越免疫原（不翻转）。
  - encoders.HLAEncoder._fetch_hla：mhcnames.normalize_allele_name + CW→C + 4 处 02 订正 +
    <8 自动补 ':01'；解析后不在 library 抛 `ValueError(hla + " invalid HLA lookup attempted")`。

部署环境：python=3.9 / pytorch=1.12.0 / pandas=1.3.4 / numpy==1.23.3 / mhcnames==0.4.8 /
  biopython==1.78（见 environment.yml）。纯 CPU 可跑、无外部 binary 依赖（不调 netMHCpan）。

用法：
  # 烟测（需先 conda env create environment.yml 装好依赖 + JIT 权重在 models/）
  python run_immugenx.py --smoke 5
  # 全量
  python prep_input.py
  python run_immugenx.py
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

DEFAULT_RUNNER_REPO = SCRIPT_DIR / "zenodo" / "immugenx_runner_pub"
DEFAULT_INPUT = SCRIPT_DIR / "immugenx_input.csv"
DEFAULT_RAW = SCRIPT_DIR / "immugenx_raw.csv"
DEFAULT_UNSUP_ALLELE = SCRIPT_DIR / "immugenx_unsupported_allele.csv"

# 官方 cli 输出的分数列名（核自 config: name=ImmugenX / Stability）
COL_IMMUGENX = "ImmugenX"
COL_STABILITY = "Stability"

# 官方 HLA 订正映射（镜像 encoders.HLAEncoder._fetch_hla，mhcnames normalize 后的形态）
HLA_CORRECTIONS = {
    "HLA-B*07:01": "HLA-B*07:02",
    "HLA-A*24:01": "HLA-A*24:02",
    "HLA-B*44:01": "HLA-B*44:02",
    "HLA-C*06:01": "HLA-C*06:02",
}

# 烟测用 5 个标准肽（HLA-A*02:01，pMHC-I 经典验证集）
SMOKE_PEPTIDES = ["SIINFEKL", "NLVPMVATV", "GILGFVFTL", "KLGGALQAK", "YVLDHLIVV"]
SMOKE_HLA = "HLA-A*02:01"          # 原始带星号格式（universe 风格）


# ---------------------------------------------------------------------------
# mhcnames 归一（优先用官方依赖；无则降级字符串规整，标 TODO）
# ---------------------------------------------------------------------------

def _build_normalizer():
    """
    返回 (normalize_fn, have_mhcnames)。
    have_mhcnames=True：用 mhcnames.normalize_allele_name（与官方 encoders.py 完全一致）。
    False：降级为字符串规整（去 'HLA-'/'*'/':' 大写）—— TODO: 仅近似，缺 mhcnames 的
           特殊订正/自动补全细节；真实运行环境（environment.yml）含 mhcnames，走精确路径。
    """
    try:
        import mhcnames

        def _norm(a: str) -> str:
            return mhcnames.normalize_allele_name(a)

        return _norm, True
    except Exception:
        # TODO: 未装 mhcnames（静态/无 env 时）。降级近似归一，仅供静态过；
        #       正式运行务必在 immugenx conda env（含 mhcnames==0.4.8）内执行。
        def _norm(a: str) -> str:
            return a.upper().replace("HLA-", "").replace("*", "").replace(":", "").strip()

        return _norm, False


# ---------------------------------------------------------------------------
# 载入支持 allele 集合 + 解析（镜像官方 HLAEncoder）
# ---------------------------------------------------------------------------

def load_supported_alleles(runner_repo: pathlib.Path, normalize) -> set:
    """
    读 RUNNER_REPO/immugenx_runner/libraries/HLA/class1_pseudosequences.csv，
    镜像 HLAEncoder._populate_pseudoseq_library 过滤（'HLA' in allele 且末位非字母）+ normalize，
    返回支持 allele 归一名集合。
    """
    lib_path = (
        runner_repo / "immugenx_runner" / "libraries" / "HLA" / "class1_pseudosequences.csv"
    )
    if not lib_path.exists():
        print(f"[run_immugenx] ERROR: 找不到 pseudosequence 库: {lib_path}", file=sys.stderr)
        sys.exit(1)

    lib = pd.read_csv(lib_path)
    keys = set()
    for _, row in lib.iterrows():
        allele = str(row["allele"])
        if "HLA" not in allele:
            continue
        if allele[-1].isalpha():
            continue
        try:
            keys.add(normalize(allele))
        except Exception:
            continue
    print(f"[run_immugenx] class1_pseudosequences 支持 HLA allele: {len(keys)} 个")
    return keys


def resolve_allele(hla: str, lib_keys: set, normalize):
    """
    镜像 HLAEncoder._fetch_hla 的解析：判定该 allele 是否能在库里命中（否则官方会 ValueError 崩批）。
    返回命中的归一键；不可解析返回 None。
    """
    h = hla
    # 截 suffix（>2 字段保留前 2）
    if len(h.split(":")) > 2:
        h = ":".join(h.split(":")[:2])
    try:
        h = normalize(h)
    except Exception:
        return None
    h = h.replace("CW", "C")
    h = HLA_CORRECTIONS.get(h, h)
    if h in lib_keys:
        return h
    # 官方对 <8 的不完整 HLA 自动补 ':01'
    if len(h) < 8 and (h + ":01") in lib_keys:
        return h + ":01"
    return None


# ---------------------------------------------------------------------------
# 调官方 cli.py（subprocess）
# ---------------------------------------------------------------------------

def call_official_cli(
    runner_repo: pathlib.Path,
    config_path: pathlib.Path,
    in_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    把 in_df（含 Antigen, HLA, HLA_Allele, source）写临时 CSV，subprocess 调官方 cli.py
    （cwd=runner_repo + CUDA_VISIBLE_DEVICES="" 强制 CPU），读回输出 DataFrame。
    """
    cli_py = runner_repo / "immugenx_runner" / "cli.py"
    if not cli_py.exists():
        print(f"[run_immugenx] ERROR: 找不到官方 cli.py: {cli_py}", file=sys.stderr)
        print("  请确认 --runner-repo 指向解包后的 immugenx_runner_pub 目录。", file=sys.stderr)
        sys.exit(1)
    if not config_path.exists():
        print(f"[run_immugenx] ERROR: 找不到 config: {config_path}", file=sys.stderr)
        sys.exit(1)

    tmp_dir = pathlib.Path(tempfile.mkdtemp(prefix="immugenx_"))
    tmp_in = tmp_dir / "immugenx_batch.csv"
    tmp_out = tmp_dir / "immugenx_batch_out.csv"

    # 官方要求 Antigen/HLA 列；额外列（HLA_Allele/source）原样保留到输出
    in_df.to_csv(tmp_in, index=False, encoding="utf-8")

    cmd = [
        sys.executable, "immugenx_runner/cli.py",
        "-c", str(config_path.resolve()),
        "-i", str(tmp_in.resolve()),
        "-o", str(tmp_out.resolve()),
    ]

    # 强制 CPU：清空 CUDA_VISIBLE_DEVICES（不抢主窗 GPU）
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = ""

    print(f"[run_immugenx] 调官方 cli.py（cwd={runner_repo}，CUDA_VISIBLE_DEVICES=\"\"）:")
    print("  " + " ".join(cmd))
    # cwd=runner_repo 使 models/<id>_jit.pt 相对路径可解析
    subprocess.run(cmd, cwd=str(runner_repo), env=env, check=True)

    if not tmp_out.exists():
        print(f"[run_immugenx] ERROR: 官方输出未生成: {tmp_out}", file=sys.stderr)
        sys.exit(1)

    pred = pd.read_csv(tmp_out)
    # 官方 to_csv 默认带索引列 → 丢掉 Unnamed:*
    pred = pred[pred.columns.drop(list(pred.filter(regex="Unnamed:")))]
    for col in (COL_IMMUGENX,):
        if col not in pred.columns:
            print(f"[run_immugenx] ERROR: 官方输出缺 '{col}' 列，实际: {list(pred.columns)}",
                  file=sys.stderr)
            sys.exit(1)
    return pred


# ---------------------------------------------------------------------------
# 烟测
# ---------------------------------------------------------------------------

def run_smoke(runner_repo, config_path, n: int) -> None:
    smoke_peps = SMOKE_PEPTIDES[:n]
    print(f"\n[smoke] 烟测 {len(smoke_peps)} 肽 × allele={SMOKE_HLA}")
    df = pd.DataFrame({
        "Antigen": smoke_peps,
        "HLA": [SMOKE_HLA] * len(smoke_peps),
        "HLA_Allele": [SMOKE_HLA] * len(smoke_peps),
        "source": ["smoke"] * len(smoke_peps),
    })
    pred = call_official_cli(runner_repo, config_path, df)
    print("[smoke] 官方输出 DataFrame:")
    print(pred.to_string(index=False))
    print(f"\n[smoke] 列名: {list(pred.columns)}")
    print("[smoke] 烟测通过：ImmugenX ∈ [0,1]（越高越强）有值即 OK。")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ImmugenX MHC-I 免疫原性预测（subprocess 调官方 cli.py，CPU 强制）"
    )
    parser.add_argument(
        "--runner-repo",
        default=str(DEFAULT_RUNNER_REPO),
        help="解包后的 immugenx_runner_pub 目录（含 immugenx_runner/cli.py + models/）",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="config json（默认 <runner-repo>/configs/genesis_pub_config.json）",
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="immugenx_input.csv 路径（prep_input.py 生成）",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_RAW),
        help="原始预测结果输出路径（默认 immugenx_raw.csv）",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        metavar="N",
        default=0,
        help="烟测模式：N 个已知肽验证官方 API（N=0=关闭）",
    )
    args = parser.parse_args()

    runner_repo = pathlib.Path(args.runner_repo).resolve()
    config_path = (
        pathlib.Path(args.config).resolve()
        if args.config
        else runner_repo / "configs" / "genesis_pub_config.json"
    )

    normalize, have_mhcnames = _build_normalizer()
    if not have_mhcnames:
        print("[run_immugenx] WARN: 未装 mhcnames，allele 精过滤用降级字符串归一（仅近似）。"
              "正式运行请在 immugenx conda env 内执行。", file=sys.stderr)

    # --- 烟测分支 ---
    if args.smoke > 0:
        run_smoke(runner_repo, config_path, args.smoke)
        return

    # --- 全量预测 ---
    input_path = pathlib.Path(args.input)
    if not input_path.exists():
        print(f"[run_immugenx] ERROR: 输入文件不存在: {input_path}", file=sys.stderr)
        print("  请先运行: python prep_input.py", file=sys.stderr)
        sys.exit(1)

    df_input = pd.read_csv(input_path, dtype=str, encoding="utf-8").fillna("")
    print(f"[run_immugenx] 读入 {len(df_input)} 行 from {input_path}")
    for col in ["Antigen", "HLA", "HLA_Allele", "source"]:
        if col not in df_input.columns:
            print(f"[run_immugenx] ERROR: 输入缺列 '{col}'，实际: {list(df_input.columns)}",
                  file=sys.stderr)
            sys.exit(1)

    # --- allele 精过滤（不可解析的剔除，避免官方 _fetch_hla ValueError 崩批）---
    lib_keys = load_supported_alleles(runner_repo, normalize)
    resolved = df_input["HLA"].apply(lambda h: resolve_allele(str(h), lib_keys, normalize))
    supported_mask = resolved.notna()
    df_sup = df_input[supported_mask].copy()
    df_unsup = df_input[~supported_mask].copy()

    if len(df_unsup) > 0:
        out = df_unsup[["Antigen", "HLA_Allele"]].rename(columns={"Antigen": "peptide"})
        out["reason"] = "allele_not_in_class1_pseudosequences"
        out.to_csv(DEFAULT_UNSUP_ALLELE, index=False, encoding="utf-8", line_terminator="\n")
        print(f"[run_immugenx] {len(df_unsup)} 行 allele 不可解析 → {DEFAULT_UNSUP_ALLELE}（parse 阶段 NaN）")

    if len(df_sup) == 0:
        print("[run_immugenx] ERROR: 无任何受支持 allele 行可预测。", file=sys.stderr)
        sys.exit(1)
    print(f"[run_immugenx] 受支持行 {len(df_sup)}（{df_sup['HLA'].nunique()} 个 allele）→ 官方推理")

    # --- 调官方 cli.py ---
    feed = df_sup[["Antigen", "HLA", "HLA_Allele", "source"]].copy()
    pred = call_official_cli(runner_repo, config_path, feed)

    # --- 抽列写 raw（peptide=Antigen, HLA_Allele=原始带星号, ImmugenX, Stability）---
    has_stab = COL_STABILITY in pred.columns
    raw = pd.DataFrame({
        "peptide": pred["Antigen"].astype(str).str.strip(),
        "HLA_Allele": pred["HLA_Allele"].astype(str).str.strip(),
        "ImmugenX": pred[COL_IMMUGENX],
        "Stability": pred[COL_STABILITY] if has_stab else float("nan"),
    })

    raw_out = pathlib.Path(args.out)
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    raw.to_csv(raw_out, index=False, encoding="utf-8", line_terminator="\n")

    print(f"\n[run_immugenx] 完成。写入 {len(raw)} 行 → {raw_out}")
    print(f"[run_immugenx] 列: {list(raw.columns)}")
    sc = pd.to_numeric(raw["ImmugenX"], errors="coerce").dropna()
    if len(sc):
        print(f"[run_immugenx] ImmugenX ∈[0,1] 统计: min={sc.min():.4f}  max={sc.max():.4f}  median={sc.median():.4f}")
    print("[run_immugenx] 方向：ImmugenX/Stability = sigmoid 分 [0-1]，越高越强；parse 直接用，无需翻转。")


if __name__ == "__main__":
    main()
