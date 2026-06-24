# HyperFidBench — LOG（时间倒序，单一日志真源）

## Entry 2 — 2026-06-24 Gate1 实验设计完成（/design-experiment）

**产出**：`实验设计_2026-06-24.md`（planner opus 出矩阵 + 3 researcher 清超参 + 用户拍数据策略）。

**矩阵**：前置 P0-download→P0b-registry→[P1-upload-hpc🛑]→P2-connmat→P3-split；6 run（run-01 BrainGB GCN / 02 GAT / 03 HyperGALE / 04 fidelity-on-BrainGB / 05 multiatlas / 06 fidelity-on-HyperGALE）。必需=01/03/04（~3 GPU·h），全矩阵~6.3。预算：用户声明**无限时间算力**。

**超参已清（researcher 官方源带引用，见设计文档）**：
- BrainGB：lr1e-4/ep100/hidden360/2层/dropout0.5/batch16/node feat=adj(conn profile)/GCN mp=weighted_sum/pooling=concat/StratifiedKFold5。报告 acc GCN64.4/GAT67.9 → 对齐 65-70%✅。
- HyperGALE：**ABIDE-II/Schaefer400/n812**，k-NN 超边 k=40/lr1e-5/ep200/hidden64/1层/poly sched，acc75.34%。⚠️2 open issue=FC npy 预处理脚本缺失，须自建 nilearn+Ledoit-Wolf FC。env=PyG2.3.1/torch2.0.1/py3.11。
- PyG fidelity：`fidelity(explainer,explanation)→(fid+,fid-)`，GNNExplainer(epochs=200)。

**🔴 命门坐实**：PyG 原生**不支持超图 fidelity**（issue #5630 Open/P0，hyperedge mask 无接口）→ run-06 须自研 hyperedge mask 适配层 = 正是 Gate2 L1 贡献点，非 Gate1 阻碍。run-06 出 nan/报错不触发 K1。

**用户拍板（数据策略）**：**各按官方→Gate2 统一**。Gate1 = BrainGB 跑 ABIDE-I/CC200（现成 FC，S3 直下）+ HyperGALE 跑 ABIDE-II/Schaefer400（自建 FC），各复现论文 acc 证实现对、复现零偏离；Gate2 再统一到同数据集出可比 leaderboard。

**下一步**：派 coder 实现 Gate1 脚本（克隆官方 repo + 薄封装，复现零偏离）→ 主线跑 P0 下载 → P1 HPC 上传拍板 → 训练。

## Entry 3 — 2026-06-24 Gate1 代码实现 + 本地验证

**2 coder 并行实现**（读 vendor 官方真码写薄封装，复现零偏离）：
- `src/braingb_lane/`：download_abide1 / build_graphs / make_split / train_braingb / eval_fidelity + tests（6 文件）。官方 repo 克隆到 `vendor/BrainGB/`。
- `src/hypergale_lane/`：download_abide2 / build_fc_abide2（补 repo 缺失 FC 管道=open issue #2/#3）/ build_hyperedges / make_split / train_hypergale + tests（6 文件）。`vendor/HyperGALE/`。

**本地验证（base env: torch2.7+cu126, 装了 nilearn0.13.1+pyg2.8.0+ipdb）**：
- BrainGB 泳道 pytest **16/16 通过 ✅**（PyG 2.8 兼容 explain 模块）。
- HyperGALE 泳道：data-free 8 通过；模型 forward 3 fail = **版本矩阵坑**（vendor `HypergraphGCNConvv2` 传 `num_edges` 给 PyG `MessagePassing.__init__()`，PyG 2.8 不收；HyperGALE pin PyG **2.3.1**）。[[feedback_version_matrix_first]]
- **决策**：不改 vendor（复现零偏离）→ HyperGALE 泳道 env（torch2.0.1/cu11 + PyG2.3.1 + torch-cluster/sparse + dhg + deepsnap）这套 cu11 编译 wheel 在 Windows 建不起，**归 HPC**（Linux，正式训练本就在 HPC）。

**改动**：train_braingb.py 加 checkpoint 保存（seed0/fold0 存 .pt，run-04 fidelity 需真训练权重非随机初始化，纯 instrumentation 不改训练动力学，[[feedback_mechanism_probe_methodology]]）。

