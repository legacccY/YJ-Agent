# NCA（Neural Cellular Automata）参考手册

> 建档 2026-06-22 ｜ 源：本地三项目记录（Med-NCA / NCA-JEPA / NCA-PhaseMap）+ 5 路网搜（带 URL 引用）。
> 用途：组合台 NCA 家族通用参考。是什么 / 有什么用 / 特性 / 怎么用 / 数学推导 全收。

---

## 1. 是什么

**一句话**：把经典元胞自动机（Cellular Automata）的「手工离散更新规则」换成一个**可微小神经网络**，全图所有 cell **共享同一套权重**，靠梯度下降端到端学规则，再迭代演化涌现出全局结构。

- **经典 CA**（Conway 生命游戏）：网格上每 cell 看 3×3 邻居，按固定离散规则同步更新。规则手工设计、不可微、不能学。
- **NCA**：规则 = 共享小网络（约 8000 参数）。cell 只看局部邻域，并行、去中心化、无全局协调器。
- 奠基论文原话：NCA ≈「带 per-pixel dropout 的循环残差卷积网络」。
- 起源：Mordvintsev et al. **Growing Neural Cellular Automata**, Distill 2020（https://distill.pub/2020/growing-ca/）。

**与其他范式关系**：
| 对比 | 关系 | 区别 |
|---|---|---|
| 经典 CA | NCA 是其可微推广 | CA 离散+手工；NCA 连续+梯度学习 |
| CNN | NCA ≈ 全像素共享同一小 ConvNet 循环迭代 | CNN 单次前向+全局聚合；NCA 循环+局部 |
| RNN | 都有隐藏状态+循环 | RNN 时序单链；NCA 空间大量 cell 并行循环 |
| GNN | 本质同构（网格图上消息传递）；GNCA 已统一二者 | GNN 任意图；NCA 天然规则网格 |
| 扩散模型 | 都迭代精化 | 扩散靠全局时间步+全局注意力、参数上亿；NCA 局部通信、参数 ~8k。近年已有 NCA+Diffusion 混合 |
| PDE/反应扩散 | CA ≈ PDE 有限差分近似；可追溯 Turing 1952 morphogenesis | NCA 能学真实底层 PDE → 连续尺度控制 |

---

## 2. 有什么用（应用谱）

1. **医学影像（本组合台主战场）**
   - **Med-NCA**（IPMI 2023, arXiv:2302.03473）：分割，~13k–70k 参数，比 UNet 小 500×，Dice 高 2–3%，树莓派 B+ 可跑，对伪迹/尺度/平移天然鲁棒。
   - **M3D-NCA**（MICCAI 2023, arXiv:2309.02954）：3D 体素分割，n-level patchify 解决显存，自带方差质控。
   - **NCA-Morph**（BMVC 2024, arXiv:2410.22265）：可变形配准，比 TransMorph 少 99.7% 参数达 SOTA。
   - **MedSegDiffNCA**（IEEE CBMS 2025, arXiv:2501.02447）：NCA+Diffusion 皮肤病变分割，参数省 60–110×。
2. **图像生成 / 纹理**：Self-Organising Textures（Distill 2021）、DyNCA 实时动态纹理、Mesh-NCA（ACM TOG 2024，任意网格表面纹理）。
3. **形态发生 / 自修复**：奠基方向 —— 单种子生长目标图案 + cut-and-regrow 自愈，类比涡虫/蝾螈再生。
4. **机器人 / 控制 / 群体智能**：GoalNCA（目标引导，arXiv:2205.06806）、Spiking-NCA 软体机器人集体控制、群体机器人自组织。
5. **3D / 体素**：Growing 3D Artefacts（ALIFE 2021，Minecraft 生长城堡/功能机器再生）。
6. **分类**：Self-classifying MNIST（Distill 2020，每像素投票达成全局共识）。
7. **生成式扩散骨干**：Parameter-Efficient Diffusion with NCA（npj 2025）—— 336k 参数替 UNet 跑 512×512，FourierDiff-NCA 1.1M 参数 FID 减半。
8. **抽象推理 / 语言**（2025–2026 前沿）：NCA for ARC-AGI（arXiv:2506.15746）、ARC-NCA/EngramNCA、Training LM via NCA（arXiv:2603.10055）。

---

## 3. 特性（优势 / 局限）

