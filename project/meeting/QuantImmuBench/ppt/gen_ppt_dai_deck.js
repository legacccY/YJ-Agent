// QuantImmuBench — §3.1 单工具新抗原免疫原性预测评测 · 给导师看的结果 deck（含 DAI，7 页）
// 目标读者 = 导师：全程说人话，不用行话/内部黑话/自创词；每张图讲清「用了什么方法 + 限定什么范围」。
// 样式引擎照抄 gen_ppt_rerun_9mer.js 的 helper（header/pageno/proseCard/citeFoot/placeImg），
//   配色 Okabe-Ito（#0072B2 蓝 / #E69F00 橙 / #009E73 绿），Microsoft YaHei 中文字体，LAYOUT_WIDE。
//   图片按真实宽高比 contain 不拉伸（ratio = 宽/高，主线静态量得，见 IMG 注释）。
// 数字全部逐字采用主线 Bash 已核实值（见任务单），零自造零硬凑。
// 运行(主线跑，本脚本作者不跑): NODE_PATH=C:/Users/yj200/AppData/Roaming/npm/node_modules node ppt/gen_ppt_dai_deck.js
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "QuantImmuBench §3.1 单工具新抗原免疫原性预测评测（含 DAI）";

const W = 13.33, H = 7.5;
// Okabe-Ito 配色，沿用 rerun_9mer deck
const C = {
  dark:"0B3C49", teal:"0072B2", blue:"0072B2", orange:"E69F00", green:"009E73",
  light:"F2F7F7", card:"FFFFFF", ink:"16323A", muted:"5E7B83",
  line:"D5E3E4", warn:"E69F00", ok:"009E73", crit:"B23A48", gray:"8A9BA0",
};
const FH = "Microsoft YaHei", FB = "Microsoft YaHei", FM = "Consolas";
const sh = () => ({ type:"outer", color:"0B3C49", blur:9, offset:3, angle:135, opacity:0.12 });

// 3 张图（存在性已由主线 Bash 确认），ratio = 宽/高（主线静态量得）
const IMG = {
  rank:     { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/official/recompute_effN/figures/fig_rerun_9mer_maxpool_ranking.png",           r:0.8696 },
  dai:      { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/official/recompute_effN/figures/fig_rerun_9mer_dai_ranking.png",               r:0.8955 },
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
    if(dm) opt={ color:"1C7293", fontSize:9, hyperlink:{ url:"https://doi.org/"+dm[1], tooltip:"DOI" } };
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

// ============================================================ 1 封面（深底）
let s = pres.addSlide();
s.background = { color: C.dark };
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.green} });
s.addShape(pres.shapes.OVAL, { x:W-3.3, y:-1.6, w:4.6, h:4.6, fill:{color:C.blue, transparency:78} });
s.addShape(pres.shapes.OVAL, { x:W-2.0, y:3.6,  w:3.2, h:3.2, fill:{color:C.green, transparency:82} });
s.addText("癌症个性化新抗原疫苗 · 免疫原性预测工具评测", { x:0.9, y:1.3, w:11.5, h:0.4, fontFace:FB, fontSize:15, color:C.green, bold:true, charSpacing:2, margin:0 });
s.addText("单工具新抗原免疫原性预测评测", { x:0.9, y:1.95, w:11.7, h:1.0, fontFace:FH, fontSize:34, bold:true, color:"FFFFFF", lineSpacingMultiple:1.06, margin:0 });
s.addShape(pres.shapes.LINE, { x:0.95, y:3.2, w:3.2, h:0, line:{color:C.green, width:2} });
s.addText([
  { text:"原始蛋白定点切肽 · 突变肽（MT）与野生型（WT）双口径", options:{ breakLine:true, paraSpaceAfter:8 } },
  { text:"Braun 2025 肾癌疫苗 ELISpot 数据", options:{ breakLine:true, paraSpaceAfter:8 } },
  { text:"2026-07-08", options:{ breakLine:true, bold:true, color:"CFE7F5" } },
], { x:0.95, y:3.6, w:11.5, h:2.4, fontFace:FB, fontSize:17, color:"E6F2F2", valign:"top", lineSpacingMultiple:1.28, margin:0 });

