# G5 杀手锏 verdict — run-011 候选 A（胎儿超声半监督分割 benchmark）

> 2026-06-24。PSFHS 上 Supervised vs Mean Teacher，标注比例 {5/10/20%}，2 seed，100ep。数字 Bash 核 `results/results.csv`。

## 结果（dice_mean，100ep 真跑行）

| 比例 | Supervised | Mean Teacher | MT 增益 |
|---|---|---|---|
| 5% | 0.853(s1) | 0.863(s1) | +1.0% |
| 10% | 0.900(avg) | 0.904(avg) | +0.2% |
| 20% | 0.925(avg) | 0.925(avg) | ~0 |

注：5% 每方法仅 1 个 100ep seed（s0 是 5ep 烟测被 state 跳过）；正式跑需补 r005_s0 100ep。

## Verdict：✅ GRAY-PASS（不砍带债，R9 三分流）

核心命门**未被证伪**——曲线有可报告结构：
1. 标注效率曲线干净单调（监督 5→20% +7.2%）
2. MT 增益随标注比例单调递减（经典 SSL 收益递减，可报告 finding）
3. 增益集中难结构 PS（5% 下 +2.1%），易结构 FH 无差 → PS/FH 不对称真 story

## 暴露的真债

PSFHS 监督 baseline 已强（20%=0.925），SSL headroom 薄（峰值 spread 1.0%<2%）。裸两方法撑不厚 ACCV。**这是 floor/ceiling effect 不是 claim 死**（R9 GRAY 本意：欠功效不砍）。

## 还债设计（带进正式立项）
- 加更低标注比例 1%/2%（headroom 大区间）
- 加 HC18 + FUGC（FUGC 宫颈更难，baseline 没那么满）
- 加 baseline：CPS / UAMT / FixMatch-Seg（排名结构）
- 自适应阈值增量 + PS/FH 不对称分析当方法贡献
- 补 r005 第二 seed 100ep

## 结论
G5 PASS（GRAY）→ 候选 A 可进 G6 正式立项，但设计须按上面还债（低比例+多集+多baseline），不靠裸 MT-vs-Sup spread。
