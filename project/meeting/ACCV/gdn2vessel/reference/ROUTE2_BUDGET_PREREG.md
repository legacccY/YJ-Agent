# 路 2 模型无关两层预算 — 预登记（跑前写死，反 HARKing）

**写定日期**：2026-06-21（任何脚本真跑前）
**背景**：Stage-1 三次坐实 CHASE 连通分量 n=1-4 << d_head=64 → A2≈A1' 真 null。路 2 = 换密集集/细粒度让单图 distinct 身份数 n 逼近 d=64 甜区。用户拍：必先模型无关预算，别盲跑。本文件冻结决策阈值，verdict 须引本文件比对，**禁跑完上下调**。

---

## d 锚点

GDN-2 per-head 状态矩阵 d_head × d_head，**d_head = 64**（`unet_gdn2.py:643` 默认）。per-head 关联容量界 = d_head = 64（Schlag 2021 正交界）。

---

## Layer 1 — 数据集身份预算（阈值）

**测量**：每图 distinct 身份数，三粒度：
- 连通分量（`scipy.ndimage.label` on GT mask）— 锚点，须复现 CHASE n=1-4。
- 分支段（skeletonize → 删 junction[骨架邻居>2] → 剩余连通分量计数）— 路 2 主粒度。
- bifurcation 点（骨架邻居>2 点数）— 附报。

**目标带（写死）**：某 (数据集, 粒度, license-clean) 组合 PASS ⟺
- 每图 distinct 身份数 **median n ∈ [32, 96]** 且
- **≥30% 的图 n ≥ 48**。

理由：stateless ELU 在 n>d≈64 才崩、GDN-2 微光未证 → n 须真逼近/触及 d 才可能给 delta-rule 留余地。n<32 区间已被 Stage-1 证 null（两臂都好不分胜负）；n>>96 两臂都崩（VLA 实证）。

**候选集**：ROSE-1 SVC/DVC、OCTA-500 3M 子集、OCTA-500 6M（对照超上界）、XCAD/DCA1/CHUAC（对照下界）、CHASE/DRIVE（锚点）。采样 ≥10 图/集。

---

## Layer 2 — GDN-2 MQAR 容量探针（阈值，判决性）

**测量**：合成 associative-recall，真 `GDN2MemoryModule`(use_frangi=False, d_head=64) vs `LinearAttnModule`(stateless ELU+1)，exact-match accuracy。

**自变量**：n_kv ∈ {4,8,16,32,64,96}（主扫，固定 T=256，d_head=64）；可选扩 d_head∈{32,128}。lr ∈ {1e-3,5e-4,1e-4}（取 lr 内最大 acc）。seed ≥2（报 mean±std）。词表 V=8192，random baseline = 1/(V/2)。
**连续噪声 key 变体**：d_head 维球面采样 key + 高斯噪 σ∈{0,0.1,0.3}，value 离散；外推容差 = 比离散判决线宽 10-20%（即 Δ 放宽到 0.12）。

**判据（写死，禁跑完调）**：
- **路 2 活**（GDN-2 有优势窗口）：∃ n ∈ {16,32,64} 使
  - (a) acc_GDN2(n) − acc_LA(n) > **Δ = 0.15**，且
  - (b) acc_GDN2(n) > 0.5，且
  - (c) acc_LA(n) < 0.5（LA 已崩窗口才有意义），且
  - 3 seed **std < 0.05**。
- **路 2 死**（无窗口）：∀ n∈{4..96} |acc_GDN2−acc_LA| < Δ，**或** GDN-2 在 n≤64 从未超 acc_LA + Δ。
- **收敛 sanity**（前置 gate）：n=4 时两模型都须 acc > 0.9，否则训练未收敛 → 排除该 config 重跑（lr 加密），不得当作 null。

---

## 决策闸（两层合议）

| Layer 1 | Layer 2 | 结论 |
|---|---|---|
| PASS | PASS | 路 2 活 → 进血管 benchmark（重写 STORY + 建分支段标注 + A-v2 框重跑） |
| PASS | FAIL | 路 2 死（机制无窗口）→ 拍板停，回退路 1 / benchmark-led |
| FAIL | 任意 | 路 2 死（无集给得出甜区 n）→ 同上 |

**Layer 2 是主判决**：它 FAIL 则 Layer 1 结果无意义。

---

## 纪律

- 统计手算，禁 scipy.stats（OMP 红线）。
- 数字 Bash/Grep 核 csv/json，不信 Read。
- verdict 引本 PREREG 逐条比对；不利数字（GDN-2 无窗口）如实写，禁改判定方向。
- 机制先验弱（VLA: scalar-gate 在 n<d 就崩；GDN-2 解耦门仍 rank-1 per-step 理论无窗口；视觉无人当真瓶颈 + 自身 Stage-1 已 null）→ 大概率 FAIL，但 <1.5 GPU·h 便宜判决远胜盲跑。

---

## 架构修正记录（有效性修复，非阈值调整）

**2026-06-21：单层→2层VLA原版无conv**

- **根因**：第一版探针单层+无FFN。Based(2402.18668)/VLA(2605.11196)/Zoology(2312.04927) 均证明单层线性注意力/SSM 无法解 interleaved MQAR（key、value 是相邻 token，在 value 位拿不到 query 的 key 绑定）。HPC 真跑结果 n=4/8/16 两臂全 acc≈0.0，收敛 sanity n=4>0.9 未过 → 结果无效。
- **修法（照搬 VLA §5.1/§6.4 原版）**：2层backbone，每层=[mixer+FFN] pre-norm residual；FFN=Linear(d→4d)+GELU+Linear(4d→d)；**无short conv**（VLA故意不加，保持stateless臂对比干净）；steps 1500→2000；lr sweep{1e-3,5e-4,1e-4}不变。
- **判据阈值一字不动**：Δ=0.15/收敛sanity n=4>0.9/活死定义全部保留，属于有效性修复不是结果后调。
