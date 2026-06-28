// QuantImmuBench — 新增 7 工具横评报告 v3（Spearman 头条 · 人话文案 · 无内部术语 · 图不拉伸）
// 图 analysis/figures/*_v2.png（已重出，标签不压柱，比例正常）
// 运行: NODE_PATH=C:/Users/yj200/AppData/Roaming/npm/node_modules node ppt/gen_ppt_newtools_v3.js
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
    const gm=p.match(/(github\.com\/\S+|hlathena\.tools\S*|services\.healthtech\S*|openvax\.github\S*|tools\.iedb\.org\S*)/);
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
function principleSlide(o){
  const s = pres.addSlide();
  header(s, "工具 "+o.idx+" / 7 · 工作原理", o.name, o.accent);
  s.addText(o.sub, { x:0.7, y:1.46, w:11.8, h:0.5, fontFace:FB, fontSize:13, color:C.muted, margin:0 });
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:1.95, w:5.85, h:5.0, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  const stages = [["用什么输入", o.inP], ["模型怎么算", o.modelP], ["给出什么输出", o.outP]];
  let sy = 2.2;
  stages.forEach(st=>{
    s.addText(st[0], { x:0.95, y:sy, w:5.4, h:0.34, fontFace:FH, fontSize:14, bold:true, color:o.accent, margin:0 });
    s.addText(st[1], { x:0.95, y:sy+0.4, w:5.4, h:1.12, fontFace:FB, fontSize:11.5, color:C.ink, valign:"top", lineSpacingMultiple:1.18, margin:0 });
    sy += 1.6;
  });
  codeBox(s, 6.85, 1.95, 5.75, 1.62, "运行命令", o.cmd);
  codeBox(s, 6.85, 3.72, 5.75, 1.55, "输入数据样例", o.inFmt);
  codeBox(s, 6.85, 5.42, 5.75, 1.5, "输出数据样例", o.outFmt);
  citeFoot(s, o.cite);
  pageno(s);
}
function toolSlide(o){
  const s = pres.addSlide();
  header(s, "工具 "+o.idx+" / 7 · 四类信息", o.name, o.accent);
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
function figSlide(o){
  const s = pres.addSlide();
  header(s, o.kicker, o.title, o.accent||C.teal);
  const fx=0.7, fy=1.7, fw=6.7, fh=5.25;
  s.addShape(pres.shapes.RECTANGLE, { x:fx, y:fy, w:fw, h:fh, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  const RT = { fig_spearman_17tools_corrected_v2:1.18, fig_perpatient_fisherz_17tools_v2:1.18,
    fig_auc_17tools_corrected_v2:1.18, pooling_heatmap_global_17tools_v2:1.11,
    pooling_max_vs_countsafe_17tools_v2:1.13, pooling_spread_17tools_v2:1.13,
    spearman_ceiling_squeeze_17tools_v2:1.24,
    fig_roc_newtools_v3:1.20, fig_consistency_newtools_v3:1.14 };
  const _k = (o.img.match(/([a-z_0-9]+)\.png/) || [])[1];
  const R = o.ratio || RT[_k] || 1.18, aw = fw-0.24, ah = fh-0.24;
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
s.addText("新增 7 个免疫原性预测工具\n部署测试与基准评估报告", { x:0.9, y:2.05, w:11.5, h:1.8, fontFace:FH, fontSize:40, bold:true, color:"FFFFFF", lineSpacingMultiple:1.05, margin:0 });
s.addText("IEDB Calis · Repitope · netMHCpan-BA · MHCflurry · CNNeo · BigMHC · T-SCAPE", { x:0.9, y:4.3, w:11.8, h:0.5, fontFace:FB, fontSize:14, color:"CADCFC", margin:0 });
s.addShape(pres.shapes.LINE, { x:0.95, y:5.1, w:3.2, h:0, line:{color:C.mint, width:2} });
s.addText("在原有十个工具的基础上，补充七个代表不同方法路线的预测工具，统一在 ELISpot 实验数据上评估它们对 T 细胞反应强弱的定量预测能力。本版数字为 2026-06-28 IMPROVE 重推理跑通后、全部十七个工具全量重算的结果。", { x:0.95, y:5.4, w:11.0, h:1.1, fontFace:FB, fontSize:13, color:"E6F2F2", valign:"top", lineSpacingMultiple:1.2, margin:0 });
s.addText("2026-06-28", { x:W-2.4, y:6.7, w:1.8, h:0.3, fontFace:FB, fontSize:12, color:"8FB7BD", align:"right", margin:0 });

// ============================================================ 目录
s = pres.addSlide();
header(s, "目录", "本报告的内容结构");
const toc = [
  ["01","为什么补充这些工具","方法路线总览与文献出处"],
  ["02","工具逐一解析","每个工具的工作原理与四类信息"],
  ["03","部署工程与环境","运行环境、依赖与部署中遇到的问题"],
  ["04","数据与评测方法","测试数据来源、评测流程与指标含义"],
  ["05","基准结果","定量能力 患者内 Fisher-Z 为主，判别力 AUC 为辅"],
  ["06","结论与许可","总体结论、已知限制与许可提示"],
];
toc.forEach((it,i)=>{
  const col = i<4 ? 0.7 : 6.85, row = i<4 ? i : i-4, y = 1.95 + row*1.22;
  s.addShape(pres.shapes.RECTANGLE, { x:col, y, w:5.78, h:1.04, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:col, y, w:0.09, h:1.04, fill:{color:C.teal} });
  s.addText(it[0], { x:col+0.28, y:y+0.22, w:0.9, h:0.6, fontFace:FH, fontSize:26, bold:true, color:C.sea, valign:"middle", margin:0 });
  s.addText(it[1], { x:col+1.25, y:y+0.16, w:4.4, h:0.42, fontFace:FH, fontSize:15, bold:true, color:C.ink, margin:0 });
  s.addText(it[2], { x:col+1.25, y:y+0.58, w:4.4, h:0.38, fontFace:FB, fontSize:11, color:C.muted, margin:0 });
});
pageno(s);

// ============================================================ 总表（Spearman 头条）
s = pres.addSlide();
header(s, "总览", "七个工具的方法、定量能力与判别力");
const hd = (t)=>({ text:t, options:{ fill:{color:C.dark}, color:"FFFFFF", bold:true, fontSize:11, align:"center", valign:"middle" } });
const cc = (t,col)=>({ text:t, options:{ color:col||C.ink, fontSize:10.5, align:"center", valign:"middle" } });
const cl = (t)=>({ text:t, options:{ color:C.ink, fontSize:11, bold:true, align:"left", valign:"middle" } });
// 主列：患者内 Fisher-Z + 95% CI（方括号小字）
const cf = (val, ci, col)=>({ text:[
  { text:val, options:{ bold:true, fontSize:11, color:col||C.ink } },
  { text:" ["+ci+"]", options:{ fontSize:8, color:C.muted } },
], options:{ align:"center", valign:"middle" } });
// 对照列：全局 max ρ + p 值（圆括号小字）
const cg = (val, p)=>({ text:[
  { text:val, options:{ fontSize:10, color:C.muted } },
  { text:" ("+p+")", options:{ fontSize:8, color:C.gray } },
], options:{ align:"center", valign:"middle" } });
const trows = [
  [hd("工具"), hd("方法路线"), hd("患者内 Fisher-Z\n[95% CI]（主）"), hd("全局 max ρ\n(p)（对照）"), hd("判别力\nAUC"), hd("许可")],
  [cl("MHCflurry（亲和力）"), cc("结合亲和力代理"),    cf("+0.203","−0.028,+0.413",C.ink),   cg("+0.128","0.202"), cc("0.476",C.muted), cc("Apache-2.0",C.ok)],
  [cl("netMHCpan-BA"),        cc("结合亲和力金标准"),  cf("+0.155","−0.079,+0.373",C.ink),   cg("+0.090","0.370"), cc("0.468",C.muted), cc("学术许可 🔴",C.crit)],
  [cl("MHCflurry（提呈）"),   cc("提呈预测代理"),      cf("+0.124","−0.108,+0.342",C.ink),   cg("+0.098","0.329"), cc("0.513",C.muted), cc("Apache-2.0",C.ok)],
  [cl("Repitope"),            cc("不依赖 HLA 序列"),   cf("+0.119","−0.112,+0.338",C.ink),   cg("+0.084","0.406"), cc("0.620",C.muted), cc("MIT 开放",C.ok)],
  [cl("IEDB Calis"),          cc("经典氨基酸统计"),    cf("+0.112","−0.120,+0.334",C.ink),   cg("+0.096","0.339"), cc("0.528",C.muted), cc("学术免费",C.ok)],
  [cl("T-SCAPE"),             cc("多域结构深度学习"),  cf("+0.001","−0.226,+0.227",C.muted), cg("−0.139","0.167"), cc("0.442",C.muted), cc("CC BY-NC-ND",C.warn)],
  [cl("BigMHC"),              cc("大规模迁移学习"),    cf("−0.014","−0.241,+0.215",C.muted), cg("−0.041","0.684"), cc("0.499",C.muted), cc("学术非商用",C.warn)],
  [cl("CNNeo"),               cc("语言模型增强 CNN"),  cf("−0.204","−0.413,+0.026",C.muted), cg("+0.085","0.396"), cc("0.398",C.muted), cc("MIT 开放",C.ok)],
];
s.addTable(trows, { x:0.7, y:1.78, w:11.9, colW:[2.0,2.5,3.0,1.7,0.8,1.9],
  rowH:[0.58,0.42,0.42,0.42,0.42,0.42,0.42,0.42,0.42], border:{pt:1,color:C.line}, align:"center", valign:"middle", fontFace:FB, fill:{color:C.card} });
s.addText("自 2026-06-28 全项目口径统一：以按患者各自计算相关系数、再做 Fisher-Z 变换加权汇总的患者内相关为首要指标（计入患者间整体差异，方括号为 95% 置信区间，区间整体偏离零才算显著）；全局 max 聚合口径仅作对照（圆括号为 p 值）。AUC 只反映有无反应的二分判别，仅作参考。", { x:0.7, y:5.82, w:11.9, h:0.78, fontFace:FB, fontSize:10.5, color:C.muted, valign:"top", lineSpacingMultiple:1.12, margin:0 });
s.addText("* netMHCpan-BA 受 DTU 学术许可约束（🔴 对外公布前需书面同意），T-SCAPE 为 CC BY-NC-ND 非商业禁演绎许可。表中数字为 2026-06-28 IMPROVE 重推理跑通后、全部十七个工具按统一口径全量重算的结果；MHCflurry 给出亲和力与提呈两个分数，分两行列出。", { x:0.7, y:6.62, w:11.9, h:0.4, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", lineSpacingMultiple:1.05, margin:0 });
citeFoot(s, "netMHCpan-4.1 DOI 10.1093/nar/gkaa379 · T-SCAPE DOI 10.1126/sciadv.adz8759 · 完整论文与代码见后页文献出处");
pageno(s);

// ============================================================ 为什么补充这 7 个
s = pres.addSlide();
header(s, "为什么补充这些工具", "沿一条方法路线主轴，每个工具补上一类此前缺失的方法");
const spectrum = [
  ["IEDB Calis","经典氨基酸统计","只用氨基酸的理化性质打分，代表二〇一三年的经典做法，是衡量新方法是否真有进步的基准线。", C.gray],
  ["Repitope","不依赖 HLA 的序列模型","不需要输入患者的 HLA 分型，只看肽段序列本身，用来衡量抛开 HLA 信息还能预测多少。", C.sea],
  ["netMHCpan-BA","结合亲和力金标准","领域内使用最广的结合预测工具，用来检验单纯的结合强度能否代表免疫原性。", C.warn],
  ["MHCflurry","提呈预测代理","社区最常用的开源提呈预测工具，用来检验能被提呈是否就意味着能引发免疫反应。", C.teal],
  ["CNNeo","语言模型增强 CNN","把蛋白质语言模型的序列表示引入预测，代表最新的深度学习思路。", C.mint],
  ["BigMHC","大规模迁移学习","先在大规模提呈数据上预训练、再迁移到免疫原性，代表大模型迁移的现代范式。", C.sea],
  ["T-SCAPE","多域结构深度学习","同时整合结合、TCR 识别与激活信号，代表二〇二五年最新的复杂模型。", C.crit],
];
spectrum.forEach((it,i)=>{
  const y = 1.8 + i*0.73;
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y, w:11.9, h:0.63, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y, w:0.09, h:0.63, fill:{color:it[3]} });
  s.addText(String(i+1), { x:0.88, y, w:0.5, h:0.63, fontFace:FH, fontSize:18, bold:true, color:it[3], align:"center", valign:"middle", margin:0 });
  s.addText(it[0], { x:1.45, y, w:2.5, h:0.63, fontFace:FH, fontSize:13.5, bold:true, color:C.ink, valign:"middle", margin:0 });
  s.addText(it[2], { x:4.05, y, w:8.4, h:0.63, fontFace:FB, fontSize:11, color:C.muted, valign:"middle", lineSpacingMultiple:1.0, margin:0 });
});
pageno(s);

// ============================================================ 文献矩阵
s = pres.addSlide();
header(s, "文献出处", "七个工具的论文、代码与许可");
const lh = (t)=>({ text:t, options:{ fill:{color:C.dark}, color:"FFFFFF", bold:true, fontSize:10.5, align:"center", valign:"middle" } });
const lc = (t,al)=>({ text:t, options:{ color:C.ink, fontSize:9.5, align:al||"left", valign:"middle" } });
const ldoi = (doi)=>({ text:doi, options:{ color:"1C7293", fontSize:8.5, align:"center", valign:"middle", hyperlink:{ url:"https://doi.org/"+doi, tooltip:"DOI" } } });
const lrepo = (disp,url)=>({ text:disp, options:{ color:"1C7293", fontSize:8.5, align:"center", valign:"middle", hyperlink:{ url:url, tooltip:url } } });
const lrows = [
  [lh("工具"), lh("发表年 / 期刊"), lh("DOI"), lh("代码 / 主页"), lh("许可")],
  [lc("IEDB Calis"),   lc("2013 · PLOS Comput Biol","center"), ldoi("10.1371/journal.pcbi.1003266"), lrepo("tools.iedb.org","https://tools.iedb.org/immunogenicity"),                       lc("学术免费","center")],
  [lc("Repitope"),     lc("2019 · Front Immunol","center"),    ldoi("10.3389/fimmu.2019.00827"),     lrepo("github/masato-ogishi","https://github.com/masato-ogishi/Repitope"),            lc("MIT","center")],
  [lc("netMHCpan-BA"), lc("2020 · Nucleic Acids Res","center"),ldoi("10.1093/nar/gkaa379"),          lrepo("healthtech.dtu.dk","https://services.healthtech.dtu.dk/services/NetMHCpan-4.1"), lc("学术许可","center")],
  [lc("MHCflurry"),    lc("2020 · Cell Systems","center"),     ldoi("10.1016/j.cels.2020.06.010"),   lrepo("github/openvax","https://github.com/openvax/mhcflurry"),                        lc("Apache-2.0","center")],
  [lc("CNNeo"),        lc("2026 · Front Immunol","center"),    ldoi("10.3389/fimmu.2026.1722117"),   lrepo("github/AaronChen007","https://github.com/AaronChen007/neoantigen"),            lc("MIT","center")],
  [lc("BigMHC"),       lc("2023 · Nature Mach Intell","center"),ldoi("10.1038/s42256-023-00694-6"),  lrepo("github/KarchinLab","https://github.com/KarchinLab/bigmhc"),                     lc("学术非商用","center")],
  [lc("T-SCAPE"),      lc("2025 · Science Advances","center"), ldoi("10.1126/sciadv.adz8759"),       lrepo("github/seoklab","https://github.com/seoklab/T-SCAPE"),                          lc("CC BY-NC-ND","center")],
];
s.addTable(lrows, { x:0.7, y:1.85, w:11.9, colW:[1.85,2.75,2.95,2.55,1.8],
  rowH:[0.5,0.52,0.52,0.52,0.52,0.52,0.52,0.52], border:{pt:1,color:C.line}, align:"center", valign:"middle", fontFace:FB, fill:{color:C.card} });
s.addText("表中 DOI 与代码主页均可点击跳转。netMHCpan-BA 与 T-SCAPE 的许可禁止再分发或演绎，相关结果对外公布前需先取得授权方书面同意。", { x:0.7, y:6.2, w:11.9, h:0.7, fontFace:FB, fontSize:11, color:C.muted, valign:"top", lineSpacingMultiple:1.15, margin:0 });
pageno(s);

// ============================================================ 项目背景（块 A）
s = pres.addSlide();
header(s, "项目背景", "我们到底想预测什么");
proseCard(s, 0.7, 1.7, 11.9, 2.45, "从是非题到程度题", [
  "这个项目要解决的核心问题，是预测一条新抗原肽段在患者体内激发 T 细胞反应的强弱程度，而不只是判断它有没有免疫原性。过去大多数工具回答的是一道是非题，也就是这条肽能不能被免疫系统识别；而我们关心的是一道程度题，也就是它能引起多强的反应。",
  "这个差别很关键，因为癌症疫苗和个体化免疫治疗在挑选靶点时，真正需要的是把候选肽按反应强弱排出优先次序，而不是简单地分成有反应和没反应两类。",
], C.teal);
proseCard(s, 0.7, 4.3, 11.9, 2.55, "为什么在原有十个工具之外再补七个", [
  "为了衡量各类工具在这个更难的任务上的真实表现，项目此前已经部署并测试了十个主流的免疫原性预测工具。在那一轮横评的基础上，又补充了七个新工具。",
  "原有的十个工具在方法学上并不能覆盖这个领域的全部技术路线，缺少纯统计的经典基准，缺少不依赖 HLA 信息的路线，也缺少最新的大语言模型增强方法和多任务结构感知方法。要让横评结论站得住脚，必须把每一类有代表性的方法范式都纳入对照，才能回答不同方法范式对免疫强弱定量到底各自贡献了多少。",
], C.sea);
pageno(s);

// ============================================================ 逐工具 1/7 IEDB Calis
principleSlide({
  idx:1, name:"IEDB Immunogenicity（Calis 2013）", accent:C.teal,
  sub:"经典统计基线，没有机器学习，被主流新抗原流水线默认集成",
  inP:"只需要肽段序列，每次调用针对一个指定的 HLA 等位基因。肽段以纯文本一行一条给出，等位基因通过命令行参数单独指定。",
  modelP:"把肽段每个位置上氨基酸的免疫原性倾向分值做线性加权求和，同时用一个与等位基因相关的锚位屏蔽规则，把负责 HLA 结合的关键位置排除在外，避免结合信号干扰对免疫原性的估计。它没有机器学习，也没有需要训练的权重文件。",
  outP:"给出一个连续的打分，分数越高代表免疫原性越强，可以直接用来排序。整个过程在普通处理器上以秒级完成。",
  cmd:["python predict_immunogenicity.py \\","  --allele=HLA-A0201 \\","  HLA-A0201.txt"],
  inFmt:["# 纯文本，一行一肽","FIAGLIAIV","LITGRLQSL","NLVPMVATV"],
  outFmt:["peptide,length,score","FIAGLIAIV,9,0.45678","LITGRLQSL,9,0.23456","NLVPMVATV,9,0.12345"],
  cite:"IEDB Immunogenicity, PLOS Comput Biol 2013 · DOI 10.1371/journal.pcbi.1003266 · tools.iedb.org/immunogenicity"
});
toolSlide({
  idx:1, name:"IEDB Immunogenicity（Calis 2013）", accent:C.teal,
  tagline:"二零一三年的历史对照基准，任何新工具不超过它即可判定没有进步",
  status:"部署完成 · AUC 0.528", statusCol:C.ok, method:"线性统计，无机器学习",
  input:["输入是纯文本文件，每行一条肽段序列，没有表头也没有 HLA 列。",
         "等位基因通过命令行参数单独指定，格式需要去掉星号和冒号。",
         "八到十五个氨基酸的肽段都能打分。"],
  params:["主要参数是指定等位基因，以及是否使用自定义的屏蔽位置。",
          "它是纯 Python 脚本，不需要 GPU，也不需要基因组数据或野生型肽。",
          "几秒钟即可跑完所有等位基因。"],
  output:["输出是每条肽的连续打分，没有固定的上下界，通常落在负一点五到正一点五之间。",
          "分数越高免疫原性越强，可以直接用于强弱排名。"],
  intro:["它零依赖、完全开源，可以逐位追溯每个分数的来源，并被多个主流新抗原流水线默认集成，是这一领域引用频次最高的经典基准。",
         "选它是为了建立一条历史对照线，任何新工具如果不能明显超过这条线，就可以判定它没有带来真正的进步。"],
  cite:"IEDB Immunogenicity, PLOS Comput Biol 2013 · DOI 10.1371/journal.pcbi.1003266 · tools.iedb.org/immunogenicity"
});

// ============================================================ 逐工具 2/7 Repitope
principleSlide({
  idx:2, name:"Repitope（2019）", accent:C.sea,
  sub:"唯一不依赖 HLA 的序列路线，许可宽松，部署没有申请障碍",
  inP:"只需要肽段序列本身，不接受也不使用 HLA 等位基因信息。肽长限制在八到十一个氨基酸之间。",
  modelP:"利用公开的 T 细胞受体序列库，对每一条肽序列模拟整个人群的受体库对它的接触势能，从而衡量这条肽序列本身固有的免疫原性潜力，再用一组极端随机树模型做集成预测。",
  outP:"输出一个零到一之间的免疫原性分数，分数越高代表免疫原性越强。由于不使用 HLA 信息，同一条肽在不同等位基因下会得到相同的分数。",
  cmd:["set RSCRIPT=E:\\R-4.3.3\\bin\\Rscript.exe","Rscript run_repitope.R \\","  --input repitope_input.csv \\","  --frag-lib FragmentLibrary.fst \\","  --feature-df FeatureDF_Weighted.10000.fst \\","  --cores 6"],
  inFmt:["peptide","SIINFEKL","LITGRLQSL","FIAGLIAIV"],
  outFmt:["Peptide,ImmunogenicityScore,ImmunogenicityScore.cv","SIINFEKL,0.421,0.087","LITGRLQSL,0.338,0.092","FIAGLIAIV,0.195,0.104"],
  cite:"Repitope, Front Immunol 2019 · DOI 10.3389/fimmu.2019.00827 · github.com/masato-ogishi/Repitope"
});
toolSlide({
  idx:2, name:"Repitope（2019）", accent:C.sea,
  tagline:"不问 HLA，衡量肽序列本身的免疫原性潜力",
  status:"部署完成 · AUC 0.620", statusCol:C.ok, method:"不依赖 HLA 的序列模型",
  input:["输入是一份肽段序列列表，只需要序列本身。",
         "肽长严格限制在八到十一个氨基酸，超过这个范围的肽无法打分。",
         "运行前需要先从公开数据源下载两份预计算文件。"],
  params:["每次运行都会重新训练集成模型，整个过程在多核处理器上完成，不需要 GPU。",
          "可以指定并行核数来加速接触势能特征的计算。"],
  output:["输出是零到一之间的连续免疫原性分数，分数越高免疫原性越强，可以直接用于排名。",
          "需要注意同一条肽在不同等位基因下分数相同，这一点要在报告中标注。"],
  intro:["它是这一批工具里唯一不依赖 HLA 的路线，生物物理意义清晰，许可宽松，部署没有申请障碍。",
         "选它是为了衡量 HLA 限制信息究竟有多大价值，如果不依赖 HLA 也能表现得不差，说明序列内在特征已经足够。"],
  cite:"Repitope, Front Immunol 2019 · DOI 10.3389/fimmu.2019.00827 · github.com/masato-ogishi/Repitope"
});

// ============================================================ 逐工具 3/7 netMHCpan-BA
principleSlide({
  idx:3, name:"netMHCpan-4.1 结合亲和力模式（2020）", accent:C.warn,
  sub:"结合亲和力的业界标尺，覆盖一万八千多个等位基因，采用学术许可",
  inP:"输入是肽段序列加上对应的等位基因。它覆盖一万八千多个等位基因，八到十四个氨基酸的肽段都能预测。",
  modelP:"模型经过大规模结合数据训练，等位基因由伪序列表示来实现泛化覆盖。它的结合亲和力模式只输出预测的结合亲和力，并不直接预测 T 细胞免疫原性。",
  outP:"输出预测的结合亲和力，结合越强对应的数值越低。为了让分数方向与免疫强弱一致，本项目在使用时对其取负，使得分数越高代表结合越强。",
  cmd:["# HPC Linux 原生二进制","netMHCpan -BA \\","  -a HLA-A0201 \\","  -p peptides.txt \\","  -l 9"],
  inFmt:["# 肽序列文件（一行一肽）","FIAGLIAIV","LITGRLQSL","NLVPMVATV"],
  outFmt:["# Allele  Pos  Peptide  ...  Score_BA  Rank_BA  Aff_BA(nM)","HLA-A*02:01  0  FIAGLIAIV  ...  0.123  0.50  150.2","HLA-A*02:01  0  LITGRLQSL  ...  0.087  1.20  280.4"],
  cite:"netMHCpan-4.1, Nucleic Acids Res 2020 · DOI 10.1093/nar/gkaa379 · services.healthtech.dtu.dk/services/NetMHCpan-4.1"
});
toolSlide({
  idx:3, name:"netMHCpan-4.1 结合亲和力模式（2020）", accent:C.warn,
  tagline:"用纯结合亲和力检验结合强度能否代表免疫原性",
  status:"部署完成 · 许可受限", statusCol:C.warn, method:"结合亲和力泛等位基因网络",
  input:["输入是肽段序列与等位基因的组合。",
         "它依赖官方提供的二进制程序，本项目在高性能计算集群的操作系统环境下原生跑通，并用官方样例验证通过。"],
  params:["在结合亲和力模式下运行，可以指定一个或多个等位基因以及肽长，不需要 GPU。"],
  output:["输出是预测的结合亲和力，结合越强数值越低，本项目取负之后用于排名。"],
  intro:["它覆盖等位基因最广、使用最普遍，是新抗原流水线中最常用的上游工具。选它是为了把纯结合信号当作一条基线，量化它与真实 T 细胞反应之间的差距。",
         "它采用学术许可，未经书面同意不得对外发布在其软件上跑出的结果，相关数字需在取得书面同意后才能对外公布。"],
  cite:"netMHCpan-4.1, Nucleic Acids Res 2020 · DOI 10.1093/nar/gkaa379 · services.healthtech.dtu.dk/services/NetMHCpan-4.1"
});

// ============================================================ 逐工具 4/7 MHCflurry
principleSlide({
  idx:4, name:"MHCflurry 2.0（2020）", accent:C.teal,
  sub:"开源社区使用最广的提呈预测工具，同时给出结合亲和力与提呈两个分数",
  inP:"输入是肽段序列和等位基因，等位基因格式与本项目的标准格式一致，不需要转换，支持的肽长在八到十五之间。",
  modelP:"用神经网络联合建模 HLA 结合亲和力与抗原加工过程，同时给出两个分数，一个是结合亲和力，一个是综合的提呈分数。它本身并不直接预测 T 细胞免疫原性。",
  outP:"提呈分数在零到一之间且越高越强，可以直接使用；结合亲和力则是越低越强，本项目取负之后再用。",
  cmd:["from mhcflurry import Class1PresentationPredictor","predictor = Class1PresentationPredictor.load()","result = predictor.predict(","  peptides=['SIINFEKL','NLVPMVATV'],","  alleles=['HLA-A*02:01'],","  verbose=0)"],
  inFmt:["# Python API","peptides=['SIINFEKL','NLVPMVATV']","alleles=['HLA-A*02:01']","# 或 CLI：mhcflurry-predict input.csv ..."],
  outFmt:["peptide,sample_name,affinity,presentation_score","SIINFEKL,HLA-A*02:01,142.3,0.891","NLVPMVATV,HLA-A*02:01,8.4,0.983"],
  cite:"MHCflurry 2.0, Cell Systems 2020 · DOI 10.1016/j.cels.2020.06.010 · github.com/openvax/mhcflurry"
});
toolSlide({
  idx:4, name:"MHCflurry 2.0（2020）", accent:C.teal,
  tagline:"检验未经免疫原性微调的提呈预测能否当作强弱定量的代理",
  status:"部署完成 · AUC 0.513", statusCol:C.ok, method:"神经网络提呈预测，双分数",
  input:["输入是肽段序列与等位基因，等位基因格式与本项目标准一致，无需转换。",
         "支持的肽长在八到十五之间，本项目用到的全部等位基因都被支持。"],
  params:["通过一键安装的软件包运行，第一次使用时下载一次模型文件。",
          "处理器和 GPU 都可以运行。"],
  output:["输出包含两个方向的分数。提呈分数越高越强，可以直接使用；结合亲和力越低越强，取负之后再用。"],
  intro:["它社区认可度最高，双分数可以分别分析，安装零障碍，许可完全自由。",
         "它本质上预测的是提呈而非免疫原性，两者并不等价。绝大多数新工具论文都会拿它对比，因此纳入它能让横评更完整。"],
  cite:"MHCflurry 2.0, Cell Systems 2020 · DOI 10.1016/j.cels.2020.06.010 · github.com/openvax/mhcflurry"
});

// ============================================================ 逐工具 5/7 CNNeo
principleSlide({
  idx:5, name:"CNNeo（2026）", accent:C.mint,
  sub:"把蛋白质语言模型的序列表示引入预测，二零二六年最新发表，许可宽松",
  inP:"输入是肽段序列和等位基因，等位基因用标准格式，支持的肽长在八到十四之间。",
  modelP:"先把序列切成短片段，再用蛋白质语言模型生成序列嵌入，最后通过卷积网络给出免疫原性概率。它没有发布现成的预训练权重，每次运行会用代码仓库内置的训练数据自行训练后再推理。",
  outP:"输出一个零到一之间的免疫原性概率，分数越高代表免疫原性越强，超过零点五判为阳性。",
  cmd:["# Step 1: 准备输入","python HPC/deploy/cnneo/prep_input.py","# Step 2: 训练（首次自动，FCNN_TF ~5-15min CPU）+ 推理","python HPC/deploy/cnneo/run_cnneo.py","# Step 3: 回贴 universe","python HPC/deploy/cnneo/parse_output.py"],
  inFmt:["peptide,hla","SIINFEKL,HLA-A*02:01","NLVPMVATV,HLA-B*07:02","FIAGLIAIV,HLA-A*02:01"],
  outFmt:["peptide,hla,score,label","SIINFEKL,HLA-A*02:01,0.847,1","NLVPMVATV,HLA-B*07:02,0.234,0","FIAGLIAIV,HLA-A*02:01,0.612,1"],
  cite:"CNNeoPP, Front Immunol 2026 · DOI 10.3389/fimmu.2026.1722117 · github.com/AaronChen007/neoantigen"
});
toolSlide({
  idx:5, name:"CNNeo（2026）", accent:C.mint,
  tagline:"率先把蛋白质语言模型引入新表位免疫原性预测的最新工作",
  status:"部署完成 · AUC 0.398", statusCol:C.ok, method:"语言模型嵌入结合卷积网络",
  input:["输入是带表头的表格文件，包含肽段序列和等位基因两列，等位基因用标准格式。",
         "支持的肽长在八到十四之间。"],
  params:["可以选择不同的子模型。本项目使用的轻量子模型在处理器上数分钟即可训练完。",
          "语言模型版本则建议用 GPU 加速。"],
  output:["输出是零到一之间的连续概率，分数越高免疫原性越强，可以直接用于排名，超过零点五判为阳性。"],
  intro:["它率先在这一任务上引入蛋白质语言模型嵌入，与依靠自训练大矩阵的方法互为补充，是二零二六年最新发表的工作，并且用与本项目真值同源的数据做过验证。",
         "选它是为了填补语言模型增强这一方法学空白，展示方法前沿。"],
  cite:"CNNeoPP, Front Immunol 2026 · DOI 10.3389/fimmu.2026.1722117 · github.com/AaronChen007/neoantigen"
});

// ============================================================ 逐工具 6/7 BigMHC
principleSlide({
  idx:6, name:"BigMHC 免疫原性模式（2023）", accent:C.sea,
  sub:"先在数十万条洗脱配体数据上预训练，再迁移到免疫原性，训练规模最大",
  inP:"输入是等位基因和肽段序列，等位基因格式宽容，多种写法都能识别，不需要转换，八到十四个氨基酸都支持。",
  modelP:"第一阶段先在数十万条洗脱配体数据上做大规模预训练，学习 HLA 提呈的规律；第二阶段再迁移到有标注的免疫原性数据上做微调，并用七个不同的模型做集成。这套方法的训练规模在所有参选工具中最大。",
  outP:"输出一个零到一之间的免疫原性分数，分数越高代表免疫原性越强，可以直接用于排名。",
  cmd:["cd HPC/deploy/bigmhc_im/repo/src","python predict.py \\","  -i=/path/to/bigmhc_input.csv \\","  -m=im -a=0 -p=1 -c=1 \\","  -d=cpu -j=1 -v=1 \\","  -o=/path/to/bigmhc_output.prd"],
  inFmt:["mhc,pep","HLA-A*24:02,RLETIRNPK","HLA-A*03:01,RLETIRNPK","HLA-B*40:01,AAAMRILHN"],
  outFmt:["mhc,pep,tgt,len,BigMHC_IM","HLA-A*24:02,RLETIRNPK,,9,0.743","HLA-A*03:01,RLETIRNPK,,9,0.698","HLA-B*40:01,AAAMRILHN,,9,0.218"],
  cite:"BigMHC, Nature Machine Intelligence 2023 · DOI 10.1038/s42256-023-00694-6 · github.com/KarchinLab/bigmhc"
});
toolSlide({
  idx:6, name:"BigMHC 免疫原性模式（2023）", accent:C.sea,
  tagline:"大规模预训练再迁移到免疫原性的现代范式代表",
  status:"部署完成 · AUC 0.500", statusCol:C.ok, method:"两阶段迁移学习与多模型集成",
  input:["输入是带表头的表格文件，第一列是等位基因，第二列是肽段序列。",
         "等位基因格式宽容，多种写法都能识别，覆盖五百多个等位基因。"],
  params:["通过命令行调用，可以选择在处理器或 GPU 上执行。",
          "免疫原性模式会自动加载七个模型做集成。"],
  output:["输出是零到一之间的连续免疫原性分数，越高越强，可以直接用于排名。"],
  intro:["它覆盖五百多个等位基因，训练规模最大，可信度高，代表当下大规模预训练加下游迁移这一主流范式。",
         "这是同行评审时会被特别关注的代表性工作，缺席会被注意到。本项目还用官方对照样例验证了结果，确认权重完整、流程正确。"],
  cite:"BigMHC, Nature Machine Intelligence 2023 · DOI 10.1038/s42256-023-00694-6 · github.com/KarchinLab/bigmhc"
});

// ============================================================ 逐工具 7/7 T-SCAPE
principleSlide({
  idx:7, name:"T-SCAPE（2025）", accent:C.warn,
  sub:"在一套共享表示上联合学习结合、受体识别与免疫原性，采用最严格的学术非商业许可",
  inP:"输入只需要突变肽和等位基因，不需要野生型对照，支持的肽长在二十以内，九个氨基酸时最优。",
  modelP:"采用多任务多域的深度学习框架，在一套共享表示上联合学习 HLA 结合、T 细胞受体结合与免疫原性等多个任务。同一套权重可以通过切换任务类型，复用于多种预测。",
  outP:"输出一个零到一之间的免疫原性分数，分数越高代表免疫原性越强，超过零点五判为阳性。",
  cmd:["# Step 1: 贴 pseudo + 过滤不支持 allele（308 行过滤）","python mhc_pseudo_matching.py I \\","  input.csv input_mod.csv","# Step 2: 推理（CPU，batch_size=32）","python inference_csv.py \\","  --csv_path input_mod.csv \\","  --inf_type pmhc_im_neo \\","  --output tscape_scores.csv"],
  inFmt:["Allele,peptide","HLA-A*02:01,sllmwitqv","HLA-B*07:02,gpghfvnml","# ⚠️ peptide 列须小写！"],
  outFmt:["Allele,peptide,score","HLA-A*02:01,sllmwitqv,0.6234","HLA-B*07:02,gpghfvnml,0.1891"],
  cite:"T-SCAPE, Science Advances 2025 · DOI 10.1126/sciadv.adz8759 · github.com/seoklab/T-SCAPE"
});
toolSlide({
  idx:7, name:"T-SCAPE（2025）", accent:C.warn,
  tagline:"二零二五年最新发表的多任务结构方法，用来划定复杂度上限",
  status:"部署完成 · 许可受限", statusCol:C.warn, method:"多任务多域深度学习",
  input:["输入是表格文件，包含等位基因和肽段两列，只需要突变肽，不需要野生型。",
         "支持的肽长在二十以内，九个氨基酸时最优。"],
  params:["运行分两步，先给每行匹配等位基因的伪序列并过滤掉不支持的等位基因，再做推理。",
          "整个过程在处理器上完成，不需要 GPU，但只能在 Linux 环境运行。"],
  output:["输出是零到一之间的连续免疫原性分数。",
          "本项目如实报告它在测试数据上呈现的负相关结果，并标注方向有待进一步核实，没有擅自把分数取反。"],
  intro:["它输入门槛低，一套权重可以多任务复用，是参选工具里发表时间最新的。选它是为了用最新的复杂方法划定一条复杂度上限。",
         "它采用署名、非商业、禁止演绎的许可，仅限学术非商业用途。本项目使用官方权重并修复了官方代码中两个会导致崩溃的缺陷后才跑通，这一点也如实标注。"],
  cite:"T-SCAPE, Science Advances 2025 · DOI 10.1126/sciadv.adz8759 · github.com/seoklab/T-SCAPE"
});

// ============================================================ 部署工程：运行环境与两套战场
s = pres.addSlide();
header(s, "部署工程", "运行环境与两套部署战场");
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:1.7, w:5.85, h:5.25, fill:{color:C.dark}, shadow:sh() });
s.addText("两套部署环境", { x:0.98, y:1.92, w:5.3, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"轻量的工具直接在本地完成。本地使用的是 Windows 系统下的 Linux 子系统，因为这些工具大多是为 Linux 编写的老链路，在原生 Windows 上跑不动。", options:{ color:"FFFFFF", fontSize:13, breakLine:true, paraSpaceAfter:12 } },
  { text:"较重的、需要官方学术许可的，或对环境有特殊要求的工具，则放到学校的高性能计算集群上运行。", options:{ color:"CADCFC", fontSize:13, breakLine:true } },
], { x:0.98, y:2.45, w:5.35, h:4.3, fontFace:FB, valign:"top", lineSpacingMultiple:1.25, margin:0 });
proseCard(s, 6.85, 1.7, 5.78, 5.25, "哪些工具在哪里运行", [
  "在本地的 Linux 子系统中完成部署的有 IEDB Calis、MHCflurry、CNNeo、Repitope、BigMHC 和 T-SCAPE。",
  "部署在高性能计算集群上的是 netMHCpan 的结合亲和力工具，它依赖官方二进制程序并受学术许可约束。",
  "无论在哪一套环境，所有工具都用官方样例或对照数据验证过，确认流程正确、结果可信。",
], C.teal);
pageno(s);

// ============================================================ 部署工程：按工具踩坑
s = pres.addSlide();
header(s, "部署工程", "各工具部署中遇到的主要问题");
const deployRows = [
  ["IEDB Calis","纯 Python 统计脚本，没有机器学习框架依赖，本地几秒钟就能跑完所有等位基因，少数等位基因不在锚位屏蔽列表内会回退到通用规则。", C.teal],
  ["MHCflurry","通过一键安装的软件包部署，需要新建一个隔离环境避免依赖冲突，并在 Linux 子系统下设置统一文本编码以避开配置文件的编码问题。", C.teal],
  ["CNNeo","没有发布现成权重，每次运行用代码仓库内置的训练数据自行训练后再推理，轻量子模型在处理器上数分钟即可完成。", C.mint],
  ["Repitope","用 R 语言加随机树后端，依赖 Java 环境，核心后端软件包已从官方仓库下架，需要从存档取源码自行编译并安装约四十个依赖包。", C.sea],
  ["BigMHC","权重通过大文件存储管理、体积较大，在 Linux 子系统下多进程数据加载会耗尽内存，本地运行时必须把并行进程数调小并保证独占内存。", C.sea],
  ["T-SCAPE","只能在 Linux 环境运行，官方代码直接跑会崩溃，本项目定位并修复了两个导致崩溃的问题和一个导致结果不一致的问题后才跑通。", C.warn],
  ["netMHCpan-BA","依赖官方提供的二进制程序，部署在集群上原生跑通并用官方样例验证通过，其许可对结果的对外发布有限制。", C.warn],
];
deployRows.forEach((it,i)=>{
  const y = 1.78 + i*0.73;
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y, w:11.9, h:0.63, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y, w:0.09, h:0.63, fill:{color:it[2]} });
  s.addText(it[0], { x:0.95, y, w:2.15, h:0.63, fontFace:FH, fontSize:12.5, bold:true, color:C.ink, valign:"middle", margin:0 });
  s.addText(it[1], { x:3.2, y, w:9.25, h:0.63, fontFace:FB, fontSize:10.5, color:C.muted, valign:"middle", lineSpacingMultiple:1.05, margin:0 });
});
pageno(s);

