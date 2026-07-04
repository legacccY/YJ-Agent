// QuantImmuBench — 阶段进度与方法学评价 v4（给袁老师周五讨论用 · 进度评价扩充版）
// 复用初始化 / 16 色板 / 母版 / 卡片 / 表格 / citeFoot / placeImg helper（样式引擎不重造）
// 结构：进度与 30 工具部署 → 数据口径 → 三层核心结果（Spearman 头条）→ 方法学评价专章 → 局限
// 图片一律按真实宽高比 contain 不拉伸（ratio 已由 PNG IHDR 静态量得，见各页注释）
// 运行(主线跑，本脚本作者不跑): NODE_PATH=C:/Users/yj200/AppData/Roaming/npm/node_modules node ppt/gen_ppt_progress_v4.js
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "QuantImmu 新抗原免疫原性定量评测框架 — 阶段进度与方法学评价";

const W = 13.33, H = 7.5;
const C = {
  dark:"0B3C49", teal:"028090", sea:"00A896", mint:"02C39A",
  light:"F2F7F7", card:"FFFFFF", ink:"16323A", muted:"5E7B83",
  line:"D5E3E4", warn:"C9743D", ok:"00A896", crit:"B23A48", gray:"8A9BA0",
};
const FH = "Microsoft YaHei", FB = "Microsoft YaHei", FM = "Consolas";
const FIG4 = "D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/figures_ppt_v4";
const sh = () => ({ type:"outer", color:"0B3C49", blur:9, offset:3, angle:135, opacity:0.12 });

let _PG = 1;
function header(slide, kicker, title, accent=C.teal){
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
  const runs=[{ text:"来源  ", options:{ color:C.teal, fontSize:9, bold:true } }];
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
// 图片按真实宽高比 contain 进容器（ratio = 宽/高，由调用方传入实测值）
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
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.mint} });
s.addShape(pres.shapes.OVAL, { x:W-3.3, y:-1.6, w:4.6, h:4.6, fill:{color:C.teal, transparency:78} });
s.addShape(pres.shapes.OVAL, { x:W-2.0, y:3.6,  w:3.2, h:3.2, fill:{color:C.sea,  transparency:82} });
s.addText("癌症个性化新抗原疫苗 · 免疫原性定量评测", { x:0.9, y:1.5, w:11, h:0.4, fontFace:FB, fontSize:15, color:C.mint, bold:true, charSpacing:2, margin:0 });
s.addText("QuantImmu 新抗原免疫原性定量评测框架\n阶段进度与方法学评价", { x:0.9, y:2.05, w:11.5, h:1.8, fontFace:FH, fontSize:38, bold:true, color:"FFFFFF", lineSpacingMultiple:1.05, margin:0 });
s.addShape(pres.shapes.LINE, { x:0.95, y:4.55, w:3.2, h:0, line:{color:C.mint, width:2} });
s.addText("30 工具系统横评 · 官方 130 肽口径 · 2026-07-01", { x:0.9, y:4.8, w:11.8, h:0.5, fontFace:FB, fontSize:15, color:"CADCFC", margin:0 });
s.addText("本版围绕项目当前阶段进度展开，先说明三十个预测工具的部署到位情况与数据口径，再依次呈现单工具基线、子肽聚合规律与多工具融合三层核心结果，最后用单独一章系统说明如何看待这批数据，包括已经处理好的方法学问题和留待周五讨论的两处措辞。", { x:0.95, y:5.4, w:11.0, h:1.1, fontFace:FB, fontSize:13, color:"E6F2F2", valign:"top", lineSpacingMultiple:1.2, margin:0 });
s.addText("2026-07-01", { x:W-2.4, y:6.7, w:1.8, h:0.3, fontFace:FB, fontSize:12, color:"8FB7BD", align:"right", margin:0 });

