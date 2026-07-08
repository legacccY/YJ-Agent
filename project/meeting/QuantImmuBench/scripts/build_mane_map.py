#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_mane_map.py
服务: quantimmu-bench / 切肽口径大改 §改动②/③ (从原始蛋白定点切 mut-spanning 窗)

解析本地 MANE flat file -> gene 定位真源 (symbol / HGNC_ID / GeneID -> MANE Select
蛋白全长)。给 cut_from_protein.py 在肽窗溢出 SLP 时锚定原始蛋白补窗。

================== 输入 (只读, 主线已下到 data/external/MANE/) ==================
  MANE.GRCh38.v1.5.summary.txt.gz        (tab; 列 #NCBI_GeneID Ensembl_Gene HGNC_ID
      symbol name RefSeq_nuc RefSeq_prot Ensembl_nuc Ensembl_prot MANE_status ...)
  MANE.GRCh38.v1.5.refseq_protein.faa.gz (FASTA; header '>NP_xxxxx.x <desc> [Homo sapiens]',
      accession(含版本) == summary 的 RefSeq_prot)
  (可选) hgnc_complete_set.txt            (别名二次解析; 不存在则软降级跳过)

================== 关键铁律 ==================
  - 逐记录解析 FASTA (一条 accession 一条序列), 绝不 ''.join(所有行) 全拼
    -> 全拼是袁脚本 DLC1 拉错蛋白的根因。
  - 主键 HGNC_ID/GeneID 优先, gene symbol 仅 fallback; GT 只有 gene symbol,
    先按 summary 官方 symbol 列直接命中 -> 命中即拿 HGNC_ID。
  - DLC1 自检: "DLC1" 官方符号命中的须是长蛋白 (真 DLC1≈1528aa) 而非 DYNLL1(89aa);
    不一致 -> warn + flag (不静默)。

================== 输出 ==================
  build_mane_map() 返回 dict:
    {
      "by_symbol":  {SYMBOL_UPPER: entry, ...},
      "by_hgnc":    {HGNC_ID:      entry, ...},
      "by_gene_id": {GeneID:       entry, ...},
      "by_alias":   {ALIAS_UPPER:  official_symbol_upper, ...},   # 无 hgnc_complete_set 则空
    }
    entry = {refseq_prot_acc, protein_seq, hgnc_id, gene_id, symbol}
  落 data/external/MANE/mane_map.parsed.json (缓存; 再跑优先读缓存)。

================== 跑法 (不在本脚本内跑; 交主线) ==================
  python scripts/build_mane_map.py            # 解析 + 落缓存 + 打自检
