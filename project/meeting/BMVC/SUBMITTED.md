# 🔒 BMVC 2026 — SUBMITTED & SEALED

**封印日期**：2026-05-24
**投稿日期**：2026-05-29（BMVC P2 deadline）
**论文标题**：Quality-Conditioned Temperature Scaling: Post-hoc Calibration under Image Quality Shift
**最终页数**：主文 10 页（BMVC hard limit 达标）+ Supp 18 页

---

## ⛔ 封印规则

1. **此目录所有 tex / fig / csv / md 文件冻结**，不再修改
2. 任何"补实验"、"加新 ablation"、"调图"诉求 → 走 ICLR 2027 大项目分支，不动 BMVC
3. 仅允许的修改：rebuttal 阶段（收到 review 后）— 单独建 `rebuttal/` 子目录
4. README.md 顶部已加 🔒 SEALED 标记

---

## 📋 提交清单（已交付）

| 交付物 | 路径 | 状态 |
|---|---|---|
| 主文 PDF | `itb_paper.pdf` | ✅ 10 页 + 2 页 ref |
| Supplementary PDF | `itb_supp.pdf` | ✅ 18 页 |
| Overleaf 压缩包 | `itb_paper_overleaf.zip` | ✅ |
| Supp 压缩包 | `itb_supp_material.zip` | ✅ |
| Anonymous GitHub | release/ + GITHUB_SETUP.md | ✅ skeleton 完成（用户手动 push）|

---

## 🎯 三条核心论点（投稿版本）

1. **TS reversal 真实**：MC vs deterministic-μ forward swap 是 Std VIB ρ 翻转的真正机制（A1 3-way forward ablation 实证，Δρ<10⁻⁵ for scalar TS）
2. **QCTS = universal post-hoc fix**：2 参数 softplus，跨 VIB / CNN / Transformer 三家族
3. **q̄ = universal per-input quality scalar**：learned (dermoscopy) 或 a priori (ImageNet-C severity) 都适用

---

## 📊 投稿版本关键数字（已冻结，禁止改动）

### Table 1 锁定（ITB-LQ n=300 / ITB-HQ n=360）

| Method | AUC-LQ | ECE-LQ | AUC-HQ | ECE-HQ | QCDI | ρ |
|---|---|---|---|---|---|---|
| EfficientNet-B3 | 0.751 | 0.345 | 0.938 | 0.068 | +0.277 | −0.123 |
| MC Dropout (30×) | 0.693 | 0.615 | 0.808 | 0.473 | +0.142 | −0.114 |
| Deep Ensemble (5×) | 0.711 | 0.440 | 0.868 | 0.339 | +0.101 | −0.123 |
| EDL | 0.586 | 0.316 | 0.895 | 0.270 | +0.046 | +0.039 |
| Std VIB | 0.553 | 0.146 | 0.587 | 0.129 | +0.016 | −0.153 |
| Std VIB + TS | 0.582 | 0.175 | 0.732 | 0.160 | +0.015 | **+0.241** |
| **Std VIB + QCTS** | 0.563 | **0.079** | 0.580 | 0.075 | **+0.004** | **−0.249** |

### Universality（Table 3，5 backbone）
- Std VIB / ResNet-50 / ViT-Tiny / ConvNeXt-Tiny / Swin-Tiny — 详见 STORY_FRAMEWORK.md 已锁定数字表

### Zero-shot
- HAM10000 (n=10015): Std VIB ρ=−0.033 → +QCTS ρ=−0.108 (p<10⁻²⁶)
- PAD-UFES (n=2298): Std VIB ρ=−0.075 → +QCTS ρ=−0.150 (p<10⁻¹²)

---

## 🛡️ 3 reviewer 应答状态（封印前）

5 致命 / 8 高 / 5 中 — 18 issues 全部应答完成，详见 `WORKLOG.md` 2026-05-21 第六次会话 entry。

| 攻击 | 应答位置 |
|---|---|
| TS reversal MC vs det 混淆 | A1 实测 3-way ablation（supp §A19）+ Intro/§5.2/§6 reframe |
| Std VIB AUC 0.553 头条 | hedge「intentionally bottlenecked」+ EffNet-B3 数字 Table 1 |
| ResNet-50 QCDI 不改善 | §5.4 自承 + reframe「gains on weakly Q-aware backbones」|
| B1-B3 不 pin softplus | §4.2 改「design choice + ablation, not derived」|
| ρ<-0.15 阈值数据后拟合 | supp §A14 permutation null 推导 ρ_noise=0.043 |
| NLL「flat landscape」夸大 | reframe「shallow basin, 2/3 seed 在边界」|
| Triage simulation 反向打脸 | supp §A3 重写「probe vs deployable caveat」|
| Fitz V-VI stat empty | 「directionally consistent」+ 删 VI 单类 QCDI |
| DCA 0.192 vs 0.186 没 CI | bootstrap CI 2000 次，CI 全 overlap，主文 honest reading |
| zero-shot HAM10000 overclaim | 改 cross-dataset + 注明 PAD smartphone |

---

## 🔗 BMVC 与 ICLR 2027 大项目的关系

| 维度 | BMVC（已提交） | ICLR 2027（启动中）|
|---|---|---|
| 范围 | **Post-hoc calibration** 单一模块（QCTS） | **End-to-end 5 模块系统**（VisiScore + Q-VIB + VisiEnhance + Agent + ITB）|
| Hook | Standard TS 在 quality shift 下系统性误导 | Closed-loop agent with active quality intervention |
| Theory | softplus QCTS 从 B1-B3 inductive biases 推导 | Q-VIB Prop 1/2/Thm 1 + VisiEnhance Prop 3 + DP-Loss Lemma 3 + Agent Thm 2 |
| 关键差异 | frozen model + post-hoc T(q̄) | trainable enhancer + DP-loss + dual-channel decision |
| 复用 | QCTS 在 ICLR 论文里作为 baseline / one ablation | — |

---

## ⚠️ 未来如何动 BMVC（合法路径）

- ✅ rebuttal：建 `rebuttal/` 子目录，写 response.tex + 补 ablation csv（仅限 review 要求范围）
- ✅ camera-ready：建 `camera_ready/` 子目录，按官方要求改
- ❌ 把 BMVC 数字写入 ICLR 论文：要 cite 自己 BMVC paper（如果已 accepted），不复用 fig / tex
- ❌ 加新 baseline / dataset / claim：全部走 ICLR 大项目分支
