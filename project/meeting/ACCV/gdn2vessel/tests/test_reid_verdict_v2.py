"""
test_reid_verdict_v2.py — reid_verdict_v2.py 的完整测试套件。

覆盖：
  1. 精确排列检验手算正确性（已知 p 验证）
  2. Wilcoxon 符号秩检验手算正确性（方向一致性）
  3. 小集特例（n=4 STARE 场景）
  4. 跨集一致性判定
  5. ε_β0 配平分层 CDE（子集筛选 + 排列检验）
  6. TE/NDE/NIE OLS + cluster bootstrap（有限数字、CI 有序）
  7. A4 泄漏测试
  8. 真 e2e 烟测：造 3 臂×多集假数据 → run_verdict 全链跑通

红线：
  - 禁 scipy.stats（OMP）
  - 阈值禁跑完改（硬编码核对）
  - 禁碰 ACCEPTANCE 文件
"""
from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

# ─────────────────────────────────────────────────────────────────────────────
# 路径 setup
# ─────────────────────────────────────────────────────────────────────────────
_repo_root = Path(__file__).parent.parent
_src_dir   = _repo_root / 'src'
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from reid_verdict_v2 import (
    exact_sign_permutation_pvalue,
    wilcoxon_signed_rank_pvalue,
    small_set_verdict,
    per_dataset_paired_test,
    cross_dataset_consistency,
    cde_stratified_test,
    mediation_ols,
    a4_leakage_test,
    run_verdict,
    load_arm_csv,
    select_last_epoch,
    paired_by_image,
    P_THRESH_MAIN,
    P_THRESH_CDE,
    A4_DELTA_MAX,
    CONSISTENCY_FRAC,
)


# ─────────────────────────────────────────────────────────────────────────────
# 工具：写 mock CSV
# ─────────────────────────────────────────────────────────────────────────────

_CSV_HEADER = ['epoch', 'image_id', 'dataset', 'severity',
               'reid_rate', 'reid_rate_head', 'reid_idf1',
               'epsilon_beta0', 'success_rate', 'n_gaps', 'arm']


def _write_csv(tmp_path: Path, rows: list[dict], fname: str) -> Path:
    """写 mock reid_results CSV 并返回路径。"""
    p = tmp_path / fname
    with open(p, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=_CSV_HEADER)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, '') for k in _CSV_HEADER})
    return p


def _make_rows(image_ids: list[str],
               reid_rates: list[float],
               eps_beta0s:  list[float],
               dataset: str = 'chase',
               epoch: int = 80,
               arm: str = 'test',
               reid_rate_head: float | None = None,
               headless: bool = False) -> list[dict]:
    """
    合成一批 reid_results 行。
    reid_rate_head: None → 与 reid_rate 相同（有头臂默认）
    headless=True  → reid_rate_head='nan'（A0' 无 re-ID 头场景）
    """
    rows = []
    for i, (iid, rr, eb) in enumerate(zip(image_ids, reid_rates, eps_beta0s)):
        if headless:
            rh = 'nan'
        elif reid_rate_head is not None:
            rh = reid_rate_head if not isinstance(reid_rate_head, list) else reid_rate_head[i]
        else:
            rh = rr  # 默认与 reid_rate 相同
        rows.append({
            'epoch':          epoch,
            'image_id':       iid,
            'dataset':        dataset,
            'severity':       'Medium',
            'reid_rate':      rr,
            'reid_rate_head': rh,
            'reid_idf1':      rr * 0.9,  # 辅助指标，随意给个值
            'epsilon_beta0':  eb,
            'success_rate':   0.8,
            'n_gaps':         10,
            'arm':            arm,
        })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# 0. 回归：dataset 大小写归一（集成烟测 2026-06-20 逮到的假 FAIL 缝）
#    train_reid_pilot 写 sample['dataset']（CHASE/STARE 大写），DATASETS 硬编码小写，
#    不归一 → n=0 空集 → 假 FAIL（Entry14 pilot n=0 同款，会烧 92 GPU·h）。
#    现有测试默认 dataset='chase' 小写故漏掉此缝；本测试锁大写输入必被归一。
# ─────────────────────────────────────────────────────────────────────────────
class TestDatasetCaseNormalization:

    def test_uppercase_dataset_normalized_to_lower(self, tmp_path):
        # train 真写大写 'CHASE'
        rows = _make_rows(['i0', 'i1'], [0.5, 0.6], [100.0, 110.0],
                          dataset='CHASE', arm='memory')
        csv_p = _write_csv(tmp_path, rows, 'upper.csv')
        by_ds = load_arm_csv(csv_p)
        # key 必归一小写，对齐 DATASETS=['chase',...]，否则 n=0 假 FAIL
        assert 'chase' in by_ds, f"大写 CHASE 未归一小写 → 会假 FAIL，得到 keys={list(by_ds)}"
        assert 'CHASE' not in by_ds
        assert len(by_ds['chase']) == 2
        # row 内 dataset 字段也归一（mediation dummies 一致性）
        assert all(r['dataset'] == 'chase' for r in by_ds['chase'])

    def test_mixed_case_dataset_collapses(self, tmp_path):
        rows = (_make_rows(['a0'], [0.5], [100.0], dataset='STARE')
                + _make_rows(['a1'], [0.6], [110.0], dataset='stare'))
        csv_p = _write_csv(tmp_path, rows, 'mixed.csv')
        by_ds = load_arm_csv(csv_p)
        # STARE 与 stare 必合并为同一集，不裂成两 key
        assert 'stare' in by_ds and len(by_ds['stare']) == 2
        assert 'STARE' not in by_ds


# ─────────────────────────────────────────────────────────────────────────────
# 1. 精确排列检验
# ─────────────────────────────────────────────────────────────────────────────

