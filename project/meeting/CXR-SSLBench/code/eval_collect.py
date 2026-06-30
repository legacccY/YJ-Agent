# -*- coding: utf-8 -*-
"""
eval_collect —— 两种模式：

  mode=probe（默认，原行为不变）：只读**已缓存**的 pooled 特征跑 linear probe，写结果 CSV。
    不抽特征、不碰 GPU（纯 numpy/CPU）。先用 extract_features.py 抽好缓存，再跑本脚本。
        python eval_collect.py --backbones chexworld imagenet_sup_vitb --label_fracs 1 10
    缺缓存的 (backbone, frac) 自动跳过并打印 SKIP。

  mode=collect：汇全评估网格到 results/eval_grid.csv（INTERFACE §3 扩展 schema）。
    把多个来源 CSV（pilot_hpc.csv / pilot_results.csv / probe_vs_budget.csv / vindr 结果 …）的行
    规范化为统一 15 列 schema = 现有 12 列 + 新列 (pretrain_seed, pretrain_ep, images_seen)，合并去重写一份。
    源行缺 pretrain_* 时：若 backbone 名匹配中间 ckpt 命名(<method>_s<seed>_ep<E>) 则从名字解析回填，否则留空
    （imagenet_sup/scratch 等非自训 backbone 本就无 pretrain 预算轴 -> 空）。
        python eval_collect.py --mode collect --sources results/pilot_hpc.csv results/probe_vs_budget.csv \
            --out_csv results/eval_grid.csv
"""
import os, csv, json, argparse, datetime
import paths
from ckpt_probe_driver import parse_ckpt_name
# extract_features / probes 惰性 import（仅 mode=probe 才需 repo/torch 栈；mode=collect 纯 csv）

# 现有 12 列基 schema（pilot_hpc.csv / pilot_results.csv 同口径）
CSV_FIELDS = ['backbone', 'probe_type', 'label_frac', 'domain', 'split',
              'mAUC', 'per_class_auc', 'seed', 'n_train', 'n_test', 'seconds', 'timestamp']

# 扩展 15 列 schema（INTERFACE §3）= 基 12 + A′ 受控重训预算轴 3 列
EVAL_GRID_EXTRA = ['pretrain_seed', 'pretrain_ep', 'images_seen']
EVAL_GRID_FIELDS = CSV_FIELDS + EVAL_GRID_EXTRA


def _now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _pooled_path(backbone, domain, split):
    import extract_features as EF
    return os.path.join(paths.CACHE_DIR, EF.cache_basename(backbone, domain, split, 'pooled') + '.npz')


def append_row(csv_path, row):
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    exists = os.path.exists(csv_path)
    with open(csv_path, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not exists:
            w.writeheader()
        w.writerow(row)


# ---------------------------------------------------------------------------
# mode=collect：汇全网格 -> eval_grid.csv（扩展 15 列 schema）
# ---------------------------------------------------------------------------
def normalize_row(row):
    """把任意来源行（12 列基 或 已含扩展列）规范化为 15 列 dict。
    缺 pretrain_* 时：backbone 名匹配中间 ckpt 命名则解析回填，否则留空字符串。"""
    out = {k: row.get(k, '') for k in EVAL_GRID_FIELDS}
    bk = str(row.get('backbone', ''))
    # 已有扩展列就用源值；否则尝试从 ckpt 名解析
    if not str(out.get('pretrain_seed', '')).strip() or not str(out.get('pretrain_ep', '')).strip():
        info = parse_ckpt_name(bk + '.pth')
        if info is not None:
            if not str(out.get('pretrain_seed', '')).strip():
                out['pretrain_seed'] = info['pretrain_seed']
            if not str(out.get('pretrain_ep', '')).strip():
                out['pretrain_ep'] = info['pretrain_ep']
    return out


def _row_key(r):
    """去重键：唯一定位一个评估 cell（含预算轴）。"""
    return (r['backbone'], r['probe_type'], str(r['label_frac']), r['domain'], r['split'],
            str(r['seed']), str(r['pretrain_seed']), str(r['pretrain_ep']))


def collect_to_grid(sources, out_csv, dedup=True):
    """读多个来源 CSV，规范化为 15 列，合并(可去重)写 eval_grid.csv。返回写出行数。"""
    seen = {}
    order = []
    for src in sources:
        if not os.path.exists(src):
            print(f'[collect][SKIP] 来源不存在：{src}')
            continue
        with open(src, 'r', newline='') as f:
            for raw in csv.DictReader(f):
                nr = normalize_row(raw)
                k = _row_key(nr)
                if dedup and k in seen:
                    seen[k] = nr  # 后者覆盖（更新结果）
                else:
                    if k not in seen:
                        order.append(k)
                    seen[k] = nr
        print(f'[collect] 读入 {src}')
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=EVAL_GRID_FIELDS)
        w.writeheader()
        for k in order:
            w.writerow(seen[k])
    print(f'[collect] 写出 {len(order)} 行 -> {out_csv}（schema={EVAL_GRID_FIELDS}）')
    return len(order)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', default='probe', choices=['probe', 'collect'])
    ap.add_argument('--backbones', nargs='+', default=['chexworld', 'imagenet_sup_vitb'])
    ap.add_argument('--label_fracs', nargs='+', type=int, default=[1, 10])
    ap.add_argument('--domain', default='nih')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--sources', nargs='+', default=None, help='mode=collect 的来源 CSV 列表')
    ap.add_argument('--out_csv', default=None)
    args = ap.parse_args()

    if args.mode == 'collect':
        sources = args.sources or [os.path.join(paths.RESULTS_DIR, n) for n in
                                   ('pilot_hpc.csv', 'pilot_results.csv', 'probe_vs_budget.csv')]
        out_csv = args.out_csv or os.path.join(paths.RESULTS_DIR, 'eval_grid.csv')
        collect_to_grid(sources, out_csv)
        return

    import extract_features as EF
    import probes as P
    args.out_csv = args.out_csv or os.path.join(paths.RESULTS_DIR, 'pilot_results.csv')
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
