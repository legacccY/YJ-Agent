// QuantImmuBench — 第一批 5 工具横评报告 v3（Spearman 头条 · 人话文案 · 图不拉伸 · 来源超链接）
// 范围：DeepImmuno / PredIG / pTuneos / IMPROVE / NeoTImmuML
// 版式照已批准的 ppt/gen_ppt_newtools_v3.js：figSlide 按真实宽高比 contain 放置、citeFoot/文献矩阵 DOI 与 repo 超链接、proseCard 完整中文句、结论页浅底深字
// 2026-06-28 更新：IMPROVE Phase B 重推理跑通（n_pep 86→101），触发 14/14 工具全量重算，本批 5 工具的 Spearman / AUC / per-patient fisherz 全部刷新
// 数字均经 analysis/metrics_ds2_16tools.csv + analysis/per_patient_spearman_16tools.csv 核对；2026-06-28 口径统一：主指标改为患者内 Fisher-Z（与项目主表一致），全局 max Spearman 降为对照，逐字照搬不自算
// 运行: NODE_PATH=C:/Users/yj200/AppData/Roaming/npm/node_modules node ppt/gen_ppt_5tools.js
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "新抗原免疫原性预测工具 — 第一批 5 工具横评报告";

const W = 13.33, H = 7.5;
const C = {
  dark:"0B3C49", teal:"028090", sea:"00A896", mint:"02C39A",
  light:"F2F7F7", card:"FFFFFF", ink:"16323A", muted:"5E7B83",
  line:"D5E3E4", warn:"C9743D", ok:"00A896", crit:"B23A48", gray:"8A9BA0",
};
const FH = "Microsoft YaHei", FB = "Microsoft YaHei", FM = "Consolas";
const FIG = "D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/figures";
const sh = () => ({ type:"outer", color:"0B3C49", blur:9, offset:3, angle:135, opacity:0.12 });

let _PG = 1; // 封面=1 不显示
function header(slide, kicker, title, accent=C.teal){
  slide.background = { color: C.light };
  slide.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:0.28, h:H, fill:{color:accent} });
  slide.addText(kicker.toUpperCase(), { x:0.7, y:0.42, w:11, h:0.3, fontFace:FB, fontSize:12, color:accent, bold:true, charSpacing:3, margin:0 });
  slide.addText(title, { x:0.7, y:0.72, w:12, h:0.7, fontFace:FH, fontSize:25, color:C.ink, bold:true, margin:0 });
}
function pageno(slide){ _PG++; slide.addText(String(_PG), { x:W-0.8, y:H-0.5, w:0.5, h:0.3, fontFace:FB, fontSize:11, color:C.muted, align:"right", margin:0 }); }
function infoCard(slide, x, y, w, h, head, lines, accent){
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill:{color:C.card}, line:{color:C.line, width:1}, shadow:sh() });
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w:0.09, h, fill:{color:accent} });
  slide.addText(head, { x:x+0.28, y:y+0.16, w:w-0.4, h:0.34, fontFace:FH, fontSize:15, bold:true, color:accent, margin:0 });
  const rt = lines.map((t)=>({ text:t, options:{ bullet:{indent:12}, breakLine:true, color:C.ink, fontSize:11.5, paraSpaceAfter:5 } }));
  slide.addText(rt, { x:x+0.3, y:y+0.58, w:w-0.55, h:h-0.7, fontFace:FB, valign:"top", margin:0 });
}
function proseCard(slide, x, y, w, h, head, body, accent){
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill:{color:C.card}, line:{color:C.line, width:1}, shadow:sh() });
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w:0.09, h, fill:{color:accent} });
  slide.addText(head, { x:x+0.28, y:y+0.16, w:w-0.4, h:0.36, fontFace:FH, fontSize:15, bold:true, color:accent, margin:0 });
  const arr = Array.isArray(body) ? body : [body];
  const rt = arr.map((t)=>({ text:t, options:{ breakLine:true, color:C.ink, fontSize:12, paraSpaceAfter:7, lineSpacingMultiple:1.18 } }));
  slide.addText(rt, { x:x+0.3, y:y+0.62, w:w-0.55, h:h-0.74, fontFace:FB, valign:"top", margin:0 });
}
function badge(slide, x, y, txt, col, w=2.5){
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h:0.42, rectRadius:0.21, fill:{color:col} });
  slide.addText(txt, { x, y, w, h:0.42, fontFace:FB, fontSize:11.5, bold:true, color:"FFFFFF", align:"center", valign:"middle", margin:0 });
}
function citeFoot(slide, txt){
  const runs=[{ text:"来源  ", options:{ color:C.teal, fontSize:9, bold:true } }];
  txt.split(" · ").forEach((p,i)=>{
    let opt={ color:C.muted, fontSize:9 };
    const dm=p.match(/DOI\s+(10\.\S+)/);
    const gm=p.match(/(github\.com\/\S+|services\.healthtech\S*|tools\.iedb\.org\S*)/);
    if(dm) opt={ color:"1C7293", fontSize:9, hyperlink:{ url:"https://doi.org/"+dm[1], tooltip:"DOI" } };
    else if(gm) opt={ color:"1C7293", fontSize:9, hyperlink:{ url:"https://"+gm[1].replace(/^https?:\/\//,""), tooltip:"link" } };
    runs.push({ text:(i>0?" · ":"")+p, options:opt });
  });
  slide.addText(runs, { x:0.7, y:7.08, w:11.9, h:0.34, fontFace:FB, italic:true, valign:"top", margin:0 });
}
function codeBox(slide, x, y, w, h, head, lines){
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius:0.06, fill:{color:C.dark}, shadow:sh() });
  slide.addText(head, { x:x+0.2, y:y+0.12, w:w-0.4, h:0.3, fontFace:FB, fontSize:12, bold:true, color:C.mint, margin:0 });
  const rt = lines.map((t)=>({ text:t, options:{ breakLine:true, color:"D6F2EC", fontSize:9, paraSpaceAfter:1 } }));
  slide.addText(rt, { x:x+0.22, y:y+0.46, w:w-0.4, h:h-0.55, fontFace:FM, valign:"top", margin:0 });
}
// 工作原理页（输入 模型 输出 + 命令/输入/输出 代码框）
function principleSlide(o){
  const s = pres.addSlide();
  header(s, "工具 "+o.idx+" / 5 · 工作原理", o.name, o.accent);
  s.addText(o.sub, { x:0.7, y:1.46, w:11.8, h:0.5, fontFace:FB, fontSize:13, color:C.muted, margin:0 });
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:1.95, w:5.85, h:5.0, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  const stages = [["用什么输入", o.inP], ["模型怎么算", o.modelP], ["给出什么输出", o.outP]];
  let sy = 2.2;
  stages.forEach(st=>{
    s.addText(st[0], { x:0.95, y:sy, w:5.4, h:0.34, fontFace:FH, fontSize:14, bold:true, color:o.accent, margin:0 });
    s.addText(st[1], { x:0.95, y:sy+0.38, w:5.4, h:1.15, fontFace:FB, fontSize:11.5, color:C.ink, valign:"top", lineSpacingMultiple:1.15, margin:0 });
    sy += 1.6;
  });
  codeBox(s, 6.85, 1.95, 5.75, 1.62, "运行命令", o.cmd);
  codeBox(s, 6.85, 3.72, 5.75, 1.55, "输入数据样例", o.inFmt);
  codeBox(s, 6.85, 5.42, 5.75, 1.5, "输出数据样例", o.outFmt);
  citeFoot(s, o.cite);
  pageno(s);
}
// 四类信息页（完整中文句，照 v3 proseCard）
function toolSlide(o){
  const s = pres.addSlide();
  header(s, "工具 "+o.idx+" / 5 · 四类信息", o.name, o.accent);
  s.addText(o.tagline, { x:0.7, y:1.46, w:8.6, h:0.5, fontFace:FB, fontSize:13, color:C.muted, margin:0 });
  badge(s, W-3.2, 0.72, o.status, o.statusCol, 2.5);
  s.addText("方法  "+o.method, { x:W-3.2, y:1.22, w:2.5, h:0.3, fontFace:FB, fontSize:11, color:C.teal, bold:true, align:"center", margin:0 });
  const cx=0.7, cy=2.0, cw=6.0, ch=2.28, gap=0.3;
  proseCard(s, cx,        cy,        cw, ch, "输入数据与格式", o.input,  o.accent);
  proseCard(s, cx+cw+gap, cy,        cw, ch, "运行参数",       o.params, o.accent);
  proseCard(s, cx,        cy+ch+gap, cw, ch, "输出格式与含义", o.output, o.accent);
  proseCard(s, cx+cw+gap, cy+ch+gap, cw, ch, "特点与选用理由",  o.intro,  o.accent);
  citeFoot(s, o.cite);
  pageno(s);
}
// 图页（按真实宽高比 contain 放置，绝不拉伸；右侧 proseCard 读图要点）
function figSlide(o){
  const s = pres.addSlide();
  header(s, o.kicker, o.title, o.accent||C.teal);
  const fx=0.7, fy=1.7, fw=6.7, fh=5.25;
  s.addShape(pres.shapes.RECTANGLE, { x:fx, y:fy, w:fw, h:fh, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  const RT = { fig_perpatient_fisherz_5tools_v3:1.45, fig_spearman_5tools_v3:1.45, fig_auc_5tools_v3:1.45,
    fig_roc_5tools_v3:1.20, fig_consistency_5tools_v3:1.14, fig_lenstrat_5tools_v3:1.46 };
  const _k = (o.img.match(/([a-z_0-9]+)\.png/) || [])[1];
  const R = o.ratio || RT[_k] || 1.30, aw = fw-0.24, ah = fh-0.24;
  let iw = aw, ih = aw / R; if (ih > ah) { ih = ah; iw = ah * R; }
  const ix = fx + 0.12 + (aw - iw) / 2, iy = fy + 0.12 + (ah - ih) / 2;
  s.addImage({ path:o.img, x:ix, y:iy, w:iw, h:ih });
  proseCard(s, 7.6, 1.7, 5.03, 5.25, o.noteHead||"读图要点", o.notes, o.accent||C.teal);
  if(o.cite) citeFoot(s, o.cite);
  pageno(s);
}

// ============================================================ 封面
let s = pres.addSlide();
s.background = { color: C.dark };
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.mint} });
s.addShape(pres.shapes.OVAL, { x:W-3.3, y:-1.6, w:4.6, h:4.6, fill:{color:C.teal, transparency:78} });
s.addShape(pres.shapes.OVAL, { x:W-2.0, y:3.6,  w:3.2, h:3.2, fill:{color:C.sea,  transparency:82} });
s.addText("癌症个性化新抗原疫苗 · 预测工具部署与基准评估", { x:0.9, y:1.5, w:11, h:0.4, fontFace:FB, fontSize:15, color:C.mint, bold:true, charSpacing:2, margin:0 });
s.addText("第一批 5 个免疫原性预测工具\n部署测试与基准评估报告", { x:0.9, y:2.05, w:11.5, h:1.8, fontFace:FH, fontSize:40, bold:true, color:"FFFFFF", lineSpacingMultiple:1.05, margin:0 });
s.addText("DeepImmuno · PredIG · pTuneos · IMPROVE · NeoTImmuML", { x:0.9, y:4.3, w:11.8, h:0.5, fontFace:FB, fontSize:15, color:"CADCFC", margin:0 });
s.addShape(pres.shapes.LINE, { x:0.95, y:5.1, w:3.2, h:0, line:{color:C.mint, width:2} });
s.addText("对第一批五个现有免疫原性预测工具完成部署与运行测试，统一在 ELISpot 实验数据上评估它们对 T 细胞反应强弱的定量预测能力，并逐工具记录工作原理与四类信息。", { x:0.95, y:5.4, w:9.8, h:1.0, fontFace:FB, fontSize:13, color:"E6F2F2", valign:"top", lineSpacingMultiple:1.2, margin:0 });
s.addText("2026-06-28 · IMPROVE 跑通后全量更新", { x:W-5.2, y:6.7, w:4.6, h:0.3, fontFace:FB, fontSize:12, color:"8FB7BD", align:"right", margin:0 });