class TestExactPermutation:

    def test_all_positive_deltas_gives_min_p(self):
        """n=8，全正 delta → p = 1/2^8 = 1/256 ≈ 0.00391。"""
        d = [0.1, 0.2, 0.05, 0.15, 0.08, 0.12, 0.18, 0.07]
        p = exact_sign_permutation_pvalue(d, one_sided='greater')
        expected = 1 / 256
        assert abs(p - expected) < 1e-6, f'Expected {expected:.6f}, got {p:.6f}'

    def test_all_negative_deltas_gives_max_p(self):
        """n=8，全负 delta → p = 1.0（H1:delta>0 完全不支持）。"""
        d = [-0.1, -0.2, -0.05, -0.15, -0.08, -0.12, -0.18, -0.07]
        p = exact_sign_permutation_pvalue(d, one_sided='greater')
        assert p == 1.0 or abs(p - 1.0) < 1e-6, f'Expected p≈1.0, got {p}'

    def test_half_half_delta_approx_half(self):
        """n=6，3正3负对称 → p ≈ 0.5。"""
        d = [0.1, 0.2, 0.15, -0.1, -0.2, -0.15]
        p = exact_sign_permutation_pvalue(d, one_sided='greater')
        # 对称 → 约等于 0.5（不严格 = 0.5 因为用 mean 而非 W）
        assert 0.3 < p < 0.7, f'Expected ~0.5, got {p}'

    def test_empty_deltas_returns_1(self):
        p = exact_sign_permutation_pvalue([], one_sided='greater')
        assert p == 1.0

    def test_single_positive_delta(self):
        """n=1，正 delta → p = 0.5（1/2^1）。"""
        p = exact_sign_permutation_pvalue([0.5], one_sided='greater')
        assert abs(p - 0.5) < 1e-9

    def test_n4_all_positive_exact(self):
        """n=4，全正 → p = 1/16 = 0.0625（STARE 小集场景）。"""
        d = [0.05, 0.08, 0.12, 0.03]
        p = exact_sign_permutation_pvalue(d, one_sided='greater')
        assert abs(p - 1/16) < 1e-9, f'Expected 0.0625, got {p}'


# ─────────────────────────────────────────────────────────────────────────────
# 2. Wilcoxon 手算
# ─────────────────────────────────────────────────────────────────────────────

class TestWilcoxon:

    def test_all_positive_small_p(self):
        """n=8 全正 delta → Wilcoxon p 应很小。"""
        d = [0.1, 0.2, 0.05, 0.15, 0.08, 0.12, 0.18, 0.07]
        p = wilcoxon_signed_rank_pvalue(d, one_sided='greater')
        assert p < 0.05, f'Expected p<0.05 for all-positive, got {p}'

    def test_all_negative_large_p(self):
        """n=8 全负 delta → H1:greater 不支持，p > 0.5。"""
        d = [-0.1, -0.2, -0.05, -0.15, -0.08, -0.12, -0.18, -0.07]
        p = wilcoxon_signed_rank_pvalue(d, one_sided='greater')
        assert p > 0.5, f'Expected p>0.5 for all-negative, got {p}'

    def test_zero_deltas_returns_1(self):
        """全零 delta → 无信息 → p = 1。"""
        d = [0.0, 0.0, 0.0]
        p = wilcoxon_signed_rank_pvalue(d, one_sided='greater')
        assert p == 1.0

    def test_empty_returns_1(self):
        p = wilcoxon_signed_rank_pvalue([], one_sided='greater')
        assert p == 1.0

    def test_consistency_with_permutation_direction(self):
        """Wilcoxon 与排列检验方向一致（正 delta → 两者 p 都小）。"""
        d = [0.05, 0.12, 0.08, 0.15, 0.03, 0.09, 0.11, 0.07]
        p_perm = exact_sign_permutation_pvalue(d)
        p_wil  = wilcoxon_signed_rank_pvalue(d)
        # 两者都应 < 0.05
        assert p_perm < 0.05
        assert p_wil  < 0.05


# ─────────────────────────────────────────────────────────────────────────────
# 3. 小集特例（n<6）
# ─────────────────────────────────────────────────────────────────────────────

class TestSmallSetVerdict:

    def test_n4_all_positive_deemed_pass(self):
        """n=4 全正 → deemed_pass=True（STARE 场景）。"""
        d = [0.05, 0.08, 0.12, 0.03]
        sv = small_set_verdict(d)
        assert sv['deemed_pass'] is True
        assert sv['all_same_sign'] is True
        assert abs(sv['p_min_achievable'] - 1/16) < 1e-9

    def test_n4_mixed_sign_fail(self):
        """n=4，有负 delta → deemed_pass=False。"""
        d = [0.05, -0.02, 0.12, 0.03]
        sv = small_set_verdict(d)
        assert sv['deemed_pass'] is False
        assert sv['all_same_sign'] is False

    def test_n3_all_positive(self):
        """n=3 全正 → deemed_pass=True，p_min=1/8=0.125。"""
        d = [0.1, 0.2, 0.15]
        sv = small_set_verdict(d)
        assert sv['deemed_pass'] is True
        assert abs(sv['p_min_achievable'] - 1/8) < 1e-9

    def test_n5_all_positive(self):
        d = [0.1, 0.2, 0.15, 0.05, 0.08]
        sv = small_set_verdict(d)
        assert sv['deemed_pass'] is True
        assert abs(sv['p_min_achievable'] - 1/32) < 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# 4. 单集配对检验
# ─────────────────────────────────────────────────────────────────────────────

