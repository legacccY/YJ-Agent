# CMedFaith — Kill-shot Ledger（立项前证伪，冻结防 HARKing）

> 记录立项前跑的两发 kill-shot：预注册判据（跑前冻结）+ 实测结果（Bash 核 csv）。
> 目的：把"哪些前提被验/被证伪"钉死，防止立项后回填有利叙事（HARKing）。
> 冻结日期：2026-07-11。数字真源 = scratchpad 各 `results.csv`（本文数字已 Bash 核对）。

---

## Kill-shot #1：通用域跨语言（中文 vs 英文）——证伪"检测器跨语言崩"

**承重前提（原候选 A headline）**：现成多语言检测器一到中文就掉分。
**预注册判据**：mDeBERTa-XNLI 在 PsiloQA 中文 vs 英文 macro-F1，`G_lang ≥ 0.05` 且 bootstrap 95%CI 排除 0 → 前提成立。
**脚本**：`_scratch/killshot_psiloqa.py`（PsiloQA test split，标签=labels非空或含[HAL]→unfaithful）。

| 检测器 | 语言 | macro-F1 | n_faith | n_unfaith | G_lang | CI95 |
|---|---|---|---|---|---|---|
| mDeBERTa-XNLI | en | 0.6235 | 39 | 1059 | −0.0042 | [−0.0894, 0.0864] |
| mDeBERTa-XNLI | zh | 0.6277 | 39 | 261 | | |

**裁决：前提证伪。** G_lang≈0，CI 含 0，中文甚至略高。**放弃"检测器跨语言崩"这个动机**（与 EACL 2026 论文 arXiv:2601.16766「检测器跨语言下降远小于任务」独立一致）。
**残留 caveat**：类别不平衡（faithful 仅 39），macro-F1 的 faithful 类不稳；单臂。作用=证伪旧动机 + 未来当"通用域对照基线"数据点。

---

## Kill-shot #2：医学 vs 通用（英文）——验证新方向命门"医学域更难"

**承重前提（新方向）**：现成检测器在医学 faithfulness 上比通用域显著弱 → 支持建专门医学 benchmark。
**预注册判据**：`G_domain = macroF1(通用) − macroF1(医学) ≥ 0.05` 且 bootstrap 95%CI 下界>0 → 命门 PASS。
**脚本**：`_scratch/killshot_med_vs_general.py`。医学=MedHallu pqa_labeled（每 question 派生 忠实/不忠实 各1条，天然平衡）；通用=PsiloQA-en 平衡下采样。NLI 设置跨两数据集恒定。

| 检测器 | 域 | macro-F1 | n_faith | n_unfaith | G_domain | CI95 |
|---|---|---|---|---|---|---|
| mDeBERTa-XNLI | general (PsiloQA-en) | 0.7204 | 39 | 39 | +0.2927 | [0.1844, 0.3912] |
| mDeBERTa-XNLI | medical (MedHallu) | 0.4277 | 1000 | 1000 | | |

**裁决：命门 PASS。** 医学域掉 29 个点，CI 稳稳排除 0（冒烟 40/80 条=0.29，全量=0.29，一致）。medical macro-F1 0.43 < 随机 0.5 = 现成 NLI 检测器在医学对抗幻觉上系统失效。
**残留 caveat（立项后正式实验必须处理）**：
1. **对抗构造 confound**：MedHallu 幻觉是对抗性构造、PsiloQA 是自然生成，G_domain 混着"对抗 vs 自然"难度差，不纯是"医学领域"。→ 正式 benchmark 须分层"自然 vs 对抗"幻觉。
2. **单承重臂**：仅 mDeBERTa，judge 第二臂待补（≥2 臂才定稿）。
3. **英文粗筛**：中文医学数据尚未自建，pilot 是英文 MedHallu 代理。

---

## 立项后待验（结转 02_ACCEPTANCE 的 kill criteria）
- K1：补 LLM-judge 第二承重臂，G_domain 是否仍显著。
- K2：控制对抗构造 confound（自然 vs 对抗分层），医学更难是否残留。
- K3：中文医学自建数据上，现成检测器是否同样失效。
