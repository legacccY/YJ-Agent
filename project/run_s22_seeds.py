"""S2.2: 3-seed robustness training — seeds 123 and 2024 for D/E/F.
Seed 42 already exists in the original checkpoints.

NOTE: G (Q-VIB+TokFT) is NOT trained here from scratch.
G is produced by fine-tuning F via finetune_tokenizer.py.
To produce G seed variants, run run_g_tokft_seeds.py after this script.

Bug history (fixed): this script previously listed G with config=qad_finetuned_clean.yaml
and called train_qad.py, producing a ckpt byte-for-byte identical to F (MD5 collision
confirmed for efnet_tokft_s123 and efnet_tokft_s2024). G must be built on top of the
corresponding F seed ckpt via finetune_tokenizer.py — see run_g_tokft_seeds.py.

Run:
  cd D:/YJ-Agent/project
  python run_s22_seeds.py
"""

import subprocess
import sys
import time
from pathlib import Path

SEEDS = [123, 2024]

# G intentionally absent: G = finetune_tokenizer.py(F seed ckpt).  See run_g_tokft_seeds.py.
BASELINES = {
    "D": {"config": "configs/qad_stdvib.yaml",  "ckpt_base": "D:/YJ-Agent/checkpoints/stdvib"},
    "E": {"config": "configs/qad_adaptive.yaml", "ckpt_base": "D:/YJ-Agent/checkpoints/adaptive"},
    "F": {"config": "configs/qad_efnet.yaml",    "ckpt_base": "D:/YJ-Agent/checkpoints/efnet"},
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
