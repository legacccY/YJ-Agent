// QuantImmuBench — 新增 7 工具横评报告 v2（5 工具版式 + pooling 评判专章）2026-06-27
// 范围：BigMHC / CNNeo / MHCflurry / IEDB_Calis / Repitope / T-SCAPE / netMHCpan-BA
// 主榜 max 聚合口径（与全项目交付同口径）；pooling 专章结合朱同学研究揭示 count-safe 潜力
// 数字：analysis/metrics_ds2_16tools.csv + NEWTOOLS_ANALYSIS.md + SPEARMAN_ZHU_INTEGRATED.md（均已核 csv）
// 运行: NODE_PATH=C:/Users/yj200/AppData/Roaming/npm/node_modules node gen_ppt_newtools_v2.js
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "新抗原免疫原性预测工具 — 新增 7 工具横评报告";

const W = 13.33, H = 7.5;
const C = {
  dark:"0B3C49", teal:"028090", sea:"00A896", mint:"02C39A",
  light:"F2F7F7", card:"FFFFFF", ink:"16323A", muted:"5E7B83",
  line:"D5E3E4", warn:"C9743D", ok:"00A896", crit:"B23A48", gray:"8A9BA0",
};
const FH = "Microsoft YaHei", FB = "Microsoft YaHei", FM = "Consolas";
const FIG = "D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/figures";
const sh = () => ({ type:"outer", color:"0B3C49", blur:9, offset:3, angle:135, opacity:0.12 });

let _PG = 1;
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
function badge(slide, x, y, txt, col, w=2.5){
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h:0.42, rectRadius:0.21, fill:{color:col} });
  slide.addText(txt, { x, y, w, h:0.42, fontFace:FB, fontSize:11.5, bold:true, color:"FFFFFF", align:"center", valign:"middle", margin:0 });
}
function citeFoot(slide, txt){
  const runs=[{ text:"来源  ", options:{ color:C.teal, fontSize:9, bold:true } }];
  txt.split(" · ").forEach((p,i)=>{
    let opt={ color:C.muted, fontSize:9 };
    const dm=p.match(/DOI\s+(10\.\S+)/);
    const gm=p.match(/(github\.com\/\S+|hlathena\.tools\S*|services\.healthtech\S*)/);
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
// 工作原理页（N=7）
function principleSlide(o){
  const s = pres.addSlide();
  header(s, "工具 "+o.idx+" / 7 · 工作原理", o.name, o.accent);
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
  codeBox(s, 6.85, 5.42, 5.75, 1.5, "输出数据样例", o.outFmt);
  citeFoot(s, o.cite);
  pageno(s);
}
// 4类信息页（N=7）
function toolSlide(o){
  const s = pres.addSlide();
  header(s, "工具 "+o.idx+" / 7 · 四类信息", o.name, o.accent);
  s.addText(o.tagline, { x:0.7, y:1.46, w:8.6, h:0.5, fontFace:FB, fontSize:13, color:C.muted, margin:0 });
  badge(s, W-3.2, 0.72, o.status, o.statusCol, 2.5);
  s.addText("方法  "+o.method, { x:W-3.2, y:1.22, w:2.5, h:0.3, fontFace:FB, fontSize:11, color:C.teal, bold:true, align:"center", margin:0 });
  const cx=0.7, cy=2.0, cw=6.0, ch=2.28, gap=0.3;
  infoCard(s, cx,        cy,        cw, ch, "① 输入数据 / 格式", o.input,  o.accent);
  infoCard(s, cx+cw+gap, cy,        cw, ch, "② 运行参数",       o.params, o.accent);
  infoCard(s, cx,        cy+ch+gap, cw, ch, "③ 输出格式 / 含义", o.output, o.accent);
  infoCard(s, cx+cw+gap, cy+ch+gap, cw, ch, "④ 为什么选作对比",  o.intro,  o.accent);
  citeFoot(s, o.cite);
  pageno(s);
}
function figSlide(kicker, title, accent, img, notes, noteHead){
  const s = pres.addSlide();
  header(s, kicker, title, accent);
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:1.7, w:7.4, h:5.2, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addImage({ path:img, x:0.85, y:1.85, w:7.1, h:4.9, sizing:{type:"contain", w:7.1, h:4.9} });
  infoCard(s, 8.35, 1.7, 4.28, 5.2, noteHead||"读图要点", notes, accent);
  pageno(s);
}

// ============================================================ 封面
let s = pres.addSlide();
s.background = { color: C.dark };
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.mint} });
s.addShape(pres.shapes.OVAL, { x:W-3.3, y:-1.6, w:4.6, h:4.6, fill:{color:C.teal, transparency:78} });
s.addShape(pres.shapes.OVAL, { x:W-2.0, y:3.6,  w:3.2, h:3.2, fill:{color:C.sea,  transparency:82} });
s.addText("癌症个性化新抗原疫苗 · 预测工具部署与基准评估", { x:0.9, y:1.5, w:11, h:0.4, fontFace:FB, fontSize:15, color:C.mint, bold:true, charSpacing:2, margin:0 });
s.addText("新增 7 个对比工具\n部署测试 · 基准评估 · pooling 评判", { x:0.9, y:2.05, w:11.5, h:1.8, fontFace:FH, fontSize:40, bold:true, color:"FFFFFF", lineSpacingMultiple:1.05, margin:0 });
s.addText("BigMHC · CNNeo · MHCflurry · IEDB_Calis · Repitope · T-SCAPE · netMHCpan-BA", { x:0.9, y:4.3, w:11.8, h:0.5, fontFace:FB, fontSize:14, color:"CADCFC", margin:0 });
s.addShape(pres.shapes.LINE, { x:0.95, y:5.1, w:3.2, h:0, line:{color:C.mint, width:2} });
s.addText([
  { text:"内容  ", options:{ color:"8FB7BD", fontSize:13 } },
  { text:"逐工具部署 + 工作原理 + 四类信息 + 为什么选作对比 · 结合朱同学 pooling 研究的 spearman 评判", options:{ color:"FFFFFF", fontSize:13, breakLine:true } },
  { text:"定位  ", options:{ color:"8FB7BD", fontSize:13 } },
  { text:"在原 10 工具横评基础上扩充方法学多样性", options:{ color:"FFFFFF", fontSize:13 } },
], { x:0.95, y:5.35, w:10.5, h:1.0, fontFace:FB, valign:"top", margin:0 });
s.addText("2026-06-27", { x:W-2.4, y:6.7, w:1.8, h:0.3, fontFace:FB, fontSize:12, color:"8FB7BD", align:"right", margin:0 });

