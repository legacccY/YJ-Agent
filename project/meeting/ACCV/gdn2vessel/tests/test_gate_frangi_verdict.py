"""
test_gate_frangi_verdict.py — gate_frangi_verdict.py 的完整测试套件。

覆盖：
  1.  符号检验手算正确性（已知 p 验证）
  2.  Wilcoxon 手算正确性（方向一致性）
  3.  Bootstrap CI 下界（正 delta 集 → CI>0）
  4.  配对逻辑（on/off 按 image_id+seed 配对）
  5.  单集 PASS 分支（gap≥0.03 + p<0.05 + CI>0 + 正方向）
  6.  单集 FAIL 分支（gap<0.03 / p≥0.05 / CI≤0 / 负方向）
  7.  全局 PASS：DRIVE+CHASE 两集都正向 + ≥1 集达 P1+P2
  8.  全局 FAIL：两集方向相反（P3 violated）
  9.  CSV 加载（arm 从目录名推断 / dataset 小写 / NaN 容忍）
  9a. arm 推断：infer_arm_from_dirpath 从目录名正确推断 gate-on/gate-off
  9b. epoch 去重：同 (image_id,seed,arm) 多行取最大 epoch
  10. no-scipy 红线（禁 scipy.stats）

红线：
  - 禁 scipy.stats（OMP Error #15）
  - 阈值硬编码核对（GAP_THRESH=0.03, P_THRESH=0.05）
  - arm 不读 csv 内列（csv 内 arm='memory'），从目录名推断
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
    infer_arm_from_dirpath,
    GAP_THRESH,
    P_THRESH,
    N_BOOTSTRAP,
    DATASETS,
)


# ─────────────────────────────────────────────────────────────────────────────
# 工具：写 mock CSV（模拟真实 reid_results.csv 格式）
# ─────────────────────────────────────────────────────────────────────────────
# 真实列集（epoch 字段 + arm='memory' 模拟真实训练产出）
_GATE_CSV_HEADER = ['epoch', 'image_id', 'dataset', 'seed', 'arm',
                    'cldice', 'epsilon_beta0', 'betti_err_total']


def _write_gate_csv(path: Path, rows: list[dict]) -> Path:
    """写 CSV 到 path（path 必须是完整文件路径，包含目录）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=_GATE_CSV_HEADER)
        w.writeheader()
        for row in rows:
            # arm 写 'memory'（模拟真实训练产出，arm 推断靠目录名）
            out_row = {k: row.get(k, 'nan') for k in _GATE_CSV_HEADER}
            out_row['arm'] = 'memory'  # 真实 csv 里 arm 列 = reid_feat_source
            w.writerow(out_row)
    return path


def _write_gate_csv_in_dir(tmp_path: Path,
                            rows: list[dict],
                            dir_name: str,
                            fname: str = 'reid_results.csv') -> Path:
    """
    在 tmp_path/<dir_name>/<fname> 写 csv。
    dir_name 应含 'gate_on' 或 'gate_off'（让 infer_arm_from_dirpath 能推断）。
    """
    return _write_gate_csv(tmp_path / dir_name / fname, rows)


def _make_gate_rows(image_ids: list[str],
                    cldice_on: list[float],
                    cldice_off: list[float],
                    dataset: str = 'drive',
                    seed: int = 42,
                    epoch: int = 1,
                    eps_on: float = 0.10,
                    eps_off: float = 0.15,
                    betti_on: float = 1.0,
                    betti_off: float = 1.5) -> tuple[list[dict], list[dict]]:
    """
    生成 gate-on 和 gate-off 两组行（分开返回，便于写入不同目录）。

    返回 (on_rows, off_rows)，调用方分别写入 gate_on_xxx/ 和 gate_off_xxx/ 目录。
    arm 字段不写入 csv（写 'memory'），由目录名推断。
    """
    on_rows, off_rows = [], []
    for iid, von, voff in zip(image_ids, cldice_on, cldice_off):
        on_rows.append({
            'epoch': epoch, 'image_id': iid, 'dataset': dataset, 'seed': seed,
            'cldice': von,  'epsilon_beta0': eps_on,  'betti_err_total': betti_on,
        })
        off_rows.append({
            'epoch': epoch, 'image_id': iid, 'dataset': dataset, 'seed': seed,
            'cldice': voff, 'epsilon_beta0': eps_off, 'betti_err_total': betti_off,
        })
    return on_rows, off_rows


