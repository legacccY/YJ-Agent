# 工作日志（快速指针）

**最后更新**：2026-05-17 | **完整进度**：见 `D:/YJ-Agent/project/PROJECT_OVERVIEW.md`

---

## 🎯 当前焦点

- **BMVC 投稿** | Deadline 2026-05-29（12 天）| 状态：12 页论文 + 4 张图 + 实验完成
- **大项目** | VisiEnhance Stage 1 容量问题待决策（选 A 重训 vs 选 B 接受小 PSNR）

---

## 📊 一句话进度

| 部分 | 状态 | 核心数字 | 最后更新 |
|------|------|---------|---------|
| **BMVC** | ⏳ 待英文润色 + 导师审阅 | 12 页 / 4 张图 / QCTS 68%↓ ECE | 2026-05-16 |
| **大项目 Q-VIB** | ✅ 完成 | F AUC 0.707 / ECE 0.098 / ρ=-0.165 | 2026-05-15 |
| **大项目 VisiScore** | ✅ 完成 | PLCC 0.924 / SRCC 0.895 | 2026-05-07 |
| **大项目 Agent** | ✅ 完成 | 低质追问 59% / 高质 15.5% | 2026-05-07 |
| **大项目 VisiEnhance** | ❌ 待决策 | PSNR 25.55 dB（目标 ≥30）| 2026-05-16 |

---

## 🚀 下一步（清单）

### 本周（2026-05-17~05-24）
- [ ] **VisiEnhance 决策**：选方案 A（重训，30-40h）或 B（接受 25-26 dB）
- [ ] **BMVC 实验**：所有 QCTS 数值确认，fig4 升级完成
- [ ] **BMVC 代码**：匿名化 + 英文润色 + 导师审阅
- [ ] **工程**：测试 reproduce.sh，确保所有 baselines 可复现

### 5 月底前（投稿前）
- [ ] **BMVC**：最终检查 + OpenReview 上传
- [ ] **大项目**：Method 3.3 数字对应 VisiEnhance 决策

### 6 月后
- [ ] MICCAI 版本 Abstract / Experiments / Conclusion / Appendix
- [ ] Release 准备（ITB Benchmark + QCTS code）
- [ ] Reader Study（推进 3 位医生）

---

## 📂 快速导航

| 需求 | 文件 |
|------|------|
| **项目全貌** | `project/PROJECT_OVERVIEW.md` ⭐ |
| **BMVC 日志** | `project/meeting/BMVC/BMVC_LOG.md` |
| **BMVC 论文** | `project/meeting/BMVC/itb_paper.tex` |
| **阶段计划** | `project/plans/00_overview.md` |
| **核心实验脚本** | `project/run_qcts.py` / `gen_bmvc_figures.py` |
| **权重位置** | `project/checkpoints/` |
| **数据资产** | `project/data/` |
| **结果数据** | `project/results/` |

---

## 🔬 关键数据速查

### Q-VIB 主结果（test set, 19878 张）
```
F (Q-VIB Full):  AUC 0.707  ECE 0.098  Entropy~q̄ ρ = -0.165 ✅
D (Std VIB):     AUC 0.693  ECE 0.097  Entropy~q̄ ρ = -0.024
```

### BMVC QCTS 结果（ITB-LQ）
```
Std VIB:           ECE 0.146
Std VIB + QCTS:    ECE 0.047  (68% ↓) ✅
```

### VisiScore-Net
```
平均 PLCC 0.924 / SRCC 0.895 ✅
```

---

## ⚠️ 待决策

### VisiEnhance Stage 1
- **现状**：PSNR 25.55 dB（目标 ≥30），SSIM 0.9535（目标 >0.92 ✅）
- **原因**：模型仅 1.7M 参数，容量不足
- **选项 A**：换大 config（~15M），重跑 30-40h
- **选项 B**：接受 25-26 dB，核心靠代码发布 + E1 贡献

---

最后更新时间：2026-05-17 10:50（北京时间）