// ============================================================ 目录
s = pres.addSlide();
header(s, "目录", "本报告的内容结构");
const toc = [
  ["01","为什么扩这 7 个","方法学演化光谱 + 文献矩阵"],
  ["02","工具逐一解析","每个工具的工作原理 + 四类信息"],
  ["03","数据与评测方法","测试数据来源、评测流程、指标说明"],
  ["04","基准结果","判别力 AUC + 能否定量 Spearman"],
  ["05","pooling 评判专章","结合朱同学：换 pooling 如何改变排序"],
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

// ============================================================ 背景：为什么扩工具
s = pres.addSlide();
header(s, "项目背景", "为什么在 10 工具之外再扩 7 个");
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:1.7, w:5.55, h:2.55, fill:{color:C.dark}, shadow:sh() });
s.addText("目标回顾", { x:0.98, y:1.9, w:5, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"做一个能预测 T 细胞反应 ", options:{ color:"FFFFFF", fontSize:13.5 } },
  { text:"「强弱程度」", options:{ color:C.mint, fontSize:16, bold:true } },
  { text:" 的工具。", options:{ color:"FFFFFF", fontSize:13.5, breakLine:true } },
  { text:"benchmark 路线 = 大量跑现有工具，钉死它们的定量能力上限，再立项自研。", options:{ color:"CADCFC", fontSize:12, breakLine:true } },
], { x:0.98, y:2.36, w:5.05, h:1.8, fontFace:FB, valign:"top", lineSpacingMultiple:1.18, margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:4.45, w:5.55, h:2.55, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addText("为什么不止 10 个工具", { x:0.95, y:4.6, w:5, h:0.34, fontFace:FH, fontSize:14, bold:true, color:C.teal, margin:0 });
s.addText([
  { text:"原 10 工具多为「浅层 ML / 早期 CNN 直接拟合免疫原性」一类方法。", options:{ color:C.ink, fontSize:11.5, breakLine:true, paraSpaceAfter:5 } },
  { text:"要让 benchmark 有说服力，必须覆盖更多方法学范式——统计、纯结合、提呈、LLM、大模型迁移、多域结构。", options:{ color:C.ink, fontSize:11.5, breakLine:true, paraSpaceAfter:5 } },
  { text:"新增 7 个工具各占一格生态位，把方法学谱系填满。", options:{ color:C.dark, fontSize:11.5, bold:true } },
], { x:0.95, y:4.98, w:5.2, h:1.95, fontFace:FB, valign:"top", lineSpacingMultiple:1.1, margin:0 });
infoCard(s, 6.55, 1.7, 6.08, 5.3, "新增 7 工具一览（主榜 max 口径 AUC）", [
  "IEDB_Calis · 经典氨基酸统计基线（2013）· AUC 0.449",
  "Repitope · 唯一 HLA-agnostic 路线（2019）· AUC 0.620",
  "netMHCpan-BA · 纯结合亲和力金标准（2020）· AUC 0.419 ⚠️DTU",
  "MHCflurry · 社区金标准提呈代理（2020）· AUC 0.432",
  "CNNeo · LLM(BioBERT) 增强 CNN（2026）· AUC 0.382",
  "BigMHC · 大规模迁移学习 ensemble（2023）· AUC 0.396",
  "T-SCAPE · 多域对抗 DL，2025 SOTA · AUC 0.362 ⚠️NC-ND",
], C.teal);
pageno(s);

// ============================================================ 方法学演化光谱
s = pres.addSlide();
header(s, "为什么扩这 7 个", "一条方法学演化主轴，每个工具占一格生态位");
const spectrum = [
  ["IEDB_Calis","经典统计","氨基酸理化富集，无 ML，2013 历史临界线", C.gray],
  ["Repitope","HLA-agnostic","不问 HLA，测肽序列本身免疫原潜力", C.sea],
  ["netMHCpan-BA","纯结合亲和力","验证「结合≠免疫原性」核心命题", C.warn],
  ["MHCflurry","提呈代理","检验「能提呈能否当强弱代理」", C.teal],
  ["CNNeo","LLM 增强","BioBERT 序列表征，2026 最新", C.mint],
  ["BigMHC","大规模迁移","提呈预训练→免疫原性迁移，Nat MI", C.sea],
  ["T-SCAPE","多域结构 SOTA","TCR-pMHC+激活信号四路对抗融合", C.crit],
];
spectrum.forEach((it,i)=>{
  const y = 1.85 + i*0.72;
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y, w:11.9, h:0.62, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y, w:0.09, h:0.62, fill:{color:it[3]} });
  s.addText(String(i+1), { x:0.9, y, w:0.5, h:0.62, fontFace:FH, fontSize:18, bold:true, color:it[3], align:"center", valign:"middle", margin:0 });
  s.addText(it[0], { x:1.5, y, w:2.6, h:0.62, fontFace:FH, fontSize:14, bold:true, color:C.ink, valign:"middle", margin:0 });
  s.addText(it[1], { x:4.1, y, w:2.3, h:0.62, fontFace:FB, fontSize:12, bold:true, color:it[3], valign:"middle", margin:0 });
  s.addText(it[2], { x:6.4, y, w:6.0, h:0.62, fontFace:FB, fontSize:11, color:C.muted, valign:"middle", margin:0 });
});
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:6.95, w:11.9, h:0.0, line:{color:C.line,width:0} });
pageno(s);

// ============================================================ 01 文献矩阵
s = pres.addSlide();
header(s, "01 文献矩阵", "7 个新增对比工具 — 论文出处 · repo · 许可");
const _litRows = [
  [{text:"工具",options:{bold:true,fill:{color:C.dark},color:"FFFFFF",fontFace:FH,fontSize:10,align:"center",valign:"middle"}},
   {text:"年 · 期刊",options:{bold:true,fill:{color:C.dark},color:"FFFFFF",fontFace:FH,fontSize:10,align:"center",valign:"middle"}},
   {text:"DOI",options:{bold:true,fill:{color:C.dark},color:"FFFFFF",fontFace:FH,fontSize:10,align:"center",valign:"middle"}},
   {text:"官方 repo / web",options:{bold:true,fill:{color:C.dark},color:"FFFFFF",fontFace:FH,fontSize:10,align:"center",valign:"middle"}},
   {text:"许可",options:{bold:true,fill:{color:C.dark},color:"FFFFFF",fontFace:FH,fontSize:10,align:"center",valign:"middle"}}],
  [{text:"IEDB_Calis",options:{bold:true,color:C.teal}},{text:"2013 · PLOS Comput Biol"},{text:"10.1371/journal.pcbi.1003266"},{text:"tools.iedb.org/immunogenicity"},{text:"NPOSL-3.0 ✅"}],
  [{text:"Repitope",options:{bold:true,color:C.teal}},{text:"2019 · Front Immunol"},{text:"10.3389/fimmu.2019.00827"},{text:"github.com/masato-ogishi/Repitope"},{text:"MIT ✅"}],
  [{text:"netMHCpan-BA",options:{bold:true,color:C.warn}},{text:"2020 · Nucleic Acids Res"},{text:"10.1093/nar/gkaa379"},{text:"services.healthtech.dtu.dk/NetMHCpan-4.1"},{text:"⚠️ DTU 学术·禁再分发"}],
  [{text:"MHCflurry 2.0",options:{bold:true,color:C.teal}},{text:"2020 · Cell Systems"},{text:"10.1016/j.cels.2020.06.010"},{text:"github.com/openvax/mhcflurry"},{text:"Apache-2.0 ✅"}],
  [{text:"CNNeo / CNNeoPP",options:{bold:true,color:C.teal}},{text:"2026 · Front Immunol"},{text:"10.3389/fimmu.2026.1722117"},{text:"github.com/AaronChen007/neoantigen"},{text:"MIT ✅"}],
  [{text:"BigMHC (-m=im)",options:{bold:true,color:C.teal}},{text:"2023 · Nature MI"},{text:"10.1038/s42256-023-00694-6"},{text:"github.com/KarchinLab/bigmhc"},{text:"学术非商用 ✅"}],
  [{text:"T-SCAPE",options:{bold:true,color:C.crit}},{text:"2025 · Science Advances"},{text:"10.1126/sciadv.adz8759"},{text:"github.com/seoklab/T-SCAPE"},{text:"⚠️ CC-BY-NC-ND"}],
];
s.addTable(_litRows, {x:0.6,y:1.75,w:11.8,colW:[1.6,2.0,3.0,3.2,2.0],rowH:0.6,border:{type:"solid",color:C.line,pt:0.5},fontFace:FB,fontSize:9.5,color:C.ink,valign:"middle"});
pageno(s);

