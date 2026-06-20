#!/usr/bin/env node
// SessionStart hook: YJ-Agent 科研组合台开门提示（portfolio-aware）。
// 读 .portfolio/registry.json + 训练锁，报当前论文组合 + 锁状态 + 读档/caveman 规则。
// 非 YJ-Agent 目录静默。

const fs = require('fs');
const path = require('path');

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', () => {
  let data;
  try { data = JSON.parse(input); } catch (e) { process.exit(0); }
  const cwd = (data.cwd || '').replace(/\\/g, '/');
  if (!cwd.includes('YJ-Agent')) process.exit(0);

  const root = cwd.slice(0, cwd.indexOf('YJ-Agent') + 'YJ-Agent'.length);
  let lines = [];
  lines.push('[YJ-Agent 组合台] 开门三步：①读 PORTFOLIO + 各项目最新状态，一句话报每篇进度 ②主动问用户「本窗口做哪篇论文？」 ③认领 .portfolio/locks/<proj>.claim 再深读该项目。');

  // 项目组合
  try {
    const reg = JSON.parse(fs.readFileSync(path.join(root, '.portfolio', 'registry.json'), 'utf8'));
    const ps = reg.projects || {};
    const brief = Object.keys(ps).map(k => `${k}:${ps[k].status}(P${ps[k].priority})`).join(' | ');
    if (brief) lines.push('在跑：' + brief + '。');
  } catch (e) {}

  // 本窗口归属推断 + 项目读档清单（claim-aware，省得 agent 漏读档）
  // 取最近修改的 *.claim（排除归档/training.lock）→ 映射该项目入口读档链 → 直接注入确切路径。
  try {
    const locksDir = path.join(root, '.portfolio', 'locks');
    const reg = JSON.parse(fs.readFileSync(path.join(root, '.portfolio', 'registry.json'), 'utf8'));
    const projHome = {};
    Object.keys(reg.projects || {}).forEach(k => { projHome[k] = (reg.projects[k].home || '').replace(/\/$/, ''); });

    // 历史特例读档链（其余走标准 schema）
    const SPECIAL = {
      gdn2vessel: h => [`${h}/00_README.md`, `${h}/STORY_FRAMEWORK.md`, `${h}/ACCEPTANCE_CRITERIA.md`, `${h}/PLAN/MASTER_PLAN.md`, `${h}/PROJECT_LOG.md（最新 entry）`],
      iclr: h => [`${h}/README.md`, `${h}/STORY_FRAMEWORK.md`, `${h}/ACCEPTANCE_CRITERIA.md`, `${h}/PROJECT_LOG.md（最新 entry）`],
      'nca-jepa': h => [`${h}/README.md`, `${h}/01_创新计划`, `${h}/02_理论框架`, `${h}/04_LOG.md（最新 entry）`],
      bmvc: () => ['🔒 BMVC 已封印：只读 meeting/BMVC/SUBMITTED.md，不动手'],
    };
    const standard = h => [`${h}/00_README.md`, `${h}/01_STORY.md`, `${h}/02_ACCEPTANCE.md`, `${h}/04_LOG.md（最新 entry）`];

    const claims = fs.readdirSync(locksDir)
      .filter(f => f.endsWith('.claim') && !f.startsWith('_archived'))
      .map(f => ({ proj: f.replace(/\.claim$/, ''), mtime: fs.statSync(path.join(locksDir, f)).mtimeMs }))
      .filter(c => projHome[c.proj] != null)   // 只认 registry 里有的项目
      .sort((a, b) => b.mtime - a.mtime);

    if (claims.length) {
      const top = claims[0];
      const h = projHome[top.proj];
      const buildList = SPECIAL[top.proj] || standard;
      const readlist = buildList(h);
      const others = claims.slice(1, 4).map(c => c.proj).join(', ');
      lines.push(`📂 本窗口大概率=${top.proj}（最近认领的 claim）。**先确认归属，再立即按此链读档**：${readlist.join(' → ')}。`);
      if (others) lines.push(`   （其他活跃 claim：${others}——若本窗其实做别篇，读那篇的 00_README 链。）`);
    }
  } catch (e) {}

  // 训练锁
  try {
    const lock = JSON.parse(fs.readFileSync(path.join(root, '.portfolio', 'locks', 'training.lock'), 'utf8'));
    lines.push(`⚠️ 训练锁持有中：${lock.project || '?'} (${lock.status || '?'}, win ${lock.window_id || '?'}) — 串行红线，勿另启训练。`);
  } catch (e) {
    lines.push('训练锁空闲。');
  }

  // 在跑的 Conductor 阶段 DAG（每窗必报，不靠关键词——最可靠的续跑触发）
  try {
    const pdir = path.join(root, '.portfolio', 'pipelines');
    const pfiles = fs.readdirSync(pdir).filter(f => f.endsWith('.json'));
    const briefs = [];
    pfiles.forEach(f => {
      try {
        const dag = JSON.parse(fs.readFileSync(path.join(pdir, f), 'utf8'));
        const ns = dag.nodes || [];
        const done = ns.filter(n => n.status === 'done' || n.status === 'skipped').length;
        const doneIds = new Set(ns.filter(n => n.status === 'done' || n.status === 'skipped').map(n => n.id));
        const ready = ns.filter(n => n.status === 'pending' && (n.deps || []).every(d => doneIds.has(d)));
        const running = ns.filter(n => n.status === 'running');
        let head;
        if (ready.some(n => n.gate)) head = `🛑拍板点 ${ready.filter(n => n.gate)[0].id}`;
        else if (ready.length) head = '下一棒 ' + ready.map(n => `${n.id}(${n.agent})`).join(',');
        else if (running.length) head = '在跑 ' + running.map(n => `${n.id}@${n.owner || '?'}`).join(',');
        else if (done === ns.length) head = '✓ 全完成→可收尾清扫(归档图+清_scratch)';
        else head = '查 pipeline.py next';
        briefs.push(`${dag.project} ${done}/${ns.length} → ${head}`);
      } catch (e) {}
    });
    if (briefs.length) {
      lines.push('🎼 在跑阶段 DAG（Conductor）：' + briefs.join(' ｜ ') + '。续跑=说人话「推进<项目>」我读图接着干（状态在 .portfolio/pipelines/，不靠 context）。一篇多窗→各窗认领不同节点(claim)，汇到 integrate 集成烟测才放行训练。');
    }
  } catch (e) {}

  lines.push('规则：进项目先读其 00_README/STORY+ACCEPTANCE；数字 Bash/Grep 核 csv 不信 Read；BMVC 封印。');
  lines.push('Caveman 仅内部沟通/对话；写 tex/正文/rebuttal 一律 OFF（hook 会提醒）。');
  lines.push('多窗口：写项目前认领 .portfolio/locks/<proj>.claim；训练前持 training.lock。');

  // 自主运行 + 拍板点（默认一直跑；规范见 PROJECT_LIFECYCLE）
  lines.push('🤖 默认自主一直跑，只在拍板点停（训练/HPC启动·新项目立项·投稿/force push·偏离STORY/改阈值·gate FAIL放行·危险删除·大额花费）。SOP+细则见 project/PROJECT_LIFECYCLE.md。');

  // 自优化：friction 待处理 → 提示 /optimize
  try {
    const fric = fs.readFileSync(path.join(root, '.portfolio', 'friction.jsonl'), 'utf8')
      .split('\n').filter(Boolean);
    if (fric.length) {
      const types = {};
      fric.forEach(l => { try { const t = JSON.parse(l).type; types[t] = (types[t] || 0) + 1; } catch (e) {} });
      const brief = Object.keys(types).map(k => `${k}×${types[k]}`).join(' ');
      lines.push(`🔧 摩擦信号待处理 ${fric.length} 条（${brief}）→ 跑 /optimize 聚类自优化（反复出现的才动）。`);
    }
  } catch (e) {}

  process.stdout.write(lines.join('\n') + '\n');
  process.exit(0);
});
