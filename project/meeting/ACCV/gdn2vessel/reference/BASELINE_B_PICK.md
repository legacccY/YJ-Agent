# 档 B 补位 baseline 核源（baselineB-pick，winG）

**服务**：lever L3（保 ≥12 baseline 超量）。承 2026-06-20 裁定 = MambaVesselNet++ 降档 C（repo 只 3D Conv3d 无 2D path），从档 B 提 1 个有 2D 实现的 SSM/血管 baseline 顶替补位。
**产出**：researcher 核源（官方 repo 源码 + license + DRIVE 超参，复现零偏离红线②，查不到标 TODO），2026-06-20。
**territory**：本档（reference/）。roster 改交主窗合并进 BASELINE_SPEC（不在本棒碰）。

---

## 裁决：选 **MM-UNet（Morph Mamba UNet）** 补位

理由：唯一满足「2D PyTorch 可跑 + SSM + 域对口 + license 清」全条件的候选。SSM 顶替逻辑与降档的 MambaVesselNet++ 一致。

| 候选 | 框架/2D 代码 | license | 主域 | 裁决 |
|---|---|---|---|---|
| **MM-UNet** | ✅ PyTorch 2D SSM 完整实现 | **MIT** | DRIVE+STARE 视网膜血管 | ✅ **补位** |
| SA-UNetv2 | ⚠️ Keras/TF（非 PyTorch）+ notebook 非模块化 .py | ❌ **无 LICENSE** | 视网膜（DRIVE/STARE） | ✗ 框架不匹配 + 无 license + 非 SSM |
| TFFM | ⚠️ 真实 GitHub repo URL **无法定位**（仅 GitHub Pages 静态页） | 代码 license 未知（论文 CC BY） | Fundus-AVSeg 主训，DRIVE 仅 zero-shot | ✗ 代码不可达 + 非 DRIVE 主训 + WACV Workshop 分量低 |

---

## MM-UNet 核源详情（补位采用）

- **repo**：github.com/liujiawen-jpg/MM-UNet
- **框架**：PyTorch，Mamba SSM + Conv2d 2D 实现（`src/UM_Net/MMUNet.py` 26KB，含 `MM_Net`/`MMConv`/`RCG`/`CBAM`/`HPPF`，`bimamba_type="v3"`）
- **2D 代码存在性确认**：`MMUNet.py` + `train.py`（完整训练循环，`monai.losses.DiceFocalLoss`）+ `config.yml`（DRIVE/STARE 超参）+ `data.py`/`loss.py`/`test.py` 全在。**README "Coming soon" 文字过时**（最新 commit 2026-03-09，IEEE Xplore 已正式发表 document/11357047）。
- **license**：**MIT**（`gh api repos/liujiawen-jpg/MM-UNet` → `license.key: mit`）→ vendor + 发表无障碍。
- **超参（论文 arXiv 2511.02193 + config.yml 双核）**：
  - optimizer = AdamW；lr = 0.001，linear warmup 2 ep → cosine annealing → min 1e-7；weight_decay = 0.05（end 0.04）
  - DRIVE：batch_size = 5，input = 608×608，ImageNet 归一化
  - STARE：input = 704×704
  - loss = `monai.losses.DiceFocalLoss`（train.py 实际用；loss.py 里另有 `DICE_BCE_Loss` 未用）

### ⚠️ 跑前 TODO（查不到/矛盾，禁臆想，须人工/烟测确认）
- **epochs 矛盾**：config.yml = 3000 vs 论文正文 = 500 → 以论文 500 为准（config 3000 疑探索值），需 train.sh 或论文复核。
- **DiceFocalLoss 参数**：train.py `monai.losses.DiceFocalLoss(...)` 省略 alpha/gamma 具体值 → 查 train.py 完整参数或用 monai 默认（lambda_dice=1.0, lambda_focal=1.0），标 TODO 不臆造。
- **STARE batch_size 矛盾**：config.yml = 5 vs 论文 = 2 → 以论文 2 为准。
- **8GB 显存可行性**：input 608×608 + Mamba bs5 在本机 RTX4070 8GB **疑 OOM** → 正式训练走 HPC（24GB+ gpu4090）不阻塞；本机只烟测。

---

## 关键引用
- MM-UNet repo — github.com/liujiawen-jpg/MM-UNet（MIT，commit 2026-03-09，PyTorch 2D SSM 完整）
- MM-UNet arXiv 2511.02193 — DRIVE ep500/bs5/608×608/AdamW lr0.001/warmup2+cosine 超参源
- MM-UNet IEEE Xplore document/11357047 — 正式发表，确认 "Coming soon" 过时
- SA-UNetv2 — github.com/clguo/SA-UNetv2（Keras/TF，无 LICENSE，notebook 实现）；arXiv 2509.11774（Adam lr1e-3/bs8/ep150/input592/0.5BCE+0.5MCC/DropBlock0.15）
- TFFM — arXiv 2601.19136 + WACV2026W/P2P（Fundus-AVSeg 主训非 DRIVE，DRIVE zero-shot Dice 82.10；代码仅 tffm-module.github.io 静态页无 repo 直链）

---

## 下一轮新任务（裁决产生，本棒不做）
- coder 加 `mm_unet` adapter（env=mamba，按上表超参 + 跑前 TODO 先清）+ pytest + 烟测。
- 主窗合并：BASELINE_SPEC §0 档 A 把 MambaVesselNet++ 移档 C、A11 槽位填 MM-UNet（保 ≥12）；§1 补 MM-UNet 超参行。