// ============================================================ 01 横评总表
s = pres.addSlide();
header(s, "01 横评总表", "7 新工具 — 方法范式 · 判别力 · 定量能力 · 许可");
const _sumRows = [
  [{text:"工具",options:{bold:true,fill:{color:C.dark},color:"FFFFFF",fontFace:FH,fontSize:10,align:"center",valign:"middle"}},
   {text:"方法范式",options:{bold:true,fill:{color:C.dark},color:"FFFFFF",fontFace:FH,fontSize:10,align:"center",valign:"middle"}},
   {text:"能否定量",options:{bold:true,fill:{color:C.dark},color:"FFFFFF",fontFace:FH,fontSize:10,align:"center",valign:"middle"}},
   {text:"AUC(max,>0)",options:{bold:true,fill:{color:C.dark},color:"FFFFFF",fontFace:FH,fontSize:10,align:"center",valign:"middle"}},
   {text:"许可",options:{bold:true,fill:{color:C.dark},color:"FFFFFF",fontFace:FH,fontSize:10,align:"center",valign:"middle"}}],
  [{text:"IEDB_Calis",options:{bold:true}},{text:"经典统计线性加权，无 ML"},{text:"✅ 连续分可排名"},{text:"0.449",options:{align:"center"}},{text:"NPOSL-3.0 ✅"}],
  [{text:"Repitope",options:{bold:true}},{text:"HLA-agnostic CPP + ERT"},{text:"✅ 0-1 连续"},{text:"0.620",options:{align:"center",bold:true,color:C.teal}},{text:"MIT ✅"}],
  [{text:"netMHCpan-BA",options:{bold:true,color:C.warn}},{text:"Pan-allele 神经网络（结合亲和力）"},{text:"✅ 连续可排名"},{text:"0.419",options:{align:"center"}},{text:"⚠️ DTU pending"}],
  [{text:"MHCflurry 2.0",options:{bold:true}},{text:"提呈代理神经网络（双分数）"},{text:"⚠️ 间接代理"},{text:"0.432",options:{align:"center"}},{text:"Apache-2.0 ✅"}],
  [{text:"CNNeo / CNNeoPP",options:{bold:true}},{text:"BioBERT 序列嵌入 + TextCNN"},{text:"✅ 0-1 连续"},{text:"0.382",options:{align:"center"}},{text:"MIT ✅"}],
  [{text:"BigMHC (-m=im)",options:{bold:true}},{text:"大规模迁移学习 7-ckpt ensemble"},{text:"✅ 0-1 连续"},{text:"0.396",options:{align:"center"}},{text:"学术非商用 ✅"}],
  [{text:"T-SCAPE",options:{bold:true,color:C.crit}},{text:"ByteNet 跨域辅助多任务 DL"},{text:"✅ 0-1 连续"},{text:"0.362 ⚠️",options:{align:"center",color:C.crit}},{text:"⚠️ CC-BY-NC-ND"}],
];
s.addTable(_sumRows, {x:0.6,y:1.75,w:11.4,colW:[2.0,3.4,1.8,1.6,2.6],rowH:0.6,border:{type:"solid",color:C.line,pt:0.5},fontFace:FB,fontSize:9.5,color:C.ink,valign:"middle"});
s.addText("注：Repitope 0.620 = 新工具最高；全组新工具未突破旧工具天花板（pTuneos 0.719）；TSCAPE 0.362 + Spearman 全聚合负 → 方向待核", {x:0.7,y:6.55,w:11.4,h:0.42,fontFace:FB,fontSize:9,color:C.muted,margin:0});
pageno(s);

// ============================================================ 02 工具 1/7 IEDB_Calis
principleSlide({
  idx:1, name:"IEDB Immunogenicity (Calis 2013)", accent:C.teal,
  sub:"经典统计基线 · 无 ML · 被主流新抗原流水线默认集成 · NPOSL-3.0",
  inP:"纯文本肽序列列表（大写氨基酸，一行一肽）+ HLA allele 命令行参数（--allele=HLA-A0201）\n8–15mer 均有分，65 allele，0 NaN；每次调用处理一个 allele",
  modelP:"各位置氨基酸 immunogenicity propensity 分值线性加权求和\nallele-specific anchor mask 屏蔽 HLA 锚位（P1/P2/C-term）\n无 ML 无梯度无权重文件，纯统计，秒级完成",
  outP:"immunogenicity score（无硬边界，通常 -1.5~+1.5），越高越免疫原\n实测 34247 行 0 NaN；AUC(max,>0) 0.449",
  cmd:["python predict_immunogenicity.py \\","  --allele=HLA-A0201 \\","  HLA-A0201.txt"],
  inFmt:["# 纯文本，一行一肽","FIAGLIAIV","LITGRLQSL","NLVPMVATV"],
  outFmt:["peptide,length,score","FIAGLIAIV,9,0.45678","LITGRLQSL,9,0.23456","NLVPMVATV,9,0.12345"],
  cite:"IEDB Immunogenicity, PLOS Comput Biol 2013 · DOI 10.1371/journal.pcbi.1003266 · tools.iedb.org/immunogenicity"
});
toolSlide({
  idx:1, name:"IEDB Immunogenicity (Calis 2013)", accent:C.teal,
  method:"线性统计（无 ML）", status:"RUN_DONE · AUC 0.449", statusCol:C.ok,
  tagline:"2013 历史对照基准 · 任何新工具不超过它即可判无效",
  input:["格式：纯文本 .txt，每行一肽（大写 20 种氨基酸，无表头）",
         "HLA 格式：去 * 去 :（如 HLA-A*02:01 → HLA-A0201）",
         "肽长：8–15mer 均有分（8/10mer+ 有特殊位置调整规则）",
         "每次调用处理一个 allele，benchmark 共 65 allele，秒级全量"],
  params:["--allele=HLA-A0201  使用 allele-specific anchor mask（42 个已知 allele）",
          "不加 --allele  回退默认 mask（P1, P2, C-term）",
          "纯 Python 3，无需 pip/GPU/权重文件，pip free",
          "流水线：prep_input.py → run_iedb_calis.sh → parse_output.py"],
  output:["score 连续无界（通常 -1.5~+1.5），越高越免疫原，直接用",
          "列：MT_IEDB_Calis / WT_IEDB_Calis（浮点无界）",
          "实测：34247 行，0 NaN；65 allele 全覆盖",
          "产物：IEDB_Calis_DS1DS2_scores.csv"],
  intro:["建立 2013 年历史基准——现代 DL 工具须显著高于此线才算真进步",
         "被 pVACseq / iNeo-Suite 等主流新抗原流水线默认集成，引用频次最高经典基准",
         "任何工具 AUC 不超过 0.449 即可判定方法无贡献",
         "NPOSL-3.0，数字完全自由发布，无 DTU 限制"],
  cite:"IEDB Immunogenicity, PLOS Comput Biol 2013 · DOI 10.1371/journal.pcbi.1003266 · tools.iedb.org/immunogenicity"
});

// ============================================================ 02 工具 2/7 Repitope
principleSlide({
  idx:2, name:"Repitope (2019)", accent:C.sea,
  sub:"唯一 HLA-agnostic 路线 · CPP 接触势 + ERT · MIT 许可",
  inP:"仅需肽段序列（8–11mer，大写氨基酸），不接受 HLA allele 输入\n12–14mer → NaN；需下载预计算文件（Mendeley，~127MB）",
  modelP:"Contact Potential Profiling（CPP）：用公开 TCR CDR3b 库模拟整个人群 TCR 对肽的 in-silico 接触势能\n32 个最小特征；25 个 Extremely Randomized Trees（ERT）ensemble\n训练于 MHCI_Human（~7000 肽，IEDB 等公开标注）",
  outP:"ImmunogenicityScore ∈ [0,1]，越高越免疫原\n实测：22391 行有分（8–11mer），12–14mer NaN，分数范围 0.06–0.61",
  cmd:["set RSCRIPT=E:\\R-4.3.3\\bin\\Rscript.exe","Rscript run_repitope.R \\","  --input repitope_input.csv \\","  --frag-lib FragmentLibrary.fst \\","  --feature-df FeatureDF_Weighted.10000.fst \\","  --cores 6"],
  inFmt:["peptide","SIINFEKL","LITGRLQSL","FIAGLIAIV"],
  outFmt:["Peptide,ImmunogenicityScore,ImmunogenicityScore.cv","SIINFEKL,0.421,0.087","LITGRLQSL,0.338,0.092","FIAGLIAIV,0.195,0.104"],
  cite:"Repitope, Front Immunol 2019 · DOI 10.3389/fimmu.2019.00827 · github.com/masato-ogishi/Repitope"
});
toolSlide({
  idx:2, name:"Repitope (2019)", accent:C.sea,
  method:"HLA-agnostic CPP + ERT", status:"RUN_DONE · AUC 0.620", statusCol:C.ok,
  tagline:"不问 HLA，测肽序列本身的免疫原性潜力——新工具最高 AUC",
  input:["仅需肽序列（8–11mer 大写氨基酸），不接受 HLA allele 输入",
         "数据依赖：FragmentLibrary.fst + MHCI/FeatureDF_Weighted.10000.fst（Mendeley DOI 10.17632/sydw5xnxpt.1）",
         "12–14mer → NaN（超训练长度限制，benchmark ~11856 行 NaN）",
         "实测输入：7437 个唯一 8–11mer 肽（从 universe 过滤）"],
  params:["--cores N  并行核数（建议 6–8，加速 CPP 特征计算）",
          "--smoke N  仅取前 N 肽快速验格式",
          "featureSet = MHCI_Human_MinimumFeatureSet（32 特征，大幅加速）",
          "每次运行重训 25 个 ERT 模型，约 5–20min（无预存权重）"],
  output:["ImmunogenicityScore ∈ [0,1]，越高越免疫原，直接用",
          "⚠️ HLA-agnostic：同肽对所有 HLA_Allele 行填相同值（须在报告标注）",
          "实测：34247 行；22391 行有分；12–14mer NaN；分数 0.06–0.61",
          "产物：Repitope_DS1DS2_scores.csv（MT_Repitope / WT_Repitope）"],
  intro:["原 10 工具几乎全 HLA-aware；Repitope 是唯一 HLA-agnostic 路线，补方法学空白",
         "量化「HLA 限制信息到底值多少」：不差 = 序列内在特征够用；很差 = HLA 限制是关键",
         "MIT 许可，部署零障碍（无 DTU 学术许可申请）",
         "AUC 0.620 = 7 新工具最高，与旧工具前列持平；per-patient fisherz 0.119（CI 含 0）"],
  cite:"Repitope, Front Immunol 2019 · DOI 10.3389/fimmu.2019.00827 · github.com/masato-ogishi/Repitope"
});

