# gdn2vessel 总计划（MASTER_PLAN）

**项目**：GDN-2 门控关联记忆做连通性保持血管分割
**venue**：顶会亮度（CVPR/ICCV/MICCAI）标准建，ACCV 2026 作随时可降投保底
**周期**：不设上限——唯一推进条件 = 每阶段硬阈值全 PASS
**最后更新**：2026-06-20

> 本文件是阶段总览 + 指针中枢。反跑偏细则见 [`../STORY_FRAMEWORK.md`](../STORY_FRAMEWORK.md)，验收阈值见 [`../ACCEPTANCE_CRITERIA.md`](../ACCEPTANCE_CRITERIA.md)。

---

## 一句话 headline（锁定，不可漂）

> 用 GDN-2 的门控关联记忆做连通性保持的血管分割，核心 = **跨遮挡/低对比断点的空间续连（reconnection）+ 同根血管 re-identification**。

---

## 双硬核贡献（锁定）

| 角色 | 内容 | 承重 |
|---|---|---|
| **核心 1 = C** | delta-rule 矩阵态当血管「身份记忆」，遮挡后 key 查回 value 续上 | 独头承重，干净消融 |
| **核心 2 = 空间 re-ID** | 断点两侧「是否同一条血管」做显式 re-identification + 自定义 re-ID 率 | GDKVM 区分点 |
| 机制 = B | 解耦 erase/write 门，可微 Frangi（input-derived）调制 | 服务 C，非独立 claim |
| 工程 = A | 标准 reorder 多向合并，不重写 kernel | 不声张、scan 不当贡献 |

**杀手锏**：自造人工断点 benchmark（合成协议对齐 creatis plug-and-play）+ 续连率/re-ID 率指标。

---

## 阶段总览（P0 → P7）

| 阶段 | 目标一句 | 入口 gate | 出口 gate（硬阈值见 ACCEPTANCE） | 状态 | 分计划 |
|---|---|---|---|---|---|
| **P0** | 环境 + kill-shot（kernel 烟测 + pilot） | 关 0/1 PASS | 关 2 kernel 通 + 关 3 pilot 不输纯 CNN | 🚧 关 0/1 ✅，关 2/3 待 | [PHASE_0](PHASE_0_killshot_env.md) |
| **P1** | 数据 + 断点续连 benchmark（杀手锏） | P0 PASS | 协议可复现 + 零泄漏 + re-ID 指标实现 | ⬜ | [PHASE_1](PHASE_1_data_benchmark.md) |
| **P2** | 核心模型实现 | P1 部分（可并行） | pytest 通 + 不碰 GT + 兜底可跑 | ⬜ | [PHASE_2](PHASE_2_model_impl.md) |
| **P3** | 主实验 + baseline 全谱同台 | P1+P2 PASS | 拓扑/续连 ≥1 轴赢 SOTA + Dice 不输 | ⬜ | [PHASE_3](PHASE_3_main_experiments.md) |
| **P4** | 消融超量（≥8-10 组） | P3 跑通 | C/re-ID 干净可归因证 headline | ⬜ | [PHASE_4](PHASE_4_ablation.md) |
| **P5** | 泛化/跨域/跨器官（全做满） | P3 PASS | ≥10 集 + 跨域不崩 | ⬜ | [PHASE_5](PHASE_5_generalization.md) |
| **P6** | 可解释性 | P3/P4 有结果 | ≥3 张支撑 headline 图 | ⬜ | [PHASE_6](PHASE_6_interpretability.md) |
| **P7** | 写作 + 对抗审稿 + 投稿 | 全部实验收口 | 数字 0 偏离 + 0 致命 + 双盲合规 | ⬜ | [PHASE_7](PHASE_7_writing_submit.md) |

> P2 可与 P1 后段并行（模型实现不依赖 benchmark 全部就位）。P5/P6 可在 P3 出结果后并行铺。

---

## 指针区（进项目按需深读）

