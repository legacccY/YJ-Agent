// QuantImmuBench — 7 新工具独立横评报告 (2026-06-27)
// 范围：BigMHC / CNNeo / MHCflurry / IEDB_Calis / Repitope / T-SCAPE / netMHCpan-BA
// 视觉风格仿 gen_ppt_5tools.js（LAYOUT_WIDE，teal/mint 配色）
// 数字真源：analysis/NEWTOOLS_ANALYSIS.md（已核 metrics_ds2_16tools.csv）
// 运行: NODE_PATH=C:/Users/yj200/AppData/Roaming/npm/node_modules node ppt/gen_ppt_newtools.js
const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "新增 7 对比工具横评 · QuantImmuBench";

const W = 13.33, H = 7.5;
const C = {
  dark:"0B3C49", teal:"028090", sea:"00A896", mint:"02C39A",
  light:"F2F7F7", card:"FFFFFF", ink:"16323A", muted:"5E7B83",
  line:"D5E3E4", warn:"C9743D", ok:"00A896", crit:"B23A48", gray:"8A9BA0",
};
const FH = "Microsoft YaHei", FB = "Microsoft YaHei";
const FIG = "D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/figures";

const sh = () => ({ type:"outer", color:"0B3C49", blur:9, offset:3, angle:135, opacity:0.12 });

let _PG = 1;
function header(slide, kicker, title, accent){
  accent = accent || C.teal;
  slide.background = { color: C.light };
  slide.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:0.28, h:H, fill:{color:accent} });
  slide.addText(kicker.toUpperCase(), { x:0.7, y:0.42, w:11, h:0.3, fontFace:FB, fontSize:12, color:accent, bold:true, charSpacing:3, margin:0 });
  slide.addText(title, { x:0.7, y:0.72, w:12, h:0.7, fontFace:FH, fontSize:26, color:C.ink, bold:true, margin:0 });
}
function pageno(slide){
  _PG++;
  slide.addText(String(_PG), { x:W-0.8, y:H-0.5, w:0.5, h:0.3, fontFace:FB, fontSize:11, color:C.muted, align:"right", margin:0 });
}
function infoCard(slide, x, y, w, h, head, lines, accent){
  slide.addShape(pres.shapes.RECTANGLE, { x:x, y:y, w:w, h:h, fill:{color:C.card}, line:{color:C.line, width:1}, shadow:sh() });
  slide.addShape(pres.shapes.RECTANGLE, { x:x, y:y, w:0.09, h:h, fill:{color:accent} });
  slide.addText(head, { x:x+0.28, y:y+0.16, w:w-0.4, h:0.34, fontFace:FH, fontSize:15, bold:true, color:accent, margin:0 });
  var rt = lines.map(function(t){ return { text:t, options:{ bullet:{indent:12}, breakLine:true, color:C.ink, fontSize:11.5, paraSpaceAfter:5 } }; });
  slide.addText(rt, { x:x+0.3, y:y+0.58, w:w-0.55, h:h-0.7, fontFace:FB, valign:"top", margin:0 });
}
function badge(slide, x, y, txt, col, bw){
  bw = bw || 2.5;
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x:x, y:y, w:bw, h:0.42, rectRadius:0.21, fill:{color:col} });
  slide.addText(txt, { x:x, y:y, w:bw, h:0.42, fontFace:FB, fontSize:11.5, bold:true, color:"FFFFFF", align:"center", valign:"middle", margin:0 });
}
function citeFoot(slide, txt){
  var runs = [{ text:"来源  ", options:{ color:C.teal, fontSize:9, bold:true } }];
  txt.split(" · ").forEach(function(p, i){
    var opt = { color:C.muted, fontSize:9 };
    var dm = p.match(/DOI\s+(10\.\S+)/);
    var gm = p.match(/(github\.com\/\S+|tools\.iedb\.org\S*|services\.healthtech\.dtu\.dk\S*)/);
    if(dm) opt = { color:"1C7293", fontSize:9, hyperlink:{ url:"https://doi.org/"+dm[1], tooltip:"DOI" } };
    else if(gm) opt = { color:"1C7293", fontSize:9, hyperlink:{ url:"https://"+gm[1], tooltip:"repo/web" } };
    runs.push({ text:(i>0?" · ":"")+p, options:opt });
  });
  slide.addText(runs, { x:0.7, y:7.08, w:11.4, h:0.34, fontFace:FB, italic:true, valign:"top", margin:0 });
}

// 工具卡（7 新工具，仿 toolSlide）
function toolSlideNew(o){
  var s = pres.addSlide();
  header(s, "新工具 "+o.idx+" / 7  四类信息", o.name, o.accent);
  s.addText(o.tagline, { x:0.7, y:1.46, w:8.6, h:0.5, fontFace:FB, fontSize:12.5, color:C.muted, margin:0 });
  badge(s, W-3.2, 0.72, o.status, o.statusCol, 2.5);
  s.addText("生态位  "+o.niche, { x:W-3.2, y:1.22, w:2.5, h:0.3, fontFace:FB, fontSize:10.5, color:C.teal, bold:true, align:"center", margin:0 });
  var cx=0.7, cy=2.0, cw=6.0, ch=2.28, gap=0.3;
  infoCard(s, cx,          cy,        cw, ch, "① 输入数据 / 格式", o.input,  o.accent);
  infoCard(s, cx+cw+gap,   cy,        cw, ch, "② 运行参数",       o.params, o.accent);
  infoCard(s, cx,          cy+ch+gap, cw, ch, "③ 输出格式 / 含义", o.output, o.accent);
  infoCard(s, cx+cw+gap,   cy+ch+gap, cw, ch, "④ 简介 / 选用理由", o.intro,  o.accent);
  citeFoot(s, o.cite);
  pageno(s);
}

