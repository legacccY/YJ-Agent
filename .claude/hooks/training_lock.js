#!/usr/bin/env node
// PreToolUse(Bash) hook: 全局训练互斥锁。落实「训练串行」红线，跨所有终端窗口。
// 协议：主线启训前先写 .portfolio/locks/training.lock {status:"starting",...}，
//       本 hook 见 starting → 放行并翻成 running（持锁者自己的启动）；
//       他窗见 running → 阻断（exit 2）。完成后主线删锁。
// 非训练命令一律放行。陈旧 running 锁（进程已死）由人工/主线清。

const fs = require('fs');
const path = require('path');
const { log } = require('./_friction.js');

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', c => { input += c; });
process.stdin.on('end', () => {
  let data;
  try { data = JSON.parse(input); } catch (e) { process.exit(0); }
  if ((data.tool_name || '') !== 'Bash') process.exit(0);

  const cmd = (data.tool_input && data.tool_input.command) || '';
  // 训练命令识别（保守）：Start-Process+train / sbatch / python+train.py / run-experiment
  const isTraining =
    (/Start-Process/i.test(cmd) && /train/i.test(cmd)) ||
    /\bsbatch\b/i.test(cmd) ||
    (/python/i.test(cmd) && /train[\w-]*\.py/i.test(cmd)) ||
    /run[_-]experiment/i.test(cmd);
  if (!isTraining) process.exit(0);

  const cwd = (data.cwd || process.cwd()).replace(/\\/g, '/');
  // 定位 .portfolio（向上找含 .portfolio 的目录；默认 D:/YJ-Agent）
  const root = cwd.includes('YJ-Agent') ? cwd.slice(0, cwd.indexOf('YJ-Agent') + 'YJ-Agent'.length) : 'D:/YJ-Agent';
  const lockPath = path.join(root, '.portfolio', 'locks', 'training.lock');

  let lock = null;
  try { lock = JSON.parse(fs.readFileSync(lockPath, 'utf8')); } catch (e) { lock = null; }

  if (!lock) process.exit(0); // 无锁 → 放行（注意：规范要求启训前应先持锁）

  if (lock.status === 'starting') {
    // 持锁者自己的启动 → 放行并翻成 running
    try {
      lock.status = 'running';
      lock.running_since = new Date().toISOString();
      fs.writeFileSync(lockPath, JSON.stringify(lock, null, 2));
    } catch (e) {}
    process.exit(0);
  }

  if (lock.status === 'running') {
    log('training-lock-block', `${lock.project || '?'}@${lock.window_id || '?'}`);
    process.stderr.write(
      `🔒 训练锁被持有：window=${lock.window_id || '?'} project=${lock.project || '?'} ` +
      `host=${lock.host || '?'} since=${lock.running_since || lock.start_ts || '?'}。\n` +
      `串行红线：同一时刻只许一个训练（跨窗口 + 本地 GPU + HPC 配额）。\n` +
      `→ 等其完成（完成后删 .portfolio/locks/training.lock），或确认是陈旧锁（进程已死）再人工清。\n`
    );
    process.exit(2);
  }

  process.exit(0);
});
