"""R2: Med-NCA (2D two-level) on ISIC 2018 Task1 skin lesion segmentation (RGB).

Faithful to official src/examples/train_Med_NCA.py architecture + per-image
Dice CSV + bootstrap 95% CI, aligned with run_r1_hippocampus.py style.

Acceptance R2 (REPRO_PLAN §5):
  per-image Dice mean >= 0.752  (paper ~0.772, tolerance ±0.02)

Architecture:
  Two BackboneNCA stacks (coarse → fine), Agent_Med_NCA, DiceBCELoss.
  channel_n=24 (ch0..ch2 = RGB input, ch3..ch23 = 21 hidden state dims),
  input_channels=3 (RGB), output_channels=1 (binary mask).
  Two-level input_size: coarse (32,32) global context → fine (128,128) patch
  detail. Fine patch bumped from 64→128 because ISIC original images are
  ~700×900px; 64px patch captures too little structure. Coarse scaled 2× to
  maintain the same 1:4 coarse:fine ratio as the official hippocampus config.

Data:
  ISIC 2018 Task1, 2594 image pairs (jpg + png), data_split [0.7, 0, 0.3].
  Custom ISIC2D_RGB_Dataset adapter (code/dataset_isic2d.py) — official
  framework has no native 2D RGB JPG dataset class.

Pixel alignment:
  Both image and GT mask are resized to the same dsize via cv2.resize;
  image uses INTER_CUBIC, GT uses INTER_NEAREST (binary values preserved).

§3 数字溯源 fields in summary.json:
  seed             — global random seed used (numpy + torch)
  git_commit       — short git hash at run time (subprocess git rev-parse)
  epochs_target    — exp.get_max_steps()   (what the Experiment thinks it should run)
  epochs_trained_to— exp.currentStep       (actual steps completed)
  NOTE: deliberately NOT using python variable N_EPOCH in these fields.
  Experiment.reload() can overwrite runtime config from an existing config.dt
  on disk, silently locking n_epoch to the old value while python's N_EPOCH
  still holds the new value → summary would lie. Use exp API instead.

To smoke test (2 epochs, no GPU needed):
    set R2_EPOCHS=2
    D:\\Anaconda\\envs\\mednca\\python.exe code\\run_r2_isic.py

To run full training (300 epochs default, extend if Dice<0.752):
    D:\\Anaconda\\envs\\mednca\\python.exe code\\run_r2_isic.py

Environment variables:
    R2_EPOCHS   : number of training epochs (default 300; paper uses 1000)
    CUDA_VISIBLE_DEVICES : GPU id (default 0)
"""
import os
import sys
import json
import csv
import time
import subprocess
import numpy as np
import torch

# ----- path setup: add official repo + switch cwd so its relative imports work -----
# ROOT: 本地默认 Windows 路径；HPC 上通过 MEDNCA_ROOT 环境变量覆盖
ROOT     = os.environ.get("MEDNCA_ROOT", r"D:\YJ-Agent\project\meeting\Med-NCA")
OFFICIAL = os.path.join(ROOT, "M3D-NCA-official")
CODE_DIR = os.path.join(ROOT, "code")

sys.path.insert(0, OFFICIAL)   # official src.* imports
sys.path.insert(0, CODE_DIR)   # our dataset_isic2d
os.chdir(OFFICIAL)             # required: official code uses relative file access

# ----- official imports -----
from src.losses.LossFunctions import DiceBCELoss, DiceLoss
from src.utils.Experiment import Experiment
from src.agents.Agent_Med_NCA import Agent_Med_NCA

# ----- our custom 2D RGB dataset -----
from dataset_isic2d import ISIC2D_RGB_Dataset

# ----- GPU-rand patched backbone (math-equivalent, fixes CPU-sync stall; see REPRO_PLAN §9 #10) -----
from fast_nca import FastBackboneNCA as BackboneNCA

# --------------------------------------------------------------------------
# Hyper-parameters  (source: official train_Med_NCA.py + REPRO_PLAN §4)
# --------------------------------------------------------------------------
N_EPOCH = int(os.environ.get("R2_EPOCHS", "300"))
DEVICE  = "cuda:0" if torch.cuda.is_available() else "cpu"

