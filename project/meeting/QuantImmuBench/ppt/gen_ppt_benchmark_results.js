// QuantImmuBench — benchmark 结果总览（合并 deck，12 页：封面 + 11 内容页）
// 把原先分散在 progress deck(9mer) + 8to11mer supplement 两处的结果合成一份：
//   9mer 主口径 + 8-11mer 补充口径 Spearman 图 + pooling / robustness / 融合严格检验
//   + 工具打分相关结构四图（层次聚类树 / 椭圆 corrplot / 相关性网络 / MDS 工具地图）全部核心结果。
//   （已去掉 §3.4 综合排名整页。）
// 样式引擎复用 gen_ppt_progress_v4.js 的 helper（header/placeImg/citeFoot/proseCard/tbl），
// 配色改用 Okabe-Ito（#0072B2 蓝 / #E69F00 橙 / #009E73 绿），Microsoft YaHei 中文字体，LAYOUT_WIDE。
// 图片一律按真实宽高比 contain 不拉伸（ratio 由 PNG IHDR 静态量得，见各页注释）。
// 数字全部逐字采用主线 Bash 已核实值，零自造；图只引 8 个已确认存在的绝对路径 png。
// 运行(主线跑，本脚本作者不跑): NODE_PATH=C:/Users/yj200/AppData/Roaming/npm/node_modules node ppt/gen_ppt_benchmark_results.js
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "QuantImmuBench — 新抗原免疫原性工具系统评测（结果总览）";

const W = 13.33, H = 7.5;
// 中性底色沿用模板，accent 三色换成 Okabe-Ito（teal 别名 = Okabe 蓝，供 citeFoot 标签色复用）
const C = {
  dark:"0B3C49", teal:"0072B2", blue:"0072B2", orange:"E69F00", green:"009E73",
  light:"F2F7F7", card:"FFFFFF", ink:"16323A", muted:"5E7B83",
  line:"D5E3E4", warn:"E69F00", ok:"009E73", crit:"B23A48", gray:"8A9BA0",
};
const FH = "Microsoft YaHei", FB = "Microsoft YaHei", FM = "Consolas";
const sh = () => ({ type:"outer", color:"0B3C49", blur:9, offset:3, angle:135, opacity:0.12 });

