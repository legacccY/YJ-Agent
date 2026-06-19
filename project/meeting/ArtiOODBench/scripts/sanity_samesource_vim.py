"""
Sanity 负对照：检验 A-5 承重 ViM=1.0 是否被「in-sample vs out-of-sample 残差不对称」混杂，
而非纯 source-leakage。

背景（reviewer 攻击面 #1）：
  l3_ood_rerank._run_full_pipeline 用 feats_test = concat(feats_id, feats_ood)，
  即 ViM 的 fit 集 feats_id 同时是 test 的 ID 部分（in-sample）。
  500 样本 < 1024 维 → PCA 子空间永不满秩 → in-sample ID 残差≈0，
  任何 held-out 数据（同源或跨源）落在 null space → 残差>0。
  风险：ViM=1.0 可能是「in-sample(残差0) vs held-out(残差大)」的几何伪迹。

三个对照（每模态各跑，用已存盘 feats，不重抽）：
  C0 cross-source（真实设定复刻）：fit+id = source A 全量, ood = source B 全量。
     —— 复刻 l3 的 in-sample ID 设定，应 ≈ l3 报的 ~1.0。
  C1 same-source in-sample（关键证伪）：fit+id = A 前半, pseudo-ood = A 后半（同源 held-out）。
     —— 若 C1 也 ≈1.0 → 1.0 是 in-sample 伪迹，A-5 承重被混杂（坏）。
     —— 若 C1 ≈0.5 → 同源分不开，cross-source 的 1.0 是真 source 信号（承重稳）。
  C2 same-source held-out symmetric（干净负对照）：fit = A 前 1/3, id-test = A 中 1/3,
     pseudo-ood = A 后 1/3（id-test 与 pseudo-ood 都 held-out，对称）。应 ≈0.5。

  ΔAUROC = C0 - C1 = 扣除 in-sample 伪迹后的真 source 信号量。

输出：results/sanity_samesource_vim.csv
"""
import sys
from pathlib import Path
import numpy as np

# 复用 l3 的官方 ViM / Residual / auroc 实现（module-level，禁臆想重写）
sys.path.insert(0, str(Path(__file__).resolve().parent))
from l3_ood_rerank import method_vim, method_residual, auroc_numpy, VIM_DIM  # noqa: E402

FEATS_DIR = Path(__file__).resolve().parent.parent / "results" / "feats"
OUT_CSV = Path(__file__).resolve().parent.parent / "results" / "sanity_samesource_vim.csv"
SEED = 42

# 每模态选一个代表 source（同源切分用），+ 其 cross-source 对端（复刻 C0）
# (modality, source_A_ID, source_B_OOD)
TRIPLETS = [
    ("CXR",        "NIH_CXR14",   "VinDr_CXR"),
    ("BrainMRI",   "BraTS_normal", "BrainTumor_normal"),
    ("Dermoscopy", "HAM_NV",      "ISIC2020_benign"),
]


def _load(ds):
    f = np.load(FEATS_DIR / f"{ds}.npy")
    lp = FEATS_DIR / f"{ds}_logits.npy"
    l = np.load(lp) if lp.exists() else None
    return f, l


def _vim_auroc(feats_fit, logits_fit, feats_id_test, logits_id_test,
               feats_ood, logits_ood):
    """fit 在 feats_fit 上；test = concat(id_test, ood)；返回 (vim_auroc, resid_auroc)。"""
    feats_test = np.concatenate([feats_id_test, feats_ood], axis=0)
    logits_test = None
    if logits_fit is not None and logits_id_test is not None and logits_ood is not None:
        logits_test = np.concatenate([logits_id_test, logits_ood], axis=0)
    labels = np.array([0] * len(feats_id_test) + [1] * len(feats_ood), dtype=np.int32)

    vim_s = method_vim(feats_fit, feats_test, logits_id=logits_fit,
                       logits_test=logits_test, dim=VIM_DIM)
    res_s = method_residual(feats_fit, feats_test, logits_id=logits_fit,
                            logits_test=logits_test, dim=VIM_DIM)
    return auroc_numpy(labels, vim_s), auroc_numpy(labels, res_s)


