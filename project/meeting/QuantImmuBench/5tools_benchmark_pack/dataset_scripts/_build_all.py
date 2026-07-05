#!/usr/bin/env python3
"""
============================================================
rerun_v2 — Master Build Script
============================================================
Reads the ground-truth reference (MOESM4_ESM) and generates ALL
input files for 5 tools + analysis, using the COMPLETE 130 peptides.

Usage:  python _build_all.py

Output: rerun_v2/
  ├── 00_source/          Fixed Dataset2 (130 peptides) + HLA map
  ├── 01_DeepHLApan/      Input CSVs (MT+WT), run commands
  ├── 02_PRIME/           Input peptide lists (MT+WT), run commands
  ├── 03_ImmuneApp/       Per-HLA peptide files, run commands
  ├── 04_HLAthena/        Per-patient input files, run commands
  ├── 05_MHLAPre/         Input + run commands
  ├── 06_analysis/        Placeholder for re-run outputs
  └── README.md           Master index & re-run order
============================================================
"""

import pandas as pd
import numpy as np
import os, re, sys

# ── Paths ──────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJ_ROOT  = os.path.dirname(SCRIPT_DIR)
REF_PATH   = os.path.join(PROJ_ROOT, "data",
    "副本A neoantigen vaccine generates antitumour immunity in renal cell carcinoma_MOESM4_ESM.xlsx")
DS2_OLD    = os.path.join(PROJ_ROOT, "data", "Elispot_Dataset2.xlsx")

os.chdir(PROJ_ROOT)

# ── Load ground truth ─────────────────────────────────────
print("=" * 60)
print("Loading reference (ground truth)...")
ref_invitro = pd.read_excel(REF_PATH, sheet_name="In Vitro")
ref_exvivo  = pd.read_excel(REF_PATH, sheet_name="Ex Vivo")
print(f"  In Vitro: {ref_invitro.shape[0]} peptides, {ref_invitro.shape[1]} columns")
print(f"  Ex Vivo:  {ref_exvivo.shape[0]} rows, {ref_exvivo.shape[1]} columns")

# ── Utility: compact HLA -> full nomenclature ─────────────
def compact_to_full(h):
    h = str(h).strip()
    if not h or h == 'nan':
        return None
    m = re.match(r'^([ABC])(\d{2})(\d{2})$', h)
    if m:
        return f"HLA-{m.group(1)}*{m.group(2)}:{m.group(3)}"
    return h

def compact_to_deephlapan(h):
    """A0201 -> HLA-A02:01"""
    full = compact_to_full(h)
    if full:
        return full.replace("*", "")
    return h

def compact_to_prime(h):
    """keep as A0201"""
    return h

# ══════════════════════════════════════════════════════════
# 00_source — Clean source data
# ══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("00_source — Building complete Dataset2 (130 peptides)...")

SRC = os.path.join(SCRIPT_DIR, "00_source")
os.makedirs(SRC, exist_ok=True)

# Build from reference In Vitro directly
# This is the canonical 130-peptide dataset
cols_order = [
    'Patient_ID', 'Peptide_ID', 'Treatment', 'Vaccine_Peptide',
    'Gene_and_Protein_Change', 'Short_Epitope', 'TPM_PurifiedTumorRNA',
    'Elispot', 'HLA-1', 'HLA-2', 'HLA-3', 'HLA-4', 'HLA-5', 'HLA-6',
    'Pool', 'Hugo_Symbol', 'Chromosome', 'Start_position', 'Variant_Type',
    'Mutation_type', 'CCF', 'Clonal', 'Rank', 'TPM_BulkRNA',
    'AvePeptide', 'Avebackground',
    'InVitro_PeptideStim_Replicate01', 'InVitro_PeptideStim_Replicate02',
    'InVitro_PeptideStim_Replicate03',
    'InVitro_NoStim_Replicate01', 'InVitro_NoStim_Replicate02',
    'InVitro_NoStim_Replicate03',
    'Ttest_pvalue_InVitroStim',
    'VaccineExpanded_TumorStim_Replicate01',
    'VaccineExpanded_TumorStim_Replicate02',
    'VaccineExpanded_TumorStim_Replicate03',
    'VaccineExpanded_NoStim_Replicate01',
    'VaccineExpanded_NoStim_Replicate02',
    'VaccineExpanded_NoStim_Replicate03',
    'HLA_of_best_short_epitope',
]