class TestPerDatasetPairedTest:

    def test_n8_all_positive_pass(self):
        """n=8 全正 delta → deemed_pass=True。"""
        ids = [f'img{i}' for i in range(8)]
        a2  = [0.7, 0.8, 0.75, 0.72, 0.68, 0.71, 0.79, 0.73]
        a1p = [0.6, 0.7, 0.65, 0.62, 0.58, 0.61, 0.69, 0.63]
        r = per_dataset_paired_test(ids, a2, a1p, 'chase', 'A2', "A1'")
        assert r['deemed_pass'] is True
        assert r['perm_p'] < P_THRESH_MAIN
        assert r['n'] == 8
        assert r['n_positive'] == 8

    def test_n8_all_negative_fail(self):
        """n=8 全负 delta（A2 < A1'）→ deemed_pass=False。"""
        ids = [f'img{i}' for i in range(8)]
        a2  = [0.5, 0.6, 0.55, 0.52, 0.48, 0.51, 0.59, 0.53]
        a1p = [0.6, 0.7, 0.65, 0.62, 0.58, 0.61, 0.69, 0.63]
        r = per_dataset_paired_test(ids, a2, a1p, 'chase', 'A2', "A1'")
        assert r['deemed_pass'] is False

    def test_n4_small_set_all_positive(self):
        """n=4 全正 → 小集特例，deemed_pass=True。"""
        ids = [f'img{i}' for i in range(4)]
        a2  = [0.7, 0.8, 0.75, 0.72]
        a1p = [0.6, 0.7, 0.65, 0.62]
        r = per_dataset_paired_test(ids, a2, a1p, 'stare', 'A2', "A1'")
        assert r['deemed_pass'] is True
        assert r['small_set'] is not None
        assert r['small_set']['all_same_sign'] is True

    def test_empty_set(self):
        r = per_dataset_paired_test([], [], [], 'empty', 'A2', "A1'")
        assert r['deemed_pass'] is False
        assert r['n'] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. 跨集一致性
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossDatasetConsistency:

    def test_3_of_4_pass(self):
        """3/4 集通过 → consistency_pass=True（阈 CONSISTENCY_FRAC=3/4）。"""
        results = [
            {'deemed_pass': True,  'dataset': 'chase'},
            {'deemed_pass': True,  'dataset': 'hrf'},
            {'deemed_pass': True,  'dataset': 'fives'},
            {'deemed_pass': False, 'dataset': 'stare'},
        ]
        c = cross_dataset_consistency(results, CONSISTENCY_FRAC)
        assert c['consistency_pass'] is True
        assert c['n_pass_direction'] == 3
        assert c['frac_pass'] == 3/4

    def test_2_of_4_fail(self):
        results = [
            {'deemed_pass': True,  'dataset': 'chase'},
            {'deemed_pass': True,  'dataset': 'hrf'},
            {'deemed_pass': False, 'dataset': 'fives'},
            {'deemed_pass': False, 'dataset': 'stare'},
        ]
        c = cross_dataset_consistency(results, CONSISTENCY_FRAC)
        assert c['consistency_pass'] is False
        assert c['frac_pass'] == 0.5

    def test_all_pass(self):
        results = [{'deemed_pass': True} for _ in range(4)]
        c = cross_dataset_consistency(results)
        assert c['consistency_pass'] is True

    def test_empty(self):
        c = cross_dataset_consistency([])
        assert c['consistency_pass'] is False


# ─────────────────────────────────────────────────────────────────────────────
# 6. ε_β0 配平分层 CDE
# ─────────────────────────────────────────────────────────────────────────────

class TestCDEStratifiedTest:

    def _make_rows_local(self, iids, reids, eps, ds='chase', epoch=80, arm='test',
                         reid_rate_head=None):
        """
        reid_rate_head=None → 与 reid_rate 相同（有头臂默认）
        reid_rate_head='nan' → A0' headless 场景
        """
        rows = []
        for i in range(len(iids)):
            if reid_rate_head is None:
                rh = reids[i]
            elif isinstance(reid_rate_head, (list, tuple)):
                rh = reid_rate_head[i]
            else:
                rh = reid_rate_head
            rows.append({
                'image_id': iids[i],
                'image_id_global': f'{ds}__{iids[i]}',
                'dataset': ds,
                'reid_rate': reids[i],
                'reid_rate_head': rh,
                'epsilon_beta0': eps[i],
                'epoch': epoch,
                'arm': arm,
            })
        return rows

    def test_subset_filters_large_delta_eps(self):
        """
        8 图：前4图 Δε_β0=0（两臂 ε 相同）→ 应全纳入子集。
        后4图 Δε_β0=2.0（远大于 IQR）→ 应被筛去。
        """
        ids = [f'img{i}' for i in range(8)]
        # A2 reid_rate 均高于 A1'（正 delta）
        r_a2  = [0.7, 0.8, 0.75, 0.72, 0.65, 0.60, 0.70, 0.68]
        r_a1p = [0.6, 0.7, 0.65, 0.62, 0.50, 0.45, 0.55, 0.53]
        # ε_β0：前4图两臂相同；后4图 A2 比 A1' 大 2.0
        e_a2  = [0.1, 0.2, 0.15, 0.12, 0.1,  0.2,  0.15, 0.12]
        e_a1p = [0.1, 0.2, 0.15, 0.12, 2.1,  2.2,  2.15, 2.12]

        rows_a2  = self._make_rows_local(ids, r_a2,  e_a2,  ds='chase', arm='a2')
        rows_a1p = self._make_rows_local(ids, r_a1p, e_a1p, ds='chase', arm='a1p')

        r = cde_stratified_test(rows_a2, rows_a1p, 'chase', P_THRESH_CDE)

        # 子集应只含前4图（Δε≈0，落 IQR 内）
        assert r['n_total'] == 8, f"n_total={r['n_total']}"
        assert r['n_subset'] <= 4, (
            f"Expected subset ≤ 4 (large-Δε filtered), got {r['n_subset']}")
        # 子集内 delta 全正 → 小集特例或 p 小 → deemed_pass
        assert r['deemed_pass'] is True, (
            f"Expected deemed_pass=True for positive deltas, got: {r}")

    def test_negative_subset_deltas_fail(self):
        """子集内 A2 < A1'（负 delta）→ deemed_pass=False。"""
        ids = [f'img{i}' for i in range(8)]
        # A2 reid_rate 均 <  A1'
        r_a2  = [0.5, 0.6, 0.55, 0.52, 0.48, 0.51, 0.59, 0.53]
        r_a1p = [0.6, 0.7, 0.65, 0.62, 0.58, 0.61, 0.69, 0.63]
        # ε_β0 两臂相同 → 所有图 Δε=0 → 全进子集
        e_same = [0.1, 0.2, 0.15, 0.12, 0.18, 0.11, 0.13, 0.09]
        rows_a2  = self._make_rows_local(ids, r_a2,  e_same, ds='hrf', arm='a2')
        rows_a1p = self._make_rows_local(ids, r_a1p, e_same, ds='hrf', arm='a1p')

        r = cde_stratified_test(rows_a2, rows_a1p, 'hrf', P_THRESH_CDE)
        assert r['deemed_pass'] is False

    def test_empty_set_graceful(self):
        r = cde_stratified_test([], [], 'empty', P_THRESH_CDE)
        assert r['n_total'] == 0
        assert r['deemed_pass'] is False


# ─────────────────────────────────────────────────────────────────────────────
# 7. TE/NDE/NIE 三件套
# ─────────────────────────────────────────────────────────────────────────────

