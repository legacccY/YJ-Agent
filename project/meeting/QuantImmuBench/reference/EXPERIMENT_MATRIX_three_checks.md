# 实验矩阵 — 补齐袁 md 三重检验 + 12-fusion（planner 设计，待 coder 实现）

> 建档 2026-06-29。服务 QuantImmuBench 论文（投 BiB）§袁 md §2.5/§2.6/§3.3 三重检验 + 12-fusion lever。
> **只设计不写码不跑**（本次文档对齐范围）。实现 = 后续 coder 编队；跑 = 主线（纯 CPU，0 GPU，无需 gpu_slot/拍板）。
> 数字红线：**不预设任何结果数字**。袁 md 声称值（geomean 删10% +0.4643 等）本地零 csv 支撑（见 `_scratch/ALIGN_FACTS.md` §5），是本批实验**要去复现/证伪的对象**，不当预期填。下文「预期」列只写方向性判定。
> 配套 gap 全景见 `GAP_ROADMAP_vs_outline.md`；判据见 `../02_ACCEPTANCE.md`。

## 真源 / 待扩脚本
- 模型矩阵：`quantimmune/model_matrix.csv`（17 工具 × DS2 9 患者）、`scripts/out/merged_all_tools_16tools.xlsx`（子肽级，pooling 用）。
- 待扩：`analysis/fusion_study.py`（已有 fixavg/rankmean/ridge/gbdt 4 法 + LOPO + Fisher-z 核）、`quantimmune/lopo_eval.py`（单层 LOPO + ridge alpha 内层网格）。
- 复用函数：`spearman_np` / `fisherz_weighted_agg` / `aggregate_per_patient` / `paired_bootstrap` / `sign_test_exact_p` / `permutation_sign_flip_p`。

## 实验 4（地基，先做，阻断后续）：fusion 扩至 12 法 × 多维复现性
- **对应袁 md**：§2.5 表 4（12 fusion 定义）+ §3.3.1 表 6 + §3.3.4 跨维复现性。
- **12 法**（rank-fusion，病人内先各维转 rank 再融合）：① mean-rank(=rankmean,已有) ② **geomean**(承重,AND/共识型) ③ median-rank ④ powmean(p∈{−2,−1,0.5,2}) ⑤ max-rank(OR) ⑥ min-rank ⑦ z-mean/fixavg(已有) ⑧ perf-weighted-mean(按单工具 LOPO ρ 加权) ⑨ softmax-rank(T∈{0.1,0.5,1,2}) ⑩ stacking-LR(Ridge,训练类) ⑪ stacking-GBDT(训练类) ⑫ constrained-LR(非负权和=1,训练类)。
- **维配置**：3 维={PRIME,IMPROVE,deepHLApan}；4 维=+MHCflurry_affinity_neg；6 维=surv6(PredIG/IMPROVE/pTuneos/PRIME/ImmuneApp/deepHLApan)；7 维=surv6+netmhcpan_ba(geomean pooled,⚠️DTU)。**⚠️ 维成员清单需核袁 md 原始 `fourdim_cls2`/`robustness_7dim` 定义，TODO 派 researcher/问朱同学，不臆造。**
- **产物**：`analysis/fusion_methods_12.csv`、`analysis/fusion_crossdim_reproducibility.csv`(列 geq_meanrank_in_all_dims[bool])。
- **脚本**：新 `analysis/fusion_methods_12.py`（引 fusion_study 工具函数，不改原 4 法基线）。本地 CPU 秒级。
- **方向预期**：geomean 在 3/4/6/7 维全 ≥ mean-rank；stacking 三法因 n=9 饥饿过拟合落后甚至负（本地 ridge −0.30/gbdt −0.04 已实证）。

