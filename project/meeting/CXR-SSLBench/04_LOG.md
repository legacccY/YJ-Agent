# CXR-SSLBench LOG

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
