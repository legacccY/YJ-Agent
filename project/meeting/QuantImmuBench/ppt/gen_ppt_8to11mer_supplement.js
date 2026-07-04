// QuantImmuBench — 8-11mer 可变窗补充口径 deck（rev1, 2026-07-04 重建）
// 缘由：原 supplement_2026-07-03 生成脚本丢失 + deepHLApan indel 修复后图/数字/归类过时
//   （原 slide5 把 deepHLApan 当差分工具=错，它 context-free 已补 130）。本脚本用当前图 + 更正文字重建。
// 复用 gen_ppt_progress_v4.js 的 helper（就地拷贝，自包含）。
// 运行: NODE_PATH=C:/Users/yj200/AppData/Roaming/npm/node_modules node ppt/gen_ppt_8to11mer_supplement.js
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "QuantImmuBench — 8-11mer 可变窗补充口径";

const W = 13.33, H = 7.5;
const C = {
  dark:"0B3C49", teal:"028090", sea:"00A896", mint:"02C39A",
  light:"F2F7F7", card:"FFFFFF", ink:"16323A", muted:"5E7B83",
  line:"D5E3E4", warn:"C9743D", ok:"00A896", crit:"B23A48", gray:"8A9BA0",
};
const FH = "Microsoft YaHei", FB = "Microsoft YaHei";
const RE = "D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/official/recompute_effN";
const PF = "D:/YJ-Agent/project/meeting/QuantImmuBench/paper/figures";
const sh = () => ({ type:"outer", color:"0B3C49", blur:9, offset:3, angle:135, opacity:0.12 });

let _PG = 1;
function header(slide, kicker, title, accent=C.teal){
  slide.background = { color: C.light };
  slide.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:0.28, h:H, fill:{color:accent} });
  slide.addText(kicker.toUpperCase(), { x:0.7, y:0.42, w:11, h:0.3, fontFace:FB, fontSize:12, color:accent, bold:true, charSpacing:3, margin:0 });
  slide.addText(title, { x:0.7, y:0.72, w:12, h:0.7, fontFace:FH, fontSize:22, color:C.ink, bold:true, margin:0 });
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
  slide.addText([{ text:"来源  ", options:{ color:C.teal, fontSize:9, bold:true } }, { text:txt, options:{ color:C.muted, fontSize:9 } }],
    { x:0.7, y:7.08, w:11.9, h:0.34, fontFace:FB, italic:true, valign:"top", margin:0 });
}
function placeImg(slide, img, ratio, bx, by, bw, bh){
  slide.addShape(pres.shapes.RECTANGLE, { x:bx, y:by, w:bw, h:bh, fill:{color:C.card}, line:{color:C.line, width:1}, shadow:sh() });
  const aw = bw-0.24, ah = bh-0.24;
  let iw = aw, ih = aw/ratio; if (ih > ah) { ih = ah; iw = ah*ratio; }
  const ix = bx+0.12+(aw-iw)/2, iy = by+0.12+(ah-ih)/2;
  slide.addImage({ path:img, x:ix, y:iy, w:iw, h:ih });
}
function tbl(slide, headers, rows, colW, x, y, opts){
  opts = opts || {};
  const head = headers.map(h=>({ text:h, options:{ fill:{color:C.dark}, color:"FFFFFF", bold:true, fontSize:opts.hfs||12, align:"center", valign:"middle" } }));
  const body = rows.map((r,ri)=> r.map((c,ci)=>{
    const cell = (c && typeof c==="object") ? c : { text:String(c) };
    const zebra = ri%2===0 ? C.card : C.light;
    return { text:cell.text, options:{ fill:{ color:cell.fill||zebra }, color:cell.color||C.ink,
      bold:cell.bold||false, fontSize:cell.fs||opts.bfs||11, align:cell.align||(ci===0?"left":"center"), valign:cell.valign||"middle" } };
  }));
  const rowH = [opts.hh||0.5].concat(rows.map(()=> opts.rh||0.6));
  slide.addTable([head].concat(body), { x, y, w:colW.reduce((a,b)=>a+b,0), colW, rowH,
    border:{ pt:1, color:C.line }, align:"center", valign:"middle", fontFace:FB, autoPage:false });
}
function statChip(slide, x, y, big, small, accent){
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w:2.05, h:1.15, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w:2.05, h:0.09, fill:{color:accent} });
  slide.addText(big, { x, y:y+0.22, w:2.05, h:0.55, fontFace:FH, fontSize:26, bold:true, color:accent, align:"center", margin:0 });
  slide.addText(small, { x, y:y+0.78, w:2.05, h:0.3, fontFace:FB, fontSize:10.5, color:C.muted, align:"center", margin:0 });
}

