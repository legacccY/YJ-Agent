// QuantImmuBench — 5 工具客观版横评报告 (2026-06-25)
// 范围：第一批 5 工具 DeepImmuno / PredIG / pTuneos / IMPROVE / NeoTImmuML
// 每工具：工作原理页(输入→模型→输出) + 4类信息页 + 实测命令/IO 代码框
// benchmark：5 工具 ELISpot 评估，统一 max 聚合口径（与 10 工具 deck / 全项目交付同口径），图=fig6/7/8_5tools（plot_5tools_max.py）
// 客观中立：无第一人称主观字眼（不出现「我/我负责/汇报人」）；外部工具标论文+DOI+repo；MHLAPre 不在 5 工具范围
// 数字均经 analysis/metrics_ds2.csv 核对。运行: NODE_PATH=<global> node gen_ppt_5tools.js
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "新抗原免疫原性预测工具 5 工具部署测试与基准评估报告";

const W = 13.33, H = 7.5;
const C = {
  dark:"0B3C49", teal:"028090", sea:"00A896", mint:"02C39A",
  light:"F2F7F7", card:"FFFFFF", ink:"16323A", muted:"5E7B83",
  line:"D5E3E4", warn:"C9743D", ok:"00A896", crit:"B23A48", gray:"8A9BA0",
};
const FH = "Microsoft YaHei", FB = "Microsoft YaHei", FM = "Consolas";
const FIG   = "D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/figures";
const FIGRV = "D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/figures_R_v3";
const FIGROOT = "D:/YJ-Agent/project/meeting/QuantImmuBench/figures";
const sh = () => ({ type:"outer", color:"0B3C49", blur:9, offset:3, angle:135, opacity:0.12 });

let _PG = 1; // 封面=1 不显示
function header(slide, kicker, title, accent=C.teal){
  slide.background = { color: C.light };
  slide.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:0.28, h:H, fill:{color:accent} });
  slide.addText(kicker.toUpperCase(), { x:0.7, y:0.42, w:11, h:0.3, fontFace:FB, fontSize:12, color:accent, bold:true, charSpacing:3, margin:0 });
  slide.addText(title, { x:0.7, y:0.72, w:12, h:0.7, fontFace:FH, fontSize:26, color:C.ink, bold:true, margin:0 });
}
function pageno(slide){ _PG++; slide.addText(String(_PG), { x:W-0.8, y:H-0.5, w:0.5, h:0.3, fontFace:FB, fontSize:11, color:C.muted, align:"right", margin:0 }); }
function infoCard(slide, x, y, w, h, head, lines, accent){
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill:{color:C.card}, line:{color:C.line, width:1}, shadow:sh() });
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w:0.09, h, fill:{color:accent} });
  slide.addText(head, { x:x+0.28, y:y+0.16, w:w-0.4, h:0.34, fontFace:FH, fontSize:15, bold:true, color:accent, margin:0 });
  const rt = lines.map((t)=>({ text:t, options:{ bullet:{indent:12}, breakLine:true, color:C.ink, fontSize:11.5, paraSpaceAfter:5 } }));
  slide.addText(rt, { x:x+0.3, y:y+0.58, w:w-0.55, h:h-0.7, fontFace:FB, valign:"top", margin:0 });
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
    const gm=p.match(/(github\.com\/\S+|hlathena\.tools\S*)/);
    if(dm) opt={ color:"1C7293", fontSize:9, hyperlink:{ url:"https://doi.org/"+dm[1], tooltip:"DOI" } };
    else if(gm) opt={ color:"1C7293", fontSize:9, hyperlink:{ url:"https://"+gm[1], tooltip:"repo" } };
    runs.push({ text:(i>0?" · ":"")+p, options:opt });
  });
  slide.addText(runs, { x:0.7, y:7.08, w:11.4, h:0.34, fontFace:FB, italic:true, valign:"top", margin:0 });
}
function codeBox(slide, x, y, w, h, head, lines){
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius:0.06, fill:{color:C.dark}, shadow:sh() });
  slide.addText(head, { x:x+0.2, y:y+0.12, w:w-0.4, h:0.3, fontFace:FB, fontSize:12, bold:true, color:C.mint, margin:0 });
  const rt = lines.map((t)=>({ text:t, options:{ breakLine:true, color:"D6F2EC", fontSize:9, paraSpaceAfter:1 } }));
  slide.addText(rt, { x:x+0.22, y:y+0.46, w:w-0.4, h:h-0.55, fontFace:FM, valign:"top", margin:0 });
}
// 工作原理页（输入→模型→输出 + 命令/输入/输出 代码框）
function principleSlide(o){
  const s = pres.addSlide();
  header(s, "工具 "+o.idx+" / 5 · 工作原理", o.name, o.accent);
  s.addText(o.sub, { x:0.7, y:1.46, w:11.8, h:0.5, fontFace:FB, fontSize:13, color:C.muted, margin:0 });
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:1.95, w:5.85, h:5.0, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  const stages = [["① 用什么输入", o.inP], ["② 模型怎么算", o.modelP], ["③ 给出什么输出", o.outP]];
  let sy = 2.2;
  stages.forEach(st=>{
    s.addText(st[0], { x:0.95, y:sy, w:5.4, h:0.34, fontFace:FH, fontSize:14, bold:true, color:o.accent, margin:0 });
    s.addText(st[1], { x:0.95, y:sy+0.38, w:5.4, h:1.15, fontFace:FB, fontSize:12, color:C.ink, valign:"top", lineSpacingMultiple:1.15, margin:0 });
    sy += 1.6;
  });
  codeBox(s, 6.85, 1.95, 5.75, 1.62, "运行命令", o.cmd);
  codeBox(s, 6.85, 3.72, 5.75, 1.55, "输入数据样例", o.inFmt);
  codeBox(s, 6.85, 5.42, 5.75, 1.5, o.unfinished?"输出数据样例（未做成·无输出）":"输出数据样例", o.outFmt);
  citeFoot(s, o.cite);
  pageno(s);
}
// 4类信息页
function toolSlide(o){
  const s = pres.addSlide();
  header(s, "工具 "+o.idx+" / 5 · 四类信息", o.name, o.accent);
  s.addText(o.tagline, { x:0.7, y:1.46, w:8.6, h:0.5, fontFace:FB, fontSize:13, color:C.muted, margin:0 });
  badge(s, W-3.2, 0.72, o.status, o.statusCol, 2.5);
  s.addText("方法  "+o.method, { x:W-3.2, y:1.22, w:2.5, h:0.3, fontFace:FB, fontSize:11, color:C.teal, bold:true, align:"center", margin:0 });
  const cx=0.7, cy=2.0, cw=6.0, ch=2.28, gap=0.3;
  infoCard(s, cx,        cy,        cw, ch, "① 输入数据 / 格式", o.input,  o.accent);
  infoCard(s, cx+cw+gap, cy,        cw, ch, "② 运行参数",       o.params, o.accent);
  infoCard(s, cx,        cy+ch+gap, cw, ch, "③ 输出格式 / 含义", o.output, o.accent);
  infoCard(s, cx+cw+gap, cy+ch+gap, cw, ch, "④ 简介 / 特点优势", o.intro,  o.accent);
  citeFoot(s, o.cite);
  pageno(s);
}

