# Med-NCA 项目日志（时间倒序）

---

## 2026-06-02 — 会话 2：环境修复 + 数据解压 + smoke test 通过

**完成**：
- 验 CUDA：torch 2.7.0+cu126，`torch.cuda.is_available()` = True ✅
- 补装缺失依赖：nibabel 5.4.2 + torchio 1.2.0（官方代码依赖，REPRO_PLAN 未列）
- ISIC GT 解压：2596 files ✅
- ISIC Input 解压（11GB）：2596 files ✅（Input/GT 配对完整）
- **R1 smoke test（2 epoch）全路径通过**：数据加载 → 训练 → per-patient Dice eval → CSV + JSON，零崩溃
  - R3 params = 25,920 **PASS <100K** ✅
  - 2 epoch Dice = 0.525（正常，未收敛）

**下一步（会话 3 开门即办）**：
1. 启 R1 正式训练（R1_EPOCHS=300，Start-Process 新窗口）
2. 训练约 38h（7.6 min/epoch × 300），每 25 epoch 自动 eval，50 epoch 存 ckpt
3. 完成后读 `results/r1_hippocampus_single_summary.json` 看 Dice vs 0.86 threshold

---

## 2026-06-02 — 会话 1：计划重定位 + 框架迁移 + 官方代码落地

**完成**：
- 读官方 `M3D-NCA-official`（已 clone，shallow）核对架构 —— 发现与 PDF 两处差异：`BasicNCA` 用固定 Sobel 感知（非 learned conv），example loss 是 DiceBCELoss（PDF 说 Dice Focal）。真实超参 lr=16e-4 / betas=(0.5,0.5) / batch=48 / 2-level [(16,16),(64,64)]。
- 写 `REPRO_PLAN.md`：把大项目 6 件套纪律（红线/跑偏/数字溯源/工程血泪/量化验收/lever）迁入。策略定为「最小复现(R1 Hippocampus + R2 一个 2D + R3 参数量<100K)→快速转创新」，独立顶会论文定位，混合算力。
- 建工作目录骨架：`code/ configs/ data/ results/ checkpoints/`。
- 探本地环境：conda 24.11.3 / RTX 4070 Laptop 8GB（够 2D + Hippocampus，3D 大体积留 HPC）。

**收工状态（10:20）**：
- ✅ 数据：Hippocampus 解压 260 img/label 配对（清掉 macOS `._*` 垃圾）；ISIC GT 全✓；**ISIC input 续传中 3.69GB/11.16GB**（`code/resume_isic.ps1` curl -C - 循环，断点续传生效）
- ✅ R1 脚本就绪 `code/run_r1_hippocampus.py`（基于官方 example + per-patient Dice csv + bootstrap CI + R3 参数量核对，阈值 Dice≥0.86）
- ⚠️ **env CUDA torch 阻塞，真因 = C 盘满**：conda mednca(py3.9) + requirements 装好，但 cu118 torch（2.5GB wheel）四次装失败。前三次误判为 spec/CPU-fallback；第四次 log 暴露真因 `[Errno 28] No space left on device`。
  - **`df -h`：C 盘 99% 满，仅剩 2.3GB**；conda env 默认在 C 盘 → 2.5GB cu118 torch 装不下。
  - D 盘 328GB 空闲（ISIC 下载在 D，无辜，非元凶）。
  - 现 torch 被卸空（env 里暂无 torch 模块，属正常中间态）。

**下一步（开门即办，严格按序）**：
1. ✅ env 留 C 盘。`conda clean --all` 已腾出 7.5GB；cu118 torch 在装（log `code/torch4.log`）。
2. 验 `python -c "import torch; print(torch.cuda.is_available())"` == True
3. CPU/GPU 各跑通官方 1 batch（`R1_EPOCHS=2` smoke 验代码路径）
4. 发 R1 正式训练（`R1_EPOCHS=300` 起，Start-Process 开窗 + log 轮询）→ per-image Dice vs 0.86
5. ISIC 续传完（`code/resume_isic.ps1` 应已补满 11.16GB）→ 解压 → R2 2D 适配（RGB + resize 256）

**血泪 +1**：大下载/装包前先 `df -h` 看盘；C 盘<6GB 别在 C 盘 env 装 CUDA torch。已记入 REPRO_PLAN §9 待补。

**红线提醒**：Phase 0 三项（R1+R2+R3）PASS 前不碰创新代码。
