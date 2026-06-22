# gdn2vessel 理论地基（★ 主理论文档）

**最后更新**：2026-06-21
**定位**：headline 一切理论结论的**单一权威入口**。三份子文档（[`MQAR_MATH_WIRING_AUDIT.md`](MQAR_MATH_WIRING_AUDIT.md) / [`NOVELTY_DERIVATION_AUDIT.md`](NOVELTY_DERIVATION_AUDIT.md) / 解法 plan `~/.claude/plans/nifty-wishing-rainbow.md`）是细节支撑，本文是整合后的主结论。写 §1/§3 tex、定 headline、red-team 前**先读本文**。
**方法纪律**：以下全部为**纯数学推导 + 多源核源**得出（3 轮 skeptic/researcher 对抗，未跑实验时已成立）。可行性数字仍须 MQAR 实验（见 §5）。

---

## 0. 一句话总纲

> **借来的 GDN-2 引擎接线数学上正确（0 致命）；但我们三件原创里 headline 承重的「记忆做 re-ID」被推出结构性致命——整套目标函数里没有任何 loss 在优化「同根血管在 memory 状态空间可分」，所以 A2≈A1' 是数学必然，不是 bug。headline 的死活押在一个尚未跑出的实验上：delta-rule 机制在 n≈d 甜区能否显著强过普通有状态记忆（机制特异性）。**

---

## 1. 借来的引擎（GDN-2 delta-rule）：wiring 0 致命 ✅

HPC 上 gdn2 臂用 FLA 自己的 kernel，递推数学是 FLA 的。审计我们喂 kernel 的 q/k/v/β/g：

| 项 | 结论 |
|---|---|
| gated delta-rule 递推（stub einsum 逐维） | ✅ 与 canonical（DeltaNet 2406.06484 / GDN-2 2605.22791 / FLA naive）转置等价，无收缩维/符号错 |
| q/k L2-norm、β=sigmoid∈(0,1)、g=log-space<0、传参解包 | ✅ 全对齐 FLA 契约 |
| β∈(0,1)+k L2-norm | ✅ delta 标准干净覆写区间，非缺陷 |

**推论**：n_kv=4≪d=64 若崩，数学上排除「机制做不了关联召回」和「容量 null」，只能是 wiring/训练/数据管线。（细节 → `MQAR_MATH_WIRING_AUDIT.md`）

---

## 2. 容量理论：delta 优势窗口在 n≈d，小 n 打平是「伪 null」

| n 区间 | keys 几何 | stateless | delta-rule | delta 优势 |
|---|---|---|---|---|
| **n≪d**（1-4, d=64） | 近正交 | 完美召回 | 完美召回（纠错项≈0） | **基本无** |
| **n≈d**（32-96, d=64） | 开始非正交 | 开始出错（Schlag Fig2: d=64@n≈60） | 主动擦除-写入纠偏 | **存在且明显** |
| **n>d** | 严重非正交 | 崩溃 | 仍维持 | **最大** |

- **Stage-1 的 CHASE 连通分量 n=1-4 两臂打平 = 理论预期的伪 null**（n≪d 时本就该打平），不是机制死。A2≈A1' 在小 n 反而**印证机制理解正确**。
- Route2 甜区 **[32,96]（逼近 d=64）设对了**（Schlag 容量界 + DeltaNet collision L>d）。
- ⚠️ **两个 paper 必交代的限定**：① collision 原文是「L>d」（序列长），我们映射成「distinct 身份数 n>d」是自己的推断（方向安全但须明说）；② Hopfield 是指数容量界、linear attn 是线性界（≈d），别混引——该引 Schlag 线性界。

### 2.2 ⚠️⚠️ 探针实测 + theory-audit 三层防线纠偏（2026-06-22，上表 n≈d/n>d 乐观行被证伪）

无conv 甜区探针(job 1482972, csv 真源核过)实测推翻上表「n≈d delta 优势明显 / n>d delta 仍维持最大优势」：

| arm | n=16 | n=32 | n=64(=d) |
|---|---|---|---|
| gdn2 | 0.05 / 0.06 | 0.02 / 0.02 | 0.007(lr3e-4) / **0.999(lr1e-3 converged!)** |
| gla | 0.04 / 0.05 | ~0.001 | 0.005 / **0.992(lr1e-3 converged!)** |
| linear_attn | 0.05 / 0.06 | 0.02 | 0.005 / 0.008 |

