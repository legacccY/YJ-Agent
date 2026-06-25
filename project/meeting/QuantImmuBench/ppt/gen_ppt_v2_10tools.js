// QuantImmuBench 全量交付 PPT v2 (2026-06-25) — 10 工具横评
// 10 工具部署 + 4 类信息(逐工具) + 10工具横评总表 + ELISpot benchmark(8工具+HLAthena proxy) + 参考文献 + 结论
// 约束：说人话 / 不出现具体导师姓名(中性「课题组」) / 外部工具标引用出处(论文+DOI+repo,本地产物不标) / 客观中立
// 所有 benchmark 数字经 analysis/metrics_ds2_*.csv 核对；MHLAPre 无数字=未做成(绝不臆造)；HLAthena=提呈proxy 单列不并比
// 运行: node gen_ppt_v2_10tools.js   (需 npm i pptxgenjs)
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "legacccy";
pres.title = "新抗原免疫原性预测工具 10 工具横评 + Benchmark 报告";

const W = 13.33, H = 7.5;
const C = {
  dark:"0B3C49", teal:"028090", sea:"00A896", mint:"02C39A",
  light:"F2F7F7", card:"FFFFFF", ink:"16323A", muted:"5E7B83",
  line:"D5E3E4", warn:"C9743D", ok:"00A896", crit:"B23A48", gray:"8A9BA0",
};
const FH = "Microsoft YaHei", FB = "Microsoft YaHei";
const FIG  = "D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/figures";
const FIGD = "D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/figures_deepdive";
const sh = () => ({ type:"outer", color:"0B3C49", blur:9, offset:3, angle:135, opacity:0.12 });

function header(slide, kicker, title, accent=C.teal){
  slide.background = { color: C.light };
  slide.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:0.28, h:H, fill:{color:accent} });
  slide.addText(kicker.toUpperCase(), { x:0.7, y:0.42, w:11, h:0.3, fontFace:FB, fontSize:12, color:accent, bold:true, charSpacing:3, margin:0 });
  slide.addText(title, { x:0.7, y:0.72, w:12, h:0.7, fontFace:FH, fontSize:26, color:C.ink, bold:true, margin:0 });
}
let _PG = 1; // 封面=1 不显示
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
// 逐工具 4 类信息卡
function toolSlide(o){
  const s = pres.addSlide();
  header(s, "工具 "+o.idx+" / 10 · 四类信息", o.name, o.accent);
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
  return s;
}

// 逐工具「工作原理」页
function principleSlide(o){
  const s = pres.addSlide();
  header(s, "工具 "+o.idx+" / 10 · 工作原理", o.name, o.accent);
  s.addText(o.sub, { x:0.7, y:1.46, w:11.8, h:0.5, fontFace:FB, fontSize:13, color:C.muted, margin:0 });

  // 左半：白卡 + 三段原理
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:1.95, w:5.85, h:5.0, fill:{color:C.card}, line:{color:C.line, width:1}, shadow:sh() });

  // ① 用什么输入
  s.addText("① 用什么输入", { x:0.98, y:2.1, w:5.3, h:0.32, fontFace:FH, fontSize:12.5, bold:true, color:o.accent, margin:0 });
  s.addText(o.inP, { x:0.98, y:2.44, w:5.3, h:1.35, fontFace:FB, fontSize:12, color:C.ink, valign:"top", lineSpacingMultiple:1.15, margin:0 });

  // ② 模型怎么算
  s.addText("② 模型怎么算", { x:0.98, y:3.85, w:5.3, h:0.32, fontFace:FH, fontSize:12.5, bold:true, color:o.accent, margin:0 });
  s.addText(o.modelP, { x:0.98, y:4.19, w:5.3, h:1.35, fontFace:FB, fontSize:12, color:C.ink, valign:"top", lineSpacingMultiple:1.15, margin:0 });

  // ③ 给出什么输出
  s.addText("③ 给出什么输出", { x:0.98, y:5.6, w:5.3, h:0.32, fontFace:FH, fontSize:12.5, bold:true, color:o.accent, margin:0 });
  s.addText(o.outP, { x:0.98, y:5.94, w:5.3, h:0.9, fontFace:FB, fontSize:12, color:C.ink, valign:"top", lineSpacingMultiple:1.15, margin:0 });

  // 右半：三个代码框
  const codeBlock = (bx, by, bw, bh, label, lines) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x:bx, y:by, w:bw, h:bh, rectRadius:0.08, fill:{color:C.dark} });
    s.addText(label, { x:bx+0.18, y:by+0.1, w:bw-0.3, h:0.3, fontFace:FH, fontSize:12, bold:true, color:C.mint, margin:0 });
    const lineObjs = lines.map((t, i) => ({
      text: t,
      options: { breakLine: i < lines.length-1, color:"D6F2EC", fontSize:9, fontFace:"Consolas" }
    }));
    s.addText(lineObjs, { x:bx+0.18, y:by+0.44, w:bw-0.3, h:bh-0.54, fontFace:"Consolas", fontSize:9, color:"D6F2EC", valign:"top", margin:0 });
  };

  const outLabel = o.unfinished ? "输出数据样例（未做成·无输出）" : "输出数据样例";
  codeBlock(6.85, 1.95, 5.75, 1.6,  "运行命令",    o.cmd);
  codeBlock(6.85, 3.75, 5.75, 1.6,  "输入数据样例", o.inFmt);
  codeBlock(6.85, 5.55, 5.75, 1.4,  outLabel,      o.outFmt);

  citeFoot(s, o.cite);
  pageno(s);
  return s;
}

// ============================================================ S1 封面
let s = pres.addSlide();
s.background = { color: C.dark };
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.mint} });
s.addShape(pres.shapes.OVAL, { x:W-3.3, y:-1.6, w:4.6, h:4.6, fill:{color:C.teal, transparency:78} });
s.addShape(pres.shapes.OVAL, { x:W-2.0, y:3.6,  w:3.2, h:3.2, fill:{color:C.sea,  transparency:82} });
s.addText("癌症个性化新抗原疫苗 · 预测工具部署与基准评估", { x:0.9, y:1.5, w:11, h:0.4, fontFace:FB, fontSize:15, color:C.mint, bold:true, charSpacing:2, margin:0 });
s.addText("10 个新抗原免疫原性预测工具\n横向评测报告", { x:0.9, y:2.05, w:11.5, h:1.8, fontFace:FH, fontSize:42, bold:true, color:"FFFFFF", lineSpacingMultiple:1.05, margin:0 });
s.addText("逐工具部署 + 四类信息 · 9 工具进入 ELISpot 统一基准 · 一个工具阻塞未完成", { x:0.9, y:4.2, w:11.5, h:0.5, fontFace:FB, fontSize:15, color:"CADCFC", margin:0 });
s.addShape(pres.shapes.LINE, { x:0.95, y:5.1, w:3.2, h:0, line:{color:C.mint, width:2} });
s.addText([
  { text:"汇报人  ", options:{ color:"8FB7BD", fontSize:13 } },
  { text:"余嘉 (legacccy)", options:{ color:"FFFFFF", fontSize:13, bold:true, breakLine:true } },
  { text:"项目  ", options:{ color:"8FB7BD", fontSize:13 } },
  { text:"癌症新抗原疫苗协作项目", options:{ color:"FFFFFF", fontSize:13 } },
], { x:0.95, y:5.35, w:9, h:1.0, fontFace:FB, valign:"top", margin:0 });
s.addText("2026-06-25", { x:W-2.4, y:6.7, w:1.8, h:0.3, fontFace:FB, fontSize:12, color:"8FB7BD", align:"right", margin:0 });