# Build clean Dataset2 from reference
ds2 = ref_invitro[cols_order].copy()
ds2 = ds2.sort_values(["Patient_ID", "Pool", "Peptide_ID"]).reset_index(drop=True)

# Add derived columns that downstream tools expect
ds2['Parsed_Gene'] = ds2['Gene_and_Protein_Change'].str.extract(r'^([A-Za-z0-9]+)\|')
ds2['Parsed_Mutation'] = ds2['Gene_and_Protein_Change'].str.extract(r'\|p\.(.+)$')

# WT Peptide Seq — merge from original Dataset2 (101 peptides have known WT)
# For the 29 missing (indels + 1 SNV), WT is structurally different or unknown
ds2_old = pd.read_excel(DS2_OLD)
ds2_old.columns = [c.strip() for c in ds2_old.columns]
wt_map = dict(zip(ds2_old['Peptide_ID'], ds2_old['WT Peptide Seq']))
ds2['WT Peptide Seq'] = ds2['Peptide_ID'].map(wt_map)
n_wt_known = ds2['WT Peptide Seq'].notna().sum()
print(f"  WT sequences known: {n_wt_known}/130 (29 missing are indels — WT not applicable)")

# Add placeholder columns that older scripts expect
ds2['Ref UniProt ID'] = ""
ds2['Peptide Position'] = np.nan

# Write
out_xlsx = os.path.join(SRC, "Elispot_Dataset2_complete.xlsx")
ds2.to_excel(out_xlsx, sheet_name="All_Peptides", index=False)
print(f"  -> {out_xlsx}")
print(f"     {len(ds2)} peptides, {len(ds2.columns)} columns")
print(f"     Variant_Type: {ds2['Variant_Type'].value_counts().to_dict()}")
print(f"     Patients: {sorted(ds2['Patient_ID'].unique())}")

# Also build HLA map
hla_set = set()
for c in ['HLA-1','HLA-2','HLA-3','HLA-4','HLA-5','HLA-6']:
    hla_set.update(ds2[c].dropna().unique())
hla_map = []
for h in sorted(hla_set):
    full = compact_to_full(h)
    note = ""
    if h == "A3001":
        note = "ERROR in old PRIME output: used HLA-A*31:01. Correct is HLA-A*30:01."
    hla_map.append({"compact": h, "full_nomenclature": full, "issue": note})
pd.DataFrame(hla_map).to_excel(os.path.join(SRC, "HLA_nomenclature_map.xlsx"), index=False)
print(f"  -> HLA_nomenclature_map.xlsx ({len(hla_map)} alleles)")

# ══════════════════════════════════════════════════════════
# 01_DeepHLApan — Generate input CSVs
# ══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("01_DeepHLApan — Generating input files...")

DHL = os.path.join(SCRIPT_DIR, "01_DeepHLApan")
os.makedirs(os.path.join(DHL, "inputs"), exist_ok=True)
os.makedirs(os.path.join(DHL, "outputs"), exist_ok=True)
os.makedirs(os.path.join(DHL, "logs"), exist_ok=True)

# Adapted from DeepHLApan/prepare_input.py — uses complete ds2
hla_cols = ['HLA-1','HLA-2','HLA-3','HLA-4','HLA-5','HLA-6']

rows_mt, rows_wt = [], []
for _, row in ds2.iterrows():
    mt_pep = str(row['Vaccine_Peptide']).strip()
    wt_pep = str(row['WT Peptide Seq']).strip() if pd.notna(row.get('WT Peptide Seq')) else ''
    pep_len = len(mt_pep)

    # Collect HLAs for this peptide
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
            annotation = f"{row['Patient_ID']}_{row['Peptide_ID']}_pos{pos+1}_ws{ws}"
            for hla in hlas:
                rows_mt.append({'Annotation': annotation, 'HLA': hla, 'peptide': mt_sub})
                if wt_sub and all(aa in 'ACDEFGHIKLMNPQRSTVWY' for aa in wt_sub):
                    rows_wt.append({'Annotation': annotation, 'HLA': hla, 'peptide': wt_sub})