# --------------------------------------------------------------------------
# §3 数字溯源: seed + git_commit（在任何随机操作之前固定）
# --------------------------------------------------------------------------
SEED = 42
np.random.seed(SEED)
torch.manual_seed(SEED)
if torch.cuda.is_available():
    torch.cuda.manual_seed_all(SEED)

try:
    _git_out = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,   # 用 ROOT 派生，本地和 HPC 都可用
        stderr=subprocess.DEVNULL,
    )
    GIT_COMMIT = _git_out.decode().strip()
except Exception:
    GIT_COMMIT = "unknown"

print(f"[R2] seed={SEED}  git_commit={GIT_COMMIT}", flush=True)

IMG_PATH   = os.path.join(ROOT, "data", "ISIC2018_Task1-2_Training_Input")
LABEL_PATH = os.path.join(ROOT, "data", "ISIC2018_Task1_Training_GroundTruth")
MODEL_PATH = os.path.join(ROOT, "checkpoints", "r2_isic")

config = [{
    # Paths
    'img_path':   IMG_PATH,
    'label_path': LABEL_PATH,
    'model_path': MODEL_PATH,
    'device':     DEVICE,
    'unlock_CPU': True,

    # Optimizer  (from official example, REPRO_PLAN §4)
    'lr':       16e-4,
    'lr_gamma': 0.9999,
    'betas':    (0.5, 0.5),

    # Training
    'save_interval':     50,
    'evaluate_interval': 25,
    'n_epoch':    N_EPOCH,
    'batch_size': 48,

    # Model
    # RISK-FIX (b): channel_n bumped 16→24.
    #   RGB input occupies ch0..ch2 (3 slots). With channel_n=16 only 13 hidden
    #   dims remain — fewer than the grayscale R1 (15 hidden). Bumping to 24
    #   gives 21 effective hidden dims (≥15), restoring sufficient capacity for
    #   RGB inputs without breaking the <100K parameter budget.
    'channel_n':       24,
    'inference_steps': 64,
    'cell_fire_rate':  0.5,
    'input_channels':  3,    # RGB — differs from R1 (grayscale=1)
    'output_channels': 1,    # binary mask
    'hidden_size':     128,

    # Two-level coarse→fine (REPRO_PLAN §4, consistent with train_Med_NCA.py)
    # RISK-FIX (a): fine patch bumped 64→128, coarse scaled 16→32 (same 1:4 ratio).
    #   ISIC original images are ~700×900px; a 64px fine patch covers only ~9%
    #   of image width, missing global lesion context needed for good segmentation.
    #   128px covers ~18% and preserves the coarse:fine 1:4 ratio from R1.
    'train_model': 1,           # index of "last" model to train (0-indexed, so 2 models)
    'input_size':  [(32, 32), (128, 128)],

    # Data
    'data_split': [0.7, 0, 0.3],   # train / val / test
}]

# --------------------------------------------------------------------------
print(f"[R2] device={DEVICE}  epochs={N_EPOCH}", flush=True)
print(f"[R2] img_path  = {IMG_PATH}", flush=True)
print(f"[R2] label_path= {LABEL_PATH}", flush=True)

# --------------------------------------------------------------------------
# Dataset
# --------------------------------------------------------------------------
dataset = ISIC2D_RGB_Dataset()

# --------------------------------------------------------------------------
# Models  (two BackboneNCA stacks: coarse + fine)
# NOTE: channel_n=24, input_channels=3
#   BackboneNCA.forward() keeps ch0..ch2 (RGB) frozen per step via:
#     x = concat(x[...,:input_channels], x2[...,input_channels:])
#   so the RGB input is always pinned; hidden state evolves in ch3..ch23.
# --------------------------------------------------------------------------
device = torch.device(DEVICE)
ca1 = BackboneNCA(
    config[0]['channel_n'],
    config[0]['cell_fire_rate'],
    device,
    hidden_size=config[0]['hidden_size'],
    input_channels=config[0]['input_channels']
).to(device)

ca2 = BackboneNCA(
    config[0]['channel_n'],
    config[0]['cell_fire_rate'],
    device,
    hidden_size=config[0]['hidden_size'],
    input_channels=config[0]['input_channels']
).to(device)

ca = [ca1, ca2]

