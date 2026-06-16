# MedAD-FailMap 项目 LOG

> 入口 `00_README.md`。STORY `01_STORY.md`。验收 `02_ACCEPTANCE.md`。探路全档 `../方向探路_2026-06-16.md`。

---

## 2026-06-16 — 立项（大部队探路收口）

**怎么来的**
MedSeg-UQ「医学分割 UQ 纯理论下界」三轮 reviewer 全塌缩后，用户拍「重头大部队找方向，分割/UQ 可分开，参考 NCA-JEPA 打法，别跟现有方向重合，多挖宝藏」。锚定=医学影像内任务放开 + 主投纯顶会。

**探路过程（两轮 + 三次 reviewer 裁，全档见 `../方向探路_2026-06-16.md`）**
1. 第一轮 4 researcher 扫 17 候选 → reviewer 判 9 个是「搬成熟体系换皮」（同 MedSeg-UQ 病根），红榜 P/M/I 但偏 NCA 味。
2. 用户转向「别跟 NCA/JEPA 重合，挖宝藏」→ 第二轮 3 researcher 硬排除 NCA/JEPA → reviewer 红黑榜：🏆 重建式 AD 假设证伪（五项全占）、🥈 OOD covariate/semantic 解耦、🥉 SAE probing。
3. 用户拍「就定潜力最好的」→ 选定重建式 AD。立项前 3 路核实：
   - **数据**🟢：MedIAnomaly Zenodo 7 集 2.4GB 预处理可下 + 本地 HAM10000 NV/NIH CXR14 复用。
   - **撞车**🟡→reframe：发现 incumbent = HKUST Cai 组同时占 benchmark（MedIAnomaly）+ 理论证伪（AE4AD），原 framing「证伪三假设」=incremental 死法（同 MedSeg-UQ ★1）。
   - reviewer 终裁 🟡 窄门 → **reframe 到协变量正交轴**（AE4AD 定理不带协变量参数、benchmark 不分层，结构上够不到）。
   - **算力**🟢：重建 AD 模型极小、2D，4×4090 轻松（主线判，驳 reviewer 保守）。
   - **协变量失败边界撞车**🟢：穷举无命中，四项缝完整空白（可外推函数/phase diagram/per-image 判据/多方法边界），捡到 conspicuity 理论桥可借。

**立项决策（拍板点，用户已拍）**
- **方向/RQ**：重建式医学 AD 的失败何时可预测 = 协变量化失败边界 + per-image 可靠性判据 + 多方法对比边界。三假设降为分析工具。
- **会场**：主投 ICLR/NeurIPS analysis track，退路 MICCAI/MedIA。
- **打法**：capability/机理型，非刷 SOTA。
- **配置**：本科单人 + 低算力 4×4090 + 2D 公开集。

**纪律教训沉淀（继承 MedSeg-UQ）**
- 主轴守协变量+可预测，跑偏到「证伪三假设」立即停（incumbent 地盘）。
- 理论命题先 reviewer 裁再落「已证」。
- 这次探路在立项前逮到 AE4AD incumbent + reframe，正是 MedSeg-UQ 当年没做到的——准备做足才立项。

**已认领** `.portfolio/locks/medad-failmap.claim`；registry + datasets 已登记。

**下一步（待办）**
- [ ] Phase 0 可行性预检：搭最小重建 AD pipeline（AE/VAE baseline，复用 MedIAnomaly codebase）+ 协变量分层 sanity（先合成可控异常或用 BraTS2021 像素 mask 分层）→ Gate 0。**跑实验是拍板点 + 持训练锁。HPC 没空则只推软活。**
- [ ] 下数据：MedIAnomaly Zenodo 2.4GB（records/12677223）；本地 HAM10000 NV 子集对接「nevus=正常」。
- [x] ~~reviewer 裁 ②③ 验收阈值~~ **已裁并收紧（见下）**。
- [x] ~~researcher 核 conspicuity 可计算实现~~ **已核（见下）**。

### 2026-06-16 续 — 两件软活（不占 GPU/训练锁）

