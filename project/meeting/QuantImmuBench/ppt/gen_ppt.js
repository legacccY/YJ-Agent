const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";          // 13.33 x 7.5 in
pres.author = "余嘉 (legacccy)";
pres.title = "新抗原免疫原性预测工具部署测试报告";

const W = 13.33, H = 7.5;

// ---------- 配色 (Teal Trust 生物医学) ----------
const C = {
  dark:   "0B3C49",   // 深青墨 (标题/结论底)
  teal:   "028090",   // 主青
  sea:    "00A896",   // 海绿
  mint:   "02C39A",   // 薄荷 accent
  light:  "F2F7F7",   // 浅底
  card:   "FFFFFF",
  ink:    "16323A",   // 正文深
  muted:  "5E7B83",   // 次要灰青
  line:   "D5E3E4",
  warn:   "C9743D",   // 警示橙(部分完成)
  ok:     "00A896",
};
const FH = "Microsoft YaHei";   // 标题/正文都用雅黑(中文安全)
const FB = "Microsoft YaHei";
const FIG = "D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/figures";

const sh = () => ({ type:"outer", color:"0B3C49", blur:9, offset:3, angle:135, opacity:0.12 });

// ---------- 通用页眉 (浅色内容页) ----------
function header(slide, kicker, title, accent=C.teal){
  slide.background = { color: C.light };
  slide.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:0.28, h:H, fill:{color:accent} });
  slide.addText(kicker.toUpperCase(), { x:0.7, y:0.42, w:11, h:0.3, fontFace:FB, fontSize:12, color:accent, bold:true, charSpacing:3, margin:0 });
  slide.addText(title, { x:0.7, y:0.72, w:12, h:0.7, fontFace:FH, fontSize:30, color:C.ink, bold:true, margin:0 });
}
function pageno(slide, n){
  slide.addText(String(n), { x:W-0.8, y:H-0.5, w:0.5, h:0.3, fontFace:FB, fontSize:11, color:C.muted, align:"right", margin:0 });
}

// 工具信息卡 (4象限)
function infoCard(slide, x, y, w, h, icon, head, lines, accent){
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill:{color:C.card}, line:{color:C.line, width:1}, shadow:sh() });
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w:0.09, h, fill:{color:accent} });
  slide.addText(head, { x:x+0.28, y:y+0.16, w:w-0.4, h:0.34, fontFace:FH, fontSize:15, bold:true, color:accent, margin:0 });
  const rt = lines.map((t,i)=>({ text:t, options:{ bullet:{indent:12}, breakLine:true, color:C.ink, fontSize:11.5, paraSpaceAfter:5 } }));
  slide.addText(rt, { x:x+0.3, y:y+0.58, w:w-0.55, h:h-0.7, fontFace:FB, valign:"top", margin:0 });
}

// 状态徽章
function badge(slide, x, y, txt, col){
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w:1.85, h:0.42, rectRadius:0.21, fill:{color:col} });
  slide.addText(txt, { x, y, w:1.85, h:0.42, fontFace:FB, fontSize:12, bold:true, color:"FFFFFF", align:"center", valign:"middle", margin:0 });
}

// 工具页统一模板
function toolSlide(o){
  const s = pres.addSlide();
  header(s, "工具 "+o.idx+" / 5", o.name, o.accent);
  // 副标题 + 方法标签 + 状态徽章
  s.addText(o.tagline, { x:0.7, y:1.5, w:8.6, h:0.5, fontFace:FB, fontSize:13, color:C.muted, margin:0 });
  badge(s, W-2.55, 0.72, o.status, o.statusCol);
  s.addText("方法: "+o.method, { x:W-2.55, y:1.22, w:1.85, h:0.3, fontFace:FB, fontSize:11, color:C.teal, bold:true, align:"center", margin:0 });
  // 2x2 信息卡
  const cx=0.7, cy=2.12, cw=6.0, ch=2.45, gap=0.32;
  infoCard(s, cx,        cy,        cw, ch, "1", "① 输入数据 / 格式", o.input,  o.accent);
  infoCard(s, cx+cw+gap, cy,        cw, ch, "2", "② 运行参数", o.params, o.accent);
  infoCard(s, cx,        cy+ch+gap, cw, ch, "3", "③ 输出格式 / 含义", o.output, o.accent);
  infoCard(s, cx+cw+gap, cy+ch+gap, cw, ch, "4", "④ 简介 / 特点优势", o.intro,  o.accent);
  pageno(s, o.idx+3);
  return s;
}

