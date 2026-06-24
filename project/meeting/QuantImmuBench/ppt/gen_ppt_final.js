// QuantImmuBench 最终交付 PPT (2026-06-24) — 保守版
// 余嘉前 5 工具 4 类信息 + 8tools ELISpot benchmark 保守结论 + 蓝海/命门/理论 + QuantImmune 立项
// 所有数字经 csv 核对 (verifier 0 drift)；措辞保守 (无「最优/最强/无可替代」)；NeoTImmuML 标★自训版
// 运行: node gen_ppt_final.js   (需 npm i pptxgenjs)
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "余嘉 (legacccy)";
pres.title = "新抗原免疫原性预测工具部署测试 + Benchmark 报告";

const W = 13.33, H = 7.5;
const C = {
  dark:"0B3C49", teal:"028090", sea:"00A896", mint:"02C39A",
  light:"F2F7F7", card:"FFFFFF", ink:"16323A", muted:"5E7B83",
  line:"D5E3E4", warn:"C9743D", ok:"00A896", crit:"B23A48",
};
const FH = "Microsoft YaHei", FB = "Microsoft YaHei";
const FIG  = "D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/figures";
const FIGD = "D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/figures_deepdive";
const sh = () => ({ type:"outer", color:"0B3C49", blur:9, offset:3, angle:135, opacity:0.12 });

function header(slide, kicker, title, accent=C.teal){
  slide.background = { color: C.light };
  slide.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:0.28, h:H, fill:{color:accent} });
  slide.addText(kicker.toUpperCase(), { x:0.7, y:0.42, w:11, h:0.3, fontFace:FB, fontSize:12, color:accent, bold:true, charSpacing:3, margin:0 });
  slide.addText(title, { x:0.7, y:0.72, w:12, h:0.7, fontFace:FH, fontSize:28, color:C.ink, bold:true, margin:0 });
}
function pageno(slide, n){
  slide.addText(String(n), { x:W-0.8, y:H-0.5, w:0.5, h:0.3, fontFace:FB, fontSize:11, color:C.muted, align:"right", margin:0 });
}
function infoCard(slide, x, y, w, h, head, lines, accent){
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill:{color:C.card}, line:{color:C.line, width:1}, shadow:sh() });
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w:0.09, h, fill:{color:accent} });
  slide.addText(head, { x:x+0.28, y:y+0.16, w:w-0.4, h:0.34, fontFace:FH, fontSize:15, bold:true, color:accent, margin:0 });
  const rt = lines.map((t)=>({ text:t, options:{ bullet:{indent:12}, breakLine:true, color:C.ink, fontSize:11.5, paraSpaceAfter:5 } }));
  slide.addText(rt, { x:x+0.3, y:y+0.58, w:w-0.55, h:h-0.7, fontFace:FB, valign:"top", margin:0 });
}
function badge(slide, x, y, txt, col, w=1.95){
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h:0.42, rectRadius:0.21, fill:{color:col} });
  slide.addText(txt, { x, y, w, h:0.42, fontFace:FB, fontSize:11.5, bold:true, color:"FFFFFF", align:"center", valign:"middle", margin:0 });
}
function toolSlide(o){
  const s = pres.addSlide();
  header(s, "工具 "+o.idx+" / 5 · 4 类信息", o.name, o.accent);
  s.addText(o.tagline, { x:0.7, y:1.5, w:8.6, h:0.5, fontFace:FB, fontSize:13, color:C.muted, margin:0 });
  badge(s, W-2.65, 0.72, o.status, o.statusCol);
  s.addText("方法: "+o.method, { x:W-2.65, y:1.22, w:1.95, h:0.3, fontFace:FB, fontSize:11, color:C.teal, bold:true, align:"center", margin:0 });
  const cx=0.7, cy=2.12, cw=6.0, ch=2.45, gap=0.32;
  infoCard(s, cx,        cy,        cw, ch, "① 输入数据 / 格式", o.input,  o.accent);
  infoCard(s, cx+cw+gap, cy,        cw, ch, "② 运行参数",       o.params, o.accent);
  infoCard(s, cx,        cy+ch+gap, cw, ch, "③ 输出格式 / 含义", o.output, o.accent);
  infoCard(s, cx+cw+gap, cy+ch+gap, cw, ch, "④ 简介 / 特点优势", o.intro,  o.accent);
  pageno(s, o.idx+3);
  return s;
}

// ============================================================ S1 封面
let s = pres.addSlide();
s.background = { color: C.dark };
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.mint} });
s.addShape(pres.shapes.OVAL, { x:W-3.3, y:-1.6, w:4.6, h:4.6, fill:{color:C.teal, transparency:78} });
s.addShape(pres.shapes.OVAL, { x:W-2.0, y:3.6,  w:3.2, h:3.2, fill:{color:C.sea,  transparency:82} });
s.addText("癌症个性化新抗原疫苗 · 工具部署 + Benchmark", { x:0.9, y:1.55, w:11, h:0.4, fontFace:FB, fontSize:15, color:C.mint, bold:true, charSpacing:2, margin:0 });
s.addText("新抗原免疫原性预测工具\n部署测试与基准评估报告", { x:0.9, y:2.1, w:11.5, h:1.8, fontFace:FH, fontSize:42, bold:true, color:"FFFFFF", lineSpacingMultiple:1.05, margin:0 });
s.addText("前 5 工具部署 + 4 类信息 · 8 工具 ELISpot 基准 (保守结论) · QuantImmune 立项支撑", { x:0.9, y:4.25, w:11.5, h:0.5, fontFace:FB, fontSize:15, color:"CADCFC", margin:0 });
s.addShape(pres.shapes.LINE, { x:0.95, y:5.15, w:3.2, h:0, line:{color:C.mint, width:2} });
s.addText([
  { text:"汇报人  ", options:{ color:"8FB7BD", fontSize:13 } },
  { text:"余嘉 (legacccy)", options:{ color:"FFFFFF", fontSize:13, bold:true, breakLine:true } },
  { text:"协作项目  ", options:{ color:"8FB7BD", fontSize:13 } },
  { text:"袁老师课题组 · 西交利物浦大学", options:{ color:"FFFFFF", fontSize:13 } },
], { x:0.95, y:5.4, w:9, h:1.0, fontFace:FB, valign:"top", margin:0 });
s.addText("2026-06-24", { x:W-2.4, y:6.7, w:1.8, h:0.3, fontFace:FB, fontSize:12, color:"8FB7BD", align:"right", margin:0 });

