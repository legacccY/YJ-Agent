# Med-NCA 项目日志（时间倒序）

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
1. **解 C 盘空间**（任选）：
   - (a) 推荐：把 conda env 建到 D 盘 → `conda create -p D:\YJ-Agent\project\meeting\Med-NCA\envs\mednca python=3.9`，再装 torch cu118 + requirements（pip 缓存/TMP 也指 D：`$env:TMP="D:\tmp"; $env:PIP_CACHE_DIR="D:\pipcache"`）
   - (b) 或清 C 盘腾 ≥6GB（清 pip/conda cache、temp、回收站）后原 env 重装 cu118
2. 验 `python -c "import torch; print(torch.cuda.is_available())"` == True
3. CPU/GPU 各跑通官方 1 batch（`R1_EPOCHS=2` smoke 验代码路径）
4. 发 R1 正式训练（`R1_EPOCHS=300` 起，Start-Process 开窗 + log 轮询）→ per-image Dice vs 0.86
5. ISIC 续传完（`code/resume_isic.ps1` 应已补满 11.16GB）→ 解压 → R2 2D 适配（RGB + resize 256）

**血泪 +1**：大下载/装包前先 `df -h` 看盘；C 盘<6GB 别在 C 盘 env 装 CUDA torch。已记入 REPRO_PLAN §9 待补。

**红线提醒**：Phase 0 三项（R1+R2+R3）PASS 前不碰创新代码。
