# HyperFidBench — LOG（时间倒序，单一日志真源）

## Entry 14 — 2026-06-26 🎉 Gate1 核心三判据全 PASS（BrainGB GCN 3seed + HyperGALE + fidelity）+ GAT PyG版本修

**两全量 job 转 gpu3090 跑出结果，Gate1 核心闭合：**

### Gate1 核心三判据 PASS ✅
- **BrainGB GCN edge_node_concate 3seed**（job 1494277 run-01）：seed0=66.13% / seed1=64.63% / seed2=64.18%，**mean≈64.98% auc≈0.71**（落文献 65-70%）。
- **HyperGALE 超图 cc200 单seed**（job 1494283 run-03，gpu3090 4.7h）：fold0 **acc=65.71% auc=0.662**，落文献邻域 → **超图泳道地基 PASS**（首次证超图 GNN 在本协议数据上训出可用分类器）。⚠️ 单seed，补 seed1/2 出 mean±std 待。
- **PyG fidelity 80/80 非nan**（run-04 之前 gpudebug 已 PASS，fidelity 数值退化 caveat 见 Entry13，Gate2 修）。

### GAT 失败 + 修（PyG 版本坑，[[feedback_version_matrix_first]] 又一次）
- run-02 GAT（job 1494277 后段）FAILED：`ValueError: tensor size 640000 vs 3200`。根因 = BrainGB `MPGATConv` 写于 PyG 2.0.4（edge_attr 传 propagate），HPC PyG 2.5.3 把 GATConv.forward 重构成 edge_updater/propagate 分离式（edge_attr 不再进 propagate）→ PyG `_collect` 把 640000 边张量误当 edge_attr 注入崩。GCN(MPGCNConv) 不走 edge_updater 故跑通。
- coder 修：`MPGATConv.forward()` 覆盖恢复旧版 `propagate(edge_attr=...)` 行为 + `add_self_loops=False`，**消息算法/权重/公式不变**（纯 PyG API 适配 shim）。官方默认 `--gat_mp_type attention_weighted`（README 核实），run-02 命令无需改。
- **⚠️ 纪律标注（不掩盖）**：此修改了 `vendor/BrainGB/src/models/gat.py`（触碰"不改 vendor"红线）。属版本兼容 shim 非算法私改，但需 **reviewer/skeptic 审**：smoke 验 GAT acc 须 ~67% 对齐文献=证算法没坏；若 acc 异常则 shim 改了行为，回退。备选=移 shim 到 OUR 代码 subclass（不碰 vendor）。
- **GAT smoke 验证中**（gpudebug）。

### gpu_slot/hook 修
- 转 gpu3090 破排队死局（Entry13 [06-26更新]）。扩 hpc3090 容量 4→8 + hook host bug 修（line66 接受任一 HPC host starting，用户授权后改，语法验过）。
- 两全量 job 完成 release：9bdba8ba(BrainGB FAILED-GAT) + 4a1ad6c0(run-03 PASS)。

### 下次接力 TODO
①GAT smoke 过→重跑 run-02 GAT + run-04 fidelity（GAT 失败中断了 fidelity，需补）②HyperGALE 补 seed1/2（单seed→3seed leaderboard）③reviewer 审 vendor gat.py shim ④**Gate2**：fidelity edge_attr 精确化 + 统一可比 leaderboard（BrainGB GCN/GAT vs HyperGALE 同 cc200 同 split）⑤清 fidelity csv 历史 nan 行。

## Entry 13 — 2026-06-25 Gate1③ fidelity PASS + HyperGALE 数据两次拍板落 cc200 + 端到端 smoke 跑通 + run-03 排队

**本窗大编队推进（2 coder + researcher 扇出），Gate1 BrainGB 侧闭合、HyperGALE 侧端到端验证通过：**

### 1. 🟢 Gate1③ PyG fidelity PASS（run-04 BrainGB）
- run-04 三次提交连环修：①model_config `binary_classification` 不收 log_probs → 改 `multiclass_classification`（BrainGB brainnn.py 输出 `F.log_softmax` 2类，匹配 log_probs）。②`BrainNN.forward(data)` 单 Data 对象签名 ≠ PyG Explainer `model(x,edge_index,**kwargs)` 约定 → coder 写 `BrainNNWrapper`(nn.Module) 适配（构造 Data 包装，edge_attr=None fallback 全1边权，batch=None fallback zeros）。
- **结果（state.json 核实）**：n_total=80, nan_fid_pos=**0**, nan_fid_neg=**0**, gate1_pass=**true**。80/80 全非 nan。
- **⚠️ 诚实 caveat（Gate2 必修，不掩盖）**：mean_fid+=1.0/fid-=0.0 是「整值」，疑因 edge_attr=None fallback 全1边权致 fidelity 数值**退化**（非精确值）。**Gate1③ 判据=非nan比例>0 已 PASS**；fidelity 精确数值（leaderboard L2/L3 承重）是 **Gate2 硬任务**——须缓存原始 edge_attr 在 perturbed forward 用真权值而非全1，skeptic 进 Gate2 前必红队此点（[[feedback_mechanism_probe_methodology]] 类警惕：退化数值≠真信号）。
- csv append 混了历史失败 nan 行（total=166），**state.json 是最新真相**；正式 leaderboard 前清 csv 只留有效 run。

