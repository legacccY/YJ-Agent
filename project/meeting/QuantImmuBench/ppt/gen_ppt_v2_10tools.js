// QuantImmuBench 全量交付 PPT v3 标准 (2026-06-28 修订) — 10 工具横评
// 2026-06-28 IMPROVE 跑通后全量更新：14 工具数字全部重算，本 10 工具 PPT 的 Spearman/AUC/per-patient/置信区间逐处更新
//   头名翻转 IMPROVE+PredIG 双显著（max p<0.05）；per-patient CI 排 0 = PRIME+IMPROVE；数字真源换为 metrics_ds2_16tools.csv / per_patient_spearman_16tools.csv
//   2026-06-28 口径统一：主指标改为「患者内 Fisher-Z」（与项目 README 统一，按患者内聚合排序 PRIME>IMPROVE>PredIG…）；全局 max ρ 降为对照列。总表/结论同步翻新
// 旧版 2026-06-25 重构到 PPT_SPEC v3：① Spearman 头条主指标（AUC 退为参考）② 来源/文献全超链接
// ③ 图按宽高比 aspect-fit 不拉伸（Spearman 主图用 _v2 标签不压柱）④ 完整中文句去 AI 味 ⑤ 结论页浅底深字
// 约束：说人话 / 不出现具体导师姓名(中性「课题组」) / 外部工具标引用出处(论文+DOI+repo,本地产物不标) / 客观中立
// 数字红线：benchmark/AUC/Spearman 逐字取自 analysis/*.csv（主指标=患者内 Fisher-Z per_patient_spearman_16tools.csv；对照=corrected-full 全局 max ρ metrics_ds2_16tools.csv；与图同源），不自算不臆改
//   MHLAPre 无数字=未做成(绝不臆造)；HLAthena=提呈 proxy 单列不并比
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
const FIGROOT = "D:/YJ-Agent/project/meeting/QuantImmuBench/figures";
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
// 浅底深字段落卡（v3 风格，用于结论等深背景改造页）
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
// 来源行：DOI→doi.org、repo→github/hlathena 超链接（每页底部）
function citeFoot(slide, txt){
  const runs=[{ text:"来源  ", options:{ color:C.teal, fontSize:9, bold:true } }];
  txt.split(" · ").forEach((p,i)=>{
    let opt={ color:C.muted, fontSize:9 };
    const dm=p.match(/(?:DOI\s+)?(10\.\d{4,}\/[^\s·]+)/);
    const gm=p.match(/(github\.com\/[A-Za-z0-9_.\-\/]+|hlathena\.tools[A-Za-z0-9_.\-\/]*|services\.healthtech[A-Za-z0-9_.\-\/]*|tools\.iedb\.org[A-Za-z0-9_.\-\/]*)/);
    if(dm) opt={ color:"1C7293", fontSize:9, hyperlink:{ url:"https://doi.org/"+dm[1], tooltip:"DOI" } };
    else if(gm) opt={ color:"1C7293", fontSize:9, hyperlink:{ url:"https://"+gm[1].replace(/^https?:\/\//,""), tooltip:"link" } };
    runs.push({ text:(i>0?" · ":"")+p, options:opt });
  });
  slide.addText(runs, { x:0.7, y:7.08, w:11.9, h:0.34, fontFace:FB, italic:true, valign:"top", margin:0 });
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

// 结果图页：按图真实宽高比 aspect-fit 放入容器，绝不拉伸（v3 做法）
function figSlide(o){
  const s = pres.addSlide();
  header(s, o.kicker, o.title, o.accent||C.teal);
  const fx=0.6, fy=o.fy||1.65, fw=o.fw||7.0, fh=o.fh||5.2;
  s.addShape(pres.shapes.RECTANGLE, { x:fx, y:fy, w:fw, h:fh, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  // sizing:contain = 在 fw×fh 包围盒内按原始宽高比缩放居中（letterbox），不变形
  s.addImage({ path:o.img, x:fx+0.12, y:fy+0.12, w:fw-0.24, h:fh-0.24, sizing:{type:"contain", w:fw-0.24, h:fh-0.24} });
  if(o.caption) s.addText(o.caption, { x:fx+0.05, y:fy+fh+0.04, w:fw, h:0.6, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", margin:0 });
  // 右侧读图卡
  const nx=fx+fw+0.2, nw=W-(fx+fw+0.2)-0.6;
  s.addShape(pres.shapes.RECTANGLE, { x:nx, y:fy, w:nw, h:fh, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:nx, y:fy, w:0.09, h:fh, fill:{color:o.accent||C.teal} });
  s.addText(o.noteHead||"读图要点", { x:nx+0.28, y:fy+0.16, w:nw-0.4, h:0.36, fontFace:FH, fontSize:15, bold:true, color:o.accent||C.teal, margin:0 });
  s.addText(o.notes.map((t)=>({ text:t, options:{ breakLine:true, color:C.ink, fontSize:11, paraSpaceAfter:7, lineSpacingMultiple:1.16 } })),
    { x:nx+0.3, y:fy+0.62, w:nw-0.55, h:fh-0.74, fontFace:FB, valign:"top", margin:0 });
  if(o.cite) citeFoot(s, o.cite);
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
s.addText("2026-06-28", { x:W-2.4, y:6.7, w:1.8, h:0.3, fontFace:FB, fontSize:12, color:"8FB7BD", align:"right", margin:0 });

// ============================================================ 目录
s = pres.addSlide();
header(s, "目录", "本报告的内容结构");
const toc = [
  ["01","项目背景与任务","要解决什么、本报告做了什么"],
  ["02","10 工具总览横评","一张表看清定量能力、判别力与装到什么程度"],
  ["03","工具逐一解析","每个工具的工作原理与四类信息"],
  ["04","部署工程与踩坑","运行环境、依赖与按工具遇到的问题"],
  ["05","数据与评测方法","测试数据来源、评测流程与指标含义"],
  ["06","基准结果","定量能力以患者内 Fisher-Z 为主、全局 Spearman 为对照，AUC 为辅"],
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
  { text:"现有工具大多只回答一条肽有没有免疫反应，这是一道是非题；本项目想更进一步，给出反应到底有多强，这是一道程度题。", options:{ color:"CADCFC", fontSize:12.5, breakLine:true } },
], { x:0.98, y:2.42, w:5.05, h:2.2, fontFace:FB, valign:"top", lineSpacingMultiple:1.18, margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:4.95, w:5.55, h:2.05, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addText("我这部分的任务", { x:0.95, y:5.08, w:5, h:0.34, fontFace:FH, fontSize:14, bold:true, color:C.teal, margin:0 });
s.addText([
  { text:"把市面上现有的预测工具一个一个装好、跑通。", options:{ color:C.ink, fontSize:12, breakLine:true } },
  { text:"再用同一套真实实验数据（ELISpot）横向比一遍，看它们到底准不准、能不能分出反应强弱。", options:{ color:C.ink, fontSize:12, breakLine:true, paraSpaceAfter:6 } },
  { text:"每个工具记录四类信息，整理成本报告。", options:{ color:C.dark, fontSize:12, bold:true } },
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

// ============================================================ S3 ⭐ 10 工具横评总表（Spearman 头条）
s = pres.addSlide();
header(s, "总览", "10 个工具一览：定量能力以患者内 Fisher-Z 为主指标、全局 Spearman 为对照，判别力 AUC 参考");
const hd = (t)=>({ text:t, options:{ fill:{color:C.dark}, color:"FFFFFF", bold:true, fontSize:11, align:"center", valign:"middle" } });
const cc = (t,col)=>({ text:t, options:{ color:col||C.ink, fontSize:11, align:"center", valign:"middle" } });
const cl = (t)=>({ text:t, options:{ color:C.ink, fontSize:11, bold:true, align:"left", valign:"middle" } });
const cz = (t,col)=>({ text:t, options:{ color:col||C.ink, fontSize:9, align:"center", valign:"middle" } }); // 窄列（含 CI / p）
// 主指标* = 患者内 Spearman + Fisher-Z 加权聚合 + 95%CI（取自 analysis/per_patient_spearman_16tools.csv，与 E1 图同源）；按 Fisher-Z 降序（PRIME>IMPROVE>PredIG…）
// 对照 = 全局 max ρ (p)：所有患者肽混合池化、|ρ| 最大聚合、阈值>0（取自 analysis/metrics_ds2_16tools.csv，与 E2 图同源），旧主口径现降为对照
// 判别力 AUC = ELISpot DS2、max 聚合、阈值>0（取自历史横评，逐字照搬，未重算）
const rows = [
  [hd("工具"), hd("方法"), hd("患者内 Fisher-Z\n[95% CI]（主*）"), hd("全局 max ρ (p)\n（对照）"), hd("判别力\nAUC"), hd("版本 / 状态")],
  [cl("PRIME"),         cc("轻量打分模型"),     cz("+0.279 ✅ [+0.05,+0.48]",C.ok),   cz("+0.158 (0.114)",C.ink),   cc("0.517",C.muted), cz("完整（对账 r=1.0）",C.ok)],
  [cl("IMPROVE"),       cc("随机森林"),         cz("+0.250 ✅ [+0.02,+0.46]",C.ok),   cz("+0.252 (0.011) ✅",C.ok), cc("0.616",C.muted), cz("特征降级",C.warn)],
  [cl("PredIG"),        cc("梯度提升树"),       cz("+0.229 [−0.00,+0.44]",C.ink),     cz("+0.201 (0.044) ✅",C.ok), cc("0.663",C.muted), cz("完整端到端",C.ok)],
  [cl("deepHLApan"),    cc("双向循环网络"),     cz("+0.224 [−0.01,+0.43]",C.ink),     cz("+0.002 (0.988)",C.muted), cc("0.445",C.muted), cz("完整",C.ok)],
  [cl("ImmuneApp"),     cc("CNN-LSTM"),         cz("+0.157 [−0.08,+0.37]",C.ink),     cz("+0.079 (0.433)",C.muted), cc("0.591",C.muted), cz("完整",C.ok)],
  [cl("pTuneos"),       cc("机器学习流程"),     cz("+0.121 [−0.11,+0.34]",C.ink),     cz("+0.119 (0.237)",C.ink),   cc("0.718",C.muted), cz("子模型（对账 r=1.0）",C.warn)],
  [cl("NeoTImmuML ★"),  cc("集成机器学习"),     cz("+0.033 [−0.19,+0.26]",C.muted),   cz("+0.022 (0.829)",C.muted), cc("0.655",C.muted), cz("自训版（非官方权重）",C.warn)],
  [cl("DeepImmuno"),    cc("卷积网络 CNN"),     cz("+0.015 [−0.21,+0.24]",C.muted),   cz("−0.089 (0.376)",C.muted), cc("0.469",C.muted), cz("完整端到端",C.ok)],
  [cl("HLAthena"),      cc("全连接网络（提呈 proxy）",C.warn), cz("−0.011 [−0.25,+0.23]",C.warn), cz("+0.091 (0.390)",C.warn), cc("0.415",C.muted), cz("提呈 proxy，不并比",C.warn)],
  [cl("MHLAPre"),       cc("元学习+Transformer"), cz("—",C.gray),                     cz("—",C.gray),               cc("—",C.gray),      cz("未做成（缺权重）",C.crit)],
];
s.addTable(rows, { x:0.55, y:1.7, w:12.25, colW:[1.55,2.05,2.95,2.05,0.95,2.7],
  rowH:[0.52,0.4,0.4,0.4,0.4,0.4,0.4,0.4,0.4,0.4,0.4],
  border:{pt:1,color:C.line}, align:"center", valign:"middle", fontFace:FB, fill:{color:C.card} });
s.addText([
  { text:"* 主指标（与项目 README 统一 · 2026-06-28 口径统一）：先在每位患者内部算工具打分与 ELISpot 反应强弱的 Spearman，再跨患者做 Fisher-Z 加权聚合并给 95% 置信区间——这样才不被患者间尺度差异污染，是方法学上正确的定量口径。✅ 表示置信区间不含零（稳定显著）：本主口径下仅 PRIME（+0.279）与 IMPROVE（+0.250）显著，其余均不显著。", options:{ color:C.muted, fontSize:9, italic:true, breakLine:true, paraSpaceAfter:3 } },
  { text:"对照列「全局 max ρ (p)」把所有患者的肽混在一起算一个相关（旧主口径，现降为对照）：该口径下改为 IMPROVE（+0.252, p=0.011）与 PredIG（+0.201, p=0.044）双双显著。两口径头名不同，说明聚合是否计入患者差异会改变结论。 ★ NeoTImmuML 官方未放权重，用公开数据自训了一版，数值不对标原论文。 HLAthena 预测「提呈」而非「免疫原性」，单列参照、不与前 8 个工具并比。 判别力 AUC（阈值>0）仅作参考。", options:{ color:C.ink, fontSize:9.5, breakLine:true } },
], { x:0.55, y:6.0, w:12.25, h:1.0, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
pageno(s);

// ============================================================ S3b ⭐ 各工具环境与依赖速查表
s = pres.addSlide();
header(s, "总览", "各工具的运行环境与依赖包（部署到什么环境、装了哪些包）");
const eh = (t)=>({ text:t, options:{ fill:{color:C.dark}, color:"FFFFFF", bold:true, fontSize:11, align:"center", valign:"middle" } });
const en = (t,col)=>({ text:t, options:{ color:col||C.ink, fontSize:9, align:"left", valign:"middle" } });
const enl= (t)=>({ text:t, options:{ color:C.ink, fontSize:10.5, bold:true, align:"left", valign:"middle" } });
const erows = [
  [eh("工具"), eh("运行环境"), eh("关键包 / 版本"), eh("外部工具 / 权重")],
  [enl("DeepImmuno"),   en("conda · Python 3.8"),       en("tensorflow 2.3.0 · numpy 1.18.5 · pandas 1.1.1 · protobuf 3.20.3"), en("无（纯肽段 + HLA）",C.ok)],
  [enl("PredIG"),       en("Docker / Singularity 镜像"), en("镜像内置 R + XGBoost 全套"),                                       en("NetCleave · NOAH · netCTLpan · MHCflurry（镜像自带）")],
  [enl("pTuneos"),      en("Docker 镜像 · Python 2.7"),  en("Python 2.7 · R 3.2.3 · scikit-learn（容器内）"),                   en("netMHCpan-4.0 · VEP+cache 14G · GATK · PyClone（镜像自带）",C.warn)],
  [enl("IMPROVE"),      en("conda · Python 3.11"),       en("numpy ≥2.0 · scikit-learn 1.9 · pandas · seaborn"),                en("netMHCpan-4.1 · netMHCstabpan · PRIME · MixMHCpred + models.zip 1.9G(git-lfs)",C.warn)],
  [enl("NeoTImmuML ★"), en("conda · Python 3.10 + R"),   en("lightgbm · xgboost · scikit-learn · pandas · numpy + R Peptides 2.4.6"), en("无外部许可工具；权重自训（官方未发布）",C.warn)],
  [enl("PRIME"),        en("conda · Python 3.11"),       en("numpy · pandas · scipy · logomaker · matplotlib（+MAFFT 可选）"),   en("PRIME.x（g++ 编译）· MixMHCpred 3.0（Python）")],
  [enl("ImmuneApp"),    en("conda · Python 3.7"),        en("tensorflow 1.15.0"),                                               en("权重随 repo（880M）")],
  [enl("deepHLApan"),   en("Docker 镜像 · Python 2.7"),  en("keras 2.0.8 · tensorflow 1.12（容器内）"),                         en("权重随镜像")],
  [enl("HLAthena"),     en("Docker / Singularity（sif 792M）"), en("镜像内置"),                                                 en("65-allele 模型 6.6G（从 GCS 下载）",C.warn)],
  [enl("MHLAPre"),      en("未配通",C.crit),             en("文献：CUDA 10.2 · PyTorch（元学习 + Transformer）"),               en("❌ 无官方权重（部署阻塞）",C.crit)],
];
s.addTable(erows, { x:0.45, y:1.62, w:12.45, colW:[1.75,2.5,4.05,4.15],
  rowH:[0.42,0.46,0.46,0.46,0.46,0.46,0.46,0.46,0.46,0.46,0.46],
  border:{pt:1,color:C.line}, valign:"middle", fontFace:FB, fill:{color:C.card} });
s.addText([
  { text:"环境分两类：", options:{ bold:true, color:C.teal, fontSize:9.5 } },
  { text:"轻量工具用 conda 建独立 Python 环境装包；老链或多依赖工具用官方 Docker 镜像（在 HPC 上转成 Singularity）打包整套环境。", options:{ color:C.muted, fontSize:9.5, breakLine:true } },
  { text:"★ NeoTImmuML 官方未发布权重，用公开数据自训替代；MHLAPre 缺权重未做成。学术工具（如 netMHCpan）需 DTU 许可，禁止再分发。", options:{ color:C.ink, fontSize:9.5 } },
], { x:0.45, y:6.7, w:12.45, h:0.6, fontFace:FB, valign:"top", lineSpacingMultiple:1.04, margin:0 });
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
  output:[ "三列  peptide / HLA / immunogenicity", "immunogenicity = 0~1 连续分，越高越强", "实测已知强表位高分（CMV NLVPMVATV=0.957），符合预期" ],
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
  intro:[ "连续分 + 可解释特征 + 容器化（依赖全打包，省去装环境）", "环境：官方 Docker（14.4G），在 HPC 转 Singularity（4.6G）", "限制：镜像体积大" ],
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
  params:[ "完整：python pTuneos.py  加  配置文件", "子模型：自写脚本调用识别打分函数", "可并行加速（多进程 + 批量结合预测）" ],
  output:[ "完整流程出患者级排名分（乘了表达/突变频率，需测序）", "子模型出纯肽免疫原性识别分，这部分进基准、可与其它工具比", "示例数据跑出 40 个候选新抗原" ],
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
  intro:[ "22 个特征专为新表位排名设计，整合了 TCR 识别信号", "缺口：ELISpot 没有 RNA 表达量，表达相关特征降级；稳定性特征依赖的外部工具受系统库版本所限", "预测步本地与 HPC 都跑通；这是数据缺一块、不是装不上" ],
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
toolSlide({ idx:5, page:8, name:"NeoTImmuML ★ 自训版", accent:"028090", method:"集成机器学习", status:"⚠️ 自训版", statusCol:C.warn,
  tagline:"三种模型加权集成（LightGBM+XGBoost+随机森林）预测肿瘤新抗原免疫原性，用 78 个肽段物化特征",
  input:[ "CSV：肽段 + 标签 + 78 个物化特征", "肽段 8–13 个氨基酸，不需要 HLA", "78 个特征要先用 R 的 Peptides 包算好" ],
  params:[ "不是命令行，是 Jupyter notebook（21 个单元格）", "改路径指向数据；内含 8 种算法对比 + 加权集成 + 交叉验证" ],
  output:[ "分类指标 + 雷达图 + 连续概率（能分强弱）", "★ 官方没放预训练权重，基准用我们自训的版本", "数值不对标原论文精度" ],
  intro:[ "纯肽段特征，不要 HLA、不要任何收费工具，装起来最省心", "限制：是研究用 notebook，没带权重，用公开肿瘤抗原库重训了一版", "不含 78 特征的计算代码，要自己用 R 算" ],
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
  cite:"PRIME, Cell Reports Medicine 2021 / Cell Systems 2023 · DOI 10.1016/j.celrep.2021.100194 · DOI 10.1016/j.cels.2022.12.002 · github.com/GfellerLab/PRIME",
});
toolSlide({ idx:6, page:9, name:"PRIME", accent:"1C7293", method:"轻量打分模型", status:"✅ 完整 (对账 r=1.0)", statusCol:C.ok,
  tagline:"轻量模型预测新表位免疫原性：把 HLA 提呈分 + TCR 接触位点氨基酸频率 + 肽长 揉成一个排名分",
  input:[ "纯文本（每行一条肽段）或 FASTA", "HLA 用命令行 -a 指定，多个逗号分隔", "肽段 8–14；HLA 写法很宽松（A0101 / A01:01 / HLA-A*01:01 都行）" ],
  params:[ "-i 输入  -o 输出  -a HLA 列表  -mix 指定 MixMHCpred 路径", "模型版本 v2.1（需配 MixMHCpred v3.0+）" ],
  output:[ "文本 5 列：肽段 / 最优%Rank / PRIME Score / 结合%Rank / 最优 allele", "PRIME Score 连续，量化免疫原性强弱", "实测 147 行输出与官方答案逐字一致（diff=0）" ],
  intro:[ "直接出免疫原性连续分；依赖链最短（只要 MixMHCpred，无收费工具），五个里装起来最容易", "方法非深度学习，轻快、CPU 即可", "限制：肽长 8–14；需对齐 MixMHCpred 版本" ],
  cite:"PRIME, Cell Reports Medicine 2021 / Cell Systems 2023 · DOI 10.1016/j.celrep.2021.100194 · DOI 10.1016/j.cels.2022.12.002 · github.com/GfellerLab/PRIME",
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
  intro:[ "HLA-I 提呈方向性能领先，预训练权重随仓库带、MIT 许可无障碍、不依赖收费工具", "方法可解释（注意力能指出关键结合残基）", "限制：仅 HLA-I；TF1.15 老环境易踩坑；训练数据含公开库，注意与测试集重叠" ],
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
  intro:[ "一次同时给「结合 + 免疫原性」两个分，纯肽段+HLA，不依赖收费工具", "官方推荐用 Docker 镜像绕开版本不兼容问题", "限制：仅 MHC-I；训练数据含公开库，与测试集可能重叠，需排重" ],
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
toolSlide({ idx:9, page:12, name:"HLAthena（提呈 proxy）", accent:"C9743D", method:"全连接网络", status:"⚠️ 提呈 proxy", statusCol:C.warn,
  tagline:"质谱数据训练的全连接网络，预测肽段被 HLA-I「提呈」的概率 —— 注意：是提呈，不是免疫原性",
  input:[ "tab 分隔（带表头）或 FASTA，必填 peptide 列", "肽段 8 / 9 / 10 / 11", "可选列（剪切上下文 / 表达量）决定跑哪个子模型" ],
  params:[ "选模型 MSi / MSiC / MSiCE（取决于提供的可选列）", "实测用 Docker 镜像跑，参数同官方 web" ],
  output:[ "连续提呈分（MSi 等列），越高越可能被提呈", "不是免疫强弱分，这是它与前 8 个工具的本质区别", "实测 IDLLKEIY  MSi=0.844" ],
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
toolSlide({ idx:10, page:13, name:"MHLAPre（未完成）", accent:"B23A48", method:"元学习+Transformer", status:"❌ 未做成", statusCol:C.crit,
  tagline:"元学习 + Transformer + TextCNN 预测突变 HLA-I 表位免疫原性 —— 信息已摸清，但无法复现运行",
  input:[ "CSV：肽段 + HLA + 标签", "肽段 8–15（以 9 为主）", "HLA 写法  B*07:02（无 HLA- 前缀）" ],
  params:[ "顺序跑 3 个脚本（预处理 → Transformer → TextCNN）", "无命令行参数说明" ],
  output:[ "原代码不存预测文件，只算指标（同 notebook 性质）", "理论上出 0~1 连续概率，要自己加导出代码", "实测无输出（卡在缺数据，跑不起来）" ],
  intro:[ "方法新（元学习），论文报告指标高；纯开源依赖、无收费工具", "阻塞：官方未放预训练权重，预处理中间数据也缺失", "连自训也走不通：把原始数据拼成模型输入的那段代码没随仓库发出（被注释掉）", "全网（GitHub/Gitee/ModelScope/Zenodo + 逐个 commit）搜权重均空，唯一出路是邮件原作者索取" ],
  cite:"MHLAPre, Briefings in Bioinformatics 2024 · DOI 10.1093/bib/bbae625 · github.com/ChanganMakeYi/MHLAPre（无 LICENSE）",
});

// ============================================================ 部署工程 ① 两套战场总览
// 按工具列问题：每卡 = 工具名 + 元信息 + 带[本机]/[HPC]来源标签的问题条目
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
function srcLegend(s){
  s.addText([
    { text:"来源标签：", options:{ color:C.muted, fontSize:11, bold:true } },
    { text:" 本机 ", options:{ color:C.sea, fontSize:11, bold:true } },
    { text:"= 本地 WSL2   ", options:{ color:C.muted, fontSize:11 } },
    { text:" HPC ", options:{ color:C.warn, fontSize:11, bold:true } },
    { text:"= 学校集群   ", options:{ color:C.muted, fontSize:11 } },
    { text:" — ", options:{ color:C.gray, fontSize:11, bold:true } },
    { text:"= 未做成无输出", options:{ color:C.muted, fontSize:11 } },
  ], { x:0.7, y:1.5, w:11.9, h:0.34, fontFace:FB, valign:"top", margin:0 });
}

s = pres.addSlide();
header(s, "04 · 部署工程", "两套部署战场：为什么不是「点一下就能跑」");
s.addText("本地的 WSL2 负责逐个调通工具并摸清四类信息，学校 HPC 集群负责正式大规模跑。两边出网都受限，工具多是为 Linux 写的老链路，需要逐个适配。",
  { x:0.7, y:1.46, w:11.9, h:0.5, fontFace:FB, fontSize:13, color:C.muted, margin:0 });
infoCard(s, 0.7,  2.1, 3.97, 4.35, "本机 · WSL2 Ubuntu 24.04", [
  "角色：调试主场，逐个工具跑通、摸清四类信息",
  "环境：直通显卡 + conda + Docker",
  "为什么不用 Windows：仓库含带 * 的非法文件名，且工具多为 Linux 老链",
], C.sea);
infoCard(s, 4.93, 2.1, 3.97, 4.35, "HPC · 学校集群", [
  "角色：正式大规模跑，团队最终交付目标",
  "环境：Singularity 容器（无 Docker）+ 多核 CPU",
  "推理多在 CPU 上完成（梯度提升树 / 随机森林 / CNN 推理），基本不占显卡",
], C.teal);
infoCard(s, 9.16, 2.1, 3.47, 4.35, "两边共同约束", [
  "出网：GitHub / PyPI / DTU 通；Docker Hub 两边都不通",
  "对策：本机打包镜像后上传，再转 Singularity",
  "学术工具（如 netMHCpan）禁止再分发，含其跑出的数字",
], C.warn);
s.addText("下面两页按工具逐个列出遇到的问题，并标注来源环境（本机 / HPC）。",
  { x:0.7, y:6.62, w:11.9, h:0.4, fontFace:FB, fontSize:10.5, italic:true, color:C.muted, margin:0 });
pageno(s);

// ============================================================ 部署工程 ② 第一批 5 工具（按工具）
s = pres.addSlide();
header(s, "04 · 部署工程 · 按工具", "各工具遇到的问题（第一批 5 工具）", C.sea);
srcLegend(s);
toolIssueGrid(s, [
  { name:"DeepImmuno", meta:"CNN · 本机+HPC 均通", accent:C.teal, issues:[
    { env:"本机", text:"仓库含 * 文件名，Windows 存不了，搬到 WSL2" },
    { env:"本机", text:"protobuf 须降 3.20；TF2.3 / Py3.8 严格对版本" },
    { env:"HPC",  text:"顺利跑通，结果与本机一字不差" },
  ]},
  { name:"PredIG", meta:"XGBoost · 官方镜像", accent:C.teal, issues:[
    { env:"本机", text:"镜像 14.4G + Docker Hub 墙，用镜像源 + 代理 + 删旧源" },
    { env:"本机", text:"单次输入硬限 <5000 行，切块串跑再按序拼" },
    { env:"HPC",  text:"镜像转 Singularity；只读容器写 tmp 需 writable-tmpfs" },
  ]},
  { name:"pTuneos", meta:"Py2.7 流水线", accent:C.teal, issues:[
    { env:"本机", text:"自带样例连修 8 处 bug 才端到端跑通" },
    { env:"本机", text:"VEP 注释库 14G 龟速，多连接下载提速约 12 倍" },
    { env:"本机", text:"完整版喂不了 ELISpot，用 Pre&RecNeo 子模型进基准" },
    { env:"HPC",  text:"镜像程序在 /root + 无 fakeroot，改本机容器验证" },
  ]},
  { name:"IMPROVE", meta:"随机森林", accent:C.teal, issues:[
    { env:"本机", text:"模型用新版 numpy 存，换 Py3.11 才读得了" },
    { env:"本机", text:"老二进制 netMHCpan-2.8 崩，内核 vsyscall 救活" },
    { env:"本机", text:"表达量特征需 RNA-seq，ELISpot 没有，该特征降级" },
    { env:"HPC",  text:"glibc 2.28 < stabpan 要 2.29，稳定性特征跑不了" },
  ]},
  { name:"NeoTImmuML ★", meta:"集成 ML · 自训替代", accent:C.teal, issues:[
    { env:"本机", text:"源码 URL 未公开，浏览器自动化从数据库站抓出" },
    { env:"本机", text:"无官方权重，公开数据自训（已确认全网无权重）" },
    { env:"本机", text:"78 特征 R 库接口随版本变，逐列核对修对 76/78" },
  ]},
]);
pageno(s);

// ============================================================ 部署工程 ③ 第二批 5 工具（按工具）
s = pres.addSlide();
header(s, "04 · 部署工程 · 按工具", "各工具遇到的问题（第二批 5 工具）", C.teal);
srcLegend(s);
toolIssueGrid(s, [
  { name:"PRIME", meta:"提呈 + TCR", accent:C.teal, issues:[
    { env:"HPC", text:"26 个罕见 allele 不支持，PRIME.x 卡死不报错" },
    { env:"HPC", text:"按 PID 净杀僵死进程 + 预筛排除标 NaN 才跑完" },
    { env:"HPC", text:"输出与官方完全一致（r=1.0），防伪通过" },
  ]},
  { name:"ImmuneApp", meta:"提呈 + 免疫原性", accent:C.teal, issues:[
    { env:"HPC", text:"repo 880M 巨权重 git clone 卡死，改 tarball 下载" },
    { env:"HPC", text:"TF1.15 一次 pip 依赖死循环，先单装 TF 再装其余" },
  ]},
  { name:"deepHLApan", meta:"双模型 · 镜像", accent:C.teal, issues:[
    { env:"本机", text:"py2.7 + 老 keras 版本地狱，改用官方 Docker" },
    { env:"本机", text:"输出目录不自建须先 mkdir；HLA 格式无星号" },
  ]},
  { name:"HLAthena", meta:"仅提呈 · proxy 单列", accent:C.warn, issues:[
    { env:"本机", text:"镜像空壳，GCS 凭证 401 死锁，改匿名直链下模型" },
    { env:"HPC",  text:"误拉整模型目录会暴涨几百 G，精确下" },
    { env:"HPC",  text:"3 真 bug：CRLF 进肽长 / 混长度崩 / 孤儿抢 CPU" },
    { env:"HPC",  text:"分块跑 70 块被内存杀（覆盖 266/336，逐肽 98%）" },
  ]},
  { name:"MHLAPre", meta:"未做成", accent:C.crit, issues:[
    { env:"—", text:"无官方权重 + 预处理数据缺 + 拼装码被注释，跑不通" },
    { env:"—", text:"全网搜权重为空，唯一出路：邮件作者" },
  ]},
]);
pageno(s);

// ============================================================ 数据集来源与规模
s = pres.addSlide();
header(s, "测试数据从哪来", "ELISpot 实测数据 · 规模 · 正负比");
const dscards = [
  ["DS2 · 主测试集（有阴有阳）","028090",[
    "101 条肽段：有反应 90 条 / 无反应 11 条",
    "来自 9 位患者；反应值 SFC 范围 −34 ~ 209",
    "用途：算 AUC（能不能分开有反应与无反应）"]],
  ["DS1 · 定量验证集（全阳）","00A896",[
    "82 条肽段：全部有反应，无阴性",
    "来自 6 位患者；强度 SFC 16 ~ 677（约 40 倍跨度）",
    "用途：检验能不能把强弱排对"]],
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
  { text:"SFC = 斑点形成细胞数，是 T 细胞反应强度的实验读数；阈值 >0 记为有反应。", options:{ color:"CADCFC", fontSize:10.5, breakLine:true, paraSpaceAfter:10 } },
  { text:"展开规模", options:{ bold:true, color:"FFFFFF", fontSize:12, breakLine:true } },
  { text:"每条肽按子肽×HLA 窗口展开，DS1+DS2 共 34,247 行预测。", options:{ color:"CADCFC", fontSize:10.5, breakLine:true, paraSpaceAfter:10 } },
  { text:"局限", options:{ bold:true, color:"FFFFFF", fontSize:12, breakLine:true } },
  { text:"样本来自有限患者，存在聚集；DS2 阴性仅 11 条，置信区间偏宽。", options:{ color:"CADCFC", fontSize:10.5 } },
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
  ["算指标","Spearman / AUC\n/ PPV / MCC",C.teal],
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
  if(i<flow.length-1) s.addShape(pres.shapes.LINE, { x:x+bw+0.02, y:by+bh/2, w:bgap-0.04, h:0, line:{color:C.gray, width:1.5, endArrowType:"triangle"} });
});
s.addShape(pres.shapes.RECTANGLE, { x:0.72, y:4.7, w:11.9, h:1.95, fill:{color:"F2F7F7"}, line:{color:C.line,width:1} });
s.addText("读这张图", { x:0.95, y:4.85, w:11, h:0.36, fontFace:FH, fontSize:14, bold:true, color:C.teal, margin:0 });
s.addText([
  { text:"同一批肽段喂给 9 个工具，每个工具独立打分。因为一条肽会拆成多个子肽与 HLA 组合，统一按逐肽取最高分聚合，再按实验反应值 SFC 是否大于零切成有反应与无反应两类，最后用同一套指标评估，9 个工具便落在完全相同的口径上横向对比。", options:{ color:C.ink, fontSize:11.5, breakLine:true, paraSpaceAfter:5 } },
  { text:"关键在于所有工具走完全一致的聚合、阈值与指标口径，保证彼此可比。", options:{ color:C.dark, fontSize:11.5, bold:true } },
], { x:0.95, y:5.25, w:11.45, h:1.3, fontFace:FB, valign:"top", lineSpacingMultiple:1.08, margin:0 });
pageno(s);

// ============================================================ 基准方法/数据
s = pres.addSlide();
header(s, "基准方法", "用什么数据、怎么比、看什么指标");
const mcards = [
  ["测试数据","真实 ELISpot 实验数据 DS2：101 条肽段。按实验反应值切分，有反应 90 条、无反应 11 条（反应值不大于零算真无反应）。","028090"],
  ["参评工具","9 个进基准：8 个免疫原性工具直接横比 + HLAthena（提呈 proxy）单列参照。MHLAPre 因缺权重未参评。","00A896"],
  ["怎么比","一条肽段会拆成多个子肽与 HLA 组合，先聚合（取最大或平均）再按阈值切。主口径是取最大、阈值大于零，保证各工具同口径。","1C7293"],
  ["看什么","首要看 Spearman 相关（分数与反应强弱是否同向，能不能分强弱）——主口径为患者内 Fisher-Z 聚合（计入患者差异），全局 max 作对照；其次看 AUC（能不能分开有反应与无反应，0.5 等于瞎猜），辅以 AUPRC。用 2000 次重抽样给出置信区间。","028090"],
];
let my=1.85;
mcards.forEach(m=>{
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:my, w:11.9, h:1.18, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:my, w:0.09, h:1.18, fill:{color:m[2]} });
  s.addText(m[0], { x:1.0, y:my+0.16, w:2.4, h:0.85, fontFace:FH, fontSize:15, bold:true, color:m[2], valign:"top", margin:0 });
  s.addText(m[1], { x:3.4, y:my+0.14, w:9.0, h:0.9, fontFace:FB, fontSize:12, color:C.ink, valign:"middle", lineSpacingMultiple:1.05, margin:0 });
  my += 1.28;
});
s.addText("口径校验：旧 5 工具复现与历史结果最大差不超过 0.004（浮点精度内），口径对齐通过；所有数字经 csv 三方核对。", { x:0.7, y:6.95, w:11.9, h:0.4, fontFace:FB, fontSize:10.5, italic:true, color:C.muted, margin:0 });
pageno(s);

// ============================================================ 看懂这些指标（Spearman 主、AUC 次）
s = pres.addSlide();
header(s, "先看懂这些指标", "后面每个数字是什么意思、最该信哪个");
const metricCards = [
  ["Spearman 相关（能否分强弱）","模型分数的高低排序，和真实反应强弱的排序，吻合到什么程度。","+1 = 完全同向，0 = 没关系，−1 = 完全反着。这是本项目最关心的能力。",C.sea,"★ 首要"],
  ["AUC（判别力）","随便挑一条有反应、一条没反应，模型给有反应那条打分更高的概率。","1 = 完美，0.5 = 和瞎猜一样，小于 0.5 = 反着的。仅作参考。",C.teal,"参考"],
  ["PPV@10（前10命中率）","把分数最高的 10 条挑出来，里面真有反应的比例。","临床只能合成排在最前的几条肽，所以这个最贴近实战。",C.teal,"贴临床"],
  ["AUPRC","精确率-召回率曲线下的面积，阳性很少时比 AUC 更敏感。","本数据阳性本就占 89%，起点就高，提升空间小，参考意义有限。",C.warn,"参考有限"],
  ["MCC","同时看真阳、假阳、真阴、假阴四格的平衡分。","取值 −1 到 +1，类别不平衡时比准确率更稳。",C.sea,"辅助"],
  ["95% 置信区间 / p 值","重复抽样 2000 次看指标的波动范围；p<0.05 才算不是偶然。","区间越宽越不确定。本数据样本小（101 条、阴性仅 11），区间普遍偏宽。",C.crit,"看可信度"],
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
  { text:"本报告首要看 Spearman（能否分强弱），AUC（判别力）只作参考；AUPRC 因阳性占比高、参考有限；样本量小，所有指标的置信区间都偏宽，结论以方向性为主，不抠零点几的差距。", options:{ color:C.ink, fontSize:10.5 } },
], { x:0.7, y:6.9, w:11.95, h:0.5, fontFace:FB, valign:"top", lineSpacingMultiple:1.02, margin:0 });
pageno(s);

// ====================================================================================
// ===== 基准结果（块 E · v3 对齐）：① 按患者衡量（首要，计入患者差异）→ ② 全局 Spearman（对照）→ ③ AUC（判别力，参考）=====
// ===== 全量对齐 v3 子集图：三张均为本批 10 工具，ratio≈1.20，figSlide 容器按 ~1.20 取 contain 不拉伸 =====
// ====================================================================================

// —— E1 ⭐ 按患者衡量的定量能力（patient-内 Spearman + Fisher-Z 聚合，结果章头条）——
figSlide({
  kicker:"基准结果 · 定量能力（首要）", title:"按患者衡量能不能分强弱：患者内 Spearman + Fisher-Z 聚合（计入患者差异）", accent:C.teal,
  img:`${FIG}/fig_perpatient_fisherz_10tools_v3.png`, fw:6.6, fh:5.5,
  caption:"图（corrected-full，本批 10 工具子集，max 聚合）：先在每位患者内部各自算 Spearman，再跨患者做 Fisher-Z 加权聚合，并给 95% 置信区间。覆盖 9 个有数据的工具，MHLAPre 因无数据未入图。",
  noteHead:"读图要点（正确定量口径）",
  notes:[
    "这是本项目最关心、也是方法学上正确的定量口径：把所有患者的肽混在一起算一个相关，会被患者之间的尺度差异污染；改为每位患者各自算相关、再做 Fisher-Z 聚合，才真正衡量「同一位患者内部能不能把反应强的肽排在前」。",
    "本批工具里按患者衡量表现最好的是 PRIME，约为 +0.28，置信区间为 [+0.05, +0.48]、下界在零以上；IMPROVE 约为 +0.25，置信区间 [+0.02, +0.46]、下界也勉强为正。这两个是仅有的、置信区间排除零的工具。",
    "PredIG 按患者衡量约 +0.23，但置信区间下界略低于零（约 −0.003），未达稳定显著；其余工具的相关都落在零附近，没有一个达到中等强度（0.2 到 0.5）的稳定正相关。",
    "结论：现有工具对免疫强弱的定量能力普遍偏弱，撞在一条不高的天花板上；这正是「预测反应强弱」这件事值得做的直接证据。",
  ],
  cite:"评估数据集 DS2 corrected-full · 患者内 Spearman + Fisher-Z 加权聚合 · 数字见 analysis/per_patient_spearman_16tools.csv",
});

// —— E2 全局 Spearman（所有患者肽混合池化，作对照）——
figSlide({
  kicker:"基准结果 · 定量能力（对照）", title:"全局 Spearman 对照：所有患者肽混合后算一个相关（10 工具）", accent:C.sea,
  img:`${FIG}/fig_spearman_10tools_v3.png`, fw:6.6, fh:5.5,
  caption:"图（HLA 修复后 corrected-full，本批 10 工具，每工具取 |ρ| 最大聚合）：把所有患者的肽混在一起算的全局 Spearman。这是上一页「患者内」口径的对照——未计入患者间差异，仅供参照。",
  noteHead:"读图要点（对照口径）",
  notes:[
    "这张图把所有患者的肽混在一起算一个相关，没有区分患者，会把患者间的尺度差异混进来，所以只作对照，不是首要口径。",
    "在 max 聚合口径下，本批工具里 IMPROVE（+0.252，p=0.011）与 PredIG（+0.201，p=0.044）双双达到统计显著的正相关，PRIME（+0.158）、pTuneos（+0.119）为正但不显著。",
    "DeepImmuno（−0.089）呈弱负相关，deepHLApan（+0.002）几乎为零，说明它们的打分排序与真实强弱基本无关。",
    "换用其它子肽聚合方式（如取前三高分平均）相关系数会随之变化，说明聚合方式会影响排序结论（详见 pooling 聚合专章）；本表主榜统一以患者内 Fisher-Z 为准。",
  ],
  cite:"评估数据集 DS2 corrected-full · 每条肽取 |ρ| 最大聚合 · 数字见 analysis/metrics_ds2_16tools.csv",
});

// —— E3 判别力 AUC（参考，AUC 值逐字照搬历史横评，未重算）——
figSlide({
  kicker:"基准结果 · 判别力（参考）", title:"判别力 AUC：普遍偏弱、彼此分不出显著高下、新工具没带来增量（10 工具）", accent:C.warn,
  img:`${FIG}/fig_auc_10tools_v3.png`, fw:6.6, fh:5.5,
  caption:"图（DS2，max 聚合，阈值>0）：本批 10 工具的 AUC 点估加 95% 置信区间。AUC 只反映能否区分「有反应 / 无反应」，不等于能定量强弱，仅作参考。",
  noteHead:"读图要点（参考指标）",
  notes:[
    "判别力普遍偏弱：点估最高的是 pTuneos 0.718，但无反应样本只有 11 个，置信区间很宽；多数工具的区间下界都跌破随机线 0.5。",
    "彼此分不出高下：头部工具两两相比，差距都跨过 0（无反应样本只有 11 个），统计上区分不开，故只说「点估居前」、不下「最优」结论。",
    "新工具没带来增量：第二批工具在所有口径下都没超过第一批最好的点估（ImmuneApp 0.591 / PRIME 0.517 / deepHLApan 0.445），这个结论很稳。",
    "AUC 与前两页 Spearman 的结论一致：无论按全局还是按患者衡量，现有工具对免疫原性的预测能力整体偏弱。",
  ],
  cite:"评估数据集 DS2 · max 聚合、阈值>0 · AUC 数字取自 analysis/metrics_ds2_16tools.csv（2026-06-28 全量重算）",
});

// —— E4 判别力 ROC 曲线（v3 修正版，9 工具有数据，ratio≈1.20，容器 fw6.6/fh5.5 取 contain）——
figSlide({
  kicker:"基准结果 · 判别力（参考）", title:"判别力 ROC 曲线 — 多数贴近随机对角线", accent:C.warn,
  img:`${FIG}/fig_roc_10tools_v3.png`, fw:6.6, fh:5.5,
  noteHead:"读图要点（参考指标）",
  notes:[
    "ROC 曲线把判别力画成一条线，曲线越凸向左上角代表判别力越强，越贴近对角线代表越接近随机猜测。",
    "pTuneos 的曲线最明显凸向左上，PredIG、NeoTImmuML、ImmuneApp 次之，deepHLApan 和 HLAthena 则落在对角线下方。",
    "这与 AUC 柱状图互相印证，只有少数工具具备一定的二分判别力，整体都谈不上强。",
  ],
  cite:"评估数据集 DS2 corrected-full · 肽级最大分聚合，Elispot 大于零为阳性",
});

// —— E5 工具间一致性热图（v3 修正版，ratio≈1.12，容器 fw6.6/fh5.5 取 contain）——
figSlide({
  kicker:"基准结果 · 一致性（对照）", title:"工具之间一致吗 — 彼此基本不相关", accent:C.sea,
  img:`${FIG}/fig_consistency_10tools_v3.png`, fw:6.6, fh:5.5,
  noteHead:"读图要点（一致性）",
  notes:[
    "这张热力图把工具在同一批肽段上的打分两两做 Spearman 相关，颜色越绿越正相关，越红越负相关，对角线恒为一。",
    "对角线以外大多接近零，说明不同工具对同一条肽的排序基本各说各话；其中 IMPROVE 与 PRIME 约零点六八相对最高，可能与方法或训练数据重叠有关。",
    "工具之间缺乏共识，意味着没有哪一个能当公认标准，简单平均集成的提升也有限。",
  ],
  cite:"评估数据集 DS2 corrected-full，101 条肽 · 肽级分数两两 Spearman 相关",
});

// —— E6 按肽长分层 AUC（v3 修正版宽图 ratio≈2.19，用更宽更矮容器 fw9.5/fh4.6，contain 保比例不拉伸）——
figSlide({
  kicker:"基准结果 · 稳健性（参考）", title:"按肽长分层的判别力 AUC — 看是否跨肽长稳健", accent:C.warn,
  img:`${FIG}/fig_lenstrat_10tools_v3.png`, fw:9.5, fh:4.6,
  noteHead:"读图要点（稳健性）",
  notes:[
    "把肽段按长度分成几个区间分别看各工具的 AUC，可以检查判别力是不是只在某个肽长上成立。",
    "整体看判别力在不同肽长区间并不稳定，没有哪个工具在所有区间都明显优于随机线。",
    "分层后每个区间样本更小，这张图只作稳健性参考，不下定论。",
  ],
  cite:"评估数据集 DS2 corrected-full · 按肽长分层，AUC 仅作参考",
});

// —— E9 HLAthena proxy 单列 ——
s = pres.addSlide();
header(s, "基准结果 · 提呈参照（单列）", "HLAthena 预测的是提呈不是免疫原性，单独看、不与前 8 个并比", C.warn);
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:1.78, w:7.5, h:5.05, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addText("在 ELISpot 上的表现（DS2）", { x:0.95, y:1.95, w:7.0, h:0.4, fontFace:FH, fontSize:15, bold:true, color:C.dark, margin:0 });
const hla = [
  ["AUC（取最大，阈值>0）","0.415","略低于随机（0.5）",C.crit],
  ["AUC（各种口径范围）","0.42 – 0.62","没有一个明显离开随机",C.crit],
  ["与反应强度的相关","0.09 – 0.19","全都不显著",C.warn],
  ["AUPRC","0.864","数据本身阳性占比就 0.89，谈不上提升",C.warn],
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
  { text:"HLAthena 在免疫原性上接近随机，这恰恰符合它的本职，它只预测能否被提呈，论文也明说不预测能否激活 T 细胞。所以它在这里只当提呈参照，", options:{ color:C.ink, fontSize:11 } },
  { text:"单列，不和 8 个免疫原性工具直接并比。", options:{ bold:true, color:C.dark, fontSize:11 } },
], { x:1.15, y:5.56, w:6.6, h:1.06, fontFace:FB, valign:"middle", lineSpacingMultiple:1.04, margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:8.4, y:1.78, w:4.35, h:5.05, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addText("覆盖度与工程说明", { x:8.65, y:1.95, w:3.9, h:0.4, fontFace:FH, fontSize:15, bold:true, color:C.warn, margin:0 });
s.addText([
  { text:"逐肽覆盖 92/101（91%）", options:{ bold:true, color:C.dark, fontSize:11.5, breakLine:true } },
  { text:"HLAthena 只支持 8/9/10/11 长度的肽，少数肽段因落在支持长度外无分；每条肽段取其所有子肽中的最高分，逐肽结论依然稳。", options:{ color:C.ink, fontSize:10.5, breakLine:true, paraSpaceAfter:10 } },
  { text:"分块计算 266/336 完成", options:{ bold:true, color:C.dark, fontSize:11.5, breakLine:true } },
  { text:"在共享登录节点上跑，部分小任务因节点高负载被系统中止；因覆盖已达 91%，不影响近随机的结论。", options:{ color:C.ink, fontSize:10.5, breakLine:true, paraSpaceAfter:10 } },
  { text:"模型下载绕坑", options:{ bold:true, color:C.dark, fontSize:11.5, breakLine:true } },
  { text:"镜像自带的下载凭证已失效，改用匿名直链下模型、改配置走本地挂载，才跑通。", options:{ color:C.ink, fontSize:10.5, breakLine:true } },
], { x:8.65, y:2.45, w:3.9, h:4.3, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
citeFoot(s, "HLAthena, Nature Biotechnology 2020 · DOI 10.1038/s41587-019-0322-9 · 数字见 analysis/metrics_ds2_16tools.csv（n=92）");
pageno(s);

// ============================================================ 诚实边界 + 许可红线
s = pres.addSlide();
header(s, "诚实边界", "已知限制与红线（先讲清楚）", C.warn);
const cav = [
  ["样本量很小","无反应样本只有 11 个，所有 AUC 与相关的置信区间都偏宽，工具间不到 0.05 的差距不显著。这正是没有稳定最优这一结论的来源。",C.crit],
  ["数据有聚集","101 条肽来自 9 个病人，前两个病人贡献了约 45% 的阴性肽，有效样本数其实小于 101，AUC 可能部分在区分病人。需按病人分层复核。",C.warn],
  ["训练-测试可能重叠","第二批几个工具用公开库训练，可能与本测试集重叠；当前未排重，独立性待核。重叠会让分数偏高，对新工具无增量这个主结论反而更保守、更稳。",C.warn],
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
s.addText("许可红线", { x:9.05, y:2.0, w:3.5, h:0.4, fontFace:FH, fontSize:16, bold:true, color:"F2C2C7", margin:0 });
s.addText([
  { text:"netMHCpan / netMHCstabpan", options:{ bold:true, color:"FFFFFF", fontSize:12.5, breakLine:true } },
  { text:"采用 DTU 学术许可。未经书面同意，不得把在其软件上跑出的结果（含数字）对外发布。", options:{ color:"F2C2C7", fontSize:11, breakLine:true, paraSpaceAfter:12 } },
  { text:"本项目正是基准评测", options:{ bold:true, color:"FFFFFF", fontSize:12.5, breakLine:true } },
  { text:"论文或对外材料若含这些工具跑出的对比数字，须先取得 DTU 书面同意（投稿阶段处理）。", options:{ color:"F2C2C7", fontSize:11, breakLine:true, paraSpaceAfter:12 } },
  { text:"deepHLApan = GPL-2.0", options:{ bold:true, color:"FFFFFF", fontSize:12.5, breakLine:true } },
  { text:"公开发布前需做许可合规审查。", options:{ color:"F2C2C7", fontSize:11 } },
], { x:9.05, y:2.5, w:3.55, h:4.2, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
pageno(s);

// ============================================================ 参考文献
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

// ============================================================ 结论 + 下一步（浅底深字）
s = pres.addSlide();
header(s, "结论与下一步", "总结、已知边界与下一步计划");
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:1.7, w:6.1, h:5.25, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:1.7, w:0.09, h:5.25, fill:{color:C.sea} });
s.addText("已经完成", { x:0.98, y:1.86, w:5.6, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.sea, margin:0 });
s.addText([
  { text:"10 个工具全部部署、四类信息全部收集，逐工具文档齐备。", options:{ breakLine:true, color:C.ink, fontSize:12.5, paraSpaceAfter:9, lineSpacingMultiple:1.16 } },
  { text:"9 个跑进统一 ELISpot 基准；唯一的 MHLAPre 因缺权重未完成，已尽力核实并留下可行出路。", options:{ breakLine:true, color:C.ink, fontSize:12.5, paraSpaceAfter:9, lineSpacingMultiple:1.16 } },
  { text:"主结论：现有工具对反应强弱的定量能力普遍偏弱。按主口径（患者内 Fisher-Z，2026-06-28 与 README 统一）只有 PRIME（+0.279）与 IMPROVE（+0.250）的置信区间排除零、达稳定显著，最高也仅到约 +0.28；全局对照口径下则改为 IMPROVE（+0.252）与 PredIG（+0.201）双双显著——两口径头名不同，说明聚合是否计入患者差异会改变结论。判别力 AUC 同样普遍偏弱、彼此分不出显著高下，新工具没有带来增量。", options:{ breakLine:true, color:C.ink, fontSize:12.5, paraSpaceAfter:9, lineSpacingMultiple:1.16 } },
  { text:"HLAthena（提呈 proxy）接近随机，印证了提呈不等于免疫原性，单列作参照。", options:{ breakLine:true, color:C.ink, fontSize:12.5, paraSpaceAfter:9, lineSpacingMultiple:1.16 } },
  { text:"现有工具几乎不能预测反应有多强，反过来说明做强弱定量这件事有空白、有价值。", options:{ color:C.dark, fontSize:12.5, bold:true, lineSpacingMultiple:1.16 } },
], { x:0.98, y:2.32, w:5.6, h:4.5, fontFace:FB, valign:"top", margin:0 });
s.addText("下一步", { x:7.05, y:1.86, w:5.5, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.warn, margin:0 });
const ns=[
  ["先核连续标签够不够","要做强弱回归，先确认公开库里带强度标签的数据量够不够，这是方向的总开关，零算力"],
  ["补充阴性样本","测试集无反应样本仅 11 个，补到 30 个以上再重测，结论更稳"],
  ["排查训练-测试重叠","把测试肽与公开训练库做精确比对，报告重叠比例"],
  ["接入正式数据","课题组正式数据到位后，按各工具格式转换再正式测一轮"],
  ["对外许可","投稿前取得 DTU 书面同意（netMHCpan 相关数字）"],
];
let ny=2.36;
ns.forEach(g=>{
  s.addShape(pres.shapes.RECTANGLE, { x:7.05, y:ny, w:5.55, h:0.86, fill:{color:C.light}, line:{color:C.line,width:1} });
  s.addShape(pres.shapes.RECTANGLE, { x:7.05, y:ny, w:0.08, h:0.86, fill:{color:C.warn} });
  s.addText(g[0], { x:7.3, y:ny+0.1, w:5.15, h:0.32, fontFace:FH, fontSize:12.5, bold:true, color:C.ink, margin:0 });
  s.addText(g[1], { x:7.3, y:ny+0.42, w:5.15, h:0.4, fontFace:FB, fontSize:9.5, color:C.muted, valign:"top", margin:0 });
  ny += 0.96;
});
citeFoot(s, "基准数字均经 csv 三方核对 · 逐工具四类信息见 TOOLS/ 目录 · 工具出处见参考文献页");
pageno(s);

// ---------- write ----------
pres.writeFile({ fileName: "D:/YJ-Agent/project/meeting/QuantImmuBench/QuantImmuBench_10工具横评_2026-06-28.pptx" })
  .then(f=>console.log("WROTE", f, "pages", _PG))
  .catch(e=>{ console.error("ERR", e); process.exit(1); });
