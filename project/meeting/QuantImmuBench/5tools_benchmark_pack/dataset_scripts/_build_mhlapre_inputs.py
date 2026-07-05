#!/usr/bin/env python3
"""
Build MHLAPre input CSVs from the 130-peptide Dataset2 + reference Ex Vivo.
Generates:
  - dataset2_MT.csv, dataset2_WT.csv  (training)
  - dataset1_MT_predict.csv, dataset1_WT_predict.csv (prediction)
  - dataset2_MT_predict.csv, dataset2_WT_predict.csv (prediction)
"""

import pandas as pd
import numpy as np
import os, sys, re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_ROOT = os.path.dirname(SCRIPT_DIR)
REF_PATH = os.path.join(PROJ_ROOT, "data",
    "副本A neoantigen vaccine generates antitumour immunity in renal cell carcinoma_MOESM4_ESM.xlsx")
SRC = os.path.join(SCRIPT_DIR, "00_source")
OUT = os.path.join(SCRIPT_DIR, "05_MHLAPre", "inputs")
os.makedirs(OUT, exist_ok=True)

STD_AA = set('ACDEFGHIKLMNPQRSTVWY')

def is_valid(pep):
    return all(aa in STD_AA for aa in str(pep))

def compact_to_deephlapan(h):
    h = str(h).strip()
    if not h or h == 'nan':
        return None
    m = re.match(r'^([ABC])(\d{2})(\d{2})$', h)
    if m:
        return f"HLA-{m.group(1)}{m.group(2)}:{m.group(3)}"
    return h

# ══════════════════════════════════════════════════════════
# Dataset2 (In Vitro) — 130 peptides
# ══════════════════════════════════════════════════════════
print("Loading Dataset2...")
ref_invitro = pd.read_excel(REF_PATH, sheet_name="In Vitro")
hla_cols = ['HLA-1','HLA-2','HLA-3','HLA-4','HLA-5','HLA-6']

# Build clean ds2
cols_order = [
    'Patient_ID', 'Peptide_ID', 'Treatment', 'Vaccine_Peptide',
    'Gene_and_Protein_Change', 'Short_Epitope', 'TPM_PurifiedTumorRNA',
    'Elispot', 'HLA-1', 'HLA-2', 'HLA-3', 'HLA-4', 'HLA-5', 'HLA-6',
    'Pool', 'Hugo_Symbol', 'Chromosome', 'Start_position', 'Variant_Type',
    'Mutation_type',
]
ds2 = ref_invitro[cols_order].copy()

# Get WT sequences from original DS2
ds2_old = pd.read_excel(os.path.join(PROJ_ROOT, "data", "Elispot_Dataset2.xlsx"))
ds2_old.columns = [c.strip() for c in ds2_old.columns]
wt_map = dict(zip(ds2_old['Peptide_ID'], ds2_old['WT Peptide Seq']))
ds2['WT Peptide Seq'] = ds2['Peptide_ID'].map(wt_map)

rows_mt_train, rows_wt_train, rows_mt_pred, rows_wt_pred = [], [], [], []
for _, row in ds2.iterrows():
    mt_pep = str(row['Vaccine_Peptide']).strip()
    wt_pep = str(row['WT Peptide Seq']).strip() if pd.notna(row.get('WT Peptide Seq')) else ''
    pep_len = len(mt_pep)
    pid = row['Patient_ID']
    elispot_val = row['Elispot']
    label = 1 if (pd.notna(elispot_val) and elispot_val > 0) else 0

    # Collect HLAs
    hlas = []
    for c in hla_cols:
        v = row.get(c)
        if pd.notna(v):
            h = compact_to_deephlapan(str(v).strip())
            if h:
                hlas.append(h)

    for ws in [8, 9, 10, 11]:
        if ws > pep_len:
            continue
        for pos in range(pep_len - ws + 1):
            mt_sub = mt_pep[pos:pos+ws]
            wt_sub = wt_pep[pos:pos+ws] if len(wt_pep) >= pos+ws else ''
            if not is_valid(mt_sub):
                continue
            for hla in hlas:
                # Training: includes label
                rows_mt_train.append({'peptide': mt_sub, 'HLA': hla, 'label': label, 'patient': pid})
                # Prediction: no label needed (but include for alignment)
                rows_mt_pred.append({'peptide': mt_sub, 'allele': hla, 'patient': pid})
                if wt_sub and is_valid(wt_sub):
                    rows_wt_train.append({'peptide': wt_sub, 'HLA': hla, 'label': 0, 'patient': pid})
                    rows_wt_pred.append({'peptide': wt_sub, 'allele': hla, 'patient': pid})

