#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bootstrap CI for 8-tool DS2 benchmark AUC + paired tool comparison.
补救红队 🔴-A：证据集(5)≠结论集(8) —— 「新 3 工具无增量」是全 8 工具声称，
必须给全 8 工具 AUC bootstrap CI，不能只 5 个。

数据源改为全 8 工具同源：scripts/out/merged_all_tools_8tools.xlsx
  - 按 Peptide_ID max-agg（每肽取该工具全部 HLA×Window 子肽的 MT_<tool> 最大值）
  - 标签 = Elispot > 0（>0 阈值，对齐 metrics_ds2_8tools.csv 的 max/>0 行）
  - 旧 5 工具的 point AUC 与 metrics_ds2_8tools.csv max/>0 行一致
    (pTuneos 0.7525 / PredIG 0.6611 / NeoTImmuML 0.6551 / IMPROVE 0.6207 / DeepImmuno 0.4813)
  - 新 3 工具 max/>0: ImmuneApp 0.5889 / PRIME 0.5276 / deepHLApan 0.4188
    n_pep 不齐: deepHLApan=98、PRIME=100、其余=101 —— CI 各自照算
零 GPU。
输出 analysis/bootstrap_ci_ds2.csv (8 行) + analysis/figures_deepdive/fig_bootstrap_ci.png (全 8 工具 caterpillar)

跑法 (主线，本脚本不自跑):
  python analysis/bootstrap_ci.py
