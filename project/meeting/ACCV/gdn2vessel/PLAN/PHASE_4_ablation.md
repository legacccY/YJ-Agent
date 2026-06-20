# PHASE 4 — 消融超量（≥8-10 组）

## ① 目标（锁定）
用干净可归因的消融证「核心 1（C 记忆）+ 核心 2（re-ID）」各自的贡献，尤其证「有 C → 续连率/re-ID 率显著↑」=headline 铁证。消融体量远超同类（2-4 组）。

## ② 入口依赖
P3 跑通（主实验 + benchmark 有结果）。

## ③ 任务清单（消融菜单，≥8-10 组）
1. **C 有/无**（独头干净对照）— 核心，证记忆续连贡献
2. **re-ID 读出头 有/无** — 核心 2 贡献
3. **Frangi 解耦门 有/无**（B 机制）
4. **解耦门 vs 单门**
5. **reorder 多向数扫**（2/4/8 向）
6. **flatten 序列长度扫**（256/512/1K/2K，看检索衰减——对应容量约束）
7. **记忆插入深度扫**
8. **delta-rule vs 等参普通线性 attn（= 命门 A1' 臂，升格进 re-ID 可归因预登记表）**
   —— 证「re-ID 增益来自 delta-rule 关联记忆机制，非加注意力模块的容量」。
   - **A1' 定义（等参非 delta-rule 线性注意力臂）**：保留 GDN2MemoryModule 的
     proj_q/k/v/out 投影、LayerNorm、同一插入深度、同 Frangi 门信号通路与训练预算，
     **唯一改动** = 把有状态的 gated delta-rule 关联更新（FLA gated_delta_rule，
     含 erase/write delta 项 v−Sk 与衰减状态 S_t）替换为**无状态普通线性注意力**
     聚合（softmax-free linear attention，o = φ(q)·Σφ(k)ᵀv 形式，无 S 状态传递、
     无 erase/write 门对记忆的读写）。
   - **等参定义（预登记，阈值写死）**：A1' 与 A2 的**可训练参数总量差 ≤ ±5%**
     （以 `sum(p.numel() for p in module.parameters() if p.requires_grad)` 为准，
     全模型口径）。delta-rule 算子无额外可训练参数，A1' 用同投影集 → 参数量预期 ≈0% 差。
     若替换后 numel 差 >5% → coder 必须报回 planner 重对齐，**禁默许超阈**。
     三臂 numel 实测值写进论文表脚注（留痕）。
   - **归因链目标**：A2 > A1' > A0'。
       - A2 > A1'：证 **stateful associative memory 整体（delta-rule 更新 + 递推状态 S_t）**
         vs **stateless linear attention** 的净贡献。注：S_t 是激活态存储不计入 numel，
         但属机制本身、与 A1' 绑定不可再细分——**不单 claim「delta 更新公式这一行算子」
         的贡献**，claim 的是「有状态关联记忆」这一整体机制。
       - A1' > A0'：证「加注意力模块（容量）」本身的贡献（A0' = 无任何记忆/注意力模块的纯 CNN）。
   - **与命门关系**：本项即 re-ID 可归因预登记表的 A1' 臂，**不另起 run**，与 A0'/A2
     同 seed/split/超参三臂同跑（见 ACCEPTANCE 预登记表），避免与该消融重复跑。
   - **🟠 coder 实现规范（写进交接，不改设计骨架）**：
       - A1' 中 proj_write/proj_erase/proj_g **不得变成死参**——须真接入无状态注意力计算图
         （如门信号作用在 linear-attn 输出/聚合权重上），保持与 A2 同投影集且参与前向。
       - **跑后审计**：训完审计 A1' 这三组投影的梯度 ≠ 0（grad norm 写附录留痕）。
         给不出此审计 = 等参对照不成立（死参≠等参），该缺陷升 🔴。
9. **记忆 state 维度扫**
10. **续连率/re-ID 率 vs 断点 severity 曲线**

## ④ ACCEPTANCE 硬阈值（不妥协）
- [ ] ≥8-10 组消融全跑
- [ ] **C 消融干净可归因**：有 C 续连率/re-ID 率显著↑（附统计），单变量对照不与其他机制纠缠
- [ ] re-ID 头消融干净可归因
- [ ] 序列长度扫出检索衰减曲线（佐证 ≤1K 容量约束）
- [ ] 数字 Bash/Grep 核 csv

## ⑤ 自由发挥区
额外探索性消融（如不同 Frangi scale、不同 reorder 路径对比）、消融在哪几个集上做、是否加交互项消融。

## ⑥ 跑偏定义 / 红线
- ❌ 多机制同时变 = 不可归因（跑偏）
- ❌ 挑对自己有利的子集报消融（cherry-pick）
- ❌ 数字凭印象

## ⑦ 退路 + 派谁 + 出口 gate
- 退路：若 C 消融证不出续连↑ → headline 塌，stage-gate FAIL 报用户（可能回 P2 重设记忆机制）。
- 派谁：`planner` 设计消融矩阵 → `skeptic` 红队（0 致命即过）→ `coder` 实现 → 主线跑 → `analyst` 解读 + `verifier` 核数。一键 `/experiment-cycle`。
- **出口 gate**：≥8 组 + C/re-ID 干净可归因 → 进 P6（可解释）/收口。
