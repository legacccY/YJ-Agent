#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
load_unified.py — 把已下的异构新抗原数据集统一成 reference/UNIFIED_GT_schema.md 的长表 schema。

服务 quantimmu-bench 数据组。一行 = 一肽 × 一 HLA × 一来源记录；多源标签语义不同
（binary / 序数 / 患者应答 / TCR confidence）分列存，不压成单一 label。

用法:
    python scripts/load_unified.py                 # 加载所有已下集 → 打印台账 + overlap
    python scripts/load_unified.py --out unified.csv   # 另存统一长表 csv

依赖: openpyxl（读 xlsx）。纯 CPU，零 GPU。Windows: 全部 encoding='utf-8',errors='replace' 防 gbk 坑。
数据根: project/meeting/QuantImmuBench/data/external/
"""
import csv, re, argparse, sys
from pathlib import Path
from collections import Counter

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))  # VDJdb/IEDB 长字段

ROOT = Path(__file__).resolve().parent.parent  # QuantImmuBench/
EXT = ROOT / "data" / "external"

AA = re.compile(r'^[ACDEFGHIKLMNPQRSTVWY]{8,25}$')

# ---- schema 列 ----
FIELDS = ["peptide", "peptide_wt", "hla", "hla_class", "pep_key",
          "label_binary", "label_ordinal", "magnitude_value", "magnitude_unit",
          "magnitude_assay", "resp_tested", "resp_positive", "resp_freq",
          "source_dataset", "source_study_id", "disease", "is_neoantigen",
          "note"]


def blank():
    return {k: None for k in FIELDS}


# ---- HLA 规范化 → HLA-A*02:01；返回 (canonical, 4digit) ----
_hla_re = re.compile(r'(?:HLA-)?([A-Z]+)\*?(\d{2,4}):?(\d{0,2})', re.I)

def norm_hla(raw):
    if not raw:
        return None, None
    s = str(raw).strip().upper().replace(' ', '')
    m = _hla_re.match(s)
    if not m:
        return None, None
    gene, f1, f2 = m.group(1), m.group(2), m.group(3)
    # 紧凑 4 位 '0201' → field1=02 field2=01
    if not f2 and len(f1) == 4:
        f1, f2 = f1[:2], f1[2:]
    if not f2:
        return None, None  # 只有 supertype/单组，无法配 4 位
    canon = f"HLA-{gene}*{f1}:{f2}"
    four = f"{gene}*{f1}:{f2}"
    return canon, four


def norm_pep(p):
    return (p or '').strip().upper()


def pep_key(pep, four):
    if not pep:
        return None
    return f"{pep}|{four or 'NA'}"


# ---- 各源 loader：yield dict(schema) ----
def load_itsndb():
    f = EXT / "ITSNdb" / "data" / "ITSNdb.csv"
    if not f.exists():
        return
    with open(f, encoding='utf-8', errors='replace') as fh:
        for row in csv.DictReader(fh):
            r = blank()
            r['peptide'] = norm_pep(row.get('Neoantigen'))
            r['peptide_wt'] = norm_pep(row.get('WT')) or None
            r['hla'], four = norm_hla(row.get('HLA'))
            r['hla_class'] = 'I'
            r['pep_key'] = pep_key(r['peptide'], four)
            r['label_binary'] = 1 if (row.get('NeoType') or '').strip() == 'Positive' else 0
            r['source_dataset'] = 'ITSNdb'
            r['source_study_id'] = (row.get('Paper') or row.get('Author') or '').strip()[:80] or None
            r['disease'] = (row.get('Tumor') or '').strip() or None
            r['is_neoantigen'] = True
            yield r


def load_prime(include_random=False):
    import openpyxl
    f = EXT / "PRIME" / "TableS4.xlsx"
    if not f.exists():
        return
    wb = openpyxl.load_workbook(f, read_only=True)
    ws = wb.active
    it = ws.iter_rows(values_only=True)
    next(it); next(it)  # 标题行 + 表头行
    for row in it:
        if row[0] is None:
            continue
        rand = row[9]
        if rand == 1 and not include_random:
            continue
        r = blank()
        r['peptide'] = norm_pep(row[0])           # Mutant
        r['hla'], four = norm_hla(row[1])          # Allele
        r['hla_class'] = 'I'
        r['pep_key'] = pep_key(r['peptide'], four)
        r['label_binary'] = 1 if row[7] == 1 else 0  # Immunogenicity
        r['source_dataset'] = 'PRIME'
        r['source_study_id'] = (str(row[8]).strip() if row[8] else None)  # SourceProt
        r['is_neoantigen'] = True
        r['note'] = 'random_negative' if rand == 1 else 'iedb_derived_train'
        yield r


def load_vdjdb():
    f = EXT / "vdjdb" / "vdjdb-2026-06-03" / "vdjdb.slim.txt"
    if not f.exists():
        return
    with open(f, encoding='utf-8', errors='replace') as fh:
        r0 = csv.DictReader(fh, delimiter='\t')
        for row in r0:
            pep = norm_pep(row.get('antigen.epitope'))
            if not AA.match(pep):
                continue
            r = blank()
            r['peptide'] = pep
            r['hla'], four = norm_hla(row.get('mhc.a'))
            r['hla_class'] = 'I' if (row.get('mhc.class') == 'MHCI') else 'II'
            r['pep_key'] = pep_key(pep, four)
            # 不产 label_binary：VDJdb 是 TCR 维度
            r['source_dataset'] = 'VDJdb'
            r['source_study_id'] = (row.get('reference.id') or '').strip() or None
            r['note'] = f"tcr_pmhc_only;confidence={row.get('vdjdb.score')}"
            yield r


def load_iedb(limit=None):
    """IEDB tcell_full_v3：双行表头，Epitope/Name=idx11，Qualitative=idx122。
    只取线性 8-25mer。大文件，可 --limit 截断试跑。"""
    f = EXT / "tcell_full_v3.csv"
    if not f.exists():
        return
    with open(f, newline='', encoding='utf-8', errors='replace') as fh:
        rr = csv.reader(fh)
        cat = next(rr); fld = next(rr)
        # 定位列
        def idx(c, n):
            for i, (a, b) in enumerate(zip(cat, fld)):
                if a == c and b == n:
                    return i
            return None
        i_pep = idx('Epitope', 'Name')
        i_qual = idx('Assay', 'Qualitative Measurement')
        i_quant = idx('Assay', 'Quantitative measurement')
        i_units = idx('Assay', 'Units')
        i_method = idx('Assay', 'Method')
        i_tested = idx('Assay', 'Number of Subjects Tested')
        i_pos = idx('Assay', 'Number of Subjects Positive')
        i_freq = idx('Assay', 'Response Frequency (%)')
        i_dis = idx('Host', 'Disease')
        n = 0
        for row in rr:
            if i_pep is None or len(row) <= i_pep:
                continue
            pep = norm_pep(row[i_pep])
            if not AA.match(pep):
                continue
            r = blank()
            r['peptide'] = pep
            r['pep_key'] = pep_key(pep, None)  # IEDB HLA 列复杂，HLA 留待精解；先肽级 key
            qual = (row[i_qual] if i_qual and len(row) > i_qual else '') or ''
            if qual.startswith('Positive'):
                r['label_binary'] = 1
                r['label_ordinal'] = {'Positive-High': 3, 'Positive-Intermediate': 2,
                                      'Positive-Low': 1}.get(qual, None)
            elif qual == 'Negative':
                r['label_binary'] = 0
            for key, ii in [('magnitude_value', i_quant), ('magnitude_unit', i_units),
                            ('magnitude_assay', i_method), ('resp_tested', i_tested),
                            ('resp_positive', i_pos), ('resp_freq', i_freq),
                            ('disease', i_dis)]:
                if ii is not None and len(row) > ii and row[ii] not in ('', None):
                    r[key] = row[ii]
            r['source_dataset'] = 'IEDB'
            yield r
            n += 1
            if limit and n >= limit:
                return


LOADERS = {'ITSNdb': load_itsndb, 'PRIME': load_prime, 'VDJdb': load_vdjdb}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=None, help='另存统一长表 csv')
    ap.add_argument('--with-iedb', action='store_true', help='含 IEDB（慢，1.3G）')
    ap.add_argument('--iedb-limit', type=int, default=None)
    args = ap.parse_args()

    rows = []
    for name, fn in LOADERS.items():
        rs = list(fn())
        rows.extend(rs)
        labs = Counter(r['label_binary'] for r in rs)
        print(f"[{name}] {len(rs)} rows | label_binary: {dict(labs)} | uniq pep: {len(set(r['peptide'] for r in rs))}")
    if args.with_iedb:
        rs = list(load_iedb(limit=args.iedb_limit))
        rows.extend(rs)
        print(f"[IEDB] {len(rs)} rows | uniq pep: {len(set(r['peptide'] for r in rs))}")

    # overlap 实测（肽级，泄漏上界）
    def peps(src):
        return set(r['peptide'] for r in rows if r['source_dataset'] == src and r['peptide'])
    its, prime = peps('ITSNdb'), peps('PRIME')
    print(f"\n[overlap] ITSNdb({len(its)}) ∩ PRIME({len(prime)}) = {len(its & prime)} "
          f"({100*len(its & prime)//max(len(its),1)}%)")

    if args.out:
        with open(args.out, 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        print(f"\n→ wrote {len(rows)} rows to {args.out}")


if __name__ == '__main__':
    main()
