# NCA-JEPA — 04_LOG（时间倒序）

> **全史真源**：`../PROJECT_LOG.md`（Med-NCA 总日志，含复现 + NCA-JEPA 全部历史 entry）。
> 本文件 = NCA-JEPA 子项目going-forward 简日志 + 最新状态快照。新 NCA-JEPA 会话在此追一行，详写进 `../PROJECT_LOG.md`。
> 入口读档：`README.md`（命名+状态）→ `01_创新计划` + `02_理论框架`（why+命题）→ `03_pilot`（怎么跑）→ `registry.json`（臂/门/状态）。

---

## 2026-06-16 — A0+ 臂落地 + stability-vs-anytime trade-off 升一等指标
- **拍板执行探路两大 framing 决策**（探路报告 §5 致命伤①②）：用户拍板后 2 researcher 并行查官方源 → 落档。
- **新增 A0+ 臂**（4→5 臂）：early-exit ViT predictor = N 层 ViT + 每层 `Linear(pred_emb,enc_emb)` L2 head + **等权聚合**（MSDNet 官方 `ParallelCriterion` weight=1，ICLR'18 1703.09844；MeViT 2106.15183 证 early-exit+regression 可行）。参数 ≈ A0 不偷加。打死「ViT 也能 early-exit」reviewer 攻击（reject 级）。
- **意外强 novelty**：全网零 anytime-SSL-predictor 先例——early-exit 全在分类/判别 fine-tune，没人在 JEPA latent-regression predictor 位做早退 → ②牌空白确认，写入 related work。
- **②anytime 升一等指标**（03_pilot 新 §9.1）：stability-vs-anytime trade-off。Q(k) 曲线族（多 L_f/SN 强度 + A0+ 同台）+ anytime-gain(Q8/Q64) vs stability-margin(1−L_f) 散点。理论根 Bassily 2018（1804.01619「收敛快⇄稳定差」）+ DEQ Bai 2019（1909.01377 收缩-表达张力）。02 新增**性质 4.2**（稳定化压缩 anytime 有效区间 k*，🟡）。
- **诚实预案**：测出「稳定区 anytime 无意义」也是可发表负结果（best-compromise S），不藏。阈值（gain≥0.85/<0.7）标工程 go/no-go 非论文 claim。
- **口径修正**：01 §四②行「ViT 结构上做不到」→「默认全或无，加早退头可 anytime 但需额外 head+loss 且 SSL predictor 位无先例」；Q(k)=cosine（latent regression）非分割 Dice。
- 落档：03_pilot §5/§9.1/§14 + 01 §七/§八/§十三/§十五 + 02 §4.1/§7/§8 + registry(a0plus 臂/Gate3)。
- **3 TODO 已查清（红线10，researcher 第 3 派）**：① loss-weight 全程等权 w=1（MSDNet 正文+源码硬编码，无变体）；② exit-head=LayerNorm+Linear（MeViT MLP-EE 退化版 + I-JEPA predictor_proj）；③ stop-grad 全回传（I-JEPA/MSDNet/MeViT 三源一致，predictor 内无 detach），stop-grad 变体留 Phase1 实测。**官方默认与代码骨架完全吻合，零返工**。
- **A0+ 代码已落地**：`ijepa/src/models/earlyexit_vit_predictor.py`（`EarlyExitViTPredictor`：训练返回各 exit list、推理 `exit_layer=k` 单点）+ `helper.py` 分支 + `train.py` loss_fn list 等权 + config `a0plus_earlyexit_vit_vits_nih10k.yaml`。
- **评估工具链已落地（§9.1 一等指标产出）**：`nca_predictor.py` forward 加 `exit_step`（NCA 早退）+ **`eval_anytime.py`**（eval 模式出 Q(k) csv+曲线+L_f power iteration；aggregate 模式出 trade-off 主图曲线族+副图散点）。本地 CPU smoke 全通（`_scratch/smoke_a0plus.py` 6 项 + eval_anytime 双臂 + aggregate 图）。
- **参数实测核对**：A0=11.0M / A0+=11.76M(+6.7%) / NCA=3.22M；改了 4 处「A0+ 与 NCA 同量级」错述（NCA 实际省参 3.4×）。
- **工作报告**：`06_A0+_anytime_trade-off_落地_2026-06-16.md`（交付 + 完成度审计 + 继续命令）。
- **诚实缺口（见 06 §7）**：① 真数据 smoke + 训练未跑（待拍，串行红线）；② **SN 强度旋钮设计问题**——PyTorch spectral_norm 固定 σ→1 不能设目标 L_f，§9.1「扫 L_f」改用 nca_steps S∈{4,8,16,32} 当主旋钮 + L_f 实测，真扫 L_f 需另加约束机制（Phase1 开放项，不臆想）；③ hpc sbatch 加 a0plus 映射 + 多 S 配置待补。
- **本地真数据全链路 smoke 通过**（`_scratch/smoke_train_a0plus.py`，GPU）：真 MBMaskCollator + encoder + EMA + a0plus + loss list 等权 + backward + EMA，1 step 全过；A0+ 6 exit shape 全 == target；**等权 loss 初值 0.4796 ≈ A0 baseline 0.476**（job 1450052）→ 集成正确、真训练会健康。`hpc/sbatch_pilot.sh` 加 a0plus 映射。
- **✅ HPC 真数据 smoke 通过**（用户选项落地）：VPN 通 → 推 7 文件（earlyexit/nca/helper/train/config/sbatch/eval_anytime）→ HPC import 链 OK → login CPU 真 NIH 全链路 smoke `loss=0.4796`（与本地一致，≈A0 baseline 0.476），rc=0。`_scratch/_hpc_push_a0plus.py` 一键推+smoke。
- **✅ A0+ seed42 首训健康完成**（job 1450845，持 training.lock→完删）：sacct COMPLETED ExitCode 0:0，跑满 50ep，avg loss 0.088（6-exit 等权均值，浅层拉高，正常），VERDICT HEALTHY，无报错。31min（比 A0 16min 慢=6 exit 多反传）。
- **✅ A0+ anytime 真信号**（eval_anytime on jepa-ep50，ckpt 载入 missing=0）：Q(k)=0.975/0.986/0.992/0.994/0.997/1.000（k=1..6），**单调上升=anytime 有效**（合 Jazbec conditional monotonicity）；anytime-gain Q(4)/Q(6)=0.994。csv `results/anytime_a0plus_s42.csv`（已核）。
- **⚠️ 战略洞察（诚实）**：A0+ **Q(1)=0.975 已极高 → ViT early-exit 几乎无损、anytime 动态范围窄**。即「ViT 也能 early-exit 且本任务几乎完美」——②牌压力实锤。NCA 要赢不能靠「anytime 更准」，得差异化（稳定性维度 / 更激进早退 / 省参下的 anytime）。这正是 §9.1 trade-off 要诚实呈现的，须 A1/A2 的 Q(k) 同台才完整。
- **下一步**：拍 A1/A2 训练（NCA 臂，待用户「跑」）→ 各自 eval_anytime Q(k) → aggregate 出 trade-off 图（A0+ 基准线已就位）→ 看 NCA 动态范围 vs A0+ → Gate1/3。