// ============================================================
// Slide 1 — 封面
// ============================================================
let s = pres.addSlide();
s.background = { color: C.dark };
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.mint} });
s.addShape(pres.shapes.OVAL, { x:W-3.3, y:-1.6, w:4.6, h:4.6, fill:{color:C.teal, transparency:78} });
s.addShape(pres.shapes.OVAL, { x:W-2.0, y:3.6,  w:3.2, h:3.2, fill:{color:C.sea,  transparency:82} });
s.addText("癌症个性化新抗原疫苗 · 工具 Benchmark", { x:0.9, y:1.7, w:10, h:0.4, fontFace:FB, fontSize:15, color:C.mint, bold:true, charSpacing:2, margin:0 });
s.addText("新抗原免疫原性预测工具\n部署测试报告", { x:0.9, y:2.25, w:11, h:1.8, fontFace:FH, fontSize:46, bold:true, color:"FFFFFF", lineSpacingMultiple:1.05, margin:0 });
s.addText("5 个预测工具 · 部署 / 运行 / 4 类信息收集 · ELISpot 真实数据验证", { x:0.9, y:4.35, w:11, h:0.5, fontFace:FB, fontSize:16, color:"CADCFC", margin:0 });
s.addShape(pres.shapes.LINE, { x:0.95, y:5.25, w:3.2, h:0, line:{color:C.mint, width:2} });
s.addText([
  { text:"汇报人  ", options:{ color:"8FB7BD", fontSize:13 } },
  { text:"余嘉 (legacccy)", options:{ color:"FFFFFF", fontSize:13, bold:true, breakLine:true } },
  { text:"协作项目  ", options:{ color:"8FB7BD", fontSize:13 } },
  { text:"袁老师课题组 · 西交利物浦大学", options:{ color:"FFFFFF", fontSize:13 } },
], { x:0.95, y:5.5, w:9, h:1.0, fontFace:FB, valign:"top", margin:0 });
s.addText("2026-06", { x:W-2.2, y:6.6, w:1.6, h:0.3, fontFace:FB, fontSize:12, color:"8FB7BD", align:"right", margin:0 });