// ============================================================ 封面（客观，无第一人称）
let s = pres.addSlide();
s.background = { color: C.dark };
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.mint} });
s.addShape(pres.shapes.OVAL, { x:W-3.3, y:-1.6, w:4.6, h:4.6, fill:{color:C.teal, transparency:78} });
s.addShape(pres.shapes.OVAL, { x:W-2.0, y:3.6,  w:3.2, h:3.2, fill:{color:C.sea,  transparency:82} });
s.addText("癌症个性化新抗原疫苗 · 预测工具部署与基准评估", { x:0.9, y:1.5, w:11, h:0.4, fontFace:FB, fontSize:15, color:C.mint, bold:true, charSpacing:2, margin:0 });
s.addText("新抗原免疫原性预测工具\n部署测试与基准评估报告", { x:0.9, y:2.05, w:11.5, h:1.8, fontFace:FH, fontSize:42, bold:true, color:"FFFFFF", lineSpacingMultiple:1.05, margin:0 });
s.addText("第一批 5 工具：DeepImmuno · PredIG · pTuneos · IMPROVE · NeoTImmuML", { x:0.9, y:4.25, w:11.5, h:0.5, fontFace:FB, fontSize:15, color:"CADCFC", margin:0 });
s.addShape(pres.shapes.LINE, { x:0.95, y:5.1, w:3.2, h:0, line:{color:C.mint, width:2} });
s.addText([
  { text:"内容  ", options:{ color:"8FB7BD", fontSize:13 } },
  { text:"逐工具部署 + 工作原理 + 四类信息 · ELISpot 统一基准评估", options:{ color:"FFFFFF", fontSize:13, breakLine:true } },
  { text:"项目  ", options:{ color:"8FB7BD", fontSize:13 } },
  { text:"癌症新抗原疫苗协作项目", options:{ color:"FFFFFF", fontSize:13 } },
], { x:0.95, y:5.35, w:9.5, h:1.0, fontFace:FB, valign:"top", margin:0 });
s.addText("2026-06-25", { x:W-2.4, y:6.7, w:1.8, h:0.3, fontFace:FB, fontSize:12, color:"8FB7BD", align:"right", margin:0 });

