// QuantImmuBench — 原则化交叉验证的融合选择（选哪些工具 × 几个 × 哪种融合）deck，9 页
// 主题：给"融合胜单工具"的头条补严格 nested-LOPO 交叉验证；证 CV-最优实为小 k、单工具 MHCnuggets 足矣，
//       SURV6 六工具无 CV 依据（与 CV 互证、非否定），并给每个方法学决策配一条受控对照（13 条 rationale ledger）。
// 样式引擎复用 gen_ppt_peplen_confounder.js 的 helper（header/pageno/proseCard/citeFoot/placeImg/tbl），
// 配色 Okabe-Ito（#0072B2 蓝 / #E69F00 橙 / #009E73 绿 / #B23A48 红），Microsoft YaHei 中文，LAYOUT_WIDE 13.33×7.5。
// 图片按真实宽高比 contain 不拉伸（ratio 已量好，勿改）。数字全部逐字采用主线+verifier 已核值，零自造。
// 措辞纪律：禁 proven optimal/best/SOTA；null 写「无可检测的整合净优势」不写「证伪」；SURV6=互证/残差非否定。
// 运行(主线跑): NODE_PATH=C:/Users/yj200/AppData/Roaming/npm/node_modules node ppt/gen_ppt_fusion_cv.js
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "QuantImmuBench — 原则化交叉验证的融合选择";

const W = 13.33, H = 7.5;
const C = {
  dark:"0B3C49", teal:"0072B2", blue:"0072B2", orange:"E69F00", green:"009E73",
  light:"F2F7F7", card:"FFFFFF", ink:"16323A", muted:"5E7B83",
  line:"D5E3E4", warn:"E69F00", ok:"009E73", crit:"B23A48", gray:"8A9BA0",
};
const FH = "Microsoft YaHei", FB = "Microsoft YaHei", FM = "Consolas";
const sh = () => ({ type:"outer", color:"0B3C49", blur:9, offset:3, angle:135, opacity:0.12 });