// ============================================================ 目录
s = pres.addSlide();
header(s, "目录", "本报告的内容结构");
const toc = [
  ["01","项目背景与任务","要解决什么、本报告做了什么"],
  ["02","工具逐一解析","每个工具的工作原理与四类信息"],
  ["03","部署工程与环境","运行环境、依赖与部署中遇到的问题"],
  ["04","数据与评测方法","测试数据来源、评测流程与指标含义"],
  ["05","基准结果","定量能力患者内 Fisher-Z 为主，判别力 AUC 为辅"],
  ["06","诚实边界与许可","已知限制、口径说明与许可提示"],
  ["07","结论与下一步","总体结论与后续计划"],
];
toc.forEach((it,i)=>{
  const col = i<4 ? 0.7 : 6.85;
  const row = i<4 ? i : i-4;
  const y = 1.95 + row*1.22;
  s.addShape(pres.shapes.RECTANGLE, { x:col, y, w:5.78, h:1.04, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:col, y, w:0.09, h:1.04, fill:{color:C.teal} });
  s.addText(it[0], { x:col+0.28, y:y+0.22, w:0.9, h:0.6, fontFace:FH, fontSize:26, bold:true, color:C.sea, valign:"middle", margin:0 });
  s.addText(it[1], { x:col+1.25, y:y+0.16, w:4.4, h:0.42, fontFace:FH, fontSize:15, bold:true, color:C.ink, margin:0 });
  s.addText(it[2], { x:col+1.25, y:y+0.58, w:4.4, h:0.38, fontFace:FB, fontSize:11, color:C.muted, margin:0 });
});
pageno(s);

// ============================================================ 项目背景
s = pres.addSlide();
header(s, "项目背景", "我们到底想预测什么");
proseCard(s, 0.7, 1.7, 5.9, 5.25, "从是非题到程度题", [
  "这个项目要解决的核心问题，是预测一条新抗原肽段在患者体内激发 T 细胞反应的强弱程度，而不只是判断它有没有免疫原性。",
  "过去大多数工具回答的是一道是非题，也就是这条肽能不能被免疫系统识别；而本项目关心的是一道程度题，也就是它能引起多强的反应。",
  "这个差别很关键，因为癌症疫苗和个体化免疫治疗在挑选靶点时，真正需要的是把候选肽按反应强弱排出优先次序，而不是简单地分成有反应和没反应两类。",
], C.teal);
proseCard(s, 6.85, 1.7, 5.78, 5.25, "本报告做了什么", [
  "本报告对第一批五个现有免疫原性预测工具完成了部署与运行测试，并在统一的 ELISpot 实验数据上做横向基准评估。",
  "每个工具都记录四类信息：输入数据与格式、运行参数、输出格式与含义，以及方法特点与选用理由。",
  "五个工具均已完成部署，都能产出可以进入基准的连续分数。由于各工具的端到端完整度不同，报告对此分级说明，但都不影响它们进入同一套基准比较。",
], C.sea);
pageno(s);

// ============================================================ 5 工具横评总表（Spearman 头条）
s = pres.addSlide();
header(s, "总览", "五个工具的方法、定量能力与判别力");
const hd = (t)=>({ text:t, options:{ fill:{color:C.dark}, color:"FFFFFF", bold:true, fontSize:11.5, align:"center", valign:"middle" } });
const cc = (t,col)=>({ text:t, options:{ color:col||C.ink, fontSize:11, align:"center", valign:"middle" } });
const cl = (t)=>({ text:t, options:{ color:C.ink, fontSize:11.5, bold:true, align:"left", valign:"middle" } });
const trows = [
  [hd("工具"), hd("方法"), hd("患者内 Fisher-Z\n[95% CI] · 主指标"), hd("全局 max ρ（p）\n· 对照"), hd("判别力\nAUC"), hd("端到端\n完整度")],
  [cl("IMPROVE"),    cc("随机森林"),     cc("+0.250\n[+0.021, +0.455] *",C.ok),  cc("+0.252（0.011）*",C.ok),  cc("0.616",C.muted), cc("特征降级",C.warn)],
  [cl("PredIG"),     cc("梯度提升树"),   cc("+0.229\n[−0.003, +0.437]",C.ink),   cc("+0.201（0.044）*",C.ok),  cc("0.663",C.muted), cc("完整端到端",C.ok)],
  [cl("pTuneos"),    cc("机器学习流程"), cc("+0.121\n[−0.112, +0.341]",C.ink),   cc("+0.119（0.237）",C.ink),  cc("0.718",C.muted), cc("识别子模型",C.warn)],
  [cl("NeoTImmuML"), cc("集成机器学习"), cc("+0.033\n[−0.194, +0.256]",C.ink),   cc("+0.022（0.829）",C.ink),  cc("0.655",C.muted), cc("自训版",C.warn)],
  [cl("DeepImmuno"), cc("卷积网络"),     cc("+0.015\n[−0.213, +0.242]",C.ink),   cc("−0.089（0.376）",C.ink),  cc("0.469",C.muted), cc("完整端到端",C.ok)],
];
s.addTable(trows, { x:0.7, y:1.78, w:11.9, colW:[1.45,1.85,3.5,2.35,1.1,1.65],
  rowH:[0.7,0.6,0.6,0.6,0.6,0.6], border:{pt:1,color:C.line}, align:"center", valign:"middle", fontFace:FB, fill:{color:C.card} });
