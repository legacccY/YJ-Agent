# QuantImmune F-pilot — THEORY LEDGER（理论账本，冻结假设链防 HARKing）

> 服务 quantimmu-bench F-pilot（QuantImmune 定量原型可行性去风险）。三层防线 kickoff 产出，2026-06-26。
> Layer1 theorist(opus) 推导 → Layer2 skeptic(opus) 独立证伪 + 第二 theorist(opus) 命门多路投票 → Layer3 verifier(sonnet) 核 csv。
> **铁律：§2 假设链出实证前写死，禁跑完调（防 HARKing）。命门塌缩=拍板点。**

---

## §1 pilot 定义（drift 契约）
- **claim**：用本地 DS1+DS2 真 ELISpot SFC 连续值，把 9(→19) 个现有免疫原性工具分数 + 肽/HLA 序列特征做 **stacking 元模型回归** target=SFC，在 leave-one-patient-out CV 下 per-patient rank 相关能否超最佳单工具地板。
- **数据**（verifier 核 master_backbone.csv ✅）：183 唯一肽 / 15 患者（DS1 6人[1-6] + DS2 9人[101,102,104-110]，103 缺）。SFC min=-33.7 / max=677 / median=73 / **n_pos=172/183(93.9%)**。
- **不碰**：IEDB 连续 GT 路线（已实证 FAIL，肿瘤子集 functional 连续正例仅 6 条，见 PHASE0_iedb_fillrate_MEASURED.md）；benchmark 部署节点。
- **成本**：≈0 GPU（183×~10 表格 ridge，CPU 秒级）。回报/成本比由「廉价」撑，非「高上限」撑。

## §2 假设链冻结表（出实证前写死）
| # | 承重假设 | 若错 → 现象 | 置信 | 状态 |
|---|---|---|---|---|
| H1 | 正信号工具误差**部分独立**（实测两两均值 r̄=0.130，verifier 核✅，非 theorist 早期写的 0.17）| 若 r̄ 主要来自共享 IEDB 训练误差 → 去相关不消共误差 | 中 | 冻结 |
| H2 | 有效独立信号维度 ≥3（非全塌进 binding/presentation 同源簇）| 若 d_eff=1 → stacking 退化为选最佳单工具，零增量 | 中 | 冻结 |
| H3 | 序列特征（外来度/自相似/长度残差）含工具未编码的 SFC 信号 | 若已被工具吸收 → 偏相关≈0，无增量 | **低（未测，最该先验）** | 冻结·待验 |
| H4 | 跨患者信号可迁移（14 患者学的权重对第 15 患者有效）| 若纯患者特异（deepHLApan rho_std=0.458 核✅）→ LOPO ρ 塌回 0 | **低** | 冻结·高风险 |
| H5 | 地板可预登记固定 + 同折配对 LOPO 设计可控 | 不预登记/不配对 → 永远卡「点估升但 CI 含地板」| 高 | 冻结 |

## §3 命门定理（能否超地板的承重前提）
> **定理（薄回报 × 重罚）**：组合 in-sample 上界 R_max（两路独立推：theorist#1 用 Mosier 复合得 ~0.40 含 oracle 权重正偏；theorist#2 用等相关块得 ~0.33）与地板 R_floor=0.26 之差仅 **+0.07~0.14**，而拟合 9 个权重的 Olkin-Pratt 收缩罚 ≈0.08（n≈167）。**拟合式 stacker 的 LOPO 期望 ≤ 地板；唯一可能超地板的是零自由度固定平均（top-4~6）或极强正则 ridge（有效 DOF 压到 2-3）。**
>
> **可证伪条件（任一成立则 pilot 判负/降级）**：
> 1. 标签打乱后元模型 ρ ≈ 真实 ρ → 学的是泄漏/批次（**最先做，零成本**）。
> 2. 元模型权重塌缩到单一工具 → H2 错，无 stacking 价值。
> 3. 配对 LOPO Δz 患者间方向不一致（半数患者反劣）→ H4 错。
> 4. 元模型 ρ CI 下界**未能**超预登记地板 CI 上界 → 只能报点估增量+方向（**两路独立预测大概率如此**）。

## §4 回报预测表（乐观/中性/悲观 per-patient Fisher-z；出实证前写死）
| 档 | 预测 LOPO per-patient Fisher-z | 条件 |
|---|---|---|
| 乐观 | 0.36~0.40 | H3 兑现 + 权重跨患者泛化（≈生物天花板下沿）|
| **中性（最现实，两路收敛）** | **0.27~0.33（+0.02~0.07 over 地板）** | 零参数固定平均/强正则 ridge；拟合式被收缩罚拉回 |
| 悲观 | ≤0.26（甚至跌破，stacking 反伤）| 拟合式 + 序列特征过拟合 / 地板通胀 + DS1 稀释 |