**theory-audit diagnose 三层防线(theorist→skeptic+2nd theorist 多路投票→verifier)结论**：
1. **崩因 ≠ 容量/机制死刑**(归因=②优化/配置)：n=16 崩 << 容量界 64;且 **n=64(=d) lr=1e-3 gdn2/gla 都收敛到 0.99** → 容量崩讲不通(n=d 该最崩却收敛)。真因 = **无 short conv 让 MQAR 难优化**(Zoology 已知 conv 助收敛) + lr/步数敏感(8000step 大部分配置没训到,非不能训)。
2. **「GDN-2 比 plain DeltaNet 更早崩」反常不成立**(skeptic🔴+2nd theorist 独立一致)：0.05(我们n=16) > 0.009(VLA n=16) = 崩得**更轻**;且 n/d 不同(0.25 vs 0.5)是横比口径错。theorist v1 的「时间衰减第二崩塌源/双链死」失去解释对象 → **撤回**(α 从未 dump,是待跑假说非定理)。
3. **delta 非特异迹象**：唯一可比收敛点(n=64 lr1e-3) **gdn2=0.999 ≈ gla=0.992** → delta 不比普通有状态 GLA 强(单点,但是路A要的 A2>GLA 的反证)。
4. random baseline = 1/(V/2)=1/4096=0.00024(非 1/8192);n=64 acc 0.007 = 28× random(有学到没收敛)。

**净判**：探针又是 messy null——证明 GDN-2 没那么差(非容量/机制死),但也**没证出 delta 特异**(全崩判不出 gap + 唯一收敛点≈GLA)。§4 第一链(目标函数错配)仍独立死。叠加 skeptic 路A 2🔴 → 路A 不值,理性指向路B。**上表 n≈d/n>d 乐观行作废,以本节实测为准。**

### 2.1 ⚠️ VLA 一手数据校准（2026-06-22 researcher 原文核源，skeptic🔴-1 触发）

上表「n≈d 才显优势、n>d 仍维持」的乐观叙事**对 plain DeltaNet（scalar gate）已被 VLA(arXiv 2605.11196) 实测证伪**——但**对我们用的 GDN-2（解耦 erase/write 门）是文献空白，押探针**。逐条校准：

| 项 | 本节原主张 | VLA 一手实测校准 |
|---|---|---|
| **plain DeltaNet 甜区** | n≈d 才显优势 | **证伪**：Table 11(d_h=32,无conv) DeltaNet n=8→0.965、**n=16(n/d=0.5)→0.009 已崩到 random**(1/128≈0.008)、n=24→0.007。无「n≈d 优势窗口」，n/d≈0.5 就早崩。 |
| **n>d 仍维持（delta）** | 「最大」优势 | **证伪**：plain DeltaNet n≥16 全程 random，与 linear attn 同。真正 n>d 维持的是 VLA 自己（matrix gate，n=32→0.623）不是 DeltaNet。 |
| **Schlag 线性界 d** | linear attn n≈60/d=64 出错 | 基本坐实(n/d≈0.94)，但这是 **linear attn**，非 delta-rule——别拿它给 DeltaNet 容量背书。 |
| **GDN-2 解耦门崩点** | （隐含继承 delta 乐观窗口） | **文献空白**：VLA 只测 plain DeltaNet(scalar gate)；GDN-2 原文(2605.22791) 零 MQAR 容量曲线。GDN-2 的 b_t⊙k_t **定向**擦除理论上类 VLA matrix A_t 的方向选择性遗忘 → 崩点**可能**晚于 plain DeltaNet，但**无任何文献实测**。 |

- **机制差核心**（VLA §1.1/§7.2）：scalar gate「forgets **all** directions at once」→ 均匀遗忘致早崩；matrix/方向选择性遗忘才能在 n≤d 维持。VLA Prop3：三者状态都是 d_h×d_h、上界都 d_h，差别全在遗忘是否方向选择。**GDN-2 的解耦门属哪边 = 我们要证的空白**。
- **→ 探针(job 1482972)意义升级**：测 n∈{16,32,64}，而 plain DeltaNet 恰在 **n=16 崩**。
  - **gdn2 n=16 仍 acc>0.5** = 解耦门推迟了 DeltaNet 崩点（vs plain DeltaNet n=16 已崩）→ 文献空白处一手证据，本身可成 novelty 卖点。
  - **gdn2 n=16 就崩** = GDN-2 退化成 scalar-like 均匀遗忘 → 据 VLA 强先验转路 B（Frangi 门）。
- **§2 限定语（写作期必加）**：「delta 甜区预测成立的前提是 GDN-2 解耦门能实现类 VLA 的方向选择性遗忘；若退化为 scalar-like 遗忘则崩点同样在 n/d<1。定论待 GDN-2 自测（文献无 GDN-2 MQAR n/d 曲线）。」

---

## 3. 三件原创件可行性

