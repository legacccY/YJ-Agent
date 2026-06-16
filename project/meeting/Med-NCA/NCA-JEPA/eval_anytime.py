# -*- coding: utf-8 -*-
# ===========================================================================
# NCA-JEPA pilot —— anytime × stability trade-off 评估（§9.1 一等指标产出工具）
#
# 这是 03_pilot_NIH_ChestXray14.md §9.1 的核心产出脚本。没有它，就算训练跑完
# 也产不出那张 trade-off 图，§9.1 升一等只是纸面。
#
# 两个模式：
#   [eval]      单配置（单 ckpt / 单臂）→ 出 Q(k) 曲线 csv + 单配置曲线图 + L_f（NCA）。
#               python eval_anytime.py eval --config configs/a2_scp_nca_vits_nih10k.yaml \
#                       --ckpt checkpoints/a2_seed42/last.pth.tar --out results/anytime_a2_s42.csv
#   [aggregate] 多份 anytime_*.csv → trade-off 主图（Q(k) 曲线族）+ 副图（anytime-gain vs
#               stability-margin 散点）。跑完多个 S/臂后汇总。
#               python eval_anytime.py aggregate --glob "results/anytime_*.csv" --out-fig results/tradeoff.png
#
# 指标定义（02_理论框架 §4 / 03_pilot §9.1，红线：Q 是 latent regression 的 cosine，不是分割 Dice）：
#   Q(k) = cos( ĥ_y^(k), ĥ_y^(S) )   第 k 步/层提前终止预测 vs 满步预测的 cosine（自洽性）。
#   anytime-gain = Q(k_early) / Q(k_full)   （默认 k_early 取 ~S/2，k_full 取满步；脚本按可用 k 自适应）。
#   stability-margin = 1 − L_f   （L_f = NCA cell Jacobian 谱半径，power iteration 估；A0+/ViT 无此量，标 NaN）。
#
# anytime 接口（已在 predictor 实现）：
#   NCA:  predictor(x, masks_x, masks, exit_step=k)   k∈[1, nca_steps]
#   A0+:  predictor(x, masks_x, masks, exit_layer=k)  k∈[1, depth]
#
# 阈值（§9.1，工程 go/no-go 设计决策，非论文 claim）：
#   anytime-gain ≥ 0.85（某 L_f≤0.9 稳定配置）→ 「稳定×anytime 可共存」成立。
#   全部稳定配置 < 0.70 → 诚实报互斥 + best-compromise S（可发表负结果）。
# ===========================================================================

import os
import sys
import glob
import argparse

import numpy as np
import pandas as pd
import yaml
import torch
import torch.nn.functional as F

_HERE = os.path.dirname(os.path.abspath(__file__))
_IJEPA_ROOT = os.path.join(_HERE, 'ijepa')
if _IJEPA_ROOT not in sys.path:
    sys.path.insert(0, _IJEPA_ROOT)

from src.helper import init_model  # noqa: E402


# ----------------------------------------------------------------------------
# 模型构建 + ckpt 载入
# ----------------------------------------------------------------------------
def build_model(config, device):
    """按 config 的 meta 重建 encoder+predictor（与训练同路径，保证结构一致）。"""
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
        exit_stop_grad=m.get('exit_stop_grad', False))
    return enc, pred


def load_ckpt(ckpt_path, encoder, predictor, device):
    """载 ckpt 的 target_encoder（EMA 版）+ predictor 权重，strip 'module.' 前缀。"""
    ck = torch.load(ckpt_path, map_location='cpu')
    def strip(d):
        return {k.replace('module.', ''): v for k, v in d.items()}
    enc_key = 'target_encoder' if 'target_encoder' in ck else 'encoder'
    msg_e = encoder.load_state_dict(strip(ck[enc_key]), strict=False)
    msg_p = predictor.load_state_dict(strip(ck['predictor']), strict=False)
    print(f'  载 ckpt epoch={ck.get("epoch","?")} enc({enc_key}) missing={len(msg_e.missing_keys)} '
          f'pred missing={len(msg_p.missing_keys)} unexpected={len(msg_p.unexpected_keys)}')
    return encoder, predictor


