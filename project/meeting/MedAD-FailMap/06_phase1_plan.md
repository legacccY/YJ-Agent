# MedAD-FailMap — Phase 1 / Gate1 Plan

> 状态：**待用户立项拍板**（新阶段开启=拍板点）。planner 设计 + skeptic 红队（1 致命已修 + 2 重要已纳）。
> 服务 **Claim ②「边界可外推」** / lever「跨集+跨模态零调参外推不塌」。把 Phase 0 退守缺席的外推腿补成**真同构、零调参、带统计力的有效读数**。
> 对齐 `02_ACCEPTANCE.md` ②「三条全过才绿」+ `05_preregistration.md §E` 反跑偏不续命。**不碰 Phase 0 既有 A/C 绿结论 + 既有阈值定义**（§A.1/§B/§E 既有口径不动；本阶段新增口径须跑前冻结进 05）。

## 0. 背景（Gate0 出口）

Gate0 重判（2026-06-17 /stage-gate）：**PC-A ① PASS 绿 + PC-C ③ PASS 绿**（三档全坐实，verifier 0 drift）。**PC-B ② 不达绿**——T8.1/T8.2 + T7 large 过，但 **T6 跨数据集+跨模态外推整条退守缺席**（原 BraTS→HAM 整图代理 vs 真 mask 几何不同构）。用户拍板 **B = 有条件进 Phase 1 带债推进**，第一硬前置 = 出真同构跨集外推读数，出不来退 MICCAI。

## 1. Goal

用 HAM10000 官方 GT lesion mask（Harvard Dataverse doi:10.7910/DVN/DBW86T，已查证 10015 全图）在病灶上算与 BraTS **同口径** size/contrast，消除 Phase 0「整图代理 vs 真 mask」特征错配，把退守缺席的跨集外推补成**真同构有效读数**。PASS/AMBER/负结果均算交付——**目的是补有效读数，不是凑 PASS**。

> **诚实预期**：即便两端真 mask，BraTS 小病灶淹大背景（conspicuity 稀释驱动漏检）vs HAM 皮损占画面主体，失败机制可能仍不同 → **跨模态对（BraTS→HAM）大概率 AMBER/负，同模态对（BraTS→METS）更可能过**。这是 T6 该实证回答的，非设计缺陷。

## 2. Gate1 判据（headline A 重铸 2026-06-17：双臂判据，沿用 05 §E CI 门不调松）

> **🔁 headline A 重构说明**：旧 §2 建在旧 ② 「跨模态对（HAM）不塌 = PASS 必要条件」上。headline A 把 ② 改成**外推有效性判据**——「能否外推」由 area-ratio 前验门预言。于是 Gate1 改**双臂**结构。**续命后门未重开**（防 skeptic 致命-1 复发）：见 §2 尾铁律——前验门**跑前预登记** + **正臂强制要求一个预诊断同构的跨模态对真 PASS**，绝不允许把「预诊断同构却塌」的对洗成正面发现。

**沿用 05 §E（不动）**：跨集 AUROC bootstrap CI 下界 ≥0.70 且 ≥集内×0.80 = 不塌门；0.50~0.70 = 弱值；≤0.50 = 塌。strong baseline 须 Holm Δ>0 显著超 SB1(size)+SB2(size+contrast)，**在跨集外推 AUROC 上比**。extrapolation 方向 test split 须 ≥20 detected。

**Phase 1 硬前置（Gate1 专属，跑前冻结进 05）**：
- **G1-a 同构性 + 前验门**：两端 size/contrast 均在**真 mask 病灶**上算（整图代理不得作确证特征）。**area-ratio 重叠前验门（PR-7，跑前预登记、纯 CPU 先跑）**：每对先算「病灶/背景面积比分布重叠」→ 输出 `iso=True/False`（重叠实质 ≥ 阈值 = 同构 / 否则不同构）。**此门在跑外推 AUROC 之前固定每对的 iso 标签**，是判据的输入不是事后归因。
- **G1-b 双臂样本**：**正臂** ≥1 个 `iso=True` 对（含 ≥1 跨模态预诊断同构对）；**负臂** ≥1 个 `iso=False` 对（HAM 已实测 1.3% 重叠 = `iso=False`，天然负臂样本）。
- **G1-c 模态覆盖**：正臂的 iso=True 对中**须含 ≥1 跨模态**（如 BraTS→CBIS-DDSM 单肿块稀释 regime，待验 iso）+ ≥1 同模态（BraTS→METS，待验 iso）。
- **G1-d ≥3 seed** 方差带；判定取 seed 间最差档 CI 下界（PR-5 冻结）。

