# VisiEnhance dflip / query-for-retake 文献支撑（会话 21 调研，2026-06-09）

支撑 Claim 2（diagnosis-preserving enhancement）+ Claim 3（query-for-retake 通道）+ §4/§7/§8 写作。
**写 LaTeX 前用 Scholar/arXiv 核对作者全名与最终 venue**（部分 2026 预印本作者顺序可能微调）。锚点三篇（标★）可放心主引。

## 类别 1：perception-distortion / task tradeoff（dflip 根源 = tradeoff 固有代价，非 bug）
- ★ **Blau & Michaeli, The Perception-Distortion Tradeoff, CVPR 2018** — 数学证明失真与感知质量天生对立。dflip 理论基石。
- **Chen et al., UniRestore: Unified Perceptual and Task-Oriented Image Restoration Model Using Diffusion Prior, CVPR 2025** — 感知恢复提升视觉却损下游任务、任务导向恢复牺牲视觉，系统性冲突。
- **Kim et al., SR4IR: Task-Driven Perceptual Loss, CVPR 2024** — 仅优化像素/感知的超分不保下游识别的任务高频信息；需 task-driven loss。
- **Mathieu et al., Evaluating Super-Resolution Models in Biomedical Imaging (Segmentation/Classification), J. Imaging 2025 (PMC12027580)** — PSNR/SSIM 改善不可靠转化为下游分割/分类性能。

## 类别 2：医学增强幻觉/伪影损诊断（支撑「deterministic > 生成式」红线 R8）
- ★ **Cohen, Luck & Honari, Distribution Matching Losses Can Hallucinate Features in Medical Image Translation, MICCAI 2018 (arXiv:1805.08841)** — CycleGAN MRI 翻译「无中生有」加肿瘤/抹真肿瘤。最契合反向类比。
- **Mardani et al., GAN-Hallucination (compressed-sensing/GAN MRI recon)** — 量化逆问题重建中「逼真但无数据支撑」幻觉。
- **Tivnan et al., Hallucination Index: An Image Quality Metric for Generative Reconstruction Models, MICCAI 2024 (PMC11956116)** — 专测生成式重建幻觉，强调视觉有说服力却篡改诊断解剖。

## 类别 3：task-aware / diagnosis-preserving 增强（DP-Loss 直系前作）
- **Kim et al., SR4IR (TDP loss), CVPR 2024** — 从任务网蒸馏知识约束超分保识别信息。DP-Loss 最近前作。
- **Chen et al., UniRestore, CVPR 2025** — 扩散先验统一感知+任务，仍无诊断 risk bound / 闭环。
- **Bai et al., Task-driven Image Fusion with Learnable Fusion Loss, CVPR 2025** — 下游信号回灌增强过程。
- **Deep Perceptual Enhancement for Medical Image Analysis (arXiv:2503.08027)** — 医学域增强与下游分析联合。

## 类别 4：质量门控 / 拒识 / 重拍 / defer（query-for-retake 通道先例）
- ★ **Geifman & El-Yaniv, Selective Classification for Deep Neural Networks, NeurIPS 2017；SelectiveNet, ICML 2019** — reject option 理论基石（risk-coverage），四通道 reject/defer 锚点。
- **Fu et al., EyeQ (Retinal Image Gradability Good/Usable/Reject), MICCAI 2019** — 质量门控「不足该拒用非强行分析」，与质量分级→门控几乎同构。
- **Araújo et al., DR|GRADUATE (uncertainty-aware DR grading + referral), Medical Image Analysis 2020 (arXiv:1910.11777)** — 不确定性 + 转专家。
- **Saeed et al., Learning IQA by Reinforcing Task-Amenable Data Selection, IPMI 2021 (arXiv:2102.07615)** — 按下游任务价值（非视觉质量）门控，最贴本文。（原误记 Saeidi；bib key `saeed2021learning`）
- **Jalaboi et al., Explainable Image Quality Assessments in Teledermatological Photography, Telemedicine and e-Health 2023 (PMC10468541)** — 皮肤科远程摄影标 poor quality + 引导重拍（retake）。皮肤镜域最直接重拍先例。（原误记 Vodrahalli；bib key `jalaboi2023explainable`）

## Gap（本文新意一句话）
前人各有半块：理论有 perception-distortion tradeoff、实证有生成式幻觉损诊断、方法有 task-aware restoration、机制有质量门控/拒识。**无人把 质量分级→诊断保持增强 OR 追问重拍→诊断 串成带理论 risk bound 的闭环 quality-triage agent，并实证增强对真阳黑色素瘤的系统性危害边界（dangerous flip）**。task-aware 增强默认「增强总帮忙」、门控只做拒识不接增强决策、幻觉研究只警示不治理 → 本文填空。