// ============================================================ 数据与评测：数据来源
s = pres.addSlide();
header(s, "数据与评测", "测试数据的来源");
proseCard(s, 0.7, 1.7, 5.9, 5.25, "ELISpot 免疫原性数据集", [
  "测试数据来自多中心癌症患者的 ELISpot 实验，这是一种检测 T 细胞活化的方法。",
  "数据的真值是 T 细胞反应的强弱程度，是一个连续的数量，而不是简单的有反应或没有反应两类。",
  "整套数据包含约三万四千行突变新抗原肽，覆盖六十五个等位基因，肽长在八到十四个氨基酸之间。",
  "做有无反应的二分判别时，把有反应和没有反应的肽分成两类来比较。",
], C.teal);
proseCard(s, 6.85, 1.7, 5.78, 5.25, "评估口径与注意事项", [
  "全部十七个工具采用统一的评估口径，新工具和原有工具放在一起比较。",
  "判别力用每条肽取最强结合子肽的口径来计算。",
  "定量能力用每位患者各自的相关系数，再做加权汇总。",
  "极少数等位基因不被某些工具支持，对应的肽段记为缺失，占比不到百分之一。",
], C.sea);
citeFoot(s, "评估数据集 DS2 corrected-full · 全部十七个工具统一聚合口径");
pageno(s);

