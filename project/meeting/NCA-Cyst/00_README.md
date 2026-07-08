# NCA-Cyst — 全局视野 NCA 做肾囊肿分割

> **一句话**：主流分割模型在 KiTS23 散布小囊肿上近随机（cyst Dice 0.17–0.45），我们给参数极小的 NCA 补一个「全局视野」，让它跑别人跑不动的囊肿。
> **本期（Phase 1）只做 baseline**：把 M3D-NCA + UNet3D 在 KiTS23 上跑起来、建立第一个真数字，创新模块下阶段再立。

---

## 读档顺序（新窗口一跳读全）

1. **`00_README.md`**（本文，入口 + 铁律 + venue）
2. **`01_STORY.md`**（战略叙事唯一真源：headline + 三支柱 + 囊肿场景措辞红线 + 差异化）
3. **`02_ACCEPTANCE.md`**（验收判据唯一真源：A1-An 硬阈值 + 静默发散 Decision Gate + kill criteria + 复现红线）
4. **`DATA_INVENTORY.md`**（KiTS23 细目，路径引 `.portfolio/datasets.json` 真源）
5. **`04_LOG.md` 最新 entry**（时间倒序，最新在上）
6. 动手阶段 → 计划书 `~/.claude/plans/nca-m3d-nca-baseline-*.md`（立项提案 + Phase 1 执行方案）

---

## 铁律（复现零偏离，CLAUDE.md 强制）

- **零偏离官方 M3D-NCA**：禁私加梯度裁剪 / 降 lr / 改步数 / 换实现凑收敛；连数学等价的提速改写都会毁复现（官方 `Agent.py` 全程无 `clip_grad_norm_`）。
- **静默发散**：loss 死平 ~5.0（健康 ~1.25）、Dice=0 但 job 不报错。检测器：ep10 后 loss>3 且 Dice<0.05 = 已死立即 scancel。
- **seed 锁不住**：生死在 epoch 1 由 GPU 随机性掷定 → 报**多 seed 收敛率**，不报单值。
- **推理步数 = 训练步数**：严格对齐，别过步数。
- **护原始数据**：KiTS23 只读，扁平化用软链/派生，不动原始 case 目录。
- **数字 Bash/Grep 核 csv 不信 Read**；超参查官方源查不到标 TODO。

---

## 立项依据（五路调研已交叉验证，全档见 `reference/`）

| 支点 | 结论 | 来源 |
|---|---|---|
| 故事成立 | KiTS23 多类 cyst Dice 0.17–0.45 ≪ kidney 0.93 / tumor 0.69 | springer 978-3-031-54806-2_21 |
| 精确边界 | 专攻囊肿二分类 nnUNet 达 0.82–0.90（ADPKD）→ 动机须锚定「多类小散布 cyst」 | pubmed 38389364 |
| 方法蓝海 | 全局池化 broadcast / global latent token = 干净空白 | survey arXiv 2506.22899 |
| 必避撞车 | Fourier 全局（MECLab 已做 FourierDiff-NCA）、attention-NCA 已成熟 | arXiv 2401.06291 / 2211.01233 |
| 区分点 | M3D-NCA 全局视野只来自最低分辨率级，高分辨率 patch 间无全局通道 | M3D-NCA arXiv 2309.02954 |

---

## 诚实天花板

- **当前档位**：baseline 阶段，创新未验。**「全局视野专治 cyst」是文献空白，没人直接证过**——是机会也是风险，不能 claim 已被证明。
- **升级前置**：Phase 1 baseline 数字（M3D-NCA vs UNet 在囊肿上的对照）落地后，才启动全局视野创新模块立项（下阶段拍板点）。
- **重大风险**：高分辨率 3D 配置历史 0/11 全发散（前列腺 320³），KiTS23 体积更大正撞最难区间——baseline 能否收敛本身是未知数。

---

## 文件导航

| 文件 | 作用 |
|---|---|
| `01_STORY.md` | 战略叙事 + 措辞红线 |
| `02_ACCEPTANCE.md` | 验收判据 + kill criteria |
| `DATA_INVENTORY.md` | KiTS23 数据细目 |
| `04_LOG.md` | 进度日志（时间倒序） |
| `code/` | 实验代码（数据适配 / config） |
| `06_experiments/` | 结果 csv |
| `reference/` | 调研引用存档 |
| 官方代码 | `../Med-NCA/M3D-NCA-official/`（vendor，零改复用） |

---

## Venue

**TODO**（听博士生 + 导师定）。方向登记为医学影像（datasets.json: MICCAI/MedIA）。计划书按通用医学影像方法论文写。

## 角色与协作

博士生观察到「其他模型囊肿近随机」→ 余嘉本窗任务 = M3D-NCA baseline + UNet 对照。创新模块 / venue 由博士生 + 导师定。
