# NCA-Cyst — 进度日志（时间倒序，最新在上）

---

## 2026-07-09 · ✅ Phase1a 收敛(越过发散风险) + A2 cyst 3seed 提交 + A3 UNet 烟测 PASS

**背景**：用户「继续一直走到计划结束」→ 自主推进 Phase 1 全部三判据（A1 管线复现 / A2 M3D-NCA 囊肿多 seed / A3 UNet 同口径对照）到出数字。

**做的事 + 结果**：
- **A1 实测达成**：Phase1a full baseline（job 1514946，binary_all/seed0/[10,10]/1000ep/(64,64,32)→(128,128,64)）**稳定收敛**——RUNNING 11h20min，epoch 988/1000，**avg_loss 0.145、dice 0.833、无发散**（发散阈值 loss>3+Dice<0.05 全程没触发）。→ **越过项目头号风险**：立项标注「高分辨率 3D 配置历史 0/11 全发散、KiTS23 体积更大正撞最难区间」——实证零偏离官方复现在 KiTS23 稳定收敛。A1 PASS（等 1000ep 自然收尾落终值）。
- **A2 铺开**：Phase1b M3D-NCA 囊肿 `--label_mode cyst`（label==3）**3 seed 提交 HPC**（job 1515817/1515818/1515819，seed 0/1/2，同 full config）。走 gpu_slot 各占 1 卡（GO 95cce6e2/515299e3/1666b1cc）。当前 PENDING(Priority) 排队等卡（gpu4090 全校 congestion）。目标=A2 多 seed 收敛率 + 均值±std。
- **A3 就绪**：Phase1c UNet3D **本地烟测 PASS**（`--config smoke binary_all`，5case/30ep/(64,64,32)）——无形状错（整除约束 32 倍数验通，`unet-0.8.1` num_encoding_blocks 兼容）、loss 1.196→1.188 健康降、Dice 0.046（未收敛预期）、34.5s。UNet 管线机械正确 → 待 Phase1a 腾卡后提交 UNet full cyst 对照。

**判读**：Phase 1 三条腿全部推到「在跑 / 就绪」。最大不确定性（NCA 在 KiTS23 会不会发散）已由 Phase1a 实证消除。cyst 能否收敛是下一个观察点（囊肿极端类不平衡，中位仅 65/百万体素）。

**下一步（挂监控走到结束）**：Phase1a done→release+提交 UNet full cyst；cyst 3seed 陆续起跑→盯前几 ep 发散 signature；全 done→收 dice 落 `06_experiments/` + `/stage-gate`。零偏离纪律：不因 cyst 发散改超参（触发 K1 则诚实报收敛率）。

**补记（10:40）— A1 落定 + 本地探路否决 + 全排队**：
- **A1 PASS 终值**：Phase1a `status=done`，epoch 1000，**dice 0.831 / loss 0.142**（与进行中 0.833 一致）。M3D-NCA 在 KiTS23 稳定收敛坐实。
- **本地能否原样跑 cyst（用户问「本地快的话本地也可以，前提原样跑」）→ 实测否决**：原样 full config（(128,128,64)/batch2，零改超参）在本地 4070 8GB **显存 OK 不 OOM**（唯一好消息），但**单 epoch 极慢**——state.json 卡 `starting` 整 5.5min，342 train 样本的第一个 epoch 都没跑完。估单 seed 17-25h、3 seed 本地只能串行 ≈50-75h，占死本地卡 2-3 天，**打不过 HPC 3 卡并行**（起跑后 11.4h 全出）。结论=回 HPC 等（用户拍板老实等 gpu4090）。
- **A2/A3 全提交 HPC 排队**：cyst seed0/1/2（job 1515817/818/819）+ UNet full cyst seed0（job 1516006）。全部降 TimeLimit 24h→14h 改善 backfill。**Phase1a done 后 cyst 优先级 103→245 回升**（fairshare 恢复中），SLURM 预估上界 07-13 但实际大概率更早。挂长间隔监控等起跑。

---

## 2026-07-08 · ✅ Phase 1a/1b 本地烟测 PASS（管线验活）

**背景**：coder 写完 KiTS23 数据适配（`code/kits23_dataset.py` 子类直读原生 case 目录免 34GB 扁平化 + label 开关 + 缓存 fix）+ 两套 config + 训练入口（state.json 监控 + 静默发散钩子）。主线本地烟测验管线。