// ============================================================
// Slide 2 — 任务背景 + 子任务
// ============================================================
s = pres.addSlide();
header(s, "项目背景", "任务目标与我负责的子任务");
// 左: 项目目标
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:1.75, w:5.7, h:4.9, fill:{color:C.dark}, shadow:sh() });
s.addText("项目总目标", { x:1.0, y:2.05, w:5, h:0.4, fontFace:FH, fontSize:18, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"做一个能预测 T 细胞免疫反应", options:{ breakLine:true, color:"FFFFFF", fontSize:15 } },
  { text:"「强弱定量程度」", options:{ breakLine:true, color:C.mint, fontSize:20, bold:true } },
  { text:"的工具 —— 比现有只判「有 / 无免疫原性」的二分类更进一步。", options:{ color:"CADCFC", fontSize:14 } },
], { x:1.0, y:2.55, w:5.1, h:1.7, fontFace:FB, valign:"top", lineSpacingMultiple:1.15, margin:0 });
s.addText([
  { text:"技术路线\n", options:{ breakLine:true, color:C.mint, fontSize:13, bold:true } },
  { text:"大量 benchmark 现有工具 + 数据集  →  结合自研 QuantImmune 算法", options:{ color:"FFFFFF", fontSize:13 } },
], { x:1.0, y:4.55, w:5.1, h:1.0, fontFace:FB, valign:"top", margin:0 });
s.addText("我的子任务：在 HPC 部署并测试运行 5 个工具，每个收集 4 类信息 → PPT", { x:1.0, y:5.7, w:5.2, h:0.7, fontFace:FB, fontSize:12.5, italic:true, color:"9FD9CF", valign:"top", margin:0 });
// 右: 4类信息
s.addText("每个工具需收集的 4 类信息", { x:6.9, y:1.85, w:6, h:0.4, fontFace:FH, fontSize:17, bold:true, color:C.ink, margin:0 });
const items = [
  ["①","输入数据的模板 / 格式","文件类型、必填列、肽长限制、HLA 格式"],
  ["②","预测工具运行参数","可调参数的类型及功能、运行模式"],
  ["③","输出数据格式及含义","关键列、分数类型、能否定量强弱"],
  ["④","工具简介","方法、特点、优势与局限"],
];
let yy=2.4;
items.forEach(it=>{
  s.addShape(pres.shapes.RECTANGLE, { x:6.9, y:yy, w:5.7, h:0.95, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.OVAL, { x:7.08, y:yy+0.22, w:0.52, h:0.52, fill:{color:C.teal} });
  s.addText(it[0], { x:7.08, y:yy+0.22, w:0.52, h:0.52, fontFace:FH, fontSize:18, bold:true, color:"FFFFFF", align:"center", valign:"middle", margin:0 });
  s.addText(it[1], { x:7.8, y:yy+0.13, w:4.6, h:0.36, fontFace:FH, fontSize:14.5, bold:true, color:C.ink, margin:0 });
  s.addText(it[2], { x:7.8, y:yy+0.5,  w:4.6, h:0.34, fontFace:FB, fontSize:11, color:C.muted, margin:0 });
  yy += 1.06;
});
pageno(s,2);

// ============================================================
// Slide 3 — 5 工具总览表
// ============================================================
s = pres.addSlide();
header(s, "总览", "5 个工具 · 部署与运行状态一览");
const hd = (t)=>({ text:t, options:{ fill:{color:C.dark}, color:"FFFFFF", bold:true, fontSize:13, align:"center", valign:"middle" } });
const cc = (t,col)=>({ text:t, options:{ color:col||C.ink, fontSize:12.5, align:"center", valign:"middle" } });
const cl = (t)=>({ text:t, options:{ color:C.ink, fontSize:12.5, bold:true, align:"left", valign:"middle" } });
const rows = [
  [hd("工具"), hd("方法"), hd("能否定量强弱"), hd("本地 WSL2"), hd("HPC"), hd("端到端「肽段→分数」")],
  [cl("DeepImmuno"), cc("CNN"), cc("✅ 连续 0-1",C.ok), cc("✅ 跑通",C.ok), cc("✅ 0.5325",C.ok), cc("✅ 完全跑通",C.ok)],
  [cl("PredIG"), cc("XGBoost"), cc("✅ 连续 0-1",C.ok), cc("✅ 跑通",C.ok), cc("✅ 0.00614",C.ok), cc("✅ 完全跑通",C.ok)],
  [cl("IMPROVE"), cc("RandomForest"), cc("✅ 连续 0-1",C.ok), cc("🟡 Predict 步",C.warn), cc("🟡 Predict 步",C.warn), cc("⚠️ 部分(特征链)",C.warn)],
  [cl("NeoTImmuML"), cc("集成 ML"), cc("✅ 概率",C.ok), cc("🟡 重训跑通",C.warn), cc("🟡 env 就绪",C.warn), cc("⚠️ 部分(需重训)",C.warn)],
  [cl("pTuneos"), cc("ML pipeline"), cc("✅ 排名分",C.ok), cc("✅ 端到端",C.ok), cc("🟡 sif 受限",C.warn), cc("✅ Pre&RecNeo",C.ok)],
];
s.addTable(rows, { x:0.7, y:1.95, w:11.9, colW:[2.0,1.9,2.3,1.85,1.7,2.15], rowH:[0.55,0.62,0.62,0.62,0.62,0.62],
  border:{pt:1,color:C.line}, align:"center", valign:"middle", fontFace:FB, fill:{color:C.card} });
// 结论条
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:5.95, w:11.9, h:0.72, fill:{color:"E6F4F1"}, line:{color:C.sea,width:1} });
s.addText([
  { text:"结论：", options:{ bold:true, color:C.teal, fontSize:13 } },
  { text:"5 工具全部部署 / 环境就绪；其中 ", options:{ color:C.ink, fontSize:12.5 } },
  { text:"5 / 5 均产出 ELISpot 真实分数并完成 benchmark", options:{ bold:true, color:C.dark, fontSize:12.5 } },
  { text:"。DeepImmuno、PredIG 本地+HPC 双验证完全端到端；pTuneos 本地 docker 端到端 (Pre&RecNeo 子模型跑 ELISpot)；IMPROVE/NeoTImmuML 部分 (缺口明确，非「装不上」)。5 个均输出连续 / 概率分数 → 都支持「强弱定量」。", options:{ color:C.ink, fontSize:12.5 } },
], { x:0.95, y:6.0, w:11.4, h:0.62, fontFace:FB, valign:"middle", lineSpacingMultiple:1.02, margin:0 });
// 「部分完成」说明条 (缺什么 → 影响什么)
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:6.74, w:11.9, h:0.66, fill:{color:"FBEEE4"}, line:{color:C.warn,width:1} });
s.addText([
  { text:"「部分完成」= 工具自身限制，非部署失败：", options:{ bold:true, color:C.warn, fontSize:11 } },
  { text:"IMPROVE 缺 ELISpot 没有的 RNA-seq 表达量 → Expression 特征降级、排序精度打折；NeoTImmuML 无官方预训练权重 → 用公开数据自训版 (不对标原论文数值)。两者均能出分、不影响进 benchmark。", options:{ color:C.ink, fontSize:11 } },
], { x:0.95, y:6.79, w:11.4, h:0.56, fontFace:FB, valign:"middle", lineSpacingMultiple:1.0, margin:0 });
pageno(s,3);

