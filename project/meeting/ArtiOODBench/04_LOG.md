# ArtiOODBench — LOG

> **核心章节散文草稿指针**：`05_DRAFT_core.md`（writer 出，§Method/§Results/§Discussion-Limitations，paper-ready，venue 无关 md 待落 D&B LaTeX；数字全 verifier 核，2026-06-19）。⚠️ **Entry 10 后此草稿的 A-5「ViM=1.0 完美 source leakage」段落已失效待重写**（in-sample 伪迹，见 Entry 10）。

## Entry 11 — 2026-06-19 ~17:40 held-out 全矩阵重跑（用户拍板「held-out 重算 + 银边升主线」）→ A-5 strict FAIL，承重据实迁移

**用户拍板**：option ① held-out 重算 + 把 in-sample 灌水升为新 benchmark-critique 主贡献。

**coder 改 l3 加 `--protocol {insample,heldout}` 旗**（ID 切 fit/eval seed42 0.5，方法 fit 在 id_fit、eval 在 concat(id_eval,ood)，cleanC 在 id_eval×ood 配对；in-sample 路径保留作对比；输出 `_heldout` 后缀不毁 in-sample csv）。主线跑全 13 法×7 对，verifier+analyst 收口。

**held-out A-5 真值（verifier MWU 从原始分数独立重算，零 drift；与 C3 负对照高度一致）**：

| 对 | held-out ViM | in-sample(伪) | artifact-only |
|---|---|---|---|
| BraTS_vs_BrainTumor | 0.997 | 1.0 | 0.9997 |
| HAM_vs_fitzpatrick | 0.938 | 1.0 | — |
| NIH_vs_VinDr | 0.841 | 1.0 | 0.896 |
| ISIC_vs_PAD_UFES | 0.798 | 1.0 | — |
| VinDr_vs_RSNA | 0.772 | 1.0 | — |
| HAM_vs_ISIC2020 | 0.689 | 1.0 | 0.816 |
| **NIH_vs_RSNA(诚实负例)** | **0.406** | 1.0 | 0.640 |

- **A-5 v5 strict 门 FAIL**：held-out ViM 仅 **2/7 >0.95**（BraTS+HAM/fitz），需 ≥6/7 → FAIL。触预登记 **FAIL 三档退路 #1**：承重退 **A-1/A-2(已 PASS)+A-6 处方 + 新增 in-sample 灌水 finding**。
- **灌水局部性铁证（verifier 核）**：Δ(insample−heldout) **只** ViM=+0.223 / Residual=+0.223，其余 11 法 |Δ|<0.012。根因 = ViM/Residual 的 null-space 残差打分，N_id<D 致 in-sample ID 残差≈0、完美分离任何 held-out，**与 source 无关**。非 bug，是投影降维方案内在数学特性，可机理解释可复现。
- **source 距离单因子驱动**（Spearman ρ=1.0 / Pearson r=0.9995, p=0.0005, n=4 有 artifact 参考对）：artifact 可分性越强 held-out ViM 越高；NIH/RSNA 两美国源 artifact=0.64→ViM=0.41≈chance = **同模态内诚实负例**（证非 CXR 模态 ViM 天然好，是 source 距离驱动）。
- **13 法 held-out 谱异质**：ViM/Residual 0.777 > KNN0.709/MDS0.688/SHE0.686 > logit 类 0.61-0.64 > DICE0.551/fDBD0.510/GradNorm0.397。BraTS 上 8/13 法>0.75、NIH/RSNA 上 8/13 法<0.55 → source leakage 非普遍、强弱看 source 距离。
- **A-4 held-out 仍全 FAIL**（5 可评估 1 极宽 CI + 2 INSUFFICIENT n<30；held-out 配对更少低功效更重，结构性低功效预判成立当 contribution）。
- **ViM cleanC held-out 0.628**（raw 0.777，Δ−0.149）仍 > chance → 深层 source leakage 超 43 维手工特征匹配范围（PR-G4 disclose limitation 不藏）。

**修正后承重故事（诚实，三贡献）**：①现象 = artifact-only 白盒定位（A-1/A-2 PASS，3 模态 artifact 0.64-0.9997）②机制 = 投影类 OOD 检测器 in-sample 评估虚高（ViM/Residual 1.0→0.78，null-space 根因，可推广任意 projection-based 法）③处方 = held-out 协议 + cross-source normal-vs-normal sanity baseline + artifact-only 污染上界。A-4 排名翻转 negative + 低功效剖析当 discussion contribution。

**资产**：results/l3_*_heldout.csv 全落 + sanity_samesource_vim.csv（C0-C3）+ analyst 3 图（fig_heldout_insample_delta / fig_heldout_vim_vs_artifact / fig_heldout_heatmap_13x7）。verifier 零 drift。

**待办**：①writer 重写 STORY/ACCEPTANCE 承重口径(留全痕)+05_DRAFT_core.md 失效段 → 新诚实 headline ②skeptic 红队新框架 ③（增益，低优先）补 a1_artifact_auroc 到 7 对全覆盖把 source 距离相关 n=4→7 ④sanity csv note 列含 ASCII 逗号致 resid_auroc 解析偏移，cosmetic 待修。

---

