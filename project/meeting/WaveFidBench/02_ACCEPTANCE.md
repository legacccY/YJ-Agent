# WaveFidBench — ACCEPTANCE（二元 PASS/FAIL 验收）

## lever 分解（headline 承重链）

headline =「频带分解作 XAI 忠实度可控轴 + AD 频域忠实度 benchmark + 非平凡发现」，承重三腿：
- **L1 频带承载差异真实**：子带置零(LL/LH/HL/HH)对 AD 分类精度的损失显著不同 → 判别信息确实在频带上不均匀。
- **L2 benchmark 真实**：≥3 XAI × 4 子带 × ≥3 faithfulness 指标 × ≥1 数据集(Kaggle, 增信加 OASIS)，数字经 verifier 核 csv。
- **L3 非平凡发现**：得到可操作结论(如某 XAI 在高频被噪声带偏 / 某频带解释最忠实)，非"wavelet 有用"。

## 阶段硬阈值

| 阶段 | PASS 条件 | FAIL→动作 |
|---|---|---|
| Gate1 地基跑通 | Kaggle AD 4-class 下载+ResNet/ViT 分类器训练(acc 合理,对齐文献)+pytorch_wavelets 子带置零生效+Quantus 算出非 nan faithfulness | 跑不通 → 砍(K1) |
| Gate2 频带轴成立 | 子带置零的精度损失在 LL vs 高频间有显著差异(L1)+解释能量频带分布可计算 | 频带无差异/轴立不住 → 退 CBM 或砍(K2) |
| Gate3 benchmark+发现 | ≥3XAI×4子带×≥3指标 全表 + ≥1 条非平凡可操作发现 | 只得"都差不多"无发现 → 退 BSPC/CBM(K3) |

## 红线（反跑偏，不可松动）

- **数字一律 Bash/Grep 核 csv**，不信 Read（[[feedback_verify_paper_numbers.md]]）。
- **评估不泄漏**：分类器 train/test split 不交叉；忠实度评测扰动不混入训练。Kaggle 集须核患者级 split（防同患者切片跨 train/test 泄漏致虚高）。
- **超参禁臆想**：分类器/wavelet/XAI 超参查官方源，查不到标 TODO（[[feedback_no_hallucinate_settings.md]]）。
- **复现零偏离**：baseline/XAI 按官方实现，不私改（[[feedback_repro_zero_deviation.md]]）。
- **数据溯源**：Kaggle 4-class 须确认是 OASIS 等真实衍生集而非 AI 合成伪造集（DATA_INVENTORY 待核 TODO）；存疑则改用 OASIS 官方。

## 书面 kill criteria（事前冻结，防 HARKing）

- **K1 地基死**：数据拿不到 / wavelet+分类器+Quantus 工程跑不通 → 砍。
- **K2 频带轴塌**：子带置零对精度无差异(频带都一样)→ 频域视角立不住 → 退 CBM analysis 或砍，不硬凑。
- **K3 发现空洞**：benchmark 跑完只得"各 XAI/各频带忠实度无差异"且无可操作结论 → 退 BSPC/CBM，不当 ACCV main 卖。
- **K4 撞车**：投稿前复查，若 WaveletFusion 类论文已补 XAI 忠实度维度、或出现同样"频带×XAI 忠实度"benchmark → 重定位或退路。
- **K5 算力超支**：>5 GPU·h（实际应远低）仍无可用结果 → 停下报。

## G4 红队残差（动手前置，已记 LOG）

1. WaveletFusion(2026-05)是结构最近邻 → 全文严守 benchmark 定位，绝不写成"又一个 wavelet 分类器"。
2. novelty 必须锚定"频带分解作忠实度轴"——这是 L1，先验证频带承载差异真实再铺 benchmark。
3. Quantus 是否含独立 insertion/deletion 实现待核（否则用 PixelFlipping 等价 + 自实现<50行,标清楚）。
4. 2601.19017(频带摄动评忠实度)是音频域无代码 → 思路可借，实现自写，引用诚实标"方法借鉴音频域"。
