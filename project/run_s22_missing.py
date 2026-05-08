"""补跑 S2.2 缺失的 seed checkpoint。"""

import subprocess, sys, time
from pathlib import Path

MISSING = [
    ("D", "configs/qad_stdvib.yaml",         "D:/YJ-Agent/checkpoints/stdvib_s2024",      2024),
    ("E", "configs/qad_adaptive.yaml",        "D:/YJ-Agent/checkpoints/adaptive_s123",     123),
    ("G", "configs/qad_finetuned_clean.yaml", "D:/YJ-Agent/checkpoints/efnet_tokft_s123",  123),
    ("G", "configs/qad_finetuned_clean.yaml", "D:/YJ-Agent/checkpoints/efnet_tokft_s2024", 2024),
]

for bl, cfg, ckpt_dir, seed in MISSING:
    print(f"\n{'='*60}\n[{bl}] seed={seed}  ->  {ckpt_dir}\n{'='*60}")
    t0 = time.time()
    r = subprocess.run([sys.executable, "train_qad.py",
                        "--config", cfg,
                        "--seed", str(seed),
                        "--ckpt-dir", ckpt_dir],
                       cwd=Path(__file__).parent)
    print(f"[{bl}] seed={seed} -> {'OK' if r.returncode==0 else 'FAILED'} in {(time.time()-t0)/60:.1f} min")