// ============================================================ 2 目录
s = pres.addSlide();
header(s, "目录", "本报告的内容结构");
const toc = [
  ["01","进度与工具部署","三十个工具的部署到位情况与整体完成度"],
  ["02","数据与评测口径","主分析集 主副指标 与聚合方式"],
  ["03","三层核心结果","单工具基线 子肽聚合规律 多工具融合"],
  ["04","方法学评价专章","如何看待这批数据 及三个评价要点"],
  ["05","局限与下一步","当前限制 与周五要讨论的问题"],
];
toc.forEach((it,i)=>{
  const y = 1.9 + i*1.02;
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y, w:11.9, h:0.86, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y, w:0.09, h:0.86, fill:{color:C.teal} });
  s.addText(it[0], { x:0.95, y:y+0.13, w:0.9, h:0.6, fontFace:FH, fontSize:26, bold:true, color:C.sea, valign:"middle", margin:0 });
  s.addText(it[1], { x:2.0, y:y+0.12, w:4.4, h:0.42, fontFace:FH, fontSize:16, bold:true, color:C.ink, valign:"middle", margin:0 });
  s.addText(it[2], { x:6.5, y:y+0.12, w:5.9, h:0.62, fontFace:FB, fontSize:12, color:C.muted, valign:"middle", margin:0 });
});
pageno(s);

// ============================================================ 3 进度总览（progress_overview.png ratio=1.871）
s = pres.addSlide();
header(s, "进度总览", "工具接入 数据到位 评测流程的整体完成度");
placeImg(s, `${FIG4}/progress_overview.png`, 1.871, 0.7, 1.7, 7.05, 5.25);
proseCard(s, 7.95, 1.7, 4.68, 5.25, "阶段进度要点", [
  "工具接入已全部完成，三十个工具全部部署跑通并进入官方一百三十肽评测，其中八种属于抗原呈递与结合方向，二十二种属于免疫原性方向。",
  "人源数据两套均已就位，一套是六例黑色素瘤的早期数据集，另一套是官方发布的一百三十条肽、九名患者的主分析队列。",
  "小鼠数据两套目前都还没有，正在收集当中。",
  "评测所需的方法学工具已全部跑通，包括十二种融合方法、四种子肽聚合算子，以及三重检验流程。",
], C.teal);
citeFoot(s, "项目进度追踪（2026-07-01）· 官方一百三十肽队列");
pageno(s);

// ============================================================ 4 30 工具部署清单·呈递/结合类（10）— DEPLOY_TRACKER 表 A
s = pres.addSlide();
header(s, "工具部署清单 · 一", "抗原呈递与结合类共八种工具的部署状态");
tbl(s, ["工具","分数类型","部署状态","许可"], [
  [{text:"netMHCpan-4.1 (BA)",bold:true}, "结合亲和力", "已部署", {text:"DTU 学术许可",color:C.warn}],
  ["netMHCpan-4.1 (EL)", "抗原呈递", "已部署", {text:"DTU 学术许可",color:C.warn}],
  ["MHCflurry 2.0", "抗原呈递 / 亲和力", "已部署", "Apache-2.0"],
  ["netMHCstabpan", "结合稳定性", "已部署", {text:"DTU 学术许可",color:C.warn}],
  ["TransHLA", "抗原呈递", "已部署", "MIT"],
  ["MHCnuggets", "结合亲和力", "已部署", "BSD 类"],
  ["MHCSeqNet", "抗原呈递", "已部署", "Apache-2.0"],
  ["HLAthena", "抗原呈递代理", "已部署（代理）", "学术"],
], [3.5, 2.7, 2.6, 3.1], 0.7, 2.0, { rh:0.46, hh:0.48, bfs:12, hfs:12 });
s.addText("呈递与结合类工具预测肽段能否被 MHC 分子提呈或结合，是免疫原性预测的上游环节。标注 DTU 学术许可的工具，其对比数字在对外公布前需先取得书面同意。", { x:0.7, y:6.75, w:11.9, h:0.5, fontFace:FB, fontSize:11.5, color:C.muted, valign:"top", lineSpacingMultiple:1.15, margin:0 });
citeFoot(s, "工具部署总表 表 A（呈递/结合组）· 官方一百三十肽口径");
pageno(s);

