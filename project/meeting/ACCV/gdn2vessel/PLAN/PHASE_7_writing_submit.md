# PHASE 7 — 写作 + 对抗审稿 + 投稿

## ① 目标（锁定）
按章节弧写成 14 页 LNCS，related work 硬区分 GDKVM，CV 方法贡献叙述到位，数字三方对账 0 偏离，对抗审稿 0 致命，双盲合规后投稿（顶会优先，ACCV 保底）。

## ② 入口依赖
P3/P4/P5/P6 实验全收口、数字落 csv。

## ③ 任务清单
1. **写作**：按 STORY_FRAMEWORK §1-§7 章节弧写（caveman OFF）。数字只用 verifier 核过的值。
2. **related work 硬区分 GDKVM**：用 R3 固定模板（时序 vs 空间 + GDN-2 vs 早期 GatedDeltaNet）。
3. **CV 方法贡献叙述**：新机制/原理/benchmark 先行，医学=validation（避被读成换模块/纯临床）。
4. **数字三方对账**：registry ↔ STORY 锁定表 ↔ tex 逐条核（`/pre-submit-check`）。
5. **对抗审稿**：reviewer 十角色 + skeptic 攻 claim 逻辑 + 反跑偏审计。
6. **脱敏双盲**：机构/lab/链接全删，grep 自引/匿名残留。
7. **Code release** + 复现骨架（双盲匿名）。
8. **编译**：pdflatex×2 + bibtex + ×2，0 error / 0 undef，≤14 页。

## ④ ACCEPTANCE 硬阈值（不妥协）
- [ ] related work 含 GDKVM 区分句（grep 确认）
- [ ] 数字三方对账 0 偏离（每续连/re-ID 数字附统计，Dice/clDice 附 seed std）
- [ ] reviewer 十角色 0 致命 issue + skeptic 攻 claim 通过
- [ ] 防御写法 R1-R7 全过（grep "universal"/"always"/"prove" 0 误命中）
- [ ] 双盲脱敏合规 + 编译干净 + ≤14 页
- [ ] **拍板点**：投稿（venue 二选）

## ⑤ 自由发挥区
叙述措辞、图表布局、supp 篇幅、venue 最终选择（顶会 vs ACCV，依实验强度报用户拍）、rebuttal 预案。

## ⑥ 跑偏定义 / 红线
- ❌ related work 不区分 GDKVM
- ❌ 数字凭印象 / 与 csv 不一致
- ❌ 绝对化 claim（R1/R2）
- ❌ 双盲违规（机构/链接残留 = 不送审直接拒）
- ❌ scan 写成贡献 / 纯临床故事撑录用

## ⑦ 退路 + 派谁 + 出口 gate
- 退路：实验强度不够顶会 → 降投 ACCV 保底（venue 弹性，用户拍）；reviewer 致命未解 → 不投，回补实验。
- 派谁：`verifier`（核数）→ `writer`（写章节）→ `reviewer`（对抗审）流水；缺引用补 `researcher`。投稿主线串行（拍板点）。
- **出口 gate**：硬阈值全 PASS + 用户拍板投稿 → 投稿，更新 registry/PORTFOLIO。
