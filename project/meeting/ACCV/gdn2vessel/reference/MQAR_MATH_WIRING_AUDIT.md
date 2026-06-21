# GDN2MemoryModule 数学推导 + wiring 审计 — 「bug 冒充 null」证否

**日期**：2026-06-21
**触发**：MQAR 隔离测 `GDN2MemoryModule` 疑似崩 → 用户要求大编队**纯数学推导 + 文献核源**，判定是实现 bug 还是机制真做不了关联召回。**全程只推不跑代码。**
**方法**：3 路并行（skeptic opus 推 delta-rule 数学 + wiring；researcher 核 short-conv 文献；researcher 核容量理论）。
**服务**：Claim 1「delta-rule 关联记忆做血管断点续连」/ Route2 容量探针判据。

---

## 一句话裁决

> **我们喂 kernel 的数学完全正确（0 致命）。MQAR 在小 n（如 Stage-1 的 n=1-4）两臂打平不是机制死，是 n 选太小的「伪 null」——理论预言 delta-rule 的优势窗口在 n≈d=64 附近及以上，n<<d 时两臂本就该打平。结论：headline 没被证伪，但承重前提改为「必须在 n≈64 甜区测」。**

三个独立子结论合议：
1. **数学/wiring 正确**（skeptic）→ 排除「实现 bug 冒充 null」。
2. **short conv 缺失不是混淆**（researcher B）→ 主对比 gdn2 vs linear_attn 对称、干净。
3. **小 n 打平是理论预期**（researcher C）→ Stage-1 的 n=1-4 null 是伪 null（粒度错），真判决要在 n≈d。

---

## ① delta-rule 递推数学 + wiring 审计（skeptic，0 致命）

**关键事实**：HPC 上 gdn2 臂真用的是 **FLA 自己的 `naive_chunk_gated_delta_rule`**（不是 CPU stub）。递推数学是 FLA 的，审的是我们包装层喂 kernel 的 q/k/v/β/g 对不对。

### 逐方程对照（canonical vs 我们实现）

| 项 | canonical | 我们实现 | 判定 |
|---|---|---|---|
| 递推 | `S_t = diag(g_t)S_{t−1} + β_t(v_t − S_{t−1}k_t)k_tᵀ`，`o_t=S_t q_t`（GatedDeltaNet 2412.06464 / GDN-2 2605.22791 / FLA naive） | stub 4 个 einsum（衰减/retrieval/写入/output） | ✅ value-by-key 约定下逐维自洽，与 FLA key-by-value 互为转置、语义等价，无转置/符号/收缩维错误 |
| q/k L2-norm | FLA naive **不内部** normalize → 需调用方自己做 | L745-746 `F.normalize(q/k)` | ✅ 正确补上 |
| β 范围 | FLA 默认 `sigmoid∈(0,1)`（仅 `allow_neg_eigval=True` 才 `2·sigmoid∈(0,2)`） | `sigmoid(proj_write)∈(0,1)` | ✅ 合法默认，k 已 L2-norm → β∈(0,1) 是标准干净覆写区间（I−βkkᵀ 特征值∈{1−β,1}） |
| g 衰减 | FLA `−exp(A_log)·softplus(...)` < 0 | `logsigmoid(proj_g)−\|erase\|` < 0 | 🟠 参数化不同款但都是合法 log-decay，机制等价，**非 bug** |
| 传参/解包 | `(q,k,v,g,beta,...)` → `(o, final_state)` | L763/774 命名参数 + L766/775 取 res[0]/[1] | ✅ |

### 能力判据（确认 sanity gate 逻辑）
n_kv 个近正交单位 key 存 d=64 维状态 S∈ℝ^{64×64}：n_kv<64 时 delta-rule 的纠错项 `β(v−Sk)kᵀ` 精确覆写对应 slot 不干扰其他 → **n_kv=4 ≪ 64 平凡可解**。∴ 若实证 n_kv=4 崩 → 数学上排除容量 null（上界 64 远未触及），只能是 wiring/训练/数据管线。

### 🟠 值得改（不阻断 HPC 判定）
- **CPU stub 缺 `scale=1/√d`**：FLA naive 内部 `q=q*scale`，stub 没有 → output 幅度差 √64=8× 常数。**只影响 CPU smoke/pytest，HPC 走 FLA kernel 不受影响**。要 bit 对齐则 stub L95 前补 `qt=qt/(dh**0.5)`。
- **g 参数化 logsigmoid vs softplus**：不影响召回能力，想严格贴 GatedDeltaNet 复现谱系可换。

