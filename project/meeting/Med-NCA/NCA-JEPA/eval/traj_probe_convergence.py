# -*- coding: utf-8 -*-
# ===========================================================================
# NCA-JEPA 探路第二轮 — 路线① 轨迹收敛探针
#
# 目标：对一组样本逐步跑 NCA predictor，统计每样本「收敛步数」
#       = earliest k where cos(pred_k, pred_{k-1}) < cos_thr（默认 0.01），
#       输出 NIH / VinDr 两域对比直方图 + 重叠面积，kill-shot 判别两域收敛行为异质性。
#
# 用法：
#   # smoke（随机权重，CPU，N=4，快速验管线）
#   python eval/traj_probe_convergence.py --smoke --n 4
#
#   # HPC 真跑（载 A2 ckpt，双域各 500 样本）
#   python eval/traj_probe_convergence.py \
#       --config configs/a2_scp_nca_vits_nih10k.yaml \
#       --ckpt /path/to/logs/a2_scp_nca_vits_nih10k/jepa-ep50.pth.tar \
#       --n 500 --max-steps 64 --cos-thr 0.01 \
#       --nih-root data/nih_cxr14 \
#       --vindr-root data/vindr_cxr \
#       --out results/traj_convergence \
#       --device cuda
#
# 注：A2 训练步数 trained_S=16；max-steps>16 为外推（日志中有标注）。
# ===========================================================================

import os
import sys
import argparse

import numpy as np
import pandas as pd
import yaml
import torch
import torch.nn.functional as F

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_HERE, '..')                    # NCA-JEPA 项目根
_IJEPA_ROOT = os.path.join(_ROOT, 'ijepa')
if _IJEPA_ROOT not in sys.path:
    sys.path.insert(0, _IJEPA_ROOT)

from src.helper import init_model  # noqa: E402


TRAINED_S = 16   # A2 训练用的 NCA 步数；外推区段（k>16）在输出中标注


# ---------------------------------------------------------------------------
# 模型构建 + ckpt 载入（复用 eval_anytime.py 同款逻辑，禁私改）
# ---------------------------------------------------------------------------

def build_model(config, device):
    """按 config.meta 重建 encoder+predictor，结构与训练完全一致。"""
    m = config['meta']
    enc, pred = init_model(
        device=device,
        patch_size=config['mask']['patch_size'],
        crop_size=config['data']['crop_size'],
        model_name=m['model_name'],
        pred_depth=m.get('pred_depth', 6),
        pred_emb_dim=m.get('pred_emb_dim', 384),
        predictor_type=m.get('predictor_type', 'vit'),
        nca_steps=m.get('nca_steps', 16),
        nca_hidden=m.get('nca_hidden', 128),
        fire_rate=m.get('fire_rate', 0.5),
        stabilize=m.get('stabilize', False),
        deterministic_fire=m.get('deterministic', False),
        fire_seed=int(m.get('seed', 0)),
        exit_stop_grad=m.get('exit_stop_grad', False),
    )
    return enc, pred


def load_ckpt(ckpt_path, encoder, predictor, device):
    """载 target_encoder（EMA）+ predictor，strip 'module.' 前缀。"""
    ck = torch.load(ckpt_path, map_location='cpu')
    def strip(d):
        return {k.replace('module.', ''): v for k, v in d.items()}
    enc_key = 'target_encoder' if 'target_encoder' in ck else 'encoder'
    msg_e = encoder.load_state_dict(strip(ck[enc_key]), strict=False)
    msg_p = predictor.load_state_dict(strip(ck['predictor']), strict=False)
    print(f'  载 ckpt epoch={ck.get("epoch","?")}  '
          f'enc missing={len(msg_e.missing_keys)}  '
          f'pred missing={len(msg_p.missing_keys)} unexpected={len(msg_p.unexpected_keys)}')
    return encoder, predictor


# ---------------------------------------------------------------------------
# 数据加载：NIH / VinDr，单域工厂
# ---------------------------------------------------------------------------

