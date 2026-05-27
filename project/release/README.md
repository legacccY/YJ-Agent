<div align="center">

# Quality-Conditioned Temperature Scaling
### Post-hoc Calibration under Image Quality Shift

[![License: MIT](https://img.shields.io/badge/Code-MIT-blue.svg)](LICENSE)
[![Data: CC BY-NC-SA 4.0](https://img.shields.io/badge/Data-CC--BY--NC--SA--4.0-lightgrey.svg)](DATASET_CARD.md)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-green.svg)](requirements.txt)
[![PyTorch 2.7](https://img.shields.io/badge/PyTorch-2.7%20(CUDA%2012.6)-ee4c2c.svg)](requirements.txt)
[![Benchmark: ITB v1.0](https://img.shields.io/badge/Benchmark-ITB%20v1.0-orange.svg)](DATASET_CARD.md)

**Official code and benchmark for the BMVC 2026 paper** *(Anonymous Authors, under review)*

</div>

---

## TL;DR

> **Standard temperature scaling can make a model *less* reliable on low-quality images** — it
> *reverses* the calibrator's quality-awareness. We diagnose why, and fix it with **one extra
> parameter**.

On a strongly bottlenecked backbone, the entropy–quality correlation $\rho(\text{entropy},\bar q)$
**flips sign from $-0.153$ to $+0.241$** after vanilla temperature scaling (TS): the calibrated model
becomes *more* confident on *worse* images. **Quality-Conditioned Temperature Scaling (QCTS)** removes
this with a quality-dependent temperature

$$T(\bar q) = \mathrm{softplus}\big(T_0 + \alpha\,(1-\bar q)\big),$$

restoring $\rho = -0.249$ and cutting the quality-conditional calibration gap (QCDI) by **73%** over
standard TS — using just **two parameters** and **no retraining**.

---

## Key Results (ITB-LQ, low-quality subset)

| Method | ECE-LQ ↓ | ρ(entropy, q̄) | Note |
|---|---|---|---|
| MC Dropout (30×) | 0.615 | −0.114 | high AUC, quality-oblivious |
| Deep Ensemble (5×) | 0.440 | −0.123 | high AUC, quality-oblivious |
| Std VIB | 0.146 | −0.153 | quality-aware but mis-calibrated |
| Std VIB + TS | 0.175 | **+0.241** | ⚠️ quality-awareness **reversed** |
| **Std VIB + QCTS (ours)** | **0.079** | **−0.249** | ✅ reversal fixed, best ECE |

QCTS generalizes across backbones (ResNet-50, ViT-Tiny, ConvNeXt-Tiny, Swin-Tiny) and to ImageNet-C
corruption severities, where the quality scalar is the known severity level rather than a learned
score. Full tables: see the paper and `scripts/generate_tables.py`.

---

## Install

### Docker (recommended)

```bash
docker build -t itb-qcts:v1.0 .
docker run --gpus device=0 -v $(pwd)/data:/workspace/data itb-qcts:v1.0
```

### Local

```bash
pip install -r requirements.txt
bash reproduce.sh
```

**Requirements:** Python 3.10+, PyTorch 2.7 (CUDA 12.6). QCTS itself fits in CPU-seconds on cached
logits; the full pipeline (backbone inference → ITB evaluation → calibration) runs in about an hour
on a single consumer GPU (e.g. an RTX 4070-class card) — no cluster required.

---

## Apply QCTS to Your Own Model

QCTS is a drop-in post-hoc calibrator: fit on a validation set, then rescale test logits by a
quality-dependent temperature.

```python
import numpy as np
from qcts import QCTSCalibrator

# Fit on your validation set (logits, per-input quality scalar, targets)
cal = QCTSCalibrator()
cal.fit(val_logits, val_qbar, val_targets)
print(cal)                       # QCTSCalibrator(T0=1.1700, alpha=0.9554)

# Calibrate test predictions
prob_calibrated = cal.predict(test_logits, test_qbar)
```

The quality scalar `qbar` can be:

- the **5-head IQA module** (`iqa/five_head.py`) — best performance on dermoscopy; or
- **any per-input quality proxy** — Laplacian variance, BRISQUE, or a known corruption severity.

---

## Reproduce Paper Numbers

| What | Command |
|---|---|
| Download ITB v1.0 metadata | `python scripts/download_itb.py` |
| Table 1 (main results) | `bash reproduce.sh` |
| Table 3 (backbone universality) | `python scripts/run_qcts.py --backbone all` |
| Calibration tables | `python scripts/generate_tables.py` |

---

## Repository Structure

```
├── itb/                  # ITB evaluation protocol
│   ├── metrics.py        # ECE, QCDI, Spearman rho, bootstrap CI
│   └── evaluate.py       # Full ITB evaluation report
├── qcts/
│   └── calibrate.py      # QCTSCalibrator (fit + predict)
├── iqa/
│   └── five_head.py      # 5-head IQA module (EfficientNet-B0 backbone)
├── baselines/
│   └── temperature_scaling.py
├── scripts/
│   ├── download_itb.py   # Fetch ITB v1.0 metadata from Zenodo
│   ├── run_qcts.py       # Fit + evaluate QCTS
│   └── generate_tables.py
├── configs/default.yaml
├── data/README.md        # How to obtain the raw images
├── DATASET_CARD.md       # ITB v1.0 dataset card
├── Dockerfile · docker-compose.yml
├── reproduce.sh
└── requirements.txt
```

---

## ITB v1.0 — Image Triage Benchmark

ITB partitions four public dermatology datasets (**ISIC 2020, FitzPatrick17k, HAM10000, PAD-UFES**)
into quality-stratified subsets using a five-dimensional learned quality scalar (sharpness,
brightness, completeness, colour temperature, contrast).

- **Zenodo:** DOI `10.5281/zenodo.XXXXXXX` (activated upon acceptance)
- **License:** CC-BY-NC-SA 4.0 for metadata; raw images remain under their original licenses
- **Details:** see [`DATASET_CARD.md`](DATASET_CARD.md)

The repository redistributes only derived metadata (quality scores, subset labels, targets) and
pre-computed baseline predictions; raw images are downloaded from their original sources.

---

## Citation

```bibtex
@inproceedings{anonymous2026qcts,
  title     = {Quality-Conditioned Temperature Scaling: Post-hoc Calibration under Image Quality Shift},
  author    = {Anonymous Authors},
  booktitle = {British Machine Vision Conference (BMVC)},
  year      = {2026},
  note      = {Under review}
}
```

---

## License

- **Code:** MIT — see [`LICENSE`](LICENSE)
- **Dataset metadata:** CC-BY-NC-SA 4.0 — see [`DATASET_CARD.md`](DATASET_CARD.md)
