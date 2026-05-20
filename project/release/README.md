# ITB + QCTS: Quality-Aware Calibration for Dermatology AI

Code and data for the BMVC 2026 paper:
> **Quality-Aware Calibration: Exposing and Mitigating Calibration Collapse under Image Quality Shift in Dermatology AI**
> Anonymous Authors, BMVC 2026

---

## Key Findings

- Standard temperature scaling (TS) can **reverse** a backbone's quality-awareness: on Std VIB, ρ(entropy, q̄) flips from −0.153 to +0.241 after TS.
- **QCTS** (Quality-Conditioned Temperature Scaling) fixes this with one extra parameter: T(q̄) = softplus(T₀ + α(1 − q̄)).
- MC Dropout and Deep Ensembles are **quality-oblivious** despite high AUC (ECE on low-quality images 0.44–0.62, ~3× worse than simpler alternatives).
- QCTS reduces QCDI by 73% over standard TS and extends to ResNet-50, ViT-Tiny, ConvNeXt-Tiny, Swin-Tiny, and ImageNet-C corruptions.

---

## Quick Start

### Docker (recommended)

```bash
# Build
docker build -t itb-qcts:v1.0 .

# Reproduce Table 1 (~2h on A100)
docker run --gpus device=0 -v $(pwd)/data:/workspace/data itb-qcts:v1.0
```

### Local

```bash
pip install -r requirements.txt
bash reproduce.sh
```

---

## Project Structure

```
├── itb/                  # ITB evaluation protocol
│   ├── metrics.py        # ECE, QCDI, Spearman rho, bootstrap CI
│   └── evaluate.py       # Full ITB evaluation report
├── qcts/
│   └── calibrate.py      # QCTSCalibrator (fit + predict)
├── iqa/
│   └── five_head.py      # 5-Head IQA module (EfficientNet-B0)
├── baselines/
│   └── temperature_scaling.py
├── scripts/
│   ├── download_itb.py   # Download ITB v1.0 metadata from Zenodo
│   ├── run_qcts.py       # Fit + evaluate QCTS
│   └── generate_tables.py
├── configs/default.yaml
├── data/README.md        # How to download raw images
├── DATASET_CARD.md       # ITB v1.0 dataset card
├── Dockerfile
├── reproduce.sh
└── requirements.txt
```

---

## Applying QCTS to Your Own Model

```python
import numpy as np
from qcts import QCTSCalibrator

# Fit on your validation set
cal = QCTSCalibrator()
cal.fit(val_logits, val_qbar, val_targets)
print(cal)  # QCTSCalibrator(T0=1.1700, alpha=0.9554)

# Calibrate test predictions
prob_calibrated = cal.predict(test_logits, test_qbar)
```

The quality scalar `qbar` can be:
- The 5-head IQA module (see `iqa/five_head.py`) — best performance on dermoscopy
- Any per-input quality proxy (Laplacian variance, BRISQUE, corruption severity, etc.)

---

## Reproducing Paper Numbers

| What | Command |
|------|---------|
| Download ITB v1.0 | `python scripts/download_itb.py` |
| Table 1 (main results) | `bash reproduce.sh` |
| Table 3 (backbone universality) | `python scripts/run_qcts.py --backbone all` |
| Supplementary threshold sensitivity | `python scripts/threshold_sensitivity.py` |

---

## ITB v1.0 Dataset

The Image Triage Benchmark partitions four public dermoscopy datasets (ISIC 2020,
FitzPatrick17k, HAM10000, PAD-UFES) into quality-stratified subsets using a
5-dimensional learned quality scalar.

- **Zenodo**: DOI 10.5281/zenodo.XXXXXXX (active after acceptance)
- **License**: CC-BY-NC-SA 4.0 (metadata); raw images under original licenses

See `DATASET_CARD.md` for full details.

---

## Requirements

- Python 3.10+
- PyTorch 2.7 (CUDA 12.6)
- See `requirements.txt` for full pinned versions

---

## License

Code: MIT (see `LICENSE`)
Dataset metadata: CC-BY-NC-SA 4.0 (see `DATASET_CARD.md`)