// ============================================================
// Slides 4-8 — 逐工具
// ============================================================
toolSlide({ idx:1, name:"DeepImmuno", accent:"028090", method:"CNN", status:"✅ 完全跑通", statusCol:C.ok,
  tagline:"深度学习 (CNN) 预测肽段对 CD8+ T 细胞的免疫原性 (HLA-I)，附 GAN 生成功能",
  input:[ "CSV，无表头两列  peptide,HLA", "肽段长度死限 9 / 10-mer", "HLA 格式  HLA-A*0201", "无需基因组 / HLA 库" ],
  params:[ "--mode single  单条 (结果打 stdout)", "--mode multiple --intdir --outdir  批量", "无可调超参；须在 repo 根目录运行" ],
  output:[ "tab 分隔  peptide / HLA / immunogenicity", "immunogenicity = 连续 0-1 (越高越强)", "实测 NLVPMVATV(CMV)=0.957、GILGFVFTL(流感)=0.887 → 已知强表位高分，合理" ],
  intro:[ "最轻量，纯肽段+HLA 即可，无许可工具依赖，CPU 可跑", "部署：Python3.8 + TF2.3 + protobuf3.20 (坑：不降报 Descriptors 错)", "局限：肽长死限 9/10-mer" ],
});
toolSlide({ idx:2, name:"PredIG", accent:"1C7293", method:"XGBoost", status:"✅ 完全跑通", statusCol:C.ok,
  tagline:"XGBoost 预测 T 细胞表位免疫原性，三类抗原专用模型，可解释",
  input:[ "3 模式：CSV-Uniprot / CSV-Recombinant / FASTA", "Recombinant 列  epitope,HLA_allele,protein_seq,protein_name", "肽段 8-14 AA" ],
  params:[ "--modelXG {neoant | noncan | path}", "--type {uniprot | recombinant | fasta}", "-o 输出文件" ],
  output:[ "CSV，PredIG 列 = 连续 0-1 免疫原性分", "+ NOAH / NetCleave / 物化 / TCR_contact 等 13 列特征", "实测 SLLMWITQV = 0.0061" ],
  intro:[ "连续分 + 可解释特征 + 容器化 (依赖全打包)", "部署：官方 Docker 镜像 (14.4G)→ HPC 转 Singularity (predig.sif 4.6G)", "局限：镜像大" ],
});
toolSlide({ idx:3, name:"IMPROVE", accent:"028090", method:"RandomForest", status:"⚠️ 部分完成", statusCol:C.warn,
  tagline:"随机森林预测新表位免疫原性，22 特征，三变体 (Simple / TME_excluded / TME_included)",
  input:[ "TSV，必填  突变肽 + 野生型肽 + HLA", "肽段 8-12 AA", "两步流程：① feature_calc 算特征  ② Predict 跑 RF" ],
  params:[ "步2  --model {Simple | TME_excluded | TME_included}", "每变体加载 5 个 RF (rf0-rf4 集成)" ],
  output:[ "TSV 追加  mean_prediction_rf (连续 0-1)", "= 5fold × 50 RF 集成平均", "实测 Simple 变体 EEFLNSWML = 0.5146" ],
  intro:[ "RF 22 特征，专为新表位排名设计，整合 TCR 识别 (PRIME)", "⚠️ 数据缺口：ELISpot 仅肽+HLA，无 RNA-seq → Expression / NetMHCExp 必 impute；Stability 可经容器补", "Predict 步本地+HPC 跑通；许可工具(netMHCpan/PRIME)已到位，全特征链余 netMHCstabpan(glibc 挡)+self_similarity/garnish 待补" ],
});
toolSlide({ idx:4, name:"NeoTImmuML", accent:"1C7293", method:"集成 ML", status:"⚠️ 部分(已重训)", statusCol:C.warn,
  tagline:"加权集成 (LightGBM+XGBoost+RandomForest) 预测肿瘤新抗原免疫原性，78 个肽段物化特征",
  input:[ "CSV：Peptide + immunogenicity(标签) + 78 个 R Peptides 物化特征", "肽段 8-13 AA，不要 HLA", "78 特征须先用 R Peptides 包外部算好" ],
  params:[ "不是 CLI，是 Jupyter notebook (21 cell)", "改 file_path 指数据；内含 8 算法对比+加权集成+5fold CV" ],
  output:[ "分类指标 + 雷达图 + predict_proba 连续概率", "→ 能定量强弱", "自训后 10536 ELISpot 肽出分 0.0002-0.9974" ],
  intro:[ "纯肽特征，不要 HLA / 不要 netMHCpan 等许可工具 (部署最轻)", "局限：研究 notebook 无预训练权重 → 用 TumorAgDB2.0 (36535 行) 重训", "不含 78 特征计算代码 → 须 R Peptides 算" ],
});
toolSlide({ idx:5, name:"pTuneos", accent:"028090", method:"ML pipeline", status:"✅ 端到端跑通", statusCol:C.ok,
  tagline:"个性化新抗原全流程 pipeline (WES/RNA-seq 或 VCF → 排名)；识别子模型可单独跑肽段",
  input:[ "完整 pipeline：VCF + 表达谱 + 拷贝数 + 纯度 + HLA (需全基因组，吃不了纯肽)", "⭐ Pre&RecNeo 子模型：仅 MT_pep + WT_pep + HLA 三列 (可跑 ELISpot 肽)" ],
  params:[ "完整：python pTuneos.py {WES|VCF} -i config.yaml", "Pre&RecNeo：自写 wrapper 调 InVivoModelAndScore", "批 netMHCpan/blastp 加速 + nproc 并行" ],
  output:[ "RefinedNeo = 患者级排名分 (乘表达/VAF/克隆性，需测序)", "Pre&RecNeo (model_pro) = 纯肽免疫原性识别分 → 与其他 4 工具可比", "example VCF 出 40 新抗原 (RefinedNeo 0.42–1.13)" ],
  intro:[ "镜像自带 netMHCpan-4.0 / VEP / GATK / BWA 全套；修 8 坑 + VEP cache 14G 端到端跑通", "Pre&RecNeo 跑 ELISpot 32178 肽对 → 进 5 工具 benchmark (对账官方 r=1.0)", "⚠️ 诚实：本地 docker 跑 (HPC sif 受限 singularity 非 root)；疏水模型仅 9/10/11mer" ],
});

