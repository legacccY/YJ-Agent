# PhysioNet CITI 认证 checklist（KS-2，用户线下办，2 周提前量）

> 腿 B 承重实证需 **MIMIC-IV / eICU**（PhysioNet credentialed access），凭证审核数天~2 周，**现在办不拖**。CITI 认证是用户本人实名动作，主线不代办。

## 步骤

1. **注册 PhysioNet 账号**：https://physionet.org/ →「Register」，用真实姓名 + 学校邮箱（`@xjtlu.edu.cn` 更易过 credentialing）。

2. **完成 CITI 培训课程**（几小时，免费）：
   - 去 https://about.citiprogram.org/ 注册，Affiliation 选 **Massachusetts Institute of Technology Affiliates**（PhysioNet 认可，MIMIC 归属 MIT-LCP）。
   - 选课程 **"Data or Specimens Only Research"**（PhysioNet 指定，非 human-subjects 全套）。
   - 完成后下载 **completion report PDF**（含证书编号）。
   - 参考 PhysioNet 说明：https://physionet.org/about/citi-course/

3. **提交 PhysioNet credentialing 申请**：
   - 账号 →「Credentialing」，填职业/机构/督导（本科生填导师 = 王水花教授作 reference/supervisor）。
   - 上传 CITI completion report。
   - 审核数天~2 周（人工）。

4. **签数据集 DUA 并下载**（credentialing 过后）：
   - MIMIC-IV：https://physionet.org/content/mimiciv/ → 同意 DUA。
   - eICU：https://physionet.org/content/eicu-crd/ → 同意 DUA。
   - （SLEEP-EDF / PTB-XL / MIT-BIH 多为开放，不需 credentialing，可先下做延迟/前沿预实验。）

## 卡点
- credentialing 常因「机构/督导信息不全」被退回补材料 → 一次填全，导师信息（王水花，西浦，reference）提前备好。
- 办好后路径登 `.portfolio/datasets.json`（跨论文真源），别硬编码。

## 与 KS-3 的关系
CITI 过 → 拿 MIMIC/eICU → 跑 KS-3 命门 pilot（<1GPU·h）。CITI 未过前，主线可先用**开放的 SLEEP-EDF/PTB-XL** 做延迟-精度前沿预热（腿 B 的延迟轴部分不依赖 credentialed 数据）。
