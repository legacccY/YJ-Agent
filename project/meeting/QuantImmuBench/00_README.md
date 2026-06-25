# QuantImmuBench — 新抗原免疫原性「强弱定量」工具 Benchmark

> 入口读档顺序：本文 → `REPORT.md`（完整部署测试报告，PPT 素材）→ `DEPLOY_TRACKER.md`（5 工具部署状态总表）→ `TOOLS/<tool>.md`（逐工具信息）→ `04_LOG.md` 最新 entry
>
> 另见：`REFERENCES.md`（工具论文/DOI/repo 出处）· `PROVENANCE.md`（代码归属：哪些是我们写的 vs 外部工具 + 许可/再分发限制）· `HPC/`（从 HPC 拉回的部署脚本 + ELISpot 正式跑产物，`HPC/README.md` 说明哪些大件留 HPC）

## 一句话
袁老师牵头的**癌症个性化新抗原疫苗**协作项目。总目标 = 做一个能预测 T 细胞免疫反应**「强弱定量程度」**的工具（比现有只判「有/无免疫原性」的二分类更进一步），路线 = 大量跑现有工具 + 数据集做 benchmark，再结合自研 QuantImmune 算法。

## 我（余嘉 / legacccy）的子任务
在 HPC 上**部署并测试现有预测工具**，每个工具测试运行后收集 4 类信息，最终以 **PPT** 形式记录：
1. 输入数据的模板 / 格式
2. 预测工具运行的参数设置（可调参数的类型及功能）
3. 输出数据的格式及含义
4. 工具的简要介绍（特点、优势）

**余嘉的 5 工具（✅ 全部署 + 跑通 ELISpot benchmark + 4 类信息 + PPT，核心任务已完成）**：PredIG · DeepImmuno · pTuneos · IMPROVE · NeoTImmuML
**李紫晨的 5 工具（⚠️ 2026-06-24 袁老师分工明确=李紫晨负责，非余嘉核心任务）**：PRIME · deepHLApan · ImmuneApp · MHLAPre · HLAthena
- ⚠️ **分工纠正（2026-06-24 袁老师分组消息，见 04_LOG Entry 25）**：后 5 工具是李紫晨的活，余嘉此前做的 Wave3 部署+benchmark（3 工具 SMOKE_PASS+进 8tools 表）属**超额/可移交李紫晨参考**，不回退（已做的 benchmark 仍有效）。余嘉后续重心 = 前 5 工具 + 配合 QuantImmu 组（徐伊琳）/ 数据组（王子源、谢孟翰）。
- 可行性矩阵 + 部署排序 + 两红旗见 `DEPLOY_TRACKER.md` §第二批 Wave 3。要点：PRIME 最易（HPC 已半 clone）；**HLAthena 仅预测提呈非免疫原性→只能当 presentation proxy**；**MHLAPre 权重未发布需邮件作者（阻塞）**。

**📚 2026-06-24 大面积推动产出（13 路 opus 编队，全景调研+深析+红队+理论+路线，见 04_LOG Entry 25）**：
- `PROJECT_LANDSCAPE.md`（项目根）= 给袁老师的**一页纸决策综述**（现状+蓝海+命门+理论天花板+下一步），QuantImmune 立项拍板入口。
- `reference/`（新建调研档）：`LANDSCAPE_tools.md`（工具全景+撞车=蓝海）· `LANDSCAPE_datasets.md`（数据集全景+定量 GT 命门）· `BENCHMARK_METHODOLOGY.md`（学界方法学对标）· `REDTEAM_benchmark.md`（红队 🔴-1）· `VERIFY_numbers.md`（0 drift 核数）· `THEORY_quant.md`（可行性理论 ρ~0.4-0.6）· `REVIEW_deliverables.md`（十角色审稿）· `EXPERIMENT_MATRIX_quantimmune.md`（QuantImmune 实验路线）。
- `analysis/` 新增：`DEEPDIVE_8tools.md`（组合最优深析）· `DS1_magnitude.md`（DS1 证伪工具定量能力）· `bootstrap_ci.py`+csv（pTuneos「最优」统计不可区分铁证）· `metrics_topk.py`+csv（AUPRC+ISSR）· `patient_strat_check.py`+csv（患者聚集）· `iedb_overlap_check.py`（待跑，需下 IEDB csv）。

## 团队分工（背景，非我任务）
- **预测工具组**：李紫晨（5 工具）+ 余嘉（5 工具，本档）
- **QuantImmu 组**：徐伊琳 —— HPC 部署 QuantImmune 模块
- **数据收集组**：王子源、谢孟翰 —— 文献搜索 + 数据收集（袁老师提供输入数据）

