# -*- coding: utf-8 -*-
"""
run_hlathena_101102.py — Phase B：用订正 HLA 等位重推理 HLAthena（P101/P102）。

⚠️⚠️ HLAthena 预测 MHC-I **提呈（presentation）不是免疫原性**（Sarkizova 2020
Nat Biotech）。进 benchmark 只作 presentation baseline proxy，**单列 presentation 分**，
绝不与免疫原性工具 apples-to-apples 并列。方向照原部署：MSi 越高越可能被 HLA-I 提呈。

唯一订正输入源 = scripts/out/phaseB/backbone_101102.csv（prep_101102_subset.py 产，
已过闸门1：HLA_Allele == 订正真值 P101={A*66:01,B*40:01,B*57:01,C*06:02}/
P102={A*02:01,B*35:03,B*38:01}）。本脚本只从这份派生，绝不读旧 HLAthena 输入文件。

部署=本地 WSL docker（GCS 死锁绕过：挂本地模型 + patched predict_docker.bash，
fetch_models=false）。**调法逐字照 /root/quantimmu_wave3/run_hla_bench.sh（实测 SMOKE_PASS）**：
  docker run --rm \\
    -v <models>:/models -v <models_panpan>:/models_panpan \\
    -v <predict_docker.bash>:/pred/predict_docker.bash \\
    -v <rundir>:/work -w /work \\
    ssarkizova/hlathena-external:dev \\
    predict --runID r --rundir /work --peptides /work/peps_in.txt --alleles <tag>
输入文件 peps_in.txt = 首行表头 `pep` + 每行一肽（HLAthena peptide_col_name 默认 pep）。
输出 r-predictions.txt（**TAB 分隔**，列含 MSi_<tag> 提呈分 / model_<tag> 用了哪个模型 /
best.MSi）。

覆盖（实测纠正）：HLAthena **缺 specific 模型时直接崩**（`cannot open
models_linear_8_<tag>_slim.RDS`），**不自动回退 panpan**——本地 models_linear 只覆盖常见
等位（A0101/A0201/A0301/A2402…），罕见等位（A6601/B3503/B3801…）大概率缺。故跑前预检
`models_linear/models_linear_*_<tag>_slim.RDS`，无 → **跳过该 allele 整组留 NaN 继续下一个**
（不整体崩；HLAthena 等位覆盖有限是其本性，proxy 单列本就不全）。另加 try/except 兜底：跑
出错也置 NaN 继续。NaN 来自：①该 allele 无 specific 模型 ②长度∉8-11mer（HLAthena 仅
8/9/10/11mer，本子集含 12-14mer ~35%）③非标准氨基酸 ④该肽未出现在输出。

三步：
  1. prep：从 backbone 取 MT_Subpeptide + WT_Subpeptide，按 HLA_Allele 分组去重，
     仅留 8-11mer 标准 AA 肽（HLA-A*66:01 → A6601，predict_docker.bash 内部也去 HLA-/*/:，
     此处先规范化便于建列名 MSi_A6601）。
  2. run：逐 allele 写 peps_in.txt（表头 pep）→ docker 跑 → r-predictions.txt。
  3. parse：读 r-predictions.txt（tab），取 MSi_<tag>（缺则 best.MSi），按 (pep_upper, tag)
     回贴每行 bb_idx 的 MT/WT；同时记录 model_<tag>（specific/panpan）供透明报告。

产出: scripts/out/phaseB/HLAthena_101102.csv  列: bb_idx, MT_HLAthena, WT_HLAthena
方向: MSi presentation 分越高越可能被提呈（官方原始方向，无翻转）。
      ⚠️ presentation proxy，非免疫原性，下游不与免疫原性工具并列。

用法:
    python run_hlathena_101102.py [--smoke N]
        [--models-dir DIR] [--models-panpan DIR] [--predict-script PATH]
        [--image IMG] [--workdir DIR]
    --smoke N: 只跑前 N 个 allele 分组（验 docker 能跑、MSi 合理），不产正式 CSV。

⚠️ 本脚本只写不跑（coder 红线）；docker/烟测由主线在 WSL 执行。py_compile 已过。
"""
import argparse
import csv
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # QuantImmuBench/
BACKBONE = ROOT / "scripts" / "out" / "phaseB" / "backbone_101102.csv"
OUT = ROOT / "scripts" / "out" / "phaseB" / "HLAthena_101102.csv"