## 实验 1：nested-LOPO 双层（oracle vs LOPO 一致性）
- **对应袁 md**：§2.6 + §3.3.3 表 8（外层留一病人、内层选超参 θ；oracle vs LOPO 相等=零过拟合）。
- **两腿**：腿 A pooling-selection（内层为每工具选最优 pooling θ_pool）；腿 B fusion-selection（内层选最优 fusion 法 + stacking alpha）。oracle=θ 用含 held-out 全数据选。
- **内层网格**：pooling 走袁 md 表3 全网格（topk_w k×α、softmax T、rankdecay γ）；fusion alpha eff_DOF≈2.5。
- **产物**：`analysis/nested_lopo.csv`(列 oracle_rho/lopo_rho/gap/gap_in_CI[bool])。
- **脚本**：新 `quantimmune/nested_lopo_ensemble.py`（扩 lopo_eval 加 patient-level 内层 CV）。本地 CPU 分钟级。
- **方向预期 + 价值**：oracle 略高于 LOPO，gap 小且落 per-patient CI 带内=无系统过拟合。**核心价值=把 θ 选择关进内层折，剥离袁 md §4.3 自承的设计层 selection bias**（但工具菜单本身的选择仍在 CV 外，无法靠 nested-LOPO 消除，必须 Limitations 诚实写）。

## 实验 2：ablation（维度留一 + 加权对比）
- **对应袁 md**：§3.3.2 表 7（deephlapan_Imm 最承重 + 加权一律塌回等权）。
- **方法**：(a) 7 维逐一剔 1 维跑 geomean+mean-rank，Δρ 最大=最承重维。(b) 4 加权方案（等权/单工具 LOPO-ρ 加权/逆方差/学权重 ridge）比 LOPO ρ。
- **产物**：`analysis/ablation_leave_one_dim.csv`、`analysis/ablation_weighting.csv`。
- **脚本**：新 `analysis/ablation_dims_weights.py`（复用 fusion LOPO 核）。本地 CPU 秒级。
- **方向预期**：deepHLApan 维最承重（与亲和力/PRIME 最正交）；各加权 Δ vs 等权落 CI 内=加权不帮忙。

## 实验 3：robustness 删 10%/20% × 30 seed（图 3 核心）
- **对应袁 md**：§3.3.4 图 3 / 表 9（geomean 删10%/20% 双第一、max 满数据虚高但子采样塌）。
- **方法**：每 seed 病人内随机删 10%/20% 突变（保每病人 ≥min_pep=4）→ 重跑全 12 fusion per-patient LOPO → 跨 30 seed 聚合（子采样均值/中位/胜率）。
- **网格**：删比例 {0%对照,10%,20%} × 12 法 × **30 seed**(0..29 固定列出)。
- **产物**：`analysis/robustness_subsample.csv`、`analysis/robustness_summary.csv`(列 mean_rho/median_rho/win_rate/rank)。
- **脚本**：新 `analysis/robustness_subsample.py`。本地 CPU 分钟级。
- **方向预期 + 红线**：geomean 删10/20% 子采样均值居前；max 满数据高但子采样塌（点估陷阱）。**⚠️ 这是袁 md 声称值 +0.4643/+0.4488 的本地首次复现/证伪点——结果若与袁 md 数量级背离（很可能因 92/8 vs 101/9 口径差）需停下报拍板，不照袁 md 数字硬填。**

## 实验 5：显著性配对（geomean_vs_mean_paired，病人为配对单元）
- **对应袁 md**：§3.3.5（配对检验，病人为配对单元，明确报持平 vs 显著）。
- **方法**：病人级配对 Δz_i=arctanh(ρ_geomean,i)−arctanh(ρ_mean,i) → bootstrap(B=10000)+精确符号+全枚举置换(2^9)。对：geomean vs mean-rank、geomean vs 最强单工具、关键两两对。
- **产物**：`analysis/geomean_vs_mean_paired.csv`。
- **脚本**：扩 `analysis/fusion_study.py` Section D（三检验函数已有，换配对对象）。本地 CPU 秒级。
- **方向预期**：整合 vs 最强单工具统计持平（本地已核 fixavg p=0.974/rankmean p=0.833；袁 md Δ≈+0.038 p≈0.70）；geomean vs mean-rank 大概率也持平。**诚实呈现「排名次序≠显著差异」是验收要点，不挑显著对。**