// ============================================================ 封面
var s = pres.addSlide();
s.background = { color: C.dark };
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.mint} });
s.addShape(pres.shapes.OVAL, { x:W-3.3, y:-1.6, w:4.6, h:4.6, fill:{color:C.teal, transparency:78} });
s.addShape(pres.shapes.OVAL, { x:W-2.0, y:3.6,  w:3.2, h:3.2, fill:{color:C.sea,  transparency:82} });
s.addText("癌症个性化新抗原疫苗  新增对比工具横评", { x:0.9, y:1.5, w:11, h:0.4, fontFace:FB, fontSize:15, color:C.mint, bold:true, charSpacing:2, margin:0 });
s.addText("新增 7 对比工具独立横评\n方法学多样性扩充报告", { x:0.9, y:2.05, w:11.5, h:1.8, fontFace:FH, fontSize:40, bold:true, color:"FFFFFF", lineSpacingMultiple:1.05, margin:0 });
s.addText("BigMHC  CNNeo  MHCflurry  IEDB_Calis  Repitope  T-SCAPE  netMHCpan-BA", { x:0.9, y:4.25, w:11.5, h:0.5, fontFace:FB, fontSize:14, color:"CADCFC", margin:0 });
s.addShape(pres.shapes.LINE, { x:0.95, y:5.1, w:3.2, h:0, line:{color:C.mint, width:2} });
s.addText([
  { text:"内容  ", options:{ color:"8FB7BD", fontSize:13 } },
  { text:"方法学演化光谱 · 文献矩阵 · 逐工具四类信息 · ELISpot 17 工具横评结果", options:{ color:"FFFFFF", fontSize:13, breakLine:true } },
  { text:"真源  ", options:{ color:"8FB7BD", fontSize:13 } },
  { text:"NEWTOOLS_ANALYSIS.md · TOOLS/<tool>.md · NEWTOOLS_LIT_MATRIX.md", options:{ color:"FFFFFF", fontSize:13 } },
], { x:0.95, y:5.35, w:9.5, h:1.0, fontFace:FB, valign:"top", margin:0 });
s.addText("2026-06-27", { x:W-2.4, y:6.7, w:1.8, h:0.3, fontFace:FB, fontSize:12, color:"8FB7BD", align:"right", margin:0 });

// ============================================================ 为什么选这 7 个：方法学演化光谱
s = pres.addSlide();
header(s, "选型理由", "方法学演化光谱  每个工具填补一个独特生态位");
s.addText("这 7 个工具不是同质堆叠，而是沿方法学演化主轴各占一格，使横评从「比谁分高」升级为「检验每一类方法范式对免疫强弱定量的真实贡献」。", {
  x:0.7, y:1.46, w:11.9, h:0.44, fontFace:FB, fontSize:12.5, color:C.muted, margin:0
});
var specItems = [
  ["统计基线",        "IEDB_Calis  2013",     "纯氨基酸理化属性线性加权（P4–P6 位富集），无 ML，无权重；主流流水线默认集成（pVACseq/iNeo-Suite）；任何新工具不超过它即可判无效。",   C.teal],
  ["HLA-agnostic",   "Repitope  2019",        "不问肽结合哪个 HLA，用整个人群 TCR 库的 in-silico 接触势能打分；量化「HLA 限制信息」对定量到底值多少。",                             C.sea],
  ["纯结合亲和力",    "netMHCpan-BA  2020",   "HLA-肽结合金标准（覆盖 >18,000 等位基因）；直接验证「结合亲和力 ≠ 免疫原性」命题，量化 gap，为其他工具提供提升幅度参照系。  ⚠️ DTU",  C.warn],
  ["提呈代理",        "MHCflurry 2.0  2020",  "开源社区最广用提呈预测，双分数（affinity + presentation）；检验「提呈预测无免疫原性微调能否代理强弱定量」；reviewer 必注意缺席。",    C.teal],
  ["LLM 增强",        "CNNeo  2026",           "率先引入 BioBERT 蛋白质语言模型嵌入（CNN+BioBERT），正交于 BigMHC；2026 最新，TESLA+ELISpot 验证与本项目真值同源，MIT 许可。",      C.sea],
  ["大规模迁移",      "BigMHC  2023",          "EL 大规模预训练（数十万 MHC-I 洗脱配体）→ IM 下游迁移两阶段范式，7 checkpoint ensemble；Nature MI 2023，pan-allele >500 等位基因。",  C.teal],
  ["多域结构 SOTA",   "T-SCAPE  2025",         "多任务跨域 DL（ByteNet），融合 pMHC 结合 / TCR 结合 / 免疫原性四路信号；检验「复杂度上限」是否突破数据瓶颈。  ⚠️ CC-BY-NC-ND",     C.crit],
];
var siy=1.97, sih=0.65, sigap=0.05;
specItems.forEach(function(it, i){
  var y = siy + i*(sih+sigap);
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:y, w:11.9, h:sih, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:y, w:0.09, h:sih, fill:{color:it[3]} });
  s.addText(it[0], { x:0.88, y:y+0.08, w:1.65, h:sih-0.16, fontFace:FH, fontSize:11, bold:true, color:it[3], valign:"middle", margin:0 });
  s.addText(it[1], { x:2.62, y:y+0.08, w:2.3, h:sih-0.16, fontFace:FB, fontSize:11, bold:true, color:C.ink, valign:"middle", margin:0 });
  s.addText(it[2], { x:5.08, y:y+0.07, w:7.3, h:sih-0.14, fontFace:FB, fontSize:10, color:C.muted, valign:"middle", lineSpacingMultiple:1.02, margin:0 });
});
pageno(s);

