# Phase1 A′ 受控重训实验矩阵（planner 定稿 2026-06-30）

> 服务 C1（主）+C2/C3/C4 承重 / lever=Phase1 A′ 混合受控。对齐 02_ACCEPTANCE。
> 超参真源 = `reference/SSL_RECIPES.md`；TODO 处禁臆想（R4）。

## 1. 预算对齐（A′ 核心）
- **主控轴 = images-seen = Σ(steps×global_batch)**，4 SSL 范式严格相等，**不计 crop/view 数**（multi-crop 是方法构成要素归方法不归预算）。
- `images-seen = E_eq × N`（N=112120）。**E_eq=100 → B=11.21M 源图**。对齐源图曝光（非含糊 epoch）。⚠️ tex 措辞诚实：写「采用 source-exposure 对齐并报全三轴」，**别写「公认协议」当铁律**（该系也有按 iteration 对齐的，无唯一标准）。
- **🆕(skeptic-1 最高杠杆) 中间预算 checkpoint probing**：每预训练 run 在 25/50/100/[200] eff-ep 各存 ckpt + 跑 linear-probe@10%（已训过这些步，存盘近零成本）。一举解决三攻击：①probe-vs-budget 曲线证 C1 排名对预算稳定（杀 transient 批评）②看排名在 GPU·h-matched 点会不会翻（杀 DINO multi-crop 偷喂 10× 算力批评）③把「上调」改成**预登记平台判据**（loss 斜率<ε 或 probe 饱和则停，迭代到平台、按预算封顶）取代拍死 200。
- **防 HARKing 调整规则（改）**：E_eq 按上述平台判据迭代，未平台则全 4 范式**统一**上调（绝不按范式单调），预登记停止条件，LOG 留痕。
- **🆕(skeptic 预算轴硬约束) 全三轴预算表**：每范式报 images-seen / steps / GPU·h / view-instances 四列；至少对 outlier(DINO) 报一个 GPU·h 或 iteration-matched 预算点的敏感性 probe，证「C1 排名不因预算轴选择翻转」。蹭中间 ckpt 不另烧算力。

| 范式 | 官方 eff_bs | lr(官方@eff_bs,不 rescale) | steps@100ep | warmup | 来源 |
|---|---|---|---|---|---|
| MAE | 4096 | 2.4e-3 (blr1.5e-4×4096/256) | 2737 | 5ep | SSL_RECIPES §1, mask 0.90/norm_pix |
| MoCo-v3 | 4096 | **1.0e-4**(论文更稳) | 2737 | 13ep | §3 + TODO-B, stop-grad-conv1 必开 |
| DINO v1 | 512 | 0.00075 | 21898 | 10ep/temp warmup 12.5ep | §2, **fp16=off** |
| CheXWorld | **2048**(128×accum2×8gpu) | **2e-4 绝对**(min_lr 1e-6) | **5474**(11.21M/2048) | 40ep | ✅SSL_RECIPES §4, ssl_type iwm_dual_easy/ema 0.996→1.0/mask multi_multiblock; `--dataset nih` 单库; HPC accum_iter 凑 eff_bs=2048 |

> 同 images-seen 11.21M 下 MAE/MoCo 跑 2737 步、DINO 跑 21898 步（步数差 8×=batch 差 8× 镜像），源图曝光相等，batch 不动官方值。
> 次级透明项(只记录)：encoder view-instances(MAE~0.1× / MoCo~2× / DINO~3.8×)、实际 GPU·h(烟测标定)。

### 🆕(2026-06-30 路A 拍板) reduced-batch + lr 线性缩放（硬件约束预登记，防 HARKing）
4×4090（24GB）装不下 DINO/MoCo 官方 per-GPU batch：DINO 官方 eff_bs=512=16卡×32、MoCo=4096=64卡，单/4 卡达不到。**预登记走 reduced-batch + lr 线性缩放**（images-seen 不变，仅 eff_bs 降）：
- **MAE/CheXWorld**：accum 凑满官方 eff_bs(4096/2048)，**lr 不缩放**。
- **DINO/MoCo（reduced）**：用 4090 可容 per-GPU batch（DINO 官方 32/卡、MoCo 烟测标定~128/卡），eff_bs=BPG×GPUS（<官方）；**lr 按线性规则缩放 lr_scaled=official_lr×eff/official_eff_bs**（DINO 0.00075@512、MoCo 1e-4@4096 为锚），每次缩放 stderr 留痕。
- 与 A′ 哲学自洽：eff_bs 本就是「方法构成要素、放开不强对齐」，images-seen 才是主控轴。
- 诚实 limitation（写 tex）：「受 4×4090 限制，DINO/MoCo 用 reduced eff_bs + 标准线性 lr 缩放；MAE/CheXWorld accum 凑满官方」。这是 solo-learn/VISSL 有限算力横评标准做法，非疏漏。
- 烟测顺便标定 4090 单卡可容 BPG（OOM 则降 BPG_CAP env）。