**优势**
- 极少参数：原版 ~8k；Med-NCA ~13k（比 UNet 小 500×）；参数不随图像尺寸增长（全图共享一套规则）。
- 推理高度并行；自组织涌现（无全局协调器）；自修复 / 损伤鲁棒；尺度/分辨率泛化（最新可 8192×8192 推理免重训）。
- 理论根基：CA 图灵完备（Cook 2004）；能学真实 PDE。

**局限**
- 长程依赖弱：信息每步只传 1 cell，大图需极多步。
- 推理慢：需迭代 64–200 步；训练时间/显存随网格尺寸**二次方**增长，难 scale 大图。
- 训练不稳定 / 易发散；对超参（alive 阈值/fire rate/步数）敏感；可解释性有限。

**本组合台实证的坑（独家硬资产）**
- **浮点非确定性放大**：同 seed 两次 run 在 ep1 即落不同盆地；前列腺像素 NCA（128 步）λ_eff·S≈41，10⁻⁷ 扰动放大 ~5×10¹⁰ → Med-NCA 官方配置复现 **0/11 存活至 1000ep**。
- **静默发散 signature**：ep1 loss 死平 ~5.0（健康 ~1.25）+ 中期 Dice=0 → 不可恢复，立即 scancel。
- **弱更新 regime 下谱卡 1⁺**：残差更新 h_{t+1}=h_t+m⊙f(h_t) 的 Jacobian J=I+J_δ；近恒等初始化 + SN 让 J_δ 小，ρ/‖J‖ 都贴 1⁺，SN 只压到 1.007（−26%）。⚠️ 这是经验+regime 论证，**非**「L_f<1 数学不可达」（残差映射可收缩，见 PRIMER §6.4 修正）。
- **稀疏度相变**：fire_rate 存在尖锐功能塌缩边界（Hippocampus 单集 STABLE_SHARP），但 BraTS 不复现 → 非普适。

---

## 4. 怎么用（实操）

**典型结构（Growing-NCA 原版）**
- state grid：每格 16 维（前 4=RGBA 可见，后 12=hidden）；α>0.1 判活。
- perception：固定 Sobel 3×3 核对 16 通道做 x/y 偏导 + identity → 48 维。
- update MLP（1×1 conv）：48→128(ReLU)→16，**输出层零初始化**（do-nothing 初态），残差加回。
- stochastic mask：每格每步 fire_rate=0.5 概率更新（空间 dropout，异步性）。
- alive masking：更新前后都查 α>0.1 邻域，死格清零。
- 训练 loop：sample pool（1024）+ 随机跑 64–96 步 + L2 loss + **per-variable 梯度归一化** `grad/(‖grad‖+1e-8)`。

**默认超参**
| | Growing-NCA (TF) | Med-NCA (PyTorch) |
|---|---|---|
| channels | 16 | 32 |
| hidden | 128 | 128 |
| fire_rate | 0.5 | 0.5 |
| steps | 64–96 | 64 (inference) |
| lr | 2e-3→衰减 | 16e-4 |
| optim | Adam | Adam betas=(0.5,0.5) ⚠️非标准 |
| batch / pool | 8 / 1024 | 20 |
| loss | MSE(RGBA) | DiceBCELoss |
| total | 8000 steps | 1000 epoch |
| patch | 64×64 grid | 双级 (64,64)+(256,256) |

**主流开源**
- 官方 TF：`google-research/self-organising-systems` → `notebooks/growing_ca.ipynb`（Colab 免费 GPU，30min 出结果）。
- 医学：`MECLabTUDA/M3D-NCA`（入口 `train_Med_NCA.ipynb`，先跑 Medical Decathlon Task04_Hippocampus）。
- PyTorch 社区：`PWhiddy/Growing-Neural-Cellular-Automata-Pytorch`。
- JAX 高性能：`maxencefaldor/cax`（ICLR 2025 oral，快 2000×，含 attention-NCA）。
- 聚合：`MECLabTUDA/awesome-nca`。

**上手顺序**：读 Distill 交互文章 → 跑官方 Colab → 选方向（医学克 M3D-NCA / 大规模消融用 CAX）。

**高频踩坑**
- 梯度爆炸（同网络跑 64–96 次连乘）→ 用 per-variable L2 归一化，**不是** grad clip。
- alive check 必须更新前后都做，否则死细胞扩散。
- persistent/regenerating 必须用 sample pool，否则无持久性（去掉后 acc 46%→8%）。
- fire_rate=1.0 不稳；Med-NCA betas=(0.5,0.5) 别改回默认。