// ============================================================ 文献矩阵表
s = pres.addSlide();
header(s, "文献矩阵", "7 个新对比工具：论文 · 期刊年份 · DOI · repo / web · 许可");
var lh = function(t){ return { text:t, options:{ fill:{color:C.dark}, color:"FFFFFF", bold:true, fontSize:11, align:"center", valign:"middle" } }; };
var lc = function(t, col, bold){ return { text:t, options:{ color:col||C.ink, fontSize:9.5, align:"left", valign:"middle", bold:!!bold } }; };
var lcLink = function(t, url){ return { text:t, options:{ color:"1C7293", fontSize:9.5, align:"left", valign:"middle", hyperlink:{ url:url, tooltip:url } } }; };
var litRows = [
  [lh("工具"), lh("年 / 期刊"), lh("DOI"), lh("repo / web"), lh("许可")],
  [lc("IEDB_Calis",C.teal,true),     lc("2013 · PLOS Comput Biol"),   lcLink("10.1371/journal.pcbi.1003266","https://doi.org/10.1371/journal.pcbi.1003266"), lcLink("tools.iedb.org/immunogenicity","https://tools.iedb.org/immunogenicity"),             lc("NPOSL-3.0 ✅")],
  [lc("Repitope",C.sea,true),        lc("2019 · Front Immunol"),      lcLink("10.3389/fimmu.2019.00827","https://doi.org/10.3389/fimmu.2019.00827"),          lcLink("github.com/masato-ogishi/Repitope","https://github.com/masato-ogishi/Repitope"),   lc("MIT ✅")],
  [lc("netMHCpan-BA",C.warn,true),   lc("2020 · Nucleic Acids Res"),  lcLink("10.1093/nar/gkaa379","https://doi.org/10.1093/nar/gkaa379"),                    lcLink("services.healthtech.dtu.dk","https://services.healthtech.dtu.dk/services/NetMHCpan-4.1"), lc("⚠️ DTU 禁再分发",C.warn)],
  [lc("MHCflurry 2.0",C.teal,true),  lc("2020 · Cell Systems"),       lcLink("10.1016/j.cels.2020.06.010","https://doi.org/10.1016/j.cels.2020.06.010"),      lcLink("github.com/openvax/mhcflurry","https://github.com/openvax/mhcflurry"),             lc("Apache-2.0 ✅")],
  [lc("CNNeo",C.sea,true),           lc("2026 · Front Immunol"),      lcLink("10.3389/fimmu.2026.1722117","https://doi.org/10.3389/fimmu.2026.1722117"),       lcLink("github.com/AaronChen007/neoantigen","https://github.com/AaronChen007/neoantigen"), lc("MIT ✅")],
  [lc("BigMHC",C.teal,true),         lc("2023 · Nature Machine Intell"),lcLink("10.1038/s42256-023-00694-6","https://doi.org/10.1038/s42256-023-00694-6"),     lcLink("github.com/KarchinLab/bigmhc","https://github.com/KarchinLab/bigmhc"),           lc("学术非商用 ✅")],
  [lc("T-SCAPE",C.crit,true),        lc("2025 · Science Advances"),   lcLink("10.1126/sciadv.adz8759","https://doi.org/10.1126/sciadv.adz8759"),               lcLink("github.com/seoklab/T-SCAPE","https://github.com/seoklab/T-SCAPE"),               lc("⚠️ CC-BY-NC-ND",C.crit)],
];
s.addTable(litRows, { x:0.5, y:1.85, w:12.35, colW:[1.85,2.5,2.9,2.55,2.55],
  rowH:[0.48,0.62,0.62,0.62,0.62,0.62,0.62,0.62],
  border:{pt:1,color:C.line}, valign:"middle", fontFace:FB, fill:{color:C.card} });
s.addText([
  { text:"⚠️ 许可红线（对外/投稿前必处理）：", options:{ bold:true, color:C.warn, fontSize:10 } },
  { text:"netMHCpan-BA = DTU 学术许可禁再分发，数字对外前取 DTU 书面同意；T-SCAPE = CC-BY-NC-ND 4.0 禁衍生，报告数字须标注来源。其余 5 工具许可均允许发数字。", options:{ color:C.ink, fontSize:10 } },
], { x:0.5, y:6.72, w:12.35, h:0.66, fontFace:FB, valign:"top", lineSpacingMultiple:1.08, margin:0 });
pageno(s);

// ============================================================ 工具卡 1 — IEDB_Calis
toolSlideNew({ idx:1, name:"IEDB Immunogenicity  Calis 2013", accent:C.teal, niche:"统计基线", status:"✅ RUN_DONE", statusCol:C.ok,
  tagline:"经典统计线性加权，2013 历史基准  现代工具须显著超越此线才算真进步",
  input:["纯文本 .txt，每行一条肽序列（大写），无 HLA 列，无表头",
         "每次调用只处理一个 HLA allele（命令行 --allele 参数）",
         "肽段 9-mer 最优；8-mer / 10-mer+ 均支持，全 34247 行 0 NaN",
         "HLA 格式：去 * 去 :（HLA-A*02:01 → HLA-A0201）；42 个有 allele-specific mask"],
  params:["--allele=HLA-A0201   指定 allele（使用 allele-specific mask）",
          "不加 --allele → 默认 mask（P1, P2, C-term），其余约 23/65 allele 用此回退",
          "--allele_list  打印全部 42 个支持 allele",
          "安装：无需 pip，直接 wget IEDB_Immunogenicity-3.0.tar.gz 解压即用"],
  output:["stdout CSV：peptide / length / score（按 score 降序排列）",
          "score 无硬边界（通常 -1.5 ~ +1.5），越高越免疫原，直接用无需翻转",
          "实测：34247 行，0 NaN；不支持 allele 回退默认 mask 仍给分",
          "完全可解释：每个 score 可逐位追溯氨基酸 propensity 贡献"],
  intro:["纯统计，无 ML，无权重文件；零依赖，纯 Python 3，65 allele 秒级跑完",
         "被 pVACseq、iNeo-Suite 等主流新抗原流水线默认集成",
         "2013 PLOS Comput Biol，引用频次最高的 class-I 免疫原性工具之一",
         "选用理由：建立历史对照基准——任何新工具不超过它即可判无效"],
  cite:"Calis 2013 · PLOS Comput Biol · DOI 10.1371/journal.pcbi.1003266 · tools.iedb.org/immunogenicity · NPOSL-3.0" });

