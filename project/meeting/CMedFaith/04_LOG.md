# CMedFaith — 项目日志（时间倒序，单一真源）

---

## 2026-07-12 凌晨 · 整晚自主：NVIDIA 限流规律定案 + 首批 17 条干净数据跑通

**整晚在 NVIDIA 限流上反复搏斗，最终定案（用户回来提醒"别泄漏/别卡住"，已彻查无泄漏——见下）：**

**🔴 NVIDIA 免费层限流完整规律（血泪定案）**：
- **per-model 配额，且严重程度差异极大**。生成器 qwen3-next-80b（MoE a3b）**海量调用始终 0 失败**；qwen3.5-122b/mistral-small-119b **0 失败**；llama-3.1-8b **轻微**（5% 级，小模型重试快不卡死）。
- **🔴 Google(gemma) 家族账户配额极紧**：gemma-4-31b（150条 355失败）、gemma-2-2b（50条 175失败）**大小都撞**，且 31B 重试慢会拖死 phase2（5h+）。**gemma 系彻底弃用**。
- **投票阶段是重灾区**：每个投票器要判所有候选（150条=1350个/投票器），高频批量放大限流。
- **对策定案**：①生成器 qwen3-next-80b ②投票器避开 Google，用 **qwen3.5-122b + llama-3.1-8b + mistral-small-119b**（Qwen/Meta/Mistral 三家）③并发1（瞬时1请求，配合小模型不卡死）④单批 ≤50-80 条（投票总量可控）。**反复 kill 4 次的教训：别赌单模型、别大批并发，避开 gemma 是关键。**

**✅ 首批跑通（20条→17条干净数据，v3 组合）**：失败率 5%（758调用42失败全在 llama-8b 轻限流），24min。产出 `code/data/zh_med_pilot.csv` 17 条，备份 `_scratch/nvidia_batch1_17rows.csv`。**构造集全体={qwen3-next-80b(生成), qwen3.5-122b, llama-3.1-8b, mistral-small-119b}→P3 承重 judge 避开 Qwen/Meta/Mistral 三家族**（剩 step/gpt-oss/seed/nemotron/stockmark/deepseek/Google-judge 可用）。
- **质检达标**：结构 evidence-conditioned 三元组完整；抽检幻觉质量高（例：证据只说"隐性感染最常见"无数字→幻觉编"发生率95%/显性1%"，结论对但塞证据外数字，NLI证据→幻觉=0.002，教科书级 faithfulness≠factuality）。
- **⚠️ 待改（留白天，非阻塞）**：类型偏斜 fabricated_guideline 12/17=70%（生成prompt/投票器倾向）；难度无 hard 偏易。放大时改造幻觉 prompt 均衡类型。

**🔒 泄漏彻查（用户凌晨警觉"别泄漏"）**：四项审计全过——api_keys.env 未被 git 追踪（gitignored）/ 完整 key 未进任何追踪文件（04_LOG 原有 6字符"nvapi-"前缀说明已抹除）/ 阿里云 AK 未进文件 / 暂存区无敏感文件。脚本 key 从环境变量读不硬编码、log 不打印 key 值。**⚠️ 提醒用户去阿里云 RAM 作废那对明文 AccessKey（账号级主凭证）。**

**✅ 80 条批完成（凌晨自主）**：v3 组合跑通，失败率 6%（llama-8b 189次+qwen122b 8次，不卡死），84min。**产出 70 条干净数据，类型覆盖 7 类**（fabricated_guideline 36/incomplete 16/dosage 7/mechanism 5/baseless 2/outdated 2/overclaim 2）+ 难度 medium29/easy41。备份 `_scratch/nvidia_batch2_70rows.csv`。**接近 P1 pilot 达标规模（~100条），类型覆盖达标（≥5类）。**

**⚠️ 待改（白天，非阻塞）**：类型仍偏斜（fabricated_guideline 51%）；难度无 hard；放大改造幻觉 prompt 均衡+加难度。

**下一步（下次开工，优先级序）**：
1. **K3 大样本重验规模依赖**（核心！用 70 条造平衡集，硅基流动 judge 池 GLM-4-9B/Hunyuan/MiniMax/GLM-4.5-Air 与旧28条可对比，验"规模依赖失效"是否更稳）。K3 脚本 `code/k3_probe.py` 接口待核（可能要改数据路径/judge）。
2. 继续放量到 150-200 条（同 v3 组合，凑 P3 样本量）。
3. **P3 拍板两件仍挂**：0.90 阈口径 / headline 最终措辞（等 K3 大样本定）。

**收工状态（2026-07-12 凌晨）**：数据构造管线在 NVIDIA 上打通（限流规律定案：避开 Google，qwen生成+Qwen/Meta/Mistral投票+并发1+≤80条/批）。有 70 条 P1 达标数据。K3 重验是下次第一优先。

---

## 2026-07-11 · P2 转 NVIDIA API 构造 + 限流规律摸清 + 脚本加并发 + 150 条放量在跑

**背景**：用户提供 NVIDIA NIM API key（build.nvidia.com 服务 key，OpenAI 兼容端点 `https://integrate.api.nvidia.com/v1`），明确"没上限随便跑"。决定 P2 正式数据**统一用 NVIDIA 重构**（方案 A），旧硅基流动 14 条备份到 `_scratch/pilot_siliconflow_backup/`（不进正式集）。key 只存 gitignored 的 `_scratch/api_keys.env`（脚本从环境变量读，不硬编码，不进 git）。

