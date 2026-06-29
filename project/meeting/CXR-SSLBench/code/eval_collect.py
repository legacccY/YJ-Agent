# -*- coding: utf-8 -*-
"""
Probe-only 驱动：只读**已缓存**的 pooled 特征跑 linear probe，写结果 CSV。
不抽特征、不碰 GPU、不触发 gpu_slot hook（纯 numpy/CPU）。
用法：先用 extract_features.py 把所需 (backbone, split) 的 pooled 缓存抽好，再跑本脚本。
    python probe_only.py --backbones chexworld imagenet_sup_vitb --label_fracs 1 10
缺缓存的 (backbone, frac) 自动跳过并打印 SKIP（不抽取）。
"""
import os, csv, json, argparse, datetime
import paths, extract_features as EF, probes as P

CSV_FIELDS = ['backbone', 'probe_type', 'label_frac', 'domain', 'split',
              'mAUC', 'per_class_auc', 'seed', 'n_train', 'n_test', 'seconds', 'timestamp']


def _now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _pooled_path(backbone, domain, split):
    return os.path.join(paths.CACHE_DIR, EF.cache_basename(backbone, domain, split, 'pooled') + '.npz')


def append_row(csv_path, row):
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    exists = os.path.exists(csv_path)
    with open(csv_path, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not exists:
            w.writeheader()
        w.writerow(row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--backbones', nargs='+', default=['chexworld', 'imagenet_sup_vitb'])
    ap.add_argument('--label_fracs', nargs='+', type=int, default=[1, 10])
    ap.add_argument('--domain', default='nih')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--out_csv', default=os.path.join(paths.RESULTS_DIR, 'pilot_results.csv'))
    args = ap.parse_args()

    test_split = paths.TEST_SPLIT
    te_cache = {}
    for bk in args.backbones:
        tp = _pooled_path(bk, args.domain, test_split)
        if not os.path.exists(tp):
            print(f'[SKIP] {bk}: test 缓存缺 {tp}')
            continue
        te = EF.load_pooled_cache(tp)
        for frac in args.label_fracs:
            tr_split = paths.SPLIT_BY_FRAC[frac]
            trp = _pooled_path(bk, args.domain, tr_split)
            if not os.path.exists(trp):
                print(f'[SKIP] {bk}/{frac}%: train 缓存缺 {trp}')
                continue
            tr = EF.load_pooled_cache(trp)
            res = P.run_linear_probe(tr, te, seed=args.seed, device='cpu')
            row = dict(backbone=bk, probe_type='linear', label_frac=frac, domain=args.domain,
                       split=tr_split, mAUC=round(res['mAUC'], 4),
                       per_class_auc=json.dumps([None if (v != v) else round(float(v), 4)
                                                 for v in res['per_class_auc']]),
                       seed=args.seed, n_train=res['n_train'], n_test=res['n_test'],
                       seconds=res['seconds'], timestamp=_now())
            append_row(args.out_csv, row)
            print(f'[OK] {bk}/linear/{frac}% mAUC={res["mAUC"]:.4f} (n_train={res["n_train"]})')


if __name__ == '__main__':
    main()
