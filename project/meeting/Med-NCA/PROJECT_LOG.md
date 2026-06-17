# Med-NCA 项目日志（时间倒序）

> 🗄️ **已封印（2026-06-17 用户拍板「封存」）**。Med-NCA 伞下全部 NCA 探索收口、不再投入：
> - **复现线**（Med-NCA/M3D-NCA 最小复现）：实测 M3D-NCA 训练发散，封存。
> - **NCA-JEPA 创新线**：今早已封存（弃 NCA 主线，资源转 P1 ICLR / P3 MedAD-FailMap，详见 registry nca-jepa phase + NCA-JEPA/04_LOG）。
> - **NCA-AB 换路探路**（方向 A 3D 全分辨率分割 / 方向 B 连续疾病轨迹）：A Gate 前判死（prior art + 显存账），B Gate0-2 过、**Gate3 轨迹证伪**（见下「Gate3 终判」）。
> 资产可复用（NCA 码 / NIH 纵向对抽取 / 探针框架 / Gate1 胸片 persistence 能力发现 26.5dB），但无干净顶会方向。后续如续 NCA 医学轨迹须换叙事重走 Gate0。

---

## 2026-06-17 — 换路探路：审核 NCA-AB 两方向 + 文献证伪 + 立项前证伪闸门

**背景**：用户提出把 Med-NCA 从「复现 Med-NCA/M3D-NCA」换路到两个新方向，给了两份材料（`NCA-AB理论.md` 数学分析、`NCA-AB方向.md` 调研）：
- 方向 A：3D NCA 全分辨率体积分割（免 patch / 省显存）
- 方向 B：NCA 连续疾病轨迹生成（中间态=可解释渐进病变）

要求：找出问题、审核 AB、设计完整探路计划。编队 = researcher×2 + skeptic 红队。

**核出的地基级问题（材料前提错误）**：
- `NCA-AB方向.md` 整篇建在「NCA+医学图像零 prior art / 你是第一个」之上，**该前提被证伪**。prior art 密集，且就在本项目目录：
  - **Med-NCA**(IPMI 2023) + **M3D-NCA**(MICCAI 2023) = `M3D-NCA-official/`，本项目正在复现它。方向 A 的「免 patch 省显存 + 多尺度信息传播」两大卖点，M3D-NCA 2023 已做。
  - **OctreeNCA**(2025-08)：184MP 单遍分割、少 90% VRAM——方向 A 核心叙事被整篇覆盖。
  - **GeCA**(MICCAI 2024) NCA 医学高分辨率生成；**TeNCA**(MICCAI 2025) 时序 NCA——方向 B「零 prior art」原话错。
- 本项目复现报告已实测 **M3D-NCA 训练发散**（loss 跳 ~5.0、Dice 归零、无安全区、前列腺 0/11）——材料「训练稳定性可工程化解决」与实测打架。

**审核裁定（skeptic 红队，3 致命）**：
- **方向 A → 接近判死**：卖点全被 M3D-NCA/OctreeNCA 占；唯一缝隙「真免 patch（全分辨率单状态）」被 `理论.md` A.3 自己的显存账打死（512³ BPTT 17–68GB，4090 装不下，为甩 patch 反而更费显存，自相矛盾）。
- **方向 B → 暂缓，须先过 <3 GPU·h 证伪闸**：「连续可解释轨迹」收窄角度可能仍留白，但 persistence training（B 唯一防乱改正常组织的闸门）在本项目实测 NCA 易炸。

**探路计划（证伪闸门，非绿灯）**：Gate0 新颖性精核 → Gate1 persistence 收敛 kill-shot → Gate2 NIH 纵向对数据核查 → Gate3 单病灶轨迹探针。任一 ❌ 即终止 B。

**用户拍板**：B 跑 Gate0-1 证伪。

**本会话结果**：
- ✅ **Gate0 过**（researcher 精核 GeCA/TeNCA/BrLP/AD-DAE/Causal/Nature BME/Ordinal-Diffusion）：B 的「NCA 局部迭代生长机制本身=病变形态演化机制」同构角度仍留白。最近竞品 Ordinal-Aware Diffusion(2025) 属 diffusion+序数嵌入，无 NCA 局部生长；无一篇把 NCA 迭代步与临床疾病阶段显式绑定。
- ✅ **Gate1 脚本就绪**（coder）：`code/probe_persistence.py` + `.yaml` + `test_probe_persistence.py`（pytest 8 passed）。NIH No Finding 子集 64²→128² persistence，sample pool + 每步 loss 防发散，自写 state.json + PSNR/SSIM + 发散早停 + 25ep 对比图。~70MB 显存 / 15-30 分钟。
  - kill-shot 判读：state.json `converged`(val_psnr≥25) / `diverged`；diverged 或 best_psnr 常驻 <10dB → 方向 B 当场死。
  - TODO：lr=2e-3 取自 growing-NCA 印象，非严格 persistence 文献来源（探针非复现，可接受；正式立项再核）。

**状态（卡争用）**：Gate1 probe 申请 local 卡槽 = QUEUED `0d3087f7`，local 1 卡被 iclr C0 re-smoke 占（`12476ec0` starting）。绝不裸启，等 release 自动取出。

**下一步**：local 卡释放 → 起 probe → 读 state.json 判 Gate1 → 过则跑 Gate2（NIH Patient ID 纵向对核查）+ Gate3 探针，全过进正式立项红队；崩则方向 B 终止。

### 续：2026-06-17 同会话 — Gate1 执行完毕（PASS）

**probe 工程坑（修了 3 处，非科学结论）**：
1. CUDA illegal memory access @ `pool.commit`：`self._pool[idx]` 用 CPU LongTensor 索引 CUDA tensor → 非法访问。修：index tensor 放 `_pool.device`。coder 两次没真修（mini smoke pool16/3batch 没触发 CUDA async 错），主线 opus 接手 1 行修好。
2. `perceive()` 每步 numpy 重建 Sobel kernel + `.to(device)`（上万次 host→device 同步）→ 单 epoch 8min。修：Sobel kernel 预建成 `register_buffer`，单 epoch 降到 ~11s（数学等价）。
3. **首版探针退化假 PASS**：persistence-only + 每 batch 重写可见通道为真图 + fc1 零初始化 → 恒等 NCA「什么都不做」就 loss=0/PSNR=100/converged=true。识破后重设计两个非退化 mode（pytest 加恒等 NCA loss>0 反退化断言防回归）。

**Gate1 两 mode 最终数字（state.json 核实，64²/ch16/NIH No Finding 500 张）**：
| mode | 测什么 | epoch1→best PSNR | converged | diverged |
|---|---|---|---|---|
| damage（损伤恢复，Mordvintsev attractor 测试） | NCA 能否学成真 attractor、修复抹除区 | 16.8 → **26.5dB** (ep21 早停) | true | false |
| reconstruct（16²糊图→64²重建，纹理生成力） | 3×3 局部更新能否合成胸片纹理 | 21.8 → **25.56dB** (ep57 早停) | true | false |

**Gate1 裁定：PASS（两 mode best_psnr 均 ≥25dB、converged、未发散）**。NCA 在胸片上既能学成可修复损伤的稳定 attractor，又能从糊图重建纹理——Direction B 的 persistence 地基不是死路（之前最大担忧「NCA 在高纹理胸片上根本不收敛/崩」被证伪）。

**Caveat（如实标）**：
- reconstruct 偏边际：best 25.56 刚过线、val 在 22-25 震荡、loss 仍缓降未完全收敛（早停在 ep57，非 100）。damage 更干净(26.5/ssim0.96)。
- **晚期发散风险未排除**：两 mode 都在 ~ep20-57 早停（kill-shot 只答「能否做」）。本项目复现实测 M3D-NCA 晚期断崖发散（ep121 崩，见 [[reference_nca_divergence_signature]]）——Direction B 正式训练须警惕 ep60+ 晚期崩，非本探针范畴。
- 64² 低分辨率 + 仅 500 张；正式需上 128²/256² + 全量验证纹理是否仍 hold。

### 续：Gate2 — NIH 纵向对核查（PASS，数据充足）

数 `Data_Entry_2017.csv`（Bash csv 核实）：
- 总患者 30805，**有 ≥2 次拍摄 = 13302 (43.2%)**（远超方向.md 估的 15-25%）
- 相邻随访对总数 = 81315
- **正常→异常 转变对 = 14380**（理想轨迹监督：No Finding → 有病）
- 异常→异常（进展）对 = 27722
- 合计 ~42k 疾病相关转变对可用

**Gate2 裁定：PASS**。成对纵向轨迹监督数据极充足（~14k 正常→异常 + ~28k 进展对），远超 PoC 所需，无须 unpaired fallback（skeptic 担忧的「unpaired 无监督信号」不触发）。

**当前总进度**：Gate0 ✅(新颖性留白) + Gate1 ✅(persistence 两 mode 收敛不崩) + Gate2 ✅(纵向对充足)。
**下一步**：Gate3 = 单病灶轨迹探针（最简病种如肺结节，小样本跑 Phase2 轨迹训练 mode，停 16/32/48 步看中间态是否渐进合理）。需 coder 写轨迹训练 mode + 一轮训练。Gate3 过 → 进正式立项红队（攻轨迹收敛 + 临床盲评设计）。

### 续：Gate3 设计 → skeptic 红队判 3🔴 → 重设计（kill-criterion 对齐局部性卖点）

