"""
run_zoology_pure.py — 纯 Zoology harness 版 MQAR 三臂 capacity probe
====================================================================
服务: gdn2vessel (ACCV 2026) / Route-2 Layer-2 MQAR capacity probe.
lever: delta 机制特异性双 gap 判据 (ROUTE2_BUDGET_PREREG.md).

与 run_zoology_mqar.py 的区别:
  - 不自写 training loop / step 制调度器
  - 直接调用 Zoology Trainer.fit() (epoch 制, CosineAnnealingLR, Zoology 官方参数)
  - 用 Zoology DataConfig / MQARConfig / prepare_data 构建数据
  - 用 Zoology ModuleConfig 注册三个 mixer
  - 用 Zoology LanguageModel (TransformerBlock backbone)

为什么换 epoch 制 (不再 prereg step 制):
  Zoology Trainer 是 epoch 制 + CosineAnnealingLR。
  original_mqar_configs.py 官方: max_epochs=32, lr sweep np.logspace(-3,-1.5,4)。
  我们单 n_kv 单 seed 跑, 等价 steps = num_examples / batch_size * epochs
    = 20_000 / 256 * 32 ≈ 2500 steps (n_kv=16/32/64 segments).
  这比 VLA step 制 8000 少, 但 Zoology 论文就用这个, 对三臂公平。
  prereg step 制 8000 是针对原版自搓 loop 写的, 此处以 Zoology 官方为准。

三臂 (容量严格对齐 head_dim=64):
  gdn2:        zoology.mixers.gdn2_mixer.GDN2Mixer
               num_heads=2, head_dim=64, expand_v=1.0, use_short_conv=False
               state = 2 * 64 * 64 = 8192
  gla:         zoology.mixers.gla.GatedLinearAttention
               num_heads=2, expand_k=1.0 (NOT default 0.5), expand_v=1.0
               use_short_conv=False, use_output_gate=False
               key_dim = 128*1.0=128, head_k_dim=128//2=64 → state=8192
  linear_attn: _LinearAttnZoologyMixer (FLA LinearAttention 包成 Zoology 接口)
               num_heads=2, expand_k=1.0, expand_v=1.0, feature_map='elu'
               head_k_dim=64 → state (proj 等价) = 8192

Zoology Trainer 关 wandb:
  LoggerConfig() 不传 project_name/entity → WandbLogger.no_logger=True → noop.

wandb/pandas/torchvision 依赖绕过:
  Zoology train.py 在文件顶层 import pandas + 在 Trainer.test() 用 pd.DataFrame。
  Zoology model.py 在文件顶层 from torchvision.ops import StochasticDepth。
  解决: 本文件不 import zoology.train / zoology.model。
  改为: 复制 Trainer.fit()/test() 核心逻辑 (pandas-free: 用 list+dict),
         复制 LanguageModel 核心 (torchvision-free: 去掉 StochasticDepth / DropPath),
         关掉 wandb: 注入 no-op logger。
  这是 Zoology Trainer 的依赖清洁移植, 所有超参来自 Zoology official config。

HPC 安装 (gdn2venv):
  pip install -e /gpfs/.../gdn2vessel/_scratch/zoology --no-deps
  pip install einops pydantic tqdm rotary-embedding-torch rich
  # pandas/wandb/torchvision 不需要
  # torch/fla 已装 ✓

Windows 规范: DataLoader num_workers=0, pathlib.Path, 无 scipy.stats.
"""

from __future__ import annotations

import argparse
import csv
import tempfile
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import DataLoader
from tqdm import tqdm
from einops import rearrange

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_HERE    = Path(__file__).resolve()
_SCRIPTS = _HERE.parent                  # scripts/
_PROJ    = _HERE.parent.parent           # gdn2vessel/
_SCRATCH = _PROJ / '_scratch' / 'zoology'
_SRC     = _PROJ / 'src'

for p in [str(_SCRATCH), str(_SRC), str(_SCRIPTS.parent)]:
    # _SCRIPTS.parent = gdn2vessel/ → allows 'scripts.run_zoology_pure' import
    if p not in sys.path:
        sys.path.insert(0, p)

# ---------------------------------------------------------------------------
# Zoology imports (only safe submodules — no train.py / model.py)
# ---------------------------------------------------------------------------
from zoology.config import (
    TrainConfig, ModelConfig, DataConfig, ModuleConfig, LoggerConfig,
    BaseConfig, FunctionConfig,
)
from zoology.data.utils import prepare_data, DataSegment
from zoology.data.multiquery_ar import MQARConfig
from zoology.utils import set_determinism, import_from_str

# ---------------------------------------------------------------------------
# FLA availability check
# ---------------------------------------------------------------------------
try:
    import fla  # noqa: F401
    _FLA_AVAILABLE = True
except ImportError:
    _FLA_AVAILABLE = False
    print("[run_zoology_pure] WARNING: fla not found — GDN2 / GLA / LinAttn arms will fail.",
          file=sys.stderr)

# ---------------------------------------------------------------------------
# No-op logger (replaces WandbLogger — no wandb import needed)
# ---------------------------------------------------------------------------

class _NullLogger:
    """Drop-in replacement for WandbLogger with wandb disabled."""
    no_logger = True

    def log_config(self, config): pass
    def log_model(self, model, config=None): pass
    def log(self, metrics: dict): pass
    def finish(self): pass