df_mt = pd.DataFrame(rows_mt)
df_wt = pd.DataFrame(rows_wt)
df_mt.to_csv(os.path.join(DHL, "inputs", "DeepHLApan_dataset2_MT.csv"), index=False)
df_wt.to_csv(os.path.join(DHL, "inputs", "DeepHLApan_dataset2_WT.csv"), index=False)
print(f"  MT: {len(df_mt)} rows -> DeepHLApan_dataset2_MT.csv")
print(f"  WT: {len(df_wt)} rows -> DeepHLApan_dataset2_WT.csv")

# ══════════════════════════════════════════════════════════
# 02_PRIME — Generate input peptide lists
# ══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("02_PRIME — Generating input files...")

PRM = os.path.join(SCRIPT_DIR, "02_PRIME")
os.makedirs(os.path.join(PRM, "inputs"), exist_ok=True)
os.makedirs(os.path.join(PRM, "outputs"), exist_ok=True)
os.makedirs(os.path.join(PRM, "logs"), exist_ok=True)

mt_subs, wt_subs = set(), set()
hla2 = set()

for _, row in ds2.iterrows():
    mt_pep = str(row['Vaccine_Peptide']).strip()
    wt_pep = str(row.get('WT Peptide Seq', '')).strip()
    pep_len = len(mt_pep)

    for ws in range(8, 15):
        if ws > pep_len:
            continue
        for pos in range(pep_len - ws + 1):
            mt_subs.add(mt_pep[pos:pos+ws])
            if len(wt_pep) >= pos+ws:
                wt_subs.add(wt_pep[pos:pos+ws])

    for c in hla_cols:
        v = row.get(c)
        if pd.notna(v):
            h = compact_to_prime(str(v).strip())
            if h:
                hla2.add(h)

with open(os.path.join(PRM, "inputs", "PRIME_database2_MT.txt"), "w", encoding="utf-8") as f:
    for seq in sorted(mt_subs):
        f.write(seq + "\n")

with open(os.path.join(PRM, "inputs", "PRIME_database2_WT.txt"), "w", encoding="utf-8") as f:
    for seq in sorted(wt_subs):
        f.write(seq + "\n")

print(f"  MT: {len(mt_subs)} unique subpeptides -> PRIME_database2_MT.txt")
print(f"  WT: {len(wt_subs)} unique subpeptides -> PRIME_database2_WT.txt")
print(f"  HLA alleles: {len(hla2)}")

with open(os.path.join(PRM, "inputs", "HLA_alleles.txt"), "w") as f:
    for h in sorted(hla2):
        f.write(h + "\n")
print(f"  -> HLA_alleles.txt")

# ══════════════════════════════════════════════════════════
# 03_ImmuneApp — Generate per-HLA peptide files
# ══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("03_ImmuneApp — Generating input files...")

IMM = os.path.join(SCRIPT_DIR, "03_ImmuneApp")
os.makedirs(os.path.join(IMM, "inputs"), exist_ok=True)
os.makedirs(os.path.join(IMM, "outputs"), exist_ok=True)
os.makedirs(os.path.join(IMM, "logs"), exist_ok=True)

# ImmuneApp reads DeepHLApan-format CSV input
dhl_mt = df_mt.copy()
dhl_wt = df_wt.copy()

for label, dhl_df in [("dataset2_MT", dhl_mt), ("dataset2_WT", dhl_wt)]:
    outdir = os.path.join(IMM, "inputs", label)
    os.makedirs(outdir, exist_ok=True)
    if len(dhl_df) == 0:
        print(f"  {label}: 0 rows (no WT data — skipping)")
        continue
    for hla, subdf in dhl_df.groupby("HLA"):
        peptides = subdf["peptide"].dropna().astype(str).drop_duplicates()
        fname = hla.replace(":", "").replace("*", "")
        peptides.to_csv(os.path.join(outdir, f"{fname}.txt"), index=False, header=False)
    print(f"  {label}: {dhl_df['HLA'].nunique()} HLA files -> {outdir}")

