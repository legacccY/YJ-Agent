# -*- coding: utf-8 -*-
"""
run_immuneapp_hpc.py — Phase B：在 HPC 上用订正 HLA 等位重推理 ImmuneApp-Neo（P101/P102）。

唯一订正输入源 = $BASE/phaseB/backbone_101102.csv（HLA_Allele 已订正：
P101={A*66:01,B*40:01,B*57:01,C*06:02} / P102={A*02:01,B*35:03,B*38:01}）。
本脚本只从这份派生，绝不读任何旧 immuneapp 输入。

与本地版 scripts/phaseB/run_immuneapp_101102.py 逻辑一致，但：
  - 路径全改 HPC（BASE=/gpfs/work/bio/jiayu2403/quantimmu）。
  - run 步**不走 WSL**：本脚本由 run_immuneapp_hpc.sh 在 `source activate envs/immuneapp`
    后调起，env 的 python 已在 PATH，直接 subprocess 调官方脚本（cwd=repo）即可。

自包含三步：
  1. prep：从 backbone 取 MT_Subpeptide ∪ WT_Subpeptide，按 HLA_Allele 分组去重。
     ImmuneApp 接受标准格式 HLA-A*66:01（不转换）；仅 8–15 mer + 20 标准氨基酸，
     非标准/越界肽不送工具、回贴时置 NaN（空）。
  2. run：逐 allele 写 peps.txt，调官方 ImmuneApp_immunogenicity_prediction.py
     （cd repo，相对路径加载 ImmuneApp_weights/）。
  3. parse：读每 allele 输出 ImmuneApp_Immunogenicity_predictions.tsv
     （列 Allele/Peptide/Sample/Immunogenicity_score），(pep_upper, allele) → score，
     回贴每行 bb_idx 的 MT/WT 分数。

产出: $BASE/phaseB/ImmuneApp_101102.csv
      列: bb_idx, MT_ImmuneApp, WT_ImmuneApp
方向: Immunogenicity_score 越高越免疫原（官方原始方向 0~1 sigmoid，无翻转）。

用法（HPC，由 run_immuneapp_hpc.sh 激活 env 后调起）:
    python run_immuneapp_hpc.py [--smoke N]
    --smoke N: 只跑前 N 个 allele 分组（验工具能跑、分数在 0~1），不产正式 CSV。

环境覆盖（路径不确定时用 env 改，不改代码）:
    QIB_BASE            quantimmu 根目录（默认 /gpfs/work/bio/jiayu2403/quantimmu）
    IMMUNEAPP_REPO      ImmuneApp repo 绝对路径（默认 $BASE/tools_repos/ImmuneApp）
"""
import argparse
import csv
import math
import os
import subprocess
import sys
from collections import defaultdict

# ── HPC 路径（与部署一致；可用 env 覆盖，勿改死）─────────────────────────────
BASE = os.environ.get("QIB_BASE", "/gpfs/work/bio/jiayu2403/quantimmu")
REPO = os.environ.get("IMMUNEAPP_REPO", os.path.join(BASE, "tools_repos", "ImmuneApp"))
BACKBONE = os.path.join(BASE, "phaseB", "backbone_101102.csv")
WORKDIR = os.path.join(BASE, "phaseB", "immuneapp_work")  # per-allele in/out
OUT = os.path.join(BASE, "phaseB", "ImmuneApp_101102.csv")

TSV_NAME = "ImmuneApp_Immunogenicity_predictions.tsv"  # ImmuneApp 固定输出文件名

STD_AA = set("ACDEFGHIKLMNPQRSTVWY")  # 仅 20 标准氨基酸（read_peplist 硬验证）
MIN_LEN, MAX_LEN = 8, 15            # ImmuneApp-Neo 肽长限制 8–15 mer

# 订正真值（自校验用）。HLA_Allele 标准格式 HLA-<gene>*<field>。
EXPECTED_HLA = {
    "101": {"HLA-A*66:01", "HLA-B*40:01", "HLA-B*57:01", "HLA-C*06:02"},
    "102": {"HLA-A*02:01", "HLA-B*35:03", "HLA-B*38:01"},
}


def is_clean_pep(p):
    return bool(p) and MIN_LEN <= len(p) <= MAX_LEN and all(c in STD_AA for c in p)


def allele_safe(h):
    """HLA-A*66:01 → HLA-A_66_01（* 与 : 换 _，文件/目录名安全）。"""
    return h.replace("*", "_").replace(":", "_")


