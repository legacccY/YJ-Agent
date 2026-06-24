# WaveFidBench — LOG（时间倒序，单一日志真源）

## Entry 5 — 2026-06-24 OASIS 全自动源（免 DUA，解锁正式 Gate1）

用户问 OASIS 有没有自动办法。researcher + kaggle 查证：**有，免 DUA 全程序化**。
- **源 = Kaggle `ninadaithal/imagesoasis`**（OASIS-1 衍生，80000 张 2D slice，1.3GB，`kaggle datasets download` 直拉）。
- **决定性**：文件名 `Data/Mild Dementia/OAS1_0028_MR1_mpr-1_100.jpg` —— **保留 subject ID `OAS1_0028`**（→ 患者级 split 防泄漏可做，我修过的 `extract_subject_id` 正则 `^(OAS\d+_\d+)` 直接吃）+ **类文件夹**（Non/Very mild/Mild/Moderate Dementia → 4 类 CDR 标签，collect_samples 自动检测）。
- 同时满足「自动下载 + subject ID + CDR 标签」三需求 = **reportable 正式数据，不用等官方 DUA**（官方 OASIS-1/2 DUA 仍是黄金退路，~1周）。
- 旁证：jddunn/dementia-progression GitHub 实证官方 OASIS 文件名 `OAS1_XXXX_MR1_mpr-1_anon` 格式，对照 oasis_cross-sectional.csv 的 CDR 做患者级标签。
- 配 `gate1_oasis.yaml`：patient split + OAS1 正则 + epochs 50 + 全 Quantus + class_weight（imagesoasis 极不均衡）。
- **下一步**：本地下载(进行中)→ 验证患者级 split 不泄漏 → 🛑 HPC 上传 1.3GB(对外,报)→ 跑正式 Gate1 → analyst L1 柱状图 → /stage-gate。

---

## Entry 4 — 2026-06-24 HPC 上传 + Kaggle sanity job 提交（用户拍板「两条都走」）

用户拍板「两条都走」=① 现在 HPC 跑 Kaggle sanity ② 并行申请 OASIS（用户自己申请）。

**HPC 部署（主线串行 paramiko，对外已授权）**：
- 装包：DTN 登录节点 pip 装 `pytorch_wavelets 1.3.0 + captum 0.9.0 + quantus 0.6.0 + PyWavelets 1.8.0`（缺 pywt 补上）。**numpy 恢复原 2.1.2**（我脚本曾误降 1.26.4，因 yjcu124py310 是共享 env，opencv 要 numpy≥2，恢复减误伤）。全栈 import + DWT 验通。
- 上传：`/gpfs/work/bio/jiayu2403/wavefid/`（code tar + data tar 65MB sftp）。data 解压 10240 图（train 4 类各 2560，gpfs 小文件解压慢用 105s，服务端等完）。submit.sh 去 CRLF。
- **卡槽**：`gpu_slot.py request wavefid hpc 1` → **GO 75d8a8b6**（HPC 2→1 空卡）。
- 提交：`sbatch submit.sh` → job 1490385 (wavefid_g1k)，4 步流水线（data_split slice → train resnet50 15ep → subband_zero → faithfulness n=200），config `gate1_hpc_kaggle.yaml`。
- **gpu4090 堵 1h**（集群他用户占 + fairshare Priority 排队）→ 按 [[feedback_hpc_gpu3090_fallback]] 转 **gpu3090**（partition 改 gpu3090 + qos=4gpus，gpudebug 被 gdn2vessel 占）→ 取消 1490385，重投 **job 1490627** → **50s 内 RUNNING @ gpu3090n5**。

**注**：Kaggle sanity = slice split 泄漏，数字**不可报正式**，仅验 GPU 规模 + 真 Quantus 数。正式 reportable Gate1 待 OASIS（用户申请中）。

**✅ Gate1 Kaggle sanity 结果（2026-06-24 18:05 ALL DONE 无报错，job 1490627 @ gpu3090，~50min；slot 已 release）**：
- **分类器** resnet50 15ep slice：test_acc 0.9876 / macro-F1 0.9877（slice 虚高，对齐文献 95-99%）。
- **子带置零（L1 信号强）**：W-base 0.9876（=直通，往返无损✅）| **W-LL 0.25（drop 0.738，置零低频→掉到 4 类随机）** | W-LH 0.955(drop 0.033) | W-HL 0.969(drop 0.019) | **W-HH 0.986(drop 0.002，高频几乎不承载)**。→ 判别信息压倒性集中 LL 低频，高频近乎无关，**L1「频带承载差异真实」预览强**。
- **Quantus 忠实度 4/4 非 nan**：PixelFlipping 102.4 | **ROAD 0.719**（烟测 0.0 = tiny-model artifact，确认非 bug）| IROF 52.9 | Insertion(自实现) 0.756。
- 结论：GPU 规模管道 e2e 通 + Quantus 集成全对 + L1 信号强。**sanity 数据不跑 /stage-gate**（留正式 OASIS Gate1 判 PASS/FAIL）。