**⚠️ 安全**：用户先贴了阿里云 AccessKey（`LTAI...`+secret，账号级主凭证，风险远大于模型 key）→ 已提醒**务必去 RAM 控制台作废**，未写入任何文件。NVIDIA key 是模型服务 key，风险可控。

**关键工程发现（放量前踩通）**：
1. **`/v1/models` 列出 121 个 ≠ 账户都能调**：实测 42 个候选，22 可用。404 不可用=kimi-k2.6/yi-large/**palmyra-med-70b(医学专用可惜)**/nemotron-340b/253b/gemma-3-4b/12b/ibm-granite/dbrx。可用清单见 `_scratch/nv_probe2.py` 输出。
2. **能调通≠中文能用**：nemotron 系多数 zh0（返回空/英文）或 CoT 泄漏（reasoning 模型复述 prompt 没真答）；gpt-oss/seed/step 返回英文。**中文强+稳定档**=mistral-large-675b/qwen三档(80b/122b/397b)/llama-70b·8b/gemma-4-31b/mistral-small-119b/stockmark-100b。
3. **🔴 真瓶颈=RPM 限流，且模型越大越严（per-model）**：limit10 用 deepseek-v4-pro 生成器+并发8→142 次 429 打废；limit5 用 mistral-large-675b→155 失败、llama-70b→46 失败，qwen3-next-80b/gemma-4-31b **0 失败**。规律=**巨模型(≥100B)高频调用必 429，中小模型限流松**。
4. **对策=全中小模型+并发 2**：生成器 `qwen3-next-80b`(MoE a3b，中文所有模型里最好之一，0失败) + 投票器 `gemma-4-31b`/`llama-3.1-8b`/`mistral-small-119b`（四家不同：Qwen/Google/Meta/Mistral）+ `--api-concurrency 2` → **limit5 失败率 0%（181调用仅1失败），280s/5条**。

**脚本改动（主线，6 处，py_compile 通过）**：`build_zh_med.py` 的 `OpenAICompatBackend` 加并发——`generate_batch` 用 ThreadPoolExecutor（`--api-concurrency` 控，默认1=串行保持原行为），counter 自增加 threading.Lock 防竞态；`make_backend`/CLI 贯通传参。这是放量提速关键（原串行是瓶颈）。

**真实速度**：~40s/条（扣 ~80s 一次性 NLI+embedding 加载）。放量估：100条≈1.1h/150条≈1.7h/200条≈2.3h。

**🔄 在跑**：P2 放量 **150 条**（qwen3-next-80b 生成 + 三家中小投票 + 并发2，后台 `b5ny99l1b`，log `_scratch/nv_p2_150.log`，约1.7h）。**构造集全体={qwen3-next-80b, gemma-4-31b, llama-3.1-8b, mistral-small-119b}→P3 承重 judge 须避开这四家族**（Qwen/Google/Meta/Mistral，剩 step/gpt-oss/seed/nemotron/stockmark/deepseek 够用）。

**⚠️ 待观察**：limit5 小样本类型覆盖偏窄（5条仅1-3类型），放量到 150 条看类型/难度覆盖是否自然铺开（旧硅基流动版覆盖5类）；phase2 保留率 31%（投票器组合变化）。跑完 analyst 解读 + 质量抽检。

**下一步（150条跑完）**：①质量抽检 + 类型/难度覆盖核 ②K3 大样本重验规模依赖（当前仅28条）③达标则 P1 阶段闸 → 考虑 P2 全量。P3 待拍板两件（0.90阈口径/预算——NVIDIA 无上限，预算点弱化）仍挂。

---

## 2026-07-11 · P3 设计闭环（planner→skeptic→researcher 三轮）+ 待拍板两件

**接上条「先稳一步」拍板，本轮完成 P3 横评设计闭环，三 agent 全回：**

**① planner 出 P3 矩阵**（`PLAN/P3_MATRIX_scale_dependence.md`）：检测器全谱 D1-D15 四族齐；规模曲线核心 run R-P3.13（双面板：judge 族内能力单调轴 + 专训小模型带）；样本量 28→建议 ≥400（理想 600），Wilson CI 推导（聚合 n=200 unfaithful 充分）；bootstrap 10000 + Spearman 单调性 + paired bootstrap + Holm。**自报 flag-A**：Qwen2.5-72B 是构造投票器却被当强 judge 上界臂→重犯🔴-2，建议承重 judge 排除构造集。