## Entry 10 — 2026-06-19 ~17:10 ⚠️ 重大发现：A-5 承重 ViM=1.0 是 in-sample 几何伪迹，非纯 source leakage（到拍板点）

**触发**：reviewer 对抗审 05_DRAFT_core.md 列头号 reject 风险 = 「ViM=1.0 可能是 trivial 评估伪迹而非真 source covariate」。主线写负对照 `scripts/sanity_samesource_vim.py` 验，**坐实是评估协议混杂**。

**根因（已读 l3_ood_rerank.py L1037-1062 确认非误读）**：`_run_full_pipeline` 用 `feats_test = np.concatenate([feats_id, feats_ood])`，方法以 `fn(feats_id, feats_test)` 调用 → **ID 部分既是 ViM/Residual/MDS/KNN 的 fit 集，又是 test 的 ID 半（in-sample）**，无 held-out 切分。500 样本 < 1024 维 → PCA 子空间不满秩 → in-sample ID 残差≈0、任何 held-out 残差>0 → 残差类方法把「in-sample vs held-out」当信号，**与 source 无关地完美分离**。

**负对照证据（4 对照 × 3 模态，已存 feats，复用 l3 官方 method_vim/method_residual）**：

| 模态 | C0 cross-source in-sample(=l3报A-5) | C1 same-source in-sample | C2 same-source held-out 对称 | **C3 cross-source HELD-OUT(正确协议)** |
|---|---|---|---|---|
| CXR (NIH/VinDr) | 1.0 | **1.0** | 0.470 | **0.841** |
| BrainMRI (BraTS/BrainTumor) | 1.0 | **1.0** | 0.515 | **0.998** |
| Dermoscopy (HAM/ISIC) | 1.0 | **1.0** | 0.590 | **0.673** |

- **C1 铁证**：同一来源（NIH 对半切）+ in-sample 评估也给 ViM=1.0 → 1.0 来自 in-sample 不对称，**不是 source**。
- **C2 公平负对照**：两端都 held-out 同源 → ≈0.5（无信号，正常）。
- **C3 正确协议**（fit=A 前半 / id-test=A 后半 held-out / ood=B 跨源）：**source leakage 真实存在但非完美**——CXR 0.841 / MRI 0.998 / Derm 0.673，全 >> C2≈0.5。Residual 同步（与 ViM 同几何）。

**判定（诚实，不硬撑）**：
1. **headline「OOD 方法测 source 非病理」存活**：C3 held-out 全 >> 0.5 chance，source 信号真实可检、跨 3 模态。
2. **但承重数字必须从「ViM=1.0 完美」改为「held-out 0.67–0.998」**：Entry 9 的 A-5 PASS 满分（in-sample 1.0）失效。strict A-5 阈值（>0.95 on ≥6/7）在 held-out 下**只 MRI 过、CXR/Derm 不过 → A-5 strict FAIL**。
3. **波及全 l3 矩阵**：13 法 × 7 对 raw+cleanC **全部用 in-sample concat** → 残差/距离类方法（ViM/Residual/MDS/KNN）的 AUROC 都被 in-sample 灌水，需 held-out 重算才有效。logit 类（MSP/Energy…不依赖 ID 几何拟合）受影响小。
4. **银边 = in-sample 灌水本身是新 benchmark-critique contribution**：「OOD 检测器在这些 benchmark 上 in-sample 评估会报虚高近完美 AUROC；held-out 后 source 信号真实但小得多」——比原 claim 更契合 D&B（评测协议陷阱 + 处方）。

**到拍板点（#4 偏离 STORY 承重数字 / #5 stage-gate strict-A-5 FAIL 放行方向）**：需用户拍板重算+reframe 方向，不擅自改 STORY 承重口径。资产：`results/sanity_samesource_vim.csv` + `scripts/sanity_samesource_vim.py`。

**下一步（待拍板）**：推荐 = 改 l3 为 held-out 协议（ID train/test 切分）重算全 13 法×7 对 → A-5 承重换 held-out 真值 → reframe headline 到诚实量级 + in-sample 灌水当新 finding。

---

## Entry 9 — 2026-06-19 ~16:40 v5 扩证据实跑完成（7→13 法 × 4→7 对）→ A-5 承重 PASS 满分（⚠️ 见 Entry 10：此 1.0 系 in-sample 伪迹，承重数字失效）

**触发**：D&B 主投「为 70 中稿」扩证据（STORY/ACCEPTANCE v5 预登记块，2026-06-19 跑前冻结）。代码 e6f36ec 已写，本轮纯执行。

**执行链**：
1. 抽 2 套新 derm feats（GPU frozen 推理）：Fitzpatrick_NV (485,1024)、PAD_UFES_NEV (244,1024) + 各 18 logits。manifest 6229 行含 13 套。
2. **逮 bug**：l3 查找名 `fitzpatrick17k`/`PAD_UFES` ≠ feats 实存名 `Fitzpatrick_NV`/`PAD_UFES_NEV` → P4b/P4c 优雅跳过。改 l3 第 1350/1360 行查找名重跑全量（确定性，5 旧对重算同值 + 补 2 新 derm 对）。
3. 跑 l3 全矩阵：13 法 × 7 对 × (raw + cleanC propensity 配对) + bootstrap。

