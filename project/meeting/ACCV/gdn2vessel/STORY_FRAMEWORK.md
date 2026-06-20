# gdn2vessel 故事框架（反跑偏主文档）

**适用范围**：任何 Claude / Sonnet / Opus 会话写 gdn2vessel 内容（tex / 正文 / rebuttal / 实验设计 claim）前必读。
**最后更新**：2026-06-20（立项 + 顶会亮度计划成型）

> 如果用户描述的任务与本文件冲突 → **停下来澄清**，不要按用户描述硬干（用户可能忘了已有约束）。铁律：计划外岔路先问，不盲跑。

---

## ⛔ 跑偏定义（命中任一条立即停手）

1. **把 headline 从「断点续连 + 同根血管 re-ID」漂走**（如改成纯「血管分割涨点」或「换了个 SSM backbone」）。
2. **把 scan / reorder 写成核心贡献**（撞 Serp-Mamba/SWinMamba 蛇形；只能定性「标准工程实现」）。
3. **vesselness 先验用 GT / 分割结果**（必须 input-derived 可微 Frangi，破鸡生蛋 + 防评估泄漏）。
4. **断点续连 benchmark 测试集拼入训练样本 / 记忆 key 用 GT 监督**（in-sample 伪迹，红线）。
5. **凭印象写数字**而非 Bash/Grep 核 csv。
6. **改动 §1-§7 章节弧顺序**（见下方故事弧）。
7. **写绝对化措辞**（"universal" / "always" / "we prove" / "theorem"）或 **related work 不区分 GDKVM**。

---

## 🎯 核心 Claim（论文一切内容服务于此）

### Claim 1（核心 1 = C）：模型内 delta-rule 关联记忆能做单图内空间断点续连

> GDN-2 的矩阵态当血管「身份记忆」：沿降采样深层 patch 序列写入血管 key-value，遇遮挡/低对比断点处用 key 检索回此前 value，把断开的同一条血管在特征空间续上。
> **必须写**：记忆是 **end-to-end 模型内机制**（区别于拓扑损失 clDice / 后处理图算法 / learned post-processing 如 arXiv 2404.10506）。
> **绝对禁止**："universal reconnection" / "always reconnects"。续连能力随断点 severity / 序列长度衰减，必须如实呈现衰减曲线。

### Claim 2（核心 2 = 空间 re-identification）：续连不止「填上」，而是「认出同根」

> 现有续连指标（ε_β0/SR）只量「gap 是否被填充」，不量「填充者是否是同一条血管的延伸」。我们把断点两侧的 re-identification 做成显式机制 + 自定义 **re-ID 率**指标（借 MOT IDF1 逻辑：正确同根匹配 / 全部 gap）。
> **这是与 GDKVM（ICCV2025 时序心超视频版）的硬区分点**：我们是单图内空间 re-ID，无时序维度。
> **监督辖域（2026-06-20 用户拍板 A，分层诚实）**：re-ID 用**合成断点弱监督**——「我用 apply_breaks 亲手切开，故知两侧同根」，与 creatis plug-and-play [2404.10506] 同范式（creatis 自己也不 claim annotation-free）。此弱监督经 **stop-gradient 隔离仅更新匹配头、不回流 memory/encoder**，故 Claim 1 续连能力保持 GT-topology-free。novelty 在**机制（记忆做空间 re-ID）+ benchmark**，不在「无监督」。
> **绝对禁止**：把 re-ID 率算在含训练样本的集上；把 re-ID 弱监督粉饰成「无监督」；让 re-ID 弱监督回流 memory（必须 detach）。

### Claim 3（机制 = B）：解耦 erase/write 门 + 可微 Frangi（input-derived）是 C 的实现机制

> 血管延续处压低 erase 拒绝遗忘、血管证据处拉高 write；门控调制信号来自**可微 Frangi 层的输出（input-derived vesselness）**，绝不用分割结果/GT。
> **必须写**：区别于 Frangi-Net（arXiv 1711.03345，那是「学 Frangi 权重做分割」）——我们是「用 Frangi 输出当外部门信号调制线性注意力记忆」。
> **kernel 外调制（2026-06-20，FLA 单-β 事实）**：FLA 通用 gated-delta-rule kernel 是**单-β**，我们的解耦 erase/write 门是 **kernel 外调制层**（write→β、erase→g 的加性 decay 修正），**不重写 kernel**（R4：贡献是记忆机制非 kernel 工程）。§3.4 写清是「双门近似」不 claim 与 NVlabs gdn2_ops 真双门严格等价。
> **绝对禁止**："we prove uniqueness" / 把门控写成独立 claim（它服务于 C）/ 把 kernel 外调制写成「重写了 kernel 做真双门」。

