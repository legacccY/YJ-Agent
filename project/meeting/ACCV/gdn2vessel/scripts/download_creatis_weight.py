#!/usr/bin/env python3
"""
download_creatis_weight.py — 下载 creatis Stage-2 官方预训 reconnecting 权重。

用途:
  gdn2vessel L3 baseline `creatis_postproc`（两段式后处理）Stage-2 需要官方
  预训 monai UNet 权重 best_metric_model.pth（STARE 上训练的 2D reconnecting
  模型）。本脚本从官方 GitHub raw 直接下载到本地/HPC，并做完整性校验。

⚠️ 授权与再分发:
  官方 repo `creatis-myriad/plug-and-play-reco-regularization` 根目录**无 LICENSE
  文件**（= 保留所有权利，README/vendor 注 CeCILL 但正式 license 文件缺失）。
  因此**不把权重再分发进本 repo**：本脚本从官方 URL 现下载，权重文件本身经
  .gitignore（`*.pth` + models/creatis/）排除，不进 git。
  发表时须引用:
    [1] Carneiro-Esteves et al., "Restoring Vessel Connectivity ...",
        Neurocomputing 2024 (arXiv:2404.10506)
    [2] Carneiro-Esteves et al., TGI3 MICCAI Workshop 2024 (arXiv:2408.12943)

官方权重信息（researcher 核实，2026-06-xx）:
  URL   : https://raw.githubusercontent.com/creatis-myriad/
          plug-and-play-reco-regularization/main/modeles/2D_model_stare/
          best_metric_model.pth
  size  : 1657821 字节（硬校验；不符即失败）
  gitsha: 8d93daa307dd8c6e903c8ab970ac5af3863cb9bf（git blob sha1，交叉校验）
  架构  : monai UNet(spatial_dims=2, in_ch=1, out_ch=1,
          channels=(16,32,64,128), strides=(2,2,2), num_res_units=2, norm='batch')

同目录 config_training.json（含 norm 字段，evaluate.py 会读取以精确匹配权重）
也一并下载。

用法（主线跑，本 coder 不跑）:
  python scripts/download_creatis_weight.py
  python scripts/download_creatis_weight.py --dest /path/to/best_metric_model.pth
  # HPC 上（gdn2venv 需先 pip install monai）:
  python scripts/download_creatis_weight.py \
      --dest $HPC_PROJECT_ROOT/models/creatis/2D_model_stare/best_metric_model.pth
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

# --------------------------------------------------------------------------- #
#  官方常量（researcher 核实，勿改）
# --------------------------------------------------------------------------- #

_RAW_BASE = (
    "https://raw.githubusercontent.com/creatis-myriad/"
    "plug-and-play-reco-regularization/main/modeles/2D_model_stare"
)
WEIGHT_URL = f"{_RAW_BASE}/best_metric_model.pth"
CONFIG_URL = f"{_RAW_BASE}/config_training.json"

EXPECTED_SIZE = 1657821  # 字节，硬校验
EXPECTED_GIT_BLOB_SHA1 = "8d93daa307dd8c6e903c8ab970ac5af3863cb9bf"

# 默认落地路径：<gdn2vessel>/models/creatis/2D_model_stare/best_metric_model.pth
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DEST = (
    _PROJECT_ROOT / "models" / "creatis" / "2D_model_stare" / "best_metric_model.pth"
)


# --------------------------------------------------------------------------- #
#  helpers
# --------------------------------------------------------------------------- #

def _download(url: str, dest: Path) -> None:
    """下载 url 到 dest（覆盖）。用 stdlib urllib，无第三方依赖。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"[download] GET {url}")
    print(f"[download]  -> {dest}")
    req = urllib.request.Request(url, headers={"User-Agent": "gdn2vessel-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    dest.write_bytes(data)
    print(f"[download] wrote {len(data)} bytes")


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _git_blob_sha1_of(path: Path) -> str:
    """计算 git blob sha1 = sha1('blob <len>\\0' + content)，用于对官方 blob sha 交叉校验。"""
    content = path.read_bytes()
    header = f"blob {len(content)}\0".encode("ascii")
    h = hashlib.sha1()
    h.update(header)
    h.update(content)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
#  main
# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Download creatis Stage-2 official reconnecting weight (STARE).",
    )
    ap.add_argument(
        "--dest",
        type=Path,
        default=_DEFAULT_DEST,
        help=(
            "best_metric_model.pth 落地路径（默认 "
            "<gdn2vessel>/models/creatis/2D_model_stare/best_metric_model.pth）。"
            "config_training.json 会下载到同目录。"
        ),
    )
    ap.add_argument(
        "--skip-config",
        action="store_true",
        help="只下权重，不下 config_training.json（不推荐；config 供 norm 精确匹配）。",
    )
    ap.add_argument(
        "--no-verify",
        action="store_true",
        help="跳过 size / git-blob-sha1 校验（不推荐，仅调试用）。",
    )
    args = ap.parse_args()

    dest_weight: Path = args.dest
    dest_config: Path = dest_weight.parent / "config_training.json"

    # ------------------------------------------------------------------ #
    #  1. 下载权重
    # ------------------------------------------------------------------ #
    try:
        _download(WEIGHT_URL, dest_weight)
    except Exception as e:
        print(f"[download] ERROR 下载权重失败: {e}", file=sys.stderr)
        return 1

    # ------------------------------------------------------------------ #
    #  2. 校验 size + git blob sha1 + 打印 sha256 存档
    # ------------------------------------------------------------------ #
    actual_size = dest_weight.stat().st_size
    sha256 = _sha256_of(dest_weight)
    git_sha1 = _git_blob_sha1_of(dest_weight)

    print("")
    print("[verify] best_metric_model.pth")
    print(f"[verify]   size (bytes) : {actual_size}  (expected {EXPECTED_SIZE})")
    print(f"[verify]   git blob sha1: {git_sha1}")
    print(f"[verify]   expected sha1: {EXPECTED_GIT_BLOB_SHA1}")
    print(f"[verify]   sha256       : {sha256}   <-- 存档此值")

    if not args.no_verify:
        ok_size = actual_size == EXPECTED_SIZE
        ok_sha1 = git_sha1 == EXPECTED_GIT_BLOB_SHA1
        if not ok_size:
            print(
                f"[verify] FAIL: size {actual_size} != expected {EXPECTED_SIZE}. "
                "下载可能损坏/被重定向到 HTML，请重试或核 URL。",
                file=sys.stderr,
            )
            return 2
        if not ok_sha1:
            print(
                f"[verify] FAIL: git blob sha1 {git_sha1} != expected "
                f"{EXPECTED_GIT_BLOB_SHA1}。官方权重内容可能已变更，"
                "请核 researcher 记录的 blob sha。",
                file=sys.stderr,
            )
            return 3
        print("[verify] PASS: size + git blob sha1 均匹配官方 ✅")

    # ------------------------------------------------------------------ #
    #  3. 下载 config_training.json（供 evaluate.py 读 norm）
    # ------------------------------------------------------------------ #
    if not args.skip_config:
        try:
            _download(CONFIG_URL, dest_config)
            print(f"[download] config_training.json -> {dest_config}")
        except Exception as e:
            print(
                f"[download] WARN 下载 config_training.json 失败: {e}\n"
                "  evaluate.py 会 fallback norm='batch'（官方默认，researcher 核实），"
                "  通常仍可正确加载权重。",
                file=sys.stderr,
            )

    print("")
    print("[done] creatis Stage-2 权重就绪。")
    print(f"[done] 权重: {dest_weight}")
    print(
        "[done] 引用 [1] Neurocomputing 2024 (arXiv:2404.10506) "
        "+ [2] TGI3 MICCAI 2024 (arXiv:2408.12943)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