def _make_transform(crop_size):
    import torchvision.transforms as T
    return T.Compose([
        T.Resize((crop_size, crop_size)),
        T.ToTensor(),
        T.Lambda(lambda t: t.expand(3, -1, -1) if t.shape[0] == 1 else t),
    ])


def load_nih_samples(root, n, crop_size, image_folder='images-224/images-224',
                     subset_file=None):
    """从 NIHChestXray14 随机取 n 张，返回 tensor [n,3,H,W]。"""
    from src.datasets.nih_cxr14 import NIHChestXray14
    tf = _make_transform(crop_size)
    ds = NIHChestXray14(root=root, image_folder=image_folder,
                        transform=tf, subset_file=subset_file)
    n = min(n, len(ds))
    idx = np.random.choice(len(ds), size=n, replace=False)
    imgs = torch.stack([ds[int(i)][0] for i in idx])
    return imgs, [f'nih_{i}' for i in idx]


def load_vindr_samples(root, n, crop_size):
    """从 VinDr-CXR（PNG 扁平目录）随机取 n 张。

    目录结构：root/train/*.png（与 NIH 相同，直接扫 root/train）。
    VinDr 没有独立 Dataset class，用 PIL 直扫 train 子目录。
    """
    from PIL import Image
    tf = _make_transform(crop_size)
    train_dir = os.path.join(root, 'train')
    if not os.path.isdir(train_dir):
        raise FileNotFoundError(f'VinDr train dir 不存在: {train_dir}')
    files = [f for f in os.listdir(train_dir) if f.lower().endswith('.png')]
    if not files:
        raise FileNotFoundError(f'VinDr train dir 无 .png 文件: {train_dir}')
    n = min(n, len(files))
    chosen = np.random.choice(files, size=n, replace=False).tolist()
    imgs = []
    for fname in chosen:
        img = Image.open(os.path.join(train_dir, fname)).convert('RGB')
        imgs.append(tf(img))
    return torch.stack(imgs), [f'vindr_{f}' for f in chosen]


# ---------------------------------------------------------------------------
# 轨迹收敛计算：逐样本逐步跑，记录 conv_step
# ---------------------------------------------------------------------------

def _make_masks(encoder, B, device):
    """造一组共享 mask（context + pred），batch 共用，与 eval_anytime 同款。"""
    N = encoder.patch_embed.num_patches
    enc_D = encoder.embed_dim
    n_ctx = max(8, int(N * 0.5))
    n_pred = max(4, int(N * 0.15))
    perm = torch.randperm(N, device=device)
    ctx_idx = perm[:n_ctx].sort().values
    pred_idx = perm[n_ctx:n_ctx + n_pred].sort().values
    masks_x = [ctx_idx.unsqueeze(0).expand(B, -1).contiguous()]
    masks = [pred_idx.unsqueeze(0).expand(B, -1).contiguous()]
    return masks_x, masks, n_ctx, enc_D


