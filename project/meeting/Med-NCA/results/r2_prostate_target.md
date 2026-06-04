# R2 Prostate 复现靶子溯源

## 论文目标数值

| 指标 | 值 | 来源 |
|------|----|------|
| Med-NCA Prostate Dice | **0.838 ± 0.083** | Med-NCA IPMI 2023, arXiv:2302.03473, Table 1 |
| UNet Baseline Dice | 0.799 ± 0.099 | 同上 |
| 评测口径 | per-volume mean Dice | 同上（与 hippocampus 相同口径） |

PASS 判定（写入脚本注释 + summary.json）：
- 条件 A：bootstrap 1000× 95% CI 含 0.838
- 条件 B：点估 >= 0.81 AND > UNet 0.799

---

## 配置口径结论

### 1. NCA 架构级数

**结论（实证）：Med-NCA prostate 使用与 hippocampus 完全相同的 2-stage coarse→fine 架构，不是不同的"n_level"。**

代码证据：
- `train_Med_NCA.ipynb` cell-5 配置 `'train_model': 1`
- `Agent_Med_NCA.get_outputs()` 第 201 行：`for m in range(self.exp.get_from_config('train_model')+1):`
  → `range(1+1) = range(2)` 即 m=0（coarse）和 m=1（fine）两个 stage
- 文件：`M3D-NCA-official/src/agents/Agent_Med_NCA.py:201`

REPRO_PLAN §4 所说"n_level=2"对应的是这两个 stage（train_model=1），不是第三个额外级别。

### 2. 输入模态数（input_channels）

**结论（实证）：input_channels = 1，仅使用 T2 模态（第 0 通道），忽略 ADC。**

代码证据：
- `Nii_Gz_Dataset_3D.__getitem__()` 第 156-158 行（2D slice 分支）：
  ```python
  if len(img.shape) == 4:
      img = img[..., 0]   # 只取第 0 个模态
  ```
  文件：`M3D-NCA-official/src/datasets/Nii_Gz_Dataset_3D.py:156-158`
- `Dataset_3D.preprocessing()` 第 51 行（另一处保障）：
  ```python
  if len(img.shape) > 2:
      img = img[:, :, 0]  # 同样只取第 0 个模态
  ```
  文件：`M3D-NCA-official/src/datasets/Dataset_3D.py:51`
- 官方注释（同文件第 66 行）：`# TODO: Currently only single volume, no multi phase`

MSD Task05 Prostate 原始数据 shape 为 `(H, W, Z, 2)`（T2+ADC），但框架强制丢弃第 2 模态。

### 3. 标签处理（output_channels）

**结论（实证）：output_channels = 1，整腺二值（whole-gland binary），不区分 PZ/TZ 分区。**

代码证据：
- `Nii_Gz_Dataset_3D.__getitem__()` 第 210 行：
  ```python
  label[label > 0] = 1   # 所有前景（PZ=1, TZ=2）合并为 1
  ```
  文件：`M3D-NCA-official/src/datasets/Nii_Gz_Dataset_3D.py:210`
- `Dataset_3D.preprocessing()` 第 56-57 行（2D 路径相同逻辑）：
  ```python
  if isLabel:
      img[..., 0][img[...,0] != 0] = 1
  ```
  文件：`M3D-NCA-official/src/datasets/Dataset_3D.py:56-57`

论文 Table 1 报告的 0.838 ± 0.083 即整腺 Dice，不是分区域 Dice。

### 4. 每级 input_size

**结论（实证，来自官方 notebook）：**

| Stage | input_size | 说明 |
|-------|-----------|------|
| Coarse (m=0) | (64, 64) | 全图缩放至 1/4 分辨率 |
| Fine (m=1) | (256, 256) | 全分辨率（prostate 图像约 256×256 axial） |

代码证据：
- `train_Med_NCA.ipynb` cell-5：`'input_size': [(64, 64), (256, 256)]`
- `Agent_Med_NCA.get_outputs()` 第 158 行：`down_scaled_size = (int(inputs.shape[1] / 4), int(inputs.shape[2] / 4))`
  → coarse stage 输入自动缩至 1/4，故 fine=256 时 coarse=64，吻合

对比 hippocampus：`input_size=[(16,16),(64,64)]`（海马体图像较小，约 64×64）

### 5. channel_n 差异

**结论（实证）：prostate channel_n = 32（hippocampus 为 16）。**

来源：`train_Med_NCA.ipynb` cell-5：`'channel_n': 32`

注意：channel_n=32 时参数量约为 hippocampus 的 4 倍（约 80K vs 20K），仍在 100K 以内。

---

## 不确定点 / 需进一步核实

1. **batch_size 是否影响复现**：notebook 给出 20，而 paper 未明确指定（可能用了不同值），当前脚本沿用 notebook 的 20。
2. **slice 轴向**：当前用 `slice=2`（z 轴，轴位），与 R1 相同，与 notebook 相同，但 prostate 部分文献偏好矢状位——官方 notebook 无明确指定，沿用轴位。
3. **n_epoch=1000 vs 300**：脚本默认 300，与 R1 相同，等待实测后按需延伸至 1000。

---

## 查阅文件清单

- `M3D-NCA-official/train_Med_NCA.ipynb` — prostate 配置（实证）
- `M3D-NCA-official/src/datasets/Nii_Gz_Dataset_3D.py` — 模态截断 + 标签二值化（实证）
- `M3D-NCA-official/src/datasets/Dataset_3D.py` — preprocessing 模态截断（实证）
- `M3D-NCA-official/src/agents/Agent_Med_NCA.py` — 2-stage 推理逻辑（实证）
- `M3D-NCA-official/src/examples/train_Med_NCA.py` — hippocampus 通用 example（无 prostate 专用）
