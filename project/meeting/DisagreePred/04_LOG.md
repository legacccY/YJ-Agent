# DisagreePred PROJECT LOG

> 进度留痕。倒序（最新在上）。

---

## Entry 7 — 🔴 KILL-1 在 289 cluster 硬 FAIL（2026-06-19，gating 证伪，待拍板封存）

**核心 claim「分歧可从图像预测」在功效足的 289 cluster 数据上崩塌——KILL-1 FAIL，且 95% CI 整条压在 0.50 以下。**

**先解决盲区再重跑（见 Entry 6 末 + 本 entry）**：上一轮 HPC job 1471101 跑 54min stdout 全缓冲看不到 fold/perm 进度，无法辨 hang/慢，用户拍「停+反思+杀+加心跳/无缓冲+2rep 烟测+重跑」。coder 给 kill1_baseline.py + a2_seg_uq.py 加 `state.json` 心跳 + `line_buffering`/`flush`/submit `python -u`+`PYTHONUNBUFFERED`（**零改训练逻辑/超参/foreach=False**）。本地 CPU 烟测验心跳真落盘。重传 HPC + 新 submit。

**烟测意外出真 gating 答案**：HPC 烟测 job 1471647（`--n_perm 2`，但**无 --smoke 截断 = 完整 289 cluster 真 CV**）exit0 + 心跳 done + 产出全落。perm 仅 2 rep（null 无效），但 **CV AUROC 点估计 + bootstrap CI 是真值**：
- **cv_pooled_auroc = 0.431317**（n=289 cluster / 119 患者，seed 0，patient-level StratifiedGroupKFold 5 折）
- **95% CI = [0.370409, 0.490820]** ← **CI 上界 0.4908 < 0.50**，整条 CI 低于随机
- per-fold AUROC = 0.4938 / 0.4127 / 0.5231 / 0.3582 / 0.4181（全 ≤0.52）
- verdict = FAIL（Bash 核 `results/kill1_cv_auroc.csv` summary 行 + `kill1_cv_summary.json`，红线达标）

**判决**：触发 ACCEPTANCE **KILL-1**（AUROC≤0.60→核心 claim 死，砍）+ **KILL-3**（分歧纯随机不可从图像预测）。**75-scan 的 0.7094 PASS 是小样本假阳**——Entry 5 大编队复核已警「脆，可信度 6/10，CI 下界 0.6031 擦边，top-10 患者贡献 50.7% cluster，fold 方差 0.44~0.84」，翻倍数据（75→150 scan / 75→289 cluster）后崩到低于随机 = 经典回归均值，无真信号。退路档 MedIA/UNSURE/D&B（A1+A2+A3）全押 A1=KILL-1，A1 死 → 退路同灭。**不跑 perm1000**（AUROC 已低于随机，无信号可测，perm 2rep p=1.0 已印证）。gpu_slot c3bdb04c 已 release。

**盲区根治达成（本轮硬资产）**：state.json 心跳 + 无缓冲固化进 kill1/a2 脚本 + 新 submit 模板（`python -u`+`PYTHONUNBUFFERED`+心跳轮询替代盯缓冲 .out）。fmreg 同款「stdout 缓冲看不到 epoch」摩擦 → 该让 optimizer 固化进全项目 submit 模板 + 训练脚本规范。

**🛑 拍板点（stage-gate FAIL，默认不放行写诚实回退）**：KILL-1 gating 证伪 = 项目核心 claim 死。待用户拍板封存 / 多 seed 复核 / pivot framing。**未拍板前不写「砍」入 registry，不动 STORY headline。**

---

## Entry 6 — 150 scan parse 落地 + A2 管线实现 + KILL-1 rerun 排队（2026-06-19，闪退恢复后大编队续）

闪退恢复，续 Entry 5 大编队。本窗 = DisagreePred（除 ArtiOODBench 外新立项）。

**① 数据扩成**：扩 scan 下载（bt2yuqp0m）完成 → 150 patient/15G 本地。`parse_lidc.py` 跑出 **289 cluster**（`parse_lidc_summary.json`：disagree_binary 164/agree 125，率 56.75%；k 分布 4:125/3:48/2:51/1:65；k_solo agree125/multi99/solo65 供 k=1 捷径消融；方案甲只留 k≥1 禁 k=0；skipped_patch_oob 357/vol_load_fail 4）。

