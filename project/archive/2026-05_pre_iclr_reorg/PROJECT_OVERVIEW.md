# VisiSkin-Agent 项目总览

**最后更新**：2026-05-17 | **当前焦点**：BMVC 投稿（Deadline 2026-05-29）+ VisiEnhance Stage 1 容量问题

---

## 🎯 项目核心

**VisiSkin-Agent** 是一个医学 AI 系统，为皮肤镜图像同时做**质量评估**和**黑色素瘤诊断**，产出**临床可信的不确定性估计**。

### 四大技术支柱

| 模块 | 作用 | 状态 | 权重 |
|------|------|------|------|
| **VisiScore-Net** | 皮肤镜图像质量评分（ABCD+颜色等） | ✅ 完成 | `checkpoints/best_visiscore.pth` |
| **Q-VIB** | 质量自适应分类器（自信度与质量挂钩） | ✅ 完成 | `checkpoints/efnet/best_qad.pth` |
| **VisiEnhance-Net** | 图像增强（3 阶段渐进式）| ⏳ 训练中（Stage 1 容量问题） | `checkpoints/visienhance/` |
| **Agent** | ReAct 双通道决策（规则+LLM） | ✅ 完成 | - |

---

## 📊 项目进度全景

### 大项目（MICCAI 2027 投稿目标）

#### 阶段 1-2：基础（已完成）
- ✅ 环境 + 数据管道 + 配对数据集（149K 张）
- ✅ 149K 张特征预计算（EfficientNet-B0）

#### 阶段 3：VisiScore-Net（已完成）
- ✅ 5 维质量评分模型（PLCC 0.924 / SRCC 0.895）
- 📄 **论文**：Method 3.1 完成

#### 阶段 4：Q-VIB（已完成）
- ✅ Std VIB / Adaptive Prior / Q-VIB Full 消融完成
- ✅ ITB Benchmark（4 质量分层子集：HQ/LQ/Edge/Diverse）
- ✅ 3-seed 鲁棒性验证（AUC CV < 2%）
- ✅ 跨数据集验证（HAM10000 / PAD-UFES zero-shot）
- ✅ 9 条 baseline 对比（含 MC Dropout / Deep Ensemble）
- 📄 **论文**：Method 3.2 完成

#### 阶段 5：Agent（已完成）
- ✅ Qwen3-4B 本地化（4-bit nf4）
- ✅ ReAct 状态机 + 规则 fallback
- ✅ 低质追问率 59%（目标 ≥50%），高质追问率 15.5%（目标 ≤30%）
- 📄 **论文**：Method 3.4 完成

#### 阶段 6：ITB Benchmark（已完成）
- ✅ 7 张论文图表（DPI 300）
- ✅ 6 路 baseline + Agent 评测完成

#### ⚠️ 阶段 7：VisiEnhance-Net（待决策）
- ❌ Stage 1 训练停止（29 epoch）→ PSNR 25.55 dB（目标 ≥30）
- ✅ SSIM 0.9535（目标 >0.92）✅
- **根因**：模型仅 1.7M 参数，容量不足（计划 67M）
- **方案 A**：换大 config（~15M 参数），重跑 30-40 小时
- **方案 B**：接受 25-26 dB，调整论文目标，核心靠 E1（|ΔAUC| < 1.5%）
- 📄 **论文**：Method 3.3 框架完成，数字待更新

#### 阶段 8：论文（MICCAI 投稿）
- 📄 LaTeX 骨架就位（11 文件）
- 📄 Method 3.1/3.2/3.4 完成
- 📄 Method 3.3 框架完成（数字待更新）
- 📄 Related Work / Introduction 完成
- ⏳ Abstract / Experiments / Conclusion / Appendix 待写
- ⏳ 需从 ICLR 官方下载 `iclr2027_conference.sty`

---

### 🔴 **BMVC 投稿线**（独立进度，Deadline 2026-05-29）

从大项目**提取**"Quality Calibration Training Scheme（QCTS）"的核心发现发表。