s.addText("本项目最关心定量能力——工具打分能否把免疫反应的强弱排对。主指标改为患者内 Fisher-Z 相关：先在每位患者内部单独算 Spearman，再用 Fisher-Z 加权聚合并给 95% 置信区间，扣除了患者间基线差异，比全局相关更稳健，与项目主表口径统一。按此主口径，五个工具里仅 IMPROVE 的置信区间整段落在零以上、达显著正相关，PredIG 下界 −0.003 擦零未达显著，其余三个不显著；全局 max ρ 仅作对照，对照口径下 IMPROVE 与 PredIG 显著。AUC 只反映有无反应的二分判别，仅作参考。", { x:0.7, y:5.52, w:11.9, h:0.95, fontFace:FB, fontSize:10.5, color:C.muted, valign:"top", lineSpacingMultiple:1.12, margin:0 });
s.addText("星号表示显著（患者内：95% CI 不含零；全局：括号内 p<0.05）。NeoTImmuML 官方未发布预训练权重，基准用公开数据自训版，数值不对标原论文。2026-06-28 口径统一：患者内 Fisher-Z 为主、全局 Spearman 为对照，与项目主表一致；数据见 analysis/per_patient_spearman_16tools.csv 与 metrics_ds2_16tools.csv。", { x:0.7, y:6.52, w:11.9, h:0.5, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", lineSpacingMultiple:1.05, margin:0 });
pageno(s);

// ============================================================ 逐工具：原理页 + 四类信息页 ×5
// 1 DeepImmuno
principleSlide({ idx:1, name:"DeepImmuno", accent:"028090",
  sub:"用卷积神经网络判断一条肽段能不能激活 CD8+ T 细胞",
  inP:"只要两样东西，一条肽段序列和它对应的 HLA 分型，肽段长度固定为九或十个氨基酸。它不需要基因组，也不需要表达量，是这一批工具里最省事的。",
  modelP:"先把氨基酸序列和 HLA 假基序按物化性质编码成一张数字矩阵，再用卷积神经网络像扫图像一样扫过这张矩阵，自动抓出与免疫原性有关的局部模式，最后汇总成一个分数。",
  outP:"输出一个零到一之间的连续分数，越接近一表示越可能激活 T 细胞。实测已知强表位如 CMV 的 NLVPMVATV 确实拿到高分，符合预期。",
  cmd:["# 单条", "python deepimmuno-cnn.py \\", "  --mode single \\", "  --epitope NLVPMVATV --hla HLA-A*0201", "# 批量", "#   --mode multiple --intdir IN --outdir OUT"],
  inFmt:["# CSV，两列，无表头", "# 肽段, HLA", "NLVPMVATV,HLA-A*0201", "GILGFVFTL,HLA-A*0201"],
  outFmt:["peptide    HLA          immunogenicity", "NLVPMVATV  HLA-A*0201   0.957", "GILGFVFTL  HLA-A*0201   0.887"],
  cite:"DeepImmuno, Briefings in Bioinformatics 2021 · DOI 10.1093/bib/bbab160 · github.com/frankligy/DeepImmuno" });
toolSlide({ idx:1, name:"DeepImmuno", accent:"028090", method:"卷积网络", status:"完整端到端 · AUC 0.469", statusCol:C.ok,
  tagline:"用卷积神经网络判断一条肽段能否激活 CD8+ T 细胞，最轻量，只要肽段和 HLA",
  input:[ "输入是一个没有表头的两列 CSV 文件，第一列是肽段序列，第二列是对应的 HLA 分型，HLA 按 HLA-A*0201 的写法填写。",
          "肽段长度固定为九或十个氨基酸，运行时不需要基因组，也不需要任何 HLA 数据库。" ],
  params:[ "单条预测用 single 模式，结果直接打印在屏幕上；批量预测用 multiple 模式，指定输入和输出目录即可。",
           "它没有可调的超参数，但必须在代码仓库的根目录下运行。" ],
  output:[ "输出是三列，分别是肽段、HLA 和免疫原性分数，这个分数是零到一之间的连续值，越高代表越可能激活 T 细胞。",
           "实测 CMV 的强表位 NLVPMVATV 拿到零点九五七的高分，结果合理。" ],
  intro:[ "它是这一批工具里最省事的，只要肽段和 HLA 就能运行，不依赖任何收费工具，普通处理器即可。",
          "运行环境为 Python 3.8 加 TensorFlow 2.3，需要把 protobuf 降到 3.20，它的主要限制是肽长只能是九或十。" ],
  cite:"DeepImmuno, Briefings in Bioinformatics 2021 · DOI 10.1093/bib/bbab160 · github.com/frankligy/DeepImmuno" });
// 2 PredIG
principleSlide({ idx:2, name:"PredIG", accent:"1C7293",
  sub:"用梯度提升树预测免疫原性，并给出一串可解释的特征",
  inP:"输入肽段、HLA 分型，以及在重组模式下肽段所在的蛋白序列。它支持三种输入模式，肽段长度为八到十四个氨基酸。",
  modelP:"先调用一串内置工具算出十三类特征，包括蛋白酶切位点、提呈分、物化性质和 TCR 接触位点等，再把这些特征喂给梯度提升树模型综合打分。特征可解释是它的卖点。",
  outP:"输出一个零到一之间的免疫原性分数，同时附上那十三列特征，方便回看模型究竟凭什么给出这个分数。",
  cmd:["python predig.py \\", "  --type recombinant \\", "  --modelXG neoant \\", "  -i input.csv \\", "  -o result.csv"],
  inFmt:["# CSV，重组模式", "epitope,HLA_allele,protein_seq,protein_name", "SLLMWITQV,HLA-A*0201,MSLL...,TP53"],
  outFmt:["# CSV，含 PredIG 分 + 13 列特征", "epitope    PredIG   NOAH   TCR_contact", "SLLMWITQV  0.0061   0.42   ..."],
  cite:"PredIG, Genome Medicine 2025 · DOI 10.1186/s13073-025-01569-8 · github.com/BSC-CNS-EAPM/PredIG" });
toolSlide({ idx:2, name:"PredIG", accent:"1C7293", method:"梯度提升树", status:"完整端到端 · AUC 0.663", statusCol:C.ok,
  tagline:"用梯度提升树预测 T 细胞表位免疫原性，按抗原类型分专用模型，结果可解释",
  input:[ "它支持三种输入模式，分别基于 Uniprot 编号、重组蛋白序列和 FASTA 文件。",
          "以重组模式为例，需要肽段、HLA 分型、所在蛋白序列和蛋白名四列，肽段长度为八到十四个氨基酸。" ],
  params:[ "用 modelXG 参数选择模型，可选新抗原专用、非经典抗原或自定义模型；用 type 参数选择输入模式；用 o 参数指定输出文件。" ],
  output:[ "输出是一个 CSV 文件，PredIG 列是零到一之间的连续免疫原性分数，同时附带十三列特征，包括切割位点、提呈分、物化性质和 TCR 接触位点等。",
           "实测 SLLMWITQV 得到零点零零六一。" ],
  intro:[ "它的卖点是连续分数加可解释特征，并且把全部依赖打包进容器，省去自行配置环境的麻烦。",
          "官方提供的 Docker 镜像约十四点四 GB，在集群上转成 Singularity 后约四点六 GB，主要限制是镜像体积较大。" ],
  cite:"PredIG, Genome Medicine 2025 · DOI 10.1186/s13073-025-01569-8 · github.com/BSC-CNS-EAPM/PredIG" });
// 3 pTuneos
principleSlide({ idx:3, name:"pTuneos", accent:"028090",
  sub:"一整套个性化新抗原流程，其中识别子模型可以单独给肽段打分",
  inP:"完整流程需要测序得到的变异、表达量、拷贝数、肿瘤纯度和 HLA，依赖全基因组数据，无法直接喂入纯肽段。它的识别子模型只要突变肽、对应野生肽和 HLA 三列，这一部分能用来跑 ELISpot 肽段。",
  modelP:"完整流程先把测序变异注释成突变肽，再逐层打分；识别子模型则针对一对突变肽与野生肽算结合、相似度和被 T 细胞识别等特征，输出免疫识别分。本基准用的就是这个子模型。",
  outP:"完整流程给出患者级别的排名分，这个分乘进了表达量和突变频率，需要测序数据；识别子模型给出纯肽段的免疫识别分，这一部分可以与其它工具横向比较。示例数据端到端跑出四十个候选新抗原。",
  cmd:["# 完整流程", "python pTuneos.py VCF -i config.yaml", "# 识别子模型（喂肽段）", "# 自写脚本调用 InVivoModelAndScore"],
  inFmt:["# 子模型输入：三列", "MT_pep,     WT_pep,     HLA", "AAAVFKTLP,  AAAVFKTLR,  HLA-A*02:01"],
  outFmt:["# 子模型识别分 model_pro", "MT_pep      model_pro", "AAAVFKTLP   0.73"],
  cite:"pTuneos, Genome Medicine 2019 · DOI 10.1186/s13073-019-0679-x · github.com/bm2-lab/pTuneos" });
toolSlide({ idx:3, name:"pTuneos", accent:"028090", method:"机器学习流程", status:"识别子模型 · AUC 0.718", statusCol:C.warn,
  tagline:"一整套个性化新抗原流程，从测序数据到排名；识别子模型可单独拿肽段来打分",
  input:[ "完整流程需要测序变异、表达量、拷贝数、肿瘤纯度和 HLA，依赖全基因组数据，无法直接喂入纯肽段。",
          "它的识别子模型只需要突变肽、对应野生肽和 HLA 三列，这一部分可以用来评测 ELISpot 肽段。" ],
  params:[ "完整流程通过 pTuneos.py 配合配置文件运行；识别子模型则需要自行编写脚本调用其打分函数。",
           "运行时可以用多进程和批量结合预测来加速。" ],
  output:[ "完整流程给出患者级别的排名分，这个分乘进了表达量和突变频率，必须有测序数据；识别子模型给出纯肽段的免疫识别分，本基准用的就是这部分，可以与其它工具横比。",
           "示例数据端到端跑出四十个候选新抗原。" ],
  intro:[ "它的镜像自带 netMHCpan、VEP、GATK 等全套工具，修复八处问题并准备十四 GB 注释缓存后才端到端跑通。",
          "进入基准用的是识别子模型，与官方逻辑对账完全一致，相关系数为一，但这并不代表整条流程的端到端能力。完整流程在本地容器跑通，集群因权限限制未运行。" ],
  cite:"pTuneos, Genome Medicine 2019 · DOI 10.1186/s13073-019-0679-x · github.com/bm2-lab/pTuneos" });
// 4 IMPROVE
principleSlide({ idx:4, name:"IMPROVE", accent:"1C7293",
  sub:"用随机森林给新表位打分，整合了二十二个特征",
  inP:"输入突变肽、对应野生肽和 HLA，采用 TSV 格式，肽段长度为八到十二个氨基酸。流程分两步，先计算特征，再做预测。",
  modelP:"第一步用外部工具算出二十二个特征，包含结合、稳定性、TCR 识别分和自相似度等；第二步把特征喂给随机森林综合打分，每个变体用五个森林做集成。本基准里表达相关特征因 ELISpot 没有 RNA 数据而降级。",
  outP:"在输入表后追加一列 mean_prediction_rf，是多折多森林集成后的平均分，取值在零到一之间。",
  cmd:["# 第一步：算特征", "bash run_feature_calc.sh input.tsv", "# 第二步：预测", "python Predict.py --model Simple"],
  inFmt:["# TSV：突变肽 + 野生肽 + HLA", "Mut_pep     Norm_pep    HLA", "EEFLNSWML   EEFLNSWMV   HLA-B*08:01"],
  outFmt:["# 追加 mean_prediction_rf 列", "Mut_pep     mean_prediction_rf", "EEFLNSWML   0.5146"],
  cite:"IMPROVE, Frontiers in Immunology 2024 · DOI 10.3389/fimmu.2024.1360281 · github.com/SRHgroup/IMPROVE_tool" });
toolSlide({ idx:4, name:"IMPROVE", accent:"1C7293", method:"随机森林", status:"特征降级 · AUC 0.616", statusCol:C.warn,
  tagline:"用随机森林给新表位的免疫原性打分，二十二个特征，分三种变体模型",
  input:[ "输入是 TSV 格式，必填突变肽、对应野生肽和 HLA 三列，肽段长度为八到十二个氨基酸。",
          "流程分两步，先计算特征，再跑随机森林做预测。" ],
  params:[ "用 model 参数选择 Simple、TME_excluded 或 TME_included 三种变体，每个变体加载五个森林做集成。" ],
  output:[ "输出在输入表后追加一列 mean_prediction_rf，是多折与多森林集成后的平均分数，取值在零到一之间。",
           "实测 Simple 变体的 EEFLNSWML 得到零点五一四六。" ],
  intro:[ "它整合了二十二个专为新表位排名设计的特征，其中包含 TCR 识别信号。",
          "本基准的缺口在于 ELISpot 没有 RNA 表达量，导致表达相关特征降级，稳定性特征依赖的外部工具又受系统库版本限制。预测步骤在本地和集群都跑通，这属于数据缺一块而不是装不上。" ],
  cite:"IMPROVE, Frontiers in Immunology 2024 · DOI 10.3389/fimmu.2024.1360281 · github.com/SRHgroup/IMPROVE_tool" });
// 5 NeoTImmuML
principleSlide({ idx:5, name:"NeoTImmuML（自训版）", accent:"028090",
  sub:"三种模型加权集成，用七十八个肽段物化特征；官方无权重，本基准为自训版",
  inP:"输入肽段加上七十八个物化特征，需要先用 R 语言的 Peptides 包算好，不需要 HLA，肽段长度为八到十三个氨基酸。",
  modelP:"把七十八维特征喂给 LightGBM、XGBoost 和随机森林三个模型，再加权集成成一个概率。官方仓库是研究用 notebook，没有带预训练权重，因此本基准用公开肿瘤抗原库自己重训了一版，数值不对标原论文。",
  outP:"输出一个零到一之间的免疫原性概率，可以用来排出强弱，同时给出分类指标和雷达图。",
  cmd:["# 不是命令行，是 Jupyter notebook", "# 改 file_path 指向数据后", "# 顺序运行 21 个单元格", "# （含 8 算法对比 + 加权集成）"],
  inFmt:["# CSV：肽段 + 标签 + 78 特征", "Peptide    label  feat1  feat2 ... feat78", "AAAVFKTLP  1      0.12   -0.4  ..."],
  outFmt:["# predict_proba 连续概率", "Peptide    immuno_prob", "AAAVFKTLP  0.81"],
  cite:"NeoTImmuML, Frontiers in Immunology 2025 · DOI 10.3389/fimmu.2025.1681396 · github.com/01SYan19/NeoTImmuML" });
toolSlide({ idx:5, name:"NeoTImmuML（自训版）", accent:"028090", method:"集成机器学习", status:"自训版 · AUC 0.655", statusCol:C.warn,
  tagline:"三种模型加权集成预测肿瘤新抗原免疫原性，用七十八个肽段物化特征",
  input:[ "输入是 CSV 格式，包含肽段、标签和七十八个物化特征，不需要 HLA，肽段长度为八到十三个氨基酸。",
          "这七十八个特征需要先用 R 语言的 Peptides 包计算好。" ],
  params:[ "它不是命令行工具，而是一个包含二十一个单元格的 Jupyter notebook。",
           "把数据路径改好之后顺序运行即可，内含八种算法的对比、加权集成与交叉验证。" ],
  output:[ "输出是零到一之间的免疫原性概率，可以用来排出强弱，同时给出分类指标和雷达图。",
           "官方仓库没有发布预训练权重，因此本基准使用公开肿瘤抗原库自行重训的版本，数值不对标原论文精度。" ],
  intro:[ "它只用肽段特征，不需要 HLA 也不需要任何收费工具，安装最省心。",
          "主要限制是官方只提供研究用的 notebook 而没有权重，需要用公开数据重新训练，并且不含七十八个特征的计算代码，需要自行用 R 计算。" ],
  cite:"NeoTImmuML, Frontiers in Immunology 2025 · DOI 10.3389/fimmu.2025.1681396 · github.com/01SYan19/NeoTImmuML" });

// ============================================================ 部署工程 ① 两套战场总览
const ENVCOL = { "本机":C.sea, "HPC":C.warn, "—":C.gray };
function toolIssueGrid(s, tools){
  tools.forEach((t,i)=>{
    const x = (i%2===0)? 0.7 : 6.95;
    const y = 1.92 + Math.floor(i/2)*1.72;
    const w = 5.68, h = 1.62;
    const acc = t.accent || C.teal;
    s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
    s.addShape(pres.shapes.RECTANGLE, { x, y, w:0.07, h, fill:{color:acc} });
    s.addText(t.name, { x:x+0.22, y:y+0.1, w:3.5, h:0.32, fontFace:FH, fontSize:12.5, bold:true, color:acc, valign:"middle", margin:0 });
    s.addText(t.meta, { x:x+w-2.7, y:y+0.12, w:2.5, h:0.28, fontFace:FB, fontSize:9, color:C.muted, align:"right", valign:"middle", margin:0 });
    const runs = [];
    t.issues.forEach((is)=>{
      runs.push({ text:is.env+" ", options:{ color:ENVCOL[is.env]||C.gray, bold:true, fontSize:8.5 } });
      runs.push({ text:is.text, options:{ color:C.ink, fontSize:8.5, breakLine:true } });
    });
    s.addText(runs, { x:x+0.22, y:y+0.46, w:w-0.42, h:h-0.54, fontFace:FB, valign:"top", lineSpacingMultiple:1.04, margin:0 });
  });
}

s = pres.addSlide();
header(s, "部署工程", "两套部署战场：本机调试，集群正式跑");
s.addText("本批五个工具都经过两套环境，先在本机的 Linux 子系统里逐个调通并摸清四类信息，再以学校的高性能计算集群作为最终部署目标。两边出网都受限，工具多为面向 Linux 的老链路，需要逐个适配。",
  { x:0.7, y:1.46, w:11.9, h:0.5, fontFace:FB, fontSize:13, color:C.muted, margin:0 });
infoCard(s, 0.7,  2.1, 3.97, 4.35, "本机 · WSL2 Ubuntu 24.04", [
  "角色是调试主场，逐个工具跑通并摸清四类信息",
  "环境为直通显卡加 conda 加 Docker",
  "不用原生 Windows，是因为仓库含带星号的非法文件名，且工具多为 Linux 老链路",
], C.sea);
infoCard(s, 4.93, 2.1, 3.97, 4.35, "HPC · 学校集群", [
  "角色是正式大规模跑，也是团队最终交付目标",
  "环境为 Singularity 容器加多核处理器，没有 Docker",
  "推理大多在处理器上完成，基本不占显卡",
], C.teal);
infoCard(s, 9.16, 2.1, 3.47, 4.35, "两边共同约束", [
  "GitHub、PyPI、DTU 可达，但 Docker Hub 两边都不通",
  "对策是本机打包镜像后上传，再转成 Singularity",
  "学术工具如 netMHCpan 禁止再分发，包含其跑出的数字",
], C.warn);
s.addText("下面先看各工具的运行环境与依赖，再按工具逐个列出部署中遇到的问题，并标注来源环境。",
  { x:0.7, y:6.62, w:11.9, h:0.4, fontFace:FB, fontSize:10.5, italic:true, color:C.muted, margin:0 });
pageno(s);

// ============================================================ 部署工程 ①b 各工具环境与依赖速查表
s = pres.addSlide();
header(s, "部署工程 · 环境", "各工具的运行环境与依赖包", C.teal);
const eh = (t)=>({ text:t, options:{ fill:{color:C.dark}, color:"FFFFFF", bold:true, fontSize:11.5, align:"center", valign:"middle" } });
const en = (t,col)=>({ text:t, options:{ color:col||C.ink, fontSize:9.5, align:"left", valign:"middle" } });
const enl= (t)=>({ text:t, options:{ color:C.ink, fontSize:11, bold:true, align:"left", valign:"middle" } });
const erows = [
  [eh("工具"), eh("运行环境"), eh("关键包与版本"), eh("外部工具与权重")],
  [enl("DeepImmuno"),   en("conda · Python 3.8"),       en("tensorflow 2.3.0 · numpy 1.18.5 · pandas 1.1.1 · protobuf 3.20.3"), en("无，纯肽段加 HLA",C.ok)],
  [enl("PredIG"),       en("Docker / Singularity 镜像"), en("镜像内置 R 与 XGBoost 全套"),                                      en("NetCleave · NOAH · netCTLpan · MHCflurry，镜像自带")],
  [enl("pTuneos"),      en("Docker 镜像 · Python 2.7"),  en("Python 2.7 · R 3.2.3 · scikit-learn，容器内"),                   en("netMHCpan-4.0 · VEP 加 14G 缓存 · GATK · PyClone，镜像自带",C.warn)],
  [enl("IMPROVE"),      en("conda · Python 3.11"),       en("numpy ≥2.0 · scikit-learn 1.9 · pandas · seaborn"),               en("netMHCpan-4.1 · netMHCstabpan · PRIME · MixMHCpred 加 1.9G 权重",C.warn)],
  [enl("NeoTImmuML"),   en("conda · Python 3.10 加 R"),  en("lightgbm · xgboost · scikit-learn · pandas · numpy · R Peptides 2.4.6"), en("无许可工具，权重自训，官方未发布",C.warn)],
];
s.addTable(erows, { x:0.55, y:1.95, w:12.25, colW:[1.9,2.6,3.95,3.8],
  rowH:[0.5,0.72,0.72,0.72,0.72,0.72],
  border:{pt:1,color:C.line}, valign:"middle", fontFace:FB, fill:{color:C.card} });
s.addText("环境分两类，轻量工具用 conda 建独立的 Python 环境装包，老链路或多依赖工具则用官方 Docker 镜像，在集群上转成 Singularity 打包整套环境。NeoTImmuML 官方未发布权重，用公开数据自训替代；netMHCpan 等学术工具需 DTU 许可，禁止再分发。",
  { x:0.55, y:6.4, w:12.25, h:0.7, fontFace:FB, fontSize:10, color:C.muted, valign:"top", lineSpacingMultiple:1.1, margin:0 });
pageno(s);

// ============================================================ 部署工程 ② 按工具列问题
s = pres.addSlide();
header(s, "部署工程 · 按工具", "各工具部署中遇到的问题与解法，并标注来源环境", C.sea);
s.addText([
  { text:"来源标签  ", options:{ color:C.muted, fontSize:11, bold:true } },
  { text:" 本机 ", options:{ color:C.sea, fontSize:11, bold:true } },
  { text:"指本地 WSL2，     ", options:{ color:C.muted, fontSize:11 } },
  { text:" HPC ", options:{ color:C.warn, fontSize:11, bold:true } },
  { text:"指学校集群。", options:{ color:C.muted, fontSize:11 } },
], { x:0.7, y:1.5, w:11.9, h:0.34, fontFace:FB, valign:"top", margin:0 });
toolIssueGrid(s, [
  { name:"DeepImmuno", meta:"CNN · 本机加集群均通", accent:C.teal, issues:[
    { env:"本机", text:"仓库含星号文件名，Windows 无法保存，改搬到 WSL2" },
    { env:"本机", text:"protobuf 须降到 3.20，TF2.3 与 Py3.8 对版本严格" },
    { env:"HPC",  text:"顺利跑通，结果与本机一字不差" },
  ]},
  { name:"PredIG", meta:"XGBoost · 官方镜像", accent:C.teal, issues:[
    { env:"本机", text:"镜像 14.4G 加 Docker Hub 受限，改用镜像源加代理拉取" },
    { env:"本机", text:"单次输入硬限不到 5000 行，切块串跑后按序拼回" },
    { env:"HPC",  text:"镜像转 Singularity，只读容器写临时目录需开 writable-tmpfs" },
  ]},
  { name:"pTuneos", meta:"Py2.7 流水线", accent:C.teal, issues:[
    { env:"本机", text:"自带样例连修 8 处 bug 才端到端跑通" },
    { env:"本机", text:"VEP 注释库 14G 下载龟速，多连接提速约 12 倍" },
    { env:"本机", text:"完整版喂不了 ELISpot，改用识别子模型进基准" },
    { env:"HPC",  text:"镜像程序在 root 目录且无 fakeroot，改在本机容器验证" },
  ]},
  { name:"IMPROVE", meta:"随机森林", accent:C.teal, issues:[
    { env:"本机", text:"模型用新版 numpy 保存，换 Py3.11 才读得了" },
    { env:"本机", text:"老二进制 netMHCpan-2.8 崩溃，靠内核 vsyscall 救活" },
    { env:"本机", text:"表达量特征需 RNA-seq，ELISpot 没有，该特征降级" },
    { env:"HPC",  text:"glibc 2.28 低于 stabpan 要求的 2.29，稳定性特征跑不了" },
  ]},
  { name:"NeoTImmuML", meta:"集成 ML · 自训替代", accent:C.teal, issues:[
    { env:"本机", text:"源码 URL 未公开，用浏览器自动化从数据库站抓出" },
    { env:"本机", text:"无官方权重，用公开数据自训，已确认全网无权重" },
    { env:"本机", text:"78 特征的 R 库接口随版本变，逐列核对修对 76 个" },
  ]},
]);
pageno(s);

// ============================================================ 数据集来源与规模
s = pres.addSlide();
header(s, "测试数据从哪来", "ELISpot 实测数据、规模与正负比");
const dscards = [
  ["DS2 · 主测试集，有阴有阳","028090",[
    "一百零一条肽段，其中有反应九十条、无反应十一条",
    "来自九位患者，反应值 SFC 范围从负三十四到二百零九",
    "用途是算 AUC，衡量能不能分开有反应和无反应",
  ]],
  ["DS1 · 定量验证集，全阳","00A896",[
    "八十二条肽段，全部有反应，没有阴性",
    "来自六位患者，强度 SFC 从十六到六百七十七，约四十倍跨度",
    "用途是检验能不能把强弱排对",
  ]],
];
let dy=1.85;
dscards.forEach(d=>{
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:dy, w:7.3, h:1.95, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:dy, w:0.09, h:1.95, fill:{color:d[1]} });
  s.addText(d[0], { x:0.96, y:dy+0.14, w:6.9, h:0.4, fontFace:FH, fontSize:15, bold:true, color:d[1], margin:0 });
  s.addText(d[2].map(x=>({text:x,options:{bullet:{indent:12},breakLine:true,color:C.ink,fontSize:11.5,paraSpaceAfter:4}})),
    { x:0.98, y:dy+0.58, w:6.85, h:1.3, fontFace:FB, valign:"top", margin:0 });
  dy += 2.1;
});
s.addShape(pres.shapes.RECTANGLE, { x:8.25, y:1.85, w:4.4, h:4.05, fill:{color:C.dark}, shadow:sh() });
s.addText("关键说明", { x:8.5, y:2.02, w:4.0, h:0.4, fontFace:FH, fontSize:15, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"标签是 ELISpot SFC", options:{ bold:true, color:"FFFFFF", fontSize:12, breakLine:true } },
  { text:"SFC 是斑点形成细胞数，反映 T 细胞反应强度的实验读数，阈值大于零记为有反应。", options:{ color:"CADCFC", fontSize:10.5, breakLine:true, paraSpaceAfter:10 } },
  { text:"展开规模", options:{ bold:true, color:"FFFFFF", fontSize:12, breakLine:true } },
  { text:"每条肽按子肽与 HLA 窗口展开，DS1 加 DS2 共三万四千二百四十七行预测。", options:{ color:"CADCFC", fontSize:10.5, breakLine:true, paraSpaceAfter:10 } },
  { text:"局限", options:{ bold:true, color:"FFFFFF", fontSize:12, breakLine:true } },
  { text:"样本来自有限患者，存在聚集；DS2 阴性仅十一条，置信区间偏宽。", options:{ color:"CADCFC", fontSize:10.5 } },
], { x:8.5, y:2.46, w:3.95, h:3.3, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
s.addText("数据来源为课题组 ELISpot 实测（Elispot_Dataset1.xlsx / Elispot_Dataset2.xlsx），为内部数据，无公开链接。", { x:0.7, y:6.05, w:7.3, h:0.4, fontFace:FB, fontSize:10, italic:true, color:C.muted, valign:"top", margin:0 });
pageno(s);

// ============================================================ 评测流程图
s = pres.addSlide();
header(s, "评测流程", "从一条肽段到工具横向对比");
const flow = [
  ["肽段输入","DS1 与 DS2\n的肽段加 HLA",C.teal],
  ["五工具打分","各工具独立\n给免疫原性分",C.sea],
  ["聚合","子肽与 HLA\n逐肽取最大值",C.teal],
  ["切标签","按 SFC 大于零\n分有无反应",C.sea],
  ["算指标","Spearman 与 AUC\n等同口径计算",C.teal],
  ["横向对比","五工具同口径\n排名与显著性",C.dark],
];
const bw=1.78, bh=1.5, by=2.6, gap=0.26, startx=0.72;
flow.forEach((b,i)=>{
  const x=startx + i*(bw+gap);
  const fc = b[2]===C.dark ? C.dark : C.card;
  const tc = b[2]===C.dark ? "FFFFFF" : C.ink;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y:by, w:bw, h:bh, rectRadius:0.08, fill:{color:fc}, line:{color:b[2],width:2}, shadow:sh() });
  s.addText(b[0], { x, y:by+0.22, w:bw, h:0.45, fontFace:FH, fontSize:15, bold:true, color:b[2]===C.dark?C.mint:b[2], align:"center", margin:0 });
  s.addText(b[1], { x:x+0.1, y:by+0.72, w:bw-0.2, h:0.65, fontFace:FB, fontSize:10, color:tc, align:"center", valign:"top", lineSpacingMultiple:1.0, margin:0 });
  if(i<flow.length-1) s.addText("▶", { x:x+bw-0.04, y:by+bh/2-0.22, w:gap+0.08, h:0.44, fontFace:FB, fontSize:14, bold:true, color:C.muted, align:"center", valign:"middle", margin:0 });
});
s.addShape(pres.shapes.RECTANGLE, { x:0.72, y:4.7, w:11.9, h:1.95, fill:{color:"F2F7F7"}, line:{color:C.line,width:1} });
s.addText("读这张图", { x:0.95, y:4.85, w:11, h:0.36, fontFace:FH, fontSize:14, bold:true, color:C.teal, margin:0 });
s.addText([
  { text:"同一批肽段喂给五个工具，每个工具独立打分。因为一条肽会拆成多个子肽与 HLA 组合，所以统一按逐肽取最大分聚合，再按实验反应值大于零切出有无反应标签，最后用同一套指标评估，让五个工具在完全相同的口径下横向对比。", options:{ color:C.ink, fontSize:11.5, breakLine:true, paraSpaceAfter:5 } },
  { text:"关键在于所有工具都走完全一致的聚合、阈值与指标口径，保证可比。", options:{ color:C.dark, fontSize:11.5, bold:true } },
], { x:0.95, y:5.25, w:11.45, h:1.3, fontFace:FB, valign:"top", lineSpacingMultiple:1.08, margin:0 });
pageno(s);

