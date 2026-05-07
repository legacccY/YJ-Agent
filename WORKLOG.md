# 工作日志

## 当前状态

- **阶段**：阶段五（Agent 系统）完成验收 ✅，可进入阶段六（Benchmark）
- **上次完成**：
  - `agent/tools.py`：VisiScore / ABCD / EfficientNet-B0 / Q-VIB 封装为可调用工具（quality_assess / extract_features / triage）
  - `agent/orchestrator.py`：Qwen3-8B ReAct 状态机（含规则引擎 fallback，最大 3 轮追问）；修复 LLM 仅检测一次
  - `agent/question_bank.py`：5 维质量问题 + 4 条临床追问模板库
  - `app.py`：Gradio Demo（图片上传 + 多轮对话 + 分诊结果展示）
  - `agent/eval_agent.py`：端到端评测脚本（引导选择性 + 分类性能）
  - 质量阈值校准：OVERALL_THRESHOLD=0.50，is_acceptable 改为只用均值判断（不再逐维度判断）
  - `tests/test_agent.py`：20 个新测试，总计 62 tests 全绿

- **阶段五验收结果（2026-05-07）**：
  - 低质量图追问率：59.0%（目标 ≥ 50%）✅
  - 高质量图追问率：15.5%（目标 ≤ 30%）✅
  - 端到端推理：40ms（目标 < 3s）✅
  - eval_agent.py 输出报告已生成：results/eval_agent_report.md ✅
  - 引导选择性测试：[PASS] ✅

- **Gradio Demo 验收（2026-05-07）**：
  - 低质量图（重度降质）→ Agent 追问重拍：「拍摄有点晃动，可以试试贴近对象放慢拍摄，清晰度会更好。」✅
  - 重拍高质量图 → Agent 直接输出分诊：🟢 低风险，恶性概率 4.2%，ABCD 特征完整，免责声明显示 ✅
  - UI 截图存档：`demo_heavy.png`（追问流）、`demo_retake.png`（完整流）
  - 运行端口：7862（7860 被旧进程占用）

- **Qwen3-8B 下载状态**：后台下载中（约 1 GB / 16 GB，继续进行中）
  - 下载完后运行 `cd D:/YJ-Agent/project && python test_llm_react.py` 验证 LLM ReAct

- **下一步**：
  - 选 A：等 Qwen3-8B 下载完成，切换为 LLM 驱动的完整 Demo
  - 选 B：直接进入阶段六（Benchmark）

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

2026-05-07 21:16（北京时间）