# ══════════════════════════════════════════════════════════
# 04_HLAthena — Per-patient input with context
# ══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("04_HLAthena — Generating input files...")

ATH = os.path.join(SCRIPT_DIR, "04_HLAthena")
os.makedirs(os.path.join(ATH, "inputs"), exist_ok=True)
os.makedirs(os.path.join(ATH, "outputs"), exist_ok=True)
os.makedirs(os.path.join(ATH, "logs"), exist_ok=True)

STD_AA = set('ACDEFGHIKLMNPQRSTVWY')

def is_valid_pep(pep):
    return all(aa in STD_AA for aa in str(pep))

for pid in sorted(ds2['Patient_ID'].unique()):
    sub = ds2[ds2['Patient_ID'] == pid]
    alleles = [str(sub.iloc[0][c]) for c in hla_cols
               if pd.notna(sub.iloc[0].get(c)) and str(sub.iloc[0][c]) != 'nan']

    rows = []
    for _, r in sub.iterrows():
        vac_pep = str(r['Vaccine_Peptide']).strip()
        tpm = r.get('TPM_PurifiedTumorRNA', np.nan)
        elispot = r.get('Elispot', np.nan)
        pep_id = r['Peptide_ID']

        for wsize in [8, 9, 10, 11]:
            for offset in range(len(vac_pep) - wsize + 1):
                subpep = vac_pep[offset:offset + wsize]
                if not is_valid_pep(subpep):
                    continue
                rows.append({
                    'pep': subpep,
                    'TPM': tpm,
                    'peptide_id': pep_id,
                    'patient_id': pid,
                    'elispot': elispot,
                    'window_size': wsize,
                    'position': offset,
                })

    out_df = pd.DataFrame(rows)
    fname = os.path.join(ATH, "inputs", f"d2_patient{pid}.txt")
    out_df.to_csv(fname, sep='\t', index=False)
    allele_str = ','.join(alleles)
    print(f"  Patient {pid}: {len(out_df)} subpeptides | alleles: {allele_str}")

# ══════════════════════════════════════════════════════════
# 05_MHLAPre — Training/prediction inputs
# ══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("05_MHLAPre — Placeholder (uses DeepHLApan + PRIME outputs)...")

MHL = os.path.join(SCRIPT_DIR, "05_MHLAPre")
os.makedirs(os.path.join(MHL, "inputs"), exist_ok=True)
os.makedirs(os.path.join(MHL, "outputs"), exist_ok=True)
os.makedirs(os.path.join(MHL, "logs"), exist_ok=True)
os.makedirs(os.path.join(MHL, "models"), exist_ok=True)

with open(os.path.join(MHL, "inputs", "README.txt"), "w", encoding="utf-8") as f:
    f.write("MHLAPre reads DeepHLApan + PRIME outputs for training.\n")
    f.write("Place input files here after DeepHLApan and PRIME complete.\n")

print("  -> inputs/README.txt (run after DeepHLApan + PRIME)")

# ══════════════════════════════════════════════════════════
# 06_analysis — Placeholder
# ══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("06_analysis — Placeholder...")

ANL = os.path.join(SCRIPT_DIR, "06_analysis")
os.makedirs(os.path.join(ANL, "outputs"), exist_ok=True)
os.makedirs(os.path.join(ANL, "logs"), exist_ok=True)

with open(os.path.join(ANL, "README.txt"), "w", encoding="utf-8") as f:
    f.write("Run analysis scripts AFTER all 5 tools complete.\n")
    f.write("Scripts: unified_roc_v4.py, run_spearman_all.py\n")

print("  -> README.txt")

# ══════════════════════════════════════════════════════════
# MASTER README
# ══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("Writing master README...")

