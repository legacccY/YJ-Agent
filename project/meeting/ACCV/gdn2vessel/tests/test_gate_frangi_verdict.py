"""
test_gate_frangi_verdict.py — gate_frangi_verdict.py 的完整测试套件。

覆盖：
  1. 符号检验手算正确性（已知 p 验证）
  2. Wilcoxon 手算正确性（方向一致性）
  3. Bootstrap CI 下界（正 delta 集 → CI>0）
  4. 配对逻辑（on/off 按 image_id+seed 配对）
  5. 单集 PASS 分支（gap≥0.03 + p<0.05 + CI>0 + 正方向）
  6. 单集 FAIL 分支（gap<0.03 / p≥0.05 / CI≤0 / 负方向）
  7. 全局 PASS：DRIVE+CHASE 两集都正向 + ≥1 集达 P1+P2
  8. 全局 FAIL：两集方向相反（P3 violated）
  9. CSV 加载（arm 归一化 / dataset 小写 / NaN 容忍）
  10. no-scipy 红线（禁 scipy.stats）

红线：
  - 禁 scipy.stats（OMP Error #15）
  - 阈值硬编码核对（GAP_THRESH=0.03, P_THRESH=0.05）
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pytest

# ─────────────────────────────────────────────────────────────────────────────
# 路径 setup
# ─────────────────────────────────────────────────────────────────────────────
_repo_root  = Path(__file__).parent.parent
_scripts_dir = _repo_root / 'scripts'
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from gate_frangi_verdict import (
    sign_test_pvalue,
    wilcoxon_signed_rank_pvalue,
    bootstrap_ci_lower,
    paired_gate_deltas,
    dataset_verdict,
    run_verdict,
    load_metrics_csv,
    GAP_THRESH,
    P_THRESH,
    N_BOOTSTRAP,
    DATASETS,
)


# ─────────────────────────────────────────────────────────────────────────────
# 工具：写 mock CSV
# ─────────────────────────────────────────────────────────────────────────────
_GATE_CSV_HEADER = ['image_id', 'dataset', 'seed', 'arm',
                    'cldice', 'epsilon_beta0', 'betti_err_total']


def _write_gate_csv(tmp_path: Path, rows: list[dict], fname: str) -> Path:
    p = tmp_path / fname
    with open(p, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=_GATE_CSV_HEADER)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, 'nan') for k in _GATE_CSV_HEADER})
    return p


def _make_gate_rows(image_ids: list[str],
                    cldice_on: list[float],
                    cldice_off: list[float],
                    dataset: str = 'drive',
                    seed: int = 42,
                    eps_on: float = 0.10,
                    eps_off: float = 0.15,
                    betti_on: float = 1.0,
                    betti_off: float = 1.5) -> list[dict]:
    """生成 gate-on + gate-off 两组行。"""
    rows = []
    for iid, von, voff in zip(image_ids, cldice_on, cldice_off):
        rows.append({'image_id': iid, 'dataset': dataset, 'seed': seed,
                     'arm': 'gate-on',  'cldice': von,
                     'epsilon_beta0': eps_on,   'betti_err_total': betti_on})
        rows.append({'image_id': iid, 'dataset': dataset, 'seed': seed,
                     'arm': 'gate-off', 'cldice': voff,
                     'epsilon_beta0': eps_off,  'betti_err_total': betti_off})
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# 0. 常量核对（禁跑完改阈值）
# ─────────────────────────────────────────────────────────────────────────────
class TestConstants:

    def test_gap_thresh(self):
        assert GAP_THRESH == 0.03, f'GAP_THRESH 应为 0.03，得 {GAP_THRESH}'

    def test_p_thresh(self):
        assert P_THRESH == 0.05, f'P_THRESH 应为 0.05，得 {P_THRESH}'

    def test_n_bootstrap(self):
        assert N_BOOTSTRAP >= 1000, f'N_BOOTSTRAP 应 ≥1000，得 {N_BOOTSTRAP}'

    def test_datasets(self):
        assert 'drive' in DATASETS and 'chase' in DATASETS


# ─────────────────────────────────────────────────────────────────────────────
# 1. 符号检验
# ─────────────────────────────────────────────────────────────────────────────
class TestSignTest:

    def test_all_positive_n8(self):
        """n=8 全正 → p = 1/256 ≈ 0.00391。"""
        d = [0.1, 0.2, 0.05, 0.15, 0.08, 0.12, 0.18, 0.07]
        p = sign_test_pvalue(np.array(d), 'greater')
        assert abs(p - 1.0 / 256.0) < 1e-5, f'Expected ~{1/256:.6f}, got {p:.6f}'

    def test_all_negative_n8(self):
        """n=8 全负 → p = 1.0（H1:greater 不支持）。"""
        d = [-0.1, -0.2, -0.05, -0.15]
        p = sign_test_pvalue(np.array(d), 'greater')
        assert p >= 0.9, f'Expected p≈1 for all-neg, got {p}'

    def test_empty_returns_1(self):
        p = sign_test_pvalue(np.array([]), 'greater')
        assert p == 1.0

    def test_single_positive(self):
        """n=1 正 → p = 0.5。"""
        p = sign_test_pvalue(np.array([0.5]), 'greater')
        assert abs(p - 0.5) < 1e-9

    def test_n4_all_positive_exact(self):
        """n=4 全正 → p = 1/16 = 0.0625。"""
        p = sign_test_pvalue(np.array([0.05, 0.08, 0.12, 0.03]), 'greater')
        assert abs(p - 1.0 / 16.0) < 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# 2. Wilcoxon 手算
# ─────────────────────────────────────────────────────────────────────────────
class TestWilcoxon:

    def test_all_positive_n12(self):
        """n=12 全正 → p 很小。"""
        d = [0.05 * i for i in range(1, 13)]
        p = wilcoxon_signed_rank_pvalue(np.array(d), 'greater')
        assert p < 0.01, f'Expected p<0.01 for large positive, got {p}'

    def test_all_negative_large_p(self):
        d = [-0.1 * i for i in range(1, 9)]
        p = wilcoxon_signed_rank_pvalue(np.array(d), 'greater')
        assert p > 0.5, f'Expected p>0.5 for all-neg, got {p}'

    def test_empty_returns_1(self):
        p = wilcoxon_signed_rank_pvalue(np.array([]), 'greater')
        assert p == 1.0

    def test_zero_deltas_returns_1(self):
        p = wilcoxon_signed_rank_pvalue(np.array([0.0, 0.0, 0.0]), 'greater')
        assert p == 1.0

    def test_direction_consistent_with_sign_test(self):
        """正 delta: 两者都给小 p。"""
        d = [0.08, 0.12, 0.09, 0.15, 0.06, 0.10, 0.11, 0.07, 0.13, 0.14]
        ps = sign_test_pvalue(np.array(d))
        pw = wilcoxon_signed_rank_pvalue(np.array(d))
        assert ps < 0.05 and pw < 0.05


# ─────────────────────────────────────────────────────────────────────────────
# 3. Bootstrap CI
# ─────────────────────────────────────────────────────────────────────────────
class TestBootstrapCI:

    def test_positive_deltas_ci_positive(self):
        """全正 delta → 95% CI 下界 > 0。"""
        d = np.array([0.04, 0.05, 0.06, 0.05, 0.04, 0.07, 0.06, 0.05])
        ci_lo = bootstrap_ci_lower(d, n_resample=2000, rng_seed=0)
        assert ci_lo > 0.0, f'Expected CI_lo>0 for positive deltas, got {ci_lo}'

    def test_negative_deltas_ci_negative(self):
        """全负 delta → CI 下界 < 0。"""
        d = np.array([-0.04, -0.05, -0.06, -0.04, -0.05, -0.07])
        ci_lo = bootstrap_ci_lower(d, n_resample=1000, rng_seed=1)
        assert ci_lo < 0.0, f'Expected CI_lo<0 for negative deltas, got {ci_lo}'

    def test_empty_returns_neg_inf(self):
        ci_lo = bootstrap_ci_lower(np.array([]))
        assert ci_lo == float('-inf')


# ─────────────────────────────────────────────────────────────────────────────
# 4. 配对逻辑
# ─────────────────────────────────────────────────────────────────────────────
class TestPairedGateDeltas:

    def test_paired_basic(self):
        """6 图配对 → n_pairs=6，delta=on-off。"""
        iids = [f'img{i}' for i in range(6)]
        rows = _make_gate_rows(iids,
                               cldice_on=[0.8] * 6,
                               cldice_off=[0.7] * 6,
                               seed=42)
        deltas, info = paired_gate_deltas(rows, metric='cldice')
        assert len(deltas) == 6
        assert all(abs(d - 0.1) < 1e-9 for d in deltas)
        assert info['n_pairs'] == 6

    def test_partial_pairs_missing_off(self):
        """gate-off 只有 3 图 → 只配对 3 对。"""
        rows = []
        for i in range(6):
            rows.append({'image_id': f'img{i}', 'dataset': 'drive', 'seed': 42,
                         'arm': 'gate-on', 'cldice': 0.8,
                         'epsilon_beta0': 0.1, 'betti_err_total': 1.0})
        for i in range(3):
            rows.append({'image_id': f'img{i}', 'dataset': 'drive', 'seed': 42,
                         'arm': 'gate-off', 'cldice': 0.7,
                         'epsilon_beta0': 0.15, 'betti_err_total': 1.5})
        deltas, info = paired_gate_deltas(rows, 'cldice')
        assert len(deltas) == 3, f'Expected 3 pairs, got {len(deltas)}'

    def test_multi_seed_pairing(self):
        """3 seed × 4 图 → 12 配对（不丢 seed）。"""
        rows = []
        for seed in [42, 1337, 2024]:
            for i in range(4):
                rows.append({'image_id': f'img{i}', 'dataset': 'drive', 'seed': seed,
                             'arm': 'gate-on', 'cldice': 0.8,
                             'epsilon_beta0': 0.1, 'betti_err_total': 1.0})
                rows.append({'image_id': f'img{i}', 'dataset': 'drive', 'seed': seed,
                             'arm': 'gate-off', 'cldice': 0.7,
                             'epsilon_beta0': 0.15, 'betti_err_total': 1.5})
        deltas, info = paired_gate_deltas(rows, 'cldice')
        assert len(deltas) == 12, f'Expected 12 pairs (3seed×4img), got {len(deltas)}'

    def test_empty_rows(self):
        deltas, info = paired_gate_deltas([], 'cldice')
        assert len(deltas) == 0 and info['n_pairs'] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. 单集 dataset_verdict PASS 分支
# ─────────────────────────────────────────────────────────────────────────────
class TestDatasetVerdictPass:

    def test_clear_pass(self):
        """
        DRIVE: 12 配对（3seed×4img），on≈0.85 off≈0.70 → gap≈0.15≥0.03,
        p<0.05, CI>0 → dataset_pass=True。
        """
        iids = [f'img{i}' for i in range(4)]
        rows = []
        for seed in [42, 1337, 2024]:
            r = _make_gate_rows(
                iids,
                cldice_on=[0.85, 0.84, 0.86, 0.83],
                cldice_off=[0.70, 0.71, 0.69, 0.72],
                dataset='drive', seed=seed)
            rows.extend(r)
        v = dataset_verdict(rows, 'drive', metric='cldice')
        assert v['dataset_pass'] is True, f'Expected PASS, got: {v}'
        assert v['gap'] >= GAP_THRESH
        assert v['p_used'] < P_THRESH
        assert v['boot_ci_lower'] > 0.0
        assert v['direction_positive'] is True

    def test_gap_exactly_threshold(self):
        """gap 恰好 ≥ 0.03 → gap_ok=True（边界）。"""
        iids = [f'img{i}' for i in range(8)]
        on_vals  = [0.730] * 8
        off_vals = [0.700] * 8  # gap = 0.030 ≥ GAP_THRESH
        rows = _make_gate_rows(iids, on_vals, off_vals, dataset='drive')
        v = dataset_verdict(rows, 'drive', metric='cldice')
        assert v['gap_ok'] is True, f'gap={v["gap"]!r} should be ≥ {GAP_THRESH}'


# ─────────────────────────────────────────────────────────────────────────────
# 6. 单集 dataset_verdict FAIL 分支
# ─────────────────────────────────────────────────────────────────────────────
class TestDatasetVerdictFail:

    def test_gap_too_small(self):
        """gap = 0.01 < 0.03 → FAIL。"""
        iids = [f'img{i}' for i in range(8)]
        on_vals  = [0.710] * 8
        off_vals = [0.700] * 8  # gap = 0.01
        rows = _make_gate_rows(iids, on_vals, off_vals, dataset='drive')
        v = dataset_verdict(rows, 'drive', metric='cldice')
        assert v['dataset_pass'] is False
        assert not v['gap_ok']

    def test_negative_direction(self):
        """on < off（负方向）→ FAIL。"""
        iids = [f'img{i}' for i in range(8)]
        on_vals  = [0.65] * 8
        off_vals = [0.80] * 8  # on < off
        rows = _make_gate_rows(iids, on_vals, off_vals, dataset='chase')
        v = dataset_verdict(rows, 'chase', metric='cldice')
        assert v['dataset_pass'] is False
        assert not v['direction_positive']

    def test_empty_dataset(self):
        """无行 → FAIL。"""
        v = dataset_verdict([], 'drive', metric='cldice')
        assert v['dataset_pass'] is False
        assert v['n_pairs'] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 7. 全局 run_verdict PASS（DRIVE+CHASE 两集正向 + ≥1 集 P1+P2）
# ─────────────────────────────────────────────────────────────────────────────
class TestRunVerdictPass:

    def _make_clear_pass_rows(self, n_per_seed: int = 4) -> dict:
        """DRIVE+CHASE 各 3seed×n 图，on≈0.85 off≈0.70 → 大 gap，明确 PASS。"""
        rows_by_ds: dict = {}
        for ds in ['drive', 'chase']:
            rows = []
            for seed in [42, 1337, 2024]:
                iids = [f'img{i}' for i in range(n_per_seed)]
                on_vals  = [0.85 + 0.01 * i for i in range(n_per_seed)]
                off_vals = [0.70 + 0.01 * i for i in range(n_per_seed)]
                rows.extend(_make_gate_rows(iids, on_vals, off_vals,
                                            dataset=ds, seed=seed))
            rows_by_ds[ds] = rows
        return rows_by_ds

    def test_global_pass(self):
        rows = self._make_clear_pass_rows()
        v = run_verdict(rows, datasets=['drive', 'chase'])
        assert v['global_pass'] is True, f'Expected PASS, fail_reasons={v["fail_reasons"]}'
        assert v['VERDICT'] == 'PASS'

    def test_both_datasets_in_result(self):
        rows = self._make_clear_pass_rows()
        v = run_verdict(rows, datasets=['drive', 'chase'])
        ds_in_result = {d['dataset'] for d in v['per_dataset_cldice']}
        assert 'drive' in ds_in_result and 'chase' in ds_in_result

    def test_aux_metrics_present(self):
        """辅助指标 aux_epsilon_beta0 / aux_betti_err 存在（非空）。"""
        rows = self._make_clear_pass_rows()
        v = run_verdict(rows, datasets=['drive', 'chase'])
        assert len(v['aux_epsilon_beta0']) >= 1
        assert len(v['aux_betti_err']) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# 8. 全局 run_verdict FAIL（P3：两集方向相反）
# ─────────────────────────────────────────────────────────────────────────────
class TestRunVerdictFail:

    def test_opposite_direction_fail(self):
        """DRIVE on>off，CHASE on<off → P3 violated → global FAIL。"""
        iids = [f'img{i}' for i in range(6)]
        rows_by_ds = {
            'drive': _make_gate_rows(iids,
                                     cldice_on=[0.85]*6, cldice_off=[0.70]*6,
                                     dataset='drive'),
            'chase': _make_gate_rows(iids,
                                     cldice_on=[0.60]*6, cldice_off=[0.80]*6,
                                     dataset='chase'),
        }
        v = run_verdict(rows_by_ds, datasets=['drive', 'chase'])
        assert v['global_pass'] is False
        assert any('P3' in r or 'direction' in r.lower()
                   for r in v['fail_reasons']), f'fail_reasons={v["fail_reasons"]}'

    def test_gap_too_small_fail(self):
        """两集 gap=0.005 < 0.03 → global FAIL。"""
        iids = [f'img{i}' for i in range(6)]
        rows_by_ds = {ds: _make_gate_rows(
            iids,
            cldice_on=[0.705]*6, cldice_off=[0.700]*6,  # gap=0.005
            dataset=ds) for ds in ['drive', 'chase']}
        v = run_verdict(rows_by_ds, datasets=['drive', 'chase'])
        assert v['global_pass'] is False

    def test_empty_both_datasets_fail(self):
        """两集均无数据 → global FAIL。"""
        v = run_verdict({}, datasets=['drive', 'chase'])
        assert v['global_pass'] is False


# ─────────────────────────────────────────────────────────────────────────────
# 9. CSV 加载
# ─────────────────────────────────────────────────────────────────────────────
class TestCSVLoad:

    def test_load_basic(self, tmp_path):
        iids = ['img0', 'img1', 'img2']
        rows = _make_gate_rows(iids, [0.8]*3, [0.7]*3, dataset='drive')
        p = _write_gate_csv(tmp_path, rows, 'test.csv')
        by_ds = load_metrics_csv([p])
        assert 'drive' in by_ds
        assert len(by_ds['drive']) == 6  # 3 on + 3 off

    def test_dataset_lowercased(self, tmp_path):
        """dataset 字段大写 DRIVE → 归一小写 drive。"""
        rows = [{'image_id': 'img0', 'dataset': 'DRIVE', 'seed': 42,
                 'arm': 'gate-on', 'cldice': 0.8,
                 'epsilon_beta0': 0.1, 'betti_err_total': 1.0}]
        p = _write_gate_csv(tmp_path, rows, 'upper.csv')
        by_ds = load_metrics_csv([p])
        assert 'drive' in by_ds, f'Keys: {list(by_ds)}'
        assert 'DRIVE' not in by_ds

    def test_arm_normalization(self, tmp_path):
        """arm='gate_on' / '1' / 'on' 都归一为 'gate-on'。"""
        rows = [
            {'image_id': 'img0', 'dataset': 'drive', 'seed': 42,
             'arm': 'gate_on', 'cldice': 0.8,
             'epsilon_beta0': 0.1, 'betti_err_total': 1.0},
            {'image_id': 'img1', 'dataset': 'drive', 'seed': 42,
             'arm': '1', 'cldice': 0.8,
             'epsilon_beta0': 0.1, 'betti_err_total': 1.0},
            {'image_id': 'img2', 'dataset': 'drive', 'seed': 42,
             'arm': 'gate-off', 'cldice': 0.7,
             'epsilon_beta0': 0.15, 'betti_err_total': 1.5},
        ]
        p = _write_gate_csv(tmp_path, rows, 'arm_norm.csv')
        by_ds = load_metrics_csv([p])
        arms = {r['arm'] for r in by_ds['drive']}
        assert 'gate-on' in arms, f'Arms: {arms}'
        assert 'gate_on' not in arms and '1' not in arms

    def test_nan_tolerance(self, tmp_path):
        """cldice='nan' → 不 crash，加载为 float('nan')。"""
        rows = [{'image_id': 'img0', 'dataset': 'drive', 'seed': 42,
                 'arm': 'gate-on', 'cldice': 'nan',
                 'epsilon_beta0': 'nan', 'betti_err_total': 'nan'}]
        p = _write_gate_csv(tmp_path, rows, 'nan.csv')
        by_ds = load_metrics_csv([p])
        r = by_ds['drive'][0]
        assert np.isnan(r['cldice'])
        assert np.isnan(r['epsilon_beta0'])

    def test_multi_csv_concat(self, tmp_path):
        """多个 CSV 文件合并（不同 arm/seed）。"""
        iids = ['img0', 'img1']
        p1 = _write_gate_csv(tmp_path,
                              [{'image_id': i, 'dataset': 'drive', 'seed': 42,
                                'arm': 'gate-on', 'cldice': 0.8,
                                'epsilon_beta0': 0.1, 'betti_err_total': 1.0}
                               for i in iids], 'on.csv')
        p2 = _write_gate_csv(tmp_path,
                              [{'image_id': i, 'dataset': 'drive', 'seed': 42,
                                'arm': 'gate-off', 'cldice': 0.7,
                                'epsilon_beta0': 0.15, 'betti_err_total': 1.5}
                               for i in iids], 'off.csv')
        by_ds = load_metrics_csv([p1, p2])
        assert len(by_ds['drive']) == 4


# ─────────────────────────────────────────────────────────────────────────────
# 10. 红线：禁 scipy.stats
# ─────────────────────────────────────────────────────────────────────────────
class TestNoScipy:

    def test_no_scipy_stats_import(self):
        """
        gate_frangi_verdict 模块不得 import scipy.stats。
        注入假 scipy → 运算不应触发 RuntimeError。
        """
        import importlib
        import sys as _sys

        # 移除已加载的 scipy
        to_remove = [k for k in _sys.modules if k.startswith('scipy')]
        for k in to_remove:
            del _sys.modules[k]

        class _FakeScipy:
            class stats:
                @staticmethod
                def __getattr__(*args):
                    raise RuntimeError('scipy.stats forbidden (OMP red-line)')
        _sys.modules['scipy'] = _FakeScipy()          # type: ignore
        _sys.modules['scipy.stats'] = _FakeScipy.stats  # type: ignore

        try:
            import gate_frangi_verdict as _gfv
            importlib.reload(_gfv)
            # 做一次计算验证不 crash
            p = _gfv.sign_test_pvalue(np.array([0.05, 0.1, 0.08]))
            assert p < 1.0
        finally:
            for k in ['scipy', 'scipy.stats']:
                _sys.modules.pop(k, None)


# ─────────────────────────────────────────────────────────────────────────────
# 11. 全链 e2e：合成 12run（DRIVE+CHASE × gate-on/off × 3seed）→ run_verdict
# ─────────────────────────────────────────────────────────────────────────────
class TestE2ERunVerdict:
    """
    完整端对端：造 12 run CSV（2集×2臂×3seed×4图/run），
    通过 load_metrics_csv → run_verdict 验证全链。
    """

    SEEDS    = [42, 1337, 2024]
    N_IMGS   = 4
    DATASETS_ = ['drive', 'chase']

    def _make_12run_rows(self, on_off_gap: float = 0.10) -> dict:
        """造 12run 数据，返回 {dataset: rows}。"""
        rows_by_ds: dict = {}
        for ds in self.DATASETS_:
            rows = []
            for seed in self.SEEDS:
                iids = [f'img{i}' for i in range(self.N_IMGS)]
                on_vals  = [0.80 + on_off_gap * 0.5] * self.N_IMGS
                off_vals = [0.80 - on_off_gap * 0.5] * self.N_IMGS
                rows.extend(_make_gate_rows(iids, on_vals, off_vals,
                                            dataset=ds, seed=seed))
            rows_by_ds[ds] = rows
        return rows_by_ds

    def test_12run_clear_pass(self, tmp_path):
        """gap=0.10 → 明确 PASS。"""
        rows = self._make_12run_rows(on_off_gap=0.10)
        v = run_verdict(rows, datasets=self.DATASETS_)
        assert v['global_pass'] is True, f'fail_reasons={v["fail_reasons"]}'
        assert v['VERDICT'] == 'PASS'

    def test_12run_small_gap_fail(self, tmp_path):
        """gap=0.01 < 0.03 → FAIL。"""
        rows = self._make_12run_rows(on_off_gap=0.01)
        v = run_verdict(rows, datasets=self.DATASETS_)
        assert v['global_pass'] is False

    def test_via_csv_roundtrip(self, tmp_path):
        """
        CSV 写出 → load_metrics_csv → run_verdict 全链，
        验证 CSV 格式与 load 逻辑无缝衔接。
        """
        rows = self._make_12run_rows(on_off_gap=0.12)
        # 写各 run CSV（每 dataset 一个 CSV 含所有 seed+arm）
        csv_paths = []
        for ds, ds_rows in rows.items():
            p = _write_gate_csv(tmp_path, ds_rows, f'{ds}_all.csv')
            csv_paths.append(p)

        loaded = load_metrics_csv(csv_paths)
        v = run_verdict(loaded, datasets=self.DATASETS_)
        assert v['global_pass'] is True, f'CSV roundtrip verdict={v}'

    def test_verdict_json_serializable(self):
        """run_verdict 返回 dict 必须 json.dumps 不抛异常。"""
        rows = self._make_12run_rows()
        v = run_verdict(rows, datasets=self.DATASETS_)
        out = json.dumps(v, ensure_ascii=False)
        reloaded = json.loads(out)
        assert reloaded['VERDICT'] in ('PASS', 'FAIL')
