#!/usr/bin/env node
// Stop hook: 一轮收尾时，若训练 state.json 已 status:"done" 但本 run 还没解读 → 提醒 /analyze-results。
// 防"结果跑完烂在硬盘没人解读"。loop-safe：stop_hook_active 时跳过；
// 用 .portfolio/.analyzed_runs.json 记已提醒过的 run_name，同一 run 不反复 nag。

const fs = require('fs');
const path = require('path');

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

  // 读训练状态
  let st;
  try { st = JSON.parse(fs.readFileSync(path.join(root, 'log', 'experiment_state.json'), 'utf8')); } catch (e) { process.exit(0); }
  if (!st || st.status !== 'done') process.exit(0);

  const run = (st.experiment && st.experiment.run_name) || 'unknown_run';

  // 已提醒过这个 run？
  const memFile = path.join(root, '.portfolio', '.analyzed_runs.json');
  let done = [];
  try { done = JSON.parse(fs.readFileSync(memFile, 'utf8')).notified || []; } catch (e) {}
  if (done.includes(run)) process.exit(0);

  done.push(run);
  try { fs.writeFileSync(memFile, JSON.stringify({ notified: done.slice(-50), ts: new Date().toISOString() })); } catch (e) {}

  const best = (st.checkpoint && st.checkpoint.best_path) || '';
  process.stderr.write(
    `[结果待解读] 训练 ${run} 已完成（status:done${best ? '，best: ' + best : ''}）但本会话还没解读。\n` +
    `跑 /analyze-results <project> 让 analyst 算趋势/出图/对判据 ✅❌ + 建议下一步，再 /checkpoint 落档。别让结果烂在硬盘。\n`
  );
  process.exit(2);
});
