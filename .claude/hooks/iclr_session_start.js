#!/usr/bin/env node
// SessionStart hook: brief reminder if cwd is YJ-Agent project.
// Silent if not in YJ-Agent.

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', () => {
  let data;
  try { data = JSON.parse(input); } catch (e) { process.exit(0); }
  const cwd = (data.cwd || '').replace(/\\/g, '/');
  if (!cwd.includes('YJ-Agent')) process.exit(0);
  process.stdout.write(
    '[ICLR 2027 大项目 active] Read order if writing tex/数字: ' +
    'project/README.md -> STORY_FRAMEWORK.md -> ACCEPTANCE_CRITERIA.md -> ' +
    'DATA_INVENTORY.md -> PROJECT_LOG.md. BMVC SEALED. Opus 在 project/ 内关 caveman。\n'
  );
  process.exit(0);
});