---

## 5. 本组合台 NCA 项目战绩（封存资产）

| 项目 | 状态 | 核心 | 结论 |
|---|---|---|---|
| **NCA-JEPA** | shelved P8 | NCA 替 ViT 做 JEPA latent 预测器 | 5 路线天花板全探明：稳定性可测（L_f，SN−26%）扎实但非惊艳；anytime 被 early-exit ViT 打平；抗遗忘证伪反转（等参更易忘 83%） |
| **NCA-PhaseMap** | shelved P6 | fire_rate 稀疏度→功能塌缩相变 | Hippo 单集 STABLE_SHARP，BraTS 三闸全 FAIL，非普适 |
| **Med-NCA 复现** | 封印转创新 | 四器官分割官方复现 | 官方配置 0/11 存活至论文规模，非 bit 级可复现 |

**关键档**：`project/meeting/Med-NCA/NCA-JEPA/{02_理论框架.md,04_LOG.md}`、`project/meeting/NCA-PhaseMap/05_Gate1_去留报告.md`、memory `reference_nca_divergence_signature.md`。

---

## 6. 数学理论完整推导

### 6.1 状态空间与更新算子
设网格 $\Omega \subset \mathbb{Z}^2$，每 cell $i\in\Omega$ 持状态 $h_i^t \in \mathbb{R}^C$（$C$=通道数，含可见 RGBA + hidden）。
全局状态 $H^t \in \mathbb{R}^{|\Omega|\times C}$。NCA 是一个**离散动力系统**：
$$H^{t+1} = \Phi_\theta(H^t),\qquad H^T = \Phi_\theta^{(T)}(H^0)=\underbrace{\Phi_\theta\circ\cdots\circ\Phi_\theta}_{T}(H^0).$$
关键：$\Phi_\theta$ 在所有 cell 与所有时间步**权重共享**（同一 $\theta$），故 NCA = 权重绑定的极深残差网（深度 $T$）。

### 6.2 单步算子分解（四阶段）
$\Phi_\theta = \text{Alive}\circ\text{Residual}\circ\text{Stoch}\circ\text{Update}\circ\text{Perceive}$。

**(a) 感知 Perceive — 线性算子.** 对每通道做固定核卷积（Sobel $K_x,K_y$ + identity $K_0$）：
$$p_i = \big[(K_0*h)_i,\ (K_x*h)_i,\ (K_y*h)_i\big]\in\mathbb{R}^{3C}.$$
写成全局线性算子 $P:\mathbb{R}^{|\Omega|C}\to\mathbb{R}^{3|\Omega|C}$，$p=PH$。Sobel 估一阶偏导 ⇒ 感知 = 离散梯度算子 $\Rightarrow$ NCA 内禀编码 $(\,h,\nabla_x h,\nabla_y h\,)$。

**(b) 更新 Update — 逐点非线性.** 共享 MLP $f_\theta:\mathbb{R}^{3C}\to\mathbb{R}^C$（如 $3C\!\to\!128\!\xrightarrow{\text{ReLU}}\!C$）：
$$\delta_i = f_\theta(p_i).$$
**最后一层零初始化** $\Rightarrow \delta_i\equiv 0$ at $t{=}0 \Rightarrow \Phi_\theta=\mathrm{Id}$ 初态（恒等映射，训练从稳定不动点起步）。

**(c) 随机掩码 Stoch.** 每 cell 独立 $b_i^t\sim\text{Bernoulli}(p)$，$p$=fire_rate（0.5）：$\tilde\delta_i = b_i^t\,\delta_i$。
**期望意义**：$\mathbb{E}[b_i^t\delta_i]=p\,\delta_i$ ⇒ 期望动力学 = 确定 NCA 的 $p$-缩放步长，即随机更新 ≈ 步长 $p$ 的异步显式 Euler；方差 $\text{Var}=p(1-p)\|\delta_i\|^2$ 提供正则（空间 dropout）。

**(d) 残差 Residual.** $h_i^{t+1}=h_i^t+\tilde\delta_i$。

**(e) 存活 Alive.** $h_i^{t+1}\leftarrow h_i^{t+1}\cdot\mathbb{1}[\max_{j\in\mathcal N(i)}\alpha_j>0.1]$（硬门控，分段连续）。

