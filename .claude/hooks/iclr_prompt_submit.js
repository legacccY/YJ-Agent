#!/usr/bin/env node
// UserPromptSubmit hook: keyword reminders + Opus-in-ICLR caveman-off signal.
// Silent unless triggered.

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', () => {
  let data;
  try { data = JSON.parse(input); } catch (e) { process.exit(0); }

  const cwd = (data.cwd || '').replace(/\\/g, '/');
  if (!cwd.includes('YJ-Agent')) process.exit(0);

  const prompt = String(data.prompt || '');
  let out = '';

  // Opus-in-ICLR caveman override (cwd within project/)
  if (cwd.includes('YJ-Agent/project')) {
    out += '[Opus-in-ICLR rule] CAVEMAN MODE OVERRIDE — Opus 在 project/ 内用正常中文，不 caveman。Sonnet/Haiku subagent 可继续 caveman。\n';
  }

  // Keyword triggers
  if (/(写论文|写tex|写 tex|ICLR 论文|draft|章节|Section|main paper)/i.test(prompt)) {
    out += '[Keyword: 论文/tex] Before edit meeting/ICLR2027/*.tex: Read STORY_FRAMEWORK.md (§1-§9 锁定) + DATA_INVENTORY.md (数字 csv 源). 数字必须 csv 核算.\n';
  }
  if (/(跑实验|开始训练|启动训练|train|实验|config|重训)/i.test(prompt)) {
    out += '[Keyword: 训练] 用 /loop /run-experiment 触发 (CLAUDE.md 规范). Start-Process 开新窗口避免阻塞.\n';
  }
  if (/(改 BMVC|改BMVC|BMVC 加|改 itb_paper|改itb_paper)/i.test(prompt)) {
    out += '[Keyword: BMVC] BMVC SEALED. 任何改动走 meeting/BMVC/rebuttal/ 或 meeting/ICLR2027/.\n';
  }
  if (/(扩散|diffusion|DiffBIR|SD-Turbo|Stable Diffusion)/i.test(prompt)) {
    out += '[Keyword: 扩散] R8 红线: 扩散模型禁用于皮肤镜增强 (伪影). 只能在 §8.2 作为对照警示出现.\n';
  }

  if (out) process.stdout.write(out);
  process.exit(0);
});