**② KILL-1 rerun 排队（GPU 阻塞，未挤）**：289-cluster rerun（perm1000 + Adam `foreach=False` 修 RTX4070 SM8.9 CUDA illegal memory access，`kill1_baseline.py:364`）申请 local 卡槽 → **QUEUED `a1774701`**，排 artioodbench(`bd707938`，另窗 ~10GPU·h frozen-encoder inference) 后。绝不挤正在跑的。⚠️ 早前一次 289 run（13:38，foreach 修前）崩于 `CUDA illegal memory access`，残留 `kill1_cv_summary.json`=FAIL 0.572/n26/60 **是崩溃残值非真结果**，rerun 会覆写。

**③ A2 管线实现（coder，纯写码不跑）**：
- `scripts/a2_seg_uq.py`（~430 行）：`pylidc.utils.consensus(clevel=0.5)` 出 consensus mask + 2D U-Net(dropout) 训分割 → MC-dropout(T=20 前景熵) + deep ensemble(k=3 前景方差) 出 cluster 级 UQ-proxy → `results/a2_uq_proxy_scores.csv`。folds 复刻 KILL-1 StratifiedGroupKFold(seed0) 保配对合法。
- `scripts/a2_residual_info.py`（~340 行，纯 CPU）：reduced(仅UQ) vs full(UQ+KILL-1 OOF supervised) logistic OOF → 残余 ΔAUROC 配对 bootstrap(按 patient,≥1000rep)CI + LRT + 三件套联合 verdict。
- `kill1_baseline.py` 加 OOF 落盘 `results/kill1_oof_scores.csv`（A2 full model 依赖，rerun 一跑双得）。
- smoke 全过（py_compile + import + UNet forward + AUROC/CI/fold/logistic/LRT mini 测）。
- **A2 consensus mask 预计算后台跑完**（CPU，exit0，不占卡槽）→ `results/a2_seg_masks/`。

**④ A2 分割超参（用户拍板：社区默认先跑，不核源，投稿前补 TODO）**：U-Net base16/depth3、dropout0.3、seg_lr1e-3、30ep、consensus clevel0.5、MC-dropout T20、ensemble k3。`a2_seg_uq.py` 内标 `# TODO 超参待核源`（复现红线，投稿前过 researcher/verifier）。