// ============================================================ 02 工具 3/7 netMHCpan-BA
principleSlide({
  idx:3, name:"netMHCpan-4.1 BA mode (2020)", accent:C.warn,
  sub:"纯结合亲和力金标准 · 验证「结合 ≠ 免疫原性」核心命题 · ⚠️ DTU 禁再分发",
  inP:"肽序列文件（一行一肽）+ --allele HLA 参数；BA mode 专测结合亲和力\n覆盖 >18,000 等位基因（pan-allele），8–14mer；HPC Linux 二进制",
  modelP:"Pan-allele 神经网络，训练于大规模 HLA-肽结合亲和力 + MS 洗脱配体数据\nBA mode 仅输出结合亲和力（nM）；不直接预测 T 细胞免疫原性\n等位基因由伪序列表示（pseudosequence）泛化覆盖",
  outP:"Score_BA（越高越不结合）、Aff_BA（nM 越低越强结合）、Rank_BA（%ile）\n取负后与免疫强弱正向对齐；AUC(max,>0) 0.419，mean 聚合 Spearman +0.381 全场最强",
  cmd:["# HPC Linux 原生二进制","netMHCpan -BA \\","  -a HLA-A0201 \\","  -p peptides.txt \\","  -l 9"],
  inFmt:["# 肽序列文件（一行一肽）","FIAGLIAIV","LITGRLQSL","NLVPMVATV"],
  outFmt:["# Allele  Pos  Peptide  ...  Score_BA  Rank_BA  Aff_BA(nM)","HLA-A*02:01  0  FIAGLIAIV  ...  0.123  0.50  150.2","HLA-A*02:01  0  LITGRLQSL  ...  0.087  1.20  280.4"],
  cite:"netMHCpan-4.1, Nucleic Acids Res 2020 · DOI 10.1093/nar/gkaa379 · services.healthtech.dtu.dk/services/NetMHCpan-4.1"
});
toolSlide({
  idx:3, name:"netMHCpan-4.1 BA mode (2020)", accent:C.warn,
  method:"Pan-allele 神经网络（结合亲和力）", status:"RUN_DONE · ⚠️ DTU pending", statusCol:C.warn,
  tagline:"纯结合亲和力 vs ELISpot 真实反应——验证核心方法学命题",
  input:["肽序列文件（一行一肽）+ -a HLA-A0201 等位基因参数（BA mode）",
         "覆盖 >18,000 等位基因（pan-allele 伪序列泛化）",
         "HPC Linux 二进制（Windows 不支持 DTU 原生二进制）",
         "本 benchmark 在 HPC el8 原生跑通（netMHCpan-4.1 test.pep PASS）"],
  params:["netMHCpan -BA  启用结合亲和力预测模式（-EL 为 eluted ligand）",
          "-a HLA-A0201  指定等位基因（支持 batch 多 allele）",
          "-l 9  肽长（8–14 均支持）",
          "-p 肽文件输入；-f fasta 格式；-v verbose"],
  output:["Score_BA：取负 → MT_netmhcpan_ba（越高越强结合，越应免疫原）",
          "Rank_BA：%ile 排名（越低=越强结合）",
          "Aff_BA(nM)：预测亲和力（越低越强）",
          "⚠️ mean 聚合 Spearman +0.381 p=0.0003 全场最强，但 DTU pending + 聚合敏感"],
  intro:["直接检验本 benchmark 最重要命题：「结合亲和力 ≠ 免疫原性」",
         "量化纯结合信号与真实 ELISpot 的 gap，为整合 TCR/加工信号工具提供提升参照系",
         "新抗原流水线最广用上游工具，等位基因覆盖业内最多",
         "⚠️ DTU 学术许可第 7(v)/10 条禁再分发跑出数字；投稿前须取 DTU 书面同意"],
  cite:"netMHCpan-4.1, Nucleic Acids Res 2020 · DOI 10.1093/nar/gkaa379 · services.healthtech.dtu.dk/services/NetMHCpan-4.1"
});

// ============================================================ 02 工具 4/7 MHCflurry
principleSlide({
  idx:4, name:"MHCflurry 2.0 (2020)", accent:C.teal,
  sub:"社区金标准「提呈代理」· 双分数（提呈 + 亲和力）· Apache-2.0",
  inP:"Python API：peptides（str list）+ alleles（HLA-A*02:01 格式）\n8–15mer；65 allele 全支持，0 NaN；无需格式转换",
  modelP:"神经网络 pan-allele 模型（Class1PresentationPredictor）\n联合建模 HLA 结合亲和力 + 抗原加工（proteasome/TAP）\n训练于大规模 MHC-I 结合亲和力 + MS 洗脱配体，无 T 细胞免疫原性标注",
  outP:"双分数：presentation_score [0,1]（越高越强提呈）+ affinity（nM，越低越强结合，取负用）\n实测 34247 行 0 NaN；AUC_presentation=AUC_affinity_neg=0.432",
  cmd:["from mhcflurry import Class1PresentationPredictor","predictor = Class1PresentationPredictor.load()","result = predictor.predict(","  peptides=['SIINFEKL','NLVPMVATV'],","  alleles=['HLA-A*02:01'],","  verbose=0)"],
  inFmt:["# Python API","peptides=['SIINFEKL','NLVPMVATV']","alleles=['HLA-A*02:01']","# 或 CLI：mhcflurry-predict input.csv ..."],
  outFmt:["peptide,sample_name,affinity,presentation_score","SIINFEKL,HLA-A*02:01,142.3,0.891","NLVPMVATV,HLA-A*02:01,8.4,0.983"],
  cite:"MHCflurry 2.0, Cell Systems 2020 · DOI 10.1016/j.cels.2020.06.010 · github.com/openvax/mhcflurry"
});
toolSlide({
  idx:4, name:"MHCflurry 2.0 (2020)", accent:C.teal,
  method:"神经网络提呈预测（双分数）", status:"RUN_DONE · AUC 0.432", statusCol:C.ok,
  tagline:"检验「提呈预测（无免疫原性微调）能否代理强弱定量」",
  input:["Python API：peptides(str list) + alleles(['HLA-A*02:01'])",
         "8–15mer；HLA 格式与 benchmark 标准格式一致，无需转换",
         "65 allele 全支持（benchmark universe 全覆盖，0 NaN）",
         "实测：53582 行（MT+WT），CPU ~30–60min；GPU ~5min"],
  params:["predictor = Class1PresentationPredictor.load()  加载模型（~70MB）",
          "predictor.predict(peptides, alleles, verbose=0)  批量预测",
          "mhcflurry-downloads fetch models_class1_presentation  首次下载",
          "按 allele 分组单独预测（65 组循环），verbose=0 静默"],
  output:["presentation_score [0,1]，越高越强提呈 → MT/WT_MHCflurry_presentation",
          "affinity(nM，越低越强结合)取负 → MT/WT_MHCflurry_affinity_neg",
          "⚠️ 不直接预测 T 细胞免疫原性，作 presentation proxy baseline",
          "实测 34247 行 0 NaN；两列 AUC 均 0.432；affinity_neg 聚合方向翻转（⚠️ 不稳健）"],
  intro:["检验「提呈预测（无免疫原性微调）能否当强弱定量代理」",
         "领域「公共参照系」——多数新工具论文都拿它对比，不纳入会被 reviewer 注意",
         "双分数可分析 affinity vs presentation 哪条信号更预测真值",
         "Apache-2.0，pip 一键装，社区使用最广；全量 65 allele 0 NaN 无缺失"],
  cite:"MHCflurry 2.0, Cell Systems 2020 · DOI 10.1016/j.cels.2020.06.010 · github.com/openvax/mhcflurry"
});