## 2. Collapse 烟测（投全预算前强制，ACCEPTANCE Phase1 前置）
DINO/MoCo 必烟测(collapse)+标定 imgs/sec。**🆕(skeptic-3) MAE+CheX 也加廉价 loss-sanity 烟测 gate**（同量级、少 collapse 监控）——接住「官方高 lr(MAE 2.4e-3/CheX 2e-4 在大语料调) × 112k 小语料 × 8× 少步」未测 regime，预登记「loss 平台/无发散」PASS 再投全量，别让 130 GPU·h 裸跑。

| run | 范式 | 预算 | 监控量 | 健康判据(预登记) | 失败动作 |
|---|---|---|---|---|---|
| SMK-DINO | DINO | 10 eff-ep(2190步) | teacher 熵/KL/特征std/loss | 熵∈(0.3,0.95)×log(65536)不塌；std>0.01；loss 单调降；无NaN | 延 temp warmup/降lr/增 freeze_last_layer(官方缓解,不私调架构)→重烟测；仍塌→C后备公开权重标mismatch |
| SMK-MOCO | MoCo | 15 eff-ep(410步) | 对比loss vs ln(batch)/std/梯度范数/dip | loss<ln(batch)不卡平台；std>0.01；无dip/NaN；stop-grad-conv1开 | 降lr1e-4/减batch/确认fixed patch-proj→重烟测 |

- 监控每 50-100 步 dump `results/smoke_<method>.csv`(state.json 心跳)。
- **Gate**：双 PASS→解锁全量；任一塌且官方缓解无效→停报拍板(ACCEPTANCE Phase1 FAIL 退路:N/5 受控+余者公开权重标mismatch,不绑死5/5)。
- 2 卡并行,含队列 ~1 天。

## 3. 重训 run 表（4 SSL × 预训练 seed）
imagenet_sup/scratch floor 不耗预训练预算。

| run | 范式 | 预算 | seed | GPU·h/run | 判据 |
|---|---|---|---|---|---|
| PT-MAE-s{0,1,2} | MAE | 11.21M | 3 | ~2.5 | Phase1 PASS |
| PT-DINO-s{0,1,2} | DINO | 11.21M | 3 | ~25(multi-crop 最贵) | Phase1 PASS |
| PT-MOCO-s{0,1,2} | MoCo | 11.21M | 3 | ~7 | Phase1 PASS |
| PT-CHEX-s{0,1,2} | CheXWorld | B(TODO-A) | 3 | ~9 | Phase1 PASS |

**两层 seed**：预训练 seed(贵,控 C1 排名真实性)=3×4=12 job；probe/finetune seed(廉,控 head init+子集重采样)见 §4。
**组合边界(防 nested 失控)**：主网格=预训练 seed-0×全 probe-seed sweep；预训练方差=3 预训练 seed×probe-seed-0。拼 CI 不全交叉。
**🆕(skeptic-2) C1 headline 排名在 3 个 PT-seed 都算**（哪怕只 probe-seed-0）+报 3-seed 排名 spread，别把 headline CI 建在单 PT-seed-0+probe-init。预登记「PT-seed 方差是 C1 主不确定源」。⚠️ n=3 **不挂 p<0.05 范式优越硬 claim**，描述性报排名+spread；排名跨 PT-seed 翻转本身就是 C1 向 a/向 b 证据，不亏。
**fallback**：gpu4090 堵致 DINO 超墙钟→统一降 DINO 2 seed(预登记非事后挑)。

## 4. 评估矩阵（对齐 C1-C4）
网格={linear,attentive,knn,finetune}×{1%,10%,100%}×{NIH in-domain,NIH→VinDr}×seed×6 backbone(4SSL+imagenet_sup+scratch)。复用 code/probes.py+run_finetune.py+extract_features.py。

