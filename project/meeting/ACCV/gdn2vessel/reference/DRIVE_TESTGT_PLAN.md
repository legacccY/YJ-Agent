# DRIVE test GT 重下方案（drive-testgt，winL）

**服务**：DRIVE 标准 20/20（train20+test20）主 Dice 表，可比 SOTA / lever L3。承 Entry 14「DRIVE 无 test-GT」根因核实。
**产出**：researcher 核源（官方页 + 镜像 + license），2026-06-20。**本档只出方案，不真下载大文件 / 不传 HPC**（主线串行 + 拍板点）。
**territory**：本档（reference/）+ datasets.json 备注。下载/上传交主线拍板。

---

## 结论先行：DRIVE 官方 test GT 公开性判定

**判定 = grand-challenge 官方下载包不含 test GT，只能在线提交预测评分。**

- 官方页 drive.grand-challenge.org 原文：`"For the test cases no annotations are made available, you will be able to submit your predictions to this site and have them compared to the gold standard."` → test/1st_manual + test/2nd_manual **不随官方包发放**。
- 原始 ISI UU 站（isi.uu.nl/Research/Databases/DRIVE/download.php）**404 已死**，grand-challenge 现为唯一官方入口（注册后下载 = training(1st_manual) + test(images+mask)，无 test GT）。
- 现项目 Kaggle `umairinayat/retinal-vessel-segmentation-datasets` 包 `DRIVE/test/` 只有 images+mask 无 1st_manual → **不是上传者失误，是官方下载本身不含 test GT 的直接反映**（orobix/retina-unet issue #76 社区原发报告同症）。
- 混淆根因：Bob/Idiap 文档「two manual segmentations available」描述的是数据集**理论设计**，非官方公开下载内容。大量 paper 报 DRIVE test Dice = 用了社区流传的完整包（2004 原始 ISI 发布曾含 test GT，后撤）。

---

## 可执行下载方案（排序，交主线拍板）

> ⚠️ 方案 A/B/C 共同 TODO（30 秒可解，须真下载前人工做）：进 Kaggle Data Explorer 确认 `DRIVE/test/1st_manual/` 下有 **20 个 `01_manual1.gif`…`20_manual1.gif`** 再下，避免拿到同样缺 GT 的二手包。

### 方案 A（首选）：Kaggle `zhz638/drive-dataset`
- URL：https://www.kaggle.com/datasets/zhz638/drive-dataset
- 社区多次指为「完整版本」（区别于缺包的 andrewmvd/umairinayat），结构应含 `test/1st_manual/` + `test/2nd_manual/`
- 下载：`kaggle datasets download -d zhz638/drive-dataset --unzip -p <out>`
- **TODO**：Data Explorer 验 test/1st_manual 20 文件 + License 字段（学术可用性）。

### 方案 B：Kaggle `aifahim/drive-test-dataset`
- URL：https://www.kaggle.com/datasets/aifahim/drive-test-dataset
- 名称直指「DRIVE test dataset」，疑专为补 test 集发布
- 下载：`kaggle datasets download -d aifahim/drive-test-dataset --unzip`
- **TODO**：Data Explorer 验是否含 1st_manual GT + license。

### 方案 C：Kaggle `andrewmvd/drive-digital-retinal-images-for-vessel-extraction`
- URL：https://www.kaggle.com/datasets/andrewmvd/drive-digital-retinal-images-for-vessel-extraction
- 社区说法**矛盾**（含/不含 test GT 都有人说）→ 不作首选，**TODO** Data Explorer 人工确认。

### 方案 D（最权威，需账号，不适合多方法主表）：grand-challenge 在线评估
- 注册 drive.grand-challenge.org → 上传 test 预测（20 PNG）→ 平台返回 Dice/AUC（官方 gold standard）
- 提交入口：https://drive.grand-challenge.org/evaluation/d86fe121-0fd1-46b7-a02e-4c845f65bbc9/
- 缺点：无法本地批量算多模型 Dice，P3 12+ baseline 对比每个都要一次提交，繁琐。

---

## 数据一致性校验清单（拿到包后核，防二手不一致）
- test 20 张：`01_manual1.gif`…`20_manual1.gif`（1st=gold）+ `01_manual2.gif`…（2nd 观察员，可选）
- images `01_test.tif`…`20_test.tif`；mask `01_test_mask.gif`…
- 分辨率 565×584 8-bit，FOV 45° 彩色眼底
- 原始 ref：Staal et al. 2004 IEEE TMI 23(4):501-509（1st=gold，2nd=独立观察员）

---

## 退路（若 A/B/C 都确认无 test GT）
1. **grand-challenge 在线提交**：12+ baseline 各一次提交拿 leaderboard Dice（可比性最强，繁琐）。
2. **DRIVE train-only 内部 5-fold CV**：train20 做 5-fold，论文写明 "internal cross-validation"，**不能直接和标准 DRIVE test Dice 对比 SOTA**。
3. **主表换有完整 GT 的集**（CHASE_DB1 有完整 test、STARE LOO 全公开 GT），DRIVE 降附录或仅引 train split 指标。

> 注：WINDOW_TASKS 拍板点 3 已定「DRIVE 不做断点 benchmark，走 CHASE」；本节点只补 DRIVE **标准分割 Dice 表**的 test GT，与断点轴无关。

---

## 关键引用
- drive.grand-challenge.org（官方页：test 无 annotation，在线提交）
- isi.uu.nl/Research/Databases/DRIVE（原始站 404 已死）
- orobix/retina-unet issue #76（社区原发报告 test GT 缺失）
- Kaggle zhz638/drive-dataset · aifahim/drive-test-dataset · andrewmvd/...（候选完整包，待 Data Explorer 验）
- grand-challenge 提交入口 evaluation/d86fe121-...（在线评估退路）
- Bob/Idiap bob.db.drive 文档（「two manual」=设计描述非下载内容，混淆根因）

---

## 下一步（主线拍板）
1. 进方案 A（zhz638）Data Explorer 验 test/1st_manual 20 文件 + license → 确认则 `kaggle datasets download` 下载本地。
2. 校验清单核对 → 主线拍板传 HPC（对外传输，拍板点）。
3. datasets.json DRIVE 条目回填新 local 路径 + test GT 来源（真下载后改，本棒不臆改）。