// ============================================================ 02 工具 5/7 CNNeo
principleSlide({
  idx:5, name:"CNNeo / CNNeoPP (2026)", accent:C.mint,
  sub:"LLM 增强 CNN · BioBERT 序列嵌入 · MIT · 最新发表（2026）",
  inP:"CSV：peptide（肽序列）+ hla（HLA-A*02:01 格式）\n8–11mer 训练分布内；12–14mer 轻度 OOD；<8 or >14 → NaN",
  modelP:"FCNN_TF 子模型：6-mer TF-IDF(max=1000) → FCNN(1000→64→2) → softmax[:, 1]\nCNN_BioBERT 子模型：4-mer → dmis-lab/biobert-base-cased-v1.1 → TextCNN → softmax[:, 1]\n首次运行自动从 training_data.xlsx 训练（TESLA+ELISpot，SMOTE 过采样）",
  outP:"score ∈ [0,1]，softmax class=1 概率，越高越免疫原；>0.5 判为免疫原\n实测 34247 行 0 NaN；分数范围 0.13–0.96；AUC(max,>0) 0.382",
  cmd:["# Step 1: 准备输入","python HPC/deploy/cnneo/prep_input.py","# Step 2: 训练（首次自动，FCNN_TF ~5-15min CPU）+ 推理","python HPC/deploy/cnneo/run_cnneo.py","# Step 3: 回贴 universe","python HPC/deploy/cnneo/parse_output.py"],
  inFmt:["peptide,hla","SIINFEKL,HLA-A*02:01","NLVPMVATV,HLA-B*07:02","FIAGLIAIV,HLA-A*02:01"],
  outFmt:["peptide,hla,score,label","SIINFEKL,HLA-A*02:01,0.847,1","NLVPMVATV,HLA-B*07:02,0.234,0","FIAGLIAIV,HLA-A*02:01,0.612,1"],
  cite:"CNNeoPP, Front Immunol 2026 · DOI 10.3389/fimmu.2026.1722117 · github.com/AaronChen007/neoantigen"
});
toolSlide({
  idx:5, name:"CNNeo / CNNeoPP (2026)", accent:C.mint,
  method:"BioBERT 序列嵌入 + TextCNN ensemble", status:"RUN_DONE · AUC 0.382", statusCol:C.ok,
  tagline:"率先引入蛋白质语言模型嵌入的新表位免疫原性工具（2026 最新）",
  input:["CSV 有表头：peptide（肽序列）+ hla（HLA-A*02:01 格式）",
         "8–11mer 训练分布内；12–14mer 可处理（轻度 OOD，分数供参考）",
         "<8 or >14mer 由 prep_input.py 过滤，benchmark 输出 NaN",
         "实测：53582 行（MT+WT），0 NaN；FCNN_TF 子模型"],
  params:["--model cnn_biobert  使用 BioBERT 子模型（默认 FCNN_TF）",
          "--smoke N  仅对 N 对肽做推理（快速验格式）",
          "--force-retrain  强制重训（首次自动从 training_data.xlsx 训练）",
          "FCNN_TF 无需预下载；CNN_BioBERT 需 HF 下载 BioBERT ~500MB"],
  output:["score ∈ [0,1]，softmax class=1，越高越免疫原，直接用",
          "label：score>0.5 → 1（预测阳性），0 → 阴性",
          "实测：34247 行 0 NaN；FCNN_TF 自训 ValAcc~75%；score 0.13–0.96",
          "产物：CNNeo_DS1DS2_scores.csv（MT_CNNeo / WT_CNNeo）"],
  intro:["填「LLM 增强序列表征」方法学空白，正交于 BigMHC（自训大矩阵 vs 外部 LLM）",
         "2026 最新发表，TESLA+ELISpot 验证（与本 benchmark 真值来源同系）",
         "MIT 许可，FCNN_TF 轻量（5–15min CPU 自训），展示方法前沿",
         "AUC 0.382 = 7 新工具最低；LLM 嵌入能否带来增益仍需更多数据验证"],
  cite:"CNNeoPP, Front Immunol 2026 · DOI 10.3389/fimmu.2026.1722117 · github.com/AaronChen007/neoantigen"
});

// ============================================================ 02 工具 6/7 BigMHC
principleSlide({
  idx:6, name:"BigMHC -m=im (2023)", accent:C.sea,
  sub:"大规模迁移学习 pMHC ensemble · Nature Machine Intelligence · 学术非商用",
  inP:"CSV：列 0=mhc（HLA allele），列 1=pep（肽序列），须有表头\nHLA 格式宽容（HLA-A*02:01/A*02:01/A0201 均可）；8–14mer 全支持",
  modelP:"两阶段迁移：① EL stage 在数十万 MHC-I 质谱洗脱配体上预训练，学 pMHC 提呈规律\n② IM stage 下游 fine-tune 到有标注免疫原性数据\n7 个不同 batch-size checkpoint ensemble 取平均分",
  outP:"BigMHC_IM ∈ [0,1]，越高越免疫原，直接用\n实测：34247 行 0 NaN；分数范围 0.0–0.95；AUC(max,>0) 0.396",
  cmd:["cd HPC/deploy/bigmhc_im/repo/src","python predict.py \\","  -i=/path/to/bigmhc_input.csv \\","  -m=im -a=0 -p=1 -c=1 \\","  -d=cpu -j=1 -v=1 \\","  -o=/path/to/bigmhc_output.prd"],
  inFmt:["mhc,pep","HLA-A*24:02,RLETIRNPK","HLA-A*03:01,RLETIRNPK","HLA-B*40:01,AAAMRILHN"],
  outFmt:["mhc,pep,tgt,len,BigMHC_IM","HLA-A*24:02,RLETIRNPK,,9,0.743","HLA-A*03:01,RLETIRNPK,,9,0.698","HLA-B*40:01,AAAMRILHN,,9,0.218"],
  cite:"BigMHC, Nature Machine Intelligence 2023 · DOI 10.1038/s42256-023-00694-6 · github.com/KarchinLab/bigmhc"
});
toolSlide({
  idx:6, name:"BigMHC -m=im (2023)", accent:C.sea,
  method:"两阶段迁移学习 + 7-ckpt ensemble", status:"RUN_DONE · AUC 0.396", statusCol:C.ok,
  tagline:"「大规模预训练→下游迁移」现代范式代表（Nature MI 2023）",
  input:["CSV：列 0=mhc（HLA allele），列 1=pep（肽序列），须有表头",
         "HLA 格式宽容：HLA-A*02:01 / A*02:01 / A0201 等均可自动匹配",
         "pan-allele（伪序列覆盖 >500 等位基因），8–14mer 全支持",
         "实测：53582 行（MT+WT），0 NaN"],
  params:["-m=im  免疫原性模式（-m=el 为提呈预训练模式）",
          "-d=cpu / 0  CPU 推理或 GPU 0 号卡（GPU 大幅加速）",
          "-j=1  Windows 本地必须用 1（spawn OOM）；HPC 建议 4-8",
          "⚠️ 必须从 repo/src/ 启动（内部用相对路径 ../../models/ + ../data/）"],
  output:["BigMHC_IM ∈ [0,1]，越高越免疫原，直接用",
          "实测：34247 行 0 NaN；分数范围 0.0–0.95",
          "EL 模式官方 .cmp 验证 PASS（diff 4.5e-7），权重完整管道正确",
          "产物：BigMHC_DS1DS2_scores.csv（MT_BigMHC / WT_BigMHC）"],
  intro:["代表「大规模预训练 + 下游迁移」现代范式；Nature MI 2023 高可信度期刊",
         "pan-allele 覆盖 >500 等位基因，两阶段迁移在同类比较中精度最优",
         "reviewer 会注意其缺席——不纳入导致 benchmark 范式覆盖不完整",
         "学术非商用许可，发数字 ✅；商用须另签协议（Johns Hopkins Karchin Lab）"],
  cite:"BigMHC, Nature Machine Intelligence 2023 · DOI 10.1038/s42256-023-00694-6 · github.com/KarchinLab/bigmhc"
});