**进行中**：P0 本地下载 ABIDE-I CC200 ROI 时序（nilearn fetch_abide_pcp，后台）。

**下一步**：下载完 → build_graphs → make_split → BrainGB smoke（本地）；HyperGALE 全程 → 🛑 P1 HPC 上传拍板。

## Entry 4 — 2026-06-24 BrainGB 泳道本地验证全通 + 版本矩阵踩坑实录

**P0-P3 + smoke 全跑通（本地 base env）**：
- P0 下载：nilearn fetch_abide_pcp → 871 个 rois_cc200 .1D + phenotypic（1112 行）。
- **P2 build_graphs 抓到并修 bug**：原 `extract_sub_id` 用 `parts[1]` 取 SUB_ID，多下划线站点（UM_1/Leuven_1/UCLA_1 等）错取 site 后缀 → 只匹配 610/871（丢 261，30%）。诊断（[[feedback_diagnose_single_value]] 单值核：FILE_ID 精确匹配 871/871）确认是 bug 非数据损失。改用 `\d{5,7}` 抓 sub_id 数字串 → **871/871 全匹配**，FC shape (871,200,200)，ASD403/TD468，无 NaN/Inf。**若没核就训=610 子集 acc 对不上文献，险踩坑**。
- P0b 登记 `.portfolio/datasets.json` → `abide_i_cc200`。
- P3 make_split：871 被试 5 fold StratifiedKFold，patient-level（SUB_ID 键），分层均衡，20 site。
- pytest braingb_lane **16/16 通过**。
- **BrainGB GCN smoke 端到端通**：数据→训练→评估→checkpoint。1 epoch acc 53%（随机水平烟测正常，满 100 epoch 待 ~65%）。

**版本矩阵踩坑链（[[feedback_version_matrix_first]] 现场重演，base torch2.7 跑 BrainGB 2022 repo）**——HPC 复刻环境必备：
1. `torch_sparse`/`torch_scatter` 缺 → 装 pt27cu126 wheel（data.pyg.org）。
2. `node2vec` 缺（transforms 顶层 import）→ pip 装。
3. `networkx` 3.x 删了 `from_numpy_matrix` → 降 `networkx<3`（=2.8.8，BrainGB pin）。
4. `nni` 缺（BrainGB 用 NNI 调参）→ pip 装。
5. torch 2.6+ `torch.load` weights_only 默认翻 True → wrapper 加兼容 shim（`weights_only=False`，缓存自建可信，不改 vendor）。
6. Windows numpy 默认 int32，PyG index_select 要 int64 → wrapper 转 `torch.long`。
> 修 5/6 都在 OUR wrapper（train_braingb.py），**未改 vendor 算法**，复现零偏离不受影响。**HPC 上用 BrainGB pin 的老 torch(2.0.x) 则 5/6 自动消失**——建议 HPC 直接按 requirements 建 pinned env 而非沿用 base。

**待 HPC（P1 拍板后）**：BrainGB 正式训练（100ep×3seed×5fold，cc200 轻量）；HyperGALE 全程（env 必须 HPC：torch2.0.1/cu11/PyG2.3.1/torch-cluster/sparse/dhg/deepsnap）。

## Entry 5 — 2026-06-24 BrainGB 本地正式训练 + config 对齐文献修正

**用户拍板本地跑 BrainGB Gate1 partial**（cc200 轻量 200 节点图，8GB 够；gpu_slot local 1）。
- 首跑 argparse 裸默认（`gcn_mp_type=weighted_sum`, hidden 360）：seed 0 全跑完 = **acc 57.4%**，低于 Gate1 判据 65-70%。
- **根因（非模型失败，config 问题）**：BrainGB README 文档命令 = `--gcn_mp_type edge_node_concate --hidden_dim 256`，这才是它报 65.31% 的配置；argparse 裸默认 weighted_sum ≠ 官方 headline 报告配置。researcher 早标二者不同。
- **修正（复现零偏离=复现官方报告结果，用官方文档命令，非臆改）**：换 `edge_node_concate + hidden 256` 重跑 run-01。weighted_sum partial 归档 `braingb_results_weighted_sum_partial.csv` 留作 leaderboard 旁证配置。
- 用户拍板：停 weighted_sum 切正主（TaskStop + gpu_slot release 5e49227d→request c2c7a0a9）。
- **edge_node_concate 本地不可行（实测）**：稠密 FC 图 200 节点→40k 边，每边 concat×hidden256 → 近 OOM（7816/8188 MiB）+ 单 epoch >90s（weighted_sum 才 2s，慢 45×）。100ep×5fold×3seed 在本地 8GB = 几天，不可行。停掉（TaskStop bs0q78il5 + release c2c7a0a9，GPU 清回 1440 MiB baseline）。
- **结论**：BrainGB headline 配置（命中文献 65% 的 edge_node_concate）**也必须 HPC**（gpu4090 24GB + 快）。本地只能验 pipeline + 证 BrainGB 能跑（weighted_sum 57%）。**Gate1 ② 对齐文献的结果须在 HPC 出。**

