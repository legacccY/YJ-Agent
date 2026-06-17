# MedAD-FailMap — Phase 0 预登记分析协议（Pre-registration）

> **冻结时间**：2026-06-17（A0 训练提交前）。
> **冻结人**：planner（opus），服务 `02_ACCEPTANCE.md` 反跑偏侧 lever「多重比较 Holm/FDR 预登记 + 防自欺」。主线已采纳全部 planner 推荐（见末「待拍板项」均已拍）。
> **效力**：本文档在看到任何 anomaly score **之前**冻结全部阈值口径、显著性检验清单、多重比较校正方案、确证/探索分线、Gate0 判定规则。一旦 A0 出分，**不得**再调阈值/换检验/挑校正方法——否则 = p-hacking，Phase 0 结论作废。
> **修改纪律**：本文档冻结后若需改任何确证性检验/阈值/校正口径，必须 reviewer 复裁 + 主线拍板 + 在本文档底部「修订记录」留痕注明原因，**绝不静默改**。探索性条目可调（本就不下确证结论），但调整也要留痕。
> **配套档**：判据真源 `02_ACCEPTANCE.md`；闸设计 `03_phase0_plan.md`；脚本 `code/{stratify_eval,conspicuity_proxy,incremental_stats,failure_boundary,train_recon_ae}.py`。

---

## 0. 数据与模型（冻结背景，照搬来源）

- **主分层集**：BraTS2021（FLAIR axial 2D），train 4211 normal / test 828 normal + 1948 tumor / annotation 1948（pixel>0=肿瘤 mask）。来源：`03_phase0_plan.md` 附录 + 官方 `MedIAnomaly/dataload.py`，HPC 计数已校验对齐。
- **跨模态外推集**：HAM10000 NV 子集（ISIC2018 NV=正常），train 6705 / test 909 normal + 603 abnormal。来源同上。
- **模型**：AE（Phase 0 主），VAE（④ 第二方法 / B0）。超参一律照 MedIAnomaly 官方：Adam lr=1e-3 / bs=64 / epochs(BraTS)=250 / latent=16 / 输入 64×64 / L2 recon / VAE β=0.005。来源：`03_phase0_plan.md` 附录（researcher 已核 repo `github.com/caiyu6666/MedIAnomaly`，复现零偏离；AE+VAE bottleneck 两层 MLP 已对齐官方）。
- **Anomaly score**：per-pixel L2 map → 图像级 = spatial mean，无后处理。来源：官方 `ae_worker.py`。
- **seed**：所有训练 + 统计脚本固定 `random_state=42`（脚本已硬编码）。Phase 0 先 1 seed 探信号；Gate0 后扩 seed 在 Phase 1 预登记另议。

---

## A. 阈值口径（钉死）

### A.1 「检出成败 detected」阈值 —— **冻结：anomaly_score top-10%（90th percentile），tumor-only 集内定阈**（主线已拍）

| 项 | 冻结值 | 来源 / 依据 |
|---|---|---|
| 阈值定义 | `detected = (anomaly_score >= P90)`，`P90 = np.percentile(scores, 90)` | 脚本 `stratify_eval.py` / `incremental_stats.py` / `failure_boundary.py` 已统一用 `threshold_pct=90` |
| **在哪个集合上算 P90** | **PC-A（A1/A2/A3）+ PC-C（C2/C3）**：在 **tumor-only** 子集（1948 张）内算 P90 并定 detected | 语义 = 「肿瘤图里 anomaly_score 排前 10% 算被这个 AD 检出」 |
| | **PC-B（B1/B2/B4）失败定义**：同样 tumor-only 内 P90，`y_fail = 1 - detected` | `failure_boundary.py` 只取 tumor 行 |
| | **PC-C C4（risk-coverage / selective AUROC）**：**不用 P90 detected**，改用 normal(0) vs tumor(1) 真 AD label 在 **normal+tumor 混合集**上算 AUROC | C4 是 selective-AD 语义，需两类（已修「only one class」bug） |

**选 10% 的依据 + 诚实说明**：
- 10% 是**雏形/惯例值**，**官方 MedIAnomaly 未指定 per-image「检出成败」二值化阈值**（官方只报 image-level AUROC）。脚本已显式标 `TODO: 阈值选法官方未明确`。
- **因此 top-10% 的绝对值不进确证性结论的字面解读**（见 D 节）：确证性结论看「检出率/失败概率**随协变量的单调/交互趋势**」与「跨集外推保留率」，这类**排序型**结论对阈值绝对值不敏感。
- **预登记敏感性分析（确证结论的稳健性闸，必跑）**：复跑 PC-A 单调/交互、PC-C C2/C3、PC-B B2/B3 在 **三档阈值 {top-5%, top-10%, top-15%}** 各一遍。**确证结论只在三档方向一致时才算数**；仅 10% 成立则降级探索性。三档不另立 family 做多重比较（稳健性检查非新假设）。

