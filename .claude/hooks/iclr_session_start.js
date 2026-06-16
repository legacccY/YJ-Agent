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

  // 训练锁
  try {
    const lock = JSON.parse(fs.readFileSync(path.join(root, '.portfolio', 'locks', 'training.lock'), 'utf8'));
    lines.push(`⚠️ 训练锁持有中：${lock.project || '?'} (${lock.status || '?'}, win ${lock.window_id || '?'}) — 串行红线，勿另启训练。`);
  } catch (e) {
    lines.push('训练锁空闲。');
  }

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
