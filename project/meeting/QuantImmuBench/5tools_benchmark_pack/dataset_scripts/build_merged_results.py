#!/usr/bin/env python3
"""
Build 5 merged-tool-result Excel files (one per tool).
Backbone = patient/peptide/subpeptide/HLA info.
Tool scores merged by (Subpeptide, HLA_Allele) or Peptide_ID.
"""
import pandas as pd
import numpy as np
import os, re

PROJ = r"D:\D_Agent\project\rerun_v2"
OUT = os.path.join(PROJ, "merged_results")
os.makedirs(OUT, exist_ok=True)

SRC_DS2 = os.path.join(PROJ, "00_source", "Elispot_Dataset2_complete.xlsx")

STD_AA = set("ACDEFGHIKLMNPQRSTVWY")
def is_valid(pep):
    return all(aa in STD_AA for aa in str(pep))

def hla_norm(h):
    """Normalize any HLA format to compact: HLA-B*57:01 / HLA-B57:01 / B5701 → B5701"""
    h = str(h).strip()
    h = re.sub(r'^(HLA-)?', '', h)
    h = h.replace('*', '').replace(':', '')
    return h

# ================================================================
# 1. Build backbone from DS2
# ================================================================
print("Building backbone from DS2...")
ds2 = pd.read_excel(SRC_DS2)
ds2.columns = [str(c).strip() for c in ds2.columns]

backbone_rows = []
for _, row in ds2.iterrows():
    pid = row["Patient_ID"]
    pep_id = row["Peptide_ID"]
    treatment = row.get("Treatment", "")
    gene = row.get("Hugo_Symbol", row.get("Gene_Name", ""))
    mutation = row.get("Gene_and_Protein_Change", row.get("Mutation", ""))
    mt_full = str(row["Vaccine_Peptide"]).strip()
    wt_full = str(row.get("WT_Peptide_Seq", row.get("WT Peptide Seq", ""))).strip() if pd.notna(row.get("WT_Peptide_Seq", row.get("WT Peptide Seq", ""))) else ""
    pep_len = len(mt_full)
    tpm = row.get("TPM_PurifiedTumorRNA", np.nan)
    elispot = row.get("Elispot", np.nan)

    hla_cols = ["HLA-1", "HLA-2", "HLA-3", "HLA-4", "HLA-5", "HLA-6"]
    hlas = []
    for c in hla_cols:
        v = row.get(c)
        if pd.notna(v) and str(v).strip() not in ["", "nan"]:
            hlas.append(str(v).strip())

    for ws in [8, 9, 10, 11]:
        if ws > pep_len:
            continue
        for pos in range(pep_len - ws + 1):
            mt_sub = mt_full[pos:pos+ws]
            wt_sub = wt_full[pos:pos+ws] if len(wt_full) >= pos+ws else ""
            if not is_valid(mt_sub):
                continue
            for hla in hlas:
                backbone_rows.append({
                    "Patient_ID": pid,
                    "Peptide_ID": pep_id,
                    "Treatment": treatment,
                    "Gene_Name": gene,
                    "Mutation": mutation,
                    "Vaccine_Peptide": mt_full,
                    "WT_Peptide_Seq": wt_full if wt_full else "",
                    "Peptide_Length": pep_len,
                    "TPM_PurifiedTumorRNA": tpm,
                    "Elispot": elispot,
                    "Window_Size": ws,
                    "Position": pos,
                    "MT_Subpeptide": mt_sub,
                    "WT_Subpeptide": wt_sub,
                    "HLA_Allele": hla,
                })

backbone = pd.DataFrame(backbone_rows)
# Add HLA without star for tools that use that format
backbone["HLA_Allele_norm"] = backbone["HLA_Allele"].apply(hla_norm)
print(f"Backbone: {len(backbone)} rows, {backbone['Peptide_ID'].nunique()} peptides")
print(f"  HLA normalized: {backbone['HLA_Allele'].iloc[0]} → {backbone['HLA_Allele_norm'].iloc[0]}")

# ================================================================
# 2. PRIME
# ================================================================
print("\n=== PRIME ===")
PRIME_MT = os.path.join(PROJ, "02_PRIME", "outputs", "dataset2_MT_prime.txt")
PRIME_WT = os.path.join(PROJ, "02_PRIME", "outputs", "dataset2_WT_prime.txt")

prime = backbone.copy()