### A.2 size / contrast 分桶边界 —— **冻结：分位数三等分（33/67 percentile），≥3 桶**（主线已拍）

| 项 | 冻结值 | 来源 |
|---|---|---|
| 分桶方式 | **分位数**三等分 0/33/67/100 | `stratify_eval.py` `percentile_bin(n_bins=3)` |
| size 定义 | 最大连通域面积（像素，mask pixel>0，4-连通），64×64 mask 坐标系 | `compute_mask_covariate` |
| contrast 定义 | `|mean(img[lesion]) - mean(img[ring])|`，ring=3px 膨胀环带 XOR lesion | `compute_contrast(dilation_px=3)` |
| A3 交互网格 | size 3 × contrast 3 = 9 格 | `_write_interact_csv` |

依据：分位数保每桶样本量均衡（≈649/桶），避免极端桶 n 过小。环宽 `dilation_px=3` 与 size 下限过滤的微调留 Gate0 由 analyst 报告后复裁（不改「分位数三等分」冻结决定，调整须留痕）。

### A.3 conspicuity reliability 排序方向 + 复合权重 —— **定不了，划为探索性，不进确证结论**

C4 排序方向（conspicuity 高=更可靠？）+ reliability 复合权重均未定（脚本 TODO，需 A0 出分后实验验）。**冻结决定：C4 risk-coverage 全划探索性**（生成假设、不下确证结论），不作 ③「conspicuity 桥可操作」的确证证据。③ 确证靠 C2+C3（见 B/D）。

---

## B. 确证性检验清单（穷举 17 个编号，每条预登记）

> 每条 = Phase 0 实际跑的一个显著性检验。**清单之外不得新增**；A0 出分后想多测的一律进探索性、不进 Gate0。

### family 总览（详见 C）

| family | 含检验 | Pillar |
|---|---|---|
| **F-A** | T1, T2, T3 | ① |
| **F-C** | T4.1–T4.5, T5.1–T5.5 | ③ |
| **F-B** | T6, T7, T8.1, T8.2 | ② |

### F-A：PC-A 协变量失败边界（Pillar ①）

| # | 检验名 | H0 | 统计量 | 侧 | α | 脚本 |
|---|---|---|---|---|---|---|
| **T1** | size→检出率单调 | β_size=0 | `detected ~ size_px` LR 系数 Wald → chi2(1) | 双侧 | 0.05 | ⚠️ 待补（见实现缺口） |
| **T2** | contrast→检出率单调 | β_contrast=0 | `detected ~ contrast` LR Wald → chi2(1) | 双侧 | 0.05 | ⚠️ 待补 |
| **T3** | size×contrast 交互（① 命门） | 交互系数=0 | `detected ~ size+contrast+size:contrast` LR 交互项 Wald / 嵌套似然比 → chi2(1) | 双侧 | 0.05 | ⚠️ 待补 |

### F-C：PC-C per-image 增量信息（Pillar ③，防循环论证）

> **y = detected**（tumor-only P90 派生），非 label（tumor-only label 恒=1）。测「given anomaly_score 后 conspicuity 是否额外预测检出成败」。

**C2 嵌套 LR 似然比**（每特征一条）：

| # | 特征 | H0 | 统计量 | 侧 | α |
|---|---|---|---|---|---|
| **T4.1** | sigma_global | loglik_full=loglik_base | `chi2=2(ll_full−ll_base)`,df=1 | 单侧 | 0.05 |
| **T4.2** | glcm_cluster_prom | 同 | 同 | 单侧 | 0.05 |
| **T4.3** | glcm_contrast | 同 | 同 | 单侧 | 0.05 |
| **T4.4** | fft_spectral_entropy | 同 | 同 | 单侧 | 0.05 |
| **T4.5** | cnr_proxy_otsu | 同 | 同 | 单侧 | 0.05 |

实现：`incremental_stats.py run_c2_lr_test`，full=[score,feat] vs base=[score]，输出 `incremental_C2_lr_test.csv`。

