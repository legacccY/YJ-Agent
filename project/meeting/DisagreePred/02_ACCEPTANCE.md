# DisagreePred — ACCEPTANCE CRITERIA

> 验收判据 + 书面 kill criteria 唯一真源。改阈值 = 拍板点。2026-06-18 立项首版（源 G6 charter C065 R7）。

## 核心验收判据（投稿前必须全过）

- **A1 分歧可预测（gating，最硬，方案甲）**：**在 k≥1 区内**（至少 1 医师标注的位置），模型从图像预测专家是否分歧（k∈{1,2,3} vs k=4）AUROC **> 0.60**（显著高于随机），且高分歧预测区与真实专家分歧区空间对齐。⚠️ 禁掺 k=0 负样本（避结节检测 leakage，2026-06-18 skeptic 红队定）。⏳ KILL-1，下 LIDC 后首跑。
- **A2 优于平凡基线**：分歧预测优于「用模型自身 UQ（熵/MC-dropout）当分歧代理」——证明预测的是专家间分歧而非模型自身不确定。⏳ 立项后。
- **A3 framing 差异化坐实**：与 EDUE / disagreement-guided 在任务定义层面切清——本文目标 = 预测 P(分歧)，对手 = 用分歧辅助别的目标。related work 显式对照。
- **A4 普适性 / 临床价值**（顶会前置）：第二多标注集（QUBIQ）复现 + deferral 实验（高分歧处转人工能提整体可靠性）。⏳ standout 升级。

## 雄心档位（诚实分级）

- **退路档达标线（MedIA / UNSURE / D&B）**：A1 + A2 + A3 + 单集（LIDC）诚实标注 = 分歧可预测的首个正面证据，站得住。
- **顶会升级线（MICCAI 2026）**：再 + A4（QUBIQ 第二集 + deferral 临床价值）= framing 新 + 实证扎实 + 临床落点。

## 书面 kill criteria（立项即生效，触发即诚实回退）

- **KILL-1（实证 · gating，最优先）**：下 LIDC 后跑分歧可预测性 baseline，预测 4-annotator 分歧 **AUROC ≤ 0.60**（近随机）→ 核心 claim 死，砍。复查：数据就位后首轮 2 周。**立项后首要动作，先验后大投入。**
- **KILL-2（撞车）**：disagreement-predictor-as-target 被 EDUE(2403.16594) / 2510.10462 系列先发覆盖，差异化压缩到无 → 重定位或砍。
- **KILL-3（理论）**：若 LIDC 分歧本质纯随机不可从图像预测（KILL-1 实测即验）→ 砍。
- **KILL-4（资源）**：> 50 GPU·h 仍无信号 → 停。
- 复查节奏：每 2 周。签字：用户 legacccy / 2026-06-17。

## 复现红线（全程）

- LIDC 分歧标签构造按 4-annotator 原始标注真实计算（margin / 存在性投票），禁私造分歧定义凑信号。
- 数字一律 Bash/Grep 核 csv，入文前过 verifier，不信 Read。
- claim 措辞守 STORY 红线：预测分歧 ≠ 用分歧辅助；可预测须 KILL-1 通过且有读数才写。
