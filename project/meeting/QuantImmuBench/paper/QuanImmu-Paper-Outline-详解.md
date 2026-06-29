# QuanImmu 论文大纲 · 逐节详解（白话导读版）

> **这份文件是什么**：把 [`QuanImmu-Paper-Outline.md`](./QuanImmu-Paper-Outline.md) 这份"骨架大纲"翻译成人话，**每一节都讲透**——这一节是干嘛的、为什么要写、里面每个术语/数字/公式到底在说什么、跟整篇论文怎么咬合。给"不是做这行的人"也能一口气读懂的版本。
>
> **怎么用**：大纲是给写论文的人看的"提纲"，本文是给你（或合作者、袁老师、答辩听众）看的"讲解"。读完这份，你就能跟任何人讲清楚这篇论文每个部分在干嘛。
>
> **超链接约定**：遇到专业名词第一次出现，挂一个外部链接（维基/官方/论文），想深挖就点。内部文件用相对链接（如支撑数据 csv、其他项目档）。
>
> **数据真源提醒**：本文引用的数字来自 [`paper/STORY.md`](./STORY.md) 锁定值 + [`analysis/`](../analysis/) 下已核 csv。⚠️ 注意大纲（2026-06-29 版）描述的是**更宏大的 QuantImmu 框架版本**（30 工具 + pooling/fusion 三步范式），而当前实测落地的是 9 工具的 benchmark——两者数字口径有差异，写正文时以 csv 实测为准，框架部分是目标蓝图。详见文末 [§现状对照](#现状对照大纲蓝图--实测落地)。

---

## 先理解这篇论文一句话在干嘛

**临床场景**：一个癌症病人，肿瘤里有几十个基因突变。理论上每个突变都可能产生一段"异常蛋白片段"（叫 [neoantigen / 新抗原](https://en.wikipedia.org/wiki/Neoantigen)），免疫系统的 T 细胞可能认出它来打肿瘤。做[个性化肿瘤疫苗](https://www.cancer.gov/news-events/cancer-currents-blog/2023/melanoma-mrna-vaccine-keytruda)就是从这几十个突变里挑出**最可能激起强免疫反应的那几个**，合成成疫苗打进去。

**问题**：怎么挑？现在有一堆软件工具（30 来个）能给每个突变打分。但它们有两个"错配"：
1. 它们大多只回答"**有没有**免疫原性"（是/否，二分类），但临床要的是"**强多少**"（连续排序，谁更值得做）。
2. 它们在"**肽段–HLA分型**"这个细粒度层面打分，但临床决策单元是"**突变**"——一个突变会对应好几条候选肽段，分数得想办法**合并**到突变级。

**这篇论文做的事**：提出一个统一框架 **QuantImmu**，把任意工具的输出转成"突变级的定量免疫原性分"，然后系统横评 30 个工具，研究怎么合并（pooling）、怎么把多个工具融合（fusion）效果最好，并用最严格的方法验证结论靠不靠谱。真值标准用 [ELISpot 实验](https://en.wikipedia.org/wiki/ELISpot)（实际测 T 细胞反应强度），评测指标用 [Spearman 秩相关](https://en.wikipedia.org/wiki/Spearman%27s_rank_correlation_coefficient)（衡量排序对不对）。

记住三个卖点（标题/摘要必须出现）：**quantitative（定量，不是二分类）· mutation-level（突变级，不是肽–分型级）· 30-tool benchmark（系统横评）**。

---

## 0. 候选标题 —— 为什么标题这么重要

**这一节在干嘛**：选论文标题。大纲列了原标题的毛病 + 3 个候选。

**为什么单独花篇幅**：标题是论文的"门面"，决定审稿人和读者第一眼判断这篇值不值得看。原标题 *A quantitative framework for mutation-level assessment of neoantigen immunogenicity* 的问题是：
- **太宽泛**：听起来像综述，没说清具体做了啥。
- **没体现最大卖点**：30 工具系统横评这个"硬资产"没在标题里。
- **没记忆点**：没有方法名，读者记不住。好论文都有个能被引用时反复念叨的名字（像 BERT、AlphaFold）。所以起了 **QuantImmu** 这个名字。

**三个候选的取舍**（大纲推荐第 1 个 ⭐）：
1. `QuantImmu: a quantitative, mutation-level framework for benchmarking and integrating...` —— 有方法名 + 三卖点齐，最推荐。
2. 强调"从肽–分型分到突变级"的转化。
3. 强调 pooling/fusion 策略。

> 💡 比喻：标题就像店招牌。"一家餐厅"没人进，"XX 牛肉面·30 年老汤"才有人记得住、愿意试。

---

## Abstract（结构化摘要）—— 4 段式

**这一节在干嘛**：摘要。投稿 [Briefings in Bioinformatics（BiB）](https://academic.oup.com/bib) 习惯写**结构化摘要**（分小标题），约 250–300 词。

**为什么 4 段**：BiB 这类生信期刊审稿人时间紧，结构化摘要让他们 30 秒抓住"你解决什么问题、做了什么、发现什么、能不能用"。四段固定套路：

- **Motivation/Background（动机）**：点出那个"系统性错配"——现有工具做二分类、用 [AUC](https://en.wikipedia.org/wiki/Receiver_operating_characteristic#Area_under_the_curve) 评、工作在肽–HLA 层；但临床要的是在几十个突变里做定量精细排序。一句话立靶子。
- **Results（结果）**：介绍 QuantImmu 框架（三步：逐行打分 → pooling → rank-fusion），系统评测 30 工具（10 呈递 + 20 免疫原性），跨人（ds1/ds2）和小鼠（B16F10/CT26）数据，给三层结论。
- **Key findings（关键发现）**：三个最硬的发现——① pooling 会**重排**工具优劣（结合类工具用 top-k 聚合后分数近翻倍，免疫原性类工具直接取最强即可）；② [geomean（几何平均）](https://en.wikipedia.org/wiki/Geometric_mean) rank-fusion 是唯一通过双重检验的整合法则；③ 样本有限时整合相对最强单工具统计上"持平"（没显著优势）——所以建议**按鲁棒性而非点估计**部署。
- **Availability（可用性）**：代码开源，框架即插即用任意新工具。

**Keywords**：neoantigen; immunogenicity prediction; MHC/HLA presentation; benchmarking; rank fusion; ELISpot; tumor vaccine.

> 💡 比喻：摘要是电影预告片。把最炸的镜头（三个 key findings）剪进去，但别剧透到让人不想看正片。

---

## 1. Introduction —— 怎么把"问题"讲成"非解决不可"

**这一节在干嘛**：引言。任务是**论证 gap（学界空白）真实存在且重要**，让审稿人觉得"这事确实没人好好做过，该做"。分 5 个小段：

### 1.1 临床背景
铺场景：个性化疫苗的流程 = 突变检出 → 候选肽 → 优先级排序 → 合成/接种。**排序质量直接决定疫苗成败**——挑错了，疫苗白做。把读者带进"这是真临床刚需"的语境。

### 1.2 两个错配（本文的核心 gap）
这是引言的"立靶"段，两个错配就是论文要打的靶子：
- **错配一：二分类 vs 定量**。主流工具（[DeepImmuno](https://github.com/frankligy/DeepImmuno)、[IEDB immunogenicity](http://tools.iedb.org/immunogenicity/)、[deephlapan](https://github.com/jiujiezz/deephlapan)、[PRIME](https://github.com/GfellerLab/PRIME) 等）把免疫原性建成"是/否"，用 AUC/准确率评。但免疫原性本质是**连续强度**，临床要精细排序 → 应该用 Spearman 衡量。
- **错配二：肽–HLA 层 vs 突变层**。工具在"一条肽 × 一个等位基因"上打分，但一个突变对应**多条**候选肽–HLA 行；临床决策单元是**突变**。怎么把多行**聚合（pooling）**到突变级，是个被忽视但关键的方法学选择。

> 💡 比喻：错配一像"医生只会说'你有没有发烧'，但你想知道'烧到几度'"。错配二像"一个学生考了语数英好几科，你要给学生排名次，得先想清楚怎么把多科分数合成一个总分（求和？取最高？取平均？）"——这个"合成方式"就是 pooling，选错了排名全乱。

### 1.3 第三个 gap：缺乏统一公平的定量系统评测
已有 benchmark 大多在二分类/肽层、工具数有限。缺一个把 30 个异质工具放在**同一突变级定量口径**下、用**统一无泄漏协议**比较、并研究**怎么最优整合**的工作。这就是本文的位置。

### 1.4 本文贡献（三条，跟标题呼应）
1. 提出 **QuantImmu** —— 定量评估免疫原性的统一框架（三步范式 + 无泄漏 [LOPO](https://en.wikipedia.org/wiki/Cross-validation_(statistics)#Leave-one-out_cross-validation) 协议）。
2. 把评估从**肽–分型层提升到突变层**，并系统刻画 pooling 这个关键步骤。
3. **系统评测 30 工具**（10 呈递 + 20 免疫原性），跨人/鼠，给单工具、单工具×pooling、多工具×fusion 三层完整结果 + 严格鲁棒性检验。

### 1.5 Roadmap
一段话告诉读者后面每节讲啥、指向哪个 Results 小节。给读者一张"地图"。

> 💡 引言写作铁律：**先让读者认同有个坑（gap），再说我来填**。顺序不能反——先说方案再说问题，读者会觉得"你这是为做而做"。

---

## 2. Materials and Methods —— 方法学主体，"你怎么做的"

**这一节在干嘛**：交代数据、工具、框架、协议，让别人**能复现**。BiB 这类期刊，方法的严格性本身就是卖点。

### 2.1 Datasets（人 + 鼠）
**用了哪些数据**：
- **人源 ds1**（`human_ELSpot_dataset_1/`）：netMHCpan + PRIME 合并结果，当人源补充/复现集。
- **人源 ds2**（`human_ELISpot_dataset_2/`，**主分析集**）：9 个病人（P101–P110），统一口径为 inference 子集（**92 突变 / 8 有效病人**，P102 在 inference 中近乎缺席）。
- **小鼠 B16F10 / CT26**：结构最干净的经典模型，含 BigMHC_IM、PRIME 合并版。
- **真值（ground truth）**：[ELISpot](https://en.wikipedia.org/wiki/ELISpot) 反应（斑点数，[SFC = spot-forming cells](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4863971/)）；标签列 `Elispot`。这是"金标准"——实际在实验室测出来的 T 细胞反应强度。
- **聚合键（怎么定义"一个突变"）**：小鼠用 `27AA_Sequence_MT`；人用 `Patient_ID|Peptide_ID`（叫 `mut_key`）。这决定 pooling 时"哪些行算同一个突变"。
- **表 1**：数据集汇总（物种、病人数、有标签突变数、肽–HLA 行数、覆盖工具）。

> 💡 为什么要小鼠+人？小鼠数据"干净"（实验可控），人数据"真实"（临床相关）。两个都验证 → 说明结论不是某个数据集的偶然。这叫**跨物种泛化**，审稿人爱看。

> ⚠️ 数据集真源在 [`.portfolio/datasets.json`](../../../../.portfolio/datasets.json)，引用前先查别硬编码路径。

### 2.2 The 30 tools surveyed（核心资产，一张大表）
**这是论文最值钱的硬资产**——30 个工具的系统清单。
- **表 2（关键表）**：分两类列：
  - **10 种呈递预测（presentation/binding）**：预测"这条肽能不能被 HLA 分子呈递到细胞表面"。如 [netMHCpan](https://services.healthtech.dtu.dk/services/NetMHCpan-4.1/)（Aff/BA/EL 三种分）、netMHCpan 可变窗、MAAP、[MHCflurry](https://github.com/openvax/mhcflurry)、[NetMHCstabpan](https://services.healthtech.dtu.dk/services/NetMHCstabpan-1.0/)、BigMHC_EL 等。
  - **20 种免疫原性预测（immunogenicity）**：进一步预测"被呈递后，T 细胞会不会真的反应"。如 PRIME、deephlapan(Imm/Bind)、[PredIG](https://github.com/PuriejvD/PredIG)、DeepImmuno、IEDB immunogenicity、[BigMHC](https://github.com/KarchinLab/bigmhc)(IM)、内部 Inference 8-class、[Seq2Neo](https://github.com/XSLiuLab/Seq2Neo)、DeepNeo 等。
- **每行标注**：输出分名、原生任务（二分类/连续/概率）、是否提供 MT/WT、9mer 还是可变窗、引用文献。
- **9mer vs 可变窗**：同工具 `9AAonly`（只看 9 氨基酸肽）一致优于可变窗（4/4 数据集），所以主分析用 9AA，可变窗放补充材料。

> 💡 呈递 vs 免疫原性的关系像"门禁 → 面试"。呈递 = 肽能不能被带到细胞表面（进门）；免疫原性 = 进门后 T 细胞认不认（面试过没过）。两层都过才有真免疫反应。HLAthena 这种纯呈递工具 AUC≈0.51 近随机，恰好印证"光进门没用，还得面试过"。

> ⚠️ **写作待办**：当前仓库实测接入约 14 个分数源（[`DEPLOY_TRACKER.md`](../DEPLOY_TRACKER.md)），投稿前要补到 30。表 2 现在是占位，逐一接入后填数。

### 2.3 The QuantImmu framework（三步范式 —— 方法学心脏）
**整篇论文的核心方法**。把任意工具输出转成"突变级定量分"分三步：

- **Step 1 逐行打分 + 定向（orientation）**：每条肽–HLA 行取一个标量分，统一成"**越大越免疫原**"。比如亲和力（[binding affinity](https://en.wikipedia.org/wiki/Dissociation_constant)，单位 nM，越小越强）要取负号 `−Aff(nM)` 才变成"越大越好"。可选 **DAI（突变型 vs 野生型对比）**两种形式：相减型 `max(MT−WT,0)`、对数比值型 `max(log₂(Aff_WT/Aff_MT),0)`——意思是"突变让结合变强了多少"。
- **逐病人归一化（无泄漏）**：min-shift + RMS（`y=x−min`，再 `y/√mean(y²)`）。**只用病人自己的特征、不碰标签、不看别的病人** → 这是后面交叉验证"无泄漏"的基础。
- **Step 2 pooling（多行 → 突变级 1 分）**：一个突变的多条肽–HLA 行怎么合成一个分。四种方法（详见 2.4）。
- **Step 3 fusion（多个工具的 rank → 一个综合分）**：每个工具在病人内转成排名（rank），再融合多个工具（详见 2.5）。

> 💡 三步用做菜比喻：Step 1 = 把各种食材统一切好、统一朝向摆盘（定向 + 归一化）；Step 2 = 把一道菜的多个零件合成一盘（pooling）；Step 3 = 把多道菜拼成一桌定个总评（fusion）。

### 2.4 Pooling methods（表 3）—— 四种"合并"公式
一个突变有多条肽行（按分数从大到小排成 v₁≥v₂≥…），怎么合成一个分 s：

| pooling | 公式 | 直觉 |
|---|---|---|
| **max** | s=v₁ | 只取最强那条（"一票最高定胜负"） |
| **topk_w** | s=Σwᵣvᵣ/Σwᵣ, wᵣ=r^(−α), 取前 k 条 | 前 k 条加权平均，α 控制权重衰减 |
| **softmax** | s=Σe^(vᵣ/T)vᵣ/Σe^(vᵣ/T) | [softmax](https://en.wikipedia.org/wiki/Softmax_function) 软性加权，T 越小越接近 max |
| **rankdecay** | s=Σwᵣvᵣ/Σwᵣ, wᵣ=1/log(r+γ) | 按排名对数衰减加权 |

超参网格（要扫的参数组合）：topk_w 的 `k∈{1,2,3,5,8,10,20,50,100}×α∈{0,0.5,1,2}`；softmax 的 `T∈{0.03,...,2}`；rankdecay 的 `γ∈{1,...,20}`。

> 💡 max vs topk 的核心区别：**max 是"只信最强那一条肽"**，topk 是"信前几条的综合"。后面会发现这个选择对不同工具影响巨大——结合类工具用 top-k 聚合后分数翻倍，免疫原性类工具 max 就够了。这是论文一个可推广的规律。

### 2.5 Fusion methods（12 种 —— 对应贡献 3 的整合）
把多个工具/维度的排名融合成一个综合排序，列全 12 种：mean-rank、geomean、median、powmean、max、min、加权变体、softmax-rank、stacking/线性回归、constrained 等（按实测脚本 [`fourdim_cls2_aggregation.py`](../analysis/)、`robustness_7dim_fusions.py`、`nested_lopo_ensemble.py`、`stacking_lopo.py` 实际枚举填表 4）。

重点定义 **geomean rank-fusion**（[几何平均](https://en.wikipedia.org/wiki/Geometric_mean)，共识/AND 型）vs **max**（OR 型）的对立直觉：
- **geomean（AND/共识型）**：一个突变要**所有工具都觉得它好**，综合分才高（任一工具给低分都拉垮总分）。稳，但保守。
- **max（OR型）**：**任一工具觉得它好**就高。激进，但容易被单个工具的假阳性带偏。

> 💡 geomean 像招聘要"所有面试官都点头才录"，max 像"任一面试官力挺就录"。后面会发现 geomean 更鲁棒——因为它要求多方共识，不容易被单个工具的噪声忽悠。

### 2.6 Evaluation protocol（评测协议 —— 严格性是卖点）
怎么评分、怎么防作弊（数据泄漏）：
- **主指标**：per-patient **Spearman**（每个病人单独算"预测分 vs ELISpot"的秩相关），再跨病人**等权平均**。[Pearson](https://en.wikipedia.org/wiki/Pearson_correlation_coefficient) 作对照放补充表。
- **Nested LOPO（[留一病人交叉验证](https://en.wikipedia.org/wiki/Cross-validation_(statistics))）**：外层留一个病人当测试，内层用其余病人选超参 θ → 得到**无泄漏**的测试表现。报告 **oracle vs LOPO**（两者相等 = 零过拟合，说明选超参没偷看测试集）。
- **Ablation（消融）**：维度留一（[leave-one-out](https://en.wikipedia.org/wiki/Ablation_(artificial_intelligence))，去掉某个工具看掉多少）、加权方式对比。
- **Robustness（鲁棒性）**：随机删 10% 和 20% 突变 × 多组固定种子，看子采样的**均值/中位/胜率**而非单点——区分"真信号"和"某个配置专属的运气"。
- **Significance（显著性）**：方法间**配对显著性检验**（以病人为配对单元），明确报"持平 vs 显著"。

> 💡 为什么这么折腾？因为**点估计会骗人**。某方法在全数据上排第一，可能只是运气（恰好这批数据对它友好）。删掉一部分数据重测、换种子重测，如果它还稳居第一，才是真本事。这套协议就是"反运气"的防火墙。Nested LOPO 则是防"选超参时偷看答案"——很多论文虚高就是栽在这。

### 2.7 Implementation
技术栈：Python（numpy/pandas/scipy/openpyxl），无编译步骤。`score_pooling_lopo.py` 是 ds2 的公共库（load/build/POOLERS），`camp.py` 是小鼠参考实现。脚本↔图表映射见附录 A。

---

## 3. Results —— 三层递进，论文的肉

**这一节在干嘛**：摆结果。三层递进结构，每层都给**人+鼠**结果，主图用 Spearman、附表附 Pearson。

### 3.1 单工具 max-pooling 基线（结果①）
**最简单的起点**：每个工具只用 max-pooling（取最强肽），算突变级 Spearman。因为 max 无超参，所以 LOPO==oracle==均值（没有选超参的环节，不会过拟合）。
- **图 1 / 表 5**：30 工具的 max-pool Spearman，人/鼠分面。
- **关键发现**（ds2 已知）：只用 max 时，**免疫原性类工具领先**（PRIME、deephlapan_Imm、PredIG、Inference 概率类都在 +0.28~+0.32），**亲和力类垫底**（netAffneg 只有 +0.196）。
- 小鼠对照：看 B16F10/CT26 上排名跟人是否一致。

> 💡 这一层是"裸奔基线"——不做任何花哨处理，看每个工具的原始水平。结论：免疫原性工具确实比纯亲和力工具懂"免疫原性"。但下一节会反转。

### 3.2 单工具 × 4 种 pooling（结果②）—— 核心"洗牌"
**这是论文第一个亮点**：换 pooling 方式，工具排名会**大洗牌**。
- **图 2（核心洗牌图）**：每个工具 max vs 它最优 pooling 的提升，按工具类别着色。
- **关键发现**：`netAffneg_9`（亲和力工具，max 时垫底只有 +0.196）经 **top-20 等权平均（k=20, α=0）跃居单工具第一 +0.3946**——分数翻倍！
- **沉淀为领域规律**（可推广结论）：
  - **结合/亲和力类**（netMHCpan Aff/BA/EL、MAAP）→ 要"**聚合**"（大 k、α=0 的 top-k 等权平均，信号近翻倍）。
  - **免疫原性类**（PRIME/deephlapan/PredIG）→ 要"**取最强**"（max 即最优）。
  - **概率类**（Inference）→ 取最强。

> 💡 为什么亲和力工具要聚合？因为单条肽的亲和力噪声大、不可靠，但一个突变下"有多少条肽都结合得不错"反而是个稳的信号——所以平均前 20 条比只看最强 1 条准。而免疫原性工具本身已经建模了"哪条最可能激免疫"，取最强那条就对。**这个规律是论文能被别人引用复用的干货**。

### 3.3 多工具整合：12 种 fusion + 三重检验（结果③，方法学高潮）
**论文最硬核的部分**：把多个工具融合，并用三重严格检验筛出真正靠谱的整合法则。

#### 3.3.1 12 种 fusion 对比
表 6：多维（3/4/6/7 维，即融合 3~7 个工具/维度）下 12 种 fusion 的 LOPO Spearman。发现 **geomean 突出**。

#### 3.3.2 Ablation test（消融）
- **维度留一**（表 7）：每次去掉一个维度，看掉多少分 → 找出哪个工具最"承重"。ds2 发现 **deephlapan_Imm 最承重**（因为它跟亲和力/PRIME 最[正交](https://en.wikipedia.org/wiki/Orthogonality)——提供别人没有的独立信息）。
- **加权 ablation**：试 4 种加权方式 → 发现**加权一律塌回等权**（花哨加权不帮忙，简单等权就够）。

> 💡 "承重"= 抽掉它整个塌得最多。最承重的不一定是单独最强的，而是**信息最独立**的——它补的是别人补不了的角度。这跟投资组合一样，最有价值的不是收益最高的股票，是跟别人最不相关的那只。

#### 3.3.3 Nested-LOPO
表 8：整合 vs 最强单工具的**无泄漏**对比，报告 oracle/LOPO 一致性（一致 = 零过拟合）。

#### 3.3.4 Robustness（删 10%/20%）—— 第二个亮点
- **图 3 / 表 9**：7 维 × fusion 的子采样均值。**geomean 在删 10%（+0.4643）和删 20%（+0.4488）双双第一**。而 `max` 满数据时虚高（+0.4834）但子采样一删就塌——**反面教材：点估计陷阱**。
- **跨维复现性**：geomean 是唯一在 3/4/6/7 维都一致 ≥ mean 的 fusion（max/powmean 做不到）→ 这是判定 geomean 为真信号的关键检验。

> 💡 这就是 2.6 说的"反运气防火墙"实战。max 在完整数据上看着最高，但你删掉一点数据它就垮——说明它的"第一"是运气。geomean 删了还稳，才是真本事。**论文用这个对比教读者：别信单点最高分，要信删了还稳的。**

#### 3.3.5 显著性现实检验（必须诚实）
**最诚实也最重要的一段**：配对检验显示，整合相对最强单工具**统计上持平**（ds2：Δ≈+0.038、p≈0.70，而且这点提升主要由单个病人 P101 驱动）。强调"**排名次序 ≠ 显著差异**"。

> 💡 为什么要主动说自己没显著优势？因为审稿人一定会查，你不说他查出来就是"隐瞒"，直接拒稿。主动诚实承认 + 给出"那该怎么办"的部署建议（见 3.4），反而显得这工作扎实可信。这是 [[feedback_claim_shape_decides_birth_difficulty]] 说的"窄+诚实的 claim 更容易过"。

### 3.4 综合排名与部署建议 —— 把"持平"变成可操作结论
**承上启下**：既然整合没显著优势，那到底用啥？把"持平"转化成实用建议。
- **图 4 / 表 10**：全方法统一 LOPO 排名（人+鼠）。
- 因为统计持平 → **按"零过拟合 + 依赖最少 + 鲁棒 + 可解释"选**，给两个方案：
  1. **务实默认**：单 affinity pooling（`netAffneg_9 topk k=20,α=0`，只依赖 netMHCpan、最稳、零过拟合）。
  2. **按需备选**：多维 free-pooling + **geomean**（点估计和鲁棒性双优，代价是要跑多个工具管线）。
- **部署实例**：`rank_T01_deploy.py` 对无标签的真实病人（T01/T04）排序——证明框架真能用在临床。

> 💡 这一节是论文从"学术发现"落到"临床能用"的桥。给两个方案而不是硬推一个，是因为不同实验室条件不同：资源紧就用务实默认（一个工具搞定），追求最优就上 geomean 整合。**给选择权 = 显得成熟、考虑实际**。

---

## 4. Discussion —— 拔高 + 诚实兜底

**这一节在干嘛**：讨论。解读结果的更深意义、对冲质疑、诚实列局限、展望未来。BiB 审稿人**特别看重诚实的局限**。

### 4.1 方法学要点
拔高：定量 + 突变级 + pooling/fusion 是三个常被忽视但影响结论的设计轴。本文给出可推广的 pooling 类别规律（结合类聚合/免疫原类取最强）+ geomean fusion 法则。

### 4.2 为什么 Spearman≈0.4 是有竞争力的信号（而非"弱相关"）
**关键辩护段**。0.4 听起来不高，要论证它其实很强：
- 跨病人平均显著优于随机（t≈4.8、p<0.01）。
- 神经抗原免疫原性是**公认极难问题**（生物学上界封顶，见 [`THEORY_quant.md`](../reference/THEORY_quant.md)：precursor frequency 等因素让理论上界 ρ_max≈0.4–0.6）。
- 注意事项要诚实：per-patient 在 0.17–0.80 剧烈波动、榜单顶端仍有假阳性 → 当**强力排序输入**用，不是唯一裁判。

> 💡 这段在跟审稿人"砍价"。审稿人会说"0.4 太弱"，你反驳"这问题的天花板就是 0.4–0.6，我已经接近天花板了"。但又不能吹过头，所以补一句"它是好用的排序输入，不是终极答案"。攻守兼备。

### 4.3 诚实的局限（Limitations）
**BiB 极看重，必须诚实列全**：
- 整合 vs 最强单工具**不显著**（样本小、单病人驱动）。
- **设计层 selection bias 未进 CV**：用哪些工具/类别/pooling 菜单是看了全数据才定的 → 整合数字偏乐观。
- 仅 8 有效病人（ds2）→ ±0.03–0.05 的差异难言显著。
- CV 协议本身无泄漏（这是优点），问题在样本量 + 人为选择。
- 所有增量结论**待外部独立队列验证**。

> 💡 主动暴露"selection bias 没进 CV"这种连审稿人可能都没想到的硬伤，是高级操作——显得你比谁都懂自己工作的边界，反而建立信任。这跟 [[feedback_research_before_design]] 的"主动暴露不确定性"一脉相承。

### 4.4 Future work
- **HLA II 型**：把框架扩到 [MHC-II](https://en.wikipedia.org/wiki/MHC_class_II) 呈递 + CD4⁺ 免疫原性（现在只做 MHC-I / CD8⁺）。
- 更大规模、多中心 ELISpot 队列外部验证。
- 把框架做成即插即用任意新工具的**标准评测平台**——呼应 QuantImmune 自研算法立项（见 [`PROJECT_LANDSCAPE.md`](../PROJECT_LANDSCAPE.md)）。

---

## 5. Key Points（BiB 要求的 3–5 条要点框）

**这一节在干嘛**：BiB 特有栏目，要 3–5 条一句话要点，放论文首页边栏，给只看要点的读者。本质是"摘要的摘要"：
- 神经抗原免疫原性应作**连续强度在突变层**定量评估（Spearman），而非肽层二分类（AUC）。
- pooling 选择会**系统性重排**工具优劣：结合类要聚合、免疫原性类要取最强。
- 30 工具上，**geomean rank-fusion** 是唯一通过跨配置复现性 + 删突变鲁棒性双重检验的整合法则。
- 样本有限时整合相对最强单工具**统计持平**；部署应按鲁棒性而非点估计选。
- 框架开源、可扩展至任意新工具及 HLA-II。

> 💡 每条都对应正文一个发现。写法是"结论先行"——直接抛观点，不铺垫。

---

## 6. 论文常规部分（投稿必备）

**这一节在干嘛**：期刊投稿的标准"行政件"，缺一不可：
- **Author Contributions**：谁做了啥。
- **Funding**：经费来源。
- **Data Availability**：数据哪来的、能不能拿到。⚠️ 人源 ELISpot 数据有**伦理/获取限制**要注明。
- **Code Availability**：开源仓库链接 + 关键脚本（`camp.py`、`score_pooling_lopo.py`、`robustness_7dim_fusions.py` 等）+ 复现说明。
- **Conflict of Interest**：利益冲突声明。
- **Acknowledgements**：致谢。
- **References**：30 工具各自原始文献 + benchmark/方法学引用（[`REFERENCES.md`](../REFERENCES.md) 已有 DOI 出处）。

> ⚠️ **许可红线**：netMHCpan/stabpan 学术许可**禁止再分发**（含它们跑出的数字），投稿前要取 [DTU](https://services.healthtech.dtu.dk/) 书面同意（见 [`PROVENANCE.md`](../PROVENANCE.md)）。DTU 工具数字现在一律标 `pending DTU consent`。

---

## 7. Figures & Tables 清单（投稿打包用）

**这一节在干嘛**：列全所有图表，方便投稿时打包。论文的"装配清单"：

**主图（建议 4–5 张）**：
- 图 1：30 工具 max-pool 基线（人/鼠分面）。
- 图 2：pooling "洗牌"图（max vs 最优 pooling，按类别着色）← **核心**。
- 图 3：fusion 鲁棒性（10% vs 20% 子采样均值，geomean 双第一）← **核心**。
- 图 4：全方法统一 LOPO 排名 + 部署方案标注。
- （可选）图 5：框架示意图（三步范式 schematic，放 §2 开头）。

**主表**：表 1 数据集汇总；表 2 **30 工具清单（10+20）**；表 3 pooling 网格；表 4 12 fusion 定义；表 5 单工具 max 基线；表 6 多维 fusion 对比；表 7 维度 ablation；表 8 nested-LOPO；表 9 删突变鲁棒性；表 10 统一排名。

**补充材料（Supplementary）**：全部 Pearson 对照表；可变窗（mw）结果；ds1 复现；逐病人 Spearman 分布（0.17–0.80）；30 组随机种子明细；配对检验完整统计。

> 💡 图 2 和图 3 是"核心"——一个讲 pooling 洗牌（亮点①），一个讲 geomean 鲁棒（亮点②）。这两张图是论文的"封面照"，审稿人主要看它们判断工作质量。出图规范见 [academic-figure-prompt skill] + [`/validate-figures`]，含数字的图主线必派 verifier 核 ≥2 个值再接稿。

---

## 附录 A：脚本 ↔ 结果章节映射（复现索引）

**这一节在干嘛**：给"想复现的人"一张对照表——每个 Results 小节用哪个脚本跑出哪个 csv。是开源诚意 + 自己日后复查的索引：

| 论文小节 | 主要脚本 | 产物 |
|---|---|---|
| §3.1 单工具 max | `score_pooling_subset.py` | `score_pooling_subset92_results.csv` |
| §3.2 单工具×pooling | `score_pooling_lopo.py`, `inference_scan_subset92.py`, `predig_subset_eval.py` | `*_results.csv` |
| §3.3.1 多维 fusion | `fourdim_cls2_aggregation.py`, `inference_integration_variants.py` | `*_results.csv` |
| §3.3.2 ablation | `sixdim_ablation_weights.py`, `ablation_7dim_geomean_robust*.py` | `*_results.csv` |
| §3.3.3 nested-LOPO | `nested_lopo_ensemble.py`, `cross_dataset_lopo.py`, `constrained_nested.py` | `*.result/.csv` |
| §3.3.4 robustness | `robustness_subsample.py`, `robustness_7dim_fusions*.py`, `robustness_fusion_reproducibility*.py` | `*_results.csv` |
| §3.3.5 显著性 | `_audit_paired.py`, `geomean_vs_mean_paired.py` | — |
| §3.4 部署 | `rank_T01_deploy.py`, `rank_T01_GATK.py`, `rank_T04_GATK.py`, `frozen_pipeline.py` | `T0*_ranking_report.md` |
| 小鼠 | `camp.py`, `compare_models.py`, `quantimmu4*.py`, `mouse_window_compare.py` | `*.result/.md` |

> 权威技术细节以 `six_dim_model_report.md` 与 `QuantImmu项目说明.md` 为准。

---

## 附录 B：投稿前 to-do（写作 checklist）

**这一节在干嘛**：投稿前必须扫平的硬待办：
1. **补齐 30 工具**：当前约 14 个分数源 → 接到 10 呈递 + 20 免疫原性，填表 2/表 5。
2. **统一人/鼠口径**：确认四个数据集都跑通同一三步范式 + nested-LOPO。
3. **Pearson 全量补充**：主文 Spearman、补充材料补全 Pearson。
4. **显著性诚实呈现**：所有"第一/最优"措辞旁注是否统计显著。
5. **外部验证表态**：Discussion 明确所有增量结论待独立队列验证。
6. **HLA-II 仅作 Future work**（除非投稿前真有结果）。

---

## 现状对照：大纲蓝图 ↔ 实测落地

> ⚠️ **重要**：大纲（2026-06-29 版）描述的是**目标蓝图**——30 工具、三步范式（pooling/fusion）、Spearman≈0.4 量级的整合结论。但**当前实测落地的版本**（见 [`paper/STORY.md`](./STORY.md) 锁定值 2026-06-26）是更保守的 9 工具 benchmark，承重 claim 也不同：

| 维度 | 大纲蓝图（QuantImmu 框架版） | 当前实测（STORY 锁定版） |
|---|---|---|
| 工具数 | 30（10 呈递 + 20 免疫原性） | 9 跑通（8 免疫原性 + 1 proxy），约 14 分数源 |
| 核心方法 | 三步范式 + pooling/fusion 整合 | apples-to-apples 横评 + per-patient 聚合 |
| 主结论 | geomean fusion + pooling 类别规律 + Spearman≈0.4 | C1：工具普遍弱/不显著（|ρ|<0.33）；C2：per-patient 揭示个体差异；C3：magnitude 是 gap |
| 头条数字 | netAffneg topk +0.3946、geomean +0.4643 | IMPROVE top3mean ρ=0.3202、PredIG mean ρ=0.2797 |

**为什么有差距**：
- 大纲是**更宏大的论文目标**（可能对应升级版或 QuantImmune 自研算法立项后的版本）。
- ⚠️ **2026-06-27 HLA 数据修正（HLA-FIX）翻转了部分头条**：DS2 患者 P101/P102 的 HLA 等位曾被 Excel 拖拽填充弄出伪迹。修复后 PredIG 全局显著性失效（max ρ 0.198→0.104 p=0.343 不显著），头条从"PredIG 和 IMPROVE 都显著"修正为"仅 IMPROVE 稳健显著"。当前有效数字真源 = [`analysis/metrics_ds2_fixed_exclP101P102.csv`](../analysis/)（corrected-excl）。详见 [`04_LOG.md`](../04_LOG.md) Entry HLA-FIX + [`data/HLA数据错误_完整上报_给袁老师_2026-06-27.md`](../data/)。

**写正文时的纪律**：
1. **数字一律以 csv 实测为准**（Bash/Grep 核，不信 Read，入 tex 前过 verifier）——大纲里的 +0.3946 / +0.4643 等若来自更大框架版本，未在当前 csv 复现的不能直接写进投稿。
2. **大纲的 30 工具/三步范式是目标**，投稿前若补不齐，按 STORY 的 9 工具 + per-patient 框架走更稳。
3. **承重 claim 形状**：STORY 已收窄为"窄+可观测+增量"（C1 全实测最稳），比大纲的"整合涨点"更不容易被审稿人打。优先守 STORY。

---

## 一页纸总览（给答辩/汇报用）

```
问题：癌症疫苗要从几十个突变里挑最强免疫原性的，但现有工具
      ① 只做二分类（有/无），临床要定量排序（强多少）
      ② 在肽-HLA层打分，临床决策单元是突变（要合并）

方案：QuantImmu 框架 = 逐行打分 → pooling(合并到突变) → fusion(融合多工具)
      横评 30 工具 × 人/鼠数据 × ELISpot 真值 × Spearman 主指标

三层结果：
  ① 单工具 max 基线        → 免疫原性工具领先，亲和力垫底
  ② 单工具 × 4 pooling     → 洗牌！亲和力工具聚合后翻倍夺冠（规律：结合类聚合、免疫类取最强）
  ③ 多工具 × 12 fusion     → geomean 唯一通过"删数据+跨维"双重检验（max 是点估计陷阱）

诚实兜底：整合 vs 最强单工具统计持平 → 按鲁棒性而非点估计部署
          务实方案：单 affinity pooling；进阶方案：多维 geomean

局限：样本小（8 病人）、selection bias、待外部验证
未来：扩 HLA-II + 大队列 + 做成标准平台（QuantImmune 立项背书）
```

---

*本详解基于 [`QuanImmu-Paper-Outline.md`](./QuanImmu-Paper-Outline.md)（2026-06-29）+ [`paper/STORY.md`](./STORY.md) + [`analysis/`](../analysis/) 实测 csv + [`00_README.md`](../00_README.md) 撰写。数字以 csv 实测为准，框架部分为论文目标蓝图。如大纲更新，本文需同步。*