**C3 控制 size+contrast 后残差偏相关**（每特征一条）：

| # | 特征 | H0 | 统计量 | 侧 | α |
|---|---|---|---|---|---|
| **T5.1** | sigma_global | 偏相关=0 | residualize on [size,contrast] 后 Pearson r, t=r√(n−2)/√(1−r²) | 双侧 | 0.05 |
| **T5.2** | glcm_cluster_prom | 同 | 同 | 双侧 | 0.05 |
| **T5.3** | glcm_contrast | 同 | 同 | 双侧 | 0.05 |
| **T5.4** | fft_spectral_entropy | 同 | 同 | 双侧 | 0.05 |
| **T5.5** | cnr_proxy_otsu | 同 | 同 | 双侧 | 0.05 |

实现：`incremental_stats.py run_c3_partial_corr`，输出 `incremental_C3_partial_corr.csv`。

### F-B：PC-B 外推 + strong baseline（Pillar ②）

| # | 检验名 | H0 | 统计量 | 侧 | α | 脚本 |
|---|---|---|---|---|---|---|
| **T6** | 跨集外推（BraTS→HAM） | 跨集 AUROC≤0.5 | 跨域 AUROC + bootstrap CI（500 boot），判 CI 下界 | 单侧 | 0.0125（Bonf 4，见 C） | `failure_boundary.py run_b2` |
| **T7** | extrapolation 未见极小 size | 外推 AUROC≤0.5 | mid→small size LR AUROC + bootstrap CI | 单侧 | 0.0125 | `run_b4` |
| **T8.1** | 多维边界 vs SB1（size 单变量） | Δ AUROC≤0 | Δ + bootstrap p=P(Δ_boot≤0) | 单侧 | 0.05（Holm 内） | `run_b3` |
| **T8.2** | 多维边界 vs SB2（size+contrast） | Δ≤0 | 同 T8.1 | 单侧 | 0.05（Holm 内） | `run_b3` |

> B1 边界拟合系数 = 描述性输出，非假设检验，不进清单。

---

## C. 多重比较校正方案（钉死）

> 原则：**family 跑前划定**，每 family 内同时报 Holm（控 FWER，主判）+ BH-FDR（辅）；**Gate0 以 Holm 为准**。family-wise α=0.05。

| family | 成员 | 数 | 主判 | α |
|---|---|---|---|---|
| **F-A** | T1,T2,T3 | 3 | Holm + FDR | 0.05 |
| **F-C** | T4.1–5 + T5.1–5 | 10 | Holm + FDR（**C2+C3 合并统一**） | 0.05 |
| **F-B** | T6,T7,T8.1,T8.2 | 4 | T8.x Holm；T6/T7 用 Bonferroni 调整 CI（98.75%，α=0.05/4）并入 family | 0.05 |

**冻结决策（防事后挑范围）**：
1. **F-C 合并 C2(5)+C3(5)=10 个统一 Holm/FDR**（同一科学问题：given 已知量后是否还有增量预测力）。汇总 `incremental_FC_family_holm.csv`；各子 csv 内 p_holm 标注「仅 family 内 5 个，非确证判定用」，Gate0 只认汇总表。
2. **F-B 内 T6/T7 用 Bonferroni 调整 CI（各用 98.75% CI 即 α=0.05/4）并入 F-B family 控错**（主线已拍选项 a，更严）；T8.1/T8.2 走 Holm。
3. **family 间不跨校正**（F-A/F-C/F-B 回答三个独立 Pillar，三道独立闸）。
4. **敏感性三档阈值不算多重比较**（同一结论的稳健性复算，要求三档全一致比单档更严）。

### 实现缺口（交 coder，纯 CPU，**A0 训练不阻塞**，A0 出分前补完）

- [ ] **T1/T2/T3 显著性检验**：当前 `stratify_eval.py` 只出描述性桶检出率 csv，**无 LR Wald/交互似然比**。补三个 LR，输出 T1/T2/T3 chi2+raw p，合并 F-A family Holm/FDR（`stratify_significance_FA.csv`）。
- [ ] **F-C 合并 family**：C2+C3=10 个统一 Holm/FDR，汇总 `incremental_FC_family_holm.csv`。
- [ ] **F-B 控错口径**：T6/T7 CI 从 95% 改 98.75%（α=0.0125）。

---

## D. 确证性 vs 探索性分线（防把探索当确证卖，STORY 红线）

