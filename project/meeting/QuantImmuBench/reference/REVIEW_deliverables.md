# Benchmark 交付物对抗审稿报告

> 服务 quantimmu-bench。reviewer(opus) 十角色对抗审 8 工具 benchmark 全套交付物，2026-06-24。前提：红队 🔴-1「pTuneos 最优统计不可区分」假定会改保守版，本报告专找这条以外的问题。数字一致性 verifier 已核 0 drift，本报告只攻方法学/呈现/完整性/措辞/许可。

## 总判
- **致命=1**(🔴-A 图表+文档双重误导，纯重画/改文档可修，不需重跑工具)。**重伤=4，跑偏=2。**
- **可否给袁老师**：补完 🔴-A + 两条跑偏措辞 → 可交付，质量从「会被一句话打回」升级「诚实防弹」。
- **能否对外(投稿/公开)**：**否**。三道硬门未过：①netMHCpan/DTU 书面同意未取 ②deepHLApan=GPL-2.0 公开需合规审 ③IEDB overlap 仍「待查」无实测。

## 🔴 致命
**🔴-A【图表+元审稿】fig6 红色基准线 + caterpillar 缺新工具 = 图表层把不稳健的 0.75 包装成确定性**
- `analysis/figures/fig6_8tools_auc_comparison.png`：y 轴从 0.3 截断(放大柱差) + 贯穿全图红线「pTuneos best (0.75)」当标尺 —— 正是红队判脆弱的三重最优角落点画成天花板基准，与保守 headline 直接打架。
- `figures_deepdive/fig_bootstrap_ci.png` + `bootstrap_ci_ds2.csv` **只有旧 5 工具**，缺 PRIME/ImmuneApp/deepHLApan。但「新 3 工具无增量」是全 8 工具排名声称 → 证据集(5)≠结论集(8)。
- **修**(纯重画<10 行)：fig6 删红线/标注 y 轴截断/柱叠 CI；caterpillar 补全 8 工具(新工具 CI 预期同样跨随机线，正面支撑「无增量」)，取代 fig6 进 PPT 当主图。

## 🟠 重伤
- **🟠-B【统计】阴性标签定义自相矛盾**：BENCHMARK_REPORT:13「n_neg=11(>0 切)」vs DEEPDIVE:63「11 负里只 1 个 ==0 其余 0<x≤10」打架。**主线已 Bash 核实真相**：DS2 阴性 11 = 1 个 ==0 + 10 个 <0(负 SFC 背景扣减=真无反应)，**DEEPDIVE:63 描述错**(非 0<x≤10)，阴性定义其实干净(≤0)。修 DEEPDIVE:63。
- **🟠-C【数据】IEDB overlap 全程「待查」无实测数**，污染单工具绝对分(尤其要进 PPT 推荐的 pTuneos)。修：32178 肽 vs IEDB 精确+9mer match 报 overlap%(coder 已写 `iedb_overlap_check.py` 待主线跑，需先下 IEDB csv)。
- **🟠-D【复现】「5/5 全部署+跑通」与逐工具实况不符**：REPORT:28 headline 说 5/5 跑通，但 IMPROVE=仅 Predict 步、NeoTImmuML=自训版(从未产官方分)、pTuneos=Pre&RecNeo 子模型。修：headline 改「均产出可进 benchmark 分数；DeepImmuno/PredIG 完整端到端，IMPROVE/NeoTImmuML/pTuneos 为子模型/降级/自训版」。**NeoTImmuML 0.655 进排名表必须标星「自训版非官方」**。
- **🟠-E【新颖性】ensemble 0.81 点估诱人但已自证不显著**，防被单独摘进 PPT。任何组合数字进 PPT 必带「点估略高、统计不显著、需 n_neg≥30 再验」。唯一显著配对 = pTuneos-IMPROVE(CI[0.006,0.287])。

## ⛔ 跑偏命中
- **⛔-F【反跑偏】绝对化措辞「无可替代/最强」超 n_neg=11 证据**：IMPROVE「Spearman 0.320 无可替代」、pTuneos「仍最强」。改「在本 DS2 上 IMPROVE 定量相关性最高且唯一稳定显著(但样本小 CI 宽)」，删「无可替代/最强」。
- **⛔-G【许可/反跑偏】DEEPDIVE:67「纳 DS1 合并扩负例」与「DS1 全阳无阴性」冲突**：DS1 一个阴性都没有(主线核实 82 肽全 >10)，合并只会让不平衡更糟。**删 DEEPDIVE:67「或纳 DS1 合并」**，扩负例唯一正路=袁老师补真实 ELISpot 阴性肽。

## 🟡 小问题
- BENCHMARK_8TOOLS:96 vs 98「0.056 vs 0.055」(csv 实算 0.0555)统一 0.055。
- 排名表我们自训的 NeoTImmuML 应加星脚注。
- TOOLS 卡完整性：HLAthena.md 输入/参数/输出/样例多为 TODO(只 proxy-smoke 没全跑)；ImmuneApp/deepHLApan 各 3 TODO。PPT 若要 10 工具齐全，HLAthena/MHLAPre 实测列基本空，需诚实标「未部署/proxy 仅烟测」别和跑通的 8 张同成色。

## 十角色一句话裁决
1.统计→🔴-A+🟠-B 2.领域→🟠-D(自训/子模型当官方排名) 3.复现→🟠-D 4.伦理许可→对外 gate+⛔-G 5.图表→🔴-A 6.写作→⛔-F+🟡 7.新颖性→🟠-E 8.临床转化→🟠-C+🟠-B 9.数据→🟠-C+🟠-B 10.元审稿→🔴-A+🟠-E。

## 收口
致命=1(🔴-A 纯图表+文档可修)。核心病灶与红队 🔴-1 同根(小样本把点估当结论)，但渗进 ①fig6 红线 ②5 工具 caterpillar ③IMPROVE「无可替代」④ensemble 0.81。四处+headline 一起改保守版，补全 8 工具 caterpillar + 修阴性定义(🟠-B 已查) + IEDB overlap 给数(🟠-C) + NeoTImmuML/pTuneos 标自训/子模型(🟠-D)，交付即「诚实防弹」，且保守版更强化袁立项动机。
**待修文件**：figures/fig6_8tools_auc_comparison.png、figures_deepdive/fig_bootstrap_ci.png+bootstrap_ci_ds2.csv、DEEPDIVE_8tools.md(63/67)、BENCHMARK_REPORT.md(13)、REPORT.md(28)、BENCHMARK_8TOOLS.md(§5/6 措辞+NeoTImmuML 星)、TOOLS/HLAthena.md。
