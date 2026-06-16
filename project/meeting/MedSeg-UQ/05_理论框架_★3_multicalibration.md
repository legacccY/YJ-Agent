# ★3 理论框架：分割的 Multicalibration —— 空间结构能否打破指数下界？

> 项目 MedSeg-UQ 主攻方向（替代已降级为 MICCAI 档的 ★1 trade-off，见 `02_理论框架.md`）。
> 日期：2026-06-16。会场目标：COLT / NeurIPS / ICLR（纯理论档）。
> **纪律（E1 三翻教训）**：先建 toy 验「结构红利是否存在」这个未知二元问题，**再写定理**；自验通过先派 reviewer 裁，绝不「自验通过即写已成」。

---

## 0. 选型依据（3 路 researcher 收敛）

- ★2（最优聚合）**高塌缩**：Guarino et al. CVPR'26 已做经验版且实证「无单一最优算子」；Neyman-Roughgarden'21 已给 proper-scoring→最优聚合（QA pooling）理论；SDC 做 Dice 特例。→ 弃。
- ★3（分割 multicalibration）**塌缩中-低**：核心硬问题零先例（含 COLT'25 全程序）。竞品 Fair Risk Control（ICML'24）做分割 FNR 但 demographic 子群+post-hoc；Liu-Wu'24 是 NLP 版。**须正文回答「为何不能直接把 GMC/Liu-Wu 套到分割」——答案 = 空间结构-复杂度问题（真新）。** → 选。

---

## 1. 核心开放问题（COLT 级，零先例）

**背景定理（已核，researcher）**：
- 高维校准指数代价（Tang 2505.21460）：d 维 simplex 上 ε-calibration 需 **T ≥ exp(poly(1/ε))**，上界 d^{O(1/ε²)}。
- 在线 multicalibration 下界（2601.05245）：Ω(T^{2/3})，**仅 3 个不相交子群**即可建立。
- 这些下界**对无结构输出**。空间结构能否绕过——**零文献**（正反都没人碰）。

**我方核心问题**：
> 分割输出有**空间 Markov / CRF 结构**（相邻像素强相关、联合分布因子化）。问：**multicalibrate 分割的联合标签分布，其样本/轮次复杂度，能否因空间结构严格低于无结构的指数下界？**

**两种 reading（须先厘清，决定问题对不对）**：
- **(a) 逐像素边际校准，子群=像素位置**：|G|=HW 个子群，复杂度 poly(HW)——**不指数，不是 COLT 难题**（平凡，避开）。
- **(b) 联合分布校准**：预测整图联合标签分布，outcome 空间 2^{HW}，d=2^{HW} **指数**。multicalibrate 这个联合 = 指数难。**空间 Markov 结构使联合因子化（链/树 CRF 的联合由局部势决定）→ 有效维度坍缩**。**这才是 COLT 核心**：结构把 2^{HW} 的指数难度降到 poly？

**∴ 主攻 = reading (b)：结构化联合分布的 multicalibration 复杂度**。直觉（待验）：Markov 结构应给「结构红利」（类似图模型推断从 #P 降到链上线性），但 multicalibration 是**对抗在线**设定，红利未必转移——**这正是未知、值得证的点**。

---

## 1.5 形式化已钉死（researcher 核，防塌缩四条）

**前作边界**：reading-(b) = **部分空白**。最接近 = **Kuleshov-Liang 2015「Calibrated Structured Prediction」**（NeurIPS'15）——校准大输出空间的边际查询，**但**：① 非 multicalibration（无子群多组）② 校准用户指定边际、非利用结构降复杂度 ③ **无 sample/computational complexity 分析**。核心 gap（multicalibration + 因子化降指数复杂度）**无前作**。

**推荐形式化（researcher 给，采用）—— Clique-marginal Multicalibration**：
- 预测器 f: X→Δ(Y)，Y={0,1}^{HW}，联合 CRF 因子化（pairwise/k-clique 势）。
- 子群族 G（g:X→{0,1}）。
- **结构化 MC 误差** = max_{g∈G, S: |S|≤k} max_{config} | E[ 𝟙{y_S=config}·g(x) ] − E[ q_S(config)·g(x) ] |，
  即对**所有 k-clique 边际 q_S** 做多子群校准。
- **复杂度参数 = (n=HW 像素, k=团大小/Markov 阶, |G|, ε)**；目标 **poly(n^k,|G|,1/ε)** vs 朴素联合 MC 的 **exp(n)**（outcome 空间 2^{HW}）。

**防塌缩四条精确区分（写进正文 Related Work）**：
1. **Kuleshov'15**：非 multi-group、无复杂度分析、不用因子化 → 我方加这三者。
2. **Low-Degree MC（2203.01255）**：degree-k 降的是 **group 函数**多项式复杂度，**不降 outcome 基数**（输出仍有限 C 类）；我方指数来自 |Y|=2^{HW}，正交。
3. **Tang（2505.21460）**：d=simplex 维，T=d^{O(1/ε²)}，d=2^{HW} 时**双指数**；没碰因子化把 d 从 2^{HW} 换 poly(HW)——正是我方贡献。
4. **Decision-cal dimension-free（2504.15615）**：dimension-free 针对 **feature** 维，非 **outcome** 基数 |Y|。

---

## 2. 极简 toy（已初推，⚠️待审，不预设）

> 主线初推 1D 链,得到正信号 + 看清边界。**标「初推待审」,不当定论**（E1 教训）。

