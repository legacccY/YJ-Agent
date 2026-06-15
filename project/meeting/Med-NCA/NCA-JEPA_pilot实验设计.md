# NCA-JEPA 2 周 Pilot 实验设计 + 决策门

> 目的：在投入数月主攻前，用 2 周低成本验证 NCA-JEPA 的**两根生死实证轴**，并预定义 go/pivot 决策门。
> 配套：`NCA-JEPA_创新计划.md` §8（gated 双轨）
> 最后更新：2026-06-14

---

## 0. Pilot 只回答两个问题（不多做）

1. **Pillar 1 — 稳定性**：③ 收缩约束的 latent-NCA predictor 塞进 I-JEPA，**训得稳、不塌缩、rollout 收敛**？
2. **Pillar 2 — 等变优势**：④ 等变 NCA predictor 在**小数据/旋转 OOD** 上，相对 ViT predictor 真有优势信号？

> ⚠️ Pilot 不追 SOTA、不上 3D、不调超参炫技。只要**信号**（趋势 + 效应量 + 多 seed 一致），不要终版数字。
> ⚠️ VisiSkin 教训：**复用 I-JEPA 官方代码库**，只换 predictor 模块——把 silent-bug 面降到最小，绝不从零搭 JEPA。

---

## 1. 固定设置（全臂一致，省得混淆变量）

| 项 | 取值 | 理由 |
|---|---|---|
| backbone | ViT-S/16 | pilot 求快；主攻再上 ViT-B |
| 分辨率 | 224² | 对齐 CheXWorld |
| 预训练数据 | NIH ChestX-ray14 + CheXpert 子集，~50k frontal | 公开、够看趋势；不用全 0.5M |
| 预训练 epoch | 100（pilot 短跑） | 看轨迹趋势足够 |
| target encoder | EMA(context)，momentum 0.996→1.0 | I-JEPA 标配 |
| 条件 z | 先只做 mask M（局部任务）；位移 Δ 留主攻 | 缩面，先验证机制 |
| 下游探针 | VinDr-CXR + RSNA，linear probe + 1%/10% data | 轻、快出信号 |
| seed | gate 判定臂跑 3 seed | 多 seed 一致才算数（复现报告教训） |
| 确定性 | 记录 cudnn flags + seed；不强求 bit 复现 | atomic 非确定性教训，至少留痕 |

---

## 2. 对照臂（4 臂，控变量）

| 臂 | predictor | 验什么 |
|---|---|---|
| **A0** | ViT predictor（I-JEPA 原版） | **基线/管线 sanity**。A0 学不动=管线坏，与 NCA 无关 |
| **A1** | vanilla NCA predictor（无约束） | NCA 直接搬进来会不会发散/塌缩（预期：会，作 ③ 的反例） |
| **A2** | 收缩 NCA predictor（spectral-norm / Lipschitz<1） | **Pillar 1 主臂**：约束是否治好 A1 的病 |
| **A3** | 收缩 + 各向同性/等变更新 | **Pillar 2 主臂**：等变优势是否出现 |

- 全 NCA 臂 predictor 参数预算 ≤ A0（卖点之一是省参，不能偷偷加参）。
- A1 可选（时间紧可砍），但留着能讲「问题→修复」的干净故事。

---

## 3. 量化指标

**Pillar 1（稳定性 / 塌缩）**
- 训练 loss 轨迹：无 NaN、无 flat-high（>3 死平，复现报告的发散 signature）
- **塌缩 canary**：token 嵌入 std / 嵌入矩阵有效秩（rank）/ KoLeo——低于阈值=塌缩，**别把低 loss 当成功**（JEPA 头号假阳性）
- rollout 收敛：‖S_{t+1}−S_t‖ 随 t 单调↓ → 是否到不动点；记实测 per-step Lipschitz
- A1 vs A2 对比：约束是否把发散/塌缩压住

**Pillar 2（等变 / 样本效率）**
- 下游 linear probe AUROC @ 1% / 10% / 100% data（VinDr-CXR、RSNA）
- **旋转 OOD**：测试图旋转 {15°,30°,90°}，下游 AUROC 掉多少；A3 应比 A0 掉得少
- 预测一致性：旋转输入后 predictor 输出的等变误差（A3 应显著低于 A0）

---

## 4. Silent-bug 哨兵（VisiSkin visiscore 教训，强制）

跑大实验前，每条必须先过；任一红灯=管线 bug，**先修再跑**，别让 bug 假扮结果。

