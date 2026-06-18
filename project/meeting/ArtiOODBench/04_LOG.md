# ArtiOODBench — LOG

## Entry 1 — 2026-06-18 立项（ideation run-006 G6）

**立项决策（用户拍板）**：ideation run-006「现象优先选题」漏斗 138→C107 唯一 G5 去风险确证候选，用户 G6 拍板「立项 C107 + 并行续 C003」。

**选题轨迹**（全留痕 `project/ideation/runs/2026-06-18_run-006_phenom-medimg-failure/`）：
- G0 宪章：医学影像真实失效现象，锁 CVPR + 排除清单（NCA/JEPA + selinf/disagree/公平长尾/mech-interp/配准/failmap）。
- G1：ideator×8 产 138 候选（S3 矛盾×3 + S4 dataset×3 + S5 残值 + S6 SOTA边界）。
- G2：去重 49 + 硬排除 16 + 撞车砍 38（皮肤 shortcut 重灾区被 Winkler/Bissoto/Transfusion/Zech 等撞车清光）→ 35。
- G3：InnoEval 排序，C107 rank#2（7.75，CVPR-fit 9 最高）。
- G4：skeptic 红队 🟡（撞 OpenMIBOOD 风险，待 G5 核）。
- G5a：免费撞车核查 SURVIVE（OpenMIBOOD/PMC10532230 只概念/3D，无去污染重排闭环）。
- **G5 killshot 现象坐实**：artifact-only 43 维（resize 224² 控分辨率）NIH vs VinDr **AUROC=0.9213±0.009**（n=1000，csv `results/c107_artifact_ood_killshot.csv`）。核心 claim 没死。

**headline**：医学 OOD benchmark 在测采集 artifact 非病理异常；artifact-only 特征顶满 OOD → 方法排名被混淆。承重 = L1 多 benchmark 量化 + L2 去污染协议 + **L3 重排闭环（命门 actionable so-what）**。venue CVPR 2027 / 退路 NeurIPS D&B/MICCAI/TMLR。

**红队残差（必答）**：差异化全压「2D 系统化 + 去污染 + 重排闭环」，Related Work 须硬对齐 OpenMIBOOD(CVPR25)/PMC10532230(3D)；0.92<0.95 不夸大成「完全 artifact」；命门 = 去污染后排名真翻转（否则降 ICBINB）。

**下一步**：
1. researcher 全面对齐先驱 + MedIAnomaly 方法集，锁差异化、补 K4 撞车排查。
2. /design-experiment 设计 Gate1 矩阵：≥3 benchmark 对（NIH/VinDr + MedIAnomaly 7 集 + dermoscopy 跨集）跑 A-1 + 去污染 A-3 + 重排 A-4。
3. ACCEPTANCE 阈值冻结（拍板点）。

**资产**：G5 killshot 脚本 `project/ideation/.../06_experiments/c107_artifact_ood_killshot.py` + csv 已复制进 results/。
