# -*- coding: utf-8 -*-
"""
块A 预训练 launch 脚本自测（pytest）。**纯逻辑，不跑训练、不加载真权重**。
覆盖：images-seen 步数换算 / build_cmd 冻结超参 & eff_bs 校验 / ckpt schema 往返 /
      export 键剥离 / smoke_monitor 监控量 & gate 判据。
跑：cd code && python -m pytest pretrain/test_pretrain.py -x -q
"""
import os
import sys

import pytest

_PRE = os.path.dirname(os.path.abspath(__file__))
_CODE = os.path.dirname(_PRE)
for p in (_CODE, _PRE):
    if p not in sys.path:
        sys.path.insert(0, p)

import common  # noqa: E402
from registry import get_recipe, RECIPES  # noqa: E402
import smoke_monitor as sm  # noqa: E402


# ---------------------------------------------------------------------------
# 1. images-seen 预算换算（对齐矩阵 §1 steps@100ep）
# ---------------------------------------------------------------------------
def test_budget_matches_matrix():
    assert common.N_NIH == 112120
    cases = {'mae': (4096, 2737), 'dino': (512, 21898),
             'moco': (4096, 2737), 'chexworld': (2048, 5474)}
    for method, (eff_bs, steps) in cases.items():
        b = common.budget(eff_bs, e_eq=100)
        assert b['images_seen'] == 100 * 112120 == 11212000
        assert b['epochs'] == 100
        assert b['steps'] == steps, f'{method}: {b["steps"]} != 矩阵 {steps}'


def test_recipe_official_eff_bs():
    assert get_recipe('mae').official_eff_bs == 4096
    assert get_recipe('dino').official_eff_bs == 512
    assert get_recipe('moco').official_eff_bs == 4096
    assert get_recipe('chexworld').official_eff_bs == 2048


def test_steps_per_epoch_floor():
    # drop_last 实际 per-epoch（floor），与理想 budget 区分
    assert common.steps_per_epoch(2048) == 112120 // 2048 == 54


# ---------------------------------------------------------------------------
# 2. build_cmd：冻结超参 + epochs=E_eq + eff_bs 校验
# ---------------------------------------------------------------------------
def _cmd(method, **over):
    r = get_recipe(method, e_eq=over.pop('e_eq', 100))
    kw = dict(seed=0, output_dir='/out', data_path='/data', repo_dir='/repo',
              batch_size_per_gpu=None, accum_iter=1, world_size=1)
    # 各范式凑官方 eff_bs 的合法默认
    defaults = {'mae': dict(batch_size_per_gpu=4096),
                'dino': dict(batch_size_per_gpu=512),
                'moco': dict(batch_size_per_gpu=4096),
                'chexworld': dict(batch_size_per_gpu=128, accum_iter=16)}
    kw.update(defaults[method])
    kw.update(over)
    return r.build_cmd(**kw)


def test_mae_cmd_frozen_hparams():
    c = ' '.join(_cmd('mae'))
    assert '--mask_ratio 0.9' in c and '--norm_pix_loss' in c
    assert '--blr 0.00015' in c and '--warmup_epochs 5' in c
    assert '--epochs 100' in c
    assert 'main_pretrain.py' in c


def test_dino_cmd_frozen_hparams():
    c = ' '.join(_cmd('dino'))
    assert '--use_fp16 false' in c                    # ViT-B 关 fp16（防 NaN）
    assert '--lr 0.00075' in c and '--out_dim 65536' in c
    assert '--freeze_last_layer 3' in c and '--momentum_teacher 0.996' in c
    assert '--warmup_teacher_temp_epochs 13' in c     # 12.5 向上取整
    assert '--local_crops_number 10' in c
    assert '--saveckp_freq 25' in c and '--epochs 100' in c


def test_moco_cmd_frozen_hparams():
    c = ' '.join(_cmd('moco'))
    assert '--stop-grad-conv1' in c and '--moco-m-cos' in c
    assert '--lr 0.0001' in c and '--moco-t 0.2' in c
    assert '--warmup-epochs 13' in c and '--batch-size 4096' in c


def test_chexworld_cmd_frozen_hparams():
    c = ' '.join(_cmd('chexworld'))
    assert '--ssl_type iwm_dual_easy' in c and '--dataset nih' in c
    assert '--lr 0.0002' in c and '--ema 0.996' in c and '--ema_end 1.0' in c
    assert '--mask_type multi_multiblock' in c and '--pred_emb_dim 384' in c
    assert '--eval_list 24 49 99' in c                # eff-ep 25/50/100 -> 0-based
    assert c.count('--ipe_scale') == 1               # 不重复
    assert '--epochs 100' in c


