// QuantImmuBench — §3.1 单工具 max-pooling 排序 · 9mer 新切肽口径（改动②③重跑复刻，5 页）
// 用 2026-07-08 改动②③全量重跑（29 工具）数复刻上一版单工具 max-pooling Spearman 排序 deck，
//   新切肽口径 = 原始蛋白定点切含突变窗（SLP 锚定 + MANE 补），窗长 9mer；聚合口径完全复刻上一版：
//   per-patient Spearman → effN≥8 门槛 → clip±0.99 → Fisher-Z 病人等权均值 → tanh；CI = cluster-bootstrap over patients 95%。
// 样式引擎照抄 gen_ppt_benchmark_results.js / gen_ppt_progress_v4.js 的 helper（header/placeImg/citeFoot/proseCard/tbl），
//   配色 Okabe-Ito（#0072B2 蓝 / #E69F00 橙 / #009E73 绿），Microsoft YaHei 中文字体，LAYOUT_WIDE。
// 图片按真实宽高比 contain 不拉伸（ratio = 宽/高，已由主线静态量得，见 IMG 注释）。
// 数字全部逐字采用主线 Bash 已核实值，零自造零硬凑；图只引 2 个已确认存在的绝对路径 png。
// 运行(主线跑，本脚本作者不跑): NODE_PATH=C:/Users/yj200/AppData/Roaming/npm/node_modules node ppt/gen_ppt_rerun_9mer.js
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "QuantImmuBench §3.1 单工具 max-pooling 排序 — 9mer 新切肽口径（改动②③重跑复刻）";

const W = 13.33, H = 7.5;
// Okabe-Ito 配色（teal 别名 = Okabe 蓝，供 citeFoot 标签色复用），沿用 benchmark deck
const C = {
  dark:"0B3C49", teal:"0072B2", blue:"0072B2", orange:"E69F00", green:"009E73",
  light:"F2F7F7", card:"FFFFFF", ink:"16323A", muted:"5E7B83",
  line:"D5E3E4", warn:"E69F00", ok:"009E73", crit:"B23A48", gray:"8A9BA0",
};
const FH = "Microsoft YaHei", FB = "Microsoft YaHei", FM = "Consolas";
const sh = () => ({ type:"outer", color:"0B3C49", blur:9, offset:3, angle:135, opacity:0.12 });

// 2 张图（存在性已由主线 Bash 确认），ratio = 宽/高（主线静态量得）
const IMG = {
  rank:     { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/official/recompute_effN/figures/fig_rerun_9mer_maxpool_ranking.png",           r:0.8696 },
  dumbbell: { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/official/recompute_effN/figures/fig_rerun_9mer_newcut_vs_oldSLP_dumbbell.png", r:0.9106 },
};

let _PG = 1;
function header(slide, kicker, title, accent=C.blue){
  slide.background = { color: C.light };
  slide.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:0.28, h:H, fill:{color:accent} });
  slide.addText(kicker.toUpperCase(), { x:0.7, y:0.42, w:11, h:0.3, fontFace:FB, fontSize:12, color:accent, bold:true, charSpacing:3, margin:0 });
  slide.addText(title, { x:0.7, y:0.72, w:12.2, h:0.7, fontFace:FH, fontSize:22, color:C.ink, bold:true, margin:0 });
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

// ============================================================ 1 封面
let s = pres.addSlide();
s.background = { color: C.dark };
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.green} });
s.addShape(pres.shapes.OVAL, { x:W-3.3, y:-1.6, w:4.6, h:4.6, fill:{color:C.blue, transparency:78} });
s.addShape(pres.shapes.OVAL, { x:W-2.0, y:3.6,  w:3.2, h:3.2, fill:{color:C.green, transparency:82} });
s.addText("癌症个性化新抗原疫苗 · 免疫原性工具系统评测", { x:0.9, y:1.3, w:11.5, h:0.4, fontFace:FB, fontSize:15, color:C.green, bold:true, charSpacing:2, margin:0 });
s.addText("QuantImmuBench §3.1 单工具 max-pooling 排序\n—— 9mer 新切肽口径（改动②③重跑复刻）", { x:0.9, y:1.9, w:11.7, h:1.9, fontFace:FH, fontSize:30, bold:true, color:"FFFFFF", lineSpacingMultiple:1.06, margin:0 });
s.addShape(pres.shapes.LINE, { x:0.95, y:4.4, w:3.2, h:0, line:{color:C.green, width:2} });
s.addText([
  { text:"数据 2026-07-08 改动②③全量重跑（29 工具）· 官方 DS2 · 102 SNV 肽 · 9 患者（P101/102/104/105/106/107/108/109/110）", options:{ breakLine:true, paraSpaceAfter:6 } },
  { text:"聚合口径 = per-patient Spearman → effN≥8 门槛 → clip±0.99 → Fisher-Z 病人等权均值 → tanh；CI = cluster-bootstrap over patients 95%", options:{ breakLine:true, paraSpaceAfter:6 } },
  { text:"切肽口径 = 原始蛋白定点切含突变窗（SLP 锚定 + MANE 补），窗长 9mer；聚合算子 = max-pooling", options:{ breakLine:true, bold:true, color:"CFE7F5" } },
], { x:0.95, y:4.7, w:11.5, h:1.9, fontFace:FB, fontSize:14, color:"E6F2F2", valign:"top", lineSpacingMultiple:1.25, margin:0 });
s.addText("2026-07-08", { x:W-2.4, y:6.8, w:1.8, h:0.3, fontFace:FB, fontSize:12, color:"8FB7BD", align:"right", margin:0 });