if os.path.exists(PRIME_MT):
    mt = pd.read_csv(PRIME_MT, sep="\t", skiprows=11, engine="python")
    mt.columns = [str(c).strip() for c in mt.columns]
    print(f"  MT: {len(mt)} rows, {len(mt.columns)} cols")
    # Map best-allele columns
    for col in ["%Rank_bestAllele", "Score_bestAllele", "%RankBinding_bestAllele", "BestAllele"]:
        if col in mt.columns:
            m = dict(zip(mt["Peptide"].str.strip(), mt[col]))
            out_col = f"MT_PRIME_{col.replace('%','').replace('_bestAllele','_best')}"
            prime[out_col] = prime["MT_Subpeptide"].map(m)
    n_mt = prime["MT_PRIME_Score_best"].notna().sum()
    print(f"  MT best-allele matched: {n_mt}")

if os.path.exists(PRIME_WT):
    wt = pd.read_csv(PRIME_WT, sep="\t", skiprows=11, engine="python")
    wt.columns = [str(c).strip() for c in wt.columns]
    print(f"  WT: {len(wt)} rows")
    for col in ["%Rank_bestAllele", "Score_bestAllele", "%RankBinding_bestAllele", "BestAllele"]:
        if col in wt.columns:
            m = dict(zip(wt["Peptide"].str.strip(), wt[col]))
            out_col = f"WT_PRIME_{col.replace('%','').replace('_bestAllele','_best')}"
            prime[out_col] = prime["WT_Subpeptide"].map(m)
    n_wt = prime[prime["WT_Subpeptide"].apply(lambda x: str(x) != "" and is_valid(str(x)))]["WT_PRIME_Score_best"].notna().sum()
    print(f"  WT best-allele matched: {n_wt}")

# ================================================================
# 3. DeepHLApan  (HLA format: HLA-B57:01, no star)
# ================================================================
print("\n=== DeepHLApan ===")
DHL_MT = os.path.join(PROJ, "01_DeepHLApan", "outputs", "dataset2_MT",
                      "DeepHLApan_dataset2_MT_predicted_result.csv")
DHL_WT = os.path.join(PROJ, "01_DeepHLApan", "outputs", "dataset2_WT",
                      "DeepHLApan_dataset2_WT_predicted_result.csv")

dhl = backbone.copy()

if os.path.exists(DHL_MT):
    mt = pd.read_csv(DHL_MT)
    mt.columns = [c.strip() for c in mt.columns]
    mt["_pep"] = mt["Peptide"].str.strip()
    mt["_hla_norm"] = mt["HLA"].apply(hla_norm)
    # Dedup: keep max per (subpeptide, HLA)
    mt_dedup = mt.groupby(["_pep", "_hla_norm"])[["binding score", "immunogenic score"]].max().reset_index()
    # Merge: match by (MT_Subpeptide, HLA_Allele_norm)
    dhl = dhl.merge(mt_dedup.rename(
        columns={"_pep": "MT_Subpeptide", "_hla_norm": "HLA_Allele_norm",
                 "binding score": "MT_DHL_binding_score",
                 "immunogenic score": "MT_DHL_immunogenic_score"}),
        on=["MT_Subpeptide", "HLA_Allele_norm"], how="left")
    print(f"  MT merged: {dhl['MT_DHL_immunogenic_score'].notna().sum()}")
if os.path.exists(DHL_WT):
    wt = pd.read_csv(DHL_WT)
    wt.columns = [c.strip() for c in wt.columns]
    wt["_pep"] = wt["Peptide"].str.strip()
    wt["_hla_norm"] = wt["HLA"].apply(hla_norm)
    wt_dedup = wt.groupby(["_pep", "_hla_norm"])[["binding score", "immunogenic score"]].max().reset_index()
    dhl = dhl.merge(wt_dedup.rename(
        columns={"_pep": "WT_Subpeptide", "_hla_norm": "HLA_Allele_norm",
                 "binding score": "WT_DHL_binding_score",
                 "immunogenic score": "WT_DHL_immunogenic_score"}),
        on=["WT_Subpeptide", "HLA_Allele_norm"], how="left")
    print(f"  WT merged: {dhl['WT_DHL_immunogenic_score'].notna().sum()}")
    print(f"  Final rows: {len(dhl)}")