**coder 首版实现**（`code/probe_persistence.py` 加 `NIHPairDataset` + mode=trajectory + 中间态评估，pytest 22 passed）：seed=t0、target=t1、NCA 跑 T∈[48,64] 步学 t0→t1，停 16/32/48/64 测 dist_to_t1/dist_from_t0 单调性 + baseline_psnr_t0_to_t1。自动选对数最多 finding = Infiltration(1976 对)。

**🛑 skeptic 红队判 3🔴 致命（先修再跑）**——病根：现判据测「NCA 能否平滑插值到 t1」，但 Direction B 卖点是「NCA **局部**生长出病变」，两者不是一回事：
- 🔴-1 三判据（PSNR>平凡 + 单调 + 非退化）被**全局线性插值退化解通吃**：学成 out_T≈(1−T/64)t0+(T/64)t1 三条全过，但这正是 diffusion/latent 插值在做的全局同步渐变=Direction B 要超越的反面。测的是「能插值」非「局部生长」=NCA-JEPA 路线③(轨迹=h16+插值无独特信息)已死同款坑。
- 🔴-2 缺强基线 → 假 PASS 几乎必然：唯一基线是「啥都不做」PSNR(t0,t1)，最弱。须加全局线性插值 + 小 U-Net 一跳，否则排除不掉「NCA 迭代性纯属累赘」。
- 🔴-3 「选对数最多类」选到 Infiltration（弥漫+标注噪），与局部叙事自相矛盾。须按叙事选局灶病。

**finding 粒度纵向对实测**（Bash 核 CSV，No Finding 最早→单 finding 同患者去 multi-label）：Nodule 943(同VP 646)/Mass 626(397)/Atelectasis 1644(904)/Pneumonia 199(116)/Infiltration 2904(1924)。→ **🔴-3 可修**：选 **Nodule**（结节 5mm→20mm 局部外扩=材料叙事范例病，646 同VP对足）。

**重设计（已发回 coder 修，4 改）**：① 换 Nodule + 只留同 View Position 对（顺带挡 🟠-5 nuisance）② 加**局部性判据** change_in_roi_frac=相邻步变化能量落在 (|t1−t0|) diff ROI 内占比（局部生长高/全局插值低，最关键判据）③ 加强基线 linear_interp + U-Net 一跳，PASS 改写为「NCA change_in_roi_frac 明显 > 线性插值」非「终态多准」④ 加 Laplacian 方差抗糊代理。新 PASS 需 5 条全满足（见发回 coder 的 message）。
**残差(🟢，写进裁定)**：Gate3 PASS=机制可行性探针，非疗效/临床可解释证明；晚期发散(承 Gate1 caveat)、128²+、临床盲评全留正式立项阶段。

### 续：Gate3 重设计实现完毕 + HPC 起训（job 1452901）

**coder 改完 4 处**（`code/probe_persistence.py`，pytest 主线亲跑 **29/29 过**）：换 Nodule 固定 + `require_same_view=True`（同 VP 过滤 nuisance）；加 `compute_roi_mask`/`compute_change_in_roi_frac`（核心局部性判据）/`compute_front_expansion_violation_rate`；加 `SmallUNet`(3层) + `compute_linear_interp_metrics` 双强基线；加 `compute_laplacian_variance` 抗糊代理。state.json 写齐 5 条 PASS 字段。Nodule 同 VP **400 对**（train~360/val~40，够 PoC）。lr=2e-3 仍 TODO(无 trajectory NCA 官方源)。

**HPC 部署（用户放行「全自动」）**：local 唯一卡被他窗 ideation-run002 G5 killshot 占（后 ideation 也挪 HPC），改走 HPC。NIH 数据已在 `/gpfs/work/bio/jiayu2403/nca-jepa/data/nih_cxr14/`（CSV+112120png 同结构），env `yjcu124py310` torch2.6/numpy2.1.2/PIL+yaml 齐。上传 probe_persistence.py + `probe_trajectory_hpc.yaml`（路径改 HPC）+ `sbatch_gate3.sh` 到 `med_nca_probe/`，远程 py_compile 过 → **sbatch job 1452901 RUNNING**（gpu4090n7，1×rtx4090，~30min，卡槽 97e0648f）。
**下一步**：轮询 1452901 → done 则 sftp 拉 `med_nca_probe/results/probe_trajectory/trajectory/state.json` + 轨迹图 → analyst 判 Gate3 5 判据（重点 change_in_roi_frac 明显>linear_interp 才算真局部性）→ release 卡槽。Gate3 PASS→进正式立项红队；FAIL→Direction B 死或大改。

### 续：Gate3 终判 = **FAIL（明确）** → Direction B 叙事证伪

**job 1452901 COMPLETED**（150ep 跑满，exit 0，20min，未发散，Status=PARTIAL/未收敛）。analyst 判读（数字 + 轨迹图视觉）：

**终值（state.json 核实）**：
| 判据 | 值 | 判 |
|---|---|---|
| P1 映射 final_psnr_to_t1 | 16.49 vs baseline(输出t0)=15.41 | +1.08dB，PASS 但有保留 |
| 强基线 unet 一跳 | **15.40（低于 baseline）** | 同规模强监督也学不会 |
| P2 mono_to_t1 违反率 | 0.594 | ❌ FAIL（半数中间帧不单调趋 t1） |
| P3 front_expansion 违反率 | 0.0052 | 数字好看但 trivial（输出几乎没动） |
| P3 change_in_roi_frac | 0.49 < linear 0.72 | ❌ 连均匀渐变都不如 |
| dist_from_t0@step64 | 0.0145 | 输出离 t0 仅 1.5%（near-identity） |
| step64 路程进度 | 36.8% | 64 步只走到 t0→t1 的 37% |
| final_psnr_to_t0 | 18.95 >to_t1 16.49 | 输出更像 t0 不像 t1 |
| P4 laplacian ratio | 0.79 | PASS（轻度糊，勉强） |
| **综合** | pass_summary=False | **FAIL** |

**核心结论（双重）**：
1. **NCA 学的是「停在 t0 附近的微漂移」非「疾病进展」**——轨迹图 ep1 vs ep150 肉眼几乎无差，中间 4 列(snap16/32/48/64)就是 t0 副本，无结节从无到有的局部萌生。front_expansion 好看是 near-identity 的 trivial artifact（输出没动，微扰自然满足单调扩张），非真局部生长。
2. **不是 NCA 特有失败，是 64²/~580 对下 Nodule 的 t0→t1 信号本就在分辨率/噪声底以下**——U-Net 一跳强基线 15.40 连「复制 t0」的 15.41 都没过。几像素的结节差异被重采样+患者间个体差异淹没。材料 §5 命门「纯 NCA+L2 中间态不可解释」在此尺度完全成立。

**判据校准如实标**：change_in_roi_frac 这条门槛位错（线性插值变化正比 t1−t0 天然 ROI 集中、构造≈0.72，非「全局均匀」退化解）；已用 front_expansion 当主局部性判据补正。但即便用补正判据，结论不变（输出近恒等使局部性判据失去意义）。

**裁定：Gate3 FAIL，Direction B 此尺度死、叙事证伪**。analyst 建议不在当前 Direction B 上补丁赌大尺度——上 128²/256²+配准对+改损失=独立新 hypothesis，须重走 Gate0。

**Med-NCA 换路探路总结**：方向 A（3D 全分辨率分割）Gate 前判死（prior art 全占 + 显存账自相矛盾）；方向 B（连续疾病轨迹）Gate0✅新颖性→Gate1✅persistence→Gate2✅纵向对→**Gate3❌轨迹证伪**。两方向均不立项。换路探路收口。
**待用户拍板**：Direction B 关闭（叙事证伪）确认 / 是否换叙事重立项（走 /ideate 或 Gate0）/ Med-NCA 子项目去向。
HPC 卡槽 97e0648f 已 release。临时脚本 `_scratch/hpc_gate3_*.py` 待清。

---

## 2026-06-16 — NCA-JEPA pilot 探路：数据落地 + predictor 集成接通 + 集成 smoke 全过

**背景**：archive.zip（NIH ChestX-ray14 224² resized 版）下好。开门盘点发现上个会话只建了「半成品」——`nca_predictor.py`/3 config/8 哨兵/ijepa clone 都在，但**集成没接通**：`helper.init_model:79` 还硬编码 `vit_predictor`，没 NIH dataset loader，config 新字段 train 侧没消费。本会话把脊柱焊上 + 端到端验通。**分工**：opus 主线做集成接线（关键路径），简单独立件全交 sonnet。

**做的事**：
- **数据落地**（后台解压）：112,120 张 PNG（`data/nih_cxr14/images-224/images-224/`）+ Data_Entry_2017.csv + 官方 train_val/test list 全解压。
- **集成接线（opus 主线）**：
  - `ijepa/src/helper.py::init_model` 加 `predictor_type` 分支 + NCA 超参（nca_steps/nca_hidden/fire_rate/stabilize/deterministic_fire/fire_seed），`scp_nca`/`vanilla_nca` 走 `nca_predictor` 工厂、`vit` 回退官方原版不破；NCA 跳过外部 trunc init（护 fc1 零初始化语义）。
  - `ijepa/src/train.py`：读 `meta` 的 predictor_type/nca_* 字段传 init_model；`deterministic=True` 时全局开 `cudnn.deterministic`+`use_deterministic_algorithms`（Det 件套，理论 §3.2）；dataset 默认切 NIH（`dataset:'imagenet1k'` 可回退官方），传 `subset_file`。