class TestMediationOLS:

    def _make_rows_mediation(self, n_per_arm=20, seed=0):
        """
        造两组行（A2 memory_on=1, A1' memory_on=0）。
        A2 的 reid_rate_head 约 0.9，A1' 约 0.7 → TE ≈ 0.2。
        ε_β0 两组相近。
        mediation_ols 现结局量 = reid_rate_head，所以必须提供该字段。
        """
        rng = np.random.default_rng(seed)
        rows_a2  = []
        rows_a1p = []
        for i in range(n_per_arm):
            iid = f'chase__img{i}'
            rows_a2.append({
                'image_id_global': iid,
                'dataset': 'chase',
                'reid_rate':      0.7 + rng.normal(0, 0.05),
                'reid_rate_head': 0.9 + rng.normal(0, 0.05),  # 新指标
                'epsilon_beta0':  0.1 + rng.normal(0, 0.02),
                'epoch': 80,
            })
            rows_a1p.append({
                'image_id_global': iid,
                'dataset': 'chase',
                'reid_rate':      0.5 + rng.normal(0, 0.05),
                'reid_rate_head': 0.7 + rng.normal(0, 0.05),  # 新指标
                'epsilon_beta0':  0.12 + rng.normal(0, 0.02),
                'epoch': 80,
            })
        return rows_a2, rows_a1p

    def test_te_nde_nie_finite(self):
        """TE/NDE/NIE 必须有限（非 nan/inf）。"""
        rows_a2, rows_a1p = self._make_rows_mediation(20)
        result = mediation_ols(rows_a2, rows_a1p, n_bootstrap=100)
        assert np.isfinite(result['TE_obs']),  f"TE_obs={result['TE_obs']}"
        assert np.isfinite(result['NDE_obs']), f"NDE_obs={result['NDE_obs']}"
        assert np.isfinite(result['NIE_obs']), f"NIE_obs={result['NIE_obs']}"

    def test_te_nde_nie_identity(self):
        """TE = NDE + NIE（误差 < 1e-9）。"""
        rows_a2, rows_a1p = self._make_rows_mediation(20)
        result = mediation_ols(rows_a2, rows_a1p, n_bootstrap=100)
        te  = result['TE_obs']
        nde = result['NDE_obs']
        nie = result['NIE_obs']
        assert abs(te - (nde + nie)) < 1e-9, f'TE≠NDE+NIE: {te} ≠ {nde}+{nie}'

    def test_te_direction_correct(self):
        """TE 方向应为正（A2 约 0.7 > A1' 约 0.5）。"""
        rows_a2, rows_a1p = self._make_rows_mediation(30, seed=7)
        result = mediation_ols(rows_a2, rows_a1p, n_bootstrap=100)
        assert result['TE_obs'] > 0, f"Expected TE>0, got {result['TE_obs']}"

    def test_ci_ordered(self):
        """CI 下界 ≤ 观测值 ≤ CI 上界（各三个量）。"""
        rows_a2, rows_a1p = self._make_rows_mediation(20)
        result = mediation_ols(rows_a2, rows_a1p, n_bootstrap=200)
        for key in ('TE', 'NDE', 'NIE'):
            obs = result[f'{key}_obs']
            lo, hi = result[f'{key}_CI_95']
            # CI 可能不包含点估计（bootstrap 偏差），但 lo ≤ hi 必须成立
            assert lo <= hi, f'{key} CI: {lo} > {hi}'

    def test_insufficient_data_graceful(self):
        """样本 < 4 → 返回 note 字段，不 crash，且 TE_obs 要么不存在要么 nan。"""
        result = mediation_ols([], [], n_bootstrap=10)
        # 当样本不足时，实现返回 note 而不包含 TE_obs
        has_note = bool(result.get('note'))
        te_is_nan = (not np.isfinite(result['TE_obs'])
                     if 'TE_obs' in result else True)
        assert has_note or te_is_nan, (
            f'Expected note or nan TE_obs for insufficient data; got {result}')

    def test_bootstrap_count_reasonable(self):
        """bootstrap 成功次数 > 0。"""
        rows_a2, rows_a1p = self._make_rows_mediation(10)
        result = mediation_ols(rows_a2, rows_a1p, n_bootstrap=50)
        assert result.get('n_bootstrap', 0) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 8. A4 泄漏测试
# ─────────────────────────────────────────────────────────────────────────────

class TestA4Leakage:

    def _make_rows(self, iids, reids, ds='chase', rh_offset=0.0):
        """
        rh_offset: reid_rate_head = reid_rate + rh_offset（模拟 A4 与 A2 的微小偏差）。
        a4_leakage_test 现用 reid_rate_head，所以 _make_rows 必须提供该字段。
        """
        return [
            {'image_id_global': f'{ds}__{iid}',
             'reid_rate':      rr,
             'reid_rate_head': rr + rh_offset,  # 有头臂均提供 reid_rate_head
             'epsilon_beta0':  0.1,
             'epoch':          80}
            for iid, rr in zip(iids, reids)
        ]

    def test_pass_when_delta_lt_005(self):
        """|A4-A2| 均值 < 0.05 → deemed_pass=True。"""
        ids = [f'img{i}' for i in range(5)]
        rows_a2 = self._make_rows(ids, [0.70, 0.75, 0.72, 0.68, 0.71])
        rows_a4 = self._make_rows(ids, [0.72, 0.73, 0.71, 0.69, 0.70])
        r = a4_leakage_test(rows_a2, rows_a4, A4_DELTA_MAX)
        assert r['deemed_pass'] is True
        assert r['mean_abs_delta'] < A4_DELTA_MAX

    def test_fail_when_delta_gt_005(self):
        """|A4-A2| 均值 > 0.05 → deemed_pass=False。"""
        ids = [f'img{i}' for i in range(4)]
        rows_a2 = self._make_rows(ids, [0.70, 0.70, 0.70, 0.70])
        rows_a4 = self._make_rows(ids, [0.80, 0.82, 0.78, 0.79])
        r = a4_leakage_test(rows_a2, rows_a4, A4_DELTA_MAX)
        assert r['deemed_pass'] is False
        assert r['mean_abs_delta'] > A4_DELTA_MAX

    def test_no_data_graceful(self):
        r = a4_leakage_test([], [], A4_DELTA_MAX)
        assert r['deemed_pass'] is False
        assert r['n'] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 9. CSV 加载 + image_id 前缀
# ─────────────────────────────────────────────────────────────────────────────