**② skeptic 红队：0 致命 ✅ 放行**。主动证伪最凶一条——4 个 K3 test judge 无一是构造投票器，「强 judge 抓得住只因没参与构造」confound 不成立（对四 judge 对称）。6 条🟡（不阻断，跑时顺手折入）：
- 🟡-A：排除清单须改**家族粒度**——DeepSeek-R1 与生成器 V3.2 同源基座，当承重 judge 是部分构造循环；主 XL 锚用 MiniMax/GLM-4.5-Air（非 DeepSeek、非投票器，干净），R1 仅参考臂。冻结时含**生成器身份**。
- 🟡-B：GLM-4-9B vs GLM-4.5-Air 是跨代跨架构（dense→MoE），叫「控训练配方因果最强单点」overclaim→需真同代梯子或降为相关性。**（researcher 已解，见④）**
- 🟡-C：0.90 阈有 HARKing 嫌疑（pilot 强档已 0.79）→建议 monotonicity 定 primary、0.90 降 secondary、rationale 删「pilot 0.79」只留外部规范、预注册 0.85/0.90/0.95 敏感带。**（待用户拍）**
- 🟡-D：补 K1×R-P3.13 的 2×2 联合结局→headline 映射表，P3 前冻结（防事后挑叙事）。
- 🟡-E：per-type 规模分析 200/8类≈25/类 CI 爆宽→收成 2-3 超组或降定性。
- 🟡-F：真残留=投票器含强模型 Qwen72B + 宽松「骗过≥1」筛→保留幻觉的选择组成影响强档 recall。出路：按「骗过哪些投票器」打层画曲线 + MedFact 自然臂当 robustness。宽松筛对「强档仍漏」是保守方向（利好）。
- 🟢：G-1 平衡集漏检率≠部署 prevalence（Limitations 声明）；G-2 主 XL 锚全 API 不可复现→复现锚须含≥1 开源 judge 进 XL/近 XL 档（R7 张力）；G-3 LettuceDetect 环境（researcher 已解）。

**③ researcher 解前置 TODO（带引用，`PLAN/P3_MATRIX_scale_dependence.md` 待折入）**：
- **干净规模梯子=Yi-1.5（6/9/34B, Apache-2.0）**，未参与构造/中文强/可复现→§2.3 因果语言保住（Yi 家族内 within-family + GLM 家族内并列双证据）。第二对照 InternLM2.5（1.8/7/20B，权重商用需申请、学术可用）。Gemma-2 弃用（自定义许可非 OSI + 中文弱）。
- **LettuceDetect（D5）隔离方案**：独立 venv（python3.11 + numpy2.2/torch2.6/transformers4.48.3），根因=主环境 numpy 降 1.26.4 与其 numpy≥2.2.2 冲突；mmBERT 版支持中文无 transformers 5.x 上限。D5 中文臂可保，不退 Limitations。
- **许可全清**：Lynx-8B=CC-BY-NC（须写 non-commercial）、Bespoke-MiniCheck-7B 商用受限（主横评只用 MIT 变体 Flan-T5/DeBERTa/RoBERTa）、HHEM=Apache、MiniCheck-Flan-T5=MIT、LettuceDetect=MIT、SummaC=TODO 核 repo LICENSE。全部学术发布 OK。
- **能力代理分 TODO（未公开不臆想）**：Yi-1.5/InternLM 各档精确 C-Eval/CMMLU/MedQA-zh、MiniMax/Hunyuan 中文医学分、所有候选 CMB/MedBench→查 OpenCompass 或本地实测；GLM-4-9B C-Eval 检索 81.5 vs PLAN 记 87.2 需以 arXiv:2406.12793 复核。横轴降级=「已知通用中文分+参数量档」。

**🟡 处理方针**：🟡-A/D/E/F + researcher 选型（Yi 梯子/LettuceDetect venv/许可）= 主线自主折入 PLAN（纠错+落档，不改战略）。🟡-C（0.90 阈口径）= **待用户拍板**。

**🛑 待用户拍板两件**：
1. **P2 全量构造 API 预算**（唯一花真金）：主线荐先 ¥20-60 小批 2000 条验信号→站得住再全量 ¥300-900。
2. **0.90 阈口径**：主线荐按 skeptic 🟡-C 改（monotonicity 主判据 + 0.90 降辅助 + 删 pilot 后见 + 预注册敏感带）。

**下一步（拍板后）**：折 6🟡+选型进 PLAN + 冻结判据写 KILLSHOT → 放量 pilot（P2 小批）。设计/代码全绿，卡点=用户拍预算+阈值。

---

## 2026-07-11 · 拍板 claim 方向「先稳一步」+ 落档 + 启动 P3 横评设计

**拍板点决议（用户）**：K3 揭示失效是**规模依赖**非**系统性**，headline 重心怎么定 → 用户选 **「先稳一步」**（不彻底改死 headline，把精化 claim 当**工作假设**落档，等 P3 大样本回来再拍最终措辞）；下一步 = **落档 + 设计 P3 横评**。

**已落档三处**：
1. **STORY**：headline「系统性失效」软化为「不可靠 / 失效边界」；新增「⚠️ 工作假设更新」块（记 K3 四 judge 数据 + 当前工作假设「中小 judge+NLI 族不可靠，能力随规模升但最强 judge 仍漏 20-30%」+ 不锁死程度词 + caveat）；Headline 策略段加「#1 内部失效程度轴」分档规则（P3 前一律用谨慎版 b）；措辞红线加「不 claim 无条件系统性失效」。
2. **ACCEPTANCE**：K3 判据补初验记录（规模依赖形态）+ 新增「P3 验收口径」（按规模/族分档报 recall/BA+bootstrap CI，画能力→可靠性曲线，验规模依赖稳健性，含 PASS/FAIL 线）。
3. **本 LOG**。