// ============================================================ 2 一页看懂（文字页 · 三卡）
s = pres.addSlide();
header(s, "一页看懂", "改动②③是什么，这版复刻了上一版哪种口径", C.blue);
proseCard(s, 0.7, 1.6, 3.84, 5.35, "改动②③ 做了什么", [
  "改动② = 切肽方式改成从原始蛋白上定点切「含突变的窗口」（SLP 锚定，缺失处用 MANE 参考序列补齐），把每条肽切出的子肽袋子固定成恒定的 9 个。",
  "袋子恒定 → 从特征侧消除肽长混杂：窗数与 SLP 肽长的相关从 0.463 掉到 −0.097，工具分数不再靠「长肽切更多窗、最大值偏高」搭便车。",
  "改动③ = 补齐野生型 WT 对照序列，已就绪但本版未跑（见第 5 页遗留）。",
], C.blue);
proseCard(s, 4.74, 1.6, 3.84, 5.35, "复刻上一版的哪种口径", [
  "本版严格复刻上一版单工具 max-pooling Spearman 排序 deck 的聚合口径，只换切肽方式：",
  "每位患者单独算 Spearman（per-patient）→ 有效样本数 effN≥8 才计入 → 相关值 clip 到 ±0.99 → Fisher-Z 变换后病人等权求均值 → tanh 反变换。",
  "置信区间 = 对患者做 cluster-bootstrap 的 95% 区间。聚合算子固定为 max-pooling（每条肽取其子肽窗口的最大分）。",
], C.green);
proseCard(s, 8.78, 1.6, 3.84, 5.35, "与旧版数字口径差异（勿直接比）", [
  "旧版排序基于 130 肽、且工具集含 NeoaPred；本版基于 102 SNV 肽、NeoaPred 已从工具集剔除（30→29）。",
  "肽集不同、工具集不同，两版的绝对数值不可直接对比，只能看趋势与排序结构。",
  "本版绝对量级低于旧 SLP 版，是「去肽长混杂 + 只保留 SNV」后的诚实结果，不是 bug。",
], C.orange);
citeFoot(s, "R1_recomputed_rerun_9mer_effN8.csv · 改动②③全量重跑（2026-07-08，29 工具）");
pageno(s);

