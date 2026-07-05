#!/usr/bin/env python3
"""Investigate DeepHLApan immunogenic score direction vs ELISpot"""
import pandas as pd, numpy as np
from scipy.stats import spearmanr

df = pd.read_csv("/gpfs/work/bio/zichenli24/rerun_v2/01_DeepHLApan/outputs/dataset2_MT/DeepHLApan_dataset2_MT_predicted_result.csv")
df.columns = df.columns.str.strip()
df["Peptide_ID"] = df["Annotation"].apply(lambda a: str(a).split("_")[1] if len(str(a).split("_")) >= 2 else a)

ds2 = pd.read_excel("/gpfs/work/bio/zichenli24/rerun_v2/00_source/Elispot_Dataset2_complete.xlsx")
max_df = df.dropna(subset=["immunogenic score"]).sort_values("immunogenic score", ascending=False).drop_duplicates("Peptide_ID")
max_df = max_df.merge(ds2[["Peptide_ID","Elispot","Vaccine_Peptide"]].astype(str), on="Peptide_ID", how="left")

r, p = spearmanr(max_df["immunogenic score"].astype(float), max_df["Elispot"].astype(float))
print(f"DeepHLApan immunogenic_score vs ELISpot: Spearman r={r:.4f} p={p:.4f}")
print(f"N peptides with scores: {max_df['Elispot'].notna().sum()}")

high = max_df[max_df["Elispot"].astype(float) > max_df["Elispot"].astype(float).median()]
low = max_df[max_df["Elispot"].astype(float) <= max_df["Elispot"].astype(float).median()]
print(f"High ELISpot (>median): mean immunogenic_score = {high['immunogenic score'].astype(float).mean():.4f}")
print(f"Low ELISpot (<=median): mean immunogenic_score = {low['immunogenic score'].astype(float).mean():.4f}")

r2, p2 = spearmanr(max_df["binding score"].astype(float), max_df["Elispot"].astype(float))
print(f"\nBinding score vs ELISpot: Spearman r={r2:.4f} p={p2:.4f}")

print("\nTop 5 by immunogenic score:")
for _, row in max_df.nlargest(5, "immunogenic score").iterrows():
    print(f"  {row['Peptide_ID']:20s} immuno={row['immunogenic score']:.4f} bind={row['binding score']:.4f} ELISpot={row['Elispot']}")

print("\nBottom 5 by immunogenic score:")
for _, row in max_df.nsmallest(5, "immunogenic score").iterrows():
    print(f"  {row['Peptide_ID']:20s} immuno={row['immunogenic score']:.4f} bind={row['binding score']:.4f} ELISpot={row['Elispot']}")
