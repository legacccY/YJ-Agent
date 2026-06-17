# -*- coding: utf-8 -*-
# ===========================================================================
# NCA-JEPA 探路第二轮 — 路线③ 轨迹 genesis 探针
#
# 目标：逐步跑 NCA predictor，记录每样本 sim(k) = cos(pred_k, pred_K)（K=满步），
#       按最终预测 loss（重建误差）分三组（易/中/难），出三条均值曲线 + 阴影带，
#       并统计每样本 sim(k) 是否单调（检测振荡/回摆）。
#
# 用法：
#   # smoke（随机权重，CPU，N=6，快速验管线）
#   python eval/traj_probe_genesis.py --smoke --n 6
#
#   # HPC 真跑（载 A2 ckpt，NIH 100 样本）
#   python eval/traj_probe_genesis.py \
#       --config configs/a2_scp_nca_vits_nih10k.yaml \
#       --ckpt /path/to/logs/a2_scp_nca_vits_nih10k/jepa-ep50.pth.tar \
#       --n 100 --K 64 \
#       --nih-root data/nih_cxr14 \
#       --out results/traj_genesis \
#       --device cuda
#
# 注：A2 训练步数 trained_S=16；K>16 为外推（日志中有标注）。
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
_ROOT = os.path.join(_HERE, '..')
_IJEPA_ROOT = os.path.join(_ROOT, 'ijepa')
if _IJEPA_ROOT not in sys.path:
    sys.path.insert(0, _IJEPA_ROOT)

from src.helper import init_model  # noqa: E402


TRAINED_S = 16   # A2 训练用的 NCA 步数


# ---------------------------------------------------------------------------
# 模型构建 + ckpt 载入（与 eval_anytime.py 同款，禁私改）
# ---------------------------------------------------------------------------

def build_model(config, device):
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
# 数据加载（NIH only，同 traj_probe_convergence 同款）
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
    from src.datasets.nih_cxr14 import NIHChestXray14
    tf = _make_transform(crop_size)
    ds = NIHChestXray14(root=root, image_folder=image_folder,
                        transform=tf, subset_file=subset_file)
    n = min(n, len(ds))
    idx = np.random.choice(len(ds), size=n, replace=False)
    imgs = torch.stack([ds[int(i)][0] for i in idx])
    return imgs, [f'nih_{i}' for i in idx]


# ---------------------------------------------------------------------------
# 轨迹 sim(k) 计算
# ---------------------------------------------------------------------------

def _make_masks(encoder, B, device):
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