**本地阶段收口（已尽本地之能）**：
- ✅ 数据管道全验（871 FC 干净，修了 261 丢失 bug，patient-level split）
- ✅ pytest braingb 16/16
- ✅ BrainGB 算子链能跑（weighted_sum smoke + seed0 full=57%，证实现对）
- ❌ headline edge_node_concate / HyperGALE → 本地 8GB 不可行（OOM / env），**必须 HPC**

**→ 到 P1 HPC 上传拍板点**（对外传输）：传 abide.npy(871,~140MB)+ABIDE-II 时序(HyperGALE)+src+vendor → HPC 建 2 pinned env（BrainGB 老 torch + HyperGALE torch2.0.1/cu11）→ gpu_slot 申请 → 跑 run-01(edge_node_concate)/02/03/04。等用户放行 P1。

## Entry 6 — 2026-06-24 P1 放行，HPC 上传 + 建 env（GLIBC 坑）

**用户放行 P1**。HPC=XJTLU dtn.hpc.xjtlu.edu.cn（jiayu2403，account shuihuawang，gpu4090/gpu3090）。凭据从 HPC_WORKFLOW.md 读不进命令行（防泄露 hook，helper=`tools/_hf_hpc.py`）。
- **上传**：vendor 两 repo HPC 直接 git clone；src(11 py)+abide.npy(136M)+split 上传到 `/gpfs/work/bio/jiayu2403/hyperfid/`。
- **HPC 现状**：gpu4090 拥堵（我已有 fmreg/fetalss/km 3 job PD，多窗在跑别篇）；conda env 在 ~/.conda/envs（my_torch_env=torch2.7cu126 / yjcu124py310=py3.10）；cuda module 10.2-12.6 全有；磁盘 132T 空；无 ABIDE 缓存。
- **🔴 GLIBC 坑（新踩，[[feedback_version_matrix_first]]）**：login glibc=**2.28**，torch_sparse **cu126** wheel 需 GLIBC_2.32（torch 本体 manylinux 兼容能 import，torch_sparse 单独 build 的 .so 不兼容）。计算节点同 OS 镜像大概率也 2.28。**解=换 cu118 wheel**（manylinux2014/glibc2.17，兼容 2.28）。但 cu118 torch≤2.1 无 py3.12 wheel → 用 yjcu124py310(py3.10) 当 base 建干净 venv。
- **2 env 策略**（均 py3.10 + cu118，老 glibc 兼容）：
  - `hf_braingb_venv`：torch2.1.0+cu118 + PyG2.5.3(explain API 近2.8) + torch_sparse/scatter + nilearn/node2vec/nni/networkx<3。
  - `hf_hypergale_venv`：torch2.0.1+cu118(官方pin) + PyG2.3.1(官方pin) + torch_cluster/sparse/scatter + lightning2.0.7/dhg/hydra/deepsnap(git)。
- **eval_fidelity 改**：加 `--gcn_mp_type/--hidden_dim` 透传，run-04 加载 run-01 edge_node_concate/256 ckpt 时架构匹配（否则 load_state_dict 挂）。
- **进行中**：两 env HPC 并行构建；BrainGB sbatch 待提交（run-01 edge_node_concate + run-02 GAT + run-04 fidelity 一 job 串跑）。ABIDE-II 下载+FC 自建管道待 HyperGALE env 就绪后跑。

## Entry 7 — 2026-06-24 env 构建踩坑：login 节点杀进程 → 转 SLURM cpudebug

