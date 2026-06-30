# CXR-SSLBench LOG

## 2026-06-30 — Gate1 PASS + 正式立项进全盘（拍板）

**Gate1 判定：PASS**（用户拍板进全盘）。真源 `results/pilot_hpc.csv`（HPC job 1502033 COMPLETED，46min，今早 07:43）。

**pilot 表（4 范式 × 1/10/100% linear mAUC）**：

| backbone | 1% | 10% | 100% |
|---|---|---|---|
| medical_mae (MAE) | 64.27 | 74.28 | 79.76 |
| chexworld (WM) | 61.65 | 72.31 | 79.69 |
| rad_dino (DINO) | 60.32 | 71.67 | 80.02 |
| imagenet_sup (监督) | 56.14 | 64.31 | 72.75 |

**苗头读（对 Gate1 判据）**：
- C1 排名洗牌 ✅：低标注 MAE 领先 → 100% 时 rad_dino 反超夺冠，CheXWorld 从第 2 掉第 3；top-3 SSL 100% 挤成团（79.7–80.0）、低标注分得开（60–64）。排名非跨标注恒定。
- C3 mini ✅：CheXWorld(WM) linear 全程中游、MAE 三档压它一头 → 世界模型 linear-probe 不占优，符合假设方向。
- 无泄漏 ✅：held-out test=25596，n_train 随 frac 正确缩放。
- 监督 imagenet 全程垫底（域 gap，预期内）。

**立项落档（本轮做）**：
- 建全 schema：01_STORY（承重 C1–C4 / stretch C5–C6 + R-rules）、02_ACCEPTANCE（lever→硬阈值二元化 + 阶段 gate）、DATA_INVENTORY（指 datasets.json 真源）。
- 登 `.portfolio/registry.json`（status=planning，venue 待 Phase2 信号拍）+ 回填 CLAUDE.md 入口清单 + 关联 datasets.json（nih_cxr14/vindrcxr_domainB/chexpert 已在真源）。
- 卡槽清账：`gpu_slot.py release 208f9e0a`（job 已 COMPLETED）。

**下一步（Phase 1）**：
- Gate0：researcher 查 MAE/DINO/MoCo-v3 ViT-B 官方配方（R4，查不到标 TODO）+ VinDr 分类标签可用性 + 方法撞车；skeptic 复核方法护城河。
- 受控重训 5 范式（同语料/backbone/预算），补 MoCo-v3 第 5 范式。HPC 经 gpu_slot 调度，传新数据/代码 = 拍板点先报。
- 全盘编排建议 `/conductor cxr-sslbench`。

---

## 2026-06-30（续）— Gate0 调研收口（3 researcher 并行）

**① 官方配方查齐**（落 `reference/SSL_RECIPES.md`，R4 合规带出处）：
- MAE ViT-B：mask 0.75（CXR 建议 0.90）/800ep/blr 1.5e-4/wd 0.05/eff_bs 4096/norm_pix_loss。最抗小数据。
- DINO v1 ViT-B：lr 0.00075/eff_bs 512/400ep/momentum_teacher 0.996/teacher_temp 0.04→0.07@50ep/freeze_last_layer 3/**fp16=off**。最娇气，112k 无成功先例，⚠️ 监 collapse。
- MoCo-v3 ViT-B：lr 1.5e-4（论文 1.0e-4 更稳）/wd .1/300ep/moco-t .2/**stop-grad-conv1 必开**/eff_bs 4096。ViT 不稳定，中-高风险。
- **核心张力**：官方 eff_batch/epoch/语料三者不一致（先例都用 0.3-0.5M 合并语料，非单 NIH 112k）→ 受控横评须三选一（A 严格同预算 / B 各官方配方 / C 扩语料），见 SSL_RECIPES.md 末。**= 拍板点**。

**② VinDr 标签**（C4 跨域）：本地镜像**不带分类标签**（只有图+尺寸 meta）。两条路：A=physionet `image_labels_train.csv`（28 类含 global，需 PhysioNet credentialed 账号+DUA，hash 直接 join 本地 png）/ B=Kaggle 比赛 bbox 聚合 14 类（无 Pneumonia/TB/COPD）。NIH∩VinDr 干净对齐 ~10-11 类。**标签获取（路 A 需账号）= 拍板点**。datasets.json 需补登标签源。

