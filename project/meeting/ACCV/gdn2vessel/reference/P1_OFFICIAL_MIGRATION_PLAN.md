# P1 血管主实验官方化迁移 plan（拆自搓外壳）

**日期**：2026-06-22
**服务**：gdn2vessel P1 主实验（DRIVE/CHASE/STARE/FIVES/HRF + 冠脉）。
**触发**：用户质疑「自搓外壳惯性」→ 把基础设施全换官方,只留 4 个 novelty 件自搓。
**配套**：[`OFFICIAL_CODE_REUSE.md`](OFFICIAL_CODE_REUSE.md)（库清单）。
**时序铁律**：**等 MQAR go/no-go 判决出、headline 定了再启动本 plan**。若判决 DEAD→退路 B（Frangi 门），主实验框架也随之调（headline 不同,backbone 不变但 claim 变）。现在先把 plan 备好,不空等。

---

## 0. 为什么官方化（三个硬伤）

1. **backbone 自搓 vanilla CNN、无 ImageNet 预训练** → 审稿人第一枪「没用预训练所以 Dice 不可比」。
2. **训练超参偏离官方**（lr=1e-3 vs FR-UNet 官方 1e-4、BCE+Dice vs 纯 BCE）→ 复现红线。
3. **自搓 dataloader 踩坑**（cv2 返回全零、.gif mask、green channel）→ 隐性 bug 源。

novelty **不受影响**（4 件自搓:Frangi 门 / re-ID 头 / GDN2 bottleneck / SR·re-ID 指标）——官方化只换基础设施。

---

## 1. 框架选型决策：2D smp 预训练 encoder（不用 3D nnU-Net）

**判断**：我们数据**全 2D**（眼底 + 2D 冠脉造影）→ 用 **segmentation_models_pytorch（smp）2D 预训练 encoder** 当 backbone。
- ✅ 得 ImageNet 预训练 encoder（resnet34/efficientnet-b0,审稿第一枪解掉）。
- ✅ 灵活——GDN-2 记忆插 encoder 最深层 bottleneck,smp encoder-decoder 中间可手动接。
- ❌ **不用 nnU-Net**:它是 3D 医学黄金标准 + 全自动黑盒,2D 眼底过重,且自配架构难插自定义 GDN-2 bottleneck（继承 trainer 覆盖 build_network_architecture 受 deep supervision/动态 patch 约束）。
- 🟡 MONAI 2D 备选（更灵活但要自己组 + 写 Engine）,smp 更省。

**GDN-2 插法（保留现机制）**：smp encoder 输出 bottleneck feature (B,C,H/16,W/16) → 插 `GDN2MemoryModule`（flatten ≤1024 token 约束不变,patch=512→32×32=1024 边界）→ 喂 smp decoder 或自定义 decoder。
> **TODO（实施前 researcher 核）**：smp 是否支持在 encoder/decoder 之间插自定义模块,还是要 `smp.encoders.get_encoder()` 拿 encoder + 手搭 decoder。smp encoder 各 stage 输出维度对 GDN-2 d_model。

---

## 2. 逐件迁移表

| 组件 | 现状（自搓） | 换成官方 | 怎么接 | 状态 |
|---|---|---|---|---|
| **backbone** | `models/unet.py` vanilla CNN 无预训练 | **smp.Unet(encoder_name='resnet34'/'efficientnet-b0', encoder_weights='imagenet')** | encoder 拿 bottleneck → 插 GDN-2 → decoder | 🔴 换 |
| **data 加载+预处理** | `datasets/` 自搓（cv2/gif 坑） | **抄 [FR-UNet](https://github.com/lseventeen/FR-UNet) `data_process.py`**（视网膜+冠脉全覆盖,patch48/stride6/二值化≥100）+ **[orobix](https://github.com/orobix/retina-unet) 预处理**（CLAHE clipLimit=2.0/tile8×8 + gamma1.2 + 标准化） | 复用其 dataloader,适配我们 HPC 数据路径（查 `.portfolio/datasets.json`） | 🔴 换 |
| **训练超参** | lr=1e-3,BCE+Dice | **对齐 FR-UNet config.yaml**:lr=1e-4,Adam wd=1e-5,CosineAnnealingLR T_max=40,**纯 BCE**（或明示偏离理由） | 改 train loop 超参 | 🔴 对齐 |
| **数据增强** | 简单 | 翻转+旋转**为主**（薄血管对强增强脆弱,debuggercafe 实证;别上 sunflare/弹性） | albumentations 轻增强 | 🟡 调 |
| **拓扑指标** | wrapper | clDice/Skeleton-Recall/Betti 官方 | 已对接 ✓ | 🟢 保持 |
| **断点合成** | synth_breaks | creatis `disconnect.py` | 已对齐 ✓ | 🟢 保持 |
| **baseline** | — | FR-UNet/各 SOTA 官方 repo copy 入 third_party | 已做 ✓ | 🟢 保持 |

---

## 3. 4 个 novelty 件（自搓保留,插进官方 backbone）

| novelty | 插法 |
|---|---|
| `GDN2MemoryModule`（delta 记忆,Claim 1） | 插 smp encoder bottleneck（最深层）|
| `DifferentiableFrangi` 解耦门（Claim 3） | bottleneck feature 算 vesselness → 调制 GDN-2 写/擦门（机制不变,§3.4 措辞按 THEORY_FOUNDATION §6 改「正交解耦轴」）|
| `ReIDReadoutHead`（Claim 2） | 接 memory 输出 + decoder feature → 同根匹配（**待 MQAR 判决:若 delta 非特异,re-ID 头能否保留看路 A/B**）|
| SR·re-ID 指标 | 评估层自搓（无官方）|

---

## 4. 关键 TODO（实施前 researcher 核,不臆想）
1. smp 插自定义 bottleneck 的精确接口（get_encoder + 手搭 decoder vs 改 smp.Unet 内部）。
2. smp encoder bottleneck 输出空间分辨率 vs GDN-2 ≤1024 token 约束（patch size 怎么配）。
3. FR-UNet `data_process.py` 适配我们 5+ 数据集路径 + 冠脉格式。
4. ImageNet 预训练 encoder（3 通道 RGB）对眼底（green channel/灰度）的输入适配（3ch vs 1ch）。
5. 顶会 2D 眼底血管分割用预训练 backbone 的先例（smp/timm encoder 采用度）。

---

## 5. 不做 + 验证
- **不做**：3D nnU-Net（不对口）、重写已对接的指标/断点合成、为换框架而推迟 headline 验证（MQAR 优先）。
- **验证**：迁移后主 Dice **不低于**自搓版（smp 预训练应更高）；训练超参三方对齐 FR-UNet 官方;复现零偏离。

> 本 plan 是「headline 定了之后」的主实验地基。当前优先级仍是 MQAR go/no-go（纯 Zoology 烟测排队中）。判决出→据 LIVE/DEAD 定 headline→启动本 plan。
