# -*- coding: utf-8 -*-
"""
prep_101102_subset.py — Phase B 闸门 0/1：从订正 canonical backbone 抽 101/102 子集。

唯一订正源 = scripts/out/master_backbone.csv（已核 P101/P102 为订正等位）。
所有工具的 101/102 重推理输入都从本脚本产的 backbone_101102.csv 派生，
保证全链只读订正等位、绝不碰旧伪迹数据。

产出: scripts/out/phaseB/backbone_101102.csv（4018 子肽×HLA 行，bb_idx 对齐合表）
闸门 1（内置）: 断言 101/102 的 HLA_Allele 集 == 订正真值，不符即 raise。
"""
import os
import sys
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKBONE = os.path.join(ROOT, "scripts", "out", "master_backbone.csv")
OUTDIR   = os.path.join(ROOT, "scripts", "out", "phaseB")
OUT      = os.path.join(OUTDIR, "backbone_101102.csv")

# 订正真值（HLA-FIX2 自证，三方互证）— canonical `HLA-A*66:01` 格式
TRUTH = {
    "101": {"HLA-A*66:01", "HLA-B*40:01", "HLA-B*57:01", "HLA-C*06:02"},
    "102": {"HLA-A*02:01", "HLA-B*35:03", "HLA-B*38:01"},
}


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    df = pd.read_csv(BACKBONE)
    pid = df["Patient_ID"].astype(str).str.split(".").str[0]
    sub = df[pid.isin(["101", "102"])].copy()
    sub_pid = sub["Patient_ID"].astype(str).str.split(".").str[0]

    # ── 闸门 1：HLA_Allele 集必须 == 订正真值 ───────────────────────────────
    for p in ["101", "102"]:
        got = set(sub.loc[sub_pid == p, "HLA_Allele"].dropna().astype(str).unique())
        exp = TRUTH[p]
        if got != exp:
            raise SystemExit(
                f"[闸门1 FAIL] P{p} HLA 不符订正真值\n  期望={sorted(exp)}\n  实得={sorted(got)}\n"
                f"  → backbone 可能是旧伪迹数据，停止 Phase B。")
        print(f"[闸门1 PASS] P{p} HLA == 订正真值 {sorted(exp)}")

    # ── 报告 + 落盘 ────────────────────────────────────────────────────────
    n_pep = sub["Peptide_ID"].nunique()
    n_pos = sub[sub["Elispot"] > 0]["Peptide_ID"].nunique()
    n_neg = sub[sub["Elispot"] <= 0]["Peptide_ID"].nunique()
    print(f"\n101/102 子集: 子肽×HLA 行={len(sub)} | 肽={n_pep}（阳{n_pos} 阴{n_neg}）"
          f" | bb_idx {sub['bb_idx'].min()}–{sub['bb_idx'].max()}")
    sub.to_csv(OUT, index=False)
    print(f"[DONE] 写 {OUT}  shape={sub.shape}")
    print("  → 13 个 HLA-dep 工具的 101/102 输入一律从这份派生（唯一订正源）。")


if __name__ == "__main__":
    main()
