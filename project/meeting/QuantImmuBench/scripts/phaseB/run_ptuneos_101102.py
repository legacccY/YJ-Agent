# -*- coding: utf-8 -*-
"""
run_ptuneos_101102.py — Phase B：用订正 HLA 等位重推理 pTuneos Pre&RecNeo（P101/P102）。

唯一订正输入源 = scripts/out/phaseB/backbone_101102.csv（prep_101102_subset.py 产，
已过闸门1：HLA_Allele == 订正真值 P101={A*66:01,B*40:01,B*57:01,C*06:02}/
P102={A*02:01,B*35:03,B*38:01}）。本脚本只从这份派生，绝不读旧 ptuneos 输入文件。

══════════════════════════════════════════════════════════════════════════════
pTuneos 子模型口径（与原部署 Entry 20 完全一致 —— 本地 WSL docker，**非 HPC**）
──────────────────────────────────────────────────────────────────────────────
跑的是 pTuneos 内部的 **Pre&RecNeo 识别子模型**（输出列 model_pro），RandomForest
基于 5 个纯肽+HLA 特征 [Hydrophobicity, Recognition, Self_similarity,
MT_Binding_EL, WT_Binding_EL]，输入仅 (MT_pep, WT_pep, HLA_type) 三列。
**不换全基因组 VCF 模式**（那是 RefinedNeo，需测序，喂不了纯肽）。

容器内真正干活的是已部署 wrapper `scripts/ptuneos/ptuneos_pre_recneo.py`（Python 2.7，
逐字复刻官方 VCFprocessor.py::InVivoModelAndScore() 的 5 特征 RF，对账官方 example
40 肽 model_pro r=1.0）。本脚本是 **host 侧 Py3 编排器**：prep（建容器输入 TSV）→
run（docker 起容器跑 wrapper）→ parse（model_pro 贴回 bb_idx）。

只产 **MT_pTuneos = model_pro(MT_pep=MT_sub, WT_pep=WT_sub, HLA)**（合表无 WT 列）。
model_pro 本就是「突变肽 vs 其野生型种系」的不对称免疫原性分（Self_similarity /
WT_Binding_EL 特征已内含 MT-vs-WT 差异），无独立 WT 分。
方向：model_pro 越高越免疫原（官方原始方向，无翻转）。

══════════════════════════════════════════════════════════════════════════════
原始跑法（实测 /root/quantimmu/ptuneos_run/elispot/full_run2.log 复盘确认）
──────────────────────────────────────────────────────────────────────────────
· 镜像 bm2lab/ptuneos:v2.1（本地 WSL docker 有）。
· 容器 /work = 挂载 host 工作目录（含 wrapper + 输入 TSV）；wrapper 调
    --input /work/<in>.tsv --output /work/<out>.tsv
    --models /root/pTuneos/train_model（镜像自带 RF/cf_hy/iedb.fasta）
    --blastdb <blastdb>/peptide --nproc N
  容器内 export PATH=/root/software/netMHCpan-4.0:$PATH（镜像自带 netMHCpan-4.0）。
· **blastdb（Self_similarity homolog 项必需）真实路径** = host WSL
    /root/quantimmu/ptuneos_run/database/Protein/peptide_database/peptide.{phr,pin,psq}
  （Ensembl release-97 human.pep.all，110048 序列；原跑 blastp 7135/7137 拿到非默认
   homolog → blastdb 真用上、r=1.0 成立。注意 elispot/blastdb 子目录是空壳，别用那个）。
  本脚本把该目录额外挂为容器 /blastdb，wrapper --blastdb /blastdb/peptide。

caveat（非 bug）：P101/P102 的 7 个 HLA 若某个不在 netMHCpan-4.0 列表 → 该行 EL 缺失
→ model_pro=NaN（wrapper 已优雅处理，回贴留空）。

用法（主线在 WSL 跑，sudo docker）:
    sudo python3 run_ptuneos_101102.py [--smoke N] [--nproc 8]
  默认 --docker-cmd "docker"（WSL 内直跑）。若从 Windows host 起则
    python run_ptuneos_101102.py --docker-cmd "wsl docker"
  （脚本自动把 /work 与 blastdb 挂载源 Windows 路径 D 盘 → /mnt/d/ 供 wsl docker 用；
   但 blastdb 在 WSL /root/... 下，从 Windows host 经 wsl docker 不一定可挂 → 建议直接
   在 WSL 内 sudo 跑，挂载源全是原生 WSL 路径最稳）。

  ⚠️ 本脚本含 docker 子进程（执行容器代码）→ **coder 不跑，交主线烟测**：
       先 `sudo python3 run_ptuneos_101102.py --smoke 3` 验 docker/wrapper/blastdb 通，
       再 `sudo python3 run_ptuneos_101102.py` 全量产 CSV。
"""
import argparse
import csv
import math
import os
import shutil
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # QuantImmuBench/
BACKBONE = ROOT / "scripts" / "out" / "phaseB" / "backbone_101102.csv"
WRAPPER = ROOT / "scripts" / "ptuneos" / "ptuneos_pre_recneo.py"  # 容器内跑的 Py2.7 wrapper
WORKDIR = ROOT / "scripts" / "out" / "phaseB" / "ptuneos_work"    # 挂为容器 /work
IN_TSV = WORKDIR / "ptuneos_input_101102.tsv"                     # 容器输入 (MT_pep,WT_pep,HLA_type)
OUT_TSV = WORKDIR / "ptuneos_output_101102.tsv"                   # 容器输出 (含 model_pro)
OUT = ROOT / "scripts" / "out" / "phaseB" / "pTuneos_101102.csv"  # 最终交付

