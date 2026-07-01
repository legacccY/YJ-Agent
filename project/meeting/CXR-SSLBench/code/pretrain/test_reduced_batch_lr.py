# -*- coding: utf-8 -*-
"""
reduced-batch + lr 线性缩放自测（pytest）。**纯逻辑，不跑训练、不加载真权重**。
路 A：4×4090 装不下 DINO/MoCo 官方 eff_bs → reduced eff_bs + lr 按 bs 线性缩放（lr=official_lr×eff/official）、
images-seen 不变（epochs=E_eq 恒定，步数随 eff 放大）。MAE/CheXWorld 用 accum 凑满 official → 不触发缩放。
跑：cd code && python -m pytest pretrain/test_reduced_batch_lr.py -x -q
"""
import os
import sys

import pytest

_PRE = os.path.dirname(os.path.abspath(__file__))
_CODE = os.path.dirname(_PRE)
for p in (_CODE, _PRE):
    if p not in sys.path:
        sys.path.insert(0, p)

from registry import get_recipe  # noqa: E402


def _build(method, **kw):
    """直接拼 cmd（默认 e_eq=100，full 凑官方 eff_bs 的合法默认，override 走 kw）。"""
    r = get_recipe(method, e_eq=kw.pop('e_eq', 100))
    base = dict(seed=0, output_dir='/out', data_path='/data', repo_dir='/repo',
                batch_size_per_gpu=None, accum_iter=1, world_size=1)
    full = {'mae': dict(batch_size_per_gpu=4096),
            'dino': dict(batch_size_per_gpu=512),
            'moco': dict(batch_size_per_gpu=4096),
            'chexworld': dict(batch_size_per_gpu=128, accum_iter=16)}
    base.update(full[method])
    base.update(kw)
    return r, ' '.join(r.build_cmd(**base))


# ---------------------------------------------------------------------------
# 1. scaled_lr 线性缩放公式（基类单元）
# ---------------------------------------------------------------------------
def test_scaled_lr_formula():
    dino = get_recipe('dino')
    assert dino.scaled_lr(512) == 0.00075                       # eff==official → 不缩放
    assert dino.scaled_lr(32) == 0.00075 * 32 / 512             # reduced → 线性
    assert dino.scaled_lr(256) == 0.00075 * 256 / 512
    moco = get_recipe('moco')
    assert moco.scaled_lr(4096) == 1.0e-4
    assert moco.scaled_lr(128) == 1.0e-4 * 128 / 4096
    assert moco.scaled_lr(256) == 1.0e-4 * 256 / 4096


def test_official_lr_fields_set():
    assert get_recipe('dino').official_lr == 0.00075
    assert get_recipe('moco').official_lr == 1.0e-4
    assert get_recipe('mae').official_lr == 2.4e-3
    assert get_recipe('chexworld').official_lr == 2e-4


# ---------------------------------------------------------------------------
# 2. DINO reduced：不再 assert 崩 + lr 正确缩放 + images-seen 不变
# ---------------------------------------------------------------------------
def test_dino_reduced_eff32_lr_scaled(capsys):
    # eff_bs=32（reduced，官方 512）→ 不抛错；lr=0.00075×32/512
    r, c = _build('dino', batch_size_per_gpu=32, accum_iter=1, world_size=1)
    expect_lr = str(0.00075 * 32 / 512)        # 4.6875e-05
    assert f'--lr {expect_lr}' in c, c
    assert '--batch_size_per_gpu 32' in c
    assert '--epochs 100' in c                  # images-seen 不变：epochs=E_eq 恒定（步数按 eff 放大）
    err = capsys.readouterr().err
    assert '[dino][WARN]' in err and 'reduced eff_bs=32' in err and '官方 512' in err


def test_dino_reduced_4gpu_128(capsys):
    # 4 卡 × 32/gpu = eff 128（reduced）→ lr=0.00075×128/512
    r, c = _build('dino', batch_size_per_gpu=32, accum_iter=1, world_size=4)
    assert f'--lr {str(0.00075 * 128 / 512)}' in c
    assert '--nproc_per_node 4' in c
    assert 'reduced eff_bs=128' in capsys.readouterr().err


