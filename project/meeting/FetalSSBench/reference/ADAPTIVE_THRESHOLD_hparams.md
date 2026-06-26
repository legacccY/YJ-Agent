# 自适应置信阈值 — 官方超参 + 公式真源（Phase 3 实现依据）

> 来源：researcher 联网核官方 repo + paper（2026-06-25）。**已核源码的直接用，标 TODO 的动手前必补，绝不臆造（守 R3/R5）。**
> 服务：FetalSSBench Phase 3（自适应阈值 = 核心贡献之二）。贡献定位 = 在跨结构难度 benchmark 上**系统验证已有自适应阈值机制兑现规律3 的难度不对称预测**，不 claim 新阈值机制 novelty。

---

## 1. FreeMatch（ICLR 2023, arXiv:2205.07246）— Phase 3 自适应主力

**全局阈值 EMA 更新**（USB 官方 `semilearn/algorithms/freematch/utils.py` — FreeMatchThresholingHook 核实）：
```python
# 初始 time_p = 1/num_classes
time_p = m * time_p + (1 - m) * max_probs.mean()
```

**局部类别阈值**：
```python
mod = p_model / torch.max(p_model, dim=-1)[0]   # p_model 初始 = uniform(1/C)，EMA 维护
mask = max_probs.ge(time_p * mod[max_idx])       # 类 c 阈值 = time_p * mod[c]
```

**SAF 自适应公平正则**（官方源码核实）：
```python
# mod_prob_model = EMA类别分布 × label_hist逆权重（归一化）
# mod_mean_prob_s = 强增强预测均值 × 预测分布逆权重（归一化）
loss_ent = mod_prob_model * log(mod_mean_prob_s + 1e-12)
total_loss = sup_loss + lambda_u * unsup_loss + lambda_e * ent_loss
```

**默认超参**：
- EMA 动量 m = **0.999**（USB `--ema_p 0.999`）
- p_model / label_hist 初始 = uniform(1/C)
- lambda_e（SAF 权重）= **TODO**：查 USB freematch.py 完整 argparse 默认值，未确认前不写死

**官方 repo**：https://github.com/microsoft/Semi-supervised-learning（`semilearn/algorithms/freematch/`）

**→ Phase 3 怎么用**：直接替换 SSL4MIS FixMatch-Seg 的固定 `conf_thresh=0.8` 为 FreeMatch 全局+局部类别阈值。PS(难/小结构) 的 `mod[c]` 自动更低 → 阈值更低 → 放更多伪标签进来 = 正打规律3 痛点（难结构低标注区）。

---

## 2. FlexMatch（NeurIPS 2021, arXiv:2110.08263）— G5 消融备选

**学习状态**（公式 5）：`σ_t(c) = Σ_n 1[max p(y|u_n) > τ] · 1[argmax = c]`
**灵活阈值**（公式 6-7）：`β_t(c) = σ_t(c) / max_c{σ_t}`；`T_t(c) = β_t(c) · τ`
**Warmup**（公式 11）：`β_t(c) = σ_t(c) / max{max_c σ_t, N − Σ_c σ_t(c)}`
**非线性映射**（公式 12）：`M(x) = x / (2 − x)`（单调递增凸）

**TorchSSL 默认**（官方代码核实）：p_cutoff(τ) = **0.95**（CIFAR/STL/SVHN）/ 0.7（ImageNet）；ema_m = **0.999**；T = 0.5；hard_label = True
**官方 repo**：https://github.com/TorchSSL/TorchSSL

---

## 3. 分割任务适配（关键 — 分类→分割的改造点）

**核心问题（文献明确）**：像素类不平衡 → 少数类 σ_t(c) 极低 → 类别阈值极低 → 低质伪标签塌缩。

**SSL4MIS FixMatch-Seg 基线阈值**（官方 `train_fixmatch_standard_augs.py` 核实）：
```python
parser.add_argument("--conf_thresh", type=float, default=0.8)   # 固定 0.8，全局单阈值不分类别
pseudo_mask = (normalize(outputs_weak_soft) > args.conf_thresh).float()
```

**Phase 3 实现要点**：
- FreeMatch `mod[c] = p_model[c]/max(p_model)` 的类别缩放因子逐像素按最大类别应用
- `σ_t(c)` 分母从「图数」改「像素数」，防 background 淹没 foreground 估计
- FreeMatch SAF 可直接用（像素粒度预测分布）

**待补 TODO**：
- nnFilterMatch(arXiv:2509.19746) 类自适应细节 — HTML 404，动手前重抓或读 PDF
- Dense FixMatch(arXiv:2210.09919) 分割阈值默认 — PDF 未解析，动手前补

---

## 4. 撞车防御（总风险低）

| 论文 | 用概率自适应阈值? | 撞车 |
|---|---|---|
| FUGC (2601.15572) | 否，benchmark 论文，参赛队无人用 FreeMatch/FlexMatch | 低 |
| HDC (CVPR25, 2504.09876) | 否，Correlation Guidance + MI Loss | 低 |
| DSTCT (MICCAI24, 2409.06928) | 否，argmax 硬标签 + 温度 τ=0.1 sharpening | 低 |
| ERSR (JBHI25, 2508.19815) | **不同范式**：几何 dual-scoring(Sobel/Laplacian+Top-K)，非概率置信阈值 | 中低 |

**区分点**：四篇均未实现 FreeMatch/FlexMatch 式概率置信自适应阈值。ERSR 的几何 scoring 须在 Related Work 明确区分（**几何先验 vs 概率自适应是两种范式**）。我们的 claim 是「跨结构难度 benchmark 上系统验证自适应阈值兑现难度不对称预测」= 实证测量 claim，无撞车。

---

## 已核源码 URL
- USB FreeMatch: https://github.com/microsoft/Semi-supervised-learning/blob/main/semilearn/algorithms/freematch/freematch.py
- USB FreeMatch utils: https://github.com/microsoft/Semi-supervised-learning/blob/main/semilearn/algorithms/freematch/utils.py
- TorchSSL FlexMatch: https://github.com/TorchSSL/TorchSSL/blob/main/flexmatch.py
- FlexMatch 公式: https://ar5iv.labs.arxiv.org/html/2110.08263
- SSL4MIS FixMatch-seg: https://github.com/HiLab-git/SSL4MIS/blob/master/code/train_fixmatch_standard_augs.py

## 动手前必清 TODO（3 项）
1. FreeMatch `lambda_e` 默认值 → USB freematch.py argparse
2. nnFilterMatch 类自适应机制 → arXiv:2509.19746 重抓
3. Dense FixMatch 分割阈值 → arXiv:2210.09919 PDF