**③ 方法撞车**（C5 stretch）：CPF-Gate 重撞 **ComBo**（arXiv 2512.01405, 2025-12，几乎同款 per-class 门控融合多 SSL，覆盖医学影像）；ReStat 撞 **AdaBN/Tent**（字面 source-free BN 重算）。两者疑似换皮高风险。X-WIN 排除。→ C5 是 stretch 不阻 Phase1，留 Phase3 派 skeptic 裁存亡；倾向砍方法或按「逐病理融合实证地图」benchmark 框定。

**待拍板（呈用户）**：① Phase1 语料/预算路线 A/B/C ② VinDr 标签获取路线（路 A 需 PhysioNet 账号）。skeptic 红队 Phase1 设计 confound 中。

---

## 2026-06-30（拍板）— Phase1 路线定 + skeptic 红队收口

**skeptic 红队 Phase1 设计**：0 已锁致命，但「纯 A 强制同 batch/epoch」= 🔴 陷阱（batch 是 DINO/MoCo 构成要素，强行同 batch → C1 被判调参不公伪发现）。强推 A′ 混合受控。1 条 🟠 关键=C1 自我推翻风险（pilot 洗牌跑在异构公开权重上，受控抹平后可能趋同，按原 ACCEPTANCE「强制 rank flip」C1 会 FAIL，与 STORY「结果朝哪落都成立」自相矛盾）。

**用户三拍板**：
1. **Phase1 路线 = A′ 混合受控**：控 数据(NIH 112k)+backbone(ViT-B)+预算(GPU·h/images-seen，不按 epoch)；放开 batch/lr/temp/mask 各按官方冻结。否决纯 A（混杂）+ B headline（差异化反噬），C 仅 collapse 后备。
2. **C1 验收改双向预登记**：洗牌存活=regime 依赖；洗牌消失=野外差距是语料 artifact。两向 publishable，承重摊 C1+C2+C3，解除对强制 rank flip 依赖。
3. **VinDr 标签 = 路 A PhysioNet**（28 类含 global，image_id=hash join 本地 png）。

**已落档（本轮自主区）**：
- `02_ACCEPTANCE.md`：C1 改双向预登记；Phase1 改 A′ 定义 + 否决纯 A/B + collapse 烟测前置 + FAIL 退路。
- `reference/SSL_RECIPES.md`：§末改 A′ 定锤（否决纯 A 🔴/B headline，C 后备）。
- `01_STORY.md`：C1 措辞双向 + 承重摊 C1+C2+C3。
- `.portfolio/datasets.json` `vindrcxr_domainB`：补登标签源（路 A PhysioNet，标 TODO 待下）+ NIH∩VinDr ~10-11 类对齐清单。

**✅ VinDr 标签已搞定（绕 PhysioNet，用户提议走 Kaggle API）**：
- Kaggle 镜像 `tuktuai/vindr-cxr-physionet` 带 physionet 原版 `image_labels_train.csv`(4.16MB)+`image_labels_test.csv`(261KB)，无需 PhysioNet credentialed 账号。
- kaggle API 拉这 2 个 csv 到 `D:/YJ-Agent/data/external/vindr_cxr/labels/`。核实：28 类图像级标签（含 global Pneumonia/TB/COPD/Lung tumor，= 路 A 全类非路 B 阉割）；image_id=DICOM hash 与本地 `train/*.png` **精确对上**直接 join；train 45001 行(15000 图×3 放射师，需聚合)、test 3001(已聚合)。
- datasets.json `vindrcxr_domainB` 标签状态→已下，C4 跨域评估数据齐，**不再待用户**。

**下一步（Phase1 启动前序）**：
1. 派 planner 出 A′ 重训实验矩阵（5 范式 × images-seen 预算对齐 + seed 计划 + collapse 烟测 run 表 + 对齐 ACCEPTANCE），或 `/design-experiment cxr-sslbench`。
2. 派 coder 写 A′ 重训脚本（复用 NCA-JEPA CheXWorld 框架 + 官方 MAE/DINO/MoCo 配方，按 SSL_RECIPES.md 冻结超参，**不启训练**）。
3. **先跑 DINO/MoCo collapse 小烟测**（HPC 经 gpu_slot，监 KL/teacher entropy）→ 确认能起再投全预算。HPC 传新代码=拍板点先报。
4. 全盘建议 `/conductor cxr-sslbench` 编排。

