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

---

## 2026-07-11 · 实验设计红队 + 方案A定稿（冻结防 HARKing）

> 全量实验设计（PLAN/EXPERIMENT_MATRIX_P1-P3.md）经 skeptic 红队砸出 3🔴 致命，用户拍板方案A修。K 判决**预注册判据在此冻结**，跑前不改（跑后回填有利叙事=HARKing）。

**skeptic 3🔴（同根=对照两侧构造/选择/模型不匹配）**：
- 🔴-1 对照锚 PsiloQA-zh 未过"骗过≥1检测器"筛，zh-med 过了 → G_domain 是选择伪迹非域效应。
- 🔴-2 构造投票器含 Qwen2.5-7B = K1 承重 judge D10 同体 → 循环。
- 🔴-3 Evident/Subtle≠natural/adversarial（RAGTruth 全自然/我们全对抗构造零自然臂）→ K2 对抗 confound 控制无效。
- 承重事实已核：RAGTruth Evident/Subtle=自然幻觉显隐性 arXiv:2502.17125；MedHallu hard/med/easy=骗过检测器过滤 2025.emnlp-main.143。

**方案A修法（用户拍板）**：①对称化主力（对照通用锚也过同 MedHallu 管线+同筛=CMedFaith-zh-gen-adv）②MedFact 真自然臂三角互证 ③协变量回归 robustness。

**🔒 预注册冻结（跑前定死，防 HARKing）**：
1. **K1 承重判据**：`G_domain=MacroF1(zh-gen-adv)−MacroF1(zh-med-adv)≥0.05` 且 bootstrap95%CI下界>0，承重族=NLI(D1 `mnli-xnli`)+**非投票judge(D11 GLM-4/D12 InternLM2.5)**+专用(D5)；**D10(Qwen2.5-7B)是构造投票器成员→不进承重**。PASS=≥2族(含≥1非投票judge)医学显著弱。
2. **K2 判据（重述）**：等构造强度下 `ΔF1(zh-gen-adv − zh-med-adv)≥0.05` 且CI下界>0 **且 ≥1 三角互证同向**（MedFact自然臂也弱/协变量回归β_domain残留）。最强claim=「等构造强度下医学域更难」，**不 claim 无条件"本身难"**。
3. **K3 判据**：中文医学 zh-med 检测器显著弱（对照用 zh-gen-adv 对称锚），en→zh 平行迁移 ΔF1 带 CI。
4. **🔒 对称锚同筛检测器集冻结**：CMedFaith-zh-med 与 CMedFaith-zh-gen-adv **必须用同一组"骗过≥1检测器"的检测器**（消🔴-1 的关键）。该检测器清单 = [构造 pilot 时确定，跑 R-P2.7 前冻结写此处 TODO]，两侧严格一致，跑后不改。
5. **D1 复现锚**：pilot 冻结值 G_domain=0.2927 CI[0.184,0.391] 用 `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli`；R-P1.0 全量复现须对齐此（2mil7 版会变值不可直接引）。

**FAIL 退路（预注册）**：K1 非投票judge不弱→#1收缩「NLI族失效」；K2不难→#2「对抗鲁棒性」；K3不难→#3「英→中迁移诊断」。

**R-P1.0 复现校验（2026-07-11 冒烟）**：smoke(20/40条+boot200)方向一致 got G_domain=0.276 CI[0.014,0.501] vs frozen 0.2927；全量复现在跑核对 frozen 0.4277/0.7204（verifier 核 code/results/）。
