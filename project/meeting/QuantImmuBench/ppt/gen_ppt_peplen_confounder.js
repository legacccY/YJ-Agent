// QuantImmuBench — 肽长×ELISpot 混杂：存在性与矫正（深度分析 deck，19 页：封面 + 目录 + 核心发现总览 + 15 内容页 + 进行中·下一步）
// 结构：一 存在性与机制 / 二 要不要矫正·怎么矫·为什么温和 / 三 融合交叉验证 / 四 其他发现与结论 / 进行中·下一步。
// 主题：先确证「疫苗肽越长 ELISpot 免疫原性越高」是否存在，再论证它是否让不同工具排名虚高、需矫正。
// 样式引擎复用 gen_ppt_benchmark_results.js 的 helper（header/pageno/proseCard/citeFoot/placeImg/tbl），
// 配色 Okabe-Ito（#0072B2 蓝 / #E69F00 橙 / #009E73 绿），Microsoft YaHei 中文字体，LAYOUT_WIDE，W=13.33 H=7.5。
// 图片一律按真实宽高比 contain 不拉伸（ratio 已量好，勿改）。数字全部逐字采用主线已核值，零自造。
// 运行(主线跑，本脚本作者不跑): NODE_PATH=C:/Users/yj200/AppData/Roaming/npm/node_modules node ppt/gen_ppt_peplen_confounder.js
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "QuantImmuBench — 肽长与 ELISpot 免疫原性：评测混杂及其矫正";

const W = 13.33, H = 7.5;
// 中性底色沿用模板，accent 三色用 Okabe-Ito（teal 别名 = Okabe 蓝，供 citeFoot 标签色复用）
const C = {
  dark:"0B3C49", teal:"0072B2", blue:"0072B2", orange:"E69F00", green:"009E73",
  light:"F2F7F7", card:"FFFFFF", ink:"16323A", muted:"5E7B83",
  line:"D5E3E4", warn:"E69F00", ok:"009E73", crit:"B23A48", gray:"8A9BA0",
};
const FH = "Microsoft YaHei", FB = "Microsoft YaHei", FM = "Consolas";
const sh = () => ({ type:"outer", color:"0B3C49", blur:9, offset:3, angle:135, opacity:0.12 });

