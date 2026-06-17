#!/usr/bin/env node
// UserPromptSubmit hook: 指令像"设计实验/写实验代码/分析结果"却可能主线串行硬扛时，
// 注入提醒派对应 agent（planner/coder/analyst）。直击"低效惯性"——把 CLAUDE.md 已写的
// 并行规矩变成每次自动触发。静默除非命中；纯提醒，exit 0。

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', c => { input += c; });
process.stdin.on('end', () => {
  let data;
  try { data = JSON.parse(input); } catch (e) { process.exit(0); }
  const cwd = (data.cwd || '').replace(/\\/g, '/');
  if (!cwd.includes('YJ-Agent')) process.exit(0);

  const p = String(data.prompt || '');
  let out = '';

  // 泛指令（无关键词的"开始工作/继续/干活"）→ 提醒主线按项目状态自动路由流水线，别串行单干
  const vagueStart = /^(\s*)(开始(工作|干活|吧)?|继续|接着(干|做)|干活(吧)?|推进(一下)?|开工|往下走|往前推|go|start|继续推进|接着来)(\s|$|，|。|！|\.|!)/i.test(p)
    || /(开始工作|继续干|接着干|干活吧|推进一下|往下推进)/i.test(p);
  if (vagueStart && p.length < 40) {
    out += '[自动路由] 泛指令 → 别主线埋头串行。先读 registry.phase + 项目 LOG 最新 entry + log/experiment_state.json 定位流水线当前棒 → 主动派对应 agent/skill（researcher/planner/coder/analyst/writer/reviewer 或 /paper-scout、/design-experiment、/experiment-cycle、/analyze-results、/stage-gate）→ 拍板点停。默认动作=派编队不是自己干。\n';
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
  // 完整一轮实验 → experiment-cycle
  if (/(跑一轮|完整.*实验|一整套实验|推进.*阶段.*实验|设计并.*实现|从设计到)/i.test(p)) {
    out += '[编排 /experiment-cycle] 完整一轮实验 → 一键 /experiment-cycle <project> 自动 planner→coder→🛑拍板→跑→analyst→verifier，人只在跑训练拍板点介入。\n';
  }
  // GitHub 发布/拉取/维护 → gh-flow（提 github/开源/推仓库/拉 repo/issue 即软触发）
  if (/(github|开源|推(送|上|到).*(仓库|repo|远端)|发布.*(仓库|repo|项目)|准备开源|建.*(仓库|repo)|克隆|clone|拉.*(repo|仓库|代码进来)|pull request|提.*pr|按.*(issue|review).*修|维护.*(repo|仓库)|隐私.*(扫|审|检查)|repo)/i.test(p)) {
    out += '[编排 /gh-flow] GitHub 活别主线手撸 → 一键 /gh-flow publish <路径> | pull <repo-url> | maintain <owner/repo>，派 gh-publisher(sonnet) 跑隐私扫描+顶级开源骨架+许可证合规+按 review 修 bug。对外 push/repo create/回 issue 仍主线串行拍板，公开 repo 与 private YJ-Agent 隔离。\n';
  }

  if (out) {
    out += '（八角色全闭环见 CLAUDE.md / PROJECT_LIFECYCLE.md。训练启停仍主线串行红线，agent 不碰。）\n';
    process.stdout.write(out);
  }
  process.exit(0);
});
