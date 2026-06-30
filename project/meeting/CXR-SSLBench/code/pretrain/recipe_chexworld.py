# -*- coding: utf-8 -*-
"""
CheXWorld (world-model JEPA) launch recipe —— 薄包装本地官方 repo train_jepa.py（R4 零偏离）。

repo = project/meeting/复现/CheXWorld/repo（paths.CHEXWORLD_REPO）。冻结超参真源 = SSL_RECIPES §4 / repo/PRETRAIN.md：
  ssl_type iwm_dual_easy / vit_base patch16 input224 / eff_bs 2048(=128×accum×gpus) / lr 2e-4 绝对 / min_lr 1e-6
  warmup 40ep / wd 0.05 恒定 / clip_grad 1 / ema 0.996→1.0 / ipe_scale 1.25 / loss l2 / pred_emb 384 / pred_depth 6
  mask multi_multiblock / enc_mask_scale 0.75-1.0 / extra_mean / extra_global_scale 0.3-1.0
  aug jit / crop rrc / scale_min 0.3 / epochs=E_eq(100)。

A′ 受控改法（SSL_RECIPES §4）：`--dataset mimic_nih_chex` → **`--dataset nih`**（单库；data_utils 含 'nih' 不含
  chex/mimic → ConcatDataset([NIH])）。HPC 用 accum_iter 凑 eff_bs=2048（保 lr=2e-4 绝对，官方在 2048 下定）。

⚠️ NIH 数据定位：train_jepa 走 repo 自家 data_utils/data_path.py 找 NIH（**非 harness paths.py**）。
   主线在 HPC 须把 data_path.py 的 NIH 路径指向 NIH_IMAGES_DIR（TODO，见 submit_pretrain.sh TODO-CHEX）。
⚠️ --data_postfix：官方例用 '_proc'（预处理图）；我们用 raw NIH → 默认 ''，主线按 HPC NIH 布局设（TODO）。

中间 ckpt：train_jepa 在 `(epoch+1)%eval_freq==0 or epoch==epochs-1 or epoch in eval_list` 存
  `epoch_{epoch}.pth.tar`（0-based epoch）。eff-ep E → epoch index E-1 → 传 eval_list=[24,49,99] 落 25/50/100。
ckpt 取 target_encoder.*（teacher，与 backbones.py::_load_chexworld use_target=True 一致）→ jepa_vit-B。
"""
import argparse

from recipe_base import Recipe, add_common_args
from common import save_unified_ckpt, make_meta, ckpt_out_path, strip_prefix


