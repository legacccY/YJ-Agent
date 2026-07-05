# BMVC 2026 Rebuttal 工作日志

> 论文《Quality-Conditioned Temperature Scaling》已封印（SUBMITTED.md）。rebuttal 是合法路径，所有产物只落本 `rebuttal/` 子目录，绝不改投出稿。

---

## 2026-07-04 ⚡ Rebuttal 决策 + 弹药盘点 + 数字核实 + 起草

### 审稿结果（rebuttal 窗口 07-03~07-10 AoE）
分数 **5(8hpP) / 4(6xgi) / 3(isv7) / 3(XHFa)**，满分 6，中线 3.5，**均分 3.75**（录取线 4 下一点，偏正活稿）。
- 8hpP(5, conf3)：Std VIB 近随机头条 / reversal=VIB MC 现象过度概括 / 纯合成 QCTS 没测真实 LQ / 闭环结构增益 / 缺 re-marginalize baseline
- isv7(3, conf3)：backbone-dependent / Std VIB 弱 / QCDI 奖励 HQ 退化 / QCTS 不提升 AUC / 合成 vs 真实 / 5维IQA分开没测 / IQA 没对专家验证 / **T0α 稳定性未报**
- XHFa(3, **conf4**)：缺 submission ID / 无核心贡献 / IQA 细节不清 / 阈值 0.45/0.50 无依据 / ITB 为何多退化类型
- 6xgi(4, conf3)：温和，要求讨论 weakness

### 决策：**反驳，不撤稿**（skeptic 0 致命放行）
死结反证：把 Std VIB 批评讲最狠的 8hpP 给全场最高 5 分 → scope 争议非 reject 引擎。reject 压力=isv7+XHFa。**目标=拱 isv7 3→4，均分→~4.0 进 AC 可捞区**。

### 战术骨架（skeptic 定）
主武器=**指回论文自带 §6 A1–A6 预答节 + 只补增量**（非从零重建）。火力集中 isv7；XHFa 只最短事实纠错+Prop1 一句；8hpP 轻致谢指回 A4。
**3 处停止过度认怂**：① ImageNet-C 讲 18/18+配对检验（方向普适），别自贬「不显著」② 真实性讲 A1 的 174 真实图，别裸认全合成 ③ Std VIB 弱=by-design 可修复原型，别认 flaw。
**边界铁律**：头条幅度（73% QCDI 降/LQ ECE 减半）确 Std-VIB-specific，ImageNet-C 救**方向不救幅度**，rebuttal 不越界。

### 范围决策（用户拍板）
「加 HPC 拉数据」档。**HPC 实检结果**：`efficientnet_features.npy`/`abcd_cache.csv`/`quality_labels_all.csv` 本地+HPC **两头都没有**；只 `quality_labels_nocrop_hpc.csv`（训练池变体）在 HPC。→ E3 完整 per-dim 网格 + 主 Std-VIB 从零重拟合**不可行**，走降级（引 §A12 Dimwise + 现存 seed std）。**不写 AC 机密备注**，XHFa 误读正文纠错。

### 新实验（缓存数据，零训练，coder 写主线跑）
- **E1 T0/α 稳定性**（`rebuttal/scripts/qcts_stability.py`，复用论文 `fit_qcts` 零偏离）：4 backbone bootstrap。**结果**：α 本身不稳（CV 36–133%，=§A18 flat landscape），但**下游 ECE-LQ 稳**（CV ResNet3.0/ConvNeXt12.1/Swin4.2/ViT7.9%）。诚实答 isv7⑧=「α 弱可辨识但交付校准 robust」。QCDI 太噪（sign 不稳）**不用**。
- **E2 qbar 阈值分布**（`qbar_distribution.py`）：LQ 100%<0.45/HQ 100%>0.50 但**循环**（子集按阈值切）→ 阈值合理性靠 §A10 敏感性撑，直方图仅辅助。

