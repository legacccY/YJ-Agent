# -*- coding: utf-8 -*-
"""
merge_metrics_9tools.py
服务: quantimmu-bench / HLAthena 第9列收尾
1) 读本地 HPC/hlathena_run/hla_bench3/<allele>_{MT,WT}.txt (combined, pep\tMSi)
2) 按 (norm HLA_Allele, Subpeptide) map 回 merged_all_tools_8tools.xlsx -> +MT_HLAthena/WT_HLAthena
   -> scripts/out/merged_all_tools_9tools.xlsx
3) 复刻 export_plot_data 聚合逻辑算 9 工具 DS2 指标 (max/mean/top3mean x >0/>10/>median)
   -> analysis/metrics_ds2_9tools.csv
   并复现 8 工具数字对账 metrics_ds2_8tools.csv (口径对齐铁证)
HLAthena = presentation proxy (预测提呈非免疫原性), ELISpot 上预期近随机, caveat 写进 csv 注释行.
"""
import os, glob, re
import numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score
from scipy.stats import spearmanr

SD = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.join(SD, "..")
BACKBONE = os.path.join(PROJ, "scripts", "out", "merged_all_tools_8tools.xlsx")
HLA_DIR = os.path.join(PROJ, "HPC", "hlathena_run", "hla_bench3")
OUT_XLSX = os.path.join(PROJ, "scripts", "out", "merged_all_tools_9tools.xlsx")
OUT_CSV = os.path.join(SD, "metrics_ds2_9tools.csv")
REF_CSV = os.path.join(SD, "metrics_ds2_8tools.csv")

def norm_allele(a):
    """HLA-A*24:02 -> A2402 ; A2402 -> A2402"""
    if not isinstance(a, str): return None
    return a.replace("HLA-", "").replace("*", "").replace(":", "").strip()

def load_hlathena():
    """return {'MT': {(allele_norm, pep): msi}, 'WT': {...}}"""
    maps = {"MT": {}, "WT": {}}
    files = glob.glob(os.path.join(HLA_DIR, "*_MT.txt")) + glob.glob(os.path.join(HLA_DIR, "*_WT.txt"))
    # exclude chunk intermediates like A0101_MT_9_000.txt (won't match *_MT.txt anyway since they end _000)
    n_rows = 0
    for f in files:
        bn = os.path.basename(f)
        m = re.match(r"^(.+)_(MT|WT)\.txt$", bn)
        if not m: continue
        allele, T = m.group(1), m.group(2)
        an = norm_allele(allele)
        df = pd.read_csv(f, sep="\t")
        # columns: pep, MSi
        pcol = "pep" if "pep" in df.columns else df.columns[0]
        scol = "MSi" if "MSi" in df.columns else df.columns[1]
        for pep, msi in zip(df[pcol], df[scol]):
            try: v = float(msi)
            except: continue
            k = (an, str(pep).strip())
            # keep max if dup
            if k not in maps[T] or v > maps[T][k]:
                maps[T][k] = v
        n_rows += len(df)
    return maps, len(files), n_rows

