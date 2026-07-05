# 原则化 CV 融合选择 — 编码设计规格（planner 定稿 + skeptic 6🟠 落实）

> 服务 §3.3 fusion / §4.3 selection-bias。两脚本 `select_engine.py`(Part A) + `rationale_ablations.py`(Part B)。**不改 canonical / official R 脚本 / `fusion_nested_cv.py`。** 纯 numpy/pandas 禁 scipy.stats，seed=42。
> **诚实边界（写进每个 CSV 顶部注释）**：n=9 无"唯一最优"确定性证明；交付=无泄漏 CV 程序 + 选出的(成员×k×算子) + 稳定性/不可分带 + 每选择的受控证明。**措辞禁 "proven optimal/the best/SOTA"**；用「CV-最优 + 统计不可分带 + 入选频率」。

## 复用接口（import，不改）
- `fusion_nested_cv.py`：`guarded_perpat_metric(df,score,pats,caliber,*,return_perpat=False)`→`(rb,lo,hi,nu,nd[,rhos_by,ns_by])`（**所有 CV 一律走它，禁裸 per_patient**）；`cover_pool(df,tools,pats,cover_min=8)`；`guarded_bootstrap_ci(rhos_by,ns_by,pats,n_boot,seed)`；`guarded_paired_test(ra,na,rb,nb,pats,seed,n_perm=10000)`；`best_single(df,pool,pats,caliber)`；常量 SURV6/COVER_MIN=8/N_EFF_MIN=4/DEGEN_RHO=0.999/EPS=0.01/MAXDIM=6。
- `_official_common as C`：`apply_fusion(df,dim_cols,method,patients=)`、`UNSUPERVISED_FUSIONS`(8:geomean/mean_rank/median/powmean/max/min/weighted_mean_rank/softmax_rank)、`pool_col(t,'max')`、`present_patients`、`TOOLS_30`、`DTU_TOOLS`、`DS2_PATIENTS`、`fisherz_weighted_agg`、`spearman_np`。
- `_toolcorr_common`：`load_max_scores()`、`spearman_corr(scores)→(corr,dropped)`（130 肽 per-peptide Spearman，剔 DeepNetBim）。

## 必新增（在 select_engine.py 内，不改 fusion_nested_cv.py）
`fusion_score_op(df,members,pats,op)=C.apply_fusion(df,[C.pool_col(t,'max') for t in members],op,patients=pats)`；`greedy_members_op(df,pool,pats,caliber,eps,maxdim,op)`（同 greedy 逻辑但融合走 op）。其余程序（后向/穷举/topk/去相关）也在此新建，评分一律 guarded。

统一口径（Part A 全固定）：外层 LOPO 9 折；内层其余 8 患者选；pooling=`_max`；池=`cover_pool(≥8)`=24 工具；raw+lenctrl（raw 主，**lenctrl 只做固定 geomean 敏感性、不做联合选**=skeptic🟡）。CV-honest 预测装配：外层每折留出患者 p 填 `fusion_score_op(df,members_f,[p],op)`（within-patient 独立零泄漏），装满 130 行后 `guarded_perpat_metric(cv_pred)`。

---
## Part A（select_engine.py）

**A1 k 学习曲线**：`select_mode∈{greedy_to_k(关eps跑满k=1..8), exhaustive_topk(k≤3, 内层top-10 by单工具ρ̄, 穷举C(10,k))}`。oracle 对照=内层选集换全9患者(in-sample)。`inflation(k)=oracle−cv`。**top-10 预筛在内层8患者做，oracle臂在全9**。→ `k_curve.csv`: `k,caliber,select_mode,cv_rho,cv_ci_lo,cv_ci_hi,oracle_rho,inflation,n_folds_used,paired_p_vs_best_single,modal_members,member_stability_frac,note`。预期 cv 峰在 k=1(≈MHCnuggets 0.447)或小k，inflation 随k升。

