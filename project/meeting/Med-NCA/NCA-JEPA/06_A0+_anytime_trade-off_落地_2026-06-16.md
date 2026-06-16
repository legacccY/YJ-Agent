# NCA-JEPA — A0+ 对照臂 + stability-vs-anytime trade-off 落地报告（2026-06-16）

> 本报告 = 探路报告 `05_` 列的两大 framing 决策（致命伤①②）的执行交付 + 完成度审计 + 继续做下去的交接。
> 配套读：`03_pilot §5/§9.1`（执行计划）、`01 §七/§十五`（叙事）、`02 §4.1`（理论）、`registry.json`（臂/门）。
> 数字均 Bash/Grep 核（参数 init_model 实测，非心算）；超参均查官方源（researcher 3 派，URL 见 `05_` + 本文）。

---

## 一句话

给 pilot 加了「努力过的 ViT」early-exit 对照臂 **A0+**，并把 **stability-vs-anytime trade-off** 从纸面升级为可产出的一等指标——predictor 早退接口 + 评估工具链 + 画图全部落地、本地 smoke 验通；**但真数据训练未跑（待用户拍），且有一个 SN 强度旋钮的设计问题需在 Phase 1 解决**（见 §7）。

---

## 1. 本轮交付（三块）

| 块 | 内容 | 状态 |
|---|---|---|
| **A** framing 文档 | `03/01/02/registry/04_LOG` 加 A0+ 臂 + §9.1 trade-off 一等指标 + 性质 4.2 + 审稿对峙 | ✅ |
| **B** A0+ 代码 | `earlyexit_vit_predictor.py` + helper/train 接入 + config | ✅ 本地 smoke 通 |
| **C** 评估工具链 | NCA 早退接口 + `eval_anytime.py`（Q(k)+L_f+trade-off 图） | ✅ 本地 smoke 通 |

---

## 2. A0+ 臂设计（官方依据，红线 10 已查清）

**A0+ = N 层 ViT predictor，每层接独立早退头（LayerNorm + Linear），各 exit 等权聚合。** 第 k 层即输出预测特征 ĥ_y^(k)，与 NCA 第 k 步同台测 anytime。

| 参数 | 取值 | 官方源 |
|---|---|---|
| loss-weight | 全程等权 w=1 | MSDNet 正文「losses of all classifiers are weighted equally」+ Lua 源码硬编码（arXiv:1703.09844 / gaohuang/MSDNet）；无递增/递减变体 |
| exit-head | LayerNorm + Linear(pred_emb→enc_emb) | MeViT MLP-EE 退化版（arXiv:2106.15183）+ I-JEPA `predictor_proj`；7 种 head 无专为 SSL regression 设计者 |
| stop-grad | 默认全回传（`exit_stop_grad=false`） | I-JEPA / MSDNet / MeViT 三源一致，predictor 内无 detach；stop-grad 变体留 Phase 1 实测 |
| loss 函数 | smooth_l1（跟随 I-JEPA，全臂一致） | I-JEPA `train.py` |

**意外强 novelty**：全网零 anytime-SSL-predictor 先例——early-exit 全在分类/判别 fine-tune，没人在 JEPA latent-regression predictor 位做早退。即「ViT 也能 early-exit」攻击本身亦无先例，A0+ 是我们自建的诚实对手（写入 related work + §十五对峙）。

---

## 3. stability-vs-anytime trade-off（一等指标，§9.1）

**矛盾（reviewer 致命伤①）**：稳定化（SN 约束 L_f、小步数 S）使系统几步收敛 → 稳定区恰是 anytime 最弱区。

**指标定义**（红线：Q 是 latent regression 的 cosine，**不是分割 Dice**）：
- `Q(k) = cos(ĥ_y^(k), ĥ_y^(S))` 第 k 步/层 vs 满步预测的自洽性。
- `anytime-gain = Q(k_early)/Q(S)`；`stability-margin = 1 − L_f`（L_f = NCA cell Jacobian 谱半径，power iteration 实测；A0+/ViT 无此量标 NaN）。

**理论根**（性质 4.2，02 §4.1）：Bassily 2018「收敛快⇄稳定差」（1804.01619）+ DEQ 收缩-表达张力（1909.01377）。

**产出工具** `eval_anytime.py` 两模式：
- `eval`：单 ckpt → Q(k) csv + 单配置曲线图 + L_f。
- `aggregate`：多 csv → 主图（Q(k) 曲线族）+ 副图（anytime-gain vs stability-margin 散点，带 0.85/0.70 阈值线）。

**阈值**（工程 go/no-go，非论文 claim）：某 L_f≤0.9 配置 gain≥0.85 → 共存成立；全部 <0.70 → 诚实报互斥 + best-compromise S（可发表负结果）。

---

## 4. 参数实测（init_model 核，非心算）

| 臂 | predictor 参数 | vs A0 |
|---|---|---|
| A0（vit） | 11,018,880 | — |
| **A0+（earlyexit_vit）** | **11,761,920** | **+6.7%（6 个 norm+Linear 早退头）** |
| A2（scp_nca） | 3,223,040 | −71%（省参 3.4×） |

**诚实修正**：落档初稿写「A0+ 与 NCA 同量级」**错**——NCA 省参 3.4 倍。正确论点：A0+≈A0 同 ViT 量级 → anytime 公平对照；NCA 用 1/3.4 参数仍 anytime = 省参加分。

---

## 5. smoke 验证（本地，含真数据 GPU 全链路）

