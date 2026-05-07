"""One-shot Q-VIB Full training with L2-norm fix, unique checkpoint dir."""
import subprocess
import sys
from pathlib import Path

ckpt_dir = Path("D:/YJ-Agent/checkpoints/qvib_ft_clean")
ckpt_dir.mkdir(parents=True, exist_ok=True)

# Use qad_finetuned.yaml but override checkpoint dir
import tempfile, shutil
from omegaconf import OmegaConf

cfg = OmegaConf.load("D:/YJ-Agent/project/configs/qad_finetuned.yaml")
cfg.output.checkpoint_dir = str(ckpt_dir)
tmp = Path("D:/YJ-Agent/project/configs/qad_finetuned_clean.yaml")
OmegaConf.save(cfg, tmp)

print(f"Checkpoint dir: {ckpt_dir}")
print(f"Config: {tmp}")

result = subprocess.run(
    [sys.executable, "train_qad.py", "--config", str(tmp)],
    cwd="D:/YJ-Agent/project",
)
if result.returncode != 0:
    print(f"[ERROR] Training failed (code {result.returncode})")
    sys.exit(1)
print("[DONE] Training complete")