> 规则：**确证 = 跑前预登记 + 过 family Holm + 三档阈值一致 → 进 Gate0**。**探索 = 生成假设、描述现象，绝不下「成立/证明」、绝不进 Gate0**。报告时探索结果显式标 "exploratory, hypothesis-generating only"。

### 确证性结论（过了才算数，进 Gate0）

| 结论 | 支撑 | family |
|---|---|---|
| ① size 边界系统存在 | T1 Holm 显著 + 三档一致 | F-A |
| ① contrast 边界系统存在 | T2 Holm 显著 + 三档一致 | F-A |
| ① size×contrast 有交互 | T3 Holm 显著 + 三档一致 | F-A 命门 |
| ③ conspicuity 有增量信息 | F-C ≥1 特征 C2 或 C3 Holm 显著 + 三档一致 | F-C |
| ② 跨集外推不塌 | T6 CI 下界≥0.70 且≥集内 0.80× | F-B |
| ② 多维边界赢 baseline | T8.1 且 T8.2 Holm Δ>0 显著 | F-B |
| ② extrapolation 成立 | T7 CI 下界>0.5 | F-B |

### 探索性产出（不进 Gate0，必标 exploratory）

- **C4 risk-coverage**（排序方向/权重未定，A.3）
- **B1 边界拟合系数**（描述性）
- **top-10% 绝对检出率数值**（阈值雏形，只看趋势）
- **GBM 失败边界超参**（n_estimators=50/max_depth=3 经验值无官方依据，T8 看相对差确证、绝对 AUROC 探索）
- **VAE 一切**（Phase 0 主跑 AE，VAE 失败几何差异确证留 Phase 1）

> **③ 红线**：F-C（C2+C3）过 Holm 前，**不得**在任何文档/图/LOG 落「conspicuity 桥成立」。只 ρ 高 / 只 C4 单调 / 只优于重建误差 = 弱证据，不算确证。

---

## E. Gate0 判定规则（二值化，可机械判定）

> 「显著」= 该 family Holm 校正后 p<0.05 且三档阈值 {5,10,15%} 方向一致。无「基本通过」模糊空间。

### PC-A（Pillar ①）

| 判定 | 规则 |
|---|---|
| **PASS（绿）** | T1、T2 至少 2 个 Holm 显著（三档一致）且检出率方向符合预期单调 **且 T3 交互 Holm 显著**（三档一致） |
| **AMBER（黄）** | T1/T2 至少 2 轴显著但 **T3 交互不显著** → 报拍板：补 texture/位置轴找交互，找不到 → ② 降级 MICCAI |
| **FAIL（红）** | T1、T2 显著轴<2 → 停，重审协变量/数据；仍红 → 方向不成立报拍板 |

### PC-C（Pillar ③）

| 判定 | 规则 |
|---|---|
| **PASS（绿）** | F-C ≥1 特征在 C2 或 C3 Holm 显著（三档一致） |
| **FAIL（红）** | F-C 全 10 个 Holm 均不显著 → ③ 诚实退守，砍 per-image 腿，①② 继续。**不得**因 C4 好看翻案 |

> C4 探索性，不参与 PC-C 判定。

### PC-B（Pillar ②）

| 判定 | 规则 |
|---|---|
| **PASS（绿）** | T6 跨集 AUROC（CI 下界）≥0.70 且≥集内×0.80 **且** T8.1、T8.2 Holm Δ>0 显著 **且** T7 CI 下界>0.5 |
| **AMBER（黄）** | T6 跨集 AUROC 0.5~0.70（雏形仅一对，统计力弱）→ 标黄不判死，Phase 1 扩≥3 集严判 |
| **FAIL（红）** | T6 CI 下界≤0.5 **或** T8.1/T8.2 Δ≤0（输给 size baseline）→ 报拍板：退守 MICCAI 受控失败现象学档 |

### Gate0 总决策

