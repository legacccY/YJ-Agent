# BMVC 2026 rebuttal 工作区（review 5/4/3/3，目标拱 isv7 3→4）

> BMVC 主目录已封印；本 `rebuttal/` 是官方允许的唯一修改路径。所有 rebuttal 产物登记于此。

## 产物指针
- `response_body.tex` — **rebuttal 正文草稿块**（模板无关，无 preamble；待官方 rebuttal.tex 到位灌壳）。~570 词，≤1 页。
- `scripts/qcts_stability.py` + `results/qcts_stability.{csv,pdf}` / `qcts_stability_summary.json` — 4-backbone bootstrap 稳定性新实验。
- `scripts/qbar_distribution.py` + `results/qbar_*.{csv,pdf}` — q̄ 分布/阈值敏感性支撑。

## 战术骨架（skeptic 定）
外科式指回论文 A1–A6 预答 + 只补增量新证据。火力砸 isv7；XHFa 最短事实纠错 + 一句 Prop1；8hpP(5)/6xgi(4) 轻带过。

## rebuttal 里须显式声明为「新增分析」的两处（未进投出稿）
1. 4-backbone bootstrap 稳定性 — α 弱可辨识（NLL 平），但 ECE-LQ CV 仅 3–12%（ResNet 3.0 / Swin 4.2 / ViT 7.9 / ConvNeXt 12.1%）。措辞 "we ran a new bootstrap"。
2. ImageNet-C 18/18 corruption Wilcoxon signed-rank **p=3.8×10⁻⁶**。措辞 "a new Wilcoxon signed-rank test confirms"，**禁**写 "the paper reports"。

## 复用已投稿证据（非新，直接指回）
§A8 真实 LQ 174 张（106 ISIC+68 Fitzpatrick17k，ECE 0.073[0.038,0.125]）；§5.2 Eq.(5)+§A20 re-marginalize（ρ_a −0.163 / ρ_b +0.241）；Table 3 强 backbone QCDI 符号翻转→toward zero；§A10 阈值 τ∈[0.40,0.50]；§A18 NLL landscape ΔNLL<0.002；Prop 1。

## 诚实边界（结尾锁死）
头条幅度（73% QCDI 降 / LQ ECE 减半）= Std-VIB-specific；机制方向 5 backbone + 18 corruption 普适；QCTS 从不损害 quality-awareness。