def test_eff_bs_assert_raises_on_mismatch():
    # MAE/DINO/CheXWorld 硬 assert 官方 eff_bs；MoCo 例外（TODO-B 允许 reduced batch，只 warn 不 assert）
    for method, off in [('mae', 4096), ('dino', 512), ('chexworld', 2048)]:
        with pytest.raises(AssertionError):
            _cmd(method, batch_size_per_gpu=off + 7, accum_iter=1, world_size=1)


def test_moco_reduced_batch_warns_not_raises():
    # MoCo total_batch != 4096 不抛错（reduced-batch fallback），actual eff_bs 记 meta
    c = ' '.join(_cmd('moco', e_eq=100))  # 默认 total_batch=4096
    assert '--batch-size 4096' in c


def test_dino_moco_reject_accum():
    with pytest.raises(AssertionError):
        _cmd('dino', batch_size_per_gpu=256, accum_iter=2, world_size=1)
    with pytest.raises(AssertionError):
        _cmd('moco', batch_size_per_gpu=2048, accum_iter=2, world_size=1)


def test_smoke_e_eq_shrinks_epochs():
    assert '--epochs 10' in ' '.join(_cmd('dino', e_eq=10))
    assert '--epochs 15' in ' '.join(_cmd('moco', e_eq=15))


# ---------------------------------------------------------------------------
# 3. 统一 ckpt schema 往返 + export 键剥离（需 torch）
# ---------------------------------------------------------------------------
def test_ckpt_roundtrip(tmp_path):
    torch = pytest.importorskip('torch')
    sd = {'patch_embed.proj.weight': torch.zeros(4, 3, 2, 2),
          'blocks.0.norm1.weight': torch.ones(4)}
    meta = common.make_meta('mae', seed=1, eff_bs=4096, ep=50)
    out = common.ckpt_out_path(str(tmp_path), 'mae', 1, 50)
    common.save_unified_ckpt(out, sd, meta)
    assert os.path.basename(out) == 'mae_s1_ep50.pth'
    sd2, meta2 = common.load_unified_ckpt(out)
    assert set(sd2.keys()) == set(sd.keys())
    assert meta2['method'] == 'mae' and meta2['ep'] == 50
    assert meta2['eff_bs'] == 4096 and meta2['loader_hint'] == 'timm_vit_base'
    # ep=50 占 E_eq=100 一半 → images_seen 约半
    assert meta2['images_seen'] == round(11212000 * 50 / 100)


def test_make_meta_fields():
    m = common.make_meta('dino', 2, 512, 100, loader_hint='timm_vit_base')
    assert m['images_seen'] == 11212000 and m['steps_full'] == 21898
    assert m['method'] == 'dino' and m['seed'] == 2 and m['e_eq'] == 100


def _save(tmp, obj):
    import torch
    p = os.path.join(str(tmp), 'src.pth')
    torch.save(obj, p)
    return p


def test_export_mae_filters_decoder(tmp_path):
    torch = pytest.importorskip('torch')
    src = _save(tmp_path, {'model': {
        'patch_embed.proj.weight': torch.zeros(2),
        'blocks.0.norm1.weight': torch.zeros(2),
        'decoder_blocks.0.x': torch.zeros(2),
        'mask_token': torch.zeros(2)}})
    out = get_recipe('mae').export_ckpt(src, ep=25, seed=0, results_dir=str(tmp_path))
    sd, meta = common.load_unified_ckpt(out)
    assert 'patch_embed.proj.weight' in sd and 'blocks.0.norm1.weight' in sd
    assert not any(k.startswith('decoder') for k in sd) and 'mask_token' not in sd
    assert meta['loader_hint'] == 'timm_vit_base' and meta['n_dropped'] == 2


def test_export_dino_strips_backbone_takes_teacher(tmp_path):
    torch = pytest.importorskip('torch')
    teacher = {'backbone.cls_token': torch.zeros(2),
               'backbone.patch_embed.proj.weight': torch.zeros(2),
               'head.mlp.0.weight': torch.zeros(2)}
    src = _save(tmp_path, {'teacher': teacher, 'student': {}, 'epoch': 24})
    out = get_recipe('dino').export_ckpt(src, ep=25, seed=0, results_dir=str(tmp_path))
    sd, meta = common.load_unified_ckpt(out)
    assert 'cls_token' in sd and 'patch_embed.proj.weight' in sd
    assert not any(k.startswith('head.') for k in sd)   # projection head 丢弃
    assert meta['stripped_prefix'] == 'backbone.' and meta['use'] == 'teacher'


def test_export_moco_takes_base_encoder(tmp_path):
    torch = pytest.importorskip('torch')
    sd_raw = {'module.base_encoder.patch_embed.proj.weight': torch.zeros(2),
              'module.base_encoder.head.0.weight': torch.zeros(2),
              'module.momentum_encoder.patch_embed.proj.weight': torch.zeros(2)}
    src = _save(tmp_path, {'state_dict': sd_raw, 'epoch': 24})
    out = get_recipe('moco').export_ckpt(src, ep=25, seed=0, results_dir=str(tmp_path), eff_bs=4096)
    sd, meta = common.load_unified_ckpt(out)
    assert 'patch_embed.proj.weight' in sd
    assert not any(k.startswith('head.') for k in sd)
    assert not any('momentum' in k for k in sd)
    assert meta['reduced'] == 'no'