- **功效判决（两路独立一致）**：15 患者 + 跨患者强异质（SD(z)≈0.48），配对检验 +0.10 增益功效仅 ~24%，+0.04 增益功效 ~6%。**即便真有增量也大概率测不出 p<0.05。** 要测显著需患者数升到 ~55-90（算力无关，是样本瓶颈）。
- **MAE 判决**：绝对 SFC 的 MAE 在 LOPO 下被每患者 precursor frequency 截距主导，结构性失效。**只 rank 口径可信；MAE 若报须用患者内中心化版。**

## §5 三层防线裁决 + F2 设计强制约束（skeptic 🔴-1 修正案）
**裁决：命门未塌（方向可做，本地有连续 GT），但当前设计会产出无效决策 → F2 必须内置以下修正（全程 ~0 GPU）才放行。**

| 约束 | 来源 | 必做项 |
|---|---|---|
| ① 换终点：去显著性检验 → 效应量估计 | skeptic🔴-1 + 两路功效 | 主读数=**配对同折 Δ(meta−floor) 的点估 + bootstrap 95%CI**（患者重抽），**不**以"p<0.05"当 go/no-go。报"点估+方向+CI 宽"。|
| ② catastrophe gate | skeptic🔴-1 | 负信号闸=元模型点估**明显低于同折地板**才判 stacking 反伤；否则"点估升一点 CI 宽"=**已去风险、值得上 powered 研究**。|
| ③ 地板去偏 + 同口径 | skeptic🔴-1 + theorist#1 A10 | 在**同 15 患者、同 LOPO 折**重算地板；预登记**一个有生物先验的固定 baseline**（单工具或固定等权免疫原性集成），**不**用 9 工具事后取最大；meta vs baseline **配对同折同患者**比。|
| ④ DS1 全阳稀释处理 | skeptic🔴-1 | DS1 6 患者 SFC 阳性内变异小 → per-patient ρ 不可靠：聚合时降权/单列，或主结论只在 DS2 报、DS1 当敏感性。|
| ⑤ 防泄漏对照（命门定理可证伪条件1）| 两路 theorist 一致 | **标签打乱重跑 LOPO 必归零**；若仍 >0.1 = 管道漏。第一个跑的对照。|
| ⑥ IEDB overlap 量化 | skeptic🟠-A | 跑**已写好**的 analysis/iedb_overlap_check.py，报泄漏肽占比 + 剔除后敏感性 ρ（堵审稿；rank 口径泄漏有界，非救命）。|
| ⑦ 目标患者内中心化 | skeptic🟠-B | 训练前 SFC 做患者内中心化（或拟合患者内秩/加患者随机截距），让目标与 rank 评估对齐，防 ridge 拿工具分当患者均值代理。|
| ⑧ 跨数据集指纹敏感性 | skeptic🟠-C + theorist TODO-4 | 报 DS1-only / DS2-only 分层 ρ；若分层翻号 = 在学批次非生物。|
| ⑨ 模型复杂度上界 | 两路 theorist 一致 | 主力=**强正则 ridge（有效 DOF 2-3）或零参数固定平均**；浅 GBDT 仅敏感性对照不当 headline；**小 NN 拒**（n=183 无依据）。先剪枝剔死工具（DeepImmuno/NeoTImmuML/HLAthena 信号≤0.03）+ 冗余簇留一，实际入模 ~5-8 特征。|

## §6 残留 TODO
- TODO-1（analyst/F2 内）：测肽长/外来度/自相似对 SFC 的偏相关，验 H3，未测前序列特征增量不记账。
- TODO-2（已并入 F2 约束③）：全 15 患者 LOPO 重算预登记地板。
- TODO-3（researcher，可选外锚）：查免疫原性工具横评是否有已发表「stacking vs best single tool」LOPO 基准，验 0.24-0.33 区间。
- TODO-4（verifier 已核）：DeepImmuno fisherz=+0.013（非 -0.01）；工具间均值=0.130（非 0.17）——LEDGER 已用核后真值。

## §7 一句话判决
**GRAY·值得做但要为「不显著」预先定调**：F-pilot 是 IEDB FAIL 后唯一仍有连续 GT 的零成本去风险动作；两路独立推导收敛=点估可微超地板（中性 0.27-0.33），但 15 患者下任何现实增量统计不显著（功效 ≤25%），绝对 MAE 结构性失效只 rank 可信。**最大风险=把泄漏的 in-sample ~0.33 误当 LOPO 结果卖（标签打乱必做）。** pilot 不能验天花板，只能验「stacking 相对去偏地板有无增量+方向 + 给 powered 研究估方差」——这才是该交付的东西。立项与否是后续拍板点，pilot 结论（能/不能超去偏地板、差多少、方差多大）是关键证据。
