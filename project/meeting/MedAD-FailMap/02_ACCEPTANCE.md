# MedAD-FailMap — ACCEPTANCE CRITERIA

> Capability paper 判据：验「可预测/可外推/可操作」，不验「AUROC 更高」。Gate 不达标按预案走，不临时找理由续命。

## 核心验收（论文成立的硬条件）

> **reviewer 已裁（2026-06-16，立项当天首钉）**：原判据 ②③ 松到自验必过、③ 有循环论证结构性洞。下表已按裁决收紧——**钉的是对照结构 + 外推维度，不只是 ρ/AUROC 数字**。

| Pillar | 指标 | 绿灯（已收紧） |
|---|---|---|
| **① 失败边界存在且系统** | 受控操纵协变量（size/contrast/texture/位置/正常集多样性），重建式 AD 性能随之系统变化 | 至少 2 个协变量轴失败呈系统规律（非噪声）跨 ≥3 数据集复现；**且至少一个轴上是非单调 / 交互效应（如 size×contrast 交互）**——否则相图退化成单变量、② 的 strong baseline 对照站不住 |
| **② 边界可外推** | 数据集 A 拟合的失败边界，零调参 predict held-out | **三条全过才绿**：①**跨数据集**零调参外推，跨集 AUROC ≥ 集内自测的 80% 且绝对 ≥0.70（掉到随机=不可外推）②至少一对**跨模态**外推不塌（如胸片→脑 MRI，分「数据集特异拟合」与「可外推函数」）③显著超过 **strong baseline**（单变量 size 回归 + size+contrast 双变量回归）——超不过 = 相图多维结构是装饰；④外推方向为 **extrapolation**（训中等 size→测未见极小 size），非 i.i.d. interpolation |
| **③ per-image 可靠性判据可操作** | conspicuity 桥派生 per-image score 预测该图 AD 成败 | **防循环论证三件套全过才绿**：①**增量信息检验**——given 模型 anomaly score 后，conspicuity 仍能额外预测成败（嵌套逻辑回归似然比 / 偏相关显著），非单看 ρ ②**控制显然变量残差**——回归掉 size+raw contrast 后 conspicuity 桥在残差上仍有预测力（塌则判据平凡，③ 诚实退守）③**可操作校准**——report risk-coverage / selective AUROC（按 reliability 排序丢 bottom-k% 后 AD 性能单调升）。**不许只报「优于重建误差」**（弱 baseline） |
| **④ 多方法对比有结构** | 不同 AD 方法失败边界在同一 phase space 形状不同 | 至少揭示 2 类方法的失败几何差异（非全部重合） |

> **③ 红线**：在「增量信息检验 + 控制显然变量后残差预测」过关前，**不得落「conspicuity 桥成立」**——否则 = 把已知「大病灶好检」重命名，踩 STORY 红线「别把弱结果当强卖」。
> conspicuity 可计算性（核实）：gCNR/CNR/Weber 需 GT mask 不可用于无标注新图；**per-image 判据用无 mask 代理**——全图 σ / GLCM(Cluster Prominence,Contrast) / FFT 频谱熵 / Otsu 伪前景 CNR_proxy（scikit-image 可算，先例 Mammogram-difficulty GLCM 无 mask AUC=0.75）。

## 决策门（预定义 if-then）

- **Gate 0（可行性预检，Phase 0 末）**：最小 pipeline 搭通 + 协变量分层 sanity（人工合成可控异常或天然分层）能跑出非平凡失败变化 → 进 Phase 1；跑不出系统变化 → 重审协变量选择/数据，不硬推。
- **Gate 1（边界存在，Phase 1 末）**：Pillar ① 绿（≥2 轴系统、跨 ≥3 集复现）→ 进 Gate 2；否则 → 退守「重建式 AD 失败的受控现象学」单薄档（MICCAI/MedIA 退路）。
- **Gate 2（可外推 + 可操作，Phase 2 末）**：Pillar ②③ 绿（held-out 预测成立 + per-image 判据成立）→ GREEN 冲 ICLR/NeurIPS；②或③ 不成立 → 退路 MICCAI/MedIA（受控失败分析仍可发，不白做）。

## 反跑偏（验收侧）

- 不顺手加新方法/新模态/堆指标——只验 4 Pillar。
- 退路 B/C 的产物（受控失败现象学）可复用，不算白做。
- 所有 run 记 seed + 协变量配置 + 数据集 + job ID，可追溯。
- **滑回刷 AUROC = 跑偏**：本文不与 AD 方法竞争分数，只刻画其失败几何。
- **多重比较校正**：扫 size×contrast×texture×位置×正常集多样性 多轴 × 多数据集 × 多方法 → 所有显著性检验**预登记 + Holm/FDR 校正**，防 p 值满天飞被统计角色审稿人打穿。