// ============================================================ S2 背景 + 4类信息 + 分工
s = pres.addSlide();
header(s, "项目背景", "任务目标 · 我负责的子任务 · 团队分工");
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:1.7, w:5.55, h:3.55, fill:{color:C.dark}, shadow:sh() });
s.addText("项目总目标", { x:0.98, y:1.95, w:5, h:0.4, fontFace:FH, fontSize:17, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"做能预测 T 细胞反应 ", options:{ color:"FFFFFF", fontSize:14 } },
  { text:"「强弱定量程度」", options:{ color:C.mint, fontSize:17, bold:true } },
  { text:" 的工具 —— 比现有只判「有/无免疫原性」的二分类更进一步。", options:{ breakLine:true, color:"CADCFC", fontSize:13 } },
], { x:0.98, y:2.4, w:5.05, h:1.5, fontFace:FB, valign:"top", lineSpacingMultiple:1.15, margin:0 });
s.addText([
  { text:"技术路线  ", options:{ color:C.mint, fontSize:12.5, bold:true } },
  { text:"大量 benchmark 现有工具 + 数据集 → 结合自研 QuantImmune 算法", options:{ color:"FFFFFF", fontSize:12.5 } },
], { x:0.98, y:4.35, w:5.05, h:0.8, fontFace:FB, valign:"top", lineSpacingMultiple:1.1, margin:0 });
// 团队分工条
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:5.45, w:5.55, h:1.55, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addText("团队分工", { x:0.95, y:5.55, w:5, h:0.32, fontFace:FH, fontSize:13, bold:true, color:C.teal, margin:0 });
s.addText([
  { text:"预测工具组：余嘉 (前 5 工具，本报告) + 李紫晨 (后 5 工具)", options:{ bullet:{indent:10}, breakLine:true, color:C.ink, fontSize:10.5, paraSpaceAfter:3 } },
  { text:"QuantImmu 组：徐伊琳 (HPC 部署 QuantImmune)", options:{ bullet:{indent:10}, breakLine:true, color:C.ink, fontSize:10.5, paraSpaceAfter:3 } },
  { text:"数据收集组：王子源、谢孟翰 (文献 + 数据)", options:{ bullet:{indent:10}, color:C.ink, fontSize:10.5 } },
], { x:0.95, y:5.9, w:5.2, h:1.05, fontFace:FB, valign:"top", margin:0 });
// 右: 4类信息 + 负责工具
s.addText("每个工具收集的 4 类信息", { x:6.7, y:1.78, w:6, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.ink, margin:0 });
const items = [
  ["①","输入数据的模板 / 格式","文件类型、必填列、肽长限制、HLA 格式"],
  ["②","预测工具运行参数","可调参数的类型及功能、运行模式"],
  ["③","输出数据格式及含义","关键列、分数类型、能否定量强弱"],
  ["④","工具简介","方法、特点、优势与局限"],
];
let yy=2.28;
items.forEach(it=>{
  s.addShape(pres.shapes.RECTANGLE, { x:6.7, y:yy, w:5.9, h:0.82, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.OVAL, { x:6.86, y:yy+0.18, w:0.46, h:0.46, fill:{color:C.teal} });
  s.addText(it[0], { x:6.86, y:yy+0.18, w:0.46, h:0.46, fontFace:FH, fontSize:16, bold:true, color:"FFFFFF", align:"center", valign:"middle", margin:0 });
  s.addText(it[1], { x:7.5, y:yy+0.1, w:4.9, h:0.34, fontFace:FH, fontSize:13.5, bold:true, color:C.ink, margin:0 });
  s.addText(it[2], { x:7.5, y:yy+0.44, w:4.9, h:0.3, fontFace:FB, fontSize:10.5, color:C.muted, margin:0 });
  yy += 0.92;
});
s.addShape(pres.shapes.RECTANGLE, { x:6.7, y:5.98, w:5.9, h:1.02, fill:{color:"E6F4F1"}, line:{color:C.sea,width:1} });
s.addText([
  { text:"我负责的 5 工具：", options:{ bold:true, color:C.teal, fontSize:12 } },
  { text:"PredIG · DeepImmuno · pTuneos · IMPROVE · NeoTImmuML", options:{ color:C.dark, fontSize:12, bold:true } },
], { x:6.92, y:6.12, w:5.5, h:0.8, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
pageno(s,2);

// ============================================================ S3 5工具总览(诚实分级)
s = pres.addSlide();
header(s, "总览", "5 工具部署状态 · 端到端完整度诚实分级");
const hd = (t)=>({ text:t, options:{ fill:{color:C.dark}, color:"FFFFFF", bold:true, fontSize:12.5, align:"center", valign:"middle" } });
const cc = (t,col)=>({ text:t, options:{ color:col||C.ink, fontSize:11.5, align:"center", valign:"middle" } });
const cl = (t)=>({ text:t, options:{ color:C.ink, fontSize:12, bold:true, align:"left", valign:"middle" } });
const rows = [
  [hd("工具"), hd("方法"), hd("能否定量"), hd("本地"), hd("HPC"), hd("端到端完整度 (诚实分级)")],
  [cl("DeepImmuno"), cc("CNN"), cc("✅ 连续0-1",C.ok), cc("✅",C.ok), cc("✅",C.ok), cc("✅ 完整端到端 (本地+HPC 双验证)",C.ok)],
  [cl("PredIG"), cc("XGBoost"), cc("✅ 连续0-1",C.ok), cc("✅",C.ok), cc("✅",C.ok), cc("✅ 完整端到端 (本地+HPC 双验证)",C.ok)],
  [cl("pTuneos"), cc("ML pipeline"), cc("✅ 排名分",C.ok), cc("✅",C.ok), cc("🟡",C.warn), cc("⚠️ 子模型 (Pre&RecNeo 跑肽段, r=1.0)",C.warn)],
  [cl("IMPROVE"), cc("RandomForest"), cc("✅ 连续0-1",C.ok), cc("🟡",C.warn), cc("🟡",C.warn), cc("⚠️ 降级 (特征链缺 RNA-seq/stabpan)",C.warn)],
  [cl("NeoTImmuML ★"), cc("集成 ML"), cc("✅ 概率",C.ok), cc("🟡",C.warn), cc("🟡",C.warn), cc("⚠️ 自训版 (无官方权重, 不对标原论文)",C.warn)],
];
s.addTable(rows, { x:0.7, y:1.85, w:11.9, colW:[2.05,1.7,1.55,0.85,0.85,4.9], rowH:[0.5,0.6,0.6,0.6,0.6,0.6],
  border:{pt:1,color:C.line}, align:"center", valign:"middle", fontFace:FB, fill:{color:C.card} });
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:5.55, w:11.9, h:0.78, fill:{color:"E6F4F1"}, line:{color:C.sea,width:1} });
s.addText([
  { text:"诚实分级结论：", options:{ bold:true, color:C.teal, fontSize:12.5 } },
  { text:"5 工具均部署 + 均产出可进 ELISpot benchmark 的连续/概率分数；但端到端完整度分三档，不可一概而论 —— ", options:{ color:C.ink, fontSize:11.5 } },
  { text:"DeepImmuno/PredIG 完整双验证，pTuneos 子模型，IMPROVE 降级，NeoTImmuML 自训版。", options:{ bold:true, color:C.dark, fontSize:11.5 } },
], { x:0.95, y:5.6, w:11.4, h:0.68, fontFace:FB, valign:"middle", lineSpacingMultiple:1.02, margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:6.4, w:11.9, h:0.62, fill:{color:"FBEEE4"}, line:{color:C.warn,width:1} });
s.addText([
  { text:"★ NeoTImmuML = 自训版：", options:{ bold:true, color:C.warn, fontSize:10.5 } },
  { text:"官方 repo 无预训练权重，benchmark 用我们用公开数据自训的模型，非官方权重，数值不对标原论文精度。「⚠️ 部分」= 工具自身限制非部署失败。", options:{ color:C.ink, fontSize:10.5 } },
], { x:0.95, y:6.44, w:11.4, h:0.55, fontFace:FB, valign:"middle", lineSpacingMultiple:1.0, margin:0 });
pageno(s,3);

// ============================================================ S4-S8 逐工具
toolSlide({ idx:1, name:"DeepImmuno", accent:"028090", method:"CNN", status:"✅ 完整端到端", statusCol:C.ok,
  tagline:"深度学习 (CNN) 预测肽段对 CD8+ T 细胞的免疫原性 (HLA-I)，附 GAN 生成功能",
  input:[ "CSV，无表头两列  peptide,HLA", "肽段长度死限 9 / 10-mer", "HLA 格式  HLA-A*0201", "无需基因组 / HLA 库" ],
  params:[ "--mode single  单条 (结果打 stdout)", "--mode multiple --intdir --outdir  批量", "无可调超参；须在 repo 根目录运行" ],
  output:[ "tab 分隔  peptide / HLA / immunogenicity", "immunogenicity = 连续 0-1 (越高越强)", "实测 NLVPMVATV(CMV)=0.957、GILGFVFTL(流感)=0.887 → 已知强表位高分，合理" ],
  intro:[ "最轻量，纯肽段+HLA 即可，无许可工具依赖，CPU 可跑", "部署：Python3.8 + TF2.3 + protobuf3.20 (坑：不降报 Descriptors 错)", "局限：肽长死限 9/10-mer" ],
});
toolSlide({ idx:2, name:"PredIG", accent:"1C7293", method:"XGBoost", status:"✅ 完整端到端", statusCol:C.ok,
  tagline:"XGBoost 预测 T 细胞表位免疫原性，三类抗原专用模型，可解释",
  input:[ "3 模式：CSV-Uniprot / CSV-Recombinant / FASTA", "Recombinant 列  epitope,HLA_allele,protein_seq,protein_name", "肽段 8-14 AA" ],
  params:[ "--modelXG {neoant | noncan | path}", "--type {uniprot | recombinant | fasta}", "-o 输出文件" ],
  output:[ "CSV，PredIG 列 = 连续 0-1 免疫原性分", "+ NOAH / NetCleave / 物化 / TCR_contact 等 13 列特征", "实测 SLLMWITQV = 0.0061" ],
  intro:[ "连续分 + 可解释特征 + 容器化 (依赖全打包)", "部署：官方 Docker 镜像 (14.4G) → HPC 转 Singularity (predig.sif 4.6G)", "局限：镜像大" ],
});
toolSlide({ idx:3, name:"pTuneos", accent:"028090", method:"ML pipeline", status:"⚠️ 子模型端到端", statusCol:C.warn,
  tagline:"个性化新抗原全流程 pipeline (WES/RNA-seq 或 VCF → 排名)；识别子模型可单独跑肽段",
  input:[ "完整 pipeline：VCF + 表达谱 + 拷贝数 + 纯度 + HLA (需全基因组，吃不了纯肽)", "⭐ Pre&RecNeo 子模型：仅 MT_pep + WT_pep + HLA 三列 (可跑 ELISpot 肽)" ],
  params:[ "完整：python pTuneos.py {WES|VCF} -i config.yaml", "Pre&RecNeo：自写 wrapper 调 InVivoModelAndScore", "批 netMHCpan/blastp 加速 + nproc 并行" ],
  output:[ "RefinedNeo = 患者级排名分 (乘表达/VAF/克隆性，需测序)", "Pre&RecNeo (model_pro) = 纯肽免疫原性识别分 → 与其他 4 工具可比", "example VCF 出 40 新抗原" ],
  intro:[ "镜像自带 netMHCpan-4.0 / VEP / GATK / BWA 全套；修 8 坑 + VEP cache 14G 端到端跑通", "Pre&RecNeo 跑 ELISpot 32178 肽对 → 进 benchmark (对账官方 r=1.0)", "⚠️ 诚实：本地 docker 跑 (HPC sif 受限)；r=1.0 只证复刻逻辑对，非整管线 ELISpot 能力背书" ],
});
toolSlide({ idx:4, name:"IMPROVE", accent:"1C7293", method:"RandomForest", status:"⚠️ 降级版", statusCol:C.warn,
  tagline:"随机森林预测新表位免疫原性，22 特征，三变体 (Simple / TME_excluded / TME_included)",
  input:[ "TSV，必填  突变肽 + 野生型肽 + HLA", "肽段 8-12 AA", "两步流程：① feature_calc 算特征  ② Predict 跑 RF" ],
  params:[ "步2  --model {Simple | TME_excluded | TME_included}", "每变体加载 5 个 RF (rf0-rf4 集成)" ],
  output:[ "TSV 追加  mean_prediction_rf (连续 0-1)", "= 5fold × 50 RF 集成平均", "实测 Simple 变体 EEFLNSWML = 0.5146" ],
  intro:[ "RF 22 特征，专为新表位排名设计，整合 TCR 识别 (PRIME)", "⚠️ 缺口：ELISpot 无 RNA-seq → Expression 特征降级；netMHCstabpan 受 glibc 挡", "Predict 步本地+HPC 跑通；非「装不上」，是结构性数据缺口" ],
});
toolSlide({ idx:5, name:"NeoTImmuML ★自训版", accent:"028090", method:"集成 ML", status:"⚠️ 自训版", statusCol:C.warn,
  tagline:"加权集成 (LightGBM+XGBoost+RandomForest) 预测肿瘤新抗原免疫原性，78 个肽段物化特征",
  input:[ "CSV：Peptide + immunogenicity(标签) + 78 个 R Peptides 物化特征", "肽段 8-13 AA，不要 HLA", "78 特征须先用 R Peptides 包外部算好" ],
  params:[ "不是 CLI，是 Jupyter notebook (21 cell)", "改 file_path 指数据；内含 8 算法对比+加权集成+5fold CV" ],
  output:[ "分类指标 + 雷达图 + predict_proba 连续概率 → 能定量强弱", "★ 官方无预训练权重 → benchmark 用我们自训版", "数值不对标原论文精度" ],
  intro:[ "纯肽特征，不要 HLA / 不要 netMHCpan 等许可工具 (部署最轻)", "局限：研究 notebook 无权重 → 用 TumorAgDB2.0 重训", "不含 78 特征计算代码 → 须 R Peptides 算" ],
});

// ============================================================ S9 部署工程 + 踩坑
s = pres.addSlide();
header(s, "工程", "部署环境与关键技术问题 (踩坑)");
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:1.8, w:4.6, h:4.85, fill:{color:C.dark}, shadow:sh() });
s.addText("部署环境", { x:0.95, y:2.05, w:4, h:0.4, fontFace:FH, fontSize:17, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"本机 WSL2 Ubuntu 24.04", options:{ bold:true, color:"FFFFFF", fontSize:13.5, breakLine:true } },
  { text:"调试主战场 · GPU 直通 RTX4070 · conda + Docker", options:{ color:"9FD9CF", fontSize:11.5, breakLine:true, paraSpaceAfter:10 } },
  { text:"XJTLU HPC", options:{ bold:true, color:"FFFFFF", fontSize:13.5, breakLine:true } },
  { text:"dtn.hpc.xjtlu.edu.cn · 最终部署目标", options:{ color:"9FD9CF", fontSize:11.5, breakLine:true } },
  { text:"Singularity 3.11.3 + module miniconda3", options:{ color:"9FD9CF", fontSize:11.5, breakLine:true, paraSpaceAfter:10 } },
  { text:"出网", options:{ bold:true, color:"FFFFFF", fontSize:13.5, breakLine:true } },
  { text:"github / pypi / DTU ✅   Docker Hub ❌", options:{ color:"9FD9CF", fontSize:11.5 } },
], { x:0.95, y:2.5, w:4.15, h:4.0, fontFace:FB, valign:"top", margin:0 });
s.addText("关键技术问题与解决 (踩坑)", { x:5.6, y:1.9, w:7, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.ink, margin:0 });
const pit = [
  ["Windows 跑不动","repo 含非法 * 文件名 → NTFS checkout 崩 → 全转 WSL2/HPC Linux"],
  ["版本地狱","老 TF/numpy/protobuf → 严格按官方 pin 建独立 conda env"],
  ["Docker Hub 国内不通","WSL mirrored + daemon 代理拉镜像；HPC 转 Singularity"],
  ["2014 老二进制 segfault","WSL 内核 vsyscall → .wslconfig 加 vsyscall=emulate"],
  ["HPC glibc 2.28 < 2.29","netMHCstabpan 原生跑不了 → 需新 glibc 容器"],
  ["git-lfs 大文件","models 1.9G：--depth 1 只得指针 → git lfs pull"],
];
pit.forEach((p,i)=>{
  const col = (i%2===0)? 5.6 : 9.2;
  const yrow = 2.4 + Math.floor(i/2)*1.42;
  s.addShape(pres.shapes.RECTANGLE, { x:col, y:yrow, w:3.4, h:1.28, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:col, y:yrow, w:3.4, h:0.06, fill:{color:C.sea} });
  s.addText(p[0], { x:col+0.18, y:yrow+0.15, w:3.05, h:0.35, fontFace:FH, fontSize:12.5, bold:true, color:C.teal, margin:0 });
  s.addText(p[1], { x:col+0.18, y:yrow+0.52, w:3.08, h:0.68, fontFace:FB, fontSize:10.5, color:C.ink, valign:"top", margin:0 });
});
pageno(s,9);

