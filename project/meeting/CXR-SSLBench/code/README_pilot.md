# CXR-SSLBench Phase 0 pilot harness —— 运行说明（给主线串行执行）

> 服务 CXR-SSLBench Phase 0：验「SSL 范式选择 regime（标注量×域×probe/finetune）依赖」苗头（C1/C3）。
> **coder 已写好、做过 `py_compile` 静态语法检查，但未运行任何代码。以下命令交主线串行跑。**

## 模块结构（`code/`）
| 文件 | 作用 |
|---|---|
| `paths.py` | 中央路径（NIH 图/csv/splits、CheXWorld tar/repo、VinDr、cache/results）。本地优先，退 HPC 候选。 |
| `metrics_auc.py` | 多标签 mAUC + per-class AUC，**纯 numpy**（Windows 规范，避开 scipy/sklearn OMP 冲突）。 |
| `backbones.py` | `load_backbone(name)` 可插拔。已接入 6 个：`chexworld`(已验)、`medical_mae`、`rad_dino`、`imagenet_sup_vitb`、`chess`（写好待主线烟测）、`radjepa`（⚠️未实测，优雅降级）。每个 backbone 带自己的 `fb.transform`（输入尺寸/norm 因模型而异），由 `extract_features` 自动喂给 dataset。 |
| `datasets.py` | `NIHFrozenDataset`（patient-level 无泄漏 split + 14 类多标签 + Patient ID）+ eval transform + spawn loader。`VinDrClsDataset` = 跨域占位（标签 TODO）。 |
| `extract_features.py` | 冻结特征抽取+缓存。`pooled`→.npz（linear）；`tokens`→.npy memmap（attentive，带 size 守卫）。含 `--smoke`。 |
| `probes.py` | `run_linear_probe`（pooled）/ `run_attentive_probe`（tokens，repo 原版 AttentiveClassifier）+ 无泄漏 assert。 |
| `run_pilot.py` | 编排器：grid(backbone×frac×probe)→抽特征→probe→写结果 CSV。 |
| `run_finetune.py` | finetune 启动器，**照搬 FINETUNE.md 官方 recipe**驱动 repo `train_finetune.py`（复现零偏离）。 |

## 依赖前提（主线先确认）
- 跑在 **CheXWorld repo 同环境**（torch/timm 已装；`backbones/probes` 复用 repo `models/jepa_vit`、`models/attentive_pooler`）。
- 本地 splits 若缺，先在 NCA-JEPA 跑 `build_splits.py` 生成 `data/nih_cxr14/splits/`（HPC 已有 `/gpfs/.../nca-jepa/splits/`）。
- 权重 `assets/chexworld_pretrained.tar` 就位（paths.py 已指；HPC 路径待回填）。
- **新增依赖**：`rad_dino`/`radjepa` 需 `transformers`（+ `huggingface_hub`）；`chess` 需 `torchvision`。缺包时该 backbone 加载会被 `run_pilot` 归类为 SKIP，不影响其他 backbone。主线先 `pip show transformers` 确认。

## backbone 权重下载（主线串行，下到 cache/weights/ 后再跑）
```bash
cd D:/YJ-Agent/project/meeting/CXR-SSLBench/code
mkdir -p ../cache/weights

# 1) medical_mae（MAE ViT-B/16，X-rays 0.5M pretrain）—— Google Drive，用 gdown
pip install -q gdown
gdown 10wqOFCkhyWp6JdSFADrH6Xu9e1am3gXJ -O ../cache/weights/medical_mae_vitb.pth

# 2) chess（对比 ResNet50，备选低优先）—— Google Drive
gdown 1IfiuQdKV7en9DFaB0NqNdsDkVbdyoVyD -O ../cache/weights/chess_r50.pth

# 3) rad_dino（DINOv2 蒸馏 ViT-B/14）—— HF 自动缓存，无需手动下；预拉可：
python -c "from transformers import AutoModel, AutoImageProcessor; AutoModel.from_pretrained('microsoft/rad-dino'); AutoImageProcessor.from_pretrained('microsoft/rad-dino')"

# 4) imagenet_sup_vitb（监督对照）—— timm 自动下，无需手动；预拉可：
python -c "import timm; timm.create_model('vit_base_patch16_224.augreg2_in21k_ft_in1k', pretrained=True, num_classes=0)"

# 5) radjepa（I-JEPA ViT-B/14）—— ⚠️未实测可下性，先 curl 验证：
python -c "from huggingface_hub import snapshot_download; print(snapshot_download('AIDElab-IITBombay/RadJEPA'))"
#   能下 -> 烟测核 token 输出 shape 后启用；下不到 -> 该 backbone 自动 SKIP（不阻塞其他）。
```

## 跑前烟测（主线跑，验算子/路径）
```bash
cd D:/YJ-Agent/project/meeting/CXR-SSLBench/code
python paths.py                      # 打印各路径 exists=True/False，先确认数据/权重/repo 解析正确
python -m pytest -q                  # （若主线补了 tests/；当前未附 pytest，见下「待补」）
# GPU 算子烟测：抽 2 batch 特征，不落盘（逐 backbone 验算子 + 核 token shape）
python extract_features.py --backbone chexworld         --domain nih --split 1 --ftype pooled --smoke 2 --num_workers 0
python extract_features.py --backbone medical_mae       --domain nih --split 1 --ftype pooled --smoke 2 --num_workers 0
python extract_features.py --backbone rad_dino          --domain nih --split 1 --ftype pooled --smoke 2 --num_workers 0   # 核 num_tokens=1369（无 register）
python extract_features.py --backbone imagenet_sup_vitb --domain nih --split 1 --ftype pooled --smoke 2 --num_workers 0
python extract_features.py --backbone chess             --domain nih --split 1 --ftype pooled --smoke 2 --num_workers 0   # ResNet50, num_tokens=49, D=2048
python extract_features.py --backbone radjepa           --domain nih --split 1 --ftype pooled --smoke 2 --num_workers 0   # ⚠️未实测，可下则核输出 shape
# 也用 --ftype tokens --smoke 2 各跑一遍，确认 [B,T,D] 形状与 fb.num_tokens 一致（attentive probe 依赖）
```

