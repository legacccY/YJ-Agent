"""
reid_verdict_v2.py — 命门统计工具 v2（2026-06-20 重写；2026-06-21 新指标升级）

WHY REWRITE:
  旧版：只比 A2 vs A0（两臂）、用 scipy.stats（OMP 红线）、LMM（已证塌 p=0.486，
  与 over-control 回归数学同构）——全部作废。

新版严格对齐 ACCEPTANCE_CRITERIA.md P4 判据1/2/3（2026-06-20 skeptic 定案）：

判据1（主判据，机制可归因）= 三臂归因链 A2 > A1' > A0'
  (1a) reid_rate_head(A2) > reid_rate_head(A1')：每集内 per-image 配对精确排列检验
       n≥6：枚举 2^n 符号排列，单侧 p < 0.05
       n<6 小集特例：方向为正 + 全配对同向（最小可达 p）→ 记该集达标
       + 配对 Wilcoxon 同号佐证（手算，禁 scipy）
       + 跨集一致性：(1a) 方向在 ≥3/4 集成立
  (1b) reid_rate_head(A1') > reid_rate_head(A0')：
       A0' 无 re-ID 头（headless），reid_rate_head 全 nan。
       该判据在 reid_rate_head 上标 N/A (A0' headless)，
       回退用旧 seg-mask reid_rate 算 1b 作辅助上下文（明确标注）。
       辅助证据，A1'≈A0' 不致命。

判据2（ε_β0 配平分层 CDE）= "认出≠填上"
  每集筛 |ε_β0(A2)-ε_β0(A1')| 落该集 ε_β0 IQR 内的图子集
  子集内重做配对精确排列（结局量=reid_rate_head），单侧 p < 0.10
  （子集 n<6 套小集特例）
  PASS → re-ID 是 memory 对 re-ID 的直接效应（CDE），非 ε_β0 副产物

判据3（A4 封泄漏）：|reid_rate_head(A4) - reid_rate_head(A2)| < 0.05
  A4 有 re-ID 头，可直接比较。

辅助 TE/NDE/NIE 三件套（仅描述，不设 PASS/FAIL 门）：
  手算 OLS：中介模型 ε_β0~memory_on+dataset，
            结局模型 reid_rate_head~memory_on+ε_β0+dataset
  cluster bootstrap by image_id，95% CI，≥1000 resample

新增列（2026-06-21 升级）：
  reid_rate_head — re-ID 头配对，GT 当裁判（A2/A1'/A4 有值，A0' nan）
  reid_idf1      — IDF1 辅助指标（记录不作判据）
  旧 reid_rate（seg-mask）并列保留在输出 json，仅 1b 回退和辅助上下文用。

红线：禁 scipy.stats（OMP），排列/Wilcoxon/bootstrap/OLS 全手算（numpy+itertools）
     禁跑完调阈值（HARKing），阈值写死
     禁改 ACCEPTANCE（只实现，不改判据）

多集路径聚合：image_id 加数据集前缀（防跨集撞）
"""
from __future__ import annotations

import csv
import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# 预登记阈值（禁跑完改，设计阶段写死）
# ─────────────────────────────────────────────────────────────────────────────
P_THRESH_MAIN = 0.05   # 判据1a/1b n≥6 集单侧精确排列 p
P_THRESH_CDE  = 0.10   # 判据2 ε_β0 配平分层子集单侧精确排列 p
A4_DELTA_MAX  = 0.05   # 判据3 |reid_rate(A4)-reid_rate(A2)| 上界
CONSISTENCY_FRAC = 3/4  # 跨集一致性：A2>A1' 方向 ≥3/4 集成立
N_BOOTSTRAP   = 1000   # cluster bootstrap resample 次数

# 数据集列表（主集，ACCEPTANCE P3）
DATASETS = ['chase', 'hrf', 'fives', 'stare']

# ─────────────────────────────────────────────────────────────────────────────
# CSV 加载 / 多集聚合
# ─────────────────────────────────────────────────────────────────────────────

def _parse_float_nan(val: str | float | None) -> float:
    """
    安全解析浮点，字符串 'nan'/'NaN'/'' / None → float('nan')。
    禁 scipy，纯 Python。
    """
    if val is None:
        return float('nan')
    s = str(val).strip().lower()
    if s in ('nan', '', 'none', 'null', 'n/a'):
        return float('nan')
    try:
        return float(s)
    except ValueError:
        return float('nan')


def load_arm_csv(csv_path: Path | str) -> dict[str, list[dict]]:
    """
    读取 reid_results CSV，返回 {dataset: [row_dict, ...]}。
    image_id 加数据集前缀防跨集撞（`dataset__image_id`）。
    CSV 必须含列：image_id, dataset, reid_rate, epsilon_beta0, epoch, arm
    新增列（可选，缺失则 nan）：reid_rate_head, reid_idf1

    reid_rate_head：re-ID 头配对（GT 裁判）；A0'（headless）全为 nan，优雅处理。
    reid_idf1：辅助 IDF1 指标，仅记录不作判据。
    """
    csv_path = Path(csv_path)
    rows_by_dataset: dict[str, list[dict]] = {}
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 规范小写：train_reid_pilot 写 benchmark 的 sample['dataset']（CHASE/STARE 等大写），
            # 但 DATASETS 硬编码小写 → 不归一会 n=0 假 FAIL（集成烟测 2026-06-20 逮到，
            # 同 Entry14 pilot n=0 假 FAIL 类）。strip+lower 对齐 DATASETS。
            ds = row.get('dataset', 'unknown').strip().lower()
            row = dict(row)
            row['dataset'] = ds
            # 加前缀防撞
            row['image_id_global'] = f"{ds}__{row['image_id']}"
            # 旧 seg-mask reid_rate（保留作 1b 回退和辅助上下文）
            row['reid_rate']        = float(row['reid_rate'])
            # 新 re-ID 头指标（A0' headless → nan；字符串 'nan' 也安全）
            row['reid_rate_head']   = _parse_float_nan(row.get('reid_rate_head'))
            row['reid_idf1']        = _parse_float_nan(row.get('reid_idf1'))
            row['epsilon_beta0']    = float(row.get('epsilon_beta0', float('nan')))
            row['epoch']            = int(row.get('epoch', 0))
            # A-v2 M-B crowding-stratified cols (nan when not computed or A0' headless)
            row['reid_rate_head_high'] = _parse_float_nan(row.get('reid_rate_head_high'))
            row['reid_rate_head_low']  = _parse_float_nan(row.get('reid_rate_head_low'))
            if ds not in rows_by_dataset:
                rows_by_dataset[ds] = []
            rows_by_dataset[ds].append(row)
    return rows_by_dataset


