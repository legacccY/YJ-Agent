# G6 立项卡 — run-002 医学影像·方法创新型

> 选题工业流水线终点。G5 杀手锏把 7 个候选证伪到只剩 1 个。本卡是**立项拍板材料**（新项目立项 = 拍板点），呈 legacccy 决定立项与否。
> 数字均经 verifier 核 csv 自洽（2026-06-17，6 个 killshot csv 无 drift）。

---

## 一、漏斗终局

| 闸 | 入 → 出 | 通过率 |
|---|---|---|
| G1 批量产出 | 116 raw → 73 live | 63% |
| G2 机器硬筛 | 73 → 22 | 30% |
| G3 评分排序 | 22 → 8 | 36% |
| G4 红队 | 8 → 7 | 88% |
| **G5 杀手锏** | **7 → 1** | **14%** |
| **G6 立项** | **1 单苗待拍板** | — |

**杀手锏死亡率 6/7**——这是 `/ideate` 流水线的设计预期（立项前用 <1GPU·h 证伪「大胆 claim」，而非立项后翻车烧掉数周中训）。S2-03 是唯一扛过先验生死闸的候选。

---

## 二、唯一存活候选 = S2-03（flow-matching 跨模态可变形配准）

| 字段 | 内容 |
|---|---|
| **one-liner** | flow-matching（OT-Flow）直线流形变场做跨模态/单模态可变形医学图像配准，少步逼近 diffusion 配准精度 |
| **problem** | diffusion 配准（DiffuseMorph 类）需多步采样、推理慢；FM 直线传输可少步；跨/单模态形变配准需拓扑合法（雅可比正）。对手 = VoxelMorph / TransMorph（无 FM）、DiffuseMorph（多步慢） |
| **why-new** | FM 用于图像**合成**已多，迁移到「形变场 = flow target」的**配准**范畴尚空白 |
| **双 venue** | top：MICCAI 2026 / CVPR 2026 ｜ fallback：MedIA / TMLR |
| **datasets** | BraTS2021（本机 ready）、OASIS（需下，killshot 已用 2D 切片）、可选 Learn2Reg / NLST CT |
| **compute** | ~80 GPU·h（HPC gpu4090 可承） |

### G5 杀手锏实证（雅可比闸 → 🟢 GREEN PASS）
`results/killshot_s2_03_jacobian.csv`：
```
neg_jac_pct = 0.0000   (零拓扑折叠)
dice_fm     = 0.9279  >  dice_affine = 0.8384
```
OASIS 20 对 2D 脑切片，极简 FM 单步 Euler 积分形变场 φ。skeptic 在 G4 提的 🔴「FM velocity ≠ 合法 diffeomorphism 形变场，范畴塌」**快测不成立**：单步形变 0% 负雅可比 + 胜仿射基线。

### ⚠️ 诚实 caveat（立项前须知）
1. **killshot 用简化 FM target 代理**。关键的「几何雅可比属性」已干净验证，但完整 velocity→diffeomorphism 的理论保证（LDDMM/测地线层面）待中训证。skeptic 对此置信中等，建议立项后第一件事补几何配准理论复核。
2. **单苗风险**：G5 只剩这 1 个，没有第二存活候选对冲。若中训发现塌方，本轮 run-002 归零。

---

## 三、书面 kill criteria（立项即生效，触发即诚实回退）

- **K1（拓扑）**：完整 FM 配准在 OASIS / Learn2Reg **held-out** 上 `neg_jac_pct > 5%` 或 Dice ≤ TransMorph baseline → KILL。
- **K2（卖点·快）**：少步（≤4 步）推理 Dice 掉点 > 2% vs diffusion 配准多步 → 「FM 又快又准」卖点塌 → 降级或 KILL。
- **K3（撞车）**：投稿前 researcher 复查 2026 有无 FM-registration 成片（G3 撞车核验当前未发现直接撞，但 FM 方向热，须复核）。

---

## 四、备选第二苗（BLOCKED，非证伪）

**S4-05**（VinDr reader 分歧 = 局部不确定性）因 **VinDr-CXR 缺逐医生 bbox 标注**（现有 train_meta.csv 只有 image_id/dim）→ killshot BLOCKED，**非真 KILL**。**用户已拍板：并行复活作潜在第二苗。**

**✅ 便宜路径（2026-06-17 核实，免 physionet credentialing）**：S4-05 要的逐医生 bbox = Kaggle 比赛 `vinbigdata-chest-xray-abnormalities-detection` 的 **`train.csv`**（列含 `image_id, class_id, rad_id, x_min, y_min, x_max, y_max` = 逐放射科医生逐框）。我们**已有该比赛的图**（local `data/external/vindr_cxr/`，来自 xhlulu/vinbigdata mirror），**只缺这个 train.csv**。

**下一步（外部动作，需你的 Kaggle 账号）**：
1. `kaggle competitions download -c vinbigdata-chest-xray-abnormalities-detection -f train.csv`（或网页下 `train.csv`），放到 `data/external/vindr_cxr/train.csv`，登 datasets.json。
2. 到货后补跑 S4-05 G5 杀手锏（**零训练**）：算 reader IoU 分歧 vs 预训练 detector confidence 的相关性 ρ + 是否预测定位误差。ρ>0.7（冗余）或不预测误差 → 仍塌；否则 GREEN → 走 `/spin-off-paper` 立第二项目。
3. physionet VinDr-CXR 1.0.0（DICOM + 凭证）是备选，但既然 Kaggle train.csv 就够，**不必走 physionet 审批延迟**。

---

## 五、🛑 请拍板

1. **立 S2-03 为新项目？**（FM 跨模态配准，MICCAI/CVPR 双投，~80 GPU·h，带上面 3 条书面 kill criteria）
   - 立 → 跑 `/spin-off-paper` 建 schema + 登 registry + 关联 datasets + claim，进 G7 中训。
   - 不立 → run-002 收档为「7 候选全程证伪、净化选题池」的负结果留痕，转下一轮 `/ideate` 或别的方向。
2. **要不要并行申请 VinDr 标注、留 S4-05 作第二苗？**（独立于 1，可同时做）

---

## 附：留痕清洁 TODO（不影响本卡结论）

`04_pool/pool.jsonl` 的 `S2-03` 行有 **ID 撞车污染**：raw 阶段存在两个同 id 文件（`03_raw_candidates/S2-cross.jsonl` 连字符 = FM 配准；`S2_cross.jsonl` 下划线 = 另一候选「对比解码弱监督定位」）。pool 行内容被后者污染却 stamp 了 FM 的 `g5_verdict`。**G4/G5/killshot 全程操作的是 FM 配准候选**（雅可比测试只对配准有物理意义），survivor 身份无歧义。下轮修 pool 去重 ID 撞车（建议 `/ideate` G1 dedup 加 id 唯一性校验）。