// ============================================================ 目录
s = pres.addSlide();
header(s, "目录", "本报告的内容结构");
const toc = [
  ["01","项目背景与任务","要解决什么、本报告做了什么"],
  ["02","工具逐一解析","每个工具的工作原理 + 四类信息"],
  ["03","部署工程与踩坑","环境、典型问题与解决（按工具归属）"],
  ["04","数据与评测方法","测试数据来源、评测流程、指标说明"],
  ["05","基准结果","判别力 / 能否定量 / 工具间一致性"],
  ["06","诚实边界与许可","已知限制、口径、许可红线"],
  ["07","结论与下一步","总结与后续计划"],
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

// ============================================================ 背景（客观）
s = pres.addSlide();
header(s, "项目背景", "目标 · 报告范围 · 四类信息");
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:1.7, w:5.55, h:3.05, fill:{color:C.dark}, shadow:sh() });
s.addText("项目目标", { x:0.98, y:1.95, w:5, h:0.4, fontFace:FH, fontSize:17, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"构建一个能预测 T 细胞反应 ", options:{ color:"FFFFFF", fontSize:14 } },
  { text:"「强弱程度」", options:{ color:C.mint, fontSize:17, bold:true } },
  { text:" 的工具。", options:{ color:"FFFFFF", fontSize:14, breakLine:true } },
  { text:"现有工具多数只判断「是否具有免疫原性」（二分类）；目标是更进一步，给出反应强度的连续估计（定量）。", options:{ color:"CADCFC", fontSize:12.5, breakLine:true } },
], { x:0.98, y:2.42, w:5.05, h:2.2, fontFace:FB, valign:"top", lineSpacingMultiple:1.18, margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:4.95, w:5.55, h:2.05, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addText("本报告范围", { x:0.95, y:5.08, w:5, h:0.34, fontFace:FH, fontSize:14, bold:true, color:C.teal, margin:0 });
s.addText([
  { text:"对第一批 5 个现有免疫原性预测工具完成部署与运行测试，", options:{ color:C.ink, fontSize:12, breakLine:true } },
  { text:"在统一的 ELISpot 实验数据上做横向基准评估，", options:{ color:C.ink, fontSize:12, breakLine:true, paraSpaceAfter:6 } },
  { text:"每个工具记录 4 类信息并整理成本报告。", options:{ color:C.dark, fontSize:12, bold:true } },
], { x:0.95, y:5.46, w:5.2, h:1.5, fontFace:FB, valign:"top", lineSpacingMultiple:1.1, margin:0 });
s.addText("每个工具记录的 4 类信息", { x:6.7, y:1.78, w:6, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.ink, margin:0 });
const items = [
  ["①","输入数据格式","文件格式、必填列、肽段长度、HLA 写法"],
  ["②","运行参数","可调参数及其功能、运行模式"],
  ["③","输出数据含义","关键列、分数类型、能否定量强弱"],
  ["④","工具简介","所用方法、特点、优势与限制"],
];
let yy=2.3;
items.forEach(it=>{
  s.addShape(pres.shapes.RECTANGLE, { x:6.7, y:yy, w:5.9, h:0.92, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.OVAL, { x:6.86, y:yy+0.23, w:0.46, h:0.46, fill:{color:C.teal} });
  s.addText(it[0], { x:6.86, y:yy+0.23, w:0.46, h:0.46, fontFace:FH, fontSize:16, bold:true, color:"FFFFFF", align:"center", valign:"middle", margin:0 });
  s.addText(it[1], { x:7.5, y:yy+0.14, w:4.9, h:0.34, fontFace:FH, fontSize:13.5, bold:true, color:C.ink, margin:0 });
  s.addText(it[2], { x:7.5, y:yy+0.5, w:4.9, h:0.34, fontFace:FB, fontSize:10.5, color:C.muted, margin:0 });
  yy += 1.04;
});
s.addShape(pres.shapes.RECTANGLE, { x:6.7, y:6.5, w:5.9, h:0.5, fill:{color:"E6F4F1"}, line:{color:C.sea,width:1} });
s.addText("5 个工具均完成部署并产出可进入基准的连续分数；端到端完整度分级见下页。", { x:6.92, y:6.52, w:5.6, h:0.46, fontFace:FB, fontSize:11, bold:true, color:C.dark, valign:"middle", margin:0 });
pageno(s);

// ============================================================ 5 工具横评总表
s = pres.addSlide();
header(s, "总览", "5 个工具：方法 · 端到端完整度 · 基准判别力");
const hd = (t)=>({ text:t, options:{ fill:{color:C.dark}, color:"FFFFFF", bold:true, fontSize:12, align:"center", valign:"middle" } });
const cc = (t,col)=>({ text:t, options:{ color:col||C.ink, fontSize:11, align:"center", valign:"middle" } });
const cl = (t)=>({ text:t, options:{ color:C.ink, fontSize:11.5, bold:true, align:"left", valign:"middle" } });
const rows = [
  [hd("工具"), hd("方法"), hd("能否定量"), hd("基准 AUC*"), hd("端到端完整度")],
  [cl("DeepImmuno"),  cc("卷积网络 CNN"),   cc("连续 0–1",C.ok), cc("0.481",C.ink), cc("完整端到端",C.ok)],
  [cl("PredIG"),      cc("梯度提升树"),     cc("连续 0–1",C.ok), cc("0.661",C.ink), cc("完整端到端",C.ok)],
  [cl("pTuneos"),     cc("机器学习流程"),   cc("排名分",C.ok),   cc("0.752",C.ink), cc("子模型 (对账 r=1.0)",C.warn)],
  [cl("IMPROVE"),     cc("随机森林"),       cc("连续 0–1",C.ok), cc("0.621",C.ink), cc("特征降级",C.warn)],
  [cl("NeoTImmuML ★"),cc("集成机器学习"),   cc("概率",C.ok),     cc("0.655",C.ink), cc("自训版 (非官方权重)",C.warn)],
];
s.addTable(rows, { x:0.7, y:1.85, w:11.9, colW:[2.3,2.6,1.9,1.7,3.4],
  rowH:[0.5,0.62,0.62,0.62,0.62,0.62], border:{pt:1,color:C.line}, align:"center", valign:"middle", fontFace:FB, fill:{color:C.card} });
s.addText([
  { text:"* 基准 AUC = ELISpot 测试集 DS2、max 聚合、阈值>0 口径下的判别力（0.5=随机，与全项目其它交付同口径）。完整数字见 analysis/metrics_ds2.csv。", options:{ color:C.muted, fontSize:9.5, italic:true, breakLine:true } },
  { text:"★ NeoTImmuML：官方未发布预训练权重，基准使用基于公开数据自训的版本，数值不对标原论文。「端到端完整度」三档：完整双验证 / 子模型 / 降级或自训，均不影响进入基准，仅口径需说明。", options:{ color:C.ink, fontSize:9.5, breakLine:true } },
], { x:0.7, y:5.75, w:11.9, h:0.95, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
pageno(s);

// ============================================================ 逐工具：原理页 + 4类信息页 ×5
// 1 DeepImmuno
principleSlide({ idx:1, name:"DeepImmuno", accent:"028090",
  sub:"用卷积神经网络判断一条肽段能不能激活 CD8+ T 细胞",
  inP:"只要两样东西：一条肽段序列（9 或 10 个氨基酸）和它对应的 HLA 分型。不需要基因组、不需要表达量，是十个工具里最省事的。",
  modelP:"先把氨基酸序列和 HLA 假基序按物化性质编码成一张数字矩阵，再用卷积神经网络（CNN）像扫图像一样扫过这张矩阵，自动抓出和免疫原性有关的局部模式，最后汇总成一个分数。",
  outP:"输出一个 0 到 1 之间的连续分，越接近 1 表示越可能激活 T 细胞。实测已知强表位（如 CMV 的 NLVPMVATV）确实拿到高分，符合预期。",
  cmd:["# 单条", "python deepimmuno-cnn.py \\", "  --mode single \\", "  --epitope NLVPMVATV --hla HLA-A*0201", "# 批量", "#   --mode multiple --intdir IN --outdir OUT"],
  inFmt:["# CSV，两列，无表头", "# 肽段, HLA", "NLVPMVATV,HLA-A*0201", "GILGFVFTL,HLA-A*0201"],
  outFmt:["peptide    HLA          immunogenicity", "NLVPMVATV  HLA-A*0201   0.957", "GILGFVFTL  HLA-A*0201   0.887"],
  cite:"DeepImmuno, Briefings in Bioinformatics 2021 · DOI 10.1093/bib/bbab160 · github.com/frankligy/DeepImmuno" });
toolSlide({ idx:1, name:"DeepImmuno", accent:"028090", method:"卷积网络 CNN", status:"✅ 完整端到端", statusCol:C.ok,
  tagline:"用卷积神经网络判断一条肽段能否激活 CD8+ T 细胞（HLA-I），最轻量、只要肽段+HLA",
  input:[ "CSV，两列无表头  peptide, HLA", "肽段长度固定 9 或 10", "HLA 写法  HLA-A*0201", "不需要基因组 / HLA 库" ],
  params:[ "--mode single  单条，结果打印屏幕", "--mode multiple  批量，指定输入输出目录", "没有可调超参；须在 repo 根目录运行" ],
  output:[ "三列  peptide / HLA / immunogenicity", "immunogenicity = 0~1 连续分，越高越强", "实测已知强表位高分（CMV NLVPMVATV=0.957）→ 合理" ],
  intro:[ "最省事：纯肽段+HLA 就能跑，不依赖任何收费工具，CPU 即可", "环境：Python3.8 + TensorFlow2.3（protobuf 须降到 3.20）", "限制：肽长只能 9 或 10" ],
  cite:"DeepImmuno, Briefings in Bioinformatics 2021 · DOI 10.1093/bib/bbab160 · github.com/frankligy/DeepImmuno" });
// 2 PredIG
principleSlide({ idx:2, name:"PredIG", accent:"1C7293",
  sub:"用梯度提升树预测免疫原性，并给出一串可解释的特征",
  inP:"输入肽段、HLA 分型，以及（重组模式下）肽段所在的蛋白序列。支持三种输入模式，肽段长度 8–14。",
  modelP:"先调用一串内置工具算出 13 类特征——蛋白酶切位点、提呈分（NOAH）、物化性质、TCR 接触位点等——再把这些特征喂给 XGBoost 梯度提升树模型综合打分。特征可解释是它的卖点。",
  outP:"输出一个 0 到 1 的免疫原性分（PredIG 列），同时附上那 13 列特征，方便回看模型是凭什么给的分。",
  cmd:["python predig.py \\", "  --type recombinant \\", "  --modelXG neoant \\", "  -i input.csv \\", "  -o result.csv"],
  inFmt:["# CSV，重组模式", "epitope,HLA_allele,protein_seq,protein_name", "SLLMWITQV,HLA-A*0201,MSLL...,TP53"],
  outFmt:["# CSV，含 PredIG 分 + 13 列特征", "epitope    PredIG   NOAH   TCR_contact", "SLLMWITQV  0.0061   0.42   ..."],
  cite:"PredIG, Genome Medicine 2025 · DOI 10.1186/s13073-025-01569-8 · github.com/BSC-CNS-EAPM/PredIG" });
toolSlide({ idx:2, name:"PredIG", accent:"1C7293", method:"梯度提升树 XGBoost", status:"✅ 完整端到端", statusCol:C.ok,
  tagline:"用梯度提升树预测 T 细胞表位免疫原性，按抗原类型分专用模型，结果可解释",
  input:[ "3 种模式：Uniprot / Recombinant / FASTA", "Recombinant 列  epitope, HLA_allele, protein_seq, protein_name", "肽段 8–14 个氨基酸" ],
  params:[ "--modelXG  选模型（neoant / noncan / 自定义）", "--type  选输入模式", "-o  输出文件" ],
  output:[ "CSV，PredIG 列 = 0~1 连续免疫原性分", "另附 13 列特征（切割/提呈/物化/TCR 接触等）", "实测 SLLMWITQV = 0.0061" ],
  intro:[ "连续分 + 可解释特征 + 容器化（依赖全打包，省去装环境）", "环境：官方 Docker（14.4G）→ HPC 转 Singularity（4.6G）", "限制：镜像体积大" ],
  cite:"PredIG, Genome Medicine 2025 · DOI 10.1186/s13073-025-01569-8 · github.com/BSC-CNS-EAPM/PredIG" });
// 3 pTuneos
principleSlide({ idx:3, name:"pTuneos", accent:"028090",
  sub:"一整套新抗原流程；其中识别子模型可单独给肽段打分",
  inP:"完整流程要测序变异（VCF）、表达量、拷贝数、肿瘤纯度、HLA——需要全基因组数据，喂不了纯肽段。但它的识别子模型 Pre&RecNeo 只要三列：突变肽、对应野生肽、HLA，这部分能用来跑 ELISpot 肽段。",
  modelP:"完整流程先把测序变异注释成突变肽，再逐层打分；识别子模型则针对一对「突变肽 vs 野生肽」算结合、相似度、被 T 细胞识别等特征，输出免疫识别分。本基准用的就是这个子模型。",
  outP:"完整流程给患者级排名分（乘了表达量和突变频率，需测序）；子模型给纯肽免疫识别分，这部分可与其它工具横比。实测示例数据端到端跑出 40 个候选新抗原。",
  cmd:["# 完整流程", "python pTuneos.py VCF -i config.yaml", "# 识别子模型（喂肽段）", "# 自写脚本调用 InVivoModelAndScore"],
  inFmt:["# 子模型输入：三列", "MT_pep,     WT_pep,     HLA", "AAAVFKTLP,  AAAVFKTLR,  HLA-A*02:01"],
  outFmt:["# 子模型识别分 model_pro", "MT_pep      model_pro", "AAAVFKTLP   0.73"],
  cite:"pTuneos, Genome Medicine 2019 · DOI 10.1186/s13073-019-0679-x · github.com/bm2-lab/pTuneos" });
toolSlide({ idx:3, name:"pTuneos", accent:"028090", method:"机器学习流程", status:"⚠️ 子模型端到端", statusCol:C.warn,
  tagline:"一整套个性化新抗原流程（从测序数据到排名）；识别子模型可单独拿肽段来打分",
  input:[ "完整流程：测序变异 + 表达量 + 拷贝数 + 纯度 + HLA（要全基因组，喂不了纯肽）", "★ 识别子模型：只要 突变肽 + 野生肽 + HLA 三列（能跑 ELISpot 肽）" ],
  params:[ "完整：python pTuneos.py  +  配置文件", "子模型：自写脚本调用识别打分函数", "可并行加速（多进程 + 批量结合预测）" ],
  output:[ "完整流程出患者级排名分（乘了表达/突变频率，需测序）", "子模型出纯肽免疫原性识别分 → 这部分进基准、可与其它工具比", "示例数据跑出 40 个候选新抗原" ],
  intro:[ "镜像自带 netMHCpan / VEP / GATK 等全套；修了 8 处坑 + 14G 注释缓存才端到端跑通", "进基准用的是识别子模型，对账官方逻辑一致（r=1.0），不等于整条流程的端到端能力", "完整流程在本地容器跑通；HPC 因权限限制未跑" ],
  cite:"pTuneos, Genome Medicine 2019 · DOI 10.1186/s13073-019-0679-x · github.com/bm2-lab/pTuneos" });
// 4 IMPROVE
principleSlide({ idx:4, name:"IMPROVE", accent:"1C7293",
  sub:"用随机森林给新表位打分，整合了 22 个特征",
  inP:"输入突变肽、对应野生肽、HLA（TSV 格式，肽段 8–12）。流程分两步：先算特征，再预测。",
  modelP:"第一步用外部工具算出 22 个特征（包含结合、稳定性、TCR 识别 PRIME 分、自相似度等）；第二步把特征喂给随机森林（每个变体 5 个森林做集成）综合打分。本基准里表达相关特征因 ELISpot 无 RNA 数据而降级。",
  outP:"在输入表后追加一列 mean_prediction_rf，是多折多森林的集成平均分（0 到 1）。",
  cmd:["# 第一步：算特征", "bash run_feature_calc.sh input.tsv", "# 第二步：预测", "python Predict.py --model Simple"],
  inFmt:["# TSV：突变肽 + 野生肽 + HLA", "Mut_pep     Norm_pep    HLA", "EEFLNSWML   EEFLNSWMV   HLA-B*08:01"],
  outFmt:["# 追加 mean_prediction_rf 列", "Mut_pep     mean_prediction_rf", "EEFLNSWML   0.5146"],
  cite:"IMPROVE, Frontiers in Immunology 2024 · DOI 10.3389/fimmu.2024.1360281 · github.com/SRHgroup/IMPROVE_tool" });
toolSlide({ idx:4, name:"IMPROVE", accent:"1C7293", method:"随机森林", status:"⚠️ 特征降级", statusCol:C.warn,
  tagline:"用随机森林给新表位的免疫原性打分，22 个特征，分三种变体模型",
  input:[ "TSV，必填  突变肽 + 野生肽 + HLA", "肽段 8–12 个氨基酸", "两步走：先算特征，再跑随机森林预测" ],
  params:[ "--model  选 Simple / TME_excluded / TME_included", "每个变体加载 5 个森林做集成" ],
  output:[ "TSV 追加一列  mean_prediction_rf（0~1 连续）", "= 多折 × 多森林的集成平均", "实测 Simple 变体 EEFLNSWML = 0.5146" ],
  intro:[ "22 个特征专为新表位排名设计，整合了 TCR 识别信号", "缺口：ELISpot 没有 RNA 表达量 → 表达相关特征降级；稳定性特征依赖的外部工具受系统库版本所限", "预测步本地+HPC 都跑通；这是「数据缺一块」不是「装不上」" ],
  cite:"IMPROVE, Frontiers in Immunology 2024 · DOI 10.3389/fimmu.2024.1360281 · github.com/SRHgroup/IMPROVE_tool" });
// 5 NeoTImmuML
principleSlide({ idx:5, name:"NeoTImmuML ★ 自训版", accent:"028090",
  sub:"三种模型加权集成，用 78 个肽段物化特征；官方无权重，本基准为自训版",
  inP:"输入肽段加上 78 个物化特征（要先用 R 的 Peptides 包算好），不需要 HLA，肽段 8–13。",
  modelP:"把 78 维特征喂给 LightGBM、XGBoost、随机森林三个模型，再加权集成成一个概率。官方仓库是研究用 notebook、没带预训练权重，所以本基准用公开肿瘤抗原库自己重训了一版（数值不对标原论文）。",
  outP:"输出 0 到 1 的免疫原性概率（predict_proba），能用来排强弱；同时给分类指标和雷达图。",
  cmd:["# 不是命令行，是 Jupyter notebook", "# 改 file_path 指向数据后", "# 顺序运行 21 个单元格", "# （含 8 算法对比 + 加权集成）"],
  inFmt:["# CSV：肽段 + 标签 + 78 特征", "Peptide    label  feat1  feat2 ... feat78", "AAAVFKTLP  1      0.12   -0.4  ..."],
  outFmt:["# predict_proba 连续概率", "Peptide    immuno_prob", "AAAVFKTLP  0.81"],
  cite:"NeoTImmuML, Frontiers in Immunology 2025 · DOI 10.3389/fimmu.2025.1681396 · github.com/01SYan19/NeoTImmuML" });
toolSlide({ idx:5, name:"NeoTImmuML ★ 自训版", accent:"028090", method:"集成机器学习", status:"⚠️ 自训版", statusCol:C.warn,
  tagline:"三种模型加权集成（LightGBM+XGBoost+随机森林）预测肿瘤新抗原免疫原性，用 78 个肽段物化特征",
  input:[ "CSV：肽段 + 标签 + 78 个物化特征", "肽段 8–13 个氨基酸，不需要 HLA", "78 个特征要先用 R 的 Peptides 包算好" ],
  params:[ "不是命令行，是 Jupyter notebook（21 个单元格）", "改路径指向数据；内含 8 种算法对比 + 加权集成 + 交叉验证" ],
  output:[ "分类指标 + 雷达图 + 连续概率（能分强弱）", "★ 官方没放预训练权重 → 基准用自训的版本", "数值不对标原论文精度" ],
  intro:[ "纯肽段特征，不要 HLA、不要任何收费工具，装起来最省心", "限制：是研究用 notebook，没带权重 → 用公开肿瘤抗原库重训了一版", "不含 78 特征的计算代码 → 要自己用 R 算" ],
  cite:"NeoTImmuML, Frontiers in Immunology 2025 · DOI 10.3389/fimmu.2025.1681396 · github.com/01SYan19/NeoTImmuML" });

// ============================================================ 部署工程 + 踩坑（5 工具归属）
s = pres.addSlide();
header(s, "工程", "部署环境与典型技术问题（按工具归属）");
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:1.8, w:4.6, h:4.85, fill:{color:C.dark}, shadow:sh() });
s.addText("部署环境", { x:0.95, y:2.05, w:4, h:0.4, fontFace:FH, fontSize:17, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"本机 WSL2 Ubuntu", options:{ bold:true, color:"FFFFFF", fontSize:13.5, breakLine:true } },
  { text:"调试主场 · 直通显卡 · conda + Docker", options:{ color:"9FD9CF", fontSize:11.5, breakLine:true, paraSpaceAfter:10 } },
  { text:"学校 HPC 集群", options:{ bold:true, color:"FFFFFF", fontSize:13.5, breakLine:true } },
  { text:"最终部署目标 · Singularity 容器", options:{ color:"9FD9CF", fontSize:11.5, breakLine:true, paraSpaceAfter:10 } },
  { text:"出网情况", options:{ bold:true, color:"FFFFFF", fontSize:13.5, breakLine:true } },
  { text:"GitHub / PyPI / DTU 通；Docker Hub 不通", options:{ color:"9FD9CF", fontSize:11.5 } },
], { x:0.95, y:2.5, w:4.15, h:4.0, fontFace:FB, valign:"top", margin:0 });
s.addText("典型的坑与解法（标明工具）", { x:5.6, y:1.9, w:7, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.ink, margin:0 });
const pit = [
  ["DeepImmuno：版本敏感","protobuf 必须降到 3.20，否则报 Descriptors 错；TF2.3 + Python3.8 严格对版本"],
  ["PredIG：镜像体积大","官方 Docker 14.4G；HPC 不通 Docker Hub → 转 Singularity（4.6G）"],
  ["pTuneos：老链 + 大缓存","老依赖修了 8 处坑 + VEP 注释缓存 14G 才端到端跑通；HPC 因容器权限受限未跑"],
  ["IMPROVE：外部工具受限","稳定性特征依赖的 netMHCstabpan 受系统库版本所限；表达特征因无 RNA 降级"],
  ["NeoTImmuML：无官方权重","研究用 notebook 不带权重 → 用公开数据自训；78 特征需先用 R 算"],
  ["通用：Docker Hub 不通","HPC 出网受限 → 镜像转 Singularity；老二进制改内核兼容配置绕过"],
];
pit.forEach((p,i)=>{
  const col = (i%2===0)? 5.6 : 9.2;
  const yrow = 2.4 + Math.floor(i/2)*1.42;
  s.addShape(pres.shapes.RECTANGLE, { x:col, y:yrow, w:3.4, h:1.28, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:col, y:yrow, w:3.4, h:0.06, fill:{color:C.sea} });
  s.addText(p[0], { x:col+0.18, y:yrow+0.13, w:3.05, h:0.35, fontFace:FH, fontSize:11.5, bold:true, color:C.teal, margin:0 });
  s.addText(p[1], { x:col+0.18, y:yrow+0.5, w:3.08, h:0.72, fontFace:FB, fontSize:9.5, color:C.ink, valign:"top", lineSpacingMultiple:1.04, margin:0 });
});
pageno(s);

// ============================================================ 数据集来源与规模
s = pres.addSlide();
header(s, "测试数据从哪来", "ELISpot 实测数据 · 规模 · 正负比");
const dscards = [
  ["DS2 · 主测试集（有阴有阳）","028090",[
    "101 条肽段：有反应 90 条 / 无反应 11 条",
    "来自 9 位患者；反应值 SFC 范围 −34 ~ 209",
    "用途：算 AUC（能不能分开「有/无反应」）"]],
  ["DS1 · 定量验证集（全阳）","00A896",[
    "82 条肽段：全部有反应，无阴性",
    "来自 6 位患者；强度 SFC 16 ~ 677（约 40 倍跨度）",
    "用途：检验「能不能把强弱排对」"]],
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
  { text:"标签 = ELISpot SFC", options:{ bold:true, color:"FFFFFF", fontSize:12, breakLine:true } },
  { text:"SFC = 斑点形成细胞数，T 细胞反应强度的实验读数；阈值 >0 记为有反应。", options:{ color:"CADCFC", fontSize:10.5, breakLine:true, paraSpaceAfter:10 } },
  { text:"展开规模", options:{ bold:true, color:"FFFFFF", fontSize:12, breakLine:true } },
  { text:"每条肽按子肽×HLA 窗口展开，DS1+DS2 共 34,247 行预测。", options:{ color:"CADCFC", fontSize:10.5, breakLine:true, paraSpaceAfter:10 } },
  { text:"局限", options:{ bold:true, color:"FFFFFF", fontSize:12, breakLine:true } },
  { text:"样本来自有限患者 → 存在聚集；DS2 阴性仅 11 条，置信区间偏宽。", options:{ color:"CADCFC", fontSize:10.5 } },
], { x:8.5, y:2.46, w:3.95, h:3.3, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
s.addText("数据来源：课题组 ELISpot 实测（Elispot_Dataset1.xlsx / Elispot_Dataset2.xlsx）。", { x:0.7, y:6.05, w:7.3, h:0.4, fontFace:FB, fontSize:10, italic:true, color:C.muted, valign:"top", margin:0 });
pageno(s);

// ============================================================ 评测流程图
s = pres.addSlide();
header(s, "评测流程", "从一条肽段到工具横向对比");
const flow = [
  ["肽段输入","DS1 / DS2\n的肽段 + HLA",C.teal],
  ["5 工具打分","各工具独立\n给免疫原性分",C.sea],
  ["聚合","子肽×HLA\n逐肽取 max",C.teal],
  ["切标签","按 SFC>0\n分有/无反应",C.sea],
  ["算指标","AUC / Spearman\n/ PPV / MCC",C.teal],
  ["横向对比","5 工具同口径\n排名与显著性",C.dark],
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
  { text:"同一批肽段喂给 5 个工具 → 每个工具独立打分 → 因一条肽会拆成多个子肽×HLA，统一「逐肽取最大分」聚合 → 按实验反应值 SFC>0 切「有/无反应」标签 → 用同一套指标评估 → 5 个工具在完全相同的口径下横向对比。", options:{ color:C.ink, fontSize:11.5, breakLine:true, paraSpaceAfter:5 } },
  { text:"关键：所有工具走完全一致的聚合、阈值、指标口径，保证「apples-to-apples」可比。", options:{ color:C.dark, fontSize:11.5, bold:true } },
], { x:0.95, y:5.25, w:11.45, h:1.3, fontFace:FB, valign:"top", lineSpacingMultiple:1.08, margin:0 });
pageno(s);

// ============================================================ benchmark 方法
s = pres.addSlide();
header(s, "基准方法", "用什么数据、怎么比、看什么指标");
const mcards = [
  ["测试数据","真实 ELISpot 实验数据 DS2：101 条肽段。按实验反应值切分 —— 有反应 90 条、无反应 11 条（反应值≤0 算真无反应）。","028090"],
  ["参评工具","第一批 5 个免疫原性工具：DeepImmuno / PredIG / pTuneos / IMPROVE / NeoTImmuML。","00A896"],
  ["怎么比","一条肽段拆成多个子肽×HLA，先聚合（统一取 max 最大值，与全项目其它交付同口径）再按阈值切，保证可比。","1C7293"],
  ["看什么","AUC（能否分开「有反应/无反应」，0.5=随机）、AUPRC、Spearman 相关（分数与反应强弱是否同向 = 能否定量）。","028090"],
];
let my=1.85;
mcards.forEach(m=>{
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:my, w:11.9, h:1.18, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:my, w:0.09, h:1.18, fill:{color:m[2]} });
  s.addText(m[0], { x:1.0, y:my+0.16, w:2.4, h:0.85, fontFace:FH, fontSize:15, bold:true, color:m[2], valign:"top", margin:0 });
  s.addText(m[1], { x:3.4, y:my+0.14, w:9.0, h:0.9, fontFace:FB, fontSize:12, color:C.ink, valign:"middle", lineSpacingMultiple:1.05, margin:0 });
  my += 1.28;
});
s.addText("所有数字经 analysis/metrics_ds2.csv 核对（max 聚合, >0）；图表为 5 工具 max 聚合口径，与全项目一致。", { x:0.7, y:6.95, w:11.9, h:0.4, fontFace:FB, fontSize:10.5, italic:true, color:C.muted, margin:0 });
pageno(s);