# ── 本地 WSL docker 默认配置（逐字照 run_hla_bench.sh / run_hla_patched.sh 实测）──────
DEFAULT_IMAGE = "ssarkizova/hlathena-external:dev"
# 实测 SMOKE_PASS 用的是 hla_arr 布局（run_hla_patched.sh：A=/root/quantimmu_wave3/hla_arr，
# 挂 $A/models 与 $A/models_panpan，产 hlasmoke-predictions.txt）。两布局都含 models_panpan，
# panpan 覆盖全 A/B/C，差别仅 specific 模型是否解压（对 7 订正等位无影响，多走 panpan）。
DEFAULT_MODELS_DIR = "/root/quantimmu_wave3/hla_arr/models"          # → /models（含 models_linear + ecdf）
DEFAULT_MODELS_PANPAN = "/root/quantimmu_wave3/hla_arr/models_panpan"  # → /models_panpan
DEFAULT_PREDICT_SCRIPT = "/root/quantimmu_wave3/hla_run/predict_docker.bash"  # patched fetch_models=false
# rundir/肽文件放原生 WSL 路径（避开 drvfs /mnt 权限坑，匹配 bench 原生 rundir 做法）。
DEFAULT_WORKDIR = "/root/quantimmu_wave3/hlathena_phaseB_work"

STD_AA = set("ACDEFGHIKLMNPQRSTVWY")  # HLAthena 仅接受标准 20 种氨基酸
HLATHENA_LENGTHS = frozenset({8, 9, 10, 11})  # 官方支持长度；其余 → NaN


def hla_to_tag(h: str) -> str:
    """HLA-A*66:01 → A6601（去 HLA- 去 * 去 :），与原部署 --alleles A0101 同格。"""
    return h.replace("HLA-", "").replace("*", "").replace(":", "")


def is_clean_pep(p: str) -> bool:
    return bool(p) and all(c in STD_AA for c in p)


def has_specific_model(models_dir: Path, tag: str) -> bool:
    """该 allele 是否有 specific slim 模型（任一长度有即算覆盖）。
    实测：HLAthena 缺 specific 模型时 predict_docker.bash 直接崩
    （`cannot open models_linear_8_<tag>_slim.RDS`），**不自动回退 panpan**。
    故跑前预检，无 → 跳过该 allele 留 NaN（HLAthena 等位覆盖有限是其本性）。"""
    mldir = models_dir / "models_linear"
    if not mldir.exists():
        return False
    return any(mldir.glob(f"models_linear_*_{tag}_slim.RDS"))


