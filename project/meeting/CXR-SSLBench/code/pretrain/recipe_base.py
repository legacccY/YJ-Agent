# -*- coding: utf-8 -*-
"""
recipe 基类 —— 4 范式 launch 脚本共用骨架（薄包装官方 repo，R4 零偏离）。

每个 recipe_*.py 提供：
  - CONFIG: 冻结超参 dict（值=矩阵 §1 + SSL_RECIPES，**一字不改**；查不到处标 TODO 不臆想）
  - build_cmd(...): 拼官方训练入口的 argv（注入冻结超参 + epochs=E_eq + 中间 ckpt 存盘机制 + seed）
  - export_ckpt(...): 官方 ckpt -> 统一 schema（抽 backbone + 记 meta）
recipe 自身**不实现 SSL 算法、不跑训练**。主线 clone 官方 repo 后经 submit 跑。
"""
import argparse

from common import budget, INTERMEDIATE_EPS


class Recipe:
    method = None            # 'mae'|'dino'|'moco'|'chexworld'
    official_eff_bs = None   # 矩阵 §1 官方 eff_bs（recipe 强制不变，HPC 用 accum 凑）
    entry = None             # 官方训练入口脚本名（repo 内相对）
    loader_hint = 'timm_vit_base'  # block B 建模型用：MAE/DINO/MoCo=timm_vit_base，CheXWorld=jepa_vit_base
    arch = 'vit_base_patch16_224'

    def __init__(self, e_eq=100):
        self.e_eq = e_eq
        self.budget = budget(self.official_eff_bs, e_eq=e_eq)

    # -- 子类实现 --
    def build_cmd(self, **kw):
        raise NotImplementedError

    def export_ckpt(self, src_ckpt, ep, seed, results_dir):
        raise NotImplementedError

    # -- 共用：校验 eff_bs 凑对（HPC accum/多卡组合必须等于官方 eff_bs，否则 lr 语义被偷换）--
    def assert_eff_bs(self, batch_size_per_gpu, accum_iter, world_size):
        eff = int(batch_size_per_gpu) * int(accum_iter) * int(world_size)
        assert eff == self.official_eff_bs, (
            f'[{self.method}] eff_bs={eff} != 官方 {self.official_eff_bs} '
            f'(batch/gpu={batch_size_per_gpu} × accum={accum_iter} × gpus={world_size})。'
            f'矩阵 §1 铁律：保官方 eff_bs，lr 不 rescale。请调 accum_iter/batch 凑回官方值。')
        return eff

    def ckpt_epochs(self):
        """本 recipe 实际能落盘的中间 eff-epoch 列表。子类可覆盖（官方 repo 原生存盘 cadence 不同）。"""
        return list(INTERMEDIATE_EPS)


def add_common_args(p: argparse.ArgumentParser):
    """各 recipe CLI 共用参数。"""
    p.add_argument('--mode', choices=['print-cmd', 'export', 'info'], default='info')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--e_eq', type=int, default=100, help='images-seen 预算 E_eq（matrix 默认 100）')
    p.add_argument('--repo_dir', default=None, help='官方 repo clone 路径（HPC）')
    p.add_argument('--data_path', default=None, help='NIH 训练图目录（默认走 paths.NIH_IMAGES_DIR）')
    p.add_argument('--output_dir', default=None, help='官方 repo 原生 ckpt/日志输出目录')
    p.add_argument('--results_dir', default=None, help='harness results/ 目录（统一 ckpt + state.json 落处）')
    p.add_argument('--batch_size_per_gpu', type=int, default=None)
    p.add_argument('--accum_iter', type=int, default=1)
    p.add_argument('--world_size', type=int, default=1, help='参与训练的 GPU 数')
    # export 模式：
    p.add_argument('--src_ckpt', default=None, help='export 模式：官方原生 ckpt 路径')
    p.add_argument('--ep', type=int, default=None, help='export 模式：本 ckpt 的 eff-epoch（25/50/100）')
    return p