# blastdb 真实路径（host WSL，见顶部）。父目录挂为容器 /blastdb，prefix=peptide。
DEFAULT_BLASTDB_HOST = "/root/quantimmu/ptuneos_run/database/Protein/peptide_database"

STD_AA = set("ACDEFGHIKLMNPQRSTVWY")  # 仅标准 20 氨基酸送工具，否则 hydro_vector KeyError


def is_clean_pep(p: str) -> bool:
    return bool(p) and all(c in STD_AA for c in p)


def win_to_wsl_path(p: str) -> str:
    """Windows 'D:\\a\\b' → WSL '/mnt/d/a/b'（仅 --docker-cmd 含 wsl 且 host 为 Windows 时用）。
    已是 POSIX 路径则原样返回。"""
    p = str(p)
    if len(p) >= 2 and p[1] == ":" and p[0].isalpha():
        drive = p[0].lower()
        rest = p[2:].replace("\\", "/")
        if not rest.startswith("/"):
            rest = "/" + rest
        return f"/mnt/{drive}{rest}"
    return p.replace("\\", "/")


def build_input_triples(rows):
    """
    从 backbone 行集建容器输入所需的 **unique (MT_pep, WT_pep, HLA_type)** 三元组。
    仅 MT 套: (MT_pep=MT_sub, WT_pep=WT_sub, HLA) → 回贴 MT_pTuneos（原部署口径）。
    非标准氨基酸 / 空肽 → 不入容器输入（回贴时留空 = NaN）。
    返回 OrderedDict[(mt,wt,hla)] = None（有序去重集）。
    """
    triples = OrderedDict()
    for r in rows:
        hla = (r.get("HLA_Allele") or "").strip()
        mt = (r.get("MT_Subpeptide") or "").strip().upper()
        wt = (r.get("WT_Subpeptide") or "").strip().upper()
        if hla and is_clean_pep(mt) and is_clean_pep(wt):
            triples.setdefault((mt, wt, hla), None)
    return triples