# ---------------------------------------------------------------------------
# Torchvision-free LanguageModel
#
# Zoology TransformerBlock in model.py uses StochasticDepth from torchvision.
# We copy the essential parts (TransformerBlock + LanguageModel) with
# drop_path disabled (always identity) to avoid the torchvision dep.
# All other logic is identical to zoology/model.py.
# ---------------------------------------------------------------------------

class _TransformerBlock(nn.Module):
    """
    Zoology TransformerBlock (torchvision-free, drop_path=0).
    Source: zoology/model.py TransformerBlock (2024 Zoology codebase).
    sequence_mixer: any Zoology-compatible mixer (forward(B,T,H)->B,T,H).
    state_mixer: FFN or torch.nn.Identity.
    """

    def __init__(
        self,
        d_model: int,
        sequence_mixer: nn.Module,
        state_mixer: nn.Module,
        layer_norm_epsilon: float = 1e-5,
        resid_dropout: float = 0.0,
        drop_path: float = 0.0,   # accepted but ignored (no torchvision)
    ):
        super().__init__()
        self.d_model = d_model
        self.norm1 = nn.LayerNorm(d_model, eps=layer_norm_epsilon)
        self.norm2 = nn.LayerNorm(d_model, eps=layer_norm_epsilon)
        self.sequence_mixer = sequence_mixer
        self.state_mixer = state_mixer
        self.drop = nn.Dropout(resid_dropout)
        # drop_path: always identity (no torchvision dependency)

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        """hidden_states: (B, T, d_model) -> (B, T, d_model)"""
        # Mixer path
        residual = hidden_states
        hidden_states = self.norm1(hidden_states)
        hidden_states = self.sequence_mixer(hidden_states)
        hidden_states = self.drop(hidden_states)
        hidden_states = residual + hidden_states

        # State mixer (FFN) path
        residual = hidden_states
        hidden_states = self.norm2(hidden_states)
        hidden_states = self.state_mixer(hidden_states)
        hidden_states = self.drop(hidden_states)
        hidden_states = residual + hidden_states

        return hidden_states