### CV 方法贡献定位（纯 CV 会议必读）

> ACCV/CVPR/ICCV 是 CV 方法会议：贡献必须落在**新机制/新原理/新 benchmark**（线性注意力关联记忆的空间续连 + re-ID + 断点 benchmark），医学数据集是 **validation 场景**，不是靠临床故事撑录用。

---

## 📐 故事弧（章节顺序锁定）

```
§1 Intro
├── §1.1 问题：细长血管/管状结构在遮挡/低对比处断点，连通性是临床关键
├── §1.2 现有路径局限：拓扑损失(clDice)/后处理图算法/蛇形扫描都不在模型内做"身份记忆"
├── §1.3 ★ Hook：delta-rule 关联记忆做空间断点续连 + 同根 re-identification ★
└── §1.4 贡献列点（C 记忆续连 / re-ID 机制+指标 / 断点 benchmark / 全谱实验）

§2 Related Work
├── 血管/管状分割（CNN 经典 + SSM/Mamba 家族）
├── 拓扑/连通性方法（clDice/cbDice/Skeleton Recall/Betti/DSCNet）
├── 线性注意力/DeltaNet（★ GDKVM 硬区分：时序 vs 空间；GDN-2 vs 早期 GatedDeltaNet ★）
└── 可微 vesselness（Frangi-Net 区分）

§3 Method
├── §3.1 总体架构（CNN U-Net + GDN-2 记忆模块插 encoder 深层 + re-ID 读出头）
├── §3.2 GDN-2 关联记忆做血管身份记忆（C）
├── §3.3 空间 re-identification 机制（核心 2）
├── §3.4 可微 Frangi 解耦门（B，input-derived）
└── §3.5 2D 化：标准 reorder 多向合并（A，定性工程，不当贡献）

§4 Disconnection-Reconnection Benchmark（杀手锏）
├── §4.1 合成断点协议（对齐 creatis plug-and-play，半径分布+gap 参数）
├── §4.2 续连指标 ε_β0 / SR + 自定义 re-ID 率
└── §4.3 防泄漏设计（测试集 held-out，记忆不碰 GT）

§5 Experiments
├── §5.1 Setup（数据集 ≥10 / baseline ≥12 / 三轴指标 / seed≥3）
├── §5.2 主实验（DRIVE/CHASE/FIVES/STARE，三轴表）
├── §5.3 断点续连 benchmark 结果（★ headline 铁证 ★）
├── §5.4 消融（≥8 组，C/re-ID/Frangi/门/序列长度/多向…）
├── §5.5 泛化/跨域/跨器官（冠脉/OCTA/跨域）
└── §5.6 可解释性（记忆认出同根血管可视化）

§6 Discussion + Limitations（续连随 severity/序列衰减；序列≤1K 容量；synthetic 断点 vs 真实病理断点）
§7 Conclusion
```

---

## 🔒 锁定数字表（实验后由 verifier 核 csv 回填，此刻一律 TODO，严禁臆造）

### 主实验三轴（DRIVE/CHASE/FIVES/STARE）

| 数据集 | 方法 | Dice | clDice | Betti β₀/β₁ err | ε_β0 | re-ID 率 |
|---|---|---|---|---|---|---|
| DRIVE | Ours | TODO | TODO | TODO | TODO | TODO |
| ... | ... | TODO | TODO | TODO | TODO | TODO |

### SOTA 天花板（researcher×4 核源 2026-06-20，作为「要赢多少」的参照，非我们的数字。全表来源/陷阱见 [`reference/SOTA_NUMBERS.md`](reference/SOTA_NUMBERS.md)）

