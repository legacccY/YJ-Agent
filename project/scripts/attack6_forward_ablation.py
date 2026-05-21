"""A1 (reviewer-driven): 3-way forward ablation for Std VIB.

Decompose the TS reversal: ρ(H, q̄) on full ITB pool (n=2820).
  (a) raw MC-marginalised forward    (N_MC=20, current 'D')
  (b) raw deterministic-μ forward    (T=1.0, no TS)
  (c) deterministic-μ + scalar TS    (T=T_OPT)

Scalar TS preserves rank on (b)→(c) (monotonic), so ρ(b) ≈ ρ(c).
If ρ(b) ≠ ρ(a), the MC-vs-deterministic forward swap drives the flip.
"""
from pathlib import Path
import json, sys
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
import cv2
from scipy.stats import spearmanr
from tqdm import tqdm

PROJ = Path("D:/YJ-Agent/project")
sys.path.insert(0, str(PROJ))
from models.q_vib_encoder import QVIBEncoder
from models.qad_classifier import QADClassifier
from agent.tools import extract_features

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
CKPT = "D:/YJ-Agent/checkpoints/stdvib/best_qad.pth"
TEMP_PATH = "D:/YJ-Agent/checkpoints/stdvib/temperature.json"
ITB_CSV = PROJ / "results/itb_subsets.csv"
OUT_JSON = PROJ / "results/forward_ablation_stdvib.json"
OUT_CSV = PROJ / "results/forward_ablation_stdvib.csv"

N_MC = 20


def H_binary(p):
    p = np.clip(p, 1e-7, 1 - 1e-7)
    return -(p * np.log(p) + (1 - p) * np.log(1 - p))


def main():
    df = pd.read_csv(ITB_CSV)
    print(f"ITB rows: {len(df)}")

    with open(TEMP_PATH) as f:
        T_OPT = float(json.load(f)["T"])
    print(f"T_OPT = {T_OPT:.4f}")

    ckpt = torch.load(CKPT, map_location=DEVICE, weights_only=False)
    encoder = QVIBEncoder(
        abcd_dim=4, q_dim=5, d_model=128, n_heads=4,
        latent_dim=64, efnet_dim=1280,
    ).to(DEVICE).eval()
    classifier = QADClassifier(latent_dim=64, hidden_dim=128, num_classes=2, dropout=0.2).to(DEVICE).eval()
    encoder.load_state_dict(ckpt["encoder"])
    classifier.load_state_dict(ckpt["classifier"])
    encoder.tokenizer.forward = lambda q: torch.zeros(q.shape[0], device=q.device)
    print(f"Loaded Std VIB from {CKPT}")

    torch.manual_seed(42)
    rng_seed = 42

    rows = []
    for _, r in tqdm(df.iterrows(), total=len(df)):
        img = cv2.imread(str(r["image_path"]))
        if img is None:
            continue
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        feats = extract_features(img)
        abcd_t = torch.tensor(feats.abcd, dtype=torch.float32).unsqueeze(0).to(DEVICE)
        q_t = torch.tensor(feats.q_vector, dtype=torch.float32).unsqueeze(0).to(DEVICE)
        ef_t = torch.tensor(feats.efnet_feat, dtype=torch.float32).unsqueeze(0).to(DEVICE)

        with torch.no_grad():
            mu, lsq = encoder(abcd_t, q_t, efnet_feat=ef_t)

            # (a) MC-marginalised — match run_experiments.py's mc_predict
            torch.manual_seed(rng_seed)
            probs_mc = []
            for _ in range(N_MC):
                z = encoder.reparameterize(mu, lsq)
                probs_mc.append(F.softmax(classifier(z), dim=-1))
            p_mc = torch.stack(probs_mc).mean(0).squeeze(0).cpu().numpy()

            # (b) deterministic μ, T=1
            logits = classifier(mu)
            p_det = F.softmax(logits, dim=-1).squeeze(0).cpu().numpy()

            # (c) deterministic μ + TS
            p_ts = F.softmax(logits / T_OPT, dim=-1).squeeze(0).cpu().numpy()

        rows.append({
            "image_path": r["image_path"],
            "subset": r["subset"],
            "qbar": float(r["qbar"]),
            "target": int(r["target"]),
            "p_mc": float(p_mc[1]),
            "p_det": float(p_det[1]),
            "p_ts": float(p_ts[1]),
        })

    out = pd.DataFrame(rows)
    out.to_csv(OUT_CSV, index=False)
    print(f"Saved {len(out)} rows → {OUT_CSV}")

    # ρ(H, q̄) on full pool
    results = {}
    for col, name in [("p_mc", "(a) raw MC-marginalised"),
                      ("p_det", "(b) raw deterministic-μ"),
                      ("p_ts", "(c) deterministic-μ + TS")]:
        h = H_binary(out[col].values)
        rho, p = spearmanr(h, out["qbar"].values)
        results[col] = {"name": name, "rho": float(rho), "p": float(p), "n": int(len(out))}
        print(f"  {name}: rho={rho:+.4f} p={p:.3e}")

    delta_a_b = results["p_det"]["rho"] - results["p_mc"]["rho"]
    delta_b_c = results["p_ts"]["rho"] - results["p_det"]["rho"]
    print(f"\nΔρ (a→b, MC→det)     = {delta_a_b:+.4f}")
    print(f"Δρ (b→c, det→det+TS) = {delta_b_c:+.4f}  (should be ≈ 0 by monotonicity)")

    results["delta_a_b_mc_to_det"] = float(delta_a_b)
    results["delta_b_c_det_to_ts"] = float(delta_b_c)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Summary: {OUT_JSON}")


if __name__ == "__main__":
    main()