# ----------------------------------------------------------------------------
# 造 anytime 输入（context 特征 + mask indices）
# ----------------------------------------------------------------------------
def make_inputs(encoder, predictor, imgs, n_ctx, n_pred, device, smoke=False):
    """返回 (x_ctx, masks_x, masks)。smoke=True 时用 random 特征不过 encoder（管线验证）。"""
    N = encoder.patch_embed.num_patches
    D = encoder.embed_dim
    B = imgs.shape[0] if imgs is not None else 2
    # batch 共享一组 mask indices（评估 Q(k) 自洽性足够）
    perm = torch.randperm(N, device=device)
    ctx_idx = perm[:n_ctx].sort().values
    pred_idx = perm[n_ctx:n_ctx + n_pred].sort().values
    masks_x = [ctx_idx.unsqueeze(0).expand(B, -1).contiguous()]
    masks = [pred_idx.unsqueeze(0).expand(B, -1).contiguous()]
    if smoke or imgs is None:
        x_ctx = torch.randn(B, n_ctx, D, device=device)
    else:
        with torch.no_grad():
            feats = encoder(imgs.to(device))            # [B,N,D]
        x_ctx = torch.gather(feats, 1, ctx_idx.view(1, -1, 1).expand(B, -1, D))
    return x_ctx, masks_x, masks


def _pred_at(predictor, x, masks_x, masks, k, is_nca):
    """第 k 步/层的预测；k=None 即满步。"""
    if k is None:
        return predictor(x, masks_x, masks)
    if is_nca:
        return predictor(x, masks_x, masks, exit_step=k)
    out = predictor(x, masks_x, masks, exit_layer=k)
    return out


def compute_qk(predictor, x, masks_x, masks, ks, full_k, is_nca):
    """Q(k)=cos(ĥ^(k), ĥ^(S))，按样本+token 展平算 cosine 再平均。返回 {k: Q}。"""
    predictor.eval()
    with torch.no_grad():
        z_full = _pred_at(predictor, x, masks_x, masks, None if is_nca else full_k, is_nca)
        zf = z_full.reshape(z_full.shape[0], -1)
        out = {}
        for k in ks:
            zk = _pred_at(predictor, x, masks_x, masks, k, is_nca)
            zk = zk.reshape(zk.shape[0], -1)
            q = F.cosine_similarity(zk, zf, dim=1).mean().item()
            out[k] = q
    return out


