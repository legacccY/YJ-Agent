# FetalSSBench src/

5 方法 x 2 数据集 x 5 比例 x 3 seed = 150 run SSL 基准。

## 文件索引

| 文件 | 用途 |
|---|---|
| `datasets.py` | 统一 dataloader：PSFHS(.mha) + HC18(png+填充mask) |
| `harness.py` | 统一训练 harness，--method 选方法 |
| `run_matrix.py` | 生成 150-run 矩阵 runlist.json，不直接跑 |
| `unet.py` | 2D UNet base_ch=32，~1.9M 参数 |
| `results/` | 运行后生成：results.csv + state.json |

## 数据路径（自动探测）

默认从 `../../_run011_pilot/data/` 读：
- PSFHS: `_run011_pilot/data/PSFHS/PSFHS/{image_mha,label_mha}/`
- HC18: `_run011_pilot/data/HC18/training_set/training_set/` (双层目录)

也可用 `--data_dir` 手动指定。

## 烟测顺序（主线执行，先验后跑）

### Step 0：HC18 mask 填充验证（最大坑，必须先跑）
```
# 进 src/ 目录下跑（从 src/ 目录启动，或绝对路径）
python -c "
from datasets import _fill_annotation_to_mask, _get_hc18_pairs
from pathlib import Path
pairs = _get_hc18_pairs(Path('../../_run011_pilot/data/HC18'))
img_path, ann_path = pairs[0]
mask = _fill_annotation_to_mask(ann_path, 256)
print(f'mask shape: {mask.shape}, unique: {set(mask.flatten().tolist()[:100])}')
print(f'mask sum: {mask.sum()} / {mask.size} pixels')
import numpy as np
assert set(np.unique(mask)).issubset({0,1}), 'mask 值域错误'
print('HC18 mask 填充 OK')
"
```

期望输出：mask sum 在 1000~30000 之间（头部面积），unique = {0, 1}

### Step 1：各方法烟测（5ep，每个约 2-5 min）

```bash
# 从 FetalSSBench/ 根目录执行

# PSFHS 烟测（2 方法即可，PSFHS 沿用 pilot 代码低风险）
python src/harness.py --method supervised --dataset psfhs --quick
python src/harness.py --method mean_teacher --dataset psfhs --quick

# HC18 烟测（每个方法都过一遍，数据路径+mask 是新的）
python src/harness.py --method supervised --dataset hc18 --quick
python src/harness.py --method mean_teacher --dataset hc18 --quick
python src/harness.py --method cps --dataset hc18 --quick
python src/harness.py --method uamt --dataset hc18 --quick
python src/harness.py --method fixmatch --dataset hc18 --quick
```

### Step 2：生成完整 runlist

```bash
python src/run_matrix.py
# 输出: src/runlist.json（150 run）
python src/run_matrix.py --status   # 查看进度
```

### Step 3：全量跑（主线 /loop 调度）

```bash
# 逐条（续跑安全：已跑的 run 自动跳过）
python src/harness.py --method supervised --dataset psfhs --ratio 0.05 --seed 0 --epochs 100
# ... 或用主线 /loop /run-experiment 批量
```

## 超参（复现零偏离，禁修改）

| 方法 | 关键超参 | 值 |
|---|---|---|
| 统一 | Adam lr=1e-3 / CosineAnneal / base_ch=32 / batch=4 / 100ep | 对照协议 |
| MeanTeacher | EMA=0.99 / cons=0.1 / rampup=40ep | SSL4MIS |
| CPS | cons=0.1 / rampup=200ep | SSL4MIS |
| UAMT | EMA=0.99 / cons=0.1 / rampup=200ep / T=8 / thresh=(0.75+0.25r)*ln2 | SSL4MIS |
| FixMatch | conf=0.8 / cons=0.1 / rampup=200ep | SSL4MIS |

## 结果格式（results/results.csv）

PSFHS（num_classes=3）：`method,dataset,label_ratio,seed,dice_PS,dice_FH,dice_mean,hd95_PS,hd95_FH,hd95_mean,...`

HC18（num_classes=2）：`method,dataset,label_ratio,seed,dice_head,dice_mean,hd95_head,hd95_mean,...`

（CSV 字段自动适配 num_classes）
