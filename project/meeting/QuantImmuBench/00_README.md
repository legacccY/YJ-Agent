# QuantImmuBench — 新抗原免疫原性「强弱定量」工具 Benchmark

> 入口读档顺序：本文 → `REPORT.md`（完整部署测试报告，PPT 素材）→ `DEPLOY_TRACKER.md`（5 工具部署状态总表）→ `TOOLS/<tool>.md`（逐工具信息）→ `04_LOG.md` 最新 entry

## 一句话
袁老师牵头的**癌症个性化新抗原疫苗**协作项目。总目标 = 做一个能预测 T 细胞免疫反应**「强弱定量程度」**的工具（比现有只判「有/无免疫原性」的二分类更进一步），路线 = 大量跑现有工具 + 数据集做 benchmark，再结合自研 QuantImmune 算法。

## 我（余嘉 / legacccy）的子任务
在 HPC 上**部署并测试 5 个现有预测工具**，每个工具测试运行后收集 4 类信息，最终以 **PPT** 形式记录：
1. 输入数据的模板 / 格式
2. 预测工具运行的参数设置（可调参数的类型及功能）
3. 输出数据的格式及含义
4. 工具的简要介绍（特点、优势）

**我负责的 5 个工具**：PredIG · DeepImmuno · pTuneos · IMPROVE · NeoTImmuML
（李紫晨负责另 5 个：PRIME / deepHLApan / ImmuneApp / MHLAPre / HLAthena —— 不在本档范围）

## 团队分工（背景，非我任务）
- **预测工具组**：李紫晨（5 工具）+ 余嘉（5 工具，本档）
- **QuantImmu 组**：徐伊琳 —— HPC 部署 QuantImmune 模块
- **数据收集组**：王子源、谢孟翰 —— 文献搜索 + 数据收集（袁老师提供输入数据）

## 当前状态
- **阶段**：部署 + example 烟测（袁老师输入数据未到 → 先用各工具自带 example 跑通）
- **硬阻塞**：
  1. **netMHCpan / PRIME 等学术许可未到位** → pTuneos + IMPROVE 硬依赖，需先申请（见 `DEPLOY_TRACKER.md` 许可清单），排在 Wave 2。
  2. **NeoTImmuML 官方源码 URL 未公开** → 需进 tumoragdb.com.cn 站内找（TODO）。
  3. **袁老师输入数据待给** → 到位后第二阶段做格式转换 + 正式测试。

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
├── TOOLS/                # 每工具一份 info 文档（= PPT 素材）
│   ├── _TEMPLATE.md
│   ├── PredIG.md / DeepImmuno.md / pTuneos.md / IMPROVE.md / NeoTImmuML.md
└── scripts/              # 部署 / 烟测 / 格式转换脚本
```

## 注
本项目现为**轻量工程台档**（benchmark 阶段），暂不建 `01_STORY` / `02_ACCEPTANCE`；若日后成论文再补论文 schema。
