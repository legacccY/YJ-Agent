# 图1「30 工具 Spearman 排序能力」核查报告：到底为什么出错

> 服务：QuantImmuBench §3.1 图1（PPT `progress_v4_rev1` 里的横条图 `fig1_spearman_30tools.png`）。
> 日期：2026-07-03。核查方式：本机独立重算（verifier scipy 全新代码）+ HPC 侧探查 + 主线代码级根因核 + analyst 方法学审计，四方交叉。
> 结论一句话：**图上的数字没算错，但排序被稀疏覆盖的伪相关污染，榜首三名是假的。**

---

## 0. TL;DR

| | 原图（有 bug） | 修正后（effN≥5） |
|---|---|---|
| 第 1 名 | HLAthena 0.627 | （全覆盖口径）netMHCpan_BA 0.392 |
| 第 2 名 | andy90 0.585 | MHCflurry 0.308 |
| 第 3 名 | Seq2Neo 0.441 | PRIME 0.294 |
| HLAthena | **0.627（#1）** | 0.207（#12），↓0.42 |
| andy90 | **0.585（#2）** | 0.134（#22），↓0.45 |
| Seq2Neo | **0.441（#3）** | −0.234（垫底，覆盖失败），↓0.67 |

原图把两个「随机猜级别」的工具（HLAthena 自己在 `00_README` 标 proxy AUC≈0.51）抬上了冠亚军。**根因是一处「分母数错了」的代码缺陷**——不是数据错，不是公式错，是防小样本的门槛数错了对象。

---

## 1. 这张图是什么 + 数据链

- **图**：`analysis/figures_ppt_v4/fig1_spearman_30tools.png`，30 个工具按「突变级 per-patient Spearman」降序排的横条图，是 PPT 展示各工具排序能力强弱的主图。
- **数据源**：`analysis/official/R1_single_maxpool_official.csv` 的 `fisherz_rho_raw` 列。
- **算法**：`analysis/official/R1_official.py` 调 `_official_common.per_patient_spearman`——对每个工具取 `<Tool>_max` 列，在 DS2 的 9 个患者（P101/102/104-110）里各自算「工具打分 vs Elispot 真值」的 Spearman，再跨患者用 Fisher-z 等权聚合成一个数。
- **输入**：`data/frozen/pooled_clean_9mer.csv`（130 肽级行）。

---

## 2. 双侧核查结果（本机 + HPC）

**本机侧**：verifier 用全新 scipy 代码从 `pooled_clean_9mer.csv` 独立重算 30 个工具的 `fisherz_rho_raw`，逐个对 canonical CSV，最大偏差 `|diff|=0.00005`。→ **图上数字本身可复现，PASS，没有算错。**

**HPC 侧**：探查 `/gpfs/work/bio/jiayu2403/quantimmu/`，只存**逐 allele 的原始工具输出**（HLAthena 的 `.msi/.txt`、predig/deepimmuno 的输入输出，按 HLA×MT/WT×窗长组织），**没有** pooled/R1/spearman 的任何副本。→ 被质疑的「每患者聚合 + 覆盖」这一步 100% 是本机后处理，HPC 不参与、也无法独立重算此图。所以「单边对复查」的实质就是本机重算这一条，已完成。

**两侧合起来的意思**：问题不在原始工具打分（那些在 HPC 上、日期 6-24~25、provenance 完整），问题在本机把逐 allele 分数聚合到「患者级 Spearman」的那段代码。

---

## 3. 到底为什么出错——四环因果链

### 第一环：数据是「漏的」，不是满的
`pooled_clean_9mer.csv` 每个患者有一批肽（行），比如 P101 有 12 行。但**不是每个工具对每条肽都有分数**——工具因为肽长超出适用范围、HLA 不匹配、覆盖不到，就填 NaN。HLAthena 在 P101 的 12 行里**只有 3 行真有分数**，其余 9 行是空的。

所以「P101 有 12 行」≠「HLAthena 在 P101 有 12 个分数」。这是坑的地基。

### 第二环：3 个点算相关，必然凑出 ±1（数学必然）
`spearman_np` 内部会先去掉 NaN（`m = ~(isnan(x)|isnan(y))`），只拿有效点算相关。但**3 个点算秩相关，只要碰巧单调递增就是 +1、单调递减就是 −1**，3 个随机点约各 1/6 概率撞上完美 ±1。所以凡是覆盖稀疏的工具，必然在这些患者上刷出一堆假的 ±1。这不是数据错，是小样本秩相关的数学宿命。

实测：全部 13 个 rho=±1 的格子，**无一例外落在有效点数 effN=2 或 3 的患者上**（重灾患者 = P102，8 个工具在它这里撞 ±1）。