// ============================================================ 基准方法
s = pres.addSlide();
header(s, "基准方法", "用什么数据、怎么比、看什么指标");
const mcards = [
  ["测试数据","真实 ELISpot 实验数据 DS2 共一百零一条肽段，按实验反应值切分为有反应九十条、无反应十一条，反应值不大于零算真无反应。","028090"],
  ["参评工具","第一批五个免疫原性工具，分别是 DeepImmuno、PredIG、pTuneos、IMPROVE 和 NeoTImmuML。","00A896"],
  ["怎么比","一条肽段会拆成多个子肽与 HLA 组合，先统一取最大值聚合，再按阈值切标签，与全项目其它交付同口径，保证可比。","1C7293"],
  ["看什么","首要指标是 Spearman 相关，衡量分数与反应强弱是否同向，也就是能否定量；AUC 衡量能否分开有反应和无反应，零点五相当于随机，只作参考；AUPRC 作为补充。","028090"],
];
let my=1.85;
mcards.forEach(m=>{
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:my, w:11.9, h:1.18, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:my, w:0.09, h:1.18, fill:{color:m[2]} });
  s.addText(m[0], { x:1.0, y:my+0.16, w:2.4, h:0.85, fontFace:FH, fontSize:15, bold:true, color:m[2], valign:"top", margin:0 });
  s.addText(m[1], { x:3.4, y:my+0.14, w:9.0, h:0.9, fontFace:FB, fontSize:12, color:C.ink, valign:"middle", lineSpacingMultiple:1.05, margin:0 });
  my += 1.28;
});
s.addText("所有数字经 analysis/metrics_ds2_16tools.csv 核对，统一最大值聚合、阈值大于零，与全项目其它交付一致。", { x:0.7, y:6.95, w:11.9, h:0.4, fontFace:FB, fontSize:10.5, italic:true, color:C.muted, margin:0 });
pageno(s);

