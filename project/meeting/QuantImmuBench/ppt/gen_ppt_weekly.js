// QuantImmuBench — 本周工作简报（3 页）2026-06-26
// 范围：余嘉本周(06-24~26)在新抗原免疫原性工具部署测试项目上的工作汇报
// 数字均经 analysis/metrics_ds2_9tools.csv (max,>0) + ds1_magnitude_spearman_bestbinder.csv 核对
// 运行: NODE_PATH=C:/Users/yj200/AppData/Roaming/npm/node_modules node gen_ppt_weekly.js
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "新抗原免疫原性预测工具 — 本周工作简报";

const W = 13.33, H = 7.5;
const C = {
  dark:"0B3C49", teal:"028090", sea:"00A896", mint:"02C39A",
  light:"F2F7F7", card:"FFFFFF", ink:"16323A", muted:"5E7B83",
  line:"D5E3E4", warn:"C9743D", ok:"00A896", crit:"B23A48", gray:"8A9BA0",
};
const FH = "Microsoft YaHei", FB = "Microsoft YaHei", FM = "Consolas";
const FIG = "D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/figures";
const sh = () => ({ type:"outer", color:"0B3C49", blur:9, offset:3, angle:135, opacity:0.12 });

function header(slide, kicker, title, accent=C.teal){
  slide.background = { color: C.light };
  slide.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:0.28, h:H, fill:{color:accent} });
  slide.addText(kicker.toUpperCase(), { x:0.7, y:0.42, w:11, h:0.3, fontFace:FB, fontSize:12, color:accent, bold:true, charSpacing:3, margin:0 });
  slide.addText(title, { x:0.7, y:0.72, w:12, h:0.7, fontFace:FH, fontSize:25, color:C.ink, bold:true, margin:0 });
}
function pageno(slide, n){ slide.addText(String(n), { x:W-0.8, y:H-0.5, w:0.5, h:0.3, fontFace:FB, fontSize:11, color:C.muted, align:"right", margin:0 }); }
function infoCard(slide, x, y, w, h, head, lines, accent){
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill:{color:C.card}, line:{color:C.line, width:1}, shadow:sh() });
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w:0.09, h, fill:{color:accent} });
  slide.addText(head, { x:x+0.28, y:y+0.16, w:w-0.4, h:0.34, fontFace:FH, fontSize:15, bold:true, color:accent, margin:0 });
  const rt = lines.map((t)=>({ text:t, options:{ bullet:{indent:12}, breakLine:true, color:C.ink, fontSize:12, paraSpaceAfter:6 } }));
  slide.addText(rt, { x:x+0.3, y:y+0.6, w:w-0.55, h:h-0.72, fontFace:FB, valign:"top", margin:0 });
}
function stat(slide, x, y, w, big, label, col){
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w, h:1.45, fill:{color:C.card}, line:{color:C.line, width:1}, shadow:sh() });
  slide.addText(big, { x, y:y+0.16, w, h:0.74, fontFace:FH, fontSize:34, bold:true, color:col, align:"center", margin:0 });
  slide.addText(label, { x:x+0.1, y:y+0.92, w:w-0.2, h:0.42, fontFace:FB, fontSize:11.5, color:C.muted, align:"center", valign:"top", margin:0 });
}

// ============ P1 本周工作概览 ============
{
  const s = pres.addSlide();
  s.background = { color: C.dark };
  s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:0.28, h:H, fill:{color:C.mint} });
  s.addText("本周工作简报 · 2026-06-26", { x:0.7, y:0.55, w:11, h:0.35, fontFace:FB, fontSize:13, color:C.mint, bold:true, charSpacing:3, margin:0 });
  s.addText("新抗原免疫原性预测工具 — 部署测试与基准评估", { x:0.7, y:0.95, w:12, h:0.9, fontFace:FH, fontSize:28, color:"FFFFFF", bold:true, margin:0 });
  s.addText("癌症个性化新抗原疫苗协作项目 · 预测工具组", { x:0.7, y:1.85, w:12, h:0.4, fontFace:FB, fontSize:13, color:"AFCBD0", margin:0 });

  // 四个关键数字
  stat(s, 0.7, 2.6, 2.85, "10", "工具完成部署测试", C.mint);
  stat(s, 3.75, 2.6, 2.85, "9", "进入 ELISpot 横评", C.sea);
  stat(s, 6.8, 2.6, 2.85, "4 类", "信息逐工具收齐", C.teal);
  stat(s, 9.85, 2.6, 2.78, "2 份", "横评 PPT + 数据包", C.warn);

  // 本周主要工作
  const lines = [
    "完成 10 个免疫原性预测工具的 HPC / 本地部署测试，逐工具收齐输入格式 / 参数 / 输出含义 / 工具简介 4 类信息",
    "建统一口径横评流水线（统一输入切窗 → max 聚合 → ELISpot 真值 → 三档阈值 → AUC + AUPRC + Spearman），9 工具同条起跑线",
    "补横评方法学依据：七步拉齐流程 + 自创 / 有文献依据家底表 + best-binder 聚合与 ELISpot 定量真值的文献回填",
    "跨成员对账组内另一位的数据：数据集 100% 同源、PRIME 原始分相关 r=0.94、三工具结论一致",
    "产出 10 工具横评 PPT（40 页）+ 5 工具客观版（26 页）+ 数据交付包 + 私有代码仓库（已脱敏）",
  ];
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:4.35, w:11.93, h:2.75, fill:{color:"0F4A58"}, line:{color:"1C6B7A", width:1} });
  s.addText("本周主要工作", { x:0.95, y:4.5, w:11, h:0.36, fontFace:FH, fontSize:16, bold:true, color:C.mint, margin:0 });
  s.addText(lines.map((t)=>({ text:t, options:{ bullet:{code:"2022", indent:14}, breakLine:true, color:"E6F2F2", fontSize:12.5, paraSpaceAfter:8 } })),
    { x:1.0, y:4.95, w:11.4, h:2.0, fontFace:FB, valign:"top", margin:0 });
  pageno(s, 1);
}