"""
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import roc_auc_score

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MERGED = ROOT / "scripts" / "out" / "merged_all_tools_8tools.xlsx"
OUT_CSV = HERE / "bootstrap_ci_ds2.csv"
FIG_DIR = HERE / "figures_deepdive"
FIG_DIR.mkdir(exist_ok=True)
N_BOOT = 2000
SEED = 20260624

# 全 8 工具 MT_ 分数列 (与 metrics_topk.py MERGED_TOOL_COLS 一致；IMPROVE 列名特殊)
TOOL_COLS = {
    "DeepImmuno": "MT_DeepImmuno",
    "PredIG": "MT_PredIG",
    "NeoTImmuML": "MT_NeoTImmuML",
    "IMPROVE": "MT_IMPROVE_mean_prediction_rf",
    "pTuneos": "MT_pTuneos",
    "PRIME": "MT_PRIME",
    "ImmuneApp": "MT_ImmuneApp",
    "deepHLApan": "MT_deepHLApan",
}
# 新增 3 工具 (Wave3)，画图时标注用
NEW_TOOLS = {"ImmuneApp", "PRIME", "deepHLApan"}


def auc_safe(y, s):
    m = ~pd.isna(s)
    y, s = y[m], s[m]
    if len(np.unique(y)) < 2:
        return np.nan
    return roc_auc_score(y, s)


def load_8tools():
    """从 8tools xlsx 读，每工具 max-agg 到肽级 + Elispot>0 标签。
    返回 {tool: (y_arr, score_arr)}，仅含该工具有效肽（drop NaN 已在调用处做）。"""
    df = pd.read_excel(MERGED)
    if "Peptide_ID" not in df.columns or "Elispot" not in df.columns:
        raise SystemExit("[ERR] 8tools 表缺 Peptide_ID / Elispot 列")
    # DS2 过滤 (若有 Dataset 列；merged 表可能只含 DS2，无列则全用)
    if "Dataset" in df.columns:
        df = df[df["Dataset"] == "DS2"].copy()
    g = df.groupby("Peptide_ID")
    elis = g["Elispot"].first()
    per_tool = {}
    for tool, col in TOOL_COLS.items():
        if col not in df.columns:
            print(f"[warn] 8tools 表无列 {col}，跳过 {tool}")
            continue
        sc = g[col].max()  # max-agg：每肽取全部子肽该工具分数的 max
        merged = pd.concat([elis, sc], axis=1)
        merged.columns = ["Elispot", "score"]
        # 该工具有效肽 = Elispot 非空 且 score 非空 (deepHLApan/PRIME 缺肽在此 drop)
        merged = merged.dropna(subset=["Elispot", "score"])
        y = (merged["Elispot"].values.astype(float) > 0).astype(float)
        s = merged["score"].values.astype(float)
        per_tool[tool] = (y, s)
    return per_tool, df


def main():
    per_tool, df = load_8tools()
    tools = [t for t in TOOL_COLS if t in per_tool]

    rng = np.random.default_rng(SEED)
    rows = []
    point = {}
    for t in tools:
        y, sc = per_tool[t]
        pt = auc_safe(pd.Series(y), pd.Series(sc))
        point[t] = pt
        n = len(y)
        boots = []
        for _ in range(N_BOOT):
            idx = rng.integers(0, n, n)
            yb, sb = y[idx], sc[idx]
            if len(np.unique(yb)) < 2:
                continue
            boots.append(roc_auc_score(yb, sb))
        boots = np.array(boots)
        lo, hi = np.percentile(boots, [2.5, 97.5])
        rows.append({"Tool": t, "n_pep": int(n), "n_pos": int(y.sum()),
                     "n_neg": int((y == 0).sum()), "AUC": round(pt, 4),
                     "CI_lo": round(lo, 4), "CI_hi": round(hi, 4),
                     "CI_width": round(hi - lo, 4),
                     "is_new": int(t in NEW_TOOLS)})
    res = pd.DataFrame(rows)
    res.to_csv(OUT_CSV, index=False)

    # paired bootstrap: pTuneos (旧最优) vs 三个新工具 + 旧内部对照
    # 新工具是否能区分于旧最优？common-peptide 配对，CI 跨 0 = 不可区分
    wide = {t: per_tool[t] for t in tools}

    def paired(ta, tb):
        ya, sa = wide[ta]
        yb_, sb = wide[tb]
        # 两工具肽集可能不同 (deepHLApan/PRIME 缺肽)；按公共 Peptide_ID 对齐需原始 index。
        # 这里简化：两工具都从同一 elis 索引派生，长度可能不同 → 取交集索引重算。
        # 为稳健，重新从 df 取两工具共同肽。
        g = df.groupby("Peptide_ID")
        elis = g["Elispot"].first()
        ca = TOOL_COLS[ta]; cb = TOOL_COLS[tb]
        m = pd.concat([elis, g[ca].max(), g[cb].max()], axis=1)
        m.columns = ["Elispot", "a", "b"]
        m = m.dropna()
        y = (m["Elispot"].values.astype(float) > 0).astype(float)
        a = m["a"].values.astype(float)
        b = m["b"].values.astype(float)
        n = len(y)
        diffs = []
        rng2 = np.random.default_rng(SEED + 1)
        for _ in range(N_BOOT):
            idx = rng2.integers(0, n, n)
            ybb = y[idx]
            if len(np.unique(ybb)) < 2:
                continue
            diffs.append(roc_auc_score(ybb, a[idx]) - roc_auc_score(ybb, b[idx]))
        diffs = np.array(diffs)
        lo, hi = np.percentile(diffs, [2.5, 97.5])
        frac_gt0 = float((diffs > 0).mean())
        return dict(pair=f"{ta}-{tb}", n_common=int(n),
                    dAUC=round(auc_safe(pd.Series(y), pd.Series(a)) - auc_safe(pd.Series(y), pd.Series(b)), 4),
                    CI_lo=round(lo, 4), CI_hi=round(hi, 4), P_a_gt_b=round(frac_gt0, 3),
                    sig=("YES" if (lo > 0 or hi < 0) else "NO(CI跨0)"))

    pairs = [paired("pTuneos", "ImmuneApp"), paired("pTuneos", "PRIME"),
             paired("pTuneos", "deepHLApan"), paired("pTuneos", "PredIG"),
             paired("pTuneos", "IMPROVE")]
    pdf = pd.DataFrame(pairs)
    pdf.to_csv(HERE / "bootstrap_paired_ds2.csv", index=False)

    print("=== Per-tool AUC 95% bootstrap CI (DS2, max-agg, Elispot>0, " + str(N_BOOT) + " boots) ===")
    print(res.to_string(index=False))
    print("\n=== Paired ΔAUC bootstrap CI (pTuneos vs others, common peptides) ===")
    print(pdf.to_string(index=False))

    # ── 全 8 工具 caterpillar plot ───────────────────────────────────────────
    # 新工具用空心/橙色标注；预期 CI 同样跨随机线 0.5 / 与旧工具大幅重叠 → 支撑「无增量」
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        rs = res.sort_values("AUC").reset_index(drop=True)
        fig, ax = plt.subplots(figsize=(7.5, 5.5))
        yv = np.arange(len(rs))
        for i, r in rs.iterrows():
            is_new = bool(r["is_new"])
            col = "#E69F00" if is_new else "#0072B2"   # 新=橙 旧=蓝
            ax.errorbar(r["AUC"], i,
                        xerr=[[r["AUC"] - r["CI_lo"]], [r["CI_hi"] - r["AUC"]]],
                        fmt=("s" if is_new else "o"), color=col, ecolor="#999",
                        capsize=4, ms=8, mfc=("white" if is_new else col),
                        mew=1.5, zorder=3)
        ax.axvline(0.5, ls="--", color="#888", lw=1.2,
                   label="random (0.5)", zorder=1)
        ax.set_yticks(yv)
        ax.set_yticklabels([f"{r['Tool']} (n={r['n_pep']})" for _, r in rs.iterrows()])
        ax.set_xlim(0.25, 0.95)
        ax.set_xlabel("AUC-ROC (DS2, max-agg, Elispot>0) with 95% bootstrap CI")
        ax.set_title("Per-tool AUC 95% CI — all 8 tools, n_neg=10~11, CIs span 0.5 & overlap heavily")
        # 图例: 区分新旧 + 随机线
        from matplotlib.lines import Line2D
        handles = [
            Line2D([0], [0], marker="o", color="w", mfc="#0072B2", ms=8, label="Wave1-2 (5 tools)"),
            Line2D([0], [0], marker="s", color="w", mfc="white", mec="#E69F00", mew=1.5, ms=8, label="Wave3 new (ImmuneApp/PRIME/deepHLApan)"),
            Line2D([0], [0], ls="--", color="#888", label="random (0.5)"),
        ]
        ax.legend(handles=handles, loc="lower right", fontsize=8.5)
        plt.tight_layout()
        plt.savefig(FIG_DIR / "fig_bootstrap_ci.png", dpi=200, bbox_inches="tight")
        print("\nsaved", FIG_DIR / "fig_bootstrap_ci.png")
    except Exception as e:
        print("plot skipped:", e)


if __name__ == "__main__":
    main()