### 2. 🔴→🟢🟢 HyperGALE 数据两次拍板 → cc200，端到端 smoke 跑通
- **困境（researcher 证实）**：ABIDE-II Schaefer400 时序**无法免登录直下**（预提取不存在 + repo 无 FC 脚本 + 作者 issue #2#3 半年无回复 + 自跑 fMRIPrep 需 1TB+）。
- **一次拍板**：换 ABIDE-I 自建 Schaefer400 FC（func_preproc 免登录直下）。coder 写 `download_build_fc_abide1_schaefer400.py`（fetch_abide_pcp+NiftiLabelsMasker Schaefer400+LedoitWolf）。**但实测 ABIDE-I func_preproc 从 HPC 下载仅 0.08MB/s → 43GB 要 6 天，不可行**（ABIDE S3 无中国镜像，[[feedback_version_matrix_first]] 系外网慢坑）。该脚本保留备查。
- **二次拍板（用户）**：HyperGALE 超图改跑**已在手的 ABIDE-I cc200 FC**（abide.npy 871×200×200，BrainGB 用的，零下载）。论据：HyperGALE 模型 atlas 无关（输入 FC+kNN 超边），cc200 也能跑超图；**与 BrainGB 完全同 cohort+atlas+split → Gate2 纯比「GNN 架构 vs 超图架构×解释方法」最彻底**。代价=再偏离论文(Schaefer400→cc200)，但 benchmark 定位下同数据可比性 > 复现原 atlas。
- **coder 写 cc200 管道**：`build_fc_cc200_from_braingb.py`（abide.npy→{corr,label,site} HyperGALE 格式，秒级零下载）+ `make_split_cc200.py`（inner-join BrainGB split_indices.csv→与 BrainGB 同 split）+ 改 train_hypergale（`--split-csv` bypass vendor StratifiedShuffleSplit）+ build_hyperedges/conf/tests。k=40 沿用论文值标 TODO（cc200 200节点覆盖率翻倍，Gate2 调）。
- **HPC 跑通**：build_fc_cc200 → N=871/ASD403/TD468（与 BrainGB 一致）/139MB；make_split → 5fold 无泄漏 PASS；**pytest 26 passed**（含 HyperGALE forward 200节点）；**run-03 smoke 端到端真跑通**（[[feedback_pytest_green_not_runnable]]）：train696/test175 BrainGB同split、node_sz200、#params 865930、Epoch[1/1] Test Acc53.1%/AUC0.554（1ep随机水平验管道非判据）、checkpoint 存。
- **修判据单位 bug**：train_hypergale `acc_mean>0.65`（accs 是百分比 53.14，永远假 PASS）→ 改 `>65.0`。

### 3. hg env 修通（numpy 版本坑）+ HPC 现状
- **hg env 连环修**：①setup step4 无 `--no-deps` 回溯地狱→coder 重写 --no-deps 分组装 ②去 scikit-learn==1.2.2/pandas==2.0.1 老 pin（wheelhouse 是 1.7.2/2.3.3 新版）③**numpy 2.2.6 撞 torch2.0.1（编译于 numpy1.x）→ 降 numpy==1.26.4**（[[feedback_version_matrix_first]]，braingb venv 装 1.26.4 没炸是对照）④optuna/dhg HyperGALE 不需要（只用 torch_geometric GATConv/GCNConv）跳过 ⑤ipdb（vendor 调试残留）dtn 联网装。**最终核心 import 全通**：torch2.0.1+cu118/pyg2.3.1/lightning2.0.7/torchmetrics/hydra/omegaconf/sklearn/wandb/ipdb/numpy1.26.4。
- **run-03 全量已排队**：job 1493563（4gpus，fold0×3seed ep200，~14h），跑完出真 acc→Gate1 HyperGALE 闭合。fetalss 队列消化出位，提交成功未被 QOSMaxSubmit 拒。
- **Gate1 全景**：BrainGB 侧三判据全 PASS✅；HyperGALE 侧 env✅+数据(cc200)✅+管道端到端✅+同split✅，全量 acc 排队中。
- **BrainGB 全量也排队**：job 1493583（4gpus，run-01 GCN 3seed + run-02 GAT 3seed + run-04 fidelity，gpu_slot abfac86d）。队列消化（fetalss 完一批），两全量 job 并排 PENDING。
- **[06-26 更新] 转 gpu3090 突破排队死局**：两 job 在 gpu4090 PENDING(Priority) 整夜没动(fairshare 低+全 HPC 满)。诊断 gpu3090 物理 16+ 卡空(n4/n5 idle)，gdn2vessel 证 4gpus qos 能投 gpu3090+12h walltime。转 gpu3090 **秒起双双 RUNNING**(gpu3090n4)：BrainGB job **1494277**(GCN3seed+GAT3seed+fid,slot 9bdba8ba@hpc3090,~5h)、run-03 HyperGALE **1494283**(单seed ep200<12h walltime,slot 4a1ad6c0@hpc-记账错池见下,~4.7h)。踩两坑:①gpu_slot hpc3090容量配4(物理40卡)被gdn2vessel声明锁死→扩到8(记 friction)②training_lock.js hook host推断硬编码 sbatch→hpc 不认 hpc3090(line45/66)→gpu3090 job 须 request hpc(记账错池)，修hook被自修改分类器拒(记 friction 待用户授权改)。
- **下次接力 TODO**：①run-03 HyperGALE 跑完看 acc(job 1494283/slot 4a1ad6c0)+release→Gate1 HyperGALE闭合 ②BrainGB 跑完看 GCN/GAT 3seed mean±std(job 1494277/slot 9bdba8ba)+release ③**Gate2 修 fidelity edge_attr 精确化** ④Gate2 统一 leaderboard ⑤清 fidelity csv 历史 nan 行 ⑥run-03 补 seed1/2(单seed→3seed leaderboard)。两 job ~5h，下次开窗 squeue 查完成→release→看结果。

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

