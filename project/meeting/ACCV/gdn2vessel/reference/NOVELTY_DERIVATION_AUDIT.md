# 三件原创件 数学推导 + 可行性审计 —— 「能不能证明 + 会不会跑好」

**日期**：2026-06-21
**触发**：用户追问「我们**原创**的创新点你推了吗?能证明可以吗?会跑好吗?」——指出上一轮 [`MQAR_MATH_WIRING_AUDIT.md`](MQAR_MATH_WIRING_AUDIT.md) 只验了**借来的 GDN-2/DeltaNet 引擎**(NVIDIA 的),没碰**我们自己的三件原创**。
**方法**：主线先第一性推导 → 派 2×skeptic(opus) 对抗验证 + 1×researcher(sonnet) 文献核。**全程不跑代码。**
**服务**：Claim 1/2/3 全部原创机制 + headline 定稿决策。

---

## 一句话裁决

> **① Frangi 门机制成立(改措辞即可)；② re-ID 头有 1 个致命伤——没有任何 loss 训练 memory 绑同根身份,headline「记忆做 re-ID」的因果 claim 站不住,与 Entry 22 实证 A2≈A1' 因果咬合;③ framing 依赖②同塌。会训通(不发散),但 re-ID 大概率跑不出有用结果。出路涉及改 R5 弱监督辖域 = 战略级,需用户拍板。**

---

## 原创① 可微 Frangi 解耦 erase/write 门(Claim 3)—— 🟠 改措辞,不阻断

代码 `unet_gdn2.py` L828-844 + L756。skeptic 对抗主线两条推导:

### 推导 A — clamp 饱和杀 alpha_w 梯度 → 降级为 🟢 可接受残差
- 饱和精确条件:`raw_write > 1/(1+alpha_w·v)`。alpha_w 初始 σ(0.5)≈0.622,v→1 时触顶阈值≈0.617,血管处易触。**饱和真实存在**(主线①②证实)。
- **但被三因素救回**:(a) alpha_w 是**全局标量**,跨 batch×T×nh 聚合梯度,饱和仅命中「血管∩高 write_logit」少数像素;(b) 被截断的恰是「已达成最大写入」的语义无害点;(c) v 已 per-sample 归一化 max=1、α_w∈(0,1)→放大仅 ×1.62 温和。→ **alpha_w 整体可训,机制不失效**。
- **可选探针(非必须,要做交主线跑)**:训练后查 `alpha_w.grad` 范数 + 前后值,若卡死则降级回硬伤,改用 `write_gate=σ(proj_write+α_w·v)`(放大塞进 sigmoid 内,无需 clamp,处处可导)。

### 推导 B — 我们解耦的不是 GDN-2 那个门 → 🟠 证实,STORY 必须改措辞
真 GDN-2(arXiv 2605.22791 Eq.10):`S_t=(I−k_t(b_t⊙k_t)ᵀ)D_t·S_{t−1}+k_t(w_t⊙v_t)ᵀ`,b_t∈[0,1]^{d_k}、w_t∈[0,1]^{d_v} **per-channel 向量门**,在 rank-1 更新**内部**解耦**定向擦除 vs 定向写入**。

我们真实跑的(FLA 单-β kernel):`S_t=exp(g_t−|e_t|)·(I−β_t k_tk_tᵀ)S_{t−1}+β_t v_tk_tᵀ`,β/erase 均 per-head **标量**,erase 进**全局各向同性衰减 α_t**,**β 仍同时进擦除项与写入项**(原版 β 耦合我们根本没碰)。

| 维度 | 真 GDN-2 | 我们 |
|---|---|---|
| erase 进哪 | 定向擦除矩阵(沿 kkᵀ 选择性) | 全局标量衰减 α_t(各向同性) |
| 解耦了什么 | 定向擦除 vs 定向写入 | **全局遗忘 vs 写入强度**(正交于 GDN-2) |
| 门粒度 | b/w 向量 | per-head 标量 |