**待**：OASIS 到位 → 填 `gate1_oasis.yaml`（同流程 patient split）跑正式 Gate1 → analyst 出 L1 柱状图 + /stage-gate 严判。

---

## Entry 3 — 2026-06-24 Gate1 工程地基烟测验通（coder 4 脚本 + CPU e2e 真烟测 + Quantus 集成修复）

**coder 交 4 脚本 + 2 config + 3 pytest**（`src/{data_split,train_classifier,subband_zero,faithfulness}.py`，`configs/gate1_{kaggle,oasis,smoke}.yaml`）。py_compile 全过。

**装依赖**：captum 0.9.0 / quantus 0.6.0 / pytorch_wavelets 1.3.0（torch 2.7+cu126 已在）。numpy 被升 2.x 打崩 matplotlib → 降回 1.26.4 修复。

**CPU tiny e2e 真烟测**（`gate1_smoke.yaml`，87 图子集，强制 CPU 不占被占的 local 卡，`--smoke` flag 过 training_lock hook）——验工程地基全跑通：
- `data_split.py` ✅ slice 模式 87 图 train60/val13/test14。
- `train_classifier.py` ✅ ResNet50 CPU 1ep 跑完存 checkpoint。
- `subband_zero.py` ✅ **W-base 重建 acc=直通 acc（DWT→IDWT 往返无损，命门验证）**；LL/LH/HL/HH 置零各出不同 acc_drop。
- `faithfulness.py` ✅ **4 指标全非 nan**：PixelFlipping/ROAD/IROF（Quantus）+ Insertion（自实现）。Gate1 Q 块 PASS（≥1 非 nan，实得 4/4）。
- pytest **23/23 PASS**。

**烟测暴露并修 7 个真 bug（印证「pytest 绿≠真能跑」纪律）**：
1. `extract_subject_id` 从 basename 提 subject ID（OASIS ID 在父目录）→ **患者级 split 命门**，遍历路径各段修。
2. pytest `test_ll_zero` 用白噪声断言「LL 置零误差>高频」（白噪声四子带能量均分）→ 改低频主导信号。
3. `train_classifier` 漏定义 `load_config` → inline yaml.safe_load。
4. `faithfulness` `imgs.to('cpu')` 原地 requires_grad_ 污染原 tensor → `.detach()`。
5. **Quantus 传 `model=model_predict`（函数）→ 应传 `model`（nn.Module），Quantus 内部自包 PyTorchModel**（researcher T5 骨架本就直接传 model）。
6. JSON `np.bool_` 不可序列化 → 加 numpy 类型转换器。
7. **Quantus 0.6.0 多通道图像 3 坑**（coder 查源码修）：PixelFlipping `features_in_step` 须整除 H*W=50176（加整除防御）；ROAD indices broadcast 到 C*H*W 越界 → 自定义 `_road_perturb_3ch`（indices % H*W）；IROF mask(N,1,H,W) vs arr(N,C,H,W) → 自定义 `_irof_perturb_broadcast`。

**注**：烟测数字全无意义（1ep tiny model + slice + 极小子集）。ROAD 恰好=0.0 标记正式跑须 sanity check（疑 dedup 或 tiny-model 退化）。

**Gate1 状态**：工程地基 = ✅ 烟测验通（4 脚本 + Quantus 集成 + DWT 往返 + pytest）。**但 reportable Gate1 数字未出** = 须 OASIS 患者级 split（正式主集，用户申请中）+ GPU 跑（local 被 ideation-run011 占 / HPC 2 卡空待上传拍板）。full-Kaggle GPU 跑只给烟测级数（slice 泄漏不可报），价值有限。

**下一步（拍板点）**：① OASIS access 用户申请 → 到位填 `gate1_oasis.yaml` ② HPC 上传代码+数据（对外拍板）→ 跑正式 Gate1。或先 full-Kaggle GPU sanity（非 reportable）。

---

## Entry 2 — 2026-06-24 Gate1 设计 + 数据主集拍板（planner + 4 researcher + 用户拍板）

**planner 出 Gate1 矩阵**（`实验设计_2026-06-24.md`）：18 run ~5 GPU·h，4 块 S(数据)/C(分类器3seed×2backbone)/W(子带置零+L1初验)/Q(Quantus非nan烟测)。Gate1 只验工程跑通+置零生效+趋势，**L1 显著性留 Gate2 防 HARKing**。

