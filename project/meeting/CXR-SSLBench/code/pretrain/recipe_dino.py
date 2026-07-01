# -*- coding: utf-8 -*-
"""
DINO v1 launch recipe —— 薄包装 facebookresearch/dino 官方 main_dino.py（R4 零偏离，**非 DINOv2**）。

冻结超参真源 = 矩阵 §1 + SSL_RECIPES §2：
  arch vit_base / patch 16 / out_dim 65536 / eff_bs 512 / lr 0.00075 / warmup 10ep / min_lr 2e-6
  wd 0.04→0.4 / momentum_teacher 0.996 / warmup_teacher_temp 0.04 / teacher_temp 0.07
  warmup_teacher_temp_epochs≈12.5(→13) / norm_last_layer=true / freeze_last_layer 3 / **use_fp16=false**(ViT-B 关 AMP 防 NaN)
  global_crops_scale [0.25,1.0] / local_crops_scale [0.05,0.25] / local_crops_number 10 / epochs=E_eq(100)。

⚠️ DINO **无 gradient accumulation**：eff_bs = batch_size_per_gpu × world_size（无 accum）。
   要保官方 eff_bs=512 → HPC 选 gpu/batch 组合凑 512（如 4 卡×128）；1 卡需 batch 512（ViT-B+10 local crop 易 OOM）。
   assert_eff_bs 强制 accum_iter=1 且乘积==512。

⚠️ warmup_teacher_temp_epochs：矩阵给 12.5（官方 50@400ep 按比例 → 12.5），DINO 该参为 int。
   默认向上取整 13（SSL_RECIPES §6：temp warmup 越长越稳）。TODO 主线/planner 确认 12 vs 13。
   collapse 烟测失败动作之一就是「延 temp warmup」——此参是烟测主调旋钮。

⚠️ 112k 小语料 DINO ViT-B collapse 风险**最高**（SSL_RECIPES §2/§6 无成功先例）→ 强依赖 SMK-DINO 烟测放行。
"""
import argparse

from recipe_base import Recipe, add_common_args
from common import save_unified_ckpt, make_meta, ckpt_out_path, strip_prefix

# warmup_teacher_temp_epochs：12.5 向上取整（更稳）。TODO 见模块 docstring。
DINO_WARMUP_TEACHER_TEMP_EPOCHS = 13


