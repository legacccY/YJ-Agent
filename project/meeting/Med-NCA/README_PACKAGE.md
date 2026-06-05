# Med-NCA Reproduction Package

Independent, zero-deviation reproduction of **Med-NCA** (IPMI 2023) and
**M3D-NCA** (MICCAI 2023) on MSD Task04 Hippocampus and Task05 Prostate.

Author: legacccy (Yu Jia), XJTLU Bioinformatics · Date: 2026-06-05

---

## TL;DR (the three findings)

1. **Hippocampus reproduces faithfully** — per-volume Dice **0.864** vs. paper 0.886 (within 1 std). PASS.
2. **Prostate is NOT reproducible at paper scale** from the public code — **0/9 fresh seeds** (0/11 attempts overall) reach the paper's 1000 epochs. Best partial run 0.672 vs. paper 0.838.
3. **Root cause** — the stochastic fire mask draws from a **CUDA RNG stream that CPU seeding does not control**. The convergence basin is fixed at epoch 1; the *same seed* converges in one run and diverges in another; a mathematically equivalent CPU→GPU change collapses training to Dice 0.0.

Full write-up: **`report/mednca_repro_report.pdf`** (8 pages, 7 figures, 3 appendices including a complete engineering pitfall log).

---

## Package layout

```
Med-NCA/
├── README_PACKAGE.md          ← you are here
├── REPRO_PLAN.md              acceptance plan (A–F groups, RIDGE-aligned)
├── PROJECT_LOG.md             chronological session log (the full process)
├── Plan.md                    early planning notes
├── requirements.lock          pinned env (torch 2.7.1+cu118, py3.9)
├── report/
│   ├── mednca_repro_report.tex / .pdf
│   └── figures/               7 figures + their plot_*.py (all CSV-driven)
├── code/                      all training / eval / analysis scripts
├── results/                   30+ CSV/JSON + R1/R2 reports + training logs
└── checkpoints/
    └── r1_hippocampus_official/   ← R1 anchor ckpt (eval-only reproduces 0.864)
```

**Not included** (fetch separately, see below):
- `data/` — the MSD raw datasets (22 GB, redistribution-restricted).
- `M3D-NCA-official/` — the upstream code; clone it yourself.

---

## Reproducing the numbers

### 0. Environment
```bash
conda create -n mednca python=3.9 && conda activate mednca
pip install -r requirements.lock          # torch 2.7.1+cu118
```

### 1. Upstream code
```bash
git clone https://github.com/MECLabTUDA/M3D-NCA.git M3D-NCA-official
```

### 2. Data (MSD)
```powershell
# Hippocampus (Task04) + Prostate (Task05)
./code/download_data.ps1        # Task04
./code/download_task05.ps1      # Task05 (S3 direct link)
# extract with GNU tar (NOT bsdtar — see pitfall #10), then:
#   find data -name '._*' -delete
```

### 3. R1 Hippocampus — eval-only (uses the bundled checkpoint)
```bash
python code/eval_r1.py \
  --ckpt checkpoints/r1_hippocampus_official/models/epoch_<E> --seed 42
# -> results/r1_official_single.csv : per-volume Dice 0.8644
```

### 4. R2 Prostate — training (needs a GPU; expect instability)
```bash
# single run
R2_SEED=42 R2_EPOCHS=1000 python code/run_r2_prostate.py
# the 9-seed sweep: launch one job per seed 42..50
# (we used XJTLU HPC RTX 4090; see PROJECT_LOG.md for the Slurm setup)
```
**Expect divergence.** After epoch 10, if training loss > 3 and validation
Dice < 0.05, the run is dead — cancel it. See pitfall log (report Appendix B).

### 5. Regenerate the figures (no GPU / no data needed)
```bash
cd report/figures && for f in plot_*.py; do python "$f"; done
```

---

## Key result files

| File | What |
|---|---|
| `results/r1_official_single.csv` | R1 per-volume Dice (anchor 0.8644) |
| `results/r2_prostate_single.csv` | R2 best partial run (0.672 @ 301 ep) |
| `results/r2_seed_sweep_traces.csv` | per-epoch loss, all 9 seeds (388 rows) |
| `results/r2_seed_sweep_summary.json` | per-seed basin / crash epoch / peak Dice |
| `results/c1_steps_summary.json` | inference-step sweep (peak at 16) |
| `results/v1_robustness_summary.json` | corruption robustness |
| `results/v2_r5_summary.json` | NQM quality metric ↔ Dice (ρ=0.47) |
| `results/r2_efficiency.json` | params / memory / latency / MACs |

Every number carries a bootstrap 95% CI, a fixed seed, and a run/job ID.

---

## Targets (Med-NCA IPMI'23 Table 1)

| Task | Med-NCA | U-Net | Our repro |
|---|---|---|---|
| Hippocampus | 0.886 ± 0.042 | 0.858 | **0.864** (PASS) |
| Prostate | 0.838 ± 0.083 | 0.799 | **0.672** best partial — **not reproducible at scale (0/11)** |
