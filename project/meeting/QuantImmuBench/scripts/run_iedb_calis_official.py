# -*- coding: utf-8 -*-
"""
run_iedb_calis_official.py — 新官方数据上重推理 IEDB_Calis（管道验证打头工具）。

克隆自 scripts/phaseB/run_iedb_calis_101102.py，唯一改动 = 输入/输出路径指向
新官方数据。算法逻辑、SUPPORTED_ALLELES、masking 规则、方向（score 越高越免疫原，
无翻转）、HLA→IEDB tag 转换、MT/WT 双侧解析全部保持一致（不改算法）。

输入源 = scripts/out_official/master_backbone_official.csv（schema 与 _101102 一致：
bb_idx / MT_Subpeptide(1761 非空) / WT_Subpeptide(244 非空) / HLA_Allele(HLA-A*66:01) /
mut_key）。WT 多数为空（indel 肽无 WT）→ 空的 WT 分数留空，不报错。

自包含三步（prep+run+parse 一体），与 HPC/deploy/iedb_calis 三件套调用逻辑一致：
  1. 从 backbone 取 MT_Subpeptide + WT_Subpeptide，按 HLA_Allele 分组
     （HLA 去 * 去 : → IEDB tag，如 HLA-A*02:01 → HLA-A0201）。
  2. 对每个 allele 调官方 predict_immunogenicity.py：
       - allele 在工具 allele_dict（42 个）→ --allele=<tag>（allele-specific mask）
       - 不在 → 不传 --allele（默认 mask P1,P2,C-term），与 run_local.py 一致。
  3. 解析 stdout（peptide,length,score）→ (pep_upper, allele_tag) → score，
     回贴每行 bb_idx 的 MT/WT 分数。

产出: scripts/out_official/IEDB_Calis_official.csv
      列: bb_idx, MT_IEDB_Calis, WT_IEDB_Calis
方向: score 越高越免疫原（官方原始方向，无翻转）。

用法:
    python run_iedb_calis_official.py [--smoke N]
    --smoke N: 只跑前 N 个 allele 分组（验工具能跑、分数合理），不产正式 CSV。
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
ROOT = HERE.parent  # QuantImmuBench/（本脚本在 scripts/ 下，比 _101102 浅一层）
BACKBONE = ROOT / "scripts" / "out_official" / "master_backbone_official.csv"
TOOL = ROOT / "HPC" / "deploy" / "iedb_calis" / "immunogenicity" / "predict_immunogenicity.py"
WORKDIR = ROOT / "scripts" / "out_official" / "iedb_calis_work"  # per-allele 临时 in/out
OUT = ROOT / "scripts" / "out_official" / "IEDB_Calis_official.csv"

# IEDB Calis v3.0 支持的 allele（allele-specific mask）。
# 来源：predict_immunogenicity.py 源码 allele_dict.keys()（42 个，含 6 小鼠 H-2）。
# 不在此集的 allele 一律用默认 mask（P1,P2,C-term），与官方 run_local.py 行为一致。
SUPPORTED_ALLELES = frozenset({
    "H-2-Db", "H-2-Dd", "H-2-Kb", "H-2-Kd", "H-2-Kk", "H-2-Ld",
    "HLA-A0101", "HLA-A0201", "HLA-A0202", "HLA-A0203", "HLA-A0206", "HLA-A0211",
    "HLA-A0301", "HLA-A1101", "HLA-A2301", "HLA-A2402", "HLA-A2601", "HLA-A2902",
    "HLA-A3001", "HLA-A3002", "HLA-A3101", "HLA-A3201", "HLA-A3301", "HLA-A6801",
    "HLA-A6802", "HLA-A6901",
    "HLA-B0702", "HLA-B0801", "HLA-B1501", "HLA-B1502", "HLA-B1801", "HLA-B2705",
    "HLA-B3501", "HLA-B3901", "HLA-B4001", "HLA-B4002", "HLA-B4402", "HLA-B4403",
    "HLA-B4501", "HLA-B4601", "HLA-B5101", "HLA-B5301", "HLA-B5401", "HLA-B5701",
    "HLA-B5801",
})

STD_AA = set("ACDEFGHIKLMNPQRSTVWY")  # 工具仅接受标准 20 种氨基酸，否则整文件 exit(1)


def hla_to_iedb(h: str) -> str:
    """HLA-A*02:01 → HLA-A0201（去 * 去 :），与 prep_input.py 一致。"""
    return h.replace("*", "").replace(":", "")


def allele_tag_to_file_tag(tag: str) -> str:
    """HLA-A0201 → A0201 / H-2-Db → H_2_Db（文件名安全）。"""
    return tag.replace("HLA-", "").replace("-", "_")


def is_clean_pep(p: str) -> bool:
    return bool(p) and all(c in STD_AA for c in p)


def score_allele(tool_py, allele_tag, is_supported, pep_file, env):
    """调官方工具打一个 allele 文件，解析 stdout → {pep_upper: score}。"""
    cmd = [sys.executable, str(tool_py)]
    if is_supported:
        cmd.append(f"--allele={allele_tag}")
    cmd.append(str(pep_file))
    res = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600)
    if res.returncode != 0:
        raise RuntimeError(f"{allele_tag} 工具失败 rc={res.returncode}: {res.stderr[:200]}{res.stdout[:200]}")
    scores = {}
    in_data = False
    for line in res.stdout.splitlines():
        s = line.strip()
        if not in_data:
            if s == "peptide,length,score":
                in_data = True
            continue
        if not s:
            continue
        parts = s.split(",")
        if len(parts) < 3:
            continue
        try:
            scores[parts[0].strip().upper()] = float(parts[2].strip())
        except ValueError:
            continue
    return scores


def main():
    ap = argparse.ArgumentParser(description="新官方数据 IEDB_Calis 重推理")
    ap.add_argument("--smoke", type=int, default=0, help="只跑前 N 个 allele 分组验工具，不产 CSV")
    args = ap.parse_args()

    if not BACKBONE.exists():
        raise SystemExit(f"[FAIL] 官方源不存在: {BACKBONE}")
    if not TOOL.exists():
        raise SystemExit(f"[FAIL] 官方工具不存在: {TOOL}（先解压 IEDB_Immunogenicity-3.0）")
    WORKDIR.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONUTF8="1")

    # ── 读 backbone，按 allele_tag 聚合所有需打分的肽（MT ∪ WT，去重）────────
    rows = []
    allele_peps = defaultdict(set)          # allele_tag → {pep_upper}
    allele_original = {}                    # allele_tag → 原始 HLA 串（仅记录）
    dropped = 0
    with open(BACKBONE, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
            tag = hla_to_iedb(r["HLA_Allele"].strip())
            allele_original.setdefault(tag, r["HLA_Allele"].strip())
            for col in ("MT_Subpeptide", "WT_Subpeptide"):
                pep = (r.get(col) or "").strip().upper()
                if not pep:
                    continue  # 空 WT（indel 肽无 WT）→ 不送工具，回贴时留空
                if is_clean_pep(pep):
                    allele_peps[tag].add(pep)
                else:
                    dropped += 1  # 含非标准氨基酸 → 不送工具，回贴时 NaN

    alleles = sorted(allele_peps.keys())
    print(f"[prep] backbone={len(rows)} 行 | 唯一 allele={len(alleles)} | 非标准肽丢弃(置NaN)={dropped}")
    for tag in alleles:
        sup = tag in SUPPORTED_ALLELES
        print(f"[prep]   {tag:<12} ({allele_original.get(tag):<14}) "
              f"{'spec-mask' if sup else 'default-mask':<12} {len(allele_peps[tag])} uniq pep")

    # ── 逐 allele 写 txt + 调工具打分 ────────────────────────────────────────
    run_tags = alleles[:args.smoke] if args.smoke else alleles
    score_dict = {}  # (pep_upper, allele_tag) → score
    for i, tag in enumerate(run_tags, 1):
        is_sup = tag in SUPPORTED_ALLELES
        pep_list = sorted(allele_peps[tag])
        pep_file = WORKDIR / f"{allele_tag_to_file_tag(tag)}.txt"
        pep_file.write_text("\n".join(pep_list) + "\n", encoding="utf-8")
        sc = score_allele(TOOL, tag, is_sup, pep_file, env)
        for pep, v in sc.items():
            score_dict[(pep, tag)] = v
        smin = min(sc.values()) if sc else float("nan")
        smax = max(sc.values()) if sc else float("nan")
        print(f"[run] [{i}/{len(run_tags)}] {tag} ({'spec' if is_sup else 'dflt'}) "
              f"{len(sc)} scores | range [{smin:.4f}, {smax:.4f}]")

    if args.smoke:
        print(f"\n[smoke] 跑了 {len(run_tags)} 个 allele，工具可跑、分数在合理区间。未产 CSV。")
        return

    # ── 回贴 bb_idx，写 IEDB_Calis_official.csv ─────────────────────────────
    def fmt(pep, tag):
        v = score_dict.get((pep, tag))
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""  # NaN → 空（pandas 读为 NaN）
        return str(round(v, 6))

    n_mt = n_wt = n_mt_nan = n_wt_nan = 0
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bb_idx", "MT_IEDB_Calis", "WT_IEDB_Calis"])
        w.writeheader()
        for r in rows:
            tag = hla_to_iedb(r["HLA_Allele"].strip())
            mt = (r.get("MT_Subpeptide") or "").strip().upper()
            wt = (r.get("WT_Subpeptide") or "").strip().upper()
            mt_s = fmt(mt, tag) if mt else ""
            wt_s = fmt(wt, tag) if wt else ""  # 空 WT → 留空，不报错
            n_mt += mt_s != ""
            n_wt += wt_s != ""
            n_mt_nan += mt_s == ""
            n_wt_nan += wt_s == ""
            w.writerow({"bb_idx": r["bb_idx"], "MT_IEDB_Calis": mt_s, "WT_IEDB_Calis": wt_s})

    print(f"\n[parse] 写 {OUT}  ({len(rows)} 行)")
    print(f"[parse]   MT_IEDB_Calis: {n_mt} found / {n_mt_nan} NaN")
    print(f"[parse]   WT_IEDB_Calis: {n_wt} found / {n_wt_nan} NaN")
    print(f"[parse]   方向：score 越高越免疫原（无翻转）")


if __name__ == "__main__":
    main()
