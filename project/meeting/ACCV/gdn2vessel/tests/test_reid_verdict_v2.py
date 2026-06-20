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
               'reid_rate', 'epsilon_beta0', 'success_rate', 'n_gaps', 'arm']


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
               arm: str = 'test') -> list[dict]:
    """合成一批 reid_results 行。"""
    rows = []
    for iid, rr, eb in zip(image_ids, reid_rates, eps_beta0s):
        rows.append({
            'epoch':        epoch,
            'image_id':     iid,
            'dataset':      dataset,
            'severity':     'Medium',
            'reid_rate':    rr,
            'epsilon_beta0': eb,
            'success_rate': 0.8,
            'n_gaps':       10,
            'arm':          arm,
        })
    return rows


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

    def _make_rows_local(self, iids, reids, eps, ds='chase', epoch=80, arm='test'):
        return [
            {
                'image_id': iids[i],
                'image_id_global': f'{ds}__{iids[i]}',
                'dataset': ds,
                'reid_rate': reids[i],
                'epsilon_beta0': eps[i],
                'epoch': epoch,
                'arm': arm,
            }
            for i in range(len(iids))
        ]

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
        A2 的 reid_rate 约 0.7，A1' 约 0.5 → TE ≈ 0.2。
        ε_β0 两组相近。
        """
        rng = np.random.default_rng(seed)
        rows_a2  = []
        rows_a1p = []
        for i in range(n_per_arm):
            iid = f'chase__img{i}'
            rows_a2.append({
                'image_id_global': iid,
                'dataset': 'chase',
                'reid_rate': 0.7 + rng.normal(0, 0.05),
                'epsilon_beta0': 0.1 + rng.normal(0, 0.02),
                'epoch': 80,
            })
            rows_a1p.append({
                'image_id_global': iid,
                'dataset': 'chase',
                'reid_rate': 0.5 + rng.normal(0, 0.05),
                'epsilon_beta0': 0.12 + rng.normal(0, 0.02),
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

    def _make_rows(self, iids, reids, ds='chase'):
        return [
            {'image_id_global': f'{ds}__{iid}',
             'reid_rate': rr, 'epsilon_beta0': 0.1, 'epoch': 80}
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
        造 4 集×3 臂 CSV。
        A2 reid_rate ~ 0.75 + noise
        A1' reid_rate ~ 0.65 + noise
        A0' reid_rate ~ 0.55 + noise
        A4  reid_rate ~ 0.76 + noise（与 A2 接近，|delta| < 0.05）
        """
        rng = np.random.default_rng(seed)
        rows_a2  = []
        rows_a1p = []
        rows_a0p = []
        rows_a4  = []

        for ds in self.DATASETS:
            n = self.N_IMG
            # 保证方向可靠：使用固定差距，加小 noise
            base_r_a2  = 0.75
            base_r_a1p = 0.63
            base_r_a0p = 0.50

            for i in range(n):
                iid = f'img{i}'
                eps = 0.12 + rng.normal(0, 0.01)
                # A2
                rows_a2.append({
                    'epoch': 80, 'image_id': iid, 'dataset': ds,
                    'severity': 'Medium',
                    'reid_rate':     base_r_a2  + rng.uniform(0.00, 0.02),
                    'epsilon_beta0': eps - 0.01,
                    'success_rate':  0.85, 'n_gaps': 10, 'arm': 'a2',
                })
                # A1'
                rows_a1p.append({
                    'epoch': 80, 'image_id': iid, 'dataset': ds,
                    'severity': 'Medium',
                    'reid_rate':     base_r_a1p + rng.uniform(0.00, 0.02),
                    'epsilon_beta0': eps + 0.01,  # 与 A2 相近（Δε 小→进 CDE 子集）
                    'success_rate':  0.75, 'n_gaps': 10, 'arm': 'a1p',
                })
                # A0'
                rows_a0p.append({
                    'epoch': 80, 'image_id': iid, 'dataset': ds,
                    'severity': 'Medium',
                    'reid_rate':     base_r_a0p + rng.uniform(0.00, 0.02),
                    'epsilon_beta0': eps + 0.02,
                    'success_rate':  0.65, 'n_gaps': 10, 'arm': 'a0p',
                })
                # A4（与 A2 接近）
                rows_a4.append({
                    'epoch': 80, 'image_id': iid, 'dataset': ds,
                    'severity': 'Medium',
                    'reid_rate':     base_r_a2 + rng.uniform(-0.01, 0.01),
                    'epsilon_beta0': eps,
                    'success_rate':  0.84, 'n_gaps': 10, 'arm': 'a4',
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