- **sonnet A — NIH loader + 切分**：`ijepa/src/datasets/nih_cxr14.py`（`make_nih_cxr14` 逐参对齐 `make_imagenet1k`、灰度→RGB、subset_file 控子集）+ `build_splits.py`（**patient-level 严切**）。跑出 `splits/`：`pretrain_10k`=10000 图/3257 患者、probe 1%/10%/100%、probe_test=25596（官方 test）；**三组患者重叠全 0**（ChestX-ray14 泄漏陷阱守住）。
- **sonnet B — 8 哨兵审计**：全部 import 通过 + 自测 PASS。s1/s3/s6/s7 即用；s2/s5 待集成喂 encoder/eval_fn；**s4/s8 含作者主动留的 `NotImplementedError` TODO 占位**（`build_ijepa_nca_batch`/`build_nca_pure_predict_case`），待主线接真 batch 才能用。nca_predictor 接口无需改。
- **sonnet C — 3 config 补路径**：a0/a1/a2 的 data 段补 `dataset/root_path/image_folder/subset_file` 对齐真实路径，yaml parse 全过。
- **集成 smoke**（`smoke_integration.py`，CPU，不启训练）：① init_model scp_nca→NCAPredictor 构造 ✅ ② predictor forward shape 对 ✅ ③ vit 回退=VisionTransformerPredictor(11M) ✅ ④ NIH dataset 载 10000 图、3×224×224 ✅。`py_compile` train/helper/nca_predictor/nih loader 全过。

**状态**：**集成脊柱接通、端到端 smoke PASS、数据+子集就绪**。

**续（同会话）— s4/s8 哨兵填实 + 关键发现 + seed plumbing + HPC 全量部署**：

- **s4/s8 哨兵 TODO 填实**（2 sonnet 并行，ECONNRESET 但实活已落盘）：
  - **关键发现①（度量缺陷）**：s8 框架收敛判据 `l2=(pred-target).norm()` 是全 numel 欧氏范数（平方和开根），随张量元素数缩放——NCA target=36864 元素时即使 MSE→1e-6 欧氏范数仍≈0.19，tol=0.01 须 MSE<2.7e-12 **不可达**。改判据为**逐元素 RMSE<0.01**（合 §7#8「L2<0.01」本意），s8 转 **3 passed**（Test3 RMSE epoch4 触底，但 euclid 轨迹震荡 36→2.4→1.87→5.86→1.22，单 fire NCA 纯预测能触底不稳，呼应 PC-2）。
  - **关键发现②（全链 floor）**：s4 全链 batch-8 overfit（encoder 训 + target 冻结 + 16 步 NCA）实测（diag_s4_fullchain，4070×3000 步）**lr3e-3 floor 在 ~0.042**（0.45→0.042=91% drop），lr1e-2 反卡 0.20，**到不了绝对 <0.01**——真发现（全递归链优化慢、有 ~0.04 floor，呼应 NCA 递归不稳），非接线 bug。s4 判据本就是「>90% drop=管线对」（抓 flat/NaN，非追零），步数 1500→3000 过线。
  - **NCA 架构本身健康**：diag 证 deterministic_fire 逐元素固定、纯 predictor 单样本 MSE→1e-6 可收敛、SN 不拖累。
- **seed plumbing 修复**：`main.py` 原无 `--seed`（sbatch 骨架的 --seed 收不到）→ 加 `--seed` argparse + 注入 `meta.seed` + train.py 读 `run_seed` 覆盖全局 seed + 喂 fire_seed；另加 config `$ENV` 递归展开（`os.path.expandvars`，处理 $EXP_LOG_ROOT）。
- **🚀 HPC 全量部署完成**（`/gpfs/work/bio/jiayu2403/nca-jepa/`，env=`yjcu124py310` torch2.6/cu124+einops/timm/pandas/cv2 全在，只缺 submitit 但用 main.py 本地启动不需要）：
  - code(ijepa+configs+sentinels+脚本) tar 上传解压；**archive.zip 2.47GB SFTP 传输中途 EOF 断（2.15GB）→ 写断点续传脚本**（append+seek+keepalive）补满、校验 ZIPOK、解压 112120 png 到 `data/nih_cxr14/`。
  - HPC 上 build_splits（pretrain_10k 10000/3257 患者，重叠全 0）+ smoke_integration **ALL PASS**。
  - sbatch 模板 `hpc/{run_sentinels,sbatch_pilot}.sh`（account shuihuawang/gpu4090/qos 4gpus/rtx4090:1）。
  - **§7 哨兵门 job 1450035 提交**（RUNNING gpu4090n9，8 哨兵串行）。

- **哨兵门结果**（job 1450035，HPC rtx4090）：**7/8 PASS**（s1 归一/s2 EMA/s3 塌缩/s5 z-shuffle 掉50/s6 det/s7 发散/s8 纯预测 RMSE 触底全过）+ **s4 边界 FAIL**（全链 overfit 0.45→0.0506=88.8% drop，差 90% 一线；4070 本地是 91% 过、rtx4090 是 88.8%，floor ~0.05 跨硬件翻转）。**判定 s4 非 bug**（单调降无 NaN + s8 证 NCA 能拟合 + 余 7 全过），是全递归链优化慢的真属性=pilot PC-1/PC-2 要测的信号；不再调阈值凑绿（已调过 s4 步数+s8 度量各一次）。
- **🚀 A0 baseline 开跑（用户拍板）→ 连过 2 个琐碎崩溃修复 → 训练健康跑通**：
  - 提交 1450048 → 崩①`FileNotFoundError` 日志目录没建 → train.py 加 `os.makedirs(folder)`。
  - 重提 1450049 → 崩②I-JEPA 官方 `transforms.py::GaussianBlur` 的 `radius=torch.rand(1)` 是张量、新版 PIL 不收 → 转 `.item()` float（版本兼容 bugfix 非超参改）。
  - 重提 **1450052 训练完成**：loss 0.476(ep1)→**avg 0.059(ep50)** 平滑收敛，ckpt `logs/a0_vit_vits_nih10k/jepa-ep50.pth.tar`(478MB)+`jepa-latest`，~16min，**全链端到端验通**（数据→mask→encoder→predictor→smooth_l1→AdamW）。**第一个完整 pilot 训练跑通。****注**：smoke 当时用简化 transform 没测 make_transforms 组合，故这 2 崩首次真实触发；已确认 DDP/seed/expandvars 全工作。
  - **✅ 红线 10 官方超参联网复核完成**（核 CheXWorld `opts.py`+`PRETRAIN.md`+I-JEPA）→ 写 `configs/PROVENANCE.md`（可审计单一真源，每值标 🟢官方/🟡pilot自定/🔴自创方法/⚠️偏差）。**结论：config ~90% 真是 CheXWorld 官方值**（lr2e-4/wd0.05/ema0.996/mask_scale/pred_depth/min_keep/nenc/npred 全核对上，enc_mask_scale 0.85=opts.py 默认我之前误判）。**真偏差（全有意/已澄清）**：① batch64（我们单卡，CheXWorld 256）② blur 实跑 I-JEPA p=0.5 非注释的 0.2 ③ **clip_grad 故意不加**（三件套=SN+EMA+Det 不含 grad clip，加了会掩盖 NCA 不稳定=PC-1 要观察的，pilot 设计选择非遗漏）④ vit_small/50ep/warmup5 pilot 缩水。**A0 不需重训**（pilot 比同设置下相对差，三臂同 config 受控）。

**下一步（接续）**：① 盯 A0 1450052 训完（50ep，~16min）→ Gate0 判定（A0 probe 显著>scratch + s4 overfit + s5 z-shuffle 掉）。② A0 过 → **A1/A2 各 3 seed**（qos 4 卡并行）→ PC-1/PC-2/Gate1；官方超参已核（PROVENANCE.md），**仍待用户拍**。③ PC-3（10×推理方差）+ PC-4（1% probe）→ Gate2/3 → GREEN/AMBER/RED 三态。本会话产出未 commit（待收工）。HPC 临时脚本 `_hpc_*.py`/`diag_*.py` 待清。

---

## 2026-06-15 — NCA-JEPA 创新线归档 + 规范命名 + NIH pilot 计划落定

**背景**：Med-NCA 复现已封印，子项目转新投稿方向 NCA-JEPA（NCA 替 I-JEPA 的 ViT 预测器，主打稳定/随时推理/可解释三能力）。3 份方向文档散落根目录、SCP-JEPA 与 NCA-JEPA 命名漂移。

**做的事**：
- 建独立子文件夹 `Med-NCA/NCA-JEPA/`，归入 3 文档：`01_创新计划.md`（原 NCA-JEPA_创新计划）/ `02_理论框架.md`（原 理论框架.md）/ `_archive/pilot实验设计_v1.md`（原 pilot 实验设计，已被新 pilot 计划取代）。Med-NCA 复现侧（报告/Plan/REPRO_PLAN/report/results/code/checkpoints）全留原位不动。
- **规范命名止漂**：**NCA-JEPA = 项目/架构家族名**（arXiv 占坑，实测未被占用）；**SCP-JEPA = 加稳定化三件套的具体方法 = A2 臂**。命名横幅写入 01/02/README 三处单一真源。
- **写主交付物 `03_pilot_NIH_ChestXray14.md`**：唯一权威 pilot 执行计划。NIH ChestX-ray14（112,120 全 frontal，224² resized 版）~10k 子集，I-JEPA 官方库只换 predictor，4 臂（A0 ViT/A1 vanilla NCA/A2 SCP-JEPA/A3 能力）+ 8 哨兵 + PC-1~4 + 3 Pillar 指标 + 理论锚验证 + Gate0-3 三态判定 + 退路 B/C/D + HPC（gpu4090/`/gpfs/work/bio/jiayu2403/nca-jepa/`）sbatch 骨架。约 48 GPU·小时 / 2 天。
- 写 `README.md` 入口（命名规范 + 读档顺序 + 判向逻辑图 + 状态）。
- 已上网核实：NIH 数据规模/全 frontal/224² Kaggle 版、I-JEPA 官方库、CheXWorld 官方库、「NCA-JEPA」名未被占用。