**Gate1 PASS/AMBER/FAIL 机械判定（双臂，含续命后门铁律）**：

| 判定 | 规则 |
|---|---|
| **PASS（绿）** | **正臂**：≥1 个 `iso=True` 跨模态对 + ≥1 个 `iso=True` 同模态对，**均零调参外推不塌**（CI 下界≥0.70 且 ≥集内×0.80）且外推 Δ Holm 显著超 SB1+SB2 ∧ **负臂**：≥1 个 `iso=False` 对（HAM）前验门预言不可外推、**实测确实塌或拒绝外推**（预言↔实测方向一致）∧ T7 extrapolation CI 下界>0.5 ∧ G1-a..d 前置全满足 |
| **AMBER（黄）** | 仅当**正臂某 iso=True 对测出弱值 CI 下界 0.50~0.70**（§E AMBER 唯一合法语义=测出弱值）→ Decision Gate 分诊，不自动续命 |
| **FAIL（红，退 MICCAI）** | **正臂空**（无任何 iso=True 跨模态对真 PASS）/ 同模态 iso=True 对塌 / 外推 Δ 输 baseline / **前验门失灵**（预言 iso=True 却塌，或预言 iso=False 却 PASS = 判据本身不成立） |

> **🔴 续命后门铁律（skeptic 致命-1 防复发，headline A 下重申）**：
> 1. **`iso` 标签必须跑外推 AUROC 之前由 PR-7 前验门固定并写进 05**——绝不允许跑完看结果再贴 iso 标签（那才是真续命偷换）。
> 2. **负臂只收 `iso=False` 对**（前验门预言不可外推的）。一个 `iso=True`（预诊断同构）的对如果**塌**，**不得**洗进负臂当「边界条件发现」——它要么使正臂不满足 → FAIL，要么暴露前验门失灵 → FAIL。**预诊断同构却塌 ≠ 正面发现**。
> 3. ~~正臂强制要一个 `iso=True` 跨模态对真 PASS~~ **→ 改铁律3'（2026-06-17 reframe A'，跨模态正例实证枯竭）**：正臂强制要 ≥1 个 `iso=True` 对真 PASS（**同模态 BraTS→METS 可**，跨模态正例几何枯竭故不强求），光有「负臂全塌」= 判据无正例锚 = FAIL 退 MICCAI。**但 headline/正文禁 claim 任何跨模态正向外推**——手上零跨模态 iso=True 正例，暗示跨模态 work = 偷偷松掉「跨模态」三字 = 移动球门（skeptic 红队2-🟠-1）。跨模态一律落负臂「前验判据正确预言其失败」。**承重压判据预言性 + Gate2 held-out 盲测命中**（防「同模态 work」被打 trivial），不压「同模态 work」这个结果（skeptic 🟠-2）。
> 4. **负臂证据须有实测锚，防判据自我循环**（skeptic 红队2-🟡-5）：负向预言（iso=False→不可外推）作判据证据，**至少需 ≥1 个 iso=False 对「跑了外推、实测确实塌」**（HAM 已满足=Phase 0 实测退守）。其余 iso=False 对止损不跑可以，但**只作工程省算力、不计入判据负向预言命中证据**（否则「判据说不行→不跑→拿判据自己的话当证据」= 自我循环）。

## 3. 实验矩阵

**零调参铁律**（搬 05）：proxy-clf 在 BraTS fit，目标集只 transform 不 refit；StandardScaler 同样 BraTS fit/目标 transform。同口径：size=连通域面积，contrast=|mean(病灶)−mean(环带)|。

**前置数据准备（CPU/下载）**：
- **P1-D1**：下载 HAM 官方 mask（Harvard Dataverse，`HAM10000_segmentations_lesion_tschandl.zip`，命名 `ISIC_<id>_segmentation.png`），登记 datasets.json。**非拍板点**（非对外传输），可自主取。
- **P1-D2（🛑拍板）**：BraTS-METS 2023（Synapse syn51156910，需注册=对外，**402 studies/3076 lesions**，同模态 MRI+voxel mask）。下载+预处理照 BraTS2021 口径。**须主线拍板**（对外注册+HPC 上传新数据）。fallback：若注册受阻/METS 训练不稳（recon 异常），同模态锚降级为 **BraTS 跨中心 train/test split**（退化版同模态对照）。

