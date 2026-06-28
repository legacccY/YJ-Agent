# -*- coding: utf-8 -*-
"""
run_immuneapp_101102.py — Phase B：用订正 HLA 等位重推理 ImmuneApp-Neo（P101/P102）。

唯一订正输入源 = scripts/out/phaseB/backbone_101102.csv（prep_101102_subset.py 产，
已过闸门1：HLA_Allele == 订正真值 P101={A66:01,B40:01,B57:01,C06:02}/
P102={A02:01,B35:03,B38:01}）。本脚本只从这份派生，绝不读任何旧 immuneapp 输入。

自包含三步（prep+run+parse 一体），与 run_iedb_calis_101102.py 调用逻辑一致：
  1. prep：从 backbone 取 MT_Subpeptide ∪ WT_Subpeptide，按 HLA_Allele 分组去重。
     ImmuneApp 接受标准格式 HLA-A*66:01（不转换）；仅 8–15 mer + 20 标准氨基酸。
  2. run：逐 allele 写 peps.txt，调官方 ImmuneApp_immunogenicity_prediction.py。
     ImmuneApp 是 TF1.15/py3.7 Linux-only 工具（不能原生 Windows 跑）→ 经 WSL2 conda
     env `immuneapp` 调用（与 HPC envs/immuneapp 同一份依赖；WSL2 镜像 /root/quantimmu/）。
     必须 cd 到 repo 根目录（脚本用相对路径加载 ImmuneApp_weights/）。
  3. parse：读每 allele 输出 ImmuneApp_Immunogenicity_predictions.tsv
     （列 Allele/Peptide/Sample/Immunogenicity_score），(pep_upper, allele) → score，
     回贴每行 bb_idx 的 MT/WT 分数。

产出: scripts/out/phaseB/ImmuneApp_101102.csv
      列: bb_idx, MT_ImmuneApp, WT_ImmuneApp
方向: Immunogenicity_score 越高越免疫原（官方原始方向 0~1 sigmoid，无翻转）。

用法:
    python run_immuneapp_101102.py [--smoke N]
    --smoke N: 只跑前 N 个 allele 分组（验工具能跑、分数在 0~1），不产正式 CSV。

环境覆盖（路径不确定时主线用 env 改，不改代码）:
    IMMUNEAPP_REPO_WSL  ImmuneApp repo 在 WSL2 的绝对路径
    IMMUNEAPP_ENV_WSL   conda env（-p）在 WSL2 的绝对路径
    IMMUNEAPP_CONDA_SH  conda.sh 在 WSL2 的绝对路径
    WSL_DISTRO          指定 WSL 发行版（默认用 wsl 默认发行版）
"""
import argparse
import csv
import math
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # QuantImmuBench/
BACKBONE = ROOT / "scripts" / "out" / "phaseB" / "backbone_101102.csv"
WORKDIR = ROOT / "scripts" / "out" / "phaseB" / "immuneapp_work"  # per-allele in/out
OUT = ROOT / "scripts" / "out" / "phaseB" / "ImmuneApp_101102.csv"

# ── WSL2 调用配置 ──────────────────────────────────────────────────────────
# TODO（主线确认）：以下 WSL2 路径按 HPC 部署 /gpfs/work/bio/jiayu2403/quantimmu/
# 的本地镜像推断（neotimmuml verify 脚本佐证 WSL2 base=/root/quantimmu/）。
# 若实际路径不同，用上方 env 覆盖，勿改死代码。ImmuneApp.md 仅记 HPC /gpfs 部署，
# 未记 WSL2 路径——这是推断值，跑前抽 1 个 allele 烟测确认。
IMMUNEAPP_REPO_WSL = os.environ.get(
    "IMMUNEAPP_REPO_WSL", "/root/quantimmu/tools_repos/ImmuneApp")
IMMUNEAPP_ENV_WSL = os.environ.get(
    "IMMUNEAPP_ENV_WSL", "/root/quantimmu/envs/immuneapp")