# Write Dataset2 training
df_mt_train = pd.DataFrame(rows_mt_train)
df_wt_train = pd.DataFrame(rows_wt_train)
df_mt_train.to_csv(os.path.join(OUT, 'dataset2_MT.csv'), index=False)
df_wt_train.to_csv(os.path.join(OUT, 'dataset2_WT.csv'), index=False)
print(f"  dataset2_MT.csv: {len(df_mt_train)} rows, pos={df_mt_train['label'].sum()}")
print(f"  dataset2_WT.csv: {len(df_wt_train)} rows, pos={df_wt_train['label'].sum()}")

# Write Dataset2 prediction
df_mt_pred = pd.DataFrame(rows_mt_pred).drop_duplicates(subset=['peptide','allele','patient'])
df_wt_pred = pd.DataFrame(rows_wt_pred).drop_duplicates(subset=['peptide','allele','patient'])
df_mt_pred.to_csv(os.path.join(OUT, 'dataset2_MT_predict.csv'), index=False)
df_wt_pred.to_csv(os.path.join(OUT, 'dataset2_WT_predict.csv'), index=False)
print(f"  dataset2_MT_predict.csv: {len(df_mt_pred)} rows")
print(f"  dataset2_WT_predict.csv: {len(df_wt_pred)} rows")

# ══════════════════════════════════════════════════════════
# Dataset1 — 82 9-mer peptides (from original Elispot_Dataset1.xlsx)
# ══════════════════════════════════════════════════════════
print("\nLoading Dataset1...")
DS1_PATH = os.path.join(PROJ_ROOT, "data", "Elispot_Dataset1.xlsx")
df1 = pd.read_excel(DS1_PATH)
hla_cols_d1 = ['HLA Allele-1', 'HLA Allele-2', 'HLA Allele-3', 'HLA Allele-4', 'HLA Allele-5', 'HLA Allele-6']

def full_to_deephlapan(h):
    """HLA-A*24:02 -> HLA-A24:02"""
    return str(h).replace("*", "").replace("HLA-", "HLA-")

rows_d1_mt, rows_d1_wt = [], []
for _, row in df1.iterrows():
    mt_pep = str(row['MT Epitope Seq']).strip()
    wt_pep = str(row.get('WT Peptide Seq', '')).strip() if pd.notna(row.get('WT Peptide Seq')) else ''
    pid = row['Patient ID']
    if not is_valid(mt_pep):
        continue

    hlas = []
    for c in hla_cols_d1:
        v = row.get(c)
        if pd.notna(v):
            h = str(v).strip().replace("*", "")
            if h:
                hlas.append(h)

    for hla in hlas:
        rows_d1_mt.append({'peptide': mt_pep, 'allele': hla, 'patient': pid})
        if wt_pep and is_valid(wt_pep):
            rows_d1_wt.append({'peptide': wt_pep, 'allele': hla, 'patient': pid})

df_d1_mt = pd.DataFrame(rows_d1_mt).drop_duplicates()
df_d1_wt = pd.DataFrame(rows_d1_wt).drop_duplicates()
df_d1_mt.to_csv(os.path.join(OUT, 'dataset1_MT_predict.csv'), index=False)
df_d1_wt.to_csv(os.path.join(OUT, 'dataset1_WT_predict.csv'), index=False)
print(f"  dataset1_MT_predict.csv: {len(df_d1_mt)} rows")
print(f"  dataset1_WT_predict.csv: {len(df_d1_wt)} rows")

print("\nDone! MHLAPre inputs written to:", OUT)