// ============================================================ 数据与评测：评测流程
s = pres.addSlide();
header(s, "数据与评测", "从原始肽序列到定量排行的评测流程");
const evalCards = [
  ["第一步","输入准备","按每个工具要求的格式生成输入文件，部分工具按等位基因分组，部分一次性全量输入。"],
  ["第二步","工具推理","各工具在各自的运行环境中独立运行，产出原始分数表。"],
  ["第三步","回贴整理","把分数对回到全量肽段表上，按肽段编号和等位基因对齐。"],
  ["第四步","汇总到肽级","一条长肽会切出许多子肽并与多个等位基因组合，需要把这一大批分数汇总成一个肽级分数用于排序。"],
  ["第五步","计算判别力","用受试者工作特征曲线下的面积，衡量工具区分有反应与没有反应的能力。"],
  ["第六步","计算定量能力","用秩相关衡量预测分数排序与真实反应强弱排序的吻合程度，并按患者加权。"],
];
evalCards.forEach((st,i)=>{
  const col = i<3 ? 0.7 : 6.55;
  const row = i<3 ? i : i-3;
  const y = 1.75 + row*1.57;
  s.addShape(pres.shapes.RECTANGLE, { x:col, y, w:5.6, h:1.42, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:col, y, w:0.09, h:1.42, fill:{color:C.teal} });
  s.addText(st[0], { x:col+0.25, y:y+0.2, w:1.3, h:1.0, fontFace:FH, fontSize:15, bold:true, color:C.teal, valign:"middle", margin:0 });
  s.addText(st[1], { x:col+1.55, y:y+0.16, w:3.9, h:0.38, fontFace:FH, fontSize:13, bold:true, color:C.ink, margin:0 });
  s.addText(st[2], { x:col+1.55, y:y+0.56, w:3.9, h:0.8, fontFace:FB, fontSize:10.5, color:C.muted, valign:"top", lineSpacingMultiple:1.1, margin:0 });
});
pageno(s);

