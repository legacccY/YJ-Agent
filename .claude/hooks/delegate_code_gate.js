#!/usr/bin/env node
// PreToolUse(Edit|Write|MultiEdit) hook: 主线「正要写实验码」那一刻拦一下 → 提醒派 coder。
// 直击根因：派单提示原本挂 UserPromptSubmit（只在用户含关键词发话时触发），
// 但写码决定常发生在主线中途推理（用户只说「继续」），那刻无 prompt → 旧提示永不触发。
// 本 hook 挂在「写文件」事件，正好命中决策点。
//
// 设计（节流 + 可绕过，绝不硬卡死）：
//   - 只管 project/ 下实验 .py（排 _scratch/tests/_archive/docs）。
//   - 命中且距上次拦截 > THROTTLE → exit 2 一次强提醒（派 coder）；记时间戳。
//   - THROTTLE 内同类写入 → 放行（不唠叨；也让 coder 子代理首拦后重试即过 + 后续连写不卡）。
//   - 放行口（重试即过）：你就是 coder / <15 行小修 / 非实验逻辑。
//   - 任何异常一律 exit 0 失败放行，绝不拖垮 session。

const fs = require('fs');
const path = require('path');

const THROTTLE_MS = 30 * 60 * 1000; // 30 分钟内只提醒一次，避免同工作段连写重复噪声

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

  // 只管研究项目实验代码：project/ 下 .py，排临时/测试/存档
  if (!/\/project\//.test(norm)) process.exit(0);
  if (!/\.py$/i.test(norm)) process.exit(0);
  if (/\/(_scratch|_archive|node_modules|\.git)\//.test(norm)) process.exit(0);
  // ideation/runs/ 下是流水线辅助脚本（dedup/killshot plan 等），非模型训练码 → 放行
  if (/\/ideation\/runs\//.test(norm)) process.exit(0);
  if (/\/tests?\//.test(norm) || /(^|\/)(test_|conftest)/i.test(norm)) process.exit(0);

  // 定位 state 文件
  const cwd = (data.cwd || process.cwd()).replace(/\\/g, '/');
  const root = cwd.includes('YJ-Agent') ? cwd.slice(0, cwd.indexOf('YJ-Agent') + 'YJ-Agent'.length) : 'D:/YJ-Agent';
  const statePath = path.join(root, '.claude', 'hooks', '.delegate_gate_state.json');

  let last = 0;
  try { last = JSON.parse(fs.readFileSync(statePath, 'utf8')).last_block_ts || 0; } catch (e) { last = 0; }

  const now = Date.now();
  if (now - last < THROTTLE_MS) process.exit(0); // 节流窗内 → 放行不唠叨

  // 记时间戳（先写，避免重试时再次拦）
  try { fs.writeFileSync(statePath, JSON.stringify({ last_block_ts: now }, null, 2)); } catch (e) {}

  // friction 记账（best-effort）
  // 注意：hook 无法区分主线 vs subagent 写入（Claude hook schema 无 agent 标识字段）。
  // 用 code-gate-trigger 而非 main-writes-code，避免 optimizer 误把 coder 的写入当主线违规聚类。
  try { require('./_friction.js').log('code-gate-trigger', norm.split('YJ-Agent/')[1] || norm); } catch (e) {}

  const short = norm.split('YJ-Agent/')[1] || norm;
  // 用户决策（2026-06-19）：改训练/实验文件不需拍板、auto=acceptEdits 放开权限 →
  // 本门降级为「只提醒不拦」（exit 0），不再 exit 2 打断主线写入。派 coder 仍是推荐默认，但软提醒。
  process.stderr.write(
    `[派单门 💡软提醒] 正写实验码 ${short}\n` +
    `推荐默认：写/改实验代码派 coder(sonnet) 省主线 context；多个独立文件并行多 coder。\n` +
    `→ Task(subagent_type="coder", prompt=路径+目标+Windows规范+「不启训练」+服务哪项目§)。\n` +
    `（已放行，不打断；小修/纯配置/你就是 coder 时直接写即可。6 分钟内同类不再提醒。）\n`
  );
  process.exit(0);
});
