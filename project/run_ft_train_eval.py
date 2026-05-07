"""Retrain + eval with fixed beta_max (skip precompute, features already exist)."""
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
        print(f"[ERROR] {desc} failed (code {result.returncode})")
        sys.exit(1)
    print(f"[DONE] {desc}")


def main():
    for ckpt_dir in ["stdvib_ft", "adaptive_ft", "qvib_ft"]:
        Path(f"D:/YJ-Agent/checkpoints/{ckpt_dir}").mkdir(parents=True, exist_ok=True)

    configs = [
        ("configs/qad_stdvib_ft.yaml",  "Train Std VIB + FT (beta=1e-4)"),
        ("configs/qad_adaptive_ft.yaml", "Train Adaptive Prior + FT (beta=1e-4)"),
        ("configs/qad_finetuned.yaml",   "Train Q-VIB Full + FT (beta=1e-4)"),
    ]
    for cfg, desc in configs:
        run(["train_qad.py", "--config", cfg], desc)

    run(["eval_ablation_ft.py"], "Full evaluation")

    print("\n" + "="*60)
    print("  ALL DONE — results/eval_report_finetuned.md")
    print("="*60)


if __name__ == "__main__":
    main()
