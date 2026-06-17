# run-002 漏斗台账（医学影像·方法创新型）

> 5 分钟看懂这轮怎么从批量候选收敛到 G5。只增不删,被砍留 reason。

## 漏斗数字

| 闸 | 入 | 出 | 通过率 | 方法 |
|---|---|---|---|---|
| G0 宪章 | — | charter锁定 | — | 全模态开放挖·方法创新型(CVPR/MICCAI/NeurIPS)·70/30稳健·≤两周中训 |
| G1 批量产出 | 6策略×ideator | **116 raw → 73 live**(41 merged) | 63% | S1-S6 正交扇出+语义聚类去重(24簇) |
| G2 机器硬筛 | 73 | **22** | 30% | R1二元kill(硬排除NCA/撞组合台/超算力/纯分析) |
| G3 评分排序 | 22 | **8** | 36% | 5×researcher撞车核验+InnoEval;**12条撞2025-26新论文killed** |
| G4 红队 | 8 | **7** | 88% | skeptic红队+pre-mortem;KILL 1(S5-08撞车成片) |
| G5 杀手锏 | 7 | **1**(S2-03 GREEN) | 14% | <1GPU·h证伪RAT;6 证伪/blocked,仅 FM 配准扛过 |
| G6 立项 | 1 | **1 单苗待拍板** | — | 双venue+书面kill criteria→🛑用户拍板(见 07_report/G6_proposal_card.md) |

## G3 撞车 killed(researcher 实证,2025-26 新论文直击)

S6-02(VesSAM Nov25)·S6-14(MAFF-Net Nov25)·S6-04(ARCD/CCD/VGS三篇)·S4-18(SLIMP May25)·S3-08(PL-DC)·S6-13(CXR-LT生态)·S4-02(Fitzpatrick Thresholding)·S6-12(UM-SAM)·S6-03(频域拥挤)·S1-06(MedPEFT-CL)·S3-12(CoDyRA)·S4-01(降备胎)

## G5 7 幸存(带杀手锏闸,详见 05_screening/G4_redteam/G4_verdict.md)

**0 致命 PASS**：S4-05(VinDr分歧检测不确定)·S2-12(lesion-aware MAE)
**0 致命 CONDITIONAL**：S2-17(TTC scaling分割)·S1-08(TTA停适监控)
**🔴带先验生死闸**：S2-03(FM配准/雅可比闸)·S6-18(病理跨染色/数据闸)·S5-10(do-calculus公平/泄漏闸)

## G5 进行中（用户拍板：先只跑🔴三闸，一票否决）

- **S6-18 病理跨染色**：数据闸 EXISTS(ACROBAT/BCI/ANHIR 免费可下)不塌,但 researcher 顺手抓出 **CSCL(2512.03577 Dec25)直接撞 90%**(ACROBAT+CONCH+patch InfoNCE 适配 IHC),残余=换组织/UNI2/LoRA 仅 incremental → **改判 KILL on collision**(方法新颖性塌非数据塌)。
- **S2-03 FM配准雅可比闸 → 🟢GREEN PASS**：`neg_jac_pct=0.00% | dice_fm=0.9279 > dice_aff=0.8384`(results/killshot_s2_03_jacobian.csv)。单步形变 0% 拓扑折叠+胜仿射,skeptic 的🔴"FM≠形变场范畴塌"快测不成立 → **S2-03 存活**(注:FM target 简化代理,几何雅可比属性是关键已干净)。
- **S5-10 do-calculus泄漏闸 → 🔴RED KILL**：`leak_ratio=1.8662 > 0.5 | corr_with_ITA=0.394 | lesion_region_change=0.054 > bg_change=0.029`(results/killshot_s5_10_leakage.csv)。β-TCVAE 干预肤型维显著扰动 lesion 区像素(>背景 1.9×)→ 解耦泄漏坐实,do(skintone) 污染诊断 → **S5-10 塌**。
- **🔴三闸出齐总账**：S2-03 GREEN 存活 | S5-10 RED 塌 | S6-18 KILL(CSCL撞车) → 🔴组 3 进 1。
- 剩 4 个非🔴(S4-05/S2-12/S2-17/S1-08)续 G5 杀手锏(数据 HAM/BraTS/NIH+VinDr 本机ready;S4-05 需逐医生标注待核)。

## G5 完成总账（2026-06-17，4 非🔴 killshot 全跑完，verifier 核 csv 自洽）

> S2-12/S1-08 因 local GPU 被 iclr 占，用户定「HPC 跑」→ tar 上传 HAM/NIH/VinDr 到 gpu4090 并行 sbatch（job 1453112/1453382），跑完拉回 csv。

| 候选 | killshot 读数(csv 原值) | 判决 |
|---|---|---|
| **S2-03** FM配准 | neg_jac_pct=0.0000, dice_fm=0.9279>dice_aff=0.8384 | 🟢 **GREEN 存活** |
| S2-17 TTC scaling | rho_score=-0.0303 < rho_baseline=0.7455 | 🔴 RED KILL(输平凡方差基线) |
| S2-12 lesion-MAE | mean_delta=-0.0083, CI95[-0.0273,0.0106]覆盖0 | 🔴 RED KILL(引导 masking 无增益) |
| S1-08 TTA停适 | peak_step=-1, monotonic=True | 🔴 RED KILL(AUC 单调无过适应峰=伪问题) |
| S4-05 reader分歧 | n_images=0(VinDr 缺逐医生 bbox) | ⚠️ BLOCKED(数据缺,非证伪) |

**G5 终局 7→1**：S2-03 GREEN 唯一存活；S5-10/S6-18/S2-17/S2-12/S1-08 共 5 证伪；S4-05 BLOCKED。
**→ G6 立项卡见 `07_report/G6_proposal_card.md`（🛑 单苗待用户拍板）。**

## 历史下一步 🛑 G5 拍板点

G5 = 跑 <1GPU·h 杀手锏证伪(本机4070或HPC单卡)。数据就绪度差异：
- 本机ready即跑：S2-12(HAM)·S5-10(Fitz+HAM)·S1-08(NIH→VinDr)·S2-17(BraTS)
- 需小下载：S2-03(OASIS脑配准)·S6-18(先查IHC配对数据≈零GPU)·S4-05(VinDr三医生需physionet申请,有延迟)
