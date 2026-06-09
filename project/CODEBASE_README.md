# VisiSkin-Agent: Quality-Adaptive Dermoscopy Triage via Q-VIB

Official implementation of **"Quality-Adaptive Dermoscopy Triage with Variational Information Bottleneck"** (MICCAI 2027 submission).

## Overview

VisiSkin-Agent is a clinical AI system that simultaneously assesses dermoscopy image quality and triages melanoma risk. The core model, **Q-VIB (Quality-Adaptive VIB)**, adapts its prior variance to image quality, producing well-calibrated uncertainty estimates that correlate with image quality (Proposition 2).

**Key results on ITB-LQ (low-quality images)**:
- Q-VIB Full achieves **ECE 0.149** vs MC Dropout 0.613 / Deep Ensemble 0.440
- AUC consistently better than Std VIB across 3 seeds (CV < 2%)
- Entropy–q̄ Spearman ρ = −0.192 (p < 1e-24), confirming quality-aware uncertainty

## Quick Start

```bash
git clone <repo>
cd project
pip install -r requirements.txt

# Run the Gradio demo (uses pretrained weights from Zenodo)
python app.py
```

Pretrained weights and data splits: **[Zenodo DOI: TBD]**

## Installation

```bash
pip install -r requirements.txt
```

Tested on Python 3.12, CUDA 12.6 (RTX 4070 Laptop GPU).

## Reproducing Results

See `reproduce.sh` for the full pipeline. Steps at a glance:

### 1. Data