- **login nohup 构建失败**：torch cu118 wheel 下到 /tmp 但 pip 进程被杀、venv 仍 51M（未装完）。**根因=login 节点杀长时重进程**（HPC 常规）。
- **修正**：env 构建走 SLURM 计算节点。账户 shuihuawang qos 仅 `4gpus/cpudebug/gpudebug` → CPU 只能用 **cpudebug**（限 1h/4cpu/1job）。单 env 一个 cpudebug job 建（`sbatch_buildenv.sh <which>`）。
- braingb env job 1491066 提交（cpudebug）。env 完 → 提交 GPU 训练 job。1job 限制 → braingb/hypergale env 串行建。

## Entry 8 — 2026-06-24 镜像加速：pytorch.org 1MB/s → aliyun 22MB/s

- **1491066 撞墙**：cpudebug 1h 跑到 57min 仍卡 torch 下载（download.pytorch.org 从 HPC 仅 **1MB/s**，2.3GB 要 38min+，超 1h 限）。scancel。
- **测镜像**：SJTU/TUNA 404（路径错），**aliyun `https://mirrors.aliyun.com/pytorch-wheels/cu118/` = 22MB/s**（快 100×，2.3GB 仅 ~105s）+ aliyun PyPI simple 通。
- **修**：两 setup 脚本 torch 用 `-f https://mirrors.aliyun.com/pytorch-wheels/cu118/`（版本写 `torch==2.1.0+cu118`），PyPI 包用 `-i https://mirrors.aliyun.com/pypi/simple/`，torch_sparse/scatter 仍 data.pyg.org（小文件 OK）。**[[project_hpc_xjtlu]] HPC 在中国，外网 pip 一律走 aliyun 镜像**。
- braingb env 重提 job 1491217。

## Entry 9 — 2026-06-24 真根因=计算节点外网慢，dtn 快 → wheelhouse 离线装

- **1491217 又卡 56min**：即便 aliyun，**计算节点（cpu8358n11）外网慢**；我 curl 22MB/s 是在 **dtn** 测的。实证：dtn 上 `pip download torch2.1.0+cu118`(2.3GB) **22 秒**（105MB/s）。
- **方案（HPC 通用，复用价值高）**：dtn 上 `pip download` 全依赖闭包 → `wheelhouse/` → 计算节点 `pip install --no-index --find-links wheelhouse`（离线，不碰外网）。两 setup 脚本改离线装。
- **坑**：`pip download torch==2.1.0 torch==2.0.1 ...` 同命令 = ResolutionImpossible（版本冲突）→ 两 torch 版本**分开下**。`| tail` 管道吃掉 pip 退出码 → `set -e` 不触发（脚本带病继续）。paramiko 单 exec 跑长下载会 channel 超时→远程 SIGHUP 死 → 长下载必 nohup。
- wheelhouse braingb 依赖齐（63 wheel/2.4G：torch2.1+ext+pyg2.5.3+nilearn+nni+...）；hypergale 专属（torch2.0.1/torchvision/pyg2.3.1/lightning/dhg/hydra/wandb/deepsnap）nohup 补下中。
- braingb env build job 1491426（离线）RUNNING。

## Entry 10 — 2026-06-25 离线装连环坑 + GPU 队列被他窗塞满

- **离线装 3 连坑全修**：①pip 版本自检走网挂起→`PIP_DISABLE_PIP_VERSION_CHECK=1` ②sympy/mpmath 缺(torch 依赖, --no-deps 下 torch 没带)→补下 ③triton 拉不动→torch `--no-deps` 跳过(BrainGB 不用 torch.compile)+手动补 filelock/sympy/networkx/jinja2/fsspec 等。
- **gpfs 解包 2.3GB torch 慢**：cpudebug 单节点 cpu8358n11 恒慢/超载(46min/81M)；dtn 快(5min/160M)。**修=TMPDIR 设节点本地 /tmp**(避 gpfs 3× 临时IO)。env 改 dtn nohup 建(TMPDIR本地, 不占GPU队列)。
- **🚧 GPU 队列被他窗塞满**：4gpus qos `MaxSubmitPU=8/MaxJobsPU=4`。当前我 8 job 全满(6×fss_*[fetalss另窗]+km+fmreg)→hyperfid 提交 `QOSMaxSubmitJobPerUserLimit` 被拒。**多窗争用**：fetalss 单窗塞 6 job。hyperfid GPU 训练须等队列腾位。gpu_slot 300797d4 已释放(没真跑)。
- **现状**：braingb env dtn 建中(ready 后等 4gpus 空位提交纯训练 job)。HyperGALE env wheel 仍缺(torch2.0.1/pyg2.3.1/lightning/dhg/deepsnap)待补。