**关键定调**：pilot 28 条不足以锁死 headline；「系统性失效」vs「规模依赖失效边界」的最终选择等 P3 大样本（D2-D15 全谱 + 放量 + bootstrap CI）数据说话。**不 overclaim、不过早锁死 = 守纪律。**

**下一步（在做）**：派 planner 按对齐后的 ACCEPTANCE（含 P3 验收口径）+ 现有 `PLAN/EXPERIMENT_MATRIX_P1-P3.md` 设计 P3 全套横评实验矩阵——重点=严格验证规模依赖曲线。planner 回来 → skeptic 红队设计（0 致命即过）→ 落 PLAN → 拍板放量/上算力。

---

## 2026-07-11 · 收工（史诗场：全量设计→真数据→K3命门规模依赖发现）

**本 session 完成（详见下方各 entry）**：
1. **全量实验设计定稿**（PLAN/EXPERIMENT_MATRIX_P1-P3.md）：15检测器/4族×三级×5-6分层=12表8图8分析块（远超EACL），skeptic红队3🔴命门→用户拍板**对称化**修复+MedFact三角+K2重述，判据预注册冻结。
2. **双管线建成验证**：`code/eval_harness.py`(评测,全量复现精确命中0.4277/0.7204/G_domain0.2927) + `code/build_zh_med.py`(中文构造,CMExam证据源,MedHallu四阶段)。
3. **真中文医学faithfulness数据产出**：算力卡壳(本地8GB放不下/HPC队列满)→转全API(硅基流动DeepSeek-V3.2生成+多judge投票+本地CPU NLI/embedding)。20条pilot质量达标(evidence过滤守R3,幻觉塞假指南/假数值)。
4. **K3命门初验(4 judge)**：`code/k3_probe.py`。**规模依赖发现**——中小judge(GLM-4-9B 0.14/Hunyuan-13B 0.29 recall_unfaithful≈失效)但强模型(MiniMax/GLM-4.5-Air 0.71-0.79 抓得住)。

**🔴 claim 待深议(下次拍)**：核心claim「现成检测器系统性失效」**过强**,数据揭示是**规模/部署依赖的失效**(中小judge+NLI族失效,强模型挽回但仍漏20-30%)。这正是skeptic K1判据预埋分支+用户要的实验↔叙事互调。方向精化待用户定,正式措辞等P3大样本。

**环境/安全**：numpy降1.26.4(修lettucedetect顶numpy2撞scipy);硅基流动key存`_scratch/api_keys.env`(gitignored,✅git不追踪)。⚠️**提醒用户:key曾在对话明文,建议硅基流动后台删重建**。总API花费这场≈¥1-2。

**下次入口**：本entry + `PLAN/EXPERIMENT_MATRIX_P1-P3.md` + `reference/RESEARCH_BRIEF_2026-07-11.md`。下一步=claim方向深议→P3全套横评(D2-D15+大样本+bootstrap CI严格验规模依赖)/放量pilot。**P1(管线+质量)达标,K3揭示规模依赖失效待精化claim**。

---

## 2026-07-11 · 全量实验设计情报底座（5路researcher）+ 🔴K0命门修正

**本 session（推进实验设计）**：
1. 派 5 路 researcher 并行深调研 → 综合成情报底座 `reference/RESEARCH_BRIEF_2026-07-11.md`（每条带来源）：对标benchmark完整实验协议 / 检测器全谱4族 / 数据构造MedHallu四阶段照抄级细节 / venue(ARR/EACL)标准 / 评测统计方法学。
2. **实验深度靶子量化**：对标EACL/ACL强benchmark中位≈5-6主表/4图/11检测器/3-4分层维/2级评测，普遍软肋=无IAA κ/α·无CI·无校准·单语。CMedFaith"远超"配方=**≥12-15检测器4族+三级评测(response/claim/span)+≥5分层维+≥8主表+≥6图+κ/α+bootstrap CI+AUROC/AUPRC+ECE校准+中英对照**。
3. 派 planner 出正式全量实验矩阵 P1-P3（在跑，落 PLAN/）。

**🔴 K0 命门修正（张冠李戴，必须改）**：
- 之前 K0「PASS」核的 `2025.findings-acl.211` **是误指**——真身="Long-form Hallucination Detection with Self-elicitation"（**通用域**长文本幻觉检测方法，与中文/医学/release全无关）。**"MedHallu-ZH"根本不存在**（MedHallu英文独占，HF/repo无zh分支）。
- **真正该核的中文医学幻觉benchmark = CMHE**（Chinese Medical Hallucination Evaluation, LREC-COLING2024, Chengfeng Dou）：snowballing多轮误导场景，**非evidence-conditioned → 不撞headline #1**，但须补相关工作+正式撞车核查。
- **结论方向不变**：中文医学evidence-conditioned faithfulness仍空白，headline #1成立。但K0核查对象错→待改写ACCEPTANCE/KILLSHOT_LEDGER（保留原文痕迹+加correction，防HARKing），CMHE补撞车条（TODO下载Google Drive核规模/许可/分层）。