// ============================================================ 2 数据、切肽方式与评测指标（单卡）
s = pres.addSlide();
header(s, "背景与方法", "数据、切肽方式与评测指标", C.blue);
proseCard(s, 0.7, 1.6, 11.92, 5.35, "这项评测怎么做的（逐条说明）", [
  "数据：Braun 等 2025 年发表于《Nature》的肾癌新抗原疫苗试验；9 位患者；用 ELISpot 实验实测每条突变肽的 T 细胞反应强度，作为评测的真值。",
  "肽的范围：102 条点突变（SNV）肽。移码和插入/缺失突变（共 28 条）已排除，因为它们没有对应的正常（野生型）序列，无法计算差异。",
  "怎么切肽：围绕每个突变位点，从蛋白序列上截取长度为 9 的短肽，每条突变固定截出 9 个窗口。这样每条突变的候选肽数量一致，避免“疫苗肽越长、候选越多”带来的偏差。",
  "打分与汇总：每个工具对“短肽–HLA”打分，取该突变所有窗口里的最高分代表这条突变。",
  "评测指标：在每位患者内部，计算工具打分与 ELISpot 实验值的 Spearman 秩相关（衡量排序是否一致）；要求该患者至少有 8 条肽同时具备打分和实验值才纳入；再把各患者的相关系数等权平均。相关系数越接近 1，说明工具越能把实验上更强的突变排在前面。",
], C.blue);
citeFoot(s, "R1_recomputed_rerun_9mer_effN8.csv · Braun et al. 2025, Nature（肾癌新抗原疫苗试验，ELISpot 真值）");
pageno(s);

// ============================================================ 3 单工具主排名（左图 + 右卡）
s = pres.addSlide();
header(s, "核心结果 · 主排名", "单工具排名：谁最能预测免疫原性", C.blue);
placeImg(s, IMG.rank.p, IMG.rank.r, 0.5, 1.5, 5.6, 5.7);
proseCard(s, 6.35, 1.5, 6.28, 5.7, "怎么读这张图", [
  "方法：用每个工具对突变肽的原始打分来排序，指标见上一页。",
  "范围：102 条 SNV 肽、9 位患者、9mer 短肽。",
  "结果：netMHCpan_BA 排第一（相关 0.372）；排在前面的基本是结合/呈递类工具（如 MHCnuggets、MHCflurry）；免疫原性专用工具多数靠后。28 个工具的平均相关约 0.11。",
  "两点说明：",
  "① 平均值 0.11 绝对不高，是因为 T 细胞免疫原性本身极难预测，文献里同类单指标的水平也是这个量级。",
  "② DeepNetBim 打分全部相同、无法排序，NeoaPred 已从工具集去除，这两个不计入。",
], C.blue);
citeFoot(s, "R1_recomputed_rerun_9mer_effN8.csv · 用突变肽原始打分排序 · 102 SNV 肽 / 9 患者 / 9mer");
pageno(s);

// ============================================================ 4 什么是 DAI（单卡）
s = pres.addSlide();
header(s, "概念说明 · DAI", "什么是 DAI（差异指数），为什么要用野生型", C.green);
proseCard(s, 0.7, 1.6, 11.92, 5.35, "差异指数 DAI 的想法与定义", [
  "出发点：新抗原能被免疫系统识别，部分原因是它和正常（野生型）序列不同。于是有一种思路：不看突变肽的绝对分，而看“突变肽比它对应的野生型强多少”。",
  "定义：DAI = 突变肽得分 − 野生型得分（差为负时记为 0）。这个差越大，代表突变让这条肽比原来更容易被呈递或识别。",
  "这正是野生型（WT）数据的用处：只有同时给突变肽和野生型肽都打分，才能算出这个差。",
  "来源：由 Duan 等人在 2014 年提出。",
], C.green);
citeFoot(s, "R1_recomputed_rerun_9mer_dai_effN8.csv · DAI 概念：Duan et al. 2014");
pageno(s);

