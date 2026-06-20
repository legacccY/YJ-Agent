# BASELINE_ENV_READINESS.md
# P3 主实验 HPC 环境就绪清单

**更新日期**：2026-06-20
**对应矩阵**：`PLAN/PHASE_3_MATRIX.md` §1 进档 A 的 12 baseline + ours_gdn2

---

## 一张表：每个 baseline → env_tag → 现状

| # | registry name | env_tag | env 名 | 需装什么 | HPC 现状 | 本地烟测 |
|---|---|---|---|---|---|---|
| 1 | `fr_unet` | main | gdn2venv | 已在 gdn2venv | ✅ 就绪 | ✅ PASS |
| 2 | `cs_net` | main | gdn2venv | 已在 gdn2venv | ✅ 就绪 | ✅ PASS |
| 3 | `dscnet` | main | gdn2venv | 已在 gdn2venv | ✅ 就绪 | ✅ PASS |
| 4 | `creatis_postproc` | main | gdn2venv | monai（见下） | ⬜ 待装 monai | ✅ PASS（本地有 monai） |
| 5 | `cldice` | main | gdn2venv | 已在 gdn2venv | ✅ 就绪 | ✅ PASS |
| 6 | `cbdice` | main | gdn2venv | 已在 gdn2venv | ✅ 就绪 | ✅ PASS |
| 7 | `skeleton_recall` | main | gdn2venv | 已在 gdn2venv（skimage）| ✅ 就绪 | ✅ PASS |
| 8 | `vm_unet` | **mamba** | mamba_venv | mamba-ssm + causal-conv1d | ⬜ 待建 mamba_venv | ✅ RuntimeError 正确报 mamba_venv_needed |
| 9 | `u_mamba` | **mamba** | mamba_venv | mamba-ssm + nnunetv2 + U-Mamba | ⬜ 待建 mamba_venv | ✅ RuntimeError 正确报 mamba_venv_needed |
| 10 | `mm_unet` | **mamba** | mamba_venv | mamba-ssm + causal-conv1d + monai | ⬜ 待建 mamba_venv | ✅ RuntimeError 正确报 mamba_venv_needed |
| 11 | `nnunet` | main | gdn2venv | pip install nnunetv2 | ⬜ 待装 nnunetv2 + Dataset 格式转换 | ✅ RuntimeError 正确报 nnUNetv2_needed（本地已有 nnunetv2，仍 RuntimeError 因框架不可独立 build） |
| 12 | `pasc_net` | main | gdn2venv | nnunetv2 + PASC-Net trainer | ⬜ 待装 + 🛑拍板 | ✅ RuntimeError 正确报 nnUNetv2_needed |
| — | `ours_gdn2` | main | gdn2venv | 已在 gdn2venv | ✅ 就绪 | ✅ PASS |

---

## 分组说明

### A. gdn2venv 系（main, 10 个）— batch-1 直接可跑

已在 HPC `gdn2venv` 就绪，直接挂 batch-1：
- **架构类**：`fr_unet`, `cs_net`, `dscnet`, `creatis_postproc`（需 monai，见下）, `ours_gdn2`
- **loss 类**：`cldice`, `cbdice`, `skeleton_recall`

**例外：creatis_postproc 需装 monai**
```bash
# HPC gdn2venv 中补装
pip install monai
# 验证
python -c "import monai; print(monai.__version__)"
```

**例外：nnunet / pasc_net 需 nnunetv2 + 数据转格式**
```bash
# 安装 nnunetv2
pip install nnunetv2

# PASC-Net 额外 trainer
git clone https://github.com/IPMI-NWU/PASC-Net
cd PASC-Net && pip install -e .

# 4 集转 nnUNet Dataset 格式（4 个命令，待主线拍板格式约定）
# nnUNetv2_plan_and_preprocess -d <dataset_id> --verify_dataset_integrity
# nnUNetv2_train <dataset_id> 2d 0 --tr nnUNetTrainer    # nnunet
# nnUNetv2_train <dataset_id> 2d 0 --tr PASCTrainer      # pasc_net
# nnUNetv2_predict ...                                    # 推理输出 → evaluate.py
```

