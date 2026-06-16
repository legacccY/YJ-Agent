#!/usr/bin/env node
// UserPromptSubmit hook: 通用防跑偏注入（全项目，非仅 ICLR）。
// 当 prompt 像"动手指令"时，注入 drift 契约 + 红线 + 数据集真源指针。
// 只补 iclr_prompt_submit.js（ICLR 专属关键词）不覆盖的通用部分。静默除非命中。

const fs = require('fs');
const path = require('path');

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', c => { input += c; });
process.stdin.on('end', () => {
  let data;
  try { data = JSON.parse(input); } catch (e) { process.exit(0); }
  const cwd = (data.cwd || '').replace(/\\/g, '/');
  if (!cwd.includes('YJ-Agent')) process.exit(0);
  const root = cwd.slice(0, cwd.indexOf('YJ-Agent') + 'YJ-Agent'.length);

  const prompt = String(data.prompt || '');
  let out = '';

  // 1) 动手类指令 → drift 契约 + 红线提醒
  const actiony = /(写|改|跑|做|实现|加|删|重构|训练|实验|生成|核|审|复现|补|扩|落地|实施|搞)/.test(prompt);
  if (actiony && prompt.length > 4) {
    out += '[防跑偏] 动手前先答：本任务服务哪项目的哪个 § / lever？与该项目 STORY/ACCEPTANCE 冲突 → 停下澄清，不照描述硬干。红线：①数字一律 Bash/Grep 核 csv，不信 Read ②超参/架构查官方源，查不到标 TODO 绝不臆想 ③复现零偏离（禁私加裁剪/降 lr/改步数凑收敛）④BMVC 已封印。\n';
  }

  // 2) 数据集相关 → 指向共享真源
  if (/(数据集|dataset|data_root|data path|ISIC|HAM|Fitz|ChestX|CheXpert|Kvasir|APTOS|NIH|路径在哪|哪里下|下载)/i.test(prompt)) {
    out += '[数据集真源] 路径/下载源查 .portfolio/datasets.json（本地+HPC+source+状态），别硬编码别臆想；换路径只改那里。\n';
  }

  // 3) 大阶段收口类 → 提醒 opus 严审
  if (/(收官|大阶段|阶段性|里程碑|milestone|完成了|搞定|这一阶段|阶段完成|gate)/i.test(prompt)) {
    out += '[阶段 gate] 半天级大阶段完成 → 跑 /stage-gate <project> 让 opus reviewer 严格对 ACCEPTANCE 判 PASS/FAIL（不存在"基本完成"）。\n';
  }

  // 4) 当前窗口认领提示（有 claim 但 prompt 没提项目时轻提）
  try {
    const claims = fs.readdirSync(path.join(root, '.portfolio', 'locks')).filter(f => f.endsWith('.claim'));
    if (claims.length && actiony) {
      out += `[认领] 本组合已认领：${claims.map(c => c.replace('.claim', '')).join(', ')}。确认本窗在写的是这篇，按其入口读档。\n`;
    }
  } catch (e) {}

  if (out) process.stdout.write(out);
  process.exit(0);
});