"""

import sys
import gzip
import json
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
MANE_DIR = ROOT / "data" / "external" / "MANE"
HGNC_DIR = ROOT / "data" / "external" / "HGNC"
CACHE_JSON = MANE_DIR / "mane_map.parsed.json"

# 真 DLC1 (deleted-in-liver-cancer 1, ARHGAP7) ≈1528aa; DYNLL1 别名亦叫 DLC1 但仅 89aa。
DLC1_MIN_LEN = 1000  # 命中长度 < 此值 -> 疑似拉到 DYNLL1, warn+flag


# ─────────────────────────────────────────────────────────────────────────
# 文件定位 (glob, 抗版本号变动)
# ─────────────────────────────────────────────────────────────────────────
def _find_one(dir_path, pattern):
    """glob 单一匹配; 0 或多命中报错 (不静默取第一个乱来)。"""
    hits = sorted(dir_path.glob(pattern))
    if not hits:
        raise SystemExit(f"[ERR] 未找到 {pattern} in {dir_path} (主线是否已下载 MANE?)")
    if len(hits) > 1:
        print(f"[WARN] {pattern} 多命中, 取首个: {[h.name for h in hits]}")
    return hits[0]


# ─────────────────────────────────────────────────────────────────────────
# 逐记录解析 FASTA (绝不全拼)
# ─────────────────────────────────────────────────────────────────────────
def parse_fasta(faa_gz):
    """
    逐记录解析: 遇 '>' 开新记录, 序列行只 append 到当前记录 (不跨记录拼接)。
    返回 {accession(含版本): protein_seq}。
    """
    seqs = {}
    acc = None
    buf = []
    with gzip.open(faa_gz, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith(">"):
                # 收束上一条记录 (仅当前记录的行, 不与下条混)
                if acc is not None:
                    seqs[acc] = "".join(buf)
                acc = line[1:].split()[0]   # '>NP_000005.3 desc' -> 'NP_000005.3'
                buf = []
            else:
                buf.append(line.strip())
        # 末条记录
        if acc is not None:
            seqs[acc] = "".join(buf)
    return seqs


# ─────────────────────────────────────────────────────────────────────────
# 解析 summary (按表头名取列, 不硬编码位置)
# ─────────────────────────────────────────────────────────────────────────
def parse_summary(summary_gz):
    """
    返回 records: [{gene_id, hgnc_id, symbol, refseq_prot}, ...] (仅 MANE Select/Plus)。
    列按 '#'-开头表头名定位。
    """
    records = []
    with gzip.open(summary_gz, "rt", encoding="utf-8") as fh:
        header = fh.readline().rstrip("\n").lstrip("#").split("\t")
        idx = {name: i for i, name in enumerate(header)}
        need = ["NCBI_GeneID", "HGNC_ID", "symbol", "RefSeq_prot"]
        for n in need:
            if n not in idx:
                raise SystemExit(f"[ERR] summary 缺列 {n}; 实际表头: {header}")
        for line in fh:
            if not line.strip():
                continue
            f = line.rstrip("\n").split("\t")
            if len(f) <= idx["RefSeq_prot"]:
                continue
            gene_id = f[idx["NCBI_GeneID"]].strip()      # 'GeneID:1'
            if gene_id.startswith("GeneID:"):
                gene_id = gene_id.split(":", 1)[1]        # -> '1'
            records.append({
                "gene_id": gene_id,
                "hgnc_id": f[idx["HGNC_ID"]].strip(),     # 'HGNC:5'
                "symbol": f[idx["symbol"]].strip(),
                "refseq_prot": f[idx["RefSeq_prot"]].strip(),  # 'NP_570602.2'
            })
    return records


# ─────────────────────────────────────────────────────────────────────────
# 别名二次解析 (可选; hgnc_complete_set.txt 缺则软降级)
# ─────────────────────────────────────────────────────────────────────────
def parse_alias_map(hgnc_dir=None):
    """
    读 hgnc_complete_set.txt -> {别名/旧名(大写): hgnc_id}。
    GT symbol 不命中 MANE 官方 symbol 时, 用此表 alias_symbol/prev_symbol -> hgnc_id,
    再回 MANE by_hgnc 命中 (如 CCDC130=prev_symbol -> HGNC:28118 -> YJU2B NP_110445.1)。
    文件不存在 -> 返回 {} 软降级 (保持现状)。优先 data/external/HGNC/, 回退 MANE_DIR。
    仅取 alias_symbol + prev_symbol -> hgnc_id (当前 symbol 由 MANE by_symbol 覆盖, 不重复入表避撞名)。
    """
    hgnc_file = None
    for d in ([hgnc_dir] if hgnc_dir else []) + [HGNC_DIR, MANE_DIR]:
        cand = d / "hgnc_complete_set.txt"
        if cand.exists():
            hgnc_file = cand
            break
    if hgnc_file is None:
        print("[info] 无 hgnc_complete_set.txt, 跳过别名解析 (软降级; GT symbol 若不命中官方符号会记 unmatched)")
        return {}
    alias_map = {}
    ambiguous = set()
    with open(hgnc_file, "r", encoding="utf-8") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        idx = {name: i for i, name in enumerate(header)}
        hgnc_i = idx.get("hgnc_id")
        cols = [idx.get(c) for c in ("alias_symbol", "prev_symbol")]
        if hgnc_i is None:
            print("[WARN] hgnc_complete_set 无 hgnc_id 列, 跳过别名解析")
            return {}
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) <= hgnc_i:
                continue
            hgnc_id = f[hgnc_i].strip()
            if not hgnc_id:
                continue
            for col_i in cols:
                if col_i is None or len(f) <= col_i:
                    continue
                # alias_symbol/prev_symbol 可能形如 "A|B|C" (HGNC 惯例, 含引号)
                for a in f[col_i].strip().strip('"').split("|"):
                    a = a.strip().strip('"').upper()
                    if not a:
                        continue
                    if a in alias_map and alias_map[a] != hgnc_id:
                        ambiguous.add(a)  # 同别名映到多 hgnc_id -> 歧义, 保留首个但记
                        continue
                    alias_map.setdefault(a, hgnc_id)
    print(f"[info] 别名映射: {len(alias_map)} 条 (alias/prev -> hgnc_id) 自 {hgnc_file.name}; "
          f"歧义(多 hgnc_id)保留首个 {len(ambiguous)} 条")
    return alias_map


# ─────────────────────────────────────────────────────────────────────────
# 主构建
# ─────────────────────────────────────────────────────────────────────────
def build_mane_map(use_cache=True):
    """
    解析 MANE summary + FASTA -> 定位真源 dict (见模块文档 输出节)。
    use_cache=True 且缓存存在 -> 直接读缓存 json (再跑不重解析)。
    """
    if use_cache and CACHE_JSON.exists():
        with open(CACHE_JSON, "r", encoding="utf-8") as fh:
            m = json.load(fh)
        # auto-heal: 缓存无别名但 HGNC 文件现已就位 -> 重建以纳入别名 (CCDC130 补漏)
        hgnc_present = (HGNC_DIR / "hgnc_complete_set.txt").exists() or \
                       (MANE_DIR / "hgnc_complete_set.txt").exists()
        if hgnc_present and not m.get("by_alias"):
            print("[info] 缓存无别名但 HGNC 文件已就位 -> 重建以纳入别名 (auto-heal)")
        else:
            print(f"[info] 读缓存 MANE map: {CACHE_JSON}  "
                  f"(by_symbol={len(m.get('by_symbol', {}))}, by_alias={len(m.get('by_alias', {}))})")
            return m

    summary_gz = _find_one(MANE_DIR, "MANE.*.summary.txt.gz")
    faa_gz = _find_one(MANE_DIR, "MANE.*.refseq_protein.faa.gz")
    print(f"[info] summary: {summary_gz.name}")
    print(f"[info] fasta  : {faa_gz.name}")

    seqs = parse_fasta(faa_gz)
    print(f"[info] FASTA 记录数(逐条, 未全拼): {len(seqs)}")
    records = parse_summary(summary_gz)
    print(f"[info] summary 记录数: {len(records)}")

    by_symbol, by_hgnc, by_gene_id = {}, {}, {}
    n_noseq = 0
    for rec in records:
        acc = rec["refseq_prot"]
        seq = seqs.get(acc)
        if seq is None:
            n_noseq += 1
            continue  # summary 有该 accession 但 FASTA 无序列 (罕见), 跳过
        entry = {
            "refseq_prot_acc": acc,
            "protein_seq": seq,
            "hgnc_id": rec["hgnc_id"],
            "gene_id": rec["gene_id"],
            "symbol": rec["symbol"],
        }
        sym_u = rec["symbol"].upper()
        if sym_u:
            by_symbol[sym_u] = entry
        if rec["hgnc_id"]:
            by_hgnc[rec["hgnc_id"]] = entry
        if rec["gene_id"]:
            by_gene_id[rec["gene_id"]] = entry
    if n_noseq:
        print(f"[WARN] {n_noseq} 条 summary accession 在 FASTA 无序列, 已跳过")

    alias_map = parse_alias_map()  # 默认优先 HGNC_DIR, 回退 MANE_DIR

    m = {
        "by_symbol": by_symbol,
        "by_hgnc": by_hgnc,
        "by_gene_id": by_gene_id,
        "by_alias": alias_map,
    }

    # ── DLC1 自检 (逐记录解析对不对的锚点) ──────────────────────────────
    _dlc1_selfcheck(by_symbol)

    # ── 落缓存 ──────────────────────────────────────────────────────────
    MANE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_JSON, "w", encoding="utf-8") as fh:
        json.dump(m, fh)  # 不 indent (蛋白序列很长, 省体积)
    print(f"[saved] {CACHE_JSON}  by_symbol={len(by_symbol)} by_hgnc={len(by_hgnc)} "
          f"by_gene_id={len(by_gene_id)} by_alias={len(alias_map)}")
    return m


def _dlc1_selfcheck(by_symbol):
    """DLC1 官方符号须命中长蛋白(≈1528aa); 命中短蛋白 -> 疑逐条解析串位, warn+flag。"""
    e = by_symbol.get("DLC1")
    if e is None:
        print("[WARN][DLC1-selfcheck] by_symbol 无 'DLC1' (MANE 里缺该符号?), 无法自检")
        return
    L = len(e["protein_seq"])
    if L >= DLC1_MIN_LEN:
        print(f"[OK][DLC1-selfcheck] DLC1 -> {e['refseq_prot_acc']} 长度 {L}aa "
              f"(>= {DLC1_MIN_LEN}, 真 DLC1≈1528, 逐条解析未串位)")
    else:
        print(f"[FLAG][DLC1-selfcheck] !!! DLC1 -> {e['refseq_prot_acc']} 仅 {L}aa "
              f"(< {DLC1_MIN_LEN}, 疑拉到 DYNLL1/89aa; 逐条解析可能串位, 人工核, 不静默通过)")


def main():
    m = build_mane_map(use_cache=False)  # 直跑强制重解析 + 落缓存
    # 抽样打印几个已知基因作 sanity
    for sym in ("DLC1", "PIK3CA", "AMACR", "TP53"):
        e = m["by_symbol"].get(sym.upper())
        if e:
            print(f"[sample] {sym:8s} -> {e['refseq_prot_acc']}  "
                  f"{len(e['protein_seq'])}aa  {e['hgnc_id']}  GeneID:{e['gene_id']}")
        else:
            print(f"[sample] {sym:8s} -> (未在 by_symbol; 可能官方符号不同, 走别名/unmatched)")
    print("[DONE] build_mane_map 完成")


if __name__ == "__main__":
    main()