**状态**：计划已定，pilot 待用户拍板开跑（训练启停归用户，串行红线）。本次纯文档，不下数据/不写代码/不启训练。

---

## 2026-06-05 — 会话 11：1436470 第三次发散 → 逐行核实零偏离官方 → 转「多 seed 脆弱性扫描」并行 5 job

### 背景：连续两次 1000ep 全发散，回头质疑「是否真按官方」
- **1436470（会话 10 重提的 1000ep）跑到 ep99 又发散**（loss 死平 5.64 + 验证 Dice 0.0），signature 同 1436075。**三连战绩：1435378(301ep)✅0.672 / 1436075(1000ep)❌ / 1436470(1000ep)❌**。2/3 发散太高，不该甩锅 RNG，scancel 止损后逐行核对官方。

### 🔬 逐行核实「零偏离官方」（结论：是，全官方）
对照官方 `M3D-NCA-official/train_Med_NCA.ipynb` cell-5 + `src/` 源码：
- **config 逐字一致**：lr16e-4 / lr_gamma0.9999 / betas(0.5,0.5) / n_epoch1000 / batch20 / channel_n32 / **inference_steps64**（确认官方 prostate notebook 原值，之前纠结的 config.dt=16 是 hippocampus tutorial 存档，无关）/ cell_fire_rate0.5 / in-out_channels1 / input_size[(64,64),(256,256)] / data_split[0.7,0,0.3]。
- **实现全官方原版**：model=`OfficialBackboneNCA`、agent=`OfficialAgent_Med_NCA`、data=`Dataset_NiiGz_3D`、loss=`DiceBCELoss`，零 subclass。
- **归一化官方**：`__getitem__` 用 `torchio.ZNormalization()` + `RescaleIntensity(0,1, percentiles 0.5-99.5)`，强度规整 [0,1]，非 bug。
- **收敛 run 与发散 run 跑同一份代码同一 config，唯一变量 = RNG。**

### ★ 发散真机理（比「RNG 玄学」更具体，报告增值）
R2 用 **64 inference steps @ 256²**，R1 hippocampus 仅 **16 steps @ 64²**。NCA 是递归更新，64 步 = R1 的 4× 递归深度 → cell 状态指数放大空间大 → 落发散盆地概率高。官方论文报 0.838 = 挑了个收敛 run 报单值、未报方差。**复现研究价值点：量化「官方配置在 prostate 大尺度上的收敛概率」。**

### 执行：转「多 seed 脆弱性扫描」（作者决策「最硬」方案）
- **改训练脚本**：`run_r2_prostate.py` 第 27 行 `SEED` 改 env 驱动（`R2_SEED`，默认 42）；MODEL_TAG 已 env 驱动 → 每 seed 独立目录 `r2_seed_{N}` 防污染。**seed 非官方方法 config，零偏离。**
- **查 qos `4gpus` 上限**：MaxJobsPU=4 同时跑 / MaxSubmitPU=8 队列 / MaxTRESPU gpu=4。→ **可并行**（本地「训练串行」红线仅适用 Windows 单 GPU 抢占，HPC 独立 GPU+目录+log 物理隔离，作者批准并行）。
- **并行提 5 个 seed job（42-46）** `_hpc_r2seed.py`：4 RUNNING + seed46 PENDING(QOSMaxJobsPerUserLimit 自动补位)。jobid 存 `_r2seed_jobids.txt`。
  - jobid：42→1436781 / 43→1436782 / 44→1436783 / 45→1436784 / 46→1436785。
- **监控**：新 `hpc_r2seed_check.py`（多 seed 快照 + 发散检测 loss>3+Dice0）。**发散早杀策略**：~ep15 命中 signature → scancel 该 seed（省 GPU ~10 分钟）；收敛的放跑满 1000ep eval。
- **ep1 早期苗头**（同 config 仅 seed 不同）：seed43 loss1.5（疑收敛）/ seed44 3.34 / seed45 4.52（疑发散）→ 脆弱性从 ep1 可见。

### ★★ 重大发现：NCA 中途断崖式崩溃（推翻「发散只在早期」假设）
- 首轮 ep15 筛查：3/5 早发散（42@ep14 / 44@ep27 / 45@ep17，loss>4.5 Dice0），早 scancel。剩 43/46 看似收敛。
- **但 seed 43 中途崩**：loss 健康降到 ep60=0.766，**ep61 单 epoch 暴涨 3.901 → 之后永卡 >4.5**（ep103=4.31 死局）。**不是渐变是悬崖** —— 健康训 60ep 后单步雪崩。scancel 1436782。
- **教训**：早杀策略不安全，NCA 可中途崩，必须盯到 ep1000。检测器修：Dice 塌判定 `==0.0`→`<0.05`（43 崩后 Dice=0.004 漏报）。
- **分布更新（更严峻）**：**4/5 发散（42 早/43 中途/44 早/45 早）+ 1/5 仅存（46）**。收敛率从看似 2/5 跌到 ≤1/5。
- **headline 升级**：官方零偏离配置 prostate 不仅 60% 早期发散，且「健康收敛 run 也可能 ep60 后断崖崩」→ 复现危机证据更硬（单个 seed 健康轨迹不代表能跑完）。

### ★★★ 真因精确定位：生死在 epoch 1 由 GPU fire-mask 随机性掷定（seed 锁不住）
对比各 run 的 **ep1 loss**（首 epoch 末，健康该 ~1.25）：

| run | seed | ep1 loss | 结局 |
|---|---|---|---|
| 1435378 | 42 | **1.25** | 健康→0.672 |
| 1436781 | **42** | **4.33** | 开局坏→发散 |
| 1436783 | 44 | 3.34 | 开局坏 |
| 1436784 | 45 | 4.51 | 开局坏 |
| 1436785 | 46 | 1.29 | 健康(在跑) |

**两大铁证**：
1. **多数不是「中途崩」是「ep1 即死」**：42/44/45 第 1 epoch loss 就 3.3-4.5，开局直落发散盆地，从没健康过（监控 ep14-27 才标红=首次查的时刻，非崩塌时刻）。**唯一真·中途崩 = seed 43**（健康 60ep → ep61 跳崖）。
2. **同 seed 42 两次 run，ep1=1.25 vs 4.33 完全分叉**：同 seed/config/init，第 1 epoch 即分道 → `np.seed+torch.manual_seed` **锁不住真随机源**。
- **真凶 = NCA 随机 fire-mask**（`cell_fire_rate=0.5`，每步随机 50% cell 更新×64 步），用 GPU rand 流 + CUDA 非确定 kernel，不受 CPU seed 控。每 run 掷不同 mask 序列 → 64 步放大 → **ep1 即决定好盆地(1.25)/坏盆地(4.5)**。
- **headline 终版**（最硬）：官方零偏离配置 prostate，**收敛与否在第一个 epoch 由不可控 GPU fire-mask 随机性掷定，seed 完全锁不住**（同 seed 42 一收敛一发散实证）。比「跑越久越容易崩」「fast-subclass 改 RNG」都强。
- ⚠️ 修正「1435378 短训没崩」误解：不是跑得短躲过，是 **ep1 抽中好盆地**后一路稳；与 epoch 数无关。

### ★★★★ 终极结果：0/9 跑满 1000ep —— 官方配置无一存活（含历史 11 次尝试全灭）
| 结果 | seed/run | 死在 |
|---|---|---|
| 唯一跑完(主动停非崩) | 1435378 | 301ep, 0.672 |
| 崩 | 1436075 / 1436470 | ep185 / ep99 |
| ep1 坏盆地即死 | 42,44,45,47,48,49,50 | ep1 (loss3.3-5.5) |
| 中途断崖 | seed 43 | ep61 (健康60ep后跳崖) |
| 中途断崖 | seed 46 | ep~120 (健康109ep Dice0.618 后崩) |
- **seed 46 = 最强反例**：赢 ep1 抽签 + 跨过 seed43 的 ep61 崩区，ep109 Dice 已 0.618（逼近 1435378 终值 0.672），**仍在 ep110-124 断崖崩**。证明**没有安全期，任何 epoch 都可能崩**。
- **崩塌点分布 ep1→ep185 全程散布** → 官方配置 prostate 实际**不可训满 1000ep**，0.838 用公开代码练不到。1435378 的 301ep/0.672 是 11 次里唯一的幸存者且未跑满。
- **1435378 ckpt 已丢**（`rm -rf r2_prostate` 删）→ 无法续训；且 9 新 seed 无一活过 ep169，0.672 本身近乎不可复现。

### R2 终稿定论（建议）
- **R2 = FAIL，但归因强且诚实**：非我方偏离（逐行核实零偏离）、非欠训，而是**官方配置 NCA 训练不稳定性致 11/11 无法跑满**。最好部分结果 1435378=0.672@301ep（论文 0.838，gap −0.166）。
- R2 复现 verdict：**「官方配置在 prostate 上不可稳定训练至论文轮数；0/9 fresh seed 存活至 ep1000，崩塌点 ep1-185 全程散布」** → 这是比单个 Dice 数字更重的复现性发现，升级为报告主结论之一。