// ============================================================ 工具卡 2 — Repitope
toolSlideNew({ idx:2, name:"Repitope  HLA-agnostic  2019", accent:C.sea, niche:"HLA-agnostic", status:"✅ RUN_DONE  n=9", statusCol:C.ok,
  tagline:"唯一 HLA-agnostic 路线  用 TCR 库接触势能量化肽序列内在免疫原性潜力",
  input:["仅肽段序列（大写氨基酸），不接受 HLA 输入（HLA-agnostic）",
         "严格 8-11mer；12-14mer 不支持，对应行填 NaN（约 35% universe 缺分）",
         "实测：7437 个唯一 8-11mer 肽进入预测",
         "⚠️ 同一肽对所有 HLA_Allele 行填相同值（HLA-agnostic 映射）"],
  params:["R API 三步：Features() → TrainModels() → Predict()",
          "--cores N  并行核数（建议 6-8，加速 CPP 特征计算）",
          "需下载预计算文件：FragmentLibrary.fst + FeatureDF_Weighted.10000.fst（Mendeley DOI 10.17632/sydw5xnxpt.1，共约 127MB）",
          "每次运行重训 25 个 ERT 模型（5 seeds × 5 runs，约 5-20min）；无预保存权重"],
  output:["ImmunogenicityScore [0,1]，越高越免疫原；直接用，无需翻转",
          "ImmunogenicityScore.cv = 25 模型间变异系数（一致性参考）",
          "实测：34247 行；22391 行有分（8-11mer）；12-14mer → NaN；score 0.06-0.61",
          "benchmark AUC 0.620（排全 17 工具第 4）；per-patient fisherz 0.119（CI 含 0）"],
  intro:["唯一 HLA-agnostic：量化「HLA 限制信息」对免疫原性定量到底值多少",
         "CPP（Contact Potential Profiling）—— in-silico TCR 接触势能，生物物理可解释",
         "MIT 许可，部署零申请；R + rJava + extraTrees（CRAN 已下架需 Archive 源码编译）",
         "选用理由：HLA-agnostic 若不差说明序列内在特征够用；若很差反证 HLA 是关键信号"],
  cite:"Repitope, Front Immunology 2019 · DOI 10.3389/fimmu.2019.00827 · github.com/masato-ogishi/Repitope · MIT" });

// ============================================================ 工具卡 3 — netMHCpan-BA
toolSlideNew({ idx:3, name:"netMHCpan-4.1  BA mode  DTU  2020", accent:C.warn, niche:"纯结合亲和力", status:"⚠️ DTU pending", statusCol:C.warn,
  tagline:"HLA-肽结合亲和力金标准  验证「结合亲和力 ≠ 免疫原性」命题  ⚠️ 禁再分发",
  input:["每 allele 一个 .pep 文件（每行一条肽序列）；Linux 二进制，需 DTU 学术许可",
         "HLA 格式：去 *（HLA-A*02:01 → HLA-A02:01），保留冒号",
         "肽段 8-15mer；实测 53582 行（MT+WT）分组为 65 个 .pep 文件",
         "部署：HPC /gpfs/work/bio/jiayu2403/quantimmu/ext_tools/netMHCpan-4.1/"],
  params:["netMHCpan -a HLA-A02:01 -BA -xls input.pep",
          "-BA  Binding Affinity 模式（对比 -EL 洗脱配体模式）",
          "-xls  输出 XLS 格式（parse_netmhcpan_ba.py 批量解析）",
          "流水线：prep_netmhcpan_ba.py → sbatch run_netmhcpan_ba.sh → parse_netmhcpan_ba.py"],
  output:["Aff_nM：IC50 亲和力（nM），越低越强结合",
          "Rnk_BA：%排位（百分比），越低越强结合",
          "取负后 netmhcpan_ba_score = -Rnk_BA（越高=更强结合，与其他工具方向一致）",
          "⚠️ 全部 34247 行标 pending_DTU_consent=True；对外前须 DTU 书面授权"],
  intro:["HLA-肽结合亲和力金标准，覆盖 >18,000 等位基因，新抗原流水线最广用上游工具",
         "mean 聚合下全场最强 Spearman rho=+0.381（p=0.0003），但仅 mean 聚合触发，不稳健",
         "DTU 学术许可：禁止再分发在其软件上跑出的 benchmark 数字，投稿/对外前取书面同意",
         "选用理由：直接验证「结合 ≠ 免疫原性」命题，量化 gap，为其他工具提供提升幅度参照系"],
  cite:"netMHCpan-4.1, Nucleic Acids Res 2020 · DOI 10.1093/nar/gkaa379 · services.healthtech.dtu.dk · DTU 学术许可 ⚠️ 禁再分发" });

