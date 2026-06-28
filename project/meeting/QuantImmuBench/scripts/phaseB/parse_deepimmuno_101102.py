# -*- coding: utf-8 -*-
"""
parse_deepimmuno_101102.py — Phase B：DeepImmuno 输出映射回 bb_idx。

读 DeepImmuno 批量输出（deepimmuno-cnn-result.txt，tab 分隔 3 列
peptide / HLA / immunogenicity）+ 订正 backbone_101102.csv，
按 (peptide, HLA_di) 查分，逐 bb_idx 填 MT / WT 分。

仅输出 Window_Size∈{9,10} 的 bb_idx（DeepImmuno 适用面）；
WT 子肽非 9/10-mer 或缺分则该格留空（正常）。

用法:
    python parse_deepimmuno_101102.py <deepimmuno-cnn-result.txt>
  缺省路径 = scripts/out/phaseB/deepimmuno-cnn-result.txt

产出:
    scripts/out/phaseB/DeepImmuno_101102.csv   列 = bb_idx, MT_DeepImmuno, WT_DeepImmuno

自校验（内置打印）:
    ① 输入分文件 HLA 全为订正真值
    ② 输出行数 == 9/10-mer backbone 行数
    ③ 分数范围 0-1
"""
import os
import sys
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PHASEB = os.path.join(ROOT, "scripts", "out", "phaseB")
BACKBONE = os.path.join(PHASEB, "backbone_101102.csv")
OUT = os.path.join(PHASEB, "DeepImmuno_101102.csv")
DEFAULT_RESULT = os.path.join(PHASEB, "deepimmuno-cnn-result.txt")

VALID_LEN = {9, 10}

TRUTH_DI = {
    "HLA-A*6601", "HLA-B*4001", "HLA-B*5701", "HLA-C*0602",  # P101
    "HLA-A*0201", "HLA-B*3503", "HLA-B*3801",                # P102
}


def hla_to_deepimmuno(hla_std: str) -> str:
    """HLA-A*66:01 → HLA-A*6601（去冒号，保留星号）。"""
    return str(hla_std).replace(":", "")


def main():
    result_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RESULT
    if not os.path.exists(result_path):
        raise SystemExit(f"[FAIL] 找不到 DeepImmuno 输出: {result_path}")

    # ── 读输出，构建 (peptide, HLA_di) → score 查找表 ────────────────────────
    res = pd.read_csv(result_path, sep="\t")
    # 兼容大小写/位置：取前 3 列为 peptide / HLA / immunogenicity
    res.columns = [c.strip() for c in res.columns]
    pep_c, hla_c, sc_c = res.columns[0], res.columns[1], res.columns[2]
    res[sc_c] = pd.to_numeric(res[sc_c], errors="coerce")

    # 自校验①：输出 HLA 全为订正真值
    out_hla = set(res[hla_c].astype(str).unique())
    bad = out_hla - TRUTH_DI
    if bad:
        raise SystemExit(
            f"[自校验① FAIL] 输出含非订正真值 HLA: {sorted(bad)}")
    print(f"[自校验① PASS] 输出 HLA 全为订正真值 {sorted(out_hla)}")

    score = {(str(r[pep_c]), str(r[hla_c])): r[sc_c]
             for _, r in res.iterrows()}

    def lookup(pep, hla_std):
        if not isinstance(pep, str) or len(pep) not in VALID_LEN:
            return None
        return score.get((pep, hla_to_deepimmuno(hla_std)))

    # ── 逐 bb_idx 填分（仅 9/10-mer 行）─────────────────────────────────────
    df = pd.read_csv(BACKBONE)
    sub = df[df["Window_Size"].isin(VALID_LEN) & df["HLA_Allele"].notna()].copy()

    sub["MT_DeepImmuno"] = sub.apply(
        lambda r: lookup(r["MT_Subpeptide"], r["HLA_Allele"]), axis=1)
    sub["WT_DeepImmuno"] = sub.apply(
        lambda r: lookup(r["WT_Subpeptide"], r["HLA_Allele"]), axis=1)

    out = sub[["bb_idx", "MT_DeepImmuno", "WT_DeepImmuno"]].copy()
    out.to_csv(OUT, index=False, encoding="utf-8")

    # ── 自校验②③ ─────────────────────────────────────────────────────────
    n_mt = out["MT_DeepImmuno"].notna().sum()
    n_wt = out["WT_DeepImmuno"].notna().sum()
    print(f"[自校验② ] 输出行数={len(out)} (== 9/10-mer backbone 行) | "
          f"MT 有分={n_mt} WT 有分={n_wt}")
    vals = pd.concat([out["MT_DeepImmuno"], out["WT_DeepImmuno"]]).dropna()
    if len(vals):
        vmin, vmax = vals.min(), vals.max()
        ok = (vmin >= 0) and (vmax <= 1)
        print(f"[自校验③ {'PASS' if ok else 'FAIL'}] 分数范围 "
              f"[{vmin:.4f}, {vmax:.4f}]" + ("" if ok else "  ⚠️ 越界 0-1"))
    else:
        print("[自校验③ WARN] 无任何有效分数 —— 检查 HLA 是否被 DeepImmuno 支持")

    print(f"[DONE] 写 {OUT}")


if __name__ == "__main__":
    main()