**Toy 设定**：1D Markov 链,n 像素,y∈{0,1}^n,联合按边(pairwise 2-clique)因子化。预测 q 取同链结构。clique=边(k=2)。

**初推结果（正信号）**：
1. **clique 边际低维 ⟹ poly**：n−1 条边,每边边际是 {0,1}²=4 维(常数)。校准每条边的 4 维边际(对所有 g∈G)= (n−1)·|G| 个**低维**校准子问题,各花 poly(1/ε) → **总 poly(n,|G|,1/ε)。无指数。**
2. **链/树 joint 由 clique 边际决定**（junction-tree 因子化:joint = ∏clique边际 / ∏separator边际）⟹ 若 q 取树结构,校准全部 clique 边际即重构出 truth 的**树投影**。
3. ⟹ **结构红利存在**:链上 clique-marginal MC = poly(n),而朴素联合 MC（outcome 2^n）= exp(n)。**指数 → 多项式,结构兑现。**

**⚠️ 诚实边界（主线自标,防再翻车）**：
- 「clique 边际校准 ⟹ **全联合**校准」**仅当 truth 本身是该树结构**;truth 非树时,q=truth 的树投影(I-projection),全联合不等。**故诚实 claim = 校准所有 clique/局部边际(下游分割实际要的局部统计),非无条件全联合。** 这是真实保证,不夸。
- 预测器须限定结构族(CRF/树),否则 clique 边际不定 joint。可接受的建模假设。

**浮现的核心参数 = treewidth(树宽)**：
> 链=treewidth 1→poly;一般 CRF 复杂度猜想 **poly(n,|G|,1/ε)·exp(O(treewidth))**——低树宽 tractable、高树宽 exp。**把图模型精确推断的 treewidth 参数化搬到 multicalibration**,这是 COLT 级且新（researcher 确认无前作）。`【猜想·待证·待审】`

**仍未知 / 下一步要判**：
- loopy（高树宽）下是否真 exp（下界）?——嵌 2601.05245 的 Ω 下界到高树宽团,证结构救不了高树宽(对称完成 treewidth 刻画)。
- 对抗**在线** MC（非 batch）下结构红利是否仍转移?（E1 的教训:batch 直觉未必过 online）——须单独验。

---

## 3. 立即下一步（严守纪律）

1. ✅ 形式化钉死（researcher）：clique-marginal MC + 防塌缩四条 + treewidth 参数。
2. ✅ toy 初推（主线）：链上 clique-marginal MC = poly(n)，结构红利存在（有边界）。
3. 🔄 **派 reviewer 攻 toy + treewidth 猜想**（进行中）：找退化、查「是否只是 Kuleshov'15 + junction-tree 的平凡组合」、判 online vs batch 红利是否转移。
4. reviewer 过 → 推一般 CRF 的 treewidth 上界 + 高树宽下界（嵌 2601.05245）→ 完整 treewidth 刻画。
5. **Opus 深核**：clique-marginal MC ⟹ joint 的边界、online 对抗设定红利转移性（E1 教训：batch 直觉未必过 online）。

## 候选主定理（待证待审，不预设）
> **结构化（clique-marginal）multicalibration 的复杂度 = poly(n,|G|,1/ε)·exp(O(treewidth))** —— 把图模型推断的 treewidth 参数化引入 multicalibration。低树宽（链/小宽网格）poly 可解、高树宽 exp（下界待证）。贡献 = 定义(clique-marginal MC) + treewidth 上界 + 高树宽下界 + 与 Kuleshov/Low-Degree/Tang 的精确区分。

## 🔴 reviewer-4 裁决：当前形态大体塌缩，仅余一条窄活路

- **toy「结构红利」= 稻草人**：「朴素联合 MC over 2^n」是本文自定义、外部无人主张的目标；真问题从来是局部边际校准，而那**本就 poly**。**没打破任何外部既成立的指数下界。**
- **treewidth 主定理上界 = junction-tree（Lauritzen-Spiegelhalter 教科书）+ per-marginal 校准 的机械拼接**，treewidth 进复杂度纯因「算 clique 边际=做推断=treewidth 参数化」这个已知事实，**非 MC 新难度 → 上界塌缩**。
- 退守「只保证局部边际校准」后，与 **Kuleshov'15 marginal calibration + Hébert-Johnson multi-group 的直接叠加**无本质差异（multi-group 是 MC 自带、因子化是 junction-tree 自带、复杂度=两已知相乘）。
- **唯一窄活路（go/no-go 门）**：弃 batch/「打破指数」全部包装，**只赌 online 对抗 regret**——严格算链/低树宽下 online clique-marginal MC regret，证它**严格优于逐 clique 独立基线**，且 gap 源自 MC 对抗性（非推断难度）。**风险**：2601.05245 的 Ω(T^{2/3})（3 子群即触发）可能打在每条边 → 总 (n−1)·Ω(T^{2/3})，红利被吃光。reviewer 判这条也很可能塌缩。

## 诚实状态（★3）
- 形式化钉死、toy 初推——但 reviewer-4 判 toy 正信号建在稻草人对照上、treewidth 上界塌缩成已知组合。
- **唯一未毙的 = online regret go/no-go**（链上严格算 online clique-marginal MC vs naive 基线）。过则真新、不过则毙。**先只做这一件，不推一般定理、不立项。**
- ⚠️ 承重文献待 researcher 联网核：2601.05245（online MC Ω(T^{2/3}),3 子群）、Tang 双指数表述、Kuleshov'15 是否真无复杂度分析。