readme = """# rerun_v2 — Complete Re-run Based on MOESM4 Ground Truth

**Generated**: 2026-06-30
**Source of truth**: `data/副本A neoantigen vaccine generates antitumour immunity in renal cell carcinoma_MOESM4_ESM.xlsx`
**Key fix**: Dataset2 now has **130 peptides** (was 101, missing 28 indels + 1 SNV)

---

## Directory Structure

```
rerun_v2/
├── README.md                   # This file
├── _build_all.py               # Master build script (reproducible)
│
├── 00_source/                  # Clean canonical source data
│   ├── Elispot_Dataset2_complete.xlsx   # 130 peptides from reference
│   └── HLA_nomenclature_map.xlsx         # Compact <-> Full HLA mapping
│
├── 01_DeepHLApan/              # DeepHLApan binding prediction
│   ├── inputs/                 # ✅ READY — CSV files for MT and WT
│   ├── outputs/                # 🔧 Pending — run on HPC
│   └── logs/                   # 🔧 Pending
│
├── 02_PRIME/                   # PRIME immunogenicity prediction
│   ├── inputs/                 # ✅ READY — peptide lists + HLA list
│   ├── outputs/                # 🔧 Pending — run on HPC
│   └── logs/                   # 🔧 Pending
│
├── 03_ImmuneApp/               # ImmuneApp immunogenicity
│   ├── inputs/                 # ✅ READY — per-HLA peptide files
│   ├── outputs/                # 🔧 Pending — run on HPC
│   └── logs/                   # 🔧 Pending
│
├── 04_HLAthena/                # HLAthena presentation prediction
│   ├── inputs/                 # ✅ READY — per-patient files
│   ├── outputs/                # 🔧 Pending — run on HPC
│   └── logs/                   # 🔧 Pending
│
├── 05_MHLAPre/                 # MHLAPre (deep learning)
│   ├── inputs/                 # 🔧 After DeepHLApan + PRIME complete
│   ├── outputs/                # 🔧 Pending
│   ├── models/                 # 🔧 Pending
│   └── logs/                   # 🔧 Pending
│
└── 06_analysis/                # Cross-tool ROC + Spearman
    ├── outputs/                # 🔧 After all tools complete
    └── logs/                   # 🔧 Pending
```

Legend: ✅ = Ready to use | 🔧 = Needs HPC run

---

## Re-run Order (Strict Dependency)

```
Step 1: 01_DeepHLApan   (no dependencies)
Step 2: 02_PRIME         (no dependencies — can run parallel with DeepHLApan)
Step 3: 03_ImmuneApp     (depends on 01_DeepHLApan inputs — already generated)
Step 4: 04_HLAthena      (no dependencies — needs UniProt fetch for context seqs)
Step 5: 05_MHLAPre       (depends on 01_DeepHLApan + 02_PRIME outputs)
Step 6: 06_analysis      (depends on ALL tool outputs)
```

### Parallel execution:
- DeepHLApan, PRIME, and HLAthena can run **simultaneously**
- ImmuneApp can run after DeepHLApan inputs are built (already done)
- MHLAPre MUST wait for DeepHLApan + PRIME results
- Analysis MUST wait for everything

---

## HPC Run Commands

### 01_DeepHLApan
```bash
cd /gpfs/work/bio/zichenli24/tools/DeepHLApan
# Use the inputs from rerun_v2/01_DeepHLApan/inputs/
# MT prediction
python predict.py \\
  --input rerun_v2/01_DeepHLApan/inputs/DeepHLApan_dataset2_MT.csv \\
  --output rerun_v2/01_DeepHLApan/outputs/dataset2_MT/
# WT prediction
python predict.py \\
  --input rerun_v2/01_DeepHLApan/inputs/DeepHLApan_dataset2_WT.csv \\
  --output rerun_v2/01_DeepHLApan/outputs/dataset2_WT/
```

### 02_PRIME
```bash
cd /gpfs/work/bio/zichenli24/tools/PRIME
# Use inputs from rerun_v2/02_PRIME/inputs/
python PRIME.py \\
  --mt_peptides rerun_v2/02_PRIME/inputs/PRIME_database2_MT.txt \\
  --wt_peptides rerun_v2/02_PRIME/inputs/PRIME_database2_WT.txt \\
  --hla_alleles $(cat rerun_v2/02_PRIME/inputs/HLA_alleles.txt | tr '\\n' ',') \\
  --output_dir rerun_v2/02_PRIME/outputs/
```

### 03_ImmuneApp
```bash
cd /gpfs/work/bio/zichenli24/tools/ImmuneApp
# Inputs ready at rerun_v2/03_ImmuneApp/inputs/
# Process each HLA allele file
for f in rerun_v2/03_ImmuneApp/inputs/dataset2_MT/*.txt; do
  hla=$(basename "$f" .txt)
  python predict.py --peptides "$f" --hla "$hla" \\
    --output rerun_v2/03_ImmuneApp/outputs/
done
```

### 04_HLAthena
```bash
cd /gpfs/work/bio/zichenli24/tools/HLAthena
# First run prepare_inputs.py with rerun_v2 source data
# Then for each patient:
singularity exec hlathena.sif predict \\
  --peptides rerun_v2/04_HLAthena/inputs/d2_patient{N}.txt \\
  --alleles <allele_list> \\
  --rundir rerun_v2/04_HLAthena/outputs/ \\
  --expr_col_name TPM --logtransform_expr true
```

### 05_MHLAPre
```bash
# Run AFTER DeepHLApan + PRIME complete
cd /gpfs/work/bio/zichenli24/tools/MHLAPre
python train_predict.py \\
  --deephlapan_out rerun_v2/01_DeepHLApan/outputs/ \\
  --prime_out rerun_v2/02_PRIME/outputs/ \\
  --output_dir rerun_v2/05_MHLAPre/outputs/
```

### 06_analysis
```bash
# Run AFTER ALL tools complete
cd /gpfs/work/bio/zichenli24/tools/analysis
python unified_roc_v4.py   # Update paths to rerun_v2 outputs
python run_spearman_all.py # Update paths to rerun_v2 outputs
```

---

## What Changed from Original

| Item | Old | New | Reason |
|------|-----|-----|--------|
| Dataset2 peptides | 101 | **130** | Restored 29 missing (28 indels + 1 SNV) |
| SNV peptides | 100 | **101** | CAPRIN2 p.T525A restored |
| DEL peptides | 0 | **23** | All indels restored |
| INS peptides | 0 | **5** | All insertions restored |
| WT Peptide Seq column | Has trailing space | **Clean** | Fixed |
| HLA A3001 mapping | Mapped to A*31:01 | **A*30:01** | Fixed |
| Source data | Elispot_Dataset2.xlsx | **Reference MOESM4 directly** | Ground truth |

---

## Notes

1. **WT peptide sequences**: For DEL/INS variants, the WT peptide has different length.
   The prepare scripts use WT sequences for sliding windows; empty WT means no WT
   windows are generated (which is correct for frameshifts where WT is meaningless).

2. **HLA format**: All inputs use the format expected by each tool:
   - DeepHLApan: `HLA-A02:01` (no star)
   - PRIME: `A0201` (compact)
   - ImmuneApp: same as DeepHLApan
   - HLAthena: same as PRIME compact

3. **Analysis scripts**: The existing `unified_roc_v4.py` and `run_spearman_all.py`
   need path updates to point to `rerun_v2/` outputs instead of `Data_5/`.

4. **Reproducibility**: Delete all `outputs/` and `logs/` directories and re-run
   `_build_all.py` to regenerate inputs from scratch.

---

*Last updated: 2026-06-30*
"""

with open(os.path.join(SCRIPT_DIR, "README.md"), "w", encoding="utf-8") as f:
    f.write(readme)

print("  -> README.md")

# ══════════════════════════════════════════════════════════
print()
print("=" * 60)
print("ALL DONE!")
print(f"Output: {SCRIPT_DIR}")
print()
print("Ready to run:")
print("  Step 1+2 (parallel): DeepHLApan + PRIME + HLAthena")
print("  Step 3: ImmuneApp")
print("  Step 4: MHLAPre")
print("  Step 5: analysis")