def _make_and_write_gate_pair(tmp_path: Path,
                               image_ids: list[str],
                               cldice_on: list[float],
                               cldice_off: list[float],
                               dataset: str = 'drive',
                               seed: int = 42,
                               epoch: int = 1,
                               tag: str = '') -> tuple[Path, Path]:
    """
    一站式：生成 gate-on/off 行并写入对应目录，返回 (on_csv_path, off_csv_path)。

    目录命名：gate_on_{dataset}_s{seed}{tag} / gate_off_{dataset}_s{seed}{tag}
    """
    on_rows, off_rows = _make_gate_rows(
        image_ids, cldice_on, cldice_off, dataset=dataset, seed=seed, epoch=epoch)
    on_dir  = f'gate_on_{dataset}_s{seed}{tag}'
    off_dir = f'gate_off_{dataset}_s{seed}{tag}'
    on_path  = _write_gate_csv_in_dir(tmp_path, on_rows,  on_dir)
    off_path = _write_gate_csv_in_dir(tmp_path, off_rows, off_dir)
    return on_path, off_path


def _make_rows_direct(image_ids: list[str],
                      cldice_on: list[float],
                      cldice_off: list[float],
                      dataset: str = 'drive',
                      seed: int = 42,
                      eps_on: float = 0.10,
                      eps_off: float = 0.15,
                      betti_on: float = 1.0,
                      betti_off: float = 1.5) -> list[dict]:
    """
    直接生成已含 arm 字段的 row 列表（用于 unit test 直接调 paired_gate_deltas /
    dataset_verdict / run_verdict，不走 CSV，不需要目录名推断）。
    """
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
        rows = _make_rows_direct(iids,
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
            r = _make_rows_direct(
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
        rows = _make_rows_direct(iids, on_vals, off_vals, dataset='drive')
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
        rows = _make_rows_direct(iids, on_vals, off_vals, dataset='drive')
        v = dataset_verdict(rows, 'drive', metric='cldice')
        assert v['dataset_pass'] is False
        assert not v['gap_ok']

    def test_negative_direction(self):
        """on < off（负方向）→ FAIL。"""
        iids = [f'img{i}' for i in range(8)]
        on_vals  = [0.65] * 8
        off_vals = [0.80] * 8  # on < off
        rows = _make_rows_direct(iids, on_vals, off_vals, dataset='chase')
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
                rows.extend(_make_rows_direct(iids, on_vals, off_vals,
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
            'drive': _make_rows_direct(iids,
                                       cldice_on=[0.85]*6, cldice_off=[0.70]*6,
                                       dataset='drive'),
            'chase': _make_rows_direct(iids,
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
        rows_by_ds = {ds: _make_rows_direct(
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
# 9a. infer_arm_from_dirpath 单元测试
# ─────────────────────────────────────────────────────────────────────────────
class TestInferArm:
    """验证 arm 从目录名正确推断，不读 csv 内 arm 列。"""

    def test_gate_on_underscore(self, tmp_path):
        """目录名含 gate_on → 'gate-on'。"""
        p = tmp_path / 'gate_on_drive_s0' / 'reid_results.csv'
        assert infer_arm_from_dirpath(p) == 'gate-on'

    def test_gate_off_underscore(self, tmp_path):
        """目录名含 gate_off → 'gate-off'。"""
        p = tmp_path / 'gate_off_chase_s1337' / 'reid_results.csv'
        assert infer_arm_from_dirpath(p) == 'gate-off'

    def test_gate_on_hyphen(self, tmp_path):
        """目录名含 gate-on（连字符）→ 'gate-on'。"""
        p = tmp_path / 'gate-on_drive_s2024' / 'reid_results.csv'
        assert infer_arm_from_dirpath(p) == 'gate-on'

    def test_gate_off_hyphen(self, tmp_path):
        """目录名含 gate-off（连字符）→ 'gate-off'。"""
        p = tmp_path / 'gate-off_drive_s0' / 'reid_results.csv'
        assert infer_arm_from_dirpath(p) == 'gate-off'

    def test_gate_on_uppercase(self, tmp_path):
        """大写 GATE_ON → 归一小写后识别。"""
        p = tmp_path / 'GATE_ON_drive' / 'metrics.csv'
        assert infer_arm_from_dirpath(p) == 'gate-on'

    def test_unknown_dir_returns_none(self, tmp_path):
        """无 gate_on/gate_off 字样 → None。"""
        p = tmp_path / 'baseline_run' / 'reid_results.csv'
        assert infer_arm_from_dirpath(p) is None

    def test_memory_arm_in_dir_name_irrelevant(self, tmp_path):
        """目录名含 'memory' 但不含 gate_on/off → None（不误匹配）。"""
        p = tmp_path / 'gate_sweep_memory_s0' / 'reid_results.csv'
        # 'gate_sweep_memory' 不含 gate_on 或 gate_off 作为独立子串
        result = infer_arm_from_dirpath(p)
        assert result is None

    def test_gate_on_in_grandparent(self, tmp_path):
        """gate_on 出现在祖父目录名 → 'gate-on'（检查两级）。"""
        p = tmp_path / 'gate_on_exp' / 'subdir' / 'reid_results.csv'
        # parent.name = 'subdir'（无 gate_on）, parent.parent.name = 'gate_on_exp'
        assert infer_arm_from_dirpath(p) == 'gate-on'


# ─────────────────────────────────────────────────────────────────────────────
# 9. CSV 加载（arm 从目录名推断）
# ─────────────────────────────────────────────────────────────────────────────
class TestCSVLoad:

    def test_load_basic_via_dirname(self, tmp_path):
        """arm 从目录名推断：gate_on_drive_s0/ + gate_off_drive_s0/ → 各 3 行，共 6 行。"""
        iids = ['img0', 'img1', 'img2']
        on_path, off_path = _make_and_write_gate_pair(
            tmp_path, iids, [0.8]*3, [0.7]*3, dataset='drive', seed=42)
        by_ds = load_metrics_csv([on_path, off_path])
        assert 'drive' in by_ds
        assert len(by_ds['drive']) == 6  # 3 on + 3 off
        arms = {r['arm'] for r in by_ds['drive']}
        assert arms == {'gate-on', 'gate-off'}, f'Expected both arms, got {arms}'

    def test_arm_from_dirname_not_csv_column(self, tmp_path):
        """
        csv 内 arm 列 = 'memory'，arm 应从目录名推断（gate-on），不是 'memory'。
        """
        on_path, _ = _make_and_write_gate_pair(
            tmp_path, ['img0'], [0.8], [0.7], dataset='drive', seed=42, tag='_test')
        by_ds = load_metrics_csv([on_path])
        assert 'drive' in by_ds
        r = by_ds['drive'][0]
        assert r['arm'] == 'gate-on', f'arm should be gate-on from dirname, got {r["arm"]!r}'

    def test_dataset_lowercased(self, tmp_path):
        """dataset 字段大写 DRIVE → 归一小写 drive。"""
        row = {'epoch': 1, 'image_id': 'img0', 'dataset': 'DRIVE', 'seed': 42,
               'cldice': 0.8, 'epsilon_beta0': 0.1, 'betti_err_total': 1.0}
        p = _write_gate_csv(tmp_path / 'gate_on_DRIVE_s0' / 'reid_results.csv', [row])
        by_ds = load_metrics_csv([p])
        assert 'drive' in by_ds, f'Keys: {list(by_ds)}'
        assert 'DRIVE' not in by_ds

    def test_nan_tolerance(self, tmp_path):
        """cldice='nan' → 不 crash，加载为 float('nan')。"""
        row = {'epoch': 1, 'image_id': 'img0', 'dataset': 'drive', 'seed': 42,
               'cldice': 'nan', 'epsilon_beta0': 'nan', 'betti_err_total': 'nan'}
        p = _write_gate_csv(tmp_path / 'gate_on_drive_s0' / 'reid_results.csv', [row])
        by_ds = load_metrics_csv([p])
        r = by_ds['drive'][0]
        assert np.isnan(r['cldice'])
        assert np.isnan(r['epsilon_beta0'])

    def test_epoch_dedup_last_epoch_wins(self, tmp_path):
        """
        同 (image_id, seed, arm) 多 epoch 行 → 只保留最大 epoch 行。
        epoch=1 cldice=0.7, epoch=5 cldice=0.85 → 保留 epoch=5 的 0.85。
        """
        rows = [
            {'epoch': 1, 'image_id': 'img0', 'dataset': 'drive', 'seed': 42,
             'cldice': 0.70, 'epsilon_beta0': 0.15, 'betti_err_total': 1.5},
            {'epoch': 5, 'image_id': 'img0', 'dataset': 'drive', 'seed': 42,
             'cldice': 0.85, 'epsilon_beta0': 0.10, 'betti_err_total': 1.0},
            {'epoch': 3, 'image_id': 'img0', 'dataset': 'drive', 'seed': 42,
             'cldice': 0.78, 'epsilon_beta0': 0.12, 'betti_err_total': 1.2},
        ]
        p = _write_gate_csv(tmp_path / 'gate_on_drive_s42' / 'reid_results.csv', rows)
        by_ds = load_metrics_csv([p])
        assert 'drive' in by_ds
        drive_rows = by_ds['drive']
        assert len(drive_rows) == 1, f'Expected 1 row after dedup, got {len(drive_rows)}'
        assert abs(drive_rows[0]['cldice'] - 0.85) < 1e-9, (
            f'Expected epoch=5 cldice=0.85, got {drive_rows[0]["cldice"]}')
        assert drive_rows[0]['epoch'] == 5

    def test_multi_csv_concat_via_dirname(self, tmp_path):
        """多个 CSV（gate_on / gate_off 目录）合并，共 4 行。"""
        iids = ['img0', 'img1']
        on_path, off_path = _make_and_write_gate_pair(
            tmp_path, iids, [0.8, 0.82], [0.7, 0.71], dataset='drive', seed=42)
        by_ds = load_metrics_csv([on_path, off_path])
        assert len(by_ds['drive']) == 4, f'Expected 4 rows, got {len(by_ds["drive"])}'

    def test_unknown_dir_rows_skipped(self, tmp_path):
        """
        目录名无 gate_on/off，csv 内 arm='memory'（真实产出）→ 行被跳过，
        不 crash，drive 无数据（返回空 dict）。
        """
        row = {'epoch': 1, 'image_id': 'img0', 'dataset': 'drive', 'seed': 42,
               'cldice': 0.8, 'epsilon_beta0': 0.1, 'betti_err_total': 1.0}
        p = _write_gate_csv(tmp_path / 'baseline_run' / 'reid_results.csv', [row])
        by_ds = load_metrics_csv([p])
        # arm='memory' 无法从目录名推断 → 行跳过 → drive 无数据
        assert by_ds.get('drive', []) == [], f'Should be empty, got {by_ds.get("drive")}'


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
    arm 从目录名推断，通过 load_metrics_csv → run_verdict 验证全链。
    """

    SEEDS     = [42, 1337, 2024]
    N_IMGS    = 4
    DATASETS_ = ['drive', 'chase']

    def _make_12run_rows_direct(self, on_off_gap: float = 0.10) -> dict:
        """造 12run 数据（直接行，含 arm 字段），返回 {dataset: rows}。用于跳 CSV 直测。"""
        rows_by_ds: dict = {}
        for ds in self.DATASETS_:
            rows = []
            for seed in self.SEEDS:
                iids = [f'img{i}' for i in range(self.N_IMGS)]
                on_vals  = [0.80 + on_off_gap * 0.5] * self.N_IMGS
                off_vals = [0.80 - on_off_gap * 0.5] * self.N_IMGS
                rows.extend(_make_rows_direct(iids, on_vals, off_vals,
                                              dataset=ds, seed=seed))
            rows_by_ds[ds] = rows
        return rows_by_ds

    def _write_12run_csvs(self, tmp_path: Path,
                           on_off_gap: float = 0.10) -> list:
        """
        写真实目录结构 12 run CSV（arm 从目录名推断），返回 csv 路径列表。
        结构：tmp_path/gate_{on/off}_{ds}_s{seed}/reid_results.csv
        """
        csv_paths = []
        for ds in self.DATASETS_:
            for seed in self.SEEDS:
                iids = [f'img{i}' for i in range(self.N_IMGS)]
                on_vals  = [0.80 + on_off_gap * 0.5] * self.N_IMGS
                off_vals = [0.80 - on_off_gap * 0.5] * self.N_IMGS
                on_p, off_p = _make_and_write_gate_pair(
                    tmp_path, iids, on_vals, off_vals, dataset=ds, seed=seed)
                csv_paths.extend([on_p, off_p])
        return csv_paths

    def test_12run_clear_pass_direct(self):
        """gap=0.10 直接行 → 明确 PASS（绕 CSV 快路径）。"""
        rows = self._make_12run_rows_direct(on_off_gap=0.10)
        v = run_verdict(rows, datasets=self.DATASETS_)
        assert v['global_pass'] is True, f'fail_reasons={v["fail_reasons"]}'
        assert v['VERDICT'] == 'PASS'

    def test_12run_small_gap_fail_direct(self):
        """gap=0.01 < 0.03 直接行 → FAIL。"""
        rows = self._make_12run_rows_direct(on_off_gap=0.01)
        v = run_verdict(rows, datasets=self.DATASETS_)
        assert v['global_pass'] is False

    def test_via_csv_roundtrip_dirname(self, tmp_path):
        """
        CSV 写入目录（gate_on_xxx/gate_off_xxx）→ load_metrics_csv 从目录名推 arm
        → run_verdict 全链，验证真实场景配对正确（gap=0.12 → PASS）。

        这是修 arm 配对 bug 后的核心回归测试：
        - csv 内 arm 列='memory'（不是 gate-on/gate-off）
        - arm 靠目录名 gate_on_*/gate_off_* 推断
        - 配对键 (image_id, seed) 正确产生 12对/集
        """
        csv_paths = self._write_12run_csvs(tmp_path, on_off_gap=0.12)
        loaded = load_metrics_csv(csv_paths)

        # 验证每集都有 gate-on 和 gate-off 行（配对前置检查）
        for ds in self.DATASETS_:
            arms_found = {r['arm'] for r in loaded.get(ds, [])}
            assert 'gate-on'  in arms_found, f'{ds}: missing gate-on rows'
            assert 'gate-off' in arms_found, f'{ds}: missing gate-off rows'
            n_on  = sum(1 for r in loaded[ds] if r['arm'] == 'gate-on')
            n_off = sum(1 for r in loaded[ds] if r['arm'] == 'gate-off')
            assert n_on == self.N_IMGS * len(self.SEEDS), (
                f'{ds}: expected {self.N_IMGS * len(self.SEEDS)} on-rows, got {n_on}')
            assert n_off == n_on, f'{ds}: on={n_on} off={n_off} mismatch'

        v = run_verdict(loaded, datasets=self.DATASETS_)
        assert v['global_pass'] is True, (
            f'CSV roundtrip with dirname-arm should PASS, got: '
            f'verdict={v["VERDICT"]}, fail_reasons={v["fail_reasons"]}, '
            f'per_dataset={[(d["dataset"], d["gap"], d["n_pairs"]) for d in v["per_dataset_cldice"]]}')

    def test_verdict_json_serializable(self):
        """run_verdict 返回 dict 必须 json.dumps 不抛异常。"""
        rows = self._make_12run_rows_direct()
        v = run_verdict(rows, datasets=self.DATASETS_)
        out = json.dumps(v, ensure_ascii=False)
        reloaded = json.loads(out)
        assert reloaded['VERDICT'] in ('PASS', 'FAIL')
