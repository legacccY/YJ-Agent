#!/usr/bin/env node
// PreToolUse(Bash) hook: 按卡训练调度（schema v2，取代旧全局单锁）。
// 容量：local=1 卡（RTX4070 8GB）、hpc=4 卡（gpu4090 qos 4gpus）。
// 协议：主线启训前先 `python tools/gpu_slot.py request <project> <host> <gpus>`，
//       够卡 -> 写 active starting 条目（GO）；卡满 -> 入 queue（QUEUED，不启）。
// 本 hook 见训练命令：
//   - 找到对应 host 的 starting 条目 -> 翻 running、放行（主线自己的启动）。
//   - 没有 starting 条目 -> 阻断，提示先 request 申请卡槽（防裸启绕过记账）。
// 多任务可共存（不同卡），绝不挤正在跑的。非训练命令一律放行。

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
  // 洞 B 修：只读查看命令按「首 token」判（剥掉前缀 `cd ... &&` / env 赋值），
  // 命令里把 sbatch/Start-Process 当搜索词提到不再误伤（真启动以 python/Start-Process/sbatch 开头，不以 grep/cat 开头）。
  const effCmd = cmd.replace(/^\s*cd\s+[^&|;]+(?:&&|;)\s*/i, '').trim();
  const firstTok = ((effCmd.split(/[\s|;&]+/)[0]) || '').replace(/.*[/\\]/, '');
  const isReadOnlyViewer = /^(grep|rg|egrep|fgrep|wc|printf|echo|cat|ls|stat|md5sum|sha256sum|diff|head|tail|find|sed|awk|tasklist)$/i.test(firstTok);
  // 非执行命令豁免：py_compile / pytest / lint / 版本帮助 + 调度器自身命令 + SFTP/scp 传输 + 只读查看
  const isCompileOrTest = /py_compile|pyflakes|flake8|\bpytest\b|-m\s+pytest|--version|--help|gpu_slot\.py/i.test(cmd)
    || /\bsftp\b|\bscp\b/i.test(cmd)
    || isReadOnlyViewer;
  // 洞 A 修：训练识别不止文件名 train*.py——扩到 probe/sweep/pilot/capacity/finetune/pretrain/mqar/experiment
  // 这类「训到收敛/扫描」脚本名（防 mqar_capacity_probe.py 之类绕过）；--smoke/--dry-run/test_ 仍放行（tiny 烟测）。
  const isSmoke = /--smoke|--dry[-_]?run|\btest_|tests\//i.test(cmd);
  const isTraining = !isCompileOrTest && !isSmoke && (
    (/Start-Process/i.test(cmd) && /\b(train|python)\b/i.test(cmd)) ||
    /\bsbatch\b/i.test(cmd) ||
    (/\bpython\b/i.test(cmd) && /[\w./-]*(train|sweep|probe|pilot|capacity|finetune|pretrain|mqar|experiment)[\w-]*\.py/.test(cmd)) ||
    /run[_-]experiment/i.test(cmd)
  );
  if (!isTraining) process.exit(0);

  // host 推断：sbatch -> hpc；本地 Start-Process/python -> local
  const host = /\bsbatch\b/i.test(cmd) ? 'hpc' : 'local';

  const cwd = (data.cwd || process.cwd()).replace(/\\/g, '/');
  const root = cwd.includes('YJ-Agent') ? cwd.slice(0, cwd.indexOf('YJ-Agent') + 'YJ-Agent'.length) : 'D:/YJ-Agent';
  const lockPath = path.join(root, '.portfolio', 'locks', 'training.lock');

  let lock = null;
  try { lock = JSON.parse(fs.readFileSync(lockPath, 'utf8')); } catch (e) { lock = null; }

  // 无锁文件 / 旧 schema：放行但提醒走调度器（兼容过渡，不硬卡）
  if (!lock || !Array.isArray(lock.active)) {
    process.stderr.write('⚠️ 未见 schema v2 卡槽记录。建议先 `python tools/gpu_slot.py request <project> <host> <gpus>` 申请卡槽（按卡调度，卡满自动排队）。本次放行。\n');
    process.exit(0);
  }

  const CAP = lock.capacity || { local: 1, hpc: 4 };
  const usedOn = h => lock.active
    .filter(j => j.host === h && (j.status === 'running' || j.status === 'starting'))
    .reduce((s, j) => s + (parseInt(j.gpus, 10) || 1), 0);

  // 找 starting 条目（主线刚 request 出来的）。sbatch 无法从命令区分 gpu4090(hpc)/gpu3090(hpc3090)，
  // 故接受任一 HPC host 的 starting（gpu_slot request 已记正确 host；local 仍只认 local）。
  const acceptHosts = host === 'local' ? ['local'] : ['hpc', 'hpc3090'];
  const starting = lock.active.filter(j => acceptHosts.includes(j.host) && j.status === 'starting');

  if (starting.length > 0) {
    // 主线自己的启动 -> 翻最新一个 starting 为 running，放行
    starting.sort((a, b) => String(a.start_ts).localeCompare(String(b.start_ts)));
    const j = starting[starting.length - 1];
    j.status = 'running';
    j.running_since = new Date().toISOString();
    try { fs.writeFileSync(lockPath, JSON.stringify(lock, null, 2)); } catch (e) {}
    process.stderr.write(`✅ 卡槽放行：${j.project || '?'} @${j.host} 占 ${j.gpus || 1} 卡（${j.host} 用 ${usedOn(j.host)}/${CAP[j.host] || '?'}）。完成后 \`gpu_slot.py release ${j.id}\`。\n`);
    process.exit(0);
  }

  // 没有 starting 条目 -> 没走调度器申请，阻断
  log('training-lock-block', `no-slot-request@${host}`);
  const f = (CAP[host] || 0) - usedOn(host);
  process.stderr.write(
    `🔒 未申请卡槽就启训（${host} 当前空闲 ${f}/${CAP[host] || '?'} 卡）。\n` +
    `按卡调度协议：先 \`python tools/gpu_slot.py request <project> ${host} <gpus> [note]\`\n` +
    `  够卡 -> 打印 GO，再启动（本 hook 自动放行）；卡满 -> 打印 QUEUED（已排队，别裸启，等 release 自动取出）。\n` +
    `绝不挤正在跑的任务。\n`
  );
  process.exit(2);
});
