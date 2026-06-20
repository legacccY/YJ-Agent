#!/usr/bin/env node
// UserPromptSubmit hook: 指令像"设计实验/写实验代码/分析结果"却可能主线串行硬扛时，
// 注入提醒派对应 agent（planner/coder/analyst）。直击"低效惯性"——把 CLAUDE.md 已写的
// 并行规矩变成每次自动触发。静默除非命中；纯提醒，exit 0。

const fs = require('fs');
const path = require('path');

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', c => { input += c; });
process.stdin.on('end', () => {
  let data;
  try { data = JSON.parse(input); } catch (e) { process.exit(0); }
  const cwd = (data.cwd || '').replace(/\\/g, '/');
  if (!cwd.includes('YJ-Agent')) process.exit(0);
  const root = cwd.slice(0, cwd.indexOf('YJ-Agent') + 'YJ-Agent'.length);

  const p = String(data.prompt || '');
  let out = '';

  // 泛指令（无关键词的"开始工作/继续/干活"）→ 提醒主线按项目状态自动路由流水线，别串行单干
  const vagueStart = /^(\s*)(开始(工作|干活|吧)?|继续|接着(干|做)|干活(吧)?|推进(一下)?|开工|往下走|往前推|go|start|继续推进|接着来|往下做|接着推)(\s|$|，|。|！|\.|!)/i.test(p)
    || /(开始工作|继续干|接着干|干活吧|推进一下|往下推进|把这篇.*(推|做|干).*(下去|完)|往下做|接着推)/i.test(p);
  if (vagueStart && p.length < 40) {
    // 有现成 pipeline DAG → 优先续跑 conductor（状态在文件里，抗 context 压缩/跨窗）
    let pipes = [];
    try {
      pipes = fs.readdirSync(path.join(root, '.portfolio', 'pipelines'))
        .filter(f => f.endsWith('.json')).map(f => f.replace('.json', ''));
    } catch (e) {}
    if (pipes.length) {
      out += `[自动路由→conductor] 在跑的阶段 DAG：${pipes.join(', ')}。泛指令=续跑编排器别另起：\`python tools/pipeline.py next <project>\` 看卡哪棒 → 按 /conductor 驱动（ready→派编队→done 解锁→gate 停）。状态在 .portfolio/pipelines/，跨窗/压缩照样续。\n`;
    } else {
      out += '[自动路由] 泛指令 → 别主线埋头串行。多阶段连续推进 → 起 /conductor <project>（读 phase 建持久 DAG，自动一棒接一棒派编队、拍板点停、可恢复）。单棒活按状态派对应 agent/skill（researcher/planner/skeptic/coder/analyst/writer/reviewer 或 /paper-scout、/design-experiment、/experiment-cycle、/analyze-results、/stage-gate）→ 拍板点停。默认=派编队不是自己干。\n';
    }
  }

  // 协调/多窗/排活/集成缝类 → 用 Conductor，禁止手搓方案（冷窗口防再造轮子）
  if (/(多.*窗|一篇.*窗|多个窗|协同|分工|怎么.*(组织|安排|协调|编排)|多阶段|谁先谁后|阶段.*(排|安排|顺序)|集成.*(缝|没.*测|怎么不.*崩)|pytest.*(真验|hpc|不够)|并行.*(干|做|推).*(一篇|同.*项目))/i.test(p)) {
    out += '[用 Conductor 别手搓] 协调/多窗/多阶段/集成缝 = Conductor 已建的职责。第一动作：`python tools/pipeline.py list` 看在跑的图 → `next/status <project>` 续，没有且活够大就 `/conductor <project>` 建图。**禁止从零手工设计协调方案**（memory [[reference_conductor_pipeline]]，正是它要替代的）。集成缝→模板自带 integrate 真烟测闸。问「怎么用」就真用一次，别再画架构。\n';
  }

  // 设计实验类 → planner
  if (/(设计.*实验|实验.*设计|消融|ablation|实验矩阵|跑哪些实验|该跑什么|怎么验证|验证.*claim|baseline 选|对照组|实验方案)/i.test(p)) {
    out += '[派 planner] 设计实验别主线串行拍脑袋 → 派 planner(opus) 出实验矩阵（对齐 ACCEPTANCE 判据），或一键 /design-experiment <project>。\n';
  }
  // 写实验代码类 → coder
  if (/(写.*(训练|脚本|代码|model|loss|dataloader|dataset|预处理|增强)|实现.*(model|loss|架构|网络|模块)|改.*(训练脚本|dataloader|config 逻辑)|加.*(数据增强|augment)|修.*(报错|bug|训练))/i.test(p)) {
    out += '[派 coder] 写/改实验代码别主线扛 → 派 coder(sonnet)（Windows 规范内嵌，自测 pytest，不启训练），多个独立 config 可并行多 coder。\n';
  }
  // 分析结果类 → analyst
  if (/(分析.*(结果|实验|数据)|跑完.*看|结果.*说明|画.*(曲线|图|loss|指标)|这.*消融.*说明|解读.*结果|trend|趋势)/i.test(p)) {
    out += '[派 analyst] 解读结果别主线 Read csv 凭印象 → 派 analyst(sonnet) 算趋势/出图/找 pattern（禁 Read csv 下结论），或一键 /analyze-results <project>。\n';
  }
  // 红队/批判/立项前提 → skeptic
  if (/(红队|批判|devil|质疑.*(设计|前提|claim|立项)|攻一下|找致命伤|这.*(立项|方向|假设).*(行不行|靠谱|站得住|可行)|混杂|confound|baseline.*(对不对|选错)|claim.*(站得住|逻辑|成立)|定.*headline.*前)/i.test(p)) {
    out += '[派 skeptic] 执行前红队别主线自己说服自己 → 派 skeptic(opus) 攻立项前提/实验设计/claim 逻辑（severity-gated，0 致命即放行不卡流程，每条攻击带出路）。区别 reviewer（事后审成稿）。\n';
  }
  // 完整一轮实验 → experiment-cycle
  if (/(跑一轮|完整.*实验|一整套实验|推进.*阶段.*实验|设计并.*实现|从设计到)/i.test(p)) {
    out += '[编排 /experiment-cycle] 完整一轮实验 → 一键 /experiment-cycle <project> 自动 planner→coder→🛑拍板→跑→analyst→verifier，人只在跑训练拍板点介入。\n';
  }
  // GitHub 发布/拉取/维护 → gh-flow（提 github/开源/推仓库/拉 repo/issue 即软触发）
  if (/(github|开源|推(送|上|到).*(仓库|repo|远端)|发布.*(仓库|repo|项目)|准备开源|建.*(仓库|repo)|克隆|clone|拉.*(repo|仓库|代码进来)|pull request|提.*pr|按.*(issue|review).*修|维护.*(repo|仓库)|隐私.*(扫|审|检查)|repo)/i.test(p)) {
    out += '[编排 /gh-flow] GitHub 活别主线手撸 → 一键 /gh-flow publish <路径> | pull <repo-url> | maintain <owner/repo>，派 gh-publisher(sonnet) 跑隐私扫描+顶级开源骨架+许可证合规+按 review 修 bug。对外 push/repo create/回 issue 仍主线串行拍板，公开 repo 与 private YJ-Agent 隔离。\n';
  }

  if (out) {
    out += '（九角色全闭环见 CLAUDE.md / PROJECT_LIFECYCLE.md。训练启停仍主线串行红线，agent 不碰。）\n';
    process.stdout.write(out);
  }
  process.exit(0);
});
