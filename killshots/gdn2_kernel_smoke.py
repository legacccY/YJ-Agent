"""
gdn2vessel kill-shot 关 2 — GPU kernel 烟测 v2 (带超时守门)
目标: 验证 GDN-2 (FLA gated_delta_rule) 在 4090 (sm_89) fwd/bwd 能跑通, grad 有限非 NaN.
v2 改动: 每个实现加 SIGALRM 150s 超时守门 (v1 chunk triton kernel 首调 hang 8min+ 无报错).
测序: naive(纯PyTorch零triton, plan退路) → fused_recurrent(triton) → chunk(triton, v1 hang者) 末位.

用法 (HPC GPU 节点 sbatch): python gdn2_kernel_smoke.py
判据: 任一实现 PASS (shape OK + grad 有限) → 关 2 PASS (naive 退路 PASS 即满足 plan 不妥协闸).
红线: 不改 FLA 官方实现; 全 hang/fail 则停下报用户 (铁律).
"""
import sys, signal, traceback
import torch

class Timeout(Exception): pass
def _alarm(sig, frm): raise Timeout()

def make_inputs():
    B, T, H, D = 1, 256, 8, 64
    dev = "cuda"; dtype = torch.bfloat16
    torch.manual_seed(0)
    q = torch.randn(B, T, H, D, dtype=dtype, device=dev, requires_grad=True)
    k = torch.randn(B, T, H, D, dtype=dtype, device=dev, requires_grad=True)
    v = torch.randn(B, T, H, D, dtype=dtype, device=dev, requires_grad=True)
    beta = torch.sigmoid(torch.randn(B, T, H, device=dev))
    g = torch.nn.functional.logsigmoid(torch.randn(B, T, H, device=dev))  # 衰减门 log space
    return q, k, v, beta, g

def try_impl(name, fn, secs=150):
    print(f"\n[{name}] start (timeout {secs}s)...", flush=True)
    signal.signal(signal.SIGALRM, _alarm); signal.alarm(secs)
    try:
        q, k, v, beta, g = make_inputs()
        out, _ = fn(q, k, v, beta=beta, g=g, output_final_state=True)
        out.float().sum().backward()
        signal.alarm(0)
        gn = q.grad.norm().item()
        finite = torch.isfinite(out).all().item() and torch.isfinite(q.grad).all().item()
        print(f"[{name}] out.shape={tuple(out.shape)} grad_norm={gn:.4e} finite={finite}", flush=True)
        return finite
    except Timeout:
        print(f"[{name}] HANG >{secs}s — 超时守门触发 (v1 chunk 即此症)", flush=True)
        return False
    except Exception as e:
        signal.alarm(0)
        print(f"[{name}] EXC {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        return False

def main():
    print(f"torch={torch.__version__} cuda={torch.cuda.is_available()}", flush=True)
    if not torch.cuda.is_available():
        print("NO GPU — 须 srun gpu4090. ABORT."); sys.exit(2)
    print(f"device={torch.cuda.get_device_name(0)} cap={torch.cuda.get_device_capability(0)}", flush=True)
    results = {}
    # 1) naive 纯 PyTorch 零 triton (plan 退路, 主验)
    naive = None
    for path in ("fla.ops.gated_delta_rule.naive", "fla.ops.gated_delta_rule"):
        try:
            mod = __import__(path, fromlist=["naive_chunk_gated_delta_rule"])
            naive = getattr(mod, "naive_chunk_gated_delta_rule")
            print(f"naive import OK from {path}", flush=True); break
        except Exception as e:
            print(f"naive import fail from {path}: {e}", flush=True)
    if naive: results["naive"] = try_impl("naive_chunk", naive)
    # 2) fused_recurrent (triton recurrent)
    try:
        from fla.ops.gated_delta_rule import fused_recurrent_gated_delta_rule as fr
        results["fused_recurrent"] = try_impl("fused_recurrent", fr)
    except Exception as e:
        print(f"fused_recurrent import fail: {e}", flush=True)
    # 3) chunk (triton chunk, v1 hang者) — 末位带守门确认
    try:
        from fla.ops.gated_delta_rule import chunk_gated_delta_rule as ch
        results["chunk"] = try_impl("chunk", ch)
    except Exception as e:
        print(f"chunk import fail: {e}", flush=True)

    print(f"\n=== 汇总 {results} ===", flush=True)
    if any(results.values()):
        passed = [k for k, v in results.items() if v]
        print(f"关 2 PASS via {passed}" + ("" if "chunk" in passed else " (chunk 待修, naive/fr 退路验通)"))
        sys.exit(0)
    print("关 2 FAIL — 全实现 hang/fail. 停下报用户 (铁律).")
    sys.exit(1)

if __name__ == "__main__":
    main()
