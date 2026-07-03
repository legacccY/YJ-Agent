# WardAgentBench — DATA_INVENTORY（公开数据细目）

> 全部**公开数据**（无真实临床数据可用）。license/门槛来自 researcher 2026-07-02 核实，见 `reference/LANDSCAPE_2026-07-02.md`。用前查 `.portfolio/datasets.json`（跨论文真源），换路径只改那里。

## 🎯 候选 B 主数据（多告警器复合误报 benchmark，2026-07-02 起主轴）
| 数据集 | 内容 | 候选 B 用途 | 门槛 | 状态 |
|---|---|---|---|---|
| **MIMIC-III/IV Waveform Matched** | ICU 波形（ECG/PPG/ABP/RESP）+ 数值 | **承重**：按 Chromik et al. 派生多阈值告警共触发事件 + 结局代理定真/假 | PhysioNet credentialed + CITI + DUA | 需办 CITI（KS-2，用户线下） |
| PhysioNet 2015 Challenge | 1250 段危急告警（5 类，**单告警/段**） | 命门对照：确认单告警标签**无法**供共触发标注（锁死结论） | 开放（登录） | 可用 |
| VTaC (NeurIPS D&B 2023) | 5037 VT 告警（1441 真/3596 假，**全单类**） | 单告警器 true/false 参照 baseline | 公开 | 可用 |

> ⚠️ **命门（KS-3）**：多告警「共触发 + 逐告警真/假」在这些集**不带标注地存在**，须自派生（阈值规则 + 结局代理）。稿中必显式声明标签为派生（R8）。共触发是否真频繁/相关 + 复合 FAR 阈值族稳健性 = 立项生死，动笔前先证。
> ⚠️ 生理波形切窗严禁泄漏（同一病人不跨 train/test，R2）。

## 腿 A 开源实现 / 中文（次要，KS-3 NO-GO 退路 + RAG 语料）
| 数据集 | 内容 | license | 状态 |
|---|---|---|---|
| Huatuo-26M-Lite | ~177K 中文医疗 QA（RAG 语料，许可最干净） | Apache-2.0 ✅ | 可用 |
| MedSafetyBench | test 900 安全拒答率 | MIT ✅ | 可用 |
| MedDG / CBLUE-CHIP | 中文医疗对话/理解 | ⚠️ license 待确认 | 用前确认 |

## 评估规范（报告用，非数据）
- TRIPOD-LLM（living，交互站 tripod-llm.vercel.app）+ DECIDE-AI（早期临床评估）+ HealthBench（rubric 化）。仍是 2026 主流。

## 慧脉自有「数据」
- **无真实临床数据**。唯一实资产 = RAG 知识库（中华医学会指南~500 + 药监局药物库~3000 + 疾病科普~1000 + ICD-10~14000 WHO 中文）——公开源整理，可复用作 RAG 语料，非评估集。
