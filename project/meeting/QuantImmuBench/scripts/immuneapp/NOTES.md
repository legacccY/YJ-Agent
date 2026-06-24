# ImmuneApp HPC 部署说明

> 服务：quantimmu-bench / ImmuneApp-Neo 免疫原性预测模块

---

## 部署步骤清单

按顺序执行：

```bash
# 1. 部署（clone repo + 建 conda env + 装依赖）
bash /gpfs/work/bio/jiayu2403/quantimmu/scripts/immuneapp/deploy_immuneapp.sh

# 2. 烟测（repo 自带 testdata 跑一遍）
bash /gpfs/work/bio/jiayu2403/quantimmu/scripts/immuneapp/smoke_immuneapp.sh
```

产出路径：
- repo：`/gpfs/work/bio/jiayu2403/quantimmu/tools_repos/ImmuneApp/`
- conda env：`/gpfs/work/bio/jiayu2403/quantimmu/envs/immuneapp/`
- 烟测结果：`/gpfs/work/bio/jiayu2403/quantimmu/elispot_run/immuneapp_out/ImmuneApp_Immunogenicity_predictions.tsv`
- stdout log：`/gpfs/work/bio/jiayu2403/quantimmu/logs/immuneapp_smoke_stdout.log`

---

## 风险与已知坑

### 1. Python 3.7 必须严格（高风险）

TF 1.15 官方 PyPI wheel 只发布了 Python 3.6 / 3.7 的 Linux 版本，3.8+ 没有官方 wheel。conda create 时必须显式指定 `python=3.7`，不能用系统默认的 3.8/3.9/3.10/3.11。

如果 HPC 默认 conda 环境是 3.x ≥ 3.8，`pip install tensorflow==1.15` 会报"找不到兼容版本"错误，需从源码编译——避免走这条路，坚持 3.7。

### 2. TF 1.15 是 CPU-only（不影响功能）

ImmuneApp 推理量小，CPU 跑即可，不需要申请 GPU 节点。`tensorflow==1.15` PyPI 包是 CPU only wheel，如果想要 GPU 需装 `tensorflow-gpu==1.15`（但 HPC CUDA 版本可能不匹配 TF1 的要求，建议不折腾，用 CPU）。

### 3. h5py 必须 2.10.0（高风险）

TF 1.15 保存的模型权重（`.h5` 文件）用 h5py 2.x API（`f['layer_name']` 直接当 dict 用）。h5py 3.x 改了 API（`f['layer_name'][()]` 才能读数据），导致加载权重时报 `AttributeError` 或 `TypeError`。

必须钉死 `h5py==2.10.0`，不能用 3.x。

### 4. protobuf 必须 3.20（高风险）

TF 1.15 的 `.proto` 生成代码调用 `descriptor_pool.Add()`，该接口在 protobuf 4.x 被删除。安装后报 `AttributeError: module 'google.protobuf.descriptor_pool' has no attribute 'Add'`。

必须钉死 `protobuf==3.20`，不能用 4.x（conda 默认可能装 4.x）。

### 5. Keras 2.3.1 standalone（中风险）

ImmuneApp 代码 `import keras`（standalone），不是 `from tensorflow import keras`（tf.keras）。TF 1.15 内置的 tf.keras 与 standalone Keras 2.3.1 在 `Model.load_weights()` 行为有细微差异，必须用 standalone `Keras==2.3.1`。

如果 import 时看到 `Using TensorFlow backend` 提示，说明 Keras 正确接入 TF 后端。

### 6. numpy 版本（中风险）

numpy 1.20 是 repo README 锁定版本。TF 1.15 依赖 `np.bool`、`np.int`、`np.float` 等已弃用别名（Python type aliases），这些在 numpy 1.20 仍作为 deprecated 警告存在，1.21 升为警告，1.24 彻底删除。不要升到 1.24+。

### 7. ImmuneApp_weights/ 随 repo（无需额外下载）

预训练权重文件已包含在 git repo 中，clone 完整即可直接用，无需从 web server 另行下载。但 repo 较大（含权重 h5 文件），clone 时间可能较长（视 HPC 出口带宽）。

### 8. 运行时必须 cd 到 REPO_DIR（中风险）

`ImmuneApp_immunogenicity_prediction.py` 使用相对路径加载权重（`ImmuneApp_weights/`），必须先 `cd` 到 repo 根目录再执行，否则报 `FileNotFoundError`。smoke 脚本已处理此项。

### 9. -o 参数语义待核（低风险，smoke 验证）

调研卡中 `-o results` 是目录名，但实际输出文件名是固定的 `ImmuneApp_Immunogenicity_predictions.tsv`。smoke 脚本的 QC 步骤会列出 OUTPUT_DIR 所有文件帮助调试，如果文件位置不对请查 stdout log。

---

## 实测后回填 TOOLS/ImmuneApp.md 的项

烟测跑通后，将以下信息填入 `TOOLS/ImmuneApp.md` 对应 TODO：

1. **实测输入样例** — 从 `testdata/test_immunogenicity.txt` 取前 3 行（纯肽段，每行一条，无 header）
2. **实测命令行** — smoke 脚本 Step 3 中的完整命令（含绝对路径版本）
3. **实测输出样例** — 从输出 tsv 取前 3 行（Allele / Peptide / Sample / Immunogenicity_score）
4. **Immunogenicity_score 值域** — smoke QC 打印的 `[min, max]`（验证 sigmoid 0~1 约束）
5. **多 HLA allele 是否 per-allele** — 查 Allele 列行数分布（smoke QC 已打印，每肽每 allele 各一行 = per-allele 格式）
6. **部署状态** → 从"待部署"改为"已部署，smoke PASS"，记录 job_id 或时间戳
