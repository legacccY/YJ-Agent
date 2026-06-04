"""Med-NCA R2 Prostate — Efficiency 四件套测量脚本
验收项 D：params / FLOPs / 推理延迟 / 峰值显存

运行方式：
    python D:/YJ-Agent/project/meeting/Med-NCA/code/measure_efficiency_r2.py

输出：ROOT/results/r2_efficiency.json
"""
import os, sys, json, time
import torch
import numpy as np

# ── 环境设置（与 run_r2_prostate.py 完全一致）──────────────────────────────
ROOT    = os.environ.get("MEDNCA_ROOT", r"D:\YJ-Agent\project\meeting\Med-NCA")
OFFICIAL = os.path.join(ROOT, "M3D-NCA-official")
sys.path.insert(0, OFFICIAL)
os.chdir(OFFICIAL)

sys.path.insert(0, os.path.join(ROOT, "code"))
from fast_nca import FastBackboneNCA as BackboneNCA

SEED = 42
torch.manual_seed(SEED)
np.random.seed(SEED)

# ── 模型超参（R2 Prostate config）─────────────────────────────────────────
CHANNEL_N      = 32
CELL_FIRE_RATE = 0.5
HIDDEN_SIZE    = 128
INPUT_CHANNELS = 1
INFERENCE_STEPS = 64
INPUT_SIZE_COARSE = (64, 64)    # stage 0
INPUT_SIZE_FINE   = (256, 256)  # stage 1

assert torch.cuda.is_available(), "需要 CUDA GPU，当前无可用 GPU"
device = torch.device("cuda:0")
device_name = torch.cuda.get_device_name(0)
print(f"[device] {device_name}", flush=True)

# ── 实例化两个 NCA（与 run_r2_prostate.py 第 88-91 行相同）──────────────────
ca1 = BackboneNCA(CHANNEL_N, CELL_FIRE_RATE, device,
                  hidden_size=HIDDEN_SIZE,
                  input_channels=INPUT_CHANNELS).to(device)
ca2 = BackboneNCA(CHANNEL_N, CELL_FIRE_RATE, device,
                  hidden_size=HIDDEN_SIZE,
                  input_channels=INPUT_CHANNELS).to(device)
ca  = [ca1, ca2]

# ════════════════════════════════════════════════════════════════════════════
# [D1] params — 复核 = 70016
# ════════════════════════════════════════════════════════════════════════════
n_params = sum(p.numel() for m in ca for p in m.parameters())
param_ok  = (n_params == 70016)
print(f"[D1] params = {n_params}  {'== 70016 OK' if param_ok else f'!= 70016 WARN'}", flush=True)

# ════════════════════════════════════════════════════════════════════════════
# helper: 完整 2-stage 推理（dummy 合成输入）
# 格式：NCA forward 的 x shape = (B, H, W, C)，C = channel_n
# ════════════════════════════════════════════════════════════════════════════
def run_two_stage(ca1, ca2, device, seed=None):
    """运行一次完整 coarse→fine 推理。dummy 输入，不加载真实数据。"""
    if seed is not None:
        torch.manual_seed(seed)

    # Stage 0 (coarse): shape (1, 64, 64, channel_n)
    H0, W0 = INPUT_SIZE_COARSE
    x_coarse = torch.randn(1, H0, W0, CHANNEL_N, device=device)

    # 只有 input_channels=1 个通道是"图像"，其余是 NCA state，全 0 初始化更贴近推理
    x_coarse[..., INPUT_CHANNELS:] = 0.0

    # Stage 0 forward
    out_coarse = ca1(x_coarse, steps=INFERENCE_STEPS, fire_rate=CELL_FIRE_RATE)

    # 上采样到 fine 分辨率（nearest × 4），与 Agent_Med_NCA.get_outputs 相同
    # out_coarse: (1, 64, 64, 32) → permute → (1, 32, 64, 64) → upsample → (1, 32, 256, 256)
    out_perm = out_coarse.permute(0, 3, 1, 2)
    up = torch.nn.functional.interpolate(out_perm, scale_factor=4, mode='nearest')
    out_up = up.permute(0, 2, 3, 1)   # (1, 256, 256, 32)

    # Stage 1 (fine): 拼接原始图像 + 上采样特征
    H1, W1 = INPUT_SIZE_FINE
    img_fine = torch.randn(1, H1, W1, INPUT_CHANNELS, device=device)
    x_fine = torch.cat([img_fine, out_up[..., INPUT_CHANNELS:]], dim=-1)  # (1,256,256,32)

    out_fine = ca2(x_fine, steps=INFERENCE_STEPS, fire_rate=CELL_FIRE_RATE)
    return out_fine