// ============================================================ 数据与评测：看懂两个指标
s = pres.addSlide();
header(s, "数据与评测", "看懂两个核心指标");
proseCard(s, 0.7, 1.7, 5.9, 5.25, "AUC 衡量判别力", [
  "AUC 是受试者工作特征曲线下的面积，衡量工具能不能把有反应和没有反应的肽区分开。",
  "取值零点五相当于随机猜测，一点零是完美区分，通常零点七五以上算良好。",
  "它只回答一道是非题，也就是这条肽有没有反应。",
  "本项目所有工具的 AUC 都不高，能区分阴阳不等于能定量排出强弱程度。",
], C.teal);
proseCard(s, 6.85, 1.7, 5.78, 5.25, "Spearman 衡量定量能力", [
  "Spearman 相关系数衡量预测分数的排序与真实反应强弱排序之间的吻合程度，取值在负一到正一之间。",
  "绝对值小于零点二是弱相关，零点二到零点五是中等，大于零点五才算强。",
  "它回答的是一道程度题，也就是反应到底有多强，正是本项目最关心的能力。",
  "因此 Spearman 是首要指标，AUC 只作参考。",
], C.sea);
pageno(s);

// ============================================================ 基准结果（块 E）①：按患者定量能力（主图）
figSlide({
  kicker:"基准结果", title:"按患者衡量的定量能力 — 计入患者差异的正确口径", accent:C.teal,
  img:`${FIG}/fig_perpatient_fisherz_17tools_v2.png`,
  noteHead:"读图要点",
  notes:[
    "这张图按每位患者分别计算相关系数，再做 Fisher 变换加权汇总，是定量能力最核心的呈现，因为它把不同患者之间的整体差异计入了进来，才是衡量强弱排序的正确口径。",
    "全部十七个工具里，按患者口径达到统计显著（置信区间整体落在零以上）的只有两个，而且都是原有工具：PRIME 约零点二八、IMPROVE 约零点二五。新工具中表现最好的是 MHCflurry 的结合亲和力分数，约零点二零，但它的置信区间已经包含零，不再显著。",
    "把十七个工具放在一起，按患者衡量的定量相关没有任何一个达到零点三，中位数大约在零点一二，全部落在弱相关区间。",
    "T-SCAPE 在全局聚合下方向一致为负，约在负零点一四到负零点一九之间，但重新计算后已经全部不显著；按每位患者的口径汇总则接近零。它是否发生了分数语义的方向反转仍待核实，本项目没有擅自取反，而是如实报告。",
  ],
  cite:"T-SCAPE DOI 10.1126/sciadv.adz8759 · 评估数据集 DS2 corrected-full"
});

