# FMReg PROJECT LOG

> 进度留痕。倒序（最新在上）。

---

## Entry 2 — 立项证据归档 + 收工（2026-06-17）

立项材料完整归到本项目文件夹（自包含，不依赖 ideation run-002 目录）：`00_provenance/` 存
- `killshot_s2_03_jacobian.py`（G5 雅可比闸脚本）
- `killshot_s2_03_jacobian.csv`（GREEN 读数原值）
- `G6_proposal_card.md`（立项卡）
- `run-002_funnel.md`（漏斗台账 7→1）

组合台登记已全落：registry.json `fmreg` 条目 / datasets.json OASIS+Learn2Reg+BraTS2021复用 / locks/fmreg.claim。

下一步仍是 Entry 1 的 Gate1 三前置（R1 理论复核 / 下数据+baseline / `/design-experiment fmreg`），未启动。

---

## Entry 1 — 立项决策（2026-06-17）

**决策**：用户拍板立项。来源 = 选题流水线 run-002 医学影像方法创新型 G6 立项卡（唯一存活候选 S2-03，G5 雅可比闸 GREEN）。

**核心 RQ**：flow-matching（OT-Flow）直线流形变场做可变形医学配准，少步（≤4）逼近 diffusion 配准精度 + 保拓扑合法。

**venue**：MICCAI 2027 / CVPR 2027（top），MedIA / TMLR（fallback）。注：立项时纠偏——MICCAI 2026/CVPR 2026 截稿已过。

**边界**：组合台唯一碰「配准 + flow matching」的项目，与 iclr/medad-failmap/nca-jepa/bmvc 零重叠。

**立项证据**：`ideation/runs/2026-06-17_run-002_medimg-method/06_experiments/results/killshot_s2_03_jacobian.csv` → `neg_jac_pct=0.0000`, `dice_fm=0.9279 > dice_affine=0.8384`（OASIS 20 对 2D 单步 Euler，verifier 核 csv 自洽 0 drift）。

**G5 漏斗背景**：7 候选 → 杀手锏 6 证伪/blocked → 1 存活（S2-03）。死亡：S5-10(泄漏)/S6-18(撞车)/S2-17(输方差基线)/S2-12(masking无增益)/S1-08(无过适应峰)。S4-05 BLOCKED(VinDr 缺逐医生 bbox，用户已并行申标注作潜在第二项目)。

**已知风险（带债推进，见 02_ACCEPTANCE §C）**：
- R1 FM-proxy：killshot 用简化 FM target，velocity→diffeomorphism 理论待证。
- R2 单苗：无第二苗对冲。

**下一步（Gate1 前置）**：
1. 🔜 派 researcher + skeptic 复核 R1（FM velocity→diffeomorphism 几何配准理论，LDDMM/测地线先例），定 headline 是「保证」还是「经验」diffeomorphism。
2. 🔜 下载 OASIS + Learn2Reg，登 datasets.json，跑通 VoxelMorph/TransMorph/DiffuseMorph baseline 对照线。
3. 🔜 `/design-experiment fmreg` 出完整中训实验矩阵（对齐 L1-L4 + K1/K2 闸）。

**留痕清洁 TODO（继承自 run-002）**：run-002 pool.jsonl 的 S2-03 行有 ID 撞车污染（raw 双文件 hyphen/underscore 同 id），不影响本项目（survivor 身份 = FM 配准无歧义），下轮 /ideate 修。
