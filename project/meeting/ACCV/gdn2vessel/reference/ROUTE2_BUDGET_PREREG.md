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

**测量**：合成 associative-recall，exact-match accuracy。**四臂因子设计（2026-06-21 skeptic 红队升级写死，stateful×delta 2×2）**：

| 臂 | stateful | delta 纠错 | 角色 |
|---|---|---|---|
| `gdn2` (A2) | Y | Y | 主角：delta-rule 关联记忆 |
| `gla` | Y | **N** | **机制特异性对照**：scalar-gate 有状态、**无 delta 纠错**（=A2 去掉 `v−Sk` 纠错项，1head×64 容量严格对齐）|
| `linear_attn` (A1', `mqar_pure`) | N | N | 无状态等参（**MQAR 去 iso-param 输出旁路**，唯一变量=delta on/off）|
| `gdn2_fla` | Y | Y+short_conv | 仅作 canonical 收敛**参照**，**不进定量 gap 比较**（2head×32 容量+short conv 不对等）|

> 升级根因（skeptic 2026-06-21）：旧三臂全是「delta 或其无状态退化」，A2>A1' 只证「有状态>无状态」，**证不到「delta 纠错 > 普通有状态记忆」=headline 要的机制特异性**。加 `gla` 臂 + 双 gap 判据堵死「换任意有状态记忆+loss 也行」的审稿质疑。A1' 旧版为 iso-param 加了 A2 没有的输出旁路（`out*gate_map`/`g_gate`），污染归因 → `mqar_pure=True` 净化。

**自变量**：n_kv ∈ {4,8,16,32,64,96}（主扫，固定 T=256，d_head=64）；可选扩 d_head∈{32,128}。lr ∈ {1e-3,5e-4,3e-4,1e-4}（加 3e-4 覆盖 VLA 标准，取 lr 内最大 acc）。seed ≥2（报 mean±std）。词表 V=8192，random baseline = 1/(V/2)。
**连续噪声 key 变体**：d_head 维球面采样 key + 高斯噪 σ∈{0,0.1,0.3}，value 离散；外推容差 = 比离散判决线宽 10-20%（即 Δ 放宽到 0.12）。

**判据（写死，禁跑完调；2026-06-21 升级为双 gap 机制特异性判据）**：
- **路 2 活**（delta 机制特异，**两道 gap 都须过**）：∃ n ∈ {16,32,64} 使
  - (a) acc_GDN2(n) − acc_LA(n) > **Δ = 0.15**（delta > 无状态），且
  - (a') acc_GDN2(n) − acc_GLA(n) > **Δ = 0.15**（delta > 普通有状态，**机制特异性必需，新增**），且
  - (b) acc_GDN2(n) > 0.5，且
  - (c) acc_LA(n) < 0.5（无状态已崩窗口才有意义），且
  - 3 seed **std < 0.05**（三臂均）。
- **路 2 死**（无机制特异窗口）：∀ n 上述任一不满足；**尤其 acc_GDN2 ≈ acc_GLA（gap (a') 不过）→ delta 非特异、只是「有状态」效应，headline「delta 关联记忆」塌**，回退路 1 / benchmark-led。
- **收敛 sanity**（前置 gate）：n=4 时 gdn2 / gla / linear_attn **三臂**都须 acc > 0.9（有状态两臂 gdn2/gla 在 n≪d 必平凡解出），否则训练未收敛 → 排除该 config 重跑（lr 加密），不得当作 null。**跑全扫前先单 config 烟测 A1' n=4 能否上 0.9**（防大词表+长噪声污染 ELU 归一化 denom 致 stateless 臂系统性 sanity fail）。

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
