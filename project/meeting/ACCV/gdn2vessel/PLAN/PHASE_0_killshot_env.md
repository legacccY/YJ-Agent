# PHASE 0 — 环境 & kill-shot

## ① 目标（锁定）
验证 GDN-2 在 HPC 4090 能真跑、记忆模块塞进小 U-Net 不发散且不输纯 CNN。这是整条 plan 的存活闸——通不过则方向不成立。

## ② 入口依赖
- 关 0 PASS（driver 565.77，cu126 退路确认可行）
- 关 1 PASS（venv `gdn2venv`：torch 2.9.0+cu126 + triton 3.5.0 + FLA，`import torch,fla` 通）

## ③ 任务清单
1. **关 2 — GPU kernel 烟测（<5min）**：srun gpu4090（gpu_slot 申请），跑单层 GDN-2 fwd/bwd，确认 sm_89 编通。骨架见批准 plan（`chunk_gated_delta_rule`，退路 `naive_chunk_gated_delta_rule`）。
2. **关 3 — pilot**：GDN-2 记忆模块塞小 U-Net + 初版断点续连测试，DRIVE 上验 ①不发散 ②Dice ≥ 纯 CNN。

## ④ ACCEPTANCE 硬阈值（不妥协）
- [ ] 关 2：kernel fwd/bwd 跑通，grad norm 有限非 NaN（或 naive 退路先验正确）
- [ ] 关 3：DRIVE pilot loss 不死平>3 / Dice 非 0（不发散）+ Dice ≥ 纯 CNN baseline
- [ ] **不妥协闸**：kernel 连 naive 退路都不通 OR pilot 主集发散/输纯 CNN → **砍**（拍板点，写诚实回退给用户）

## ⑤ 自由发挥区
chunk vs naive 实现选择、bf16/fp32、编译细节、pilot 小 U-Net 深度、记忆模块插入位置初探。

## ⑥ 跑偏定义 / 红线
- ❌ kernel 编不通就私自改官方实现凑通（复现零偏离）——退 naive 退路，仍不通则停下报
- ❌ pilot 为了不发散私自降 lr/改步数（复现零偏离）
- ❌ 本地 8GB 跑正式 pilot（仅烟测；正式上 HPC）

## ⑦ 退路 + 派谁 + 出口 gate
- 退路：kernel 编不通 → naive_chunk_gated_delta_rule 纯 PyTorch 先验正确性。
- 派谁：主线串行（训练启停红线）；kill-shot 脚本放 `killshots/`（<50 行）。烟测前 `gpu_slot.py request gdn2vessel hpc 1`。
- **出口 gate**：关 2 + 关 3 双 PASS → 进 P1/P2。NaN signature（loss 死平>3 + Dice 0）= 立即重提（见记忆 nca_divergence_signature 同理）。