# ════════════════════════════════════════════════════════════════════════════
# [D2] 峰值显存（MB）
# ════════════════════════════════════════════════════════════════════════════
ca1.eval(); ca2.eval()
torch.cuda.reset_peak_memory_stats(device)
with torch.no_grad():
    _ = run_two_stage(ca1, ca2, device, seed=SEED)
torch.cuda.synchronize(device)

peak_bytes = torch.cuda.max_memory_allocated(device)
peak_mb    = peak_bytes / (1024 ** 2)
print(f"[D2] peak_mem = {peak_mb:.2f} MB", flush=True)

# ════════════════════════════════════════════════════════════════════════════
# [D3] 推理延迟（ms/slice）：warmup 5 + 计时 20
# ════════════════════════════════════════════════════════════════════════════
WARMUP  = 5
MEASURE = 20

with torch.no_grad():
    for _ in range(WARMUP):
        _ = run_two_stage(ca1, ca2, device, seed=SEED)
        torch.cuda.synchronize(device)

timings = []
with torch.no_grad():
    for _ in range(MEASURE):
        torch.cuda.synchronize(device)
        t0 = time.perf_counter()
        _ = run_two_stage(ca1, ca2, device, seed=SEED)
        torch.cuda.synchronize(device)
        t1 = time.perf_counter()
        timings.append((t1 - t0) * 1000.0)  # ms

latency_mean  = float(np.mean(timings))
latency_std   = float(np.std(timings))
print(f"[D3] latency = {latency_mean:.2f} ± {latency_std:.2f} ms/slice  (n={MEASURE})", flush=True)

# ════════════════════════════════════════════════════════════════════════════
# [D4] FLOPs —— 优先 fvcore，退化为理论 MACs 估算
# 测量口径：单步 BackboneNCA.forward (steps=1) × 64 步 × 2 stage
# ════════════════════════════════════════════════════════════════════════════
flops_value  = None
flops_method = None
macs_value   = None

# 方案 A：fvcore
try:
    from fvcore.nn import FlopCountAnalysis

    # 测 ca1（coarse stage），输入 (1, 64, 64, 32)
    dummy_coarse = torch.randn(1, INPUT_SIZE_COARSE[0], INPUT_SIZE_COARSE[1], CHANNEL_N, device=device)
    fca = FlopCountAnalysis(ca1, (dummy_coarse, 1, CELL_FIRE_RATE))
    fca.unsupported_ops_warnings(False)
    fca.uncalled_modules_warnings(False)
    flops_per_step_coarse = fca.total()   # FLOPs for steps=1, coarse

    # 测 ca2（fine stage），输入 (1, 256, 256, 32)
    dummy_fine = torch.randn(1, INPUT_SIZE_FINE[0], INPUT_SIZE_FINE[1], CHANNEL_N, device=device)
    fca2 = FlopCountAnalysis(ca2, (dummy_fine, 1, CELL_FIRE_RATE))
    fca2.unsupported_ops_warnings(False)
    fca2.uncalled_modules_warnings(False)
    flops_per_step_fine = fca2.total()

    total_flops = (flops_per_step_coarse + flops_per_step_fine) * INFERENCE_STEPS
    flops_value  = int(total_flops)
    flops_method = "fvcore_FlopCountAnalysis_single_step_x64x2stage"
    print(f"[D4-fvcore] coarse_step={flops_per_step_coarse:,}  fine_step={flops_per_step_fine:,}  total={total_flops:,}", flush=True)
    print(f"[D4] FLOPs (fvcore) = {flops_value/1e9:.3f} GFLOPs", flush=True)

