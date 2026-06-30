# -*- coding: utf-8 -*-
"""
MAE launch recipe —— 薄包装 facebookresearch/mae 官方 main_pretrain.py（R4 零偏离）。

冻结超参真源 = 矩阵 §1 + SSL_RECIPES §1：
  eff_bs 4096 / blr 1.5e-4(lr=2.4e-3 @4096) / warmup 5ep / mask_ratio 0.90 / --norm_pix_loss
  wd 0.05 / AdamW(β1=.9,β2=.95) / cosine / epochs=E_eq(100)。
  ⚠️ mask 0.90 取自 medical_mae CXR 配方（胸片信息密度低）；base repo = facebookresearch/mae（默认 0.75，此处覆盖）。

⚠️ 增强 scale：facebookresearch/mae 默认 RandomResizedCrop scale (0.2,1.0)；medical_mae CXR 用 (0.5,1.0)。
   矩阵 §1 未指定 → 默认用 base repo (0.2,1.0)，TODO 主线/researcher 确认是否换 CXR 的 (0.5,1.0)。

⚠️ 中间 ckpt：facebookresearch/mae 原生存盘 cadence = 每 20 epoch + last（无 --save_freq 入口）。
   → 默认中间预算点会落在 {20,40,60,80,100} 而非矩阵 {25,50,100}。两者都是合法 probe-vs-budget 采样点。
   export_ckpt 按实际 ep 记 meta，对两种 cadence 都鲁棒。若要精确 25/50：主线在 submit 加 1 行
   非算法性 save-condition 补丁（不改训练动态）—— 见 submit_pretrain.sh TODO-MAE。
"""
import argparse

from recipe_base import Recipe, add_common_args
from common import save_unified_ckpt, make_meta, ckpt_out_path

# RandomResizedCrop scale：默认 base-repo 值；TODO 见模块 docstring。
MAE_RRC_SCALE = (0.2, 1.0)


class MAERecipe(Recipe):
    method = 'mae'
    official_eff_bs = 4096
    entry = 'main_pretrain.py'
    loader_hint = 'timm_vit_base'

    CONFIG = dict(
        model='mae_vit_base_patch16',
        mask_ratio=0.90,            # 矩阵 §1（medical_mae CXR）；覆盖 base repo 0.75
        norm_pix_loss=True,
        blr=1.5e-4,                 # lr = blr × eff_bs/256 = 2.4e-3 @4096（MAE 内部线性缩放，保 eff_bs=4096）
        weight_decay=0.05,
        warmup_epochs=5,            # 矩阵 §1（官方 40@800ep → 按 100ep 预算比例缩 1/8；planner 定稿）
        input_size=224,
        # AdamW β=(0.9,0.95) = MAE main_pretrain 硬编码默认，无需传参
    )

    def build_cmd(self, *, seed, output_dir, data_path, batch_size_per_gpu,
                  accum_iter, world_size, repo_dir, num_workers=8, python='python',
                  rrc_scale=MAE_RRC_SCALE):
        self.assert_eff_bs(batch_size_per_gpu, accum_iter, world_size)
        c = self.CONFIG
        # 多卡 → torchrun；单卡也可 torchrun --nproc_per_node 1（与官方 DDP 路径一致）
        cmd = [python, '-m', 'torch.distributed.run', '--nproc_per_node', str(world_size),
               f'{repo_dir}/{self.entry}',
               '--model', c['model'],
               '--mask_ratio', str(c['mask_ratio']),
               '--norm_pix_loss',
               '--epochs', str(self.budget['epochs']),
               '--warmup_epochs', str(c['warmup_epochs']),
               '--blr', str(c['blr']),
               '--weight_decay', str(c['weight_decay']),
               '--batch_size', str(batch_size_per_gpu),
               '--accum_iter', str(accum_iter),
               '--input_size', str(c['input_size']),
               '--num_workers', str(num_workers),
               '--data_path', data_path,
               '--output_dir', output_dir,
               '--log_dir', output_dir,
               '--seed', str(seed)]
        # ⚠️ facebookresearch/mae 无 RandomResizedCrop scale 入口；若用 medical_mae fork 则加
        #    `--random_resize_range {lo} {hi}`。base repo 用默认 (0.2,1.0)，此处仅记录不传。
        return cmd

    def export_ckpt(self, src_ckpt, ep, seed, results_dir):
        """官方 MAE ckpt -> 统一 schema。滤 decoder_*/mask_token（解码器，probe 不用），余 = timm-vit-B encoder。"""
        import torch  # 惰性
        obj = torch.load(src_ckpt, map_location='cpu', weights_only=False)
        sd = obj.get('model', obj)
        enc = {k: v for k, v in sd.items()
               if not k.startswith('decoder') and k != 'mask_token'}
        meta = make_meta(self.method, seed, self.official_eff_bs, ep, e_eq=self.e_eq,
                         loader_hint=self.loader_hint, arch=self.arch, src_ckpt=src_ckpt,
                         stripped_prefix='(filtered decoder_*/mask_token)',
                         extra=dict(mask_ratio=self.CONFIG['mask_ratio'], norm_pix_loss=True,
                                    n_dropped=len(sd) - len(enc)))
        out = ckpt_out_path(results_dir, self.method, seed, ep)
        return save_unified_ckpt(out, enc, meta)


if __name__ == '__main__':
    p = add_common_args(argparse.ArgumentParser(description='MAE recipe (thin wrapper, 不跑训练)'))
    a = p.parse_args()
    r = MAERecipe(e_eq=a.e_eq)
    if a.mode == 'print-cmd':
        print(' '.join(r.build_cmd(
            seed=a.seed, output_dir=a.output_dir, data_path=a.data_path,
            batch_size_per_gpu=a.batch_size_per_gpu, accum_iter=a.accum_iter,
            world_size=a.world_size, repo_dir=a.repo_dir)))
    elif a.mode == 'export':
        print(r.export_ckpt(a.src_ckpt, a.ep, a.seed, a.results_dir))
    else:
        print(f'[MAE] eff_bs={r.official_eff_bs} budget={r.budget} ckpt_epochs={r.ckpt_epochs()}')
        print(f'      CONFIG={r.CONFIG}')