# conda.sh：留空则 bash -lc 依赖 .bashrc 里 conda init 把 conda 放进 PATH
IMMUNEAPP_CONDA_SH = os.environ.get("IMMUNEAPP_CONDA_SH", "")
WSL_DISTRO = os.environ.get("WSL_DISTRO", "")  # 空 = wsl 默认发行版

TSV_NAME = "ImmuneApp_Immunogenicity_predictions.tsv"  # ImmuneApp 固定输出文件名

STD_AA = set("ACDEFGHIKLMNPQRSTVWY")  # 仅 20 标准氨基酸（read_peplist 硬验证）
MIN_LEN, MAX_LEN = 8, 15            # ImmuneApp-Neo 肽长限制 8–15 mer


def is_clean_pep(p: str) -> bool:
    return bool(p) and MIN_LEN <= len(p) <= MAX_LEN and all(c in STD_AA for c in p)


def allele_safe(h: str) -> str:
    """HLA-A*66:01 → HLA-A_66_01（* 与 : 换 _，文件/目录名安全）。"""
    return h.replace("*", "_").replace(":", "_")


def win_to_wsl(p: Path) -> str:
    """D:\\a\\b → /mnt/d/a/b（WSL2 挂载约定）。"""
    s = str(p.resolve())
    drive = s[0].lower()
    rest = s[2:].replace("\\", "/")
    return f"/mnt/{drive}{rest}"


def build_wsl_cmd(peps_wsl: str, allele_std: str, outdir_wsl: str) -> list:
    """构造 wsl bash -lc 调 ImmuneApp 的命令列表。"""
    parts = ["set -e"]
    if IMMUNEAPP_CONDA_SH:
        parts.append(f"source '{IMMUNEAPP_CONDA_SH}'")
    parts.append(f"cd '{IMMUNEAPP_REPO_WSL}'")
    # conda run -p <envpath>（与 deploy/smoke 脚本一致，避免 activate 在非交互失效）
    parts.append(
        f"conda run --no-capture-output -p '{IMMUNEAPP_ENV_WSL}' "
        f"python ImmuneApp_immunogenicity_prediction.py "
        f"-f '{peps_wsl}' -a '{allele_std}' -o '{outdir_wsl}'"
    )
    inner = " && ".join(parts)
    pre = ["wsl"]
    if WSL_DISTRO:
        pre += ["-d", WSL_DISTRO]
    return pre + ["bash", "-lc", inner]