// ============================================================ 目录
s = pres.addSlide();
header(s, "目录", "本报告的内容结构");
const toc = [
  ["01","项目背景与任务","要解决什么、本报告做了什么"],
  ["02","10 工具总览横评","一张表看清装到什么程度、进没进基准"],
  ["03","工具逐一解析","每个工具的工作原理 + 四类信息"],
  ["04","部署工程与踩坑","环境、典型问题与解决（按工具归属）"],
  ["05","数据与评测方法","测试数据来源、评测流程、指标说明"],
  ["06","基准结果","判别力 / 能否定量 / 工具间一致性 / 分层"],
  ["07","诚实边界 · 参考 · 结论","限制与许可、出处、总结与下一步"],
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

// ============================================================ S2 背景 + 4类信息
s = pres.addSlide();
header(s, "项目背景", "要解决什么问题 · 我做了什么");
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:1.7, w:5.55, h:3.05, fill:{color:C.dark}, shadow:sh() });
s.addText("项目要做的事", { x:0.98, y:1.95, w:5, h:0.4, fontFace:FH, fontSize:17, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"做一个能预测 T 细胞反应 ", options:{ color:"FFFFFF", fontSize:14 } },
  { text:"「强弱程度」", options:{ color:C.mint, fontSize:17, bold:true } },
  { text:" 的工具。", options:{ color:"FFFFFF", fontSize:14, breakLine:true } },
  { text:"现有工具大多只回答「有没有免疫反应」（是非题）；目标是更进一步，给出反应「有多强」（打分题）。", options:{ color:"CADCFC", fontSize:12.5, breakLine:true } },
], { x:0.98, y:2.42, w:5.05, h:2.2, fontFace:FB, valign:"top", lineSpacingMultiple:1.18, margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:4.95, w:5.55, h:2.05, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addText("我这部分的任务", { x:0.95, y:5.08, w:5, h:0.34, fontFace:FH, fontSize:14, bold:true, color:C.teal, margin:0 });
s.addText([
  { text:"把市面上现有的预测工具一个个装好、跑通，", options:{ color:C.ink, fontSize:12, breakLine:true } },
  { text:"用同一套真实实验数据（ELISpot）横向比一遍，看它们到底准不准、能不能分强弱。", options:{ color:C.ink, fontSize:12, breakLine:true, paraSpaceAfter:6 } },
  { text:"每个工具记录 4 类信息，整理成本报告。", options:{ color:C.dark, fontSize:12, bold:true } },
], { x:0.95, y:5.46, w:5.2, h:1.5, fontFace:FB, valign:"top", lineSpacingMultiple:1.1, margin:0 });
// 右: 4类信息
s.addText("每个工具记录的 4 类信息", { x:6.7, y:1.78, w:6, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.ink, margin:0 });
const items = [
  ["①","输入要喂什么","文件格式、必填列、肽段长度、HLA 写法"],
  ["②","怎么运行 / 调参","可调参数有哪些、各管什么、运行模式"],
  ["③","输出是什么","关键列含义、分数类型、能不能分强弱"],
  ["④","工具是什么 / 优缺点","用的什么方法、强在哪、有什么限制"],
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
s.addText("覆盖 10 个工具：9 个跑进统一基准，1 个（MHLAPre）因缺权重未完成。", { x:6.92, y:6.52, w:5.6, h:0.46, fontFace:FB, fontSize:11, bold:true, color:C.dark, valign:"middle", margin:0 });
pageno(s);

// ============================================================ S3 ⭐ 10 工具横评总表
s = pres.addSlide();
header(s, "总览", "10 个工具一览：装到什么程度 · 进没进基准 · 跑的什么版本");
const hd = (t)=>({ text:t, options:{ fill:{color:C.dark}, color:"FFFFFF", bold:true, fontSize:11.5, align:"center", valign:"middle" } });
const cc = (t,col)=>({ text:t, options:{ color:col||C.ink, fontSize:10.5, align:"center", valign:"middle" } });
const cl = (t)=>({ text:t, options:{ color:C.ink, fontSize:11, bold:true, align:"left", valign:"middle" } });
const rows = [
  [hd("工具"), hd("预测什么"), hd("方法"), hd("进基准"), hd("基准 AUC*"), hd("版本 / 状态")],
  [cl("DeepImmuno"), cc("免疫原性"), cc("卷积网络 CNN"), cc("✅",C.ok), cc("0.481",C.ink), cc("完整端到端",C.ok)],
  [cl("PredIG"),     cc("免疫原性"), cc("梯度提升树"),   cc("✅",C.ok), cc("0.661",C.ink), cc("完整端到端",C.ok)],
  [cl("pTuneos"),    cc("免疫原性"), cc("机器学习流程"), cc("✅",C.ok), cc("0.753",C.ink), cc("子模型 (对账 r=1.0)",C.warn)],
  [cl("IMPROVE"),    cc("免疫原性"), cc("随机森林"),     cc("✅",C.ok), cc("0.621",C.ink), cc("特征降级",C.warn)],
  [cl("NeoTImmuML ★"),cc("免疫原性"), cc("集成机器学习"), cc("✅",C.ok), cc("0.655",C.ink), cc("自训版 (非官方权重)",C.warn)],
  [cl("PRIME"),      cc("免疫原性"), cc("轻量打分模型"), cc("✅",C.ok), cc("0.528",C.ink), cc("完整 (对账 r=1.0)",C.ok)],
  [cl("ImmuneApp"),  cc("免疫原性"), cc("CNN-LSTM"),     cc("✅",C.ok), cc("0.589",C.ink), cc("完整",C.ok)],
  [cl("deepHLApan"), cc("免疫原性"), cc("双向循环网络"), cc("✅",C.ok), cc("0.419",C.ink), cc("完整",C.ok)],
  [cl("HLAthena"),   cc("提呈 (非免疫原性)",C.warn), cc("全连接网络"), cc("✅ 单列",C.warn), cc("0.509",C.ink), cc("提呈 proxy，不并比",C.warn)],
  [cl("MHLAPre"),    cc("免疫原性"), cc("元学习+Transformer"), cc("❌",C.crit), cc("—",C.gray), cc("未做成 (缺权重)",C.crit)],
];
s.addTable(rows, { x:0.55, y:1.7, w:12.25, colW:[2.0,1.95,2.05,0.95,1.3,4.0],
  rowH:[0.42,0.39,0.39,0.39,0.39,0.39,0.39,0.39,0.39,0.39,0.39],
  border:{pt:1,color:C.line}, align:"center", valign:"middle", fontFace:FB, fill:{color:C.card} });
s.addText([
  { text:"* 基准 AUC = ELISpot 测试集 DS2、max 聚合、阈值>0 口径下的判别力（0.5=随机，越高越好）。完整数字与其它口径见基准章节与 analysis/metrics_ds2_9tools.csv。", options:{ color:C.muted, fontSize:9, italic:true, breakLine:true } },
  { text:"★ NeoTImmuML：官方未放出预训练权重，用公开数据自训了一版进基准，数值不对标原论文。   9 个进基准 = 8 个免疫原性工具直接横比 + HLAthena（预测「提呈」非「免疫原性」）单列作参照、不与前 8 个并比。", options:{ color:C.ink, fontSize:9.5, breakLine:true } },
], { x:0.55, y:6.05, w:12.25, h:0.95, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
pageno(s);

// ============================================================ S4-S23 逐工具 (10) 每工具=原理页+四类信息页
// —— 第一批 5 工具 ——
principleSlide({ idx:1, name:"DeepImmuno", accent:"028090",
  sub:"用卷积神经网络判断一条肽段能不能激活 CD8+ T 细胞",
  inP:"只要两样东西：一条肽段序列（9 或 10 个氨基酸）和它对应的 HLA 分型。不需要基因组、不需要表达量，是十个工具里最省事的。",
  modelP:"先把氨基酸序列和 HLA 假基序按物化性质编码成一张数字矩阵，再用卷积神经网络（CNN）像扫图像一样扫过这张矩阵，自动抓出和免疫原性有关的局部模式，最后汇总成一个分数。",
  outP:"输出一个 0 到 1 之间的连续分，越接近 1 表示越可能激活 T 细胞。实测已知强表位（如 CMV 的 NLVPMVATV）确实拿到高分，符合预期。",
  cmd:["# 单条", "python deepimmuno-cnn.py \\", "  --mode single \\", "  --epitope NLVPMVATV --hla HLA-A*0201", "# 批量", "#   --mode multiple --intdir IN --outdir OUT"],
  inFmt:["# CSV，两列，无表头", "# 肽段, HLA", "NLVPMVATV,HLA-A*0201", "GILGFVFTL,HLA-A*0201"],
  outFmt:["peptide    HLA          immunogenicity", "NLVPMVATV  HLA-A*0201   0.957", "GILGFVFTL  HLA-A*0201   0.887"],
  cite:"DeepImmuno, Briefings in Bioinformatics 2021 · DOI 10.1093/bib/bbab160 · github.com/frankligy/DeepImmuno",
});
toolSlide({ idx:1, page:4, name:"DeepImmuno", accent:"028090", method:"卷积网络 CNN", status:"✅ 完整端到端", statusCol:C.ok,
  tagline:"用卷积神经网络判断一条肽段能否激活 CD8+ T 细胞（HLA-I），最轻量、只要肽段+HLA",
  input:[ "CSV，两列无表头  peptide, HLA", "肽段长度固定 9 或 10", "HLA 写法  HLA-A*0201", "不需要基因组 / HLA 库" ],
  params:[ "--mode single  单条，结果打印屏幕", "--mode multiple  批量，指定输入输出目录", "没有可调超参；须在 repo 根目录运行" ],
  output:[ "三列  peptide / HLA / immunogenicity", "immunogenicity = 0~1 连续分，越高越强", "实测已知强表位高分（CMV NLVPMVATV=0.957）→ 合理" ],
  intro:[ "最省事：纯肽段+HLA 就能跑，不依赖任何收费工具，CPU 即可", "环境：Python3.8 + TensorFlow2.3（protobuf 须降到 3.20）", "限制：肽长只能 9 或 10" ],
  cite:"DeepImmuno, Briefings in Bioinformatics 2021 · DOI 10.1093/bib/bbab160 · github.com/frankligy/DeepImmuno",
});
principleSlide({ idx:2, name:"PredIG", accent:"1C7293",
  sub:"用梯度提升树预测免疫原性，并给出一串可解释的特征",
  inP:"输入肽段、HLA 分型，以及（重组模式下）肽段所在的蛋白序列。支持三种输入模式，肽段长度 8–14。",
  modelP:"先调用一串内置工具算出 13 类特征——蛋白酶切位点、提呈分（NOAH）、物化性质、TCR 接触位点等——再把这些特征喂给 XGBoost 梯度提升树模型综合打分。特征可解释是它的卖点。",
  outP:"输出一个 0 到 1 的免疫原性分（PredIG 列），同时附上那 13 列特征，方便回看模型是凭什么给的分。",
  cmd:["python predig.py \\", "  --type recombinant \\", "  --modelXG neoant \\", "  -i input.csv \\", "  -o result.csv"],
  inFmt:["# CSV，重组模式", "epitope,HLA_allele,protein_seq,protein_name", "SLLMWITQV,HLA-A*0201,MSLL...,TP53"],
  outFmt:["# CSV，含 PredIG 分 + 13 列特征", "epitope    PredIG   NOAH   TCR_contact ...", "SLLMWITQV  0.0061   0.42   ..."],
  cite:"PredIG, Genome Medicine 2025 · DOI 10.1186/s13073-025-01569-8 · github.com/BSC-CNS-EAPM/PredIG",
});
toolSlide({ idx:2, page:5, name:"PredIG", accent:"1C7293", method:"梯度提升树 XGBoost", status:"✅ 完整端到端", statusCol:C.ok,
  tagline:"用梯度提升树预测 T 细胞表位免疫原性，按抗原类型分专用模型，结果可解释",
  input:[ "3 种模式：Uniprot / Recombinant / FASTA", "Recombinant 列  epitope, HLA_allele, protein_seq, protein_name", "肽段 8–14 个氨基酸" ],
  params:[ "--modelXG  选模型（neoant / noncan / 自定义）", "--type  选输入模式", "-o  输出文件" ],
  output:[ "CSV，PredIG 列 = 0~1 连续免疫原性分", "另附 13 列特征（切割/提呈/物化/TCR 接触等）", "实测 SLLMWITQV = 0.0061" ],
  intro:[ "连续分 + 可解释特征 + 容器化（依赖全打包，省去装环境）", "环境：官方 Docker（14.4G）→ HPC 转 Singularity（4.6G）", "限制：镜像体积大" ],
  cite:"PredIG, Genome Medicine 2025 · DOI 10.1186/s13073-025-01569-8 · github.com/BSC-CNS-EAPM/PredIG",
});
principleSlide({ idx:3, name:"pTuneos", accent:"028090",
  sub:"一整套新抗原流程；其中识别子模型可单独给肽段打分",
  inP:"完整流程要测序变异（VCF）、表达量、拷贝数、肿瘤纯度、HLA——需要全基因组数据，喂不了纯肽段。但它的识别子模型 Pre&RecNeo 只要三列：突变肽、对应野生肽、HLA，这部分能用来跑 ELISpot 肽段。",
  modelP:"完整流程先把测序变异注释成突变肽，再逐层打分；识别子模型则针对一对「突变肽 vs 野生肽」算结合、相似度、被 T 细胞识别等特征，输出免疫识别分。本基准用的就是这个子模型。",
  outP:"完整流程给患者级排名分（乘了表达量和突变频率，需测序）；子模型给纯肽免疫识别分，这部分可与其它工具横比。实测示例数据端到端跑出 40 个候选新抗原。",
  cmd:["# 完整流程", "python pTuneos.py VCF -i config.yaml", "# 识别子模型（喂肽段）", "# 自写脚本调用 InVivoModelAndScore"],
  inFmt:["# 子模型输入：三列", "MT_pep,     WT_pep,     HLA", "AAAVFKTLP,  AAAVFKTLR,  HLA-A*02:01"],
  outFmt:["# 子模型识别分 model_pro", "MT_pep      model_pro", "AAAVFKTLP   0.73"],
  cite:"pTuneos, Genome Medicine 2019 · DOI 10.1186/s13073-019-0679-x · github.com/bm2-lab/pTuneos",
});
toolSlide({ idx:3, page:6, name:"pTuneos", accent:"028090", method:"机器学习流程", status:"⚠️ 子模型端到端", statusCol:C.warn,
  tagline:"一整套个性化新抗原流程（从测序数据到排名）；其中识别子模型可单独拿肽段来打分",
  input:[ "完整流程：测序变异 + 表达量 + 拷贝数 + 纯度 + HLA（要全基因组，喂不了纯肽）", "★ 识别子模型：只要 突变肽 + 野生肽 + HLA 三列（能跑 ELISpot 肽）" ],
  params:[ "完整：python pTuneos.py  +  配置文件", "子模型：自写脚本调用识别打分函数", "可并行加速（多进程 + 批量结合预测）" ],
  output:[ "完整流程出患者级排名分（乘了表达/突变频率，需测序）", "子模型出纯肽免疫原性识别分 → 这部分进基准、可与其它工具比", "示例数据跑出 40 个候选新抗原" ],
  intro:[ "镜像自带 netMHCpan / VEP / GATK 等全套；修了 8 处坑 + 14G 注释缓存才端到端跑通", "诚实说明：进基准用的是识别子模型，对账官方逻辑一致（r=1.0），不等于整条流程的端到端能力", "完整流程在本地容器跑通；HPC 因权限限制未跑" ],
  cite:"pTuneos, Genome Medicine 2019 · DOI 10.1186/s13073-019-0679-x · github.com/bm2-lab/pTuneos",
});
principleSlide({ idx:4, name:"IMPROVE", accent:"1C7293",
  sub:"用随机森林给新表位打分，整合了 22 个特征",
  inP:"输入突变肽、对应野生肽、HLA（TSV 格式，肽段 8–12）。流程分两步：先算特征，再预测。",
  modelP:"第一步用外部工具算出 22 个特征（包含结合、稳定性、TCR 识别 PRIME 分、自相似度等）；第二步把特征喂给随机森林（每个变体 5 个森林做集成）综合打分。本基准里表达相关特征因 ELISpot 无 RNA 数据而降级。",
  outP:"在输入表后追加一列 mean_prediction_rf，是多折多森林的集成平均分（0 到 1）。",
  cmd:["# 第一步：算特征", "bash run_feature_calc.sh input.tsv", "# 第二步：预测", "python Predict.py --model Simple"],
  inFmt:["# TSV：突变肽 + 野生肽 + HLA", "Mut_pep     Norm_pep    HLA", "EEFLNSWML   EEFLNSWMV   HLA-B*08:01"],
  outFmt:["# 追加 mean_prediction_rf 列", "Mut_pep     mean_prediction_rf", "EEFLNSWML   0.5146"],
  cite:"IMPROVE, Frontiers in Immunology 2024 · DOI 10.3389/fimmu.2024.1360281 · github.com/SRHgroup/IMPROVE_tool",
});
toolSlide({ idx:4, page:7, name:"IMPROVE", accent:"1C7293", method:"随机森林", status:"⚠️ 特征降级", statusCol:C.warn,
  tagline:"用随机森林给新表位的免疫原性打分，22 个特征，分三种变体模型",
  input:[ "TSV，必填  突变肽 + 野生肽 + HLA", "肽段 8–12 个氨基酸", "两步走：先算特征，再跑随机森林预测" ],
  params:[ "--model  选 Simple / TME_excluded / TME_included", "每个变体加载 5 个森林做集成" ],
  output:[ "TSV 追加一列  mean_prediction_rf（0~1 连续）", "= 多折 × 多森林的集成平均", "实测 Simple 变体 EEFLNSWML = 0.5146" ],
  intro:[ "22 个特征专为新表位排名设计，整合了 TCR 识别信号", "缺口：ELISpot 没有 RNA 表达量 → 表达相关特征降级；稳定性特征依赖的外部工具受系统库版本所限", "预测步本地+HPC 都跑通；这是「数据缺一块」不是「装不上」" ],
  cite:"IMPROVE, Frontiers in Immunology 2024 · DOI 10.3389/fimmu.2024.1360281 · github.com/SRHgroup/IMPROVE_tool",
});
principleSlide({ idx:5, name:"NeoTImmuML ★ 自训版", accent:"028090",
  sub:"三种模型加权集成，用 78 个肽段物化特征；官方无权重，本基准为自训版",
  inP:"输入肽段加上 78 个物化特征（要先用 R 的 Peptides 包算好），不需要 HLA，肽段 8–13。",
  modelP:"把 78 维特征喂给 LightGBM、XGBoost、随机森林三个模型，再加权集成成一个概率。官方仓库是研究用 notebook、没带预训练权重，所以本基准用公开肿瘤抗原库自己重训了一版（数值不对标原论文）。",
  outP:"输出 0 到 1 的免疫原性概率（predict_proba），能用来排强弱；同时给分类指标和雷达图。",
  cmd:["# 不是命令行，是 Jupyter notebook", "# 改 file_path 指向数据后", "# 顺序运行 21 个单元格", "# （含 8 算法对比 + 加权集成）"],
  inFmt:["# CSV：肽段 + 标签 + 78 特征", "Peptide    label  feat1  feat2 ... feat78", "AAAVFKTLP  1      0.12   -0.4  ..."],
  outFmt:["# predict_proba 连续概率", "Peptide    immuno_prob", "AAAVFKTLP  0.81"],
  cite:"NeoTImmuML, Frontiers in Immunology 2025 · DOI 10.3389/fimmu.2025.1681396 · github.com/01SYan19/NeoTImmuML",
});
let sN = toolSlide({ idx:5, page:8, name:"NeoTImmuML ★ 自训版", accent:"028090", method:"集成机器学习", status:"⚠️ 自训版", statusCol:C.warn,
  tagline:"三种模型加权集成（LightGBM+XGBoost+随机森林）预测肿瘤新抗原免疫原性，用 78 个肽段物化特征",
  input:[ "CSV：肽段 + 标签 + 78 个物化特征", "肽段 8–13 个氨基酸，不需要 HLA", "78 个特征要先用 R 的 Peptides 包算好" ],
  params:[ "不是命令行，是 Jupyter notebook（21 个单元格）", "改路径指向数据；内含 8 种算法对比 + 加权集成 + 交叉验证" ],
  output:[ "分类指标 + 雷达图 + 连续概率（能分强弱）", "★ 官方没放预训练权重 → 基准用我们自训的版本", "数值不对标原论文精度" ],
  intro:[ "纯肽段特征，不要 HLA、不要任何收费工具，装起来最省心", "限制：是研究用 notebook，没带权重 → 用公开肿瘤抗原库重训了一版", "不含 78 特征的计算代码 → 要自己用 R 算" ],
  cite:"NeoTImmuML, Frontiers in Immunology 2025 · DOI 10.3389/fimmu.2025.1681396 · github.com/01SYan19/NeoTImmuML",
});
// —— 第二批 5 工具 ——
principleSlide({ idx:6, name:"PRIME", accent:"1C7293",
  sub:"轻量打分模型：把提呈分、TCR 接触特征、肽长揉成一个免疫原性分",
  inP:"只要肽段（每行一条或 FASTA）和 HLA（命令行 -a 指定），肽段 8–14。HLA 写法很宽松。依赖链最短，十个里最好装。",
  modelP:"先用 MixMHCpred 算出 HLA 提呈分，再结合 TCR 接触位点的氨基酸频率特征和肽段长度，用一个轻量打分模型（非深度学习）综合成免疫原性排名分。CPU 即可、很快。",
  outP:"输出每条肽段跨所有 HLA 的最优 %Rank（越低越好）和 PRIME Score（连续，量化强弱），以及最优 allele。实测 147 行输出与官方答案逐字一致。",
  cmd:["./PRIME \\", "  -i test/test.txt \\", "  -o test/out.txt \\", "  -a A0101,A2501,B0801 \\", "  -mix <MixMHCpred 路径>"],
  inFmt:["# 每行一条肽段", "VMLQAPLFT", "GILGFVFTL"],
  outFmt:["Peptide    %Rank   Score     BestAllele", "VMLQAPLFT  3.901   0.01024   B0801"],
  cite:"PRIME, Cell Reports Medicine 2021 / Cell Systems 2023 · DOI 10.1016/j.celrep.2021.100194 · 10.1016/j.cels.2022.12.002 · github.com/GfellerLab/PRIME",
});
toolSlide({ idx:6, page:9, name:"PRIME", accent:"1C7293", method:"轻量打分模型", status:"✅ 完整 (对账 r=1.0)", statusCol:C.ok,
  tagline:"轻量模型预测新表位免疫原性：把 HLA 提呈分 + TCR 接触位点氨基酸频率 + 肽长 揉成一个排名分",
  input:[ "纯文本（每行一条肽段）或 FASTA", "HLA 用命令行 -a 指定，多个逗号分隔", "肽段 8–14；HLA 写法很宽松（A0101 / A01:01 / HLA-A*01:01 都行）" ],
  params:[ "-i 输入  -o 输出  -a HLA 列表  -mix 指定 MixMHCpred 路径", "模型版本 v2.1（需配 MixMHCpred v3.0+）" ],
  output:[ "文本 5 列：肽段 / 最优%Rank / PRIME Score / 结合%Rank / 最优 allele", "PRIME Score 连续，量化免疫原性强弱", "实测 147 行输出与官方答案逐字一致（diff=0）" ],
  intro:[ "直接出免疫原性连续分；依赖链最短（只要 MixMHCpred，无收费工具），五个里装起来最容易", "方法非深度学习，轻快、CPU 即可", "限制：肽长 8–14；需对齐 MixMHCpred 版本" ],
  cite:"PRIME, Cell Reports Medicine 2021 / Cell Systems 2023 · DOI 10.1016/j.celrep.2021.100194 · 10.1016/j.cels.2022.12.002 · github.com/GfellerLab/PRIME",
});
principleSlide({ idx:7, name:"ImmuneApp", accent:"028090",
  sub:"带注意力的 CNN-LSTM，做 HLA-I 表位与免疫原性预测",
  inP:"输入肽段（每行一条）和 HLA（-a 指定），肽段 8–15，仅 20 种标准氨基酸。",
  modelP:"用注意力机制的 CNN-LSTM 混合网络处理肽段序列，注意力能指出哪些残基对结合关键；其中免疫原性模块由迁移学习得到。仅支持 HLA-I。",
  outP:"输出 TSV，每条肽段每个 HLA 一行，给 0 到 1 的 Immunogenicity_score。实测 CILGKLFTKK=0.99997、ALPPTVYEV=0.00068。",
  cmd:["python \\", "  ImmuneApp_immunogenicity_prediction.py \\", "  -f test_immunogenicity.txt \\", "  -a 'HLA-A*01:01' 'HLA-A*02:01' \\", "  -o results"],
  inFmt:["# 每行一条肽段 + 命令行 -a 给 HLA", "CILGKLFTKK", "ALPPTVYEV"],
  outFmt:["Allele       Peptide      Immunogenicity_score", "HLA-A*01:01  CILGKLFTKK   0.99997", "HLA-A*01:01  ALPPTVYEV    0.00068"],
  cite:"ImmuneApp, Nature Communications 2024 · DOI 10.1038/s41467-024-53296-0 · github.com/bsml320/ImmuneApp",
});
toolSlide({ idx:7, page:10, name:"ImmuneApp", accent:"028090", method:"CNN-LSTM + 注意力", status:"✅ 完整", statusCol:C.ok,
  tagline:"带注意力的 CNN-LSTM，做 HLA-I 表位预测 + 免疫肽组分析；其中 Neo 模块专做免疫原性",
  input:[ "纯肽段文本（每行一条，无表头）+ 命令行 -a 指定 HLA", "肽段 8–15 个氨基酸（仅 20 种标准氨基酸）", "HLA 写法  HLA-A*01:01" ],
  params:[ "-f 肽段文件  -a HLA 列表  -o 输出目录", "多个模块（结合/洗脱/提呈/免疫原性），本项目用免疫原性模块" ],
  output:[ "TSV：Allele / Peptide / Sample / Immunogenicity_score", "分数 0~1 连续；每条肽段每个 HLA 各出一行", "实测 CILGKLFTKK = 0.99997、ALPPTVYEV = 0.00068" ],
  intro:[ "HLA-I 提呈方向性能领先，预训练权重随仓库带、MIT 许可无障碍、不依赖收费工具", "方法可解释（注意力能指出关键结合残基）", "限制：仅 HLA-I；TF1.15 老环境易踩坑；训练数据含公开库 → 注意与测试集重叠" ],
  cite:"ImmuneApp, Nature Communications 2024 · DOI 10.1038/s41467-024-53296-0 · github.com/bsml320/ImmuneApp",
});
principleSlide({ idx:8, name:"deepHLApan", accent:"1C7293",
  sub:"双向循环网络+注意力，一次给出结合分和免疫原性分（仅 MHC-I）",
  inP:"输入 CSV，必须有表头 Annotation,HLA,peptide，肽段 8–15。HLA 写法特殊：HLA-A01:01（无星号、连字符直连）。",
  modelP:"用三层双向 GRU 加注意力处理肽段+HLA，同时输出两个任务的分：一个判结合/提呈，一个判免疫原性，无需手动切换。训练数据含公开库，需注意与测试集重叠。",
  outP:"输出 CSV，给 binding score 和 immunogenic score（都是 0–1）。高置信新抗原定义为免疫原性 >0.5 且结合排名前 20。实测 MKRFVQWL/HLA-C07:02 结合 0.99、免疫原性 0.97。",
  cmd:["# 先建好输出目录", "mkdir -p out", "deephlapan -F input.csv -O out"],
  inFmt:["# CSV，必须有表头", "Annotation,HLA,peptide", "test,HLA-A01:01,MKRFVQWL"],
  outFmt:["Annotation,HLA,Peptide,binding score,immunogenic score", "test,HLA-C07:02,MKRFVQWL,0.9919,0.972"],
  cite:"DeepHLApan, Frontiers in Immunology 2019 · DOI 10.3389/fimmu.2019.02559 · github.com/jiujiezz/deephlapan（GPL-2.0）",
});
toolSlide({ idx:8, page:11, name:"deepHLApan", accent:"1C7293", method:"双向循环网络 BiGRU", status:"✅ 完整", statusCol:C.ok,
  tagline:"双向循环网络+注意力，两个模型一起出：一个判结合/提呈，一个判免疫原性（仅 MHC-I）",
  input:[ "CSV，必须有表头  Annotation, HLA, peptide", "肽段 8–15 个氨基酸", "HLA 写法  HLA-A01:01（注意：无星号、连字符直连）" ],
  params:[ "-F 输入 CSV，或 -P 单肽 + -H 单 HLA", "两个模型一次出结果，无需手动切换" ],
  output:[ "CSV：binding score + immunogenic score（都是 0~1）", "高置信新抗原 = 免疫原性 >0.5 且结合排名前 20", "实测 MKRFVQWL/HLA-C07:02  结合=0.99 免疫原性=0.97" ],
  intro:[ "一次同时给「结合 + 免疫原性」两个分，纯肽段+HLA，不依赖收费工具", "官方推荐用 Docker 镜像绕开版本不兼容问题", "限制：仅 MHC-I；训练数据含公开库 → 与测试集可能重叠，需排重" ],
  cite:"DeepHLApan, Frontiers in Immunology 2019 · DOI 10.3389/fimmu.2019.02559 · github.com/jiujiezz/deephlapan（GPL-2.0）",
});
principleSlide({ idx:9, name:"HLAthena（提呈 proxy）", accent:"C9743D",
  sub:"质谱训练的全连接网络，预测「提呈」概率——不是免疫原性",
  inP:"输入肽段（tab 带表头或 FASTA，必填 peptide 列），肽段 8/9/10/11。可选给剪切上下文或表达量，决定跑哪个子模型。",
  modelP:"用大规模质谱免疫肽组数据训练一个单隐层全连接网络，预测肽段被 HLA-I 提呈的概率。论文明确声明：它只预测「能否被提呈」，不预测「能否激活 T 细胞」。",
  outP:"输出连续提呈分（MSi 等列），越高越可能被提呈。注意这不是免疫强弱分——这正是它在本基准里只能作提呈参照、不与免疫原性工具并比的原因。实测 IDLLKEIY 的 MSi=0.844。",
  cmd:["predict \\", "  --runID demo \\", "  --rundir /work \\", "  --peptides peps.txt \\", "  --alleles A0101"],
  inFmt:["# tab 分隔，带表头", "peptide", "IDLLKEIY", "AAAVFKTLP"],
  outFmt:["peptide    MSi_A0101   prank.MSi", "IDLLKEIY   0.844       1.2"],
  cite:"HLAthena, Nature Biotechnology 2020 · DOI 10.1038/s41587-019-0322-9 · hlathena.tools + Docker ssarkizova/hlathena-external",
});
// HLAthena —— proxy 卡（橙色边界，明确标提呈非免疫原性）
let sHla = toolSlide({ idx:9, page:12, name:"HLAthena（提呈 proxy）", accent:"C9743D", method:"全连接网络", status:"⚠️ 提呈 proxy", statusCol:C.warn,
  tagline:"质谱数据训练的全连接网络，预测肽段被 HLA-I「提呈」的概率 —— 注意：是提呈，不是免疫原性",
  input:[ "tab 分隔（带表头）或 FASTA，必填 peptide 列", "肽段 8 / 9 / 10 / 11", "可选列（剪切上下文 / 表达量）决定跑哪个子模型" ],
  params:[ "选模型 MSi / MSiC / MSiCE（取决于提供的可选列）", "实测用 Docker 镜像跑，参数同官方 web" ],
  output:[ "连续提呈分（MSi 等列），越高越可能被提呈", "❌ 不是免疫强弱分 —— 这是它与前 8 个工具的本质区别", "实测 IDLLKEIY  MSi=0.844" ],
  intro:[ "质谱免疫肽组大规模训练、覆盖人群广、不依赖收费工具", "论文明确声明：只预测「能否被提呈」，不预测「能否激活 T 细胞」", "故进基准只作提呈参照（proxy），单列、不与免疫原性工具直接并比" ],
  cite:"HLAthena, Nature Biotechnology 2020 · DOI 10.1038/s41587-019-0322-9 · hlathena.tools + Docker ssarkizova/hlathena-external",
});
principleSlide({ idx:10, name:"MHLAPre（未完成）", accent:"B23A48", unfinished:true,
  sub:"元学习+Transformer+TextCNN 预测突变 HLA-I 表位免疫原性——信息摸清但无法复现运行",
  inP:"输入 CSV：肽段、HLA、标签，肽段 8–15（以 9 为主）。HLA 写法 B*07:02（无 HLA- 前缀）。",
  modelP:"用元学习（MAML）加 Transformer 编码器加 TextCNN，BLOSUM62 编码肽段。论文报告指标很高，但官方未放预训练权重，且把原始数据拼成模型输入的预处理代码缺失（被注释掉）——所以连自训也走不通。",
  outP:"原代码只算评估指标、不保存预测文件（同 notebook 性质），理论上能出 0–1 概率但需自己加导出。实际因缺权重与中间数据，跑不起来，未做成。",
  cmd:["# 顺序运行 3 个脚本", "python Pretreatment.py", "python TransfomerEncoder.py", "python TextCNN.py", "# 但缺中间数据，会报 FileNotFound"],
  inFmt:["# CSV", "Epitope,MHC Restriction,Assay", "APSFGSFHLI,B*07:02,1"],
  outFmt:["# 未做成：原代码不存预测文件", "# 缺预训练权重 + 预处理中间数据", "# 跑不起来，无实测输出"],
  cite:"MHLAPre, Briefings in Bioinformatics 2024 · DOI 10.1093/bib/bbae625 · github.com/ChanganMakeYi/MHLAPre（无 LICENSE）",
});
// MHLAPre —— 未做成卡（红色边界，讲清为什么没成）
let sMh = toolSlide({ idx:10, page:13, name:"MHLAPre（未完成）", accent:"B23A48", method:"元学习+Transformer", status:"❌ 未做成", statusCol:C.crit,
  tagline:"元学习 + Transformer + TextCNN 预测突变 HLA-I 表位免疫原性 —— 信息已摸清，但无法复现运行",
  input:[ "CSV：肽段 + HLA + 标签", "肽段 8–15（以 9 为主）", "HLA 写法  B*07:02（无 HLA- 前缀）" ],
  params:[ "顺序跑 3 个脚本（预处理 → Transformer → TextCNN）", "无命令行参数说明" ],
  output:[ "原代码不存预测文件，只算指标（同 notebook 性质）", "理论上出 0~1 连续概率，要自己加导出代码", "实测无输出（卡在缺数据，跑不起来）" ],
  intro:[ "方法新（元学习），论文报告指标高；纯开源依赖、无收费工具", "❌ 阻塞：官方未放预训练权重，预处理中间数据也缺失", "❌ 连自训也走不通：把原始数据拼成模型输入的那段代码没随仓库发出（被注释掉）", "全网（GitHub/Gitee/ModelScope/Zenodo + 逐个 commit）搜权重均空 → 唯一出路是邮件原作者索取" ],
  cite:"MHLAPre, Briefings in Bioinformatics 2024 · DOI 10.1093/bib/bbae625 · github.com/ChanganMakeYi/MHLAPre（无 LICENSE）",
});

// ============================================================ S14 部署工程 + 踩坑
s = pres.addSlide();
header(s, "工程", "装这些工具踩过的坑（为什么不是点一下就能跑）");
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
s.addText("典型的坑与解法", { x:5.6, y:1.9, w:7, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.ink, margin:0 });
const pit = [
  ["DeepImmuno：版本敏感","protobuf 必须降到 3.20，否则报 Descriptors 错；TF2.3 + Python3.8 严格对版本"],
  ["ImmuneApp：装 TF1.15 卡死","一次性 pip 装会依赖回溯死循环(卡 20min+)→ 改先单独装 tensorflow==1.15 再装其余才过"],
  ["deepHLApan：输出目录","工具不自建输出目录，outdir 必须先 mkdir，否则报 No such file；用官方 Docker 绕版本不兼容"],
  ["pTuneos：老链 + 大缓存","镜像老依赖修了 8 处坑 + VEP 注释缓存 14G 才端到端跑通；HPC 因容器权限受限未跑"],
  ["HLAthena：下载凭证失效","镜像自带 GCS 凭证 401 死锁 → 改匿名直链下模型 + 关掉自动拉取、本地挂载才跑通"],
  ["MHLAPre：缺权重","官方未放预训练权重 + 预处理中间数据缺 + 拼装代码被注释 → 跑不通(未做成)"],
];
pit.forEach((p,i)=>{
  const col = (i%2===0)? 5.6 : 9.2;
  const yrow = 2.4 + Math.floor(i/2)*1.52;
  s.addShape(pres.shapes.RECTANGLE, { x:col, y:yrow, w:3.4, h:1.4, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:col, y:yrow, w:3.4, h:0.06, fill:{color:C.sea} });
  s.addText(p[0], { x:col+0.18, y:yrow+0.14, w:3.05, h:0.34, fontFace:FH, fontSize:12, bold:true, color:C.teal, margin:0 });
  s.addText(p[1], { x:col+0.18, y:yrow+0.5, w:3.08, h:0.82, fontFace:FB, fontSize:9.5, color:C.ink, valign:"top", lineSpacingMultiple:1.1, margin:0 });
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
  ["9 工具打分","各工具独立打分\n(8免疫原性+1提呈)",C.sea],
  ["聚合","子肽×HLA\n逐肽取 max",C.teal],
  ["切标签","按 SFC>0\n分有/无反应",C.sea],
  ["算指标","AUC / Spearman\n/ PPV / MCC",C.teal],
  ["横向对比","9 工具同口径\n排名与显著性",C.dark],
];
const bw=1.78, bh=1.5, by=2.6, bgap=0.26, startx=0.72;
flow.forEach((b,i)=>{
  const x=startx + i*(bw+bgap);
  const fc = b[2]===C.dark ? C.dark : C.card;
  const tc = b[2]===C.dark ? "FFFFFF" : C.ink;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y:by, w:bw, h:bh, rectRadius:0.08, fill:{color:fc}, line:{color:b[2],width:2}, shadow:sh() });
  s.addText(b[0], { x, y:by+0.22, w:bw, h:0.45, fontFace:FH, fontSize:15, bold:true, color:b[2]===C.dark?C.mint:b[2], align:"center", margin:0 });
  s.addText(b[1], { x:x+0.1, y:by+0.72, w:bw-0.2, h:0.65, fontFace:FB, fontSize:10, color:tc, align:"center", valign:"top", lineSpacingMultiple:1.0, margin:0 });
  if(i<flow.length-1) s.addText("▶", { x:x+bw-0.04, y:by+bh/2-0.22, w:bgap+0.08, h:0.44, fontFace:FB, fontSize:14, bold:true, color:C.muted, align:"center", valign:"middle", margin:0 });
});
s.addShape(pres.shapes.RECTANGLE, { x:0.72, y:4.7, w:11.9, h:1.95, fill:{color:"F2F7F7"}, line:{color:C.line,width:1} });
s.addText("读这张图", { x:0.95, y:4.85, w:11, h:0.36, fontFace:FH, fontSize:14, bold:true, color:C.teal, margin:0 });
s.addText([
  { text:"同一批肽段喂给 9 个工具 → 每个工具独立打分 → 因一条肽会拆成多个子肽×HLA，统一「逐肽取最大分」聚合 → 按实验反应值 SFC>0 切「有/无反应」标签 → 用同一套指标评估 → 9 个工具在完全相同的口径下横向对比。", options:{ color:C.ink, fontSize:11.5, breakLine:true, paraSpaceAfter:5 } },
  { text:"关键：所有工具走完全一致的聚合、阈值、指标口径，保证「apples-to-apples」可比。", options:{ color:C.dark, fontSize:11.5, bold:true } },
], { x:0.95, y:5.25, w:11.45, h:1.3, fontFace:FB, valign:"top", lineSpacingMultiple:1.08, margin:0 });
pageno(s);

// ============================================================ S15 benchmark 方法/数据
s = pres.addSlide();
header(s, "基准方法", "用什么数据、怎么比、看什么指标");
const mcards = [
  ["测试数据","真实 ELISpot 实验数据 DS2：101 条肽段。按实验反应值切分 —— 有反应 90 条、无反应 11 条（反应值≤0 算真无反应）。","028090"],
  ["参评工具","9 个进基准：8 个免疫原性工具直接横比 + HLAthena（提呈 proxy）单列参照。MHLAPre 因缺权重未参评。","00A896"],
  ["怎么比","一条肽段会拆成多个子肽×HLA，先聚合（取最大/平均）再按阈值切。主口径 = 取最大、阈值>0，保证各工具同口径。","1C7293"],
  ["看什么","AUC（能不能分开「有反应/无反应」，0.5=瞎猜）、AUPRC、Spearman 相关（分数和反应强弱是否同向 = 能不能分强弱）。用 2000 次重抽样给出置信区间。","028090"],
];
let my=1.85;
mcards.forEach(m=>{
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:my, w:11.9, h:1.18, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:my, w:0.09, h:1.18, fill:{color:m[2]} });
  s.addText(m[0], { x:1.0, y:my+0.16, w:2.4, h:0.85, fontFace:FH, fontSize:15, bold:true, color:m[2], valign:"top", margin:0 });
  s.addText(m[1], { x:3.4, y:my+0.14, w:9.0, h:0.9, fontFace:FB, fontSize:12, color:C.ink, valign:"middle", lineSpacingMultiple:1.05, margin:0 });
  my += 1.28;
});
s.addText("口径校验：旧 5 工具复现与历史结果最大差 ≤ 0.004（浮点精度内），口径对齐通过；所有数字经 csv 三方核对。", { x:0.7, y:6.95, w:11.9, h:0.4, fontFace:FB, fontSize:10.5, italic:true, color:C.muted, margin:0 });
pageno(s);

// ============================================================ 看懂这些指标（说人话解释每个指标）
s = pres.addSlide();
header(s, "先看懂这些指标", "后面每个数字是什么意思、最该信哪个");
const metricCards = [
  ["AUC（判别力）","随便挑「一条有反应 + 一条没反应」，模型给有反应那条打分更高的概率。","1=完美，0.5=和瞎猜一样，<0.5=反着的。本报告最主要看它。",C.teal,"★ 主看"],
  ["Spearman 相关（能否分强弱）","模型分数的高低排序，和真实反应强弱的排序，吻合到什么程度。","+1=完全同向，0=没关系，−1=完全反着。这是「能不能分强弱」的关键。",C.sea,"★ 看定量"],
  ["PPV@10（前10命中率）","把分数最高的 10 条挑出来，里面真有反应的比例。","临床只能合成排在最前的几条肽，所以这个最贴近实战。",C.teal,"贴临床"],
  ["AUPRC","精确率-召回率曲线下的面积，阳性很少时比 AUC 更敏感。","⚠️ 本数据阳性本就占 89%，起点就高 → 提升空间小，参考意义有限。",C.warn,"参考有限"],
  ["MCC","同时看「真阳/假阳/真阴/假阴」四格的平衡分。","−1 到 +1，类别不平衡时比「准确率」更稳。",C.sea,"辅助"],
  ["95% 置信区间 / p 值","重复抽样 2000 次看指标的波动范围；p<0.05 才算「不是偶然」。","区间越宽=越不确定。本数据样本小（101 条、阴性仅 11）→ 区间普遍偏宽。",C.crit,"看可信度"],
];
let mcx=0.7, mcy=1.75, mcw=5.92, mch=1.5, mgapx=0.36, mgapy=0.22;
metricCards.forEach((m,i)=>{
  const x = mcx + (i%2)*(mcw+mgapx);
  const y = mcy + Math.floor(i/2)*(mch+mgapy);
  s.addShape(pres.shapes.RECTANGLE, { x, y, w:mcw, h:mch, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x, y, w:0.09, h:mch, fill:{color:m[3]} });
  s.addText(m[0], { x:x+0.26, y:y+0.14, w:mcw-1.4, h:0.34, fontFace:FH, fontSize:14, bold:true, color:m[3], margin:0 });
  badge(s, x+mcw-1.15, y+0.13, m[4], m[3], 1.0);
  s.addText([
    { text:m[1], options:{ breakLine:true, color:C.ink, fontSize:10.5, paraSpaceAfter:3 } },
    { text:m[2], options:{ color:C.muted, fontSize:10 } },
  ], { x:x+0.28, y:y+0.55, w:mcw-0.5, h:mch-0.62, fontFace:FB, valign:"top", lineSpacingMultiple:1.04, margin:0 });
});
s.addText([
  { text:"一句话：", options:{ bold:true, color:C.dark, fontSize:11 } },
  { text:"本报告主看 AUC（判别力）和 Spearman（能否分强弱）；AUPRC 因阳性占比高、参考有限；样本量小 → 所有指标的置信区间都偏宽，结论以「方向性」为主、不抠零点几的差距。", options:{ color:C.ink, fontSize:10.5 } },
], { x:0.7, y:6.9, w:11.95, h:0.5, fontFace:FB, valign:"top", lineSpacingMultiple:1.02, margin:0 });
pageno(s);

// ============================================================ S16 8工具 benchmark 核心结论
s = pres.addSlide();
header(s, "核心结论", "8 个免疫原性工具：判别力普遍偏弱、彼此分不出显著高下、新工具没带来增量", C.crit);
s.addShape(pres.shapes.RECTANGLE, { x:0.6, y:1.65, w:7.0, h:5.2, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIG+"/fig6_8tools_auc_comparison.png", x:0.7, y:1.78, w:6.8, h:4.6, sizing:{type:"contain", w:6.8, h:4.6} });
s.addText("图：8 个工具的 AUC（DS2，取最大聚合，阈值>0）+ 95% 置信区间；橙色为第二批新工具。除 pTuneos 外，置信区间下界都跌破随机线 0.5。", { x:0.65, y:6.42, w:6.9, h:0.5, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", margin:0 });
const pts = [
  ["判别力普遍偏弱","点估最高的是 pTuneos 0.753，但置信区间 [0.598, 0.888] 很宽（约 ±0.15）；除它之外，其余工具的区间下界都低于 0.5（随机线）。",C.crit],
  ["彼此分不出高下","两两对比，头部工具之间的差距都跨过 0 —— 比如 pTuneos 与 PredIG 差 0.09、与 NeoTImmuML 差 0.10，区间都含 0，统计上区分不开。根因是无反应样本只有 11 个。",C.warn],
  ["新工具没带来增量","第二批 3 个工具在所有口径下都没超过第一批最好的点估：ImmuneApp 0.589 / PRIME 0.528 / deepHLApan 0.419（低于随机）。这个结论很稳，不依赖排名精度。",C.teal],
];
let py2=1.78;
pts.forEach(p=>{
  s.addShape(pres.shapes.RECTANGLE, { x:7.8, y:py2, w:4.95, h:1.62, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:7.8, y:py2, w:0.09, h:1.62, fill:{color:p[2]} });
  s.addText(p[0], { x:8.0, y:py2+0.12, w:4.7, h:0.34, fontFace:FH, fontSize:14, bold:true, color:p[2], margin:0 });
  s.addText(p[1], { x:8.0, y:py2+0.5, w:4.6, h:1.05, fontFace:FB, fontSize:10.5, color:C.ink, valign:"top", lineSpacingMultiple:1.04, margin:0 });
  py2 += 1.72;
});
s.addText("措辞克制：用「点估居前」而非「最优/最强」—— 在无反应样本仅 11 个时，这些差距不足以支撑「最优」的判断。", { x:7.8, y:6.95, w:4.95, h:0.4, fontFace:FB, fontSize:9, italic:true, color:C.crit, valign:"top", margin:0 });
pageno(s);

// ============================================================ S17 ROC 曲线 (8工具)
const FIGROOT = "D:/YJ-Agent/project/meeting/QuantImmuBench/figures";
s = pres.addSlide();
header(s, "判别力 · ROC 曲线", "8 个工具在 ELISpot 上的 ROC：多数贴着随机线");
s.addShape(pres.shapes.RECTANGLE, { x:0.6, y:1.65, w:6.9, h:5.2, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIG+"/fig8_8tools_roc_curves.png", x:0.8, y:1.78, w:6.5, h:4.95, sizing:{type:"contain", w:6.5, h:4.95} });
s.addText("图：8 个工具的 ROC 曲线（DS2，取最大聚合，阈值>0）。蓝实线=第一批，橙虚线=第二批新工具，灰点线=随机。曲线离左上角越远越弱。", { x:0.62, y:6.78, w:6.9, h:0.45, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", margin:0 });
const rocpts = [
  ["怎么看这张图","曲线越往左上角凸 = 判别力越强；贴着对角线（灰点线）= 和瞎猜差不多。",C.teal],
  ["实际表现","只有 pTuneos（蓝）明显凸向左上；多数工具的曲线缠在对角线附近上下穿插，几个新工具（橙虚线）有段还落到对角线下方（不如随机）。",C.warn],
  ["和柱状图一致","这与上一页 AUC 柱状图给出的结论相互印证：除少数外，判别力普遍接近随机。",C.sea],
];
let ry=1.8;
rocpts.forEach(p=>{
  s.addShape(pres.shapes.RECTANGLE, { x:7.7, y:ry, w:5.05, h:1.6, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:7.7, y:ry, w:0.09, h:1.6, fill:{color:p[2]} });
  s.addText(p[0], { x:7.9, y:ry+0.13, w:4.8, h:0.34, fontFace:FH, fontSize:14, bold:true, color:p[2], margin:0 });
  s.addText(p[1], { x:7.9, y:ry+0.52, w:4.7, h:1.0, fontFace:FB, fontSize:11, color:C.ink, valign:"top", lineSpacingMultiple:1.05, margin:0 });
  ry += 1.7;
});
pageno(s);

// ============================================================ S18 统计稳健性 (caterpillar)
s = pres.addSlide();
header(s, "为什么不下「最优」结论", "置信区间互相重叠 + 样本太小");
s.addShape(pres.shapes.RECTANGLE, { x:0.6, y:1.65, w:7.4, h:5.25, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIGD+"/fig_bootstrap_ci.png", x:0.72, y:1.8, w:7.15, h:4.7, sizing:{type:"contain", w:7.15, h:4.7} });
s.addText("图：8 个工具的 AUC 点估 + 95% 置信区间。所有区间都跨过或贴近 0.5，且彼此大幅重叠。", { x:0.65, y:6.55, w:7.3, h:0.4, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:8.2, y:1.78, w:4.55, h:2.5, fill:{color:C.dark}, shadow:sh() });
s.addText("根因：无反应样本只有 11 个", { x:8.42, y:1.95, w:4.2, h:0.4, fontFace:FH, fontSize:14, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"无反应这一类是少数，AUC 的不确定性主要由它决定。11 个样本 → 每次重抽样波动都很大 → 区间宽达 ±0.15。", options:{ breakLine:true, color:"FFFFFF", fontSize:11.5, paraSpaceAfter:8 } },
  { text:"工具之间不到 0.05 的差距，完全淹没在区间宽度里。", options:{ color:"CADCFC", fontSize:11.5 } },
], { x:8.42, y:2.4, w:4.15, h:1.75, fontFace:FB, valign:"top", lineSpacingMultiple:1.08, margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:8.2, y:4.45, w:4.55, h:2.45, fill:{color:"FBEEE4"}, line:{color:C.warn,width:1} });
s.addText("「最优」只是个脆弱的角落", { x:8.42, y:4.6, w:4.2, h:0.4, fontFace:FH, fontSize:14, bold:true, color:C.warn, margin:0 });
s.addText([
  { text:"pTuneos 的 0.75 是「某一种聚合 × 某一个阈值 × 11 个样本」凑出来的最高点。", options:{ breakLine:true, color:C.ink, fontSize:11, paraSpaceAfter:6 } },
  { text:"同一工具换个阈值，AUC 就掉到约 0.46（低于随机）→ 不是稳定的能力。", options:{ breakLine:true, color:C.ink, fontSize:11, paraSpaceAfter:6 } },
  { text:"它只显著强过几个最弱的工具，对最接近的竞品并不显著。", options:{ color:C.ink, fontSize:11 } },
], { x:8.42, y:5.02, w:4.15, h:1.8, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
pageno(s);

// ============================================================ S19 工具间一致性 (corr heatmap)
s = pres.addSlide();
header(s, "工具之间一致吗", "把同一批肽段的打分两两比对：彼此基本不相关");
s.addShape(pres.shapes.RECTANGLE, { x:0.6, y:1.65, w:7.0, h:5.2, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIGD+"/fig_corr_heatmap.png", x:0.75, y:1.78, w:6.7, h:4.95, sizing:{type:"contain", w:6.7, h:4.95} });
s.addText("图：8 个工具在同一批肽段上打分的两两相关（Spearman）。颜色越红越正相关，越白越不相关。除对角线外大多接近白色。", { x:0.62, y:6.78, w:6.9, h:0.45, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", margin:0 });
const cpts = [
  ["大多互不相关","对角线之外，绝大多数格子都接近 0 —— 不同工具对同一条肽段给的高低排序基本各说各话。",C.crit],
  ["只有两对例外","IMPROVE–PRIME 0.69、DeepImmuno–deepHLApan 0.50 较高，多半因为它们方法或训练数据有重叠。",C.warn],
  ["这说明什么","工具之间没有共识 → 没有哪一个是「公认标准答案」；也意味着简单做平均集成，提升有限（后续验证也确实如此）。",C.teal],
];
let cpy=1.8;
cpts.forEach(p=>{
  s.addShape(pres.shapes.RECTANGLE, { x:7.8, y:cpy, w:4.95, h:1.6, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:7.8, y:cpy, w:0.09, h:1.6, fill:{color:p[2]} });
  s.addText(p[0], { x:8.0, y:cpy+0.13, w:4.7, h:0.34, fontFace:FH, fontSize:14, bold:true, color:p[2], margin:0 });
  s.addText(p[1], { x:8.0, y:cpy+0.52, w:4.6, h:1.0, fontFace:FB, fontSize:11, color:C.ink, valign:"top", lineSpacingMultiple:1.05, margin:0 });
  cpy += 1.7;
});
pageno(s);

// ============================================================ S20 定量能力 + DS1 证伪
s = pres.addSlide();
header(s, "能不能分强弱", "现有工具更像「分类器」而非「打分器」—— 在全是阳性的数据上排不出强弱");
s.addShape(pres.shapes.RECTANGLE, { x:0.6, y:1.65, w:6.6, h:5.2, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIG+"/fig7_8tools_spearman.png", x:0.72, y:1.8, w:6.35, h:4.5, sizing:{type:"contain", w:6.35, h:4.5} });
s.addText("图：8 个工具分数与实验反应强度的 Spearman 相关（取最大聚合）。* 表示显著。只有 IMPROVE / PredIG 显著正相关。", { x:0.65, y:6.4, w:6.5, h:0.45, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:7.4, y:1.75, w:5.35, h:2.55, fill:{color:C.dark}, shadow:sh() });
s.addText("用「全阳数据」DS1 验证「能不能分强弱」", { x:7.62, y:1.92, w:5.0, h:0.4, fontFace:FH, fontSize:13.5, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"DS1 = 82 条肽段，全部有反应（强度从 16 到 677，差约 40 倍），没有阴性 → 不能算 AUC，只能看能不能排强弱。", options:{ breakLine:true, color:"FFFFFF", fontSize:11, paraSpaceAfter:6 } },
  { text:"结果：9 个里 8 个的相关性接近 0、都不显著（基本等于乱排）。唯一显著的那个还是反着的。", options:{ color:"CADCFC", fontSize:10.5 } },
], { x:7.62, y:2.42, w:4.95, h:1.85, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:7.4, y:4.45, w:5.35, h:2.4, fill:{color:"E6F4F1"}, line:{color:C.sea,width:1} });
s.addText("这说明什么", { x:7.62, y:4.58, w:5.0, h:0.36, fontFace:FH, fontSize:13, bold:true, color:C.teal, margin:0 });
s.addText([
  { text:"干净对照：同一批工具在有阴有阳的 DS2 上，头部还能正向排强弱；一到「全是阳性」的 DS1 就全塌成乱排。", options:{ breakLine:true, color:C.ink, fontSize:10.5, paraSpaceAfter:6 } },
  { text:"也就是说，它们的本事主要在「分有反应 / 没反应」这道门槛；真要预测「有多强」几乎做不到（详见下页 DS1 全阳证据）。", options:{ color:C.dark, fontSize:10.5, bold:true } },
], { x:7.62, y:4.96, w:4.95, h:1.85, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
pageno(s);

// ============================================================ S21 DS1 证伪（全阳数据）
s = pres.addSlide();
header(s, "用全阳数据证伪「能分强弱」", "DS1 全是有反应的肽，按强弱排 —— 没有工具排得对");
s.addShape(pres.shapes.RECTANGLE, { x:0.6, y:1.6, w:7.55, h:3.05, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIGROOT+"/ds1_vs_ds2_spearman_bar.png", x:0.72, y:1.72, w:7.3, h:2.8, sizing:{type:"contain", w:7.3, h:2.8} });
s.addText("图上：同一工具在 DS2（蓝，有阴有阳）能正向排强弱，到 DS1（橙，全阳）就掉到 0 附近。", { x:0.62, y:4.58, w:7.5, h:0.35, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:0.6, y:4.95, w:7.55, h:1.95, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIGROOT+"/ds1_magnitude_scatter_bestbinder.png", x:0.72, y:5.05, w:7.3, h:1.75, sizing:{type:"contain", w:7.3, h:1.75} });
s.addText("图下：每个工具的分数 vs 真实反应强度散点 —— 都是一团平云，没有上升趋势。", { x:0.62, y:6.86, w:7.5, h:0.3, fontFace:FB, fontSize:8.5, italic:true, color:C.muted, valign:"top", margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:8.35, y:1.6, w:4.4, h:5.3, fill:{color:C.dark}, shadow:sh() });
s.addText("结论：分类器，不是打分器", { x:8.58, y:1.8, w:4.0, h:0.4, fontFace:FH, fontSize:15, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"DS1 = 82 条肽，全部有反应，强度从 16 到 677（差约 40 倍）。没有阴性，所以只考一件事：能不能把「强的排前、弱的排后」。", options:{ breakLine:true, color:"FFFFFF", fontSize:11, paraSpaceAfter:10 } },
  { text:"结果：几乎所有工具的相关系数都接近 0、不显著（等于乱排）；个别显著的还是反向。", options:{ breakLine:true, color:"CADCFC", fontSize:11, paraSpaceAfter:10 } },
  { text:"对照 DS2（有阴有阳）头部还能排 → 工具的能力集中在「有反应 / 没反应」这道门槛上；一旦都是阳性、要比「谁更强」，门槛信息用完就失灵。", options:{ breakLine:true, color:"FFFFFF", fontSize:11, paraSpaceAfter:10 } },
  { text:"这正是「预测反应强弱」值得做的直接证据。", options:{ color:C.mint, fontSize:11.5, bold:true } },
], { x:8.58, y:2.3, w:3.95, h:4.5, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
pageno(s);

// ============================================================ S22 细看：肽长分层 + top-K 指标
s = pres.addSlide();
header(s, "再细看一层", "按肽段长度分开看 · 临床更关心的 top-K 命中率");
s.addShape(pres.shapes.RECTANGLE, { x:0.6, y:1.65, w:7.6, h:4.0, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIGD+"/fig_length_strat_auc.png", x:0.74, y:1.8, w:7.3, h:3.65, sizing:{type:"contain", w:7.3, h:3.65} });
s.addText("图：按子肽长度（8–14）分开算 AUC。PredIG（橙）在各长度都稳在 0.5 以上；多数工具随长度上下波动、部分跌破随机。", { x:0.62, y:5.55, w:7.6, h:0.45, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:0.6, y:6.05, w:7.6, h:0.95, fill:{color:"E6F4F1"}, line:{color:C.sea,width:1} });
s.addText([
  { text:"读法：", options:{ bold:true, color:C.teal, fontSize:11 } },
  { text:"长度分层后样本更小、波动更大，但能看出哪些工具的判别力对肽长稳健（PredIG 相对稳）。这一层主要用于诊断，不改变「整体偏弱」的主结论。", options:{ color:C.ink, fontSize:10.5 } },
], { x:0.8, y:6.12, w:7.25, h:0.82, fontFace:FB, valign:"middle", lineSpacingMultiple:1.03, margin:0 });
// 右：top-K 临床指标表
s.addText("临床更关心：top-K 命中率（PPV@K）", { x:8.4, y:1.7, w:4.4, h:0.4, fontFace:FH, fontSize:13.5, bold:true, color:C.ink, margin:0 });
const th = (t)=>({ text:t, options:{ fill:{color:C.dark}, color:"FFFFFF", bold:true, fontSize:10, align:"center", valign:"middle" } });
const tc = (t,col,b)=>({ text:t, options:{ color:col||C.ink, fontSize:10, align:"center", valign:"middle", bold:!!b } });
const ktbl = [
  [th("工具"), th("AUPRC"), th("PPV@10"), th("MCC")],
  [tc("pTuneos",C.ink,true), tc("0.949"), tc("1.00",C.ok,true), tc("0.280")],
  [tc("PredIG",C.ink,true),  tc("0.941"), tc("1.00",C.ok,true), tc("0.247")],
  [tc("NeoTImmuML",C.ink,true), tc("0.942"), tc("1.00",C.ok,true), tc("0.224")],
  [tc("IMPROVE",C.ink,true), tc("0.922"), tc("0.90"), tc("0.240")],
  [tc("DeepImmuno",C.ink,true), tc("0.895"), tc("0.90"), tc("0.082")],
];
s.addTable(ktbl, { x:8.4, y:2.2, w:4.35, colW:[1.5,1.0,0.95,0.9], rowH:[0.36,0.4,0.4,0.4,0.4,0.4],
  border:{pt:1,color:C.line}, align:"center", valign:"middle", fontFace:FB, fill:{color:C.card} });
s.addShape(pres.shapes.RECTANGLE, { x:8.4, y:4.85, w:4.35, h:2.05, fill:{color:"FBEEE4"}, line:{color:C.warn,width:1} });
s.addText([
  { text:"怎么读这些指标：", options:{ bold:true, color:C.warn, fontSize:11, breakLine:true } },
  { text:"PPV@10 = 把分数最高的 10 条挑出来，里面真有反应的比例（临床只能合成前几条，这个最实用）。AUPRC、MCC 是综合精确率指标。", options:{ color:C.ink, fontSize:10, breakLine:true, paraSpaceAfter:5 } },
  { text:"注意：阳性本就占 89%，AUPRC 起点就高、提升空间有限；这 5 个为第一批工具，新工具的 top-K 未单独计算。", options:{ color:C.muted, fontSize:9, italic:true } },
], { x:8.58, y:4.95, w:4.0, h:1.9, fontFace:FB, valign:"top", lineSpacingMultiple:1.03, margin:0 });
pageno(s);

// ============================================================ S23 HLAthena proxy 单列
s = pres.addSlide();
header(s, "提呈参照（单列）", "HLAthena：预测的是「提呈」不是「免疫原性」，单独看、不与前 8 个并比", C.warn);
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:1.78, w:7.5, h:5.05, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addText("在 ELISpot 上的表现（DS2）", { x:0.95, y:1.95, w:7.0, h:0.4, fontFace:FH, fontSize:15, bold:true, color:C.dark, margin:0 });
const hla = [
  ["AUC（取最大，阈值>0）","0.509","≈ 随机（0.5）",C.crit],
  ["AUC（各种口径范围）","0.49 – 0.59","没有一个明显离开随机",C.crit],
  ["与反应强度的相关","0.08 – 0.15","全都不显著",C.warn],
  ["AUPRC","0.890","数据本身阳性占比就 0.89，谈不上提升",C.warn],
];
let hy=2.5;
hla.forEach(r=>{
  s.addShape(pres.shapes.RECTANGLE, { x:0.95, y:hy, w:7.0, h:0.62, fill:{color:"F7FAFA"}, line:{color:C.line,width:1} });
  s.addShape(pres.shapes.RECTANGLE, { x:0.95, y:hy, w:0.08, h:0.62, fill:{color:r[3]} });
  s.addText(r[0], { x:1.15, y:hy+0.06, w:3.3, h:0.5, fontFace:FB, fontSize:11.5, bold:true, color:C.ink, valign:"middle", margin:0 });
  s.addText(r[1], { x:4.5, y:hy+0.06, w:1.3, h:0.5, fontFace:FH, fontSize:14, bold:true, color:r[3], valign:"middle", align:"center", margin:0 });
  s.addText(r[2], { x:5.85, y:hy+0.06, w:2.0, h:0.5, fontFace:FB, fontSize:9.5, italic:true, color:C.muted, valign:"middle", margin:0 });
  hy += 0.72;
});
s.addShape(pres.shapes.RECTANGLE, { x:0.95, y:5.5, w:7.0, h:1.18, fill:{color:"E6F4F1"}, line:{color:C.sea,width:1} });
s.addText([
  { text:"怎么理解：", options:{ bold:true, color:C.teal, fontSize:12 } },
  { text:"HLAthena 在免疫原性上接近随机，这恰恰符合它的本职 —— 它只预测「能否被提呈」，论文也明说不预测「能否激活 T 细胞」。所以它在这里只当提呈参照，", options:{ color:C.ink, fontSize:11 } },
  { text:"单列，不和 8 个免疫原性工具直接并比。", options:{ bold:true, color:C.dark, fontSize:11 } },
], { x:1.15, y:5.56, w:6.6, h:1.06, fontFace:FB, valign:"middle", lineSpacingMultiple:1.04, margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:8.4, y:1.78, w:4.35, h:5.05, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addText("覆盖度与工程说明", { x:8.65, y:1.95, w:3.9, h:0.4, fontFace:FH, fontSize:15, bold:true, color:C.warn, margin:0 });
s.addText([
  { text:"逐肽覆盖 100/101（98%）", options:{ bold:true, color:C.dark, fontSize:11.5, breakLine:true } },
  { text:"每条肽段取其所有子肽中的最高分，即使个别子肽缺失，逐肽结论依然稳。", options:{ color:C.ink, fontSize:10.5, breakLine:true, paraSpaceAfter:10 } },
  { text:"分块计算 266/336 完成", options:{ bold:true, color:C.dark, fontSize:11.5, breakLine:true } },
  { text:"在共享登录节点上跑，部分小任务因节点高负载被系统中止；因覆盖已达 98%，不影响「近随机」的结论。", options:{ color:C.ink, fontSize:10.5, breakLine:true, paraSpaceAfter:10 } },
  { text:"模型下载绕坑", options:{ bold:true, color:C.dark, fontSize:11.5, breakLine:true } },
  { text:"镜像自带的下载凭证已失效 → 改用匿名直链下模型、改配置走本地挂载，才跑通。", options:{ color:C.ink, fontSize:10.5, breakLine:true } },
], { x:8.65, y:2.45, w:3.9, h:4.3, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
citeFoot(s, "HLAthena, Nature Biotechnology 2020 · DOI 10.1038/s41587-019-0322-9 · 数字见 analysis/metrics_ds2_9tools.csv");
pageno(s);

// ============================================================ S24 诚实边界 + 许可红线
s = pres.addSlide();
header(s, "诚实边界", "已知限制与红线（先讲清楚）", C.warn);
const cav = [
  ["样本量很小","无反应样本只有 11 个 → 所有 AUC/相关的置信区间都偏宽，工具间不到 0.05 的差距不显著。这正是「没有稳定最优」结论的来源。",C.crit],
  ["数据有聚集","101 条肽来自 9 个病人，前两个病人贡献了约 45% 的阴性肽 → 有效样本数其实小于 101，AUC 可能部分在「区分病人」。需按病人分层复核。",C.warn],
  ["训练-测试可能重叠","第二批几个工具用公开库训练，可能与本测试集重叠；当前未排重，「独立性待核」。重叠会让分数偏高 → 对「新工具无增量」这个主结论反而更保守、更稳。",C.warn],
  ["完整度分级","DeepImmuno/PredIG/PRIME/ImmuneApp/deepHLApan 完整；pTuneos 用子模型；IMPROVE 特征降级；NeoTImmuML 自训版；MHLAPre 未完成。",C.teal],
];
let cy2=1.78;
cav.forEach(c=>{
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:cy2, w:7.9, h:1.18, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:cy2, w:0.09, h:1.18, fill:{color:c[2]} });
  s.addText(c[0], { x:0.98, y:cy2+0.14, w:2.0, h:0.9, fontFace:FH, fontSize:12.5, bold:true, color:c[2], valign:"top", margin:0 });
  s.addText(c[1], { x:2.95, y:cy2+0.12, w:5.5, h:0.95, fontFace:FB, fontSize:10.5, color:C.ink, valign:"middle", lineSpacingMultiple:1.04, margin:0 });
  cy2 += 1.28;
});
s.addShape(pres.shapes.RECTANGLE, { x:8.8, y:1.78, w:3.95, h:5.05, fill:{color:"4A1F24"}, shadow:sh() });
s.addText("⚠️ 许可红线", { x:9.05, y:2.0, w:3.5, h:0.4, fontFace:FH, fontSize:16, bold:true, color:"F2C2C7", margin:0 });
s.addText([
  { text:"netMHCpan / netMHCstabpan", options:{ bold:true, color:"FFFFFF", fontSize:12.5, breakLine:true } },
  { text:"= DTU 学术许可。未经书面同意，不得把在其软件上跑出的结果（含数字）对外发布。", options:{ color:"F2C2C7", fontSize:11, breakLine:true, paraSpaceAfter:12 } },
  { text:"本项目正是基准评测", options:{ bold:true, color:"FFFFFF", fontSize:12.5, breakLine:true } },
  { text:"→ 论文或对外材料若含这些工具跑出的对比数字，须先取 DTU 书面同意（投稿阶段处理）。", options:{ color:"F2C2C7", fontSize:11, breakLine:true, paraSpaceAfter:12 } },
  { text:"deepHLApan = GPL-2.0", options:{ bold:true, color:"FFFFFF", fontSize:12.5, breakLine:true } },
  { text:"公开发布前需做许可合规审查。", options:{ color:"F2C2C7", fontSize:11 } },
], { x:9.05, y:2.5, w:3.55, h:4.2, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
pageno(s);

// ============================================================ S25 参考文献
s = pres.addSlide();
header(s, "参考文献", "10 个工具的论文出处与代码仓库");
const refs = [
  ["DeepImmuno","Briefings in Bioinformatics 2021","10.1093/bib/bbab160","github.com/frankligy/DeepImmuno"],
  ["PredIG","Genome Medicine 2025","10.1186/s13073-025-01569-8","github.com/BSC-CNS-EAPM/PredIG"],
  ["pTuneos","Genome Medicine 2019","10.1186/s13073-019-0679-x","github.com/bm2-lab/pTuneos"],
  ["IMPROVE","Frontiers in Immunology 2024","10.3389/fimmu.2024.1360281","github.com/SRHgroup/IMPROVE_tool"],
  ["NeoTImmuML","Frontiers in Immunology 2025","10.3389/fimmu.2025.1681396","github.com/01SYan19/NeoTImmuML"],
  ["PRIME","Cell Rep. Med. 2021 / Cell Systems 2023","10.1016/j.celrep.2021.100194","github.com/GfellerLab/PRIME"],
  ["ImmuneApp","Nature Communications 2024","10.1038/s41467-024-53296-0","github.com/bsml320/ImmuneApp"],
  ["deepHLApan","Frontiers in Immunology 2019","10.3389/fimmu.2019.02559","github.com/jiujiezz/deephlapan"],
  ["MHLAPre","Briefings in Bioinformatics 2024","10.1093/bib/bbae625","github.com/ChanganMakeYi/MHLAPre"],
  ["HLAthena","Nature Biotechnology 2020","10.1038/s41587-019-0322-9","hlathena.tools · Docker ssarkizova/hlathena-external"],
];
const rh = (t)=>({ text:t, options:{ fill:{color:C.dark}, color:"FFFFFF", bold:true, fontSize:11, align:"left", valign:"middle" } });
const rc = (t,b)=>({ text:t, options:{ color:C.ink, fontSize:10, align:"left", valign:"middle", bold:!!b } });
const rcLink = (t,url)=>({ text:t, options:{ color:"1C7293", fontSize:10, align:"left", valign:"middle", hyperlink:{ url, tooltip:url } } });
const reftbl = [[rh(" 工具"), rh("发表期刊 / 年份"), rh("DOI（可点击）"), rh("代码仓库（可点击）")]];
refs.forEach(r=> reftbl.push([rc(" "+r[0],true), rc(r[1]), rcLink(r[2],"https://doi.org/"+r[2]), rcLink(r[3],"https://"+r[3].split(" ")[0])]));
s.addTable(reftbl, { x:0.7, y:1.75, w:11.95, colW:[1.85,3.1,2.85,4.15],
  rowH:[0.4,0.44,0.44,0.44,0.44,0.44,0.44,0.44,0.44,0.44,0.44],
  border:{pt:1,color:C.line}, align:"left", valign:"middle", fontFace:FB, fill:{color:C.card}, margin:[2,4,2,4] });
s.addText("外部依赖工具：netMHCpan / netMHCstabpan（DTU Health Tech，学术许可）· MixMHCpred（Gfeller lab）· Ensembl VEP · R Peptides 包。数据集与本地产物为课题组内部数据，不在此列。", { x:0.7, y:6.75, w:11.95, h:0.5, fontFace:FB, fontSize:9.5, italic:true, color:C.muted, valign:"top", margin:0 });
pageno(s);

// ============================================================ S22 结论 + 下一步
s = pres.addSlide();
s.background = { color: C.dark };
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.mint} });
s.addText("结论与下一步", { x:0.9, y:0.7, w:10, h:0.7, fontFace:FH, fontSize:32, bold:true, color:"FFFFFF", margin:0 });
s.addText("已经完成", { x:0.9, y:1.85, w:5.5, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"10 个工具全部部署 + 四类信息全收集（逐工具文档齐）", options:{ bullet:{indent:14}, breakLine:true, color:"FFFFFF", fontSize:12.5, paraSpaceAfter:6 } },
  { text:"9 个跑进统一 ELISpot 基准；唯一 MHLAPre 因缺权重未完成（已尽力核实、留可行出路）", options:{ bullet:{indent:14}, breakLine:true, color:"FFFFFF", fontSize:12.5, paraSpaceAfter:6 } },
  { text:"主结论：8 个免疫原性工具判别力普遍偏弱、彼此分不出显著高下、新工具无增量", options:{ bullet:{indent:14}, breakLine:true, color:"FFFFFF", fontSize:12.5, paraSpaceAfter:6 } },
  { text:"HLAthena（提呈 proxy）近随机，印证「提呈 ≠ 免疫原性」，单列参照", options:{ bullet:{indent:14}, breakLine:true, color:"FFFFFF", fontSize:12.5, paraSpaceAfter:6 } },
  { text:"现有工具几乎不能预测「反应有多强」→ 反过来说明做「强弱定量」这件事有空白、有价值", options:{ bullet:{indent:14}, color:C.mint, fontSize:12.5, bold:true } },
], { x:0.9, y:2.35, w:5.85, h:4.5, fontFace:FB, valign:"top", margin:0 });
s.addText("下一步", { x:7.0, y:1.85, w:5.5, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.warn, margin:0 });
const ns=[
  ["先核连续标签够不够","要做「强弱回归」，先确认公开库里带强度标签的数据量够不够 —— 这是方向的总开关，零算力"],
  ["补充阴性样本","测试集无反应样本仅 11 个 → 补到 ≥30 再重测，结论更稳"],
  ["排查训练-测试重叠","把测试肽与公开训练库做精确比对，报告重叠比例"],
  ["接入正式数据","课题组正式数据到位后，按各工具格式转换再正式测一轮"],
  ["对外许可","投稿前取 DTU 书面同意（netMHCpan 相关数字）"],
];
let ny=2.35;
ns.forEach(g=>{
  s.addShape(pres.shapes.RECTANGLE, { x:7.0, y:ny, w:5.5, h:0.86, fill:{color:"123F4B"}, line:{color:"1C5563",width:1} });
  s.addShape(pres.shapes.RECTANGLE, { x:7.0, y:ny, w:0.08, h:0.86, fill:{color:C.warn} });
  s.addText(g[0], { x:7.25, y:ny+0.1, w:5.1, h:0.32, fontFace:FH, fontSize:12.5, bold:true, color:"FFFFFF", margin:0 });
  s.addText(g[1], { x:7.25, y:ny+0.42, w:5.1, h:0.4, fontFace:FB, fontSize:9.5, color:"9FD9CF", valign:"top", margin:0 });
  ny += 0.96;
});
s.addText("基准数字均经 csv 三方核对；逐工具四类信息见 TOOLS/ 目录；工具论文出处见参考文献页。", { x:0.9, y:7.05, w:11.5, h:0.35, fontFace:FB, fontSize:9.5, italic:true, color:"6E9AA1", margin:0 });
pageno(s);

// ---------- write ----------
pres.writeFile({ fileName: "D:/YJ-Agent/project/meeting/QuantImmuBench/QuantImmuBench_10工具横评_2026-06-25.pptx" })
  .then(f=>console.log("WROTE", f))
  .catch(e=>{ console.error("ERR", e); process.exit(1); });
