# -*- coding: utf-8 -*-
"""
Pilot 编排器：grid(backbone × label_frac × probe_type × domain) -> 抽特征(缓存) -> 跑 probe -> 写结果 CSV。

结果 CSV 列（固定，单写者，勿并发写同一文件）：
    backbone, probe_type, label_frac, domain, split, mAUC, per_class_auc, seed, n_train, n_test, seconds, timestamp
per_class_auc = json 字符串（14 个 float，退化类为 NaN -> json 写 null）。

⚠️ 本脚本会跑 ViT forward + probe 训练（GPU）。**coder 不跑，交主线**。Phase 0 走 CheXWorld 单 backbone
先验苗头；其余 backbone 待 researcher 回填权重（load_backbone 抛 NotImplementedError 会被本脚本捕获跳过并记 skip）。
"""
import os
import csv
import json
import argparse
import datetime

import paths
import extract_features as EF
import probes as P
import backbones

CSV_FIELDS = ['backbone', 'probe_type', 'label_frac', 'domain', 'split',
              'mAUC', 'per_class_auc', 'seed', 'n_train', 'n_test', 'seconds', 'timestamp']


def _now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _json_per_class(per_class):
    # NaN -> null（json 合法）
    return json.dumps([None if (v != v) else round(float(v), 4) for v in per_class])


def append_row(csv_path, row):
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    exists = os.path.exists(csv_path)
    with open(csv_path, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not exists:
            w.writeheader()
        w.writerow(row)


def _ensure_pooled(backbone, domain, split, device, batch_size, num_workers):
    return EF.extract(backbone, domain, split, ftype='pooled', device=device,
                      batch_size=batch_size, num_workers=num_workers)


def _ensure_tokens(backbone, domain, split, device, batch_size, num_workers, max_gb, force):
    return EF.extract(backbone, domain, split, ftype='tokens', device=device,
                      batch_size=batch_size, num_workers=num_workers, max_gb=max_gb, force=force)


def run(backbones_list, label_fracs, probe_types, domain, seed, device,
        out_csv, batch_size, num_workers, max_gb, force):
    test_split = paths.TEST_SPLIT
    for bk in backbones_list:
        try:
            _ = backbones.load_backbone(bk, device=device)  # 提前探测权重就位（失败即 skip 全 backbone）
        except NotImplementedError as e:
            print(f'[run_pilot][SKIP] backbone={bk} 未就位：{e}')
            continue
        except Exception as e:
            print(f'[run_pilot][SKIP] backbone={bk} 加载失败：{e}')
            continue

        for ptype in probe_types:
            for frac in label_fracs:
                train_split = paths.SPLIT_BY_FRAC[frac]
                try:
                    if ptype == 'linear':
                        tr = EF.load_pooled_cache(
                            _ensure_pooled(bk, domain, train_split, device, batch_size, num_workers))
                        te = EF.load_pooled_cache(
                            _ensure_pooled(bk, domain, test_split, device, batch_size, num_workers))
                        res = P.run_linear_probe(tr, te, seed=seed, device=device)
                    elif ptype == 'attentive':
                        fb_dim = backbones.load_backbone(bk, device=device).feature_dim
                        tr = EF.load_tokens_cache(
                            _ensure_tokens(bk, domain, train_split, device, batch_size, num_workers, max_gb, force))
                        te = EF.load_tokens_cache(
                            _ensure_tokens(bk, domain, test_split, device, batch_size, num_workers, max_gb, force))
                        res = P.run_attentive_probe(tr, te, feature_dim=fb_dim, seed=seed, device=device)
                    elif ptype == 'finetune':
                        print(f'[run_pilot] finetune 不在本编排器内跑（复现零偏离）；用 run_finetune.py，见 README_pilot.md。')
                        continue
                    else:
                        raise ValueError(f'未知 probe_type={ptype}')
                except Exception as e:
                    print(f'[run_pilot][ERR] {bk}/{ptype}/{frac}%: {e}')
                    continue

                row = dict(backbone=bk, probe_type=ptype, label_frac=frac, domain=domain,
                           split=train_split, mAUC=round(res['mAUC'], 4),
                           per_class_auc=_json_per_class(res['per_class_auc']),
                           seed=seed, n_train=res['n_train'], n_test=res['n_test'],
                           seconds=res['seconds'], timestamp=_now())
                append_row(out_csv, row)
                print(f'[run_pilot][OK] {bk}/{ptype}/{frac}% mAUC={res["mAUC"]:.4f} '
                      f'(n_train={res["n_train"]}, {res["seconds"]}s) -> {out_csv}')


def main():
    ap = argparse.ArgumentParser('CXR-SSLBench Phase 0 pilot orchestrator')
    ap.add_argument('--backbones', nargs='+', default=['chexworld'])
    ap.add_argument('--label_fracs', nargs='+', type=int, default=[1, 10, 100])
    ap.add_argument('--probes', nargs='+', default=['linear', 'attentive'],
                    choices=['linear', 'attentive', 'finetune'])
    ap.add_argument('--domain', default='nih', choices=['nih', 'vindr'])
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--device', default='cuda')
    ap.add_argument('--out_csv', default=os.path.join(paths.RESULTS_DIR, 'pilot_results.csv'))
    ap.add_argument('--batch_size', type=int, default=128)
    ap.add_argument('--num_workers', type=int, default=4)
    ap.add_argument('--max_gb', type=float, default=25.0)
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()
    run(args.backbones, args.label_fracs, args.probes, args.domain, args.seed, args.device,
        args.out_csv, args.batch_size, args.num_workers, args.max_gb, args.force)


if __name__ == '__main__':
    main()