// ============================================================ 5 30 工具部署清单·免疫原性类（20）— DEPLOY_TRACKER 表 B（两栏各 10）
s = pres.addSlide();
header(s, "工具部署清单 · 二", "免疫原性类共二十二种工具的部署状态");
const immL = [
  ["DeepImmuno","已部署","学术"],
  ["PredIG","已部署","学术"],
  ["IMPROVE","已部署·降级","学术"],
  ["NeoTImmuML","已部署·自训","学术"],
  ["pTuneos","已部署","学术"],
  ["PRIME","已部署","学术免费"],
  ["ImmuneApp","已部署","学术"],
  ["deepHLApan","已部署","学术"],
  ["BigMHC-IM","已部署","学术非商用"],
  ["CNNeo","已部署·自训","MIT"],
  ["IEDB-Calis","已部署","NPOSL-3.0"],
];
const immR = [
  ["Repitope","已部署","MIT"],
  ["T-SCAPE","已部署",{text:"学术非商用",color:C.warn}],
  ["ICERFIRE","已部署",{text:"DTU 学术许可",color:C.warn}],
  ["Seq2Neo","已部署","AFL-3.0"],
  ["NetTepi","已部署·低覆盖",{text:"DTU 学术许可",color:C.warn}],
  ["ImmugenX","已部署","学术许可"],
  ["MUNIS","已部署","CC-BY-4.0"],
  ["andy90","已部署","MIT"],
  ["DeepNetBim","已部署·低覆盖","待授权"],
  ["NeoaPred","已部署","学术"],
  ["NeoaG","已部署","学术"],
];
tbl(s, ["工具","部署状态","许可"], immL.map(r=>[{text:r[0],bold:true},r[1],r[2]]), [2.3, 1.9, 1.7], 0.5, 1.75, { rh:0.38, hh:0.42, bfs:10.5, hfs:11 });
tbl(s, ["工具","部署状态","许可"], immR.map(r=>[{text:r[0],bold:true},r[1],r[2]]), [2.3, 1.9, 1.7], 6.85, 1.75, { rh:0.38, hh:0.42, bfs:10.5, hfs:11 });
s.addText("免疫原性类工具直接预测肽段引发 T 细胞反应的强度。NeoTImmuML 与 CNNeo 因官方权重不可得采用自训版本，结果不与原论文对标；标注 DTU 学术许可的工具数字对外公布前需先取得书面同意。", { x:0.5, y:6.5, w:12.3, h:0.55, fontFace:FB, fontSize:11, color:C.muted, valign:"top", lineSpacingMultiple:1.15, margin:0 });
citeFoot(s, "工具部署总表 表 B（免疫原性组）· 官方一百三十肽口径");
pageno(s);

// ============================================================ 6 数据与评测口径
s = pres.addSlide();
header(s, "数据与评测口径", "主分析集 主副指标 与聚合方式");
tbl(s, ["口径项","具体设定"], [
  [{text:"主分析集",bold:true,align:"left"}, {text:"官方发布的一百三十条肽、九名患者，患者编号从 P101 到 P110，其中缺少 P103",align:"left"}],
  [{text:"序列口径",bold:true,align:"left"}, {text:"以九个氨基酸的肽段为主分析对象",align:"left"}],
  [{text:"主指标",bold:true,align:"left"}, {text:"Spearman 秩相关，衡量对候选肽精细排序的能力，正是临床挑选疫苗靶点最需要的",align:"left"}],
  [{text:"副指标",bold:true,align:"left"}, {text:"肽级 AUPRC，作为补充的功效指标",align:"left"}],
  [{text:"聚合方式",bold:true,align:"left"}, {text:"先对每位患者单独计算相关，再做 Fisher-z 变换等权合并，避免患者之间的信息泄漏",align:"left"}],
], [2.6, 9.3], 0.7, 1.9, { rh:0.86, hh:0.55, hfs:13, bfs:12.5 });
citeFoot(s, "官方一百三十肽队列（Braun 2025）· 主分析冻结表 pooled_clean_9mer.csv");
pageno(s);

