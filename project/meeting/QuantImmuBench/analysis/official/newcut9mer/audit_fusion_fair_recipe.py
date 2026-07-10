#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性审计(放 _scratch, 不进读档链): 融合用大纲预指定的聚合亲和维 vs 最强单工具, 公平配对。
问题: R3b 融合成员一律用 max, 可能削弱融合(大纲配方亲和维用 netAffneg topk-20)。这里公平重算。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis" / "official"))
from _official_common import (
    load_frozen, present_patients, per_patient_spearman,
    per_patient_partial_spearman, apply_fusion, paired_patient_test,
)

ROOT = Path(__file__).resolve().parents[1]
df = load_frozen(ROOT / "data" / "frozen" / "pooled_clean_rerun_9mer.csv")
pats = present_patients(df)
MP = 8


def rho(colname_or_score, ctrl=None):
    if ctrl:
        return per_patient_partial_spearman(df, colname_or_score, ctrl=ctrl, patients=pats, min_pep=MP)[0]
    return per_patient_spearman(df, colname_or_score, patients=pats, min_pep=MP)[0]


AFF_AGG = "netMHCpan_BA_topk_k20_a0"    # 大纲聚合亲和(netAffneg)
AFF_MAX = "netMHCpan_BA_max"
AFF_BEST = "netMHCpan_BA_rankdecay_g5"  # 单工具最佳 pooling

# 大纲预指定融合配方: geomean, 聚合亲和 + 免疫原 max
members = [AFF_AGG, "PRIME_max", "deepHLApan_max", "PredIG_max"]
fus = apply_fusion(df, members, method="geomean", patients=pats)

print("=== 单工具基线(裸 / 控长) ===")
for name, col in [("亲和max", AFF_MAX), ("亲和聚合netAffneg", AFF_AGG), ("亲和最佳rankdecay", AFF_BEST)]:
    print(f"  {name:20s} 裸={rho(col):+.4f}  控长={rho(col, 'peplen'):+.4f}")

print("\n=== 大纲配方融合 geomean(聚合亲和+3免疫原) ===")
print(f"  融合 裸={rho(fus):+.4f}  控长={rho(fus, 'peplen'):+.4f}")

print("\n=== 融合 vs 各单工具 病人配对(裸 / 控长) ===")
for name, col in [("vs 亲和max(0.372)", AFF_MAX),
                  ("vs 亲和聚合(netAffneg)", AFF_AGG),
                  ("vs 亲和最佳(rankdecay)", AFF_BEST)]:
    dz_r, p_r, K = paired_patient_test(df, fus, col, patients=pats, min_pep=MP)
    dz_l, p_l, _ = paired_patient_test(df, fus, col, ctrl="peplen", patients=pats, min_pep=MP)
    print(f"  {name:26s} 裸Δz={dz_r:+.4f}(p={p_r:.3f})  控长Δz={dz_l:+.4f}(p={p_l:.3f})  K={K}")
