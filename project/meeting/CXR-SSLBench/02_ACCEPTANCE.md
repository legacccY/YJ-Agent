# CXR-SSLBench — ACCEPTANCE（二元 PASS/FAIL 验收）

> 原则：每条判据二元化（PASS/FAIL），不存在「基本完成」。半天级大阶段收口跑 `/stage-gate cxr-sslbench`。
> 数字一律 Bash/Grep 核 `results/*.csv`，不信 Read。

## Lever 分解（承重 claim → 可测判据）

| Claim | Lever（怎么证） | 硬阈值 PASS 条件 |
|---|---|---|
| C1 无单一最优（**双向预登记**） | Friedman 检验 + Nemenyi CD 图，跨 regime 排名 | **两向均 PASS（受控重训前预登记，防 HARKing）**：**向 a**=洗牌存活（Friedman p<0.05 且至少 1 对范式排名跨 regime 翻转，多 seed CI 显著）→ 结论「范式选择 regime 依赖」；**向 b**=洗牌消失（受控后范式趋同）→ 结论「野外观察到的 SSL 范式差距是语料/配方 artifact、非范式内禀」。两向都是 publishable finding，C1 不依赖强制 rank flip。承重重心摊 C1+C2+C3，不让单条 0.3 点级翻转扛大梁。 |
| C2 数据效率 gap | 1/10/100% mAUC 曲线，范式间极差 | 范式间 mAUC 极差在 **1% 标注 > 100% 标注**（gap 随标注量单调收窄） |
| C3 probe-finetune 解离 | WM(CheXWorld) linear vs finetune 相对排名 | CheXWorld linear 排名**低于**其 finetune 排名（probe 协议改变范式相对位次） |
| C4 跨域退化因范式而异 | NIH→VinDr/CheXpert 跨域 ΔmAUC 按范式 | 跨域掉点幅度范式间显著分化（无统一鲁棒冠军），至少 1 范式相对位次跨域翻转 |

## stretch（不达不回退主贡献）

| Claim | Lever | PASS（达则加分） |
|---|---|---|
| C5 方法 fix | CPF-Gate/ReStat 在预登记 failure cell 上 ΔmAUC | failure cell 上显著 >0（DeLong p<0.05）；不达 → 诚实标 negative，主贡献 C1–C4 独立成立 |
| C6 鲁棒/校准 | 腐蚀曲线 + 罕见病理分层 + ECE | 出可复现的范式分化 finding（方向一致即 PASS） |

## 阶段硬阈值

### ✅ Phase 0 / Gate1（已 PASS，2026-06-30）
- 苗头可见且方向一致：C1 排名洗牌（低标注 MAE 领先→100% rad_dino 反超，CheXWorld 第 2 掉第 3）；C3 mini（CheXWorld linear 中游，MAE 三档压一头）。
- 无泄漏：held-out test=25596，n_train 随 frac 正确缩放。
- 重训路径清：plan 估 ~1000 GPU·h，4 范式权重 HPC 可下，env 就绪。
- **判定：PASS** → 进全盘，正式登 registry。
- 真源：`results/pilot_hpc.csv`（job 1502033 COMPLETED）。

### Phase 1 — 受控重训（**A′ 混合受控**，2026-06-30 拍板）
- **A′ 定义**：控住「数据(NIH 112k) + backbone(ViT-B/16) + 计算预算（按 GPU·h 或 images-seen 预登记，**不按 epoch**——batch 差异会偷换 images-seen）」；放开「batch/lr/temp/mask_ratio/稳定性开关 各按官方冻结」（DINO temp warmup+fp16 off、MoCo stop-grad-conv1+lr 1e-4、MAE mask 0.90）。预登记一句「batch 因方法而异是构成要素非疏漏」+ 每范式 images-seen 表。
- **否决纯 A**（强制同 batch/epoch = 方法构成要素混杂，C1 被判调参不公，skeptic 🔴）。**否决 B 作 headline**（非受控、差异化反噬）。**C 仅作 collapse 压不住后备**。
- **投全预算前必做**：DINO/MoCo 各跑 1 个小规模 collapse 烟测（监 KL/teacher entropy），确认能起再投。
- **🆕 reduced-batch 预登记（2026-06-30 路A 拍板）**：4×4090 装不下 DINO/MoCo 官方 eff_bs(512/4096) → DINO/MoCo 用 reduced eff_bs（4090 可容 per-GPU batch）+ lr 线性缩放(lr×eff/official_eff_bs)，images-seen 不变；MAE/CheXWorld accum 凑满官方 eff_bs。诚实标 limitation，对齐 A′「eff_bs 是方法构成要素放开」。非复现偏离（学界有限算力横评标准做法 solo-learn/VISSL）。
- PASS：5 范式在 NIH 112k 按 A′ 收敛（无 collapse），预算/seed/images-seen 记录在案。
- FAIL 退路：某范式 collapse 压不住 → 退公开胸片权重并诚实标 mismatch；差异化改写「N/5 范式同语料受控重训 + 余者公开权重标 mismatch」，不绑死 5/5 全自训。

### Phase 2 — 全评估矩阵 + C1–C4
- PASS：5 范式 × 3 集 × 1/10/100% × {linear/attentive/knn + finetune} × 3–5 seed 跑齐；C1–C4 四条**全部**达上表硬阈值；统计（Friedman+CD+DeLong+Holm）齐备。
- 跑完**先冻结 failure cell 定义**（预登记，R6 防 HARKing）再做方法。
- FAIL：任一承重 claim 不达阈值 → 停下报，按结果如实改 STORY（不硬撑、不挑 cell）。

### Phase 3 — 方法 + 鲁棒（stretch）
- C5/C6 按 stretch 表；不达不回退主贡献。

### Phase 4 — 写作 + 投稿
- 投稿前 `/pre-submit-check`：数字三方对账（csv↔registry↔tex）+ 脱敏 + 图验证；与任何主论文重叠 <30%。
- venue 待 Phase 2 真信号后拍（顶刊 PR/TMI 接受最终录用滑 2027 Q1，或 benchmark 友好场拿 2026）。

## 红线（违即 FAIL，不放行）
1. 数字非 csv 实测（臆造/Read 当真）。
2. 超参非官方源（臆想 lr/配方）。
3. 复现有偏离（私加裁剪/降 lr/改步数凑收敛）。
4. 评估泄漏（probe/test 患者重叠、跨域拼训练集）。
5. 为方法涨点挑 cell 或改 benchmark 设计（违预登记）。