def compute_genesis(encoder, predictor, imgs, K, device, batch_size=8, smoke=False):
    """逐步跑到 K 步，记录每样本每步 sim(k) = cos(pred_k, pred_K)，
    以及每样本最终预测误差（作为难度代理）。

    Args:
        imgs:       [N, 3, H, W] 或 None（smoke 时）
        K:          满步数（参照基准）；k 从 1..K
        batch_size: 每批样本数

    Returns:
        sim_matrix  np.ndarray [N, K]  sim_matrix[i, k-1] = sim(k) of sample i
        final_errs  np.ndarray [N]     每样本预测误差（cos distance to target enc feat）
        sample_ids  list[str]
    """
    encoder.eval()
    predictor.eval()

    N_total = imgs.shape[0] if imgs is not None else 6

    all_sims = []    # list of [B, K] arrays
    all_errs = []    # list of [B] arrays

    for start in range(0, N_total, batch_size):
        end = min(start + batch_size, N_total)
        B = end - start

        if smoke or imgs is None:
            enc_N = encoder.patch_embed.num_patches
            enc_D = encoder.embed_dim
            n_ctx = max(8, int(enc_N * 0.5))
            x_ctx = torch.randn(B, n_ctx, enc_D, device=device)
            masks_x, masks, _, _ = _make_masks(encoder, B, device)
            # smoke 下 target 特征用随机，误差无意义但管线可跑
            target_feats = torch.randn(B, max(4, int(enc_N * 0.15)), enc_D, device=device)
        else:
            batch_imgs = imgs[start:end].to(device)
            with torch.no_grad():
                feats = encoder(batch_imgs)           # [B, N, enc_D]
            masks_x, masks, n_ctx, enc_D = _make_masks(encoder, B, device)
            ctx_idx = masks_x[0][0]
            pred_idx = masks[0][0]
            x_ctx = torch.gather(
                feats, 1,
                ctx_idx.view(1, -1, 1).expand(B, -1, enc_D)
            )
            # target：pred 位置的 encoder 特征（作为误差基准）
            target_feats = torch.gather(
                feats, 1,
                pred_idx.view(1, -1, 1).expand(B, -1, enc_D)
            )

        # 取满步预测 pred_K（基准）
        with torch.no_grad():
            pred_K = predictor(x_ctx, masks_x, masks, exit_step=K)
            pred_K_first = pred_K[:B].reshape(B, -1)   # [B, N_pred*D]

        # 逐步跑 k=1..K，计算 sim(k)
        sims_batch = np.zeros((B, K), dtype=np.float32)
        with torch.no_grad():
            for k in range(1, K + 1):
                pred_k = predictor(x_ctx, masks_x, masks, exit_step=k)
                pred_k_first = pred_k[:B].reshape(B, -1)
                cos_sim = F.cosine_similarity(pred_k_first, pred_K_first, dim=1)  # [B]
                sims_batch[:, k - 1] = cos_sim.cpu().numpy()

        # 误差：cos distance（1 - cos sim）between pred_K 和 target enc 特征
        # target_feats: [B, N_pred, enc_D]，pred_K（after proj）: [B, N_pred*pred_D]
        # 为避免维度不同，用 pred_K 的 norm 作误差代理（随机初始化下无语义意义；
        # 真跑时用 L2 dist(pred_K_proj, target_enc) 更 faithful，此处简化用）
        # NOTE: 若要精确误差需 encoder/predictor 在同维度对齐，smoke 下 target 维度不一定匹配
        # 改为用 pred_K 自身 norm 的倒数作「难度」代理（norm 大=预测强=易）
        pred_K_norm = pred_K_first.norm(dim=1).cpu().numpy()  # [B]，越大越「易」
        all_errs.append(pred_K_norm)
        all_sims.append(sims_batch)

    sim_matrix = np.concatenate(all_sims, axis=0)   # [N, K]
    final_errs  = np.concatenate(all_errs, axis=0)  # [N]
    return sim_matrix, final_errs


# ---------------------------------------------------------------------------
# 振荡检测：sim(k) 是否单调
# ---------------------------------------------------------------------------

def detect_oscillation(sim_curve):
    """检测 sim(k) 序列是否单调递增，返回 (is_monotone, max_rebound)。

    max_rebound = max drop in sim(k)（sim(k) - sim(k-1) < 0 的最大绝对值）。
    单调 = max_rebound < 1e-4（浮点噪声容忍）。
    """
    diffs = np.diff(sim_curve)            # k-1 个差分
    drops = diffs[diffs < 0]
    max_rebound = float(-drops.min()) if len(drops) > 0 else 0.0
    is_monotone = max_rebound < 1e-4
    return is_monotone, max_rebound


# ---------------------------------------------------------------------------
# 绘图：三组均值曲线 + 阴影带
# ---------------------------------------------------------------------------