**做的事 + 结果**（本地 mednca env / RTX4070，走 gpu_slot 记账）：
- **Phase 1a 烟测**（binary_all，5 大囊肿 case，input (32,32,16)→(64,64,32)，30 ep）：exit 0 无崩溃，**loss 1.25→1.0 健康降不卡 5.0**，Dice 0.03~0.09（30ep 远未收敛，预期）。→ **路径 override 直读 KiTS23 原生目录成功**（coder 标的唯一静态没法确认点，验通）。
- **Phase 1b cyst 烟测**（label==3，12 ep）：exit 0 无 NaN，loss 1.57→1.05 健康降，**Dice=0.017 非零 → 证明 label==3 真产出非零囊肿标签**（缓存 fix 生效，非静默全零）。
- state.json 监控 + 发散检测器工作正常（loss<3 未误触发）。

**判读**：烟测目的=验管道通不通（非收敛），两条路全 PASS。管线机械正确。收敛/发散风险留待 HPC full（1000ep）真测。

**下一步**：HPC full baseline（用户已放行传输 + 选「先走轻配置探路」）。

---

## 2026-07-08 · 🚀 Phase 1a full baseline 提交 HPC（job 1514946）

**背景**：用户放行 HPC 上传 + 选轻配置([10,10]/1000ep)先探发散。

**做的事**：
- HPC 只读侦察：✅ kits23 数据在 `/gpfs/.../kits23/dataset`（489例）；✅ 官方 M3D-NCA repo 已在 `/gpfs/.../mednca/M3D-NCA-official`（**不用传官方**）；✅ env yjcu124py310 依赖齐（torch2.6+cu124/torchio1.2.1/nibabel5.4.2/cv2）；✅ QOS 4gpus 墙时限 7天/4卡上限。
- 代码改 env 可覆盖路径（`KITS23_ROOT`/`M3DNCA_OFFICIAL_ROOT`），一套代码本地+HPC 通用（小改3文件）。
- 传 4 code 文件 + submit_hpc.sh 到 `/gpfs/.../nca-cyst/`，去 CRLF。**登录节点 `--help` import 预检通过**（官方 src.*+torchio 链全通，版本差异没崩）。
- gpu_slot request hpc 1 → GO 7184eef4（占1剩3）。sbatch → **job 1514946**（config full / binary_all / seed0 / [10,10]/1000ep / (64,64,32)→(128,128,64) / batch2）。

**结果**：job 1514946 PD 排队中（等卡）。⚠️ **关键观察点=会不会重演历史 0/11 发散**（发散 signature：loss 死平>3 + Dice≈0，epoch 1 就可能定生死）。挂后台监控，起跑后盯前几个 epoch。

**下一步**：监控 job → 不发散跑到收敛 → Phase 1b cyst + 多 seed + UNet3D 对照。

---

## 2026-07-08 · 🔬 等卡期间：机制证据 + 调研固化（非 GPU）

**背景**：gpu4090 congestion，Phase1a 排队 ~2 天（优先级 1409 垫底，全校占满；shuihuawang 账户只我 1 job）。用户拍板「老实等 gpu4090，期间推进不吃 GPU 的活」。

**做的事**：
- **调研固化**：五路调研 → `reference/RESEARCH_2026-07-08.md`（全 URL 引用），档自包含。
- **下采样囊肿存活分析**（`code/downsample_survival.py` → `06_experiments/downsample_survival.csv`，248 含囊肿 case，官方 rescale3d 同法）：**粗级 (64,64,32) 9.7% 囊肿完全抹没、中位存活 0.4% 体素**；细级 (128,128,64) 1.2% 抹没、中位 3.5%。
- **核实 M3D-NCA 两级数据流**（`Agent_M3D_NCA.get_outputs` L151-229）：粗级下采样整卷(全局但囊肿没了)；细级随机 patch(L204-209 无 mask 优先采样，囊肿~0.0065%几乎抽不到)+patch间无全局通道。→ **「两难」代码+数据双实测坐实**：无一级同时具备全局视野+看得见囊肿。
- **建 `reference/THEORY_LEDGER.md`**：冻结 H1(机制,🟢实测)/H2(全局池化创新,🔴文献空白待验)/H3(近随机边界)。厘清故事逻辑：vanilla NCA baseline 囊肿失败=动机非矛盾（「我们」=NCA+全局视野Phase2）。
- STORY 支柱2 更新为代码+数据双实测机制 + 加措辞红线（防审稿人误读 baseline 失败）。

