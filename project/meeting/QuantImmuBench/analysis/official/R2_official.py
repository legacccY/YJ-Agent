#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R2_official.py
==============
服务: QuantImmuBench 大纲 §3.2 (图2 洗牌图) —— 30 工具 × 51 pooling 变体全扫。
对应大纲: paper/QuanImmu-Paper-Outline.md §3.2 "聚合方式 (pooling) 影响"。

★ 2026-07-01 Part D Phase 3 重写 (干净表 51 变体命名, 见 04_LOG):
  旧脚本 for pl in POOLINGS (8 个旧名 max/mean/geomean/sum/softmax/top3mean/topk_w/rankdecay)
  在干净表会全 miss (干净表命名 = <Tool>_max / _topk_k{k}_a{α} / _softmax_T{T} / _rankdecay_g{γ},
  共 51 变体)。本脚本改用 tool_pooling_cols(df, tool) 动态遍历该工具全部 pooling 变体, 每变体
  算等权 per-patient Fisher-z ρ̄。
  ⚠️ [B5 selection] R2_best_per_tool.csv 的 best 变体 = in-sample 上界 (同 held-in 数据挑
  ρ̄ 最高 = 乐观选择偏), 仅用于描述 pooling 规律 (「结合/亲和类靠聚合、免疫原类 max 即峰」);
  ★ 全文 headline 一律用零选择 <tool>_max (max_rho 列), 不用 best 当主结果。
  【旧 count-clean 注释已删】: 干净表不带 count_conf 列, 混杂改由 B2 偏相关 (R1/R3 度量层) 控。

  ★★ 2026-07-01 Part D Phase 3b confound 捡回修复 (见 04_LOG):
  旧脚本 best-pooling 用**裸 rho** 选 → 挑到肽长混杂的大 k topk (如 MUNIS topk_k8 裸 0.69,
  控肽长骤降 0.23)。根因: 大 k topk ≈ mean, 会把肽长搭便车效应捡回 (长肽子肽多 → 池化值抬高,
  肽长本身与 ELISpot 弱相关)。故 pooling 规律须看**控肽长偏相关** (per_patient_partial_spearman
  ctrl='peplen', B2), 不看裸 rho。本次改:
    · best_per_tool 同出两选 —— best_raw (裸 rho 选) + best_lenctrl (控肽长偏相关选), 各带 rho。
    · sweep 长表加 rho_lenctrl 列 (每变体控肽长偏相关)。
    · §3.2 pooling 规律结论一律以**控肽长版 (best_lenctrl / rho_lenctrl)** 为准。

做什么:
  30 工具 × 该工具全 pooling 变体各算 DS2 per-patient Fisher-z 等权 ρ̄ (裸) + 控肽长偏相关。
  每工具找 in-sample 最优变体 (裸选 + 控肽长选两版), 比零选择 max vs best 的提升。验大纲关键发现:
  结合/亲和类 (netMHCpan_BA/EL, MHCflurry) 靠 topk 聚合提升 (netMHCpan_BA_topk_k20_a0=netAffneg
  应在变体里胜出); 免疫原类 max 即峰 (best≈max)。★ 判定以控肽长版为准 (裸版会被肽长混杂捡回)。
  如实输出实测, headline 成立与否=拍板点, 不凑数。

输入 (只读干净表):
  data/frozen/pooled_clean_9mer.csv
输出 (analysis/official/):
  R2_pooling_sweep_official.csv  —— 长表: Tool, pooling_variant, family, pending_DTU,
                                    fisherz_rho(裸), rho_lenctrl(控肽长偏相关), ci_lo, ci_hi,
                                    n_pat, n_dropped (30×51 行)
  R2_best_per_tool.csv           —— 每工具一行: Tool, pending_DTU,
                                    max_rho(零选择基线,裸), max_rho_lenctrl(零选择基线,控肽长),
                                    best_raw(裸选变体), best_raw_rho,
                                    best_lenctrl(控肽长选变体), best_lenctrl_rho,
                                    gain_raw_over_max, gain_lenctrl_over_maxlen, selection

复用旧骨架:
  · per-patient Spearman + Fisher-z 等权 → _official_common.per_patient_spearman
  · 控肽长偏相关 (B2) → per_patient_partial_spearman(ctrl='peplen')
  · 51 变体动态列名 → tool_pooling_cols(df, tool)