| 数据集 | 当前最高 Dice | 方法（来源） | clDice 报告者 |
|---|---|---|---|
| DRIVE | ~0.84 | EFDG-UNet 0.8412 / HM-Mamba 0.8327（Mamba 家族最强同台） / VFGS-Net 0.8323✓ | HREFNet 0.8240 |
| CHASE_DB1 | ~0.85 | EFDG-UNet 0.8469 / HM-Mamba 0.8197✓ | HREFNet 0.8293 |
| STARE | ~0.85 | FSG-Net 0.8510✓（**上修，原 83.21 偏低**）/ MDFI-Net 0.8581(待核split) | FA-Net 0.8763 |
| HRF | ~0.86 | VFGS-Net 0.8560 / FSG-Net 0.8157 | — |
| FIVES | ~0.918 | PASC-Net 0.9183✓ | PASC-Net 0.9174 |

> 基调：**裸 Dice 已饱和**（各集 0.84–0.92），胜负压拓扑(clDice/Betti)/续连(ε_β0/SR/re-ID)轴；裸 Dice 持平不输即可，禁调参作弊凑赢。
> **战略空白**：clDice/拓扑指标报告者极少（仅 HREFNet/PASC-Net/FA-Net/TFFM），主流强作 FSG-Net/HM-Mamba/EFDG-UNet 全不报 clDice，续连/re-ID 轴更无人占——这是我们的取胜窗口。
> ⛔ RV-GAN 86.90/89.57「F1」疑指标混用，**禁引**（原文只报 AUC）。
> ⚠️ creatis 协议两修正（见 reference）：**原文无 boundary blur、无 SR 指标**（只有 ε_β0/DSC/ASSD/AUC）——P1 写作勿误称对齐，SR 来源待澄清。

---

## 🛡️ 防御写法硬规则（违反即跑偏）

| 编号 | 严禁 | 必须 |
|---|---|---|
| R1 | "universal reconnection" / "always" | "reconnection degrades with break severity / sequence length"，附衰减曲线 |
| R2 | "we prove" / "theorem" / "uniqueness" | "we design / motivated by" |
| R3 | related work 不提或不区分 GDKVM | 固定模板："Unlike GDKVM [ICCV25] which uses gated delta KV memory across echo video frames (temporal), we operate within a single image (spatial) and add explicit same-vessel re-identification." |
| R4 | 把 scan/reorder 写成贡献 | "we adopt a standard reorder; the contribution is the associative memory, not the scan" |
| R5（分层辖域，2026-06-20 用户拍板 A 修订） | 把分割主干/记忆/Frangi 门写成用 GT；或把 re-ID 弱监督粉饰成「无监督」 | **分层声明**：①分割主干 + GDN-2 记忆 keys + Frangi 门 = input-derived，**never GT topology**（Claim 1 续连 GT-free）；②re-ID 头同根判别 = **synthetic-break weak supervision**（与 creatis 同范式，creatis 自己也不 claim annotation-free），且经 **stop-gradient 隔离、弱监督仅更新匹配头、不回流 memory/encoder**；③评估用 GT 当裁判 = allowed。**禁**把②写成无监督，**禁**把①写成用 GT。 |
| R6 | bare numbers | 续连/re-ID 数字附统计（bootstrap CI 或显著性），Dice/clDice 附 seed std |
| R7 | 纯临床故事撑录用 | CV 方法贡献先行，医学集是 validation |

---

## 📊 novelty 真实性（2026-06-20 调研双证）

- GDN-2 在视觉/分割**零应用**（NVlabs repo 仅 LM/long-context）。
- 单图内 KV 关联记忆做空间 re-ID 续连 = 检索文献无直接撞车（最近邻 GDKVM 是跨帧时序）。
- 2D 眼底「人工断点 + 记忆续连」专用 benchmark 不存在 → 自造必要、novelty 强。
- 可微 Frangi 当外部解耦门 = 无先例组合（区别 Frangi-Net）。

---

## 🚨 会话开始前 checklist

1. ✅ 读本文件一遍
2. ✅ 读 `PLAN/MASTER_PLAN.md` + 当前 `PHASE_x.md`
3. ✅ 读 `ACCEPTANCE_CRITERIA.md` 查当前任务硬阈值
4. ✅ 读 `PROJECT_LOG.md` 最新 entry
5. ✅ 写数字前先 Bash/Grep 核数据源 csv
