# Benchmark 方法学红队报告

> 服务 quantimmu-bench 8 工具 ELISpot benchmark(DS2)。skeptic(opus) 红队，2026-06-24。攻 headline「新 3 工具无增量、第一批 pTuneos/PredIG/IMPROVE 最优」的推理链。只攻不改。
> 一句话定调：caveat 写得诚实(§8 已自曝小样本+IEDB overlap)，但有一条真致命伤被「小样本」叙述掩盖了。

## 🔴 致命（建议阻断对外强结论措辞，不阻断 benchmark 本身）

### 🔴-1 「pTuneos 最优」用确定性排名语言，但 n_neg=11 下统计不可区分
- 主结论说 pTuneos 最优(AUC 0.752/0.781) > PredIG(0.661/0.750)，据此给袁老师推荐。
- 但 AUC 不确定性由少数类主导：n_neg=11，AUC 95% CI 宽度经验在 ±0.13~0.18。pTuneos 0.752 与 PredIG 0.661 差 0.09，几乎确定落在彼此 CI 内。
- §8 caveat 自己写「排名差异<0.05 AUC 统计不显著」，但正文/启示表(§5/§6)和给袁老师推荐仍用「最优/最强/无可替代」确定性词 → **caveat 与 headline 自相矛盾**（组合台栽过的 headline 内部矛盾模式）。
- **更硬反证**：pTuneos「最优」高度依赖聚合：max>0=0.752/mean>0=0.781，但 **>10 阈值掉到 0.58、>median 掉到 0.46(低于随机)**。真正判别力强的工具不会换阈值后掉随机以下。0.78 是 (单聚合×单阈值×11 阴性) 三重最优角落的点，非稳健能力。
- **为什么致命**：直接进袁 PPT、指导她立项动机和工具选型。把噪声当信号往下游传。
- **出路（<10 行代码，不需重跑工具）**：①DeLong/bootstrap CI 算每工具 AUC 95% CI 画 caterpillar 图(预期 CI 大面积重叠) ②paired bootstrap 检验 pTuneos vs PredIG ΔAUC 是否含 0 ③headline 改「现有工具在本 ELISpot 集判别力普遍弱(最优点估 ~0.75 但不稳健、对聚合/阈值敏感)，无统计显著最优工具」。**改写反而强化袁立项动机。**

## 🟠 值得改（削弱可信度但不推翻）

### 🟠-2 IEDB train/test 泄漏：没排重、无法证明没泄漏，但实测结果让它降级
- §8 caveat 4 承认「PRIME/ImmuneApp/deepHLApan 均用 IEDB 训练…实际独立性待查」；全项目 grep **无任何排重/overlap 检测代码**。
- 不是 🔴 的原因：泄漏方向是让分数虚高，而含 IEDB 训练的工具(DeepImmuno 0.48/deepHLApan 0.42/PRIME 0.53)普遍很差甚至低于随机 → 泄漏对「新工具无增量」主结论顺风。
- **但对单工具绝对数字仍污染**：pTuneos 0.78 的 Recognition/Self-similarity 特征间接依赖 IEDB 免疫原性数据，高分可能部分来自 overlap（与 🔴-1 叠加）。
- **出路**：①ELISpot 32178 unique 肽 vs IEDB 全库精确 match + 9mer 子串 match，报 overlap% ②若高，held-out 剔除重算 ③caveat 4 从「待查」升级成「已测 overlap=X%，剔除后 pTuneos 从 0.78→Y」。

### 🟠-3 聚合×阈值多重比较 = 9 格挑最好看的 → cherry-picking
- 每工具 3 聚合×3 阈值=9 个 AUC。§3「各工具最优 AUC(任意聚合)」为每工具挑 9 个里最高 → selection-on-max，期望天然偏高，且不同工具取不同(聚合,阈值)彼此不可比。
- 不是 🔴：主对比表(§2)固定 (max,>0) 是 apples-to-apples；主结论在任意聚合下都成立。
- **出路**：§3 表删或加粗声明「非同口径仅供参考」，绝不进 PPT 当排名依据；主结论锚定预注册单一口径。

### 🟠-4 患者层聚集/非独立样本（6 个攻击点没列但更致命的独立性漏洞）
- BENCHMARK_REPORT 自己写「DS2 Patient_ID 有多个，检查 ELISpot 是否因患者系统偏移」。
- 101 肽来自多患者，但 AUC/Spearman 当独立样本算。若同患者肽 ELISpot 系统偏移 → ①有效样本量<101(伪重复，CI 比算的还宽) ②若某患者贡献大部分阴性肽，AUC 可能在测「区分患者」而非「区分免疫原性」。11 阴性若集中 1~2 患者则极严重。
- **出路**：按 Patient_ID 统计阴性肽分布；算 per-patient 内排序一致性或患者分层 bootstrap；caveat 加「有效自由度<n」。

## 🟢 可接受残差
- 🟢-5 HLAthena/MHLAPre **都没进 8 工具表**(HLAthena 还在救援、MHLAPre 判死) → presentation 混进 immunogenicity 表的污染**实际没发生**。✅ 但 HLAthena 若救援成功进表，必须单独成行标「presentation proxy，非免疫原性」不进主排名。pTuneos r=1.0 只证复刻官方逻辑正确，不证喂纯肽对 ELISpot 有效（两件事，措辞别误导）。
- 🟢-6 攻击点 5「换 DS1 反转」不成立：DS1 **全阳性无阴性**，连判别任务都构不成、算不了 AUC。但这暴露：判别结论只有 DS2 一个集、11 阴性支撑，无外部验证集（数据可得性限制，记录为已知残差）。换指标 AUPRC 已在表里，与 AUC 结论一致无反转。
- 🟢-7 deepHLApan AUC 0.419<0.5 = 反向判别，n_neg=10 下极可能噪声，结论「无有效信号」成立。

## 放行裁决
**致命伤=1（🔴-1）。** 对外强结论措辞先补 bootstrap CI 再交付，benchmark 工程本身可推进。
- **必补**：🔴-1 的 CI/bootstrap（<半天，现成 score 列+2000 次重抽样），补完把「pTuneos 最优」改「判别力统计不可区分、无稳健最优工具」。
- **主结论「新 3 工具无增量」稳健可保留**：不依赖排名精度，所有 9 格没一个超第一批，IEDB 泄漏方向顺风。可现在就对袁老师说。
- **强烈建议补**：🟠-2 IEDB overlap 实测（给个数代替「待查」）、🟠-4 Patient_ID 聚集检查。
- **措辞红线**：🟠-3 §3「各取所长」表不进 PPT；pTuneos r=1.0 ≠ ELISpot 能力背书。

**一句话**：诚实结论的**保守版**(「现有工具判别力普遍弱且统计不可区分、新工具无增量」)完全站得住且更强化袁立项动机；要砍的是**激进版**「pTuneos 0.78 最优」——那 0.78 是 (单聚合×单阈值×11 阴性×可能 IEDB 泄漏) 四重最优角落的脆弱点。补一个 bootstrap CI 图，交付从「被一句'CI 呢'打回」变「诚实且防弹」。