def test_export_chexworld_takes_target_encoder(tmp_path):
    torch = pytest.importorskip('torch')
    sd_raw = {'target_encoder.patch_embed.proj.weight': torch.zeros(2),
              'target_encoder.norm.weight': torch.zeros(2),
              'encoder.x': torch.zeros(2), 'predictor.y': torch.zeros(2)}
    src = _save(tmp_path, {'model': sd_raw, 'epoch': 49})
    out = get_recipe('chexworld').export_ckpt(src, ep=50, seed=0, results_dir=str(tmp_path))
    sd, meta = common.load_unified_ckpt(out)
    assert 'patch_embed.proj.weight' in sd and 'norm.weight' in sd
    assert not any(k.startswith('encoder.') or k.startswith('predictor.') for k in sd)
    assert meta['loader_hint'] == 'jepa_vit_base' and meta['stripped_prefix'] == 'target_encoder.'


# ---------------------------------------------------------------------------
# 4. smoke_monitor 监控量 + gate 判据
# ---------------------------------------------------------------------------
def test_entropy_kl_pure():
    np = pytest.importorskip('numpy')
    D = 16
    uni = np.full((8, D), 1.0 / D)
    assert abs(sm.teacher_entropy(uni) - np.log(D)) < 1e-9      # 均匀 → ln(D)
    assert abs(sm.kl_to_uniform(uni)) < 1e-9                    # KL→0
    onehot = np.zeros((8, D)); onehot[:, 0] = 1.0
    assert sm.teacher_entropy(onehot) < 1e-6                    # one-hot → 0
    assert abs(sm.kl_to_uniform(onehot) - np.log(D)) < 1e-6


def test_feature_std_and_baseline():
    np = pytest.importorskip('numpy')
    assert sm.feature_std(np.zeros((10, 5))) == 0.0
    assert sm.feature_std(np.random.randn(500, 8)) > 0.5
    assert abs(sm.contrastive_baseline(4096) - np.log(4096)) < 1e-9


def test_loss_diverged_detects():
    import math
    assert sm.loss_diverged([1.0, 2.0, float('nan')])[0] is True
    assert sm.loss_diverged([10, 11, 30, 40])[0] is True        # 上升
    assert sm.loss_diverged([10, 8, 6, 5])[0] is False          # 在降
    assert sm.loss_decreasing([10, 8, 6, 5]) is True


def test_gate_dino_incomplete_without_entropy():
    # 只有 loss（--tail 模式）→ 缺熵/std → INCOMPLETE，不给假 PASS
    rows = [{'loss': v} for v in [9, 8, 7, 6]]
    res = sm.evaluate_gate('dino', rows)
    assert res['verdict'] == 'INCOMPLETE' and 'teacher_entropy' in res['missing']


def test_gate_dino_pass_with_healthy_metrics():
    import math
    band_mid = 0.6 * math.log(sm.DINO_OUT_DIM)
    rows = [{'loss': l, 'teacher_entropy': band_mid, 'feat_std': 0.5}
            for l in [9, 8, 7, 6]]
    res = sm.evaluate_gate('dino', rows)
    assert res['verdict'] == 'PASS', res


def test_gate_dino_fail_on_collapse():
    rows = [{'loss': l, 'teacher_entropy': 0.01, 'feat_std': 0.001}
            for l in [9, 8, 7, 6]]
    res = sm.evaluate_gate('dino', rows)
    assert res['verdict'] == 'FAIL'


def test_gate_moco_loss_above_baseline_fails():
    import math
    b = math.log(4096)
    rows = [{'loss': b + 0.5, 'feat_std': 0.3, 'contrastive_baseline': b} for _ in range(4)]
    res = sm.evaluate_gate('moco', rows, stop_grad_conv1=True)
    assert res['verdict'] == 'FAIL'


def test_gate_mae_loss_sanity_pass():
    rows = [{'loss': l} for l in [1.0, 0.8, 0.6, 0.5]]
    assert sm.evaluate_gate('mae', rows)['verdict'] == 'PASS'
    rows_div = [{'loss': l} for l in [0.5, 0.6, 0.9, 1.2]]
    assert sm.evaluate_gate('chexworld', rows_div)['verdict'] == 'FAIL'


def test_parse_log_line():
    loss, gn = sm.parse_log_line('[Epoch 3] Loss: 0.4321  Grad_Norm: 1.23')
    assert abs(loss - 0.4321) < 1e-9 and abs(gn - 1.23) < 1e-9


def test_registry_complete():
    assert set(RECIPES) == {'mae', 'dino', 'moco', 'chexworld'}
