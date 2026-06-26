# NetMHCpan-4.1 -BA  Proxy Baseline

Service: quantimmu-bench §Tier-2  lever=NetMHCpan 4.1 -BA proxy baseline

## TL;DR workflow

```
# Step 1 (local Windows) — generate .pep files + index
python prep_netmhcpan_ba.py

# Step 2 — upload inputs dir to HPC
# scp/rsync scripts/out/newtools/netmhcpan_ba_inputs/ → HPC same relative path

# Step 3 (HPC) — score all alleles
mkdir -p /gpfs/work/bio/jiayu2403/quantimmu/logs
sbatch run_netmhcpan_ba.sh

# Step 4 (local or HPC) — parse scores → bb_idx table
python parse_netmhcpan_ba.py
```

## HLA allele format

| Context | Format | Example |
|---|---|---|
| master_backbone.csv | `HLA-A*02:01` | star + colon |
| netMHCpan CLI `-a` | `HLA-A02:01` | no star, colon kept |
| .pep filename | `HLA-A02-01.pep` | no star, colon→hyphen |

Conversion: `hla_to_netmhcpan(h) = h.replace('*', '')`

## Score direction

```
netmhcpan_ba_score = -Rnk_BA
```

`%Rank_BA` from netMHCpan: **lower = stronger binding**.
Negated so that **higher score = stronger binding = more immunogenic** — consistent
with the other tools in this benchmark.

## Output schema

File: `scripts/out/newtools/netmhcpan_ba_DS1DS2_scores.csv`

| Column | Type | Notes |
|---|---|---|
| `bb_idx` | int | join key to master_backbone.csv |
| `netmhcpan_ba_Aff_nM` | float | affinity nM; lower = stronger |
| `netmhcpan_ba_Rnk_BA` | float | %Rank_BA; lower = stronger |
| `netmhcpan_ba_score` | float | `-Rnk_BA`; higher = stronger |
| `is_MT` | bool str | `True` = MT_Subpeptide; `False` = WT_Subpeptide |
| `pending_DTU_consent` | str | always `True` — see red line below |

One bb_idx can appear twice: once for MT_Subpeptide, once for WT_Subpeptide.

## DTU licensing red line

`pending_DTU_consent = True` on every output row.
**Do NOT publish or share benchmark numbers derived from netMHCpan output
until DTU (Technical University of Denmark) provides written consent** for
use of netMHCpan-4.1 in this benchmark context.

## Files

| File | Purpose |
|---|---|
| `prep_netmhcpan_ba.py` | Read master_backbone → write per-allele .pep + pep_index.csv + allele_map.tsv |
| `run_netmhcpan_ba.sh` | SLURM batch: loop alleles, run netMHCpan -BA -xls per allele |
| `parse_netmhcpan_ba.py` | Parse *_out.xls + pep_index → netmhcpan_ba_DS1DS2_scores.csv |

## NetMHCpan binary (HPC)

```
/gpfs/work/bio/jiayu2403/quantimmu/ext_tools/netMHCpan-4.1/netMHCpan
```

Already patched for HPC paths (see `HPC/deploy/hpc_dtu_setup.sh`).
