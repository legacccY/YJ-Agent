# -*- coding: utf-8 -*-
"""
MoCo-v3 launch recipe —— 薄包装 facebookresearch/moco-v3 官方 main_moco.py（R4 零偏离）。

冻结超参真源 = 矩阵 §1 + SSL_RECIPES §3：
  arch vit_base / eff_bs 4096 / lr 1.0e-4(base，moco 内部 ×bs/256) / warmup 13ep / wd 0.1
  moco-t 0.2 / --moco-m-cos / **--stop-grad-conv1 必开**(ViT 不稳定缓解=fixed random patch proj) / AdamW / epochs=E_eq(100)。
  ⚠️ lr 取 1.0e-4 非 1.5e-4（SSL_RECIPES §3：1.0e-4 更稳，72.2%）。

⚠️⚠️ batch 现实约束（TODO-B / 矩阵 §2 预登记）：官方 ViT-B bs4096 = 8-node 64 卡，HPC 4 卡放不下。
   MoCo-v3 **无 accum_iter** → eff_bs=total batch=gpus×per-gpu。减 batch 时 moco **内部自动线性缩放 lr**
   （lr×bs/256），且 images-seen 仍=11.21M（epochs=100 over NIH 不随 batch 变，只 step 数变）。
   **但** batch=对比负样本数=方法构成要素，减 batch 偏离官方 → 须 SMK-MOCO 烟测定 + LOG 留痕（矩阵 §2 失败动作）。
   recipe 默认 total_batch=4096；override 走 reduced 路径会 loudly warn，actual eff_bs 记进 ckpt meta。
"""
import argparse

from recipe_base import Recipe, add_common_args
from common import save_unified_ckpt, make_meta, ckpt_out_path, strip_prefix, budget


class MoCoRecipe(Recipe):
    method = 'moco'
    official_eff_bs = 4096
    official_lr = 1.0e-4        # @eff_bs4096（SSL_RECIPES §3 锚点，比 1.5e-4 稳）；reduced 时 lr×eff/4096
    entry = 'main_moco.py'
    loader_hint = 'timm_vit_base'

    CONFIG = dict(
        arch='vit_base',
        lr=1.0e-4,                  # base lr；moco 内部 ×total_bs/256。SSL_RECIPES §3：1.0e-4 比 1.5e-4 稳
        weight_decay=0.1,
        warmup_epochs=13,
        moco_t=0.2,
        moco_m_cos=True,            # --moco-m-cos（cosine EMA → 1.0）
        stop_grad_conv1=True,       # ⚠️ 必开：fixed random patch projection（ViT 稳定性）
        optimizer='adamw',
        # moco-dim/moco-mlp-dim 用官方 ViT 默认（256/4096），无需覆盖
    )

    def build_cmd(self, *, seed, output_dir, data_path, batch_size_per_gpu,
                  accum_iter, world_size, repo_dir, num_workers=8, python='python',
                  total_batch=None, dist_url='tcp://localhost:10001'):
        # MoCo 无 accum；actual eff_bs = 全局 batch = batch/gpu × world_size（修「无视 batch_size_per_gpu」bug）。
        assert int(accum_iter) == 1, '[moco] MoCo-v3 无 gradient accumulation，accum_iter 必须=1'
        if total_batch is not None:
            eff = int(total_batch)                      # 显式 override（legacy / 直接指定全局 batch）
        elif batch_size_per_gpu is not None:
            eff = int(batch_size_per_gpu) * int(accum_iter) * int(world_size)
        else:
            eff = self.official_eff_bs                  # 都没给 → 官方 4096
        lr = self.check_eff_and_lr(eff)   # eff>official 抛；eff<official → reduced：lr×eff/4096 + stderr WARN
        c = self.CONFIG
        cmd = [python, f'{repo_dir}/{self.entry}',
               '-a', c['arch'],
               '--optimizer', c['optimizer'],
               '--lr', str(lr),
               '--weight-decay', str(c['weight_decay']),
               '--epochs', str(self.budget['epochs']),
               '--warmup-epochs', str(c['warmup_epochs']),
               '--batch-size', str(eff),                # moco: 全局 batch = 实际 eff_bs（非硬编码 4096）
               '--moco-t', str(c['moco_t']),
               '--moco-m-cos',
               '--stop-grad-conv1',
               '--workers', str(num_workers),   # moco-v3 用 --workers/-j（非 --num_workers）
               '--multiprocessing-distributed',
               '--world-size', '1', '--rank', '0',
               '--dist-url', dist_url,
               '--seed', str(seed),
               data_path]
        # ⚠️ moco-v3 输出目录：官方写 cwd 下 checkpoint_*.pth.tar，须在 output_dir 下 cd 运行（submit 处理）。
        return cmd

    def export_ckpt(self, src_ckpt, ep, seed, results_dir, eff_bs=None):
        """官方 MoCo-v3 ckpt -> 统一 schema。取 base_encoder（query 编码器），strip
        'module.base_encoder.'，丢 projection head.* -> timm-vit-B。"""
        import torch  # 惰性
        obj = torch.load(src_ckpt, map_location='cpu', weights_only=False)
        sd = obj.get('state_dict', obj)
        prefix = 'module.base_encoder.'
        enc, n = strip_prefix(sd, prefix)
        if n == 0:  # 兼容无 module. 前缀
            prefix = 'base_encoder.'
            enc, n = strip_prefix(sd, prefix)
        assert n > 0, f'[moco] base_encoder 前缀未命中，键样例={list(sd)[:3]}'
        # 丢 projection head（'head.*' 是 MoCo projector，非 backbone；probe 用 backbone 特征）
        enc = {k: v for k, v in enc.items() if not k.startswith('head.')}
        eff = int(eff_bs) if eff_bs is not None else self.official_eff_bs
        # actual eff_bs 影响 steps/images_seen 记录：用 actual eff_bs 重算 meta
        meta = make_meta(self.method, seed, eff, ep, e_eq=self.e_eq,
                         loader_hint=self.loader_hint, arch=self.arch, src_ckpt=src_ckpt,
                         stripped_prefix=prefix + ' (+dropped head.*)',
                         extra=dict(moco_t=self.CONFIG['moco_t'], stop_grad_conv1=True,
                                    n_backbone_keys=len(enc),
                                    official_eff_bs=self.official_eff_bs,
                                    reduced='yes' if eff != self.official_eff_bs else 'no'))
        out = ckpt_out_path(results_dir, self.method, seed, ep)
        return save_unified_ckpt(out, enc, meta)


if __name__ == '__main__':
    p = add_common_args(argparse.ArgumentParser(description='MoCo-v3 recipe (thin wrapper, 不跑训练)'))
    p.add_argument('--total_batch', type=int, default=None, help='moco 全局 batch；默认官方 4096')
    a = p.parse_args()
    r = MoCoRecipe(e_eq=a.e_eq)
    if a.mode == 'print-cmd':
        print(' '.join(r.build_cmd(
            seed=a.seed, output_dir=a.output_dir, data_path=a.data_path,
            batch_size_per_gpu=a.batch_size_per_gpu, accum_iter=a.accum_iter,
            world_size=a.world_size, repo_dir=a.repo_dir, total_batch=a.total_batch)))
    elif a.mode == 'export':
        print(r.export_ckpt(a.src_ckpt, a.ep, a.seed, a.results_dir,
                            eff_bs=a.total_batch))
    else:
        print(f'[MoCo] eff_bs={r.official_eff_bs} budget={r.budget} ckpt_epochs={r.ckpt_epochs()}')
        print(f'       CONFIG={r.CONFIG}')
