# -*- coding: utf-8 -*-
"""
块A 预训练共享工具 —— images-seen 预算换算 / 统一 ckpt schema / state.json 心跳 / 种子。

设计契约（对齐 INTERFACE.md §2/§4 + PHASE1_A_PRIME_MATRIX §1）：
- **主控轴 = images-seen = E_eq × N**（N=NIH 112120）。4 范式严格相等 11.21M（E_eq=100），不计 crop/view。
- 各官方 repo 都按「epoch over NIH」迭代 → 1 epoch 恰好见 N 图一次 → **epochs 参数 = E_eq**。
  steps 只因 eff_bs 不同而异：steps = round(E_eq × N / eff_bs)。
- 统一 ckpt 落 `results/pretrain/<method>_s<seed>_ep<E>.pth`，E∈INTERMEDIATE_EPS（中间预算 probing）。
  内含 `model_state_dict`(ViT-B backbone) + `meta`。block B 按 meta['loader_hint'] 建模型 load_state_dict(strict=False)。
- state.json 心跳每 50-100 步写 `results/state_<run>.json`，主线监控读它不读 stdout。

⚠️ R4：本模块**不实现任何 SSL 算法**，只做预算换算 + ckpt 转格式 + 心跳。算法走官方 repo（见 recipe_*.py）。
"""
import json
import os
import time

# NIH ChestX-ray14 训练库样本数（patient-level split 全量 = 112120；预算换算分母）
# 真源：NCA-JEPA NIH 解压后 / Data_Entry_2017.csv 行数。⚠️ 若 split 实际 < 112120（去重/缺图），
#       主线在 HPC 用真实 len(dataset) 回填——steps 会随之变，meta 里记录的是「按 N 估算值」。
N_NIH = 112120

# 中间预算 checkpoint 的 eff-epoch（matrix §1：25/50/100，[200] 平台判据触发时再加）
INTERMEDIATE_EPS = [25, 50, 100]


def budget(eff_bs, e_eq=100, n=N_NIH):
    """images-seen 预算换算。返回 dict(images_seen, eff_bs, steps, epochs, e_eq, n)。
    epochs == e_eq（官方 repo 按 epoch over NIH 迭代，1 epoch 见 N 图一次）。
    steps == 总优化步数 = round(e_eq × n / eff_bs)。"""
    images_seen = e_eq * n
    steps = round(images_seen / eff_bs)
    return dict(images_seen=images_seen, eff_bs=int(eff_bs), steps=int(steps),
                epochs=int(e_eq), e_eq=int(e_eq), n=int(n))


def steps_per_epoch(eff_bs, n=N_NIH):
    """单 epoch 步数（drop_last 下 floor；官方 DataLoader drop_last=True）。"""
    return n // int(eff_bs)


# ---------------------------------------------------------------------------
# 统一 ckpt schema（INTERFACE §2）：{model_state_dict, meta}
# ---------------------------------------------------------------------------
def make_meta(method, seed, eff_bs, ep, e_eq=100, loader_hint='timm_vit_base',
              arch='vit_base_patch16_224', src_ckpt=None, stripped_prefix='',
              extra=None):
    """组装 ckpt meta。ep=本 ckpt 的 eff-epoch（25/50/100）；e_eq=全预算 E_eq。"""
    b = budget(eff_bs, e_eq=e_eq)
    # 本 ckpt 此刻已见的 images（按 ep 占 e_eq 比例）
    images_seen_at_ep = round(b['images_seen'] * ep / e_eq)
    steps_at_ep = round(b['steps'] * ep / e_eq)
    meta = dict(
        method=method, seed=int(seed), ep=int(ep), e_eq=int(e_eq),
        eff_bs=int(eff_bs), steps=int(steps_at_ep), steps_full=b['steps'],
        images_seen=int(images_seen_at_ep), images_seen_full=b['images_seen'],
        loader_hint=loader_hint, arch=arch,
        src_ckpt=str(src_ckpt) if src_ckpt is not None else None,
        stripped_prefix=stripped_prefix, n_nih=N_NIH,
    )
    if extra:
        meta.update(extra)
    return meta


def save_unified_ckpt(out_path, model_state_dict, meta):
    """落统一 ckpt（torch 惰性 import；torch.save 不算执行项目逻辑，是写盘）。"""
    import torch  # 惰性
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    torch.save({'model_state_dict': model_state_dict, 'meta': meta}, out_path)
    return out_path


def load_unified_ckpt(path, map_location='cpu'):
    """读统一 ckpt -> (model_state_dict, meta)。block B 消费入口。"""
    import torch  # 惰性
    obj = torch.load(path, map_location=map_location, weights_only=False)
    return obj['model_state_dict'], obj['meta']


def ckpt_out_path(results_dir, method, seed, ep):
    """results/pretrain/<method>_s<seed>_ep<E>.pth。"""
    d = os.path.join(results_dir, 'pretrain')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f'{method}_s{int(seed)}_ep{int(ep)}.pth')


def strip_prefix(state_dict, prefix):
    """取 state_dict 中以 prefix 开头的键并去前缀。返回 (新 dict, 命中数)。
    用于从官方 SSL ckpt 抽 backbone（如 DINO 'backbone.' / MoCo 'base_encoder.' / CheXWorld 'target_encoder.'）。"""
    out = {}
    for k, v in state_dict.items():
        if k.startswith(prefix):
            out[k[len(prefix):]] = v
    return out, len(out)


# ---------------------------------------------------------------------------
# state.json 心跳（INTERFACE §4）
# ---------------------------------------------------------------------------
def write_state(results_dir, run, *, step=None, total_steps=None, epoch=None,
                loss=None, metrics=None, status='running', method=None, seed=None):
    """每 50-100 步调用：写 results/state_<run>.json（原子写：tmp + replace）。"""
    os.makedirs(results_dir, exist_ok=True)
    path = os.path.join(results_dir, f'state_{run}.json')
    payload = dict(run=run, method=method, seed=seed, step=step, total_steps=total_steps,
                   epoch=epoch, loss=loss, metrics=metrics or {}, status=status,
                   timestamp=time.strftime('%Y-%m-%dT%H:%M:%S'), updated_unix=time.time())
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)
    return path


def read_state(results_dir, run):
    path = os.path.join(results_dir, f'state_{run}.json')
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        return json.load(f)