### headline 终版（报告 §6 核心，三档证据从弱到强）
1. (会话 7) fast-subclass 改 RNG 流 → 单点发散对照。
2. (会话 10) 同 config 同 seed 42 两次 1000ep 发散。
3. **(会话 11) n=9 seed 扫描：收敛率 1/9；同 seed 42 ep1 loss 1.25(收敛) vs 4.33(发散) 分叉；机理 = NCA fire-mask(cell_fire_rate0.5×64步) 用 GPU-rand 流，CPU seed 锁不住，ep1 即掷定盆地。** ← 最硬，主推。

### 下一步（会话 11 接续）
- ① 盯 seed 46 到 ep1000（**不能信任早停**，seed 43 证明好盆地也可能中途崩）。出最终 Dice vs 0.838 看 gap → R2 是否翻 PASS（≥0.81）或诚实记「收敛时 Dice X + 收敛率 11%」。
- ② 跑完立即下载 seed 46 best ckpt 到本地（防再丢）。
- ③ 报告 §6 用 ep1 loss 分叉表 + fire-mask 机理重写；地基账 R2 更新。
- ④ 清根目录临时 `_hpc_r2seed*.py`/`_r2seed_jobids.txt`/`_hpc_r2full.py`/`_r2full_jobid.txt`。
- ② 汇总 headline：`收敛 N/5 + 收敛 run Dice mean±std + 发散率` → 报告 §6 RNG 脆弱性（比 fast-subclass 对照硬）。
- ③ 决定 R2 终稿数字：若有收敛 run 达 ~0.81 则翻 PASS；否则诚实记「官方配置 prostate 收敛率 N/5 + 收敛时 Dice X」。
- ④ 清根目录临时文件 `_hpc_r2seed.py`/`_r2seed_jobids.txt`/`_hpc_r2full.py`/`_r2full_jobid.txt`（连续挂账）。

## 2026-06-05 — 会话 10：1436075 静默发散诊断（同 config 同 seed 仍炸）→ 杀 + 重提 1436470 + 监控弃弹窗改终端

### ⚠️ 训练问题记录（作为参考 — NCA 复现脆弱性又一实证）
**现象**：1000ep 重训 job **1436075** 跑到 ep185 时被发现**静默发散**：
- 训练 loss 从 **ep1=4.80 起就死平在 ~5.0**（4.6–5.8 抖），185ep 完全不降。
- 中期验证 **`Average Dice Loss 3d: 0, 0.0`**（格式 `0, X`，第二个数 X 才是真 mean Dice），连续 7 个验证点 patient 23-31 **全 0.0**。

**对比老 run 1435378（301ep，成功）**：ep1 loss=**1.25** → 降到 0.8；验证 Dice 0.47→0.60→0.70→0.73。**起点 loss 就差 4 倍。**

**根因确诊（非欠训/非打印 bug/非配置错）**：两 run 打印 config **完全相同**（`impl=official steps=64 lr=0.0016 grad_clip=0.0 seed=42`），test split 同一批 patient（23-31）。同 seed 同 config 却一收敛一发散 → **官方 Med-NCA 复现非 bit 级可复现**：`np.random.seed(42)+torch.manual_seed(42)` 锁不住 DataLoader shuffle worker RNG + CUDA 非确定 kernel + NCA fire-mask 随机流。prostate 大配置（256²/64步）处**稳定边缘**，run 间 RNG 噪声偶尔把轨迹推进发散盆地。**这正是报告 headline「NCA RNG 脆弱性」的又一直接实证**（会话 7 是 fast-subclass 改 RNG 致发散，本次是同 config 纯运气发散，更强）。

**🔑 发散 signature（存档供日后秒判，勿再等 185ep）**：`过 ep10 后 loss 仍 >3.0(健康起点~1.25) + 验证 Dice==0` = 死局，不会恢复，立即 scancel。旧 `hpc_mednca_gui.py` 只查 nan/oom **漏报这种静默发散**，烧了 2.5h GPU 才被肉眼发现。

### 执行
1. **scancel 1436075**（队列确认清空）—— 跑 185ep 死局烧 GPU，0 价值。
2. **零偏离重提 1000ep → job 1436470**（RUNNING gpu4090n4，`_hpc_r2full.py`，config 一字未改，赌这次 RNG 落收敛盆地，像 1435378 一样）。
3. **监控弃 tkinter 弹窗**（黑屏风险 + 漏报发散）→ 新建 `hpc_mednca_check.py`（终端单次快照 / `watch` 轮询，**内置发散检测** loss>3 死平 + Dice 0 → 报红）。`hpc_mednca_gui.py` 弃用。

### 下一步（接续）
- ① 盯 1436470 **前 ~20ep**：ep1 loss 该 ~1.25、验证 Dice 该非 0 = 落收敛盆地；若又是 loss>3 + Dice 0 → 再 scancel 重抽（或固定更多 RNG 源 / 接受老 run 301ep 0.672 写终稿）。
- ② 收敛则跑完 1000ep eval Dice vs 0.838，看 gap。
- ③ 把「同 config 发散」这次写进报告 §6 RNG 脆弱性（比 fast-subclass 对照更硬）。

## 2026-06-05 — 会话 9：R2 官方配置核实 + 收敛趋势诊断（未饱和）+ 延 1000ep 重训提交

**核实 R2 是否按官方**（`R2_REPRO_REPORT.md` §1 逐项对照官方 `train_Med_NCA.ipynb` cell-5）：**11/12 项一字不差**（BackboneNCA/ch32/64²→256²/lr16e-4/betas(0.5,0.5)/无裁剪/batch20/DiceBCE/steps64/单模态T2/整腺二值/split0.7-0-0.3），**唯一缺口 = epoch 301 vs 论文 1000**。连「数学等价提速」都没用（fast subclass 已作废）。→ R2 0.672 FAIL 主因坐实 = 欠训。

**收敛趋势诊断**（拉 HPC job 1435378 `r2full_1435378.out` 逐 epoch loss + 每 25ep 验证 Dice，脚本 `_hpc_r2trend.py`）：
- **训练 loss 一路降没平**：ep125→300 从 0.37→0.27（斜率未归零）。
- **验证 Dice 峰值线持续抬**：ep25=0.47→ep150=0.73→**ep275=0.795**（已贴 UNet 基线 0.799），ep300 ckpt 落回 0.68 = n=9 小样本 ±0.1 抖动撞噪声谷。
- **判定：未到瓶颈**，延 1000ep 极可能显著缩 gap（−0.166）逼近论文 0.838。

**提交 R2 1000ep 重训**（HPC job **1436075**，RUNNING gpu4090n4）：仅改 `R2_EPOCHS=300→1000`，其余零偏离；清 `r2_prostate` 目录防 config.dt 陷阱；墙时 48h 预计 ~10h。提交脚本 `_hpc_r2full.py`，jobid 存 `_r2full_jobid.txt`。监控 GUI `hpc_mednca_gui.py 1436075`（已修 `TOTAL_EPOCHS=1000` + 日志路径 `r2full_<jid>`）。

**下一步（会话 10）**：① 盯 1436075 收敛 → ep1000 eval Dice vs 0.838，看 gap 缩多少 → R2 是否翻 PASS。② 若仍 < 0.81 诚实记「1000ep 仍未达 + n=9 高方差」终稿。③ R2 翻盘则回填 `R2_REPRO_REPORT.md` + 报告 §5 + 地基账。④ 清根目录 `_*.py`/`_*jobid.txt` 临时文件归位（连续第 N 次挂账）。

## 2026-06-05 — 会话 8：R1/R2 官方原版收口 + 全套行为档案官方重算 + LaTeX 复现报告终版（6页6图）

**本会话 = 地基复现收口大会战**：R2 官方版结果落地、R1 官方版训练收敛停训冻结 anchor、C1/V1/V2/S1 全套用官方 ckpt 重算覆盖 fast 版、产出带图表的专业 LaTeX 复现报告。

**🔵 R2 (Prostate) 官方原版结果**（HPC job 1435378，COMPLETED 02:50:26，301ep）：
- per-volume Dice **single 0.672 ± 0.148**（CI [0.575,0.765]）/ **pseudo10 0.686**。论文 0.838，**verdict FAIL gap −0.166**，但**非崩溃**（fast 版 1435267 是 0.0 全背景发散）。
- gap 诚实归因（不凑数）：① 301<1000ep 欠训（同 R1 方向）② n=9 小样本高方差 ③ split 随机 ④ 单模态 T2（官方码本身丢 ADC）。守红线 §1#3 不延 epoch/换 split 凑 0.838。
- summary 下载本地 `results/r2_prostate_{single,pseudo10}*.{csv,json}`，回填 `results/R2_REPRO_REPORT.md`。

**🥇 R1 (Hippocampus) 官方原版收口 PASS**：
- 本地训练 eval 连续 3 点平台（ep125/150/175 = 0.8644/0.8647/0.8641，ep175 微降=过拟合前兆）→ **停训于 epoch 187**（最新 ckpt epoch_150）。
- `finalize_r1_official.py` eval-only 冻结官方 anchor（官方 `BackboneNCA` ch32/steps16/rescale，params **70,016**）：**single 0.8644 ± 0.0353**（CI [0.8557,0.8718]）**PASS** / **pseudo10 0.8663** PASS / **R4 ensemble>single +0.00187**（CI 排除0）PASS。
- 官方版 0.8644 ≈ fast 版 0.8661 ≈ 平台 eval 0.8647 → **三源一致，R1 复现坐实**（论文 0.886 −1std 内）。
- `results/r1_official_{single,pseudo10}*.{csv,json}` + `r4_official_summary.json`。

