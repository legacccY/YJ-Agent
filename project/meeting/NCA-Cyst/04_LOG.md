# NCA-Cyst — 进度日志（时间倒序，最新在上）

---

## 2026-07-08 · 🟢 立项 + 五路调研 + 建档

**背景**：博士生观察到主流分割模型在肾囊肿上近随机，NCA 加全局视野也许能跑。余嘉本窗任务 = 先做 M3D-NCA baseline。用户拍板立项（方向=NCA×KiTS23 囊肿分割，本期只 baseline，创新模块下阶段再立）。

**做的事**：
- 五路 opus 编队调研（2 路本地 + 3 路联网），交叉验证地基：
  - 数据集确认 = **KiTS23**（肾 CT，489 例，囊肿=label 3），本地+HPC 均验通。
  - 故事成立**但有精确边界**：KiTS23 多类 cyst Dice 0.17–0.45（近随机），但专攻二分类 nnUNet 达 0.82–0.90 → motivation 必须锚定「多类小散布 cyst」。
  - 方法蓝海 = 全局池化 broadcast / global latent token；必避 Fourier（MECLab FourierDiff-NCA）+ attention-NCA。
  - 官方 M3D-NCA 3D 超参从 config 源码核实（Adam lr16e-4 betas(0.9,0.99) / DiceFocalLoss / 两级[(80,80,6),(320,320,24)] / 步数[20,40] / 3000ep）。
  - 重大风险：高分辨率 3D 配置历史 0/11 全发散；静默发散；seed 锁不住；步数须对齐。
- 关键发现：官方 dataloader `Nii_Gz_Dataset_3D.py:209-210` 默认 `label[label>0]=1`（二分类），做囊肿必须改。
- 用户拍板三岔路：①先复现官方二分类→再切囊肿(label==3)；②本期自己也跑 UNet3D 同口径对照；③venue=TODO。
- 建标准档（00/01/02/04 + DATA_INVENTORY）。
- 跑 KiTS23 囊肿分布分析（`_scratch/kits23_cyst_dist.csv`）。

**结果**：项目档建立，计划书批准（`~/.claude/plans/nca-m3d-nca-baseline-*.md`）。

**下一步**：
1. KiTS23 扁平化预处理脚本（case 子目录→images/labels 扁平同名）。
2. Phase 1a：官方二分类 config 本地小样本烟测（验管线不发散）→ HPC 全量。
3. Phase 1b：切囊肿二分类拿 NCA 第一个真数字。
4. Phase 1c：UNet3D 同口径对照。