## 当前状态（2026-06-25 更新，详见 04_LOG Entry HLA2；**进度真源 = `DEPLOY_TRACKER.md` 顶部规范状态总表**）
- **总账（10 工具）**：✅ **9 进 ELISpot benchmark** + ❌ **1 未做成（MHLAPre）**。
  - **9 进 benchmark** = 8 免疫原性工具 apples-to-apples（DeepImmuno · PredIG · pTuneos · IMPROVE · NeoTImmuML · PRIME · ImmuneApp · deepHLApan）+ HLAthena 1 个 presentation proxy 单列（近随机 AUC 0.51，印证提呈≠免疫原性）。
  - ⚠️ 版本 caveat：**NeoTImmuML = 自训版**（官方权重不可得→复刻官方 RF+LGB+XGB，PPT 标★非官方）；**pTuneos = Pre&RecNeo 子模型**；**IMPROVE = Expression 特征降级**。结论一律诚实分级，无"5/5 完美跑通"。
  - ❌ **MHLAPre 唯一未做成**：无权重 + ProcessData npy 缺 + 预处理拼装码被注释 → 自训路也不通，唯一出路邮件作者。
- **余嘉核心 5 工具（第一批）**：全部进 benchmark（DeepImmuno/PredIG 完整端到端；pTuneos 子模型；IMPROVE 降级；NeoTImmuML 自训版）。
- **Wave3 5 工具（归李紫晨，余嘉超额）**：PRIME/ImmuneApp/deepHLApan ✅ 进 benchmark；HLAthena ✅ proxy；MHLAPre ❌ 阻塞。
- PPT（17 slide）+ Word 报告成型。
- **许可/依赖均已解决**（不再是阻塞）：
  1. **netMHCpan-4.1 / 4.0 / 2.8 已装 + 跑通**（netMHCpan-4.0 随 pTuneos 镜像内置免单独申请）；**PRIME / MixMHCpred 学术免费，已 clone**。pTuneos example VCF 端到端 + Pre&RecNeo 跑 ELISpot 进 benchmark（对账官方 r=1.0）。
  2. **NeoTImmuML 官方源码已找到**（github.com/01SYan19/NeoTImmuML，Playwright 进 tumoragdb.com.cn 抓出）。
- **遗留（非阻塞 / 小缺口）**：
  - **netMHCstabpan-1.0** 仍 glibc 挡（HPC el8 仅 glibc 2.28，需 ≥2.29）→ 仅 IMPROVE feature_calc 的 Stability 特征用它，Predict 步与 benchmark 不受影响。
  - **pTuneos HPC 真跑** 受 singularity 非 root/fakeroot 限制（本地 WSL2 docker 已端到端验证）。
  - **袁老师输入数据待给** → 到位后第二阶段做格式转换 + 正式测试。
- ⚠️ 许可红线：netMHCpan/stabpan 学术许可禁再分发（含其跑出的数字），投稿前取 DTU 书面同意（见 `PROVENANCE.md` / `DEPLOY_TRACKER.md`）。

## HPC / 部署规范
- HPC：`dtn.hpc.xjtlu.edu.cn` / 用户 `jiayu2403` / 分区 `gpu4090`（详见 `project/HPC_WORKFLOW.md` + memory `project_hpc_xjtlu`）。
- 这些工具多为 **CPU 推理**（XGBoost / RandomForest / CNN inference），基本不占 GPU 卡槽；如某步要 GPU 才走 `tools/gpu_slot.py request`。
- **拍板点**：HPC 上传新代码 / 数据 / 许可证 = 对外传输，每次上传前一行报；本地 clone、写脚本、读 README、填 md 自主推进。
- 部署一个工具的标准 6 步见 `DEPLOY_TRACKER.md` 顶部。

## 文档结构
```
QuantImmuBench/
├── 00_README.md          # 本文：总目标 + 我的子任务 + 状态
├── 04_LOG.md             # 时间倒序日志
├── DEPLOY_TRACKER.md     # 5 工具部署状态总表 + 标准流程 + 许可清单
├── REFERENCES.md         # 工具论文/DOI/repo 出处 + 外部依赖 + 数据集
├── PROVENANCE.md         # 代码归属（我们写的 vs 外部）+ 许可/再分发限制
├── TOOLS/                # 每工具一份 info 文档（= PPT 素材）
│   ├── _TEMPLATE.md
│   ├── 第一批：PredIG.md / DeepImmuno.md / pTuneos.md / IMPROVE.md / NeoTImmuML.md
│   ├── 第二批：PRIME.md / deepHLApan.md / ImmuneApp.md / MHLAPre.md / HLAthena.md
├── HPC/                  # 从 HPC 拉回的部署脚本 + ELISpot 正式跑产物（HPC/README.md 说明）
├── analysis/            # benchmark 指标/出图（figures_R_v3 为终版）/报告
└── scripts/              # 部署 / 烟测 / 格式转换脚本（均我们写的，见 PROVENANCE）
```

## 注
本项目现为**轻量工程台档**（benchmark 阶段），暂不建 `01_STORY` / `02_ACCEPTANCE`；若日后成论文再补论文 schema。