def write_input_tsv(triples, path):
    """写容器输入 TSV：列 MT_pep<TAB>WT_pep<TAB>HLA_type（wrapper 必需三列）。
    HLA_type 保留 backbone 原格 'HLA-A*66:01'（wrapper 内部 .replace('*','') 喂 netMHCpan）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write("MT_pep\tWT_pep\tHLA_type\n")
        for (mt, wt, hla) in triples.keys():
            f.write(f"{mt}\t{wt}\t{hla}\n")


def build_docker_cmd(args, in_name, out_name):
    """组装 docker 调用。复盘 full_run2.log 口径：/work 挂 work 目录，blastdb 父目录挂 /blastdb。"""
    docker_tokens = args.docker_cmd.split()
    use_wsl = any("wsl" in t for t in docker_tokens)

    work_src = args.mount_src or str(WORKDIR)
    bdb_src = args.blastdb_host
    if use_wsl and os.name == "nt":
        # Windows host 经 wsl docker：挂载源须转 WSL 路径
        work_src = win_to_wsl_path(work_src)
        bdb_src = win_to_wsl_path(bdb_src)

    inner = (
        "export PATH=/root/software/netMHCpan-4.0:$PATH && "
        f"python /work/ptuneos_pre_recneo.py "
        f"--input /work/{in_name} "
        f"--output /work/{out_name} "
        f"--models /root/pTuneos/train_model "
        f"--blastdb /blastdb/peptide "
        f"--nproc {args.nproc}"
    )
    cmd = docker_tokens + [
        "run", "--rm",
        "-v", f"{work_src}:/work",
        "-v", f"{bdb_src}:/blastdb:ro",
        args.image,
        "bash", "-c", inner,
    ]
    return cmd


def parse_output(out_tsv):
    """读容器输出 TSV → {(MT_pep, WT_pep, HLA_type): model_pro_float}。"""
    score = {}
    with open(out_tsv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for c in ("MT_pep", "WT_pep", "HLA_type", "model_pro"):
            if c not in reader.fieldnames:
                raise RuntimeError(f"容器输出缺列 {c}；实际列={reader.fieldnames}")
        for row in reader:
            mt = (row["MT_pep"] or "").strip().upper()
            wt = (row["WT_pep"] or "").strip().upper()
            hla = (row["HLA_type"] or "").strip()
            raw = (row["model_pro"] or "").strip()
            try:
                v = float(raw)
            except (TypeError, ValueError):
                v = float("nan")
            score[(mt, wt, hla)] = v
    return score


def main():
    ap = argparse.ArgumentParser(description="Phase B pTuneos Pre&RecNeo 重推理 P101/P102")
    ap.add_argument("--smoke", type=int, default=0,
                    help="只把前 N 个 unique 三元组送容器验工具，不产 CSV")
    ap.add_argument("--docker-cmd", default="docker",
                    help="docker 可执行；WSL 内直跑用 'docker'，Windows host 用 'wsl docker'")
    ap.add_argument("--image", default="bm2lab/ptuneos:v2.1", help="pTuneos 镜像 tag")
    ap.add_argument("--mount-src", default="",
                    help="挂为容器 /work 的 host 路径（默认 WORKDIR）")
    ap.add_argument("--blastdb-host", default=DEFAULT_BLASTDB_HOST,
                    help="host 上 blastdb 父目录（含 peptide.{phr,pin,psq}），挂为容器 /blastdb")
    ap.add_argument("--nproc", type=int, default=8, help="wrapper calculate_R 并行进程数")
    args = ap.parse_args()

    if not BACKBONE.exists():
        raise SystemExit(f"[FAIL] 订正源不存在: {BACKBONE}")
    if not WRAPPER.exists():
        raise SystemExit(f"[FAIL] 容器 wrapper 不存在: {WRAPPER}")
    WORKDIR.mkdir(parents=True, exist_ok=True)

    # ── 读 backbone ───────────────────────────────────────────────────────────
    with open(BACKBONE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # ── prep：建 unique 三元组 + 写容器输入 TSV + 拷 wrapper 进 /work ─────────
    triples = build_input_triples(rows)
    all_keys = list(triples.keys())
    if args.smoke:
        all_keys = all_keys[:args.smoke]
        triples = OrderedDict((k, None) for k in all_keys)
    in_tsv = (WORKDIR / "ptuneos_input_smoke.tsv") if args.smoke else IN_TSV
    out_tsv = (WORKDIR / "ptuneos_output_smoke.tsv") if args.smoke else OUT_TSV
    write_input_tsv(triples, in_tsv)
    shutil.copy2(WRAPPER, WORKDIR / "ptuneos_pre_recneo.py")  # 挂载后容器内 /work/ptuneos_pre_recneo.py

    n_mt_pairs = sum(1 for r in rows
                     if is_clean_pep((r.get("MT_Subpeptide") or "").strip().upper())
                     and is_clean_pep((r.get("WT_Subpeptide") or "").strip().upper())
                     and (r.get("HLA_Allele") or "").strip())
    print(f"[prep] backbone={len(rows)} 行 | unique 三元组={len(all_keys)}"
          f"{' (smoke 截断)' if args.smoke else ''} | 写 {in_tsv}")
    print(f"[prep]   clean MT-pair 行(有HLA)={n_mt_pairs} | HLA 集合={sorted({k[2] for k in all_keys})}")

    # ── run：docker 起容器跑 wrapper ─────────────────────────────────────────
    cmd = build_docker_cmd(args, in_tsv.name, out_tsv.name)
    print(f"[run] docker 命令:\n      {' '.join(cmd[:-1])} '<inner bash -c>'")
    print(f"[run] inner: {cmd[-1]}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.stdout:
        print("[run][container stdout tail]\n" + "\n".join(res.stdout.splitlines()[-15:]))
    if res.returncode != 0:
        raise SystemExit(
            f"[FAIL] 容器退出码 {res.returncode}\n  stderr tail:\n"
            + "\n".join(res.stderr.splitlines()[-20:]))
    if not out_tsv.exists():
        raise SystemExit(f"[FAIL] 容器未产出 {out_tsv}（核挂载/路径 + stderr）")

    # ── parse：model_pro 贴回 bb_idx ─────────────────────────────────────────
    score = parse_output(out_tsv)
    print(f"[parse] 容器输出 {len(score)} 条 model_pro")

    if args.smoke:
        vals = [v for v in score.values() if not math.isnan(v)]
        smin = min(vals) if vals else float("nan")
        smax = max(vals) if vals else float("nan")
        print(f"\n[smoke] 送 {len(all_keys)} 三元组，工具可跑、得 {len(vals)} 有效分 "
              f"range [{smin:.6f}, {smax:.6f}]（0-1 概率）。未产 CSV。")
        return

    def fmt(mt, wt, hla):
        v = score.get((mt, wt, hla))
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""
        return str(round(v, 6))

    n_mt = n_mt_nan = 0
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bb_idx", "MT_pTuneos"])
        w.writeheader()
        for r in rows:
            hla = (r.get("HLA_Allele") or "").strip()
            mt = (r.get("MT_Subpeptide") or "").strip().upper()
            wt = (r.get("WT_Subpeptide") or "").strip().upper()
            mt_s = fmt(mt, wt, hla) if (is_clean_pep(mt) and is_clean_pep(wt) and hla) else ""
            n_mt += mt_s != ""
            n_mt_nan += mt_s == ""
            w.writerow({"bb_idx": r["bb_idx"], "MT_pTuneos": mt_s})

    # ── 自校验打印 ────────────────────────────────────────────────────────────
    print(f"\n[parse] 写 {OUT}  ({len(rows)} 行)")
    print(f"[parse]   MT_pTuneos: {n_mt} found / {n_mt_nan} NaN（model_pro，原部署口径）")
    print(f"[parse]   方向：model_pro 越高越免疫原（无翻转）")
    print(f"[parse]   clean MT-pair={n_mt_pairs} → 应 ≈ found；NaN 偏多=该 allele 不被 netMHCpan-4.0 覆盖")


if __name__ == "__main__":
    main()
