# CMedFaith — 验收判据（二元 PASS/FAIL，不存在"基本完成"）

> 读档：`00_README` → `01_STORY` → 本文 → `DATA_INVENTORY` → `04_LOG`。
> 立项前 pilot 判据已冻结在 `reference/KILLSHOT_LEDGER.md`（防 HARKing）。本文=立项后正式验收。
> 数字入任何材料前 Bash/Grep 核 csv + 过 verifier。

## Lever 分解（双贡献 → 可验收单元）

### L1 资源贡献：中文医学 faithfulness 数据集质量
- **L1-a 标注质量**：IAA 达标——response 级 Cohen's κ ≥ 0.7（对标 RAGTruth response 91.8%）；原子陈述级 ≥ 0.6。PASS 线：κ ≥ 0.7 / FAIL：< 0.6。
- **L1-b 许可合规**：分发的证据源只用可再分发许可（Huatuo-26M/维基/CMExam），版权受限源（指南/UpToDate）不进公开发布。二元：有任一版权受限源进发布 = FAIL。
- **L1-c 规模 + 平衡**：faithful/unfaithful 平衡（不搞 PsiloQA 那种 39:261 极不平衡）；覆盖 ≥5 类幻觉类型学（见 DATA_INVENTORY B3）+ 自然/对抗分层。规模阈 ⏳ 待定。

### L2 发现+基线贡献：现成检测器医学域失效
- **L2-a 基线套件全面**：至少覆盖三族——NLI(mDeBERTa/AlignScore)、专用检测器(LettuceDetect/HHEM/MiniCheck)、LLM-judge(GPT-4o/Qwen/DeepSeek)。少一族 = 不完整。
- **L2-b 口径固定**：主指标 = **Balanced Accuracy + Macro-F1**（应对不平衡）；response 级为主口径，claim/span 级作补充但不混报。span 级报 P/R/F1（非 IoU）。
- **L2-c 核心发现成立**：见下 kill criteria。

## Kill Criteria（承重前提，任一 FAIL 触发停下报拍板）

- **K0（撞车终检，动笔前最优先，🔴命门）**：人工核 MedHallu-ZH / SelfElicit（`2025.findings-acl.211`）原文三点——(a) 是否 evidence-conditioned（含外部检索证据）；(b) 是否公开 release + 规模；(c) 是否含对抗幻觉。
  - PASS：MedHallu-ZH 确非 evidence-conditioned（是 self-elicitation）→ headline #1「首个中文医学 evidence-conditioned faithfulness benchmark」成立。
  - 部分 FAIL：若它也 evidence-conditioned → headline #1 塌，**退到 #2（自然/对抗分层）或 #3（跨语迁移）**，方向不死但 claim 重心移，停下报拍板。
  - **✅ 2026-07-11 实测 PASS**（researcher 逐段核 PDF 2025.findings-acl.211 §C.2）：MedHallu-ZH = (query, response) 两元组**无外部证据字段**，判幻觉靠专家/世界知识（self-elicitation，reference-free），**确非 evidence-conditioned** → headline #1 成立。规模 zh 2704 response/18031 句；自然幻觉非对抗；已有 zh+en 平行集但未做迁移诊断；**无公开 release 链接**。
  - **两 TODO（动笔前人工确认）**：(a) MedHallu-ZH 是否真公开可下（影响我们"独立公开资源"亮点强度）；(b) zh 测试集是否也有 severity 分层（原文只明写 en）。
  - **收紧的措辞红线**（结转 STORY）：② 检测器横评须限定"evidence-conditioned 设定下"（它已横评 9 个 reference-free 方法，别泛称首个方法横评）；③ 别 claim 首创难度分层（它有 severity），只 claim"自然+对抗对照"；④ 别 claim"首个中英平行医学幻觉集"（它已有平行集），改"跨语迁移诊断分析"。

结转自 pilot 的三条残留（KILLSHOT_LEDGER）：

- **K1（补第二承重臂）**：加 LLM-judge 臂后，医学域失效（G_domain 或医学 BA 显著低于通用）**是否仍成立**。
  - PASS：≥2 承重检测器族上，医学显著弱于通用（CI 排除 0）。FAIL：judge 臂上医学不弱 → 失效是 mDeBERTa 单模型伪迹，核心发现塌，停下报。
- **K2（控对抗构造 confound）**：**自然幻觉 vs 对抗构造幻觉分层**后，"医学域更难"是否残留。
  - PASS：自然幻觉子集上医学仍显著难于通用自然子集。FAIL：难度纯来自对抗构造 → 不能 claim 医学领域难，改口径为"对抗鲁棒性"，停下报。
- **K3（中文迁移）**：自建**中文**医学数据上，现成检测器是否同样失效（英文 pilot 结论迁移到中文）。
  - PASS：中文医学上现成检测器显著弱。FAIL：中文医学不难 → benchmark 价值存疑，停下报。

## 阶段闸（半天级收口跑 /stage-gate）

| 阶段 | PASS 条件 |
|---|---|
| P1 数据构造 pilot | 小规模（~100条）中文医学 faithfulness 构造通 + 人工抽检幻觉质量合格 + K3 初验 |
| P2 数据集成 | 全量数据 + IAA κ≥0.7（L1-a）+ 许可合规（L1-b）+ 类型/分层覆盖（L1-c）|
| P3 基线评测 | 三族基线全跑（L2-a）+ 口径固定（L2-b）+ K1/K2 通过（L2-c）|
| P4 成稿 | Limitations + Ethics + Responsible NLP Checklist（ARR 强制）+ 数字三方对账 |

## 红线（违反即 FAIL，不放行）
1. **faithfulness ≠ factuality**：只评"答案对给定证据"，筛掉"答案对世界知识"的 factuality 样本（过半幻觉检测失败源于混淆二者，arXiv:2508.08285）。
2. **口径不混报**：response/claim/span 级分开报，不挑高的报。
3. **不 overclaim 难度归因**：K2 未过前，不 claim 难度来自"医学领域本身"（只能说"现成检测器在此数据上弱"）。
4. **临床数据伦理**：去标识 + 数据来源合规 + Ethics Statement（临床 resource 论文 reviewer 必查）。
5. **数字核 csv**：所有报告数走 Bash/verifier，不信 Read。
6. **复现**：检测器超参查官方源，查不到标 TODO；数据/代码/prompt 公开。
