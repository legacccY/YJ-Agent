# WardAgentBench — ACCEPTANCE（探路阶段 GO/NO-GO 判据）

> 本阶段不是「论文验收」，是「值不值得投论文」的探路判据。任一 kill-shot NO-GO → 停下报，诚实退回「纯 SOP 临床合作素材」不投论文（符合低优先定位）。

## KS-1 · 路线选择 + 差异化红队 ✅ 已过（2026-07-02 skeptic 裁决）
- **结论**：**选路线②重定位 + 组合**（腿 B 承重 = 部署系统实证 + 腿 A 开源实现 + 腿 C feasibility）。路线①作承重实证 claim 判**致命**（四角色数据结构性不支撑）→ 降腿 A 不带实证 claim。详见 `01_STORY.md` 核心 claim + 致命伤记录。
- **最小可辩护 claim**：边缘延迟(<5ms)+双轨告警部署约束下，公开 ICU 数据(MIMIC-IV/eICU)实证多并行轻量体征告警器的延迟-精度前沿 + 误报复合效应 + 简单缓解 + 开源 ward-agent 参考实现。

## venue/niche 大编队侦察 ✅ 已过（2026-07-02，5 researcher + skeptic）
- **方向升级**：路线② → **候选 B（多告警器复合误报联合校准 benchmark + e-value 依赖稳健校准）**，冲 SCI 一区。
- **venue 双靶**：IEEE JBHI（一区现实）/ npj Digital Medicine（一区冲刺）/ D&B-workshop / JMIR（保底）。NeurIPS E&D 主 track 低概率不押。
- 详见 `reference/RECON_2026-07-02_venue_niche.md`。

## KS-2 · 数据可达性（0 算力，即刻启动，2 周提前量）
- **KS-1 后优先级调整**：腿 B 主吃 **MIMIC-IV / eICU**（PhysioNet credentialed + CITI「Data or Specimens Only Research」+ DUA，审核数天~2 周）→ **CITI 照办不拖**。MedDG/CBLUE 只服务腿 A 开源实现，license 压力小。
- **动作**：用户线下办 CITI + PhysioNet credentialing（见 `reference/CITI_PHYSIONET_CHECKLIST.md`）。
- **✅ GO**：MIMIC-IV 或 eICU 可合法获取，认证流程已启动。
- **❌ NO-GO**：认证被拒 / 数据全不可得 → 退腿 A 开源 + SOP。
- **注**：CITI 认证是用户本人线下动作（需实名 + 邮箱），主线只出 checklist，不代办。

## 🔴 KS-3 · 数据命门 kill-shot（<1 GPU·h，CPU 可，候选 B 生死点，动笔前必跑）
依赖 KS-2 拿到 MIMIC-III/IV Waveform Matched。按 Chromik et al.「Extracting Alarm Events from MIMIC-III」法派生多阈值告警共触发 + **书面登记的结局代理**（如 X 分钟内恶化）定真/假。R2 held-out 固定 seed 不混训练。三问：
1. 多告警是否**真以有意义频率 + 相关性共触发**（非罕见事件）？
2. 复合 FAR 效应在 **≥2-3 组合理阈值族**下是否稳健（换阈值不翻）？
3. 确认 PhysioNet 2015 五类标签**无法**供共触发标注（锁死单告警结论）。
- **✅ 三问全过 → GO**：派 planner 出 benchmark 实验矩阵 + coder 建 harness，升 status=active，靶 JBHI/npj DM。
- **❌ 任一翻**（现象随阈值翻转 / 共触发罕见 → 自造 artifact）→ 退腿 A（开源 ward-agent 参考实现）+ SOP 素材，不硬撑（符合低优先诚实定位）。
- **命门理由**：中心对象「多告警共触发+逐告警真假」公开数据不带标注存在，须自合成 → 防自造现象（[[delta_statetrack]] 坑）。

## KS-4 · venue 现实核对（0 算力）
- **动作**：确认 JMIR Formative 投稿流程 + ML4H 2026 Findings 确切截止（9 月查官网），锁 1-2 现实目标。
- **✅ GO**：至少 1 个现实 venue + 明确截止 / 滚动政策。

## 全过后
KS-1~4 全 GO → 派 `planner` 出正式实验矩阵 + `writer` 起 outline，升 status=`active`（低优先）。这是**新阶段拍板点**，届时报用户定投入。

## 依赖 DAG
KS-1（选路）→ KS-2 & KS-4（可并行）→ KS-3（依赖 KS-1 选路 + KS-2 拿数据）→ 全过 gate。
