# netMHCstabpan-1.0 — MHC-peptide stability tool (DTU)

Service: quantimmu-bench §tools_present  lever=netMHCstabpan-1.0 (stability)

> ⚠️⚠️ **THIS KIT IS READY, NOT EXECUTED.** The three real steps —
> **(1) applying for / installing the DTU binary, (2) building & uploading
> `net.sif` to HPC, (3) running the sbatch job** — are all **MAIN-THREAD
> decision points** because they involve a **DTU academic license** and
> **outbound HPC transfer**. Nothing here has been run or uploaded.

## Why this tool needs a container (root-cause, do NOT re-debug)

The `netMHCstabpan-1.0` binary and its `netMHCpan-2.8` backend are linked
against **GLIBC_2.29**. The HPC is el8 with **glibc 2.28**, so running directly
fails:

```
./netMHCpan: version `GLIBC_2.29' not found
```

**Verdict = apptainer container** (`net.def`, base `ubuntu:20.04` → glibc 2.31,
satisfies GLIBC_2.29 at runtime). We bind the DTU `ext_tools` tree into the
container and run the binary inside it. This is exactly how LENS
(uselens.io) officially ships the DTU net* trio — proven precedent.

Rejected alternatives (researcher 2026-06-29):
- **conda sysroot / cross-glibc** — fixes compile time, not runtime → no good.
- **patchelf --set-interpreter** — extremely brittle on a closed-source binary
  that also dlopen's helpers → rejected.

## TL;DR workflow

```
# Step 0 (MAIN THREAD) — apply for & install the DTU binary on HPC:
#   /gpfs/work/bio/jiayu2403/quantimmu/ext_tools/netMHCstabpan-1.0/
#   (netMHCpan-2.8 backend already present at ext_tools/netMHCpan-2.8)

# Step 1 (MAIN THREAD) — build the container (two routes, see net.def):
#   apptainer build --fakeroot net.sif net.def        # if HPC has fakeroot
#   # else: build with root locally, then scp net.sif up (outbound transfer)

# Step 2 (ONE-TIME) — rewrite the tcsh wrapper env paths (see checklist below)

# Step 3 (HPC) — score all alleles (reuses the -BA .pep inputs):
mkdir -p /gpfs/work/bio/jiayu2403/quantimmu/logs
sbatch run_netmhcstabpan.sh

# Step 4 (local or HPC) — parse → bb_idx table
python parse_netmhcstabpan.py
```

## Input reuse

We do **not** regenerate inputs. The job reuses the **exact** per-allele `.pep`
files + `allele_map.tsv` + `pep_index.csv` that the netMHCpan-4.1 -BA job uses
(same peptides × alleles):

```
scripts/out/newtools/netmhcpan_ba_inputs/   <- .pep, allele_map.tsv, pep_index.csv  (reused)
scripts/out/newtools/netmhcstabpan_inputs/  <- <allele>_stab.xls  (this job's outputs, separate dir)
```

Separate output dir = stability `*_stab.xls` never clobber the -BA `*_out.xls`.

## tcsh wrapper rewrite checklist (do ONCE before first run)

The netMHCstabpan launcher is a tcsh script with **host paths baked in** that
won't exist inside the container. Edit them to **container-visible (post-bind)**
paths or you'll get "cannot find data dir" / "backend not found":

```
setenv NMHOME    /ext_tools/netMHCstabpan-1.0     # was a /gpfs/... path
setenv TMPDIR    /tmp                              # must be writable in container
setenv NETMHCpan /netMHCpan-2.8/netMHCpan         # backend bind target (var name varies)
```

`grep` the wrapper for `NMHOME` / `netMHCpan` / `NetMHCpan` and fix **every**
`/gpfs` path to its bind target. Check the netMHCpan-2.8 wrapper's own `NMHOME`
too.

Bind layout used by `run_netmhcstabpan.sh`:

| host | container |
|---|---|
| `${ROOT}/ext_tools` | `/ext_tools` |
| `${ROOT}/ext_tools/netMHCpan-2.8` | `/netMHCpan-2.8` |
| `netmhcpan_ba_inputs/` | `/pep_in` |
| `netmhcstabpan_inputs/` | `/pep_out` |

## Output format (netMHCstabpan, DTU official)

```
pos  HLA  peptide  Identity  Pred  Thalf(h)  %Rank_Stab  BindLevel
```

| field | direction |
|---|---|
| `Pred` | higher = MORE stable |
| `Thalf(h)` | higher = MORE stable (half-life, hours) |
| `%Rank_Stab` | LOWER = more stable |
| `BindLevel` | SB / WB |

## Score direction (unified across benchmark = higher = stronger)

```
netmhcstabpan_score = Pred                  (higher = more stable)
fallback if Pred missing: -%Rank_Stab       (negated → higher = more stable)
```

## Output schema

File: `scripts/out/newtools/netmhcstabpan_DS1DS2_scores.csv`

| Column | Type | Notes |
|---|---|---|
| `bb_idx` | int | join key to master_backbone.csv |
| `netmhcstabpan_Pred` | float | stability prediction; higher = more stable |
| `netmhcstabpan_Thalf` | float | half-life hours; higher = more stable |
| `netmhcstabpan_RnkStab` | float | %Rank_Stab; lower = more stable |
| `netmhcstabpan_score` | float | `Pred` (fallback `-RnkStab`); higher = stronger |
| `is_MT` | bool str | `True` = MT_Subpeptide; `False` = WT_Subpeptide |
| `pending_DTU_consent` | str | always `True` — DTU red line |

One `bb_idx` can appear twice (MT and WT).

## DTU licensing red line

`pending_DTU_consent = True` on every row. **Do NOT publish or share benchmark
numbers derived from netMHCstabpan output until DTU (Technical University of
Denmark) provides written consent** for use in this benchmark context.

## ⚠️ Verify-on-deploy TODO (flags/paths NOT confirmed yet)

The netMHCstabpan-1.0 backend is **old** (netMHCpan-2.8 era); flags below
follow net* convention but are **unverified for this exact version**. Before
the real run, inside the container:

```
apptainer exec net.sif /ext_tools/netMHCstabpan-1.0/netMHCstabpan -h
```

Confirm:
1. **peptide-file flag** is `-p` (vs `-f`/`-pf`).
2. **allele flag** is `-a`, comma-joined, no spaces.
3. **`-xls` / `-xlsfile` exist.** If NOT (likely for this old build), drop them
   in `run_netmhcstabpan.sh` and redirect stdout instead:
   `... netMHCstabpan -a <allele> -p <pep> > <allele>_stab.xls`
   — then `parse_netmhcstabpan.py._split_row` falls back to whitespace splitting
   (already handled), but re-check the column headers it fuzzy-matches.
4. **Exact env-var name** the wrapper uses to find the netMHCpan-2.8 backend
   (could be `NETMHCpan`, `NMHOME`, or a hardcoded path) — fix in the wrapper.

## Files

| File | Purpose |
|---|---|
| `net.def` | apptainer definition (ubuntu:20.04 + tcsh/gawk → glibc 2.31 shim) |
| `run_netmhcstabpan.sh` | SLURM batch: loop alleles, run netMHCstabpan in container |
| `parse_netmhcstabpan.py` | Parse `*_stab.xls` + pep_index → netmhcstabpan_DS1DS2_scores.csv |
| `README.md` | this file |