### 第三环：门槛数错了分母（真正的 bug）
代码本来有防线，专门挡这种小样本伪相关——`MIN_PEP=3` / `FISHER_MIN_N=3`（点数 ≤3 就剔出）。**它的本意正是挡住 2-3 点凑的 ±1。** 但 `per_patient_spearman` 里这样写（`_official_common.py:292-298`）：

```python
g = work[work["Patient_ID"] == pat]
n = len(g)                                    # ← 拿的是「患者总行数」= 12
rho = spearman_np(x, y) if n >= min_pep else np.nan   # 门槛用 12
ns.append(float(n))                           # 传给聚合剔除的 n 也是 12
```

- `spearman_np` 用**有效点数（3）**算 rho；
- 但门槛判定和聚合剔除（`fisherz_weighted_agg` 里 `keep = ns > FISHER_MIN_N`）用的 `n` 都是 **`len(g)`=患者总行数（8~19，全 >3）**。

后果：一个只有 2-3 个有效点、rho=±1 的患者，因为总行数 8-15 顺利过门槛，**满权进入等权 Fisher-z 聚合**；连方差 `Var(z)=(1+rho²/2)/(n−3)` 都用被灌水的 n，把它当成十几个点的可靠估计。

> **打个比方**：班里 40 人只交了 3 份卷子，这 3 份碰巧全 100 分。规矩是「至少 5 份卷子才算班级平均分」，但你数的是「全班 40 人」而不是「实际交卷 3 人」，于是 40>5 通过，把这个虚高的满分记进了年级排名。防线没坏，是数错了分母。

### 第四环：clip + arctanh 把假分放大成「重炮」
Fisher-z 聚合要把 rho=1 转成 `arctanh(1)=∞`，会崩，所以 clip 到 0.9999。但 `arctanh(0.9999)≈4.95`，是个巨大的值。9 个患者等权平均时，别人 z 都在 0.1~0.5，唯独这个假患者是 4.95——一个数就把平均 z̄ 拽到 0.74，tanh 回来 = **0.627**。**一个 n=3 的伪满相关患者，几乎单枪匹马定了 HLAthena 的第一名。**

### 因果链一句话
> 工具覆盖不均（某患者只 2-3 条非 NaN）→ 小样本秩相关必出 ±1（数学必然）→ 门槛用**总行数**而非**有效点数**，数错分母（设计 bug，写代码时默认「干净表每行都有分」）→ 伪 ±1 逃过防线 → clip 后 arctanh 放大成 z≈5 → 等权平均被单点绑架 → 榜首虚高。

四环里前两环（数据漏 + 数学必然）是客观事实躲不掉，**唯一出错也唯一能修的是第三环**：门槛该数「这个工具实际打了几分（effN）」，却去数了「这患者一共几行（len g）」。

---

## 4. 修正重算：门槛改用有效覆盖 effN

修法 = 把门槛从「患者总行数 `len(g)`」改成「有效非 NaN 点数 effN」，effN 不足的患者剔出聚合，方差/CI 也用 effN。产物（未覆盖 canonical）：
- `R1_recomputed_effN5.csv`（主，effN≥5）+ `R1_recomputed_effN3.csv`（对照）+ `R1_compare_orig_vs_effN.csv`（新旧对照）
- 修正图 `fig1_spearman_30tools_effN5.png`

### 为什么门槛必须 ≥5，不能 =3
effN≥3 修不干净——HLAthena 的 P101 有效点数正好 =3，卡在门槛线上进得去：

| 工具 | 门槛 effN≥3 | 门槛 effN≥5 |
|---|---|---|
| HLAthena | 0.627（没变，P101 effN=3 逃过）| 0.207 |
| andy90 | 0.585（没变）| 0.134 |
| Seq2Neo | 0.543（仅剔 2 个 effN=2 患者）| −0.234（覆盖失败）|
| netMHCstabpan | **0.854（反而冲到第一！）** | 覆盖失败（9 患者剔 7 个）|

effN=3 甚至更糟——netMHCstabpan 那个 P101 effN=3 的 rho=+1 让它假分冲到 0.854。**analyst 实测 effN=4 仍偶发 ±1，门槛定 5 才稳。**

---

## 5. 修正前后对照 + 双向污染

伪迹是**双向**的：既把假货抬上榜首，也把真货错误压低。

**被伪迹抬高（剔除后暴跌）**：
| 工具 | 原 rho（名次）| 修正 rho（名次）| Δ |
|---|---|---|---|
| HLAthena | 0.627（#1）| 0.207（#12）| −0.42 |
| andy90 | 0.585（#2）| 0.134（#22）| −0.45 |
| Seq2Neo | 0.441（#3）| −0.234（覆盖失败）| −0.67 |