| 三闸组合 | 决策 |
|---|---|
| A 绿 + C 绿 + B 绿/黄（雏形不塌） | **全绿 → 进 Phase 1**（扩≥3 集严判 Gate1，矩阵预登记另议） |
| A 红 | 停，重审；仍红报拍板 |
| A 黄（无交互） | 报拍板：补轴 / ② 降级 MICCAI |
| C 红 | ③ 诚实退守砍 per-image 腿，①② 继续（按预案自动，不报拍板） |
| B 红 | 报拍板：退守 MICCAI |
| **B 外推腿退守（T6 无读数，T7/T8 部分过）** | **预登记原未预见此态，2026-06-17 补档 + 主线拍板**：「外推腿整条退守（不出读数）」既非字面 AMBER（AMBER 锁「T6 测出 0.5~0.70 弱值」，没测≠测出弱）也非字面 FAIL（锁「T6≤0.5 或 T8 Δ≤0」）→ **落决策表空隙，报拍板**。**主线已拍（B）：有条件进 Phase 1，带债推进**——② 核心承诺『可外推』Phase 0 实质未验，**Phase 1 第一硬前置（=Gate1 闸条件）= 出一个真同构的跨集/跨模态外推读数**（HAM lesion 分割管线 或 换有 mask 的第二集），出不来则退 MICCAI。**收口表述守诚实：A/C 双绿确证 PASS + PC-B 未验，进 Phase 1 非 Gate0 机械全绿** |

> **反跑偏**：Gate FAIL 按预案走，**不临时找理由续命**、不调松门槛回填。门槛改动 = 改 ACCEPTANCE 方向 = 拍板点。

---

## 关键冻结项一句话摘要

1. **detected = anomaly_score top-10%（P90），tumor-only 集内定**（C4 例外走混合真 label）；10% 雏形，确证靠趋势/排序不靠绝对值，加三档 {5/10/15%} 敏感性扫描为稳健性闸。
2. **分桶 = 分位数三等分（33/67），≥3 桶**；size=连通域面积、contrast=3px 环带差。
3. **conspicuity 排序方向/权重未定 → C4 全划探索性**，不进 ③ 确证。
4. **确证检验穷举 17 个**：F-A{T1,T2,T3}、F-C{T4.1-5 + T5.1-5}、F-B{T6,T7,T8.1,T8.2}。
5. **多重比较**：3 family 各 Holm（主）+FDR（辅）；F-C 合并 10 个统一 Holm；F-B 内 T6/T7 用 Bonferroni 调 CI 并入；family 间不跨校正；敏感性三档不算多重比较。
6. **确证 vs 探索分线**：C4 / B1 系数 / 绝对检出率 / GBM 超参 / VAE = 探索性，不进 Gate0；③ 桥成立需 F-C Holm 过关才落。
7. **Gate0 二值化**：三闸 PASS/FAIL 全数值门槛，FAIL 按预案走不续命。

---

## 待拍板项（主线已拍，留痕）

1. **A.1**：接受 top-10% detected 主口径 + 三档敏感性扫描 — ✅ 采纳。
2. **C 决策 2**：F-B 内 T6/T7 用 Bonferroni 调整 CI 并入（选项 a，更严） — ✅ 采纳。
3. **A.2 微调**：contrast 环宽 / size 下限是否 Gate0 复裁（不改分位数三等分） — ✅ 采纳（Gate0 由 analyst 报告后复裁，留痕）。

## 交 coder 的实现缺口（纯 CPU，A0 训练不阻塞，A0 出分前补完）

1. T1/T2/T3 显著性检验（LR Wald + 交互似然比）+ F-A family Holm/FDR 汇总。
2. F-C 合并 C2+C3 为 10 个统一 Holm/FDR 汇总表。
3. F-B 按选项 a 调 T6/T7 CI 置信水平到 98.75%（α=0.0125）。

> 三项实现完成前，Gate0 的 F-A 判定、F-C 合并判定缺统计支撑——**A0 可先训练出 anomaly score，但 Gate0 正式判定须等这三项补完**。

## 修订记录

- 2026-06-17 planner 初版冻结（A0 提交前）；主线采纳全部推荐拍板，落盘 `05_preregistration.md`。