**训练（GPU，走 gpu_slot，自主）**：P1-T0-brats（复用 A0 ckpt+补 2 seed）/ P1-T1-ham（复用 B0 ckpt+补 2 seed）/ P1-T2-mets（依赖 P1-D2，3 seed）。各 ~2-4 GPU·h×seed，复用已归档 ckpt 抵 seed=42。

**评分+特征+外推（CPU，coder 实现即跑，不抢 GPU）**：
- P1-F1：HAM 异常皮损子集（dx≠nv）+ NV 上用真 mask 算同口径 size/contrast（环宽=mask 等效直径 5-10% 相对宽度，跑前冻结 PR-2）。
- P1-F2（条件）：METS 同口径特征。
- P1-B1：BraTS 拟合边界 clf（多 seed）。
- **P1-B2-ham**（跨模态）/ **P1-B2-mets**（同模态）：BraTS-fit clf 零调参 transform predict，bootstrap CI 98.75%，多 seed。
- P1-B3：strong baseline 在**跨集外推 AUROC** 上比 Δ。
- P1-B4：extrapolation 修 ≥20 detected split。

**依赖**：P1-D1 可先做 → P1-F1 待 HAM score；训练拼卡并行；外推两条 P1-B2-* 并行。

## 4. Decision Gates（if-then）

| 触发态 | 动作 |
|---|---|
| 正臂空：无任何 `iso=True` 跨模态对真 PASS（含候选集都作废/都塌） | **FAIL 退 MICCAI**（判据无正例锚、外推主轴空；A/C 绿+受控失败现象学作 MICCAI 档） |
| 前验门判某对 `iso=False`（面积比不重叠，如 HAM） | 进**负臂**：不跑该对跨模态外推（止损省 GPU），其「前验预言不可外推」作判据负臂证据；**不得**洗成正面边界发现 |
| **`iso=True` 对塌（预诊断同构却 CI 下界≤0.50）** | **FAIL**：要么使正臂不满足、要么暴露前验门失灵（预言↔实测矛盾）→ 退 MICCAI。**绝不**当负臂/边界条件（续命后门铁律2） |
| 正臂 `iso=True` 对测出弱值（0.50~0.70） | AMBER 分诊：reviewer 独立判是否够 analysis track novelty，**主线不自宣**；绝不重命名成 PASS |
| 同模态 `iso=True` 对塌（METS≤0.50） | FAIL：同构同模态都不可外推 → 退 MICCAI |
| 正臂 `iso=True` 跨模态对过 PASS 门（外推有效性判据坐实正例） | 强 PASS，但 verifier 三方核 + reviewer 复核非泄漏/非整图代理偷换 + 复核 iso 标签确系跑前预登记（太好反而要查） |
| ≥3 seed 方差大跨 PASS/AMBER 门 | 取最差档（保守）；最差档定义见 PR-5 |
| 外推 Δ 输 baseline | FAIL：多维相图是装饰 |

> **续命红线**（搬 §E + headline A 重申）：FAIL 按预案退 MICCAI，不调松 CI 门、不把 `iso=True` 对的塌重命名成「探索性发现/边界条件」、不跑后补贴 iso 标签。门槛改动=改 ACCEPTANCE 方向=拍板点。

## 5. Gate1 PASS 后 → ② 终绿 还差的清单（skeptic 重要-2，防假象）

**Gate1 是「外推腿从 0 读数 → ≥1 真读数」的解锁闸，不是 ② 的验收。** Gate1 全 PASS 后，离 ② 终绿仍差：
1. strong baseline 的**跨集版**对照（Phase 0 T8 是 in-domain）——Gate1 已纳 P1-B3 部分覆盖，但需 Gate2 在更多对上稳。
2. extrapolation 的**跨集版**（Phase 0 T7 是 in-domain）。
3. ①「跨≥3 集」的**第三个真正独立模态/解剖集**——BraTS+HAM+METS 里 METS 是近分布脑 MRI，三集俩脑 MRI 会被审稿人质疑「跨集复现」说服力打折 → Gate2 需补一个真正独立集。