Download [ISIC 2020](https://www.kaggle.com/c/siim-isic-melanoma-classification/data) and [FitzPatrick17k](https://github.com/mattgroh/fitzpatrick17k):

```bash
kaggle competitions download -c siim-isic-melanoma-classification
kaggle datasets download -d mattgroh/fitzpatrick17k
```

Unzip to `data/raw/isic2020/` and `data/raw/fitzpatrick17k/` respectively.

### 2. Precompute features

```bash
python precompute_efficientnet.py   # EfficientNet-B0 features (~728 MB)
python create_split.py              # 70/10/20 split by isic_id
```

### 3. Train Q-VIB Full (F)

```bash
python train_qad.py --config configs/qad_efnet_nw0.yaml --seed 42 \
    --ckpt-dir checkpoints/efnet_s42
```

Training ~30 min on RTX 4070 (30 epochs, batch 256).

### 4. Run ITB benchmark

```bash
python benchmark/build_itb.py    # Build quality-stratified subsets
python run_experiments.py        # Inference for all baselines
python analyze_results.py        # Figures + significance tests
```

Figures are saved to `results/figures/` (DPI 300, MICCAI-compatible).

### 5. External validation (HAM10000 / PAD-UFES)

```bash
python precompute_external_features.py
python run_external.py
python analyze_external.py
```

## Project Structure

```
project/
├── models/
│   ├── q_vib_encoder.py           # Q-VIB encoder (Transformer + quality tokenizer)
│   ├── qad_classifier.py          # MLP head
│   ├── quality_adaptive_prior.py  # sigma^2(q-bar) prior (Lemma 1)
│   └── q_vib_loss.py              # VIB + CE loss
├── agent/
│   ├── orchestrator.py            # ReAct agent (Qwen3-4B + rule fallback)
│   └── tools.py                   # quality_assess / extract_features / triage
├── baselines/
│   ├── temperature_scaling.py
│   └── focal_loss_baseline.py
├── benchmark/
│   ├── build_itb.py               # ITB: 4 quality-stratified subsets
│   └── metrics.py                 # ECE / AUC / Brier / Sens@95Spec
├── train_qad.py                   # Training script
├── run_experiments.py             # ITB inference for all baselines
├── analyze_results.py             # Figures and significance tests
├── configs/
│   ├── qad_efnet_nw0.yaml         # Q-VIB Full (recommended)
│   ├── qad_stdvib_nw0.yaml        # Std VIB baseline
│   └── qad_mcdropout.yaml         # MC Dropout baseline
└── reproduce.sh                   # One-command reproduction
```

## Baselines

| ID | Name | Description |
|----|------|-------------|
| A | EfficientNet-B3 (Direct) | Fine-tuned classification without quality awareness |
| D | Std VIB | Fixed prior N(0,I), no quality tokenizer |
| E | Adaptive Prior | Quality-adaptive sigma^2(q-bar), no tokenizer |
| **F** | **Q-VIB Full (Ours)** | **Full model: adaptive prior + quality tokenizer** |
| TS | Std VIB + TS | Temperature scaling (Guo et al. 2017) |
| H | Focal+LS | Focal loss + label smoothing |
| I | MC Dropout | 30 MC forward passes, dropout=0.3 (Gal & Ghahramani 2016) |
| J | Deep Ensemble | 5 independently trained Std VIB models (Lakshminarayanan 2017) |
| G | Q-VIB+TokFT* | Supplementary: higher AUC at cost of calibration |

## VisiEnhance Evaluation Suite (E1–E12)

> Registered session 21 (2026-06-09). These scripts evaluate the **VisiEnhance** enhancement model and the quality-routing agent, on top of the Q-VIB triage core. All run on **XJTLU HPC** (local RTX 4070 Laptop crashes on VisiEnhance forward — see Notes). Each evaluator has a `run_*_hpc.py` paramiko wrapper and, where applicable, a `submit_*.sh` SLURM script.

### Evaluation scripts

| Script | Experiment | What it computes |
|--------|-----------|------------------|
| `eval_diag_paired.py` | E3 / E7 | Diagnosis-preserving paired eval (degrade@256 → enhance → crop224 → B3); dAUC, agreement rate, KL, dangerous_flip + paired bootstrap |
| `eval_e2_perdim.py` | E2 | Per-degradation-dimension PSNR |
| `eval_e6_severe.py` | E6 | Safety margin dAUC on the *severe* degradation band |
| `eval_e12_speed.py` | E12 | End-to-end inference speed |
| `eval_e5_salvage.py` | E5 | SalvageRate (norm-q routing: enhance uses raw-q, routing tier uses norm-q̄) |
| `eval_qnorm_compare.py` | — | visiscore feeding A/B: raw-q[0,1]@256 vs ImageNet-NORM-q |

### Ablation / figure scripts

| Script | Purpose |
|--------|---------|
| `run_e1_ablation_hpc.py` | E1 — FiLM same-pipeline PSNR ablation |
| `run_eval_filmabl_hpc.py` | FiLM diagnosis ablation |
| `dump_dflip_figure_data.py` + `render_dflip_figure.py` | `fig_dflip` — dump data then render |
| `plot_e5_salvage.py` | `fig_e5_salvage` plot |

### HPC wrappers & submit scripts

- **paramiko wrappers** (submit + monitor on HPC): `run_e2_hpc.py`, `run_e6_hpc.py`, `run_e12_hpc.py`, `run_e5_hpc.py`, `run_qnorm_hpc.py`, `run_dflip_hpc.py`, `run_e1_ablation_hpc.py`, `run_eval_filmabl_hpc.py`
- **SLURM submit scripts**: `submit_e5.sh`, `submit_qnorm.sh`, `submit_filmabl.sh`, `submit_e1abl.sh`, `submit_dflip.sh` (E2/E6/E12 are submitted directly by their `run_*_hpc.py` wrappers, no standalone `submit_*.sh`)

### E1–E12 status (as of session 21)

| Done (has data) | Pending (needs retrain / new data) |
|-----------------|------------------------------------|
| ✅ E1, E2, E3, E5, E6, E7, E8, E12 | ❌ E4, E9, E10, E11 |

### Notes (read before extending — avoids known pitfalls)

- **visiscore feeding口径**: visiscore must be fed **ImageNet-NORM 224** inputs (timm backbone). The current enhance/eval chain feeds **raw [0,1] @256**, which degrades q̄ (discovered session 21, see `PROJECT_LOG.md`). The enhancement model's **raw-q training口径 is self-consistent**, so existing results remain valid; the **agent / E5 routing uses an independent norm-q̄** path.
- **Local GPU**: running VisiEnhance forward on the RTX 4070 Laptop reliably triggers a CUDA illegal-access crash → run all VisiEnhance eval on **HPC or CPU**.

## Citation

```bibtex
@inproceedings{yu2027visiskin,
  title={Quality-Adaptive Dermoscopy Triage with Variational Information Bottleneck},
  author={Yu, Jia},
  booktitle={Medical Image Computing and Computer Assisted Intervention (MICCAI)},
  year={2027}
}
```

## License

MIT — see `LICENSE`.
