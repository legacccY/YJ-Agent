# 工作日志

## 当前状态

- **阶段**：阶段三完成，准备进入阶段四
- **上次完成**：
  - VisiScore-Net 训练完成（20 epochs，最佳权重来自 epoch 6）
  - 评估脚本 `eval_visiscore.py` 完成，对比 BRISQUE baseline
  - 评估报告 `results/eval_report_visiscore.md` 已生成
  - 验收结果：平均 PLCC=0.924 / SRCC=0.895，推理 3.1 ms/张，全部达标
- **下一步**：开始阶段四——QAD（质量感知推断）
- **待确认**：completeness 维度 SRCC=0.689 略低于 0.7，后续可针对性改进

## 阶段三评估结果

| 维度 | PLCC | SRCC |
|------|------|------|
| sharpness | 0.947 | 0.863 |
| brightness | 0.987 | 0.986 |
| completeness | 0.731 | 0.689 |
| color_temp | 0.992 | 0.990 |
| contrast | 0.961 | 0.945 |
| 平均 | 0.924 | 0.895 |

BRISQUE 对比 sharpness：VisiScore 0.947 vs BRISQUE -0.184

## 数据资产

| 数据集 | 路径 | 规模 |
|--------|------|------|
| ISIC 2020 (原始) | D:/YJ-Agent/data/raw/isic2020/train-image/image/ | 33,126 张 |
| FitzPatrick17k (原始) | D:/YJ-Agent/data/raw/fitzpatrick17k/images/ | 16,574 张 |
| 配对数据集 ISIC | D:/YJ-Agent/data/paired_dataset/{light,medium,heavy}/ | 99,378 张 |
| 配对数据集 FP17k | D:/YJ-Agent/data/paired_dataset_fp17k/{light,medium,heavy}/ | 49,722 张 |
| 合并质量标签 | D:/YJ-Agent/data/quality_labels_all.csv | 149,100 行 |
| 专家 QC 标注 | D:/YJ-Agent/data/expert_qc_labels.csv | 487 行 |
| 最佳模型权重 | D:/YJ-Agent/checkpoints/best_visiscore.pth | epoch 6 |

## 最后更新

2026-05-06 21:00（北京时间）