// ============================================================ 7 §3.1 单工具 Spearman 主指标（fig1 ratio=9/15=0.60 大图+窄侧栏）
s = pres.addSlide();
header(s, "核心结果一 · 单工具主指标", "三十个工具的 Spearman 排序能力（覆盖修复后 effN≥8）");
placeImg(s, `${FIG4}/fig1_spearman_30tools_effN8.png`, 0.991, 0.5, 1.5, 7.6, 5.7);
proseCard(s, 8.3, 1.5, 4.3, 5.7, "主指标要点（Spearman 秩相关，effN≥8）", [
  "覆盖修复后八个工具补满一百三十肽，主榜从十五个扩到二十二个全覆盖工具，同患者集公平可比。",
  "顶部工具相关集中在零点三九到零点四五之间，没有单一压倒者：MHCnuggets 零点四四七、netMHCpan-BA 零点三九二、MHCflurry 零点三零八，且置信区间大幅重叠。",
  "MHCnuggets 补齐最难的一名患者后数值居首，netMHCpan-BA 仍作为结合亲和力的基准锚点。",
  "整体天花板相关不足零点四五，印证新抗原免疫原性预测仍是公认的难题。头条措辞待与袁老师确认。",
], C.teal);
citeFoot(s, "R1_recomputed_effN8.csv · per-patient Spearman（effN≥8，覆盖修复 remerge 后重算）");
pageno(s);

// ============================================================ 8 工具间相关性（fig_tool_corr_heatmap ratio=14/13.5=1.037 近方大图）
s = pres.addSlide();
header(s, "核心结果一 · 工具间相关性", "各工具预测得分之间的相关结构", C.teal);
placeImg(s, `${FIG4}/fig_tool_corr_heatmap.png`, 1.1044, 0.5, 1.5, 7.4, 5.7);
proseCard(s, 8.1, 1.5, 4.5, 5.7, "相关结构要点", [
  "亲和力与呈递类工具彼此之间高度相关，说明它们捕捉的是相近的信号，存在明显的预测冗余。",
  "这一类工具与部分免疫原性工具之间相关很低甚至为负，两者在信息上互补。",
  "这样的相关结构为下一步的问题提供了依据：多个工具融合起来，是否能够超越单个最强工具。",
], C.teal);
citeFoot(s, "工具间得分相关矩阵 · 官方一百三十肽口径");
pageno(s);

// ============================================================ 9 §3.2 池化算子重排（fig2 ratio=9/14=0.643 大图+窄侧栏）
s = pres.addSlide();
header(s, "核心结果二 · 子肽聚合", "不同工具最优的子肽聚合方式并不一致", C.teal);
placeImg(s, `${FIG4}/fig2_pooling_shuffle.png`, 0.6523, 0.5, 1.5, 7.6, 5.7);
proseCard(s, 8.3, 1.5, 4.3, 5.7, "子肽聚合规律", [
  "结合与亲和类工具依靠把一条肽切出的多个子肽窗口聚合起来，能够获得显著提升。以 netMHCpan-BA 为例，最大池化的相关为 0.43，改用前五个最强窗口的聚合后升至 0.52。",
  "免疫原性类工具则取单个最强窗口就已接近最优，继续聚合的收益有限。控制肽长之后，各聚合方式与最强窗口之间的中位差约为 0.05，落在噪声范围之内。",
  "换句话说，聚合方式不能一刀切，工具的类别决定了最优的池化策略。",
], C.teal);
citeFoot(s, "R2_pooling_sweep_official.csv · R2_best_per_tool.csv");
pageno(s);

