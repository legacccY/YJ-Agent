# gdn2vessel/src — Module Guide

## Directory Layout

```
src/
  datasets/
    drive.py       DRIVE retinal vessel dataset (green+CLAHE preprocessing)
  models/
    unet.py        Pure CNN U-Net baseline (关3 对照)
    unet_gdn2.py   U-Net + GDN-2 associative memory (关3 主模型)
  train_pilot.py   Pilot training script (DRIVE, CLI)
  README.md        This file
tests/
  test_shapes.py   pytest — shape/contract/GT-isolation tests (CPU, no GPU needed)
```

---

## 1  How to Run

### Pilot training (DRIVE)

```bash
# From project root (project/meeting/ACCV/gdn2vessel/)

# Pure CNN baseline
python src/train_pilot.py \
  --model unet \
  --data_root /path/to/DRIVE \
  --output_dir outputs/unet_baseline

# GDN-2 memory model (naive backend, HPC-tested)
python src/train_pilot.py \
  --model unet_gdn2 \
  --data_root /gpfs/work/bio/jiayu2403/gdn2vessel/data/vessel/DRIVE \
  --output_dir outputs/unet_gdn2_pilot \
  --backend naive
```

Key flags:
- `--no_memory`     degrade unet_gdn2 to pure CNN (same as unet baseline, for ablation)
- `--smoke`         exit after 2 steps (CI smoke test)
- `--num_workers 0` safe default on Windows; use 2-4 on HPC Linux

### Tests

```bash
cd project/meeting/ACCV/gdn2vessel
python -m pytest tests/ -v
```

---

## 2  GDN-2 Backend Switch

The GDN-2 kernel has two backends:

| Backend | Module | Status |
|---|---|---|
| `naive` | `fla.ops.gated_delta_rule.naive.naive_chunk_gated_delta_rule` | HPC-tested PASS (fwd/bwd finite) |
| `chunk` | `fla.ops.gated_delta_rule.chunk_gated_delta_rule` | Pending — Triton hang on HPC (FLA issue #734) |

**Current default: `naive`** (set by `GDN2_BACKEND=naive` env or `--backend naive` CLI).

Switch to `chunk` once FLA #734 is resolved:
```bash
GDN2_BACKEND=chunk python src/train_pilot.py --model unet_gdn2 ...
# or
python src/train_pilot.py --model unet_gdn2 --backend chunk ...
```

---

## 3  Memory Module Design Notes

- Sequence formed by flattening bottleneck spatial feature (H/16 × W/16).
  For patch_size=512: 32×32 = **1024 tokens** — exactly at the ≤1K limit.
- **Keys come from input features only** — never from GT annotations (STORY red line).
- `use_memory=False` degrades UNetGDN2 to pure CNN (verified by pytest).
- Multi-direction scan: currently single direction (raster order).
  Interface stubbed in `GDN2MemoryModule(directions=N)` — merge logic TBD in P2.

---

## 4  DRIVE Preprocessing

Standard retinal fundus preprocessing (per FR-UNet / SA-UNet DRIVE convention):
1. **Green channel extraction** — highest vessel/background contrast in fundus RGB
2. **CLAHE** (clip_limit=2.0, 8×8 tiles) — standard for low-contrast fundus images
3. **Normalise** to [0,1] then standardise (GREEN_MEAN=0.5, GREEN_STD=0.1)
   - TODO: recompute exact per-training-set mean/std for final experiments
4. **FOV mask** — loss and metrics computed only inside field-of-view (mask=1 region)

Data split: 20 training images → 16 train / 4 val (fixed, deterministic).
Test set (20 images) has no public GT; not used in this pilot.

---

## 5  state.json Schema

`train_pilot.py` writes `{output_dir}/state.json` every epoch:

```json
{
  "epoch": 42,
  "train_loss": 0.123456,
  "val_dice": 0.810234,
  "best_dice": 0.815000,
  "status": "running"
}
```

`status` is `"running"` during training, `"done"` when finished (or early-stopped),
`"error"` if an exception is caught. The `/loop` monitor reads this file.