**A-5 source-leakage 承重命门 = PASS 满分（verifier 从原始分数独立重算确证，零 drift）**：
- **ViM raw AUROC = 1.0 全 7/7 对**（门 ≥(N-1)/N=6/7 >0.95）→ 超额达标，跨 CXR×3 / BrainMRI×1 / Dermoscopy×3 三模态。
- ViM cleanC = 1.0 全 6/6 可评估对（BraTS cleanC n_matched=6<30 按 PR-匹配半径第 6 条剔）→ **去污染后仍 1.0 = 深层 source leakage 顽固，L2 propensity 对 ViM 形同虚设**（PR-G4 disclosure 债，必当 finding+limitation 主动写）。
- Residual raw=1.0 全 7/7 佐证（feature-geometric 残差 = 纯源检测，但非命门承载法，仅描述性对照）。
- 新对 P2b(VinDr×RSNA)/P4b(HAM×fitzpatrick)/P4c(ISIC×PAD_UFES) ViM 全 1.0 → 普适性扩稳。

**13 法 AUROC 谱（描述性，v5 不预登记组级命门）**：三层异质——ViM/Residual 恒 1.0 → KNN(0.719)/MDS(0.694)/SHE(0.682) 中层（跨模态方差大，CXR 低 derm/MRI 高）→ DICE/fDBD/GradNorm 弱（GradNorm mean=0.387 全对最低，唯一依赖梯度的法，frozen encoder 下捕不到 source covariate，据实陈异质不挂组帽）。

**A-4 排名翻转 negative result（已降级，未翻案）**：6 可评估对全 FAIL + BraTS INSUFFICIENT，无一 PASS。spearman_point CXR 高(0.945/0.978/0.775) vs derm 低(0.582/0.720/0.676)，**13 法 CI 上界仍全 >0.7（0.966-1.0）→ 扩方法数 7→13 没救回功效，印证「结构性低功效」预登记剖析当 contribution**（discussion：「即使 7→13 法，所有 CI 上界仍>0.7，判据恒 FAIL 与真值无关」）。

**skeptic 跑后 HARKing 轻量过闸 = 0 致命放行**：A-5 升级口径跑前冻结且留 FAIL 空间（非松到必过）；13 法 7 对全报无挑无藏（弱法 GradNorm/fDBD 如实低分在列）；承重隔离守住（只 ViM 担、独立于配对质量）；A-4 negative 诚实留痕未翻案。**口径校正**：P4c(ISIC×PAD_UFES) cleanC n_matched=**188**（充足），n=6 的是 **BraTS**；P4b(HAM×fitzpatrick) n=39 SMD_max=0.675 平衡差，**仅拖累 A-4/cleanC 不拖累 A-5**（A-5 看 raw 不依赖配对）。

**资产**：results/ 全落盘（l3_raw_ranking / l3_cleanC_ranking / a4_bootstrap_spearman 全 7 对 13 法）+ scripts/plot_v5_figures.py + 3 张扩展图（figures/fig_v5_heatmap_13x7 / fig_v5_vim_leakage / fig_v5_a4_negative，pdf+png，主线核 GradNorm0.387/ViM7×1.0/KNN0.719 三值一致）。

**写 draft 前置（skeptic+analyst 收口，写入待办）**：①A-5 段明写承重基于 raw ViM、独立配对质量（化解 P4b SMD 攻击面）②PR-G4 ViM cleanC 仍 1.0 当 limitation 主动 disclose ③排除 5 法(GEN/KLM/Relation/RankFeat/SCALE) backbone 不兼容理由写 methods ④ViM=1.0 措辞「pre-specified consistent observation」非「we found」⑤SMD 全对 max>0.1（mean<0.1）需 disclose ⑥n 口径别写串(P4c=188/BraTS=6/P4b=39)。

**下一步**：draft 章节（verifier 已核数 → writer 按 STORY v4 + 6 前置写 §Results/§Method/§Discussion）；A-6 评测处方可补 checklist 图。**未到拍板点**（无投稿/训练/删除），自主推进。

---

## Entry 8 — 2026-06-19 ~15:30 命门 reframe 锁定（用户拍板 option ① + 编队收口）

**用户拍板 = ①诚实 reframe headline**（非降 ICBINB、非改裁决救 L3）。