### 原创① 可微 Frangi 解耦 erase/write 门（Claim 3）—— 🟠 成立，改措辞
- 机制成立、可训（clamp 饱和杀 alpha_w 梯度被全局标量聚合救回 = 可接受残差）。
- **🔴 措辞硬伤**：我们解耦的是「**全局遗忘率 α vs 写入强度 β**」，**不是** GDN-2 的「**定向擦除 vs 定向写入**」（b_t⊙k_t / w_t⊙v_t per-channel）。两者**正交、不同轴**。我们的 β 仍同时进擦除项与写入项（原版耦合没碰）。
- **§3.4 必改**：删「双门近似」（暗示劣化版同一东西，会被 Eq.10 对照击穿），改「**正交解耦轴**」+ 主动声明（各向同性全局衰减 vs 定向擦除、不 claim 等价或更细）。对血管用例（延续处压全局遗忘保住主导身份）合理但是更粗的近似。
- 文献：可微 Frangi 当外部门无先例（novelty+）；⚠️ 可微 Hessian 近重复特征值梯度爆炸（2104.03821），背景均匀区 λ₁,λ₂≈0 需 Taylor/LDL 防爆。

### 原创② 空间 re-ID 读出头（Claim 2）—— 🔴 1 致命
**梯度图逐节点证**：作用在 memory 参数上的梯度源**只有分割主 loss**。而：
- 分割主 loss = 逐像素分类，充分条件是「每像素 readout 可分前景/背景」；
- headline 要的「同根两端 memory 状态 cosine 高」是**严格更强**约束，分割 loss 对它**梯度激励恒为零**（同根两端各自分对前景即可，状态可完全不同）；
- DeltaNet「关联检索从主 loss 涌现」**前提=主任务本身是检索**（每 token 对召回 loss 在线梯度下降）；眼底分割不是检索 → **涌现前提不满足**。
- 三道 detach（保 Claim1 GT-free）掐断了唯一能训 memory 绑身份的弱监督路径。

文献三方印证：XMem 靠 attention correspondence 不靠裸 cosine；医学 VOS 需显式 contrastive memory；Alain&Bengio linear probe 定理（探针只读出主干已有的，主干没学到则必失败）。

### 原创③ 跨断点检索 framing（Claim 1）—— 🔴 连带塌
依赖②的 memory 真能 re-ID。②塌 → 因果 claim 退到「容量充足的 readout + 模块容量」，不能 claim delta-rule 机制特异性。（细节 → `NOVELTY_DERIVATION_AUDIT.md`）

---

## 4. 核心定理（目标函数错配）

> **在「分割主 loss + 三道 detach 隔离 re-ID 头」这个目标函数下，memory 状态空间不会被优化出「同根身份可 cosine 检索」的结构。因此 A2（delta 记忆）与 A1'（无状态等参）在 re-ID 上必然趋同——这不是实现 bug，是目标函数与 claim 不对齐的结构性必然。**

三独立证据同向咬合：① 理论（梯度激励为零）→ 预测 A2≈A1'；② 实证（Entry 22, mean_delta≈2.35e-5）→ 实测 A2≈A1'；③ linear probe 定理 → 主干没学到则探针读不出。

**关键推论**：路 2（换密集数据集让 n≈d）**单独解决不了**——crowding 是「装得下」，碰不到「没 loss 去绑」。路 2 要 work 几乎必然要加显式身份 loss → 与 R5 冲突比 LOG 当前评估更深。

---

## 5. 解法路径 + 可行性判决

**唯一数学出路 = 显式检索 loss 回流 memory**。理论锚（2026-06-22 researcher 原文核源纠正）：
- ⚠️ **引用纠错**：「状态更新≡检索 loss 一步在线梯度下降」是 **DeltaNet 自己**证的（`S_t=S_{t-1}−β_t(S_{t-1}k_t−v_t)k_t^T` = 对 `L_t=½‖Sk_t−v_t‖²` 一步 GD，Songlin Yang blog + NeurIPS2024 DeltaNet），**不是 VLA**——VLA 是 RLS 闭式解（Sherman-Morrison），无显式 readout loss 回流。原文写「VLA 证」是误读，引用改 DeltaNet。
- 显式 loss **有工程先例**：医学 VOS 2503.14979 的 `L_tc` contrastive 直接流到 memory values（不经 detach），可训。
- 自切「同根」标签本质 = **SupCon**（Khosla 2020，有显式同根 ID），不是 SimCLR 式 SSL → 引 SupCon 比 2506.04411 更直接。