// ============================================================ 看懂这些指标（Spearman 为首要）
s = pres.addSlide();
header(s, "先看懂这些指标", "后面每个数字是什么意思、最该信哪个");
const metricCards = [
  ["Spearman 相关（能否分强弱）","模型分数的高低排序，和真实反应强弱的排序，吻合到什么程度。","正一是完全同向，零是没关系，负一是完全反着。这是本报告最看重的定量能力指标，以患者内 Fisher-Z 口径为主、全局口径为对照。",C.sea,"主指标"],
  ["AUC（判别力）","随便挑一条有反应和一条没反应的肽，模型给有反应那条打更高分的概率。","一是完美，零点五和瞎猜一样，小于零点五是反着的。它只回答有没有反应，作为参考。",C.teal,"参考"],
  ["AUPRC","精确率与召回率曲线下的面积，在阳性很少时比 AUC 更敏感。","本数据阳性本就占百分之八十九，起点很高，提升空间小，参考意义有限。",C.warn,"参考有限"],
  ["95% 置信区间与 p 值","重复抽样两千次看指标的波动范围，p 小于零点零五才算不是偶然。","区间越宽越不确定。本数据样本小，区间普遍偏宽。",C.crit,"看可信度"],
];
let mcx=0.7, mcy=1.85, mcw=5.92, mch=1.95, mgapx=0.36, mgapy=0.3;
metricCards.forEach((m,i)=>{
  const x = mcx + (i%2)*(mcw+mgapx);
  const y = mcy + Math.floor(i/2)*(mch+mgapy);
  s.addShape(pres.shapes.RECTANGLE, { x, y, w:mcw, h:mch, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x, y, w:0.09, h:mch, fill:{color:m[3]} });
  s.addText(m[0], { x:x+0.26, y:y+0.16, w:mcw-1.5, h:0.4, fontFace:FH, fontSize:15, bold:true, color:m[3], margin:0 });
  badge(s, x+mcw-1.25, y+0.16, m[4], m[3], 1.1);
  s.addText([
    { text:m[1], options:{ breakLine:true, color:C.ink, fontSize:11.5, paraSpaceAfter:5 } },
    { text:m[2], options:{ color:C.muted, fontSize:11 } },
  ], { x:x+0.28, y:y+0.7, w:mcw-0.55, h:mch-0.8, fontFace:FB, valign:"top", lineSpacingMultiple:1.06, margin:0 });
});
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:6.05, w:11.92, h:0.85, fill:{color:"E6F4F1"}, line:{color:C.sea,width:1} });
s.addText([
  { text:"一句话  ", options:{ bold:true, color:C.teal, fontSize:11.5 } },
  { text:"本报告以患者内 Fisher-Z 相关衡量能否分强弱、作为首要指标，全局 Spearman 作对照，AUC 衡量判别力、只作参考；AUPRC 因阳性占比高参考有限；样本量小使所有指标的置信区间都偏宽，结论以方向性为主，不抠零点几的差距。", options:{ color:C.ink, fontSize:11 } },
], { x:0.92, y:6.12, w:11.5, h:0.72, fontFace:FB, valign:"middle", lineSpacingMultiple:1.04, margin:0 });
pageno(s);

