// 共享摩擦信号记录器。block 类 hook 触发时调一行，把"已发生的拦截"变成"重复问题"证据。
// 零模型 token（纯 JS 文件写入）。optimizer agent 读 .portfolio/friction.jsonl 聚类找根因。
// 设计：只记 block/重复类信号，一行一事件，不记一次性细节（贴合"不过度记录"）。
// best-effort：任何失败静默吞掉，绝不拖垮触发它的 hook。

const fs = require('fs');
const path = require('path');

// __dirname = <root>/.claude/hooks → 上溯两级到 root
const ROOT = path.join(__dirname, '..', '..');
const LOG = path.join(ROOT, '.portfolio', 'friction.jsonl');

// type: 信号类型（redline / no-pointer / caveman-on-write / training-lock-block / ...）
// detail: 短串（如文件相对路径 / 命中模式），禁长文本
function log(type, detail) {
  try {
    const line = JSON.stringify({
      ts: new Date().toISOString(),
      type: String(type),
      detail: String(detail || '').slice(0, 200),
    });
    fs.appendFileSync(LOG, line + '\n');
  } catch (e) { /* 静默 */ }
}

module.exports = { log };