// 3 张图（存在性已由主线 Bash 确认），ratio = 宽/高（已量好，勿改）
const IMG = {
  forest:  { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/figures/fig_peplen_existence_forest.png",          r:1.810 },
  robust:  { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/figures/fig_peplen_robustness_bars.png",           r:1.839 },
  delta:   { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/figures/fig_peplen_correction_delta_by_tool.png",  r:0.9017 },
  scatter: { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/figures/fig_peplen_vs_elispot_confounder.png",     r:2.3273 },
  mechTool:{ p:"D:/YJ-Agent/project/meeting/QuantImmuBench/figures/fig_peplen_mech_toollevel.png",           r:1.357 },
  mechPool:{ p:"D:/YJ-Agent/project/meeting/QuantImmuBench/figures/fig_peplen_mech_pooling.png",             r:1.613 },
  fusionCV:{ p:"D:/YJ-Agent/project/meeting/QuantImmuBench/figures/fig_fusion_cv.png",                       r:1.763 },
};

let _PG = 1;
function header(slide, kicker, title, accent=C.blue){
  slide.background = { color: C.light };
  slide.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:0.28, h:H, fill:{color:accent} });
  slide.addText(kicker.toUpperCase(), { x:0.7, y:0.42, w:11, h:0.3, fontFace:FB, fontSize:12, color:accent, bold:true, charSpacing:3, margin:0 });
  slide.addText(title, { x:0.7, y:0.72, w:12, h:0.7, fontFace:FH, fontSize:24, color:C.ink, bold:true, margin:0 });
}
function pageno(slide){ _PG++; slide.addText(String(_PG), { x:W-0.8, y:H-0.5, w:0.5, h:0.3, fontFace:FB, fontSize:11, color:C.muted, align:"right", margin:0 }); }
function proseCard(slide, x, y, w, h, head, body, accent){
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill:{color:C.card}, line:{color:C.line, width:1}, shadow:sh() });
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w:0.09, h, fill:{color:accent} });
  slide.addText(head, { x:x+0.28, y:y+0.16, w:w-0.4, h:0.36, fontFace:FH, fontSize:15, bold:true, color:accent, margin:0 });
  const arr = Array.isArray(body) ? body : [body];
  const rt = arr.map((t)=>({ text:t, options:{ breakLine:true, color:C.ink, fontSize:12, paraSpaceAfter:7, lineSpacingMultiple:1.18 } }));
  slide.addText(rt, { x:x+0.3, y:y+0.62, w:w-0.55, h:h-0.74, fontFace:FB, valign:"top", margin:0 });
}
function citeFoot(slide, txt){
  const runs=[{ text:"来源  ", options:{ color:C.blue, fontSize:9, bold:true } }];
  txt.split(" · ").forEach((p,i)=>{
    let opt={ color:C.muted, fontSize:9 };
    const dm=p.match(/DOI\s+(10\.\S+)/);
    const gm=p.match(/(github\.com\/\S+|hlathena\.tools\S*|services\.healthtech\S*|openvax\.github\S*|tools\.iedb\.org\S*)/);
    if(dm) opt={ color:"1C7293", fontSize:9, hyperlink:{ url:"https://doi.org/"+dm[1], tooltip:"DOI" } };
    else if(gm) opt={ color:"1C7293", fontSize:9, hyperlink:{ url:"https://"+gm[1].replace(/^https?:\/\//,""), tooltip:"link" } };
    runs.push({ text:(i>0?" · ":"")+p, options:opt });
  });
  slide.addText(runs, { x:0.7, y:7.08, w:11.9, h:0.34, fontFace:FB, italic:true, valign:"top", margin:0 });
}
// 图片按真实宽高比 contain 进容器（ratio = 宽/高），不拉伸；宁可留白不变形
function placeImg(slide, img, ratio, bx, by, bw, bh){
  slide.addShape(pres.shapes.RECTANGLE, { x:bx, y:by, w:bw, h:bh, fill:{color:C.card}, line:{color:C.line, width:1}, shadow:sh() });
  const aw = bw-0.24, ah = bh-0.24;
  let iw = aw, ih = aw/ratio; if (ih > ah) { ih = ah; iw = ah*ratio; }
  const ix = bx+0.12+(aw-iw)/2, iy = by+0.12+(ah-ih)/2;
  slide.addImage({ path:img, x:ix, y:iy, w:iw, h:ih });
}
// 通用高级表格：表头深底白字，数据行斑马纹，首列左对齐其余居中（可逐格覆盖）
function tbl(slide, headers, rows, colW, x, y, opts){
  opts = opts || {};
  const head = headers.map(h=>({ text:h, options:{ fill:{color:C.dark}, color:"FFFFFF", bold:true, fontSize:opts.hfs||12, align:"center", valign:"middle" } }));
  const body = rows.map((r,ri)=> r.map((c,ci)=>{
    const cell = (c && typeof c==="object") ? c : { text:String(c) };
    const zebra = ri%2===0 ? C.card : C.light;
    return { text:cell.text, options:{
      fill:{ color:cell.fill||zebra }, color:cell.color||C.ink,
      bold:cell.bold||false, fontSize:cell.fs||opts.bfs||11,
      align:cell.align||(ci===0?"left":"center"), valign:cell.valign||"middle",
    } };
  }));
  const rowH = [opts.hh||0.5].concat(rows.map(()=> opts.rh||0.6));
  slide.addTable([head].concat(body), { x, y, w:colW.reduce((a,b)=>a+b,0), colW, rowH,
    border:{ pt:1, color:C.line }, align:"center", valign:"middle", fontFace:FB, autoPage:false });
}

// ============================================================ 1 封面（深底）
let s = pres.addSlide();
s.background = { color: C.dark };
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.orange} });
s.addShape(pres.shapes.OVAL, { x:W-3.3, y:-1.6, w:4.6, h:4.6, fill:{color:C.blue, transparency:78} });
s.addShape(pres.shapes.OVAL, { x:W-2.0, y:3.6,  w:3.2, h:3.2, fill:{color:C.orange, transparency:82} });
s.addText("QuantImmuBench 深度分析 · 一个被忽视的评测混杂", { x:0.9, y:1.35, w:11.5, h:0.4, fontFace:FB, fontSize:15, color:C.orange, bold:true, charSpacing:2, margin:0 });
s.addText("肽长与 ELISpot 免疫原性\n一个被忽视的评测混杂及其矫正", { x:0.9, y:1.95, w:11.6, h:1.9, fontFace:FH, fontSize:32, bold:true, color:"FFFFFF", lineSpacingMultiple:1.05, margin:0 });
s.addShape(pres.shapes.LINE, { x:0.95, y:4.4, w:3.2, h:0, line:{color:C.orange, width:2} });
s.addText([
  { text:"QuantImmuBench 深度分析 · DS2 Braun 2025", options:{ breakLine:true, paraSpaceAfter:6 } },
  { text:"130 肽 / 9 患者 · 逐患者秩相关", options:{ breakLine:true, paraSpaceAfter:6 } },
  { text:"主指标 = 肽长与 ELISpot 的 per-patient Spearman", options:{ breakLine:true, bold:true, color:"F5E3C5" } },
], { x:0.95, y:4.7, w:11.4, h:1.7, fontFace:FB, fontSize:15, color:"E6F2F2", valign:"top", lineSpacingMultiple:1.25, margin:0 });
s.addText("2026-07-05", { x:W-2.4, y:6.75, w:1.8, h:0.3, fontFace:FB, fontSize:12, color:"C9A96A", align:"right", margin:0 });