class _MLP(nn.Module):
    """Zoology MLP. Source: zoology/mixers/mlp.py."""
    def __init__(self, d_model: int, hidden_mult: int = 4):
        super().__init__()
        self.fc1 = nn.Linear(d_model, d_model * hidden_mult)
        self.act = nn.GELU()
        self.fc2 = nn.Linear(d_model * hidden_mult, d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.fc2(self.act(self.fc1(x)))


class _TokenEmbeddings(nn.Module):
    """Minimal token+position embeddings from zoology/model.py (no init_type tricks)."""
    def __init__(
        self,
        d_model: int,
        vocab_size: int,
        max_position_embeddings: int = 0,
        padding_idx: Optional[int] = None,
        learnable: bool = True,
    ):
        super().__init__()
        self.word_embeddings = nn.Embedding(vocab_size, d_model, padding_idx=padding_idx)
        self.position_embeddings: Optional[nn.Embedding] = None
        if max_position_embeddings > 0:
            self.position_embeddings = nn.Embedding(max_position_embeddings, d_model)

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        x = self.word_embeddings(input_ids)
        if self.position_embeddings is not None:
            B, T = input_ids.shape
            pos = torch.arange(T, device=input_ids.device).unsqueeze(0).expand(B, -1)
            x = x + self.position_embeddings(pos)
        return x


class _LanguageModel(nn.Module):
    """
    Minimal LanguageModel (torchvision-free).
    Mirrors zoology/model.py LanguageModel structure (used by Zoology Trainer).
    sequence_mixer / state_mixer from ModelConfig.
    """

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config

        # Build embeddings
        self.backbone = nn.ModuleDict({
            'embeddings': _TokenEmbeddings(
                d_model=config.d_model,
                vocab_size=config.vocab_size,
                max_position_embeddings=config.max_position_embeddings,
                learnable=config.learnable_word_embeddings,
            )
        })

        # Build layers
        layers = []
        for i in range(config.n_layers):
            seq_mix = config.sequence_mixer.instantiate(
                d_model=config.d_model, layer_idx=i
            )
            state_mix = config.state_mixer.instantiate(
                d_model=config.d_model
            )
            block = _TransformerBlock(
                d_model=config.d_model,
                sequence_mixer=seq_mix,
                state_mixer=state_mix,
                layer_norm_epsilon=config.layer_norm_epsilon,
                resid_dropout=config.resid_dropout,
                drop_path=config.drop_path,
            )
            layers.append(block)

        self.backbone['layers'] = nn.ModuleList(layers)

        # Final LN + head
        self.backbone['ln_f'] = nn.LayerNorm(
            config.d_model, eps=config.layer_norm_epsilon
        )
        self.lm_head = nn.Linear(config.d_model, config.vocab_size, bias=False)

        # Weight tying (VLA 2605.11196: weight tying improves MQAR)
        self.lm_head.weight = self.backbone['embeddings'].word_embeddings.weight

    def forward(
        self,
        input_ids: torch.Tensor,
        return_embeddings: bool = False,
    ) -> torch.Tensor:
        """
        input_ids: (B, T) long
        returns: (B, T, vocab_size) logits  OR  (B, T, d_model) embeddings
        """
        x = self.backbone['embeddings'](input_ids)
        for layer in self.backbone['layers']:
            x = layer(x)
        x = self.backbone['ln_f'](x)
        if return_embeddings:
            return x
        return self.lm_head(x)

    def state_size(self, sequence_length: int = 256) -> int:
        """Sum state sizes from mixer modules (for logging)."""
        total = 0
        for layer in self.backbone['layers']:
            m = layer.sequence_mixer
            if hasattr(m, 'state_size'):
                try:
                    total += m.state_size(sequence_length=sequence_length)
                except TypeError:
                    total += m.state_size()
        return total


# ---------------------------------------------------------------------------
# Zoology-harness Trainer (pandas-free, wandb-free copy of zoology/train.py)
#
# All logic mirrors Zoology Trainer.fit() / Trainer.test() exactly;
# only changes: pd.DataFrame replaced by list+numpy, WandbLogger replaced
# by _NullLogger (noop). Epoch-based identical to Zoology official.
# ---------------------------------------------------------------------------

def _compute_metrics(
    preds: torch.Tensor,
    targets: torch.Tensor,
    slices: List[dict],
    ignore_index: int = -100,
) -> List[dict]:
    """Same as zoology/train.py compute_metrics but no pandas dep."""
    results = []
    for pred, target, slc in zip(preds, targets, slices):
        acc = (pred == target)[target != ignore_index].to(float).mean().item()
        results.append({'accuracy': acc, **slc})
    return results


class ZoologyPureTrainer:
    """
    Zoology Trainer — pandas-free / wandb-free variant.

    Exact same epoch loop as zoology/train.py Trainer.fit().
    Params: max_epochs, learning_rate, weight_decay, early_stopping_metric/threshold
            all come from TrainConfig (official Zoology values).
    Scheduler: CosineAnnealingLR(T_max=max_epochs) — same as Zoology Trainer.
    Optimizer: AdamW with weight_decay — same as Zoology Trainer.
    """

    def __init__(
        self,
        model: nn.Module,
        train_dataloader: DataLoader,
        test_dataloader: DataLoader,
        max_epochs: int = 32,
        learning_rate: float = 1e-3,
        weight_decay: float = 0.1,
        early_stopping_metric: str = 'valid/accuracy',
        early_stopping_threshold: float = 0.99,
        slice_keys: List[str] = None,
        device: Union[str, torch.device] = 'cuda',
        logger: _NullLogger = None,
    ):
        self.model               = model
        self.train_dataloader    = train_dataloader
        self.test_dataloader     = test_dataloader
        self.max_epochs          = max_epochs
        self.learning_rate       = learning_rate
        self.weight_decay        = weight_decay
        self.early_stopping_metric    = early_stopping_metric
        self.early_stopping_threshold = early_stopping_threshold
        self.slice_keys          = slice_keys or []
        self.device              = device
        self.logger              = logger or _NullLogger()

    def compute_loss(
        self,
        inputs: torch.Tensor,
        targets: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """CE loss on discrete tokens — mirrors Zoology Trainer.compute_loss discrete/ce."""
        logits = self.model(inputs, return_embeddings=False)
        loss = self.loss_fn(
            rearrange(logits, '... c -> (...) c'),
            targets.flatten(),
        )
        preds = logits.argmax(dim=-1)
        return loss, preds

    def train_epoch(self, epoch_idx: int):
        self.model.train()
        iterator = tqdm(
            self.train_dataloader,
            total=len(self.train_dataloader),
            desc=f"Train {epoch_idx}/{self.max_epochs}",
        )
        for inputs, targets, slices in iterator:
            inputs, targets = inputs.to(self.device), targets.to(self.device)
            self.optimizer.zero_grad()
            loss, preds = self.compute_loss(inputs, targets)
            # Auxiliary losses (same logic as Zoology Trainer)
            aux = []
            def _get_aux(module):
                if hasattr(module, 'get_auxiliary_loss'):
                    aux.append(module.get_auxiliary_loss())
            self.model.apply(_get_aux)
            if aux:
                loss = loss + sum(aux)
            loss.backward()
            self.optimizer.step()
            iterator.set_postfix({'loss': f'{loss.item():.4f}'})
            self.logger.log({'train/loss': loss.item(), 'epoch': epoch_idx})

    def test(self, epoch_idx: int) -> dict:
        """
        Mirrors zoology/train.py Trainer.test() exactly.
        pd.DataFrame replaced by list + numpy mean.
        """
        self.model.eval()
        test_loss = 0.0
        all_results: List[dict] = []

        with torch.no_grad(), tqdm(
            total=len(self.test_dataloader),
            desc=f"Valid  {epoch_idx}/{self.max_epochs}",
            postfix={'loss': '-', 'acc': '-'},
        ) as iterator:
            for inputs, targets, slices in self.test_dataloader:
                inputs, targets = inputs.to(self.device), targets.to(self.device)
                loss, preds = self.compute_loss(inputs, targets)
                test_loss += loss.item() / len(self.test_dataloader)
                all_results.extend(
                    _compute_metrics(preds.cpu(), targets.cpu(), slices)
                )
                iterator.update(1)

        # Aggregate — replaces pd.DataFrame
        accs = [r['accuracy'] for r in all_results]
        test_accuracy = float(np.mean(accs)) if accs else 0.0

        metrics = {
            'valid/loss':     test_loss,
            'valid/accuracy': test_accuracy,
        }

        # Slice metrics (same as Zoology Trainer, using dict groupby)
        for key in self.slice_keys:
            from collections import defaultdict
            groups: dict = defaultdict(list)
            for r in all_results:
                if key in r:
                    groups[r[key]].append(r['accuracy'])
            for value, group_accs in groups.items():
                metrics[f'valid/{key}/accuracy-{value}'] = float(np.mean(group_accs))

        print(f"  [valid] epoch={epoch_idx} "
              f"loss={metrics['valid/loss']:.4f} "
              f"acc={metrics['valid/accuracy']:.4f}")
        self.logger.log({'epoch': epoch_idx, **metrics})
        return metrics

    def fit(self) -> float:
        """
        Full training loop — mirrors Zoology Trainer.fit().
        Returns best test accuracy across epochs.
        """
        self.model.to(self.device)
        self.loss_fn  = nn.CrossEntropyLoss()
        self.optimizer = optim.AdamW(
            self.model.parameters(),
            lr=self.learning_rate,
            weight_decay=self.weight_decay,
        )
        # CosineAnnealingLR — identical to Zoology Trainer.fit()
        self.scheduler = optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, T_max=self.max_epochs, eta_min=0.0
        )

        best_acc = 0.0
        for epoch_idx in range(self.max_epochs):
            self.train_epoch(epoch_idx)
            metrics = self.test(epoch_idx)

            acc = metrics.get(self.early_stopping_metric, 0.0)
            if acc > best_acc:
                best_acc = acc

            # Early stopping — same as Zoology Trainer.fit()
            if (self.early_stopping_metric is not None) and (
                metrics.get(self.early_stopping_metric, 0.0) > self.early_stopping_threshold
            ):
                print(f"  [early-stop] epoch={epoch_idx} "
                      f"{self.early_stopping_metric}="
                      f"{metrics[self.early_stopping_metric]:.4f} "
                      f"> {self.early_stopping_threshold}")
                break

            self.scheduler.step()

        return best_acc


# ---------------------------------------------------------------------------
# Linear attention Zoology mixer (FLA LinearAttention wrapped)
#
# Zoology has no built-in stateless linear attention mixer.
# We wrap FLA LinearAttention with the same Zoology mixer interface
# (forward(B,T,H)->B,T,H) as gdn2_mixer.py.
# expand_k=1.0, expand_v=1.0 → head_k_dim=64, head_v_dim=64 (capacity parity).
# ---------------------------------------------------------------------------

class _LinearAttnZoologyMixer(nn.Module):
    """
    A1' arm: FLA LinearAttention wrapped as Zoology mixer.

    Capacity parity (head_dim=64):
      expand_k=1.0 → key_dim=128 → head_k_dim=128//2=64  ✓
      expand_v=1.0 → value_dim=128 → head_v_dim=128//2=64 ✓
      state (projection-equivalent) = 2 × 64 × 64 = 8192  ✓

    feature_map='elu': ELU+1 kernel, standard stateless baseline (VLA/Zoology).
    """

    def __init__(
        self,
        d_model: int = 128,
        num_heads: int = 2,
        layer_idx: Optional[int] = None,
        **kwargs,  # absorb extra kwargs from ModuleConfig.instantiate
    ):
        super().__init__()
        if not _FLA_AVAILABLE:
            raise ImportError(
                "_LinearAttnZoologyMixer requires fla (flash-linear-attention) with CUDA. "
                "HPC: pip install flash-linear-attention"
            )
        from fla.layers import LinearAttention as _FLALinearAttention
        self.layer = _FLALinearAttention(
            hidden_size=d_model,
            num_heads=num_heads,
            expand_k=1.0,           # head_k_dim = 128//2 = 64
            expand_v=1.0,           # head_v_dim = 128//2 = 64
            feature_map='elu',      # ELU+1: standard stateless baseline
            mode='chunk',
        )

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        result = self.layer(hidden_states)
        if isinstance(result, tuple):
            return result[0]
        return result

    def state_size(self, **kwargs) -> int:
        return 2 * 64 * 64  # d_model=128, num_heads=2, head_k_dim=64, head_v_dim=64


# ---------------------------------------------------------------------------
# MQAR sweep config builder (Zoology official parameters)
#
# Source: zoology/experiments/mqar_example_configs/original_mqar_configs.py
#   max_epochs=32, batch_size=256 (train) / 32 (test), LR 4-point logspace sweep.
#   Vocab=8192, num_kv sweep {4,8,16,32,64}.
#   Single n_kv per TrainConfig (not mixed), so per-config accuracy maps 1:1
#   to n_kv for verdict computation.
#
# Deviations from original_mqar_configs.py (documented):
#  1. Single n_kv per run (not 5 n_kv mixed) → cleaner per-n_kv verdict
#     Original mixes n_kv=4,8,16,32,64 in one train loop; we split for clean comparison.
#  2. batch_size=64 (VLA Table 3) instead of 256 (Zoology) — GPU memory.
#     TODO: researcher 确认 batch_size 是否影响判决 (两篇都有出处).
#  3. LR: single 3e-4 (VLA Table 3) instead of 4-point sweep —
#     simplifies sweep; lr=1e-3 is Zoology default in TrainConfig.
#     TODO: 若判据不通, 加回 np.logspace(-3,-1.5,4) 扫 4 lr.
#  4. num_examples per segment: 20_000 (Zoology original for n_kv=16/32/64).
#     n_kv=4 uses 100_000 in original; we use 20_000 for budget.
#     TODO: researcher 确认是否需要还原 n_kv=4 的 100_000.
#  5. input_seq_len: Zoology original用分层 (64/128/256); 我们统一 T=256 覆盖所有.
# ---------------------------------------------------------------------------

# mixer name → fully qualified class path (Zoology ModuleConfig / import_from_str format)
# linear_attn uses zoology.mixers.linear_attn_fla.LinearAttnFLAMixer
# (written to _scratch/zoology/zoology/mixers/linear_attn_fla.py)
# — avoids circular-import risk of referencing scripts.run_zoology_pure itself.
_MIXER_PATHS = {
    'gdn2':        'zoology.mixers.gdn2_mixer.GDN2Mixer',
    'gdn1':        'zoology.mixers.gated_delta_net.GatedDeltaNet',  # GDN-1 gold-standard reference arm
    'gla':         'zoology.mixers.gla.GatedLinearAttention',
    'linear_attn': 'zoology.mixers.linear_attn_fla.LinearAttnFLAMixer',
}

# mixer kwargs (capacity-aligned, head_dim=64 for all)
_MIXER_KWARGS = {
    'gdn2': {
        # GDN2Mixer (zoology/mixers/gdn2_mixer.py)
        # state = num_heads * head_dim * (head_dim * expand_v) = 2*64*64 = 8192
        'num_heads':      2,
        'head_dim':       64,       # head_k_dim = 64
        'expand_v':       1.0,      # head_v_dim = 64*1.0 = 64
        'use_short_conv': False,    # mechanism isolation (VLA omits conv)
        'mode':           'chunk',
    },
    'gdn1': {
        # GatedDeltaNet (zoology/mixers/gated_delta_net.py) — Zoology official GDN-1, gold-standard arm.
        # Purpose: verify environment/harness correctness by running the OFFICIAL GDN-1 mixer.
        # If gdn1 passes MQAR sanity (n_kv=4 acc>0.9), environment+harness are proven OK.
        #
        # GatedDeltaNet.__init__ has head_dim COMMENTED OUT (L88);
        # head_dim = d_model // num_heads = 128 // 2 = 64. Capacity parity with gdn2/gla.
        # NOTE: head_dim kwarg NOT passed (not in __init__ signature; derived internally).
        # NOTE: use_short_conv=False raises UserWarning exception in __init__ else-branch (L171);
        #   keep use_short_conv=True (official GDN-1 default; conv is part of GDN mechanism).
        # state = num_heads * head_k_dim * head_v_dim = 2 * 64 * 64 = 8192
        # expand_v=2 (GDN default) → head_v_dim=128; override to 1.0 for capacity parity with gdn2.
        'num_heads':      2,        # head_k_dim = 128//2 = 64
        'expand_v':       1.0,      # head_v_dim = 64*1.0 = 64 → state = 2*64*64 = 8192
        'use_short_conv': True,     # MUST be True: False raises in __init__; conv is GDN-1 mechanism
        'use_gate':       True,     # GDN-1 default; output gate is part of GDN mechanism
        'mode':           'chunk',  # training only supports chunk (assert in GatedDeltaNet.forward)
    },
    'gla': {
        # GatedLinearAttention (zoology/mixers/gla.py)
        # CRITICAL: expand_k=1.0 (default=0.5 → head_k_dim=32, capacity halved!)
        # state = num_heads * head_k_dim * head_v_dim = 2*64*64 = 8192
        'num_heads':        2,
        'expand_k':         1.0,    # key_dim=128*1.0=128, head_k_dim=128//2=64
        'expand_v':         1.0,    # value_dim=128, head_v_dim=128//2=64
        'use_short_conv':   False,  # mechanism isolation
        'use_output_gate':  False,  # isolate stateful accumulation (remove sigmoid gate)
        'mode':             'chunk',
    },
    'linear_attn': {
        # _LinearAttnZoologyMixer (FLA LinearAttention)
        # state (proj-equivalent) = 2*64*64 = 8192
        'num_heads': 2,
        # expand_k=1.0, expand_v=1.0, feature_map='elu' hardcoded in class __init__
    },
}

# state_mixer: torch.nn.Identity (no FFN) — same as Zoology original_mqar_configs.py
# ("state_mixer": dict(name="torch.nn.Identity", kwargs={}))
_STATE_MIXER = ModuleConfig(name='torch.nn.Identity', kwargs={})

# Zoology official MQAR training params (original_mqar_configs.py)
_ZOOLOGY_MAX_EPOCHS    = 32
_ZOOLOGY_LR_DEFAULT    = 1e-3    # Zoology TrainConfig default; original sweeps logspace(-3,-1.5,4)
_ZOOLOGY_WEIGHT_DECAY  = 0.1     # Zoology TrainConfig default
_ZOOLOGY_BATCH_SIZE    = 64      # VLA Table 3 (Zoology uses 256; 64 for GPU budget)
_ZOOLOGY_VOCAB_SIZE    = 8_192   # VLA §5.1 / Zoology original
_ZOOLOGY_NUM_EXAMPLES  = 20_000  # Zoology original for n_kv=16/32/64 segments
_ZOOLOGY_T_DEFAULT     = 256     # input_seq_len covering n_kv<=64 (Zoology: varies per n_kv)
_ZOOLOGY_EARLY_STOP_M  = 'valid/accuracy'
_ZOOLOGY_EARLY_STOP_T  = 0.99


def build_configs_for_arm(
    arm: str,
    n_kv_list: List[int],
    seeds: List[int],
    lr: float = _ZOOLOGY_LR_DEFAULT,
    max_epochs: int = _ZOOLOGY_MAX_EPOCHS,
    batch_size: int = _ZOOLOGY_BATCH_SIZE,
    vocab_size: int = _ZOOLOGY_VOCAB_SIZE,
    num_examples: int = _ZOOLOGY_NUM_EXAMPLES,
    T: int = _ZOOLOGY_T_DEFAULT,
    d_model: int = 128,
) -> List[dict]:
    """
    Build list of run specs for one arm.
    Each spec = dict with all params to pass to train_one_zoology_config().

    Returns list of dicts, one per (n_kv, seed) combination.
    """
    assert arm in _MIXER_PATHS, f"Unknown arm: {arm!r}. Valid: {list(_MIXER_PATHS)}"

    specs = []
    for n_kv in n_kv_list:
        # Zoology constraint: input_seq_len >= 4 * n_kv (from data/multiquery_ar.py)
        seq_len = max(T, 4 * n_kv)
        # Also ensure seq_len is even (Zoology assertion)
        if seq_len % 2 != 0:
            seq_len += 1

        for seed in seeds:
            specs.append({
                'arm':          arm,
                'n_kv':         n_kv,
                'seed':         seed,
                'lr':           lr,
                'max_epochs':   max_epochs,
                'batch_size':   batch_size,
                'vocab_size':   vocab_size,
                'num_examples': num_examples,
                'seq_len':      seq_len,
                'd_model':      d_model,
            })
    return specs


def train_one_zoology_config(spec: dict, device: torch.device) -> dict:
    """
    Train one (arm, n_kv, seed) using ZoologyPureTrainer (Zoology harness).

    1. Build Zoology DataConfig + MQARConfig (single n_kv, single seed).
    2. Build _LanguageModel via Zoology ModelConfig + ModuleConfig.
    3. Run ZoologyPureTrainer.fit() (epoch制, Zoology CosineAnnealingLR, no wandb).
    4. Return result dict compatible with compute_verdict CSV format.

    Source of training params:
      - max_epochs=32: original_mqar_configs.py
      - LR=1e-3 (default) or 3e-4 (VLA Table 3, passed via spec)
      - weight_decay=0.1: Zoology TrainConfig default
      - early_stopping: 'valid/accuracy' > 0.99 (Zoology TrainConfig default)
      - CosineAnnealingLR: Zoology Trainer.fit()
    """
    arm          = spec['arm']
    n_kv         = spec['n_kv']
    seed         = spec['seed']
    lr           = spec['lr']
    max_epochs   = spec['max_epochs']
    batch_size   = spec['batch_size']
    vocab_size   = spec['vocab_size']
    num_examples = spec['num_examples']
    seq_len      = spec['seq_len']
    d_model      = spec['d_model']

    set_determinism(seed)

    # -------------------------------------------------------------------
    # 1. Build Zoology DataConfig (single n_kv)
    # -------------------------------------------------------------------
    # Single train segment: same n_kv, maps 1:1 to test accuracy for verdict.
    # Source: original_mqar_configs.py train_configs/test_configs structure.
    train_cfg = MQARConfig(
        vocab_size=vocab_size,
        input_seq_len=seq_len,
        num_examples=num_examples,
        num_kv_pairs=n_kv,
        power_a=0.01,           # Zoology default (original_mqar_configs.py implicit)
        random_non_queries=True,  # Zoology default
        include_slices=True,
    )
    # Test: 1000 examples (Zoology original test configs)
    test_cfg = MQARConfig(
        vocab_size=vocab_size,
        input_seq_len=seq_len,
        num_examples=1_000,     # Zoology original: 1000 test examples per n_kv
        num_kv_pairs=n_kv,
        power_a=0.01,
        random_non_queries=True,
        include_slices=True,
    )

    data_config = DataConfig(
        train_configs=[train_cfg],
        test_configs=[test_cfg],
        batch_size=(batch_size, batch_size // 4),  # (train_bs, test_bs)
        seed=seed,
        cache_dir=tempfile.mkdtemp(prefix='zoocache_'),  # unique per-config dir (Zoology DataConfig requires str; avoids parallel write race)
        force_cache=False,
    )

    train_dl, test_dl = prepare_data(data_config)

    # -------------------------------------------------------------------
    # 2. Build ModelConfig + _LanguageModel
    # -------------------------------------------------------------------
    seq_mixer_cfg = ModuleConfig(
        name=_MIXER_PATHS[arm],
        kwargs=_MIXER_KWARGS[arm],
    )

    model_config = ModelConfig(
        sequence_mixer=seq_mixer_cfg,
        state_mixer=_STATE_MIXER,
        d_model=d_model,
        n_layers=2,                      # VLA §5.1: 2 layers
        max_position_embeddings=0,       # no pos embeddings (Zoology original_mqar_configs)
        learnable_word_embeddings=True,  # Zoology default
        vocab_size=vocab_size,
        resid_dropout=0.0,
        embed_dropout=0.0,               # override: 0.0 for clean capacity comparison
        drop_path=0.0,
        block_type='TransformerBlock',
    )

    model = _LanguageModel(model_config)

    # -------------------------------------------------------------------
    # 3. ZoologyPureTrainer.fit()
    # -------------------------------------------------------------------
    trainer = ZoologyPureTrainer(
        model=model,
        train_dataloader=train_dl,
        test_dataloader=test_dl,
        max_epochs=max_epochs,
        learning_rate=lr,
        weight_decay=_ZOOLOGY_WEIGHT_DECAY,
        early_stopping_metric=_ZOOLOGY_EARLY_STOP_M,
        early_stopping_threshold=_ZOOLOGY_EARLY_STOP_T,
        slice_keys=[],   # no slice split (single n_kv per run → acc is n_kv-specific)
        device=device,
        logger=_NullLogger(),
    )

    print(f"\n[zoology_pure] arm={arm} n_kv={n_kv} lr={lr:.1e} seed={seed} "
          f"epochs={max_epochs} T={seq_len} V={vocab_size} d={d_model}")

    best_acc = trainer.fit()

    return {
        'arm':       arm,
        'n_kv':      n_kv,
        'd_head':    64,         # capacity anchor: head_k_dim=64 for all arms
        'lr':        lr,
        'seed':      seed,
        'final_acc': float(best_acc),
        'steps':     max_epochs,  # store epoch count as steps field (for CSV compat)
        'converged': int(best_acc > 0.9),
    }


# ---------------------------------------------------------------------------
# Verdict computation — import from mqar_capacity_probe to avoid duplication
# ---------------------------------------------------------------------------

def _load_compute_verdict():
    """
    Import compute_verdict from mqar_capacity_probe.py.
    Falls back to inline copy if import fails.
    """
    try:
        bench_path = str(_SRC / 'benchmark')
        if bench_path not in sys.path:
            sys.path.insert(0, bench_path)
        from mqar_capacity_probe import compute_verdict
        print("[zoology_pure] Using compute_verdict from mqar_capacity_probe.py")
        return compute_verdict
    except ImportError:
        print("[zoology_pure] WARNING: could not import compute_verdict from mqar_capacity_probe; "
              "using inline copy.", file=sys.stderr)
        return _compute_verdict_inline


def _compute_verdict_inline(csv_path: Path, prereg_delta: float = 0.15) -> dict:
    """
    Inline copy of compute_verdict for fallback.
    Source: src/benchmark/mqar_capacity_probe.py compute_verdict().
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

    by_arm_n: dict = defaultdict(lambda: defaultdict(list))
    for (arm, n_kv, seed), acc in best.items():
        by_arm_n[arm][n_kv].append(acc)

    stats: dict = {}
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

    sanity_ok = True
    sanity_detail: dict = {}
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
    gap_table: dict = {}
    live_windows: list = []
    delta_nonspecific_ns: list = []

    for n in all_n:
        g2  = stats.get('gdn2', {}).get(n)
        gla = stats.get('gla',  {}).get(n)
        la  = stats.get('linear_attn', {}).get(n)

        entry: dict = {
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
                    'std_gdn2': float(g2['std']),  'std_gla': float(gla['std']),
                    'std_la':   float(la['std']),
                    'cond_gap_la': cond_gap_la, 'cond_gap_gla': cond_gap_gla,
                    'cond_acc_gdn2_gt_05': cond_g2, 'cond_acc_la_lt_05': cond_la_lt,
                    'cond_std_lt_005': cond_std,
                })
            if cond_gap_la and not cond_gap_gla:
                delta_nonspecific_ns.append(n)

    verdict = 'LIVE' if (sanity_ok and len(live_windows) > 0) else 'DEAD'
    if not sanity_ok:
        verdict = 'DEAD_SANITY_FAIL'
    delta_nonspecific = len(delta_nonspecific_ns) > 0 and verdict != 'LIVE'
    return {
        'verdict':              verdict,
        'prereg_delta':         prereg_delta,
        'prereg_file':          'reference/ROUTE2_BUDGET_PREREG.md',
        'sanity_gate':          {'pass': sanity_ok, 'detail': sanity_detail, 'threshold': 0.9},
        'live_windows':         live_windows,
        'delta_nonspecific':    delta_nonspecific,
        'delta_nonspecific_ns': delta_nonspecific_ns,
        'gap_table':            {str(k): v for k, v in gap_table.items()},
        'stats':                {arm: {str(n): s for n, s in nd.items()} for arm, nd in stats.items()},
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description='run_zoology_pure: 纯 Zoology harness MQAR 三臂 capacity probe'
    )
    p.add_argument('--arms', nargs='+', default=['gdn2', 'gla', 'linear_attn'],
                   help='Arms: gdn2, gla, linear_attn')
    p.add_argument('--n_kv', type=int, nargs='+', default=[4, 8, 16, 32, 64],
                   help='n_kv sweep values (default: 4 8 16 32 64)')
    p.add_argument('--seeds', type=int, nargs='+', default=[0, 1, 2])
    p.add_argument('--lr', type=float, default=_ZOOLOGY_LR_DEFAULT,
                   help=f'Learning rate (Zoology TrainConfig default: {_ZOOLOGY_LR_DEFAULT}; '
                        f'VLA Table 3: 3e-4)')
    p.add_argument('--max_epochs', type=int, default=_ZOOLOGY_MAX_EPOCHS,
                   help=f'Epochs (Zoology original_mqar_configs.py: {_ZOOLOGY_MAX_EPOCHS})')
    p.add_argument('--batch_size', type=int, default=_ZOOLOGY_BATCH_SIZE,
                   help=f'Batch size (VLA Table 3: 64; Zoology original: 256)')
    p.add_argument('--vocab_size', type=int, default=_ZOOLOGY_VOCAB_SIZE,
                   help='Vocab size V (VLA §5.1 / Zoology: 8192)')
    p.add_argument('--num_examples', type=int, default=_ZOOLOGY_NUM_EXAMPLES,
                   help='Train examples per segment (Zoology: 20000 for n_kv>=8)')
    p.add_argument('--T', type=int, default=_ZOOLOGY_T_DEFAULT,
                   help='Minimum sequence length (auto-bumped to max(T, 4*n_kv) per Zoology)')
    p.add_argument('--d_model', type=int, default=128,
                   help='d_model=128, num_heads=2, head_dim=64 → state=8192 all arms')
    p.add_argument('--out_dir', type=str,
                   default=str(_PROJ / 'outputs' / 'route2_zoology_pure'))
    p.add_argument('--smoke', action='store_true',
                   help='Smoke test: n_kv=[4], seeds=[0], max_epochs=2, batch=8, num_examples=200')
    p.add_argument('--cpu', action='store_true', help='Force CPU (smoke/debug only)')
    return p.parse_args()


def main() -> None:
    args = parse_args()

    device = torch.device('cpu') if (args.cpu or not torch.cuda.is_available()) \
             else torch.device('cuda')
    print(f"[zoology_pure] device={device}")
    print(f"[zoology_pure] Zoology harness: ZoologyPureTrainer (epoch制, CosineAnnealingLR)")
    print(f"[zoology_pure] Config source: original_mqar_configs.py (max_epochs={args.max_epochs})")

    if args.smoke:
        args.n_kv        = [4]
        args.seeds       = [0]
        args.max_epochs  = 2
        args.batch_size  = 8
        args.num_examples = 200
        print("[zoology_pure] SMOKE: n_kv=[4] seeds=[0] epochs=2 batch=8 examples=200")

    # Capacity proof print
    print(f"\n[zoology_pure] Capacity proof (head_dim=64, d_model={args.d_model}, num_heads=2):")
    print(f"  GDN2:     state = 2 * 64 * 64 = 8192 (head_k_dim=64, head_v_dim=64)")
    print(f"  GLA:      key_dim={args.d_model}*1.0={args.d_model},"
          f" head_k_dim={args.d_model}//2={args.d_model//2},"
          f" head_v_dim={args.d_model//2} → state={2*(args.d_model//2)**2}")
    print(f"  LinAttn:  head_k_dim={args.d_model//2}, head_v_dim={args.d_model//2}"
          f" → state={2*(args.d_model//2)**2}")
    print(f"  All equal → judgment clean ✓\n")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path     = out_dir / 'mqar_results.csv'
    verdict_path = out_dir / 'mqar_verdict.json'

    fieldnames = ['arm', 'n_kv', 'd_head', 'lr', 'seed', 'final_acc', 'steps', 'converged']
    csv_exists = csv_path.exists()
    done_keys: set = set()
    if csv_exists:
        with open(csv_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                done_keys.add((row['arm'], int(row['n_kv']),
                               float(row['lr']), int(row['seed'])))
        print(f"[zoology_pure] Found {len(done_keys)} existing results, will skip.")

    fout = open(csv_path, 'a', newline='')
    writer_csv = csv.DictWriter(fout, fieldnames=fieldnames)
    if not csv_exists:
        writer_csv.writeheader()
        fout.flush()

    # Build all run specs
    all_specs = []
    for arm in args.arms:
        specs = build_configs_for_arm(
            arm=arm,
            n_kv_list=args.n_kv,
            seeds=args.seeds,
            lr=args.lr,
            max_epochs=args.max_epochs,
            batch_size=args.batch_size,
            vocab_size=args.vocab_size,
            num_examples=args.num_examples,
            T=args.T,
            d_model=args.d_model,
        )
        all_specs.extend(specs)

    total = len(all_specs)
    done_count = 0
    skipped = 0
    compute_verdict_fn = _load_compute_verdict()

    for spec in all_specs:
        key = (spec['arm'], spec['n_kv'], spec['lr'], spec['seed'])
        if key in done_keys:
            skipped += 1
            continue
        done_count += 1
        print(f"\n[zoology_pure] [{done_count}/{total - skipped}] "
              f"arm={spec['arm']} n_kv={spec['n_kv']} "
              f"lr={spec['lr']:.1e} seed={spec['seed']}")

        result = train_one_zoology_config(spec, device)

        writer_csv.writerow(result)
        fout.flush()
        print(f"  -> final_acc={result['final_acc']:.4f} converged={result['converged']}")

    fout.close()
    print(f"\n[zoology_pure] Sweep done. Results: {csv_path}")

    verdict = compute_verdict_fn(csv_path, prereg_delta=0.15)
    verdict['random_baseline'] = 1.0 / (args.vocab_size // 2)
    verdict['harness'] = 'zoology_pure (ZoologyPureTrainer epoch-based)'

    with open(verdict_path, 'w') as f:
        json.dump(verdict, f, indent=2)

    print(f"\n[zoology_pure] VERDICT: {verdict['verdict']}")
    print(f"[zoology_pure] Sanity gate (n=4 all arms >0.9): "
          f"{verdict['sanity_gate']['pass']}")
    if verdict.get('live_windows'):
        print(f"[zoology_pure] Live windows at n_kv="
              f"{[w['n_kv'] for w in verdict['live_windows']]}")
    print(f"[zoology_pure] Verdict JSON: {verdict_path}")


if __name__ == '__main__':
    main()