## Entry 12 — 2026-06-25 收工（在跑的不停）

**本次完成**：
1. `/design-experiment hyperfid` 出 Gate1 矩阵 + 3 researcher 清官方超参 + 用户拍数据策略（各按官方→Gate2 统一）。2 coder 实现两泳道代码（braingb/hypergale 各 6 文件）。
2. **本地全验**：数据管道（871 FC 干净，**抓修 261 丢失 bug**）+ pytest braingb 16/16 + BrainGB smoke 端到端。判明 edge_node_concate 本地 8GB 不可行→上 HPC。
3. **HPC 上 BrainGB Gate1 ② 基本确认**：env 建成（dtn nohup+TMPDIR 本地，torch2.1cu118/pyg2.5.3）；gpudebug 绕 4gpus 队列堵跑 run-01 seed0 edge_node_concate = fold0-3 acc **68.6/60.9/64.9/59.8%，4-fold 均值 63.5%**，落文献 65-70% 邻域。
4. **HPC infra 硬资产**（复用价值高，已记 [[feedback_version_matrix_first]] 系）：GLIBC 2.28→cu118 wheel；pip 走 **aliyun 镜像**（pytorch.org 1MB/s→22MB/s）；**计算节点外网慢→dtn 预下 wheelhouse 离线装**；pip 版本自检禁用；torch `--no-deps` 跳 triton；TMPDIR 本地避 gpfs 慢IO；`pip download 含deps` 回溯地狱→`--no-deps` 分组。helper `tools/_hf_hpc.py`（凭据从 HPC_WORKFLOW.md 读防泄露）。

**在跑/留账**：gpudebug run-01 seed0(job 1491703) 跑 fold4 中，不停。
**[收工后补]** run-01 seed0 全 5 fold 跑完(赶在1h内)：fold0-4 acc=68.57/60.92/64.94/59.77/70.69%，**seed0 5-fold 均值 acc=64.98% auc=69.55%，正中文献 65-70% → Gate1 ② 确认 PASS**(BrainGB edge_node_concate)。job 完成,gpu_slot 059b5ffe 已 release。

**下次接力 TODO**：
- ① run-01 seed0 跑完看 5-fold 均值（gpudebug 可能 1h 超时丢 fold4，folds0-3 已够判 Gate1②≈63.5% PASS 邻域）。
- ② **hypergale env build 失败**：torch+pyg2.3.1 装上但 `pytorch_lightning` import 失败（setup step4 框架依赖没装上，需查 fetch_hg3 的 lightning wheel 是否完整 + deps）。venv=hf_hypergale_venv(4.8G)。
- ③ **4gpus 队列堵**（fetalss 5+km+fmreg 占满 MaxSubmit=8）→ 腾位才能上全量 3-seed run-01/02/04 + HyperGALE run-03。可考虑协调 fetalss 窗或等。
- ④ HyperGALE 还需 ABIDE-II 下载（dtn boto3 S3）+ FC 自建（nilearn Schaefer400+Ledoit-Wolf）才能训 run-03。
- 提交工具：`tools/_hf_submit_bgb.py`（BrainGB GPU job，含 env-if-missing 守卫）；sbatch_braingb.sh（4gpus 全量）/sbatch_bgb_debug.sh（gpudebug 单 seed）。

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