// ============================================================ 02 工具 7/7 T-SCAPE
principleSlide({
  idx:7, name:"T-SCAPE (2025)", accent:C.warn,
  sub:"多域结构感知 SOTA · ByteNet 跨域辅助多任务 · ⚠️ CC-BY-NC-ND 4.0",
  inP:"CSV：Allele（HLA-A*02:01）+ peptide（小写氨基酸！）\nMT-only，不需野生型；需先 mhc_pseudo_matching.py 贴 pseudo 并过滤不支持 allele\n≤20mer，最优 9mer；Linux-only 部署",
  modelP:"ByteNet 骨架跨域辅助多任务 DL\n联合 pMHC 结合 / TCR-pMHC 交互 / source organism / T 细胞激活四路信号\n--inf_type pmhc_im_neo = 癌症新抗原免疫原性头（含 2 致命 bug 修复）",
  outP:"score ∈ [0,1]，越高越免疫原；>0.5 判为免疫原\n实测范围 0.0057–0.7716；⚠️ 全聚合 Spearman 显著负，方向待核，未取反",
  cmd:["# Step 1: 贴 pseudo + 过滤不支持 allele（308 行过滤）","python mhc_pseudo_matching.py I \\","  input.csv input_mod.csv","# Step 2: 推理（CPU，batch_size=32）","python inference_csv.py \\","  --csv_path input_mod.csv \\","  --inf_type pmhc_im_neo \\","  --output tscape_scores.csv"],
  inFmt:["Allele,peptide","HLA-A*02:01,sllmwitqv","HLA-B*07:02,gpghfvnml","# ⚠️ peptide 列须小写！"],
  outFmt:["Allele,peptide,score","HLA-A*02:01,sllmwitqv,0.6234","HLA-B*07:02,gpghfvnml,0.1891"],
  cite:"T-SCAPE, Science Advances 2025 · DOI 10.1126/sciadv.adz8759 · github.com/seoklab/T-SCAPE"
});
toolSlide({
  idx:7, name:"T-SCAPE (2025)", accent:C.warn,
  method:"ByteNet 跨域辅助多任务 DL（四路信号）", status:"RUN_DONE · ⚠️ CC-BY-NC-ND", statusCol:C.warn,
  tagline:"2025 多域结构 SOTA「复杂度上限」基线 · 也是许可最严格的工具",
  input:["CSV 两列：Allele（HLA-A*02:01）+ peptide（小写，否则读不到肽段！）",
         "MT-only：只需突变肽 + HLA，无需野生型 WT",
         "预处理：mhc_pseudo_matching.py I 贴 pseudo + 过滤不支持 allele",
         "实测：32178 个 unique (MT,HLA)；过滤 308 行 → 31871 进推理"],
  params:["--inf_type pmhc_im_neo  癌症新抗原任务（需修复 KeyError bug）",
          "--csv_path  输入 CSV（已贴 pseudo 序列）",
          "--output  输出路径",
          "⚠️ Linux-only；CPU 推理 batch_size=32；官方代码含 2 致命 bug 已修复"],
  output:["score ∈ [0,1]，越高越免疫原（>0.5 = 预测免疫原）",
          "实测范围 0.0057–0.7716；34247 行 33939 有分（308 allele 过滤 NaN）",
          "⚠️ 全聚合 Spearman 显著负（-0.23/-0.25/-0.27，p<0.05）——分数语义疑反转，方向待核",
          "⚠️ 复现零偏离红线：未擅自取反，PPT 如实报负标方向待核"],
  intro:["作「复杂度上限」基线：若最新多域 DL 增益有限，说明是数据瓶颈而非方法瓶颈",
         "benchmark 须纳入最新 SOTA 保时效性；Sci Adv 2025 + 前身 TITANiAN（bioRxiv 2025.05.11.653308）",
         "官方代码 2 致命 bug（pmhc_im_neo KeyError + dropout 推理非确定性）已修复才能跑通",
         "⚠️ CC-BY-NC-ND 4.0：仅限学术非商用，禁演绎/分发修改版；对外报告须署名标注"],
  cite:"T-SCAPE, Science Advances 2025 · DOI 10.1126/sciadv.adz8759 · github.com/seoklab/T-SCAPE"
});

// ============================================================ 03 数据集来源
s = pres.addSlide();
header(s, "03 数据与评测", "测试数据来源");
infoCard(s, 0.7, 1.7, 5.9, 5.3, "DS2 — ELISpot 免疫原性数据集", [
  "来源：多中心癌症患者 ELISpot 实验（T 细胞活化检测）",
  "真值：T 细胞反应强弱（ELISpot spot count，连续量化，非 0/1 二值）",
  "口径：DS2 corrected-full（HLA-FIX 后，P101/P102 HLA-dep 行置 NaN）",
  "规模：34247 行 universe（8–14mer 突变新抗原肽，65 allele）",
  "HLA：65 个 allele；仅使用 ELISpot >0 vs 0 做 AUC 二值判别",
  "benchmark 评估：全量（含 reinf 工具）统一口径，新旧工具一起比",
], C.teal);
infoCard(s, 6.85, 1.7, 5.78, 5.3, "口径说明 / 注意事项", [
  "AUC 口径：max 聚合（生物先验=单显性表位/best-binder）",
  "Spearman 口径：best-agg（三聚合取 p 最小）+ per-patient Fisher-Z LOPO",
  "reinf_pending=True（15/17 工具）：Phase B 重推理后数字可微变，方向不变",
  "TSCAPE 308 行因 allele 不支持置 NaN（过滤率 <1%）",
  "MHCflurry 双分数并存；netmhcpan_ba 取负后对齐正向",
  "全 17 工具（7 新+10 旧）统一口径，便于横向比较",
], C.sea);
pageno(s);