### 6.3 连续极限 → 反应扩散 PDE
取期望、令步长 $\Delta t=p\to 0$，残差步是显式 Euler：
$$\frac{h_i^{t+1}-h_i^t}{\Delta t}=f_\theta(h_i,\nabla h_i)\ \xrightarrow{\Delta t\to0}\ \partial_t h = F_\theta(h,\nabla h,\nabla^2 h).$$
**⚠️ 注意**：Sobel $K_x,K_y$ 给的是**一阶**偏导 $\nabla_x,\nabla_y$，反应扩散里的 $D\nabla^2h$（Laplacian）是**二阶**——单靠 Sobel_x/y 的线性组合**得不到** $\nabla^2$。原版 Growing-NCA 感知里**没有**显式 Laplacian。要严格得到扩散项，须**显式往感知核加 Laplacian**（许多 NCA 变体正是这么做）。故下式是**示意/理想化**，非从 Sobel-only 严格导出：
$$\boxed{\ \partial_t h = D\,\nabla^2 h + R_\theta(h)\ }$$
**Turing 反应扩散方程**（1952 morphogenesis）：$D\nabla^2h$=扩散（局部通信），$R_\theta$=反应（学到的非线性）。当感知含 Laplacian 时，NCA = 可学习反应扩散系统的有限差分离散，故继承「图灵斑图/自组织」表达力。

