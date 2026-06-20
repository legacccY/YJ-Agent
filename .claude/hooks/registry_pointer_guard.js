#!/usr/bin/env node
// registry_pointer_guard.js — SessionStart 索引漂移 guard。
// 根因（2026-06-20 gdn2vessel）：新项目登了 .portfolio/registry.json 却忘了在
// CLAUDE.md「进具体某项目动手前」入口清单补行 → 新窗口选该项目读不到阶段档。
// 本 hook 每次开窗对账两索引，仅在漂移时注入一行提醒；对齐则静默（不污染 context）。
// 自包含：纯 JSON 解析 + 正则，不 spawn python，~0 开销。

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const REGISTRY = path.join(ROOT, ".portfolio", "registry.json");
const CLAUDE = path.join(ROOT, "CLAUDE.md");

const SECTION_START = "进**具体某项目**动手前";
const SECTION_END = "按需读档";

try {
  const reg = JSON.parse(fs.readFileSync(REGISTRY, "utf8"));
  const projects = reg.projects || {};
  const text = fs.readFileSync(CLAUDE, "utf8");

  const si = text.indexOf(SECTION_START);
  if (si === -1) process.exit(0); // 段标记没了，不阻断
  let ei = text.indexOf(SECTION_END, si);
  if (ei === -1) ei = text.length;
  const section = text.slice(si, ei);

  const missing = [];
  for (const [key, meta] of Object.entries(projects)) {
    const name = meta.name || "";
    const home = (meta.home || "").replace(/\/+$/, "");
    const homeShort = home.replace(/^project\//, "");
    const keyRe = new RegExp(`\\b${key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i");
    const hit =
      keyRe.test(section) ||
      (name && section.includes(name)) ||
      (home && section.includes(home)) ||
      (homeShort && section.includes(homeShort));
    if (!hit) missing.push(`${key}(${name},${meta.status || "?"})`);
  }

  if (missing.length) {
    const msg =
      `⚠️ 索引漂移：${missing.length} 个项目在 registry 但 CLAUDE.md 入口清单缺登记 → ` +
      `${missing.join(", ")}。新窗口选它会读不到阶段档，补 CLAUDE.md「进具体某项目动手前」一行修` +
      `（python tools/check_registry_pointers.py 看详情）。`;
    console.log(msg);
  }
} catch (e) {
  // guard 永不阻断 session 启动
}
process.exit(0);