// 4 张图（本窗 analyst 出、逐值核过），ratio = 宽/高（已量好，勿改）
const IMG = {
  kcurve:     { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/figures/fig_fusioncv_kcurve.png",     r:2.3298 },
  procedures: { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/figures/fig_fusioncv_procedures.png", r:1.6046 },
  toolfreq:   { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/figures/fig_fusioncv_toolfreq.png",   r:1.5954 },
  ledger:     { p:"D:/YJ-Agent/project/meeting/QuantImmuBench/figures/fig_fusioncv_ledger.png",     r:1.2420 },
};

let _PG = 1;
function header(slide, kicker, title, accent=C.blue){
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
  const runs=[{ text:"来源  ", options:{ color:C.blue, fontSize:9, bold:true } }];
  txt.split(" · ").forEach((p,i)=>{ runs.push({ text:(i>0?" · ":"")+p, options:{ color:C.muted, fontSize:9 } }); });
  slide.addText(runs, { x:0.7, y:7.08, w:11.9, h:0.34, fontFace:FB, italic:true, valign:"top", margin:0 });
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
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.orange} });
s.addShape(pres.shapes.OVAL, { x:W-3.3, y:-1.6, w:4.6, h:4.6, fill:{color:C.blue, transparency:78} });
s.addShape(pres.shapes.OVAL, { x:W-2.0, y:3.6,  w:3.2, h:3.2, fill:{color:C.orange, transparency:82} });
s.addText("QuantImmuBench 深度分析 · §3.3 融合 / §4.3 选择偏差", { x:0.9, y:1.35, w:11.5, h:0.4, fontFace:FB, fontSize:15, color:C.orange, bold:true, charSpacing:2, margin:0 });
s.addText("原则化交叉验证的融合选择\n选哪些工具 × 选几个 × 用哪种融合", { x:0.9, y:1.95, w:11.6, h:1.9, fontFace:FH, fontSize:32, bold:true, color:"FFFFFF", lineSpacingMultiple:1.05, margin:0 });
s.addShape(pres.shapes.LINE, { x:0.95, y:4.4, w:3.2, h:0, line:{color:C.orange, width:2} });
s.addText([
  { text:"DS2 Braun 2025 · 130 肽 / 9 患者 · 逐患者秩相关（退化守卫）", options:{ breakLine:true, paraSpaceAfter:6 } },
  { text:"外层留一患者 nested-LOPO · 内层前向贪心选融合成员 · pooling=max · 全覆盖 24 工具池", options:{ breakLine:true, paraSpaceAfter:6 } },
  { text:"核心问题：融合到底该选哪些工具、选几个、用哪种融合——用大量交叉验证说话", options:{ breakLine:true, bold:true, color:"F5E3C5" } },
], { x:0.95, y:4.7, w:11.4, h:1.7, fontFace:FB, fontSize:15, color:"E6F2F2", valign:"top", lineSpacingMultiple:1.25, margin:0 });
s.addText("2026-07-05", { x:W-2.4, y:6.75, w:1.8, h:0.3, fontFace:FB, fontSize:12, color:"C9A96A", align:"right", margin:0 });

// ============================================================ 2 一页看懂（核心结论 2×2）
s = pres.addSlide();
header(s, "核心结论", "一页看懂：融合该怎么选", C.blue);
proseCard(s, 0.7, 1.7, 5.75, 2.5, "① CV-最优是小 k，单工具已足", [
  "严格交叉验证下，最强单工具 MHCnuggets 逐患者 ρ̄=0.4466（k=1，此时无选择膨胀）就是曲线的实际拐点；加更多工具，交叉验证成绩不升反抖。",
  "大融合没有交叉验证依据。",
], C.green);
proseCard(s, 6.75, 1.7, 5.85, 2.5, "② 换哪种选法都不超单工具", [
  "前向贪心/后向消除/穷举/单工具排序/去相关五种选择程序，交叉验证成绩全在 0.33~0.40，都低于单工具，且统计上分不出高下（p 全 >0.05）。",
  "38 个候选集统计不可分——连单工具本身都在其中。",
], C.orange);
proseCard(s, 0.7, 4.35, 5.75, 2.5, "③ SURV6 无 CV 依据，但与 CV 互证", [
  "头条的 SURV6 六工具是「存活工具≈朱的六维」的传承先验，成员从未进过交叉验证。",
  "它的 CV 成绩 0.3657 精确复现 R3、几乎不虚高；与本次数据驱动的 CV 结论方向一致=互证，不是否定。",
], C.orange);
proseCard(s, 6.75, 4.35, 5.85, 2.5, "④ 每个方法学决策都配受控实验", [
  "守卫指标 / cover 池 / nested-CV / geomean 算子……13 条对照，每条「只变一处」实证换别的更差或会泄漏。",
  "n=9 下不宣称唯一最优——报 CV-最优 + 不可分带 + 入选频率。",
], C.blue);
citeFoot(s, "PEPTIDE_LENGTH_CONFOUNDER.md §5 · analysis/fusion_cv/*.csv");
pageno(s);

// ============================================================ 3 方法：CV 选择引擎口径
s = pres.addSlide();
header(s, "方法 · 无泄漏的选择程序", "怎么选才诚实：留一患者 + 内层选 + 退化守卫", C.blue);
proseCard(s, 0.7, 1.65, 6.0, 3.15, "统一口径（零泄漏装配）", [
  "外层：留一患者（9 折）——留出的患者只用来「考试」，绝不参与挑工具。",
  "内层：在其余 8 位患者上选融合成员（前向贪心，pooling 固定取最大值）。",
  "候选池：每患者 ≥8 肽的全覆盖 24 工具；评估一律走退化守卫（有效样本 <4 剔患者、丢假满分相关）。",
  "留出患者的分数用「组内独立」融合装配，装满 130 行再算逐患者 ρ̄——within-patient 独立、零泄漏。",
], C.blue);
proseCard(s, 6.85, 1.65, 5.78, 3.15, "作弊上限 vs 交叉验证", [
  "作弊上限（oracle）：用全部数据又挑工具又打分——最乐观。",
  "交叉验证（CV）：只拿留出患者考试——真实水平。",
  "两者之差 = 挑工具带来的虚高（选择膨胀）。",
  "本次实测：k≥2 时膨胀稳定在 0.09~0.15——「按数据重选成员」会系统性抬高约一到一成半。",
], C.orange);
proseCard(s, 0.7, 5.0, 11.93, 1.9, "两个正交 null（验「选到的是信号、不是选择伪迹」）", [
  "患者内置换 null：把 ELISpot 在每位患者体内打乱后重跑整条选择——真 CV=0.3525 显著高于置换（p=0.01）→ 选择抓到的是真信号，不是过拟合噪声。",
  "随机子集 null：从池里随便抽 k 个的偶然天花板——观测值落在其极端尾部（选择确实有效），但这只证「选得对」，不改变「整合相对单工具无净优势」。",
], C.green);
citeFoot(s, "select_engine.py · fusion_nested_cv.py（守卫引擎，import 复用）· select_null.csv");
pageno(s);

// ============================================================ 4 k 学习曲线图
s = pres.addSlide();
header(s, "选几个 · k 学习曲线", "融合几个工具最好？——单调升的是作弊上限，不是真实水平", C.blue);
placeImg(s, IMG.kcurve.p, IMG.kcurve.r, 0.7, 1.65, 8.0, 5.05);
proseCard(s, 8.9, 1.65, 3.73, 5.05, "读图", [
  "上线（作弊上限）随工具数单调升到 0.5435；",
  "下线（交叉验证）从 k=1 的 0.4466 抖到 k=7 名义 0.4495——只高 0.003，且与单工具分不出（p≈0.96）；",
  "两线之间的缝 = 选择膨胀 0.09~0.15；",
  "结论：真实水平不随融合规模上升，小 k / 单工具足矣。",
], C.orange);
citeFoot(s, "k_curve.csv（raw 口径 · greedy_to_k）· oracle 处处 ≥ CV 已核 0 违例");
pageno(s);

// ============================================================ 5 五种选择程序横比
s = pres.addSlide();
header(s, "怎么选 · 五程序横比", "换哪种选择程序，都赢不了最强单工具", C.blue);
placeImg(s, IMG.procedures.p, IMG.procedures.r, 0.7, 1.65, 7.4, 5.05);
proseCard(s, 8.3, 1.65, 4.33, 5.05, "读图", [
  "前向贪心 0.352 / 后向消除 0.354 / 穷举 0.399 / 单工具排序 0.400 / 去相关贪心 0.327；",
  "全部低于单工具 MHCnuggets 0.4466（虚线），差值全为负；",
  "与单工具的配对检验 p 全 >0.05（0.12 / 0.31 / 0.48 / 0.36 / 0.12）——统计上分不出高下；",
  "措辞纪律：报为「点估已不胜、n=9 功效不足未能检出差异」，不写赢家。",
], C.orange);
citeFoot(s, "select_engine.csv（算子固定 geomean，隔离「程序」变量）");
pageno(s);

// ============================================================ 6 工具入选频率
s = pres.addSlide();
header(s, "选哪些 · 稳定性选择", "反复重采样后，只有一个工具稳定入选", C.blue);
placeImg(s, IMG.toolfreq.p, IMG.toolfreq.r, 0.7, 1.65, 7.4, 5.05);
proseCard(s, 8.3, 1.65, 4.33, 5.05, "读图", [
  "外层 9 折 × 患者 bootstrap（B=200）重采样，记每个工具的入选频率；",
  "只有 MHCnuggets 过 0.6 共识阈（0.795，9 折里 9 次全选）；",
  "次高 netMHCpan_BA 仅 0.411（且是 DTU 工具、待授权）、IEDB_Calis 0.372——都不过阈；",
  "即「哪些工具可信」的正解：稳的就 MHCnuggets 一个，其余是噪声级。",
], C.orange);
citeFoot(s, "select_stability.csv · geomean 算子占 77.8% 折");
pageno(s);

// ============================================================ 7 SURV6 定位
s = pres.addSlide();
header(s, "SURV6 定位", "与 CV 互证、不是否定——把差异摆成「CV 残差」", C.orange);
proseCard(s, 0.7, 1.7, 5.9, 3.0, "两个量必须分清", [
  "① 固定 SURV6 头条本身几乎没虚高：CV 成绩 0.3657 ≈ honest CV 0.352，且 0.3657 精确复现 R3 六维 geomean（raw）。",
  "② 0.17 是「按数据重选融合成员」这个过程的过拟合上界（oracle 0.525 − CV 0.352），不是现有头条被夸大 0.17。",
], C.blue);
proseCard(s, 6.7, 1.7, 5.93, 3.0, "为什么是互证不是否定", [
  "SURV6 可追溯为 selection-informed 先验（存活工具≈朱的六维）；本次 CV 是正交的、纯数据驱动。",
  "两条路方向一致（都指向小 k / 少数工具、大融合无净优势）→ 互相印证。",
  "差异量化成「SURV6 的 CV 残差」，不读作「SURV6 错」。",
], C.green);
proseCard(s, 0.7, 4.85, 11.93, 2.05, "数值锚点（全部已核）", [
  "SURV6 fixed geomean CV：0.3657（raw）/ 0.2945（控肽长）——精确复现 R3 六维 geomean 两口径。",
  "排序：SURV6 0.3657  <  单工具 MHCnuggets 0.4466  <  作弊上限 0.525；SURV6 的六工具成员从未进过任何交叉验证。",
], C.orange);
citeFoot(s, "fusion_nested_cv.csv:fixed_surv6 · official/R3_fusion_12methods_official.csv（geomean ndim=6）");
pageno(s);

// ============================================================ 8 13 条 rationale ledger（图 + 精选表）
s = pres.addSlide();
header(s, "为什么这样做", "13 条方法学决策 · 每条配一个受控对照实验", C.blue);
placeImg(s, IMG.ledger.p, IMG.ledger.r, 0.7, 1.6, 6.35, 5.15);
tbl(s,
  ["#", "方法学决策", "换别的会怎样（Δ）"],
  [
    ["1", "nested-CV 选成员", { text:"in-sample 上界虚高 +0.17", color:C.crit }],
    ["4", "退化守卫指标", { text:"裸口径被小n伪迹抬冠军 +0.18", color:C.crit }],
    ["5", "cover 池（≥8 肽）", { text:"全30 稀疏工具打乱仍虚高 +0.32", color:C.crit }],
    ["5b", "守卫 × 池 双防线", { text:"守卫下两者相等=防线重叠", color:C.muted }],
    ["11", "DTU 入池", { text:"剔 DTU 不翻符号=结论稳", color:C.ok }],
    ["12", "raw 主口径", { text:"控肽长成员漂移=敏感性", color:C.warn }],
    ["13", "geomean 算子", { text:"胜 mean_rank/median/max", color:C.ok }],
  ],
  [0.6, 3.0, 3.65], 7.25, 1.95, { hh:0.45, rh:0.6, hfs:12, bfs:11 }
);
s.addText("读法：#1/#2 撑「诚实 CV 口径」；#4/#5/#5b 撑「守卫 + 池过滤双防线」；#10/#13 撑「钉 geomean」；#11 撑「结论 consent-robust」；#12 是控肽长敏感性 caveat。",
  { x:7.25, y:6.55, w:5.4, h:0.85, fontFace:FB, fontSize:10.5, italic:true, color:C.muted, valign:"top", lineSpacingMultiple:1.15, margin:0 });
citeFoot(s, "rationale_ledger.csv（18 行含子行）· 每条只变一处、其余固定");
pageno(s);

// ============================================================ 9 结论 + 拍板点 + 局限
s = pres.addSlide();
header(s, "结论 · 拍板点 · 局限", "证据齐了，headline 归袁老师 + 朱同学拍板", C.crit);
proseCard(s, 0.7, 1.65, 5.9, 2.75, "可严格达成的结论", [
  "一套无泄漏的 CV 选择程序 + 它选出的（成员 × 数量 × 算子）；",
  "CV-最优 = 小 k、稳定入选仅 MHCnuggets、算子 geomean；",
  "五程序 / k=1..8 / 稳定性 / 38 不可分带四路证据一致：honest CV 下无可检测的整合净优势；",
  "13 条方法学决策全配受控对照实证。",
], C.green);
proseCard(s, 6.7, 1.65, 5.93, 2.75, "🛑 拍板点（本窗不擅改）", [
  "CV 结论与现有 headline 冲突：SURV6 六工具无 CV 依据、CV-最优实为小 k / 单工具 MHCnuggets。",
  "建议：headline 把 SURV6 标注为「selection-informed 先验、CV 正交互证」或明示其无 CV 验证依据。",
  "归袁老师 + 朱同学定；SURV6 摆成互证、非否定朱的工作。",
], C.crit);
proseCard(s, 0.7, 4.55, 11.93, 2.15, "诚实局限（不掩盖）", [
  "单队列 DS2 / n=9：统计功效有限，只能报「CV-最优 + 统计不可分带 + 入选频率」，不宣称唯一最优；null 只写「未检出净优势」不写「证伪」。",
  "跨队列复现（DS1 / 鼠 B16F10·CT26）未做 = G2/G3 全套仍缺；控肽长口径下 CV-最优成员有漂移（#12）；不可分带内多含 DTU 工具（netMHCpan_BA），相关数字对外前需 consent 到位。",
], C.warn);
citeFoot(s, "决策档：给袁老师_肽长矫正决策档.md 拍板点3 · 详版 PEPTIDE_LENGTH_CONFOUNDER.md §5 · 04_LOG Entry 55");
pageno(s);

// ============================================================ 导出
const OUT = "D:/YJ-Agent/project/meeting/QuantImmuBench/QuantImmuBench_融合CV选择_2026-07-05.pptx";
pres.writeFile({ fileName: OUT }).then(()=>{ console.log("[OK] 导出 9 页 →", OUT); }).catch(e=>{ console.error("[ERR]", e); });