- **对血管用例反而对**:延续处压低 erase→α_t→1→已存身份保留更久。但是**更粗的各向同性近似**,非更优。
- **§3.4 现有「双门近似」措辞会被真方程击穿三处**:① 「近似」暗示「劣化版同一东西」,实为「正交的不同东西」(说成劣势还露破绽);② 没区分各向同性 vs 定向;③ 没声明 β 残余耦合。**改写建议已写入 skeptic 报告**——删「双门近似」,改「正交解耦轴」+ 三条主动声明。

### 文献(researcher)
- 可微 Frangi 当外部门调制别的模块 = **无先例,novelty 成立**(Frangi-Net 是学权重做分割;VP UNet 2508.00235 的 Frangi 是 fixed 不可微)。
- ⚠️ **已知工程坑**:可微特征值在**近重复特征值处梯度爆炸**(arXiv 2104.03821)。Frangi Hessian 在背景均匀区 λ₁,λ₂≈0 近重复→反传数值爆炸,需 Taylor 平滑/pseudo-inverse。做可微 Frangi 必处理。

---

## 原创② 空间 re-ID 读出头(Claim 2)—— 🔴 1 致命:无训练信号绑身份

代码 `unet_gdn2.py` ReIDReadoutHead L333-547 + `reid_loss.py`。skeptic 三推导全部证实,合流成 1 致命。

### 推导 A — detach 自洽,但头是「读探针」非「身份训练器」(致命链)
梯度图逐节点核实:`L_match` 梯度只触达 `mem_proj/loc_proj/fuse/log_temp` 四组参数,**不触达 memory/encoder/Frangi**(detach1/3 截断)。→ GT-free 在梯度层成立(Claim 1 正资产),**但头无力改变 memory 的身份排布**。

**致命问:什么 loss 训 memory 绑同根身份?排查 = 没有任何 loss。**
| 梯度源 | 作用对象 | 绑同根身份? |
|---|---|---|
| 分割主 loss(Dice/BCE 逐像素) | memory+encoder+Frangi | ❌ 只要逐像素分对前景/背景,同根两端状态可完全不同 |
| L_match / L_contrastive | 仅头投影层 | ❌ detach 后够不到 memory |
| 显式 retrieval/跨断点信号 | — | **不存在** |

DeltaNet「关联召回从主 loss 涌现」**前提=主任务本身是检索目标**(LM/recall,delta-rule 每 token 对召回 loss 做一步在线梯度下降)。**眼底分割是逐像素分类,不是检索目标→涌现前提不满足。**

### 推导 B — cosine-on-memory=同根身份 是纯假设,无机制保证
`o_t=S_t·q_t`,要同根两位 cosine 高需 ① q 同根一致(局部外观差很多,无保证) **或** ② S 对同根给一致 readout(=身份绑定本身,循环论证)。在推导 A 已证「无 loss 绑身份」下,**假设站不住**。→ 给 Entry 22「A2≈A1'(mean_delta≈2.35e-5)」提供机制层「为什么必然如此」。

### 推导 C — 位置缩放粒度塌缩 → 🟠 加剧 A/B
- dec3(128)→bottleneck(32) scale=0.25+floor。一个 bottleneck token 覆盖原图 **16×16 px**。**原图距离<16px 的断点塌进同一 token**→近距离 re-ID 结构性不可分。眼底毛细血管间距常<16px→密集区相邻断点几乎必塌。
- **二次损失**:loc 路走 dec3(128)双线性,比 memory 路(32)细 **16×**→fuse 理性抄近路绕过 memory = LOG 二诊「dec_feat 抄近路压没 memory」的机制根因。
- ⚠️ **打击路 2**:换分支段粒度让 n↑的同时,断点空间密度↑→更多断点塌同 token→memory 可分性更差。