// ============================================================
// Slide 9 — 部署环境 + 踩坑
// ============================================================
s = pres.addSlide();
header(s, "工程", "部署环境与关键技术问题");
// 左: 环境
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:1.8, w:4.6, h:4.85, fill:{color:C.dark}, shadow:sh() });
s.addText("部署环境", { x:0.95, y:2.05, w:4, h:0.4, fontFace:FH, fontSize:17, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"本机 WSL2 Ubuntu 24.04", options:{ bold:true, color:"FFFFFF", fontSize:13.5, breakLine:true } },
  { text:"调试主战场 · GPU 直通 RTX4070 · conda + Docker", options:{ color:"9FD9CF", fontSize:11.5, breakLine:true, paraSpaceAfter:10 } },
  { text:"XJTLU HPC", options:{ bold:true, color:"FFFFFF", fontSize:13.5, breakLine:true } },
  { text:"dtn.hpc.xjtlu.edu.cn · 最终部署目标", options:{ color:"9FD9CF", fontSize:11.5, breakLine:true } },
  { text:"Singularity 3.11.3 + module miniconda3 + gpfs 136T", options:{ color:"9FD9CF", fontSize:11.5, breakLine:true, paraSpaceAfter:10 } },
  { text:"出网", options:{ bold:true, color:"FFFFFF", fontSize:13.5, breakLine:true } },
  { text:"github / pypi / DTU ✅   Docker Hub ❌", options:{ color:"9FD9CF", fontSize:11.5 } },
], { x:0.95, y:2.5, w:4.15, h:4.0, fontFace:FB, valign:"top", margin:0 });
// 右: 踩坑 grid
s.addText("关键技术问题与解决 (踩坑)", { x:5.6, y:1.9, w:7, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.ink, margin:0 });
const pit = [
  ["Windows 跑不动","repo 含非法 * 文件名 → NTFS checkout 崩 → 全转 WSL2/HPC Linux"],
  ["版本地狱","老 TF/numpy/protobuf → 严格按官方 pin 建独立 conda env"],
  ["Docker Hub 国内不通","WSL mirrored 网络 + daemon 代理拉镜像；HPC 转 Singularity"],
  ["2014 老二进制 segfault","WSL 内核 vsyscall → .wslconfig 加 vsyscall=emulate"],
  ["HPC glibc 2.28 < 2.29","netMHCstabpan 二进制原生跑不了 → 需新 glibc 容器"],
  ["git-lfs 大文件","models 1.9G：--depth 1 只得指针 → git lfs pull"],
];
let py=2.4;
pit.forEach((p,i)=>{
  const col = (i%2===0)? 5.6 : 9.2;
  if(i%2===0 && i>0) py += 1.42;
  const yrow = 2.4 + Math.floor(i/2)*1.42;
  s.addShape(pres.shapes.RECTANGLE, { x:col, y:yrow, w:3.4, h:1.28, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:col, y:yrow, w:3.4, h:0.06, fill:{color:C.sea} });
  s.addText(p[0], { x:col+0.18, y:yrow+0.15, w:3.05, h:0.35, fontFace:FH, fontSize:12.5, bold:true, color:C.teal, margin:0 });
  s.addText(p[1], { x:col+0.18, y:yrow+0.52, w:3.08, h:0.68, fontFace:FB, fontSize:10.5, color:C.ink, valign:"top", margin:0 });
});
pageno(s,9);

