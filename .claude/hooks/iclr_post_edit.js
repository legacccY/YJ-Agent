#!/usr/bin/env node
// PostToolUse hook: scan red-line patterns in ICLR tex/md edits.
// exit 2 + stderr = warn. Silent on pass.

const fs = require('fs');
const { log } = require('./_friction.js');

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', () => {
  let data;
  try { data = JSON.parse(input); } catch (e) { process.exit(0); }

  const tool = data.tool_name || '';
  if (!/^(Edit|Write|MultiEdit)$/.test(tool)) process.exit(0);

  const path = (data.tool_input && data.tool_input.file_path) || '';
  const norm = path.replace(/\\/g, '/');

  // Target paths: ICLR2027 *.tex/*.md (full check), or main project guidance docs (writing-only check)
  // Exempt: _开头的 prep/工具文档（如 _脱敏替换表.md），这类文件合法引用禁词作为"需 grep 清单"
  const base = (norm.split('/').pop() || '');
  const isPrepDoc = /^_/.test(base) && /\.md$/.test(base);
  const isTexTarget = !isPrepDoc && /project\/meeting\/ICLR2027\/.*\.(tex|md)$/.test(norm);
  const isDocTarget = /project\/(STORY_FRAMEWORK|ACCEPTANCE_CRITERIA|README)\.md$/.test(norm);

  if (!isTexTarget && !isDocTarget) process.exit(0);

  let content;
  try { content = fs.readFileSync(path, 'utf8'); } catch (e) { process.exit(0); }

  // tex: full redline (anonymization + model names + writing rules)
  // planning docs: writing-quality only. anonymization tokens (anonymous2025) are
  // dropped here — in planning docs they appear only as meta (rules / grep checks),
  // and the real anonymization gate is the tex full-check above.
  const patterns = isTexTarget
    ? /(anonymous2025|VisiSkin-Agent|VisiScore-Net|VisiEnhance-Net|Q-VIB\b|DiffBIR|SD-Turbo|TS always reverses|universal reversal|we prove|\bBayesian\b|doctors? confirmed|clinically validated|clinical decision support)/g
    : /(TS always reverses|universal reversal|doctors? confirmed|clinically validated|clinical decision support)/g;
  // Doc mode quotes banned phrases as DON'T examples (R1-R10 rule table). Skip a
  // match whose preceding char is a quote so the rulebook can cite what it forbids.
  const QUOTES = new Set(['"', '“', '”', '「', '」']);
  const lines = content.split('\n');
  const hits = [];
  lines.forEach((line, idx) => {
    patterns.lastIndex = 0;
    let m;
    while ((m = patterns.exec(line)) !== null) {
      if (!isTexTarget && m.index > 0 && QUOTES.has(line[m.index - 1])) continue;
      hits.push(`${idx + 1}: ${line.trim()}`);
      break;
    }
  });

  if (hits.length > 0) {
    log('redline', path.replace(/\\/g, '/').split('YJ-Agent/').pop());
    process.stderr.write(`REDLINE HIT in ${path} (R1/R2/R4/R8):\n`);
    hits.slice(0, 5).forEach(h => process.stderr.write(`${h}\n`));
    process.stderr.write('Fix before continuing. See project/STORY_FRAMEWORK.md R1-R10.\n');
    process.exit(2);
  }

  process.exit(0);
});