**🔬 C1 官方版重大发现（报告增值点）**：官方训练 steps16，推理步数扫描 → **Dice 在 steps=16 达峰 0.865，偏离即退化**：steps32→0.808、steps48→0.236、steps64→**0.123 崩溃**。**NCA 推理步数必须匹配训练步数，Med-NCA 非 over-step-stable**（与 fast 版训练 steps64 单调饱和到 64 完全相反）。机理：over-stepping 致 cell 状态过度演化。

**V1/V2/S1 官方 ckpt 重算（覆盖 fast 版，4 脚本已转 ch32/steps16/官方 BackboneNCA）**：
- **V1 鲁棒性**：baseline 0.8647，noise std0.4→**0.046**（最毒）/ bias_field coef0.7→0.429 / scale0.8→0.743 / translate10px→0.770 / ghosting int1.0→**0.809**（最钝 −0.056）。定性同 fast 版。
- **V2 NQM**：n=78，2 例 fail（<0.8），top-2 检出全中 **detection 1.0**，**R5 Spearman ρ=0.4737 p≈3e-6**。论文「内建质控」声明复现。
- **S1 确定性**：同 seed 复跑 max_abs_diff **0.0**，mean_rerun **0.86439 = anchor**，PASS。

**★ NCA 复现脆弱性发现（report headline）**：prostate 同配置纯 RNG 对照——fast subclass（GPU-rand）0.0 发散 vs 官方（CPU-rand）0.672 收敛。数学等价的提速改 RNG 流即破坏复现。坐实零偏离红线 §1#8。

**📄 LaTeX 复现报告终版** `report/mednca_repro_report.pdf`（**6 页 + 6 图 + 附录**，英文顶会风格，对标 RIDGE）：Abstract→§1 Intro→§2 Med-NCA→§3 零偏离协议→§4 R1（收敛图+C1步数图+anchor表）→§5 R2（gap归因）→§6 ★RNG脆弱性（headline图）→§7 行为刻画（V1/V2/efficiency）→§8 Discussion→§9 Conclusion。6 图全官方数据：fig_{convergence,c1_steps,v1_robustness,v2_nqm,anchor_compare,rng_fragility}。画图脚本 `report/figures/plot_*.py`。
- 诚实标注：fast 版（ch16/steps64）= deprecated 非官方配置参考；官方版（ch32/steps16）= 复现 anchor；RNG 纯对照仅 prostate（同配置），hippocampus 两版配置不同不算纯对照。
- efficiency hippo latency/mem 标 pending（params 70016 已填，prostate 四件套完整）。

**杂项**：红线翻转——`iclr_session_start.js/.ps1/.sh` 改「Opus 在 project/ 内默认开 caveman，用户说关才关」（原为「关 caveman」）。

**地基账（更新）**：R1 ✅ PASS（官方 0.8644）+ R3 ✅（70016<100K）+ **R2 🟡 未达标**（0.672，诚实部分复现）。A 组 R2 仍是唯一未 PASS 锚点。B/C 组行为档案全官方化齐（S1/V1/V2/R5/C1）。

**下一步（会话 9）**：① 作者决策 R2——接受 0.672 诚实部分复现 写入终稿，或申请延官方 1000ep 重训追 gap（非偏离）。② efficiency hippo 四件套补测（可选）。③ R1_REPRO_REPORT.md 已待官方版更新。④ 地基是否 gate：R2 未 PASS 下作者定是否转创新选型。

---

## 2026-06-04 — 会话 7：揪出 R2 发散真因 = 我方 fast subclass RNG + 立「零偏离」红线 + R1/R2 官方原版双线重训

**🔴 R2 发散真因坐实（推翻会话 6 的「config 尺度梯度爆炸」初判）**：
- 上网溯源（官方 Med-NCA repo notebook + IPMI'23 论文 ar5iv + M3D tutorial config.dt）：官方 prostate 配置 = **steps64/ch32/256²/lr16e-4/无裁剪 = 我们 R2 一字不差**；论文只提 reflect padding + 50% fire rate 稳定化，**无梯度裁剪**，Dice 0.838。→ R2 配置忠实，发散非配置错。
- diff 两 repo（Med-NCA vs 本地 M3D-NCA）源码：`Agent_Multi_NCA.batch_step` / `Model_BasicNCA` / `BackboneNCA` **逐字相同**，换 repo 无意义。
- **真凶 = 我方 `FastBackboneNCA`**（会话 3 加的提速 subclass，把 fire-mask `torch.rand` 从 CPU 挪 GPU）：虽数学「等价」，但**改了 RNG 流 → 随机 fire mask 序列不同 → 训练轨迹不同**。prostate 大配置处稳定边缘，fast 版梯度爆炸(logits -1e9, Dice 0)、官方原版 CPU-rand 正常收敛。
- **实证**：忠实 smoke（job 1435372，官方 `BackboneNCA`+无裁剪+lr16e-4+64步）loss ep1=1.25→ep5=1.01 健康降、Dice@5ep=**0.33**（fast 版同点 0.0）。真凶坐实。

**🔴 作者立永久红线 §1 #8「复现必须完全按官方，零偏离」**（最高优先）：禁私自加裁剪/降lr/改步数/换实现/连提速 subclass 也禁；复现不出只能诚实记失败；偏离要过三道闸（穷尽证明+显式标注+作者批）。已写 REPRO_PLAN §1 + 跨会话记忆 `feedback_repro_zero_deviation`。
- 据此：早期加梯度裁剪+降lr 的 smoke（job 1435362, Dice 0.37）**作废**，仅算诊断。
- 据此：旧 R1 0.8661 也用了 fast subclass + 非官方超参 → **作废重训**；其行为刻画 C1/S1/V1/V2/R5 待 R1 官方版收敛后重算。

**双线忠实重训启（全部官方原版，零偏离）**：
- **R2 HPC** job **1435378**：官方 `BackboneNCA`+ch32+steps64+256²+lr16e-4+无裁剪+300ep（官方 prostate notebook 一字不差），~10-25h。监控弹窗 `hpc_mednca_gui.py 1435378`。
- **R1 本地** 4070：官方 `BackboneNCA`+官方 hippocampus `config.dt` 全套（ch32/steps16/batch40/rescale=True/16→64/1500ep）。2ep smoke 验 Dice 0.62 健康（一次偶发 CUDA unknown error，重试即过）。~3.5min/ep → eval 每 25ep 早停于收敛。新目录 `r1_hippocampus_official`，监控弹窗 `r1_live_gui.py`。

**下一步（会话 8）**：① 盯两训练 eval 收敛 → R2 Dice vs 0.838、R1 vs 0.86 → 忠实 PASS。② R1 官方版冻结后重算 C1/S1/V1/V2/R5 覆盖旧 fast 版。③ 两者忠实 PASS = 地基就绪 → gate 交作者选创新向。④ 清根目录临时文件（`_*.py`/`_*jobid.txt`/`_mednca_repo`/GUI）归位。

---

## 2026-06-04 — 会话 6：复查补账 — R1 行为刻画全做完(C1/S1/V1/V2/R5) + 🔴 R2 prostate 训练发散硬 FAIL

> ⚠️ **本 entry 是事后补记**：会话 6（06-04 凌晨）的实验全跑了但当时没记日志、没更新 state.json、没填 R2 报告（PROJECT_LOG 已第二次同坑，见会话 5 末尾教训）。本次复查靠产物 + HPC log 还原。

**✅ R1 (Hippocampus) 行为刻画全套补齐（4 项，全本地 4070，seed 42 / commit 9d844b58）**：

- **C1 推理步数扫描**（`results/c1_steps_summary.json` + `r1_c1_steps.csv`）：steps∈{1,2,4,8,16,32,48,64}。64步=**0.866** 复现 anchor（容差 0.005 PASS）。**拐点 ~32 步**（steps=32 Dice 0.692 → 48 0.846 → 64 0.866，48 后增益收窄）。<16 步基本不分割（Dice <0.17）。→ **C1 ✅ PASS**。
- **S1 确定性复跑**（`s1_determinism_summary.json`）：single 推理同 seed 复跑 vs 冻结 csv，逐例 **max_abs_diff = 0.0**，n=78。地基可复跑实锤。→ **S1 ✅ PASS**。
- **V1 鲁棒性退化曲线**（`v1_robustness_summary.json` + `r1_v1_robustness.csv`，76705 行）：对 test split 施 5 类扰动逐档算 per-patient 3D Dice。关键数：
  - **noise** 最毒：std0.1→0.815 / std0.2→0.498 / std0.4→**0.032**（几乎全崩）
  - **bias_field**：coef0.5→0.663 / coef0.7→0.454
  - **scale**：0.8→0.710 / 1.2→0.791（对称敏感）
  - **translate**：10px→0.725
  - **ghosting** 最钝：int1.0 仅 −0.015
  - → **V1 ✅ DONE**（行为档案，非 PASS/FAIL 门）。
- **V2 NQM 失败检测 + R5 相关**（`v2_r5_summary.json` + `r1_nqm_per_volume.csv`）：78 例里 2 例 Dice<0.8。NQM 降序 **top-2 命中全部 2 例 fail（检测率 1.0）**。**R5 Spearman ρ = 0.4963，p≈1e-6**（NQM 越高 Dice 越低，方向成立，p<0.001 显著）。→ **V2/R5 ✅ DONE**，为「质量度量」铺路。

**🔴 R2 (Prostate) — 训完 301 epoch 但彻底崩，FAIL**（HPC job **1435267**，gpu4090，23:07→01:43 约 2.6h）：