### 6.4 不动点与稳定性（核心：为何易发散 + L_f<1 不可达）
目标图案 $H^\star$ 是 $\Phi_\theta$ 的（近似）不动点：$\Phi_\theta(H^\star)\approx H^\star$。
持久性 ⇔ $H^\star$ **渐近稳定**。线性化单步 Jacobian（忽略 alive 门控、取期望）：
$$J=\frac{\partial \Phi_\theta}{\partial H}\Big|_{H^\star}=I+p\,\mathrm{diag}(f_\theta')\,P.$$
令 $J_\delta=p\,\mathrm{diag}(f_\theta')\,P$（更新部分的 Jacobian）。则
$$J=I+J_\delta.$$
**这是 NCA 稳定性的要害**（先分清两个量：**谱半径** $\rho(J)$ 管稳定性，**谱范数** $\|J\|=L_f$ 管收缩，恒有 $\rho\le\|J\|$）：
- 不动点**渐近稳定** ⟺ $\rho(J)<1$ ⟺ $J_\delta$ 全部特征值落进**以 $-1$ 为心、半径 1 的圆盘**。**可达**（$J_\delta$ 特征值取负实部即可）。
- **形式收缩** $L_f=\|J\|<1$（每步严格压缩，比稳定更强）**并非结构性不可能**：反三角 $\|J\|\ge|1-\|J_\delta\||$ 只说明「$J_\delta\to0$（弱更新）时 $\|J\|\to1$」，**不**排除 $\|J\|<1$——取 $J_\delta=-\varepsilon S$（$S$ 对称正定，$\varepsilon\lambda_{\max}(S)<2$）即得 $\|I+J_\delta\|<1$（i-ResNet 收缩流正是此例）。
- **诚实陈述**（替换早期「结构性不可达」的 overclaim）：在 **NCA 的近恒等初始化 + 弱更新 regime**（零初始化 + SN 约束让 $J_\delta$ 小、且更新方向不天然反向对齐）下，$\|J\|$ 与 $\rho$ 都**贴着 $1^+$**；本组合台 SN 把 $\rho$ 从 ~1.366 压到 ~1.007（−26%）是**经验观测 + regime 论证**，不是「$\inf\|J\|=1$」的硬定理。
⇒ 这仍是 NCA-JEPA 的「诚实负理论」根，但要说成「弱更新 regime 下 $\rho$ 卡在 $1^+$ 难再压」，**不能**说成「数学上不可能 $<1$」。

### 6.5 多步敏感性与发散（λ_eff·S 公式）
$T$ 步的端到端 Jacobian $\prod_{t=1}^{T}J^{(t)}$。沿轨迹的有效放大率由**最大 Lyapunov 指数** $\lambda$ 控制：
$$\|\delta H^T\|\ \lesssim\ e^{\lambda T}\|\delta H^0\|,\qquad \lambda=\lim_{T\to\infty}\tfrac1T\log\|\textstyle\prod_t J^{(t)}\|.$$
本组合台经验记为 $\lambda_{\text{eff}}\cdot S$（$S$=步数）：
- 前列腺**像素** NCA：$\lambda_{\text{eff}}S\approx 41 \Rightarrow$ 放大 $e^{41}\sim 10^{18}$，$10^{-7}$ 浮点扰动 → $\sim5\times10^{10}$ ⇒ 压垮信号、**双盆地**（同 seed 落不同解）、0/11 发散。
- **latent** NCA-JEPA：$S$ 从 128 降到 16，$\lambda_{\text{eff}}S<6 \Rightarrow$ 放大 $<e^6\approx400$，可控。
⇒ 控发散的两把手：降步数 $S$（latent 化）或压谱（SN 降 $\lambda_{\text{eff}}$）。

### 6.6 训练：BPTT 与梯度爆炸
loss $\mathcal L(H^T,H^\star)$ 对 $\theta$ 的梯度沿时间反传（BPTT）：
$$\frac{\partial\mathcal L}{\partial\theta}=\sum_{t=1}^{T}\frac{\partial\mathcal L}{\partial H^T}\Big(\prod_{s=t+1}^{T}J^{(s)}\Big)\frac{\partial \Phi_\theta}{\partial\theta}\Big|_{t}.$$
含 $\prod J^{(s)}$ ⇒ 同 6.5 的 $e^{\lambda T}$ 爆炸/消失。各项量级跨数量级 ⇒ Adam 失稳。
**官方对策 = per-variable 梯度归一化**：$g\leftarrow g/(\|g\|+\varepsilon)$（按参数变量分组），把每个变量的更新方向**单位化**，等效自适应学习率、解耦尺度，比全局 grad-clip 更稳（clip 只截上界、不修相对尺度失衡）。
**Sample pool** 数学意义：把训练分布从「seed 起 $T$ 步」拓成「不动点流形邻域的占用测度」，逼近 $\Phi_\theta$ 在 $H^\star$ 吸引域上的**不变测度**，故学到的不动点真稳（去 pool ⇒ acc 46%→8%，吸引域没学到）。

### 6.7 表达力：图灵完备与长程依赖下界
- CA 图灵完备（Cook 2004，Rule 110）⇒ 参数化 NCA 至少同等计算类，原则上 universal。
- **长程依赖的硬下界**：信息每步传播 ≤1 cell（感知核半径 $r{=}1$）⇒ 网格直径 $d$ 的两端通信**至少需 $T\ge d/r$ 步**。这是 NCA「大图慢、长程弱」的信息论根，非工程缺陷。Med-NCA 双级 patch、DyNCA 多尺度感知都是绕此下界。

### 6.8 一句话串起来
NCA = 权重共享的残差迭代算子 $\Phi_\theta=I+J_\delta$，其
（i）感知 = 离散梯度、连续极限 = 反应扩散 PDE ⇒ **表达力来自自组织**；
（ii）$I$ 项锚定恒等 ⇒ **训练易起步；弱更新 regime 下 $\rho,\|J\|$ 卡在 $1^+$ 难再压**（非「数学不可能 $<1$」，见 6.4 修正）；
（iii）$\prod J^{(t)}$ 的 $e^{\lambda T}$ ⇒ **既是发散源也是梯度爆炸源**，全靠降 $S$/压谱/梯度归一化/pool 驯服。

---

## 关键论文 / 仓库速查
- Growing NCA — https://distill.pub/2020/growing-ca/
- Self-classifying MNIST — https://distill.pub/2020/selforg/mnist/
- Self-Organising Textures — https://distill.pub/selforg/2021/textures/
- IsoNCA — arXiv:2205.01681 ｜ ViTCA(NeurIPS22) — arXiv:2211.01233
- Med-NCA — arXiv:2302.03473 ｜ M3D-NCA — arXiv:2309.02954 ｜ NCA-Morph — arXiv:2410.22265
- Diff-NCA(npj25) — nature.com/articles/s44335-025-00026-4
- 综述：From Cells to Pixels — arXiv:2506.22899 ｜ Hartl+Levin(Phys Life Rev) — arXiv:2509.11131
- 仓库：google-research/self-organising-systems ｜ MECLabTUDA/M3D-NCA ｜ maxencefaldor/cax ｜ MECLabTUDA/awesome-nca

## TODO（网搜未坐实，需人工确认）
- NCA 本身（非经典 CA）图灵完备严格证明
- NCA isotropy（Sobel 设计）各向同性数学推导
- NCA 超参敏感性系统量化研究
- 无 NCA+JEPA 公开专项论文（本组合台 NCA-JEPA 是自创方向，非复现已有工作）
