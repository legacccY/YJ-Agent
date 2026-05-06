# VisiScore-Net 评估报告

- 验证集样本数：500
- VisiScore 推理速度：3.1 ms/张

## 各维度 PLCC / SRCC

| 维度 | PLCC | SRCC | 是否达标 (≥0.7) |
|------|------|------|----------------|
| sharpness | 0.947 | 0.863 | ✅ |
| brightness | 0.987 | 0.986 | ✅ |
| completeness | 0.731 | 0.689 | ⚠️ |
| color_temp | 0.992 | 0.990 | ✅ |
| contrast | 0.961 | 0.945 | ✅ |
| **平均** | **0.924** | **0.895** | ✅ |

## 与 BRISQUE 对比（sharpness 维度）

| 模型 | PLCC | SRCC |
|------|------|------|
| VisiScore-Net (sharpness) | 0.947 | 0.863 |
| BRISQUE | -0.184 | -0.415 |

## 结论

VisiScore-Net sharpness 维度 PLCC=高于 BRISQUE (0.947 vs -0.184)。
推理速度 3.1 ms/张，达标 (<100 ms 要求)。