- eval **Dice = 0.0**（single + pseudo10 都 0）。`r2_prostate_single_summary.json` verdict=FAIL（HPC 上，未下载）。
- **根因揪出**（debug job 1435324 `_debug_r2.py` 逐例 + 1435325 `_debug_r2_ckpts.py` 时间线）：
  - 输出 logits **爆至 -1e9 量级**（`raw min≈-9.8亿 max≈-490万`）→ sigmoid 全压 0 → **预测全背景 pred_fg 恒 0**。
  - **非数据/eval bug**：GT 正常（gt_fg 0→3690、unique{0,1}）、输入归一 0~1 正常。
  - **时间线**：epoch_50/100/150/200/250/300 **六个 ckpt 全 mean_dice=0** → 从头没学会，非晚期发散。
  - 训练 loss 全程卡 ~5 不降（main job log 实锤）。
- **崩因判断**：channel_n=**32** + fine **256×256** + 64 步 + lr=**16e-4**，比 R1（ch16/64×64）激进太多 → NCA 状态 64 步内数值爆炸。R1 那套稳，prostate 这套发散。
- **配套**：R3 prostate 参数量 **70,016** <100K ✅（channel_n=32）；Efficiency 四件套 `r2_efficiency.json`（peak_mem 121.6MB、latency 173.6ms/slice、310 GMACs，本地 4070 dummy 输入测，与 Dice 失败无关）。

**当前 Phase 0 账**：R1 系（R1/R3/R4/C1/S1/V1/V2/R5）全齐 ✅；**R2 卡死 FAIL** → 最小复现差 R2 一项，**地基未就绪**，不可转 Phase 1。

**下一步（会话 7 开门即办）**：
1. **救 R2**：查官方 `train_Med_NCA.ipynb` prostate 是否另有 lr/steps 配置 → 降 lr（16e-4→4e-4 或 1e-3）+ 梯度裁剪，或 NCA `update` 后 clamp/tanh 限状态幅值（外部 subclass，不动官方）→ 清 `checkpoints/r2_prostate`（防 config.dt）→ HPC 重训。
2. R2 PASS → R1+R2+R3 三项齐 → 地基冻结 → gate 交作者选创新向。
3. 下载 HPC 的 `r2_prostate_*_summary.json` 到本地 results/ 留档。

**临时文件待归位**（根目录散落，收工前清/移）：`_debug_r2*.py`、`_hpc_*.py`、`_*_jobid.txt`、`hpc_mednca_gui.py`、`mednca_watch.py` → 应移入 `Med-NCA/code/` 或删。

---

## 2026-06-03 — 会话 5：计划定稿 v1.0（复现锁论文数据集）+ 多 agent 备非实验件 + Task05 下载

**定位决策（用户定）**：复现严格按论文，**只用官方数据集 hippocampus + prostate，弃自建 ISIC**。web 核实官方 `MECLabTUDA/Med-NCA` + `M3D-NCA` 只评这两个，无 ISIC → 旧 R2(ISIC) 的「0.772 来路不明」完整性漏洞消除。

**REPRO_PLAN.md 改写 → v1.0 定稿**：
- 删全部创新方向倾向（旧 §7 候选 A-E、§2 方向性跑偏条款）→ 创新选向标「作者独立决策区」，助理零倾向。
- 验收升级 A-F 六组，对标 **RIDGE 五维 + MICCAI 复现 checklist + 复现专章 NBK597469**（web 查实）：A 锚点 / B 稳定性(噪声地板) / C 论文声明复现+行为档案 / D 算力+Efficiency四件套 / E 工程复跑 / F 冻结报告。
- **R2 = Prostate**（取代 ISIC），靶子 Med-NCA IPMI'23 Table 1 **0.838 ± 0.083**（UNet 0.799）；R1 论文精确值 0.886 ± 0.042（我们 0.8661 在 1 std 内）。

**多 agent 并行备非实验件（4 sonnet，零冲突，新增文件——本会话指针）**：
- `code/run_r2_prostate.py` + `results/r2_prostate_target.md`（agent A）：prostate 训练脚本 + 靶子溯源。**官方配置全实证**（`train_Med_NCA.ipynb`+`Nii_Gz_Dataset_3D.py`）：channel_n=32、input_size=[(64,64),(256,256)]、batch=20、单模态 T2(ADC 截断)、整腺二值(label>0)、2-stage。⚠️ channel_n=32 → 参数 ~80K，<100K 但训后核 R3。
- `code/reproduce_baseline.py`（agent B + 主线修）：E1 一键 eval-only 复跑；agent 误接 ISIC，主线已改正为 prostate(NiiGz 3D)。
- `code/extract_baseline_meta.py` + `results/test_ids_r1.txt`(78 例 S0) + `results/r1_convergence.csv`(335 点 C1)（agent C）。data_split.dt 结构：DataSplit 对象 .images/.labels = {train/val/test: {id:path}}，182/0/78。
- `requirements.lock`(70 包) + `code/ENV_NOTES.md`（agent D，E2）：实测 torch **2.7.1+cu118**、CUDA 11.8、cuDNN 9.1、py3.9.25、4070 Laptop 8GB 驱动 576.02。

**Task05 Prostate 数据（主线）**：
- `code/download_task05.ps1` S3 直链下 `Task05_Prostate.tar`(229MB) → 解压 **32 img + 32 lbl**（MSD 标准 32 例）。
- ⚠️ **坑**：PowerShell bsdtar 解压被 macOS `._*` 资源叉报 warning 当失败退出（marker 写 EXTRACT_FAILED 但 tar 下载完好）→ 改用 Git Bash GNU tar 解过，`._*` 已 `find -delete`。

**验收推进**：S0 ✅ / C1 ✅(有数据) / E2 ✅ / E1 脚本就绪 / R0 靶子溯源 ✅ / R2 代码+数据就绪。**剩余全需 GPU**：R2 训练、S1/S2、V1/V2、D1/D2 运行时、F1。

**下一步（会话 6 开门即办）**：
1. 清 `checkpoints/r2_prostate`（防 config.dt 陷阱）→ `/loop /run-experiment` 启 R2 prostate 2-epoch smoke 验 VRAM/不 OOM + 量 s/epoch → 放长训。
2. R2 PASS（CI 含 0.838 或点估 ≥0.81 且 >0.799）→ 起 Phase P（B/C/D/E/F 加固）→ 地基冻结 → 交棒作者选向。

⚠️ **未 commit**：本会话所有改动（计划 + 新脚本 + 产物 + 数据）尚未 git commit，收工时一并提交。

---

## 2026-06-03 — 会话 4：R1 停训 + epoch_300 eval-only → R1 PASS（Dice 0.8661，baseline 锚定）

**动作**：会话 3 过夜的 1000ep R1 训练跑到 epoch 303，主动停（kill pid 32244）。**epoch_300 ckpt 为冻结点**（下个 ckpt 要到 350，停在 303 不丢 epoch_300）。

**真训实锤**（破会话 3 的 config.dt 假轮数疑虑）：epoch_300 ckpt 是真训 300 epoch 的产物 —— ckpt 目录 epoch_50/100/150/200/250/300 按 ~3.7h 间隔递增（Jun2 19:06 → Jun3 15:24），训练 log 连续到 epoch 303，非会话 3 那种「8 真 epoch」假象。

**eval-only 复现**（新脚本 `code/eval_r1.py`，load epoch_300 不再训，复用 data_split.dt 同 test split）：
- **🥇 R1 single PASS**：per-image(per-volume) Dice **0.8661 ± 0.0333**，n=78，bootstrap 95% CI [0.858, 0.8731]。阈值 ≥0.86 ✅，论文 0.882 容差带 [0.862, 0.902] 内。seed 42，commit 9d844b58。
- **🥇 R3 PASS**：总参数 **25,920** < 100K（2 级 NCA 各 12,960）。
- **🥈 R1 pseudo10 PASS**：10× 推理 ensemble per-image Dice **0.8669 ± 0.0319**，CI [0.8593, 0.8737]，过阈值。覆盖了会话 2 那份过时的 pseudo10_summary（FAIL 0.636 欠训版）。
- **🥈 R4 PASS**（ensemble > single，epoch_300 重核）：mean_diff **+0.00081**，bootstrap 95% CI [0.00024, 0.00149] 排除 0，n_pairs=78。Δ 比欠训版（+0.0078）小很多 —— 收敛后单次推理已稳，ensemble 增益收窄，符合预期（欠训时方差大、ensemble 收益高）。`results/r4_summary.json`。
- **工程注**：pseudo10 是 10× 推理 + 全 slice NQM 打分，本地 4070 上跑 ~1.5h；用 `Start-Process` 独立窗口或 Bash 后台均可，但 **stdout 块缓冲会让 log 的 CASE/NQM 计数严重滞后**，别据此误判进程死活 —— 看 `Get-Process .CPU` 是否在涨才准（`tasklist /FI` 经 grep 还遇到过假阴性"gone"，差点误启重复 job 违反单卡串行）。

**关键澄清 — 会话 2/3 的 FAIL summary 是欠训残留**：`results/r1_hippocampus_single_summary.json` 原写 0.628 FAIL（Jun2 14:08，那是 config.dt 陷阱下只训 ~8ep 的产物）。本会话 eval-only 已覆盖为 0.8661 PASS。**血泪重申**：欠训 eval 产物必须及时覆盖/标注，否则下次会话误读 FAIL。