// ============================================================ S10 benchmark 方法/数据
s = pres.addSlide();
header(s, "Benchmark 方法", "ELISpot 真实数据 · 评估口径");
const mcards = [
  ["测试集 DS2","101 条肽段，34247 行 (子肽×HLA)。标签按 ELISpot SFC>0 切：90 阳 / 11 阴 (1 个 ==0 + 10 个 <0 背景扣减 = 真无反应，阴性定义干净 ≤0)。","028090"],
  ["参评工具","8 个：第一批 5 (DeepImmuno/PredIG/IMPROVE/NeoTImmuML★/pTuneos) + 第二批 3 (PRIME/ImmuneApp/deepHLApan)。","00A896"],
  ["聚合 × 阈值","每肽多子肽×HLA → 聚合 max / mean / top3mean；阈值 >0 / >10 / >median=22.67。主对比口径 = max, >0 (apples-to-apples)。","1C7293"],
  ["指标","AUC-ROC (判别力)、AUPRC、Spearman ρ (连续 SFC 相关 = 定量强弱)。AUC 不显著性用 2000 次 bootstrap 95% CI 量化。","028090"],
];
let my=1.85;
mcards.forEach(m=>{
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:my, w:11.9, h:1.18, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:my, w:0.09, h:1.18, fill:{color:m[2]} });
  s.addText(m[0], { x:1.0, y:my+0.16, w:2.6, h:0.85, fontFace:FH, fontSize:15, bold:true, color:m[2], valign:"top", margin:0 });
  s.addText(m[1], { x:3.6, y:my+0.14, w:8.8, h:0.9, fontFace:FB, fontSize:12, color:C.ink, valign:"middle", lineSpacingMultiple:1.05, margin:0 });
  my += 1.28;
});
s.addText("旧 5 工具复现验证：max|AUC diff| ≤ 0.004 (浮点精度内)，口径对齐 PASS。所有数字经 csv 三方核对 (0 drift)。", { x:0.7, y:6.95, w:11.9, h:0.4, fontFace:FB, fontSize:10.5, italic:true, color:C.muted, margin:0 });
pageno(s,10);