**A2 联合选(子集×算子)**（skeptic🟠①三护栏必全做）：①报每算子分开的 subset-selected 曲线(8臂 `op_<name>_subsetsel`)；②`inflation_joint` vs `inflation_fixed_geomean`（若 joint>>fixed=算子DOF过拟合）；③两版 `op_set∈{all8, consensus3=geomean/mean_rank/median}`。arm 列取值 `joint_all8/joint_consensus3/fixed_geomean/op_<name>_subsetsel`。预期 cv_joint≤cv_fixed_geomean。

**A3 选择程序横比**（算子固定 geomean，隔离"程序"变量）：`forward_greedy`(复用greedy逻辑,eps=0.01,maxdim=6) / `backward_elim`(从top-N=12起,每步移除"移除后内层ρ̄最大"者,停在k) / `exhaustive_k≤3`(内层top-10穷举C(10,1..3)=175) / `topk_single`(内层单工具ρ̄ top-k,k=1..6) / `decorr_greedy`(见下)。→ `select_engine.csv`: `procedure,arm,op_set,lambda,caliber,k_selected,members_selected,cv_rho,cv_ci_lo,cv_ci_hi,oracle_rho,inflation,paired_p_vs_best_single,delta_vs_best_single,indistinguishable_set_size,interpretation`。

**去相关贪心**（skeptic🟠③堵两泄漏口）：`score(t)=ρ̄_inner(geomean(members+[t])) − λ·max_{s∈members}|corr(t,s)|`；corr 来自 `spearman_corr(load_max_scores())`，dump `tool_tool_corr.csv`(`tool_a,tool_b,spearman`)。首成员惩罚0；不在阵内(DeepNetBim)惩罚0。**λ 固定先验扫 {0.05,0.10,0.20} 主报0.10、每λ一行、绝不用外层ρ̄挑λ**。corr 阵全130肽算一次=**feature-feature 非标签泄漏**（注释显式声明这是label-free预处理放松，不 claim 零泄漏；严格版"每折内层8患者重算corr"列为可选变体注释）。

**A4 稳定性选择**（skeptic🟠①扩算子维）：外层9折×每折内层8患者 cluster bootstrap **B=200**(慢降100)跑 forward_greedy(geomean)记成员→入选频率=选中次数/(9×B)。共识阈 π∈{0.5,0.6(主),0.8}。**加算子churn**：若做联合选,记每折选中算子,报geomean占比/churn。→ `select_stability.csv`: `tool,category,is_dtu,select_freq_boot,select_freq_9fold,in_consensus_0p5,in_consensus_0p6,in_consensus_0p8,mean_single_rho_inner`；另一行块记 `operator_churn`(每算子被选折数)。

**A5 两个正交 null**（skeptic🟠④分列标死）：①**随机k-子集null**(控"从多子集挑"天花板)：每k从cover池随机抽R=1000子集,各算in-sample geomean ρ̄→null分布(mean/p95/max)。②**患者内置换null**(控选择泄漏vs信号)：患者内打乱Elispot→**重跑CHOSEN程序整条选择**(forward_greedy geomean),S=200→置换p。**只对CHOSEN程序跑置换,别全程序×全算子(会爆)**。→ `select_null.csv`: `null_type,k,R_or_S,null_mean,null_p95,null_max,observed_cv_rho,perm_p,caliber`。

**A6 赢家判决**（skeptic🟠②不宣称唯一最优）：CV最优 vs 最强单工具 `guarded_paired_test`+`guarded_bootstrap_ci(n_boot=2000)`。**统计不可分带**=枚举 A1/A2/A3 所有候选config的CV per-patient ρ向量,判"与CV最优不可分"=(a)`guarded_paired_test` p>0.05 或(b)bootstrap 95%CI重叠;报 `indistinguishable_set_size`+清单。**必报CV最优是否连MHCnuggets都区分不了**(预期不能→诚实结论小k/单工具足矣)。interpretation 用预登记口径:null写「无可检测的整合净优势」禁「证伪整合优势」。