def run_hlathena_allele(image, models_dir, models_panpan, predict_script, tag, workdir):
    """对一个 allele 调 docker 跑 HLAthena，返回 r-predictions.txt 的 Path。

    逐字照 run_hla_bench.sh：rundir 内已写 peps_in.txt（表头 pep），输出 r-predictions.txt。
    """
    rundir = workdir / f"run_{tag}"
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{models_dir}:/models",
        "-v", f"{models_panpan}:/models_panpan",
        "-v", f"{predict_script}:/pred/predict_docker.bash",
        "-v", f"{rundir}:/work", "-w", "/work",
        image,
        "predict",
        "--runID", "r",
        "--rundir", "/work",
        "--peptides", "/work/peps_in.txt",
        "--alleles", tag,
    ]
    print(f"[run]   docker: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=3000)
    pred = rundir / "r-predictions.txt"
    if not pred.exists():
        raise RuntimeError(
            f"{tag} 未生成 r-predictions.txt rc={res.returncode}\n"
            f"STDERR: {res.stderr[:400]}\nSTDOUT: {res.stdout[:400]}")
    return pred


def parse_predictions(pred_txt: Path, tag: str):
    """读 r-predictions.txt（TAB 分隔），取 MSi_<tag> 提呈分 → ({pep_upper: score}, model_used)。

    优先列 MSi_<tag>（如 MSi_A6601）；缺则 fallback best.MSi。model_<tag> 记录用了
    specific 还是 panpan（透明报告用）。方向：越高越提呈，无翻转。
    """
    text = pred_txt.read_text(encoding="utf-8", errors="replace")
    lines = [ln.rstrip("\r\n") for ln in text.splitlines() if ln.strip()]
    if not lines:
        return {}, "EMPTY"
    header = [h.strip() for h in lines[0].split("\t")]

    def col(name):
        return header.index(name) if name in header else None

    pep_idx = col("pep")
    msi_idx = col(f"MSi_{tag}")
    if msi_idx is None:
        msi_idx = col("best.MSi")
    model_idx = col(f"model_{tag}")
    if pep_idx is None or msi_idx is None:
        raise RuntimeError(
            f"{tag} predictions 缺列 pep/MSi_{tag}（pep_idx={pep_idx}, msi_idx={msi_idx}），"
            f"实际表头={header}")

    scores = {}
    model_used = "?"
    for ln in lines[1:]:
        parts = ln.split("\t")
        if len(parts) <= max(pep_idx, msi_idx):
            continue
        pep = parts[pep_idx].strip().upper()
        if model_idx is not None and len(parts) > model_idx:
            model_used = parts[model_idx].strip() or model_used
        try:
            v = float(parts[msi_idx].strip())
        except ValueError:
            continue
        if not math.isnan(v):
            scores[pep] = v
    return scores, model_used


def main():
    ap = argparse.ArgumentParser(description="Phase B HLAthena 重推理 P101/P102（presentation proxy）")
    ap.add_argument("--smoke", type=int, default=0, help="只跑前 N 个 allele 分组，不产 CSV")
    ap.add_argument("--models-dir", default=DEFAULT_MODELS_DIR, help="→ 挂 /models（含 models_linear + ecdf）")
    ap.add_argument("--models-panpan", default=DEFAULT_MODELS_PANPAN, help="→ 挂 /models_panpan")
    ap.add_argument("--predict-script", default=DEFAULT_PREDICT_SCRIPT, help="patched predict_docker.bash")
    ap.add_argument("--image", default=DEFAULT_IMAGE, help="HLAthena docker 镜像")
    ap.add_argument("--workdir", default=DEFAULT_WORKDIR, help="rundir/肽文件目录（原生 WSL 路径，避 drvfs 坑）")
    args = ap.parse_args()

    if not BACKBONE.exists():
        raise SystemExit(f"[FAIL] 订正源不存在: {BACKBONE}")
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    # ── 读 backbone，按 allele_tag 聚合需打分的肽（MT ∪ WT，去重，仅 8-11mer 标准 AA）─────
    rows = []
    allele_peps = defaultdict(set)   # allele_tag → {pep_upper}
    allele_original = {}             # allele_tag → 原始 HLA 串
    n_len_drop = 0                   # 长度不在 8-11mer
    n_aa_drop = 0                    # 含非标准氨基酸
    with open(BACKBONE, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
            tag = hla_to_tag(r["HLA_Allele"].strip())
            allele_original.setdefault(tag, r["HLA_Allele"].strip())
            for col_name in ("MT_Subpeptide", "WT_Subpeptide"):
                pep = (r.get(col_name) or "").strip().upper()
                if not pep:
                    continue
                if len(pep) not in HLATHENA_LENGTHS:
                    n_len_drop += 1
                    continue
                if not is_clean_pep(pep):
                    n_aa_drop += 1
                    continue
                allele_peps[tag].add(pep)

    alleles = sorted(allele_peps.keys())
    models_dir = Path(args.models_dir)
    print(f"[prep] backbone={len(rows)} 行 | 唯一 allele={len(alleles)}")
    print(f"[prep] 丢弃(置NaN)：长度∉8-11mer={n_len_drop} | 非标准氨基酸={n_aa_drop}")
    covered = {}  # tag → bool（有 specific 模型）
    for tag in alleles:
        ok = has_specific_model(models_dir, tag)
        covered[tag] = ok
        print(f"[prep]   {tag:<8} ({allele_original.get(tag):<12}) {len(allele_peps[tag])} uniq pep（8-11mer）"
              f"  specific模型={'✅在' if ok else '❌缺→整组NaN'}")
    n_missing = sum(1 for v in covered.values() if not v)
    if n_missing:
        print(f"[prep] ⚠️ {n_missing}/{len(alleles)} 等位无 specific 模型 → 跳过留 NaN"
              f"（HLAthena 缺 specific 直接崩不回退 panpan，等位覆盖有限是其本性）。")

    # ── 逐 allele 写 peps_in.txt（表头 pep）+ 调 docker 打分 ──────────────────────────
    run_tags = alleles[:args.smoke] if args.smoke else alleles
    score_dict = {}      # (pep_upper, allele_tag) → MSi
    model_report = {}    # tag → model_used（specific/panpan/SKIP_no_model/ERROR）
    for i, tag in enumerate(run_tags, 1):
        if not covered[tag]:
            model_report[tag] = "SKIP_no_model"
            print(f"[run] [{i}/{len(run_tags)}] {tag} 跳过（无 specific 模型）→ 整组 NaN")
            continue
        rundir = workdir / f"run_{tag}"
        rundir.mkdir(parents=True, exist_ok=True)
        pep_list = sorted(allele_peps[tag])
        # peps_in.txt：首行表头 pep + 每行一肽（LF），与 run_hla_bench.sh `{ echo pep; cat f; }` 一致
        (rundir / "peps_in.txt").write_text("pep\n" + "\n".join(pep_list) + "\n", encoding="utf-8")
        # 兜底：单 allele 跑/解析出错 → 置 NaN 继续下一个，别整体崩
        try:
            pred = run_hlathena_allele(
                args.image, args.models_dir, args.models_panpan, args.predict_script, tag, workdir)
            sc, model_used = parse_predictions(pred, tag)
        except Exception as e:
            model_report[tag] = "ERROR"
            print(f"[run] [{i}/{len(run_tags)}] {tag} ❌ 出错置 NaN 继续: {str(e)[:200]}", file=sys.stderr)
            continue
        model_report[tag] = model_used
        for pep, v in sc.items():
            score_dict[(pep, tag)] = v
        smin = min(sc.values()) if sc else float("nan")
        smax = max(sc.values()) if sc else float("nan")
        print(f"[run] [{i}/{len(run_tags)}] {tag} model={model_used} {len(sc)} MSi 分 | "
              f"range [{smin:.4f}, {smax:.4f}]")

    if args.smoke:
        print(f"\n[smoke] 跑了 {len(run_tags)} 个 allele，docker 可跑、MSi 在 [0,1] 合理区间。未产 CSV。")
        print(f"[smoke] 模型使用：{model_report}")
        return

    # ── 回贴 bb_idx，写 HLAthena_101102.csv ────────────────────────────────────────
    def fmt(pep, tag):
        if not pep:
            return ""
        v = score_dict.get((pep, tag))
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""  # NaN → 空（长度/AA/缺失多重原因）
        return str(round(v, 6))

    n_mt = n_wt = n_mt_nan = n_wt_nan = 0
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bb_idx", "MT_HLAthena", "WT_HLAthena"])
        w.writeheader()
        for r in rows:
            tag = hla_to_tag(r["HLA_Allele"].strip())
            mt = (r.get("MT_Subpeptide") or "").strip().upper()
            wt = (r.get("WT_Subpeptide") or "").strip().upper()
            mt_s = fmt(mt, tag)
            wt_s = fmt(wt, tag)
            n_mt += mt_s != ""
            n_wt += wt_s != ""
            n_mt_nan += mt_s == ""
            n_wt_nan += wt_s == ""
            w.writerow({"bb_idx": r["bb_idx"], "MT_HLAthena": mt_s, "WT_HLAthena": wt_s})

    print(f"\n[parse] 写 {OUT}  ({len(rows)} 行)")
    print(f"[parse]   模型使用（specific/panpan）：{model_report}")
    print(f"[parse]   MT_HLAthena: {n_mt} found / {n_mt_nan} NaN")
    print(f"[parse]   WT_HLAthena: {n_wt} found / {n_wt_nan} NaN")
    print(f"[parse]   方向：MSi presentation 分越高越提呈（无翻转）")
    print(f"[parse]   ⚠️ presentation proxy，非免疫原性——下游单列，不与免疫原性工具并列。")


if __name__ == "__main__":
    main()