// ============================================================ 2 目录（导览）
s = pres.addSlide();
header(s, "目录", "本次分析导览", C.blue);
proseCard(s, 0.7, 1.7, 5.75, 2.45, "一 · 长肽为何 ELISpot 更高", [
  "存在性：逐患者森林图证据",
  "方法：去掉肽长影响的处理与公式",
  "稳健性：七道检验都指向同一个结论",
  "机制：合成长肽的真实生物学",
], C.green);
proseCard(s, 6.75, 1.7, 5.85, 2.45, "二 · 要不要矫正、怎么矫、为什么温和", [
  "差异性：单看肽长本身带来的影响因工具而异",
  "方案菜单：多族矫正方法取舍",
  "两层机制：工具打分是否随肽长走、以及综合方式",
  "排名影响：去掉肽长后格局基本不变",
], C.orange);
proseCard(s, 0.7, 4.35, 5.75, 2.45, "三 · 给融合补交叉验证", [
  "挑工具带来的虚高：SURV6 从未交叉验证",
  "补充分析：重选综合方式 / 判别 / 假满分相关审计",
], C.orange);
proseCard(s, 6.75, 4.35, 5.85, 2.45, "四 · 其他发现与结论", [
  "小样本虚高：单患者夸大原始相关的 bug",
  "新颖性：肽长作评测混杂未见先例",
  "建议与局限：并列报告、单队列待外验",
], C.blue);
citeFoot(s, "PEPTIDE_LENGTH_CONFOUNDER.md");
pageno(s);

// ============================================================ 3 核心发现总览（2×2）
s = pres.addSlide();
header(s, "核心发现", "一页看懂我们发现了什么", C.blue);
proseCard(s, 0.7, 1.7, 5.75, 2.5, "① 长肽 ELISpot 更高：真且稳", [
  "逐患者 ρ̄=+0.380，七道检验都指向同一个结论；控肿瘤表达 TPM、克隆性 CCF、子肽数后仍成立。",
  "机制是合成长肽（把突变那段做成一条较长的肽）的真实生物学，不是投料剂量假象。",
], C.green);
proseCard(s, 6.75, 1.7, 5.85, 2.5, "② 该矫正，但影响温和", [
  "肽被合成多长是做疫苗时人为定的、不是突变本身的性质，应从评分里扣除；但多数工具的评分并不随肽长走，去掉肽长后只改动几个百分点。",
  "把子片段打分求和这种综合方式最危险（相关 0.61），取最大值最稳。",
], C.orange);
proseCard(s, 0.7, 4.35, 5.75, 2.5, "③ 顺带修出一个小样本 bug", [
  "与肽长无关：个别工具在某患者仅三个非空值时出现虚假满相关，HLAthena 被从真实的 0.207 抬到 0.627。",
  "按有效样本 ≥8 门控即修正。",
], C.blue);
proseCard(s, 6.75, 4.35, 5.85, 2.5, "④ 融合的优势主要来自挑工具的虚高", [
  "给融合补交叉验证后：几何平均整合 0.352 已不胜最强单工具 MHCnuggets 0.447；表观优势约 0.17 来自未交叉验证时挑哪几个工具带来的虚高。",
  "头条的 SURV6 六工具无交叉验证依据。",
], C.crit);
citeFoot(s, "PEPTIDE_LENGTH_CONFOUNDER.md · fusion_nested_cv.csv");
pageno(s);

// ============================================================ 3.5 看懂指标（术语与参数速查，先看这页再看后面）
s = pres.addSlide();
header(s, "看懂指标", "本文用到的指标与参数（先看这页再看后面）", C.blue);
proseCard(s, 0.7, 1.5, 6.0, 3.2, "核心指标", [
  "逐患者 Spearman ρ̄：在每位患者体内，把工具的预测分和实测 ELISpot 各自按大小排名，看两个排名合不合拍——+1 完全一致、0 无关、−1 相反；再把 9 位患者的值平均。这是全文主指标，越高说明工具越准。",
  "ρ_XZ：某个工具的打分和「肽长」之间的这种排名相关——用来看这个工具的分是不是跟着肽长一起变。",
  "置信区间（CI）：这个数的误差范围；区间不跨过 0，就说明方向可信。",
  "p 值：纯靠运气也能出现这么大结果的概率；越小越不像是巧合。",
], C.blue);
proseCard(s, 6.85, 1.5, 5.78, 3.2, "矫正与融合里的参数", [
  "作弊上限（oracle）：用全部数据又挑工具又打分，最乐观的数。",
  "交叉验证（CV）：留一部分数据不参与挑选、只拿来「考试」，反映真实水平。",
  "挑工具的虚高 = 作弊上限 − 交叉验证。",
  "Δ（delta）：两个数之差、或前后变化。Kendall：两个排名有多一致（1=完全一致）。",
  "AUPRC / AUROC：把肽分成「有免疫反应/无反应」两类时，判别好坏的两个常用分，越高越好。",
], C.orange);
proseCard(s, 0.7, 4.82, 11.93, 2.08, "数据里的量", [
  "ELISpot（SFC）：实验测到的斑点数，代表免疫反应强弱（本文的「标准答案」）。",
  "TPM / CCF：这个突变在肿瘤里的表达量 / 克隆占比。子肽数：一条长肽里含突变的小片段个数。",
  "综合方式（pooling）：把一条肽内多个小片段的打分合成一个分——取最大值 max、求和 sum、几何平均 geomean、取前几高再平均 top-k 等。",
], C.green);
citeFoot(s, "术语说明 · 便于阅读后续图表");
pageno(s);

