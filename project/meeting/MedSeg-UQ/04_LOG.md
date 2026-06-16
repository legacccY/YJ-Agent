# MedSeg-UQ 项目 LOG

> 索引见 `00_选题调研_2026-06-16.md`。理论框架见 `02_理论框架.md`。

---

## 2026-06-16 — 立项前调研 + ★1 理论骨架启动

**做了什么**
1. **8 路 researcher 并行调研**（应用 4 + 理论 4），产出选题矩阵（T1-T6）+ 文献矩阵（5 族带引用）+ 理论深挖矩阵（★1-★6 排行）+ 导师王水花画像 → 全在 `00_选题调研`。
2. **定向**：用户拍方向 = ★1（Calibration–Dice trade-off 下界）为主、★2（最优聚合算子）保留；会场 = 纯顶会（CVPR/ICLR/NeurIPS）。
3. **★1 防撞车检查**（researcher 穷举 2020-26）：判定**真空白**。最接近=mL1-ACE 实证称 "inherent tension" 无定理；RankSEG 定义 Dice-calibration 但未证 calibration 下界；信息论不可能定理仅分类非分割。
4. **★1 理论框架 `02_理论框架`**：形式化设定（逐像素 p(x)、歧义质量 m_δ、smCE、Dice）+ 三步证明骨架（Lemma1 Dice偏好硬决策 / Lemma2 sharp⟹miscalibrated / 主定理 Dice≥α⟹smCE≥Φ(α;m_δ)）。
5. **P0 玩具命题亲推走通**：p=1/2 歧义区 + sharpening s，证 **smCE(f) ≥ m·s**（构造 1-Lipschitz g*=−1@v₀），两端退化（s=0 / m=0 → 0）都过。验证 g* 构造法 work。
6. **Opus 核原文**（主源验证，红线，**两篇全核到**）：
   - RankSEG [2206.13086]：Thm1 Dice-Bayes=ranking top-τ* 规则、Remark2 固定阈值次优、Def8/Lemma9 CE/focal 非 Dice-calibrated → 精化 Lemma1。
   - Błasiok [2211.16886]（ar5iv 主源）：§7 smCE=sup_{w∈1-Lipschitz[0,1]→[−1,1]} E[w(v)(y−v)]，与 P0 逐字一致；一致性 **½·d̲CE ≤ smCE ≤ 2·d̲CE**（Def5.1）→ **P0 下界传到真·ℓ1 校准距离 d̲CE ≥ ½·m·s，结论变强，不依赖度量选择**。
   - （firecrawl 额度爆，改用 WebFetch ar5iv + themoonlight 二手交叉，均确认。）

**结论**：★1 真空白可推进；证明主线（aleatoric 歧义驱动 trade-off）自洽且 P0 内核已证；解释 mL1-ACE 实证方向（歧义大的 BraTS 损 Dice 最多、KiTS 几乎不损）。

**7. P1 + P2 主定理亲推（核心推理，已完成骨架）** — 见 `02_理论框架` §3.6/§3.7：
   - **P1（已证）**：large-image 极限 population soft-Dice 下，校准预测器的 soft-Dice 上确界 = **𝔇_cal\*=E[p²]/E[p]**（Cauchy–Schwarz，等号 f=p）；与上限 1 的头空间 = **E[p(1−p)]/E[p] = 归一化 aleatoric 不确定性**。
   - **P2（骨架已推）**：两条无条件 smCE 下界（w=v / w=1）+ soft-Dice Lipschitz（引理2.1，4Δ/c）+ d̲CE≤2smCE 找附近校准 g（引理2.2）⟹ **smCE(f) ≥ (E[p]/8)(𝔇(f)−E[p²]/E[p])**，即 **Φ(α)=(1/8)(α·E[p]−E[p²])**，d̲CE 同阶。
   - 性质：Φ>0 ⟺ α>𝔇_cal\*；确定数据 Φ=0（无 trade-off）；常数 8 宽松可改。
   - **意义**：首个把「Dice 超出校准最优量」下界到校准误差的形式化定理，头空间 = aleatoric，机制清晰。对上 mL1-ACE 实证（BraTS 损最多/KiTS 不损）。

**结论更新**：理论侧 Gate0 可证部分（P0/P1/P2 骨架）**已过**。

**下一步（待办）**
- [ ] P2 polish (a)：引理 2.2 d̲CE coupling→functional 测度论严格化。
- [ ] P2 polish (b)：去 A1（large-image 极限），回到有限-N 真 Dice 的 U-statistic 分母耦合 + soft↔hard Dice = 论文 full version 核心增量。
- [ ] P3 实证：ACDC/BraTS 画 Dice–smCE 经验 Pareto 前沿，验证落 Φ 之上 + 歧义大前沿更陡（查 `.portfolio/datasets.json`）。
- [ ] **拍板点**：Gate0 全过（+P3）→ `/spin-off-paper` 正式立项 + 向导师对齐会场/合作者。

**拍板状态**：方向已拍（★1+★2 留）；正式立项（registry schema）待 Gate0。已认领 `.portfolio/locks/medseg-uq.claim`。
