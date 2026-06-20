#!/usr/bin/env python3
"""check_registry_pointers.py — 组合台索引漂移检查（drift guard）。

根因（2026-06-20 gdn2vessel 踩坑）：新项目只登 .portfolio/registry.json，
忘了在 CLAUDE.md「进具体某项目动手前」入口清单补一行 → 新窗口选该项目读不到
阶段文档（registry 只让 SessionStart hook 报进度，读档指令真源是 CLAUDE.md 清单）。

本工具对账两个索引，列出任一边缺失的项目。建档流程（/spin-off-paper Step 7、
PROJECT_LIFECYCLE 新项目 SOP step 2c）收尾必跑；/optimize 与收工自检也可跑。

退出码：0 = 对齐；1 = 有漂移（CI/hook 可据此拦）。
用法：python tools/check_registry_pointers.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / ".portfolio" / "registry.json"
CLAUDE = ROOT / "CLAUDE.md"

# CLAUDE.md 入口清单段：从「进具体某项目动手前」到「按需读档」之间
SECTION_START = "进**具体某项目**动手前"
SECTION_END = "按需读档"


def load_registry_projects():
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return data.get("projects", {})


def load_pointer_section():
    text = CLAUDE.read_text(encoding="utf-8")
    si = text.find(SECTION_START)
    if si == -1:
        sys.exit(f"FATAL: CLAUDE.md 找不到入口清单段标记 '{SECTION_START}'")
    ei = text.find(SECTION_END, si)
    if ei == -1:
        ei = len(text)
    return text[si:ei]


def main():
    projects = load_registry_projects()
    section = load_pointer_section()

    missing = []  # 在 registry 但 CLAUDE.md 入口清单查不到
    for key, meta in projects.items():
        name = meta.get("name", "")
        home = (meta.get("home") or "").rstrip("/")
        # home 去掉 project/ 前缀做宽松匹配（清单里有时写相对 meeting/... 路径）
        home_short = re.sub(r"^project/", "", home)
        # 命中任一即视为已登：key（忽略大小写）/ name / home 路径出现在清单段
        hit = (
            re.search(rf"\b{re.escape(key)}\b", section, re.IGNORECASE)
            or (name and name in section)
            or (home and home in section)
            or (home_short and home_short in section)
        )
        if not hit:
            missing.append((key, name, meta.get("status", "?"), home))

    if not missing:
        print(f"OK: registry {len(projects)} 个项目全部在 CLAUDE.md 入口清单登记，无漂移。")
        return 0

    print(f"DRIFT: {len(missing)} 个项目在 registry 但 CLAUDE.md 入口清单缺登记：")
    for key, name, status, home in missing:
        print(f"  - {key} ({name}, status={status}) → 补一行入口指向 {home}/00_README.md")
    print("\n修法：CLAUDE.md「进具体某项目动手前」清单补行，格式见 PROJECT_LIFECYCLE 新项目 SOP step 2b。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