def compute_convergence(encoder, predictor, imgs, max_steps, cos_thr, device,
                        batch_size=8, smoke=False):
    """逐步跑 NCA predictor，计算每样本收敛步数和最终预测 norm。

    Args:
        imgs:       [N, 3, H, W] 或 None（smoke=True 时）
        max_steps:  最大推理步数（可大于 trained_S=16，外推区段）
        cos_thr:    收敛阈值（cos(pred_k, pred_{k-1}) < thr 时视为收敛）
        batch_size: 每批推理的样本数（显存友好）
        smoke:      True 则用 random 特征跳过 encoder

    Returns:
        conv_steps  list[int|None]  每样本收敛步数（None=max_steps 内未收敛）
        final_norms list[float]     每样本最终预测 L2 norm
    """
    encoder.eval()
    predictor.eval()

    N_total = imgs.shape[0] if imgs is not None else 4

    conv_steps = []
    final_norms = []

    for start in range(0, N_total, batch_size):
        end = min(start + batch_size, N_total)
        B = end - start

        if smoke or imgs is None:
            enc_N = encoder.patch_embed.num_patches
            enc_D = encoder.embed_dim
            n_ctx = max(8, int(enc_N * 0.5))
            x_ctx = torch.randn(B, n_ctx, enc_D, device=device)
            masks_x, masks, _, _ = _make_masks(encoder, B, device)
        else:
            batch_imgs = imgs[start:end].to(device)
            with torch.no_grad():
                feats = encoder(batch_imgs)           # [B, N, enc_D]
            masks_x, masks, n_ctx, enc_D = _make_masks(encoder, B, device)
            ctx_idx = masks_x[0][0]                  # [n_ctx]
            x_ctx = torch.gather(
                feats, 1,
                ctx_idx.view(1, -1, 1).expand(B, -1, enc_D)
            )                                         # [B, n_ctx, enc_D]

        # 逐步跑，记录 pred_k 序列
        prev_pred = None
        conv_step_batch = [None] * B
        pred_at_step = {}

        with torch.no_grad():
            for k in range(1, max_steps + 1):
                pred_k = predictor(x_ctx, masks_x, masks, exit_step=k)
                # pred_k: [num_pred*B, N_pred, D]；只取第一个 pred mask 的输出（前 B 行）
                pred_k_first = pred_k[:B].reshape(B, -1)   # [B, N_pred*D]
                pred_at_step[k] = pred_k_first

                if prev_pred is not None:
                    cos_sim = F.cosine_similarity(pred_k_first, prev_pred, dim=1)  # [B]
                    for b in range(B):
                        if conv_step_batch[b] is None and cos_sim[b].item() < cos_thr:
                            conv_step_batch[b] = k

                prev_pred = pred_k_first

        # final norm：最后一步预测的 L2 norm
        final_pred = pred_at_step[max_steps]
        fnorms = final_pred.norm(dim=1).cpu().numpy().tolist()

        conv_steps.extend(conv_step_batch)
        final_norms.extend(fnorms)

    return conv_steps, final_norms


# ---------------------------------------------------------------------------
# 直方图 + 重叠面积（纯 numpy，不用 scipy，避免 OMP Error #15）
# ---------------------------------------------------------------------------