// 8 张图（存在性已由主线 Bash 确认），ratio = 宽/高（PNG IHDR 静态量）
const IMG = {
  sp9:   { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/official/recompute_effN/fig1_spearman_30tools_9mer_effN8.png",    r:0.9909 },
  sp811: { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/official/recompute_effN/fig1_spearman_30tools_8to11mer_effN8.png", r:0.9909 },
  // §2.2 长度口径哑铃对比（分两张：上半 15 工具 / 下半 14 工具；均 figsize 9.6×7.6 => ratio=1.2632，plot_fig_lencompare.py 静态保证不用 tight bbox）
  lc1:   { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/official/figures/fig_lencompare_1.png",                            r:1.2632 },
  lc2:   { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/official/figures/fig_lencompare_2.png",                            r:1.2632 },
  pool:  { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/official/figures/fig2_pooling_shuffle.png",                        r:0.9923 },
  robust:{ p:"D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/official/figures/fig3_robustness.png",                            r:1.3294 },
  // 工具打分相关结构四图（ratio 由各 PNG IHDR 静态量得；network 每次重出，比例约 1.14 稳定，placeImg contain 不拉伸）
  tcDendro:{ p:"D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/official/figures/fig_toolcorr_dendrogram.png",                  r:1.4330 },
  tcCorr:  { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/official/figures/fig_toolcorr_corrplot.png",                    r:1.0009 },
  tcNet:   { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/official/figures/fig_toolcorr_network.png",                     r:1.1376 },
  tcMds:   { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/official/figures/fig_toolcorr_mds.png",                         r:1.1911 },
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

// ============================================================ 1 封面
let s = pres.addSlide();
s.background = { color: C.dark };
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.green} });
s.addShape(pres.shapes.OVAL, { x:W-3.3, y:-1.6, w:4.6, h:4.6, fill:{color:C.blue, transparency:78} });
s.addShape(pres.shapes.OVAL, { x:W-2.0, y:3.6,  w:3.2, h:3.2, fill:{color:C.green, transparency:82} });
s.addText("癌症个性化新抗原疫苗 · 免疫原性工具系统评测", { x:0.9, y:1.35, w:11.5, h:0.4, fontFace:FB, fontSize:15, color:C.green, bold:true, charSpacing:2, margin:0 });
s.addText("QuantImmuBench — 新抗原免疫原性工具系统评测\n（结果总览）", { x:0.9, y:1.95, w:11.6, h:1.9, fontFace:FH, fontSize:34, bold:true, color:"FFFFFF", lineSpacingMultiple:1.05, margin:0 });
s.addShape(pres.shapes.LINE, { x:0.95, y:4.35, w:3.2, h:0, line:{color:C.green, width:2} });
s.addText([
  { text:"30 工具（10 呈递 + 20 免疫原性）× DS2 官方 130 肽 / 9 患者（Braun 2025）", options:{ breakLine:true, paraSpaceAfter:6 } },
  { text:"QuantImmu 三步框架：逐行打分 → pooling → rank-fusion", options:{ breakLine:true, paraSpaceAfter:6 } },
  { text:"主指标 = per-patient Spearman 等权平均", options:{ breakLine:true, bold:true, color:"CFE7F5" } },
], { x:0.95, y:4.65, w:11.4, h:1.7, fontFace:FB, fontSize:15, color:"E6F2F2", valign:"top", lineSpacingMultiple:1.25, margin:0 });
s.addText("2026-07-04", { x:W-2.4, y:6.75, w:1.8, h:0.3, fontFace:FB, fontSize:12, color:"8FB7BD", align:"right", margin:0 });

// ============================================================ 2 §3.1 单工具 Spearman · 9mer 主口径（fig1 9mer ratio=0.9909）
s = pres.addSlide();
header(s, "核心结果 · §3.1 单工具主指标", "单工具 Spearman · 9mer 主口径（effN≥8，n=9 患者）", C.blue);
placeImg(s, IMG.sp9.p, IMG.sp9.r, 0.5, 1.5, 7.6, 5.7);
proseCard(s, 8.3, 1.5, 4.3, 5.7, "9mer 主口径要点（Spearman，effN≥8，n=9 患者）", [
  "排序能力最强的三个工具为 MHCnuggets 0.447、netMHCpan-BA 0.392、MHCflurry 0.308。",
  "顶部工具的相关集中在 0.39 到 0.45 这一狭窄区间，且置信区间大幅重叠。",
  "换句话说，不存在单一压倒性的王座工具，头部几个工具在统计上难以区分。",
  "MHCnuggets 数值居首，netMHCpan-BA 仍是结合亲和力方向的基准锚点。",
], C.blue);
citeFoot(s, "R1_recomputed_effN8.csv · per-patient Spearman（9mer，effN≥8）");
pageno(s);

// ============================================================ 3 §3.1 单工具 Spearman · 8-11mer 补充口径（fig1 8to11mer ratio=0.9909）
s = pres.addSlide();
header(s, "核心结果 · §3.1 单工具主指标", "单工具 Spearman · 8-11mer 补充口径", C.blue);
placeImg(s, IMG.sp811.p, IMG.sp811.r, 0.5, 1.5, 7.6, 5.7);
proseCard(s, 8.3, 1.5, 4.3, 5.7, "8-11mer 补充口径要点", [
  "把评测放宽到 8 到 11 个氨基酸的可变窗口径下，排序能力最强的三个工具为 MHCnuggets 0.373、netMHCpan-BA 0.289、MHCflurry 0.286。",
  "工具排序与 9mer 主口径基本一致，MHCnuggets 仍居首。",
  "但整体数值较 9mer 主口径有所回落，本页作为补充口径呈现，主分析以 9mer 为准。",
], C.blue);
citeFoot(s, "R1_recomputed_8to11mer_effN8.csv · per-patient Spearman（8-11mer，effN≥8）");
pageno(s);

// ============================================================ 4 §2.2 长度口径 9mer vs 8-11mer · 逐工具哑铃（上半 15 工具，lc1 ratio=1.2632）
s = pres.addSlide();
header(s, "评测口径 · §2.2 长度口径", "9mer 主口径 vs 8-11mer 可变窗 · 逐工具对比（上半 15 工具）", C.blue);
placeImg(s, IMG.lc1.p, IMG.lc1.r, 0.5, 1.5, 7.6, 5.7);
proseCard(s, 8.3, 1.5, 4.3, 5.7, "口径决策 · 关键数字", [
  "每行一个工具：实心蓝点 = 9mer 主口径，空心橙点 = 8-11mer 可变窗，横线连两点。",
  "9mer 平均排序能力 ρ=0.187，明显高于 8-11mer 可变窗 ρ=0.121。",
  "29 个共同工具里有 25 个在 9mer 上不劣于 8-11mer；仅 4 个工具 8-11mer 反超（连线标红），诚实呈现「多数但非全部」。",
  "因此主分析统一采用 9AA-only 口径，8-11mer 结果作为补充分析。本页为上半（9mer ρ 较高的 15 个工具），下半见次页。",
], C.blue);
citeFoot(s, "R1_recomputed_effN8.csv · R1_recomputed_8to11mer_effN8.csv · per-patient Spearman（effN≥8，n=130 肽）");
pageno(s);

// ============================================================ 5 §2.2 长度口径 · 逐工具哑铃（下半 14 工具，lc2 ratio=1.2632）
s = pres.addSlide();
header(s, "评测口径 · §2.2 长度口径", "9mer 主口径 vs 8-11mer 可变窗 · 逐工具对比（下半 14 工具）", C.blue);
placeImg(s, IMG.lc2.p, IMG.lc2.r, 0.5, 1.5, 7.6, 5.7);
proseCard(s, 8.3, 1.5, 4.3, 5.7, "诚实脚注 · 口径不对称", [
  "本页为下半（9mer ρ 较低的 14 个工具），读法同上页；均值/计数注文（0.187 vs 0.121、25/29）为全 29 工具口径。",
  "补充口径的一处不对称：8-11mer 分析中，真正的插入缺失突变（DEL + INS 共 28 肽）仍只在 9mer 窗上展开。",
  "子肽窗口展开对 SNV 与 indel 两类突变并不对称，解读 8-11mer 结果时需注意这一处不一致。",
], C.orange);
citeFoot(s, "R1_recomputed_effN8.csv · R1_recomputed_8to11mer_effN8.csv · per-patient Spearman（effN≥8，n=130 肽）");
pageno(s);

// ============================================================ 6 §3.2 pooling「洗牌」（fig2 ratio=0.9923）
s = pres.addSlide();
header(s, "核心结果 · §3.2 子肽聚合", "pooling「洗牌」：最优聚合方式因工具类别而异", C.green);
placeImg(s, IMG.pool.p, IMG.pool.r, 0.5, 1.5, 7.6, 5.7);
proseCard(s, 8.3, 1.5, 4.3, 5.7, "子肽聚合规律", [
  "结合与亲和力类工具依靠把一条肽切出的多个子肽窗口聚合起来获得提升，最优算子是 top-k、softmax 或 rankdecay 这类聚合，而非取单一最大值。",
  "以 netMHCpan-BA 为例，最大池化（max）的排序能力为 0.432，改用 top-k 聚合后升至 0.525。",
  "免疫原性类工具则相反，取单个最强窗口（max）就已接近最优。",
  "聚合方式不能一刀切，工具类别决定最优的池化策略。",
], C.green);
citeFoot(s, "R2_best_per_tool.csv · 各工具最优子肽聚合算子");
pageno(s);

// ============================================================ 7 §3.3.4 删突变鲁棒性（fig3 ratio=1.3294）
s = pres.addSlide();
header(s, "核心结果 · §3.3.4 鲁棒性", "删突变鲁棒性：几何均值融合最稳", C.green);
placeImg(s, IMG.robust.p, IMG.robust.r, 0.5, 1.5, 7.6, 5.7);
proseCard(s, 8.3, 1.5, 4.3, 5.7, "删突变鲁棒性", [
  "在删除 10% 与 20% 突变的鲁棒性检验下，几何均值（geomean）融合的头名命中率 win_rate_top1 分别为 0.567 与 0.600。",
  "两种删除强度下，几何均值融合都稳居第一名（rank1）。",
  "这说明当突变信息受损时，几何均值融合仍是最稳健的选择。",
], C.green);
citeFoot(s, "R6_robustness_official_summary.csv · 删突变鲁棒性汇总");
pageno(s);

// ============================================================ 8 §3.3 融合与严格检验（文字页 · 三列）
s = pres.addSlide();
header(s, "核心结果 · §3.3 融合与严格检验", "融合默认、无泄漏检验、整合 vs 最强单", C.green);
proseCard(s, 0.7, 1.7, 3.84, 5.25, "融合默认：几何均值", [
  "几何均值是共识类融合里最稳的默认选择。",
  "它与算术秩均值（mean-rank）、中位数（median）互为数学近亲，三者的排序相关高达 0.97。",
  "因此把几何均值作为融合的默认算子。",
], C.green);
proseCard(s, 4.74, 1.7, 3.84, 5.25, "nested-LOPO：零过拟合", [
  "无信息泄漏的嵌套留一患者验证下，LOPO 排序能力 ρ=0.275，与 oracle 上界 0.297 几乎相等，间隙仅 0.018。",
  "1000 次置换构造的零分布下，经验 p 值为 0.013，真值落在第 98.8 百分位。",
  "即信号显著、且并非泄漏所致。",
], C.blue);
proseCard(s, 8.78, 1.7, 3.84, 5.25, "整合 vs 最强单：持平", [
  "整合方案（SURV6 六工具几何均值）排序能力 0.366，最强单工具 MHCnuggets 为 0.447。",
  "配对置换检验：裸口径 p=0.46、控肽长 p=0.22，两者统计上持平。",
  "点估计上整合略逊于最强单工具，整合的价值在于事先不知哪个工具最优时给出稳健输出。",
], C.orange);
citeFoot(s, "R5 nested-LOPO · R7 显著性配对置换");
pageno(s);

// ============================================================ 9 工具打分相关结构 · 层次聚类树（tcDendro ratio=1.4330，宽扁）
s = pres.addSlide();
header(s, "核心结果 · 工具打分相关结构", "工具打分相关结构 · 层次聚类树", C.blue);
placeImg(s, IMG.tcDendro.p, IMG.tcDendro.r, 0.5, 1.5, 7.6, 5.7);
proseCard(s, 8.3, 1.5, 4.3, 5.7, "层次聚类树读法", [
  "按 1−|Spearman ρ| 距离对工具做层次聚类。",
  "叶标签配色：蓝=抗原呈递/结合类，橙=免疫原类。",
  "先合并（树最低处相接）= 打分最像的近亲工具。",
  "真源 pooled_clean_9mer.csv 30 工具 _max 列 per-peptide Spearman（n=130 肽，剔 DeepNetBim 常数列 → 29 工具）。",
], C.blue);
citeFoot(s, "pooled_clean_9mer.csv · 30 工具 _max 列 per-peptide Spearman（n=130 肽，剔 DeepNetBim → 29 工具）");
pageno(s);

// ============================================================ 10 工具打分相关结构 · 椭圆 corrplot（tcCorr ratio=1.0009，近方）
s = pres.addSlide();
header(s, "核心结果 · 工具打分相关结构", "工具打分相关结构 · 椭圆 corrplot", C.blue);
placeImg(s, IMG.tcCorr.p, IMG.tcCorr.r, 0.5, 1.5, 7.6, 5.7);
proseCard(s, 8.3, 1.5, 4.3, 5.7, "椭圆 corrplot 读法", [
  "每格画一个椭圆，不是填色热图。",
  "椭圆越扁 = |ρ| 越大（越相关）；朝向编码正负相关。",
  "颜色深浅 = ρ 大小。",
  "行列按层次聚类重排，黑框圈出同一相关簇。",
], C.blue);
citeFoot(s, "pooled_clean_9mer.csv · 30 工具 _max 列 per-peptide Spearman（n=130 肽，剔 DeepNetBim → 29 工具）");
pageno(s);

// ============================================================ 11 工具打分相关结构 · 相关性网络（tcNet ratio≈1.14，近方；每次重出）
s = pres.addSlide();
header(s, "核心结果 · 工具打分相关结构", "工具打分相关结构 · 相关性网络", C.blue);
placeImg(s, IMG.tcNet.p, IMG.tcNet.r, 0.5, 1.5, 7.6, 5.7);
proseCard(s, 8.3, 1.5, 4.3, 5.7, "相关性网络读法", [
  "节点 = 工具：蓝=呈递/结合，橙=免疫原；节点大小 ∝ 单工具 per-patient Spearman 性能。",
  "|ρ|≥0.4 才连边，线宽 ∝ |ρ|。",
  "一眼看出：相互高度相关的核心团、由核心辐射出的相关链、以及游离在外的离群工具。",
], C.blue);
citeFoot(s, "pooled_clean_9mer.csv per-peptide Spearman（n=130，|ρ|≥0.4 连边） · 节点大小 R1_recomputed_effN8.csv");
pageno(s);

// ============================================================ 12 工具打分相关结构 · MDS 工具地图（tcMds ratio=1.1911，宽 ~1.2）
s = pres.addSlide();
header(s, "核心结果 · 工具打分相关结构", "工具打分相关结构 · MDS 工具地图", C.blue);
placeImg(s, IMG.tcMds.p, IMG.tcMds.r, 0.5, 1.5, 7.6, 5.7);
proseCard(s, 8.3, 1.5, 4.3, 5.7, "MDS 工具地图读法", [
  "按 1−|ρ| 距离把工具投到二维平面（多维标度 MDS）。",
  "两点位置越近 = 两工具打分越相似。",
  "背景色块 = KMeans 4 簇划分，辅助看工具分群。",
], C.blue);
citeFoot(s, "pooled_clean_9mer.csv · 1−|ρ| 距离 MDS（n=130 肽，29 工具，KMeans 4 簇）");
pageno(s);

pres.writeFile({ fileName:"D:/YJ-Agent/project/meeting/QuantImmuBench/QuantImmuBench_benchmark_results_2026-07-04.pptx" }).then(f=>console.log("WROTE", f, "pages", _PG));