# ----------------------------------------------------------------------------
# L_f：NCA cell Jacobian 谱半径（power iteration via JVP），命题 1.1 / §10 理论锚
# ----------------------------------------------------------------------------
def estimate_lf(predictor, x, masks_x, masks, n_iter=20):
    """对 NCA cell 在真实迭代轨迹多点上估 ‖J_f‖_2（谱半径上界），取最大值。

    口径说明（§10/命题1.1）：
    - 估计点：在 (x, masks_x, masks) 的真实 forward 轨迹上取 S/4、S/2、3S/4 三步
      拿到真实网格状态 h，分别用 power iteration 估 sigma，取 max。
      （Bug#1 修复：原实现在 torch.randn 随机点估，与轨迹无关；现改为真实点。）
    - 算子固定：cell 内含随机 fire mask，power iteration 要求算子不变才能收敛。
      修复方式：每次 cell(h_, generator=gen) 调用前 gen.manual_seed(FIXED_SEED)
      重置，使每步看到相同 fire mask（确定性 fire 路径，与 scp_nca 训练时
      deterministic_fire 语义一致）。
    - Bug#2 结论：NCAStep.forward 返回 h + fire*delta（残差全映射），cell(h_) 的
      Jacobian 已是 d(h+fire·delta)/dh = I + diag(fire)·J_delta，口径正确，
      不需修正。
    - 锚定：get_hidden_at_step 含锚定步骤（context 位置强制，是迭代映射的一部分）；
      cell(h_) 用于估 Jacobian 时不含锚定（锚定对 h 是仿射投影，不改变 cell 本身
      的谱半径；若含锚定则 sigma 会被人为压低，偏保守但口径不清晰）。
    - 非 NCA predictor（无 cell 属性）返回 NaN。
    """
    cell = getattr(predictor, 'cell', None)
    if cell is None:
        return float('nan')
    if not hasattr(predictor, 'get_hidden_at_step'):
        return float('nan')

    predictor.eval()
    S = predictor.nca_steps
    fire_seed = getattr(predictor, 'fire_seed', 0)

    # 轨迹采样点：S/4, S/2, 3S/4（各取整，去重，保证 >=1）
    sample_steps = sorted(set(max(1, s) for s in [S // 4, S // 2, (3 * S) // 4]))

    # 固定 fire 用的 generator（每次 power iteration 步前 reset seed，保算子不变）
    gen = torch.Generator(device=x.device)

    sigma_max = 0.0
    with torch.no_grad():
        hidden_states = [predictor.get_hidden_at_step(x, masks_x, masks, s)
                         for s in sample_steps]

    for h_pt in hidden_states:
        # 初始随机方向向量
        v = torch.randn_like(h_pt)
        v = v / (v.norm() + 1e-12)
        sigma = 0.0
        for _ in range(n_iter):
            h_ = h_pt.detach().requires_grad_(True)
            # 每次 reset seed，保证 power iteration 每步算子相同（固定 fire mask）
            gen.manual_seed(fire_seed)
            f = cell(h_, generator=gen)
            # JVP: J·v via autograd（‖Jv‖/‖v‖ 即当前估计的最大奇异值）
            (jv,) = torch.autograd.grad(
                f, h_, grad_outputs=v, create_graph=False, retain_graph=False)
            sigma = jv.norm().item() / (v.norm().item() + 1e-12)
            v = (jv / (jv.norm() + 1e-12)).detach()
        if sigma > sigma_max:
            sigma_max = sigma

    return float(sigma_max)


# ----------------------------------------------------------------------------
# eval 模式：单配置出 Q(k) csv + 曲线图
# ----------------------------------------------------------------------------
def run_eval(args):
    device = torch.device(args.device)
    with open(args.config, encoding='utf-8') as f:
        config = yaml.safe_load(f)
    m = config['meta']
    is_nca = m.get('predictor_type', 'vit') in ('nca', 'vanilla_nca', 'scp_nca')
    enc, pred = build_model(config, device)
    if args.ckpt:
        load_ckpt(args.ckpt, enc, pred, device)
    elif not args.smoke:
        print('  [警告] 无 --ckpt 且非 --smoke：用随机初始化权重，Q(k) 数值无意义（仅管线验证）')

    # 可用步数/层数
    if is_nca:
        full_k = m.get('nca_steps', 16)
        ks = [k for k in [1, 2, 4, 8, 16, 32, 64] if k <= full_k]
    else:
        full_k = m.get('pred_depth', 6)
        ks = list(range(1, full_k + 1))

    # 数据
    imgs = None
    if not args.smoke and args.ckpt:
        imgs = _load_eval_batch(config, args.n_imgs, device)

    n_ctx = max(8, int(enc.patch_embed.num_patches * 0.5))
    n_pred = max(4, int(enc.patch_embed.num_patches * 0.15))
    x, masks_x, masks = make_inputs(enc, pred, imgs, n_ctx, n_pred, device, smoke=args.smoke)

    qk = compute_qk(pred, x, masks_x, masks, ks, full_k, is_nca)
    lf = estimate_lf(pred, x, masks_x, masks) if is_nca else float('nan')

    # anytime-gain：早停点取 ~half，满步取 full
    k_early = ks[len(ks) // 2]
    gain = qk[k_early] / (qk[full_k] + 1e-12) if full_k in qk else float('nan')

    rows = [{'arm': m.get('predictor_type'), 'config': os.path.basename(args.config),
             'k': k, 'Q': qk[k], 'full_k': full_k, 'L_f': lf,
             'stability_margin': (1 - lf) if not np.isnan(lf) else float('nan'),
             'anytime_gain': gain, 'k_early': k_early} for k in ks]
    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f'\nQ(k): ' + '  '.join(f'k={k}:{qk[k]:.3f}' for k in ks))
    print(f'L_f={lf:.3f}  stability-margin={1-lf:.3f}  anytime-gain(Q{k_early}/Q{full_k})={gain:.3f}'
          if not np.isnan(lf) else
          f'L_f=NaN(非NCA)  anytime-gain(Q{k_early}/Q{full_k})={gain:.3f}')
    print(f'写出 {args.out}')

    if args.out_fig:
        _plot_single(qk, ks, m.get('predictor_type'), args.out_fig)
    return df


def _load_eval_batch(config, n_imgs, device):
    from src.datasets.nih_cxr14 import NIHChestXray14
    import torchvision.transforms as T
    root = config['data']['root_path']
    tf = T.Compose([T.Resize((config['data']['crop_size'],) * 2), T.ToTensor(),
                    T.Lambda(lambda t: t.expand(3, -1, -1) if t.shape[0] == 1 else t)])
    subset = config['data'].get('subset_file')
    ds = NIHChestXray14(root=root, image_folder=config['data']['image_folder'],
                        transform=tf, subset_file=subset)
    idx = np.random.choice(len(ds), size=min(n_imgs, len(ds)), replace=False)
    imgs = torch.stack([ds[i][0] for i in idx])
    return imgs


# ----------------------------------------------------------------------------
# aggregate 模式：多 csv → trade-off 主图（曲线族）+ 副图（散点）
# ----------------------------------------------------------------------------
def run_aggregate(args):
    files = sorted(glob.glob(args.glob))
    assert files, f'无文件匹配 {args.glob}'
    dfs = [pd.read_csv(f).assign(src=os.path.basename(f)) for f in files]
    big = pd.concat(dfs, ignore_index=True)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    # 主图：Q(k) 曲线族
    for src, g in big.groupby('src'):
        g = g.sort_values('k')
        ax1.plot(g['k'], g['Q'], marker='o', label=src.replace('anytime_', '').replace('.csv', ''))
    ax1.set_xlabel('exit step / layer  k'); ax1.set_ylabel('Q(k) = cos(h_pred^k, h_pred^S)')
    ax1.set_title('Anytime quality curves (Q(k) family)'); ax1.legend(fontsize=7); ax1.grid(alpha=0.3)
    # 副图：anytime-gain vs stability-margin 散点
    per = big.groupby('src').agg(gain=('anytime_gain', 'first'),
                                 margin=('stability_margin', 'first'),
                                 arm=('arm', 'first')).reset_index()
    ax2.scatter(per['margin'], per['gain'])
    for _, r in per.iterrows():
        ax2.annotate(r['src'].replace('anytime_', '').replace('.csv', ''),
                     (r['margin'], r['gain']), fontsize=7)
    ax2.axhline(0.85, ls='--', c='g', lw=0.8, label='gain=0.85 (coexist thr.)')
    ax2.axhline(0.70, ls='--', c='r', lw=0.8, label='gain=0.70 (mutual-excl. lower)')
    ax2.set_xlabel('stability-margin = 1 - L_f'); ax2.set_ylabel('anytime-gain = Q(k_early)/Q(S)')
    ax2.set_title('Stability x Anytime trade-off'); ax2.legend(fontsize=7); ax2.grid(alpha=0.3)
    fig.tight_layout()
    os.makedirs(os.path.dirname(args.out_fig) or '.', exist_ok=True)
    fig.savefig(args.out_fig, dpi=150)
    print(f'写出 trade-off 图 {args.out_fig}（{len(files)} 配置）')
    big.to_csv(args.out_fig.replace('.png', '_merged.csv'), index=False)


def _plot_single(qk, ks, arm, out_fig):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.plot(ks, [qk[k] for k in ks], marker='o')
    ax.set_xlabel('exit step / layer k'); ax.set_ylabel('Q(k)')
    ax.set_title(f'Anytime quality curve - {arm}'); ax.grid(alpha=0.3)
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_fig) or '.', exist_ok=True)
    fig.savefig(out_fig, dpi=150)
    print(f'写出曲线图 {out_fig}')


def main():
    p = argparse.ArgumentParser(description='NCA-JEPA anytime × stability trade-off 评估 (§9.1)')
    sub = p.add_subparsers(dest='mode', required=True)
    pe = sub.add_parser('eval')
    pe.add_argument('--config', required=True)
    pe.add_argument('--ckpt', default=None)
    pe.add_argument('--out', default='results/anytime.csv')
    pe.add_argument('--out-fig', default=None)
    pe.add_argument('--n-imgs', type=int, default=32)
    pe.add_argument('--smoke', action='store_true', help='random 特征，仅验证管线不报错')
    pe.add_argument('--device', default='cpu')
    pa = sub.add_parser('aggregate')
    pa.add_argument('--glob', required=True)
    pa.add_argument('--out-fig', default='results/tradeoff.png')
    args = p.parse_args()
    if args.mode == 'eval':
        run_eval(args)
    else:
        run_aggregate(args)


if __name__ == '__main__':
    main()