def plot_histogram(df, out_path, max_steps, cos_thr, trained_S):
    """两域收敛步数直方图 + 重叠面积。"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    nih_steps   = df.loc[df['domain'] == 'NIH',   'conv_step'].dropna().astype(int).values
    vindr_steps = df.loc[df['domain'] == 'VinDr', 'conv_step'].dropna().astype(int).values

    bins = np.arange(1, max_steps + 2) - 0.5   # 整数刻度居中

    # 空域兜底（smoke 或数据路径缺失时）
    if len(nih_steps) == 0 or len(vindr_steps) == 0:
        print('  [警告] 一侧或两侧收敛样本为空，跳过直方图')
        return float('nan')

    nih_hist,   _ = np.histogram(nih_steps,   bins=bins, density=True)
    vindr_hist, _ = np.histogram(vindr_steps, bins=bins, density=True)

    # 重叠面积 = sum min(p,q)（density 归一化后 bin_width=1）
    overlap = float(np.sum(np.minimum(nih_hist, vindr_hist)))

    fig, ax = plt.subplots(figsize=(8, 4.5))
    centers = (bins[:-1] + bins[1:]) / 2
    width = 0.4
    ax.bar(centers - width / 2, nih_hist,   width=width, alpha=0.7, label=f'NIH (n={len(nih_steps)})')
    ax.bar(centers + width / 2, vindr_hist, width=width, alpha=0.7, label=f'VinDr (n={len(vindr_steps)})')

    ax.axvline(trained_S, ls='--', c='gray', lw=1, label=f'trained S={trained_S}')
    ax.set_xlabel('Convergence step  k  (cos(pred_k, pred_{k-1}) < thr)')
    ax.set_ylabel('Density')
    ax.set_title(f'NCA Trajectory Convergence Steps\n'
                 f'cos_thr={cos_thr}  max_steps={max_steps}  '
                 f'overlap={overlap:.3f}')
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()

    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f'  直方图写出 {out_path}  重叠面积={overlap:.4f}')
    return overlap


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description='NCA-JEPA 路线① 轨迹收敛探针（traj_probe_convergence）')
    p.add_argument('--config',      default=None,
                   help='a2 config yaml（不传 + --smoke 可用 dummy 兜底）')
    p.add_argument('--ckpt',        default=None,
                   help='A2 ckpt 路径（不传则随机权重，仅 smoke/管线验证用）')
    p.add_argument('--nih-root',    default='data/nih_cxr14',
                   help='NIH 数据根目录（HPC: data/nih_cxr14/）')
    p.add_argument('--nih-subset',  default=None,
                   help='NIH subset txt（默认用 config.data.subset_file）')
    p.add_argument('--vindr-root',  default='data/vindr_cxr',
                   help='VinDr-CXR 根目录（含 train/ 子目录）')
    p.add_argument('--n',           type=int, default=500,
                   help='每域样本数（默认 500，smoke 时自动缩到 4）')
    p.add_argument('--max-steps',   type=int, default=64,
                   help=f'最大推理步数（>trained_S={TRAINED_S} 为外推）')
    p.add_argument('--cos-thr',     type=float, default=0.01,
                   help='收敛阈值 cos(pred_k, pred_{k-1}) < thr（默认 0.01）')
    p.add_argument('--batch-size',  type=int, default=8,
                   help='每批推理样本数（显存友好）')
    p.add_argument('--out',         default='results/traj_convergence',
                   help='输出目录（写 csv + png）')
    p.add_argument('--device',      default='cpu')
    p.add_argument('--smoke',       action='store_true',
                   help='随机权重 + 极小 N，仅验管线不崩，无真实意义')
    args = p.parse_args()

    if args.smoke:
        args.n = 4
        print('[smoke] N 强制=4，随机权重，仅管线验证')

    device = torch.device(args.device)

    # ------------------------------------------------------------------
    # 构建模型
    # ------------------------------------------------------------------
    if args.config is not None:
        with open(args.config, encoding='utf-8') as f:
            config = yaml.safe_load(f)
    else:
        # smoke 兜底 dummy config
        print('[smoke] 无 config，使用内置 dummy config (vit_small, nca_steps=16)')
        config = {
            'data': {'crop_size': 224, 'root_path': args.nih_root,
                     'image_folder': 'images-224/images-224',
                     'subset_file': args.nih_subset},
            'mask': {'patch_size': 16},
            'meta': {'model_name': 'vit_small', 'pred_depth': 6,
                     'pred_emb_dim': 384, 'predictor_type': 'scp_nca',
                     'nca_steps': 16, 'nca_hidden': 128, 'fire_rate': 0.5,
                     'stabilize': True, 'deterministic': True, 'seed': 0},
        }

    enc, pred = build_model(config, device)

    trained_S = config['meta'].get('nca_steps', TRAINED_S)
    if args.max_steps > trained_S:
        print(f'  [注意] max_steps={args.max_steps} > trained_S={trained_S}，'
              f'步数 {trained_S+1}~{args.max_steps} 为外推区段')

    predictor_type = config['meta'].get('predictor_type', 'vit')
    is_nca = predictor_type in ('nca', 'vanilla_nca', 'scp_nca')
    if not is_nca:
        raise ValueError(f'traj_probe_convergence 仅支持 NCA predictor，当前={predictor_type}')

    # 若 max_steps > pred.nca_steps，覆盖（纯推理，不改训练语义）
    if args.max_steps > pred.nca_steps:
        print(f'  覆盖 predictor.nca_steps: {pred.nca_steps} -> {args.max_steps}（外推）')
        pred.nca_steps = args.max_steps

    if args.ckpt:
        load_ckpt(args.ckpt, enc, pred, device)
    elif not args.smoke:
        print('  [警告] 无 --ckpt 且非 --smoke：随机初始化，结果无训练意义（仅管线验证）')

    enc.to(device)
    pred.to(device)

    crop_size = config['data']['crop_size']

    # ------------------------------------------------------------------
    # 逐域跑
    # ------------------------------------------------------------------
    records = []

    domain_configs = [
        ('NIH', load_nih_samples, {
            'root':         config['data'].get('root_path', args.nih_root),
            'n':            args.n,
            'crop_size':    crop_size,
            'image_folder': config['data'].get('image_folder', 'images-224/images-224'),
            'subset_file':  args.nih_subset or config['data'].get('subset_file'),
        }),
        ('VinDr', load_vindr_samples, {
            'root':      args.vindr_root,
            'n':         args.n,
            'crop_size': crop_size,
        }),
    ]

    for domain_name, loader_fn, loader_kwargs in domain_configs:
        print(f'\n=== {domain_name} (n={args.n}) ===')

        if args.smoke:
            imgs, sample_ids = None, [f'{domain_name.lower()}_{i}' for i in range(4)]
            print(f'  [smoke] 跳过数据加载，用随机特征')
        else:
            print(f'  加载 {domain_name} 数据…')
            try:
                imgs, sample_ids = loader_fn(**loader_kwargs)
                print(f'  加载完成 shape={tuple(imgs.shape)}')
            except FileNotFoundError as e:
                print(f'  [跳过] {domain_name} 数据路径不存在: {e}')
                continue

        conv_steps, final_norms = compute_convergence(
            enc, pred, imgs,
            max_steps=args.max_steps,
            cos_thr=args.cos_thr,
            device=device,
            batch_size=args.batch_size,
            smoke=args.smoke,
        )

        n_actual = len(conv_steps)
        n_conv = sum(1 for c in conv_steps if c is not None)
        converged_vals = [c for c in conv_steps if c is not None]
        med = float(np.median(converged_vals)) if converged_vals else float('nan')
        print(f'  收敛样本 {n_conv}/{n_actual}，中位收敛步={med:.1f}')

        for sid, cs, fn in zip(sample_ids, conv_steps, final_norms):
            records.append({
                'sample_id':    sid,
                'domain':       domain_name,
                'conv_step':    cs,
                'converged':    cs is not None,
                'final_norm':   fn,
                'max_steps':    args.max_steps,
                'cos_thr':      args.cos_thr,
                'trained_S':    trained_S,
                'extrapolated': (args.max_steps > trained_S),
            })

    if not records:
        print('[错误] 无有效记录（数据路径均失败）')
        sys.exit(1)

    # ------------------------------------------------------------------
    # 输出 csv
    # ------------------------------------------------------------------
    os.makedirs(args.out, exist_ok=True)
    csv_path = os.path.join(args.out, 'convergence.csv')
    df = pd.DataFrame(records)
    df.to_csv(csv_path, index=False)
    print(f'\n写出 csv: {csv_path}  ({len(df)} 行)')

    # ------------------------------------------------------------------
    # 直方图 + 重叠面积
    # ------------------------------------------------------------------
    png_path = os.path.join(args.out, 'convergence_hist.png')
    overlap = plot_histogram(df, png_path, args.max_steps, args.cos_thr, trained_S)
    print(f'重叠面积（两域收敛步数分布）= {overlap:.4f}')
    print('  重叠 ~1 → 两域收敛行为同质  |  重叠 <0.5 → 明显异质（可作 kill-shot 证据）')

    # 分域统计
    for domain, g in df.groupby('domain'):
        c = g['conv_step'].dropna()
        if len(c) > 0:
            print(f'  {domain}: n_converged={len(c)}/{len(g)}  '
                  f'mean={c.mean():.1f}  median={c.median():.1f}  std={c.std():.1f}')
        else:
            print(f'  {domain}: n_converged=0/{len(g)}（max_steps 内无样本收敛，考虑降 cos_thr 或增 max_steps）')


if __name__ == '__main__':
    main()
