# FUGC 数据纳入作战（第 3 数据集）

> 来源：researcher 联网侦察（2026-06-25）。服务 lever L1（覆盖广度 3 集）+ STORY_REFINEMENT 招 2（第三难度点破 cherry-pick）。
> **重大利好**：FUGC 有 **Open 直接下载**版本（Zenodo 16893174，免邮件申请）→ 取数风险从「需申请等 1-3 天」降到「wget 即得」。
> **规格修正**：FUGC 是 **2 类**（anterior + posterior cervical lip，分评 DSC_A/DSC_P），不是单结构 → 给「跨结构难度连续谱」额外两个难度点，比预想更强化故事。

---

## 行动清单（优先级排序，主线串行取数）

### ① 首选：Zenodo 16893174 直接下（Open，无需账户）
```bash
wget "https://zenodo.org/records/16893174/files/FUGC_Dataset.zip" -O FUGC_Dataset.zip
unzip FUGC_Dataset.zip
# 核：①文件格式(PNG/NIfTI?) ②测试集300张是否含GT mask ③train/val/test划分
```
- 161.8 MB，CC-BY-4.0，标注 Open
- URL: https://zenodo.org/records/16893174

### ② 备选：Google Drive（最完整，含 nnUNet 预处理 + 特征版，需 Google 登录）
```bash
pip install gdown
gdown --folder https://drive.google.com/drive/folders/1iaCGYgvMXJvASX5pbNxz87E-V2AguoIi
```
- 含 `fugc2025.zip`(154MB)/`processed_fugc2025.zip`(139MB)/pretrain(2.32GB)/DINOv2+BioMedCLIP features
- 用途：若 ① 缺预处理或要对标官方 pipeline

### ③ 测试集 GT 必不公开 → 自建 held-out（最可控）
- 从 90 张 val（含 GT）切作我们内部 held-out test，或从 500 train 划 N 张有 GT 的
- HPC 上自评，**不走 Codabench 在线评测**（赛后是否接受提交 TODO）
- 与 PSFHS/HC18 的 held-out 协议一致（守 R2 不泄漏）

### ④ 兜底：邮件申请（仅 ①②③ 全失败时）
- 签 Zenodo 14305302 的 `Data-sharing Agreement_FUGC2025.docx` → 发 fugc.isbi25@gmail.com，等 1-3 天

### ⑤ pseudo-label 补充源（可选，非 expert GT）
- Zenodo 18217137（含各轮 refined mask + 源码，Open）：964MB + 2.5GB pretrain。仅作 SSL 预训练料，**不当 GT 评测**。

---

## 数据规格（设计扩 run 矩阵用）

| 项 | 值 |
|---|---|
| 总图 | 890 TVS（transvaginal ultrasound） |
| 训练集 | 500（50 labeled + 450 unlabeled，标注率 10%） |
| 验证集 | 90（含 GT）← 拟作内部 held-out |
| 测试集 | 300（GT 未公开，赛后 Codabench 评测） |
| 分辨率 | 544 × 336 |
| 类别 | **2 类**：anterior + posterior cervical lip（分评 DSC_A/DSC_P） |
| 标注 | 1 位 >10 年专家(Yuxin Huang)，PAIR 软件自动+人工校正 |
| 顶队 SSL Dice | mDSC = **90.26%**（前后唇均值，T4 队，对标基准） |
| 监督 baseline | TODO：常规全标 baseline Dice 未在 paper 给（仅 SAM 辅助标注 0.9831，非同等对比） |

---

## 纳入后的扩 run 清单（对接 PHASE_3 G4 + LEVER L1）
- FUGC 跑全 benchmark 矩阵：5 方法 × 5 比例 × 5 seed = 125 run（接 master 矩阵）
- Phase3 G4：fixmatch_fixed vs freematch @ {1,2,5%} × 5 seed
- 把 cervix(2 类) 落入「监督基线 dice ↔ SSL 增益」散点，扩到跨结构难度连续谱

---

## 拍板点 + TODO
- **拍板点**：FUGC 数据下到本地后 **上传 HPC = 对外传输，先报用户**（守 CLAUDE.md 拍板点）。
- **TODO（解压后核）**：①测试集 300 张是否含 GT ②文件格式 PNG/NIfTI ③常规监督 baseline Dice ④赛后 Codabench 是否仍接受提交。
- **回退（守 R6）**：若 FUGC 最终拿不到/质量不可用 → 诚实降「双数据集 PSFHS+HC18」，叙事「跨结构连续谱」从 PSFHS 双结构 + HC18 单结构撑（弱化但不塌）。

## 关键引用
- FUGC arXiv: https://arxiv.org/html/2601.15572v1
- Zenodo 16893174（Open）: https://zenodo.org/records/16893174
- Zenodo 14305302（需协议）: https://zenodo.org/records/14305302
- Zenodo 18217137（pseudo-label）: https://zenodo.org/records/18217137
- Google Drive: https://drive.google.com/drive/folders/1iaCGYgvMXJvASX5pbNxz87E-V2AguoIi
- Codabench: https://www.codabench.org/competitions/4781/
