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
  // 纯 CPU 分析/出图/交付脚本豁免：这类产出图表/表格/汇总/合并，从不占 GPU，
  // 却被通用词 sweep/experiment/probe 误判成训练（实证 analysis/pooling_sweep_17tools.py 被 ×8 拦，
  // 主线被迫反复 `gpu_slot.py request <p> local 0` 绕过）。两条高置信信号：
  //   1) 脚本在 analysis/ 目录下；2) .py 文件名以「出产物」动词开头/结尾（plot/build/merge/pool/agg/report/fig/table/export/collect/summary/delivery…）。
  // 仅匹配 .py 文件名本身（[\w-]*\.py 锚定），不误伤路径里的同名目录；训练脚本约定为 train*/_probe/pretrain 等不在此列。
  const isCpuAnalysis = /(^|[\/\\])analysis[\/\\][\w./-]*\.py/i.test(cmd)
    || /[\/\\]?(plot|build|merge|make|agg|aggregate|summar\w*|report|pool|pooling|fig|figure|table|export|collect|gather)[\w-]*\.py/i.test(cmd)
    || /_(delivery|report|plot|fig|figure|figures|summary|table|export)\.py/i.test(cmd);
  // 洞 A 修：训练识别不止文件名 train*.py——扩到 probe/sweep/pilot/capacity/finetune/pretrain/mqar/experiment
  // 这类「训到收敛/扫描」脚本名（防 mqar_capacity_probe.py 之类绕过）；--smoke/--dry-run/test_ 仍放行（tiny 烟测）。
  const isSmoke = /--smoke|--dry[-_]?run|\btest_|tests\//i.test(cmd);
  // 纯 CPU / 纯推理豁免：显式 CPU 设备标志 或 特征抽取/probe-only 推理脚本名 → 放行（不占 GPU，
  // 却被通用词 probe/pilot/sweep/experiment 误判成训练。实证 run_pilot.py(冻结特征抽取)/probe_only.py(numpy LR)
  // 本会话被 ×7 拦，被迫为 0-GPU 活反复 request 卡槽 + 改名绕过）。两类高置信信号：
  //   1) 命令显式 --device cpu / --cpu / CUDA_VISIBLE_DEVICES=（空）—— 用户已声明不用 GPU；
  //   2) .py 名含纯推理动词 extract_features/feature_extract/linear_probe/probe_only/infer/inference。
  // 真 GPU 训练绝不会带这些标志/名，故零漏洞。需占 GPU 的活仍照常走调度器。
  const isCpuInference =
    /--device[=\s]+cpu\b|--cpu\b|CUDA_VISIBLE_DEVICES\s*=\s*(?:""|''|)(?:\s|$)/i.test(cmd)
    || /[\/\\]?(extract_features|feature_extract\w*|linear_probe|probe_only|inference|\binfer)[\w-]*\.py/i.test(cmd);
  const isTraining = !isCompileOrTest && !isSmoke && !isCpuAnalysis && !isCpuInference && (
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
    // gpus=0（CPU/工具推理批跑）占 0 卡，须与 gpu_slot.py 的 int(gpus) 一致：
    // 只有键缺失/非数才回退 1，显式 0 保留为 0（否则 0 卡活被误记 1，free 数吓退后续申请）。
    .reduce((s, j) => { const g = parseInt(j.gpus, 10); return s + (Number.isFinite(g) ? g : 1); }, 0);

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
    `  ▸ 纯 CPU / 工具打分推理批跑（不占 GPU，如免疫原性工具 Rscript/predict、分析/probe 脚本）→ <gpus> 填 0：\n` +
    `    \`python tools/gpu_slot.py request <project> ${host} 0 [note]\` 恒 GO（占 0 卡、绝不挤正在跑的、不记 friction），跑完照常 release。别改名绕过。\n` +
    `绝不挤正在跑的任务。\n`
  );
  process.exit(2);
});