## 依赖与并行
```
P0 卡点（非本批阻断）：鼠 B16F10/CT26 csv 缺失 → 鼠侧三重检验无法跑（归数据组）；本批 5 实验全走 DS2 人源不被卡
阶段1（地基,先做）：实验4（12 法库+多维矩阵）← 下游全依赖
阶段2（实验4 后,4 个全并行,各写独立 csv）：实验1 nested-LOPO ∥ 实验2 ablation ∥ 实验3 robustness ∥ 实验5 paired
```

## 算力
全 5 实验纯 CPU、0 GPU；最重实验3（12法×2比例×30seed×9折）≈数千次小 LOPO 单机分钟级。总计 **<0.1 CPU·h，0 GPU·h** → 无需 gpu_slot 申请、无需拍板，coder 实现后主线本地一键跑。

## 验收门槛（反推自袁 md §3.3 Key Findings，对齐 02_ACCEPTANCE G3/G4，二元 PASS/FAIL）
- **G3 整合复现性门**：PASS ⟺ geomean 在 3/4/6/7 维全 ≥ mean-rank **AND** 删10/20% 子采样均值排第一。FAIL ⟺ 任一不成立 → 袁 md headline 不成立，**停下报拍板，不改 headline 方向硬凑**。
- **G4 严格性诚实门**：PASS ⟺ ① nested-LOPO oracle−LOPO gap 落 CI 带内 **AND** ② 配对检验如实落盘（不论持平/显著）**AND** ③ shuffle 对照 ρ̄≈0（无泄漏）。FAIL ⟺ gap 系统性塌 → 诚实写进 Limitations（袁 md §4.3 已留位）。
- 辅助：实验2 维度留一 deepHLApan 最承重 + 加权塌回等权（方向印证，非硬门）。

## 风险红线（带给 coder/主线）
1. **🔴 训练类 fusion 过拟合（已实证负）**：stacking-LR/GBDT/constrained 在 n=9 必过拟合（本地 ridge −0.30/gbdt −0.04 双确认）。保留但仅作"样本饥饿铁证/反面教材"，不当推荐法；alpha/超参严格内层选，绝不外层调参。
2. **🔴 selection bias**：nested-LOPO 只能消 θ 选择层，工具菜单本身的选择仍在 CV 外 → Limitations 必须诚实写明，不得声称已完全消除。
3. **🟡 DTU 数字 pending**：netmhcpan_ba/TSCAPE 数字 `pending_DTU_consent`；含 DTU 的 7 维结果打标记，正文先用不含 DTU 的 6 维主结论。
4. **🟡 口径歧义**：全程用本地已核口径（9 患者/101 肽/min_pep=4），袁 md 92突变/8患者声称值只作对照标注，不混真源。统一需袁老师/朱同学拍板。
5. **🟡 袁 md 声称值无本地支撑**：robustness +0.4643 等本地零 csv，实验3 是首次复现点；数量级背离需停下报。
6. **维成员未冻 + 编码纪律**：3/4/6/7 维成员核袁 md 原始脚本（TODO researcher/朱同学）；coder 铁律=禁 scipy（OMP Error #15，纯 numpy/pandas/sklearn）、UTF-8 stdout、复用现有函数保口径、不改现有 4 法基线 csv。

## 交接
- → **coder**（5 脚本，无文件冲突可多 opus 并行）：`fusion_methods_12.py`(先)→`nested_lopo_ensemble.py`/`ablation_dims_weights.py`/`robustness_subsample.py`/扩 `fusion_study.py` Section D。
- → **主线跑**：纯 CPU 本地一键，实验4 → 并行 1/2/3/5。
- → **analyst 看** + **verifier 核**：geomean 跨维单调性、robustness win_rate 分母、nested gap 符号。