def main():
    rng = np.random.RandomState(SEED)
    rows = []
    hdr = ("modality,source_A,source_B,control,vim_auroc,resid_auroc,"
           "n_fit,n_id_test,n_ood,note")
    print(hdr)

    for modality, dsA, dsB in TRIPLETS:
        fA, lA = _load(dsA)
        fB, lB = _load(dsB)
        # 打乱 A（同源切分用确定性 seed）
        idxA = rng.permutation(len(fA))
        fA, lA = fA[idxA], (lA[idxA] if lA is not None else None)

        nA = len(fA)

        # ---- C0 cross-source（复刻 l3 in-sample ID 设定）----
        v, r = _vim_auroc(fA, lA, fA, lA, fB, lB)
        rows.append((modality, dsA, dsB, "C0_cross_source_insample",
                     v, r, nA, nA, len(fB),
                     "复刻 l3：fit+id=A 全量(in-sample), ood=B 全量"))

        # ---- C1 same-source in-sample（关键证伪）----
        half = nA // 2
        A1, A2 = fA[:half], fA[half:]
        lA1 = lA[:half] if lA is not None else None
        lA2 = lA[half:] if lA is not None else None
        # fit+id = A1 (in-sample), pseudo-ood = A2 (同源 held-out)
        v, r = _vim_auroc(A1, lA1, A1, lA1, A2, lA2)
        rows.append((modality, dsA, dsA, "C1_same_source_insample",
                     v, r, half, half, nA - half,
                     "fit+id=A前半(in-sample), pseudo-ood=A后半(同源held-out)"))

        # ---- C2 same-source held-out symmetric（干净负对照，应≈0.5）----
        third = nA // 3
        Af, Aid, Aood = fA[:third], fA[third:2 * third], fA[2 * third:3 * third]
        lAf = lA[:third] if lA is not None else None
        lAid = lA[third:2 * third] if lA is not None else None
        lAood = lA[2 * third:3 * third] if lA is not None else None
        # fit=Af; id-test=Aid(held-out); pseudo-ood=Aood(held-out) —— 对称
        v, r = _vim_auroc(Af, lAf, Aid, lAid, Aood, lAood)
        rows.append((modality, dsA, dsA, "C2_same_source_heldout_symmetric",
                     v, r, third, third, third,
                     "fit=A1/3; id-test+pseudo-ood 都 held-out 对称, 应≈0.5"))

        # ---- C3 cross-source HELD-OUT（正确 source-leakage 协议）----
        # fit = A 前半(train); id-test = A 后半(held-out 同源); ood = B 全量(跨源)
        # 扣掉 in-sample 伪迹后，若 ViM 仍高 = 真 source leakage；若 ≈C2 = 无 source 信号
        v, r = _vim_auroc(A1, lA1, A2, lA2, fB, lB)
        rows.append((modality, dsA, dsB, "C3_cross_source_heldout",
                     v, r, half, nA - half, len(fB),
                     "fit=A前半; id-test=A后半(held-out); ood=B(跨源). 正确协议=真 source 信号"))

    with open(OUT_CSV, "w", encoding="utf-8") as f:
        f.write(hdr + "\n")
        for row in rows:
            line = ",".join(str(x) for x in row)
            f.write(line + "\n")
            print(f"  {row[0]:11} {row[3]:34} ViM={row[4]:.4f}  Resid={row[5]:.4f}")

    print(f"\n[OUT] {OUT_CSV}")
    print("\n判读：")
    print("  C1 ≈1.0 → ViM=1.0 是 in-sample 几何伪迹，A-5 承重被混杂（需 reframe/补 held-out 协议）")
    print("  C1 ≈0.5 → 同源分不开，cross-source(C0) 的 1.0 是真 source 信号（承重稳）")
    print("  ΔAUROC = C0 - C1 = 扣 in-sample 伪迹后真 source 信号量")


if __name__ == "__main__":
    main()
