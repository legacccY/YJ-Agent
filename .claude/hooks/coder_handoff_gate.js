#!/usr/bin/env node
// PostToolUse (Edit|Write) hook: 改了 project/ 下的 .py 实验脚本 → 自动 py_compile 验语法。
// 语法错 → 回灌 stderr 让下一步自修（质量回环），exit 2 非阻断。
// hook 自身任何异常（python 不在 PATH、超时等）一律静默 exit 0，绝不拖垮 session。

const { execFileSync } = require('child_process');

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', c => { input += c; });
process.stdin.on('end', () => {
  let data;
  try { data = JSON.parse(input); } catch (e) { process.exit(0); }

  const tool = data.tool_name || '';
  if (tool !== 'Edit' && tool !== 'Write' && tool !== 'MultiEdit') process.exit(0);

  const fp = (data.tool_input && data.tool_input.file_path) || '';
  const norm = fp.replace(/\\/g, '/');
  // 只管项目内的 .py，排除测试/临时探针（tests 自有 pytest，_scratch 不计）
  if (!norm.includes('YJ-Agent')) process.exit(0);
  if (!/\.py$/i.test(norm)) process.exit(0);
  if (!/\/project\//.test(norm)) process.exit(0);
  if (/\/(_scratch|_archive|node_modules)\//.test(norm)) process.exit(0);

  // py_compile 验语法。任何 spawn 层错误（python 没装/超时）→ 静默放过。
  try {
    execFileSync('python', ['-m', 'py_compile', fp], { stdio: 'pipe', timeout: 8000 });
    process.exit(0); // 编译过 → 静默
  } catch (err) {
    if (err && err.code === 'ENOENT') process.exit(0); // python 不在 PATH → 不报
    if (err && err.signal) process.exit(0);            // 超时被杀 → 不报
    // 走到这 = py_compile 非零退出 = 真语法错
    let detail = '';
    try { detail = (err.stderr || err.stdout || '').toString().split('\n').filter(Boolean).slice(-4).join('\n'); } catch (e) {}
    process.stderr.write(
      `[coder 质量门] py_compile 失败：${norm.split('YJ-Agent/')[1] || norm}\n` +
      (detail ? detail + '\n' : '') +
      `交付/启动训练前先修语法。coder 交付应已过 py_compile + pytest——若这是 coder 产出，让其修复后再交。\n`
    );
    process.exit(2);
  }
});