// ============================================================ 基准结果②：全局 Spearman 对照
figSlide({
  kicker:"基准结果", title:"全局 Spearman 对照 — 十七个工具横评", accent:C.sea,
  img:`${FIG}/fig_spearman_17tools_corrected_v2.png`,
  noteHead:"读图要点",
  notes:[
    "这张图把所有患者的肽混在一起算一个全局 Spearman 相关系数，采用每条肽取最强结合子肽的 max 聚合口径（与总表对照列一致），作为患者内 Fisher-Z 主口径的对照参考。",
    "在统一的 max 口径下，新增七个工具的全局相关都很小，绝对值大多在零点一三以内，整体没有突破原有工具的天花板。",
    "真正的判定仍以患者内 Fisher-Z 口径为准：全部十七个工具里只有 IMPROVE 和 PRIME 两个达到统计显著的正相关，而且都是原有工具；新增的七个工具没有一个达到这一标准。",
    "需要提醒的是，netMHCpan 的结合亲和力只有在改用对同一患者所有结合分数取平均的非稳健汇总方式时才会冲到约零点三五，换回统一的 max 口径就只剩约正零点零九，并不稳健；且该数字受学术许可约束，需取得书面同意后才能对外公布。",
    "整体说明无论新旧，现有工具对免疫强弱的定量预测都还相当弱。",
  ],
  cite:"netMHCpan-4.1 DOI 10.1093/nar/gkaa379 · 评估数据集 DS2 corrected-full"
});