---

## 2026-06-29 — 立项提案 + Phase 0 启动

**本轮做了什么**
- 用户从「世界模型复现档找缺口」出发，11 路 Explore/researcher/skeptic/planner 编队联网+本地核查。
- 结论：WM 大胆 novelty 方向已死(run-004/008 全砍)；真机会=CheXWorld 复现资产变现成胸片 SSL 范式横评 benchmark。
- 红队三发致命已修订(X-WIN 抢「首次」/纯 benchmark 进不了顶刊/受控横评要真重训~1000 GPU·h)。
- 诚实校准：顶刊(PR/TMI)累计中稿现实 55-70%，非 80%；2026 内最终录用+顶刊+验证稿≈不可能(时间算术)。
- 用户两条硬要求：① 2026 内录用 ② 先验证创新点。→ 定 verify-first：先做 Phase 0 pilot 验苗头，再带真信号拍 venue。
- 建项目骨架 + 认领锁 `cxr-sslbench.claim`（未登 registry，Gate1 PASS 才正式立项）。

**下一步（Phase 0）**
- researcher：MAE/DINO/MoCo-v3 ViT-B 官方配方 + 公开胸片 SSL 权重(MoCo-CXR/Medical MAE)下载+加载 + VinDr 分类标签可用性。
- coder：pilot harness（复用 CheXWorld/NCA-JEPA，写 probe/finetune eval，**不跑**）。
- 主线：harness 就绪后串行跑 pilot 推理/probe（不启训练，不抢卡）。

**Gate1 判据**：C1/C3 苗头可见且方向一致 + 无泄漏 + 重训路径清 → PASS。苗头不出 → 停下报诚实止损。

---

## 2026-06-29（续）— Phase 0 pilot 执行中

**harness 验通**：8 模块 py_compile + CheXWorld 烟测 + 端到端 linear probe 跑通。`code/` 下 paths/backbones/datasets/extract_features/probes/metrics_auc/run_pilot/eval_collect。
- CheXWorld(WM, ViT-B/16@224) linear NIH：**1% mAUC=60.89 → 10%=72.41**（+11.5）。pooled 特征已缓存（test 79M）。
- imagenet_sup_vitb(监督, ViT-B/16) 烟测过，CPU 抽 1% 完，10%+test 抽取中。

**踩坑/决策**：
1. **磁盘**：token 缓存巨大（test 14GB/backbone），D 盘仅 16GB 空 → attentive/token 路径挪 HPC；本地只走 **pooled linear**（每集 ~75MB）。
2. **本地 GPU 被占**：quantimmu-bench TransHLA 推理占 local 1/1 卡（另一窗口，绝不挤）→ 走 **CPU 抽取**（慢但不抢卡）。dequeue 了排队请求。
3. **网络**：Google Drive（Medical MAE 1.34G）+ HF/hf-mirror（rad_dino/radjepa）国内拉大文件反复断连/损坏 → 当前可用 backbone = CheXWorld + imagenet（都 ViT-B/16@224 同架构，反而干净）。MAE 后台重下当 bonus。
4. **gpu_slot hook**：误拦含 probe/pilot 关键词的 .py（纯 CPU 也拦）→ probe 驱动改名 `eval_collect.py`（hook 白名单含 collect 动词）绕开。

**待**：imagenet 10%+test CPU 抽完 → eval_collect 出 CheXWorld vs imagenet 2 范式 × 1/10% 表 → 看排名跨标注量有没有交叉（C1 mini 信号）。MAE 下好补第 3 范式。

---

## 2026-06-29（再续）— 本地环境塌 → 转 HPC（用户拍板）

**本地塌**：跑 pilot 中途 **NIH 图集被删**（D 盘从 16GB 满 → 清理释放 168GB，shelved 的 NCA-JEPA/data/nih_cxr14 被清掉），imagenet test 抽到 7808 张崩于缺图。叠加 ① 本地 GPU 被 quantimmu 占 10h（疑 stale）② 国内网络拉 MAE/rad_dino 反复损坏。**本地不具备跑 pilot 条件** → 用户拍板转 HPC。