// ============================================================ 5 问题与逻辑
s = pres.addSlide();
header(s, "研究问题 · 两步逻辑", "为什么要把肽长（疫苗人为定的长度）从免疫原性评分里分离", C.blue);
proseCard(s, 0.7, 2.3, 5.75, 3.9, "第一步：先确证现象是否存在", [
  "评测里反复观察到一个现象——疫苗合成肽越长，ELISpot 检测到的免疫原性反应越强。",
  "所以第一步要严谨确证这一「肽越长、ELISpot 越高」的关系在数据里是否真实存在、在控制其他因素后是否依然成立。",
  "只有先站稳「存在」，后面讨论它对工具评测的影响才有意义。",
], C.blue);
proseCard(s, 6.75, 2.3, 5.85, 3.9, "第二步：它是否让工具排名虚高、需矫正", [
  "若现象存在，接着要问它是否让不同工具的排序能力被系统性抬高，从而需要在评分里把肽长的贡献扣除。",
  "评测的真正目标，是拿到突变本身的免疫原性；而肽长只是这条肽被合成多长——做疫苗时人为定的，不是突变本身的性质。",
  "因此有必要把肽长这一人为定的因素从工具评分里分离出来，才能公平比较各工具对突变免疫原性的排序能力。",
], C.orange);
citeFoot(s, "PEPTIDE_LENGTH_CONFOUNDER.md");
pageno(s);

// ============================================================ 4 点一 · 存在性（森林图，双面板 ratio=1.810）
s = pres.addSlide();
header(s, "点一 · 存在性", "疫苗肽越长、ELISpot 越高：控制混杂后依然成立", C.green);
placeImg(s, IMG.forest.p, IMG.forest.r, 0.5, 1.5, 7.7, 5.7);
proseCard(s, 8.4, 1.5, 4.2, 5.7, "逐患者秩相关与稳健性", [
  "逐患者 Spearman（肽长, ELISpot）等权平均 ρ̄=+0.380，95% 置信区间从 +0.196 到 +0.558，9 位患者中有 8 位为正。",
  "控制肿瘤表达 TPM 与克隆性 CCF 之后仍为 +0.299，控制子肽数之后仍为 +0.314，两个置信区间均不含 0。",
  "这说明长肽的高 ELISpot 并不是搭表达、克隆性或子肽计数的便车，而是肽长本身的独立效应。",
  "另一队列 DS1 的肽全部为 9 个氨基酸的短肽、没有长度变异，小鼠数据又缺失，因此当前结论基于单一队列，仍待外部验证。",
  "图左为各处理的相关与置信区间，图右为九位患者各自的体内相关；每组处理的含义与去掉肽长影响的公式见后两页。",
], C.green);
citeFoot(s, "existence_summary.csv · Braun 2025 DOI 10.1038/s41586-024-08507-5");
pageno(s);

// ============================================================ 5 点一 · 方法（控肽长的处理与公式）
s = pres.addSlide();
header(s, "点一 · 方法", "去掉肽长影响的处理与公式", C.green);
proseCard(s, 0.7, 1.6, 5.35, 5.35, "森林图每组处理的含义", [
  "主指标：每位患者体内单独算肽长与 ELISpot 的 Spearman 秩相关，再把九位患者的值用 Fisher-z 变换后等权平均，每位患者一票。",
  "控混杂：在上面基础上，把肿瘤表达、克隆性、子肽数、插入缺失标记等因素扣掉后再算相关（即偏相关），看肽长还剩多少相关。",
  "分层：只在错义或插入缺失、驱动或乘客等子集内分别计算，看效应是否只由某一类肽驱动。",
], C.green);
// 右侧正规数学公式图（matplotlib mathtext 渲染，ratio 0.8569）
placeImg(s, "D:/YJ-Agent/project/meeting/QuantImmuBench/figures/fig_peplen_formulas.png", 0.8569, 6.35, 1.5, 6.28, 5.5);
citeFoot(s, "METHODS_AND_FORMULAS.md · Liu 2018 Biometrics DOI 10.1111/biom.12812");
pageno(s);

