#!/usr/bin/env node
// PreToolUse hook: BMVC unsealed 2026-07-04 (rebuttal/decision phase).
// No longer blocks. Soft reminder that the submitted manuscript matches OpenReview.

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
      `BMVC unsealed (rebuttal/decision phase). Note: ${path} is the OpenReview-submitted version; ` +
      `edit only for camera-ready or a deliberate reason. New work → meeting/BMVC/rebuttal/ or camera_ready/.\n`
    );
    process.exit(0);
  }

  process.exit(0);
});