**reframe 闭环（researcher 撞车 → skeptic 红队 → writer 落档）**：
- **researcher 撞车复查 = 0.35 SURVIVE**：关键近祖 **ImageNet-OOD（ICLR2024, arXiv:2310.01755）**已证「OOD detector 对 covariate>semantic 敏感 + ViM latch spurious 特征」——但**自然图像/黑盒/无 cross-institution normal-vs-normal/无手工 artifact 量化/无 L2 去污染 L3 闭环**（单项 0.45）。OpenMIBOOD（CVPR25, arXiv:2503.16247）附带发现未闭环（0.30）。ViM 医学 cross-institution AUROC=1.0 实证 + 43 维手工量化 + L1+L2+L3 闭环全未发表（0.05-0.10）。
- **skeptic 红队新 headline = 0 致命放行**，5 条加固（CVPR vs D&B 分水岭）：①Related Work 正面摆 ImageNet-OOD/OpenMIBOOD + 写「black-box 性能归因→white-box artifact 定位」递进 + 3 差异化 contribution bullet（白盒定位/cross-institution normal-vs-normal 物理切分/propensity 去污染配对）②actionable so-what 从「排名翻转」换「评测协议处方」（cross-source normal-vs-normal 当 sanity baseline + artifact-only AUROC 当污染上界）补 L3 退场空缺 ③**ViM cleanC 后仍 1.0**（skeptic 核全 4 对）→ L2 没削掉 ViM 深层源泄漏 → disclose 成 finding+limitation 别让审稿人发现 L2 形同虚设 ④HARKing 免疫：明写 L3 预登记→FAIL→据实降级时间线，ViM=1.0 写「pre-specified matrix consistent observation」非「we found」，FAIL 的 L3 不删当 contribution ⑤投稿前 verifier 统一 a4_rank_flip.csv（标 PASS）vs a4_bootstrap（标 FAIL）verdict 口径（both 指向 FAIL，但 csv 列矛盾=信誉伤害）。
- **writer 落档 STORY v4 + ACCEPTANCE v4**：留全预登记痕（v2/v3/A-1~A-4 原文/PR-F1-F3/K1-K4 不删不改阈值），A-4 降 negative+完整时间线修订记录，新增承重 A-5（source-leakage ViM=1.0）/A-6（评测协议处方=L3'），K2 修订记录（literal 仅 1/3 对满足=非干净触发，reframe 因 L1+source-leakage 独立成立）。会场 = CVPR analysis/benchmark-critique 主投/NeurIPS D&B/MICCAI/ICBINB 底线。

**venue 现实（skeptic 诚实判，不护盘）**：CVPR/NeurIPS D&B **边界带**——5 加固全做 + ImageNet-OOD 差异化辩护成立 → CVPR 有戏（不保底）；任一没做实 → 落 D&B/MICCAI；ICBINB 底线退路。去掉 L3 排名翻转命门后从「有 actionable 结论的 critique」降为「系统性诊断 + 评测规范处方」，靠工件完整度 + 差异化 selling 而非 killer result。

**registry.phase 已更新**（reframe 摘要 + 待办）。

**待办（下阶段）**：①Gate1 出图（A-1 artifact AUROC bar / ViM score 分布零重叠图 / A-3 去污染曲线 / L3 negative slope chart）②写 draft 章节（按 STORY v4 + 5 加固）③修 a4_rank_flip.py verdict bug（AND 门误判 PASS，投稿前 verifier 统一）④撞车加固：Related Work 真正面摆 ImageNet-OOD。

---

## Entry 7 — 2026-06-19 ~15:00 命门 A-4 重跑（propensity caliper 修正版）→ 全 FAIL，到拍板点

**重跑结果（4 对，1 维 propensity caliper，verifier Bash 三方对账 0 drift）**：

| 对 | n_matched | spearman(orig,C) | CI | A-4 | SMD max/mean |
|---|---|---|---|---|---|
| NIH_vs_VinDr | 156 | 0.857 | [0.40,1.0] | FAIL | 0.128/0.052 |
| NIH_vs_RSNA_normal | 382 | 1.0（七法 rank 全同 d²=0）| [1.0,1.0] | FAIL | 0.146/0.045 |
| BraTS_vs_BrainTumor | 6 | — | — | **INSUFFICIENT**（n<30 硬门剔，SMD 1.53）| — |
| HAM_vs_ISIC2020 | 228 | 0.286（GradNorm 7→2/MDS 2→4/Energy 4→7）| [-0.87,0.96] | FAIL | 0.196/0.066 |

- **propensity caliper 修复有效**：n_matched 从 43 维版的 6 → 156/382/228（3 对），证实之前 n=6 是维度灾难非数据问题。BraTS（artifact AUROC 0.9997 近完美可分）propensity 也近可分 → 只配 6 对 → n<30 硬门正确剔除（如预判）。
- **A-4 命门全 FAIL**：无对达「CI 上界<0.7 OR top1 掉出 top3」。

**verifier 纠 analyst 两处误判（Bash 核 score 列，按红线工具打架信 Bash）**：
- **ViM AUROC=1.0 不是 bug/artifact，是真实完美分离**：vim_score inlier 上界~2-7 / OOD 下界~30622-153912，零重叠、量级差 6000-31000x、unique=1000/1000 无常数堆叠。物理含义 = ViM 捕到源域 virtual-logit residual = **artifact 本身**（ViM 的「OOD 检测」实为 artifact 检测）。ViM 在 raw+cleanC 都恒 top1 → top1 未掉。
- **common_support_pct=0.0 不是 bug**：score 分布零重叠 → 公共支撑面积真为 0；与 n_matched（artifact 特征配对数）是两个独立量，不矛盾。

**命门诚实解读（混合信号 + 判据低功效）**：
1. CXR 两对（NIH/RSNA spearman=1.0、NIH/VinDr=0.857）去污染后排名**基本保持** → 偏向「污染无 actionable 后果」（K2 方向）。
2. derm 一对（HAM 0.286）**真发生重排**（GradNorm 大幅升、MDS 降），但 7 方法 Spearman CI[-0.87,0.96] 巨宽 → 判不出方向。
3. **预登记 A-4 判据本身结构性低功效**：7 方法只有 7 个 rank 点，bootstrap Spearman CI 天然趋向 [-1,1]，CI 上界<0.7 近乎不可达（除非 spearman 点估计就很低 + n 极大）。判据可能与真值无关地恒 FAIL。
4. **K2 literal（Spearman>0.9 几乎不变）仅 1/3 对满足**（NIH/RSNA=1.0；VinDr 0.857<0.9；HAM 0.286）→ 不是干净 K2 触发。

