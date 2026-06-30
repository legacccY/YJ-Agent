"""
build_balanced_trainset.py — QuantImmuBench / NeoTImmuML 忠实复现训练集
=====================================================================
用 TumorAgDB2.0 (https://tumoragdb.com.cn) 原始带标数据重建论文口径的平衡训练集，
还原 NeoTImmuML 工具的真实能力（非弱化降采样——论文自己就是把丰富负样本平衡到正样本数）。

论文构集口径 (Front. Immunol. 2025, Methods):
  正 (immunogenicity=1): 功能实验(ELISPOT/FACS)确认免疫原 + IEDB 人 T 细胞表位
  负 (immunogenicity=0): TESLA/IEDB 非免疫原 + dbSNP 模拟
  => 论文把负样本【平衡到正样本数】。本脚本同口径：正样本尽量凑满真实带标肽，
     负样本随机下采样到正样本数 (random_state=42)。

数据源 (scripts/neotimmuml/train_data/tumoragdb/，dl_tumoragdb.py 从官方文件服务下载):
  正样本文件 → 取各自肽列，标签用文件自带 immunogenicity 列(应=1)
    T-mTSA-postive-Homo sapiens-8~12.xlsx        肽列=Peptide      (IEDB T 细胞激活，主正源)
    immunogenic Neo-peptide Dataset.xlsx         肽列=mutant_seq
    immunogenic Mutation Dataset.xlsx            肽列=mutant_seq
    Validated Immunogenic Neoantigen Data.xlsx   肽列=Peptide
  负样本文件 → 标签应=0
    Non-immunogenic Neo-peptide Dataset.xlsx     肽列=Peptide
    Non-immunogenic Mutation Dataset.xlsx        肽列=mutant_seq

口径说明（写入 LOG / 论文）：
  - 这是【忠实复现】(真实带标源数据重建平衡集 + 论文超参)，非 bit-exact
    (论文精确 5156:5156 训练 CSV + 预训练权重未公开，需邮件作者)。
  - 标签以每个文件自带 immunogenicity 列为准；同肽跨源标签冲突 → 丢弃(歧义，报数)。
  - 长度过滤 8-13mer + 仅标准 20 AA + dedup（与 extract_peptides.py 一致）。

用法:
  python scripts/neotimmuml/build_balanced_trainset.py \
      [--src-dir scripts/neotimmuml/train_data/tumoragdb] \
      [--output  scripts/neotimmuml/train_data/trainset_balanced.csv] \
      [--min_len 8] [--max_len 13] [--seed 42]
"""

import argparse
import pathlib
import sys

import pandas as pd

VALID_AAS = set("ACDEFGHIKLMNPQRSTVWY")

# 文件 → 肽列名（标签一律用文件自带 immunogenicity 列）
POS_FILES = {
    "T-mTSA-postive-Homo sapiens-8~12.xlsx": "Peptide",
    "immunogenic Neo-peptide Dataset.xlsx": "mutant_seq",
    "immunogenic Mutation Dataset.xlsx": "mutant_seq",
    "Validated Immunogenic Neoantigen Data.xlsx": "Peptide",
}
NEG_FILES = {
    "Non-immunogenic Neo-peptide Dataset.xlsx": "Peptide",
    "Non-immunogenic Mutation Dataset.xlsx": "mutant_seq",
}


def is_valid(pep, min_len, max_len):
    if not isinstance(pep, str):
        return False
    pep = pep.strip().upper()
    return min_len <= len(pep) <= max_len and all(c in VALID_AAS for c in pep)