# --------------------------------------------------------------------------
# Agent + Experiment
# --------------------------------------------------------------------------
agent = Agent_Med_NCA(ca)
exp   = Experiment(config, dataset, ca, agent)
dataset.set_experiment(exp)
exp.set_model_state('train')

# --------------------------------------------------------------------------
# R3: parameter count check (<100K)
# --------------------------------------------------------------------------
n_params = sum(p.numel() for m in ca for p in m.parameters())
r3_verdict = "PASS <100K" if n_params < 1e5 else "FAIL >=100K"
print(f"[R3] total params = {n_params:,}  ({r3_verdict})", flush=True)

# --------------------------------------------------------------------------
# Training
# --------------------------------------------------------------------------
loader = torch.utils.data.DataLoader(
    dataset,
    shuffle=True,
    batch_size=exp.get_from_config('batch_size'),
    num_workers=0,         # Windows: spawn safety — keep 0 to avoid multiprocessing issues
    pin_memory=(DEVICE != "cpu"),
)
loss_function = DiceBCELoss()

t0 = time.time()
agent.train(loader, loss_function)
elapsed = (time.time() - t0) / 60
print(f"[R2] training done in {elapsed:.1f} min", flush=True)

# --------------------------------------------------------------------------
# Evaluation: per-image Dice + bootstrap 95% CI
# (§3 口径: per-image mean, NOT batch-aggregate)
# --------------------------------------------------------------------------

def bootstrap_ci(vals, n=1000, seed=42):
    """Bootstrap 95% CI for the mean of vals."""
    rng  = np.random.default_rng(seed)
    vals = np.asarray(vals, dtype=float)
    means = [rng.choice(vals, len(vals), replace=True).mean() for _ in range(n)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)

for ens, tag in [(False, "single"), (True, "pseudo10")]:
    print(f"\n[R2-{tag}] running eval ...", flush=True)
    loss_log = agent.getAverageDiceScore(pseudo_ensemble=ens)

    # loss_log = {channel_idx: {img_id: dice_value}}
    # We report channel 0 (the segmentation output)
    ch0 = loss_log[0]
    vals = list(ch0.values())

    if len(vals) == 0:
        print(f"[R2-{tag}] WARNING: no test samples found — check data_split or file paths",
              flush=True)
        continue

    mean_dice = float(np.mean(vals))
    std_dice  = float(np.std(vals))
    lo, hi    = bootstrap_ci(vals)

    # Write per-image CSV
    out_csv = os.path.join(ROOT, "results", f"r2_isic_{tag}.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["img_id", "dice"])
        for img_id, d in sorted(ch0.items()):
            w.writerow([img_id, round(d, 6)])

    # Verdict
    threshold = 0.752   # paper ~0.772 ± 0.02
    verdict   = "PASS" if mean_dice >= threshold else "FAIL"

    # §3 数字溯源: 用 exp API 取真实训练轮数，绝不用 python 变量 N_EPOCH。
    # 原因: Experiment.reload() 若 model_path 下存在 config.dt 会整个覆盖运行时
    # config，使 n_epoch 被旧值锁死，而 python N_EPOCH 还是新值 → summary 说谎。
    # epochs_target    = 框架实际认定的目标轮数
    # epochs_trained_to= 实际跑完的步数
    summary = {
        "exp":              "R2_ISIC_2018_skin",
        "tag":              tag,
        "seed":             SEED,
        "git_commit":       GIT_COMMIT,
        "n_images":         len(vals),
        "dice_mean":        round(mean_dice, 4),
        "dice_std":         round(std_dice,  4),
        "ci95":             [round(lo, 4), round(hi, 4)],
        "threshold":        threshold,
        "verdict":          verdict,
        "epochs_target":    exp.get_max_steps(),
        "epochs_trained_to":exp.currentStep,
        "params":           n_params,
        "channel_n":        config[0]['channel_n'],
        "input_channels":   config[0]['input_channels'],
        "input_size":       str(config[0]['input_size']),
    }

    print(f"[R2-{tag}] {json.dumps(summary)}", flush=True)

    out_json = os.path.join(ROOT, "results", f"r2_isic_{tag}_summary.json")
    with open(out_json, "w") as f:
        json.dump(summary, f, indent=2)

print("\n[R2] done.", flush=True)
