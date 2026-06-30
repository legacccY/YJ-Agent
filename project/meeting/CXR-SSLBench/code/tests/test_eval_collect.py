# -*- coding: utf-8 -*-
"""eval_collect 单测：normalize_row 回填 pretrain 列、collect_to_grid 15 列 schema + 去重。"""
import csv

import eval_collect as EC


def test_eval_grid_schema_15_cols():
    assert EC.EVAL_GRID_FIELDS == EC.CSV_FIELDS + ['pretrain_seed', 'pretrain_ep', 'images_seen']
    assert len(EC.EVAL_GRID_FIELDS) == 15


def test_normalize_row_fills_from_ckpt_name():
    row = {'backbone': 'mae_s1_ep50', 'probe_type': 'linear', 'label_frac': '10',
           'domain': 'nih', 'split': 'probe_train_10pct.txt', 'mAUC': '80.0',
           'per_class_auc': '[]', 'seed': '0', 'n_train': '11', 'n_test': '25596',
           'seconds': '1.0', 'timestamp': 'now'}
    nr = EC.normalize_row(row)
    assert set(nr.keys()) == set(EC.EVAL_GRID_FIELDS)
    assert nr['pretrain_seed'] == 1
    assert nr['pretrain_ep'] == 50
    assert nr['images_seen'] == ''   # ckpt 名无 images_seen，留空


def test_normalize_row_non_pretrained_backbone_empty():
    row = {'backbone': 'imagenet_sup_vitb', 'probe_type': 'linear', 'label_frac': '1',
           'domain': 'nih', 'split': 's', 'mAUC': '70', 'per_class_auc': '[]', 'seed': '0',
           'n_train': '1', 'n_test': '2', 'seconds': '0', 'timestamp': 't'}
    nr = EC.normalize_row(row)
    assert nr['pretrain_seed'] == ''
    assert nr['pretrain_ep'] == ''


def test_normalize_row_keeps_existing_extended_cols():
    row = {'backbone': 'dino_s2_ep100', 'pretrain_seed': '2', 'pretrain_ep': '100',
           'images_seen': '11210000', 'probe_type': 'knn', 'label_frac': '100',
           'domain': 'nih', 'split': 's', 'mAUC': '75', 'per_class_auc': '[]', 'seed': '0',
           'n_train': '1', 'n_test': '2', 'seconds': '0', 'timestamp': 't'}
    nr = EC.normalize_row(row)
    assert str(nr['pretrain_seed']) == '2'
    assert str(nr['images_seen']) == '11210000'


def _write_csv(path, fields, rows):
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def test_collect_to_grid_merges_and_dedups(tmp_path):
    base = EC.CSV_FIELDS
    s1 = tmp_path / 's1.csv'
    s2 = tmp_path / 's2.csv'
    r1 = dict(backbone='chexworld', probe_type='linear', label_frac='10', domain='nih',
              split='probe_train_10pct.txt', mAUC='80', per_class_auc='[]', seed='0',
              n_train='1', n_test='2', seconds='1', timestamp='t1')
    r2 = dict(r1, backbone='medical_mae', mAUC='78')
    # s2 含与 r1 同 cell 的更新行（后者覆盖）+ 一个 ckpt 命名行
    r1b = dict(r1, mAUC='81', timestamp='t2')
    r3 = dict(r1, backbone='mae_s0_ep25', mAUC='70')
    _write_csv(s1, base, [r1, r2])
    _write_csv(s2, base, [r1b, r3])

    out = tmp_path / 'eval_grid.csv'
    n = EC.collect_to_grid([str(s1), str(s2)], str(out))
    # 唯一 cell：chexworld(去重后1) + medical_mae(1) + mae_s0_ep25(1) = 3
    assert n == 3

    with open(out, newline='') as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == EC.EVAL_GRID_FIELDS
        recs = list(reader)
    assert len(recs) == 3
    by_bk = {r['backbone']: r for r in recs}
    # chexworld 被 s2 的更新行覆盖
    assert by_bk['chexworld']['mAUC'] == '81'
    # ckpt 命名行回填 pretrain 列
    assert by_bk['mae_s0_ep25']['pretrain_seed'] == '0'
    assert by_bk['mae_s0_ep25']['pretrain_ep'] == '25'
