# Q-VIB Full Ablation Report (Fine-tuned EfficientNet-B3 Backbone)

## Table 1: Global Metrics (test split, temperature-scaled)

| Method | AUC | ECE | Sens | Spec | Mean H | H~q (rho) |
|--------|-----|-----|------|------|--------|-----------|
| EfficientNet-B3 (direct) | 0.9159 | 0.039 | 0.872 | 0.797 | 0.079 | N/A |
| MC-Dropout | 0.8514 | 0.328 | 0.775 | 0.781 | 0.283 | 0.054 |
| Std VIB + FT features | 0.8566 | 0.328 | 0.789 | 0.765 | 0.283 | 0.059 |
| Adaptive Prior + FT | 0.8561 | 0.325 | 0.786 | 0.767 | 0.285 | 0.058 |
| Q-VIB Full + FT (Ours) | 0.8549 | 0.325 | 0.783 | 0.773 | 0.285 | 0.059 |

## Table 2: Per Degradation Level (AUC / ECE)

### Light degradation

| Method | AUC | ECE | Mean Entropy |
|--------|-----|-----|--------------|
| MC-Dropout | 0.8972 | 0.370 | 0.282 |
| Std VIB + FT features | 0.9029 | 0.370 | 0.282 |
| Adaptive Prior + FT | 0.9033 | 0.368 | 0.284 |
| Q-VIB Full + FT (Ours) | 0.9007 | 0.368 | 0.284 |

### Medium degradation

| Method | AUC | ECE | Mean Entropy |
|--------|-----|-----|--------------|
| MC-Dropout | 0.8561 | 0.330 | 0.286 |
| Std VIB + FT features | 0.8612 | 0.331 | 0.286 |
| Adaptive Prior + FT | 0.8608 | 0.327 | 0.287 |
| Q-VIB Full + FT (Ours) | 0.8601 | 0.328 | 0.287 |

### Heavy degradation

| Method | AUC | ECE | Mean Entropy |
|--------|-----|-----|--------------|
| MC-Dropout | 0.8089 | 0.284 | 0.282 |
| Std VIB + FT features | 0.8131 | 0.284 | 0.282 |
| Adaptive Prior + FT | 0.8130 | 0.282 | 0.284 |
| Q-VIB Full + FT (Ours) | 0.8112 | 0.279 | 0.283 |

## Table 3: Per q_bar Quintile (Q-VIB Full)

| q_bar range | AUC | ECE | Entropy | Mean KL | N |
|-------------|-----|-----|---------|---------|---|
| [0.05,0.44] | 0.797 | 0.284 | 0.273 | 82.460 | 3977 |
| [0.44,0.47] | 0.884 | 0.347 | 0.284 | 108.151 | 3976 |
| [0.47,0.51] | 0.915 | 0.346 | 0.285 | 113.443 | 3977 |
| [0.51,0.54] | 0.892 | 0.328 | 0.294 | 116.152 | 3976 |
| [0.54,0.92] | 0.811 | 0.321 | 0.288 | 132.395 | 3976 |