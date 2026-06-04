# Med-NCA 环境规格说明

**生成时间**：2026-06-03  
**用途**：一键重建 mednca conda 环境的参考基线，供复现验收 E2「环境锁定」使用。

---

## 操作系统

- Windows 11 Home China，内核版本 10.0.26100.3775

---

## 硬件 / 驱动

| 项目 | 值 |
|------|-----|
| GPU 型号 | NVIDIA GeForce RTX 4070 Laptop GPU |
| 显存 | 8188 MiB（约 8 GB） |
| 驱动版本 | 576.02 |

---

## Conda 环境

| 项目 | 值 |
|------|-----|
| 环境路径 | `D:\Anaconda\envs\mednca` |
| Python 版本 | 3.9.25 |

---

## 关键框架版本

| 包 | 版本 |
|----|------|
| torch | 2.7.1+cu118（CUDA 11.8 编译版） |
| torchvision | 0.22.1+cu118 |
| CUDA runtime | 11.8 |
| cuDNN | 9.1.0.0（version() = 90100） |

---

## 项目核心依赖

| 包 | 版本 | 说明 |
|----|------|------|
| nibabel | 5.3.3 | 医学图像 NIfTI/NRRD 读写，原始代码依赖 |
| torchio | 0.18.82 | 3D 医学图像数据增强/采样，原始代码依赖 |
| simpleitk | 2.5.5 | 医学图像 I/O 与处理 |
| unet | 0.8.1 | 基线对比模型 |
| scipy | 1.13.1 | 统计指标计算 |
| numpy | 2.0.2 | 数值计算 |
| opencv-python | 4.13.0.92 | 图像处理辅助 |

> nibabel 和 torchio 是会话 2 补装的，原始环境可能不含，复现时需手动 pip install。

---

## 完整依赖清单

见同级目录 `requirements.lock`（由 `pip freeze` 直接导出，70 个包）。

一键重建命令：

```bash
# 1. 创建 conda 环境
conda create -n mednca python=3.9.25 -y

# 2. 安装 PyTorch（cu118 版，与原始环境一致）
pip install torch==2.7.1+cu118 torchvision==0.22.1+cu118 \
    --index-url https://download.pytorch.org/whl/cu118

# 3. 安装其余依赖
pip install -r requirements.lock
```

> 注意：`requirements.lock` 中 `torch` 和 `torchvision` 带 `+cu118` 后缀，普通 PyPI 找不到，步骤 2 必须先单独从 PyTorch 官方 wheel 安装，再执行步骤 3（pip 会跳过已满足的版本）。

---

## Windows 复现注意事项

### OMP / KMP 线程冲突

Windows 上同时加载多个 OpenMP 实现（Intel MKL + LLVM）会触发报错：

```
OMP: Error #15: Initializing libiomp5md.dll, but found libiomp5md.dll already initialized.
```

解决方式：在训练脚本最顶部或启动命令前设置环境变量：

```python
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
```

或在 PowerShell 中：

```powershell
$env:KMP_DUPLICATE_LIB_OK = "TRUE"
python train.py ...
```

### 多进程 DataLoader

Windows 使用 `spawn` 而非 `fork`，DataLoader 的 `num_workers > 0` 时必须在 `if __name__ == "__main__":` 保护块内调用，否则子进程会递归启动。

### 路径分隔符

代码中硬编码路径建议用 `pathlib.Path` 或 `os.path.join`，避免 `\` 转义问题。

---

## 验收状态

- [x] E2 环境锁定：requirements.lock 已生成（70 个包，pip freeze 原样导出）
- [x] torch cu118 版本确认
- [x] GPU 驱动与显存记录
