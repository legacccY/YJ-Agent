# 工作日志

## 当前状态

- **阶段**：阶段二完成，准备进入阶段三
- **上次完成**：
  - ISIC 2020（33k 张）+ FitzPatrick17k（16.6k 张）全部退化 + 标注完成
  - quality_labels_all.csv：149,100 行，覆盖 Fitzpatrick I–VI 全肤色
  - expert_qc_labels.csv：487 张皮肤科医生 QC 标注（可作论文 expert validation）
  - DataLoader 验收通过，所有脚本 ruff 干净，推送到 GitHub
- **下一步**：开始阶段三——VisiScore-Net 训练
- **待确认**：`wandb login` 尚未执行，阶段三训练前需要手动跑一次

## 数据资产

| 数据集 | 路径 | 规模 |
|--------|------|------|
| ISIC 2020 (原始) | D:/YJ-Agent/data/raw/isic2020/train-image/image/ | 33,126 张 |
| FitzPatrick17k (原始) | D:/YJ-Agent/data/raw/fitzpatrick17k/images/ | 16,574 张 |
| 配对数据集 ISIC | D:/YJ-Agent/data/paired_dataset/{light,medium,heavy}/ | 99,378 张 |
| 配对数据集 FP17k | D:/YJ-Agent/data/paired_dataset_fp17k/{light,medium,heavy}/ | 49,722 张 |
| 合并质量标签 | D:/YJ-Agent/data/quality_labels_all.csv | 149,100 行 |
| 专家 QC 标注 | D:/YJ-Agent/data/expert_qc_labels.csv | 487 行 |

## 最后更新

2026-05-06 13:00（北京时间）