def select_last_epoch(rows: list[dict]) -> list[dict]:
    """每个 image_id_global 取最后 epoch（最终评估状态）。

    防御：若同一 image_id_global 出现多行相同最大 epoch（说明调用方 concat 时
    未加 seed 前缀，多 seed 数据错误合并），打印 WARNING 提示。
    多 seed 正确做法：concat 前给每 seed 的 image_id 加 seed 前缀
    （seed{seed}__{image_id}），使每 seed 每图 image_id_global 唯一。
    """
    import sys
    latest: dict[str, dict] = {}
    # 先收集各 key 的最大 epoch
    max_epoch: dict[str, int] = {}
    for r in rows:
        k = r['image_id_global']
        ep = r['epoch']
        if k not in max_epoch or ep > max_epoch[k]:
            max_epoch[k] = ep

    # 检测同一 key 是否有多行命中最大 epoch（= 没加 seed 前缀时多 seed 误合并）
    count_at_max: dict[str, int] = {}
    for r in rows:
        k = r['image_id_global']
        if r['epoch'] == max_epoch[k]:
            count_at_max[k] = count_at_max.get(k, 0) + 1
    duplicates = [k for k, c in count_at_max.items() if c > 1]
    if duplicates:
        print(
            f"[select_last_epoch WARNING] {len(duplicates)} image_id_global "
            f"各有多行命中最大 epoch（如 {duplicates[:3]!r}）。"
            f"可能原因：多 seed concat 时未加 seed 前缀，导致 seed 信息被吞。"
            f"正确做法：concat 前给 image_id 加 seed 前缀（seed{{seed}}__image_id）。",
            file=sys.stderr,
        )

    for r in rows:
        k = r['image_id_global']
        if k not in latest or r['epoch'] > latest[k]['epoch']:
            latest[k] = r
    return list(latest.values())


def paired_by_image(rows_a: list[dict], rows_b: list[dict],
                    key: str = 'reid_rate',
                    skip_nan: bool = False) -> tuple[list, list, list]:
    """
    配对两臂同图记录，返回 (img_ids, vals_a, vals_b)。
    只取两臂都有的 image_id_global。

    skip_nan=True：任一臂的 key 值为 nan 的配对行不进结果
                   （用于 reid_rate_head 判据，A0' headless 场景已在 1b 回退；
                    A2/A1' 理应有值但稳健处理）。
    """
    map_a = {r['image_id_global']: r for r in rows_a}
    map_b = {r['image_id_global']: r for r in rows_b}
    common = sorted(set(map_a) & set(map_b))
    imgs, va, vb = [], [], []
    for k in common:
        v_a = map_a[k].get(key, float('nan'))
        v_b = map_b[k].get(key, float('nan'))
        if skip_nan and (
            (isinstance(v_a, float) and v_a != v_a) or  # nan check: nan != nan
            (isinstance(v_b, float) and v_b != v_b)
        ):
            continue
        imgs.append(k)
        va.append(v_a)
        vb.append(v_b)
    return imgs, va, vb

# ─────────────────────────────────────────────────────────────────────────────
# 精确排列检验（手算，禁 scipy）
# ─────────────────────────────────────────────────────────────────────────────

def exact_sign_permutation_pvalue(deltas: list[float] | np.ndarray,
                                   one_sided: str = 'greater') -> float:
    """
    配对精确符号排列检验（paired signed permutation test）。
    H1: mean(deltas) > 0（one_sided='greater'）。
    枚举所有 2^n 符号翻转，计算比例 ≥ observed test_stat。
    禁 scipy.stats。
    n 过大（>20）→ 用蒙特卡洛估计（≥10000 次）。

    Returns:
        one-sided p-value (float)
    """
    d = np.asarray(deltas, dtype=float)
    n = len(d)
    obs = float(np.mean(d))

    if n == 0:
        return 1.0

    # n≥6 枚举精确（ACCEPTANCE 要求）；n>20 用 MC（防指数爆炸）
    if n <= 20:
        count_ge = 0
        total = 0
        for signs in itertools.product([-1, 1], repeat=n):
            s = np.array(signs)
            perm_stat = float(np.mean(s * np.abs(d)))
            if one_sided == 'greater':
                if perm_stat >= obs - 1e-12:
                    count_ge += 1
            else:
                if perm_stat <= obs + 1e-12:
                    count_ge += 1
            total += 1
        return count_ge / total
    else:
        # 蒙特卡洛近似
        rng = np.random.default_rng(seed=42)
        n_mc = 10000
        count_ge = 0
        abs_d = np.abs(d)
        for _ in range(n_mc):
            signs = rng.choice([-1.0, 1.0], size=n)
            perm_stat = float(np.mean(signs * abs_d))
            if one_sided == 'greater':
                if perm_stat >= obs - 1e-12:
                    count_ge += 1
            else:
                if perm_stat <= obs + 1e-12:
                    count_ge += 1
        return count_ge / n_mc


def min_achievable_p(n: int) -> float:
    """n 个配对下精确符号排列单侧最小可达 p = 1/2^n。"""
    return 1.0 / (2 ** n)