// ============================================================ 基准结果：患者内 Spearman（定量主图，头条）
figSlide({
  kicker:"基准结果 · 定量主图", title:"定量能力主指标 — 患者内 Fisher-Z 相关（计入患者差异）", accent:C.sea,
  img:`${FIG}/fig_perpatient_fisherz_5tools_v3.png`,
  noteHead:"读图要点（本报告主指标）",
  notes:[
    "这是本报告判断定量能力的主指标。衡量工具能否把反应的强弱排对，最直接的指标是 Spearman 相关系数。由于不同患者的肽段集合和反应基线差异很大，把所有患者的肽混在一起算一个相关，会让患者之间的差异掩盖真实的排序能力，因此正确的做法是先在每一位患者内部计算相关，再跨患者聚合，这也是与项目主表统一的口径。",
    "这张图就是患者内的口径：先对每位患者单独算 Spearman，再用 Fisher-Z 加权聚合，误差棒是百分之九十五置信区间。",
    "在主测试集 DS2 上，IMPROVE 最高约为零点二五零，PredIG 约为零点二二九，pTuneos 约为零点一二一，NeoTImmuML 约为零点零三三，DeepImmuno 约为零点零一五。在患者内口径下五个工具都为正，但数值普遍偏低，只有 IMPROVE 的置信区间整段落在零以上，其余四个工具的置信区间仍然跨过零。",
    "这说明现有工具的能力主要集中在区分有没有反应，对反应到底有多强的定量预测仍然很弱，而这正是强弱定量这一方向尚待填补的空白。",
  ],
  cite:"评估数据集 DS2 corrected-full · 患者内 Spearman，Fisher-Z 加权聚合，误差棒为 95% 置信区间",
});

