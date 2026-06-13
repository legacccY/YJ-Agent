# E10 — 6 SOTA baseline 权重 + arch 下载清单

zero-shot 路线：官方预训练权重直接 inference。红线：全 6 个非扩散。
HPC 目标根目录：`/gpfs/work/bio/jiayu2403/visienhance/`
- arch 逐字 vendor 到 `code/baselines/archs/<method>_arch.py`（权重 key 精确匹配）
- 权重放 `checkpoints/baselines/<method>/<file>.pth`

口径：每方法 wrapper 输入退化图 256×256 RGB[0,1] → enhance → 256 RGB[0,1]。
选「去噪/去模糊/复原」任务权重优先（皮肤镜退化 = 模糊+噪声+低对比，落这些分布内）。

---

## 1. Restormer (CVPR22, swz30/Restormer)
- **arch raw**：`https://raw.githubusercontent.com/swz30/Restormer/main/basicsr/models/archs/restormer_arch.py`
- **权重**：`real_denoising.pth`（真实噪声去噪，最贴皮肤镜）— Google Drive，链接见 repo `Denoising/README.md`（用 gdown）
  - 备选 deblur：`motion_deblurring.pth`
- **目标**：`checkpoints/baselines/restormer/real_denoising.pth`
- **输入**：[0,1] RGB，全卷积+transformer 任意尺寸，256 直接过；构造 `Restormer(LayerNorm_type='BiasFree')` 默认参数与权重匹配。

## 2. NAFNet (ECCV22, megvii-research/NAFNet)
- **arch raw**：`https://raw.githubusercontent.com/megvii-research/NAFNet/main/basicsr/models/archs/NAFNet_arch.py`
- **权重**：`NAFNet-SIDD-width64.pth`（去噪）— Google Drive，链接见 repo README
  - 备选 deblur：`NAFNet-GoPro-width64.pth`
- **目标**：`checkpoints/baselines/nafnet/NAFNet-SIDD-width64.pth`
- **构造**：width=64, enc_blk_nums=[2,2,4,8], middle_blk_num=12, dec_blk_nums=[2,2,2,2]（SIDD-width64 配置，须与权重对齐）。ckpt key 在 `params`。
- **注**：与我方 VisiEnhanceNet 同源（NAFBlock）→ 最干净消融线「NAFNet 原版 vs +FiLM+DP」。

## 3. MIRNet-v2 (TPAMI22, swz30/MIRNetv2)
- **arch raw**：`https://raw.githubusercontent.com/swz30/MIRNetv2/main/basicsr/models/archs/mirnet_v2_arch.py`
- **权重**：`enhancement_lol.pth`（低光增强）或 `real_denoising.pth` — Google Drive，repo README
- **目标**：`checkpoints/baselines/mirnetv2/enhancement_lol.pth`
- **构造**：`MIRNet_v2()` 默认参数。低光权重与皮肤镜有 domain gap，预期 zero-shot 较弱（正好对比）。

## 4. SwinIR (ICCVW21, JingyunLiang/SwinIR)
- **arch raw**：`https://raw.githubusercontent.com/JingyunLiang/SwinIR/main/models/network_swinir.py`
- **权重（直链 github release）**：彩色去噪
  `https://github.com/JingyunLiang/SwinIR/releases/download/v0.0/005_colorDN_DFWB_s128w8_SwinIR-M_noise25.pth`
- **目标**：`checkpoints/baselines/swinir/005_colorDN_DFWB_s128w8_SwinIR-M_noise25.pth`
- **构造（colorDN-M）**：`SwinIR(upscale=1, in_chans=3, img_size=128, window_size=8, img_range=1., depths=[6]*6, embed_dim=180, num_heads=[6]*6, mlp_ratio=2, upsampler='', resi_connection='1conv')`。256%8==0 OK；边长须被 window_size 整除（用 base_enhancer.pad_to_multiple 兜底）。

## 5. Uformer (CVPR22, ZhendongWang6/Uformer)
- **arch raw**：`https://raw.githubusercontent.com/ZhendongWang6/Uformer/main/model.py`
  （依赖 `https://raw.githubusercontent.com/ZhendongWang6/Uformer/main/modules.py` 等，一并 vendor）
- **权重**：`Uformer_B.pth`（SIDD 去噪）— Google Drive，repo README
- **目标**：`checkpoints/baselines/uformer/Uformer_B.pth`
- **构造**：`Uformer(img_size=256, embed_dim=32, win_size=8, token_projection='linear', token_mlp='leff', depths=[1,2,8,8,2,8,8,2,1], modulator=True)`（Uformer-B 配置，须对齐权重；以 repo README 为准）。

## 6. Real-ESRGAN (ICCVW21, xinntao/Real-ESRGAN)
- **arch**：用 basicsr `RRDBNet`
  `https://raw.githubusercontent.com/xinntao/Real-ESRGAN/master/realesrgan/archs/srvgg_arch.py`（轻量）
  或 RRDBNet（`from basicsr.archs.rrdbnet_arch import RRDBNet`，HPC 装 basicsr）
- **权重（直链 github release）**：
  `https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth`
- **目标**：`checkpoints/baselines/realesrgan/RealESRGAN_x2plus.pth`
- **构造**：`RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=2)`，ckpt key `params_ema`。
- **增强用法**：SR 模型 → `base_enhancer.sr_roundtrip(x, model_fn, scale=2)`（downsample 1/2 → SR ×2 回 256）。

---

## 下载脚本骨架（HPC，一次性）
```bash
cd /gpfs/work/bio/jiayu2403/visienhance/checkpoints/baselines
# github release 直链
wget -P swinir/     https://github.com/JingyunLiang/SwinIR/releases/download/v0.0/005_colorDN_DFWB_s128w8_SwinIR-M_noise25.pth
wget -P realesrgan/ https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth
# Google Drive (Restormer/NAFNet/MIRNetv2/Uformer) → pip install gdown; gdown <id 见各 repo README>
```

## 状态
- [x] arch vendor（6 个，agent 并行）+ 6 wrapper 落地 — 本地 import+构造+forward 256→256 全过
  - Restormer 26.1M / NAFNet 116M / MIRNet-v2 5.9M / SwinIR-M 11.5M / Uformer-B 50.9M / RRDBNet 16.7M（param 量对齐官方）
- [ ] 权重下载（HPC，主线串行；github 直链 2 个 + gdrive 4 个需 gdown）
- [ ] 上传 baselines/ + run_e10_baseline_hpc.py 到 HPC code/
- [ ] 登录节点 CPU 验 load_state_dict 0 missing key（strict=True 已设，权重 key 不对会立报）
- [ ] `python run_e10_baseline_hpc.py --method <m>` 逐个跑（GPU job，~半天 6 个）