| probe | seed(per backbone,frac) | 服务判据 |
|---|---|---|
| linear | 5@1%,5@10%,3@100% | C1/C2/C3/C4 |
| attentive(TODO-D:DINOv2-eval MHA pooling) | 5@1%,5@10%,3@100% | C1/C3 |
| knn(k=20 DINO默认) | 3@各frac | C1 |
| finetune(全解冻,贵) | 3@1%,2@10%,2@100% | C2/C3/C4 |

- C1 双向预登记(已冻结于此刻):洗牌存活=regime依赖/消失=语料artifact,两向 publishable,不依赖强制rank flip。Friedman+Nemenyi CD。
- C2:mAUC vs frac 极差 1%>100%。1% 端 5seed×子集重采样配足。
- C3:CheXWorld linear排名<finetune排名。需 linear+attentive+finetune matched frac 齐。
- C4:每 backbone VinDr-train 训 probe、VinDr-test 评(患者disjoint,R5),共享类比 ΔmAUC。TODO-E:NIH∩VinDr ~10-11类终表重训前冻。VinDr 标签已落 data/external/vindr_cxr/labels/(train 45001行需按image_id聚合3放射师)。

## 5. 依赖 DAG
```
Stage0 烟测  SMK-DINO ‖ SMK-MOCO (2卡,~1天)
  │ Gate 双PASS
Stage1 预训练 PT-MAE×3 ‖ PT-DINO×3 ‖ PT-MOCO×3 ‖ PT-CHEX×3 (4卡,DINO/MoCo受gate;MAE/CheX可与烟测并发)
  │ 每ckpt落盘触发下游
Stage2 特征抽取(廉,跟各PT后)
Stage3 probe linear/attentive/knn(廉,大并行) ‖ Stage4 finetune(贵,跟PT后) ‖ Stage5 跨域VinDr
  │ 全评估矩阵C1-C4齐
Stage6 ★冻结 failure-cell→reference/FAILURE_CELLS_FROZEN.md(R6) →(Phase3方法,本设计不含)
```
关键路径=SMK-DINO(~1天)→PT-DINO(最贵~25h×3)→DINO finetune→分析。**墙钟估 8-12 天**(4卡+队列)。

## 6. 算力预估（待烟测标定,MAE=1×基准）
| 模块 | GPU·h |
|---|---|
| Stage0 烟测 | ~6 |
| Stage1 预训练(3seed×4) | ~130(DINO~75占大头) |
| Stage3 linear/attentive/knn | ~40 |
| Stage4 finetune | ~200 |
| Stage5 跨域 | ~80 |
| **合计** | **~450-600**(<plan原估1000;4卡墙钟8-12天) |

## 7. 前置 TODO（coder 起前必补）
- ✅ **TODO-A 已解**:CheXWorld 官方 PRETRAIN 配方在本地 `repo/PRETRAIN.md`(eff_bs2048/300ep/lr2e-4绝对/AdamW/ema0.996→1.0/mask multi_multiblock,零缺失),回填 SSL_RECIPES §4。`--dataset nih` 单库,HPC accum_iter 凑 eff_bs=2048。C3 不塌。
- ✅ **TODO-B 已查**:MoCo-v3 112k单库CXR **无公开先例**→须烟测定 batch/lr(减batch按线性缩放降lr);DINO collapse 官方默认+小语料缓解候选已落 SSL_RECIPES §6,强依赖 SMK-DINO 烟测。
- 🟠 TODO-C:单NIH 112k收敛E_eq无先例→烟测+早期曲线确认(规则已定)。
- 🟡 TODO-D:attentive头规格(DINOv2-eval标准MHA pooling)。
- 🟡 TODO-E:NIH∩VinDr共享类终表(~10-11类)重训前冻+VinDr train按image_id聚合。
- ⚠️ 拍板点:HPC上传新代码=对外先报。
- 🟡 主线复核:images-seen对齐 vs GPU·h对齐取舍(本设计选images-seen主控,理由更抗审稿;DINO multi-crop吃~10×GPU·h是已知代价)。

## 8. 交接
researcher补TODO-A/B→回填SSL_RECIPES → coder扩写code/(4范式预训练+collapse监控+评估网格+submit) → 主线gpu_slot跑烟测→gate→全量。
