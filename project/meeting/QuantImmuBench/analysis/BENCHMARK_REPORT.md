# QuantImmuBench Benchmark Report
Generated: 2026-06-23
Source: merged_all_tools_4tools.xlsx (34247 rows = subpeptide x HLA)
Data source columns: AUC_ROC/AUPRC/Spearman from analysis/metrics_ds2.csv (真跑 sklearn)

## 0. 数据概况

| 项目 | 值 |
|------|-----|
| 总行数 (subpep x HLA) | 34,247 |
| 数据集 | DS1 (82 peptides, 325 rows) / DS2 (101 peptides, 33,922 rows) |
| DS1 ELISpot | 全阳性 (min=16 SFC), 无阴性对照 → 不算 AUC, 只看排序 |
| DS2 ELISpot | -33.7 ~ 209 SFC, median=22.67; n_pos(>0)=90, n_neg=11 |
| 金标签粒度 | 每个 Peptide_ID 内 ELISpot 同值 (per full-length peptide) |

工具覆盖 (DS2, 101 peps all covered):
- DeepImmuno: 9-10mer subpeptides only (11,358 / 34,247 rows)
- PredIG: 8-14mer all windows (34,247 rows)
- IMPROVE: 8-12mer (26,790 rows)
- NeoTImmuML: 8-13mer (30,739 rows)

## 1. 主要指标 (DS2, 阈值 ELISpot > 0, n_pos=90, n_neg=11)

### 1a. 各聚合方法 AUC-ROC 对比

| Tool | agg=max | agg=mean | agg=top3mean | Spearman-rho (max) | Spearman-p (max) |
|------|---------|----------|--------------|-------------------|-----------------|
| PredIG | 0.661 | **0.750** | 0.663 | 0.198 | 0.047 |
| NeoTImmuML | **0.655** | 0.576 | 0.655 | 0.022 | 0.829 |
| IMPROVE | 0.621 | 0.618 | 0.626 | 0.243 | 0.014 |
| DeepImmuno | 0.481 | 0.519 | 0.499 | -0.117 | 0.245 |

来源: analysis/metrics_ds2.csv, Threshold=>0

### 1b. 阈值敏感性 (agg=max)

| Tool | AUC >0 (n_pos=90) | AUC >10 (n_pos=64) | AUC >median=22.67 (n_pos=50) |
|------|---------|---------|---------|
| PredIG | 0.661 | 0.558 | 0.568 |
| NeoTImmuML | 0.655 | 0.505 | 0.517 |
| IMPROVE | 0.621 | **0.656** | **0.598** |
| DeepImmuno | 0.481 | 0.519 | 0.454 |

来源: analysis/metrics_ds2.csv

### 1c. AUPRC (agg=max, 各阈值)

| Tool | AUPRC >0 | AUPRC >10 | AUPRC >median |
|------|---------|---------|---------|
| NeoTImmuML | **0.942** | 0.637 | 0.516 |
| PredIG | 0.941 | 0.677 | 0.562 |
| IMPROVE | 0.922 | **0.760** | **0.621** |
| DeepImmuno | 0.895 | 0.663 | 0.493 |

注意: AUPRC 在 >0 阈值下 baseline (prevalence) = 90/101 = 0.891, 所有工具都高于 baseline.

### 1d. Spearman (连续 ELISpot, DS2, agg=max)

| Tool | rho | p-value | 显著? |
|------|-----|---------|-------|
| IMPROVE | 0.243 | 0.014 | 是 (p<0.05) |
| PredIG | 0.198 | 0.047 | 是 (p<0.05) |
| NeoTImmuML | 0.022 | 0.829 | 否 |
| DeepImmuno | -0.117 | 0.245 | 否 (负相关!) |

## 2. DS1 Spearman (全阳性, 无 AUC)

| Tool | n (peps) | Spearman rho | p-value |
|------|----------|--------------|---------|
| DeepImmuno | 82 | -0.028 | 0.803 |
| PredIG | 82 | 0.028 | 0.804 |
| IMPROVE | 82 | 0.007 | 0.953 |
| NeoTImmuML | 82 | -0.157 | 0.159 |

来源: DS1 Spearman python -c 跑 scipy.stats.spearmanr, agg=max

结论: DS1 全为阳性 (ELISpot 16-677 SFC), 没有阴性对照; 四工具 Spearman 均不显著 (|rho|<=0.16), 无法用此数据做判别分析.

## 3. 子肽长度覆盖情况 (DS2)

| Tool | 8mer | 9mer | 10mer | 11mer | 12mer | 13mer | 14mer |
|------|------|------|-------|-------|-------|-------|-------|
| DeepImmuno | N/A | 101 | 101 | N/A | N/A | N/A | N/A |
| PredIG | 101 | 101 | 101 | 101 | 101 | 101 | 101 |
| IMPROVE | 101 | 101 | 101 | 101 | 101 | N/A | N/A |
| NeoTImmuML | 101 | 101 | 101 | 101 | 101 | 101 | N/A |