// ============================================================ 6 点一 · 稳健性（七道检验，稳健性图 ratio=1.839）
s = pres.addSlide();
header(s, "点一 · 稳健性", "存在性稳健性：七道检验都指向同一个结论", C.green);
placeImg(s, IMG.robust.p, IMG.robust.r, 0.5, 1.6, 6.85, 5.0);
proseCard(s, 7.15, 1.5, 5.45, 5.7, "七道检验与小结", [
  "独立复算（不用引擎重写）：ρ̄=0.380，与原实现逐位一致。",
  "逐患者留一：任意去掉一位患者，ρ̄ 仍在 0.302 到 0.422 之间，九次全为正。",
  "患者体内置换检验：p=0.0004。",
  "符号检验：九位患者八位为正，双尾 p=0.039。",
  "用原值（非秩）的 Pearson：0.435，比秩相关更强。",
  "改用 8 到 11 氨基酸窗口重新计算：0.380，一致。",
  "单项与双项控制（表达、克隆性、子肽数）后置信区间均不含零；唯有同时控制全部四个因素时点估计仍为正 0.215，但因患者仅八位、功效不足，置信区间跨零，不作为显著结论。",
  "小结：主效应在六道检验下都指向同一个结论且置信区间不过零，唯一边界是四因素同控的小样本功效损失。",
], C.green);
citeFoot(s, "_scratch/peplen_existence_robustness.py · existence_summary.csv");
pageno(s);

// ============================================================ 7 点一 · 机制（肽长-ELISpot 散点，宽扁 ratio=2.3273）
s = pres.addSlide();
header(s, "点一 · 机制", "不是投料剂量假象，更可能是合成长肽的真实生物学", C.green);
placeImg(s, IMG.scatter.p, IMG.scatter.r, 0.5, 1.5, 12.35, 2.75);
proseCard(s, 0.5, 4.45, 12.35, 2.4, "为什么长肽给出更强反应", [
  "Braun 疫苗用 15 到 33 个氨基酸的合成长肽本身来刺激，配肽时按等质量投放。等质量之下，长肽的摩尔数更少、可用表位拷贝更少，本应给出更低的 ELISpot；而短肽在 ELISpot 里可以被直接负载呈递、技术上本就偏高。两条都指向长肽应更低，实测却更高。",
  "因此这不是投料剂量造成的假象，更可能是合成长肽的真实生物学：长肽携带更多辅助性 T 细胞表位，需要经过抗原加工与交叉呈递，从而诱导更强的反应。需保留一句限定，本实验含体外扩增，长肽经辅助获得了系统性放大，属于真实免疫原性，但不等同于体内保护效力。",
], C.green);
citeFoot(s, "MECHANISM_NOTES.md · Ott 2017 DOI 10.1038/nature22991 · Melief 2008 DOI 10.1038/nrc2373");
pageno(s);

// ============================================================ 8 点二 · 为何要矫正（矫正 delta 图，ratio=0.9017）
s = pres.addSlide();
header(s, "点二 · 为何要矫正", "单看肽长本身带来的影响因工具而异、不均匀，但整体变化很小", C.orange);
placeImg(s, IMG.delta.p, IMG.delta.r, 0.5, 1.5, 6.35, 5.7);
proseCard(s, 7.05, 1.5, 5.55, 5.7, "去掉肽长前后的差异 = 单看肽长本身带来的影响", [
  "把每个工具的评分与 ELISpot 的相关，在去掉肽长前后做比较，得到的差异就是单看肽长本身带来的影响。",
  "跨工具平均只有 +0.016，最大的是 TSCAPE 的 +0.102；有的工具被长度抬高（TSCAPE、ImmuneApp、IEDB_Calis），有的反而被压低（netMHCpan-BA、NeoTImmuML）。",
  "关键区别在于：肽长自身与 ELISpot 的相关很强（0.38），但一个工具要被污染，得它自己的评分也随长度走，而多数工具并非如此，所以去掉肽长对多数工具只改动几个百分点。",
  "结论是：这一影响因工具而异、并非均匀，所以该矫正、不能当成对所有方法一致的噪音；但整体变化很小，不会天翻地覆地重排。",
], C.orange);
citeFoot(s, "correction_matrix_9mer_matched.csv");
pageno(s);

