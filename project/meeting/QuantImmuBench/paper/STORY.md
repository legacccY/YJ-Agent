<!-- TODO[HLA-FIX 2026-06-27]: PredIG 全局显著性已失效(max-pool rho 0.198->0.104 p=0.343 ns; mean-agg 0.280->0.188 p=0.084 ns)，剔污染患者 P101/P102 后不存活；IMPROVE 仍稳健显著(0.226 p=0.037)，TSCAPE 翻为显著负(-0.230 p=0.033)，deepHLApan 另有 merge bug 双重不可信；per-patient 头条数字(PRIME/deepHLApan)待 Phase B 正确等位重推理后更新。STORY 锁定数字/headline 暂不动(投稿=拍板点 + P102 等位待袁老师确认)，待 Phase B 后据 corrected-excl 复核。详见 04_LOG Entry HLA-FIX。 -->

# QuantImmuBench — 投稿论文 STORY / Headline 框架（锁定 2026-06-26）

> 本文是 paper_sprint 的锚定文件。所有章节、claim、措辞以此为准；偏离须停下澄清。
> 数字红线：一律 Bash/Grep 核 csv（真源 `analysis/metrics_ds2_8tools.csv` + `analysis/per_patient_spearman_9tools.csv`），入 tex 前过 verifier。DTU 工具数字标 `pending DTU consent`。双盲：0 个人/机构/导师名。

---

## 1. Venue（拍板已定 2026-06-26）

- **主投**：Briefings in Bioinformatics（生信顶刊，常发工具横评 / benchmark / comparison；看重公平横评 + gap 发现，不要求 radical novelty）。
- **Fallback（双 venue 策略）**：NeurIPS Datasets & Benchmarks track（若要冲 ML 顶会）或 ML4H / MLCB workshop（快门槛低，先拿反馈）。
- **形态（拍板已定）**：**benchmark backbone × position framing 融合** —— 主体是工具横评 benchmark（承重靠实测，稳），intro/discussion 用 position 叙事拔高 magnitude gap（拔高靠论证，不靠大规模实验）。
  - ⚠️ 防「两头不到岸」：benchmark 是 contribution 主轴（可复现协议 + 实测表 + per-patient 发现），position 是 framing（为什么这个 benchmark 重要）。不喧宾夺主。

---

## 2. 承重 Claim（三条，按强度排序）

> claim 形状原则（[[feedback_claim_shape_decides_birth_difficulty]]）：窄 + 可观测 + 增量。承重点尽量少，已验证的实测在前，论证性的 framing 在后。

### C1（最稳，全实测支撑）— 现有工具做不了 magnitude 定量回归
在统一 ELISpot 真值 + apples-to-apples 协议下，8 个免疫原性工具 + 1 个 presentation proxy 对 T 细胞反应**强弱程度（ELISpot SFC 连续值）**的 Spearman 相关**普遍弱/不显著**：
- 全工具 |ρ| < 0.33；仅 IMPROVE(top3mean ρ=0.3202, p=0.0011) / PredIG(mean ρ=0.2797, p=0.0046) 在某些口径显著，其余全不显著。
- 阴/阳判别 AUC 点估最高 pTuneos 0.7525（max,>0），但 bootstrap CI 大面积重叠、对聚合/阈值敏感（换 >median 掉到 ~0.46），**统计不可区分**，无「最优工具」。
- HLAthena（presentation proxy）AUC≈0.51 近随机 → 印证 presentation ≠ immunogenicity ≠ magnitude。
- **支撑文件**：`analysis/metrics_ds2_8tools.csv`（核过，BENCHMARK_8TOOLS.md 忠实）+ `bootstrap_ci_ds2.csv` + `bootstrap_paired_ds2.csv`。

### C2（中强，实测 + 方法学发现）— per-patient 揭示被全局指标掩盖的个体差异
核心指标从「全局 Spearman」改为「per-patient 单独算 ρ_i 再聚合（Fisher-z 加权 / median）」后，**排名大变 + 个体差异浮现**：
- **头号干净例 PRIME**：全局 0.116（弱）→ per-patient Fisher-z 0.253 / median 0.386（Δmed +0.270）；best-binder 分数与肽长基本无关（ρ_count≈0.13）→ **真 within-patient 重排,非长度假象**。
- IMPROVE/PredIG 两口径都稳居前二（鲁棒，ρ_count≈0.12 干净）。
- ⚠️ **deepHLApan 是混杂警示例不作能力证据**：数值跳升最大（全局 0.042→median 0.402）但 best-binder 下分数与肽长 ρ≈0.57（H 窗 `POOLING_STUDY.md`），去混杂（mean/geomean）后免疫原性相关塌到 ≈0 → per-patient 跳升大半是肽长不是排序能力。各患者 ρ_i 跨 −0.43~+0.81/std 0.46 仅作离散度描述。
- **方法学贡献**：全局聚合（pool 所有患者）会掩盖个体内排序能力 → benchmark 评估应 per-patient 算后聚合（对齐 TESLA/Müller cohort-level 范式）。
- ⚠️ caveat：多工具 rho_std 0.4–0.46 + n_i 小 → 聚合 CI 宽，主结论以 Fisher-z 加权 + median 为准，余作敏感性。
- **支撑文件**：`analysis/per_patient_spearman_9tools.csv`（核过）。