# ================================================================
# 4. ImmuneApp  (HLA format: HLA-A*02:01, matches backbone directly)
# ================================================================
print("\n=== ImmuneApp ===")
IMM = os.path.join(PROJ, "03_ImmuneApp", "outputs", "all_results",
                   "ImmuneApp_Immunogenicity_predictions.tsv")

imm = backbone.copy()

if os.path.exists(IMM):
    mt = pd.read_csv(IMM, sep="\t")
    mt.columns = [c.strip() for c in mt.columns]
    mt["_pep"] = mt["Peptide"].str.strip()
    mt["_hla_norm"] = mt["Allele"].apply(hla_norm)
    print(f"  MT: {len(mt)} rows, cols={list(mt.columns)}")
    # Dedup: take max Immunogenicity_score per (peptide, HLA)
    mt_agg = mt.groupby(["_pep", "_hla_norm"])["Immunogenicity_score"].max().reset_index()
    imm = imm.merge(mt_agg.rename(columns={"_pep": "MT_Subpeptide", "_hla_norm": "HLA_Allele_norm",
                                            "Immunogenicity_score": "MT_ImmuneApp_Score"}),
                     on=["MT_Subpeptide", "HLA_Allele_norm"], how="left")
    # WT not available for DS2
    imm["WT_ImmuneApp_Score"] = np.nan
    print(f"  MT merged: {imm['MT_ImmuneApp_Score'].notna().sum()}")

# ================================================================
# 5. HLAthena  (per Peptide_ID, no per-allele)
# ================================================================
print("\n=== HLAthena ===")
ATH = os.path.join(PROJ, "04_HLAthena", "outputs", "HLAthena_presentation_scores.csv")

ath = backbone.copy()
if os.path.exists(ATH):
    at = pd.read_csv(ATH)
    print(f"  Scores: {len(at)} rows")
    score_map = dict(zip(at["Peptide_ID"].astype(str), at["presentation_score"]))
    ath["HLAthena_presentation_score"] = ath["Peptide_ID"].astype(str).map(score_map)
    print(f"  Matched: {ath['HLAthena_presentation_score'].notna().sum()}")
else:
    print("  WARNING: not found")

# ================================================================
# 6. MHLAPre  (HLA format: HLA-B57:01, no star)
# ================================================================
print("\n=== MHLAPre ===")
MHL_MT = os.path.join(PROJ, "05_MHLAPre", "outputs", "dataset2_MT_predicted.csv")
MHL_WT = os.path.join(PROJ, "05_MHLAPre", "outputs", "dataset2_WT_predicted.csv")

mhl = backbone.copy()

if os.path.exists(MHL_MT):
    mt = pd.read_csv(MHL_MT)
    mt.columns = [c.strip() for c in mt.columns]
    mt["_pep"] = mt.iloc[:, 0].str.strip()
    mt["_hla_norm"] = mt.iloc[:, 1].apply(hla_norm)
    mt_dedup = mt.groupby(["_pep", "_hla_norm"])["MHLAPre_score"].max().reset_index()
    mhl = mhl.merge(mt_dedup.rename(
        columns={"_pep": "MT_Subpeptide", "_hla_norm": "HLA_Allele_norm",
                 "MHLAPre_score": "MT_MHLAPre_Score"}),
        on=["MT_Subpeptide", "HLA_Allele_norm"], how="left")
    print(f"  MT merged: {mhl['MT_MHLAPre_Score'].notna().sum()}")

if os.path.exists(MHL_WT):
    wt = pd.read_csv(MHL_WT)
    wt.columns = [c.strip() for c in wt.columns]
    wt["_pep"] = wt.iloc[:, 0].str.strip()
    wt["_hla_norm"] = wt.iloc[:, 1].apply(hla_norm)
    wt_dedup = wt.groupby(["_pep", "_hla_norm"])["MHLAPre_score"].max().reset_index()
    mhl = mhl.merge(wt_dedup.rename(
        columns={"_pep": "WT_Subpeptide", "_hla_norm": "HLA_Allele_norm",
                 "MHLAPre_score": "WT_MHLAPre_Score"}),
        on=["WT_Subpeptide", "HLA_Allele_norm"], how="left")
    print(f"  WT merged: {mhl['WT_MHLAPre_Score'].notna().sum()}")

# Drop helper column
for df in [prime, dhl, imm, ath, mhl]:
    if "HLA_Allele_norm" in df.columns:
        df.drop(columns=["HLA_Allele_norm"], inplace=True, errors="ignore")

