#!/usr/bin/env node
// Stop hook: 收尾时若根目录/根 _scratch 散落文件数超阈值 → 提醒跑 /tidy scan。
// 轻量、非阻断、loop-safe：用 .portfolio/.hygiene_state.json 记上次提醒时的散落数，
// 仅当散落数比上次"又增长 ≥ 阈值"时再提，避免反复打断 Stop。
// 与 stage_progress.js 同模式。best-effort：任何失败静默 exit 0。

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const THRESHOLD = 8;   // 根目录散落文件数阈值
const GROWTH = 5;      // 相比上次提醒的增量阈值

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

  // 数根目录散落物：_scratch_*.py / tmp_*.py / *captcha*.png / test_write* / 乱码名 / nul / =*
  let count = 0;
  let samples = [];
  try {
    const names = fs.readdirSync(root);
    for (const n of names) {
      let hit = false;
      if (/^_scratch_.*\.(py|sh)$/.test(n)) hit = true;
      else if (/^tmp_.*\.(py|txt)$/.test(n)) hit = true;
      else if (/captcha.*\.png$/i.test(n)) hit = true;
      else if (/^test_write/.test(n)) hit = true;
      else if (/^nul$/.test(n) || /^=/.test(n)) hit = true;
      else if (/C:Users|AppDataLocalTemp/.test(n)) hit = true; // 乱码路径当文件名
      if (hit) { count++; if (samples.length < 4) samples.push(n); }
    }
  } catch (e) { process.exit(0); }

  if (count < THRESHOLD) process.exit(0);

  const stateFile = path.join(root, '.portfolio', '.hygiene_state.json');
  let last = 0;
  try { last = JSON.parse(fs.readFileSync(stateFile, 'utf8')).last_nudge_count || 0; } catch (e) {}
  if (count - last < GROWTH && last >= THRESHOLD) process.exit(0);

  try { fs.writeFileSync(stateFile, JSON.stringify({ last_nudge_count: count, ts: new Date().toISOString() })); } catch (e) {}

  process.stderr.write(
    `[产物散落] 根目录已积 ${count} 个散落文件（如 ${samples.join(', ')} …）。\n` +
    `跑 /tidy scan root 让 custodian 扫一遍 → pointer-aware 归档清单（被读档链引用的不动，归档可逆）。收工前清一清免得越攒越乱。\n`
  );
  process.exit(2);
});