数字 = 有预测分的 Peptide_ID 数 (来源: ds2.groupby Window_Size 统计)
注意: length-stratified AUC 与全局 AUC 相同 (见 caveat 部分).

## 4. 聚合方式结论

最佳聚合因工具而异:
- PredIG: **mean 最优** (AUC 0.750 vs max 0.661), 差距明显 (+0.089)
- NeoTImmuML: max = top3mean (0.655), mean 更差 (0.576)
- IMPROVE: top3mean 略优 (0.626 vs max 0.621), 差异小
- DeepImmuno: 三种聚合均在 0.48-0.52 之间, 无系统性优势

PredIG mean 聚合最优的可能原因: PredIG 评分代表序列内在结合力, 多表位平均能更好捕捉肽段整体免疫原性势; 而 NeoTImmuML 最高分子肽 (max) 已足够区分.

## 5. 整体排名

**DS2 综合判别能力排名** (综合最优 AUC-ROC):

1. **PredIG** — 最优 AUC=0.750 (mean agg), Spearman 显著 (rho=0.198, p=0.047); 覆盖最全 8-14mer
2. **NeoTImmuML** — AUC=0.655 (max agg), Spearman 不显著; 覆盖 8-13mer
3. **IMPROVE** — AUC=0.621 (max); Spearman 最强 (rho=0.243, p=0.014); 严格阈值 (>10/>median) 时表现最稳
4. **DeepImmuno** — AUC=0.481 低于随机 (max), 仅 9-10mer; Spearman 负向; 本数据集表现最差

IMPROVE 特点: AUC 不是最高, 但连续相关性最强 (rho=0.243), 对 ELISpot 定量强度敏感.

## 6. 图

| 图号 | 路径 | 内容 |
|------|------|------|
| Fig 1 | analysis/figures/fig1_roc_curves_ds2.png | DS2 ROC 曲线对比 (agg=max, >0) |
| Fig 2 | analysis/figures/fig2_auc_bar_thresholds.png | 3 个阈值 x 4 工具 AUC 柱状图 |
| Fig 3 | analysis/figures/fig3_score_vs_elispot_scatter.png | 预测分 vs ELISpot 散点 (4 panel) |
| Fig 4 | analysis/figures/fig4_length_auc_heatmap.png | 子肽长度 x 工具 AUC 热图 |
| Fig 5 | analysis/figures/fig5_aggregation_comparison.png | 聚合方式比较 |

## 7. Caveats (诚实标注)

1. **样本量极小**: DS2 仅 101 肽、11 个阴性, AUC 置信区间宽; n_neg=11 导致 AUC 估计不稳定, 不宜过度解读排名差异.
2. **IMPROVE 降级版**: 跳过 netMHCstabpan (Stability=NaN 补 0), 缺失 Stability 特征可能压低其表现, 实际工具可能更强.
3. **NeoTImmuML 重训版**: 我们用 TumorAgDB 数据重训, 训练集 364:1 不平衡 notebook 无下采样处理, aaComp_1/cruciani_1 两列对 demo 有微小偏差; 分数不代表官方模型性能.
4. **DeepImmuno 覆盖受限**: 仅 9-10mer, 无法评估所有肽长; 其低 AUC 部分可能反映表位长度限制而非模型本身.
5. **pTuneos 不在此分析**: 无法接受全长肽段输入, 需要处理流程重设计.
6. **DS1 无阴性**: 不能做判别 AUC; 四工具 DS1 Spearman 均不显著.
7. **Length-stratified AUC 平行**: 由于每肽 agg=max 已聚合全部长度窗口, 按 Window_Size 过滤肽 ID 集合不变 (PredIG 对 101 肽全覆盖 8-14mer), 所以各长度 AUC 与全局 AUC 相同. 若要真正按长度分析需改为在特定长度窗口上取 agg.
8. **AUPRC 高 baseline**: >0 阈值下 baseline AUPRC = 0.891 (90/101), 工具 AUPRC 0.89-0.94 提升有限, 不是有力判别信号.

## 8. 建议下一步实验

1. **扩充阴性对照**: DS2 仅 11 个阴性肽, 强烈建议增加更多 ELISpot 阴性样本 (建议 n_neg >= 30); 当前 AUC 估计不稳定.
2. **PredIG mean 聚合验证**: PredIG mean vs max (+0.089 AUC) 差距值得深入, 用交叉验证确认是否稳健, 还是小样本波动.
3. **IMPROVE 完整版对比**: 补全 netMHCstabpan 跑完整 IMPROVE, 对比降级版分数差异.
4. **长度特异分析修正**: 改为在子肽层面做预测 (不 agg 到肽), 按 HLA 分组评估 (MHC I vs MHC II 混用可能引入混淆).
5. **differential agretopicity (MT-WT)**: 表中有 WT_ 分, 可算 MT_score - WT_score 看净增强是否比绝对分更预测 ELISpot.
6. **DS2 患者分层**: Patient_ID 有多个, 检查 ELISpot 是否因患者不同系统性偏移, 做 per-patient 归一化.