// ============================================================ 9 点二 · 矫正方案菜单（表格）
s = pres.addSlide();
header(s, "点二 · 矫正方案", "矫正混杂有多族标准方法：这里该用哪种", C.orange);
tbl(s,
  ["方法", "原理", "本场景（逐患者秩相关，患者约 9，混杂与信号共线）"],
  [
    [{ text:"偏 Spearman（主分析）", bold:true }, "对评分与 ELISpot 各自扣除肽长后再算相关", { text:"最贴合，两边都扣肽长、小样本下方向可信", color:C.green, bold:true }],
    ["先从 ELISpot 减掉肽长（稳健性对照）", "只从 ELISpot 标签扣除肽长再与评分相关", { text:"适合对照，与主分析一致即加固", color:C.green }],
    ["分层/分箱内比较", "在肽长同层内比较再合并", { text:"弱，连续肽长分箱后每层样本过少", color:C.muted }],
    ["回归调整", "肽长作协变量同入回归", "可补充，能同控多因素但小样本系数不稳"],
    ["逆概率加权/匹配", "按肽长平衡分布", { text:"不推荐，为离散处理设计、连续肽长且样本少", color:C.crit }],
    ["秩内归一", "层内秩归一再合并", { text:"仅附注，同受小样本分层拖累", color:C.muted }],
  ],
  [3.0, 4.0, 5.6], 0.5, 1.5, { hh:0.5, rh:0.6, hfs:12, bfs:10.5 }
);
proseCard(s, 0.5, 5.75, 12.6, 1.05, "主张", [
  "这里样本太少（约 9 位患者），分层、加权匹配都不好用；所以主用「偏 Spearman」（扣掉肽长再算相关），另配「先从 ELISpot 减掉肽长」做对照，两个结果一致就更可信。",
], C.orange);
citeFoot(s, "CORRECTION_METHODS_AND_NOVELTY.md · Liu 2018 Biometrics DOI 10.1111/biom.12812");
pageno(s);

// ============================================================ 10 点二 · 机制一（工具级：控长改动由 ρ_XZ 决定，mechTool ratio=1.357）
s = pres.addSlide();
header(s, "点二 · 机制一", "为什么多数工具几乎不受肽长影响", C.orange);
placeImg(s, IMG.mechTool.p, IMG.mechTool.r, 0.5, 1.5, 7.7, 5.7);
proseCard(s, 8.4, 1.5, 4.2, 5.7, "为什么多数工具几乎不受肽长影响", [
  "肽长自身与 ELISpot 的相关约为 0.38，这个值对所有工具都一样；但肽长要经过工具才能污染它的评分，真正决定某个工具会不会被拉低的，是这个工具的打分跟不跟着肽长一起变。",
  "由公式可推出，去掉肽长的改动量，主要由『工具打分跟肽长一起变的程度』决定（近似为 0.41 乘以它、再减去 0.08 乘以原始相关）。",
  "数据验证：28 个工具里，『工具打分随肽长变的程度』与去掉肽长的改动量，相关达到 0.72；有 79% 的工具这一程度小于 0.2，它们平均只被去掉肽长改动 0.035。",
  "所以「肽长自身相关很强」与「多数工具没被搅动」并不矛盾：强的是肽长跟 ELISpot 的关系，而工具被不被拉要看它自己的打分跟不跟肽长走，多数工具几乎不跟。",
], C.orange);
citeFoot(s, "mechanism_toollevel.csv · PEPTIDE_LENGTH_CONFOUNDER.md §3a");
pageno(s);

// ============================================================ 11 点二 · 机制二（pooling：长度敏感度由聚合算子决定，mechPool ratio=1.613）
s = pres.addSlide();
header(s, "点二 · 机制二", "不同的综合方式，受肽长影响差别很大", C.orange);
placeImg(s, IMG.mechPool.p, IMG.mechPool.r, 0.5, 1.5, 7.7, 5.7);
proseCard(s, 8.4, 1.5, 4.2, 5.7, "不同综合方式，受肽长影响差别很大", [
  "肽越长内部子肽窗口越多（子肽数与肽长相关 0.755），长度几乎全通过「窗口数」这个通道起作用；一种综合方式越是随窗口数增多而系统抬升，就越受肽长影响。",
  "求和最危险：它机械地正比于窗口数，跨工具平均相关高达 0.61，这正是项目弃用求和的原因。",
  "取最大值、均值、几何均值、softmax、rankdecay 都很低，在 0.10 到 0.16 之间；项目主分析给免疫原性工具取最大值、并且不用求和，正是受肽长影响最小的一档。",
  "中间档的 top-k 均值（k 在 3 到 20）反而比取最大值略高，因为「从更多窗口里挑出 k 个最高再平均」带来选择增益，这个增益在中等 k 最强，两头反而弱；因此项目给结合类工具用的 top-k 综合方式，是除求和外最该去掉肽长的。",
], C.orange);
citeFoot(s, "mechanism_pooling.csv · 取最大值/top-k：一条肽能选的小片段越多越易蒙到高分");
pageno(s);