// ============================================================ 基准结果③：判别力 AUC（参考）
figSlide({
  kicker:"基准结果", title:"判别力 AUC — 作为定量能力的补充参考", accent:C.warn,
  img:`${FIG}/fig_auc_17tools_corrected_v2.png`,
  noteHead:"读图要点",
  notes:[
    "作为二分判别能力的补充，AUC 的结论与 Spearman 一致。",
    "新工具中 Repitope 的 AUC 约为零点六二，在全部工具中排名靠前，说明肽序列层面确实存在一定信号。",
    "其余新工具的 AUC 大多落在零点四零到零点五三之间，多数贴近代表随机的零点五，整体偏弱的结论没有改变。",
    "判别力高不等于能定量排出强弱，因此 AUC 只作参考。",
  ],
  cite:"评估数据集 DS2 corrected-full · 每条肽取最强结合子肽口径"
});

// ============================================================ 基准结果：判别力 ROC 曲线（七个新工具）
figSlide({
  kicker:"基准结果", title:"判别力 ROC 曲线 — 七个新工具", accent:C.teal,
  img:`${FIG}/fig_roc_newtools_v3.png`,
  noteHead:"读图要点",
  notes:[
    "ROC 曲线把判别力画成一条线，越凸向左上判别力越强，越贴近对角线越接近随机。",
    "七个新工具的曲线整体都贴近对角线，没有哪个明显凸出，与柱状图上 AUC 普遍接近随机一致。",
  ],
  cite:"评估数据集 DS2 corrected-full · 肽级最大分聚合，Elispot 大于零为阳性"
});

