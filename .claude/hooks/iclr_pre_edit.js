#!/usr/bin/env node
// PreToolUse hook: block edits to sealed BMVC dir.
// exit 2 + stderr = block. Silent on pass.

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', () => {
  let data;
  try { data = JSON.parse(input); } catch (e) { process.exit(0); }

  const tool = data.tool_name || '';
  if (!/^(Edit|Write|NotebookEdit|MultiEdit)$/.test(tool)) process.exit(0);

  const path = (data.tool_input && data.tool_input.file_path) || '';
  const norm = path.replace(/\\/g, '/');

  if (norm.includes('project/meeting/BMVC/')) {
    if (norm.includes('meeting/BMVC/rebuttal/') || norm.includes('meeting/BMVC/camera_ready/')) {
      process.exit(0);
    }
    process.stderr.write(
      `BMVC SEALED 2026-05-24. Edit blocked: ${path}. ` +
      `Use meeting/ICLR2027/ for new work; meeting/BMVC/rebuttal/ for rebuttal.\n`
    );
    process.exit(2);
  }

  process.exit(0);
});