def parse_tsv(tsv_path: Path) -> dict:
    """读 ImmuneApp 输出 tsv → {pep_upper: score}（单 allele 目录，Allele 列恒定）。"""
    scores = {}
    if not tsv_path.exists():
        return scores
    with open(tsv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        # 容错：列名可能含首尾空格
        cols = {c.strip(): c for c in (reader.fieldnames or [])}
        pep_c = cols.get("Peptide")
        sc_c = cols.get("Immunogenicity_score")
        if not pep_c or not sc_c:
            raise RuntimeError(
                f"tsv 缺列（需 Peptide/Immunogenicity_score）: {reader.fieldnames}")
        for r in reader:
            pep = (r.get(pep_c) or "").strip().upper()
            try:
                scores[pep] = float((r.get(sc_c) or "").strip())
            except ValueError:
                continue
    return scores


def score_allele(allele_std, pep_list):
    """对一个 allele 写 peps.txt + 调 ImmuneApp，返回 {pep_upper: score}。"""
    safe = allele_safe(allele_std)
    adir = WORKDIR / safe
    adir.mkdir(parents=True, exist_ok=True)
    pep_file = adir / "peps.txt"
    pep_file.write_text("\n".join(pep_list) + "\n", encoding="utf-8")  # 无 header

    peps_wsl = win_to_wsl(pep_file)
    outdir_wsl = win_to_wsl(adir)
    cmd = build_wsl_cmd(peps_wsl, allele_std, outdir_wsl)
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if res.returncode != 0:
        raise RuntimeError(
            f"{allele_std} ImmuneApp 失败 rc={res.returncode}: "
            f"{res.stderr[-300:]}{res.stdout[-300:]}")
    return parse_tsv(adir / TSV_NAME)


def main():
    ap = argparse.ArgumentParser(description="Phase B ImmuneApp-Neo 重推理 P101/P102")
    ap.add_argument("--smoke", type=int, default=0,
                    help="只跑前 N 个 allele 分组验工具，不产 CSV")
    args = ap.parse_args()

    if not BACKBONE.exists():
        raise SystemExit(f"[FAIL] 订正源不存在: {BACKBONE}")
    WORKDIR.mkdir(parents=True, exist_ok=True)

    # ── prep：读 backbone，按 allele 聚合所有需打分的肽（MT ∪ WT，去重）─────────
    rows = []
    allele_peps = defaultdict(set)          # allele_std → {pep_upper}
    dropped = 0
    with open(BACKBONE, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
            allele = (r.get("HLA_Allele") or "").strip()
            if not allele:
                continue
            for col in ("MT_Subpeptide", "WT_Subpeptide"):
                pep = (r.get(col) or "").strip().upper()
                if not pep:
                    continue
                if is_clean_pep(pep):
                    allele_peps[allele].add(pep)
                else:
                    dropped += 1  # 非标准/越界肽 → 不送工具，回贴时 NaN

    alleles = sorted(allele_peps.keys())
    print(f"[prep] backbone={len(rows)} 行 | 唯一 allele={len(alleles)} | "
          f"非标准/越界肽丢弃(置NaN)={dropped}")
    for a in alleles:
        print(f"[prep]   {a:<14} {len(allele_peps[a])} uniq pep")

    # ── run：逐 allele 调 ImmuneApp（经 WSL2 conda）──────────────────────────
    run_alleles = alleles[:args.smoke] if args.smoke else alleles
    score_dict = {}  # (pep_upper, allele_std) → score
    for i, a in enumerate(run_alleles, 1):
        pep_list = sorted(allele_peps[a])
        sc = score_allele(a, pep_list)
        for pep, v in sc.items():
            score_dict[(pep, a)] = v
        smin = min(sc.values()) if sc else float("nan")
        smax = max(sc.values()) if sc else float("nan")
        print(f"[run] [{i}/{len(run_alleles)}] {a} "
              f"{len(sc)}/{len(pep_list)} scores | range [{smin:.4f}, {smax:.4f}]")

    if args.smoke:
        print(f"\n[smoke] 跑了 {len(run_alleles)} 个 allele，工具可跑、分数在 0~1。未产 CSV。")
        return

    # ── parse：回贴 bb_idx，写 ImmuneApp_101102.csv ──────────────────────────
    def fmt(pep, allele):
        if not pep:
            return ""
        v = score_dict.get((pep, allele))
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""  # NaN → 空（pandas 读为 NaN）
        return str(round(v, 6))

    n_mt = n_wt = n_mt_nan = n_wt_nan = 0
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bb_idx", "MT_ImmuneApp", "WT_ImmuneApp"])
        w.writeheader()
        for r in rows:
            allele = (r.get("HLA_Allele") or "").strip()
            mt = (r.get("MT_Subpeptide") or "").strip().upper()
            wt = (r.get("WT_Subpeptide") or "").strip().upper()
            mt_s = fmt(mt, allele)
            wt_s = fmt(wt, allele)
            n_mt += mt_s != ""
            n_wt += wt_s != ""
            n_mt_nan += mt_s == ""
            n_wt_nan += wt_s == ""
            w.writerow({"bb_idx": r["bb_idx"], "MT_ImmuneApp": mt_s,
                        "WT_ImmuneApp": wt_s})

    print(f"\n[parse] 写 {OUT}  ({len(rows)} 行)")
    print(f"[parse]   MT_ImmuneApp: {n_mt} found / {n_mt_nan} NaN")
    print(f"[parse]   WT_ImmuneApp: {n_wt} found / {n_wt_nan} NaN")
    print(f"[parse]   方向：Immunogenicity_score 越高越免疫原（0~1，无翻转）")


if __name__ == "__main__":
    main()