// ============================================================
// Slide 10 — 初步结果 (ELISpot 真实数据)
// ============================================================
s = pres.addSlide();
header(s, "初步结果", "用袁老师 ELISpot 真实数据跑通");
// 左: 数据说明 + 行数
s.addText([
  { text:"数据处理管线\n", options:{ bold:true, color:C.teal, fontSize:14, breakLine:true } },
  { text:"DS1 (83 行全 9-mer) 直接喂；DS2 (101 行变长) 滑窗截取 8-14mer。HLA 归一后按各工具格式生成输入，输出回贴主干表 (34247 行)。", options:{ color:C.ink, fontSize:12 } },
], { x:0.7, y:1.75, w:5.4, h:1.5, fontFace:FB, valign:"top", lineSpacingMultiple:1.1, margin:0 });
const stat = [["DeepImmuno","17,103"],["PredIG","68,494"],["IMPROVE","26,790"],["NeoTImmuML","10,536"],["pTuneos","34,247"]];
let sy=3.18;
stat.forEach(st=>{
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:sy, w:5.4, h:0.56, fill:{color:C.card}, line:{color:C.line,width:1} });
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:sy, w:0.08, h:0.56, fill:{color:C.mint} });
  s.addText(st[0], { x:1.0, y:sy, w:3, h:0.56, fontFace:FB, fontSize:12.5, bold:true, color:C.ink, valign:"middle", margin:0 });
  s.addText(st[1]+"  行", { x:3.7, y:sy, w:2.2, h:0.56, fontFace:FB, fontSize:12.5, color:C.teal, bold:true, align:"right", valign:"middle", margin:0 });
  sy += 0.66;
});
s.addText("5 / 5 工具产出 ELISpot 真实免疫原性分数 (pTuneos 用 Pre&RecNeo 子模型跑肽段，对账官方 r=1.0)", { x:0.7, y:6.5, w:5.5, h:0.7, fontFace:FB, fontSize:10.5, italic:true, color:C.muted, valign:"top", margin:0 });
// 右: ROC 图 (1400x1200 -> 比例 1.167)
const ih=4.3, iw=ih*(1400/1200);
s.addShape(pres.shapes.RECTANGLE, { x:6.5, y:1.7, w:6.1, h:5.1, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIG+"/fig1_roc_curves_ds2.png", x:6.5+(6.1-iw)/2, y:1.95, w:iw, h:ih });
s.addText("5 工具 ROC (DS2, max 聚合, ELISpot>0)；pTuneos AUC 最高 0.75。DS2 阴性仅 11 → 非统计显著，演示用", { x:6.5, y:6.3, w:6.1, h:0.4, fontFace:FB, fontSize:9.5, italic:true, color:C.muted, align:"center", margin:0 });
pageno(s,10);