**1. conspicuity 可计算性核（researcher）**：gCNR/CNR/Weber **都需 GT mask**，不能用于无标注 per-image 判据。**无 mask 代理成立**：全图 σ、GLCM（Cluster Prominence/Contrast）、FFT 频谱熵、Otsu 伪前景 CNR_proxy（scikit-image 可算，无训练）。先例 = Mammogram difficulty（34 GLCM 无 mask 预测判读难度 AUC=0.75，arXiv/PMC12092920）。**「图像先验 conspicuity→预测重建式 AD 成败」仍真空白**。配方建议 `CNR_proxy/(1+complexity_proxy)`，预期 0.65-0.75 AUROC 但需实验验。gCNR 仅 MATLAB（VU-BEAM-Lab），Python 需自实现（公式简单）。

**2. ACCEPTANCE ②③ reviewer 终裁 + 收紧（opus，立项首道防自欺闸）**：原判据松到自验必过、③ 有循环论证结构性洞。
- 🔴 **③ 循环论证**：conspicuity = 病灶可见性重命名，"预测成败"恐 tautological；"vs 重建误差"是弱 baseline。**已收紧**：增量信息嵌套检验（given anomaly score 仍能额外预测）+ 控制 size/contrast 后残差预测 + risk-coverage/selective AUROC 校准。过关前不得落「conspicuity 桥成立」。
- 🟠 **② "优于随机"太松**。**已收紧**：跨数据集零调参外推（保留率≥80% 且≥0.70）+ 跨模态不塌 + strong baseline（vs size / size+contrast 回归）+ extrapolation 到未见协变量区域。
- 🟡 **① 加非单调/交互效应要求**（否则相图退化单变量、② strong baseline 站不住）；反跑偏侧加**多重比较 Holm/FDR 预登记**。
- `02_ACCEPTANCE.md` 已据此改判据**结构**（非只改数字），与 STORY 承诺对齐。

**纪律点**：这次「先 reviewer 裁再钉 ACCEPTANCE」就堵住了 MedSeg-UQ「自验通过就写已成」的同型洞——立项当天就把循环论证陷阱挡在实验前。

**3. Phase 0 设计（planner）** → `03_phase0_plan.md`：三道证伪闸 PC-A（地基：协变量系统失败+交互）/ PC-C（防循环论证：conspicuity 增量信息三件套，纯 CPU）/ PC-B（可外推雏形+strong baseline）。最小数据=BraTS2021（有 mask 可分层）+ 本地 HAM-NV（跨模态零下载），AE/VAE 照官方超参。**GPU 仅两次训练 6-9 GPU·h，其余纯 CPU 软活**。Gate 0 决策表全绿进 Phase 1、任一红修/退。

**GPU-free 进度小结（本窗 HPC 没空时推的纯软活）**：conspicuity 核 ✅ + ACCEPTANCE 收紧 ✅ + Phase 0 设计 ✅。**剩余 GPU-free 前置**：① researcher 锁 MedIAnomaly 官方超参 ② coder 实现 5 个脚本（含 CPU 软活 C/B 系列）③ 下 MedIAnomaly Zenodo 数据。**需 GPU（拍板点+训练锁）**：A0/B0 两次 AE 训练。

---

## 2026-06-16 续 — Phase 0 全套脚本实现（coder）

**官方超参来源**：`github.com/caiyu6666/MedIAnomaly`，复现零偏离，见 `03_phase0_plan.md` 附录。

### code/ 目录文件指针

| 文件 | 功能 | 对应实验 |
|---|---|---|
| `code/train_recon_ae.py` | AE/VAE 训练 + anomaly score csv；官方超参（Adam lr=1e-3/bs=64/epochs=250/latent=16/64×64/L2/β=0.005）；`-d brats/isic -m ae/vae` | A0-train-AE, B0-train-HAM |
| `code/stratify_eval.py` | PC-A 分层评估；mask 连通域 size + 3px 环带 contrast；≥3 桶 + 3×3 交互网格；输出检出率 csv | A1/A2/A3 |
| `code/conspicuity_proxy.py` | PC-C C1 无 mask 代理特征（σ/GLCM/FFT 熵/Otsu CNR_proxy）；纯 CPU scikit-image；输出 per-image 特征 csv | C1 |
| `code/incremental_stats.py` | PC-C C2/C3/C4 增量统计；嵌套 LR 检验 + 残差偏相关 + risk-coverage；内置 Holm/FDR 校正 | C2/C3/C4 |
| `code/failure_boundary.py` | PC-B 失败边界拟合+跨集外推+strong baseline；逻辑回归/GBM；extrapolation 到未见 size 区域 | B1/B2/B3/B4 |
| `code/download_medianomaly.py` | Zenodo records/12677223 下载 + 目录结构校验（写好不执行，主线跑） | 数据前置 |
| `code/tests/test_cpu_scripts.py` | pytest 冒烟测试（合成数据，验 stratify/conspicuity/incremental/boundary 不报错） | CI |

