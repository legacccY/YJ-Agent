# -*- coding: utf-8 -*-
"""run_mhcseqnet_official.py — MHCSeqNet 官方数据预测（HPC 跑）。
服务 quantimmu-bench §Phase0 W2-presml。lever=补 MHCSeqNet 呈递分。

env: envs/immuneapp (py3.7 + tf1.15 + keras2.3.1 + sklearn 已装)。
CLI（已 Sample 烟测核实，2026-06-30）:
  cd tools_repos/MHCSeqNet
  python MHCSeqNet.py -p PretrainedModels/sequence_model/ -m sequence -i paired PEP ALLELE OUT
  ⚠️ -p 必须尾斜杠（源码 model_path+"model_%d.h5" 无分隔符）
  PEP/ALLELE 各单列无表头，行对齐（paired）；ALLELE 带星 HLA-A*02:01。
  OUT = TSV `peptide\tallele\tprob` 无表头。prob∈[0,1] 越高越强。

流程：
  读 mhcseqnet_input_official.csv(peptide,HLA_Allele[带星]) → 过滤 supported_alleles.txt
  → 写 pep/allele 临时文件 → 调 CLI → 读 OUT → 写 mhcseqnet_raw.csv(peptide,HLA_Allele,prob)。
  不支持的等位/超长肽 → 不喂（parse 阶段诚实 NaN）。

用法（HPC，cd 项目根）:
  conda activate envs/immuneapp
  python official_inputs/hpc_official/run_mhcseqnet_official.py \
     --input official_inputs/out_official/mhcseqnet_input_official.csv \
     --repo  tools_repos/MHCSeqNet \
     --out   official_inputs/out_official/mhcseqnet_raw.csv
"""
import argparse, subprocess, sys, tempfile, os
from pathlib import Path
import pandas as pd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--smoke", type=int, default=0)
    a = ap.parse_args()

    repo = Path(a.repo).resolve()
    model_dir = repo / "PretrainedModels" / "sequence_model"
    sup_file = model_dir / "supported_alleles.txt"
    supported = set()
    if sup_file.exists():
        supported = {l.strip() for l in sup_file.read_text().splitlines() if l.strip()}
    print(f"[supported] {len(supported)} alleles in supported_alleles.txt", flush=True)

    df = pd.read_csv(a.input)
    df = df[["peptide", "HLA_Allele"]].dropna().drop_duplicates()
    if a.smoke:
        df = df.head(a.smoke)
    n0 = len(df)

    # 覆盖诊断：我们的 26 等位哪些 supported
    ours = sorted(df["HLA_Allele"].unique())
    if supported:
        miss = [h for h in ours if h not in supported]
        print(f"[coverage] 输入 {len(ours)} 等位，unsupported {len(miss)}: {miss}", flush=True)
        df = df[df["HLA_Allele"].isin(supported)].copy()
    print(f"[input] {n0} 对 → 喂 {len(df)} 对（过滤 unsupported 后）", flush=True)
    if df.empty:
        print("[ERR] 无 supported 对可跑", file=sys.stderr); sys.exit(2)

    # 写 pep/allele 行对齐临时文件
    tmpd = Path(tempfile.mkdtemp(prefix="seqnet_"))
    pep_f = tmpd / "pep.txt"; al_f = tmpd / "allele.txt"; out_f = tmpd / "out.tsv"
    pep_f.write_text("\n".join(df["peptide"].tolist()) + "\n")
    al_f.write_text("\n".join(df["HLA_Allele"].tolist()) + "\n")

    cmd = [sys.executable, "MHCSeqNet.py",
           "-p", "PretrainedModels/sequence_model/", "-m", "sequence", "-i", "paired",
           str(pep_f), str(al_f), str(out_f)]
    print(f"[run] cwd={repo} :: {' '.join(cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=str(repo))
    if r.returncode != 0 or not out_f.exists():
        print(f"[ERR] MHCSeqNet 失败 rc={r.returncode}", file=sys.stderr); sys.exit(3)

    rows = []
    for line in out_f.read_text().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        rows.append((parts[0], parts[1], float(parts[2])))
    raw = pd.DataFrame(rows, columns=["peptide", "HLA_Allele", "prob"])
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    raw.to_csv(a.out, index=False)
    print(f"[OUT] {a.out}  {len(raw)} 行  prob[min={raw.prob.min():.4f},max={raw.prob.max():.4f}]", flush=True)

if __name__ == "__main__":
    main()