// ============================================================ 工具卡 4 — MHCflurry
toolSlideNew({ idx:4, name:"MHCflurry 2.0  提呈代理  2020", accent:C.teal, niche:"提呈代理", status:"✅ RUN_DONE", statusCol:C.ok,
  tagline:"开源社区最广用提呈预测  双分数（affinity + presentation）  Apache-2.0",
  input:["Python API：predictor.predict(peptides, alleles)；或 CLI（CSV）",
         "peptides = str list；alleles = ['HLA-A*02:01']（标准格式，与 universe 一致）",
         "肽段 8-15mer；支持 65 个 allele 全覆盖，0 NaN",
         "pip install mhcflurry + mhcflurry-downloads fetch models_class1_presentation（~70MB）"],
  params:["按 allele 分组循环预测（65 组，每组约 800 肽）",
          "verbose=0 静默，1 进度条",
          "CPU 全量 ~30-60min；GPU ~5min（TF 自动检测）",
          "⚠️ 需隔离 conda env（TF 2.x；若环境有 TF 1.x 会冲突）"],
  output:["presentation_score [0,1]，越高越强提呈（直接用，不需翻转）",
          "affinity nM → 取负 affinity_neg（越高=越强结合，正向化后与其他工具方向一致）",
          "实测：34247 行，0 NaN（65 allele 全支持）",
          "benchmark：AUC 0.432；affinity_neg mean 聚合 rho=-0.328(p=0.002)  ⚠️ 方向翻转"],
  intro:["社区使用最广（openvax），多数新工具论文以其为必须对比的公共参照系",
         "本身不直接预测 T 细胞免疫原性（提呈代理）；双分数可分析哪条更预测真值",
         "Apache-2.0 完全自由发布（数字、结果无限制），pip 一键安装，无 DTU 申请障碍",
         "选用理由：检验「提呈预测无免疫微调能否代理强弱定量」；不纳入 reviewer 会注意"],
  cite:"MHCflurry 2.0, Cell Systems 2020 · DOI 10.1016/j.cels.2020.06.010 · github.com/openvax/mhcflurry · Apache-2.0" });

// ============================================================ 工具卡 5 — CNNeo
toolSlideNew({ idx:5, name:"CNNeo / CNNeoPP  LLM 增强  2026", accent:C.sea, niche:"LLM 增强", status:"✅ RUN_DONE", statusCol:C.ok,
  tagline:"首个引入 BioBERT 蛋白质语言模型的新表位免疫原性工具  2026 最新  TESLA+ELISpot 验证",
  input:["CSV（peptide, hla）；HLA 标准格式 HLA-A*02:01",
         "8-11mer 为训练分布内；12-14mer 轻度 OOD，分数可用但注意；<8 或 >14 自动过滤",
         "无需 WT 肽，无需基因组数据",
         "实测：53582 行（MT+WT）→ 34247 行有分，0 NaN"],
  params:["三步流水线：prep_input.py → run_cnneo.py → parse_output.py",
          "--model cnn_biobert（BioBERT+TextCNN，需 HF 下载 ~500MB）；默认 FCNN_TF（TF-IDF，CPU 5-15min）",
          "--smoke N 烟测（仅对 N 对推理，不影响训练）；--force-retrain 强制重训",
          "⚠️ 无官方预训练权重：首次运行自动从 repo 内置 training_data.xlsx 训练"],
  output:["score [0,1]（softmax class=1 概率），越高越免疫原，>0.5 判阳",
          "实测（FCNN_TF 自训 ValAcc ~75%）：34247 行，0 NaN，score 范围 0.13-0.96",
          "benchmark AUC 0.382；per-patient fisherz -0.173（CI 全含 0，CI [-0.399, 0.073]）",
          "label 辅助列：score>0.5 → 1（分类标签）"],
  intro:["首个引入 BioBERT 的新表位免疫原性工具；方法正交于 BigMHC（外部 LLM vs 自训大矩阵）",
         "2026 Frontiers in Immunology，TESLA+ELISpot 验证（与本 benchmark 真值同源）",
         "MIT 许可，完全自由发布；FCNN_TF 子模型轻量，CPU 可完成",
         "选用理由：填「LLM 增强序列表征」方法学空白；2026 最新，展示方法前沿"],
  cite:"CNNeoPP, Front Immunology 2026 · DOI 10.3389/fimmu.2026.1722117 · github.com/AaronChen007/neoantigen · MIT" });

// ============================================================ 工具卡 6 — BigMHC
toolSlideNew({ idx:6, name:"BigMHC -m=im  大规模迁移  2023", accent:C.teal, niche:"大规模迁移", status:"✅ RUN_DONE", statusCol:C.ok,
  tagline:"两阶段迁移学习 7-checkpoint ensemble  pan-allele >500 等位基因  Nature MI 2023",
  input:["CSV（mhc, pep）；HLA 格式宽容（HLA-A*02:01 / A*02:01 / A0201 均可，模糊匹配）",
         "肽长 8-14mer；实测 benchmark universe 全覆盖，0 NaN",
         "无需 WT 肽，无需基因组数据",
         "实测：53582 行（MT+WT）→ 34247 行有分，0 NaN，BigMHC_IM 范围 0.0-0.95"],
  params:["python predict.py -m=im -a=0 -p=1 -c=1 -d=cpu -j=4 -v=1",
          "-m=im  免疫原性模式（自动加载 7 个不同 batch-size checkpoint ensemble，取平均分）",
          "⚠️ 必须从 repo/src/ 目录运行（内部依赖相对路径 ../../models/ + ../data/）",
          "⚠️ git lfs clone ~5GB（含模型权重）；Windows 须 -j=1（避 spawn OOM）"],
  output:["BigMHC_IM [0,1]，越高越免疫原；直接用，无需翻转",
          "7 个不同 batch-size checkpoint（bat512~bat32768/im）ensemble 平均",
          "实测：34247 行，0 NaN；EL 模式官方验证 diff=4.5e-7（权重完整，管道正确）",
          "benchmark AUC 0.396；per-patient fisherz -0.069（CI [-0.307, 0.176]，含 0）"],
  intro:["两阶段迁移：Stage 1 EL 预训练（数十万 MHC-I 洗脱配体 MS 数据）→ Stage 2 IM 下游迁移",
         "Nature MI 2023 高可信，同类比较精度最优，pan-allele 覆盖 >500 等位基因",
         "BigMHC Academic License（学术非商用）；发数字 ✅，商用需另签协议",
         "选用理由：代表「大规模预训练 + 下游迁移」现代范式；reviewer 会注意其缺席"],
  cite:"BigMHC, Nature Machine Intelligence 2023 · DOI 10.1038/s42256-023-00694-6 · github.com/KarchinLab/bigmhc · 学术非商用" });