// ===== 1 封面 =====
let s = pres.addSlide();
s.background = { color: C.dark };
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.mint} });
s.addShape(pres.shapes.OVAL, { x:-1.4, y:H-3.2, w:4.4, h:4.4, fill:{color:C.teal, transparency:80} });
s.addShape(pres.shapes.OVAL, { x:W-2.6, y:-1.4, w:3.4, h:3.4, fill:{color:C.sea, transparency:82} });
s.addText("QuantImmuBench · 补充口径", { x:0.9, y:2.15, w:11, h:0.5, fontFace:FB, fontSize:16, color:C.mint, bold:true, charSpacing:3, margin:0 });
s.addText("8–11mer 可变窗补充口径", { x:0.9, y:2.75, w:11.5, h:1.0, fontFace:FH, fontSize:40, bold:true, color:"FFFFFF", margin:0 });
s.addShape(pres.shapes.LINE, { x:0.95, y:3.95, w:3.2, h:0, line:{color:C.mint, width:2} });
s.addText("主分析用 9AA 单一窗；本补充口径把每条肽按 8/9/10/11mer 全窗切分后 max 池化，检验「可变窗是否优于 9mer」。结论：不推翻、反而加固 9mer 主口径。", { x:0.95, y:4.25, w:10.8, h:1.0, fontFace:FB, fontSize:14, color:"E6F2F2", valign:"top", lineSpacingMultiple:1.25, margin:0 });
s.addText("rev1 · 2026-07-04（deepHLApan indel 修复后重建）", { x:0.95, y:6.5, w:10, h:0.3, fontFace:FB, fontSize:11, color:C.gray, margin:0 });

// ===== 2 方法：scope 收窄 =====
s = pres.addSlide();
header(s, "方法", "scope 收窄 — 只重跑真正需要的，不盲跑 25 工具", C.sea);
tbl(s, ["类别","工具","处理","理由"], [
  [{text:"A 全量已含 8–11",bold:true,align:"left"}, {text:"MHCnuggets/MHCseqNet/MUNIS/ImmuGenX/andy90 等",align:"left"}, {text:"复用原生 8–11 分",align:"left"}, {text:"canonical 已覆盖，仅补 5 缺肽",align:"left"}],
  [{text:"C 严格重跑",bold:true,align:"left"}, {text:"netMHCstabpan / Seq2Neo",align:"left"}, {text:"HPC/本地全 8–11 重跑",align:"left"}, {text:"canonical 只 9mer，工具支持 8–11，不跑则暗藏只 9mer",align:"left"}],
  [{text:"D 限长诚实",bold:true,align:"left"}, {text:"DeepNetBim(9)/DeepImmuno(9–10)/NeoaPred(9)",align:"left"}, {text:"诚实标真实窗长",align:"left"}, {text:"工具官方架构限长，不硬造 8–11", color:C.warn}],
], [2.4, 3.7, 3.0, 3.4], 0.7, 1.85, { rh:0.95, hh:0.5, bfs:11 });
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:5.75, w:11.93, h:1.05, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:5.75, w:0.09, h:1.05, fill:{color:C.warn} });
s.addText([
  { text:"⚠ 口径诚实脚注（本次审计新增）：", options:{ bold:true, color:C.warn, breakLine:false } },
  { text:"DeepNetBim / NeoaPred 长表实际仅有 9mer 子肽分、DeepImmuno 仅 9–10mer —— 这 3 个工具的「8–11mer」列并非真 8–11，是原生架构限长。§2.2 须标注真实窗长，避免过度声称。", options:{ color:C.ink } },
], { x:0.98, y:5.9, w:11.5, h:0.85, fontFace:FB, fontSize:11.5, valign:"top", lineSpacingMultiple:1.15, margin:0 });
citeFoot(s, "长表 Window_Size 逐工具核 · scripts/out/merged_all_tools_30_official_covfix_8to11.csv");
pageno(s);

// ===== 3 图1 并列：9mer vs 8-11mer 各自 30 工具榜 =====
s = pres.addSlide();
header(s, "图1", "30 工具 per-patient Spearman：9mer 主口径 vs 8–11mer 可变窗", C.teal);
placeImg(s, `${RE}/fig1_spearman_30tools_9mer_effN8.png`, 0.9909, 0.55, 1.75, 6.0, 5.4);
placeImg(s, `${RE}/fig1_spearman_30tools_8to11mer_effN8.png`, 0.9909, 6.75, 1.75, 6.0, 5.4);
citeFoot(s, "R1_recomputed_effN8.csv (9mer) + R1_recomputed_8to11mer_effN8.csv (8–11mer) · 主榜=9/9 全覆盖，effN≥8");
pageno(s);