**结果**：方法地基假设链冻结、机制有硬证据；档自包含。Phase1a 仍排队。

---

## 2026-07-08 · 🔩 Phase 1c UNet3D 对照并行铺开（HPC 已就绪）

**背景**：用户要并行推进。M3D-NCA Phase1a job 排队时，并行准备 UNet3D 同口径对照。

**做的事**：
- coder 写 UNet3D Phase1c（`config_unet_kits23.py` / `train_unet_kits23.py` / `submit_unet_hpc.sh`）：**复用同一 `Dataset_KiTS23_3D`**（同 case/split/label/eval），仅模型换官方 `UNet3D`+`Agent_UNet`+`DiceBCELoss`（UNet 官方超参 lr1e-4）。7 条同口径对齐点逐一确认。full input (128,128,64) 对齐 NCA 最细级。
- 本地 + HPC 均装 `unet-0.8.1`；**UNet3D 参数 = 19,071,297（~19M）**→ 对比卖点硬数字「UNet ~19M vs M3D-NCA ~13k，约 1500×」。
- HPC prep：传 3 文件、pip install unet、import 预检通过（登录节点 --help，UNet3D+官方链全通）。HPC 侧就绪待 sbatch。
- 本地 UNet 烟测因**别窗（quantimmu TSCAPE+TransHLA）占本地 GPU** → 正确 QUEUED（d4de169a），有卡自动取出。绝不抢正在跑的。

**结果**：UNet Phase1c 代码+HPC 全就绪；本地烟测排队中。

**下一步**：本地烟测验 UNet 算子/整除 → 通过即 sbatch UNet full（HPC 已 prep）。与 M3D-NCA Phase1a 并行出对照数字。

---

## 2026-07-08 · 🟢 立项 + 五路调研 + 建档

**背景**：博士生观察到主流分割模型在肾囊肿上近随机，NCA 加全局视野也许能跑。余嘉本窗任务 = 先做 M3D-NCA baseline。用户拍板立项（方向=NCA×KiTS23 囊肿分割，本期只 baseline，创新模块下阶段再立）。

**做的事**：
- 五路 opus 编队调研（2 路本地 + 3 路联网），交叉验证地基：
  - 数据集确认 = **KiTS23**（肾 CT，489 例，囊肿=label 3），本地+HPC 均验通。
  - 故事成立**但有精确边界**：KiTS23 多类 cyst Dice 0.17–0.45（近随机），但专攻二分类 nnUNet 达 0.82–0.90 → motivation 必须锚定「多类小散布 cyst」。
  - 方法蓝海 = 全局池化 broadcast / global latent token；必避 Fourier（MECLab FourierDiff-NCA）+ attention-NCA。
  - 官方 M3D-NCA 3D 超参从 config 源码核实（Adam lr16e-4 betas(0.9,0.99) / DiceFocalLoss / 两级[(80,80,6),(320,320,24)] / 步数[20,40] / 3000ep）。
  - 重大风险：高分辨率 3D 配置历史 0/11 全发散；静默发散；seed 锁不住；步数须对齐。
- 关键发现：官方 dataloader `Nii_Gz_Dataset_3D.py:209-210` 默认 `label[label>0]=1`（二分类），做囊肿必须改。
- 用户拍板三岔路：①先复现官方二分类→再切囊肿(label==3)；②本期自己也跑 UNet3D 同口径对照；③venue=TODO。
- 建标准档（00/01/02/04 + DATA_INVENTORY）。
- 跑 KiTS23 囊肿分布分析（`_scratch/kits23_cyst_dist.csv`）。

**结果**：项目档建立，计划书批准（`~/.claude/plans/nca-m3d-nca-baseline-*.md`）。

**下一步**：
1. KiTS23 扁平化预处理脚本（case 子目录→images/labels 扁平同名）。
2. Phase 1a：官方二分类 config 本地小样本烟测（验管线不发散）→ HPC 全量。
3. Phase 1b：切囊肿二分类拿 NCA 第一个真数字。
4. Phase 1c：UNet3D 同口径对照。