except Exception as e:
    print(f"[D4] fvcore 不可用或报错: {e}，退化到理论 MACs 估算", flush=True)

    # 方案 B：理论 MACs 估算
    # BackboneNCA 每步主要算子：
    #   perceive:
    #     p0: Conv2d(32, 32, 3x3, pad=1, reflect) → 2 * 32 * 32 * 9 * H * W MACs
    #     p1: Conv2d(32, 32, 3x3, pad=1, reflect) → 同上
    #     cat → 3×channel_n 特征
    #   fc0: Linear(32*3, 128) 逐像素 → 2 * (32*3) * 128 * H * W MACs
    #   relu: ~0
    #   fc1: Linear(128, 32) 逐像素 → 2 * 128 * 32 * H * W MACs

    def macs_per_step(H, W, ch=32, hid=128):
        # perceive: 2 conv, each kernel 3×3, ch→ch
        c_p0 = 2 * ch * ch * 9 * H * W
        c_p1 = 2 * ch * ch * 9 * H * W
        # fc0: input = 3*ch, output = hid
        c_fc0 = 2 * (3 * ch) * hid * H * W
        # fc1: input = hid, output = ch
        c_fc1 = 2 * hid * ch * H * W
        return c_p0 + c_p1 + c_fc0 + c_fc1

    H0, W0 = INPUT_SIZE_COARSE
    H1, W1 = INPUT_SIZE_FINE

    macs_coarse = macs_per_step(H0, W0) * INFERENCE_STEPS
    macs_fine   = macs_per_step(H1, W1) * INFERENCE_STEPS
    total_macs  = macs_coarse + macs_fine

    macs_value   = int(total_macs)
    flops_method = "theoretical_MACs_2conv_2linear_per_step_x64x2stage"
    print(f"[D4-MACs] coarse={macs_coarse/1e9:.3f} G  fine={macs_fine/1e9:.3f} G  total={total_macs/1e9:.3f} GMACs", flush=True)

# ════════════════════════════════════════════════════════════════════════════
# 写 JSON
# ════════════════════════════════════════════════════════════════════════════
result = {
    "params":               n_params,
    "params_check_70016":   param_ok,
    "peak_mem_mb":          round(peak_mb, 2),
    "latency_ms_per_slice": round(latency_mean, 3),
    "latency_std_ms":       round(latency_std, 3),
    "latency_n_runs":       MEASURE,
    "flops_method":         flops_method,
    "device_name":          device_name,
    "inference_steps":      INFERENCE_STEPS,
    "channel_n":            CHANNEL_N,
    "input_size":           [list(INPUT_SIZE_COARSE), list(INPUT_SIZE_FINE)],
    "seed":                 SEED,
    "note":                 (
        "2-stage coarse(64x64,64step)+fine(256x256,64step); "
        "dummy randn input, no real data; "
        "latency measured with cuda.synchronize; "
        "peak_mem measured over one full 2-stage pass"
    ),
}
if flops_value is not None:
    result["flops"]       = flops_value
    result["flops_gflops"] = round(flops_value / 1e9, 3)
elif macs_value is not None:
    result["macs"]        = macs_value
    result["macs_gmacs"]  = round(macs_value / 1e9, 3)

out_path = os.path.join(ROOT, "results", "r2_efficiency.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

print(f"\n[DONE] 结果写入 {out_path}", flush=True)
print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