// ============================================================ 3 主排名图页（rank ratio=0.8696，竖高图）
s = pres.addSlide();
header(s, "核心结果 · §3.1 单工具主指标", "单工具 max-pooling Spearman 排序 · 9mer 新切肽（effN≥8，8/9 病人进聚合）", C.blue);
placeImg(s, IMG.rank.p, IMG.rank.r, 0.5, 1.5, 5.5, 5.7);
proseCard(s, 6.25, 1.5, 6.35, 5.7, "主排名要点（ρ̄ = Fisher-Z 病人等权均值）", [
  "头部前六：netMHCpan_BA 0.372 > MHCnuggets 0.319 > PredIG 0.290 > ICERFIRE 0.234 > MHCseqNet 0.228 > MHCflurry 0.214。",
  "紧随其后：PRIME 0.181、MUNIS 0.180、BigMHC_IM 0.178、deepHLApan 0.174、netMHCpan_EL 0.169。",
  "尾部（负相关）：andy90 −0.001、netMHCstabpan −0.033、ImmuneApp −0.044、NeoaG −0.048、CNNeo −0.058、Seq2Neo −0.075、TSCAPE −0.099。",
  "28 个有效工具的均值 ρ̄ = 0.113。",
  "N/A（不入排序）：DeepNetBim（max 池化下饱和成常数、退化）、NeoaPred（已从工具集剔除）。",
  "可比性已核：28 工具全平均在同一 8 病人（102 因肽<8 剔）、每病人排同一批 102 肽（肽级覆盖全 100%，无覆盖子集虚高）、定向统一——苹果对苹果。",
], C.blue);
citeFoot(s, "R1_recomputed_rerun_9mer_effN8.csv · per-patient Spearman（9mer 新切，effN≥8，8/9 病人进聚合）");
pageno(s);

// ============================================================ 4 新切 vs 旧 SLP 哑铃页（dumbbell ratio=0.9106）
s = pres.addSlide();
header(s, "口径对照 · 新切 vs 旧 SLP", "9mer 新切肽口径 vs 旧 SLP 9mer · 逐工具哑铃对比", C.orange);
placeImg(s, IMG.dumbbell.p, IMG.dumbbell.r, 0.5, 1.5, 5.5, 5.7);
proseCard(s, 6.25, 1.5, 6.35, 5.7, "对照要点", [
  "去掉肽长混杂后整体排序能力下降：28 个有效工具均值从旧 SLP 的 0.191 降到新切的 0.113。",
  "逐工具方向：26/28 下降，仅 2 个上升（PredIG、deepHLApan）。",
  "降幅最大者（当初最吃肽长混杂）：MHCnuggets 0.447→0.319、netMHCstabpan 0.234→−0.033、NetTepi 0.293→0.093、IMPROVE 0.285→0.146、ImmuneApp 0.179→−0.044。",
  "结论：越是靠「长肽多窗、最大值偏高」拿高分的工具，去混杂后掉得越狠。",
  "⚠ caveat：新切基于 102 SNV 肽、旧版基于 130 肽，肽集不同，本页仅作趋势示意，不作绝对数值对标。",
], C.orange);
citeFoot(s, "R1_recomputed_rerun_9mer_effN8.csv · 新切 9mer vs 旧 SLP 9mer 逐工具 ρ̄ 对照");
pageno(s);

