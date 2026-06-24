# FetalSSBench — DATA_INVENTORY

> 路径/状态真源 = `.portfolio/datasets.json`，此处只细目。全公开免费集。

| 集 | 任务 | 规模 | GT | 来源 | 本地 | 状态 |
|---|---|---|---|---|---|---|
| **PSFHS** | 耻骨联合+胎头分割(2类) | 1358 图+mask | 像素 mask | Zenodo 10969427 (免申请,132MB) | `project/meeting/_run011_pilot/data/PSFHS/PSFHS/{image_mha,label_mha}/` (2716 .mha) | ✅ ready(G5用) |
| **HC18** | 胎儿头围分割 | 999训+335测 | 椭圆轮廓(填成mask) | Zenodo 1322001 (免申请) | TODO 下载 | ⬜ todo |
| **FUGC** | 宫颈超声分割 | 890图(500/90/300) | 像素mask(测试集不公开,提交平台评) | Zenodo 14305302 (需签协议邮件 fugc.isbi25@gmail.com) | TODO 申请 | ⚠️ 需申请 |

## 备注
- HC18 GT 是 HC 椭圆参数(CSV)，分割用须填充椭圆成 mask（标准做法，dataset.py 已处理 PSFHS .mha，HC18 加适配）。
- FUGC 测试集 mask 不公开 → 验证集评估 or 提交平台；拿不到全集则诚实降"双数据集(PSFHS+HC18)"。
- speckle 合成(候选C用)：纯 Python Nakagami 注入，无需额外数据。
- **不用**：BraTS-Africa/M&Ms(那是候选B跨中心OOD用)、BUSI(候选C用)。本项目(候选A)只 PSFHS+HC18+FUGC。

## pilot 资产可复用
`project/meeting/_run011_pilot/`：dataset.py(PSFHS .mha loader+split)、unet.py、pilot_g5.py(Sup+MeanTeacher)、results/results.csv(G5 12 runs)。正式跑扩展加 CPS/UAMT/FixMatch + HC18/FUGC + 低比例。
