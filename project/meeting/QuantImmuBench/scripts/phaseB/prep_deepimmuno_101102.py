# -*- coding: utf-8 -*-
"""
prep_deepimmuno_101102.py — Phase B：从订正 backbone_101102 派生 DeepImmuno 输入。

唯一订正源 = scripts/out/phaseB/backbone_101102.csv（已过闸门1，HLA_Allele 订正真值）。
绝不读任何旧的 deepimmuno_input*.csv。

DeepImmuno 限制：仅支持 9-mer / 10-mer。本脚本过滤 Window_Size∈{9,10} 的行，
MT_Subpeptide 与 WT_Subpeptide 都纳入（去重），转 DeepImmuno HLA 格式（去冒号）。

产出（scripts/out/phaseB/）:
    deepimmuno_input_101102.csv   DeepImmuno 批量输入（无表头，两列 peptide,HLA_di）
    （映射回 bb_idx 由 parse 脚本从 backbone 重算，无需中间 map 文件）

闸门: 断言输入里每个 HLA 仍是订正真值（去冒号格式），否则 raise。
"""
import os
import sys
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PHASEB = os.path.join(ROOT, "scripts", "out", "phaseB")
BACKBONE = os.path.join(PHASEB, "backbone_101102.csv")
OUT = os.path.join(PHASEB, "deepimmuno_input_101102.csv")

VALID_LEN = {9, 10}

# 订正真值（去冒号 DeepImmuno 格式）— 用于闸门自证
TRUTH_DI = {
    "HLA-A*6601", "HLA-B*4001", "HLA-B*5701", "HLA-C*0602",  # P101
    "HLA-A*0201", "HLA-B*3503", "HLA-B*3801",                # P102
}


def hla_to_deepimmuno(hla_std: str) -> str:
    """HLA-A*66:01 → HLA-A*6601（去冒号，保留星号）。"""
    return str(hla_std).replace(":", "")


def main():
    df = pd.read_csv(BACKBONE)

    # 仅 Window_Size∈{9,10}（DeepImmuno 死限）；其余 mer 本工具本就 NaN，正常跳过
    sub = df[df["Window_Size"].isin(VALID_LEN) & df["HLA_Allele"].notna()].copy()

    # 展开 MT + WT 两套肽，统一列名
    mt = sub[["MT_Subpeptide", "HLA_Allele"]].rename(
        columns={"MT_Subpeptide": "peptide"})
    wt = sub[["WT_Subpeptide", "HLA_Allele"]].rename(
        columns={"WT_Subpeptide": "peptide"})
    allp = pd.concat([mt, wt], ignore_index=True)

    # 子肽长度再过一遍（WT 极端情况可能短于 9/10），去空
    allp = allp[allp["peptide"].apply(lambda x: len(str(x)) in VALID_LEN)].copy()

    # 转 DeepImmuno HLA 格式
    allp["HLA_di"] = allp["HLA_Allele"].apply(hla_to_deepimmuno)

    # 闸门：每个 HLA 必须是订正真值
    got = set(allp["HLA_di"].unique())
    bad = got - TRUTH_DI
    if bad:
        raise SystemExit(
            f"[闸门 FAIL] 出现非订正真值 HLA: {sorted(bad)}\n"
            f"  → backbone 可能含旧伪迹数据，停止。")
    print(f"[闸门 PASS] 输入 HLA 全为订正真值 {sorted(got)}")

    # unique (peptide, HLA_di) 去重 → 无表头两列写盘
    uniq = allp[["peptide", "HLA_di"]].drop_duplicates().reset_index(drop=True)
    uniq.to_csv(OUT, index=False, header=False, encoding="utf-8")

    print(f"[DONE] 写 {OUT}  unique (peptide,HLA)={len(uniq)}")
    print(f"  9/10-mer backbone 行={len(sub)} | MT+WT 展开去空={len(allp)}")
    print(f"  → 下一步 WSL conda deepimmuno 跑 multiple 模式，"
          f"再用 parse_deepimmuno_101102.py 映射回 bb_idx。")


if __name__ == "__main__":
    main()
