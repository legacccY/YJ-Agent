
<div class="omv-content markdown-body github-markdown-body" data-color-mode="auto" data-light-theme="light" data-dark-theme="dark" style="--omv-active-inline-code-bg: rgb(43, 43, 43); --omv-active-inline-code-fg: rgb(208, 208, 208); --omv-active-inline-code-radius: 4px; --omv-active-pre-bg: rgb(43, 43, 43); --omv-active-pre-border: rgb(43, 43, 43); --omv-active-pre-fg: rgb(208, 208, 208); --omv-active-pre-radius: 8px; --omv-code-bg: rgb(43, 43, 43); --omv-code-fg: rgb(208, 208, 208); --omv-mermaid-accent: rgb(77, 170, 252); --omv-mermaid-border: rgb(43, 43, 43); --omv-mermaid-muted: rgb(157, 157, 157); --omv-mermaid-panel-bg: rgb(43, 43, 43); --omv-mermaid-viewport-bg: rgb(43, 43, 43);">
<div class="github-markdown-content">
<h1 id="quanimmu-briefings-in-bioinformatics-" tabindex="-1" data-source-line="0" data-source-line-end="1">QuanImmu —— 论文大纲（Briefings in Bioinformatics 投稿版）<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#quanimmu-briefings-in-bioinformatics-" class="omv-heading-anchor" title="Copy heading link">#</a></h1>
<blockquote>
<p data-source-line="2" data-source-line-end="3">本文件是面向 <strong>Briefings in Bioinformatics (BiB)</strong> 的论文结构大纲。BiB 偏好「系统性评估 / benchmark / problem-solving protocol」类工作，恰好匹配本项目"系统评测 30 种工具 + 提出定量整合框架"的定位。</p>
<p data-source-line="4" data-source-line-end="5">全文以 <strong>Spearman 秩相关</strong>为主指标，<strong>Pearson 作为附表/补充材料</strong>呈现（与项目既定口径一致）。结果同时覆盖**人源（ds1、ds2）与小鼠（B16F10、CT26）**数据。</p>
</blockquote>
<hr data-source-line="6" data-source-line-end="7">
<h2 id="0-" tabindex="-1" data-source-line="8" data-source-line-end="9">0. 候选标题（请从中择一，或在此基础上微调）<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#0-" class="omv-heading-anchor" title="Copy heading link">#</a></h2>
<p data-source-line="10" data-source-line-end="11">原标题 <em>A quantitative framework for mutation-level assessment of neoantigen immunogenicity</em> 的问题：过于宽泛、未体现"系统评测 30 种工具"这一最大卖点、缺少记忆点（无方法名）。</p>
<p data-source-line="12" data-source-line-end="13">候选：</p>
<ol>
<li>⭐ <strong>QuantImmu: a quantitative, mutation-level framework for benchmarking and integrating neoantigen immunogenicity predictors</strong></li>
<li><strong>From peptide–allele scores to mutation-level immunogenicity: benchmarking 30 presentation and immunogenicity tools under a unified quantitative framework</strong></li>
<li><strong>Pooling and rank-fusion strategies for quantitative, mutation-level neoantigen immunogenicity prediction: a systematic benchmark of 30 tools</strong></li>
</ol>
<blockquote>
<p data-source-line="18" data-source-line-end="19">三个卖点必须出现在标题/摘要：<strong>quantitative（连续强度，非二分类）</strong>、<strong>mutation-level（突变级，非肽–分型级）</strong>、<strong>30-tool systematic benchmark（10 呈递 + 20 免疫原性）</strong>。</p>
</blockquote>
<hr data-source-line="20" data-source-line-end="21">
<h2 id="abstractbib-250300-" tabindex="-1" data-source-line="22" data-source-line-end="23">Abstract（结构化摘要，BiB 常用 250–300 词）<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#abstractbib-250300-" class="omv-heading-anchor" title="Copy heading link">#</a></h2>
<p data-source-line="24" data-source-line-end="25">按 BiB 习惯可分 4 小段：</p>
<ul>
<li><strong>Motivation / Background</strong>：神经抗原免疫原性预测对个体化肿瘤疫苗至关重要；现有工具绝大多数做<strong>二分类（免疫原 / 非免疫原）<strong>并以 AUC 评测，且工作在</strong>肽–HLA 层</strong>；但临床需求是在一个病人的几十个<strong>突变</strong>里做<strong>定量精细排序</strong>（谁更值得做疫苗）。两者之间存在系统性错配。</li>
<li><strong>Results</strong>：我们提出 <strong>QuantImmu</strong>，一个把任意上游工具输出转成<strong>突变级定量免疫原性分</strong>的统一框架（逐行打分 → pooling → rank-fusion 三步）。在此框架下系统评测 <strong>30 种工具（10 呈递 + 20 免疫原性）</strong>，跨<strong>人（ds1/ds2）与小鼠（B16F10/CT26）</strong>、以 ELISpot 为真值、用 <strong>Spearman</strong> 评测。给出三层结论：(i) 单工具 max-pooling 基线；(ii) 单工具 4 种 pooling 的系统比较与<strong>工具类别决定最优 pooling</strong>的规律；(iii) 12 种 fusion 整合多工具，配合 <strong>ablation、nested-LOPO、随机删 10%/20% 鲁棒性</strong>三重严格检验。</li>
<li><strong>Key findings</strong>：pooling 会<strong>重排</strong>工具优劣（结合/亲和力类靠 top-k 聚合近翻倍，免疫原性类在 max 即达峰）；<strong>geomean rank-fusion</strong> 是唯一通过跨配置复现性与删突变鲁棒性双重检验的整合法则；在样本有限时整合相对最强单工具的增量统计上持平——因此我们给出<strong>以鲁棒性而非点估计为准</strong>的部署建议。</li>
<li><strong>Availability</strong>：全部代码与脚本开源（见 Code Availability），框架可即插即用任意新工具。</li>
</ul>
<p data-source-line="31" data-source-line-end="32"><strong>Keywords</strong>：neoantigen; immunogenicity prediction; MHC/HLA presentation; benchmarking; rank fusion; ELISpot; tumor vaccine.</p>
<hr data-source-line="33" data-source-line-end="34">
<h2 id="1-introduction" tabindex="-1" data-source-line="35" data-source-line-end="36">1. Introduction<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#1-introduction" class="omv-heading-anchor" title="Copy heading link">#</a></h2>
<p data-source-line="37" data-source-line-end="38">1.1 <strong>临床背景</strong>：个体化肿瘤新抗原疫苗流程（突变检出 → 候选肽 → 优先级排序 → 合成/接种），排序质量直接决定疫苗成败。</p>
<p data-source-line="39" data-source-line-end="40">1.2 <strong>现状与两个错配（本文的 gap）</strong>：</p>
<ul>
<li><strong>错配一：二分类 vs 定量</strong>。主流工具（DeepImmuno、IEDB immunogenicity、deephlapan、PRIME 等）把免疫原性建模为二分类、用 AUC/准确率评测；但免疫原性本是<strong>连续强度</strong>，临床要的是精细排序 → 应以 <strong>Spearman</strong> 衡量。</li>
<li><strong>错配二：肽–HLA 层 vs 突变层</strong>。工具在「肽–等位基因」对上打分，但一个突变对应多条候选肽–HLA 行；临床决策单元是<strong>突变</strong>。如何把多行**聚合（pooling）**到突变级，是一个被忽视但关键的方法学选择。</li>
</ul>
<p data-source-line="43" data-source-line-end="44">1.3 <strong>第三个 gap：缺乏统一、公平、定量的系统评测</strong>。已有 benchmark 多在二分类/肽层、且工具数有限；缺少一个把 30 种异质工具放在<strong>同一突变级定量口径</strong>下、用<strong>统一无泄漏协议</strong>比较并研究<strong>如何最优整合</strong>的工作。</p>
<p data-source-line="45" data-source-line-end="46">1.4 <strong>本文贡献（三条，与标题呼应）</strong>：</p>
<ol>
<li>提出 <strong>QuantImmu</strong> —— 一个**定量（quantitative）**评估免疫原性的统一框架（三步范式 + 无泄漏 LOPO 协议）。</li>
<li>把评估从<strong>肽–分型层提升到突变层（mutation-level）</strong>，并系统刻画 pooling 这一关键步骤。</li>
<li><strong>系统评测 30 种免疫原性相关工具（10 种呈递预测 + 20 种免疫原性预测）</strong>，跨人/鼠数据，给出单工具、单工具×pooling、多工具×fusion 三层完整结果与严格鲁棒性检验。</li>
</ol>
<p data-source-line="50" data-source-line-end="51">1.5 <strong>Roadmap</strong>：本文结构概述（指向各 Results 小节）。</p>
<hr data-source-line="52" data-source-line-end="53">
<h2 id="2-materials-and-methods" tabindex="-1" data-source-line="54" data-source-line-end="55">2. Materials and Methods<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#2-materials-and-methods" class="omv-heading-anchor" title="Copy heading link">#</a></h2>
<h3 id="21-datasets-" tabindex="-1" data-source-line="56" data-source-line-end="57">2.1 Datasets（人 + 鼠）<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#21-datasets-" class="omv-heading-anchor" title="Copy heading link">#</a></h3>
<ul>
<li><strong>人源 ds1</strong>（<code>human_ELSpot_dataset_1/</code>）：netMHCpan + PRIME 合并结果，作为人源补充/复现集。</li>
<li><strong>人源 ds2</strong>（<code>human_ELISpot_dataset_2/</code>，<strong>主分析集</strong>）：9 个病人（P101–P110），多工具各自 xlsx；统一口径为 <strong>inference 子集（92 突变 / 8 有效病人</strong>，P102 在 inference 中近缺席）。</li>
<li><strong>小鼠 B16F10 / CT26</strong>（<code>*_M1/M2/M3.xlsx</code> 及 Merged 版本）：结构最干净的经典范式，含 BigMHC_IM、PRIME 合并版。</li>
<li><strong>真值（ground truth）</strong>：ELISpot 反应（斑点数）；标签列 <code>Elispot</code>。</li>
<li><strong>聚合键（突变定义）</strong>：小鼠 <code>27AA_Sequence_MT</code>；人 <code>Patient_ID|Peptide_ID</code>（<code>mut_key</code>）。</li>
<li>表 1：数据集汇总（物种、病人/样本数、有标签突变数、肽–HLA 行数、覆盖的工具）。</li>
</ul>
<h3 id="22-the-30-tools-surveyed" tabindex="-1" data-source-line="64" data-source-line-end="65">2.2 The 30 tools surveyed（核心资产，需一张完整表）<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#22-the-30-tools-surveyed" class="omv-heading-anchor" title="Copy heading link">#</a></h3>
<ul>
<li><strong>表 2（关键表）</strong>：30 种工具清单，分两类列出——
<ul>
<li><strong>10 种呈递预测（presentation/binding）</strong>：如 netMHCpan(Aff/BA/EL)、netMHCpan 可变窗、MAAP、MHCflurry、NetMHCstabpan、BigMHC_EL 等（按实际接入填写）。</li>
<li><strong>20 种免疫原性预测（immunogenicity）</strong>：如 PRIME、deephlapan(Imm/Bind)、PredIG、DeepImmuno、IEDB immunogenicity、BigMHC_IM、内部 Inference 8-class、Seq2Neo、DeepNeo 等（按实际接入填写）。</li>
<li>每行标注：输出分名、原生任务（二分类/连续/概率）、是否提供 MT/WT、9mer vs 可变窗、引用文献。</li>
</ul>
</li>
<li><strong>9mer vs 可变窗口径说明</strong>：同工具 <code>9AAonly</code> 一致优于可变窗（4/4），全文主分析用 9AA，可变窗入补充。</li>
<li>
<blockquote>
<p data-source-line="70" data-source-line-end="71">⚠️ <strong>写作待办</strong>：当前仓库已接入约 14 个分数源；投稿前需补齐到 30。表 2 留占位，逐一接入后填数。</p>
</blockquote>
</li>
</ul>
<h3 id="23-the-quantimmu-framework-" tabindex="-1" data-source-line="72" data-source-line-end="73">2.3 The QuantImmu framework（三步范式 —— 方法学主体）<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#23-the-quantimmu-framework-" class="omv-heading-anchor" title="Copy heading link">#</a></h3>
<ul>
<li><strong>Step 1 逐行打分 + 定向（orientation）</strong>：每条肽–HLA 行取标量并统一成"越大越免疫原"；亲和力取 <code>−Aff(nM)</code>；可选 **DAI（MT vs WT）**两形式：相减型 <code>max(MT−WT,0)</code>、对数比值型 <code>max(log₂(Aff_WT/Aff_MT),0)</code>。</li>
<li><strong>逐病人归一化（无泄漏）</strong>：min-shift + RMS（<code>y=x−min</code>，<code>y/√mean(y²)</code>），仅用病人自身特征、不碰标签/他人 → CV 无泄漏基础。</li>
<li><strong>Step 2 pooling（多行 → 突变级 1 分）</strong>：四法 <strong>max / topk_w(k,α) / softmax(T) / rankdecay(γ)</strong>（公式 + 超参网格，见表 3）。</li>
<li><strong>Step 3 fusion（多维 rank → 综合分）</strong>：各维病人内转 rank，再融合（mean-rank、geomean 等，详见 §2.5）。</li>
</ul>
<h3 id="24-pooling-methods-3" tabindex="-1" data-source-line="78" data-source-line-end="79">2.4 Pooling methods（表 3）<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#24-pooling-methods-3" class="omv-heading-anchor" title="Copy heading link">#</a></h3>
<table data-source-line="79" data-source-line-end="85">
<thead>
<tr>
<th>pooling</th>
<th>公式</th>
<th>超参 / 网格</th>
</tr>
</thead>
<tbody>
<tr>
<td>max</td>
<td>s=v₁</td>
<td>无</td>
</tr>
<tr>
<td>topk_w</td>
<td>s=Σwᵣvᵣ/Σwᵣ, wᵣ=r^(−α), 前 k</td>
<td>k∈{1,2,3,5,8,10,20,50,100}×α∈{0,0.5,1,2}</td>
</tr>
<tr>
<td>softmax</td>
<td>s=Σe^(vᵣ/T)vᵣ/Σe^(vᵣ/T)</td>
<td>T∈{0.03,0.05,0.1,0.2,0.5,1,2}</td>
</tr>
<tr>
<td>rankdecay</td>
<td>s=Σwᵣvᵣ/Σwᵣ, wᵣ=1/log(r+γ)</td>
<td>γ∈{1,1.5,2,3,5,10,20}</td>
</tr>
</tbody>
</table>
<h3 id="25-fusion-methods12-3-" tabindex="-1" data-source-line="86" data-source-line-end="87">2.5 Fusion methods（12 种 —— 对应贡献 3 的整合部分）<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#25-fusion-methods12-3-" class="omv-heading-anchor" title="Copy heading link">#</a></h3>
<ul>
<li>列全 <strong>12 种 fusion</strong>（mean-rank、geomean、median、powmean、max、min、加权变体、softmax-rank、stacking/线性回归、constrained 等 —— 按 <code>fourdim_cls2_aggregation.py</code> / <code>robustness_7dim_fusions.py</code> / <code>nested_lopo_ensemble.py</code> / <code>stacking_lopo.py</code> 实际枚举填表 4）。</li>
<li>重点定义 <strong>geomean rank-fusion</strong>（共识/AND 型聚合）及其与 max（OR 型）的对立直觉。</li>
</ul>
<h3 id="26-evaluation-protocol" tabindex="-1" data-source-line="90" data-source-line-end="91">2.6 Evaluation protocol（严格性是本文的卖点之一）<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#26-evaluation-protocol" class="omv-heading-anchor" title="Copy heading link">#</a></h3>
<ul>
<li><strong>主指标</strong>：per-patient <strong>Spearman</strong>(预测分, ELISpot)，跨有效病人<strong>等权平均</strong>；<strong>Pearson 作为对照入补充表</strong>。</li>
<li><strong>Nested LOPO（Leave-One-Patient-Out）</strong>：外层留一病人评测，内层用其余病人选超参 θ → 无泄漏 test 表现；报告 <strong>oracle vs LOPO</strong>（相等 = 零过拟合）。</li>
<li><strong>Ablation</strong>：维度留一（leave-one-dimension-out）、加权方式对比。</li>
<li><strong>Robustness</strong>：随机删 <strong>10% 与 20%</strong> 突变 × 多组固定种子，比较<strong>子采样均值/中位/胜率</strong>而非单点（区分真信号与配置专属噪声）。</li>
<li><strong>Significance</strong>：方法间<strong>配对显著性检验</strong>（病人为配对单元），明确报告"持平 vs 显著"。</li>
</ul>
<h3 id="27-implementation" tabindex="-1" data-source-line="97" data-source-line-end="98">2.7 Implementation<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#27-implementation" class="omv-heading-anchor" title="Copy heading link">#</a></h3>
<ul>
<li>Python（numpy/pandas/scipy/openpyxl），无 build step；<code>score_pooling_lopo.py</code> 为 ds2 公共库（load/build/POOLERS）；<code>camp.py</code> 为小鼠参考实现。脚本↔图表映射见附录 A。</li>
</ul>
<hr data-source-line="100" data-source-line-end="101">
<h2 id="3-results" tabindex="-1" data-source-line="102" data-source-line-end="103">3. Results<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#3-results" class="omv-heading-anchor" title="Copy heading link">#</a></h2>
<blockquote>
<p data-source-line="104" data-source-line-end="105">三层递进，与你列的"主要结果"逐条对应。每一小节都给出<strong>人 + 鼠</strong>结果，主图 Spearman、附表附 Pearson。</p>
</blockquote>
<h3 id="31-max-pooling-3-" tabindex="-1" data-source-line="106" data-source-line-end="107">3.1 单工具 max-pooling 基线比较（贡献 3 / 结果 ①）<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#31-max-pooling-3-" class="omv-heading-anchor" title="Copy heading link">#</a></h3>
<ul>
<li><strong>图 1 / 表 5</strong>：30 工具在 max-pool（无超参 → LOPO==oracle==均值）下的突变级 Spearman，人/鼠分面。</li>
<li>关键发现（ds2 已知）：仅 max 时<strong>免疫原性分领先</strong>（PRIME +0.286、deephlapan_Imm +0.280、PredIG +0.322、Inference class_2/3 +0.31），<strong>亲和力垫底</strong>（netAffneg +0.196）。</li>
<li>小鼠对照：B16F10/CT26 上的工具排名（指出物种间一致/差异）。</li>
</ul>
<h3 id="32-4-pooling-" tabindex="-1" data-source-line="111" data-source-line-end="112">3.2 单工具 × 4 种 pooling 比较（结果 ②）<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#32-4-pooling-" class="omv-heading-anchor" title="Copy heading link">#</a></h3>
<ul>
<li><strong>图 2（核心"洗牌"图）</strong>：每工具 max vs 最优 pooling 的提升；按工具类别着色。</li>
<li>关键发现：<strong>pooling 重排工具优劣</strong>——<code>netAffneg_9</code> 经 <strong>top-20 等权平均（k=20,α=0）跃居单工具第一 +0.3946</strong>（max 时仅 +0.196）。</li>
<li><strong>沉淀为领域规律（本文一个可推广结论）</strong>：
<ul>
<li><strong>结合/亲和力类（netMHCpan Aff/BA/EL、MAAP）→ 要"聚合"</strong>（大 k、α=0 的 top-k 等权平均，信号近翻倍）；</li>
<li><strong>免疫原性类（PRIME/deephlapan/PredIG）→ 要"取最强"</strong>（max 即最优）；</li>
<li><strong>概率类（Inference）→ 取最强</strong>。</li>
</ul>
</li>
<li>人/鼠是否复现该规律（跨物种泛化讨论）。</li>
</ul>
<h3 id="33-12-fusion-" tabindex="-1" data-source-line="120" data-source-line-end="121">3.3 多工具整合：12 种 fusion + 三重严格检验（结果 ③，本文方法学高潮）<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#33-12-fusion-" class="omv-heading-anchor" title="Copy heading link">#</a></h3>
<ul>
<li><strong>3.3.1 12 种 fusion 对比</strong>：表 6，多维（3/4/6/7 维）下 12 种 fusion 的 LOPO Spearman；发现 <strong>geomean</strong> 突出。</li>
<li><strong>3.3.2 Ablation test</strong>：
<ul>
<li>维度留一（leave-one-dimension-out，表 7）：哪个维度最"承重"（ds2：<strong>deephlapan_Imm 最承重</strong>，因与亲和力/PRIME 最正交）；</li>
<li>加权 ablation：4 种加权方式 → <strong>加权一律塌回等权</strong>（不帮忙）。</li>
</ul>
</li>
<li><strong>3.3.3 Nested-LOPO</strong>：表 8，整合 vs 最强单工具的无泄漏对比；报告 oracle/LOPO 一致性。</li>
<li><strong>3.3.4 Robustness（删 10% / 20%）</strong>：
<ul>
<li><strong>图 3 / 表 9</strong>：7 维 × fusion 的子采样均值——<strong>geomean 在 10%（+0.4643）与 20%（+0.4488）双双第一</strong>；<code>max</code> 满数据虚高（+0.4834）但子采样塌陷（反面教材：点估计陷阱）。</li>
<li><strong>跨维复现性</strong>：geomean 是唯一在 3/4/6/7 维一致 ≥ mean 的 fusion（max/powmean 不可复现）→ 判定 geomean 为真信号的关键检验。</li>
</ul>
</li>
<li><strong>3.3.5 显著性现实检验（必须诚实呈现）</strong>：配对检验显示整合相对最强单工具<strong>统计持平</strong>（ds2：Δ≈+0.038、p≈0.70、主要由单一病人 P101 驱动）；强调"排名次序 ≠ 显著差异"。</li>
</ul>
<h3 id="34-" tabindex="-1" data-source-line="131" data-source-line-end="132">3.4 综合排名与部署建议（把"持平"转化为可操作结论）<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#34-" class="omv-heading-anchor" title="Copy heading link">#</a></h3>
<ul>
<li><strong>图 4 / 表 10</strong>：全方法统一 LOPO 排名（人 + 鼠）。</li>
<li>因统计持平 → <strong>按"零过拟合 + 依赖最少 + 鲁棒 + 可解释"选</strong>，给两条方案：
<ol>
<li><strong>务实默认</strong>：单 affinity pooling（<code>netAffneg_9 topk k=20,α=0</code>，仅依赖 netMHCpan、最稳、零过拟合）。</li>
<li><strong>按需备选</strong>：多维 free-pooling + <strong>geomean</strong>（点估计与鲁棒性双优，代价是多管线依赖）。</li>
</ol>
</li>
<li>部署实例：<code>rank_T01_deploy.py</code> 对无标签病人（T01/T04）排序。</li>
</ul>
<hr data-source-line="138" data-source-line-end="139">
<h2 id="4-discussion" tabindex="-1" data-source-line="140" data-source-line-end="141">4. Discussion<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#4-discussion" class="omv-heading-anchor" title="Copy heading link">#</a></h2>
<p data-source-line="142" data-source-line-end="143">4.1 <strong>方法学要点</strong>：定量 + 突变级 + pooling/fusion 是三个常被忽视但影响结论的设计轴；本文给出可推广的 pooling 类别规律与 geomean fusion 法则。</p>
<p data-source-line="144" data-source-line-end="145">4.2 <strong>为什么 Spearman≈0.4 是有竞争力的信号（而非"弱相关"）</strong>：跨病人平均显著优于随机（t≈4.8、p&lt;0.01）；神经抗原免疫原性是公认极难问题。注意事项：per-patient 在 0.17–0.80 剧烈波动、榜单顶端仍有假阳性 → 当<strong>强力排序输入</strong>用，非唯一裁判。</p>
<p data-source-line="146" data-source-line-end="147">4.3 <strong>诚实的局限（Limitations，BiB 审稿很看重）</strong>：</p>
<ul>
<li>整合 vs 最强单工具<strong>不显著</strong>（样本小、单病人驱动）；</li>
<li><strong>设计层 selection bias 未进 CV</strong>（用哪些工具/类别/pooling 菜单是看全数据定的）→ 整合数字偏乐观；</li>
<li>仅 8 有效病人（ds2）→ ±0.03–0.05 差异难言显著；</li>
<li>CV 协议本身无泄漏（正面），问题在样本量 + 人为选择；</li>
<li>所有增量结论<strong>待外部独立队列验证</strong>。</li>
</ul>
<p data-source-line="153" data-source-line-end="154">4.4 <strong>Future work</strong>：</p>
<ul>
<li><strong>HLA II 型</strong>：将框架扩展到 MHC-II 呈递与 CD4⁺ 免疫原性预测（呈递 + 免疫原性双任务）；</li>
<li>更大规模、多中心 ELISpot 队列的外部验证；</li>
<li>把框架做成可即插即用任意新工具的标准评测平台。</li>
</ul>
<hr data-source-line="158" data-source-line-end="159">
<h2 id="5-key-pointsbib-35-" tabindex="-1" data-source-line="160" data-source-line-end="161">5. Key Points（BiB 要求的 3–5 条要点框）<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#5-key-pointsbib-35-" class="omv-heading-anchor" title="Copy heading link">#</a></h2>
<ul>
<li>神经抗原免疫原性应作<strong>连续强度在突变层</strong>定量评估（Spearman），而非肽层二分类（AUC）。</li>
<li>pooling 的选择会<strong>系统性重排</strong>工具优劣：结合类要聚合、免疫原性类要取最强。</li>
<li>在 30 种工具上，<strong>geomean rank-fusion</strong> 是唯一通过跨配置复现性 + 删突变鲁棒性双重检验的整合法则。</li>
<li>样本有限时整合相对最强单工具<strong>统计持平</strong>；部署应按鲁棒性而非点估计选择。</li>
<li>框架开源、可扩展至任意新工具及 HLA-II。</li>
</ul>
<hr data-source-line="168" data-source-line-end="169">
<h2 id="6-" tabindex="-1" data-source-line="170" data-source-line-end="171">6. 论文常规部分（投稿必备）<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#6-" class="omv-heading-anchor" title="Copy heading link">#</a></h2>
<ul>
<li><strong>Author Contributions</strong></li>
<li><strong>Funding</strong></li>
<li><strong>Data Availability</strong>：ELISpot 数据来源与可获取性声明（人源数据的伦理/获取限制需注明）。</li>
<li><strong>Code Availability</strong>：开源仓库链接；列出关键脚本（<code>camp.py</code>、<code>score_pooling_lopo.py</code>、<code>robustness_7dim_fusions.py</code> 等）与复现说明。</li>
<li><strong>Conflict of Interest</strong></li>
<li><strong>Acknowledgements</strong></li>
<li><strong>References</strong>（30 工具各自的原始文献 + benchmark/方法学引用）</li>
</ul>
<hr data-source-line="180" data-source-line-end="181">
<h2 id="7-figures-tables-" tabindex="-1" data-source-line="182" data-source-line-end="183">7. Figures &amp; Tables 清单（投稿打包用）<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#7-figures-tables-" class="omv-heading-anchor" title="Copy heading link">#</a></h2>
<p data-source-line="184" data-source-line-end="185"><strong>主图（建议 4–5 张）</strong></p>
<ul>
<li>图 1：30 工具 max-pool 基线（人/鼠分面）。</li>
<li>图 2：pooling "洗牌"图（max vs 最优 pooling，按类别着色）。← 核心</li>
<li>图 3：fusion 鲁棒性（10% vs 20% 子采样均值，geomean 双第一）。← 核心</li>
<li>图 4：全方法统一 LOPO 排名 + 部署方案标注。</li>
<li>（可选）图 5：框架示意图（三步范式 schematic，放 §2 开头）。</li>
</ul>
<p data-source-line="191" data-source-line-end="192"><strong>主表</strong></p>
<ul>
<li>表 1 数据集汇总；表 2 <strong>30 工具清单（10+20）</strong>；表 3 pooling 网格；表 4 12 fusion 定义；表 5 单工具 max 基线；表 6 多维 fusion 对比；表 7 维度 ablation；表 8 nested-LOPO；表 9 删突变鲁棒性；表 10 统一排名。</li>
</ul>
<p data-source-line="194" data-source-line-end="195"><strong>补充材料（Supplementary）</strong></p>
<ul>
<li>全部 <strong>Pearson</strong> 对照表；可变窗（mw）口径结果；ds1 复现；逐病人 Spearman 分布（0.17–0.80）；30 组随机种子明细；配对检验完整统计。</li>
</ul>
<hr data-source-line="197" data-source-line-end="198">
<h2 id="-a-" tabindex="-1" data-source-line="199" data-source-line-end="200">附录 A：脚本 ↔ 结果章节映射（复现索引）<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#-a-" class="omv-heading-anchor" title="Copy heading link">#</a></h2>
<table data-source-line="201" data-source-line-end="212">
<thead>
<tr>
<th>论文小节</th>
<th>主要脚本</th>
<th>产物</th>
</tr>
</thead>
<tbody>
<tr>
<td>§3.1 单工具 max</td>
<td><code>score_pooling_subset.py</code></td>
<td><code>score_pooling_subset92_results.csv</code></td>
</tr>
<tr>
<td>§3.2 单工具×pooling</td>
<td><code>score_pooling_lopo.py</code>, <code>inference_scan_subset92.py</code>, <code>predig_subset_eval.py</code></td>
<td><code>*_results.csv</code></td>
</tr>
<tr>
<td>§3.3.1 多维 fusion</td>
<td><code>fourdim_cls2_aggregation.py</code>, <code>inference_integration_variants.py</code></td>
<td><code>*_results.csv</code></td>
</tr>
<tr>
<td>§3.3.2 ablation</td>
<td><code>sixdim_ablation_weights.py</code>, <code>ablation_7dim_geomean_robust*.py</code></td>
<td><code>*_results.csv</code></td>
</tr>
<tr>
<td>§3.3.3 nested-LOPO</td>
<td><code>nested_lopo_ensemble.py</code>, <code>cross_dataset_lopo.py</code>, <code>constrained_nested.py</code></td>
<td><code>*.result/.csv</code></td>
</tr>
<tr>
<td>§3.3.4 robustness</td>
<td><code>robustness_subsample.py</code>, <code>robustness_7dim_fusions*.py</code>, <code>robustness_fusion_reproducibility*.py</code></td>
<td><code>*_results.csv</code></td>
</tr>
<tr>
<td>§3.3.5 显著性</td>
<td><code>_audit_paired.py</code>, <code>geomean_vs_mean_paired.py</code></td>
<td>—</td>
</tr>
<tr>
<td>§3.4 部署</td>
<td><code>rank_T01_deploy.py</code>, <code>rank_T01_GATK.py</code>, <code>rank_T04_GATK.py</code>, <code>frozen_pipeline.py</code></td>
<td><code>T0*_ranking_report.md</code></td>
</tr>
<tr>
<td>小鼠</td>
<td><code>camp.py</code>, <code>compare_models.py</code>, <code>quantimmu4*.py</code>, <code>mouse_window_compare.py</code></td>
<td><code>*.result/.md</code></td>
</tr>
</tbody>
</table>
<blockquote>
<p data-source-line="213" data-source-line-end="214">权威技术细节以 <code>six_dim_model_report.md</code> 与 <code>QuantImmu项目说明.md</code> 为准。</p>
</blockquote>
<hr data-source-line="215" data-source-line-end="216">
<h2 id="-b-to-do-checklist" tabindex="-1" data-source-line="217" data-source-line-end="218">附录 B：投稿前 to-do（写作 checklist）<a href="file:///D:/Weixin_Data/xwechat_files/wxid_nc73h92iwwpg22_899b/msg/file/2026-06/QuanImmu-Paper-Outline.html#-b-to-do-checklist" class="omv-heading-anchor" title="Copy heading link">#</a></h2>
<ol>
<li><strong>补齐 30 工具</strong>：当前仓库约 14 个分数源 → 接入至 10 呈递 + 20 免疫原性，填表 2/表 5。</li>
<li><strong>统一人/鼠口径</strong>：确认四个数据集都跑通同一三步范式 + nested-LOPO，避免口径不一致。</li>
<li><strong>Pearson 全量补充</strong>：主文 Spearman、补充材料补全 Pearson 对照（满足"同时呈现"）。</li>
<li><strong>显著性诚实呈现</strong>：所有"第一/最优"措辞旁注明是否统计显著。</li>
<li><strong>外部验证表态</strong>：Discussion 明确所有增量结论待独立队列验证。</li>
<li><strong>HLA-II 仅作 Future work</strong>（除非投稿前真有结果，否则不进 Results）。</li>
</ol>