// ============================================================ 03 评测流程
s = pres.addSlide();
header(s, "03 数据与评测", "评测流程 — 6 步从原始肽序列到 Spearman 排行");
const _evalCards = [
  ["Step 1","输入准备","按各工具格式生成输入（prep_input.py）；部分按 HLA allele 分组，部分全量一次输入"],
  ["Step 2","工具推理","各工具独立运行（HPC Linux / WSL2 / 本地 Windows），产出原始分数 CSV"],
  ["Step 3","回贴 universe","parse_output.py 将分数 join 回 34247 行全量 universe（按 Peptide_ID + HLA_Allele）"],
  ["Step 4","聚合（pooling）","子肽×HLA → 肽级：max / mean / top3mean / geomean / softmax 等 8 种聚合（见 pooling 专章）"],
  ["Step 5","计算 AUC","sklearn.metrics.roc_auc_score（ELISpot>0 vs 0 二值；max 聚合为主榜口径）"],
  ["Step 6","计算 Spearman","全局 ρ + per-patient Fisher-Z 加权；count 混杂检测（|ρ(pooled,子肽数)|>0.5 剔除）"],
];
_evalCards.forEach(function(st,i){
  const col = i<3 ? 0.7 : 6.55;
  const row = i<3 ? i : i-3;
  const y = 1.75 + row*1.57;
  s.addShape(pres.shapes.RECTANGLE, {x:col, y:y, w:5.6, h:1.42, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh()});
  s.addShape(pres.shapes.RECTANGLE, {x:col, y:y, w:0.09, h:1.42, fill:{color:C.teal}});
  s.addText(st[0], {x:col+0.25, y:y+0.24, w:1.1, h:0.9, fontFace:FH, fontSize:17, bold:true, color:C.teal, valign:"middle", margin:0});
  s.addText(st[1], {x:col+1.4, y:y+0.15, w:4.05, h:0.38, fontFace:FH, fontSize:13, bold:true, color:C.ink, margin:0});
  s.addText(st[2], {x:col+1.4, y:y+0.57, w:4.05, h:0.78, fontFace:FB, fontSize:10.5, color:C.muted, valign:"top", lineSpacingMultiple:1.1, margin:0});
});
pageno(s);

// ============================================================ 03 看懂指标
s = pres.addSlide();
header(s, "03 数据与评测", "看懂两个核心指标 — AUC 判别力 vs Spearman 定量能力");
infoCard(s, 0.7, 1.7, 5.9, 5.3, "AUC — 判别力（能否区分阴/阳）", [
  "定义：ROC 曲线下面积；二值分类（ELISpot>0 = 阳性）",
  "范围：0.5 = 随机猜，1.0 = 完美判别",
  "口径：max 聚合（生物先验 = 每肽取最强结合子肽）",
  "参考线：0.75+ = 良好；0.6–0.75 = 中等；<0.6 ≈ 接近随机",
  "本 benchmark 所有工具 AUC < 0.72（含旧工具 pTuneos 0.719）",
  "⚠️ 能区分阴阳（AUC 高）≠ 能定量排强弱程度（Spearman 高）",
], C.teal);
infoCard(s, 6.85, 1.7, 5.78, 5.3, "Spearman ρ — 定量能力（强弱排序）", [
  "定义：预测分与真实 ELISpot 反应强度的秩相关系数",
  "范围：-1~+1；|ρ|<0.2 = 弱，0.2–0.5 = 中等，>0.5 = 强",
  "口径：best-agg（三聚合取 p 最小）+ per-patient Fisher-Z",
  "「CI 下界 > 0」= 统计显著正相关（全 17 工具中仅 3 个）",
  "per-patient Fisher-Z 最大值：PRIME 0.300 [0.056, 0.511]（旧工具）",
  "普遍弱相关 = 定量飞跃须新信号，正是 QuantImmune 立项依据",
], C.sea);
pageno(s);

// ============================================================ 04 基准结果 AUC
figSlide(
  "04 基准结果", "判别力 AUC — 17 工具横评（DS2 corrected-full，max 聚合）",
  C.teal, `${FIG}/fig_auc_17tools_corrected.png`,
  ["Repitope 0.620 = 7 新工具最高，与旧工具前列持平",
   "新工具整体 AUC 0.36–0.62，均未超旧工具天花板（pTuneos 0.719）",
   "netmhcpan_ba 0.419 / MHCflurry 0.432 / BigMHC 0.396 居中段",
   "T-SCAPE 0.362 最低且全聚合 Spearman 显著负——⚠️ 分数方向待核",
   "判别力（AUC）≠ 定量能力（Spearman）——见右页",
   "⚠️ netMHCpan-BA = DTU pending；T-SCAPE = CC-BY-NC-ND 须 caveat"]
);

// ============================================================ 04 基准结果 Spearman
figSlide(
  "04 基准结果", "定量能力 Spearman — 17 工具横评（DS2 corrected，best-agg）",
  C.sea, `${FIG}/fig_spearman_17tools_corrected.png`,
  ["仅 3 个工具 CI 下界>0（统计显著正）：PRIME / IMPROVE / MHCflurry_affinity_neg",
   "TSCAPE 全聚合显著负（-0.23~-0.27，p<0.05）：高度疑似分数语义反转，⚠️ 方向待核",
   "netmhcpan_ba mean 聚合全场最强 +0.381（p=0.0003）；max 聚合仅 0.090",
   "新工具 per-patient fisherz 均值 0.052 < 旧工具 0.137",
   "「普遍弱相关」结论不变：17 工具无一 per-patient fisherz >0.35",
   "pooling 维度对排序影响极大——见下章专章分析"]
);

// ============================================================ 05 pooling 专章 页1：为什么评判要变
s = pres.addSlide();
header(s, "05 pooling 评判专章", "为什么 Spearman 要看 pooling（朱同学核心贡献）");
s.addShape(pres.shapes.RECTANGLE, {x:0.7, y:1.7, w:5.85, h:5.25, fill:{color:C.dark}, shadow:sh()});
s.addText("朱同学的发现", {x:0.95, y:1.9, w:5.35, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.mint, margin:0});
s.addText("同一工具换 pooling\n（子肽×HLA→肽级聚合）\nSpearman 可翻倍", {x:0.95, y:2.36, w:5.35, h:1.3, fontFace:FH, fontSize:16, color:"FFFFFF", bold:true, lineSpacingMultiple:1.1, margin:0});
s.addText("netMHCpan  max 0.196  →  topk_w 0.395", {x:0.95, y:3.72, w:5.35, h:0.45, fontFace:FM, fontSize:13, color:C.mint, bold:true, margin:0});
s.addShape(pres.shapes.LINE, {x:0.95, y:4.28, w:5.3, h:0, line:{color:C.teal, width:1.5}});
s.addText("「报一个工具的 Spearman」是不完整的——你报的是「工具 + 你选的 pooling」联合结果", {x:0.95, y:4.38, w:5.35, h:0.85, fontFace:FB, fontSize:12, color:"CADCFC", valign:"top", lineSpacingMultiple:1.15, margin:0});
s.addText("本框架三原则", {x:0.95, y:5.3, w:5.35, h:0.35, fontFace:FH, fontSize:13, bold:true, color:C.mint, margin:0});
s.addText([
  {text:"① 不报单一聚合：",options:{color:C.mint,bold:true}},{text:"并列 max（单显性先验）与 count-safe 最优两套\n",options:{color:"CADCFC"}},
  {text:"② 剔 count 混杂：",options:{color:C.mint,bold:true}},{text:"|ρ(pooled,子肽数)|>0.5 格打叉剔除再选\n",options:{color:"CADCFC"}},
  {text:"③ 天花板夹逼：",options:{color:C.mint,bold:true}},{text:"把最优 ρ 放进 0.33–0.43 区间定位",options:{color:"CADCFC"}},
], {x:0.95, y:5.7, w:5.35, h:1.2, fontFace:FB, fontSize:11.5, valign:"top", lineSpacingMultiple:1.25, margin:0});
infoCard(s, 6.85, 1.7, 5.78, 5.25, "主榜 vs 专章口径声明", [
  "主榜口径：max 聚合（与全项目交付同口径）",
  "  → 一致性，方便与旧工具横比",
  "",
  "专章口径：count-safe 最优（逐工具最优聚合）",
  "  → 反映工具理论上限，揭示 max 的系统低估",
  "",
  "两套口径并存，不互相替代",
  "⚠️ 朱 topk_w 实现细节待朱本人对账",
], C.teal);
pageno(s);