1. **归一化 assert**：log 喂入张量的 mean/std == 期望 NORM 统计；raw 值溜进来直接 raise（visiscore 喂 raw 的同类坑）
2. **EMA sanity**：target ≠ context（momentum 在动）；target encoder 不吃梯度
3. **塌缩 canary**：嵌入 std < 阈值 → flag（不是「loss 真好」）
4. **overfit-one-batch**：全跑前，模型须把单 batch loss 压到≈0；压不下=代码 bug，立即 abort
5. **z-shuffle 对照**：打乱 mask/条件 z → 下游应**掉**。不掉=z 没接进去（管线没真用条件，CheXWorld 自己的 ablation 逻辑）
6. **determinism 留痕**：记 cudnn.deterministic / benchmark / seed，便于复盘

---

## 5. 决策门（预定义 if-then，失败不临时改主意）

### Gate 0 — 管线 sanity（~Day 3）
**条件**：A0 linear probe 显著 > from-scratch（ΔAUROC ≥ +5）**且** overfit-one-batch 过 **且** z-shuffle 对照下游掉（≥3 AUROC）。
- ✅ 过 → 进 Gate 1
- ❌ 不过 → **管线 bug，不是 NCA 问题**。修管线，不推进。

### Gate 1 — Pillar 1 稳定性（~Day 7）
**条件**（A2，3 seed）：3/3 跑完无发散无 NaN **且** 塌缩 canary 全程健康（std/rank 在阈上）**且** rollout 残差收敛。
- ✅ 过 → 进 Gate 2（理想加分：A1 展示出 A2 修好的病，故事更干净）
- ❌ 不过（收缩仍救不住 latent NCA-JEPA）→ 🔴 **RED：转保底轨**（复现/稳定性论文），不再砸钱。

### Gate 2 — Pillar 2 等变优势（~Day 12）
**条件**（A3 vs A0，3 seed）：A3 在 {1%-data linear probe, 旋转 OOD} **至少一项**显著 ≥ A0（效应量 + 3 seed 方向一致，CI 排 0）。
- ✅ 过 → 🟢 **GREEN：升级 NCA-JEPA 主攻**（X 光先行打平/超 CheXWorld + 锁等变杀手锏；3D 后加）
- ❌ 不过但 Gate 1 过 → 🟡 **AMBER**：NCA-JEPA 训得稳但无 ViT-beating 性质。time-box 1 周再试杀手锏 ⑤（自适应计算）；仍无 → 降级「高效 SSL NCA」弱会 或 转保底。**不无限延**。

> 三态总结：Gate1+Gate2 双过=GREEN 主攻；Gate1 过 Gate2 否=AMBER 限时再赌一个性质；Gate1 否=RED 退保底。

---

## 6. 两周排期

| 天 | 活 |
|---|---|
| D1–2 | 拉 I-JEPA 官方库，跑通 A0 baseline；建 6 个哨兵；预训练数据子集就绪 |
| D3 | **Gate 0 判定**（A0 sanity + overfit-batch + z-shuffle） |
| D4–5 | 实现 NCA predictor 模块（A1 vanilla）+ 收缩约束（A2）；接 FiLM 条件注入 |
| D6–7 | 跑 A1/A2 各 3 seed；测稳定/塌缩/收敛 → **Gate 1 判定** |
| D8–9 | 实现各向同性/等变更新（A3）；跑 A3 3 seed |
| D10–11 | 下游探针：1%/10% linear probe + 旋转 OOD（A0 vs A3） |
| D12 | **Gate 2 判定** → GREEN/AMBER/RED |
| D13–14 | 写 pilot 结论（1–2 页：图 + 三态判定 + 下一步），存档 |

---

## 7. 算力预算

- 主力单卡即可（ViT-S/50k/100ep ≈ 数小时/臂）；4 臂 × 3 seed ≈ 十几个短 job → 你 ≥4 卡数天的预算**绰绰有余**
- 多 seed 并行铺在多卡，2 周内稳完

---

## 8. 交付物

- `results/pilot_*` 每臂逐 epoch 轨迹 + 塌缩指标 + 下游探针 CSV（单一真源）
- 稳定性三联图（loss / 塌缩 canary / rollout 残差）
- 等变对比图（1%-data probe + 旋转 OOD，A0 vs A3）
- 1–2 页 pilot 结论 + GREEN/AMBER/RED 判定 + 决策门留痕

---

## 9. 反跑偏红线（贴墙）

- 只验 2 个 pillar，不顺手加任务/加模态/调参炫技
- 哨兵不过不跑大实验
- 决策门数字达不到就按预案走，**不临时找理由续命**（VisiSkin 跑偏教训）
- pilot 产物即使 RED 也有用（喂保底轨），不算白做
