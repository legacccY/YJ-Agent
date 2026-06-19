# SelInfBench → BIBE 2026 论文 BUILD MAP

> 投稿目标：IEEE BIBE 2026（DDL 用户称 2026-06-24，官网未核实需用户确认；IEEE 双栏 10pt，full 8 页）。
> 本文档 = 每个章节 ↔ 验收判据 ↔ **本地可核 csv 数字来源** 的钉死表，防 HARKing / number drift。
> 数字铁律：只用本地 Bash/Grep 可核的 csv 值；无源数字一律标 🚫 不准入稿。

## venue 决策留痕
- 2026-06-19 用户拍板：SelInfBench 从 TMLR/D&B 降档投 BIBE 2026（EI/IEEE，中稿率高）。资产已撞顶会天花板（A3 仅 2/3），EI 量级正合适。
- K2 撞车复查 🟢 不撞（researcher 2026-06-19）：无人先发「selective inference 校正医学影像 benchmark winner's curse」同 claim。

## 数字来源钉死表（全部本地可核）

| 证据 | 数值 | 来源 csv（本地） | 状态 |
|---|---|---|---|
| **A1 偏差可测**（用 truthproxy，**不用无源 0.7467**） | HAM val_best 0.9283 → test_selected 0.8536，winner's curse **+0.0746** | `results/a3_truthproxy.csv` HAM 行 | ✅ 可核 |
| **A1 补强：HAM winner's curse bootstrap CI** | test_selected bootstrap CI 下界须 >0（证 +0.0746 非抽样噪声） | 待 coder 加 `a3_bootstrap_coverage` 算 | ⏳ 补做 |
| A1 旧 headline 0.7467>0.7330 | — | HPC `c025_deflation.csv` **未回传本地** | 🚫 无源，禁入稿 |
| **A2 覆盖率破裂**（真区制 σ_mu/σ=0） | naive 覆盖 0.7935(M=18)/0.715(M=36)，点偏 +0.0266/+0.0298 | `results/coverage_sim_v2.csv` | ✅ 可核 |
| **A2 data fission 修回** | df 覆盖 0.9455(M=18)/0.9485(M=36)，去偏 ≈0 | `results/coverage_sim_v2.csv` | ✅ 可核 |
| A2 弱区制 gap 消失（非 artifact） | σ_mu/σ=5：naive 回 0.948(M=18)/0.932(M=36) | `results/coverage_sim_v2.csv` | ✅ 可核 |
| **A3 三集 winner's curse**（独立 test 当真值，真高估） | HAM +0.0746✅强 / BraTS +0.0163✅(触顶弱) / ISIC −0.0080(待 R1 全 test 复测) | `results/a3_truthproxy.csv` | ✅ 可核 |
| **A3 方向检验 g_star vs naive 距 test** | g_star 是否比 naive 更接近独立 test 真值（HAM/BraTS ✅近 / ISIC ❌远，诚实） | `results/a3_truthproxy.csv` gstar_to_test_abs vs naive_to_test_abs | ✅ 可核 |
| ~~A3 去偏移位 debias_shift 3/3 全正~~ | 🚫 **弃用**：`val_best−g_star` 构造性偏正（零真信号下 P(>0)≈0.95，随 σ 放大），与真偏差脱钩（ISIC WC<0 但 shift>0 自证）。**永不当 A3 证据**，与 deflation 同病根 | — | 🚫 禁入稿 |
| **A4 校正器交付** | ham macro_auc：naive 0.9469 → g_star 0.9359，CI[0.8950,0.9767]，去偏移位 +0.0111 | `scripts/selinf_corrector.py` 跑 `results/ham_datafission.csv` | ✅ 烟测核过 |

## 禁用指标（方法红线，违反即跑偏）
- 🚫 **deflation = df_width/naive_width−1**：已证 ≡√(2M)−1 纯 M 恒等式 artifact，永不当有效性证据。`selinf_corrector.py` 已不输出此列。
- 🚫 **debias_shift = val_best−g_star**（2026-06-19 skeptic 红队抓出）：构造性偏正，零真信号下 P(>0)≈0.95、随 σ 单调放大，与真偏差脱钩（ISIC WC<0 但 shift>0 自证）。与 deflation 同病根，永不当去偏/A3 证据。若要复活须配零信号 null 校准报净值（真区制显著>0、弱区制塌回 0）。
- 真证据只能是：**① 条件覆盖率破裂 + 修回**（A2 合成，随 σ_mu 正确缩放，已 verifier 过）+ **② winner's curse = val_best−test_selected**（独立 test 当真值的真高估）+ **③ g_star 是否更接近独立 test**（方向检验）。

## ISIC R1 预登记（2026-06-19，防 HARKing，跑前钉死）
- **判据先于结果**：ISIC 改用**全 test 分区（117 阳性）**评估，理由 = 原脚本 `ISIC_TEST_N=1000` 下采样是任意注噪选择（把 117 阳性砍到 ~17），全 test 才是正确评估口径。**这是纠正评估 bug，非朝想要方向调数据。**
- **承诺据实报**：全 test 下 winner's curse 转正 → A3=3/3；仍 ≤0 → 诚实写「ISIC 因阳性样本稀少(584/全集)、低信噪比，selection 噪声主导，未观测净高估」当方法适用边界，A3 保持 2/3。**两种结果都写进稿，不挑。**
- 绝不做：为转正调 test 采样比/改选择流程/换 sigma 口径（踩复现红线）。

## 章节 ↔ 判据 ↔ 数字映射（8 页 IEEE full）

| § | 内容 | 判据 | 数字 |
|---|---|---|---|
| Abstract | winner's curse 医学 benchmark 可测 + data fission 校正 + 校正器交付 | — | A1/A2/A4 各一句 |
| §1 Intro | benchmark 报 sweep/seed-max → CI 失效；贡献三条（首个医学影像 selective inference + 校正器 + 3 集实证） | — | — |
| §2 Related | Åkesson2024(现象)/Zrnic-Fithian2024+Leiner2023(方法)/Koopmans2025/Sculley2018；边界切清 | K2 | 引用 |
| §3 Method | data fission post-selection CI 构造（f=X+τZ 选/g=X−Z/τ 推）；校正器算法 | — | 公式，无数 |
| §4 Results | A1 偏差可测 + A2 覆盖率破裂&修回 + A3 三集 | A1/A2/A3 | 上表全部 |
| §5 Discussion | 辖域/局限（ISIC 噪声受限、BraTS 触顶、单 sweep 不泛化）；校正器交付物 | A4 | A4 |
| §6 Conclusion | — | — | — |

## 写作红线（继承 STORY/ACCEPTANCE）
- 偏差 ≠ 模型差：claim 全指向 reporting practice。
- 辖域守纪律：禁把单 sweep 结论泛化成「所有医学论文欠覆盖 X%」。
- K3 caveat 据实：写「主流报告习惯与 winner's curse 一致」，不写「已普查证实取 max」。
- ISIC 负例诚实写（test 仅 17 阳性方差大），BraTS 触顶诚实写——不藏不洗。
- caveman OFF（写作保真）。数字入稿前过 verifier。