- 反跑偏主文 → [`../STORY_FRAMEWORK.md`](../STORY_FRAMEWORK.md)
- 验收硬阈值 → [`../ACCEPTANCE_CRITERIA.md`](../ACCEPTANCE_CRITERIA.md)
- 数据/脚本/baseline 全景 → [`../DATA_INVENTORY.md`](../DATA_INVENTORY.md)
- P3 baseline 全谱准备规格（roster/官方超参/harness 设计） → [`BASELINE_SPEC.md`](BASELINE_SPEC.md)
- 多窗任务 + 各节点完成线 DoD（承 Entry 14 待续，配 Conductor 图） → [`WINDOW_TASKS.md`](WINDOW_TASKS.md)
- 进度日志 → [`../PROJECT_LOG.md`](../PROJECT_LOG.md)
- 批准 plan（GDN-2 选型链） → `~/.claude/plans/d-yj-agent-project-meeting-accv-2024-acc-keen-pony.md`
- 数据集真源 → `.portfolio/datasets.json`
- HPC 工作流 → `project/HPC_WORKFLOW.md`
- 卡调度 → `tools/gpu_slot.py`

---

## 全局红线（贯穿所有阶段）

四红线（项目通用）：①数字 Bash/Grep 核 csv 不信 Read ②超参/架构查官方源查不到标 TODO ③复现零偏离 ④评估集不泄漏。

ACCV 专属：
- 投稿 / HPC 上传新代码新数据 / force push = 拍板点，执行前报。
- 断点续连 benchmark 测试集零拼训练样本；记忆/Frangi 不碰 GT。
- 不重写 kernel；scan 不当贡献；related work 硬区分 GDKVM。
- **铁律：任何计划外岔路先问用户，不盲跑。**

---

## 「自由发挥 ↔ 防跑偏 ↔ 不妥协」三原则

- **🟢 自由区（鼓励发挥）**：模型实现细节、超参搜索（复现纪律内）、额外探索性消融、可视化形式、断点形态设计、re-ID 匹配公式。
- **🔴 锁定区（不可动）**：双核心贡献、章节弧、评估协议、防泄漏设计、headline。
- **⛔ 不妥协闸**：每 phase 出口硬阈值未达 = **不进下阶段** + 写诚实回退 + 停下报。不存在「基本完成」。stage-gate FAIL 放行是拍板点。

---

## 超量原则（顶会亮度，全面碾压同类）

| 维度 | 同类（ACCV/MICCAI 录用线） | 我们 |
|---|---|---|
| 数据集 | 3-5 集 | **≥10 集全做满**（允许 1-2 边缘失败） |
| baseline | 5-10 | **≥12 全谱**（SSM+拓扑+经典+冠脉+2025-2026 最新） |
| 消融 | 2-4 组 | **≥8-10 组** |
| 指标 | 单轴 Dice | **三轴**（重叠+拓扑+续连/re-ID） |
| seed | 1-3 | **≥3** |

---

## 亮度远超录用线论证（逐条对位 ACCEPTANCE lever）

1. 双核心证透（C 独头可归因 + 空间 re-ID 硬机制）→ L1
2. 自造断点续连 benchmark 杀手锏 → L2
3. baseline 全谱 + 数据集 ≥10 → L3/L4
4. 消融 ≥8 → L5
5. 拓扑/续连维度赢 SOTA（Dice 已饱和，换轴取胜）→ L6
6. 可解释「记忆认出同根血管」（王水花方向）→ L7
7. CV 方法贡献明确（新机制/benchmark，非换模块）→ L8
8. 对抗审稿 + 数字三方对账 + 复现/双盲 → L9/L10

---

## 算力调度

- HPC 4 卡动态并行，4 个不同任务各占 1 卡吞吐最大。
- 启训前 `python tools/gpu_slot.py request gdn2vessel hpc 1`，GO 即起、QUEUED 即排队，**绝不挤正在跑的**，完成 release。
- 本地 RTX4070 8GB 仅做 <5min 烟测/调试，正式训练一律 HPC。
- 不赶 deadline——以质量门为唯一推进条件。

---

## 拍板点清单

HPC 上传新代码/数据 · 投稿/对外发布/force push · stage-gate FAIL 放行 · 偏离 STORY/改阈值 · 大额算力 · **任何计划外岔路（铁律先问）**。