// ============================================================ 基准结果：工具间一致性热图（七个新工具）
figSlide({
  kicker:"基准结果", title:"七个新工具之间一致吗 — 彼此基本不相关", accent:C.mint,
  img:`${FIG}/fig_consistency_newtools_v3.png`,
  noteHead:"读图要点",
  notes:[
    "这张热力图把七个新工具在同一批肽段上的打分两两做 Spearman 相关，颜色越绿越正相关，越红越负相关，对角线恒为一。",
    "对角线以外大多接近零，说明不同方法路线的工具对同一条肽给出的排序基本各说各话，相互之间没有共识。",
  ],
  cite:"评估数据集 DS2 corrected-full，101 条肽 · 肽级分数两两 Spearman 相关"
});

// ============================================================ 结论与许可（块 G，浅底深字）
s = pres.addSlide();
header(s, "结论与许可", "总体结论、已知限制与许可提示");
proseCard(s, 0.7, 1.7, 6.45, 5.25, "总体结论", [
  "以最严格的患者内 Fisher-Z 口径衡量，新增七个工具没有一个达到统计显著，置信区间全部跨过零；表现最好的 MHCflurry 亲和力分数约为正零点二零，置信区间同样包含零，仍然不显著。",
  "相比之下，原有工具里只有 PRIME 约正零点二八、IMPROVE 约正零点二五两个达到患者内显著。新增七个工具均未突破这条天花板，它们的价值不在刷新排行榜，而在把统计基线到最新多任务结构方法等七类有代表性的方法范式都纳入同一套横评。",
  "这样一来，现有工具难以做好强弱定量这一结论就被钉得更牢。要实现实质性的飞跃，必须引入现有工具尚未利用的新信号，或者扩充数据规模，这正是后续自研工具立项的统一依据。",
], C.sea);
proseCard(s, 7.4, 1.7, 5.23, 5.25, "许可提示", [
  "netMHCpan 的结合亲和力工具采用学术许可，未经书面同意不得对外发布在其软件上跑出的结果。它在本横评中表现出的较强信号，需要在取得书面同意之后才能对外公布。",
  "T-SCAPE 采用署名、非商业、禁止演绎的许可，仅限学术非商业用途，对外报告其数字时需加相应说明。",
  "在正式对外公布任何包含这两个工具的数字之前，都需要先完成相应的许可确认。",
], C.warn);
citeFoot(s, "netMHCpan-4.1 DOI 10.1093/nar/gkaa379 · T-SCAPE DOI 10.1126/sciadv.adz8759");
pageno(s);

pres.writeFile({ fileName:"D:/YJ-Agent/project/meeting/QuantImmuBench/QuantImmuBench_新工具横评_v3_2026-06-28.pptx" }).then(f=>console.log("WROTE", f, "pages", _PG));
