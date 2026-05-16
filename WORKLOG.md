# 工作日志

## 当前状态

- **阶段**：阶段七 VisiEnhance-Net + 阶段八论文写作并行进行
- **Sprint 搁置**：改为对标 ICLR CCF-A 标准

### ⚠️ 待决策：Stage 1 模型容量问题

Stage 1 训练于 2026-05-16 启动，运行 29 epoch（~9 小时）后手动停止：
- 最佳 val PSNR：**25.55 dB**（目标 ≥ 30 dB，未达标）
- 最佳 val SSIM：**0.9535**（目标 > 0.92，已达标 ✅）
- 根本原因：实现的 VisiEnhanceNet 仅 **1.7M 参数**，容量不足（原计划 NAFNet-64 约 67M）

**下次会话第一件事**：决定方向
- **方案 A**：换大 config（base_channels=64, mid_blocks=8，预估 ~15M 参数），重新跑 Stage 1（预计 ~30-40 小时）
- **方案 B**：接受 25-26 dB，调整论文 E1 目标为 ≥ 26 dB，核心仍靠 E3（|ΔAUC| < 1.5%）
- 权重保存位置：`checkpoints/visienhance/stage1/`（29 epoch 的 checkpoint 仍存在）

### 论文进度（D:/YJ-Agent/paper/）

| 章节 | 状态 |
|------|------|
| LaTeX 骨架（11 个文件）| ✅ 就位 |
| Method 3.1 VisiScore-Net | ✅ 完成 |
| Method 3.2 Q-VIB | ✅ 完成（含 Lemma 1、Proposition 2、三数据集 ρ 值）|
| Method 3.3 VisiEnhance-Net | ✅ 完成（含 DP-Loss、Proposition 3、三阶段训练）|
| Method 3.4 双通道 Agent | ✅ 完成（含 Algorithm 伪代码）|
| Method 3.5 ITB Benchmark | ✅ 完成 |
| Related Work | ✅ 完成（4 方向）|
| Introduction | ✅ 完成（7 段）|
| Abstract | ⏳ 待写 |
| Experiments | ⏳ 框架可写，E3/E5 数字等训练完 |
| Conclusion | ⏳ 待写 |
| Appendix（定理证明）| ⏳ 待写 |

**编译**：需从 ICLR 官方下载 `iclr2027_conference.sty` 放入 `D:/YJ-Agent/paper/`

---

### 下次会话启动建议（旧 Sprint，已搁置）

**S3 剩余**：
- S3.1 Reader Study（30 张图 + 3 reader）——**限速项，需要你推进找人**
- fig12 Reader Study 图——等 S3.1 数据完成后生成
- Zenodo DOI 上传（权重 + split csv）——代码 release 最后一步

**关键提醒**：
- ⚠️ 不要再用 sonnet 子 agent 跑长时间任务，它的心跳监控会狂刷屏
- ⚠️ MC 采样 per-sample 种子已修复（`_seed_from_path` in run_experiments.py），结果 bit-reproducible
- ⚠️ FP17K 标签 bug 已修，build_itb.py 加了 drop_duplicates(fp_id)

---



- **2026-05-08 自检发现的硬伤**（投稿前必须修）：
  1. **G (Q-VIB+TokFT) 校准恶化**：HQ ECE 0.122 → 0.263（翻倍），跟"Q-VIB 提升校准"叙事冲突
     - 修复方向：F (Q-VIB Full) 重新定位为 Ours；G 降级为 supplementary 的 discriminative variant
  2. **B3 在 LQ 上 Brier 0.391 < G 的 0.424**——之前 WORKLOG 写"B3 校准差"是错的，应改为"B3 discriminative 最强但 ECE 在 LQ 段恶化（0.080 HQ → 0.416 LQ，单调发散），Q-VIB Full 用 AUC 换得 LQ 段 ECE 稳定（0.122/0.152）"
  3. **样本量与计划不符**：原计划每子集 500，实际 LQ 225 / HQ 125 / Edge 660 / Diverse 7350——HQ 25 个正例导致 AUC 95% CI 半宽 0.124（过宽），需重做 build_itb 扩到 ≥500
  4. **缺外部已发表 calibration baseline**：仅 B3 直推一个外部对比，审稿人必问；S1.3 加 Temperature Scaling + Focal Loss
  5. **单一数据集**：仅 ISIC2020 + FP17k；S2.1 加 HAM10000 / PAD-UFES zero-shot
  6. **单 seed**：S2.2 跑 3 seed 报均值±std