**其余待改（brief §6，planner回来一起落）**：DATA_INVENTORY撤MedHallu-ZH条·CMExam许可降级"内部构造不分发"(数据学术禁商用与repo Apache冲突)·B3补2类(过时指南+诊断决策误导)剔reasoning类·RAGTruth是2×2轴(Conflict/Baseless×Evident/Subtle)非并列4类；ACCEPTANCE的IAA对标"RAGTruth 91.8%"存疑(可能是模型F1非IAA→TODO人工核，改用FaithBench Krippendorff α=0.748)+补统计规范(paired bootstrap非McNemar+Holm-Bonferroni+ECE)。

**检测器关键情报**：原生中文专用检测器仅 LettuceDetect多语版(EuroBERT/mmBERT,MIT)；AlignScore/HHEM/MiniCheck/Lynx全仅英文=天然"英→中迁移崩塌"素材；judge中文主力Qwen2.5-7B(Apache,4090可)+GLM-4-9B/InternLM2.5对照。

**下一步**：planner实验矩阵回来 → skeptic红队设计（0致命即过）→ 落PLAN/ + 修STORY/ACCEPTANCE/DATA_INVENTORY/KILLSHOT_LEDGER四处 → P1数据构造pilot（验K3+MedHallu管线中文可跑性）。

**更新（同session续，planner+skeptic回）**：
- ✅ planner 出全量实验矩阵 `PLAN/EXPERIMENT_MATRIX_P1-P3.md`：15检测器/4族 × 三级评测 × 5-6分层维 = 10表7图7分析块（远超EACL中位），三命门判决实验+预注册判据+退路，实验↔叙事互调映射表。
- 🛑 **skeptic 红队 3🔴 致命（已联网核实，PLAN §0.5）**：同根=对照锚 PsiloQA-zh 未与我们"骗过≥1检测器"筛过的 zh-med 匹配。🔴-1 选择伪迹冒充域效应(K1/K3假闸)；🔴-2 构造投票器Qwen2.5-7B=K1承重judge D10循环；🔴-3 **Evident/Subtle≠natural/adversarial**(RAGTruth全自然/我们全对抗构造零自然样本)→K2对抗confound控制无效。**仅阻断K判决run(R-P3.4/3.5/3.6)+判据预注册，P1/P2/主横评不阻断可推进**。
- 🔴-1/🔴-2 修法明确(换非投票judge+对照锚同筛)。**🔴-3=拍板点**：建自然医学臂(额外采集标注成本)换干净K2「医学域本身难」 vs 降级headline #2「对抗鲁棒性」→抛用户拍板。
- **下一步**：用户拍 🔴-3 → 回 planner 统一修 K 判决对比设计 + 派 researcher 解TODO → P1 起(R-P1.0英文复现无依赖)。

**里程碑（方案A定稿 + R-P1.0 管线验证 PASS）**：
- ✅ **用户拍板方案A**（对称化主力+MedFact自然臂三角互证+协变量回归）→ planner 出 K 判决定稿（PLAN §0.6）：🔴-1 对称通用对抗锚 zh-gen-adv(同管线同筛)/🔴-2 K1承重judge换非投票D11/D12·D10降构造臂/🔴-3 K2重述「等构造强度下医学域仍难」+MedFact三角。新增 R-P2.7/R-P3.12/R-P3.5-appx，体量升 8资产/12表/8图/8分析块。
- ✅ **前置TODO全解**（researcher）：MedHallu逐字管线(embedding all-MiniLM-L6-v2/蕴含roberta-large-mnli τ=0.75/judge 0-1-2 prompt)+finetune超参(RAGTruth lr2e-5/1ep,batch未披露TODO)+许可全核(MiniCheck-Bespoke/Lynx=CC-BY-NC禁商用)+**RAGTruth 91.8%/78.8%确是IAA但未校正**+CMHE不撞。落 brief §7。
- ✅ **R-P1.0 全量复现精确命中冻结锚**：MedHallu 0.4277/PsiloQA-en 0.7204/G_domain 0.2927 CI[0.184,0.391] 三值全中(Bash核 code/results/)。统一评测 harness(三级+BA/F1/MCC/AUROC/AUPRC+bootstrap10000+paired bootstrap+Holm)建成验证。**L2基线地基牢**。
- ✅ **四处文档更新**：PLAN §0.6定稿 / ACCEPTANCE(K0修正留痕+K2重述+IAA口径+L2-b统计规范) / KILLSHOT(三🔴红队+方案A预注册冻结防HARKing+对称锚同筛清单) / DATA_INVENTORY+STORY(writer在改)。
- **命门修正**：K0张冠李戴(MedHallu-ZH不存在,实为SelfElicit通用域)→真对照CMHE(非evidence-conditioned不撞)已改档。
- **代码就绪（两脚本 + 双烟测 PASS）**：
  - `code/eval_harness.py`（统一评测 harness，R-P1.0 全量复现精确命中冻结锚）。
  - `code/build_zh_med.py`（R-P1.1 中文构造，MedHallu 四阶段复刻，开源为主+`--use-openai`可选，🔴-2 硬校验解耦）。**mock 烟测 PASS**（生成18候选→投票保留9→蕴含过滤→兜底2条,管线逻辑通,不占卡不联网）。