### 数字底座（verifier Bash 核实，rebuttal 只用这些值）
| # | 值 | 位置 | 坑 |
|---|---|---|---|
| ImageNet-C | 18/18 两 backbone QCTS 更负；TS 惰性 18/18；**新增 Wilcoxon p=3.81e-6** | csv 实测 | ⚠️Wilcoxon 只在孤儿 table_imagenetc.tex 未进投出稿→写「新增分析」不写「论文已述」 |
| re-marginalize | ρ_a(MC-marg)=**−0.163**, ρ_b=+0.241, Δ=+0.404 | 正文 **§5.2 Eq.(5)** line173 + supp **§A20** | ⚠️别引 Table 1（那是 −0.153） |
| 真实 LQ | EffNet-B3 ECE **0.073**[0.038,0.125]<ITB-LQ 0.146 同向 | 正文 line232 §6 A1 | ⚠️**106 ISIC+68 Fitzpatrick** 非「174 ISIC」；真号 **§A8** 非正文写的 A7 |
| Table 3 flip | ViT(DeiT)/ConvNeXt/Swin raw_qcdi +0.023/+0.136/+0.020→ts −0.029/−0.022/−0.021；AUC-HQ 0.92–0.94 | section54_summary.csv DeiT 行 | ⚠️Swin qcts_qcdi 仍 +0.016→用「toward zero」 |
| E1 下游 | ECE-LQ CV 3–12% 稳、α CV 133% 不稳 | rebuttal/results | 逻辑审计 PASS 无泄漏 |
| §A18 | α∈{0.34,0.96,0.37}, ΔNLL | supp §A18 真号 | ⚠️界写「<0.002」不写「<0.0012」 |
| taxonomy | Std VIB=Quality-Fragile(0<QCDI≤0.10)可修复档 | 正文 line95 §3.2 | 明确归此档 |

### ⚠️ 投出稿自相矛盾（reviewer 对抗审逮出，Bash 定案）
real-LQ 集**投出稿内部就打架**，rebuttal **绝不选边、不提构成**：
- **§A8**（itb_supp.tex:447）+ 正文 A1（itb_paper.tex:233）：写「**174 全 ISIC**，blur37/combined50/dark50/other37，全良性」
- **§A22**（itb_supp.tex:852）+ `real_lq_inference.json`：写「**106 ISIC+68 Fitzpatrick**」，且 `rho_direction_same:false`（real-LQ ρ=**+0.446** vs ITB-LQ ρ=**−0.029** 符号相反）
→ rebuttal 定稿只写「174 real-world LQ images, ECE 0.073 vs 0.146（supp real-LQ table）」，**不写构成、不写 same-signed、不写硬 §号**（§A7/A8 也打架）。这是投出稿的病，rebuttal 不碰。

### reviewer 对抗审修正（本轮，已落 response_body.tex）
- 🔴 real-LQ 删「106+68 Fitzpatrick」+「same-signed」+ §A8 硬号（own-goal，撞投出稿）
- 🟠 α 段从「Honestly...weakly identifiable...loosely pinned」忏悔式 → 等效性 robustness（「any nonzero slope suffices, consistent with Prop 1」），消与 novelty 段内耗
- 🟠 补 IQA 指针块（isv7⑦/XHFa③）：§A2 mean SRCC 0.895 + 均值 rationale + 「QCTS 不 hinge on 模块（外部 ImageNet-C 标量也成立）」
- 🟡 「a new Wilcoxon」→「a Wilcoxon」（去 new 避 AC 视作加新贡献）；ViT ρ −0.139→−0.210 精修为 −0.138→−0.209
- 保留 XHFa「两 backbone」纠错（reviewer 误判，XHFa 原文确写 "two different backbones... ViT and ConvNet"）

### 进度
- ✅ 探路(3 Explore)+红队(skeptic)+核数(verifier)+E1/E2 跑完+writer 起草+reviewer 对抗审(修 1 reject 级 own-goal)
- ✅ **完整 `rebuttal.tex` 本地生成 + 编译成 `rebuttal.pdf`**（TeX Live 2025 在 E:\texlive；用官方 bmvc2k.cls review 去标题模式，单栏）。**1 页、0 error、0 overfull**（修了 ResNet/ViT/ConvNeXt/Swin 长串戳边距）。cls+sty 已拷入 rebuttal/ 自成一体。
- ⏳ **仅剩用户**：① `rebuttal.tex` 里 `\bmvcreviewcopy{??}` 填 BMVC 投稿号（顺带堵 XHFa「缺 submission ID」）② 手动 OpenReview 上传 `rebuttal.pdf`（拍板点，窗口 07-10 AoE 前）
- 编译命令：`cd rebuttal && /e/texlive/2025/bin/windows/pdflatex.exe -interaction=nonstopmode rebuttal.tex`