**被伪迹压低（剔除后翻正冲榜前）**——这批工具原来被 P102 的 rho=−1 拖成负分：
| 工具 | 原 rho（名次）| 修正 rho（名次）| Δ |
|---|---|---|---|
| MHCnuggets | −0.108（#24）| 0.460（#1）| **+0.57** |
| MUNIS | −0.265（#27）| 0.304（#4）| +0.57 |
| MHCseqNet | −0.269（#28）| 0.299（#5）| +0.57 |
| NetTepi | −0.275（#29）| 0.293（#7）| +0.57 |

**纹丝不动的（全 9 患者覆盖，无伪迹）**：netMHCpan_BA 0.392、MHCflurry 0.308、PRIME 0.294、IMPROVE 0.285、PredIG 0.250、IEDB_Calis 0.249（Δ≈0.00005）。**这批才是原图里唯一能信的部分。**

---

## 6. 一个新警示 + 最稳的 headline

effN≥5 门槛有个副作用：它让部分工具从 9/9 覆盖降到 8/9（剔掉了 P102 那个稀疏患者），于是**跨工具的 n_full 不再对齐**，直接比 rho 仍不完全公平。典型：**MHCnuggets 在 effN5 下冲到第一（0.460），但它是靠剔掉 P102 单个 −1 从 −0.108 翻上来的、只有 8/9 覆盖、而且是呈递类 EL 模型**——这个「第一」依赖单点剔除，不稳。

**最干净、最能站住的 headline = 只在全覆盖 9/9 的工具里比**：

```
netMHCpan_BA  0.392  CI[0.140, 0.594]  9/9   ← 真·第一（DTU 受限）
MHCflurry     0.308  CI[0.166, 0.457]  9/9
PRIME         0.294  CI[0.123, 0.466]  9/9
IMPROVE       0.285  CI[0.092, 0.482]  9/9
PredIG        0.250  CI[0.131, 0.368]  9/9
IEDB_Calis    0.249  CI[0.031, 0.466]  9/9
Repitope      0.122  CI[0.007, 0.242]  9/9
```

**CI 宽度是最干净的判别器**：这批稳榜工具 CI 宽度 0.24~0.46；而伪高工具 Seq2Neo/netMHCstabpan CI 宽度 >1.8（在图上并排画 CI，宽度自己就把伪高工具暴露了）。

> 注：netMHCpan_BA 是 DTU 受限工具（结果照常算，部署/再分发受 DTU 书面同意约束）。若 headline 不想用受限工具，则第一名为 MHCflurry 0.308。

**这也和项目已知的另一个方法学问题（肽长混杂）方向一致但独立**：控肽长列 `fisherz_rho_lenctrl` 里 netMHCpan_BA 反而升到 0.432 真第一；但控肽长救不了 Seq2Neo（lenctrl 反而更离谱 0.874）。→「稀疏覆盖 ±1」和「肽长混杂」是两个独立病根，原图 raw 排序两个病一起占。

---

## 7. 修法建议（分档）+ 拍板点

**这是核查报告，未改任何 canonical `official/` / `data/` 文件。以下动到底层口径的都是拍板点，待余嘉/袁老师定。**

1. **止血（可先做，不动底层）**：PPT 那张图旁标注「榜首受稀疏覆盖伪相关污染，以全覆盖工具 netMHCpan_BA 为准」，或直接换用本报告的修正图 `fig1_spearman_30tools_effN5.png`（已画好：加 CI 误差棒 + 每工具标 n_full + 覆盖失败工具灰掉单列）。
2. **改口径（拍板点）**：把 `per_patient_spearman` 的 `n=len(g)` 改成有效非 NaN 计数，让 `MIN_PEP`/`FISHER_MIN_N` 真正生效，门槛提到 effN≥5。**⚠️ 这会重排 R1 榜单，并连累下游所有用 `per_patient_spearman` 的产物（R2 pooling / R3 fusion / R4 ablation / R5 LOPO / R6 robustness / R7 / R8 排名），需整体重跑。属偏离已冻结方法，袁老师拍板级。**
3. **报覆盖**：无论是否改口径，图/表都应报每工具的有效覆盖（n_full 或每 rho_p 格子的 effN），不能只画一根光杆条形——覆盖信息本身就是读者判断可信度的关键。
4. **覆盖失败工具单列**：Seq2Neo、netMHCstabpan（9 患者只有 2 个像样覆盖）不该进主排序，标「coverage insufficient」。

---

## 附：产物清单（均在 `analysis/official/recompute_effN/`，未覆盖 canonical）
- `recompute_R1_effN.py`—重算脚本（门槛改 effN，参数化 5/3）
- `plot_R1_effN.py`—修正版画图脚本
- `R1_recomputed_effN5.csv` / `R1_recomputed_effN3.csv`—重算结果（主 + 对照）
- `R1_compare_orig_vs_effN.csv`—新旧逐工具对照
- `fig1_spearman_30tools_effN5.png`—修正版图
- `REPORT_fig1_why_wrong.md`—本报告