- **用户决策**：API「迟早要搞」但 pilot 先零成本开源版（GPT-4o-mini pilot<$1/全量$25-50 其实极便宜；开源中文模型当投票器更合理）。
- **前置选型已定（researcher 2026-07-11）**：[V3]第三投票器=**Yi-1.5-9B-Chat**(Apache2.0,避开GLM/InternLM满🔴-2)；[EMB]=**bge-base-zh-v1.5**(MIT,C-MTEB 63.13)。
- **🔴 承重张力（证据源）**：Huatuo-26M(可分发Apache2.0)的 encyclopedia_qa/KG_qa **都只有Q/A无独立证据段→做不了evidence-conditioned**(核心护城河)；唯一有独立证据段的=**CMExam**(`Explanation`临床解析4-3k字→context / `Question+Answer`→忠实answer,结构完美,Apache2.0)但**国家医师考题许可受限**(DATA_INVENTORY已标只内部构造不分发)。矛盾=可分发的做不了evidence-conditioned,能做的不能分发原文。**推荐解法**：CMExam内部构造,发布只发生成的幻觉答案+CMExam指针(不重分发Explanation原文),核CMExam LICENSE确认(MedHallu外常见合规做法)。⚠️CMExam是选择题解析当证据,与典型RAG检索文档段性质略异,需在数据构造说明写清。
- ✅ **build_zh_med.py 改CMExam + 选型填好 + 端到端验证通过（用户选A，2026-07-11）**：coder 改 loader(Huatuo→CMExam)+填V3=Yi-1.5-9B/EMB=bge-base-zh；主线核 CMExam features(`Question/Options/Answer/Explanation`匹配)+**修 `_parse_options` bug**(HF版Options是`[{key,value}]`dict-list非字符串,原解析全空→加dict-list分支)；端到端验证 load_cmexam **0 skip**,evidence=Explanation解析段/gt_answer="针对问题「Q」正确答案是X"/correct_letters正确=**真 evidence-conditioned 结构**。mock 烟测管线通。🔴-2 解耦确认(Yi不在judge臂放行,GLM/InternLM仍拦)。
- **⚠️ 待拍板（上 HPC 跑正式 pilot）**：脚本全就绪,差上传 HPC+占卡。HPC 跑 `build_zh_med.py --backend vllm --limit 150`(Qwen2.5-14B生成+3投票器Qwen7B/Gemma9B/Yi9B+mDeBERTa NLI+bge,模型串行加载,14B可能超单卡24GB需量化/tp2)。上传新代码=拍板点已报方案待用户点头。
- **算力转向全 API（2026-07-11，用户选）**：本地8GB放不下(三9B投票器)，HPC核查发现 gpu4090 **配额被别项目占满**(账号下已7个GPU job PD排队:ncacyst×3+r1/r3×4)+login无python要配环境+上传硬门禁+50GB模型下载 → 真跑pilot卡在GPU算力/环境(非设计/代码,那些全绿)。**转全API绕开GPU**：coder 扩 build_zh_med `--backend api`(OpenAICompatBackend 可配base_url指向DeepSeek/Qwen/OpenAI,生成器+投票器走API不占GPU,本地CPU只跑mDeBERTa NLI+bge embedding),含retry/超时/`--api-max-calls`成本保护。mock验通过。
- **推荐 DeepSeek**(中文医学好/极便宜150条<¥1/国内免梯子)：`--backend api --api-base-url https://api.deepseek.com --api-key-env DEEPSEEK_API_KEY --gen-model deepseek-chat --voter-models deepseek-chat deepseek-reasoner deepseek-chat --device cpu`。投票器多样性:DeepSeek仅chat+reasoner两款,正式pilot要三家多样性可用OpenRouter聚合器(一key跑deepseek/gpt-4o-mini/qwen三家)。
- **⚠️ 待用户提供 API key** → 设环境变量 → 主线跑 limit3 小试看真数据 → 通了放 20/150 条。**这是唯一卡点**(脚本+设计全就绪,mock验通)。
- **✅ 里程碑：真中文医学 faithfulness 数据产出（2026-07-11，硅基流动 API）**：key存`_scratch/api_keys.env`(gitignored)；跑 `--backend api` limit3 mini-pilot：生成器`deepseek-ai/DeepSeek-V3.2`+投票器三家`DeepSeek-V3.2/Qwen2.5-7B/Qwen2.5-72B`(避开K1 judge守🔴-2)，本地CPU跑mDeBERTa NLI+bge-base-zh。**108次API调用0失败,成本≈¥0.1-0.3**。CMExam证据源0 skip,Phase2保留8/27(骗过≥1),Phase3 8/8(ℰ<0.75滤同义),产出3条(easy2/medium1,3类型)。数据在 `code/data/zh_med_pilot.csv`。
- **数据质量评估(诚实)**：evidence-conditioned三元组结构完全正确。样本1(机制误归因)质量高=编假机制"砂仁后下因保护生物碱抗炎活性"(真因是挥发油,证据无此说)；样本2(过度断言)中等=加"完全/绝对"绝对化；样本3(信息不全)**偏弱**=太接近正确(骗过2/3票+蕴含E最高0.0072,撞skeptic警告"难例贴近GT易假到不够假")。**P1闸"管线中文可跑性"达标**；质量提升空间=质检层更严+造幻觉prompt让偏离更明确。
- **✅ P1 数据构造管线+质量达标（2026-07-11，20条pilot）**：coder 补两优化——① Phase3 加 evidence-grounded 过滤(nli_evi2hallu=NLI(证据,幻觉),≥τ_evi0.5=被证据蕴含=忠实=滤,守R3 faithfulness核心判据) ② 强化造幻觉prompt(引入证据外/矛盾具体内容)。20条pilot:**720 API调用0失败**,phase3-GT过滤后30→**evidence过滤滤掉6条"其实忠实"**(解决mini-pilot样本3漏网)→产出14条。nli_evi2hallu分布min0/中位0.004/max0.102全<<0.5,滤掉的≥0.5,**0.1~0.5间无样本=τ_evi0.5分得干净**(coder担心的误滤没发生)。类型覆盖5类(fabricated_guideline5/incomplete4/dosage2/mechanism2/overclaim1),难度easy7/medium7。成本≈¥1-2。
- **质量抽检**:幻觉都塞证据外假细节=假指南引用(《神经生理学标准指南》5.3节/《2023中国血脂指南》5.2条)、假数值(特异性阈值80%/煎煮30分钟)、假机制→**结论常对但不忠于证据**=faithfulness幻觉精髓,完美契合faithfulness≠factuality定义。数据 `code/data/zh_med_pilot.csv`(14条)。
- **✅✅ K3 初验命门信号正面（2026-07-11，强支持核心 claim）**：用**独立** LLM-judge GLM-4-9B(`THUDM/GLM-4-9B-0414`,硅基流动,未参与构造避🔴-2循环；LettuceDetect mmBERT撞transformers版本地狱`TokenizersBackend`缺失,升级会破坏已验证脚本故弃用改judge)测 28 条平衡集(14忠实+14幻觉)。**结果:recall_faithful=1.0(14/14忠实全判对)但 recall_unfaithful=0.143(14条幻觉只抓出2条,放过12条!),BA=0.571(≈随机),Macro-F1=0.475**。28次API调用0失败,成本≈¥0.x。
- **解读**:GLM-4 放过的12条幻觉=假指南引用(《神经生理学标准指南》第5.3节-捏造)、假数值(煎煮30/15分钟、特异性阈值80%)、假机制——**judge看结论对就判faithful,抓不住藏的证据外假细节**,正是混淆factuality(结论对)与faithfulness(忠于证据)的命门。**初步支持「现成检测器中文医学faithfulness系统性失效」,值得上P3全套横评**。caveat:28条小样本粗信号非P3正式;幻觉是"骗过≥1投票器"对抗样本(构造强度有份);单judge(GLM-4-9B较小,大judge如GPT-4o/R1待P3测)。结果 `code/results/k3_probe_judge.csv`。
- **环境变动**:装 lettucedetect 0.2.2(顶numpy2.2.6撞崩scipy)→降 numpy 1.26.4 修复(scipy/sklearn/transformers兼容,是修复);lettucedetect当前跑不了(mmBERT需新transformers,不动稳定环境)。
- **🔴 K3 多 judge 普遍性验证：命门信号分化，claim 需精化（2026-07-11，重要诚实发现）**：4 个独立跨家 judge 测同 28 条——
  | judge | recall_unfaithful | BA |
  |---|---|---|
  | GLM-4-9B | 0.143 | 0.571 |
  | Hunyuan-A13B | 0.286 | 0.607 |
  | MiniMax-M2.5 | **0.786** | **0.786** |
  | GLM-4.5-Air | **0.714** | **0.786** |
  **中小模型(9B/13B)失效(recall0.14-0.29≈随机),但强模型(MiniMax/GLM-4.5-Air)抓得住大部分(recall0.71-0.79)**。→ **claim「现成检测器系统性失效」过强,须精化**。这正是 skeptic K1 判据预埋的分支(互调表"judge臂不弱→claim收缩")+用户要的实验↔叙事互调真实发生。