关键辨析：合成断点「同根」标签来自自切 ≠ 数据集真实连通性 GT（眼底集本就没）→ 回流**不污染 Dice 评估**（C-DARL/VAMAE 自监督先例），但有两道 skeptic🔴（2026-06-22，路A拍板前必解）：
- **🔴-1 VOS 撞车**：改 R5 加显式 loss 后 headline 从「记忆**自发**涌现身份」滑成「U-Net+记忆+contrastive loss」= VOS 家族成熟范式（CVPR24 Cutie/XMem、VS-ReID 1708.00197、医学VOS 2503.14979），CVPR 增量存疑 → 须 researcher 系统查「单图内空间 re-ID + delta 解耦门」是否留缝。
- **🔴-2 GT-free 死结**：自切要知「切前同一条」须先有分割 GT 连通分量标注 → 拆 detach 回流 memory = **作废 Claim1「续连 GT-topology-free」防御**。出路=诚实把 Claim1 降级为「合成断点弱监督（creatis 同范式，不 claim 无监督）」，**用户拍板**。
- skeptic 裁决：**即便探针 LIVE 也别当天拍走路A**，先补三门（查VOS撞车留缝 / 用户拍 Claim1 降级 / 小算力验「两臂都加loss后血管 A2 仍>A1'」），三过才投重做工程，否则路B保ACCV、路A留CVPR后续。

| 路径 | 做法 | venue | 代价 |
|---|---|---|---|
| **A 进攻** | 合成断点对比 loss 回流 memory，重划 R5 | 可冲 CVPR/ICCV | 战略级改 R5 |
| **B 退守** | 弃 re-ID，锚 Frangi 门 + 拓扑保持 | MICCAI/ACCV 天花板 | novelty 降 |

**可行性数学证不出，押实验**：
> 真正胜负手 = MQAR n≈d=64 甜区，**A2(delta) 能否同时显著 > A1'(无状态) 且 > GLA(普通有状态)**（双 gap 判据，反 HARKing 写死 PREREG）。
> - 双胜 → delta 机制特异性坐实 → 路 A 值得改 R5 冲 CVPR。
> - `delta_nonspecific`（A2≈GLA） → delta 非特异、仅「有状态」效应，headline 塌 → 退路 B。

加显式 loss 后「能训出 re-ID」大概率成立，但创新重心偏到「loss+benchmark」——审稿人必问「换任意有状态记忆+loss 也行？」。**所以 delta 机制特异性（A2>GLA）是出彩与否的真正胜负手，没跑出来前谁都不能说它出彩。**

（实验进展见 `PROJECT_LOG.md` 最新 entry；判据 `ROUTE2_BUDGET_PREREG.md`）

---

## 6. STORY 待改清单（理论推导触发，定稿前必改）

| § | 现状 | 改成 |
|---|---|---|
| §1/§3 | 引 GDN-2「interference」当**短序列**干扰锚 | 误用（原文 4K-8K 长序列）→ 改引 Schlag d 容量界 + DeltaNet collision |
| §3.4 | 「双门近似」 | 「正交解耦轴」（α-decay vs β-write，非 GDN-2 的定向擦除 vs 写入）+ 三条主动声明 |
| Claim 1/2 | 「记忆内生做 re-ID」 | 视 §5 实验：双胜→保留并补显式 loss 说明；否则退「容量+readout」 |
| paper | collision「L>d」直接当「n>d」 | 明说 L→n（distinct 身份数）是我们的推断 |

---

## 7. 关键引用

- [GatedDeltaNet 2412.06464](https://arxiv.org/pdf/2412.06464) / [GDN-2 2605.22791 Eq.10](https://arxiv.org/html/2605.22791v1) / [FLA 源码](https://github.com/fla-org/flash-linear-attention)
- [DeltaNet collision 2406.06484](https://arxiv.org/abs/2406.06484) / [Schlag 容量界 2102.11174](https://ar5iv.labs.arxiv.org/html/2102.11174)（Fig2: d=64@n≈60）
- [DeltaNet 状态≡检索loss一步GD（Songlin Yang blog）](https://sustcsonglin.github.io/blog/2024/deltanet-1/) / [VLA(RLS闭式解,非GD) 2605.11196](https://arxiv.org/html/2605.11196) / [SupCon Khosla2020](https://arxiv.org/abs/2004.11362)（自切同根本质=SupCon）/ [自监督对比≈有监督 2506.04411](https://arxiv.org/abs/2506.04411)（C大时,非最强支撑）
- VOS 撞车（路A改R5后 headline 防御）：[Cutie/XMem CVPR24](https://openaccess.thecvf.com/content/CVPR2024/papers/Cheng_Putting_the_Object_Back_into_Video_Object_Segmentation_CVPR_2024_paper.pdf) / [VS-ReID 1708.00197](https://arxiv.org/pdf/1708.00197) / 自切不泄漏先例 [C-DARL 2308.00193](https://arxiv.org/pdf/2308.00193)
- [可微 SVD 梯度 2104.03821](https://arxiv.org/abs/2104.03821) / [医学VOS contrastive 2503.14979](https://arxiv.org/abs/2503.14979) / [Alain&Bengio linear probe](http://index.cslt.org/mediawiki/images/f/f6/Understanding_intermediate_layers_using_linear_classifier_probes.pdf)

> 盲区如实标 TODO（L→n 映射、delta n<d 非正交定量优势界、V=2048 无官方源）。不利结论（re-ID 致命）照写，禁改判定方向。