// ===== 4 核心发现：9mer 一致优于 8-11mer =====
s = pres.addSlide();
header(s, "图2 · 核心发现", "9mer 主口径一致优于 8–11mer 可变窗", C.teal);
placeImg(s, `${PF}/fig_9mer_vs_8to11mer_spearman.png`, 1.0339, 0.55, 1.5, 7.5, 5.6);
statChip(s, 8.35, 1.65, "5/5", "Top-5 工具 9mer 全胜", C.mint);
statChip(s, 10.55, 1.65, "86%", "24/28 工具 9mer > 8–11", C.sea);
proseCard(s, 8.35, 3.0, 4.3, 3.6, "要点", [
  "均值 rho：9mer = 0.191 vs 8–11mer = 0.122（两口径都适用的 28 工具；剔 DeepNetBim/NeoaPred 硬 9mer）。",
  "Top-5：MHCnuggets 0.447→0.373、netMHCpan_BA 0.392→0.289、MHCflurry 0.308→0.286、PRIME、NetTepi —— 全部 9mer 更高。",
  "8–11mer 口径不推翻、反而加固 §2.2「9AA 一致优于可变窗」。",
  "注：MHCseqNet 0.246→−0.227、Seq2Neo 0.072→−0.084 可变窗翻负是真实结果非 bug（非 9mer 窗抢走 max 且与免疫原性反相关）。",
], C.teal);
citeFoot(s, "R1_recomputed_effN8.csv + R1_recomputed_8to11mer_effN8.csv · deepHLApan indel 修复后重算");
pageno(s);

// ===== 5 覆盖：24/30 =====
s = pres.addSlide();
header(s, "图3 · 覆盖", "8–11mer 口径工具覆盖：24/30 达 130，其余诚实上限", C.sea);
placeImg(s, `${PF}/fig_8to11mer_coverage.png`, 1.0598, 0.55, 1.55, 6.5, 5.5);
statChip(s, 8.9, 1.65, "24/30", "工具达 130/130", C.mint);
proseCard(s, 7.4, 3.0, 5.25, 3.55, "剩 6 个 <130 = 诚实上限（非 bug，不补零）", [
  "✅ deepHLApan 101→130：context-free 单肽，原被误当差分工具漏 28 indel+1 SNV，本轮补跑修复入主榜。",
  "差分工具（需 MT-vs-WT）：ICERFIRE 100 / NeoaG 102 / pTuneos 102 —— 28 无 WT 肽结构性打不出。",
  "NeoaPred 14：结构工具只吃严格 9mer。",
  "NetTepi 125：模型仅覆盖 13 等位。",
  "HLAthena 121：P101 缺 9 肽（待对齐 zichenli 完整部署，非 8–11 口径引入）。",
], C.sea);
citeFoot(s, "pooled_clean_8to11mer.csv 各 <Tool>_max 非空肽数 · deepHLApan 修复后 23/30→24/30");
pageno(s);

// ===== 6 结论 & 交接 =====
s = pres.addSlide();
header(s, "结论 & 交接", "8–11mer 补充口径小结", C.dark);
proseCard(s, 0.7, 1.7, 6.0, 5.0, "结论", [
  "1. 9mer 主口径一致优于 8–11mer 可变窗（Top-5 全胜、均值 0.191 vs 0.122）→ 加固 §2.2 主分析选 9AA。",
  "2. 24/30 工具在 8–11mer 达满 130 覆盖；deepHLApan 本轮修复后从参考区入主榜。",
  "3. 可变窗使部分工具（MHCseqNet/Seq2Neo）翻负 = 真实信号，非 bug。",
], C.teal);
proseCard(s, 6.9, 1.7, 5.75, 5.0, "交接待办（非本口径 bug）", [
  "① 口径脚注：DeepNetBim/NeoaPred「8–11」实为 9mer-only、DeepImmuno 为 9–10mer → §2.2 须标真实窗长。",
  "② indel 肽在 8–11mer 下实为 9mer-only 池化（全 30 工具共有，源头无 indel 的 8/10/11mer 子肽）→ 诚实标注。",
  "③ HLAthena 121→130 需对齐 zichenli 完整部署（同 9mer 遗留）。",
  "④ 差分工具（ICERFIRE/NeoaG/pTuneos）indel 硬限，补 germline 也打不出 → 论文标覆盖上限。",
], C.warn);
pageno(s);

pres.writeFile({ fileName:"D:/YJ-Agent/project/meeting/QuantImmuBench/QuantImmuBench_8to11mer_supplement_rev1_2026-07-04.pptx" }).then(f=>console.log("WROTE", f, "pages", _PG));
