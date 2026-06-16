# NCA-JEPA — 04_LOG（时间倒序）

> **全史真源**：`../PROJECT_LOG.md`（Med-NCA 总日志，含复现 + NCA-JEPA 全部历史 entry）。
> 本文件 = NCA-JEPA 子项目going-forward 简日志 + 最新状态快照。新 NCA-JEPA 会话在此追一行，详写进 `../PROJECT_LOG.md`。
> 入口读档：`README.md`（命名+状态）→ `01_创新计划` + `02_理论框架`（why+命题）→ `03_pilot`（怎么跑）→ `registry.json`（臂/门/状态）。

---

## 2026-06-16 — 探路战队（5 agent）+ framing 安全修正
- **5 路并行探路**（4 researcher sonnet + 1 reviewer opus，组合台系统首次实战）→ 报告 `05_探路_2026-06-16.md`。
- **致命发现**：①稳定区=anytime 最弱区（trade-off 须升 pilot 一等指标）②三张牌打 ViT 稻草人（缺 early-exit ViT 对照臂 A0+）③Kvalsund&Stovold 2026（2604.12720）实证 NCA 振荡吸引子非固定点（须主动引区隔）④resilience MICCAI 2026 占④不确定性牌；RadJEPA 2026-01 占医学 JEPA（ViT predictor）；NCA-as-SSL-predictor 仍全网空白。
- **venue**：NeurIPS 2026 已过；ICLR 2027 ~9 月（主线 3 月冲刺）；MICCAI 2027 ~2 月（退路 C）。2027 CFP 未出盯官网。
- **超参**：5/6 官方源，deterministic 自创已正确标；nca_steps=16 加 ablation {8,16,32}。
- **✅ 安全修正落地**（caveman off 精修）：01/02/README「可证稳定」→「稳定性可分析可控」；02「定理 6.1」→「性质 6.1」🟢→🟡（无证明不叫定理）；02 §5.1(b) 上界冒等式 → 标 🟡「至多…需实测」；02 加 Kvalsund 防御注（像素 vs latent）；01 加 RadJEPA related-work 行；03_pilot 头 A0 状态统一（A0 done / A1A2 pending）。
- **待用户拍的大 framing 决策（未动）**：加 A0+ early-exit ViT 对照臂 + stability-vs-anytime trade-off 升一等指标。
- 系统：teams flag 开 + /paper-scout skill 建；自定义 agent/team 需**重启 CC** 激活。本轮产出未 commit（待收工）。

## 2026-06-16 — 实验阶段启 + HPC 部署验通
- 地基搭建完：`facebookresearch/ijepa` 集成 + NCA predictor + 8 哨兵；smoke 全过。
- HPC 全量部署验通：`/gpfs/work/bio/jiayu2403/nca-jepa/`，env `yjcu124py310`，NIH 112120 图全解压、pilot 10k 子集泄漏 0。
- 哨兵门 **7/8 PASS**（s4 边界非 bug）。
- **A0 baseline 训练健康跑通**：job 1450052，loss 0.476→0.056@ep10，50ep ~16min。
- 红线10 官方超参联网复核完成：`configs/PROVENANCE.md`（~90% 真 CheXWorld 官方值，偏差全有意/已澄清，A0 不需重训）。
- **下一步**：A0 训完 → Gate0 → A1/A2 多 seed。**待用户放行**（训练串行红线，HPC 提交主线亲自做）。

> 早于本日的复现+pilot 设计 entry 见 `../PROJECT_LOG.md`。