// ============================================================ 10 §3.3 多工具融合 + 鲁棒性（fig3 ratio=14/7.5=1.867 宽扁, 画布不变）
s = pres.addSlide();
header(s, "核心结果三 · 多工具融合", "融合方法的紧簇表现与删突变鲁棒性", C.teal);
placeImg(s, `${FIG4}/fig3_robustness.png`, 1.8777, 0.7, 1.7, 7.35, 3.85);
proseCard(s, 8.25, 1.7, 4.38, 3.85, "融合与鲁棒性要点", [
  "在六工具子集的最强窗口维度下，十二种融合方法紧密聚成一簇，相关介于 0.33 到 0.39 之间，没有出现单一冠军。",
  "在删除百分之十与百分之二十突变的鲁棒性检验下，几何均值的夺冠胜率居前，分别为 0.40 与 0.47。",
], C.sea);
s.addText("这里的六工具子集，指从三十个工具中选出的六个组成一组用于融合分析。多种融合方法在秩指标下表现接近，几何均值在稳健性上略占优势，但整体差距不大。", { x:0.7, y:5.85, w:11.9, h:0.9, fontFace:FB, fontSize:12, color:C.muted, valign:"top", lineSpacingMultiple:1.15, margin:0 });
citeFoot(s, "R3_fusion_12methods_official.csv · R6 删突变鲁棒性");
pageno(s);

// ============================================================ 11 §3.3.3 无泄漏对比（文字 + 小表）
s = pres.addSlide();
header(s, "核心结果三 · 无泄漏对比", "整合方案与最强单工具在留一交叉验证下持平", C.teal);
tbl(s, ["对比项","排序能力","配对检验"], [
  [{text:"整合（六工具几何均值）",bold:true,align:"left"}, {text:"0.366",bold:true,fs:13}, {text:"裸口径 p 值为 0.46，控肽长后为 0.22，两者持平",align:"left"}],
  [{text:"最强单工具 MHCnuggets",bold:true,align:"left"}, {text:"0.447",bold:true,fs:13}, {text:"覆盖修复后升至全覆盖，成为最强单工具",align:"left"}],
], [4.3, 2.3, 5.3], 0.7, 2.0, { rh:1.05, hh:0.52, bfs:12.5 });
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:4.55, w:11.93, h:2.0, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:4.55, w:0.09, h:2.0, fill:{color:C.teal} });
s.addText([
  { text:"在无信息泄漏的留一患者交叉验证下，六工具几何均值的整合方案与最强单工具 MHCnuggets 之间，配对检验结果为持平（裸口径 p 值为 0.46），点估计上整合略逊于覆盖修复后的最强单工具。", options:{ breakLine:true, paraSpaceAfter:6 } },
  { text:"整合方案的价值不在于跑赢最强单工具，而在于当事先并不知道哪个工具最优时，它能给出稳健的、接近最优的输出。", options:{ breakLine:true, bold:true, color:C.teal } },
], { x:0.98, y:4.72, w:11.5, h:1.7, fontFace:FB, fontSize:12.5, color:C.ink, valign:"top", lineSpacingMultiple:1.22, margin:0 });
citeFoot(s, "R5 nested-LOPO · R7 显著性配对置换");
pageno(s);

// ============================================================ 12 §3.4 统一排名与部署（fig4 ratio=10/20=0.50 大图+窄侧栏, 40+行最挤）
s = pres.addSlide();
header(s, "核心结果三 · 统一排名与部署", "综合排名与两条务实可落地的部署路线", C.teal);
placeImg(s, `${FIG4}/fig4_unified_ranking.png`, 0.5015, 0.5, 1.5, 7.6, 5.7);
proseCard(s, 8.3, 1.5, 4.3, 5.7, "部署方案", [
  "务实默认方案是单一亲和力工具 netMHCpan-BA，采用取前二十个最强窗口的聚合，排序能力达到 0.461。它只依赖一个工具，最为稳定；该工具属于 DTU 学术许可。",
  "按需备选方案是多维度几何均值融合，排序能力为 0.366，适用于不确定哪个工具最优时的稳健选择。",
  "抗原呈递代理类工具因为覆盖稀疏、又存在肽长搭便车，不纳入部署候选。",
], C.sea);
citeFoot(s, "R8 部署评估 · R1 单工具基线");
pageno(s);