// ============ P2 核心结果 ============
{
  const s = pres.addSlide();
  header(s, "核心结果", "9 工具 ELISpot 基准评估 — 谁能定量预测免疫强弱？", C.teal);

  // 左：横评表
  const rows = [
    ["工具", "AUC", "类型"],
    ["pTuneos", "0.75", "免疫原性"],
    ["PredIG", "0.66", "免疫原性"],
    ["NeoTImmuML★", "0.66", "免疫原性"],
    ["IMPROVE", "0.62", "免疫原性"],
    ["ImmuneApp", "0.59", "免疫原性"],
    ["PRIME", "0.53", "免疫原性"],
    ["HLAthena", "0.51", "提呈 proxy"],
    ["DeepImmuno", "0.48", "免疫原性"],
    ["deepHLApan", "0.42", "免疫原性"],
  ];
  const tb = rows.map((r,i)=> r.map((c,j)=>({
    text:c,
    options:{
      fontFace: j===0?FH:FB, fontSize: i===0?12:11.5, bold: i===0,
      color: i===0?"FFFFFF":(j===1?C.dark:C.ink),
      fill:{ color: i===0?C.teal : (i%2? "FFFFFF":"EEF5F5") },
      align: j===0?"left":"center", valign:"middle",
    }
  })));
  s.addTable(tb, { x:0.7, y:1.75, w:5.5, colW:[2.6,1.3,1.6], rowH:0.42, border:{type:"solid", color:C.line, pt:1} });
  s.addText("★ NeoTImmuML 为复刻官方算法的自训版（官方权重不可得）", { x:0.7, y:6.45, w:5.6, h:0.5, fontFace:FB, fontSize:9.5, italic:true, color:C.muted, valign:"top", margin:0 });

  // 右：图
  s.addShape(pres.shapes.RECTANGLE, { x:6.5, y:1.7, w:6.15, h:3.55, fill:{color:C.card}, line:{color:C.line, width:1}, shadow:sh() });
  s.addImage({ path:`${FIG}/fig6_8tools_auc_comparison.png`, x:6.62, y:1.8, w:5.9, h:3.35, sizing:{type:"contain", w:5.9, h:3.35} });

  // 右下：结论卡
  infoCard(s, 6.5, 5.45, 6.15, 1.55, "一句话结论", [
    "现有工具能判「有 / 无免疫原性」，但对免疫反应「强弱定量」普遍弱相关（AUC 多在随机线附近，少数到 0.66~0.75）",
    "HLAthena（仅预测 MHC 提呈）近随机 0.51 → 印证「能被提呈 ≠ 能引发免疫」",
  ], C.warn);
  pageno(s, 2);
}

// ============ P3 进展 + 下一步 ============
{
  const s = pres.addSlide();
  header(s, "进展与计划", "完成度盘点 · 遗留 · 下一步", C.sea);

  infoCard(s, 0.7, 1.75, 5.85, 2.55, "✅ 已完成", [
    "10 工具部署测试 + 4 类信息全收齐",
    "9 工具进 ELISpot 统一口径横评，指标 + 图 + 统计稳健性（bootstrap CI）齐全",
    "DS1 全阳样本验「强弱排序」：所有工具相关近 0 → 量化能力的真实空白已用数据钉死",
    "交付物（2 份 PPT + 数据包 + 代码仓库）成型并脱敏",
  ], C.ok);

  infoCard(s, 6.7, 1.75, 5.93, 2.55, "⚠️ 遗留 / 阻塞", [
    "MHLAPre：无公开权重 + 预处理码缺失，自训路也不通 → 唯一出路邮件作者（已尝试）",
    "netMHCstabpan：HPC glibc 版本不足，仅影响 IMPROVE 一个辅助特征，不影响主结论",
    "袁老师统一输入数据尚未下发 → 第二阶段格式转换 + 正式测试待启动",
  ], C.warn);

  infoCard(s, 0.7, 4.55, 11.93, 2.45, "→ 下一步", [
    "数据到位后：按各工具输入格式写转换脚本，在真实数据上做正式批量测试，回填真实输出",
    "配合 QuantImmu 组：把「现有工具难做强弱定量」这一空白，作为自研 QuantImmune 量化算法的立项依据与基线对照",
    "投稿 / 对外前的合规：netMHCpan 系列许可要求取 DTU 书面同意后方可发布其相关对比数字",
  ], C.teal);
  pageno(s, 3);
}

pres.writeFile({ fileName:"D:/YJ-Agent/project/meeting/QuantImmuBench/QuantImmuBench_本周工作简报_2026-06-26.pptx" })
  .then((f)=>console.log("WROTE", f));
