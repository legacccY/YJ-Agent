# 数字三方对账报告

> 服务 quantimmu-bench。verifier(opus) 用 Bash/awk/python 直读 csv，禁 Read 看数据，2026-06-24。
> 真源：`analysis/metrics_ds2_8tools.csv`(73 行)、`analysis/metrics_ds2.csv`(46 行旧 5 工具)。
> 口径：csv `n_pep` ≠ `n_pos`/`n_neg`。max>0 阈值下主流工具 n_pep=101/n_pos=90/n_neg=11。任务里「101/100/98」=n_pep，「阴性 10/11」=n_neg。

## 1. Entry 24 八工具 AUC (max,>0)
逐个回 csv `max,>0` 行核 AUC_ROC：

| 工具 | 声称 | csv 实值 | 判定 |
|---|---|---|---|
| pTuneos | 0.7525 | 0.7525 | ✅ |
| PredIG | 0.6611 | 0.6611 | ✅ |
| NeoTImmuML | 0.6551 | 0.6551 | ✅ |
| IMPROVE | 0.6207 | 0.6207 | ✅ |
| ImmuneApp | 0.589 | 0.5889 | ✅(舍入) |
| PRIME | 0.528 | 0.5276 | ✅(舍入) |
| DeepImmuno | 0.4813 | 0.4813 | ✅ |
| deepHLApan | 0.419 | 0.4188 | ✅(舍入) |

全 8 个 AUC 一致。最优聚合表(pTuneos mean>0=0.7813/PredIG mean>0=0.7495/IMPROVE top3mean>10=0.6805)逐行核 csv ✅全对。

## 2. Spearman (top3mean/mean 行)
| 声称 | csv 实值 | 判定 |
|---|---|---|
| IMPROVE ρ=0.320 p=0.001 | rho=0.3202 pval=0.0011 (top3mean) | ✅ |
| PredIG mean ρ=0.280 p=0.005 | rho=0.2797 pval=0.0046 (mean) | ✅ |
| pTuneos ρ=0.136 p=0.174 | rho=0.1363 pval=0.1741 (max) | ✅ |

口径标注正确(IMPROVE 标 top3mean、PredIG 标 mean)。

## 3. 旧 5 工具复现 delta 0.004
metrics_ds2(旧5) vs metrics_ds2_8tools 同工具同口径全量比对(45 条 AUC)：
- max,>0(排名表)：**0.0000**(5/5 完全相同)
- 全口径(3agg×3阈值)：**0.0039**(pTuneos top3mean,>median)
- 全口径 AUPRC：0.0044
→ LOG/BENCHMARK 称「delta 0.004」csv 实算 0.0039 ✅有据(浮点/排序差异，不影响结论)。

## 4. n_pos/n_neg 边界
| 工具 | 报告 | csv(max,>0) | 判定 |
|---|---|---|---|
| PRIME | 100/89/11 | 100/89/11 | ✅(A0208/罕见 allele 全 NaN，分母 100) |
| deepHLApan | 98/88/10 | 98/88/10 | ✅(3 肽缺，阴性降 10) |
| 其余 6 工具 | 101/90/11 | 101/90/11 | ✅ |
deepHLApan 唯一 n_neg=10，其余 11，与 caveat 完全吻合。

## 5. TOOLS 卡 / DEPLOY_TRACKER
- TOOLS/pTuneos.md:39 max/>0=0.7525、mean/>0=0.7813、ρ=0.136 p=0.174 → ✅全对 csv(唯一含 DS2 benchmark 分数的 TOOLS 卡)。
- 其余 TOOLS 卡只含论文报告值+烟测单值，非本 benchmark 结论，无 csv 真源，不纳入对账。
- DEPLOY_TRACKER 仅含烟测复现单值(DeepImmuno 0.5324/PredIG 0.006138)，无 benchmark 聚合数字，无冲突。
- 旧 BENCHMARK_REPORT.md(5 工具)不含 8tools 新数字，用 metrics_ds2.csv，与 8tools 旧 5 工具 0 漂移，无冲突。

## ⚠️ 唯一内部小瑕疵（非 csv 漂移）
`analysis/BENCHMARK_8TOOLS.md` line 96/98 ImmuneApp mean−max 差值自相矛盾：line96「0.056」vs line98「0.055」。csv 实算 0.6444−0.5889=0.0555 → 两处同值不同舍入(0.055 更准)。不影响结论，建议 writer 统一为 0.055。

## 总判
**三方对账(csv↔04_LOG↔BENCHMARK_8TOOLS/TOOLS 卡)：0 处 DRIFT。**
- 8 工具 AUC/AUPRC/Spearman/p、最优聚合、n_pos/n_neg 边界、旧 5 工具 delta — 全部回 csv 实算一致。
- 结论数字(pTuneos 0.7525/0.7813 第一、IMPROVE ρ=0.320 定量最强、deepHLApan 低于随机、新 3 工具无一超第一批)**全部可信，可入 PPT/报告**。
- 唯一 ⚠️：BENCHMARK_8TOOLS line96/98「0.056 vs 0.055」文字小不一致(非数据漂移)，统一为 0.055。

> 注：verifier 核的是**数字一致性**(报告值 == csv 值)。红队 🔴-1 攻的是**统计稳健性**(这些一致的数字在 n_neg=11 下能否支撑「最优」措辞) — 两者正交，都成立：数字对，但排名差异不显著。