#### 论文状态
- 📄 **12 页 PDF**，零编译 error
- 📄 **4 张真实图表**（fig0_teaser / fig1_taxonomy / fig2_reliability / fig3_degradation）
- 📄 **Abstract / Introduction / Method / Results / Discussion** 骨架完整

#### 实验完成（最新）
| 实验 | 结果 | 文件 |
|------|------|------|
| Std VIB 基准 | ECE 0.146 → 0.047（68%↓），LQ 段效果最明显 | `qcts_itb_results.csv` |
| QCTS 应用 | ECE LQ 降 68%，QCDI 偏移 -0.015，ρ -0.108 | `qcts_params.json` |
| 控制实验 | EfficientNet-B3 alpha=0 时退化为 TS，证明 QCTS 需质量表示 | `qcts_form_ablation.csv` |
| TS 反转现象 | ρ 反向 +0.324（最强发现），Kendall τ=0.85 稳健性高 | `threshold_sensitivity.csv` |

#### 待完成
| 优先级 | 任务 | 说明 |
|--------|------|------|
| 🔴 | fig4 升级 | 2×2 grid 对比 TS+QCTS，展示反转发现 |
| 🔴 | 自引匿名化 | 去掉 `anonymous2025qvib` 暴露身份 |
| 🟡 | 英文润色 | Intro / Discussion 打磨 |
| 🔴 | 导师审阅 | 2026-05-28 前 |
| 🟡 | 页数控制 | 现在 12 页，BMVC 限 14 页除 ref |
| 🟢 | Release | ITB/QCTS 代码 + README |

#### 文件位置
```
project/meeting/BMVC/
├── itb_paper.tex / pdf         # 12 页论文
├── egbib.bib                   # 文献（格式已修正）
├── bmvc2k.cls / .bst           # BMVC 模板
└── figures/
    ├── fig0_teaser.*           # 新增：皮肤镜 3×3 矩阵 + 置信度对比
    ├── fig1_taxonomy.*         # 校准分类散点图（双面板）
    ├── fig2_reliability.*      # 可靠性曲线（LQ/HQ 分层）
    └── fig3_degradation.*      # 逐降质维度 ECE

project/
├── run_qcts.py                 # QCTS 实验脚本
├── gen_bmvc_figures.py         # 图表生成脚本
├── results/qcts_*.csv          # QCTS 结果数据
```

---

## 📦 数据资产清单

### 原始数据
| 数据集 | 规模 | 路径 |
|--------|------|------|
| ISIC 2020 | 33.1K | `data/raw/isic2020/train-image/image/` |
| FitzPatrick17k | 16.6K | `data/raw/fitzpatrick17k/images/` |
| HAM10000 | 10.0K | `data/external/ham10000/` |
| PAD-UFES | 2.3K | `data/external/pad_ufes/` |

### 特征 & 标签
| 产物 | 大小 | 作用 |
|------|------|------|
| EfficientNet-B0 特征 | 728 MB | `data/efficientnet_features.npy` (149K×1280) |
| ABCD 缓存 | - | `data/abcd_cache.csv` (149K 行) |
| 质量标签 | - | `data/quality_labels_all.csv` |
| ISIC 70/10/20 分割 | - | `data/isic_split.csv` |
| ITB 子集定义 | - | `results/itb_subsets.csv` |
| 专家 QC 标注 | - | `data/expert_qc_labels.csv` (487 行) |

### 模型权重
| 模型 | 参数量 | 路径 | 用途 |
|------|--------|------|------|
| VisiScore | - | `checkpoints/best_visiscore.pth` | 质量评分 |
| Q-VIB Full (F) | 1.3M | `checkpoints/efnet/best_qad.pth` | 论文主结果 |
| Std VIB (D) | 1.3M | `checkpoints/stdvib/best_qad.pth` | baseline |
| Adaptive Prior (E) | 1.3M | `checkpoints/adaptive/best_qad.pth` | 消融 |
| MC Dropout (I) | 1.3M | `checkpoints/mcdropout/best_qad.pth` | baseline |
| Deep Ensemble (J) | 1.3M × 5 | `checkpoints/ensemble/seed_{42,123,2024,456,789}` | baseline |
| EfficientNet-B3 (A) | 4M | `checkpoints/efnet_finetuned.pth` | 诊断基线 |
| VisiEnhance Stage 1 | 1.7M | `checkpoints/visienhance/stage1/` | 待更新 |

