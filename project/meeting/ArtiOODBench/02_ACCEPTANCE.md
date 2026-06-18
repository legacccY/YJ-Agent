# ArtiOODBench — ACCEPTANCE / 判据

> 立项时预登记，防 HARKing。阈值草案，Gate1 设计时冻结（拍板点）。

## 核心 RQ
医学影像 OOD detection benchmark 的方法排名在多大程度上被采集 artifact 混淆？去污染后排名是否实质改变？

## 承重判据（对齐 STORY lever）

| ID | 判据 | 阈值（草案，待冻） | 对应 lever |
|---|---|---|---|
| A-1 | artifact-only 特征在 ≥3 个医学 OOD benchmark 对上 AUROC | ≥0.80（多数对），≥1 对 >0.90 | L1 |
| A-2 | 现象普适性：≥3 模态（CXR / 脑 MRI / dermoscopy）均见污染 | 每模态 ≥1 对 artifact-only AUROC>0.75 | L1 |
| A-3 | 去污染协议有效性：去污染后 artifact-only AUROC 显著下降 | artifact-only 掉到 <0.65（接近随机） | L2 |
| A-4（命门） | 去污染后主流 OOD 方法排名改变 | ≥2 方法排名翻转（如 top1 掉出 top3）或 Spearman(原,去污染)<0.7 | L3 |

## Kill criteria（书面，事前冻结）

- **K1**：artifact-only AUROC 在 ≥3 个 benchmark 对都 <0.7 → 现象不普适，**砍立项**。
- **K2**：去污染后 OOD 方法排名 Spearman(原,去污染) >0.9（几乎不变）→ 污染无 actionable 后果，**降 ICBINB 短文，不投 CVPR**。
- **K3**：去污染协议被证明把真 semantic 信号也去掉（去污染后所有方法都崩到随机）→ 协议无效，回设计。
- **K4**：撞车——若发现某已发论文已做 L1+L2+L3 完整闭环（非仅概念/3D）→ 撞车 >0.85，**砍或大幅 reframe**。

## Gate1（立项后第一闸，MICCAI/CVPR 就绪前置）
- 第一硬前置 = 在 ≥3 个 benchmark 对上复现 A-1（artifact-only 高 AUROC）+ 实现 A-3 去污染使其掉到随机。出不来则现象不稳，退守。
- 次优先 = A-4 重排（命门，决定 CVPR vs ICBINB）。

## 反跑偏红线（继承组合台）
- 数字一律 Bash/Grep 核 csv，不信 Read。
- artifact 特征提取必须 resize 统一分辨率（否则分辨率本身直接泄漏，AUROC=1 无意义）——已在 G5 killshot 落实，正式实验沿用。
- OOD 方法用官方实现/官方超参，查不到标 TODO，不臆想。
- 去污染前后用同一 split、同一方法集，三方对账。
