# MedAD-FailMap — ACCEPTANCE CRITERIA

> Capability paper 判据：验「可预测/可外推/可操作」，不验「AUROC 更高」。Gate 不达标按预案走，不临时找理由续命。

## 核心验收（论文成立的硬条件）

> **reviewer 已裁（2026-06-16，立项当天首钉）**：原判据 ②③ 松到自验必过、③ 有循环论证结构性洞。下表已按裁决收紧——**钉的是对照结构 + 外推维度，不只是 ρ/AUROC 数字**。
>
> **⚠️ 编号调和（2026-06-17 headline A 重铸）**：本表 Pillar 编号 = **验收维度**（①边界存在 ②外推有效性 ③per-image ④多方法），与 `01_STORY.md §三` 的**承重排序**（①conspicuity桥per-image ②外推有效性判据 ③相图=地基）不同号，勿混。承重共识：**真承重 = 本表 ③(per-image 桥) + ②(外推有效性判据)**；本表 ①(相图) 是地基非 headline；本表 ④(多方法) 退为 Phase 1+ 补充章、当前零实证、不进 headline。Gate 逻辑按本表编号判定。

> **headline A 铁律（防 🔴-1 复发）**：「可外推」永远带「regime 同构 + 可前验」限定，**绝不验「任意跨模态不塌」**——该条已被 G1-a（BraTS→HAM 1.3% 重叠）自家证伪。跨模态不同构对**塌**是 ② 负臂判据**正确预言**，记 PASS 证据不记 FAIL。

| Pillar | 指标 | 绿灯（已收紧） |
|---|---|---|
| **① 失败边界存在且系统** | 受控操纵协变量（size/contrast/texture/位置/正常集多样性），重建式 AD 性能随之系统变化 | 至少 2 个协变量轴失败呈系统规律（非噪声）跨 ≥3 数据集复现；**且至少一个轴上是非单调 / 交互效应（如 size×contrast 交互）**——否则相图退化成单变量、② 的 strong baseline 对照站不住 |
| **② 外推有效性判据可操作**（2026-06-17 headline A 重铸 + reframe A' 二次收窄：跨模态正臂实证枯竭 → 正臂改同模态示范 + 跨模态落负臂，skeptic 铁律3'） | 数据集 A 拟合的失败边界，零调参 predict held-out；**且「能否外推」可在跑前从无标注数据前验** | **双臂判据全过才绿**（不再要求「跨模态不塌」=已被 G1-a 自证伪、且 HAM/CBIS/IDRiD 跨模态正例几何枯竭）：**(正臂，同模态示范)** 至少一对**几何 regime 同构的同模态对**（BraTS→METS，脑 MRI 内，面积比分布实质重叠 iso=True）零调参外推**不塌**，跨集 AUROC CI 下界 ≥0.70 且 ≥集内×0.80 且 Holm 显著超 strong baseline（size + size×contrast 回归）。**🔴 铁律3'：headline/正文禁 claim 任何跨模态正向外推**（手上零跨模态 iso=True 正例，暗示跨模态 work=移动球门）；**(负臂，跨模态实证)** ≥2 个**几何 regime 不同构的跨模态对**（HAM 太大/CBIS 太小[/IDRiD]，verifier 坐实面积比不重叠），**前验判据预言其不可外推 → 实测确实塌/拒绝外推**——前验门预言与实测方向一致 = 判据成立证据，**非绿灯失败**；**(终验)** Gate2 **held-out 盲测对**（判据参数没碰过，先预言后跑、看命中）= ICLR 命门（防「同模态 work」被打 trivial）；**(extrapolation)** 外推方向为 extrapolation（训中等→测未见极小，≥20 detected）非 interpolation |
| **③ per-image 可靠性判据可操作** | conspicuity 桥派生 per-image score 预测该图 AD 成败 | **防循环论证三件套全过才绿**：①**增量信息检验**——given 模型 anomaly score 后，conspicuity 仍能额外预测成败（嵌套逻辑回归似然比 / 偏相关显著），非单看 ρ ②**控制显然变量残差**——回归掉 size+raw contrast 后 conspicuity 桥在残差上仍有预测力（塌则判据平凡，③ 诚实退守）③**可操作校准**——report risk-coverage / selective AUROC（按 reliability 排序丢 bottom-k% 后 AD 性能单调升）。**不许只报「优于重建误差」**（弱 baseline） |
| **④ 多方法对比有结构** | 不同 AD 方法失败边界在同一 phase space 形状不同 | 至少揭示 2 类方法的失败几何差异（非全部重合） |