// ============================================================ 看懂这些指标
s = pres.addSlide();
header(s, "先看懂这些指标", "后面每个数字是什么意思、最该信哪个");
const metricCards = [
  ["AUC（判别力）","随便挑「一条有反应 + 一条没反应」，模型给有反应那条打分更高的概率。","1=完美，0.5=和瞎猜一样，<0.5=反着的。本报告最主要看它。",C.teal,"★ 主看"],
  ["Spearman 相关（能否分强弱）","模型分数的高低排序，和真实反应强弱的排序，吻合到什么程度。","+1=完全同向，0=没关系，−1=完全反着。这是「能不能分强弱」的关键。",C.sea,"★ 看定量"],
  ["AUPRC","精确率-召回率曲线下的面积，阳性很少时比 AUC 更敏感。","⚠️ 本数据阳性本就占 89%，起点就高 → 提升空间小，参考意义有限。",C.warn,"参考有限"],
  ["95% 置信区间 / p 值","重复抽样 2000 次看指标的波动范围；p<0.05 才算「不是偶然」。","区间越宽=越不确定。本数据样本小（101 条、阴性仅 11）→ 区间普遍偏宽。",C.crit,"看可信度"],
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
  { text:"一句话：", options:{ bold:true, color:C.teal, fontSize:11.5 } },
  { text:"本报告主看 AUC（判别力）和 Spearman（能否分强弱）；AUPRC 因阳性占比高、参考有限；样本量小 → 所有指标的置信区间都偏宽，结论以「方向性」为主、不抠零点几的差距。", options:{ color:C.ink, fontSize:11 } },
], { x:0.92, y:6.12, w:11.5, h:0.72, fontFace:FB, valign:"middle", lineSpacingMultiple:1.04, margin:0 });
pageno(s);