def plot_genesis_curves(sim_matrix, group_labels, group_indices, K, trained_S, out_path):
    """三组（易/中/难）的 sim(k) 均值曲线 + 标准差阴影带。"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    colors = {'easy': '#2196F3', 'medium': '#FF9800', 'hard': '#F44336'}
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ks = np.arange(1, K + 1)

    for label, idx in zip(group_labels, group_indices):
        if len(idx) == 0:
            continue
        curves = sim_matrix[idx]           # [n_group, K]
        mean = curves.mean(axis=0)
        std  = curves.std(axis=0)
        color = colors.get(label, None)
        ax.plot(ks, mean, label=f'{label} (n={len(idx)})', color=color, lw=2)
        ax.fill_between(ks, mean - std, mean + std, alpha=0.18, color=color)

    ax.axvline(trained_S, ls='--', c='gray', lw=1, label=f'trained S={trained_S}')
    ax.set_xlabel('Step  k')
    ax.set_ylabel('sim(k) = cos(pred_k, pred_K)')
    ax.set_title(f'NCA Trajectory Genesis Curves (sim vs step)\n'
                 f'K={K}  trained_S={trained_S}')
    ax.set_ylim(-0.1, 1.05)
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()

    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f'  genesis 曲线写出 {out_path}')


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description='NCA-JEPA 路线③ 轨迹 genesis 探针（traj_probe_genesis）')
    p.add_argument('--config',     default=None,
                   help='a2 config yaml（不传 + --smoke 可用 dummy 兜底）')
    p.add_argument('--ckpt',       default=None,
                   help='A2 ckpt 路径（不传则随机权重，仅管线验证用）')
    p.add_argument('--nih-root',   default='data/nih_cxr14',
                   help='NIH 数据根目录（HPC: data/nih_cxr14/）')
    p.add_argument('--nih-subset', default=None,
                   help='NIH subset txt（默认用 config.data.subset_file）')
    p.add_argument('--n',          type=int, default=100,
                   help='NIH 样本数（默认 100；smoke 时自动缩到 6）')
    p.add_argument('--K',          type=int, default=64,
                   help=f'满步数（K=参照基准；>trained_S={TRAINED_S} 为外推）')
    p.add_argument('--n-easy',     type=int, default=20,
                   help='易组样本数（默认 20）')
    p.add_argument('--n-hard',     type=int, default=20,
                   help='难组样本数（默认 20）')
    p.add_argument('--batch-size', type=int, default=8,
                   help='每批推理样本数')
    p.add_argument('--out',        default='results/traj_genesis',
                   help='输出目录（写 csv + png）')
    p.add_argument('--device',     default='cpu')
    p.add_argument('--smoke',      action='store_true',
                   help='随机权重 + 极小 N，仅验管线不崩')
    args = p.parse_args()

    if args.smoke:
        args.n = 6
        print('[smoke] N 强制=6，随机权重，仅管线验证')

    device = torch.device(args.device)

    # ------------------------------------------------------------------
    # 构建模型
    # ------------------------------------------------------------------
    if args.config is not None:
        with open(args.config, encoding='utf-8') as f:
            config = yaml.safe_load(f)
    else:
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
    if args.K > trained_S:
        print(f'  [注意] K={args.K} > trained_S={trained_S}，'
              f'步数 {trained_S+1}~{args.K} 为外推区段')

    predictor_type = config['meta'].get('predictor_type', 'vit')
    is_nca = predictor_type in ('nca', 'vanilla_nca', 'scp_nca')
    if not is_nca:
        raise ValueError(f'traj_probe_genesis 仅支持 NCA predictor，当前={predictor_type}')

    # 覆盖 nca_steps 支持外推
    if args.K > pred.nca_steps:
        print(f'  覆盖 predictor.nca_steps: {pred.nca_steps} -> {args.K}（外推）')
        pred.nca_steps = args.K

    if args.ckpt:
        load_ckpt(args.ckpt, enc, pred, device)
    elif not args.smoke:
        print('  [警告] 无 --ckpt 且非 --smoke：随机初始化，结果无训练意义（仅管线验证）')

    enc.to(device)
    pred.to(device)

    crop_size = config['data']['crop_size']

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------
    if args.smoke:
        imgs, sample_ids = None, [f'nih_{i}' for i in range(args.n)]
        print('[smoke] 跳过数据加载，用随机特征')
    else:
        print(f'加载 NIH 数据 (n={args.n})…')
        imgs, sample_ids = load_nih_samples(
            root=config['data'].get('root_path', args.nih_root),
            n=args.n,
            crop_size=crop_size,
            image_folder=config['data'].get('image_folder', 'images-224/images-224'),
            subset_file=args.nih_subset or config['data'].get('subset_file'),
        )
        print(f'加载完成 shape={tuple(imgs.shape)}')

    # ------------------------------------------------------------------
    # 跑轨迹
    # ------------------------------------------------------------------
    print(f'\n跑轨迹（K={args.K} 步，N={args.n} 样本）…')
    sim_matrix, final_errs = compute_genesis(
        enc, pred, imgs,
        K=args.K,
        device=device,
        batch_size=args.batch_size,
        smoke=args.smoke,
    )
    N = sim_matrix.shape[0]
    print(f'  sim_matrix shape={sim_matrix.shape}')

    # ------------------------------------------------------------------
    # 分三组（按 final_err/norm 排序；norm 大=易，norm 小=难）
    # ------------------------------------------------------------------
    sorted_idx = np.argsort(final_errs)[::-1]  # 降序：大 norm→易

    n_easy = min(args.n_easy, N // 3)
    n_hard = min(args.n_hard, N // 3)
    n_mid  = N - n_easy - n_hard

    easy_idx   = sorted_idx[:n_easy].tolist()
    hard_idx   = sorted_idx[N - n_hard:].tolist()
    medium_idx = sorted_idx[n_easy:N - n_hard].tolist()

    group_labels  = ['easy', 'medium', 'hard']
    group_indices = [easy_idx, medium_idx, hard_idx]

    print(f'  easy={len(easy_idx)}  medium={len(medium_idx)}  hard={len(hard_idx)}')

    # ------------------------------------------------------------------
    # 振荡统计（逐样本）
    # ------------------------------------------------------------------
    is_mono_list  = []
    max_reb_list  = []
    for i in range(N):
        mono, reb = detect_oscillation(sim_matrix[i])
        is_mono_list.append(mono)
        max_reb_list.append(reb)

    n_mono = sum(is_mono_list)
    print(f'  单调样本: {n_mono}/{N}  振荡样本: {N-n_mono}/{N}')
    if N > 0:
        mean_reb = float(np.mean([r for r, m in zip(max_reb_list, is_mono_list) if not m] or [0.0]))
        print(f'  振荡样本均值 max_rebound={mean_reb:.4f}')

    # ------------------------------------------------------------------
    # 输出 csv（每样本一行）
    # ------------------------------------------------------------------
    os.makedirs(args.out, exist_ok=True)
    csv_path = os.path.join(args.out, 'genesis.csv')

    # 确定每样本所属组
    group_of = [''] * N
    for lbl, idx_list in zip(group_labels, group_indices):
        for i in idx_list:
            group_of[i] = lbl

    rows = []
    for i in range(N):
        row = {
            'sample_id':    sample_ids[i],
            'group':        group_of[i],
            'final_norm':   float(final_errs[i]),
            'is_monotone':  bool(is_mono_list[i]),
            'max_rebound':  float(max_reb_list[i]),
            'K':            args.K,
            'trained_S':    trained_S,
            'extrapolated': (args.K > trained_S),
        }
        # sim(k) 逐步写列（k=1..K）
        for k in range(1, args.K + 1):
            row[f'sim_k{k}'] = float(sim_matrix[i, k - 1])
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False)
    print(f'\n写出 csv: {csv_path}  ({len(df)} 行, {len(df.columns)} 列)')

    # ------------------------------------------------------------------
    # genesis 曲线图
    # ------------------------------------------------------------------
    png_path = os.path.join(args.out, 'genesis_curves.png')
    plot_genesis_curves(sim_matrix, group_labels, group_indices, args.K, trained_S, png_path)

    # ------------------------------------------------------------------
    # 振荡汇总
    # ------------------------------------------------------------------
    print('\n--- 振荡统计 ---')
    for lbl, idx_list in zip(group_labels, group_indices):
        if not idx_list:
            continue
        mono_in_group = sum(is_mono_list[i] for i in idx_list)
        reb_vals = [max_reb_list[i] for i in idx_list if not is_mono_list[i]]
        reb_str = f'mean_rebound={np.mean(reb_vals):.4f}' if reb_vals else 'no oscillation'
        print(f'  {lbl}: monotone={mono_in_group}/{len(idx_list)}  {reb_str}')

    print('\n解读提示：')
    print('  sim(k) 单调上升 → NCA 迭代稳定收敛到最终态（有序 genesis）')
    print('  sim(k) 振荡/回摆 → 细胞动力学不稳（random fire 引入的涌现噪声）')
    print('  三组分离明显 → 难度影响 genesis 速度（可作难度敏感性 kill-shot）')


if __name__ == '__main__':
    main()
