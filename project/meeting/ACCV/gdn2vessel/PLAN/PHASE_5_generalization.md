# PHASE 5 — 泛化 / 跨域 / 跨器官（全做满，允许 1-2 边缘集失败）

## ① 目标（锁定）
把方法推到冠脉/OCTA/跨域，证「记忆续连」不是视网膜专属，达成数据集 ≥10 的碾压覆盖 + 跨域泛化「眼前一亮」。

## ② 入口依赖
P3 PASS（主集方法立住）。可与 P4/P6 并行。

## ③ 任务清单
1. **冠脉（跨器官管状）**：XCAD / DCA1 / CHUAC + 冠脉 baseline（如 EAG）。
2. **OCTA 血管**：OCTA-500 / ROSE + OCTAMamba baseline 必跑。
3. **跨域（附录泛化）**：裂缝 Crack500 / 道路 Massachusetts Roads。
4. **跨域协议**：FIVES→{DRIVE,STARE,CHASE,HRF}（一训测四，文献最强 source）+ DRIVE→CHASE/STARE 经典。
5. 三轴指标 + 断点续连 benchmark 推广到冠脉/OCTA。

## ④ ACCEPTANCE 硬阈值（不妥协）
- [ ] ≥10 集覆盖（含主集）
- [ ] 跨域不崩（FIVES→4 集 + DRIVE→CHASE/STARE 有合理迁移）
- [ ] 冠脉/OCTA 上方法可跑且不输对应专用 baseline（边缘集允许 1-2 失败）
- [ ] 数字核 csv

## ⑤ 自由发挥区
哪些边缘集深做、跨域附录做多大、是否加更多跨器官集、是否在跨域上也跑断点 benchmark。

## ⑥ 跑偏定义 / 红线
- ❌ 许可证未确认就纳入发表数据
- ❌ 跨域调参作弊（跨域必须 source 训 target 直测，不在 target 调参）
- ❌ 边缘集失败硬撑伪造数字（允许失败，诚实标注）

## ⑦ 退路 + 派谁 + 出口 gate
- 退路：边缘集（冠脉/OCTA/跨域）允许 1-2 失败（kill 放宽）；下载源失效先问用户（铁律）。
- 派谁：数据/脚本派 `coder`；HPC 上传新数据拍板（主线先报）；主线跑训练 4 卡并行；`analyst` 解读。
- **出口 gate**：≥10 集 + 跨域不崩 → 收口进 P7。