---

## 🔬 核心实验数据速查表

### Q-VIB 消融（test set, 19878 张）
| 方法 | AUC | ECE | Entropy | Entropy~q̄ (ρ) |
|------|-----|-----|---------|----------------|
| Std VIB (D) | 0.693 | 0.097 | 0.240 | -0.024 |
| Adaptive Prior (E) | 0.688 | 0.100 | 0.228 | -0.169 |
| **Q-VIB Full (F)** | **0.707** | **0.098** | 0.225 | **-0.165** |

### ITB-LQ 质量分层对比（3-seed 稳健性）
| 方法 | AUC | ECE | 鲁棒性 (CV%) |
|------|-----|-----|------------|
| F (Q-VIB) | 0.726±0.007 | 0.149 | 0.9% ✅ |
| D (Std VIB) | 0.716±0.012 | 0.175 | 1.7% ✅ |
| TS (Std VIB + TS) | - | 0.175 | - |
| I (MC Dropout) | 0.693 | 0.613 | - |
| J (Deep Ensemble) | 0.711 | 0.440 | - |

### BMVC QCTS 实验（ITB-LQ）
| 方法 | ECE | 改进 | Δ QCDI | ρ(熵~q̄) |
|------|-----|------|--------|----------|
| Std VIB | 0.146 | - | +0.018 | -0.033 |
| **Std VIB + QCTS** | **0.047** | **68%↓** | **-0.015** | **-0.108** |
| EfficientNet-B3 | 0.345 | - | - | - |

### VisiScore-Net 评估
| 维度 | PLCC | SRCC |
|------|------|------|
| Sharpness | 0.947 | 0.863 |
| Brightness | 0.987 | 0.986 |
| Completeness | 0.731 | 0.689 |
| Color Temp | 0.992 | 0.990 |
| Contrast | 0.961 | 0.945 |
| **平均** | **0.924** | **0.895** |

---

## ⚠️ 待决策项

### 1. VisiEnhance Stage 1 容量问题
**现状**：PSNR 25.55 dB（目标 ≥30）

**选项**：
- **A（推荐）**：换大 config（base_channels=64, mid_blocks=8, ~15M 参数），重跑 30-40 小时
- **B**：接受 25-26 dB，调整论文目标为 ≥26 dB，核心靠 E1（|ΔAUC|<1.5%）+ E3（代码发布）

### 2. BMVC 匿名化
**问题**：代码里暴露 `anonymous2025qvib` 和 `visiscore` 等身份信息
**方案**：全局替换为通用名称，论文参考改为平台化描述

### 3. BMVC 论文长度
**现状**：12 页（含图表和参考文献）
**限制**：BMVC 限 14 页（除参考文献外），现在还有 2 页余量
**计划**：fig4 升级后可能需要压缩某些 supplementary 内容

---

## 🚀 下一步清单

### 本周（2026-05-17~05-24）
- [ ] **决策**：VisiEnhance Stage 1 选 A 还是 B
- [ ] **BMVC**：运行 QCTS 所有实验，更新论文数值和 fig4
- [ ] **BMVC**：代码匿名化（global find/replace）
- [ ] **BMVC**：英文润色（Intro / Discussion）
- [ ] **BMVC**：导师审阅反馈汇总

### 5月底前
- [ ] **BMVC**：提交版本最终检查 + OpenReview 上传
- [ ] **大项目**：根据 Stage 1 决策，更新 Method 3.3 + Experiments 章节