// ============================================================ 工具卡 7 — T-SCAPE
toolSlideNew({ idx:7, name:"T-SCAPE  多域结构 SOTA  2025", accent:C.crit, niche:"多域结构 SOTA", status:"⚠️ CC-BY-NC-ND", statusCol:C.crit,
  tagline:"多任务跨域 DL（ByteNet）融合 4 路信号  2025 Science Advances  ⚠️ 全聚合负相关，方向待核",
  input:["CSV（Allele, peptide）；peptide 列必须小写（官方 bug：文档写大写，实际读小写）",
         "肽长 ≤20mer（最优 9-mer）；HLA 标准格式 HLA-A*02:01",
         "MT-only，无需野生型对照，输入门槛低",
         "⚠️ 前置：mhc_pseudo_matching.py I 过滤不支持 allele（实测 308 行被滤 → NaN）"],
  params:["两步：python mhc_pseudo_matching.py I input.csv input_mod.csv",
          "        python inference_csv.py --inf_type pmhc_im_neo --csv_path input_mod.csv --output out.csv",
          "CPU 推理（device=cpu, batch_size=32）；Linux-only",
          "⚠️ 官方代码 3 个 bug 需修复（列名 bug + pmhc_im_neo KeyError + dropout 确定性 bug）；权重 HuggingFace 下载，癌症任务仅需 0.53GB"],
  output:["score [0,1]，官方定义越高越免疫原，>0.5=阳",
          "实测：34247 行，33939 行有分（308 行 allele 被过滤 NaN）；score 0.0057-0.7716",
          "benchmark AUC 0.362（低于随机 0.5）；全聚合一致显著负相关（rho -0.23~-0.27，p<0.05）",
          "⚠️ 方向疑反转（高分=低应答？）；守复现零偏离红线，未擅自取反，标「方向待核」"],
  intro:["跨域辅助多任务 DL（ByteNet 骨架）：联合 pMHC 结合 / TCR 结合 / 免疫原性四路信号",
         "2025 Science Advances（前身 TITANiAN, bioRxiv 2025.05.11.653308）",
         "⚠️ CC-BY-NC-ND 4.0：仅限学术非商用，禁衍生与分发修改版，报告数字须署名",
         "选用理由：「复杂度上限」基线——最新 SOTA 若也弱，说明是数据瓶颈而非方法瓶颈"],
  cite:"T-SCAPE, Science Advances 2025 · DOI 10.1126/sciadv.adz8759 · github.com/seoklab/T-SCAPE · CC-BY-NC-ND 4.0" });

