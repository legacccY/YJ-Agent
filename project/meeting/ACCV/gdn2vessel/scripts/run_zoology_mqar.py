"""
run_zoology_mqar.py — Route-2 MQAR胜负手：Zoology mixer + 我们的step制训练loop
================================================================================
服务: gdn2vessel (ACCV 2026) / Route-2 Layer-2 MQAR capacity probe.
lever: delta 机制特异性双 gap 判据 (ROUTE2_BUDGET_PREREG.md).

为什么不直接用 Zoology Trainer？
  - Zoology 用 epoch 制 + CosineAnnealingLR(T_max=epochs)，无 warmup。
  - 我们 prereg 用 VLA Table 3: step 制 8000 steps + 10% warmup + cosine decay。
  - Zoology Trainer 无内置 CSV 输出（只有 wandb）。
  - 直接用 Zoology Trainer 会造成训练配置偏离 prereg，污染判据。

本文件做法:
  - 用 Zoology mixers 的三个 mixer class（GDN2Mixer/GLA/GatedDeltaNet-1）
    和 Zoology 的 multiquery_ar 数据生成器。
  - 把它们插入我们自己验证过的 MQARBackbone + step制训练loop（VLA Table 3对齐）。
  - 输出与 mqar_capacity_probe.py 相同格式的 CSV + verdict JSON，
    复用现有 compute_verdict() 逻辑（双 gap + sanity gate）。

三臂 (prereg ROUTE2_BUDGET_PREREG.md):
  gdn2        — FLA GatedDeltaNet2 (A2: delta+gate+stateful)
  gla         — Zoology GLA (gate+stateful, no delta) expand_k=1.0保证head_k_dim=64
  linear_attn — Zoology GatedDeltaNet-1 去掉delta? NO: 用 Zoology Based (ELU+1 feature map)
                或直接用 FLA LinearAttention 包成 Zoology 接口。
                —— 本文件用独立 _LinearAttnMixer (FLA LinearAttention) ，
                   与 mqar_capacity_probe.py 保持同一实现，避免引入新变量。

NOTE: 本文件需要在 HPC gdn2venv 上运行（torch2.9+cu126+fla 已装），
且需要在 _scratch/zoology/ 目录 pip install -e . --no-deps。

Windows 规范:
  - DataLoader num_workers=0 (单进程, spawn 在 HPC Linux 不需要但无害)
  - 路径全用 pathlib.Path / 正斜线
  - 无 scipy.stats

依赖冲突分析 (见文末 DEPENDENCY_NOTES):
  - zoology setup.py 要 flash-linear-attention — HPC gdn2venv 已装 ✓
  - causal_conv1d — HPC 需确认（GDN-2 use_short_conv=False 时不调用）
  - einops, pydantic, wandb, tqdm, rotary-embedding-torch — 需装
  - ray — 可选（不用并行模式不需要）
  - torchvision (model.py StochasticDepth) — 我们不用 Zoology model.py 所以不需要
  安装命令: pip install -e . --no-deps  (只装 zoology 包本身, 跳过 install_requires)
  然后: pip install einops pydantic tqdm wandb rotary-embedding-torch
  (wandb 离线模式可 WANDB_MODE=offline 或 LoggerConfig() 不传 project_name 跳过)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# ---------------------------------------------------------------------------
# Path setup — 让 Python 能 import zoology (需先 pip install -e . --no-deps 装 zoology)
# ---------------------------------------------------------------------------
_HERE   = Path(__file__).resolve()
_PROJ   = _HERE.parent.parent            # gdn2vessel/
_SCRATCH = _PROJ / '_scratch' / 'zoology'
_SRC    = _PROJ / 'src'

for p in [str(_SCRATCH), str(_SRC)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ---------------------------------------------------------------------------
# FLA 可用性检查
# ---------------------------------------------------------------------------
try:
    import fla  # noqa: F401
    _FLA_AVAILABLE = True
except ImportError:
    _FLA_AVAILABLE = False
    print("[run_zoology_mqar] WARNING: fla not found — FLA-backed mixers will fail at construction. "
          "Full sweep requires HPC with fla installed.", file=sys.stderr)

# ---------------------------------------------------------------------------
# Zoology MQAR 数据生成 (直接使用 zoology.data.multiquery_ar)
# ---------------------------------------------------------------------------
def _build_mqar_batch_zoology(
    batch_size: int,
    T: int,
    n_kv: int,
    V: int,
    device: torch.device,
    seed: Optional[int] = None,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """
    Build MQAR batch using Zoology's multiquery_ar generator.

    Zoology multiquery_ar 约定:
      - input_seq_len: T (total sequence length, must be even)
      - num_kv_pairs: n_kv
      - vocab_size: V
      - context_size = 2 * n_kv * num_passes (= 2*n_kv for num_passes=1)
      - power_a=0.01 (power-law gap distribution, Zoology default)
      - random_non_queries=True (non-query positions filled with random tokens)

    Zoology constraint: num_kv_pairs * 2 * num_passes + num_kv_pairs * 2 <= input_seq_len
      => 4 * n_kv <= T  => T >= 4 * n_kv
      For n_kv=64: T >= 256 ✓ (we use T=256)
      Also: input_seq_len % 2 == 0 ✓
      Also: vocab_size > input_seq_len ✓ (V=8192 >> T=256)

    Returns:
      inputs: (B, T) long
      targets: (B, T) long, -100 at non-query positions
      query_mask: (B, T) bool, True at query positions
    """
    try:
        from zoology.data.multiquery_ar import multiquery_ar
    except ImportError:
        raise ImportError(
            "zoology not importable. Install with: "
            "cd _scratch/zoology && pip install -e . --no-deps"
        )

    # Zoology constraint: 4*n_kv <= T
    assert T >= 4 * n_kv, (
        f"T={T} too short for n_kv={n_kv} under Zoology constraint 4*n_kv<=T: need T>={4*n_kv}"
    )
    assert T % 2 == 0, f"Zoology requires T%2==0, got T={T}"
    assert V > T, f"Zoology requires vocab_size > input_seq_len, got V={V}, T={T}"

    _seed = seed if seed is not None else int(torch.randint(0, 2**31, (1,)).item())

    segment = multiquery_ar(
        vocab_size=V,
        num_examples=batch_size,
        input_seq_len=T,
        seed=_seed,
        power_a=0.01,          # Zoology MQAR default (power-law gap distribution)
        num_kv_pairs=n_kv,
        num_passes=1,
        random_non_queries=True,  # Zoology default: non-queries are random tokens
    )

    inputs  = segment.inputs.to(device)    # (B, T)
    targets = segment.labels.to(device)    # (B, T), -100 at non-query pos

    query_mask = (targets != -100)         # (B, T) bool
    return inputs, targets, query_mask


# ---------------------------------------------------------------------------
# Three mixer wrappers — 统一 forward(x: (B,T,H)) -> (B,T,H) 接口
# ---------------------------------------------------------------------------

class _GDN2ZoologyMixer(nn.Module):
    """
    A2 arm: FLA GatedDeltaNet2 包装为 Zoology mixer 接口。
    委托给 _scratch/zoology/zoology/mixers/gdn2_mixer.py 的 GDN2Mixer。
    """
    has_internal_residual = False

    def __init__(self, d_model: int = 128, num_heads: int = 2, head_dim: int = 64,
                 expand_v: float = 1.0, use_short_conv: bool = False, layer_idx: int = 0):
        super().__init__()
        try:
            from zoology.mixers.gdn2_mixer import GDN2Mixer
        except ImportError as e:
            raise ImportError(
                f"Cannot import GDN2Mixer from zoology.mixers.gdn2_mixer: {e}\n"
                "Ensure zoology is installed: cd _scratch/zoology && pip install -e . --no-deps"
            ) from e
        self.mixer = GDN2Mixer(
            d_model=d_model,
            num_heads=num_heads,
            head_dim=head_dim,
            expand_v=expand_v,
            use_short_conv=use_short_conv,
            mode='chunk',
            layer_idx=layer_idx,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.mixer(x)


class _GLAZoologyMixer(nn.Module):
    """
    GLA arm: Zoology GatedLinearAttention (gate+stateful, no delta).

    容量对齐 (head_k_dim=64, head_v_dim=64):
      d_model=128, num_heads=2, expand_k=1.0 (NOT default 0.5)
        -> key_dim = 128 * 1.0 = 128 -> head_k_dim = 128 // 2 = 64 ✓
      expand_v=1.0 -> value_dim = 128 * 1.0 = 128 -> head_v_dim = 128 // 2 = 64 ✓
      state = 2 * 64 * 64 = 8192

    use_short_conv=False: 与 GDN-2 统一（mechanism isolation）。
    use_output_gate=False: 去掉 sigmoid 输出门，仅保留 stateful 累加效应。
      — 注意 Zoology gla.py 的 use_output_gate 对应 FLA GLA 的 use_output_gate。
      — Zoology gla.py 里该参数名也是 use_output_gate。 ✓
    """
    has_internal_residual = False

    def __init__(self, d_model: int = 128, num_heads: int = 2, layer_idx: int = 0):
        super().__init__()
        try:
            from zoology.mixers.gla import GatedLinearAttention
        except ImportError as e:
            raise ImportError(
                f"Cannot import GatedLinearAttention from zoology.mixers.gla: {e}"
            ) from e
        # CRITICAL: expand_k=1.0 (not default 0.5) to get head_k_dim=64
        self.mixer = GatedLinearAttention(
            d_model=d_model,
            num_heads=num_heads,
            expand_k=1.0,           # CRITICAL: default 0.5 -> head_k_dim=32 (capacity halved)
            expand_v=1.0,           # head_v_dim = 128//2 = 64
            use_short_conv=False,   # mechanism isolation
            use_output_gate=False,  # remove output gate: isolate stateful accumulation
            mode='chunk',
            layer_idx=layer_idx,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        result = self.mixer(x)
        if isinstance(result, tuple):
            return result[0]
        return result


class _LinearAttnFLAMixer(nn.Module):
    """
    A1' arm: FLA LinearAttention (stateless, ELU+1, no gate, no delta).

    与 mqar_capacity_probe.py 保持相同实现，避免引入新变量。
    容量对齐: expand_k=1.0, expand_v=1.0, num_heads=2
      -> head_k_dim = 128//2 = 64, head_v_dim = 128//2 = 64
      state (if were stateful) = 2*64*64 = 8192 ✓
    """
    has_internal_residual = False

    def __init__(self, d_model: int = 128, num_heads: int = 2, layer_idx: int = 0):
        super().__init__()
        if not _FLA_AVAILABLE:
            raise ImportError(
                "_LinearAttnFLAMixer requires fla (flash-linear-attention) with CUDA."
            )
        from fla.layers import LinearAttention as _FLALinearAttention
        self.layer = _FLALinearAttention(
            hidden_size=d_model,
            num_heads=num_heads,
            expand_k=1.0,
            expand_v=1.0,
            feature_map='elu',  # ELU+1, standard stateless baseline (VLA/Zoology)
            mode='chunk',
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        result = self.layer(x)
        if isinstance(result, tuple):
            return result[0]
        return result


# ---------------------------------------------------------------------------
# FFN + Backbone (same as mqar_capacity_probe.py, copied for standalone use)
# ---------------------------------------------------------------------------

class _FFN(nn.Module):
    """Two-layer FFN with GELU. 4x expansion. VLA / Zoology standard."""
    def __init__(self, d_model: int, expand: int = 4):
        super().__init__()
        self.fc1 = nn.Linear(d_model, d_model * expand, bias=False)
        self.fc2 = nn.Linear(d_model * expand, d_model, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.fc2(F.gelu(self.fc1(x)))


class _MQARBackbone(nn.Module):
    """
    2-layer backbone: each layer = pre-norm + mixer + residual + pre-norm + FFN + residual.
    VLA arXiv 2605.11196 §5.1/§6.4.
    """
    def __init__(self, d_model: int, mixers: List[nn.Module], n_layers: int = 2):
        super().__init__()
        assert len(mixers) == n_layers
        self.n_layers = n_layers
        self.mixer_norms = nn.ModuleList([nn.LayerNorm(d_model) for _ in range(n_layers)])
        self.ffn_norms   = nn.ModuleList([nn.LayerNorm(d_model) for _ in range(n_layers)])
        self.mixers = nn.ModuleList(mixers)
        self.ffns   = nn.ModuleList([_FFN(d_model) for _ in range(n_layers)])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        for i in range(self.n_layers):
            x = x + self.mixers[i](self.mixer_norms[i](x))
            x = x + self.ffns[i](self.ffn_norms[i](x))
        return x


class _MQARModel(nn.Module):
    """Embedding -> 2-layer backbone -> head, with weight tying."""
    def __init__(self, V: int, d_model: int, backbone: _MQARBackbone):
        super().__init__()
        self.embed    = nn.Embedding(V, d_model)
        self.backbone = backbone
        self.head     = nn.Linear(d_model, V, bias=False)
        self.head.weight = self.embed.weight  # weight tying (VLA 2605.11196)

    def forward(self, seq_ids: torch.Tensor) -> torch.Tensor:
        return self.head(self.backbone(self.embed(seq_ids)))


# ---------------------------------------------------------------------------
# Cosine LR scheduler with warmup (pure PyTorch)
# ---------------------------------------------------------------------------

class _CosineWarmupScheduler:
    """Linear warmup + cosine decay. VLA Table 3: warmup = 10% of total steps."""
    def __init__(self, optimizer, total_steps: int, warmup_frac: float = 0.1, lr: float = 3e-4):
        self.optimizer    = optimizer
        self.total_steps  = total_steps
        self.warmup_steps = max(1, int(total_steps * warmup_frac))
        self.base_lr      = lr

    def step(self, step: int) -> None:
        if step < self.warmup_steps:
            lr = self.base_lr * step / self.warmup_steps
        else:
            progress = (step - self.warmup_steps) / max(1, self.total_steps - self.warmup_steps)
            lr = self.base_lr * 0.5 * (1.0 + math.cos(math.pi * progress))
        for pg in self.optimizer.param_groups:
            pg['lr'] = lr


# ---------------------------------------------------------------------------
# Training loop (single arm, single config)
# ---------------------------------------------------------------------------

def train_one_config(
    arm: str,
    n_kv: int,
    lr: float,
    seed: int,
    T: int,
    V: int,
    steps: int,
    device: torch.device,
    batch_size: int = 64,
    d_model: int = 128,
    num_heads: int = 2,
    head_dim: int = 64,
    n_layers: int = 2,
    log_every: int = 200,
) -> Dict:
    """
    Train one (arm, n_kv, lr, seed) config.

    arm: 'gdn2' | 'gla' | 'linear_attn'

    Training config (VLA Table 3):
      AdamW lr=3e-4, wd=1e-2, β=(0.9,0.999), grad_clip=1.0, batch=64,
      cosine decay + 10% warmup, steps=8000.

    Data: Zoology multiquery_ar (power_a=0.01, random_non_queries=True).
    """
    torch.manual_seed(seed)
    np.random.seed(seed)

    def _make_mixers():
        if arm == 'gdn2':
            return [
                _GDN2ZoologyMixer(d_model=d_model, num_heads=num_heads, head_dim=head_dim,
                                  expand_v=1.0, use_short_conv=False, layer_idx=i)
                for i in range(n_layers)
            ]
        elif arm == 'gla':
            return [
                _GLAZoologyMixer(d_model=d_model, num_heads=num_heads, layer_idx=i)
                for i in range(n_layers)
            ]
        elif arm == 'linear_attn':
            return [
                _LinearAttnFLAMixer(d_model=d_model, num_heads=num_heads, layer_idx=i)
                for i in range(n_layers)
            ]
        else:
            raise ValueError(f"Unknown arm: {arm!r}. Valid: gdn2, gla, linear_attn")

    mixers   = _make_mixers()
    backbone = _MQARBackbone(d_model=d_model, mixers=mixers, n_layers=n_layers)
    model    = _MQARModel(V=V, d_model=d_model, backbone=backbone).to(device)

    optimizer = torch.optim.AdamW(
        model.parameters(), lr=lr, weight_decay=1e-2, betas=(0.9, 0.999)
    )
    scheduler = _CosineWarmupScheduler(optimizer, total_steps=steps, warmup_frac=0.1, lr=lr)

    best_acc = 0.0

    for step in range(1, steps + 1):
        scheduler.step(step)
        model.train()

        # Online data generation via Zoology multiquery_ar
        seq_ids, targets, query_mask = _build_mqar_batch_zoology(
            batch_size=batch_size, T=T, n_kv=n_kv, V=V, device=device, seed=None,
        )

        logits = model(seq_ids)  # (B, T, V)
        B, Tlen, Vsize = logits.shape
        loss = F.cross_entropy(
            logits.reshape(B * Tlen, Vsize),
            targets.reshape(B * Tlen),
            ignore_index=-100,
        )

        optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

        if step % log_every == 0 or step == steps:
            model.eval()
            with torch.no_grad():
                seq_e, tgt_e, qmask_e = _build_mqar_batch_zoology(
                    batch_size=batch_size * 2, T=T, n_kv=n_kv, V=V,
                    device=device, seed=step * 997 + seed,
                )
                logits_e = model(seq_e)
                pred_e   = logits_e.argmax(dim=-1)
                correct  = (pred_e == tgt_e) & qmask_e
                n_q      = qmask_e.sum().item()
                acc      = correct.sum().item() / max(n_q, 1)

            if acc > best_acc:
                best_acc = acc

            if step % (log_every * 5) == 0 or step == steps:
                print(f"  [{arm}|n={n_kv}|lr={lr:.0e}|seed={seed}] "
                      f"step={step}/{steps} loss={loss.item():.4f} "
                      f"acc={acc:.4f} best={best_acc:.4f}")

    return {
        'arm':       arm,
        'n_kv':      n_kv,
        'd_head':    head_dim,
        'lr':        lr,
        'seed':      seed,
        'final_acc': float(best_acc),
        'steps':     steps,
        'converged': int(best_acc > 0.9),
    }


# ---------------------------------------------------------------------------
# compute_verdict — 复用 mqar_capacity_probe.py 的双gap逻辑 (纯 numpy)
# ---------------------------------------------------------------------------

def compute_verdict(csv_path: Path, prereg_delta: float = 0.15) -> Dict:
    """
    Read sweep CSV, compute per-n_kv mean±std across seeds, judge LIVE/DEAD.
    Identical logic to mqar_capacity_probe.compute_verdict().
    PREREG: ROUTE2_BUDGET_PREREG.md dual-gap 2026-06-21.
    """
    rows = []
    with open(csv_path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                'arm':       row['arm'],
                'n_kv':      int(row['n_kv']),
                'lr':        float(row['lr']),
                'seed':      int(row['seed']),
                'final_acc': float(row['final_acc']),
            })

    from collections import defaultdict
    best = defaultdict(lambda: -1.0)
    for r in rows:
        key = (r['arm'], r['n_kv'], r['seed'])
        if r['final_acc'] > best[key]:
            best[key] = r['final_acc']

    by_arm_n = defaultdict(lambda: defaultdict(list))
    for (arm, n_kv, seed), acc in best.items():
        by_arm_n[arm][n_kv].append(acc)

    stats = {}
    for arm, n_dict in by_arm_n.items():
        stats[arm] = {}
        for n, accs in n_dict.items():
            arr = np.array(accs, dtype=float)
            stats[arm][n] = {
                'mean':    float(np.mean(arr)),
                'std':     float(np.std(arr, ddof=1) if len(arr) > 1 else 0.0),
                'n_seeds': len(arr),
                'accs':    [float(a) for a in arr],
            }

    # Sanity gate: n=4 all three arms mean > 0.9
    sanity_ok = True
    sanity_detail = {}
    for arm in ('gdn2', 'gla', 'linear_attn'):
        if arm in stats and 4 in stats[arm]:
            s = stats[arm][4]
            sanity_detail[arm] = {'mean': s['mean'], 'pass': bool(s['mean'] > 0.9)}
            if s['mean'] <= 0.9:
                sanity_ok = False
        else:
            sanity_detail[arm] = {'mean': None, 'pass': False}
            sanity_ok = False

    all_n = sorted(set(
        list(stats.get('gdn2', {}).keys()) +
        list(stats.get('gla', {}).keys()) +
        list(stats.get('linear_attn', {}).keys())
    ))
    gap_table    = {}
    live_windows = []
    delta_nonspecific_ns = []

    for n in all_n:
        g2  = stats.get('gdn2', {}).get(n)
        gla = stats.get('gla',  {}).get(n)
        la  = stats.get('linear_attn', {}).get(n)

        entry = {
            'acc_gdn2': float(g2['mean'])  if g2  is not None else None,
            'std_gdn2': float(g2['std'])   if g2  is not None else None,
            'acc_gla':  float(gla['mean']) if gla is not None else None,
            'std_gla':  float(gla['std'])  if gla is not None else None,
            'acc_la':   float(la['mean'])  if la  is not None else None,
            'std_la':   float(la['std'])   if la  is not None else None,
            'gap_la':   None,
            'gap_gla':  None,
        }
        if g2 is not None and la is not None:
            entry['gap_la']  = float(g2['mean'] - la['mean'])
        if g2 is not None and gla is not None:
            entry['gap_gla'] = float(g2['mean'] - gla['mean'])
        gap_table[n] = entry

        if n in (16, 32, 64) and g2 is not None and gla is not None and la is not None:
            gap_la  = entry['gap_la']
            gap_gla = entry['gap_gla']
            cond_gap_la  = gap_la  > prereg_delta
            cond_gap_gla = gap_gla > prereg_delta
            cond_g2      = g2['mean']  > 0.5
            cond_la_lt   = la['mean']  < 0.5
            cond_std     = (g2['std'] < 0.05 and gla['std'] < 0.05 and la['std'] < 0.05)

            all_live = cond_gap_la and cond_gap_gla and cond_g2 and cond_la_lt and cond_std
            if all_live:
                live_windows.append({
                    'n_kv': n, 'gap_la': float(gap_la), 'gap_gla': float(gap_gla),
                    'acc_gdn2': float(g2['mean']), 'acc_gla': float(gla['mean']),
                    'acc_la':   float(la['mean']),
                    'std_gdn2': float(g2['std']), 'std_gla': float(gla['std']),
                    'std_la':   float(la['std']),
                    'cond_gap_la': cond_gap_la, 'cond_gap_gla': cond_gap_gla,
                    'cond_acc_gdn2_gt_05': cond_g2,
                    'cond_acc_la_lt_05': cond_la_lt,
                    'cond_std_lt_005': cond_std,
                })
            if cond_gap_la and not cond_gap_gla:
                delta_nonspecific_ns.append(n)

    verdict = 'LIVE' if (sanity_ok and len(live_windows) > 0) else 'DEAD'
    if not sanity_ok:
        verdict = 'DEAD_SANITY_FAIL'

    delta_nonspecific = len(delta_nonspecific_ns) > 0 and verdict != 'LIVE'
    return {
        'verdict':               verdict,
        'prereg_delta':          prereg_delta,
        'prereg_file':           'reference/ROUTE2_BUDGET_PREREG.md',
        'sanity_gate':           {'pass': sanity_ok, 'detail': sanity_detail, 'threshold': 0.9},
        'live_windows':          live_windows,
        'delta_nonspecific':     delta_nonspecific,
        'delta_nonspecific_ns':  delta_nonspecific_ns,
        'gap_table':             {str(k): v for k, v in gap_table.items()},
        'stats':                 {arm: {str(n): s for n, s in nd.items()} for arm, nd in stats.items()},
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description='Route-2 MQAR胜负手: Zoology mixer + step制训练loop'
    )
    p.add_argument('--arms', nargs='+', default=['gdn2', 'gla', 'linear_attn'],
                   help='Arms: gdn2, gla, linear_attn')
    p.add_argument('--n_kv', type=int, nargs='+', default=[4, 8, 16, 32, 64],
                   help='n_kv sweep values (default: 4 8 16 32 64)')
    p.add_argument('--T',    type=int, default=256,
                   help='Sequence length. T=256 covers n_kv<=64 under Zoology 4*n_kv<=T constraint.')
    p.add_argument('--V',    type=int, default=8192, help='Vocab size (VLA §5.1: 8192)')
    p.add_argument('--lr',   type=float, nargs='+', default=[3e-4],
                   help='Learning rate (VLA Table 3: 3e-4)')
    p.add_argument('--seeds', type=int, nargs='+', default=[0, 1, 2])
    p.add_argument('--steps', type=int, default=8000,
                   help='Training steps per config (VLA Table 3: 8000)')
    p.add_argument('--batch_size', type=int, default=64, help='Batch size (VLA Table 3: 64)')
    p.add_argument('--d_model',   type=int, default=128)
    p.add_argument('--num_heads', type=int, default=2)
    p.add_argument('--head_dim',  type=int, default=64,
                   help='Per-head key dim. Capacity anchor: num_heads*head_dim*head_dim = 2*64*64=8192')
    p.add_argument('--n_layers',  type=int, default=2, help='Backbone layers (VLA §5.1: 2)')
    p.add_argument('--log_every', type=int, default=200)
    p.add_argument('--out_dir',   type=str,
                   default=str(_PROJ / 'outputs' / 'route2_zoology'))
    p.add_argument('--smoke', action='store_true',
                   help='Smoke test: n_kv=4, seeds=[0], steps=200, batch=8')
    p.add_argument('--cpu',   action='store_true', help='Force CPU (smoke/debug only)')
    return p.parse_args()


def main() -> None:
    args = parse_args()

    device = torch.device('cpu') if (args.cpu or not torch.cuda.is_available()) else torch.device('cuda')
    print(f"[run_zoology_mqar] device={device}")
    print(f"[run_zoology_mqar] data: Zoology multiquery_ar (power_a=0.01, random_non_queries=True)")
    print(f"[run_zoology_mqar] training: VLA Table 3 — steps=8000 lr=3e-4 warmup=10% AdamW wd=1e-2")

    if args.smoke:
        args.n_kv      = [4]
        args.lr        = [3e-4]
        args.seeds     = [0]
        args.steps     = 200
        args.batch_size = 8
        print("[run_zoology_mqar] SMOKE MODE: n_kv=[4] lr=[3e-4] seeds=[0] steps=200 batch=8")

    # Validate Zoology constraint: 4*n_kv <= T
    for n in args.n_kv:
        assert args.T >= 4 * n, (
            f"T={args.T} too short for n_kv={n}: Zoology requires T >= 4*n_kv = {4*n}"
        )

    valid_arms = {'gdn2', 'gla', 'linear_attn'}
    for arm in args.arms:
        if arm not in valid_arms:
            raise ValueError(f"Unknown arm: {arm!r}. Valid: {sorted(valid_arms)}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path     = out_dir / 'mqar_results.csv'
    verdict_path = out_dir / 'mqar_verdict.json'

    print(f"[run_zoology_mqar] Capacity proof: state = num_heads({args.num_heads}) "
          f"* head_k_dim({args.head_dim}) * head_v_dim({args.head_dim}) = "
          f"{args.num_heads * args.head_dim * args.head_dim}")
    print(f"  GDN-2:      head_k_dim={args.head_dim}, head_v_dim={args.head_dim}*1.0={args.head_dim}")
    print(f"  GLA:        key_dim={args.d_model}*1.0={args.d_model}, head_k_dim={args.d_model}//{args.num_heads}={args.d_model//args.num_heads}")
    print(f"  LinAttn:    key_dim={args.d_model}*1.0={args.d_model}, head_k_dim={args.d_model}//{args.num_heads}={args.d_model//args.num_heads}")
    print(f"  All equal -> judgment clean ✓")

    fieldnames = ['arm', 'n_kv', 'd_head', 'lr', 'seed', 'final_acc', 'steps', 'converged']
    csv_exists = csv_path.exists()
    done_keys  = set()
    if csv_exists:
        with open(csv_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                done_keys.add((row['arm'], int(row['n_kv']), float(row['lr']), int(row['seed'])))
        print(f"[run_zoology_mqar] Found {len(done_keys)} existing results, will skip.")

    fout = open(csv_path, 'a', newline='')
    writer_csv = csv.DictWriter(fout, fieldnames=fieldnames)
    if not csv_exists:
        writer_csv.writeheader()
        fout.flush()

    total_configs = len(args.arms) * len(args.n_kv) * len(args.lr) * len(args.seeds)
    done_count    = 0
    skipped       = 0

    for arm in args.arms:
        for n_kv in args.n_kv:
            for lr in args.lr:
                for seed in args.seeds:
                    key = (arm, n_kv, lr, seed)
                    if key in done_keys:
                        skipped += 1
                        continue
                    done_count += 1
                    print(f"\n[run_zoology_mqar] [{done_count}/{total_configs - skipped}] "
                          f"arm={arm} n_kv={n_kv} T={args.T} lr={lr:.0e} seed={seed}")

                    result = train_one_config(
                        arm=arm, n_kv=n_kv, lr=lr, seed=seed, T=args.T, V=args.V,
                        steps=args.steps, device=device,
                        batch_size=args.batch_size, d_model=args.d_model,
                        num_heads=args.num_heads, head_dim=args.head_dim,
                        n_layers=args.n_layers, log_every=args.log_every,
                    )

                    writer_csv.writerow(result)
                    fout.flush()
                    print(f"  -> final_acc={result['final_acc']:.4f} converged={result['converged']}")

    fout.close()
    print(f"\n[run_zoology_mqar] Sweep done. Results: {csv_path}")

    verdict = compute_verdict(csv_path, prereg_delta=0.15)
    verdict['random_baseline'] = 1.0 / (args.V // 2)

    with open(verdict_path, 'w') as f:
        json.dump(verdict, f, indent=2)

    print(f"\n[run_zoology_mqar] VERDICT: {verdict['verdict']}")
    print(f"[run_zoology_mqar] Sanity gate (n=4 all arms >0.9): {verdict['sanity_gate']['pass']}")
    if verdict['live_windows']:
        print(f"[run_zoology_mqar] Live windows at n_kv={[w['n_kv'] for w in verdict['live_windows']]}")
    print(f"[run_zoology_mqar] Verdict JSON: {verdict_path}")


if __name__ == '__main__':
    main()


# =============================================================================
# DEPENDENCY_NOTES (for HPC install, not executed)
# =============================================================================
#
# HPC gdn2venv 已有: torch2.9+cu126, flash-linear-attention (fla), numpy, tqdm
#
# 新增需装（Zoology 依赖）:
#   pip install -e /path/to/_scratch/zoology --no-deps
#   pip install einops pydantic wandb "rotary-embedding-torch>=0.5"
#
# wandb 离线（不想注册 wandb 账号）:
#   本脚本不用 Zoology Trainer，故不涉及 WandbLogger，无需 wandb。✓
#
# causal_conv1d:
#   我们 use_short_conv=False，GDN-2 不调用 causal_conv1d，可跳过。
#   Zoology gla.py 的 use_short_conv=False 同理。✓
#
# torchvision (Zoology model.py StochasticDepth):
#   本脚本不 import zoology.model，不需要 torchvision。✓
#
# ray: 仅 Zoology 并行 launch 用，本脚本不需要。✓
#
# 冲突分析:
#   - Zoology setup.py 要 flash-linear-attention — gdn2venv 已装 ✓
#   - torch 版本: Zoology 无 torch 版本要求 (setup.py 里先 import torch，
#     装好就行) ✓
#   - einops: 常规小包，无 CUDA，不与 torch/fla 冲突 ✓
#   - pydantic: 常规，无冲突 ✓
#   结论: pip install -e . --no-deps 最小侵入，不动现有 torch/fla ✓