### 6月后
- [ ] **阶段 8**：写完 MICCAI 版本 Abstract / Experiments / Conclusion / Appendix
- [ ] **Release**：ITB benchmark + QCTS 代码包 + README
- [ ] **Reader Study**：推进 3 位临床医生评审 30 张代表性图像

---

## 📂 项目文件导航

```
D:/YJ-Agent/project/
│
├── 🎯 PROJECT_OVERVIEW.md              # 你在这里（项目中心）
├── README.md                            # VisiSkin-Agent 库描述
├── WORKLOG.md                           # (D:\YJ-Agent) 日常工作进度
│
├── 📋 plans/                            # 阶段计划文档
│   ├── 00_overview.md
│   ├── phase_03_visiscore.md
│   ├── phase_04_Q-VIB.md
│   └── ... (phase_01~08)
│
├── 🔬 models/                           # 模型代码（9 个 .py 文件）
│   ├── visiscore.py
│   ├── q_vib_encoder.py
│   ├── qad_classifier.py
│   ├── quality_adaptive_prior.py
│   ├── quality_tokenizer.py
│   └── ...
│
├── 🧠 agent/                            # Agent 实现
│   ├── orchestrator.py                  # ReAct 状态机
│   ├── tools.py                         # 工具定义
│   └── question_bank.py
│
├── 🛠️ configs/                          # 训练配置
│   ├── qad_efnet_nw0.yaml              # Q-VIB Full（主）
│   ├── qad_stdvib_nw0.yaml
│   └── ...
│
├── 🎓 data/                             # 数据管道
│   ├── dataset.py
│   ├── degrade.py
│   ├── qad_dataset.py
│   └── *.csv / *.npy（特征、标签）
│
├── 🏆 benchmark/                        # ITB Benchmark
│   ├── build_itb.py
│   └── metrics.py
│
├── 📊 results/                          # 实验结果
│   ├── *.csv（eval_report / itb_results 等）
│   └── figures/                        # 论文图表 (DPI 300)
│
├── 🔴 meeting/BMVC/                     # BMVC 投稿目录
│   ├── itb_paper.tex / pdf             # 论文
│   ├── BMVC_LOG.md                     # BMVC 日志
│   ├── figures/                        # 4 张图表
│   └── ...
│
├── 🧪 train_*.py                        # 训练脚本
│   ├── train_visiscore.py
│   ├── train_qad.py
│   └── train_visienhance.py
│
├── 📈 run_*.py / eval_*.py              # 实验脚本
│   ├── run_experiments.py
│   ├── run_qcts.py                     # BMVC QCTS 实验
│   ├── gen_bmvc_figures.py             # 图表生成
│   └── analyze_results.py
│
└── ✅ tests/                            # 62 个单元测试
```

---

## 🔗 快速链接

- **BMVC 日志**：`project/meeting/BMVC/BMVC_LOG.md`
- **大项目工作日志**：`D:\YJ-Agent\WORKLOG.md`
- **VisiSkin-Agent 库文档**：`project/README.md`
- **阶段计划**（所有）：`project/plans/00_overview.md`

---

## 💡 最常见的工作流

### "启动 Claude Code，快速了解现状"
1. 读 `PROJECT_OVERVIEW.md`（本文件，3 分钟）
2. 看 BMVC 进度（下一截止） vs 大项目进度（阶段 7 决策）
3. 核心数据速查表找关键数字

### "BMVC 推进"
1. 编辑 `project/meeting/BMVC/itb_paper.tex`
2. 运行 `python project/gen_bmvc_figures.py` 生成/更新图表
3. 检查 `project/meeting/BMVC/BMVC_LOG.md` 的待完成清单

### "决策 VisiEnhance Stage 1"
1. 检查当前权重 `checkpoints/visienhance/stage1/`
2. 选择方案 A（大 config）或 B（接受小 PSNR）
3. 更新本文档的"待决策项"部分，提醒下次会话

### "跑实验"
1. 根据需要编辑配置（`project/configs/`）
2. **用 `/loop` 模式启动**：`/loop /run-experiment ...`
3. Monitor 自动 heartbeat，state.json 记录进度
