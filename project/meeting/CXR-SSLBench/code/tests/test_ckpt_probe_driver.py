# -*- coding: utf-8 -*-
"""ckpt_probe_driver 单测：ckpt 文件名解析 + 扫描过滤/排序（纯文件名逻辑，无 GPU/repo）。"""
import ckpt_probe_driver as CK


def test_parse_ckpt_name_ok():
    info = CK.parse_ckpt_name('mae_s0_ep25.pth')
    assert info['method'] == 'mae'
    assert info['pretrain_seed'] == 0
    assert info['pretrain_ep'] == 25
    assert info['stem'] == 'mae_s0_ep25'


def test_parse_ckpt_name_method_with_underscore():
    # method 含下划线（如 moco_v3）也能解析（贪婪到最后的 _s<d>_ep<d>）
    info = CK.parse_ckpt_name('moco_v3_s2_ep100.pth')
    assert info['method'] == 'moco_v3'
    assert info['pretrain_seed'] == 2
    assert info['pretrain_ep'] == 100


def test_parse_ckpt_name_bad():
    assert CK.parse_ckpt_name('random_weights.pth') is None
    assert CK.parse_ckpt_name('mae_seed0_ep25.pth') is None


def test_scan_ckpts_filters_and_sorts(tmp_path):
    for fn in ['mae_s0_ep25.pth', 'mae_s0_ep100.pth', 'dino_s1_ep50.pth',
               'mae_s0_ep200.pth', 'junk.pth', 'notes.txt']:
        (tmp_path / fn).write_bytes(b'x')
    got = CK.scan_ckpts(pretrain_dir=str(tmp_path), epochs=[25, 50, 100])
    stems = [info['stem'] for _, info in got]
    # ep200 被默认 epochs 过滤；junk/notes 不匹配；按 (method,seed,ep) 排序
    assert stems == ['dino_s1_ep50', 'mae_s0_ep25', 'mae_s0_ep100']


def test_scan_ckpts_method_filter(tmp_path):
    for fn in ['mae_s0_ep25.pth', 'dino_s0_ep25.pth']:
        (tmp_path / fn).write_bytes(b'x')
    got = CK.scan_ckpts(pretrain_dir=str(tmp_path), epochs=[25], methods=['dino'])
    assert [i['stem'] for _, i in got] == ['dino_s0_ep25']


def test_csv_fields_match_eval_grid():
    # 驱动输出列须与 eval_grid 扩展 schema 一致（15 列）
    assert CK.CSV_FIELDS[-3:] == ['pretrain_seed', 'pretrain_ep', 'images_seen']
    assert len(CK.CSV_FIELDS) == 15