// ============================================================ 5 掉分归因分解页（表 + 解读卡）
s = pres.addSlide();
header(s, "掉分归因 · 分解实验", "为什么从旧 0.191 掉到新 0.113 —— 一半是砍 indel，一半才是去混杂", C.orange);
// 三情景分解表（同 effN8 Fisher-Z 口径，逐值 Bash 核；加性 A−C=−0.078）
const _th = { fill:{color:"0B3C49"}, color:"FFFFFF", bold:true, fontFace:FH, fontSize:12, align:"center", valign:"middle" };
const _td = { fontFace:FB, fontSize:12, color:C.ink, align:"center", valign:"middle", fill:{color:"FFFFFF"} };
const _tdl = Object.assign({}, _td, { align:"left" });
const rows = [
  [ {text:"情景", options:_th}, {text:"肽集 / 切法", options:_th}, {text:"均值 ρ̄", options:_th}, {text:"vs 上一步", options:_th} ],
  [ {text:"A 旧 SLP", options:_tdl}, {text:"130 肽 · SLP 切", options:_tdl}, {text:"0.191", options:Object.assign({},_td,{bold:true})}, {text:"—", options:_td} ],
  [ {text:"B 旧 SLP", options:_tdl}, {text:"仅 102 SNV · SLP 切（只砍 28 indel）", options:_tdl}, {text:"0.147", options:Object.assign({},_td,{bold:true})}, {text:"−0.044", options:Object.assign({},_td,{color:"B23A48",bold:true})} ],
  [ {text:"C 新切", options:_tdl}, {text:"102 SNV · 蛋白定点切（只换切法）", options:_tdl}, {text:"0.113", options:Object.assign({},_td,{bold:true})}, {text:"−0.034", options:Object.assign({},_td,{color:"B23A48",bold:true})} ],
];
s.addTable(rows, { x:0.7, y:1.75, w:7.3, colW:[1.3,3.7,1.1,1.2], rowH:[0.5,0.62,0.78,0.78], border:{type:"solid",color:C.line,pt:1}, valign:"middle" });
s.addText([
  { text:"总掉 −0.078  =  ", options:{ color:C.ink, fontSize:14, bold:true } },
  { text:"砍 28 高应答 indel 肽 −0.044（56%）", options:{ color:"B23A48", fontSize:14, bold:true } },
  { text:"  +  ", options:{ color:C.ink, fontSize:14, bold:true } },
  { text:"去肽长混杂 −0.034（44%）", options:{ color:C.orange, fontSize:14, bold:true } },
], { x:0.7, y:4.35, w:7.3, h:0.6, fontFace:FB, align:"center", valign:"middle", fill:{color:"F2F7F7"}, line:{color:C.line,width:1}, margin:0 });
proseCard(s, 8.3, 1.75, 4.3, 4.6, "怎么读这张分解", [
  "① 砍 28 条 indel/移码肽（占一半多）：只做 SNV → 130 肽变 102。那 28 条恰是高应答肽（ELISpot 中位更高、VHL 移码=392），好排的肽被拿走，任务本身更难；附带病人 102（SNV 仅 6 肽<effN8）也掉出聚合。",
  "② 去肽长混杂（占差不多另一半）：改动②袋子恒定=9，挤掉「长肽多窗、max 偏高」的虚高。吃这口最狠者掉最惨：netMHCstabpan 0.234→0.134→−0.033、NetTepi 0.293→0.161→0.093。",
  "反直觉：非全掉——netMHCpan_BA 砍 indel 后反升 0.392→0.454、deepHLApan 两步都升 0.052→0.174，本被噪声压低、去掉才显真本事。",
  "结论：0.113 是更干净、更难 benchmark（仅 SNV + 无肽长虚高）上的诚实水平，两个原因都非 bug。",
], C.orange);
citeFoot(s, "分解实验 _scratch/decompose.py · 三情景同 effN8 Fisher-Z 口径 · pooled_clean_9mer.csv(旧) + pooled_clean_rerun_9mer.csv(新)");
pageno(s);

// ============================================================ 6 结论 + 诚实边界页（文字 · 三卡）
s = pres.addSlide();
header(s, "结论与诚实边界", "核心结论、遗留事项、数据完整性", C.green);
proseCard(s, 0.7, 1.6, 3.84, 5.35, "核心结论", [
  "netMHCpan_BA 领跑，结合 / 呈递类工具整体居前，印证 claim i：结合类工具排序能力不弱于免疫原性专用工具。",
  "绝对量级低于旧 SLP 版，是「去肽长混杂 + 只保留 SNV」后的诚实结果，不是 bug 也不是退步。",
  "越吃肽长混杂的工具去混杂后掉得越狠（见第 4 页哑铃），说明旧版部分高分来自可疑的肽长搭便车。",
], C.green);
proseCard(s, 4.74, 1.6, 3.84, 5.35, "遗留事项（勿预焊胜利）", [
  "DeepNetBim 在 max 池化下饱和成常数、退化，本版列 N/A，未纳入排序。",
  "DAI 相关的改动③（补 WT 对照）已就绪但本版未跑，结果未知，不预先宣称胜利。",
  "8-11mer 可变窗的新切口径本版未做，留待以后补。",
], C.orange);
proseCard(s, 8.78, 1.6, 3.84, 5.35, "数据完整性", [
  "29 个工具全部齐整：共 4053 行打分数据完整。",
  "覆盖缺口仅 NeoTImmuML 的 1 条肽 ×5 个 HLA，属极小残缺，不影响主排名。",
  "NeoaPred 已从工具集剔除（30→29），本版排序不含它。",
], C.blue);
citeFoot(s, "R1_recomputed_rerun_9mer_effN8.csv · 改动②③全量重跑（2026-07-08，29 工具，4053 行）");
pageno(s);

pres.writeFile({ fileName:"D:/YJ-Agent/project/meeting/QuantImmuBench/QuantImmuBench_9mer新切排名_2026-07-08.pptx" }).then(f=>console.log("WROTE", f, "pages", _PG));