// ============================================================
// Slide 11 — Benchmark 深入 (阈值敏感 + 定量相关) + 官方/改动透明
// ============================================================
const FIG_R3 = "D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/figures_R_v3";
s = pres.addSlide();
header(s, "Benchmark 深入", "阈值敏感性 · 定量相关 · 官方/改动透明");
// 左图: 阈值柱状 (门槛效应)
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:1.65, w:5.85, h:3.35, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIG_R3+"/fig2_bar_v3.png", x:0.85, y:1.78, w:5.55, h:3.1, sizing:{type:"contain", w:5.55, h:3.1} });
s.addText("① 阈值敏感：pTuneos >0 最高 (0.78)，但 >10/>median 跌到 0.51/0.46 = 门槛效应；PredIG/IMPROVE 跨阈值稳", { x:0.7, y:5.02, w:5.85, h:0.55, fontFace:FB, fontSize:9.5, color:C.muted, valign:"top", margin:0 });
// 右图: 散点 (定量相关)
s.addShape(pres.shapes.RECTANGLE, { x:6.75, y:1.65, w:5.85, h:3.35, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIG_R3+"/fig3_scatter_v3.png", x:6.9, y:1.78, w:5.55, h:3.1, sizing:{type:"contain", w:5.55, h:3.1} });
s.addText("② 定量相关 (分数 vs ELISpot SFU)：PredIG ρ=0.28** / IMPROVE ρ=0.21* 能跟踪强度；pTuneos ρ=0.03 (ns) 不跟踪", { x:6.75, y:5.02, w:5.85, h:0.55, fontFace:FB, fontSize:9.5, color:C.muted, valign:"top", margin:0 });
// 底部: 官方 vs 我们改动 透明声明
s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:5.72, w:5.85, h:1.45, fill:{color:"E6F4F1"}, line:{color:C.sea,width:1} });
s.addText([
  { text:"✅ 完全官方 (算法/分数没动)\n", options:{ bold:true, color:C.teal, fontSize:11.5, breakLine:true } },
  { text:"5 工具模型/权重/评分；pTuneos model_pro 数值 (r=1.0 对账证)；netMHCpan/blastp/VEP 等外部工具", options:{ color:C.ink, fontSize:10 } },
], { x:0.9, y:5.85, w:5.5, h:1.25, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:6.75, y:5.72, w:5.85, h:1.45, fill:{color:"FBEEE4"}, line:{color:C.warn,width:1} });
s.addText([
  { text:"🔧 我们的改动 (需标清)\n", options:{ bold:true, color:C.warn, fontSize:11.5, breakLine:true } },
  { text:"ELISpot 滑窗/格式转换 · benchmark 评估框架 + 所有图 · ⚠️pTuneos 喂肽段 (抠识别子模型，合法但非官方标准流程) · 批处理加速 (结果同) · 修部署 8 坑 (不改算法)", options:{ color:C.ink, fontSize:10 } },
], { x:6.95, y:5.85, w:5.5, h:1.25, fontFace:FB, valign:"top", lineSpacingMultiple:1.05, margin:0 });
pageno(s,11);

