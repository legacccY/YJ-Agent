"""S2.2: 3-seed robustness training — seeds 123 and 2024 for D/E/F/G.
Seed 42 already exists in the original checkpoints.

Run:
  cd D:/YJ-Agent/project
  python run_s22_seeds.py
"""

import subprocess
import sys
import time
from pathlib import Path

SEEDS = [123, 2024]

BASELINES = {
    "D": {"config": "configs/qad_stdvib.yaml",         "ckpt_base": "D:/YJ-Agent/checkpoints/stdvib"},
    "E": {"config": "configs/qad_adaptive.yaml",        "ckpt_base": "D:/YJ-Agent/checkpoints/adaptive"},
    "F": {"config": "configs/qad_efnet.yaml",           "ckpt_base": "D:/YJ-Agent/checkpoints/efnet"},
    "G": {"config": "configs/qad_finetuned_clean.yaml", "ckpt_base": "D:/YJ-Agent/checkpoints/efnet_tokft"},
}

def run(baseline, seed):
    cfg = BASELINES[baseline]
    ckpt_dir = f"{cfg['ckpt_base']}_s{seed}"
    cmd = [
        sys.executable, "train_qad.py",
        "--config", cfg["config"],
        "--seed",   str(seed),
        "--ckpt-dir", ckpt_dir,
    ]
    print(f"\n{'='*60}")
    print(f"[{baseline}] seed={seed}  ckpt -> {ckpt_dir}")
    print(f"{'='*60}")
    t0 = time.time()
    result = subprocess.run(cmd, cwd=Path(__file__).parent)
    elapsed = (time.time() - t0) / 60
    status = "OK" if result.returncode == 0 else f"FAILED (rc={result.returncode})"
    print(f"\n[{baseline}] seed={seed} -> {status} in {elapsed:.1f} min")
    return result.returncode == 0

if __name__ == "__main__":
    total = len(BASELINES) * len(SEEDS)
    done = 0
    failed = []

    for bl in ["D", "E", "F", "G"]:
        for seed in SEEDS:
            ok = run(bl, seed)
            done += 1
            if not ok:
                failed.append(f"{bl}-s{seed}")
            print(f"\nProgress: {done}/{total}  failed: {failed or 'none'}")

    print(f"\n{'='*60}")
    print(f"S2.2 seed training complete: {done-len(failed)}/{total} succeeded")
    if failed:
        print(f"Failed: {failed}")