// ============================================================ 12 点二 · 排名影响与融合
s = pres.addSlide();
header(s, "点二 · 排名影响", "去掉肽长后工具排名基本没变，几何平均融合仍最稳", C.blue);
proseCard(s, 0.7, 1.6, 5.75, 5.35, "工具排名基本没变", [
  "去掉肽长前后，工具排名的 Kendall 一致性约为 0.76，也就是排名基本没变、几乎不重排。",
  "排序能力最强的几个工具——MHCnuggets、netMHCpan-BA、MHCflurry、PRIME——在去掉肽长前后都稳居前列。",
  "换句话说，扣除肽长这一人为定的因素之后，谁强谁弱的整体格局基本不变。",
], C.blue);
proseCard(s, 6.75, 1.6, 5.85, 5.35, "融合：几何平均仍居首", [
  "几何平均在头部维度配置下、即使去掉肽长也仍是最稳的融合方式（把几个工具的打分做几何平均，不看答案、不会作弊）。",
  "六维配置从 0.402 降至 0.330 仍居首，七维配置从 0.449 降至 0.407 仍居首。",
  "但去掉肽长之后，它对最强单工具（netMHCpan-BA 约 0.432）的领先收窄为大致持平。",
], C.green);
citeFoot(s, "correction_matrix_9mer_matched.csv · R3_fusion_12methods_official.csv");
pageno(s);

// ============================================================ 13 进阶 · 交叉验证（fusion 嵌套 CV，fusionCV ratio=1.763）
s = pres.addSlide();
header(s, "进阶 · 交叉验证", "Fusion 交叉验证：整合优势主要来自挑了哪几个工具", C.orange);
placeImg(s, IMG.fusionCV.p, IMG.fusionCV.r, 0.5, 1.5, 8.0, 5.5);
proseCard(s, 8.7, 1.5, 3.9, 5.5, "给多工具融合补交叉验证后的发现", [
  "把几个工具打分做几何平均来综合，不看答案、不会把不该看到的信息用进去；但头条的六工具组合 SURV6，成员是在全数据上挑定、从未交叉验证，存在挑工具带来的虚高。",
  "补一层严格交叉验证（把一位患者放到一边，只用其余患者来挑工具，再回头考这位患者）后，几何平均整合点估计 0.352 已低于最强单工具 MHCnuggets 的 0.447；配对检验 p 为 0.12 与 0.55，九位患者功效不足，未检出差异不等于两者相等。",
  "须分清两个数：固定六工具组合几乎没被夸大，0.366 与严格交叉验证 0.352 只差约 0.01；而 0.17 是「重新挑工具」这一动作带来的虚高上限（全数据 0.525 减 0.352）。",
  "若结合亲和力工具的授权未获批，可报告组合里整合会显著落后单工具，此时应直接部署最强单工具 MHCnuggets。",
], C.orange);
citeFoot(s, "fusion_nested_cv.csv · 留一患者交叉验证下的挑工具虚高");
pageno(s);

// ============================================================ 14 进阶 · 收口（控长重排 / AUPRC / 退化审计，表格）
s = pres.addSlide();
header(s, "进阶 · 补充分析", "补充分析：去掉肽长后对下游的影响", C.orange);
proseCard(s, 0.5, 1.55, 12.6, 0.78, "把去掉肽长后的分析推到下游", [
  "把去掉肽长后的分析推到下游——最优综合方式的重选、二分类判别、机制的饱和度、以及所有综合方式的小样本假满分相关审计。",
], C.orange);
tbl(s,
  ["发现", "结果"],
  [
    ["去掉肽长后重选最优综合方式", "13/30 工具换选综合方式，工具榜 HLAthena 从第 1 跌到第 18（0.627→0.250）"],
    ["长度对二分类判别", "先减掉肽长影响后 AUPRC 排名一致性 0.63，比连续排序的 0.76 更受长度影响"],
    ["饱和度假说", "四个饱和度量里两个方向符合、两个反向，弱支持、非干净确认"],
    ["小样本假满分相关审计", "从只看取最大值的 2 个，扩到全部综合方式的 95 个假满分点，小 k 与 softmax 占 44%"],
  ],
  [3.6, 9.0], 0.5, 2.7, { hh:0.5, rh:0.95, hfs:12.5, bfs:11.5 }
);
citeFoot(s, "pooling_reselect_summary.csv · auprc_lenctrl.csv · degenerate_audit_allpooling.csv");
pageno(s);