---
## Part B（rationale_ablations.py）— 每条只变一处
统一固定(除被试):pool=cover(≥8)/op=geomean/procedure=forward_greedy/outer=leave-patient/metric=guarded/caliber=raw/seed=42。→ `rationale_ledger.csv`: `id,choice,fixed_vars,varied_var,chosen_value,alt_value,chosen_metric,alt_metric,delta,caliber,n_used,expected_direction,observed_verdict,why_oneline`。

- **#1** nested-CV vs oracle：varied=选择集{inner8|all9}。delta=oracle−cv=膨胀(≈0.17)。
- **#2** nested vs 单层LOPO（⚠️恒等陷阱,skeptic🟠⑤）：单层=全数据选成员+只LOPO评。**因geomean within-patient独立→单层LOPO≡oracle**,coder须显式断言 `abs(single_layer−oracle)<1e-9`,verdict写「全数据选+LOPO评≡in-sample,非真CV,膨胀同#1」。**不当独立数报**。
- **#3** 留患者 vs 留肽（⚠️只换折单元,skeptic🟠⑤）：alt=leave-peptide=**5折stratified-by-patient**(每患者肽均分5折),内层训练肽选成员,装配全130 out-of-fold→guarded。delta=留肽−留患者(预期>0=留肽泄漏患者内结构)。**承认bundle了折粒度,不claim纯单变量**。
- **#4** 守卫 vs 裸指标：varied=metric{guarded|裸 C.per_patient_spearman}。同best_single。预期裸选HLAthena 0.627,守卫0.207。
- **#5** cover池 vs 全30：metric=各自shuffle-null ρ̄。预期cover null≈0、全30 null>0(稀疏工具虚高)。
- **#6** Fisher-z vs 逆方差 vs 均值（⚠️只换聚合,skeptic🟠⑤）：**同一份 rhos_by/ns_by**(guarded return_perpat)三种聚合:equal/invvar/`np.nanmean(ρ向量)`。报点估+CI宽度。
- **#7** per-patient vs pooled（⚠️只换ρ口径）：同融合分。alt=`spearman_np(融合分_全130,Elispot_全130)`。delta预期背离。
- **#8** 贪心 vs 穷举（⚠️同池top-10同k同算子,只变搜索）：k=2,3。delta=exhaustive−greedy预期小。verdict**解耦**(skeptic🟡):只证"贪心是合格优化器",泛化由oracle−CV答,别混。
- **#9** ε/maxdim敏感性:扫eps{0,0.01,0.02}×maxdim{3,6,8}小网格,报峰位。verdict「峰稳→不靠调参」。
- **#10** 算子CV选 vs 钉geomean：delta=fixed_geomean−cvselect预期≥0(DOF伤CV)。
- **#11** DTU入池 vs 剔DTU：报两版结论+符号翻转(consent_critical)。
- **#12** 裸 vs 控肽长口径：报两口径CV最优/结论是否一致。
- **#13** geomean vs mean_rank/median/max_rank：同CV最优成员集只换算子。why=geomean共识/AND鲁棒。

## 算力(纯CPU)：A1/A3穷举秒级;A4 B=200≈1800贪心分钟级(慢降100);A5 S=200只跑CHOSEN;bootstrap n_boot=2000便宜。
## SURV6定位(skeptic🟠⑥)：报 fixed_surv6 vs CV最优 Δ+CI,大概率统计不可分=互证(SURV6可追溯selection-informed先验,CV正交数据驱动,一致=互证);差异量化成"SURV6的CV残差"非"SURV6错"。决策归袁+朱。
## 结论冲突=拍板点：CV说小k/单工具最优、SURV6无CV正当性 → 停下报袁老师+朱同学,不擅改canonical/headline。