def wilcoxon_signed_rank_pvalue(deltas: list[float] | np.ndarray,
                                 one_sided: str = 'greater') -> float:
    """
    手算配对 Wilcoxon 符号秩检验（禁 scipy）。
    正态近似（n≥6 适用），连续性修正。
    返回单侧 p。
    """
    d = np.asarray(deltas, dtype=float)
    d_nz = d[d != 0.0]
    n = len(d_nz)
    if n == 0:
        return 1.0
    # 秩（按绝对值）
    abs_d = np.abs(d_nz)
    order = np.argsort(abs_d)
    ranks = np.empty(n, dtype=float)
    i = 0
    while i < n:
        j = i
        while j < n - 1 and abs_d[order[j]] == abs_d[order[j+1]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    W_plus = float(ranks[d_nz > 0].sum())
    W_minus = float(ranks[d_nz < 0].sum())
    if one_sided == 'greater':
        W = W_plus
    else:
        W = W_minus
    # 正态近似
    mu_W = n * (n + 1) / 4.0
    # 修正 tie（这里近似无 tie）
    var_W = n * (n + 1) * (2 * n + 1) / 24.0
    if var_W <= 0:
        return 0.5
    z = (W - mu_W - 0.5) / float(np.sqrt(var_W))  # 连续性修正
    # 手算标准正态 CDF（Taylor 近似，精度足够）
    p_onesided = _standard_normal_sf(z)
    return float(p_onesided)


def _standard_normal_sf(z: float) -> float:
    """
    P(Z > z) 手算（禁 scipy）。
    用 Abramowitz & Stegun 7.1.26 近似，精度 <1.5e-7。
    """
    # 利用 erf 的多项式近似
    sign = 1.0
    if z < 0:
        z = -z
        sign = -1.0
    # erfc(x/sqrt(2)) / 2
    # 用 A&S 7.1.26
    t = 1.0 / (1.0 + 0.2316419 * z)
    poly = t * (0.319381530
                + t * (-0.356563782
                       + t * (1.781477937
                              + t * (-1.821255978
                                     + t * 1.330274429))))
    p = poly * float(np.exp(-0.5 * z * z)) / float(np.sqrt(2.0 * np.pi))
    if sign > 0:
        return float(p)
    else:
        return float(1.0 - p)

# ─────────────────────────────────────────────────────────────────────────────
# 小集特例判定（ACCEPTANCE n<6 预登记规则）
# ─────────────────────────────────────────────────────────────────────────────

def small_set_verdict(deltas: list[float] | np.ndarray) -> dict:
    """
    n<6 小集特例（ACCEPTANCE 预登记）：
    达标线 = 方向为正（mean(deltas)>0）+ 全配对同向（全部 delta>0）
    即取该 n 下精确排列最小可达 p（1/2^n）。
    返回 {'direction_positive': bool, 'all_same_sign': bool,
           'p_min_achievable': float, 'deemed_pass': bool}。
    """
    d = np.asarray(deltas, dtype=float)
    n = len(d)
    direction_pos = float(np.mean(d)) > 0
    all_pos       = bool(np.all(d > 0))
    p_min         = min_achievable_p(n)
    deemed_pass   = direction_pos and all_pos
    return {
        'n':                  n,
        'direction_positive': direction_pos,
        'all_same_sign':      all_pos,
        'p_min_achievable':   p_min,
        'deemed_pass':        deemed_pass,
    }

# ─────────────────────────────────────────────────────────────────────────────
# 判据1a/1b：三臂归因链逐集检验
# ─────────────────────────────────────────────────────────────────────────────

def per_dataset_paired_test(img_ids: list[str],
                             vals_hi: list[float],
                             vals_lo: list[float],
                             dataset: str,
                             label_hi: str, label_lo: str,
                             p_thresh: float = P_THRESH_MAIN) -> dict:
    """
    单集内 per-image 配对精确排列检验 + Wilcoxon 佐证。
    vals_hi, vals_lo 已配对（同 img_id）。
    """
    deltas = [h - l for h, l in zip(vals_hi, vals_lo)]
    n = len(deltas)
    mean_delta = float(np.mean(deltas)) if n > 0 else float('nan')
    n_pos = int(sum(d > 0 for d in deltas))

    if n == 0:
        return {
            'dataset': dataset, 'n': 0, 'label_hi': label_hi, 'label_lo': label_lo,
            'mean_delta': float('nan'),
            'n_positive': 0,
            'perm_p': float('nan'),
            'wilcoxon_p': float('nan'),
            'small_set': None,
            'deemed_pass': False,
            'note': 'empty set',
        }

    if n < 6:
        sv = small_set_verdict(deltas)
        return {
            'dataset': dataset, 'n': n, 'label_hi': label_hi, 'label_lo': label_lo,
            'mean_delta': mean_delta,
            'n_positive': n_pos,
            'perm_p': sv['p_min_achievable'],
            'wilcoxon_p': float('nan'),
            'small_set': sv,
            'deemed_pass': sv['deemed_pass'],
            'note': f'n<6 小集特例（n={n}），达标=方向正+全同向',
        }

    # n≥6：精确排列检验
    perm_p = exact_sign_permutation_pvalue(deltas, one_sided='greater')
    wil_p  = wilcoxon_signed_rank_pvalue(deltas, one_sided='greater')
    deemed_pass = (mean_delta > 0) and (perm_p < p_thresh)

    return {
        'dataset':    dataset,
        'n':          n,
        'label_hi':   label_hi,
        'label_lo':   label_lo,
        'mean_delta': mean_delta,
        'n_positive': n_pos,
        'perm_p':     float(perm_p),
        'wilcoxon_p': float(wil_p),
        'small_set':  None,
        'deemed_pass': deemed_pass,
        'note':       f'n≥6，perm_p={perm_p:.4f} vs thresh={p_thresh}',
    }


def cross_dataset_consistency(per_ds_results: list[dict],
                               frac_thresh: float = CONSISTENCY_FRAC) -> dict:
    """
    跨集一致性：A2>A1' 方向在 ≥frac_thresh 集成立（小集按小集特例算）。
    """
    n_sets = len(per_ds_results)
    if n_sets == 0:
        return {'n_sets': 0, 'n_pass_direction': 0, 'frac_pass': float('nan'),
                'consistency_pass': False}
    n_pass = sum(1 for r in per_ds_results if r['deemed_pass'])
    frac   = n_pass / n_sets
    return {
        'n_sets':          n_sets,
        'n_pass_direction': n_pass,
        'frac_pass':       frac,
        'consistency_pass': frac >= frac_thresh,
        'frac_thresh':     frac_thresh,
    }

# ─────────────────────────────────────────────────────────────────────────────
# 判据2：ε_β0 配平分层 CDE
# ─────────────────────────────────────────────────────────────────────────────

def cde_stratified_test(rows_a2: list[dict], rows_a1p: list[dict],
                         dataset: str,
                         p_thresh: float = P_THRESH_CDE) -> dict:
    """
    ε_β0 配平分层 CDE（每集）。
    筛选 |ε_β0(A2) - ε_β0(A1')| 落该集 ε_β0 IQR 内的图子集，
    子集内重做配对精确排列检验（结局量 = reid_rate_head），单侧 p < p_thresh。
    子集 n<6 套小集特例。
    A2/A1' 都有 reid_rate_head（有头臂），skip_nan=True 稳健过滤。
    """
    # 配对 reid_rate_head（承重结局量）和 epsilon_beta0，过滤 nan
    img_ids, reid_a2, reid_a1p = paired_by_image(
        rows_a2, rows_a1p, 'reid_rate_head', skip_nan=True)
    if not img_ids:
        return {'dataset': dataset, 'n_total': 0, 'n_subset': 0,
                'perm_p': float('nan'), 'deemed_pass': False,
                'note': '无配对图（或 reid_rate_head 全 nan）', 'small_set': None}

    # 取 epsilon_beta0
    map_a2  = {r['image_id_global']: r for r in rows_a2}
    map_a1p = {r['image_id_global']: r for r in rows_a1p}

    eps_a2  = [map_a2[k]['epsilon_beta0']  for k in img_ids]
    eps_a1p = [map_a1p[k]['epsilon_beta0'] for k in img_ids]

    # 该集所有 ε_β0（A2 和 A1' 合并）用于 IQR
    all_eps = np.array(eps_a2 + eps_a1p, dtype=float)
    all_eps = all_eps[np.isfinite(all_eps)]
    if len(all_eps) < 2:
        return {'dataset': dataset, 'n_total': len(img_ids), 'n_subset': 0,
                'perm_p': float('nan'), 'deemed_pass': False,
                'note': 'ε_β0 样本不足，无法计算 IQR', 'small_set': None}

    q25, q75 = float(np.percentile(all_eps, 25)), float(np.percentile(all_eps, 75))
    iqr = q75 - q25

    # 筛 Δε_β0 落 IQR 内的图
    delta_eps = [abs(ea - eb) for ea, eb in zip(eps_a2, eps_a1p)]
    subset_mask = [de <= iqr for de in delta_eps]
    subset_imgs  = [img_ids[i]   for i in range(len(img_ids)) if subset_mask[i]]
    subset_deltas = [reid_a2[i] - reid_a1p[i]
                     for i in range(len(img_ids)) if subset_mask[i]]

    n_total  = len(img_ids)
    n_subset = len(subset_deltas)

    if n_subset == 0:
        return {'dataset': dataset, 'n_total': n_total, 'n_subset': 0,
                'iqr': iqr, 'q25': q25, 'q75': q75,
                'perm_p': float('nan'), 'deemed_pass': False,
                'note': 'CDE 子集为空（所有图 Δε_β0 > IQR）', 'small_set': None}

    mean_delta_subset = float(np.mean(subset_deltas))

    if n_subset < 6:
        sv = small_set_verdict(subset_deltas)
        return {
            'dataset':   dataset,
            'n_total':   n_total,
            'n_subset':  n_subset,
            'iqr':       iqr, 'q25': q25, 'q75': q75,
            'mean_delta_subset': mean_delta_subset,
            'perm_p':    sv['p_min_achievable'],
            'wilcoxon_p': float('nan'),
            'deemed_pass': sv['deemed_pass'],
            'small_set': sv,
            'note': f'CDE 子集 n<6 小集特例（n={n_subset}），达标=方向正+全同向',
        }

    perm_p = exact_sign_permutation_pvalue(subset_deltas, one_sided='greater')
    wil_p  = wilcoxon_signed_rank_pvalue(subset_deltas, one_sided='greater')
    deemed_pass = (mean_delta_subset > 0) and (perm_p < p_thresh)

    return {
        'dataset':   dataset,
        'n_total':   n_total,
        'n_subset':  n_subset,
        'iqr':       iqr, 'q25': q25, 'q75': q75,
        'mean_delta_subset': mean_delta_subset,
        'perm_p':    float(perm_p),
        'wilcoxon_p': float(wil_p),
        'deemed_pass': deemed_pass,
        'small_set': None,
        'note': f'CDE，子集 n={n_subset}，perm_p={perm_p:.4f} vs thresh={p_thresh}',
    }

# ─────────────────────────────────────────────────────────────────────────────
# 辅助 TE/NDE/NIE 三件套（手算 OLS，cluster bootstrap）
# ─────────────────────────────────────────────────────────────────────────────

def _ols_fit(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """
    手算 OLS 系数（禁 scipy/statsmodels）。
    X: (n, p)，已含截距列；y: (n,)
    返回 beta: (p,)
    """
    # beta = (X'X)^{-1} X'y，用 lstsq 的 numpy 版
    # numpy.linalg.lstsq 是纯 numpy，不触发 OMP
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    return beta


def _dataset_dummies(dataset_ids: list[str]) -> np.ndarray:
    """
    为数据集 ID 列表生成虚拟变量矩阵（drop first）。
    返回 (n, n_ds-1) 矩阵（float64）。
    """
    unique_ds = sorted(set(dataset_ids))
    if len(unique_ds) <= 1:
        return np.zeros((len(dataset_ids), 0), dtype=float)
    # drop first
    ref = unique_ds[0]
    cols = []
    for ds in unique_ds[1:]:
        cols.append([1.0 if d == ds else 0.0 for d in dataset_ids])
    return np.column_stack(cols)


def mediation_ols(all_rows_a2: list[dict],
                  all_rows_a1p: list[dict],
                  n_bootstrap: int = N_BOOTSTRAP,
                  rng_seed: int = 42) -> dict:
    """
    TE/NDE/NIE 三件套（手算 OLS，cluster bootstrap by image_id_global）。

    数据：A2 和 A1' 的多集合并（注意 memory_on=1 → A2，=0 → A1'）。
    中介模型：ε_β0 ~ memory_on + dataset_dummies + intercept
    结局模型：reid_rate_head ~ memory_on + ε_β0 + dataset_dummies + intercept
              （2026-06-21 升级：结局量从 reid_rate 换成 reid_rate_head）
    TE  = A2 的 reid_rate_head 均值 - A1' 的 reid_rate_head 均值（不调 ε_β0）
    NDE = 结局模型中 memory_on 系数（固定 ε_β0，直接效应；注意 NDE 偏小是预期，
          原因=中介路径被截断，非无直接效应，论文如实标注）
    NIE = TE - NDE
    cluster bootstrap by image_id_global (≥1000 resample)。
    返回 dict（仅描述，不设 PASS/FAIL）。
    """
    # 合并 A2 + A1' 行
    rows_all = []
    for r in all_rows_a2:
        r2 = dict(r)
        r2['memory_on'] = 1.0
        rows_all.append(r2)
    for r in all_rows_a1p:
        r1 = dict(r)
        r1['memory_on'] = 0.0
        rows_all.append(r1)

    # 过滤：reid_rate_head 有限 + epsilon_beta0 有限（跳 A0' headless nan）
    rows_all = [r for r in rows_all
                if np.isfinite(r.get('reid_rate_head', float('nan')))
                and np.isfinite(r.get('epsilon_beta0', float('nan')))]

    if len(rows_all) < 4:
        return {'note': '样本不足，跳过 TE/NDE/NIE', 'n': len(rows_all),
                'TE_obs': float('nan'), 'NDE_obs': float('nan'), 'NIE_obs': float('nan')}

    n = len(rows_all)
    memory_on  = np.array([r['memory_on']      for r in rows_all], dtype=float)
    reid_head  = np.array([r['reid_rate_head']  for r in rows_all], dtype=float)
    eps_beta0  = np.array([r['epsilon_beta0']   for r in rows_all], dtype=float)
    dataset_ids = [r.get('dataset', 'unknown') for r in rows_all]
    image_ids   = [r['image_id_global'] for r in rows_all]

    ds_dummies = _dataset_dummies(dataset_ids)  # (n, n_ds-1)

    # ---- 中介模型：ε_β0 ~ memory_on + dataset + intercept ---- #
    X_med = np.column_stack([
        np.ones(n),
        memory_on,
        ds_dummies,
    ])
    beta_med = _ols_fit(X_med, eps_beta0)
    # beta_med[1] = memory_on 对 ε_β0 的效应（因果链 a 路径）

    # ---- 结局模型：reid_rate_head ~ memory_on + ε_β0 + dataset + intercept ---- #
    X_out = np.column_stack([
        np.ones(n),
        memory_on,
        eps_beta0,
        ds_dummies,
    ])
    beta_out = _ols_fit(X_out, reid_head)
    # beta_out[1] = NDE（memory_on 系数，固定 ε_β0）
    # beta_out[2] = ε_β0 对 reid_rate_head 的效应（b 路径）

    NDE_obs = float(beta_out[1])

    # TE = A2 均值 - A1' 均值（单变量，不调 ε_β0）
    TE_obs = float(np.mean(reid_head[memory_on == 1]) -
                   np.mean(reid_head[memory_on == 0]))
    NIE_obs = TE_obs - NDE_obs

    # ---- cluster bootstrap by image_id_global ---- #
    unique_imgs = list(set(image_ids))
    # cluster：按 image_id 分组
    img2idx: dict[str, list[int]] = {}
    for i, iid in enumerate(image_ids):
        img2idx.setdefault(iid, []).append(i)

    rng = np.random.default_rng(seed=rng_seed)
    TE_boot  = []
    NDE_boot = []
    NIE_boot = []

    for _ in range(n_bootstrap):
        # 有放回抽 image clusters
        sampled_imgs = rng.choice(unique_imgs, size=len(unique_imgs), replace=True)
        idx_boot = []
        for im in sampled_imgs:
            idx_boot.extend(img2idx[im])
        idx_boot = np.array(idx_boot, dtype=int)

        mo_b = memory_on[idx_boot]
        rh_b = reid_head[idx_boot]
        ep_b = eps_beta0[idx_boot]
        ds_b = [dataset_ids[i] for i in idx_boot]
        ds_dum_b = _dataset_dummies(ds_b)
        nb = len(idx_boot)

        # 中介模型
        X_med_b = np.column_stack([np.ones(nb), mo_b, ds_dum_b])
        try:
            b_med_b = _ols_fit(X_med_b, ep_b)
        except Exception:
            continue

        # 结局模型（reid_rate_head）
        X_out_b = np.column_stack([np.ones(nb), mo_b, ep_b, ds_dum_b])
        try:
            b_out_b = _ols_fit(X_out_b, rh_b)
        except Exception:
            continue

        nde_b = float(b_out_b[1])
        te_b  = (float(np.mean(rh_b[mo_b == 1])) - float(np.mean(rh_b[mo_b == 0]))
                 if (mo_b == 1).any() and (mo_b == 0).any()
                 else float('nan'))
        if not np.isfinite(te_b):
            continue
        nie_b = te_b - nde_b

        TE_boot.append(te_b)
        NDE_boot.append(nde_b)
        NIE_boot.append(nie_b)

    def _ci(arr):
        if not arr:
            return float('nan'), float('nan')
        a = np.array(arr)
        return float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))

    te_lo, te_hi   = _ci(TE_boot)
    nde_lo, nde_hi = _ci(NDE_boot)
    nie_lo, nie_hi = _ci(NIE_boot)

    return {
        'n':          n,
        'n_images':   len(unique_imgs),
        'outcome_metric': 'reid_rate_head',  # 2026-06-21 升级标记
        'TE_obs':     TE_obs,
        'NDE_obs':    NDE_obs,
        'NIE_obs':    NIE_obs,
        'TE_CI_95':   [te_lo,  te_hi],
        'NDE_CI_95':  [nde_lo, nde_hi],
        'NIE_CI_95':  [nie_lo, nie_hi],
        'n_bootstrap': len(TE_boot),
        'note': (
            'NDE 偏小预期（中介路径被截断，非无直接效应）。'
            '仅描述，不设 PASS/FAIL。'
            '须真写进论文正文（主动暴露不利数字=严谨；省掉=藏）。'
            '结局量=reid_rate_head（2026-06-21 升级，旧 reid_rate 仅 1b 回退用）。'
        ),
    }