跑法 (主线跑, 我不跑):
  python analysis/official/R2_official.py
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _official_common import (                              # noqa: E402
    load_frozen, present_patients, per_patient_spearman,
    per_patient_partial_spearman, tool_pooling_cols,
    TOOLS_30, DTU_TOOLS, MIN_PEP, FROZEN_POOLED, ensure_out_dir, r6,
)


def pooling_family(variant):
    """pooling 变体后缀 -> 家族名 (max / topk / softmax / rankdecay)。未知返回 'other'。"""
    if variant == "max":
        return "max"
    for fam in ("topk", "softmax", "rankdecay"):
        if variant.startswith(fam + "_"):
            return fam
    return "other"


def main():
    ap = argparse.ArgumentParser(
        description="R2 官方: 30 工具 × 51 pooling 变体 sweep per-patient Fisher-z (§3.2)")
    ap.add_argument("--input", default=str(FROZEN_POOLED), help="干净肽级表路径")
    ap.add_argument("--min_pep", type=int, default=MIN_PEP)
    ap.add_argument("--ctrl", default="peplen",
                    help="控制变量列 (B2 偏相关, 默认 peplen; pooling 规律以控肽长版为准)")
    args = ap.parse_args()

    df = load_frozen(args.input)
    pats = present_patients(df)
    print(f"[info] 干净表: {df.shape}; DS2 患者({len(pats)})={pats}; "
          f"sweep {len(TOOLS_30)}工具 × 全 pooling 变体 (tool_pooling_cols 动态)")

    sweep_rows = []
    best_rows = []
    for tool in TOOLS_30:
        is_dtu = tool in DTU_TOOLS
        cols = tool_pooling_cols(df, tool)
        if not cols:
            print(f"[warn] {tool}: 无 pooling 变体列, 跳过")
            continue
        per_variant = {}       # variant 后缀 -> 裸 rho
        per_variant_len = {}   # variant 后缀 -> 控肽长偏相关 rho (B2)
        for col in cols:
            variant = col[len(tool) + 1:]           # 去 "<tool>_" 前缀 -> 变体后缀
            fam = pooling_family(variant)
            if df[col].notna().sum() == 0:
                per_variant[variant] = np.nan
                per_variant_len[variant] = np.nan
                sweep_rows.append(dict(Tool=tool, pooling_variant=variant, family=fam,
                                       pending_DTU=is_dtu, fisherz_rho=np.nan,
                                       rho_lenctrl=np.nan,
                                       ci_lo=np.nan, ci_hi=np.nan, n_pat=0, n_dropped=0))
                continue
            rho, cl, ch, nu, nd = per_patient_spearman(
                df, col, patients=pats, min_pep=args.min_pep)
            # 控肽长偏相关 (B2): 大 k topk≈mean 的肽长混杂在此现形
            rho_len, _cl, _ch, _nu, _nd = per_patient_partial_spearman(
                df, col, ctrl=args.ctrl, patients=pats, min_pep=args.min_pep)
            per_variant[variant] = rho
            per_variant_len[variant] = rho_len
            sweep_rows.append(dict(Tool=tool, pooling_variant=variant, family=fam,
                                   pending_DTU=is_dtu, fisherz_rho=r6(rho, 4),
                                   rho_lenctrl=r6(rho_len, 4),
                                   ci_lo=r6(cl, 4), ci_hi=r6(ch, 4),
                                   n_pat=int(nu), n_dropped=int(nd)))

        max_rho = per_variant.get("max", np.nan)          # 零选择基线 (裸)
        max_rho_len = per_variant_len.get("max", np.nan)  # 零选择基线 (控肽长)
        valid_raw = {k: v for k, v in per_variant.items()
                     if v is not None and not np.isnan(v)}
        valid_len = {k: v for k, v in per_variant_len.items()
                     if v is not None and not np.isnan(v)}
        if not valid_raw:
            print(f"[warn] {tool}: 全 pooling 无有效 rho, 跳过 best")
            continue
        # 裸选 in-sample 上界 (乐观选择偏 + 会捡回肽长混杂, 仅供对照)
        best_raw_pl = max(valid_raw, key=valid_raw.get)
        best_raw_rho = valid_raw[best_raw_pl]
        # 控肽长偏相关选 (★ §3.2 规律以此为准; 隔离大 k topk≈mean 的肽长搭便车)
        if valid_len:
            best_len_pl = max(valid_len, key=valid_len.get)
            best_len_rho = valid_len[best_len_pl]
        else:
            best_len_pl, best_len_rho = None, np.nan
        gain_raw = (best_raw_rho - max_rho
                    if max_rho is not None and not np.isnan(max_rho) else np.nan)
        gain_len = (best_len_rho - max_rho_len
                    if (best_len_pl is not None and max_rho_len is not None
                        and not np.isnan(max_rho_len) and not np.isnan(best_len_rho))
                    else np.nan)
        best_rows.append(dict(
            Tool=tool, pending_DTU=is_dtu,
            max_rho=r6(max_rho, 4), max_rho_lenctrl=r6(max_rho_len, 4),
            best_raw=best_raw_pl, best_raw_rho=r6(best_raw_rho, 4),
            best_lenctrl=best_len_pl, best_lenctrl_rho=r6(best_len_rho, 4),
            gain_raw_over_max=r6(gain_raw, 4),
            gain_lenctrl_over_maxlen=r6(gain_len, 4),
            selection="in-sample上界(raw+lenctrl两版; 规律以lenctrl为准)"))
        mr = f"{max_rho:+.4f}" if max_rho is not None and not np.isnan(max_rho) else "  NaN "
        bl = (f"{best_len_rho:+.4f}@{best_len_pl}" if best_len_pl is not None else "  NaN ")
        print(f"  {tool:16s} max_raw={mr} best_raw={best_raw_rho:+.4f}@{best_raw_pl:<14s} "
              f"best_lenctrl={bl}")

    sweep_df = pd.DataFrame(sweep_rows)
    # 规律以控肽长版为准 → 按控肽长 gain 排序 (NaN 置末)
    best_df = pd.DataFrame(best_rows).sort_values(
        "gain_lenctrl_over_maxlen", ascending=False, na_position="last")

    out_dir = ensure_out_dir()
    sweep_path = out_dir / "R2_pooling_sweep_official.csv"
    with open(sweep_path, "w", encoding="utf-8") as f:
        f.write("# R2_pooling_sweep_official.csv\n")
        f.write("# QuantImmuBench §3.2 图2: 30 工具 × 全 pooling 变体 per-patient Fisher-z 等权全扫 (长表)\n")
        f.write(f"# 输入={Path(args.input).name}; DS2 9 患者; pooling_variant=<max/topk_k{{k}}_a{{α}}/softmax_T{{T}}/rankdecay_g{{γ}}>\n")
        f.write("# family=pooling 家族(max/topk/softmax/rankdecay); pending_DTU=True 为 DTU 受限工具(结果照常算)\n")
        f.write("# fisherz_rho=裸 Fisher-z 等权聚合(B1); rho_lenctrl=控肽长偏相关(B2, ctrl=peplen; 大 k topk≈mean 的肽长混杂在此现形, 规律以此列为准)\n")
        f.write("# ci_lo/ci_hi=裸固定效应 95%CI(快速参考, headline CI 见 R1 bootstrap)\n")
        sweep_df.to_csv(f, index=False)
    print(f"\n[saved] {sweep_path}  shape={sweep_df.shape}")

    best_path = out_dir / "R2_best_per_tool.csv"
    with open(best_path, "w", encoding="utf-8") as f:
        f.write("# R2_best_per_tool.csv\n")
        f.write("# QuantImmuBench §3.2: 每工具 零选择 max vs in-sample 最优 pooling 变体 (裸选 + 控肽长选两版)\n")
        f.write("# ★ B5: max_rho/max_rho_lenctrl=零选择基线(headline 用, 裸/控肽长两口径)\n")
        f.write("# best_raw/best_raw_rho=裸 rho 选的 in-sample 上界(会捡回肽长混杂, 仅对照); best_lenctrl/best_lenctrl_rho=控肽长偏相关选(★ §3.2 规律以此为准)\n")
        f.write("# gain_raw_over_max=裸选 vs 裸 max; gain_lenctrl_over_maxlen=控肽长选 vs 控肽长 max(排序键)\n")
        f.write("# 大 k topk≈mean → 裸 gain 大但多是肽长搭便车; 控肽长后 gain 才反映真 pooling 增益(验大纲: 亲和/结合类靠 topk, 免疫原类 max 即峰)\n")
        best_df.to_csv(f, index=False)
    print(f"[saved] {best_path}  shape={best_df.shape}")
    print("[DONE] R2")


if __name__ == "__main__":
    main()