// ============================================================ 5 DAI 排名（左图 + 右卡）
s = pres.addSlide();
header(s, "核心结果 · DAI", "差异指数 DAI 能预测免疫原性吗", C.green);
placeImg(s, IMG.dai.p, IMG.dai.r, 0.5, 1.5, 5.6, 5.7);
proseCard(s, 6.35, 1.5, 6.28, 5.7, "怎么读这张图", [
  "方法：把每个工具的打分换成 DAI（突变分 − 野生型分），其余算法与前面相同。25 个工具能算 DAI；另有 4 个工具只输出一个综合分、无法单独给野生型打分，不计入。",
  "三个关键数字的含义：",
  "· 平均 0.007（几乎为零）：DAI 平均而言几乎没有预测能力，接近随机。",
  "· 最高 0.344（PredIG）：即便表现最好的 DAI，也没有超过用原始突变肽分时的最高值（0.372）。",
  "· 最低 −0.316；且 25 个工具正负几乎各半，其中只有 3 个的置信区间不包含 0。这说明大多数结果与“零相关”无法区分，正负主要是小样本的随机波动，不是真的反向预测。",
  "结论：在这批数据上，“看突变与野生型的差异”并没有比“直接看突变肽的分”带来提升。",
], C.green);
citeFoot(s, "R1_recomputed_rerun_9mer_dai_effN8.csv · 用 DAI（突变分−野生型分）排序 · 25 工具可算");
pageno(s);

// ============================================================ 6 为什么本版平均分比旧版低（左图 dumbbell + 右卡）
s = pres.addSlide();
header(s, "口径说明", "为什么本版平均分比旧版低", C.orange);
placeImg(s, IMG.dumbbell.p, IMG.dumbbell.r, 0.5, 1.5, 5.6, 5.7);
proseCard(s, 6.35, 1.5, 6.28, 5.7, "两个原因，各约一半", [
  "旧版（按疫苗肽切、130 条肽）平均相关 0.191；本版（按蛋白定点切、102 条 SNV）平均 0.113。",
  "下降来自两件事，各约一半：",
  "· 只保留点突变：去掉了 28 条移码/插入缺失肽，而这些恰好是实验反应偏强的肽，任务因此更难（约 −0.04）。",
  "· 换了切肽方式：旧切法下疫苗肽越长、候选肽越多，最高分容易偏高；新切法固定每条突变 9 个窗口，去掉了这个偏差（约 −0.03）。",
  "两者都不是出错，而是更严格、更干净口径下的真实水平。",
], C.orange);
citeFoot(s, "R1_recomputed_rerun_9mer_effN8.csv · 新切 9mer vs 旧疫苗肽切逐工具对照");
pageno(s);

// ============================================================ 7 结论与局限（三小段短标题）
s = pres.addSlide();
header(s, "小结", "结论与局限", C.blue);
proseCard(s, 0.7, 1.6, 3.84, 5.35, "结论", [
  "① 结合/呈递类工具对突变肽的原始打分，是最强的单指标排序输入（netMHCpan_BA 居首）。",
  "② 差异指数 DAI（用上野生型）在这批数据上几乎没有预测力，也没有比原始打分更好。",
], C.blue);
proseCard(s, 4.74, 1.6, 3.84, 5.35, "局限", [
  "① 仅 9 位患者、单一队列，结论属初步观察，不宜外推为普适排名。",
  "② 仅点突变（SNV），移码/插入缺失未纳入。",
  "③ 仅 9mer，8–11 可变窗长尚未做。",
], C.orange);
proseCard(s, 8.78, 1.6, 3.84, 5.35, "与文献一致", [
  "IMPROVE（2024）报告 DAI 区分免疫原性 p=0.96（接近随机）；",
  "TESLA（2020）报告只看差异、不看呈递反而更差；",
  "同类单指标的判别力（AUC）普遍在 0.52–0.60。",
  "本结果与这些文献一致。",
], C.green);
citeFoot(s, "R1_recomputed_rerun_9mer_effN8.csv + R1_recomputed_rerun_9mer_dai_effN8.csv · 文献：IMPROVE 2024 / TESLA 2020");
pageno(s);

pres.writeFile({ fileName:"D:/YJ-Agent/project/meeting/QuantImmuBench/QuantImmuBench_单工具评测_DAI_2026-07-08.pptx" }).then(f=>console.log("WROTE", f, "pages", _PG));
