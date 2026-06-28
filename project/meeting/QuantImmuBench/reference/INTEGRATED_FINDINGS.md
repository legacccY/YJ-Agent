# 跨窗整合综合 —— Spearman 探索三窗收敛 + 跨窗洞察

> 服务 quantimmu-bench / A 主窗 Lead 整合。建档 2026-06-26。
> 整合 H(pooling)·I(fusion 天花板)·F(QuantImmune pilot) 三个已完成窗口 + 朱同学外部成果。
> 数字真源:`analysis/pooling_*.csv`(H)·`analysis/fusion_*.csv`(I)·`quantimmune/results/*`(F)·`analysis/per_patient_spearman_12tools.csv`(A)。全 Bash 核 csv。
>
> ⚠️ **2026-06-27 HLA-FIX 后置 caveat**：本档建于 2026-06-26，H/I/F/A 各窗头条数字均来自**修复前**（含 P101/P102 等位伪迹）。修复后：① PredIG 全局显著性失效（剔 P101/P102 后 p=0.343 ns），表中「PredIG count-safe 0.364 / max 0.198」头条受污染影响；② deepHLApan 另有 merge bug，相关结论需重核；③ per-patient 数字待 Phase B 重推理更新。**总纲结论方向不变**（现有工具及组合定量能力 ρ≈0.26–0.36 触顶、融合增益落噪声内），但具体单工具头条数请以 corrected-excl 真源 `analysis/metrics_ds2_fixed_exclP101P102.csv` + 04_LOG Entry HLA-FIX 为准。

---

## 0. 一句话总纲

**四方独立证据(我整合的 13 工具 benchmark + H pooling + I fusion + F pilot + 朱同学)收敛到同一结论:在真实新抗原免疫原性数据(DS2,101 肽/9 患者)上,现有工具及其任意组合的定量(per-patient Spearman)能力在 ρ≈0.26–0.36 触顶,逼近理论天花板下沿(0.4),且融合相对最优单工具的增益落在噪声内(p>0.8)。要做定量飞跃必须喂新信号/新数据,不是堆工具或换模型。**

---

## 1. 三窗结论速览

| 窗 | 核心产出 | 头条数 | 结论 |
|---|---|---|---|
| **H pooling** | 子肽聚合 8 算子 × 9 工具二维扫描 | PredIG count-safe 0.364 / max 0.198 | pooling 决定排序;`max` 系统低估有信号工具 0.05–0.17;`sum` 是肽长混杂假象必排除 |
| **I fusion 天花板** | LOPO + 三检验 + 天花板距离 | fixavg 0.328 vs deepHLApan 0.252,p>0.8 | 融合非杀手锏,学权重过拟合反伤,逼近天花板未确证触顶 |
| **F QuantImmune pilot** | stacking 元模型 LOPO 可行性 | 定平均集成 0.328 ≈ 平手最强单工具 | 现有工具组合做不出定量飞跃,需新信号(供体 TCR/precursor) |
| **A 整合(13 工具)** | 第一波 3 工具进表 + per-patient | MHCflurry proxy 0.203 第5,CNNeo 最新 -0.158 垫底 | 免疫原性工具无一明显超结合 proxy |

---

## 2. ★跨窗洞察(只有整合才看得见,最高价值)

### 2.1 deepHLApan 的"最强单工具"地位是肽长混杂假象 —— H 修正 I/F
- **H 实证**:deepHLApan 的 max/top3mean/topk_w/rankdecay 池化分数与子肽数(≈肽长)相关 ρ≈0.57(count-confounded);去混杂后唯一 count-safe 算子(softmax/mean)≈0 或转负 → **deepHLApan 的"正信号"大半是肽长度,不是真免疫原性**。
- **I/F 用它当融合地板**(per-patient ρ=0.252,max 池化)→ 这个地板被肽长虚高。
- **整合结论**:融合(0.33)其实**没超过一个正确池化的真信号单工具**(H 测 PredIG count-safe geomean=0.364、IMPROVE top3mean=0.320,均 ≥ 融合 0.33)。→ **"融合非杀手锏"被进一步加固**:连单个会挑 pooling 的工具都打平/超过融合。
- ⚠️ caveat:H 的 count-safe 是全局 Spearman、I/F 是 per-patient LOPO,口径不同不能逐位比;geomean 有 min-shift 实现注意。**可执行下一步**:I/F 的 fusion 实验应改用 count-safe pooling 的真信号工具(PredIG/IMPROVE)当地板重跑,而非 max 池化的 deepHLApan。