**SMD**：3 有效对 smd_max 0.128/0.146/0.196 均略>0.1 阈（mean<0.1）→ 配对平衡边界达标，cleanC 结论可信度打折但未失效。

**到拍板点（拍板 #4/#5：stage-gate FAIL 放行 / 改判据方向）**：命门 A-4 既非干净 PASS、非干净 K2-kill、也不能简单「inconclusive 续命」。三条路待用户拍板：①接受 K2 向 → 降 ICBINB/D&B 短文不投 CVPR（诚实退守）②扩方法池 7→12-15（OpenOOD REACT/DICE/SHE…）或换 Kendall+permutation 提功效——但**改裁决口径触 PR-F2 预登记 = 看到 FAIL 后改方法，须 skeptic 红队 HARKing + 用户拍板**③诚实 reframe（headline 从「排名翻转」转向「artifact 完美混淆 OOD 分数本身」——ViM=1.0 由 artifact 驱动是强证据，可能比「排名翻转」更干净）。

**资产**：a4 命门表 + 4 对 cleanC/raw 排名 + l3_method_scores_raw + SMD 全落 results/。analyst 出图 a4_analysis_summary.png。

**下一步**：用户拍板方向 → 据此 /stage-gate 或 reframe STORY。

---

## Entry 6 — 2026-06-19 14:18 A-4 caliper 实现修正（留痕，先于改代码）

**触发**：Gate1 l3 实跑后 crash 残局诊断（analyst + skeptic 红队）暴出命门 A-4 方案 C 配对的实现缺陷。

**现行 43 维实现产出（证据，改代码前钉死）**：
- `artifact_matched_subset()` L535 把预登记「0.2 SD caliper」实现为 **43 维 artifact 特征空间欧式距离 ≤ 0.2×√43 ≈ 1.311**。
- 后果：NIH vs RSNA_normal（同美国 CXR 源、all-43dim artifact AUROC=0.64，artifact 分布最接近、最该配得上的一对）**只配出 6/500 对**（1.2%）。43 维标化空间随机对期望 L2≈√43，threshold 1.311 处累积概率≈0 = 维度灾难。残局 csv `results/a4_bootstrap_spearman.csv` 录得 NIH_vs_RSNA n_matched=6 / bootstrap CI 上界=1.0 / verdict A-4 FAIL。**该 FAIL 实为「样本太少无统计功效」非「排名真没翻」**（method_mean_auroc_cleanC=0.4643<0.55 已触 K3 WARN = 配对太少把 semantic 也删了）。

**修正决策（用户 2026-06-19 拍板，option ①）**：把 caliper 实现改为 **1 维 logistic propensity score 上的 0.2×SD(logit) caliper**（Austin 2011 标准含义）。
- **定性 = 实现 bug 修正，非协议变更/HARKing**。依据：①「0.2 SD caliper」在 propensity matching 文献（Austin 2011, Pharm Stat / PMC3144483；Wang 2014 AJE）确切含义 = 1 维 propensity logit 标准差的 0.2 倍，43 维欧氏球是误读；②curse of dimensionality 坐实（arXiv:2203.00554）；③**改的方向不偏向 PASS**——现 FAIL 是「无功效（CI=1.0）」，修正后样本变多恢复功效，结果可能 PASS 也可能真 FAIL，是恢复「能判断」非朝 PASS 调参。skeptic 红队 0 致命放行。
- 预登记原文 PR-匹配半径只写「caliper（如 0.2 SD），不事后调」**未指定维度** → ACCEPTANCE v3 澄清此歧义、保留 v2 原文不覆盖。

**配套（防 HARKing，写入 ACCEPTANCE v3 PR-匹配半径）**：7 条冻死的 propensity 规格（plain logistic 无交互项 / 无正则或固定 L2 写明值 / k=5 fold out-of-fold 交叉拟合防自配 / caliper=0.2×SD(logit) pooled / 1:1 greedy without replacement seed=42 / **n_matched<30 硬门不计入 A-4**[替原 n<10 仅 WARN] / 配对后报 |SMD|<0.1 平衡诊断）。

**程序**：①本 LOG 留痕（先于改代码，时序可查）✅ ②ACCEPTANCE v3 澄清 PR-匹配半径 + 留 v2 痕 ③coder 按 7 规格实现 ④重跑 4 对 → analyst → verifier 核 n_matched/SMD/命门数 ⑤paper methods 必 disclose（预登记 0.2 SD→初版误作 43 维欧氏球仅 6 对无功效→按 Austin 2011 修正为 1 维 propensity，主动 disclose 防攻）。

**并行保险**：方案 A regress-out（R0a R²<0.3 全可用）作**已预登记附录 robustness 并行报，不取代方案 C 当主裁**（换主裁=改 PR-F2 承重判据，HARKing 嫌疑更大）。⚠️ R0a 七方法 R² 近乎全 0.0，方案 A 真用前派 verifier 复核非退化/占位。