## 6. 次优先（Phase 1 做但非 Gate1 闸）

- C4 校准补确证（③ 第三件套）：须**先冻结排序方向+reliability 权重**（PR-6）才能升确证；解决不了则 ③ 维持 C2+C3 双件套（已绿，不强凑）。
- T8 写作只引相对 Δ，不碰绝对 in-domain AUROC=0.964。
- glcm_cluster_prom 多 seed 重跑复核稳定（Phase 0 已 z-score 修）。

## 7. 预登记增补清单（跑前冻结进 05，reviewer 复裁+主线拍板+留痕）

| # | 待冻结 | 建议值 |
|---|---|---|
| PR-1 | 跨集 detected 语义 | HAM lesion 子集内 P90 = y_fail，与 BraTS tumor-only P90 同构；METS 同 BraTS |
| **PR-7b（新，skeptic 红队2-🟠 唯一真残口）** | **iso 阈值确定规则**（防「看候选对重叠率后校准尺子凑臂」= 隐蔽事后归因） | **绝对阈值跑前冻死、不依赖任何候选对实测重叠率**：建议「BraTS 稀释 regime（≤P25 面积比）内目标集样本占比 ≥X%（如 X=5）= iso=True，否则 False」，X 在**看 CBIS/IDRiD/METS 任何重叠率之前**由 reviewer 拍板冻进 05；或连续化取消二分（预登记「重叠率 vs 外推保留率单调」趋势检验，用所有对，顺带缓解 n=1 过拟合）。reviewer 复裁须把「阈值是否在看候选对重叠率前定」列为复核项（现有「复核标签时序」查不到阈值校准） |
| PR-2 | 环带宽度 | HAM = mask 等效直径 5-10% 相对宽度（取单值如 7.5%）；BraTS/METS 沿用 3px |
| PR-3 | proxy-clf+scaler 零调参 | [size,contrast] clf BraTS fit/目标 transform 不 refit；Gate1 确证不用整图代理 |
| PR-4 | 几对的多重比较校正 | ≥2 对+SB = 新 family F-B'，family 内 Holm（CI Bonferroni 调），与 Phase 0 family 不跨校正 |
| PR-5 | 多 seed 聚合 | ≥3 seed；判定取最差档 CI 下界（精确定义：最差 seed 点估计 vs seed 间最差，二选一冻结） |
| PR-6 | C4 排序方向+权重（若纳 C4 确证） | conspicuity 高=更可靠方向 + 复合权重，跑前定 |
| **PR-7（新，机制同构）** | **面积比分布重叠检查** | BraTS 与目标集病灶/背景面积比分布须实质重叠（G1-a 子条件，纯 CPU 早跑） |

## 8. 算力预估

GPU 训练 ~10-28 GPU·h（复用 2 个 ckpt 抵 seed=42；METS 纳则上界）；CPU 软活分钟级；下载 HAM mask（百 MB）+ METS（GB 级，拍板）。**拍板点**：P1-D2（METS 对外注册下载）；GPU 训练经 gpu_slot 自主起。

## 9. 交接

- **coder**：HAM mask 对接+同口径 lesion 特征提取（复用 BraTS 几何函数）；failure_boundary 扩 BraTS→HAM/METS 零调参 transform 多 seed；B4 split 修 ≥20 detected；seed 参数化；面积比重叠检查脚本（PR-7）；（条件）METS 切片预处理。
- **主线**：P1-D2 拍板 → GPU 训练自主起 → CPU run。
- **analyst**：跑后看 extrap csv 对 §2 判定表机械判 + 多 seed 方差带。
- **verifier**：三方核 csv 原值禁 Read。
- **reviewer**：跑前复裁 §7 预登记（PR-1/PR-2/PR-4/PR-7 重点）；跑后若 PASS 复核非泄漏/非代理偷换。

---

## skeptic 红队结论（2026-06-17）

裁决 **CONDITIONAL→已补致命升 PASS**。1 致命（AMBER 跨模态续命后门，§2 修法 a 已烤入）+ 2 重要（G1-a 面积比重叠检查 PR-7、Gate1→② 差距清单 §5，均已纳）+ 残差（METS 实为 402 studies 非 238；最差档定义；HAM mask 单医师标注）。诚实底盘扎实（不续命、禁整图代理、有 fallback）。
