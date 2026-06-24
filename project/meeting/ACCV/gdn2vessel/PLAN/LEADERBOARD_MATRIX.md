# benchmark-only 续连 leaderboard 实验矩阵（planner 2026-06-24）

> benchmark-only D&B 稿（Entry 32 拍板）。承重点 = 续连指标族 + 12 baseline 全谱 + 诊断方法学。**不复活 delta/Frangi 机制 claim**——ours_gdn2 只是 leaderboard 一行被评测方法。全链路代码今天建：`train_harness.py`（统一训练台）+ `evaluate.py --benchmark_dir`（断点评测出续连三轴）。

## ⚠️ 两处口径偏移（拍板点，到批2 命门时拍）
1. benchmark-only 后 leaderboard 卖「benchmark 能区分方法」**不卖「Ours 赢 SOTA」**——旧 ACCEPTANCE L6「Ours 拓扑/续连赢 SOTA」降为参照，Ours 输也不塌稿。
2. ACCEPTANCE 需补 benchmark-only 专属「区分度门」判据（skeptic 命门）。改判据方向=拍板点，不自创阈值。

## severity 策略：多 severity（Easy/Medium/Hard/Extreme）
- severity-response 曲线（续连率随断点 severity 衰减，不同方法斜率不同）= benchmark 判别轴 = D&B 难度旋钮。单 Medium 易挤一团撑不起稿。
- 训练按 (baseline×dataset×seed)；评测 ×4 severity 纯推理廉价，**不重训**。

## 数据集分层
| 层 | 集 | npz | split/n | 入批 |
|---|---|---|---|---|
| 核心 | DRIVE | ✅(manifest 16) | val n=20 | 批0/1 |
| 核心 | CHASE | ✅(manifest 32) | val n=8 | 批1 |
| 核心 | STARE | ⚠️待核 | 10/10 n=10 | 批2 |
| 核心 | FIVES | ⚠️待核(大集) | val n=200 | 批5 |
| 扩展 | HRF/冠脉/OCTA | ⚠️/❌ | — | 批6 加分 |

## 分批 rollout（先打通再批量，绝不裸铺全量）
| 批 | 范围 | 训练 run | GPU·h | 出口 gate |
|---|---|---|---|---|
| 批0 | FR-UNet×DRIVE×s42 烟测(job1489877) | 1(2ep) | <0.5 | 续连列非NaN+管道不碎 |
| 批1 | FR-UNet×{DRIVE,CHASE}×s42 正式(40ep官方) | 2 | 3-5 | 真链路通+校准GPU·h+三轴sane+csv 22列 |
| **批2** | {DRIVE,CHASE}×全main-venv baseline×s42 | ~14 | 25-35 | **命门：方法间区分度+severity曲线分得开?挤一团→停下报** |
| 批3 | +seed{1,2} 补std/CI | ~28 | ~50 | 3-seed std+bootstrap CI |
| 批4 | mamba系(vm_unet/mm_unet)×{DRIVE,CHASE}×3seed | ~12 | ~25 | mamba_venv build通 |
| 批5 | STARE+FIVES×全baseline×3seed | ~78 | 150-200 | npz齐+批2-3立住 |
| 批6 | nnUNet系+HRF+跨器官(加分) | ~30+ | 100+ | nnUNet桥接拍板 |

核心(批0-5)≈250-320 GPU·h；2-3卡并行(fmreg占1)墙钟~100-160卡·h，qos 7天分批消化。

## leaderboard 每 cell 列
- 轴1分割(sanity)：dice,iou,auc,se,sp
- 轴2拓扑：cldice,betti_b0/b1_err,skeleton_recall,topo_source
- 轴3续连(核心)：epsilon_beta0,success_rate,reid_rate,n_gaps
- 统计：3seed mean±std + per-image bootstrap 95%CI(手算numpy,禁scipy.stats=OMP红线)
- 审计：ckpt_path,eval_input_mode,threshold,git_commit,severity
- **关键**：ε_β0/SR/reid_rate 从 pred_mask+GT 算，**不需 re-ID 头→12 baseline 公平同台**。reid_rate_head 仅 ours 专属附加列(大图超seq_len记NaN双报,不污染主列)。

## 特殊 baseline
| baseline | venv | 跑法 | 批 | 降档 |
|---|---|---|---|---|
| vm_unet/mm_unet | mamba_venv | source build+关AMP(nan)+import烟测 | 批4 | mamba_vessel_net已降C |
| creatis_postproc | main | 两段式(Stage1分割+Stage2续连postproc),train_harness识别kind走两段(TODO确认入口) | 批2 | 续连唯一直接对手必跑 |
| nnunet/pasc_net/u_mamba | nnUNetv2命令行另路 | plan_preprocess→train→predict→桥接evaluate(TODO桥接+epoch限) | 批6 | 官方1000ep须限 |
| ours_gdn2 | main | 同台不开后门+reid_head专属列 | 批2 | 大图reid_head坑 |

## 前置 TODO
- SSH 核 STARE/FIVES/HRF benchmark npz 齐不齐（只确认 DRIVE16+CHASE32）→定批5。
- researcher 补 BASELINE_SPEC §1 剩余官方超参 TODO(csnet RandEnhance/dscnet MONAI prob/vm_unet normalize),禁臆想。
- 拍板：nnUNet桥接方案+epoch限；creatis 两段式 harness 入口；ACCEPTANCE 补区分度门+L6降参照。
- 复现纪律：held-out(DRIVE val37-40 vs train21-36不重叠)+官方超参禁改+数字Bash核csv+某baseline复现Dice低>2-3点标差距不当胜利。

## 交接
coder=creatis两段式入口+benchmark×4severity批量脚本+nnUNet桥接 | researcher=补超参TODO | 主线串行=gpu_slot分批 | analyst=批1三轴sane/批2区分度命门/全量出表+衰减曲线 | verifier=核22列+topo_source同值+复现差距