**下一步**：ACCEPTANCE v3 落 → coder 实现 1 维 propensity caliper → 重 request slot（排 disagree 后）→ 跑 → analyst + verifier。

---

## Entry 2 — 2026-06-19 先驱对齐 + K4 撞车排查（researcher×3 并行）

派 3 个 researcher 并行钉死先驱地图、方法集、K4 撞车（K4 是 kill criterion，存亡攸关）。

**K4 撞车判定 = 安全，立项守得住**：
- **OpenMIBOOD（CVPR2025, arXiv:2503.16247）**：14 数据集/24 post-hoc 方法/3 benchmark（MIDOG 病理 + PhaKIR 腹腔镜 + OASIS3 脑 MRI）。建立 covariate/semantic-shift taxonomy，但把 acquisition artifact 当 OOD 目标而非混杂——**L1 artifact-only 量化 / L2 去污染 / L3 重排全 free**。撞车分 0.18。必引 baseline，非威胁。
- **PMC10532230（3D MRI, arXiv:2306.13528, MDPI J.Imaging 2023）**：自提 IHF（强度直方图特征）AUROC=0.97（MRI）超所有 DL 方法，明说「benchmark 含 implicit trivial feature → deceptive conclusions」=**做到 L1 局部**。但 **L2 去污染协议空白 + L3 方法重排空白 + 限 3D volumetric（LIDC-IDRI 肺 / VS-Seg）**。撞车风险**中**。⚠️ 它也用 LIDC-IDRI（3D）——我们走 2D 多模态别撞；Related Work 必须硬对齐，framing = 「PMC10532230 的 L2+L3 延续 + 2D 多模态推广」。
- **L1+L2+L3 完整闭环：两轮搜索零命中**。L3 去污染后方法重排闭环 = 文献真空 = 本文承重点。
- 邻域必引区分：Skin Deep Unlearning（ICML2022，dermoscopy ruler/marking unlearning 非 OOD 重排）、Shortcut Learning Medical Seg（MICCAI2024，caliper/center shortcut 限分割）、MaskMedPaint（2411.10686，diffusion inpaint 缓解非检测）、In the Picture living review（2501.10727）、arXiv 2508.09381（IAA-malignancy 非污染，落 K2 对手侧）。

