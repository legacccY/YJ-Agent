# WaveFidBench — STORY（反跑偏主文）

## 核心 Claim（一句话钉死）

AD 分类的判别信息在 wavelet 频带上不均匀分布，但现有 XAI 解释从未被检验是否对齐真正承载信息的频带；本文以**频带分解为可控忠实度轴**，给出第一张「频带 × XAI 方法 × faithfulness 指标」系统 benchmark，揭示解释在哪些频带最忠实、在哪些被噪声带偏。

> **benchmark/empirical** 论文，不是新模型。卖点 = 频域忠实度评测框架 + 系统发现，不是更高 AD 分类精度。

## 为什么是真 gap（非"没人做"）

1. wavelet+CNN 做 AD 分类有(WaveletFusion 2026-05 等)，但**只报分类精度，无 XAI 忠实度评测**。
2. XAI 忠实度评测有(2601.12826 肺 CT、2407.08546 AD 显著图)，但**无 wavelet 子带可控分解维度**。
3. 两维交叉(频带 × 忠实度)空白 → 「解释是否对齐真正承载判别信息的频带」无人答。

## 章节弧

1. **Intro**：AD 临床依赖可信解释 → wavelet 频带承载不同结构信息 → 但 XAI 是否对齐承载信息的频带未知 → 本文建频域忠实度 benchmark。
2. **Related**：wavelet 医学分类(WaveletFusion/WaveFormer)/XAI 忠实度评测(2601.12826/Quantus)/AD 解释(2407.08546)。明确切开 WaveletFusion(只分类无忠实度)。
3. **Method = 频域忠实度协议**：①子带可控分解(LL/LH/HL/HH 逐组置零测判别信息)②频带摄动忠实度(借 2601.19017 思路,各子带遮蔽测模型敏感度 vs 解释覆盖)③对齐度量(解释热图能量在各频带的分布 vs 真判别频带)。
4. **Experiments**：Kaggle AD 4-class(+OASIS)上 ≥3 XAI(Grad-CAM/SHAP/IG) × 4 子带 × {ROAD, IROF, insertion-deletion}，出 benchmark + 发现。
5. **Conclusion**：哪类 XAI 在哪个频带最忠实;解释是否被高频噪声带偏;频域视角对 AD 可信解释的启示。

## 防御写法 R-rules

- **R1 不卖方法新**：定位 evaluation benchmark；不声称提出更好分类器。novelty 在"频带分解作忠实度轴"。
- **R2 数字只用核实值**：所有 faithfulness/精度/对齐数经 verifier Bash 核 csv 才入文。
- **R3 撞车诚实**：Related 明写 WaveletFusion(2026-05)、2601.12826，本文差异=频带×忠实度交叉 + benchmark 定位。
- **R4 拉开与 WaveletFusion 距离**：必须强调本文是评测框架(多 XAI×多子带×多指标)，不是又一个 wavelet 分类器。
- **R5 结论非平凡**：必须有可操作发现(如"高频子带解释忠实度低=解释被纹理噪声带偏")，非"wavelet 有用"。
- **R6 辖域限定**：claim 限 AD 分类 × 这几个数据集 × 这几个 XAI，不外推所有医学影像。

## 与组合台边界（防自撞）

- 姊妹篇 [[HyperFidBench]]：同"XAI 忠实度评测"母题，但**模态/方法完全不同**(本篇=wavelet 频域脑结构 MRI 分类；姊妹=超图脑连接组)。共享 Quantus/扰动公理**工程框架**可复用，claim/数据/方法不重叠。
- 与 ArtiOODBench/MedAD-FailMap/selinf：不同母题，无重叠。
- 与 gdn2vessel、NCA 家族：无关。