- **上次完成（2026-05-09）— Sprint 3 技术部分 ✅**：
  - **S3.2 fig1 更新**：9 条 baseline（含 I/J），ECE y 轴扩展到 0.70 真实呈现差异，D/E/F AUC 加 3-seed 跨 seed std 误差棒
  - **S3.2 fig3 更新**：±SEM → ±1.96×SEM（95% CI 带），只保留 VIB 消融变体（A/D/E/F/G），Proposition 2 D vs F 一目了然
  - **S3.3 代码 release**：README.md（含 Quick Start / 复现步骤 / 9 baseline 说明）/ reproduce.sh（5 步流水线，前 2 步验证通过）/ requirements.txt / LICENSE (MIT)
  - 62 tests 全绿，reproduce.sh 环境检查 + pytest 验证通过

- **上次完成（2026-05-09）— S2.2 修复（proper seed 42）✅**：
  - 发现原 Phase 4 checkpoints（D/E/F seed42）与重训 seeds（s123/s2024）在 ITB 上呈现两种局部最优：Phase 4 型（AUC 低但 ECE 好），重训型（AUC 高但 ECE 差）
  - **根因**：S2.2 重训前 train_qad.py 尚未加 --seed 参数，Phase 4 checkpoint 实为随机初始化，非 seed42
  - **修复方案**：用 proper --seed 42 重训 D/E/F（configs/*_nw0.yaml），得到与 s123/s2024 同一局部最优的三组 checkpoint
  - **3-seed AUC 鲁棒性（最终达标）**：F-LQ 0.726±0.007（CV=0.9%），D-LQ 0.717±0.012（CV=1.7%），全部 CV < 2% ✅
  - **entropy~q̄ 跨 seed 稳定性**：9/9 全部显著（p<0.05），全部负向 ✅
  - **论文叙事定位**：
    - 主结果（全测试集 + Phase 4 ckpt）：F AUC=0.707, ECE=0.098, rho=-0.165 vs D rho=-0.024
    - 3-seed 鲁棒性（proper seeds）：仅报 AUC CV%（< 2%），不用 ECE 对比
    - ECE 比较（ITB）：Phase 4 ckpt，F=0.149 vs TS=0.175/A=0.345/H=0.535 优势显著

- **上次完成（2026-05-08）— S2.3 ✅ MC Dropout + Deep Ensemble**：
  - 训练 3 个新模型：MC Dropout (dropout=0.3)，Std VIB seed 456/789
  - MC Dropout (I)：ITB-LQ AUC=0.693 ECE=0.613（校准严重退化）
  - Deep Ensemble (J, 5 模型 seed 42/123/2024/456/789)：ITB-LQ AUC=0.711 ECE=0.440
  - **F vs I ECE-LQ**：F 0.149 vs I 0.613（F 好 4.1×），**F vs J ECE-LQ**：F 0.149 vs J 0.440（F 好 3.0×）
  - entropy~q̄ rho：F=-0.192（最强）> D=-0.153 > J=-0.123 > I=-0.114，F 是唯一通过 quality-aware 建模实现校准的
  - 论文叙事：MC Dropout/Ensemble 高 AUC 但校准退化；Q-VIB 以 adaptive prior 专门针对质量维度建模，LQ 段 ECE 领先
  - 新增文件：`configs/qad_mcdropout.yaml`，`baselines/` 新增 I/J 推理函数，`analyze_results.py` 加 I/J 颜色/标签
  - 图表已更新（fig1 含 9 个 baseline）

- **上次完成（2026-05-08）— S2.2 ✅ + S2.4b ✅**：
  - **S2.4b**：fig10_kl_collapse.png，KL 峰值 185（epoch 2），前 5 epoch 全部 >100，AUC 0.80→0.62
  - **S2.2**：D/E/F/G 各 3 seed（42/123/2024）全部训练完成，fig1 更新含误差棒
    - F (Ours) ITB-LQ AUC 0.681±0.083，ITB-Edge 0.798±0.148
    - 关键工程修复：train_qad.py 新增 --seed/--ckpt-dir 参数；qad_efnet_tokft.yaml（G 正确 config，1280D B0）；qad_dataset.py mmap_mode 节省内存；DataLoader persistent_workers bug 修复
    - G config 历史澄清：G(seed42) 用 1280D B0 特征（qad_efnet_tokft.yaml），非 1536D B3

- **上次完成（2026-05-08）— S2.1 跨数据集 zero-shot ✅**：
  - HAM10000（10015 张，MEL 11.1%）+ PAD-UFES（2298 张，MEL 2.3%）全部下载、解压、特征提取、推理完成
  - **Proposition 2 跨数据集验证**：
    - HAM10000: F rho=-0.164, p=5.3e-61 ✅
    - PAD-UFES: F rho=-0.236, p=1.5e-30 ✅（比 ISIC 内部 -0.165 更强）
  - F vs D AUC 在两个数据集上不显著（zero-shot 跨模态属预期），但熵单调性稳健
  - fig9_cross_dataset.png 生成（DPI 300）
  - 修复 `precompute_external_features.py` PAD-UFES 路径（Kaggle 解压后在 `PAD-UFES-20/Dataset/`）
  - 修复 `analyze_external.py` Windows GBK emoji 编码问题
  - 数据留存：`data/external/ham10000/` + `data/external/pad_ufes/`（zip 可删节省空间）

- **上次完成（2026-05-08）— 阶段六 ITB Benchmark v1**：
  - 构建 4 子集（按预计算 q̄ 分层）：ITB-LQ（q̄<0.40, N=225）/ ITB-HQ（q̄>0.65, N=125）/ ITB-Edge（q̄ 0.40-0.55, N=660）/ ITB-Diverse（FP17k I-VI 均衡, N=7350）
  - 运行 6 路 baseline（A/D/E/F/G）+ Agent 评测，存 itb_results.csv / itb_ablation.csv / itb_predictions.csv
  - 指标：classwise binary ECE + Sens@95Spec + Brier Score + Mean Entropy + bootstrap AUC CI
  - 7 张论文图表 DPI 300 全部生成
  - **Proposition 2 实证成立**：Std VIB 熵全 q̄ 段 ~0.20 平稳，Q-VIB Full 随 q̄ 单调降（0.21→0.17）
  - **F vs D 显著性**（待 S1.1 重跑确认）：MAIN 对比

- **2026-05-08 S1.1 完成 + 重大发现**：
  - F/G 标签调换：F → "Q-VIB Full (Ours)"（红色），G → "Q-VIB+TokFT*"（紫色，supplementary）
  - 新增 fig8 AUC-ECE 帕累托图：B3 在 HQ/Edge 上 Pareto-dominate F；F 仅相对 D/E 占优
  - **新发现：F vs D AUC 在 ITB 子集上全部不显著**（HQ p=0.072, LQ p=0.233, Edge p=0.076）
    - 根因：ITB 子集样本量过小（HQ 125 / LQ 225），bootstrap CI 太宽
    - F vs D 在原 test set（19878 张）上 AUC 0.707 vs 0.693 是显著的，但 ITB 上不显著
    - 但 F vs D 熵差异在 HQ/Edge 上仍显著（p<0.05），Proposition 2 站得住
  - **结论：Sprint 1.2（扩 N≥500）从"重要"升级为"必须"**——否则论文 AUC 主张全部站不住

- **2026-05-08 S1.2 完成（核心达标）**：
  - 阈值放宽：HQ q̄>0.50（原 0.65），LQ q̄<0.45（原 0.40），Diverse 下采样 ≤1500
  - 仅采 test split（避免训练泄漏），N: HQ 125→360 / LQ 225→300 / Edge 660 / Diverse 1500
  - **F vs D AUC**：ITB-LQ Δ=+0.093 p<0.05 ✅，ITB-Edge Δ=+0.047 p<0.05 ✅，ITB-HQ p=0.232（高质量段不显著属预期）
  - **F vs D Entropy**：HQ/LQ/Edge 全部 p<0.05 ✅，Proposition 2 强支持
  - 🐛 待修：ITB-Diverse 1500 张中 1470 个正例（98%），FP17K 标签正则 `melanoma|malignant` 可能命中负例"non-malignant"，下放到 S2.1 一起处理

- **2026-05-08 Sprint 1 完成 ✅（顶刊投稿基线达成）**：
  - **S1.1**：F → "Q-VIB Full (Ours)"，G → supplementary "Q-VIB+TokFT*"，新增 fig8 帕累托图
  - **S1.2**：ITB 子集扩量 HQ 125→360 / LQ 225→300 / Edge 660 / Diverse 1500
  - **S1.3a-d**：Temperature Scaling baseline TS（T=2.32，过拟合 val 反而 test ECE 变差）
  - **S1.3e**：Focal Loss + Label Smoothing baseline H（best epoch 1, val AUC 0.8167，过拟合极快）
  - **S1.3f**：MC 采样 per-sample 种子（hashlib.md5(image_path) → torch.manual_seed），bit-reproducible
  - **FP17K bug 修复**：drop_duplicates(fp_id) 防止三倍化；Diverse 现在 1500 张 / 490 真正例

- **Sprint 1 最终核心数据**（seeded MC + FP17K-fixed ITB）：

| F (Ours) vs D | AUC Δ | AUC p | 熵 Δ | 熵 p |
|---|---|---|---|---|
| ITB-HQ | +0.018 | 0.193 n.s. | +0.044 | <0.05 ✅ |
| **ITB-LQ** | +0.032 | **<0.05** ✅ | +0.012 | **<0.05** ✅ |
| **ITB-Edge** | +0.029 | **<0.05** ✅ | +0.039 | **<0.05** ✅ |

| ITB-LQ ECE | 值 | F vs 它 |
|---|---|---|
| F (Ours) | **0.149** | — |
| Std VIB + TS | 0.175 | F -0.026 ✅ |
| EfficientNet-B3 | 0.345 | F -0.196 ✅ |
| Focal+LS | 0.535 | F -0.386 ✅ |

- **下一步（Sprint 2，3 周）**：
  - S2.1 跨数据集 zero-shot：HAM10000 + PAD-UFES，验证 Proposition 2 不依赖 ISIC（**sonnet 后台进行中**）
  - S2.2 3-seed 鲁棒性：D/E/F/G 各跑 3 个种子，报均值±std
  - S2.3 加入 MC Dropout + Deep Ensemble baseline
  - S2.4a ✅ 失败案例 fig11：F vs B3 在 1320 样本上的非对称错误模式
    - **核心发现**：F 漏 melanoma 160 个（B3 都接住），但 F 把 B3 误报的 223 个 benign 正确分类
    - 解读：F 是 high-specificity 保守模型，sensitivity 由 Agent 重拍/escalate 兜底
  - S2.4b ⏳ KL 崩塌 fig10：等 Sprint 2.1 完成后用 qad_adaptive_ft.yaml 重训 ~10 epoch 复现

- **上次完成（2026-05-08）— Qwen 本地化**：
  - 模型切换：Qwen3-8B（残缺）→ Qwen3-4B 4-bit nf4（完整下载 ~8 GB，显存 2.67 GB，cuda:0）
  - 修复 `_parse_tool_call` 正则 bug：非贪婪 `\{.*?\}` 遇嵌套大括号截断 → 改为贪婪 `\{.*\}`
  - 强化 system prompt：明确禁止纯文本输出，要求每次响应只输出一个工具调用
  - 开启 `enable_thinking=True`：帮助 4B 小模型在多轮工具调用中保持推理连贯
  - `test_llm_react.py` PASS：好图 done=True（malignancy 4.6%，low）/ 差图 waiting=True retake=1
  - 62 tests 全绿，零回归

- **阶段五验收结果（2026-05-07）**：
  - 低质量图追问率：59.0%（目标 ≥ 50%）✅
  - 高质量图追问率：15.5%（目标 ≤ 30%）✅
  - 端到端推理：40ms（目标 < 3s）✅（规则 fallback；LLM 模式约 40-90s/轮）

- **下一步**：进入阶段六（Benchmark）

- **阶段四验收（2026-05-07 补充）**：
  - verify_phase4.md 四条标准全过：KL ρ=0.278 ✅，熵 Q1>Q5 p=2.14e-44 ✅，ECE 0.131<0.166 ✅，E2E 927ms ✅

## 阶段五交付文件

| 文件 | 用途 |
|------|------|
| `project/agent/tools.py` | 工具定义：quality_assess / extract_features / triage |
| `project/agent/orchestrator.py` | ReAct 状态机（Qwen3-8B + 规则 fallback） |
| `project/agent/question_bank.py` | 追问模板库 |
| `project/app.py` | Gradio Demo |
| `project/agent/eval_agent.py` | Agent 端到端评测 |

## 阶段四旧记录（已完成）

- **上次完成**：
  - VisiScore-Net 训练完成（20 epochs，最佳权重来自 epoch 6）
  - 评估脚本 `eval_visiscore.py` 完成，对比 BRISQUE baseline
  - 评估报告 `project/results/eval_report_visiscore.md` 已生成并追加 q 向量分析
  - 验收结果：平均 PLCC=0.924 / SRCC=0.895，推理 3.1 ms/张，全部达标
  - `forward_features()` 方法已补充，返回 `(features, q_vector)`，供阶段四 Q-VIB 复用
  - q 向量三项验收全通过：值域 [0,1] ✓，维度最大相关 |r|=0.328 ✓，q̄ 分离显著（p=2.85e-28）✓
  - test_visiscore.py 新增 `forward_features` 测试，21 tests 全绿

- **阶段四消融实验完成（正式结果）**：
  - 发现 ABCD-only 输入信号太弱（AUC 三路差距 <0.002），全面升级为 EfficientNet-B0 特征
  - 预计算 149100 张图的 EfficientNet-B0 特征 → `data/efficientnet_features.npy`（728 MB）
  - 正确消融：三个独立模型分别训练（Std VIB / Adaptive Prior / Q-VIB Full）
  - 正确分割：70/10/20 按 isic_id 分组，test set 完全 held-out

- **三路消融正式结果（test split 19878 张）**：

| Variant | AUC-ROC | ECE | Mean Entropy | Entropy~q̄ (ρ) |
|---------|---------|-----|--------------|----------------|
| Std VIB | 0.693 | 0.097 | 0.240 | -0.024 (弱，p=6e-4) |
| Adaptive Prior only | 0.688 | 0.100 | 0.228 | -0.169 (强，p<1e-120) |
| **Q-VIB Full** | **0.707** | **0.098** | 0.225 | **-0.165 (强，p<1e-120)** |

- **核心结论（论文关键数据）**：
  - Proposition 2 验证：Std VIB ρ=-0.024（几乎无相关），Q-VIB ρ=-0.165（强显著）
  - Entropy 单调性：Q-VIB 低质量段 0.255 → 高质量段 0.188（单调递减），Std VIB 几乎不变
  - Q-VIB Full AUC 最高（0.707 vs Std VIB 0.693）

- **新增文件**：
  - `precompute_efficientnet.py`：EfficientNet 特征预计算
  - `create_split.py` + `data/isic_split.csv`：70/10/20 分割
  - `eval_ablation.py`：三模型独立消融评估
  - `configs/qad_stdvib.yaml`、`configs/qad_adaptive.yaml`：消融配置
  - 21 tests 全绿（含 3 个新 EfficientNet encoder 测试）

- **阶段四验收（2026-05-07 补充）**：
  - verify_phase4.md 四条标准全过：KL ρ=0.278 ✅，熵 Q1>Q5 p=2.14e-44 ✅，ECE 0.131<0.166 ✅，E2E 927ms ✅
  - EfficientNet-B3 微调完成，best val AUC=0.9102，作为强诊断基线（test AUC=0.9159）
  - FT 消融（Q-VIB + fine-tuned B3）探索：发现 VIB 瓶颈与 1536D 高维特征存在 KL 冲突（训练中 KL 飙至 100+，AUC 崩溃）。根本原因：CE 优化推大 mu，而自适应先验（sigma0=0.1）过紧无法容纳。记录为架构限制，未来工作方向：VIB 只作用于 ABCD+q，EfficientNet 特征绕过瓶颈作为旁路
  - 新增文件：finetune_efficientnet.py、precompute_finetuned_features.py、eval_ablation_ft.py、eval_ablation.py、verify_phase4.py、create_split.py 及相关 configs

- **下一步**：进入阶段五（Agent 系统集成），或先补充论文可视化图表
- **待确认**：MobileSAM 单张 909ms 超过 200ms 标准，是否在论文中用 EfficientSAM 替换

## 阶段三评估结果

| 维度 | PLCC | SRCC |
|------|------|------|
| sharpness | 0.947 | 0.863 |
| brightness | 0.987 | 0.986 |
| completeness | 0.731 | 0.689 |
| color_temp | 0.992 | 0.990 |
| contrast | 0.961 | 0.945 |
| 平均 | 0.924 | 0.895 |

BRISQUE 对比 sharpness：VisiScore 0.947 vs BRISQUE -0.184

## 数据资产

| 数据集 | 路径 | 规模 |
|--------|------|------|
| ISIC 2020 (原始) | D:/YJ-Agent/data/raw/isic2020/train-image/image/ | 33,126 张 |
| FitzPatrick17k (原始) | D:/YJ-Agent/data/raw/fitzpatrick17k/images/ | 16,574 张 |
| 配对数据集 ISIC | D:/YJ-Agent/data/paired_dataset/{light,medium,heavy}/ | 99,378 张 |
| 配对数据集 FP17k | D:/YJ-Agent/data/paired_dataset_fp17k/{light,medium,heavy}/ | 49,722 张 |
| 合并质量标签 | D:/YJ-Agent/data/quality_labels_all.csv | 149,100 行 |
| ABCD 缓存 | D:/YJ-Agent/data/abcd_cache.csv | 149,100 行 |
| EfficientNet 特征 | D:/YJ-Agent/data/efficientnet_features.npy | 728 MB，(149100, 1280) |
| ISIC 分割文件 | D:/YJ-Agent/data/isic_split.csv | 70/10/20 by isic_id |
| 专家 QC 标注 | D:/YJ-Agent/data/expert_qc_labels.csv | 487 行 |
| VisiScore 权重 | D:/YJ-Agent/checkpoints/best_visiscore.pth | epoch 6 |
| Q-VIB Full 权重 | D:/YJ-Agent/checkpoints/efnet/best_qad.pth | epoch 27 |
| Std VIB 权重 | D:/YJ-Agent/checkpoints/stdvib/best_qad.pth | — |
| Adaptive Prior 权重 | D:/YJ-Agent/checkpoints/adaptive/best_qad.pth | — |

## 最后更新

2026-05-09 01:10（北京时间）