### 文献(researcher,利空)
- 关联记忆状态做显式 cosine re-ID = 无直接先例(GDKVM 时序跟踪不是跨实例检索;MambaPro re-ID 在输出层不在状态)。**novelty+ 但也无先例证明 work**。
- **纯分割 loss 自发学出可 cosine 检索身份 = 文献无证据,多篇反向暗示需显式 contrastive**(医学 VOS 2503.14979 显式加 temporal contrastive memory bank;DAMN 2007.10637 专设 Memory Refreshing Loss)。**组2 是三件里最缺训练信号、最可能跑不出来的。**

---

## 原创③ 跨断点检索 framing(Claim 1)—— 🔴 连带
依赖②的 memory 真能 re-ID。②塌→「关联记忆做跨断点身份检索」的因果 claim 同塌,最多退到「容量充足的 readout + 模块容量」,不能 claim delta-rule 机制特异性。

---

## 「会跑好吗」两问拆答
- **会不会训崩**? 不会。门有界、g<0、q/k 归一化、detach 自洽,无 NaN/发散。**能跑通。**
- **会不会有用**(memory 真赢 baseline)? **大概率不**。② 缺训练信号 + ③ 粒度塌缩 + Entry 22 实证 A2≈A1' 三重指向「re-ID 跑不出机制特异增益」。

---

## 🛑 拍板分岔(headline「记忆做 re-ID」定稿,致命伤=1,需用户拍)

出路三选一(按对 R5/STORY 冲突程度排序):
1. **改 headline 因果(不违 R5)**:承认 re-ID 增益来自「头+容量」非 delta-rule 机制,退到「容量充足的关联记忆 readout 支持空间 re-ID」,不 claim 机制特异性。代价:novelty 降,但诚实、与实证一致。**= LOG Entry 24「路 1(门控保留 framing)」**。
2. **加显式身份辅助 loss 直接作用 memory**(去掉 detach 对 memory 那条,让 contrastive 回流):**直接违 R5 弱监督辖域 + Claim 1 GT-free(Entry 10 致命-1 红线)**。战略级,**不可 agent 自决,需用户拍重划 R5**。= **路 2 要 work 的隐藏必要条件**。
3. **证伪本红队**:给出「分割主 loss 隐含同根一致约束」的形式证明。skeptic 强烈怀疑不存在(A2≈A1' 已是反证)。

**额外裁决(对路 2 的独立警告)**:路 2(换密集数据集让 k≈d)**单独解决不了**——crowding 是「装得下」,碰不到「没 loss 去绑」。**路 2 几乎必然要出路 2 的显式身份 loss,与 R5 冲突比 LOG 当前评估更深。建议路 2 立项前把此点摆给用户。**

---

## 引用(关键)
- [GDN-2 arXiv 2605.22791 Eq.10](https://arxiv.org/html/2605.22791v1)、[NVlabs/GatedDeltaNet-2](https://github.com/NVlabs/GatedDeltaNet-2/)
- [Robust Differentiable SVD 2104.03821](https://arxiv.org/abs/2104.03821)(近重复特征值梯度爆炸)
- [DeltaNet NeurIPS2024](https://proceedings.neurips.cc/paper_files/paper/2024/file/d13a3eae72366e61dfdc7eea82eeb685-Paper-Conference.pdf)(涌现前提=检索主任务)
- [医学 VOS temporal contrastive 2503.14979](https://arxiv.org/abs/2503.14979)、[DAMN Memory Refreshing Loss 2007.10637](https://arxiv.org/pdf/2007.10637)
- [Alain&Bengio linear probe](http://index.cslt.org/mediawiki/images/f/f6/Understanding_intermediate_layers_using_linear_classifier_probes.pdf)、[XMem 2207.07115](https://arxiv.org/abs/2207.07115)

> **未做**:任何代码执行。本审计=纯推导核源。`alpha_w.grad` 实测等探针属主线跑数范畴,待拍板后定。