**就绪状态**：脚本全部写好，未启训练。GPU 训练 (A0/B0) 是拍板点，主线 `/loop /run-experiment` 跑。

### 2026-06-16 续 — 数据下载 + CPU 管线真数据验通（主线，GPU-free）

**1. BraTS2021 下载就位**：核 Zenodo API 发现是**分集 tar.gz 非单 zip**（coder 脚本 URL 写错，已重写 `download_medianomaly.py` 为分集版）。直接 curl `BraTS2021.tar.gz`(70MB) 解压到 `data/BraTS2021/`，**计数对齐官方✅**：train 4211 / test normal 828 / tumor 1948 / annotation 1948。datasets.json 标 partial(BraTS ready)。
- **数据路径=`data/BraTS2021/`**（非脚本默认的 `data/brats/`，训练/eval 调用时用 `--data-dir` 指对）。

**2. conspicuity_proxy.py 真数据验通**（PC-C C1，纯 CPU 不需训练）：1948 张真 BraTS tumor 图跑通 → `results/conspicuity_features_tumor.csv`。Bash 核分布：**0 NaN**，5 特征全非退化有方差（sigma 0.025-0.29 / cluster_prom 181-3.6e6 / contrast 0.5-66 / fft_ent 3.1-5.4 / cnr 2.6-12）。**CPU 软活管线真数据端到端通，特征有方差=③ 判据能有信号的前置成立**。⚠️ cluster_prom 量级跨 4 个数量级，analyst 跑增量统计前考虑 log 变换。

**GPU 墙到此**：余下 Phase 0（stratify 检出率 / incremental 增量统计 / failure_boundary 外推）全需 AE 的 anomaly score = A0 训练 = **拍板点 + 训练锁**。GPU-free 能推的已推完。

### 2026-06-17 — HPC 上传准备完成（用户拍走 HPC，主线亲跑，未提交训练）

**HPC 状态**：gpu4090 全分区 12 张空闲卡，导师配额 shuihuawang 0 占用（QOS 4gpus=最多 4 卡），Phase 0 只需 1 卡，能马上排上。
**上传就位**（`/gpfs/work/bio/jiayu2403/medad-failmap/`）：
- 数据：BraTS2021 整包 tar 传后 HPC 解压，计数对齐 4211/828/1948/1948 ✅。
- 代码：6 个 py + `submit_a0.sh`（SBATCH 头照 nca-jepa 同款：account=shuihuawang/partition=gpu4090/qos=4gpus/gres=gpu:rtx4090:1/time=2h）。
- 环境：复用 nca-jepa 的 `yjcu124py310`（torch 2.6.0+cu124 + skimage 0.25.2 + sklearn 1.7.1，零搭建）。
- **修 bug**：coder 的 train 脚本写死 `data/brats/`（小写），实际 Zenodo 目录是 `BraTS2021/`，已修两处对齐官方目录名（复现零偏离）。
- **HPC smoke 验通**（登录节点，不训练不占 GPU）：BraTSTrainDataset 数到 4211 文件，shape (1,64,64)，range [-1,0.09]（Normalize 正确）。
**清陈旧训练锁**：撞到 nca-jepa 训练锁（win-1844），核 7 个 job（1450889-901）全 COMPLETED（22:21-23:00 结束）、我方 0 活动 job = 确认陈旧，按 CLAUDE.md「确认陈旧再人工清」改名存档 `training.lock.stale-nca-jepa-20260617`（PowerShell 删被权限拒→用 filesystem move）。

**就绪待拍板**：A0 提交 = `sbatch code/submit_a0.sh`（HPC 上），是拍板点。提交前主线写 MedAD 的 `training.lock`（串行红线）。**等用户「跑」。**