// ============================================================ 基准结果：全局 Spearman（对照）
figSlide({
  kicker:"基准结果", title:"全局 Spearman — 不区分患者的对照口径", accent:C.teal,
  img:`${FIG}/fig_spearman_5tools_v3.png`,
  noteHead:"读图要点",
  notes:[
    "作为对照，这张图把所有患者的肽段合并在一起算一个全局 Spearman，统一采用最强结合子（max）聚合，与主表口径一致。这是过去常用的口径，但它没有区分患者，容易受患者间差异干扰。",
    "在全局口径、统一最强结合子（max）聚合下，IMPROVE 约为零点二五二、PredIG 约为零点二零一均达到统计显著（p 分别约为零点零一一、零点零四四），pTuneos 约为零点一一九，NeoTImmuML 约为零点零二二，DeepImmuno 约为负零点零八九。",
    "对比上一页可以看到，DeepImmuno 在全局口径里是负值，但在患者内口径里转为接近零的小正值，说明全局口径确实会因为患者差异给出有偏的结论。",
    "需要注意全局对照口径下 IMPROVE 与 PredIG 都显著，而患者内主口径下只有 IMPROVE 显著；本报告以患者内口径为准来判断定量能力，全局口径仅作对照参考。",
  ],
  cite:"评估数据集 DS2 corrected-full · 全局 Spearman，统一最强结合子（max）聚合，星号表示 p 小于 0.05",
});

// ============================================================ 基准结果：判别力 AUC（参考）
figSlide({
  kicker:"基准结果", title:"判别力 AUC — 作为定量能力的补充参考", accent:C.warn,
  img:`${FIG}/fig_auc_5tools_v3.png`,
  noteHead:"读图要点",
  notes:[
    "作为二分判别能力的补充参考，AUC 衡量工具能不能把有反应和没反应的肽区分开，取零点五相当于随机猜测，取零点七五为一条参考线。",
    "在最优聚合与阈值的口径下，pTuneos 约为零点七七、PredIG 约为零点七六点估相对靠前，IMPROVE 约为零点六八、NeoTImmuML 约为零点六六居中，DeepImmuno 约零点五四仅略高于随机线。",
    "无反应样本只有十一个，工具之间的差距置信区间较宽，因此这里只给点估，不下最优的判断。",
    "需要强调的是，判别力高并不等于能定量排出强弱，所以 AUC 始终只作参考，本项目的核心指标是上面两页的 Spearman。",
  ],
  cite:"评估数据集 DS2 corrected-full · 每工具取最高 AUC 的聚合方式与阈值组合",
});

// ============================================================ 基准结果：判别力 ROC 曲线（参考）
figSlide({
  kicker:"基准结果", title:"判别力 ROC 曲线 — 多数贴近随机对角线", accent:C.warn,
  img:`${FIG}/fig_roc_5tools_v3.png`,
  noteHead:"读图要点",
  notes:[
    "ROC 曲线把判别力画成一条线，曲线越凸向左上角代表判别力越强，越贴近对角线代表越接近随机猜测。",
    "pTuneos 约零点七二、PredIG 约零点六六、NeoTImmuML 约零点六六的曲线相对凸向左上，IMPROVE 约零点六二居中，DeepImmuno 约零点四七则基本缠绕在对角线附近。",
    "这与 AUC 柱状图互相印证，只有少数工具具备一定的二分判别力，且都谈不上强。",
  ],
  cite:"评估数据集 DS2 corrected-full · 肽级最大分聚合，Elispot 大于零为阳性",
});

// ============================================================ 基准结果：工具间一致性热图（参考）
figSlide({
  kicker:"基准结果", title:"工具之间一致吗 — 彼此基本不相关", accent:C.teal,
  img:`${FIG}/fig_consistency_5tools_v3.png`,
  noteHead:"读图要点",
  notes:[
    "这张热力图把五个工具在同一批肽段上的打分两两做 Spearman 相关，颜色越绿代表越正相关，越红代表越负相关，对角线是工具与自身的相关恒为一。",
    "对角线以外的格子大多接近零，说明不同工具对同一条肽给出的排序基本各说各话。",
    "其中只有少数几对略高，可能是方法或训练数据有重叠所致；工具之间缺乏共识，意味着没有哪一个能当作公认标准，简单做平均集成提升也有限。",
  ],
  cite:"评估数据集 DS2 corrected-full，101 条肽 · 肽级分数两两 Spearman 相关",
});

// ============================================================ 基准结果：按肽长分层 AUC（参考）
figSlide({
  kicker:"基准结果", title:"按肽长分层的判别力 AUC — 看是否跨肽长稳健", accent:C.warn,
  img:`${FIG}/fig_lenstrat_5tools_v3.png`,
  noteHead:"读图要点",
  notes:[
    "把肽段按长度分成几个区间，分别看各工具的 AUC，可以检查判别力是不是只在某个肽长上成立。",
    "整体看，工具的判别力在不同肽长区间并不稳定，随机线上下波动，没有哪个工具在所有区间都明显优于随机。",
    "样本被分层后每个区间更小，这张图只作稳健性的参考，不用来下定论。",
  ],
  cite:"评估数据集 DS2 corrected-full · 按肽长分层，AUC 仅作参考",
});