// ============================================================ 13 副指标·肽级 AUPRC —— 已移除（肽级 AUPRC 池化 130 肽忽略患者结构=pseudo-replication，PREREG_R10 定为 exploratory 不入 headline，2026-07-04 用户拍板删）

// ============================================================ 14 评价专章封面页（深底分隔）
s = pres.addSlide();
s.background = { color: C.dark };
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.mint} });
s.addShape(pres.shapes.OVAL, { x:-1.4, y:H-3.2, w:4.4, h:4.4, fill:{color:C.teal, transparency:80} });
s.addShape(pres.shapes.OVAL, { x:W-2.6, y:-1.4, w:3.4, h:3.4, fill:{color:C.sea, transparency:82} });
s.addText("方法学评价专章", { x:0.9, y:2.35, w:11, h:0.5, fontFace:FB, fontSize:16, color:C.mint, bold:true, charSpacing:3, margin:0 });
s.addText("如何评价跑出来的数据", { x:0.9, y:2.95, w:11.5, h:1.0, fontFace:FH, fontSize:40, bold:true, color:"FFFFFF", margin:0 });
s.addShape(pres.shapes.LINE, { x:0.95, y:4.15, w:3.2, h:0, line:{color:C.mint, width:2} });
s.addText("数据本身没有错，但要读得对。这一章系统说明三个评价要点：肽长混杂、计数混杂、融合方法数学近亲，并给出各自的处理方式与当前状态。", { x:0.95, y:4.45, w:10.8, h:1.0, fontFace:FB, fontSize:14, color:"E6F2F2", valign:"top", lineSpacingMultiple:1.25, margin:0 });

// ============================================================ 15 评价陷阱总览（高级表格 四行）
s = pres.addSlide();
header(s, "方法学评价", "三个评价要点及其处理", C.sea);
tbl(s, ["评价要点","具体表现","处理方式","当前状态"], [
  [{text:"肽长混杂",bold:true,align:"left"}, {text:"长肽会切出更多窗口，最强窗口容易随机偏高",align:"left"}, {text:"裸口径与控肽长两列并排报告",align:"left"}, {text:"待周五讨论",color:C.warn,bold:true}],
  [{text:"计数混杂",bold:true,align:"left"}, {text:"一条肽切出的子肽数量本身就与反应弱相关",align:"left"}, {text:"排除计数型的池化方式",align:"left"}, {text:"已修正",color:C.ok,bold:true}],
  [{text:"融合方法数学近亲",bold:true,align:"left"}, {text:"在秩指标下，几何均值与算术秩均值几乎等价",align:"left"}, {text:"用三重检验刻画其差异",align:"left"}, {text:"已有定论",color:C.ok,bold:true}],
], [2.6, 4.0, 3.1, 2.2], 0.7, 1.95, { rh:0.92, hh:0.52, bfs:11.5 });
s.addText("三个要点里两个已经处理定论，只剩肽长是否应作为混杂加以控制这一处，留到周五与老师当面讨论。", { x:0.7, y:6.0, w:11.9, h:0.7, fontFace:FB, fontSize:12, color:C.muted, valign:"top", lineSpacingMultiple:1.15, margin:0 });
citeFoot(s, "方法学评价工具 · S2_regime_compare.csv");
pageno(s);