# ─────────────────────────────────────────────────────────────────────────────
# 判据3：A4 封泄漏
# ─────────────────────────────────────────────────────────────────────────────

def a4_leakage_test(rows_a2: list[dict], rows_a4: list[dict],
                    delta_max: float = A4_DELTA_MAX) -> dict:
    """
    |reid_rate_head(A4) - reid_rate_head(A2)| < delta_max（0.05）
    → GT 拓扑无实质优势，泄漏质疑解除。
    A4 有 re-ID 头，两臂均用 reid_rate_head（skip_nan=True 稳健处理）。
    """
    img_ids, reid_a2, reid_a4 = paired_by_image(
        rows_a2, rows_a4, 'reid_rate_head', skip_nan=True)
    if not img_ids:
        return {'n': 0, 'mean_abs_delta': float('nan'),
                'deemed_pass': False,
                'note': '无配对 A4 数据（或 reid_rate_head 全 nan）',
                'metric': 'reid_rate_head'}

    deltas = [abs(a4 - a2) for a4, a2 in zip(reid_a4, reid_a2)]
    mean_delta = float(np.mean(deltas))
    deemed_pass = mean_delta < delta_max
    return {
        'n':             len(deltas),
        'mean_abs_delta': mean_delta,
        'max_abs_delta':  float(max(deltas)),
        'delta_max_thresh': delta_max,
        'deemed_pass':   deemed_pass,
        'metric':        'reid_rate_head',  # 2026-06-21 升级标记
        'note': f'|A4-A2| reid_rate_head mean={mean_delta:.4f} vs thresh={delta_max}',
    }