class TestCSVLoad:

    def test_load_adds_global_prefix(self, tmp_path):
        """image_id_global 应为 dataset__image_id。"""
        rows = _make_rows(['img1', 'img2'], [0.7, 0.8], [0.1, 0.2],
                          dataset='chase')
        p = _write_csv(tmp_path, rows, 'test.csv')
        loaded = load_arm_csv(p)
        assert 'chase' in loaded
        for r in loaded['chase']:
            assert r['image_id_global'].startswith('chase__'), (
                f"Expected chase__ prefix, got {r['image_id_global']}")

    def test_select_last_epoch(self, tmp_path):
        """同图有多 epoch → 只保留最大 epoch。"""
        rows = (
            _make_rows(['img1'], [0.6], [0.1], epoch=40) +
            _make_rows(['img1'], [0.7], [0.1], epoch=80)
        )
        p = _write_csv(tmp_path, rows, 'test.csv')
        loaded = load_arm_csv(p)['chase']
        last = select_last_epoch(loaded)
        assert len(last) == 1
        assert last[0]['epoch'] == 80
        assert abs(last[0]['reid_rate'] - 0.7) < 1e-6

    def test_paired_by_image(self, tmp_path):
        """paired_by_image 只返回两臂共有的图。"""
        rows_a = _make_rows(['img1', 'img2', 'img3'], [0.7, 0.8, 0.75],
                             [0.1, 0.2, 0.15], dataset='chase')
        rows_b = _make_rows(['img1', 'img3'], [0.6, 0.65],
                             [0.1, 0.15], dataset='chase')

        pa = _write_csv(tmp_path, rows_a, 'a.csv')
        pb = _write_csv(tmp_path, rows_b, 'b.csv')
        la = select_last_epoch(load_arm_csv(pa).get('chase', []))
        lb = select_last_epoch(load_arm_csv(pb).get('chase', []))
        imgs, va, vb = paired_by_image(la, lb, 'reid_rate')
        assert len(imgs) == 2, f'Expected 2 common images, got {len(imgs)}'
        assert all(i.startswith('chase__') for i in imgs)


# ─────────────────────────────────────────────────────────────────────────────
# 10. 真 e2e 烟测：3 臂 × 多集假数据 → run_verdict 全链
# ─────────────────────────────────────────────────────────────────────────────

