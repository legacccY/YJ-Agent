# 工作日志（快速指针）

**最后更新**：2026-06-15 20:30 ICLR 会话 30（详见 PROJECT_LOG 会话30 entry；本行起为历史指针）｜会话 24（**v6 训练 14h 窗口主线零空等**〔job 1442696 还在跑 ep12/80、4×GPU 全占满（QOS 上限 4 卡、无剩余配额开第二 job）、E1 守 PSNR30.16、ETA 明早~06:00〕→ ① **§7.4 mask-L1 两分支预写** `drafts/s74_branches.tex`〔救起 A/没救 B + 6 占位符，eval 落地按 analyze_e5_perclass VERDICT 一键填零返工〕② **Table1 骨架对齐** `s7_table1_skeleton.tex`〔揪出 8 行与 gen_table1 GROUPS 对不齐→改 9 baseline+Ours 与 csv 1:1，仍全 -- 占位 gated M2〕③ **审 v6 re-eval 管线** 焊死零返工〔wiring 传得过/Stage1 镜像 v5/aux ckpt 全在/键名全对/输出 _v6 不覆盖〕④ **实现 E9 cross-attn**〔模型从「不支持」→ 代码就绪 4/7，CrossAttnConditioning n_tokens=4 修正草案单 KV token 退化缺陷、resume strict=False 跨 conditioning 暖启、smoke 全过、v7 config 建〕。commit `8bc602b1`+`496385c4`。**开火点=v6 训完**〔sbatch submit_eval_v6.sh + E9 重传 3 文件排队，均串行 gated on v6〕。详见 PROJECT_LOG 会话 24 entry）｜ 会话 23（🚀 **v6 mask-L1 重训启动 job 1442696 健康跑中**〔Grad-CAM 被 smoke 证伪打角落→改经典三层分割 Otsu/GrabCut/中心高斯、33126 mask 全覆盖、四道返工门全过；早期 3ep val_PSNR 30.14→30.18 守 E1、DP/hinge 正常降、ETA 明早05:30〕+ **§7.4 E5 诚实版编译进 paper 37 页**〔melanoma salvage 5.2%/damage 31% net−81 不卖聚合〕+ **v6 re-eval 全管线 staged**〔analyze_e5_perclass 验过复现 v5、E1/E3/dflip/E5 launcher+submit_eval_v6.sh 上传、会话24 一条 sbatch 开火〕+ 更正会话22 HAM/PAD 误判）｜ 会话 21（**E8 消融定论**〔E1 同口径：FiLM 对 PSNR 中性 with 32.74/no 33.06；FiLM 诊断消融：with-FiLM dAUC −.033/一致率 .90/KL .24 全面优于 no-FiLM −.042/.87/.35 → FiLM 价值在诊断保持非 PSNR，reviewer 攻击拆解；E8 判据从「FiLM 涨 PSNR」诚实改判「FiLM 诊断更好」〕+ **fig_dflip v5 重出**〔job 1442284，flip 13→10、B_enh 11→8、均值 0.93→0.82，/validate-figures PASS + .verified〕+ **framing 回写清偿 4 会话核心欠债**〔STORY Claim2/3+锁定表 + ACCEPTANCE E1-E12 实测块+E8 修判据 + 文献 refs `plans/lit_visienhance_dflip_refs.md`〕 + **§7/§8 paper TEX 回写**〔main.tex 填 E1/E2/E3/E6/E7/E8/E12 frozen + §8 接 fig_dflip+dflip/E6 discussion + references.bib 补 18 文献，**编译 zero undefined 33→36 页**；3 subagent 并行只碰独立文件〕 + **🔴 揪出 visiscore 集成喂错根因**〔timm backbone 被喂 raw[0,1]@256 而非 NORM224 → q̄ 恒 ~0.54 不响应退化，连贯解释 E8/hinge/E5 三异常；qnorm 对照 job1442379 证实**现有 E1-E12 数字仍有效**（raw-q 训练口径自洽最优，喂正确 NORM-q 反更差）、bug 影响收窄〕 + **E5 norm-q 路由版**〔job1442385，moderate SalvageRate 0.737✅，benign-FP 主导 nuance 待解读，暂不写 §7〕）｜会话 20（**v5 训完**〔job 1440985 completed，best_val_PSNR 30.186 守 E1〕→ **HPC GPU 跑 E3/E7**〔job 1441301，3.5min〕→ **E3 翻 PASS**：dAUC −0.0120 PASS、一致率 0.9575 PASS、**dangerous_flip 0.176→0.135 破 v4 三版卡点**（未归零）、McNemar enh-vs-ref p=0.573 无显著差；**E7 续 PASS**：ΔAUC +0.0205 显著>0、ΔKL −0.148 显著<0、McNemar p=2.3e-45。反直觉：S1(no-DP) dflip 0.054<v5 但 S1 整体全 FAIL，dflip 不可孤立比、须配 KL 读。存档 `results/eval_v5_E3E7_1441301.out`+`stage2_diag_paired_v5.csv`。**欠债**：framing 回写仍顺延）| **完整进度**：见 `D:/YJ-Agent/project/PROJECT_LOG.md`（ICLR 主线，会话 20 详 entry）+ `project/meeting/Med-NCA/PROJECT_LOG.md`（Med-NCA）