- **精化后 claim(待用户拍)**：「中小模型judge(部署常用档)+NLI族在中文医学faithfulness不可靠;能力随模型规模显著提升,但最强judge仍漏20-30%幻觉」——更nuanced/更真/更难被攻,契合MedHallu"大模型judge更好"规律。caveat:28条小样本噪声大;强模型0.79也非满分(faithfulness仍难);对抗样本构造强度有份。总成本这几轮≈¥1-2。逐judge结果 `code/results/k3_*`。
- **🛑 拍板点(headline重心移)**：claim 从"系统性失效"精化为"规模/能力依赖的失效"——方向调整需用户定。
- **下一步(拍板后)**:①headline精化落STORY/ACCEPTANCE(K1判据已预埋此分支);②P3全套横评(D2-D15+大样本+bootstrap CI严格验规模依赖);③放量pilot。**P1(管线+质量)达标,K3揭示规模依赖失效**。

---

## 2026-07-11 · 收工（本 session：从文献综述到立项建档全链完成）

**本 session 完成**：
1. ACL 6 篇文献综述（`../ACL/文献综述_ACL2026_幻觉检测与忠实度验证.md`）→ 领域评估 → 三候选红队 → 选 A → 转医学域 → CMedFaith 立项。
2. 两发 kill-shot pilot（通用跨语言 G_lang≈0 证伪旧动机 / 医学 vs 通用 G_domain=0.293 命门 PASS）。
3. 标准 schema 建档全套 + registry/CLAUDE/claim/datasets 登记 + 指针自检零漂移。
4. 4 路深度调研（竞品delta/数据构造/评测venue/K0）+ K0 撞车终检 PASS。