// ============================================================
// Slide 12 — 结论 + 缺口
// ============================================================
s = pres.addSlide();
s.background = { color: C.dark };
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.mint} });
s.addText("结论与下一步", { x:0.9, y:0.7, w:10, h:0.7, fontFace:FH, fontSize:32, bold:true, color:"FFFFFF", margin:0 });
// 左: 已达成
s.addText("已达成", { x:0.9, y:1.85, w:5, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"5 工具全部部署 / 环境就绪", options:{ bullet:{indent:14}, breakLine:true, color:"FFFFFF", fontSize:13.5, paraSpaceAfter:8 } },
  { text:"2 个完全端到端跑通 (DeepImmuno、PredIG)，本地+HPC 双验证", options:{ bullet:{indent:14}, breakLine:true, color:"FFFFFF", fontSize:13.5, paraSpaceAfter:8 } },
  { text:"5 / 5 产出 ELISpot 真实分数 + benchmark (pTuneos 用 Pre&RecNeo 子模型，pTuneos AUC 最高 0.75)", options:{ bullet:{indent:14}, breakLine:true, color:"FFFFFF", fontSize:13.5, paraSpaceAfter:8 } },
  { text:"4 类信息全部收集完成 (逐工具文档齐)", options:{ bullet:{indent:14}, color:"FFFFFF", fontSize:13.5 } },
], { x:0.9, y:2.35, w:5.7, h:4.2, fontFace:FB, valign:"top", margin:0 });
// 右: 剩余缺口
s.addText("剩余缺口 (诚实标注)", { x:7.0, y:1.85, w:5.5, h:0.4, fontFace:FH, fontSize:16, bold:true, color:C.warn, margin:0 });
const gaps=[
  ["IMPROVE 全特征链","Expression/NetMHCExp 需 RNA-seq，ELISpot 无 → 结构性 impute"],
  ["NeoTImmuML 权重","研究 notebook 无预训练权重，已用公开库自训补"],
  ["pTuneos HPC 真跑","本地 docker 已端到端；HPC singularity 非 root/fakeroot 受限，待重打包"],
  ["袁老师正式数据","到位后按各工具格式做转换 → 正式测试"],
];
let gy=2.35;
gaps.forEach(g=>{
  s.addShape(pres.shapes.RECTANGLE, { x:7.0, y:gy, w:5.5, h:0.92, fill:{color:"123F4B"}, line:{color:"1C5563",width:1} });
  s.addShape(pres.shapes.RECTANGLE, { x:7.0, y:gy, w:0.08, h:0.92, fill:{color:C.warn} });
  s.addText(g[0], { x:7.25, y:gy+0.1, w:5.1, h:0.34, fontFace:FH, fontSize:13, bold:true, color:"FFFFFF", margin:0 });
  s.addText(g[1], { x:7.25, y:gy+0.46, w:5.1, h:0.42, fontFace:FB, fontSize:10.5, color:"9FD9CF", valign:"top", margin:0 });
  gy += 1.04;
});
s.addText("数据真源：本地 ~/quantimmu/smoke/ + HPC /gpfs/.../quantimmu/ · 逐工具 4 类信息见 TOOLS/*.md", { x:0.9, y:6.95, w:11.5, h:0.4, fontFace:FB, fontSize:10, italic:true, color:"6E9AA1", margin:0 });

// ---------- write ----------
pres.writeFile({ fileName: "D:/YJ-Agent/project/meeting/QuantImmuBench/QuantImmuBench_部署测试报告.pptx" })
  .then(f=>console.log("WROTE", f))
  .catch(e=>{ console.error("ERR", e); process.exit(1); });