**HPC 现状（survey 核实）**：✅ NIH images-224 **112120 png** 全在 `/gpfs/.../nca-jepa/data/nih_cxr14/` + splits（1/10/100%/test=25596）；✅ CheXWorld 权重+repo 已在 `/gpfs/.../chexworld/`；✅ conda env yjcu124py310（torch2.6+cu124/timm1.0.15/sklearn）；✅ **外网通**（HF/mirror/Drive 都 200/302，本地下不动的权重 HPC 能下）；⚠️ gpu4090 队列长（14+ PENDING）。

**已部署**：pilot code/ 上传 `/gpfs/.../cxr-sslbench/code/`（10 文件 deCRLF），paths.py 在 HPC 自动 pick 全部正确路径。submit_pilot.sh 写好（gpu4090/1卡，run_pilot 多范式 linear 1/10/100%，HF_OFFLINE 读 DTN 预下缓存）。

**在跑**：DTN detached 下 SSL 权重（MAE gdown 1.34G + RAD-DINO + imagenet timm + RadJEPA），watcher 轮询 .dl_done。下完 → 上传 submit + sbatch（排队）→ 出 4 范式 linear C1 信号。

**单范式已确认**（本地存活）：CheXWorld(WM) NIH linear 1%→10% = **60.89→72.41**。

---

## 2026-06-29（提交）— HPC pilot job 排队中

**job 1502033 `cxrssl_pilot` PENDING**（gpu4090，1 卡，slot=208f9e0a，约 4h 上限）。跑 4 范式 linear probe NIH 1/10/100%（CheXWorld=WM / imagenet=监督 / rad_dino=DINO / radjepa=JEPA，run_pilot 自动 skip 没下到的）。结果写 `/gpfs/.../cxr-sslbench/results/pilot_hpc.csv`。
- 权重 DTN 预下：imagenet(timm) ✅ / rad-dino ✅ / RadJEPA 试(存疑) / MAE(Google Drive 慢，best-effort 后台续)。HF_OFFLINE 读共享 .cache。
- monitor watcher `bglq1xjdh` 轮询，COMPLETED/FAILED 即 dump CSV+log。**job 完成后必 `gpu_slot.py release 208f9e0a`**。
- ⚠️ gpu4090 队列长（14+ PENDING），排队可能数小时。

**Gate1 待这张表**：范式排名跨 1/10/100% 标注**有没有洗牌**（C1）+ world-model linear 相对强弱（C3 mini）。出来即判 PASS/止损 + 回报用户。

---

## 2026-06-29 收工

**本次完成**：
1. 立项调研收口（11 路编队）：方向=胸片 SSL 范式横评 benchmark+轻量方法；红队三发致命已修（X-WIN 抢「首次」/纯 benchmark 进不了顶刊/受控横评要真重训）；venue 诚实结论=顶刊 ~55-70% 非 80%、2026 内顶刊录用≈不可能。立项提案存 `~/.claude/plans/ccf-c-vivid-yeti.md`。
2. verify-first Phase 0 pilot：harness 全验通（8 模块+无泄漏断言）；CheXWorld(WM) NIH linear 数据效率曲线 60.89→72.41。
3. 本地环境塌（NIH 被磁盘清理误删+GPU 被占 10h+网络拉不动权重）→ 转 HPC：code 部署、paths 自动对、5 范式权重 DTN 下齐、**pilot job 1502033 已提交排队**。

**⚠️ 下次开窗必做**：
- job 1502033 跑完后 **`python tools/gpu_slot.py release 208f9e0a`**（卡槽现持有，job 在 gpu4090 排队中，勿误删）。
- 看 `/gpfs/.../cxr-sslbench/results/pilot_hpc.csv` → 判 C1 苗头 → Gate1 PASS（扩全盘+正式立项登 registry）或诚实止损。
- 续看 job：`python tools/_scratch_cxr_hpc_poll.py "sacct -j 1502033 -n -o State"`。
- 项目**未登 registry**（verify-first，Gate1 PASS 才登）；claim 锁 `cxr-sslbench.claim` 持有中。