# ================================================================
# 7. Write Excel files
# ================================================================
print("\n" + "="*60)
print("Writing Excel files...")

BB_COLS = list(backbone.drop(columns=["HLA_Allele_norm"]).columns)

def write_excel(df, name, score_cols, col_desc):
    out_cols = BB_COLS + [c for c in score_cols if c in df.columns]
    out = df[out_cols].copy()
    path = os.path.join(OUT, f"{name}_merged_results.xlsx")
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        out.to_excel(w, sheet_name="Sheet1", index=False)
        desc_df = pd.DataFrame(col_desc)
        desc_df.to_excel(w, sheet_name="列说明", index=False)
    n_col = len(out_cols)
    n_row = len(out)
    print(f"  {name}: {n_row} rows × {n_col} cols → {os.path.basename(path)}")

# PRIME
write_excel(prime, "PRIME",
    [c for c in prime.columns if c not in BB_COLS],
    [{"列名": c, "含义": "PRIME immunogenicity/binding score/rank", "方向": "Score越高越免疫原 / Rank越低越强", "范围": "Score∈[0,1] Rank∈[0,100]"}
     for c in prime.columns if c not in BB_COLS] +
    [{"列名": c, "含义": "Backbone column (patient/peptide/HLA info from DS2)", "方向": "—", "范围": "—"} for c in BB_COLS])

# DeepHLApan
write_excel(dhl, "DeepHLApan",
    ["MT_DHL_binding_score", "MT_DHL_immunogenic_score",
     "WT_DHL_binding_score", "WT_DHL_immunogenic_score"],
    [{"列名": "MT_DHL_binding_score", "含义": "DeepHLApan pMHC-I binding score (MT)", "方向": "越高结合越强", "范围": "[0, 1]"},
     {"列名": "MT_DHL_immunogenic_score", "含义": "DeepHLApan immunogenicity score (MT), ⚠️ DS2上分数聚集~0.97无区分力", "方向": "越高越免疫原", "范围": "[0, 1]"},
     {"列名": "WT_DHL_binding_score", "含义": "WT peptide binding score", "方向": "同上", "范围": "[0, 1]"},
     {"列名": "WT_DHL_immunogenic_score", "含义": "WT peptide immunogenicity score", "方向": "同上", "范围": "[0, 1]"}] +
    [{"列名": c, "含义": "Backbone column (patient/peptide/HLA info from DS2)", "方向": "—", "范围": "—"} for c in BB_COLS])

# ImmuneApp
write_excel(imm, "ImmuneApp",
    ["MT_ImmuneApp_Score"],
    [{"列名": "MT_ImmuneApp_Score", "含义": "ImmuneApp-Neo immunogenicity score (MT peptide)", "方向": "越高越免疫原", "范围": "[0, 1] (sigmoid)"}] +
    [{"列名": c, "含义": "Backbone column (patient/peptide/HLA info from DS2)", "方向": "—", "范围": "—"} for c in BB_COLS])

# HLAthena
write_excel(ath, "HLAthena",
    ["HLAthena_presentation_score"],
    [{"列名": "HLAthena_presentation_score", "含义": "HLAthena MSiCE MHC-I presentation probability (per Peptide_ID, not per-allele)", "方向": "越高越可能被提呈", "范围": "[0, 1]", "⚠️": "提呈proxy，非免疫原性工具"}] +
    [{"列名": c, "含义": "Backbone column (patient/peptide/HLA info from DS2)", "方向": "—", "范围": "—"} for c in BB_COLS])

# MHLAPre
write_excel(mhl, "MHLAPre",
    ["MT_MHLAPre_Score", "WT_MHLAPre_Score"],
    [{"列名": "MT_MHLAPre_Score", "含义": "MHLAPre TextCNN immunogenicity score (MT)", "方向": "越高越免疫原", "范围": "[0, 1]", "⚠️": "CV AUC=0.53 接近随机"},
     {"列名": "WT_MHLAPre_Score", "含义": "MHLAPre TextCNN immunogenicity score (WT)", "方向": "越高越免疫原", "范围": "[0, 1]", "⚠️": "CV AUC=0.53 接近随机"}] +
    [{"列名": c, "含义": "Backbone column (patient/peptide/HLA info from DS2)", "方向": "—", "范围": "—"} for c in BB_COLS])

print(f"\nDone! Files in: {OUT}")
