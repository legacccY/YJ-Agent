# NCA-JEPA — 04_LOG（时间倒序）

> **全史真源**：`../PROJECT_LOG.md`（Med-NCA 总日志，含复现 + NCA-JEPA 全部历史 entry）。
> 本文件 = NCA-JEPA 子项目going-forward 简日志 + 最新状态快照。新 NCA-JEPA 会话在此追一行，详写进 `../PROJECT_LOG.md`。
> 入口读档：`README.md`（命名+状态）→ `01_创新计划` + `02_理论框架`（why+命题）→ `03_pilot`（怎么跑）→ `registry.json`（臂/门/状态）。

---

## 2026-06-16 — 实验阶段启 + HPC 部署验通
- 地基搭建完：`facebookresearch/ijepa` 集成 + NCA predictor + 8 哨兵；smoke 全过。
- HPC 全量部署验通：`/gpfs/work/bio/jiayu2403/nca-jepa/`，env `yjcu124py310`，NIH 112120 图全解压、pilot 10k 子集泄漏 0。
- 哨兵门 **7/8 PASS**（s4 边界非 bug）。
- **A0 baseline 训练健康跑通**：job 1450052，loss 0.476→0.056@ep10，50ep ~16min。
- 红线10 官方超参联网复核完成：`configs/PROVENANCE.md`（~90% 真 CheXWorld 官方值，偏差全有意/已澄清，A0 不需重训）。
- **下一步**：A0 训完 → Gate0 → A1/A2 多 seed。**待用户放行**（训练串行红线，HPC 提交主线亲自做）。

> 早于本日的复现+pilot 设计 entry 见 `../PROJECT_LOG.md`。