def parse_tsv(tsv_path):
    """读 ImmuneApp 输出 tsv → {pep_upper: score}（单 allele 目录，Allele 列恒定）。"""
    scores = {}
    if not os.path.exists(tsv_path):
        return scores
    with open(tsv_path, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        # 容错：列名可能含首尾空格
        cols = {c.strip(): c for c in (reader.fieldnames or [])}
        pep_c = cols.get("Peptide")
        sc_c = cols.get("Immunogenicity_score")
        if not pep_c or not sc_c:
            raise RuntimeError(
                "tsv 缺列（需 Peptide/Immunogenicity_score）: %s" % reader.fieldnames)
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
    adir = os.path.join(WORKDIR, safe)
    if not os.path.isdir(adir):
        os.makedirs(adir)
    pep_file = os.path.join(adir, "peps.txt")
    with open(pep_file, "w") as f:
        f.write("\n".join(pep_list) + "\n")  # 无 header

    # env 已激活 → 直接用当前 python 调官方脚本，cwd=repo（相对加载权重）
    cmd = [sys.executable, "ImmuneApp_immunogenicity_prediction.py",
           "-f", pep_file, "-a", allele_std, "-o", adir]
    res = subprocess.run(cmd, cwd=REPO, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, universal_newlines=True,
                         timeout=1800)
    if res.returncode != 0:
        raise RuntimeError(
            "%s ImmuneApp 失败 rc=%d: %s%s" % (
                allele_std, res.returncode, res.stderr[-300:], res.stdout[-300:]))
    return parse_tsv(os.path.join(adir, TSV_NAME))


def main():
    ap = argparse.ArgumentParser(description="Phase B ImmuneApp-Neo 重推理 P101/P102 (HPC)")
    ap.add_argument("--smoke", type=int, default=0,
                    help="只跑前 N 个 allele 分组验工具，不产 CSV")
    args = ap.parse_args()

    print("[cfg] BASE=%s" % BASE)
    print("[cfg] REPO=%s" % REPO)
    print("[cfg] BACKBONE=%s" % BACKBONE)
    if not os.path.exists(BACKBONE):
        raise SystemExit("[FAIL] 订正源不存在: %s" % BACKBONE)
    if not os.path.isdir(REPO):
        raise SystemExit("[FAIL] ImmuneApp repo 不存在: %s" % REPO)
    if not os.path.isdir(WORKDIR):
        os.makedirs(WORKDIR)

    # ── prep：读 backbone，按 allele 聚合所有需打分的肽（MT ∪ WT，去重）─────────
    rows = []
    allele_peps = defaultdict(set)          # allele_std → {pep_upper}
    patient_hla = defaultdict(set)          # Patient_ID 前缀 → {HLA_Allele}（自校验）
    dropped = 0
    with open(BACKBONE, newline="") as f:
        for r in csv.DictReader(f):
            rows.append(r)
            allele = (r.get("HLA_Allele") or "").strip()
            pid = (r.get("Patient_ID") or "").split(".")[0]
            if allele and pid:
                patient_hla[pid].add(allele)
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

    # ── 自校验：HLA 订正值是否与预期一致 ──────────────────────────────────────
    print("\n[check] === HLA 订正自校验 ===")
    ok_hla = True
    for pid in sorted(patient_hla.keys()):
        got = patient_hla[pid]
        exp = EXPECTED_HLA.get(pid)
        tag = ""
        if exp is not None:
            tag = " ✅ 匹配订正真值" if got == exp else " ❌ 与订正真值不符 exp=%s" % sorted(exp)
            if got != exp:
                ok_hla = False
        print("[check]   P%s -> %s%s" % (pid, sorted(got), tag))
    if not ok_hla:
        print("[check] ⚠️ HLA 订正不一致——backbone 源异常，停止避免污染。")
        raise SystemExit("[FAIL] HLA 订正自校验未通过")

    alleles = sorted(allele_peps.keys())
    print("\n[prep] backbone=%d 行 | 唯一 allele=%d | 非标准/越界肽丢弃(置NaN)=%d"
          % (len(rows), len(alleles), dropped))
    for a in alleles:
        print("[prep]   %-14s %d uniq pep" % (a, len(allele_peps[a])))

    # ── run：逐 allele 调 ImmuneApp（env 已激活）──────────────────────────────
    run_alleles = alleles[:args.smoke] if args.smoke else alleles
    score_dict = {}  # (pep_upper, allele_std) → score
    for i, a in enumerate(run_alleles, 1):
        pep_list = sorted(allele_peps[a])
        sc = score_allele(a, pep_list)
        for pep, v in sc.items():
            score_dict[(pep, a)] = v
        smin = min(sc.values()) if sc else float("nan")
        smax = max(sc.values()) if sc else float("nan")
        print("[run] [%d/%d] %s %d/%d scores | range [%.4f, %.4f]"
              % (i, len(run_alleles), a, len(sc), len(pep_list), smin, smax))

    if args.smoke:
        print("\n[smoke] 跑了 %d 个 allele，工具可跑、分数在 0~1。未产 CSV。"
              % len(run_alleles))
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
    with open(OUT, "w", newline="") as f:
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

    print("\n[parse] 写 %s  (%d 行)" % (OUT, len(rows)))
    print("[parse]   MT_ImmuneApp: %d found / %d NaN" % (n_mt, n_mt_nan))
    print("[parse]   WT_ImmuneApp: %d found / %d NaN" % (n_wt, n_wt_nan))
    print("[parse]   方向：Immunogenicity_score 越高越免疫原（0~1，无翻转）")


if __name__ == "__main__":
    main()