- **5 路并行探路**（4 researcher sonnet + 1 reviewer opus，组合台系统首次实战）→ 报告 `05_探路_2026-06-16.md`。
- **致命发现**：①稳定区=anytime 最弱区（trade-off 须升 pilot 一等指标）②三张牌打 ViT 稻草人（缺 early-exit ViT 对照臂 A0+）③Kvalsund&Stovold 2026（2604.12720）实证 NCA 振荡吸引子非固定点（须主动引区隔）④resilience MICCAI 2026 占④不确定性牌；RadJEPA 2026-01 占医学 JEPA（ViT predictor）；NCA-as-SSL-predictor 仍全网空白。
- **venue**：NeurIPS 2026 已过；ICLR 2027 ~9 月（主线 3 月冲刺）；MICCAI 2027 ~2 月（退路 C）。2027 CFP 未出盯官网。
- **超参**：5/6 官方源，deterministic 自创已正确标；nca_steps=16 加 ablation {8,16,32}。
- **✅ 安全修正落地**（caveman off 精修）：01/02/README「可证稳定」→「稳定性可分析可控」；02「定理 6.1」→「性质 6.1」🟢→🟡（无证明不叫定理）；02 §5.1(b) 上界冒等式 → 标 🟡「至多…需实测」；02 加 Kvalsund 防御注（像素 vs latent）；01 加 RadJEPA related-work 行；03_pilot 头 A0 状态统一（A0 done / A1A2 pending）。
- **待用户拍的大 framing 决策（未动）**：加 A0+ early-exit ViT 对照臂 + stability-vs-anytime trade-off 升一等指标。
- 系统：teams flag 开 + /paper-scout skill 建；自定义 agent/team 需**重启 CC** 激活。本轮产出未 commit（待收工）。

## 2026-06-16 — 实验阶段启 + HPC 部署验通
- 地基搭建完：`facebookresearch/ijepa` 集成 + NCA predictor + 8 哨兵；smoke 全过。
- HPC 全量部署验通：`/gpfs/work/bio/jiayu2403/nca-jepa/`，env `yjcu124py310`，NIH 112120 图全解压、pilot 10k 子集泄漏 0。
- 哨兵门 **7/8 PASS**（s4 边界非 bug）。
- **A0 baseline 训练健康跑通**：job 1450052，loss 0.476→0.056@ep10，50ep ~16min。
- 红线10 官方超参联网复核完成：`configs/PROVENANCE.md`（~90% 真 CheXWorld 官方值，偏差全有意/已澄清，A0 不需重训）。
- **下一步**：A0 训完 → Gate0 → A1/A2 多 seed。**待用户放行**（训练串行红线，HPC 提交主线亲自做）。

> 早于本日的复现+pilot 设计 entry 见 `../PROJECT_LOG.md`。
