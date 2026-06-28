"""
run_local.py — IEDB Calis 本地全量 runner（Windows，CPU，纯统计秒级）
遍历 allele_manifest.csv，对每个 allele 调 predict_immunogenicity.py：
  - is_supported=True  → --allele=<tag>（allele-specific mask）
  - is_supported=False → 默认 mask（P1,P2,C-term）
每 allele 输出写 scores/<file_tag>_scores.txt（含工具 stdout 原样）。

用法: python run_local.py [--smoke N]
"""
import argparse, csv, subprocess, sys, os
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE / 'immunogenicity' / 'predict_immunogenicity.py'
ROOT = HERE.parents[2]  # QuantImmuBench/
INP = ROOT / 'scripts' / 'out' / 'newtools' / 'iedb_calis_inputs'
SCORES = ROOT / 'scripts' / 'out' / 'newtools' / 'iedb_calis_scores'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--smoke', type=int, default=0, help='只跑前 N 个 allele')
    args = ap.parse_args()
    SCORES.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONUTF8='1')

    with open(INP / 'allele_manifest.csv', newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    if args.smoke:
        rows = rows[:args.smoke]

    n_ok = 0
    for i, r in enumerate(rows, 1):
        tag = r['allele_tag']
        is_sup = r['is_supported'].strip().lower() == 'true'
        pep_file = INP / r['pep_filename']
        out_file = SCORES / r['scores_filename']
        cmd = [sys.executable, str(TOOL)]
        if is_sup:
            cmd.append(f'--allele={tag}')
        cmd.append(str(pep_file))
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600)
        except subprocess.TimeoutExpired:
            print(f'[{i}/{len(rows)}] {tag} TIMEOUT', file=sys.stderr)
            continue
        if res.returncode != 0:
            print(f'[{i}/{len(rows)}] {tag} ERR rc={res.returncode}: {res.stderr[:200]}', file=sys.stderr)
            continue
        out_file.write_text(res.stdout, encoding='utf-8')
        n_ok += 1
        print(f'[{i}/{len(rows)}] {tag} ({"spec" if is_sup else "dflt"}) {r["pep_count"]} peps -> {out_file.name}')

    print(f'\n[run] {n_ok}/{len(rows)} allele 成功 -> {SCORES}')


if __name__ == '__main__':
    main()