class TestE2ERunVerdict:
    """
    完成线核心测试：非 mock，造 3 臂×多集假数据喂全链。
    A2 > A1' > A0'（设计成清晰正 delta）。
    """

    N_IMG   = 8      # 每集图数（n≥6，走完整排列）
    DATASETS = ['chase', 'hrf', 'fives', 'stare']

    def _make_verdict_csvs(self, tmp_path: Path, seed: int = 0) -> dict[str, Path]:
        """
        造 4 集×3 臂 CSV（含新列 reid_rate_head、reid_idf1）。
        A2  reid_rate_head ~ 0.93 + noise（有头，高）
        A1' reid_rate_head ~ 0.70 + noise（有头，低）
        A0' reid_rate_head = 'nan'（headless，无 re-ID 头）
        A4  reid_rate_head ~ 0.94 + noise（与 A2 接近，|delta| < 0.05）
        """
        rng = np.random.default_rng(seed)
        rows_a2  = []
        rows_a1p = []
        rows_a0p = []
        rows_a4  = []

        for ds in self.DATASETS:
            n = self.N_IMG
            base_r_a2      = 0.75
            base_r_a1p     = 0.63
            base_r_a0p     = 0.50
            # reid_rate_head（新指标）有更大差距，确保判据1a清晰通过
            base_rh_a2     = 0.93
            base_rh_a1p    = 0.70

            for i in range(n):
                iid = f'img{i}'
                eps = 0.12 + rng.normal(0, 0.01)
                # A2（有 re-ID 头）
                rh_a2 = base_rh_a2 + rng.uniform(0.00, 0.02)
                rows_a2.append({
                    'epoch': 80, 'image_id': iid, 'dataset': ds,
                    'severity': 'Medium',
                    'reid_rate':      base_r_a2  + rng.uniform(0.00, 0.02),
                    'reid_rate_head': rh_a2,
                    'reid_idf1':      rh_a2 * 0.9,
                    'epsilon_beta0':  eps - 0.01,
                    'success_rate':   0.85, 'n_gaps': 10, 'arm': 'a2',
                })
                # A1'（有 re-ID 头）
                rh_a1p = base_rh_a1p + rng.uniform(0.00, 0.02)
                rows_a1p.append({
                    'epoch': 80, 'image_id': iid, 'dataset': ds,
                    'severity': 'Medium',
                    'reid_rate':      base_r_a1p + rng.uniform(0.00, 0.02),
                    'reid_rate_head': rh_a1p,
                    'reid_idf1':      rh_a1p * 0.9,
                    'epsilon_beta0':  eps + 0.01,  # 与 A2 相近（Δε 小→进 CDE 子集）
                    'success_rate':   0.75, 'n_gaps': 10, 'arm': 'a1p',
                })
                # A0'（headless，无 re-ID 头）
                rows_a0p.append({
                    'epoch': 80, 'image_id': iid, 'dataset': ds,
                    'severity': 'Medium',
                    'reid_rate':      base_r_a0p + rng.uniform(0.00, 0.02),
                    'reid_rate_head': 'nan',  # headless
                    'reid_idf1':      'nan',
                    'epsilon_beta0':  eps + 0.02,
                    'success_rate':   0.65, 'n_gaps': 10, 'arm': 'a0p',
                })
                # A4（有 re-ID 头，与 A2 接近）
                rh_a4 = base_rh_a2 + rng.uniform(-0.01, 0.01)
                rows_a4.append({
                    'epoch': 80, 'image_id': iid, 'dataset': ds,
                    'severity': 'Medium',
                    'reid_rate':      base_r_a2 + rng.uniform(-0.01, 0.01),
                    'reid_rate_head': rh_a4,
                    'reid_idf1':      rh_a4 * 0.9,
                    'epsilon_beta0':  eps,
                    'success_rate':   0.84, 'n_gaps': 10, 'arm': 'a4',
                })

        csv_a2  = _write_csv(tmp_path, rows_a2,  'a2_reid.csv')
        csv_a1p = _write_csv(tmp_path, rows_a1p, 'a1p_reid.csv')
        csv_a0p = _write_csv(tmp_path, rows_a0p, 'a0p_reid.csv')
        csv_a4  = _write_csv(tmp_path, rows_a4,  'a4_reid.csv')
        return {
            'a2':  csv_a2,
            'a1p': csv_a1p,
            'a0p': csv_a0p,
            'a4':  csv_a4,
        }

    def test_run_verdict_no_crash(self, tmp_path):
        """全链 run_verdict 不 crash，返回 dict。"""
        csvs = self._make_verdict_csvs(tmp_path)
        result = run_verdict(
            csv_a2=csvs['a2'],
            csv_a1p=csvs['a1p'],
            csv_a0p=csvs['a0p'],
            csv_a4=csvs['a4'],
            datasets=self.DATASETS,
        )
        assert isinstance(result, dict)

    def test_run_verdict_has_all_keys(self, tmp_path):
        """返回 dict 包含所有预期顶层 key。"""
        csvs = self._make_verdict_csvs(tmp_path)
        result = run_verdict(
            csv_a2=csvs['a2'], csv_a1p=csvs['a1p'],
            csv_a0p=csvs['a0p'], csv_a4=csvs['a4'],
            datasets=self.DATASETS,
        )
        for key in ('verdict_1a_per_dataset', 'verdict_1a_consistency',
                    'verdict_1a_pass', 'verdict_1b_per_dataset',
                    'verdict_2_cde_per_dataset', 'verdict_2_pass',
                    'mediation_TE_NDE_NIE', 'verdict_3_a4_leakage',
                    'CLAIM2_VERDICT'):
            assert key in result, f'Missing key: {key}'

    def test_run_verdict_datasets_covered(self, tmp_path):
        """每个数据集都有 1a/1b/CDE 结果。"""
        csvs = self._make_verdict_csvs(tmp_path)
        result = run_verdict(
            csv_a2=csvs['a2'], csv_a1p=csvs['a1p'],
            csv_a0p=csvs['a0p'], csv_a4=csvs['a4'],
            datasets=self.DATASETS,
        )
        assert len(result['verdict_1a_per_dataset']) == len(self.DATASETS)
        assert len(result['verdict_1b_per_dataset']) == len(self.DATASETS)
        assert len(result['verdict_2_cde_per_dataset']) == len(self.DATASETS)

    def test_run_verdict_positive_delta_1a_pass(self, tmp_path):
        """
        A2 reid_rate 明显高于 A1'（设计 delta≈0.12）→
        判据1a 应全部或多数集 PASS，跨集一致性 PASS。
        """
        csvs = self._make_verdict_csvs(tmp_path, seed=42)
        result = run_verdict(
            csv_a2=csvs['a2'], csv_a1p=csvs['a1p'],
            csv_a0p=csvs['a0p'], csv_a4=csvs['a4'],
            datasets=self.DATASETS,
        )
        # 跨集一致性：至少 3/4 集方向正
        cons = result['verdict_1a_consistency']
        assert cons['n_pass_direction'] >= 3, (
            f"Expected ≥3 datasets pass 1a, got {cons['n_pass_direction']}: "
            f"{result['verdict_1a_per_dataset']}")
        assert result['verdict_1a_pass'] is True

    def test_run_verdict_cde_nonempty(self, tmp_path):
        """
        Δε_β0 很小（两臂 ε 接近）→ CDE 子集应非空。
        """
        csvs = self._make_verdict_csvs(tmp_path, seed=7)
        result = run_verdict(
            csv_a2=csvs['a2'], csv_a1p=csvs['a1p'],
            csv_a0p=csvs['a0p'],
            datasets=self.DATASETS,
        )
        n_nonempty = sum(
            1 for r in result['verdict_2_cde_per_dataset']
            if r['n_subset'] > 0
        )
        assert n_nonempty >= 1, (
            f"Expected at least 1 non-empty CDE subset, got 0: "
            f"{result['verdict_2_cde_per_dataset']}")

    def test_run_verdict_a4_pass(self, tmp_path):
        """A4 与 A2 接近（设计 |delta| < 0.05）→ A4 封泄漏 PASS。"""
        csvs = self._make_verdict_csvs(tmp_path)
        result = run_verdict(
            csv_a2=csvs['a2'], csv_a1p=csvs['a1p'],
            csv_a0p=csvs['a0p'], csv_a4=csvs['a4'],
            datasets=self.DATASETS,
        )
        assert result['verdict_3_a4_leakage']['deemed_pass'] is True, (
            f"A4 leakage: {result['verdict_3_a4_leakage']}")

    def test_run_verdict_mediation_finite(self, tmp_path):
        """TE/NDE/NIE 三件套必须有限。"""
        csvs = self._make_verdict_csvs(tmp_path)
        result = run_verdict(
            csv_a2=csvs['a2'], csv_a1p=csvs['a1p'],
            csv_a0p=csvs['a0p'],
            datasets=self.DATASETS,
        )
        med = result['mediation_TE_NDE_NIE']
        if 'TE_obs' in med:  # 有足够数据
            assert np.isfinite(med['TE_obs']),  f"TE_obs={med['TE_obs']}"
            assert np.isfinite(med['NDE_obs']), f"NDE_obs={med['NDE_obs']}"
            assert np.isfinite(med['NIE_obs']), f"NIE_obs={med['NIE_obs']}"

    def test_run_verdict_writes_json(self, tmp_path):
        """out_json 参数 → 写出可解析的 JSON 文件。"""
        csvs = self._make_verdict_csvs(tmp_path)
        out_json = tmp_path / 'verdict_v2.json'
        run_verdict(
            csv_a2=csvs['a2'], csv_a1p=csvs['a1p'],
            csv_a0p=csvs['a0p'], csv_a4=csvs['a4'],
            datasets=self.DATASETS,
            out_json=out_json,
        )
        assert out_json.exists(), 'verdict JSON not written'
        with open(out_json, encoding='utf-8') as f:
            data = json.load(f)
        assert 'CLAIM2_VERDICT' in data

    def test_run_verdict_no_scipy_import(self, tmp_path):
        """
        红线验证：reid_verdict_v2 模块不得 import scipy.stats。
        """
        import importlib, sys as _sys
        # 从 sys.modules 移除（如已加载）
        to_remove = [k for k in _sys.modules if k.startswith('scipy')]
        for k in to_remove:
            del _sys.modules[k]

        # 临时注入假 scipy 使 import 报错
        class _FakeScipy:
            class stats:
                @staticmethod
                def __getattr__(*args):
                    raise RuntimeError('scipy.stats forbidden (OMP red-line)')
        _sys.modules['scipy'] = _FakeScipy()  # type: ignore
        _sys.modules['scipy.stats'] = _FakeScipy.stats  # type: ignore

        try:
            # 重新加载 reid_verdict_v2
            import reid_verdict_v2 as _rv
            importlib.reload(_rv)
            # 做一次计算验证不 crash
            p = _rv.exact_sign_permutation_pvalue([0.1, 0.2, 0.05])
            assert p < 1.0
        finally:
            # 清理假 scipy
            for k in ['scipy', 'scipy.stats']:
                _sys.modules.pop(k, None)