// ============================================================ 横评结果 · AUC 柱状图
s = pres.addSlide();
header(s, "横评结果  判别力", "17 工具 AUC（DS2，max 聚合，阈值>0）  新工具未破旧工具天花板");
s.addShape(pres.shapes.RECTANGLE, { x:0.6, y:1.65, w:7.5, h:5.32, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIG+"/fig_auc_17tools_corrected.png", x:0.75, y:1.78, w:7.18, h:4.9, sizing:{type:"contain", w:7.18, h:4.9} });
s.addText("图：17 工具 AUC 柱状图（DS2，max 聚合，阈值>0）。虚线=随机 0.5；粗线=0.75。新工具（橙色/标注）与旧工具（蓝色）对比。", {
  x:0.62, y:6.62, w:7.5, h:0.4, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", margin:0 });
var aucPts = [
  ["旧工具仍领先", "pTuneos 0.719 / PredIG 0.660 / NeoTImmuML 0.655 居前三；新工具最高 Repitope 0.620 仅列第 4，未超旧工具天花板。", C.teal],
  ["新工具整体落后", "7 个新工具 AUC 集中在 0.36-0.62，中值约 0.42；6 个（Repitope 除外）全低于旧工具中值。", C.warn],
  ["TSCAPE AUC 最低", "T-SCAPE AUC 0.362，低于随机基线 0.5；与其全聚合显著负相关结论一致，分数方向疑反转。", C.crit],
];
var apy = 1.72;
aucPts.forEach(function(p){
  s.addShape(pres.shapes.RECTANGLE, { x:8.28, y:apy, w:4.47, h:1.62, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:8.28, y:apy, w:0.09, h:1.62, fill:{color:p[2]} });
  s.addText(p[0], { x:8.46, y:apy+0.12, w:4.2, h:0.36, fontFace:FH, fontSize:13.5, bold:true, color:p[2], margin:0 });
  s.addText(p[1], { x:8.46, y:apy+0.52, w:4.1, h:1.06, fontFace:FB, fontSize:10.5, color:C.ink, valign:"top", lineSpacingMultiple:1.04, margin:0 });
  apy += 1.72;
});
pageno(s);

// ============================================================ 横评结果 · Spearman 柱状图
s = pres.addSlide();
header(s, "横评结果  定量强弱", "17 工具 Spearman（DS2，best-agg per tool）  corrected-full 口径");
s.addShape(pres.shapes.RECTANGLE, { x:0.6, y:1.65, w:7.4, h:5.32, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIG+"/fig_spearman_17tools_corrected.png", x:0.72, y:1.78, w:7.1, h:4.9, sizing:{type:"contain", w:7.1, h:4.9} });
s.addText("图：17 工具 Spearman 相关柱状图（corrected-full 口径，best-agg per tool）。* p<0.05；横线=0；CI 线段。新旧工具分色。", {
  x:0.62, y:6.62, w:7.4, h:0.4, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", margin:0 });
var sprPts = [
  ["netmhcpan_ba mean 聚合最强（DTU pending）", "mean 聚合 rho=+0.381 p=0.0003，AUC(mean,>10)=0.714——全场最强信号，但仅 mean 聚合触发（max/top3 均 n.s.），聚合高度敏感，不稳健。⚠️ 所有数字 pending_DTU_consent=True。", C.warn],
  ["TSCAPE 全聚合一致显著负", "3 种聚合 rho 均 -0.23~-0.27，p 均<0.05；AUC 0.362（低于随机）。分数语义疑反转（高分=低应答）；守复现零偏离红线，未取反，标「方向待核」。", C.crit],
  ["MHCflurry_affinity 聚合方向翻转", "max rho=+0.158(n.s.) / mean -0.328(p=0.002) / top3 +0.215(p=0.047)——三聚合方向不一致，对「取最强 vs 平均结合」高度敏感；引用时须说明聚合依赖性。", C.warn],
];
var spy = 1.72;
sprPts.forEach(function(p){
  s.addShape(pres.shapes.RECTANGLE, { x:8.18, y:spy, w:4.57, h:1.62, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:8.18, y:spy, w:0.09, h:1.62, fill:{color:p[2]} });
  s.addText(p[0], { x:8.36, y:spy+0.1, w:4.3, h:0.38, fontFace:FH, fontSize:12.5, bold:true, color:p[2], margin:0 });
  s.addText(p[1], { x:8.36, y:spy+0.52, w:4.2, h:1.06, fontFace:FB, fontSize:10, color:C.ink, valign:"top", lineSpacingMultiple:1.04, margin:0 });
  spy += 1.72;
});
pageno(s);

// ============================================================ 新工具详细 · Fisher-Z + Heatmap
s = pres.addSlide();
header(s, "新工具详细结果", "per-patient Fisher-Z 加权均值  Spearman 聚合方向热图");
s.addShape(pres.shapes.RECTANGLE, { x:0.55, y:1.62, w:6.25, h:5.32, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIG+"/fig_newtools_fisherz.png", x:0.65, y:1.72, w:6.0, h:5.1, sizing:{type:"contain", w:6.0, h:5.1} });
s.addText("图：7 新工具 per-patient Fisher-Z 加权均值 + 95% CI。CI_lo>0 标 * = 统计显著正相关。", {
  x:0.55, y:6.75, w:6.25, h:0.3, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", margin:0 });
s.addShape(pres.shapes.RECTANGLE, { x:7.02, y:1.62, w:5.75, h:5.32, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
s.addImage({ path: FIG+"/fig_newtools_spearman_heatmap.png", x:7.1, y:1.72, w:5.6, h:5.1, sizing:{type:"contain", w:5.6, h:5.1} });
s.addText("图：7 新工具 x 3 聚合（max/mean/top3）Spearman 热图。* = p<0.05；红色=正相关，蓝色=负相关。", {
  x:7.02, y:6.75, w:5.75, h:0.3, fontFace:FB, fontSize:9, italic:true, color:C.muted, valign:"top", margin:0 });
pageno(s);

// ============================================================ 关键发现
s = pres.addSlide();
header(s, "关键发现", "5 条主要结论  数字来自 analysis/NEWTOOLS_ANALYSIS.md", C.teal);
var findings = [
  ["发现 1  新工具整体未破旧工具天花板",
   "新工具组 per-patient fisherz 均值 0.052，旧工具组 0.137。旧工具最强 PRIME 0.300 [0.056,0.511]；新工具最强 MHCflurry_affinity_neg 0.248 [0.003,0.464]（CI 勉强排 0）。全 17 工具中 CI_lo>0 的统计显著正相关仅 3 个：PRIME / IMPROVE / MHCflurry_affinity_neg。",
   C.teal],
  ["发现 2  netmhcpan_ba mean 聚合全场最强，但聚合敏感且 DTU pending",
   "mean 聚合 rho=+0.381 p=0.0003，AUC(mean,>10)=0.714——全场最强，但仅 mean 聚合触发，max/top3 均 n.s.，聚合高度敏感、不稳健。⚠️ 全部数字 pending_DTU_consent=True，对外前须 DTU 书面授权。",
   C.warn],
  ["发现 3  TSCAPE 全聚合一致显著负相关（方向待核）",
   "3 种聚合 rho 约 -0.23~-0.27，p 均<0.05；AUC 0.362（低于随机）。高度疑似分数语义反转（高分=低应答）或耐受性预测。⚠️ 守复现零偏离红线，未擅自取反；PPT 如实报负并标「方向待核」；需 verifier 回溯分数定义再定论。",
   C.crit],
  ["发现 4  MHCflurry_affinity_neg 聚合方向翻转，三聚合不一致",
   "max rho=+0.158(n.s.) / mean rho=-0.328(p=0.002) / top3 rho=+0.215(p=0.047)——三聚合方向不一致，对「取最强结合 vs 平均结合」高度敏感。引用时不能只引最好 p 值，须说明聚合依赖性。",
   C.warn],
  ["发现 5  Repitope（唯一 HLA-agnostic）AUC 0.620 排第四，但 fisherz 仍弱",
   "AUC 0.620 排全 17 工具第 4，per-patient fisherz 0.119（CI [-0.112, 0.338] 含 0）；数据最全（n=9，reinference_pending=False）。肽序列内在信号存在，但 CI 含 0，定量预测仍弱，HLA 信息仍重要。",
   C.sea],
];
var fy = 1.72, fh = 0.87, fgap = 0.06;
findings.forEach(function(f){
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:fy, w:11.9, h:fh, fill:{color:C.card}, line:{color:C.line,width:1}, shadow:sh() });
  s.addShape(pres.shapes.RECTANGLE, { x:0.7, y:fy, w:0.09, h:fh, fill:{color:f[2]} });
  s.addText(f[0], { x:0.9, y:fy+0.09, w:3.1, h:fh-0.18, fontFace:FH, fontSize:11, bold:true, color:f[2], valign:"middle", margin:0 });
  s.addText(f[1], { x:4.1, y:fy+0.09, w:8.35, h:fh-0.18, fontFace:FB, fontSize:9.8, color:C.ink, valign:"middle", lineSpacingMultiple:1.04, margin:0 });
  fy += fh + fgap;
});
s.addText("所有数字经 analysis/NEWTOOLS_ANALYSIS.md 核对（真源：metrics_ds2_16tools.csv + per_patient_spearman_16tools.csv，corrected-full 口径）。", {
  x:0.7, y:7.08, w:11.9, h:0.32, fontFace:FB, fontSize:9.5, italic:true, color:C.muted, margin:0 });
pageno(s);

// ============================================================ 结论 + 许可 Caveat
s = pres.addSlide();
s.background = { color: C.dark };
s.addShape(pres.shapes.RECTANGLE, { x:0, y:0, w:W, h:0.18, fill:{color:C.mint} });
s.addText("结论与许可 Caveat", { x:0.9, y:0.68, w:10, h:0.6, fontFace:FH, fontSize:30, bold:true, color:"FFFFFF", margin:0 });
// 左侧：整体结论
s.addText("整体结论", { x:0.9, y:1.52, w:5.6, h:0.38, fontFace:FH, fontSize:15, bold:true, color:C.mint, margin:0 });
s.addText([
  { text:"整体仍「普遍弱相关」——新工具未改变结论", options:{ bullet:{indent:14}, breakLine:true, color:C.mint, fontSize:13, bold:true, paraSpaceAfter:8 } },
  { text:"17 工具 per-patient fisherz 无一 >0.35（最高 PRIME 0.300），中位数约 0.12，全落「弱相关」区间", options:{ bullet:{indent:14}, breakLine:true, color:"FFFFFF", fontSize:12, paraSpaceAfter:6 } },
  { text:"无任何新工具实现「弱→中等」跨级提升", options:{ bullet:{indent:14}, breakLine:true, color:"FFFFFF", fontSize:12, paraSpaceAfter:6 } },
  { text:"新工具价值 = 方法学覆盖面：统计/HLA-agnostic/纯结合/提呈/LLM/迁移/多域 7 类范式全测过", options:{ bullet:{indent:14}, breakLine:true, color:"CADCFC", fontSize:11.5, paraSpaceAfter:6 } },
  { text:"把「现有工具难做强弱定量」钉得更死 → 直接服务 QuantImmune 自研算法立项依据", options:{ bullet:{indent:14}, color:C.mint, fontSize:13, bold:true } },
], { x:0.9, y:2.0, w:5.85, h:4.7, fontFace:FB, valign:"top", margin:0 });
// 右侧：许可 caveat
s.addText("⚠️ 许可 Caveat（对外前必处理）", { x:7.05, y:1.52, w:5.7, h:0.38, fontFace:FH, fontSize:14, bold:true, color:"F2C2C7", margin:0 });
var cavItems = [
  ["netMHCpan-BA（DTU 禁再分发）",
   "全部 34247 行标 pending_DTU_consent=True。mean 聚合最强信号 rho=+0.381 暂不可对外引用。论文/PPT 含其数字前需取 Technical University of Denmark 书面同意（投稿阶段处理）。",
   "F2C2C7"],
  ["T-SCAPE（CC-BY-NC-ND 4.0）",
   "非商业 + 禁演绎。报告数字须标注来源（署名）；不得分发修改版代码/权重。⚠️ 全聚合显著负相关（AUC 0.362）方向待 verifier 诊断，使用前须确认分数语义是否反转。",
   "F9E0E4"],
  ["其余 5 工具（许可允许发数字）",
   "BigMHC（学术非商用 ✅）  CNNeo（MIT ✅）  MHCflurry（Apache-2.0 ✅）  IEDB_Calis（NPOSL-3.0 ✅）  Repitope（MIT ✅）——无 DTU 禁令，数字可自由发布。",
   "CADCFC"],
];
var cy3 = 2.0;
cavItems.forEach(function(c){
  s.addShape(pres.shapes.RECTANGLE, { x:7.05, y:cy3, w:5.7, h:1.44, fill:{color:"123F4B"}, line:{color:"1C5563",width:1} });
  s.addShape(pres.shapes.RECTANGLE, { x:7.05, y:cy3, w:0.07, h:1.44, fill:{color:C.warn} });
  s.addText(c[0], { x:7.26, y:cy3+0.1, w:5.3, h:0.36, fontFace:FH, fontSize:11.5, bold:true, color:"FFFFFF", margin:0 });
  s.addText(c[1], { x:7.26, y:cy3+0.5, w:5.3, h:0.9, fontFace:FB, fontSize:9.5, color:c[2], valign:"top", lineSpacingMultiple:1.04, margin:0 });
  cy3 += 1.54;
});
s.addText("数字真源：analysis/NEWTOOLS_ANALYSIS.md（metrics_ds2_16tools.csv + per_patient_spearman_16tools.csv，corrected-full 口径）。reinference_pending 工具（BigMHC/CNNeo/IEDB_Calis/MHCflurry/Repitope）Phase B 重推理后数字可能微变，方向不变。", {
  x:0.9, y:7.05, w:11.5, h:0.38, fontFace:FB, fontSize:9, italic:true, color:"6E9AA1", margin:0 });
pageno(s);

// ---------- write ----------
pres.writeFile({ fileName: "D:/YJ-Agent/project/meeting/QuantImmuBench/QuantImmuBench_新工具横评_2026-06-27.pptx" })
  .then(function(f){ console.log("WROTE", f); })
  .catch(function(e){ console.error("ERR", e); process.exit(1); });