## 正式跑（主线串行，纯推理+probe，不抢训练卡；attentive 也只训小 head）
```bash
cd D:/YJ-Agent/project/meeting/CXR-SSLBench/code

# 1) linear-probe 全 grid（CheXWorld × 1/10/100% × NIH）—— 主信号 C1/C3
python run_pilot.py --backbones chexworld --label_fracs 1 10 100 \
    --probes linear --domain nih --device cuda --num_workers 4

# 2) attentive-probe（给 JEPA 公平；需 token 缓存，注意体积守卫 --max_gb）
#    probe_test=25596 图 token≈14.7GB；100% probe-train 较大，超 25GB 会被守卫拦，必要时 --force 或先只跑 1/10%
python run_pilot.py --backbones chexworld --label_fracs 1 10 100 \
    --probes attentive --domain nih --device cuda --num_workers 4 --max_gb 25

# 结果累积写入 results/pilot_results.csv（单写者，勿并发起多个 run_pilot 写同一 CSV）
```

## finetune（可选对照，复现零偏离；真训练→走 gpu_slot）
```bash
# 先打印命令核对（不执行）：
python run_finetune.py --data_pct 0.01 --output_dir D:/YJ-Agent/project/meeting/CXR-SSLBench/runs/ft_nih_1pct
# 主线确认后，申请卡槽 + 在 repo 目录真起（或加 --execute）：
# python tools/gpu_slot.py request cxr-sslbench hpc 1 "ft nih 1pct verbatim FINETUNE.md"
# cd D:/YJ-Agent/project/meeting/复现/CheXWorld/repo && <上面打印的 torchrun 命令>
```
> ⚠️ finetune 用 repo 官方 NIH 切分（图级 data_pct，seed 42），与 probe 的 patient-level split 非同套——Phase 0 已知 caveat（见 `run_finetune.py` 头注），recipe 复现优先；Phase 1 统一切分。

## 结果 CSV 列
`backbone, probe_type, label_frac, domain, split, mAUC, per_class_auc(json), seed, n_train, n_test, seconds, timestamp`

## 待主线烟测验证清单（backbone 接入后必核）
- **medical_mae**：烟测看 `load_state_dict` 日志——patch_embed/blocks 不该出现在 missing（只剩 head.* 算正常）。⚠️ medical_mae 自家 eval 是否用 chest 专属 mean/std 待 researcher 核（当前用 ImageNet+Grayscale3，与 chexworld 同口径，CXR-pretrained 公平）。
- **rad_dino**：核 `fb.num_tokens=1369`（518/14=37²），假设无 register token；若 HF 版含 register，token 数会偏移 -> 回填 `_load_rad_dino` 的 strip 逻辑。预处理走官方 AutoImageProcessor（短边 518，零硬编码）。
- **radjepa**：⚠️**未实测可下性**——先跑 README 上面 `snapshot_download('AIDElab-IITBombay/RadJEPA')` 验证；下不到则 `run_pilot` 自动 SKIP（NotImplementedError）。下到后烟测打印 encoder 输出 shape，核 token 格式（是否带 cls / token 数 256），回填 `_load_radjepa`。
- **chess**：⚠️CheSS 官方 eval 归一化未在 findings 给出，当前用 ImageNet+Grayscale3 标准做法；核 mi2rl/CheSS repo 确认后回填 `_build_chess_transform`（低优先备选，不阻塞 ViT 族）。烟测核 `num_tokens=49, D=2048`。

## ⚠️ pooling 一致性 caveat（交 planner/skeptic 确认）
linear-probe 的 pooled 各 backbone 用「该模型规范 pool」：MAE/CheXWorld/CheSS/RadJEPA=mean patch token；**rad_dino/imagenet_sup_vitb=CLS**（按 researcher findings 指定）。跨 backbone pool 不统一是潜在混杂因子；**attentive-probe（token 路径对所有 backbone 统一，head 自学 pool）才是公平主对照**。是否强制统一为 mean 由 planner 拍。

## 等 researcher 回填的 TODO 钩子（接口已留，回填即接）
1. **VinDr 跨域标签**（`datasets.py::VinDrClsDataset` + `VINDR_TO_NIH_LABEL_MAP`）：当前 `train_meta.csv` 无病理标签。回填 = VinDr 官方 image-level 标签 csv 路径 + VinDr→NIH 14 类映射表。
2. **HPC 路径**（`paths.py`）：NIH images 子路径、CheXWorld tar、新增 backbone 权重的 HPC 位置待 ls 确认回填（`_MEDICAL_MAE_WEIGHTS_CANDS` / `_CHESS_WEIGHTS_CANDS` 已留 HPC 候选占位）。
3. **probe-head 超参**（`probes.py` 头注 TODO）：linear/attentive probe 的 lr/epochs/wd 是 harness 惯例默认（**非 CheXWorld 官方**，官方只有 finetune recipe）→ planner/researcher 确认 sweep 协议。

## 待补（主线可选）
- `tests/`：pytest 未附（本 pilot 以 `--smoke` + `run_pilot` 小 grid 真跑验收）。如需，可对 `metrics_auc`（对拍 sklearn）、`datasets.load_nih_label_map`（抽样核标签）、无泄漏 assert 写单测。