- **2026-06-17 T6（跨集外推 BraTS→HAM）诚实退守 —— 主线拍板，reviewer 复裁留痕**

  **缘起**：A0（BraTS）出分后推 T6，pre-flight 审计（reviewer→planner→reviewer 复裁）逐层逮到 T6 下游 = RED，且核心是科学根基问题非工程 bug：
  - 🔴 评分 split 不存在：`train_recon_ae.py::_save_isic_scores` 只扫 `test_nv`/`test_abnormal` 目录，本地 HAM 实为 `HAM10000_images_part_1/part_2` + metadata（dx 列），训练完不产 HAM score csv。
  - 🔴 跨集特征错配：`run_b1` 用真 mask 特征 `size_px`/`contrast` 训 clf，`run_b2` 用整图代理 `sigma_global`/`cnr_proxy_otsu` predict HAM + 无 scaler，量纲与物理含义断裂 → 跨集 predict 输出纯噪声。
  - 🔴 **HAM 侧失败语义本身是预登记缺口**（§A.1 只冻了 BraTS tumor-only P90，HAM 侧 detected/y_fail 从没冻）。

  **planner 修正方案（决策 1）**：引入 HAM 异常皮损子集（dx≠nv，3310 张）当「待检出目标」对应 BraTS tumor，子集内 P90 算 y_fail，称与 BraTS「tumor-only 内 P90」严格同构 + BraTS 侧额外训 proxy-only clf（`[sigma_global, cnr_proxy_otsu]` + StandardScaler，BraTS fit / HAM transform）专供 T6。

  **reviewer 复裁 = CONDITIONAL，实质推翻决策 1 原样落地（🔴）**：BraTS 的 y_fail 语义是 **tumor 区域**漏检——小肿瘤淹在大片正常脑组织里、lesion conspicuity 低导致整图 anomaly_score 被稀释，驱动量是**病灶/背景面积比 × 对比度（lesion-level 几何）**。HAM 皮镜异常图是**整图即一个皮损特写**（皮损占画面主体），不存在「小病灶嵌正常背景」的几何；特征从 mask 几何（size_px）退化成整图统计量（σ）后，被外推函数的物理意义已断裂。「HAM 异常整图 ↔ BraTS tumor 区域」= **image-level 漏检 vs pixel-region 漏检的偷换（貌合神离非真同构）**。即便用整图代理硬迁跑出 PASS，证的是「跨域 image-level AD 可分性」≠ STORY 贡献①「failure-boundary（病灶几何→漏检）可外推」，会被对抗审稿按 STORY 正交轴一击穿。要真同构须补 HAM 无监督 lesion 分割、在病灶上算同口径 size/contrast（= 一条新管线大工程）；HAM 无可信 mask 则此对作废。

  **主线拍板（用户）**：**诚实退守**。T6 BraTS→HAM 标记为 **「不可同构外推 · Phase 0 退守 · 留 Phase 1 重设计（需 HAM lesion 分割管线方可真同构）」**。**不得用整图代理凑 PASS**（守 §E 反跑偏：不临时找理由续命）。本次 HAM-NV AE（B0）训练健康完成，checkpoint + HAM 重建能力作为 Phase 1 可复用资产归档，但**不产 T6 跨集确证读数**。

  **对 Gate0 / PC-B 的影响**：T6 在 Phase 0 不出确证读数 → 按 §E，PC-B 不字面 PASS（PASS 需 T6+T8.1+T8.2+T7 全过）。但 PC-B 不字面 FAIL：T7 已重设计救回（large 方向 AUROC=0.6447，CI 下界 0.5835>0.5），T8.1/T8.2 已过。PC-B 最终以 T7+T8+三档敏感性为准，T6 退守标 exploratory，留 Phase 1 扩 ≥3 集 + 同构重设计后严判。**§A.1/§B/§E 的既有阈值口径一律不动**（本条只记录 T6 此对退守，不改任何确证检验定义或门槛）。

- **2026-06-17 Gate0 重判收口 + §E 补「B 外推腿退守档」—— /stage-gate（verifier 0 drift → opus 严判）+ 主线拍板（B）有条件进 Phase 1**

  跑 `/stage-gate medad-failmap`：verifier 直核 csv = **0 drift**。opus reviewer 严判：**PC-A ① PASS 绿 / PC-C ③ PASS 绿 / PC-B ② 不达绿**（T8.1/T8.2+T7 large 过，但 T6 跨集+跨模态缺席 → ② 字面「三条全过才绿」不满足）。T7 重设计**合法非 p-hacking**（预授权时序成立）。反跑偏审计干净（T6 退守=教科书级反跑偏正例）。Gate0 总决策落 §E 决策表**空隙**（「外推腿退守」原未预见）→ 报拍板。

  **主线拍板（用户选 B）= 有条件进 Phase 1**：不现在退 MICCAI（A/C 扎实方向没死）、不假装全绿；**Phase 1 第一硬前置（Gate1 闸条件）= 出一个真同构跨集/跨模态外推读数**，出不来退 MICCAI。已在 §E 总决策表补「B 外推腿退守档」行。**此为改预登记结构（补决策档），按修改纪律 reviewer 复裁 + 主线拍板 + 留痕齐备；既有阈值/确证检验定义一律不动。** Phase 1 次优先：≥3 seed 方差带、C4 校准补确证、T8 写作只引相对 Δ 不碰绝对 0.964。