def main():
    print("=== STEP A: load HLAthena combined txt ===")
    maps, nfiles, nrows = load_hlathena()
    print(f"hlathena_txt_files={nfiles} rows={nrows} MT_keys={len(maps['MT'])} WT_keys={len(maps['WT'])}")
    alleles = sorted(set(k[0] for k in maps['MT']) | set(k[0] for k in maps['WT']))
    print(f"alleles_covered={len(alleles)}: {alleles}")

    print("=== STEP B: merge into backbone ===")
    df = pd.read_excel(BACKBONE)
    an_col = df["HLA_Allele"].map(norm_allele)
    def lk(T, pep_col):
        m = maps[T]
        return [m.get((an, str(p).strip()), np.nan) for an, p in zip(an_col, df[pep_col])]
    df["MT_HLAthena"] = lk("MT", "MT_Subpeptide")
    df["WT_HLAthena"] = lk("WT", "WT_Subpeptide")
    mt_nonnull = df["MT_HLAthena"].notna().sum()
    wt_nonnull = df["WT_HLAthena"].notna().sum()
    print(f"merged shape={df.shape} MT_HLAthena_nonnull={mt_nonnull} WT_HLAthena_nonnull={wt_nonnull}")
    df.to_excel(OUT_XLSX, index=False)
    print(f"saved {OUT_XLSX}")

    print("=== STEP C: metrics (9 tools) ===")
    TOOLS = {
        "DeepImmuno": "MT_DeepImmuno", "PredIG": "MT_PredIG",
        "IMPROVE": "MT_IMPROVE_mean_prediction_rf", "NeoTImmuML": "MT_NeoTImmuML",
        "pTuneos": "MT_pTuneos", "PRIME": "MT_PRIME", "ImmuneApp": "MT_ImmuneApp",
        "deepHLApan": "MT_deepHLApan", "HLAthena": "MT_HLAthena",
    }
    ds2 = df[df["Dataset"] == "DS2"].copy()
    ds2_pep = ds2.drop_duplicates("Peptide_ID")[["Peptide_ID", "Elispot"]].set_index("Peptide_ID")
    elispot = ds2_pep["Elispot"]

    def agg_pep(col):
        valid = ds2[ds2[col].notna()]
        out = {}
        for pid, grp in valid.groupby("Peptide_ID")[col]:
            arr = grp.values.astype(float); k = min(3, len(arr))
            out[pid] = {"max": float(arr.max()), "mean": float(arr.mean()),
                        "top3mean": float(np.sort(arr)[-k:].mean())}
        return out

    rows = []
    for tname, col in TOOLS.items():
        ps = agg_pep(col)
        if not ps:
            print(f"WARN {tname}: no scores"); continue
        pids = list(ps.keys())
        el = elispot.loc[pids].values.astype(float)
        med = float(np.median(el))
        for agg in ["max", "mean", "top3mean"]:
            sc = np.array([ps[p][agg] for p in pids])
            rho, pval = spearmanr(sc, el)
            for thr_name, thr in [(">0", 0.0), (">10", 10.0), (">median", med)]:
                labs = (el > thr).astype(int)
                npos, nneg = int(labs.sum()), int((1 - labs).sum())
                auc = roc_auc_score(labs, sc) if npos and nneg else np.nan
                ap = average_precision_score(labs, sc) if npos and nneg else np.nan
                rows.append({"Tool": tname, "Aggregation": agg, "Threshold": thr_name,
                    "n_pep": len(pids), "n_valid_pep_for_spearman": len(pids),
                    "n_pos": npos, "n_neg": nneg,
                    "AUC_ROC": round(auc, 4) if auc==auc else np.nan,
                    "AUPRC": round(ap, 4) if ap==ap else np.nan,
                    "Spearman_rho": round(rho, 4), "Spearman_pval": round(pval, 4)})
    out = pd.DataFrame(rows)
    with open(OUT_CSV, "w", encoding="utf-8") as fo:
        fo.write("# HLAthena = presentation proxy (predicts MHC-I presentation, NOT immunogenicity); near-random expected on ELISpot; NOT apples-to-apples with immunogenicity tools\n")
        out.to_csv(fo, index=False)
    print(f"saved {OUT_CSV} shape={out.shape}")

    print("=== STEP D: reproduce 8-tool numbers vs metrics_ds2_8tools.csv ===")
    if os.path.exists(REF_CSV):
        ref = pd.read_csv(REF_CSV)
        merged = out.merge(ref, on=["Tool", "Aggregation", "Threshold"], suffixes=("_new", "_ref"))
        merged["dAUC"] = (merged["AUC_ROC_new"] - merged["AUC_ROC_ref"]).abs()
        merged["drho"] = (merged["Spearman_rho_new"] - merged["Spearman_rho_ref"]).abs()
        print(f"max |dAUC|={merged['dAUC'].max():.4f}  max |drho|={merged['drho'].max():.4f}  (should be ~0)")
        bad = merged[(merged["dAUC"] > 0.01) | (merged["drho"] > 0.01)]
        if len(bad): print("MISMATCH rows:\n", bad[["Tool","Aggregation","Threshold","AUC_ROC_new","AUC_ROC_ref","dAUC"]].to_string())
        else: print("ALL 8-tool numbers MATCH (delta<0.01) -> 口径对齐")
    print("=== HLAthena rows ===")
    print(out[out.Tool=="HLAthena"].to_string())

if __name__ == "__main__":
    main()
