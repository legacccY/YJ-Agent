"""Orchestrate full fine-tuned ablation pipeline.

Runs in sequence after finetune_efficientnet.py completes:
  1. precompute_finetuned_features.py
  2. train_qad.py --config configs/qad_stdvib_ft.yaml
  3. train_qad.py --config configs/qad_adaptive_ft.yaml
  4. train_qad.py --config configs/qad_finetuned.yaml
  5. eval_ablation_ft.py

Usage:
    python run_ft_ablation.py
"""

import subprocess
import sys
from pathlib import Path


def run(cmd, desc):
    print(f"\n{'='*60}")
    print(f"  {desc}")
    print(f"{'='*60}")
    result = subprocess.run(
        [sys.executable] + cmd,
        cwd="D:/YJ-Agent/project",
    )
    if result.returncode != 0:
        print(f"[ERROR] {desc} failed with code {result.returncode}")
        sys.exit(1)
    print(f"[DONE] {desc}")


def main():
    # Check fine-tuned checkpoint exists
    ckpt = Path("D:/YJ-Agent/checkpoints/efficientnet_b3_isic.pth")
    if not ckpt.exists():
        print(f"ERROR: Fine-tuned checkpoint not found at {ckpt}")
        print("Run finetune_efficientnet.py first.")
        sys.exit(1)

    for d in ["stdvib_ft", "adaptive_ft", "qvib_ft"]:
        Path(f"D:/YJ-Agent/checkpoints/{d}").mkdir(parents=True, exist_ok=True)

    run(["precompute_finetuned_features.py"], "Step 1: Precompute fine-tuned features")

    configs = [
        ("configs/qad_stdvib_ft.yaml",  "Step 2: Train Std VIB (fine-tuned features)"),
        ("configs/qad_adaptive_ft.yaml", "Step 3: Train Adaptive Prior (fine-tuned features)"),
        ("configs/qad_finetuned.yaml",   "Step 4: Train Q-VIB Full (fine-tuned features)"),
    ]
    for cfg, desc in configs:
        run(["train_qad.py", "--config", cfg], desc)

    run(["eval_ablation_ft.py"], "Step 5: Full evaluation")

    print("\n" + "="*60)
    print("  ALL DONE — results/eval_report_finetuned.md")
    print("="*60)


if __name__ == "__main__":
    main()