- **`_scratch/smoke_train_a0plus.py`（真 NIH 数据 + GPU 全链路，最强证据）**：真 `MBMaskCollator`（nenc=1/npred=4，enc_keep=67/pred_keep=36）+ encoder + EMA target + a0plus predictor + loss list 等权 + backward + EMA 更新，1 step 全过。A0+ 6 个 exit shape `(16,36,384)` **全 == target h**；**等权 loss 初值 0.4796 ≈ A0 baseline 初值 0.476**（job 1450052），强证集成正确、真训练会健康；主干第 1 层梯度 |sum|=13.4（全回传工作）。
- `_scratch/smoke_a0plus.py`（单元）：6 项全过（构造 / forward list(6 exit) / exit_layer 单点 / 等权 loss+backward / stop-grad 主干仍训 / 参数对比）。
- `eval_anytime.py eval --smoke`：NCA 臂（exit_step + L_f power iteration，L_f=1.000=SN 压谱半径到 1，符合命题 1.1）+ A0+ 臂（exit_layer + Q(k)）均跑通出 csv。
- `eval_anytime.py aggregate`：trade-off 主图+副图 png 生成（图 label 已英文化，避中文字体豆腐块）。

> 单元 smoke（`--smoke`）用随机权重数值无意义；但**全链路 train smoke 用真数据真权重，loss 初值对齐 A0**，是「A0+ 真能训」的实证。HPC 侧只需上传新代码复跑确认（等 VPN）。

---

## 6. 完成度审计（诚实）

| 项 | 状态 |
|---|---|
| framing 文档（A0+ + trade-off 升级） | ✅ |
| A0+ predictor 代码 + 接入 | ✅ 本地 smoke |
| NCA 早退接口（exit_step） | ✅ |
| 评估工具 eval_anytime（Q(k)+L_f+图） | ✅ 本地 smoke |
| 参数实测核对 | ✅ |
| **真数据全链路 smoke** | ✅ 本地 GPU + **✅ HPC login CPU**（`smoke_train_a0plus.py`，两侧 loss 初值均 0.4796≈A0；HPC import 链 + 7 文件已上传，rc=0） |
| **A0/A0+/A1/A2 训练** | ❌ 待用户拍（串行红线，代码已就绪可 sbatch） |
| **SN 强度可调旋钮**（扫不同 L_f） | ❌ 设计问题未解，见 §7 |
| **trade-off 真图（训练后）** | ❌ 依赖训练 |

---

## 7. 怎么继续做下去（交接）

### 已知设计问题（必须 Phase 1 解决）
§9.1 写「扫 L_f∈{0.5,0.7,0.9,1.0} 画多条线」，但 **PyTorch `spectral_norm` 把每层 σ 固定归一到 1，不能直接设目标 L_f**。可行替代旋钮：
- **主旋钮 = `nca_steps` S∈{4,8,16,32}**（config 现成可调，各训一个 ckpt）。
- **L_f 当 x 轴用 `eval_anytime` 的 power iteration 实测**（不预设、不臆想）。
- 若要真正扫不同 L_f，需另加 Lipschitz 约束系数机制（非 PyTorch 原生 SN）——这是 Phase 1 的开放实现项，**不要臆想填**。

### 继续命令（训练待用户拍）
```bash
# 1. 真数据 smoke（HPC，1 step 验集成，非训练）—— 跑 A0+ config 确认 dataloader+loss 不报错
# 2. 训练（持 training.lock，串行）：A0+ 与 A0/A1/A2 同协议
sbatch --export=ALL,ARM=a0plus,SEED=42 hpc/sbatch_pilot.sh   # 需在 sbatch 脚本加 a0plus config 映射
# 3. 训完评估 anytime（每个 ckpt + 每个 S 配置各一次）：
python eval_anytime.py eval --config configs/a2_scp_nca_vits_nih10k.yaml \
       --ckpt checkpoints/a2_seed42/last.pth.tar --out results/anytime_a2_S16_s42.csv
python eval_anytime.py eval --config configs/a0plus_earlyexit_vit_vits_nih10k.yaml \
       --ckpt checkpoints/a0plus_seed42/last.pth.tar --out results/anytime_a0plus_s42.csv
# 4. 汇总出 trade-off 一等图：
python eval_anytime.py aggregate --glob "results/anytime_*.csv" --out-fig results/tradeoff.png
```

### 还需补的小件
- `hpc/sbatch_pilot.sh` 加 `a0plus` → config 映射（现只映 a0/a1/a2）。
- 多 S 配置文件（a2_S4 / a2_S8 / a2_S32 …）= 复制 a2 改 `nca_steps`，扫 trade-off 用。

---

## 8. 本轮文件清单

**新建**：
- `ijepa/src/models/earlyexit_vit_predictor.py` — A0+ predictor
- `configs/a0plus_earlyexit_vit_vits_nih10k.yaml` — A0+ config
- `eval_anytime.py` — anytime×stability trade-off 评估工具（§9.1 产出）
- `06_A0+_anytime_trade-off_落地_2026-06-16.md` — 本报告
- `_scratch/smoke_a0plus.py` — A0+ 单元 smoke（探针，免登记）

**改动**：
- `ijepa/src/models/nca_predictor.py` — forward 加 `exit_step`（NCA 早退）
- `ijepa/src/helper.py` — `earlyexit_vit` 分支 + `exit_stop_grad`
- `ijepa/src/train.py` — `loss_fn` list 等权聚合 + 读 `exit_stop_grad`
- `03_pilot / 01 / 02 / registry / 04_LOG` — framing 落档

**未 commit**（待用户说收工/commit）。
