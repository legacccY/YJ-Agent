# Phase 7 (Plan A active): VisiEnhance-Net NAFNet-15M 重训

**Status**：ACTIVE
**Started**：2026-05-24
**Target Deadline**：2026-07-22（M2 Gate）
**Responsible**：Claude + 用户（用户跑 GPU，Claude 调脚本/分析）

> ⚠️ 本计划是 Plan A 的 active 执行版本。原始设计 spec 见 `phase_07_visienhance.md`，本文件聚焦 ICLR 2027 命中率目标 + 实操步骤。

---

## Goal

VisiEnhance Stage 1 v0（base_channels=32, mid_blocks=2, 1.7M 参数）容量不足 → PSNR 仅 25.55 dB（目标 ≥30）。

Plan A：换大 config（**base_channels=64, mid_blocks=8, ~15M 参数**），重跑 Stage 1（30-40h on RTX 4070），再依次 Stage 2 (DP-Loss) + Stage 3 (quality hinge)。

最终目标：
- E1 PSNR ≥ 30 dB, SSIM ≥ 0.92, LPIPS ≤ 0.08
- E3 \|ΔAUC\| < 1.5%, 分类一致率 > 95%
- E5 SalvageRate (moderate q̄∈[0.35,0.5]) > 55%, (severe q̄<0.25) < 25%
- Prop 3 实证：增强后 entropy ↓ paired t-test p<0.01（E4）
- Lemma 3 实证：有 DP-Loss 组 ΔAUC 显著更小（E7）

---

## Success Criteria（M2 Gate 必须 PASS）

- [ ] **Plan A Stage 1 训练完成**：`checkpoints/visienhance/stage1_planA/best_visienhance.pth`
  - PSNR (moderate val set) ≥ 30 dB
  - SSIM ≥ 0.92
  - LPIPS ≤ 0.08
- [ ] **Stage 2 DP-Loss 微调完成**：`stage2/best_visienhance.pth`
  - DP-Loss 收敛到 < 0.05
  - Q-VIB 预测一致率 > 95%
- [ ] **Stage 3 质量 hinge 完成**：`stage3/best_visienhance.pth`
  - E5 SalvageRate 阈值达标
- [ ] **E1-E12 全跑**（详见 ACCEPTANCE_CRITERIA.md E 表）
- [ ] **Proposition 3 + Lemma 3 数学推导完整**写入 main paper §4.4 + Appendix A2
- [ ] **Theorem 2 (agent risk bound) 推导完成**（独立 lever L4）
- [ ] **Table 1 加 row** "Q-VIB + VisiEnhance Stage 3" 数字
- [ ] 单元测试：`pytest tests/test_visienhance.py` 全绿

---

## Decision Gates（预定义，不需用户确认即可执行）

| 条件 | 行动 |
|---|---|
| Stage 1 ep10 PSNR < 27 dB | 停训，检查数据/loss/lr，可能需调 batch size / 改 LPIPS λ |
| Stage 1 ep20 PSNR < 29 dB | 增加 200 → 250 epoch 上限 |
| Stage 1 ep80 PSNR < 29.5 dB | 转 Plan B（接受 27-29 dB），改写 §4 + Limitation |
| Stage 2 DP-Loss 训 20 epoch 不降 | 降 λ_DP 从 0.05 → 0.02 试 |
| Stage 2 Q-VIB 一致率 < 90% | 增 λ_DP 从 0.05 → 0.1 试 |
| Stage 3 SalvageRate < 50% | 调阈值 q̄_target 0.55 → 0.50 |
| 显存超过 7.5GB | batch 16 → 12，启用 gradient checkpointing |
| 训练崩溃 / OOM | 写明原因到 PROJECT_LOG.md，重启训练 |

---

## Tasks（按周细分）

### W1 (2026-05-25 ~ 05-31)

- [ ] **D1-D2**：起 `configs/visienhance_s1_planA.yaml`
  - base_channels=64
  - mid_blocks=8（前 mid_blocks=2）
  - encoder/decoder blocks 各 2 → 2（保持）
  - batch 16（FP16 AMP，~6.5 GB on 4070）
  - lr 1e-4 cosine annealing
  - epochs 200 + 早停 patience=5
  - data: paired_dataset/{light,medium,heavy} 全部
- [ ] **D3-D4**：单元测试更新 `tests/test_visienhance.py` 跑 batch=1 冒烟测试通过
- [ ] **D5**：用户启动训练，Start-Process 开新窗口（CLAUDE.md 长任务规范）
- [ ] **D6-D7**：Monitor heartbeat 30min cadence + state.json 每 1 epoch 更新

### W2 (2026-06-01 ~ 06-07)

- [ ] **D8-D11**：Stage 1 训练继续（预期 30-40h，6 月 1-3 日完成）
- [ ] **D12-D13**：Theorem 2 (agent risk bound) 数学推导（与训练并行）
  - decision-theoretic formulation
  - expected loss bound
  - 写入 `plans/V-QIB数学推导_v2.md` (新文件)
- [ ] **D14**：Stage 1 完成 → eval_visienhance.py --exp E1 跑通

### W3 (2026-06-08 ~ 06-14)

- [ ] **D15-D17**：Stage 2 DP-Loss 微调（~36h）
- [ ] **D18-D19**：Corollary 1 (Q-VIB + QCTS ECE bound) 推导
- [ ] **D20-D21**：CheXpert + Fundus APTOS cross-domain inference（脚本就位）

### W4 (2026-06-15 ~ 06-22)

- [ ] **D22-D24**：Stage 3 quality hinge 微调（~24h）
- [ ] **D25-D26**：Q-VIB + VisiEnhance 联合推理 → Table 1 加 row
- [ ] **D27-D28**：M1 Gate 验收 + PROJECT_LOG 总结

### W5-W8 (2026-06-23 ~ 07-22) — M2 Gate
- E1-E12 全跑 + 6 SOTA 对比 + per-mechanism ablation + Fairness + ISIC 2024 SLICE-3D
- 详见 ACCEPTANCE_CRITERIA.md M2 Gate

---

## Experiment Log

| run_id | config | key_metric | status | note |
|---|---|---|---|---|
| 2026-05-16_visienhance_s1_v0 | visienhance_s1.yaml (1.7M) | PSNR 25.55 / SSIM 0.9535 | ❌ done but inadequate | 容量不足，作为 baseline |
| TBD | visienhance_s1_planA.yaml (~15M) | TBD | pending | M1 W1 启动 |

---

## Blockers

无（M1 W1 启动前）。

---

## Notes

- **不能用扩散模型**（红线 R8 + 永久红线 4）
- DP-Loss 需冻结 Q-VIB encoder（`requires_grad_(False)`）
- Stage 2/3 训练中 VisiScore-Net 也必须冻结
- E3 必须用 test split（`isic_split.csv` 的 `split == 'test'`），严禁 train 数据
- 训练前检查：磁盘 ≥ 30GB 空间（checkpoint × 多 stage）