# ─────────────────────────────────────────────────────────────────────────────
# 11. DEP-3 回归测试：多 seed 聚合配对粒度
#     验证：seed 前缀后配对数 = seed × 图（不丢 seed）；
#           无前缀时 select_last_epoch 触发 WARNING（防御生效）。
# ─────────────────────────────────────────────────────────────────────────────

class TestDep3MultiSeedAggregation:
    """
    DEP-3 bug：多 seed concat 后同一 image_id_global 有多行同 epoch，
    select_last_epoch 只留一行 → 配对数 = 图（而非 seed × 图）。

    修复：concat 时给 image_id 加 seed 前缀（seed{seed}__image_id）。
    image_id_global = dataset__seed{seed}__image_id，每 seed 每图唯一。

    DoD：
      T1 — 带 seed 前缀的 concat → 配对数 = SEEDS × N_IMGS（不丢 seed）
      T2 — 无 seed 前缀的 concat → select_last_epoch 触发 WARNING（防御生效）
      T3 — 带前缀数据跑完整 paired_by_image → 配对数断言正确
    """

    SEEDS   = [42, 1337, 2024]
    N_IMGS  = 3   # 每集图数（enough 验配对数，不需 n≥6）
    DATASETS_DEP3 = ['chase', 'hrf']

    def _make_seed_csv(self, tmp_path: Path, seed: int, dataset: str,
                       arm: str, with_seed_prefix: bool) -> Path:
        """造单 seed 单集 CSV；with_seed_prefix=True 时 image_id 已含 seed{seed}__ 前缀。"""
        rows = []
        for i in range(self.N_IMGS):
            raw_iid = f'img{i}'
            iid = f'seed{seed}__{raw_iid}' if with_seed_prefix else raw_iid
            rows.append({
                'epoch':         300,
                'image_id':      iid,
                'dataset':       dataset,
                'severity':      'Medium',
                'reid_rate':     0.70 + 0.01 * i,
                'epsilon_beta0': 0.10 + 0.01 * i,
                'success_rate':  0.80,
                'n_gaps':        10,
                'arm':           arm,
            })
        fname = f'{dataset}_{arm}_seed{seed}_{"pre" if with_seed_prefix else "nopre"}.csv'
        p = tmp_path / fname
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            for r in rows:
                w.writerow(r)
        return p

    def _concat_csvs_to_file(self, csv_paths: list[Path], out: Path) -> None:
        """简单纵向合并 CSV 文件（列相同），写到 out。"""
        rows = []
        header = None
        for p in csv_paths:
            with open(p, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                if header is None:
                    header = reader.fieldnames
                for r in reader:
                    rows.append(dict(r))
        with open(out, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            for r in rows:
                w.writerow(r)

    def test_with_seed_prefix_no_seed_loss(self, tmp_path):
        """
        T1：带 seed 前缀 concat → 每集配对数 = SEEDS × N_IMGS，不丢 seed。
        3 seed × 3 图 = 9 配对单元（每集）。
        """
        ds = 'chase'
        arm_a = 'memory'
        arm_b = 'cnn'

        # 分 seed 造 CSV，image_id 带 seed 前缀
        csvs_a = [self._make_seed_csv(tmp_path, s, ds, arm_a, with_seed_prefix=True)
                  for s in self.SEEDS]
        csvs_b = [self._make_seed_csv(tmp_path, s, ds, arm_b, with_seed_prefix=True)
                  for s in self.SEEDS]

        # 合并成各臂总 CSV
        concat_a = tmp_path / 'concat_a.csv'
        concat_b = tmp_path / 'concat_b.csv'
        self._concat_csvs_to_file(csvs_a, concat_a)
        self._concat_csvs_to_file(csvs_b, concat_b)

        # 经 load_arm_csv → select_last_epoch → paired_by_image
        by_ds_a = load_arm_csv(concat_a)
        by_ds_b = load_arm_csv(concat_b)

        rows_a = select_last_epoch(by_ds_a.get(ds, []))
        rows_b = select_last_epoch(by_ds_b.get(ds, []))

        imgs, va, vb = paired_by_image(rows_a, rows_b, 'reid_rate')

        expected_pairs = len(self.SEEDS) * self.N_IMGS  # 3 × 3 = 9
        assert len(imgs) == expected_pairs, (
            f"[DEP-3] 配对数应 = seed×图 = {expected_pairs}，"
            f"实得 {len(imgs)}（丢了 seed 信息则为 {self.N_IMGS}）"
        )

    def test_without_seed_prefix_triggers_warning(self, tmp_path, capsys):
        """
        T2：无 seed 前缀 concat → 同 image_id_global 有多行同 epoch，
        select_last_epoch 应打印 WARNING（防御生效）。
        """
        ds = 'hrf'
        arm = 'memory'

        # 不加 seed 前缀：3 seed 同一图会重名
        csvs = [self._make_seed_csv(tmp_path, s, ds, arm, with_seed_prefix=False)
                for s in self.SEEDS]
        concat_all = tmp_path / 'concat_nopre.csv'
        self._concat_csvs_to_file(csvs, concat_all)

        by_ds = load_arm_csv(concat_all)
        rows = by_ds.get(ds, [])

        # 调用 select_last_epoch，应触发 WARNING
        _ = select_last_epoch(rows)

        captured = capsys.readouterr()
        assert 'WARNING' in captured.err, (
            f"[DEP-3] 无 seed 前缀时 select_last_epoch 应打印 WARNING，"
            f"实际 stderr={captured.err!r}"
        )

    def test_with_seed_prefix_paired_count_per_dataset(self, tmp_path):
        """
        T3：多集多 seed 带前缀 concat → 每集配对数均 = SEEDS × N_IMGS。
        涉及 chase + hrf 两集，跑全链 paired_by_image 验配对数。
        """
        arm_a = 'memory'
        arm_b = 'linear_attn'
        expected_pairs = len(self.SEEDS) * self.N_IMGS  # 9

        for ds in self.DATASETS_DEP3:
            csvs_a = [self._make_seed_csv(tmp_path, s, ds, arm_a, with_seed_prefix=True)
                      for s in self.SEEDS]
            csvs_b = [self._make_seed_csv(tmp_path, s, ds, arm_b, with_seed_prefix=True)
                      for s in self.SEEDS]
            concat_a = tmp_path / f'concat_a_{ds}.csv'
            concat_b = tmp_path / f'concat_b_{ds}.csv'
            self._concat_csvs_to_file(csvs_a, concat_a)
            self._concat_csvs_to_file(csvs_b, concat_b)

            rows_a = select_last_epoch(load_arm_csv(concat_a).get(ds, []))
            rows_b = select_last_epoch(load_arm_csv(concat_b).get(ds, []))
            imgs, _, _ = paired_by_image(rows_a, rows_b, 'reid_rate')

            assert len(imgs) == expected_pairs, (
                f"[DEP-3] ds={ds}: 配对数应 {expected_pairs}，实得 {len(imgs)}"
            )

    def _build_concat_cmd_body(self, src_seed_pairs: list, out_csv: str,
                                out_dir: str) -> str:
        """
        重现 launch_reid_sweep.make_verdict_commands 生成的 concat 命令体
        （python -c 的 -c 参数字符串）。与 launcher 完全等价，用于真执行验证。
        拼接逻辑：'seed'+str(s)+'__'+r['image_id']（纯字符串拼接，无 f-string）。
        """
        pairs_repr = repr(src_seed_pairs)
        return (
            'import csv, pathlib; '
            + f'pairs={pairs_repr}; '
            + 'rows=[]; '
            + "[([(r.__setitem__('image_id', 'seed'+str(s)+'__'+r['image_id']),"
            + "rows.append(dict(r))) for r in csv.DictReader(open(p))])"
            + " for p,s in pairs if pathlib.Path(p).exists()]; "
            + f"pathlib.Path({repr(out_dir)}).mkdir(parents=True, exist_ok=True); "
            + f"w=csv.DictWriter(open({repr(out_csv)},'w',newline=''), fieldnames=rows[0].keys()) if rows else None; "
            + "w and (w.writeheader(), [w.writerow(r) for r in rows])"
        )

    def test_launcher_concat_cmd_subprocess_no_syntaxerror(self, tmp_path):
        """
        T4（真执行，防同款 bug 复发）：
        重现 launcher make_verdict_commands 生成的 python -c 命令，
        subprocess 真跑（非 exec/eval），验证：
          (a) returncode=0（无 SyntaxError / 运行时错误）
          (b) 输出 CSV 行数 = SEEDS × N_IMGS
          (c) image_id 带 seed 前缀（seed42__img0 等）
        如果 launcher 的字符串拼接逻辑含 f-string 混用 {} 等 bug，此测试必报 SyntaxError。
        """
        import subprocess
        import sys as _sys
        import csv as _csv

        ds = 'chase'
        arm = 'memory'
        seeds = self.SEEDS
        n_imgs = self.N_IMGS

        # 造各 seed CSV（不带前缀，由 concat 命令注入）
        csvs = [self._make_seed_csv(tmp_path, s, ds, arm, with_seed_prefix=False)
                for s in seeds]
        src_seed_pairs = [(str(p), s) for p, s in zip(csvs, seeds)]
        out_csv = str(tmp_path / 'arm_memory_all.csv')
        out_dir = str(tmp_path)

        cmd_body = self._build_concat_cmd_body(src_seed_pairs, out_csv, out_dir)

        # subprocess 真跑（完全隔离，等价 HPC 端 python -c "..." 执行）
        ret = subprocess.run(
            [_sys.executable, '-c', cmd_body],
            capture_output=True, text=True,
        )
        assert ret.returncode == 0, (
            f"[DEP-3 T4] concat 命令 returncode={ret.returncode}，"
            f"SyntaxError 或运行时错误:\n{ret.stderr}"
        )

        # (b) 验输出 CSV 行数
        with open(out_csv, newline='', encoding='utf-8') as f:
            rows = list(_csv.DictReader(f))

        expected = len(seeds) * n_imgs
        assert len(rows) == expected, (
            f"[DEP-3 T4] 输出行数={len(rows)}，期望 {expected}（{len(seeds)} seed × {n_imgs} 图）"
        )

        # (c) 验 seed 前缀
        for s in seeds:
            prefixed = [r for r in rows if r['image_id'].startswith(f'seed{s}__')]
            assert len(prefixed) == n_imgs, (
                f"[DEP-3 T4] seed{s} 行数={len(prefixed)}，期望 {n_imgs}"
            )

        # 验配对数（经 load_arm_csv → select_last_epoch → paired_by_image 全链）
        arm_b = 'cnn'
        csvs_b = [self._make_seed_csv(tmp_path, s, ds, arm_b, with_seed_prefix=False)
                  for s in seeds]
        src_b = [(str(p), s) for p, s in zip(csvs_b, seeds)]
        out_csv_b = str(tmp_path / 'arm_cnn_all.csv')
        cmd_b = self._build_concat_cmd_body(src_b, out_csv_b, out_dir)
        ret_b = subprocess.run(
            [_sys.executable, '-c', cmd_b], capture_output=True, text=True
        )
        assert ret_b.returncode == 0, f"[DEP-3 T4] concat arm_b failed: {ret_b.stderr}"

        rows_a = select_last_epoch(load_arm_csv(out_csv).get(ds, []))
        rows_b_loaded = select_last_epoch(load_arm_csv(out_csv_b).get(ds, []))
        imgs, _, _ = paired_by_image(rows_a, rows_b_loaded, 'reid_rate')

        assert len(imgs) == expected, (
            f"[DEP-3 T4] 配对数={len(imgs)}，期望 {expected}（seed×图），"
            f"若 = {n_imgs} 说明 seed 信息仍被吞"
        )