**⑤ 转 HPC 跑（用户「HPC」拍板 + CLAUDE.md 改默认 host=hpc 优先）**：local 被 artioodbench 超时占住 → 撤 local 队列（dequeue 时已空，无幽灵）→ 申 HPC 卡槽 GO `8149747f`(hpc 1/4)。**不传 15G DICOM**——只传 ~25M 派生件（tar 2.5M：scripts/*.py + results/patches 289npy + a2_seg_masks 289 + 改写 HPC 路径的 labels csv）到 `/gpfs/work/bio/jiayu2403/disagree/`。写 submit_kill1.sh（env=yjcu124py310 torch2.6+cu124，gpu4090/4gpus/48h walltime，`--n_perm 1000 --seed 0`）→ **sbatch job 1471101 RUNNING**（gpu4090n4，RTX4090，过 fold1 没崩=foreach=False 修生效，上次本地正崩于此）。坑：①Git Bash `/tmp` ≠ Windows python `/tmp` 致 sftp FileNotFound → tar 放项目目录绝对路径 ②patch_path 原为 Windows 绝对路径 → 改写成 HPC 绝对（289 行全改 0 残留）③env CUDA 测在 login 节点显 False 是假警报，计算节点 .out 显 RTX4090 真有卡。

**下一步（HPC job 1471101 跑完后）**：①analyst 判 KILL-1 289 真值 A1 PASS/FAIL（CV pooled AUROC + CI 下界 vs 0.60 + perm1000 p）+ k=1/k_solo 消融（验不靠单人标撑分）②KILL-1 PASS 才上 A2：HPC 跑 a2_seg_uq.py(seg-UQ,需 kill1_oof_scores.csv) → a2_residual_info.py(CPU 残余信息) → analyst 判三件套 ③verifier 核数。FAIL 即砍。job 外部 HPC 需轮询（harness 不通知）。⚠️ KILL-1「PASS」须诚实降调（Entry5：50→现 150scan 量级正向信号，CI 下界擦边，perm p<0.01 不写 0）。

---

## Entry 5 — 大编队复核 KILL-1 PASS + A2 重设计 + 扩 scan 启动（2026-06-19，用户「DisagreePred 大编队推进」）

KILL-1 既过，开大编队（researcher×2 + planner + skeptic + analyst + verifier + coder，7 路）复核「PASS 够不够硬投 A2」并设计 A2。结论：A1 PASS 站得住但脆，A2 原设计有致命缺陷已修，扩 scan 75→150 坐实。

**① KILL-2 撞车复查（researcher）→ 🟢 不触发**：差异化守得住。EDUE(2403.16594)/2510.10462 把分歧当训练信号非预测目标，完全不撞。两个边界工作需 related work 主动切：`2508.09381`（皮肤镜 IAA 预测，最近邻，但「边界 vs 存在性」「回归 vs 分类」「数据集」三点可切）+ `2604.26288` CheXthought（CXR 数据集论文，多模态 demo，可切）。LIDC 域 2024-2026 无人把 4-radiologist 存在性分歧当分类 target。

**② KILL-1「PASS」复核（skeptic + analyst 独立收敛）→ 0 致命但脆（可信度 6/10）**：
- 数字全核对，与 Entry 4 逐位一致 ✓（CV pooled 0.709402 / CI[0.6031,0.8116] / perm 0.506346 / 折 0.53/0.44/0.84/0.69/0.83）。
- CI 下界 0.6031 **擦边压 0.60**（Hanley-McNeil 独立估算 0.593 实际跌破，边缘 PASS）。
- 折方差 0.44~0.84，top-10 患者贡献 50.7% cluster = 方差根因；fold2=0.44 below chance。
- k=1 单人标（17 个，44% 正样本）混入「分歧」：①边缘锐利度捷径苗头（k=1 grad 0.0063 vs k=4 0.0114，方向性但 n 小不显著）②k=1「存在性争议」与 k=3「共识性分歧」语义混一类。
- **投稿 framing 须诚实降调**：写「50-scan 量级正向信号」不写「已证稳定可预测」；perm 措辞 p<0.01 不写 p=0.0000。

**③ verifier 核异常**：`kill1_disagree_auroc.csv` perm_mean=0.807（vs cv 版 0.506）= **已废弃早期 buggy smoke 残留**（无脚本引用、5 行同值=bug 特征、对应 Entry 4 记的早期 random-split 实现 bug）。KILL-1 perm 唯一有效真源 = `kill1_cv_auroc.csv` perm=0.506346，PASS 证据可信 ✓。⚠️ `kill1_disagree_auroc.csv` 建议日后归档防误读。

**④ A2 设计 → 🔴 致命已修（skeptic 红队 + 用户拍板重设计）**：
- 原设计 UQ-proxy 用 malignancy 良恶性模型——与「存在性分歧」在 LIDC 天然耦合，无论结果都测不出「专家分歧 ≠ 模型自身不确定」。且原 LOG 把「UQ-proxy 追平」误映射成 KILL-2(撞车)，实为 A2 失败/支柱2 塌(claim 内部矛盾)。
- **重设计（planner）**：UQ-proxy 改 **P1=分割不确定性**——majority-vote consensus mask 训分割模型，取逐像素 entropy(前景均值)/MC-dropout/ensemble 像素分歧当 proxy（它建模存在性本身=要对照的模型自身不确定）。判据改 **残余信息**：reduced(仅UQ) vs full(UQ+本文P(disagree)) 两个 logistic，残余 ΔAUROC 配对 bootstrap CI 下界>0 + 三件套联合。弃单一 ρ<0.7 硬门。
- **硬约束**：现数据无 k=0 负样本纯检测器训不了 → 必走 P1 分割形态，需 parse 补存 consensus mask。
- **researcher 去风险**：`pylidc.utils.consensus(anns, clevel=0.5, pad=...)` 返回 (cmask, cbbox, masks)，150 cluster 稳定可出；UQ 聚合用前景均值 entropy（Mehrtash structure predictive entropy r=0.699）；ResNet-18 encoder+轻 decoder 公平合理。A2 P1 完全可行。

**ACCEPTANCE 改两处（用户批准，补口径/纠错非改阈值方向）**：A2 加量化口径（解耦分割 UQ + 残余信息三件套）+ KILL-2 辨混注释（UQ-proxy 追平 = A2 失败/支柱2 塌，非 KILL-2 撞车）。

**扩 scan 启动（用户拍板）**：coder 改 download/parse 脚本（extend 模式跳已下 50、parse 加 `k_solo` 列支持 k=1 捷径消融）。dry_run 确认 100 新 patient/~12GB。主线串行启真实下载（后台 bt2yuqp0m，本地公开 TCIA 数据非 HPC 上传）。

**下一步（下载完后）**：① parse 重生成 150 cluster 标签（含 k_solo 列）② 重跑 KILL-1（gpu_slot 申请单卡）坐实 A1：CI 下界从 0.60 擦边推到 ~0.65 + k=1/k≥2 拆开消融 + perm 提到 1000 ③ A1 硬了再派 coder 实现 A2（parse 补 consensus mask + a2_seg_uq.py 分割 UQ + a2_residual.py 残余信息，ensemble 5 成员可并行）④ related work 切 2508.09381 + CheXthought。

---

## Entry 4 — KILL-1 真跑（2026-06-18，50-scan smoke→诊断→patient-CV，CV pooled AUROC 0.71 provisional PASS 待置换确认）

用户拍板下 ~50 scan(~6GB) CT 子集跑 KILL-1 smoke。全程主线串：

**下载 + 解析（零拍板，公开数据）**：
- coder 写 `download_lidc_subset.py`（pylidc DB 取 series UID + NBIA getImage 公开 API 免 auth + 选 50 平衡 patient）→ 主线跑下载：50/50 patient，4.29GB，落 `data/LIDC_subset/`，pylidc.conf 配好。
- `parse_lidc.py`（方案甲：只 k≥1 区）串修 4 个 compat bug（主线 <15 行小修）：configparser.SafeConfigParser shim(Py3.12 移除)+ 子集过滤(只跑 50 已下载非全 1018)+ pylidc.conf 写对位置(C:\Users\yj200\pylidc.conf 非 .pylidcrc)+ 熵 k≥total 边界(k>4 合并 cluster log2(0) 崩)。出 **75 cluster：disagree=1:39(52%)/disagree=0:36(48%) 平衡**，75 patch 落盘。

**KILL-1 smoke（50-scan）→ 不可定论 + 红旗**：5-seed AUROC=0.6545±0.3051(seed 间 0.25~0.98 噪声级)，**置换 0.81 没塌回 0.50**。analyst 诊断：根因=(a)实现 bug(置换错把 val/test 标签也打乱+仅2rep)+(b)test 仅 15 cluster/6 patient/4 负例→AUROC 粒度 0.25/步纯噪声。**非 leakage**(patient split 干净 0 重叠 + HU 固定常量归一化无全局泄漏)。

**修复 + patient-level CV 重跑（省下载聪明解）**：coder 重写 kill1_baseline=StratifiedGroupKFold(groups=patient,5 折)+ 置换只打乱 train+≥100rep + bootstrap CI 按 patient 重采样 + GBK ✓✗→[PASS]/[FAIL]。现有 75 样本 5 折 OOF 聚合：
- **CV pooled AUROC(n=75)=0.7094，bootstrap 95% CI [0.6031,0.8116]** → CI 下界 0.60 > 0.50 = 真正向信号（远比单切 15-test 有意义，且不用加下载）。
- 折 AUROC：0.53/0.44/0.84/0.69/0.83（fold2 below chance，但 pooled 稳）。

**✅ KILL-1 PASS 确认（2026-06-18，100-rep 置换跑完 buuwx9eij）**：
- **置换 null 100 rep = 0.5063 ≈ 0.50（塌回了）**，perm p-value = 0.0000 → 修复后置换正确塌回随机 = **零 leakage**，0.71 是真信号非泄漏 artifact。
- 判据三条全过：AUROC 0.71 > 0.60 ✓ / CI 下界 0.60 > 0.50 ✓ / perm null 0.51 < 0.60 ✓ = **KILL-1 PASS**。
- claim「分歧可从图像预测」在 50-scan 量级站住，A1 主判据初步达标。csv: `results/kill1_cv_auroc.csv` 汇总行 `cv_pooled_auroc=0.709402, perm_auroc_mean=0.506346, verdict=PASS`。

**下一步（KILL-1 既过，进 A2/A4）**：① 扩 ~150 scan 加统计功效坐实（可选，50-scan 已 PASS）② A2：分歧预测 vs 模型自身 UQ（熵/MC-dropout）对照，证预测专家间分歧非模型自身不确定 ③ A3：related work 切清 EDUE/2508.09381（辅助任务 vs 预测目标）④ A4：QUBIQ 第二集 + deferral 临床价值。

---

## Entry 3 — 分歧分布确认（2026-06-18，零下载，用户拍板「先 XML-only 算分布」）

用户拍板**不下载过大数据**（LIDC 全集 124GB 出局）。researcher 探精简路径 → 关键发现：**pylidc 自带 `pylidc.sqlite`（6859 标注/1018 scan 全在 DB），算分歧分布零下载**（比下 XML <200MB 还省）。coder 写 `scripts/lidc_disagreement_stats.py`（monkey-patch np.int 修 pylidc 0.2.3 compat + 顺修 parse_lidc.py 同 bug）跑通：

**分歧分布（2651 cluster，无异常 scan，`results/lidc_disagreement_dist.csv`）**：
- k=1:771(29.1%) / k=2:488(18.4%) / k=3:481(18.1%) / k=4:897(33.8%) / k>4:14(0.5%,pylidc 聚类未降到≤4 的边缘)。
- **k=4 全一致=897(33.8%) vs k<4 存在分歧=1754(66.2%)**。
- 对照 Armato2011 65.2%，偏差仅 1.0pp = 数量级完全吻合 → **分歧标签信号真实存在，统计先验过**。

⚠️ 注意：这只证**标签分布真实**，"分歧可从图像预测"（真 KILL-1）仍需 CT patch 跑 AUROC。

**精简数据路径（datasets.json lidc_idri 已登）**：①XML/DB 零下载算分布(已做✅) ②DICOM-LIDC-IDRI-Nodules 2.51GB=per-annotator SEG mask(非CT像素) ③真 KILL-1 需 CT 图像 patch→NBIA 子集 ~50 scan(~6GB,smoke)/~150 scan(~18-24GB,功效足)。LUNA16 衍生丢标注者身份不可用/QUBIQ 无肺结节排除。

**带债 / 下一步拍板点**：分布既已坐实，真 KILL-1（图像预测分歧 AUROC>0.60）需下小 CT 子集——等用户定 ~6GB(50scan smoke) 还是 ~18-24GB(150scan 一步到位)，或继续暂缓。k>4 的 14 cluster 处理（clamp 到 4 还是丢）留 parse_lidc 实现时定。

---

## Entry 2 — Gate1 设计 + skeptic 红队 + 数字订正（2026-06-18，用户拍板方案甲）

**planner 出 KILL-1 矩阵 → skeptic 红队 1🔴 + researcher 核源逮出 STORY 数字错 → 用户拍板补救。**

🔴 **致命（label leakage）**：负样本 k=0（无结节区）让「分歧 vs 不分歧」≈「有结节 vs 无结节」，模型学结节检测就能拿高 AUROC = KILL-1 假 PASS，根本没验「分歧可预测」。**用户拍板方案甲**：KILL-1 改为**只在 k≥1 区内**（至少 1 医师标注的位置）预测专家是否分歧（k∈{1,2,3} vs k=4 全体一致），彻底切检测捷径。社区 SSN（Monteiro+ NeurIPS2020）正是只处理被标过切片。已订正 01_STORY（加 KILL-1 设计红线）+ 02_ACCEPTANCE A1。

🔴 **数字错（researcher 核源）**：旧稿「margin 0.22」用错——0.22 来自 **Dong 2017 是结节边缘锐利度评分（1-5 量表）的分歧**，**不是 detection-level 存在性分歧**。存在性分歧正确口径 = **65.2%**（2669 被标结节仅 928=34.8% 获 4/4 一致，Armato et al. Medical Physics 2011, PMC3041807）。已订正全处（STORY/README/registry/datasets/本 LOG）。

**researcher 补齐官方口径（堵臆想）**：
- pylidc `cluster_annotations()` tol 默认=`slice_thickness`（⚠️ 文档写 pixel_spacing 是 bug，源码为准 Scan.py L419）；padding 在 `bbox/boolean_mask(pad=)`。
- 负样本社区惯例：用 annotation count 当 soft label（0/4~4/4）或只处理标过位置（方案甲对齐）。
- CT 超参：肺窗 clip[−1000,400] 归一化 `(x+1000)/1400`（LUNA16）；ImageNet ResNet-18 当 2D 探针合理（RadImageNet 无 R18 权重，3D 用 MedicalNet）；patient-level split；CT 禁垂直翻转，水平翻转+±10°旋转 OK；Adam lr=1e-4 wd=1e-4。
- 撞车信号：arXiv 2508.09381（skin lesion 从图像预测 IAA 一致性用 AUROC）但当**辅助任务**，落 K2 对手侧，差异化暂守得住——靠「分歧空间结构对齐」拉开（A1 后半句别省）。

**下一步**：派 coder 实现 pylidc 解析（方案甲：k≥1 区分歧标签 + 投票熵）+ KILL-1 baseline（ResNet-18 5seed + 置换检验 + bootstrap AUROC CI）。数据先下 LIDC 到本地（~124GB，确认 D 盘）；🛑 上 HPC=拍板点。

---

## Entry 1 — 立项 spin-off（2026-06-18，用户已拍板）

**立项决策**：源 = ideation run-002（医学图像 × 不确定性）G6 立项 **C065**。用户 2026-06-17 AskUserQuestion 拍板「立项 C025 + C065」（G6_charter.md 签字）。本 entry 为拍板后 spin-off 执行（建标准 schema + 登 registry），非新决策。

**RQ / headline**：别再把标注者分歧当噪声消除——分歧本身可从图像预测。LIDC-IDRI 上把「预测 4-annotator 分歧」当建模目标（而非 majority-vote 取 GT），首次证明分歧是图像可预测的结构信号而非随机标注噪声；模型在专家也犹豫处主动犹豫 = 临床 deferral 信号。

**与边界**：纯新项目（非主论文拆分）。与 ICLR(VisiSkin) / MedAD-FailMap / FMReg / NCA-PhaseMap / SelInfBench 零重叠——多标注分歧预测，正交于校准 / 分割 / 配准 / meta-science。

**立项依据**：
- LIDC-IDRI 4-annotator 存在性分歧巨大（65.2% 被标结节非 4/4 一致，Armato 2011 PMC3041807）= 真实、可量化、临床有意义的分歧源。⚠️ 旧稿「margin 0.22」用错（0.22=Dong2017 边缘锐利度评分分歧≠存在性分歧），2026-06-18 researcher 核源订正。
- R4 taste 48 全 top，零直接竞品；framing 新（预测分歧 vs 消除分歧取 GT）。
- ⚠️ 须守差异化于 EDUE(2403.16594) / 2510.10462（难度估计 / disagreement-guided 训练）——它们用分歧辅助别的目标，本文把「预测分歧本身」当终极目标。
- 立项卡 `ideation/runs/2026-06-17_run-002_medimg-uncertainty/07_report/G6_charter.md` 立项 2。

**G5 killshot ⏳ 未跑（数据待下）**：列为 KILL-1 gating，立项后首要动作——区别于 C025（已 PASS），C065 的核心 claim 全押在下 LIDC 后的分歧可预测性 baseline。先验后大投入。

**诚实天花板**：framing 强 + taste 高，但核心 claim 全押 KILL-1（分歧可预测 AUROC > 0.60）。过不了即砍。退路档 MedIA/UNSURE/D&B（A1+A2+A3 单集）；顶会 MICCAI 需 A4（QUBIQ 第二集 + deferral 临床价值）。书面 kill criteria K1-K4 见 02_ACCEPTANCE。

**带债 / 立项后第一前置**：
- R1（gating，最优先）：下 LIDC-IDRI（TCIA 公开免费 1018 CT 4-annotator）→ 跑分歧可预测性 baseline（KILL-1，AUROC ≤ 0.60 即砍）。
- R2（差异化）：投稿前 researcher 复查 EDUE/2510.10462 系列是否先发占 disagreement-as-target（KILL-2）。
- R3（普适+临床）：QUBIQ 第二集复现 + deferral 实验（A4，standout 升级）。

**venue**：top MICCAI 2026｜fallback MedIA / UNSURE workshop / NeurIPS D&B。算力 ≤ 50 GPU·h。

**下一步 Gate1**：先下 LIDC-IDRI（**HPC 上传新数据 = 拍板点，先报用户**）→ `/design-experiment disagree` 出 KILL-1 baseline 矩阵。数据尚未在 `.portfolio/datasets.json`，已登 lidc 条目 status=todo。