def test_dino_full_eff512_lr_unchanged(capsys):
    r, c = _build('dino', batch_size_per_gpu=512, accum_iter=1, world_size=1)
    assert '--lr 0.00075' in c                  # eff==official → 官方 lr 不缩放
    assert capsys.readouterr().err == ''        # full 不打 WARN


def test_dino_over_official_still_raises():
    with pytest.raises(AssertionError):
        _build('dino', batch_size_per_gpu=519, accum_iter=1, world_size=1)  # eff>512


# ---------------------------------------------------------------------------
# 3. MoCo reduced：--batch-size 跟实际 eff_bs（非硬编码 4096）+ lr 缩放
# ---------------------------------------------------------------------------
def test_moco_reduced_eff128_batchsize_and_lr(capsys):
    # 4 卡 × 32/gpu = eff 128（reduced，官方 4096）→ --batch-size 128（非 4096）、lr=1e-4×128/4096
    r, c = _build('moco', batch_size_per_gpu=32, accum_iter=1, world_size=4)
    assert '--batch-size 128' in c and '--batch-size 4096' not in c
    assert f'--lr {str(1.0e-4 * 128 / 4096)}' in c   # 3.125e-06
    assert '--epochs 100' in c
    err = capsys.readouterr().err
    assert '[moco][WARN]' in err and 'reduced eff_bs=128' in err


def test_moco_batchsize_follows_actual_eff_not_hardcoded():
    # 修「无视 batch_size_per_gpu」bug：BPG=64 × 4 卡 = eff 256 → --batch-size 256（非 4096）
    r, c = _build('moco', batch_size_per_gpu=64, accum_iter=1, world_size=4)
    assert '--batch-size 256' in c
    assert f'--lr {str(1.0e-4 * 256 / 4096)}' in c


def test_moco_full_eff4096_unchanged(capsys):
    r, c = _build('moco', batch_size_per_gpu=4096, accum_iter=1, world_size=1)
    assert '--batch-size 4096' in c and '--lr 0.0001' in c
    assert capsys.readouterr().err == ''


def test_moco_total_batch_override(capsys):
    # 显式 total_batch override（legacy 直接指定全局 batch）仍生效：256 → --batch-size 256 + lr 缩放
    r, c = _build('moco', batch_size_per_gpu=4096, accum_iter=1, world_size=1, total_batch=256)
    assert '--batch-size 256' in c
    assert f'--lr {str(1.0e-4 * 256 / 4096)}' in c
    assert 'reduced eff_bs=256' in capsys.readouterr().err


def test_moco_over_official_raises():
    with pytest.raises(AssertionError):
        _build('moco', batch_size_per_gpu=8192, accum_iter=1, world_size=1)  # eff>4096


# ---------------------------------------------------------------------------
# 4. MAE / CheXWorld：accum 凑满 official → eff==official 走不缩放分支，lr 不变、不 WARN
# ---------------------------------------------------------------------------
def test_mae_full_accum_no_scaling(capsys):
    # 256/gpu × accum16 × 1 卡 = eff 4096（凑满官方）→ blr 不变、不 WARN
    r, c = _build('mae', batch_size_per_gpu=256, accum_iter=16, world_size=1)
    assert '--blr 0.00015' in c                 # MAE 注入 blr（repo 内部按 eff/256 缩放），不动
    assert '--batch_size 256' in c and '--accum_iter 16' in c
    assert capsys.readouterr().err == ''        # eff==official → 无 reduced WARN


def test_chexworld_full_accum_no_scaling(capsys):
    # 128/gpu × accum16 × 1 卡 = eff 2048（凑满官方）→ lr 绝对 2e-4 不变、不 WARN
    r, c = _build('chexworld', batch_size_per_gpu=128, accum_iter=16, world_size=1)
    assert '--lr 0.0002' in c
    assert capsys.readouterr().err == ''


def test_mae_over_official_raises():
    with pytest.raises(AssertionError):
        _build('mae', batch_size_per_gpu=4103, accum_iter=1, world_size=1)  # eff>4096