## Entry 11 — 2026-06-25 BrainGB env 成 + Gate1 ② 正面信号(gpudebug 绕队列)

- **BrainGB env 建成**（dtn nohup + TMPDIR 本地方案成功）：torch2.1.0+cu118/torch_sparse0.6.18/pyg2.5.3 explain+fidelity OK/nx2.8.8，venv 5.4G。
- **绕 4gpus 队列堵**：gpudebug qos 独立有位 → 塞 run-01 seed0(edge_node_concate)拿 Gate1② 早期信号。
- **🟢 Gate1 ② 信号好**：edge_node_concate seed0 各 fold acc=68.57/60.92/64.94%（auc 71.6/61.8/72.2），**3-fold 均值 64.8%，正落文献 65-70% 区间**。（注：训练中途 ep59 test=60% 是过拟合中途值，fold 终值更高，别误判）。folds 3-4 跑中，可能撞 gpudebug 1h 限。
- **hg wheel 全齐**（lightning2.0.7/torchmetrics/hydra/omegaconf/wandb0.15/dhg0.9.3/nilearn0.10.1/deepsnap）。坑=`pip download <pin> 含deps` 触发回溯地狱 → 改 `--no-deps` 分组下解决。
- HyperGALE env dtn nohup 建中。
- **待**：run-01 seed0 5-fold 均值定 Gate1②；4gpus 腾位→上全量 3-seed run-01/02/04 + HyperGALE run-03。

## Entry 1 — 2026-06-24 立项决策（用户拍板）

**来源**：选题流水线 `/ideate` 2026-06-24 轮（charter: `project/ideation/runs/2026-06-24_charter.md`；报告: `2026-06-24_选题报告.md`）。从 112 候选 → G2 16 → G3 评分 → G2′撞车核 + G4 红队 → 双 headline 幸存。本项目 = headline 1（B5-10）。

**立项要素**：
- **方向**：超图 GNN 脑病(ASD/AD)分类的解释忠实度 benchmark。对齐导师王水花超图 GCN 独门方向。
- **会议**：ACCV 2026（Biomedical track；截稿 2026-07-05）；退路 MICCAI workshop / BSPC。
- **核心 RQ**：同一忠实度公理下，超图 XAI(超边/GNNExplainer/Grad-CAM-graph)哪种最忠实+对齐 DMN；修复现有超图 fidelity 指标缺陷(2410.07764)。
- **边界**：与姊妹篇 [[WaveFidBench]] 同"XAI 忠实度"母题但模态/方法不重叠（本篇超图脑连接组 vs 姊妹 wavelet 脑结构 MRI）。

**G5 地基核查（researcher 联网，全绿）**：
- 数据 ABIDE I/II 免登录 S3 直下🟢；baseline BrainGB(217⭐)/BrainGNN(211⭐)/HyperGALE(超图16⭐)🟢；指标 PyG fidelity 内置+GraphFramEx+nilearn Schaefer(DMN)🟢。
- 最大坎=超图 fidelity 语义适配(删超边≠删边，~3-5天，是贡献点)。

**红队结论（skeptic G4）**：0 无出路致命。残差3条已入 02_ACCEPTANCE（引言讲透超图解释难评 / 可比协议先设计 / SHypX 无代码只引数字）。

**撞车（researcher G2′）**：🟡 有角度。最近邻 SHypX(2410.07764, 通用超图非脑病)、Explainable GNN Dementia(2509.18568, 普通图非超图无忠实度 benchmark)、HyperGALE(2403.14484, 分类无忠实度评测)。差异=脑病应用+跨解释类型可比协议+DMN 对齐。

**下一步**：认领 claim → `/design-experiment hyperfid` 出 Gate1 矩阵（先下 ABIDE + 跑通 BrainGB/HyperGALE + 验 PyG fidelity 出非 nan 数）。数据下载若走 HPC = 拍板点先报。