### 2.2 pooling 维度 ≈ fusion 维度同等重要,但此前全被 max 口径掩盖
- 我之前 per-patient 头条(`per_patient_spearman_12tools.csv`)固定 `sub_agg=max`。H 证 max 非最优 + deepHLApan 头条是混杂 → **我的 deepHLApan per-patient 跳升(0.04→0.26)头条需打肽长混杂 caveat,可能也是长度假象**。
- 真正稳健的头部应是 PredIG/IMPROVE/PRIME(H 证这些 count-safe 后升到 0.32–0.36,且非混杂)。

### 2.3 三个"天花板"数值惊人一致(独立推导/实测)
- 理论天花板(THEORY_quant,低置信):ρ_max≈0.4–0.6
- I 融合点估:0.328–0.334
- F pilot 集成:0.328
- 朱同学融合:0.43(p=0.70)
- H 单工具 count-safe 上限:PredIG 0.364
→ **四个独立来源全落在 0.33–0.43**,夹逼出"现有肽+HLA 信号的定量上限"。

---

## 3. 整合后给 benchmark 的可执行修正(A 窗待办)

1. **主排行榜默认 pooling 从 `max` 改 count-safe 最优(top3mean/mean)**,max 保留作"单显性表位"对照。报数前查 `pooling_count_confound.csv`,>0.5 一律不入主报(尤其 deepHLApan/HLAthena 长肽富集工具)。
2. **永不用 `sum` pooling**(肽长混杂,DeepImmuno 被 sum 从 -0.117 翻成 +0.113 纯假象)。
3. **pooled 分数 round(8) 后算 Spearman**(H 抓的浮点 tie bug,现有 metrics/per_patient 值有 ≤0.0025 浮点漂移)。→ 反哺 `per_patient_spearman_multimethod.py` + `merge_metrics_NNtools.py`。
4. **per-patient 头条加肽长混杂 caveat**,deepHLApan 跳升不作为 headline 正面证据,改以 PredIG/IMPROVE/PRIME 为稳健头部。
5. **fusion 地板用 count-safe 真信号工具重跑**(2.1),确认融合是否连单工具都超不过。

---

## 4. 整合后给 QuantImmune 立项的统一建议(呈用户/袁老师拍板)

- **不建议**以"融合现有工具做定量"立项(I+F+朱三方证不显著,撞天花板)。
- **唯一理论路径=喂新信号**:供体 TCR-seq / HLA 分型(袁数据已有 HLA)/ precursor frequency 代理(THEORY C2)。
- **或扩数据 powered study**:K=9→55–90 患者(F 功效估算),多中心连续 SFC。
- **headline 押 C3**(连续模型 top-K 排序临床价值)而非"融合破天花板"。
- **负结论本身可发表**:用干净 LOPO+配对+三检验定量钉死"多工具融合在真实数据上增益落噪声内",是方法学贡献 + powered study 功效依据。

---

## 5. 残留 caveat / 未决
- DTU 工具(NetMHCpan-BA/NetTepi/ICERFIRE)落地后融合输入扩 ~19 维,本结论需重跑确认(数字标 pending DTU)。
- 朱 netAffneg_9 绝对值(0.3946/0.4328)依赖其原始输入,只复现结构性结论,未逐位对齐。
- 天花板 0.4–0.6 = 低置信理论估计,需大样本 magnitude benchmark 校准。
- 多重比较未校正(I 试 4 融合法报最高,投稿前列全 grid 或预登记)。
- DS1 跨数据集符号翻负(融合/单工具 DS1 均 ρ<0),泛化未验。

## 数据真源索引
H:`analysis/POOLING_STUDY.md` + `pooling_{2d_scan,best_per_tool,count_confound,global_spearman}.csv` · I:`reference/FUSION_CEILING.md` + `fusion_{methods,vs_single_paired,ceiling_distance,single_floor}.csv` · F:`reference/QUANTIMMUNE_PILOT_SUMMARY.md` + `quantimmune/results/*` + `QUANTIMMUNE_THEORY_LEDGER.md` · A:`per_patient_spearman_12tools.csv` + `metrics_ds2_12tools.csv`