// ============================================================ 16 评价·问题二 第一页（heatmap 1.139 + cluster 1.141）
s = pres.addSlide();
header(s, "方法学评价 · 融合方法数学近亲", "几何均值与算术均值秩融合的排序高度一致", C.sea);
placeImg(s, `${FIG4}/q2_rank_corr_heatmap.png`, 1.139, 0.7, 1.65, 5.9, 3.75);
placeImg(s, `${FIG4}/q2_pointest_cluster.png`, 1.141, 6.85, 1.65, 5.78, 3.75);
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:5.55, w:11.93, h:1.4, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:5.55, w:0.09, h:1.4, fill:{color:C.sea} });
s.addText([
  { text:"左图把几种融合方法在同一批肽上的排序两两求相关，几何均值与算术均值秩融合的排序相关高达 0.95（患者内）与 0.97（合并），几乎完全一致。", options:{ breakLine:true, paraSpaceAfter:5 } },
  { text:"右图显示三种融合方法的点估计紧紧聚成一簇，几何均值、算术均值秩、中位数分别为 0.366、0.348 与 0.252，患者层的配对检验 p 值为 0.54，差异并不显著。", options:{ breakLine:true } },
], { x:0.98, y:5.68, w:11.5, h:1.2, fontFace:FB, fontSize:12, color:C.ink, valign:"top", lineSpacingMultiple:1.18, margin:0 });
citeFoot(s, "R3_fusion_12methods_official.csv · 融合方法排序相关与点估计");
pageno(s);

// ============================================================ 17 评价·问题二 第二页 —— 已移除（q2_auprc_kinship + q2_taylor_scatter 均肽级 AUPRC 副指标，同 pseudo-replication 问题；geomean≈mean_rank 结论 slide 16 已用 Spearman 版给出，2026-07-04 用户拍板删）

// ============================================================ 18 评价·问题一（只讲现象不下结论，len 1.381）
s = pres.addSlide();
header(s, "方法学评价 · 肽长混杂", "控制肽长前后各类工具的表现变化", C.warn);
placeImg(s, `${FIG4}/len_confound_bare_vs_ctrl.png`, 1.381, 0.7, 1.7, 6.7, 5.25);
proseCard(s, 7.6, 1.7, 5.03, 5.25, "现象描述", [
  "这张图并排比较了控制肽长之前与之后各工具的表现。",
  "控制肽长之后，抗原呈递代理类工具的相关明显回落，以 HLAthena 为例，从 0.63 降至 0.25。",
  "而结合亲和力类工具基本不受影响，甚至略有上升，netMHCpan-BA 从 0.39 变为 0.43。",
  "此处只陈述观察到的现象，不对处理方式下判断。肽长是否应作为混杂加以控制，留待进一步讨论。",
], C.warn);
citeFoot(s, "R1_single_maxpool_official.csv · 裸口径与控肽长对照");
pageno(s);

// ============================================================ 19 局限与下一步
s = pres.addSlide();
header(s, "局限与下一步", "当前限制与周五要讨论的问题");
proseCard(s, 0.7, 1.7, 5.9, 5.25, "主要局限", [
  "患者数量有限，仅九名，细粒度的方法差异统计上难以分开。",
  "多工具整合方案与最强单工具在统计上持平，并没有真正超越。",
  "肽长与插入缺失这两类混杂尚待进一步讨论。",
  "几何均值虽可作稳健默认，但并非唯一最优。",
  "小鼠数据两套目前都还缺失，正在收集。",
], C.warn);
proseCard(s, 6.85, 1.7, 5.78, 5.25, "下一步计划", [
  "周五与老师当面讨论两个问题：肽长是否作为混杂加以控制，以及融合方法的措辞如何拿捏。",
  "继续收集并接入两套小鼠数据，补齐人鼠对照。",
  "补齐三十个工具完整的版本与代码提交清单，供投稿前核验。",
], C.sea);
citeFoot(s, "方法学评价专章 · 项目进度追踪（2026-07-01）");
pageno(s);

pres.writeFile({ fileName:"D:/YJ-Agent/project/meeting/QuantImmuBench/QuantImmuBench_progress_v4_rev6_2026-07-04.pptx" }).then(f=>console.log("WROTE", f, "pages", _PG));
