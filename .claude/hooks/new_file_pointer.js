#!/usr/bin/env node
// PostToolUse (Write) hook: 新建重要项目文件却没在索引文档里登指针 → 提醒。
// 防"新脚本/新章节/新 config 散落无人指向、下次会话找不到"。
// 只在 Write（新建/整体覆写）触发，不在 Edit；非项目源文件静默；已被任一索引文档引用则静默。
// exit 2 + stderr = 提醒（非阻断性，给主线看到即可补指针）。

const fs = require('fs');
const path = require('path');
const { log } = require('./_friction.js');

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', c => { input += c; });
process.stdin.on('end', () => {
  let data;
  try { data = JSON.parse(input); } catch (e) { process.exit(0); }
  if ((data.tool_name || '') !== 'Write') process.exit(0);

  const fp = (data.tool_input && data.tool_input.file_path) || '';
  const norm = fp.replace(/\\/g, '/');
  if (!norm.includes('YJ-Agent')) process.exit(0);

  const root = norm.slice(0, norm.indexOf('YJ-Agent') + 'YJ-Agent'.length);
  const rel = norm.slice(norm.indexOf('YJ-Agent') + 'YJ-Agent'.length + 1);

  // 只关心"重要"源文件：脚本 / 论文章节 / config / plan 文档
  const important = /\.(py|tex|ya?ml|json|md)$/i.test(rel) && rel.startsWith('project/');
  if (!important) process.exit(0);

  // 自身就是索引/日志/临时 → 不要求被指（README / LOG / registry / _scratch / _archive / sentinels）
  const base = path.basename(rel);
  if (/(README|_LOG|PROJECT_LOG|04_LOG|registry|MEMORY|PORTFOLIO|SUBMITTED)/i.test(base)) process.exit(0);
  if (/\/(\_scratch|\_archive|archive|sentinels|node_modules)\//.test('/' + rel)) process.exit(0);

  // 深层代码/config 子树（src/ configs/ utils/ scripts/ code/ eval/ tools/ 下的文件）→ 整个目录已被项目索引覆盖，单文件不逐一登
  if (/\/(src|configs?|utils?|scripts?|code|eval|tools?)\//.test('/' + rel)) process.exit(0);

  // 带日期戳的调研/日志 md（文件名含 \d{4}-\d{2}-\d{2}）→ 日记性质，不要求上层索引
  if (/\d{4}-\d{2}-\d{2}/.test(base)) process.exit(0);

  // 候选索引文档：PORTFOLIO + registry + 文件所在项目树内的 README / *LOG*
  const indexFiles = [
    path.join(root, 'PORTFOLIO.md'),
    path.join(root, '.portfolio', 'registry.json'),
  ];
  // 向上找该文件所在项目目录的索引（最多回溯到 project/）
  let dir = path.dirname(path.join(root, rel));
  const stop = path.join(root, 'project');
  for (let i = 0; i < 8 && dir.length >= stop.length; i++) {
    for (const name of ['README.md', 'PROJECT_LOG.md', '04_LOG.md']) {
      const f = path.join(dir, name);
      if (fs.existsSync(f)) indexFiles.push(f);
    }
    if (dir === stop) break;
    dir = path.dirname(dir);
  }

  // 是否任一索引文档已提到此文件 basename？
  let referenced = false;
  for (const f of indexFiles) {
    try {
      if (fs.readFileSync(f, 'utf8').includes(base)) { referenced = true; break; }
    } catch (e) {}
  }
  if (referenced) process.exit(0);

  log('no-pointer', rel);
  process.stderr.write(
    `[新文件无指针] ${rel}\n` +
    `刚建的重要文件没在任何索引文档登记。补一条指针到对应项目的 README / PROJECT_LOG / 04_LOG（或 registry / PORTFOLIO），免得下次会话找不到、散落跑偏。\n` +
    `若是临时探针放 _scratch/ 则无须登记。\n`
  );
  process.exit(2);
});