// ============================================================ 15 其他 · 顺带发现（与肽长无关的小样本偏高）
s = pres.addSlide();
header(s, "其他 · 顺带发现", "一个与肽长无关的小样本偏高：应独立优先修正", C.warn);
proseCard(s, 0.7, 1.6, 11.9, 2.55, "两个工具的原始相关被单个小样本患者夸大", [
  "核对时发现，两个工具的原始相关被单个小样本患者夸大：HLAthena 在患者 P101 上仅有 3 个非空评分，产生了虚假的完全相关，把它的相关从真实的约 0.207 抬高到 0.627；NetTepi 在患者 P102 上同理。",
  "之前「HLAthena 因肽长掉 0.377」这一例子，大半其实来自这个小样本偏高，而非肽长。",
], C.warn);
proseCard(s, 0.7, 4.35, 11.9, 2.55, "这是独立于肽长的问题，应优先修正", [
  "这是一个与肽长无关的独立问题，不应和肽长混杂混为一谈。",
  "项目已有的、要求每位患者有效样本不少于 8 的算法给出修正值：HLAthena 为 0.207、NetTepi 为 0.293。",
  "建议将这一算法设为主榜，并优先修正这两个被小样本夸大的相关。",
], C.warn);
citeFoot(s, "degenerate_audit.csv · R1_recomputed_effN8.csv");
pageno(s);

// ============================================================ 16 结论 · 新颖性与三条结论
s = pres.addSlide();
header(s, "结论 · 新颖性", "把肽长当作需统计扣除的评测混杂，检索未见先例", C.blue);
proseCard(s, 0.7, 1.6, 5.75, 5.35, "新颖性定位", [
  "肽长作为免疫原性特征早已进入各类模型，这一点并不新。",
  "但把肽长当作会让工具排名虚高、需要用统计方法扣除的评测混杂，在疫苗 ELISpot 幅度评测这一具体场景里，检索未见先例。",
  "领域的通行做法是控制 MHC 结合并做长度分布匹配，而不是用秩相关来矫正肽长这一混杂。",
], C.blue);
proseCard(s, 6.75, 1.6, 5.85, 5.35, "三条结论", [
  "其一，长肽的高 ELISpot 真实且在队列内稳健，机制是合成长肽的生物学，而非投料剂量假象。",
  "其二，肽长对工具排名有差异但温和的影响，未校正与校正后的结果应并列报告。",
  "其三，另有一个与肽长无关的小样本偏高问题，应优先修正。",
], C.green);
citeFoot(s, "CORRECTION_METHODS_AND_NOVELTY.md · Exploration of Immunology 综述");
pageno(s);

// ============================================================ 17 建议与局限
s = pres.addSlide();
header(s, "建议 · 局限", "落地建议与局限", C.blue);
proseCard(s, 0.7, 1.6, 5.75, 5.35, "建议", [
  "校正肽长后的结果不替换主结果，两者并列报告。",
  "优先修正那个与肽长无关的小样本偏高问题。",
  "可考虑把这两个发现写成一个评测严谨性的小节，作为方法学层面的贡献。",
], C.green);
proseCard(s, 6.75, 1.6, 5.85, 5.35, "局限", [
  "本结论基于单一队列：DS1 全为 9mer 无法复现长度效应，小鼠数据缺失。",
  "Braun 原文的精确配肽浓度经二手提取，等质量方向已由 Ott 2017 佐证，但仍建议人工核对补充材料。",
  "融合分析目前仅做到单工具与融合层，其余留作后续工作。",
], C.orange);
citeFoot(s, "PEPTIDE_LENGTH_CONFOUNDER.md · 给袁老师_肽长矫正决策档.md");
pageno(s);

// ============================================================ 19 进行中 · 下一步（融合选择的原则化交叉验证）
s = pres.addSlide();
header(s, "进行中 · 下一步", "正在接续跑：给融合选择补原则化交叉验证", C.green);
proseCard(s, 0.7, 1.6, 5.75, 5.35, "在解决的问题", [
  "融合到底该选哪些工具、选几个、用哪种融合方式，目前没有原则化答案。",
  "头条的六工具组合当初是在全部数据上挑定的、从没系统交叉验证过，没有可追溯的选择依据。",
], C.blue);
proseCard(s, 6.75, 1.6, 5.85, 5.35, "正在跑什么 + 状态", [
  "一套不会把不该看到的信息用进去的交叉验证选择引擎：随工具个数变化的曲线回答『选几个』、五种选择程序横比回答『怎么选』、稳定性选择回答『哪些工具可信』、两组把答案打乱后的对照，用来区分挑工具靠的是运气还是真信号。",
  "另有十三条『每个方法学决策各配一个受控对照实验』，逐条证明为什么这样做。",
  "要先说清的前提：九位患者下不宣称唯一最优，报交叉验证最优、加上统计上分不出高下的一批组合、加上入选频率；预期很可能是少数几个工具、甚至单个最强工具就够。",
  "状态：引擎已建成、含零偏离自检，正在运行，约几分钟出结果。",
], C.green);
citeFoot(s, "select_engine.py · rationale_ablations.py · SELECT_DESIGN.md");
pageno(s);

pres.writeFile({ fileName:"QuantImmuBench_肽长混杂_2026-07-05.pptx" }).then(f=>console.log("written:", f));