// ============================================================ benchmark 结论 AUC (fig2_bar_v3)
s = pres.addSlide();
header(s, "判别力", "5 工具 AUC：除 pTuneos / PredIG 外，多数接近随机", C.warn);
s.addShape(pres.shapes.RECTANGLE, { x:0.6, y:1.65, w:7.5, h:5.2, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIG+"/fig6_5tools_auc.png", x:0.78, y:1.85, w:7.15, h:4.7, sizing:{type:"contain", w:7.15, h:4.7} });
s.addText("图：5 工具 AUC（DS2，max 聚合，阈值>0）+ 95% bootstrap CI。虚线=随机 0.5。pTuneos 0.75、PredIG 0.66 居前；DeepImmuno 0.48 低于随机。", { x:0.62, y:6.6, w:7.5, h:0.4, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", margin:0 });
const pts = [
  ["两个居前","pTuneos（0.75）与 PredIG（0.66）在阈值>0 下判别力点估相对最好；其余三个在 0.48–0.66 之间。",C.teal],
  ["阈值敏感","换更严的阈值（>median），pTuneos 从 0.75 掉到 0.53、DeepImmuno 始终≤0.52 → 多数工具的优势不跨阈值稳健。",C.warn],
  ["样本小须谨慎","无反应样本仅 11 个，工具间的差距置信区间较宽；本页给点估，不下「最优」判断。",C.crit],
];
let py2=1.78;
pts.forEach(p=>{
  s.addShape(pres.shapes.RECTANGLE, { x:8.3, y:py2, w:4.45, h:1.62, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:8.3, y:py2, w:0.09, h:1.62, fill:{color:p[2]} });
  s.addText(p[0], { x:8.5, y:py2+0.12, w:4.2, h:0.34, fontFace:FH, fontSize:14, bold:true, color:p[2], margin:0 });
  s.addText(p[1], { x:8.5, y:py2+0.5, w:4.1, h:1.05, fontFace:FB, fontSize:10.5, color:C.ink, valign:"top", lineSpacingMultiple:1.04, margin:0 });
  py2 += 1.72;
});
pageno(s);

// ============================================================ ROC (fig1_roc_v3)
s = pres.addSlide();
header(s, "判别力 · ROC 曲线", "5 工具 ROC：多数贴近随机对角线");
s.addShape(pres.shapes.RECTANGLE, { x:0.6, y:1.65, w:7.5, h:5.2, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIG+"/fig8_5tools_roc.png", x:0.85, y:1.8, w:7.0, h:4.95, sizing:{type:"contain", w:7.0, h:4.95} });
s.addText("图：5 工具 ROC 曲线（DS2，max 聚合，阈值>0）。曲线越往左上凸=判别力越强；贴近对角线=接近随机。", { x:0.62, y:6.62, w:7.5, h:0.4, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", margin:0 });
const rocp = [
  ["怎么看","曲线离左上角越远 = 判别力越强；贴着对角线 = 与随机猜测相当。",C.teal],
  ["表现","pTuneos、PredIG 的曲线较明显凸向左上；DeepImmuno 等缠绕在对角线附近。",C.warn],
  ["与柱状图一致","与上一页 AUC 柱状图相互印证：仅少数工具具备一定判别力。",C.sea],
];
let ry2=1.8;
rocp.forEach(p=>{
  s.addShape(pres.shapes.RECTANGLE, { x:8.3, y:ry2, w:4.45, h:1.6, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:8.3, y:ry2, w:0.09, h:1.6, fill:{color:p[2]} });
  s.addText(p[0], { x:8.5, y:ry2+0.13, w:4.2, h:0.34, fontFace:FH, fontSize:14, bold:true, color:p[2], margin:0 });
  s.addText(p[1], { x:8.5, y:ry2+0.52, w:4.1, h:1.0, fontFace:FB, fontSize:11, color:C.ink, valign:"top", lineSpacingMultiple:1.05, margin:0 });
  ry2 += 1.7;
});
pageno(s);

// ============================================================ 定量能力 (fig3_scatter_v3 + Spearman + DS1)
s = pres.addSlide();
header(s, "能否定量强弱", "分数与真实反应强度的相关：仅个别工具显著");
s.addShape(pres.shapes.RECTANGLE, { x:0.6, y:1.65, w:7.0, h:5.2, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIG+"/fig7_5tools_spearman.png", x:0.75, y:1.8, w:6.7, h:4.95, sizing:{type:"contain", w:6.7, h:4.95} });
s.addText("图：5 工具 Spearman 相关（max 聚合，分数 vs 反应强度）。* = p<0.05。仅 IMPROVE / PredIG 显著正相关。", { x:0.62, y:6.62, w:7.0, h:0.4, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:7.8, y:1.75, w:4.95, h:2.55, fill:{color:C.dark}, shadow:sh() });
s.addText("Spearman 相关（分数 vs 反应强度）", { x:8.0, y:1.92, w:4.6, h:0.4, fontFace:FH, fontSize:13.5, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"IMPROVE  ρ=0.243（p=0.014，显著）", options:{ breakLine:true, color:"FFFFFF", fontSize:11, paraSpaceAfter:3 } },
  { text:"PredIG  ρ=0.198（p=0.047，显著）", options:{ breakLine:true, color:"FFFFFF", fontSize:11, paraSpaceAfter:3 } },
  { text:"pTuneos ρ=0.136、NeoTImmuML ρ=0.022、DeepImmuno ρ=−0.117 —— 均不显著。", options:{ color:"CADCFC", fontSize:10.5 } },
], { x:8.0, y:2.42, w:4.55, h:1.85, fontFace:FB, valign:"top", lineSpacingMultiple:1.08, margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:7.8, y:4.45, w:4.95, h:2.4, fill:{color:"E6F4F1"}, line:{color:C.sea,width:1} });
s.addText("用全阳数据 DS1 进一步验证", { x:8.0, y:4.58, w:4.6, h:0.36, fontFace:FH, fontSize:13, bold:true, color:C.teal, margin:0 });
s.addText([
  { text:"DS1 = 82 条肽，全部有反应（强度差约 40 倍）。在 DS2 上头部还能正向排强弱的工具，到全阳的 DS1 上相关系数普遍落到 0 附近。", options:{ breakLine:true, color:C.ink, fontSize:10.5, paraSpaceAfter:6 } },
  { text:"说明现有工具的能力集中在「区分有/无反应」，对「反应有多强」的定量预测仍弱 —— 这正是「强弱定量」方向的空白所在。", options:{ color:C.dark, fontSize:10.5, bold:true } },
], { x:8.0, y:4.96, w:4.55, h:1.85, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
pageno(s);

// ============================================================ 工具之间一致性
s = pres.addSlide();
header(s, "工具之间一致吗", "把同一批肽段的打分两两比对：彼此基本不相关");
s.addShape(pres.shapes.RECTANGLE, { x:0.6, y:1.65, w:7.0, h:5.2, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIG+"/fig_corr_heatmap_5tools.png", x:0.78, y:1.82, w:6.65, h:4.9, sizing:{type:"contain", w:6.65, h:4.9} });
s.addText("图：5 工具在同一批肽段（DS2，n=101）上打分的两两 Spearman 相关。颜色越红越正相关，越白越不相关；对角线为自身=1。", { x:0.62, y:6.62, w:7.0, h:0.4, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", margin:0 });
const cpts5 = [
  ["大多互不相关","对角线之外多数格子接近 0 —— 不同工具对同一条肽段给的排序基本各说各话。",C.crit],
  ["少数偏高","IMPROVE–pTuneos 0.31、IMPROVE–PredIG 0.28 略高，可能因方法或训练数据有重叠。",C.warn],
  ["这说明什么","工具之间缺乏共识 → 没有一个是公认标准；简单做平均集成提升也有限。",C.teal],
];
let cpy5=1.8;
cpts5.forEach(p=>{
  s.addShape(pres.shapes.RECTANGLE, { x:7.8, y:cpy5, w:4.95, h:1.6, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:7.8, y:cpy5, w:0.09, h:1.6, fill:{color:p[2]} });
  s.addText(p[0], { x:8.0, y:cpy5+0.13, w:4.7, h:0.34, fontFace:FH, fontSize:14, bold:true, color:p[2], margin:0 });
  s.addText(p[1], { x:8.0, y:cpy5+0.52, w:4.6, h:1.0, fontFace:FB, fontSize:11, color:C.ink, valign:"top", lineSpacingMultiple:1.05, margin:0 });
  cpy5 += 1.7;
});
pageno(s);

// ============================================================ 诚实边界
s = pres.addSlide();
header(s, "诚实边界", "已知限制与口径说明", C.warn);
const cav = [
  ["样本量较小","无反应样本仅 11 个 → AUC/相关的置信区间偏宽，工具间小于 0.05 的 AUC 差距不具显著性。",C.crit],
  ["数据存在聚集","101 条肽来自 9 个病人，部分病人贡献较多阴性肽 → 有效样本数小于 101，判别力可能部分反映「区分病人」。",C.warn],
  ["完整度分级","DeepImmuno / PredIG 完整端到端双验证；pTuneos 为识别子模型（对账 r=1.0）；IMPROVE 特征链降级；NeoTImmuML 为自训版（非官方权重）。结论按此口径解读。",C.teal],
  ["聚合口径","本报告统一采用 max 聚合（与全项目其它交付一致）；换 mean / top3mean 点估略有差异，但「多数工具判别力偏弱、定量相关弱」的总体结论一致。",C.sea],
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
s.addText("⚠️ 许可提示", { x:9.05, y:2.05, w:3.5, h:0.4, fontFace:FH, fontSize:16, bold:true, color:"F2C2C7", margin:0 });
s.addText([
  { text:"netMHCpan / netMHCstabpan", options:{ bold:true, color:"FFFFFF", fontSize:12.5, breakLine:true } },
  { text:"为 DTU 学术许可。未经书面同意，不得向第三方发布在其软件上跑出的结果（含数字）。", options:{ color:"F2C2C7", fontSize:11, breakLine:true, paraSpaceAfter:14 } },
  { text:"pTuneos / IMPROVE 依赖上述工具", options:{ bold:true, color:"FFFFFF", fontSize:12.5, breakLine:true } },
  { text:"→ 对外报告含相关对比数字前，需先取得 DTU 书面同意（投稿阶段处理）。", options:{ color:"F2C2C7", fontSize:11 } },
], { x:9.05, y:2.55, w:3.55, h:4.1, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
pageno(s);

// ============================================================ 参考文献
s = pres.addSlide();
header(s, "参考文献", "5 个工具的论文出处与代码仓库");
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
const reftbl = [[rh(" 工具"), rh("发表期刊 / 年份"), rh("DOI（可点击）"), rh("代码仓库（可点击）")]];
refs.forEach(r=> reftbl.push([rc(" "+r[0],true), rc(r[1]), rcLink(r[2],"https://doi.org/"+r[2]), rcLink(r[3],"https://"+r[3].split(" ")[0])]));
s.addTable(reftbl, { x:0.7, y:1.85, w:11.95, colW:[2.05,3.1,2.85,3.95],
  rowH:[0.5,0.6,0.6,0.6,0.6,0.6], border:{pt:1,color:C.line}, align:"left", valign:"middle", fontFace:FB, fill:{color:C.card}, margin:[2,4,2,4] });
s.addText("外部依赖工具：netMHCpan / netMHCstabpan（DTU Health Tech，学术许可）· MixMHCpred（Gfeller lab）· Ensembl VEP · R Peptides 包。", { x:0.7, y:5.55, w:11.95, h:0.5, fontFace:FB, fontSize:10, italic:true, color:C.muted, valign:"top", margin:0 });
pageno(s);

// ============================================================ 结论（客观）
s = pres.addSlide();
s.background = { color: C.dark };
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.mint} });
s.addText("结论与下一步", { x:0.9, y:0.7, w:10, h:0.7, fontFace:FH, fontSize:32, bold:true, color:"FFFFFF", margin:0 });
s.addText("已完成", { x:0.9, y:1.85, w:5.5, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"5 个工具全部完成部署，四类信息逐工具记录齐全", options:{ bullet:{indent:14}, breakLine:true, color:"FFFFFF", fontSize:13, paraSpaceAfter:8 } },
  { text:"DeepImmuno / PredIG 完整端到端双验证；其余按口径诚实分级", options:{ bullet:{indent:14}, breakLine:true, color:"FFFFFF", fontSize:13, paraSpaceAfter:8 } },
  { text:"ELISpot 基准结论：5 个工具判别力总体偏弱，仅 pTuneos / PredIG 点估居前；定量相关仅 IMPROVE / PredIG 显著", options:{ bullet:{indent:14}, breakLine:true, color:"FFFFFF", fontSize:13, paraSpaceAfter:8 } },
  { text:"现有工具对「反应强弱」的定量预测仍弱 → 该方向存在明确空白与价值", options:{ bullet:{indent:14}, color:C.mint, fontSize:13, bold:true } },
], { x:0.9, y:2.35, w:5.85, h:4.5, fontFace:FB, valign:"top", margin:0 });
s.addText("下一步", { x:7.0, y:1.85, w:5.5, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.warn, margin:0 });
const ns=[
  ["扩充阴性样本","无反应样本仅 11 个 → 补充至 ≥30 后重测，使结论更稳"],
  ["统一多聚合口径","补充 max / top3mean 口径的对照，确认结论稳健"],
  ["核连续标签数据量","评估公开库中带反应强度标签的数据是否足以支撑定量回归"],
  ["接入正式数据","正式数据到位后按各工具格式转换并正式测试"],
  ["对外许可","对外报告含 netMHCpan 相关数字前取 DTU 书面同意"],
];
let ny=2.35;
ns.forEach(g=>{
  s.addShape(pres.shapes.RECTANGLE, { x:7.0, y:ny, w:5.5, h:0.86, fill:{color:"123F4B"}, line:{color:"1C5563",width:1} });
  s.addShape(pres.shapes.RECTANGLE, { x:7.0, y:ny, w:0.08, h:0.86, fill:{color:C.warn} });
  s.addText(g[0], { x:7.25, y:ny+0.1, w:5.1, h:0.32, fontFace:FH, fontSize:12.5, bold:true, color:"FFFFFF", margin:0 });
  s.addText(g[1], { x:7.25, y:ny+0.42, w:5.1, h:0.4, fontFace:FB, fontSize:9.5, color:"9FD9CF", valign:"top", margin:0 });
  ny += 0.96;
});
s.addText("基准数字均经 analysis/metrics_ds2.csv 核对（max 聚合, >0）；逐工具四类信息见 TOOLS/ 目录。", { x:0.9, y:7.05, w:11.5, h:0.35, fontFace:FB, fontSize:9.5, italic:true, color:"6E9AA1", margin:0 });
pageno(s);

// ---------- write ----------
pres.writeFile({ fileName: "D:/YJ-Agent/project/meeting/QuantImmuBench/QuantImmuBench_5工具横评_2026-06-25.pptx" })
  .then(f=>console.log("WROTE", f))
  .catch(e=>{ console.error("ERR", e); process.exit(1); });
