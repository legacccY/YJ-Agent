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

**第一批 5 工具（✅ 全部署 + 跑通 ELISpot benchmark）**：PredIG · DeepImmuno · pTuneos · IMPROVE · NeoTImmuML
**第二批 5 工具（原李紫晨负责，现并入；2026-06-24 调研建档完成，待部署）**：PRIME · deepHLApan · ImmuneApp · MHLAPre · HLAthena
- 可行性矩阵 + 部署排序 + 两红旗见 `DEPLOY_TRACKER.md` §第二批 Wave 3。要点：PRIME 最易（HPC 已半 clone）；**HLAthena 仅预测提呈非免疫原性→只能当 presentation proxy**；**MHLAPre 权重未发布需邮件作者（阻塞）**。

## 团队分工（背景，非我任务）
- **预测工具组**：李紫晨（5 工具）+ 余嘉（5 工具，本档）
- **QuantImmu 组**：徐伊琳 —— HPC 部署 QuantImmune 模块
- **数据收集组**：王子源、谢孟翰 —— 文献搜索 + 数据收集（袁老师提供输入数据）

## 当前状态（2026-06-24 更新，详见 04_LOG Entry 19/20）
- **阶段**：✅ **5 工具全部部署 + 跑通 ELISpot benchmark**（用各工具自带 example + ELISpot 数据集）；PPT + Word 报告成型。
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
