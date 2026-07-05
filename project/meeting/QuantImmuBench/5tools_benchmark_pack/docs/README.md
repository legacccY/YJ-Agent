# Rerun v2 — 5 工具 × 130 肽 × 三层次评估交付包

> 子任务：在 HPC 上部署 5 个新抗原免疫原性预测工具，使用 130 肽 Dataset2（In Vitro ELISpot）ground truth 做横向 benchmark，采用三层次评估框架。
>
> **更新日期：2026-06-30**（5 工具全量完成，评估通过）

---

## 一、交付内容

| 子目录 / 文件 | 内容 |
|---|---|
| `docs/` | **5 个工具的说明文档**，每个一份 md，含 6 部分：① 工具简介（原理 / 特点 / 论文 DOI / repo / 许可）② 输入数据模板 ③ 参数设置 ④ 输出格式及含义 ⑤ 最新 DS2 ELISpot benchmark 结果 ⑥ 部署环境与已知问题 |
| `环境配置命令.md` | **5 个工具的真实部署命令回顾**（clone / 建环境 / 权重下载 / 烟测 / 正式跑 / 关键坑），逐条标注来源 |
| `HPC_Inventory.md` | **HPC 目录完整清单**——所有 input / output / log 文件的位置、行数、大小、Job ID |
| `../06_analysis/outputs/` | 评估原始输出（HPC）—— `metrics_three_tier.csv` + `per_patient_details.csv` |

数据源：HPC `/gpfs/work/bio/zichenli24/rerun_v2/`（连接 `ssh zichenli24@dtn.hpc.xjtlu.edu.cn`）

---

## 二、5 工具横评总表（DS2 ELISpot，n_pep=130）

> **主指标 = 患者内 Fisher-Z 加权 Spearman**（先在每位患者内部算相关、再跨患者聚合，计入患者间差异，方法学最严谨）
> **全局 Spearman** = 所有患者肽混合后算（作对照）
> **AUC** = 有无免疫原性二分类判别力（SFC > 0 cutoff）
> 方向统一「分数越高越免疫原」。下表按主指标（患者内 Fisher-Z）降序。

| 工具 | 类型 | 患者内 Fisher-Z [95%CI]（主） | 全局 Spearman ρ (p)（对照） | AUC (SFC>0) | 许可 | 备注 |
|---|---|---|---|---|---|---|
| **MHLAPre** | IMMUNO | **+0.039 [+0.030, +0.048]** ❌不显著 | +0.052 (p≈0) | **0.530±0.057** | 开源 | ★ CV 修正：GroupKFold 后 AUC→0.53（原 0.997 为数据泄露）。TextCNN 对 DS2 基本无预测力 |
| **PRIME** | IMMUNO | **+0.203 [+0.013, +0.379]** ✅显著 | +0.226 (0.010) ✅ | 0.586 | 学术免费 | 已发表工具中最佳；依赖 MixMHCpred |
| **HLAthena** | PRESEN | **+0.200 [+0.010, +0.377]** ✅显著 | +0.137 (0.121) | 0.438 | research only | ⚠️ 提呈 proxy，非免疫原性工具；Fisher-Z 上界显著，不可与免疫原性工具直接并列 |
| **ImmuneApp** | IMMUNO | +0.172 [−0.020, +0.351] 不显著 | +0.036 (0.681) | 0.579 | MIT | CNN-LSTM ATT；TF 1.15 老环境 |
| **DeepHLApan** | IMMUNO | +0.009 [−0.182, +0.200] 不显著 | −0.129 (0.144) | 0.404 | GPL-2.0 | 全局反向相关（immunogenity_score 与 ELISpot 呈弱负相关） |

> ✅显著 = 95% 置信区间不含 0（患者内主指标）/ p < 0.05（全局对照）。⚠️ MHLAPre 值仅作参考——同数据训练+预测导致 AUC 高达 0.997，不可对外引用。

> ⚠️ **HLAthena 定位**：预测 MHC-I 提呈（presentation）而非免疫原性，与上表前两列本质不同，仅作为 presentation proxy baseline 单列参考，不可与免疫原性工具 apples-to-apples 直接并列。

**总体结论**：在 130 肽 Dataset2 上，5 工具均未达到强相关。患者内 Fisher-Z 口径下，**PRIME（+0.203）和 MHLAPre（+0.224，但含数据泄露）是唯一达到统计显著的免疫原性工具**；全局 Spearman 口径下 MHLAPre（p=0.002）和 PRIME（p=0.010）显著。HLAthena 作为提呈工具有 Fisher-Z 显著（+0.200），说明提呈信息有一定预测力，但 AUC 仅 0.438 印证「提呈 ≠ 免疫原性」。

---

## 三、三层次评估方法

本评估采用三层递进指标：

| 层次 | 指标 | 原理 | 权重 |
|---|---|---|---|
| **Tier 1（主）** | 患者内 Fisher-Z 加权 Spearman | 每位患者内算 Spearman ρ → Fisher Z 变换 → 逆方差加权聚合 → 反变换回 ρ。有效计入患者间异质性，统计效力最高 | ★★★★★ |
| **Tier 2（对照）** | 全局 Spearman ρ | 所有患者肽混合后算单次 Spearman。快速、直观，但忽略患者内结构 | ★★★ |
| **Tier 3（辅助）** | AUC (SFC > 0) | 有无免疫反应二分类判别力。连续强度定量以 Tier 1/2 为准 | ★★ |

---

## 四、数据集

| 项目 | 数值 |
|---|---|
| 肽数（DS2 In Vitro） | 130 条长肽 → 展开为 25,470 条 8-11mer 子肽（per HLA） |
| 患者数 | 9（P101–P110，其中 P103 缺失） |
| HLA 等位基因数 | 26（跨 9 患者） |
| 正样本（SFC > 0） | ~90 条（69%） |
| Ground Truth | ELISpot SFC（连续值）+ SFC > 0（二分类） |
| 数据源 | `Elispot_Dataset2_complete.xlsx`（MOESM4 In Vitro sheet + WT sequences） |

---

## 五、重要 Caveat（诚实标注）

- **MHLAPre** = 用 DS2 数据训练并在同一批数据上预测，AUC = 0.997 是**数据泄露**产物，Fisher-Z 也高估。需要 GroupKFold CV（按患者分组）才能得到真实性能。当前值仅供参考，不可外发。
- **DeepHLApan** = 全局 ρ = −0.129，分数方向可能反了（immunogenity_score 越高 ELISpot 越低），需排查分数方向定义。
- **HLAthena** = 提呈预测工具，不预测免疫原性。Fisher-Z 显著但 AUC 近随机——提呈信息对免疫强弱有一定参考但不替代。仅作 presentation proxy 单列。
- **ImmuneApp** = Fisher-Z 95%CI 跨 0（−0.020 ~ +0.351），正方向但未达显著。需更多样本排查。
- 所有 benchmark 数字出自 HPC `/gpfs/work/bio/zichenli24/rerun_v2/06_analysis/outputs/`，可完整溯源。