# ─────────────────────────────────────────────────────────────────────────────
# 主入口：多集完整 verdict
# ─────────────────────────────────────────────────────────────────────────────

def run_verdict(
    csv_a2:  Path | str,
    csv_a1p: Path | str,
    csv_a0p: Path | str,
    csv_a4:  Path | str | None = None,
    datasets: list[str] = DATASETS,
    out_json: Path | str | None = None,
) -> dict:
    """
    完整命门 verdict 主入口。

    参数：
      csv_a2   : A2（完整记忆）reid_results CSV
      csv_a1p  : A1'（等参普通线性注意力）reid_results CSV
      csv_a0p  : A0'（纯 CNN 无记忆）reid_results CSV
      csv_a4   : A4（预测骨架 breakpoint）reid_results CSV（可为 None）
      datasets : 参与统计的数据集名列表
      out_json : 输出 JSON 路径（None 则不写文件）

    返回：完整 verdict dict。
    """
    print('[reid_verdict_v2] 加载 CSV...')
    all_a2  = load_arm_csv(csv_a2)
    all_a1p = load_arm_csv(csv_a1p)
    all_a0p = load_arm_csv(csv_a0p)
    all_a4  = load_arm_csv(csv_a4) if csv_a4 else {}

    # ── 判据1a：A2 > A1'，逐集（承重，用 reid_rate_head）────────────────── #
    results_1a: list[dict] = []
    results_1b: list[dict] = []
    results_1b_fallback: list[dict] = []  # 1b 回退 seg-mask reid_rate
    all_a2_rows:  list[dict] = []
    all_a1p_rows: list[dict] = []

    # 检测 A0' 是否全为 headless（reid_rate_head 全 nan）
    all_a0p_rows_flat = [r for ds_rows in all_a0p.values() for r in ds_rows]
    a0p_head_vals = [r.get('reid_rate_head', float('nan')) for r in all_a0p_rows_flat]
    a0p_is_headless = (len(a0p_head_vals) == 0 or
                       all(v != v for v in a0p_head_vals))  # nan != nan

    for ds in datasets:
        rows_a2_ds  = select_last_epoch(all_a2.get(ds, []))
        rows_a1p_ds = select_last_epoch(all_a1p.get(ds, []))
        rows_a0p_ds = select_last_epoch(all_a0p.get(ds, []))

        all_a2_rows.extend(rows_a2_ds)
        all_a1p_rows.extend(rows_a1p_ds)

        # 1a：A2 > A1'（承重判据，用 reid_rate_head，skip_nan=True）
        img_ids_1a, va2_head, va1p_head = paired_by_image(
            rows_a2_ds, rows_a1p_ds, 'reid_rate_head', skip_nan=True)
        r_1a = per_dataset_paired_test(
            img_ids_1a, va2_head, va1p_head, ds, 'A2', "A1'", P_THRESH_MAIN)
        r_1a['metric'] = 'reid_rate_head'  # 标记使用的指标

        # 双报：同集 reid_rate（旧指标）透明留痕
        img_ids_1a_old, va2_old, va1p_old = paired_by_image(
            rows_a2_ds, rows_a1p_ds, 'reid_rate')
        r_1a['mean_reid_rate_old'] = (
            float(np.mean([a - b for a, b in zip(va2_old, va1p_old)]))
            if va2_old else float('nan')
        )
        r_1a['n_old'] = len(va2_old)
        results_1a.append(r_1a)

        # 1b：A1' > A0'
        if a0p_is_headless:
            # A0' 无头，reid_rate_head 无法比较 → 标 N/A，回退 seg-mask
            r_1b_fallback = per_dataset_paired_test(
                *paired_by_image(rows_a1p_ds, rows_a0p_ds, 'reid_rate')[:],
                ds, "A1'", "A0'", P_THRESH_MAIN)
            r_1b_fallback['metric'] = 'reid_rate_segmask_fallback'
            r_1b_fallback['note_1b'] = (
                '1b 用 seg-mask reid_rate（A0\' headless，reid_rate_head=nan）；'
                '1b 辅助非承重，A1\'≈A0\' 不致命。'
            )
            results_1b.append({
                'dataset': ds,
                'metric': 'N/A (A0\' headless)',
                'deemed_pass': None,
                'note': '1b 在 reid_rate_head 上 N/A：A0\' 无 re-ID 头。'
                        '见 verdict_1b_fallback_per_dataset 获取 seg-mask 辅助结果。',
            })
            results_1b_fallback.append(r_1b_fallback)
        else:
            # A0' 有头（正常路径，未来若 A0' 也训 re-ID 头）
            img_ids_1b, va1p_2, va0p = paired_by_image(
                rows_a1p_ds, rows_a0p_ds, 'reid_rate_head', skip_nan=True)
            r_1b = per_dataset_paired_test(
                img_ids_1b, va1p_2, va0p, ds, "A1'", "A0'", P_THRESH_MAIN)
            r_1b['metric'] = 'reid_rate_head'
            results_1b.append(r_1b)

    # 跨集一致性（1a）
    consistency_1a = cross_dataset_consistency(results_1a, CONSISTENCY_FRAC)

    # 1a 总体 PASS
    verdict_1a_pass = consistency_1a['consistency_pass']

    # ── A-v2 M-C dose-response 判据（命门 A-v2 主判据升级）─────────────────── #
    # 主判据 = dose-response 交互：A2−A1' delta 随 crowding 单调上升。
    # high-crowding 子集（k≥k_thresh）per-image 配对 A2>A1' 显著(p<0.05)
    # + low-crowding 子集（k<k_thresh）tied（方向不显著）→ dose-response 成立。
    # 承重列：reid_rate_head_high（A-v2 新列）vs reid_rate_head_low（tied 期望）。
    results_dose_high: list[dict] = []
    results_dose_low:  list[dict] = []

    for ds in datasets:
        rows_a2_ds  = select_last_epoch(all_a2.get(ds, []))
        rows_a1p_ds = select_last_epoch(all_a1p.get(ds, []))

        # High-crowding subset (k ≥ k_thresh): A2 > A1' expected
        img_ids_h, va2_h, va1p_h = paired_by_image(
            rows_a2_ds, rows_a1p_ds, 'reid_rate_head_high', skip_nan=True)
        r_high = per_dataset_paired_test(
            img_ids_h, va2_h, va1p_h, ds, 'A2', "A1'", P_THRESH_MAIN)
        r_high['subset'] = 'high'
        r_high['metric'] = 'reid_rate_head_high'
        results_dose_high.append(r_high)

        # Low-crowding subset (k < k_thresh): tied expected (direction not significant)
        img_ids_l, va2_l, va1p_l = paired_by_image(
            rows_a2_ds, rows_a1p_ds, 'reid_rate_head_low', skip_nan=True)
        r_low = per_dataset_paired_test(
            img_ids_l, va2_l, va1p_l, ds, 'A2', "A1'", P_THRESH_MAIN)
        r_low['subset'] = 'low'
        r_low['metric'] = 'reid_rate_head_low'
        results_dose_low.append(r_low)

    # Dose-response 成立 iff:
    #   high-crowding 跨集一致性 ≥3/4 PASS (A2>A1' 显著)
    #   AND low-crowding 跨集方向不显著 (tied; high-crowding 特异)
    consistency_high = cross_dataset_consistency(results_dose_high, CONSISTENCY_FRAC)
    # low-crowding: "tied" = ≥3/4 集 deemed_pass=False (NOT significant)
    n_low_pass_dir = sum(1 for r in results_dose_low if r['deemed_pass'])
    n_low_sets     = len(results_dose_low)
    frac_low_tied  = 1.0 - (n_low_pass_dir / n_low_sets) if n_low_sets > 0 else 0.0
    low_is_tied    = (frac_low_tied >= CONSISTENCY_FRAC)   # ≥3/4 集 not significant

    dose_response_pass = consistency_high['consistency_pass'] and low_is_tied

    # Determine n_high_total / n_low_total for audit
    n_high_total = int(sum(r.get('n', 0) for r in results_dose_high))
    n_low_total  = int(sum(r.get('n', 0) for r in results_dose_low))

    dose_note = (
        f"dose-response {'成立' if dose_response_pass else '不成立'}: "
        f"high-crowding A2>A1' 一致性 {consistency_high['n_pass_direction']}/{consistency_high['n_sets']} "
        f"({'PASS' if consistency_high['consistency_pass'] else 'FAIL'}); "
        f"low-crowding tied (≥3/4集不显著) {'成立' if low_is_tied else '不成立'} "
        f"({n_low_sets - n_low_pass_dir}/{n_low_sets} 集不显著). "
        f"判定：high 显著 & low tied → dose-response 成立 iff 两者均满足."
    )
    print(f'[A-v2 dose-response] {dose_note}')

    # (a)/(b) 归因读数（描述性，不设门）
    # A1' vs r_chance in high subset: 从行数据直接汇总（可选，若 r_chance 列有值）
    dose_ab_note = (
        '(a)/(b) 描述性读数: 见 dose_response_per_dataset 各集 mean_delta。'
        'r_chance=1/(K-1) 从 state.json 或 crowding_manifest 读；'
        '正式论文写 A1\'/A2 在 high subset 各自 reid_rate_head_high vs r_chance。'
    )

    # 1b 总体（辅助，不致命）
    if a0p_is_headless:
        n_ds_pass_1b_fb = sum(1 for r in results_1b_fallback if r['deemed_pass'])
        verdict_1b_note = (
            f"[1b N/A on reid_rate_head: A0' headless] "
            f"回退 seg-mask 辅助：A1'>A0' 方向成立集数 "
            f"{n_ds_pass_1b_fb}/{len(results_1b_fallback)}。"
            f"1b 辅助非承重，A1'≈A0' 不致命。"
        )
    else:
        n_ds_pass_1b = sum(1 for r in results_1b if r.get('deemed_pass'))
        verdict_1b_note = (
            f"A1'>A0' reid_rate_head 方向成立集数: {n_ds_pass_1b}/{len(results_1b)}。"
            f"辅助证据，A1'≈A0' 不致命（增益全在 delta-rule 更利 headline）。"
        )

    print(f'[判据1a] 跨集一致性: {consistency_1a["n_pass_direction"]}/{consistency_1a["n_sets"]} '
          f'集成立 (reid_rate_head) → {" PASS" if verdict_1a_pass else " FAIL"}')

    # ── 判据2：ε_β0 配平分层 CDE，逐集 ────────────────────────────────── #
    results_cde: list[dict] = []
    for ds in datasets:
        rows_a2_ds  = select_last_epoch(all_a2.get(ds, []))
        rows_a1p_ds = select_last_epoch(all_a1p.get(ds, []))
        r_cde = cde_stratified_test(rows_a2_ds, rows_a1p_ds, ds, P_THRESH_CDE)
        results_cde.append(r_cde)

    # 判据2 PASS：多集中一致（至少 ≥3/4 集子集 PASS；子集为空不算 FAIL 但标注）
    nonempty_cde = [r for r in results_cde if r['n_subset'] > 0]
    n_cde_pass   = sum(1 for r in nonempty_cde if r['deemed_pass'])
    verdict_2_pass = (len(nonempty_cde) > 0 and
                      n_cde_pass / len(nonempty_cde) >= CONSISTENCY_FRAC)
    print(f'[判据2 CDE] 子集非空集通过: {n_cde_pass}/{len(nonempty_cde)} '
          f'→ {" PASS" if verdict_2_pass else " FAIL"}')

    # ── 辅助 TE/NDE/NIE ──────────────────────────────────────────────────── #
    print('[辅助 TE/NDE/NIE] 计算中（cluster bootstrap）...')
    mediation_result = mediation_ols(all_a2_rows, all_a1p_rows, N_BOOTSTRAP)

    # ── 判据3：A4 封泄漏 ─────────────────────────────────────────────────── #
    if all_a4:
        all_a2_last  = []
        all_a4_last  = []
        for ds in datasets:
            all_a2_last.extend(select_last_epoch(all_a2.get(ds, [])))
            all_a4_last.extend(select_last_epoch(all_a4.get(ds, [])))
        a4_result = a4_leakage_test(all_a2_last, all_a4_last, A4_DELTA_MAX)
    else:
        a4_result = {'note': 'A4 CSV 未提供，跳过判据3', 'deemed_pass': None}

    verdict_3_pass = a4_result.get('deemed_pass', None)
    print(f'[判据3 A4] {a4_result["note"]}')

    # ── 最终命门判定 ─────────────────────────────────────────────────────── #
    # PASS 线（A-v2 升级）：
    #   主判据 = dose-response: high-crowding A2>A1' 跨集一致性 ≥3/4 AND low-crowding tied
    #   判据 1a（旧全 gap reid_rate_head）仍报作辅助参照
    #   判据2 ε_β0 CDE ≥3/4 非空集通过
    #   判据3 如有数据则需 PASS（否则 pending）
    #
    # A-v2 命门主判据 = dose_response_pass（ACCEPTANCE 2026-06-21 预登记）。
    # 若 dose-response 列全 nan（首次跑无 crowding_manifest），回退旧 verdict_1a_pass。
    _use_dose = (n_high_total > 0)   # has actual high-crowding data
    _main_pass = dose_response_pass if _use_dose else verdict_1a_pass
    _main_label = 'dose-response' if _use_dose else '1a(全gap,fallback)'

    if verdict_3_pass is None:
        claim2_verdict = (
            f'PASS（待 A4; 主判据={_main_label}）' if (_main_pass and verdict_2_pass)
            else f'FAIL（待 A4; 主判据={_main_label}）'
        )
    else:
        claim2_verdict = (
            f'PASS（主判据={_main_label}）'
            if (_main_pass and verdict_2_pass and verdict_3_pass)
            else f'FAIL（主判据={_main_label}）'
        )

    print(f'\n=== CLAIM 2 最终命门判定: {claim2_verdict} ===')

    out = {
        'meta': {
            'version': 'reid_verdict_v2_rewrite_20260621_av2_dose_response',
            'metric_upgrade': (
                '2026-06-21 A-I: 判据 1a/2/A4 从 reid_rate(seg-mask) 换成 '
                'reid_rate_head(re-ID 头配对,GT 当裁判)。'
                '旧 reid_rate 并列保留作辅助上下文和 1b 回退。'
                'A0\' headless → 1b 在 reid_rate_head 上标 N/A，回退 seg-mask。'
                '2026-06-21 A-v2: 新增 dose-response 判据（high/low-crowding 子集交互，'
                '承重列=reid_rate_head_high/low，k_thresh=median from crowding_manifest）。'
                'M-A memory-only 头（use_loc_feat=False）砍 dec_feat 近路。'
            ),
            'pre_registered_thresholds': {
                'P_THRESH_MAIN':     P_THRESH_MAIN,
                'P_THRESH_CDE':      P_THRESH_CDE,
                'A4_DELTA_MAX':      A4_DELTA_MAX,
                'CONSISTENCY_FRAC':  CONSISTENCY_FRAC,
            },
            'datasets': datasets,
            'a0p_is_headless': a0p_is_headless,
        },
        # ── 判据 1a（承重，reid_rate_head）────────────────────────────────── #
        'verdict_1a_per_dataset': results_1a,   # 含 metric='reid_rate_head' + mean_reid_rate_old 双报
        'verdict_1a_consistency': consistency_1a,
        'verdict_1a_pass':        verdict_1a_pass,
        # ── 判据 1b（辅助）────────────────────────────────────────────────── #
        'verdict_1b_per_dataset':          results_1b,           # headless → N/A
        'verdict_1b_fallback_per_dataset': results_1b_fallback,  # 回退 seg-mask（headless 时有值）
        'verdict_1b_note':                 verdict_1b_note,
        # ── A-v2 M-C dose-response 判据（承重，高低 crowding 交互）────────── #
        'dose_response_high_per_dataset': results_dose_high,
        'dose_response_low_per_dataset':  results_dose_low,
        'dose_response_high_consistency': consistency_high,
        'dose_response_low_tied':         low_is_tied,
        'dose_response_n_low_sets':       n_low_sets,
        'dose_response_n_low_pass_dir':   n_low_pass_dir,
        'dose_response_n_high_total':     n_high_total,
        'dose_response_n_low_total':      n_low_total,
        'dose_response_pass':             dose_response_pass,
        'dose_response_note':             dose_note,
        'dose_ab_note':                   dose_ab_note,
        # ── 判据 2（CDE，reid_rate_head）──────────────────────────────────── #
        'verdict_2_cde_per_dataset': results_cde,
        'verdict_2_pass':            verdict_2_pass,
        'verdict_2_n_pass':          n_cde_pass,
        'verdict_2_n_nonempty':      len(nonempty_cde),
        # ── 辅助 TE/NDE/NIE（reid_rate_head）──────────────────────────────── #
        'mediation_TE_NDE_NIE':   mediation_result,
        # ── 判据 3 A4（reid_rate_head）────────────────────────────────────── #
        'verdict_3_a4_leakage':   a4_result,
        'verdict_3_pass':         verdict_3_pass,
        'CLAIM2_VERDICT':         claim2_verdict,
    }

    if out_json is not None:
        out_json = Path(out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(out, indent=2, ensure_ascii=False),
                            encoding='utf-8')
        print(f'[written] {out_json}')

    return out


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _cli():
    import argparse
    parser = argparse.ArgumentParser(
        description='gdn2vessel Claim2 re-ID 可归因命门统计工具 v2')
    parser.add_argument('--csv_a2',  required=True,
                        help='A2（完整记忆）reid_results CSV')
    parser.add_argument('--csv_a1p', required=True,
                        help="A1'（等参线性 attn）reid_results CSV")
    parser.add_argument('--csv_a0p', required=True,
                        help="A0'（纯 CNN）reid_results CSV")
    parser.add_argument('--csv_a4',  default=None,
                        help='A4（预测骨架）reid_results CSV（可选）')
    parser.add_argument('--datasets', nargs='+', default=DATASETS,
                        help='数据集名列表（默认 chase hrf fives stare）')
    parser.add_argument('--out_json', default=None,
                        help='输出 verdict JSON 路径')
    args = parser.parse_args()
    run_verdict(
        csv_a2=args.csv_a2,
        csv_a1p=args.csv_a1p,
        csv_a0p=args.csv_a0p,
        csv_a4=args.csv_a4,
        datasets=args.datasets,
        out_json=args.out_json,
    )


if __name__ == '__main__':
    _cli()
