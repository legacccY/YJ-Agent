#!/usr/bin/env node
// Stop hook: 一轮工作收尾时，若改动量大但没动项目 LOG → 提醒写进度 + 考虑 /stage-gate。
// loop-safe：stop_hook_active 时不再触发；用 .portfolio/.stage_state.json 记上次提醒时的改动数，
// 仅当改动数比上次提醒"又增长 ≥ 阈值"时再提，避免反复阻断 Stop。

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const THRESHOLD = 6; // 改动文件数增量阈值

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', c => { input += c; });
process.stdin.on('end', () => {
  let data;
  try { data = JSON.parse(input); } catch (e) { process.exit(0); }
  if (data.stop_hook_active) process.exit(0); // 防 Stop 循环

  const cwd = (data.cwd || '').replace(/\\/g, '/');
  if (!cwd.includes('YJ-Agent')) process.exit(0);
  const root = cwd.slice(0, cwd.indexOf('YJ-Agent') + 'YJ-Agent'.length);

  let changed = [];
  try {
    const out = execSync('git -C "' + root + '" status --porcelain', { encoding: 'utf8', timeout: 4000 });
    changed = out.split('\n').map(l => l.slice(3).trim()).filter(Boolean);
  } catch (e) { process.exit(0); }

  // 只数项目源文件改动；排除 _scratch / 锁 / state
  const proj = changed.filter(f => /project\//.test(f) && !/(\_scratch\/|\.portfolio\/|sentinels\/)/.test(f));
  const count = proj.length;

  const stateFile = path.join(root, '.portfolio', '.stage_state.json');
  let last = 0;
  try { last = JSON.parse(fs.readFileSync(stateFile, 'utf8')).last_nudge_count || 0; } catch (e) {}

  if (count - last < THRESHOLD) process.exit(0);

  // 这批改动里有没有动 LOG？
  const touchedLog = proj.some(f => /(PROJECT_LOG|04_LOG|_LOG)\.md$/.test(f));

  try { fs.writeFileSync(stateFile, JSON.stringify({ last_nudge_count: count, ts: new Date().toISOString() })); } catch (e) {}

  let msg = `[阶段进度] 本轮已改 ${count} 个项目文件`;
  if (!touchedLog) msg += '，但没写项目 LOG。先在对应 PROJECT_LOG / 04_LOG 补一条进度 entry（完成/待续/命中率回退），再继续。';
  else msg += '。';
  msg += '\n半天级大阶段若已收口 → 跑 /stage-gate <project> 让 opus 严审是否达 ACCEPTANCE 标准。';

  // 摩擦累积 → 提示自优化
  try {
    const fric = fs.readFileSync(path.join(root, '.portfolio', 'friction.jsonl'), 'utf8').split('\n').filter(Boolean);
    if (fric.length >= 3) msg += `\n🔧 摩擦已累积 ${fric.length} 条 → 跑 /optimize 自优化协作流程。`;
  } catch (e) {}

  process.stderr.write(msg + '\n');
  process.exit(2);
});
