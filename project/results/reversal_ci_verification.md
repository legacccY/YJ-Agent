# TS-Reversal Bootstrap-CI Verification — 溯源记录

**目的**：为 BMVC §5.2 / Appendix A1 的「TS reversal 三路前向分解」点估计补上 95% bootstrap 置信区间，硬化 rebuttal 防御（投稿版只有点估计）。

**结论**：翻转方向稳健，所有 CI 不过零；TS 那步 Δρ≈10⁻⁶（数学保证）。

---

## 复现命令

```bash
cd D:/YJ-Agent/project
python scripts/verify_reversal_ci.py
```

## 溯源

| 项 | 值 |
|---|---|
| 运行日期 | 2026-06-12 12:23 CST |
| git HEAD | `496385c4` |
| 脚本 | `scripts/verify_reversal_ci.py` |
| 输入数据 | `results/forward_ablation_stdvib.csv`（n=2820，ITB-LQ+HQ pooled）|
| 输入 md5 | `cfbe10d3da7b775a9141730ef76beae5` |
| 输入生成脚本 | `scripts/attack6_forward_ablation.py`（ckpt `checkpoints/stdvib/best_qad.pth`, seed 42, MC 前向）|
| 输出 | `results/reversal_ci_verification.csv` |
| bootstrap | B=5000，固定 `rng seed=0`（CI 可复现）|

## 结果（与投稿数字逐字对齐）

| 量 | 值 | 95% CI | 过零? |
|---|---|---|---|
| ρ_a（MC 前向）| **−0.1632** | [−0.1996, −0.1270] | 否 |
| ρ_b（确定性-μ, T=1）| **+0.2406** | [+0.2066, +0.2751] | 否 |
| ρ_c（确定性-μ + TS）| +0.2406 | [+0.2065, +0.2743] | 否 |
| Δρ a→b（翻转主因）| **+0.4039** | [+0.3440, +0.4633] | **否** |
| Δρ b→c（TS 那步）| −7×10⁻⁶ | — | — |

- 投稿版 ρ_a=−0.163 / ρ_b=+0.241 ← 本次重算 −0.1632 / +0.2406，**一字不差**。
- ρ_a 整条 CI 在负、ρ_b 整条 CI 在正，两区间互不重叠且均远离 0。
- Δρ a→b 的 CI [+0.34, +0.46] 不过零 → 翻转非噪声、大幅稳健。
- Δρ b→c = −7×10⁻⁶ 对上论文「<10⁻⁵」→ TS 单调缩放不改秩（Prop ts_rank 的实证确认）。

## 一句话防御（rebuttal 可直接引）

> The a→b entropy-quality correlation flip (Δρ=+0.40, 95% bootstrap CI [+0.34, +0.46], n=2820) does not cross zero; the b→c TS step changes ρ by <10⁻⁵, confirming scalar TS preserves rank. Reversal is driven entirely by the MC→deterministic forward swap, not by TS as a calibrator.

## 范围与边界（诚实记录）

- 本验证为**单 seed（42）**，但 n=2820、CI 离 0 很远 → 主结论稳。
- **跨 seed 未补**：seed 123/2024 的预测文件（`itb_predictions_s{123,2024}.csv`）只存单路 `prob_pos`，无 MC vs 确定性分路；补跨 seed 需 stdvib 各 seed checkpoint（本地未找到，疑在 HPC 或已清）。属锦上添花，非命门。
- **未触碰 BMVC 封印目录**：脚本、CSV、本 md 全在 `results/` 与 `scripts/`。