def load_pool(src_dir, files, expected_label, min_len, max_len):
    """读一组文件 → DataFrame(Peptide, immunogenicity)，用文件自带 immunogenicity 列。"""
    frames = []
    for fname, pepcol in files.items():
        path = src_dir / fname
        if not path.exists():
            print(f"[WARN] 缺文件，跳过: {path}", file=sys.stderr)
            continue
        df = pd.read_excel(str(path), engine="openpyxl")
        if pepcol not in df.columns:
            sys.exit(f"[ERR] {fname} 无肽列 '{pepcol}'，实有 {list(df.columns)[:8]}...")
        if "immunogenicity" not in df.columns:
            sys.exit(f"[ERR] {fname} 无 immunogenicity 列")
        sub = df[[pepcol, "immunogenicity"]].copy()
        sub.columns = ["Peptide", "immunogenicity"]
        # 标签规范化
        sub["immunogenicity"] = pd.to_numeric(sub["immunogenicity"], errors="coerce")
        n_raw = len(sub)
        # 报文件自带标签分布（核对方向）
        vc = sub["immunogenicity"].value_counts(dropna=False).to_dict()
        # 肽过滤
        sub = sub[sub["Peptide"].apply(lambda p: is_valid(p, min_len, max_len))].copy()
        sub["Peptide"] = sub["Peptide"].str.strip().str.upper()
        n_off = (sub["immunogenicity"] != expected_label).sum()
        print(f"[LOAD] {fname}: 原 {n_raw} 行, 标签分布 {vc}, "
              f"过滤后 {len(sub)} 有效肽行 (其中 {n_off} 行标签≠预期{expected_label})",
              file=sys.stderr)
        frames.append(sub)
    if not frames:
        sys.exit("[ERR] 一个源文件都没读到")
    return pd.concat(frames, ignore_index=True)


def main():
    here = pathlib.Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--src-dir", default=str(here / "train_data" / "tumoragdb"))
    ap.add_argument("--output", default=str(here / "train_data" / "trainset_balanced.csv"))
    ap.add_argument("--min_len", type=int, default=8)
    ap.add_argument("--max_len", type=int, default=13)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    src = pathlib.Path(args.src_dir)
    pos = load_pool(src, POS_FILES, 1, args.min_len, args.max_len)
    neg = load_pool(src, NEG_FILES, 0, args.min_len, args.max_len)

    # 用文件自带标签为真值（不靠文件名硬贴）：正池保留 ==1，负池保留 ==0
    pos = pos[pos["immunogenicity"] == 1]
    neg = neg[neg["immunogenicity"] == 0]

    # 各自 dedup
    pos_set = set(pos["Peptide"].unique())
    neg_set = set(neg["Peptide"].unique())

    # 冲突肽（既出现在正又在负）→ 歧义，两边都丢
    conflict = pos_set & neg_set
    if conflict:
        print(f"[CONFLICT] {len(conflict)} 个肽正负标签冲突 → 两边丢弃(歧义)", file=sys.stderr)
    pos_clean = sorted(pos_set - conflict)
    neg_clean = sorted(neg_set - conflict)

    n_pos = len(pos_clean)
    n_neg_avail = len(neg_clean)
    print(f"[POOL] 正样本 unique 有效肽={n_pos}, 负样本可用 unique={n_neg_avail}", file=sys.stderr)
    if n_neg_avail < n_pos:
        print(f"[WARN] 负样本不足以平衡到正样本数({n_neg_avail}<{n_pos})，将用全部负样本",
              file=sys.stderr)

    # 负样本随机下采样到正样本数（论文口径：平衡到正样本数, random_state=seed）
    neg_series = pd.Series(neg_clean)
    n_take = min(n_pos, n_neg_avail)
    neg_sampled = neg_series.sample(n=n_take, random_state=args.seed).tolist()

    out = pd.DataFrame(
        {"Peptide": pos_clean + neg_sampled,
         "immunogenicity": [1] * n_pos + [0] * len(neg_sampled)}
    )
    # 打乱（可复现）
    out = out.sample(frac=1.0, random_state=args.seed).reset_index(drop=True)

    pathlib.Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)
    vc = out["immunogenicity"].value_counts().to_dict()
    lens = out["Peptide"].str.len().value_counts().sort_index().to_dict()
    print(f"[DONE] 平衡训练集 {len(out)} 行 (正={vc.get(1,0)}, 负={vc.get(0,0)}) → {args.output}",
          file=sys.stderr)
    print(f"[INFO] 肽长分布: {lens}", file=sys.stderr)


if __name__ == "__main__":
    main()