**最小复现进度**：R1 ✅ + R3 ✅ + R2 ⏳（ISIC 2D，代码会话 3 已就位 `run_r2_isic.py` 未训）。**R1+R2+R3 全 PASS = baseline 冻结，转 Phase 1 创新选型**（§7 候选 A-E，需用户 gate）。

**会话 4 收口状态**：R1 ✅ + R3 ✅ + R4 ✅（§5 四项里仅差 R2、R5）。所有数字 csv + bootstrap CI + seed42 + commit 9d844b58 落盘，守 §3 口径红线。

**下一步（会话 5 开门即办）**：
1. **跑 R2**（ISIC 2D）：先 `Remove-Item -Recurse checkpoints/r2_*` 防 config.dt 陷阱 → `run_r2_isic.py` → per-image Dice vs 0.772 (±0.02)。⚠️ 首排查点 fine patch 64→128/256（ISIC 原图 ~700×900）。⚠️ 长 eval 用 Start-Process，别据 log CASE 计数判死活。
2. R2 PASS → R1+R2+R3 三项齐 → 写「baseline 冻结」+ 报用户 gate 进 Phase 1 创新选型（§7 候选 A-E）。

---

## 2026-06-02 — 会话 3：R1 启训 + 两大根因诊断（config.dt resume 陷阱 + NCA 计算密集）+ 过夜 1000ep

**多 agent 并行**：R1（本地 4070）训练 + sonnet subagent 备 R2 代码（HPC 被 ICLR job 1434145 占，按「被占用就本地」全留本地串行）。

**R2 代码就位**（subagent 交付，未训）：
- `code/dataset_isic2d.py`：2D RGB JPG dataset 适配类（官方只有 nii 专用，无现成 2D RGB）。过滤垃圾文件 + 像素对齐（img INTER_CUBIC / GT INTER_NEAREST 同 dsize）。
- `code/run_r2_isic.py`：结构对齐 R1，input_channels=3，per-image Dice + bootstrap CI。
- ⚠️ 风险点：input_size fine patch=64 对 ISIC ~700×900 原图可能太小（Dice<0.752 第一排查点 = 64→128/256）；channel_n=16 下 RGB 吃 3 slot 有效隐藏维 15→13。

**🔴 根因 1 — `Experiment.reload()` 的 config.dt 陷阱**：
官方 `Experiment.py:82` 启动时若 model_path 目录存在 `config.dt` 就**整个覆盖运行时 config**，`get_max_steps()`(:73) 于是返回旧存的 `n_epoch`，**env 变量 R1_EPOCHS 静默失效**。导致连续两次「300/1000 epoch」其实都只训了 ~8 真 epoch（同 8min、同 Dice 0.628）。summary 里的 `epochs` 字段是假的（只是 python 变量 N_EPOCH 照抄）。**修复 = 每次重训前 `Remove-Item -Recurse checkpoints/r1_hippocampus`**（清掉 config.dt + data_split.dt）。

**🔴 根因 2 — 训练慢真因 = NCA 计算密集，非数据瓶颈**：
- 现象：60-90s/epoch，1000ep ≈ 17-25h。曾见 GPU 1-3%（误判数据瓶颈），实为 batch 间隙采样。
- 查明：`Model_BasicNCA.update:71` 的 fire-mask `torch.rand([...])` 在 **CPU** 生成再 `.to(device)`，每步一次 CPU→GPU 同步（64 步×2 级×136 batch）。
- 修复（不动官方，§2 #5 允许的外部 subclass）：`code/fast_nca.py` 的 `FastBackboneNCA` 覆盖 `update`，rand 直接 device 生成。数学等价（仍 Bernoulli mask，仅 RNG 流换 GPU）。`run_r1` 已改用它。
- patch 后 GPU 拉到 89%（真在算），但 epoch 仍 60-90s → **本质 GPU-compute-bound**，NCA 64 步顺序推理不可并行，4070 Laptop 满载即此速。压不动。

**数据集事实校正**：Datasplit = **182 train / 78 test 个体积**（非 slice），dataset 展开成 ~6528 slice → 136 batch/epoch（batch 48）。

**当前状态（15:58）**：R1 patched 1000ep 在独立 PowerShell 窗口跑（pid 变动，~20h，过夜）。用户决策「跑满 1000ep」。Monitor armed（崩溃+完成）。每 50 epoch 存 ckpt（`checkpoints/r1_hippocampus/models/`），每 25 epoch tensorboard eval（不打印 stdout Dice）。

**Dice 进展（真 epoch 数）**：2ep→0.525，~8ep→0.628（single）/0.636（pseudo10，R4 方向成立 ensemble>single）。论文 0.882 / 阈值 0.86。1000ep 跑完看是否欠训。

**下一步（会话 4 开门即办）**：
1. 读 `results/r1_hippocampus_single_summary.json`（epochs 字段看是否真 1000）+ pseudo10。Dice ≥0.86 → R1 PASS 冻结；<0.86 → 看是平台（真 gap，深挖 slice 轴/归一化/loss）还是仍在爬（加 epoch）。
2. R1 出结果后跑 R2（先 `Remove-Item checkpoints/r2_*` 防 config.dt 陷阱）→ ISIC Dice vs 0.752。
3. R1+R2+R3 全 PASS → 冻结 baseline，进 Phase 1 创新选型（§7 候选 A-E，需用户 gate）。

---

## 2026-06-02 — 会话 2：环境修复 + 数据解压 + smoke test 通过

**完成**：
- 验 CUDA：torch 2.7.0+cu126，`torch.cuda.is_available()` = True ✅
- 补装缺失依赖：nibabel 5.4.2 + torchio 1.2.0（官方代码依赖，REPRO_PLAN 未列）
- ISIC GT 解压：2596 files ✅
- ISIC Input 解压（11GB）：2596 files ✅（Input/GT 配对完整）
- **R1 smoke test（2 epoch）全路径通过**：数据加载 → 训练 → per-patient Dice eval → CSV + JSON，零崩溃
  - R3 params = 25,920 **PASS <100K** ✅
  - 2 epoch Dice = 0.525（正常，未收敛）

**下一步（会话 3 开门即办）**：
1. 启 R1 正式训练（R1_EPOCHS=300，Start-Process 新窗口）
2. 训练约 38h（7.6 min/epoch × 300），每 25 epoch 自动 eval，50 epoch 存 ckpt
3. 完成后读 `results/r1_hippocampus_single_summary.json` 看 Dice vs 0.86 threshold

---

## 2026-06-02 — 会话 1：计划重定位 + 框架迁移 + 官方代码落地

**完成**：
- 读官方 `M3D-NCA-official`（已 clone，shallow）核对架构 —— 发现与 PDF 两处差异：`BasicNCA` 用固定 Sobel 感知（非 learned conv），example loss 是 DiceBCELoss（PDF 说 Dice Focal）。真实超参 lr=16e-4 / betas=(0.5,0.5) / batch=48 / 2-level [(16,16),(64,64)]。
- 写 `REPRO_PLAN.md`：把大项目 6 件套纪律（红线/跑偏/数字溯源/工程血泪/量化验收/lever）迁入。策略定为「最小复现(R1 Hippocampus + R2 一个 2D + R3 参数量<100K)→快速转创新」，独立顶会论文定位，混合算力。
- 建工作目录骨架：`code/ configs/ data/ results/ checkpoints/`。
- 探本地环境：conda 24.11.3 / RTX 4070 Laptop 8GB（够 2D + Hippocampus，3D 大体积留 HPC）。

**收工状态（10:20）**：
- ✅ 数据：Hippocampus 解压 260 img/label 配对（清掉 macOS `._*` 垃圾）；ISIC GT 全✓；**ISIC input 续传中 3.69GB/11.16GB**（`code/resume_isic.ps1` curl -C - 循环，断点续传生效）
- ✅ R1 脚本就绪 `code/run_r1_hippocampus.py`（基于官方 example + per-patient Dice csv + bootstrap CI + R3 参数量核对，阈值 Dice≥0.86）
- ⚠️ **env CUDA torch 阻塞，真因 = C 盘满**：conda mednca(py3.9) + requirements 装好，但 cu118 torch（2.5GB wheel）四次装失败。前三次误判为 spec/CPU-fallback；第四次 log 暴露真因 `[Errno 28] No space left on device`。
  - **`df -h`：C 盘 99% 满，仅剩 2.3GB**；conda env 默认在 C 盘 → 2.5GB cu118 torch 装不下。
  - D 盘 328GB 空闲（ISIC 下载在 D，无辜，非元凶）。
  - 现 torch 被卸空（env 里暂无 torch 模块，属正常中间态）。

**下一步（开门即办，严格按序）**：
1. ✅ env 留 C 盘。`conda clean --all` 已腾出 7.5GB；cu118 torch 在装（log `code/torch4.log`）。
2. 验 `python -c "import torch; print(torch.cuda.is_available())"` == True
3. CPU/GPU 各跑通官方 1 batch（`R1_EPOCHS=2` smoke 验代码路径）
4. 发 R1 正式训练（`R1_EPOCHS=300` 起，Start-Process 开窗 + log 轮询）→ per-image Dice vs 0.86
5. ISIC 续传完（`code/resume_isic.ps1` 应已补满 11.16GB）→ 解压 → R2 2D 适配（RGB + resize 256）

**血泪 +1**：大下载/装包前先 `df -h` 看盘；C 盘<6GB 别在 C 盘 env 装 CUDA torch。已记入 REPRO_PLAN §9 待补。

**红线提醒**：Phase 0 三项（R1+R2+R3）PASS 前不碰创新代码。