### C3（position framing，论证性）— magnitude 是被系统性忽视的 gap
- 普查 2024–2026 的 12+ 新方法 + 6 篇综述：**没有任何一个工具对 response magnitude 做连续回归并报 Pearson/Spearman/MAE**，全是二分类或 binding 强度。
- 最强反向佐证：PredIG 训练数据含 positive-low/intermediate/high 分级标签却主动 binarize；CNNeoPP ELISpot 数据能分 weak/strong 却仍只吐二分类；ICERFIRE 明文「标签塌缩为单一类」→ **数据里有 magnitude 信号被选择性丢弃**。
- ⚠️ 必须对冲（reviewer 🟠1）：「没人做」既可能是机会也可能是「没人做得动」（纯序列信号弱、ROI 低）。叙事主动承认生物学上界（precursor frequency 封顶 ρ_max≈0.4–0.6，见 `THEORY_quant.md`）→ claim 收窄为「连续排序对临床 top-K 选择的增量」，不押回归精度。
- **未来工作锚**：QuantImmune（F 窗 pilot）= 填这个 L4 gap 的尝试，本文是其立项 benchmark 背书。

---

## 3. 章节结构（Briefings in Bioinformatics，融合形态）

| 节 | 内容 | 承重 | 主写 |
|---|---|---|---|
| Abstract | gap + benchmark + per-patient 发现 + 蓝海结论 | C1+C2+C3 | writer |
| 1. Introduction | position 叙事：能力阶梯 L1→L4 + magnitude gap + 本文贡献（benchmark + per-patient 协议 + gap 量化） | C3 framing | writer |
| 2. Background / Related Work | 能力阶梯 taxonomy（L1 binding→L2 presentation→L3 二分类→L4 magnitude 空白）+ 连续近邻防御（binding/stability/TCR-pMHC）+ 标签塌缩证据 | C3 | writer（料齐 RELATED_WORK_draft.md）|
| 3. Benchmark Setup | 数据集（DS1/DS2 ELISpot）+ 工具清单（9 跑通 + 扩张标 pending）+ 七步 harmonization 协议 + 指标（AUC/AUPRC/Spearman/per-patient 聚合）+ 公平性五依据 + 泄漏声明 | 方法学 | writer |
| 4. Results | 4.1 全局横评表（C1）4.2 聚合/阈值敏感性 + bootstrap CI（无最优工具）4.3 per-patient 多方法（C2 头条）4.4 proxy 对照（HLAthena 近随机）| C1+C2 | writer + verifier |
| 5. Discussion | 理论天花板（ρ_max 上界）+ magnitude gap 解读 + 局限（n 小、DS2 阴性 11、IEDB overlap）+ 未来 QuantImmune | C3 | writer |
| 6. Conclusion | 三条 claim 收束 | — | writer |

---

## 4. 红线 / 禁区（写作全程守）

1. **数字**：只用 `analysis/*.csv` 已核值，入 tex 前过 verifier。BENCHMARK_8TOOLS.md 已核对 csv 忠实，可作中转但 verifier 仍直核 csv。
2. **DTU 工具**（netMHCpan-4.1/4.0/2.8、netMHCstabpan、NetTepi、netmhcpan_ba 等扩张波）：数字一律标 `pending DTU consent`，投稿前需 DTU 书面同意（PROVENANCE.md 红线）。当前主表 8 工具**不含** DTU 工具，主结论不依赖它们。
3. **双盲**：0 个人名 / 机构名 / 导师名 / HPC 主机名。
4. **引用修正**（researcher 2026-06-26 核）：explorationpub = **2023**（非 2024）；NetTepi = **Trolle & Nielsen, Immunogenetics 2014**（非 Andreatta/NAR）；explorationpub 三句逐字引**未证实→转述去引号**；CD8 magnitude 独立 TMB 无 canonical 出处→降档「T 细胞 breadth 关联复发延迟」+ 引 Sahin BNT122 Nature 2023。
5. **不夸大**：「点估居前」不用「最优/最强」；承认上界；position claim 主动对冲对立假设。
6. **投稿 = 拍板点**：做到 submission-ready 草稿即停，呈用户拍板，绝不擅自投稿/对外发布。
7. **NeoPepDB 不存在=NEPdb 笔误；neoIM 专有不可纳入；「Nature Cancer 2025 reproducibility crisis」疑幻觉勿引**（RELATED_WORK_draft.md §6）。

---

## 5. 关键数字速查（已核 csv，2026-06-26）

主表（agg=max, threshold>0，DS2 n=101）：
| 工具 | AUC | AUPRC | Spearman ρ | p |
|---|---|---|---|---|
| pTuneos | 0.7525 | 0.9494 | 0.1363 | 0.1741 |
| PredIG | 0.6611 | 0.9411 | 0.1983 | 0.0468* |
| NeoTImmuML★ | 0.6551 | 0.9421 | 0.0218 | 0.8285 |
| IMPROVE | 0.6207 | 0.9221 | 0.2434 | 0.0142* |
| ImmuneApp | 0.5889 | 0.9080 | 0.0885 | 0.3786 |
| PRIME | 0.5276(n=100) | 0.9146 | 0.1163 | 0.2491 |
| DeepImmuno | 0.4813 | 0.8951 | −0.1168 | 0.2449 |
| deepHLApan | 0.4188(n=98) | 0.9038 | 0.0415 | 0.6847 |

最优口径 Spearman（任意聚合）：IMPROVE top3mean ρ=0.3202(p=0.0011)；PredIG mean ρ=0.2797(p=0.0046)。
★ NeoTImmuML = 自训版（官方权重不可得），标非官方。pTuneos=Pre&RecNeo 子模型；IMPROVE=Expression 特征降级。
