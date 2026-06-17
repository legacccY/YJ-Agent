"""S2.2 follow-up: produce G (Q-VIB+TokFT) seed checkpoints via finetune_tokenizer.py.

G is built by fine-tuning each F seed checkpoint with the auxiliary tokenizer loss.
This must run AFTER run_s22_seeds.py has produced efnet_s{seed}/best_qad.pth.

Bug fixed: run_s22_seeds.py / run_s22_missing.py previously called train_qad.py with
qad_finetuned_clean.yaml for G, producing ckpts byte-for-byte identical to F
(MD5 collision confirmed). The correct path is finetune_tokenizer.py(F_seed_ckpt).

Run:
  cd D:/YJ-Agent/project
  python run_g_tokft_seeds.py
"""

import hashlib
import subprocess
import sys
import time
from pathlib import Path

SEEDS = [123, 2024]

CONFIG = "configs/qad_efnet.yaml"  # same config as F (efnet_dim=1280, ImageNet features)

F_CKPT_BASE  = "D:/YJ-Agent/checkpoints/efnet"
G_CKPT_BASE  = "D:/YJ-Agent/checkpoints/efnet_tokft"


def md5(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def run_tokft(seed: int) -> bool:
    f_ckpt = Path(f"{F_CKPT_BASE}_s{seed}/best_qad.pth")
    g_ckpt = Path(f"{G_CKPT_BASE}_s{seed}/best_qad.pth")

    if not f_ckpt.exists():
        print(f"[G-s{seed}] ERROR: F seed ckpt not found: {f_ckpt}")
        print(f"  Run run_s22_seeds.py first to produce efnet_s{seed}/best_qad.pth")
        return False

    cmd = [
        sys.executable, "finetune_tokenizer.py",
        "--config",          CONFIG,
        "--checkpoint_in",   str(f_ckpt),
        "--checkpoint_out",  str(g_ckpt),
    ]

    print(f"\n{'='*60}")
    print(f"[G] seed={seed}")
    print(f"  F ckpt (input):  {f_ckpt}")
    print(f"  G ckpt (output): {g_ckpt}")
    print(f"{'='*60}")

    t0 = time.time()
    result = subprocess.run(cmd, cwd=Path(__file__).parent)
    elapsed = (time.time() - t0) / 60
    status = "OK" if result.returncode == 0 else f"FAILED (rc={result.returncode})"
    print(f"\n[G] seed={seed} -> {status} in {elapsed:.1f} min")

    if result.returncode == 0 and g_ckpt.exists() and f_ckpt.exists():
        # Sanity: G ckpt must differ from F ckpt (they should diverge after fine-tuning)
        hf = md5(f_ckpt)
        hg = md5(g_ckpt)
        if hf == hg:
            print(f"  [WARN] G ckpt MD5 == F ckpt MD5 ({hg[:12]}). Fine-tuning may have no effect.")
        else:
            print(f"  [OK] G ckpt differs from F (G={hg[:12]}, F={hf[:12]})")

    return result.returncode == 0


if __name__ == "__main__":
    total = len(SEEDS)
    done = 0
    failed = []

    for seed in SEEDS:
        ok = run_tokft(seed)
        done += 1
        if not ok:
            failed.append(f"G-s{seed}")
        print(f"\nProgress: {done}/{total}  failed: {failed or 'none'}")

    print(f"\n{'='*60}")
    print(f"G tokft seeds complete: {done - len(failed)}/{total} succeeded")
    if failed:
        print(f"Failed: {failed}")
        sys.exit(1)
