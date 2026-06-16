#!/usr/bin/env node
// PreToolUse(Edit|Write|...) hook: 写论文正文时提醒 caveman OFF（文字保真）。
// 命中 .tex / paper|drafts 类 .md → 注入 additionalContext。其他文件静默放行。
// 非阻断（exit 0）。caveman 仅内部沟通用，写作一律关。

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', c => { input += c; });
process.stdin.on('end', () => {
  let data;
  try { data = JSON.parse(input); } catch (e) { process.exit(0); }
  const tool = data.tool_name || '';
  if (!/^(Edit|Write|MultiEdit|NotebookEdit)$/.test(tool)) process.exit(0);

  const fp = ((data.tool_input && data.tool_input.file_path) || '').replace(/\\/g, '/');
  if (!fp) process.exit(0);

  const isWriting =
    /\.tex$/i.test(fp) ||
    /\.bib$/i.test(fp) ||
    (/\.md$/i.test(fp) && /(\/paper\/|\/drafts\/|\/meeting\/ICLR2027\/|rebuttal|camera_ready)/i.test(fp));
  if (!isWriting) process.exit(0);

  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      additionalContext:
        "✍️ 写作模式：caveman OFF。本文件是论文正文/参考文献，措辞需完整规范、" +
        "保真，禁缩写禁省冠词连接词。数字只用已核实值（疑则 \\todo 占位过 verifier）。"
    }
  }));
  process.exit(0);
});