> **③ 红线**：在「增量信息检验 + 控制显然变量后残差预测」过关前，**不得落「conspicuity 桥成立」**——否则 = 把已知「大病灶好检」重命名，踩 STORY 红线「别把弱结果当强卖」。
> conspicuity 可计算性（核实）：gCNR/CNR/Weber 需 GT mask 不可用于无标注新图；**per-image 判据用无 mask 代理**——全图 σ / GLCM(Cluster Prominence,Contrast) / FFT 频谱熵 / Otsu 伪前景 CNR_proxy（scikit-image 可算，先例 Mammogram-difficulty GLCM 无 mask AUC=0.71，Siviengphanom 2023 CC+MLO，95%CI 0.64–0.78；订正：原写 0.75 为误）。

## 决策门（预定义 if-then）

- **Gate 0（可行性预检，Phase 0 末）**：最小 pipeline 搭通 + 协变量分层 sanity（人工合成可控异常或天然分层）能跑出非平凡失败变化 → 进 Phase 1；跑不出系统变化 → 重审协变量选择/数据，不硬推。
- **Gate 1（边界存在，Phase 1 末）**：Pillar ① 绿（≥2 轴系统、跨 ≥3 集复现）→ 进 Gate 2；否则 → 退守「重建式 AD 失败的受控现象学」单薄档（MICCAI/MedIA 退路）。
- **Gate 2（外推有效性 + 可操作，Phase 2 末）**：Pillar ②③ 绿（**② 双臂判据成立**：正臂同构对零调参外推不塌 + 负臂前验门正确预言不同构对不可外推；**③ per-image 判据三件套成立**）→ GREEN 冲 ICLR/NeurIPS；②或③ 不成立 → 退路 MICCAI/MedIA（受控失败分析仍可发，不白做）。**② 红线**：正臂至少需一个同构对（含 ≥1 跨模态）零调参 PASS——光有负臂（全不同构）= 判据无正例锚、外推主轴空，退 MICCAI。**② held-out 硬条件（skeptic 红队2-🟡-3 提级，防「2 点定线=判据被图示非被验证」）**：Gate2 须含 **≥1 对「判据参数（含 area-ratio 阈值）从未碰过」的 held-out 盲测对**——先用冻结判据预言它落哪臂，再跑、看预言命中。Gate1 的正/负臂对都属「判据形成期」（HAM 是激发判据的对、正臂 PASS 对参与定线），**不算判据的独立检验**；STORY §七「judging 判据准不准」的回应须等此 held-out 命中才算兑现，Gate1 PASS 不得视为已兑现。

## 反跑偏（验收侧）

- 不顺手加新方法/新模态/堆指标——只验 4 Pillar。
- 退路 B/C 的产物（受控失败现象学）可复用，不算白做。
- 所有 run 记 seed + 协变量配置 + 数据集 + job ID，可追溯。
- **滑回刷 AUROC = 跑偏**：本文不与 AD 方法竞争分数，只刻画其失败几何。
- **多重比较校正**：扫 size×contrast×texture×位置×正常集多样性 多轴 × 多数据集 × 多方法 → 所有显著性检验**预登记 + Holm/FDR 校正**，防 p 值满天飞被统计角色审稿人打穿。