**方法集 + 官方超参锁定（L3 重排用，堵臆想红线）**：
- OpenOOD 7 post-hoc 法 + 官方超参：MSP（无参）/ ODIN（T=1000, ε=0.0014）/ Energy EBO（T=1）/ Mahalanobis MDS（无参）/ KNN（K=50）/ ViM（dim=256 for ResNet18/34）/ GradNorm（无参）。repo: github.com/Jingkang50/OpenOOD configs/postprocessors/*.yml。
- backbone：TorchXRayVision DenseNet121-res224（`-all` 联合 / `-nih`）frozen encoder，HuggingFace 托管，224² 输入。MDS/KNN/ViM 从倒二层提特征，复用 frozen encoder 无需重训。
- MedIAnomaly（github.com/caiyu6666/MedIAnomaly, arXiv:2404.04518）7 集 5 模态：RSNA(CXR) / VinDr-CXR / Brain Tumor(MRI) / LAG(眼底) / ISIC2018(皮肤镜) / Camelyon16(病理) / BraTS2021(MRI)。Image-level AUROC 主指标。

**留账 TODO（必答）**：
- 去污染前后排名翻转**无标准化评测协议先例**（两轮搜零命中）→ 自拟协议，paper 明说，Spearman(原,去污染) + 补 top-k Kendall τ 凸显头部翻转。A-4 命门判据沿用此口径。
- OpenMIBOOD near-OOD 类别定义是否暗用 artifact 作信号未抓到全文（403）——若是则 L1 部分重叠，投稿前人工核。

**下一步**：派 planner 设 Gate1 实验矩阵（A-1 ≥3 benchmark 对 artifact-only AUROC + A-2 ≥3 模态 + A-3 去污染 + A-4 重排），对齐 ACCEPTANCE 草案 → skeptic 红队设计 → ACCEPTANCE 阈值冻结（拍板点）。

---

## Entry 3 — 2026-06-19 Gate1 矩阵设计 + skeptic 红队（逮 2🔴 回修）

**planner 出 Gate1 矩阵 v1**：~8 run / ~9 GPU·h（远低于 50 上限，几乎全本地 CPU+frozen encoder 推理，无需 HPC 训练）。L1 量化（R1/R2 43 维 artifact AUROC）+ R3 frozen DenseNet 提特征 + R4-R7 7 方法重排（raw + 3 去污染方案）+ R8 翻转评测。本地 ready=NIH/VinDr/BraTS/HAM；待下载=RSNA(568MB)/BrainTumor(42MB)/LAG(202MB，HPC 上传=拍板点，但 Gate1 第一刀不依赖大下载）。

**skeptic 红队 v1 → 2🔴 致命，回 planner 修**：
- 🔴 **F1 regress-out 数学缺陷**：`clean_score=raw−f(artifact)` 是线性残差化，43 维 artifact（hist/glcm/fft/stats）与 7 OOD 方法 score 物理同源（真 pathology 也靠强度/纹理表现）→ 高度共线 → 残差化连真 semantic 一起减，A-4 假翻转+踩 K3 且数学不可分。**Fix**：方案 C（artifact-matched 配对子集，不碰 score 代数）提为命门唯一裁决，regress-out 降对照（保留则先做 <1 CPU·h 受控共线 R² 准入实验）。
- 🔴 **F2 A-4 翻转协议 cherry-pick**：3 方案×3 口径=隐性 p-hacking，三口径高度正相关挡不住，n=7 Spearman 挪 1-2 名次就翻。**Fix**：预登记唯一裁决方案(C) + bootstrap CI 上界<0.7（非点估计）+ 第二口径换「机制可解释的翻转」。
- 🟡 **F3 跨域 frozen encoder 退化**：CXR 预训练 DenseNet 提 MRI/derm 可能退化到随机→翻噪声。Fix：各模态前测 7 法 AUROC<0.6 则不计入 A-4，写进 ACCEPTANCE 防 HARKing。
- 🟡→已定 **F4 L3 设定**：采纳 skeptic 判断=选 **cross-source 跨机构对**（非 MedIAnomaly 同集内 near-OOD）。near-OOD 同机构无跨机构 artifact 可去污染→假触 K2+割裂 L1↔L3 承重链。

**ViM dim 订正**（researcher 核 OpenOOD）：官方无 DenseNet121 专属 ViM 配置，planner 的「ResNet50 dim=1024」有误（OpenOOD sweep 实为 [256,1000]）。DenseNet121 N=1024<1500 → 按 ViM 原论文（arXiv:2203.10807）取 **dim=512**，paper 标注自定。

**planner v2 闭合 4 修**：L3 命门唯一裁决=方案 C 配对子集（regress-out 降对照 + R0a 共线准入闸）；A-4 改 bootstrap CI 上界<0.7 + 机制可解释第二口径；各模态准入门 R3b；cross-source L3 对；ViM dim=512。v2 矩阵 ~9 run / ~10 GPU·h 全本地。

**用户拍板（2026-06-19）**：
- ✅ **ACCEPTANCE v2 冻结**（阈值 + PR-F1/F2/F3 预登记 + cross-source L3 + A-4 命门 bootstrap CI），写入 02_ACCEPTANCE.md 标已冻结。
- ✅ **Gate1 启动范围 = 先补齐三模态再起**：下 BrainTumor(42MB, MRI 对端 P3) + ISIC2018(derm 对端 P4) + RSNA(568MB, CXR 补强 P2)，三模态齐了跑全 A-2。CXR 主场 P1（NIH+VinDr 本地 ready）。下载到本地（全跑本地，非 HPC 上传，不卡拍板）。下载源=MedIAnomaly Zenodo record 12677223 分集 tar.gz。

**下一步**：派 coder 写 5 脚本（a1_a2_artifact_auroc / extract_frozen_feats / collinearity_check R0a / l3_ood_rerank / a4_rank_flip）+ 并行下载三模态对端数据 → /loop /run-experiment 跑 → analyst 解读 → verifier 核。

---

## Entry 4 — 2026-06-19 coder 写 5 脚本 + 数据下载（执行中）

**coder 交 5 脚本**（`scripts/` 下，py_compile + smoke 全过）：a1_a2_artifact_auroc.py / extract_frozen_feats.py / collinearity_check.py(R0a) / l3_ood_rerank.py(R3b+R4-R7) / a4_rank_flip.py(R8)。
**逮 coder v1 真问题 → 回修中**：MSP/ODIN/Energy/GradNorm 用了 proxy（特征 L2-norm/logsumexp 代 logit）≠ 官方方法，违反「OOD 方法用官方实现」红线，会让 L3 排名失真。回修：extract 同时出 14 维 DenseNet logits；MSP/Energy 用真 logits（multi-label sigmoid 适配）；MDS/KNN/ViM 用 1024 特征（ViM 补 virtual-logit 项）；ODIN/GradNorm 需 live 模型（输入扰动/梯度范数），l3 脚本 load frozen DenseNet 跑 live。诚实标注：DenseNet 是 CXR-only，logit-based 方法在 MRI/derm 预期崩=F3 准入门要拦的设计预期非 bug；ODIN T=1000 从 ImageNet 标定用于 multi-label CXR 是已知 transfer 局限，paper limitation 标注不擅改。

**数据下载修正**：MedIAnomaly Zenodo record 12677223 实际只 6 集（BrainTumor/BraTS2021/LAG/RSNA/VinCXR/Camelyon16），**无 ISIC2018**（datasets.json 旧注释有出入）。修正后：
- MRI 对端 = **BrainTumor.tar.gz (42MB)** 下载中 → `data/external/medianomaly/`
- CXR 补强 = **RSNA.tar.gz (568MB)** 下载中 → 同上
- CXR 主场 P1 = NIH + VinDr（本地 ready）
- derm 对端改用**本地 ISIC2020**（`data/raw/isic2020/` 已 ready）vs HAM10000，零下载（cross-source = 两不同 challenge 源）
- MRI ID = BraTS2021 normal（本地 ready）

**下一步**：等下载完解压验数 + coder logit 修完重烟测 → `/loop /run-experiment` 跑 R1/R2/R3/R0a/R4-R7/R8 → analyst 解读对 A-1~A-4 → verifier 核命门数字。

---

## Entry 5 — 2026-06-19 Gate1 实跑（extract + A-1/A-2 PASS，l3 命门跑中）

**coder 二修接线**：补全 4 个 cross-source 跨机构对（P1 NIH×VinDr / P2 NIH×RSNA / P3 BraTS×BrainTumor / P4 HAM×ISIC2020），within-source（BraTS normal-vs-tumor 等）降对照独立 csv。+ logit 真实现（18 维 DenseNet logits，MSP/Energy 真 logit，ODIN/GradNorm live 模型，ViM 补 virtual-logit）。

**踩坑修复**：extract --device cuda **segfault exit 139 零输出** → cv2+torch 双 OpenMP 冲突（libiomp5md duplicate）。修=跑前置 `KMP_DUPLICATE_LIB_OK=TRUE OMP_NUM_THREADS=1` + `python -u`。**后续所有 torch/cv2 跑都带此 env**（已记入运行规范）。

**extract 成功**：11 集×500 = 5500 行，feats(500,1024)+logits(500,18) 全落 `results/feats/`。GPU 提特征 ~4min。

**A-1/A-2 跑完（Bash 核 csv）**：
- NIH vs VinDr (CXR) = **0.896**（对齐 G5 的 0.92，n=300）
- NIH vs RSNA (CXR) = 0.640（两美国源更像，最弱对）
- BraTS vs BrainTumor (MRI) = **0.9997**（⚠️ 近满，诚实留账：待 analyst 核是否两 MRI 库强度归一化差异平凡分离，别夸大成纯 scanner）
- HAM vs ISIC2020 (derm) = **0.816**
- **A-1 PASS**（3 对≥0.80 ✓≥2 + BraTS>0.90 ✓）；**A-2 PASS**（三模态各≥1 对>0.75）。⚠️ 脚本 a2_pass 逻辑 bug（CXR 误判 0，实际按「≥1 对>0.75」该过）待修。
- within-source 对照（仅附录）：BraTS normal-vs-tumor 0.878 / HAM NV-vs-nonNV 0.786 / RSNA normal-vs-pneumonia 0.835（artifact 在同源内也分离病理=已知 shortcut，不入命门）。

**l3 命门跑中**（R3b 准入门 + R4 raw + R5 方案C配对 bootstrap + R6/R7 对照）。跑完 → R0a 共线 + a4_rank_flip → analyst 解读 → verifier 核 → /stage-gate。

---

## Entry 1 — 2026-06-18 立项（ideation run-006 G6）

**立项决策（用户拍板）**：ideation run-006「现象优先选题」漏斗 138→C107 唯一 G5 去风险确证候选，用户 G6 拍板「立项 C107 + 并行续 C003」。

**选题轨迹**（全留痕 `project/ideation/runs/2026-06-18_run-006_phenom-medimg-failure/`）：
- G0 宪章：医学影像真实失效现象，锁 CVPR + 排除清单（NCA/JEPA + selinf/disagree/公平长尾/mech-interp/配准/failmap）。
- G1：ideator×8 产 138 候选（S3 矛盾×3 + S4 dataset×3 + S5 残值 + S6 SOTA边界）。
- G2：去重 49 + 硬排除 16 + 撞车砍 38（皮肤 shortcut 重灾区被 Winkler/Bissoto/Transfusion/Zech 等撞车清光）→ 35。
- G3：InnoEval 排序，C107 rank#2（7.75，CVPR-fit 9 最高）。
- G4：skeptic 红队 🟡（撞 OpenMIBOOD 风险，待 G5 核）。
- G5a：免费撞车核查 SURVIVE（OpenMIBOOD/PMC10532230 只概念/3D，无去污染重排闭环）。
- **G5 killshot 现象坐实**：artifact-only 43 维（resize 224² 控分辨率）NIH vs VinDr **AUROC=0.9213±0.009**（n=1000，csv `results/c107_artifact_ood_killshot.csv`）。核心 claim 没死。

**headline**：医学 OOD benchmark 在测采集 artifact 非病理异常；artifact-only 特征顶满 OOD → 方法排名被混淆。承重 = L1 多 benchmark 量化 + L2 去污染协议 + **L3 重排闭环（命门 actionable so-what）**。venue CVPR 2027 / 退路 NeurIPS D&B/MICCAI/TMLR。

**红队残差（必答）**：差异化全压「2D 系统化 + 去污染 + 重排闭环」，Related Work 须硬对齐 OpenMIBOOD(CVPR25)/PMC10532230(3D)；0.92<0.95 不夸大成「完全 artifact」；命门 = 去污染后排名真翻转（否则降 ICBINB）。

**下一步**：
1. researcher 全面对齐先驱 + MedIAnomaly 方法集，锁差异化、补 K4 撞车排查。
2. /design-experiment 设计 Gate1 矩阵：≥3 benchmark 对（NIH/VinDr + MedIAnomaly 7 集 + dermoscopy 跨集）跑 A-1 + 去污染 A-3 + 重排 A-4。
3. ACCEPTANCE 阈值冻结（拍板点）。

**资产**：G5 killshot 脚本 `project/ideation/.../06_experiments/c107_artifact_ood_killshot.py` + csv 已复制进 results/。
