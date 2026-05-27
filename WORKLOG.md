# 工作日志（快速指针）

**最后更新**：2026-05-27 收工 | **完整进度**：见 `D:/YJ-Agent/project/PROJECT_LOG.md`

---

## 🎯 当前焦点

**ICLR 2027 大项目启动**（Deadline 2026-09-22，**121 天**）
- 目标命中率：**78-80%**（25 lever stack）
- 当前 M1 W1：VisiEnhance Plan A 重训准备 + Theorem 2 推导

**BMVC**：✅ 已封印（2026-05-24），不再修改 — 详见 `project/meeting/BMVC/SUBMITTED.md`

---

## 📋 主指导文档（按读档顺序）

| 优先级 | 文件 | 用途 |
|---|---|---|
| 🥇 入口 | `project/README.md` | ICLR 2027 项目入口 + 4 文件读档顺序 |
| 🥈 反跑偏 | `project/STORY_FRAMEWORK.md` | 10 跑偏定义 + §1-§9 锁定 + 锁定数字 + R1-R10 |
| 🥉 验收 | `project/ACCEPTANCE_CRITERIA.md` | 25 lever + E1-E12 + 红线 + M1-M4 milestone |
| 数据 | `project/DATA_INVENTORY.md` | checkpoint + 数据集 + 30+ csv + 脚本 + W1-W16 |
| 日志 | `project/PROJECT_LOG.md` | 时间倒序，每次会话进度 |

---

## 🚀 下一步（M1 W1-W2，2026-05-27 ~ 06-08）

会话 6（2026-05-27）完成（详见 PROJECT_LOG）：
- [x] 锁定数字 audit 定案：核心表真实(脚本改 md 解析,ICLR 11/11 PASS)+ cross-domain 标待核 PENDING ✅
- [x] hook 假阳性根治(doc 模式去 anonymous2025 + 跳引号匹配,js+sh+ps1) ✅
- [x] 5-theorem β/√ε 一致性统一(β=M·L_q/√2, Pinsker-optimal) ✅
- [x] ICLR2027 paper 骨架 + Appendix A2/A2.3/A3 LaTeX 化(Prop3/Lemma3/Thm2/Cor1, 9 页 exit 0) ✅

待续：
- [ ] **续训待启动**（从 ep 15 续，`stage1_planA/last_visienhance.pth`，`/loop /run-experiment`）
- [ ] **Appendix A1 LaTeX 化**（Q-VIB Prop1/Lemma1/Thm1/Prop2，源 `V-QIB数学推导.md`）
- [ ] 主文 §3-§8 正文填充（M3）
- [ ] **Plan A re-eval 后必办**：重导 n=19878 per-sample csv + 决定 cross-domain 锁定值(−0.108→−0.164/−0.150→−0.236)

详细 task 清单见 `project/plans/phase_07_visienhance_planA_active.md`

---

## 🔬 关键数字速查（ICLR 2027）

| 模块 | 状态 | 核心数字 |
|---|---|---|
| VisiScore-Net | ✅ done | PLCC 0.924 / SRCC 0.895 |
| Q-VIB Full | ✅ done | AUC 0.707, ECE 0.098, ρ=−0.165 (p<10⁻²⁴) |
| 5 backbone universality | ✅ done | section54_summary.csv |
| VisiEnhance Stage 1 v0 | ❌ 容量不足 | PSNR 25.55 dB（目标 ≥30）|
| **VisiEnhance Plan A** | ⏳ M1-M2 | PSNR ≥ 30, \|ΔAUC\|<1.5%, SalvageRate>55% |
| 5-theorem closure | ✅ 5/5 推导 done (实证待 Plan A) | Prop 1-3 + Lemma 1-3 + Thm 1-2 + Cor 1 全 publication-grade，详 `project/plans/{Theorem2,Prop3_Lemma3,Corollary1}*.md` |

---

## ⚠️ 永久红线（CLAUDE.md 复用）

1. Reader Study 数据**不可伪造** — 用 DCA + Triage simulation + 已发表 dermatologist baseline + LLM-judge protocol (§A23 disclaimer) 替代
2. **所有材料只能从网上公开资源获取** — 不联系诊所、不采集线下样本、不依赖人际网络
3. **不用扩散生成模型做皮肤镜增强**（伪影发明病灶，临床红线）
4. **数字凭印象写禁止** — 每个数字必须 csv 核算 + bootstrap 95% CI + run_id
5. **BMVC 数字不可直接搬入 ICLR**（必须重跑或 cite-as-paper）
