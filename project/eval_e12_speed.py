"""E12 推理速度: 端到端 VisiScore -> VisiEnhance 每图耗时.

验收: 端到端 < 50 ms / image (GPU). 协议: @256 单图前向, warmup 后计时 N 张取均值.
复用 eval_stage2_compare 的 loaders. cwd 必须是 project/.
"""
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_stage2_compare import load_visienhance, load_visiscore, CFG

# 路径常量 (本地默认; run_e12_hpc.py 覆盖为 GPFS)
ROOT      = "D:/YJ-Agent"
VISISCORE = f"{ROOT}/checkpoints/best_visiscore.pth"
CKPT_V5   = f"{ROOT}/project/checkpoints/visienhance/stage2_planA_256_v5/best_visienhance.pth"

IMG = 256
WARMUP = 20
N = 200
THRESH_MS = 50.0


@torch.no_grad()
def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[E12] device={device}  img={IMG}  warmup={WARMUP}  N={N}")
    visiscore = load_visiscore(VISISCORE, device)
    model = load_visienhance(CFG, CKPT_V5, device)

    x = torch.rand(1, 3, IMG, IMG, device=device)

    def step():
        q = visiscore(x)
        _ = model(x, q)

    for _ in range(WARMUP):
        step()
    if device.type == "cuda":
        torch.cuda.synchronize()

    ts = []
    for _ in range(N):
        if device.type == "cuda":
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        step()
        if device.type == "cuda":
            torch.cuda.synchronize()
        ts.append((time.perf_counter() - t0) * 1000.0)

    ts = np.array(ts)
    mean_ms, p50, p95 = float(ts.mean()), float(np.percentile(ts, 50)), float(np.percentile(ts, 95))
    verdict = "PASS" if mean_ms < THRESH_MS else "FAIL"
    print(f"[E12] mean={mean_ms:.2f} ms  p50={p50:.2f}  p95={p95:.2f}  (<{THRESH_MS} ms)  {verdict}")

    Path("results").mkdir(exist_ok=True)
    import pandas as pd
    pd.DataFrame([{"mean_ms": round(mean_ms, 2), "p50_ms": round(p50, 2),
                   "p95_ms": round(p95, 2), "thresh_ms": THRESH_MS, "pass": verdict}]
                 ).to_csv("results/e12_speed.csv", index=False)
    print("saved -> results/e12_speed.csv")


if __name__ == "__main__":
    main()