class DINORecipe(Recipe):
    method = 'dino'
    official_eff_bs = 512
    official_lr = 0.00075       # @eff_bs512（官方 args.txt）；reduced 时 lr×eff/512（路 A 线性缩放）
    entry = 'main_dino.py'
    loader_hint = 'timm_vit_base'

    CONFIG = dict(
        arch='vit_base',
        patch_size=16,
        out_dim=65536,
        lr=0.00075,                 # DINO 内部按 eff_bs 线性缩放（×eff_bs/256）；保官方 eff_bs=512 即复现官方
        min_lr=2e-6,
        warmup_epochs=10,
        weight_decay=0.04,
        weight_decay_end=0.4,
        momentum_teacher=0.996,
        warmup_teacher_temp=0.04,
        teacher_temp=0.07,
        warmup_teacher_temp_epochs=DINO_WARMUP_TEACHER_TEMP_EPOCHS,
        norm_last_layer=True,
        freeze_last_layer=3,
        use_fp16=False,             # ⚠️ ViT-B 关 fp16，AMP 致 NaN/collapse（SSL_RECIPES §2）
        global_crops_scale=(0.25, 1.0),
        local_crops_scale=(0.05, 0.25),
        local_crops_number=10,
    )

    def assert_eff_bs(self, batch_size_per_gpu, accum_iter, world_size):
        assert int(accum_iter) == 1, '[dino] DINO 无 gradient accumulation，accum_iter 必须=1'
        return super().assert_eff_bs(batch_size_per_gpu, 1, world_size)

    def build_cmd(self, *, seed, output_dir, data_path, batch_size_per_gpu,
                  accum_iter, world_size, repo_dir, num_workers=8, python='python',
                  saveckp_freq=25):
        eff = self.assert_eff_bs(batch_size_per_gpu, accum_iter, world_size)
        lr = self.scaled_lr(eff)   # eff==512 → 0.00075；reduced → 0.00075×eff/512（步数由 budget 按 eff 放大）
        c = self.CONFIG
        cmd = [python, '-m', 'torch.distributed.run', '--nproc_per_node', str(world_size),
               f'{repo_dir}/{self.entry}',
               '--arch', c['arch'],
               '--patch_size', str(c['patch_size']),
               '--out_dim', str(c['out_dim']),
               '--norm_last_layer', 'true' if c['norm_last_layer'] else 'false',
               '--warmup_teacher_temp', str(c['warmup_teacher_temp']),
               '--teacher_temp', str(c['teacher_temp']),
               '--warmup_teacher_temp_epochs', str(c['warmup_teacher_temp_epochs']),
               '--use_fp16', 'true' if c['use_fp16'] else 'false',
               '--weight_decay', str(c['weight_decay']),
               '--weight_decay_end', str(c['weight_decay_end']),
               '--freeze_last_layer', str(c['freeze_last_layer']),
               '--lr', str(lr),
               '--warmup_epochs', str(c['warmup_epochs']),
               '--min_lr', str(c['min_lr']),
               '--momentum_teacher', str(c['momentum_teacher']),
               '--global_crops_scale', str(c['global_crops_scale'][0]), str(c['global_crops_scale'][1]),
               '--local_crops_scale', str(c['local_crops_scale'][0]), str(c['local_crops_scale'][1]),
               '--local_crops_number', str(c['local_crops_number']),
               '--batch_size_per_gpu', str(batch_size_per_gpu),
               '--epochs', str(self.budget['epochs']),
               '--saveckp_freq', str(saveckp_freq),   # 25 → 落 25/50/75/100，export 取 25/50/100
               '--num_workers', str(num_workers),
               '--data_path', data_path,
               '--output_dir', output_dir,
               '--seed', str(seed)]
        return cmd

    def export_ckpt(self, src_ckpt, ep, seed, results_dir, use='teacher'):
        """官方 DINO ckpt -> 统一 schema。取 teacher（DINO 下游 eval 规范用 teacher），
        strip 'backbone.' 前缀（DINO=MultiCropWrapper(backbone, head)），丢 head.* -> timm-vit-B。"""
        import torch  # 惰性
        obj = torch.load(src_ckpt, map_location='cpu', weights_only=False)
        raw = obj[use]  # 'teacher' or 'student'
        # DDP 可能带 'module.' 前缀
        if all(k.startswith('module.') for k in raw):
            raw = {k[len('module.'):]: v for k, v in raw.items()}
        enc, n = strip_prefix(raw, 'backbone.')   # head.* 自动丢弃（不以 backbone. 开头）
        assert n > 0, f'[dino] backbone. 前缀未命中，键样例={list(raw)[:3]}'
        meta = make_meta(self.method, seed, self.official_eff_bs, ep, e_eq=self.e_eq,
                         loader_hint=self.loader_hint, arch=self.arch, src_ckpt=src_ckpt,
                         stripped_prefix='backbone.',
                         extra=dict(use=use, out_dim=self.CONFIG['out_dim'],
                                    n_backbone_keys=n))
        out = ckpt_out_path(results_dir, self.method, seed, ep)
        return save_unified_ckpt(out, enc, meta)


if __name__ == '__main__':
    p = add_common_args(argparse.ArgumentParser(description='DINO recipe (thin wrapper, 不跑训练)'))
    a = p.parse_args()
    r = DINORecipe(e_eq=a.e_eq)
    if a.mode == 'print-cmd':
        print(' '.join(r.build_cmd(
            seed=a.seed, output_dir=a.output_dir, data_path=a.data_path,
            batch_size_per_gpu=a.batch_size_per_gpu, accum_iter=a.accum_iter,
            world_size=a.world_size, repo_dir=a.repo_dir)))
    elif a.mode == 'export':
        print(r.export_ckpt(a.src_ckpt, a.ep, a.seed, a.results_dir))
    else:
        print(f'[DINO] eff_bs={r.official_eff_bs} budget={r.budget} ckpt_epochs={r.ckpt_epochs()}')
        print(f'       CONFIG={r.CONFIG}')