// ============================================================ 诚实边界与许可
s = pres.addSlide();
header(s, "诚实边界", "已知限制与口径说明", C.warn);
const cav = [
  ["样本量较小","无反应样本仅十一个，AUC 和相关的置信区间偏宽，工具间小于零点零五的 AUC 差距不具显著性。",C.crit],
  ["数据存在聚集","一百零一条肽来自九个病人，部分病人贡献较多阴性肽，有效样本数小于一百零一，判别力可能部分反映区分病人的能力。",C.warn],
  ["完整度分级","DeepImmuno 和 PredIG 完整端到端双验证，pTuneos 为识别子模型且与官方对账一致，IMPROVE 特征链降级，NeoTImmuML 为自训版非官方权重，结论按此口径解读。",C.teal],
  ["聚合口径","本报告统一采用最大值聚合，与全项目其它交付一致，换成 mean 或 top3mean 点估略有差异，但多数工具判别力偏弱、定量相关弱的总体结论一致。",C.sea],
];
let cy2=1.85;
cav.forEach(c=>{
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:cy2, w:7.9, h:1.2, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:cy2, w:0.09, h:1.2, fill:{color:c[2]} });
  s.addText(c[0], { x:0.98, y:cy2+0.14, w:2.0, h:0.95, fontFace:FH, fontSize:13, bold:true, color:c[2], valign:"top", margin:0 });
  s.addText(c[1], { x:2.95, y:cy2+0.12, w:5.5, h:0.98, fontFace:FB, fontSize:10.5, color:C.ink, valign:"middle", lineSpacingMultiple:1.04, margin:0 });
  cy2 += 1.3;
});
s.addShape(pres.shapes.RECTANGLE, { x:8.8, y:1.85, w:3.95, h:5.0, fill:{color:"4A1F24"}, shadow:sh() });
s.addText("许可提示", { x:9.05, y:2.05, w:3.5, h:0.4, fontFace:FH, fontSize:16, bold:true, color:"F2C2C7", margin:0 });
s.addText([
  { text:"netMHCpan 与 netMHCstabpan", options:{ bold:true, color:"FFFFFF", fontSize:12.5, breakLine:true } },
  { text:"为 DTU 学术许可，未经书面同意，不得向第三方发布在其软件上跑出的结果，包含数字。", options:{ color:"F2C2C7", fontSize:11, breakLine:true, paraSpaceAfter:14 } },
  { text:"pTuneos 与 IMPROVE 依赖上述工具", options:{ bold:true, color:"FFFFFF", fontSize:12.5, breakLine:true } },
  { text:"对外报告含相关对比数字前，需先取得 DTU 书面同意，在投稿阶段处理。", options:{ color:"F2C2C7", fontSize:11 } },
], { x:9.05, y:2.55, w:3.55, h:4.1, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
pageno(s);

// ============================================================ 参考文献（DOI 与代码仓库可点击）
s = pres.addSlide();
header(s, "参考文献", "五个工具的论文出处与代码仓库");
const refs = [
  ["DeepImmuno","Briefings in Bioinformatics 2021","10.1093/bib/bbab160","github.com/frankligy/DeepImmuno"],
  ["PredIG","Genome Medicine 2025","10.1186/s13073-025-01569-8","github.com/BSC-CNS-EAPM/PredIG"],
  ["pTuneos","Genome Medicine 2019","10.1186/s13073-019-0679-x","github.com/bm2-lab/pTuneos"],
  ["IMPROVE","Frontiers in Immunology 2024","10.3389/fimmu.2024.1360281","github.com/SRHgroup/IMPROVE_tool"],
  ["NeoTImmuML","Frontiers in Immunology 2025","10.3389/fimmu.2025.1681396","github.com/01SYan19/NeoTImmuML"],
];
const rh = (t)=>({ text:t, options:{ fill:{color:C.dark}, color:"FFFFFF", bold:true, fontSize:11.5, align:"left", valign:"middle" } });
const rc = (t,b)=>({ text:t, options:{ color:C.ink, fontSize:11, align:"left", valign:"middle", bold:!!b } });
const rcLink = (t,url)=>({ text:t, options:{ color:"1C7293", fontSize:11, align:"left", valign:"middle", hyperlink:{ url, tooltip:url } } });
const reftbl = [[rh(" 工具"), rh("发表期刊与年份"), rh("DOI（可点击）"), rh("代码仓库（可点击）")]];
refs.forEach(r=> reftbl.push([rc(" "+r[0],true), rc(r[1]), rcLink(r[2],"https://doi.org/"+r[2]), rcLink(r[3],"https://"+r[3].split(" ")[0])]));
s.addTable(reftbl, { x:0.7, y:1.85, w:11.95, colW:[2.05,3.1,2.85,3.95],
  rowH:[0.5,0.6,0.6,0.6,0.6,0.6], border:{pt:1,color:C.line}, align:"left", valign:"middle", fontFace:FB, fill:{color:C.card}, margin:[2,4,2,4] });
s.addText("表中 DOI 与代码仓库均可点击跳转。外部依赖工具包括 netMHCpan 与 netMHCstabpan（DTU Health Tech，学术许可）、MixMHCpred、Ensembl VEP 与 R 语言的 Peptides 包。", { x:0.7, y:5.55, w:11.95, h:0.7, fontFace:FB, fontSize:10.5, color:C.muted, valign:"top", lineSpacingMultiple:1.15, margin:0 });
citeFoot(s, "netMHCpan-4.1 DOI 10.1093/nar/gkaa379 · services.healthtech.dtu.dk/services/NetMHCpan-4.1");
pageno(s);

// ============================================================ 结论与下一步（浅底深字）
s = pres.addSlide();
header(s, "结论与下一步", "总体结论、已知空白与后续计划");
proseCard(s, 0.7, 1.7, 6.45, 5.25, "总体结论", [
  "第一批五个工具已经全部完成部署，每个工具的四类信息都逐一记录齐全。",
  "在统一的 ELISpot 基准上，五个工具对反应强弱的定量能力普遍偏弱。以患者内 Fisher-Z 为主指标衡量，只有 IMPROVE 达到统计显著的正相关（约零点二五零，百分之九十五置信区间不含零），是唯一在患者内主口径下显著的工具；PredIG 接近显著但置信区间下界擦零，其余三个不显著。作为对照的全局相关口径下，IMPROVE 与 PredIG 均显著。二分判别力 AUC 仅作参考，也只有 pTuneos 和 PredIG 点估相对靠前。",
  "这说明现有工具的能力主要停留在区分有没有反应，对反应到底有多强的定量预测仍然是一块明确的空白，也正是后续自研工具立项的价值所在。",
], C.sea);
const ns=[
  ["扩充阴性样本","目前无反应样本只有十一个，补充到三十个以上后重新评测，可以让结论更稳。"],
  ["统一多聚合口径","补充最大值之外的 mean 与 top3mean 口径作对照，确认结论稳健。"],
  ["核连续标签数据量","评估公开库中带反应强度标签的数据，是否足以支撑定量回归。"],
  ["接入正式数据","正式数据到位后，按各工具格式转换并正式测试。"],
  ["对外许可","对外报告包含 netMHCpan 相关数字之前，先取得 DTU 书面同意。"],
];
s.addText("下一步", { x:7.4, y:1.72, w:5.2, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.warn, margin:0 });
let ny=2.25;
ns.forEach(g=>{
  s.addShape(pres.shapes.RECTANGLE, { x:7.4, y:ny, w:5.23, h:0.86, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:7.4, y:ny, w:0.08, h:0.86, fill:{color:C.warn} });
  s.addText(g[0], { x:7.65, y:ny+0.1, w:4.85, h:0.32, fontFace:FH, fontSize:12.5, bold:true, color:C.ink, margin:0 });
  s.addText(g[1], { x:7.65, y:ny+0.42, w:4.85, h:0.4, fontFace:FB, fontSize:9.5, color:C.muted, valign:"top", lineSpacingMultiple:1.0, margin:0 });
  ny += 0.95;
});
citeFoot(s, "netMHCpan-4.1 DOI 10.1093/nar/gkaa379 · 基准数字经 analysis/metrics_ds2_16tools.csv 核对 · 逐工具四类信息见 TOOLS 目录");
pageno(s);

// ---------- write ----------
pres.writeFile({ fileName: "D:/YJ-Agent/project/meeting/QuantImmuBench/QuantImmuBench_5工具横评_2026-06-28.pptx" })
  .then(f=>console.log("WROTE", f, "pages", _PG))
  .catch(e=>{ console.error("ERR", e); process.exit(1); });