> ⚠️ **nnunet/pasc_net 训练走 nnUNetv2 命令行（非 train_harness.py），评估桥接方案待主线拍板（PHASE_3_MATRIX §5）。建议排 batch-2，batch-1 不含。**

---

### B. mamba_venv 系（mamba, 3 个）— 需独立 venv build

`vm_unet`, `u_mamba`, `mm_unet` 依赖 mamba-ssm CUDA kernel（需 sm_89 编译）。

**Build 步骤（HPC gpu4090, sm_89）：**
```bash
# 1. 创建独立 venv（与 gdn2venv 隔离）
conda create -n mamba_venv python=3.10 -y
conda activate mamba_venv

# 2. 装 PyTorch（HF cu126 wheel，与 gdn2venv 对齐）
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126

# 3. 装 mamba-ssm（BASELINE_SPEC §3，sm_89 关键）
TORCH_CUDA_ARCH_LIST="8.9" pip install mamba-ssm --no-build-isolation
pip install causal-conv1d

# 4. 验证烟测
python -c "from mamba_ssm import Mamba; print('mamba_ssm OK')"

# 5. 装 monai（mm_unet 需要）
pip install monai

# 6. 装 nnunetv2（u_mamba 需要）
pip install nnunetv2
git clone https://github.com/bowang-lab/U-Mamba && cd U-Mamba && pip install -e .

# 7. 装 gdn2vessel 项目依赖（adapter 代码共享）
pip install -e /gpfs/work/bio/jiayu2403/gdn2vessel/  # 或 PYTHONPATH 指向
```

**build 不通降档处理**：若 mamba_venv build 失败（sm_89 / CUDA 版本不兼容），
vm_unet/u_mamba/mm_unet 降档 C，引文献数字，标「非同框架复现」。不阻塞 batch-1。

---

## HPC 批次编排（对应 PHASE_3_MATRIX §4）

```
batch-1（立即可跑，main 8 run + FIVES 探针）：
  前提：train_harness.py 建成（最高优先阻塞）
  env:   gdn2venv
  cover: DRIVE × {fr_unet, cs_net, dscnet, creatis_postproc*, cldice, cbdice, skeleton_recall, ours_gdn2} × seed42
  注:    creatis_postproc 需先 pip install monai in gdn2venv

batch-2（batch-1 校准通过后）：
  env:   gdn2venv（主流）+ mamba_venv（若 build 通）
  cover: DRIVE × seed{1,2} + {CHASE, STARE, FIVES} × 全 baseline × 3 seed
  nnUNet 桥接拍板后并入

batch-3（续连轴 benchmark）：
  cover: 全 baseline 在 P1 断点 benchmark 上跑 ε_β0/SR/re-ID
  依赖:  P1 断点协议冻结 + precompute_benchmark.py（STARE/HRF/FIVES）
```

---

## 状态总结

| 状态 | baseline 数 | 说明 |
|---|---|---|
| ✅ gdn2venv 就绪（batch-1 可直接用） | 7 | fr_unet/cs_net/dscnet/cldice/cbdice/skeleton_recall/ours_gdn2 |
| ⬜ 待装 monai（简单 pip install） | 1 | creatis_postproc |
| ⬜ 待装 nnunetv2 + 转格式 + 🛑拍板 | 2 | nnunet/pasc_net（batch-2 前拍板）|
| ⬜ 待建 mamba_venv（sm_89 build） | 3 | vm_unet/u_mamba/mm_unet（batch-1 后并入）|

**batch-1 阻塞命脉：train_harness.py 建成（PHASE_3_MATRIX §0 阻塞-1）。**
所有 adapter 本地烟测已全过（test_baseline_build_smoke.py: 502 passed, 7 skipped）。
