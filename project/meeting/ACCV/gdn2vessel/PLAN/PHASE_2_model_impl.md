# PHASE 2 — 核心模型实现

## ① 目标（锁定）
实现 CNN U-Net 主干 + GDN-2 关联记忆模块（插 encoder 降采样深层）+ 空间 re-ID 读出头 + 可微 Frangi 解耦门 + 标准 reorder 多向合并，且可退化纯 CNN 兜底。

## ② 入口依赖
P0 PASS（kernel/记忆模块可跑）。可与 P1 后段并行。

## ③ 任务清单
1. **主干**：CNN U-Net（nnU-Net 级公平 baseline 同框架）。
2. **核心 1（C）**：GDN-2 门控关联记忆模块插 encoder 深层，flatten 序列 ≤~1K；记忆 key-value 写入/检索。
3. **核心 2（re-ID）**：空间 re-identification 读出头，输出断点两侧同根匹配。
4. **机制（B）**：可微 Frangi 层（input-derived）→ 解耦 erase/write 门调制（延续处压 erase、证据处拉 write）。
5. **工程（A）**：因果→2D 标准 reorder 多向输出合并（合并 o 不合并态 S）；走标准 GDN-2 kernel。
6. **兜底**：可退化纯 CNN（GDN-2 失效仍可投）。
7. **pytest**：各模块单测（shape/梯度/不读 GT 断言）。

## ④ ACCEPTANCE 硬阈值（不妥协）
- [ ] pytest 全通（记忆/re-ID 头/Frangi 门/多向合并）
- [ ] grep 确认 Frangi 与记忆 key **不读 GT/分割结果**
- [ ] flatten 序列 ≤~1K
- [ ] 纯 CNN 兜底可跑（degrade path 测试）
- [ ] **红线**：不重写 kernel；scan 不写成贡献

## ⑤ 自由发挥区
插入深度（哪几层 encoder）、多向数量（2/4/8 向）、门控耦合方式、re-ID 头结构、记忆 state 维度、Frangi scale 参数。

## ⑥ 跑偏定义 / 红线
- ❌ 重写 GDN-2 kernel（工作量爆炸 + 撞 TopoMamba 风险）
- ❌ vesselness 用 GT/分割结果（红线）
- ❌ 把 reorder/scan 设计当核心贡献（撞 Serp-Mamba）
- ❌ 私加官方没有的裁剪/技巧凑收敛（复现零偏离）

## ⑦ 退路 + 派谁 + 出口 gate
- 退路：记忆模块若拖累 → 纯 CNN 兜底仍可投（但 headline 弱化，需报用户）。
- 派谁：**默认派 `coder`**（写实验码省主线 context）；主线只跑训练。
- **出口 gate**：pytest 通 + 不碰 GT + 兜底可跑 → 进 P3。