// ============================================================ S11 ⭐ 8工具 benchmark 保守结论 (主图 fig6)
s = pres.addSlide();
header(s, "核心结论", "8 工具在 ELISpot 上判别力普遍弱、统计不可区分、新工具无增量", C.crit);
const ih1=4.45, iw1=ih1*(1600/1000);
s.addShape(pres.shapes.RECTANGLE, { x:0.6, y:1.65, w:7.0, h:5.2, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIG+"/fig6_8tools_auc_comparison.png", x:0.7, y:1.78, w:6.8, h:4.6, sizing:{type:"contain", w:6.8, h:4.6} });
s.addText("图：8 工具 AUC-ROC (DS2, max 聚合, >0) + 95% bootstrap CI 误差棒；橙 = 第二批新工具。除 pTuneos 外 CI 下界均跌破随机线 0.5。", { x:0.65, y:6.42, w:6.9, h:0.5, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", margin:0 });
// 右: 三条保守要点
const pts = [
  ["判别力普遍弱","AUC 点估居前 = pTuneos 0.7525，但 95% CI=[0.598, 0.888] 宽达 ±0.15；除 pTuneos 外所有工具 CI 下界均 < 0.5 (随机线)。",C.crit],
  ["统计不可区分","配对 bootstrap：pTuneos vs PredIG ΔAUC=0.091 CI=[−0.145,+0.310]、vs NeoTImmuML ΔAUC=0.098 CI=[−0.140,+0.327]，均跨 0 → 头部工具间分不出显著高下 (根因 = 阴性仅 11 个)。",C.warn],
  ["新工具无增量 (稳健)","第二批 3 工具在全部聚合×阈值下，无一超过第一批最优点估；ImmuneApp 0.589 / PRIME 0.528 / deepHLApan 0.419 (低于随机)。该结论不依赖排名精度。",C.teal],
];
let py2=1.78;
pts.forEach(p=>{
  s.addShape(pres.shapes.RECTANGLE, { x:7.8, y:py2, w:4.95, h:1.62, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:7.8, y:py2, w:0.09, h:1.62, fill:{color:p[2]} });
  s.addText(p[0], { x:8.0, y:py2+0.12, w:4.7, h:0.34, fontFace:FH, fontSize:14, bold:true, color:p[2], margin:0 });
  s.addText(p[1], { x:8.0, y:py2+0.5, w:4.6, h:1.05, fontFace:FB, fontSize:10.5, color:C.ink, valign:"top", lineSpacingMultiple:1.04, margin:0 });
  py2 += 1.72;
});
s.addText("措辞红线：用「点估居前」不用「最优/最强/无可替代」—— 这些一致的数字在 n_neg=11 下不支撑「最优」判语。", { x:7.8, y:6.95, w:4.95, h:0.4, fontFace:FB, fontSize:9, italic:true, color:C.crit, valign:"top", margin:0 });
pageno(s,11);

// ============================================================ S12 统计稳健性 (caterpillar)
s = pres.addSlide();
header(s, "统计稳健性", "为什么不能下「最优」结论 —— CI 重叠 + 小样本");
const ih2=4.7, iw2=ih2*(1600/1000);
s.addShape(pres.shapes.RECTANGLE, { x:0.6, y:1.65, w:7.4, h:5.25, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIGD+"/fig_bootstrap_ci.png", x:0.72, y:1.8, w:7.15, h:4.7, sizing:{type:"contain", w:7.15, h:4.7} });
s.addText("图：8 工具 AUC 点估 + 95% bootstrap CI (caterpillar)。所有 CI 跨越或贴近 0.5 且彼此大幅重叠。", { x:0.65, y:6.55, w:7.3, h:0.4, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:8.2, y:1.78, w:4.55, h:2.5, fill:{color:C.dark}, shadow:sh() });
s.addText("根因：阴性样本仅 11 个", { x:8.42, y:1.95, w:4.2, h:0.4, fontFace:FH, fontSize:14, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"少数类 (阴性) 主导 AUC 的不确定性。11 个阴性 → 每个 bootstrap 重抽差异巨大 → CI 宽达 ±0.15。", options:{ breakLine:true, color:"FFFFFF", fontSize:11.5, paraSpaceAfter:8 } },
  { text:"工具间排名差异 (< 0.05 AUC) 完全淹没在 CI 宽度里。", options:{ color:"CADCFC", fontSize:11.5 } },
], { x:8.42, y:2.4, w:4.15, h:1.75, fontFace:FB, valign:"top", lineSpacingMultiple:1.08, margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:8.2, y:4.45, w:4.55, h:2.45, fill:{color:"FBEEE4"}, line:{color:C.warn,width:1} });
s.addText("「最优」是脆弱角落", { x:8.42, y:4.6, w:4.2, h:0.4, fontFace:FH, fontSize:14, bold:true, color:C.warn, margin:0 });
s.addText([
  { text:"pTuneos 0.78 是「单聚合 × 单阈值 × 11 阴性」三重最优点。", options:{ breakLine:true, color:C.ink, fontSize:11, paraSpaceAfter:6 } },
  { text:"同一工具换 >median 阈值 AUC 掉到 ≈0.46 (低于随机) → 非稳健能力。", options:{ breakLine:true, color:C.ink, fontSize:11, paraSpaceAfter:6 } },
  { text:"pTuneos 仅显著超弱工具 (IMPROVE/PRIME/deepHLApan)，对最近竞品 PredIG/NeoTImmuML 不显著。", options:{ color:C.ink, fontSize:11 } },
], { x:8.42, y:5.02, w:4.15, h:1.8, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
pageno(s,12);

// ============================================================ S13 定量能力弱 + DS1 证伪
s = pres.addSlide();
header(s, "定量能力", "现有工具是分类器不是回归器 —— 全阳数据集上排不出强弱");
const ih3=4.5, iw3=ih3*(1600/1000);
s.addShape(pres.shapes.RECTANGLE, { x:0.6, y:1.65, w:6.6, h:5.2, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIG+"/fig7_8tools_spearman.png", x:0.72, y:1.8, w:6.35, h:4.5, sizing:{type:"contain", w:6.35, h:4.5} });
s.addText("图：8 工具 Spearman ρ (分数 vs ELISpot SFU, max 聚合)。* = p<0.05。仅 IMPROVE / PredIG 显著正相关。", { x:0.65, y:6.4, w:6.5, h:0.45, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", margin:0 });
// 右: DS1 证伪
s.addShape(pres.shapes.RECTANGLE, { x:7.4, y:1.75, w:5.35, h:2.55, fill:{color:C.dark}, shadow:sh() });
s.addText("DS1 全阳数据集证伪「能定量」", { x:7.62, y:1.92, w:5.0, h:0.4, fontFace:FH, fontSize:14, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"DS1 = 82 肽 9mer，全阳 (SFC 16–677，中位 131，无阴性 → 算不了 AUC)，幅度跨 ~40 倍。", options:{ breakLine:true, color:"FFFFFF", fontSize:11, paraSpaceAfter:6 } },
  { text:"8/9 工具对 DS1 SFC 的 |ρ|<0.16、p 全不显著 (≈随机)：PredIG 0.028 / IMPROVE 0.007 / pTuneos −0.022 / ImmuneApp 0.039。唯一显著的 deepHLApan ρ=−0.50 是反向 (非能力)。", options:{ color:"CADCFC", fontSize:10.5 } },
], { x:7.62, y:2.36, w:4.95, h:1.9, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:7.4, y:4.45, w:5.35, h:2.4, fill:{color:"E6F4F1"}, line:{color:C.sea,width:1} });
s.addText("机制 + 对袁课题的正面意义", { x:7.62, y:4.58, w:5.0, h:0.36, fontFace:FH, fontSize:13, bold:true, color:C.teal, margin:0 });
s.addText([
  { text:"干净对照：同批工具 DS2 上头部能正向显著排 SFC (IMPROVE top3mean ρ=0.32 p=0.001、PredIG mean ρ=0.28 p=0.005)，到 DS1 全阳就全塌成随机。", options:{ breakLine:true, color:C.ink, fontSize:10.5, paraSpaceAfter:6 } },
  { text:"判别力主要落在「阳 vs 阴」门槛；全阳后门槛信息用尽 → 预测连续 magnitude ≈ 0。这正坐实 QuantImmune 做连续回归的空白。", options:{ color:C.dark, fontSize:10.5, bold:true } },
], { x:7.62, y:4.96, w:4.95, h:1.85, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
pageno(s,13);

// ============================================================ S14 诚实 caveat + 许可红线
s = pres.addSlide();
header(s, "诚实边界", "已知限制与红线 (先说清，免被打回)", C.warn);
const cav = [
  ["样本量极小","DS2 仅 11 个阴性 → 所有 AUC/ρ 的 95% CI 都很宽，工具间排名差异 (<0.05 AUC) 不显著。这是「无稳健最优」结论的直接来源。",C.crit],
  ["患者层聚集","101 肽来自 9 个病人，前 2 个病人贡献约 45% 的阴性肽 → 有效自由度 < 101 (伪重复)，AUC 可能部分在测「区分患者」。需按 Patient_ID 分层复核。",C.warn],
  ["IEDB overlap 待测","第二批工具 (PRIME/ImmuneApp/deepHLApan) 多用 IEDB 训练，与本 ELISpot 集可能重叠；当前无排重代码，「独立性待查」。泄漏方向让分数虚高 → 对「新工具无增量」主结论顺风。",C.warn],
  ["工具完整度分级","DeepImmuno/PredIG 完整端到端；pTuneos 子模型 (r=1.0 只证复刻逻辑对)；IMPROVE 特征链降级；NeoTImmuML★自训版 (非官方权重)。",C.teal],
];
let cy2=1.78;
cav.forEach(c=>{
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:cy2, w:7.9, h:1.18, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:cy2, w:0.09, h:1.18, fill:{color:c[2]} });
  s.addText(c[0], { x:0.98, y:cy2+0.14, w:2.0, h:0.9, fontFace:FH, fontSize:13, bold:true, color:c[2], valign:"top", margin:0 });
  s.addText(c[1], { x:2.95, y:cy2+0.12, w:5.5, h:0.95, fontFace:FB, fontSize:10.5, color:C.ink, valign:"middle", lineSpacingMultiple:1.04, margin:0 });
  cy2 += 1.28;
});
// 右: 许可红线
s.addShape(pres.shapes.RECTANGLE, { x:8.8, y:1.78, w:3.95, h:5.05, fill:{color:"4A1F24"}, shadow:sh() });
s.addText("⚠️ 许可红线", { x:9.05, y:2.0, w:3.5, h:0.4, fontFace:FH, fontSize:16, bold:true, color:"F2C2C7", margin:0 });
s.addText([
  { text:"netMHCpan / netMHCstabpan", options:{ bold:true, color:"FFFFFF", fontSize:12.5, breakLine:true } },
  { text:"= DTU 学术许可。第 7(v)/10 条：未经 DTU 书面同意，不得向第三方发布在其软件上跑的 benchmark 结果 (含跑出的数字)。", options:{ color:"F2C2C7", fontSize:11, breakLine:true, paraSpaceAfter:12 } },
  { text:"本项目是 benchmark", options:{ bold:true, color:"FFFFFF", fontSize:12.5, breakLine:true } },
  { text:"→ 论文 / 对外报告含 netMHCpan 对比数字前，须先取 DTU 书面同意 (投稿阶段处理)。", options:{ color:"F2C2C7", fontSize:11, breakLine:true, paraSpaceAfter:12 } },
  { text:"deepHLApan = GPL-2.0", options:{ bold:true, color:"FFFFFF", fontSize:12.5, breakLine:true } },
  { text:"公开发布前需合规审。", options:{ color:"F2C2C7", fontSize:11 } },
], { x:9.05, y:2.5, w:3.55, h:4.2, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
pageno(s,14);

// ============================================================ S15 QuantImmune 立项支撑
s = pres.addSlide();
s.background = { color: C.dark };
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.mint} });
s.addText("QUANTIMMUNE 立项支撑", { x:0.9, y:0.55, w:11, h:0.3, fontFace:FB, fontSize:12, bold:true, color:C.mint, charSpacing:3, margin:0 });
s.addText("机会与边界：做对反应强弱的连续回归，但先验证命门", { x:0.9, y:0.85, w:11.5, h:0.6, fontFace:FH, fontSize:25, bold:true, color:"FFFFFF", margin:0 });
const q = [
  ["🌊 蓝海 (方向不撞车)","对 ELISpot SFC 做连续 magnitude 回归是学界公认空白。2024 综述 (Expl Immunol, DOI 10.37349/ei.2023.00091)：「Magnitude prediction remains an unaddressed gap」。逐一核验自称「定量」的工具 (PRIME=ranking、ICERFIRE 把量级塌成二分、neoIM/T-SCAPE 仍分类) → 真做连续回归的 = 0 个。",C.mint],
  ["🔑 命门 (立项前零成本必做)","想做回归却可能没有足够连续标签。公开数据集绝大多数二元 (PRIME/NEPdb/dbPepNeo2 全 binary)；唯一系统带 magnitude 字段 = IEDB / CEDAR。动手前必先核 IEDB/CEDAR 的 magnitude 字段实际填充率 —— 若稀疏，「想做回归但无连续标签」直接塌缩立项。零算力，数日可做。",C.warn],
  ["📈 理论天花板 (避免过度承诺)","纯「肽+HLA」对 magnitude 的可解释方差被生物学封顶 —— 头号因子 naïve precursor frequency (Jenkins & Moon 2012) 由宿主 TCR 库决定，无法从肽+HLA 推出；叠加 ELISpot 噪声 (CV~40%) → ρ 天花板粗估 0.4–0.6 (低置信，待校准)。IMPROVE ρ≈0.32 已达约 2/3。勿承诺 ρ→0.8。",C.sea],
  ["🎯 headline 押 C3 (临床 top-K 排序)","连续模型在 held-out 病人上的 top-K 推荐质量优于二分类 —— 临床只能合成 top-K 肽，排序质量直接等于临床价值。不赌破天花板，最现实、最可证伪。C1 (坐实纯序列天花板) 当诚实能力刻画；C2 (喂供体 TCR-seq 破天花板) 标探索性 stretch goal。",C.teal],
];
let qx=0.9, qy=1.75, qw=5.7, qh=2.45, qgap=0.35;
q.forEach((it,i)=>{
  const x = i%2===0 ? qx : qx+qw+qgap;
  const y = i<2 ? qy : qy+qh+qgap;
  s.addShape(pres.shapes.RECTANGLE, { x, y, w:qw, h:qh, fill:{color:"123F4B"}, line:{color:"1C5563",width:1} });
  s.addShape(pres.shapes.RECTANGLE, { x, y, w:0.09, h:qh, fill:{color:it[2]} });
  s.addText(it[0], { x:x+0.25, y:y+0.16, w:qw-0.4, h:0.4, fontFace:FH, fontSize:15, bold:true, color:it[2], margin:0 });
  s.addText(it[1], { x:x+0.27, y:y+0.62, w:qw-0.5, h:qh-0.75, fontFace:FB, fontSize:10.5, color:"E8F1F1", valign:"top", lineSpacingMultiple:1.06, margin:0 });
});
pageno(s,15);

// ============================================================ S16 结论 + 下一步
s = pres.addSlide();
s.background = { color: C.dark };
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.mint} });
s.addText("结论与下一步", { x:0.9, y:0.7, w:10, h:0.7, fontFace:FH, fontSize:32, bold:true, color:"FFFFFF", margin:0 });
s.addText("已达成 (余嘉子任务核心)", { x:0.9, y:1.85, w:5.5, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"5 工具全部部署 + 4 类信息全收集 (逐工具文档齐)", options:{ bullet:{indent:14}, breakLine:true, color:"FFFFFF", fontSize:13, paraSpaceAfter:7 } },
  { text:"2 个完整端到端双验证 (DeepImmuno/PredIG)；其余诚实分级", options:{ bullet:{indent:14}, breakLine:true, color:"FFFFFF", fontSize:13, paraSpaceAfter:7 } },
  { text:"8 工具 ELISpot benchmark：保守结论 = 判别力普遍弱、统计不可区分、新工具无增量、定量能力弱", options:{ bullet:{indent:14}, breakLine:true, color:"FFFFFF", fontSize:13, paraSpaceAfter:7 } },
  { text:"该负结果反而强化 QuantImmune 做连续 magnitude 回归的立项动机", options:{ bullet:{indent:14}, color:C.mint, fontSize:13, bold:true } },
], { x:0.9, y:2.35, w:5.8, h:4.3, fontFace:FB, valign:"top", margin:0 });
s.addText("下一步", { x:7.0, y:1.85, w:5.5, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.warn, margin:0 });
const ns=[
  ["立项命门 (优先, 零算力)","核 IEDB/CEDAR magnitude 字段填充率 —— 整个方向的开关"],
  ["扩负样本","DS2 仅 11 阴性 → 要袁老师补真实 ELISpot 阴性肽至 ≥30 再重测"],
  ["IEDB overlap 实测","32178 肽 vs IEDB 精确+9mer match 报 overlap%"],
  ["袁老师正式数据","到位后按各工具格式做转换 → 正式测试"],
  ["对外许可","投稿前取 DTU 书面同意 (netMHCpan 数字)"],
];
let ny=2.35;
ns.forEach(g=>{
  s.addShape(pres.shapes.RECTANGLE, { x:7.0, y:ny, w:5.5, h:0.82, fill:{color:"123F4B"}, line:{color:"1C5563",width:1} });
  s.addShape(pres.shapes.RECTANGLE, { x:7.0, y:ny, w:0.08, h:0.82, fill:{color:C.warn} });
  s.addText(g[0], { x:7.25, y:ny+0.1, w:5.1, h:0.32, fontFace:FH, fontSize:12.5, bold:true, color:"FFFFFF", margin:0 });
  s.addText(g[1], { x:7.25, y:ny+0.42, w:5.1, h:0.36, fontFace:FB, fontSize:10, color:"9FD9CF", valign:"top", margin:0 });
  ny += 0.92;
});
s.addText("数据真源：本地 ~/quantimmu/ + HPC /gpfs/.../quantimmu/ · 数字经 csv 三方核对 0 drift · 逐工具 4 类信息见 TOOLS/*.md", { x:0.9, y:7.0, w:11.5, h:0.4, fontFace:FB, fontSize:9.5, italic:true, color:"6E9AA1", margin:0 });

// ---------- write ----------
pres.writeFile({ fileName: "D:/YJ-Agent/project/meeting/QuantImmuBench/QuantImmuBench_最终交付_2026-06-24.pptx" })
  .then(f=>console.log("WROTE", f))
  .catch(e=>{ console.error("ERR", e); process.exit(1); });
