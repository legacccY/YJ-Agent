# -*- coding: utf-8 -*-
"""vindr_loader 单测：3 放射师聚合(union/majority)、共享类映射、test 解析、csv 编码 fallback、surrogate id。"""
import numpy as np

import vindr_loader as V

# 自定义小 shared_map：A=单列, B=两列 OR（验 OR-of-multiple）
SMAP = [('A', ['ColA']), ('B', ['ColB', 'ColC'])]


def _row(iid, rad, a, b, c):
    return {'image_id': iid, 'rad_id': rad, 'ColA': str(a), 'ColB': str(b), 'ColC': str(c)}


def test_aggregate_union_vs_majority_differ():
    rows = [
        # img1: A 阳 2/3, B(ColB|ColC) 阳 2/3
        _row('img1', 'R1', 1, 0, 0),
        _row('img1', 'R2', 1, 1, 0),
        _row('img1', 'R3', 0, 0, 1),
        # img2: A 阳 1/3（union->1，majority->0）；B 全 0
        _row('img2', 'R1', 1, 0, 0),
        _row('img2', 'R2', 0, 0, 0),
        _row('img2', 'R3', 0, 0, 0),
    ]
    uni = V.aggregate_train_labels(rows, shared_map=SMAP, method='union')
    maj = V.aggregate_train_labels(rows, shared_map=SMAP, method='majority')
    # img1
    assert uni['img1'].tolist() == [1.0, 1.0]
    assert maj['img1'].tolist() == [1.0, 1.0]
    # img2：union A=1, majority A=0（关键区分）
    assert uni['img2'].tolist() == [1.0, 0.0]
    assert maj['img2'].tolist() == [0.0, 0.0]


def test_or_of_multiple_vindr_cols():
    # B = ColB OR ColC：仅 ColC 阳也算 B 阳
    rows = [_row('x', 'R1', 0, 0, 1)]
    uni = V.aggregate_train_labels(rows, shared_map=SMAP, method='union')
    assert uni['x'].tolist() == [0.0, 1.0]


def test_parse_test_labels():
    rows = [
        {'image_id': 't1', 'ColA': '1', 'ColB': '0', 'ColC': '0'},
        {'image_id': 't2', 'ColA': '0', 'ColB': '0', 'ColC': '1'},
    ]
    out = V.parse_test_labels(rows, shared_map=SMAP)
    assert out['t1'].tolist() == [1.0, 0.0]
    assert out['t2'].tolist() == [0.0, 1.0]


def test_default_shared_map_11_classes_and_mapping():
    names = V.shared_class_names()
    assert len(names) == 11
    d = dict(V.SHARED_CLASS_MAP_DEFAULT)
    assert d['Effusion'] == ['Pleural effusion']
    assert d['Fibrosis'] == ['Pulmonary fibrosis']
    assert d['Pleural_Thickening'] == ['Pleural thickening']
    assert d['Mass_Nodule'] == ['Nodule/Mass']   # NIH Mass∪Nodule ↔ VinDr 单列


def test_imgid_to_int_stable_and_int64_safe():
    iid = '000434271f63a053c4128a0ba6352c7f'
    v = V.imgid_to_int(iid)
    assert isinstance(v, int)
    assert v == int(iid[:15], 16)
    assert v < 2 ** 63   # int64 安全


def test_load_vindr_labels_train_and_test_via_tmp_csv(tmp_path):
    import csv as _csv
    # train csv（含 rad_id，2 图×3 rad）
    train_csv = tmp_path / 'image_labels_train.csv'
    with open(train_csv, 'w', newline='', encoding='utf-8') as f:
        w = _csv.writer(f)
        w.writerow(['image_id', 'rad_id', 'ColA', 'ColB', 'ColC'])
        for iid in ('imgA', 'imgB'):
            for r in ('R1', 'R2', 'R3'):
                w.writerow([iid, r, 1, 0, 0])
    ids, labels, names = V.load_vindr_labels('train', aggregate='union', shared_map=SMAP,
                                             labels_csv=str(train_csv))
    assert ids == ['imgA', 'imgB']
    assert labels.shape == (2, 2)
    assert names == ['A', 'B']

    # test csv（无 rad_id，latin1 编码验 fallback）
    test_csv = tmp_path / 'image_labels_test.csv'
    with open(test_csv, 'w', newline='', encoding='latin1') as f:
        w = _csv.writer(f)
        w.writerow(['image_id', 'ColA', 'ColB', 'ColC'])
        w.writerow(['t1', 1, 1, 0])
    ids2, labels2, _ = V.load_vindr_labels('test', shared_map=SMAP, labels_csv=str(test_csv))
    assert ids2 == ['t1']
    assert labels2.tolist() == [[1.0, 1.0]]