**4 researcher 联网清 T1–T5**（全带引用，无臆想）：
- **T1/T2 数据红线**：Kaggle `sachinkumar413` = OASIS-1 的 2D JPEG 切片重分发（**非 AI 合成，溯源真**），但**无 patient ID 做不了患者级 split**，社区警告"unusable for research"。切片级 split 泄漏致 acc 虚高 **28–45pp**（文献 patient-level 66–90% vs slice-level 95–99%，PMC8604922/PMC12468286）。类极不均衡 Moderate 仅 64 张(1%)。退路 OASIS-1/2 自带 subject ID。
- **T3 超参**：ResNet50 主流(ViT-B/16)，Adam lr=1e-4 bs=32 ep=50 224×224 ImageNet 预训练，灰度 repeat 3ch；class weight/SMOTE 治不均衡；文献 acc 须按 split 分层读(slice-level 虚高)。
- **T4 wavelet**：`DWTForward(J=1, wave='db1'=haar, mode='zero')`；`Yh[0]` idx **0=LH/1=HL/2=HH**(注意 finest-first 与 PyWavelets 反)；全 mode 完美重建(fp32 1e-3)；**子带消融建议 mode='symmetric'/'reflect' 减边界 artifact**。
- **T5 Quantus**：**无独立 insertion/deletion**；`PixelFlipping`=deletion(默认 features_in_step=1, perturb_baseline='black')，insertion 反转顺序自实现<50行标清；ROAD(percentages=range(1,100,2),noise=0.01)/IROF(slic,mean,return_aggregate)/RegionPerturbation(patch=8,morf,100region)；captum `LayerGradCam(model.layer4[-1].conv3)`→`LayerAttribution.interpolate`→`.squeeze(1)`=Quantus a_batch (N,H,W)。

**🛑 用户拍板（数据主集）**：选 **「Kaggle 烟测 + OASIS 正式」**。
- Kaggle 今天下载跑通工程地基(下载/分类器/子带置零/Quantus 非nan)，slice-level **仅作烟测**。
- **L1/benchmark 正式数字全在 OASIS 患者级 split 出**（无泄漏，审稿人攻不动）。
- OASIS-1/2 access **用户自己填表申请**（对外，开放获取，数小时–1天）：sites.wustl.edu/oasisbrains。

**下一步**：coder 写 4 脚本(data_split/train_classifier/subband_zero/faithfulness，超参从 config 读两数据集通用) → 主线跑 Kaggle 烟测 → OASIS 到位后出正式数字。

---

## Entry 1 — 2026-06-24 立项决策（用户拍板）

**来源**：选题流水线 `/ideate` 2026-06-24 轮（charter: `project/ideation/runs/2026-06-24_charter.md`；报告: `2026-06-24_选题报告.md`）。从 112 候选漏斗收敛，本项目 = headline 2（B5-13），与 [[HyperFidBench]] 双 headline 并行。

**立项要素**：
- **方向**：Wavelet 频域子带视角的 XAI 忠实度 benchmark（AD 分类）。对齐导师王水花 wavelet×Transformer + 可解释双招牌。
- **会议**：ACCV 2026（Biomedical track；截稿 2026-07-05）；退路 CBM / BSPC。
- **核心 RQ**：AD 判别信息在 wavelet 频带的分布 + XAI 解释是否对齐承载信息的频带 + 哪类 XAI 在哪频带最忠实。
- **边界**：与姊妹篇 [[HyperFidBench]] 同"XAI 忠实度"母题但模态/方法不重叠（本篇 wavelet 脑结构 MRI vs 姊妹超图脑连接组）；共享 Quantus 工程框架。

**G5 地基核查（researcher 联网，全绿）**：
- 数据 Kaggle AD 4-class 当天可下🟢/OASIS 签 DUA🟢；baseline pytorch_wavelets(1.2k⭐)子带置零3行🟢；指标 Quantus(666⭐ ROAD/IROF)+captum🟢；<5 GPU·h。
- 撞车二次确认🟢干净：最近邻 WaveletFusion(2026-05 Haar+CNN AD,无忠实度维度)、2601.12826(肺CT无wavelet)、2407.08546(AD显著图无wavelet子带)。频带×忠实度交叉空白确认。

**红队结论（skeptic G4）**：0 无出路致命。残差4条已入 02_ACCEPTANCE（严守 benchmark 定位 / novelty 锚频带轴 / Quantus insertion-deletion 待核 / 2601.19017 思路借鉴诚实标）。

**最大风险**：WaveletFusion(2026-05)结构最近邻 → 必须定位 evaluation benchmark(多 XAI×多子带×多指标)拉开距离，不写成又一个 wavelet 分类器。

**下一步**：认领 claim → `/design-experiment wavefid` 出 Gate1 矩阵（下 Kaggle AD 4-class + 跑通 ResNet/ViT + pytorch_wavelets 子带置零 + Quantus 出非 nan faithfulness）。先核 Kaggle 数据溯源(防 AI 合成伪造集)。
