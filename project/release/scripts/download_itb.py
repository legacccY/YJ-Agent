"""Download ITB v1.0 metadata and pre-computed predictions from Zenodo.

ITB v1.0 is released under CC-BY-NC-SA 4.0.
Zenodo DOI: 10.5281/zenodo.XXXXXXX  (to be assigned after acceptance)

The download includes:
  - itb_subsets.csv        : 2820 image-level rows with qbar and subset label
  - itb_predictions.csv    : Pre-computed predictions for 9 baseline methods
  - qcts_itb_predictions.csv : QCTS predictions
  - iqa_checkpoint.pth     : Trained 5-head IQA module weights

Raw images must be downloaded separately from their original sources
(ISIC 2020, FitzPatrick17k, HAM10000, PAD-UFES); see data/README.md.
"""
import argparse
import urllib.request
from pathlib import Path


ZENODO_BASE = "https://zenodo.org/record/XXXXXXX/files"
FILES = {
    "itb_subsets.csv":           f"{ZENODO_BASE}/itb_subsets.csv",
    "itb_predictions.csv":       f"{ZENODO_BASE}/itb_predictions.csv",
    "qcts_itb_predictions.csv":  f"{ZENODO_BASE}/qcts_itb_predictions.csv",
    "iqa_checkpoint.pth":        f"{ZENODO_BASE}/iqa_checkpoint.pth",
}


def download(url: str, dest: Path) -> None:
    if dest.exists():
        print(f"  Already exists: {dest.name}")
        return
    print(f"  Downloading {dest.name}...")
    urllib.request.urlretrieve(url, dest)
    print(f"  Saved to {dest}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", default="./data", help="Where to save files")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    print("Downloading ITB v1.0 metadata and checkpoints...")
    print("NOTE: Zenodo DOI will be active after paper acceptance.")
    print(f"      Files will be saved to: {data_dir.resolve()}")

    for filename, url in FILES.items():
        download(url, data_dir / filename)

    print("\nDone. See data/README.md for instructions on downloading raw images.")


if __name__ == "__main__":
    main()