// ============================================================ 05 pooling 专章 页2：热图
figSlide("05 pooling 专章", "17 工具 × 8 pooling 全局热图——pooling matters",
  C.teal, `${FIG}/pooling_heatmap_global_17tools.png`,
  ["横轴=工具，纵轴=8 种聚合方式；颜色深浅=全局 Spearman ρ 大小",
   "打叉格 = count 混杂（|ρ(pooled,子肽数)|>0.5）：正相关是肽长假象",
   "多数工具颜色随 pooling 变化显著——聚合方式改变工具排名",
   "deepHLApan 几乎全格打叉：无真信号，所有正相关纯为肽长假象",
   "netmhcpan_ba 从低色（max）到高色（count-safe）：Δ+0.340 最大",
   "TSCAPE 全格偏负方向（蓝色），⚠️ 方向待核，未取反"],
  "读图要点"
);

// ============================================================ 05 pooling 专章 页3：max vs count-safe
figSlide("05 pooling 专章", "max vs count-safe 最优 ρ — 每工具回升量 Δ",
  C.sea, `${FIG}/pooling_max_vs_countsafe_17tools.png`,
  ["蓝条=max ρ，橙条=count-safe 最优 ρ；差值=Δ(safe-max)",
   "max 系统性低估有信号工具 0.05–0.34",
   "结合亲和力工具增益最大：netmhcpan_ba Δ+0.340（呼应朱同学翻倍效应）",
   "IMPROVE / PRIME 增益小（Δ+0.05~0.06），本身已接近 count-safe 上限",
   "Repitope / CNNeo / BigMHC / TSCAPE：换 pooling 也救不了无信号工具",
   "⚠️ geomean* 标星=min-shift 实现仅探索；稳健口径 = mean / top3mean"],
  "读图要点"
);

// ============================================================ 05 pooling 专章 页4：spread
figSlide("05 pooling 专章", "pooling spread — 各工具对聚合选择的敏感度",
  C.mint, `${FIG}/pooling_spread_17tools.png`,
  ["spread = count-safe 最优 ρ − max ρ（= Δ 的可视化）",
   "结合亲和力工具敏感度最大：netmhcpan_ba 0.343；MHCflurry_affinity_neg 0.543",
   "MHCflurry_affinity_neg spread 最大但三聚合方向翻转——不稳健",
   "IMPROVE / PRIME spread 最小（≈0.05）：稳健，max 已接近其上限",
   "结论：pooling 选择对结合亲和力工具影响远大于免疫原性监督工具",
   "报告时不能只引「最好 p 值」，须说明聚合依赖性"],
  "读图要点"
);

// ============================================================ 05 pooling 专章 页5：天花板夹逼
figSlide("05 pooling 专章", "天花板夹逼 — 四方独立证据收敛 0.33–0.43",
  C.warn, `${FIG}/spearman_ceiling_squeeze_17tools.png`,
  ["四方独立证据：理论估计 / 朱同学融合 0.43 / I-fusion 0.328 / F-pilot 0.328 四路指向同一区间",
   "17 工具 count-safe 单工具上限：netmhcpan_ba geomean* 0.430（三重 caveat）",
   "结论：现有肽+HLA 信号定量上限 ≈ 0.33–0.43——「定量飞跃」须喂新信号",
   "新信号候选：供体 TCR 库 / 供体 HLA 单体型 / 表位前体蛋白丰度",
   "这是 QuantImmune 自研算法立项的统一依据（钉死现有工具上限）",
   "⚠️ netmhcpan_ba 0.430 = geomean*+DTU pending+全局非 per-patient，三重 caveat 不作 headline"],
  "读图要点"
);

// ============================================================ 06 结论（暗背景）
s = pres.addSlide();
s.background = {color:C.dark};
s.addShape(pres.shapes.RECTANGLE, {x:0, y:0, w:W, h:0.18, fill:{color:C.mint}});
s.addShape(pres.shapes.OVAL, {x:W-3.5, y:-1.5, w:4.5, h:4.5, fill:{color:C.teal, transparency:80}});
s.addShape(pres.shapes.OVAL, {x:W-2.0, y:3.8, w:3.2, h:3.2, fill:{color:C.sea, transparency:85}});
s.addText("06 结论", {x:0.9, y:1.15, w:11, h:0.4, fontFace:FB, fontSize:15, color:C.mint, bold:true, charSpacing:2, margin:0});
s.addText("7 新工具部署测试 · 评估总结", {x:0.9, y:1.6, w:11, h:0.65, fontFace:FH, fontSize:26, bold:true, color:"FFFFFF", lineSpacingMultiple:1.0, margin:0});
const _concl = [
  ["整体不破天花板","新工具组 per-patient fisherz 均值 0.052，旧工具 0.137；无任何新工具实现「弱→中等」跨级提升"],
  ["方法学多样性价值","7 个范式（统计/HLA-agnostic/结合/提呈/LLM/迁移/多域）全部测过，benchmark 覆盖面和说服力上一台阶"],
  ["pooling 是关键维度","结合亲和力工具换 count-safe 聚合 Δ+0.34；全集印证朱同学「换 pooling 翻倍」发现"],
  ["普遍弱相关钉死","17 工具无一 per-patient fisherz >0.35；「定量飞跃须新信号」= QuantImmune 立项统一依据"],
];
_concl.forEach(function(it,i){
  const col = i<2 ? 0.9 : 6.85;
  const row = i<2 ? i : i-2;
  const y = 2.55 + row*1.6;
  s.addShape(pres.shapes.RECTANGLE, {x:col, y:y, w:5.65, h:1.42, fill:{color:"FFFFFF", transparency:8}, line:{color:C.teal, width:1}});
  s.addShape(pres.shapes.RECTANGLE, {x:col, y:y, w:0.09, h:1.42, fill:{color:C.mint}});
  s.addText(it[0], {x:col+0.28, y:y+0.14, w:5.2, h:0.42, fontFace:FH, fontSize:13, bold:true, color:C.mint, margin:0});
  s.addText(it[1], {x:col+0.28, y:y+0.6, w:5.2, h:0.75, fontFace:FB, fontSize:11, color:"CADCFC", valign:"top", lineSpacingMultiple:1.1, margin:0});
});
_PG++; s.addText(String(_PG), {x:W-0.8, y:H-0.5, w:0.5, h:0.3, fontFace:FB, fontSize:11, color:C.muted, align:"right", margin:0});

// ============================================================ 06 许可 caveat
s = pres.addSlide();
header(s, "06 诚实边界与许可", "已知限制 · 口径 caveat · 许可红线");
infoCard(s, 0.7, 1.7, 5.9, 5.3, "⚠️ 许可红线（投稿/对外前必处理）", [
  "netMHCpan-BA：DTU 学术许可第 7(v)/10 条，禁再分发跑出的 benchmark 数字",
  "  → 投稿/对外报告含此数字前，须取 DTU 书面同意（pending 状态）",
  "T-SCAPE：CC BY-NC-ND 4.0，禁演绎/商业发布，仅限学术非商用",
  "  → 学术报告须署名标注；不得分发修改版结果",
  "其余 5 工具（BigMHC/CNNeo/MHCflurry/IEDB_Calis/Repitope）许可允许发数字",
  "BigMHC 学术非商用许可，商业用途须另签协议（Johns Hopkins Karchin Lab）",
], C.warn);
infoCard(s, 6.85, 1.7, 5.78, 5.3, "口径 caveat / 已知限制", [
  "geomean* 标星：min-shift 实现有跨肽尺度扭曲，仅探索；稳健=mean/top3mean",
  "TSCAPE 方向待核：全聚合显著负，疑分数语义反转；已保持原始不取反",
  "MHCflurry_affinity_neg：三聚合方向翻转（max+/mean-/top3+），须说明聚合依赖性",
  "reinf_pending：15/17 工具待 Phase B 重推理，数字可能微变（方向不变）",
  "netmhcpan_ba 0.430：geomean*+DTU pending+全局非 per-patient，三重 caveat 不作 headline",
  "朱 topk_w k/权重/softmax T/rankdecay d 实现细节待朱本人对账",
], C.teal);
pageno(s);

pres.writeFile({ fileName:"D:/YJ-Agent/project/meeting/QuantImmuBench/QuantImmuBench_新工具横评_v2_2026-06-27.pptx" }).then(f=>console.log("WROTE", f));