class CheXWorldRecipe(Recipe):
    method = 'chexworld'
    official_eff_bs = 2048
    entry = 'train_jepa.py'
    loader_hint = 'jepa_vit_base'   # ⚠️ 与 MAE/DINO/MoCo 不同：CheXWorld 用 models.jepa_vit（无 cls）

    CONFIG = dict(
        ssl_type='iwm_dual_easy',
        dataset='nih',              # A′ 单库
        model='vit_base',
        input_size=224, resize_size=224,
        lr=2e-4, min_lr=1e-6,       # lr 绝对值（train_jepa: lr 给定则直接用不缩放）
        warmup_epochs=40,
        weight_decay=0.05, weight_decay_end=0.05, clip_grad=1.0,
        ema=0.996, ema_end=1.0, ipe_scale=1.25,
        loss_type='l2', pred_emb_dim=384, pred_depth=6,
        mask_type='multi_multiblock', enc_mask_scale=(0.75, 1.0),
        extra_global_scale=(0.3, 1.0),
        aug_type='jit', crop_type='rrc', scale_min=0.3,
        print_freq=50, eval_freq=20,
    )

    def ckpt_epochs(self):
        return [25, 50, 100]

    def _eval_list(self):
        """eff-ep -> 0-based epoch index（存盘条件 epoch in eval_list）。"""
        return [e - 1 for e in self.ckpt_epochs()]

    def build_cmd(self, *, seed, output_dir, data_path, batch_size_per_gpu,
                  accum_iter, world_size, repo_dir, num_workers=16, python='python',
                  exp_name=None, data_postfix=''):
        bpg = int(batch_size_per_gpu) if batch_size_per_gpu else 128
        self.assert_eff_bs(bpg, accum_iter, world_size)
        c = self.CONFIG
        exp_name = exp_name or f'aprime_nih_e{self.e_eq}'
        eval_list = self._eval_list()
        cmd = [python, '-m', 'torch.distributed.run', '--nproc_per_node', str(world_size),
               '--rdzv_backend', 'c10d', '--rdzv_endpoint', 'localhost:0',
               f'{repo_dir}/{self.entry}',
               '--ssl_type', c['ssl_type'],
               '--dataset', c['dataset'],
               '--data_postfix', data_postfix,
               '--data_pct', '1.0',
               '--norm_type', 'default',
               '--model', c['model'],
               '--print_freq', str(c['print_freq']),
               '--batch_size', str(bpg),
               '--accum_iter', str(accum_iter),
               '--num_workers', str(num_workers),
               '--amp',
               '--epochs', str(self.budget['epochs']),
               '--warmup_epochs', str(c['warmup_epochs']),
               '--eval_freq', str(c['eval_freq']),
               '--eval_list', *[str(e) for e in eval_list],
               '--input_size', str(c['input_size']),
               '--resize_size', str(c['resize_size']),
               '--aug_type', c['aug_type'],
               '--crop_type', c['crop_type'],
               '--scale_min', str(c['scale_min']),
               '--lr', str(c['lr']),
               '--min_lr', str(c['min_lr']),
               '--weight_decay', str(c['weight_decay']),
               '--weight_decay_end', str(c['weight_decay_end']),
               '--clip_grad', str(c['clip_grad']),
               '--ema', str(c['ema']),
               '--ema_end', str(c['ema_end']),
               '--ipe_scale', str(c['ipe_scale']),
               '--loss_type', c['loss_type'],
               '--pred_emb_dim', str(c['pred_emb_dim']),
               '--pred_depth', str(c['pred_depth']),
               '--mask_type', c['mask_type'],
               '--enc_mask_scale', str(c['enc_mask_scale'][0]), str(c['enc_mask_scale'][1]),
               '--mask_merge',
               '--extra_mean',
               '--extra_global_scale', str(c['extra_global_scale'][0]), str(c['extra_global_scale'][1]),
               '--output_dir', output_dir,
               '--exp_name', exp_name,
               '--seed', str(seed)]
        return cmd

    def export_ckpt(self, src_ckpt, ep, seed, results_dir):
        """官方 CheXWorld ckpt(epoch_*.pth.tar) -> 统一 schema。取 target_encoder.*（teacher）-> jepa_vit-B。"""
        import torch  # 惰性
        obj = torch.load(src_ckpt, map_location='cpu', weights_only=False)
        sd = obj['model']
        enc, n = strip_prefix(sd, 'target_encoder.')
        assert n > 0, f'[chexworld] target_encoder. 前缀未命中，键样例={list(sd)[:3]}'
        meta = make_meta(self.method, seed, self.official_eff_bs, ep, e_eq=self.e_eq,
                         loader_hint=self.loader_hint, arch='vit_base',
                         src_ckpt=src_ckpt, stripped_prefix='target_encoder.',
                         extra=dict(ssl_type=self.CONFIG['ssl_type'], use_target=True,
                                    n_backbone_keys=n,
                                    src_epoch_0based=obj.get('epoch')))
        out = ckpt_out_path(results_dir, self.method, seed, ep)
        return save_unified_ckpt(out, enc, meta)


if __name__ == '__main__':
    p = add_common_args(argparse.ArgumentParser(description='CheXWorld recipe (thin wrapper, 不跑训练)'))
    p.add_argument('--exp_name', default=None)
    p.add_argument('--data_postfix', default='')
    a = p.parse_args()
    r = CheXWorldRecipe(e_eq=a.e_eq)
    if a.mode == 'print-cmd':
        print(' '.join(r.build_cmd(
            seed=a.seed, output_dir=a.output_dir, data_path=a.data_path,
            batch_size_per_gpu=a.batch_size_per_gpu, accum_iter=a.accum_iter,
            world_size=a.world_size, repo_dir=a.repo_dir,
            exp_name=a.exp_name, data_postfix=a.data_postfix)))
    elif a.mode == 'export':
        print(r.export_ckpt(a.src_ckpt, a.ep, a.seed, a.results_dir))
    else:
        print(f'[CheXWorld] eff_bs={r.official_eff_bs} budget={r.budget} '
              f'ckpt_epochs={r.ckpt_epochs()} eval_list(0based)={r._eval_list()}')
        print(f'            CONFIG={r.CONFIG}')