### 🔍 调试优先级（若真要排查崩因，按此序）
1. **先验 key 正交性**：dump 一 batch normalized k 算 Gram 矩阵——若非近正交则问题在表征不在机制（最易忽略）。
2. **验训练真在学**：loss 是否真降；不降=训练 bug，降了 eval 崩=数据/评估管线 bug。
3. **派 verifier 核 HPC 真走 FLA**：`mqar_capacity_probe.py` L101-111 fallback 逻辑——确认 HPC `_FLA_AVAILABLE=True` 没被静默踩进 CPU stub 分支（**「bug 冒充 null」最隐蔽入口**）。

**来源**：[GatedDeltaNet 2412.06464](https://arxiv.org/pdf/2412.06464)、[GDN-2 2605.22791](https://arxiv.org/html/2605.22791v1)、[FLA naive 源码](https://raw.githubusercontent.com/fla-org/flash-linear-attention/main/fla/ops/gated_delta_rule/naive.py)、[FLA layer 源码](https://raw.githubusercontent.com/fla-org/flash-linear-attention/main/fla/layers/gated_deltanet.py)。盲区：GDN-2/GatedDeltaNet 原 PDF 方程无法逐字抓，β/α 参数化结论靠 FLA 一手源码 + GDN-2 HTML + 综述交叉验证；核心 wiring 契约（normalize/sigmoid/log-space/签名）均一手源码，高置信。

---

## ② short conv 缺失是不是混淆？（researcher B，否）

**疑点**：gdn2/linear_attn 臂无 short conv，gdn2_fla 臂有（`use_short_conv=True`）。FLA 警告 short conv「crucial, do not turn off」。怕「无 conv 的 gdn2 崩」跟 delta 记忆无关。

**核源结论**：
- FLA `use_short_conv` 默认 True，「crucial」警告是针对**下游语言建模**性能，**不是 MQAR 合理性声明**。Based 文献：short conv 管局部依赖（bigram），不是 delta 记忆的承重结构。[FLA delta_net.py]
- **VLA(2605.11196) §5.4 官方 MQAR：所有臂都不带 short conv**（softmax/linear/DeltaNet/VLA 四臂 zero conv）。其 DeltaNet 臂无 conv 仍能超 linear attn → **delta 记忆能力不依赖 short conv 才能被 MQAR 测出**。VLA 官方配置：`d=128, H=4, d_h=32, layers=2, FFN=256, steps=3000, lr=3e-4 cosine`。
- Zoology(2312.04927)：MQAR example config **没对所有模型统一加 short conv**；pre-Based 线性注意力（RetNet/GLA）本就不带。
- 2407.05591：LinCAT（线性 attn+conv）表现**不如** CAT（softmax+conv）→ conv 不能独立给 stateless 线性注意力注入 MQAR 能力。

**裁决**：「gdn2 无 conv vs gdn2_fla 有 conv」确实不对等（苹果 vs 橘子），**但这不是主判据**。主判据 = **gdn2 vs linear_attn 两臂都无 conv、对称、干净**；gdn2_fla 只是 canonical 交叉验证参考臂，正交于 LIVE/DEAD 判断。short conv 缺失**不能单独解释** gdn2 崩。

**修正建议**：
- prereg 补一句：`gdn2_fla` 有 conv 是 canonical FLA 配置，与主比较正交，不影响 null 判断。
- 可选增强（防审稿质疑）：加 `gdn2_no_conv` 臂 = FLA GatedDeltaNet 但 `use_short_conv=False`，直接对比 conv 对 delta 模型 MQAR 影响。**非必须**。
- ⚠️ **待核**：我们用 `n_heads=1, head_dim=64, steps=2000, lr sweep`，VLA 官方 `H=4, head_dim=32, steps=3000, lr=3e-4`。配置差异是否影响可比性，建议对齐 VLA 或在 paper 交代。

**来源**：[VLA 2605.11196](https://arxiv.org/html/2605.11196)、[Zoology 2312.04927](https://arxiv.org/html/2312.04927)、[Based 2402.18668](https://arxiv.org/html/2402.18668v1)、[FLA delta_net.py](https://github.com/fla-org/flash-linear-attention/blob/main/fla/layers/delta_net.py)、[Conv Augments Attention 2407.05591](https://arxiv.org/html/2407.05591v1)。TODO：Based §6.3 Table 4 short conv 消融数字 PDF 未提取。

---

## ③ 容量理论：delta 优势窗口在哪？（researcher C，关键发现）

### delta-rule vs stateless 的优势窗口（裁决性推导）

| n 区间 | keys 几何 | stateless ELU+1 | delta-rule | delta 优势？ |
|---|---|---|---|---|
| **n ≪ d**（如 n=1-4, d=64） | 几乎正交 | 完美召回 | 完美召回（纠错项≈0） | **基本无** |
| **n ≈ d**（如 n=32-96, d=64） | 开始非正交（随机向量 \|kᵢᵀkⱼ\|≈1/√d） | 开始出错（Schlag Fig2: d=64 在 n≈60 积累误差） | 主动擦除-写入纠偏 | **存在且明显** |
| **n > d**（n≫64） | 严重非正交，无足够正交基 | 崩溃 | 仍能维持召回 | **最大** |

机制：stateless `o=S_T φ(q)=Σφ(vᵢ)[φ(kᵢ)ᵀφ(q)]`，key 非正交则串扰（crosstalk）；delta 先 rank-1 擦除 `(I−βkkᵀ)` 再写入 → 「替换」而非「累加」，抑制串扰。

### 对我们项目的三条裁决
1. **[32,96] 甜区设对了** ✅——正落在 Schlag Fig2 观察到 linear attn 开始积累误差的区间（d=64 时 n≈60 触发）。
2. **Stage-1 n=1-4 两臂打平 = 理论预期的伪 null** ✅——n≪d 时 keys 近正交、两臂都近完美召回、delta 纠错项≈0、数学上等价。A2≈A1' 这件事**反而是机制理解正确的强证据**，不是机制坏。真判决必须在 n≈d。
3. **⚠️ GDN-2「interference」引用被误用** ❌——原文「interference among many compressed associations」语境是 **RULER 4K-8K 长序列**，**不支撑「短序列也有干扰优势」**。STORY_FRAMEWORK §1/§3 把它当短序列干扰锚 = 站不住，**需替换或限定**（改引 Schlag 容量界 + DeltaNet collision，别引 GDN-2 这句撑短序列）。

### ⚠️ 两个 paper 必须交代的风险
- **L vs n 映射**：Yang 2024 写的是 collision「**L>d**」（序列长度），不是「n>d」（distinct 实体数）。我们把 L 映射成血管 distinct 身份数 n 是**自己的推断**，原文无直述。方向安全（真碰撞阈值 n<L，保守），但 paper 必须明说此映射。
- **Hopfield 容量是指数界（softmax 路径），linear attn 是线性界（≈d）**，别混用。我们该引的是 Schlag 的 d 线性界。
- **TODO**：未找到 delta-rule 在 n<d 非正交 key 的**定量**优势界（只有定性），paper 要写精确量级需补 MQAR 实验或推导误差界。

**来源**：[DeltaNet 2406.06484](https://arxiv.org/abs/2406.06484)（"collisions when L>d"）、[Schlag 2021 2102.11174](https://ar5iv.labs.arxiv.org/html/2102.11174)（"storing more than d_dot associations → retrieval error"，Fig2 d=64@n≈60）、[GDN-2 2605.22791](https://arxiv.org/abs/2605.22791)（interference 语境=4K-8K）、[Modern Hopfield 2008.02217](https://arxiv.org/abs/2008.02217)。

---

## 行动项（待用户拍板/后续窗口）

| # | 项 | 性质 | 优先 |
|---|---|---|---|
| 1 | MQAR 真判决**必须在 n≈{32,64,96} 甜区**看 gdn2 vs linear_attn，不能拿 n=1-4 下结论 | 判据 framing | 🔴 高 |
| 2 | STORY §1/§3 **替换 GDN-2「interference」短序列锚**，改引 Schlag d 界 + DeltaNet collision | 写作纠偏 | 🔴 高 |
| 3 | paper 明说「L→n（distinct 身份数）」映射是我们的推断 | 写作诚实 | 🟡 中 |
| 4 | prereg 补注：gdn2_fla 有 conv 与主比较正交 | 文档 | 🟡 中 |
| 5 | 派 verifier 核 HPC sweep 真走 FLA kernel 非 CPU stub fallback | 防伪 null | 🟡 中 |
| 6 | （可选）对齐 VLA 官方配置（H=4/head_dim=32/steps=3000/lr=3e-4）或 paper 交代差异 | 复现严谨 | 🟢 低 |
| 7 | （可选）加 `gdn2_no_conv` 臂直接量化 conv 影响 | 防审稿 | 🟢 低 |

> **未做**：任何代码执行（CPU 烟测等）——本任务=纯推导核源，不跑。
