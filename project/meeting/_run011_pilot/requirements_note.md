# requirements_note.md

run-011 G5 pilot 依赖说明（不单独建 venv，主线用现有 cu126 环境）

## 必须已装
| 包 | 用途 | 状态 |
|---|---|---|
| torch >= 2.0 + CUDA | 训练 / AMP / GradScaler | TODO: 确认已装（gdn2vessel cu126 环境应有） |
| SimpleITK | 读 .mha 文件 | TODO: `pip install SimpleITK` 若未装 |
| numpy | 数组操作 | 通常随 torch 附带 |
| Pillow | 图像 resize（dataset.py 用 PIL.Image） | 通常已装 |
| scipy | HD95 计算（distance_transform_edt） | TODO: `pip install scipy` 若未装（仅用 ndimage，不经 OMP） |

## 安装命令（在已有 cu126 环境中）
```
pip install SimpleITK scipy Pillow
```

## 不需要
- torchvision（未用）
- matplotlib / pandas（结果写 CSV，不需图表，主线/analyst 后处理）

## 版本兼容性
- Python >= 3.9
- torch >= 2.0（AMP GradScaler API）
- SimpleITK >= 2.0（GetArrayFromImage）

## 注意
- `scipy.ndimage.distance_transform_edt` 不经 OpenMP 线程池，不会触发 OMP Error #15（与 torch 共存安全）
- Windows: DataLoader num_workers=0，pin_memory=False（pilot_g5.py 已硬编码）
- OMP_NUM_THREADS=1 已在 pilot_g5.py 顶部 `os.environ.setdefault` 设置