**concurrent work 定调（用户）**：MedHallu-ZH 系同期成果，related work 一句带过不刻意对标，靠自己亮点立文。

**下一步（下次开工）**：派 planner 设计正式实验矩阵 P1-P3 → **P1 = 小规模中文医学 faithfulness 数据构造 pilot**（验 K3 中文迁移 + MedHallu 半自动构造范式跑不跑得通）。动笔前补两 TODO（MedHallu-ZH 是否真可下 / zh 有无 severity 分层）。

---

## 2026-07-11 · K0 撞车终检 PASS + 措辞红线收紧

researcher 逐段核 MedHallu-ZH 原文（SelfElicit, Findings ACL2025, 2025.findings-acl.211 §C.2）：
- **K0 PASS**：MedHallu-ZH = (query, response) 两元组**无外部证据字段**，判幻觉靠专家/世界知识（self-elicitation, reference-free），**确非 evidence-conditioned** → headline #1「首个中文医学 evidence-conditioned faithfulness benchmark」成立，不撞。
- 事实：zh 规模 2704 response / 18031 句；自然幻觉（非对抗）；已有 zh+en 平行集但未做迁移诊断；无公开 release 链接。
- **净剩亮点**：① evidence-conditioned+span grounding ✅核心 / ③ 对抗支 ✅独有 / ⑤ 独立公开资源 ✅；② 横评限"证据条件设定下" / ④ 改"跨语迁移诊断"。
- **收紧措辞红线 3 条**（写进 STORY）：横评限定 evidence-conditioned 设定、不 claim 首创难度分层、不 claim 首个中英平行集。
- **两 TODO**：MedHallu-ZH 是否真公开可下；zh 是否也有 severity 分层。
- 全文缓存 `<session>/tool-results/selfelicit.txt`。

---

## 2026-07-11 · 立项决策 + 两发 kill-shot pilot

**立项**：用户拍板，从 ACL 文献综述（6 篇全是 LLM 幻觉/RAG faithfulness 检测）衍生的方向探索收敛而来。

**方向收敛历程**（防跑偏留痕）：
1. 起点=整理 `project/meeting/ACL/papers/` 6 篇综述（MARCH/CiteGuard/SIRG/FAMA/FRANQ/ContextCheck，全是 faithfulness/幻觉检测）。
2. 领域评估：低算力、benchmark 友好、有空白。
3. 三候选红队：A 跨语言（原 headline "检测器跨语言崩" 被 EACL 论文 arXiv:2601.16766 + pilot#1 双证伪）/ B 元评测（撞车重）/ C 打 FaithBench（50% 上界过时）。
4. 用户约束："往临床/健康 NLP 靠"（升学）+ "自建两个 benchmark，做扎实" + "走 ARR 不赶死线"。
5. **一次跑偏自查纠正**：pilot#1 跑的是"检测器跨语言掉分"（旧动机），方向早转医学域；及时改对靶子跑 pilot#2。
6. 收敛 = **中文（+英文对照）医学 RAG faithfulness 检测 benchmark**。

**核心 RQ**：现成 faithfulness 检测器在中文医学 RAG 上系统性失效吗？→ 建首个中文医学 evidence-conditioned RAG faithfulness benchmark + 基线，揭示并量化医学域失效。

**双贡献**：① 资源（首个中文医学 faithfulness 数据）② 发现+基线（现成检测器医学域失效）。

**venue**：ARR → BioNLP/ClinicalNLP/CL4Health/EACL-EMNLP Findings（临床 NLP）。

**pilot 结果**（数字 Bash 核 csv，详见 `reference/KILLSHOT_LEDGER.md`）：
- #1 通用跨语言：G_lang=−0.004 CI[−0.089,0.086]→ 语言不是难点（旧动机证伪）。
- #2 医学 vs 通用：G_domain=+0.293 CI[0.184,0.391]→ **医学域显著更难，命门 PASS**。medical macro-F1 0.43<随机。

**诚实天花板**：pilot 是英文 MedHallu 粗筛；中文数据待自建；G_domain 混对抗构造 confound；单臂待补 judge。三条结转 02_ACCEPTANCE 的 K1-K3。

**建档动作**：建 00_README/01_STORY/02_ACCEPTANCE/DATA_INVENTORY/04_LOG + KILLSHOT_LEDGER；pilot 脚本在 `_scratch/`（killshot_psiloqa.py + killshot_med_vs_general.py）；登 registry + CLAUDE.md 入口 + claim + datasets.json。

**在跑**：3 路深度调研（竞品/delta 定位、数据构造范式+中文证据源、评测协议+venue 惯例），回来精修 STORY/ACCEPTANCE/DATA_INVENTORY。

**环境记账**：为跑 pilot 装了 `datasets 5.0.0`（副作用：pandas 升 3.0.3，与 idc-index/streamlit 有版本冲突警告，不影响 pilot；需要时可回退）。

**下一步**：待 3 路调研回 → 填 STORY（delta 精确定位）+ ACCEPTANCE（判据/kill criteria）+ DATA_INVENTORY（自建方案）→ 设计正式实验矩阵（补 judge 臂 + 对抗/自然分层 + 中文数据构造 pilot）。