> 🟢 **会话 30 完成（2026-06-15）L7 cross-domain 扩到 4 skin + 1 跨模态边界 + L10 sex/age fairness，全入 paper 40 页**：① **L7**：加 Fitzpatrick17k(n=16574)+DermNet(n=3151)，**ρ 质量-不确定性耦合 4/4 skin 全转移**（Fitz −0.198 p<1e-145、DermNet −0.223 p<1e-36，F|ρ|>D>B3），但远域绝对 ECE/AUC 失守（Fitz ECE 0.587/AUC~0.58、DermNet AUC~0.54）；**fundus(APTOS n=3662) 跨模态失败边界 ρ=+0.135 翻正号、QCTS 塌回 TS** → reframe「property modality-bounded」写 §7.6+§8 Lim(5)。② **L10 fairness**：套 image_id patch 重 eval ITB → F(Ours) **sex gap 0.0382 PASS**（9 baseline 最小）/**age gap 0.2604 FAIL**（全 9 baseline 共性，祸首 >60 段 43% 高患病；唯二「达标」靠均匀失准凑 parity）→ 填 §7 Fairness 段。main.tex **40 页 0 undef**，ACCEPTANCE L7/L10 已更。**本会话产出 + 会话30 日志已 commit 清债**。待续：Kvasir/CheXpert(paper 已 deferred 低优先)、Fitz V-VI 等价检验。详见 PROJECT_LOG 会话30 entry。
>
> 🔴 **会话 29 完成（2026-06-14）E4Q FAIL + Table1 多 seed agg 证伪**：① **E4Q**（Q-VIB Full 自身 quality-conditioned entropy 重测 Prop3，非 B3）job1449094 COMPLETED：ρ_deg=-0.0381→ρ_enh=-0.0397(几乎不变)，H_deg=0.1487→H_enh=0.1572（**熵反升**，方向反）。**FAIL**，与会话28 B3 饱和 inconclusive 一致指向「E4 不支持降熵」，ACCEPTANCE E4 改判 FAIL、Q-VIB-熵重测 future 清零，Prop3 不受影响（仍由 E7 承载）。② **Table1 多 seed agg 证伪**：核查发现 Table1 现用 `checkpoints/efnet/best_qad.pth`（5月7日）与 `efnet_s{42,123,2024}/`（5月8日批次，CV<2% 验证过的那组）是**两个不同训练产物**（ITB-LQ AUC 0.585 vs 0.72-0.73，ECE 方向相反），不可 pool。"CV<2%" 描述的是另一批 ckpt，跟当前 Table1/E4Q 主 ckpt 无关。**待续项关闭**，除非重训新一组三 seed（未排期）。**未 commit（与会话28 一起待用户拍）**。详见 PROJECT_LOG 会话29 entry。
>
> 🟢 **会话 28 完成（2026-06-14）§7 实验大收官**：**Table 1 主结果 + E10 6 SOTA + E11 cross-domain 全重 eval 入 paper，编译 39 页 0 undefined**。① **E10 口径修复**：首版 on-the-fly VE PSNR 30.48≠E1 32.74 → 深挖三脚本定根因=两套协议三层差异（降质来源/严重度 mixed-vs-moderate/群体，非 bug）→ 重跑对齐（`build_df_stored` 存盘 mixed，job1448952）**VE 32.79=E1 32.74✓**、6/6 baseline paired ΔAUC 全 CI 排除 0 / McNemar p<1e-150 → main.tex `tab:e10`。② **Table 1 重 eval**（ckpt+数据+管线全本地、无须重训）：run_experiments 9 baseline 逐位复现 BMVC（确定性）+ gen_qcts_iclr 绕缺失 cache → gen_table1 改道 ICLR。**诚实 reframe（用户授权「合规+不降质量」）**：Q-VIB Full ITB ECE 与 Std VIB 持平→headline 改「质量感知校准 QCDI/ρ」（F QCDI+0.006 可训练最佳=Prop2 实证），Ours 高亮从 QCTS 改 F、QCTS 降 prior ablation。③ **E11**（HAM/PAD 重 eval）：**Q-VIB Full ρ −0.16(HAM)/−0.24(PAD) 质量感知 zero-shot 转移**、ECE 远胜 B3；远域 AUC 衰减当 limitation→agent OOD 追问。§7.6（2/8）。④ **E4 inconclusive 不入 paper**（红线4 不 fudge）：真 B3 熵饱和 ln2/ρ 正号测不出降熵，Prop3 改靠 E7+非空性；laptop GPU 对 VisiEnhance convT 废→转 HPC 才验出。BMVC csv 全归档 `results/_bmvc_archive/`（红线10）。ACCEPTANCE E4/E10/E11+L7/L8(11/12)/L9 更新。**未 commit（待用户拍）**。详见 PROJECT_LOG 会话28 entry。
>
> 🟢 **会话 27 完成（2026-06-13）**：E9 v7 crossattn **训完**（job 1444849 COMPLETED，best ep47 val_PSNR 30.184）→ eval 管线落地（改 2 build 点读 config conditioning + CFG_MAP 混合架构 paired，登录节点验 crossattn 加载 0 missing 才 sbatch）→ **E9 定论：FiLM 与 cross-attn 统计无法区分、FiLM 以 parsimony 胜（−1.8M 参数）**。同口径 paired（job 1448254，n=3627）：per-image PSNR 32.79 vs 32.74 打平、E3 双 PASS、paired ΔAUC +0.0016 / ΔKL +0.0026 三轴 CI 全含 0、McNemar p=0.679 不显著、crossattn dflip 0.19 反高于 FiLM 0.14。**🔑 纠会话 26「crossattn 低 2.6dB」= 口径错配**（拿训练 aggregate 30.17 比 FiLM per-image 32.74，会话 9/10 早定论差 ~3dB）。写进 main.tex E9 段（编译 0 undefined，38 页）+ ACCEPTANCE E9 实测块。产物 `results/{stage2_diag_paired_e9.csv,eval_e9_1448254.out,e1_v7.json}`。**开火点（会话 28）= E10 6 非扩散 SOTA**（待用户拍训练）。详见 PROJECT_LOG 会话 27 entry。
>
> 🟢 **会话 26 进行中（2026-06-12）**：开门查 HPC 发现 **E9 v7 crossattn 已在跑**（job 1444849 `visienh_v7ca`，RUNNING，ep41/80，ETA 今晚~19:30）——非会话 25 记的「待用户拍未启」，v6_eval 11:51 完后已紧接提交，**文档脱节已补**。**早期信号**：crossattn val_PSNR 30.17 vs FiLM v5 32.74，**低 2.6dB**（若 ep80 持平 → E9 = crossattn 不如 FiLM，呼应 E8）。健康（守 E1、DP/hinge 正常、无 NaN/error）。**用户问平台能停否 → 判不停**：E9 是消融须与 v5 同口径 80ep，半停结论被 reviewer 拆；PSNR 平台本身是结果信号。**会话 26 开火 = v7ca 训完 → 写 E9 eval launcher（会话24 TODO6）→ 与 v5 1:1 对比**。详见 PROJECT_LOG 会话 26 entry。

> ✅ **会话 25 已完成（2026-06-12）**：v6 mask-L1 job 1442696 **COMPLETED**（ep80，best ep51 val_PSNR 30.225）→ `sbatch submit_eval_v6.sh`（job 1444753，16min）→ 拉 5 产物 → `analyze_e5_perclass` 出 VERDICT。**🔑 mask-L1 = NULL 干预**：melanoma salvage 5.2%(4/77)→5.2%(4/77) 纹丝不动、net −81→−79（+2/274 噪声）、dflip 还略升（10→11）→ 脚本机械判 HELPS 但诚实读 = 负结果，**§7.4 用 Branch B（负结果版）落地**（main.tex 295-308，编译 0 undefined 37 页）。其余 v6 全持平 v5（E1 32.845 PASS/E3 双 PASS/E7 PASS）。ACCEPTANCE+PROJECT_LOG 已回写。**🟢 会话 26 开火 = E9 提交（待用户拍）**：v6 训完+GPU 空+代码会话24 smoke 验过，但天级 4×GPU DDP=训练串行红线须用户拍 → 重传 3 文件（visienhance.py/train_visienhance.py/v7 crossattn config）后 `sbatch`；E10 6 SOTA 待 E9 后串。**↓以下为会话 24 历史指针↓**
>
> 🟢 **会话 25 原接续（已执行完毕）**（会话 24 = 14h 训练窗口备好全部下游、开火点 = v6 训完）：**第一件查 v6 job 1442696 训完没**（4×GPU DDP 80ep，会话 24 时 ep12/80、ETA 明早~06:00）+ best ckpt 存否 → ① `sbatch submit_eval_v6.sh`（已审焊死、E1/E3/dflip/E5 串一个 GPU job ~15min）→ 拉 `stage2_diag_paired.csv`→`_v6`、`dflip_persample.csv`→`_v6`、`e5_salvage_v6*`、`e1_v6.json` → `python analyze_e5_perclass.py results/e5_salvage_v6_persample.csv --baseline results/e5_salvage_persample.csv` 看 **VERDICT**（mask-L1 救起 melanoma 否）→ 按 §7.4 `drafts/s74_branches.tex` 的 A（救起）/B（没救）分支填数进 main.tex line 295-308。② **E9 提交**（v6 训完后串行）：重传 `models/visienhance.py`+`train_visienhance.py`+`configs/visienhance_s2_planA_256_v7_crossattn_hpc.yaml` 到 HPC `code/` → `sbatch` v7 crossattn 训练（代码会话 24 已 smoke 验、resume strict=False 已通）。③ E10 选定 6 非扩散 SOTA（`plans/E10_sota_baselines_prep.md`）待 E9 后串。**注**：QOS 上限 4 卡、v6 占满、串行红线 → E9/E10 必等 v6 训完。commit `8bc602b1`+`496385c4`。详见 PROJECT_LOG 会话 24 entry。**↓以下为会话 23 历史↓**
>
> 🟢 **会话 23 前半（§7.4 + 更正）**（纯写作零训练）：① ~~写 §7.4 E5 诚实版~~ ✅ **已落笔编译**(main.tex line 295-296 placeholder → E5 benign-dominated 段 + E6 severe 段，明写不卖聚合 salvage、melanoma 5.2%/31% net −81 = query-for-retake 最硬证据，**zero undefined 36→37 页**)。② 🔧 **更正会话 22 误判**:HAM10000(10015 张)+PAD-UFES(2298 张)**本地实际在**，DATA_INVENTORY ✅ 是对的不改;**E11 真正 gate = BMVC 红线 10**(external_*_predictions.csv 是 Sprint2 产物须为 ICLR 重跑)，非缺数据 → 数据齐重跑随时可做、属 M2 待拍。③ **待用户拍 M2 重训**:mask-L1(救 melanoma salvage，§7.4 已写 future work，优先级最高)/E9/E10/visiscore norm-q 重训。④ E11 zero-shot 为 ICLR 重跑(非阻塞)、Table 1 维持 pending(红线 10)。详见 PROJECT_LOG 会话 23 entry。
>
> 🔵 **会话 22 接续点（会话 21 已清 framing 回写 + fig_dflip v5 + E8 双消融，全落 PROJECT_LOG 会话21 entry）**：① ~~§4/§7 paper TEX 回写~~ ✅ 会话 21 已做（main.tex §7 填 E1/E2/E3/E6/E7/E8/E12 frozen 数字 + §8 接 fig_dflip+dflip/E6 discussion `s8_enhancement_failure.tex` + references.bib 补 18 文献，**编译 zero undefined，33→36 页**）。下一步可搭 §7 Table 1（9-baseline×ITB）LaTeX 骨架（数字 pending 待 M2）。② **M2 重训类需用户拍**（训练串行红线）：E5 SalvageRate（建 Stage3 agent）/ E9 FiLM-vs-CrossAttn / E10 6 SOTA（红线禁扩散）/ E11 HAM/PAD 传 HPC / E4 增强图重跑 Q-VIB 链。③ 两条 limitation 入文：E2 contrast/color_shift 弱（limitation 或触发重拍）、E6 severe 不安全（triage 正证据）。**全套 run_id 溯源见 `ACCEPTANCE_CRITERIA.md` E1-E12 v5 实测块。**

> 🆕 **新独立子项目 Med-NCA**（顶会复现→创新，与 ICLR 主线并行）：计划 `project/meeting/Med-NCA/REPRO_PLAN.md`、日志 `.../PROJECT_LOG.md`。**会话 7（06-04）：揪出 R2 发散真因 = 我方 `FastBackboneNCA` 提速 subclass 改了 RNG 流（非官方配置错）—— 上网溯源官方配置一字不差 + diff 源码相同 + 忠实 smoke（官方 BackboneNCA）loss 健康降 Dice@5ep=0.33 坐实。🔴 作者立永久红线 §1#8「复现完全按官方零偏离」（禁加裁剪/降lr/换实现/提速 subclass）。旧 R1 0.8661（fast版）+ 早期加裁剪方案均作废。** **会话 8（06-05）：R1 官方版 PASS（0.8644 三源一致）+ R2 官方版 0.672 FAIL 非崩溃 + 全套行为档案官方重算 + 6 页 6 图 LaTeX 复现报告。** **会话 9（06-05）：核实 R2 配置 11/12 项一字不差官方、唯一缺口=epoch（301 vs 1000）；诊断收敛趋势=未饱和（loss ep125→300 0.37→0.27 没平 + 验证 Dice ep275 冲 0.795 贴 UNet 基线）→ 延 1000ep 重训提交 HPC job 1436075（RUNNING，~10h），监控 `hpc_mednca_gui.py 1436075`。** 下一步：盯 1436075 ep1000 eval vs 0.838 看 gap 缩多少 → R2 是否翻 PASS。

> 🔵 **会话 17 接续要点（下一步从这开始）**：v4 Stage2 已评完并取消（job 1434527 取消让 mednca 上）。**E7 PASS**（DP vs no-DP：ΔAUC +0.0299 显著、ΔKL −0.29 显著、McNemar p=4e-59）；**E3 仍卡**（dAUC −0.020 borderline、一致率 0.945、**dangerous_flip 0.176 三版 hinge 都没压下**）。**🔴 dflip 根因（`diag_dflip_v4.py`）：13 个翻转里 85% 是 enhance 主动把阳翻阴（非退化），且非 borderline（含 pr=1.0），enhance 平均把 mel 置信度 0.92→0.81 → 系统性「美化」黑色素瘤、红线 R8 实证。**
>
> **下一步（会话 18）**：
> ① **优先出 dflip figure**（零训练、最有冲击力）：mel 置信度 ref→deg→enh 下滑曲线 + 11 例 enhance-caused flip 病灶磨平对比图。
> ② **framing 转向**：E3 降级为 motivation 证据，主推 E7 + dflip 实证 → 坐实 Claim 3 / Theorem 2（query-for-retake）。回写 STORY_FRAMEWORK §4 + ACCEPTANCE E3/E7。
> ③ loss 真要救 dflip：弃加 hinge λ，转 **mask 加权 L1（病灶区不准磨平）** 或 **feature-level DP（B3 中间特征对齐）**。
>
> **本地已存**：v4 best ckpt `project/checkpoints/visienhance/stage2_planA_256_v4/best_visienhance.pth`（ep46 PSNR-best）；eval 结果 `project/results/stage2_diag_paired.csv`（dAUC/KL/McNemar）；诊断脚本 `project/diag_dflip_v4.py`。
>
> ⚠️ **教训重申**：HPC 迭代必须每轮记日志 + commit config，会话 16 的 v3/v4 又没记、靠产物还原（第二次踩同一坑）。

---

## 🎯 当前焦点

**ICLR 2027 大项目启动**（Deadline 2026-09-22，**121 天**）
- 目标命中率：**78-80%**（25 lever stack）
- 当前 M1 W1：VisiEnhance Plan A 重训准备 + Theorem 2 推导

**BMVC**：✅ 已封印（2026-05-24），不再修改 — 详见 `project/meeting/BMVC/SUBMITTED.md`

---

## 📋 主指导文档（按读档顺序）

| 优先级 | 文件 | 用途 |
|---|---|---|
| 🥇 入口 | `project/README.md` | ICLR 2027 项目入口 + 4 文件读档顺序 |
| 🥈 反跑偏 | `project/STORY_FRAMEWORK.md` | 10 跑偏定义 + §1-§9 锁定 + 锁定数字 + R1-R10 |
| 🥉 验收 | `project/ACCEPTANCE_CRITERIA.md` | 25 lever + E1-E12 + 红线 + M1-M4 milestone |
| 数据 | `project/DATA_INVENTORY.md` | checkpoint + 数据集 + 30+ csv + 脚本 + W1-W16 |
| 日志 | `project/PROJECT_LOG.md` | 时间倒序，每次会话进度 |

---

## 🔥 会话 10 定论（2026-05-31）：PSNR 口径统一 + light/heavy nocrop 生成 + Stage 2 停训

- **PSNR 口径专节**已补入 `ACCEPTANCE_CRITERIA.md`（per-image mean = 论文标准；batch-aggregate = 训练监控，差 ~4 dB）
- **regen_nocrop.py** 修复 merge 逻辑（不覆盖已有 CSV），生成 light + heavy 各 49700 张，`quality_labels_nocrop.csv` 共 149100 行 ✅
- **eval_visienhance.py** 加 `--labels-csv` override，E1 现可正确指向 nocrop CSV
- **Stage 2 (DP-Loss)** 启动并跑至 ep5：loss 持续下降（0.0181→0.0129），但 val_PSNR 从 ep1 峰值 29.844 持续下滑至 29.6 ← 用户决策停训
- **下次待确认**：Stage 2 PSNR 下滑原因（λ_DP 过大？lr 过高？）→ 调参后重跑，或直接跳 Stage 3

## 🔥 会话 9 定论（2026-05-30）：VisiEnhance Stage 1 nocrop 收敛，E1 实际达标（PSNR 定义澄清）

- **续训** PID 22296 (12:16 起 ~8h) ep17→56：ep44 起聚合 PSNR 28.97 平台锁死 12 epoch，已 kill。
- **🔑 PSNR 定义澄清**（val n=3312 对照，两种都复现）：
  - 聚合 MSE（训练日志用）：input 16.44 → enh **28.92**（复现训练 28.97）
  - 每图均值（论文标准报法）：input 21.95 → enh **32.50** → **E1≥30 PASS**；test split 32.74
  - 非 bug 非挑数字，是 PSNR log 非线性；input baseline 同规律佐证。
- **E1 结论**：PSNR **32.5**(每图)PASS / SSIM **0.946** PASS。**无须 Plan B。**
- **视觉**：`project/demo_nocrop_ep51.png`（degraded/enhanced/ref ×6）清晰无伪影，守 R8。
- 脚本新增：`scripts/eval_nocrop_e1.py`(双 PSNR 定义) + `scripts/make_visienhance_demo.py`。json：`results/visienhance_nocrop_e1.json`+`_val.json`。
- **会话 10 待办**：统一全项目 PSNR 口径 → 全量 light/heavy 重生成 → Stage 2/3 → 回写 STORY/ACCEPTANCE/paper。

## 🔥 会话 8 发现（2026-05-29）：PSNR≥30 卡死真因 = 退化管线随机裁剪 bug

- **诊断**：Plan A 15M 模型 ep42 卡 25.5，与 1.7M v0 **完全相同** → 容量证伪
- **三层诊断脚本**（`project/scripts/diag_*.py`）：
  - oracle 仿射上界仅 26.43 dB（旧裁剪数据），模型已达 96% → 不是模型问题
  - 退化分解：光度可逆到 50 dB / 模糊单独 38 dB，但组合后崩到 26
  - **元凶 = `degrade.py` 的 `apply_random_crop`（ratio 0.75-0.89, prob 0.5）**：裁剪+缩放使降质图与原图**像素错位**，强迫模型 hallucinate 被裁组织（违反红线 R8），任何容量都崩
- **修复**：crop 不属增强任务，归 Theorem 2 的 **query-for-retake 通道**
  - `degrade.py` 加 `crop_prob` 参数（可关裁剪）
  - 无裁剪重生成 medium（49700 张）→ `data/paired_dataset_nocrop/` + `quality_labels_nocrop.csv`
  - 重生成后 oracle 上界 **26.43 → 37.49 dB**（+11 dB）
- **验证训练**（`configs/visienhance_s1_planA_nocrop.yaml`，fresh init）：val_PSNR 16.47(baseline)→ ep16 **28.0**（旧死点 25.5，已甩开 +2.5 dB 且续升），**裁剪假设确认无疑**
  - checkpoint：`checkpoints/visienhance/stage1_planA_nocrop/best_visienhance.pth`（best 28.008 @ep15）
  - ep16 主动收工停训（未跑完 60ep）

## ⏭️ 下次接续（会话 9）

1. **续训 nocrop 到收敛**（resume `stage1_planA_nocrop/last`），观察是否过 30；若卡 ~28 → 加 MSE loss 项 / 提 lr / LPIPS→0
2. 达标后**全量重生成 light + heavy**（`regen_nocrop.py --levels light heavy`）
3. 完整 Stage 1→2(DP-loss)→3(hinge) + E1-E12
4. **回写文档**：STORY_FRAMEWORK §4 + ACCEPTANCE E1 + plan_07，把 crop→query-channel 写成设计决策（强化 Claim 3 / Theorem 2）

## 🚀 下一步（M1 W1-W2，2026-05-27 ~ 06-08）

会话 7（2026-05-27）完成（纯写作零实验，详见 PROJECT_LOG）：
- [x] **Appendix A1 LaTeX 化**（Q-VIB Prop1/Lemma1/Lemma2/Thm1/Prop2 full proofs）→ 5-theorem closure LaTeX 全齐 ✅
- [x] **主文 Abstract→§9 正文填充** + Ethics/Reproducibility statement（§7 result 留 TODO 占位）✅
- [x] **Appendix A0/A4/A18/A19/A20/A21/A23/A26 LaTeX 化** + references.bib(19 ref) + citation 接线 ✅
- [x] DATA_INVENTORY ITB 计数纠错（Edge660/Diverse1500）✅
- [x] paper **33 页**，bibtex 全 defined，零 undefined，零 banned 字样 ✅
- [x] **BMVC 匿名 repo 主页重写** `release/README.md`（标题对齐投稿 itb_paper.tex + headline 置顶 + 硬件纠错）✅
- [x] **release 匿名审计修复**：P1 致命去匿名（GITHUB_SETUP/造史脚本含身份词 → .gitignore 排除 + 自删）+ P2/P3/P4 一致性（DATASET_CARD 标题/区间、data/README 死链）✅

待续（全部 gated on 实验，写作侧已到边界）：
- [ ] **续训待启动**（从 ep 15 续，`stage1_planA/last_visienhance.pth`，`/loop /run-experiment`）
- [ ] §7 result tables + A5/A16/A17/A22/A24 → **必须 Plan A 重训 + re-eval 后才有 frozen 数字**
- [ ] **Plan A re-eval 后必办**：重导 n=19878 per-sample csv + 决定 cross-domain 锁定值(−0.108→−0.164/−0.150→−0.236)

详细 task 清单见 `project/plans/phase_07_visienhance_planA_active.md`

---

## 🔬 关键数字速查（ICLR 2027）

| 模块 | 状态 | 核心数字 |
|---|---|---|
| VisiScore-Net | ✅ done | PLCC 0.924 / SRCC 0.895 |
| Q-VIB Full | ✅ done | AUC 0.707, ECE 0.098, ρ=−0.165 (p<10⁻²⁴) |
| 5 backbone universality | ✅ done | section54_summary.csv |
| VisiEnhance Stage 1 v0 | ❌ 裁剪 bug | PSNR 25.55 dB（误判容量，实为裁剪致像素错位）|
| **VisiEnhance Plan A** | ⏳ M1-M2 | PSNR ≥ 30, \|ΔAUC\|<1.5%, SalvageRate>55% |
| 5-theorem closure | ✅ 5/5 推导 done (实证待 Plan A) | Prop 1-3 + Lemma 1-3 + Thm 1-2 + Cor 1 全 publication-grade，详 `project/plans/{Theorem2,Prop3_Lemma3,Corollary1}*.md` |

---

## ⚠️ 永久红线（CLAUDE.md 复用）

1. Reader Study 数据**不可伪造** — 用 DCA + Triage simulation + 已发表 dermatologist baseline + LLM-judge protocol (§A23 disclaimer) 替代
2. **所有材料只能从网上公开资源获取** — 不联系诊所、不采集线下样本、不依赖人际网络
3. **不用扩散生成模型做皮肤镜增强**（伪影发明病灶，临床红线）
4. **数字凭印象写禁止** — 每个数字必须 csv 核算 + bootstrap 95% CI + run_id
5. **BMVC 数字不可直接搬入 ICLR**（必须重跑或 cite-as-paper）
