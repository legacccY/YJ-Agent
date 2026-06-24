# run-011 候选A G5 杀手锏 Pilot

## 目标
证伪/证实命门：**不同半监督方法在不同标注比例下的标注效率曲线，有没有可报告的 spread/交叉/拐点**。
- 无结构（各法各比例 Dice 差 <1%）→ 候选A故事塌，kill
- 有可报告 spread → PASS，进正式立项

## 文件索引
| 文件 | 用途 |
|---|---|
| `download_psfhs.py` | Zenodo 10969427 下载+解压 PSFHS 数据到 data/PSFHS/ |
| `dataset.py` | PSFHS dataloader，.mha 读取，固定 seed train/test split |
| `unet.py` | 小 2D U-Net（base=32，输入 256×256） |
| `pilot_g5.py` | 主训练：2方法×3比例×2seed=12 runs，写 results.csv + state.json |
| `requirements_note.md` | 依赖说明 |
| `data/PSFHS/` | 数据目录（主线下载后出现） |
| `results/results.csv` | 最终结果（跑完后出现） |
| `results/state.json` | 进度状态（训练中持续更新） |

## 主线跑步顺序
```
# 1. 下载数据
python project/meeting/_run011_pilot/download_psfhs.py

# 2. 烟测（--quick：1 seed + 5% 比例 + 5 epoch）
python project/meeting/_run011_pilot/pilot_g5.py --quick

# 3. 全量跑（2方法 × 3比例 × 2seed = 12 runs）
python project/meeting/_run011_pilot/pilot_g5.py
```

## 数据
- PSFHS：耻骨联合(PS) + 胎头(FH)，像素 mask 2 类，1358 例 .mha
- Zenodo: https://zenodo.org/records/10969427
- 本地路径：`data/PSFHS/`（image_mha/ + label_mha/）
- Split：80% train+pool / 20% test（固定 seed=42，绝不泄漏）
